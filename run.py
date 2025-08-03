# File: run.py

import os
from flask import send_from_directory, render_template
from jinja2 import TemplateNotFound
from app import create_app

# ─── Initialize Flask app ─────────────────────────────────────────
app = create_app()
app.config['PROPAGATE_EXCEPTIONS'] = True

# ─── Service worker route ──────────────────────────────────────────
@app.route('/service-worker.js')
def service_worker():
    js_folder = os.path.join(app.root_path, 'static', 'js')
    return send_from_directory(js_folder, 'service-worker.js')

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
    print()

    # ─── Run the app ────────────────────────────────────────────────
    app.run(host="0.0.0.0", port=5000, debug=app.debug)
