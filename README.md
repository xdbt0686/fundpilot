# FundPilot 🛰️

A local AI agent for monitoring ETFs, stocks, indices, and crypto — powered by a locally-running LLM (Ollama).

FundPilot fetches real-time market data, evaluates technical signals, generates AI commentary, and provides buy/hold/sell recommendations — all running on your own machine with no cloud dependency.

---

## Features

- **Multi-asset monitoring** — UK ETFs, US stocks, UK blue chips, global indices, crypto (30 assets out of the box)
- **3-layer AI Agent** — Planner → Executor → Critic architecture for structured, self-checking analysis
- **Technical scoring** — daily / weekly / monthly momentum, MA20 deviation, volume anomaly
- **Buy/hold/sell recommendations** — AI-generated, based on quantitative signal scores
- **ETF overlap analysis** — detects redundant holdings across the watchlist
- **Portfolio composition report** — regional exposure, EM allocation, TER summary
- **GUI Dashboard** — Tkinter-based real-time dashboard with alert panel
- **Fully local** — runs on Ollama (qwen2.5:3b by default), no API keys required

---

## Architecture

```
fundpilot/
├── agent/
│   ├── event_agent.py       # Core AI agent (monitor + Q&A)
│   ├── planner.py           # Decomposes user questions into subtasks
│   ├── executor.py          # Executes subtasks (tools + LLM interpretation)
│   ├── critic.py            # Validates AI answers against raw data
│   └── orchestrator.py      # 3-layer controller: plan → execute → verify
│
├── core/
│   ├── llm.py               # Ollama API client
│   ├── prompts.py           # Centralized prompt constants & builders
│   └── router.py            # Intent classifier & tool dispatcher
│
├── providers/
│   ├── price_provider.py    # yfinance wrapper with auto symbol resolution
│   └── static_provider.py  # ETF profile loader (cached)
│
├── monitors/
│   └── price_poller.py      # Poll all watchlist tickers → snapshot
│
├── rules/
│   ├── trigger_rules.py     # Event detection (price moves, reversals, stale data)
│   └── recommendation_rules.py  # Technical scoring → buy/hold/sell signals
│
├── tools/
│   ├── overlap.py           # ETF holdings overlap estimation
│   ├── compare.py           # Side-by-side ETF comparison
│   └── portfolio.py         # Portfolio composition analysis
│
├── models/
│   └── schemas.py           # TypedDict definitions for all data structures
│
├── data/
│   ├── watchlist.json       # Your asset watchlist (edit to customize)
│   └── etfs.json            # ETF static profile data
│
├── main.py                  # Unified CLI entry point
├── fundpilot_dashboard.py   # Tkinter GUI dashboard
├── run_monitor_loop.py      # Continuous monitoring loop
└── start_agent.bat          # Windows launcher (double-click to start)
```

---

## Quickstart

### Prerequisites

1. **Python 3.10+**
2. **Ollama** — download from [ollama.com](https://ollama.com)
3. A running Ollama model:

```bash
ollama pull qwen2.5:3b
ollama serve          # keep this window open
```

### Install

```bash
git clone https://github.com/xdbt0686/fundpilot.git
cd fundpilot
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install yfinance requests ollama win10toast
```

### Run

**Option A — Double-click launcher (Windows)**

```
start_agent.bat
```

Choose a mode from the menu.

**Option B — CLI**

```bash
# Set model (optional, defaults to qwen2.5:3b)
set OLLAMA_MODEL=qwen2.5:3b

# Buy/hold/sell recommendations for all watchlist assets
python main.py recommend

# 3-layer AI agent Q&A
python main.py agent VUAG and CSP1 have diverged today?

# ETF overlap analysis
python main.py overlap

# Side-by-side ETF comparison
python main.py compare VUAG CSP1

# Full portfolio analysis
python main.py portfolio

# Single monitoring cycle
python main.py monitor

# Continuous monitoring loop
python main.py loop

# GUI dashboard
python main.py dashboard
```

---

## Customising the Watchlist

Edit `data/watchlist.json`. Any ticker supported by Yahoo Finance works:

```json
{
  "tickers": [
    "VUAG", "CSP1",
    "AAPL", "NVDA",
    "BTC-USD",
    "^GSPC",
    "BP.L"
  ]
}
```

| Format | Example | Asset type |
|--------|---------|-----------|
| Plain ticker | `AAPL`, `MSFT` | US stocks / ETFs |
| `.L` suffix | `BP.L`, `VUAG.L` | London Stock Exchange |
| `^` prefix | `^GSPC`, `^FTSE` | Indices |
| `-USD` suffix | `BTC-USD`, `ETH-USD` | Crypto |
| `.HK` suffix | `0700.HK` | Hong Kong stocks |

---

## Monitoring Settings

Create `data/monitor_settings.json` to override defaults:

```json
{
  "poll_interval_seconds": 300,
  "ai_cooldown_minutes": 10,
  "heartbeat_minutes": 30,
  "daily_move_alert_pct": 1.5,
  "daily_move_strong_pct": 3.0,
  "reversal_pct": 1.0,
  "stale_data_minutes": 20
}
```

---

## Data Source

All market data comes from **Yahoo Finance** via the `yfinance` library.

| Asset type | Delay | Notes |
|-----------|-------|-------|
| US stocks | ~15 min | Standard Yahoo free-tier delay |
| UK stocks / ETFs | ~15 min | Same |
| Indices (^GSPC etc.) | Real-time | Free on Yahoo |
| Crypto (BTC-USD etc.) | Real-time | Free on Yahoo |

> **Note:** Yahoo Finance has no official SLA. Data availability may vary. The `yfinance` library has historically required periodic updates when Yahoo changes its API.

---

## LLM Configuration

Default model: `qwen2.5:3b` (runs locally via Ollama)

To use a larger model for better analysis quality:

```bash
set OLLAMA_MODEL=qwen2.5:7b    # better reasoning
set OLLAMA_MODEL=llama3.2:3b   # alternative
```

Configure Ollama endpoint if not running on localhost:

```bash
set OLLAMA_BASE_URL=http://192.168.1.100:11434
```

---

## License

MIT
