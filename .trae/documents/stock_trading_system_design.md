# 股市交易系统设计文档

## 1. 系统概述

### 1.1 项目定位
股票模拟交易系统MVP，专注于行情、策略、风控、模拟交易和盈亏分析的核心链路。

### 1.2 核心功能模块
保留的股市相关核心模块：
- **行情监控** - 实时股票行情数据
- **策略管理** - 交易策略的配置与执行
- **持仓管理** - 持仓分析与调整
- **订单交易** - 模拟交易订单执行
- **盈亏分析** - 收益统计与风险控制
- **资产追踪** - 总资产、可用资金、持仓市值、浮动盈亏

## 2. 前端架构设计

### 2.1 技术栈
- Vue 3 + Composition API
- TypeScript
- Element Plus UI组件库
- Tailwind CSS
- Pinia 状态管理
- Vue Router
- ECharts 数据可视化

### 2.2 页面结构

```
src/
├── views/
│   ├── DashboardView.vue      # 仪表盘（系统状态、关键指标）
│   ├── MarketView.vue         # 行情页面
│   ├── StrategiesView.vue     # 策略管理
│   └── PortfolioView.vue      # 持仓管理
├── api/
│   ├── portfolio.ts          # 资产相关API
│   ├── positions.ts          # 持仓相关API
│   ├── orders.ts            # 订单相关API
│   ├── quotes.ts            # 行情相关API
│   ├── strategies.ts        # 策略相关API
│   └── reporting.ts         # 报表相关API
├── stores/
│   └── app.ts               # 全局状态管理
├── router/
│   └── index.ts             # 路由配置
└── styles/
    └── main.css            # 全局样式
```

### 2.3 Dashboard布局设计

#### 左侧状态栏（系统运行状态）
- **运行状态指示器** - 运行中/已停止
- **运行时间** - 系统运行时长
- **今日任务数** - 当日交易任务统计
- **下次启动时间** - 下次策略执行时间
- **今日交易追踪** - 交易执行时间线

#### 主内容区
1. **财务指标卡片** (4列网格)
   - 总资产 + 总收益率
   - 可用资金 + 占比
   - 持仓市值 + 占比
   - 浮动盈亏 + 收益率

2. **系统状态面板**
   - 任务统计：失败任务、执行中、排队、挂起
   - 交易统计：今日成交、历史成交、排队日志
   - 任务类型卡片：
     - 交易提醒（成功率）
     - 生活提醒（成功率）
     - 扩展数据（成功率）
     - 巡检任务（成功率）
     - 其他任务（成功率）

#### 右侧状态栏
1. **关键状态**
   - 推送前持仓（0/8只）
   - 当前持仓（3只）
   - 当前订单（0）
   - 今日成交（0笔）
   - 分级阶段
   - 总资产

## 3. 后端架构设计

### 3.1 技术栈
- FastAPI
- SQLAlchemy ORM
- PostgreSQL数据库
- Celery 异步任务
- Pydantic 数据验证

### 3.2 模块划分

```
backend/app/
├── api/                    # API路由层
│   ├── accounts.py         # 账户管理
│   ├── orders.py           # 订单管理
│   ├── positions.py        # 持仓管理
│   ├── portfolio.py        # 资产组合
│   ├── quotes.py           # 行情数据
│   ├── reporting.py        # 报表统计
│   ├── strategies.py       # 策略管理
│   ├── trading.py          # 交易执行
│   └── health.py           # 健康检查
├── models/                 # 数据模型
│   ├── account.py          # 账户模型
│   ├── order.py            # 订单模型
│   ├── position.py         # 持仓模型
│   ├── trade.py            # 成交模型
│   ├── strategy.py         # 策略模型
│   ├── strategy_run.py     # 策略运行记录
│   ├── equity_snapshot.py   # 权益快照
│   └── cash_flow.py        # 资金流水
├── schemas/                 # Pydantic模型
│   ├── account.py
│   ├── order.py
│   ├── position.py
│   ├── portfolio.py
│   ├── quote.py
│   ├── reporting.py
│   └── strategy.py
├── services/                # 业务逻辑层
│   ├── portfolio/
│   ├── positions/
│   ├── orders/
│   ├── trading/
│   ├── reporting/
│   ├── strategy/
│   ├── market/
│   └── risk/
├── tasks/                  # Celery异步任务
│   ├── trading_tasks.py
│   ├── market_tasks.py
│   └── strategy_tasks.py
└── core/                   # 核心配置
    ├── config.py
    ├── db.py
    └── celery_app.py
```

## 4. 数据模型设计

### 4.1 核心实体

#### Account (账户)
```python
class Account:
    id: int
    name: str                    # 账户名称
    account_type: str            # 账户类型 (simulated/live)
    total_equity: float          # 总资产
    available_cash: float        # 可用资金
    market_value: float          # 持仓市值
    unrealized_pnl: float        # 浮动盈亏
    created_at: datetime
    updated_at: datetime
```

#### Position (持仓)
```python
class Position:
    id: int
    account_id: int
    symbol: str                  # 股票代码
    name: str                    # 股票名称
    quantity: int                # 持仓数量
    avg_cost: float              # 平均成本
    current_price: float        # 当前价格
    market_value: float          # 市值
    unrealized_pnl: float        # 浮动盈亏
    unrealized_pnl_pct: float     # 盈亏比例
```

