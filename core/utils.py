from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR   = Path(__file__).resolve().parent.parent
DATA_DIR   = BASE_DIR / "data"

WATCHLIST_FILE        = DATA_DIR / "watchlist.json"
LAST_SNAPSHOT_FILE    = DATA_DIR / "last_snapshot.json"
MONITOR_STATE_FILE    = DATA_DIR / "monitor_state.json"
MONITOR_SETTINGS_FILE = DATA_DIR / "monitor_settings.json"

DEFAULT_WATCHLIST = ["VUAG", "CSP1", "SWDA", "HMWS", "VWRP", "VWRL"]

DEFAULT_SETTINGS: Dict[str, Any] = {
    "poll_interval_seconds":  300,
    "ai_cooldown_minutes":    10,
    "heartbeat_minutes":      30,
    "daily_move_alert_pct":   1.5,
    "daily_move_strong_pct":  3.0,
    "stale_data_minutes":     20,
    "reversal_pct":           1.0,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_watchlist() -> List[str]:
    data = load_json(WATCHLIST_FILE, {})
    if isinstance(data, dict):
        items = data.get("tickers") or data.get("watchlist") or []
        if isinstance(items, list):
            return [str(x).upper().strip() for x in items if str(x).strip()]
    elif isinstance(data, list):
        return [str(x).upper().strip() for x in data if str(x).strip()]
    return list(DEFAULT_WATCHLIST)


def load_settings() -> Dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    overrides = load_json(MONITOR_SETTINGS_FILE, {})
    if isinstance(overrides, dict):
        settings.update(overrides)
    return settings


def call_poll_once_compat(watchlist: List[str]) -> Dict[str, Any]:
    from monitors.price_poller import poll_once

    try:
        sig = inspect.signature(poll_once)
        result = poll_once(watchlist) if sig.parameters else poll_once()
    except (TypeError, ValueError):
        try:
            result = poll_once(watchlist)
        except TypeError:
            result = poll_once()

    if not isinstance(result, dict):
        raise RuntimeError(f"poll_once() should return dict, got {type(result).__name__}")

    result.setdefault("polled_at", now_iso())
    result.setdefault("data", {})
    return result
