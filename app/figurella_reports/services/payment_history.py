# app/figurella_reports/services/payment_history.py

import os, tempfile, shutil
from datetime import datetime
import pandas as pd
import pytz

from .export_excel import safe_overwrite

TODAY_FILE = "payments.xlsx"
HISTORY_FILE = "payments_history.xlsx"
ADDED_AT_COL = "addedAt"
UNIQUE_KEY = "paymentId"

def _now_est_isooffset() -> str:
    est = pytz.timezone("America/New_York")
    dt = datetime.now(est)
    offset = dt.strftime("%z")
    offset = offset[:3] + ":" + offset[3:] if offset and len(offset) == 5 else offset
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset

def _read_today_file() -> pd.DataFrame:
    if not os.path.exists(TODAY_FILE):
        raise FileNotFoundError(f"❌ Missing file: {TODAY_FILE}")
    return pd.read_excel(TODAY_FILE)

def _read_history_file() -> pd.DataFrame:
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame()
    try:
        return pd.read_excel(HISTORY_FILE)
    except Exception:
        return pd.DataFrame()

def _align_columns(today: pd.DataFrame, hist: pd.DataFrame) -> list[str]:
    cols = list(today.columns)
    if ADDED_AT_COL not in cols:
        cols.append(ADDED_AT_COL)
    return cols

def _save_atomic_xlsx(df: pd.DataFrame, path: str):
    fd, tmp = tempfile.mkstemp(suffix=".xlsx", prefix="payments_history_")
    os.close(fd)
    try:
        df.to_excel(tmp, index=False)
        try:
            os.replace(tmp, path)
        except PermissionError:
            alt = f"{os.path.splitext(path)[0]}_NEW_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
            shutil.move(tmp, alt)
            print(f"⚠️ File locked. Saved new copy as: {alt}")
            return
        print(f"📘 Saved updated history: {path}")
    finally:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except Exception: pass

def update_payment_history():
    print("🔄 Updating payment history...")

    today_df = _read_today_file()
    hist_df = _read_history_file()

    # Add timestamp only to today's rows
    now = _now_est_isooffset()
    today_df[ADDED_AT_COL] = now

    if hist_df.empty:
        print(f"🆕 Creating new payment history from {TODAY_FILE}")
        final_df = today_df.copy()
        added = len(final_df)
    else:
        if ADDED_AT_COL not in hist_df.columns:
            hist_df[ADDED_AT_COL] = ""

        # Align columns
        all_cols = _align_columns(today_df, hist_df)
        today_df = today_df.reindex(columns=all_cols)
        hist_df  = hist_df.reindex(columns=all_cols)

        # Combine and deduplicate based on paymentId
        combined = pd.concat([hist_df, today_df], ignore_index=True)
        before = len(hist_df)
        final_df = combined.drop_duplicates(subset=[UNIQUE_KEY], keep="first")
        added = len(final_df) - before

    print(f"✅ {added} new unique payment(s) added. Total rows: {len(final_df)}")

    if not safe_overwrite(HISTORY_FILE):
        print("ℹ️ Target file may be open/locked; will write a NEW copy instead.")
    _save_atomic_xlsx(final_df, HISTORY_FILE)

if __name__ == "__main__":
    update_payment_history()
