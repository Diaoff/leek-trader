# Leek Trader

一个面向**本地单用户**场景的股票模拟交易系统 MVP，当前主线是把“行情 -> 策略 -> 风控 -> 模拟交易 -> 持仓/报表 -> Web 可视化”做成**可运行、可验证、可持续迭代**的闭环。

更新日期：2026-04-24

## 当前范围

- 后端：FastAPI + SQLAlchemy
- 前端：Vue 3 + Vite + Element Plus + Pinia + ECharts
- 默认运行模式：本地脚本启动 / Docker Compose 辅助
- 行情：东方财富 + 新浪 fallback
- 账户模型：默认单账户，启动时自动初始化
- 策略：数据库驱动的种子策略，可查看、创建、启停、手动运行并记录 `strategy_runs`
- 交易：支持市价单、限价挂单、撤单、手动撮合、风控拒单原因展示

当前**不是**优先主线的内容：

- 完整多用户 / 多租户运营能力
- 完整监控后台
- 更复杂的消息编排体系
- WebSocket 实时行情推送
- 完整策略编辑器 / 脚本上传

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+

### 一键本地启动

在仓库根目录执行：

```bash
./start.sh
```

配套命令：

```bash
./stop.sh
./restart.sh
```

脚本会：

- 检查并使用根目录 `.venv`
- 检查并使用 `frontend/node_modules`
- 启动本地后端与前端
- 输出前端地址、后端地址和日志目录

注意：

- `./start.sh` 只启动本地后端和前端，不会自动启动 Celery worker / beat
- 本地模式日志目录是 `.local/logs`
- 如果要验证异步任务，需要按下面的“异步任务运行说明”额外启动 worker / beat，或者直接使用 Docker 模式

### 数据库说明

默认使用：

```text
postgresql+psycopg://postgres:postgres@localhost:5432/leek_trader
```

可以在启动前覆盖：

```bash
DATABASE_URL='postgresql+psycopg://user:pass@localhost:5432/leek_trader' ./start.sh
```

## 异步任务运行说明

### Docker 模式

如果你希望一次性启动前端、后端、PostgreSQL、Redis、Celery worker 和 Celery beat，直接使用：

```bash
./start-docker.sh
```

停止：

```bash
./stop-docker.sh
```

重启：

```bash
./restart-docker.sh
```

查看异步相关日志：

```bash
docker compose logs -f celery-worker celery-beat
```

如果需要连同后端一起排障：

```bash
docker compose logs -f backend celery-worker celery-beat
```

### 本地模式

本地模式下，先启动 Web 主链路：

```bash
./start.sh
```

本地模式的异步任务前置条件：

- PostgreSQL 需要可用，并且 `DATABASE_URL` 指向有效实例
- Redis 需要先启动；如果本机没有 Redis，可以单独执行 `docker compose up -d redis`

然后在两个额外终端中都先执行下面这组环境变量：

```bash
cd backend
export PYTHONPATH="$(pwd)"
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/leek_trader'
export REDIS_URL='redis://127.0.0.1:6379/0'
```

终端 A 启动 worker：

```bash
../.venv/bin/celery -A app.core.celery_app.celery_app worker --loglevel=info
```

终端 B 启动 beat：

```bash
../.venv/bin/celery -A app.core.celery_app.celery_app beat --loglevel=info
```

本地模式日志定位：

- Web 侧日志：`.local/logs/backend.log`、`.local/logs/frontend.log`
- Celery worker / beat：默认输出到当前终端；如果需要持久化，可以按你的运行环境自行重定向

### 当前异步任务入口

当前 Celery 任务与调度入口集中在：

- `backend/app/tasks/market_tasks.py`
- `backend/app/tasks/strategy_tasks.py`
- `backend/app/tasks/trading_tasks.py`
- `backend/app/core/celery_app.py`

如果需要确认 beat 当前调度了哪些任务，先看：

- `backend/app/core/celery_app.py`

### 当前可靠性基线

当前 Celery 任务已经具备以下统一约定：

- worker 侧启用 `task_track_started`
- worker 侧启用 `task_send_sent_event`
- 任务失败默认自动重试，采用 backoff + jitter，最大重试次数为 3
- 行情刷新、策略周期运行、挂单撮合三个任务都记录 started / succeeded 生命周期日志
- 监控接口可返回三类任务的最近运行统计与统一重试策略摘要
- 任务运行统计会持久化到数据库，摘要接口优先读取持久化结果
- 失败事件会输出 `ASYNC_TASK_ALERT` 结构化告警日志

对于尚未落库的新任务，摘要接口会临时回退到当前 worker 进程内基线数据。

如果需要定位失败原因，优先查看：

