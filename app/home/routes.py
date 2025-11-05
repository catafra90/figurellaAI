# File: app/home/routes.py
from __future__ import annotations

from flask import Blueprint, render_template, url_for, current_app

# ✅ Import from services to avoid circular imports with calendar.routes
from app.calendar.services import get_today_upcoming

home_bp = Blueprint("home", __name__)


# ---------- helpers ----------
def _safe_url(endpoint: str, **values) -> str | None:
    try:
        if endpoint in current_app.view_functions:
            return url_for(endpoint, **values)
    except Exception as e:
        current_app.logger.warning(f"[home/_safe_url] {endpoint} failed: {e}")
    return None


def _first_present(*endpoints: str) -> str | None:
    vfs = current_app.view_functions
    for ep in endpoints:
        if ep and ep in vfs:
            return ep
    return None


def _best_endpoint(filter_fn, rank_key) -> str | None:
    try:
        rules = list(current_app.url_map.iter_rules())
    except Exception:
        rules = []
    candidates = [r for r in rules if filter_fn(r)]
    if not candidates:
        return None
    chosen = sorted(candidates, key=rank_key)[0]
    return chosen.endpoint


def _resolve_or_fallback(*endpoints: str, fallback: str = "/") -> str:
    for ep in endpoints:
        u = _safe_url(ep)
        if u:
            return u
    return fallback


# ---------- Leads data (service → fallback) ----------
def _default_leads_data() -> dict:
    """Zeroed shape used by the template when no data is available."""
    return {
        "RENEW": 0,
        "OK_paid": 0,
        "OK_organic": 0,
        "FLOP": 0,
        "TRY_TO_OK": 0,
        "TRY": 0,
        "NV": 0,
        "LEADS_paid": 0,
        "LEADS_organic": 0,
    }


def _load_leads_data() -> dict:
    """
    Try to pull stats from a service, otherwise return a zeroed structure.
    Expected service:
      app.figurella_reports.services.leads_statistics.get_leads_stats() -> dict
    """
    try:
        from app.figurella_reports.services.leads_statistics import get_leads_stats  # type: ignore
        data = get_leads_stats()
        if not isinstance(data, dict):
            raise TypeError("get_leads_stats() must return dict")
        base = _default_leads_data()
        base.update({k: (int(v) if v is not None else 0) for k, v in data.items()})
        return base
    except Exception as e:
        current_app.logger.warning(f"[home/_load_leads_data] using defaults: {e}")
        return _default_leads_data()


# ---------- Clients lifecycle (service → fallback) ----------
def _default_clients_lifecycle() -> dict:
    """Zeroed shape for the Total Clients Ever card."""
    return {
        "abandon_1m": 0,
        "abandon_3m": 0,
        "abandon_6m": 0,
        "abandon_1y": 0,
        "active": 0,
    }


def _load_clients_lifecycle() -> dict:
    """
    Try to pull lifecycle stats from a service, otherwise return zeros.
    Expected service:
      app.figurella_reports.services.clients_lifecycle.get_clients_lifecycle() -> dict
    It should return keys in _default_clients_lifecycle().
    """
    try:
        from app.figurella_reports.services.clients_lifecycle import get_clients_lifecycle  # type: ignore
        data = get_clients_lifecycle()
        if not isinstance(data, dict):
            raise TypeError("get_clients_lifecycle() must return dict")
        base = _default_clients_lifecycle()
        # coerce values to int safely
        base.update({k: (int(v) if v is not None else 0) for k, v in data.items()})
        return base
    except Exception as e:
        current_app.logger.warning(f"[home/_load_clients_lifecycle] using defaults: {e}")
        return _default_clients_lifecycle()


