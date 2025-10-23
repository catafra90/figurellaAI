# app/common/scrape_clients_to_csv.py

import sys
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
import pandas as pd

from app.common.utils import persist_report

LOGIN_URL = "https://newton.hosting.memetic.it/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"


def get_date_range(days_back: int = 180, days_forward: int = 180):
    today     = datetime.today()
    from_date = (today - timedelta(days=days_back)).strftime("%m/%d/%Y")
    to_date   = (today + timedelta(days=days_forward)).strftime("%m/%d/%Y")
    return from_date, to_date


def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_selector("#txtUser", timeout=10_000)
    page.fill("#txtUser", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("text=Login")
    page.wait_for_selector("text=Reports", timeout=15_000)


def scrape_contracts(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Returns a DataFrame of the 'Contracts' report for the given date range.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()

        print("🔐 Logging in...")
        login(page)

        print("📁 Navigating to 'Contracts' report...")
        page.click("text=Reports")
        page.wait_for_timeout(1_000)
        page.click("text=Contracts")
        page.wait_for_timeout(1_000)

        print(f"📆 Setting date range: {from_date} to {to_date}")
        inputs = page.locator("input[type='text']")
        inputs.nth(0).fill(from_date)
        inputs.nth(1).fill(to_date)

        print("📤 Running the report...")
        with ctx.expect_page() as popup_info:
            page.click("text=Do Report")
        report_page = popup_info.value

        report_page.wait_for_selector("table", timeout=15_000)

        print("📥 Extracting table data...")
        rows    = report_page.locator("table tr")
        header_cells = rows.nth(0).locator("th").all()
        headers = [h.inner_text().strip() for h in header_cells] if header_cells else None

        data = []
        for i in range(1, rows.count()):
            cols = rows.nth(i).locator("td").all()
            row  = [c.inner_text().strip() for c in cols]
            if row:
                data.append(row)

        browser.close()

    if not data:
        print("⚠️ No rows found in 'Contracts' report.")
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=headers) if headers else pd.DataFrame(data)
    return df


def run():
    # parse date args or default to ±180 days
    if len(sys.argv) == 3:
        from_date, to_date = sys.argv[1], sys.argv[2]
    else:
        from_date, to_date = get_date_range()

    print(f"⏱️  Scraping Contracts from {from_date} to {to_date}…")
    df = scrape_contracts(from_date, to_date)
    if df.empty:
        return

    # persist to DB + history; disable Excel exports once fully DB-driven
    section_data = {"Contracts": df}
    persist_report(
        section_data,
        report_key="contracts",
        to_db=True,
        to_static_excel=False,
        to_download_excel=False
    )

    print("✅ Contracts persisted to database.")


if __name__ == "__main__":
    run()
