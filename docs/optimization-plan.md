# Leek Trader 模拟交易功能优化计划

> 基于GitHub量化交易项目梯队评测，针对Leek Trader当前不足，制定分阶段优化方案
>
> 生成日期：2026-05-09

---

## 一、参考项目梯队评测总结

### 1.1 梯队分类概览

| 梯队 | 代表项目 | Stars | 核心借鉴价值 |
|------|----------|-------|-------------|
| **10k+ Stars** | vnpy(36.2k)、QUANTAXIS(10k+) | 回测引擎架构、多账户体系、事件驱动设计 |
| **3k-10k Stars** | AData(3.8k)、MyTT(2.3k) | 免费数据源补充、技术指标公式移植 |
| **2025新锐** | TradingAgents(65k)、OSKHQuant | 多智能体AI分析、可视化回测方案 |

---

## 二、梯队项目详细评测

### 🏆 第一梯队：10k+ Stars（成熟框架）

---

#### 2.1.1 VeighNa (vnpy) — 国内第一量化框架

| 项目信息 | 详情 |
|---------|------|
| **GitHub URL** | https://github.com/vnpy/vnpy |
| **Star数量** | **36.2k** |
| **最新版本** | 4.3.0 (2025年12月) |
| **开源协议** | MIT License |

**核心架构：**
```
┌────────────────────────────────────────────────────────────┐
│                    VeighNa Studio (IDE)                     │
└────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────┐
│                     MainEngine                              │
│                  (事件驱动引擎)                              │
└──────────┬─────────────────────────────────────┬───────────┘
           │                                     │
    ┌──────▼──────┐                     ┌───────▼───────┐
    │  Gateway    │                     │     App       │
    │ (交易接口)   │                     │  (应用模块)    │
    └──────┬──────┘                     └───────┬───────┘
           │                                     │
    ┌──────┴──────┐                     ┌───────┴───────┐
    │CTP/XTP/IB...│                     │CTA/Alpha/     │
    │20+接口      │                     │Portfolio...   │
    └─────────────┘                     └───────────────┘
```

**核心借鉴价值：**

| 借鉴方向 | 具体内容 |
|----------|----------|
| **回测引擎架构** | CtaBacktester图形界面回测、支持Tick/K线级、内置滑点手续费模型 |
| **多账户体系** | PortfolioManager子账户管理、委托成交记录、仓位跟踪、盈亏统计 |
| **事件驱动设计** | EventEngine解耦模块通信、异步事件处理、实时行情推送 |
| **AI能力(4.0新增)** | vnpy.alpha模块：dataset/model/strategy/lab分层ML工作流 |

**对Leek Trader的可借鉴点：**
- 采用EventEngine事件驱动架构解耦模块
- Gateway抽象层统一交易接口，支持多券商扩展
- vnpy.alpha的ML模型训练流程和因子工程

---

#### 2.1.2 QUANTAXIS — 高性能一站式解决方案

| 项目信息 | 详情 |
|---------|------|
| **GitHub URL** | https://github.com/quantaxis/quantaxis |
| **Star数量** | **10k+** |
| **最新版本** | 2.1.0-alpha2 (2025年10月) |
| **核心技术** | Python + Rust |

**核心架构：**
```
QUANTAXIS/
├── QARSBridge/      # Rust桥接层 (100x性能提升)
├── QADataBridge/    # 零拷贝数据交换
├── QIFI/            # 统一账户协议
├── QAFactor/        # 因子研究套件
├── QAStrategy/      # 回测套件
├── QAPubSub/        # RabbitMQ消息队列
└── QAWebServer/     # 微服务架构
```

**性能对比：**
| 操作 | Python版本 | QARS2 Rust | 加速比 |
|------|-----------|-----------|--------|
| 创建1000个账户 | ~50秒 | ~0.5秒 | **100x** |
| 10年日线回测 | ~30秒 | ~3秒 | **10x** |
| 内存占用 | ~2MB/账户 | ~200KB/账户 | **-90%** |

**核心借鉴价值：**

| 借鉴方向 | 具体内容 |
|----------|----------|
| **回测引擎架构** | Rust核心加速、10x回测速度、支持自定义策略基类 |
| **多账户体系** | QIFI统一账户协议、跨语言兼容、增量更新 |
| **事件驱动设计** | RabbitMQ消息队列、1-1/1-n/n-n消息分发、分布式计算 |
| **分布式架构** | QAWebServer微服务、QASchedule任务调度、DAG Pipeline |

