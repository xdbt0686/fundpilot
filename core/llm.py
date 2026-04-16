from __future__ import annotations

import os
from typing import Any, Dict

import requests

BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
REQUEST_TIMEOUT = 120


def ask_llm(system_prompt: str, user_prompt: str) -> str:
    url = f"{BASE_URL}/v1/chat/completions"

    _guard = (
        "STOP. Do NOT describe, explain, or comment on the structure of any data. "
        "Do NOT say things like 'Let me break down', 'Here is a breakdown', "
        "'The JSON contains', 'The structure is', or similar meta-commentary. "
        "Answer the question directly and only.\n\n"
    )

    payload: Dict[str, Any] = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _guard + user_prompt},
        ],
        "stream": False,
    }

    resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    data = resp.json()

    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return str(data)