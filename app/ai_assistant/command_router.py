import os
import json
from openai import OpenAI, OpenAIError
from app.ai_assistant.daily_brain import run_full_summary, summarize_for_date
from app.ai_assistant.gpt_wrapper import summarize_data, analyze_trends_and_suggest

MODEL = os.getenv("GPT_FUNCTION_MODEL", "gpt-3.5-turbo")
client = OpenAI()

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
                "date": {
                    "type": "string",
                    "description": "YYYY-MM-DD"
                }
            },
            "required": ["date"]
        }
    },
    {
        "name": "navigate_to_page",
        "description": "Navigate to a specific section of the app like home, daily check-in, reports, or clients",
        "parameters": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "string",
                    "description": "Page to navigate to (e.g., home, daily, clients, reports or report names)"
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
                page = args.get("page", "").lower()

                # ✅ Alias map for report matching
                REPORT_ALIASES = {
                    "agenda": "Agenda",
                    "contracts": "Contracts",
                    "contract": "Contracts",
                    "customer acquisition": "Customer Acquisition",
                    "customer": "Customer Acquisition",
                    "acquisition": "Customer Acquisition",
                    "ibf": "IBF",
                    "last session": "Last Session",
                    "session": "Last Session",
                    "payments done": "Payments Done",
                    "done payments": "Payments Done",
                    "payments due": "Payments Due",
                    "due payments": "Payments Due",
                    "pip": "PIP",
                    "subscriptions": "Subscriptions",
                    "subs": "Subscriptions"
                }

                for key, value in REPORT_ALIASES.items():
                    if key in page:
                        return {
                            "redirect": f"/figurella-reports/reports/{value}/history/view"
                        }

                # ✅ General navigation (order matters)
                if "home" in page:
                    return {"redirect": "/"}
                elif "reports" in page:
                    return {"redirect": "/figurella-reports/reports"}
                elif "clients" in page:
                    return {"redirect": "/clients"}
                elif "check" in page or "daily" in page or "report" in page:
                    return {"redirect": "/report"}
                else:
                    return {"message": f"❓ Unknown destination: {page}"}

            return {"message": f"⚠ Function {name} not implemented."}

        return msg.content or ""

    except OpenAIError as oe:
        return f"❗ OpenAI API error: {oe}"

    except Exception as e:
        return f"❗ Internal error: {e}"
