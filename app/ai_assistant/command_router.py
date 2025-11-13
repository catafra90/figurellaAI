# app/ai_assistant/command_router.py
# Offline / iPad-safe router – NO OpenAI

import os
from app.ai_assistant.daily_brain import run_full_summary, summarize_for_date
from app.ai_assistant.gpt_wrapper import summarize_data, analyze_trends_and_suggest

# Keep MODEL env var in case you ever re-enable AI later (but it's unused here)
MODEL = os.getenv("GPT_FUNCTION_MODEL", "gpt-3.5-turbo")


def route_command(user_input: str):
    """
    Offline command router.

    It returns either:
      - {"redirect": "/some-url"}    for navigation
      - "plain text"                 for simple replies

    No OpenAI, just keyword-based logic.
    """
    if not user_input:
        return "No command received."

    text = user_input.strip()
    lower = text.lower()

    # ── Navigation intents ────────────────────────────────────────────────
    # Home / main
    if any(k in lower for k in ["home", "main menu", "dashboard"]):
        return {"redirect": "/"}

    # Daily report / check-in
    if any(k in lower for k in ["daily", "check-in", "checkin", "report today", "daily report"]):
        return {"redirect": "/report"}

    # Clients
    if "client" in lower or "clients" in lower:
        return {"redirect": "/clients"}

    # Reports shell (placeholder route)
    if "report" in lower or "reports" in lower:
        return {"redirect": "/figurella-reports/"}

    # ── Data / analytics intents ─────────────────────────────────────────
    if any(k in lower for k in ["summary", "today", "performance", "how did we do"]):
        # High-level daily summary using offline gpt_wrapper
        return summarize_data(run_full_summary())

    if any(k in lower for k in ["deep analysis", "strategy", "trend", "trends"]):
        return analyze_trends_and_suggest(run_full_summary())

    if "yesterday" in lower:
        # Let ai_assistant_routes handle most date parsing; here we just support a simple shortcut.
        from datetime import date, timedelta
        y = (date.today() - timedelta(days=1)).isoformat()
        return summarize_for_date(y)

    # ── Fallback generic reply ───────────────────────────────────────────
    return (
        "Offline assistant:\n"
        "- Say things like 'open clients', 'go to daily report', or 'show today summary'.\n"
        "- Deep AI chat is disabled in this build (no OpenAI)."
    )
