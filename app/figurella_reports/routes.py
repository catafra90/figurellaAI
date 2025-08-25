# app/figurella_reports/routes.py
import os
import json
import re
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional

import pandas as pd
from flask import (
    Blueprint, render_template, send_file,
    redirect, url_for, flash, current_app,
    request, jsonify
)

from app.common.cleaners import drop_unwanted_rows
from app.common.utils import save_report
from build_history import main as build_all_history
from app.models import Report, ReportHistory

# Scrapers (unchanged)
from app.common.scrape_agenda import main as scrape_agenda
from app.common.scrape_contracts import main as scrape_contracts
from app.common.scrape_customer_acquisitions import main as scrape_customer_acquisition
from app.common.scrape_ibf import main as scrape_ibf
from app.common.scrape_last_session import main as scrape_last_session
from app.common.scrape_payments_done import main as scrape_payments_done
from app.common.scrape_payments_due import main as scrape_payments_due
from app.common.scrape_pip import main as scrape_pip
from app.common.scrape_subscriptions import main as scrape_subscriptions

reports_bp = Blueprint(
    'reports_bp', __name__,
    url_prefix='/figurella-reports',
    template_folder='templates/figurella_reports'
)

# Cards (unchanged)
REPORT_CARDS = [
    {"key": "agenda",               "label": "Agenda",               "icon": "bi-calendar"},
    {"key": "contracts",            "label": "Contracts",            "icon": "bi-pen"},
    {"key": "customer_acquisition", "label": "Customer Acquisition", "icon": "bi-people"},
    {"key": "ibf",                  "label": "IBF",                  "icon": "bi-percent"},
    {"key": "last_session",         "label": "Last Session",         "icon": "bi-calendar-check"},
    {"key": "payments_done",        "label": "Payments Done",        "icon": "bi-check-circle"},
    {"key": "payments_due",         "label": "Payments Due",         "icon": "bi-calendar-day"},
    {"key": "pip",                  "label": "PIP",                  "icon": "bi-bank"},
    {"key": "subscriptions",        "label": "Subscriptions",        "icon": "bi-calendar-event"},
]

SCRAPERS = {
    "Agenda":               {"fn": scrape_agenda,               "key": "agenda"},
    "Contracts":            {"fn": scrape_contracts,            "key": "contracts"},
    "Customer Acquisition": {"fn": scrape_customer_acquisition, "key": "customer_acquisition"},
    "IBF":                  {"fn": scrape_ibf,                  "key": "ibf"},
    "Last Session":         {"fn": scrape_last_session,         "key": "last_session"},
    "Payments Done":        {"fn": scrape_payments_done,        "key": "payments_done"},
    "Payments Due":         {"fn": scrape_payments_due,         "key": "payments_due"},
    "PIP":                  {"fn": scrape_pip,                  "key": "pip"},
    "Subscriptions":        {"fn": scrape_subscriptions,        "key": "subscriptions"},
}

HISTORY_FILES = {c['label']: f"history_{c['key']}.xlsx" for c in REPORT_CARDS}

MONTHS_ORDER: List[Tuple[str, str]] = [
    ("Jan", "Jan."), ("Feb", "Feb."), ("Mar", "Mar."), ("Apr", "Apr."),
    ("May", "May"), ("June", "June"), ("July", "July"), ("Aug", "Aug."),
    ("Sept", "Sept."), ("Oct", "Oct."), ("Nov", "Nov."), ("Dec", "Dec.")
]


@reports_bp.app_context_processor
def inject_now():
    return {'now': datetime.utcnow}


# ---------------- Helpers ----------------

def _load_report_df(report_key: str) -> pd.DataFrame:
    """Load latest report data from DB (Report/ReportHistory) into a DataFrame."""
    rpt = Report.query.filter_by(key=report_key).first()
    if not rpt:
        return pd.DataFrame()

    if isinstance(rpt.data, list) and rpt.data:
        records = rpt.data
    else:
        entries = (
            ReportHistory.query
            .filter_by(report_id=rpt.id)
            .order_by(ReportHistory.id.asc())
            .all()
        )
        records = []
        for h in entries:
            raw = h.data
            obj = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(obj, list):
                records.extend(obj)
            else:
                records.append(obj)

    if not records:
        return pd.DataFrame()

    df = pd.json_normalize(records)
    df.drop(columns=['Email', 'Phone'], errors='ignore', inplace=True)
    if '_sheet' in df.columns:
        df.drop(columns=['_sheet'], inplace=True)
    try:
        df = drop_unwanted_rows(df)
    except Exception:
        pass
    return df


def _standardize_ibf_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Return standardized IBF columns: Date, Client, Room, Bubb, Cell, Notes (if present)."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "Client", "Room", "Bubb", "Cell", "Notes"])

    lower_map = {c.lower(): c for c in df.columns}

    def pick(*cands):
        for c in cands:
            if c in df.columns: return c
            lc = c.lower()
            if lc in lower_map: return lower_map[lc]
        return None

    col_map = {
        "Date":   pick("Date", "date"),
        "Client": pick("Client", "client", "Name", "name"),
        "Room":   pick("Room", "room", "Device", "device"),
        "Bubb":   pick("Bubb", "Bubble", "bubble"),
        "Cell":   pick("Cell", "cell"),
        "Notes":  pick("Notes", "notes", "Remark", "remark"),
    }

    out = pd.DataFrame()
    for std, src in col_map.items():
        out[std] = df[src] if (src and src in df.columns) else ""
    return out


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    try:
        d = pd.to_datetime(s, errors="coerce")
        if pd.notna(d):
            return d.date()
    except Exception:
        pass
    return None


