# app/daily_checkin/routes.py
from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request, redirect, render_template, flash, current_app, url_for, jsonify
import pandas as pd

# ── Active Clients payload + resolvers
from app.daily_checkin.services.active_clients_from_history import (
    build_active_clients_payload,
    resolve_agenda_history_path,
    resolve_customers_history_path,
)

# ✅ Expiring-contracts → monthly-planning rows service
#    Prefer the actual path you shared (app/services/...), but keep a fallback.
try:
    from app.services.internal_planning_from_contracts import load_expiring_contract_rows
except Exception:  # backward-compat fallback
    from app.daily_checkin.services.internal_planning_from_contracts import load_expiring_contract_rows  # type: ignore

# ─────────────────────────── Removed modules replaced by safe stubs ───────────────────────────
def send_to_google_chat(message: str):
    """Stub replacement: Log instead of sending webhook."""
    current_app.logger.info(f"[daily_checkin] Google Chat webhook disabled.\nMessage:\n{message[:500]}...")

def save_report(sections: dict[str, pd.DataFrame], report_name: str):
    """Save sections into a timestamped Excel file inside /download/."""
    try:
        download_dir = os.path.join(current_app.root_path, "download")
        os.makedirs(download_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(download_dir, f"{report_name}_{timestamp}.xlsx")
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sheet_name, df in sections.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        current_app.logger.info(f"[daily_checkin] Report saved → {path}")
    except Exception as e:
        current_app.logger.error(f"[daily_checkin] save_report failed: {e}")

# ✅ small metric reused from Figurella Reports
from app.figurella_reports.services.location_performance.active_clients import (
    compute_active_clients_this_month,
)

# ─────────────────────────── Blueprint ───────────────────────────
daily_checkin_bp = Blueprint("daily_checkin", __name__)

# ─────────────────────────── Template safety: always provide DC_DATA ───────────────────────────
@daily_checkin_bp.app_context_processor
def _inject_dc_default():
    # Ensures {{ (DC_DATA|default({}))|tojson }} never fails
    return {"DC_DATA": {}}

# ─────────────────────────── Paths ───────────────────────────
def _app_root() -> Path:
    # this file: app/daily_checkin/routes.py → up two levels = app/
    return Path(__file__).resolve().parents[2]

def _instance_dir() -> Path:
    return Path(current_app.instance_path)

# ---------- Pretty text helpers (monospace tables + emojis) ----------
MAX_ROWS_PER_SECTION = 12
COL_WIDTHS = {
    "Client Name": 18, "Package Sold": 18, "Revenue": 10,
    "Name": 18, "Scheduled Date": 12, "Lead Source": 16,
    "Outcome": 14, "Provider": 16, "Description": 28,
    "Attended": 10, "No-Show": 10,
}

def _clip(s, n):
    s = ("" if s is None else str(s)).strip()
    return s if len(s) <= n else (s[: max(0, n - 1)] + "…")

def _money_to_text(x):
    try:
        val = float(str(x).replace(",", "").replace("$", "").strip())
        return f"${val:,.2f}"
    except Exception:
        return str(x or "")

def _column_widths(headers, rows):
    widths = [len(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))
    capped = []
    for i, h in enumerate(headers):
        cap = COL_WIDTHS.get(h)
        capped.append(min(widths[i], cap) if cap else widths[i])
    return capped

def _df_to_table(df: pd.DataFrame, columns, max_rows: int = MAX_ROWS_PER_SECTION):
    if df.empty:
        return "(no entries)", 0
    data = df.copy()
    if "Revenue" in data.columns:
        data["Revenue"] = data["Revenue"].map(_money_to_text)

    clipped = []
    for _, row in data[columns].fillna("").astype(str).iterrows():
        clipped.append([_clip(row[col], COL_WIDTHS.get(col, 22)) for col in columns])

    omitted = max(0, len(clipped) - max_rows)
    rows_for_view = clipped[:max_rows]
    widths = _column_widths(columns, rows_for_view)
    header = " | ".join(h.ljust(w) for h, w in zip(columns, widths))
    sep = "-+-".join("-" * w for w in widths)
    body = [" | ".join(c.ljust(w) for c, w in zip(r, widths)) for r in rows_for_view]
    out = "\n".join([header, sep, *body])
    if omitted:
        out += f"\n… (+{omitted} more)"
    return out, omitted

def _build_summary(sections):
    parts = []
    if (df := sections.get("Sales")) is not None and not df.empty:
        total = 0.0
        for v in df.get("Revenue", []):
            try:
                total += float(str(v).replace(",", "").replace("$", "").strip())
            except Exception:
                pass
        parts.append(f"💸 Sales: {len(df)} (Total {_money_to_text(total)})")
    if (df := sections.get("Leads")) is not None and not df.empty:
        parts.append(f"🧲 Leads: {len(df)}")
    if (df := sections.get("Consultations")) is not None and not df.empty:
        parts.append(f"🗓️ Consultations: {len(df)}")
    if (df := sections.get("Opportunities")) is not None and not df.empty:
        parts.append(f"🌟 Opportunities: {len(df)}")
    if (df := sections.get("Attendance")) is not None and not df.empty:
        att = df.get("Attended", pd.Series([], dtype=str)).astype(str).str.strip()
        nos = df.get("No-Show", pd.Series([], dtype=str)).astype(str).str.strip()
        parts.append(f"👥 Attendance: {len(df)} (✔️ {(att!='').sum()} | ❌ {(nos!='').sum()})")
    return " • ".join(parts) if parts else "No data"

def _build_plain_text_message(submission_date, sections, history_url: str | None):
    lines = [f"✅ *Daily Check-in Submitted*  \n_{submission_date}_",
             "━━━━━━━━━━━━━━━━━━━━",
             f"*Summary:* {_build_summary(sections)}"]

    def add(title, key, cols, emoji):
        df = sections.get(key)
        if df is not None and not df.empty:
            table, _ = _df_to_table(df, cols)
            lines.append(f"\n*{emoji} {title}*")
            lines.append("```\n" + table + "\n```")

    add("Sales", "Sales", ["Client Name", "Package Sold", "Revenue"], "💸")
    add("Leads", "Leads", ["Name", "Scheduled Date", "Lead Source"], "🧲")
    add("Consultations", "Consultations", ["Client Name", "Outcome", "Lead Source"], "🗓️")
    add("Opportunities", "Opportunities", ["Name", "Provider", "Description"], "🌟")
    add("Attendance", "Attendance", ["Attended", "No-Show"], "👥")

    if history_url:
        lines.append(f"\n📁 *History:* {history_url}")
    return "\n".join(lines)

# ---------- Views ----------
@daily_checkin_bp.route("/")
def index():
    """Redirect /daily-check-in → the combined report wizard."""
    return redirect(url_for("daily_checkin.combined_report_wizard"))

@daily_checkin_bp.route("/wizard", endpoint="combined_report_wizard")
def combined_report_wizard():
    """Main launcher + Daily Checks wizard."""
    app_root = _app_root()
    instance_dir = _instance_dir()
    try:
        active_clients = compute_active_clients_this_month(app_root, instance_dir)
    except TypeError:  # older one-arg version
        active_clients = compute_active_clients_this_month(app_root)

    DC_DATA = {"active_clients": int(active_clients)}
    return render_template("daily_checkin/daily_checkin.html",
                           active_page="report",
                           DC_DATA=DC_DATA)

@daily_checkin_bp.route("/report")
def report_home():
    return redirect(url_for("daily_checkin.combined_report_wizard"))

@daily_checkin_bp.route("/submit", methods=["POST"])
def submit_report():
    submission_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Collect form data
    sales = zip(
        request.form.getlist("client_name[]"),
        request.form.getlist("package_sold[]"),
        request.form.getlist("revenue[]"),
    )
    leads = zip(
        request.form.getlist("lead_name[]"),
        request.form.getlist("lead_date[]"),
        request.form.getlist("lead_source[]"),
    )
    consultations = zip(
        request.form.getlist("consult_client[]"),
        request.form.getlist("consult_outcome[]"),
        request.form.getlist("consult_source[]"),
    )
    opportunities = zip(
        request.form.getlist("opp_name[]"),
        request.form.getlist("opp_provider[]"),
        request.form.getlist("opp_description[]"),
    )
    attendance = zip(
        request.form.getlist("att_attended[]"),
        request.form.getlist("att_no_show[]"),
    )

    # Build DataFrames
    df_sales = pd.DataFrame(sales, columns=["Client Name", "Package Sold", "Revenue"]).dropna(how="all")
    df_leads = pd.DataFrame(leads, columns=["Name", "Scheduled Date", "Lead Source"]).dropna(how="all")
    df_consults = pd.DataFrame(consultations, columns=["Client Name", "Outcome", "Lead Source"]).dropna(how="all")
    df_opps = pd.DataFrame(opportunities, columns=["Name", "Provider", "Description"]).dropna(how="all")
    df_attendance = pd.DataFrame(attendance, columns=["Attended", "No-Show"]).dropna(how="all")

    for df in [df_sales, df_leads, df_consults, df_opps, df_attendance]:
        if not df.empty:
            df.insert(0, "Date", submission_date)

    sections = {k: v for k, v in {
        "Sales": df_sales,
        "Leads": df_leads,
        "Consultations": df_consults,
        "Opportunities": df_opps,
        "Attendance": df_attendance,
    }.items() if not v.empty}

    if sections:
        save_report(sections, "daily_checkins")
        flash("✅ Report submitted successfully!", "success")
        try:
            history_url = url_for("daily_checkin.report_history", _external=True)
        except Exception:
            history_url = None
        try:
            msg = _build_plain_text_message(submission_date, sections, history_url)
            send_to_google_chat(msg)
        except Exception as e:
            current_app.logger.error(f"[daily_checkin] Chat notification failed: {e}")
    else:
        flash("⚠️ No data entered — nothing to save.", "warning")

    return redirect(url_for("daily_checkin.combined_report_wizard"))

@daily_checkin_bp.route("/report/history", endpoint="report_history")
def report_history():
    download_dir = os.path.join(current_app.root_path, "download")
    os.makedirs(download_dir, exist_ok=True)
    files = sorted([f for f in os.listdir(download_dir) if f.endswith(".xlsx")], reverse=True)
    return render_template("daily_checkin/report_history.html", files=files, active_page="report")

@daily_checkin_bp.route("/monthly-planning", methods=["GET"])
def monthly_planning():
    """Client-side monthly planner (autosave + CSV export handled by JS)."""
    exp_url = url_for("daily_checkin.monthly_planning_expiring_contracts")
    return render_template(
        "daily_checkin/monthly_planning.html",
        active_page="report",
        MP_EXP_URL=exp_url,   # <-- expose the JSON endpoint to the page
    )

# ✅ JSON for auto-filling Internal Planning from contracts ending this month
@daily_checkin_bp.get("/monthly-planning/expiring-contracts")
def monthly_planning_expiring_contracts():
    """
    Returns rows for Monthly Planning where contract endDate is in the target month.
    Query override:
      - ?month=YYYY-MM   → use that month instead of 'now'
    Row fields:
      - internal_planning: customerId
      - closing_date:      endDate (YYYY-MM-DD)
      - current_contract:  productNames (if available)
    """
    app_root = _app_root()
    instance_dir = _instance_dir()

    # Optional month override for testing or backfilling
    when = datetime.now()
    month_str = (request.args.get("month") or "").strip()
    if month_str:
        # Accept YYYY-MM or YYYY-MM-DD
        for fmt in ("%Y-%m", "%Y-%m-%d"):
            try:
                when = datetime.strptime(month_str, fmt)
                break
            except ValueError:
                continue

    rows = load_expiring_contract_rows(app_root, instance_dir, when=when)
    return jsonify({"rows": rows, "ok": True})

# ---------- JSON fallback for page JS ----------
@daily_checkin_bp.get("/_data")
def daily_checkin_data():
    app_root = _app_root()
    instance_dir = _instance_dir()
    try:
        active_clients = compute_active_clients_this_month(app_root, instance_dir)
    except TypeError:
        active_clients = compute_active_clients_this_month(app_root)
    return jsonify({"ok": True, "data": {"active_clients": int(active_clients)}})

# ═══════════════════════ Active Clients (agenda + customers history) ═══════════════════════
@daily_checkin_bp.route("/active-clients/data")
def active_clients_data():
    """
    Serve the Active Clients payload generated by the service.
    This includes ID → (name + surname) replacement using customers_history.xlsx.
    """
    year = int(request.args.get("year", datetime.now().year))
    app_root = Path(current_app.root_path).parent   # /app
    instance_dir = Path(current_app.instance_path)
    payload = build_active_clients_payload(year, app_root, instance_dir)
    return jsonify(payload), (200 if payload.get("ok") else 400)

@daily_checkin_bp.route("/active-clients/debug")
def active_clients_debug():
    """Quick check of where the files are and their columns."""
    app_root = Path(current_app.root_path).parent
    instance_dir = Path(current_app.instance_path)

    agenda_path = resolve_agenda_history_path(app_root, instance_dir)
    customers_path = resolve_customers_history_path(app_root, instance_dir)

    info = {
        "agenda_path": str(agenda_path) if agenda_path else None,
        "customers_path": str(customers_path) if customers_path else None,
    }
    try:
        if agenda_path:
            df_a = pd.read_excel(agenda_path, nrows=5)
            info["agenda_cols"] = list(map(str, df_a.columns))
        if customers_path:
            df_c = pd.read_excel(customers_path, nrows=5)
            info["customers_cols"] = list(map(str, df_c.columns))
    except Exception as e:
        info["error"] = str(e)

    return jsonify(info)
