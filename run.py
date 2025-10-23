# File: run.py

import os
from flask import send_from_directory, render_template
from jinja2 import TemplateNotFound
from app import create_app

# ⏰ Internal daily scheduler (runs scrapers at 4:00 PM ET when enabled)
# Create app/scheduler.py as previously shown, then import here:
try:
    from app.scheduler import start_scheduler
except Exception:
    start_scheduler = None

# ─── Initialize Flask app ─────────────────────────────────────────
app = create_app()
app.config['PROPAGATE_EXCEPTIONS'] = True

# Start background scheduler only if env flag is set (avoids duplicates)
if start_scheduler:
    start_scheduler(app)  # no-op if ENABLE_INTERNAL_SCHEDULER not set

# ─── Service worker route ──────────────────────────────────────────
@app.route('/service-worker.js')
def service_worker():
    js_folder = os.path.join(app.root_path, 'static', 'js')
    return send_from_directory(js_folder, 'service-worker.js')

# ─── Download route for Excel reports ──────────────────────────────
@app.route('/download/<path:filename>')
def download_file(filename):
    """
    Serve the generated Excel files from app/download/.
    """
    download_dir = os.path.join(app.root_path, 'download')
    return send_from_directory(download_dir, filename, as_attachment=True)

# ─── Fallback index route ──────────────────────────────────────────
@app.route('/')
def index():
    try:
        return render_template('index.html')
    except TemplateNotFound:
        return '✅ Platform is running. Use the navigation menu.', 200

if __name__ == "__main__":
    # ─── Print all routes on startup for verification ───────────────
    print("\n📦 Registered Routes:")
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        print(f"🔗 {rule.rule:<30} → {rule.endpoint}")
    # Show scheduler state hint
    if os.environ.get("ENABLE_INTERNAL_SCHEDULER") == "1":
        print("⏰ Internal scheduler: ENABLED (daily 4:00 PM America/New_York)")
    else:
        print("⏰ Internal scheduler: disabled (set ENABLE_INTERNAL_SCHEDULER=1 to enable)")
    print()

    # ─── Run the app ────────────────────────────────────────────────
    # Note: if you run multiple gunicorn workers, ensure ONLY ONE process has
    # ENABLE_INTERNAL_SCHEDULER=1 to avoid duplicate runs.
    app.run(host="0.0.0.0", port=5000, debug=app.debug)
