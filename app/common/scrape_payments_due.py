# app/common/scrape_payments_due.py

import os
import sys
import subprocess
import re
from datetime import datetime
from typing import List, Optional, Tuple
from io import StringIO

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

# ---------- Login & Nav ----------

def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=15_000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=20_000)

def goto_payments_due(page):
    page.click("text=Reports")
    page.wait_for_timeout(200)
    for label in ["Payments due", "Payments Due", "Pagamenti da pagare", "Pagamenti dovuti", "Pagamenti"]:
        try:
            page.click(f"text={label}", timeout=1200)
            page.wait_for_timeout(150)
            return
        except Exception:
            pass
    for sel in ["#ctl00_cphMain_lnkPaymentsDue", "#ctl00_cphMain_lnkPagamentiDaPagare"]:
        try:
            if page.locator(sel).count():
                page.locator(sel).first.click()
                page.wait_for_timeout(150)
                return
        except Exception:
            pass
    raise RuntimeError("Payments due link not found under Reports")

def _is_printable_report(page) -> bool:
    try:
        if page.locator("table.main").count() > 0:
            return True
        u = (page.url or "").lower()
        return ("report_pagamadapagare" in u) or ("report_paymentsdue" in u)
    except Exception:
        return False

# ---------- Async delta capture (UpdatePanel) ----------

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
        if "text/plain" in ctype:
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

def _wait_report_ready(page, timeout_ms: int = 30000):
    try:
        page.wait_for_function(
            """
            () => {
              const exp1 = document.querySelector('#ctl00_cphMain_hlyDownloadHTML');
              const exp2 = document.querySelector('#ctl00_cphMain_hlyDownloadHtml');
              if (exp1 || exp2) return true;
              const main = document.querySelector('table.main');
              if (main) {
                // ensure some 'titoli' or 'righe' cells exist
                if (main.querySelector('td.titoli, td.righe')) return true;
              }
              const tot = document.querySelector('#lblGranTotale');
              if (tot && (tot.textContent || '').trim().length > 0) return true;
              return false;
            }
            """,
            timeout=timeout_ms
        )
    except Exception:
        pass

# ---------- Parsing ----------

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

