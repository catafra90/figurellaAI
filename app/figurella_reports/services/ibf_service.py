import re
from datetime import date
import pandas as pd

from ..io.loader import load_df

# ---------- small helpers ----------
def _lower_map(df: pd.DataFrame):
    return {str(c).strip().lower(): c for c in df.columns}

def _pick(df: pd.DataFrame, *cands: str):
    lower = _lower_map(df)
    for c in cands:
        if c in df.columns:
            return c
        lc = str(c).strip().lower()
        if lc in lower:
            return lower[lc]
    return None

def _standardize_tidy(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize to columns: Date, Client, Bubb, Cell (+ optional: Bubble, Cellushape, Date Start First/Last Contract).
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date","Client","Bubb","Cell",
                                     "Date Start First Contract","Date Start Last Contract","Bubble","Cellushape"])
    date_col   = _pick(df, "Date","date","Data")
    client_col = _pick(df, "Client","client","Name","name","Cliente")
    bubb_col   = _pick(df, "Bubb","Bubble","bubble")
    cell_col   = _pick(df, "Cell","cell","Cellushape","CelluShape")

    dfirst_col = _pick(df, "Date Start First Contract","first contract start date","data inizio primo contratto")
    dlast_col  = _pick(df, "Date Start Last Contract","last contract start date","data inizio ultimo contratto")
    btot_col   = _pick(df, "Bubble","bubble total","bubb total","bolla")
    ctot_col   = _pick(df, "Cellushape","cellu shape","cell total","cellushape total","cell")

    out = pd.DataFrame()
    out["Date"] = pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.NaT
    if client_col:
        out["Client"] = df[client_col].astype(str).str.strip()
    else:
        f = _pick(df, "First name","First","Nome","firstname")
        l = _pick(df, "Last name","Last","Cognome","surname","lastname")
        out["Client"] = (
            df[f].astype(str) if f else ""
        ).fillna("").str.strip() + " " + (
            df[l].astype(str) if l else ""
        ).fillna("").str.strip()
        out["Client"] = out["Client"].str.replace(r"\s+"," ",regex=True).str.strip()

    out["Bubb"] = pd.to_numeric(df[bubb_col], errors="coerce").fillna(0.0) if bubb_col else 0.0
    out["Cell"] = pd.to_numeric(df[cell_col], errors="coerce").fillna(0.0) if cell_col else 0.0

    out["Date Start First Contract"] = (df[dfirst_col].astype(str) if dfirst_col else "")
    out["Date Start Last Contract"]  = (df[dlast_col].astype(str)  if dlast_col  else "")
    out["Bubble"]     = pd.to_numeric(df[btot_col], errors="coerce") if btot_col else pd.NA
    out["Cellushape"] = pd.to_numeric(df[ctot_col], errors="coerce") if ctot_col else pd.NA
    return out

def _contracts_first_last() -> pd.DataFrame:
    """
    From Contracts report, derive per-client first/last start dates if the portal columns exist.
    """
    df = load_df("contracts")
    if df.empty:
        return pd.DataFrame(columns=["Client","first_start","last_start"])
    name = _pick(df, "Client","client","Name","name")
    if not name:
        f = _pick(df, "First name","First","Nome")
        l = _pick(df, "Last name","Last","Cognome")
        if not f and not l:
            return pd.DataFrame(columns=["Client","first_start","last_start"])
        full = (df[f].astype(str).fillna("").str.strip() if f else "") + " " + \
               (df[l].astype(str).fillna("").str.strip() if l else "")
        df = df.assign(Client=full.str.replace(r"\s+"," ",regex=True).str.strip())
    else:
        df = df.rename(columns={name: "Client"})
    cfirst = _pick(df, "Date Start First Contract","first contract start date","data inizio primo contratto")
    clast  = _pick(df, "Date Start Last Contract","last contract start date","data inizio ultimo contratto")
    if not cfirst and not clast:
        return pd.DataFrame(columns=["Client","first_start","last_start"])
    first = pd.to_datetime(df[cfirst], errors="coerce") if cfirst else pd.NaT
    last  = pd.to_datetime(df[clast],  errors="coerce") if clast  else pd.NaT
    g = df.assign(_f=first, _l=last).groupby("Client", as_index=False).agg(first_start=("_f","min"),
                                                                           last_start =("_l","max"))
    g["first_start"] = g["first_start"].dt.strftime("%m/%d/%Y")
    g["last_start"]  = g["last_start"].dt.strftime("%m/%d/%Y")
    return g

