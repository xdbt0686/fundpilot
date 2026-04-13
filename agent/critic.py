from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from core.prompts import CRITIC_SYSTEM, build_critic_prompt
from core.llm import ask_llm


# ── 校验结果结构 ──────────────────────────────────────────────────────────────

class CriticVerdict:
    def __init__(
        self,
        valid:  bool,
        issues: List[str],
        hint:   str,
    ) -> None:
        self.valid  = valid
        self.issues = issues
        self.hint   = hint      # 给 Executor 重跑时的修正提示

    def __repr__(self) -> str:
        status = "通过" if self.valid else "不通过"
        return f"CriticVerdict({status}, issues={self.issues})"


# ── JSON 解析 ─────────────────────────────────────────────────────────────────

def _parse_verdict(text: str) -> Optional[Dict[str, Any]]:
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _rule_based_check(
    answer:   str,
    raw_data: Dict[str, Any],
) -> List[str]:
    """
    不依赖 LLM 的规则校验，作为 LLM 校验的补充。
    检测最常见的幻觉类型：数字矛盾。
    """
    issues: List[str] = []

    for task_key, tool_output in raw_data.items():
        if not isinstance(tool_output, dict):
            continue

        data = tool_output.get("data", {})
        if not isinstance(data, dict):
            continue

        for ticker, item in data.items():
            pct = item.get("daily_change_pct")
            if pct is None:
                continue
            pct = float(pct)

            # 检测：答案中如果出现该 ticker，方向应与数据一致
            ticker_mentioned = ticker in answer
            if not ticker_mentioned:
                continue

            rose_in_answer = any(kw in answer for kw in ["上涨", "涨幅", "走强", "上行"])
            fell_in_answer = any(kw in answer for kw in ["下跌", "跌幅", "走弱", "下行"])

            if pct > 0.5 and fell_in_answer and not rose_in_answer:
                issues.append(
                    f"{ticker} 今日实际上涨 {pct:+.2f}%，但回答描述为下跌"
                )
            elif pct < -0.5 and rose_in_answer and not fell_in_answer:
                issues.append(
                    f"{ticker} 今日实际下跌 {pct:+.2f}%，但回答描述为上涨"
                )

    return issues


# ── Critic 主类 ───────────────────────────────────────────────────────────────

class Critic:
    """
    校验 Executor 生成的最终答案是否与原始数据一致。

    两层校验：
    1. 规则层：数字方向矛盾（快速，不调 LLM）
    2. LLM 层：语义层面的事实核查

    只要任一层发现问题，verdict.valid = False。
    """

    def verify(
        self,
        question: str,
        answer:   str,
        raw_data: Dict[str, Any],
    ) -> CriticVerdict:

        # ── 规则层校验 ────────────────────────────────────────────────────────
        rule_issues = _rule_based_check(answer, raw_data)

        # ── LLM 层校验 ────────────────────────────────────────────────────────
        llm_issues: List[str] = []
        hint = ""

        try:
            raw_text = ask_llm(
                CRITIC_SYSTEM,
                build_critic_prompt(question, answer, raw_data),
            )
            parsed = _parse_verdict(raw_text)

            if parsed:
                llm_valid  = bool(parsed.get("valid", True))
                llm_issues = parsed.get("issues", []) or []
                hint       = parsed.get("hint", "") or ""

                if not llm_valid and not hint:
                    hint = "请重新检查数据后重新综合回答。"
            else:
                # LLM 输出无法解析：仅依赖规则层
                print(f"[Critic] LLM 校验输出无法解析，跳过 LLM 层。")

        except Exception as e:
            print(f"[Critic] LLM 校验失败，跳过：{e}")

        all_issues = rule_issues + llm_issues
        is_valid   = len(all_issues) == 0

        if all_issues:
            print(f"[Critic] 发现 {len(all_issues)} 个问题：{all_issues}")
        else:
            print("[Critic] 校验通过。")

        return CriticVerdict(
            valid  = is_valid,
            issues = all_issues,
            hint   = hint or ("以下问题需修正：" + "；".join(all_issues) if all_issues else ""),
        )
