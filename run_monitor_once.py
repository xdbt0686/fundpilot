from __future__ import annotations

from agent.event_agent import EventAgent
from rules.trigger_rules import evaluate_triggers
from core.utils import (
    load_watchlist, load_settings, call_poll_once_compat,
    load_json, save_json,
    LAST_SNAPSHOT_FILE, MONITOR_STATE_FILE,
)

SEP = "─" * 60


def _print_poll_summary(poll: dict) -> None:
    data = poll.get("data", {})
    print(f"\n{'─'*60}")
    print(f"  行情快照  ({poll.get('polled_at', '?')})  共 {len(data)} 只")
    print(SEP)
    print(f"  {'代码':<10} {'最新价':>10}  {'日涨跌':>8}  {'周涨跌':>8}  {'数据日期':>12}")
    print(SEP)
    for ticker, item in data.items():
        price = item.get("latest_price")
        d_pct = item.get("daily_change_pct")
        w_pct = item.get("week_change_pct")
        date  = item.get("data_date", "")
        p_str = f"{price:.4f}"   if price  is not None else "    --"
        d_str = f"{d_pct:+.2f}%" if d_pct  is not None else "    --"
        w_str = f"{w_pct:+.2f}%" if w_pct  is not None else "    --"
        print(f"  {ticker:<10} {p_str:>10}  {d_str:>8}  {w_str:>8}  {date:>12}")
    print(SEP)


def _print_trigger_summary(tr: dict) -> None:
    ms = tr.get("market_summary") or {}
    top    = ms.get("max_abs_move_ticker")
    top_m  = ms.get("max_abs_move_pct")
    top_str = f"  最大波动：{top} {float(top_m):+.2f}%" if top and top_m is not None else ""

    print(f"\n{'─'*60}")
    print(
        f"  触发规则摘要 — "
        f"上涨 {ms.get('up_count', 0)} / "
        f"下跌 {ms.get('down_count', 0)} / "
        f"持平 {ms.get('flat_count', 0)}"
        f"{top_str}"
    )
    events = tr.get("events") or []
    if events:
        print(f"  触发事件（{len(events)} 个）：")
        for ev in events:
            ticker = ev.get("ticker") or "全局"
            sev    = ev.get("severity", "info")
            title  = ev.get("title", "")
            print(f"    [{sev:6}] {ticker}: {title}")
    else:
        print("  无触发事件。")
    print(SEP)


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

    _print_poll_summary(current_poll)
    _print_trigger_summary(trigger_result)

    print(f"\n{'─'*60}")
    print("  AI 分析")
    print(SEP)
    print(ai_result.get("ai_text", "（无回答）"))
    print(SEP)

    state["last_ai_call_at"] = current_poll["polled_at"]
    if trigger_result.get("inspection_needed"):
        state["last_inspection_at"] = current_poll["polled_at"]

    save_json(MONITOR_STATE_FILE, state)
    save_json(LAST_SNAPSHOT_FILE, current_poll)


if __name__ == "__main__":
    main()
