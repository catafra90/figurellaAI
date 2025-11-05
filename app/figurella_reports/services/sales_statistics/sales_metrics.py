# app/figurella_reports/services/sales_statistics/sales_metrics.py
from __future__ import annotations
from pathlib import Path
import json, time

# Simple file-mtime cache pattern (adjust to your real sources later)
_CACHE: dict[str, dict] = {}
_TTL_SEC = 60  # optional: recheck mtimes every minute

def _sources(app_root: Path, instance_dir: Path) -> list[Path]:
    """
    Return the Excel/CSV sources that determine the sales snapshot.
    Replace with your real files (payments.xlsx, contracts.xlsx, etc.).
    """
    candidates = [
        instance_dir / "figurella_reports" / "payments.xlsx",
        instance_dir / "figurella_reports" / "contracts.xlsx",
        app_root / "payments.xlsx",
        app_root / "contracts.xlsx",
    ]
    return [p for p in candidates if p.exists()]

def _signature(paths: list[Path]) -> str:
    stats = [(str(p), p.stat().st_mtime_ns) for p in paths]
    return json.dumps(stats, sort_keys=True)

def _compute_sales_snapshot(app_root: Path, instance_dir: Path) -> dict:
    """
    Compute the current sales snapshot from your sources.
    TODO: Replace stubbed numbers with your real pandas logic.
    """
    # Example: read files with pandas and aggregate:
    #   df_pay = pd.read_excel(source1); df_cnt = pd.read_excel(source2); ...
    #   return {"total": ..., "cash": ..., "payments": ..., "internal": ..., "newClients": ...}
    return {
        "total": 18200,
        "cash": 9300,
        "payments": 5500,
        "internal": 1200,
        "newClients": 2200,
    }

def get_sales_cached(app_root: Path, instance_dir: Path) -> dict:
    """
    Fast cache: recompute only when underlying source files change (by mtime).
    """
    srcs = _sources(app_root, instance_dir)
    sig = _signature(srcs)
    now = time.time()

    entry = _CACHE.get("sales")
    if entry:
        if entry.get("sig") == sig and (now - entry.get("ts", 0) < _TTL_SEC):
            return entry["data"]

    data = _compute_sales_snapshot(app_root, instance_dir)
    _CACHE["sales"] = {"sig": sig, "data": data, "ts": now}
    return data
