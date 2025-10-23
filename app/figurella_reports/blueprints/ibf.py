# app/figurella_reports/ibf.py
from flask import Blueprint, render_template, request, flash, jsonify

# --- service imports ---------------------------------------------------------
from ..services.active_clients_service import (
    build_wide_view_context,
    build_active_clients_payload,
)
from ..services.ibf_frequency_service import (
    ibf_months_for_client,
    ibf_best_year_months_for_client,
)
from ..services.ibf_first_session_service import get_first_contract_date_for_client

bp = Blueprint("ibf_bp", __name__, url_prefix="/figurella-reports/ibf")


# ----------------------------- Views -----------------------------------------
@bp.get("/wide/view")
def wide_view():
    """
    IBF portal-style grid:
      Client | <mm - yyyy> ... | Date Start First Contract | Date Start Last Contract | Bubble | Cellushape
    Optional query params:
      ?from=YYYY-MM&to=YYYY-MM  (inclusive)
    """
    from_ym = request.args.get("from")
    to_ym   = request.args.get("to")

    cols, rows = build_wide_view_context(from_ym, to_ym)
    if not cols:
        flash("No IBF data found in the selected range.", "warning")

    return render_template(
        "figurella_reports/ibf_wide.html",
        title="IBF — Portal Layout",
        columns=cols,
        rows=rows,
    )


# Keep link compatibility: /history/view -> wide view
@bp.get("/history/view")
def history_view():
    return wide_view()


# ----------------------------- APIs ------------------------------------------
@bp.get("/frequency")
def ibf_frequency():
    """
    Two modes:
      1) Per-client month map (what charts need):
         /figurella-reports/ibf/frequency?client=First%20Last&start=YYYY-MM-DD&end=YYYY-MM-DD
         -> {"months": { "Jan": 0, ... }}

      2) Legacy aggregate (no client param): returns active-clients payload used elsewhere.
    """
    client_q = (request.args.get("client") or "").strip()
    if client_q:
        start_q = (request.args.get("start") or "").strip() or None
        end_q   = (request.args.get("end") or "").strip() or None
        months  = ibf_months_for_client(client_q, start_q, end_q)
        return jsonify({"months": months})

    # ---- Legacy aggregate mode (no client) ----
    year_q  = (request.args.get("year") or "").strip()
    start_q = (request.args.get("start") or "").strip() or None
    end_q   = (request.args.get("end") or "").strip() or None

    try:
        year = int(year_q) if year_q else None
    except Exception:
        year = None

    try:
        payload = build_active_clients_payload(year=year, start=start_q, end=end_q)
        return jsonify(payload)
    except Exception as e:
        # Keep a stable JSON envelope (HTTP 200 for compatibility)
        return jsonify({
            "ok": False,
            "error": str(e),
            "months": {},
            "clients": {},
            "from": start_q or "",
            "to": end_q or "",
        }), 200


@bp.get("/frequency/best")
def ibf_frequency_best():
    """
    Month map for the single *best* (most active) year for a client.
      ?client=First%20Last
      -> {"months": { "Jan": 0, ... }}
    """
    client_q = (request.args.get("client") or "").strip()
    months = ibf_best_year_months_for_client(client_q) if client_q else {}
    return jsonify({"months": months})


@bp.get("/client/first_contract")
def ibf_first_contract():
    """
    Lookup first-contract (first-session) date for a client.
      ?client=First%20Last
      -> {"first_contract_date": "YYYY-MM-DD"}  or {"first_contract_date": null}
    """
    client_q = (request.args.get("client") or "").strip()
    first_d  = get_first_contract_date_for_client(client_q) if client_q else None
    return jsonify({"first_contract_date": first_d})


# ------------------------- Compatibility Aliases ------------------------------
@bp.get("/reports/IBF/active_clients")
def active_clients_alias_cap():
    return ibf_frequency()

@bp.get("/reports/ibf/active_clients")
def active_clients_alias_low():
    return ibf_frequency()

@bp.get("/reports/IBF/frequency")
def frequency_alias_cap():
    return ibf_frequency()

@bp.get("/reports/ibf/frequency")
def frequency_alias_low():
    return ibf_frequency()

@bp.get("/reports/IBF/frequency/best")
def frequency_best_alias_cap():
    return ibf_frequency_best()

@bp.get("/reports/ibf/frequency/best")
def frequency_best_alias_low():
    return ibf_frequency_best()

@bp.get("/reports/IBF/client/first_contract")
def first_contract_alias_cap():
    return ibf_first_contract()

@bp.get("/reports/ibf/client/first_contract")
def first_contract_alias_low():
    return ibf_first_contract()
