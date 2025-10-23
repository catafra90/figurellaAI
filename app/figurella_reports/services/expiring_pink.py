from __future__ import annotations
import re
import unicodedata
from datetime import datetime
from typing import Dict, List, Tuple

import pandas as pd

from ..io.loader import load_df


# ------------------------- Helpers -------------------------

def _safe_df(x) -> pd.DataFrame:
    """Return the DataFrame if valid, else an empty DataFrame (avoids boolean eval)."""
    return x if isinstance(x, pd.DataFrame) else pd.DataFrame()

def _norm(s: str) -> str:
    """Casefold, strip accents, collapse spaces."""
    if s is None:
        return ""
    s = str(s).strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.casefold()
    s = re.sub(r"\s+", " ", s)
    return s

def _full(first: str, last: str) -> str:
    return _norm(f"{first or ''} {last or ''}".strip())

def _pick(df: pd.DataFrame, *cands: str) -> str | None:
    """Pick the first existing column (case-insensitive)."""
    if df is None or df.empty:
        return None
    lower = {c.lower(): c for c in df.columns}
    for k in cands:
        if k.lower() in lower:
            return lower[k.lower()]
    return None

def _parse_date_series(s: pd.Series) -> pd.Series:
    if s is None:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(s, errors="coerce")


# ------------------------- Core -------------------------

def find_expiring_pink_clients(now: datetime | None = None) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    Find clients who:
      - Have 'PINK' mentioned in Contracts 'Details' (case-insensitive), and
      - Have 'Fine contratto' falling in the current month (from Last Session).

    Returns:
      (df, payload)
      df: Pandas DataFrame with columns ["Name","Surname","Fine contratto","Source"]
      payload: List[Dict] with keys: name, surname, full_name, fine_contratto, source
    """
    now = now or datetime.today()
    cy, cm = now.year, now.month

    # Never use `or pd.DataFrame()` with DataFrames: it triggers ambiguous truth value.
    dfc = _safe_df(load_df("contracts"))
    dfl = _safe_df(load_df("last_session"))

    if dfc.empty or dfl.empty:
        return pd.DataFrame(columns=["Name", "Surname", "Fine contratto", "Source"]), []

    # ---- Contracts columns ----
    c_name    = _pick(dfc, "Name", "Nome")
    c_surname = _pick(dfc, "Surname", "Cognome", "Cognome/Last Name")
    c_details = _pick(dfc, "Details", "Dettagli", "Note")

    if not (c_name and c_surname and c_details):
        return pd.DataFrame(columns=["Name", "Surname", "Fine contratto", "Source"]), []

    # Keep only rows containing "PINK" (e.g., "Pink 6", "PINK", etc.)
    mask_pink = dfc[c_details].astype(str).str.contains(r"\bPINK\b", flags=re.I, regex=True)
    df_pink = dfc.loc[mask_pink].copy()
    if df_pink.empty:
        return pd.DataFrame(columns=["Name", "Surname", "Fine contratto", "Source"]), []

    # Build normalized name set
    pink_names = {
        _full(r.get(c_name, ""), r.get(c_surname, ""))
        for _, r in df_pink.iterrows()
        if str(r.get(c_name, "")).strip() or str(r.get(c_surname, "")).strip()
    }
    pink_names.discard("")  # just in case

    if not pink_names:
        return pd.DataFrame(columns=["Name", "Surname", "Fine contratto", "Source"]), []

    # ---- Last Session columns ----
    ls_name    = _pick(dfl, "Name", "Nome")
    ls_surname = _pick(dfl, "Surname", "Cognome")
    ls_exp     = _pick(dfl, "Fine contratto", "Fine contratto/End of contract", "Contract End", "End date")

    if not (ls_name and ls_surname and ls_exp):
        return pd.DataFrame(columns=["Name", "Surname", "Fine contratto", "Source"]), []

    # Filter to the current month
    dates = _parse_date_series(dfl[ls_exp])
    m = (dates.dt.year == cy) & (dates.dt.month == cm)
    month_df = dfl.loc[m].copy()
    if month_df.empty:
        return pd.DataFrame(columns=["Name", "Surname", "Fine contratto", "Source"]), []

    # Normalize names and intersect with PINK set
    month_df["__full"] = [
        _full(r.get(ls_name, ""), r.get(ls_surname, ""))
        for _, r in month_df.iterrows()
    ]
    out = month_df[month_df["__full"].isin(pink_names)].copy()
    if out.empty:
        return pd.DataFrame(columns=["Name", "Surname", "Fine contratto", "Source"]), []

    # Shape output
    out = out.rename(columns={ls_name: "Name", ls_surname: "Surname", ls_exp: "Fine contratto"})
    keep = [c for c in ["Name", "Surname", "Fine contratto"] if c in out.columns]
    out = out[keep]
    out["Source"] = "last_session"

    # Deduplicate by (Name, Surname, Fine contratto) to avoid repeats
    out = out.drop_duplicates(subset=[c for c in ["Name", "Surname", "Fine contratto"] if c in out.columns])

    # Build JSON payload
    payload: List[Dict] = []
    for _, r in out.iterrows():
        dt = pd.to_datetime(r.get("Fine contratto"), errors="coerce")
        payload.append({
            "name": str(r.get("Name", "")),
            "surname": str(r.get("Surname", "")),
            "full_name": f"{str(r.get('Name','')).strip()} {str(r.get('Surname','')).strip()}".strip(),
            "fine_contratto": (dt.date().isoformat() if pd.notna(dt) else None),
            "source": "last_session",
        })

    return out.reset_index(drop=True), payload
