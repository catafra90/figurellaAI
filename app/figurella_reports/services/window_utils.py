# app/figurella_reports/services/window_utils.py
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

def has_flag(flag: str) -> bool:
    return flag in sys.argv

def get_arg(flag: str, default: Optional[str] = None) -> Optional[str]:
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--"):
            return sys.argv[i + 1]
    return default

def parse_cli_date(flag: str, default_dt: datetime) -> datetime:
    val = get_arg(flag, None)
    if not val:
        return default_dt
    try:
        if len(val) == 10:
            d = datetime.fromisoformat(val).replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
            )
            return d
        d = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception as e:
        raise SystemExit(f"Invalid date for {flag}: {val} ({e})")

def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def compute_window() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if has_flag("--last-min"):
        mins = int(get_arg("--last-min", "5"))
        frm, to = now - timedelta(minutes=mins), now
    elif has_flag("--last-hours"):
        hrs = int(get_arg("--last-hours", "1"))
        frm, to = now - timedelta(hours=hrs), now
    elif has_flag("--last-days"):
        days = int(get_arg("--last-days", "31"))
        frm, to = now - timedelta(days=days), now
    else:
        frm, to = now - timedelta(days=31), now

    frm = parse_cli_date("--from", frm)
    to = parse_cli_date("--to", to)
    if frm > to:
        print(f"⚠️  from > to ({iso(frm)} > {iso(to)}). Swapping.")
        frm, to = to, frm

    print(f"🗓  GLOBAL WINDOW → {iso(frm)}  →  {iso(to)}")
    return frm, to