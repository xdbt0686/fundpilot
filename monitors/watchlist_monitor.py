from tools.price_tool import get_latest_price
from rules.price_rules import check_price_alert


def monitor_watchlist(tickers: list[str], drop_threshold: float = -2.0, rise_threshold: float = 2.0) -> list[dict]:
    results = []

    for ticker in tickers:
        price_data = get_latest_price(ticker)
        if not price_data:
            results.append({
                "ticker": ticker,
                "triggered": False,
                "alert_type": "data_error",
                "message": f"{ticker} 未获取到价格数据。"
            })
            continue

        alert = check_price_alert(
            price_data=price_data,
            drop_threshold=drop_threshold,
            rise_threshold=rise_threshold
        )
        results.append(alert)

    return results