#### Order (订单)
```python
class Order:
    id: int
    account_id: int
    symbol: str                  # 股票代码
    name: str                    # 股票名称
    direction: str               # 买入/卖出 (buy/sell)
    order_type: str              # 订单类型 (market/limit)
    price: float                 # 订单价格
    quantity: int                # 订单数量
    filled_quantity: int         # 成交数量
    status: str                  # 订单状态
    created_at: datetime
    updated_at: datetime
```

#### Trade (成交)
```python
class Trade:
    id: int
    order_id: int
    account_id: int
    symbol: str                  # 股票代码
    direction: str               # 买入/卖出
    price: float                 # 成交价格
    quantity: int               # 成交数量
    amount: float                # 成交金额
    commission: float            # 手续费
    traded_at: datetime
```

#### Strategy (策略)
```python
class Strategy:
    id: int
    name: str                    # 策略名称
    description: str             # 策略描述
    strategy_type: str           # 策略类型 (MACD/MA/自定义)
    parameters: dict             # 策略参数
    status: str                  # 启用/禁用
    created_at: datetime
    updated_at: datetime
```

#### EquitySnapshot (权益快照)
```python
class EquitySnapshot:
    id: int
    account_id: int
    total_equity: float          # 总资产
    available_cash: float        # 可用资金
    market_value: float          # 持仓市值
    unrealized_pnl: float        # 浮动盈亏
    snapshot_time: datetime
```

## 5. API接口设计

### 5.1 投资组合接口

#### GET /api/v1/portfolio/summary
获取资产摘要
```json
{
  "total_equity": 20130.04,
  "available_cash": 9944.04,
  "market_value": 10186.00,
  "unrealized_pnl": 0.00,
  "cumulative_return": 0.1567
}
```

#### GET /api/v1/portfolio/equity-curve
获取资产曲线
```json
{
  "data": [
    {"label": "2024-01-01", "total_equity": 10000},
    {"label": "2024-01-02", "total_equity": 10200}
  ]
}
```

### 5.2 持仓接口

#### GET /api/v1/positions
获取持仓列表
```json
{
  "positions": [
    {
      "id": 1,
      "symbol": "600519",
      "name": "贵州茅台",
      "quantity": 100,
      "avg_cost": 1800.00,
      "current_price": 1850.00,
      "market_value": 185000.00,
      "unrealized_pnl": 5000.00,
      "unrealized_pnl_pct": 2.78
    }
  ]
}
```

### 5.3 订单接口

#### GET /api/v1/orders
获取订单列表
```json
{
  "orders": [
    {
      "id": 1,
      "symbol": "600519",
      "name": "贵州茅台",
      "direction": "buy",
      "order_type": "market",
      "price": 1850.00,
      "quantity": 100,
      "filled_quantity": 100,
      "status": "filled",
      "created_at": "2024-01-15 10:00:00"
    }
  ]
}
```

#### POST /api/v1/orders
创建订单
```json
{
  "symbol": "600519",
  "direction": "buy",
  "order_type": "market",
  "quantity": 100
}
```

### 5.4 行情接口

#### GET /api/v1/quotes/{symbol}
获取单个股票行情
```json
{
  "symbol": "600519",
  "name": "贵州茅台",
  "current_price": 1850.00,
  "change": 15.00,
  "change_pct": 0.82,
  "open": 1835.00,
  "high": 1860.00,
  "low": 1830.00,
  "volume": 3500000,
  "amount": 6450000000.00,
  "update_time": "2024-01-15 15:00:00"
}
```

#### GET /api/v1/quotes
批量获取股票行情
```json
{
  "quotes": [
    {"symbol": "600519", "name": "贵州茅台", "current_price": 1850.00},
    {"symbol": "000858", "name": "五粮液", "current_price": 180.00}
  ]
}
```

### 5.5 策略接口

#### GET /api/v1/strategies
获取策略列表
```json
{
  "strategies": [
    {
      "id": 1,
      "name": "MACD策略",
      "description": "基于MACD指标的趋势跟踪策略",
      "strategy_type": "MACD",
      "parameters": {"fast": 12, "slow": 26, "signal": 9},
      "status": "active"
    }
  ]
}
```

#### POST /api/v1/strategies
创建策略

#### PUT /api/v1/strategies/{id}
更新策略

### 5.6 报表接口

#### GET /api/v1/reporting/summary
获取报表摘要
```json
{
  "trade_count": 50,
  "realized_pnl": 1500.00,
  "win_rate": 0.65,
  "cumulative_return": 0.1567,
  "profit_factor": 1.85,
  "max_drawdown": 0.12,
  "avg_win": 500.00,
  "avg_loss": 300.00
}
```

#### GET /api/v1/reporting/monthly
获取月度统计
```json
{
  "monthly": [
    {
      "period": "2024-01",
      "trade_count": 15,
      "realized_pnl": 500.00,
      "ending_equity": 20500.00
    }
  ]
}
```

#### GET /api/v1/reporting/yearly
获取年度统计

## 6. 已移除功能模块

以下模块已从系统中移除：
- ❌ 站点管理
- ❌ 监控进度
- ❌ 今日计划
- ❌ 内部知识
- ❌ 实时数据
- ❌ 配置管理

## 7. 系统扩展性设计

### 7.1 策略扩展
- 支持自定义策略插件
- 策略参数可配置
- 支持策略回测

### 7.2 数据源扩展
- 支持多个行情数据源（Sina、EastMoney、AKShare）
- 数据源可插拔架构

### 7.3 风控扩展
- 风险指标实时计算
- 止损止盈自动触发
- 仓位管理规则

### 7.4 报表扩展
- 自定义统计维度
- 导出功能（Excel、PDF）
- 自定义时间范围
