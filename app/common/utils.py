# app/common/utils.py
import os
import pandas as pd
import numpy as np
import datetime as _dt
import decimal as _dec
from typing import Any, Dict

from flask import flash, current_app
from app import db
from app.models import Report, ReportHistory


# ───────────────────────── JSON SANITIZER ─────────────────────────

def _to_jsonable(obj: Any) -> Any:
    """
    Recursively convert Pandas/NumPy/Decimal/Datetime to JSON-safe Python types.
    """
    # pandas NA
    try:
        if pd.isna(obj):  # catches NaN/NaT
            return None
    except Exception:
        pass

    # NumPy scalars
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        val = float(obj)
        if np.isnan(val) or np.isinf(val):
            return None
        return val
    if isinstance(obj, (np.bool_,)):
        return bool(obj)

    # Pandas Timestamp
    if isinstance(obj, pd.Timestamp):
        if obj.tzinfo is not None:
            # keep offset if present
            return obj.isoformat()
        # if midnight -> use date-only string (shorter / friendlier)
        if obj.hour == 0 and obj.minute == 0 and obj.second == 0 and obj.microsecond == 0:
            return obj.date().isoformat()
        return obj.isoformat()

    # Python datetime/date/time
    if isinstance(obj, _dt.datetime):
        return obj.isoformat() if obj.tzinfo else obj.replace(tzinfo=None).isoformat()
    if isinstance(obj, _dt.date):
        return obj.isoformat()
    if isinstance(obj, _dt.time):
        return obj.isoformat()

    # Decimals
    if isinstance(obj, _dec.Decimal):
        return float(obj)

    # Containers
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]

    return obj


def _df_to_records(df: pd.DataFrame):
    """DataFrame -> list of JSON-safe dicts."""
    if df is None or df.empty:
        return []
    df2 = df.copy()

    # Normalize by dtype
    for col, dtype in df2.dtypes.items():
        if pd.api.types.is_datetime64_any_dtype(dtype):
            df2[col] = df2[col].map(_to_jsonable)
        elif pd.api.types.is_bool_dtype(dtype):
            df2[col] = df2[col].astype(bool)
        elif pd.api.types.is_numeric_dtype(dtype):
            df2[col] = df2[col].map(_to_jsonable)
        else:
            # 🔧 IMPORTANT: sanitize object/mixed columns too (can contain pd.Timestamp)
            df2[col] = df2[col].map(_to_jsonable)

    # Replace NaN with None after mapping
    df2 = df2.where(pd.notnull(df2), None)

    recs = df2.to_dict(orient="records")
    return [_to_jsonable(r) for r in recs]


# ───────────────────────── EXCEL EXPORT ─────────────────────────

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


# ───────────────────────── MAIN ENTRY ─────────────────────────

def persist_report(section_data: Dict[str, pd.DataFrame],
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

    NOTE: All payloads are sanitized to JSON-safe Python objects.
    """
    # normalize input
    if section_data is None:
        section_data = {}
    # allow callers to pass a single DataFrame
    if isinstance(section_data, pd.DataFrame):
        section_data = {report_key: section_data}

    # Build JSON-safe payloads up-front
    json_sections: Dict[str, list] = {}
    for sheet_name, df in section_data.items():
        if isinstance(df, pd.DataFrame):
            json_sections[sheet_name] = _df_to_records(df)
        else:
            # already a list/dict? sanitize recursively
            json_sections[sheet_name] = _to_jsonable(df)

    # 1) Ensure Report exists
    report = Report.query.filter_by(key=report_key).first()
    if not report:
        # IMPORTANT: store Python object, not JSON string
        report = Report(key=report_key, data=[])
        db.session.add(report)
        db.session.commit()

    # 2) Archive old snapshot
    if to_db and report.data is not None:
        try:
            prev_hist = ReportHistory(report_id=report.id, data=_to_jsonable(report.data))
            db.session.add(prev_hist)
        except Exception as e:
            current_app.logger.error(f"Failed to archive snapshot for '{report_key}': {e}")

    # 3) Add new history entries and upsert latest
    if to_db:
        new_rows = []
        for sheet_name, records in json_sections.items():
            # records expected to be a list of dicts
            if not records:
                continue
            for rec in records:
                entry = dict(rec)
                entry["_sheet"] = sheet_name
                new_rows.append(entry)
                try:
                    hist = ReportHistory(report_id=report.id, data=_to_jsonable(entry))
                    db.session.add(hist)
                except Exception as e:
                    current_app.logger.error(f"Failed to archive row for '{report_key}': {e}")

        # Store the flattened records (without _sheet) in Report.data,
        # OR if you prefer, keep grouped by sheet; here we keep flat for compatibility
        report.data = _to_jsonable([{k: v for k, v in r.items() if k != "_sheet"} for r in new_rows])
        db.session.add(report)
        db.session.commit()
        current_app.logger.debug(f"[persist_report] upserted {len(new_rows)} history rows for '{report_key}'")

    # 4) Excel exports (use original DataFrames)
    if to_static_excel:
        static_dir = os.path.join(current_app.static_folder, "reports")
        _export_excel(section_data, report_key, static_dir)
    if to_download_excel:
        download_dir = os.path.abspath(os.path.join(current_app.root_path, os.pardir, "download"))
        _export_excel(section_data, report_key, download_dir)

    return report


# backwards compatibility wrapper
def save_report(section_data, report_key, *args, **kwargs):
    """Wrapper for persist_report: always returns the passed section_data dict to avoid None returns."""
    try:
        persist_report(section_data, report_key, *args, **kwargs)
    except Exception as e:
        current_app.logger.error(f"Error in save_report for '{report_key}': {e}")
    return section_data
