# FundPilot 代码详解报告

> 本报告对项目中每一个源文件、每一个类、每一个函数逐行说明其用途。
> 适合在完全不了解代码背景的情况下从头阅读。

---

## 一、项目总体结构

```
FundPilot/
│
├── 入口层
│   ├── main.py              # 命令行入口，10 条子命令
│   ├── web_main.py          # Web 服务入口，自动打开浏览器
│   ├── run_monitor_loop.py  # 持续监控循环（后台轮询）
│   └── run_monitor_once.py  # 单次手动巡检
│
├── API 层
│   └── api/server.py        # FastAPI 后端，所有 HTTP + WebSocket 接口
│
├── 前端层
│   └── frontend/index.html  # 单页应用（SPA），浏览器界面
│
├── Agent 层（AI 大脑）
│   ├── agent/event_agent.py    # 最简单的 AI 调用封装
│   ├── agent/planner.py        # 规划器：把问题拆成子任务
│   ├── agent/executor.py       # 执行器：跑工具 + LLM 解读
│   ├── agent/critic.py         # 校验器：检查答案是否与数据一致
│   └── agent/orchestrator.py   # 总控：Planner→Executor→Critic 三层流程
│
├── Core 层（核心工具）
│   ├── core/llm.py              # 调 Ollama 的函数
│   ├── core/prompts.py          # 所有 AI 提示词模板
│   ├── core/router.py           # 意图分类（ML 模型 + 正则兜底）
│   ├── core/intent_classifier.py# PyTorch 模型推理封装
│   └── core/utils.py            # 通用工具函数（读文件、加载配置等）
│
├── 数据层
│   ├── monitors/price_poller.py    # 批量拉取 watchlist 价格
│   ├── providers/price_provider.py # 单只股票/ETF 价格（yfinance）
│   └── providers/static_provider.py# 静态数据（ETF profiles）
│
├── 规则层（无 AI 的纯逻辑）
│   ├── rules/trigger_rules.py       # 触发规则：涨跌幅/反转/数据过期
│   └── rules/recommendation_rules.py# 技术评分：给每只资产打分
│
├── 工具层（分析工具）
│   ├── tools/overlap.py    # ETF 持仓重叠分析
│   ├── tools/compare.py    # 两只 ETF 对比
│   ├── tools/portfolio.py  # 整体组合分析
│   ├── tools/chart.py      # K 线图生成
│   ├── tools/etf_profile.py# 获取 ETF 基本信息
│   └── tools/price_tool.py # 单只资产价格工具
│
├── 通知层
│   └── notifiers/console_notifier.py # Windows 桌面通知
│
└── 模型层
    └── models/schemas.py   # 数据结构定义（TypedDict）
```

---

## 二、数据流总图

用户打开浏览器 → 前端 SPA → FastAPI server.py → 调 agent/rules/tools → 调 Ollama LLM → 返回文字

监控循环：每 N 秒 → price_poller 拉数据 → trigger_rules 判断有没有异常 → 有异常则调 EventAgent → Ollama 生成摘要 → 存快照文件

---

## 三、入口层

---

### `main.py` — 命令行入口

这是整个项目的 **CLI（命令行界面）总入口**。当你在终端输入 `python main.py xxx` 时就跑这里。

```python
BASE_DIR = Path(__file__).resolve().parent   # 项目根目录的绝对路径
DATA_DIR = BASE_DIR / "data"                  # data/ 目录
WATCHLIST_FILE = DATA_DIR / "watchlist.json" # 监控列表文件路径
DEFAULT_WATCHLIST = [...]                     # 如果文件不存在就用这个默认列表
```

**`_load_json(path, default)`**
读 JSON 文件，文件不存在或损坏时返回 default，不崩溃。

**`_load_watchlist()`**
读 `data/watchlist.json`，支持两种格式：
- `{"tickers": ["VUAG", ...]}` → 取 tickers 字段
- `["VUAG", ...]` → 直接是列表

把每个 ticker 转成大写并去除空白。

**`cmd_ask(args)`**
处理 `python main.py ask <问题>` 命令：
1. 拼接命令行参数为问题字符串
2. 调 `poll_once()` 拉最新价格
3. 调 `Router.route()` 判断意图并预计算相关数据
4. 调 `EventAgent().answer_user_question()` 让 AI 回答
5. 打印 AI 文字

**`cmd_overlap()`**
处理 `python main.py overlap`：
- 调 `analyze_watchlist_overlap()` 计算所有 ETF 两两重叠率
- 打印重叠率 ≥ 高的 ETF 对

**`cmd_compare(args)`**
处理 `python main.py compare VUAG CSP1`：
- 取前两个参数为 ticker A、B
- 拉价格数据
- 调 `compare_etfs()` 进行对比
- 打印对比要点列表

**`cmd_portfolio()`**
处理 `python main.py portfolio`：
- 拉整个 watchlist 的价格
- 调 `analyze_portfolio()` 生成组合报告
- 打印地域分布、TER 平均值、新兴市场敞口、集中度警告

**`cmd_chart(args)`**
处理 `python main.py chart VUAG 3mo`：
- 第一个参数是 ticker，第二个是周期（默认 3mo）
- 调 `plot_kline()` 下载历史数据并生成 K 线图 PNG

