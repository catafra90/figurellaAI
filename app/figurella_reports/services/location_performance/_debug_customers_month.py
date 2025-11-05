from __future__ import annotations
import os, re
from pathlib import Path
from datetime import datetime
import pandas as pd

try:
    from zoneinfo import ZoneInfo
except Exception:
    from pytz import timezone as ZoneInfo

NY = ZoneInfo("America/New_York")

# --------- ENV / defaults ----------
FILE   = os.getenv("CUSTOMERS_HISTORY_XLSX", "").strip()
SHEET  = os.getenv("NEW_CLIENTS_SHEET", "").strip()
CENTER = os.getenv("NEW_CLIENTS_CENTER_CODE", "").strip()
COUNT_UNIQUE = bool(int(os.getenv("NEW_CLIENTS_UNIQUE_CLIENTS", "1")))  # 1=unique by id (recommended)

# Fixed columns (from your workbook)
DATE_COL   = "registrationDate"
STATUS_COL = "status"
CENTER_COL = "centerCode"
ID_COL     = "id"

# OK-family: EXACT "OK", startswith "Current", EXACT "Consultation OK"
OK_RE  = re.compile(r"(?:^OK$)|(?:^CURRENT\b)|(?:^CONSULTATION\s*OK$)", re.IGNORECASE)
TRY_RE = re.compile(r"^TRY$", re.IGNORECASE)

def _month_bounds(ref: datetime, months_ago: int = 0):
    ref = ref.astimezone(NY).replace(hour=0, minute=0, second=0, microsecond=0)
    first = ref.replace(day=1)
    y, m = first.year, first.month - months_ago
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    start = first.replace(year=y, month=m)
    y2 = start.year + (start.month // 12)
    m2 = 1 if start.month == 12 else start.month + 1
    end = start.replace(year=y2, month=m2, day=1)
    return start, end

def _parse_local(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce", utc=True)
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize(NY)
    else:
        ts = ts.dt.tz_convert(NY)
    return ts

def _count_block(df: pd.DataFrame, start, end, center_mask, status):
    ts = _parse_local(df[DATE_COL])
    in_window = (ts >= start) & (ts < end)
    ok_mask  = status.str.match(OK_RE,  na=False)
    try_mask = status.str.match(TRY_RE, na=False)
    eff_ok   = in_window & center_mask & ok_mask
    eff_try  = in_window & center_mask & try_mask

    if COUNT_UNIQUE and ID_COL in df.columns:
        ok_ct  = df.loc[eff_ok,  ID_COL].nunique(dropna=True)
        try_ct = df.loc[eff_try, ID_COL].nunique(dropna=True)
    else:
        ok_ct  = int(eff_ok.sum())
        try_ct = int(eff_try.sum())

    return ok_ct, try_ct, eff_ok, eff_try

def main():
    if not FILE:
        print("❌ Set CUSTOMERS_HISTORY_XLSX to the full path of your Excel.")
        return
    p = Path(FILE)
    print("FILE:", p.resolve())

    if SHEET:
        df = pd.read_excel(p, sheet_name=SHEET)
        print("SHEET:", SHEET)
    else:
        df = pd.read_excel(p)
        print("SHEET: (first/default)")

    print("ROWS:", len(df))
    print("COLUMNS:", list(df.columns))

    for req in (DATE_COL, STATUS_COL):
        if req not in df.columns:
            print(f"❌ Missing column '{req}'.")
            return

    status = df[STATUS_COL].astype(str).str.strip()
    if CENTER and CENTER_COL in df.columns:
        center_mask = df[CENTER_COL].astype(str).str.strip().eq(CENTER)
    else:
        center_mask = pd.Series(True, index=df.index)

    now = datetime.now(NY)
    start_this, end_this = _month_bounds(now, 0)
    start_prev, end_prev = _month_bounds(now, 1)

    ok_this, try_this, eff_ok_this, eff_try_this = _count_block(df, start_this, end_this, center_mask, status)
    ok_prev, try_prev, eff_ok_prev, eff_try_prev = _count_block(df, start_prev, end_prev, center_mask, status)

    print("\nWINDOWS:")
    print("  THIS MONTH:", start_this, "→", end_this)
    print("  LAST MONTH:", start_prev, "→", end_prev)

    print("\nSTATUS distribution (top 12):")
    print(status.str.upper().value_counts(dropna=False).head(12).to_string())

    print("\nCOUNTS by registrationDate:")
    print(f"  This month  — OK: {ok_this}  TRY: {try_this}  TOTAL: {ok_this + try_this}")
    print(f"  Last month  — OK: {ok_prev}  TRY: {try_prev}  TOTAL: {ok_prev + try_prev}")

    def sample(eff_mask, label):
        cols = [c for c in [ID_COL, CENTER_COL, "name", "surname", STATUS_COL, DATE_COL] if c in df.columns]
        out = df.loc[eff_mask, cols]
        if COUNT_UNIQUE and ID_COL in out.columns:
            out = out.drop_duplicates(subset=[ID_COL])
        print(f"\nSample {label} (first 10):")
        print(out.head(10).to_string(index=False))

    sample(eff_ok_prev,  "LAST-MONTH OK")
    sample(eff_try_prev, "LAST-MONTH TRY")

if __name__ == "__main__":
    main()
