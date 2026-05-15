# 开源 Python 量化项目精华吸收计划

## 目标

本计划把国内外 Python 量化开源项目中适合 Leek Trader 的设计思想，转化为可落地、可验证、可回滚的增量路线。

当前项目定位保持不变：本地/私有化 A 股研究、回测、复盘和纸面交易平台。短期不接真实券商，不改造成全市场机构级交易终端，不引入会架空现有 FastAPI + Vue 架构的重型框架。

## 基线判断

Leek Trader 已具备以下主链路：

- 行情 provider、历史行情入库、数据质量报告。
- 策略插件、策略运行、策略版本、策略对比。
- 单标的/组合回测、参数优化、绩效报告。
- 账户、订单、持仓、成交、现金流水、纸面撮合。
- 风控阈值、拒单原因、风险规则版本追溯。
- 智能选股、AI 分析、RL 训练与模型注册。

因此，本计划不以“替换框架”为目标，而以“补强薄弱接口和专业量化细节”为目标。

## 吸收原则

- 只吸收适合当前边界的思想和局部能力，不直接吞入完整框架。
- 数据源优先做 provider 插件和健康评分，不替换主数据链路。
- 策略能力优先统一协议，再扩充模板，避免每个策略自成孤岛。
- 回测和纸面交易共享同一套撮合、成本、风控假设，减少结果断层。
- 新依赖必须先有 spike、许可证评估、字段覆盖评估、失败模式和回滚方案。
- 所有阶段必须有后端测试；涉及前端展示时必须通过前端构建。

## 开源项目可吸收点映射

| 项目 | 可吸收精华 | 本项目落点 | 是否建议直接依赖 |
| --- | --- | --- | --- |
| `vnpy/vnpy` | 事件驱动、Gateway/Engine 分层、订单生命周期、风控前置 | `backend/app/trading`、`backend/app/risk`、未来事件日志 | 否 |
| `shinnytech/tqsdk-python` | 回测与交易同策略代码、简洁 API、数据/交易闭环体验 | `backend/app/strategy`、`backend/app/backtest` | 否 |
| `QUANTAXIS` | 本地数据仓库、批量同步、数据标准化、任务化研究 | `backend/app/market`、Celery 任务、数据质量 | 否 |
| `1nchaos/adata` | A 股基础数据、概念、资金流、轻量数据接口 | 新增只读 provider 候选 | 先 spike |
| `Micro-sheep/efinance` | 多品类轻量数据、东方财富数据封装 | 新增只读 provider 候选 | 先 spike |
| `mpquant/Ashare` | 极简新浪/腾讯行情兜底 | 现有新浪/腾讯 provider 的参考实现 | 通常否 |
| `mpquant/MyTT` | 通达信/同花顺风格指标函数、公式迁移思路、轻量技术指标库 | `backend/app/indicators`、策略模板库、因子研究基础接口 | 先 spike |
| `bbfamily/abu` | 策略模板、因子实验、机器学习研究流程 | 策略模板库、因子实验页 | 否 |
| `Rockyzsu/stock` | 教学型策略案例、低门槛样例 | 示例策略与文档 | 否 |
| `shidenggui/easytrader` | 交易适配器思想、账户/下单抽象 | 未来交易 gateway 接口占位 | 否，且不接真实券商 |
| `shidenggui/easyquant` | 轻量策略运行封装 | 参考即可 | 否 |

## 不做范围

- 不接真实券商、不做客户端键鼠自动化下单。
- 不把 `vnpy`、`QUANTAXIS`、`tqsdk` 作为底层框架引入。
- 不把数据工具当完整交易框架。
- 不支持期货、期权、港美股、加密货币等新资产类别，除非另立项目边界。
- 不承诺高频交易、毫秒级撮合、生产级多账户托管。
- 不新增重型依赖，除非单独评审通过。

## Phase 1：数据源插件化与数据健康增强

目标：吸收 QUANTAXIS、AData、efinance、Ashare 的数据层经验，优先补齐 provider 能力边界，而不是直接扩张业务功能。

### 1.1 Provider 能力矩阵

