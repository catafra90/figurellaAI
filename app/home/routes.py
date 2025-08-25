# app/home/routes.py
from flask import Blueprint, render_template, url_for, current_app

home_bp = Blueprint("home", __name__)

def _safe_url(endpoint: str, **values) -> str | None:
    try:
        if endpoint in current_app.view_functions:
            return url_for(endpoint, **values)
    except Exception:
        pass
    return None

@home_bp.route("/")
def index():
    vfs = current_app.view_functions  # endpoint -> callable

    def first_present(names: list[str]) -> str | None:
        for ep in names:
            if ep in vfs:
                return ep
        return None

    # Generic rule finder with ranking
    def best_endpoint(filter_fn, rank_key):
        try:
            rules = list(current_app.url_map.iter_rules())
        except Exception:
            rules = []
        candidates = [r for r in rules if filter_fn(r)]
        if not candidates:
            return None
        chosen = sorted(candidates, key=rank_key)[0]
        return chosen.endpoint

    # ---------- REPORTS (prefer your main index) ----------
    reports_ep = (
        first_present([
            "reports.index",          # << your canonical reports endpoint
            "reports.home", "reports.dashboard",
            "report.index", "report.home",
        ])
        or best_endpoint(
            lambda r: ("report" in r.endpoint.lower()) or ("report" in r.rule.lower()),
            lambda r: (
                0 if r.rule.rstrip("/").lower() in ("/reports", "/report") else 1,
                0 if r.endpoint.lower().endswith(".index") else 1,
                0 if ("daily" not in r.endpoint.lower() and "daily" not in r.rule.lower()
                      and "checkin" not in r.endpoint.lower() and "checkin" not in r.rule.lower())
                  else 1,
                len([p for p in r.rule.strip("/").split("/") if p]),
            )
        )
    )

    # ---------- DAILY CHECK-IN (prefer your real endpoint) ----------
    checkin_ep = (
        first_present([
            "daily_checkin_bp.report_home",  # << your real endpoint
            "checkin.index", "checkins.index",
            "calendar.daily_checkin", "calendar.checkin",
            "calendar.checkins", "calendar.today_checkin",
            "daily_checkin.index", "daily_checkin.report_home",
        ])
        or best_endpoint(
            lambda r: (
                "checkin" in r.endpoint.lower() or "checkin" in r.rule.lower()
                or ("daily" in r.rule.lower() and "check" in r.rule.lower())
                or ("daily" in r.endpoint.lower() and "check" in r.endpoint.lower())
            ),
            lambda r: (
                0 if ("checkin" in r.endpoint.lower() or "checkin" in r.rule.lower()) else 1,
                0 if ("daily" in r.endpoint.lower() or "daily" in r.rule.lower()) else 1,
                len([p for p in r.rule.strip("/").split("/") if p]),
            )
        )
    )

    # ---------- Calendar safe href ----------
    calendar_href = (
        _safe_url('calendar.index')
        or _safe_url('calendar.ui')
        or _safe_url('calendar.ping')
        or '/calendar'
    )

    current_app.logger.info(f"[home/index] reports_ep={reports_ep} checkin_ep={checkin_ep}")

    return render_template(
        "index.html",
        active_page="home",
        reports_ok=bool(reports_ep),
        reports_ep=reports_ep,
        checkin_ep=checkin_ep,
        calendar_href=calendar_href,
    )