**对Leek Trader的可借鉴点：**
- QIFI协议设计统一账户标准
- Rust/Go加速关键性能路径
- 消息队列解耦实现分布式架构

---

### 🥈 第二梯队：3k-10k Stars（实用工具）

---

#### 2.2.1 AData — A股免费数据获取利器

| 项目信息 | 详情 |
|---------|------|
| **GitHub URL** | https://github.com/1nchaos/adata |
| **Star数量** | **3.8k** |
| **最新版本** | v2.9.0 (2025年4月) |
| **开源协议** | Apache-2.0 |

**数据源覆盖（全部免费）：**
| 数据源 | 数据类型 |
|--------|----------|
| 同花顺 | 行情、概念、指数 |
| 东方财富 | 行情、资金流向、北向资金 |
| 百度股市通 | 分笔成交、实时行情 |
| 腾讯理财 | 实时行情、5档行情 |
| 新浪财经 | 可转债行情 |

**数据类型：**
- 股票基本信息：代码列表、股本、行业分类、概念板块
- 行情数据：日/周/月K线、分时、实时、5档、分笔
- 资金流向：个股资金流、概念资金流、北向资金
- 其他：ETF、可转债、龙虎榜、融资融券、解禁、热度榜

**核心借鉴价值：**

| 借鉴方向 | 具体内容 |
|----------|----------|
| **免费数据源补充** | 多数据源融合切换、代理池支持、高可用保障 |
| **模块化API设计** | `stock.info.*`、`stock.market.*`、`stock.finance.*` 清晰分层 |

**对Leek Trader的可借鉴点：**
- 多数据源抽象层设计，支持动态切换和降级
- 代理机制应对访问限制
- 数据字典规范便于数据库落地

---

#### 2.2.2 MyTT — 通达信指标公式移植神器

| 项目信息 | 详情 |
|---------|------|
| **GitHub URL** | https://github.com/mpquant/MyTT |
| **Star数量** | **2.3k** |
| **核心特点** | 单文件百行代码、零依赖ta-lib |

**指标覆盖：**

| 类别 | 指标 |
|------|------|
| **趋势类** | MACD, BOLL, BBI, EXPMA, TRIX |
| **动量类** | RSI, KDJ, CCI, WR, PSY, MTM, ROC |
| **波动率** | ATR, BOLL宽度 |
| **量价类** | OBV, MFI, VR |
| **通道类** | TAQ(海龟), KTN(肯特纳) |
| **情绪类** | BRAR, BIAS |

**基础工具函数：**
`REF`, `MA`, `EMA`, `SMA`, `STD`, `HHV`, `LLV`, `CROSS`, `COUNT`, `EVERY`, `EXIST`, `BARSLAST`, `SLOPE`, `FORCAST`

**核心借鉴价值：**

| 借鉴方向 | 具体内容 |
|----------|----------|
| **技术指标公式移植** | 通达信/同花顺兼容、计算结果一致到小数点后2位 |
| **轻量级实现** | 单文件、纯Python、无ta-lib依赖 |

**对Leek Trader的可借鉴点：**
- 直接引入作为技术指标计算引擎
- 支持用户自定义通达信风格指标公式
- 向量化计算避免循环，提升性能

---

### 🚀 第三梯队：2025新锐（前沿创新）

---

#### 2.3.1 TradingAgents — 多智能体AI交易框架

| 项目信息 | 详情 |
|---------|------|
| **GitHub URL** | https://github.com/TauricResearch/TradingAgents |
| **Star数量** | **65k+** (增长极快) |
| **开源协议** | Apache-2.0 |
| **核心技术** | LangGraph + 多LLM |

**多智能体架构：**
```
┌─────────────────────────────────────────────────────────────┐
│                    Portfolio Manager                         │
│                      (最终决策)                               │
└─────────────────────┬───────────────────────────────────────┘
                      │
    ┌─────────────────┼─────────────────┐
    │                 │                 │
┌───▼───┐       ┌─────▼─────┐     ┌─────▼─────┐
│ Trader │       │   Risk    │     │  Debate   │
│(交易员)│       │Management │     │  System   │
└───┬───┘       └───────────┘     └─────┬─────┘
    │                                   │
    │         ┌─────────────────────────┤
    │         │                         │
┌───▼───────┐ │ ┌───────────────────────▼───────────────────┐
│ Analysts  │ │ │          Bull/Bear Researchers            │
│  Team     │ │ │        (多空辩论机制)                      │
└───────────┘ │ └───────────────────────────────────────────┘
              │
    ┌─────────┴─────────────────────────────────┐
    │         │         │         │             │
┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐   ┌───▼───┐
│Fundam.│ │Sentim.│ │ News  │ │Techni.│   │ Macro │
│ 基本面│ │ 情绪  │ │ 新闻  │ │ 技术  │   │ 宏观  │
└───────┘ └───────┘ └───────┘ └───────┘   └───────┘
```

