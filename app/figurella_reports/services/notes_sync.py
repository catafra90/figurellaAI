# app/figurella_reports/services/notes_sync.py
from __future__ import annotations
import os
import pandas as pd

from .api_client import fetch_customer_notes_range
from .window_utils import compute_window
from .notes_history import update_notes_history
from .export_excel import safe_overwrite

TODAY_FILE   = os.getenv("CUSTOMER_NOTES_XLSX", "customer_notes.xlsx")
HISTORY_FILE = os.getenv("CUSTOMER_NOTES_HISTORY_XLSX", "customer_notes_history.xlsx")

def _ensure_createdon_est(df: pd.DataFrame) -> pd.DataFrame:
    if "createdOn" in df.columns and "createdOn_est" not in df.columns:
        try:
            ts = pd.to_datetime(df["createdOn"], utc=True, errors="coerce").dt.tz_convert("America/New_York")
            df["createdOn_est"] = ts.dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    if "createdOn" in df.columns:
        df = df.drop(columns=["createdOn"])
    return df

def run_notes_sync(*, frm=None, to=None, center_code: str | None = None) -> pd.DataFrame:
    if frm is None or to is None:
        frm, to = compute_window()

    notes = fetch_customer_notes_range(frm, to, center_code=center_code)
    df = pd.DataFrame(notes)
    df = _ensure_createdon_est(df)

    if not safe_overwrite(TODAY_FILE):
        print("ℹ️ Target file may be open/locked; writing a NEW copy name.")
    df.to_excel(TODAY_FILE, index=False)
    print(f"📘 Saved Excel: {TODAY_FILE} ({len(df)} rows)")

    update_notes_history(today_file=TODAY_FILE, history_file=HISTORY_FILE)
    return df

if __name__ == "__main__":
    run_notes_sync()
