# File: run.py
import os
import json
from pathlib import Path
from flask import send_from_directory, render_template, jsonify
from jinja2 import TemplateNotFound
from app import create_app

# Optional internal scheduler
try:
    from app.scheduler import start_scheduler
except Exception:
    start_scheduler = None

# ── Cached Location Performance service ───────────────────────────
try:
    from app.figurella_reports.services.location_performance.perf_metrics import get_perf_cached
except Exception as _err:
    get_perf_cached = None
    print("⚠️ perf_metrics cache not available:", _err)

# ── Cached Sales Statistics service (mirror perf) ─────────────────
try:
    from app.figurella_reports.services.sales_statistics.sales_metrics import get_sales_cached
except Exception as _err:
    get_sales_cached = None
    print("⚠️ sales_metrics cache not available:", _err)

# ── Flask app ─────────────────────────────────────────────────────
app = create_app()
app.config['PROPAGATE_EXCEPTIONS'] = True
if start_scheduler:
    start_scheduler(app)  # no-op unless ENABLE_INTERNAL_SCHEDULER=1

# ── Perf payload helper (uses cache; recompute only when sources change)
def _build_perf_payload() -> dict:
    """
    Fast: uses the file-mtime cache so it only recomputes after Excel sources change.
    Falls back to safe defaults if anything goes wrong.
    """
    base = {
        "active_clients": "—",
        "new_clients": {"try": 0, "ok": 0},
        "attendance": {"weeks": [
            {"label": "This Month", "count": 0, "current": True},
            {"label": "Last Month", "count": 0},
            {"label": "2 Months Ago", "count": 0},
        ]},
    }
    try:
        if not get_perf_cached:
            return base
        app_root = Path(app.root_path)
        instance_dir = Path(app.instance_path)
        snap = get_perf_cached(app_root, instance_dir) or {}
        base.update(snap)
    except Exception as e:
        print(f"⚠️ get_perf_cached failed: {e}")
    return base

# ── Sales payload helper (same pattern as perf)
def _build_sales_payload() -> dict:
    """
    Fast: uses the file-mtime cache so it only recomputes after Excel sources change.
    Falls back to safe defaults if anything goes wrong.
    """
    base = {"total": 0, "cash": 0, "payments": 0, "internal": 0, "newClients": 0}
    try:
        if not get_sales_cached:
            return base
        app_root = Path(app.root_path)
        instance_dir = Path(app.instance_path)
        snap = get_sales_cached(app_root, instance_dir) or {}
        base.update(snap)
    except Exception as e:
        print(f"⚠️ get_sales_cached failed: {e}")
    return base

# ── Static helpers ────────────────────────────────────────────────
@app.route('/service-worker.js')
def service_worker():
    js_folder = os.path.join(app.root_path, 'static', 'js')
    return send_from_directory(js_folder, 'service-worker.js')

@app.route('/download/<path:filename>')
def download_file(filename):
    download_dir = os.path.join(app.root_path, 'download')
    return send_from_directory(download_dir, filename, as_attachment=True)

# ── Index / Dashboard ─────────────────────────────────────────────
@app.route('/')
def index():
    try:
        perf  = _build_perf_payload()
        sales = _build_sales_payload()

        # Provide BOTH object + JSON string to support either template style
        return render_template(
            'index.html',
            PERF_DATA=perf,
            SALES_DATA=sales,
            perf_json=json.dumps(perf),
            sales_json=json.dumps(sales),
        )
    except TemplateNotFound:
        return '✅ Platform is running. Use the navigation menu.', 200

# ── Small JSON endpoints for dashboard cards ──────────────────────
@app.get('/figurella-reports/_perf/data')
def perf_data_api():
    app_root = Path(app.root_path)
    instance_dir = Path(app.instance_path)
    try:
        if get_perf_cached:
            return jsonify(get_perf_cached(app_root, instance_dir))
    except Exception as e:
        print("⚠️ perf data api error:", e)
    return jsonify(_build_perf_payload())

@app.get('/figurella-reports/_sales/data')
def sales_data_api():
    app_root = Path(app.root_path)
    instance_dir = Path(app.instance_path)
    try:
        if get_sales_cached:
            return jsonify(get_sales_cached(app_root, instance_dir))
    except Exception as e:
        print("⚠️ sales data api error:", e)
    return jsonify(_build_sales_payload())

# ── Entrypoint ────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n📦 Registered Routes:")
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        print(f"🔗 {rule.rule:<30} → {rule.endpoint}")

    if os.environ.get("ENABLE_INTERNAL_SCHEDULER") == "1":
        print("⏰ Internal scheduler: ENABLED (daily 4:00 PM America/New_York)")
    else:
        print("⏰ Internal scheduler: disabled (set ENABLE_INTERNAL_SCHEDULER=1 to enable)")
    print()

    app.run(host="0.0.0.0", port=5000, debug=app.debug)