**`cmd_recommend()`**
处理 `python main.py recommend`：
1. 拉全 watchlist 价格（会比较慢，首次需探测 Yahoo 符号）
2. 调 `evaluate_all()` 对每只资产算技术评分
3. 打印评分表格（信号 + 日/周/月涨跌）
4. 调 LLM 生成买入建议文字

**`cmd_agent(args)`**
处理 `python main.py agent <问题>`（三层架构版本）：
- 调 `Orchestrator().run(question)` 走完整的 Planner→Executor→Critic 流程
- 打印最终答案 + 执行轮次 + 计划步骤

**`cmd_monitor()` / `cmd_loop()` / `cmd_dashboard()`**
直接用 `subprocess.run()` 启动对应的 Python 脚本，相当于"启动子进程"。

**`_COMMANDS` 字典 + `main()` 函数**
`_COMMANDS` 是命令名 → 处理函数的映射表。
`main()` 读取 `sys.argv`（命令行参数），找到第一个参数对应的命令，调用对应函数。

---

### `web_main.py` — Web 服务入口

```python
HOST = "127.0.0.1"   # 只监听本机，外网访问不到（安全）
PORT = 8765           # 端口号，浏览器访问 http://localhost:8765
URL  = f"http://{HOST}:{PORT}"
```

**`_open_browser()`**
等待 1.2 秒后用系统默认浏览器打开 URL。
为什么要等 1.2 秒？因为 uvicorn 启动需要时间，否则浏览器打开时服务还没就绪。

**`if __name__ == "__main__":` 主流程**
1. 打印启动提示
2. 用 `threading.Thread` 启动一个后台线程去打开浏览器（daemon=True 意味着主进程退出时这个线程也自动结束）
3. 启动 uvicorn 运行 FastAPI 应用（阻塞，直到 Ctrl+C）

---

### `run_monitor_loop.py` — 持续监控循环

这是后台监控的核心，**一直在跑的无限循环**。

**`can_call_ai(state, current_ts, cooldown_minutes)`**
判断距离上次调 AI 是否超过冷却时间（默认 10 分钟）。
防止 AI 每隔几秒就被调用一次浪费资源。

**`notify_text(title, message)`**
先尝试调 Windows 通知，失败就打印到终端。

**`build_notification_text(ai_result)`**
把 AI 结果格式化成适合通知的短文本：
- 上涨/下跌/平的数量
- 最大波动的 ticker
- 前 3 条事件
- AI 摘要（最多 1200 字）

**`main()` 主循环**
```
while True:
    1. 拉当前价格（poll_once）
    2. 读上次快照和状态文件
    3. 跑触发规则（evaluate_triggers）
    4. 如果有异常 AND 冷却时间到了 → 调 AI 分析
    5. 发通知
    6. 保存新快照
    7. 等待 N 秒（由 poll_interval_seconds 设置）
```

---

### `run_monitor_once.py` — 单次巡检

和 loop 一样，但只跑一次，然后把所有原始数据打印出来，用于调试。

---

## 四、API 层

---

### `api/server.py` — FastAPI 后端

这是 **Web 版的所有接口**，前端页面通过这里拿数据。

**路径常量**
```python
BASE_DIR   # 项目根目录
DATA_DIR   # data/ 目录
FRONT_DIR  # frontend/ 目录
WATCHLIST_FILE       # data/watchlist.json
LAST_SNAPSHOT_FILE   # data/last_snapshot.json（最新一次价格快照）
MONITOR_STATE_FILE   # data/monitor_state.json（监控状态，如上次 AI 调用时间）
MONITOR_SETTINGS_FILE# data/monitor_settings.json（用户自定义配置）
CHARTS_DIR           # data/charts/（图表存放目录）
```

**`DEFAULT_SETTINGS`**
默认配置值，用户没有 monitor_settings.json 时使用：
- `poll_interval_seconds: 10` → 每 10 秒拉一次价格
- `ai_cooldown_minutes: 10` → AI 分析最少间隔 10 分钟
- `heartbeat_minutes: 30` → 即使没有异常，每 30 分钟也强制巡检一次
- `daily_move_alert_pct: 1.5` → 日涨跌超过 1.5% 触发提醒
- `daily_move_strong_pct: 3.0` → 超过 3.0% 触发强警报
- `stale_data_minutes: 20` → 数据超过 20 分钟没更新就报"数据过期"

**`app = FastAPI(...)`**
创建 FastAPI 应用实例，`docs_url="/api/docs"` 意味着你访问 `localhost:8765/api/docs` 可以看到接口文档。

**`app.mount("/static", ...)`**
把 `frontend/` 目录挂载为静态文件服务，这样浏览器才能加载 CSS/JS。

**辅助函数**

`_load_json(path, default)` — 同 main.py，安全读 JSON。

`_load_settings()` — 合并默认配置和用户配置（用户配置覆盖默认）。

`_load_watchlist()` — 读 watchlist，同 main.py。

`_call_poll_once(watchlist)` — 调 `price_poller.poll_once()`，并处理不同版本的函数签名兼容性，确保返回值一定有 `polled_at` 和 `data` 字段。

`_monitor_status()` — 检查后台监控进程是否在运行，返回 `{running, pid, status}`。

**HTTP 接口（路由）**

