# app/figurella_reports/routes.py
from flask import Blueprint, render_template, current_app, redirect, url_for, request

# ---- Sub-blueprints (must exist as stubs or real modules) ----
from .blueprints.agenda import bp as agenda_bp
from .blueprints.contracts import bp as contracts_bp
from .blueprints.last_session import bp as last_session_bp
from .blueprints.payments_done import bp as payments_done_bp
from .blueprints.payments_due import bp as payments_due_bp
from .blueprints.pip import bp as pip_bp
from .blueprints.customer_acquisitions import bp as ca_bp
from .blueprints.ibf import bp as ibf_bp
from .blueprints.subscriptions import bp as subscriptions_bp  # ← ADDED

# ---- Cards/constants (with safe fallback) ----
try:
    from .blueprints.cards import REPORT_CARDS, HISTORY_FILES  # noqa: F401
except Exception:
    if current_app:
        try:
            current_app.logger.warning("[reports/routes] cards import failed; using fallback list")
        except Exception:
            pass
    REPORT_CARDS = [
        {"key": "agenda",                "label": "Agenda",                "icon": "bi-calendar"},
        {"key": "contracts",             "label": "Contracts",             "icon": "bi-pen"},
        {"key": "customer_acquisitions", "label": "Customer Acquisitions", "icon": "bi-people"},
        {"key": "ibf",                   "label": "IBF",                   "icon": "bi-percent"},
        {"key": "last_session",          "label": "Last Session",          "icon": "bi-calendar-check"},
        {"key": "payments_done",         "label": "Payments Done",         "icon": "bi-check-circle"},
        {"key": "payments_due",          "label": "Payments Due",          "icon": "bi-calendar-day"},
        {"key": "pip",                   "label": "PIP",                   "icon": "bi-bank"},
        {"key": "subscriptions",         "label": "Subscriptions",         "icon": "bi-calendar-event"},
    ]

# -----------------------------------------------------------------------------
# Root blueprint (kept very thin)
# -----------------------------------------------------------------------------
reports_bp = Blueprint(
    "reports_bp",
    __name__,
    url_prefix="/figurella-reports",
    template_folder="templates/figurella_reports",
)

@reports_bp.route("/reports")
def reports_home():
    """
    Renders the Reports Home with cards.
    If template or cards throw, we log and return a readable fallback instead of a 500.
    """
    try:
        return render_template("figurella_reports/reports_home.html", cards=REPORT_CARDS)
    except Exception as e:
        try:
            current_app.logger.exception("[reports_home] render failed: %s", e)
        except Exception:
            pass
        return (
            "<h2>Reports Home failed to render</h2>"
            "<p>Check server logs for details.</p>"
            f"<pre>{e}</pre>",
            500,
            {"Content-Type": "text/html"},
        )

# -----------------------------------------------------------------------------
# Backward-compatibility shim for old endpoint name
# Many pages used url_for('reports_bp.ibf_frequency'); the real endpoint now
# lives in the IBF blueprint. Keep this shim so old callers don't 500.
# -----------------------------------------------------------------------------
@reports_bp.get("/reports/IBF/frequency", endpoint="ibf_frequency")
def ibf_frequency_shim():
    # Preserve any query params and keep method (307 keeps POST if ever used)
    return redirect(url_for("ibf_bp.ibf_frequency", **request.args), code=307)

# -----------------------------------------------------------------------------
# Register sub-blueprints on the Flask app
# Call this from create_app() after creating app
# -----------------------------------------------------------------------------
def register_sub_blueprints(app):
    app.register_blueprint(agenda_bp,        url_prefix="/figurella-reports/agenda")
    app.register_blueprint(contracts_bp,     url_prefix="/figurella-reports/contracts")
    app.register_blueprint(last_session_bp,  url_prefix="/figurella-reports/last-session")
    app.register_blueprint(payments_done_bp, url_prefix="/figurella-reports/payments-done")
    app.register_blueprint(payments_due_bp,  url_prefix="/figurella-reports/payments-due")
    app.register_blueprint(pip_bp,           url_prefix="/figurella-reports/pip")
    app.register_blueprint(ca_bp,            url_prefix="/figurella-reports/customer-acquisitions")
    app.register_blueprint(ibf_bp,           url_prefix="/figurella-reports/ibf")
    app.register_blueprint(subscriptions_bp, url_prefix="/figurella-reports/subscriptions")
