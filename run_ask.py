from __future__ import annotations

import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from agent.event_agent import EventAgent
from monitors.price_poller import poll_once

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_watchlist() -> List[str]:
    data = load_json(WATCHLIST_FILE, {})
    if isinstance(data, dict):
        items = data.get("tickers") or data.get("watchlist") or []
        if isinstance(items, list):
            return [str(x).upper().strip() for x in items if str(x).strip()]
    elif isinstance(data, list):
        return [str(x).upper().strip() for x in data if str(x).strip()]
    return ["VUAG", "CSP1", "SWDA", "HMWS", "VWRP", "VWRL"]


def normalize_poll_result(raw: Any, watchlist: List[str]) -> Dict[str, Any]:
    ts = now_iso()

    if isinstance(raw, dict):
        if "data" in raw and isinstance(raw["data"], dict):
            raw.setdefault("polled_at", ts)
            return raw

        maybe_map = {}
        ok = True
        for k, v in raw.items():
            if not isinstance(k, str) or not isinstance(v, dict):
                ok = False
                break
            maybe_map[k.upper()] = v

        if ok and maybe_map:
            return {
                "polled_at": ts,
                "data": maybe_map,
            }

    if isinstance(raw, list):
        data_map: Dict[str, Any] = {}

        if all(isinstance(x, dict) for x in raw):
            for item in raw:
                ticker = (
                    item.get("ticker")
                    or item.get("symbol")
                    or item.get("code")
                    or item.get("name")
                )
                if not ticker:
                    continue
                ticker = str(ticker).upper().strip()
                data_map[ticker] = item

            if data_map:
                return {
                    "polled_at": ts,
                    "data": data_map,
                }

        if len(raw) == len(watchlist):
            for ticker, item in zip(watchlist, raw):
                if isinstance(item, dict):
                    data_map[ticker] = item
                else:
                    data_map[ticker] = {
                        "ticker": ticker,
                        "raw_value": item,
                    }

            return {
                "polled_at": ts,
                "data": data_map,
            }

    raise RuntimeError(
        f"Unsupported poll_once() return type: {type(raw).__name__}, value={raw!r}"
    )


def call_poll_once_compat(watchlist: List[str]) -> Dict[str, Any]:
    try:
        sig = inspect.signature(poll_once)
        if len(sig.parameters) == 0:
            raw = poll_once()
        else:
            raw = poll_once(watchlist)
    except (TypeError, ValueError):
        try:
            raw = poll_once(watchlist)
        except TypeError:
            raw = poll_once()

    result = normalize_poll_result(raw, watchlist)
    result.setdefault("polled_at", now_iso())
    result.setdefault("data", {})
    return result


def main() -> None:
    if len(sys.argv) >= 2:
        question = " ".join(sys.argv[1:]).strip()
    else:
        question = input("请输入你的问题：").strip()

    if not question:
        print("问题不能为空。")
        return

    watchlist = load_watchlist()
    current_poll = call_poll_once_compat(watchlist)

    agent = EventAgent()
    result = agent.answer_user_question(
        user_question=question,
        current_poll=current_poll,
    )

    print("\n=== AGENT ANSWER ===\n")
    print(result.get("ai_text", ""))


if __name__ == "__main__":
    main()