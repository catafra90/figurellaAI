# File: app/__init__.py

import os
from flask import Flask
from config import Config

def create_app():
    """Application factory: create and configure the Flask app."""
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(Config)

    # ─── Enable debug & template auto‑reload ───────────────────────────────
    app.debug = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.secret_key = app.config.get('SECRET_KEY', 'Figurella2025')

    # ─── Import & register blueprints ─────────────────────────────────────
    from app.common.routes            import common_bp
    from app.home.routes              import home_bp
    from app.clients.routes           import clients_bp
    from app.daily_checkin.routes     import daily_checkin_bp
    from app.charts.routes            import charts_bp
    from app.figurella_reports.routes import reports_bp as figurella_reports_bp
    from app.ai_assistant.routes      import ai_bp       as legacy_ai_bp
    from app.ai_assistant.umbrella    import umbrella_bp

    app.register_blueprint(common_bp)
    app.register_blueprint(home_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(daily_checkin_bp,     url_prefix='/daily-check-in')
    app.register_blueprint(charts_bp,             url_prefix='/charts')
    app.register_blueprint(figurella_reports_bp,  url_prefix='/figurella-reports')
    app.register_blueprint(legacy_ai_bp,          url_prefix='/ai')
    app.register_blueprint(umbrella_bp,           url_prefix='/ai/assistant')

    # ─── Debug: Show Registered Routes ─────────────────────────────────
    print("\n📦 Registered Routes:")
    with app.app_context():
        for rule in app.url_map.iter_rules():
            print(f"🔗 {rule.endpoint:30} → {rule.rule}")
    print()

    return app
