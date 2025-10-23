from datetime import date
import pandas as pd
from .base import to_number_any
from ..io.loader import load_df

def monthly_total(target_year: int | None = None, target_month: int | None = None):
    today = date.today()
    year  = target_year or today.year
    month = target_month or today.month

    df = load_df("payments_due")
    if df.empty:
        return (0.0, 0)

    cols = _month_columns(df)
    target_col = _pick_target_col(cols, year, month)
    if not target_col:
        return (0.0, 0)

    nums = df[target_col].map(to_number_any)
    total = float(nums.sum())
    count = int((nums != 0).sum())
    return (round(total, 2), count)

def _month_columns(df: pd.DataFrame):
    import re
    month_re = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{4})\s*$")
    out = []
    for c in df.columns:
        m = month_re.match(str(c))
        if m:
            out.append((c, int(m.group(2)), int(m.group(1))))  # (name, year, month)
    return out

def _pick_target_col(cols, year, month):
    wanted = f"{month} - {year}"
    for c, y, m in cols:
        if str(c).strip() == wanted:
            return c
    for c, y, m in cols:
        if y == year and m == month:
            return c
    return None
