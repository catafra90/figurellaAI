# app/models.py
from datetime import datetime
from sqlalchemy.sql import func
from sqlalchemy import CheckConstraint
from sqlalchemy.ext.mutable import MutableDict, MutableList
from app import db


class Client(db.Model):
    __tablename__ = 'clients'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(128), nullable=False)
    email      = db.Column(db.String(256))
    phone      = db.Column(db.String(50))
    status     = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Client {self.name}>'


class Report(db.Model):
    __tablename__ = 'reports'

    id        = db.Column(db.Integer, primary_key=True)
    key       = db.Column(db.String(128), nullable=False, unique=True, index=True)
    data      = db.Column(db.JSON, nullable=False)
    refreshed = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f'<Report {self.key} refreshed={self.refreshed}>'


class ReportHistory(db.Model):
    __tablename__ = 'report_history'

    id         = db.Column(db.Integer, primary_key=True)
    report_id  = db.Column(db.Integer, db.ForeignKey('reports.id'), nullable=False, index=True)
    data       = db.Column(db.JSON, nullable=False)
    timestamp  = db.Column(db.DateTime, server_default=func.now())

    report     = db.relationship('Report', backref=db.backref('history', lazy='dynamic'))

    def __repr__(self):
        return f'<ReportHistory report_id={self.report_id} at={self.timestamp}>'


class ChartEntry(db.Model):
    __tablename__ = 'chart_entries'

    id          = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(255), index=True, nullable=False)
    sheet       = db.Column(db.String(64), index=True, nullable=False)  # 'profile','measures','workout','nutrition','communication'
    data        = db.Column(db.JSON, nullable=False, default=dict)
    created_at  = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at  = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f'<ChartEntry {self.client_name} [{self.sheet}]>'


# ────────────────────────────────────────────────────────────────────
# Calendar features: Events + Reminders (+ completed + recurrence)
# ────────────────────────────────────────────────────────────────────

class Event(db.Model):
    __tablename__ = 'events'

    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text, default="")
    start        = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    end          = db.Column(db.DateTime(timezone=True))
    all_day      = db.Column(db.Boolean, nullable=False, server_default=db.text("0"))
    location     = db.Column(db.String(200), default="")
    assignee     = db.Column(db.String(120), index=True, default="")

    # Optional link to a client
    client_id    = db.Column(db.Integer, db.ForeignKey('clients.id'), index=True)
    client       = db.relationship('Client', backref=db.backref('events', lazy='dynamic'))

    # Completion state
    completed    = db.Column(db.Boolean, nullable=False, server_default=db.text("0"), index=True)
    completed_at = db.Column(db.DateTime(timezone=True))

    # ✅ Recurrence (mutable-aware so in-place edits are tracked)
    rrule        = db.Column(MutableDict.as_mutable(db.JSON), nullable=True)
    exdates      = db.Column(MutableList.as_mutable(db.JSON), nullable=False, default=list)

    created_at   = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at   = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint('(end IS NULL) OR (end >= start)', name='ck_events_end_after_start'),
    )

    def __repr__(self):
        return f'<Event {self.title} @ {self.start} completed={self.completed}>'


class Reminder(db.Model):
    __tablename__ = 'reminders'

    id         = db.Column(db.Integer, primary_key=True)
    event_id   = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False, index=True)
    remind_at  = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    channel    = db.Column(db.String(32), nullable=False, default="in_app")  # in_app | email | sms (future)
    sent       = db.Column(db.Boolean, nullable=False, server_default=db.text("0"), index=True)

    event      = db.relationship(
        'Event',
        backref=db.backref('reminders', lazy='dynamic', cascade="all, delete-orphan")
    )

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f'<Reminder event={self.event_id} at={self.remind_at} sent={self.sent}>'