def _parse_payments_due_html_bs4(html: str) -> pd.DataFrame:
    if not html:
        return pd.DataFrame()

    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("table.main")
    if not main:
        return pd.DataFrame()

    rows = []

    # Find every inner payment row: a <tr> with >=2 <td class="righe"> and without a "totali" cell
    for pay_tr in main.select("table tr"):
        if pay_tr.find("td", class_="totali"):
            continue
        righe_cells = pay_tr.find_all("td", class_="righe")
        if len(righe_cells) < 2:
            continue

        # Extract date & amount
        date_txt   = righe_cells[0].get_text(strip=True)
        amount_txt = righe_cells[-1].get_text(strip=True)
        iso = _dual_date(date_txt)
        if not iso:
            continue

        # Nearest contract: look for the closest ancestor <td class="righe"> that contains "Contract:"
        contract_td = pay_tr.find_parent("td", class_="righe")
        contract_code = ""
        if contract_td:
            m = re.search(r"Contract\s*:\s*([A-Za-z0-9\-\._/]+)", contract_td.get_text(" ", strip=True), flags=re.I)
            if m:
                contract_code = m.group(1).strip()

        # Nearest client header above: <td class="titoli" colspan=...>
        client_td = None
        cursor = pay_tr
        while cursor and not client_td:
            cursor = cursor.find_previous("tr")
            if cursor:
                cand = cursor.find("td", class_="titoli")
                if cand and cand.has_attr("colspan"):
                    client_td = cand
                    break
        client_name = " ".join(client_td.get_text(" ", strip=True).split()) if client_td else ""

        rows.append({
            "Client":   client_name,
            "Contract": contract_code,
            "Date":     iso,
            "Amount":   _parse_money(amount_txt),
            "TxnDate":  iso,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Client"]   = df["Client"].astype(str).str.strip()
    df["Contract"] = df["Contract"].astype(str).str.strip()
    df["Amount"]   = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)
    return df[["Client", "Contract", "Date", "Amount", "TxnDate"]]

# keep this wrapper so callers work:
def _parse_payments_due_html(html: str) -> pd.DataFrame:
    return _parse_payments_due_html_bs4(html)



def _parse_payments_due_html(html: str) -> pd.DataFrame:
    """Thin wrapper so callers can use a consistent name."""
    return _parse_payments_due_html_bs4(html)

# ---------- Single-window scrape ----------

def scrape_payments_due_chunk(ctx_page, from_date: str, to_date: str) -> pd.DataFrame:
    page = ctx_page["page"]
    ctx  = ctx_page["ctx"]

    goto_payments_due(page)

    delta_store = {"panel_html": None}
    _install_delta_listener(page, delta_store)

    # set dates
    page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
    page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel",  to_date)

    # click run
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
            for sel in ["#ctl00_cphMain_btnPagamentiDaPagare", "#ctl00_cphMain_btnEsegui", "#ctl00_cphMain_btnVisualizza"]:
                try:
                    page.click(sel, timeout=1200); clicked = True; break
                except Exception:
                    pass
    if not clicked:
        raise RuntimeError("Could not trigger Payments due run")

    # wait for ready
    try:
        page.wait_for_selector(
            "#ctl00_cphMain_hlyDownloadHTML, #ctl00_cphMain_hlyDownloadHtml, table.main, #ctl00_cphMain_upnlMain table",
            timeout=20_000
        )
    except Exception:
        pass
    _wait_report_ready(page, timeout_ms=35000)

    # path 1: printable in same tab
    if _is_printable_report(page):
        html = page.content()
        try: archive_text("payments_due", html, tag=f"printable_{from_date}_to_{to_date}", ext="html")
        except Exception: pass
        df = _parse_payments_due_html(html)
        print(f"[DEBUG] due rows parsed: {len(df)}")
        if (df.empty or len(df) < 1) and delta_store.get("panel_html"):
            html_panel = delta_store["panel_html"]
            try: archive_text("payments_due", html_panel, tag=f"delta_{from_date}_to_{to_date}", ext="html")
            except Exception: pass
            df2 = _parse_payments_due_html(html_panel)
            if not df2.empty:
                df = df2
        if not df.empty:
            try: archive_df("payments_due", df, tag=f"{from_date}_to_{to_date}")
            except Exception: pass
        return df

    # path 2: export link
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
        _wait_report_ready(rpage, timeout_ms=25000)
        html = rpage.content()
        try: archive_text("payments_due", html, tag=f"export_{from_date}_to_{to_date}", ext="html")
        except Exception: pass
        df = _parse_payments_due_html(html)
        if (df.empty or len(df) < 1) and delta_store.get("panel_html"):
            html_panel = delta_store["panel_html"]
            try: archive_text("payments_due", html_panel, tag=f"delta_{from_date}_to_{to_date}", ext="html")
            except Exception: pass
            df2 = _parse_payments_due_html(html_panel)
            if not df2.empty:
                df = df2
        rpage.close()
        if not df.empty:
            try: archive_df("payments_due", df, tag=f"{from_date}_to_{to_date}")
            except Exception: pass
        return df

    # path 3: fallback current DOM
    html = page.content()
    try: archive_text("payments_due", html, tag=f"inline_{from_date}_to_{to_date}", ext="html")
    except Exception: pass
    df = _parse_payments_due_html(html)
    if (df.empty or len(df) < 1) and delta_store.get("panel_html"):
        html_panel = delta_store["panel_html"]
        try: archive_text("payments_due", html_panel, tag=f"delta_{from_date}_to_{to_date}", ext="html")
        except Exception: pass
        df2 = _parse_payments_due_html(html_panel)
        if not df2.empty:
            df = df2
    if not df.empty:
        try: archive_df("payments_due", df, tag=f"{from_date}_to_{to_date}")
        except Exception: pass
    return df

# ---------- Runners ----------

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
            print(f"→ Payments Due window {frm} → {to}", flush=True)
            try:
                df_win = scrape_payments_due_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[Payments Due] window {frm} → {to} error: {e}", flush=True)
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
            print(f"→ Payments Due backfill window {frm} → {to}", flush=True)
            try:
                df_win = scrape_payments_due_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[Payments Due] backfill window {frm} → {to} error: {e}", flush=True)
                continue
            if not df_win.empty:
                frames.append(df_win)
        browser.close()
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# ---------- PK & CLI ----------

def _infer_pk(df: pd.DataFrame) -> List[str]:
    # a single client may have many contracts and dates
    cols = []
    for c in ("Client", "Contract", "TxnDate", "Amount"):
        if c in df.columns:
            cols.append(c)
    return cols or [str(df.columns[0])]

def _month_window_daily() -> Tuple[str, str]:
    today = datetime.today()
    start = today - relativedelta(months=6)
    end   = today + relativedelta(months=6)
    return fmt_mmddyyyy(start), fmt_mmddyyyy(end)

def _run_one_window_subprocess(frm: str, to: str, timeout_s: int = 180) -> int:
    cmd = [sys.executable, "-u", "-m", "app.common.scrape_payments_due", frm, to]
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", os.getcwd())
    print(f"   -> app.common.scrape_payments_due  {frm}  →  {to}", flush=True)
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

    # backfill example flag (optional)
    if len(sys.argv) == 2 and sys.argv[1] == "--backfill-2025":
        start_dt = datetime(2025, 1, 1)
        end_dt   = datetime.today()
        print(f"⏱️  Backfilling Payments Due from {start_dt:%m/%d/%Y} to {end_dt:%m/%d/%Y}…", flush=True)
        df = run_backfill_fixed(start_dt, end_dt, chunk_max=12, overlap=2)
        if df.empty:
            print("⚠️ No data scraped.", flush=True); return
        if DUMP_ONLY:
            try: archive_df("payments_due_debug", df, tag="backfill_2025")
            except Exception: pass
            print(f"[dump-only] rows={len(df)} cols={list(df.columns)}")
            print(df.head(10).to_string(index=False)); return
        pk_cols = _infer_pk(df)
        added = merge_into_history("payments_due", df, pk_cols=pk_cols)
        print(f"✅ Payments Due BACKFILL merged. New/updated rows: {added}", flush=True)
        return

    # manual single window
    if len(sys.argv) == 3:
        frm, to = sys.argv[1], sys.argv[2]
        print(f"⏱️  Scraping Payments Due (single window) {frm} → {to} …", flush=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx     = browser.new_context()
            page    = ctx.new_page()
            login(page)
            df = scrape_payments_due_chunk({"ctx": ctx, "page": page}, frm, to)
            browser.close()

        if df.empty:
            print("⚠️ No data scraped.", flush=True); return

        if DUMP_ONLY:
            try: archive_df("payments_due_debug", df, tag=f"{frm}_to_{to}")
            except Exception: pass
            print(f"[dump-only] rows={len(df)} cols={list(df.columns)}")
            print(df.head(10).to_string(index=False))
            return

        pk_cols = _infer_pk(df)
        added = merge_into_history("payments_due", df, pk_cols=pk_cols)
        print(f"✅ Payments Due merged. New/updated rows: {added}", flush=True)
        return

    # default daily refresh (±6m in a subprocess with timeout guard)
    print("⏱️  Scraping Payments Due (±6 months) via subprocess …", flush=True)
    frm, to = _month_window_daily()
    rc = _run_one_window_subprocess(frm, to, timeout_s=180)
    if rc != 0:
        print("⚠️ Payments Due daily window failed or timed out.", flush=True)

if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
