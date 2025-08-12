# app/common/scrape_payments_due.py

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


def get_date_range(months_back: int = 6, months_forward: int = 6):
    """
    Default window: today -6mo through today +6mo, formatted MM/DD/YYYY.
    """
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


def scrape_payments_due(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Scrape the Payments Due report for the given date range,
    parse entries into a DataFrame, apply shared cleaning,
    and return it.
    """
    html_content = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()

        login(page)
        page.click("text=Reports")
        page.wait_for_timeout(1_000)
        page.click("text=Payments due", timeout=15_000)
        page.wait_for_timeout(1_000)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel", to_date)
        page.click("text=Do Report")
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15_000)

        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        report_url = f"https://newton.hosting.memetic.it/assist/{href}" if href else page.url
        report_page = ctx.new_page()
        report_page.goto(report_url)
        report_page.wait_for_load_state("networkidle")
        time.sleep(2)

        html_content = report_page.content()
        browser.close()

    if not html_content:
        print("❌ Payments Due HTML not retrieved.")
        return pd.DataFrame(columns=["Name", "Contract", "Due date", "Amount"])

    # parse with BeautifulSoup
    soup = BeautifulSoup(html_content, "lxml")
    entries = []
    for name_td in soup.find_all("td", class_="titoli", colspan="5"):
        full_name = name_td.get_text(strip=True).replace("\u00a0", " ")
        parts     = full_name.split()
        first     = parts[0]
        last      = " ".join(parts[1:]) if len(parts) > 1 else ""
        customer  = f"{first} {last}".strip()

        row_tr   = name_td.find_parent("tr").find_next_sibling("tr")
        strong   = row_tr.find("strong", string=lambda t: t and t.strip().startswith("Contract:"))
        contract = strong.next_sibling.strip() if strong and strong.next_sibling else ""

        nested = row_tr.find_next("table")
        if not nested:
            continue

        for r in nested.find_all("tr")[1:]:
            tds = r.find_all("td", class_="righe")
            if len(tds) == 2:
                due    = tds[0].get_text(strip=True)
                amount = tds[1].get_text(strip=True)
                entries.append([customer, contract, due, amount])

    # build DataFrame
    df = pd.DataFrame(entries, columns=["Name", "Contract", "Due date", "Amount"]) if entries else pd.DataFrame(columns=["Name", "Contract", "Due date", "Amount"])

    # shared cleaning
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass

    return df


def main():
    # parse CLI args or default ±6 months
    if len(sys.argv) == 3:
        frm, to = sys.argv[1], sys.argv[2]
    else:
        frm, to = get_date_range()

    print(f"⏱️  Scraping Payments Due from {frm} to {to}…")
    df = scrape_payments_due(frm, to)
    if df.empty:
        print("⚠️ No Payments Due entries found.")
        return

    # persist to DB + history; disable Excel exports when fully DB-driven
    section_data = {"Payments Due": df}
    persist_report(
        section_data,
        report_key="payments_due",
        to_db=True,
        to_static_excel=False,
        to_download_excel=False
    )

    print("✅ Payments Due persisted to database.")


if __name__ == "__main__":
    main()
