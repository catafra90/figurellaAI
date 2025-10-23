# app/common/scrape_agenda.py

import os
import sys
import subprocess
from datetime import datetime
from typing import List, Tuple

import pandas as pd
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright

from app.common.cleaners import drop_unwanted_rows
from app.common.utils_merge import merge_into_history
from app.common.utils_raw import archive_text, archive_df
from app.common.utils_dates import build_month_windows, fmt_mmddyyyy, month_windows

LOGIN_URL = "https://newton.hosting.memetic.it/login"


# ---------- Date helpers (unchanged) ----------

def get_date_range(months_back: int = 6, months_forward: int = 6) -> Tuple[str, str]:
    today = datetime.today()
    return (
        (today - relativedelta(months=months_back)).strftime("%m/%d/%Y"),
        (today + relativedelta(months=months_forward)).strftime("%m/%d/%Y"),
    )


# ---------- Portal helpers (unchanged) ----------

def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=10_000)
    page.fill("#txtUsername", "Tutor")
    page.fill("#txtPassword", "FiguMass2025$")
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15_000)


# ---------- Your original single-window scraper (kept) ----------

def scrape_agenda(from_date: str, to_date: str) -> pd.DataFrame:
    """
    ORIGINAL FLOW (kept): click Reports→Agenda, fill dates, click Do Report,
    wait for export link, open HTML table, read rows with fixed headers.
    """
    data: List[List[str]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        login(page)
        page.click("text=Reports");  page.wait_for_timeout(500)
        page.click("text=Agenda");   page.wait_for_timeout(500)

        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel", to_date)
        page.click("text=Do Report")

        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15_000)
        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
        if not href:
            print("❌ Could not extract report link.", flush=True)
            browser.close()
            return pd.DataFrame()

        report_url = f"https://newton.hosting.memetic.it/assist/{href}"
        report_page = ctx.new_page()
        report_page.goto(report_url)
        report_page.wait_for_selector("table", timeout=10_000)

        # Optional: archive HTML for this window
        try:
            html = report_page.content()
            archive_text("agenda", html, tag=f"{from_date}_to_{to_date}", ext="html")
        except Exception:
            pass

        rows = report_page.locator("table tr")
        headers = [
            "First Name", "Last Name", "Email", "Phone",
            "Customer Status", "Day", "Appointment Status",
        ]

        n = rows.count()
        for i in range(1, n):
            cols = rows.nth(i).locator("td").all()
            row = [col.inner_text().strip() for col in cols]
            if len(row) == len(headers):
                data.append(row)

        browser.close()

    df = pd.DataFrame(data, columns=headers) if data else pd.DataFrame()
    if df.empty:
        return df

    # Optional: archive parsed CSV snapshot
    try:
        archive_df("agenda", df, tag=f"{from_date}_to_{to_date}")
    except Exception:
        pass

    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass
    return df


# ---------- Minimal wrapper: multi-window scrape + concat (for backfills) ----------

def run_scrape_windows(months_back=6, months_forward=6, *, chunk_max=12, overlap=2) -> pd.DataFrame:
    """
    Build windows and call YOUR original scrape_agenda() for each window.
    This is used by the daily/refresh flow (relative windows).
    """
    windows = build_month_windows(months_back, months_forward, chunk_max=chunk_max, overlap=overlap)
    frames: List[pd.DataFrame] = []

    for (start_dt, end_dt) in windows:
        frm, to = fmt_mmddyyyy(start_dt), fmt_mmddyyyy(end_dt)
        print(f"→ Agenda window {frm} → {to}", flush=True)
        try:
            df_win = scrape_agenda(frm, to)
        except Exception as e:
            print(f"[Agenda] window {frm} → {to} error: {e}", flush=True)
            continue
        if not df_win.empty:
            frames.append(df_win)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def run_backfill_fixed(start_dt: datetime, end_dt: datetime, *, chunk_max=12, overlap=2) -> pd.DataFrame:
    """
    Fixed-date backfill using month_windows(start_dt, end_dt).
    """
    frames: List[pd.DataFrame] = []
    for frm, to in month_windows(start_dt, end_dt, chunk_max=chunk_max, overlap=overlap):
        print(f"→ Agenda backfill window {frm} → {to}", flush=True)
        try:
            df_win = scrape_agenda(frm, to)
        except Exception as e:
            print(f"[Agenda] backfill window {frm} → {to} error: {e}", flush=True)
            continue
        if not df_win.empty:
            frames.append(df_win)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------- Daily run: single ±6m window executed in a subprocess (no hangs) ----------

