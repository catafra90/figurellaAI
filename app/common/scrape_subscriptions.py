import os
import sys
import subprocess
import re
from datetime import datetime
from typing import List, Tuple
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

# ---------- Login & Nav ----------

def login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#txtUsername", timeout=15_000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=20_000)

def goto_subscriptions(page):
    page.click("text=Reports")
    page.wait_for_timeout(200)
    # Try common labels
    for label in [
        "Subscriptions", "Subscription", "First Contract", "Primo contratto",
        "Subscriptions NEWTO", "Report first contract"
    ]:
        try:
            page.click(f"text={label}", timeout=1200)
            page.wait_for_timeout(150)
            return
        except Exception:
            pass
    # Fallback: go straight to the printable shell
    try:
        page.goto("https://newton.hosting.memetic.it/assist/report_firstcontract", wait_until="networkidle")
        return
    except Exception:
        pass
    raise RuntimeError("Subscriptions page not found")

# ---------- Helpers ----------

MONTH_HDR_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{4})\s*$", re.I)

def _build_direct_urls(from_date: str, to_date: str) -> List[str]:
    """
    Printable report URL variants for Subscriptions (same param pattern as PIP/Due/Done family).
    Some deployments use 'tom' vs 'tomm'; try both.
    Example: /assist/report_firstcontract?CLIENT_ID=0&fromgg=DD&frommm=MM&fromaa=YYYY&togg=DD&tom=MM&toaa=YYYY
    """
    def _parts(mdY: str):
        mm, dd, yyyy = mdY.split("/")
        return dd.zfill(2), mm.zfill(2), yyyy

    f_dd, f_mm, f_yyyy = _parts(from_date)
    t_dd, t_mm, t_yyyy = _parts(to_date)

    base = "https://newton.hosting.memetic.it/assist/report_firstcontract"

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

def _text_join(node) -> str:
    """Get text with <br> normalized to spaces; preserve key tokens like 'Bubb:' / 'Cell:' / '(residual: N)'."""
    if node is None:
        return ""
    # replace <br> with linebreaks for readability, then collapse extra spaces
    txt = node.get_text("\n", strip=True)
    # keep it simple: let downstream code parse residual/bubb if needed
    return re.sub(r"[ \t]+\n", "\n", txt).strip()

def _pick_main_table(soup: BeautifulSoup):
    """
    Choose the main Subscriptions table by looking near #cphMain_lblTitolo
    and selecting the first `.table.table-condensed.table-bordered.table-hover`.
    """
    title = soup.select_one("#cphMain_lblTitolo")
    if title:
        container = title.find_parent(class_=re.compile(r"\bcol-md-10\b")) or soup
        tbl = container.select_one("table.table.table-condensed.table-bordered.table-hover")
        if tbl:
            return tbl
    # Fallback: first table with several month headers like '4 - 2025'
    for tbl in soup.select("table"):
        tr = (tbl.tbody.find("tr") if getattr(tbl, "tbody", None) else tbl.find("tr"))
        if not tr:
            continue
        headers = [c.get_text(" ", strip=True) for c in tr.find_all(["td","th"])]
        month_like = sum(1 for h in headers if MONTH_HDR_RE.match(h or ""))
        if month_like >= 2:
            return tbl
    return None

# ---------- Parsing ----------

