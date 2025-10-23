# app/common/utils_wide.py
import re
import pandas as pd

MONTH_HDR_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{4})\s*$")

def melt_month_wide(df: pd.DataFrame, *, name_col: str) -> pd.DataFrame:
    """
    Converts a monthly-wide table into tidy rows:
      input: [name_col, '1 - 2025', '2 - 2025', ...]
      output: columns: [Client, Year, Month, Value]
    """
    month_cols = []
    for c in df.columns:
        m = MONTH_HDR_RE.match(str(c))
        if m:
            month_cols.append((c, int(m.group(2)), int(m.group(1))))  # (col, year, month)
    if not month_cols:
        # nothing to melt
        out = df.copy()
        out["Year"]  = None
        out["Month"] = None
        out["Value"] = None
        return out

    keep = [name_col] + [c for (c, _, _) in month_cols]
    base = df[keep].copy()
    tidy = base.melt(id_vars=[name_col], var_name="Col", value_name="Value")
    # parse Year/Month
    yy, mm = [], []
    for col in tidy["Col"].tolist():
        m = MONTH_HDR_RE.match(str(col))
        if m:
            mm.append(int(m.group(1))); yy.append(int(m.group(2)))
        else:
            mm.append(None); yy.append(None)
    tidy["Year"]  = yy
    tidy["Month"] = mm
    tidy.drop(columns=["Col"], inplace=True)
    return tidy
