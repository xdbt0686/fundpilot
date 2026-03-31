def check_price_alert(price_data: dict, drop_threshold: float = -2.0, rise_threshold: float = 2.0) -> dict | None:
    """
    根据 daily_change_pct 判断是否触发提醒。
    默认：
    - 跌幅 <= -2.0% 触发下跌提醒
    - 涨幅 >=  2.0% 触发上涨提醒
    """
    if not price_data:
        return None

    daily_change_pct = price_data.get("daily_change_pct")
    if daily_change_pct is None:
        return None

    if daily_change_pct <= drop_threshold:
        return {
            "triggered": True,
            "alert_type": "price_drop",
            "message": f"{price_data['ticker']} 今日跌幅 {daily_change_pct}%，已触发下跌提醒。",
            "price_data": price_data
        }

    if daily_change_pct >= rise_threshold:
        return {
            "triggered": True,
            "alert_type": "price_rise",
            "message": f"{price_data['ticker']} 今日涨幅 {daily_change_pct}%，已触发上涨提醒。",
            "price_data": price_data
        }

    return {
        "triggered": False,
        "alert_type": "none",
        "message": f"{price_data['ticker']} 今日涨跌幅 {daily_change_pct}%，未触发提醒。",
        "price_data": price_data
    }