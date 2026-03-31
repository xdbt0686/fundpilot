from __future__ import annotations

import inspect
import json
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

from agent.event_agent import EventAgent
from monitors.price_poller import poll_once
from rules.trigger_rules import evaluate_triggers

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

WATCHLIST_FILE = DATA_DIR / "watchlist.json"
LAST_SNAPSHOT_FILE = DATA_DIR / "last_snapshot.json"
MONITOR_STATE_FILE = DATA_DIR / "monitor_state.json"
MONITOR_SETTINGS_FILE = DATA_DIR / "monitor_settings.json"


DEFAULT_SETTINGS = {
    "poll_interval_seconds": 10,
    "ai_cooldown_minutes": 10,
    "heartbeat_minutes": 30,
    "daily_move_alert_pct": 1.5,
    "daily_move_strong_pct": 3.0,
    "stale_data_minutes": 20,
    "reversal_pct": 1.0,
    "force_ai_on_startup": True,
}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_settings() -> Dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    file_settings = load_json(MONITOR_SETTINGS_FILE, {})
    if isinstance(file_settings, dict):
        settings.update(file_settings)
    return settings


def load_watchlist() -> List[str]:
    data = load_json(WATCHLIST_FILE, [])
    if isinstance(data, dict):
        items = data.get("tickers") or data.get("watchlist") or []
        if isinstance(items, list):
            return [str(x).upper().strip() for x in items if str(x).strip()]
    elif isinstance(data, list):
        return [str(x).upper().strip() for x in data if str(x).strip()]
    return ["VUAG", "CSP1", "SWDA", "HMWS", "VWRP", "VWRL"]


def call_poll_once_compat(watchlist: List[str]) -> Dict[str, Any]:
    try:
        sig = inspect.signature(poll_once)
        if len(sig.parameters) == 0:
            result = poll_once()
        else:
            result = poll_once(watchlist)
    except (TypeError, ValueError):
        try:
            result = poll_once(watchlist)
        except TypeError:
            result = poll_once()

    if not isinstance(result, dict):
        raise RuntimeError(f"poll_once() should return dict, got {type(result).__name__}")

    result.setdefault("polled_at", datetime.now().isoformat(timespec="seconds"))
    result.setdefault("data", {})
    return result


