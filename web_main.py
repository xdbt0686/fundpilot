"""FundPilot Web — 启动 FastAPI 服务并自动打开浏览器。"""
from __future__ import annotations

import sys
import time
import threading
import webbrowser
from pathlib import Path

# Make sure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

HOST = "127.0.0.1"
PORT = 8765
URL  = f"http://{HOST}:{PORT}"


def _open_browser() -> None:
    time.sleep(1.2)          # Let uvicorn boot first
    webbrowser.open(URL)


if __name__ == "__main__":
    import uvicorn
    from api.server import app  # noqa: F401 — triggers FastAPI app import

    print(f"\n  FundPilot Web  →  {URL}\n  Press Ctrl+C to stop.\n")
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("api.server:app", host=HOST, port=PORT, reload=False, log_level="warning")
