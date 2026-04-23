# 开发计划

## Context

当前仓库已经不是“从零搭建阶段”，而是一个**本地单用户股票模拟交易系统 MVP**：

- 后端已具备 FastAPI、SQLAlchemy、基础认证、监控、策略、交易、报表、自选、AI 分析接口
- 前端已具备仪表盘、自选盯盘、策略中心、交易与持仓、盈亏复盘、AI 分析页面
- 本地运行方式已包含 `start.sh`、Docker Compose、`.env.example`、后端测试与前端构建校验

因此，下一阶段目标不再是“初始化工程骨架”，而是把现有可演示链路进一步收敛为**可验证、可持续迭代的真实主链路**。

---

## 当前仓库现状

### 已完成的基础能力

1. **工程基础**
   - `backend/`：FastAPI + SQLAlchemy 服务入口、配置、数据库初始化
   - `frontend/`：Vue 3 + Vite + Pinia + Element Plus + ECharts
   - `docker-compose.yml`、`start.sh`、`stop.sh`、`restart.sh` 可用于本地运行

2. **核心业务模型**
   - 已具备 `accounts`、`positions`、`orders`、`trades`、`cash_flows`
   - 已具备 `strategies`、`strategy_runs`
   - 已具备 `watchlist_groups`、`watchlist_items`
   - 关键业务表已预留 `tenant_id`、时间字段、状态字段

3. **核心链路**
   - 行情查询与多源 fallback 已可用
   - 模拟下单、挂单撮合、撤单、持仓与资金更新已可用
   - 风控链已覆盖交易时段、停牌、涨跌停、仓位、日频、T+1 等约束
   - 报表与资产曲线接口已可用

4. **前端主界面**
   - `/`：仪表盘
   - `/watchlist`：自选盯盘
   - `/strategies`：策略中心
   - `/portfolio`：交易与持仓
   - `/analysis`：盈亏复盘
   - `/ai`：AI 分析

### 当前仍需补强的关键点

1. 行情服务缺少明确的缓存/降载层
2. 异步任务体系仍偏轻，市场刷新与策略调度需要进一步真实化
3. 前后端主链路需要继续围绕“真实数据”收敛，而非继续横向扩表面能力
4. 文档、计划与当前代码能力必须持续同步，避免 roadmap 漂移

---

## 当前推荐实现路径

### 1. 继续保持单体分层架构，不提前拆分微服务

当前最合理的路径仍然是：

- `backend/`：围绕 market / strategy / risk / trading / portfolio / reporting 继续细化
- `frontend/`：围绕 dashboard / watchlist / strategies / portfolio / analysis 做真实链路闭环
- `infra/`：继续保持本地优先、预留 Redis/Celery/多租户扩展点

理由：

- 核心交易闭环仍在打磨，不宜过早引入服务拆分复杂度
- 当前单仓单体对 MVP 迭代效率最高
- 表结构与领域边界已为未来 SaaS 演进预留空间

### 2. 以“真实交易闭环优先”推进后续开发

优先顺序：

1. 行情获取/缓存
2. 策略运行与信号持久化
3. 风控校验与拒单审计
4. 模拟撮合与资金持仓更新
5. 投资组合与报表展示
6. 前端可视化与操作闭环

### 3. 保持扩展能力，但降低扩展面的优先级

以下能力**可以保留、但不应抢占主线资源**：

- AI 个股分析 / AI 聊天助手
- 更完整的认证与多用户能力
- 完整监控后台
- 更复杂的任务编排与消息分发
- WebSocket 实时行情推送

---

## 下一阶段实施计划

### 阶段 A：文档与现实对齐

关键文件：

- `plan.md`
- `README.md`

目标：

- 保证计划文档、README 与真实路由、真实功能范围一致
- 不再出现“仓库仍无代码、需从零搭建”的过时描述

### 阶段 B：策略链路真实化

关键文件：

- `backend/app/models/strategy.py`
- `backend/app/models/strategy_run.py`
- `backend/app/schemas/strategy.py`
- `backend/app/api/strategies.py`
- `backend/app/strategy/service.py`
- `backend/app/tasks/strategy_tasks.py`
- `frontend/src/api/strategies.ts`
- `frontend/src/stores/strategies.ts`
- `frontend/src/views/StrategiesView.vue`
- `frontend/src/views/DashboardView.vue`

目标：

- 策略从数据库读取，不再依赖纯内存定义
- 支持策略启停、更新、手动运行
- 持久化 `strategy_runs`
- 前端展示真实运行结果，不再使用随机演示指标

### 阶段 C：交易审计补强

关键文件：

- `backend/app/models/order.py`
- `backend/app/schemas/order.py`
- `backend/app/trading/service.py`
- `frontend/src/views/PortfolioView.vue`

目标：

- 风控拒单结果可查询、可展示、可审计
- 前端委托列表可直接看到拒单原因

### 阶段 D：行情缓存与异步任务增强

关键文件：

- `backend/app/market/service.py`
- `backend/app/tasks/market_tasks.py`
- `backend/app/core/celery_app.py`

目标：

- 为行情查询增加缓存或降载层
- 让市场刷新与策略运行逐步进入真实任务调度

### 阶段 E：验证体系收敛

关键文件：

- `backend/tests/**`
- `README.md`
- 如后续获准，再补前端测试脚手架

目标：

- 后端继续保持回归测试覆盖
- 前端至少持续满足 build/typecheck 校验
- 关键交易/策略链路具备明确验证脚本与说明

---

## 设计约束与实现要点

- 首版仍以**单用户、本地部署**为主
- 所有核心业务表继续保留 `tenant_id`
- 首版以 REST API 为主，WebSocket 后置
- 行情访问必须走统一适配层
- 所有交易写链路必须具备事务与审计可追踪性
- AI、复杂监控、多租户控制台不是当前主线阻塞项

---

## 验证方案

开发落地后按以下顺序验证：

1. **后端回归测试**
   - `./.venv/bin/python -m pytest backend/tests -q`

2. **前端构建校验**
   - `cd frontend && npm run build`

3. **策略验证**
   - 查看策略列表
   - 修改策略状态或参数
   - 手动运行策略
   - 校验 `strategy_runs` 与前端展示一致

4. **交易验证**
   - 提交有效买卖单
   - 提交会被风控拒绝的订单
   - 校验订单状态、拒单原因、持仓与资金变化一致

5. **行情验证**
   - 拉取一组标的行情
   - 验证 provider fallback
   - 若引入缓存，验证缓存命中与过期行为

6. **端到端验证**
   - 从盯盘/策略/下单/持仓/复盘页面完成一次完整主链路操作

---

## 结论

当前仓库的主要问题不是“还没搭起来”，而是：

**核心链路已经可运行，但仍需持续从“演示可跑”推进到“真实可验证”。**

因此后续开发的重点应放在：

- 收敛主链路真实度
- 减少随机/占位数据
- 增强审计、缓存、任务化与验证能力
- 控制非核心扩展面的膨胀
