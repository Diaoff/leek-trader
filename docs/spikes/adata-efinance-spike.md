# AData / efinance 只读 Spike 评估

## 结论

- `adata`：Go for research-only integration。
- `efinance`：No-Go for current Phase 1 scope，保持 deferred。
- 当前保留 `backend/scripts/spike_data_providers.py` 作为只读 spike 输出，用于记录字段覆盖、失败模式和正式决策口径；脚本不联网、不改生产行为。

## 正式决策记录

### `adata`

- 已纳入研究辅助范围。
- 纳管边界：
  - 可用于研究接口。
  - 可用于智能选股辅助链路。
  - 可用于 provider 能力矩阵展示。
  - 不进入主行情链路。
  - 不改变行情 provider 选择优先级。
  - 不写入主行情/主历史日线表作为默认来源。
- 结论：`adopted_for_research`。

### `efinance`

- 保持 spike 结论，不接入当前生产链路。
- deferred 原因：
  - 与现有 EastMoney / Sina / Tencent 行情覆盖重叠较高。
  - 对当前 A 股主路径的增益有限。
  - 当前没有基金、行业、债券专门能力建设的已批准范围。
- 后续仅在基金、行业或债券形成明确立项时重新评估。
- 结论：`deferred`。

## 字段覆盖

| 包 | 候选字段/能力 | 当前系统内定位 | 结论 |
| --- | --- | --- | --- |
| `adata` | A 股列表、基本面、概念板块、资金流向 | 研究接口、智能选股辅助、能力矩阵展示 | 研究辅助纳管 |
| `efinance` | 东方财富封装行情、基金净值、指数、行业数据 | 仅保留 spike 结论，不接 provider registry | deferred |

## 失败模式

| 失败模式 | 影响 | 缓解 |
| --- | --- | --- |
| 网络失败 | 研究接口或 spike 返回失败 | 保持主行情链路不依赖；研究接口返回可控空结果/降级说明 |
| 字段变更 | 研究字段解析不稳定 | 通过 provider 测试和字段映射收口，接入前先固定样本 |
| 限频 | 批量研究任务不稳定 | 使用缓存、限频和可控降级，不让主链路受影响 |
| 返回空集 | 研究结论缺失 | 输出 `empty_response` / neutral result，不伪造行情数据 |
| 编码异常 | 中文字段解析失败 | 通过 parser 映射与测试固定，异常按研究失败处理 |

## 依赖与许可证

- `adata`：
  - 当前定位为研究辅助依赖，不属于核心行情主路径必需依赖。
  - 上游仓库存在许可证文件，分发前仍需再次核验具体文本与约束。
- `efinance`：
  - 当前不加入运行时依赖。
  - 公开项目信息通常标注为 MIT，正式采用前仍需再次核验许可证文本。

## 替代与回退方案

- `adata` 不可用时：
  - 研究接口返回可控空结果或研究失败状态。
  - 智能选股回退到 neutral / missing reason，不影响主行情、回测、落库链路。
- `efinance` 未接入期间：
  - 继续使用现有 EastMoney、Sina、Tencent、BaoStock 组合。
  - 如未来需要基金/行业/债券能力，再基于明确需求重开 spike。
