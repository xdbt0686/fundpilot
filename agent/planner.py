from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from core.prompts import PLANNER_SYSTEM, build_planner_prompt
from core.llm import ask_llm


# ── 子任务结构 ────────────────────────────────────────────────────────────────

class SubTask:
    def __init__(
        self,
        id: int,
        task: str,
        tool: str,
        args: Dict[str, Any],
        depends_on: List[int],
    ) -> None:
        self.id         = id
        self.task       = task
        self.tool       = tool          # poll / overlap / compare / portfolio / profile / synthesize
        self.args       = args          # 传给工具的额外参数（如 compare 需要 ticker_a/b）
        self.depends_on = depends_on

    def __repr__(self) -> str:
        return f"SubTask(id={self.id}, tool={self.tool!r}, task={self.task!r})"


# ── JSON 解析（健壮版）────────────────────────────────────────────────────────

def _extract_json_array(text: str) -> Optional[List[Any]]:
    """从 LLM 输出中提取第一个 JSON 数组，容忍 markdown 代码块包裹。"""
    # 去掉可能的 ```json ... ``` 包裹
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

    # 找到第一个 [ ... ] 区间
    start = text.find("[")
    if start == -1:
        return None

    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _fallback_plan(question: str, watchlist: List[str]) -> List[SubTask]:
    """LLM 输出无法解析时的保底计划：单次轮询 + 综合。"""
    return [
        SubTask(0, "获取当前价格数据", "poll", {}, []),
        SubTask(1, f"回答用户问题：{question}", "synthesize", {}, [0]),
    ]


def _parse_plan(raw: Any, question: str, watchlist: List[str]) -> List[SubTask]:
    """将 LLM 返回的列表转换为 SubTask 对象，校验并修复常见问题。"""
    if not isinstance(raw, list) or not raw:
        return _fallback_plan(question, watchlist)

    valid_tools = {"poll", "overlap", "compare", "portfolio", "profile", "synthesize"}
    tasks: List[SubTask] = []

    for item in raw:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool", "synthesize")).lower().strip()
        if tool not in valid_tools:
            tool = "synthesize"

        tasks.append(SubTask(
            id         = int(item.get("id", len(tasks))),
            task       = str(item.get("task", "子任务")),
            tool       = tool,
            args       = item.get("args", {}) if isinstance(item.get("args"), dict) else {},
            depends_on = [int(x) for x in item.get("depends_on", []) if isinstance(x, (int, str)) and str(x).isdigit()],
        ))

    if not tasks:
        return _fallback_plan(question, watchlist)

    # 确保最后一个任务是 synthesize
    if tasks[-1].tool != "synthesize":
        all_ids = [t.id for t in tasks]
        tasks.append(SubTask(
            id         = max(all_ids) + 1,
            task       = "综合以上子任务结果，回答用户问题",
            tool       = "synthesize",
            args       = {},
            depends_on = all_ids,
        ))

    return tasks


# ── Planner 主类 ──────────────────────────────────────────────────────────────

class Planner:
    """
    调用 LLM 将用户问题拆解为有序子任务列表。

    用法：
        tasks = Planner().plan("VUAG 和 CSP1 今天有分化吗？", watchlist)
    """

    def plan(self, question: str, watchlist: List[str]) -> List[SubTask]:
        try:
            raw_text = ask_llm(PLANNER_SYSTEM, build_planner_prompt(question, watchlist))
        except Exception as e:
            print(f"[Planner] LLM 调用失败，使用保底计划：{e}")
            return _fallback_plan(question, watchlist)

        parsed = _extract_json_array(raw_text)
        if parsed is None:
            print(f"[Planner] JSON 解析失败，使用保底计划。原始输出：{raw_text[:200]}")
            return _fallback_plan(question, watchlist)

        tasks = _parse_plan(parsed, question, watchlist)
        print(f"[Planner] 计划 {len(tasks)} 个子任务：")
        for t in tasks:
            print(f"  [{t.id}] {t.tool} → {t.task}")

        return tasks
