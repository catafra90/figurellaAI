# File: app/clients/routes.py

import pandas as pd
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash
from app import db
from app.models import Client
from .utils import scrape_all_clients

clients_bp = Blueprint('clients', __name__, template_folder='templates')

@clients_bp.route('/clients')
def clients():
    """
    Display all clients from the database, including Name, Date Created,
    Status, Email and Phone.
    """
    clients_list = Client.query.order_by(Client.created_at).all()
    return render_template(
        'clients_table.html',
        clients=clients_list,
        active_page='clients'
    )

@clients_bp.route('/refresh_clients', methods=['GET', 'POST'])
def refresh_clients():
    """
    Scrape new client data and upsert directly into the database,
    always honoring the real "Date Created" from the dashboard.
    """
    try:
        client_dicts = scrape_all_clients()
    except Exception as e:
        flash(f"Error scraping clients: {e}", 'error')
        return redirect(url_for('clients.clients'))

    inserted = 0
    for row in client_dicts:
        name      = (row.get('Name') or '').strip()
        email     = (row.get('Email') or '').strip()
        phone     = (row.get('Phone') or '').strip()
        status    = (row.get('Status') or '').strip()
        date_str  = (row.get('Date Created') or '').strip()

        if not name:
            continue

        # Parse the scraped date into a datetime
        created_at = None
        if date_str:
            for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y'):
                try:
                    created_at = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

        # Lookup existing by name+email
        client = Client.query.filter_by(name=name, email=email).first()

        if not client:
            # INSERT
            client = Client(
                name=name,
                email=email,
                phone=phone,
                status=status,
                created_at=created_at
            )
            db.session.add(client)
            inserted += 1
        else:
            # UPDATE existing fields—and ALWAYS overwrite created_at if we parsed it
            client.phone      = phone
            client.status     = status
            if created_at:
                client.created_at = created_at

    db.session.commit()
    flash(f"Clients synced! ({inserted} new added)", 'success')
    return redirect(url_for('clients.clients'))
