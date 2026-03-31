import yfinance as yf
from datetime import datetime


YF_MAP = {
    "VUAG": "VUAG.L",
    "CSP1": "CSP1.L",
    "SWDA": "SWDA.L",
    "HMWS": "HMWO.L",
    "VWRP": "VWRP.L",
    "VWRL": "VWRL.L",
}


def get_latest_price_raw(ticker: str) -> dict | None:
    ticker = ticker.upper().strip()
    yf_symbol = YF_MAP.get(ticker)

    if not yf_symbol:
        return None

    data = yf.Ticker(yf_symbol)
    hist = data.history(period="2d", interval="1d")

    if hist is None or hist.empty:
        return None

    latest_close = float(hist["Close"].iloc[-1])

    prev_close = None
    daily_change_pct = None

    if len(hist) >= 2:
        prev_close = float(hist["Close"].iloc[-2])
        if prev_close != 0:
            daily_change_pct = round((latest_close - prev_close) / prev_close * 100, 2)

    return {
        "ticker": ticker,
        "symbol": yf_symbol,
        "latest_price": round(latest_close, 4),
        "previous_close": round(prev_close, 4) if prev_close is not None else None,
        "daily_change_pct": daily_change_pct,
        "timestamp": datetime.now().isoformat(timespec="seconds")
    }