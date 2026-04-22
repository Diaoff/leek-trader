# 开发计划

## Context
基于 `股票模拟交易系统设计文档.md`，当前仓库处于需求/规划起点阶段，尚未发现现有代码、配置或工程骨架。目标是先落地一个**单用户、本地部署、可演进到 SaaS** 的股票模拟交易系统 MVP，优先打通“行情获取 → 策略计算 → 风控校验 → 模拟交易 → 持仓/盈亏分析 → Web 可视化”主链路，并在架构层预留后续多租户、插件化和异步任务扩展能力。

本次建议的开发计划以“先可运行、再扩展”为原则：第一阶段避免直接上完整微服务与重型 SaaS 体系，采用单体分层架构实现设计文档中的核心闭环，同时保留未来拆分空间。

## 当前仓库现状
- 已存在需求文档：`/Users/diaoff/code/vibe/leek-trader/股票模拟交易系统设计文档.md`
- 未发现其他现有代码、测试、前端、后端或部署文件
- 当前没有可复用的现成函数、模块或工程配置；需从工程初始化开始搭建

## 推荐实现路径

### 1. 先搭建单体分层工程，而非一开始做完整 SaaS
建议按文档中的分层思想落地为单仓单体应用：
- `backend/`：FastAPI + SQLAlchemy + Celery + Redis
- `frontend/`：Vue 3 + Vite + Element Plus + Pinia + ECharts
- `infra/`：Docker Compose、本地开发依赖、监控预留

原因：
- 当前仓库没有基础代码，先做单体更容易打通主流程
- 文档强调“演进式多租户”，说明 SaaS 能力应预留而非首版一次性做完
- 行情、策略、交易、风控、分析本身已足够复杂，首版应优先验证业务闭环

### 2. 后端按领域拆分模块，围绕交易主链路建模
建议后端最先实现以下核心域：
- `market`：行情拉取、标准化、缓存、数据源降级
- `strategy`：策略定义、规则配置、信号生成、回测预留
- `risk`：交易时间、停牌/涨跌停、仓位、次数、熔断校验
- `trading`：订单、撮合、成交、持仓变更、账户流水
- `portfolio`：账户资产、持仓、浮盈/实盈计算
- `reporting`：绩效统计、资产曲线、收盘复盘预留
- `system`：认证、配置、日志、健康检查

建议先围绕以下闭环开发：
1. 获取行情
2. 计算策略信号
3. 执行风控校验
4. 生成模拟订单并撮合
5. 更新持仓与账户
6. 提供查询接口给前端展示

### 3. 数据模型优先覆盖 MVP 主流程，并预留 SaaS 字段
数据库首批核心表建议包括：
- `users`
- `accounts`
- `positions`
- `orders`
- `trades`
- `cash_flows`
- `watchlists` / `stock_pools`
- `market_quotes`
- `strategies`
- `strategy_runs`
- `risk_rules`
- `daily_reports`

所有业务表建议从首版开始预留：
- `tenant_id`
- `created_at`
- `updated_at`
- 必要状态字段（如 `status`、`source`、`version`）

这样后续从单用户演进到共享表/独立 schema 时，不需要重做核心表结构。

### 4. 行情系统首版采用“免费多源 + 标准化接口”
按设计文档，首版就应抽象数据源适配层，而不是把某个免费接口直接写死到业务里。

建议实现：
- `QuoteProvider` 统一接口
- 新浪财经主源适配器
- 东方财富备用适配器
- AkShare 兜底适配器
- 标准化行情 DTO
- Redis 15 秒缓存
- 批量拉取与错误重试

MVP 阶段先支持：
- 实时价格
- 涨跌幅
- 成交量
- 交易状态（正常/停牌）
- 时间戳有效性校验

先不要在第一阶段实现过于复杂的 WebSocket 恢复逻辑；优先完成轮询版可用实现。

