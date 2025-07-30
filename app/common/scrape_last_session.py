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


def get_date_range(months_back: int = 6, months_forward: int = 0):
    """
    Returns (from_date, to_date) covering `months_back` months ago through `months_forward` months ahead (default: last 6 months up to today).
    Format: MM/DD/YYYY
    """
    today = datetime.today()
    from_date = (today - relativedelta(months=months_back)).strftime("%m/%d/%Y")
    to_date   = (today + relativedelta(months=months_forward)).strftime("%m/%d/%Y")
    return from_date, to_date


def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=10000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15000)


def scrape_last_session(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Scrape the Last Session report between from_date and to_date, return a cleaned DataFrame.
    """
    table_html = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()

        login(page)
        page.click("text=Reports")
        page.wait_for_timeout(1000)
        page.click("text=Last Session", timeout=15000)
        page.wait_for_timeout(1000)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel", to_date)
        page.click("text=Do Report")
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15000)

        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        url  = f"https://newton.hosting.memetic.it/assist/{href}" if href else page.url
        rpt_page = ctx.new_page()
        rpt_page.goto(url)
        rpt_page.wait_for_load_state("networkidle")
        time.sleep(2)

        # copy HTML of the table containing 'Last Session'
        for tbl in rpt_page.locator("table").all():
            html = tbl.evaluate("el => el.outerHTML")
            if 'Last Session' in html or 'Ultima seduta' in html:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, html)
                win32clipboard.CloseClipboard()
                table_html = html
                break
        browser.close()

    if not table_html:
        print("❌ Last Session table not found.")
        return pd.DataFrame()

    # retrieve from clipboard
    win32clipboard.OpenClipboard()
    raw = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', errors='ignore')

    df = pd.read_html(StringIO(raw), flavor='lxml')[0]
    # skip header junk rows
    df = df.iloc[3:].reset_index(drop=True)
    # flatten multi-index columns if any
    if hasattr(df.columns, 'nlevels') and df.columns.nlevels > 1:
        df.columns = [' '.join(filter(None, map(str, c))).strip() for c in df.columns.values]
    df.columns = [
        "Last name","First name","status","phone","email",
        "last session","contract expiration","Bubble","cellushape"
    ]

    # apply shared cleaning if schema matches
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass
    return df


def main():
    # CLI or default date range
    if len(sys.argv) == 3:
        from_date, to_date = sys.argv[1], sys.argv[2]
    else:
        from_date, to_date = get_date_range()

    print(f"⏱️  Scraping Last Session from {from_date} to {to_date}…")
    df = scrape_last_session(from_date, to_date)
    if df.empty:
        print("⚠️ No data scraped.")
        return

    # save cleaned output
    out_dir = "downloads/last_session"
    os.makedirs(out_dir, exist_ok=True)
    sf = from_date.replace('/', '-')
    st = to_date.replace('/', '-')
    out_path = os.path.join(out_dir, f"last_session_{sf}_{st}.xlsx")
    df.to_excel(out_path, index=False)
    print(f"✅ Saved cleaned last session report to {out_path}")


if __name__ == "__main__":
    main()
