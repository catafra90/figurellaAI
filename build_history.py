import os
import glob
import pandas as pd
from app.common.cleaners import drop_unwanted_rows

# ───────── Use script directory as base ─────────
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# ───────── Configuration ─────────
REPORT_TYPES = {
    'payments_due': {
        'download_dir': 'downloads/payments_due',
        'history_file': 'history_payments_due.xlsx',
        'usecols':      ['Name','Contract','Due date','Amount'],
        'key_cols':     ['Name','Contract']
    },
    'last_session': {
        'download_dir': 'downloads/last_session',
        'history_file': 'history_last_session.xlsx',
        'usecols':      ['Last name','First name','status','phone','email','last session','contract expiration','Bubble','Cellushape'],
        'key_cols':     ['Last name','First name']
    },
    'ibf': {
        'download_dir': 'downloads/ibf',
        'history_file': 'history_ibf.xlsx',
        'usecols':      None,
        'key_cols':     None
    },
    'agenda': {
        'download_dir': 'downloads/agenda',
        'history_file': 'history_agenda.xlsx',
        'usecols':      ['First Name','Last Name','Email','Phone','Customer Status','Day','Appointment Status'],
        'key_cols':     ['First Name','Last Name','Day']
    },
    'contracts': {
        'download_dir': 'downloads/contracts',
        'history_file': 'history_contracts.xlsx',
        'usecols':      ['Name','Surname','Assist.','Date','Details','Amount'],
        'key_cols':     ['Name','Surname','Date']
    },
    'payments_done': {
        'download_dir': 'downloads/payments_done',
        'history_file': 'history_payments_done.xlsx',
        'usecols':      ['Last name','First name','Expected','Cash In','Instalment','Amount'],
        'key_cols':     ['Last name','First name','Expected','Cash In']
    },
    'customer_acquisition': {
        'download_dir': 'downloads/customer_acquisition',
        'history_file': 'history_customer_acquisition.xlsx',
        'usecols':      ['Name','Email','Phone','Date of Birth','Acquisition date','Status','First Contract'],
        'key_cols':     ['Name','Email']
    },
    'subscriptions': {
        'download_dir': 'downloads/subscriptions',
        'history_file': 'history_subscriptions.xlsx',
        'usecols':      None,
        'key_cols':     None
    },
    'pip': {
        'download_dir': 'downloads/pip',
        'history_file': 'history_pip.xlsx',
        'usecols':      ['Name','Contract Date','Assistant','Total'],
        'key_cols':     ['Name','Contract Date']
    }
}

def find_files(folder):
    """Return all .xlsx files under BASE_DIR/folder."""
    pattern = os.path.join(BASE_DIR, folder, "*.xlsx")
    return glob.glob(pattern)

def merge_history(report, cfg):
    # 1) locate new download files
    files = find_files(cfg['download_dir'])
    if not files:
        print(f"[!] No downloads for '{report}'")
        return

    # 2) load & clean existing history
    hist_path = os.path.join(BASE_DIR, cfg['history_file'])
    if os.path.exists(hist_path):
        master = pd.read_excel(hist_path)
        try:
            master = drop_unwanted_rows(master)
        except Exception:
            pass
    else:
        master = pd.DataFrame()

    # 3) read & clean all new dumps
    dfs = []
    for f in files:
        df = pd.read_excel(f)
        if cfg['usecols']:
            df = df[[c for c in cfg['usecols'] if c in df.columns]]
        try:
            df = drop_unwanted_rows(df)
        except Exception:
            pass
        dfs.append(df)
    new_all = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    # 4) combine & dedupe
    combined = pd.concat([master, new_all], ignore_index=True)
    keys = cfg.get('key_cols')
    if keys:
        combined = combined.drop_duplicates(subset=keys, keep='last')
    else:
        combined = combined.drop_duplicates(keep='last')

    # 5) for Contracts only: drop first three stray rows
    if report == 'contracts' and len(combined) > 3:
        combined = combined.iloc[3:].reset_index(drop=True)

    # 6) save back to project root
    print(f"Saving {report} history → {hist_path}")
    combined.to_excel(hist_path, index=False)
    print(f"[✔] {report} → {hist_path}")

def main():
    """Run all history merges cleanly."""
    for rpt, cfg in REPORT_TYPES.items():
        merge_history(rpt, cfg)

if __name__ == "__main__":
    main()
