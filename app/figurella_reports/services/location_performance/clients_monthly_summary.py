from __future__ import annotations
import os, re
from pathlib import Path
from datetime import datetime
import pandas as pd

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from pytz import timezone as ZoneInfo

NY = ZoneInfo("America/New_York")

# ───────── Config ─────────
CUSTOMERS_HISTORY_XLSX  = os.getenv("CUSTOMERS_HISTORY_XLSX", "").strip()
NEW_CLIENTS_SHEET       = os.getenv("NEW_CLIENTS_SHEET", "").strip()
NEW_CLIENTS_CENTER_CODE = os.getenv("NEW_CLIENTS_CENTER_CODE", "").strip()
# ✅ default: unique customers by id (avoid duplicate rows for the same person)
NEW_CLIENTS_UNIQUE      = bool(int(os.getenv("NEW_CLIENTS_UNIQUE_CLIENTS", "1")))

# Fixed workbook columns (from your file)
DATE_COL   = "registrationDate"   # month bucketing ONLY by this column
STATUS_COL = "status"             # text status
CENTER_COL = "centerCode"
ID_COL     = "id"

# Status rules:
#  - OK family: "OK", startswith "Current" (e.g., "Current client"), EXACT "Consultation OK"
#  - TRY family: EXACT "Try"
OK_RE  = re.compile(r"(?:^OK$)|(?:^CURRENT\b)|(?:^CONSULTATION\s*OK$)", re.IGNORECASE)
TRY_RE = re.compile(r"^TRY$", re.IGNORECASE)

# ───────── Helpers ─────────
def _find_customers_history(app_root: Path) -> Path | None:
    if CUSTOMERS_HISTORY_XLSX:
        p = Path(CUSTOMERS_HISTORY_XLSX)
        if p.is_absolute() and p.exists():
            print(f"✅ Using absolute customers history path: {p}")
            return p
    project_root = app_root.parent
    for name in ("customers_history.xlsx", "customer_history.xlsx", "customers.xlsx"):
        for p in (
            app_root / "instance" / "figurella_reports" / name,
            app_root / name,
            project_root / name,
        ):
            if p.exists():
                print(f"✅ Found customers history: {p}")
                return p
    print("⚠️ Customers history XLSX not found.")
    return None

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

def _count_block(df: pd.DataFrame, start, end) -> dict:
    # window by registrationDate
    ts = _parse_local(df[DATE_COL])
    in_window = (ts >= start) & (ts < end)

    # status masks
    status = df[STATUS_COL].astype(str).str.strip()
    ok_mask  = status.str.match(OK_RE,  na=False)
    try_mask = status.str.match(TRY_RE, na=False)

    # optional center filter
    if NEW_CLIENTS_CENTER_CODE and CENTER_COL in df.columns:
        center_mask = df[CENTER_COL].astype(str).str.strip().eq(NEW_CLIENTS_CENTER_CODE)
        ok_mask  &= center_mask
        try_mask &= center_mask

    ok_mask  &= in_window
    try_mask &= in_window

    if NEW_CLIENTS_UNIQUE and ID_COL in df.columns:
        ok_ct  = df.loc[ok_mask,  ID_COL].nunique(dropna=True)
        try_ct = df.loc[try_mask, ID_COL].nunique(dropna=True)
    else:
        ok_ct  = int(ok_mask.sum())
        try_ct = int(try_mask.sum())

    return {"ok": int(ok_ct), "try": int(try_ct), "total": int(ok_ct + try_ct)}

def compute_clients_monthly_summary(app_root: Path) -> dict:
    path = _find_customers_history(app_root)
    if not path:
        return {"new_clients": {"this_month": {"total": 0, "ok": 0, "try": 0},
                                "last_month": {"total": 0, "ok": 0, "try": 0}}}

    df = pd.read_excel(path, sheet_name=NEW_CLIENTS_SHEET) if NEW_CLIENTS_SHEET else pd.read_excel(path)

    # guards
    for req in (DATE_COL, STATUS_COL):
        if req not in df.columns:
            print(f"⚠️ Missing column '{req}' in {path}")
            return {"new_clients": {"this_month": {"total": 0, "ok": 0, "try": 0},
                                    "last_month": {"total": 0, "ok": 0, "try": 0}}}

    now = datetime.now(NY)
    start_this, end_this = _month_bounds(now, 0)   # current month
    start_prev, end_prev = _month_bounds(now, 1)   # last month

    this_block = _count_block(df, start_this, end_this)
    prev_block = _count_block(df, start_prev, end_prev)

    out = {"new_clients": {"this_month": this_block, "last_month": prev_block}}
    print(f"✅ New clients summary (unique={NEW_CLIENTS_UNIQUE}): {out}")
    return out
