# app/common/create_appointment.py
from playwright.sync_api import sync_playwright
import re, time, unicodedata
from typing import Optional

LOGIN_URL   = "https://newton.hosting.memetic.it/login"
AGENDA_URL  = "https://newton.hosting.memetic.it/assist/agenda_edit"
CAL_WRAP_ID = "ctl00_cphMain_upnlMain"

# DEV ONLY
FIG_USER = "Tutor"
FIG_PASS = "FiguMass2025$"

BAD_CODES = set(range(400, 600))

# ───────── helpers ─────────

def _slug(s: str) -> str:
    """Lowercase, strip, collapse spaces, remove accents for robust name compare."""
    if not s: return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def _normalize_time_label(raw: str) -> str:
    if not raw: return ""
    s = str(raw).strip().lower().replace(".", "")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(\d)(am|pm)$", r"\1 \2", s)
    m = re.match(r"^(\d{1,2})(\d{2})\s*(am|pm)$", s)
    if m: return f"{int(m.group(1))}:{m.group(2)} {m.group(3)}"
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", s)
    if m:
        hh = int(m.group(1)); mm = m.group(2) or "00"; ap = m.group(3)
        if ap in ("am","pm"): return f"{hh}:{mm} {ap}"
        if hh == 0: return f"12:{mm} am"
        if 1 <= hh <= 11: return f"{hh}:{mm} am"
        if hh == 12: return f"12:{mm} pm"
        if 13 <= hh <= 23: return f"{hh-12}:{mm} pm"
    return s

def _time_to_minutes(label: str):
    if not label: return None
    txt = _normalize_time_label(label).lower()
    m = re.match(r"^(\d{1,2}):(\d{2})\s*([ap])m$", txt)
    if not m: return None
    hh, mm, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if hh == 12: hh = 0 if ap == "a" else 12
    elif ap == "p": hh += 12
    return hh*60 + mm

def _slot_index(time_label: str) -> int:
    mins = _time_to_minutes(time_label)
    if mins is None: raise RuntimeError(f"Unrecognized time '{time_label}'.")
    start = 5*60 + 30
    delta = mins - start
    if delta < 0 or (delta % 30) != 0:
        raise RuntimeError(f"Time '{time_label}' must be on a 30-minute grid ≥ 05:30 am.")
    return delta // 30

def _resource_index(column_label: str) -> int:
    lab = column_label.strip().lower()
    mapping = {
        "consultation": 0,
        "bubble 1": 1,
        "bubble 2": 2,
        "bubble 3": 3,
        "bubble 4": 4,
        "cellushape": 5,
    }
    if lab not in mapping: raise RuntimeError(f"Unknown column label: {column_label}")
    return mapping[lab]

def _to_mmddyyyy(date_str: str) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_str or "")
    if m: y, mo, d = m.groups(); return f"{mo}/{d}/{y}"
    return date_str

def _webforms_submit(page, target: str, argument: str = ""):
    page.evaluate(
        """({target, argument}) => {
          const form=document.getElementById('aspnetForm'); if(!form) return;
          const et=document.getElementById('__EVENTTARGET'); if(et) et.value=target;
          const ea=document.getElementById('__EVENTARGUMENT'); if(ea) ea.value=argument||'';
          form.submit && form.submit();
        }""",
        {"target": target, "argument": argument}
    )

def _wait_webforms_async_complete(page, timeout_ms: int = 15000):
    try:
        page.wait_for_function(
            """
            () => {
              try{
                if(!window.Sys || !Sys.WebForms || !Sys.WebForms.PageRequestManager) return true;
                return !Sys.WebForms.PageRequestManager.getInstance().get_isInAsyncPostBack();
              }catch(e){ return true; }
            }""",
            timeout=timeout_ms
        )
    except Exception:
        page.wait_for_timeout(500)

def _cell_locator_for(page, time_label: str, column_label: str):
    want = _time_to_minutes(time_label)
    rows = page.locator(f"#{CAL_WRAP_ID} table tbody tr")
    n = rows.count()
    row_loc = None
    for i in range(n):
        raw = (rows.nth(i).locator("td").first.inner_text(timeout=0) or "").strip()
        if _time_to_minutes(raw) == want:
            row_loc = rows.nth(i); break
    if row_loc is None: raise RuntimeError(f"Time row not found: {time_label}")
    td_idx = 1 + _resource_index(column_label)
    return row_loc.locator("td").nth(td_idx)

# ───────── client binding (full name only) ─────────

