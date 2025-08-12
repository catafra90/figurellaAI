# app/scheduler.py
from datetime import datetime, timedelta
from flask import current_app
from app import db, socketio  # socketio optional (see below)
from app.models import Reminder, Event

def send_in_app_notification(payload):
    # If you integrate Flask-SocketIO:
    try:
        socketio.emit("notify", payload, broadcast=True)
    except Exception:
        pass

def process_due_reminders():
    now = datetime.utcnow()
    # small grace to avoid missing exact equality
    window = now + timedelta(seconds=30)
    due = Reminder.query.filter(
        Reminder.sent.is_(False),
        Reminder.remind_at <= window
    ).all()
    for r in due:
        ev = Event.query.get(r.event_id)
        if not ev:
            r.sent = True
            continue
        if r.channel == "in_app":
            send_in_app_notification({
                "title": f"Reminder: {ev.title}",
                "body":  ev.description or "",
                "when":  r.remind_at.isoformat(),
                "event_id": ev.id
            })
        # TODO: email/SMS channels later
        r.sent = True
    if due:
        db.session.commit()
