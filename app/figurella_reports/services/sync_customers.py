# app/figurella_reports/services/sync_customers.py
import os, time
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text
from .api_client import fetch_customers

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
CREATE TABLE IF NOT EXISTS public.raw_customers (
  _ingested_at           timestamptz DEFAULT now(),
  _source_file           text,
  "$id"                  bigint,
  id                     text,
  "centerCode"           text,
  name                   text,
  surname                text,
  email                  text,
  phone                  text,
  "birthDate"            text,
  "registrationDate"     text,
  "lastAppointmentDate"  text,
  "idStatus"             bigint,
  status                 text
);
CREATE INDEX IF NOT EXISTS idx_raw_customers_ingested_at ON public.raw_customers(_ingested_at);
CREATE INDEX IF NOT EXISTS idx_raw_customers_id ON public.raw_customers(id);

CREATE TABLE IF NOT EXISTS public.customers (
  id                    text PRIMARY KEY,
  center_code           text,
  name                  text,
  surname               text,
  email                 text,
  phone                 text,
  birth_date            date,
  registration_at       timestamptz,
  last_appointment_at   timestamptz,
  current_status        text,
  id_status             bigint,
  first_seen_at         timestamptz DEFAULT now(),
  last_seen_at          timestamptz DEFAULT now(),
  updated_at            timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_customers_status ON public.customers(current_status);
CREATE INDEX IF NOT EXISTS idx_customers_last_seen ON public.customers(last_seen_at);

CREATE TABLE IF NOT EXISTS public.customer_status_history (
  id           bigserial PRIMARY KEY,
  customer_id  text NOT NULL,
  status       text NOT NULL,
  valid_from   timestamptz NOT NULL,
  valid_to     timestamptz,
  changed_at   timestamptz DEFAULT now(),
  CONSTRAINT fk_status_customer FOREIGN KEY (customer_id)
    REFERENCES public.customers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_csh_customer_id ON public.customer_status_history(customer_id);
CREATE INDEX IF NOT EXISTS idx_csh_valid_from  ON public.customer_status_history(valid_from);
"""

UPSERT_SQL = """
WITH latest_raw AS (
  SELECT *
  FROM public.raw_customers
  WHERE _ingested_at = (SELECT max(_ingested_at) FROM public.raw_customers)
),
typed AS (
  SELECT
    id::text                                           AS id,
    "centerCode"                                       AS center_code,
    name, surname,
    lower(nullif(email, ''))                           AS email,
    regexp_replace(coalesce(phone,''), '\\D', '', 'g') AS phone,
    NULLIF("birthDate",'')::date                       AS birth_date,
    NULLIF("registrationDate",'')::timestamptz         AS registration_at,
    NULLIF("lastAppointmentDate",'')::timestamptz      AS last_appointment_at,
    status                                             AS current_status,
    "idStatus"                                         AS id_status
  FROM latest_raw
)
INSERT INTO public.customers AS c (
  id, center_code, name, surname, email, phone,
  birth_date, registration_at, last_appointment_at,
  current_status, id_status, last_seen_at, updated_at
)
SELECT
  t.id, t.center_code, t.name, t.surname, t.email, t.phone,
  t.birth_date, t.registration_at, t.last_appointment_at,
  t.current_status, t.id_status, now(), now()
FROM typed t
ON CONFLICT (id) DO UPDATE
SET center_code         = EXCLUDED.center_code,
    name                = EXCLUDED.name,
    surname             = EXCLUDED.surname,
    email               = EXCLUDED.email,
    phone               = EXCLUDED.phone,
    birth_date          = EXCLUDED.birth_date,
    registration_at     = EXCLUDED.registration_at,
    last_appointment_at = EXCLUDED.last_appointment_at,
    current_status      = EXCLUDED.current_status,
    id_status           = EXCLUDED.id_status,
    last_seen_at        = now(),
    updated_at          = now();
"""

SEED_SQL = """
INSERT INTO public.customer_status_history (customer_id, status, valid_from)
SELECT c.id, c.current_status, now()
FROM public.customers c
WHERE NOT EXISTS (
  SELECT 1 FROM public.customer_status_history h
  WHERE h.customer_id = c.id
);
"""

CLOSE_SQL = """
WITH latest_raw AS (
  SELECT id::text AS customer_id, status AS new_status
  FROM public.raw_customers
  WHERE _ingested_at = (SELECT max(_ingested_at) FROM public.raw_customers)
),
latest_hist AS (
  SELECT h1.*
  FROM public.customer_status_history h1
  JOIN (
    SELECT customer_id, max(valid_from) AS max_from
    FROM public.customer_status_history
    GROUP BY customer_id
  ) m ON m.customer_id = h1.customer_id AND m.max_from = h1.valid_from
),
changes AS (
  SELECT
    lr.customer_id,
    lr.new_status,
    lh.id AS old_row_id
  FROM latest_raw lr
  JOIN latest_hist lh ON lh.customer_id = lr.customer_id
  WHERE COALESCE(lr.new_status, '') <> COALESCE(lh.status, '')
)
UPDATE public.customer_status_history h
SET valid_to = now()
FROM changes ch
WHERE h.id = ch.old_row_id;
"""

INSERT_SQL = """
WITH latest_raw AS (
  SELECT id::text AS customer_id, status AS new_status
  FROM public.raw_customers
  WHERE _ingested_at = (SELECT max(_ingested_at) FROM public.raw_customers)
),
prev AS (
  SELECT h1.customer_id, h1.status AS prior_status
  FROM public.customer_status_history h1
  JOIN (
    SELECT customer_id, max(valid_from) AS max_from
    FROM public.customer_status_history
    GROUP BY customer_id
  ) m ON m.customer_id = h1.customer_id AND m.max_from = h1.valid_from
),
changes AS (
  SELECT lr.customer_id, lr.new_status
  FROM latest_raw lr
  JOIN prev p ON p.customer_id = lr.customer_id
  WHERE COALESCE(lr.new_status, '') <> COALESCE(p.prior_status, '')
)
INSERT INTO public.customer_status_history (customer_id, status, valid_from)
SELECT DISTINCT ch.customer_id, ch.new_status, now()
FROM changes ch;
"""

def sync_customers_to_supabase(frm: datetime) -> dict:
    eng = _db_engine()
    with eng.begin() as conn:
        conn.execute(text("SET TIME ZONE 'America/New_York';"))
        _exec_sql(conn, DDL_SQL)

    rows = fetch_customers(frm, datetime.now(timezone.utc))
    df = pd.DataFrame(rows)
    if df.empty:
        return {"ok": True, "fetched": 0, "raw_appended": 0, "upserted": 0, "history_updates": 0}

    wanted = ["$id", "id", "centerCode", "name", "surname", "email", "phone",
              "birthDate", "registrationDate", "lastAppointmentDate", "idStatus", "status"]
    for c in wanted:
        if c not in df.columns:
            df[c] = None
    df = df[wanted].copy()
    df["_source_file"] = "api/customers"
    df.to_sql("raw_customers", con=eng, schema="public", if_exists="append", index=False)

    with eng.begin() as conn:
        conn.execute(text(UPSERT_SQL))
        conn.execute(text(SEED_SQL))
        conn.execute(text(CLOSE_SQL))
        conn.execute(text(INSERT_SQL))

    with eng.begin() as conn:
        counts = conn.execute(text("""
            SELECT
              (SELECT count(*) FROM public.raw_customers
                 WHERE _ingested_at = (SELECT max(_ingested_at) FROM public.raw_customers)) AS raw_rows_latest,
              (SELECT count(*) FROM public.customers) AS customers_rows,
              (SELECT count(*) FROM public.customer_status_history) AS history_rows
        """)).mappings().one()

    return {
        "ok": True,
        "fetched": len(rows),
        "raw_latest": counts["raw_rows_latest"],
        "customers": counts["customers_rows"],
        "history": counts["history_rows"]
    }