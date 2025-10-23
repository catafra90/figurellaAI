from __future__ import annotations
from flask import Blueprint, render_template, flash, jsonify, request, current_app
import pandas as pd

from ..io.loader import load_df
from ..services.base import drop_total_col
from ..services.expiring_pink import find_expiring_pink_clients  # NEW

bp = Blueprint("contracts_bp", __name__)  # register with url_prefix="/figurella-reports/contracts"


# ------------------------- Helpers -------------------------

def _safe_df(x) -> pd.DataFrame:
    """Return DataFrame if valid, else an empty DataFrame (avoids ambiguous truth-value)."""
    return x if isinstance(x, pd.DataFrame) else pd.DataFrame()

def _pick(df: pd.DataFrame, *cands: str) -> str | None:
    if df is None or df.empty:
        return None
    lower = {c.lower(): c for c in df.columns}
    for k in cands:
        if k.lower() in lower:
            return lower[k.lower()]
    return None

def _parse_money_series(s: pd.Series) -> pd.Series:
    if s is None:
        return pd.Series(dtype="float64")
    # Strip currency symbols and thousands; accept comma as decimal if no dot present
    stripped = (
        s.astype(str)
         .str.replace(r"[^\d,.\-]", "", regex=True)                 # keep digits, comma, dot, minus
         .str.replace(r"(?<=\d)[,](?=\d{3}\b)", "", regex=True)     # remove thousands comma
    )
    normalized = stripped.apply(
        lambda x: x.replace(".", "").replace(",", ".") if ("," in x and "." not in x) else x.replace(",", "")
    )
    return pd.to_numeric(normalized, errors="coerce")


# ------------------------- Routes -------------------------

@bp.get("/history/view")
def view_history():
    df = _safe_df(load_df("contracts"))
    if not df.empty and "Name" in df.columns:
        df = df[df["Name"].astype(str).str.lower() != "name"]

    # drop_total_col should gracefully handle empty; guard just in case
    try:
        df = drop_total_col(df)
    except Exception:
        pass

    if df is None or df.empty:
        flash("No rows found for 'Contracts'.", "warning")
        cols, rows = [], []
    else:
        cols, rows = df.columns.tolist(), df.fillna("").values.tolist()

    return render_template(
        "figurella_reports/history_view.html",
        report_name="Contracts",
        columns=cols,
        data=rows,
    )


@bp.get("/sales-total")
def sales_total():
    """
    Sum of contract 'Amount' for the given year & month (creation/start month).
    Query: ?year=YYYY&month=M
    Returns: {"total": <float>}
    """
    try:
        y = int(request.args.get("year", "0"))
        m = int(request.args.get("month", "0"))
    except Exception:
        y = m = 0

    df = _safe_df(load_df("contracts"))
    if df.empty:
        return jsonify({"total": 0.0})

    date_col = _pick(df, "Date", "Data", "Creation date", "Start", "Start date")
    amt_col  = _pick(df, "Amount", "Importo", "Totale", "Total", "Price")

    if amt_col is None:
        return jsonify({"total": 0.0})

    amounts = _parse_money_series(df[amt_col])

    if date_col:
        dates = pd.to_datetime(df[date_col], errors="coerce")

        if y and m:
            mask = (dates.dt.year == y) & (dates.dt.month == m)
            total = float(amounts[mask].sum(skipna=True))
        else:
            total = float(amounts.sum(skipna=True))
    else:
        total = float(amounts.sum(skipna=True))

    return jsonify({"total": round(total, 2)})


@bp.get("/expiring-pink.json")
def expiring_pink_json():
    """
    API for Monthly Planning 'Import Expiring PINK'.
    Returns: {"items": [{full_name, name, surname, fine_contratto, source}], "error": "...?"}
    """
    try:
        now_param = (request.args.get("now") or "").strip()
        now_dt = None
        if now_param:
            now_dt = pd.to_datetime(now_param, errors="raise").to_pydatetime()

        _, payload = find_expiring_pink_clients(now=now_dt)
        return jsonify({"items": payload})
    except Exception as e:
        # never 500 the UI; log server-side and return empty list
        if current_app:
            current_app.logger.exception("expiring_pink_json failed: %s", e)
        return jsonify({"items": [], "error": "internal_error"})


@bp.get("/sales-timeseries.json")
def sales_timeseries():
    """
    Monthly sales totals from Contracts.
    Query params (optional):
      - months: how many most-recent months to return (default 18)
      - start:  YYYY-MM (inclusive) to fix a start month instead of 'months'
      - end:    YYYY-MM (inclusive) to limit end month (default = latest in data)

    Returns: {"points":[{"month":"YYYY-MM","total": float}, ...]}
    """
    # --- params ---
    try:
        months = int(request.args.get("months", "18"))
    except Exception:
        months = 18

    start_ym = (request.args.get("start") or "").strip()
    end_ym   = (request.args.get("end") or "").strip()

    # --- load DF safely ---
    df = _safe_df(load_df("contracts"))
    if df.empty:
        return jsonify({"points": []})

    # --- pick columns robustly ---
    date_col = _pick(df, "Date", "Data", "Creation date", "Start", "Start date", "Contract Date")
    amt_col  = _pick(df, "Amount", "Importo", "Totale", "Total", "Price")

    if not amt_col:
        return jsonify({"points": []})

    # --- parse ---
    amounts = _parse_money_series(df[amt_col])
    if date_col:
        dates = pd.to_datetime(df[date_col], errors="coerce")
    else:
        # no date → nothing meaningful to chart
        return jsonify({"points": []})

    # --- build monthly frame ---
    m = pd.Series(pd.PeriodIndex(dates.dt.to_period("M"), name="month"))
    frame = pd.DataFrame({"month": m.astype("string"), "amount": amounts})
    frame = frame.dropna(subset=["month"])
    monthly = frame.groupby("month", as_index=False)["amount"].sum()

    # --- clip to range ---
    if end_ym:
        monthly = monthly[monthly["month"] <= end_ym]
    if start_ym:
        monthly = monthly[monthly["month"] >= start_ym]
    elif months and len(monthly) > months:
        monthly = monthly.tail(months)

    # --- shape ---
    points = [
        {"month": r["month"], "total": float(r["amount"] or 0.0)}
        for _, r in monthly.iterrows()
    ]
    return jsonify({"points": points})