def _parse_subscriptions_html(html: str) -> pd.DataFrame:
    """
    Parse the wide Subscriptions table:
      Cols: Client | <M - YYYY>... | Contracts | Bubble | Cellushape
    Keep month cells as the portal text (e.g., 'Bubb: 7\\nCell: 0').
    """
    if not html:
        return pd.DataFrame()

    soup = BeautifulSoup(html, "html.parser")
    table = _pick_main_table(soup)
    if not table:
        return pd.DataFrame()

    body = table.tbody or table
    trs  = body.find_all("tr", recursive=False)
    if not trs:
        return pd.DataFrame()

    # Header
    hdr_cells = trs[0].find_all(["td","th"], recursive=False)
    headers = [c.get_text(" ", strip=True) for c in hdr_cells]
    # Normalize header names; keep exact month headers like '4 - 2025'
    norm_headers: List[str] = []
    for h in headers:
        hh = (h or "").strip()
        if hh == "" and len(norm_headers) == 0:
            norm_headers.append("Client")
        elif "contracts" in hh.lower():
            norm_headers.append("Contracts")
        elif "bubble" in hh.lower():
            norm_headers.append("Bubble")
        elif "cellu" in hh.lower():
            norm_headers.append("Cellushape")
        else:
            norm_headers.append(hh)

    # Data rows
    rows: List[dict] = []

    for tr in trs[1:]:
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue
        # If row is shorter/longer, pad/truncate to header length
        cells = tds[:len(norm_headers)] + [None] * max(0, len(norm_headers) - len(tds))

        rec = {}
        for idx, col in enumerate(norm_headers):
            node = cells[idx]
            # month cells are <td><div class="font-monospace">Bubb: X<br>Cell: Y</div></td>
            if col == "Client":
                rec["Client"] = _text_join(node)
            elif MONTH_HDR_RE.match(col or ""):
                # keep text (Bubb/Cell) verbatim (line breaks → '\n')
                rec[col] = _text_join(node)
            elif col in ("Contracts", "Bubble", "Cellushape"):
                rec[col] = _text_join(node)
            else:
                # unknown/trailing
                rec[col] = _text_join(node)

        # Skip empty client rows
        if not rec.get("Client", "").strip():
            continue

        rows.append(rec)

    if not rows:
        return pd.DataFrame()

    # Union all columns (months vary by window)
    all_cols = set()
    for r in rows:
        all_cols.update(r.keys())
    # Put Client first, then sorted month headers, then Contracts/Bubble/Cellushape, then extras
    month_cols = sorted([c for c in all_cols if MONTH_HDR_RE.match(c or "")],
                        key=lambda s: (int(MONTH_HDR_RE.match(s).group(2)), int(MONTH_HDR_RE.match(s).group(1))) if MONTH_HDR_RE.match(s or "") else (9999, 99))
    trailing = [c for c in ("Contracts", "Bubble", "Cellushape") if c in all_cols]
    extras   = [c for c in all_cols if c not in ({"Client"} | set(month_cols) | set(trailing))]

    ordered = ["Client"] + month_cols + trailing + extras

    df = pd.DataFrame(rows)
    df = df.reindex(columns=ordered)
    return df

# ---------- Scrape (single window) ----------

def scrape_subscriptions_chunk(ctx_page, from_date: str, to_date: str) -> pd.DataFrame:
    page = ctx_page["page"]
    ctx  = ctx_page["ctx"]

    goto_subscriptions(page)

    # Interactive attempt (some deployments have date inputs; ignore errors if not)
    try:
        page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
        page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel",  to_date)
        try:
            page.click("text=Do Report")
        except Exception:
            # try common alternates
            for label in ["Generate", "Visualizza", "Esegui", "Mostra", "Report"]:
                try:
                    page.click(f"text={label}", timeout=1200); break
                except Exception:
                    pass
    except Exception:
        pass

    try:
        page.wait_for_selector("table.table", timeout=20_000)
    except Exception:
        pass
    page.wait_for_load_state("networkidle")

    # Attempt 1: current page
    html = page.content()
    try: archive_text("subscriptions", html, tag=f"printable_{from_date}_to_{to_date}", ext="html")
    except Exception: pass

    df = _parse_subscriptions_html(html)
    print(f"[SUBS] interactive parsed cols={list(df.columns)[:6]} rows={len(df)}")
    if not df.empty:
        try: archive_df("subscriptions", df, tag=f"{from_date}_to_{to_date}")
        except Exception: pass
        return df

    # Attempt 2: direct printable (both 'tom' and 'tomm')
    for url in _build_direct_urls(from_date, to_date):
        try:
            rpage = ctx.new_page()
            rpage.goto(url, wait_until="networkidle")
            try: rpage.wait_for_selector("table.table", timeout=15000)
            except Exception: pass
            html2 = rpage.content()
            try: archive_text("subscriptions", html2, tag=f"direct_{from_date}_to_{to_date}", ext="html")
            except Exception: pass
            df2 = _parse_subscriptions_html(html2)
            print(f"[SUBS] direct parsed rows={len(df2)}")
            rpage.close()
            if not df2.empty:
                try: archive_df("subscriptions", df2, tag=f"{from_date}_to_{to_date}")
                except Exception: pass
                return df2
        except Exception as e:
            print(f"[SUBS] direct attempt failed: {e}")

    return pd.DataFrame()

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
            print(f"→ Subscriptions window {frm} → {to}", flush=True)
            try:
                df_win = scrape_subscriptions_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[SUBS] window {frm} → {to} error: {e}", flush=True)
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
            print(f"→ Subscriptions backfill window {frm} → {to}", flush=True)
            try:
                df_win = scrape_subscriptions_chunk({"ctx": ctx, "page": page}, frm, to)
            except Exception as e:
                print(f"[SUBS] backfill window {frm} → {to} error: {e}", flush=True)
                continue
            if not df_win.empty:
                frames.append(df_win)
        browser.close()
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# ---------- PK & CLI ----------