| 路径 | 方法 | 作用 |
|------|------|------|
| `/` | GET | 返回 `frontend/index.html`（主页面）|
| `/api/watchlist` | GET | 返回当前 watchlist 列表 |
| `/api/settings` | GET | 返回当前配置 |
| `/api/snapshot` | GET | 返回 `last_snapshot.json` 里的最新价格数据 |
| `/api/alerts` | GET | 对最新快照跑触发规则，返回事件列表 |
| `/api/ask` | POST | 用户提问，调 EventAgent 返回 AI 答案 |
| `/api/inspect` | POST | 手动触发一次监控巡检，返回 AI 分析 |
| `/api/recommend` | POST | 技术评分 + AI 购买建议 |
| `/api/chart` | POST | 生成 K 线图，返回 base64 编码的 PNG |
| `/api/monitor/status` | GET | 监控进程状态 |
| `/api/monitor/start` | POST | 启动监控子进程 |
| `/api/monitor/stop` | POST | 停止监控子进程 |

**WebSocket `/ws`**
```python
while True:
    读取最新快照 → 发给前端 → 等 3 秒 → 重复
```
每 3 秒向所有连接的浏览器推送最新数据，这就是"实时刷新"的原理。
当浏览器断开连接时，`WebSocketDisconnect` 异常被捕获，循环退出。

**AI 接口工作流（以 `/api/ask` 为例）**
```
1. 验证 question 非空
2. 获取 event_loop（异步事件循环）
3. 在线程池（run_in_executor）里跑同步代码（因为 LLM 调用是阻塞的）
4. 里面：poll_once → EventAgent.answer_user_question → 返回 ai_text
5. 返回 JSON {ai_text, snapshot}
```
为什么用 `run_in_executor`？FastAPI 是异步框架，不能直接在异步函数里跑阻塞代码，否则会卡住整个服务器。用线程池可以让阻塞代码在后台线程跑，主线程继续处理其他请求。

---

## 五、Agent 层

---

### `agent/event_agent.py` — 最简单的 AI 封装

**这是最基础的 AI 调用层**，不做任务拆解，直接把数据喂给 LLM。

```python
try:
    from core.llm import ask_llm
except Exception as e:
    ask_llm = None   # 如果 LLM 模块加载失败，记录错误但不崩溃
```
这种写法叫"防御性导入"，模块加不了也能继续运行（只是 AI 功能不可用）。

**`_load_profiles_for_tickers(tickers)`**
批量查询 ETF 基本信息，失败的单独记录错误，不影响其他的。

**`_call_local_llm(system_prompt, user_prompt)`**
实际调用 LLM 的函数，捕获所有异常，失败时返回错误文字而不是崩溃。

**`class EventAgent`**

`analyze_monitor_cycle(current_poll, trigger_result, profiles, lang)` — 监控巡检分析：
1. 从价格数据中提取所有 ticker
2. 加载这些 ticker 的 ETF 基本信息
3. 调 LLM，system prompt 是"你是监控 agent"，user prompt 包含最新价格 + 触发事件 + ETF 资料
4. 返回 `{mode, summary, events, ai_text}`

`answer_user_question(user_question, current_poll, profiles, extra_context, lang)` — 回答用户问题：
1. 组织数据（价格 + ETF 资料 + 额外工具计算结果）
2. 调 LLM，system prompt 是"你是问答 agent"
3. 返回 `{mode, question, ai_text}`

---

### `agent/planner.py` — 规划器

**把一个用户问题拆成 2-4 个子任务的 JSON 列表。**

**`class SubTask`**
代表一个子任务，属性：
- `id` — 编号（0, 1, 2...）
- `task` — 任务描述（中文）
- `tool` — 要调的工具名（poll/overlap/compare/portfolio/synthesize 等）
- `args` — 传给工具的参数（比如 compare 需要 `ticker_a`, `ticker_b`）
- `depends_on` — 依赖的其他子任务 ID 列表（拓扑排序用）

**`_extract_json_array(text)`**
从 LLM 输出中提取 JSON 数组，处理三种常见情况：
1. 被 ` ```json ... ``` ` 包裹的 → 先去掉包裹
2. 纯 JSON 数组 → 直接解析
3. 找第一个 `[` 到对应 `]` 之间的内容 → 手动匹配括号深度

**`_fallback_plan(question, watchlist)`**
如果 LLM 输出解析失败，用这个最简单的保底计划：只做 `poll`（拉数据）然后 `synthesize`（综合回答）。

**`_parse_plan(raw, question, watchlist)`**
把 LLM 返回的 JSON 列表转成 SubTask 对象列表：
- 验证每个 tool 是否在合法列表里，不合法就换成 synthesize
- 确保最后一个任务一定是 synthesize（收尾任务）
- 如果列表为空，用 fallback

**`class Planner` + `plan(question, watchlist)`**
1. 调 LLM，把用户问题和 watchlist 传给 PLANNER_SYSTEM 提示词
2. 解析 LLM 返回的 JSON
3. 打印计划步骤
4. 返回 SubTask 列表

---

### `agent/executor.py` — 执行器

**按顺序执行子任务，每个任务调工具并用 LLM 解读结果。**

**`class SubTaskResult`**
保存一个子任务的执行结果：
- `tool_output` — 工具原始返回数据
- `interpretation` — LLM 对工具数据的解读（2-4句话）

**`_run_tool(task, current_poll, watchlist)`**
根据 `task.tool` 调用对应工具：