当前状态：已为现有 quote / daily bar / intraday / research provider 建立统一 `ProviderProfile`，后端可返回能力矩阵；监控页已展示 provider 能力、复权支持、登录要求和回测稳定性。能力矩阵读取对单个 provider profile 异常具备兜底跳过，测试已覆盖空能力序列化与异常 provider 忽略场景。

范围：

- 为每个行情/历史数据 provider 声明能力：实时报价、日线、分钟线、基本面、概念、资金流、指数、基金、债券。
- 声明字段覆盖、复权支持、频率限制、是否需要登录、是否稳定用于回测。
- API 返回 provider 能力，供前端和健康页展示。

建议落点：

- `backend/app/market/providers/base.py`
- `backend/app/market/data_service.py`
- `backend/app/api/market.py` 或独立 `market_routes`

验收标准：

- 后端能返回所有 provider 的能力矩阵。
- 单个 provider 异常不影响能力矩阵读取。
- 测试覆盖 provider 能力序列化和空能力兜底。

不做范围：

- 不引入新数据源。
- 不修改现有行情选择优先级。

### 1.2 数据源健康评分

当前状态：已在本地日线源健康报告中补充 `health_level`、覆盖率、空数据率、字段缺失率和新鲜度分数；接口仍保持不主动探测外部网络，避免健康页产生取数副作用。quote / daily bar / intraday / history sync / AData research 调用均会记录最近成功时间、失败次数、空响应次数与平均延迟；回测主路径中的本地日线读取也会记录 `daily_bar_local_read` 事件，因此无论是否触发 fallback，监控页都可展示本地日线健康概览与近期运行时事件。

范围：

- 增加 provider 最近成功时间、失败次数、延迟、空数据率、字段缺失率。
- 给出 `healthy`、`degraded`、`down` 三档状态。
- 数据同步和回测读取时记录数据源健康事件。

建议落点：

- `backend/app/market/source_health.py`
- `backend/app/market/quality_service.py`
- `backend/app/models` 可按需新增 provider 健康模型

验收标准：

- provider 请求成功、失败、空数据均能生成健康指标。
- 健康状态不会因为一次失败直接永久降级。
- 有测试覆盖连续失败、恢复成功、空数据三种场景。

不做范围：

- 不做复杂监控系统。
- 不接入外部告警服务。

### 1.3 AData / efinance 只读 Spike

当前状态：已产出 `docs/spikes/adata-efinance-spike.md` 和 `backend/scripts/spike_data_providers.py` 作为只读评估输出；`adata` 已正式纳入研究辅助范围，用于研究 API、智能选股辅助链路和 provider 能力矩阵展示，但不参与主行情 provider 优先级和主历史日线链路；`efinance` 已完成 spike 并明确 deferred，当前不接入 provider registry、生产 API 或默认页面。该子阶段已按计划口径完成收口。

范围：

- 分别写最小 spike，验证字段覆盖、调用稳定性、许可证、安装体积、失败模式。
- 只读取候选数据；`adata` 可接研究辅助接口，但不入主行情主库、不改主行情优先级、不影响现有主链路。
- 输出评估报告，给出 go / no-go 决策。

建议候选字段：

- AData：基本面、概念板块、资金流向、A 股列表。
- efinance：东方财富封装行情、基金净值、指数/行业数据。

验收标准：

- 形成字段覆盖表。
- 形成失败模式表：网络失败、字段变更、限频、返回空集、编码异常。
- 明确是否引入依赖；若仅限研究辅助，也需写清集成边界、替代方案和回退方案。

不做范围：

- 不在 spike 阶段修改生产数据模型。
- 不把 spike provider 暴露给普通页面。

## Phase 2：回测真实性增强

目标：吸收专业框架的撮合和市场约束思想，让回测结果更接近 A 股纸面交易现实。

### 2.1 A 股交易约束模型

当前状态：已在回测撮合中加入 T+1、停牌、涨跌停买卖限制和 100 股整手约束；`ST` 股票已按 5% 涨跌幅处理。事件输出稳定的 `rejection_code` / `no_trade_reason` 便于复盘解释；异常交易状态当前按 `trade_status != 1` 最小口径统一视为不可交易。

范围：

- T+1 卖出限制。
- 涨跌停无法买入/卖出约束。
- 停牌日不成交。
- 最小交易单位 100 股。
- ST 股票和异常交易状态标记影响。

