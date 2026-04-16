"""FundPilot FastAPI backend."""
from __future__ import annotations

import asyncio
import base64
import inspect
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).resolve().parent.parent
DATA_DIR   = BASE_DIR / "data"
FRONT_DIR  = BASE_DIR / "frontend"

WATCHLIST_FILE      = DATA_DIR / "watchlist.json"
LAST_SNAPSHOT_FILE  = DATA_DIR / "last_snapshot.json"
MONITOR_STATE_FILE  = DATA_DIR / "monitor_state.json"
MONITOR_SETTINGS_FILE = DATA_DIR / "monitor_settings.json"
CHARTS_DIR          = DATA_DIR / "charts"

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

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="FundPilot API", docs_url="/api/docs")

# Serve frontend static files
app.mount("/static", StaticFiles(directory=str(FRONT_DIR)), name="static")

# Global monitor process handle
_monitor_proc: Optional[subprocess.Popen] = None

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_settings() -> Dict[str, Any]:
    s = dict(DEFAULT_SETTINGS)
    fs = _load_json(MONITOR_SETTINGS_FILE, {})
    if isinstance(fs, dict):
        s.update(fs)
    return s


def _load_watchlist() -> List[str]:
    data = _load_json(WATCHLIST_FILE, [])
    if isinstance(data, dict):
        items = data.get("tickers") or data.get("watchlist") or []
        if isinstance(items, list):
            return [str(x).upper().strip() for x in items if str(x).strip()]
    elif isinstance(data, list):
        return [str(x).upper().strip() for x in data if str(x).strip()]
    return ["VUAG", "CSP1", "SWDA", "HMWS", "VWRP", "VWRL"]


def _call_poll_once(watchlist: List[str]) -> Dict[str, Any]:
    from monitors.price_poller import poll_once
    try:
        sig = inspect.signature(poll_once)
        result = poll_once(watchlist) if sig.parameters else poll_once()
    except (TypeError, ValueError):
        try:
            result = poll_once(watchlist)
        except TypeError:
            result = poll_once()
    if not isinstance(result, dict):
        raise RuntimeError(f"poll_once returned {type(result).__name__}")
    result.setdefault("polled_at", datetime.now().isoformat(timespec="seconds"))
    result.setdefault("data", {})
    return result


def _monitor_status() -> Dict[str, Any]:
    global _monitor_proc
    if _monitor_proc is None:
        return {"running": False, "pid": None, "status": "not_started"}
    code = _monitor_proc.poll()
    if code is None:
        return {"running": True, "pid": _monitor_proc.pid, "status": "running"}
    return {"running": False, "pid": _monitor_proc.pid, "status": f"exited({code})"}

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(str(FRONT_DIR / "index.html"))


@app.get("/api/watchlist")
async def get_watchlist():
    return {"tickers": _load_watchlist()}


@app.get("/api/settings")
async def get_settings():
    return _load_settings()


@app.get("/api/snapshot")
async def get_snapshot():
    snapshot = _load_json(LAST_SNAPSHOT_FILE, {})
    if not isinstance(snapshot, dict):
        snapshot = {}
    return snapshot


@app.get("/api/alerts")
async def get_alerts():
    from rules.trigger_rules import evaluate_triggers
    snapshot = _load_json(LAST_SNAPSHOT_FILE, {})
    state    = _load_json(MONITOR_STATE_FILE, {})
    settings = _load_settings()
    if not isinstance(snapshot, dict) or not snapshot:
        return {"events": [], "market_summary": {}}
    try:
        result = evaluate_triggers(
            current_poll=snapshot,
            last_snapshot=None,
            state=state,
            config=settings,
        )
        return result
    except Exception as e:
        return {"events": [], "error": str(e)}


# ── AI Actions ────────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    lang: str = "zh"


class InspectRequest(BaseModel):
    lang: str = "zh"


class RecommendRequest(BaseModel):
    lang: str = "zh"


class ChartRequest(BaseModel):
    ticker: str
    period: str = "3mo"


