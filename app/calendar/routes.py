# app/calendar/routes.py
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional, Iterable, List, Dict
from flask import Blueprint, render_template, request, jsonify, abort

from app import db
from app.models import Event
# ↓ import shared helpers
from app.calendar.services import (
    parse_iso, as_utc, expand_event,
    load_rrule, load_exdates, save_exdates,
    load_completed_on, save_completed_on,
    event_base_payload, duration, normalize_start_end,
    get_today_upcoming,  # used by Home (imported by home/routes.py)
)

calendar_bp = Blueprint("calendar", __name__)

# Views
@calendar_bp.get("/")
def view_calendar():
    return render_template("calendar/calendar.html")

@calendar_bp.get("/_debug/ping")
def ping():
    return jsonify(ok=True)

# Events API
@calendar_bp.get("/api/events")
def api_get_events():
    start = request.args.get("start")
    end   = request.args.get("end")
    if not start or not end:
        abort(400, "start and end are required")
    win_start = parse_iso(start)
    win_end   = parse_iso(end)

    items = Event.query.order_by(Event.start.asc()).all()
    out: List[Dict] = []
    for e in items:
        out.extend(list(expand_event(e, win_start, win_end)))
    return jsonify(out)

@calendar_bp.post("/api/events")
def api_create_event():
    data = request.get_json(force=True) or {}
    start = parse_iso(data.get("start"))
    end   = parse_iso(data.get("end"))
    all_day = bool(data.get("allDay", False))
    start, end = normalize_start_end(start, end, all_day)

    e = Event(
        title=data.get("title") or "(Untitled)",
        description=data.get("description") or "",
        start=start, end=end, all_day=all_day,
        location=data.get("location") or "",
        assignee=data.get("assignee") or "",
        completed=bool(data.get("completed", False)),
    )

    e.rrule = data.get("rrule") or None
    save_exdates(e, data.get("exdates") or [])

    if isinstance(data.get("completed_on"), list):
        save_completed_on(e, data["completed_on"])
    elif isinstance(data.get("completedOn"), list):
        save_completed_on(e, data["completedOn"])

    db.session.add(e)
    db.session.commit()
    return jsonify({"id": e.id}), 201

@calendar_bp.get("/api/events/<event_id>")
def api_get_event_detail(event_id: str):
    occurrence_iso = None
    series_id = event_id
    if ":" in event_id:
        series_id, occurrence_iso = event_id.split(":", 1)

    e = Event.query.get_or_404(int(series_id))
    rr = load_rrule(e)
    ex = load_exdates(e)
    comp = load_completed_on(e)

    return jsonify({
        "id": e.id,
        "title": e.title,
        "description": e.description or "",
        "location": e.location or "",
        "assignee": e.assignee or "",
        "start": as_utc(e.start).isoformat(),
        "end": as_utc(e.end).isoformat() if e.end else None,
        "allDay": bool(e.all_day),
        "completed": bool(getattr(e, "completed", False)),
        "completed_on": comp,
        "completedOn": comp,
        "rrule": rr,
        "exdates": ex,
        "occurrence_start": occurrence_iso,
    })