建议落点：

- `backend/app/backtest/service.py`
- `backend/app/trading/matcher.py`
- `backend/app/core/trading_calendar.py`

验收标准：

- 同一交易日买入后不能在回测中卖出。
- 涨停买入、跌停卖出按配置拒绝或延迟。
- 停牌数据行不产生真实成交。
- 测试覆盖 T+1、涨跌停、停牌、100 股取整。

不做范围：

- 不模拟逐笔订单簿。
- 不承诺盘口级成交概率。

### 2.2 成交容量与滑点模型

当前状态：已支持通过策略参数 `max_volume_participation` 限制单笔最大成交量，支持 `slippage_rate` 比例滑点、`fixed_slippage_amount` 固定滑点，并通过 `impact_slippage_factor` 叠加成交量冲击滑点；回测汇总输出 `total_unfilled_shares`、`total_slippage_cost` 和完整 `execution_model`。

范围：

- 基于成交量限制最大可成交股数或成交金额。
- 支持固定滑点、比例滑点、成交量冲击滑点三种模式。
- 策略回测结果输出未成交、部分成交、滑点成本。

建议落点：

- `backend/app/backtest/service.py`
- 新增可复用成本模型模块，例如 `backend/app/backtest/execution.py`

验收标准：

- 大额订单不会无限按收盘价全额成交。
- 绩效报告区分佣金、滑点、未成交影响。
- 参数优化能沿用同一成本模型。

不做范围：

- 不做高频微观结构模型。
- 不做真实券商成交回报模拟。

### 2.3 回测与纸面撮合口径对齐

当前状态：已抽出共享 `ExecutionFill` 结构，并新增共享订单意图与数量归整 helper；纸面交易 matcher 和回测成交记录共用 `requested_quantity`、`filled_quantity`、`unfilled_quantity`、`price`、`fee`、`matched`、`mode`、`rejection_code` 等字段；现已进一步统一共享成本模型入口，并将回测/纸面交易的未成交原因收口到同一标准 reason code 语义。

范围：

- 抽取回测和纸面交易都能复用的订单意图、成交结果、成本结果结构。
- 统一手续费、滑点、交易单位、价格精度、拒单原因字段。
- 回测结果与纸面订单状态命名保持一致。

建议落点：

- `backend/app/backtest/service.py`
- `backend/app/trading/service.py`
- `backend/app/trading/matcher.py`

验收标准：

- 回测交易记录能映射到纸面订单/成交语义。
- 同一成本参数下，单笔买卖的费用计算一致。
- 有单元测试锁定费用、数量、拒单原因。

完成定义更新：

- Phase 2.1 已完成：A 股交易约束模型已接入回测。
- Phase 2.2 已完成：成交容量与滑点模型已统一输出到执行摘要。
- Phase 2.3 已完成：共享执行语义、共享成本模型入口、统一 reason code 语义均已落地。
- Phase 2 可视为完成，可进入后续阶段。

不做范围：

- 不把历史回测记录写入真实订单表。
- 不让回测直接触发纸面交易。

## Phase 3：策略协议升级

目标：吸收 tqsdk 和 vnpy 的“同一策略逻辑可在不同环境运行”的思想，把策略从单次信号函数升级为更稳定的协议。

### 3.1 标准化策略输出

当前状态：已完成统一策略协议落地。当前主链路已提供 `StrategyContext`、`StrategyMetadata`、`StrategySignal` / `OrderIntent` / `RiskIntent`，服务层对内置策略运行结果统一补齐 `standard_signal`、`strategy_metadata`、`strategy_context`，回测事件也已输出 `standard_signal`。现阶段验收重点不再是“逐个策略改写为原生结构”，而是确认所有内置策略经服务层后都稳定输出相同标准合同，同时保留 legacy dict 兼容层。

范围：

- 定义 `StrategySignal`、`OrderIntent`、`RiskIntent`、`StrategyContext`。
- 保留现有 dict 输出兼容层，允许策略内部继续返回 legacy dict，由服务层标准化为统一结构。
- 每个策略声明所需最小历史、可用执行模式、参数 schema、风险提示。
- API 与回测统一暴露 `standard_signal`、`strategy_metadata`、`strategy_context` 作为正式合同字段。

