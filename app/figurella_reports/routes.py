# app/figurella_reports/routes.py
from __future__ import annotations
from flask import Blueprint, render_template, request, jsonify, current_app, send_file, abort
from pathlib import Path
from datetime import datetime, timedelta, timezone
import shutil
import pandas as pd

# Use the same modules your CLI uses
from .services.api_client import fetch_customers, fetch_payments, fetch_agenda, fetch_contracts
from .services.export_excel import (
    save_customers_excel,
    save_agenda_excel,
    save_payments_excel,
)
from .services.customer_history import update_customer_history
from .services.agenda_history import update_agenda_history
from .services.payment_history import update_payment_history

# Contracts + Notes
from .services.contracts_sync import sync_contracts_to_excel
from .services.contracts_history import update_contracts_history
from .services.notes_sync import run_notes_sync  # writes customer_notes.xlsx and updates customer_notes_history.xlsx

# ---------- Location Performance helpers ----------
# New clients summary (registrationDate + OK / Current… / Consultation OK; TRY split; unique by id default)
from .services.location_performance.clients_monthly_summary import (
    compute_clients_monthly_summary,
)

# Active clients this month (unique customerId with OK appointments in current month)
from .services.location_performance.active_clients import (
    compute_active_clients_this_month,
)

# Weekly attendance helper (already in your project)
try:
    from .services.location_performance.perf_metrics import compute_weekly_attendance
except Exception:
    # Safe fallback so the page doesn't blow up while wiring
    def compute_weekly_attendance(app_root: Path) -> dict:
        return {"attendance": {"weeks": [
            {"label": "This Week", "count": 0, "current": True},
            {"label": "Last Week", "count": 0},
            {"label": "2 Weeks Ago", "count": 0},
        ]}}

reports_bp = Blueprint(
    "figurella_reports",
    __name__,
    url_prefix="/figurella-reports",
    template_folder="../templates",
)

# ---------- Global safety net so PERF_DATA is never undefined ----------
@reports_bp.app_context_processor
def _inject_perf_default():
    # If a template forgets to pass PERF_DATA, this makes it an empty dict instead of Undefined.
    return {"PERF_DATA": {}}

# ---------- Small helpers ----------
def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _compute_window(from_iso: str | None, to_iso: str | None, last_days_default: int) -> tuple[datetime, datetime]:
    """
    Accept ?from=&to=&days=. If not provided, use last_days_default. ISO may include 'Z'.
    """
    now = _utc_now()
    if from_iso and to_iso:
        frm = datetime.fromisoformat(from_iso.replace("Z", "+00:00"))
        to  = datetime.fromisoformat(to_iso.replace("Z", "+00:00"))
        if frm.tzinfo is None: frm = frm.replace(tzinfo=timezone.utc)
        if to.tzinfo  is None: to  = to.replace(tzinfo=timezone.utc)
        if frm > to:
            frm, to = to, frm
        return frm, to

    try:
        days = int(request.values.get("days")) if request.values.get("days") else last_days_default
    except Exception:
        days = last_days_default
    return now - timedelta(days=days), now

def _data_dir() -> Path:
    base = Path(current_app.instance_path) / "figurella_reports"
    base.mkdir(parents=True, exist_ok=True)
    return base

def _write_csv_from_xlsx(xlsx_path: Path, csv_path: Path) -> None:
    try:
        df = pd.read_excel(xlsx_path)  # first sheet
        df.to_csv(csv_path, index=False)
    except Exception:
        pass

def _place_into_instance(stem: str, src_xlsx: Path) -> None:
    base = _data_dir()
    dst_xlsx = base / f"{stem}.xlsx"
    dst_csv  = base / f"{stem}.csv"
    shutil.copy2(src_xlsx, dst_xlsx)
    _write_csv_from_xlsx(dst_xlsx, dst_csv)

def _app_root() -> Path:
    # routes.py is at app/figurella_reports/ → up two levels = app/
    return Path(__file__).resolve().parents[2]

# ---------- Home ----------
@reports_bp.get("/")
@reports_bp.get("/reports/home")
def reports_home():
    base = _data_dir()
    files = {
        "customers": {"csv": base / "customers.csv", "xlsx": base / "customers.xlsx"},
        "payments":  {"csv": base / "payments.csv",  "xlsx": base / "payments.xlsx"},
        "agenda":    {"csv": base / "agenda.csv",    "xlsx": base / "agenda.xlsx"},
        "contracts": {"csv": base / "contracts.csv", "xlsx": base / "contracts.xlsx"},
        "notes":     {"csv": base / "notes.csv",     "xlsx": base / "notes.xlsx"},
    }

    def info(p: Path):
        if not p.exists():
            return {"path": str(p), "mtime": None, "rows": None, "size": None}
        rows = None
        if p.suffix.lower() == ".csv":
            try:
                with p.open("r", encoding="utf-8", errors="ignore") as f:
                    rows = max(0, sum(1 for _ in f) - 1)
            except Exception:
                rows = None
        mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        size = p.stat().st_size
        return {"path": str(p), "mtime": mtime, "rows": rows, "size": size}

    ctx = {"files": {k: {"csv": info(d["csv"]), "xlsx": info(d["xlsx"])} for k, d in files.items()}}
    return render_template("figurella_reports/reports_home.html", **ctx)

