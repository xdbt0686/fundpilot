# FundPilot

A local AI agent for monitoring ETFs, stocks, indices, and crypto — powered by a locally-running LLM (Ollama) and a real-time web dashboard.

FundPilot fetches live market data, evaluates technical signals, generates AI commentary, and provides buy/hold/sell recommendations — all running on your own machine with no cloud dependency.

---

## Features

- **Multi-asset monitoring** — UK UCITS ETFs, US stocks, UK blue chips, global indices, crypto (29 assets out of the box)
- **Real-time web dashboard** — FastAPI + single-page app with WebSocket push, auto-refreshes every 3 seconds
- **Interactive K-line charts** — TradingView Lightweight Charts embedded in the dashboard; click any ticker to load OHLCV candlesticks with 1M / 3M / 6M / 1Y / 2Y period selector
- **3-layer AI Agent** — Planner → Executor → Critic architecture for structured, self-checking analysis
- **PyTorch intent classifier** — character n-gram MLP trained on 390 labelled examples; accuracy **89.8%** on held-out test set (+15.3 pp over regex baseline), routes user questions to the correct tool automatically
- **Technical scoring** — daily / weekly / monthly momentum, MA20 deviation, volume anomaly
- **Buy/hold/sell recommendations** — AI-generated, based on quantitative signal scores
- **ETF overlap analysis** — detects redundant holdings across the watchlist
- **Portfolio composition report** — regional exposure, EM allocation, TER summary
- **Bilingual UI** — toggle all labels, buttons, and AI responses between 中文 and English with one click
- **Alert highlights** — colour-coded row highlights and severity dots for critical events
- **Fully local** — runs on Ollama (qwen2.5:14b by default), no API keys required

---

## Architecture

```
fundpilot/
├── api/
│   └── server.py            # FastAPI backend — REST + WebSocket endpoints
│
├── frontend/
│   └── index.html           # Single-page web app (vanilla JS, TradingView Charts, dark theme)
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
│   ├── price_tool.py        # On-demand price lookup helper
│   ├── generate_training_data.py  # Generates intent classifier training set
│   └── train_intent_classifier.py # PyTorch MLP training script
│
├── normalizers/
│   └── etf_normalizer.py    # Normalises raw yfinance ETF data into a standard schema
│
├── notifiers/
│   └── console_notifier.py  # Prints formatted alert messages to the console
│
├── models/
│   └── schemas.py           # Pydantic / dataclass schemas shared across modules
│
├── tests/
│   ├── test_recommendation_rules.py
│   ├── test_router.py
│   └── test_trigger_rules.py
│
├── data/
│   ├── watchlist.json       # Your asset watchlist (edit to customise)
│   └── etfs.json            # ETF static profile data
│
├── web_main.py              # Web dashboard entry point (FastAPI + browser open)
├── run_monitor_loop.py      # Continuous background monitoring loop
├── run_monitor_once.py      # Run a single monitor cycle and print results (debug helper)
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
ollama pull qwen2.5:14b
ollama serve          # keep this window open
```

### Install

```bash
git clone https://github.com/xdbt0686/fundpilot.git
cd fundpilot
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install fastapi uvicorn yfinance requests mplfinance torch
```

### Train the intent classifier

Required on first run (model files are not checked in):

```bash
python tools/generate_training_data.py
python tools/train_intent_classifier.py
```

Trains in ~1 second on a consumer GPU. Outputs to `data/intent_model/`.

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
python web_main.py [--port 8765] [--host 127.0.0.1]

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
| AI Output | AI analysis and Q&A responses |
| Controls | Ask a question, run inspection, get recommendations, start/stop monitor |
| K-Line Chart | Interactive TradingView candlestick chart — click any row in the data table to load |
| Market Data | Live price table with change % and alert highlights |

### K-Line Chart

Click any ticker row in the data table to load its candlestick chart. Use the period buttons to switch between **1M / 3M / 6M / 1Y / 2Y**. Data is fetched from `/api/history/{ticker}` and rendered client-side via TradingView Lightweight Charts.

### Language Toggle

Click **EN / 中文** in the header to switch all UI text and AI-generated responses between English and Chinese. The language parameter is forwarded to both the LLM prompt and the signal-scoring labels.

### Monitor Control

Use **Start Monitor** / **Stop Monitor** buttons in the dashboard to manage the background polling loop without leaving the browser.

---

## Intent Classifier

User questions are automatically routed to the correct tool using a two-stage classifier:

1. **PyTorch MLP** — character n-gram features (unigram + bigram + trigram) → embedding → mean-pool → 2-layer MLP
   Trained on 390 labelled examples across 4 intents (`overlap`, `compare`, `portfolio`, `ask`)

2. **Regex fallback** — activates when ML confidence < 60% or model is not loaded

### Benchmark (59-sample held-out test set)

| Method | Correct | Accuracy | Main failure mode |
|---|---|---|---|
| Regex keyword matching | 44 / 59 | 74.6% | Paraphrased and cross-lingual queries |
| PyTorch n-gram MLP | 53 / 59 | **89.8%** | Semantically ambiguous queries |
| **Improvement** | **+9** | **+15.3 pp** | |

The classifier handles natural-language paraphrases that regex cannot match, e.g.:
- "帮我看看有没有买了差不多东西的ETF" → correctly routed to `overlap` (no keyword "重叠")
- "find duplicate stocks across my ETFs" → correctly routed to `overlap` (English, no Chinese patterns)

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

Default model: `qwen2.5:14b` (runs locally via Ollama, recommended for RTX 4060 / 8 GB VRAM)

To switch models:

```bash
set OLLAMA_MODEL=qwen2.5:7b    # lighter, faster
set OLLAMA_MODEL=llama3.1:8b   # alternative architecture
```

To store models on a non-system drive:

```bash
setx OLLAMA_MODELS "D:\ollama\models"
# restart Ollama after setting
```

Configure a remote Ollama instance:

```bash
set OLLAMA_BASE_URL=http://192.168.1.100:11434
```

---

## License

MIT