| tool | 调用的函数 |
|------|-----------|
| `poll` | 直接返回 current_poll（已有数据，不重复请求）|
| `overlap` | `analyze_watchlist_overlap()` |
| `compare` | `compare_etfs(ta, tb, current_poll)` |
| `portfolio` | `analyze_portfolio(tickers, current_poll)` |
| `profile` | `get_etf_profile(ticker)` |
| `recommend` | `evaluate_all(current_poll)` |
| `alert` | `evaluate_triggers(current_poll)` |
| `history` | `get_history_summary(ticker, period)` |
| `chart` | `plot_kline()` + `get_history_summary()` |
| `synthesize` | 不调工具，返回 None |

**`class Executor` + `execute(tasks, question, current_poll, watchlist, critic_hint)`**
按顺序处理每个 SubTask：

对于普通工具任务：
1. `_run_tool()` → 得到原始数据
2. 原始数据存入 `raw_data`（供 Critic 校验用）
3. `ask_llm(EXECUTOR_SYSTEM, build_executor_prompt(...))` → LLM 解读（2-4句）
4. 结果存入 `results[task.id]`

对于 synthesize 任务：
1. 收集所有前驱任务的解读结果
2. 如果有 `critic_hint`（上一轮校验的修正建议），拼接到 prompt 里
3. `ask_llm(SYNTHESIZER_SYSTEM, build_synthesizer_prompt(...))` → 综合最终答案

最后找最后一个 synthesize 任务的 interpretation 作为 final_answer。

---

### `agent/critic.py` — 校验器

**检查 AI 的回答有没有编造数据或和原始数据矛盾。**

**`class CriticVerdict`**
校验结果：
- `valid: bool` — 是否通过
- `issues: List[str]` — 发现的问题列表
- `hint: str` — 给 Executor 重跑时的修正建议

**`_extract_verdict(text)`**
从 LLM 输出中提取 JSON 格式的校验结果：
`{"valid": true/false, "issues": [...], "hint": "..."}`

**`class Critic` + `verify(question, answer, raw_data)`**
1. 调 LLM，system prompt 是"你是事实核查员"，user prompt 包含：
   - 用户问题
   - AI 的回答
   - 原始数据（工具返回的真实数字）
2. 解析 LLM 返回的 JSON
3. 如果解析失败，默认认为通过（宽松策略，避免卡死）

---

### `agent/orchestrator.py` — 总控制器

**三层架构的指挥中心**，把 Planner、Executor、Critic 串联起来。

```python
class Orchestrator:
    def __init__(self, max_retries=2):
        # 最多重试 2 次（总共最多跑 3 轮）
```

**`run(question, current_poll, watchlist)`完整流程：**

```
Step 1 - 规划
  Planner.plan(question, watchlist)
  → 得到 tasks 列表（比如 [{poll}, {overlap}, {synthesize}]）

Step 2 - 执行（最多 max_retries+1 轮）
  Executor.execute(tasks, ...)
  → 得到 final_answer + raw_data

Step 3 - 校验
  Critic.verify(question, final_answer, raw_data)
  → 如果通过 → 结束
  → 如果不通过 → critic_hint 传给下一轮 Executor → 重试

返回：
  {
    question, final_answer,
    plan,           # 计划步骤列表（字符串）
    attempts,       # 实际执行了几轮
    critic_passed,  # 最终是否通过校验
    subtask_results,# 每个子任务的详细结果
    timestamp       # UTC 时间戳
  }
```

---

## 六、Core 层

---

### `core/llm.py` — Ollama 调用

**所有 LLM 调用最终都走这里。**

核心函数 `ask_llm(system_prompt, user_prompt)`:
1. 读环境变量 `OLLAMA_MODEL`（默认 `qwen2.5:7b`）和 `OLLAMA_BASE_URL`（默认本机）
2. 向 Ollama API 发 POST 请求
3. 解析返回的文字
4. 返回纯文本字符串

---

### `core/prompts.py` — 提示词工厂

**所有 AI 提示词都在这里定义，是 AI 行为的"说明书"。**

**`_NO_META`**
防止 LLM 解释 JSON 数据结构的 guardrail 字符串：
> "IMPORTANT: Do NOT describe, explain, or summarize the structure of the input data..."

这句话被注入到每个 system prompt 的末尾，防止 LLM 输出"以上数据包含以下字段..."这类废话。

**`_lang_directive(lang)`**
根据语言返回输出要求（中文/英文），以及输出结构模板。

**各 prompt 构建函数：**

