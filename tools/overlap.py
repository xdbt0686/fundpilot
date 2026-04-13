from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

from tools.etf_profile import get_etf_profile


# ── 指数族归类 ────────────────────────────────────────────────────────────────
# 将各种指数名称归入同一"族"，用于查表估算重叠度

_INDEX_FAMILY: Dict[str, str] = {
    "S&P 500":                  "us_large",
    "S&P 500 ESG":              "us_large",
    "MSCI USA":                 "us_large",
    "MSCI World":               "global_developed",
    "MSCI World ESG":           "global_developed",
    "FTSE Developed World":     "global_developed",
    "FTSE Developed":           "global_developed",
    "MSCI ACWI":                "global_all",
    "FTSE All-World":           "global_all",
    "MSCI ACWI ESG":            "global_all",
    "MSCI Emerging Markets":    "em_only",
    "FTSE Emerging":            "em_only",
    "MSCI EM":                  "em_only",
    "MSCI Europe":              "europe",
    "STOXX Europe 600":         "europe",
    "MSCI Japan":               "single_country",
    "Nikkei 225":               "single_country",
    "MSCI China":               "single_country",
}

# 两个族之间的理论重叠率（对称，取高值填充另一侧）
_FAMILY_OVERLAP: Dict[Tuple[str, str], float] = {
    ("us_large",         "us_large"):          0.97,
    ("us_large",         "global_developed"):  0.65,
    ("us_large",         "global_all"):        0.58,
    ("us_large",         "em_only"):           0.00,
    ("us_large",         "europe"):            0.00,
    ("us_large",         "single_country"):    0.02,
    ("global_developed", "global_developed"):  0.97,
    ("global_developed", "global_all"):        0.83,
    ("global_developed", "em_only"):           0.00,
    ("global_developed", "europe"):            0.22,
    ("global_developed", "single_country"):    0.05,
    ("global_all",       "global_all"):        0.97,
    ("global_all",       "em_only"):           0.15,
    ("global_all",       "europe"):            0.18,
    ("global_all",       "single_country"):    0.04,
    ("em_only",          "em_only"):           0.80,
    ("em_only",          "europe"):            0.00,
    ("em_only",          "single_country"):    0.10,
    ("europe",           "europe"):            0.90,
    ("europe",           "single_country"):    0.05,
    ("single_country",   "single_country"):    0.15,
}

_OVERLAP_UNKNOWN = "unknown"


def _get_family(index_name: str) -> Optional[str]:
    """将指数名称映射到族名；支持模糊匹配（包含关键词）。"""
    if not index_name:
        return None

    normalized = index_name.strip()

    # 精确匹配
    if normalized in _INDEX_FAMILY:
        return _INDEX_FAMILY[normalized]

    # 关键词包含匹配（处理带版本号/变体的名称）
    for key, family in _INDEX_FAMILY.items():
        if key.lower() in normalized.lower():
            return family

    return None


def _lookup_overlap(family_a: Optional[str], family_b: Optional[str]) -> Optional[float]:
    """从对称表中查询两个族的重叠率。"""
    if not family_a or not family_b:
        return None

    key = (family_a, family_b)
    if key in _FAMILY_OVERLAP:
        return _FAMILY_OVERLAP[key]

    key_rev = (family_b, family_a)
    if key_rev in _FAMILY_OVERLAP:
        return _FAMILY_OVERLAP[key_rev]

    return None


def _overlap_label(pct: float) -> str:
    """将重叠率转换为中文等级标签。"""
    if pct >= 0.90:
        return "极高"
    if pct >= 0.60:
        return "高"
    if pct >= 0.30:
        return "中"
    if pct >= 0.10:
        return "低"
    return "极低"


def _build_reason(profile_a: Dict[str, Any], profile_b: Dict[str, Any], overlap: float) -> str:
    """根据 profile 信息生成人类可读的重叠原因说明。"""
    idx_a = profile_a.get("index_tracked", "")
    idx_b = profile_b.get("index_tracked", "")
    ticker_a = profile_a.get("ticker", "A")
    ticker_b = profile_b.get("ticker", "B")

    if idx_a and idx_a == idx_b:
        return f"两者均跟踪 {idx_a}，指数完全相同"

    fa = _get_family(idx_a)
    fb = _get_family(idx_b)

    if fa and fa == fb:
        return f"跟踪同一指数族（{fa}）：{idx_a} vs {idx_b}"

    if overlap >= 0.60:
        return f"{ticker_a}（{idx_a}）覆盖范围包含大部分 {ticker_b}（{idx_b}）成分股"

    if overlap <= 0.05:
        return f"{ticker_a}（{idx_a}）与 {ticker_b}（{idx_b}）地域/风格几乎不重合"

    return f"{ticker_a}（{idx_a}）与 {ticker_b}（{idx_b}）存在部分区域交叉"


