import sys
import os
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright
from app.common.cleaners import drop_unwanted_rows

LOGIN_URL = "https://newton.hosting.memetic.it/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"


def get_date_range(months_back: int = 6, months_forward: int = 6):
    """
    Return (from_date, to_date) covering `months_back` months ago through `months_forward` months ahead.
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
        page.wait_for_timeout(1000)
        page.click("text=Subscriptions", timeout=15000)
        page.wait_for_timeout(1000)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel",   to_date)
        page.click("text=Do Report")
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15000)

        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        url  = f"https://newton.hosting.memetic.it/assist/{href}" if href else page.url
        report_page = ctx.new_page()
        report_page.goto(url)
        report_page.wait_for_selector("table", timeout=10000)

        rows = report_page.locator("table tr")
        headers = [th.inner_text().strip() for th in rows.nth(0).locator("th").all()]
        for i in range(1, rows.count()):
            cols = rows.nth(i).locator("td").all()
            row = [col.inner_text().strip() for col in cols]
            if len(row) == len(headers):
                data.append(row)
        browser.close()

    df = pd.DataFrame(data, columns=headers) if data else pd.DataFrame(columns=headers)
    # apply shared cleaning if applicable
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
        print("⚠️ No data scraped.")
        return

    out_dir = "downloads/subscriptions"
    os.makedirs(out_dir, exist_ok=True)
    sf = from_date.replace("/", "-")
    st = to_date.replace("/", "-")
    out_path = os.path.join(out_dir, f"subscriptions_{sf}_{st}.xlsx")
    df.to_excel(out_path, index=False)
    print(f"✅ Saved cleaned subscriptions report to {out_path}")


if __name__ == "__main__":
    main()
