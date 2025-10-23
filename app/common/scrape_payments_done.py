# app/common/scrape_payments_done.py

import os
import sys
import subprocess
import re
from io import StringIO
from datetime import datetime
from typing import List, Optional, Tuple
# add near the top
from bs4 import BeautifulSoup

import pandas as pd
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright

from app.common.cleaners import drop_unwanted_rows  # kept for parity
from app.common.utils_merge import merge_into_history
from app.common.utils_raw import archive_text, archive_df
from app.common.utils_dates import build_month_windows, fmt_mmddyyyy, month_windows

LOGIN_URL = "https://newton.hosting.memetic.it/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"

# Optional flag: print parsed rows to archive file but do not merge
DUMP_ONLY = False

# ---------------- Login & Nav ----------------

def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=15_000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=20_000)

def goto_payments_done(page):
    page.click("text=Reports")
    page.wait_for_timeout(200)
    for label in ["Payments done", "Payments Done", "Pagamenti effettuati", "Pagamenti eseguiti", "Pagamenti"]:
        try:
            page.click(f"text={label}", timeout=1_200)
            page.wait_for_timeout(150)
            return
        except Exception:
            pass
    for sel in ["#ctl00_cphMain_lnkPaymentsDone", "#ctl00_cphMain_lnkPagamentiEffettuati"]:
        try:
            if page.locator(sel).count():
                page.locator(sel).first.click()
                page.wait_for_timeout(150)
                return
        except Exception:
            pass
    raise RuntimeError("Payments done link not found under Reports")

# Detect we are on printable/export page
def _is_printable_report(page) -> bool:
    try:
        if page.locator("table.main").count() > 0:
            return True
        url = (page.url or "").lower()
        return ("report_pagament" in url) or ("report_paymentsdone" in url)
    except Exception:
        return False

# ---------------- Async delta capture (UpdatePanel) ----------------

PANEL_ID = "ctl00_cphMain_upnlMain"

def _extract_panel_html_from_delta(payload: str, panel_id: str) -> Optional[str]:
    if not payload:
        return None
    try:
        parts = payload.split("|")
        for i in range(len(parts) - 2):
            if parts[i] == "updatePanel" and parts[i + 1] == panel_id:
                return parts[i + 2]
    except Exception:
        pass
    return None

def _install_delta_listener(page, store: dict):
    def _on_response(resp):
        try:
            ctype = (resp.headers or {}).get("content-type", "")
        except Exception:
            ctype = ""
        if "text/plain" in ctype:  # MS AJAX delta
            try:
                body = resp.text()
                html = _extract_panel_html_from_delta(body, PANEL_ID)
                if html:
                    store["panel_html"] = html
            except Exception:
                pass
    try:
        page.on("response", _on_response)
    except Exception:
        pass

# ---------------- Waits ----------------

def _wait_report_ready(page, timeout_ms: int = 30000, min_rows: int = 6):
    try:
        page.wait_for_function(
            """
            (minRows) => {
              const exp1 = document.querySelector('#ctl00_cphMain_hlyDownloadHTML');
              const exp2 = document.querySelector('#ctl00_cphMain_hlyDownloadHtml');
              if (exp1 || exp2) return true;

              const main = document.querySelector('table.main');
              if (main) {
                const rows = main.querySelectorAll('tr').length;
                if (rows >= minRows) return true;
              }

              const pnl = document.querySelector('#ctl00_cphMain_upnlMain');
              if (pnl) {
                const t = pnl.querySelector('table');
                if (t) {
                  const rows = t.querySelectorAll('tr').length;
                  if (rows >= minRows) return true;
                }
              }

              const tot = document.querySelector('#lblGranTotale');
              if (tot && (tot.textContent || '').trim().length > 0) return true;

              return false;
            }
            """,
            arg=(min_rows,),
            timeout=timeout_ms
        )
    except Exception:
        pass

# ---------------- Parsing & Cleanup ----------------