**Agent角色定义：**
| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| 基本面分析师 | 评估财务业绩 | PE/PB/ROE/财报 | 基本面评分 |
| 情绪分析师 | 分析社交媒体情绪 | 新闻/评论 | 情绪评分 |
| 新闻分析师 | 监控全球新闻 | 宏观事件 | 新闻影响 |
| 技术分析师 | 技术指标分析 | K线/指标 | 技术信号 |
| 看涨/看跌研究员 | 多空辩论 | 各Agent观点 | 辩论结论 |
| 交易员 | 执行决策 | 综合决策 | 订单 |
| 风险管理 | 风险评估 | 持仓/市场 | 风险建议 |

**核心借鉴价值：**

| 借鉴方向 | 具体内容 |
|----------|----------|
| **多智能体AI分析** | 7种专业Agent角色分工、结构化辩论机制 |
| **LLM集成** | 支持OpenAI/DeepSeek/Qwen/GLM等9种提供商 |

**对Leek Trader的可借鉴点：**
- Agent角色分工架构：分析师→研究员→交易员→风控
- 多空辩论机制避免单一视角决策偏差
- 决策日志持久化和反思系统
- 多LLM提供商支持降低API成本

---

#### 2.3.2 OSKHQuant (khQuant) — 可视化回测平台

| 项目信息 | 详情 |
|---------|------|
| **官网** | https://khsci.com/khQuant |
| **开发者** | Mr.看海 (信号处理专家) |
| **核心技术** | Python + PyQt5 + miniQMT |
| **运行平台** | Windows |

**可视化回测方案：**

| 特性 | 说明 |
|------|------|
| **回测速度** | 5x实时速度 |
| **数据粒度** | TICK级历史数据 |
| **交易成本** | 滑点模拟、手续费计算 |
| **A股适配** | 涨跌停、熔断机制 |
| **报告生成** | 夏普率、最大回撤等 |

**GUI设计特点：**
- PyQt5桌面级GUI应用
- 参数配置、回测设置鼠标点击完成
- 内置策略向导，降低编程门槛
- 动态K线绘制、技术指标叠加
- 策略净值曲线、持仓变化可视化

**核心借鉴价值：**

| 借鉴方向 | 具体内容 |
|----------|----------|
| **可视化回测方案** | GUI设计、回测引擎、图表展示 |
| **本地化部署** | 策略数据本地存储、安全可控 |

**对Leek Trader的可借鉴点：**
- PyQt5桌面应用架构
- 回测引擎滑点模拟、交易成本计算
- Matplotlib/Plotly双引擎可视化
- UI/数据/策略分离的模块化设计

---

## 三、Leek Trader 当前不足诊断

### 3.1 问题诊断矩阵

| 问题类别 | 具体问题 | 严重程度 | 参考梯队 | 参考项目 |
|----------|----------|----------|----------|----------|
| **架构层** | 非事件驱动架构 | 🔴 高 | 10k+ Stars | vnpy、QUANTAXIS |
| **架构层** | 无统一交易接口抽象 | 🔴 高 | 10k+ Stars | vnpy(Gateway层) |
| **数据层** | 数据源单一、无缓存 | 🔴 高 | 3k-10k Stars | AData |
| **策略层** | 技术指标覆盖不足(仅2种) | 🔴 高 | 3k-10k Stars | MyTT(20+) |
| **AI层** | 无LLM/多Agent能力 | 🔴 高 | 2025新锐 | TradingAgents |
| **回测层** | 回测与模拟环境不统一 | 🟡 中 | 10k+ Stars | vnpy、QUANTAXIS |
| **可视化** | 缺乏专业回测可视化 | 🟡 中 | 2025新锐 | OSKHQuant |
| **多账户** | 无多账户/子账户支持 | 🟡 中 | 10k+ Stars | vnpy、QUANTAXIS |

---

## 四、功能优化计划（分四期）

