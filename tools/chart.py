from __future__ import annotations

from pathlib import Path
from typing import Optional

import mplfinance as mpf
import pandas as pd
import yfinance as yf

from providers.price_provider import _resolve_symbol

# ── 配置 ──────────────────────────────────────────────────────────────────────

CHARTS_DIR = Path(__file__).resolve().parent.parent / "data" / "charts"

_STYLE = mpf.make_mpf_style(
    base_mpf_style="nightclouds",
    marketcolors=mpf.make_marketcolors(
        up="#26a69a",
        down="#ef5350",
        edge="inherit",
        wick="inherit",
        volume={"up": "#26a69a", "down": "#ef5350"},
    ),
    gridstyle="--",
    gridcolor="#2a2a2a",
    facecolor="#1a1a2e",
    figcolor="#1a1a2e",
    rc={"font.size": 9},
)

_VALID_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "5y"}
_PERIOD_LABELS = {
    "1mo": "1 Month",
    "3mo": "3 Months",
    "6mo": "6 Months",
    "1y":  "1 Year",
    "2y":  "2 Years",
    "5y":  "5 Years",
}


# ── 主函数 ────────────────────────────────────────────────────────────────────

def plot_kline(
    ticker: str,
    period: str = "3mo",
    show: bool = True,
    save: bool = False,
) -> Optional[Path]:
    """
    为指定 ticker 绘制 K 线图（含 MA5、MA20、成交量）。

    参数：
        ticker  — 资产代码（如 VUAG、AAPL、BTC-USD）
        period  — 时间跨度，合法值：1mo / 3mo / 6mo / 1y / 2y / 5y
        show    — 是否弹出交互窗口
        save    — 是否保存到 data/charts/<ticker>_<period>.png

    返回：
        保存路径（save=True 时），否则 None
    """
    ticker = ticker.upper().strip()
    if period not in _VALID_PERIODS:
        period = "3mo"

    symbol = _resolve_symbol(ticker)
    if not symbol:
        raise ValueError(f"无法解析 ticker：{ticker}")

    hist = yf.Ticker(symbol).history(period=period, interval="1d")
    if hist is None or hist.empty:
        raise ValueError(f"未能获取 {ticker} 的历史数据（symbol={symbol}）")

    # mplfinance 要求列名为 Open/High/Low/Close/Volume
    df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index)
    df.index = df.index.tz_localize(None)   # 去掉 tz 信息，避免 mplfinance 报错
    df = df[df["Volume"] >= 0]              # 过滤掉无效行

    # 计算叠加均线
    ma5  = df["Close"].rolling(5).mean()
    ma20 = df["Close"].rolling(20).mean()
    addplots = [
        mpf.make_addplot(ma5,  color="#f5a623", width=1.2, label="MA5"),
        mpf.make_addplot(ma20, color="#7b61ff", width=1.2, label="MA20"),
    ]

    period_label = _PERIOD_LABELS.get(period, period)
    title = f"{ticker}  {period_label} Candlestick"

    kwargs = dict(
        type="candle",
        style=_STYLE,
        addplot=addplots,
        volume=True,
        title=title,
        figsize=(14, 8),
        tight_layout=True,
        warn_too_much_data=len(df) + 1,
    )

    save_path: Optional[Path] = None
    if save:
        CHARTS_DIR.mkdir(parents=True, exist_ok=True)
        save_path = CHARTS_DIR / f"{ticker}_{period}.png"
        kwargs["savefig"] = dict(fname=str(save_path), dpi=150, bbox_inches="tight")

    if show:
        mpf.plot(df, **kwargs)
    elif save:
        mpf.plot(df, **kwargs)

    return save_path


# ── 历史数据摘要（供 agent history 工具使用）─────────────────────────────────

def get_history_summary(ticker: str, period: str = "3mo") -> dict:
    """
    返回可供 LLM 解读的历史行情摘要，不绘图。

    返回：
      {
        "ticker", "period", "symbol",
        "start_date", "end_date", "trading_days",
        "start_price", "end_price", "total_change_pct",
        "period_high", "period_low", "drawdown_from_high_pct",
        "avg_daily_volume", "ma5_latest", "ma20_latest",
        "above_ma20": bool,
        "weekly_returns": [float, ...],   # 每周收益率，最近8周
      }
    """
    ticker = ticker.upper().strip()
    if period not in _VALID_PERIODS:
        period = "3mo"

    symbol = _resolve_symbol(ticker)
    if not symbol:
        return {"error": f"无法解析 ticker：{ticker}"}

    try:
        hist = yf.Ticker(symbol).history(period=period, interval="1d")
    except Exception as e:
        return {"error": str(e)}

    if hist is None or hist.empty:
        return {"error": f"未能获取 {ticker} 历史数据"}

    closes  = hist["Close"].dropna()
    volumes = hist["Volume"].dropna() if "Volume" in hist else pd.Series(dtype=float)

    start_price = round(float(closes.iloc[0]),  4)
    end_price   = round(float(closes.iloc[-1]), 4)
    total_pct   = round((end_price - start_price) / start_price * 100, 2) if start_price else None

    period_high = round(float(closes.max()), 4)
    period_low  = round(float(closes.min()), 4)
    drawdown    = round((end_price - period_high) / period_high * 100, 2) if period_high else None

    ma5_latest  = round(float(closes.tail(5).mean()),  4) if len(closes) >= 5  else None
    ma20_latest = round(float(closes.tail(20).mean()), 4) if len(closes) >= 20 else None
    above_ma20  = (end_price > ma20_latest) if ma20_latest else None

    avg_vol = int(volumes.mean()) if len(volumes) >= 2 else None

    # 最近 8 周的周收益率
    weekly = (
        closes.resample("W").last().pct_change().dropna().tail(8)
        .mul(100).round(2).tolist()
    )

    return {
        "ticker":                ticker,
        "period":                period,
        "symbol":                symbol,
        "start_date":            str(closes.index[0].date()),
        "end_date":              str(closes.index[-1].date()),
        "trading_days":          len(closes),
        "start_price":           start_price,
        "end_price":             end_price,
        "total_change_pct":      total_pct,
        "period_high":           period_high,
        "period_low":            period_low,
        "drawdown_from_high_pct": drawdown,
        "avg_daily_volume":      avg_vol,
        "ma5_latest":            ma5_latest,
        "ma20_latest":           ma20_latest,
        "above_ma20":            above_ma20,
        "weekly_returns":        weekly,
    }
