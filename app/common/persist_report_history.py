from typing import Iterable, Mapping, Optional, Any
from datetime import datetime

from app import db
from app.models import ReportHistory

def persist_last_session_rows(rows: Iterable[Mapping[str, Any]], *, report_id: int = 2,
                              timestamp: Optional[datetime] = None) -> int:
    """
    Persist Last-Session rows as ONE ReportHistory row per client (dict). Never store a list.
    Returns number of inserted rows.
    """
    ts = timestamp or datetime.utcnow()
    n = 0
    for row in rows:
        if row is None:
            continue
        # Normalize accidental list payloads defensively:
        if isinstance(row, list):
            for item in row:
                if isinstance(item, dict):
                    db.session.add(ReportHistory(report_id=report_id, data=item, timestamp=ts))
                    n += 1
            continue
        if not isinstance(row, dict):
            continue
        db.session.add(ReportHistory(report_id=report_id, data=row, timestamp=ts))
        n += 1
    db.session.commit()
    return n
