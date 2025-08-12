# File: app/charts/exporters.py

import pandas as pd
from app.models import ChartEntry

def export_client_charts_to_excel(client: str, excel_path: str, tabs=None):
    """
    Query ChartEntry for each sheet and write an .xlsx with one tab per sheet.
    Always creates a sheet (even if empty) to avoid corrupt files.
    """
    from app.charts.routes import EXPECTED_TABS, DEFAULT_COLUMNS

    if tabs is None:
        tabs = EXPECTED_TABS

    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        for tab in tabs:
            records = (
                ChartEntry.query
                          .filter_by(client_name=client, sheet=tab)
                          .order_by(ChartEntry.created_at)
                          .all()
            )
            if records:
                df = pd.DataFrame([r.data for r in records])
            else:
                cols = DEFAULT_COLUMNS.get(tab, [f'Field {i+1}' for i in range(3)])
                df = pd.DataFrame(columns=cols)

            df.to_excel(writer, sheet_name=tab.capitalize(), index=False)