def _pick_select2_by_name(page, full_name: str) -> bool:
    """
    Open the suggestion dropdown robustly and click a row matching the full name.
    Supports Select2, jQuery UI autocomplete, and Typeahead/Bloodhound.
    Returns True if a row was clicked.
    """
    want = _slug(full_name)

    # Ensure dropdown is open: click container, press ArrowDown, dispatch events
    try:
        wrappers = page.locator(
            "span.select2-container, .select2-selection, .select2-selection--single, "
            ".ui-autocomplete-input, .tt-input, .tt-hint"
        )
        if wrappers.count():
            try: wrappers.first.click()
            except: pass
    except:
        pass

    # Nudge the widget to fetch suggestions
    try:
        txt = page.locator("#ctl00_cphMain_SelectClienteAddAppuntamento_txtSelectCliente")
        if txt.count():
            txt.press("ArrowDown")
            page.evaluate("""
              (id) => {
                const el = document.getElementById(id);
                if(!el) return;
                ['input','keyup','keydown','change'].forEach(t => el.dispatchEvent(new Event(t, {bubbles:true})));
              }
            """, "ctl00_cphMain_SelectClienteAddAppuntamento_txtSelectCliente")
    except:
        pass

    # Candidate result containers
    results_query = (
        "ul.select2-results__options li.select2-results__option, "
        "ul.select2-results__options li, "
        ".select2-results__option, .select2-results li, "     # Select2
        "ul.ui-autocomplete li.ui-menu-item, "                 # jQuery UI
        ".tt-menu .tt-suggestion, .twitter-typeahead .tt-suggestion"  # Typeahead
    )
    results = page.locator(results_query)
    try:
        results.first.wait_for(timeout=5000)
    except:
        # one more nudge
        try:
            txt = page.locator("#ctl00_cphMain_SelectClienteAddAppuntamento_txtSelectCliente")
            if txt.count():
                txt.type(" ", delay=10)
                txt.press("Backspace")
        except:
            pass
        try:
            results.first.wait_for(timeout=4000)
        except:
            return False

    # Build list for matching
    items = []
    cnt = results.count()
    for i in range(cnt):
        try:
            t = (results.nth(i).inner_text(timeout=0) or "").strip()
        except:
            t = ""
        if not t: continue
        items.append((i, t, _slug(t)))

    # exact / startswith / contains
    for i, raw, slug in items:
        if slug == want:
            try:
                results.nth(i).click(); return True
            except: pass
    for i, raw, slug in items:
        if slug.startswith(want) or want in slug:
            try:
                results.nth(i).click(); return True
            except: pass

    # fallback: first suggestion
    try:
        results.first.click(); return True
    except:
        return False

def _bind_customer(page, name: str) -> str:
    """
    Type the full name, open the dropdown, click a suggestion, and verify the hidden id was set.
    """
    txt = page.locator("#ctl00_cphMain_SelectClienteAddAppuntamento_txtSelectCliente")
    txt.wait_for(timeout=15000)

    # Focus + clear + type
    txt.click(force=True)
    try:
        txt.press("Control+A")
    except:
        try: txt.press("Meta+A")
        except: pass
    txt.press("Backspace")
    txt.type(name, delay=25)

    # Try to pick by name; if not, try Enter to accept first suggestion
    picked = _pick_select2_by_name(page, name)
    if not picked:
        try:
            txt.press("ArrowDown")
            txt.press("Enter")
        except:
            pass

    # Verify the widget set the hidden id (server needs a real numeric id here)
    try:
        hid_val = page.evaluate(
            "() => document.getElementById('ctl00_cphMain_SelectClienteAddAppuntamento_hidSelectedCliente')?.value || ''"
        )
    except:
        hid_val = ""

    print(f"DEBUG: hidSelectedCliente after selection = '{hid_val}'")
    if not hid_val.strip():
        raise RuntimeError("Client selection failed: hidden id not set after choosing name.")

    return hid_val

# ───────── core flow ─────────

def login(page):
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.fill('input[type="text"]', FIG_USER)
    page.fill('input[type="password"]', FIG_PASS)
    page.click('input[type="submit"], button:has-text("Login"), button:has-text("Accedi")')
    page.wait_for_load_state("networkidle")

def goto_calendar_and_set_date(page, date_iso: str):
    page.goto(AGENDA_URL, wait_until="domcontentloaded")
    page.locator(f"#{CAL_WRAP_ID}").wait_for(timeout=15000)
    portal_date = _to_mmddyyyy(date_iso)
    page.evaluate(
        """(val)=> {
          const t=document.getElementById('ctl00_cphMain_SelectDataPrincipale_txtDataSel');
          const h=document.getElementById('ctl00_cphMain_SelectDataPrincipale_hidDataSel');
          if(t) t.value=val; if(h) h.value=val;
        }""",
        portal_date
    )
    _webforms_submit(page, "ctl00$cphMain$SelectDataPrincipale$hidDataSel", "")
    page.wait_for_load_state("networkidle")
    page.locator(f"#{CAL_WRAP_ID} table tbody tr").first.wait_for(timeout=15000)

