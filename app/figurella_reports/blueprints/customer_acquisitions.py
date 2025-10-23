from flask import Blueprint, render_template, flash
from ..io.loader import load_df
from ..services.base import drop_total_col

bp = Blueprint("customer_acquisitions_bp", __name__)

@bp.get("/history/view")
def view_history():
    df = load_df("customer_acquisitions")
    df = drop_total_col(df)
    if df.empty:
        flash("No rows found for 'customer acquisitions'.", "warning")
        cols, rows = [], []
    else:
        cols, rows = df.columns.tolist(), df.fillna("").values.tolist()
    return render_template("figurella_reports/history_view.html",
                           report_name="customer acquisitions", columns=cols, data=rows)
