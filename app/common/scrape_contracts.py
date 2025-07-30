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

def get_date_range(months_back=6, months_forward=6):
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

def scrape_contracts(from_date, to_date) -> pd.DataFrame:
    # 1) Scrape raw table
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page    = browser.new_context().new_page()

        login(page)
        page.click("text=Reports"); page.wait_for_timeout(500)
        page.click("text=Contracts"); page.wait_for_timeout(500)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel", to_date)
        page.click("text=Do Report")
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=10000)

        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        if not href:
            browser.close()
            return pd.DataFrame()

        url = f"https://newton.hosting.memetic.it/assist/{href}"
        page.goto(url)
        page.wait_for_selector("table", timeout=10000)

        tbl = page.locator("table").first
        headers = [th.inner_text().strip() for th in tbl.locator("th").all()]

        data = []
        rows = tbl.locator("tr")
        for i in range(1, rows.count()):
            cells = rows.nth(i).locator("td").all()
            values = [c.inner_text().strip() for c in cells]
            if len(values) != len(headers):
                continue
            if values == headers:
                continue
            data.append(values)

        browser.close()

    df = pd.DataFrame(data, columns=headers)
    if df.empty:
        return df

    # 2) Drop those true “header” rows
    mask_header = (
        (df.get('Name') == 'Name') &
        (df.get('Surname') == 'Last Name') &
        (df.get('Details') == 'Details')
    )
    df = df[~mask_header].reset_index(drop=True)

    # 3) Rename any “Ammount” → “Amount”
    for col in df.columns:
        if col.lower().startswith('ammount'):
            df.rename(columns={col: 'Amount'}, inplace=True)

    # 4) Ensure Amount exists & format it
    if 'Amount' not in df:
        df['Amount'] = 0.0
    df['Amount'] = (
        pd.to_numeric(
            df['Amount']\
              .astype(str)\
              .str.replace(r'[^\d\.]+', '', regex=True),
            errors='coerce'
        )
        .fillna(0.0)
        .apply(lambda x: f"${x:,.2f}")
    )

    # 5) Drop duplicate columns (just in case)
    df = df.loc[:, ~df.columns.duplicated()]

    # 6) Apply your shared cleaner (no-ops here if irrelevant)
    try:
        df = drop_unwanted_rows(df)
    except:
        pass

    return df

def main():
    if len(sys.argv) == 3:
        frm, to = sys.argv[1], sys.argv[2]
    else:
        frm, to = get_date_range()

    print(f"⏱️  Scraping Contracts from {frm} to {to}…")
    df = scrape_contracts(frm, to)
    if df.empty:
        print("⚠️ No data scraped.")
        return

    out_dir = "downloads/contracts"
    os.makedirs(out_dir, exist_ok=True)
    fn = f"contracts_{frm.replace('/','-')}_{to.replace('/','-')}.xlsx"
    path = os.path.join(out_dir, fn)
    df.to_excel(path, index=False)
    print(f"✅ Saved cleaned contracts report to {path}")

if __name__ == "__main__":
    main()
