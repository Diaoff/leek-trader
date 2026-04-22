# Frontend Refactoring Plan

## Analysis Summary

### stock-simulator 架构优势:
1. **完善的 Pinia 状态管理**: 使用集中的 store 管理业务逻辑和数据流
2. **组件化设计**: 清晰的数据流向和状态管理
3. **丰富的 getters/actions**: 计算属性和操作方法分离
4. **完整的业务逻辑封装**: 买卖操作、持仓更新等在 store 中处理

### frontend 当前问题:
1. **状态管理薄弱**: 只有 app.ts 一个简单 store，业务逻辑分散在各个 view 中
2. **缺少可复用组件**: 每个 view 都是独立的大组件，没有拆分子组件
3. **缺少 composables**: 没有利用 Vue 3 的组合式 API 特性
4. **错误处理分散**: 每个组件单独处理错误，缺少统一机制
5. **类型定义分散**: API 类型定义混在 API 文件中

## 重构方案

### 第一阶段: 完善状态管理 (Pinia Stores)

#### 1.1 创建 Portfolio Store
- 路径: `src/stores/portfolio.ts`
- 功能: 管理持仓、账户摘要
- 从 PortfolioView 和 DashboardView 提取业务逻辑
- 包含 actions: fetchPortfolioData, refreshPositions
- 包含 getters: totalEquity, positionCount, etc.

#### 1.2 创建 Order Store  
- 路径: `src/stores/orders.ts`
- 功能: 管理订单列表、订单操作
- 从 PortfolioView 提取订单相关逻辑
- 包含 actions: fetchOrders, createOrder, cancelOrder, matchOrders
- 包含 getters: pendingOrders, recentOrders

#### 1.3 创建 Market Store
- 路径: `src/stores/market.ts`
- 功能: 管理行情数据、自选股
- 从 MarketView 提取行情相关逻辑
- 包含 actions: fetchQuotes, fetchWatchlists, addToWatchlist, removeFromWatchlist
- 包含 getters: watchlistCount, activeQuotes

#### 1.4 创建 Strategy Store
- 路径: `src/stores/strategies.ts`
- 功能: 管理策略数据
- 从 StrategiesView 提取策略相关逻辑
- 包含 actions: fetchStrategies
- 包含 getters: activeStrategies

#### 1.5 创建 Dashboard Store
- 路径: `src/stores/dashboard.ts`
- 功能: 管理仪表盘聚合数据
- 从 DashboardView 提取仪表盘数据逻辑
- 包含 actions: loadDashboardData, refreshEquityCurve
- 包含 getters: metricCards, recentActivity

### 第二阶段: 创建 Composables

#### 2.1 useLoading
- 路径: `src/composables/useLoading.ts`
- 功能: 统一加载状态管理

#### 2.2 useErrorHandler
- 路径: `src/composables/useErrorHandler.ts`
- 功能: 统一错误处理，集成 ElMessage

#### 2.3 usePolling
- 路径: `src/composables/usePolling.ts`
- 功能: 定时轮询数据更新

#### 2.4 usePagination
- 路径: `src/composables/usePagination.ts`
- 功能: 列表分页逻辑（为未来扩展预留）

### 第三阶段: 提取可复用组件

#### 3.1 MetricCard
- 路径: `src/components/MetricCard.vue`
- 功能: 指标卡片组件，用于 Dashboard 和 Portfolio 的指标展示

#### 3.2 DataTable
- 路径: `src/components/DataTable.vue`
- 功能: 封装 el-table 的通用表格组件，带加载状态和空数据提示

#### 3.3 StatusTag
- 路径: `src/components/StatusTag.vue`
- 功能: 统一的状态标签组件（订单状态、策略信号等）

#### 3.4 PageHeader
- 路径: `src/components/PageHeader.vue`
- 功能: 统一的页面标题和副标题组件

#### 3.5 ErrorAlert
- 路径: `src/components/ErrorAlert.vue`
- 功能: 统一的错误提示组件

#### 3.6 ChartCard
- 路径: `src/components/ChartCard.vue`
- 功能: 封装 ECharts 的图表卡片组件

### 第四阶段: 优化 API 层

#### 4.1 统一类型定义
- 路径: `src/types/`
- 移动所有 API 接口定义到独立的 types 文件
- 创建 `index.ts` 统一导出

