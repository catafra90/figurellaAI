# File: app/__init__.py

import os
from datetime import datetime
from flask import Flask, jsonify
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
    app.config.setdefault('SECRET_KEY', 'Figurella2025')
    app.config.setdefault('SQLALCHEMY_TRACK_MODIFICATIONS', False)
    app.config.setdefault('TEMPLATES_AUTO_RELOAD', True)

    # Debug flag (you can override via env FLASK_DEBUG=1)
    app.debug = bool(os.getenv('FLASK_DEBUG', '1') == '1')

    # ─── Proxies (Render/NGINX) ──────────────────────────────────────
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # ─── Init database & migrations ──────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)

    # ─── Jinja filters ──────────────────────────────────────────────
    from app.utils.jinja_filters import register_jinja_filters
    register_jinja_filters(app)

    # ─── Blueprints ─────────────────────────────────────────────────
    from app.home.routes              import home_bp
    from app.clients.routes           import clients_bp
    from app.daily_checkin.routes     import daily_checkin_bp
    from app.charts.routes            import charts_bp
    from app.figurella_reports.routes import reports_bp as figurella_reports_bp
    from app.ai_assistant.routes      import ai_bp as legacy_ai_bp
    from app.ai_assistant.umbrella    import umbrella_bp
    from app.calendar.routes          import calendar_bp
    from app.franchisor.routes        import franchisor_bp   # ← NEW

    app.register_blueprint(home_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(daily_checkin_bp,     url_prefix='/daily-check-in')
    app.register_blueprint(charts_bp)  # charts_bp already defines its prefix
    app.register_blueprint(figurella_reports_bp, url_prefix='/figurella-reports')
    app.register_blueprint(legacy_ai_bp,         url_prefix='/ai')
    app.register_blueprint(umbrella_bp,          url_prefix='/ai/assistant')
    app.register_blueprint(calendar_bp,          url_prefix='/calendar')
    app.register_blueprint(franchisor_bp,        url_prefix='/franchisor')  # ← NEW

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
        print()

    return app


# ─── Exporter: DB → Excel copy ───────────────────────────────────────
import pandas as pd
from flask import current_app
from app.models import ChartEntry


def export_client_charts_to_excel(client: str, excel_path: str, tabs=None) -> str:
    """
    Query ChartEntry for each sheet and write an .xlsx with one tab per sheet.
    """
    from flask import has_app_context

    def _do_export():
        nonlocal tabs
        if tabs is None:
            from app.charts.routes import EXPECTED_TABS
            tabs = EXPECTED_TABS

        os.makedirs(os.path.dirname(os.path.abspath(excel_path)), exist_ok=True)

        wrote_any = False
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
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
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
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
