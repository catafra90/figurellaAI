from app.common.utils import save_report_to_excel
from flask import Blueprint, render_template, redirect, url_for, request
import pandas as pd
import os

from .utils import scrape_all_clients

clients_bp = Blueprint('clients', __name__, template_folder='templates')

@clients_bp.route('/clients')
def clients():
    excel_path = os.path.join(os.path.dirname(__file__), 'data', 'all_clients.xlsx')
    df = pd.read_excel(excel_path)
    return render_template('clients_table.html', table=df.to_dict(orient='records'), headers=df.columns.tolist())

@clients_bp.route('/refresh_clients', methods=['POST'])
def refresh_clients():
    scrape_all_clients()
    return redirect(url_for('clients.clients'))
