from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.etf_profile import get_etf_profile
from core.prompts import (
    get_monitor_system, build_monitor_prompt,
    get_ask_system, build_ask_prompt,
)

try:
    from core.llm import ask_llm
except Exception as e:
    ask_llm = None
    _llm_import_error = str(e)
else:
    _llm_import_error = None


def _load_profiles_for_tickers(tickers: List[str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for t in tickers:
        try:
            result[t] = get_etf_profile(t)
        except Exception as e:
            result[t] = {"ticker": t, "error": str(e)}
    return result


def _call_local_llm(system_prompt: str, user_prompt: str) -> str:
    if ask_llm is None:
        return f"LLM import failed: {_llm_import_error}"
    try:
        result = ask_llm(system_prompt, user_prompt)
        return result.strip() if isinstance(result, str) else str(result).strip()
    except Exception as e:
        return f"LLM call failed: {type(e).__name__}: {e}"


class EventAgent:
    def __init__(self) -> None:
        pass

    def analyze_monitor_cycle(
        self,
        current_poll: Dict[str, Any],
        trigger_result: Dict[str, Any],
        profiles: Optional[Dict[str, Any]] = None,
        lang: str = "zh",
    ) -> Dict[str, Any]:
        data = (current_poll or {}).get("data", {}) or {}
        tickers = list(data.keys())

        if profiles is None:
            profiles = _load_profiles_for_tickers(tickers)

        answer = _call_local_llm(
            get_monitor_system(lang),
            build_monitor_prompt(current_poll, trigger_result, profiles, lang=lang),
        )

        return {
            "mode":    "monitor",
            "summary": trigger_result.get("market_summary", {}),
            "events":  trigger_result.get("events", []),
            "ai_text": answer,
        }

    def answer_user_question(
        self,
        user_question: str,
        current_poll: Dict[str, Any],
        profiles: Optional[Dict[str, Any]] = None,
        extra_context: Optional[Dict[str, Any]] = None,
        lang: str = "zh",
    ) -> Dict[str, Any]:
        data = (current_poll or {}).get("data", {}) or {}
        tickers = list(data.keys())

        if profiles is None:
            profiles = _load_profiles_for_tickers(tickers)

        answer = _call_local_llm(
            get_ask_system(lang),
            build_ask_prompt(user_question, current_poll, profiles, extra_context, lang=lang),
        )

        return {
            "mode":     "ask",
            "question": user_question,
            "ai_text":  answer,
        }