### 📌 第一期：数据与指标基础（预计1-2周）

> **参考梯队**：3k-10k Stars（AData、MyTT）
> **目标**：补齐数据短板，丰富技术指标

#### 4.1.1 集成AData数据源

**具体方案：**
```python
# 多数据源抽象层设计（参考AData）
class DataSourceManager:
    """多数据源管理器"""

    sources = {
        'eastmoney': EastMoneySource(),
        'sina': SinaSource(),
        'tencent': TencentSource(),
        'akshare': AkShareSource(),
    }

    def get_quote(self, symbol: str, source: str = None) -> Quote:
        """获取行情，自动切换数据源"""
        if source:
            return self.sources[source].get_quote(symbol)

        # 按优先级尝试各数据源
        for name, src in self.sources.items():
            try:
                return src.get_quote(symbol)
            except Exception:
                continue
        raise DataSourceExhaustedError()
```

**预期效果**：数据可用性提升至99%+

#### 4.1.2 集成MyTT技术指标库

**具体方案：**
```python
# 直接引入MyTT作为指标计算引擎
from MyTT import MACD, KDJ, RSI, BOLL, ATR

class IndicatorService:
    """技术指标服务（基于MyTT）"""

    def calculate_all(self, df: pd.DataFrame) -> dict:
        close, high, low, vol = df['close'], df['high'], df['low'], df['volume']

        return {
            'macd': MACD(close, 12, 26, 9),
            'kdj': KDJ(close, high, low, 9, 3, 3),
            'rsi': RSI(close, 14),
            'boll': BOLL(close, 20, 2),
            'atr': ATR(close, high, low, 14),
        }
```

**预期效果**：技术指标从2种扩展到20+种

---

### 📌 第二期：架构重构（预计2-3周）

> **参考梯队**：10k+ Stars（vnpy、QUANTAXIS）
> **目标**：建立事件驱动架构，统一交易接口

#### 4.2.1 事件驱动架构重构

**参考项目**：vnpy(EventEngine)、QUANTAXIS(QAPubSub)

**具体方案：**
```python
# 事件引擎设计（参考vnpy）
from enum import Enum
from typing import Callable, Dict, List
from queue import Queue
from threading import Thread

class EventType(Enum):
    TICK = "tick"           # 行情更新
    BAR = "bar"             # K线完成
    ORDER = "order"         # 订单状态
    TRADE = "trade"         # 成交
    SIGNAL = "signal"       # 策略信号
    RISK = "risk"           # 风控事件

class EventEngine:
    """事件驱动引擎（参考vnpy设计）"""

    def __init__(self):
        self._queue: Queue = Queue()
        self._handlers: Dict[str, List[Callable]] = {}
        self._thread: Thread = None
        self._active: bool = False

    def register(self, event_type: EventType, handler: Callable):
        """注册事件处理器"""
        if event_type.value not in self._handlers:
            self._handlers[event_type.value] = []
        self._handlers[event_type.value].append(handler)

    def put(self, event_type: EventType, data: any):
        """放入事件"""
        self._queue.put((event_type, data))

    def run(self):
        """运行事件引擎"""
        self._active = True
        self._thread = Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        while self._active:
            event_type, data = self._queue.get()
            handlers = self._handlers.get(event_type.value, [])
            for handler in handlers:
                handler(data)
```

#### 4.2.2 Gateway抽象层设计

**参考项目**：vnpy(Gateway层)

**具体方案：**
```python
# 交易接口抽象层（参考vnpy Gateway）
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class OrderRequest:
    symbol: str
    direction: str  # BUY/SELL
    order_type: str  # MARKET/LIMIT
    price: Optional[float]
    volume: int

@dataclass
class OrderResult:
    order_id: str
    status: str
    message: str

class BaseGateway(ABC):
    """交易接口抽象基类"""

    @abstractmethod
    def connect(self, config: dict): ...

    @abstractmethod
    def subscribe(self, symbols: List[str]): ...

    @abstractmethod
    def send_order(self, req: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def cancel_order(self, order_id: str): ...

    @abstractmethod
    def query_position(self) -> List[dict]: ...

# 实现类
class SimulatedGateway(BaseGateway):
    """模拟交易网关"""
    ...

class XtQuantGateway(BaseGateway):
    """MiniQMT实盘网关"""
    ...
```

#### 4.2.3 统一策略接口

**参考项目**：vnpy、QUANTAXIS

