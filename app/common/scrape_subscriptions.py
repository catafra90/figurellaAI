# app/common/scrape_subscriptions.py

import sys
from datetime import datetime
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright
import pandas as pd

from app.common.cleaners import drop_unwanted_rows
from app.common.utils    import persist_report

LOGIN_URL = "https://newton.hosting.memetic.it/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"


def get_date_range(months_back: int = 6, months_forward: int = 6):
    """
    Return (from_date, to_date) covering `months_back` months ago
    through `months_forward` months ahead. Format: MM/DD/YYYY
    """
    today = datetime.today()
    from_date = (today - relativedelta(months=months_back)).strftime("%m/%d/%Y")
    to_date   = (today + relativedelta(months=months_forward)).strftime("%m/%d/%Y")
    return from_date, to_date


def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=10_000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15_000)


def scrape_subscriptions(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Scrape the Subscriptions report for the given date range and return a cleaned DataFrame.
    """
    data = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()

        login(page)
        page.click("text=Reports")
        page.wait_for_timeout(1_000)
        page.click("text=Subscriptions", timeout=15_000)
        page.wait_for_timeout(1_000)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel",   to_date)
        page.click("text=Do Report")
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15_000)

        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        url  = f"https://newton.hosting.memetic.it/assist/{href}" if href else page.url
        report_page = ctx.new_page()
        report_page.goto(url)
        report_page.wait_for_selector("table", timeout=10_000)

        rows = report_page.locator("table tr")
        headers = [th.inner_text().strip() for th in rows.nth(0).locator("th").all()]
        for i in range(1, rows.count()):
            cols = rows.nth(i).locator("td").all()
            row  = [col.inner_text().strip() for col in cols]
            if len(row) == len(headers):
                data.append(row)

        browser.close()

    df = pd.DataFrame(data, columns=headers) if data else pd.DataFrame(columns=headers)
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

    print(f"⏱️  Scraping Subscriptions from {from_date} to {to_date}…")
    df = scrape_subscriptions(from_date, to_date)
    if df.empty:
        print("⚠️ No Subscriptions data scraped.")
        return

    # persist to DB + history; disable Excel exports once fully DB-driven
    section_data = {"Subscriptions": df}
    persist_report(
        section_data,
        report_key="subscriptions",
        to_db=True,
        to_static_excel=False,
        to_download_excel=False
    )

    print("✅ Subscriptions persisted to database.")


if __name__ == "__main__":
    main()
