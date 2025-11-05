# app/figurella_reports/services/sync_agenda.py
import os
import pandas as pd
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from .api_client import fetch_agenda

SUPABASE_PG_URI = os.getenv("SUPABASE_PG_URI")

class MissingDBURI(Exception): ...

def _db_engine():
    if not SUPABASE_PG_URI:
        raise MissingDBURI("SUPABASE_PG_URI not set")
    return create_engine(SUPABASE_PG_URI, pool_pre_ping=True)

def _exec_sql(conn, sql: str):
    cleaned = "\n".join(ln for ln in sql.splitlines() if not ln.strip().startswith("--"))
    for chunk in cleaned.split(";"):
        s = chunk.strip()
        if s:
            conn.execute(text(s + ";"))

DDL_SQL = """
CREATE TABLE IF NOT EXISTS public.raw_agenda (
  _ingested_at       timestamptz DEFAULT now(),
  _source_file       text,
  appointment_id     text,
  customer_id        text,
  customer_name      text,
  start_at           timestamptz,
  end_at             timestamptz,
  room               text,
  device             text,
  is_consultation    boolean,
  status_string      text,
  notes              text,
  payload            jsonb,
  raw_id             bigint,
  appointment_date   date,
  start_time         time,
  slot_id            text,
  center_code        text,
  device_id          text,
  status             text
);
CREATE INDEX IF NOT EXISTS idx_raw_agenda_ingested_at ON public.raw_agenda(_ingested_at);
CREATE INDEX IF NOT EXISTS idx_raw_agenda_customer_id ON public.raw_agenda(customer_id);
"""

def sync_agenda_to_supabase(frm: datetime, to: datetime) -> dict:
    eng = _db_engine()
    with eng.begin() as conn:
        conn.execute(text("SET TIME ZONE 'America/New_York';"))
        _exec_sql(conn, DDL_SQL)

    rows = fetch_agenda(frm, to)
    if not rows:
        return {"ok": True, "fetched": 0, "raw_appended": 0}

    df = pd.DataFrame(rows)
    df["_source_file"] = "api/agenda"
    df = df.rename(columns={
        "id": "appointment_id",
        "idCustomer": "customer_id",
        "customer": "customer_name",
        "start": "start_at",
        "end": "end_at",
        "roomName": "room",
        "deviceName": "device",
        "isConsultation": "is_consultation",
        "statusString": "status_string",
        "note": "notes",
        "idRaw": "raw_id",
        "appointmentDate": "appointment_date",
        "startTime": "start_time",
        "idSlot": "slot_id",
        "centerCode": "center_code",
        "idDevice": "device_id",
        "status": "status"
    })
    if "payload" not in df.columns:
        df["payload"] = None

    df.to_sql("raw_agenda", con=eng, schema="public", if_exists="append", index=False)

    with eng.begin() as conn:
        count = conn.execute(text("""
            SELECT count(*) AS c FROM public.raw_agenda
            WHERE _ingested_at = (SELECT max(_ingested_at) FROM public.raw_agenda)
        """)).mappings().one()

    return {
        "ok": True,
        "fetched": len(rows),
        "raw_latest": count["c"]
    }