def _month_windows_for_daily():
    # one 12-month window: 6 back + 6 forward
    today = datetime.today()
    start = today - relativedelta(months=6)
    end = today + relativedelta(months=6)
    return [(fmt_mmddyyyy(start), fmt_mmddyyyy(end))]

def _run_one_window_subprocess(frm: str, to: str, timeout_s: int = 150) -> int:
    """
    Run this module for one window in a separate process with a hard timeout.
    Using -u (unbuffered) so logs appear immediately.
    """
    cmd = [sys.executable, "-u", "-m", "app.common.scrape_agenda", frm, to]
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", os.getcwd())
    print(f"   -> app.common.scrape_agenda  {frm}  →  {to}", flush=True)
    try:
        res = subprocess.run(cmd, env=env, timeout=timeout_s)
        print(f"   <- exit {res.returncode} for {frm} → {to}", flush=True)
        return res.returncode
    except subprocess.TimeoutExpired:
        print(f"   !! window {frm} → {to} timed out after {timeout_s}s; skipping.", flush=True)
        return 124


# ---------- CLI entry ----------

def main():
    # 1) Special flag: one-time backfill from Jan 1, 2025 → today
    if len(sys.argv) == 2 and sys.argv[1] == "--backfill-2025":
        start_dt = datetime(2025, 1, 1)
        end_dt   = datetime.today()
        print(f"⏱️  Backfilling Agenda from {start_dt:%m/%d/%Y} to {end_dt:%m/%d/%Y}…", flush=True)
        df = run_backfill_fixed(start_dt, end_dt, chunk_max=12, overlap=2)
        if df.empty:
            print("⚠️ No data scraped.", flush=True)
            return
        pk = [c for c in ("First Name", "Last Name", "Day", "Appointment Status") if c in df.columns]
        if not pk:
            pk = df.columns[:2].tolist()
        added = merge_into_history("agenda", df, pk_cols=pk)
        print(f"✅ Agenda BACKFILL merged. New/updated rows: {added}", flush=True)
        return

    # 2) Manual 2-arg window: run original flow and merge
    if len(sys.argv) == 3:
        from_date, to_date = sys.argv[1], sys.argv[2]
        print(f"⏱️  Scraping Agenda from {from_date} to {to_date}…", flush=True)
        df = scrape_agenda(from_date, to_date)
        if df.empty:
            print("⚠️ No data scraped or data filtered out.", flush=True)
            return
        pk = [c for c in ("First Name", "Last Name", "Day", "Appointment Status") if c in df.columns]
        if not pk:
            pk = df.columns[:2].tolist()
        added = merge_into_history("agenda", df, pk_cols=pk)
        print(f"✅ Agenda merged. New/updated rows: {added}", flush=True)
        return

    # 3) Default refresh/daily: one big ±6m window, sandboxed with a hard timeout
    print("⏱️  Scraping Agenda across windows (6 back, 6 forward, 12 max, 2 overlap)…", flush=True)
    nonzero = 0
    for frm, to in _month_windows_for_daily():
        rc = _run_one_window_subprocess(frm, to, timeout_s=150)
        if rc != 0:
            nonzero += 1
    if nonzero:
        print("⚠️ Some Agenda windows failed or timed out.", flush=True)


if __name__ == "__main__":
    # Make sure Python prints immediately (especially on Windows)
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
