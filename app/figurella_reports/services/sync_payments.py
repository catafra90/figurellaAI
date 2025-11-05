# app/figurella_reports/services/sync_payments.py
import os
import pandas as pd
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from .api_client import fetch_payments

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
CREATE TABLE IF NOT EXISTS public.raw_payments (
  _ingested_at      timestamptz DEFAULT now(),
  _source_file      text,
  payment_id        text,
  customer_id       text,
  customer_name     text,
  amount            numeric,
  due_date          timestamptz,
  payment_date      timestamptz,
  is_paid           boolean,
  method            text,
  notes             text,
  payload           jsonb
);
CREATE INDEX IF NOT EXISTS idx_raw_payments_ingested_at ON public.raw_payments(_ingested_at);
CREATE INDEX IF NOT EXISTS idx_raw_payments_id ON public.raw_payments(payment_id);
"""

def sync_payments_to_supabase(frm: datetime, to: datetime) -> dict:
    eng = _db_engine()
    with eng.begin() as conn:
        conn.execute(text("SET TIME ZONE 'America/New_York';"))
        _exec_sql(conn, DDL_SQL)

    rows = fetch_payments(frm, to)
    if not rows:
        return {"ok": True, "fetched": 0, "raw_appended": 0}

    df = pd.DataFrame(rows)
    df["_source_file"] = "api/payments"
    df = df.rename(columns={
        "id": "payment_id",
        "idCustomer": "customer_id",
        "customer": "customer_name",
        "amount": "amount",
        "paymentExpectedDate": "due_date",
        "paymentReceivedDate": "payment_date",
        "isPaid": "is_paid",
        "paymentMethod": "method",
        "note": "notes"
    })
    if "payload" not in df.columns:
        df["payload"] = None

    df.to_sql("raw_payments", con=eng, schema="public", if_exists="append", index=False)

    with eng.begin() as conn:
        count = conn.execute(text("""
            SELECT count(*) AS c FROM public.raw_payments
            WHERE _ingested_at = (SELECT max(_ingested_at) FROM public.raw_payments)
        """)).mappings().one()

    return {
        "ok": True,
        "fetched": len(rows),
        "raw_latest": count["c"]
    }