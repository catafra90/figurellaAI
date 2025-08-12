# File: app/__init__.py

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import Config

# ─── Database objects ────────────────────────────────────────────────
db = SQLAlchemy()
migrate = Migrate()

# ─── Import models so Migrate/Cli picks them up ───────────────────────
import app.models  # noqa: F401


def create_app():
    """Application factory: create and configure the Flask app."""
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(Config)

    # ─── Enable debug & template auto-reload ─────────────────────────
    app.debug = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.secret_key = app.config.get('SECRET_KEY', 'Figurella2025')

    # ─── Initialize database ─────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)

    # ─── Import & register blueprints ───────────────────────────────
    from app.home.routes              import home_bp
    from app.clients.routes           import clients_bp
    from app.daily_checkin.routes     import daily_checkin_bp
    from app.charts.routes            import charts_bp
    from app.figurella_reports.routes import reports_bp as figurella_reports_bp
    from app.ai_assistant.routes      import ai_bp       as legacy_ai_bp
    from app.ai_assistant.umbrella    import umbrella_bp

    # Calendar blueprint (must exist; raise if missing so we see errors)
    from app.calendar.routes import calendar_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(daily_checkin_bp,     url_prefix='/daily-check-in')
    app.register_blueprint(charts_bp,            url_prefix='/charts')
    app.register_blueprint(figurella_reports_bp, url_prefix='/figurella-reports')
    app.register_blueprint(legacy_ai_bp,         url_prefix='/ai')
    app.register_blueprint(umbrella_bp,          url_prefix='/ai/assistant')
    app.register_blueprint(calendar_bp,          url_prefix='/calendar')

    # ─── Debug: Show Registered Routes ───────────────────────────────
    with app.app_context():
        print("\n📦 Registered Routes:")
        for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
            print(f"🔗 {rule.endpoint:30} → {rule.rule}")
        print()

    return app


# ─── Exporter: DB → Excel copy ────────────────────────────────────

import pandas as pd
from app.models import ChartEntry

def export_client_charts_to_excel(client: str, excel_path: str, tabs=None):
    """
    Query ChartEntry for each sheet and write an .xlsx with one tab per sheet.
    If tabs is None, pulls EXPECTED_TABS from charts.routes.
    """
    # Lazily import EXPECTED_TABS to avoid circular imports
    if tabs is None:
        from app.charts.routes import EXPECTED_TABS
        tabs = EXPECTED_TABS

    writer = pd.ExcelWriter(excel_path, engine='openpyxl')
    for tab in tabs:
        records = (
            ChartEntry.query
                      .filter_by(client_name=client, sheet=tab)
                      .order_by(ChartEntry.created_at)
                      .all()
        )
        if not records:
            continue

        df = pd.DataFrame([r.data for r in records])
        df.to_excel(writer, sheet_name=tab.capitalize(), index=False)

    writer.save()
