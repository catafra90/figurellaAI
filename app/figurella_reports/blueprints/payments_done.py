from __future__ import annotations
from flask import Blueprint, jsonify, request, render_template, flash
import pandas as pd
import re

from ..io.loader import load_df
from ..services.base import drop_total_col

bp = Blueprint("payments_done_bp", __name__)  # url_prefix set in app factory


# ------------------------- Helpers -------------------------

def _safe_df(x) -> pd.DataFrame:
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
    stripped = (
        s.astype(str)
         .str.replace(r"[^\d,.\-]", "", regex=True)                 # keep digits, comma, dot, minus
         .str.replace(r"(?<=\d)[,](?=\d{3}\b)", "", regex=True)     # remove thousands comma
    )
    normalized = stripped.apply(
        lambda x: x.replace(".", "").replace(",", ".") if ("," in x and "." not in x) else x.replace(",", "")
    )
    return pd.to_numeric(normalized, errors="coerce")


_DATE_IN_TEXT_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")

def _coerce_dates(df: pd.DataFrame) -> tuple[pd.Series | None, str]:
    """
    Return a datetime Series to use for month filtering and a short 'how' string.
    Preference order:
      1) Cash-in columns (actual payments done this month)
      2) Transaction/Generic date columns
      3) Date parsed from Details/Description (fallback)
    """
    # 1) Cash-In first (your requirement)
    cash_candidates = [
        "Cash In", "Cash in", "CashIn",
        "Data incasso", "Incasso", "Data incasso effettiva",
        "Received Date", "Paid Date"
    ]
    col = _pick(df, *cash_candidates)
    if col:
        return pd.to_datetime(df[col], errors="coerce"), f"cashin:{col}"

    # 2) Transaction/Generic date
    date_candidates = [
        "TxnDate", "Date", "Data", "Payment date", "Payment Date", "Day",
        "Data pagamento", "Data Pagamento", "Data Pag.", "Invoice Date", "Posting Date", "Expected"
    ]
    col = _pick(df, *date_candidates)
    if col:
        return pd.to_datetime(df[col], errors="coerce"), f"column:{col}"

    # 3) Fallback: first date string inside details/description
    det_col = _pick(df, "Details", "Dettagli", "Descrizione", "Description")
    if det_col:
        extracted = df[det_col].astype(str).str.extract(_DATE_IN_TEXT_RE, expand=False)
        return pd.to_datetime(extracted, errors="coerce"), f"details:{det_col}"

    return None, "none"


# ------------------------- Views -------------------------

@bp.get("/history/view")
def view_history():
    df = _safe_df(load_df("payments_done"))
    if df.empty:
        flash("No rows found for 'Payments Done'.", "warning")
        cols, rows = [], []
    else:
        try:
            df = drop_total_col(df)
        except Exception:
            pass
        cols, rows = df.columns.tolist(), df.fillna("").values.tolist()

    return render_template(
        "figurella_reports/history_view.html",
        report_name="Payments Done",
        columns=cols,
        data=rows,
    )


# ------------------------- API -------------------------

@bp.get("/total")
def total_done():
    """
    Sum of Payments Done for the given year & month.
    Uses **Cash In** date when available.
    Query: ?year=YYYY&month=M[&debug=1]
    Returns: {"total": <float>, plus debug fields when debug=1}
    """
    debug = (request.args.get("debug") == "1")
    try:
        y = int(request.args.get("year", "0"))
        m = int(request.args.get("month", "0"))
    except Exception:
        y = m = 0

    df = _safe_df(load_df("payments_done"))
    if df.empty:
        return jsonify({"total": 0.0, **({"reason": "empty_df"} if debug else {})})

    amt_col = _pick(df, "Amount", "Importo", "Totale", "Total", "Paid", "Pagamento", "Amount USD")
    if amt_col is None:
        return jsonify({"total": 0.0, **({"reason": "no_amount_col"} if debug else {})})

    amounts = _parse_money_series(df[amt_col])

    dates, how = _coerce_dates(df)
    if dates is not None and y and m:
        mask = (dates.dt.year == y) & (dates.dt.month == m)
        total = float(amounts[mask].sum(skipna=True))
        out = {"total": round(total, 2)}
        if debug:
            out.update({"used": how, "rows_matched": int(mask.sum())})
        return jsonify(out)

    # No dates available → sum all (debug tells you why)
    total = float(amounts.sum(skipna=True))
    out = {"total": round(total, 2)}
    if debug:
        out.update({"used": how, "rows_matched": None})
    return jsonify(out)
