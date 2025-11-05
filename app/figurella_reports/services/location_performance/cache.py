from __future__ import annotations
import json, os, time
from pathlib import Path
from typing import Dict, Any

CACHE_DIRNAME = "figurella_reports"
CACHE_BASENAME = "perf_cache.json"

def _now_ts() -> float:
    return time.time()

def cache_path(instance_dir: Path) -> Path:
    d = instance_dir / CACHE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d / CACHE_BASENAME

def load_cache(instance_dir: Path) -> Dict[str, Any] | None:
    p = cache_path(instance_dir)
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def save_cache(instance_dir: Path, payload: Dict[str, Any]) -> None:
    p = cache_path(instance_dir)
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, p)
