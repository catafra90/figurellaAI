# app/common/save_gate.py
import os
from functools import wraps
from flask import jsonify, current_app, request

def saves_enabled() -> bool:
    # Prefer explicit config; fallback to env; default False while you're refactoring
    cfg = getattr(current_app, "config", {}) or {}
    flag = cfg.get("ENABLE_SAVES")
    if flag is not None:
        return bool(flag)
    return os.getenv("ENABLE_SAVES", "0") in ("1", "true", "True")

def no_save_response(detail: str = "Saving is temporarily disabled."):
    return jsonify({"status": "disabled", "detail": detail}), 200

def guard_saves_route(detail: str = "Saving is temporarily disabled."):
    """
    Wrap POST/PUT/PATCH/DELETE endpoints that would modify DB/files.
    When saves are disabled, short-circuit with a benign success response.
    """
    def _decorator(fn):
        @wraps(fn)
        def _wrapped(*args, **kwargs):
            if request.method in ("POST","PUT","PATCH","DELETE") and not saves_enabled():
                return no_save_response(detail)
            return fn(*args, **kwargs)
        return _wrapped
    return _decorator

def safe_commit(db_session, detail: str = "Skipping commit (saves disabled)."):
    """
    Call instead of session.commit(). Does nothing when disabled.
    """
    if not saves_enabled():
        return False  # indicate no commit
    db_session.commit()
    return True

def safe_add(db_session, *models):
    if not saves_enabled():
        return False
    for m in models:
        db_session.add(m)
    return True

def reject_writes_model(detail: str = "Model writes are disabled right now."):
    """
    Optional: mixin/utility you can call in any service just before a write.
    """
    if not saves_enabled():
        raise RuntimeError(detail)