def _get_full_name_columns(df: pd.DataFrame) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Determine columns holding the client's name:
    returns (name_col, surname_col, client_col). If client_col is set, it already contains full name.
    Accepts variants like: Name/Surname, First name/Last name, First/Last.
    """
    if df is None or df.empty:
        return (None, None, None)

    cols = list(df.columns)
    lower_map = {c.lower(): c for c in cols}

    # Direct hits first
    client_col = lower_map.get("client") or next((c for c in cols if c.strip().lower() == "client"), None)
    name_col   = lower_map.get("name")   or next((c for c in cols if c.strip().lower() == "name"), None)
    surname_col= lower_map.get("surname")or next((c for c in cols if c.strip().lower() == "surname"), None)

    # Common variants
    if not name_col:
        for key in ("first name", "firstname", "first"):
            if key in lower_map: name_col = lower_map[key]; break
        if not name_col:
            for c in cols:
                lc = c.lower()
                if "first" in lc and "name" in lc:
                    name_col = c; break

    if not surname_col:
        for key in ("last name", "lastname", "last", "family name", "family"):
            if key in lower_map: surname_col = lower_map[key]; break
        if not surname_col:
            for c in cols:
                lc = c.lower()
                if "last" in lc and "name" in lc:
                    surname_col = c; break

    return (name_col, surname_col, client_col)


def _full_from_row(row: pd.Series, name_col: Optional[str], surname_col: Optional[str], client_col: Optional[str]) -> str:
    if client_col and client_col in row:
        return f"{row.get(client_col, '')}".strip()
    first = f"{row.get(name_col, '')}".strip() if name_col else ""
    last  = f"{row.get(surname_col, '')}".strip() if surname_col else ""
    return f"{first} {last}".strip()

def _coerce_dates(series: pd.Series) -> pd.Series:
    """Parse mixed date strings without warnings; returns pandas datetime (NaT on failure)."""
    fmts = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d")
    def _one(x):
        s = str(x).strip()
        if not s:
            return pd.NaT
        for fmt in fmts:
            try:
                return pd.to_datetime(s, format=fmt, errors="raise")
            except Exception:
                continue
        # last resort (handles oddballs)
        return pd.to_datetime(s, errors="coerce")
    return series.map(_one)


# ---------------- Pages ----------------

@reports_bp.route('/reports')
def reports_home():
    return render_template('figurella_reports/reports_home.html', cards=REPORT_CARDS)


@reports_bp.route('/reports/<report_name>/history/view')
def view_history(report_name):
    key = report_name.lower().replace(' ', '_')
    df = _load_report_df(key)
    if df.empty:
        flash(f"No history found for '{report_name}'", 'warning')
        return redirect(url_for('reports_bp.reports_home'))

    if report_name == 'IBF' and len(df) > 1:
        df = df.iloc[1:].reset_index(drop=True)
    if report_name == 'Contracts' and 'Name' in df.columns:
        df = df[df['Name'].astype(str).str.lower() != 'name']

    return render_template(
        'figurella_reports/history_view.html',
        report_name=report_name,
        columns=df.columns.tolist(),
        data=df.fillna('').values.tolist()
    )


@reports_bp.route('/reports/<report_name>/history/download')
def download_history(report_name):
    hist_file = HISTORY_FILES.get(report_name)
    if not hist_file:
        flash(f"Unknown report: {report_name}", 'danger')
        return redirect(url_for('reports_bp.reports_home'))
    project_root = os.path.abspath(os.path.join(current_app.root_path, os.pardir))
    full_path = os.path.join(project_root, hist_file)
    if not os.path.exists(full_path):
        flash(f"No history file for '{report_name}'", 'danger')
        return redirect(url_for('reports_bp.reports_home'))
    return send_file(full_path, as_attachment=True,
                     download_name=f"{report_name.replace(' ', '_')}_history.xlsx")


@reports_bp.route('/reports/refresh_all', methods=['POST'])
def refresh_all_reports():
    errors, total_rows = [], 0
    for card in REPORT_CARDS:
        label, key = card['label'], card['key']
        fn = SCRAPERS[label]['fn']
        try:
            result = fn()
        except Exception as e:
            msg = f"{label!r} scraper failed: {e}"
            current_app.logger.error(msg); errors.append(msg); continue

        if result is None:
            errors.append(f"{label!r} scraper returned None, skipping."); continue
        if isinstance(result, pd.DataFrame):
            section_data = {label: result}
        elif isinstance(result, dict):
            section_data = result
        else:
            errors.append(f"{label!r} returned unexpected type {type(result)}"); continue

        try:
            save_report(section_data, key)
            total_rows += sum(len(df) for df in section_data.values())
        except Exception as e:
            msg = f"{label!r} save_report error: {e}"
            current_app.logger.error(msg); errors.append(msg)

    try:
        build_all_history()
    except Exception as e:
        msg = f"History rebuild failed: {e}"
        current_app.logger.error(msg); errors.append(msg)

    flash(("Some operations failed:\n" + "\n".join(errors)) if errors
          else f"All reports scraped + saved! Total rows: {total_rows}",
          'warning' if errors else 'success')
    return redirect(url_for('reports_bp.reports_home'))


# ------------- JSON: Frequency (supports tidy & wide IBF) -------------

@reports_bp.get("/reports/IBF/frequency")
def ibf_frequency():
    try:
        df_raw = _load_report_df("ibf")
        if df_raw.empty:
            return jsonify({"months": {k: 0 for k, _ in MONTHS_ORDER}})

        cols_lower = {c.lower(): c for c in df_raw.columns}

        # ---------- Shape A (tidy) ----------
        has_tidy = (("date" in cols_lower) and (("bubb" in cols_lower) or ("bubble" in cols_lower)))
        if has_tidy:
            df = _standardize_ibf_cols(df_raw)
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

            client_q = (request.args.get("client") or "").strip().lower()
            start_d  = _parse_date(request.args.get("start"))
            end_d    = _parse_date(request.args.get("end"))

            if client_q and "Client" in df.columns:
                df = df[df["Client"].astype(str).str.lower().str.contains(client_q)]
            if start_d and "Date" in df.columns:
                df = df[df["Date"] >= pd.to_datetime(start_d)]
            if end_d and "Date" in df.columns:
                df = df[df["Date"] <= pd.to_datetime(end_d)]

            if df.empty:
                return jsonify({"months": {k: 0 for k, _ in MONTHS_ORDER}})

            df["Bubb"] = pd.to_numeric(df.get("Bubb", 0), errors="coerce").fillna(0)
            months = pd.to_datetime(df["Date"], errors="coerce").dt.month
            sums = df.groupby(months)["Bubb"].sum().astype(int)

            out = {}
            for idx, (short, _) in enumerate(MONTHS_ORDER, start=1):
                out[short] = int(sums.get(idx, 0))
            return jsonify({"months": out})

        # ---------- Shape B (wide) ----------
        name_col = None
        for cand in ("client", "name", "unnamed: 0", "Unnamed: 0"):
            if cand in cols_lower:
                name_col = cols_lower[cand]; break
        if name_col is None:
            name_col = df_raw.columns[0]

        month_re = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{4})\s*$")
        month_cols = []
        for c in df_raw.columns:
            m = month_re.match(str(c))
            if m:
                month_idx = int(m.group(1)); year_val = int(m.group(2))
                month_cols.append((c, month_idx, year_val))
        if not month_cols:
            return jsonify({"months": {k: 0 for k, _ in MONTHS_ORDER}})

        client_q = (request.args.get("client") or "").strip().lower()
        start_d  = _parse_date(request.args.get("start"))
        end_d    = _parse_date(request.args.get("end"))

        def in_range(year, month):
            if not start_d and not end_d:
                return True
            yyyymm = year * 100 + month
            if start_d and yyyymm < (start_d.year * 100 + start_d.month): return False
            if end_d and yyyymm > (end_d.year * 100 + end_d.month): return False
            return True

        df = df_raw.copy()
        if client_q and name_col in df.columns:
            df = df[df[name_col].astype(str).str.lower().str.contains(client_q)]

        totals_by_month = {i: 0 for i in range(1, 13)}
        val_re = re.compile(r"bubb\s*:\s*(\d+)", re.IGNORECASE)

        for col_name, m_idx, year_val in month_cols:
            if not in_range(year_val, m_idx): continue
            if col_name not in df.columns: continue
            col_vals = df[col_name].astype(str).fillna("")
            bubb_nums = col_vals.apply(lambda s: int(val_re.search(s).group(1)) if val_re.search(s) else 0)
            totals_by_month[m_idx] += int(bubb_nums.sum())

        out = {}
        for idx, (short, _) in enumerate(MONTHS_ORDER, start=1):
            out[short] = int(totals_by_month.get(idx, 0))
        return jsonify({"months": out})

    except Exception as e:
        current_app.logger.exception("ibf_frequency error: %s", e)
        return jsonify({"months": {k: 0 for k, _ in MONTHS_ORDER}})


@reports_bp.get("/reports/IBF/active_clients")
def ibf_active_clients():
    """
    For the given year, return clients 'active' per month (active = Bubb > 1).
    Options:
      - with_bubb=1  -> each item is {name, bubb}
      - with_acq=1   -> also include {new: bool} based on Customer Acquisition month
    """
    try:
        from datetime import date
        target_year = int(request.args.get("year") or date.today().year)
        with_bubb   = (request.args.get("with_bubb") == "1")
        with_acq    = (request.args.get("with_acq") == "1")

        # ---- map: normalized full name -> (year, month) of acquisition ----
        acq_map = {}
        if with_acq:
            df_ca = _load_report_df("customer_acquisition")
            if not df_ca.empty:
                name_col, surname_col, client_col = _get_full_name_columns(df_ca)
                # pick acquisition date column
                acq_col = next(
                    (c for c in df_ca.columns
                     if isinstance(c,str) and ("acquisition" in c.lower() or "first contract" in c.lower())),
                    None
                )
                if acq_col:
                    tmp = pd.DataFrame()
                    tmp["full"] = df_ca.apply(lambda r: _full_from_row(r, name_col, surname_col, client_col), axis=1)
                    tmp["__d"]  = pd.to_datetime(df_ca[acq_col], errors="coerce")
                    tmp = tmp[tmp["full"].astype(str).str.strip().ne("")]
                    tmp = tmp[pd.notna(tmp["__d"])]
                    if not tmp.empty:
                        for _, r in tmp.iterrows():
                            key = _norm_full(r["full"])
                            # keep earliest acquisition we see (just in case of duplicates)
                            y, m = int(r["__d"].year), int(r["__d"].month)
                            if key not in acq_map or (y, m) < acq_map[key]:
                                acq_map[key] = (y, m)

        month_names = (
            "January","February","March","April","May","June",
            "July","August","September","October","November","December"
        )
        months_out = {m: [] for m in month_names}
        out = {"year": target_year, "months": months_out}

        df_raw = _load_report_df("ibf")
        if df_raw.empty:
            return jsonify(out)

        cols_lower = {c.lower(): c for c in df_raw.columns}

        def item_payload(name: str, bubb_val: int, m_idx: int):
            """Compose item with optional bubb + 'new' flag."""
            base = {"name": str(name).strip()}
            if with_bubb:
                base["bubb"] = int(bubb_val)
            if with_acq:
                key = _norm_full(name)
                base["new"] = (key in acq_map and acq_map[key] == (target_year, int(m_idx)))
            return base

        # ---------------- TIDY SHAPE ----------------
        if "date" in cols_lower:
            df = _standardize_ibf_cols(df_raw)  # Date, Client, Bubb, ...
            if not {"Date","Client"}.issubset(df.columns):
                return jsonify(out)

            df["__d"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df[pd.notna(df["__d"])]
            df = df[df["__d"].dt.year == target_year]
            df["Client"] = df["Client"].astype(str).str.strip()
            df = df[df["Client"].ne("")]

            # numeric bubb
            df["__b"] = pd.to_numeric(df.get("Bubb", 0), errors="coerce").fillna(0)
            df["__m"] = df["__d"].dt.month

            # sum bubb per (client, month)
            grp = df.groupby(["Client","__m"], as_index=False)["__b"].sum()

            for m_idx in range(1, 13):
                g = grp[(grp["__m"] == m_idx) & (grp["__b"] > 1)]
                g = g.sort_values(["Client"])
                if with_bubb or with_acq:
                    months_out[month_names[m_idx-1]] = [
                        item_payload(n, b, m_idx) for n, b in zip(g["Client"], g["__b"])
                    ]
                else:
                    months_out[month_names[m_idx-1]] = g["Client"].drop_duplicates().tolist()
            return jsonify(out)

        # ---------------- WIDE SHAPE ----------------
        import re
        name_col = (cols_lower.get("client") or cols_lower.get("name") or
                    cols_lower.get("unnamed: 0") or cols_lower.get("unnamed:0") or df_raw.columns[0])

        month_re = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{4})\s*$")
        bubb_re  = re.compile(r"bubb\s*[:=]\s*(\d+)", re.IGNORECASE)

        month_cols = []
        for c in df_raw.columns:
            m = month_re.match(str(c))
            if m and int(m.group(2)) == target_year:
                month_cols.append((c, int(m.group(1))))
        if not month_cols:
            return jsonify(out)

        df = df_raw.copy()
        df[name_col] = df[name_col].astype(str).str.strip()
        df = df[df[name_col].ne("")]

        for col, m_idx in month_cols:
            if col not in df.columns:
                continue
            s = df[col].astype(str).fillna("")
            def bubb_val(txt: str) -> int:
                m = bubb_re.search(txt)
                if not m: return 0
                try: return int(m.group(1))
                except: return 0
            vals = s.map(bubb_val)
            mask = vals > 1
            names = df.loc[mask, name_col].astype(str).str.strip()
            if with_bubb or with_acq:
                items = [
                    item_payload(n, int(vals.iloc[i_row]), m_idx)
                    for i_row, n in zip(names.index, names.values)
                ]
                items.sort(key=lambda x: x["name"])
                months_out[month_names[m_idx-1]] = items
            else:
                months_out[month_names[m_idx-1]] = sorted(set(names.values))

        return jsonify(out)

    except Exception as e:
        current_app.logger.exception("ibf_active_clients error: %s", e)
        month_names = (
            "January","February","March","April","May","June",
            "July","August","September","October","November","December"
        )
        return jsonify({"year": int(request.args.get("year") or 0),
                        "months": {m: [] for m in month_names},
                        "error": "Server error"}), 200



# ------------- JSON: client suggestions -------------

@reports_bp.get("/reports/IBF/clients")
def ibf_clients():
    try:
        df_raw = _load_report_df("ibf")
        if df_raw.empty:
            return jsonify({"clients": []})

        cols_lower = {c.lower(): c for c in df_raw.columns}
        name_col = None
        for cand in ("Client", "client", "Name", "name", "Unnamed: 0", "unnamed: 0"):
            if cand in df_raw.columns:
                name_col = cand; break
            if cand.lower() in cols_lower:
                name_col = cols_lower[cand.lower()]; break
        if name_col is None:
            name_col = df_raw.columns[0]

        names = (df_raw[name_col].astype(str).fillna("").map(lambda s: s.strip()))
        names = names[names.str.lower().ne("name") & names.ne("")]
        unique = sorted(set(names))

        q = (request.args.get("q") or "").strip().lower()
        if q:
            unique = [n for n in unique if q in n.lower()]

        return jsonify({"clients": unique[:50]})
    except Exception as e:
        current_app.logger.exception("ibf_clients error: %s", e)
        return jsonify({"clients": []})


# ===================== Contracts / Last Session helpers =====================

def _latest_contracts(df_contracts: pd.DataFrame) -> pd.DataFrame:
    """
    From Contracts report, compute each client's latest contract row.
    """
    if df_contracts is None or df_contracts.empty:
        return pd.DataFrame(columns=["full", "date", "details"])

    name_col, surname_col, client_col = _get_full_name_columns(df_contracts)
    date_col = next((c for c in df_contracts.columns if "date" in c.lower()), None)
    details_col = next((c for c in df_contracts.columns if "detail" in c.lower()), None)

    out = pd.DataFrame()
    out["full"] = df_contracts.apply(lambda r: _full_from_row(r, name_col, surname_col, client_col), axis=1)
    out["date"] = pd.to_datetime(df_contracts[date_col], errors="coerce") if date_col else pd.NaT
    out["details"] = df_contracts[details_col] if details_col else ""
    out = out[out["full"].astype(str).str.strip().ne("")]
    out = out.sort_values("date").groupby("full", as_index=False).tail(1).reset_index(drop=True)
    return out


def _pick_expiration_col(df_last: pd.DataFrame) -> Optional[str]:
    """Find the column in Last Session that contains the contract expiration date."""
    if df_last is None or df_last.empty:
        return None
    for pref in ("Expiration", "Contract Expiration", "Contract Expires", "Expire", "Expiration Date"):
        if pref in df_last.columns:
            return pref
    for c in df_last.columns:
        if "expir" in c.lower():
            return c
    return None

from calendar import monthrange  # ensure this is in your imports

def _norm_full(s: str) -> str:
    import re as _re
    return _re.sub(r"\s+", " ", (s or "")).strip().casefold()


# ===================== Subscriptions helpers (wide + tidy) =====================

RESIDUAL_RE   = re.compile(r"(?:residual|residuo)\s*[:=]\s*(\d+)", re.IGNORECASE)
MONTH_HDR_RE  = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{4})\s*$")  # e.g., "8 - 2025"
DATE_RE       = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")  # MM/DD/YYYY (best effort)

def _parse_last_residual_text(s: str) -> Optional[int]:
    """Return the RIGHT-MOST residual value inside a text cell."""
    if not isinstance(s, str):
        return None
    last = None
    for m in RESIDUAL_RE.finditer(s):
        try:
            last = int(m.group(1))
        except Exception:
            continue
    return last

def _pick_name_col(df: pd.DataFrame, cols: List) -> str:
    lower_map = {c.lower(): c for c in cols if isinstance(c, str)}
    for cand in ("client", "name", "unnamed: 0", "unnamed:0", ""):
        if cand in lower_map:
            return lower_map[cand]
        if cand == "" and "" in df.columns:
            return ""
    return cols[0]

def _pick_text_col(df: pd.DataFrame, cols: List) -> Optional[str]:
    """Choose a 'Contracts'/'Details'/'Notes' style column if present."""
    for key in ("contracts", "contract", "details", "detail", "notes", "note"):
        for c in cols:
            if isinstance(c, str) and key in c.lower():
                return c
    return None

def _latest_subscriptions(df_subs: pd.DataFrame) -> pd.DataFrame:
    """
    Return each client's latest subscription entry with parsed residual.
    Handles:
      - Wide: first column is client; monthly columns named "M - YYYY"
              If month cells lack residuals, falls back to 'Contracts' text (right-most residual).
      - Tidy: has a Date column + a text column containing "residual: N"
    Output columns: full, date, residual
    """
    if df_subs is None or df_subs.empty:
        return pd.DataFrame(columns=["full", "date", "residual"])

    cols = list(df_subs.columns)

    # Detect wide by scanning month-like headers
    month_cols = []
    for c in cols:
        m = MONTH_HDR_RE.match(str(c))
        if m:
            month_cols.append((c, int(m.group(2)), int(m.group(1))))  # (col, year, month)

    if month_cols:
        # ---------- WIDE ----------
        name_col = _pick_name_col(df_subs, cols)
        txt_col  = _pick_text_col(df_subs, cols)

        month_cols.sort(key=lambda t: (t[1], t[2]))  # (year, month) asc

        rows = []
        for _, r in df_subs.iterrows():
            full = str(r.get(name_col, "")).strip()
            if not full:
                continue

            latest_date = None
            latest_res  = None

            # 1) Prefer the newest month column that contains residual text (if any)
            for col, y, m in reversed(month_cols):
                if col not in df_subs.columns:
                    continue
                cell = r.get(col, "")
                res  = _parse_last_residual_text(str(cell))
                if res is not None:
                    from calendar import monthrange as _mr
                    d = date(y, m, _mr(y, m)[1])  # end-of-month proxy
                    latest_date = d
                    latest_res  = res
                    break

            # 2) Fallback: parse RIGHT-MOST residual from 'Contracts'/'Details' text
            if latest_res is None and txt_col:
                txt = str(r.get(txt_col, "") or "")
                res = _parse_last_residual_text(txt)
                if res is not None:
                    # Try to infer a date: pick the right-most MM/DD/YYYY in the same text
                    last_date = None
                    for dm in DATE_RE.finditer(txt):
                        mm, dd, yyyy = map(int, dm.groups())
                        try:
                            last_date = date(yyyy, mm, dd)
                        except Exception:
                            continue
                    latest_date = last_date  # may be None; OK for our use
                    latest_res  = res

            rows.append({"full": full, "date": latest_date, "residual": latest_res})

        out = pd.DataFrame(rows)
        out = out.dropna(subset=["residual"])  # date may be NaT; residual required
        if "date" in out.columns:
            out["date"] = pd.to_datetime(out["date"], errors="coerce")
        return out.reset_index(drop=True)

    # ---------- TIDY ----------
    name_col, surname_col, client_col = _get_full_name_columns(df_subs)
    date_col = next((c for c in cols if isinstance(c, str) and "date" in c.lower()), None)
    text_col = _pick_text_col(df_subs, cols)

    def tidy_row_residual(row: pd.Series) -> Optional[int]:
        if text_col:
            return _parse_last_residual_text(str(row.get(text_col, "")))
        # fallback: scan all text cells, keep RIGHT-MOST across the row
        last = None
        for v in row.values:
            if isinstance(v, str):
                val = _parse_last_residual_text(v)
                if val is not None:
                    last = val
        return last

    out = pd.DataFrame()
    out["full"] = df_subs.apply(lambda r: _full_from_row(r, name_col, surname_col, client_col), axis=1)
    out["date"] = pd.to_datetime(df_subs[date_col], errors="coerce") if date_col else pd.NaT
    out["residual"] = df_subs.apply(tidy_row_residual, axis=1)

    out = out[out["full"].astype(str).str.strip().ne("")]
    out = out.sort_values("date").groupby("full", as_index=False).tail(1).reset_index(drop=True)
    return out







CURRENCY_RE = re.compile(r"[-+]?\d+(?:[.,]\d{3})*(?:[.,]\d{2})?")

def _to_number(val) -> float:
    """Best-effort currency/number parser: '$1,234.56' -> 1234.56."""
    if pd.isna(val):
        return 0.0
    s = str(val).strip()
    if not s:
        return 0.0
    # pull the last number-looking token from the string
    m = None
    for m in CURRENCY_RE.finditer(s):
        pass
    if not m:
        # also try simple strip of non-digits
        s2 = re.sub(r"[^\d\.\-]", "", s)
        try:
            return float(s2) if s2 else 0.0
        except Exception:
            return 0.0
    token = m.group(0)
    # normalize 1.234,56 vs 1,234.56
    if token.count(",") > 0 and token.count(".") == 0:
        token = token.replace(".", "").replace(",", ".")
    else:
        token = token.replace(",", "")
    try:
        return float(token)
    except Exception:
        return 0.0











# ===================== NEW: Expiring PINK clients =====================

@reports_bp.get("/reports/expiring_pink")
def expiring_pink():
    """
    Clients whose latest contract is PINK and whose expiration is in THIS month.
    Pass ?all=1 to skip the month filter, or ?debug=1 for diagnostics.
    Optional: ?year=YYYY&month=MM (defaults to current month).
    """
    try:
        today = date.today()
        year  = int(request.args.get("year") or today.year)
        month = int(request.args.get("month") or today.month)
        skip_month = (request.args.get("all") == "1")
        debug      = (request.args.get("debug") == "1")

        out_meta = {}

        # ---------- Contracts: latest row per client, filter PINK ----------
        df_contracts = _load_report_df("contracts")
        latest = _latest_contracts(df_contracts)
        if latest.empty:
            out = {"clients": []}
            if debug:
                out_meta.update({
                    "contracts_empty": True,
                    "contracts_cols": list(df_contracts.columns) if df_contracts is not None else []
                })
                out["meta"] = out_meta
            return jsonify(out)

        details_col = "details"
        mask_pink   = latest[details_col].astype(str).str.contains(r"\bpink\b", case=False, na=False)
        latest_pink = latest.loc[mask_pink].copy()

        latest_pink["full_norm"] = latest_pink["full"].map(_norm_full)
        pink_set = set(latest_pink["full_norm"])

        # ---------- Last Session ----------
        df_last = _load_report_df("last_session")
        if debug:
            out_meta.update({
                "contracts_rows": int(len(df_contracts) if df_contracts is not None else 0),
                "contracts_latest_rows": int(len(latest)),
                "contracts_latest_pink_rows": int(len(latest_pink)),
                "contracts_cols": list(df_contracts.columns) if df_contracts is not None else [],
                "last_session_cols": list(df_last.columns) if df_last is not None else []
            })

        if df_last.empty or not pink_set:
            return jsonify({"clients": [], "meta": out_meta} if debug else {"clients": []})

        name_col, surname_col, client_col = _get_full_name_columns(df_last)
        exp_col = _pick_expiration_col(df_last)
        if exp_col is None:
            if debug:
                out_meta["exp_col"] = None
                return jsonify({"clients": [], "meta": out_meta})
            return jsonify({"clients": []})

        df_last = df_last.copy()
        df_last["full"]      = df_last.apply(lambda r: _full_from_row(r, name_col, surname_col, client_col), axis=1)
        df_last["full_norm"] = df_last["full"].map(_norm_full)
        df_last["exp"]       = pd.to_datetime(df_last[exp_col], errors="coerce")
        df_last = df_last[df_last["full_norm"].ne("")]
        df_last = df_last[df_last["full_norm"].isin(pink_set)]
        df_last = df_last.dropna(subset=["exp"])
        if df_last.empty:
            return jsonify({"clients": [], "meta": out_meta} if debug else {"clients": []})

        # Most recent expiration per client
        df_last = df_last.sort_values("exp").groupby("full_norm", as_index=False).tail(1)

        # ----- EXACT month only -----
        if not skip_month:
            start = date(year, month, 1)
            end   = date(year, month, monthrange(year, month)[1])
            df_last = df_last[
                (df_last["exp"] >= pd.to_datetime(start)) &
                (df_last["exp"] <= pd.to_datetime(end))
            ]

        payload = [
            {"name": str(row["full"]).strip(), "expiration": row["exp"].date().isoformat()}
            for _, row in df_last.iterrows()
        ]

        if debug:
            out_meta.update({
                "exp_col": exp_col,
                "window_start": None if skip_month else start.isoformat(),
                "window_end":   None if skip_month else end.isoformat(),
                "result_count": len(payload),
                "sample_contracts_latest_pink": latest_pink.head(3).to_dict(orient="records"),
                "sample_last_session_filtered": df_last.head(3)[["full","exp"]].to_dict(orient="records")
            })
            return jsonify({"clients": payload, "meta": out_meta})

        return jsonify({"clients": payload})

    except Exception as e:
        current_app.logger.exception("expiring_pink error: %s", e)
        return jsonify({"clients": [], "error": str(e)}), 200


# ===================== NEW: Subscriptions low residual =====================

@reports_bp.get("/reports/subscriptions/low_residual")
def subscriptions_low_residual():
    """
    Clients whose latest subscription row has residual < threshold (default 10).
    Query:
      - threshold=INT (default 10)
      - debug=1 for diagnostics
    Response:
      { "clients": [ {"name": "...", "residual": 7}, ... ] }
    """
    try:
        debug = (request.args.get("debug") == "1")
        try:
            threshold = int(request.args.get("threshold") or 10)
        except Exception:
            threshold = 10

        df_subs = _load_report_df("subscriptions")
        out_meta = {}
        if df_subs.empty:
            return jsonify({"clients": [], "meta": out_meta} if debug else {"clients": []})

        latest = _latest_subscriptions(df_subs)
        latest = latest.dropna(subset=["residual"])
        latest = latest[latest["residual"].astype(int) < int(threshold)]

        payload = [
            {"name": str(row["full"]).strip(), "residual": int(row["residual"])}
            for _, row in latest.iterrows()
        ]

        if debug:
            out_meta.update({
                "threshold": threshold,
                "subs_cols": list(df_subs.columns),
                "result_count": len(payload),
                "sample_latest": latest.head(5)[["full","date","residual"]].to_dict(orient="records"),
            })
            return jsonify({"clients": payload, "meta": out_meta})

        return jsonify({"clients": payload})
    except Exception as e:
        current_app.logger.exception("subscriptions_low_residual error: %s", e)
        return jsonify({"clients": [], "error": str(e)}), 200


@reports_bp.get("/reports/payments_due/total")
def payments_due_total():
    """
    Sum of Payments Due for the given month (defaults to current).
    Query (optional):
      - year=YYYY
      - month=MM   (1..12)
      - debug=1    (include meta)
    Returns:
      { "ok": true, "total": 1234.56, "count": 17 } (+ "meta" if debug)
    """
    try:
        today = date.today()
        year  = int(request.args.get("year") or today.year)
        month = int(request.args.get("month") or today.month)
        debug = (request.args.get("debug") == "1")

        df = _load_report_df("payments_due")
        meta = {"year": year, "month": month, "mode": None, "notes": []}

        if df.empty:
            out = {"ok": True, "total": 0.0, "count": 0}
            if debug: out["meta"] = meta | {"columns": []}
            return jsonify(out)

        cols = list(df.columns)
        meta["columns"] = cols

        # ---------- helpers ----------
        month_re = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{4})\s*$")  # "8 - 2025"
        currency_re = re.compile(r"[-+]?\d+(?:[.,]\d{3})*(?:[.,]\d{2})?")

        def to_number(val) -> float:
            if pd.isna(val): return 0.0
            s = str(val).strip()
            if not s: return 0.0
            # take the LAST number-looking token (right-most)
            last = None
            for m in currency_re.finditer(s):
                last = m.group(0)
            if last is None:
                s2 = re.sub(r"[^\d\.\-]", "", s)
                try: return float(s2) if s2 else 0.0
                except: return 0.0
            token = last
            # normalize 1.234,56 vs 1,234.56
            if token.count(",") > 0 and token.count(".") == 0:
                token = token.replace(".", "").replace(",", ".")
            else:
                token = token.replace(",", "")
            try: return float(token)
            except: return 0.0

        # ---------- detect wide vs tidy ----------
        month_cols = []
        for c in cols:
            m = month_re.match(str(c))
            if m:
                month_cols.append((c, int(m.group(2)), int(m.group(1))))  # (col, year, month)

        total = 0.0
        row_count = 0

        if month_cols:
            # ---------- WIDE ----------
            meta["mode"] = "wide"
            month_cols.sort(key=lambda t: (t[1], t[2]))
            # try exact header "M - YYYY"
            target_hdr = f"{month} - {year}"
            target_col = next((c for c, y, m in month_cols if str(c).strip() == target_hdr), None)
            # or match by year/month pair
            if not target_col:
                for c, y, m in month_cols:
                    if y == year and m == month:
                        target_col = c
                        break
            if not target_col or target_col not in df.columns:
                meta["notes"].append("target month column not found")
            else:
                series = df[target_col]
                nums = series.map(to_number)
                total = float(nums.sum())
                row_count = int((nums != 0).sum())

                # If all zeros, some sheets keep the money in a text column; fallback parse
                if total == 0.0:
                    # look for an amount-ish column among non-month columns
                    non_month_cols = {c for c in cols if not month_re.match(str(c))}
                    amount_guess = next(
                        (c for c in non_month_cols if isinstance(c, str)
                         and any(k in c.lower() for k in
                                 ("amount","due","balance","outstanding","total","value","importo","payment"))),
                        None
                    )
                    if amount_guess and amount_guess in df.columns:
                        nums2 = df[amount_guess].map(to_number)
                        total = float(nums2.sum())
                        row_count = int((nums2 != 0).sum())
                        meta["notes"].append(f"fallback amount column: {amount_guess}")
                    else:
                        # brute force: parse numbers from every object column and take the max per row
                        candidates = []
                        for c in cols:
                            if df[c].dtype == object:
                                candidates.append(df[c].map(to_number))
                        if candidates:
                            stacked = pd.concat(candidates, axis=1)
                            perrow = stacked.max(axis=1, skipna=True)
                            total = float(perrow.sum())
                            row_count = int((perrow != 0).sum())
                            meta["notes"].append("fallback parsed all text columns (max per row)")
        else:
            # ---------- TIDY ----------
            meta["mode"] = "tidy"
            lower_map = {c.lower(): c for c in cols if isinstance(c, str)}
            date_col = next((c for c in cols if isinstance(c, str) and "date" in c.lower()), None)
            amt_col  = (lower_map.get("amount")
                        or next((c for c in cols if isinstance(c, str) and any(k in c.lower() for k in
                                ("amount","due","balance","outstanding","total","value","importo","payment"))), None))

            dff = df.copy()
            if date_col and date_col in dff.columns:
                dff["__d"] = _coerce_dates(dff[date_col])

                dff = dff[(dff["__d"].dt.year == year) & (dff["__d"].dt.month == month)]
            else:
                meta["notes"].append("no date column; not filtering by month")

            if amt_col and amt_col in dff.columns:
                nums = dff[amt_col].map(to_number)
                total = float(nums.sum())
                row_count = int((nums != 0).sum())
            else:
                # parse any text-like column
                text_cols = [c for c in dff.columns if dff[c].dtype == object]
                if text_cols:
                    stacked = pd.concat([dff[c].map(to_number) for c in text_cols], axis=1)
                    perrow  = stacked.max(axis=1, skipna=True)
                    total   = float(perrow.sum())
                    row_count = int((perrow != 0).sum())
                    meta["notes"].append("parsed all text columns (max per row)")

        out = {"ok": True, "total": round(total, 2), "count": int(row_count)}
        if debug: out["meta"] = meta
        return jsonify(out)

    except Exception as e:
        current_app.logger.exception("payments_due_total error: %s", e)
        # Never crash the front-end: always send JSON
        return jsonify({"ok": False, "error": "Server error"}), 200

@reports_bp.get("/reports/payments_done/total")
def payments_done_total():
    """
    Sum of Payments Done for the given month (defaults to current).
    Query (optional):
      - year=YYYY
      - month=MM   (1..12)
      - debug=1    (include meta)
    Returns:
      { "ok": true, "total": 1234.56, "count": 17 } (+ "meta" if debug)
    """
    try:
        today = date.today()
        year  = int(request.args.get("year") or today.year)
        month = int(request.args.get("month") or today.month)
        debug = (request.args.get("debug") == "1")

        df = _load_report_df("payments_done")
        meta = {"year": year, "month": month, "mode": None, "notes": []}

        if df.empty:
            out = {"ok": True, "total": 0.0, "count": 0}
            if debug:
                out["meta"] = meta | {"columns": []}
            return jsonify(out)

        cols = list(df.columns)
        meta["columns"] = cols

        # ---------- helpers ----------
        month_re    = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{4})\s*$")  # "8 - 2025"
        currency_re = re.compile(r"[-+]?\d+(?:[.,]\d{3})*(?:[.,]\d{2})?")

        def to_number(val) -> float:
            if pd.isna(val):
                return 0.0
            s = str(val).strip()
            if not s:
                return 0.0
            last = None
            for m in currency_re.finditer(s):  # take RIGHT-MOST number-ish token
                last = m.group(0)
            if last is None:
                s2 = re.sub(r"[^\d\.\-]", "", s)
                try:
                    return float(s2) if s2 else 0.0
                except Exception:
                    return 0.0
            token = last
            # normalize 1.234,56 vs 1,234.56
            if token.count(",") > 0 and token.count(".") == 0:
                token = token.replace(".", "").replace(",", ".")
            else:
                token = token.replace(",", "")
            try:
                return float(token)
            except Exception:
                return 0.0

        # ---------- detect wide vs tidy ----------
        month_cols = []
        for c in cols:
            m = month_re.match(str(c))
            if m:
                month_cols.append((c, int(m.group(2)), int(m.group(1))))  # (col, year, month)

        total = 0.0
        row_count = 0

        if month_cols:
            # ---------- WIDE ----------
            meta["mode"] = "wide"
            month_cols.sort(key=lambda t: (t[1], t[2]))
            target_hdr = f"{month} - {year}"
            target_col = next((c for c, y, m in month_cols if str(c).strip() == target_hdr), None)
            if not target_col:
                for c, y, m in month_cols:
                    if y == year and m == month:
                        target_col = c
                        break
            if not target_col or target_col not in df.columns:
                meta["notes"].append("target month column not found")
            else:
                nums = df[target_col].map(to_number)
                total = float(nums.sum())
                row_count = int((nums != 0).sum())

                if total == 0.0:
                    non_month_cols = [c for c in cols if not month_re.match(str(c))]
                    amount_guess = next(
                        (
                            c for c in non_month_cols
                            if isinstance(c, str)
                            and any(k in c.lower() for k in ("amount", "paid", "payment", "total", "value", "importo", "done"))
                        ),
                        None,
                    )
                    if amount_guess and amount_guess in df.columns:
                        nums2 = df[amount_guess].map(to_number)
                        total = float(nums2.sum())
                        row_count = int((nums2 != 0).sum())
                        meta["notes"].append(f"fallback amount column: {amount_guess}")
                    else:
                        candidates = [df[c].map(to_number) for c in cols if df[c].dtype == object]
                        if candidates:
                            stacked = pd.concat(candidates, axis=1)
                            perrow  = stacked.max(axis=1, skipna=True)
                            total   = float(perrow.sum())
                            row_count = int((perrow != 0).sum())
                            meta["notes"].append("fallback parsed all text columns (max per row)")
        else:
            # ---------- TIDY ----------
            meta["mode"] = "tidy"

            # Prefer 'Expected' if present; else any '...date...' column.
            def pick_date_col(columns):
                lower = {c.lower(): c for c in columns if isinstance(c, str)}
                for cand in ("expected", "expected date", "payment date"):
                    if cand in lower:
                        return lower[cand]
                for c in columns:
                    if isinstance(c, str) and "date" in c.lower():
                        return c
                return None

            date_col = pick_date_col(cols)

            lower_map = {c.lower(): c for c in cols if isinstance(c, str)}
            amt_col = (
                lower_map.get("amount")
                or next(
                    (
                        c for c in cols
                        if isinstance(c, str)
                        and any(k in c.lower() for k in ("amount", "paid", "payment", "total", "value", "importo", "done"))
                    ),
                    None,
                )
            )

            dff = df.copy()
            if date_col and date_col in dff.columns:
                dff["__d"] = _coerce_dates(dff[date_col])
                dff = dff[(dff["__d"].dt.year == year) & (dff["__d"].dt.month == month)]
            else:
                meta["notes"].append("no date column; not filtering by month")

            if amt_col and amt_col in dff.columns:
                nums = dff[amt_col].map(to_number)
                total = float(nums.sum())
                row_count = int((nums != 0).sum())
            else:
                text_cols = [c for c in dff.columns if dff[c].dtype == object]
                if text_cols:
                    stacked = pd.concat([dff[c].map(to_number) for c in text_cols], axis=1)
                    perrow  = stacked.max(axis=1, skipna=True)
                    total   = float(perrow.sum())
                    row_count = int((perrow != 0).sum())
                    meta["notes"].append("parsed all text columns (max per row)")

        out = {"ok": True, "total": round(total, 2), "count": int(row_count)}
        if debug:
            out["meta"] = meta
        return jsonify(out)

    except Exception as e:
        current_app.logger.exception("payments_done_total error: %s", e)
        return jsonify({"ok": False, "error": "Server error"}), 200



@reports_bp.get("/reports/contracts/sales_total")
def contracts_sales_total():
    """
    Sum of contract values for contracts done in the given month (defaults to current).
    Query (optional):
      - year=YYYY
      - month=MM
      - debug=1
    Returns:
      { "ok": true, "total": 1234.56, "count": 5 }
    """
    try:
        today = date.today()
        year  = int(request.args.get("year") or today.year)
        month = int(request.args.get("month") or today.month)
        debug = (request.args.get("debug") == "1")

        df = _load_report_df("contracts")
        meta = {"year": year, "month": month, "notes": []}

        if df.empty:
            out = {"ok": True, "total": 0.0, "count": 0}
            if debug: out["meta"] = meta
            return jsonify(out)

        cols = list(df.columns)

        # ---- helpers ----
        def to_number(val) -> float:
            if pd.isna(val): return 0.0
            s = str(val).strip()
            if not s: return 0.0
            m = None
            for m in re.finditer(r"[-+]?\d+(?:[.,]\d{3})*(?:[.,]\d{2})?", s):
                pass
            if not m:
                s2 = re.sub(r"[^\d\.\-]", "", s)
                try: return float(s2) if s2 else 0.0
                except: return 0.0
            token = m.group(0)
            if token.count(",") > 0 and token.count(".") == 0:
                token = token.replace(".", "").replace(",", ".")
            else:
                token = token.replace(",", "")
            try: return float(token)
            except: return 0.0

        # ---- pick columns ----
        date_col = next((c for c in cols if isinstance(c,str) and "date" in c.lower()), None)
        amt_col  = next((c for c in cols if isinstance(c,str) and any(k in c.lower() for k in ("amount","value","price","total","importo"))), None)

        dff = df.copy()
        if date_col and date_col in dff.columns:
            dff["__d"] = _coerce_dates(dff[date_col])

            dff = dff[(dff["__d"].dt.year == year) & (dff["__d"].dt.month == month)]
        else:
            meta["notes"].append("no date column found")

        total = 0.0
        row_count = 0
        if amt_col and amt_col in dff.columns:
            nums = dff[amt_col].map(to_number)
            total = float(nums.sum())
            row_count = int((nums != 0).sum())
        else:
            text_cols = [c for c in dff.columns if dff[c].dtype == object]
            if text_cols:
                stacked = pd.concat([dff[c].map(to_number) for c in text_cols], axis=1)
                perrow = stacked.max(axis=1, skipna=True)
                total = float(perrow.sum())
                row_count = int((perrow != 0).sum())
                meta["notes"].append("parsed all text columns")

        out = {"ok": True, "total": round(total,2), "count": row_count}
        if debug: out["meta"] = meta
        return jsonify(out)

    except Exception as e:
        current_app.logger.exception("contracts_sales_total error: %s", e)
        return jsonify({"ok": False, "error": "Server error"}), 200
