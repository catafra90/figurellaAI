import os
import json
import pandas as pd
import numpy as np

from flask import flash, current_app
from app import db
from app.models import Report, ReportHistory


def _export_excel(section_data: dict[str, pd.DataFrame],
                  report_key: str,
                  directory: str):
    """
    Write each DataFrame in section_data to an .xlsx named {report_key}.xlsx
    under `directory`, appending to any existing sheets.
    """
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{report_key}.xlsx")

    if not section_data:
        current_app.logger.warning(f"_export_excel: no sheets for '{report_key}', skipping export.")
        return

    existing = {}
    if os.path.exists(path):
        try:
            existing = pd.read_excel(path, sheet_name=None)
        except PermissionError:
            flash("❌ Cannot save — please close the Excel file first.", "error")
            current_app.logger.error(f"PermissionError reading {path}")
            return

    try:
        with pd.ExcelWriter(path, engine="openpyxl", mode="w") as writer:
            for sheet_name, new_df in section_data.items():
                cleaned = new_df.replace(r"^\s*$", np.nan, regex=True)
                if "Date" in cleaned.columns:
                    subset = [c for c in cleaned.columns if c != "Date"]
                    filtered = cleaned.dropna(how="all", subset=subset)
                else:
                    filtered = cleaned.dropna(how="all")

                if sheet_name in existing:
                    combined = pd.concat([existing[sheet_name], filtered], ignore_index=True)
                else:
                    combined = filtered

                combined.to_excel(writer, sheet_name=sheet_name, index=False)
    except ValueError as ve:
        if "At least one sheet must be visible" in str(ve):
            current_app.logger.warning(f"_export_excel: skipping '{report_key}' - no visible sheets.")
            return
        current_app.logger.error(f"Error in _export_excel: {ve}")
        flash(f"❌ Error saving Excel '{report_key}': {ve}", "error")
    except Exception as e:
        current_app.logger.error(f"Error in _export_excel: {e}")
        flash(f"❌ Error saving Excel '{report_key}': {e}", "error")


def persist_report(section_data: dict[str, pd.DataFrame],
                   report_key: str,
                   *,
                   to_db: bool = True,
                   to_static_excel: bool = True,
                   to_download_excel: bool = True) -> Report:
    """
    1) Upsert the current snapshot into Report + ReportHistory tables.
    2) Optionally export to Excel in:
         - static/reports/{report_key}.xlsx
         - ../download/{report_key}.xlsx
    Returns the Report model instance.
    """
    # normalize for backward compatibility
    if section_data is None:
        section_data = {}
    if isinstance(section_data, pd.DataFrame):
        section_data = {report_key: section_data}

    # 1) Ensure Report exists
    report = Report.query.filter_by(key=report_key).first()
    if not report:
        report = Report(key=report_key, data=json.dumps([]))
        db.session.add(report)
        db.session.commit()

    # 2) Archive old snapshot
    if to_db and report.data:
        try:
            prev_hist = ReportHistory(report_id=report.id, data=report.data)
            db.session.add(prev_hist)
        except Exception as e:
            current_app.logger.error(f"Failed to archive snapshot for '{report_key}': {e}")

    # 3) Add new history entries
    new_data = []
    if to_db:
        for sheet_name, df in section_data.items():
            if df is None:
                continue
            for rec in df.to_dict(orient='records'):
                entry = {**rec, "_sheet": sheet_name}
                new_data.append(entry)
                try:
                    hist = ReportHistory(report_id=report.id, data=json.dumps(entry))
                    db.session.add(hist)
                except Exception as e:
                    current_app.logger.error(f"Failed to archive row for '{report_key}': {e}")
        report.data = new_data
        db.session.add(report)
        db.session.commit()
        current_app.logger.debug(f"[persist_report] upserted {len(new_data)} history rows for '{report_key}'")

    # 4) Excel exports
    if to_static_excel:
        static_dir = os.path.join(current_app.static_folder, "reports")
        _export_excel(section_data, report_key, static_dir)
    if to_download_excel:
        download_dir = os.path.abspath(os.path.join(current_app.root_path, os.pardir, "download"))
        _export_excel(section_data, report_key, download_dir)

    return report


# backwards compatibility wrapper
from flask import current_app

def save_report(section_data, report_key, *args, **kwargs):
    """Wrapper for persist_report: always returns the passed section_data dict to avoid None returns."""
    try:
        persist_report(section_data, report_key, *args, **kwargs)
    except Exception as e:
        current_app.logger.error(f"Error in save_report for '{report_key}': {e}")
    return section_data
