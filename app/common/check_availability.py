# app/common/check_availability.py
"""
Reads availability by intercepting the ASP.NET UpdatePanel async-postback
response (no DOM heuristics). Busy = green pill (.badge.text-bg-success) or
red block (.btn-danger / .text-bg-danger / text contains 'blocked'); else open.
"""

from playwright.sync_api import sync_playwright
from typing import Dict, List, Optional, Tuple
import re

from app.common.create_appointment import login as _login
from app.common.create_appointment import goto_calendar_and_set_date as _goto_date

PANEL_ID = "ctl00_cphMain_upnlMain"  # UpdatePanel that holds the agenda table

# ---------- MS Ajax (UpdatePanel) delta parser ----------

def _extract_panel_html_from_delta(payload: str, panel_id: str) -> Optional[str]:
    """Parse MS Ajax delta payload and return HTML for the UpdatePanel."""
    if not payload:
        return None
    parts = payload.split("|")
    for i in range(len(parts) - 3):
        if parts[i] == "updatePanel" and parts[i + 1] == panel_id:
            html_candidate = parts[i + 2]
            if html_candidate.strip().startswith("<"):
                return html_candidate
            if i + 3 < len(parts) and parts[i + 3].strip().startswith("<"):
                return parts[i + 3]
    return None

# ---------- HTML parsing ----------

_TIME_RX = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([ap])m\s*$", re.I)

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def _format_time12(s: str) -> str:
    s = _norm((s or "").lower().replace(".", ""))
    m = _TIME_RX.match(s)
    if not m:
        return s
    hh = str(int(m.group(1)))
    return f"{hh}:{m.group(2)} {m.group(3)}"

def _parse_table_from_html(html: str) -> Tuple[List[str], List[Tuple[str, List[bool]]]]:
    """Parse agenda table HTML → (headers, rows)."""
    headers: List[str] = []
    thead_match = re.search(r"<thead[^>]*>(.*?)</thead>", html, flags=re.S | re.I)
    if thead_match:
        ths = re.findall(r"<th[^>]*>(.*?)</th>", thead_match.group(1), flags=re.S | re.I)
        for th in ths:
            text = _norm(re.sub(r"<[^>]+>", " ", th))
            if text and not re.fullmatch(r"(?i)time", text):
                headers.append(text)
    if not headers:
        headers = ["Consultation","Bubble 1","Bubble 2","Bubble 3","Bubble 4","Cellushape"]

    rows: List[Tuple[str, List[bool]]] = []
    tbody_match = re.search(r"<tbody[^>]*>(.*?)</tbody>", html, flags=re.S | re.I)
    if not tbody_match:
        return headers, rows

    for tr_html in re.findall(r"<tr[^>]*>(.*?)</tr>", tbody_match.group(1), flags=re.S | re.I):
        # find time cell
        time_label, time_idx = "", -1
        for idx, cell_html in enumerate(re.findall(r"<td[^>]*>(.*?)</td>", tr_html, flags=re.S | re.I)):
            text = _norm(re.sub(r"<[^>]+>", " ", cell_html))
            if time_idx < 0 and _TIME_RX.match(text or ""):
                time_idx, time_label = idx, text
                break
        if time_idx < 0:
            continue

        # device cells
        rdev_cells = re.findall(r"<td[^>]*class=['\"][^'\"]*r_device[^'\"]*['\"][^>]*>(.*?)</td>",
                                tr_html, flags=re.S | re.I)
        dev_cells = rdev_cells if rdev_cells else re.findall(
            r"<td[^>]*>(.*?)</td>", tr_html, flags=re.S | re.I)[time_idx + 1 :
        ]

        # busy detection
        busy_flags: List[bool] = []
        for i in range(len(headers)):
            cell = dev_cells[i] if i < len(dev_cells) else ""
            green = re.search(r"class=['\"][^'\"]*badge[^'\"]*text-bg-success[^'\"]*['\"]", cell, re.I)
            red   = re.search(r"class=['\"][^'\"]*(btn-danger|text-bg-danger)[^'\"]*['\"]", cell, re.I)
            blocked = re.search(r"blocked", cell, re.I)
            busy_flags.append(bool(green or red or blocked))

        rows.append((_format_time12(time_label), busy_flags))

    return headers, rows

# ---------- Public API ----------

def get_open_slots(date_iso: str,
                   allowed_columns: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """
    1) Login & navigate to agenda
    2) Set the date (triggers async postback)
    3) Intercept the async postback RESPONSE
    4) Parse UpdatePanel HTML → compute availability
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)   # headless=False for debugging
        ctx = browser.new_context()
        page = ctx.new_page()

        _login(page)

        delta_payload = {"text": None}
        def _on_response(resp):
            try:
                ct = resp.headers.get("content-type", "") if hasattr(resp, "headers") else ""
                xma = resp.headers.get("x-microsoftajax", "") if hasattr(resp, "headers") else ""
                if "text/plain" in ct and "Delta" in xma:
                    txt = resp.text()
                    if PANEL_ID in txt:
                        delta_payload["text"] = txt
            except Exception:
                pass
        ctx.on("response", _on_response)

        _goto_date(page, date_iso)

        page.wait_for_timeout(200)
        if not delta_payload["text"]:
            for _ in range(20):
                page.wait_for_timeout(150)
                if delta_payload["text"]:
                    break

        if not delta_payload["text"]:
            panel_html = page.locator(f"#{PANEL_ID}").inner_html()
        else:
            panel_html = _extract_panel_html_from_delta(delta_payload["text"], PANEL_ID) or ""

        headers, parsed_rows = _parse_table_from_html(panel_html)

        if allowed_columns:
            wanted = { _norm(c).lower() for c in allowed_columns }
            headers = [h for h in headers if _norm(h).lower() in wanted]

        results: Dict[str, List[str]] = { h: [] for h in headers }
        for time_label, busy_flags in parsed_rows:
            for i, h in enumerate(headers):
                if i < len(busy_flags) and not busy_flags[i]:
                    results[h].append(time_label)

        # dedupe
        for h, arr in list(results.items()):
            seen, out = set(), []
            for t in arr:
                key = _norm(t).lower()
                if key not in seen:
                    out.append(t); seen.add(key)
            results[h] = out

        ctx.close(); browser.close()
        return results
