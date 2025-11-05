# app/franchisor/routes.py
from flask import Blueprint, jsonify, render_template_string

# No template_folder: we’re not serving the old UI anymore
franchisor_bp = Blueprint("franchisor", __name__, url_prefix="/franchisor")

# ───────────────────────── Basic Page (feature retired) ─────────────────────────
@franchisor_bp.route("/", methods=["GET"])
def franchisor_home():
    """
    Franchisor section placeholder.
    Appointment availability & creation features were removed from the platform.
    """
    return render_template_string("""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1"/>
      <title>Franchisor</title>
      <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css">
    </head>
    <body class="bg-gray-50 text-gray-800">
      <div class="max-w-3xl mx-auto px-6 py-12">
        <h1 class="text-2xl font-semibold mb-2">Franchisor</h1>
        <p class="text-sm text-gray-600">
          Appointment availability checks and on-portal creation have been removed from the platform.
        </p>
      </div>
    </body>
    </html>
    """)

# ───────────────────────── Health ─────────────────────────
@franchisor_bp.route("/_debug/ping", methods=["GET"])
def franchisor_ping():
    return jsonify(ok=True, section="franchisor")

# Note:
# - Removed routes:
#     /availability (page)
#     /availability/check (API)
#     /create (POST)
# - Removed all helper functions and any imports related to them.
