# app/nutrition/routes.py
from __future__ import annotations

from flask import Blueprint, render_template, url_for, current_app

bp = Blueprint(
    "nutrition",
    __name__,
    url_prefix="/nutrition",
    # No template_folder needed since we render from app/templates/nutrition/...
)

# ---------- helpers (mirrors home) ----------
def _safe_url(endpoint: str, **values) -> str | None:
    try:
        if endpoint in current_app.view_functions:
            return url_for(endpoint, **values)
    except Exception as e:
        current_app.logger.warning(f"[nutrition/_safe_url] {endpoint} failed: {e}")
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


# ---------- routes ----------
@bp.get("/")
def index():
    # Build the same links dict used on Home so base.html/header works.
    charts_href = (
        _safe_url("charts.view_charts")
        or _safe_url("charts.index")
        or "/charts"
    )

    clients_href = (
        _safe_url("clients.clients")
        or _safe_url("clients.index")
        or "/clients"
    )

    calendar_href = (
        _safe_url("calendar.view_calendar")
        or _safe_url("calendar.index")
        or _safe_url("calendar.ui")
        or _safe_url("calendar.ping")
        or "/calendar"
    )

    reports_ep = (
        _first_present(
            "reports_bp.reports_home",
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

    nutrition_href = _safe_url("nutrition.index") or "/nutrition"

    links = {
        "charts": charts_href,
        "clients": clients_href,
        "calendar": calendar_href,
        "reports": reports_href,
        "checkins": checkins_href,
        "nutrition": nutrition_href,
    }

    # ⬇️ Critical change: render the namespaced template
    return render_template(
        "nutrition/index.html",
        title="Nutrition",
        active_page="nutrition",
        links=links,
        reports_ok=bool(reports_ep),
        checkins_ok=bool(checkin_ep),
    )
