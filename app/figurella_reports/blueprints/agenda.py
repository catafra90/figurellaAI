from flask import Blueprint, render_template, flash
from ..io.loader import load_df
from ..services.base import drop_total_col

bp = Blueprint("agenda_bp", __name__)

@bp.get("/history/view")
def view_history():
    df = load_df("agenda")
    df = drop_total_col(df)
    if df.empty:
        flash("No rows found for 'Agenda'.", "warning")
        cols, rows = [], []
    else:
        cols, rows = df.columns.tolist(), df.fillna("").values.tolist()
    return render_template("figurella_reports/history_view.html",
                           report_name="Agenda", columns=cols, data=rows)
