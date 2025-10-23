# app/common/scrape_ibf.py

import os
import sys
import time
import subprocess
import re
import unicodedata
from datetime import datetime
from dateutil.relativedelta import relativedelta

import pandas as pd
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from app.common.utils_merge  import merge_into_history
from app.common.utils_raw    import archive_text, archive_df
from app.common.utils_dates  import fmt_mmddyyyy, month_windows

LOGIN_URL = "https://newton.hosting.memetic.it/login"
USERNAME  = "Tutor"
PASSWORD  = "FiguMass2025$"

# ── how many months per exported table (tune if needed: 2/3/4 etc.)
CHUNK_MAX_MONTHS = 3

# ── header like "6 - 2025"
MONTH_HDR_RE   = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{4})\s*$", re.I)
# ── title like "NEWTO 06/01/2025 - 08/31/2025" (fallback only)
TITLE_RANGE_RE = re.compile(r"(\d{1,2}/\d{1,2}/\d{4}).*?(\d{1,2}/\d{1,2}/\d{4})")

BUBB_RE = re.compile(r"\bbubb\s*[:=]\s*(\d+)", re.I)
CELL_RE = re.compile(r"\bcell\s*[:=]\s*(\d+)", re.I)

# Kept for ordering; matching is alias-aware below
RIGHT_COLS_LABELS = [
    "Date Start First Contract",
    "Date Start Last Contract",
    "Bubble",
    "Cellushape",
]

