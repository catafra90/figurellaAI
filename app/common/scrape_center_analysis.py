# app/common/scrape_center_analysis.py
import os
import time
import sys
from datetime import datetime
from dateutil.relativedelta import relativedelta

import pandas as pd
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from app.common.utils import persist_report

# ───────── CONFIG ─────────
LOGIN_URL    = "https://newton.hosting.memetic.it/login"
USERNAME     = "Tutor"
PASSWORD     = "FiguMass2025$"


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
    page.wait_for_selector("#txtUsername", timeout=10_000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15_000)


# ───────── SCRAPE & PARSE ─────────
def scrape_center_analysis(from_date: str, to_date: str) -> dict[str, pd.DataFrame]:
    """
    Returns a mapping of sheet_name -> DataFrame for:
      - Consultation Agenda Outcomes
      - Sessions by Device Type
      - Payments
      - Contracts
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()

        login(page)
        page.click("text=Reports")
        time.sleep(1)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel", to_date)
        page.click("text=Do Report")
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15_000)

        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        report_url = (
            f"https://newton.hosting.memetic.it/assist/{href}"
            if href else page.url
        )

        report_page = ctx.new_page()
        report_page.goto(report_url)
        report_page.wait_for_load_state("networkidle")
        time.sleep(2)

        html  = report_page.content()
        soup  = BeautifulSoup(html, "lxml")
        tables = soup.find_all("table")

        browser.close()

    if len(tables) < 4:
        print(f"❌ Expected ≥4 tables but found {len(tables)}; aborting.")
        return {}

    # pick the four relevant tables
    main_tables = [tables[0], tables[1], tables[-2], tables[-1]]
    sheet_names = [
        "Consultation Agenda Outcomes",
        "Sessions by Device Type",
        "Payments",
        "Contracts"
    ]

    result: dict[str, pd.DataFrame] = {}
    for tbl, name in zip(main_tables, sheet_names):
        try:
            df = pd.read_html(str(tbl), flavor="lxml")[0]
        except Exception as e:
            print(f"❌ Failed to parse '{name}': {e}")
            continue

        # normalize columns
        if name == "Payments":
            df.columns = ["Metric", "Value"]
            df["Metric"] = df["Metric"].str.strip().str.rstrip(":")
        elif name == "Contracts" and len(df.columns) >= 6:
            df.columns = ["Name", "Surname", "Assistant", "Date", "Details", "Amount"]

        result[name] = df

    return result


# ───────── MAIN WORKFLOW ─────────
def run():
    # parse date args or default ±6 months
    if len(sys.argv) == 3:
        from_date, to_date = sys.argv[1], sys.argv[2]
    else:
        from_date, to_date = get_date_range()

    print(f"⏱️  Scraping Center Analysis from {from_date} to {to_date}…")
    section_data = scrape_center_analysis(from_date, to_date)
    if not section_data:
        print("⚠️  No tables scraped; exiting.")
        return

    # persist to DB + history; toggle Excel exports as needed
    persist_report(
        section_data,
        report_key="center_analysis",
        to_db=True,
        to_static_excel=False,   # set True to keep writing static/reports/*.xlsx
        to_download_excel=False  # set True to keep writing download/*.xlsx
    )

    print("✅ Center Analysis persisted to database.")


if __name__ == "__main__":
    run()
