from __future__ import annotations

import inspect
import json
import time
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
    "poll_interval_seconds": 300,
    "ai_cooldown_minutes": 10,
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


def load_settings() -> Dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    file_settings = load_json(MONITOR_SETTINGS_FILE, {})
    if isinstance(file_settings, dict):
        settings.update(file_settings)
    return settings


def load_watchlist() -> List[str]:
    data = load_json(WATCHLIST_FILE, [])
    if isinstance(data, dict):
        items = data.get("tickers") or data.get("watchlist") or []
        if isinstance(items, list):
            return [str(x).upper().strip() for x in items if str(x).strip()]
    elif isinstance(data, list):
        return [str(x).upper().strip() for x in data if str(x).strip()]
    return ["VUAG", "CSP1", "SWDA", "HMWS", "VWRP", "VWRL"]


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
        raise RuntimeError(f"poll_once() should return dict, got {type(result).__name__}")

    result.setdefault("polled_at", now_iso())
    result.setdefault("data", {})
    return result


def can_call_ai(state: Dict[str, Any], current_ts: str, cooldown_minutes: int) -> bool:
    last_ai_call_at = state.get("last_ai_call_at")
    if not last_ai_call_at:
        return True

    try:
        a = datetime.fromisoformat(last_ai_call_at.replace("Z", "+00:00"))
        b = datetime.fromisoformat(current_ts.replace("Z", "+00:00"))
        delta_min = (b - a).total_seconds() / 60.0
        return delta_min >= cooldown_minutes
    except Exception:
        return True


def notify_text(title: str, message: str) -> None:
    try:
        from notifier import send_notification  # type: ignore
        send_notification(title, message)
        return
    except Exception:
        pass

    try:
        from notifier import notify  # type: ignore
        notify(title, message)
        return
    except Exception:
        pass

    print(f"\n[NOTIFY] {title}\n{message}\n")


def build_notification_text(ai_result: Dict[str, Any]) -> str:
    events = ai_result.get("events", []) or []
    summary = ai_result.get("summary", {}) or {}
    lines = []

    if summary:
        lines.append(
            "概况："
            f"上涨 {summary.get('up_count', 0)} / "
            f"下跌 {summary.get('down_count', 0)} / "
            f"平 {summary.get('flat_count', 0)}"
        )
        max_ticker = summary.get("max_abs_move_ticker")
        max_move = summary.get("max_abs_move_pct")
        if max_ticker is not None and max_move is not None:
            lines.append(f"最大波动：{max_ticker} {float(max_move):+.2f}%")

    if events:
        lines.append("事件：")
        for ev in events[:3]:
            ticker = ev.get("ticker") or "WATCHLIST"
            lines.append(f"- [{ev.get('severity', 'info')}] {ticker}: {ev.get('title')}")

    ai_text = (ai_result.get("ai_text") or "").strip()
    if ai_text:
        lines.append("")
        lines.append(ai_text[:1200])

    return "\n".join(lines).strip()


def main() -> None:
    settings = load_settings()
    watchlist = load_watchlist()
    agent = EventAgent()

    print("[FundPilot] monitor loop started.")
    print(f"[FundPilot] watchlist: {watchlist}")
    print(f"[FundPilot] settings: {settings}")

    while True:
        cycle_started = now_iso()
        print(f"\n[FundPilot] polling at {cycle_started}")

        try:
            current_poll = call_poll_once_compat(watchlist)

            last_snapshot = load_json(LAST_SNAPSHOT_FILE, {})
            state = load_json(MONITOR_STATE_FILE, {})

            trigger_result = evaluate_triggers(
                current_poll=current_poll,
                last_snapshot=last_snapshot,
                state=state,
                config=settings,
            )

            should_run_ai = bool(trigger_result.get("should_run_ai"))
            ai_allowed = can_call_ai(
                state=state,
                current_ts=current_poll["polled_at"],
                cooldown_minutes=int(settings["ai_cooldown_minutes"]),
            )

            print("[FundPilot] market summary:", trigger_result.get("market_summary"))
            print("[FundPilot] events:", len(trigger_result.get("events", [])))
            print("[FundPilot] should_run_ai:", should_run_ai, "ai_allowed:", ai_allowed)

            if should_run_ai and ai_allowed:
                ai_result = agent.analyze_monitor_cycle(
                    current_poll=current_poll,
                    trigger_result=trigger_result,
                )

                text = build_notification_text(ai_result)
                notify_text("FundPilot 监控提醒", text)

                state["last_ai_call_at"] = current_poll["polled_at"]
                if trigger_result.get("inspection_needed"):
                    state["last_inspection_at"] = current_poll["polled_at"]

                save_json(MONITOR_STATE_FILE, state)

                print("\n[FundPilot AI]")
                print(ai_result.get("ai_text", ""))
                print()
            else:
                print("[FundPilot] AI skipped this cycle.")

            save_json(LAST_SNAPSHOT_FILE, current_poll)

        except KeyboardInterrupt:
            print("\n[FundPilot] monitor loop stopped by user.")
            break
        except Exception as e:
            print(f"[FundPilot] cycle error: {e}")

        time.sleep(int(settings["poll_interval_seconds"]))


if __name__ == "__main__":
    main()