from __future__ import annotations

import inspect
import json
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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

# All UI strings in Chinese and English
STRINGS: Dict[str, Dict[str, str]] = {
    "zh": {
        "title": "FundPilot 监控台",
        "frame_ai": "左上｜AI 回答区",
        "ai_status_ready": "状态：待命",
        "ai_initial": "FundPilot 已就绪。\n这里会显示主动问答结果，或手动巡检分析。",
        "frame_control": "右上｜提问 / 控制区",
        "monitor_label": "监控状态：",
        "refresh_label": "最后刷新：",
        "monitor_not_started": "未启动",
        "question_label": "提问输入",
        "question_placeholder": "今天这组ETF有没有明显风格分化？",
        "btn_ask": "主动提问",
        "btn_inspect": "巡检一次",
        "btn_refresh": "刷新数据",
        "btn_start": "启动监控",
        "btn_stop": "停止监控",
        "btn_q1": "问题：谁最值得盯",
        "btn_q2": "问题：差异对比",
        "q1_text": "现在谁最值得重点盯？",
        "q2_text": "VUAG 和 CSP1 当前差异主要在哪？",
        "frame_alerts": "左下｜紧急事项区",
        "alert_pending": "告警：待分析",
        "frame_data": "右下｜实时数据区",
        "snapshot_none": "最新快照：当前还没有 snapshot",
        "alert_no_data": "告警：暂无数据",
        "no_alerts": "当前无紧急事项",
        "market_summary": "概况：上涨 {up} / 下跌 {down} / 平 {flat}",
        "alert_count": "告警：{n} 条",
        "alert_fail": "触发分析失败：{e}",
        "alert_fail_status": "告警：分析失败",
        "snapshot_label": "最新快照：{t}",
        "monitor_running_exist": "运行中（已存在）",
        "monitor_running": "运行中 | PID={pid}",
        "monitor_stopped": "已停止",
        "monitor_not_running": "未运行",
        "monitor_start_fail": "启动失败",
        "monitor_exited": "已退出",
        "asking": "正在调用 Agent，请稍候...",
        "asking_status": "状态：主动提问中 | {t}",
        "ask_done": "状态：主动问答完成 | {t}",
        "ask_fail_status": "状态：主动问答失败 | {t}",
        "ask_fail": "主动问答失败：{e}",
        "no_content": "没有返回内容。",
        "inspecting": "正在生成巡检分析，请稍候...",
        "inspect_status": "状态：巡检中 | {t}",
        "inspect_done": "状态：巡检完成 | {t}",
        "inspect_fail_status": "状态：巡检失败 | {t}",
        "inspect_fail": "巡检失败：{e}",
        "warn_empty": "问题不能为空",
        "warn_title": "提示",
        "info_title": "提示",
        "err_title": "错误",
        "monitor_already": "监控进程已经在运行。",
        "monitor_start_err": "启动监控失败：{e}",
        "monitor_stop_err": "停止监控失败：{e}",
        "lang_btn": "EN",
        "vol_popup_title": "波动预警",
        "vol_popup_msg": "检测到高波动事件：\n\n{details}",
        "col_ticker": "Ticker",
        "col_latest": "最新价",
        "col_prev": "前收盘",
        "col_change": "涨跌幅",
        "col_time": "时间戳",
    },
    "en": {
        "title": "FundPilot Dashboard",
        "frame_ai": "AI Answer",
        "ai_status_ready": "Status: Ready",
        "ai_initial": "FundPilot is ready.\nAI responses and inspection results will appear here.",
        "frame_control": "Ask / Control",
        "monitor_label": "Monitor:",
        "refresh_label": "Last Refresh:",
        "monitor_not_started": "Not started",
        "question_label": "Enter Question",
        "question_placeholder": "Is there any style divergence in today's ETFs?",
        "btn_ask": "Ask AI",
        "btn_inspect": "Inspect",
        "btn_refresh": "Refresh",
        "btn_start": "Start Monitor",
        "btn_stop": "Stop Monitor",
        "btn_q1": "Who to Watch",
        "btn_q2": "Compare ETFs",
        "q1_text": "Which asset deserves the most attention right now?",
        "q2_text": "What are the main differences between VUAG and CSP1 currently?",
        "frame_alerts": "Alerts",
        "alert_pending": "Alerts: Pending",
        "frame_data": "Live Data",
        "snapshot_none": "Latest Snapshot: none yet",
        "alert_no_data": "Alerts: No data",
        "no_alerts": "No active alerts",
        "market_summary": "Market: {up} up / {down} down / {flat} flat",
        "alert_count": "Alerts: {n}",
        "alert_fail": "Trigger analysis failed: {e}",
        "alert_fail_status": "Alerts: analysis failed",
        "snapshot_label": "Latest Snapshot: {t}",
        "monitor_running_exist": "Running (already active)",
        "monitor_running": "Running | PID={pid}",
        "monitor_stopped": "Stopped",
        "monitor_not_running": "Not running",
        "monitor_start_fail": "Failed to start",
        "monitor_exited": "Exited",
        "asking": "Calling Agent, please wait...",
        "asking_status": "Status: Asking | {t}",
        "ask_done": "Status: Ask complete | {t}",
        "ask_fail_status": "Status: Ask failed | {t}",
        "ask_fail": "Ask failed: {e}",
        "no_content": "No response returned.",
        "inspecting": "Generating inspection report, please wait...",
        "inspect_status": "Status: Inspecting | {t}",
        "inspect_done": "Status: Inspection complete | {t}",
        "inspect_fail_status": "Status: Inspection failed | {t}",
        "inspect_fail": "Inspection failed: {e}",
        "warn_empty": "Question cannot be empty",
        "warn_title": "Notice",
        "info_title": "Info",
        "err_title": "Error",
        "monitor_already": "Monitor process is already running.",
        "monitor_start_err": "Failed to start monitor: {e}",
        "monitor_stop_err": "Failed to stop monitor: {e}",
        "lang_btn": "中文",
        "vol_popup_title": "Volatility Alert",
        "vol_popup_msg": "High volatility event detected:\n\n{details}",
        "col_ticker": "Ticker",
        "col_latest": "Latest",
        "col_prev": "Prev Close",
        "col_change": "Change %",
        "col_time": "Timestamp",
    },
}

