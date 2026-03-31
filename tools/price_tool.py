from providers.price_provider import get_latest_price_raw


def get_latest_price(ticker: str) -> dict | None:
    raw = get_latest_price_raw(ticker)
    if not raw:
        return None

    return raw