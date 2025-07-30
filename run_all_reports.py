#!/usr/bin/env python3
import subprocess
import sys
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

# A list of scraper scripts under app/common
SCRAPERS = [
    "scrape_agenda.py",
    "scrape_contracts.py",
    "scrape_customer_acquisitions.py",
    "scrape_ibf.py",
    "scrape_last_session.py",
    "scrape_payments_done.py",
    "scrape_payments_due.py",
    "scrape_subscriptions.py",
    "scrape_pip.py",
]


def get_date_range():
    """Return (from_date, to_date) as MM/DD/YYYY: ±6 months around today."""
    today = datetime.today()
    return (
        (today - relativedelta(months=6)).strftime("%m/%d/%Y"),
        (today + relativedelta(months=6)).strftime("%m/%d/%Y")
    )


def run_scraper(script, from_date, to_date):
    path = os.path.join(os.getcwd(), "app", "common", script)
    cmd = [sys.executable, path, from_date, to_date]
    print(f"▶ Running {script} for {from_date} → {to_date}")
    subprocess.run(cmd, check=True)


def main():
    from_date, to_date = get_date_range()

    # Ensure Playwright and dependencies are installed
    try:
        import playwright  # noqa
    except ImportError:
        print("❌ 'playwright' not found. Run: pip install playwright && playwright install")
        sys.exit(1)

    for script in SCRAPERS:
        run_scraper(script, from_date, to_date)

    print("🔄 Building history files…")
    subprocess.run([sys.executable, os.path.join(os.getcwd(), "build_history.py")], check=True)
    print("✅ All reports scraped and history built!")


if __name__ == "__main__":
    main()
