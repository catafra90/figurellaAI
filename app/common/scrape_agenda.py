import sys
import os
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright
from app.common.cleaners import drop_unwanted_rows

LOGIN_URL = "https://newton.hosting.memetic.it/login"


def get_date_range(months_back: int = 6, months_forward: int = 6):
    """
    Compute default date range: today -6mo to today +6mo,
    returned as MM/DD/YYYY strings.
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
    page.fill("#txtUsername", "Tutor")
    page.fill("#txtPassword", "FiguMass2025$")
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15000)


def scrape_agenda(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Fetch the Agenda report for the given date range and return a cleaned DataFrame.
    """
    data = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        login(page)
        page.click("text=Reports")
        page.wait_for_timeout(1000)
        page.click("text=Agenda")
        page.wait_for_timeout(1000)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel", to_date)
        page.click("text=Do Report")

        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15000)
        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        if not href:
            print("❌ Could not extract report link.")
            browser.close()
            return pd.DataFrame()

        report_url = f"https://newton.hosting.memetic.it/assist/{href}"
        report_page = ctx.new_page()
        report_page.goto(report_url)
        report_page.wait_for_selector("table", timeout=10000)

        rows = report_page.locator("table tr")
        headers = ["First Name", "Last Name", "Email", "Phone",
                   "Customer Status", "Day", "Appointment Status"]

        for i in range(1, rows.count()):
            cols = rows.nth(i).locator("td").all()
            row = [col.inner_text().strip() for col in cols]
            if len(row) == len(headers):
                data.append(row)

        browser.close()

    df = pd.DataFrame(data, columns=headers) if data else pd.DataFrame()
    if df.empty:
        return df

    # apply shared cleaning to remove unwanted rows
    return drop_unwanted_rows(df)


def main():
    # 1) Read args or default to ±6 months
    if len(sys.argv) == 3:
        from_date, to_date = sys.argv[1], sys.argv[2]
    else:
        from_date, to_date = get_date_range()

    print(f"⏱️  Scraping Agenda from {from_date} to {to_date}…")
    df = scrape_agenda(from_date, to_date)
    if df.empty:
        print("⚠️ No data scraped or data filtered out.")
        return

    # 2) Save filtered output
    out_dir = "downloads/agenda"
    os.makedirs(out_dir, exist_ok=True)
    safe_from = from_date.replace("/", "-")
    safe_to = to_date.replace("/", "-")
    out_path = os.path.join(out_dir, f"agenda_{safe_from}_{safe_to}.xlsx")
    df.to_excel(out_path, index=False)
    print(f"✅ Saved cleaned agenda report to {out_path}")


if __name__ == "__main__":
    main()
