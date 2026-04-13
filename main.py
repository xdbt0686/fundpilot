from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, List

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
DEFAULT_WATCHLIST = ["VUAG", "CSP1", "SWDA", "HMWS", "VWRP", "VWRL"]

USAGE = """
FundPilot CLI

用法：
  python main.py ask        <问题>   向 AI 提问（关键词路由）
  python main.py agent      <问题>   向 AI 提问（三层 Agent：规划→执行→校验）★
  python main.py recommend           全 watchlist 技术评分 + AI 购买建议  ★
  python main.py overlap             分析 watchlist 各 ETF 持仓重叠度
  python main.py compare    <A> <B>  横向对比两只 ETF
  python main.py portfolio           整体组合分析
  python main.py monitor             单次监控巡检
  python main.py loop                启动持续监控循环（Ctrl+C 停止）
  python main.py dashboard           启动图形界面
""".strip()


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_watchlist() -> List[str]:
    data = _load_json(WATCHLIST_FILE, {})
    if isinstance(data, dict):
        items = data.get("tickers") or data.get("watchlist") or []
        if isinstance(items, list):
            return [str(x).upper().strip() for x in items if str(x).strip()]
    elif isinstance(data, list):
        return [str(x).upper().strip() for x in data if str(x).strip()]
    return list(DEFAULT_WATCHLIST)


# ── 子命令 ────────────────────────────────────────────────────────────────────

def cmd_ask(args: List[str]) -> None:
    question = " ".join(args).strip()
    if not question:
        question = input("请输入问题：").strip()
    if not question:
        print("问题不能为空。")
        return

    from monitors.price_poller import poll_once
    from agent.event_agent import EventAgent
    from core.router import Router

    watchlist    = _load_watchlist()
    current_poll = poll_once()
    route        = Router(watchlist).route(question, current_poll)
    result       = EventAgent().answer_user_question(
        user_question=question,
        current_poll=current_poll,
        extra_context=route.get("extra_context"),
    )
    print("\n" + result.get("ai_text", "（无回答）"))


def cmd_overlap() -> None:
    from tools.overlap import analyze_watchlist_overlap

    watchlist = _load_watchlist()
    report    = analyze_watchlist_overlap(watchlist)

    print(f"\n{report['summary']}")

    high = report.get("high_overlap_pairs", [])
    if high:
        print()
        for pair in high:
            print(
                f"  {pair['ticker_a']} vs {pair['ticker_b']}: "
                f"{pair['overlap_pct']*100:.0f}%（{pair['overlap_label']}）"
                f"  — {pair.get('reason', '')}"
            )
    else:
        print("  无高重叠对。")


def cmd_compare(args: List[str]) -> None:
    if len(args) < 2:
        print("用法：python main.py compare <TICKER_A> <TICKER_B>")
        return

    from tools.compare import compare_etfs
    from monitors.price_poller import poll_once

    ta, tb       = args[0].upper(), args[1].upper()
    current_poll = poll_once()
    result       = compare_etfs(ta, tb, current_poll)

    print(f"\n{ta} vs {tb}\n")
    for point in result.get("summary_points", []):
        print(f"  • {point}")


def cmd_portfolio() -> None:
    from tools.portfolio import analyze_portfolio
    from monitors.price_poller import poll_once

    watchlist    = _load_watchlist()
    current_poll = poll_once()
    report       = analyze_portfolio(watchlist, current_poll)

    print(f"\n组合：{', '.join(report['tickers'])}  |  共 {len(report['tickers'])} 只")
    print(f"平均 TER：{report['avg_ter']}%  |  "
          f"累积型 {report['accumulating_count']}  分红型 {report['distributing_count']}")

    print("\n地域分布：")
    for region, members in report["region_exposure"].items():
        print(f"  {region}：{', '.join(members)}")

    if report["em_exposure_tickers"]:
        print(f"\n含新兴市场：{', '.join(report['em_exposure_tickers'])}")

    print(f"\n{report['overlap_summary']}")

    for w in report.get("concentration_warnings", []):
        print(f"\n  警告：{w}")