#### 4.2 增强 API Client
- 添加请求/响应拦截器
- 统一错误处理
- 添加请求超时重试机制
- 添加请求取消功能

#### 4.3 API 模块化
- 按业务模块重新组织 API 文件
- 统一 API 函数命名规范

### 第五阶段: 重构 Views

#### 5.1 DashboardView
- 使用新的 stores 和 composables
- 拆分子组件: DashboardMetrics, DashboardCharts, DashboardTables
- 简化组件逻辑，专注于 UI 展示

#### 5.2 MarketView
- 使用 Market Store
- 拆分子组件: WatchlistPanel, QuotesTable, SearchBar
- 优化数据加载流程

#### 5.3 PortfolioView
- 使用 Portfolio Store 和 Order Store
- 拆分子组件: OrderForm, OrderTable, PositionTable, PortfolioSummary
- 简化表单提交逻辑

#### 5.4 StrategiesView
- 使用 Strategy Store
- 拆分子组件: StrategyTable
- 保持简洁

### 第六阶段: 其他优化

#### 6.1 路由优化
- 添加路由守卫
- 添加路由懒加载
- 优化路由配置结构

#### 6.2 环境变量
- 创建 `.env.example` 文件
- 统一环境变量管理
- 添加类型定义

#### 6.3 性能优化
- 组件懒加载
- 路由代码分割
- 图表组件按需加载（已有）

#### 6.4 代码规范
- 统一命名规范
- 统一导入顺序
- 添加必要的注释

### 重构后目录结构

```
frontend/
├── src/
│   ├── api/                    # API 调用层
│   │   ├── client.ts           # Axios 实例配置
│   │   ├── accounts.ts
│   │   ├── orders.ts
│   │   ├── portfolio.ts
│   │   ├── positions.ts
│   │   ├── quotes.ts
│   │   ├── strategies.ts
│   │   ├── watchlists.ts
│   │   ├── reporting.ts
│   │   └── health.ts
│   ├── assets/                 # 静态资源
│   ├── components/             # 可复用组件
│   │   ├── MetricCard.vue
│   │   ├── DataTable.vue
│   │   ├── StatusTag.vue
│   │   ├── PageHeader.vue
│   │   ├── ErrorAlert.vue
│   │   └── ChartCard.vue
│   ├── composables/            # 组合式函数
│   │   ├── useLoading.ts
│   │   ├── useErrorHandler.ts
│   │   └── usePolling.ts
│   ├── stores/                 # Pinia 状态管理
│   │   ├── app.ts
│   │   ├── portfolio.ts
│   │   ├── orders.ts
│   │   ├── market.ts
│   │   ├── strategies.ts
│   │   └── dashboard.ts
│   ├── types/                  # TypeScript 类型定义
│   │   ├── account.ts
│   │   ├── order.ts
│   │   ├── portfolio.ts
│   │   ├── position.ts
│   │   ├── quote.ts
│   │   ├── strategy.ts
│   │   ├── watchlist.ts
│   │   ├── reporting.ts
│   │   ├── health.ts
│   │   └── index.ts
│   ├── views/                  # 页面视图
│   │   ├── DashboardView.vue
│   │   ├── MarketView.vue
│   │   ├── PortfolioView.vue
│   │   └── StrategiesView.vue
│   ├── router/
│   │   └── index.ts
│   ├── utils/
│   │   ├── format.ts
│   │   └── http.ts
│   ├── App.vue
│   ├── main.ts
│   ├── env.d.ts
│   └── styles.css
└── ...
```

## 实施顺序

1. 创建 types/ 目录并移动类型定义
2. 增强 API client (拦截器、错误处理)
3. 创建 composables (useLoading, useErrorHandler)
4. 创建可复用组件 (MetricCard, DataTable, StatusTag 等)
5. 创建 Pinia stores (portfolio, orders, market, strategies, dashboard)
6. 重构 Views (按复杂度从低到高: Strategies → Market → Portfolio → Dashboard)
7. 优化路由配置
8. 添加环境变量配置
9. 测试验证

## 注意事项

- 保持核心功能不变
- 确保 TypeScript 类型安全
- 保持现有 API 接口兼容
- 分步骤实施，每步验证
- 不引入新的外部依赖
- 保持 Element Plus 组件库的一致性
