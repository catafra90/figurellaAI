# app/common/scrape_contracts.py

import os
import sys
import subprocess
from datetime import datetime
from typing import List, Optional

import pandas as pd
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright

from app.common.cleaners import drop_unwanted_rows
from app.common.utils_merge import merge_into_history
from app.common.utils_raw import archive_text, archive_df
from app.common.utils_dates import build_month_windows, fmt_mmddyyyy, month_windows

LOGIN_URL = "https://newton.hosting.memetic.it/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"


# ---------- login & navigation ----------

def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=10_000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15_000)

def goto_contracts(page):
    page.click("text=Reports");   page.wait_for_timeout(250)
    page.click("text=Contracts"); page.wait_for_timeout(250)


# ---------- single-window helpers ----------

def _parse_contracts_table(report_page) -> pd.DataFrame:
    report_page.wait_for_selector("table", timeout=15_000)

    tbl = report_page.locator("table").first
    headers = [th.inner_text().strip() for th in tbl.locator("th").all()]
    rows    = tbl.locator("tr")
    n       = rows.count()

    data: List[List[str]] = []
    for i in range(1, n):
        tds  = rows.nth(i).locator("td").all()
        vals = [td.inner_text().strip() for td in tds]
        if not vals or len(vals) != len(headers):
            continue
        if vals == headers:
            continue
        data.append(vals)

    if not data:
        return pd.DataFrame(columns=headers)

    df = pd.DataFrame(data, columns=headers)

    # Drop duplicated header rows if they slipped through
    if {"Name", "Surname", "Details"}.issubset(df.columns):
        mask_header = (
            df["Name"].astype(str).str.strip().str.lower().eq("name")
            & df["Surname"].astype(str).str.strip().str.lower().isin(["surname", "last name"])
            & df["Details"].astype(str).str.strip().str.lower().eq("details")
        )
        df = df.loc[~mask_header].reset_index(drop=True)

    # Normalize column names: fix 'Ammount' -> 'Amount'
    for c in list(df.columns):
        if isinstance(c, str) and c.lower().startswith("ammount"):
            df.rename(columns={c: "Amount"}, inplace=True)

    # Parse Amount to float
    if "Amount" not in df.columns:
        df["Amount"] = 0.0
    df["Amount"] = (
        df["Amount"].astype(str)
        .str.replace(r"[^\d\-\.,]", "", regex=True)
        .str.replace(",", "", regex=False)
        .astype(float)
        .fillna(0.0)
    )

    # Remove duplicated columns if any
    df = df.loc[:, ~df.columns.duplicated()]

    # Shared cleaning
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass

    return df


def scrape_contracts_chunk(ctx_page, from_date: str, to_date: str) -> pd.DataFrame:
    """
    Scrape a single [from_date, to_date] chunk using an existing Playwright context/page.
    """
    page = ctx_page["page"]
    ctx  = ctx_page["ctx"]

    goto_contracts(page)
    page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
    page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel",  to_date)
    page.click("text=Do Report")
    page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=20_000)

    href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
    if not href:
        return pd.DataFrame()

    report_url = f"https://newton.hosting.memetic.it/assist/{href}"
    rpage = ctx.new_page()
    rpage.goto(report_url)
    rpage.wait_for_selector("table", timeout=15_000)

    # Archive raw HTML for this window
    try:
        html = rpage.content()
        archive_text("contracts", html, tag=f"{from_date}_to_{to_date}", ext="html")
    except Exception:
        pass

    df = _parse_contracts_table(rpage)
    rpage.close()

    # Archive parsed snapshot
    if not df.empty:
        try:
            archive_df("contracts", df, tag=f"{from_date}_to_{to_date}")
        except Exception:
            pass

    return df


# ---------- multi-window runners ----------

def run_scrape_windows(months_back=6, months_forward=6, *, chunk_max=12, overlap=2) -> pd.DataFrame:
    """
    Relative windows (e.g., refresh ±6m): reuse one login/session; concat result.
    """
    windows = build_month_windows(months_back, months_forward, chunk_max=chunk_max, overlap=overlap)
    frames: List[pd.DataFrame] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()

        login(page)

        for (start_dt, end_dt) in windows:
            frm, to = fmt_mmddyyyy(start_dt), fmt_mmddyyyy(end_dt)
            print(f"→ Contracts window {frm} → {to}", flush=True)
            try:
                df_win = scrape_contracts_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[Contracts] window {frm} → {to} error: {e}", flush=True)
                continue
            if not df_win.empty:
                frames.append(df_win)

        browser.close()

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def run_backfill_fixed(start_dt: datetime, end_dt: datetime, *, chunk_max=12, overlap=2) -> pd.DataFrame:
    """
    Fixed-date backfill (e.g., 01/01/2025 → today) using month_windows.
    """
    frames: List[pd.DataFrame] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()
        login(page)

        for frm, to in month_windows(start_dt, end_dt, chunk_max=chunk_max, overlap=overlap):
            print(f"→ Contracts backfill window {frm} → {to}", flush=True)
            try:
                df_win = scrape_contracts_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[Contracts] backfill window {frm} → {to} error: {e}", flush=True)
                continue
            if not df_win.empty:
                frames.append(df_win)

        browser.close()

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------- daily run: single ±6m window via subprocess (timeout guard) ----------