- worker / beat 日志输出
- `backend/app/core/celery_app.py`
- `backend/app/tasks/market_tasks.py`
- `backend/app/tasks/strategy_tasks.py`
- `backend/app/tasks/trading_tasks.py`

### 当前人工干预入口

当前已经提供以下手动派发入口：

- `POST /api/v1/monitoring/async-tasks/refresh-market-quotes`
- `POST /api/v1/monitoring/async-tasks/run-strategy-cycle`
- `POST /api/v1/monitoring/async-tasks/match-pending-orders`

当前已经提供以下任务摘要入口：

- `GET /api/v1/monitoring/async-tasks/summary`

## 页面路由

当前前端页面：

- `/`：仪表盘
- `/watchlist`：自选盯盘
- `/strategies`：策略中心
- `/portfolio`：交易与持仓
- `/analysis`：盈亏复盘
- `/ai`：AI 分析

## 主要接口

当前主链路常用接口：

- `GET /api/v1/health`
- `GET /api/v1/accounts`
- `GET /api/v1/quotes`
- `GET /api/v1/orders`
- `POST /api/v1/orders`
- `POST /api/v1/orders/{id}/cancel`
- `POST /api/v1/orders/match-pending`
- `GET /api/v1/positions`
- `GET /api/v1/portfolio/summary`
- `GET /api/v1/reporting/summary`
- `GET /api/v1/reporting/equity-curve`
- `GET /api/v1/reporting/monthly-stats`
- `GET /api/v1/strategies`
- `POST /api/v1/strategies`
- `PATCH /api/v1/strategies/{id}`
- `POST /api/v1/strategies/{id}/run`
- `GET /api/v1/monitoring/async-tasks/summary`
- `POST /api/v1/monitoring/async-tasks/refresh-market-quotes`
- `POST /api/v1/monitoring/async-tasks/run-strategy-cycle`
- `POST /api/v1/monitoring/async-tasks/match-pending-orders`
- `GET /api/v1/watchlists`
- `GET /api/v1/watchlist-groups`

API 文档：

- `http://localhost:8000/docs`

## 当前状态

### 已完成

- 默认账户初始化
- 行情 provider fallback
- 行情缓存与陈旧缓存回退
- 市价 / 限价下单
- 撤单与手动撮合挂单
- 持仓、账户、资金流水更新
- 基础收益统计与资产曲线
- 策略种子数据、策略创建/更新/运行接口
- `strategy_runs` 持久化
- 拒单原因持久化与展示
- 行情刷新 Celery 任务
- 策略周期运行 Celery 任务
- 挂单撮合 Celery 任务
- Celery Beat 已注册行情刷新、策略周期运行、挂单撮合三个定时入口
- 异步任务摘要接口与人工触发入口
- 异步任务持久化统计与结构化告警日志
- 仪表盘 / 自选 / 策略 / 交易 / 复盘 / AI 页面联调

### 未完成

- 外部告警投递与 broker 异常演练仍未补齐
- 更完整的策略参数编辑与策略创建前端
- 前端测试体系
- 包体积优化（当前 build 仍可能出现大 chunk warning）

### 当前异步状态

已落地：

- 行情刷新任务
- 策略周期运行任务
- 挂单撮合任务
- Celery 基础接入与 Beat 调度入口
- 异步任务摘要查询
- 手动派发关键异步任务入口
- 持久化任务统计
- 结构化失败告警日志

尚未落地：

- 外部告警投递与 broker 不可用场景验证

当前不要把仓库描述成“异步体系完全完成”。更准确的表述是：

**行情、策略、撮合三条异步基础链路已经接入，当前主要缺口已收敛到外部告警投递与 broker 不可用场景验证。**

## 测试与验证

后端异步相关回归测试：

```bash
./.venv/bin/python -m pytest backend/tests/test_monitoring.py backend/tests/test_market_tasks.py backend/tests/test_trading_tasks.py backend/tests/test_strategy_tasks.py -q
```

完整后端测试：

```bash
./.venv/bin/python -m pytest backend/tests -q
```

前端构建校验：

```bash
cd frontend
npm run build
```

最近一次验证结果（2026-04-24）：

- Step 8 已补齐异步任务持久化统计与结构化失败告警日志
- `./.venv/bin/python -m pytest backend/tests -q` 通过，合计 89 个用例
- `cd frontend && npm run build` 通过
- 仍存在大 chunk warning，后续需要继续做包体积优化

## 文档维护约定

- `plan.md` 用于记录当前阶段、已完成步骤和下一步
- `README.md` 只描述当前已落地能力与明确未完成项
- 每完成一个阶段性步骤，同步更新 `plan.md` 和 `README.md`