| 函数 | 作用 |
|------|------|
| `get_monitor_system(lang)` | 监控巡检的 system prompt（你是 FundPilot 监控 agent）|
| `build_monitor_prompt(current_poll, trigger_result, profiles, lang)` | 把价格数据 + 触发事件 + ETF 资料组装成 user prompt |
| `get_ask_system(lang)` | 问答的 system prompt |
| `build_ask_prompt(question, current_poll, profiles, extra_context, lang)` | 把问题 + 数据组装成 user prompt |
| `OVERLAP_SYSTEM` | 重叠分析的 system prompt |
| `build_overlap_prompt(overlap_report, profiles)` | 重叠分析的 user prompt |
| `COMPARE_SYSTEM` | ETF 对比的 system prompt |
| `build_compare_prompt(compare_result)` | ETF 对比的 user prompt |
| `PORTFOLIO_SYSTEM` | 组合分析的 system prompt |
| `build_portfolio_prompt(portfolio_result, current_poll)` | 组合分析的 user prompt |
| `get_recommend_system(lang)` | 购买建议的 system prompt（含输出结构要求）|
| `build_recommend_prompt(evaluation, poll_data, lang)` | 购买建议的 user prompt |
| `PLANNER_SYSTEM` | 规划器 system prompt（含可用工具列表）|
| `build_planner_prompt(question, watchlist)` | 规划器 user prompt |
| `EXECUTOR_SYSTEM` | 执行器 system prompt（解读单个子任务）|
| `build_executor_prompt(task_description, tool_name, tool_output)` | 执行器 user prompt |
| `SYNTHESIZER_SYSTEM` | 综合器 system prompt（整合所有子任务结论）|
| `build_synthesizer_prompt(question, subtask_results)` | 综合器 user prompt |
| `CRITIC_SYSTEM` | 校验器 system prompt（事实核查员）|
| `build_critic_prompt(question, answer, raw_data)` | 校验器 user prompt |

**`_j(obj)`**
把 Python 对象转成格式化 JSON 字符串（ensure_ascii=False 保证中文不被转义）。

---

### `core/router.py` — 意图路由

**把用户问题分类成 4 种意图，再决定调哪个工具预处理数据。**

4 种意图：
- `overlap` — 问持仓重叠
- `compare` — 问两只 ETF 对比
- `portfolio` — 问整体组合
- `ask` — 其他通用问题

**`_rule_based_intent(question)`**
纯正则匹配（兜底方案）：
- 包含"重叠""重复""雷同"等关键词 → overlap
- 包含"对比""比较""vs"等关键词 → compare
- 包含"组合""portfolio""配置"等关键词 → portfolio
- 其他 → ask

> **性能基准（59 条测试集）**
>
> | 方法 | 正确数 | 准确率 | 主要失败场景 |
> |---|---|---|---|
> | 纯正则关键词匹配 | 44 / 59 | 74.6% | 释义句、英文句、无关键词句 |
> | PyTorch n-gram MLP | 53 / 59 | 89.8% | 语义模糊句（compare vs overlap）|
> | **提升** | **+9** | **+15.3 pp** | — |
>
> 正则的典型失败案例：
> - "你能告诉我哪些基金在持仓上非常相似吗？" → 无"重叠"关键词，误判为 `ask`
> - "find duplicate stocks across my ETFs" → 英文句，正则覆盖不到，误判为 `ask`
> - "我应该选 VWRP 还是 VWRL？" → 无"比较/对比"关键词，误判为 `ask`
>
> PyTorch 分类器通过学习字符级 n-gram 的语义模式，覆盖了正则无法覆盖的释义和跨语言表达。

**`classify_intent(question, known_tickers)`**
两阶段分类：
1. 先尝试 PyTorch 分类器
2. 如果置信度 < 0.60 或模型未加载，用正则兜底
3. 顺带提取问题中提到的 ticker（直接字符串匹配）

**`class Router` + `route(question, current_poll)`**
在分类基础上，**预计算工具结果**（这样 EventAgent 回答时有更丰富的上下文）：
- overlap → 调 `analyze_watchlist_overlap()`，把结果放进 `extra_context`
- compare → 调 `compare_etfs()`，把结果放进 `extra_context`
- portfolio → 调 `analyze_portfolio()`，把结果放进 `extra_context`
- ask → 不预计算，直接让 AI 回答

---

### `core/intent_classifier.py` — PyTorch 推理封装

**加载训练好的模型，对一条文本预测意图。**

**`_extract_ngrams(text, sizes)`**
把文本切成字符级 n-gram：
- `sizes=[1,2,3]` 时，"你好" → ["你","好","你好"]
- 相当于把每个字、每对字、每三个字都当成特征

**`_encode(text, vocab, ngram_sizes)`**
把 n-gram 列表转成整数 ID 列表（用词表映射），未知 n-gram 用 `<UNK>` ID。

**`_build_model(vocab_size, embed_dim, hidden_dim, num_classes)`**
定义模型结构（必须和训练时完全一样）：
```
Embedding(vocab_size, embed_dim)  # 每个 n-gram 变成一个向量
↓ 对所有位置取平均（mean pooling）
Linear(embed_dim, hidden_dim)     # 第一层全连接
ReLU                              # 激活函数
Linear(hidden_dim, num_classes)   # 输出 4 个分类的分数
```

**`class IntentClassifier`**

`_load()` — 启动时自动加载：
1. 检查 `data/intent_model/model.pt` 是否存在
2. 读 `vocab.json`（词表）和 `meta.json`（模型超参数）
3. 重建模型结构，加载权重（`weights_only=True` 是安全选项）
4. 设为 eval 模式（关闭 dropout）

`predict(text)` → `(intent_label, confidence)` — 推理：
1. 提取 n-gram → encode → 转 tensor
2. 前向传播
3. softmax 得到概率分布
4. 取概率最大的类别和概率值

**`get_classifier()`**
单例模式：全局只创建一个分类器实例，第一次调用时创建，后续复用（避免重复加载模型）。

---

### `core/utils.py` — 通用工具

一组在多个模块复用的实用函数：