class FundPilotDashboard:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("FundPilot Dashboard")
        self.root.geometry("1480x900")
        self.root.minsize(1200, 760)

        self.agent = EventAgent()
        self.settings = load_settings()
        self.watchlist = load_watchlist()

        self.prev_snapshot: Optional[Dict[str, Any]] = None
        self.current_snapshot: Dict[str, Any] = load_json(LAST_SNAPSHOT_FILE, {})
        self.monitor_proc: Optional[subprocess.Popen] = None

        self._build_styles()
        self._build_layout()
        self._refresh_all_from_files(first_time=True)

        self.root.after(3000, self._auto_refresh_tick)

    def _build_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("Status.TLabel", font=("Consolas", 10))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10))
        style.configure("Treeview", rowheight=26, font=("Consolas", 10))
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))

    def _build_layout(self) -> None:
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=3)
        main.rowconfigure(1, weight=2)

        # 左上：AI回答区
        left_top = ttk.LabelFrame(main, text="左上｜AI 回答区", padding=8)
        left_top.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        left_top.columnconfigure(0, weight=1)
        left_top.rowconfigure(1, weight=1)

        self.ai_meta_label = ttk.Label(
            left_top,
            text="状态：待命",
            style="Status.TLabel",
        )
        self.ai_meta_label.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.ai_output = ScrolledText(
            left_top,
            wrap="word",
            font=("Microsoft YaHei UI", 11),
        )
        self.ai_output.grid(row=1, column=0, sticky="nsew")
        self.ai_output.insert("1.0", "FundPilot 已就绪。\n这里会显示主动问答结果，或手动巡检分析。")
        self.ai_output.configure(state="disabled")

        # 右上：提问/控制区
        right_top = ttk.LabelFrame(main, text="右上｜提问 / 控制区", padding=8)
        right_top.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        right_top.columnconfigure(0, weight=1)
        right_top.rowconfigure(1, weight=1)

        top_info = ttk.Frame(right_top)
        top_info.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top_info.columnconfigure(1, weight=1)

        ttk.Label(top_info, text="监控状态：", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.monitor_status_label = ttk.Label(top_info, text="未启动", style="Status.TLabel")
        self.monitor_status_label.grid(row=0, column=1, sticky="w")

        ttk.Label(top_info, text="最后刷新：", style="Title.TLabel").grid(row=1, column=0, sticky="w")
        self.refresh_status_label = ttk.Label(top_info, text="--", style="Status.TLabel")
        self.refresh_status_label.grid(row=1, column=1, sticky="w")

        input_frame = ttk.Frame(right_top)
        input_frame.grid(row=1, column=0, sticky="nsew")
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(1, weight=1)

        ttk.Label(input_frame, text="提问输入", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.question_input = ScrolledText(
            input_frame,
            wrap="word",
            height=10,
            font=("Microsoft YaHei UI", 11),
        )
        self.question_input.grid(row=1, column=0, sticky="nsew")
        self.question_input.insert("1.0", "今天这组ETF有没有明显风格分化？")

        btns = ttk.Frame(input_frame)
        btns.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for i in range(3):
            btns.columnconfigure(i, weight=1)

        ttk.Button(btns, text="主动提问", command=self.on_ask_clicked, style="Primary.TButton").grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(btns, text="巡检一次", command=self.on_inspect_clicked, style="Primary.TButton").grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(btns, text="刷新数据", command=self.on_refresh_clicked, style="Primary.TButton").grid(
            row=0, column=2, sticky="ew", padx=(4, 0)
        )

        btns2 = ttk.Frame(input_frame)
        btns2.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        for i in range(4):
            btns2.columnconfigure(i, weight=1)

        ttk.Button(btns2, text="启动监控", command=self.start_monitor_loop).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(btns2, text="停止监控", command=self.stop_monitor_loop).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(
            btns2, text="问题：谁最值得盯", command=lambda: self.quick_question("现在谁最值得重点盯？")
        ).grid(row=0, column=2, sticky="ew", padx=4)
        ttk.Button(
            btns2, text="问题：差异对比", command=lambda: self.quick_question("VUAG 和 CSP1 当前差异主要在哪？")
        ).grid(row=0, column=3, sticky="ew", padx=(4, 0))

        # 左下：紧急事项区
        left_bottom = ttk.LabelFrame(main, text="左下｜紧急事项区", padding=8)
        left_bottom.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(6, 0))
        left_bottom.columnconfigure(0, weight=1)
        left_bottom.rowconfigure(1, weight=1)

        self.alert_meta_label = ttk.Label(left_bottom, text="告警：待分析", style="Status.TLabel")
        self.alert_meta_label.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.alert_list = tk.Listbox(left_bottom, font=("Consolas", 11))
        self.alert_list.grid(row=1, column=0, sticky="nsew")

        # 右下：实时数据区
        right_bottom = ttk.LabelFrame(main, text="右下｜实时数据区", padding=8)
        right_bottom.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(6, 0))
        right_bottom.columnconfigure(0, weight=1)
        right_bottom.rowconfigure(1, weight=1)

        self.snapshot_meta_label = ttk.Label(right_bottom, text="最新快照：--", style="Status.TLabel")
        self.snapshot_meta_label.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        columns = ("ticker", "latest_price", "previous_close", "daily_change_pct", "timestamp")
        self.data_tree = ttk.Treeview(right_bottom, columns=columns, show="headings")
        self.data_tree.grid(row=1, column=0, sticky="nsew")

        self.data_tree.heading("ticker", text="Ticker")
        self.data_tree.heading("latest_price", text="Latest")
        self.data_tree.heading("previous_close", text="Prev Close")
        self.data_tree.heading("daily_change_pct", text="Change %")
        self.data_tree.heading("timestamp", text="Timestamp")

        self.data_tree.column("ticker", width=90, anchor="center")
        self.data_tree.column("latest_price", width=110, anchor="e")
        self.data_tree.column("previous_close", width=110, anchor="e")
        self.data_tree.column("daily_change_pct", width=100, anchor="e")
        self.data_tree.column("timestamp", width=180, anchor="center")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def set_ai_text(self, text: str, meta: str) -> None:
        self.ai_output.configure(state="normal")
        self.ai_output.delete("1.0", "end")
        self.ai_output.insert("1.0", text)
        self.ai_output.configure(state="disabled")
        self.ai_meta_label.config(text=meta)

    def set_monitor_status(self, text: str) -> None:
        self.monitor_status_label.config(text=text)

    def _refresh_all_from_files(self, first_time: bool = False) -> None:
        snapshot = load_json(LAST_SNAPSHOT_FILE, {})
        state = load_json(MONITOR_STATE_FILE, {})
        settings = load_settings()

        if not isinstance(snapshot, dict):
            snapshot = {}

        if first_time and not snapshot:
            self.snapshot_meta_label.config(text="最新快照：当前还没有 snapshot")
            self.alert_meta_label.config(text="告警：暂无数据")
            return

        if snapshot:
            self._update_data_table(snapshot)
            self._update_alerts(snapshot, state, settings)

        self.refresh_status_label.config(text=now_str())

    def _update_data_table(self, snapshot: Dict[str, Any]) -> None:
        for iid in self.data_tree.get_children():
            self.data_tree.delete(iid)

        data = snapshot.get("data", {}) or {}
        polled_at = snapshot.get("polled_at", "--")
        self.snapshot_meta_label.config(text=f"最新快照：{polled_at}")

        rows = []
        for ticker, item in data.items():
            latest = item.get("latest_price", "")
            prev_close = item.get("previous_close", "")
            change_pct = item.get("daily_change_pct", "")
            ts = item.get("timestamp", "")

            try:
                latest = f"{float(latest):.4f}"
            except Exception:
                latest = str(latest)

            try:
                prev_close = f"{float(prev_close):.4f}"
            except Exception:
                prev_close = str(prev_close)

            try:
                change_pct = f"{float(change_pct):+.2f}%"
            except Exception:
                change_pct = str(change_pct)

            rows.append((ticker, latest, prev_close, change_pct, ts))

        rows.sort(key=lambda x: x[0])

        for row in rows:
            self.data_tree.insert("", "end", values=row)

        self.current_snapshot = snapshot

    def _update_alerts(self, snapshot: Dict[str, Any], state: Dict[str, Any], settings: Dict[str, Any]) -> None:
        self.alert_list.delete(0, "end")

        try:
            trigger_result = evaluate_triggers(
                current_poll=snapshot,
                last_snapshot=self.prev_snapshot,
                state=state,
                config=settings,
            )
        except Exception as e:
            self.alert_list.insert("end", f"触发分析失败：{e}")
            self.alert_meta_label.config(text="告警：分析失败")
            return

        events = trigger_result.get("events", []) or []
        summary = trigger_result.get("market_summary", {}) or {}

        if not events:
            self.alert_list.insert("end", "当前无紧急事项")
            if summary:
                self.alert_list.insert(
                    "end",
                    f"概况：上涨 {summary.get('up_count', 0)} / 下跌 {summary.get('down_count', 0)} / 平 {summary.get('flat_count', 0)}",
                )
        else:
            for ev in events:
                sev = ev.get("severity", "info")
                ticker = ev.get("ticker") or "WATCHLIST"
                title = ev.get("title", "")
                self.alert_list.insert("end", f"[{sev}] {ticker} | {title}")

        self.alert_meta_label.config(text=f"告警：{len(events)} 条")
        self.prev_snapshot = snapshot

    def on_refresh_clicked(self) -> None:
        self._refresh_all_from_files()

    def quick_question(self, question: str) -> None:
        self.question_input.delete("1.0", "end")
        self.question_input.insert("1.0", question)
        self.on_ask_clicked()

    def on_ask_clicked(self) -> None:
        question = self.question_input.get("1.0", "end").strip()
        if not question:
            messagebox.showwarning("提示", "问题不能为空")
            return

        self.set_ai_text("正在调用 Agent，请稍候...", f"状态：主动提问中 | {now_str()}")

        def worker() -> None:
            try:
                current_poll = call_poll_once_compat(self.watchlist)
                result = self.agent.answer_user_question(
                    user_question=question,
                    current_poll=current_poll,
                )
                text = result.get("ai_text", "")
                self.root.after(
                    0,
                    lambda: self.set_ai_text(
                        text or "没有返回内容。",
                        f"状态：主动问答完成 | {now_str()}",
                    ),
                )
                self.root.after(0, lambda: self._update_data_table(current_poll))
            except Exception as e:
                self.root.after(
                    0,
                    lambda: self.set_ai_text(
                        f"主动问答失败：{e}",
                        f"状态：主动问答失败 | {now_str()}",
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def on_inspect_clicked(self) -> None:
        self.set_ai_text("正在生成巡检分析，请稍候...", f"状态：巡检中 | {now_str()}")

        def worker() -> None:
            try:
                current_poll = call_poll_once_compat(self.watchlist)
                state = load_json(MONITOR_STATE_FILE, {})
                settings = load_settings()

                trigger_result = evaluate_triggers(
                    current_poll=current_poll,
                    last_snapshot=self.prev_snapshot,
                    state=state,
                    config=settings,
                )

                result = self.agent.analyze_monitor_cycle(
                    current_poll=current_poll,
                    trigger_result=trigger_result,
                )

                text = result.get("ai_text", "")
                self.root.after(
                    0,
                    lambda: self.set_ai_text(
                        text or "没有返回内容。",
                        f"状态：巡检完成 | {now_str()}",
                    ),
                )
                self.root.after(0, lambda: self._update_data_table(current_poll))
                self.root.after(0, lambda: self._update_alerts(current_poll, state, settings))
            except Exception as e:
                self.root.after(
                    0,
                    lambda: self.set_ai_text(
                        f"巡检失败：{e}",
                        f"状态：巡检失败 | {now_str()}",
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def start_monitor_loop(self) -> None:
        if self.monitor_proc and self.monitor_proc.poll() is None:
            messagebox.showinfo("提示", "监控进程已经在运行。")
            self.set_monitor_status("运行中（已存在）")
            return

        try:
            self.monitor_proc = subprocess.Popen(
                [sys.executable, str(BASE_DIR / "run_monitor_loop.py")],
                cwd=str(BASE_DIR),
            )
            self.set_monitor_status(f"运行中 | PID={self.monitor_proc.pid}")
        except Exception as e:
            messagebox.showerror("错误", f"启动监控失败：{e}")
            self.set_monitor_status("启动失败")

    def stop_monitor_loop(self) -> None:
        if not self.monitor_proc or self.monitor_proc.poll() is not None:
            self.set_monitor_status("未运行")
            return

        try:
            self.monitor_proc.terminate()
            self.set_monitor_status("已停止")
        except Exception as e:
            messagebox.showerror("错误", f"停止监控失败：{e}")

    def _auto_refresh_tick(self) -> None:
        try:
            self._refresh_all_from_files()
            if self.monitor_proc and self.monitor_proc.poll() is None:
                self.set_monitor_status(f"运行中 | PID={self.monitor_proc.pid}")
            elif self.monitor_proc:
                self.set_monitor_status("已退出")
        finally:
            self.root.after(3000, self._auto_refresh_tick)

    def on_close(self) -> None:
        # 这里先不强制杀后台监控，避免误停真正常驻任务
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = FundPilotDashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()