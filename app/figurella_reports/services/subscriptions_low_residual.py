from __future__ import annotations
import re
from typing import Dict, List, Tuple

import pandas as pd

from ..io.loader import load_df


# --------------------- helpers ---------------------

def _safe_df(x) -> pd.DataFrame:
    return x if isinstance(x, pd.DataFrame) else pd.DataFrame()

def _pick(df: pd.DataFrame, *cands: str) -> str | None:
    if df is None or df.empty:
        return None
    lower = {c.lower(): c for c in df.columns}
    for k in cands:
        if k.lower() in lower:
            return lower[k.lower()]
    return None

_LAST_ITEM_RE = re.compile(
    # matches "... N - <text> (residual: 12)" and captures "<text>" and "12"
    r"(?:^|\s)(\d+)\s*-\s*([^\(]+?)\s*\(residual:\s*(\d+)\)\s*$",
    flags=re.IGNORECASE
)

_ITEM_RE = re.compile(
    r"(?:^|\s)(\d+)\s*-\s*([^\(]+?)\s*\(residual:\s*(\d+)\)\s*",
    flags=re.IGNORECASE
)

def _extract_last_item(details: str) -> Tuple[str, int] | None:
    """
    From a long 'Contracts' description, extract the last contract entry
    and its residual count.

    Returns: (last_text, residual_int) or None if not found.
    """
    if not details:
        return None
    text = str(details)

    # Try a robust "find all items, pick the last" first
    items = list(_ITEM_RE.finditer(text))
    if items:
        last = items[-1]
        last_text = last.group(2).strip()
        try:
            residual = int(last.group(3))
        except Exception:
            return None
        return last_text, residual

    # Fallback (rare): anchor at end
    m = _LAST_ITEM_RE.search(text)
    if not m:
        return None
    last_text = m.group(2).strip()
    try:
        residual = int(m.group(3))
    except Exception:
        return None
    return last_text, residual


# --------------------- core ---------------------

def find_low_residual_nonpink(threshold: int = 10) -> List[Dict]:
    """
    From the Subscriptions report, collect clients whose LAST contract item
    is NOT 'PINK' and whose residual is strictly less than `threshold`.
    Returns a list of dicts: {full_name, name, surname, residual, last_contract, source}
    """
    df = _safe_df(load_df("subscriptions"))
    if df.empty:
        return []

    # Try to find name columns; tolerate different languages/layouts
    name_col    = _pick(df, "Name", "Nome", "First Name")
    surname_col = _pick(df, "Surname", "Cognome", "Last Name")
    client_col  = _pick(df, "Client", "Cliente")  # occasionally a single client column
    details_col = _pick(df, "Contracts", "Contratti", "Details", "Dettagli")

    if not details_col:
        return []

    out: List[Dict] = []

    for _, row in df.iterrows():
        details = row.get(details_col, "")
        last = _extract_last_item(details)
        if not last:
            continue
        last_text, residual = last

        # Exclude if last contract mentions PINK (case-insensitive)
        if "pink" in str(last_text).lower():
            continue

        # Keep only residual strictly less than threshold
        try:
            res_val = int(residual)
        except Exception:
            continue
        if not (res_val < int(threshold)):
            continue

        # Build a name
        first = str(row.get(name_col, "")).strip() if name_col else ""
        lastn = str(row.get(surname_col, "")).strip() if surname_col else ""
        if not (first or lastn):
            # fallback to 'Client' single column if present
            first = str(row.get(client_col, "")).strip()
            lastn = ""

        full = f"{first} {lastn}".strip()

        out.append({
            "name": first,
            "surname": lastn,
            "full_name": full,
            "residual": res_val,
            "last_contract": last_text,
            "source": "subscriptions",
        })

    return out
