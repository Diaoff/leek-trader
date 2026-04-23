# Leek Trader

一个面向**本地单用户**场景的股票模拟交易系统 MVP，当前主线是把“行情 -> 策略 -> 风控 -> 模拟交易 -> 持仓/报表 -> Web 可视化”做成**可运行、可验证、可持续迭代**的闭环。

更新日期：2026-04-23

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

### 数据库说明

默认使用：

```text
postgresql+psycopg://postgres:postgres@localhost:5432/leek_trader
```

可以在启动前覆盖：

```bash
DATABASE_URL='postgresql+psycopg://user:pass@localhost:5432/leek_trader' ./start.sh
```

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
- 仪表盘 / 自选 / 策略 / 交易 / 复盘 / AI 页面联调

### 未完成

- 统一 worker / beat 运行与排障说明仍需补齐
- 任务级重试、监控与观测信息仍偏轻
- 更完整的策略参数编辑与策略创建前端
- 前端测试体系
- 包体积优化（当前 build 仍可能出现大 chunk warning）

### 当前异步状态

已落地：

- 行情刷新任务
- 策略周期运行任务
- 挂单撮合任务
- Celery 基础接入与 Beat 调度入口

尚未落地：

- worker / beat 运行说明与排障路径
- 更完整的任务重试与可观测性

当前不要把仓库描述成“异步体系完全完成”。更准确的表述是：

**行情、策略、撮合三条异步基础链路已经接入，但运行说明与可观测性仍待补强。**

## 测试与验证

后端异步相关回归测试：

```bash
./.venv/bin/python -m pytest backend/tests/test_market_service.py backend/tests/test_market_tasks.py backend/tests/test_trading_tasks.py backend/tests/test_strategies.py -q
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

最近一次验证结果（2026-04-23）：

- 后端全量测试通过，合计 81 个用例
- 前端生产构建通过
- 本轮受影响 Python 文件诊断为 0 个错误
- 仍存在大 chunk warning，后续需要继续做包体积优化

## 文档维护约定

- `plan.md` 用于记录当前阶段、已完成步骤和下一步
- `README.md` 只描述当前已落地能力与明确未完成项
- 每完成一个阶段性步骤，同步更新 `plan.md` 和 `README.md`