建议落点：

- `backend/app/strategy/base.py`
- `backend/app/strategy/signals.py`
- `backend/app/strategy/contracts.py`
- `backend/app/strategy/service.py`
- `backend/app/strategy/dto.py`
- `backend/app/strategy/strategies/*`

验收标准：

- 所有内置策略通过 `/strategies`、`/strategies/runs/latest`、`/strategies/{id}/run` 返回 `strategy_metadata`、`strategy_context`、`standard_signal`。
- 回测事件继续输出 `standard_signal`，且 `standard_signal.legacy` 保持可读。
- 测试覆盖 legacy dict 兼容、新结构序列化、API 合同和回测事件合同。

不做范围：

- 不做用户自定义 Python 代码在线执行。
- 不引入复杂策略 DSL。

### 3.2 策略模板库扩展

当前状态：已完成六类模板元数据合同与前端展示扩展。模板目录已覆盖 `breakout / mean_reversion / momentum / grid / factor_scoring / portfolio_rebalance` 六类输出，后端元数据包含 `category / fit_for / not_fit_for / risk_note / minimum_history / research_only / parameter_bounds`，前端策略页已消费这些字段做说明展示。

范围：

- 增加低风险、可解释策略模板：突破、均值回归、动量、网格、因子打分、组合再平衡。
- 每个模板必须有参数边界、适用市场、失效场景、最小历史要求。
- 策略模板在前端展示“适合/不适合”说明。

建议落点：

- `backend/app/strategy/strategies`
- `backend/app/strategy/service.py`
- `frontend/src/views/StrategiesView.vue`

验收标准：

- `/strategies/templates` 持续返回六类模板。
- 模板元数据字段完整可读，参数非法时仍返回可理解错误。
- 前端模板说明持续展示适合/不适合/风险提示/研究属性，不夸大收益。

不做范围：

- 不提供收益承诺。
- 不自动推荐用户实盘下单。

### 3.3 因子研究基础接口

当前状态：已完成研究型单因子横截面评分基础层。仓库中已存在 `backend/app/factors`、`FactorService`、`smart-selection/factors/rank` API，以及 smart selection 内部 `factor_context` 接入。当前应将其定义为“本地 bars 上的单因子计算与横截面排名基础接口”，而不是“完整分组回测平台”。

范围：

- 增加因子定义、因子计算、横截面排名基础接口。
- 初期只支持本地已入库字段和少量派生技术指标。
- 支持把因子结果接入智能选股评分解释。
- 因子输出合同包含 `computable / missing_ratio / source_fields`，并区分 `no_bars / insufficient_history / missing_fields / unsupported_factor`。

建议落点：

- 新增 `backend/app/factors`
- `backend/app/smart_selection`
- `backend/app/indicators`

验收标准：

- 能对一组股票计算单因子排名。
- 能输出缺失数据比例和不可计算原因。
- 因子结果不会覆盖原始行情数据，smart selection 附加的 `factor_context` 不污染原有 bars/spot 字段。
- `smart-selection/factors/rank` 与 smart selection 内部 `factor_context` 的字段命名保持一致。

不做范围：

- 不做大规模分布式因子平台。
- 不把“完整分组回测平台”作为本轮 Phase 3 必交项。
- 不引入未经评审的新数据包。

### 3.4 MyTT 指标兼容 Spike

目标：评估 MyTT 是否适合作为通达信/同花顺公式迁移和指标扩展参考。

当前状态：已形成内部兼容层路线结论，并已有 [docs/mytt-compat-spike.md](/Users/diaoff/code/vibe/leek-trader/docs/mytt-compat-spike.md:1) 记录结论。当前仓库已以自研方式落地 BIAS、WR、CCI、BBI 四个低风险指标，并补充 `REF`、`CROSS`、`COUNT`、`EVERY`、`HHV`、`LLV`、`SMA` 等公式兼容函数；结论是“不引入 MyTT 运行时依赖、不复制外部源码、不改变现有策略信号口径”。

因子衔接：已新增 `FactorService` 并补充 `smart-selection/factors/rank` 接口，可基于 BIAS、CCI、BBI、WR 对一组本地 bar 做横截面排名，并输出历史不足原因与字段来源。

