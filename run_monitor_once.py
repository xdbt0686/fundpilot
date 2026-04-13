from __future__ import annotations

import json

from agent.event_agent import EventAgent
from rules.trigger_rules import evaluate_triggers
from core.utils import (
    load_watchlist, load_settings, call_poll_once_compat,
    load_json, save_json,
    LAST_SNAPSHOT_FILE, MONITOR_STATE_FILE,
)


def main() -> None:
    watchlist = load_watchlist()
    settings  = load_settings()
    agent     = EventAgent()

    current_poll  = call_poll_once_compat(watchlist)
    last_snapshot = load_json(LAST_SNAPSHOT_FILE, {})
    state         = load_json(MONITOR_STATE_FILE, {})

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
