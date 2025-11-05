# app/figurella_reports/services/contracts_history.py
import os, tempfile, shutil
from datetime import datetime
from typing import List
import pandas as pd
import pytz

from .export_excel import safe_overwrite

TODAY_FILE   = "contracts.xlsx"           # merged workbook with sheets: contracts, sales
HISTORY_FILE = "contracts_history.xlsx"
ADDED_AT_COL = "addedAt"

SIGNATURE_COLS: List[str] = [
    "contractId", "centerCode", "customerId", "assistantId",
    "startDate", "endDate",
    "totalAmount", "salesAmountSum", "mergedTotal", "amountMismatch",
    "saleIds", "productNames", "salesCount", "tryCount", "tryAmount",
    "discountAmmount", "subscriptionAmmount",
    "statusId", "statusString", "isExpired", "isEditable", "isTry",
]

def _now_est_isooffset() -> str:
    est = pytz.timezone("America/New_York")
    dt  = datetime.now(est)
    offset = dt.strftime("%z")
    offset = offset[:3] + ":" + offset[3:] if offset and len(offset) == 5 else offset
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset

def _read_today_contracts_sheet() -> pd.DataFrame:
    if not os.path.exists(TODAY_FILE):
        raise FileNotFoundError(f"❌ {TODAY_FILE} not found. Run contracts sync first.")
    try:
        df = pd.read_excel(TODAY_FILE, sheet_name="contracts")
    except Exception:
        df = pd.read_excel(TODAY_FILE)
    return df

def _read_history() -> pd.DataFrame:
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame()
    try:
        return pd.read_excel(HISTORY_FILE)
    except Exception:
        return pd.DataFrame()

def _align_union_columns(today: pd.DataFrame, hist: pd.DataFrame) -> List[str]:
    cols = [c for c in SIGNATURE_COLS if c in today.columns or c in hist.columns]
    def _append_missing(src):
        for c in src.columns:
            if c not in cols and c != ADDED_AT_COL:
                cols.append(c)
    if not today.empty: _append_missing(today)
    if not hist.empty:  _append_missing(hist)
    if ADDED_AT_COL not in cols:
        cols.append(ADDED_AT_COL)
    return cols

# ───────────────────── Normalization ─────────────────────

def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")

def _to_num_2(series: pd.Series) -> pd.Series:
    s = _to_num(series)
    return s.round(2)

def _to_bool_text(series: pd.Series) -> pd.Series:
    s = pd.Series(series).fillna(False)
    s = s.map(lambda v: str(v).strip().lower() in ("1","true","t","yes","y"))
    return s.map(lambda b: "TRUE" if b else "FALSE")

def _to_upper_trim(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()

def _to_text_trim(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()

def _to_dt_string(series: pd.Series) -> pd.Series:
    s = pd.to_datetime(series, errors="coerce", utc=False)
    return s.dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")

def _normalize_for_signature(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for c in SIGNATURE_COLS:
        if c not in df.columns:
            out[c] = ""
            continue
        col = df[c]
        if c in ("centerCode",):
            out[c] = _to_upper_trim(col)
        elif c in ("statusString","saleIds","productNames","assistantId"):
            out[c] = _to_text_trim(col)
        elif c in ("startDate","endDate"):
            out[c] = _to_dt_string(col)
        elif c in ("isExpired","isEditable","isTry","amountMismatch"):
            out[c] = _to_bool_text(col)
        elif c in ("totalAmount","salesAmountSum","mergedTotal","tryAmount","discountAmmount","subscriptionAmmount"):
            out[c] = _to_num_2(col)
        elif c in ("contractId","customerId","statusId","salesCount","tryCount"):
            out[c] = _to_num(col).fillna(pd.NA)
        else:
            out[c] = _to_text_trim(col)
    return out

def _build_sig_key(df_norm: pd.DataFrame) -> pd.Series:
    cols = [c for c in SIGNATURE_COLS if c in df_norm.columns]
    return df_norm[cols].apply(lambda r: tuple(r.values.tolist()), axis=1)

# ───────────────────── Save ─────────────────────

def _save_atomic_xlsx(df: pd.DataFrame, path: str):
    fd, tmp = tempfile.mkstemp(suffix=".xlsx", prefix="contracts_history_")
    os.close(fd)
    try:
        df.to_excel(tmp, index=False)
        try:
            os.replace(tmp, path)
        except PermissionError:
            alt = f"{os.path.splitext(path)[0]}_NEW_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
            shutil.move(tmp, alt)
            print(f"⚠️ File locked. Saved new copy as: {alt}")
            return
        print(f"📘 Saved to: {path}")
    finally:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except Exception: pass

# ───────────────────── Main ─────────────────────

def update_contracts_history():
    print("🔄 Updating contracts history (dedupe on ALL provided header fields)…")
    today_raw = _read_today_contracts_sheet()
    if today_raw.empty:
        print("ℹ️ contracts.xlsx is empty; nothing to append.")
        return

    hist_raw = _read_history()
    now_est = _now_est_isooffset()

    if hist_raw.empty:
        hist_raw = pd.DataFrame(columns=list(today_raw.columns) + [ADDED_AT_COL])

    if ADDED_AT_COL not in hist_raw.columns:
        hist_raw[ADDED_AT_COL] = ""

    # Fill timestamp for new rows only
    today_raw[ADDED_AT_COL] = now_est

    final_cols = _align_union_columns(today_raw, hist_raw)
    today = today_raw.reindex(columns=final_cols)
    hist  = hist_raw.reindex(columns=final_cols)

    before_rows = len(hist)

    combined = pd.concat([hist, today], ignore_index=True)
    norm_view = _normalize_for_signature(combined)
    sig_key = _build_sig_key(norm_view)
    keep_mask = ~sig_key.duplicated(keep="first")

    deduped = combined.loc[keep_mask].reset_index(drop=True)

    added_rows = len(deduped) - before_rows
    skipped_rows = len(today) - added_rows
    print(f"✅ Added rows: {added_rows} | Skipped identical: {skipped_rows} | Total history: {len(deduped)}")

    if not safe_overwrite(HISTORY_FILE):
        print("ℹ️ Target file may be open/locked; will write a NEW copy instead.")
    _save_atomic_xlsx(deduped[final_cols], HISTORY_FILE)

if __name__ == "__main__":
    update_contracts_history()