- `now_iso()` — 当前 UTC 时间的 ISO 字符串
- `load_json(path, default)` — 安全读 JSON
- `save_json(path, data)` — 安全写 JSON（创建目录、UTF-8 编码）
- `load_watchlist()` — 读 watchlist
- `load_settings()` — 读配置（合并默认值）
- `call_poll_once_compat(watchlist)` — 兼容不同版本 poll_once 签名的调用

---

## 七、数据层

---

### `monitors/price_poller.py` — 批量价格轮询

**把 watchlist 里所有 ticker 的价格数据汇总成一个快照。**

**`poll_once(watchlist)`**
1. 对 watchlist 里每个 ticker 调 `price_provider.get_price()`
2. 把所有结果打包成：
```json
{
  "polled_at": "2026-04-16T10:30:00",
  "data": {
    "VUAG": {
      "price": 98.52,
      "prev_close": 98.10,
      "daily_change_pct": 0.43,
      "week_change_pct": -0.8,
      "month_change_pct": 2.1,
      "volume": 123456,
      "ma20": 97.80
    },
    "CSP1": { ... }
  }
}
```

---

### `providers/price_provider.py` — yfinance 价格获取

**从 Yahoo Finance 获取单只资产的价格数据。**

`get_price(ticker)`:
1. 用 `yfinance.Ticker(ticker)` 拉取数据
2. 计算当日涨跌幅（`(price - prev_close) / prev_close * 100`）
3. 计算周、月涨跌幅（与 5 个/21 个交易日前的收盘价对比）
4. 计算 20 日均线（MA20）
5. 返回标准化的价格字典

处理特殊情况：
- 市场休市 → 用最近一个有效收盘价
- Yahoo Finance 有时返回空数据 → 返回 `None`
- 自动解析 ticker 变体（比如 VUAG 在 Yahoo 可能需要加 `.L`）

---

### `providers/static_provider.py` — 静态 ETF 数据

**从 `data/etfs.json` 加载 ETF 的固定信息（不会每天变化的数据）。**

ETF 基本信息包含：
- `name` — 基金全名
- `isin` — 国际证券识别码
- `index` — 追踪的指数（如 MSCI World、S&P 500）
- `ter` — 总费率（每年收取的管理费百分比）
- `distribution` — 分红方式（accumulating 积累型 / distributing 分红型）
- `fund_size_gbp_m` — 基金规模（百万英镑）
- `region` — 地域分类（Global / US / EM 等）
- `em_exposure` — 是否含新兴市场

---

## 八、规则层

---

### `rules/trigger_rules.py` — 触发规则

**纯数学逻辑，不调 AI，判断市场是否有异常。**

**`evaluate_triggers(current_poll, last_snapshot, state, config)`**

检查 4 类事件，每类都生成带 severity 的 event 字典：

**1. 日涨跌幅超阈值**
```
|daily_change_pct| > daily_move_alert_pct → severity: "warning"
|daily_change_pct| > daily_move_strong_pct → severity: "critical"
```

**2. 价格反转**
与上次快照对比：如果今天涨了而昨天跌了（或反过来），且幅度超过 `reversal_pct` → severity: "info"

**3. 数据过期**
`polled_at` 与当前时间差超过 `stale_data_minutes` → severity: "warning"

**4. 心跳**
距离上次 AI 分析超过 `heartbeat_minutes` → severity: "info"，强制触发一次 AI

返回值：
```json
{
  "events": [...],              // 所有触发的事件
  "market_summary": {
    "up_count": 5,
    "down_count": 3,
    "flat_count": 2,
    "max_abs_move_ticker": "NVDA",
    "max_abs_move_pct": 3.2
  },
  "should_run_ai": true,        // 是否需要调 AI
  "inspection_needed": false    // 是否需要深度巡检
}
```

---

### `rules/recommendation_rules.py` — 技术评分

**对每只资产用 5 个技术指标打分，生成买/持/卖信号。**

**评分维度（每项 -2 到 +2 分）：**

| 维度 | 逻辑 |
|------|------|
| `_score_daily` | 日涨跌幅：>2% → +2，>0.5% → +1，<-0.5% → -1，<-2% → -2 |
| `_score_week` | 周涨跌幅：>4% → +2，>1% → +1，<-1% → -1，<-4% → -2 |
| `_score_month` | 月涨跌幅：>8% → +2，>2% → +1，<-2% → -1，<-8% → -2 |
| `_score_vs_ma20` | 相对 20 日均线：偏离 >3% → +2，>1% → +1，<-1% → -1，<-3% → -2 |
| `_score_volume` | 成交量异常（相对均量）：成交量翻倍 → +1，极低量 → -1 |

**总分 → 信号映射：**
```
≥ 5  → strong_buy（强烈买入）
≥ 2  → buy（买入）
≥ -1 → hold（持有观望）
≥ -4 → sell（建议卖出）
< -4 → strong_sell（强烈卖出）
```

**`evaluate_asset(ticker, data, lang)`**
对单只资产算完整评分，返回：
```json
{
  "score": 4,
  "signal": "buy",
  "signal_label": "买入",
  "price_snapshot": { ... }
}
```

**`evaluate_all(poll_data, lang)`**
对 poll_data 里的所有 ticker 批量评分，返回：
```json
{
  "ratings": { "VUAG": {...}, "CSP1": {...}, ... },
  "summary": {
    "strong_buy_count": 2,
    "buy_count": 5,
    ...
  }
}
```

---

## 九、工具层

---

### `tools/overlap.py` — ETF 持仓重叠分析

