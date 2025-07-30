from flask import Blueprint, render_template, redirect, url_for
import pandas as pd
import os

from .utils import scrape_all_clients

clients_bp = Blueprint('clients', __name__, template_folder='templates')

@clients_bp.route('/clients')
def clients():
    # Load the data
    excel_path = os.path.join(os.path.dirname(__file__), 'data', 'all_clients.xlsx')
    df = pd.read_excel(excel_path)

    # Drop Email & Phone for speed
    df.drop(columns=['Email', 'Phone'], errors='ignore', inplace=True)

    # Render to HTML
    table_html = df.to_html(
        table_id='clients-table',
        classes='min-w-full text-sm text-left table-auto display',
        index=False,
        border=0
    )

    return render_template(
        'clients_table.html',
        clients_table=table_html,
        active_page='clients'
    )

@clients_bp.route('/refresh_clients', methods=['POST'])
def refresh_clients():
    scrape_all_clients()
    return redirect(url_for('clients.clients'))
