from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Iterable, List, Dict

from flask import Blueprint, render_template, request, jsonify, abort
from sqlalchemy import and_, or_

from app import db
from app.models import Event

calendar_bp = Blueprint("calendar", __name__)

# ─────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────
@calendar_bp.get("/")
def view_calendar():
    return render_template("calendar/calendar.html")

@calendar_bp.get("/_debug/ping")
def ping():
    return jsonify(ok=True)

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    """Parse ISO strings; accept 'Z' and naive -> UTC."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _load_rrule(e: Event) -> Dict:
    rr = e.rrule or {}
    if isinstance(rr, str):
        try:
            rr = json.loads(rr)
        except Exception:
            rr = {}
    return rr or {}

def _load_exdates(e: Event) -> List[str]:
    v = getattr(e, "exdates", None)
    if v is None:
        return []
    if isinstance(v, list):
        return v
    try:
        return json.loads(v) or []
    except Exception:
        return []

def _save_exdates(e: Event, iso_list: List[str]) -> None:
    try:
        e.exdates = json.dumps(iso_list)
    except Exception:
        e.exdates = iso_list

def _load_completed_on(e: Event) -> List[str]:
    """Return list of ISO strings marking completed occurrences."""
    v = getattr(e, "completed_on", None)
    if v is None:
        return []
    if isinstance(v, list):
        return v
    try:
        return json.loads(v) or []
    except Exception:
        return []

def _save_completed_on(e: Event, iso_list: List[str]) -> None:
    try:
        e.completed_on = json.dumps(iso_list)
    except Exception:
        e.completed_on = iso_list

def _event_base_payload(e: Event) -> Dict:
    comp_list = _load_completed_on(e)
    # include both keys for compatibility with older frontends
    return {
        "series_id": e.id,
        "title": e.title,
        "allDay": bool(e.all_day),
        "extendedProps": {
            "description": e.description or "",
            "location": e.location or "",
            "assignee": e.assignee or "",
            "completed": bool(getattr(e, "completed", False)),  # series-level
            "completedOn": comp_list,                            # per-occurrence list
            "completed_on": comp_list,
            "recurring": bool(e.rrule),
        },
    }

def _duration(e: Event):
    if e.end is None:
        return None
    return _as_utc(e.end) - _as_utc(e.start)

def _normalize_start_end(start: Optional[datetime], end: Optional[datetime], all_day: bool):
    if start and end and end < start:
        if all_day:
            end = None
        else:
            end = start
    return start, end

# ─────────────────────────────────────────────────────────────
# Recurrence expansion (DAILY, WEEKLY, MONTHLY)
# ─────────────────────────────────────────────────────────────
def _expand_event(e: Event, win_start: datetime, win_end: datetime) -> Iterable[Dict]:
    win_start = _as_utc(win_start)
    win_end   = _as_utc(win_end)
    base_start = _as_utc(e.start)
    dur = _duration(e)
    exdates = set(_load_exdates(e))
    rr = _load_rrule(e)
    completed_list = _load_completed_on(e)
    completed_set = set(completed_list)  # faster lookups

    def _instance_completed(iso: str) -> bool:
        # exact match or same-day match
        if iso in completed_set:
            return True
        day = iso[:10]
        for s in completed_set:
            if isinstance(s, str) and s[:10] == day:
                return True
        return False

    def _emit(start_dt: datetime):
        iso = _as_utc(start_dt).isoformat()
        if iso in exdates:
            return
        d = _event_base_payload(e)
        d["id"] = f"{e.id}:{iso}"
        d["start"] = iso
        d["end"] = (_as_utc(start_dt)+dur).isoformat() if dur else None
        d["occurrenceStart"] = iso
        d["extendedProps"]["occurrence"] = True
        # mark this instance completed if its ISO (or day) is in completed_on
        if _instance_completed(iso):
            d["extendedProps"]["completed"] = True
        yield d

    # Non‑recurring
    if not rr:
        s = base_start
        if dur:
            if s < win_end and (s + dur) > win_start:
                d = _event_base_payload(e)
                d.update({"id": str(e.id), "start": s.isoformat(), "end": (s+dur).isoformat()})
                d["occurrenceStart"] = d["start"]
                # also treat single event as done if series 'completed' is true or its start in list
                if bool(getattr(e, "completed", False)) or _instance_completed(d["start"]):
                    d["extendedProps"]["completed"] = True
                yield d
        else:
            if s >= win_start and s < win_end:
                d = _event_base_payload(e)
                d.update({"id": str(e.id), "start": s.isoformat(), "end": None})
                d["occurrenceStart"] = d["start"]
                if bool(getattr(e, "completed", False)) or _instance_completed(d["start"]):
                    d["extendedProps"]["completed"] = True
                yield d
        return

    # Recurring
    freq = (rr.get("freq") or "").upper()
    interval = int(rr.get("interval") or 1)
    until = _parse_iso(rr.get("until")) if rr.get("until") else None
    if until:
        until = _as_utc(until)

    if freq == "DAILY":
        i0_days = max(0, (win_start.date() - base_start.date()).days)
        if i0_days % interval != 0:
            i0_days += (interval - (i0_days % interval))
        cur = base_start + timedelta(days=i0_days)
        while cur < win_end:
            if until and cur > until:
                break
            if (dur and cur < win_end and (cur + dur) > win_start) or (not dur and cur >= win_start):
                for ev in _emit(cur):
                    yield ev
            cur += timedelta(days=interval)

    elif freq == "WEEKLY":
        byweekday = rr.get("byweekday")
        if not byweekday or not isinstance(byweekday, list):
            byweekday = [base_start.weekday()]
        day = win_start.date()
        last_day = (win_end + timedelta(days=1)).date()
        while day < last_day:
            cur = datetime(day.year, day.month, day.day, base_start.hour, base_start.minute, base_start.second, tzinfo=timezone.utc)
            weeks = (cur.date() - base_start.date()).days // 7
            ok_week = (weeks % interval == 0) and (weeks >= 0)
            if ok_week and cur.weekday() in byweekday:
                if not until or cur <= until:
                    if (dur and cur < win_end and (cur + dur) > win_start) or (not dur and cur >= win_start):
                        for ev in _emit(cur):
                            yield ev
            day += timedelta(days=1)

    elif freq == "MONTHLY":
        mdays = rr.get("bymonthday")
        if isinstance(mdays, int):
            mdays = [mdays]
        if not mdays:
            mdays = [base_start.day]

        cursor = datetime(win_start.year, win_start.month, 1, base_start.hour, base_start.minute, base_start.second, tzinfo=timezone.utc)
        bs_month_start = datetime(base_start.year, base_start.month, 1, base_start.hour, base_start.minute, base_start.second, tzinfo=timezone.utc)
        if cursor < bs_month_start:
            cursor = bs_month_start
        month_index = 0
        while month_index % interval != 0:
            if cursor.month == 12:
                cursor = cursor.replace(year=cursor.year+1, month=1)
            else:
                cursor = cursor.replace(month=cursor.month+1)
            month_index += 1

        while cursor < win_end:
            y, m = cursor.year, cursor.month
            if m == 12:
                next_month = datetime(y+1, 1, 1, tzinfo=timezone.utc)
            else:
                next_month = datetime(y, m+1, 1, tzinfo=timezone.utc)
            days_in_month = (next_month - datetime(y, m, 1, tzinfo=timezone.utc)).days

            for dday in mdays:
                if 1 <= dday <= days_in_month:
                    cur = datetime(y, m, dday, base_start.hour, base_start.minute, base_start.second, tzinfo=timezone.utc)
                    if cur < base_start:
                        continue
                    if until and cur > until:
                        continue
                    if (dur and cur < win_end and (cur + dur) > win_start) or (not dur and cur >= win_start):
                        for ev in _emit(cur):
                            yield ev
            for _ in range(interval):
                if cursor.month == 12:
                    cursor = cursor.replace(year=cursor.year+1, month=1)
                else:
                    cursor = cursor.replace(month=cursor.month+1)

    else:
        # unknown freq → treat as single
        s = base_start
        if dur:
            if s < win_end and (s + dur) > win_start:
                d = _event_base_payload(e)
                d.update({"id": str(e.id), "start": s.isoformat(), "end": (s+dur).isoformat()})
                d["occurrenceStart"] = d["start"]
                if bool(getattr(e, "completed", False)) or (d["start"] in completed_set):
                    d["extendedProps"]["completed"] = True
                yield d
        else:
            if s >= win_start and s < win_end:
                d = _event_base_payload(e)
                d.update({"id": str(e.id), "start": s.isoformat(), "end": None})
                d["occurrenceStart"] = d["start"]
                if bool(getattr(e, "completed", False)) or (d["start"] in completed_set):
                    d["extendedProps"]["completed"] = True
                yield d

# ─────────────────────────────────────────────────────────────
# Events API
# ─────────────────────────────────────────────────────────────
@calendar_bp.get("/api/events")
def api_get_events():
    start = request.args.get("start")
    end   = request.args.get("end")
    if not start or not end:
        abort(400, "start and end are required")
    win_start = _parse_iso(start)
    win_end   = _parse_iso(end)

    items = Event.query.order_by(Event.start.asc()).all()
    out: List[Dict] = []
    for e in items:
        out.extend(list(_expand_event(e, win_start, win_end)))
    return jsonify(out)

@calendar_bp.post("/api/events")
def api_create_event():
    data = request.get_json(force=True) or {}
    start = _parse_iso(data.get("start"))
    end   = _parse_iso(data.get("end"))
    all_day = bool(data.get("allDay", False))
    start, end = _normalize_start_end(start, end, all_day)

    e = Event(
        title=data.get("title") or "(Untitled)",
        description=data.get("description") or "",
        start=start,
        end=end,
        all_day=all_day,
        location=data.get("location") or "",
        assignee=data.get("assignee") or "",
        completed=bool(data.get("completed", False)),
    )

    rr = data.get("rrule") or None
    ex = data.get("exdates") or []
    e.rrule = rr
    _save_exdates(e, ex)

    # allow optional initial completed_on list
    if isinstance(data.get("completed_on"), list):
        _save_completed_on(e, data["completed_on"])
    elif isinstance(data.get("completedOn"), list):
        _save_completed_on(e, data["completedOn"])

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
    rr = _load_rrule(e)
    ex = _load_exdates(e)
    comp = _load_completed_on(e)

    return jsonify({
        "id": e.id,
        "title": e.title,
        "description": e.description or "",
        "location": e.location or "",
        "assignee": e.assignee or "",
        "start": _as_utc(e.start).isoformat(),
        "end": _as_utc(e.end).isoformat() if e.end else None,
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

    # --- mark one occurrence (or series) completed/uncompleted ---
    if "completed" in data:
        occ_raw = data.get("occurrenceStart")
        if occ_raw:
            occ_dt = _parse_iso(occ_raw)
            if not occ_dt:
                return jsonify({"ok": False, "error": "invalid occurrenceStart"}), 400
            occ_iso = _as_utc(occ_dt).isoformat()
            lst = _load_completed_on(e)
            if data["completed"]:
                if occ_iso not in lst:
                    lst.append(occ_iso)
                    _save_completed_on(e, lst)
                    db.session.commit()
            else:
                lst2 = [x for x in lst if x != occ_iso]
                _save_completed_on(e, lst2)
                db.session.commit()
            return jsonify({"ok": True, "completed_occurrence": occ_iso})
        else:
            # whole event / series-level
            e.completed = bool(data["completed"])
            db.session.commit()
            return jsonify({"ok": True, "completed": e.completed})

    # --- skip an occurrence (exdate) ---
    if data.get("skipOccurrence") and data.get("occurrenceStart"):
        occ_dt = _parse_iso(data["occurrenceStart"])
        if not occ_dt:
            return jsonify({"ok": False, "error": "invalid occurrenceStart"}), 400
        occ_iso = _as_utc(occ_dt).isoformat()
        ex = _load_exdates(e)
        if occ_iso not in ex:
            ex.append(occ_iso)
            _save_exdates(e, ex)
            db.session.commit()
        return jsonify({"ok": True, "skipped": occ_iso})

    # --- regular field updates ---
    if "title" in data:       e.title = data["title"] or e.title
    if "description" in data: e.description = data["description"] or ""
    if "start" in data:       e.start = _parse_iso(data["start"])
    if "end" in data:         e.end   = _parse_iso(data["end"])
    if "allDay" in data:      e.all_day = bool(data["allDay"])
    if "location" in data:    e.location = data["location"] or ""
    if "assignee" in data:    e.assignee = data["assignee"] or ""
    if "rrule" in data:       e.rrule = data["rrule"] or None
    if "exdates" in data and isinstance(data["exdates"], list):
        _save_exdates(e, data["exdates"])
    if "completed_on" in data and isinstance(data["completed_on"], list):
        _save_completed_on(e, data["completed_on"])
    if "completedOn" in data and isinstance(data["completedOn"], list):
        _save_completed_on(e, data["completedOn"])

    e.start, e.end = _normalize_start_end(e.start, e.end, e.all_day)
    db.session.commit()
    return jsonify({"ok": True})

@calendar_bp.delete("/api/events/<event_id>")
def api_delete_event(event_id: str):
    mode = request.args.get("mode", "").lower()
    if ":" in event_id and mode != "series":
        series_id, occurrence_iso = event_id.split(":", 1)
        e = Event.query.get_or_404(int(series_id))
        # normalize stored exdate
        occ_dt = _parse_iso(occurrence_iso)
        if not occ_dt:
            return jsonify({"ok": False, "error": "invalid occurrence id"}), 400
        occ_iso = _as_utc(occ_dt).isoformat()
        ex = _load_exdates(e)
        if occ_iso not in ex:
            ex.append(occ_iso)
            _save_exdates(e, ex)
            db.session.commit()
        return jsonify({"ok": True, "skipped": occ_iso})

    e = Event.query.get_or_404(int(event_id.split(":")[0]))
    db.session.delete(e)
    db.session.commit()
    return jsonify({"ok": True})

# Legacy/fallback endpoint used by Home code
@calendar_bp.post("/api/events/<event_id>/complete")
def api_complete_event(event_id: str):
    data = request.get_json(force=True) or {}
    data["completed"] = True
    # delegate to PATCH handling
    with calendar_bp.test_request_context(json=data):
        return api_update_event(event_id)

# ─────────────────────────────────────────────────────────────
# Alarms (events only)
# ─────────────────────────────────────────────────────────────
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
        for ev in _expand_event(e, win_start, win_end):
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
