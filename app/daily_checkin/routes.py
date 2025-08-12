# File: app/daily_checkin/routes.py

import os
import pandas as pd
from datetime import datetime
from flask import Blueprint, request, redirect, render_template, flash, current_app, url_for

from app.common.webhook import send_to_google_chat
from app.common.utils import save_report

# Blueprint for Daily Check‑in routes
# -------------------------------------
daily_checkin_bp = Blueprint('daily_checkin', __name__)

@daily_checkin_bp.route('/wizard', endpoint='combined_report_wizard')
def combined_report_wizard():
    """Show the combined report wizard page."""
    return render_template('daily_checkin/daily_checkin.html', active_page='report')

@daily_checkin_bp.route('/report')
def report_home():
    """Alias for the wizard page."""
    return redirect(url_for('daily_checkin.combined_report_wizard'))

@daily_checkin_bp.route('/submit', methods=['POST'])
def submit_report():
    """Handle form submission, build DataFrames, persist to DB & Excel, notify, and redirect."""
    submission_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Extract form arrays
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

    # Build DataFrames
    df_sales = pd.DataFrame(sales, columns=['Client Name','Package Sold','Revenue']).dropna(how='all')
    if not df_sales.empty:
        df_sales.insert(0, 'Date', submission_date)

    df_leads = pd.DataFrame(leads, columns=['Name','Scheduled Date','Lead Source']).dropna(how='all')
    if not df_leads.empty:
        df_leads.insert(0, 'Date', submission_date)

    df_consults = pd.DataFrame(consultations, columns=['Client Name','Outcome','Lead Source']).dropna(how='all')
    if not df_consults.empty:
        df_consults.insert(0, 'Date', submission_date)

    df_opps = pd.DataFrame(opportunities, columns=['Name','Provider','Description']).dropna(how='all')
    if not df_opps.empty:
        df_opps.insert(0, 'Date', submission_date)

    df_attendance = pd.DataFrame(attendance, columns=['Attended','No-Show']).dropna(how='all')
    if not df_attendance.empty:
        df_attendance.insert(0, 'Date', submission_date)

    # Collect sections to save
    sections = {}
    if not df_sales.empty:
        sections['Sales'] = df_sales
    if not df_leads.empty:
        sections['Leads'] = df_leads
    if not df_consults.empty:
        sections['Consultations'] = df_consults
    if not df_opps.empty:
        sections['Opportunities'] = df_opps
    if not df_attendance.empty:
        sections['Attendance'] = df_attendance

    if sections:
        # Persist both to DB and to Excel
        save_report(sections, 'daily_checkins')
        flash('✅ Report submitted successfully!', 'success')
        try:
            send_to_google_chat('✅ Daily Check‑in submitted and saved.')
        except Exception as e:
            current_app.logger.error(f"Google Chat notification failed: {e}")
    else:
        flash('⚠️ No data entered — nothing to save.', 'warning')

    return redirect(url_for('daily_checkin.combined_report_wizard'))

@daily_checkin_bp.route('/report/history', endpoint='report_history')
def report_history():
    """List available Excel history files for download."""
    download_dir = os.path.join(current_app.root_path, 'download')
    os.makedirs(download_dir, exist_ok=True)

    files = sorted(
        [f for f in os.listdir(download_dir) if f.endswith('.xlsx')],
        reverse=True
    )
    return render_template(
        'daily_checkin/report_history.html',
        files=files,
        active_page='report'
    )