@calendar_bp.patch("/api/events/<event_id>")
def api_update_event(event_id: str):
    data = request.get_json(force=True) or {}
    series_id = event_id.split(":")[0]
    e = Event.query.get_or_404(int(series_id))

    # mark one occurrence (or series) completed/uncompleted
    if "completed" in data:
        # Accept occurrence from body OR from path (<series>:<iso>)
        occ_raw = data.get("occurrenceStart")
        if not occ_raw and ":" in event_id:
            _sid, _occ = event_id.split(":", 1)
            occ_raw = _occ

        if occ_raw:
            occ_dt = parse_iso(occ_raw)
            if not occ_dt:
                return jsonify({"ok": False, "error": "invalid occurrenceStart"}), 400
            occ_iso = as_utc(occ_dt).isoformat()
            lst = load_completed_on(e)
            if data["completed"]:
                if occ_iso not in lst:
                    lst.append(occ_iso)
                    save_completed_on(e, lst)
                    db.session.commit()
            else:
                lst2 = [x for x in lst if x != occ_iso]
                save_completed_on(e, lst2)
                db.session.commit()
            return jsonify({"ok": True, "completed_occurrence": occ_iso})
        else:
            e.completed = bool(data["completed"])
            db.session.commit()
            return jsonify({"ok": True, "completed": e.completed})

    # skip an occurrence (exdate)
    if data.get("skipOccurrence") and data.get("occurrenceStart"):
        occ_dt = parse_iso(data["occurrenceStart"])
        if not occ_dt:
            return jsonify({"ok": False, "error": "invalid occurrenceStart"}), 400
        occ_iso = as_utc(occ_dt).isoformat()
        ex = load_exdates(e)
        if occ_iso not in ex:
            ex.append(occ_iso)
            save_exdates(e, ex)
            db.session.commit()
        return jsonify({"ok": True, "skipped": occ_iso})

    # regular field updates
    if "title" in data:       e.title = data["title"] or e.title
    if "description" in data: e.description = data["description"] or ""
    if "start" in data:       e.start = parse_iso(data["start"])
    if "end" in data:         e.end   = parse_iso(data["end"])
    if "allDay" in data:      e.all_day = bool(data["allDay"])
    if "location" in data:    e.location = data["location"] or ""
    if "assignee" in data:    e.assignee = data["assignee"] or ""
    if "rrule" in data:       e.rrule = data["rrule"] or None
    if "exdates" in data and isinstance(data["exdates"], list):
        save_exdates(e, data["exdates"])
    if "completed_on" in data and isinstance(data["completed_on"], list):
        save_completed_on(e, data["completed_on"])
    if "completedOn" in data and isinstance(data["completedOn"], list):
        save_completed_on(e, data["completedOn"])

    e.start, e.end = normalize_start_end(e.start, e.end, e.all_day)
    db.session.commit()
    return jsonify({"ok": True})

@calendar_bp.delete("/api/events/<event_id>")
def api_delete_event(event_id: str):
    mode = request.args.get("mode", "").lower()
    if ":" in event_id and mode != "series":
        series_id, occurrence_iso = event_id.split(":", 1)
        e = Event.query.get_or_404(int(series_id))
        occ_dt = parse_iso(occurrence_iso)
        if not occ_dt:
            return jsonify({"ok": False, "error": "invalid occurrence id"}), 400
        occ_iso = as_utc(occ_dt).isoformat()
        ex = load_exdates(e)
        if occ_iso not in ex:
            ex.append(occ_iso)
            save_exdates(e, ex)
            db.session.commit()
        return jsonify({"ok": True, "skipped": occ_iso})

    e = Event.query.get_or_404(int(event_id.split(":")[0]))
    db.session.delete(e)
    db.session.commit()
    return jsonify({"ok": True})

# Legacy/fallback endpoint used by Home code — now directly reuses PATCH logic
@calendar_bp.post("/api/events/<event_id>/complete")
def api_complete_event(event_id: str):
    """Directly mark an event (or one occurrence) completed=True without test_request_context."""
    data = request.get_json(force=True) or {}
    data["completed"] = True
    # Reuse the same logic as PATCH in the current request context
    return api_update_event(event_id)

# Alarms (events only)
@calendar_bp.get("/api/alarms")
def api_upcoming_alarms():
    def _as_int(v, d):
        try: return int(v)
        except: return d

    within = _as_int(request.args.get("within"), 1440)
    grace  = _as_int(request.args.get("grace"), 5)
    limit  = _as_int(request.args.get("limit"), 50)

    now = datetime.now(timezone.utc)
    win_start = now - timedelta(minutes=grace)
    win_end   = now + timedelta(minutes=within)

    results: List[Dict] = []
    for e in Event.query.all():
        for ev in expand_event(e, win_start, win_end):
            results.append({
                "kind": "event",
                "event_id": ev["id"],
                "when": ev["start"],
                "title": ev["title"],
                "start": ev["start"],
                "end": ev.get("end"),
                "occurrenceStart": ev.get("occurrenceStart"),
                "assignee": ev["extendedProps"]["assignee"],
                "location": ev["extendedProps"]["location"],
                "description": ev["extendedProps"]["description"],
                "allDay": ev.get("allDay", False),
            })

    results.sort(key=lambda x: x["when"])
    return jsonify(results[:limit])
