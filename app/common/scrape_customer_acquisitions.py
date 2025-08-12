# app/common/scrape_customer_acquisition.py

import sys
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from io import StringIO

import pandas as pd
from playwright.sync_api import sync_playwright
import win32clipboard

from app.common.cleaners import drop_unwanted_rows
from app.common.utils    import persist_report

LOGIN_URL = "https://newton.hosting.memetic.it/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"


def get_date_range(months_back: int = 6, months_forward: int = 6):
    today = datetime.today()
    return (
        (today - relativedelta(months=months_back)).strftime("%m/%d/%Y"),
        (today + relativedelta(months=months_forward)).strftime("%m/%d/%Y")
    )


def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=10_000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15_000)


def scrape_customer_acquisition(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Scrape the 'Customer Acquisition' report, parse the table, clean it,
    and return a DataFrame.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()

        login(page)
        page.click("text=Reports")
        page.wait_for_timeout(1_000)
        page.click("#ctl00_cphMain_lnkCustomerAcquisition", timeout=15_000)
        page.wait_for_timeout(1_000)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel", to_date)
        page.click("text=Do Report")
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15_000)

        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        report_url = f"https://newton.hosting.memetic.it/assist/{href}"
        report_page = ctx.new_page()
        report_page.goto(report_url)
        report_page.wait_for_load_state("networkidle")
        time.sleep(2)

        # find the table containing "Acquisition date"
        table_html = None
        for tbl in report_page.locator("table").all():
            html = tbl.evaluate("el => el.outerHTML")
            if "Acquisition date" in html:
                table_html = html
                break

        browser.close()

    if not table_html:
        print("❌ Customer Acquisition table not found.")
        return pd.DataFrame()

    # Use clipboard to preserve HTML encoding
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, table_html)
    win32clipboard.CloseClipboard()
    time.sleep(0.5)
    win32clipboard.OpenClipboard()
    raw_html = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()

    # Parse and clean
    df = pd.read_html(StringIO(raw_html), flavor="lxml")[0]
    df = df.iloc[3:].reset_index(drop=True)  # drop header artifacts
    df.columns = [
        "Name", "Email", "Phone",
        "Date of Birth", "Acquisition date",
        "Status", "First Contract"
    ]

    # Shared cleaning
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass

    return df


def main():
    # parse CLI args or default ±6 months
    if len(sys.argv) == 3:
        from_date, to_date = sys.argv[1], sys.argv[2]
    else:
        from_date, to_date = get_date_range()

    print(f"⏱️  Scraping Customer Acquisition from {from_date} to {to_date}…")
    df = scrape_customer_acquisition(from_date, to_date)
    if df.empty:
        print("⚠️ No data scraped.")
        return

    # persist to DB + history; disable Excel exports once fully DB-driven
    section_data = {"Customer Acquisition": df}
    persist_report(
        section_data,
        report_key="customer_acquisition",
        to_db=True,
        to_static_excel=False,
        to_download_excel=False
    )

    print("✅ Customer Acquisition persisted to database.")


if __name__ == "__main__":
    main()
