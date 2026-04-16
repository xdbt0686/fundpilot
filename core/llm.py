from __future__ import annotations

import os
import re
from typing import Any, Dict

import requests

BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
REQUEST_TIMEOUT = None  # no timeout — 14b can be slow on first token


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
        text = data["choices"][0]["message"]["content"].strip()
        return _strip_meta(text)
    except Exception:
        return str(data)


# ── Post-processing: strip meta-commentary paragraphs ────────────────────────

_META_PATTERNS = re.compile(
    r"^.*("
    r"the data (provided|contains|shows|includes)|"
    r"let('s| me) (break|analyze|look|examine)|"
    r"here('s| is) (a |the )?(breakdown|analysis|summary|overview)|"
    r"the (json|structure|input|provided) (is|contains|shows|has)|"
    r"based on (the |this )?(data|input|json|information) provided|"
    r"for (a |the )?(focused |detailed |more )?analysis|"
    r"if you need (more|further|additional)|"
    r"please (specify|let me know|feel free)"
    r").*$",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_meta(text: str) -> str:
    """Remove lines that are pure meta-commentary about data structure."""
    lines = text.splitlines()
    cleaned = []
    skip_block = False

    for line in lines:
        stripped = line.strip()

        # Detect start of a meta-commentary section/paragraph
        if _META_PATTERNS.match(stripped):
            skip_block = True
            continue

        # A blank line ends a skipped block
        if not stripped:
            skip_block = False

        if not skip_block:
            cleaned.append(line)

    result = "\n".join(cleaned).strip()
    # Collapse 3+ consecutive blank lines to 2
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result if result else text  # fallback to original if everything got stripped