def _norm(s: str) -> str:
    """Case/space/accents-insensitive normalization."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().casefold()

# canonical label → acceptable header aliases (EN/IT/spacing/case variants)
RIGHT_COLS_ALIASES = {
    "Date Start First Contract": [
        "date start first contract",
        "first contract start date",
        "first start date",
        "date start first",
        "data inizio primo contratto",
        "data inizio primo",
        "datestartfirstcontract",
    ],
    "Date Start Last Contract": [
        "date start last contract",
        "last contract start date",
        "last start date",
        "date start last",
        "data inizio ultimo contratto",
        "data inizio ultimo",
        "datestartlastcontract",
    ],
    "Bubble": [
        "bubble", "bubb", "bubble total", "bolla"
    ],
    "Cellushape": [
        "cellushape", "cellu shape", "cell", "cell total", "cellushape total"
    ],
}

# ─────────────────────────── Navigation helpers ───────────────────────────

def _goto_with_retry(page, url, attempts=3, nav_timeout_ms=90_000):
    page.set_default_navigation_timeout(nav_timeout_ms)
    last_err = None
    for _ in range(attempts):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout_ms)
            return True
        except Exception as e:
            last_err = e
            try:
                page.wait_for_timeout(1200)
                page.reload(wait_until="domcontentloaded", timeout=nav_timeout_ms)
                return True
            except Exception:
                pass
    if last_err:
        print(f"[login] goto failed: {last_err}", flush=True)
    return False

def login(page):
    page.set_default_timeout(90_000)
    page.set_default_navigation_timeout(90_000)
    if not _goto_with_retry(page, LOGIN_URL, attempts=3, nav_timeout_ms=90_000):
        raise TimeoutError("Could not reach franchisor login page.")
    page.wait_for_selector("#txtUsername", timeout=60_000)
    page.fill("#txtUsername", USERNAME)
    page.fill("#txtPassword", PASSWORD)
    page.click("#btnAccedi")
    page.wait_for_selector("text=Reports", timeout=90_000)

def goto_ibf(page):
    page.click("text=Reports");  page.wait_for_timeout(250)
    # IBF = "Riepilogo per mesi" on portal
    try:
        page.click("#ctl00_cphMain_lnkRiepilogoPerMesi", timeout=8_000)
    except Exception:
        page.click("text=Riepilogo per mesi", timeout=8_000)
    page.wait_for_timeout(250)

# ───────────────────────────── Parser utils ──────────────────────────────

def _text(el) -> str:
    return (el.get_text(separator=" ", strip=True) if el else "").strip()

def _eom(y: int, m: int) -> pd.Timestamp:
    if m == 12: return pd.Timestamp(year=y, month=12, day=31)
    first_next = pd.Timestamp(year=y + (m // 12), month=(m % 12) + 1, day=1)
    return first_next - pd.Timedelta(days=1)

def _parse_bubb_cell(cell_text: str) -> tuple[int, int, str]:
    """
    Parse 'Bubb: N' and 'Cell: M'; tolerate bare numbers.
    Return (bubb, cell, portal_display_string)
    """
    if not cell_text:
        return 0, 0, "Bubb: 0\nCell: 0"
    cell_text = cell_text.replace("\r", "").replace("<br>", "\n")
    bubb, cell = 0, 0
    mb = BUBB_RE.search(cell_text)
    if mb:
        try: bubb = int(mb.group(1))
        except Exception: pass
    else:
        try: bubb = int(float(re.sub(r"[^\d\.\-]", "", cell_text)))
        except Exception: pass
    mc = CELL_RE.search(cell_text)
    if mc:
        try: cell = int(mc.group(1))
        except Exception: pass
    display = f"Bubb: {bubb}\nCell: {cell}"
    return bubb, cell, display

# ───────────────────── HTML → (tidy, wide-chunk) parser ──────────────────

def _parse_ibf_table_html(html: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Parse an IBF table with multiple month columns:
      <th>6 - 2025</th> ...; body cells: "Bubb: N<br>Cell: M".
    Return:
      tidy_df: Client | Date(EOM) | Bubb | Cell | [Date Start First Contract] | [Date Start Last Contract] | [Bubble] | [Cellushape]
      wide_df: Client | month columns | right-side 4 columns (display strings for months; raw text for right cols)
    """
    soup = BeautifulSoup(html, "lxml")

    # Fallback end date from title (only if no month headers)
    end_date_fallback = None
    title_span = soup.select_one("#cphMain_lblTitolo")
    if title_span:
        m = TITLE_RANGE_RE.search(title_span.get_text(" ", strip=True))
        if m:
            try:
                end_date_fallback = pd.to_datetime(m.group(2), format="%m/%d/%Y")
            except Exception:
                end_date_fallback = None

    tbl = soup.find("table", class_="table") or soup.find("table")
    if not tbl:
        return pd.DataFrame(columns=["Client","Date","Bubb","Cell"]), pd.DataFrame()

    # Find header row (first row containing any month header)
    all_trs = tbl.find_all("tr")
    header_tr = None
    for tr in all_trs:
        ths = tr.find_all(["th","td"])
        if ths and any(MONTH_HDR_RE.match(_text(th)) for th in ths):
            header_tr = tr
            break

    month_cols = []     # list of (col_idx, y, m, label)
    right_map  = {}     # canonical label -> col_idx
    body_trs   = []

    if not header_tr:
        if end_date_fallback is None:
            return pd.DataFrame(columns=["Client","Date","Bubb","Cell"]), pd.DataFrame()
        month_cols = [(1, None, None, end_date_fallback.strftime("%-m - %Y") if hasattr(end_date_fallback, "strftime") else "range")]
        body_trs = all_trs[1:] if len(all_trs) > 1 else []
    else:
        ths = header_tr.find_all(["th","td"])
        for idx, th in enumerate(ths):
            lab = _text(th)
            m = MONTH_HDR_RE.match(lab)
            if m:
                mm = int(m.group(1)); yy = int(m.group(2))
                month_cols.append((idx, yy, mm, f"{mm} - {yy}"))
                continue

            # alias-aware match for right-side columns
            nlab = _norm(lab)
            for canon, aliases in RIGHT_COLS_ALIASES.items():
                if nlab in { _norm(a) for a in aliases }:
                    right_map[canon] = idx
                    break

        # If unlabeled, guess last two non-month columns as Bubble/Cellushape
        if not right_map:
            non_month_idxs = [i for i, th in enumerate(ths) if not MONTH_HDR_RE.match(_text(th)) and i != 0]
            if len(non_month_idxs) >= 2:
                right_map["Bubble"]     = non_month_idxs[-2]
                right_map["Cellushape"] = non_month_idxs[-1]

        # body rows follow header row
        seen = False
        for tr in all_trs:
            if tr is header_tr:
                seen = True
                continue
            if seen:
                body_trs.append(tr)

        if not month_cols:
            if end_date_fallback is None:
                return pd.DataFrame(columns=["Client","Date","Bubb","Cell"]), pd.DataFrame()
            month_cols = [(1, None, None, end_date_fallback.strftime("%-m - %Y") if hasattr(end_date_fallback, "strftime") else "range")]

    tidy_rows = []
    wide_rows = {}  # client -> dict of month display + right cols

    for tr in body_trs:
        tds = tr.find_all("td")
        if not tds:
            continue

        client = _text(tds[0]).strip() if len(tds) else ""
        if not client:
            continue

        wr = wide_rows.setdefault(client, {})

        # ---- right-side values for this client (we'll also put them in each tidy row)
        rs_first = rs_last = ""
        rs_bubbT = rs_cellT = ""
        if "Date Start First Contract" in right_map and right_map["Date Start First Contract"] < len(tds):
            rs_first = _text(tds[right_map["Date Start First Contract"]])
        if "Date Start Last Contract" in right_map and right_map["Date Start Last Contract"] < len(tds):
            rs_last  = _text(tds[right_map["Date Start Last Contract"]])
        if "Bubble" in right_map and right_map["Bubble"] < len(tds):
            rs_bubbT = _text(tds[right_map["Bubble"]])
        if "Cellushape" in right_map and right_map["Cellushape"] < len(tds):
            rs_cellT = _text(tds[right_map["Cellushape"]])

        # record right-side values into the wide row under canonical labels
        if rs_first:  wr["Date Start First Contract"] = rs_first
        if rs_last:   wr["Date Start Last Contract"]  = rs_last
        if rs_bubbT:  wr["Bubble"]     = rs_bubbT
        if rs_cellT:  wr["Cellushape"] = rs_cellT

        # ---- month cells + tidy rows
        for idx, yy, mm, label in month_cols:
            if idx >= len(tds):
                continue
            cell_text = _text(tds[idx])
            bubb, cell, display = _parse_bubb_cell(cell_text)

            # Date (EOM) for month
            if yy is not None and mm is not None:
                dt = _eom(yy, mm)
            else:
                dt = pd.to_datetime(end_date_fallback) if end_date_fallback is not None else pd.NaT

            # tidy row: add right-side values (duplicated per month row for this client)
            row = {
                "Client": client,
                "Date":   dt,
                "Bubb":   bubb,
                "Cell":   cell,
            }
            if rs_first != "":  row["Date Start First Contract"] = rs_first
            if rs_last  != "":  row["Date Start Last Contract"]  = rs_last
            if rs_bubbT != "":  row["Bubble"]     = rs_bubbT
            if rs_cellT != "":  row["Cellushape"] = rs_cellT
            tidy_rows.append(row)

            # wide display cell for month
            wr[label] = display

    # tidy dataframe
    if tidy_rows:
        tidy_df = pd.DataFrame(tidy_rows)
    else:
        tidy_df = pd.DataFrame(columns=["Client","Date","Bubb","Cell"])

    # wide dataframe
    if wide_rows:
        wide_df = pd.DataFrame([{"Client": k, **v} for k, v in wide_rows.items()])
        # Sort month columns ascending
        month_labels = [c for c in wide_df.columns if c not in (["Client"] + RIGHT_COLS_LABELS)]
        def _month_sort_key(s):
            m = MONTH_HDR_RE.match(s or "")
            if m: return (int(m.group(2)), int(m.group(1)))
            return (9999, 99)
        month_labels = sorted(month_labels, key=_month_sort_key)
        wide_df = wide_df[["Client"] + month_labels + [c for c in RIGHT_COLS_LABELS if c in wide_df.columns]]
    else:
        wide_df = pd.DataFrame()

    return tidy_df, wide_df

