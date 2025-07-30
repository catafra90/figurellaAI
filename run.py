import os
from flask import send_from_directory, render_template
from app import create_app

# 1) Create the Flask app
app = create_app()
app.config['PROPAGATE_EXCEPTIONS'] = True  # Enable full traceback display

# 2) Register common routes
from app.common.routes import common_bp
app.register_blueprint(common_bp)

# 3) Daily Check-In is registered in app/__init__.py

# 4) Register Figurella Reports
from app.figurella_reports.routes import reports_bp as figurella_reports_bp
app.register_blueprint(figurella_reports_bp, url_prefix='/figurella-reports')

# 5) Register the Umbrella AI blueprint at /ai/assistant
from app.ai_assistant.umbrella import umbrella_bp
app.register_blueprint(umbrella_bp, url_prefix='/ai/assistant')

# 6) Service worker
@app.route('/service-worker.js')
def service_worker():
    return send_from_directory(
        os.path.join(app.root_path, 'static', 'js'),
        'service-worker.js'
    )

# 7) Fallback route for "/"
@app.route('/')
def index():
    try:
        return render_template('index.html')
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
