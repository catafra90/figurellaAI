# app/common/scrape_customer_acquisitions.py
import os
import sys
import subprocess
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import pandas as pd
from dateutil.relativedelta import relativedelta
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re

from app.common.cleaners import drop_unwanted_rows
from app.common.utils_merge import merge_into_history
from app.common.utils_raw import archive_text, archive_df
from app.common.utils_dates import build_month_windows, fmt_mmddyyyy, month_windows

BASE      = "https://newton.hosting.memetic.it"
LOGIN_URL = f"{BASE}/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"

# ---------- login & navigation ----------

def login(page):
    print("[ACQ] navigating to login…", flush=True)
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=10_000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=15_000)
    print("[ACQ] logged in; Reports tab found.", flush=True)

def goto_customer_acq(page):
    page.click("text=Reports"); page.wait_for_timeout(250)
    for label in ["Customer Acquisition", "Customer acquisition", "Acquisizione Clienti", "Acquisizioni clienti"]:
        try:
            page.click(f"text={label}", timeout=1_500)
            page.wait_for_timeout(250)
            print(f"[ACQ] opened Reports → {label}", flush=True)
            return
        except Exception:
            continue
    print("[ACQ] WARN: Could not open Customer Acquisition from Reports.", flush=True)

# ---------- parsing ----------

_ID_RE = re.compile(r"\bID:\s*(\d+)", re.I)

def _dual_date(text: str) -> str:
    if not text: return ""
    d1 = pd.to_datetime(text, dayfirst=False, errors="coerce")
    if pd.notna(d1): return d1.date().isoformat()
    d2 = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.notna(d2): return d2.date().isoformat()
    return ""

