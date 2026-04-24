# 项目推进计划

更新日期：2026-04-24

## 项目定位

Leek Trader 当前已经是一个面向本地单用户场景的股票模拟交易系统 MVP，重点不是继续铺更多页面或概念能力，而是把主链路收敛成可验证、可持续迭代的真实实现：

- 行情获取
- 策略执行
- 风控校验
- 模拟撮合
- 持仓与报表
- Web 可视化

---

## 当前代码事实

以下状态基于仓库现有实现核对后确认：

### 已完成

1. 工程骨架与页面主路由已具备
   - 后端入口与 API 路由：`backend/app/main.py`、`backend/app/api/*.py`
   - 前端页面路由：`frontend/src/router/index.ts`
   - 本地运行脚本：`start.sh`、`stop.sh`、`restart.sh`

2. 行情服务已有 fallback 和缓存降载基础
   - 行情服务与缓存实现：`backend/app/market/service.py`
   - 行情 provider 测试：`backend/tests/test_market_service.py`

3. 策略已支持数据库驱动、启停、手动运行和 `strategy_runs` 持久化
   - 策略接口：`backend/app/api/strategies.py`
   - 策略执行与运行记录：`backend/app/strategy/service.py`
   - 回归测试：`backend/tests/test_strategies.py`

4. 异步体系已完成一部分基础接入
   - Celery 应用与定时任务注册：`backend/app/core/celery_app.py`
   - 行情刷新任务：`backend/app/tasks/market_tasks.py`
   - 挂单撮合任务：`backend/app/tasks/trading_tasks.py`
   - 策略周期运行任务：`backend/app/tasks/strategy_tasks.py`
   - 对应测试：`backend/tests/test_market_tasks.py`、`backend/tests/test_trading_tasks.py`、`backend/tests/test_strategy_tasks.py`

### 未完成或仍是占位实现

1. 异步链路仍偏轻量
   - 当前已异步化的主要是行情刷新、策略周期运行和挂单撮合
   - worker / beat 运行说明已补齐，但任务级重试、监控与观测信息仍偏轻
   - 本地模式仍默认只启动前后端，异步任务需显式起 worker / beat

2. 文档需要按执行进度持续回写
   - `plan.md` 用于记录阶段、状态和下一步
   - `README.md` 用于对外说明当前真实能力，不提前承诺未完成功能

---

## 当前阶段判断

当前不再处于“从零搭建”阶段，也不能把“已有 Celery 接入”误写成“异步体系完全完成”。

目前更准确的阶段定义是：

**阶段 D：异步任务增强运行说明已补齐，进入可靠性收敛阶段。**

阶段结论：

- 行情缓存：已完成最小可用版本
- 行情刷新任务：已完成最小可用版本
- 策略异步调度：已完成最小可用版本
- 挂单撮合异步任务：已完成最小可用版本
- 统一异步运行说明：已补齐
- 任务重试与可观测性：待补强

---

## 本轮已完成步骤

### Step 1: 文档与项目进度第一次重新对齐

状态：已完成

完成内容：

- 重新核对 `plan.md`、`README.md` 与当前代码实现
- 明确“异步未完成”的真实范围是“策略调度未任务化”，而不是“整个异步体系完全不存在”
- 将后续优先级收敛到策略异步任务，而不是继续扩展非核心能力

对齐结果：

- 不再把仓库描述为“仍需从零搭建”
- 不再把异步体系描述为“已完整完成”
- 后续计划以策略异步调度补齐为主线

---

## 下一阶段推进计划

### Step 2: 补齐策略异步调度主链路

状态：已完成

关键文件：

- `backend/app/tasks/strategy_tasks.py`
- `backend/app/core/celery_app.py`
- `backend/app/strategy/service.py`
- `backend/tests/test_strategies.py`
- `backend/tests/test_strategy_tasks.py`

目标：

- 提供真实可执行的策略周期任务，而不是占位返回
- 将策略任务纳入 Celery `include/imports`
- 为 Beat 增加策略调度入口
- 保持手动运行接口与异步运行结果的语义一致

验收标准：

- 可以直接调用策略异步任务并返回真实执行结果
- Celery Beat 中能看到策略周期任务配置
- 现有策略手动运行能力不回退
- 至少有一条测试覆盖策略异步调度路径

本次结果：

