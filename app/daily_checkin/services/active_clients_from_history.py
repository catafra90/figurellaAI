from __future__ import annotations
import os, calendar, re
from pathlib import Path
from datetime import datetime
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype as is_dt

MONTH_ABBR = list(calendar.month_abbr)[1:]  # ["Jan", ..., "Dec"]

def first_present(cols, choices):
    for c in choices:
        if c in cols:
            return c
    return None

def _norm_id(val) -> str:
    """
    Normalize IDs from Excel to a comparable string key.
    Examples:
      208933.0   -> "208933"
      "208933"   -> "208933"
      "208933.0" -> "208933"
      " 20,8933 "-> "208933"
      "'208933"  -> "208933"
    Falls back to digits-only extraction if needed.
    """
    if pd.isna(val):
        return ""
    s = str(val).strip().replace(",", "")
    m = re.fullmatch(r"(\d+)(?:\.0+)?", s)
    if m:
        return m.group(1)
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except Exception:
        pass
    return re.sub(r"\D", "", s)

def resolve_agenda_history_path(app_root: Path, instance_dir: Path) -> Path | None:
    env = os.getenv("AGENDA_HISTORY_XLSX")
    if env:
        p = Path(env)
        if not p.is_absolute():
            p = app_root / p
        if p.exists():
            return p
    for p in [
        app_root / "agenda_history.xlsx",
        app_root / "history_agenda.xlsx",
        instance_dir / "agenda_history.xlsx",
        instance_dir / "history_agenda.xlsx",
    ]:
        if p.exists():
            return p
    return None

def resolve_customers_history_path(app_root: Path, instance_dir: Path) -> Path | None:
    env = os.getenv("CUSTOMERS_HISTORY_XLSX")
    if env:
        p = Path(env)
        if not p.is_absolute():
            p = app_root / p
        if p.exists():
            return p
    for p in [
        app_root / "customers_history.xlsx",
        app_root / "history_customers.xlsx",
        instance_dir / "customers_history.xlsx",
        instance_dir / "history_customers.xlsx",
    ]:
        if p.exists():
            return p
    return None

def _load_customer_name_map(app_root: Path, instance_dir: Path) -> dict[str, str]:
    """Build { id -> 'name surname' } from customers_history.xlsx (id, name, surname)."""
    path = resolve_customers_history_path(app_root, instance_dir)
    if not path:
        return {}
    try:
        df = pd.read_excel(path, dtype={"id": object, "name": object, "surname": object})
    except Exception:
        return {}
    if "id" not in df.columns:
        return {}
    name_col = first_present(df.columns, ["name", "Name"])
    surn_col = first_present(df.columns, ["surname", "Surname", "lastName", "last_name"])
    df["_id_str"] = df["id"].map(_norm_id)
    if name_col and surn_col:
        df["_full"] = (df[name_col].fillna("").astype(str).str.strip() + " " +
                       df[surn_col].fillna("").astype(str).str.strip()).str.strip()
    elif name_col:
        df["_full"] = df[name_col].fillna("").astype(str).str.strip()
    else:
        return {}
    df = df[(df["_id_str"] != "") & (df["_full"] != "")]
    return df.drop_duplicates("_id_str").set_index("_id_str")["_full"].to_dict()

def build_active_clients_payload(year: int, app_root: Path, instance_dir: Path) -> dict:
    """
    Build payload for Active Clients UI using agenda_history + customers_history.
    """
    agenda_path = resolve_agenda_history_path(app_root, instance_dir)
    if not agenda_path:
        return {"ok": False, "error": "agenda_history.xlsx/history_agenda.xlsx not found"}

    try:
        df = pd.read_excel(agenda_path)
    except Exception as e:
        return {"ok": False, "error": f"Failed reading {agenda_path}: {e}"}

    date_col   = first_present(df.columns, [
        "appointmentDate","appointment_date","start_at","startAt","start_date","StartDate","date","Date"
    ])
    status_col = first_present(df.columns, [
        "statusString","status_string","status","Status","StatusString","appointment_status"
    ])
    id_col     = first_present(df.columns, [
        "customerId","customer_id","customerID","CustomerId","CustomerID"
    ])
    name_col   = first_present(df.columns, [
        "customer_name","customerName","name","Name","customer_full_name","customerFullName"
    ])
    if not date_col:
        return {"ok": False, "error": "No appointment date column found in agenda history."}

    if not is_dt(df[date_col]):
        df["_dt"] = pd.to_datetime(df[date_col], errors="coerce")
    else:
        df["_dt"] = df[date_col]
    df = df.dropna(subset=["_dt"])
    df = df[df["_dt"].dt.year == year]

    if not status_col:
        return {"ok": True, "year": year, "from": None, "to": None,
                "months": {a: 0 for a in MONTH_ABBR},
                "clients": {a: [] for a in MONTH_ABBR}}

    norm_status = (df[status_col].astype(str).str.strip().str.replace(r"\s+", " ", regex=True).str.casefold())
    df_ok = df[norm_status.isin({"ok"})].copy()

    if id_col:
        df_ok["_cid"] = df_ok[id_col].map(_norm_id)
    else:
        df_ok["_cid"] = ""

    id_to_name = _load_customer_name_map(app_root, instance_dir)

    # Prefer agenda name → else customers_history full name → else raw id
    if name_col:
        disp = df_ok[name_col].astype(str).str.strip()
        disp = disp.where(disp != "", df_ok["_cid"])
    else:
        disp = df_ok["_cid"]
    df_ok["_display"] = disp.map(lambda x: id_to_name.get(x, x))

    df_ok["_m"] = df_ok["_dt"].dt.month
    grp = (df_ok.groupby(["_m", "_display"], as_index=False)
               .size().rename(columns={"size": "sessions"}))

    months  = {abbr: 0 for abbr in MONTH_ABBR}
    clients = {abbr: [] for abbr in MONTH_ABBR}
    for m in range(1, 13):
        abbr = calendar.month_abbr[m]
        g = grp[grp["_m"] == m]
        if not g.empty:
            months[abbr]  = int(g["_display"].nunique())
            clients[abbr] = (g.sort_values("_display")
                               .rename(columns={"_display": "name"})
                               [["name", "sessions"]]
                               .to_dict(orient="records"))

    dt_from = df_ok["_dt"].min().date().isoformat() if not df_ok.empty else None
    dt_to   = df_ok["_dt"].max().date().isoformat() if not df_ok.empty else None

    return {"ok": True, "year": year, "from": dt_from, "to": dt_to,
            "months": months, "clients": clients}