def _build_note(overlap: float, profile_a: Dict[str, Any], profile_b: Dict[str, Any]) -> str:
    """给出实用的持仓建议提示。"""
    ticker_a = profile_a.get("ticker", "A")
    ticker_b = profile_b.get("ticker", "B")

    if overlap >= 0.90:
        return f"持仓高度重复，{ticker_a} 与 {ticker_b} 同时持有意义不大，建议二选一"
    if overlap >= 0.60:
        return f"存在较大重叠，需确认是否有意增加该区域敞口"
    if overlap >= 0.30:
        return f"部分重叠，分散效果有限，留意总敞口占比"
    if overlap <= 0.05:
        return f"互补性强，组合持有可有效分散地域/风格风险"
    return f"重叠度适中，可结合目标配置权重评估是否值得同时持有"


# ── 核心对比函数 ──────────────────────────────────────────────────────────────

def compare_overlap(ticker_a: str, ticker_b: str) -> Dict[str, Any]:
    """
    估算两只 ETF 的持仓重叠度。

    返回：
      {
        "ticker_a": str,
        "ticker_b": str,
        "overlap_pct": float | None,   # 0.0–1.0，None 表示无法估算
        "overlap_label": str,          # 极高 / 高 / 中 / 低 / 极低 / unknown
        "reason": str,
        "note": str,
        "profiles": { ticker_a: {...}, ticker_b: {...} }
      }
    """
    ticker_a = ticker_a.upper().strip()
    ticker_b = ticker_b.upper().strip()

    profile_a = get_etf_profile(ticker_a) or {"ticker": ticker_a}
    profile_b = get_etf_profile(ticker_b) or {"ticker": ticker_b}

    idx_a = profile_a.get("index_tracked", "")
    idx_b = profile_b.get("index_tracked", "")

    family_a = _get_family(idx_a)
    family_b = _get_family(idx_b)
    overlap = _lookup_overlap(family_a, family_b)

    if overlap is None:
        return {
            "ticker_a": ticker_a,
            "ticker_b": ticker_b,
            "overlap_pct": None,
            "overlap_label": _OVERLAP_UNKNOWN,
            "reason": f"无法识别指数族：{idx_a!r} / {idx_b!r}",
            "note": "请手动核查两只 ETF 的指数构成",
            "profiles": {ticker_a: profile_a, ticker_b: profile_b},
        }

    return {
        "ticker_a": ticker_a,
        "ticker_b": ticker_b,
        "overlap_pct": round(overlap, 4),
        "overlap_label": _overlap_label(overlap),
        "reason": _build_reason(profile_a, profile_b, overlap),
        "note": _build_note(overlap, profile_a, profile_b),
        "profiles": {ticker_a: profile_a, ticker_b: profile_b},
    }


def analyze_watchlist_overlap(tickers: List[str]) -> Dict[str, Any]:
    """
    对 watchlist 中所有 ETF 两两做重叠分析。

    返回：
      {
        "pairs": [ { compare_overlap 结果 }, ... ],
        "high_overlap_pairs": [ (ticker_a, ticker_b, pct), ... ],  # pct >= 0.60
        "summary": str
      }
    """
    pairs: List[Dict[str, Any]] = []
    high_overlap: List[Dict[str, Any]] = []

    unique = list(dict.fromkeys(t.upper().strip() for t in tickers if t.strip()))

    for a, b in combinations(unique, 2):
        result = compare_overlap(a, b)
        pairs.append(result)

        pct = result.get("overlap_pct")
        if pct is not None and pct >= 0.60:
            high_overlap.append({
                "ticker_a": a,
                "ticker_b": b,
                "overlap_pct": pct,
                "overlap_label": result["overlap_label"],
            })

    high_overlap.sort(key=lambda x: x["overlap_pct"], reverse=True)

    if not high_overlap:
        summary = f"watchlist 共 {len(unique)} 只 ETF，两两重叠度均低于 60%，整体分散性良好。"
    else:
        top = high_overlap[0]
        summary = (
            f"watchlist 共 {len(unique)} 只 ETF，发现 {len(high_overlap)} 对高重叠组合。"
            f"重叠最高：{top['ticker_a']} vs {top['ticker_b']}（{top['overlap_pct']*100:.0f}%，{top['overlap_label']}）。"
        )

    return {
        "pairs": pairs,
        "high_overlap_pairs": high_overlap,
        "summary": summary,
    }
