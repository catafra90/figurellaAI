# app/figurella_reports/services/agenda_history.py
import os
import tempfile
import shutil
from datetime import datetime
from typing import List

import pandas as pd
import pytz

from .export_excel import safe_overwrite

TODAY_FILE   = "agenda.xlsx"
HISTORY_FILE = "agenda_history.xlsx"

# Exact identity/signature columns (ALL must match to consider a duplicate)
# NOTE: Use a single derived statusKey (from status OR statusString)
# IMPORTANT: isConsultation is intentionally NOT in the signature to avoid
#            noisy late corrections creating new rows.
SIGNATURE_COLS = [
    "appointmentId",
    "appointmentDate",
    "slotId",
    "startTime",
    "centerCode",
    "deviceId",
    # "isConsultation",  # removed from signature by design
    "customerId",
    "assistantId",
    "statusKey",       # derived, replaces 'status' + 'statusString'
]

ADDED_AT_COL = "addedAt"  # timestamp when a row was appended to history (EST with offset)

# ───────────────────────── helpers ─────────────────────────

def _dedupe_df_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.loc[:, ~df.columns.duplicated(keep="first")].copy()

def _coerce_appointment_date_series(s: pd.Series) -> pd.Series:
    if s is None or len(s) == 0:
        return pd.Series(dtype="datetime64[ns]")

    def coerce_one(v):
        if pd.isna(v):
            return pd.NaT
        if isinstance(v, (pd.Timestamp, datetime)):
            return pd.Timestamp(v)
        if isinstance(v, (int, float)):
            fv = float(v)
            if 20000 <= fv <= 80000:
                base = pd.Timestamp("1899-12-30")
                return base + pd.to_timedelta(fv, unit="D")
        try:
            txt = str(v).strip()
            if txt == "":
                return pd.NaT
            if txt.replace(".", "", 1).isdigit():
                fv = float(txt)
                if 20000 <= fv <= 80000:
                    base = pd.Timestamp("1899-12-30")
                    return base + pd.to_timedelta(fv, unit="D")
            return pd.to_datetime(txt, errors="coerce", utc=False)
        except Exception:
            return pd.NaT

    mapped = s.apply(coerce_one)
    return pd.to_datetime(mapped, errors="coerce")