### 5. 策略引擎首版做“配置化基础策略”，暂缓脚本上传
文档中的“脚本上传自定义策略”复杂度较高，首版建议只做：
- 双均线策略
- MACD / RSI 二选一作为第二个示例策略
- 参数化配置
- 策略启停
- 定时执行
- 信号记录

规则引擎建议用“数据库配置 + Python 策略类”方式先实现，而不是首版直接引入复杂规则引擎/脚本沙箱。这样更容易验证交易链路和前端配置流程。

### 6. 交易执行模块必须严格先做风控，再撮合
交易执行链路应固定为：
1. 校验交易时间
2. 校验标的状态（ST/停牌/涨跌停）
3. 校验单日交易次数
4. 校验单标的仓位上限
5. 校验总仓位上限
6. 校验日亏损熔断
7. 计算委托价格与数量
8. 执行模拟撮合
9. 更新订单、成交、持仓、账户流水

其中关键规则：
- 买入数量按 A 股 100 股整数倍取整
- 支持 T+1 约束
- 拒单必须保存原因，便于审计和 UI 展示
- 核心写操作使用数据库事务

### 7. 盈亏分析优先做 API 可用，再补强图表表现
首版分析层先保证数据正确：
- 当前总资产
- 可用资金
- 持仓市值
- 浮动盈亏
- 已实现盈亏
- 累计收益率
- 按日聚合的资产曲线
- 基础交易统计（胜率、次数、盈亏比）

前端图表首版建议实现：
- 仪表盘总览卡片
- 自选/行情列表
- 持仓列表
- 订单/成交记录
- 资产曲线
- 基础策略管理页

K 线、行业分布、复杂复盘报告可放在第二阶段。

### 8. AI 个股分析与 AI 收盘复盘放到第二阶段
文档中 AI 能力价值高，但对首版闭环不是阻塞项，且依赖外部模型接口、提示词设计、成本控制。

建议拆分为独立阶段：
- 第二阶段接入 AI 个股分析
- 第二阶段补收盘复盘任务与消息分发
- 统一设计模型配置、调用配额、失败重试和结果缓存

### 9. 基础设施与工程化从首版就补齐最小闭环
首版就应具备：
- Docker Compose 本地一键启动
- PostgreSQL + Redis 基础依赖
- Alembic 数据库迁移
- Pytest 后端测试
- 前端基础单测/组件测试（可轻量）
- `.env.example`
- 健康检查与基础日志

日志建议首版先覆盖：
- 行情拉取日志
- 策略运行日志
- 交易执行日志
- 风控拒绝日志
- 系统异常日志

## 建议开发阶段

### 阶段 1：工程初始化
关键文件（计划新增/修改）：
- `backend/pyproject.toml` 或 `backend/requirements.txt`
- `backend/app/main.py`
- `backend/app/core/config.py`
- `backend/app/core/db.py`
- `backend/alembic.ini`
- `frontend/package.json`
- `frontend/src/main.ts`
- `docker-compose.yml`
- `.env.example`

目标：
- 初始化前后端工程
- 接通 PostgreSQL、Redis
- 提供 FastAPI 基础服务和 Vue 基础页面

### 阶段 2：账户、持仓、订单基础模型
关键文件（计划新增/修改）：
- `backend/app/models/account.py`
- `backend/app/models/position.py`
- `backend/app/models/order.py`
- `backend/app/models/trade.py`
- `backend/app/models/cash_flow.py`
- `backend/app/schemas/*.py`
- `backend/app/api/accounts.py`
- `backend/app/api/orders.py`

目标：
- 建立账户、持仓、订单、成交、流水核心模型
- 提供基础查询接口

### 阶段 3：行情模块
关键文件（计划新增/修改）：
- `backend/app/market/providers/base.py`
- `backend/app/market/providers/sina.py`
- `backend/app/market/providers/eastmoney.py`
- `backend/app/market/providers/akshare_provider.py`
- `backend/app/market/service.py`
- `backend/app/tasks/market_tasks.py`
- `backend/app/api/quotes.py`