# ---------- route ----------
@home_bp.route("/")
def index():
    charts_href = _resolve_or_fallback("charts.view_charts", "charts.index", fallback="/charts")
    clients_href = _resolve_or_fallback("clients.clients", "clients.index", fallback="/clients")
    calendar_href = _resolve_or_fallback(
        "calendar.view_calendar", "calendar.index", "calendar.ui", "calendar.ping", fallback="/calendar"
    )

    reports_ep = (
        _first_present(
            "reports_bp.reports_home", "reports.index", "reports.home", "report.index", "report.home",
        )
        or _best_endpoint(
            lambda r: ("report" in r.endpoint.lower()) or ("report" in r.rule.lower()),
            lambda r: (
                0 if r.rule.rstrip("/").lower() in ("/reports", "/report") else 1,
                0 if r.endpoint.lower().endswith(".index") else 1,
                0
                if (
                    "daily" not in r.endpoint.lower()
                    and "daily" not in r.rule.lower()
                    and "checkin" not in r.endpoint.lower()
                    and "checkin" not in r.rule.lower()
                )
                else 1,
                len([p for p in r.rule.strip("/").split("/") if p]),
            ),
        )
    )
    reports_href = (_safe_url(reports_ep) if reports_ep else None) or "/figurella-reports"

    checkin_ep = (
        _first_present(
            "daily_checkin.report_home",
            "daily_checkin.index",
            "daily_checkin_bp.report_home",
            "checkin.index",
            "checkins.index",
            "calendar.daily_checkin",
        )
        or _best_endpoint(
            lambda r: (
                "checkin" in r.endpoint.lower()
                or "checkin" in r.rule.lower()
                or ("daily" in r.rule.lower() and "check" in r.rule.lower())
                or ("daily" in r.endpoint.lower() and "check" in r.endpoint.lower())
            ),
            lambda r: (
                0 if ("checkin" in r.endpoint.lower() or "checkin" in r.rule.lower()) else 1,
                0 if ("daily" in r.endpoint.lower() or "daily" in r.rule.lower()) else 1,
                len([p for p in r.rule.strip("/").split("/") if p]),
            ),
        )
    )
    checkins_href = (_safe_url(checkin_ep) if checkin_ep else None) or "/daily-check-in/"

    try:
        nutrition_href = url_for("nutrition.index")
    except Exception:
        nutrition_href = "/nutrition/"

    try:
        upcoming = get_today_upcoming(limit=6, tz="America/New_York")
    except Exception as e:
        current_app.logger.warning(f"[home/index] get_today_upcoming failed: {e}")
        upcoming = []

    current_app.logger.info(
        "[home/index] links: charts=%s, clients=%s, calendar=%s, reports_ep=%s -> %s, "
        "checkin_ep=%s -> %s, nutrition -> %s, upcoming=%s",
        charts_href,
        clients_href,
        calendar_href,
        reports_ep,
        reports_href,
        checkin_ep,
        checkins_href,
        nutrition_href,
        len(upcoming),
    )

    links = {
        "charts": charts_href,
        "clients": clients_href,
        "calendar": calendar_href,
        "reports": reports_href,
        "checkins": checkins_href,
        "nutrition": nutrition_href,
        # "consultation": _resolve_or_fallback("consultation.index", fallback="/consultation/"),  # optional
    }

    # ---- Cards data ----
    SALES_DATA = {
        "total": 18200,
        "cash": 9300,
        "payments": 5500,
        "internal": 1200,
        "newClients": 2200,
    }

    LEADS_DATA = _load_leads_data()
    CLIENTS_LIFECYCLE = _load_clients_lifecycle()

    return render_template(
        "index.html",
        active_page="home",
        links=links,
        reports_ok=bool(reports_ep),
        checkins_ok=bool(checkin_ep),
        upcoming_calendar=upcoming,
        has_upcoming=bool(upcoming),
        SALES_DATA=SALES_DATA,           # Sales card
        LEADS_DATA=LEADS_DATA,           # Leads card
        CLIENTS_LIFECYCLE=CLIENTS_LIFECYCLE,  # Total Clients Ever card
    )
