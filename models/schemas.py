from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore


# ── 价格与轮询 ────────────────────────────────────────────────────────────────

class PriceData(TypedDict, total=False):
    ticker: str
    symbol: str
    latest_price: float
    previous_close: Optional[float]
    daily_change_pct: Optional[float]
    timestamp: str


class PollResult(TypedDict, total=False):
    polled_at: str
    data: Dict[str, PriceData]


# ── 告警与触发 ────────────────────────────────────────────────────────────────

class AlertEvent(TypedDict, total=False):
    event_type: str       # daily_move / reversal / stale_data / heartbeat_inspection
    severity: str         # high / medium / low
    ticker: Optional[str]
    title: str
    message: str
    extra: Dict[str, Any]


class MarketSummary(TypedDict, total=False):
    polled_at: str
    watchlist_size: int
    up_count: int
    down_count: int
    flat_count: int
    max_abs_move_ticker: Optional[str]
    max_abs_move_pct: float


class TriggerResult(TypedDict, total=False):
    should_run_ai: bool
    events: List[AlertEvent]
    inspection_needed: bool
    market_summary: MarketSummary


# ── ETF 基础信息 ──────────────────────────────────────────────────────────────

class ETFProfile(TypedDict, total=False):
    ticker: str
    name: str
    isin: str
    provider: str
    index_tracked: str
    region_scope: str
    includes_emerging_markets: bool
    ter: float
    distribution_policy: str
    replication_method: str
    fund_domicile: str
    fund_size_gbp_m: float
    core_role: str
    notes: str


# ── 工具输出 ──────────────────────────────────────────────────────────────────

class OverlapPair(TypedDict, total=False):
    ticker_a: str
    ticker_b: str
    overlap_pct: Optional[float]
    overlap_label: str      # 极高 / 高 / 中 / 低 / 极低 / unknown
    reason: str
    note: str


class OverlapReport(TypedDict, total=False):
    pairs: List[OverlapPair]
    high_overlap_pairs: List[OverlapPair]
    summary: str


class CompareResult(TypedDict, total=False):
    ticker_a: str
    ticker_b: str
    profile_a: ETFProfile
    profile_b: ETFProfile
    profile_diff: Dict[str, Any]
    price_diff: Dict[str, Any]
    summary_points: List[str]


class PortfolioHolding(TypedDict, total=False):
    name: str
    index_tracked: str
    region_family: str
    ter: Optional[float]
    distribution_policy: str
    includes_em: bool
    daily_change_pct: Optional[float]
    latest_price: Optional[float]


class PortfolioReport(TypedDict, total=False):
    tickers: List[str]
    holdings: Dict[str, PortfolioHolding]
    region_exposure: Dict[str, List[str]]
    accumulating_count: int
    distributing_count: int
    em_exposure_tickers: List[str]
    avg_ter: Optional[float]
    overlap_summary: str
    concentration_warnings: List[str]


# ── Agent 输出 ────────────────────────────────────────────────────────────────

class AgentResult(TypedDict, total=False):
    mode: str       # monitor / ask / overlap / compare / portfolio
    question: Optional[str]
    summary: Optional[MarketSummary]
    events: Optional[List[AlertEvent]]
    ai_text: str
    data: Optional[Dict[str, Any]]
