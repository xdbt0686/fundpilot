from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.planner import SubTask
from core.prompts import EXECUTOR_SYSTEM, SYNTHESIZER_SYSTEM
from core.prompts import build_executor_prompt, build_synthesizer_prompt
from core.llm import ask_llm


# ── 子任务执行结果 ────────────────────────────────────────────────────────────

class SubTaskResult:
    def __init__(
        self,
        task:           SubTask,
        tool_output:    Any,
        interpretation: str,
    ) -> None:
        self.id             = task.id
        self.task           = task.task
        self.tool           = task.tool
        self.tool_output    = tool_output
        self.interpretation = interpretation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":             self.id,
            "task":           self.task,
            "tool":           self.tool,
            "tool_output":    self.tool_output,
            "interpretation": self.interpretation,
        }


# ── 工具分发 ──────────────────────────────────────────────────────────────────

def _run_tool(
    task:         SubTask,
    current_poll: Dict[str, Any],
    watchlist:    List[str],
) -> Any:
    """根据 task.tool 调用对应工具，返回原始数据。"""

    if task.tool == "poll":
        return current_poll

    if task.tool == "overlap":
        tickers = task.args.get("tickers") or watchlist
        from tools.overlap import analyze_watchlist_overlap
        return analyze_watchlist_overlap(tickers)

    if task.tool == "compare":
        ta = task.args.get("ticker_a") or ""
        tb = task.args.get("ticker_b") or ""
        # 从 task 描述中尝试提取 ticker（兜底）
        if not ta or not tb:
            found = [t for t in watchlist if t in task.task.upper()]
            ta = found[0] if len(found) > 0 else watchlist[0] if watchlist else "VUAG"
            tb = found[1] if len(found) > 1 else watchlist[1] if len(watchlist) > 1 else "CSP1"
        from tools.compare import compare_etfs
        return compare_etfs(ta, tb, current_poll)

    if task.tool == "portfolio":
        tickers = task.args.get("tickers") or watchlist
        from tools.portfolio import analyze_portfolio
        return analyze_portfolio(tickers, current_poll)

    if task.tool == "profile":
        ticker = task.args.get("ticker") or ""
        if not ticker:
            found = [t for t in watchlist if t in task.task.upper()]
            ticker = found[0] if found else watchlist[0]
        from tools.etf_profile import get_etf_profile
        return get_etf_profile(ticker) or {"error": f"未找到 {ticker}"}

    # synthesize 不调工具
    return None


# ── Executor 主类 ─────────────────────────────────────────────────────────────

class Executor:
    """
    按拓扑顺序执行 Planner 产出的子任务列表。

    - 每个非 synthesize 任务：调工具 → LLM 解读 → 得到 interpretation
    - synthesize 任务：收集所有前驱结果 → LLM 综合 → 得到最终答案
    """

    def execute(
        self,
        tasks:        List[SubTask],
        question:     str,
        current_poll: Dict[str, Any],
        watchlist:    List[str],
        critic_hint:  Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        返回：
          {
            "final_answer":   str,
            "subtask_results": [SubTaskResult.to_dict(), ...],
            "raw_data":        dict,   # 用于 Critic 校验
          }
        """
        results:  Dict[int, SubTaskResult] = {}
        raw_data: Dict[str, Any]           = {}

        # 拓扑执行（简单顺序，依赖关系由 Planner 保证前置）
        for task in tasks:
            print(f"[Executor] 执行子任务 [{task.id}] {task.tool}: {task.task}")

            if task.tool == "synthesize":
                # 取所有前驱结果 + 可能的 critic 修正提示
                predecessors = [
                    results[dep].to_dict()
                    for dep in task.depends_on
                    if dep in results
                ]

                system = SYNTHESIZER_SYSTEM
                user   = build_synthesizer_prompt(question, predecessors)
                if critic_hint:
                    user += f"\n\n[上一轮审查反馈，请针对性修正]\n{critic_hint}"

                try:
                    answer = ask_llm(system, user).strip()
                except Exception as e:
                    answer = f"综合失败：{e}"

                results[task.id] = SubTaskResult(task, None, answer)

            else:
                # 执行工具
                try:
                    tool_output = _run_tool(task, current_poll, watchlist)
                except Exception as e:
                    tool_output = {"error": str(e)}

                raw_data[f"task_{task.id}_{task.tool}"] = tool_output

                # LLM 解读工具输出
                try:
                    interp = ask_llm(
                        EXECUTOR_SYSTEM,
                        build_executor_prompt(task.task, task.tool, tool_output),
                    ).strip()
                except Exception as e:
                    interp = f"解读失败：{e}"

                results[task.id] = SubTaskResult(task, tool_output, interp)

        # 找最终答案（最后一个 synthesize 任务）
        final_answer = ""
        for task in reversed(tasks):
            if task.tool == "synthesize" and task.id in results:
                final_answer = results[task.id].interpretation
                break

        if not final_answer:
            # 没有 synthesize 则拼接所有解读
            final_answer = "\n\n".join(
                f"**{r.task}**\n{r.interpretation}"
                for r in results.values()
                if r.interpretation
            )

        return {
            "final_answer":    final_answer,
            "subtask_results": [r.to_dict() for r in results.values()],
            "raw_data":        raw_data,
        }