def _normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rename = {}
    for c in list(df.columns):
        lc = str(c).strip().lower()
        if lc in ("last", "last name", "surname", "cognome"):
            rename[c] = "Last name"
        elif lc in ("first", "first name", "name", "nome"):
            rename[c] = "First name"
        elif "expected" in lc or "previsto" in lc:
            rename[c] = "Expected"
        elif "cash" in lc or "incass" in lc:
            rename[c] = "Cash In"
        elif "instal" in lc or "install" in lc or "rata" in lc:
            rename[c] = "Instalment"
        elif lc.startswith("ammount") or lc == "amount" or lc == "importo":
            rename[c] = "Amount"
    if rename:
        df = df.rename(columns=rename)
    return df

def _clean_payments_done_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Last name","First name","Expected","Cash In","Instalment","Amount","TxnDate"])

    # Standardize headers first
    df = _normalize_headers(df)

    # Ensure expected columns exist
    expected = ["Last name", "First name", "Expected", "Cash In", "Instalment", "Amount"]
    for c in expected:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[expected].copy()

    # Drop title/repeated header rows
    rowtxt = df.astype(str).agg(" ".join, axis=1).str.lower()
    mask_title  = rowtxt.str.contains(r"payments done .* total am", na=False)
    mask_header = (
        df["Last name"].astype(str).str.strip().str.lower().eq("last") &
        df["First name"].astype(str).str.strip().str.lower().eq("first")
    )
    df = df[~(mask_title | mask_header)].copy()

    # Drop empty-name rows
    ln = df["Last name"].astype(str).str.strip().str.lower()
    fn = df["First name"].astype(str).str.strip().str.lower()
    df = df[~((ln.eq("") | ln.eq("nan")) & (fn.eq("") | fn.eq("nan")))].copy()

    # Types
    df["Instalment"] = pd.to_numeric(df["Instalment"], errors="coerce").astype("Int64")

    df["Amount"] = (
        df["Amount"].astype(str)
        .str.replace(r"[^\d\-\.,]", "", regex=True)
        .str.replace(",", "", regex=False)
    )
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)

    # Dates: try both dayfirst and monthfirst; keep as ISO strings
    def _dual_parse(series: pd.Series) -> pd.Series:
        d1 = pd.to_datetime(series, dayfirst=True, errors="coerce")
        d2 = pd.to_datetime(series, dayfirst=False, errors="coerce")
        d  = d2.fillna(d1)  # prefer MM/DD when both possible (matches portal sample)
        return d.dt.strftime("%Y-%m-%d")

    for dcol in ("Expected", "Cash In"):
        df[dcol] = _dual_parse(df[dcol])

    # Stable transaction date for PK
    df["TxnDate"] = df["Cash In"].fillna("").replace("NaT", "")
    mask = (df["TxnDate"].isna()) | (df["TxnDate"] == "")
    df.loc[mask, "TxnDate"] = df.loc[mask, "Expected"]

    return df.reset_index(drop=True)

def _canon_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    df.columns = [("" if c is None else str(c).strip()) for c in df.columns]
    # final column order if available
    ordered = [c for c in ["Last name","First name","Expected","Cash In","Instalment","Amount","TxnDate"] if c in df.columns]
    if ordered:
        df = df[ordered]
    # drop duplicate columns (keep first)
    df = df.loc[:, ~pd.Index(df.columns).duplicated()]
    return df

def _pick_report_table(tables: List[pd.DataFrame]) -> pd.DataFrame:
    if not tables:
        return pd.DataFrame()
    def _score(d: pd.DataFrame) -> int:
        r, c = d.shape
        return (r or 0) * (c or 0)
    # prefer one that looks like it has names
    def looks_like(d: pd.DataFrame) -> bool:
        if d is None or d.empty: return False
        cols = [str(x).strip().lower() for x in d.columns]
        if {"last","first"}.issubset(set(cols)): return True
        first = [str(x).strip().lower() for x in (list(d.iloc[0]) if len(d) else [])]
        return {"last","first"}.issubset(set(first))
    candidates = [t for t in tables if looks_like(t)]
    if candidates:
        return max(candidates, key=_score).copy()
    return max(tables, key=_score).copy()