def _infer_pk(df: pd.DataFrame) -> List[str]:
    # Wide format = one row per client for the selected window
    return ["Client"] if "Client" in df.columns else [str(df.columns[0])]

def _month_window_daily() -> Tuple[str, str]:
    today = datetime.today()
    start = today - relativedelta(months=6)
    end   = today + relativedelta(months=6)
    return fmt_mmddyyyy(start), fmt_mmddyyyy(end)

def _run_one_window_subprocess(frm: str, to: str, timeout_s: int = 180) -> int:
    cmd = [sys.executable, "-u", "-m", "app.common.scrape_subscriptions", frm, to]
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", os.getcwd())
    print(f"   -> app.common.scrape_subscriptions  {frm}  →  {to}", flush=True)
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

    # backfill example
    if len(sys.argv) == 2 and sys.argv[1] == "--backfill-2025":
        start_dt = datetime(2025, 1, 1)
        end_dt   = datetime.today()
        print(f"⏱️  Backfilling Subscriptions from {start_dt:%m/%d/%Y} to {end_dt:%m/%d/%Y}…", flush=True)
        df = run_backfill_fixed(start_dt, end_dt, chunk_max=12, overlap=2)
        if df.empty:
            print("⚠️ No data scraped.", flush=True); return
        if DUMP_ONLY:
            try: archive_df("subscriptions_debug", df, tag="backfill_2025")
            except Exception: pass
            print(f"[dump-only] rows={len(df)} cols={list(df.columns)}")
            print(df.head(10).to_string(index=False)); return
        pk_cols = _infer_pk(df)
        added = merge_into_history("subscriptions", df, pk_cols=pk_cols)
        print(f"✅ Subscriptions BACKFILL merged. New/updated rows: {added}", flush=True)
        return

    # manual single window
    if len(sys.argv) == 3:
        frm, to = sys.argv[1], sys.argv[2]
        print(f"⏱️  Scraping Subscriptions (single window) {frm} → {to} …", flush=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx     = browser.new_context()
            page    = ctx.new_page()
            login(page)
            df = scrape_subscriptions_chunk({"ctx": ctx, "page": page}, frm, to)
            browser.close()

        if df.empty:
            print("⚠️ No data scraped.", flush=True); return

        if DUMP_ONLY:
            try: archive_df("subscriptions_debug", df, tag=f"{frm}_to_{to}")
            except Exception: pass
            print(f"[dump-only] rows={len(df)} cols={list(df.columns)}")
            print(df.head(10).to_string(index=False))
            return

        pk_cols = _infer_pk(df)
        added = merge_into_history("subscriptions", df, pk_cols=pk_cols)
        print(f"✅ Subscriptions merged. New/updated rows: {added}", flush=True)
        return

    # default daily refresh (±6m)
    print("⏱️  Scraping Subscriptions (±6 months) via subprocess …", flush=True)
    frm, to = _month_window_daily()
    rc = _run_one_window_subprocess(frm, to, timeout_s=180)
    if rc != 0:
        print("⚠️ Subscriptions daily window failed or timed out.", flush=True)

if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
