# app/common/scrape_pip.py

import os
import sys
import subprocess
import re
from datetime import datetime
from typing import List, Tuple
from io import StringIO
from urllib.parse import urlencode

import pandas as pd
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright

from app.common.utils_merge import merge_into_history
from app.common.utils_raw import archive_text, archive_df
from app.common.utils_dates import build_month_windows, fmt_mmddyyyy, month_windows

LOGIN_URL = "https://newton.hosting.memetic.it/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"

DUMP_ONLY = False

# ---------- login & nav ----------

def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=15_000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=20_000)

def goto_pip(page):
    page.click("text=Reports")
    page.wait_for_timeout(200)
    # Try common labels
    for label in [
        "PIP", "Pip",
        "Payments in period", "Payments In Period",
        "Report payments in period",
        "Incassi periodo", "Pagamenti nel periodo"
    ]:
        try:
            page.click(f"text={label}", timeout=1200)
            page.wait_for_timeout(150)
            return
        except Exception:
            pass
    # Fallback by known links/IDs (if present in menu)
    for sel in ["#ctl00_cphMain_lnkPIP", "#ctl00_cphMain_lnkPaymentsInPeriod", "a[href*='report_paymentsinperiod']"]:
        try:
            if page.locator(sel).count():
                page.locator(sel).first.click()
                page.wait_for_timeout(150)
                return
        except Exception:
            pass
    # Final fallback: go straight to printable shell
    try:
        page.goto("https://newton.hosting.memetic.it/assist/report_paymentsinperiod", wait_until="networkidle")
        return
    except Exception:
        pass
    raise RuntimeError("PIP link not found under Reports")

# ---------- helpers ----------

_MONEY_RE = re.compile(r"[^\d\-\.,]")

def _parse_money(s: str) -> float:
    if s is None:
        return 0.0
    s = str(s).strip()
    if not s:
        return 0.0
    s = _MONEY_RE.sub("", s)
    # normalize 1.234,56 vs 1,234.56
    if "," in s and "." not in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return 0.0

def _dual_date(text: str) -> str:
    """Parse both MM/DD/YYYY and DD/MM/YYYY. Return ISO YYYY-MM-DD or ''."""
    if not text:
        return ""
    d1 = pd.to_datetime(text, dayfirst=False, errors="coerce")
    if pd.notna(d1):
        return d1.date().isoformat()
    d2 = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.notna(d2):
        return d2.date().isoformat()
    return ""

def _build_direct_urls(from_date: str, to_date: str) -> List[str]:
    """
    Build candidate printable URLs for PIP. Some deployments use 'tom' vs 'tomm'.
    Returns a list of plain strings.
      base: /assist/report_paymentsinperiod
      params: CLIENT_ID=0, fromgg, frommm, fromaa, togg, tom|tomm, toaa
    """
    def _parts(mdY: str):
        mm, dd, yyyy = mdY.split("/")
        return dd.zfill(2), mm.zfill(2), yyyy

    f_dd, f_mm, f_yyyy = _parts(from_date)
    t_dd, t_mm, t_yyyy = _parts(to_date)

    base = "https://newton.hosting.memetic.it/assist/report_paymentsinperiod"

    params1 = {
        "CLIENT_ID": "0",
        "fromgg": f_dd, "frommm": f_mm, "fromaa": f_yyyy,
        "togg": t_dd,  "tom":   t_mm,   "toaa":  t_yyyy,
    }
    params2 = {
        "CLIENT_ID": "0",
        "fromgg": f_dd, "frommm": f_mm, "fromaa": f_yyyy,
        "togg": t_dd,  "tomm":  t_mm,   "toaa":  t_yyyy,
    }

    return [
        f"{base}?{urlencode(params1)}",
        f"{base}?{urlencode(params2)}",
    ]

# ---------- parsing ----------

def _pick_main_table(soup: BeautifulSoup):
    """
    Choose the main PIP table by:
    1) finding the H2 span#cphMain_lblTitolo (the one that shows the date window), then
    2) picking the FIRST sibling/descendant table with classes 'table table-condensed table-bordered table-hover'.
       Skip the 'Recap by Assistant' table (headers like Sigla/Totale).
    """
    title = soup.select_one("#cphMain_lblTitolo")
    if title:
        container = title.find_parent(class_=re.compile(r"\bcol-md-10\b")) or soup
        tbl = container.select_one("table.table.table-condensed.table-bordered.table-hover")
        if tbl:
            first_tr = tbl.tbody.find("tr") if getattr(tbl, "tbody", None) else tbl.find("tr")
            if first_tr:
                headers = [c.get_text(" ", strip=True).lower() for c in first_tr.find_all(["td","th"])]
                joined = " ".join(headers)
                if "sigla" in joined or "recap" in joined:
                    tbl = None
            if tbl:
                return tbl
    # Fallback: first table having 'Customer' and 'Tot' in header
    for tbl in soup.select("table"):
        tr = (tbl.tbody.find("tr") if getattr(tbl, "tbody", None) else tbl.find("tr")) if tbl else None
        if not tr:
            continue
        headers = [c.get_text(" ", strip=True).lower() for c in tr.find_all(["td","th"])]
        if headers and any("customer" in h for h in headers) and any(("tot" in h) or ("total" in h) for h in headers):
            return tbl
    return None

