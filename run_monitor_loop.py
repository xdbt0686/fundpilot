from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict

from agent.event_agent import EventAgent
from rules.trigger_rules import evaluate_triggers
from core.utils import (
    now_iso, load_json, save_json,
    load_watchlist, load_settings, call_poll_once_compat,
    LAST_SNAPSHOT_FILE, MONITOR_STATE_FILE,
)


def can_call_ai(state: Dict[str, Any], current_ts: str, cooldown_minutes: int) -> bool:
    last = state.get("last_ai_call_at")
    if not last:
        return True
    try:
        a = datetime.fromisoformat(last.replace("Z", "+00:00"))
        b = datetime.fromisoformat(current_ts.replace("Z", "+00:00"))
        return (b - a).total_seconds() / 60.0 >= cooldown_minutes
    except Exception:
        return True


def notify_text(title: str, message: str) -> None:
    try:
        from notifiers.console_notifier import notify_windows
        notify_windows(title, message)
        return
    except Exception:
        pass
    print(f"\n[NOTIFY] {title}\n{message}\n")


def build_notification_text(ai_result: Dict[str, Any]) -> str:
    events  = ai_result.get("events", []) or []
    summary = ai_result.get("summary", {}) or {}
    lines   = []

    if summary:
        lines.append(
            f"概况：上涨 {summary.get('up_count', 0)} / "
            f"下跌 {summary.get('down_count', 0)} / "
            f"平 {summary.get('flat_count', 0)}"
        )
        t, m = summary.get("max_abs_move_ticker"), summary.get("max_abs_move_pct")
        if t is not None and m is not None:
            lines.append(f"最大波动：{t} {float(m):+.2f}%")

    if events:
        lines.append("事件：")
        for ev in events[:3]:
            ticker = ev.get("ticker") or "WATCHLIST"
            lines.append(f"- [{ev.get('severity', 'info')}] {ticker}: {ev.get('title')}")

    ai_text = (ai_result.get("ai_text") or "").strip()
    if ai_text:
        lines += ["", ai_text[:1200]]

    return "\n".join(lines).strip()


def main() -> None:
    settings  = load_settings()
    watchlist = load_watchlist()
    agent     = EventAgent()

    print("[FundPilot] monitor loop started.")
    print(f"[FundPilot] watchlist ({len(watchlist)}): {', '.join(watchlist)}")
    print(
        f"[FundPilot] settings — "
        f"poll every {settings.get('poll_interval_seconds', '?')}s  |  "
        f"AI cooldown {settings.get('ai_cooldown_minutes', '?')} min  |  "
        f"alert threshold {settings.get('daily_move_alert_pct', '?')}%"
    )

    while True:
        print(f"\n[FundPilot] polling at {now_iso()}")
        try:
            current_poll  = call_poll_once_compat(watchlist)
            last_snapshot = load_json(LAST_SNAPSHOT_FILE, {})
            state         = load_json(MONITOR_STATE_FILE, {})

            trigger_result = evaluate_triggers(
                current_poll=current_poll,
                last_snapshot=last_snapshot,
                state=state,
                config=settings,
            )

            should_run_ai = bool(trigger_result.get("should_run_ai"))
            ai_allowed    = can_call_ai(
                state=state,
                current_ts=current_poll["polled_at"],
                cooldown_minutes=int(settings["ai_cooldown_minutes"]),
            )

            ms = trigger_result.get("market_summary") or {}
            top = ms.get("max_abs_move_ticker")
            top_pct = ms.get("max_abs_move_pct")
            top_str = f"  |  最大波动 {top} {float(top_pct):+.2f}%" if top and top_pct is not None else ""
            print(
                f"[FundPilot] 市场概况 — "
                f"上涨 {ms.get('up_count', 0)} / "
                f"下跌 {ms.get('down_count', 0)} / "
                f"持平 {ms.get('flat_count', 0)}"
                f"{top_str}"
            )
            n_events = len(trigger_result.get("events", []))
            print(f"[FundPilot] 触发事件 {n_events} 个  |  AI {'待触发' if should_run_ai else '本轮跳过'}  |  冷却 {'已解除' if ai_allowed else '未到'}")

            if should_run_ai and ai_allowed:
                ai_result = agent.analyze_monitor_cycle(
                    current_poll=current_poll,
                    trigger_result=trigger_result,
                )
                notify_text("FundPilot 监控提醒", build_notification_text(ai_result))

                state["last_ai_call_at"] = current_poll["polled_at"]
                if trigger_result.get("inspection_needed"):
                    state["last_inspection_at"] = current_poll["polled_at"]
                save_json(MONITOR_STATE_FILE, state)

                print("\n[FundPilot AI]")
                print(ai_result.get("ai_text", ""))
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
