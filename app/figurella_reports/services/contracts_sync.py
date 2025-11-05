# app/figurella_reports/services/contracts_sync.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple
from datetime import datetime
import pandas as pd

from .api_client import fetch_contracts

CONTRACTS_XLSX = "contracts.xlsx"

# ───────────────── helpers ─────────────────

def _to_naive_utc(series: pd.Series) -> pd.Series:
    """
    Parse to datetime in UTC, then drop tz so Excel can write it.
    """
    s = pd.to_datetime(series, errors="coerce", utc=True)
    try:
        return s.dt.tz_convert("UTC").dt.tz_localize(None)
    except Exception:
        return s.dt.tz_localize(None) if hasattr(s.dt, "tz_localize") else s

def _normalize_contracts(rows: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Flatten API rows into:
      - df_contracts: one row per contract (sales removed)
      - df_sales: one row per sale with contractId + sale fields

    Adds per-contract aggregates (saleIds, productNames, tryCount, tryAmount,
    salesAmountSum, salesCount) and computes mergedTotal + amountMismatch.
    """
    if not rows:
        print("ℹ️ No contracts returned from API.")
        return pd.DataFrame(), pd.DataFrame()

    # peek keys
    sample_keys = set()
    for r in rows[:3]:
        sample_keys |= set(r.keys())
    print(f"🔎 Contract keys (sample): {sorted(sample_keys)}")

    contracts_out: List[Dict[str, Any]] = []
    sales_out: List[Dict[str, Any]] = []

    for r in rows:
        c = dict(r)
        sales = c.pop("sales", None)
        contracts_out.append(c)

        if isinstance(sales, list):
            for s in sales:
                row = dict(s)
                row["contractId"] = r.get("contractId")
                row["centerCode"] = row.get("centerCode") or r.get("centerCode")
                sales_out.append(row)

    df_contracts = pd.DataFrame(contracts_out)
    df_sales     = pd.DataFrame(sales_out)

    # Normalize contract datetimes/booleans
    for col in ("startDate", "endDate"):
        if col in df_contracts.columns:
            df_contracts[col] = _to_naive_utc(df_contracts[col])

    for col in ("isExpired", "isEditable", "isTry"):
        if col in df_contracts.columns:
            df_contracts[col] = df_contracts[col].astype("boolean")

    # Clean sales & build aggregates
    if not df_sales.empty:
        if "amount" in df_sales.columns:
            df_sales["amount"] = pd.to_numeric(df_sales["amount"], errors="coerce")
        if "isTry" in df_sales.columns:
            df_sales["isTry"] = df_sales["isTry"].astype("boolean")

        # Build text aggregates via agg on Series (avoids groupby.apply warning)
        def _join_unique(series: pd.Series) -> str:
            vals = [str(v) for v in series.dropna().astype(str).unique().tolist()]
            vals.sort()
            return ", ".join(vals)

        agg = df_sales.groupby("contractId", dropna=False).agg(
            saleIds=("saleId", lambda x: ",".join(str(v) for v in x.dropna().astype(str))),
            productNames=("productName", _join_unique),
            tryCount=("isTry", lambda x: int(pd.Series(x).fillna(False).sum()) if "isTry" in df_sales.columns else 0),
            tryAmount=("amount", lambda x: float(df_sales.loc[x.index][df_sales.loc[x.index, "isTry"] == True]["amount"].sum())
                       if "isTry" in df_sales.columns else 0.0),
            salesAmountSum=("amount", "sum"),
            salesCount=("amount", "size"),
        ).reset_index()

        df_contracts = df_contracts.merge(agg, on="contractId", how="left")
    else:
        for c in ("saleIds","productNames","tryCount","tryAmount","salesAmountSum","salesCount"):
            df_contracts[c] = pd.NA

    # merged total & mismatch
    has_total = "totalAmount" in df_contracts.columns
    if has_total:
        df_contracts["totalAmount"] = pd.to_numeric(df_contracts["totalAmount"], errors="coerce")
        df_contracts["mergedTotal"] = df_contracts["totalAmount"].where(
            ~df_contracts["totalAmount"].isna(),
            df_contracts["salesAmountSum"]
        )
    else:
        df_contracts["mergedTotal"] = df_contracts["salesAmountSum"]

    # Vectorized mismatch (Series vs Series) — no scalars in the expression
    ta = df_contracts["totalAmount"] if "totalAmount" in df_contracts.columns else pd.Series([pd.NA]*len(df_contracts))
    sa = df_contracts["salesAmountSum"]
    df_contracts["amountMismatch"] = (
        ta.notna() & sa.notna() & (ta.round(2) != sa.round(2))
    )

    # order columns
    preferred = [
        "$id", "contractId", "centerCode", "customerId", "assistantId",
        "startDate", "endDate",
        "totalAmount", "salesAmountSum", "mergedTotal", "amountMismatch",
        "saleIds", "productNames", "salesCount", "tryCount", "tryAmount",
        "discountAmmount", "subscriptionAmmount",
        "statusId", "statusString", "isExpired", "isEditable", "isTry",
    ]
    ordered = [c for c in preferred if c in df_contracts.columns] + \
              [c for c in df_contracts.columns if c not in preferred]
    df_contracts = df_contracts.reindex(columns=ordered)

    return df_contracts, df_sales

def _write_single_workbook(df_contracts: pd.DataFrame, df_sales: pd.DataFrame, path: str = CONTRACTS_XLSX) -> None:
    """
    Write ONE Excel file with:
      - Sheet 'contracts' (merged, one row per contract)
      - Sheet 'sales'     (raw sales detail)
    """
    with pd.ExcelWriter(path, engine="xlsxwriter", datetime_format="yyyy-mm-dd hh:mm:ss") as xw:
        df_contracts.to_excel(xw, sheet_name="contracts", index=False)
        if not df_sales.empty:
            df_sales.to_excel(xw, sheet_name="sales", index=False)
    print(f"📘 Saved Excel: {path} (contracts={len(df_contracts)} rows, sales={len(df_sales)} rows)")

# ───────────────── main ─────────────────

def sync_contracts_to_excel(frm: datetime, to: datetime):
    """
    Fetch contracts for [frm, to] and write a SINGLE workbook:
      - contracts.xlsx → Sheet 'contracts' (merged + aggregates)
                        Sheet 'sales'     (detail)
    """
    print(f"➡️  Contract/List {frm.isoformat()} → {to.isoformat()}")
    rows = fetch_contracts(frm, to)
    print(f"✅ Contracts returned: {len(rows)}")

    df_contracts, df_sales = _normalize_contracts(rows)

    # diagnostics
    if "amountMismatch" in df_contracts.columns:
        mm = df_contracts[df_contracts["amountMismatch"] == True]
        if not mm.empty:
            print("⚠️ Amount mismatches (contractId / totalAmount vs salesAmountSum):")
            print(mm[["contractId", "totalAmount", "salesAmountSum"]].to_string(index=False))
        else:
            print("✅ No amount mismatches between contract totals and sales sums.")

    _write_single_workbook(df_contracts, df_sales, CONTRACTS_XLSX)
