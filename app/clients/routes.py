# app/clients/routes.py  (FULL, revised to exclude "Scheduled" from Current)

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from sqlalchemy import func, or_, not_

from app import db
from app.models import Client
from .utils import scrape_all_clients

clients_bp = Blueprint("clients", __name__, template_folder="templates")

# Treat these as "current" when they appear anywhere in the status text.
CURRENT_KEYWORDS = {"current", "active", "pink", "confirmed", "attending"}

# Explicitly exclude these from the Current view
EXCLUDE_KEYWORDS = {"scheduled"}

def _norm(s: str) -> str:
    return (s or "").strip().lower()

@clients_bp.route("/clients")
def clients():
    """
    Renders Clients page with server-side filtering to avoid any flash-of-all-rows.
    Use ?status=current (default) or ?status=all.
    """
    status_mode = _norm(request.args.get("status") or "current")

    q = Client.query

    if status_mode != "all":
        # Include: status ILIKE any CURRENT_KEYWORDS
        include = [Client.status.ilike(f"%{kw}%") for kw in CURRENT_KEYWORDS]
        if include:
            q = q.filter(or_(*include))

        # Exclude: status ILIKE any EXCLUDE_KEYWORDS (e.g., "scheduled")
        exclude = [Client.status.ilike(f"%{kw}%") for kw in EXCLUDE_KEYWORDS]
        if exclude:
            q = q.filter(not_(or_(*exclude)))

    # Case-insensitive order by name
    clients_list = q.order_by(func.lower(Client.name).asc()).all()

    # ---- Sidebar payload (what _sidebar.html expects)
    sidebar_columns = ["Name", "Email", "Phone", "Status"]
    sidebar_data = [
        {
            "Name":   c.name or "",
            "Email":  c.email or "",
            "Phone":  c.phone or "",
            "Status": c.status or "",
        }
        for c in clients_list
    ]

    return render_template(
        "clients_table.html",
        clients=clients_list,                          # if your page also renders a main table
        columns=sidebar_columns,
        data=sidebar_data,                             # already filtered
        default_status=status_mode,
        status_action_url=url_for("clients.clients"),  # dropdown should reload this route
        active_page="clients",
    )


@clients_bp.route("/refresh_clients", methods=["GET", "POST"])
def refresh_clients():
    """
    Scrape new client data and upsert directly into the database,
    honoring the real 'Date Created' from the dashboard when available.
    """
    try:
        client_dicts = scrape_all_clients()
    except Exception as e:
        flash(f"Error scraping clients: {e}", "error")
        return redirect(url_for("clients.clients"))

    inserted = 0
    for row in client_dicts or []:
        name     = (row.get("Name") or "").strip()
        email    = (row.get("Email") or "").strip()
        phone    = (row.get("Phone") or "").strip()
        status   = (row.get("Status") or "").strip()
        date_str = (row.get("Date Created") or "").strip()

        if not name:
            continue

        # Parse date if present (try a few formats)
        created_at = None
        if date_str:
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    created_at = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

        # Upsert by (name, email)
        client = Client.query.filter_by(name=name, email=email).first()
        if not client:
            client = Client(
                name=name,
                email=email,
                phone=phone,
                status=status,
                created_at=created_at,
            )
            db.session.add(client)
            inserted += 1
        else:
            client.phone = phone
            client.status = status
            if created_at:
                client.created_at = created_at

    db.session.commit()
    flash(f"Clients synced! ({inserted} new added)", "success")

    # Preserve view mode (?status=...) after refresh
    status_mode = _norm(request.args.get("status") or "current")
    return redirect(url_for("clients.clients", status=status_mode))