def _parse_payments_done_html(html: str) -> pd.DataFrame:
    # ✅ Try BS4 FIRST (pandas was yielding NaNs for Jan)
    df = _parse_payments_done_html_bs4(html)
    if isinstance(df, pd.DataFrame) and not df.empty and df.notna().sum().sum() > 0:
        return df

    # Fallback to pandas.read_html if BS4 failed
    from io import StringIO
    try:
        tables = pd.read_html(StringIO(html))
    except Exception:
        tables = []

    if not tables:
        return pd.DataFrame()

    df = _pick_report_table(tables)

    # Promote first row to header if it looks like headers
    if len(df) > 0:
        first = [str(x).strip().lower() for x in df.iloc[0].tolist()]
        if {"last","first"}.issubset(set(first)) or any(k in first for k in ("expected","cash in","ammount","amount","instalment")):
            df.columns = [str(x).strip() for x in df.iloc[0]]
            df = df.iloc[1:].reset_index(drop=True)

    df = _normalize_headers(df)
    if "Amount" in df.columns:
        def _money(x):
            s = "" if pd.isna(x) else str(x).strip()
            s = re.sub(r"[^\d\-\.,]", "", s).replace(",", "")
            return float(s) if s not in ("", "-", None) else 0.0
        df["Amount"] = df["Amount"].map(_money)

    df = _clean_payments_done_df(df)
    df = _canon_df(df)


    return df



# ---------------- Core scrape (single window) ----------------

