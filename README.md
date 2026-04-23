# Leek Trader

一个以“本地单用户跑通股票模拟交易主链路”为目标的 MVP。

当前版本优先保证这条流程可用：

1. 本地启动前后端
2. 查看行情快照
3. 提交市价单或限价挂单
4. 查看订单、撤单或手动撮合
5. 查看持仓、资产与收益曲线变化

## 当前范围

- 后端：FastAPI + SQLAlchemy
- 前端：Vue 3 + Vite + Element Plus
- 默认运行模式：本地启动脚本 + SQLite 零依赖演示
- 行情：新浪主源，东方财富与 Akshare 作为 fallback
- 账户模型：默认单账户，启动时自动初始化

本轮不把以下能力当成阻塞项：

- 完整登录流程
- 多用户/多租户运营能力
- 完整 Celery 自动任务体系
- 完整监控后台
- 策略 CRUD、回测与脚本上传

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+

### 一键本地启动

在仓库根目录执行：

```bash
./start.sh
```

脚本会：

- 检查并使用根目录 `.venv`
- 检查并使用 `frontend/node_modules`
- 默认把后端数据库指向仓库内的 SQLite 文件
- 输出真实前端地址、后端地址和日志目录

配套命令：

```bash
./stop.sh
./restart.sh
```

### 默认数据库模式

如果不额外传入环境变量，`start.sh` 默认使用：

```text
postgresql+psycopg://postgres:postgres@localhost:5432/leek_trader
```

如果你想用自己的数据库连接串，可以在启动前覆盖：

```bash
DATABASE_URL='postgresql+psycopg://user:pass@localhost:5432/leek_trader' ./start.sh
```

## 页面与接口

当前前端主页面：

- `/`：仪表盘
- `/market`：行情中心
- `/strategies`：策略中心（只读）
- `/portfolio`：交易与持仓

当前主链路接口：

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

API 文档：

- `http://localhost:8000/docs`

## 测试

后端测试：

```bash
./.venv/bin/python -m pytest backend/tests -q
```

前端构建校验：

```bash
cd frontend
npm run build -- --outDir /tmp/leek-trader-build
```

## 当前状态

已完成：

- 默认账户初始化
- 行情 fallback
- 市价/限价下单
- 撤单与手动撮合挂单
- 持仓、账户、资金流水更新
- 基础收益统计与资产曲线
- 四个主页面联调

未完成或仍为简化版：

- 登录前端流程
- 多账户支持
- 自动任务调度
- 完整监控后台
- 完整策略管理
