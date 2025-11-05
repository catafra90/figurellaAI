# app/figurella_reports/services/customer_history.py
import os
import tempfile
import shutil
from datetime import datetime
from typing import List

import pandas as pd
import pytz

from .export_excel import safe_overwrite  # your helper

# Filenames
TODAY_FILE   = "customers.xlsx"
HISTORY_FILE = "customers_history.xlsx"

ADDED_AT_COL = "addedAt"  # EST timestamp with UTC offset
ID_COL       = "id"       # stable customer id
CENTER_COL   = "centerCode"  # kept, but not required for the logic

# Fields that, if changed (with same ID and same status), cause a REPLACE (not append)
REPLACE_FIELDS = ["name", "surname", "email", "phone", "birthDate"]

def _now_est_isooffset() -> str:
    est = pytz.timezone("America/New_York")
    dt  = datetime.now(est)
    offset = dt.strftime("%z")
    offset = offset[:3] + ":" + offset[3:] if offset and len(offset) == 5 else offset
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset

# ───────────────────────── helpers ─────────────────────────

def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return df
    df = df.copy()
    df.columns = pd.Index([str(c).strip() for c in df.columns])
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated(keep="first")]
    return df

def _read_customers_today() -> pd.DataFrame:
    if not os.path.exists(TODAY_FILE):
        raise FileNotFoundError(f"❌ {TODAY_FILE} not found. Run the customers export first.")
    df = pd.read_excel(TODAY_FILE)
    return _norm_cols(df)

def _read_history() -> pd.DataFrame:
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame()
    df = pd.read_excel(HISTORY_FILE)
    return _norm_cols(df)

def _align_schema(today: pd.DataFrame, history: pd.DataFrame) -> List[str]:
    """
    Union of columns; keep today's order first, then history extras, then addedAt last.
    """
    cols = list(today.columns)
    for c in history.columns:
        if c not in cols:
            cols.append(c)
    if ADDED_AT_COL not in cols:
        cols.append(ADDED_AT_COL)
    return cols

def _save_atomic_xlsx(df: pd.DataFrame, path: str):
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".xlsx", prefix="customers_history_")
    os.close(tmp_fd)
    try:
        df.to_excel(tmp_path, index=False)
        try:
            os.replace(tmp_path, path)
        except PermissionError:
            alt = f"{os.path.splitext(path)[0]}_NEW_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
            shutil.move(tmp_path, alt)
            print(f"⚠️ File locked. Saved new copy as: {alt}")
            return
        print(f"📘 Saved to: {path}")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

# ---- statusKey (so 4, 4.0, "4" compare equally; fallback to status text)
def _compute_status_key(row: pd.Series) -> str:
    # Prefer numeric idStatus if present/usable
    if "idStatus" in row.index:
        try:
            # coerce to integer-like string
            v = pd.to_numeric(row["idStatus"], errors="coerce")
            if pd.notna(v):
                return str(int(v))
        except Exception:
            pass
    # Else prefer numeric 'status' if it's really numeric
    if "status" in row.index:
        try:
            v = pd.to_numeric(row["status"], errors="coerce")
            if pd.notna(v):
                return str(int(v))
        except Exception:
            pass
        # or as text without trailing .0
        s = str(row["status"]).strip()
        if s:
            return s.rstrip("0").rstrip(".") if s.endswith(".0") else s
    # Else fallback to text statusString upper
    if "status" in row.index and isinstance(row["status"], str) and row["status"].strip():
        return row["status"].strip().upper()
    if "statusString" in row.index:
        return str(row["statusString"]).strip().upper()
    return ""

def _rows_equal_excluding(cols: List[str], a: pd.Series, b: pd.Series, exclude: List[str]) -> bool:
    ex = set(exclude)
    for c in cols:
        if c in ex:
            continue
        va = a.get(c, pd.NA)
        vb = b.get(c, pd.NA)
        # Treat NaN/None as equal
        if (pd.isna(va) and pd.isna(vb)):
            continue
        if str(va) != str(vb):
            return False
    return True

# ───────────────────────── main ─────────────────────────