def _month_window_daily():
    today = datetime.today()
    start = today - relativedelta(months=6)
    end   = today + relativedelta(months=6)
    return fmt_mmddyyyy(start), fmt_mmddyyyy(end)

def _run_one_window_subprocess(frm: str, to: str, timeout_s: int = 180) -> int:
    """
    Run this module for one window in a separate process with a hard timeout.
    """
    cmd = [sys.executable, "-u", "-m", "app.common.scrape_contracts", frm, to]
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", os.getcwd())
    print(f"   -> app.common.scrape_contracts  {frm}  →  {to}", flush=True)
    try:
        res = subprocess.run(cmd, env=env, timeout=timeout_s)
        print(f"   <- exit {res.returncode} for {frm} → {to}", flush=True)
        return res.returncode
    except subprocess.TimeoutExpired:
        print(f"   !! window {frm} → {to} timed out after {timeout_s}s; skipping.", flush=True)
        return 124


# ---------- PK inference ----------

def _infer_pk(df: pd.DataFrame) -> List[str]:
    """
    Choose a stable composite key for de-duplication.
    Prefer person + date + contract-identifying fields if present.
    """
    candidates = []
    # Person
    for c in ("Name", "First Name"):
        if c in df.columns: candidates.append(c)
    for c in ("Surname", "Last Name"):
        if c in df.columns: candidates.append(c)
    # Date-ish
    for c in ("Date", "Contract Date", "Start Date"):
        if c in df.columns and c not in candidates: candidates.append(c)
    # Identifier-ish
    for c in ("Contract Number", "Contract", "Details", "Plan", "Type"):
        if c in df.columns and c not in candidates: candidates.append(c)

    if candidates:
        return candidates
    return [df.columns[0]]  # fallback


# ---------- CLI entry ----------

def get_date_range(months_back: int = 6, months_forward: int = 6):
    today = datetime.today()
    return (
        (today - relativedelta(months=months_back)).strftime("%m/%d/%Y"),
        (today + relativedelta(months=months_forward)).strftime("%m/%d/%Y"),
    )

def main():
    # 1) One-time backfill flag: Jan 1, 2025 → today (chunked, overlapped)
    if len(sys.argv) == 2 and sys.argv[1] == "--backfill-2025":
        start_dt = datetime(2025, 1, 1)
        end_dt   = datetime.today()
        print(f"⏱️  Backfilling Contracts from {start_dt:%m/%d/%Y} to {end_dt:%m/%d/%Y}…", flush=True)
        df = run_backfill_fixed(start_dt, end_dt, chunk_max=12, overlap=2)
        if df.empty:
            print("⚠️ No data scraped.", flush=True); return
        pk_cols = _infer_pk(df)
        added = merge_into_history("contracts", df, pk_cols=pk_cols)
        print(f"✅ Contracts BACKFILL merged. New/updated rows: {added}", flush=True)
        return

    # 2) Manual single window (in-process): scrape and merge
    if len(sys.argv) == 3:
        frm, to = sys.argv[1], sys.argv[2]
        print(f"⏱️  Scraping Contracts (single window) {frm} → {to} …", flush=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx     = browser.new_context()
            page    = ctx.new_page()
            login(page)
            df = scrape_contracts_chunk({"ctx": ctx, "page": page}, frm, to)
            browser.close()

        if df.empty:
            print("⚠️ No data scraped.", flush=True); return

        pk_cols = _infer_pk(df)
        added = merge_into_history("contracts", df, pk_cols=pk_cols)
        print(f"✅ Contracts merged. New/updated rows: {added}", flush=True)
        return

    # 3) Default refresh/daily: one ±6m window via subprocess (timeout guard)
    print("⏱️  Scraping Contracts (±6 months) via subprocess …", flush=True)
    frm, to = _month_window_daily()
    rc = _run_one_window_subprocess(frm, to, timeout_s=180)
    if rc != 0:
        print("⚠️ Contracts daily window failed or timed out.", flush=True)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
