import json
from pathlib import Path
from datetime import datetime
from tools.price_tool import get_latest_price

BASE_DIR = Path(__file__).resolve().parent.parent
WATCHLIST_PATH = BASE_DIR / "data" / "watchlist.json"
PRICE_CACHE_PATH = BASE_DIR / "data" / "price_cache.json"


def load_watchlist() -> list[str]:
    with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_price_cache() -> dict:
    if not PRICE_CACHE_PATH.exists():
        return {}

    try:
        with open(PRICE_CACHE_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except Exception:
        return {}


def save_price_cache(data: dict):
    with open(PRICE_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def poll_once() -> dict:
    watchlist = load_watchlist()
    cache = load_price_cache()

    snapshot = {
        "polled_at": datetime.now().isoformat(timespec="seconds"),
        "data": {}
    }

    for ticker in watchlist:
        result = get_latest_price(ticker)
        if result:
            cache[ticker] = result
            snapshot["data"][ticker] = result

    save_price_cache(cache)
    return snapshot