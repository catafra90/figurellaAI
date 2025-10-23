import pandas as pd 
from app.common.report_io import load_report_df as _core_load_report_df
import re

def load_df(report_key: str) -> pd.DataFrame:
    """
    Generic loader for any report.
    Drops the internal '_sheet' column if present.
    Falls back to empty DataFrame on error.
    """
    try:
        df = _core_load_report_df(report_key)
        if df is None:
            return pd.DataFrame()
        if "_sheet" in getattr(df, "columns", []):
            df = df.drop(columns=["_sheet"])
        return df
    except Exception:
        return pd.DataFrame()

def load_last_session_df() -> pd.DataFrame:
    """
    Specialized loader for 'last_session' report.
    Cleans column headers (NBSPs, extra spaces) and ensures consistency.
    """
    df = load_df("last_session")
    if df.empty:
        return df

    def norm_head(s: str) -> str:
        if not isinstance(s, str):
            return str(s)
        s = s.replace("\u00a0", " ")
        s = re.sub(r"\s+", " ", s).strip()
        return s

    df = df.copy()
    df.columns = [norm_head(c) for c in df.columns]
    return df
