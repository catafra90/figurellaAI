# app/common/scrape_ibf.py

import sys
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta

import pandas as pd
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from app.common.cleaners import drop_unwanted_rows
from app.common.utils    import persist_report

LOGIN_URL = "https://newton.hosting.memetic.it/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"


def get_date_range(months_back: int = 6, months_forward: int = 0):
    """
    Returns (from_date, to_date) spanning six months back through today.
    Format: MM/DD/YYYY
    """
    today     = datetime.today()
    from_date = (today - relativedelta(months=months_back)).strftime("%m/%d/%Y")
    to_date   = today.strftime("%m/%d/%Y")
    return from_date, to_date


def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=10_000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15_000)


def scrape_ibf(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Scrape the IBF report via HTML download, parse first table into a DataFrame,
    apply shared cleaning, and return it.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()

        # login and navigate
        login(page)
        page.click("text=Reports")
        page.wait_for_timeout(1_000)
        page.click("#ctl00_cphMain_lnkRiepilogoPerMesi", timeout=15_000)
        page.wait_for_timeout(1_000)

        # set date range
        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel",   to_date)
        page.click("text=Do Report")

        # wait for HTML export link
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15_000)
        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        if not href:
            browser.close()
            raise RuntimeError("HTML download link for IBF not found.")

        full_url   = f"https://newton.hosting.memetic.it/assist/{href}"
        report_page = ctx.new_page()
        report_page.goto(full_url)
        report_page.wait_for_load_state("networkidle")
        time.sleep(1)
        html = report_page.content()
        browser.close()

    # parse the first table in the HTML
    soup = BeautifulSoup(html, "lxml")
    tbl  = soup.find("table")
    if tbl is None:
        raise RuntimeError("No table found in IBF HTML report.")

    df = pd.read_html(str(tbl), flavor="lxml")[0]

    # apply shared cleaning if applicable
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass

    return df


def main():
    # parse CLI args or default ±6 months back through today
    if len(sys.argv) == 3:
        frm, to = sys.argv[1], sys.argv[2]
    else:
        frm, to = get_date_range()

    print(f"⏱️  Scraping IBF from {frm} to {to}…")
    try:
        df = scrape_ibf(frm, to)
    except Exception as e:
        print(f"❌ Failed to scrape IBF: {e}")
        return

    if df.empty:
        print("⚠️ IBF report contained no data.")
        return

    # persist to DB + history (disable Excel exports once fully DB-driven)
    section_data = {"IBF": df}
    persist_report(
        section_data,
        report_key="ibf",
        to_db=True,
        to_static_excel=False,
        to_download_excel=False
    )

    print("✅ IBF persisted to database.")


if __name__ == "__main__":
    main()