@app.post("/api/ask")
async def ask_ai(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(400, "question cannot be empty")
    try:
        loop = asyncio.get_event_loop()
        watchlist = _load_watchlist()

        def _run():
            from agent.event_agent import EventAgent
            poll = _call_poll_once(watchlist)
            result = EventAgent().answer_user_question(
                user_question=req.question,
                current_poll=poll,
                lang=req.lang,
            )
            return result.get("ai_text", ""), poll

        ai_text, poll = await loop.run_in_executor(None, _run)
        return {"ai_text": ai_text or "（无回答）", "snapshot": poll}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/inspect")
async def inspect_ai(req: InspectRequest):
    try:
        loop = asyncio.get_event_loop()
        watchlist = _load_watchlist()

        def _run():
            from agent.event_agent import EventAgent
            from rules.trigger_rules import evaluate_triggers
            poll     = _call_poll_once(watchlist)
            state    = _load_json(MONITOR_STATE_FILE, {})
            settings = _load_settings()
            trigger_result = evaluate_triggers(
                current_poll=poll, last_snapshot=None, state=state, config=settings,
            )
            result = EventAgent().analyze_monitor_cycle(
                current_poll=poll, trigger_result=trigger_result, lang=req.lang,
            )
            return result.get("ai_text", ""), poll, trigger_result

        ai_text, poll, triggers = await loop.run_in_executor(None, _run)
        return {
            "ai_text": ai_text or "（无回答）",
            "snapshot": poll,
            "alerts": triggers,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/recommend")
async def recommend_ai(req: RecommendRequest):
    try:
        loop = asyncio.get_event_loop()
        watchlist = _load_watchlist()

        def _run():
            from rules.recommendation_rules import evaluate_all
            from core.prompts import get_recommend_system, build_recommend_prompt
            from core.llm import ask_llm
            poll       = _call_poll_once(watchlist)
            evaluation = evaluate_all(poll, lang=req.lang)
            ai_text    = ask_llm(
                get_recommend_system(req.lang),
                build_recommend_prompt(evaluation, poll, lang=req.lang),
            )
            return ai_text, evaluation, poll

        ai_text, evaluation, poll = await loop.run_in_executor(None, _run)
        ratings = {
            k: {
                "score": v["score"],
                "signal": v["signal"],
                "signal_label": v["signal_label"],
                "price_snapshot": v.get("price_snapshot", {}),
            }
            for k, v in evaluation.get("ratings", {}).items()
        }
        return {
            "ai_text": ai_text or "（无回答）",
            "ratings": ratings,
            "snapshot": poll,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/history/{ticker}")
async def get_history(ticker: str, period: str = "3mo"):
    """Return OHLCV bars for TradingView Lightweight Charts."""
    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()

        def _fetch():
            import math
            t = yf.Ticker(ticker.upper())
            hist = t.history(period=period)
            if hist.empty:
                return []
            bars = []
            for date, row in hist.iterrows():
                try:
                    o = float(row["Open"])
                    h = float(row["High"])
                    l = float(row["Low"])
                    c = float(row["Close"])
                    # skip bars with NaN prices (TradingView rejects them)
                    if any(math.isnan(x) for x in (o, h, l, c)):
                        continue
                    vol = int(row["Volume"]) if not math.isnan(float(row["Volume"])) else 0
                except Exception:
                    continue
                bars.append({
                    "time":   date.strftime("%Y-%m-%d"),
                    "open":   round(o, 4),
                    "high":   round(h, 4),
                    "low":    round(l, 4),
                    "close":  round(c, 4),
                    "volume": vol,
                })
            return bars

        bars = await loop.run_in_executor(None, _fetch)
        return {"ticker": ticker.upper(), "period": period, "bars": bars}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/chart")
async def generate_chart(req: ChartRequest):
    try:
        loop = asyncio.get_event_loop()

        def _run():
            from tools.chart import plot_kline
            path = plot_kline(req.ticker.upper(), period=req.period, show=False, save=True)
            return path

        path = await loop.run_in_executor(None, _run)

        if path and Path(path).exists():
            img_bytes = Path(path).read_bytes()
            b64 = base64.b64encode(img_bytes).decode()
            return {
                "success": True,
                "ticker": req.ticker.upper(),
                "period": req.period,
                "image_b64": b64,
                "path": str(path),
            }
        return {"success": False, "error": "Chart file not found"}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Monitor control ───────────────────────────────────────────────────────────

@app.get("/api/monitor/status")
async def monitor_status():
    return _monitor_status()


@app.post("/api/monitor/start")
async def monitor_start():
    global _monitor_proc
    if _monitor_proc and _monitor_proc.poll() is None:
        return {"ok": False, "message": "already_running", **_monitor_status()}
    try:
        _monitor_proc = subprocess.Popen(
            [sys.executable, str(BASE_DIR / "run_monitor_loop.py")],
            cwd=str(BASE_DIR),
        )
        return {"ok": True, **_monitor_status()}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/monitor/stop")
async def monitor_stop():
    global _monitor_proc
    if not _monitor_proc or _monitor_proc.poll() is not None:
        return {"ok": False, "message": "not_running"}
    try:
        _monitor_proc.terminate()
        return {"ok": True, "status": "stopped"}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── WebSocket for real-time push ──────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            snapshot = _load_json(LAST_SNAPSHOT_FILE, {})
            status   = _monitor_status()
            await ws.send_json({
                "type": "tick",
                "snapshot": snapshot if isinstance(snapshot, dict) else {},
                "monitor": status,
                "ts": datetime.now().isoformat(timespec="seconds"),
            })
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        pass
