# app/figurella_reports/services/location_performance/perf_metrics.py
from __future__ import annotations
import os, json, time
from pathlib import Path
from datetime import datetime, date, time as dtime, timedelta
from typing import Dict, Any, List, Iterable, Optional
import pandas as pd

try:
    from zoneinfo import ZoneInfo          # Python 3.9+
except ImportError:                         # pragma: no cover
    from pytz import timezone as ZoneInfo

# ─────────────────────────── configuration ───────────────────────────
NY = ZoneInfo("America/New_York")

AGENDA_HISTORY_XLSX = os.getenv("AGENDA_HISTORY_XLSX", "").strip()
ATTENDANCE_UNIQUE_CLIENTS = bool(int(os.getenv("ATTENDANCE_UNIQUE_CLIENTS", "0")))
ATTENDANCE_INCLUDE_CONSULTATIONS = bool(int(os.getenv("ATTENDANCE_INCLUDE_CONSULTATIONS", "1")))
ATTENDANCE_MODE = os.getenv("ATTENDANCE_MODE", "week").lower()        # 'week' | 'month'
ATTENDANCE_WEEK_START = os.getenv("ATTENDANCE_WEEK_START", "monday").lower()

# Cache location under instance
CACHE_DIRNAME = "figurella_reports"
CACHE_BASENAME = "perf_cache.json"

# Files that determine freshness of the snapshot
SOURCE_FILES = [
    "agenda_history.xlsx",
    "history_agenda.xlsx",        # allow your alternate name too
    "customers_history.xlsx",
]

# ─────────────────────────── cache helpers ───────────────────────────
def _cache_path(instance_dir: Path) -> Path:
    d = instance_dir / CACHE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d / CACHE_BASENAME

def _load_cache(instance_dir: Path) -> Dict[str, Any] | None:
    p = _cache_path(instance_dir)
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _save_cache(instance_dir: Path, payload: Dict[str, Any]) -> None:
    p = _cache_path(instance_dir)
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, p)

def _file_mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except FileNotFoundError:
        return 0.0

def _find_first(paths: Iterable[Path]) -> Optional[Path]:
    for p in paths:
        if p.exists():
            return p
    return None

def _resolve_sources(app_root: Path, instance_dir: Path) -> Dict[str, float]:
    """Return {filename: mtime} for each source that exists."""
    mtimes: Dict[str, float] = {}
    project_root = app_root.parent

    for name in SOURCE_FILES:
        found = _find_first([
            instance_dir / "figurella_reports" / name,
            instance_dir / name,
            app_root / name,
            project_root / name,
            Path.cwd() / name,
        ])
        if found:
            mtimes[name] = _file_mtime(found)
    return mtimes

def _is_stale(cache: Dict[str, Any] | None, src_mtimes: Dict[str, float]) -> bool:
    if not cache:
        return True
    cached = cache.get("meta", {}).get("source_mtimes", {})
    for k, mt in src_mtimes.items():
        if mt > float(cached.get(k, 0.0)):
            return True
    return False

# ───────────────────────────── helpers ─────────────────────────────
def _find_history_file(app_root: Path) -> Path | None:
    """
    Search common locations for the agenda history Excel file.
    Accepts an absolute AGENDA_HISTORY_XLSX as well.
    """
    if AGENDA_HISTORY_XLSX:
        p = Path(AGENDA_HISTORY_XLSX)
        if p.is_absolute() and p.exists():
            print(f"✅ Using absolute agenda history path: {p}")
            return p

    project_root = app_root.parent
    names = [AGENDA_HISTORY_XLSX] if AGENDA_HISTORY_XLSX else ["agenda_history.xlsx", "history_agenda.xlsx"]

    candidates: list[Path] = []
    for name in names:
        if not name:
            continue
        candidates += [
            app_root / "instance" / "figurella_reports" / name,
            app_root / name,
            project_root / name,
        ]

    for p in candidates:
        if p.exists():
            print(f"✅ Found agenda history: {p}")
            return p

    print("⚠️ Agenda history XLSX not found. Tried:", [str(p) for p in candidates])
    return None

