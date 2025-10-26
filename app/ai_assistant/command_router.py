import os
import json
from openai import OpenAI, OpenAIError
from app.ai_assistant.daily_brain import run_full_summary, summarize_for_date
from app.ai_assistant.gpt_wrapper import summarize_data, analyze_trends_and_suggest

MODEL = os.getenv("GPT_FUNCTION_MODEL", "gpt-3.5-turbo")
client = OpenAI()

# Only expose pages we still support (no per-report names)
FUNCTIONS = [
    {
        "name": "get_summary",
        "description": "Today's gym summary",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_deep_analysis",
        "description": "Multi-month strategic trends",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_for_date",
        "description": "One-day summary+comparison",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"}
            },
            "required": ["date"]
        }
    },
    {
        "name": "navigate_to_page",
        "description": "Navigate to a section of the app (home, daily, clients, reports).",
        "parameters": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "string",
                    "description": "One of: home, daily, clients, reports"
                }
            },
            "required": ["page"]
        }
    }
]

def route_command(user_input: str):
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": user_input}],
            functions=FUNCTIONS,
            function_call="auto"
        )

        msg = resp.choices[0].message

        if msg.function_call:
            name = msg.function_call.name
            args = json.loads(msg.function_call.arguments or "{}")

            if name == "get_summary":
                return summarize_data(run_full_summary())

            if name == "get_deep_analysis":
                return analyze_trends_and_suggest(run_full_summary())

            if name == "get_for_date":
                return summarize_for_date(args.get("date", ""))

            if name == "navigate_to_page":
                # Normalize and route only to supported top-level pages.
                page = (args.get("page") or "").strip().lower()

                # simple keyword mapping (no legacy report names / URLs)
                if "home" in page:
                    return {"redirect": "/"}
                if "report" in page or "daily" in page or "check" in page:
                    # daily check-in
                    return {"redirect": "/report"}
                if "client" in page:
                    return {"redirect": "/clients"}
                if "report" in page or "reports" in page:
                    # reports shell (placeholder)
                    return {"redirect": "/figurella-reports/"}

                return {"message": f"❓ Unknown destination: {page}"}

            return {"message": f"⚠ Function {name} not implemented."}

        return msg.content or ""

    except OpenAIError as oe:
        return f"❗ OpenAI API error: {oe}"

    except Exception as e:
        return f"❗ Internal error: {e}"