def cmd_recommend() -> None:
    from monitors.price_poller import poll_once
    from rules.recommendation_rules import evaluate_all
    from core.prompts import RECOMMEND_SYSTEM, build_recommend_prompt
    from core.llm import ask_llm

    print("正在拉取全 watchlist 数据，请稍候（首次运行需探测符号，约需 1-2 分钟）...")
    current_poll = poll_once()
    data = current_poll.get("data", {})

    if not data:
        print("未能获取到任何价格数据，请检查网络。")
        return

    evaluation = evaluate_all(current_poll)

    # 打印简明评分表
    print(f"\n{'─'*60}")
    print(f"  {'资产':<12} {'信号':<10} {'评分':>5}  {'日涨跌':>8}  {'周涨跌':>8}  {'月涨跌':>8}")
    print(f"{'─'*60}")
    for ticker, r in sorted(evaluation["ratings"].items(), key=lambda x: x[1]["score"], reverse=True):
        if r["signal"] == "no_data":
            continue
        snap = r["price_snapshot"]
        d = f"{snap['daily_change_pct']:+.2f}%" if snap.get("daily_change_pct") is not None else "  --"
        w = f"{snap['week_change_pct']:+.2f}%"  if snap.get("week_change_pct")  is not None else "  --"
        m = f"{snap['month_change_pct']:+.2f}%" if snap.get("month_change_pct") is not None else "  --"
        print(f"  {ticker:<12} {r['signal_label']:<10} {r['score']:>5}  {d:>8}  {w:>8}  {m:>8}")
    print(f"{'─'*60}")

    print("\n正在生成 AI 购买建议...")
    try:
        ai_text = ask_llm(RECOMMEND_SYSTEM, build_recommend_prompt(evaluation, current_poll))
    except Exception as e:
        ai_text = f"AI 建议生成失败：{e}"

    print(f"\n{'='*60}")
    print(ai_text)
    print(f"{'='*60}")


def cmd_agent(args: List[str]) -> None:
    question = " ".join(args).strip()
    if not question:
        question = input("请输入问题：").strip()
    if not question:
        print("问题不能为空。")
        return

    from agent.orchestrator import Orchestrator

    result = Orchestrator().run(question)

    print("\n" + "=" * 60)
    print(result["final_answer"])
    print("=" * 60)
    print(f"\n共执行 {result['attempts']} 轮  |  Critic 校验：{'通过' if result['critic_passed'] else '未通过'}")
    print(f"计划拆解：{len(result['plan'])} 个子任务")
    for step in result["plan"]:
        print(f"  {step}")


def cmd_monitor() -> None:
    import subprocess
    subprocess.run([sys.executable, str(BASE_DIR / "run_monitor_once.py")])


def cmd_loop() -> None:
    import subprocess
    subprocess.run([sys.executable, str(BASE_DIR / "run_monitor_loop.py")])


def cmd_dashboard() -> None:
    import subprocess
    subprocess.run([sys.executable, str(BASE_DIR / "fundpilot_dashboard.py")])


# ── 入口 ──────────────────────────────────────────────────────────────────────

_COMMANDS = {
    "ask":       lambda rest: cmd_ask(rest),
    "agent":     lambda rest: cmd_agent(rest),
    "recommend": lambda _:    cmd_recommend(),
    "overlap":   lambda _:    cmd_overlap(),
    "compare":   lambda rest: cmd_compare(rest),
    "portfolio": lambda _:    cmd_portfolio(),
    "monitor":   lambda _:    cmd_monitor(),
    "loop":      lambda _:    cmd_loop(),
    "dashboard": lambda _:    cmd_dashboard(),
}


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(USAGE)
        return

    cmd     = args[0].lower()
    rest    = args[1:]
    handler = _COMMANDS.get(cmd)

    if handler:
        handler(rest)
    else:
        print(f"未知命令：{cmd!r}\n\n{USAGE}")


if __name__ == "__main__":
    main()
