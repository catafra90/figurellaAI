# app/figurella_reports/services/ibf_first_session_service.py
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, date
from typing import Optional

import pandas as pd


# -------------------- helpers -------------------- #

def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except Exception:
            continue
    try:
        dt = pd.to_datetime(s, errors="coerce")
        if pd.isna(dt):
            return None
        return dt.date()
    except Exception:
        return None


def _norm(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _name_variants(name: str):
    t = _norm(name).split()
    if len(t) >= 2:
        first_last = " ".join([t[0], t[-1]])
        last_first = " ".join([t[-1], t[0]])
        return {first_last, last_first, " ".join(t)}
    return {" ".join(t)}


def _client_matcher(q: str):
    variants = _name_variants(q)

    def match(val: str) -> bool:
        nv = _norm(val)
        if nv in variants:
            return True
        vt = set(nv.split())
        for v in variants:
            if set(v.split()) == vt:
                return True
        return False

    return match


def _load_ibf_df() -> pd.DataFrame:
    """Load the IBF dataframe via the central loader."""
    try:
        from app.common.report_io import load_report_df as _core_load_report_df
        df = _core_load_report_df("ibf")
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


# -------------------- public API -------------------- #

def get_first_contract_date_for_client(client_q: str) -> Optional[str]:
    """
    Return first-contract start date for the given client as ISO 'YYYY-MM-DD', or None.

    Works with:
      A) Portal-wide shape: column 'Date Start First Contract'.
      B) Tidy shape: infer from earliest 'Date' row.
    """
    if not (client_q or "").strip():
        return None

    df_raw = _load_ibf_df()
    if df_raw is None or df_raw.empty:
        return None

    cols_lower = {c.lower(): c for c in df_raw.columns}
    client_col = (
        cols_lower.get("client")
        or cols_lower.get("name")
        or cols_lower.get("clientname")
        or "Client"
    )

    matcher = _client_matcher(client_q)
    if client_col not in df_raw.columns:
        return None

    # ---- A) Portal-wide: look for "Date Start First Contract" ----
    for key in cols_lower:
        if "date" in key and "start" in key and "first" in key and "contract" in key:
            first_contract_col = cols_lower[key]
            sub = df_raw[df_raw[client_col].map(lambda v: matcher(str(v)))].copy()
            if not sub.empty and first_contract_col in sub.columns:
                dates = (
                    sub[first_contract_col]
                    .dropna()
                    .map(_parse_date)
                    .dropna()
                    .tolist()
                )
                if dates:
                    d = min(dates)
                    return d.strftime("%Y-%m-%d")

    # ---- B) Tidy: fallback to earliest Date ----
    if "date" in cols_lower:
        date_col = cols_lower["date"]
        sub = df_raw[df_raw[client_col].map(lambda v: matcher(str(v)))].copy()
        if not sub.empty and date_col in sub.columns:
            dates = (
                pd.to_datetime(sub[date_col], errors="coerce")
                .dropna()
                .dt.date
                .tolist()
            )
            if dates:
                d = min(dates)
                return d.strftime("%Y-%m-%d")

    return None
