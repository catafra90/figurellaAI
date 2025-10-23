# app/calendar/services.py
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Iterable, List, Dict

from app.models import Event

try:
    import zoneinfo  # py3.9+
except Exception:
    zoneinfo = None

# ---------- time helpers ----------
def parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

# ---------- model field helpers ----------
def load_rrule(e: Event) -> Dict:
    rr = e.rrule or {}
    if isinstance(rr, str):
        try:
            rr = json.loads(rr)
        except Exception:
            rr = {}
    return rr or {}

def load_exdates(e: Event) -> List[str]:
    v = getattr(e, "exdates", None)
    if v is None:
        return []
    if isinstance(v, list):
        return v
    try:
        return json.loads(v) or []
    except Exception:
        return []

def save_exdates(e: Event, iso_list: List[str]) -> None:
    try:
        e.exdates = json.dumps(iso_list)
    except Exception:
        e.exdates = iso_list

def load_completed_on(e: Event) -> List[str]:
    v = getattr(e, "completed_on", None)
    if v is None:
        return []
    if isinstance(v, list):
        return v
    try:
        return json.loads(v) or []
    except Exception:
        return []

def save_completed_on(e: Event, iso_list: List[str]) -> None:
    try:
        e.completed_on = json.dumps(iso_list)
    except Exception:
        e.completed_on = iso_list

def event_base_payload(e: Event) -> Dict:
    comp_list = load_completed_on(e)
    return {
        "series_id": e.id,
        "title": e.title,
        "allDay": bool(e.all_day),
        "extendedProps": {
            "description": e.description or "",
            "location": e.location or "",
            "assignee": e.assignee or "",
            "completed": bool(getattr(e, "completed", False)),
            "completedOn": comp_list,
            "completed_on": comp_list,
            "recurring": bool(e.rrule),
        },
    }

def duration(e: Event):
    if e.end is None:
        return None
    return as_utc(e.end) - as_utc(e.start)

def normalize_start_end(start: Optional[datetime], end: Optional[datetime], all_day: bool):
    if start and end and end < start:
        end = None if all_day else start
    return start, end

# ---------- recurrence expansion (DAILY/WEEKLY/MONTHLY) ----------
def expand_event(e: Event, win_start: datetime, win_end: datetime) -> Iterable[Dict]:
    win_start = as_utc(win_start)
    win_end   = as_utc(win_end)
    base_start = as_utc(e.start)
    dur = duration(e)
    exdates = set(load_exdates(e))
    rr = load_rrule(e)
    completed_set = set(load_completed_on(e))

    def instance_completed(iso: str) -> bool:
        if iso in completed_set:
            return True
        day = iso[:10]
        for s in completed_set:
            if isinstance(s, str) and s[:10] == day:
                return True
        return False

    def emit(start_dt: datetime):
        iso = as_utc(start_dt).isoformat()
        if iso in exdates:
            return
        d = event_base_payload(e)
        d["id"] = f"{e.id}:{iso}"
        d["start"] = iso
        d["end"] = (as_utc(start_dt) + dur).isoformat() if dur else None
        d["occurrenceStart"] = iso
        d["extendedProps"]["occurrence"] = True
        if instance_completed(iso):
            d["extendedProps"]["completed"] = True
        yield d

    if not rr:
        s = base_start
        if dur:
            if s < win_end and (s + dur) > win_start:
                d = event_base_payload(e)
                d.update({"id": str(e.id), "start": s.isoformat(), "end": (s + dur).isoformat()})
                d["occurrenceStart"] = d["start"]
                if bool(getattr(e, "completed", False)) or instance_completed(d["start"]):
                    d["extendedProps"]["completed"] = True
                yield d
        else:
            if win_start <= s < win_end:
                d = event_base_payload(e)
                d.update({"id": str(e.id), "start": s.isoformat(), "end": None})
                d["occurrenceStart"] = d["start"]
                if bool(getattr(e, "completed", False)) or instance_completed(d["start"]):
                    d["extendedProps"]["completed"] = True
                yield d
        return

    freq = (rr.get("freq") or "").upper()
    interval = int(rr.get("interval") or 1)
    until = parse_iso(rr.get("until")) if rr.get("until") else None
    if until:
        until = as_utc(until)

    if freq == "DAILY":
        i0_days = max(0, (win_start.date() - base_start.date()).days)
        if i0_days % interval != 0:
            i0_days += (interval - (i0_days % interval))
        cur = base_start + timedelta(days=i0_days)
        while cur < win_end:
            if until and cur > until:
                break
            if (dur and cur < win_end and (cur + dur) > win_start) or (not dur and cur >= win_start):
                yield from emit(cur)
            cur += timedelta(days=interval)

    elif freq == "WEEKLY":
        byweekday = rr.get("byweekday")
        if not byweekday or not isinstance(byweekday, list):
            byweekday = [base_start.weekday()]
        day = win_start.date()
        last_day = (win_end + timedelta(days=1)).date()
        while day < last_day:
            cur = datetime(
                day.year, day.month, day.day,
                base_start.hour, base_start.minute, base_start.second,
                tzinfo=timezone.utc
            )
            weeks = (cur.date() - base_start.date()).days // 7
            ok_week = (weeks % interval == 0) and (weeks >= 0)
            if ok_week and cur.weekday() in byweekday:
                if not until or cur <= until:
                    if (dur and cur < win_end and (cur + dur) > win_start) or (not dur and cur >= win_start):
                        yield from emit(cur)
            day += timedelta(days=1)

    elif freq == "MONTHLY":
        mdays = rr.get("bymonthday")
        if isinstance(mdays, int):
            mdays = [mdays]
        if not mdays:
            mdays = [base_start.day]

        cursor = datetime(
            win_start.year, win_start.month, 1,
            base_start.hour, base_start.minute, base_start.second,
            tzinfo=timezone.utc
        )
        bs_month_start = datetime(
            base_start.year, base_start.month, 1,
            base_start.hour, base_start.minute, base_start.second,
            tzinfo=timezone.utc
        )
        if cursor < bs_month_start:
            cursor = bs_month_start
        month_index = 0
        while month_index % interval != 0:
            cursor = cursor.replace(
                year=cursor.year + (1 if cursor.month == 12 else 0),
                month=(1 if cursor.month == 12 else cursor.month + 1)
            )
            month_index += 1

        while cursor < win_end:
            y, m = cursor.year, cursor.month
            next_month = datetime(
                y + (1 if m == 12 else 0), (1 if m == 12 else m + 1), 1,
                tzinfo=timezone.utc
            )
            days_in_month = (next_month - datetime(y, m, 1, tzinfo=timezone.utc)).days
            for dday in mdays:
                if 1 <= dday <= days_in_month:
                    cur = datetime(
                        y, m, dday,
                        base_start.hour, base_start.minute, base_start.second,
                        tzinfo=timezone.utc
                    )
                    if cur < base_start:
                        continue
                    if until and cur > until:
                        continue
                    if (dur and cur < win_end and (cur + dur) > win_start) or (not dur and cur >= win_start):
                        yield from emit(cur)
            cursor = next_month  # advance by 1 month each loop

    else:
        # unknown freq → treat as single
        s = base_start
        if dur:
            if s < win_end and (s + dur) > win_start:
                d = event_base_payload(e)
                d.update({"id": str(e.id), "start": s.isoformat(), "end": (s + dur).isoformat()})
                d["occurrenceStart"] = d["start"]
                if bool(getattr(e, "completed", False)):
                    d["extendedProps"]["completed"] = True
                yield d
        else:
            if win_start <= s < win_end:
                d = event_base_payload(e)
                d.update({"id": str(e.id), "start": s.isoformat(), "end": None})
                d["occurrenceStart"] = d["start"]
                if bool(getattr(e, "completed", False)):
                    d["extendedProps"]["completed"] = True
                yield d