**估算两只 ETF 之间的持仓重叠程度。**

由于没有实时持仓数据，用**指数家族判断法**（启发式规则）：

```python
_INDEX_FAMILIES = {
    "sp500":  ["CSP1", "IUSA", "VUAG"],   # 都追踪 S&P 500
    "msci_w": ["SWDA", "VWRP", "VWRL", "XDWD"],  # 都追踪 MSCI World
    ...
}
```

同一家族的两只 ETF：
- 完全相同指数 → 97% 重叠
- 同家族不同份额 → 85% 重叠

不同家族之间根据指数覆盖范围估算：
- MSCI World 包含 S&P 500 → 约 60% 重叠
- 全球 vs 新兴市场 → 约 0% 重叠

**`analyze_watchlist_overlap(tickers)`**
对所有 ticker 两两计算重叠率，生成完整报告：
```json
{
  "pairs": [
    {"ticker_a": "VUAG", "ticker_b": "CSP1", "overlap_pct": 0.97, ...}
  ],
  "high_overlap_pairs": [...],  // 重叠 > 70% 的对
  "summary": "watchlist 中有 2 对高重叠 ETF..."
}
```

---

### `tools/compare.py` — ETF 对比

**生成两只 ETF 的横向对比数据。**

`compare_etfs(ticker_a, ticker_b, current_poll)`:
1. 读取两只 ETF 的静态信息（指数、TER、地域、规模等）
2. 从 current_poll 读取当前价格数据
3. 组装对比报告：
   - 哪只费率更低
   - 哪只规模更大
   - 是否一只是分红型一只是积累型
   - 当前涨跌谁更好

---

### `tools/portfolio.py` — 组合分析

**分析整个 watchlist 的整体配置情况。**

`analyze_portfolio(tickers, current_poll)`:
1. 统计地域分布（多少只在 Global / US / EM / 其他）
2. 计算平均 TER
3. 统计积累型 vs 分红型数量
4. 找出有新兴市场敞口的 ETF
5. 计算每个 ETF 与其他所有 ETF 的平均重叠率
6. 给出集中度警告（比如超过一半都是同一地域）

---

### `tools/chart.py` — K 线图生成

**下载历史 OHLCV 数据，生成蜡烛图 PNG。**

`plot_kline(ticker, period, show, save)`:
1. 用 yfinance 下载历史数据（OHLCV：开盘、最高、最低、收盘、成交量）
2. 用 `mplfinance` 库绘制蜡烛图（红绿K线）
3. 如果 `save=True`，保存到 `data/charts/{ticker}_{period}.png`
4. 如果 `show=True`，弹出图形窗口

`get_history_summary(ticker, period)`:
不生成图，只返回历史数据的统计摘要：
- 最高价/最低价/起始价/当前价
- 区间内总涨跌幅
- 成交量统计

---

### `tools/etf_profile.py` — ETF 基本信息查询

`get_etf_profile(ticker)`:
从静态数据中查找 ticker 对应的完整 ETF 信息。
找不到就返回一个只有 ticker 字段的简单字典。

---

### `tools/price_tool.py` — 单只资产价格工具

`get_price_for_ticker(ticker, current_poll)`:
先从已有的 poll 数据里找（避免重复请求），找不到再单独拉。

---

## 十、通知层

---

### `notifiers/console_notifier.py`

`notify_windows(title, message)`:
- 尝试用 `win10toast` 库发 Windows 桌面通知（右下角弹窗）
- 如果没装 win10toast 就打印到终端
- 消息最多 200 字（通知弹窗有字数限制）

---

## 十一、模型层

---

### `models/schemas.py` — 数据结构定义

用 Python 的 `TypedDict` 定义各种数据结构的标准格式，供 IDE 类型检查使用：
- `PriceData` — 单只资产的价格数据字段
- `PollSnapshot` — 一次轮询的完整快照
- `TriggerEvent` — 一个触发事件
- `TriggerResult` — evaluate_triggers 的返回值
- `AssetRating` — evaluate_asset 的返回值

---

## 十二、训练脚本

---

### `tools/generate_training_data.py` — 生成训练数据

手写 389 条带标注的样本（中英文各半）：
- overlap 类：101 条（"VUAG 和 CSP1 有多少重叠？"等）
- compare 类：87 条（"对比一下 SWDA 和 VWRL"等）
- portfolio 类：94 条（"帮我分析整体组合"等）
- ask 类：107 条（"今天市场怎么样"等）

随机打乱，85% 作训练集，15% 作测试集，保存为 JSONL 格式。

---

### `tools/train_intent_classifier.py` — 训练意图分类模型

**从零开始训练一个字符级 n-gram MLP。**

**特征提取**
`extract_ngrams(text, sizes=[1,2,3])`:
把文本切成字符、字符对、字符三元组。
例："你好吗" → ["你","好","吗","你好","好吗","你好吗"]

**词表构建**
`build_vocab(examples)`:
统计所有 n-gram 频率，取最高频的 8000 个建词表。

**模型结构**
```
Embedding(vocab_size=8000, embed_dim=64)
↓ mean pooling（把变长序列压缩成固定维向量）
Linear(64, 128)
ReLU
Dropout(0.3)
Linear(128, 4)   ← 4 个类别的 logit
```

