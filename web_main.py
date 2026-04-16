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
    import argparse
    import uvicorn
    from api.server import app  # noqa: F401 — triggers FastAPI app import

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--host", type=str, default=HOST)
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print(f"\n  FundPilot Web  →  {url}\n  Press Ctrl+C to stop.\n")
    threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(url)), daemon=True).start()
    uvicorn.run("api.server:app", host=args.host, port=args.port, reload=False,
                log_level="warning", timeout_graceful_shutdown=0)