def scrape_payments_done_chunk(ctx_page, from_date: str, to_date: str) -> pd.DataFrame:
    page = ctx_page["page"]
    ctx  = ctx_page["ctx"]

    goto_payments_done(page)

    delta_store = {"panel_html": None}
    _install_delta_listener(page, delta_store)

    # set dates
    page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
    page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel",  to_date)

    # click Run / Visualize
    clicked = False
    try:
        page.click("text=Do Report"); clicked = True
    except Exception:
        for label in ["Generate", "Visualizza", "Esegui", "Mostra", "Report"]:
            try:
                page.click(f"text={label}", timeout=1_200); clicked = True; break
            except Exception:
                pass
        if not clicked:
            for sel in ["#ctl00_cphMain_btnPagamentiFatti", "#ctl00_cphMain_btnEsegui", "#ctl00_cphMain_btnVisualizza"]:
                try:
                    page.click(sel, timeout=1_200); clicked = True; break
                except Exception:
                    pass
    if not clicked:
        raise RuntimeError("Could not trigger the Payments Done report run")

    # wait for result signal
    try:
        page.wait_for_selector(
            "#ctl00_cphMain_hlyDownloadHTML, #ctl00_cphMain_hlyDownloadHtml, table.main, #ctl00_cphMain_upnlMain table",
            timeout=20_000
        )
    except Exception:
        pass
    _wait_report_ready(page, timeout_ms=35000, min_rows=6)

    # 1) Printable/export page in same tab
    if _is_printable_report(page):
        html = page.content()
        try: archive_text("payments_done", html, tag=f"printable_{from_date}_to_{to_date}", ext="html")
        except Exception: pass
        df = _parse_payments_done_html(html)
        if (df.empty or len(df) < 6) and delta_store.get("panel_html"):
            html_panel = delta_store["panel_html"]
            try: archive_text("payments_done", html_panel, tag=f"delta_{from_date}_to_{to_date}", ext="html")
            except Exception: pass
            df2 = _parse_payments_done_html(html_panel)
            if not df2.empty and len(df2) >= 6:
                df = df2
        if not df.empty:
            try: archive_df("payments_done", df, tag=f"{from_date}_to_{to_date}")
            except Exception: pass
        return df

    # 2) Separate export link
    href = None
    for sel in ["#ctl00_cphMain_hlyDownloadHTML", "#ctl00_cphMain_hlyDownloadHtml"]:
        try:
            if page.locator(sel).count():
                href = page.get_attribute(sel, "href")
                if href: break
        except Exception:
            pass

    def _resolve_export_url(href: str) -> str:
        if not href: return ""
        href = href.strip()
        if href.startswith("http://") or href.startswith("https://"):
            return href
        if href.startswith("/"):
            return f"https://newton.hosting.memetic.it{href}"
        if href.lower().startswith("report_"):
            return f"https://newton.hosting.memetic.it/assist/{href}"
        return f"https://newton.hosting.memetic.it/{href}"

    if href:
        url = _resolve_export_url(href)
        rpage = ctx.new_page()
        rpage.goto(url)
        try: rpage.wait_for_selector("table.main", timeout=15_000)
        except Exception: pass
        _wait_report_ready(rpage, timeout_ms=25000, min_rows=6)
        html = rpage.content()
        try: archive_text("payments_done", html, tag=f"export_{from_date}_to_{to_date}", ext="html")
        except Exception: pass
        df = _parse_payments_done_html(html)
        if (df.empty or len(df) < 6) and delta_store.get("panel_html"):
            html_panel = delta_store["panel_html"]
            try: archive_text("payments_done", html_panel, tag=f"delta_{from_date}_to_{to_date}", ext="html")
            except Exception: pass
            df2 = _parse_payments_done_html(html_panel)
            if not df2.empty and len(df2) >= 6:
                df = df2
        rpage.close()
        if not df.empty:
            try: archive_df("payments_done", df, tag=f"{from_date}_to_{to_date}")
            except Exception: pass
        return df

    # 3) Fallback: current DOM
    html = page.content()
    try: archive_text("payments_done", html, tag=f"inline_{from_date}_to_{to_date}", ext="html")
    except Exception: pass
    df = _parse_payments_done_html(html)
    if (df.empty or len(df) < 6) and delta_store.get("panel_html"):
        html_panel = delta_store["panel_html"]
        try: archive_text("payments_done", html_panel, tag=f"delta_{from_date}_to_{to_date}", ext="html")
        except Exception: pass
        df2 = _parse_payments_done_html(html_panel)
        if not df2.empty and len(df2) >= 6:
            df = df2
    if not df.empty:
        try: archive_df("payments_done", df, tag=f"{from_date}_to_{to_date}")
        except Exception: pass
    return df


def _parse_payments_done_html_bs4(html: str) -> pd.DataFrame:
    if not html:
        return pd.DataFrame()

    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.main")
    if not table:
        return pd.DataFrame()

    # Find the header row (cells with class "titoli") — expect exactly 6 headers
    header_cells = table.select("tr > td.titoli")
    if len(header_cells) == 6:
        header = [td.get_text(strip=True) for td in header_cells]
    else:
        # Fallback: fixed headers matching the portal order
        header = ["Last", "First", "Expected", "Cash In", "Instalment", "Ammount"]

    # Collect data rows: each row should have 6 <td class="righe">
    data = []
    for tr in table.select("tr"):
        tds = tr.select("td.righe")
        if len(tds) != 6:
            continue
        vals = [td.get_text(strip=True) for td in tds]
        if not any(vals):
            continue
        data.append(vals)

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=header)

    # Normalize headers and clean
    df = _normalize_headers(df)       # maps Last/First/Ammount → Last name/First name/Amount
    df = _clean_payments_done_df(df)  # types, dates → ISO, TxnDate, etc.
    df = _canon_df(df)
    return df