def _parse_pip_html(html: str) -> pd.DataFrame:
    """
    Parse the PIP flat table:
    Columns: Customer | Contract Date | Assit. | Tot.
    Output: Client, ContractDate, Assist, Amount, TxnDate
    """
    if not html:
        return pd.DataFrame()

    soup = BeautifulSoup(html, "html.parser")
    main_tbl = _pick_main_table(soup)
    if not main_tbl:
        return pd.DataFrame()

    body = main_tbl.tbody or main_tbl
    trs  = body.find_all("tr", recursive=False)
    if not trs:
        return pd.DataFrame()

    rows = []

    # Skip header if present and final grand-total tail row (first 3 cells empty)
    for i, tr in enumerate(trs):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 4:
            continue
        # Header row guard
        if i == 0 and "customer" in tds[0].get_text(strip=True).lower():
            continue
        # Tail grand-total guard
        first3 = [tds[j].get_text(" ", strip=True) if j < len(tds) else "" for j in range(3)]
        if all(not s for s in first3):
            continue

        client = " ".join(tds[0].get_text(" ", strip=True).split())
        date_s = tds[1].get_text(strip=True)
        assist = tds[2].get_text(strip=True)
        amt_s  = tds[3].get_text(" ", strip=True)

        iso = _dual_date(date_s)
        if not iso:
            continue

        rows.append({
            "Client":       client,
            "ContractDate": iso,
            "Assist":       assist,
            "Amount":       _parse_money(amt_s),
            "TxnDate":      iso,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Client"] = df["Client"].astype(str).str.strip()
    df["Assist"] = df["Assist"].astype(str).str.strip()
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)
    return df[["Client", "ContractDate", "Assist", "Amount", "TxnDate"]]

# ---------- scrape (single window) ----------

def scrape_pip_chunk(ctx_page, from_date: str, to_date: str) -> pd.DataFrame:
    page = ctx_page["page"]
    ctx  = ctx_page["ctx"]

    goto_pip(page)

    # Interactive attempt
    try:
        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel",  to_date)
    except Exception:
        pass

    clicked = False
    try:
        page.click("text=Do Report"); clicked = True
    except Exception:
        for label in ["Generate", "Visualizza", "Esegui", "Mostra", "Report"]:
            try:
                page.click(f"text={label}", timeout=1200); clicked = True; break
            except Exception:
                pass
        if not clicked:
            for sel in ["#ctl00_cphMain_btnEsegui", "#ctl00_cphMain_btnVisualizza"]:
                try:
                    page.click(sel, timeout=1200); clicked = True; break
                except Exception:
                    pass

    try:
        page.wait_for_selector("table.table", timeout=20_000)
    except Exception:
        pass
    page.wait_for_load_state("networkidle")

    # Attempt 1: current page HTML
    html = page.content()
    try: archive_text("pip", html, tag=f"printable_{from_date}_to_{to_date}", ext="html")
    except Exception: pass

    df = _parse_pip_html(html)
    print(f"[PIP] interactive parsed rows: {len(df)}")
    if not df.empty:
        try: archive_df("pip", df, tag=f"{from_date}_to_{to_date}")
        except Exception: pass
        return df

    # Attempt 2: direct printable URLs (tom / tomm variants)
    for direct_url in _build_direct_urls(from_date, to_date):
        try:
            direct_url = str(direct_url)
            print(f"[PIP] trying direct URL: {direct_url}")

            rpage = ctx.new_page()
            rpage.goto(direct_url, wait_until="networkidle")
            try:
                rpage.wait_for_selector("table.table", timeout=15000)
            except Exception:
                pass

            html2 = rpage.content()
            try: archive_text("pip", html2, tag=f"direct_{from_date}_to_{to_date}", ext="html")
            except Exception: pass

            df2 = _parse_pip_html(html2)
            print(f"[PIP] direct parsed rows: {len(df2)}")
            rpage.close()

            if not df2.empty:
                try: archive_df("pip", df2, tag=f"{from_date}_to_{to_date}")
                except Exception: pass
                return df2
        except Exception as e:
            print(f"[PIP] direct URL attempt failed: {e}")

    # Attempt 3: give back empty DF
    return pd.DataFrame()

# ---------- runners ----------

def run_scrape_windows(months_back=6, months_forward=6, *, chunk_max=12, overlap=2) -> pd.DataFrame:
    windows = build_month_windows(months_back, months_forward, chunk_max=chunk_max, overlap=overlap)
    frames: List[pd.DataFrame] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()
        login(page)
        for (start_dt, end_dt) in windows:
            frm, to = fmt_mmddyyyy(start_dt), fmt_mmddyyyy(end_dt)
            print(f"→ PIP window {frm} → {to}", flush=True)
            try:
                df_win = scrape_pip_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[PIP] window {frm} → {to} error: {e}", flush=True)
                continue
            if not df_win.empty:
                frames.append(df_win)
        browser.close()
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)

