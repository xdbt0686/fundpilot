from __future__ import annotations

import math
import yfinance as yf
from datetime import datetime
from typing import Dict, List, Optional

# 已知符号覆盖：直接映射，跳过自动探测，避免首次启动的 404 噪音
_OVERRIDES: Dict[str, str] = {
    # UK ETF（London Stock Exchange，需要 .L 后缀）
    "VUAG": "VUAG.L",
    "CSP1": "CSP1.L",
    "SWDA": "SWDA.L",
    "HMWS": "HMWO.L",   # 内部名称与 Yahoo 符号不同
    "VWRP": "VWRP.L",
    "VWRL": "VWRL.L",
    "EQQQ": "EQQQ.L",
    "IUSA": "IUSA.L",
    "XDWD": "XDWD.L",
    "IEEM": "IEEM.L",
}

# 进程内符号解析缓存，避免重复网络探测
_SYMBOL_CACHE: Dict[str, Optional[str]] = {}

# 自动尝试的后缀顺序（空字符串 = 原样尝试）
_SUFFIXES = ["", ".L", ".AS", ".DE", ".PA", ".MI"]


def _resolve_symbol(ticker: str) -> Optional[str]:
    """将用户 ticker 映射到 yfinance 能识别的符号。"""
    if ticker in _SYMBOL_CACHE:
        return _SYMBOL_CACHE[ticker]

    # 优先覆盖表
    if ticker in _OVERRIDES:
        _SYMBOL_CACHE[ticker] = _OVERRIDES[ticker]
        return _OVERRIDES[ticker]

    # 指数（^开头）和加密货币（含 -）直接使用
    if ticker.startswith("^") or "-" in ticker:
        _SYMBOL_CACHE[ticker] = ticker
        return ticker

    # 已带交易所后缀（含 .）直接使用
    if "." in ticker:
        _SYMBOL_CACHE[ticker] = ticker
        return ticker

    # 依次尝试各后缀，找到有数据的就缓存并返回
    for suffix in _SUFFIXES:
        candidate = ticker + suffix
        try:
            hist = yf.Ticker(candidate).history(period="5d", interval="1d")
            if hist is not None and not hist.empty:
                _SYMBOL_CACHE[ticker] = candidate
                return candidate
        except Exception:
            continue

    _SYMBOL_CACHE[ticker] = None
    return None


def _safe(v, decimals: int = 4):
    try:
        return round(float(v), decimals) if v is not None else None
    except Exception:
        return None


def _classify_asset(ticker: str, symbol: str) -> str:
    if ticker.startswith("^"):
        return "index"
    if "-USD" in ticker or "-GBP" in ticker or "-EUR" in ticker:
        return "crypto"
    if symbol.endswith(".L"):
        return "uk_asset"
    if "." in symbol:
        return "intl_asset"
    return "us_asset"


def get_latest_price_raw(ticker: str) -> Optional[Dict]:
    ticker = ticker.upper().strip()
    symbol = _resolve_symbol(ticker)
    if not symbol:
        return None

    try:
        hist = yf.Ticker(symbol).history(period="1mo", interval="1d")
    except Exception:
        return None

    if hist is None or hist.empty:
        return None

    closes = hist["Close"].dropna()

    if len(closes) < 1:
        return None

    latest_close = float(closes.iloc[-1])
    prev_close   = float(closes.iloc[-2]) if len(closes) >= 2 else None

    # Anchor all same-bar fields to the exact date of the latest close,
    # so latest_price, day_high, day_low, and volume always come from the
    # same bar rather than each series' own last non-NaN row.
    last_date = closes.index[-1]

    def _bar_val(col):
        """Return the value at last_date for col, or None if missing/NaN."""
        if col not in hist.columns:
            return None
        v = hist.at[last_date, col]
        try:
            return None if math.isnan(float(v)) else v
        except (TypeError, ValueError):
            return None

    day_high = _safe(_bar_val("High"))
    day_low  = _safe(_bar_val("Low"))

    raw_vol       = _bar_val("Volume")
    latest_volume = int(raw_vol) if raw_vol is not None else None

    daily_change_pct = None
    if prev_close and prev_close != 0:
        daily_change_pct = round((latest_close - prev_close) / prev_close * 100, 2)

    # 周涨跌（约 5 个交易日前）——同时存点数，避免 LLM 用错公式推算
    week_change_pct    = None
    week_change_points = None
    if len(closes) >= 6:
        week_ago = float(closes.iloc[-6])
        if week_ago != 0:
            week_change_pct    = round((latest_close - week_ago) / week_ago * 100, 2)
            week_change_points = round(latest_close - week_ago, 4)

    # 月涨跌
    month_change_pct = None
    if len(closes) >= 2:
        p = float(closes.iloc[0])
        if p != 0:
            month_change_pct = round((latest_close - p) / p * 100, 2)

    # 移动均线
    ma5  = _safe(closes.tail(5).mean())  if len(closes) >= 5  else None
    ma20 = _safe(closes.tail(20).mean()) if len(closes) >= 20 else None

    vs_ma20_pct = None
    if ma20 and ma20 != 0:
        vs_ma20_pct = round((latest_close - ma20) / ma20 * 100, 2)

    # 平均成交量对齐到 closes 的日期索引，避免跨系列的 bar 偏移
    if "Volume" in hist.columns:
        aligned_vol = hist["Volume"].reindex(closes.index).dropna()
        avg_volume  = int(aligned_vol.tail(20).mean()) if len(aligned_vol) >= 2 else None
    else:
        avg_volume = None
    volume_ratio = round(latest_volume / avg_volume, 2) if latest_volume and avg_volume and avg_volume > 0 else None

    return {
        "ticker":              ticker,
        "symbol":              symbol,
        "asset_type":          _classify_asset(ticker, symbol),
        "latest_price":        _safe(latest_close),
        "previous_close":      _safe(prev_close),
        "day_high":            day_high,
        "day_low":             day_low,
        "daily_change_pct":    daily_change_pct,
        "week_change_pct":     week_change_pct,
        "week_change_points":  week_change_points,
        "month_change_pct":    month_change_pct,
        "ma5":                 ma5,
        "ma20":                ma20,
        "vs_ma20_pct":         vs_ma20_pct,
        "volume":              latest_volume,
        "avg_volume":          avg_volume,
        "volume_ratio":        volume_ratio,
        "data_date":           str(last_date.date()),
        "timestamp":           datetime.now().isoformat(timespec="seconds"),
    }