# ───────────────────────── Single-window scrape ──────────────────────────

def _scrape_ibf_single_window(ctx, page, from_date: str, to_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    goto_ibf(page)
    page.fill("#ctl00_cphMain_SelectDataDal_txtDataSel", from_date)
    page.fill("#ctl00_cphMain_SelectDataAl_txtDataSel",  to_date)
    page.click("text=Do Report")

    tidy = pd.DataFrame()
    wide = pd.DataFrame()

    # Try export link (download via request API — avoids hanging navigation)
    href = None
    try:
        page.wait_for_selector("#ctl00_cphMain_hlyDownloadHTML", timeout=15_000)
        href = page.get_attribute("#ctl00_cphMain_hlyDownloadHTML", "href")
    except Exception:
        href = None

    if href:
        full_url = f"https://newton.hosting.memetic.it/assist/{href}"
        try:
            resp = ctx.request.get(full_url, headers={"Referer": page.url}, timeout=90_000)
            if resp.ok:
                html = resp.text()
                archive_text("ibf", html, tag=f"{from_date}_to_{to_date}", ext="html")
                tidy, wide = _parse_ibf_table_html(html)
            else:
                print(f"[IBF] export GET failed: {resp.status} {full_url[-120:]}", flush=True)
        except Exception as e:
            print(f"[IBF] export GET error: {e}", flush=True)

    # Inline fallback
    if tidy.empty and wide.empty:
        try:
            page.wait_for_selector("table.table", timeout=8_000)
            html = page.content()
            archive_text("ibf", html, tag=f"{from_date}_to_{to_date}_INLINE", ext="html")
            tidy, wide = _parse_ibf_table_html(html)
        except Exception:
            pass

    # Archive chunk snapshots (serialize tidy dates for JSON)
    if not tidy.empty:
        snap = tidy.copy()
        try: snap["Date"] = pd.to_datetime(snap["Date"]).dt.strftime("%Y-%m-%d")
        except Exception: pass
        archive_df("ibf_tidy", snap, tag=f"{from_date}_to_{to_date}")

    if not wide.empty:
        archive_df("ibf_wide", wide, tag=f"{from_date}_to_{to_date}")

    return tidy, wide

# ──────────────── combine many chunks → one tidy + one wide ──────────────

def _combine_wide(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Merge multiple wide chunks, unioning month columns and keeping latest non-empty right-side fields per client."""
    if not frames:
        return pd.DataFrame()

    out = None
    for df in frames:
        if out is None:
            out = df.copy()
        else:
            out = out.merge(df, on="Client", how="outer", suffixes=("", "_dup"))

            # de-duplicate right-side columns if same labels appear twice
            for label in RIGHT_COLS_LABELS:
                col_main = label
                col_dup  = f"{label}_dup"
                if col_dup in out.columns:
                    out[col_main] = out[col_main].where(out[col_main].astype(str).str.len() > 0, out[col_dup])
                    out.drop(columns=[col_dup], inplace=True)

            # drop any duplicated month columns with _dup
            dup_months = [c for c in out.columns if c.endswith("_dup") and c not in RIGHT_COLS_LABELS]
            if dup_months:
                out.drop(columns=dup_months, inplace=True)

    # Order columns: Client | sorted months | right-side columns
    cols = list(out.columns)
    month_cols = [c for c in cols if c not in (["Client"] + RIGHT_COLS_LABELS)]
    def _month_sort_key(s):
        m = MONTH_HDR_RE.match(s or "")
        if m: return (int(m.group(2)), int(m.group(1)))
        return (9999, 99)
    month_cols = sorted(month_cols, key=_month_sort_key)
    final_cols = ["Client"] + month_cols + [c for c in RIGHT_COLS_LABELS if c in out.columns]
    return out.reindex(columns=final_cols)

# ───────────────────────── Multi-window runners ─────────────────────────

def _scrape_over_range(start_dt: datetime, end_dt: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Scrape month-aligned windows between start_dt and end_dt."""
    tidy_frames = []
    wide_frames = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx     = browser.new_context(ignore_https_errors=True)
        ctx.set_default_timeout(90_000)
        ctx.set_default_navigation_timeout(90_000)

        page = ctx.new_page()
        page.on("pageerror", lambda e: print("[PAGE ERROR]", e, flush=True))
        page.on("console",   lambda m: print("[CONSOLE]", m.type, m.text, flush=True))

        login(page)

        for frm, to in month_windows(start_dt, end_dt, chunk_max=CHUNK_MAX_MONTHS, overlap=0):
            print(f"-> IBF window {frm} -> {to}", flush=True)
            try:
                tidy, wide = _scrape_ibf_single_window(ctx, page, frm, to)
            except Exception as e:
                print(f"[IBF] window {frm} -> {to} error: {e}", flush=True)
                continue
            if not tidy.empty:
                tidy_frames.append(tidy)
            if not wide.empty:
                wide_frames.append(wide)

        browser.close()

    tidy_all = pd.concat(tidy_frames, ignore_index=True) if tidy_frames else pd.DataFrame()
    wide_all = _combine_wide(wide_frames) if wide_frames else pd.DataFrame()
    return tidy_all, wide_all

def run_plusminus_6m():
    today = datetime.today()
    start_dt = (today - relativedelta(months=6)).replace(day=1)
    end_dt   = (today + relativedelta(months=6) + relativedelta(day=31))
    return _scrape_over_range(start_dt, end_dt)

def run_backfill_year():
    y = datetime.today().year
    start_dt = datetime(y, 1, 1)
    end_dt   = datetime.today()
    return _scrape_over_range(start_dt, end_dt)

# ─────────────────────────────── CLI entry ───────────────────────────────

def _merge_tidy_and_save_wide(tidy: pd.DataFrame, wide: pd.DataFrame, tag: str):
    if not tidy.empty:
        added = merge_into_history("ibf", tidy, pk_cols=["Client","Date"])
        print(f"IBF tidy merged. New/updated rows: {added}", flush=True)
    else:
        print("No tidy rows to merge.", flush=True)

    if not wide.empty:
        archive_df("ibf_wide", wide, tag=tag)
        print(f"IBF wide snapshot saved (tag={tag}).", flush=True)
    else:
        print("No wide snapshot produced.", flush=True)

def main():
    # 1) Backfill: Jan 1 current year → today
    if len(sys.argv) == 2 and sys.argv[1] == "--backfill-year":
        print("IBF backfill (year-to-date)…", flush=True)
        tidy, wide = run_backfill_year()
        if tidy.empty and wide.empty:
            print("No IBF data scraped.", flush=True); return
        _merge_tidy_and_save_wide(tidy, wide, tag="backfill_year_to_date")
        return

    # 2) Explicit ±6 months
    if len(sys.argv) == 2 and sys.argv[1] == "--plusminus-6m":
        print("IBF ±6 months…", flush=True)
        tidy, wide = run_plusminus_6m()
        if tidy.empty and wide.empty:
            print("No IBF data scraped.", flush=True); return
        _merge_tidy_and_save_wide(tidy, wide, tag="plusminus_6m")
        return

    # 3) Manual exact window (e.g., 06/01/2025 09/30/2025)
    if len(sys.argv) == 3:
        frm, to = sys.argv[1], sys.argv[2]
        print(f"IBF manual window {frm} -> {to}…", flush=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx     = browser.new_context(ignore_https_errors=True)
            ctx.set_default_timeout(90_000)
            ctx.set_default_navigation_timeout(90_000)
            page    = ctx.new_page()
            login(page)
            tidy, wide = _scrape_ibf_single_window(ctx, page, frm, to)
            browser.close()
        if tidy.empty and wide.empty:
            print("IBF report contained no data.", flush=True); return
        _merge_tidy_and_save_wide(tidy, wide, tag=f"{frm}_to_{to}")
        return

    # 4) Default daily: run ±6m
    print("IBF daily ±6m…", flush=True)
    tidy, wide = run_plusminus_6m()
    if tidy.empty and wide.empty:
        print("No IBF data scraped.", flush=True); return
    _merge_tidy_and_save_wide(tidy, wide, tag="daily_plusminus_6m")

if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
