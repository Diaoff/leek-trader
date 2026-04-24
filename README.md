# Leek Trader

一个面向**本地单用户**场景的股票模拟交易系统 MVP，当前主线是把“行情 -> 策略 -> 风控 -> 模拟交易 -> 持仓/报表 -> Web 可视化”做成**可运行、可验证、可持续迭代**的闭环。

更新日期：2026-04-24

## 当前范围

- 后端：FastAPI + SQLAlchemy
- 前端：Vue 3 + Vite + Element Plus + Pinia + ECharts
- 默认运行模式：本地脚本启动 / Docker Compose 辅助
- 行情：东方财富 + 新浪 fallback
- 账户模型：默认单账户，启动时自动初始化
- 策略：数据库驱动的种子策略，支持页内创建、编辑、启停、手动运行，并可在 `signal_only` / `auto_trade` 两种执行模式间切换
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
./start.sh --with-async
./start.sh --with-async --skip-frontend
bash ./async-health.sh
```

脚本会：

- 检查并使用根目录 `.venv`
- 检查并使用 `frontend/node_modules`
- 启动本地后端与前端
- 输出前端地址、后端地址和日志目录

注意：

- `./start.sh` 默认只启动本地后端和前端
- `./start.sh --with-async` 会额外启动本地 Celery worker / beat
- `./start.sh --with-async --skip-frontend` 适合只验证 backend + Celery 的本地 smoke check
- 本地模式日志目录是 `.local/logs`
- 启动本地异步进程后，可直接执行 `bash ./async-health.sh` 做基础健康自检
- 如果需要持续守护，可执行 `bash ./async-health.sh --watch --interval 15 --max-failures 3`；首次连续失败会输出 `warning`，达到阈值后会升级为 `critical`
- `./start.sh --with-async` 在启动完成前会额外校验一次 `celery inspect ping`；如果 worker / beat 提前退出，会直接带最近日志失败返回
- 如果不想由脚本托管异步进程，仍可按下面的“异步任务运行说明”手动启动 worker / beat，或者直接使用 Docker 模式

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

如果希望本地脚本一并拉起 Celery worker 和 beat，可直接执行：

```bash
./start.sh --with-async
```

如果当前环境不适合启动新的 Vite 端口，但你仍想验证 backend + Celery，可以执行：

```bash
./start.sh --with-async --skip-frontend
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

如果是通过 `./start.sh --with-async` 启动的本地异步进程，可使用：

```bash
bash ./async-health.sh
```

这个自检会确认：

- 后端健康接口可达
- 异步任务摘要接口可达
- 本地 worker / beat PID 仍然存活
- `celery inspect ping` 至少能收到一个 worker 响应

如果自检失败，脚本会额外输出：

- 推荐恢复命令：`./stop.sh`、`./start.sh --with-async`、`bash ./async-health.sh`
- Redis 未就绪时的补救提示
- worker / beat 最近日志尾部路径与内容

如果你希望持续观察而不是只做一次性检查，可执行：

```bash
bash ./async-health.sh --watch --interval 15 --max-failures 3
```

watch 模式额外提供：

- 按固定间隔重复执行同一套健康检查
- 首次连续失败输出 `ASYNC_LOCAL_GUARD_ALERT`，等级为 `warning`
- 达到 `--max-failures` 阈值后升级为 `critical`，并以非零状态退出
- 默认把守护告警追加到 `.local/logs/async-guard.log`
- 通过 `--max-checks` 可做有界演练，通过 `--log-file` 可输出到自定义日志文件

本地模式日志定位：

- Web 侧日志：`.local/logs/backend.log`、`.local/logs/frontend.log`
- 通过脚本托管时，Celery worker / beat 日志位于 `.local/logs/celery-worker.log`、`.local/logs/celery-beat.log`
- 本地 watch 守护告警日志位于 `.local/logs/async-guard.log`
- 手动启动时，Celery worker / beat 默认输出到当前终端；如果需要持久化，可以按你的运行环境自行重定向

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
- 配置 `ASYNC_ALERT_WEBHOOK_URL` 后，失败事件会额外向外部 Webhook 发送 JSON 告警

Webhook 告警当前 payload 至少包含：

- `task_name`
- `task_id`
- `error`
- `timestamp`

对于尚未落库的新任务，摘要接口会临时回退到当前 worker 进程内基线数据。

可选告警配置示例：

```bash
export ASYNC_ALERT_WEBHOOK_URL='https://alerts.example.test/webhook'
export ASYNC_ALERT_TIMEOUT_SECONDS='3.0'
```

当前告警等级边界：

- Level 1：始终输出 `ASYNC_TASK_ALERT` 结构化日志，适合本地排障和日志采集
- Level 2：执行 `bash ./async-health.sh --watch ...` 后会输出 `ASYNC_LOCAL_GUARD_ALERT`，按连续失败次数在本地升级为 `warning` / `critical`
- Level 3：配置 `ASYNC_ALERT_WEBHOOK_URL` 后，任务失败事件会额外推送 Webhook，适合轻量通知或接入自建网关
- 当前未覆盖：告警去重、自动恢复、值班路由、生产级 supervisor / paging

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

