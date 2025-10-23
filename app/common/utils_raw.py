# app/common/utils_raw.py
from pathlib import Path
from datetime import datetime
import pandas as pd
from typing import Optional
import re

RAW_ROOT = Path("app/data/raw")  # adjust if you prefer another base

def _stamp():
    # e.g. 2025-08-25_21-03-12
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def _safe_tag(tag: Optional[str]) -> str:
    """
    Sanitize tag so it's safe for use in file names on Windows/Linux.
    Replaces path separators and weird chars with '-'.
    """
    if not tag:
        return ""
    s = re.sub(r"[\\/]", "-", tag)              # replace slashes
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s)     # replace other bad chars
    return s.strip("-_.")

def archive_text(report_key: str, text: str, *, tag: Optional[str] = None, ext: str = "html") -> Path:
    ts = _stamp()
    y  = datetime.now().strftime("%Y")
    ym = datetime.now().strftime("%Y-%m")
    tag_part = f"__{_safe_tag(tag)}" if tag else ""
    base = _ensure_dir(RAW_ROOT / report_key / y / ym)
    path = base / f"{ts}{tag_part}.{ext}"
    path.write_text(text or "", encoding="utf-8")
    return path

def archive_bytes(report_key: str, data: bytes, *, tag: Optional[str] = None, ext: str = "bin") -> Path:
    ts = _stamp()
    y  = datetime.now().strftime("%Y")
    ym = datetime.now().strftime("%Y-%m")
    tag_part = f"__{_safe_tag(tag)}" if tag else ""
    base = _ensure_dir(RAW_ROOT / report_key / y / ym)
    path = base / f"{ts}{tag_part}.{ext}"
    path.write_bytes(data or b"")
    return path

def archive_df(report_key: str, df: pd.DataFrame, *, tag: Optional[str] = None) -> Path:
    ts = _stamp()
    y  = datetime.now().strftime("%Y")
    ym = datetime.now().strftime("%Y-%m")
    tag_part = f"__{_safe_tag(tag)}" if tag else ""
    base = _ensure_dir(RAW_ROOT / report_key / y / ym)
    path = base / f"{ts}{tag_part}.csv"
    df.to_csv(path, index=False)
    return path
