import pandas as pd
from typing import Dict, List, Tuple
from ..io.loader import load_last_session_df

def prepare_last_session_view() -> Dict:
    """
    Return EVERY row from the Last Session report exactly as loaded.
    No grouping, no sorting, no header renames, no derived columns.
    """
    messages: List[Tuple[str, str]] = []

    df = load_last_session_df()
    if df is None or df.empty:
        messages.append(("warning", "No rows found for 'Last Session'."))
        return {"columns": [], "rows": [], "messages": messages}

    # IMPORTANT: Do NOT sort or filter. Show exactly what loader returns.
    columns = df.columns.tolist()
    rows = df.fillna("").values.tolist()

    return {"columns": columns, "rows": rows, "messages": messages}