def open_modal_by_time_and_column(page, time_label: str, column_label: str):
    time_label = _normalize_time_label(time_label)
    slot = _slot_index(time_label)
    res  = _resource_index(column_label)
    target = f"ctl00$cphMain$rptOrari$ctl{slot:02d}$rptResources$ctl{res:02d}$btnAddAppuntamento"
    _webforms_submit(page, target, "")
    cust = page.locator("#ctl00_cphMain_SelectClienteAddAppuntamento_txtSelectCliente")
    cust.wait_for(timeout=15000)

def _click_confirm_native(page):
    """
    Click the actual blue 'Create Appointment' button so their client-side
    validators and field collectors run. Fallback to a postback target.
    """
    btn = page.locator("#ctl00_cphMain_btnConfirmAddAppuntamento")
    if btn.count():
        try:
            btn.first.scroll_into_view_if_needed(timeout=800)
        except Exception:
            pass
        btn.first.click()
    else:
        # Fallback: trigger the same server handler
        page.evaluate("()=>{ try{ __doPostBack('ctl00$cphMain$btnConfirmAddAppuntamento',''); }catch(e){} }")

def fill_modal_and_confirm(page, customer_name: str, memo: str = "",
                           time_label: Optional[str] = None,
                           column_label: Optional[str] = None,
                           date_iso: Optional[str] = None) -> bool:
    """
    Bind client by full name, click the native Confirm button, wait for
    the ASP.NET async round-trip, and verify the chip appears.
    Retries once; finally refreshes same date and rechecks.
    """
    # 1) Bind the customer and ensure hidden id is set
    _ = _bind_customer(page, customer_name)

    # 2) Optional memo
    if memo:
        box = page.locator("#ctl00_cphMain_txtNotaInternaAdd")
        if box.count():
            box.fill(memo)

    # PRM wait helper
    def _wait_roundtrip():
        _wait_webforms_async_complete(page, 15000)

    # Chip verify helper
    first_token = (customer_name or "").split()[0]
    def _grid_has_chip():
        if not (time_label and column_label and first_token):
            return False
        try:
            cell = _cell_locator_for(page, time_label, column_label)
            cell.locator("text=" + first_token).first.wait_for(timeout=6000)
            return True
        except Exception:
            return False

    # 3) Click Confirm and wait
    _click_confirm_native(page)
    _wait_roundtrip()
    if _grid_has_chip():
        return True

    # 4) Retry once (helps with async/race)
    _click_confirm_native(page)
    _wait_roundtrip()
    if _grid_has_chip():
        return True

    # 5) Final attempt: soft refresh same date (if provided) and re-check
    if date_iso:
        try:
            portal_date = _to_mmddyyyy(date_iso)
            page.evaluate(
                """(val)=> {
                  const txt=document.getElementById('ctl00_cphMain_SelectDataPrincipale_txtDataSel');
                  const hid=document.getElementById('ctl00_cphMain_SelectDataPrincipale_hidDataSel');
                  if(txt) txt.value=val; if(hid) hid.value=val;
                }""",
                portal_date
            )
            _webforms_submit(page, "ctl00$cphMain$SelectDataPrincipale$hidDataSel", "")
            _wait_roundtrip()
            page.locator(f"#{CAL_WRAP_ID} table tbody tr").first.wait_for(timeout=15000)
        except Exception:
            pass

    ok = _grid_has_chip()
    if not ok:
        page.screenshot(path="final_cell.png", full_page=True)
        print("DEBUG: Could not verify chip (saved final_cell.png)")
    return ok

# ───────── public API ─────────

def create_appointment(date_iso: str, column_label: str, time_label: str,
                       customer_name: str, memo: str = "") -> bool:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context()
        page = context.new_page()
        page.on("console", lambda msg: print("PAGE LOG:", msg.type, msg.text))
        page.on("pageerror", lambda err: print("PAGE ERROR:", err))
        page.on("response", lambda r: (print("[HTTP]", r.status, r.url[-140:])) if r.status in BAD_CODES else None)

        try:
            login(page)
            goto_calendar_and_set_date(page, date_iso)
            open_modal_by_time_and_column(page, time_label, column_label)

            ok = fill_modal_and_confirm(
                page,
                customer_name=customer_name,
                memo=memo,
                time_label=time_label,
                column_label=column_label,
                date_iso=date_iso,
            )

            # Secondary lenient verification (in case chip appeared late)
            if not ok:
                first = (customer_name or "").split()[0] if customer_name else ""
                if first:
                    try:
                        cell = _cell_locator_for(page, time_label, column_label)
                        cell.locator("text=" + first).first.wait_for(timeout=6000)
                        ok = True
                    except Exception:
                        ok = False

            if not ok:
                page.screenshot(path="final_cell.png", full_page=True)
                print("DEBUG: Could not verify chip (saved final_cell.png)")
            return ok
        finally:
            context.close()
            browser.close()