def _parse_customer_acq_table_html(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.main") or soup.select_one("div#C table") or soup.select_one("table")
    if not table:
        return pd.DataFrame()

    hdr_tr = None
    for tr in table.find_all("tr"):
        if tr.find(["td", "th"], class_=re.compile(r"\btitoli\b", re.I)):
            hdr_tr = tr
            break
    if hdr_tr is None:
        return pd.DataFrame()

    headers = []
    for cell in hdr_tr.find_all(["td", "th"]):
        txt = " ".join(cell.get_text(" ", strip=True).split())
        headers.append(txt)
    lowers = [h.strip().lower() for h in headers]

    def _idx_of(*names):
        for name in names:
            n = name.strip().lower()
            if n in lowers:
                return lowers.index(n)
        return -1

    idx_name   = _idx_of("name", "cognome nome", "cliente", "nominativo")
    idx_email  = _idx_of("email", "e-mail", "mail")
    idx_phone  = _idx_of("phone", "telefono", "cellulare", "cell")
    idx_birth  = _idx_of("birth date", "data di nascita", "nascita", "birth")
    idx_acq    = _idx_of("acquisition date", "data acquisizione", "acquisition")
    idx_status = _idx_of("status", "stato")
    idx_firstc = _idx_of("first contract", "primo contratto", "first contract date")

    rows_out = []
    for tr in hdr_tr.find_all_next("tr"):
        if tr.find(["td", "th"], class_=re.compile(r"\btitoli\b", re.I)):
            continue
        tds = tr.find_all("td", class_=re.compile(r"\brighe\b", re.I)) or tr.find_all("td")
        if not tds:
            continue
        if idx_name == -1 or idx_name >= len(tds):
            continue

        name_cell = tds[idx_name]
        title_attr = (name_cell.get("title") or "")
        m = _ID_RE.search(title_attr)
        lead_id = m.group(1) if m else ""

        name_parts = [p.strip() for p in name_cell.stripped_strings if p.strip()]
        full_name  = " ".join(name_parts)
        if len(name_parts) >= 2:
            last_name  = name_parts[0]
            first_name = " ".join(name_parts[1:])
        elif len(name_parts) == 1:
            last_name, first_name = name_parts[0], ""
        else:
            last_name, first_name = "", ""

        def val_at(idx):
            if idx == -1 or idx >= len(tds):
                return ""
            return tds[idx].get_text(" ", strip=True)

        email   = val_at(idx_email)
        phone   = re.sub(r"[^\d+]", "", val_at(idx_phone))
        birth   = _dual_date(val_at(idx_birth))
        acq     = _dual_date(val_at(idx_acq))
        status  = val_at(idx_status)
        first_c = _dual_date(val_at(idx_firstc))

        if not full_name and not acq:
            continue

        rows_out.append({
            "LeadID":            lead_id,
            "Name":              full_name,
            "Last name":         last_name,
            "First name":        first_name,
            "Email":             email,
            "Phone":             phone,
            "Birth date":        birth,
            "Acquisition date":  acq,
            "Status":            status,
            "First Contract":    first_c,
        })

    df = pd.DataFrame(rows_out)
    if df.empty:
        return df
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass
    df = df.loc[:, ~df.columns.duplicated()]
    return df

# ---------- listener helper ----------

def _bind_response_sniffer(context, handler):
    context.on("response", handler)
    def unbind():
        try:
            context.remove_listener("response", handler)
        except Exception:
            pass
    return unbind

# ---------- link discovery helpers ----------

def _abs_report_href(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    try:
        return urljoin(BASE.rstrip("/") + "/", href)
    except Exception:
        return None

def _find_report_url(page) -> Optional[str]:
    # 1) Any anchor with the report path
    try:
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
        for h in hrefs or []:
            if h and "report_acquisizioniclienti" in h.lower():
                u = _abs_report_href(h)
                if u:
                    return u
    except Exception:
        pass
    # 2) Known id pattern
    try:
        for sel in ["#ctl00_cphMain_hlyDownloadHTML", "[id$='hlyDownloadHTML']"]:
            if page.locator(sel).count():
                h = page.get_attribute(sel, "href")
                if h and "report_acquisizioniclienti" in (h or "").lower():
                    u = _abs_report_href(h)
                    if u:
                        return u
    except Exception:
        pass
    # 3) Buttons that look like download
    try:
        cand = page.locator("a:has-text('Download'), a:has-text('Scarica')")
        for i in range(cand.count()):
            h = cand.nth(i).get_attribute("href")
            if h and "report_acquisizioniclienti" in h.lower():
                u = _abs_report_href(h)
                if u:
                    return u
    except Exception:
        pass
    return None

# ---------- direct URL fallback ----------

def _mmddyyyy_to_tuple(s: str) -> Optional[Tuple[int,int,int]]:
    try:
        d = datetime.strptime(s.strip(), "%m/%d/%Y")
        return d.month, d.day, d.year
    except Exception:
        # try other common delimiters
        try:
            d = pd.to_datetime(s, errors="coerce")
            if pd.notna(d):
                return int(d.month), int(d.day), int(d.year)
        except Exception:
            pass
    return None

def _build_direct_report_url(from_date: str, to_date: str) -> Optional[str]:
    f = _mmddyyyy_to_tuple(from_date)
    t = _mmddyyyy_to_tuple(to_date)
    if not f or not t:
        return None
    fm, fd, fy = f
    tm, td, ty = t
    # /assist/report_acquisizioniclienti?CLIENT_ID=0&fromgg=DD&frommm=MM&fromaa=YYYY&togg=DD&tomm=MM&toaa=YYYY
    return (
        f"{BASE}/assist/report_acquisizioniclienti"
        f"?CLIENT_ID=0&fromgg={fd}&frommm={fm}&fromaa={fy}&togg={td}&tomm={tm}&toaa={ty}"
    )

# ---------- single-window scrape (UI path) ----------

def scrape_customer_acq_chunk(ctx_page, from_date: str, to_date: str) -> pd.DataFrame:
    page = ctx_page["page"]
    ctx  = ctx_page["ctx"]

    goto_customer_acq(page)

    print(f"[ACQ] filling dates: {from_date} → {to_date}", flush=True)
    page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
    page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel",  to_date)

    report_urls: List[str] = []
    def _resp_sniffer(resp):
        url = (resp.url or "").lower()
        if "report_acquisizioniclienti" in url:
            report_urls.append(resp.url)

    unbind = _bind_response_sniffer(ctx, _resp_sniffer)
    try:
        clicked = False
        candidates = [
            "#ctl00_cphMain_btnAcquisizioneClienti",
            "text=Do Report", "text=Create Report", "text=Visualizza",
            "text=Esegui", "text=Mostra", "text=Report"
        ]
        for sel in candidates:
            try:
                page.click(sel, timeout=2_000)
                print(f"[ACQ] clicked report trigger: {sel}", flush=True)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            print("[ACQ] ERROR: Could not click any report trigger.", flush=True)
            return pd.DataFrame()

        # Wait a bit for postback/updatepanel
        page.wait_for_load_state("networkidle", timeout=8_000)
        # Archive post-click page for debugging
        try:
            archive_text("customer_acquisitions", page.content(),
                         tag=f"{from_date}_to_{to_date}_postclick", ext="html")
        except Exception:
            pass

        # Try to find href or inline table (main page)
        url = _find_report_url(page)
        if url:
            print(f"[ACQ] _find_report_url → {url}", flush=True)
        else:
            if report_urls:
                url = report_urls[-1]
                print(f"[ACQ] using sniffed URL → {url}", flush=True)
            else:
                # Inline table in main page?
                if page.locator("div#C table.main, table.main").count():
                    print("[ACQ] found inline table in main page → parsing inline.", flush=True)
                    html_inline = page.content()
                    try:
                        archive_text("customer_acquisitions", html_inline,
                                     tag=f"{from_date}_to_{to_date}_inline", ext="html")
                    except Exception:
                        pass
                    return _parse_customer_acq_table_html(html_inline)
                # Inline table in any iframe?
                for fr in page.frames:
                    try:
                        if fr.locator("div#C table.main, table.main").count():
                            print(f"[ACQ] found inline table in frame '{fr.name or '(no-name)'}' → parsing.", flush=True)
                            html_iframe = fr.content()
                            try:
                                archive_text("customer_acquisitions", html_iframe,
                                             tag=f"{from_date}_to_{to_date}_inline_frame", ext="html")
                            except Exception:
                                pass
                            return _parse_customer_acq_table_html(html_iframe)
                    except Exception:
                        continue

        # If still nothing, try direct URL fallback
        if not url:
            url = _build_direct_report_url(from_date, to_date)
            print(f"[ACQ] direct URL fallback → {url}", flush=True)

    finally:
        unbind()

    if not url:
        print("[ACQ] ERROR: No printable URL and no inline table found; skipping window.", flush=True)
        return pd.DataFrame()

    print(f"[ACQ] opening printable URL: {url}", flush=True)
    rpage = ctx.new_page()
    rpage.goto(url)
    rpage.wait_for_load_state("domcontentloaded")
    try:
        rpage.wait_for_selector("table", timeout=15_000)
    except Exception:
        pass

    html = rpage.content()
    try:
        archive_text("customer_acquisitions", html,
                     tag=f"{from_date}_to_{to_date}_printable", ext="html")
    except Exception:
        pass

    df = _parse_customer_acq_table_html(html)
    rpage.close()

    if not df.empty:
        try:
            archive_df("customer_acquisitions", df, tag=f"{from_date}_to_{to_date}")
        except Exception:
            pass
    return df

# ---------- multi-window runners (visible for debugging) ----------

def run_scrape_windows(months_back=6, months_forward=6, *, chunk_max=12, overlap=2) -> pd.DataFrame:
    windows = build_month_windows(months_back, months_forward, chunk_max=chunk_max, overlap=overlap)
    frames: List[pd.DataFrame] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        ctx     = browser.new_context()
        page    = ctx.new_page()
        login(page)

        for (start_dt, end_dt) in windows:
            frm, to = fmt_mmddyyyy(start_dt), fmt_mmddyyyy(end_dt)
            print(f"→ Customer Acquisition window {frm} → {to}", flush=True)
            try:
                df_win = scrape_customer_acq_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[ACQ] window {frm} → {to} error: {e}", flush=True)
                continue
            if not df_win.empty:
                frames.append(df_win)

        browser.close()

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates()

def run_backfill_fixed(start_dt: datetime, end_dt: datetime, *, chunk_max=12, overlap=2) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        ctx     = browser.new_context()
        page    = ctx.new_page()
        login(page)

        for frm, to in month_windows(start_dt, end_dt, chunk_max=chunk_max, overlap=overlap):
            print(f"→ Customer Acquisition backfill window {frm} → {to}", flush=True)
            try:
                df_win = scrape_customer_acq_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[ACQ] backfill window {frm} → {to} error: {e}", flush=True)
                continue
            if not df_win.empty:
                frames.append(df_win)

        browser.close()

    return pd.concat(frames, ignore_index=True).drop_duplicates() if frames else pd.DataFrame()

# ---------- daily run ----------

def _month_window_daily():
    today = datetime.today()
    start = today - relativedelta(months=6)
    end   = today + relativedelta(months=6)
    return fmt_mmddyyyy(start), fmt_mmddyyyy(end)

def _run_one_window_subprocess(frm: str, to: str, timeout_s: int = 180) -> int:
    cmd = [sys.executable, "-u", "-m", "app.common.scrape_customer_acquisitions", frm, to]
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONPATH", os.getcwd())
    print(f"   -> app.common.scrape_customer_acquisitions  {frm}  →  {to}", flush=True)
    try:
        res = subprocess.run(cmd, env=env, timeout=timeout_s)
        print(f"   <- exit {res.returncode} for {frm} → {to}", flush=True)
        return res.returncode
    except subprocess.TimeoutExpired:
        print(f"   !! window {frm} → {to} timed out after {timeout_s}s; skipping.", flush=True)
        return 124

# ---------- PK inference ----------

def _infer_pk(df: pd.DataFrame) -> List[str]:
    cols = [c for c in ("LeadID", "Acquisition date") if c in df.columns]
    if cols:
        return cols
    base = [c for c in ("Last name","First name","Acquisition date") if c in df.columns]
    return base or [str(df.columns[0])]

# ---------- CLI ----------

def get_date_range(months_back: int = 6, months_forward: int = 6):
    today = datetime.today()
    return (
        (today - relativedelta(months=months_back)).strftime("%m/%d/%Y"),
        (today + relativedelta(months=months_forward)).strftime("%m/%d/%Y"),
    )

def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--backfill-2025":
        start_dt = datetime(2025, 1, 1)
        end_dt   = datetime.today()
        print(f"⏱️  Backfilling Customer Acquisition from {start_dt:%m/%d/%Y} to {end_dt:%m/%d/%Y}…", flush=True)
        df = run_backfill_fixed(start_dt, end_dt, chunk_max=12, overlap=2)
        if df.empty:
            print("⚠️ No data scraped.", flush=True); return
        pk_cols = _infer_pk(df)
        added = merge_into_history("customer_acquisitions", df, pk_cols=pk_cols)
        print(f"✅ Customer Acquisition BACKFILL merged. New/updated rows: {added}", flush=True)
        return

    if len(sys.argv) == 3:
        frm, to = sys.argv[1], sys.argv[2]
        print(f"⏱️  Scraping Customer Acquisition (UI path) {frm} → {to} …", flush=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=300)
            ctx     = browser.new_context()
            page    = ctx.new_page()
            login(page)
            df = scrape_customer_acq_chunk({"ctx": ctx, "page": page}, frm, to)
            browser.close()

        if df.empty:
            print("⚠️ No data scraped.", flush=True); return

        pk_cols = _infer_pk(df)
        added = merge_into_history("customer_acquisitions", df, pk_cols=pk_cols)
        print(f"✅ Customer Acquisition merged. New/updated rows: {added}", flush=True)
        return

    print("⏱️  Scraping Customer Acquisition (±6 months) via subprocess …", flush=True)
    frm, to = _month_window_daily()
    rc = _run_one_window_subprocess(frm, to, timeout_s=180)
    if rc != 0:
        print("⚠️ Customer Acquisition daily window failed or timed out.", flush=True)

if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
