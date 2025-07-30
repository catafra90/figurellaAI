# app/common/scrape_center_analysis.py
# 📄 Scrapes the "Center Analysis" report and outputs an Excel file with four sheets,
#     plus maintains a rolling history in a separate workbook.

import os
import time
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# ───────── CONFIG ─────────
LOGIN_URL     = "https://newton.hosting.memetic.it/login"
OUTPUT_FILE   = "app/static/reports/center_analysis_report.xlsx"
HISTORY_FILE  = "app/static/reports/center_analysis_history.xlsx"
USERNAME      = "Tutor"
PASSWORD      = "FiguMass2025$"

# ───────── DATE RANGE ─────────
def get_date_range(months_back: int = 6, months_forward: int = 6):
    today     = datetime.today()
    from_date = (today - relativedelta(months=months_back)).strftime("%m/%d/%Y")
    to_date   = (today + relativedelta(months=months_forward)).strftime("%m/%d/%Y")
    return from_date, to_date

# ───────── LOGIN ─────────
def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=10000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15000)

# ───────── HISTORY MERGING ─────────
def update_history(scraped_tables: dict, contracts_df: pd.DataFrame):
    """
    - First three sheets get one new timestamped column each run.
    - If a table has only one data column, it uses that.
    - 'Contracts' sheet appends new rows then drops duplicates.
    """
    # load existing or init
    if os.path.exists(HISTORY_FILE):
        with pd.ExcelFile(HISTORY_FILE) as xls:
            history = {
                name: pd.read_excel(xls, sheet_name=name, index_col=0)
                for name in scraped_tables.keys()
            }
            history["Contracts"] = pd.read_excel(xls, sheet_name="Contracts")
    else:
        history = {name: pd.DataFrame() for name in scraped_tables.keys()}
        history["Contracts"] = pd.DataFrame()

    ts_col = datetime.now().strftime("%Y-%m-%d %H:%M")

    # merge first three, with safe column selection
    for name, df in scraped_tables.items():
        df_idx = df.set_index(df.columns[0])
        ncols = df_idx.shape[1]
        if ncols >= 2:
            col = df_idx.iloc[:, 1]
        elif ncols == 1:
            col = df_idx.iloc[:, 0]
        else:
            print(f"⚠️ Sheet '{name}' has no data columns, skipping.")
            continue

        col_df = pd.DataFrame({ts_col: col})

        if history[name].empty:
            history[name] = col_df
        else:
            history[name][ts_col] = col_df[ts_col]

    # merge contracts
    combined = pd.concat([history["Contracts"], contracts_df], ignore_index=True)
    combined = combined.drop_duplicates()
    history["Contracts"] = combined

    # write back out
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with pd.ExcelWriter(HISTORY_FILE, engine="openpyxl") as writer:
        for name, df in history.items():
            df.to_excel(writer, sheet_name=name[:31])

    print(f"✅ History updated in {HISTORY_FILE}")

# ───────── MAIN WORKFLOW ─────────
def run():
    from_date, to_date = get_date_range()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("🔐 Logging in...")
        login(page)

        print("📁 Navigating to 'Center Analysis' report selection...")
        page.click("text=Reports")
        time.sleep(1)

        print(f"📆 Setting date range: {from_date} to {to_date}")
        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel", to_date)

        print("📤 Running the report...")
        page.click("text=Do Report")

        print("🔗 Opening report content...")
        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        full_url = f"https://newton.hosting.memetic.it/assist/{href}" if href else page.url
        report_page = context.new_page()
        report_page.goto(full_url)
        report_page.wait_for_load_state("networkidle")
        time.sleep(2)

        print("📋 Parsing page HTML...")
        html = report_page.content()
        soup = BeautifulSoup(html, "lxml")

        tables = soup.find_all("table")
        if len(tables) < 4:
            print(f"❌ Expected ≥4 tables but found {len(tables)}. Aborting.")
            browser.close()
            return

        main_tables = [tables[0], tables[1], tables[-2], tables[-1]]
        sheet_names = [
            "Consultation Agenda Outcomes",
            "Sessions by Device Type",
            "Payments",
            "Contracts"
        ]

        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        writer = pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl")

        # collect dfs for history before writing
        scraped = {}

        for tbl, sheet in zip(main_tables, sheet_names):
            html_tbl = str(tbl)
            try:
                df = pd.read_html(html_tbl, flavor="lxml")[0]
            except Exception as e:
                print(f"❌ Failed to parse '{sheet}': {e}")
                continue

            if sheet == "Payments":
                df.columns = ["Metric", "Value"]
                df["Metric"] = df["Metric"].str.strip().str.rstrip(":")
            elif sheet == "Contracts":
                if len(df.columns) >= 6:
                    df.columns = ["Name", "Surname", "Assistant", "Date", "Details", "Amount"]

            # write each sheet
            df.to_excel(writer, sheet_name=sheet[:31], index=False)

            # stash for history
            if sheet == "Contracts":
                contracts_df = df.copy()
            else:
                scraped[sheet] = df.copy()

        writer.close()
        print(f"✅ Done! Center Analysis report saved to {OUTPUT_FILE}.")

        # ───────── UPDATE HISTORY ─────────
        update_history(scraped, contracts_df)

        browser.close()

if __name__ == "__main__":
    run()
