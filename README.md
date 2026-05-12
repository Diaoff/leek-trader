# Leek Trader

Leek Trader 是一个面向本地单用户场景的 A 股模拟交易系统。项目目标是把“行情数据 → 自选股/智能选股 → 策略运行 → 风控校验 → 模拟交易 → 持仓与盈亏分析 → Web 可视化”串成一个可运行、可验证、可持续迭代的闭环。

> 当前定位：本地研究与模拟交易 MVP，不是生产级券商交易系统，也不提供真实下单能力。

## 功能概览

- **市场与行情**：A 股证券目录、个股报价、市场总览、历史行情、市场新闻；报价具备 TTL 缓存、强制刷新、Redis 共享缓存和 provider 失败后的 stale 降级边界。
- **行情推送**：提供 `/api/v1/quotes/stream` WebSocket 行情推送，自选股页支持推送更新、断线重连与轮询兜底。
- **数据质量**：提供日线行情质量报告，可检查缺失字段、停牌、ST 标记和交易日缺口；提供多源健康摘要与主备切换说明。
- **自选股管理**：自选股分组、关注列表、个股详情联动。
- **智能选股**：数据库配置驱动的选股任务、运行记录与选股结果展示。
- **策略管理**：策略创建、编辑、启停、删除、手动运行，支持 `signal_only` 与 `auto_trade` 执行模式。
- **研究增强**：策略版本快照、2–4 个策略/版本对比、历史收盘复盘归档、交易 CSV 导出与内置策略模板。
- **RL 训练**：强化学习模型训练、训练任务跟踪、模型注册表、模型对比摘要与启用状态管理。
- **模拟交易**：默认单账户、市价单、限价单、撤单、手动撮合、风控拒单原因展示。
- **资产分析**：账户资产、持仓、委托、成交、收益曲线、盈亏分析。
- **AI 分析**：面向个股/市场信息的本地分析入口，可按环境配置接入外部能力。
- **异步任务**：Celery worker/beat 支撑行情同步、策略运行、交易撮合等后台任务，并在监控摘要中展示重试策略、幂等范围和重复触发边界。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Vue 3、Vite、TypeScript、Element Plus、Pinia、ECharts、Tailwind CSS |
| 后端 | FastAPI、SQLAlchemy 2、Pydantic、Uvicorn |
| 数据库 | PostgreSQL，测试使用 SQLite fixture |
| 异步任务 | Celery、Redis |
| 行情/数据 | 东方财富、新浪、腾讯、BaoStock 等 provider |
| 测试 | pytest、vue-tsc、Vite build |

## 项目结构

```text
.
├── backend/                    # FastAPI 后端
│   ├── app/api/                # API 路由
│   ├── app/core/               # 配置、数据库、Celery、认证、日志
│   ├── app/market/             # 行情、证券目录、历史数据、provider
│   ├── app/models/             # SQLAlchemy 模型
│   ├── app/schemas/            # Pydantic schema
│   ├── app/portfolio/          # 资产与持仓服务
│   ├── app/risk/               # 风控服务
│   ├── app/strategy/           # 策略服务
│   ├── app/tasks/              # Celery 任务
│   └── tests/                  # 后端测试
├── frontend/                   # Vue 前端
│   └── src/
│       ├── api/                # API client
│       ├── stores/             # Pinia stores
│       ├── types/              # TypeScript 类型
│       ├── views/              # 页面
│       └── components/         # 复用组件
├── docker-compose.yml          # PostgreSQL、Redis、后端、前端、Celery
├── start.sh / stop.sh          # 本地启动与停止脚本
├── start-docker.sh             # Docker Compose 启动脚本
└── async-health.sh             # 本地异步任务健康检查
```

## 环境要求

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+（本地脚本默认连接 `localhost:5432`）
- Redis 7+（仅异步任务需要；可用 Docker 单独启动）
- Docker / Docker Compose（可选，用于容器化运行）

## 快速开始

## 项目边界

Leek Trader 当前只面向本地单用户研究和模拟交易：不接真实券商、不提供真实下单、不做生产级多租户隔离、不做权限矩阵/配额/计费。贡献与功能设计应优先服务本地研究闭环：行情、策略、回测、复盘、纸面交易和可验证报告。

租户、权限、配额、部署演进、API 兼容性和数据源使用边界见 `docs/evolution-boundaries.md`。

异步任务幂等、重复触发和重试边界见 `docs/async-governance.md`。

日志分层和审计事件格式见 `docs/logging-audit.md`。

运行监控指标口径见 `docs/operations-metrics.md`。

高性能核心评估见 `docs/performance-evaluation.md`；AI/ML 样本外验证和解释性边界见 `docs/ai-ml-validation.md`。


### 1. 准备配置

复制环境变量模板并按需调整：

```bash
cp .env.example .env
```

本地脚本默认使用：

```text
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/leek_trader
REDIS_URL=redis://127.0.0.1:6379/0
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

如果你的 PostgreSQL 用户、密码或数据库名不同，请修改 `.env` 或在启动命令前临时覆盖：

```bash
DATABASE_URL='postgresql+psycopg://user:pass@localhost:5432/leek_trader' ./start.sh
```

### 2. 本地启动 Web 主链路

```bash
./start.sh
```

启动成功后访问：

- 前端：`http://127.0.0.1:5173`
- 后端健康检查：`http://127.0.0.1:8000/health`
- API 文档：`http://127.0.0.1:8000/docs`