如果 Redis / Celery broker 不可用，上述人工触发入口会显式返回 `503`，提示先检查消息队列后再重试。

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
- `execution_mode` 执行模式与 `position_pct` 仓位比例配置
- `signal_only` / `auto_trade` 双模式策略执行
- 策略自动交易复用现有下单、风控、持仓、报表链路
- 策略页 Drawer 创建 / 编辑与最近一次执行摘要展示
- `strategy_runs` 持久化
- 拒单原因持久化与展示
- 行情刷新 Celery 任务
- 策略周期运行 Celery 任务
- 挂单撮合 Celery 任务
- Celery Beat 已注册行情刷新、策略周期运行、挂单撮合三个定时入口
- 异步任务摘要接口与人工触发入口
- 异步任务持久化统计与结构化告警日志
- 异步失败 Webhook 告警投递
- broker 不可用时的 503 降级提示
- 仪表盘 / 自选 / 策略 / 交易 / 复盘 / AI 页面联调

### 未完成

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
- Webhook 外部告警投递
- broker 不可用时的显式 503 降级提示
- 本地异步异常退出恢复提示
- 本地脚本启动后的 worker ping 验证
- 本地 backend + Celery 运行态 smoke check
- 本地 watch 守护与 `warning` / `critical` 告警升级

尚未落地：

- 自动恢复 / 自动拉起方案
- 面向真实生产部署的 worker / beat 守护、告警去重与 paging 路径

当前不要把仓库描述成“异步体系完全完成”。更准确的表述是：

**行情、策略、撮合三条异步基础链路已经接入，Webhook 告警投递、broker 不可用降级提示、本地一键异步启动、基础健康自检、异常退出恢复提示、启动后 worker ping 验证、backend + Celery 运行态 smoke check、包含前端联动的本地全链路演练，以及本地 watch 守护与 `warning` / `critical` 告警升级都已补齐；当前主要缺口转向自动恢复 / supervisor 的边界收敛。**

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

- 已完成 V1 交易闭环打通：
  自选 / 行情 -> 策略创建编辑 -> signal_only / auto_trade -> 下单成交 -> 持仓更新 -> 盈亏报表
- `./.venv/bin/python -m pytest -q` 通过：`92 passed in 17.46s`
- `./.venv/bin/python -m pytest backend/tests/test_watchlists.py backend/tests/test_quotes.py backend/tests/test_strategies.py backend/tests/test_trading.py backend/tests/test_portfolio.py backend/tests/test_reporting.py backend/tests/test_monitoring.py backend/tests/test_strategy_tasks.py -q` 通过：`47 passed in 8.65s`
- `npm run build` 通过，仅保留既有的大 chunk warning
- `frontend` 项目级 TypeScript 诊断为 `0 error / 0 warning`

- Step 14 已补齐本地 watch 守护与守护告警升级
- `BACKEND_PORT=6553 bash ./async-health.sh --watch --interval 1 --max-failures 2 --max-checks 2 --log-file /tmp/leek-trader-step14-guard.log` 已验证：
  首次连续失败输出 `ASYNC_LOCAL_GUARD_ALERT severity=warning`
  第二次连续失败升级为 `severity=critical`
  命令以非零状态退出
- Step 13 已完成包含前端联动的本地全链路演练
- 提权环境下已完成同一终端内的真实链路：
  `./stop.sh -> BACKEND_PORT=8003 FRONTEND_PORT=5175 ./start.sh --with-async -> curl http://127.0.0.1:8003/api/v1/health -> curl -I http://127.0.0.1:5175/ -> BACKEND_PORT=8003 bash ./async-health.sh -> ./stop.sh`
- 该轮验证已确认：
  前端首页 `HTTP/1.1 200 OK`
  后端健康接口返回 `status=ok`
  异步摘要接口可达
  `celery inspect ping` 成功
- Step 12 已完成 backend + Celery 运行态 smoke check
- 同一终端内已完成 `./stop.sh -> BACKEND_PORT=8002 ./start.sh --with-async --skip-frontend -> BACKEND_PORT=8002 bash ./async-health.sh -> ./stop.sh`
- `BACKEND_PORT=8002 bash ./async-health.sh` 返回：
  `Backend health endpoint reachable`
  `Async summary endpoint reachable`
  `Celery inspect ping succeeded`
- Step 11 已补齐本地异步异常退出恢复提示与启动后 worker ping 验证
- `bash ./async-health.sh` 在无运行中服务时会返回失败并输出恢复提示
- Step 10 已补齐本地异步一键启动与基础健康自检脚本
- `bash -n start.sh stop.sh restart.sh async-health.sh` 通过
- Step 9 已补齐异步失败 Webhook 告警投递与 broker 不可用场景降级提示
- `./.venv/bin/python -m pytest backend/tests/test_monitoring.py -q` 通过，8 个用例
- `./.venv/bin/python -m pytest backend/tests -q` 通过，合计 92 个用例
- `cd frontend && npm run build` 通过
- 仍存在大 chunk warning，后续需要继续做包体积优化

## 文档维护约定

- `plan.md` 用于记录当前阶段、已完成步骤和下一步
- `README.md` 只描述当前已落地能力与明确未完成项
- 每完成一个阶段性步骤，同步更新 `plan.md` 和 `README.md`