# ---------- Location Performance PAGE (embeds PERF_DATA) ----------
@reports_bp.get("/reports/performance")
def reports_performance():
    app_root = _app_root()
    instance_dir = Path(current_app.instance_path)

    # 1) New clients (this + last month)
    nc_summary = compute_clients_monthly_summary(app_root)  # {"new_clients": {...}}

    # 2) Weekly attendance
    att = compute_weekly_attendance(app_root)               # {"attendance": {"weeks": [...]}}

    # 3) Active clients (unique customerId with OK appointments in current month)
    try:
        active = compute_active_clients_this_month(app_root, instance_dir)  # new two-arg version
    except TypeError:
        active = compute_active_clients_this_month(app_root)                # fallback to old one-arg

    PERF_DATA = {
        "active_clients": active,
        "new_clients": nc_summary.get("new_clients", {
            "this_month": {"total": 0, "ok": 0, "try": 0},
            "last_month": {"total": 0, "ok": 0, "try": 0},
        }),
        "attendance": att.get("attendance", {"weeks": []}),
    }

    # 👇 pass PERF_DATA so the template can serialize it with tojson
    return render_template("figurella_reports/performance.html", PERF_DATA=PERF_DATA)

# ---------- Location Performance JSON (debug/fallback) ----------
@reports_bp.get("/_perf/data")
def perf_data_json():
    app_root = _app_root()
    instance_dir = Path(current_app.instance_path)

    nc_summary = compute_clients_monthly_summary(app_root)
    att = compute_weekly_attendance(app_root)

    try:
        active = compute_active_clients_this_month(app_root, instance_dir)
    except TypeError:
        active = compute_active_clients_this_month(app_root)

    PERF_DATA = {
        "active_clients": active,
        "new_clients": nc_summary.get("new_clients", {
            "this_month": {"total": 0, "ok": 0, "try": 0},
            "last_month": {"total": 0, "ok": 0, "try": 0},
        }),
        "attendance": att.get("attendance", {"weeks": []}),
    }
    return jsonify({"ok": True, "data": PERF_DATA})

# ---------- API → FILE sync (no DB) ----------
@reports_bp.post("/_sync/customers/file")
def sync_customers_file():
    frm, to = _compute_window(request.values.get("from"), request.values.get("to"), last_days_default=90)
    customers_mode = (request.values.get("customers_mode") or "windowed").lower()
    if customers_mode not in {"windowed", "all"}:
        customers_mode = "windowed"

    rows = fetch_customers(frm, to, mode=customers_mode)

    xlsx_path = Path.cwd() / "customers.xlsx"
    save_customers_excel(rows, str(xlsx_path))
    update_customer_history()
    _place_into_instance("customers", xlsx_path)

    return jsonify({
        "ok": True,
        "window": [str(frm), str(to)],
        "saved": "customers.[csv|xlsx]",
        "customers_mode": customers_mode,
        "count": len(rows),
    }), 200

@reports_bp.post("/_sync/payments/file")
def sync_payments_file():
    frm, to = _compute_window(request.values.get("from"), request.values.get("to"), last_days_default=60)

    rows = fetch_payments(frm, to)
    xlsx_path = Path.cwd() / "payments.xlsx"
    save_payments_excel(rows, str(xlsx_path))
    update_payment_history()
    _place_into_instance("payments", xlsx_path)

    return jsonify({"ok": True, "window": [str(frm), str(to)], "saved": "payments.[csv|xlsx]"}), 200

@reports_bp.post("/_sync/agenda/file")
def sync_agenda_file():
    frm, to = _compute_window(request.values.get("from"), request.values.get("to"), last_days_default=31)

    rows = fetch_agenda(frm, to)
    xlsx_path = Path.cwd() / "agenda.xlsx"
    save_agenda_excel(rows, str(xlsx_path))
    update_agenda_history()
    _place_into_instance("agenda", xlsx_path)

    return jsonify({"ok": True, "window": [str(frm), str(to)], "saved": "agenda.[csv|xlsx]"}), 200

