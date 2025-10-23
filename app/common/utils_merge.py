# app/common/utils_merge.py
import pandas as pd
from typing import List
from app.common.report_io import load_report_df, ensure_app_context
from app.common.utils import persist_report

# ... (normalize_cols, _normalize_pk_view stay the same)

def merge_into_history(report_key: str, new_df: pd.DataFrame, pk_cols: List[str]) -> int:
    # ---- normalize incoming ----
    if new_df is None:
        return 0
    if not isinstance(new_df, pd.DataFrame):
        new_df = pd.DataFrame(new_df)
    new_df = new_df.copy()
    if new_df.empty:
        return 0
    # faster, warning-free normalization
    obj_cols = new_df.select_dtypes(include=['object'])
    if not obj_cols.empty:
        new_df[obj_cols.columns] = obj_cols.apply(
            lambda s: s.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
        )

    # ---- load current (already opens ctx inside) ----
    cur = load_report_df(report_key)
    if cur is None or cur.empty:
        # first snapshot — just persist
        with ensure_app_context():
            persist_report({report_key.replace("_"," ").title(): new_df},
                           report_key=report_key,
                           to_db=True, to_static_excel=False, to_download_excel=False)
        return len(new_df)

    # normalize current
    cur = cur.copy()
    obj_cols = cur.select_dtypes(include=['object'])
    if not obj_cols.empty:
        cur[obj_cols.columns] = obj_cols.apply(
            lambda s: s.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
        )

    # ---- ensure PKs exist ----
    for c in pk_cols:
        if c not in new_df.columns: new_df[c] = ""
        if c not in cur.columns:    cur[c]    = ""

    # ---- column union & alignment ----
    all_cols = sorted(set(cur.columns) | set(new_df.columns))
    cur    = cur.reindex(columns=all_cols)
    new_df = new_df.reindex(columns=all_cols)

    # ---- composite key ----
    def _key(df: pd.DataFrame) -> pd.Series:
        parts = []
        for c in pk_cols:
            parts.append(df[c].astype(str).str.strip().str.replace(r"\s+"," ",regex=True).str.casefold())
        if not parts:
            return df.index.astype(str)
        k = parts[0]
        for s in parts[1:]:
            k = k.str.cat(s, sep="␞")
        return k

    cur["_key"]    = _key(cur)
    new_df["_key"] = _key(new_df)

    # ---- compute metrics BEFORE merge ----
    before_total   = len(cur)
    before_unique  = cur["_key"].nunique()
    dedup_removed  = before_total - before_unique

    cur_keys = set(cur["_key"].tolist())
    new_keys = set(new_df["_key"].tolist())

    added     = len(new_keys - cur_keys)   # brand new keys
    replaced  = len(new_keys & cur_keys)   # existing keys we overwrite with latest

    # ---- concat & keep last per key ----
    merged = pd.concat([cur, new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["_key"], keep="last").drop(columns=["_key"])

    # ---- persist under app context ----
    with ensure_app_context():
        persist_report({report_key.replace("_"," ").title(): merged},
                       report_key=report_key,
                       to_db=True, to_static_excel=False, to_download_excel=False)

    # Optional: lightweight console note (uncomment if you want this logged)
    # print(f"[merge_into_history:{report_key}] added={added}, replaced={replaced}, dedup_removed={dedup_removed}, final_rows={len(merged)}", flush=True)

    # Return non-negative “new/updated” count
    return added + replaced

