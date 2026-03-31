from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from agent.event_agent import EventAgent
from monitors.price_poller import poll_once
from rules.trigger_rules import evaluate_triggers

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

WATCHLIST_FILE = DATA_DIR / "watchlist.json"
LAST_SNAPSHOT_FILE = DATA_DIR / "last_snapshot.json"
MONITOR_STATE_FILE = DATA_DIR / "monitor_state.json"
MONITOR_SETTINGS_FILE = DATA_DIR / "monitor_settings.json"


DEFAULT_SETTINGS = {
    "heartbeat_minutes": 30,
    "daily_move_alert_pct": 1.5,
    "daily_move_strong_pct": 3.0,
    "stale_data_minutes": 20,
    "reversal_pct": 1.0,
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
    return ["VUAG", "CSP1", "SWDA", "HMWS", "VWRP", "VWRL"]


def load_settings() -> Dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    file_settings = load_json(MONITOR_SETTINGS_FILE, {})
    if isinstance(file_settings, dict):
        settings.update(file_settings)
    return settings


def call_poll_once_compat(watchlist: List[str]) -> Dict[str, Any]:
    try:
        sig = inspect.signature(poll_once)
        if len(sig.parameters) == 0:
            result = poll_once()
        else:
            result = poll_once(watchlist)
    except (TypeError, ValueError):
        try:
            result = poll_once(watchlist)
        except TypeError:
            result = poll_once()

    if not isinstance(result, dict):
        raise RuntimeError("poll_once() did not return dict.")

    result.setdefault("polled_at", now_iso())
    result.setdefault("data", {})
    return result


def main() -> None:
    watchlist = load_watchlist()
    settings = load_settings()
    agent = EventAgent()

    current_poll = call_poll_once_compat(watchlist)

    last_snapshot = load_json(LAST_SNAPSHOT_FILE, {})
    state = load_json(MONITOR_STATE_FILE, {})

    trigger_result = evaluate_triggers(
        current_poll=current_poll,
        last_snapshot=last_snapshot,
        state=state,
        config=settings,
    )

    ai_result = agent.analyze_monitor_cycle(
        current_poll=current_poll,
        trigger_result=trigger_result,
    )

    print("\n=== CURRENT POLL ===")
    print(json.dumps(current_poll, ensure_ascii=False, indent=2))

    print("\n=== TRIGGER RESULT ===")
    print(json.dumps(trigger_result, ensure_ascii=False, indent=2))

    print("\n=== AI RESULT ===")
    print(ai_result.get("ai_text", ""))

    state["last_ai_call_at"] = current_poll["polled_at"]
    if trigger_result.get("inspection_needed"):
        state["last_inspection_at"] = current_poll["polled_at"]

    save_json(MONITOR_STATE_FILE, state)
    save_json(LAST_SNAPSHOT_FILE, current_poll)


if __name__ == "__main__":
    main()