def update_customer_history():
    """
    Rules:
      1) If same ID and status changed → APPEND a new row (keep old rows).
      2) If same ID and (name|surname|email|phone|birthDate) changed AND status did NOT change → REPLACE the latest row for that ID.
      3) If all columns (except '$id') are identical → SKIP.

    '$id' is ignored in comparisons. 'addedAt' is set on appended or replaced rows.
    """
    print("🔄 Updating customer history (append on status change, replace on profile change)…")

    today = _read_customers_today()
    history = _read_history()

    # Ensure required columns exist
    if ID_COL not in today.columns:
        raise RuntimeError(f"'{ID_COL}' column is required in customers.xlsx")

    # Stamp addedAt for incoming rows
    now_est = _now_est_isooffset()

    # Align schema (union)
    final_cols = _align_schema(today, history)
    history = history.reindex(columns=final_cols, fill_value=pd.NA)
    today   = today.reindex(columns=final_cols,  fill_value=pd.NA)

    # Work on a copy we’ll mutate
    out = history.copy()
    before_count = len(out)

    # For fast lookups: group indexes by id
    if not out.empty and ID_COL in out.columns:
        id_to_indexes = {}
        for idx, cid in zip(out.index, out[ID_COL]):
            id_to_indexes.setdefault(cid, []).append(idx)
    else:
        id_to_indexes = {}

    appended, replaced, skipped, new_ids = 0, 0, 0, 0

    # Process each incoming row
    for _, new_row in today.iterrows():
        cid = new_row.get(ID_COL, None)
        if pd.isna(cid):
            # If no ID, treat as append
            new_row2 = new_row.copy()
            new_row2[ADDED_AT_COL] = now_est
            out = pd.concat([out, pd.DataFrame([new_row2])], ignore_index=True)
            appended += 1
            continue

        idx_list = id_to_indexes.get(cid, [])
        if not idx_list:
            # Brand new ID → append
            new_row2 = new_row.copy()
            new_row2[ADDED_AT_COL] = now_est
            out = pd.concat([out, pd.DataFrame([new_row2])], ignore_index=True)
            id_to_indexes.setdefault(cid, []).append(len(out)-1)
            appended += 1
            new_ids += 1
            continue

        # Compare with the latest history row for this ID
        last_idx = idx_list[-1]
        old_row = out.loc[last_idx]

        # Build status keys
        new_status = _compute_status_key(new_row)
        old_status = _compute_status_key(old_row)

        if new_status != old_status:
            # Rule 1: append a new row
            new_row2 = new_row.copy()
            new_row2[ADDED_AT_COL] = now_est
            out = pd.concat([out, pd.DataFrame([new_row2])], ignore_index=True)
            id_to_indexes[cid].append(len(out)-1)
            appended += 1
            continue

        # Rule 2: same status → check profile fields
        profile_changed = False
        for f in REPLACE_FIELDS:
            if f in out.columns:
                va = old_row.get(f, pd.NA)
                vb = new_row.get(f, pd.NA)
                if (pd.isna(va) and pd.isna(vb)):
                    continue
                if str(va) != str(vb):
                    profile_changed = True
                    break

        if profile_changed:
            # REPLACE the latest row for that id with the new row (and new addedAt)
            new_row2 = new_row.copy()
            new_row2[ADDED_AT_COL] = now_est
            # assign back into out at last_idx, preserving columns
            for c in final_cols:
                out.at[last_idx, c] = new_row2.get(c, pd.NA)
            replaced += 1
            continue

        # Rule 3: identical (excluding $id differences) → skip
        # Build comparison list: all columns except $id and addedAt
        comp_cols = [c for c in final_cols if c not in ("$id", ADDED_AT_COL)]
        if _rows_equal_excluding(comp_cols, old_row, new_row, exclude=[]):
            skipped += 1
        else:
            # If something else changed (rare), default to append to avoid losing info
            new_row2 = new_row.copy()
            new_row2[ADDED_AT_COL] = now_est
            out = pd.concat([out, pd.DataFrame([new_row2])], ignore_index=True)
            id_to_indexes[cid].append(len(out)-1)
            appended += 1

    # Save
    can_overwrite = safe_overwrite(HISTORY_FILE)
    if not can_overwrite:
        print("ℹ️ Target file may be open/locked; will write a NEW copy instead.")
    _save_atomic_xlsx(out[final_cols], HISTORY_FILE)

    print(f"✅ Customer history updated. Added: {appended} | Replaced: {replaced} | Skipped: {skipped} | New IDs: {new_ids} | Total rows: {len(out)}")

if __name__ == "__main__":
    update_customer_history()
