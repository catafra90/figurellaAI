# app/common/scrape_contracts.py

import sys
from datetime import datetime
from dateutil.relativedelta import relativedelta

import pandas as pd
from playwright.sync_api import sync_playwright

from app.common.cleaners import drop_unwanted_rows
from app.common.utils    import persist_report

LOGIN_URL = "https://newton.hosting.memetic.it/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"


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
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15_000)


def scrape_contracts(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Scrape the Contracts report between from_date and to_date,
    clean header rows, rename columns, format Amount, and return a DataFrame.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()

        login(page)
        page.click("text=Reports")
        page.wait_for_timeout(500)
        page.click("text=Contracts")
        page.wait_for_timeout(500)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel", to_date)
        page.click("text=Do Report")
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=10_000)

        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        if not href:
            browser.close()
            return pd.DataFrame()

        report_url = f"https://newton.hosting.memetic.it/assist/{href}"
        page.goto(report_url)
        page.wait_for_selector("table", timeout=10_000)

        tbl = page.locator("table").first
        headers = [th.inner_text().strip() for th in tbl.locator("th").all()]

        data = []
        rows = tbl.locator("tr")
        for i in range(1, rows.count()):
            cells = rows.nth(i).locator("td").all()
            values = [c.inner_text().strip() for c in cells]
            if len(values) != len(headers) or values == headers:
                continue
            data.append(values)

        browser.close()

    if not data:
        return pd.DataFrame(columns=headers)

    df = pd.DataFrame(data, columns=headers)

    # Drop true “header” rows if they slipped through
    mask_header = (
        (df.get('Name') == 'Name') &
        (df.get('Surname') == 'Last Name') &
        (df.get('Details') == 'Details')
    )
    df = df.loc[~mask_header].reset_index(drop=True)

    # Rename “Ammount” → “Amount”
    for col in df.columns:
        if col.lower().startswith('ammount'):
            df.rename(columns={col: 'Amount'}, inplace=True)

    # Ensure and format Amount
    if 'Amount' not in df:
        df['Amount'] = 0.0
    df['Amount'] = (
        pd.to_numeric(
            df['Amount']
              .astype(str)
              .str.replace(r'[^\d\.]+', '', regex=True),
            errors='coerce'
        )
        .fillna(0.0)
        .apply(lambda x: f"${x:,.2f}")
    )

    # Drop any duplicate columns
    df = df.loc[:, ~df.columns.duplicated()]

    # Shared cleaning (if any)
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass

    return df


def main():
    # 1) Parse date args or default to ±6 months
    if len(sys.argv) == 3:
        frm, to = sys.argv[1], sys.argv[2]
    else:
        frm, to = get_date_range()

    print(f"⏱️  Scraping Contracts from {frm} to {to}…")
    df = scrape_contracts(frm, to)
    if df.empty:
        print("⚠️ No data scraped.")
        return

    # 2) Persist to DB + history (disable Excel exports if fully DB-driven)
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
    main()
