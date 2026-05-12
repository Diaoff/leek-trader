# 发布前质量闸门清单

本清单用于第九批之后的发布前收口。目标是确认前八批能力在发布前可回归、权限边界可解释、文档状态一致；不引入新的前端测试依赖，不扩展业务功能。

## 1. 范围与未提交改动

- 执行 `git status --short`，确认未提交改动只包含当前批次目标范围。
- 执行 `git diff --stat`，按模块复核改动量：后端测试、前端路由/权限、文档、运行治理、风控版本。
- 对高风险模块执行局部 diff 复核：
  - 风控版本：`backend/tests/test_risk_versioning.py`、偏好与订单风控相关服务。
  - 监控权限：`backend/app/api/monitoring.py`、`backend/app/core/auth.py`。
  - 前端路由：`frontend/src/router/index.ts`、`frontend/src/App.vue`、`frontend/src/stores/session.ts`。
  - 文档状态：`README.md`、`docs/plan.md`、`docs/release-checklist.md`。
- 不在本清单批次内处理无关重构、样式翻新、新依赖或新页面。

## 2. 后端回归

优先运行与本批相关的监控、风控、权限链路测试：

```bash
pytest backend/tests/test_monitoring.py backend/tests/test_risk_versioning.py backend/tests/test_orders.py -q
```

发布前完整后端回归：

```bash
pytest
```

验收点：

- 监控接口仍要求超级用户权限，`get_current_superuser` 是最终后端权限边界。
- 风控规则版本接口返回当前规则摘要、阈值快照、来源和说明。
- 订单风控结果携带 `risk_rule_version`，拒单原因仍可解释。
- 交易、持仓、账户一致性测试无新增失败。

## 3. 前端构建与路由权限

当前前端没有 Vitest/Playwright 等自动化测试框架；本清单不为单个路由守卫新增依赖。发布前使用构建校验与最小手动验证覆盖 `/monitoring`。

构建检查：

```bash
cd frontend && npm run build
```

`/monitoring` 最小权限验证：

1. 未登录用户访问 `/monitoring`：应跳转到 `/login`。
2. 普通登录用户访问 `/monitoring`：前端路由守卫调用当前用户信息后，应重定向到 `/`。
3. 普通登录用户查看侧边栏：不应暴露“运行治理”入口。
4. 超级用户访问 `/monitoring`：应进入运行治理页，并能查看核心指标、异步任务摘要、最新日志和系统统计。
5. 直接调用监控治理 API：普通用户请求 `/api/v1/monitoring/operations/metrics`、`/api/v1/monitoring/async-tasks/summary`、`/api/v1/monitoring/logs/latest` 等接口应返回 403。

验收点：

- `frontend/src/router/index.ts` 的 `/monitoring` 路由保留 `requiresSuperuser: true`。
- `frontend/src/App.vue` 的运行治理入口只对超级用户暴露。
- `frontend/src/stores/session.ts` 的 `isSuperuser` 来自后端当前用户信息，不从本地硬编码。
- 即使前端守卫失效，后端 `get_current_superuser` 仍阻止普通用户访问监控治理接口。

## 4. 运行治理检查

启动本地服务后检查：

```bash
./start.sh --with-async --skip-frontend
bash ./async-health.sh
```

运行治理页与接口应覆盖：

- 核心运行指标：行情新鲜度、策略执行、交易成功率。
- 异步任务摘要：调度周期、重试策略、幂等 key 示例、统计来源。
- 最新日志：读取 `LOG_DIR` 下的应用日志。
- 系统资源：CPU、内存、磁盘等本机统计。
- 健康状态：API、数据库、Redis 状态与降级说明。

边界：当前不要求 Prometheus/Grafana、长期指标归档、告警阈值管理或生产级审计留存。

## 5. 文档一致性检查

复核以下文档描述一致：

- `README.md`：功能概览、验证命令、页面/API 入口。
- `docs/plan.md`：当前能力地图、长期维护规则、Test Plan。
- `docs/operations-metrics.md`：运行指标口径与边界。
- `docs/logging-audit.md`：日志分层与审计范围。
- `docs/release-checklist.md`：发布前质量闸门。

验收点：

- 已完成能力不再出现在“当前剩余缺口”中。
- 运行治理页、风控规则版本追溯、发布验证入口均有说明。
- 后续批次规则明确要求先声明增量目标、风险点、验收标准和不做范围。
- 文档没有承诺当前未实现的生产级能力、真实交易、多租户 SaaS 或自动化前端测试。

## 6. 发布判定

满足以下条件才可判定通过：

- 后端相关测试通过，或已记录明确的非本批阻塞原因。
- 前端生产构建通过。
- `/monitoring` 权限最小验证完成，且后端 403 边界有效。
- `README.md`、`docs/plan.md`、`docs/release-checklist.md` 对能力、边界和验证命令描述一致。
- `git diff --stat` 与模块化 diff 确认改动范围未越界。