**具体方案：**
```python
# 统一策略接口（回测/模拟/实盘共用）
from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    """策略基类 - 三环境统一"""

    @abstractmethod
    def on_init(self, context: StrategyContext):
        """初始化"""
        ...

    @abstractmethod
    def on_bar(self, bar: BarData):
        """K线回调"""
        ...

    @abstractmethod
    def on_tick(self, tick: TickData):
        """Tick回调"""
        ...

    @abstractmethod
    def on_order(self, order: OrderData):
        """订单状态回调"""
        ...

    @abstractmethod
    def on_trade(self, trade: TradeData):
        """成交回调"""
        ...

# 策略运行器
class StrategyRunner:
    def run_backtest(self, strategy: BaseStrategy, start, end): ...
    def run_paper(self, strategy: BaseStrategy): ...
    def run_live(self, strategy: BaseStrategy, gateway: BaseGateway): ...
```

---

### 📌 第三期：AI能力升级（预计3-4周）

> **参考梯队**：2025新锐（TradingAgents）
> **目标**：引入多Agent架构和LLM能力

#### 4.3.1 多Agent交易决策架构

**参考项目**：TradingAgents

**架构设计：**
```
┌─────────────────────────────────────────────────────────────┐
│                    Portfolio Manager Agent                   │
│                      (最终决策审批)                           │
└─────────────────────────────┬───────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼───────┐     ┌───────▼───────┐     ┌───────▼───────┐
│  Trader Agent │     │  Risk Agent   │     │ Debate Agent  │
│   (交易执行)   │     │  (风险管理)    │     │  (多空辩论)   │
└───────────────┘     └───────────────┘     └───────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼───────┐     ┌───────▼───────┐     ┌───────▼───────┐
│Technical Agent│     │Fundamental    │     │ Sentiment     │
│  (技术分析)    │     │Agent(基本面)   │     │Agent(情绪)    │
└───────────────┘     └───────────────┘     └───────────────┘
```

**具体方案：**
```python
# 多Agent架构实现
from langgraph.graph import StateGraph
from typing import TypedDict, Annotated

class AgentState(TypedDict):
    symbol: str
    market_data: dict
    technical_analysis: dict
    fundamental_analysis: dict
    sentiment_analysis: dict
    debate_result: dict
    risk_assessment: dict
    final_decision: dict

class MultiAgentSystem:
    """多Agent交易决策系统"""

    def __init__(self, llm_provider: str = 'deepseek'):
        self.llm = LLMProviderManager().get_provider(llm_provider)
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """构建Agent工作流图"""
        graph = StateGraph(AgentState)

        # 添加节点
        graph.add_node("technical", self.technical_agent)
        graph.add_node("fundamental", self.fundamental_agent)
        graph.add_node("sentiment", self.sentiment_agent)
        graph.add_node("debate", self.debate_agent)
        graph.add_node("risk", self.risk_agent)
        graph.add_node("trader", self.trader_agent)

        # 定义边（工作流）
        graph.add_edge("technical", "debate")
        graph.add_edge("fundamental", "debate")
        graph.add_edge("sentiment", "debate")
        graph.add_edge("debate", "risk")
        graph.add_edge("risk", "trader")

        return graph.compile()

    async def analyze(self, symbol: str, market_data: dict) -> dict:
        """执行多Agent分析"""
        initial_state = AgentState(
            symbol=symbol,
            market_data=market_data,
            # ...
        )
        result = await self.graph.ainvoke(initial_state)
        return result['final_decision']
```

#### 4.3.2 LLM集成方案

**参考项目**：TradingAgents（9种LLM提供商）

**具体方案：**
```python
class LLMProviderManager:
    """多LLM提供商管理"""

    providers = {
        'deepseek': DeepSeekProvider(),      # 性价比最高
        'qwen': QwenProvider(),              # 阿里云
        'glm': GLMProvider(),                # 智谱
        'openai': OpenAIProvider(),          # GPT
        'ollama': OllamaProvider(),          # 本地模型
    }

    def analyze(self, prompt: str, provider: str = 'deepseek') -> str:
        return self.providers[provider].chat(prompt)

    def structured_output(self, prompt: str, schema: Type[BaseModel]) -> BaseModel:
        """结构化输出，确保决策一致性"""
        ...
```

---

### 📌 第四期：可视化与完善（预计1-2周）

> **参考梯队**：2025新锐（OSKHQuant）
> **目标**：完善回测可视化，建立监控体系

