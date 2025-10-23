# app/profile/routes.py
from flask import Blueprint, render_template

bp = Blueprint("profile", __name__, url_prefix="/profile")

@bp.get("/profit")
def profit_sheet():
    """
    Owner-facing cost & profit worksheet (front-end calculations).
    Revenues are manual for now; later we can pipe from reports.
    """
    return render_template("profile/profit_sheet.html", title="Profit & Costs")
