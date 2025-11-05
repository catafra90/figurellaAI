# app/figurella_reports/services/cli_runner.py
from __future__ import annotations
import os, sys
from datetime import datetime
from typing import Optional

from .api_client import (
    fetch_customers, fetch_payments, fetch_agenda, fetch_customer_notes
)
from .window_utils import compute_window, iso as to_iso
from .export_excel import (
    save_customers_excel, save_agenda_excel, save_payments_excel
)
from .customer_history import update_customer_history
from .agenda_history import update_agenda_history
from .payment_history import update_payment_history

# If you created a dedicated notes history module, import it here:
# from .notes_history import update_notes_history
# Otherwise, we'll inline a minimal saver below.
import pandas as pd

NOTES_XLSX = os.getenv("CUSTOMER_NOTES_XLSX", "customer_notes.xlsx")
NOTES_HISTORY_XLSX = os.getenv("CUSTOMER_NOTES_HISTORY_XLSX", "customer_notes_history.xlsx")

def _arg_flag(name: str) -> bool:
    return any(a == name for a in sys.argv[1:])

def _arg_kv(prefix: str) -> Optional[str]:
    # returns value for flags like --center=NEWTO or --after=2025-10-01
    for a in sys.argv[1:]:
        if a.startswith(prefix + "="):
            return a.split("=", 1)[1]
    return None

def _save_notes_excel(rows: list[dict]):
    df = pd.DataFrame(rows)
    # Add convenience columns if present
    if "createdOn" in df.columns:
        try:
            ts = pd.to_datetime(df["createdOn"], utc=True, errors="coerce").dt.tz_convert("America/New_York")
            df["createdOn_est"] = ts.dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    df.to_excel(NOTES_XLSX, index=False)
    print(f"📘 Saved Excel: {NOTES_XLSX} ({len(df)} rows)")

def _update_notes_history(rows: list[dict]) -> int:
    """
    Simple append-only history with de-dupe by (id if present/!=0) else (customerId+note+createdOn).
    """
    df_new = pd.DataFrame(rows)
    if df_new.empty:
        print("✅ 0 new note(s) added to history.")
        return 0

    # Build signature
    import hashlib
    def _sig(r):
        if pd.notna(r.get("id")) and str(r.get("id")) not in ("", "0"):
            return f"id:{r.get('id')}"
        key = f"{r.get('customerId','')}|{r.get('note','')}|{r.get('createdOn','')}"
        return "sig:" + hashlib.sha1(key.encode("utf-8")).hexdigest()

    df_new["_id_or_sig"] = [ _sig(r) for r in df_new.to_dict(orient="records") ]

    if os.path.exists(NOTES_HISTORY_XLSX):
        hist = pd.read_excel(NOTES_HISTORY_XLSX)
    else:
        hist = pd.DataFrame(columns=list(df_new.columns))

    before = len(hist)
    combined = pd.concat([hist, df_new], ignore_index=True)
    combined = combined.drop_duplicates(subset=["_id_or_sig"], keep="first").reset_index(drop=True)
    combined.to_excel(NOTES_HISTORY_XLSX, index=False)
    added = len(combined) - before
    print(f"✅ {added} new note(s) added to history. 📗 {NOTES_HISTORY_XLSX}")
    return added

def run_cli():
    from dotenv import load_dotenv
    ENV_PATH = os.path.join(os.path.dirname(__file__), "../../../.env")
    load_dotenv(dotenv_path=ENV_PATH, override=True)

    frm, to = compute_window()
    mode = sys.argv[1].lower() if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "all"

    # Optional overrides
    center_override = _arg_kv("--center")
    after_override  = _arg_kv("--after")  # for notes only

    # NEW: --customers-windowed (default remains full roster for CLI)
    customers_mode = "all"
    if any(a in ("--customers-windowed", "--customers=windowed") for a in sys.argv[1:]):
        customers_mode = "windowed"

    if mode in ("customers", "all"):
        customers = fetch_customers(frm, to, mode=customers_mode, center_code=center_override)
        save_customers_excel(customers, "customers.xlsx")
        update_customer_history()

    if mode in ("payments", "all"):
        payments = fetch_payments(frm, to, center_code=center_override)
        save_payments_excel(payments, "payments.xlsx")
        update_payment_history()

    if mode in ("agenda", "all"):
        agenda = fetch_agenda(frm, to, center_code=center_override)
        save_agenda_excel(agenda, "agenda.xlsx")
        update_agenda_history()

    # ───────────────────────────────────────────────────────────
    # NEW: NOTES
    #   - default cutoff = window start (frm) → pulls "new notes since window start"
    #   - override with: --after=2025-10-01T00:00:00Z (or YYYY-MM-DD)
    #   - output: customer_notes.xlsx + customer_notes_history.xlsx
    # ───────────────────────────────────────────────────────────
    if mode in ("notes", "all"):
        # choose cutoff
        cutoff_iso = after_override or to_iso(frm)
        notes = fetch_customer_notes(cutoff_iso, center_code=center_override)
        _save_notes_excel(notes)
        _update_notes_history(notes)

if __name__ == "__main__":
    run_cli()