def _read_xlsx_safe(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        df = pd.read_excel(path)
        if "appointmentDate" in df.columns:
            df["appointmentDate"] = _coerce_appointment_date_series(df["appointmentDate"])
        return _dedupe_df_columns(df)
    except Exception as e:
        print(f"⚠️ Failed to read {path}: {e}")
        return pd.DataFrame()

def _read_agenda_today() -> pd.DataFrame:
    if not os.path.exists(TODAY_FILE):
        raise FileNotFoundError(f"❌ {TODAY_FILE} not found. Run the agenda export first.")
    df = pd.read_excel(TODAY_FILE)
    if "appointmentDate" in df.columns:
        df["appointmentDate"] = _coerce_appointment_date_series(df["appointmentDate"])
    # Prefer to coerce isConsultation to explicit TRUE/FALSE/"" at read time
    if "isConsultation" in df.columns:
        df["isConsultation"] = _normalize_bool_series_tristate(df["isConsultation"])
    return _dedupe_df_columns(df)

def _align_union_columns(a: pd.DataFrame, b: pd.DataFrame):
    cols = list(a.columns)
    for c in b.columns:
        if c not in cols:
            cols.append(c)
    return cols, a.reindex(columns=cols), b.reindex(columns=cols)

def _save_atomic_xlsx(df: pd.DataFrame, path: str):
    fd, tmp_path = tempfile.mkstemp(suffix=".xlsx", prefix="agenda_history_")
    os.close(fd)
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

# Tri-state boolean: TRUE/FALSE/"" (unknown). Never default blanks to FALSE.
def _normalize_bool_series_tristate(s: pd.Series) -> pd.Series:
    def norm(v):
        if pd.isna(v):
            return ""
        sv = str(v).strip().lower()
        if sv in ("1","true","t","yes","y"): return "TRUE"
        if sv in ("0","false","f","no","n"): return "FALSE"
        return ""  # preserve unknowns/blanks
    return s.map(norm)

# NEW: derive a single statusKey from whichever is available
def _compute_status_key_inplace(df: pd.DataFrame):
    """
    statusKey := normalized 'status' if present, else normalized 'statusString'.
      - status      → numeric → integer-like string (e.g., 4.0/'4.0' → '4')
      - statusString→ trimmed UPPER text
      - missing both→ empty string
    """
    key = pd.Series([""] * len(df), index=df.index, dtype="object")

    if "status" in df.columns:
        s = pd.to_numeric(df["status"], errors="coerce")
        as_intlike = s.dropna().astype("Int64").astype(str)  # '4', '3', etc.
        fallback = df["status"].astype(str).str.strip()
        key = as_intlike.reindex(df.index).where(s.notna(), fallback)
        key = key.str.replace(r"\.0+$", "", regex=True)

    if "statusString" in df.columns:
        key = key.where(key.astype(str).str.len() > 0,
                        df["statusString"].astype(str).str.strip().str.upper())

    df["statusKey"] = key.fillna("")

def _normalize_signature_inplace(df: pd.DataFrame):
    """
    Normalize signature fields to stable string forms:
      - appointmentDate → 'YYYY-MM-DDT00:00:00Z'
      - startTime       → 'HH:MM'
      - centerCode      → uppercase, trimmed
      - IDs/text        → trimmed strings
      - statusKey       → trimmed string (already computed)
      - isConsultation  → tri-state TRUE/FALSE/'' (kept in data but not signature)
    """
    # Dates → ISO UTC midnight with Z
    if "appointmentDate" in df.columns:
        dt = _coerce_appointment_date_series(df["appointmentDate"])
        df["appointmentDate"] = dt.dt.strftime("%Y-%m-%dT00:00:00Z").fillna("")

    # Time → HH:MM
    if "startTime" in df.columns:
        t = pd.to_datetime(df["startTime"].astype(str).str.strip(), errors="coerce", utc=False)
        fallback = df["startTime"].astype(str).str.strip()
        df["startTime"] = t.dt.strftime("%H:%M").where(~t.isna(), fallback)

    # Tri-state for isConsultation (column retained, not in signature)
    if "isConsultation" in df.columns:
        df["isConsultation"] = _normalize_bool_series_tristate(df["isConsultation"])

    if "centerCode" in df.columns:
        df["centerCode"] = df["centerCode"].astype(str).str.strip().str.upper()

    for c in ["appointmentId", "slotId", "deviceId", "customerId", "assistantId", "statusKey"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()

def _drop_dupes_by_signature_keep_history_first(combined: pd.DataFrame) -> pd.DataFrame:
    return combined.drop_duplicates(subset=SIGNATURE_COLS, keep="first").reset_index(drop=True)

def _ensure_added_at_columns(history: pd.DataFrame, today: pd.DataFrame, now_est_iso: str):
    if ADDED_AT_COL not in history.columns:
        history[ADDED_AT_COL] = ""
    today[ADDED_AT_COL] = now_est_iso

def _now_est_isooffset() -> str:
    est = pytz.timezone("America/New_York")
    dt = datetime.now(est)
    offset = dt.strftime("%z")
    offset = offset[:3] + ":" + offset[3:] if offset and len(offset) == 5 else offset
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset

# ───────────────────────── main ─────────────────────────

def update_agenda_history():
    print("🔄 Updating agenda history with statusKey + tri-state isConsultation + addedAt (EST)…")

    # 1) Load today & existing history
    today   = _read_agenda_today()
    history = _read_xlsx_safe(HISTORY_FILE)

    # quick diagnostics
    if "isConsultation" in today.columns:
        vc = today["isConsultation"].astype(str).str.strip().str.upper().value_counts(dropna=False)
        print("[today] isConsultation counts:", dict(vc))

    # 2) Prepare addedAt (EST with offset) on 'today'
    now_est_iso = _now_est_isooffset()
    _ensure_added_at_columns(history, today, now_est_iso)

    # 3) Align to union of columns (no column loss)
    union_cols, today_aligned, hist_aligned = _align_union_columns(today, history)

    # 4) Concatenate HISTORY first, then TODAY
    combined = pd.concat([hist_aligned, today_aligned], ignore_index=True)

    # 4b) Ensure statusKey exists before normalization/dedupe
    _compute_status_key_inplace(combined)

    # 5) Normalize & de-duplicate by the signature (with statusKey)
    if all(c in combined.columns for c in SIGNATURE_COLS):
        _normalize_signature_inplace(combined)
        deduped = _drop_dupes_by_signature_keep_history_first(combined)
    else:
        missing = [c for c in SIGNATURE_COLS if c not in combined.columns]
        print(f"⚠️ Missing signature column(s) {missing}; skipping de-dup to avoid data loss.")
        deduped = combined

    # 6) Save atomically (write side copy if locked)
    can_overwrite = safe_overwrite(HISTORY_FILE)
    if not can_overwrite:
        print("ℹ️ Target file may be open/locked; will write a NEW copy instead.")
    _save_atomic_xlsx(deduped[union_cols], HISTORY_FILE)

if __name__ == "__main__":
    update_agenda_history()
