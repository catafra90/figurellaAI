# File: app/common/webhook.py
import os
import requests
from flask import current_app

# ❗ Your fallback webhook (OK for local testing; avoid committing to Git)
_DEFAULT_WEBHOOK_URL = (
    "https://chat.googleapis.com/v1/spaces/4ZsvACAAAAE/messages"
    "?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI"
    "&token=QAsMtcgO05jwCeg2HXcDrCK7ngmtq0vpQwguobG8-vU"
)

def _get_webhook_url():
    """Order of precedence: Flask config → ENV → hardcoded fallback."""
    url = None
    try:
        if current_app:
            url = current_app.config.get('GOOGLE_CHAT_WEBHOOK_URL')
    except RuntimeError:
        # current_app not active; ignore
        pass
    return url or os.getenv('GOOGLE_CHAT_WEBHOOK_URL') or _DEFAULT_WEBHOOK_URL

def send_to_google_chat(payload, chunk=True, timeout=10):
    """
    Send a message to Google Chat Incoming Webhook.
    - If `payload` is a string: posts {"text": "..."} (supports basic markdown).
    - If `payload` is a dict: posts raw JSON (for cards, etc).
    - Long strings get chunked to avoid size limits.
    """
    url = _get_webhook_url()
    if not url:
        raise RuntimeError("GOOGLE_CHAT_WEBHOOK_URL not configured and no fallback set.")

    # Dict payload → send as JSON (for cardsV2 etc.)
    if isinstance(payload, dict):
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r

    # String payload → send as {"text": "..."}
    text = str(payload)
    max_len = 3800  # safe chunk size under Chat limits
    if chunk and len(text) > max_len:
        last = None
        for i in range(0, len(text), max_len):
            part = text[i:i+max_len]
            last = requests.post(url, json={"text": part}, timeout=timeout)
            last.raise_for_status()
        return last

    r = requests.post(url, json={"text": text}, timeout=timeout)
    r.raise_for_status()
    return r
