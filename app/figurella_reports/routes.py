# app/figurella_reports/routes.py

import os
import pandas as pd
from flask import (
    Blueprint, render_template, send_file,
    redirect, url_for, flash, current_app
)
from datetime import datetime
from app.common.cleaners import drop_unwanted_rows

# entry‐points for your scrapers
from app.common.scrape_agenda import main as scrape_agenda
from app.common.scrape_contracts import main as scrape_contracts
from app.common.scrape_customer_acquisitions import main as scrape_customer_acquisition
from app.common.scrape_ibf import main as scrape_ibf
from app.common.scrape_last_session import main as scrape_last_session
from app.common.scrape_payments_done import main as scrape_payments_done
from app.common.scrape_payments_due import main as scrape_payments_due
from app.common.scrape_pip import main as scrape_pip
from app.common.scrape_subscriptions import main as scrape_subscriptions

# entry‐point for your history builder
from build_history import main as build_all_history

reports_bp = Blueprint(
    'reports_bp', __name__,
    url_prefix='/figurella-reports',
    template_folder='templates'
)

REPORTS = {
    "Agenda":               "history_agenda.xlsx",
    "Contracts":            "history_contracts.xlsx",
    "Customer Acquisition": "history_customer_acquisition.xlsx",
    "IBF":                  "history_ibf.xlsx",
    "Last Session":         "history_last_session.xlsx",
    "Payments Done":        "history_payments_done.xlsx",
    "Payments Due":         "history_payments_due.xlsx",
    "PIP":                  "history_pip.xlsx",
    "Subscriptions":        "history_subscriptions.xlsx",
}

SCRAPERS = {
    "Agenda":               scrape_agenda,
    "Contracts":            scrape_contracts,
    "Customer Acquisition": scrape_customer_acquisition,
    "IBF":                  scrape_ibf,
    "Last Session":         scrape_last_session,
    "Payments Done":        scrape_payments_done,
    "Payments Due":         scrape_payments_due,
    "PIP":                  scrape_pip,
    "Subscriptions":        scrape_subscriptions,
}

@reports_bp.app_context_processor
def inject_now():
    return {'now': datetime.utcnow}

@reports_bp.route("/reports")
def reports_home():
    return render_template(
        "figurella_reports/reports_home.html",
        reports=REPORTS
    )

@reports_bp.route("/reports/<report_name>/history/view")
def view_history(report_name):
    hist_file = REPORTS.get(report_name)
    if not hist_file:
        flash(f"Unknown report: {report_name}", "danger")
        return redirect(url_for('reports_bp.reports_home'))

    # Build absolute path to the .xlsx
    project_root = os.path.abspath(os.path.join(current_app.root_path, os.pardir))
    full_path    = os.path.join(project_root, hist_file)
    if not os.path.exists(full_path):
        flash(f"No history file for '{report_name}'.", "danger")
        return redirect(url_for('reports_bp.reports_home'))

    # 1) Load Excel into DataFrame
    try:
        df = pd.read_excel(full_path)
    except Exception as e:
        flash(f"Error reading history: {e}", "danger")
        return redirect(url_for('reports_bp.reports_home'))

    # 2) Drop contact columns globally
    df = df.drop(columns=["Email", "Phone"], errors='ignore')

    # 3) Shared cleanup (e.g. stray “Busy” rows)
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass

    # 4) IBF‐specific: drop the first junk column and the very first row
    if report_name == "IBF":
        # the first column ('0') is just noise, drop it
        df = df.drop(df.columns[0], axis=1)
        # the top row is an exception message, drop it too
        df = df.iloc[1:].reset_index(drop=True)

    # 5) Contracts‐specific: drop any repeated header rows
    #    i.e. where the “Name” column literally reads “Name”
    if report_name == "Contracts" and "Name" in df.columns:
        df = df[df["Name"].astype(str).str.lower() != "name"].reset_index(drop=True)

    # 6) Render exactly what’s in the DataFrame
    table_html = df.to_html(
        classes="min-w-full table-auto",
        table_id="history-table",
        index=False,
        border=0
    )

    return render_template(
        "figurella_reports/history_view.html",
        report_name=report_name,
        table_html=table_html
    )

@reports_bp.route("/reports/<report_name>/history/download")
def download_history(report_name):
    hist_file = REPORTS.get(report_name)
    if not hist_file:
        flash(f"Unknown report: {report_name}", "danger")
        return redirect(url_for('reports_bp.reports_home'))

    project_root = os.path.abspath(os.path.join(current_app.root_path, os.pardir))
    full_path    = os.path.join(project_root, hist_file)
    if not os.path.exists(full_path):
        flash(f"No history file for '{report_name}'.", "danger")
        return redirect(url_for('reports_bp.reports_home'))

    return send_file(
        full_path,
        as_attachment=True,
        download_name=f"{report_name.replace(' ', '_')}_history.xlsx"
    )

@reports_bp.route("/reports/refresh_all", methods=["POST"])
def refresh_all_reports():
    errors = []
    # 1) Re‐run each scraper
    for name, scraper in SCRAPERS.items():
        try:
            scraper()
        except Exception as e:
            errors.append(f"{name} scraper failed: {e}")
    # 2) Rebuild every history_*.xlsx
    try:
        build_all_history()
    except Exception as e:
        errors.append(f"History rebuild failed: {e}")

    if errors:
        flash("Some operations failed:\n" + "\n".join(errors), "warning")
    else:
        flash("All reports scraped and histories rebuilt successfully!", "success")

    return redirect(url_for('reports_bp.reports_home'))
