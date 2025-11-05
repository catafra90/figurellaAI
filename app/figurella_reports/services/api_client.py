# app/figurella_reports/services/api_client.py
import os, time, re, json
from typing import Any, Dict, List, Optional
from datetime import datetime, date, timezone, timedelta

import requests
from requests import Response, Session

from .window_utils import iso

API_BASE    = os.getenv("FIGURELLA_API_BASE", "https://apifigurella.hosting.memetic.it")
API_KEY     = os.getenv("FIGURELLA_API_KEY")
CENTER_CODE = os.getenv("FIGURELLA_CENTER_CODE", "NEWTO")

# Shared HTTP settings
_DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}
_DEFAULT_TIMEOUT = 60  # seconds
_MAX_RETRIES     = 3
_RETRY_BACKOFF   = 0.75  # seconds; 0.75, 1.5, 3.0 ...

# Reuse a session for connection pooling
_session: Session = requests.Session()
_session.headers.update(_DEFAULT_HEADERS)

# ───────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def _require_api_key() -> None:
    if not API_KEY:
        raise RuntimeError("FIGURELLA_API_KEY is not set in the environment.")

def _parse_dt_relaxed(s: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO strings or YYYY-MM-DD.
    - If date-only, return naive datetime at 00:00 (we'll compare by .date()).
    - If tz-aware, convert to UTC. If naive datetime, keep naive.
    """
    if not s:
        return None
    s2 = str(s).strip()
    try:
        if _DATE_ONLY_RE.match(s2):
            return datetime.strptime(s2, "%Y-%m-%d")
        dt = datetime.fromisoformat(s2.replace("Z", "+00:00"))
        return dt if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        return None

def _to_date(d: Optional[datetime]) -> Optional[date]:
    return d.date() if d else None

def _sleep_backoff(attempt: int, retry_after: Optional[float] = None) -> None:
    """
    Backoff: respect Retry-After header if present, else exponential.
    attempt is 0-based.
    """
    if retry_after is not None and retry_after > 0:
        time.sleep(retry_after)
        return
    delay = _RETRY_BACKOFF * (2 ** attempt)
    time.sleep(delay)

def _join_url(base: str, path: str) -> str:
    b = base.rstrip("/")
    p = path.lstrip("/")
    return f"{b}/{p}"

def _retry_after_seconds(resp: Response) -> Optional[float]:
    ra = resp.headers.get("Retry-After")
    if not ra:
        return None
    try:
        # Retry-After can be seconds or HTTP-date; we handle seconds.
        return float(ra)
    except Exception:
        return None

def _post_json(path: str, payload: Dict[str, Any], *, timeout: int = _DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """
    POST JSON with retry/backoff on transient errors (>=500, 429, or connection issues).
    Raises if 4xx (except 429) or persistent failure.
    Returns parsed JSON object (dict) or {}.
    """
    _require_api_key()
    url = _join_url(API_BASE, path)
    last_exc: Optional[Exception] = None

    for attempt in range(_MAX_RETRIES):
        try:
            resp: Response = _session.post(url, json=payload, timeout=timeout)

            # 429 rate limit → retry honoring Retry-After if provided
            if resp.status_code == 429:
                last_exc = RuntimeError(f"Rate limited (429) on {path}")
                _sleep_backoff(attempt, _retry_after_seconds(resp))
                continue

            # Retry on 5xx
            if 500 <= resp.status_code < 600:
                last_exc = RuntimeError(f"Server error {resp.status_code} on {path}")
                _sleep_backoff(attempt)
                continue

            # For other 4xx, raise immediately with body snippet
            resp.raise_for_status()

            # Parse JSON (be tolerant of empty/whitespace)
            text = (resp.text or "").strip()
            if not text:
                return {}
            try:
                data = resp.json()
            except json.JSONDecodeError:
                data = json.loads(text)

            return data if isinstance(data, dict) else {"data": data}

        except (requests.ConnectionError, requests.Timeout) as e:
            # network/timeout → retry
            last_exc = e
            _sleep_backoff(attempt)
            continue
        except Exception:
            # non-retriable (e.g., 4xx other than 429)
            raise

    # Retries exhausted
    assert last_exc is not None
    raise RuntimeError(f"POST {path} failed after {_MAX_RETRIES} retries") from last_exc

# ───────────────────────────────────────────────────────────────
# Internal: fetch all customers (paged)
# ───────────────────────────────────────────────────────────────
def _fetch_all_customers(*, center_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """Page through ALL customers (skip/take)."""
    _require_api_key()
    all_rows: List[Dict[str, Any]] = []
    skip, take = 0, 500
    cc = center_code or CENTER_CODE

    while True:
        payload: Dict[str, Any] = {
            "token": API_KEY,
            "centerCode": cc,
            "skip": skip,
            "take": take,
        }
        data = _post_json("Customers/List", payload, timeout=30)
        rows = (data or {}).get("customers", []) or []
        all_rows.extend(rows)
        if len(rows) < take:
            break
        skip += take
        # small throttle to be nice to the API
        time.sleep(0.4)

    return all_rows

# ───────────────────────────────────────────────────────────────
# PUBLIC: CUSTOMERS
# ───────────────────────────────────────────────────────────────
def fetch_customers(frm: datetime, to: datetime, mode: str = "all", *, center_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    mode = "all"       → full roster (ignores dates).
    mode = "windowed"  → include customers whose personal timeline overlaps the window:
                         start = registrationDate
                         end   = lastAppointmentDate if present, else treat as window 'to'
                         include if start <= to AND end >= from  (overlap by calendar day)

    center_code can override FIGURELLA_CENTER_CODE for this call only.
    """
    rows = _fetch_all_customers(center_code=center_code)

    if mode == "all":
        return rows

    # Compare by calendar day (avoid tz edge cases)
    f_date = (frm.astimezone(timezone.utc) if frm.tzinfo else frm).date()
    t_date = (to.astimezone(timezone.utc)  if to.tzinfo  else to ).date()

    filtered: List[Dict[str, Any]] = []
    for rec in rows:
        reg_d  = _to_date(_parse_dt_relaxed(rec.get("registrationDate")))
        last_d = _to_date(_parse_dt_relaxed(rec.get("lastAppointmentDate")))
        if reg_d is None:
            # can't place in time → skip
            continue

        # If no last appointment, treat as still existing up to the window end
        end_d = last_d or t_date

        # Overlap test: [reg_d, end_d] ∩ [f_date, t_date] ≠ ∅
        if reg_d <= t_date and end_d >= f_date:
            filtered.append(rec)

    return filtered

# ───────────────────────────────────────────────────────────────
# PUBLIC: PAYMENTS
# ───────────────────────────────────────────────────────────────
def fetch_payments(frm: datetime, to: datetime, *, center_code: Optional[str] = None) -> List[Dict[str, Any]]:
    cc = center_code or CENTER_CODE
    payload = {
        "token": API_KEY,
        "centerCode": cc,
        "from": iso(frm),
        "to": iso(to),
        "includeDuePayments": True,
        "includeDonePayments": True,
    }
    data = _post_json("Payments/List", payload, timeout=_DEFAULT_TIMEOUT)
    return (data or {}).get("payments", []) or []

# ───────────────────────────────────────────────────────────────
# PUBLIC: AGENDA
# ───────────────────────────────────────────────────────────────
def fetch_agenda(frm: datetime, to: datetime, *, center_code: Optional[str] = None) -> List[Dict[str, Any]]:
    cc = center_code or CENTER_CODE
    payload = {
        "token": API_KEY,
        "centerCode": cc,
        "from": iso(frm),
        "to": iso(to),
    }
    data = _post_json("Agenda/List", payload, timeout=_DEFAULT_TIMEOUT)
    return (data or {}).get("agendas", []) or []

# ───────────────────────────────────────────────────────────────
# PUBLIC: CONTRACTS
# ───────────────────────────────────────────────────────────────
def fetch_contracts(frm: datetime, to: datetime, *, center_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    POST /Contract/List
    Returns a list of ContractDto (each may include 'sales': [SaleDto,...]).
    """
    cc = center_code or CENTER_CODE
    payload = {
        "token": API_KEY,
        "centerCode": cc,
        "from": iso(frm),
        "to": iso(to),
    }
    data = _post_json("Contract/List", payload, timeout=_DEFAULT_TIMEOUT)
    return (data or {}).get("contracts", []) or []

# ───────────────────────────────────────────────────────────────
# NEW: CUSTOMER NOTES
# ───────────────────────────────────────────────────────────────
def fetch_customer_notes(
    note_created_after: datetime | str,
    *,
    center_code: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    POST /Customers/ListNotes
    Body:
      {
        "noteCreatedAfter": "<ISO-UTC>",
        "token": "<api-key>",
        "centerCode": "<center>"
      }

    note_created_after can be a datetime (any tz) or an ISO string.
    """
    cc = center_code or CENTER_CODE

    if isinstance(note_created_after, datetime):
        cutoff_iso = iso(note_created_after)  # ensures UTC '...Z'
    else:
        # Accept strings like "YYYY-MM-DD" or ISO; normalize to UTC ISO
        parsed = _parse_dt_relaxed(note_created_after)
        if parsed is None:
            raise ValueError(f"Invalid note_created_after value: {note_created_after!r}")
        cutoff_iso = iso(parsed)

    payload = {
        "token": API_KEY,
        "centerCode": cc,
        "noteCreatedAfter": cutoff_iso,
    }
    data = _post_json("Customers/ListNotes", payload, timeout=_DEFAULT_TIMEOUT)
    # API shape (per spec/image): {"customers":[{...}], "totalCount":0, ...}
    return (data or {}).get("customers", []) or []
# ... keep your imports and previous code ...

# ───────────────────────────────────────────────────────────────
# RANGE: CUSTOMER NOTES (robust, with forward/backward sweeps)
# ───────────────────────────────────────────────────────────────
def fetch_customer_notes_range(
    frm: datetime,
    to: datetime,
    *,
    center_code: Optional[str] = None,
    chunk_days: int = 30,
) -> List[Dict[str, Any]]:
    """
    Attempts to pull notes across [frm, to] even if the backend only accepts 'noteCreatedAfter'.
    Strategy:
      1) Forward sweep: start at frm, move cursor → max(createdOn)+1s.
      2) If forward returns empty/only the most recent month, try a backward sweep:
         start at 'to', call with after = cursor - chunk_days (server may ignore this),
         then keep only items createdOn ∈ (cursor - chunk_days, cursor].
      3) De-duplicate by (id, customerId) across all batches.
      4) Strictly filter to createdOn ≤ to (UTC) and createdOn ≥ frm.
    Also prints diagnostics about the earliest and latest timestamps returned so you can
    see if the backend is capping the window server-side.
    """
    cc = center_code or CENTER_CODE
    start = frm if frm.tzinfo else frm.replace(tzinfo=timezone.utc)
    end   = to  if to.tzinfo  else to.replace(tzinfo=timezone.utc)

    def _parse_utc(co: Any) -> Optional[datetime]:
        if not co:
            return None
        try:
            dt = datetime.fromisoformat(str(co).replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def _call_after(after_dt: datetime) -> List[Dict[str, Any]]:
        payload = {
            "token": API_KEY,
            "centerCode": cc,
            "noteCreatedAfter": iso(after_dt),
        }
        data = _post_json("Customers/ListNotes", payload, timeout=_DEFAULT_TIMEOUT)
        return (data or {}).get("customers", []) or []

    # ── Forward sweep
    forward: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    cursor = start
    safety = 1000
    while cursor < end and safety > 0:
        safety -= 1
        batch = _call_after(cursor)
        if not batch:
            # Nothing from this cursor → jump ahead by chunk (keeps loop moving)
            cursor = cursor + timedelta(days=chunk_days)
            continue

        # Merge with de-dupe
        for r in batch:
            kid = f"{str(r.get('id','')).strip()}|{str(r.get('customerId','')).strip()}"
            if kid not in seen_keys:
                seen_keys.add(kid)
                forward.append(r)

        # Advance cursor to just after the max createdOn we saw
        mx = None
        for r in batch:
            dt = _parse_utc(r.get("createdOn"))
            if dt and (mx is None or dt > mx):
                mx = dt
        if mx is None:
            cursor = cursor + timedelta(days=chunk_days)
        else:
            cursor = mx + timedelta(seconds=1)
        time.sleep(0.2)

    # Quick diagnostic for forward pass
    if forward:
        times = [t for t in (_parse_utc(r.get("createdOn")) for r in forward) if t]
        f_min = min(times) if times else None
        f_max = max(times) if times else None
        print(f"[Notes forward] batches={len(forward)} "
              f"min={f_min.isoformat() if f_min else 'n/a'} "
              f"max={f_max.isoformat() if f_max else 'n/a'}")

    # If forward brought data older than ~30–31 days from NOW, great; if not, try backward.
    result = forward[:]
    if not result:
        print("[Notes] Forward sweep yielded no data; attempting backward sweep.")

    # ── Backward sweep (helps if provider ignores 'after' far in the past)
    # Walk backward by chunk, filter each batch to (cursor-chunk, cursor].
    back_seen = seen_keys.copy()
    cursor_b = end
    safety_b = 1000
    backward: List[Dict[str, Any]] = []
    while cursor_b > start and safety_b > 0:
        safety_b -= 1
        window_start = cursor_b - timedelta(days=chunk_days)

        # We still have to call with 'after=window_start', knowing backend may ignore it.
        batch = _call_after(window_start)

        # keep only those with createdOn ∈ (window_start, cursor_b]
        for r in batch:
            dt = _parse_utc(r.get("createdOn"))
            if dt and (window_start < dt <= cursor_b):
                kid = f"{str(r.get('id','')).strip()}|{str(r.get('customerId','')).strip()}"
                if kid not in back_seen:
                    back_seen.add(kid)
                    backward.append(r)

        cursor_b = window_start - timedelta(seconds=1)
        time.sleep(0.2)

    if backward:
        times = [t for t in (_parse_utc(r.get("createdOn")) for r in backward) if t]
        b_min = min(times) if times else None
        b_max = max(times) if times else None
        print(f"[Notes backward] batches={len(backward)} "
              f"min={b_min.isoformat() if b_min else 'n/a'} "
              f"max={b_max.isoformat() if b_max else 'n/a'}")

    # Merge forward + backward, de-dupe again (in case of overlap)
    all_rows: List[Dict[str, Any]] = []
    final_keys: set[str] = set()
    for part in (result, backward):
        for r in part:
            kid = f"{str(r.get('id','')).strip()}|{str(r.get('customerId','')).strip()}"
            if kid not in final_keys:
                final_keys.add(kid)
                all_rows.append(r)

    # Strictly filter to [start, end]
    filtered: List[Dict[str, Any]] = []
    for r in all_rows:
        dt = _parse_utc(r.get("createdOn"))
        if not dt:
            # keep unknowns
            filtered.append(r)
        elif start <= dt <= end:
            filtered.append(r)

    # Final diagnostic: what did we actually get vs asked
    if filtered:
        times = [t for t in (_parse_utc(r.get("createdOn")) for r in filtered) if t]
        g_min = min(times) if times else None
        g_max = max(times) if times else None
        print(f"[Notes result] window={start.isoformat()} → {end.isoformat()} | "
              f"got={len(filtered)} rows, range={g_min.isoformat() if g_min else 'n/a'} → {g_max.isoformat() if g_max else 'n/a'}")
        # Heuristic: if g_min is still within ~31 days of 'now', provider likely caps older data
        try:
            now_utc = datetime.now(timezone.utc)
            if g_min and (now_utc - g_min).days <= 35 and start < (now_utc - timedelta(days=60)):
                print("⚠️  Provider likely caps this endpoint to ~last month; older notes may not be retrievable via ListNotes.")
        except Exception:
            pass
    else:
        print(f"[Notes result] No rows in requested window {start.isoformat()} → {end.isoformat()}.")

    return filtered
