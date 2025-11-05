# File: app/services/internal_planning_from_contracts.py
from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime, date
import calendar


# -------- Helpers to find the workbooks (instance first) ----------
def _contracts_candidates(app_root: Path, instance_dir: Path) -> list[Path]:
    return [
        instance_dir / "figurella_reports" / "contracts_history.xlsx",
        instance_dir / "contracts_history.xlsx",
        instance_dir / "figurella_reports" / "contracts.xlsx",
        instance_dir / "contracts.xlsx",
        Path.cwd() / "contracts_history.xlsx",
        Path.cwd() / "contracts.xlsx",
        app_root / "figurella_reports" / "contracts_history.xlsx",
        app_root / "figurella_reports" / "contracts.xlsx",
    ]

def _customers_candidates(app_root: Path, instance_dir: Path) -> list[Path]:
    return [
        instance_dir / "figurella_reports" / "customers_history.xlsx",
        instance_dir / "customers_history.xlsx",
        Path.cwd() / "customers_history.xlsx",
        app_root / "figurella_reports" / "customers_history.xlsx",
    ]

def _first_existing(paths: list[Path]) -> Optional[Path]:
    for p in paths:
        if p.exists():
            return p
    return None

def _find_contracts_file(app_root: Path, instance_dir: Path) -> Optional[Path]:
    return _first_existing(_contracts_candidates(app_root, instance_dir))

def _find_customers_file(app_root: Path, instance_dir: Path) -> Optional[Path]:
    return _first_existing(_customers_candidates(app_root, instance_dir))


# -------- Date utilities ----------
def _parse_date_column(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, errors="coerce", utc=True)
    return dt.dt.tz_convert(None).dt.date

def _start_of_month(ts: datetime) -> date:
    return date(ts.year, ts.month, 1)

def _end_of_month(ts: datetime) -> date:
    last = calendar.monthrange(ts.year, ts.month)[1]
    return date(ts.year, ts.month, last)

def _yyyymmdd(d: Any) -> str:
    try:
        return pd.to_datetime(d).date().strftime("%Y-%m-%d")
    except Exception:
        return ""


# -------- Customers name map ----------
def _lower_map(cols: list[str]) -> Dict[str, str]:
    return {c.lower(): c for c in cols}

def _load_customer_name_map(app_root: Path, instance_dir: Path) -> Dict[str, str]:
    """
    Build { customerId -> "First Last" } from customers_history.xlsx
    Accepts columns case-insensitively; tries:
      - firstName/lastName
      - name/surname
      - name only (as fallback)
    Also accepts id/customerId for the key.
    """
    path = _find_customers_file(app_root, instance_dir)
    if not path:
        return {}

    try:
        df = pd.read_excel(path)
    except Exception:
        return {}

    cmap = _lower_map(list(map(str, df.columns)))
    def col(name: str) -> Optional[str]: return cmap.get(name.lower())

    id_col  = col("customerId") or col("id")
    if not id_col:
        return {}

    # Prefer explicit first/last; fall back to name/surname; then name only
    first = col("firstName") or col("name")
    last  = col("lastName")  or col("surname")

    names: Dict[str, str] = {}
    for _, r in df.iterrows():
        cid = r.get(id_col)
        if pd.isna(cid):
            continue
        key = str(cid).strip()

        full = ""
        if first and last and pd.notna(r.get(first)) and pd.notna(r.get(last)):
            full = f"{str(r.get(first)).strip()} {str(r.get(last)).strip()}".strip()
        elif first and pd.notna(r.get(first)):
            full = str(r.get(first)).strip()
        elif last and pd.notna(r.get(last)):
            full = str(r.get(last)).strip()

        if full:
            names[key] = full

    return names


# -------- Core builder ----------
def load_expiring_contract_rows(
    app_root: Path,
    instance_dir: Path,
    when: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Build Monthly Planning rows from contracts whose endDate falls within the month of `when` (default: now).

    Output rows contain:
      - internal_planning: full name (from customers_history) if available, else customerId
      - closing_date:      YYYY-MM-DD
      - current_contract:  productNames (if present)
      - status, p1/p2/p3 pack/price placeholders (empty)
    """
    when = when or datetime.now()
    contracts_path = _find_contracts_file(app_root, instance_dir)
    if not contracts_path:
        return []

    # Read contracts
    df = pd.read_excel(contracts_path)

    # Case-insensitive access
    colmap = _lower_map(list(map(str, df.columns)))
    def col(name: str) -> Optional[str]: return colmap.get(name.lower())

    cust_col  = col("customerId")
    end_col   = col("endDate")
    added_col = col("addedAt")       # may be None
    prod_col  = col("productNames")  # may be None

    if not cust_col or not end_col:
        return []

    # Dates
    df["_endDate"] = _parse_date_column(df[end_col])

    # Stable ordering key for de-duplication
    if added_col:
        df["_addedAt"] = pd.to_datetime(df[added_col], errors="coerce")
    else:
        df["_addedAt"] = pd.Timestamp(datetime.fromtimestamp(contracts_path.stat().st_mtime))

    # Deduplicate per contract or (customerId, endDate)
    if col("contractId"):
        df = df.sort_values("_addedAt").drop_duplicates(subset=[col("contractId")], keep="last")
    else:
        df = df.sort_values("_addedAt").drop_duplicates(subset=[cust_col, "_endDate"], keep="last")

    # Filter target month
    m_start = _start_of_month(when)
    m_end   = _end_of_month(when)
    dfm = df.loc[df["_endDate"].between(m_start, m_end, inclusive="both")].copy()

    # Load names map once
    name_map = _load_customer_name_map(app_root, instance_dir)

    # Build rows
    rows: List[Dict[str, Any]] = []
    for _, r in dfm.iterrows():
        raw_id = "" if pd.isna(r[cust_col]) else str(r[cust_col]).strip()
        display_name = name_map.get(raw_id, raw_id)  # prefer full name, else id
        closing      = _yyyymmdd(r["_endDate"])

        current_contract = ""
        if prod_col and prod_col in r and pd.notna(r[prod_col]):
            current_contract = str(r[prod_col]).strip()

        rows.append({
            "internal_planning": display_name,  # ← full name (or id fallback)
            "closing_date":      closing,
            "current_contract":  current_contract,
            "status": "",
            "p1_pack": "",  "p1_price": "",
            "p2_pack": "",  "p2_price": "",
            "p3_pack": "",  "p3_price": "",
        })
    return rows
