import os
import pandas as pd
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://newton.hosting.memetic.it/login"
OUTPUT_FILE = "contracts_report.xlsx"

def get_date_range():
    today = datetime.today()
    from_date = (today - timedelta(days=180)).strftime("%m/%d/%Y")
    to_date = (today + timedelta(days=180)).strftime("%m/%d/%Y")
    return from_date, to_date

def login(page):
    page.goto(LOGIN_URL)
    page.fill("#txtUser", "Tutor")
    page.fill("#txtPassword", "FiguMass2025$")
    page.click("text=Login")
    page.wait_for_selector("text=Reports")

def run():
    from_date, to_date = get_date_range()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("🔐 Logging in...")
        login(page)

        print("📁 Navigating to 'Contracts' report...")
        page.click("text=Reports")
        page.wait_for_timeout(1000)
        page.click("text=Contracts")
        page.wait_for_timeout(1000)

        print(f"📆 Setting date range: {from_date} to {to_date}")
        page.fill("input[type='text']", from_date)
        page.locator("input[type='text']").nth(1).fill(to_date)

        print("📤 Running the report...")
        with context.expect_page() as report_popup:
            page.click("text=Do Report")

        report_page = report_popup.value
        report_page.wait_for_load_state()
        report_page.wait_for_selector("table")

        print("📥 Extracting table data...")
        rows = report_page.locator("tr")
        headers = [th.inner_text().strip() for th in rows.nth(0).locator("th").all()]
        data = []

        for i in range(1, rows.count()):
            cols = rows.nth(i).locator("td").all()
            row = [col.inner_text().strip() for col in cols]
            if row:
                data.append(row)

        if not data:
            print("⚠️ No rows found in the report.")
            return

        df = pd.DataFrame(data, columns=headers if headers else None)

        print(f"💾 Saving to {OUTPUT_FILE}...")
        df.to_excel(OUTPUT_FILE, index=False)
        print("✅ Done!")

        browser.close()

if __name__ == "__main__":
    run()
