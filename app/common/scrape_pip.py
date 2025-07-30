import sys
import os
import time
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from io import StringIO
from app.common.cleaners import drop_unwanted_rows

LOGIN_URL = "https://newton.hosting.memetic.it/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"


def get_date_range(months_back: int = 6, months_forward: int = 0):
    """
    Return (from_date, to_date): six months back through today.
    """
    today = datetime.today()
    from_date = (today - relativedelta(months=months_back)).strftime("%m/%d/%Y")
    to_date   = today.strftime("%m/%d/%Y")
    return from_date, to_date


def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=10000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15000)


def scrape_pip(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Scrape the PIP report via HTML parsing, return a cleaned DataFrame.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()

        login(page)
        page.click("text=Reports")
        page.wait_for_timeout(1000)
        page.click("text=PIP", timeout=15000)
        page.wait_for_timeout(1000)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel",   to_date)
        page.click("text=Do Report")

        # wait for report page load and HTML link
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15000)
        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        if not href:
            browser.close()
            raise RuntimeError("HTML download link for PIP not found.")

        report_url = f"https://newton.hosting.memetic.it/assist/{href}"
        report_page = ctx.new_page()
        report_page.goto(report_url)
        report_page.wait_for_load_state("networkidle")
        time.sleep(2)
        html = report_page.content()
        browser.close()

    # parse first table
    soup = BeautifulSoup(html, "lxml")
    tbl = soup.find("table")
    if tbl is None:
        raise RuntimeError("No table found in PIP HTML report.")

    df = pd.read_html(StringIO(str(tbl)), flavor="lxml")[0]
    # rename columns if needed
    if df.shape[1] >= 4:
        df.columns = ["Name","Contract Date","Assistant","Total"]

    # apply shared cleaning if applicable
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass

    return df


def main():
    # CLI args or default
    if len(sys.argv) == 3:
        from_date, to_date = sys.argv[1], sys.argv[2]
    else:
        from_date, to_date = get_date_range()

    print(f"⏱️  Scraping PIP from {from_date} to {to_date}…")
    try:
        df = scrape_pip(from_date, to_date)
    except Exception as e:
        print(f"❌ Failed to scrape PIP: {e}")
        return

    if df.empty:
        print("⚠️ No PIP data scraped.")
        return

    out_dir = "downloads/pip"
    os.makedirs(out_dir, exist_ok=True)
    sf = from_date.replace("/", "-")
    st = to_date.replace("/", "-")
    path = os.path.join(out_dir, f"pip_{sf}_{st}.xlsx")
    df.to_excel(path, index=False)
    print(f"✅ Saved cleaned PIP report to {path}")


if __name__ == "__main__":
    main()
