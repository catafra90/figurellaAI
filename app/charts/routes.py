# app/charts/routes.py (read-only; saving disabled; blocks imported)

from pathlib import Path
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, jsonify, current_app, url_for
from sqlalchemy import func, or_, not_

from app import db
from app.models import Client, ChartEntry
from .blocks import get_blocks  # workout presets (C*, V*, TO*, B*)

# ---------- template folder detection ----------
_here = Path(__file__).resolve()
TEMPLATES_DIR = (_here.parent.parent / "templates").resolve()
if not (TEMPLATES_DIR / "charts").exists():
    TEMPLATES_DIR = (_here.parent.parent / "template").resolve()

charts_bp = Blueprint(
    "charts",
    __name__,
    url_prefix="/charts",
    template_folder=str(TEMPLATES_DIR),
)

# ------------------- constants -------------------
EXPECTED_TABS = ["profile", "measures", "nutrition", "communication"]

DEFAULT_ROWS = {
    "nutrition": [{"Date": "", "Type": "", "Notes": ""}],
    "communication": [{"comm_date": "", "comm_type": "", "comm_notes": ""}],
}

# "Current" statuses (keyword match, case-insensitive)
CURRENT_KEYWORDS = {"current", "active", "pink", "confirmed", "attending"}
# Explicit exclusions from "Current" view
EXCLUDE_KEYWORDS = {"scheduled"}

# ------------------- small helpers -------------------
def _truthy(val) -> bool:
    if isinstance(val, bool):
        return val
    s = str(val or "").strip().lower()
    return s not in ("", "no", "false", "0", "off", "none")

