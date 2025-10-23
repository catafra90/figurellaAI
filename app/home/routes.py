# File: app/home/routes.py
from __future__ import annotations

from flask import Blueprint, render_template, url_for, current_app

# ✅ Import from services to avoid circular imports with calendar.routes
from app.calendar.services import get_today_upcoming

home_bp = Blueprint("home", __name__)


# ---------- helpers ----------
def _safe_url(endpoint: str, **values) -> str | None:
    """
    Resolve a Flask endpoint to a URL. If the endpoint doesn't exist or
    url_for raises, return None instead of crashing.
    """
    try:
        if endpoint in current_app.view_functions:
            return url_for(endpoint, **values)
    except Exception as e:
        current_app.logger.warning(f"[home/_safe_url] {endpoint} failed: {e}")
    return None


def _first_present(*endpoints: str) -> str | None:
    """
    Return the first endpoint name that exists in the app, else None.
    """
    vfs = current_app.view_functions
    for ep in endpoints:
        if ep and ep in vfs:
            return ep
    return None


def _best_endpoint(filter_fn, rank_key) -> str | None:
    """
    Heuristic endpoint finder: search url_map with a filter and pick
    the 'best' candidate via rank_key.
    """
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
    """
    Try endpoints in order via _safe_url; if none resolve, return a static fallback.
    """
    for ep in endpoints:
        u = _safe_url(ep)
        if u:
            return u
    return fallback


# ---------- route ----------
@home_bp.route("/")
def index():
    # ----- Charts (clients mgmt) -----
    charts_href = _resolve_or_fallback(
        "charts.view_charts", "charts.index",
        fallback="/charts"
    )

    # ----- Clients list -----
    clients_href = _resolve_or_fallback(
        "clients.clients", "clients.index",
        fallback="/clients"
    )

    # ----- Calendar -----
    calendar_href = _resolve_or_fallback(
        "calendar.view_calendar", "calendar.index", "calendar.ui", "calendar.ping",
        fallback="/calendar"
    )

    # ----- Reports (prefer main reports home) -----
    reports_ep = (
        _first_present(
            "reports_bp.reports_home",  # common name in your project
            "reports.index",
            "reports.home",
            "report.index",
            "report.home",
        )
        or _best_endpoint(
            lambda r: ("report" in r.endpoint.lower()) or ("report" in r.rule.lower()),
            lambda r: (
                0 if r.rule.rstrip("/").lower() in ("/reports", "/report") else 1,
                0 if r.endpoint.lower().endswith(".index") else 1,
                # exclude daily-checkin flavored routes
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

    # ----- Daily Check-in -----
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

    # ----- Nutrition (new section) -----
    # Deterministic: try url_for on the known endpoint, else hard fallback.
    try:
        nutrition_href = url_for("nutrition.index")
    except Exception:
        nutrition_href = "/nutrition/"

    # Fetch upcoming (today) items for the home notifications
    try:
        upcoming = get_today_upcoming(limit=6, tz="America/New_York")
    except Exception as e:
        current_app.logger.warning(f"[home/index] get_today_upcoming failed: {e}")
        upcoming = []

    # Log what we resolved (useful while wiring blueprints)
    current_app.logger.info(
        "[home/index] links: charts=%s, clients=%s, calendar=%s, reports_ep=%s -> %s, "
        "checkin_ep=%s -> %s, nutrition -> %s, upcoming=%s",
        charts_href, clients_href, calendar_href,
        reports_ep, reports_href,
        checkin_ep, checkins_href,
        nutrition_href,
        len(upcoming),
    )

    # Bundle links for the template (so Jinja never calls url_for directly)
    links = {
        "charts": charts_href,
        "clients": clients_href,
        "calendar": calendar_href,
        "reports": reports_href,
        "checkins": checkins_href,
        "nutrition": nutrition_href,
    }

    return render_template(
        "index.html",
        active_page="home",
        links=links,
        reports_ok=bool(reports_ep),
        checkins_ok=bool(checkin_ep),
        # notifications context
        upcoming_calendar=upcoming,
        has_upcoming=bool(upcoming),
    )