目标：
- 建立统一行情接口
- 支持批量拉取、缓存、重试、降级
- 提供行情查询 API

### 阶段 4：策略与信号模块
关键文件（计划新增/修改）：
- `backend/app/models/strategy.py`
- `backend/app/models/strategy_run.py`
- `backend/app/strategy/base.py`
- `backend/app/strategy/strategies/moving_average.py`
- `backend/app/strategy/strategies/macd.py`
- `backend/app/strategy/service.py`
- `backend/app/tasks/strategy_tasks.py`
- `backend/app/api/strategies.py`

目标：
- 支持策略创建、启停、参数配置
- 输出标准化买卖信号

### 阶段 5：风控与模拟交易执行
关键文件（计划新增/修改）：
- `backend/app/risk/service.py`
- `backend/app/risk/rules/*.py`
- `backend/app/trading/service.py`
- `backend/app/trading/matcher.py`
- `backend/app/api/trading.py`

目标：
- 实现完整风控校验链路
- 实现模拟撮合、T+1、仓位与资金更新

### 阶段 6：盈亏分析与仪表盘前端
关键文件（计划新增/修改）：
- `backend/app/portfolio/service.py`
- `backend/app/reporting/service.py`
- `backend/app/api/portfolio.py`
- `frontend/src/views/Dashboard.vue`
- `frontend/src/views/Market.vue`
- `frontend/src/views/Strategies.vue`
- `frontend/src/views/Portfolio.vue`
- `frontend/src/stores/*.ts`
- `frontend/src/api/*.ts`

目标：
- 展示账户总览、行情、策略、持仓、交易记录、资产曲线
- 打通前后端主业务流程

### 阶段 7：测试与部署完善
关键文件（计划新增/修改）：
- `backend/tests/unit/**`
- `backend/tests/integration/**`
- `frontend/src/components/**/*.test.ts`
- `docker-compose.yml`
- `README`（若后续需要再补）

目标：
- 为关键交易链路补测试
- 完善容器化启动与本地开发体验

## 设计约束与实现要点
- 首版以**单用户版**为目标，但数据表统一预留 `tenant_id`
- 首版只做 REST API；WebSocket 和复杂消息分发后置
- 首版优先轮询行情，不强依赖复杂实时推送
- 首版暂不做企业级 RBAC、多租户控制台、邮件/短信告警
- AI 能力、回测增强、复杂选股器、高级监控放到后续迭代
- 所有核心交易写链路必须具备事务与审计日志
- 所有外部行情接口必须经适配层访问，不能散落在业务逻辑中

## 可复用能力说明
当前仓库内未发现现成可复用函数、模块、工程配置或测试框架；本计划不依赖仓库已有实现。唯一可直接复用的是需求约束与模块划分，来源于：
- `/Users/diaoff/code/vibe/leek-trader/股票模拟交易系统设计文档.md`

## 验证方案
开发落地后建议按以下顺序验证：

1. **工程启动验证**
- 启动 PostgreSQL、Redis、FastAPI、Vue
- 确认前后端与数据库连接正常
- 健康检查接口返回成功

2. **行情验证**
- 拉取一组股票实时行情
- 验证主源失败时能自动切换备用源
- 验证 Redis 缓存命中与过期策略

3. **策略验证**
- 创建双均线策略并启用
- 使用历史/模拟行情触发买入卖出信号
- 校验信号记录完整

4. **交易验证**
- 对有效信号执行模拟买入/卖出
- 校验风控拒单场景：非交易时段、停牌、涨跌停、超仓位、超日频、亏损熔断
- 校验订单、成交、持仓、账户流水一致性

5. **盈亏验证**
- 校验浮盈、实盈、累计收益率计算结果
- 校验资产曲线与交易记录一致

6. **端到端验证**
- 前端完成一次从查看行情、启用策略、自动产生信号、成交、查看持仓与盈亏的完整流程
- 运行后端测试与关键前端测试