常用脚本：

```bash
./stop.sh
./restart.sh
```

本地日志默认写入 `.local/logs/`：

- `.local/logs/backend.log`
- `.local/logs/frontend.log`

### 3. 启动异步任务

如果需要同时启动 Celery worker 和 beat：

```bash
./start.sh --with-async
```

只启动后端与异步任务、不启动前端：

```bash
./start.sh --with-async --skip-frontend
```

检查本地异步任务健康状态：

```bash
bash ./async-health.sh
```

持续守护检查：

```bash
bash ./async-health.sh --watch --interval 15 --max-failures 3
```

异步任务日志：

- `.local/logs/celery-worker.log`
- `.local/logs/celery-beat.log`
- `.local/logs/async-guard.log`

如果本机没有 Redis，可以单独启动：

```bash
docker compose up -d redis
```

## Docker 运行

启动完整工作栈（PostgreSQL、Redis、后端、前端、Celery worker、Celery beat）：

```bash
./start-docker.sh
```

停止或重启：

```bash
./stop-docker.sh
./restart-docker.sh
```

查看日志：

```bash
docker compose logs -f backend frontend
docker compose logs -f celery-worker celery-beat
docker compose logs -f backend celery-worker celery-beat
```

Docker 模式会读取仓库根目录 `.env`。容器内 Redis 地址通常应使用 `redis://redis:6379/0`，PostgreSQL 可使用 compose service 名或脚本默认配置。

### 单镜像运行（PostgreSQL、Redis、Python、nginx）

如果需要把 PostgreSQL、Redis、FastAPI/Celery、前端静态资源和 nginx 打进一个镜像，可使用 `Dockerfile.all-in-one`：

```bash
docker build -f Dockerfile.all-in-one -t leek-trader:all-in-one .
```

运行容器：

```bash
cd frontend && npm ci && npm run build && cd ..

docker run --rm -p 10086:80 -p 5432:5432 \
  -v "$PWD/backend:/app/backend" \
  -v "$PWD/frontend/dist:/app/frontend/dist" \
  -v leek_trader_pgdata:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=postgres \
  leek-trader:all-in-one
```

后端挂载 `backend` 源码目录，前端挂载构建后的 `frontend/dist` 目录。服务器更新代码后，后端重启容器即可生效；前端需要在服务器重新执行 `cd frontend && npm run build` 后再重启容器。

CentOS 服务器手动上传 zip 后，首次部署使用部署脚本；脚本默认读取 `/home/diaoff/leek-trader-dev.zip`，先解压同步再部署：

```bash
chmod +x deploy-centos-all-in-one.sh
sudo REBUILD_IMAGE=1 POSTGRES_PASSWORD='你的强密码' ./deploy-centos-all-in-one.sh
# 或指定压缩包路径
sudo REBUILD_IMAGE=1 POSTGRES_PASSWORD='你的强密码' ./deploy-centos-all-in-one.sh /home/diaoff/leek-trader-dev.zip
```

脚本会自动从 zip 解压到 `/home/diaoff/leek-trader`，构建前端、按需重建容器，并挂载 `backend` 与 `frontend/dist` 便于更新。常用覆盖参数：`ZIP_PATH=/home/diaoff/leek-trader-dev.zip`、`WORK_DIR=/home/diaoff/leek-trader`、`HTTP_PORT=10086`、`POSTGRES_PORT=5432`、`REBUILD_IMAGE=1`、`SKIP_FRONTEND_BUILD=1`。

后续普通更新只替换 `/home/diaoff/leek-trader-dev.zip`，再运行更新脚本。更新脚本会复用现有容器里的数据库配置，不需要也不应该重新输入数据库密码：

```bash
chmod +x update-centos-all-in-one.sh
sudo ./update-centos-all-in-one.sh /home/diaoff/leek-trader-dev.zip
```

如果当前用户没有 Docker 权限，可以用 `sudo ./deploy-centos-all-in-one.sh ...` / `sudo ./update-centos-all-in-one.sh ...`，或者先设置 `DOCKER_CMD='sudo docker'`。脚本默认使用阿里云 apt/pip 镜像源和 `npmmirror` 加速首次构建，并把 pip 超时/重试调大；如果需要改源或超时，可以显式传 `APT_MIRROR`、`APT_SECURITY_MIRROR`、`PIP_INDEX_URL`、`PIP_TIMEOUT`、`PIP_RETRIES`、`NPM_REGISTRY`。脚本会在干净的临时目录里构建前端，避免复用宿主机旧的 `node_modules`；如果服务器没有本机 `npm`，或者 Node 版本低于 18，脚本会自动改用 `node:20-alpine` 容器构建前端。

启动后访问：

- 前端：`http://127.0.0.1:10086`
- 后端健康检查：`http://127.0.0.1:10086/health`
- API 文档：`http://127.0.0.1:10086/docs`
- PostgreSQL：`127.0.0.1:5432`（默认库 `leek_trader_prod`，用户 `postgres`）

