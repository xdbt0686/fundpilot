from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

ETF_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "etfs.json"

# 模块级缓存：进程生命周期内只读一次文件，避免每次调用都产生 I/O
_cache: Optional[Dict[str, dict]] = None


def _load_index() -> Dict[str, dict]:
    global _cache
    if _cache is None:
        with open(ETF_DATA_PATH, "r", encoding="utf-8") as f:
            raw: List[dict] = json.load(f)
        _cache = {etf["ticker"].upper(): etf for etf in raw if etf.get("ticker")}
    return _cache


def load_raw_etfs() -> List[dict]:
    return list(_load_index().values())


def get_raw_etf_by_ticker(ticker: str) -> Optional[dict]:
    return _load_index().get(ticker.upper().strip())