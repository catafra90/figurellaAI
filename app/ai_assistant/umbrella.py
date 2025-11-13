# app/ai_assistant/umbrella.py
# Offline / iPad-safe version – no OpenAI

from flask import Blueprint, jsonify, request

# keep the same name so app factory registration still works
umbrella_bp = Blueprint("umbrella_bp", __name__, url_prefix="/umbrella")


@umbrella_bp.route("/chat", methods=["POST"])
def umbrella_chat():
    """
    Simple offline echo / placeholder.
    Previously this would call OpenAI; now it just replies locally.
    """
    payload = request.get_json(force=True) or {}
    message = (payload.get("message") or payload.get("text") or "").strip()

    if not message:
        return jsonify({"reply": "AI is disabled in this offline build."}), 200

    return jsonify({
        "reply": f"[offline mode] You said: {message}"
    }), 200
