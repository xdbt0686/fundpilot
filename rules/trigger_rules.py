from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


DEFAULT_RULE_CONFIG = {
    "daily_move_alert_pct": 1.5,
    "daily_move_strong_pct": 3.0,
    "heartbeat_minutes": 30,
    "stale_data_minutes": 20,
    "reversal_pct": 1.0,
}


def _parse_iso_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _minutes_between(old_ts: Optional[str], new_ts: Optional[str]) -> Optional[float]:
    a = _parse_iso_ts(old_ts)
    b = _parse_iso_ts(new_ts)
    if not a or not b:
        return None
    return (b - a).total_seconds() / 60.0


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _build_event(
    event_type: str,
    severity: str,
    ticker: Optional[str],
    title: str,
    message: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "event_type": event_type,
        "severity": severity,
        "ticker": ticker,
        "title": title,
        "message": message,
        "extra": extra or {},
    }


def evaluate_triggers(
    current_poll: Dict[str, Any],
    last_snapshot: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    输入:
      current_poll: {
        "polled_at": "...",
        "data": {
          "VUAG": {...},
          ...
        }
      }

      last_snapshot: {
        "polled_at": "...",
        "data": {...}
      }

      state: {
        "last_inspection_at": "...",
        "last_ai_call_at": "...",
        "last_notified": {
            "event_key": "..."
        }
      }

    输出:
      {
        "should_run_ai": bool,
        "events": [...],
        "inspection_needed": bool,
        "market_summary": {...}
      }
    """
    cfg = dict(DEFAULT_RULE_CONFIG)
    if config:
        cfg.update(config)

    state = state or {}
    current_data = (current_poll or {}).get("data", {}) or {}
    current_polled_at = (current_poll or {}).get("polled_at")
    last_data = ((last_snapshot or {}).get("data", {}) if last_snapshot else {}) or {}

    events: List[Dict[str, Any]] = []

    up_count = 0
    down_count = 0
    flat_count = 0

    max_abs_move = 0.0
    max_move_ticker = None

    for ticker, item in current_data.items():
        daily_change_pct = _safe_float(item.get("daily_change_pct"))
        previous_close = item.get("previous_close")
        latest_price = item.get("latest_price")
        item_ts = item.get("timestamp") or current_polled_at

        if daily_change_pct > 0.05:
            up_count += 1
        elif daily_change_pct < -0.05:
            down_count += 1
        else:
            flat_count += 1

        if abs(daily_change_pct) > abs(max_abs_move):
            max_abs_move = daily_change_pct
            max_move_ticker = ticker

        # 1) 日内涨跌幅事件
        if abs(daily_change_pct) >= cfg["daily_move_strong_pct"]:
            severity = "high"
            title = f"{ticker} strong move"
            message = (
                f"{ticker} moved {daily_change_pct:+.2f}% today. "
                f"latest={latest_price}, prev_close={previous_close}"
            )
            events.append(
                _build_event(
                    "daily_move",
                    severity,
                    ticker,
                    title,
                    message,
                    {"daily_change_pct": daily_change_pct, "latest_price": latest_price},
                )
            )
        elif abs(daily_change_pct) >= cfg["daily_move_alert_pct"]:
            severity = "medium"
            title = f"{ticker} notable move"
            message = (
                f"{ticker} moved {daily_change_pct:+.2f}% today. "
                f"latest={latest_price}, prev_close={previous_close}"
            )
            events.append(
                _build_event(
                    "daily_move",
                    severity,
                    ticker,
                    title,
                    message,
                    {"daily_change_pct": daily_change_pct, "latest_price": latest_price},
                )
            )

        # 2) 与上一个 snapshot 比较，检测方向反转 / 短时变化
        prev_item = last_data.get(ticker, {}) if last_data else {}
        prev_change_pct = _safe_float(prev_item.get("daily_change_pct"), default=0.0)
        prev_price = prev_item.get("latest_price")
        prev_ts = prev_item.get("timestamp") or (last_snapshot or {}).get("polled_at")

        # 方向反转：上次涨、这次跌，或上次跌、这次涨，且绝对值达到阈值
        if (
            abs(prev_change_pct) >= cfg["reversal_pct"]
            and abs(daily_change_pct) >= cfg["reversal_pct"]
            and (prev_change_pct * daily_change_pct < 0)
        ):
            events.append(
                _build_event(
                    "reversal",
                    "high",
                    ticker,
                    f"{ticker} reversal detected",
                    (
                        f"{ticker} daily move changed direction from "
                        f"{prev_change_pct:+.2f}% to {daily_change_pct:+.2f}%."
                    ),
                    {
                        "previous_daily_change_pct": prev_change_pct,
                        "current_daily_change_pct": daily_change_pct,
                        "previous_price": prev_price,
                        "current_price": latest_price,
                    },
                )
            )

        # 3) 数据陈旧检测
        gap_minutes = _minutes_between(item_ts, current_polled_at)
        if gap_minutes is not None and gap_minutes >= cfg["stale_data_minutes"]:
            events.append(
                _build_event(
                    "stale_data",
                    "medium",
                    ticker,
                    f"{ticker} data may be stale",
                    f"{ticker} timestamp appears {gap_minutes:.1f} minutes older than current poll time.",
                    {"gap_minutes": gap_minutes, "item_timestamp": item_ts},
                )
            )

    # 4) 巡检事件（没有大波动也允许 AI 介入）
    inspection_needed = False
    last_inspection_at = state.get("last_inspection_at")
    since_inspection = _minutes_between(last_inspection_at, current_polled_at)

    if last_inspection_at is None:
        inspection_needed = True
    elif since_inspection is not None and since_inspection >= cfg["heartbeat_minutes"]:
        inspection_needed = True

    if inspection_needed:
        events.append(
            _build_event(
                "heartbeat_inspection",
                "low",
                None,
                "Scheduled inspection",
                "Regular market inspection cycle triggered.",
                {
                    "heartbeat_minutes": cfg["heartbeat_minutes"],
                    "last_inspection_at": last_inspection_at,
                },
            )
        )

    market_summary = {
        "polled_at": current_polled_at,
        "watchlist_size": len(current_data),
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
        "max_abs_move_ticker": max_move_ticker,
        "max_abs_move_pct": round(max_abs_move, 4),
    }

    # 事件优先，其次巡检
    should_run_ai = bool(events)

    return {
        "should_run_ai": should_run_ai,
        "events": events,
        "inspection_needed": inspection_needed,
        "market_summary": market_summary,
    }