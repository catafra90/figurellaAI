from datetime import datetime
from dateutil.relativedelta import relativedelta

def month_windows(start: datetime, end: datetime, *, chunk_max=12, overlap=2):
    """
    Yield (from_date_str, to_date_str) windows in MM/DD/YYYY format,
    each ≤ chunk_max months, with 'overlap' months between windows.
    Includes a guard so the loop cannot repeat the last window.
    """
    fmt = lambda d: d.strftime("%m/%d/%Y")
    cur_start = start

    while cur_start < end:
        cur_end = cur_start + relativedelta(months=chunk_max)
        if cur_end > end:
            cur_end = end

        yield fmt(cur_start), fmt(cur_end)

        # If we just emitted the final window, stop.
        if cur_end == end:
            break

        next_start = cur_end - relativedelta(months=overlap)
        # Guard: never go backwards or repeat
        if next_start <= cur_start:
            next_start = cur_end
        cur_start = next_start
