from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# ── 信号等级 ──────────────────────────────────────────────────────────────────

STRONG_BUY  = "strong_buy"
BUY         = "buy"
HOLD        = "hold"
SELL        = "sell"
STRONG_SELL = "strong_sell"
NO_DATA     = "no_data"

_SIGNAL_LABELS = {
    STRONG_BUY:  "强烈买入",
    BUY:         "买入",
    HOLD:        "持有观望",
    SELL:        "卖出",
    STRONG_SELL: "强烈卖出",
    NO_DATA:     "数据不足",
}

_SIGNAL_SCORE_MAP: List[Tuple[int, str]] = [
    (5,  STRONG_BUY),
    (2,  BUY),
    (-1, HOLD),
    (-4, SELL),
    (-99, STRONG_SELL),
]


def _score_to_signal(score: int) -> str:
    for threshold, signal in _SIGNAL_SCORE_MAP:
        if score >= threshold:
            return signal
    return STRONG_SELL


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


# ── 单项评分 ──────────────────────────────────────────────────────────────────

def _score_daily(pct: Optional[float]) -> Tuple[int, str]:
    if pct is None:
        return 0, ""
    if pct >= 3.0:
        return 2, f"今日大涨 {pct:+.2f}%"
    if pct >= 1.0:
        return 1, f"今日上涨 {pct:+.2f}%"
    if pct <= -3.0:
        return -2, f"今日大跌 {pct:+.2f}%"
    if pct <= -1.0:
        return -1, f"今日下跌 {pct:+.2f}%"
    return 0, f"今日持平 {pct:+.2f}%"


def _score_week(pct: Optional[float]) -> Tuple[int, str]:
    if pct is None:
        return 0, ""
    if pct >= 5.0:
        return 2, f"近一周累涨 {pct:+.2f}%，短期动能强劲"
    if pct >= 2.0:
        return 1, f"近一周上涨 {pct:+.2f}%"
    if pct <= -5.0:
        return -2, f"近一周累跌 {pct:+.2f}%，短期动能疲弱"
    if pct <= -2.0:
        return -1, f"近一周下跌 {pct:+.2f}%"
    return 0, ""


def _score_month(pct: Optional[float]) -> Tuple[int, str]:
    if pct is None:
        return 0, ""
    if pct >= 10.0:
        return 2, f"近一月累涨 {pct:+.2f}%，中期趋势向上"
    if pct >= 3.0:
        return 1, f"近一月上涨 {pct:+.2f}%"
    if pct <= -10.0:
        return -2, f"近一月累跌 {pct:+.2f}%，中期趋势向下"
    if pct <= -3.0:
        return -1, f"近一月下跌 {pct:+.2f}%"
    return 0, ""


def _score_vs_ma20(pct: Optional[float]) -> Tuple[int, str]:
    if pct is None:
        return 0, ""
    if pct >= 5.0:
        return 1, f"价格高于 MA20 {pct:+.2f}%，位于均线上方"
    if pct <= -5.0:
        return -1, f"价格低于 MA20 {pct:+.2f}%，跌破均线支撑"
    return 0, f"价格接近 MA20（偏差 {pct:+.2f}%）"


def _score_volume(ratio: Optional[float]) -> Tuple[int, str]:
    if ratio is None:
        return 0, ""
    if ratio >= 2.0:
        return 1, f"成交量为均量的 {ratio:.1f}x，放量明显"
    if ratio <= 0.4:
        return -1, f"成交量仅均量的 {ratio:.1f}x，缩量萎靡"
    return 0, ""


# ── 单资产评分 ────────────────────────────────────────────────────────────────

def evaluate_asset(ticker: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    对单只资产评分并生成信号。

    返回：
      {
        "ticker":        str,
        "signal":        str,        # strong_buy / buy / hold / sell / strong_sell
        "signal_label":  str,        # 中文标签
        "score":         int,
        "factors":       [str, ...], # 人类可读的评分因素
        "price_snapshot": dict,
      }
    """
    scores: List[int] = []
    factors: List[str] = []

    def _add(score: int, reason: str) -> None:
        scores.append(score)
        if reason:
            factors.append(reason)

    daily_pct  = _safe_float(data.get("daily_change_pct"))
    week_pct   = _safe_float(data.get("week_change_pct"))
    month_pct  = _safe_float(data.get("month_change_pct"))
    vs_ma20    = _safe_float(data.get("vs_ma20_pct"))
    vol_ratio  = _safe_float(data.get("volume_ratio"))

    has_data = any(v is not None for v in [daily_pct, week_pct, month_pct])
    if not has_data:
        return {
            "ticker":        ticker,
            "signal":        NO_DATA,
            "signal_label":  _SIGNAL_LABELS[NO_DATA],
            "score":         0,
            "factors":       ["数据不足，无法评分"],
            "price_snapshot": data,
        }

    s, r = _score_daily(daily_pct);  _add(s, r)
    s, r = _score_week(week_pct);    _add(s, r)
    s, r = _score_month(month_pct);  _add(s, r)
    s, r = _score_vs_ma20(vs_ma20);  _add(s, r)
    s, r = _score_volume(vol_ratio); _add(s, r)

    total  = sum(scores)
    signal = _score_to_signal(total)

    return {
        "ticker":        ticker,
        "signal":        signal,
        "signal_label":  _SIGNAL_LABELS[signal],
        "score":         total,
        "factors":       factors,
        "price_snapshot": {
            "latest_price":     data.get("latest_price"),
            "daily_change_pct": daily_pct,
            "week_change_pct":  week_pct,
            "month_change_pct": month_pct,
            "vs_ma20_pct":      vs_ma20,
            "volume_ratio":     vol_ratio,
        },
    }


# ── 全 watchlist 评分 ─────────────────────────────────────────────────────────

def evaluate_all(poll_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    对 poll_data["data"] 中所有资产评分，按信号分组返回。

    返回：
      {
        "ratings":   { ticker: evaluate_asset 结果 },
        "by_signal": { signal: [ticker, ...] },
        "top_picks": [评分最高的前 5 个资产],
        "avoid":     [评分最低的前 5 个资产],
      }
    """
    data = (poll_data or {}).get("data", {}) or {}
    ratings: Dict[str, Any] = {}

    for ticker, item in data.items():
        if not isinstance(item, dict):
            continue
        ratings[ticker] = evaluate_asset(ticker, item)

    # 按信号分组
    by_signal: Dict[str, List[str]] = {
        STRONG_BUY: [], BUY: [], HOLD: [], SELL: [], STRONG_SELL: [], NO_DATA: [],
    }
    for ticker, r in ratings.items():
        by_signal.setdefault(r["signal"], []).append(ticker)

    # 按评分排序，过滤掉无数据
    scored = [r for r in ratings.values() if r["signal"] != NO_DATA]
    scored_sorted = sorted(scored, key=lambda x: x["score"], reverse=True)

    top_picks = scored_sorted[:5]
    avoid     = scored_sorted[-5:][::-1]

    return {
        "ratings":   ratings,
        "by_signal": by_signal,
        "top_picks": top_picks,
        "avoid":     avoid,
    }
