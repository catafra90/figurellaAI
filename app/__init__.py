# File: app/__init__.py

import os
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, session, redirect, request, url_for, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix

# Optional: load .env if present (DEV convenience)
try:
    from dotenv import load_dotenv  # pip install python-dotenv
    load_dotenv()
except Exception:
    pass

# ─── Database objects ────────────────────────────────────────────────
db = SQLAlchemy()
migrate = Migrate()

# ─── Import models so Migrate/CLI sees them ──────────────────────────
import app.models  # noqa: F401


def create_app() -> Flask:
    """Application factory: create and configure the Flask app."""
    app = Flask(__name__, instance_relative_config=False)

    # ─── Base config ─────────────────────────────────────────────────
    from config import Config
    app.config.from_object(Config)

    # Sessions / security
    app.config.setdefault("SECRET_KEY", os.getenv("FLASK_SECRET_KEY", "Figurella2025"))

    # Flask/SQLAlchemy niceties
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    app.config.setdefault("TEMPLATES_AUTO_RELOAD", True)

    # 🔒 SAVE-GATE: keep the database connected, but disable *all writes* for now.
    # Flip to True later when you're ready to re-enable saving.
    app.config.setdefault("ENABLE_SAVES", False)

    # Debug flag (you can override via env FLASK_DEBUG=1)
    app.debug = bool(os.getenv("FLASK_DEBUG", "1") == "1")

    # ─── Proxies (Render/NGINX) ──────────────────────────────────────
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # ─── Init database & migrations ──────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)

    # ─── Jinja filters & globals ─────────────────────────────────────
    from app.utils.jinja_filters import register_jinja_filters
    register_jinja_filters(app)

    # Make workout blocks available in templates if you want to call {{ get_blocks() }}
    try:
        from app.charts.blocks import get_blocks
        app.jinja_env.globals["get_blocks"] = get_blocks
    except Exception:
        # Non-fatal: templates can still receive blocks via context (blocks_json) or via API
        pass

    # ─── Blueprints ─────────────────────────────────────────────────
    # Auth FIRST so that /auth/login is available before the login guard runs
    from app.auth.routes import bp as auth_bp
    app.register_blueprint(auth_bp)  # url_prefix="/auth"

    from app.home.routes                  import home_bp
    from app.clients.routes               import clients_bp
    from app.daily_checkin.routes         import daily_checkin_bp
    from app.charts.routes                import charts_bp
    from app.figurella_reports.routes     import (
        reports_bp as figurella_reports_bp,
        register_sub_blueprints,   # <-- ensure sub-BPs mount
    )
    from app.ai_assistant.routes          import ai_bp as legacy_ai_bp
    from app.ai_assistant.umbrella        import umbrella_bp
    from app.calendar.routes              import calendar_bp
    from app.franchisor.routes            import franchisor_bp
    from app.nutrition.routes             import bp as nutrition_bp  # ← Nutrition
    from app.profile.routes               import bp as profile_bp    # ← Profile

    # ✅ NEW: Consultation
    from app.consultation.routes          import consultation_bp

    # ✅ NEW: Simple reports endpoint for /reports/<name>
    #    (This avoids 404 when clicking names in your Consultation “Added Contacts” list.)
    try:
        from app.reports.routes           import reports_bp as simple_reports_bp
    except Exception:
        simple_reports_bp = None

    # Register blueprints
    app.register_blueprint(home_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(daily_checkin_bp, url_prefix="/daily-check-in")
    app.register_blueprint(charts_bp)  # charts_bp already defines its own prefix (/charts)

    # IMPORTANT: reports_bp already carries url_prefix="/figurella-reports"
    app.register_blueprint(figurella_reports_bp)
    # Mount sub-blueprints (agenda, contracts, last-session, payments-*, pip, customer-acquisitions)
    register_sub_blueprints(app)

    app.register_blueprint(legacy_ai_bp,  url_prefix="/ai")
    app.register_blueprint(umbrella_bp,   url_prefix="/ai/assistant")
    app.register_blueprint(calendar_bp,   url_prefix="/calendar")
    app.register_blueprint(franchisor_bp, url_prefix="/franchisor")

    # Sections with prefixes defined inside their BPs
    app.register_blueprint(nutrition_bp)  # "/nutrition"
    app.register_blueprint(profile_bp)    # "/profile"

    # ✅ Register Consultation (url_prefix="/consultation" defined in its BP)
    app.register_blueprint(consultation_bp)

    # ✅ Register simple /reports if available
    if simple_reports_bp is not None:
        # NOTE: simple_reports_bp defines its own url_prefix="/reports" in app/reports/routes.py
        app.register_blueprint(simple_reports_bp)

    # ─── Login guard & template helpers ──────────────────────────────
    @app.before_request
    def _require_login():
        """
        Require login for all routes except:
          - static files
          - /auth/* (login/logout)
          - simple health checks if you add them later (e.g., /healthz)
        """
        # Allow static and auth endpoints
        if request.endpoint in ("static",) or request.blueprint == "auth":
            return

        # Allow favicon, robots, etc., without session noise
        if request.path in ("/favicon.ico", "/robots.txt"):
            return

        # Not logged in? Redirect to login, preserving 'next'
        if not session.get("user"):
            return redirect(url_for("auth.login", next=request.url))

    @app.context_processor
    def inject_current_user():
        """
        Make `current_user` available to all templates.
        Example usage in base.html:
           {% if current_user %} {{ current_user.name }} {% endif %}
        """
        return {"current_user": session.get("user")}

    # ─── Simple JSON error handler ──────────────────────────────────
    @app.errorhandler(Exception)
    def _json_errors(e):
        status = getattr(e, "code", 500)
        if app.debug:
            return jsonify(ok=False, error=str(e), type=e.__class__.__name__), status
        return jsonify(ok=False, error="Server error"), status

    # ─── Debug: dump registered routes on startup ───────────────────
    with app.app_context():
        print("\n📦 Registered Routes:")
        for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
            print(f"🔗 {rule.endpoint:30} → {rule.rule}")
        print(f"🔒 ENABLE_SAVES = {app.config.get('ENABLE_SAVES')}\n")

    return app


# ─── Exporter: DB → Excel copy (NO-OP while saves disabled) ─────────
import pandas as pd
from app.models import ChartEntry

# Optional centralized gate; if you already added app/common/save_gate.py, you can import saves_enabled from there.
def _saves_enabled() -> bool:
    try:
        cfg = getattr(current_app, "config", {}) or {}
        flag = cfg.get("ENABLE_SAVES")
        if flag is not None:
            return bool(flag)
    except Exception:
        pass
    # fallback to env if no app context; default False during refactor
    return os.getenv("ENABLE_SAVES", "0") in ("1", "true", "True")


def export_client_charts_to_excel(client: str, excel_path: str, tabs=None) -> str:
    """
    Query ChartEntry for each sheet and write an .xlsx with one tab per sheet.
    ⚠️ While ENABLE_SAVES is False, this function becomes a NO-OP and returns the
       given path without writing any file to disk.
    """
    from flask import has_app_context

    def _do_export():
        # 🔒 SAVE-GATE: do not write files while saves are disabled
        if not _saves_enabled():
            # Intentionally skip any file system writes.
            # Return the path so callers don't break; they should handle absence if needed.
            if has_app_context():
                try:
                    current_app.logger.info(
                        f"[export_client_charts_to_excel] Skipped writing '{excel_path}' (saves disabled)."
                    )
                except Exception:
                    pass
            return excel_path

        nonlocal tabs
        if tabs is None:
            from app.charts.routes import EXPECTED_TABS
            tabs = EXPECTED_TABS

        os.makedirs(os.path.dirname(os.path.abspath(excel_path)), exist_ok=True)

        wrote_any = False
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            for tab in tabs:
                records = (
                    ChartEntry.query
                    .filter_by(client_name=client, sheet=tab)
                    .order_by(ChartEntry.created_at)
                    .all()
                )
                if not records:
                    continue
                df = pd.DataFrame([r.data or {} for r in records])
                if df.empty:
                    df = pd.DataFrame([{}])
                df.to_excel(writer, sheet_name=str(tab).capitalize(), index=False)
                wrote_any = True

        if not wrote_any:
            with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
                pd.DataFrame(
                    [{"info": f"No data for client '{client}' as of {datetime.utcnow().isoformat()}Z"}]
                ).to_excel(writer, sheet_name="Info", index=False)

        return excel_path

    if has_app_context():
        return _do_export()
    else:
        app = create_app()
        with app.app_context():
            return _do_export()
