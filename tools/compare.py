from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.etf_profile import get_etf_profile


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


def compare_etfs(
    ticker_a: str,
    ticker_b: str,
    current_poll: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    对两只 ETF 做横向对比，涵盖 profile 差异 + 当前价格表现。

    返回：
      {
        "ticker_a", "ticker_b",
        "profile_a", "profile_b",
        "profile_diff":    { field: {ta: val, tb: val} },
        "price_diff":      { ta: {...}, tb: {...}, spread_pct, spread_note },
        "summary_points":  [str, ...]   # 人类可读要点
      }
    """
    ticker_a = ticker_a.upper().strip()
    ticker_b = ticker_b.upper().strip()

    profile_a = get_etf_profile(ticker_a) or {"ticker": ticker_a}
    profile_b = get_etf_profile(ticker_b) or {"ticker": ticker_b}

    profile_diff = _diff_profiles(ticker_a, profile_a, ticker_b, profile_b)
    price_diff   = _diff_prices(ticker_a, ticker_b, current_poll)
    summary      = _build_summary(profile_diff, price_diff, ticker_a, ticker_b)

    return {
        "ticker_a":      ticker_a,
        "ticker_b":      ticker_b,
        "profile_a":     profile_a,
        "profile_b":     profile_b,
        "profile_diff":  profile_diff,
        "price_diff":    price_diff,
        "summary_points": summary,
    }


def _diff_profiles(
    ta: str, pa: Dict[str, Any],
    tb: str, pb: Dict[str, Any],
) -> Dict[str, Any]:
    """提取两只 ETF profile 中有意义的差异字段。"""
    diff: Dict[str, Any] = {}

    fields = [
        "index_tracked", "region_scope", "includes_emerging_markets",
        "ter", "distribution_policy", "replication_method",
        "fund_domicile", "fund_size_gbp_m", "core_role", "provider",
    ]

    for field in fields:
        va = pa.get(field)
        vb = pb.get(field)
        if va != vb:
            diff[field] = {ta: va, tb: vb}

    # TER 绝对差值（正值表示 B 更贵）
    ter_a = _safe_float(pa.get("ter"))
    ter_b = _safe_float(pb.get("ter"))
    if ter_a is not None and ter_b is not None:
        diff["ter_gap"] = round(ter_b - ter_a, 4)

    # 规模倍数（B / A）
    size_a = _safe_float(pa.get("fund_size_gbp_m"))
    size_b = _safe_float(pb.get("fund_size_gbp_m"))
    if size_a and size_b:
        diff["size_ratio"] = round(size_b / size_a, 2)

    return diff


def _diff_prices(
    ta: str,
    tb: str,
    current_poll: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """从 current_poll 中提取两只 ETF 的当日价格表现对比。"""
    if not current_poll:
        return {}

    data   = current_poll.get("data", {}) or {}
    item_a = data.get(ta, {})
    item_b = data.get(tb, {})

    if not item_a and not item_b:
        return {}

    pct_a = _safe_float(item_a.get("daily_change_pct"))
    pct_b = _safe_float(item_b.get("daily_change_pct"))

    result: Dict[str, Any] = {
        ta: {"latest_price": item_a.get("latest_price"), "daily_change_pct": pct_a},
        tb: {"latest_price": item_b.get("latest_price"), "daily_change_pct": pct_b},
    }

    if pct_a is not None and pct_b is not None:
        spread = round(pct_a - pct_b, 4)
        result["spread_pct"] = spread
        if abs(spread) > 0.3:
            result["spread_note"] = (
                f"{ta} 今日比 {tb} 多 {spread:+.2f}%，存在明显价格分化"
            )

    return result


def _build_summary(
    profile_diff: Dict[str, Any],
    price_diff:   Dict[str, Any],
    ta: str,
    tb: str,
) -> List[str]:
    """生成人类可读的对比摘要要点列表。"""
    points: List[str] = []

    if "index_tracked" in profile_diff:
        v = profile_diff["index_tracked"]
        points.append(f"指数不同：{ta} 跟踪 {v.get(ta)}，{tb} 跟踪 {v.get(tb)}")
    else:
        points.append(f"{ta} 与 {tb} 跟踪相同指数")

    if "ter" in profile_diff:
        v   = profile_diff["ter"]
        gap = profile_diff.get("ter_gap", 0)
        points.append(
            f"费率：{ta} TER={v.get(ta)}%，{tb} TER={v.get(tb)}%"
            + (f"（差距 {gap:+.4f}%）" if gap else "")
        )

    if "distribution_policy" in profile_diff:
        v = profile_diff["distribution_policy"]
        points.append(f"分红政策：{ta}={v.get(ta)}，{tb}={v.get(tb)}")

    if "includes_emerging_markets" in profile_diff:
        v = profile_diff["includes_emerging_markets"]
        points.append(
            f"新兴市场敞口：{ta}={'含 EM' if v.get(ta) else '不含 EM'}，"
            f"{tb}={'含 EM' if v.get(tb) else '不含 EM'}"
        )

    if "size_ratio" in profile_diff:
        ratio = profile_diff["size_ratio"]
        points.append(f"规模倍数：{tb} 规模是 {ta} 的 {ratio}x")

    note = price_diff.get("spread_note")
    if note:
        points.append(note)

    return points
