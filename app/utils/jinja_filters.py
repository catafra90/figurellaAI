# app/utils/jinja_filters.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo  # stdlib in Python 3.9+

BOSTON_TZ = ZoneInfo("America/New_York")

def _parse_to_dt(value: Any) -> datetime | None:
    """
    Accepts ISO string or datetime and returns an aware UTC datetime.
    Returns None if it can't parse.
    """
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            # Accept "...Z" and "+00:00" endings
            s = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
        else:
            return None

        # Make sure it's timezone-aware (assume UTC if naive)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        return dt
    except Exception:
        return None

def format_est(value: Any, fmt: str = "%b %d, %Y — %I:%M %p %Z") -> str:
    """
    Convert a UTC timestamp (ISO string or datetime) to Boston local time.
    Default output like: 'Aug 17, 2025 — 11:04 PM EDT'
    """
    dt = _parse_to_dt(value)
    if not dt:
        return str(value)
    local_dt = dt.astimezone(BOSTON_TZ)
    return local_dt.strftime(fmt)

def register_jinja_filters(app) -> None:
    """Register filters on the Flask app's Jinja environment."""
    app.jinja_env.filters["format_est"] = format_est
