from __future__ import annotations
from flask import Blueprint, jsonify, request, render_template, flash
import pandas as pd

from ..io.loader import load_df
from ..services.base import drop_total_col

bp = Blueprint("payments_due_bp", __name__)  # url_prefix set in app factory


# ---------- helpers ----------
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
         .str.replace(r"[^\d,.\-]", "", regex=True)
         .str.replace(r"(?<=\d)[,](?=\d{3}\b)", "", regex=True)
    )
    normalized = stripped.apply(
        lambda x: x.replace(".", "").replace(",", ".") if ("," in x and "." not in x) else x.replace(",", "")
    )
    return pd.to_numeric(normalized, errors="coerce")


# ---------- views ----------
@bp.get("/history/view")
def view_history():
    df = _safe_df(load_df("payments_due"))
    if df.empty:
        flash("No rows found for 'Payments Due'.", "warning")
        cols, rows = [], []
    else:
        try:
            df = drop_total_col(df)
        except Exception:
            pass
        cols, rows = df.columns.tolist(), df.fillna("").values.tolist()

    return render_template(
        "figurella_reports/history_view.html",
        report_name="Payments Due",
        columns=cols,
        data=rows,
    )


@bp.get("/total")
def total_due():
    """
    Sum of Payments DUE for the given year & month.
    Query: ?year=YYYY&month=M
    """
    try:
        y = int(request.args.get("year", "0"))
        m = int(request.args.get("month", "0"))
    except Exception:
        y = m = 0

    df = _safe_df(load_df("payments_due"))
    if df.empty:
        return jsonify({"total": 0.0})

    date_col = _pick(df, "Due date", "Scadenza", "Date", "Data")
    amt_col  = _pick(df, "Amount", "Importo", "Totale", "Total", "Balance")
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
