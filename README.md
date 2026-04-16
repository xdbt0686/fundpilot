# FundPilot

A local AI agent for monitoring ETFs, stocks, indices, and crypto — powered by a locally-running LLM (Ollama) and a real-time web dashboard.

FundPilot fetches live market data, evaluates technical signals, generates AI commentary, and provides buy/hold/sell recommendations — all running on your own machine with no cloud dependency.

---

## Features

- **Multi-asset monitoring** — UK UCITS ETFs, US stocks, UK blue chips, global indices, crypto (29 assets out of the box)
- **Real-time web dashboard** — FastAPI + single-page app with WebSocket push, auto-refreshes every 3 seconds
- **3-layer AI Agent** — Planner → Executor → Critic architecture for structured, self-checking analysis
- **PyTorch intent classifier** — character n-gram MLP trained on 390 labelled examples (86% test accuracy), routes user questions to the right tool automatically; falls back to regex rules when confidence is low
- **Technical scoring** — daily / weekly / monthly momentum, MA20 deviation, volume anomaly
- **Buy/hold/sell recommendations** — AI-generated, based on quantitative signal scores
- **ETF overlap analysis** — detects redundant holdings across the watchlist
- **Portfolio composition report** — regional exposure, EM allocation, TER summary
- **Bilingual UI** — toggle all labels, buttons, and AI responses between 中文 and English with one click
- **Alert panel** — card-style severity display with animated highlights for critical events
- **Candlestick charts** — generated on demand, returned inline in the dashboard
- **Fully local** — runs on Ollama (qwen2.5:7b by default), no API keys required

---

## Architecture

```
fundpilot/
├── api/
│   └── server.py            # FastAPI backend — REST + WebSocket endpoints
│
├── frontend/
│   └── index.html           # Single-page web app (vanilla JS, dark theme)
│
├── agent/
│   ├── event_agent.py       # Core AI agent (monitor + Q&A)
│   ├── planner.py           # Decomposes user questions into subtasks
│   ├── executor.py          # Executes subtasks (tools + LLM interpretation)
│   ├── critic.py            # Validates AI answers against raw data
│   └── orchestrator.py      # 3-layer controller: plan → execute → verify
│
├── core/
│   ├── llm.py               # Ollama API client
│   ├── prompts.py           # Bilingual prompt builders (zh/en)
│   ├── router.py            # Intent dispatcher (ML + regex fallback)
│   └── intent_classifier.py # PyTorch inference wrapper
│
├── providers/
│   ├── price_provider.py    # yfinance wrapper with auto symbol resolution
│   └── static_provider.py  # ETF profile loader
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
│   ├── portfolio.py         # Portfolio composition analysis
│   ├── chart.py             # Candlestick chart generation (mplfinance)
│   ├── generate_training_data.py  # Generates intent classifier training set
│   └── train_intent_classifier.py # PyTorch MLP training script
│
├── data/
│   ├── watchlist.json       # Your asset watchlist (edit to customise)
│   └── etfs.json            # ETF static profile data
│
├── web_main.py              # Web dashboard entry point (FastAPI + browser open)
├── run_monitor_loop.py      # Continuous background monitoring loop
├── main.py                  # CLI entry point
└── start_agent.bat          # Windows one-click launcher
```

---

## Quickstart

### Prerequisites

1. **Python 3.10+**
2. **Ollama** — download from [ollama.com](https://ollama.com)
3. Pull the model and start the server:

```bash
ollama pull qwen2.5:7b
ollama serve          # keep this window open
```

### Install

```bash
git clone https://github.com/xdbt0686/fundpilot.git
cd fundpilot
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install fastapi uvicorn yfinance requests mplfinance torch transformers
```

### Run

**Option A — Double-click launcher (Windows)**

```
start_agent.bat
```

Choose from the menu:

| # | Mode |
|---|------|
| 1 | Dashboard + Monitor loop (recommended) |
| 2 | Agent chat (3-layer AI) |
| 3 | Buy recommendations |
| 4 | Dashboard only |
| 5 | Monitor loop only |
| 6 | Overlap analysis |
| 7 | Portfolio analysis |

**Option B — CLI**

```bash
# Web dashboard (opens browser automatically)
python web_main.py

# 3-layer AI agent Q&A
python main.py agent

# Buy/hold/sell recommendations
python main.py recommend

# ETF overlap analysis
python main.py overlap

# Portfolio analysis
python main.py portfolio

# Continuous monitoring loop
python main.py loop
```

---

## Web Dashboard

Open `http://localhost:8765` after launching. The interface has four panels:

| Panel | Contents |
|-------|----------|
| AI Output | Streaming AI analysis and Q&A responses |
| Controls | Ask a question, run inspection, get recommendations, generate charts |
| Alerts | Card-style event feed — colour-coded by severity, animated for critical events |
| Market Data | Live price table with change % and signal badges |

### Language Toggle

Click **EN / 中文** in the header to switch all UI text and AI-generated responses between English and Chinese. The language parameter is forwarded to both the LLM prompt and the signal-scoring labels.

### Monitor Control

Use **Start Monitor** / **Stop Monitor** buttons in the dashboard to manage the background polling loop without leaving the browser.

---

## Intent Classifier

User questions are automatically routed to the correct tool using a two-stage classifier:

1. **PyTorch MLP** — character bigram/trigram features → embedding → mean-pool → 2-layer MLP  
   Trained on 390 labelled examples across 4 intents (`overlap`, `compare`, `portfolio`, `ask`)  
   Test accuracy: **86%**, trains in ~1 second on a consumer GPU

2. **Regex fallback** — activates when ML confidence < 60% or model is not loaded

To retrain after adding new examples:

```bash
python tools/generate_training_data.py
python tools/train_intent_classifier.py
```

---

## Customising the Watchlist

Edit `data/watchlist.json`. Any ticker supported by Yahoo Finance works:

```json
{
  "tickers": [
    "VUAG", "CSP1", "SWDA",
    "AAPL", "NVDA",
    "BTC-USD",
    "^GSPC",
    "BP.L"
  ]
}
```

| Format | Example | Asset type |
|--------|---------|------------|
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
| US stocks / ETFs | ~15 min | Standard Yahoo free-tier delay |
| UK stocks / ETFs | ~15 min | Same |
| Indices (`^GSPC` etc.) | Real-time | Free on Yahoo |
| Crypto (`BTC-USD` etc.) | Real-time | Free on Yahoo |

---

## LLM Configuration

Default model: `qwen2.5:7b` (runs locally via Ollama, recommended for RTX 4060 / 8 GB VRAM)

To switch models:

```bash
set OLLAMA_MODEL=qwen2.5:14b   # higher quality, needs more VRAM
set OLLAMA_MODEL=llama3.2:3b   # lighter alternative
```

Configure a remote Ollama instance:

```bash
set OLLAMA_BASE_URL=http://192.168.1.100:11434
```

---

## License

MIT
