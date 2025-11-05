# app/figurella_reports/services/location_performance/active_clients.py
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import re
import pandas as pd


def _coalesce_col(df: pd.DataFrame, names: list[str]) -> str | None:
    """Return the first matching column (case-insensitive)."""
    cols = {c.lower(): c for c in df.columns}
    for want in names:
        c = cols.get(want.lower())
        if c:
            return c
    return None


def _norm_id(val) -> str:
    """Normalize Excel-like IDs: 208933.0/'208,933' → '208933'."""
    if pd.isna(val):
        return ""
    s = str(val).strip().replace(",", "")
    m = re.fullmatch(r"(\d+)(?:\.0+)?", s)
    if m:
        return m.group(1)
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except Exception:
        pass
    return re.sub(r"\D", "", s)


def _parse_to_date(series: pd.Series) -> pd.Series:
    """Parse timestamps to local-naive date (no tz)."""
    dt = pd.to_datetime(series, errors="coerce", utc=True)
    # drop tz → naive then take date
    return dt.dt.tz_convert(None).dt.date


def _find_agenda_file(app_root: Path, instance_dir: Path) -> Path | None:
    """
    Priority (new, more robust):
      1) instance root: agenda_history.xlsx / history_agenda.xlsx
      2) instance/figurella_reports/: agenda_history.xlsx / history_agenda.xlsx
      3) app root: agenda_history.xlsx / history_agenda.xlsx
      4) CWD: agenda_history.xlsx / history_agenda.xlsx
    """
    candidates = [
        instance_dir / "agenda_history.xlsx",
        instance_dir / "history_agenda.xlsx",
        instance_dir / "figurella_reports" / "agenda_history.xlsx",
        instance_dir / "figurella_reports" / "history_agenda.xlsx",
        app_root / "agenda_history.xlsx",
        app_root / "history_agenda.xlsx",
        Path.cwd() / "agenda_history.xlsx",
        Path.cwd() / "history_agenda.xlsx",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _ok_mask(df: pd.DataFrame, status_str_col: str | None, status_num_col: str | None) -> pd.Series:
    """Return boolean mask for rows that represent an OK attendance."""
    ok_from_str = pd.Series(False, index=df.index)
    if status_str_col:
        s = df[status_str_col].astype(str).str.strip().str.casefold()
        # accept 'ok', '1 ok', 'ok ' etc.
        ok_from_str = s.str.contains(r"\bok\b", na=False)

    ok_from_num = pd.Series(False, index=df.index)
    if status_num_col:
        sn = pd.to_numeric(df[status_num_col], errors="coerce")
        ok_from_num = sn.eq(1)

    return ok_from_str | ok_from_num


def compute_active_clients_this_month(app_root: Path, instance_dir: Path) -> int:
    """
    Active Clients = UNIQUE customers with ≥1 OK appointment in the CURRENT calendar month.
    OK if statusString contains 'OK' (any case) OR numeric status == 1.
    Columns tolerated:
      customerId | customer_id
      appointmentDate | appointment_date | date
      statusString | status_string | status_text-ish
      status (numeric)
    """
    path = _find_agenda_file(app_root, instance_dir)
    if not path:
        return 0

    try:
        df = pd.read_excel(path)  # first sheet
    except Exception:
        return 0
    if df.empty:
        return 0

    cust_col       = _coalesce_col(df, ["customerId", "customer_id"])
    date_col       = _coalesce_col(df, ["appointmentDate", "appointment_date", "date"])
    status_str_col = _coalesce_col(df, ["statusString", "status_string", "status_text", "statusStr"])
    status_num_col = _coalesce_col(df, ["status"])  # numeric; 1 == OK

    if not (cust_col and date_col and (status_str_col or status_num_col)):
        return 0

    df = df.copy()
    df[date_col] = _parse_to_date(df[date_col])

    # current calendar month bounds
    today = datetime.today()
    first = datetime(today.year, today.month, 1).date()
    if today.month == 12:
        first_next = datetime(today.year + 1, 1, 1).date()
    else:
        first_next = datetime(today.year, today.month + 1, 1).date()

    ok_mask = _ok_mask(df, status_str_col, status_num_col)
    month_mask = (df[date_col] >= first) & (df[date_col] < first_next)

    m = ok_mask & month_mask & df[cust_col].notna()
    if not m.any():
        return 0

    # Normalize IDs to avoid 208933 vs 208933.0 duplicates
    ids = df.loc[m, cust_col].map(_norm_id)
    ids = ids[ids != ""]
    if ids.empty:
        return 0
    return int(ids.nunique())