# ---------------- Runners ----------------

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
            print(f"→ Payments Done window {frm} → {to}", flush=True)
            try:
                df_win = scrape_payments_done_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[Payments Done] window {frm} → {to} error: {e}", flush=True)
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
            print(f"→ Payments Done backfill window {frm} → {to}", flush=True)
            try:
                df_win = scrape_payments_done_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[Payments Done] backfill window {frm} → {to} error: {e}", flush=True)
                continue
            if not df_win.empty:
                frames.append(df_win)
        browser.close()
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# ---------------- PK inference ----------------

def _infer_pk(df: pd.DataFrame) -> List[str]:
    cols = []
    for c in ("Last name", "First name", "TxnDate", "Instalment", "Amount"):
        if c in df.columns:
            cols.append(c)
    if cols:
        return cols
    return [str(df.columns[0])]

# ---------------- CLI ----------------

def _month_window_daily() -> Tuple[str, str]:
    today = datetime.today()
    start = today - relativedelta(months=6)
    end   = today + relativedelta(months=6)
    return fmt_mmddyyyy(start), fmt_mmddyyyy(end)

def _run_one_window_subprocess(frm: str, to: str, timeout_s: int = 180) -> int:
    cmd = [sys.executable, "-u", "-m", "app.common.scrape_payments_done", frm, to]
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", os.getcwd())
    print(f"   -> app.common.scrape_payments_done  {frm}  →  {to}", flush=True)
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

    # --dump-only flag
    if len(sys.argv) >= 2 and sys.argv[-1] == "--dump-only":
        DUMP_ONLY = True
        sys.argv = sys.argv[:-1]

    # Backfill Jan 1, 2025 → today
    if len(sys.argv) == 2 and sys.argv[1] == "--backfill-2025":
        start_dt = datetime(2025, 1, 1)
        end_dt   = datetime.today()
        print(f"⏱️  Backfilling Payments Done from {start_dt:%m/%d/%Y} to {end_dt:%m/%d/%Y}…", flush=True)
        df = run_backfill_fixed(start_dt, end_dt, chunk_max=12, overlap=2)
        if df.empty:
            print("⚠️ No data scraped.", flush=True); return
        df = _canon_df(df)
        if DUMP_ONLY:
            try: archive_df("payments_done_debug", df, tag="backfill_2025")
            except Exception: pass
            print(f"[dump-only] rows={len(df)} cols={list(df.columns)}")
            print(df.head(10).to_string(index=False)); return
        pk_cols = _infer_pk(df)
        added = merge_into_history("payments_done", df, pk_cols=pk_cols)
        print(f"✅ Payments Done BACKFILL merged. New/updated rows: {added}", flush=True)
        return

    # Manual single window
    if len(sys.argv) == 3:
        frm, to = sys.argv[1], sys.argv[2]
        print(f"⏱️  Scraping Payments Done (single window) {frm} → {to} …", flush=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx     = browser.new_context()
            page    = ctx.new_page()
            login(page)
            df = scrape_payments_done_chunk({"ctx": ctx, "page": page}, frm, to)
            browser.close()

        if df.empty:
            print("⚠️ No data scraped.", flush=True); return

        df = _canon_df(df)

        if DUMP_ONLY:
            try: archive_df("payments_done_debug", df, tag=f"{frm}_to_{to}")
            except Exception: pass
            print(f"[dump-only] rows={len(df)} cols={list(df.columns)}")
            print(df.head(10).to_string(index=False))
            return

        pk_cols = _infer_pk(df)
        added = merge_into_history("payments_done", df, pk_cols=pk_cols)
        print(f"✅ Payments Done merged. New/updated rows: {added}", flush=True)
        return

    # Default: daily refresh ±6 months in a subprocess with timeout guard
    print("⏱️  Scraping Payments Done (±6 months) via subprocess …", flush=True)
    frm, to = _month_window_daily()
    rc = _run_one_window_subprocess(frm, to, timeout_s=180)
    if rc != 0:
        print("⚠️ Payments Done daily window failed or timed out.", flush=True)

if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