def run_backfill_fixed(start_dt: datetime, end_dt: datetime, *, chunk_max=12, overlap=2) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context()
        page    = ctx.new_page()
        login(page)
        for frm, to in month_windows(start_dt, end_dt, chunk_max=chunk_max, overlap=overlap):
            print(f"→ PIP backfill window {frm} → {to}", flush=True)
            try:
                df_win = scrape_pip_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[PIP] backfill window {frm} → {to} error: {e}", flush=True)
                continue
            if not df_win.empty:
                frames.append(df_win)
        browser.close()
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# ---------- PK & CLI ----------

def _infer_pk(df: pd.DataFrame) -> List[str]:
    cols = []
    for c in ("Client", "ContractDate", "Assist", "Amount"):
        if c in df.columns:
            cols.append(c)
    return cols or [str(df.columns[0])]

def _month_window_daily() -> Tuple[str, str]:
    today = datetime.today()
    start = today - relativedelta(months=6)
    end   = today + relativedelta(months=6)
    return fmt_mmddyyyy(start), fmt_mmddyyyy(end)

def _run_one_window_subprocess(frm: str, to: str, timeout_s: int = 180) -> int:
    cmd = [sys.executable, "-u", "-m", "app.common.scrape_pip", frm, to]
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", os.getcwd())
    print(f"   -> app.common.scrape_pip  {frm}  →  {to}", flush=True)
    try:
        res = subprocess.run(cmd, env=env, timeout=timeout_s)
        print(f"   <- exit {res.returncode} for {frm} → {to}", flush=True)
        return res.returncode
    except subprocess.TimeoutExpired:
        print(f"   !! window {frm} → {to} timed out after {timeout_s}s; skipping.", flush=True)
        return 124

def get_date_range(months_back: int = 6, months_forward: int = 6):
    today = datetime.today()
    return (
        (today - relativedelta(months=months_back)).strftime("%m/%d/%Y"),
        (today + relativedelta(months=months_forward)).strftime("%m/%d/%Y"),
    )

def main():
    global DUMP_ONLY

    if len(sys.argv) >= 2 and sys.argv[-1] == "--dump-only":
        DUMP_ONLY = True
        sys.argv = sys.argv[:-1]

    # backfill flag (optional)
    if len(sys.argv) == 2 and sys.argv[1] == "--backfill-2025":
        start_dt = datetime(2025, 1, 1)
        end_dt   = datetime.today()
        print(f"⏱️  Backfilling PIP from {start_dt:%m/%d/%Y} to {end_dt:%m/%d/%Y}…", flush=True)
        df = run_backfill_fixed(start_dt, end_dt, chunk_max=12, overlap=2)
        if df.empty:
            print("⚠️ No data scraped.", flush=True); return
        if DUMP_ONLY:
            try: archive_df("pip_debug", df, tag="backfill_2025")
            except Exception: pass
            print(f"[dump-only] rows={len(df)} cols={list(df.columns)}")
            print(df.head(10).to_string(index=False)); return
        pk_cols = _infer_pk(df)
        added = merge_into_history("pip", df, pk_cols=pk_cols)
        print(f"✅ PIP BACKFILL merged. New/updated rows: {added}", flush=True)
        return

    # manual single window
    if len(sys.argv) == 3:
        frm, to = sys.argv[1], sys.argv[2]
        print(f"⏱️  Scraping PIP (single window) {frm} → {to} …", flush=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx     = browser.new_context()
            page    = ctx.new_page()
            login(page)
            df = scrape_pip_chunk({"ctx": ctx, "page": page}, frm, to)
            browser.close()

        if df.empty:
            print("⚠️ No data scraped.", flush=True); return

        if DUMP_ONLY:
            try: archive_df("pip_debug", df, tag=f"{frm}_to_{to}")
            except Exception: pass
            print(f"[dump-only] rows={len(df)} cols={list(df.columns)}")
            print(df.head(10).to_string(index=False))
            return

        pk_cols = _infer_pk(df)
        added = merge_into_history("pip", df, pk_cols=pk_cols)
        print(f"✅ PIP merged. New/updated rows: {added}", flush=True)
        return

    # default daily refresh (±6m)
    print("⏱️  Scraping PIP (±6 months) via subprocess …", flush=True)
    frm, to = _month_window_daily()
    rc = _run_one_window_subprocess(frm, to, timeout_s=180)
    if rc != 0:
        print("⚠️ PIP daily window failed or timed out.", flush=True)

if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
