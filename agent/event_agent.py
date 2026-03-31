from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from tools.etf_profile import get_etf_profile

try:
    from core.llm import ask_llm
except Exception as e:
    ask_llm = None
    _llm_import_error = str(e)
else:
    _llm_import_error = None


def _compact_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


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
        if isinstance(result, str):
            return result.strip()
        return str(result).strip()
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
    ) -> Dict[str, Any]:
        data = (current_poll or {}).get("data", {}) or {}
        tickers = list(data.keys())

        if profiles is None:
            profiles = _load_profiles_for_tickers(tickers)

        system_prompt = """
You are FundPilot, a local AI monitoring agent for UK-buyable UCITS ETFs.

You are not a generic investment app and not a China mutual fund assistant.
You are part of a Windows local monitoring workflow focused on a UK ETF watchlist.

Your job:
- interpret the latest watchlist data
- identify meaningful movement or lack of movement
- explain what it means for monitoring
- suggest what to watch next

Rules:
1. Use the latest dynamic market data as the primary evidence.
2. Use ETF profile data only as background context.
3. Do not invent live news, macro events, or company events unless they appear in the input.
4. Do not sound like you have certainty about future price direction.
5. Be practical, concise, and monitoring-oriented.
6. Output must be in Chinese.
7. Prefer structured output with these sections:
   - 本轮概况
   - 重点事件
   - 对 watchlist 的含义
   - 建议动作
8. If there is no major anomaly, still provide a useful inspection summary.
""".strip()

        user_prompt = f"""
请基于以下输入，给出本轮 ETF watchlist 自动监控分析。

[Latest poll]
{_compact_json(current_poll)}

[Trigger result]
{_compact_json(trigger_result)}

[ETF profiles]
{_compact_json(profiles)}
""".strip()

        answer = _call_local_llm(system_prompt, user_prompt)

        return {
            "mode": "monitor",
            "summary": trigger_result.get("market_summary", {}),
            "events": trigger_result.get("events", []),
            "ai_text": answer,
        }

    def answer_user_question(
        self,
        user_question: str,
        current_poll: Dict[str, Any],
        profiles: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        data = (current_poll or {}).get("data", {}) or {}
        tickers = list(data.keys())

        if profiles is None:
            profiles = _load_profiles_for_tickers(tickers)

        system_prompt = """
You are FundPilot, a local AI agent for a Windows-based UK UCITS ETF monitoring project.

You answer user questions based on the latest available ETF watchlist data.

Rules:
1. Use current poll data as the main evidence.
2. Use ETF profile data as background knowledge only.
3. Do not invent live news or macro facts not present in the input.
4. Be direct, practical, and monitoring-oriented.
5. If the user asks for comparison, focus on current movement, overlap, exposure style, and what to watch next.
6. Do not give overconfident financial predictions.
7. Output must be in Chinese.
""".strip()

        user_prompt = f"""
用户问题：
{user_question}

请基于下面的当前数据回答。

[Latest poll]
{_compact_json(current_poll)}

[ETF profiles]
{_compact_json(profiles)}
""".strip()

        answer = _call_local_llm(system_prompt, user_prompt)

        return {
            "mode": "ask",
            "question": user_question,
            "ai_text": answer,
        }