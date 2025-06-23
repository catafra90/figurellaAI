print("✅ daily_report.routes.py loaded")

from flask import Blueprint, request, redirect, render_template, flash
import pandas as pd
import os
from datetime import datetime
from app.common.webhook import send_to_google_chat
from app.common.utils import save_report_to_excel  # ✅ Import updated utility

daily_report_bp = Blueprint('daily_report', __name__)

@daily_report_bp.route('/wizard', endpoint='combined_report_wizard')
def combined_report_wizard():
    return render_template('daily_report/daily_report.html', active_page='report')


@daily_report_bp.route('/report')
def report_home():
    return render_template('daily_report/daily_report.html', active_page='report')


@daily_report_bp.route('/submit', methods=['POST'])
def submit_report():
    submission_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Extract data from form
    sales = zip(
        request.form.getlist('sales_client[]'),
        request.form.getlist('sales_package[]'),
        request.form.getlist('sales_revenue[]')
    )
    leads = zip(
        request.form.getlist('leads_name[]'),
        request.form.getlist('leads_date[]'),
        request.form.getlist('leads_source[]')
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
    attendance = {
        'Date': submission_date,
        'Attended': request.form.get('attended', 0),
        'No-Show': request.form.get('no_show', 0)
    }

    # Format data into DataFrames and prepend the Date column
    df_sales = pd.DataFrame(sales, columns=['Client Name', 'Package', 'Revenue'])
    df_sales.insert(0, 'Date', submission_date)

    df_leads = pd.DataFrame(leads, columns=['Name', 'Scheduled Date', 'Lead Source'])
    df_leads.insert(0, 'Date', submission_date)

    df_consults = pd.DataFrame(consultations, columns=['Client Name', 'Outcome', 'Lead Source'])
    df_consults.insert(0, 'Date', submission_date)

    df_opps = pd.DataFrame(opportunities, columns=['Name', 'Provider', 'Description'])
    df_opps.insert(0, 'Date', submission_date)

    df_attendance = pd.DataFrame([attendance])

    # Save to cumulative Excel file using the utility function
    save_report_to_excel({
        'Sales': df_sales,
        'Leads': df_leads,
        'Consultations': df_consults,
        'Opportunities': df_opps,
        'Attendance': df_attendance
    })

    # Google Chat notification
    try:
        send_to_google_chat("✅ Daily Report submitted and saved to Excel.")
    except Exception as e:
        print("❌ Google Chat Error:", str(e))

    flash('Report submitted successfully!', 'success')
    return redirect('/')