单镜像适合本地演示或一次性部署验证；生产环境仍建议使用 `docker-compose.yml` 中的多容器拆分方式，便于数据库持久化、升级和故障隔离。

## 手动开发命令

### 后端

安装依赖：

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
```

启动 API：

```bash
cd backend
PYTHONPATH=. uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

手动启动 Celery worker/beat：

```bash
cd backend
export PYTHONPATH="$(pwd)"
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/leek_trader'
export REDIS_URL='redis://127.0.0.1:6379/0'
../.venv/bin/celery -A app.core.celery_app.celery_app worker --loglevel=info
../.venv/bin/celery -A app.core.celery_app.celery_app beat --loglevel=info
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

构建检查：

```bash
cd frontend
npm run build
```

## 验证与测试

后端测试：

```bash
pytest
```

运行单个测试模块：

```bash
pytest backend/tests/test_orders.py -q
```

前端类型检查与生产构建：

```bash
cd frontend && npm run build
```

异步任务 smoke check：

```bash
./start.sh --with-async --skip-frontend
bash ./async-health.sh
```

## API 与页面入口

主要页面：

- `/`：仪表盘
- `/watchlist`：自选股
- `/stocks/:symbol?`：个股详情
- `/market`：市场总览
- `/news`：市场快讯
- `/smart-selection`：智能选股
- `/strategies`：策略管理
- `/rl-training`：RL 训练与模型注册表
- `/portfolio`：交易与持仓
- `/analysis`：盈亏分析
- `/ai`：AI 分析

后端 API 统一挂载在 `.env` 中的 `API_PREFIX`，默认是 `/api/v1`。主要模块包括：

- `health` / `monitoring`：健康检查与异步任务状态
- `auth`：本地认证相关接口
- `accounts`、`portfolio`、`positions`、`orders`、`trading`：账户、持仓、订单与交易
- `market`、`quotes`、`securities`、`news`：行情、证券目录、新闻，`/market/health/sources` 多源健康摘要，以及 `/market/rl/*` 数据集、训练任务与模型状态接口
- `watchlists`、`watchlist-groups`：自选股
- `strategies`、`smart-selection`：策略与智能选股，策略支持软删除
- `reporting`：收益与报表
- `ai`：AI 分析

## 策略与 RL 模型使用说明

- 训练完成后，可在 `/rl-training` 的模型注册表中点击“启用模型”，将模型状态切换为 `active`。
- 策略中心的删除是逻辑删除：策略列表会隐藏已删除策略，历史运行记录仍会保留。
- `active` 模型不等于自动实盘或自动下单；实际交易仍由策略 `execution_mode` 和手动/异步运行决定。

## 数据与初始化说明

- 应用启动时会初始化数据库表和默认本地账户。
- 默认账户名称由 `DEFAULT_ACCOUNT_NAME` 控制。
- `DEFAULT_TENANT_ID` 用于当前本地单租户上下文。
- 行情数据来自第三方公开数据源，可能受网络、限流、交易日历和数据源格式变化影响。
- 本项目用于模拟交易与研究，不构成投资建议。

## 常见问题

### 端口被占用

默认端口：

- 后端：`8000`
- 前端：`5173`
- PostgreSQL：`5432`
- Redis：`6379`

检查占用：

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

也可以通过环境变量覆盖本地脚本端口：

```bash
BACKEND_PORT=8001 FRONTEND_PORT=5174 ./start.sh
```

### 数据库连接失败

确认 PostgreSQL 已启动，并且 `DATABASE_URL` 与实际用户、密码、数据库名一致。Docker 模式下注意容器内外主机名不同：本机常用 `localhost`，compose 网络内常用 service 名。

### 异步任务检查失败

先确认 Redis 可达：

```bash
docker compose up -d redis
bash ./async-health.sh
```

再查看日志：

```bash
tail -n 120 .local/logs/celery-worker.log
tail -n 120 .local/logs/celery-beat.log
```

### 前端请求后端失败

确认 `VITE_API_BASE_URL` 指向可访问的后端 API，例如：

```text
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

修改前端环境变量后需要重启 Vite。

## 开发约定

- 后端业务逻辑优先放在 service 层，路由层保持薄封装。
- 后端测试文件命名为 `test_*.py`，测试函数命名为 `test_*`。
- 前端页面组件使用 PascalCase，例如 `PortfolioView.vue`。
- 前端 API、store、工具函数沿用现有 camelCase/feature 命名风格。
- 保留现有中文 UI 文案，除非明确需要调整。
- 不提交 `.env`、日志、数据库文件、虚拟环境、`node_modules` 等本地生成内容。

## 当前边界

当前不优先覆盖：

- 真实券商交易接入
- 完整多用户/多租户运营后台
- 生产级权限、审计、监控与告警体系
- WebSocket 集群、高可用、负载均衡等生产级实时行情平台
- 完整策略脚本编辑器或在线代码执行沙箱

## License

当前仓库未声明开源许可证。如需发布或分发，请先补充明确的许可证文件。
