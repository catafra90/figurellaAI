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
    Return (from_date, to_date) spanning six months back through today.
    Format: MM/DD/YYYY
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


def scrape_ibf(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Scrape IBF report via the HTML download, parse first table into DataFrame,
    and apply shared cleaning if applicable.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # login and navigate
        login(page)
        page.click("text=Reports")
        page.wait_for_timeout(1000)
        page.click("#ctl00_cphMain_lnkRiepilogoPerMesi", timeout=15000)
        page.wait_for_timeout(1000)

        # set date range
        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel",   to_date)
        page.click("text=Do Report")

        # wait for HTML export link
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15000)
        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        if not href:
            browser.close()
            raise RuntimeError("HTML download link for IBF not found.")

        full_url = f"https://newton.hosting.memetic.it/assist/{href}"
        report_page = context.new_page()
        report_page.goto(full_url)
        report_page.wait_for_load_state("networkidle")
        time.sleep(1)

        html = report_page.content()
        browser.close()

    # parse the first <table> in the HTML
    soup = BeautifulSoup(html, "lxml")
    tbl = soup.find("table")
    if tbl is None:
        raise RuntimeError("No table found in IBF HTML report.")

    tbl_html = str(tbl)
    df = pd.read_html(tbl_html, flavor="lxml")[0]

    # apply shared cleaning if schema matches
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass

    return df


def main():
    # parse CLI args or default
    if len(sys.argv) == 3:
        from_date, to_date = sys.argv[1], sys.argv[2]
    else:
        from_date, to_date = get_date_range()

    print(f"⏱️  Scraping IBF from {from_date} to {to_date}…")
    try:
        df = scrape_ibf(from_date, to_date)
    except Exception as e:
        print(f"❌ Failed to scrape IBF: {e}")
        return

    if df.empty:
        print("⚠️ IBF report contained no data.")
        return

    # write cleaned output
    out_dir = "downloads/ibf"
    os.makedirs(out_dir, exist_ok=True)
    sf = from_date.replace("/", "-")
    st = to_date.replace("/", "-")
    path = os.path.join(out_dir, f"ibf_{sf}_{st}.xlsx")
    df.to_excel(path, index=False)
    print(f"✅ Saved cleaned IBF report to {path}")


if __name__ == "__main__":
    main()
