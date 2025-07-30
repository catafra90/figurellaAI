import os
from flask import Blueprint, request, jsonify, current_app
from .scrape_agenda import scrape_agenda, get_date_range

common_bp = Blueprint('common', __name__, url_prefix='/api/common')

@common_bp.route('/scrape/agenda', methods=['POST'])
def run_agenda_scrape():
    """
    Endpoint to trigger Agenda scraping.
    Accepts optional JSON with 'from_date' and 'to_date' (MM/DD/YYYY).
    Returns JSON with status and filename.
    """
    # Parse dates from request or default
    body = request.get_json(silent=True) or {}
    from_date = body.get('from_date')
    to_date   = body.get('to_date')
    if not from_date or not to_date:
        from_date, to_date = get_date_range()

    # Run the scraper (returns cleaned DataFrame)
    df = scrape_agenda(from_date, to_date)
    if df.empty:
        return jsonify(status='no_data'), 204

    # Prepare download path
    filename = f"agenda_{from_date.replace('/','-')}_{to_date.replace('/','-')}.xlsx"
    downloads_dir = os.path.join(current_app.root_path, os.pardir, 'downloads', 'agenda')
    os.makedirs(downloads_dir, exist_ok=True)
    file_path = os.path.join(downloads_dir, filename)

    # Save to Excel
    df.to_excel(file_path, index=False)

    return jsonify(status='ok', file=filename), 200