# ---------- main builder ----------
def build_portal_wide(from_ym: str | None = None, to_ym: str | None = None) -> pd.DataFrame:
    """
    Return a DataFrame shaped like the portal:
      Client | <mm - yyyy> ... | Date Start First Contract | Date Start Last Contract | Bubble | Cellushape
    - Accepts optional date range filters as 'YYYY-MM' (inclusive).
    - Works with 'tidy' IBF or already-wide IBF.
    """
    df_raw = load_df("ibf")
    if df_raw.empty:
        return pd.DataFrame(columns=["Client"])

    cols_lower = _lower_map(df_raw)
    is_tidy = ("date" in cols_lower or "data" in cols_lower) and ("bubb" in cols_lower or "bubble" in cols_lower)

    # Optional range
    def in_range(dt: pd.Timestamp) -> bool:
        if pd.isna(dt): return False
        if from_ym:
            y, m = map(int, from_ym.split("-"))
            if (dt.year, dt.month) < (y, m): return False
        if to_ym:
            y, m = map(int, to_ym.split("-"))
            if (dt.year, dt.month) > (y, m): return False
        return True

    if is_tidy:
        df = _standardize_tidy(df_raw)
        df = df[(df["Client"].astype(str).str.strip() != "") & (df["Date"].notna())]
        if from_ym or to_ym:
            df = df[df["Date"].map(in_range)]
        if df.empty:
            return pd.DataFrame(columns=["Client"])

        # month label "m - yyyy"
        df["monlbl"] = df["Date"].dt.month.astype(int).astype(str) + " - " + df["Date"].dt.year.astype(int).astype(str)

        # sums per client, per month
        grp = df.groupby(["Client","monlbl"], as_index=False)[["Bubb","Cell"]].sum(min_count=1)

        # pivot to columns; keep both bubb/cell by formatting inside a single cell
        clients = sorted(grp["Client"].unique())
        months  = sorted(grp["monlbl"].unique(), key=lambda s: (int(s.split(" - ")[1]), int(s.split(" - ")[0])))

        # build table rows
        rows = []
        for name in clients:
            row = {"Client": name}
            sub = grp[grp["Client"] == name].set_index("monlbl")
            for m in months:
                bb = int(sub.at[m, "Bubb"]) if (m in sub.index and pd.notna(sub.at[m,"Bubb"])) else 0
                cc = int(sub.at[m, "Cell"]) if (m in sub.index and pd.notna(sub.at[m,"Cell"])) else 0
                row[m] = f"Bubb: {bb}<br>Cell: {cc}"
            # totals, pass-throughs
            # Bubble/Cellushape: prefer file totals if present; else sum Bubb/Cell across months
            # NOTE: file totals may be NaN for some rows, so fallback accordingly
            dff = df[df["Client"] == name]
            bs = pd.to_numeric(dff.get("Bubble"), errors="coerce")
            cs = pd.to_numeric(dff.get("Cellushape"), errors="coerce")
            row["Bubble"]     = (float(bs.dropna().iloc[0]) if (bs is not None and bs.dropna().size) else
                                 int(grp.loc[grp["Client"]==name, "Bubb"].sum()))
            row["Cellushape"] = (float(cs.dropna().iloc[0]) if (cs is not None and cs.dropna().size) else
                                 int(grp.loc[grp["Client"]==name, "Cell"].sum()))
            # Dates from tidy (first non-empty) – will be overwritten by contracts join below if available
            def _first_nonempty(series):
                for v in series.astype(str):
                    v = v.strip()
                    if v and v.lower() != "none":
                        return v
                return ""
            row["Date Start First Contract"] = _first_nonempty(dff.get("Date Start First Contract", pd.Series([],dtype=str)))
            row["Date Start Last Contract"]  = _first_nonempty(dff.get("Date Start Last Contract",  pd.Series([],dtype=str)))
            rows.append(row)

        wide = pd.DataFrame(rows)
        # order columns
        ordered = ["Client"] + months + ["Date Start First Contract","Date Start Last Contract","Bubble","Cellushape"]
        # ensure all columns exist
        for c in ordered:
            if c not in wide.columns:
                wide[c] = "" if "Date Start" in c else 0
        wide = wide[ordered]

    else:
        # Already-wide export (columns like "6 - 2025", "7 - 2025", … with values like "Bubb: 12\nCell: 1")
        month_re = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{4})\s*$")
        months = []
        for c in df_raw.columns:
            m = month_re.match(str(c))
            if m:
                m_i, y_i = int(m.group(1)), int(m.group(2))
                lbl = f"{m_i} - {y_i}"
                months.append((y_i, m_i, lbl))
        if from_ym:
            fy, fm = map(int, from_ym.split("-"))
            months = [t for t in months if (t[0],t[1]) >= (fy,fm)]
        if to_ym:
            ty, tm = map(int, to_ym.split("-"))
            months = [t for t in months if (t[0],t[1]) <= (ty,tm)]
        months.sort()
        month_labels = [lbl for (_,_,lbl) in months]

        name_col = _pick(df_raw, "Client","client","Name","name","Unnamed: 0","unnamed: 0","unnamed:0") or df_raw.columns[0]
        df = df_raw.rename(columns={name_col: "Client"}).copy()
        df["Client"] = df["Client"].astype(str).str.strip()
        keep = ["Client"] + month_labels + \
               [c for c in df.columns if str(c).strip().lower() in (
                   "date start first contract","date start last contract","bubble","cellushape")]
        wide = df[keep].copy()
        # Normalize month cells to "Bubb: x<br>Cell: y"
        for lbl in month_labels:
            if lbl not in wide.columns:
                wide[lbl] = ""
            wide[lbl] = wide[lbl].fillna("").astype(str).map(lambda s: s.replace("\n","<br>").replace("\r",""))
        ordered = ["Client"] + month_labels + ["Date Start First Contract","Date Start Last Contract","Bubble","Cellushape"]
        for c in ["Date Start First Contract","Date Start Last Contract","Bubble","Cellushape"]:
            if c not in wide.columns:
                wide[c] = "" if "Date Start" in c else 0
        wide = wide[ordered]

    # Merge dates from Contracts (if present there)
    span = _contracts_first_last()
    if not span.empty and "Client" in wide.columns:
        wide = wide.merge(span, on="Client", how="left")
        # prefer contracts dates when available
        fs = pd.to_datetime(wide["Date Start First Contract"], errors="coerce")
        ls = pd.to_datetime(wide["Date Start Last Contract"],  errors="coerce")
        alt_fs = pd.to_datetime(wide["first_start"], errors="coerce")
        alt_ls = pd.to_datetime(wide["last_start"],  errors="coerce")
        fs = fs.combine_first(alt_fs)
        ls = ls.combine_first(alt_ls)
        wide["Date Start First Contract"] = fs.dt.strftime("%m/%d/%Y").fillna("")
        wide["Date Start Last Contract"]  = ls.dt.strftime("%m/%d/%Y").fillna("")
        wide = wide.drop(columns=["first_start","last_start"], errors="ignore")

    # Sort by client asc (or by Bubble desc if you prefer)
    wide = wide.sort_values(["Client"], kind="stable", ignore_index=True)
    return wide
