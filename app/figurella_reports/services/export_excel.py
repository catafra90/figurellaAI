# app/figurella_reports/services/export_excel.py
import os
import pandas as pd

def safe_overwrite(path: str) -> bool:
    try:
        if os.path.exists(path):
            os.remove(path)
        return True
    except PermissionError:
        print(f"⚠️  File '{path}' is open — close it and rerun.")
        return False

def save_customers_excel(rows, path="customers.xlsx"):
    if not rows:
        print("No customers to save to Excel.")
        return
    df = pd.DataFrame(rows).astype(str)

    if not safe_overwrite(path):
        return

    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="All")

    print(f"📘 Saved Excel: {path} ({len(rows)} rows)")

def save_payments_excel(rows, path="payments.xlsx"):
    if not rows:
        print("No payments to save to Excel.")
        return
    df = pd.DataFrame(rows)

    if not safe_overwrite(path):
        return

    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="All")

    print(f"📘 Saved Excel: {path} ({len(rows)} rows)")

def save_agenda_excel(rows, path="agenda.xlsx"):
    if not rows:
        print("No agenda data to save to Excel.")
        return
    df = pd.DataFrame(rows)

    if not safe_overwrite(path):
        return

    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="All")

    print(f"📘 Saved Excel: {path} ({len(rows)} rows)")