范围：

- 对照现有 `IndicatorService` 的 MA、MACD、RSI、BOLL、ATR、KDJ 口径差异。
- 评估 MyTT 的 `REF`、`CROSS`、`COUNT`、`EVERY`、`HHV`、`LLV`、`SMA` 等公式函数是否适合抽成内部兼容层。
- 输出精度、性能、依赖、许可证和维护状态评估。

建议落点：

- `backend/app/indicators/service.py`
- `backend/app/strategy/strategies`
- `backend/tests/test_indicators.py`

验收标准：

- 现有指标测试不变。
- 已落地指标保有固定样本测试，空数据和历史不足时返回明确不足状态。
- spike 文档能明确回答“是否引入 MyTT、为什么不引入、当前内部兼容层覆盖到哪里”。
- 不因引入 MyTT 改变现有策略信号口径。

不做范围：

- 不直接 `from MyTT import *` 污染命名空间。
- 不把外部单文件源码复制进主业务目录。
- 不允许用户在线提交任意通达信公式并执行。
- 不承诺与所有行情软件逐 tick 完全一致，只要求日线研究口径可解释。

## Phase 4：纸面交易事件化与风控前置

目标：吸收 vnpy 的事件驱动和订单状态机优势，但保持项目本地纸面交易定位。

当前状态：`Phase 4` 已完成收口。订单状态机、风控前置、统一事件链、回测风险解释统一，以及复盘页 / AI 页的事件链上下文展示均已落地；当前验收重点转为回归验证、文档同步和工作树整理，而不再是补主体能力。

已完成：

- `OrderStatus` 已扩展并收敛到统一状态迁移，支持 `accepted`、`expired`，非法迁移会被拒绝。
- 已新增 `OrderEvent` 与统一 `EventLog`，可记录 `STRATEGY_SIGNAL -> RISK_DECISION -> ORDER_EVENT -> TRADE_EXECUTION -> POSITION_CHANGE -> EQUITY_SNAPSHOT` 事件链。
- 风控已标准化为 `RiskCheckResult` / `RiskEvaluationResult`，支持规则 ID、严重级别、建议动作、解释文案和规则版本。
- 已提供 `GET /api/v1/reporting/events`，支持按 `strategy_run_id`、`order_id`、`correlation_id` 等维度查询事件链。
- AI agent 已支持只读加载事件事实，可通过 `strategy_run_id`、`order_id`、`correlation_id` 获取上下文解释素材。
- 回测链路现已统一补齐 `risk_rule_version`、`risk_decision`、`rejection_reason`、`risk_checks`、`risk_evaluation`，与纸面下单共享 `RiskEvaluationResult` 解释结构。
- 前端复盘页现已直接复用 `/api/v1/reporting/events` 展示完整事件链，AI 页也会显示事件链上下文或明确降级原因。
- 回测结果页已展示回测风控版本、决策分布和交易级风控字段，便于核对回测 / 纸面交易口径一致性。

### 4.1 订单状态机收敛

当前状态：已完成收口。

范围：

- 明确订单状态转移：创建、风控检查、接受、部分成交、全部成交、撤单、拒单、过期。
- 所有状态转移记录原因、时间、触发来源、风险规则版本。
- 限价单和市价单使用统一生命周期。

建议落点：

- `backend/app/models/order.py`
- `backend/app/trading/service.py`
- `backend/app/trading/matcher.py`

验收标准：

- 非法状态转移被拒绝。
- 撤单、拒单、成交都有明确事件记录。
- 现有订单测试全部通过并补充状态转移测试。

已完成实现说明：

- `backend/app/models/order.py` 已定义允许状态迁移集合，并通过 `Order.transition_to()` 执行迁移校验。
- `backend/app/trading/service.py` 已在下单、撤单、撮合成交等路径统一记录 `OrderEvent` 与 `ORDER_EVENT` 事件日志。
- `accepted`、`expired` 已进入订单状态与事件类型枚举，限价单和市价单共用统一生命周期模型。

不做范围：

- 不接真实交易网关。
- 不做跨进程订单撮合引擎。

### 4.2 风控前置与解释增强

当前状态：已完成收口，回测侧也已接入统一解释结构。

范围：