- `backend/app/tasks/strategy_tasks.py` 已实现 `run_strategy_cycle_task()`，默认执行所有 `active` 策略
- `backend/app/strategy/service.py` 已增加 `run_active_strategies()`，用于批量执行活跃策略并复用现有运行逻辑
- `backend/app/core/celery_app.py` 已纳入 `app.tasks.strategy_tasks`，并增加 `run-strategy-cycle` Beat 配置
- `backend/tests/test_strategy_tasks.py` 已覆盖策略周期任务执行、wrapper 返回和 Celery 调度注册

### Step 3: 收敛异步运行说明与维护约定

状态：已完成

关键文件：

- `README.md`
- `plan.md`

目标：

- README 增加明确的异步状态说明
- 计划文档在每次完成阶段性工作后同步更新状态
- 避免文档对未来能力做超前承诺

验收标准：

- README 中明确列出已落地异步能力与未完成项
- `plan.md` 中至少包含当前阶段、已完成步骤、下一步骤

本次结果：

- README 已同步标记策略周期运行任务与 Beat 调度已落地
- `plan.md` 已将当前阶段切换为“异步任务增强最小闭环已完成”
- 文档中的剩余缺口已收敛为运行说明与可观测性，而不是继续笼统写“异步未完成”

### Step 4: 异步链路验证收敛

状态：已完成

关键文件：

- `backend/tests/test_market_tasks.py`
- `backend/tests/test_trading_tasks.py`
- `backend/tests/test_strategies.py`
- `README.md`

目标：

- 为异步相关主链路补齐验证说明
- 保证任务入口、任务返回值和计划文档一致

验收标准：

- 相关测试可执行
- README 中包含可复现的验证命令

本次结果：

- `./.venv/bin/python -m pytest backend/tests -q` 已通过，81 个用例全部成功
- `cd frontend && npm run build` 已通过
- 受影响 Python 文件诊断为 0 个错误
- 前端构建仍有大 chunk warning，但不影响当前文档对齐结论

### Step 5: 补齐异步运行与排障说明

状态：已完成

关键文件：

- `README.md`
- `start.sh`
- `docker-compose.yml`

目标：

- 明确 worker / beat 启动方式
- 补齐本地调试、任务排障和日志定位说明
- 让异步任务从“代码已存在”推进到“开发者可稳定运行”

验收标准：

- README 中存在 worker / beat 启动说明
- 可以根据文档定位 Celery 相关任务与日志
- 文档说明与仓库脚本保持一致

本次结果：

- `README.md` 已补齐本地模式与 Docker 模式下的 worker / beat 启动方式
- `README.md` 已明确异步任务入口文件与日志定位方式
- `start.sh` 已明确本地模式不会自动启动 Celery worker / beat
- `start-docker.sh` 与 `restart-docker.sh` 已补充 Docker 模式中异步服务和日志查看提示
- `./.venv/bin/python -m pytest backend/tests -q` 已通过，合计 80 个用例
- `cd frontend && npm run build` 已通过
- `bash -n start.sh start-docker.sh restart-docker.sh` 已通过

### Step 6: 补齐任务重试与可观测性基线

状态：待执行

关键文件：

- `backend/app/core/celery_app.py`
- `backend/app/tasks/market_tasks.py`
- `backend/app/tasks/strategy_tasks.py`
- `backend/app/tasks/trading_tasks.py`
- `README.md`

目标：

- 为关键 Celery 任务补齐更明确的失败重试策略和日志信号
- 让异步链路从“可运行”推进到“更易定位失败原因”
- 将排障说明从启动说明进一步延伸到失败场景处理

验收标准：

- 关键任务具备一致的重试/失败处理约定
- README 中存在任务失败时的排障入口说明
- 相关变更具备明确验证命令

---

## 执行原则

- 优先补真实主链路，不横向扩展页面表面能力
- 优先补齐策略异步任务，不提前引入更复杂的消息编排
- 每完成一个明确步骤，同步更新 `plan.md` 与 `README.md`
- 文档描述必须以当前代码和验证结果为准

---

## 验证方式

本阶段相关验证以以下命令为准：

1. 后端异步相关回归测试
   - `./.venv/bin/python -m pytest backend/tests/test_market_tasks.py backend/tests/test_trading_tasks.py backend/tests/test_strategy_tasks.py -q`

2. 前端构建校验
   - `cd frontend && npm run build`

3. 文档一致性检查
   - 检查 `README.md` 中“当前状态”和 `plan.md` 中“当前阶段判断”是否一致

---

## 当前结论

当前仓库的真实状态不是“异步体系完全完成”，而是：

**行情、策略、撮合三条异步基础链路已经接入，worker / beat 运行说明也已补齐，下一步应优先补强任务重试与可观测性，并持续把执行结果回写到 `plan.md` 与 `README.md`。**
