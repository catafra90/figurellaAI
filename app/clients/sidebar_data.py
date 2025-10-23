# app/clients/sidebar_data.py
from sqlalchemy import func
from app.models import Client

CURRENT_STATUSES = {"current", "active", "pink"}  # tweak as needed

def build_sidebar_payload(status_mode: str):
    """
    Returns (columns, data) for the sidebar, already filtered by status_mode.
    status_mode: 'current' or 'all'
    """
    status_mode = (status_mode or "current").strip().lower()

    q = Client.query
    if status_mode != "all":
        q = q.filter(func.lower(Client.status).in_([s.lower() for s in CURRENT_STATUSES]))
    clients = q.order_by(Client.name.asc()).all()

    columns = ["Name", "Email", "Phone", "Status"]
    data = [{
        "Name":   c.name or "",
        "Email":  c.email or "",
        "Phone":  c.phone or "",
        "Status": c.status or "",
    } for c in clients]

    return columns, data
