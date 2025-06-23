import os
import pandas as pd

def save_report_to_excel(section_data):
    report_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'reports')
    report_path = os.path.abspath(os.path.join(report_dir, 'daily_reports.xlsx'))

    if os.path.exists(report_path):
        # Load existing Excel sheets
        existing_data = pd.read_excel(report_path, sheet_name=None)
    else:
        existing_data = {}

    with pd.ExcelWriter(report_path, engine='openpyxl', mode='w') as writer:
        for sheet_name, new_df in section_data.items():
            if sheet_name in existing_data:
                combined_df = pd.concat([existing_data[sheet_name], new_df], ignore_index=True)
            else:
                combined_df = new_df
            combined_df.to_excel(writer, index=False, sheet_name=sheet_name)