- 把风控检查结果标准化为规则 ID、严重级别、建议动作、解释文案。
- 当前实现以 `PASS/WARN/REJECT` 作为正式风险决策，其中 `WARN` 覆盖软警告场景；若后续确需引入“人工确认”中间态，应作为新增需求单独澄清，不在本阶段扩展实现。
- 回测、策略运行、纸面下单共用风控解释结构。

建议落点：

- `backend/app/risk/service.py`
- `backend/app/risk/versioning.py`
- `backend/app/trading/service.py`

验收标准：

- 每条拒单都有可展示原因和规则版本。
- 策略自动纸面下单不能绕过风控。
- 测试覆盖硬拒绝、软警告和通过场景。

已完成实现说明：

- `backend/app/schemas/risk.py` 已提供 `RiskCheckResult`、`RiskEvaluationResult`、`RiskDecision`、`RiskSeverity`。
- `backend/app/risk/service.py` 已输出规则 ID、严重级别、建议动作、阈值、实际值、解释文案与规则版本。
- `backend/app/trading/service.py` 已在手工下单和策略自动纸面下单链路统一消费 `RiskEvaluationResult`，并将结果写入订单响应与事件日志。
- `backend/app/backtest/service.py` 已在回测事件 / 成交 / 汇总中统一输出 `risk_rule_version`、`risk_decision`、`rejection_reason`、`risk_checks`、`risk_evaluation`，并与纸面交易共享标准 reason code 解释口径。
- `frontend/src/views/BacktestResultView.vue` 已把回测风控版本、决策分布和交易级风险字段展示出来，方便前端验收一致性。

不做范围：

- 不让 AI 自动覆盖风控结论。
- 不做复杂机构级合规系统。

### 4.3 事件日志与复盘联动

当前状态：已完成收口，后端查询、前端事件链展示和 AI 只读事实加载均已打通。

范围：

- 记录策略信号、风控判断、订单状态、成交、持仓变化、权益快照之间的关联链路。
- 复盘页可展示“为什么产生这笔交易”。
- AI 分析只能读取事件链做解释，不能修改事件事实。

建议落点：

- `backend/app/models` 新增或复用审计模型
- `backend/app/reporting`
- `backend/app/ai`

验收标准：

- 一笔由策略触发的纸面交易可以追溯到策略运行记录和风控结果。
- 手工下单和策略下单均有事件链。
- 缺失链路时显示明确降级原因。

已完成实现说明：

- `backend/app/models/event_log.py`、`backend/app/reporting/event_log_service.py` 已提供统一事件日志模型和查询服务。
- `backend/app/api/reporting.py` 已开放 `/api/v1/reporting/events` 查询接口。
- `backend/app/strategy/service.py`、`backend/app/trading/service.py`、`backend/app/reporting/service.py` 已把策略信号、风控决策、订单事件、成交、持仓变化、权益快照串到同一 `correlation_id` / `strategy_run_id` 上。
- `backend/app/ai/data_loader.py` 与 `backend/app/ai/service.py` 已把事件链作为 AI 只读上下文事实载入。
- `frontend/src/views/AnalysisView.vue` 已直接复用 `/api/v1/reporting/events`，按 `correlation_id / order_id / strategy_run_id` 聚合并展示事件链。
- `frontend/src/views/AiAnalysisView.vue` 已展示事件链上下文，缺失链路时会明确显示降级原因，而不是静默空白。

不做范围：

- 不做不可篡改审计账本。
- 不做监管报送。

## Phase 5：研究体验与前端呈现

目标：吸收教学项目和研究框架的低门槛体验，降低用户理解策略、数据和回测结果的成本。

### 5.1 一页式策略研究报告

当前状态：`5.1` 已完成收口。单标的回测 `summary.research_report` 与 `POST /api/v1/backtest/research-report` 统一返回同一份 Markdown 研究报告；回测结果页已同步展示数据源、样本、成本、交易约束、质量警示和“该回测不能说明什么”的结构化摘要，并覆盖空样本、零成交、provider 降级等醒目提示。当前决策口径保持不变：仅保留 Markdown 报告与下载，不新增独立 JSON 报告合同。

范围：

