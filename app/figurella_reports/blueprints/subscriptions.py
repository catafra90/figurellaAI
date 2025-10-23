# app/figurella_reports/blueprints/subscriptions.py
from __future__ import annotations
from flask import Blueprint, render_template, flash, jsonify, request, current_app
import pandas as pd

from ..io.loader import load_df
from ..services.base import drop_total_col
from ..services.subscriptions_low_residual import find_low_residual_nonpink  # NEW

bp = Blueprint("subscriptions_bp", __name__)  # register with url_prefix="/figurella-reports/subscriptions"


# ------------------------- Helpers -------------------------

def _safe_df(x) -> pd.DataFrame:
    return x if isinstance(x, pd.DataFrame) else pd.DataFrame()


# ------------------------- Views -------------------------

@bp.get("/history/view")
def view_history():
    try:
        df = _safe_df(load_df("subscriptions"))
    except Exception as e:
        flash(f"Failed to load 'Subscriptions': {e}", "danger")
        df = pd.DataFrame()

    if df.empty:
        flash("No rows found for 'Subscriptions'.", "warning")
        cols, rows = [], []
    else:
        try:
            df = drop_total_col(df)
        except Exception:
            # if drop_total_col ever raises, keep df as-is
            pass
        cols, rows = df.columns.tolist(), df.fillna("").values.tolist()

    return render_template(
        "figurella_reports/history_view.html",
        report_name="Subscriptions",
        columns=cols,
        data=rows,
    )


# ------------------------- API -------------------------

@bp.get("/low-residual")
def low_residual():
    """
    API for Monthly Planning "Import Low Residual (<N)".
    Query: ?threshold=10
    Returns JSON with both keys for back-compat:
      { "items": [...], "clients": [...] }
    Each item: {full_name, name, surname, residual, last_contract, source}
    """
    try:
        th_raw = (request.args.get("threshold") or "10").strip()
        threshold = int(th_raw)
    except Exception:
        threshold = 10

    try:
        items = find_low_residual_nonpink(threshold=threshold)
        # return under both keys so existing JS (data.clients) and new code (data.items) both work
        return jsonify({"items": items, "clients": items})
    except Exception as e:
        if current_app:
            current_app.logger.exception("subscriptions.low_residual failed: %s", e)
        return jsonify({"items": [], "clients": [], "error": "internal_error"})
