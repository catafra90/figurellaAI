# app/ai_assistant/ai_assistant_routes.py
import os, re, calendar, traceback, json
from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from dateutil import parser as date_parser

from app.ai_assistant.daily_brain import run_full_summary, summarize_for_date, summarize_range
from app.ai_assistant.gpt_wrapper import summarize_data, analyze_trends_and_suggest
from app.ai_assistant.command_router import route_command

# ────────────────────────────────────────────────────────────────────────────────
ai_bp = Blueprint("ai_bp", __name__, url_prefix="/ai")

# Regex helpers
MONTH_NAMES = "|".join(calendar.month_name[1:])
MONTH_REGEX = re.compile(rf"\b({MONTH_NAMES})(?:\s+(\d{{4}}))?\b", re.IGNORECASE)
DAY_REGEX   = re.compile(rf"\b({MONTH_NAMES})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,\s*(\d{{4}}))?\b", re.IGNORECASE)
ISO_DATE    = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

# ────────────────────────────────────────────────────────────────────────────────
@ai_bp.route("/summary", methods=["GET"])
def ai_summary():
    """Today's natural-language summary"""
    try:
        text = summarize_data(run_full_summary())
    except Exception:
        traceback.print_exc()
        df = run_full_summary()["sales"]["daily"]
        total = df["Revenue"].sum() if not df.empty else 0
        text = f"Total revenue today: ${total:.2f}"
    return jsonify({"summary": text})


@ai_bp.route("/deep-analysis", methods=["GET"])
def ai_deep_analysis():
    """Deeper trend analysis"""
    try:
        text = analyze_trends_and_suggest(run_full_summary())
    except Exception:
        traceback.print_exc()
        text = "Unable to run deep analysis at this time."
    return jsonify({"analysis": text})


@ai_bp.route("/chart-data", methods=["GET"])
def chart_data():
    """Last 14 days of revenue / leads / attendance"""
    summary = run_full_summary()
    df_sales = summary["sales"]["daily"]
    if df_sales.empty:
        return jsonify({"data": []})

    df_sales = df_sales.sort_values("Date_only").tail(14).reset_index(drop=True)
    df_sales["Date"] = df_sales["Date_only"].astype(str)

    leads_map = {
        r["Date_only"].isoformat(): r["count"]
        for r in summary["leads"]["daily"].to_dict(orient="records")
    }
    att_map = {
        r["Date_only"].isoformat(): int(r.get("Attended", 0))
        for r in summary["attendance"]["daily"].to_dict(orient="records")
    }

    data = [{
        "Date": row["Date"],
        "Revenue": row["Revenue"],
        "Leads": leads_map.get(row["Date"], 0),
        "Attendance": att_map.get(row["Date"], 0)
    } for row in df_sales.to_dict(orient="records")]

    return jsonify({"data": data})


# ────────────────────────────────────────────────────────────────────────────────
@ai_bp.route("/assistant", methods=["POST"], strict_slashes=False)
def ai_assistant():
    """
    Voice / chat commands endpoint.
    Returns either:
      { "redirect": "/target" }  ← for navigation AI
      { "reply":    "response" } ← for everything else
    """
    payload = request.get_json(force=True) or {}
    cmd = (payload.get("command") or payload.get("message") or "").strip()
    if not cmd:
        return jsonify({"reply": "No command received."}), 400

    cmd_lower = cmd.lower()

    # ── Pre-defined date/summary shortcuts ────────────────────────────────────
    if "today" in cmd_lower:
        return jsonify({"reply": summarize_for_date(date.today().isoformat())})

    if "yesterday" in cmd_lower:
        y = (date.today() - timedelta(days=1)).isoformat()
        return jsonify({"reply": summarize_for_date(y)})

    if "this month" in cmd_lower or "month summary" in cmd_lower:
        today = date.today()
        start = today.replace(day=1).isoformat()
        end   = today.replace(day=calendar.monthrange(today.year, today.month)[1]).isoformat()
        return jsonify({"reply": summarize_range(start, end)})

    if " to " in cmd_lower:
        try:
            p1, p2 = [p.strip() for p in cmd_lower.split(" to ", 1)]
            d1 = date_parser.parse(p1, fuzzy=True).date().isoformat()
            d2 = date_parser.parse(p2, fuzzy=True).date().isoformat()
            return jsonify({"reply": summarize_range(d1, d2)})
        except Exception:
            pass

    if m := ISO_DATE.search(cmd_lower):
        return jsonify({"reply": summarize_for_date(m.group(1))})

    if dm := DAY_REGEX.search(cmd_lower):
        month, day, yr = dm.group(1), dm.group(2), dm.group(3) or str(date.today().year)
        try:
            iso = date_parser.parse(f"{month} {day}, {yr}").date().isoformat()
            return jsonify({"reply": summarize_for_date(iso)})
        except Exception:
            pass

    if mm := MONTH_REGEX.search(cmd_lower):
        mon_name = mm.group(1).capitalize()
        yr = int(mm.group(2)) if mm.group(2) else date.today().year
        mnum = list(calendar.month_name).index(mon_name)
        start = date(yr, mnum, 1).isoformat()
        end = date(yr, mnum, calendar.monthrange(yr, mnum)[1]).isoformat()
        return jsonify({"reply": summarize_range(start, end)})

    # ── Everything else → Master AI (via command_router) ─────────────────────
    result = route_command(cmd)

    if isinstance(result, dict) and "redirect" in result:
        return jsonify({"redirect": result["redirect"]})

    if isinstance(result, dict) and "message" in result:
        return jsonify({"reply": result["message"]})

    return jsonify({"reply": str(result)})