# Severity levels that trigger a popup modal
POPUP_SEVERITIES: Set[str] = {"warning", "critical", "strong", "high", "danger"}


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
        self.lang: str = "zh"
        self.root.title(self.t("title"))
        self.root.geometry("1480x900")
        self.root.minsize(1200, 760)

        self.agent = EventAgent()
        self.settings = load_settings()
        self.watchlist = load_watchlist()

        self.prev_snapshot: Optional[Dict[str, Any]] = None
        self.current_snapshot: Dict[str, Any] = load_json(LAST_SNAPSHOT_FILE, {})
        self.monitor_proc: Optional[subprocess.Popen] = None

        # Track which alert keys have already triggered a popup this session
        self._alerted_keys: Set[str] = set()

        self._build_styles()
        self._build_layout()
        self._refresh_all_from_files(first_time=True)

        self.root.after(3000, self._auto_refresh_tick)

    # ── Language helpers ──────────────────────────────────────────────────────

    def t(self, key: str, **kwargs: Any) -> str:
        """Return the current-language string for the given key."""
        text = STRINGS[self.lang].get(key, key)
        return text.format(**kwargs) if kwargs else text

    def toggle_lang(self) -> None:
        self.lang = "en" if self.lang == "zh" else "zh"
        self._apply_lang()

    def _apply_lang(self) -> None:
        """Update every widget text to the current language."""
        self.root.title(self.t("title"))
        self.lang_btn.configure(text=self.t("lang_btn"))

        # Frames
        self.left_top_frame.configure(text=self.t("frame_ai"))
        self.right_top_frame.configure(text=self.t("frame_control"))
        self.left_bottom_frame.configure(text=self.t("frame_alerts"))
        self.right_bottom_frame.configure(text=self.t("frame_data"))

        # Static labels
        self.monitor_label_widget.configure(text=self.t("monitor_label"))
        self.refresh_label_widget.configure(text=self.t("refresh_label"))
        self.question_label_widget.configure(text=self.t("question_label"))

        # Buttons
        self.btn_ask.configure(text=self.t("btn_ask"))
        self.btn_inspect.configure(text=self.t("btn_inspect"))
        self.btn_refresh.configure(text=self.t("btn_refresh"))
        self.btn_start.configure(text=self.t("btn_start"))
        self.btn_stop.configure(text=self.t("btn_stop"))
        self.btn_q1.configure(text=self.t("btn_q1"))
        self.btn_q2.configure(text=self.t("btn_q2"))

        # Table column headings
        self.data_tree.heading("ticker", text=self.t("col_ticker"))
        self.data_tree.heading("latest_price", text=self.t("col_latest"))
        self.data_tree.heading("previous_close", text=self.t("col_prev"))
        self.data_tree.heading("daily_change_pct", text=self.t("col_change"))
        self.data_tree.heading("timestamp", text=self.t("col_time"))

    # ── Styles ────────────────────────────────────────────────────────────────

    def _build_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("Status.TLabel", font=("Consolas", 10))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10))
        style.configure("Lang.TButton", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Treeview", rowheight=26, font=("Consolas", 10))
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        # Top bar: language toggle button
        topbar = ttk.Frame(self.root, padding=(10, 6, 10, 0))
        topbar.pack(fill="x", side="top")
        self.lang_btn = ttk.Button(
            topbar,
            text=self.t("lang_btn"),
            command=self.toggle_lang,
            style="Lang.TButton",
            width=6,
        )
        self.lang_btn.pack(side="right")

        # Main 2×2 grid
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=3)
        main.rowconfigure(1, weight=2)

        # ── Left-top: AI output ───────────────────────────────────────────────
        self.left_top_frame = ttk.LabelFrame(main, text=self.t("frame_ai"), padding=8)
        self.left_top_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        self.left_top_frame.columnconfigure(0, weight=1)
        self.left_top_frame.rowconfigure(1, weight=1)

        self.ai_meta_label = ttk.Label(
            self.left_top_frame,
            text=self.t("ai_status_ready"),
            style="Status.TLabel",
        )
        self.ai_meta_label.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.ai_output = ScrolledText(
            self.left_top_frame,
            wrap="word",
            font=("Microsoft YaHei UI", 11),
        )
        self.ai_output.grid(row=1, column=0, sticky="nsew")
        self.ai_output.insert("1.0", self.t("ai_initial"))
        self.ai_output.configure(state="disabled")

        # ── Right-top: question / control ────────────────────────────────────
        self.right_top_frame = ttk.LabelFrame(main, text=self.t("frame_control"), padding=8)
        self.right_top_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        self.right_top_frame.columnconfigure(0, weight=1)
        self.right_top_frame.rowconfigure(1, weight=1)

        top_info = ttk.Frame(self.right_top_frame)
        top_info.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top_info.columnconfigure(1, weight=1)

        self.monitor_label_widget = ttk.Label(top_info, text=self.t("monitor_label"), style="Title.TLabel")
        self.monitor_label_widget.grid(row=0, column=0, sticky="w")
        self.monitor_status_label = ttk.Label(top_info, text=self.t("monitor_not_started"), style="Status.TLabel")
        self.monitor_status_label.grid(row=0, column=1, sticky="w")

        self.refresh_label_widget = ttk.Label(top_info, text=self.t("refresh_label"), style="Title.TLabel")
        self.refresh_label_widget.grid(row=1, column=0, sticky="w")
        self.refresh_status_label = ttk.Label(top_info, text="--", style="Status.TLabel")
        self.refresh_status_label.grid(row=1, column=1, sticky="w")

        input_frame = ttk.Frame(self.right_top_frame)
        input_frame.grid(row=1, column=0, sticky="nsew")
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(1, weight=1)

        self.question_label_widget = ttk.Label(input_frame, text=self.t("question_label"), style="Title.TLabel")
        self.question_label_widget.grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.question_input = ScrolledText(
            input_frame,
            wrap="word",
            height=10,
            font=("Microsoft YaHei UI", 11),
        )
        self.question_input.grid(row=1, column=0, sticky="nsew")
        self.question_input.insert("1.0", self.t("question_placeholder"))

        btns = ttk.Frame(input_frame)
        btns.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for i in range(3):
            btns.columnconfigure(i, weight=1)

        self.btn_ask = ttk.Button(btns, text=self.t("btn_ask"), command=self.on_ask_clicked, style="Primary.TButton")
        self.btn_ask.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.btn_inspect = ttk.Button(btns, text=self.t("btn_inspect"), command=self.on_inspect_clicked, style="Primary.TButton")
        self.btn_inspect.grid(row=0, column=1, sticky="ew", padx=4)

        self.btn_refresh = ttk.Button(btns, text=self.t("btn_refresh"), command=self.on_refresh_clicked, style="Primary.TButton")
        self.btn_refresh.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        btns2 = ttk.Frame(input_frame)
        btns2.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        for i in range(4):
            btns2.columnconfigure(i, weight=1)

        self.btn_start = ttk.Button(btns2, text=self.t("btn_start"), command=self.start_monitor_loop)
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.btn_stop = ttk.Button(btns2, text=self.t("btn_stop"), command=self.stop_monitor_loop)
        self.btn_stop.grid(row=0, column=1, sticky="ew", padx=4)

        self.btn_q1 = ttk.Button(
            btns2, text=self.t("btn_q1"),
            command=lambda: self.quick_question(self.t("q1_text")),
        )
        self.btn_q1.grid(row=0, column=2, sticky="ew", padx=4)

        self.btn_q2 = ttk.Button(
            btns2, text=self.t("btn_q2"),
            command=lambda: self.quick_question(self.t("q2_text")),
        )
        self.btn_q2.grid(row=0, column=3, sticky="ew", padx=(4, 0))

        # ── Left-bottom: alerts ───────────────────────────────────────────────
        self.left_bottom_frame = ttk.LabelFrame(main, text=self.t("frame_alerts"), padding=8)
        self.left_bottom_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(6, 0))
        self.left_bottom_frame.columnconfigure(0, weight=1)
        self.left_bottom_frame.rowconfigure(1, weight=1)

        self.alert_meta_label = ttk.Label(self.left_bottom_frame, text=self.t("alert_pending"), style="Status.TLabel")
        self.alert_meta_label.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.alert_list = tk.Listbox(self.left_bottom_frame, font=("Consolas", 11))
        self.alert_list.grid(row=1, column=0, sticky="nsew")

        # ── Right-bottom: live data ───────────────────────────────────────────
        self.right_bottom_frame = ttk.LabelFrame(main, text=self.t("frame_data"), padding=8)
        self.right_bottom_frame.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(6, 0))
        self.right_bottom_frame.columnconfigure(0, weight=1)
        self.right_bottom_frame.rowconfigure(1, weight=1)

        self.snapshot_meta_label = ttk.Label(self.right_bottom_frame, text="--", style="Status.TLabel")
        self.snapshot_meta_label.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        columns = ("ticker", "latest_price", "previous_close", "daily_change_pct", "timestamp")
        self.data_tree = ttk.Treeview(self.right_bottom_frame, columns=columns, show="headings")
        self.data_tree.grid(row=1, column=0, sticky="nsew")

        self.data_tree.heading("ticker", text=self.t("col_ticker"))
        self.data_tree.heading("latest_price", text=self.t("col_latest"))
        self.data_tree.heading("previous_close", text=self.t("col_prev"))
        self.data_tree.heading("daily_change_pct", text=self.t("col_change"))
        self.data_tree.heading("timestamp", text=self.t("col_time"))

        self.data_tree.column("ticker", width=90, anchor="center")
        self.data_tree.column("latest_price", width=110, anchor="e")
        self.data_tree.column("previous_close", width=110, anchor="e")
        self.data_tree.column("daily_change_pct", width=100, anchor="e")
        self.data_tree.column("timestamp", width=180, anchor="center")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ── Data helpers ──────────────────────────────────────────────────────────

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
            self.snapshot_meta_label.config(text=self.t("snapshot_none"))
            self.alert_meta_label.config(text=self.t("alert_no_data"))
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
        self.snapshot_meta_label.config(text=self.t("snapshot_label", t=polled_at))

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
            self.alert_list.insert("end", self.t("alert_fail", e=e))
            self.alert_meta_label.config(text=self.t("alert_fail_status"))
            return

        events = trigger_result.get("events", []) or []
        summary = trigger_result.get("market_summary", {}) or {}

        if not events:
            self.alert_list.insert("end", self.t("no_alerts"))
            if summary:
                self.alert_list.insert(
                    "end",
                    self.t(
                        "market_summary",
                        up=summary.get("up_count", 0),
                        down=summary.get("down_count", 0),
                        flat=summary.get("flat_count", 0),
                    ),
                )
        else:
            high_vol_lines: List[str] = []

            for ev in events:
                sev = ev.get("severity", "info")
                ticker = ev.get("ticker") or "WATCHLIST"
                title = ev.get("title", "")
                self.alert_list.insert("end", f"[{sev}] {ticker} | {title}")

                # Collect high-volatility events for popup
                if sev.lower() in POPUP_SEVERITIES:
                    alert_key = f"{ticker}|{title}"
                    if alert_key not in self._alerted_keys:
                        self._alerted_keys.add(alert_key)
                        high_vol_lines.append(f"  [{sev.upper()}] {ticker}: {title}")

            if high_vol_lines:
                details = "\n".join(high_vol_lines)
                self.root.after(
                    0,
                    lambda d=details: messagebox.showwarning(
                        self.t("vol_popup_title"),
                        self.t("vol_popup_msg", details=d),
                    ),
                )

        self.alert_meta_label.config(text=self.t("alert_count", n=len(events)))
        self.prev_snapshot = snapshot

    # ── Button callbacks ──────────────────────────────────────────────────────

    def on_refresh_clicked(self) -> None:
        self._refresh_all_from_files()

    def quick_question(self, question: str) -> None:
        self.question_input.delete("1.0", "end")
        self.question_input.insert("1.0", question)
        self.on_ask_clicked()

    def on_ask_clicked(self) -> None:
        question = self.question_input.get("1.0", "end").strip()
        if not question:
            messagebox.showwarning(self.t("warn_title"), self.t("warn_empty"))
            return

        self.set_ai_text(self.t("asking"), self.t("asking_status", t=now_str()))

        def worker() -> None:
            try:
                current_poll = call_poll_once_compat(self.watchlist)
                result = self.agent.answer_user_question(
                    user_question=question,
                    current_poll=current_poll,
                    lang=self.lang,
                )
                text = result.get("ai_text", "")
                self.root.after(
                    0,
                    lambda: self.set_ai_text(
                        text or self.t("no_content"),
                        self.t("ask_done", t=now_str()),
                    ),
                )
                self.root.after(0, lambda: self._update_data_table(current_poll))
            except Exception as e:
                self.root.after(
                    0,
                    lambda: self.set_ai_text(
                        self.t("ask_fail", e=e),
                        self.t("ask_fail_status", t=now_str()),
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def on_inspect_clicked(self) -> None:
        self.set_ai_text(self.t("inspecting"), self.t("inspect_status", t=now_str()))

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
                    lang=self.lang,
                )

                text = result.get("ai_text", "")
                self.root.after(
                    0,
                    lambda: self.set_ai_text(
                        text or self.t("no_content"),
                        self.t("inspect_done", t=now_str()),
                    ),
                )
                self.root.after(0, lambda: self._update_data_table(current_poll))
                self.root.after(0, lambda: self._update_alerts(current_poll, state, settings))
            except Exception as e:
                self.root.after(
                    0,
                    lambda: self.set_ai_text(
                        self.t("inspect_fail", e=e),
                        self.t("inspect_fail_status", t=now_str()),
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def start_monitor_loop(self) -> None:
        if self.monitor_proc and self.monitor_proc.poll() is None:
            messagebox.showinfo(self.t("info_title"), self.t("monitor_already"))
            self.set_monitor_status(self.t("monitor_running_exist"))
            return

        try:
            self.monitor_proc = subprocess.Popen(
                [sys.executable, str(BASE_DIR / "run_monitor_loop.py")],
                cwd=str(BASE_DIR),
            )
            self.set_monitor_status(self.t("monitor_running", pid=self.monitor_proc.pid))
        except Exception as e:
            messagebox.showerror(self.t("err_title"), self.t("monitor_start_err", e=e))
            self.set_monitor_status(self.t("monitor_start_fail"))

    def stop_monitor_loop(self) -> None:
        if not self.monitor_proc or self.monitor_proc.poll() is not None:
            self.set_monitor_status(self.t("monitor_not_running"))
            return

        try:
            self.monitor_proc.terminate()
            self.set_monitor_status(self.t("monitor_stopped"))
        except Exception as e:
            messagebox.showerror(self.t("err_title"), self.t("monitor_stop_err", e=e))

    def _auto_refresh_tick(self) -> None:
        try:
            self._refresh_all_from_files()
            if self.monitor_proc and self.monitor_proc.poll() is None:
                self.set_monitor_status(self.t("monitor_running", pid=self.monitor_proc.pid))
            elif self.monitor_proc:
                self.set_monitor_status(self.t("monitor_exited"))
        finally:
            self.root.after(3000, self._auto_refresh_tick)

    def on_close(self) -> None:
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = FundPilotDashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
