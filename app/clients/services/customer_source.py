# app/clients/services/customer_source.py
from __future__ import annotations
import os
import pandas as pd

# Path to the API-backed customers history workbook
DEFAULT_HISTORY_XLSX = os.getenv("CUSTOMERS_HISTORY_XLSX", "customers_history.xlsx")

# Common column name variants
NAME_COLS   = ["name", "firstName", "first_name", "customerName", "Name"]
SURNAME_COLS = ["surname", "lastName", "last_name", "Surname"]
STATUS_COLS = ["statusString", "status", "Status"]
ID_COLS     = ["customerId", "id", "Customer ID"]
REG_COLS    = [
    "registrationDate", "registeredAt", "registered_at",
    "createdAt", "created_on", "addedAt", "added_at", "joined_at",
]

def _pick_col(cols: set[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in cols:
            return c
    return None

def load_latest_customers(xlsx_path: str | None = None) -> list[dict]:
    """
    Return latest row per customer (by timestamp if available) for the picker.
    Output: [{id, name, surname, registrationDate, status}, ...] sorted by surname then name.
    """
    xlsx = xlsx_path or DEFAULT_HISTORY_XLSX
    df = pd.read_excel(xlsx)

    cols = set(map(str, df.columns))

    id_col      = _pick_col(cols, ID_COLS) or list(cols)[0]
    name_col    = _pick_col(cols, NAME_COLS)
    surname_col = _pick_col(cols, SURNAME_COLS)
    status_col  = _pick_col(cols, STATUS_COLS)
    reg_col     = _pick_col(cols, REG_COLS)

    # Pick a timestamp column if present for "latest" logic
    ts_col = next((c for c in ["addedAt", "_ingested_at", "createdOn", "createdOn_est", "updatedAt"]
                   if c in cols), None)

    if ts_col:
        df = df.sort_values([id_col, ts_col]).drop_duplicates(subset=[id_col], keep="last")
    else:
        df = df.drop_duplicates(subset=[id_col], keep="first")

    # Build list for JSON output
    items = []
    for _, r in df.iterrows():
        items.append({
            "id":               str(r.get(id_col, "")),
            "name":             str(r.get(name_col, "")) if name_col else "",
            "surname":          str(r.get(surname_col, "")) if surname_col else "",
            "registrationDate": str(r.get(reg_col, "")) if reg_col else "",
            "status":           str(r.get(status_col, "")) if status_col else "",
        })

    # Sort by surname then name
    items.sort(key=lambda x: ((x["surname"] or "").lower(), (x["name"] or "").lower()))
    return items
