# app/figurella_reports/routes.py
from flask import Blueprint, render_template, current_app

# -----------------------------------------------------------------------------
# Reports root blueprint (kept minimal; no legacy report references)
# -----------------------------------------------------------------------------
reports_bp = Blueprint(
    "reports_bp",
    __name__,
    url_prefix="/figurella-reports",
    template_folder="templates/figurella_reports",
)

@reports_bp.route("/", methods=["GET"])
@reports_bp.route("/reports", methods=["GET"])
def reports_home():
    """
    Renders the Reports Home placeholder.
    We intentionally do NOT import or reference any historical reports.
    """
    try:
        # If your template expects 'cards', pass an empty list.
        return render_template("figurella_reports/reports_home.html", cards=[])
    except Exception as e:
        # Stay resilient: never 500 here.
        try:
            current_app.logger.exception("[reports_home] render failed: %s", e)
        except Exception:
            pass
        return (
            "<h2>Reports Home failed to render</h2>"
            "<p>The reports section was reset and no legacy reports remain.</p>"
            f"<pre>{e}</pre>",
            500,
            {"Content-Type": "text/html"},
        )

# -----------------------------------------------------------------------------
# Hook for adding NEW reports in the future
# (Leave as a no-op until you add new blueprints.)
# -----------------------------------------------------------------------------
def register_sub_blueprints(app):
    """Register new report blueprints here when you add them."""
    pass
