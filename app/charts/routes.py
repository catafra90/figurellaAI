import os
import pandas as pd
from flask import Blueprint, render_template, request, jsonify, current_app
from werkzeug.utils import secure_filename

# ← Be sure this import path matches your app structure!
from app.models import Client  

charts_bp = Blueprint(
    'charts',
    __name__,
    url_prefix='/charts',
    template_folder=os.path.join(os.pardir, 'templates')
)

# ------------------------------------------------------------------
# Configuration for expected tabs and default columns
# ------------------------------------------------------------------
EXPECTED_TABS = ['profile', 'measures', 'workout', 'nutrition', 'communication']
DEFAULT_COLUMNS = {
    'nutrition': ['Date', 'Type', 'Notes'],
    'workout':   ['Workout', 'Rings', 'Comment'],
}

# ------------------------------------------------------------------
# Helper functions for Excel-backed routes (unchanged)
# ------------------------------------------------------------------
def _get_data_dir(subfolder: str = 'data') -> str:
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    data_dir = os.path.join(base, subfolder)
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def _clients_excel_path() -> str:
    return os.path.join(
        _get_data_dir(subfolder=os.path.join('clients', 'data')),
        'all_clients.xlsx'
    )

def _charts_excel_path(client: str) -> str:
    charts_dir = os.path.join(_get_data_dir(), 'client_charts')
    os.makedirs(charts_dir, exist_ok=True)
    filename = secure_filename(client) or 'unnamed_client'
    return os.path.join(charts_dir, f"{filename}.xlsx")

def _load_sheets(excel_path: str) -> dict:
    sheets = {}
    if os.path.exists(excel_path):
        try:
            xls = pd.ExcelFile(excel_path, engine='openpyxl')
            for sheet in xls.sheet_names:
                key = sheet.lower()
                df = pd.read_excel(xls, sheet_name=sheet)
                df = df.loc[:, ~df.columns.str.contains(r'^Unnamed', regex=True, na=False)]
                df = df.fillna('')
                sheets[key] = {'columns': df.columns.tolist(),
                               'data':    df.to_dict(orient='records')}
        except Exception as e:
            current_app.logger.warning(f"Could not load sheets from {excel_path}: {e}")
    for tab in EXPECTED_TABS:
        if tab not in sheets:
            cols = DEFAULT_COLUMNS.get(tab, [f'Field {i+1}' for i in range(3)])
            sheets[tab] = {'columns': cols, 'data': [{c: '' for c in cols}]}
    return sheets

# ------------------------------------------------------------------
# NEW: DB-BACKED sidebar
# ------------------------------------------------------------------
@charts_bp.route('/', methods=['GET'])
def view_charts():
    """List all clients from the DB (same as /clients)."""
    try:
        # exactly your clients() query:
        clients_list = Client.query.order_by(Client.created_at).all()

        # same columns you use in clients_table.html
        columns = ['Name', 'Date Created', 'Status', 'Email', 'Phone']

        # build sidebar data
        data = []
        for c in clients_list:
            data.append({
                'Name':         c.name,
                'Date Created': c.created_at.strftime('%Y-%m-%d') if c.created_at else '',
                'Status':       c.status,
                'Email':        c.email or '',
                'Phone':        c.phone or ''
            })
        error = None

    except Exception as e:
        current_app.logger.error(f"Error loading clients for charts: {e}")
        columns, data = [], []
        error = "Could not load client list."

    return render_template(
        'charts/charts.html',
        columns=columns,
        data=data,
        error=error,
        active_page='charts'
    )


# ------------------------------------------------------------------
# EXISTING: Per-client Excel-backed routes (unchanged)
# ------------------------------------------------------------------
@charts_bp.route('/client/<client>', methods=['GET'])
def client_chart(client):
    excel_path = _charts_excel_path(client)
    sheets     = _load_sheets(excel_path)
    # ... your existing parsing logic ...
    return render_template('charts/_client_form.html', 
                           client=client, 
                           sheets=sheets,
                           # etc.
                           )

@charts_bp.route('/client/<client>/save', methods=['POST'])
def save_client_chart(client):
    excel_path = _charts_excel_path(client)
    sheets     = _load_sheets(excel_path)
    # ... your existing save logic ...
    return jsonify(status='success')
