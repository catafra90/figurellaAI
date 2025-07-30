import os
import pandas as pd
import numpy as np
from flask import flash

def save_report_to_excel(section_data):
    """
    Saves a dictionary of DataFrames to an Excel file, appending to existing data by sheet.
    Handles empty rows and ensures proper directory structure.
    """
    # Set path to reports directory
    report_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'reports')
    report_path = os.path.abspath(os.path.join(report_dir, 'daily_checkins.xlsx'))

    # Ensure directory exists
    os.makedirs(report_dir, exist_ok=True)

    try:
        # Load existing Excel data (if file exists)
        existing_data = {}
        if os.path.exists(report_path):
            try:
                existing_data = pd.read_excel(report_path, sheet_name=None)
            except PermissionError:
                flash("❌ Cannot save — please close the Excel file first.", "error")
                raise

        # Write updated data to Excel
        with pd.ExcelWriter(report_path, engine='openpyxl', mode='w') as writer:
            for sheet_name, new_df in section_data.items():
                # Convert empty strings to NaN
                cleaned_df = new_df.replace(r'^\s*$', np.nan, regex=True)

                # Drop rows where all fields (except 'Date') are empty
                if 'Date' in cleaned_df.columns:
                    filtered_df = cleaned_df.dropna(how='all', subset=[col for col in cleaned_df.columns if col != 'Date'])
                else:
                    filtered_df = cleaned_df.dropna(how='all')

                # Merge with existing sheet data (if exists)
                if sheet_name in existing_data:
                    combined_df = pd.concat([existing_data[sheet_name], filtered_df], ignore_index=True)
                else:
                    combined_df = filtered_df

                # Save to sheet
                combined_df.to_excel(writer, sheet_name=sheet_name, index=False)

    except PermissionError:
        print("❌ Excel file is currently open.")
        raise
    except Exception as e:
        flash(f"❌ Unexpected error while saving report: {e}", "error")
        print("❌ save_report_to_excel error:", str(e))
        raise
