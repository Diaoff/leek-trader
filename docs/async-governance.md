# 异步任务幂等与重试边界

本文档定义当前本地模拟交易系统中 Celery 任务的幂等、重复触发和重试边界。目标是让任务失败可重试、重复触发可解释，但不把本地 MVP 提前改造成分布式工作流平台。

## 全局规则

- Celery 基类 `ReliableTask` 对任务失败启用自动重试：指数退避、抖动、最多 3 次。
- 任务执行状态会写入 `async_task_executions`，监控接口优先展示数据库统计。
- 定时任务应优先使用调度间隔、交易时段和业务状态作为重复触发保护。
- 有业务副作用的任务必须说明副作用范围和重复触发策略。
- 本阶段不引入分布式锁、全局去重队列或工作流引擎；需要这些能力时应先证明本地保护不足。

## 任务边界

| 任务 | 幂等范围 | 重复触发策略 | 重试安全性 | 主要副作用 |
| --- | --- | --- | --- | --- |
| `refresh_market_quotes` | `symbols + scheduled` | 安全刷新 | safe | 报价缓存更新 |
| `run_smart_selection` | `run_id` 优先，其次 `tenant/user/trigger` | run 记录保护 | guarded | 智能选股运行状态与推荐快照 |
| `run_strategy_cycle` | `strategy_ids + user_id + scheduled` | 定时任务受间隔保护 | guarded | 策略运行记录，可能产生模拟委托 |
| `match_pending_orders` | pending 委托状态 | 状态流转保护 | safe | 委托状态、成交、持仓、流水 |
| `monitor_position_guards` | active 持仓 guard 状态 | 状态流转保护 | guarded | guard 触发委托、持仓保护状态 |

## 使用说明

- 监控摘要接口 `/api/v1/monitoring/async-tasks/summary` 会返回每个任务的 `retry_policy`、`governance` 和 `idempotency_key_example`。
- `idempotency_key_example` 只用于可观测和排查，不作为强制去重锁。
- 手动触发策略运行可能刻意生成新的运行记录；不要把所有手动任务强行去重。
- 撮合与持仓 guard 类任务必须依赖订单/持仓状态判断，不能只依赖 Celery `task_id`。
