import sys
import os
import time
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from io import StringIO
from playwright.sync_api import sync_playwright
import win32clipboard
from app.common.cleaners import drop_unwanted_rows

LOGIN_URL = "https://newton.hosting.memetic.it/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"


def get_date_range(months_back: int = 6, months_forward: int = 6):
    """
    Return (from_date, to_date) covering `months_back` months ago to `months_forward` months ahead.
    Format: MM/DD/YYYY
    """
    today = datetime.today()
    return (
        (today - relativedelta(months=months_back)).strftime("%m/%d/%Y"),
        (today + relativedelta(months=months_forward)).strftime("%m/%d/%Y")
    )


def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=10000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15000)


def scrape_payments_done(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Scrape the Payments Done report for the date range and return a cleaned DataFrame.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()

        login(page)
        page.click("text=Reports")
        page.wait_for_timeout(1000)
        page.click("text=Payments done", timeout=15000)
        page.wait_for_timeout(1000)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel", to_date)
        page.click("text=Do Report")
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15000)

        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        url  = f"https://newton.hosting.memetic.it/assist/{href}" if href else page.url
        report_page = ctx.new_page()
        report_page.goto(url)
        report_page.wait_for_load_state("networkidle")
        time.sleep(2)

        # select table containing headers 'Expected' and 'Cash In'
        table_html = None
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

    # save cleaned output
    out_dir = "downloads/payments_done"
    os.makedirs(out_dir, exist_ok=True)
    safe_from = from_date.replace("/", "-")
    safe_to   = to_date.replace("/", "-")
    out_path  = os.path.join(out_dir, f"payments_done_{safe_from}_{safe_to}.xlsx")
    df.to_excel(out_path, index=False)
    print(f"✅ Saved cleaned Payments Done report to {out_path}")


if __name__ == "__main__":
    main()
