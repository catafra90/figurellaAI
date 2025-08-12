# app/common/scrape_payments_done.py

import sys
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from io import StringIO

import pandas as pd
import win32clipboard
from playwright.sync_api import sync_playwright

from app.common.cleaners import drop_unwanted_rows
from app.common.utils    import persist_report

LOGIN_URL = "https://newton.hosting.memetic.it/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"


def get_date_range(months_back: int = 6, months_forward: int = 6):
    """
    Return (from_date, to_date) covering `months_back` months ago to
    `months_forward` months ahead. Format: MM/DD/YYYY
    """
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


def scrape_payments_done(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Scrape the Payments Done report for the date range and return a cleaned DataFrame.
    """
    table_html = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()

        login(page)
        page.click("text=Reports")
        page.wait_for_timeout(1_000)
        page.click("text=Payments done", timeout=15_000)
        page.wait_for_timeout(1_000)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel", to_date)
        page.click("text=Do Report")
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15_000)

        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        url  = f"https://newton.hosting.memetic.it/assist/{href}" if href else page.url
        report_page = ctx.new_page()
        report_page.goto(url)
        report_page.wait_for_load_state("networkidle")
        time.sleep(2)

        # select table containing headers 'Expected' and 'Cash In'
        for tbl in report_page.locator("table").all():
            html = tbl.evaluate("el => el.outerHTML")
            if 'Expected' in html and 'Cash In' in html:
                table_html = html
                break

        browser.close()

    if not table_html:
        print("❌ Payments Done table not found.")
        return pd.DataFrame()

    # copy via clipboard for encoding safety
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, table_html)
    win32clipboard.CloseClipboard()
    time.sleep(0.5)
    win32clipboard.OpenClipboard()
    raw = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', errors='ignore')

    df = pd.read_html(StringIO(raw), flavor='lxml')[0]
    # drop extra header rows (indexes 1 and 2)
    df = df.drop(df.index[[1,2]]).reset_index(drop=True)
    df.columns = [
        "Last name", "First name", "Expected", "Cash In", "Instalment", "Amount"
    ]

    # apply shared cleaning if applicable
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass

    return df


def main():
    # parse CLI args or default date window
    if len(sys.argv) == 3:
        from_date, to_date = sys.argv[1], sys.argv[2]
    else:
        from_date, to_date = get_date_range()

    print(f"⏱️  Scraping Payments Done from {from_date} to {to_date}…")
    df = scrape_payments_done(from_date, to_date)
    if df.empty:
        print("⚠️ No data scraped.")
        return

    # persist to DB + history (disable Excel exports once fully DB-driven)
    section_data = {"Payments Done": df}
    persist_report(
        section_data,
        report_key="payments_done",
        to_db=True,
        to_static_excel=False,
        to_download_excel=False
    )

    print("✅ Payments Done persisted to database.")


if __name__ == "__main__":
    main()
