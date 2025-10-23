# app/common/utils_dates.py
from datetime import datetime
from dateutil.relativedelta import relativedelta

def build_month_windows(months_back=14, months_forward=0, *, chunk_max=12, overlap=2):
    """
    Returns list of (start_dt, end_dt) pairs covering [today - months_back, today + months_forward],
    using chunks of at most 'chunk_max' months, with 'overlap' months of overlap between chunks.
    Example (14 months, max 12, overlap 2) -> two windows:
      [T-14m, T-2m] and [T-4m, T]
    """
    assert chunk_max >= 1 and 0 <= overlap < chunk_max
    today = datetime.today()
    range_start = today - relativedelta(months=months_back)
    range_end   = today + relativedelta(months=months_forward)

    windows = []
    cur_start = range_start
    while cur_start < range_end:
        cur_end = min(cur_start + relativedelta(months=chunk_max), range_end)
        windows.append((cur_start, cur_end))
        # advance so the next window overlaps by 'overlap' months
        cur_start = cur_end - relativedelta(months=overlap)
    return windows

def month_windows(start: datetime, end: datetime, *, chunk_max=12, overlap=2):
    """
    Fixed-range windows: Yield (start_str, end_str) in MM/DD/YYYY for [start, end],
    each ≤ chunk_max months, overlapping by 'overlap' months. Never repeats the last window.
    """
    assert chunk_max >= 1 and 0 <= overlap < chunk_max
    fmt = lambda d: d.strftime("%m/%d/%Y")
    cur_start = start
    while cur_start < end:
        cur_end = cur_start + relativedelta(months=chunk_max)
        if cur_end > end:
            cur_end = end
        yield fmt(cur_start), fmt(cur_end)
        if cur_end == end:
            break
        next_start = cur_end - relativedelta(months=overlap)
        if next_start <= cur_start:
            next_start = cur_end
        cur_start = next_start

def fmt_mmddyyyy(dt: datetime) -> str:
    return dt.strftime("%m/%d/%Y")