#### 4.4.1 回测可视化升级

**参考项目**：OSKHQuant

**具体方案：**
- Matplotlib/Plotly双引擎图表
- 动态K线绘制算法
- 技术指标叠加显示
- 策略净值曲线
- 持仓变化可视化
- 关键绩效指标仪表盘

#### 4.4.2 监控与告警

**具体方案：**
- Prometheus指标导出
- 关键指标监控
- 异常告警
- 每日交易日报

---

## 五、优化优先级矩阵

| 优化项 | 预期收益 | 实现难度 | 优先级 | 参考梯队 | 参考项目 |
|--------|----------|----------|--------|----------|----------|
| 集成MyTT指标库 | ⭐⭐⭐⭐⭐ | ⭐ | **P0** | 3k-10k Stars | MyTT |
| 集成AData数据源 | ⭐⭐⭐⭐ | ⭐⭐ | **P0** | 3k-10k Stars | AData |
| 事件驱动架构 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | **P1** | 10k+ Stars | vnpy |
| Gateway抽象层 | ⭐⭐⭐⭐ | ⭐⭐⭐ | **P1** | 10k+ Stars | vnpy |
| 统一策略接口 | ⭐⭐⭐⭐ | ⭐⭐ | **P1** | 10k+ Stars | vnpy、QUANTAXIS |
| 多Agent架构 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | **P1** | 2025新锐 | TradingAgents |
| LLM集成 | ⭐⭐⭐⭐ | ⭐⭐⭐ | **P1** | 2025新锐 | TradingAgents |
| 可视化回测 | ⭐⭐⭐ | ⭐⭐ | **P2** | 2025新锐 | OSKHQuant |
| 多账户体系 | ⭐⭐⭐ | ⭐⭐⭐ | **P2** | 10k+ Stars | vnpy、QUANTAXIS |

---

## 六、预期效果总结

### 模拟交易成功率提升路径

```
当前状态
├── 技术指标：2种
├── 数据源：单一
├── 架构：非事件驱动
├── AI能力：无
└── 预估综合胜率：~35-40%

↓ 第一期完成后（数据与指标基础）

├── 技术指标：20+种（MyTT集成）
├── 数据源：多源融合（AData）
├── 数据可用性：99%+
└── 预估综合胜率：~42-47%  ⬆️ +7%

↓ 第二期完成后（架构重构）

├── 架构：事件驱动
├── 交易接口：Gateway统一抽象
├── 策略接口：三环境统一
└── 预估综合胜率：~48-53%  ⬆️ +6%

↓ 第三期完成后（AI能力升级）

├── 多Agent：7种专业Agent
├── LLM：DeepSeek/Qwen等
├── 决策质量：多视角辩论
└── 预估综合胜率：~55-62%  ⬆️ +7%

↓ 第四期完成后（可视化与完善）

├── 可视化：专业回测图表
├── 监控：Prometheus告警
├── 实盘准备就绪
└── 预估综合胜率：~58-65%  ⬆️ +3%
```

### 关键里程碑

| 里程碑 | 时间 | 标志 | 参考梯队 |
|--------|------|------|----------|
| M1：数据指标基础 | 第2周 | MyTT + AData集成 | 3k-10k Stars |
| M2：架构重构 | 第5周 | 事件驱动 + Gateway | 10k+ Stars |
| M3：AI能力上线 | 第9周 | 多Agent + LLM | 2025新锐 |
| M4：可视化完善 | 第11周 | 回测图表 + 监控 | 2025新锐 |

---

## 七、参考项目GitHub链接汇总

### 10k+ Stars梯队
| 项目 | GitHub URL | Stars |
|------|------------|-------|
| VeighNa | https://github.com/vnpy/vnpy | 36.2k |
| QUANTAXIS | https://github.com/quantaxis/quantaxis | 10k+ |

### 3k-10k Stars梯队
| 项目 | GitHub URL | Stars |
|------|------------|-------|
| AData | https://github.com/1nchaos/adata | 3.8k |
| MyTT | https://github.com/mpquant/MyTT | 2.3k |

### 2025新锐梯队
| 项目 | GitHub URL | Stars |
|------|------------|-------|
| TradingAgents | https://github.com/TauricResearch/TradingAgents | 65k+ |
| OSKHQuant | https://khsci.com/khQuant | - |

---

*本优化计划基于GitHub量化交易项目梯队评测制定，建议每季度迭代更新。*
