import os
from flask import send_from_directory, render_template
from app import create_app

# 1) Create the Flask app
app = create_app()
app.config['PROPAGATE_EXCEPTIONS'] = True  # Enable full traceback display

# 2) Register “common” routes
from app.common.routes import common_bp
app.register_blueprint(common_bp)

# 3) Register Daily Check-In (so umbrella can navigate back)
from app.daily_checkin.routes import daily_checkin_bp as daily_checkin_v2_bp
app.register_blueprint(daily_checkin_v2_bp, url_prefix='/daily-check-in')

# 4) Register Reports (for nav + history views)
from app.reports.routes import reports_bp
app.register_blueprint(reports_bp)

# 5) Register the Umbrella AI blueprint at /umbrella/query
from app.ai_assistant.umbrella import umbrella_bp
app.register_blueprint(umbrella_bp)

# 6) Service worker
@app.route('/service-worker.js')
def service_worker():
    return send_from_directory(
        os.path.join(app.root_path, 'static', 'js'),
        'service-worker.js'
    )

# ✅ 7) Define a fallback route for "/"
@app.route('/')
def index():
    try:
        return render_template('index.html')  # Only if you have index.html
    except:
        return '✅ Platform is running. Use the navigation menu.'

# 8) Print all routes on startup for verification
print("\n📦 Registered Routes:")
for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    print(f"🔗 {rule.rule:<30} → {rule.endpoint}")
print()

# 9) Run the app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
