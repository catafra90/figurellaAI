print("✅ daily_checkin.routes.py loaded")

from flask import Blueprint, request, redirect, render_template, flash
import pandas as pd
from datetime import datetime
import os

from app.common.webhook import send_to_google_chat
from app.common.utils import save_report_to_excel

daily_checkin_bp = Blueprint('daily_checkin', __name__)

@daily_checkin_bp.route('/wizard', endpoint='combined_report_wizard')
def combined_report_wizard():
    print("✅ combined_report_wizard route hit")
    return render_template('daily_checkin/daily_checkin.html', active_page='report')

@daily_checkin_bp.route('/report')
def report_home():
    return render_template('daily_checkin/daily_checkin.html', active_page='report')

@daily_checkin_bp.route('/submit', methods=['POST'])
def submit_report():
    submission_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Extract uniquely named form fields
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

    # Format DataFrames and add submission date
    df_sales = pd.DataFrame(sales, columns=['Client Name', 'Package Sold', 'Revenue']).dropna(how='all')
    if not df_sales.empty:
        df_sales.insert(0, 'Date', submission_date)

    df_leads = pd.DataFrame(leads, columns=['Name', 'Scheduled Date', 'Lead Source']).dropna(how='all')
    if not df_leads.empty:
        df_leads.insert(0, 'Date', submission_date)

    df_consults = pd.DataFrame(consultations, columns=['Client Name', 'Outcome', 'Lead Source']).dropna(how='all')
    if not df_consults.empty:
        df_consults.insert(0, 'Date', submission_date)

    df_opps = pd.DataFrame(opportunities, columns=['Name', 'Provider', 'Description']).dropna(how='all')
    if not df_opps.empty:
        df_opps.insert(0, 'Date', submission_date)

    df_attendance = pd.DataFrame(attendance, columns=['Attended', 'No-Show']).dropna(how='all')
    if not df_attendance.empty:
        df_attendance.insert(0, 'Date', submission_date)

    print("✅ SALES:\n", df_sales)
    print("✅ LEADS:\n", df_leads)
    print("✅ CONSULTATIONS:\n", df_consults)
    print("✅ OPPORTUNITIES:\n", df_opps)
    print("✅ ATTENDANCE:\n", df_attendance)

    # Save to Excel if there’s any data
    save_report_to_excel({
        'Sales': df_sales,
        'Leads': df_leads,
        'Consultations': df_consults,
        'Opportunities': df_opps,
        'Attendance': df_attendance
    })

    try:
        send_to_google_chat("✅ Daily Check-in submitted and saved to Excel.")
    except Exception as e:
        print("❌ Google Chat Error:", str(e))

    flash('✅ Report submitted successfully!', 'success')
    return redirect('/')

@daily_checkin_bp.route('/report/history', endpoint='report_history')
def report_history():
    reports_dir = os.path.join('app', 'static', 'reports')
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)

    files = sorted(
        [f for f in os.listdir(reports_dir) if f.endswith('.xlsx')],
        reverse=True
    )
    return render_template('daily_checkin/report_history.html', files=files, active_page='report')
