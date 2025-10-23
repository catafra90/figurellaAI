# app/auth/routes.py
from __future__ import annotations
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
import json

bp = Blueprint("auth", __name__, url_prefix="/auth")

# users.json will live in app/common/users.json
USERS_PATH = Path(__file__).resolve().parent.parent / "common" / "users.json"


def _ensure_seed() -> dict:
    """Create users.json with a default admin if it doesn't exist."""
    if USERS_PATH.exists():
        with USERS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)

    USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "users": [
            {
                "username": "admin",
                "name": "Administrator",
                # Default password: ChangeMe123!  (please change right away)
                "password_hash": generate_password_hash("ChangeMe123!"),
            }
        ]
    }
    with USERS_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return data


def _find_user(username: str) -> dict | None:
    data = _ensure_seed()
    for u in data.get("users", []):
        if u.get("username", "").lower() == username.lower():
            return u
    return None


@bp.route("/login", methods=["GET", "POST"])
def login():
    # Already logged in? Go home.
    if session.get("user"):
        return redirect(request.args.get("next") or "/")

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user = _find_user(username)
        if user and check_password_hash(user.get("password_hash", ""), password):
            session["user"] = {
                "username": user.get("username"),
                "name": user.get("name") or user.get("username"),
            }
            return redirect(request.args.get("next") or "/")

        flash("Invalid username or password.", "danger")

    return render_template("auth/login.html", title="Sign in")


@bp.get("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("auth.login"))
