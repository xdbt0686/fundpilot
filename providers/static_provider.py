import json
from pathlib import Path

ETF_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "etfs.json"


def load_raw_etfs() -> list[dict]:
    with open(ETF_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_raw_etf_by_ticker(ticker: str) -> dict | None:
    ticker = ticker.upper().strip()
    etfs = load_raw_etfs()

    for etf in etfs:
        if etf.get("ticker", "").upper() == ticker:
            return etf

    return None