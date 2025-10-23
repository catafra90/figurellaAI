# app/ai_assistant/umbrella.py

import os, json, calendar, re
from datetime import datetime, date, timedelta
from flask import Blueprint, request, jsonify, url_for
from openai import OpenAI, OpenAIError
from dateutil import parser as date_parser
from app.ai_assistant.daily_brain import summarize_for_date, summarize_range

# Instantiate OpenAI client
client = OpenAI()

# Describe the two sub-functions
FUNCTIONS = [
    {
        "name": "get_daily_checkin",
        "description": "Get the daily check-in report for a specific date.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD"
                }
            },
            "required": ["date"]
        }
    },
    {
        "name": "get_range_report",
        "description": "Get the check-in summary for a date range.",
        "parameters": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "end":   {"type": "string", "description": "End date YYYY-MM-DD"}
            },
            "required": ["start", "end"]
        }
    }
]

# Master AI blueprint
umbrella_bp = Blueprint('umbrella_bp', __name__, url_prefix='/umbrella')

@umbrella_bp.route('/query', methods=['POST'])
def umbrella_query():
    data = request.get_json(force=True) or {}
    user_text = (data.get('message') or data.get('command') or '').strip()
    if not user_text:
        return jsonify({'reply': "Please say something like 'today' or 'July 2025'."}), 400

    try:
        # Ask the model which sub-function (if any) to call
        resp = client.chat.completions.create(
            model=os.getenv("GPT_MODEL","gpt-3.5-turbo-0613"),
            messages=[{"role":"user","content":user_text}],
            functions=FUNCTIONS,
            function_call="auto"
        )
    except OpenAIError as e:
        return jsonify({'reply': f"OpenAI error: {e}"}), 500

    msg = resp.choices[0].message

    # If the model chose a function, dispatch to it
    if msg.function_call:
        fn   = msg.function_call.name
        args = json.loads(msg.function_call.arguments or "{}")
        if fn == "get_daily_checkin":
            return jsonify({'reply': summarize_for_date(args["date"])})
        if fn == "get_range_report":
            return jsonify({'reply': summarize_range(args["start"], args["end"])})
        return jsonify({'reply': f"Unknown function {fn}."}), 500

    # Otherwise, fall back to simple keyword parsing
    lower = user_text.lower()

    # Today
    if any(kw in lower for kw in ["today","daily","check in"]):
        return jsonify({'reply': summarize_for_date(date.today().isoformat())})
    # Yesterday
    if "yesterday" in lower:
        y = (date.today() - timedelta(days=1)).isoformat()
        return jsonify({'reply': summarize_for_date(y)})
    # This month
    if "this month" in lower or "month summary" in lower:
        today = date.today()
        start = today.replace(day=1).isoformat()
        last  = calendar.monthrange(today.year, today.month)[1]
        end   = today.replace(day=last).isoformat()
        return jsonify({'reply': summarize_range(start, end)})

    # ISO date
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", user_text)
    if iso:
        return jsonify({'reply': summarize_for_date(iso.group(1))})

    # Month name +/- year
    mon = re.search(rf"\b({'|'.join(calendar.month_name[1:])})(?:\s+(\d{{4}}))?\b", user_text, re.IGNORECASE)
    if mon:
        mname = mon.group(1).capitalize()
        yr    = int(mon.group(2)) if mon.group(2) else date.today().year
        mnum  = list(calendar.month_name).index(mname)
        start = date(yr, mnum, 1).isoformat()
        last  = calendar.monthrange(yr, mnum)[1]
        end   = date(yr, mnum, last).isoformat()
        return jsonify({'reply': summarize_range(start, end)})

    # Date range "to"
    if " to " in user_text:
        p1, p2 = [p.strip() for p in user_text.split(" to ",1)]
        try:
            d1 = date_parser.parse(p1).date().isoformat()
            d2 = date_parser.parse(p2).date().isoformat()
            return jsonify({'reply': summarize_range(d1, d2)})
        except:
            pass

    # Navigation fallback
    if "go to daily" in lower or "open daily" in lower:
        return jsonify({'navigate': url_for('daily_checkin_bp.report_home')})

    # Give up
    return jsonify({
        'reply': (
            "Sorry, I didn’t get that. You can say:\n"
            "- 'today' or 'yesterday'\n"
            "- a date like '2025-07-10'\n"
            "- a month like 'July 2025'\n"
            "- a range: '2025-07-01 to 2025-07-05'"
        )
    }), 400
