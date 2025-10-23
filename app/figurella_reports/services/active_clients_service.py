# app/figurella_reports/services/active_clients_service.py
from __future__ import annotations
from datetime import datetime, date
from calendar import month_abbr
import re, math
import pandas as pd

from app.common.report_io import load_report_df as _load_report_df
from ..services.ibf_service import build_portal_wide  # keep using your existing wide builder

# -----------------------
# Constants / regex
# -----------------------
MONTHS = [m for m in month_abbr if m]  # ["Jan","Feb",...,"Dec"]
MONTH_HDR_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{4})\s*$")

# -----------------------
# Small helpers
# -----------------------
def empty_month_map() -> dict[str, int]:
    return {m: 0 for m in MONTHS}

def parse_yyyy_mm_dd(s: str | None) -> date | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m"):
        try:
            d = datetime.strptime(s, fmt)
            if fmt in ("%Y-%m", "%Y/%m"):
                d = d.replace(day=1)
            return d.date()
        except Exception:
            pass
    return None

def coerce_numeric(x) -> int:
    if pd.isna(x):
        return 0
    if isinstance(x, (int, float)):
        if isinstance(x, float) and math.isnan(x):
            return 0
        return int(x)
    try:
        s = str(x).strip().replace(",", "")
        return int(float(s)) if s else 0
    except Exception:
        return 0

# -----------------------
# IBF shaping
# -----------------------
def standardize_tidy_ibf(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize tidy IBF into columns: Date (datetime), Client (str), Sessions (int)
    Accepts Bubb/Bubble columns. If none, fallback to 1 per row.
    """
    cols_lower = {str(c).strip().lower(): c for c in df_raw.columns}
    client_col = (
        cols_lower.get("client")
        or cols_lower.get("cliente")
        or cols_lower.get("name")
        or list(df_raw.columns)[0]
    )
    date_col = cols_lower.get("date") or cols_lower.get("data")
    bubb_col = cols_lower.get("bubb") or cols_lower.get("bubble")

    df = df_raw.copy()
    df["Date"] = pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.NaT
    df["Client"] = df[client_col].astype(str).fillna("").str.strip()

    if bubb_col:
        df["Sessions"] = pd.to_numeric(df[bubb_col], errors="coerce").fillna(0).astype(int)
    else:
        df["Sessions"] = 1

    return df[["Date", "Client", "Sessions"]]

def melt_portal_wide(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Convert portal-wide IBF (Client | '1 - 2025' | '2 - 2025' | ...) into tidy rows:
      -> columns: [Date, Client, Sessions]
    """
    month_cols = []
    for c in df_raw.columns:
        m = MONTH_HDR_RE.match(str(c))
        if m:
            month_cols.append((c, int(m.group(2)), int(m.group(1))))
    if not month_cols:
        return pd.DataFrame(columns=["Date", "Client", "Sessions"])

    month_names = {c for (c, _, _) in month_cols}
    possible_client_cols = [c for c in df_raw.columns if c not in month_names]
    client_col = possible_client_cols[0] if possible_client_cols else df_raw.columns[0]

    rows = []
    for _, r in df_raw.iterrows():
        client = str(r[client_col]).strip()
        if not client:
            continue
        for c, yyyy, mm in month_cols:
            val = coerce_numeric(r[c])
            if val <= 0:
                continue
            rows.append({"Date": datetime(yyyy, mm, 1), "Client": client, "Sessions": val})

    if not rows:
        return pd.DataFrame(columns=["Date", "Client", "Sessions"])

    out = pd.DataFrame(rows)
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    return out

def build_month_summary(
    df: pd.DataFrame,
    start_d: date | None,
    end_d: date | None,
) -> tuple[dict[str, int], dict[str, list[dict]]]:
    """
    Input tidy df: Date (datetime), Client (str), Sessions (int)

    Returns:
      months_map:    { "Jan": active_client_count, ... }
      month_clients: { "Jan": [ {"name":..., "sessions":...}, ... ], ... }
    """
    if start_d:
        df = df[df["Date"] >= pd.Timestamp(start_d)]
    if end_d:
        df = df[df["Date"] < (pd.Timestamp(end_d) + pd.Timedelta(days=1))]

    df = df.copy()
    df["MonthKey"] = df["Date"].dt.month.map(
        lambda m: month_abbr[int(m)] if pd.notna(m) else None
    )

    agg = (
        df.groupby(["MonthKey", "Client"], dropna=True)["Sessions"]
        .sum()
        .reset_index()
    )

    months = empty_month_map()
    clients = {m: [] for m in MONTHS}

    if not agg.empty:
        for m in MONTHS:
            sub = agg[agg["MonthKey"] == m]
            sub = sub[sub["Sessions"] > 0]
            months[m] = int(sub["Client"].nunique())
            ranked = (
                sub.sort_values(["Sessions", "Client"], ascending=[False, True])
                .assign(name=lambda x: x["Client"], sessions=lambda x: x["Sessions"])
                [["name", "sessions"]]
                .to_dict(orient="records")
            )
            clients[m] = ranked

    return months, clients

# -----------------------
# Public service APIs
# -----------------------
def build_wide_view_context(from_ym: str | None, to_ym: str | None):
    """
    Returns (columns, rows) for the portal-wide grid view.
    """
    df = build_portal_wide(from_ym, to_ym)
    if df is None or df.empty:
        return [], []
    return df.columns.tolist(), df.fillna("").values.tolist()

def build_active_clients_payload(
    *,
    year: int | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """
    Load IBF dataframe (tidy or wide), normalize, and produce the JSON payload
    consumed by the Active Clients UI.
    """
    start_d = parse_yyyy_mm_dd(start)
    end_d   = parse_yyyy_mm_dd(end)

    if year is not None and not (start_d or end_d):
        try:
            y = int(year)
            start_d = date(y, 1, 1)
            end_d   = date(y, 12, 31)
        except Exception:
            pass

    payload = {
        "ok": True,
        "months": empty_month_map(),
        "clients": {m: [] for m in MONTHS},
        "from": start_d.isoformat() if start_d else "",
        "to":   end_d.isoformat() if end_d else "",
    }

    df_raw = _load_report_df("ibf")
    if df_raw is None or df_raw.empty:
        return payload

    cols_lower = {str(c).strip().lower() for c in df_raw.columns}
    has_tidy = (("date" in cols_lower) and ({"bubb", "bubble"} & cols_lower))
    tidy = standardize_tidy_ibf(df_raw) if has_tidy else melt_portal_wide(df_raw)
    if tidy.empty:
        return payload

    months, client_lists = build_month_summary(tidy, start_d, end_d)
    payload["months"]  = months
    payload["clients"] = client_lists
    return payload
