from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.etf_profile import get_etf_profile
from tools.overlap import analyze_watchlist_overlap


# ── 指数族 → 中文地域标签 ─────────────────────────────────────────────────────

_INDEX_FAMILY: Dict[str, str] = {
    "S&P 500":               "us_large",
    "S&P 500 ESG":           "us_large",
    "MSCI USA":              "us_large",
    "MSCI World":            "global_developed",
    "MSCI World ESG":        "global_developed",
    "FTSE Developed":        "global_developed",
    "FTSE Developed World":  "global_developed",
    "MSCI ACWI":             "global_all",
    "FTSE All-World":        "global_all",
    "MSCI Emerging Markets": "em_only",
    "FTSE Emerging":         "em_only",
    "MSCI EM":               "em_only",
    "MSCI Europe":           "europe",
    "STOXX Europe 600":      "europe",
}

_FAMILY_LABEL: Dict[str, str] = {
    "us_large":         "美国大盘",
    "global_developed": "全球发达市场",
    "global_all":       "全球全市场（含新兴）",
    "em_only":          "纯新兴市场",
    "europe":           "欧洲",
    "single_country":   "单一国家",
    "unknown":          "未知地域",
}


def _infer_family(index_tracked: str) -> str:
    for key, family in _INDEX_FAMILY.items():
        if key.lower() in index_tracked.lower():
            return family
    return "unknown"


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def analyze_portfolio(
    tickers: List[str],
    current_poll: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    对 watchlist 做整体组合分析，输出地域分布、费率、分红类型、EM 敞口
    以及与重叠分析的组合使用结果。

    返回：
      {
        "tickers":                 [str],
        "holdings":                { ticker: PortfolioHolding },
        "region_exposure":         { region_label: [tickers] },
        "accumulating_count":      int,
        "distributing_count":      int,
        "em_exposure_tickers":     [str],
        "avg_ter":                 float | None,
        "overlap_summary":         str,
        "concentration_warnings":  [str],
      }
    """
    tickers   = [t.upper().strip() for t in tickers if t.strip()]
    poll_data = (current_poll or {}).get("data", {}) or {}

    holdings:        Dict[str, Any]        = {}
    region_exposure: Dict[str, List[str]]  = {}
    em_tickers:      List[str]             = []
    ter_values:      List[float]           = []
    acc_count  = 0
    dist_count = 0

    for ticker in tickers:
        profile    = get_etf_profile(ticker) or {"ticker": ticker}
        price_item = poll_data.get(ticker, {})

        index_tracked = profile.get("index_tracked", "")
        family        = _infer_family(index_tracked)
        region_label  = _FAMILY_LABEL.get(family, "未知地域")
        region_exposure.setdefault(region_label, []).append(ticker)

        includes_em = bool(profile.get("includes_emerging_markets"))
        if includes_em or family == "em_only":
            em_tickers.append(ticker)

        policy = (profile.get("distribution_policy") or "").lower()
        if "accum" in policy:
            acc_count += 1
        elif "dist" in policy or "income" in policy:
            dist_count += 1

        ter = _safe_float(profile.get("ter"))
        if ter is not None:
            ter_values.append(ter)

        holdings[ticker] = {
            "name":                profile.get("name", ""),
            "index_tracked":       index_tracked,
            "region_family":       region_label,
            "ter":                 ter,
            "distribution_policy": profile.get("distribution_policy", ""),
            "includes_em":         includes_em,
            "daily_change_pct":    _safe_float(price_item.get("daily_change_pct")),
            "latest_price":        price_item.get("latest_price"),
        }

    avg_ter = round(sum(ter_values) / len(ter_values), 4) if ter_values else None

    try:
        overlap_report  = analyze_watchlist_overlap(tickers)
        overlap_summary = overlap_report.get("summary", "")
    except Exception as e:
        overlap_summary = f"重叠分析失败：{e}"

    warnings = _build_warnings(region_exposure, em_tickers, tickers)

    return {
        "tickers":               tickers,
        "holdings":              holdings,
        "region_exposure":       region_exposure,
        "accumulating_count":    acc_count,
        "distributing_count":    dist_count,
        "em_exposure_tickers":   em_tickers,
        "avg_ter":               avg_ter,
        "overlap_summary":       overlap_summary,
        "concentration_warnings": warnings,
    }


def _build_warnings(
    region_exposure: Dict[str, List[str]],
    em_tickers:      List[str],
    all_tickers:     List[str],
) -> List[str]:
    warnings: List[str] = []
    total = len(all_tickers)

    for region, members in region_exposure.items():
        if len(members) >= 2 and len(members) / total >= 0.5:
            warnings.append(
                f"地域集中：{len(members)}/{total} 只 ETF 属于 [{region}]"
                f"（{', '.join(members)}）"
            )

    if not em_tickers:
        warnings.append("组合中无新兴市场敞口，缺乏地域多样性")

    return warnings
