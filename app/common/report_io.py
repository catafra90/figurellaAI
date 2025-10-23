# app/common/report_io.py
import json
import pandas as pd
from typing import List
from contextlib import contextmanager
from flask import current_app
from app.models import Report, ReportHistory
from app.common.cleaners import drop_unwanted_rows

@contextmanager
def ensure_app_context():
    try:
        _ = current_app.name
        yield
    except Exception:
        from app import create_app
        app = create_app()
        with app.app_context():
            yield

def load_report_df(report_key: str) -> pd.DataFrame:
    with ensure_app_context():
        rpt = Report.query.filter_by(key=report_key).first()
        if not rpt:
            return pd.DataFrame()

        if isinstance(rpt.data, list) and rpt.data:
            records = rpt.data
        else:
            entries: List[ReportHistory] = (
                ReportHistory.query
                .filter_by(report_id=rpt.id)
                .order_by(ReportHistory.id.asc())
                .all()
            )
            records = []
            for h in entries:
                raw = h.data
                obj = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(obj, list):
                    records.extend(obj)
                else:
                    records.append(obj)

        if not records:
            return pd.DataFrame()

        df = pd.json_normalize(records)

        # ⛔️ DO NOT drop Email/Phone globally; some reports (Last Session) need them
        # Keep only the helper column out of the way:
        if '_sheet' in df.columns:
            df.drop(columns=['_sheet'], inplace=True)

        try:
            df = drop_unwanted_rows(df)
        except Exception:
            pass

        return df
