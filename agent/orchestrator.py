from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.planner import Planner
from agent.executor import Executor
from agent.critic import Critic

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
WATCHLIST_FILE   = DATA_DIR / "watchlist.json"
DEFAULT_WATCHLIST = ["VUAG", "CSP1", "SWDA", "HMWS", "VWRP", "VWRL"]


def _load_watchlist() -> List[str]:
    if not WATCHLIST_FILE.exists():
        return list(DEFAULT_WATCHLIST)
    try:
        data = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            items = data.get("tickers") or data.get("watchlist") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        return [str(x).upper().strip() for x in items if str(x).strip()] or list(DEFAULT_WATCHLIST)
    except Exception:
        return list(DEFAULT_WATCHLIST)


class Orchestrator:
    """
    三层 Agent 控制器：Planner → Executor → Critic → (retry)

    完整流程：
    1. Planner 把用户问题拆成子任务列表
    2. Executor 按顺序执行子任务（调工具 + LLM 解读），最后综合
    3. Critic 校验答案与原始数据是否一致
    4. 若校验不通过且未超过重试次数，带修正提示重新执行第 2 步

    用法：
        result = Orchestrator().run("VUAG 和 CSP1 今天有分化吗？")
        print(result["final_answer"])
    """

    def __init__(self, max_retries: int = 2) -> None:
        self.max_retries = max_retries
        self.planner     = Planner()
        self.executor    = Executor()
        self.critic      = Critic()

    def run(
        self,
        question:     str,
        current_poll: Optional[Dict[str, Any]] = None,
        watchlist:    Optional[List[str]]       = None,
    ) -> Dict[str, Any]:
        """
        返回：
          {
            "question":       str,
            "final_answer":   str,
            "plan":           [str, ...],    # 子任务描述列表
            "attempts":       int,           # 实际执行轮次
            "critic_passed":  bool,
            "subtask_results": [...],
            "timestamp":      str,
          }
        """
        watchlist    = watchlist or _load_watchlist()
        current_poll = current_poll or self._poll_now(watchlist)

        print(f"\n{'='*60}")
        print(f"[Orchestrator] 问题：{question}")
        print(f"[Orchestrator] Watchlist：{watchlist}")
        print(f"{'='*60}")

        # ── Step 1: 规划 ──────────────────────────────────────────────────────
        tasks = self.planner.plan(question, watchlist)
        plan  = [f"[{t.id}] {t.tool}: {t.task}" for t in tasks]

        # ── Step 2 & 3: 执行 + 校验（带重试）────────────────────────────────
        critic_hint     = None
        exec_result     = {}
        critic_passed   = False
        attempts        = 0

        for attempt in range(1, self.max_retries + 2):   # +2：至少执行 1 次
            attempts = attempt
            print(f"\n[Orchestrator] 第 {attempt} 轮执行...")

            exec_result = self.executor.execute(
                tasks        = tasks,
                question     = question,
                current_poll = current_poll,
                watchlist    = watchlist,
                critic_hint  = critic_hint,
            )

            verdict = self.critic.verify(
                question = question,
                answer   = exec_result["final_answer"],
                raw_data = exec_result["raw_data"],
            )

            if verdict.valid:
                critic_passed = True
                break

            if attempt <= self.max_retries:
                critic_hint = verdict.hint
                print(f"[Orchestrator] 校验未通过，第 {attempt+1} 轮重试...")
            else:
                print("[Orchestrator] 达到最大重试次数，使用当前结果。")

        print(f"\n[Orchestrator] 完成（{attempts} 轮，校验：{'通过' if critic_passed else '未通过'}）")

        return {
            "question":        question,
            "final_answer":    exec_result.get("final_answer", ""),
            "plan":            plan,
            "attempts":        attempts,
            "critic_passed":   critic_passed,
            "subtask_results": exec_result.get("subtask_results", []),
            "timestamp":       datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _poll_now(watchlist: List[str]) -> Dict[str, Any]:
        try:
            from monitors.price_poller import poll_once
            return poll_once()
        except Exception as e:
            print(f"[Orchestrator] 价格轮询失败：{e}")
            return {"polled_at": datetime.now(timezone.utc).isoformat(), "data": {}}