- 汇总策略参数、样本区间、数据源质量、交易约束、成本假设、绩效指标、风险提示。
- 明确展示“该回测不能说明什么”。
- 保留 Markdown 预览与下载；不新增独立 JSON 报告合同。

建议落点：

- `backend/app/backtest/service.py`
- `backend/app/reporting`
- `frontend/src/views/BacktestResultView.vue`

验收标准：

- 回测报告包含数据源、成本模型、交易约束版本。
- 数据不足或质量差时有醒目提示。
- 导出内容可复现核心结论。

不做范围：

- 不做 PDF 排版系统。
- 不生成投资建议。

### 5.2 新手策略样例与解释

当前状态：`5.2` 已完成当前阶段最小闭环。策略中心模板区已返回六类模板，并支持“从模板创建”填充策略表单；模板区已具备逻辑说明、失败场景/风险提示教学面板、与当前表单值对齐的参数解释与边界摘要，以及静态教学样例。模板区现已支持直达现有分析页，并带着模板参数进入单标的回测；教学样例继续采用前端静态文案映射，不新增后端样例合同。

范围：

- 为每个内置策略补充“策略逻辑、适用市场、失败场景、参数解释”。
- 增加少量教学样例数据和回测入口。
- UI 文案保持审慎，强调模拟和研究。

建议落点：

- `backend/app/strategy/service.py`
- `frontend/src/views/StrategiesView.vue`
- `README.md` 或 `docs`

验收标准：

- 用户能从模板说明理解策略风险。
- 策略参数边界和默认值一致。
- 前端构建通过。

不做范围：

- 不复制外部教程内容。
- 不提供“稳赚策略”。

## 推荐实施顺序

1. Provider 能力矩阵与健康评分。
2. AData / efinance 只读 spike 与评估报告。
3. 回测 A 股交易约束模型。
4. 成交容量与滑点模型。
5. 策略输出协议标准化。
6. 订单状态机和风控解释标准化。
7. 因子研究基础接口。
8. 一页式研究报告和前端解释增强。

## 第一批可执行任务包

### Task A：Provider 能力矩阵

交付物：

- provider capability dataclass/schema。
- API 返回当前 provider 能力。
- 后端测试。

验证：

- `pytest backend/tests/test_market_service.py backend/tests/test_market_quality.py -q`

### Task B：A 股回测交易约束

交付物：

- T+1、停牌、涨跌停、100 股交易单位约束。
- 回测事件中记录拒绝/延迟成交原因。
- 后端回测测试。

验证：

- `pytest backend/tests/test_backtest.py backend/tests/test_backtest_portfolio.py -q`

### Task C：策略输出协议兼容层

交付物：

- 新策略信号结构。
- 旧 dict 输出兼容适配器。
- 迁移 1 个简单策略作为样例。

验证：

- `pytest backend/tests/test_strategies.py backend/tests/test_backtest.py -q`

## 风险清单

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 新数据源不稳定 | 影响研究结果可信度 | 只读 spike、健康评分、缓存、字段缺失提示 |
| 回测约束增强导致历史结果变化 | 用户误解为回归 | 报告中标记回测引擎版本和成本假设 |
| 策略协议升级破坏旧策略 | 策略运行失败 | 保留兼容层，逐个迁移 |
| 事件化改造扩大 diff | 维护成本上升 | 先抽象状态和结果结构，再改存储 |
| 前端解释过度承诺 | 合规和误导风险 | 统一使用研究/模拟/风险提示文案 |

## Go / No-Go 标准

新外部依赖只有满足以下条件才进入正式集成：

- 许可证允许当前项目使用。
- 维护状态可接受，近年仍有更新或接口足够简单可自行兜底。
- 字段覆盖能填补明确缺口，而不是与现有 provider 高度重复。
- 失败时不影响主链路。
- 有缓存和限频策略。
- 有最小测试覆盖。
- 有明确回滚方式。

## 成功标准

完成本计划前半部分后，Leek Trader 应达到：

- 数据源能力清晰、健康状态可见、数据质量可解释。
- 回测更符合 A 股真实交易约束。
- 策略信号能在回测、纸面交易、复盘之间复用。
- 纸面订单生命周期更清晰，风控解释更标准。
- 用户能通过一页报告理解策略表现、数据风险和适用边界。
