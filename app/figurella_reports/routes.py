import os
import json
import pandas as pd
from flask import (
    Blueprint, render_template, send_file,
    redirect, url_for, flash, current_app
)
from datetime import datetime
from app.common.cleaners import drop_unwanted_rows
from app.common.utils import save_report
from build_history import main as build_all_history
from app.models import Report, ReportHistory

# Import scraper functions
from app.common.scrape_agenda import main as scrape_agenda
from app.common.scrape_contracts import main as scrape_contracts
from app.common.scrape_customer_acquisitions import main as scrape_customer_acquisition
from app.common.scrape_ibf import main as scrape_ibf
from app.common.scrape_last_session import main as scrape_last_session
from app.common.scrape_payments_done import main as scrape_payments_done
from app.common.scrape_payments_due import main as scrape_payments_due
from app.common.scrape_pip import main as scrape_pip
from app.common.scrape_subscriptions import main as scrape_subscriptions

reports_bp = Blueprint(
    'reports_bp', __name__,
    url_prefix='/figurella-reports',
    template_folder='templates/figurella_reports'
)

# Dashboard cards
REPORT_CARDS = [
    {"key": "agenda",               "label": "Agenda",               "icon": "bi-calendar"},
    {"key": "contracts",            "label": "Contracts",            "icon": "bi-pen"},
    {"key": "customer_acquisition", "label": "Customer Acquisition", "icon": "bi-people"},
    {"key": "ibf",                  "label": "IBF",                  "icon": "bi-percent"},
    {"key": "last_session",         "label": "Last Session",         "icon": "bi-calendar-check"},
    {"key": "payments_done",        "label": "Payments Done",        "icon": "bi-check-circle"},
    {"key": "payments_due",         "label": "Payments Due",         "icon": "bi-calendar-day"},
    {"key": "pip",                  "label": "PIP",                  "icon": "bi-bank"},
    {"key": "subscriptions",        "label": "Subscriptions",        "icon": "bi-calendar-event"},
]

# Map labels to scraper functions
SCRAPERS = {
    "Agenda":               {"fn": scrape_agenda,               "key": "agenda"},
    "Contracts":            {"fn": scrape_contracts,            "key": "contracts"},
    "Customer Acquisition": {"fn": scrape_customer_acquisition, "key": "customer_acquisition"},
    "IBF":                  {"fn": scrape_ibf,                  "key": "ibf"},
    "Last Session":         {"fn": scrape_last_session,         "key": "last_session"},
    "Payments Done":        {"fn": scrape_payments_done,        "key": "payments_done"},
    "Payments Due":         {"fn": scrape_payments_due,         "key": "payments_due"},
    "PIP":                  {"fn": scrape_pip,                  "key": "pip"},
    "Subscriptions":        {"fn": scrape_subscriptions,        "key": "subscriptions"},
}

# Legacy history filenames
HISTORY_FILES = {c['label']: f"history_{c['key']}.xlsx" for c in REPORT_CARDS}

@reports_bp.app_context_processor
def inject_now():
    return {'now': datetime.utcnow}

@reports_bp.route('/reports')
def reports_home():
    return render_template(
        'figurella_reports/reports_home.html',
        cards=REPORT_CARDS
    )

@reports_bp.route('/reports/<report_name>/history/view')
def view_history(report_name):
    key = report_name.lower().replace(' ', '_')
    rpt = Report.query.filter_by(key=key).first()

    # Gather raw records
    if rpt and isinstance(rpt.data, list):
        records = rpt.data
    else:
        entries = (
            ReportHistory
            .query
            .filter_by(report_id=rpt.id)
            .order_by(ReportHistory.id.asc())
            .all()
        )
        records = []
        for h in entries:
            raw = h.data
            obj = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(obj, list):
                records.extend(obj)
            else:
                records.append(obj)

    if not records:
        flash(f"No history found for '{report_name}'", 'warning')
        return redirect(url_for('reports_bp.reports_home'))

    # Normalize into DataFrame
    df = pd.json_normalize(records)

    # Drop unwanted columns
    df.drop(columns=['Email', 'Phone'], errors='ignore', inplace=True)
    if '_sheet' in df.columns:
        df.drop(columns=['_sheet'], inplace=True)

    # Clean up blank header rows
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass

    # Report‐specific tweaks
    if report_name == 'IBF':
        df = df.iloc[1:].reset_index(drop=True)
    if report_name == 'Contracts' and 'Name' in df.columns:
        df = df[df['Name'].str.lower() != 'name']

    # 1) Column names
    columns = df.columns.tolist()
    # 2) Row data (fill NaN with empty string)
    data = df.fillna('').values.tolist()

    return render_template(
        'figurella_reports/history_view.html',
        report_name=report_name,
        columns=columns,
        data=data
    )



@reports_bp.route('/reports/<report_name>/history/download')
def download_history(report_name):
    hist_file = HISTORY_FILES.get(report_name)
    if not hist_file:
        flash(f"Unknown report: {report_name}", 'danger')
        return redirect(url_for('reports_bp.reports_home'))
    project_root = os.path.abspath(os.path.join(current_app.root_path, os.pardir))
    full_path = os.path.join(project_root, hist_file)
    if not os.path.exists(full_path):
        flash(f"No history file for '{report_name}'", 'danger')
        return redirect(url_for('reports_bp.reports_home'))
    return send_file(full_path, as_attachment=True,
                     download_name=f"{report_name.replace(' ', '_')}_history.xlsx")

@reports_bp.route('/reports/refresh_all', methods=['POST'])
def refresh_all_reports():
    errors = []
    total_rows = 0

    for card in REPORT_CARDS:
        label = card['label']
        key   = card['key']
        scraper_fn = SCRAPERS[label]['fn']

        # 1) Run the scraper
        try:
            result = scraper_fn()
        except Exception as e:
            msg = f"{label!r} scraper failed: {e}"
            current_app.logger.error(msg)
            errors.append(msg)
            continue

        # 2) Normalize into a dict of DataFrames
        if result is None:
            msg = f"{label!r} scraper returned None, skipping."
            current_app.logger.warning(msg)
            errors.append(msg)
            continue
        if isinstance(result, pd.DataFrame):
            section_data = { label: result }
        elif isinstance(result, dict):
            section_data = result
        else:
            msg = f"{label!r} returned unexpected type {type(result)}"
            current_app.logger.error(msg)
            errors.append(msg)
            continue

        # 3) Persist
        try:
            save_report(section_data, key)
            rows = sum(len(df) for df in section_data.values())
            total_rows += rows
            current_app.logger.debug(f"[DEBUG] scraped & persisted {rows} rows for {label!r}")
        except Exception as e:
            msg = f"{label!r} save_report error: {e}"
            current_app.logger.error(msg)
            errors.append(msg)

    # 4) Rebuild your merged history
    try:
        build_all_history()
    except Exception as e:
        msg = f"History rebuild failed: {e}"
        current_app.logger.error(msg)
        errors.append(msg)

    # 5) Flash outcome
    if errors:
        flash("Some operations failed:\n" + "\n".join(errors), 'warning')
    else:
        flash(f"All reports scraped + saved! Total rows: {total_rows}", 'success')

    return redirect(url_for('reports_bp.reports_home'))