def _utc_iso(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()

def _bulk_quick_flags(client_names):
    """Read most recent Nutrition/Focus flags from 'profile' rows for each client."""
    if not client_names:
        return {}
    flags = {name: {"nutrition": False, "focus": False} for name in client_names}
    try:
        rows = (
            ChartEntry.query
            .filter(ChartEntry.client_name.in_(client_names),
                    ChartEntry.sheet == "profile")
            .order_by(ChartEntry.created_at.desc())
            .all()
        )
        seen = {name: {"nutrition": False, "focus": False} for name in client_names}
        for ent in rows:
            name = ent.client_name
            if name not in flags:
                continue
            data = ent.data or {}
            field = (data.get("Field") or "").strip()
            if field == "Nutrition Flag" and not seen[name]["nutrition"]:
                flags[name]["nutrition"] = _truthy(data.get("Flag") or data.get("Value"))
                seen[name]["nutrition"] = True
            elif field == "Focus Case Flag" and not seen[name]["focus"]:
                flags[name]["focus"] = _truthy(data.get("Flag") or data.get("Value"))
                seen[name]["focus"] = True
    except Exception as e:
        current_app.logger.error(f"[charts/_bulk_quick_flags] {e}")
    return flags

def _readonly_mode() -> bool:
    """True when we want a blank UI (no DB rows rendered)."""
    try:
        return not bool(current_app.config.get("ENABLE_SAVES", False))
    except Exception:
        return True

def _build_sheets_for_client(client_name: str) -> dict:
    """Build the 'sheets' dict for all tabs for the given client (READ-ONLY)."""
    sheets = {}
    for tab in EXPECTED_TABS:
        entries = (
            ChartEntry.query
            .filter_by(client_name=client_name, sheet=tab)
            .order_by(ChartEntry.created_at)
            .all()
        )
        data = [e.data for e in entries] if entries else DEFAULT_ROWS.get(tab, [])
        sheets[tab] = {"data": data}

    rev1_entries = (
        ChartEntry.query
        .filter_by(client_name=client_name, sheet="workout_rev1")
        .order_by(ChartEntry.created_at)
        .all()
    )
    sheets["workout_rev1"] = {"data": [e.data for e in rev1_entries] if rev1_entries else []}

    if _readonly_mode():
        for k in list(sheets.keys()):
            sheets[k] = {"data": []}
    return sheets

# ------------------- views (read-only) -------------------
@charts_bp.get("/")
def view_charts():
    """
    Charts landing with server-side sidebar data.
    Uses ?status=current (default) or ?status=all.
    """
    status_mode = (request.args.get("status") or "current").strip().lower()
    filter_client = (request.args.get("client") or "").strip()

    try:
        q = Client.query
        if status_mode != "all":
            include = [Client.status.ilike(f"%{kw}%") for kw in CURRENT_KEYWORDS]
            q = q.filter(or_(*include))
            exclude = [Client.status.ilike(f"%{kw}%") for kw in EXCLUDE_KEYWORDS]
            q = q.filter(not_(or_(*exclude)))

        clients = q.order_by(func.lower(Client.name).asc()).all()

        names = [c.name for c in clients]
        flags_map = _bulk_quick_flags(names)

        columns = ["Name", "Date Created", "Status", "Email", "Phone"]
        data = []
        for c in clients:
            f = flags_map.get(c.name, {"nutrition": False, "focus": False})
            data.append({
                "Name": c.name,
                "Date Created": c.created_at.strftime("%Y-%m-%d") if c.created_at else "",
                "Status": c.status or "",
                "Email": c.email or "",
                "Phone": c.phone or "",
                "Nutrition Flag": "Yes" if f.get("nutrition") else "No",
                "Focus Case Flag": "Yes" if f.get("focus") else "No",
                "nutrition_flag": bool(f.get("nutrition")),
                "focus_flag": bool(f.get("focus")),
            })

        return render_template(
            "charts/charts.html",
            columns=columns,
            data=data,
            error=None,
            active_page="charts",
            default_status=status_mode,
            status_action_url=url_for("charts.view_charts"),
            filter_client=filter_client,
        )
    except Exception as e:
        current_app.logger.error(f"[view_charts] {e}")
        return render_template(
            "charts/charts.html",
            columns=[], data=[], error="Could not load client list.",
            active_page="charts",
            default_status=status_mode,
            status_action_url=url_for("charts.view_charts"),
            filter_client=filter_client,
        )

@charts_bp.get("/client/<client>")
def client_chart(client):
    """Render the full-page client tabs (with optional right rail), READ-ONLY."""
    try:
        client_obj = Client.query.filter_by(name=client).first()
        client_status = (client_obj.status if client_obj and client_obj.status else "").strip()

        sheets = _build_sheets_for_client(client)

        # Right rail list (names only)
        client_names = [c.name for c in Client.query.order_by(func.lower(Client.name)).all()]

        return render_template(
            "charts/_client_form.html",
            client=client,
            client_status=client_status,
            sheets=sheets,
            workout_blocks_json=get_blocks(),
            clients_right_rail=client_names,
        )
    except Exception as e:
        current_app.logger.error(f"[client_chart/{client}] {e}")
        return f"<div style='padding:1rem;color:#b91c1c'>Template error: {e}</div>", 200

@charts_bp.get("/client/<client>/card")
def client_card(client):
    """Return the tabbed client chart for the floating modal (READ-ONLY)."""
    try:
        client_obj = Client.query.filter_by(name=client).first()
        client_status = (client_obj.status if client_obj and client_obj.status else "").strip()
        sheets = _build_sheets_for_client(client)

        return render_template(
            "charts/client_card.html",
            client=client,
            client_status=client_status,
            sheets=sheets,
            workout_blocks_json=get_blocks(),
        )
    except Exception as e:
        current_app.logger.error(f"[client_card/{client}] {e}")
        return f"<div style='padding:1rem;color:#b91c1c'>Template error: {e}</div>", 200

# ------------------- workout blocks API (read-only) -------------------
@charts_bp.get("/workout/blocks.json")
def workout_blocks_json():
    try:
        blocks = get_blocks()
        key = (request.args.get("key") or "").strip()
        if key:
            blk = blocks.get(key)
            if not blk:
                return jsonify({"error": "unknown key", "key": key}), 404
            return jsonify(blk), 200
        return jsonify(blocks), 200
    except Exception as e:
        current_app.logger.error(f"[workout_blocks_json] {e}")
        return jsonify({"error": "failed to load blocks"}), 500

@charts_bp.get("/blocks.json")
def blocks_json():
    try:
        return jsonify(get_blocks()), 200
    except Exception as e:
        current_app.logger.error(f"[blocks_json] {e}")
        return jsonify({}), 200

# ------------------- history views (read-only) -------------------
@charts_bp.get("/client/<client>/workout-rev-history", endpoint="workout_rev_history")
def view_workout_rev_history(client: str):
    entries = (
        ChartEntry.query
        .filter_by(client_name=client, sheet="workout_rev1_history")
        .order_by(ChartEntry.created_at.desc())
        .all()
    )
    history_entries = []
    for e in entries:
        d = e.data or {}
        label = d.get("snapshot_at") or _utc_iso(e.created_at)
        history_entries.append({
            "meta": {"snapshot_id": d.get("snapshot_id", ""), "type": "workout_rev"},
            "label": label,
            "rows": d.get("rows", []),
        })
    return render_template(
        "charts/workout_rev_history.html",
        client_name=client,
        history_entries=history_entries,
    )

@charts_bp.get("/client/<client>/workout-rev-history.json")
def workout_rev_history_json(client):
    try:
        entries = (
            ChartEntry.query
            .filter_by(client_name=client, sheet="workout_rev1_history")
            .order_by(ChartEntry.created_at.desc())
            .all()
        )
        snapshots = []
        for ent in entries:
            d = ent.data or {}
            snapshots.append({
                "snapshot_id": d.get("snapshot_id") or str(ent.id),
                "snapshot_at": d.get("snapshot_at") or _utc_iso(ent.created_at),
                "kg": d.get("kg", ""),
                "tools": d.get("tools", ""),
                "program_type": d.get("program_type", ""),
                "rows": d.get("rows", []),
            })
        return jsonify(status="success", snapshots=snapshots, count=len(snapshots)), 200
    except Exception as e:
        current_app.logger.error(f"[workout_rev_history_json/{client}] {e}")
        return jsonify(status="error", message="Failed to load history"), 500

# ------------------- disabled write endpoints (no DB writes) -------------------
def _disabled(detail="Saving is temporarily disabled."):
    return jsonify({"status": "disabled", "detail": "Saving is temporarily disabled." if not detail else detail}), 200

@charts_bp.post("/client/<client>/save")
def save_client_chart_disabled(client):
    return _disabled()

@charts_bp.post("/client/<client>/workout-rev1/submit")
def workout_rev1_submit_disabled(client):
    return _disabled()

@charts_bp.post("/client/<client>/workout-rev1/clear")
def clear_workout_rev1_disabled(client):
    return _disabled()

@charts_bp.post("/client/<client>/workout-rev-history/<snapshot_id>/delete")
def delete_workout_rev_history_disabled(client, snapshot_id):
    return _disabled()

@charts_bp.get("/client/<client>/gk-order.json")
def charts_get_gk_order_disabled(client):
    return jsonify({"order": []})

@charts_bp.post("/client/<client>/gk-order")
def charts_save_gk_order_disabled(client):
    return _disabled("GK order is stored locally while saving is disabled.")
