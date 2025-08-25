# app/franchisor/routes.py
from flask import Blueprint, render_template, request, jsonify
import threading, re, traceback
from app.common.create_appointment import create_appointment
from app.common.check_availability import get_open_slots  # uses semantic badge classes

franchisor_bp = Blueprint("franchisor", __name__, template_folder="../templates")

# ───────────────────────── Pages ─────────────────────────

@franchisor_bp.route("/", methods=["GET"])
def franchisor_home():
    """Standalone page to create appointments on the franchisor portal."""
    return render_template("franchisor/index.html")

@franchisor_bp.route("/availability", methods=["GET"])
def franchisor_availability_page():
    """
    Simple page to select a date and view open slots.
    Template: app/templates/franchisor_availability.html
    """
    return render_template("franchisor_availability.html")

# ───────────────────────── Health ─────────────────────────

@franchisor_bp.route("/_debug/ping", methods=["GET"])
def franchisor_ping():
    return jsonify(ok=True, section="franchisor")

# ─────────────────── Helpers (unchanged) ──────────────────

def _normalize_time(s: str) -> str:
    """Ensure 'hh:mm am/pm' (accepts '1130am', '11:30am', '11:30 am')."""
    if not s:
        return s
    t = s.strip().lower().replace(".", "").replace("  ", " ")
    m = re.match(r"^(\d{1,2})(\d{2})(am|pm)$", t)  # 1130am
    if m:
        return f"{m.group(1)}:{m.group(2)} {m.group(3)}"
    t = re.sub(r"(\d)(am|pm)$", r"\1 \2", t)       # 11:30am -> 11:30 am
    return t

def _coerce_result(res, date_iso, column_label, time_label, customer_name):
    """
    Accepts either:
      - dict like {"ok": bool, "message": "..."}
      - bool
    and returns a dict {"ok": bool, "message": str}
    """
    if isinstance(res, dict):
        ok = bool(res.get("ok"))
        msg = res.get("message") or (
            f"Appointment {'created' if ok else 'not created'} for {customer_name} "
            f"at {time_label} in {column_label}"
        )
        return {"ok": ok, "message": msg}
    ok = bool(res)
    return {
        "ok": ok,
        "message": (
            f"Appointment created for {customer_name} at {time_label} in {column_label}"
            if ok else "Appointment was not created. Please check the franchisor portal."
        ),
    }

# ───────────────── Availability API (revised) ─────────────

@franchisor_bp.route("/availability/check", methods=["GET"])
def franchisor_availability_check():
    """
    Query open slots on the franchisor portal for a given date.

    Query params:
      - date: YYYY-MM-DD (required)
      - col:  repeated column names (optional)  e.g. ?col=Bubble%201&col=Consultation
      - columns: comma-separated columns (optional) e.g. ?columns=Bubble%201,Bubble%202

    Returns:
      { "ok": true, "date": "2025-08-31",
        "slots": { "Bubble 1": ["9:00 am", ...], "Consultation": [...] } }
    """
    date_iso = (request.args.get("date") or "").strip()
    if not date_iso:
        return jsonify(ok=False, error="Missing 'date' (YYYY-MM-DD)."), 400

    # Accept either repeated ?col=… or a single comma-separated ?columns=…
    cols = request.args.getlist("col")
    if not cols:
        csv = (request.args.get("columns") or "").strip()
        if csv:
            cols = [c.strip() for c in csv.split(",") if c.strip()]

    try:
        # get_open_slots now derives times from the grid; no step/min argument
        slots = get_open_slots(date_iso, allowed_columns=(cols or None))
        return jsonify(ok=True, date=date_iso, slots=slots)
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False, error=f"{type(e).__name__}: {e}"), 500

# ───────────────── Create Appointment (existing) ─────────

@franchisor_bp.route("/create", methods=["POST"])
def franchisor_create():
    """
    Create the appointment on the franchisor portal via Playwright.
    Runs in a background thread unless {"sync": true} is provided in the JSON.
    Expected JSON:
    {
      "date": "YYYY-MM-DD",
      "column": "Consultation" | "Bubble 1" | ...,
      "time": "07:00 am",
      "customer": "Full name as shown in franchisor portal",
      "memo": "optional note",
      "sync": true|false
    }
    """
    data = request.get_json(silent=True) or request.form.to_dict(flat=True) or {}

    print("[franchisor.create] incoming:", {
        "date": data.get("date"),
        "column": data.get("column"),
        "time": data.get("time"),
        "customer": data.get("customer"),
        "memo": data.get("memo"),
        "sync": data.get("sync"),
        "content_type": request.headers.get("Content-Type")
    })

    date_iso      = (data.get("date") or "").strip()
    column_label  = (data.get("column") or "").strip()
    time_label    = _normalize_time(data.get("time") or "")
    customer_name = (data.get("customer") or "").strip()
    memo          = (data.get("memo") or "").strip()

    # Boolean coercion for sync
    raw_sync = data.get("sync")
    sync = False
    if isinstance(raw_sync, bool):
        sync = raw_sync
    elif isinstance(raw_sync, str):
        sync = raw_sync.strip().lower() in {"1", "true", "yes", "y"}

    # Validate required fields
    missing = [k for k, v in {
        "date": date_iso,
        "column": column_label,
        "time": time_label,
        "customer": customer_name,
    }.items() if not v]
    if missing:
        return jsonify(ok=False, message=f"Missing fields: {', '.join(missing)}"), 400

    def _run_once():
        try:
            print("[franchisor.create] invoking create_appointment with:", {
                "date_iso": date_iso,
                "column_label": column_label,
                "time_label": time_label,
                "customer_name": customer_name,
                "memo": memo
            })
            res = create_appointment(
                date_iso=date_iso,
                column_label=column_label,
                time_label=time_label,
                customer_name=customer_name,
                memo=memo
            )
            return _coerce_result(res, date_iso, column_label, time_label, customer_name)
        except Exception as e:
            print(f"[franchisor.create] background error: {e}")
            return {"ok": False, "message": str(e)}

    if sync:
        result = _run_once()
        return jsonify(ok=result["ok"], queued=False, message=result["message"])

    # fire-and-forget background execution
    t = threading.Thread(target=_run_once, daemon=True)
    t.start()
    return jsonify(ok=True, queued=True, message="Queued. A browser window will handle creation.")
