# app/figurella_reports/blueprints/last_session.py
from flask import Blueprint, render_template, flash, jsonify
from ..services.last_session_service import prepare_last_session_view
import pandas as pd
from datetime import datetime

bp = Blueprint("last_session_bp", __name__)
# If you register prefix in create_app(), keep this as-is:
# app.register_blueprint(last_session_bp, url_prefix="/figurella-reports/last-session")

@bp.get("/history/view")
def view_history():
    """
    Display ALL Last Session rows exactly as stored (no filters, no sorting).
    """
    result = prepare_last_session_view()
    for category, message in result.get("messages", []):
        flash(message, category)

    return render_template(
        "figurella_reports/history_view.html",
        report_name="Last Session",
        columns=result["columns"],
        data=result["rows"],
    )

@bp.get("/expiring-month.json")
def expiring_month_json():
    """
    Debug endpoint: shows who has 'Fine contratto' in the current month.
    Useful to verify date parsing independently of the PINK filter.
    """
    # Prepare view data (columns + rows), then rebuild as DataFrame.
    result = prepare_last_session_view()
    cols = result.get("columns", [])
    rows = result.get("rows", [])
    df = pd.DataFrame(rows, columns=cols)

    # Find expiration column name
    exp_candidates = ["Fine contratto", "Fine contratto/End of contract", "Contract End", "End date"]
    exp_col = next((c for c in exp_candidates if c in df.columns), None)
    if not exp_col:
        return jsonify({"items": []})

    dates = pd.to_datetime(df[exp_col], errors="coerce", infer_datetime_format=True)
    now = datetime.today()
    mfilter = (dates.dt.year == now.year) & (dates.dt.month == now.month)
    df2 = df.loc[mfilter].copy()

    name_col = next((c for c in ["Name", "Nome"] if c in df2.columns), None)
    sur_col = next((c for c in ["Surname", "Cognome"] if c in df2.columns), None)

    out = []
    for _, r in df2.iterrows():
        out.append({
            "name": str(r.get(name_col, "")) if name_col else "",
            "surname": str(r.get(sur_col, "")) if sur_col else "",
            "fine_contratto": (
                pd.to_datetime(r.get(exp_col), errors="coerce").date().isoformat()
                if r.get(exp_col) not in (None, "", "NaT") else None
            ),
        })
    return jsonify({"items": out})
