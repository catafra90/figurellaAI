# app/figurella_reports/services/ibf_frequency_service.py
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, date
from typing import Dict, Optional, Tuple, List

import pandas as pd


# ---------------------------------------------------------------------------
# Public constants (match your template short keys exactly)
# ---------------------------------------------------------------------------
MONTH_KEYS = ["Jan", "Feb", "Mar", "Apr", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec"]
NUM_TO_KEY = {i + 1: k for i, k in enumerate(MONTH_KEYS)}

# Name variants for parsing month-name columns (portal-wide shape)
MONTH_NAME_ALIASES = {
    # short -> canonical (your template keys)
    "jan": "Jan", "jan.": "Jan", "january": "Jan",
    "feb": "Feb", "feb.": "Feb", "february": "Feb",
    "mar": "Mar", "mar.": "Mar", "march": "Mar",
    "apr": "Apr", "apr.": "Apr", "april": "Apr",
    "may": "May",
    "jun": "June", "jun.": "June", "june": "June",
    "jul": "July", "jul.": "July", "july": "July",
    "aug": "Aug", "aug.": "Aug", "august": "Aug",
    "sep": "Sept", "sep.": "Sept", "sept": "Sept", "sept.": "Sept", "september": "Sept",
    "oct": "Oct", "oct.": "Oct", "october": "Oct",
    "nov": "Nov", "nov.": "Nov", "november": "Nov",
    "dec": "Dec", "dec.": "Dec", "december": "Dec",
}


def months_zero() -> Dict[str, int]:
    """Return a zeroed month map Jan..Dec."""
    return {k: 0 for k in MONTH_KEYS}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


def _norm(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _client_matcher(q: str):
    """
    Token-based matcher:
      - case/diacritics-insensitive
      - order-insensitive
      - query tokens subset of value tokens (handles middle names)
    """
    qt = set(_norm(q).split())

    def match(val: str) -> bool:
        vt = set(_norm(val).split())
        if not qt or not vt:
            return False
        return (qt == vt) or qt.issubset(vt)

    return match


def _coerce_int(x) -> int:
    try:
        return int(float(str(x).strip()))
    except Exception:
        return 0


def _load_ibf_df() -> pd.DataFrame:
    """Load the IBF dataframe via the central loader."""
    try:
        from app.common.report_io import load_report_df as _core_load_report_df
        df = _core_load_report_df("ibf")
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _guess_client_col(cols_lower: Dict[str, str]) -> str:
    # direct obvious names
    for key in ("client", "clientname", "client_name", "client name", "name"):
        if key in cols_lower:
            return cols_lower[key]
    # any column containing 'client'
    for k, orig in cols_lower.items():
        if "client" in k:
            return orig
    return "Client"  # fallback


def _guess_bubb_col(cols_lower: Dict[str, str]) -> Optional[str]:
    for key in ("bubb", "bubble", "bubbles"):
        if key in cols_lower:
            return cols_lower[key]
    # also try variants like 'bubb.' (unlikely but safe)
    for k, orig in cols_lower.items():
        if k.startswith("bubb"):
            return orig
    return None


def _guess_date_col(cols_lower: Dict[str, str]) -> Optional[str]:
    for key in ("date", "session_date", "session date"):
        if key in cols_lower:
            return cols_lower[key]
    # generous fallback: first column that looks like date-ish by name
    for k, orig in cols_lower.items():
        if "date" in k:
            return orig
    return None


def _norm_month_key(k: str) -> Optional[str]:
    """Normalize a month label like 'Jan', 'Jan.', 'January' -> our canonical keys."""
    if not k:
        return None
    k = _norm(k)
    return MONTH_NAME_ALIASES.get(k, None)


def _scan_portal_wide_month_cols(df: pd.DataFrame) -> List[Tuple[str, int, int]]:
    """
    Return a list of (column_name, month_number, year) for portal-wide tables.
    Supports:
      - "5 - 2025"
      - "Jan - 2025", "January 2025"
      - "Jan. - 2025", "Sept - 2025", etc.
    """
    cols: List[Tuple[str, int, int]] = []

    # Numeric "m - yyyy"
    num_re = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{4})\s*$")

    # Name + year, with optional punctuation (e.g., "Jan - 2025", "January 2025", "Sept. 2024")
    name_re = re.compile(r"^\s*([A-Za-z\.]+)\s*(?:-|,)?\s*(\d{4})\s*$")

    for c in df.columns:
        s = str(c).strip()
        m = num_re.match(s)
        if m:
            mm = int(m.group(1))
            yyyy = int(m.group(2))
            if 1 <= mm <= 12:
                cols.append((c, mm, yyyy))
            continue

        m2 = name_re.match(s)
        if m2:
            month_label = m2.group(1)
            yyyy = int(m2.group(2))
            canon = _norm_month_key(month_label)
            if canon:
                # map canonical key -> month number
                mm = list(NUM_TO_KEY.keys())[list(NUM_TO_KEY.values()).index(canon)]
                cols.append((c, mm, yyyy))

    return cols


def _extract_bubb_from_cell(val) -> int:
    """
    Accepts cell strings like 'Bubb: 13  Cell: 0' or plain numbers.
    """
    if pd.isna(val):
        return 0
    s = str(val)
    m = re.search(r"(?:bubb(?:le)?s?\s*[:=]\s*)?(-?\d+)", s, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return _coerce_int(s)
    return _coerce_int(s)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ibf_months_for_client(client_q: str, start_q: Optional[str], end_q: Optional[str]) -> Dict[str, int]:
    """
    Build a Jan..Dec month map of Bubble (Bubb) counts for a specific client,
    accepting either:
      - tidy shape: cols [Date, Client, Bubb/Bubble/Bubbles]
      - portal-wide shape: month columns like "5 - 2025" OR "Jan - 2025" with cell text "Bubb: 13  Cell: 0" or numbers.
    """
    out = months_zero()
    if not client_q:
        return out

    start_d = _parse_date(start_q)
    end_d = _parse_date(end_q)
    df_raw = _load_ibf_df()
    if df_raw is None or df_raw.empty:
        return out

    cols_lower = {str(c).lower(): c for c in df_raw.columns}

    # ---------- Shape A (tidy): Date + Bubb + Client ----------
    DateCol = _guess_date_col(cols_lower)
    BubbCol = _guess_bubb_col(cols_lower)
    ClientCol = _guess_client_col(cols_lower)

    has_tidy = (DateCol is not None) and (BubbCol is not None) and (ClientCol in df_raw.columns)
    if has_tidy:
        df = df_raw.copy()

        # Coerce types
        df[DateCol] = pd.to_datetime(df[DateCol], errors="coerce").dt.date
        df[BubbCol] = df[BubbCol].map(_coerce_int)

        matcher = _client_matcher(client_q)
        df = df[df[ClientCol].map(lambda v: matcher(str(v)))]

        if start_d:
            df = df[df[DateCol] >= start_d]
        if end_d:
            df = df[df[DateCol] <= end_d]

        if not df.empty:
            df["_month"] = pd.to_datetime(df[DateCol], errors="coerce").map(lambda d: d.month if pd.notna(d) else None)
            df = df[df["_month"].notna()]
            grp = df.groupby("_month")[BubbCol].sum().to_dict()
            for mm, val in grp.items():
                k = NUM_TO_KEY.get(int(mm))
                if k:
                    out[k] += int(val)
            return out

    # ---------- Shape B (portal-wide): month columns per year ----------
    month_cols = _scan_portal_wide_month_cols(df_raw)
    if month_cols:
        matcher = _client_matcher(client_q)
        cand = df_raw[df_raw[_guess_client_col(cols_lower)].map(lambda v: matcher(str(v)))] \
            if _guess_client_col(cols_lower) in df_raw.columns else df_raw.head(0)

        if not cand.empty:
            start_ym = (start_d.year, start_d.month) if start_d else None
            end_ym = (end_d.year, end_d.month) if end_d else None

            for _, row in cand.iterrows():
                for col, mm, yyyy in month_cols:
                    if start_ym and (yyyy, mm) < (start_ym[0], start_ym[1]):
                        continue
                    if end_ym and (yyyy, mm) > (end_ym[0], end_ym[1]):
                        continue
                    bubb = _extract_bubb_from_cell(row.get(col, ""))
                    if bubb <= 0:
                        continue
                    key = NUM_TO_KEY.get(mm)
                    if key:
                        out[key] += bubb
            return out

    return out


def ibf_best_year_months_for_client(client_q: str) -> Dict[str, int]:
    """
    Return the month map for the single year where the client has the highest total Bubb.
    Works for both tidy (Date+Bubb) and portal-wide (month columns) shapes.
    """
    out = months_zero()
    if not client_q:
        return out

    df_raw = _load_ibf_df()
    if df_raw is None or df_raw.empty:
        return out

    cols_lower = {str(c).lower(): c for c in df_raw.columns}

    # ---------- Tidy shape ----------
    DateCol = _guess_date_col(cols_lower)
    BubbCol = _guess_bubb_col(cols_lower)
    ClientCol = _guess_client_col(cols_lower)

    has_tidy = (DateCol is not None) and (BubbCol is not None) and (ClientCol in df_raw.columns)
    if has_tidy:
        df = df_raw.copy()

        df[DateCol] = pd.to_datetime(df[DateCol], errors="coerce")
        df[BubbCol] = df[BubbCol].map(_coerce_int)

        matcher = _client_matcher(client_q)
        df = df[df[ClientCol].map(lambda v: matcher(str(v)))]

        if not df.empty:
            df["year"] = df[DateCol].dt.year
            df["_mon"] = df[DateCol].dt.month

            by_year = df.groupby("year")[BubbCol].sum()
            if not by_year.empty and by_year.max() > 0:
                best_year = int(by_year.idxmax())
                one = df[df["year"] == best_year].groupby("_mon")[BubbCol].sum().to_dict()
                for mm, val in one.items():
                    k = NUM_TO_KEY.get(int(mm))
                    if k:
                        out[k] += int(val)
                return out

    # ---------- Portal-wide shape ----------
    month_cols = _scan_portal_wide_month_cols(df_raw)
    if month_cols:
        client_col = _guess_client_col(cols_lower)
        if client_col in df_raw.columns:
            matcher = _client_matcher(client_q)
            cand = df_raw[df_raw[client_col].map(lambda v: matcher(str(v)))].copy()
        else:
            cand = df_raw.head(0)

        if not cand.empty:
            totals_by_year: Dict[int, int] = {}
            for _, row in cand.iterrows():
                for col, mm, yyyy in month_cols:
                    bubb = _extract_bubb_from_cell(row.get(col, ""))
                    if bubb <= 0:
                        continue
                    totals_by_year[yyyy] = totals_by_year.get(yyyy, 0) + bubb

            if totals_by_year:
                best_year = max(totals_by_year, key=totals_by_year.get)
                for _, row in cand.iterrows():
                    for col, mm, yyyy in month_cols:
                        if yyyy != best_year:
                            continue
                        bubb = _extract_bubb_from_cell(row.get(col, ""))
                        if bubb <= 0:
                            continue
                        k = NUM_TO_KEY.get(mm)
                        if k:
                            out[k] += bubb
                return out

    return out
