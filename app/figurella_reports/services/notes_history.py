import os, tempfile, shutil, json
from datetime import datetime
import pandas as pd
import pytz

from .export_excel import safe_overwrite

ADDED_AT_COL = "addedAt"

def _now_est_isooffset() -> str:
    est = pytz.timezone("America/New_York")
    dt = datetime.now(est)
    offset = dt.strftime("%z")
    offset = offset[:3] + ":" + offset[3:] if offset and len(offset) == 5 else offset
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset

def _read_xlsx(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_excel(path)
    except Exception:
        return pd.DataFrame()

def _save_atomic_xlsx(df: pd.DataFrame, path: str):
    fd, tmp = tempfile.mkstemp(suffix=".xlsx", prefix="notes_history_")
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
        print(f"📘 Saved updated history: {path}")
    finally:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except Exception: pass

def _ensure_added_at(df: pd.DataFrame) -> pd.DataFrame:
    if ADDED_AT_COL not in df.columns:
        df = df.copy()
        df[ADDED_AT_COL] = ""
    return df

def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure schema we want to compare: drop raw 'createdOn' if present."""
    if "createdOn" in df.columns:
        df = df.drop(columns=["createdOn"])
    return df

def _to_sig_str(val) -> str:
    if pd.isna(val):
        return ""
    if isinstance(val, (pd.Timestamp, datetime)):
        try:
            if isinstance(val, pd.Timestamp):
                v = val
                if v.tzinfo is None:
                    v = v.tz_localize("UTC")
                return v.tz_convert("UTC").isoformat()
            return val.astimezone(pytz.UTC).isoformat()
        except Exception:
            return str(val)
    if isinstance(val, (dict, list)):
        try:
            return json.dumps(val, sort_keys=True, ensure_ascii=False)
        except Exception:
            return str(val)
    return str(val)

def _row_signatures(df: pd.DataFrame, cols: list[str]) -> list[str]:
    if not cols:
        return [""] * len(df)
    sigs: list[str] = []
    for i in df.index:
        parts = []
        for c in cols:
            parts.append(_to_sig_str(df.at[i, c]))
        sigs.append("|".join(parts))
    return sigs

def _id_customer_key_frame(df: pd.DataFrame) -> pd.Series | None:
    """Return a Series 'key' = id|customerId if both columns exist; else None."""
    if "id" in df.columns and "customerId" in df.columns:
        key = (
            df["id"].astype(object).where(pd.notna(df["id"]), "")
            .map(lambda x: str(x).strip())
            + "|"
            + df["customerId"].astype(object).where(pd.notna(df["customerId"]), "")
            .map(lambda x: str(x).strip())
        )
        return key
    return None

def update_notes_history(
    *,
    today_file: str = "customer_notes.xlsx",
    history_file: str = "customer_notes_history.xlsx",
) -> None:
    """
    Append NEW rows from today's file into history.
    Primary de-dupe: by (id, customerId). If either column is missing, fall back to
    comparing ALL columns except 'addedAt'.
    """
    print("🔄 Updating notes history...")

    today_df = _read_xlsx(today_file)
    if today_df.empty:
        print(f"❌ Missing or empty file: {today_file}")
        return

    hist_df = _read_xlsx(history_file)

    # Clean unwanted columns (drop raw createdOn)
    today_df = _clean_df(today_df)
    hist_df  = _clean_df(hist_df)

    # Ensure addedAt exists
    today_df = _ensure_added_at(today_df)
    hist_df  = _ensure_added_at(hist_df)

    # Stamp today's rows
    now = _now_est_isooffset()
    today_df = today_df.copy()
    today_df[ADDED_AT_COL] = now

    # ── Primary path: de-dupe by (id, customerId)
    key_today = _id_customer_key_frame(today_df)
    key_hist  = _id_customer_key_frame(hist_df)

    if key_today is not None and key_hist is not None:
        existing_keys = set(key_hist.tolist())
        mask_new = ~key_today.isin(existing_keys)
        new_rows = today_df.loc[mask_new].copy()

        before = len(hist_df)
        combined = pd.concat([hist_df, new_rows], ignore_index=True)
        added = len(combined) - before
        print(f"✅ {added} new note row(s) added (id+customerId unique). Total rows: {len(combined)}")

        if not safe_overwrite(history_file):
            print("ℹ️ Target file may be open/locked; will write a NEW copy instead.")
        _save_atomic_xlsx(combined, history_file)
        return

    # ── Fallback: compare all columns except 'addedAt'
    union_cols = list(dict.fromkeys(list(today_df.columns) + list(hist_df.columns)))
    today_aligned = today_df.reindex(columns=union_cols)
    hist_aligned  = hist_df.reindex(columns=union_cols)
    compare_cols = [c for c in union_cols if c != ADDED_AT_COL]

    if hist_aligned.empty:
        combined = today_aligned
        added = len(today_aligned)
        print(f"🆕 Creating new notes history from {today_file} ({added} rows).")
    else:
        sig_today = _row_signatures(today_aligned, compare_cols)
        sig_hist  = _row_signatures(hist_aligned,  compare_cols)
        existing = set(sig_hist)
        mask_new = [s not in existing for s in sig_today]
        new_rows = today_aligned.loc[mask_new].copy()
        before = len(hist_aligned)
        combined = pd.concat([hist_aligned, new_rows], ignore_index=True)
        added = len(combined) - before
        print(f"✅ {added} new note row(s) added (fallback signature). Total rows: {len(combined)}")

    if not safe_overwrite(history_file):
        print("ℹ️ Target file may be open/locked; will write a NEW copy instead.")
    _save_atomic_xlsx(combined, history_file)

if __name__ == "__main__":
    update_notes_history()
