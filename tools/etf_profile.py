from providers.static_provider import get_raw_etf_by_ticker
from normalizers.etf_normalizer import normalize_etf


def get_etf_profile(ticker: str) -> dict | None:
    raw = get_raw_etf_by_ticker(ticker)
    if not raw:
        return None

    return normalize_etf(raw)