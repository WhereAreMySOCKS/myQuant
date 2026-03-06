# myQuant — A股量化监控系统

> 面向量化交易初学者的 A 股投资监控工具：个股 / ETF / 场外基金实时监控 + MA250 乖离率信号 + 邮件报警 + 回测引擎
>
> 基于 FastAPI + SQLite，支持 Docker 一键部署，7×24 后台运行

---

## 📖 目录

- [功能特性](#功能特性)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [API 文档](#api-文档)
- [项目结构说明](#项目结构说明)
- [技术栈](#技术栈)
- [学习文档导航](#学习文档导航)
- [运行测试](#运行测试)
- [开发路线图](#开发路线图)

---

## 功能特性

- 📈 **多类型标的支持**：A 股个股、场内 ETF、场外基金，自动识别代码类型和名称
- ⏰ **智能轮询**：交易时间自动拉取实时行情，非交易时间自动休眠节省资源
- 🎯 **均线信号**：个股/ETF 基于 MA250（年线）乖离率判断超买/超卖信号
- 📩 **邮件报警**：信号触发后通过 SMTP 发送邮件，同标的同方向每天仅报警一次（防刷屏）
- 🔁 **历史回测**：内置 MA250 乖离率策略回测引擎，支持自定义参数和日期区间
- 🛠 **RESTful API**：完整的增删改查接口，配合 Swagger UI 交互式调试
- 🗓 **节假日感知**：集成中国法定节假日和调休日历，交易时间判断更准确
- 🔄 **主备数据源**：腾讯财经为主、新浪财经为备，自动切换确保数据可用性

---

## 系统架构

```
外部数据源
  腾讯财经 (实时/历史K线)
  新浪财经 (历史K线备用)
  天天基金 (场外估值/历史净值)
       │
       ▼
┌──────────────────────────────────────────────────────┐
│                  FastAPI 应用层                       │
│                                                      │
│  ┌─────────────┐   ┌──────────────────────────────┐  │
│  │   REST API  │   │    后台监控循环 (asyncio)      │  │
│  │             │   │                              │  │
│  │ /targets    │   │  1. 拉取所有关注标的实时行情   │  │
│  │ /quote      │   │  2. 计算 MA250 乖离率          │  │
│  │ /backtest   │   │  3. 判断买卖信号               │  │
│  └─────────────┘   │  4. 触发邮件报警（去重）        │  │
│         │          └──────────────────────────────┘  │
│         │                      │                     │
│  ┌──────▼──────────────────────▼────────────────────┐│
│  │            服务层 (Services)                      ││
│  │  data_fetcher  analyzer  backtester  notifier     ││
│  └───────────────────────┬───────────────────────────┘│
└──────────────────────────┼───────────────────────────┘
                           ▼
                    SQLite 数据库
                 (targets + security_info)
```

**数据流说明：**
1. 用户通过 API 添加关注标的（如 `600519` 贵州茅台）
2. 系统在数据库中记录标的及其买卖阈值
3. 后台监控循环每隔 N 秒拉取所有标的的实时行情
4. `analyzer` 服务计算技术指标（MA250 及乖离率）
5. 乖离率超出阈值时，`notifier` 发送邮件报警
6. 用户也可以通过 `/backtest` 接口对历史数据进行策略回测

---

## 快速开始

### 方式一：Docker 部署（推荐）

**前置条件**：已安装 Docker 和 Docker Compose

```bash
# 1. 克隆仓库
git clone https://github.com/WhereAreMySOCKS/myQuant.git
cd myQuant

# 2. 复制配置模板，填入真实邮箱信息
cp .env.example .env
# 用编辑器打开 .env，修改 SMTP 配置（详见下方配置说明）
nano .env

# 3. 启动服务
docker-compose up -d --build

# 4. 确认服务运行正常
curl http://localhost:8000/
# 应返回：{"status":"ok","message":"myQuant is running"}
```

**查看运行日志：**

```bash
docker logs -f investment_guard --tail 50
```

### 方式二：本地开发运行

**前置条件**：Python 3.11+

```bash
# 1. 克隆并安装依赖
git clone https://github.com/WhereAreMySOCKS/myQuant.git
cd myQuant
pip install -r requirements.txt

# 2. 复制并配置环境变量
cp .env.example .env
# 编辑 .env 填入你的配置

# 3. 初始化数据库
mkdir -p data
python -c "from app.core.database import init_db; init_db()"

# 4. 启动开发服务器（带热重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. 打开 Swagger 交互式 API 文档
# 浏览器访问：http://localhost:8000/docs
```

### 添加第一个关注标的

```bash
# 添加贵州茅台（个股），乖离率 -8% 买入，+15% 卖出
curl -X POST http://localhost:8000/targets/ \
  -H "Content-Type: application/json" \
  -d '{"code":"600519","buy_bias_rate":-0.08,"sell_bias_rate":0.15}'

# 添加沪深300 ETF
curl -X POST http://localhost:8000/targets/ \
  -H "Content-Type: application/json" \
  -d '{"code":"510300","buy_bias_rate":-0.05,"sell_bias_rate":0.10}'

# 查询行情和技术指标
curl http://localhost:8000/quote/600519
```

---

## 配置说明

复制 `.env.example` 为 `.env` 并填入真实值。**不要将 `.env` 提交到 Git！**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `APP_ENV` | `dev` | 运行环境：`dev`（开发）/ `test`（测试）/ `prod`（生产） |
| `APP_NAME` | `myQuant` | 应用名称，用于日志标识 |
| `APP_VERSION` | `3.0.0` | 应用版本号 |
| `LOG_LEVEL` | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FORMAT` | `text` | 日志格式：`text`（开发可读）/ `json`（生产机器解析） |
| `SMTP_SERVER` | `smtp.qq.com` | SMTP 服务器地址 |
| `SMTP_PORT` | `465` | SMTP 端口（465 为 SSL，587 为 TLS） |
| `SENDER_EMAIL` | — | 发件人邮箱（如 `your_qq@qq.com`） |
| `EMAIL_PASSWORD` | — | SMTP 授权码（**不是邮箱登录密码！**） |
| `RECEIVER_EMAIL` | — | 接收报警邮件的邮箱 |
| `POLL_INTERVAL_SECONDS` | `30` | 监控轮询间隔（秒）。标的少可设 5~10，多则 15~30 |
| `MONITOR_CONCURRENCY` | `5` | 并发处理标的数，防止请求数据源过于频繁 |
| `HISTORY_LOOKBACK_MONTHS` | `18` | 历史 K 线回溯月数，需覆盖至少 250 个交易日（≈12~14 个月） |
| `DATABASE_URL` | `sqlite:///./data/investment_guard.db` | 数据库连接字符串 |

**如何获取 QQ 邮箱 SMTP 授权码：**
> QQ 邮箱 → 设置 → 账户 → 找到「POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务」→ 开启 SMTP 服务 → 按提示验证手机号 → 生成授权码

---

## API 文档

- **Base URL**：`http://localhost:8000`
- **交互式文档**：`http://localhost:8000/docs`（Swagger UI）
- **数据格式**：JSON，UTF-8 编码

### GET / — 系统状态

```bash
curl http://localhost:8000/
```

**响应示例：**
```json
{
  "status": "ok",
  "message": "myQuant is running"
}
```

---

### POST /targets/ — 新增关注标的

系统会自动识别证券代码的名称和类型（个股/ETF/场外基金），只需传入代码和阈值。

**个股示例（乖离率策略）：**
```bash
curl -X POST http://localhost:8000/targets/ \
  -H "Content-Type: application/json" \
  -d '{
    "code": "600519",
    "buy_bias_rate": -0.08,
    "sell_bias_rate": 0.15
  }'
```

**ETF 示例：**
```bash
curl -X POST http://localhost:8000/targets/ \
  -H "Content-Type: application/json" \
  -d '{
    "code": "510300",
    "buy_bias_rate": -0.05,
    "sell_bias_rate": 0.10
  }'
```

**场外基金示例（涨跌幅策略）：**
```bash
curl -X POST http://localhost:8000/targets/ \
  -H "Content-Type: application/json" \
  -d '{
    "code": "012708",
    "buy_growth_rate": -2.0,
    "sell_growth_rate": 3.0
  }'
```

**响应示例：**
```json
{
  "id": 1,
  "code": "600519",
  "name": "贵州茅台",
  "type": "stock",
  "buy_bias_rate": -0.08,
  "sell_bias_rate": 0.15,
  "buy_growth_rate": null,
  "sell_growth_rate": null,
  "created_at": "2024-01-15T10:30:00"
}
```

---

### GET /targets/ — 获取所有关注标的

```bash
curl http://localhost:8000/targets/
```

**响应示例：**
```json
[
  {
    "id": 1,
    "code": "600519",
    "name": "贵州茅台",
    "type": "stock",
    "buy_bias_rate": -0.08,
    "sell_bias_rate": 0.15,
    "buy_growth_rate": null,
    "sell_growth_rate": null,
    "created_at": "2024-01-15T10:30:00"
  }
]
```

---

### GET /targets/{code} — 查询单个标的详情

```bash
curl http://localhost:8000/targets/600519
```

---

### PUT /targets/{code} — 更新标的阈值

```bash
curl -X PUT http://localhost:8000/targets/600519 \
  -H "Content-Type: application/json" \
  -d '{
    "buy_bias_rate": -0.10,
    "sell_bias_rate": 0.20
  }'
```

---

### DELETE /targets/{code} — 删除关注标的

```bash
curl -X DELETE http://localhost:8000/targets/600519
```

**响应示例：**
```json
{"message": "已删除 600519"}
```

---

### GET /quote/{code} — 查询实时行情

查询前需先通过 `POST /targets/` 添加该标的。

```bash
curl http://localhost:8000/quote/600519
```

**交易时间响应示例（含技术指标）：**
```json
{
  "code": "600519",
  "name": "贵州茅台",
  "type": "stock",
  "status": "realtime",
  "realtime": {
    "price": 1680.5,
    "change": -12.3,
    "change_pct": -0.73,
    "volume": 123456,
    "amount": 207654321.0
  },
  "indicators": {
    "price": 1680.5,
    "ma5": 1692.3,
    "ma20": 1710.8,
    "ma120": 1748.2,
    "ma250": 1820.0,
    "bias_rate": -0.0767,
    "bias_percent": "-7.67%"
  }
}
```

**非交易时间响应示例：**
```json
{
  "code": "600519",
  "name": "贵州茅台",
  "type": "stock",
  "status": "closed",
  "close_price": 1680.5,
  "close_date": "2024-01-15"
}
```

---

### POST /backtest/single — 单标历史回测

对指定标的在历史数据上运行 MA250 乖离率策略回测。

```bash
curl -X POST http://localhost:8000/backtest/single \
  -H "Content-Type: application/json" \
  -d '{
    "code": "600519",
    "buy_bias_rate": -0.08,
    "sell_bias_rate": 0.15,
    "initial_capital": 100000,
    "start_date": "2020-01-01",
    "end_date": "2024-01-01"
  }'
```

**响应示例：**
```json
{
  "code": "600519",
  "name": "贵州茅台",
  "type": "stock",
  "period": {
    "start": "2020-01-02",
    "end": "2023-12-29"
  },
  "params": {
    "buy_bias_rate": -0.08,
    "sell_bias_rate": 0.15,
    "initial_capital": 100000.0
  },
  "summary": {
    "total_return": 0.3256,
    "total_return_pct": "32.56%",
    "annualized_return": 0.0741,
    "annualized_return_pct": "7.41%",
    "max_drawdown": -0.1823,
    "max_drawdown_pct": "-18.23%",
    "trade_count": 8,
    "win_rate": 0.75,
    "win_rate_pct": "75.00%",
    "final_capital": 132560.0,
    "benchmark_return": 0.2100,
    "benchmark_return_pct": "21.00%",
    "excess_return": 0.1156,
    "excess_return_pct": "11.56%"
  },
  "trades": [
    {
      "date": "2020-03-23",
      "action": "BUY",
      "price": 1012.3,
      "shares": 900,
      "amount": 91107.0,
      "bias_rate": -0.0912,
      "capital_after": 8893.0
    }
  ]
}
```

---

## 项目结构说明

```
myQuant/
├── .env.example              # 配置模板（安全提交）
├── .env                      # 实际配置（含密码，不提交到 Git）
├── .gitignore
├── Dockerfile                # Docker 镜像构建（Python 3.11-slim）
├── docker-compose.yml        # Docker Compose 编排配置
├── requirements.txt          # Python 依赖清单
├── alembic.ini               # 数据库迁移工具配置
├── alembic/                  # 数据库迁移脚本目录
├── tests/                    # 单元测试
│   ├── conftest.py           # pytest fixtures（共享测试依赖）
│   ├── test_analyzer.py      # 技术指标计算测试
│   ├── test_backtest.py      # 回测引擎测试
│   ├── test_cache.py         # 缓存模块测试
│   ├── test_data_fetcher.py  # 数据抓取测试（含 Mock）
│   ├── test_routes.py        # API 路由集成测试
│   └── test_utils.py         # 工具函数测试
└── app/
    ├── main.py               # FastAPI 入口：lifespan 生命周期 + 路由注册 + 异常处理
    ├── core/
    │   ├── config.py         # Settings（pydantic-settings），读取 .env 环境变量
    │   ├── database.py       # SQLAlchemy engine + SessionLocal + init_db
    │   ├── deps.py           # get_db 依赖注入（FastAPI Depends）
    │   ├── exceptions.py     # 自定义异常类层级（NotFoundException 等）
    │   └── logging.py        # 结构化日志（支持 text/json 两种格式）
    ├── models/
    │   └── target.py         # ORM 模型：Target（标的表）+ SecurityInfo（代码缓存表）
    ├── schemas/
    │   ├── target.py         # Pydantic 模型：TargetCreate / TargetUpdate / TargetResponse
    │   └── backtest.py       # Pydantic 模型：BacktestRequest / BacktestResponse
    ├── routes/
    │   ├── target.py         # 关注标的 CRUD（含批量添加和批量删除）
    │   ├── quote.py          # 行情查询（智能区分交易时间/非交易时间）
    │   └── backtest.py       # 回测接口入口（参数校验 + 调用回测引擎）
    ├── services/
    │   ├── analyzer.py       # 技术指标：MA5/20/120/250 + 乖离率 + 信号判断
    │   ├── backtester.py     # 回测引擎：MA250 乖离率策略，全仓买卖，计算完整回测指标
    │   ├── cache.py          # HistoryCache（K线缓存）+ AlertStateManager（报警去重）
    │   ├── code_resolver.py  # 证券代码解析：自动识别 stock/etf/otc 及名称
    │   ├── data_fetcher.py   # 数据抓取：腾讯财经（主）+ 新浪财经（备）+ 天天基金
    │   ├── monitor.py        # 后台监控主循环：asyncio + 并发扫描 + 邮件报警
    │   └── notifier.py       # 邮件通知：SMTP SSL 发送，含重试和日志脱敏
    └── utils/
        ├── convert.py        # safe_float：安全的字符串转浮点数工具
        ├── http_client.py    # HTTP 客户端：UA 伪装 + 请求重试策略
        └── time_utils.py     # 交易时间判断（集成 chinese_calendar 节假日库）
```

---

## 技术栈

| 类别 | 技术/库 | 用途 |
|------|---------|------|
| Web 框架 | [FastAPI](https://fastapi.tiangolo.com/) | REST API + 自动生成 Swagger 文档 |
| ASGI 服务器 | [Uvicorn](https://www.uvicorn.org/) | 高性能异步 HTTP 服务器 |
| 数据库 ORM | [SQLAlchemy](https://www.sqlalchemy.org/) | 数据库模型定义和查询 |
| 数据库 | SQLite | 轻量嵌入式数据库，无需独立部署 |
| 数据迁移 | [Alembic](https://alembic.sqlalchemy.org/) | 数据库 Schema 版本管理 |
| 配置管理 | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | 从 .env 文件读取配置，类型安全 |
| 数据处理 | [pandas](https://pandas.pydata.org/) | K 线数据处理和均线计算 |
| 节假日 | [chinese_calendar](https://github.com/LKI/chinese-calendar) | A 股交易日判断（含法定节假日调休） |
| HTTP 客户端 | [requests](https://requests.readthedocs.io/) | 抓取外部行情数据 |
| 测试框架 | [pytest](https://pytest.org/) + [pytest-asyncio](https://pytest-asyncio.readthedocs.io/) | 单元测试和异步测试 |
| HTTP 测试 | [httpx](https://www.python-httpx.org/) | FastAPI 接口测试客户端 |
| 容器化 | Docker + Docker Compose | 一键部署和环境隔离 |

---

## 学习文档导航

> 如果你是量化交易初学者，建议按照以下顺序阅读学习文档。
> 所有文档从零讲起，配合本项目代码，帮助你建立完整的量化交易知识体系。

| 序号 | 文档 | 核心内容 |
|------|------|---------|
| 01 | [量化交易入门](docs/01-quant-basics.md) | 什么是量化交易、A 股基础知识、策略分类 |
| 02 | [技术指标详解](docs/02-technical-indicators.md) | K 线、移动平均线、乖离率的计算原理 |
| 03 | [MA250 乖离率策略](docs/03-bias-strategy.md) | 本项目核心策略的完整讲解与代码解析 |
| 04 | [回测入门与实践](docs/04-backtesting-guide.md) | 如何评估策略、解读回测结果 |
| 05 | [数据源与行情获取](docs/05-data-sources.md) | 数据抓取机制、主备切换、复权说明 |
| 06 | [风险管理基础](docs/06-risk-management.md) | 仓位管理、止损止盈、最大回撤控制 |

---

## 运行测试

```bash
# 安装开发依赖（如未安装）
pip install -r requirements.txt

# 运行全部测试
pytest tests/ -v

# 运行特定模块的测试
pytest tests/test_backtest.py -v
pytest tests/test_analyzer.py -v

# 带覆盖率报告
pytest tests/ --tb=short -q
```

测试使用 `unittest.mock` 模拟外部数据源，不依赖网络连接。

---

## 开发路线图

### 已实现 ✅
- [x] 个股/ETF/场外基金行情监控
- [x] MA250 乖离率买卖信号
- [x] 邮件报警（防刷屏去重）
- [x] RESTful CRUD API
- [x] 历史回测引擎（MA250 乖离率策略）
- [x] Docker 容器化部署
- [x] 结构化日志（text/json）

### 计划中 🚀
- [ ] 支持更多技术指标（RSI、MACD、布林带）
- [ ] 场外基金回测支持
- [ ] 多策略回测对比（参数扫描）
- [ ] Web 前端界面（行情图表 + 回测结果可视化）
- [ ] 微信/钉钉通知渠道
- [ ] 自动止损功能（下单接口对接）
- [ ] 多账户支持

---

## 常见问题

**Q：轮询间隔设多少合适？**
> 标的数量少（< 10 个）可设 5~10 秒；标的多（> 20 个）建议 15~30 秒，避免被数据源封 IP。

**Q：HISTORY_LOOKBACK_MONTHS 要设多少？**
> 计算 MA250 至少需要 250 个交易日的历史数据，约等于 14 个月。建议设 18 以留有余量。

**Q：场外基金回测为什么不支持？**
> 场外基金按净值申购/赎回，不像股票可以精确按价格买入整手，回测逻辑差异较大，计划后续版本支持。

**Q：非交易时间查询返回什么？**
> 个股/ETF 返回最近交易日的收盘价；场外基金返回最近一次确认净值。

---

*如有问题或建议，欢迎提 Issue 或 PR。*