**训练**
- 优化器：Adam，学习率 0.002
- 损失函数：CrossEntropyLoss（多分类标准损失）
- 学习率调度：每 15 epoch 降低 50%
- 训练 40 个 epoch，在 RTX 4060 上约 1.3 秒

**实验结果**

在 59 条独立测试集上，PyTorch 分类器准确率 **89.8%**，相比纯正则基线（74.6%）提升 **+15.3 个百分点**。提升主要来自对释义句和英文句的识别——正则依赖固定关键词，遇到"帮我看看有没有买了差不多东西的ETF"这类自然语言表达时完全失效，而 MLP 通过学习字符 n-gram 的分布模式捕捉到了语义。

**输出文件**
- `data/intent_model/vocab.json` — 词表
- `data/intent_model/model.pt` — 训练好的权重
- `data/intent_model/meta.json` — 超参数和精度记录

---

## 十三、前端（frontend/index.html）

整个前端是一个**不依赖任何框架的纯 HTML/CSS/JS 文件**。

### CSS 部分

**CSS 变量（`:root`）**
```css
--bg: #0f1117;          /* 深色背景 */
--surface: #1c1e26;     /* 面板背景 */
--accent: #2b7a78;      /* 强调色（青绿）*/
--text: #e0e0e0;        /* 主文字颜色 */
```
所有颜色集中定义，便于统一修改。

**四格网格布局**
```css
.grid-2x2 {
    display: grid;
    grid-template-columns: 1fr 1fr;   /* 两列等宽 */
    grid-template-rows: 1fr 1fr;      /* 两行等高 */
}
```

**告警卡片样式**
- `.alert-card` — 基础卡片，带左侧彩色竖条
- `.severity-critical` — 红色，带脉冲动画（`pulse-ring` keyframe）
- `.severity-warning` — 橙色
- `.severity-info` — 蓝色

### JS 部分

**`STRINGS` 字典**
全部 UI 文字的双语版本：
```js
const STRINGS = {
    zh: { askBtn: "发送", inspectBtn: "巡检", ... },
    en: { askBtn: "Send", inspectBtn: "Inspect", ... }
}
```

**`setLang(lang)`**
切换语言：更新所有带 `data-i18n` 属性的元素文字。

**`connectWS()`**
建立 WebSocket 连接：
```js
ws = new WebSocket("ws://localhost:8765/ws");
ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    renderTable(data.snapshot);   // 更新价格表格
    updateMonitorDot(data.monitor);// 更新监控状态指示灯
};
// 断线 3 秒后自动重连
ws.onclose = () => setTimeout(connectWS, 3000);
```

**`renderTable(snapshot)`**
把价格数据渲染成 HTML 表格，每行包含：
- Ticker 名称
- 当前价格
- 日涨跌幅（绿色/红色）
- 信号 badge（强买/买/持/卖）

**`renderAlerts(events)`**
把触发事件渲染成卡片列表：
- 按 severity 排序（critical 在最上面）
- 每张卡片有颜色图标、标题、详细信息
- critical 事件有脉冲动画

**`askAI()`**
用户点击"发送"后：
1. 读取输入框文字
2. 显示 loading 状态
3. POST 到 `/api/ask`
4. 把 AI 文字渲染到输出面板（支持 Markdown 的 `**bold**` 语法）

**`inspectAI()`** / **`recommendAI()`**
类似 askAI，分别调 `/api/inspect` 和 `/api/recommend`。

**`openChart(ticker, period)`**
1. POST 到 `/api/chart`
2. 收到 base64 图片数据
3. 在模态框里显示图片

**`startMonitor()` / `stopMonitor()`**
调 `/api/monitor/start` 或 `/api/monitor/stop`，控制后台监控进程。

---

## 十四、配置文件

### `data/watchlist.json`
你的监控列表，可以随时修改。支持格式：
- ETF：`"VUAG"`, `"CSP1"`（伦交所 ETF，Yahoo Finance 可能加 `.L`）
- 美股：`"AAPL"`, `"NVDA"`
- 加密：`"BTC-USD"`, `"ETH-USD"`
- 指数：`"^GSPC"` (S&P 500), `"^FTSE"` (富时 100)
- 港股：`"0700.HK"` (腾讯)

### `data/etfs.json`
10 只 UK UCITS ETF 的静态资料库，每条包含：
- ISIN（唯一识别码）
- 追踪指数
- TER（总费率）
- 分红方式（积累/分红）
- 基金规模（百万英镑）
- 地域分类
- 是否含新兴市场

### `data/monitor_settings.json`（需自己创建）
覆盖默认配置，不创建就全用默认值。

---

## 十五、系统启动完整链路

```
双击 start_agent.bat
→ 检查 Ollama 是否运行
→ 选择模式（比如 1 = Dashboard + Monitor）
→ 启动 run_monitor_loop.py（后台循环）
→ 启动 web_main.py
   → uvicorn 启动 FastAPI
   → 浏览器自动打开 http://localhost:8765
   → 前端加载 index.html
   → WebSocket 连接建立
   → 每 3 秒收到最新数据推送

同时，后台 run_monitor_loop.py：
→ 每 10 秒轮询一次价格
→ 跑触发规则
→ 有异常 → 调 Ollama LLM 生成摘要
→ 把结果写入 last_snapshot.json
→ FastAPI 的 WebSocket 读取这个文件并推给浏览器
```

---

*报告完毕。所有代码解释基于截至 2026-04-16 的项目版本。*