def _week_start(d: datetime) -> datetime:
    """Return local week start at 00:00 based on ATTENDANCE_WEEK_START."""
    d = d.astimezone(NY).replace(hour=0, minute=0, second=0, microsecond=0)
    wd = d.weekday()  # Monday=0 ... Sunday=6
    if ATTENDANCE_WEEK_START == "sunday":
        days_back = (wd + 1) % 7
        return d - timedelta(days=days_back)
    return d - timedelta(days=wd)

def _week_bounds(ref: datetime, weeks_ago: int = 0):
    start = _week_start(ref) - timedelta(weeks=weeks_ago)
    end   = start + timedelta(days=7)
    return start, end

def _month_start(d: datetime) -> datetime:
    d = d.astimezone(NY).replace(hour=0, minute=0, second=0, microsecond=0)
    return d.replace(day=1)

def _add_months(d: datetime, n: int) -> datetime:
    y, m = d.year, d.month
    m2 = m + n
    y += (m2 - 1) // 12
    m2 = ((m2 - 1) % 12) + 1
    return d.replace(year=y, month=m2, day=1)

def _month_bounds(ref: datetime, months_ago: int = 0):
    start = _add_months(_month_start(ref), -months_ago)
    end   = _add_months(start, 1)
    return start, end

def _status_ok(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    return s.str.contains(r"\bOK\b", case=False, na=False)

def _not_consultation(series) -> pd.Series:
    if getattr(series, "dtype", None) is bool:
        return ~series
    s = series.astype(str).str.upper()
    return ~(s.isin(["TRUE", "1", "YES"]))

def _pick_flexible(df: pd.DataFrame, prefixes: list[str]) -> str | None:
    """Find first column whose name starts with any of the prefixes (case-insensitive)."""
    lower_cols = {c.lower(): c for c in df.columns}
    for p in prefixes:
        p = p.lower()
        for c_lower, original in lower_cols.items():
            if c_lower.startswith(p):
                return original
    return None

def _parse_time_like(s: pd.Series) -> pd.Series:
    """
    Parse start-time strings into datetime.time without the noisy inference warning.
    Tries a few common formats, then safe fallback to pandas.
    """
    if s.isna().all():
        return pd.Series([dtime(0, 0)] * len(s), index=s.index)

    # Try explicit formats first (fast & no warnings)
    formats = ["%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"]
    parsed = None
    for fmt in formats:
        try:
            parsed = pd.to_datetime(s, format=fmt, errors="coerce")
            if parsed.notna().mean() > 0.6:  # good enough
                break
        except Exception:
            parsed = None

    if parsed is None or parsed.isna().all():
        # Fallback: allow pandas/dateutil to guess for the remaining values
        parsed = pd.to_datetime(s, errors="coerce")

    t = parsed.dt.time
    if t.isna().all():
        return pd.Series([dtime(0, 0)] * len(s), index=s.index)
    return t.fillna(dtime(0, 0))

# ───────────────────────────── attendance ─────────────────────────────
def compute_weekly_attendance(app_root: Path) -> dict:
    """
    WEEK mode:
      This Week / Last Week / 2 Weeks Ago
    MONTH mode:
      This Month / Last Month / 2 Months Ago
    """
    path = _find_history_file(app_root)
    if not path:
        labels = ["This Week","Last Week","2 Weeks Ago"] if ATTENDANCE_MODE=="week" \
                 else ["This Month","Last Month","2 Months Ago"]
        return {"attendance":{"weeks":[
            {"label":labels[0], "count":0, "current":True},
            {"label":labels[1], "count":0},
            {"label":labels[2], "count":0},
        ]}}

    print(f"ℹ️ Reading agenda history: {path}")
    df = pd.read_excel(path)

    date_col     = _pick_flexible(df, ["appointmentDate", "appointment_date"])
    time_col     = _pick_flexible(df, ["startTime", "start_time", "startTi"])
    status_col   = _pick_flexible(df, ["statusString", "statusStr", "status"])
    consult_col  = _pick_flexible(df, ["isConsultation", "consultation", "consult"])
    cust_col     = _pick_flexible(df, ["customerId", "customer_id"])

    parsed_date = pd.to_datetime(df[date_col], utc=True, errors="coerce").dt.date if date_col else pd.Series([None]*len(df))
    if pd.isna(parsed_date).mean() > 0.8:
        alt = _pick_flexible(df, ["addedAt", "added_at"])
        if alt:
            parsed_date = pd.to_datetime(df[alt], errors="coerce").dt.date

    if pd.isna(parsed_date).all() or status_col is None:
        labels = ["This Week","Last Week","2 Weeks Ago"] if ATTENDANCE_MODE=="week" \
                 else ["This Month","Last Month","2 Months Ago"]
        print("⚠️ Could not parse usable dates or missing status column.")
        return {"attendance":{"weeks":[
            {"label":labels[0], "count":0, "current":True},
            {"label":labels[1], "count":0},
            {"label":labels[2], "count":0},
        ]}}

    # Build a local datetime from (local calendar date + local start time).
    if time_col and time_col in df.columns:
        tseries = _parse_time_like(df[time_col])
    else:
        tseries = pd.Series([dtime(0, 0)] * len(df))

    # Compose naive local datetimes, then assign NY tz (no UTC shift)
    local_dt = [
        datetime.combine(d if isinstance(d, date) else date.min, t).replace(tzinfo=NY)
        for d, t in zip(parsed_date, tseries)
    ]
    df["_local_date"] = pd.Series(local_dt).dt.date

    # Mask: OK status; consultations INCLUDED by default
    mask = _status_ok(df[status_col])
    if not ATTENDANCE_INCLUDE_CONSULTATIONS and consult_col and consult_col in df.columns:
        mask &= _not_consultation(df[consult_col])

    now = datetime.now(NY)
    out = []

    if ATTENDANCE_MODE == "month":
        labels = ["This Month", "Last Month", "2 Months Ago"]
        for idx, label in enumerate(labels):
            start, end = _month_bounds(now, months_ago=idx)
            sel = (df["_local_date"] >= start.date()) & (df["_local_date"] < end.date())
            sub = df.loc[sel & mask]
            if ATTENDANCE_UNIQUE_CLIENTS and cust_col in df.columns:
                count = sub[cust_col].nunique(dropna=True)
            else:
                count = len(sub)
            out.append({"label":label, "count":int(count), **({"current":True} if idx==0 else {})})
    else:
        labels = ["This Week", "Last Week", "2 Weeks Ago"]
        for idx, label in enumerate(labels):
            start, end = _week_bounds(now, weeks_ago=idx)
            sel = (df["_local_date"] >= start.date()) & (df["_local_date"] < end.date())
            sub = df.loc[sel & mask]
            if ATTENDANCE_UNIQUE_CLIENTS and cust_col in df.columns:
                count = sub[cust_col].nunique(dropna=True)
            else:
                count = len(sub)
            out.append({"label":label, "count":int(count), **({"current":True} if idx==0 else {})})

    print(f"✅ Attendance computed ({ATTENDANCE_MODE}, week_start={ATTENDANCE_WEEK_START}, "
          f"unique_clients={ATTENDANCE_UNIQUE_CLIENTS}, include_consults={ATTENDANCE_INCLUDE_CONSULTATIONS}): {out}")
    return {"attendance": {"weeks": out}}

# ─────────────────────── snapshot + public API ───────────────────────
def _compute_snapshot(app_root: Path, instance_dir: Path) -> Dict[str, Any]:
    """
    Build the snapshot dict that your UI expects.
    This implementation focuses on attendance (your code above).
    If you already have dedicated functions for active clients and new clients,
    you can import and call them here.
    """
    snapshot: Dict[str, Any] = {}

    # Attendance (always available from agenda history)
    snapshot.update(compute_weekly_attendance(app_root))

    # Graceful, optional hooks for your existing helpers:
    #   app/figurella_reports/services/location_performance/active_clients.py
    #   app/figurella_reports/services/location_performance/new_clients.py
    try:
        from .active_clients import compute_active_clients  # type: ignore
        snapshot["active_clients"] = compute_active_clients(Path(app_root), Path(instance_dir))
    except Exception:
        # keep existing UI tolerant — provide None or omit
        snapshot.setdefault("active_clients", None)

    try:
        from .new_clients import compute_new_clients_summary  # type: ignore
        snapshot["new_clients"] = compute_new_clients_summary(Path(app_root), Path(instance_dir))
    except Exception:
        snapshot.setdefault("new_clients", None)

    return snapshot

def get_perf_cached(app_root: Path, instance_dir: Path) -> Dict[str, Any]:
    """
    Fast path for routes/endpoints:
      - returns cached data if sources unchanged
      - recomputes + writes cache when any Excel source file mtime moves
    """
    src_mtimes = _resolve_sources(app_root, instance_dir)
    cache = _load_cache(instance_dir)

    if _is_stale(cache, src_mtimes):
        data = _compute_snapshot(app_root, instance_dir)
        payload = {
            "version": 1,
            "generated_at": time.time(),
            "meta": {"source_mtimes": src_mtimes},
            "data": data,
        }
        _save_cache(instance_dir, payload)
        return data

    return cache.get("data", {}) if cache else _compute_snapshot(app_root, instance_dir)

# ─────────────────────────── optional debug ───────────────────────────
def debug_two_weeks_ago(app_root: Path):
    """Prints a diagnostic breakdown for the '2 Weeks Ago' window."""
    path = _find_history_file(app_root)
    if not path:
        print("No history file found.")
        return
    df = pd.read_excel(path)

    date_col     = _pick_flexible(df, ["appointmentDate", "appointment_date"])
    time_col     = _pick_flexible(df, ["startTime", "start_time", "startTi"])
    status_col   = _pick_flexible(df, ["statusString", "statusStr", "status"])
    consult_col  = _pick_flexible(df, ["isConsultation", "consultation", "consult"])
    cust_col     = _pick_flexible(df, ["customerId", "customer_id"])

    parsed_date = pd.to_datetime(df[date_col], utc=True, errors="coerce").dt.date
    if time_col and time_col in df.columns:
        tseries = _parse_time_like(df[time_col])
    else:
        tseries = pd.Series([dtime(0, 0)]*len(df))

    local_dt = [datetime.combine(d, t).replace(tzinfo=NY) for d, t in zip(parsed_date, tseries)]
    df["_local_date"] = pd.Series(local_dt).dt.date

    now = datetime.now(NY)
    start, end = _week_bounds(now, weeks_ago=2)
    window = df[(df["_local_date"] >= start.date()) & (df["_local_date"] < end.date())].copy()
    window["is_ok"] = _status_ok(window[status_col])
    if consult_col:
        window["is_consult"] = window[consult_col].astype(str).str.upper().isin(["TRUE","1","YES"])
    else:
        window["is_consult"] = False

    print("— 2 Weeks Ago —")
    print("Window:", start.date(), "→", (end - timedelta(days=1)).date())
    print("Total rows in window:", len(window))
    print("OK:", window["is_ok"].sum())
    print("Consultations (all):", window["is_consult"].sum())
    print("OK (non-consult):", ((window["is_ok"]) & (~window["is_consult"])).sum())
    if ATTENDANCE_UNIQUE_CLIENTS and cust_col in df.columns:
        if ATTENDANCE_INCLUDE_CONSULTATIONS:
            uniq = window.loc[(window["is_ok"])]
        else:
            uniq = window.loc[(window["is_ok"]) & (~window["is_consult"])]
        print("Unique clients:", uniq[cust_col].nunique(dropna=True))
    print("Daily OK (effective) breakdown:")
    eff_mask = window["is_ok"]
    if not ATTENDANCE_INCLUDE_CONSULTATIONS:
        eff_mask &= (~window["is_consult"])
    print(window.loc[eff_mask].groupby("_local_date").size())
