import re
import pandas as pd
from typing import Iterable, Optional, Dict, List

# ----------------------------- Dates -----------------------------------------

def coerce_dates(series: pd.Series) -> pd.Series:
    """
    Parse to datetime. Prefer US mm/dd/yyyy when slashes are used; strip NBSP.
    Unparsable -> NaT.
    """
    if series is None or not isinstance(series, pd.Series):
        return series

    def _one(x):
        if pd.isna(x):
            return pd.NaT
        s = str(x).strip().replace("\u00a0", " ")  # NBSP -> space
        if not s or s.upper() in {"N/A", "NA", "NO CONTRACT?", "NONE"}:
            return pd.NaT

        # If looks like nn/nn/nnnn, assume US (mm/dd/yyyy)
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", s):
            try:
                return pd.to_datetime(s, format="%m/%d/%Y", errors="raise")
            except Exception:
                pass

        # Try a few strict formats
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return pd.to_datetime(s, format=fmt, errors="raise")
            except Exception:
                continue

        # Fallback tries both dayfirst=False/True and returns the later if both valid
        us = pd.to_datetime(s, errors="coerce", dayfirst=False)
        eu = pd.to_datetime(s, errors="coerce", dayfirst=True)
        if pd.isna(us):
            return eu
        if pd.isna(eu):
            return us
        return max(us, eu)

    return series.map(_one)


# ---------------------------- Numbers ----------------------------------------

_NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d{3})*(?:[.,]\d{2})?")

def _token_has_only_commas(tok: str) -> bool:
    return tok.count(",") > 0 and tok.count(".") == 0

def to_number_any(val) -> float:
    """
    Extract the *last* numeric-looking token from a string and parse it as float.
    Handles '1.234,56', '1,234.56', '$123.45', bare ints. Non-parsable -> 0.0
    """
    if pd.isna(val):
        return 0.0
    s = str(val).strip()
    if not s:
        return 0.0

    last = None
    for m in _NUM_RE.finditer(s):
        last = m.group(0)

    if last is None:
        s2 = re.sub(r"[^\d\.\-]", "", s)
        try:
            return float(s2) if s2 else 0.0
        except Exception:
            return 0.0

    token = last
    if _token_has_only_commas(token):
        token = token.replace(".", "").replace(",", ".")
    else:
        token = token.replace(",", "")
    try:
        return float(token)
    except Exception:
        return 0.0


# --------------------------- DataFrame utils ---------------------------------

def drop_total_col(df: pd.DataFrame) -> pd.DataFrame:
    """Drop a 'Total' column if present; pass-through otherwise."""
    if isinstance(df, pd.DataFrame) and "Total" in df.columns:
        return df.drop(columns=["Total"])
    return df

def drop_first_n_and_names(
    df: Optional[pd.DataFrame],
    n: int = 0,
    names: Optional[Iterable[str]] = None
) -> Optional[pd.DataFrame]:
    """
    Drop the first N columns (by position) and any named columns.
    Safe on empty/None and unknown names.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df
    names = list(names or [])
    to_drop = list(df.columns[:max(0, n)]) + [c for c in names if c in df.columns]
    return df.drop(columns=to_drop, errors="ignore")


# --------------------------- Small helpers -----------------------------------

def strip_headers(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """
    Trim whitespace from column headers and unify repeated 'Unnamed' junk.
    Keeps code small and avoids template surprises.
    """
    if df is None or not isinstance(df, pd.DataFrame):
        return df
    cols = []
    for c in df.columns:
        sc = str(c).strip()
        cols.append(None if sc.lower().startswith("unnamed:") else sc)
    df = df.copy()
    df.columns = [("" if c is None else c) for c in cols]
    return df


# =========================== Reusable header mapping ==========================

def alias_cols(df: pd.DataFrame, aliases: Dict[str, List[str]]) -> pd.DataFrame:
    """
    Rename columns to canonical names.
    aliases = {"Last session": ["Last session","Last Session","Last visit", ...], ...}
    Only renames when a variant exists. No-ops if df is empty.
    """
    if df is None or df.empty:
        return df
    lower_map = {c.lower().strip(): c for c in df.columns}
    to_rename = {}
    for canon, variants in aliases.items():
        for v in variants:
            key = v.lower().strip()
            if key in lower_map:
                src = lower_map[key]
                if src != canon:
                    to_rename[src] = canon
                break  # found one variant; stop
    if to_rename:
        df = df.rename(columns=to_rename)
    return df
