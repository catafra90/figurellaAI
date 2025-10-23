# app/reports/routes.py
from flask import Blueprint, render_template

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

@reports_bp.route("/<path:name>")
def client_report(name: str):
    """
    Minimal client report page to avoid 404s.
    Later you can replace this with a real lookup (Excel/DB) and render details.
    """
    # You could normalize `name` here, then query your data source.
    return render_template("reports/client_report.html", client_name=name)
