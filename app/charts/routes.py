import os
import pandas as pd
from flask import Blueprint, render_template, request, jsonify, current_app
from werkzeug.utils import secure_filename

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
# Helpers for paths and sheet loading
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
    """
    Load all sheets from an existing Excel, dropping any 'Unnamed:' columns,
    then ensure every EXPECTED_TAB exists with default columns if missing.
    """
    sheets = {}
    if os.path.exists(excel_path):
        try:
            xls = pd.ExcelFile(excel_path, engine='openpyxl')
            for sheet in xls.sheet_names:
                key = sheet.lower()
                df = pd.read_excel(xls, sheet_name=sheet)
                # Drop stray index columns like 'Unnamed: 0'
                df = df.loc[:, ~df.columns.str.contains(r'^Unnamed', regex=True, na=False)]
                df = df.fillna('')
                sheets[key] = {
                    'columns': df.columns.tolist(),
                    'data':    df.to_dict(orient='records')
                }
        except Exception as e:
            current_app.logger.warning(f"Could not load sheets from {excel_path}: {e}")

    # Ensure defaults for missing tabs
    for tab in EXPECTED_TABS:
        if tab not in sheets:
            cols = DEFAULT_COLUMNS.get(tab, [f'Field {i+1}' for i in range(3)])
            sheets[tab] = {
                'columns': cols,
                'data':    [{c: '' for c in cols}]
            }
    return sheets

# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
@charts_bp.route('/', methods=['GET'])
def view_charts():
    """List all current clients from the master Excel."""
    excel_path = _clients_excel_path()
    columns = []
    data = []
    error = None

    if os.path.exists(excel_path):
        try:
            df = pd.read_excel(excel_path)
            # Drop index cols
            df = df.loc[:, ~df.columns.str.contains(r'^Unnamed', regex=True, na=False)]
            # Compute full Name and filter
            df['Name'] = df.get('First Name', '').fillna('') + ' ' + df.get('Last Name', '').fillna('')
            df['Name'] = df['Name'].str.strip()
            df['Status'] = df.get('Status', '').astype(str).str.lower().str.strip()
            df = df[df['Status'] == 'current client']
            df.drop(columns=[c for c in ['First Name','Last Name'] if c in df.columns], inplace=True)
            cols = df.columns.tolist()
            if 'Name' in cols:
                cols.insert(0, cols.pop(cols.index('Name')))
                df = df[cols]
            columns = df.columns.tolist()
            data = df.to_dict(orient='records')
        except Exception as e:
            error = f"Error loading clients: {e}"
            current_app.logger.error(error)
    else:
        error = f"Client list not found at {excel_path!r}"

    return render_template(
        'charts/charts.html',
        columns=columns,
        data=data,
        error=error,
        active_page='charts'
    )


@charts_bp.route('/client/<client>', methods=['GET'])
def client_chart(client):
    """Display the client-specific chart form, loading all tabs from Excel or defaults."""
    excel_path = _charts_excel_path(client)
    sheets = _load_sheets(excel_path)

    # Parse Profile into a dict for header fields
    profile_dict = {}
    prof = sheets['profile']
    if len(prof['columns']) > 1:
        val_col = prof['columns'][1]
        for row in prof['data']:
            field = row.get('Field', '').strip()
            profile_dict[field] = row.get(val_col, '')

    return render_template(
        'charts/_client_form.html',
        client=client,
        sheets=sheets,
        # Profile header fields
        goals=profile_dict.get('Goals',''),
        init_date=profile_dict.get('Initial Weight Date',''),
        init_weight=profile_dict.get('Initial Weight',''),
        lowest_date=profile_dict.get('Lowest Weight Date',''),
        lowest_weight=profile_dict.get('Lowest Weight',''),
        target_date=profile_dict.get('Target Weight Date',''),
        target_weight=profile_dict.get('Target Weight',''),
        freq=profile_dict.get('Frequency','').split(',') if profile_dict.get('Frequency') else ['']*12,
        expiration=profile_dict.get('Expiration',''),
        first_session=profile_dict.get('First Session Date',''),
        # Tab data
        communication_data=sheets['communication']['data'],
        nutrition_data=sheets['nutrition']['data'],
        workout_data=sheets['workout']['data']
    )


@charts_bp.route('/client/<client>/save', methods=['POST'])
def save_client_chart(client):
    """Save all tab data back into the client-specific Excel."""
    excel_path = _charts_excel_path(client)
    sheets = _load_sheets(excel_path)

    # Merge posted data
    payload = request.get_json(force=True)
    for key, sheet in payload.get('sheets', {}).items():
        lk = key.lower()
        if lk in sheets:
            sheets[lk] = sheet

    # Write all tabs in specified order with correct headers
    try:
        with pd.ExcelWriter(excel_path, engine='openpyxl', mode='w') as writer:
            for tab in EXPECTED_TABS:
                sht = sheets[tab]
                df = pd.DataFrame(sht['data'], columns=sht['columns'])
                df.to_excel(writer, sheet_name=tab.capitalize(), index=False)
        return jsonify(status='success')
    except Exception as e:
        msg = f"Failed saving client Excel {excel_path}: {e}"
        current_app.logger.error(msg)
        return jsonify(status='error', error=str(e)), 500
