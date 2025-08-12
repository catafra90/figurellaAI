# app/common/scrape_agenda.py

import sys
import os
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright

from app.common.cleaners import drop_unwanted_rows
from app.common.utils    import persist_report

LOGIN_URL = "https://newton.hosting.memetic.it/login"


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
    page.fill("#txtUsername", "Tutor")
    page.fill("#txtPassword", "FiguMass2025$")
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15_000)


def scrape_agenda(from_date: str, to_date: str) -> pd.DataFrame:
    data = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()

        login(page)
        page.click("text=Reports");  page.wait_for_timeout(500)
        page.click("text=Agenda");   page.wait_for_timeout(500)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel", to_date)
        page.click("text=Do Report")

        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15_000)
        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        if not href:
            print("❌ Could not extract report link.")
            browser.close()
            return pd.DataFrame()

        report_url  = f"https://newton.hosting.memetic.it/assist/{href}"
        report_page = ctx.new_page()
        report_page.goto(report_url)
        report_page.wait_for_selector("table", timeout=10_000)

        rows    = report_page.locator("table tr")
        headers = [
            "First Name", "Last Name", "Email", "Phone",
            "Customer Status", "Day", "Appointment Status"
        ]

        for i in range(1, rows.count()):
            cols = rows.nth(i).locator("td").all()
            row  = [col.inner_text().strip() for col in cols]
            if len(row) == len(headers):
                data.append(row)

        browser.close()

    df = pd.DataFrame(data, columns=headers) if data else pd.DataFrame()
    if df.empty:
        return df

    return drop_unwanted_rows(df)


def main():
    # 1) parse dates
    if len(sys.argv) == 3:
        from_date, to_date = sys.argv[1], sys.argv[2]
    else:
        from_date, to_date = get_date_range()

    print(f"⏱️  Scraping Agenda from {from_date} to {to_date}…")
    df = scrape_agenda(from_date, to_date)
    if df.empty:
        print("⚠️ No data scraped or data filtered out.")
        return

    # 2) persist into DB + history (and Excel if you leave defaults True)
    section_data = {"Agenda": df}
    persist_report(
        section_data,
        report_key="agenda",
        to_db=True,
        to_static_excel=False,   # turn on if you still want static/reports .xlsx
        to_download_excel=False  # turn on if you still want download/ .xlsx
    )
    print("✅ Agenda persisted to database.")

if __name__ == "__main__":
    main()
