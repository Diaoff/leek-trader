# 日志分层与审计日志规范

Leek Trader 当前是本地单用户模拟交易系统，日志目标是支撑本地排障、回归验证和高风险操作追踪，不提供生产级 SIEM、审计审批流或合规留存能力。

## 日志分层

| 文件 | 用途 | 典型内容 |
| --- | --- | --- |
| `app.log` | 应用主日志 | API、服务、异常、健康检查 |
| `market.log` | 行情日志 | provider 请求失败、缓存/降级、行情同步 |
| `trading.log` | 交易日志 | 委托、撮合、交易执行路径 |
| `portfolio.log` | 资产日志 | 账户、持仓、资产统计 |
| `audit.log` | 审计日志 | 高风险用户操作、手动异步任务派发、重置/删除/运行操作 |

日志目录由 `LOG_DIR` 配置；未配置时默认写入仓库根目录 `logs/`。

## 审计事件格式

`audit.log` 每行是一条 JSON，字段包括：

- `timestamp`：UTC ISO 时间。
- `action`：动作名，例如 `devtools.reset_trading_state`、`async_task.dispatch`。
- `actor_id` / `actor_name`：操作者。
- `tenant_id`：当前本地租户。
- `resource_type` / `resource_id`：操作对象。
- `outcome`：`success`、`queued`、`rejected` 等。
- `details`：动作摘要，自动脱敏 `password`、`token`、`secret`、`api_key`、`cookie` 等字段。

## 当前审计范围

- 交易状态重置：记录成功与确认失败。
- 策略删除：记录策略 ID。
- 策略手动运行：记录 run ID、状态和信号。
- 手动异步任务派发：记录 task ID、任务 key、参数和幂等 key。

## 边界

- 当前不记录敏感密钥明文。
- 当前不做不可抵赖签名、远端集中采集、审计审批流或长期归档。
- 如果新增真实资金、真实券商、多人协作或生产权限，应先升级审计模型，而不是复用本地审计日志作为合规日志。