# ---------- home notifications ----------
def get_today_upcoming(limit: int = 20, tz: str = "America/New_York") -> list[dict]:
    """
    Show all NOT-COMPLETED appointments from the last N days up through today,
    so overdue items remain visible on Home until marked Done.
    """
    # timezone
    if zoneinfo is not None:
        try:
            tzinfo = zoneinfo.ZoneInfo(tz)
        except Exception:
            tzinfo = timezone.utc
    else:
        tzinfo = timezone.utc

    def fmt_time(dt: datetime) -> str:
        # Windows-safe hour without leading zero
        return dt.strftime("%I:%M %p").lstrip("0").replace(" 0", " ")

    now_local = datetime.now(tzinfo)

    # Look back window (change 7 to whatever you prefer)
    lookback_days = 7
    start_window_local = now_local - timedelta(days=lookback_days)
    end_of_today_local = now_local.replace(hour=23, minute=59, second=59, microsecond=0)

    win_start = as_utc(start_window_local.astimezone(timezone.utc))
    win_end   = as_utc(end_of_today_local.astimezone(timezone.utc))

    items: list[dict] = []
    for e in Event.query.order_by(Event.start.asc()).all():
        for ev in expand_event(e, win_start, win_end):
            # skip already completed occurrences/series
            if ev.get("extendedProps", {}).get("completed"):
                continue

            dt_utc = parse_iso(ev["start"])
            if not dt_utc:
                continue
            dt_loc = dt_utc.astimezone(tzinfo)

            # Include if today or in the past; exclude future days
            if dt_loc.date() > now_local.date():
                continue

            items.append({
                "when": fmt_time(dt_loc),
                "client": (ev.get("title") or "").strip(),
                "room":   (ev.get("extendedProps", {}) or {}).get("location", "") or "",
                "notes":  (ev.get("extendedProps", {}) or {}).get("description", "") or "",
                "series_id": (ev.get("id") or "").split(":", 1)[0],
                "occurrenceStart": ev.get("occurrenceStart") or ev.get("start"),
            })

    # sort by real datetime ascending (oldest first)
    items.sort(key=lambda x: parse_iso(x["occurrenceStart"]) or datetime.max.replace(tzinfo=timezone.utc))
    return items[:limit]