# Contracts → merged workbook + history
@reports_bp.post("/_sync/contracts/file")
def sync_contracts_file():
    frm, to = _compute_window(request.values.get("from"), request.values.get("to"), last_days_default=90)

    # Produce ONE workbook: contracts.xlsx (sheet 'contracts' merged + sheet 'sales')
    sync_contracts_to_excel(frm, to)

    # Update contracts history from the merged 'contracts' sheet
    update_contracts_history()

    # Publish to instance folder (CSV uses first sheet)
    _place_into_instance("contracts", Path.cwd() / "contracts.xlsx")

    return jsonify({"ok": True, "window": [str(frm), str(to)], "saved": "contracts.[csv|xlsx]"}), 200

# Notes → today Excel + history
@reports_bp.post("/_sync/notes/file")
def sync_notes_file():
    frm, to = _compute_window(request.values.get("from"), request.values.get("to"), last_days_default=31)

    run_notes_sync(frm=frm, to=to)

    _place_into_instance("notes", Path.cwd() / "customer_notes.xlsx")

    return jsonify({"ok": True, "window": [str(frm), str(to)], "saved": "notes.[csv|xlsx]"}), 200

# ---------- FILE views ----------
@reports_bp.get("/reports/<name>/history/view")
def history_view(name: str):
    name = name.lower()
    if name not in {"customers", "payments", "agenda", "contracts", "notes"}:
        abort(404)
    csv_path = _data_dir() / f"{name}.csv"
    if not csv_path.exists():
        return render_template(
            "figurella_reports/history_view.html",
            name=name,
            columns=[],
            rows=[],
            missing=True,
        )
    df = pd.read_csv(csv_path)
    return render_template(
        "figurella_reports/history_view.html",
        name=name,
        columns=list(df.columns),
        rows=df.to_dict(orient="records"),
        missing=False,
    )



# ---------- Download ----------
@reports_bp.get("/download/<name>.<ext>")
def download_file(name: str, ext: str):
    name, ext = name.lower(), ext.lower()
    if name not in {"customers", "payments", "agenda", "contracts", "notes"} or ext not in {"csv", "xlsx"}:
        abort(404)
    path = _data_dir() / f"{name}.{ext}"
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name)

# ---------- Run from page buttons (CLI-like pipeline) ----------
@reports_bp.post("/_run/cli")
def run_cli_from_web():
    mode = (request.args.get("mode") or "all").lower()
    frm, to = _compute_window(request.args.get("from"), request.args.get("to"), last_days_default=31)

    # NEW: pick up customers_mode from the UI checkbox
    customers_mode = (request.args.get("customers_mode") or "windowed").lower()
    if customers_mode not in {"windowed", "all"}:
        customers_mode = "windowed"

    base = _data_dir()

    # Helper to publish xlsx to instance + csv
    def _publish(stem: str, xlsx_path: Path):
        dst_xlsx = base / f"{stem}.xlsx"
        dst_csv  = base / f"{stem}.csv"
        shutil.copy2(xlsx_path, dst_xlsx)
        try:
            df = pd.read_excel(dst_xlsx)  # first sheet (for contracts = merged)
            df.to_csv(dst_csv, index=False)
        except Exception:
            pass

    try:
        ran = []

        if mode in ("customers", "all"):
            rows = fetch_customers(frm, to, mode=customers_mode)
            xlsx = Path.cwd() / "customers.xlsx"
            save_customers_excel(rows, str(xlsx))
            update_customer_history()
            _publish("customers", xlsx)
            ran.append(f"customers[{customers_mode}]")

        if mode in ("payments", "all"):
            rows = fetch_payments(frm, to)
            xlsx = Path.cwd() / "payments.xlsx"
            save_payments_excel(rows, str(xlsx))
            update_payment_history()
            _publish("payments", xlsx)
            ran.append("payments")

        if mode in ("agenda", "all"):
            rows = fetch_agenda(frm, to)
            xlsx = Path.cwd() / "agenda.xlsx"
            save_agenda_excel(rows, str(xlsx))
            update_agenda_history()
            _publish("agenda", xlsx)
            ran.append("agenda")

        if mode in ("contracts", "all"):
            sync_contracts_to_excel(frm, to)    # emits contracts.xlsx (merged + sales sheets)
            update_contracts_history()          # appends to history
            _publish("contracts", Path.cwd() / "contracts.xlsx")
            ran.append("contracts")

        if mode in ("notes", "all"):
            run_notes_sync(frm=frm, to=to)
            _publish("notes", Path.cwd() / "customer_notes.xlsx")
            ran.append("notes")

        if not ran:
            return jsonify({"ok": False, "error": f"Unknown mode '{mode}'"}), 400

        return jsonify({"ok": True, "message": f"Ran: {', '.join(ran)}", "refresh": True}), 200

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
