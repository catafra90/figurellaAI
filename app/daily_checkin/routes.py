# File: app/daily_checkin/routes.py
import os
import pandas as pd
from datetime import datetime
from flask import Blueprint, request, redirect, render_template, flash, current_app, url_for

from app.common.webhook import send_to_google_chat
from app.common.utils import save_report

daily_checkin_bp = Blueprint('daily_checkin', __name__)

# ---------- Pretty text helpers (monospace tables + emojis) ----------
MAX_ROWS_PER_SECTION = 12
COL_WIDTHS = {
    'Client Name': 18, 'Package Sold': 18, 'Revenue': 10,
    'Name': 18, 'Scheduled Date': 12, 'Lead Source': 16,
    'Outcome': 14, 'Provider': 16, 'Description': 28,
    'Attended': 10, 'No-Show': 10,
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
    if 'Revenue' in data.columns:
        data['Revenue'] = data['Revenue'].map(_money_to_text)

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
    if (df := sections.get('Sales')) is not None and not df.empty:
        total = 0.0
        for v in df.get('Revenue', []):
            try:
                total += float(str(v).replace(",", "").replace("$", "").strip())
            except Exception:
                pass
        parts.append(f"💸 Sales: {len(df)} (Total {_money_to_text(total)})")
    if (df := sections.get('Leads')) is not None and not df.empty:
        parts.append(f"🧲 Leads: {len(df)}")
    if (df := sections.get('Consultations')) is not None and not df.empty:
        parts.append(f"🗓️ Consultations: {len(df)}")
    if (df := sections.get('Opportunities')) is not None and not df.empty:
        parts.append(f"🌟 Opportunities: {len(df)}")
    if (df := sections.get('Attendance')) is not None and not df.empty:
        att = df.get('Attended', pd.Series([], dtype=str)).astype(str).str.strip()
        nos = df.get('No-Show', pd.Series([], dtype=str)).astype(str).str.strip()
        parts.append(f"👥 Attendance: {len(df)} (✔️ {(att!='').sum()} | ❌ {(nos!='').sum()})")
    return " • ".join(parts) if parts else "No data"

def _build_plain_text_message(submission_date, sections, history_url: str | None):
    lines = []
    lines.append(f"✅ *Daily Check-in Submitted*  \n_{submission_date}_")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"*Summary:* {_build_summary(sections)}")

    def add(title, key, cols, emoji):
        df = sections.get(key)
        if df is not None and not df.empty:
            table, _ = _df_to_table(df, cols)
            lines.append(f"\n*{emoji} {title}*")
            lines.append("```\n" + table + "\n```")

    add("Sales", "Sales", ['Client Name','Package Sold','Revenue'], "💸")
    add("Leads", "Leads", ['Name','Scheduled Date','Lead Source'], "🧲")
    add("Consultations", "Consultations", ['Client Name','Outcome','Lead Source'], "🗓️")
    add("Opportunities", "Opportunities", ['Name','Provider','Description'], "🌟")
    add("Attendance", "Attendance", ['Attended','No-Show'], "👥")

    if history_url:
        lines.append(f"\n📁 *History:* {history_url}")
    return "\n".join(lines)

# ---------- Views ----------

# Optional: base redirect so /daily-check-in/ goes to the launcher/wizard
@daily_checkin_bp.route('/')
def index():
    return redirect(url_for('daily_checkin.combined_report_wizard'))

@daily_checkin_bp.route('/wizard', endpoint='combined_report_wizard')
def combined_report_wizard():
    # This template contains the app launcher (tiles) and the Daily Checks wizard.
    return render_template('daily_checkin/daily_checkin.html', active_page='report')

@daily_checkin_bp.route('/report')
def report_home():
    return redirect(url_for('daily_checkin.combined_report_wizard'))

@daily_checkin_bp.route('/submit', methods=['POST'])
def submit_report():
    submission_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    sales = zip(
        request.form.getlist('client_name[]'),
        request.form.getlist('package_sold[]'),
        request.form.getlist('revenue[]')
    )
    leads = zip(
        request.form.getlist('lead_name[]'),
        request.form.getlist('lead_date[]'),
        request.form.getlist('lead_source[]')
    )
    consultations = zip(
        request.form.getlist('consult_client[]'),
        request.form.getlist('consult_outcome[]'),
        request.form.getlist('consult_source[]')
    )
    opportunities = zip(
        request.form.getlist('opp_name[]'),
        request.form.getlist('opp_provider[]'),
        request.form.getlist('opp_description[]')
    )
    attendance = zip(
        request.form.getlist('att_attended[]'),
        request.form.getlist('att_no_show[]')
    )

    df_sales = pd.DataFrame(sales, columns=['Client Name','Package Sold','Revenue']).dropna(how='all')
    if not df_sales.empty: df_sales.insert(0, 'Date', submission_date)

    df_leads = pd.DataFrame(leads, columns=['Name','Scheduled Date','Lead Source']).dropna(how='all')
    if not df_leads.empty: df_leads.insert(0, 'Date', submission_date)

    df_consults = pd.DataFrame(consultations, columns=['Client Name','Outcome','Lead Source']).dropna(how='all')
    if not df_consults.empty: df_consults.insert(0, 'Date', submission_date)

    df_opps = pd.DataFrame(opportunities, columns=['Name','Provider','Description']).dropna(how='all')
    if not df_opps.empty: df_opps.insert(0, 'Date', submission_date)

    df_attendance = pd.DataFrame(attendance, columns=['Attended','No-Show']).dropna(how='all')
    if not df_attendance.empty: df_attendance.insert(0, 'Date', submission_date)

    sections = {}
    if not df_sales.empty: sections['Sales'] = df_sales
    if not df_leads.empty: sections['Leads'] = df_leads
    if not df_consults.empty: sections['Consultations'] = df_consults
    if not df_opps.empty: sections['Opportunities'] = df_opps
    if not df_attendance.empty: sections['Attendance'] = df_attendance

    if sections:
        save_report(sections, 'daily_checkins')
        flash('✅ Report submitted successfully!', 'success')

        history_url = None
        try:
            history_url = url_for('daily_checkin.report_history', _external=True)
        except Exception:
            pass

        # Always send a plain-text message so it renders in Chat
        try:
            text_msg = _build_plain_text_message(submission_date, sections, history_url)
            send_to_google_chat(text_msg)
        except Exception as e:
            current_app.logger.error(f"Google Chat notification failed: {e}")
    else:
        flash('⚠️ No data entered — nothing to save.', 'warning')

    return redirect(url_for('daily_checkin.combined_report_wizard'))

@daily_checkin_bp.route('/report/history', endpoint='report_history')
def report_history():
    download_dir = os.path.join(current_app.root_path, 'download')
    os.makedirs(download_dir, exist_ok=True)
    files = sorted([f for f in os.listdir(download_dir) if f.endswith('.xlsx')], reverse=True)
    return render_template('daily_checkin/report_history.html', files=files, active_page='report')

# ---------- New: Monthly Planning ----------
@daily_checkin_bp.route('/monthly-planning', methods=['GET'])
def monthly_planning():
    """
    Simple client-side monthly planner.
    The template handles autosave to localStorage, CSV export, and printing.
    """
    return render_template('daily_checkin/monthly_planning.html', active_page='report')
