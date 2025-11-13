# File: run.py
import os
import json
import sqlite3                          # ⬅︎ NEW
from urllib.parse import unquote         # ⬅︎ NEW
from pathlib import Path
from flask import send_from_directory, render_template, jsonify, url_for, redirect  # + redirect
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

# ── NEW: Consultation blueprint registration ──────────────────────
try:
    from app.consultation.routes import bp as consultation_bp
    app.register_blueprint(consultation_bp)
    print("✅ consultation blueprint registered")
except Exception as e:
    print("⚠️ consultation blueprint not available:", e)

# ── NEW: serve saved signature images from instance/ ──────────────
@app.route("/u/signatures/<path:filename>")
def serve_signature(filename: str):
    sig_dir = os.path.join(app.instance_path, "uploads", "signatures")
    return send_from_directory(sig_dir, filename)

# ── NEW: jinja helper to build signature URL from absolute path ───
@app.context_processor
def _inject_helpers():
    def signature_url(abs_path: str | None):
        """Turn an absolute file path saved in DB into a public URL."""
        if not abs_path:
            return None
        try:
            fname = os.path.basename(abs_path)
            return url_for("serve_signature", filename=fname)
        except Exception:
            return None
    return dict(signature_url=signature_url)

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

# ── NEW: Legacy /reports/<name> → redirect to new profile route ───
def _conn_instance():
    dbp = Path(app.instance_path) / "figurella.db"
    dbp.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(dbp)
    con.row_factory = sqlite3.Row
    return con

@app.route("/reports/<path:name>")
def legacy_reports_redirect(name):
    """
    Keep old links working:
    /reports/Maria%20Rossi  →  /consultation/client/<id>
    /reports/Rossi          →  /consultation/client/<id> (last-name only)
    """
    q = unquote(name or "").strip()
    if not q:
        return "Missing client name.", 400

    parts = [p for p in q.split() if p]
    with _conn_instance() as c:
        if len(parts) == 1:
            # match either first or last name
            rows = c.execute(
                """
                SELECT id FROM clients
                WHERE lower(first_name)=lower(?) OR lower(last_name)=lower(?)
                ORDER BY id DESC LIMIT 1
                """,
                (q, q),
            ).fetchall()
        else:
            first = parts[0]
            last  = " ".join(parts[1:])
            rows = c.execute(
                """
                SELECT id FROM clients
                WHERE lower(first_name)=lower(?) AND lower(last_name)=lower(?)
                ORDER BY id DESC LIMIT 1
                """,
                (first, last),
            ).fetchall()

    if rows:
        return redirect(url_for("consultation.client_profile", client_id=rows[0]["id"]), code=302)
    return f"No client found matching '{q}'.", 404

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
