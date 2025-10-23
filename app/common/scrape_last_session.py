# app/common/scrape_last_session.py

import os
import sys
import subprocess
from datetime import datetime
from typing import List
from urllib.parse import urljoin

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

BASE_URL = "https://newton.hosting.memetic.it"
LAST_SESSION_PATHS = [
    "/assist/report_ultimasessione",   # IT slug (common)
    "/assist/report_lastsession",      # EN slug (possible)
]

# ---------- login & navigation ----------

def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=10_000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15_000)

def goto_last_session(page):
    """
    Navigate to Reports → Last Session with multiple fallbacks.
    """
    # Try to open Reports menu (ignore if already open)
    try:
        page.click("text=Reports")
        page.wait_for_timeout(250)
    except Exception:
        pass

    # 1) Text labels (EN/IT)
    for label in ("Last Session", "Last session", "Ultima sessione", "Ultima seduta"):
        try:
            page.click(f"text={label}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(400)
            return
        except Exception:
            continue

    # 2) Likely link IDs
    for css in ("#ctl00_cphMain_lnkLastSession",
                "#ctl00_cphMain_lnkUltimaSessione",
                "#ctl00_cphMain_lnkUltimaSeduta"):
        try:
            page.click(css)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(400)
            return
        except Exception:
            continue

    # 3) Direct URL once authenticated
    for path in LAST_SESSION_PATHS:
        try:
            page.goto(urljoin(BASE_URL, path), wait_until="networkidle")
            page.wait_for_selector("body", timeout=10_000)
            page.wait_for_timeout(400)
            return
        except Exception:
            continue

    raise RuntimeError("Could not open Last Session report page.")

# ---------- helpers ----------

# Italian column names we expect (no normalization)
ITALIAN_DATE_COLS = {"Ultima seduta", "Fine contratto"}
ITALIAN_NUM_COLS  = {"Bubble", "Cellushape"}  # these labels appear unchanged

def _fill_first(page, selectors: List[str], value: str) -> bool:
    for sel in selectors:
        try:
            page.fill(sel, value)
            return True
        except Exception:
            continue
    return False

def _click_first(page, selectors: List[str]) -> bool:
    for sel in selectors:
        try:
            page.click(sel)
            return True
        except Exception:
            continue
    return False

def _coerce_types_it(df: pd.DataFrame) -> pd.DataFrame:
    # Dates (keep as strings if parsing fails)
    for c in ITALIAN_DATE_COLS:
        if c in df.columns:
            df[c] = (
                pd.to_datetime(df[c], errors="coerce", dayfirst=True)
                  .dt.strftime("%m/%d/%Y")
                  .fillna(df[c].astype(str))
            )

    # Numerics
    for c in ITALIAN_NUM_COLS:
        if c in df.columns:
            df[c] = (
                df[c].astype(str)
                     .str.replace(r"[^\d\-\.,]", "", regex=True)
                     .str.replace(",", "", regex=False)
                     .replace("", "0")
                     .astype(float)
                     .fillna(0.0)
            )

    # Remove duplicated columns if any
    df = df.loc[:, ~df.columns.duplicated()]
    return df

def _dedupe_last_session_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep a single, best row per client:
      - prefer rows that have Contract expiration (Fine contratto / Contract expiration)
      - then prefer the newest Last session (Ultima seduta / Last session)
    Works with IT or EN headers.
    """
    if df is None or df.empty:
        return df.copy()

    dff = df.copy()

    # Column resolution (IT + EN fallbacks)
    def pick(*names):
        for n in names:
            if n in dff.columns:
                return n
        return None

    last_name  = pick("Cognome", "Last name")
    first_name = pick("Nome", "First name")
    last_sess  = pick("Ultima seduta", "Last session")
    exp_col    = pick("Fine contratto", "Contract expiration")

    # Need at least first/last (or bail)
    if not (first_name and last_name):
        return dff

    # Normalized full name
    dff["__full_norm"] = (
        dff[first_name].astype(str).str.strip() + " " + dff[last_name].astype(str).str.strip()
    ).str.replace(r"\s+", " ", regex=True).str.casefold()

    # Parse dates (strings may already be mm/dd/yyyy)
    d_last = pd.to_datetime(dff[last_sess], errors="coerce") if last_sess else pd.NaT
    d_exp  = pd.to_datetime(dff[exp_col],   errors="coerce") if exp_col   else pd.NaT

    dff["__has_exp"] = d_exp.notna().astype(int)
    dff["__last_dt"] = d_last

    # Sort: has_exp DESC, last_session DESC
    dff = dff.sort_values(["__has_exp", "__last_dt"], ascending=[False, False])

    # If Email exists, use it to avoid merging true homonyms
    subset_cols = ["__full_norm"]
    if "Email" in dff.columns:
        subset_cols.append("Email")

    dff = dff.drop_duplicates(subset=subset_cols, keep="first")

    # Cleanup temp columns
    return dff.drop(columns=["__full_norm", "__has_exp", "__last_dt"], errors="ignore")

# ---------- table parsing ----------

def _parse_last_session_table(page_or_report_page) -> pd.DataFrame:
    """
    Parse the visible table (export page or inline UpdatePanel).
    If there is no <thead>, use the LAST <tr> that contains <th> inside <tbody>
    as the header row (skips the top-level group header like 'Residuals').
    """
    candidates = [
        "#ctl00_cphMain_upnlMain table",
        "#ctl00_cphMain_pnlGrid table",
        "table"
    ]
    tbl = None
    for sel in candidates:
        try:
            page_or_report_page.wait_for_selector(sel, timeout=10_000)
            t = page_or_report_page.locator(sel).first
            if t.locator("th").count() > 0:
                tbl = t
                break
        except Exception:
            continue
    if tbl is None:
        return pd.DataFrame()

    # ----- find the header row -----
    header_tr = None
    header_rows_before_data = 0

    thead = tbl.locator("thead")
    if thead.count() > 0 and thead.locator("tr").count() > 0:
        trs = thead.locator("tr")
        header_tr = trs.nth(trs.count() - 1)
        header_rows_before_data = trs.count()
    else:
        # No <thead>: headers are in <tbody>. Take the LAST tr that has <th>.
        all_trs = tbl.locator("tr")
        th_rows_idx = []
        for i in range(all_trs.count()):
            if all_trs.nth(i).locator("th").count() > 0:
                th_rows_idx.append(i)
        if not th_rows_idx:
            # fallback: gather any th in table
            headers = [th.inner_text().strip() for th in tbl.locator("th").all()]
            headers = [h for h in headers if h]
            return pd.DataFrame(columns=headers)
        last_header_idx = th_rows_idx[-1]
        header_tr = all_trs.nth(last_header_idx)
        header_rows_before_data = last_header_idx + 1  # data starts after this index

    headers = [th.inner_text().strip() for th in header_tr.locator("th").all()]
    headers = [h for h in headers if h]  # drop empty from colspans

    # ----- collect rows -----
    # Prefer <tbody> rows; if that yields nothing, take any <tr> AFTER the header row.
    body_rows = tbl.locator("tbody tr")
    data = []

    if body_rows.count() > 0:
        for i in range(body_rows.count()):
            row = body_rows.nth(i)
            # skip header-like rows that still use <th>
            if row.locator("th").count() > 0:
                continue
            tds = row.locator("td").all()
            vals = [td.inner_text().strip() for td in tds]
            if len(vals) == len(headers) + 1:
                vals = vals[1:]  # skip row-number col if present
            if len(vals) == len(headers) and any(v for v in vals):
                data.append(vals)
    else:
        all_trs = tbl.locator("tr")
        total = all_trs.count()
        for i in range(header_rows_before_data, total):
            row = all_trs.nth(i)
            if row.locator("th").count() > 0:
                continue
            tds = row.locator("td").all()
            vals = [td.inner_text().strip() for td in tds]
            if len(vals) == len(headers) + 1:
                vals = vals[1:]
            if len(vals) == len(headers) and any(v for v in vals):
                data.append(vals)

    if not data:
        return pd.DataFrame(columns=headers)

    df = pd.DataFrame(data, columns=headers)

    # Drop grouped header column if it leaked
    for g in ("Residuals", "Residui"):
        if g in df.columns:
            df.drop(columns=[g], inplace=True, errors="ignore")

    # Clean & types (Italian labels preserved)
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass

    df = _coerce_types_it(df)
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    return df

def scrape_last_session_chunk(ctx_page, from_date: str, to_date: str) -> pd.DataFrame:
    """
    Scrape a single [from_date, to_date] chunk using an existing Playwright context/page.
    Works whether the report offers an HTML export link or just updates the grid in-page.
    """
    page = ctx_page["page"]
    ctx  = ctx_page["ctx"]

    goto_last_session(page)

    # Date inputs: try several IDs (reports can differ)
    date_from_ids = [
        "#ctl00_cphMain_SelectDataDal_txtDataSel",
        "#ctl00_cphMain_txtDataDal",
        "input[id*='DataDal']",
        "input[id*='From']",
    ]
    date_to_ids = [
        "#ctl00_cphMain_SelectDataAl_txtDataSel",
        "#ctl00_cphMain_txtDataAl",
        "input[id*='DataAl']",
        "input[id*='To']",
    ]

    ok_from = _fill_first(page, date_from_ids, from_date)
    ok_to   = _fill_first(page, date_to_ids,   to_date)
    if not (ok_from and ok_to):
        try:
            archive_text("last_session", page.content(), tag="no_date_inputs", ext="html")
        except Exception:
            pass
        return pd.DataFrame()

    # Run/Generate button: try several labels/IDs
    run_buttons = [
        "text=Do Report",
        "text=Generate",
        "text=Visualizza",
        "text=Esegui",
        "text=Mostra",
        "#ctl00_cphMain_btnUltimaSessione",
        "#ctl00_cphMain_btnExecute",
        "button:has-text('Report')",
    ]
    if not _click_first(page, run_buttons):
        try:
            archive_text("last_session", page.content(), tag="no_run_button", ext="html")
        except Exception:
            pass
        return pd.DataFrame()

    # Give the UpdatePanel a moment; then wait for either rows OR an export link
    page.wait_for_timeout(500)
    try:
        page.wait_for_selector(
            "#ctl00_cphMain_hlyDownloadHTML, "
            "#ctl00_cphMain_upnlMain table td, "
            "#ctl00_cphMain_pnlGrid table td, "
            "table td",
            timeout=8_000
        )
    except Exception:
        pass

    # Try to get an export link first…
    export_selectors = [
        "#ctl00_cphMain_hlyDownloadHTML",
        "a[href*='report_']",
        "a:has-text('HTML')",
        "a:has-text('Scarica')",
    ]
    href = None
    for sel in export_selectors:
        try:
            page.wait_for_selector(sel, timeout=8_000)
            href = page.get_attribute(sel, "href")
            if href:
                break
        except Exception:
            continue

    if href:
        # Open export and parse
        report_url = urljoin(BASE_URL + "/assist/", href.lstrip("/"))
        rpage = ctx.new_page()
        rpage.goto(report_url)
        try:
            rpage.wait_for_selector("table", timeout=15_000)
        except Exception:
            pass

        try:
            html = rpage.content()
            archive_text("last_session", html, tag=f"{from_date}_to_{to_date}", ext="html")
        except Exception:
            pass

        df = _parse_last_session_table(rpage)
        df = _dedupe_last_session_rows(df)
        rpage.close()
        return df

    # …otherwise, parse the table that updated inline on the same page
    try:
        html = page.content()
        archive_text("last_session", html, tag=f"inline_{from_date}_to_{to_date}", ext="html")
    except Exception:
        pass

    df = _parse_last_session_table(page)
    df = _dedupe_last_session_rows(df)
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
            print(f"→ Last Session window {frm} → {to}", flush=True)
            try:
                df_win = scrape_last_session_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[Last Session] window {frm} → {to} error: {e}", flush=True)
                continue
            if not df_win.empty:
                frames.append(df_win)

        browser.close()

    if not frames:
        return pd.DataFrame()
    big = pd.concat(frames, ignore_index=True)
    big = _dedupe_last_session_rows(big)
    return big

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
            print(f"→ Last Session backfill window {frm} → {to}", flush=True)
            try:
                df_win = scrape_last_session_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[Last Session] backfill window {frm} → {to} error: {e}", flush=True)
                continue
            if not df_win.empty:
                frames.append(df_win)

        browser.close()

    if not frames:
        return pd.DataFrame()
    big = pd.concat(frames, ignore_index=True)
    big = _dedupe_last_session_rows(big)
    return big

# ---------- PK inference ----------

def _infer_pk(df: pd.DataFrame) -> List[str]:
    """
    Stable composite key for de-duplication with Italian columns.
    Prefer: Cognome + Nome + Ultima seduta (+ Fine contratto if present).
    """
    candidates = []
    for c in ("Cognome", "Nome"):
        if c in df.columns: candidates.append(c)
    for c in ("Ultima seduta", "Fine contratto"):
        if c in df.columns: candidates.append(c)
    # useful disambiguators
    for c in ("Email", "Telefono", "Stato"):
        if c in df.columns and c not in candidates: candidates.append(c)

    return candidates or [df.columns[0]]

# ---------- daily window via subprocess ----------

def _month_window_daily():
    today = datetime.today()
    start = today - relativedelta(months=6)
    end   = today + relativedelta(months=6)
    return fmt_mmddyyyy(start), fmt_mmddyyyy(end)

def _run_one_window_subprocess(frm: str, to: str, timeout_s: int = 180) -> int:
    cmd = [sys.executable, "-u", "-m", "app.common.scrape_last_session", frm, to]
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", os.getcwd())
    print(f"   -> app.common.scrape_last_session  {frm}  →  {to}", flush=True)
    try:
        res = subprocess.run(cmd, env=env, timeout=timeout_s)
        print(f"   <- exit {res.returncode} for {frm} → {to}", flush=True)
        return res.returncode
    except subprocess.TimeoutExpired:
        print(f"   !! window {frm} → {to} timed out after {timeout_s}s; skipping.", flush=True)
        return 124

# ---------- CLI entry ----------

def get_date_range(months_back: int = 6, months_forward: int = 6):
    today = datetime.today()
    return (
        (today - relativedelta(months=months_back)).strftime("%m/%d/%Y"),
        (today + relativedelta(months=months_forward)).strftime("%m/%d/%Y"),
    )

def main():
    # 1) One-time backfill (example): Jan 1, 2025 → today
    if len(sys.argv) == 2 and sys.argv[1] == "--backfill-2025":
        start_dt = datetime(2025, 1, 1)
        end_dt   = datetime.today()
        print(f"⏱️  Backfilling Last Session from {start_dt:%m/%d/%Y} to {end_dt:%m/%d/%Y}…", flush=True)
        df = run_backfill_fixed(start_dt, end_dt, chunk_max=12, overlap=2)
        if df.empty:
            print("⚠️ No data scraped.", flush=True); return
        df = _dedupe_last_session_rows(df)
        pk_cols = _infer_pk(df)
        added = merge_into_history("last_session", df, pk_cols=pk_cols)
        print(f"✅ Last Session BACKFILL merged. New/updated rows: {added}", flush=True)
        return

    # 2) Manual single window (in-process)
    if len(sys.argv) == 3:
        frm, to = sys.argv[1], sys.argv[2]
        print(f"⏱️  Scraping Last Session (single window) {frm} → {to} …", flush=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx     = browser.new_context()
            page    = ctx.new_page()
            login(page)
            df = scrape_last_session_chunk({"ctx": ctx, "page": page}, frm, to)
            browser.close()

        if df.empty:
            print("⚠️ No data scraped.", flush=True); return

        df = _dedupe_last_session_rows(df)
        pk_cols = _infer_pk(df)
        added = merge_into_history("last_session", df, pk_cols=pk_cols)
        print(f"✅ Last Session merged. New/updated rows: {added}", flush=True)
        return

    # 3) Default refresh/daily: one ±6m window via subprocess (timeout guard)
    print("⏱️  Scraping Last Session (±6 months) via subprocess …", flush=True)
    frm, to = _month_window_daily()
    rc = _run_one_window_subprocess(frm, to, timeout_s=180)
    if rc != 0:
        print("⚠️ Last Session daily window failed or timed out.", flush=True)

if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
