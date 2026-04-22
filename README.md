# Leek Trader - 股票模拟交易系统

[![GitHub 仓库](https://img.shields.io/badge/GitHub-仓库-blue?style=for-the-badge&logo=github)](https://github.com/Diaoff/leek-trader.git)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Vue.js](https://img.shields.io/badge/Vue.js-4FC08D?style=for-the-badge&logo=vue.js)](https://vuejs.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?style=for-the-badge&logo=postgresql)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker)](https://www.docker.com/)

> 🔗 **GitHub 仓库**: https://github.com/Diaoff/leek-trader.git

一个基于 FastAPI 和 Vue 3 的股票模拟交易系统，提供真实行情接入、策略信号计算、模拟交易执行和投资组合分析功能。

## 📋 项目概述

Leek Trader 是一个轻量级的股票模拟交易 MVP（最小可行产品），旨在为投资者提供一个安全的环境来学习和实践股票交易策略。

### 核心技术栈

- **后端**: FastAPI + SQLAlchemy + PostgreSQL
- **前端**: Vue 3 + Vite + Pinia + Element Plus
- **缓存**: Redis
- **容器化**: Docker Compose

### 设计理念

- 遵循领域驱动设计（DDD）架构
- 支持多租户（tenant_id）架构
- RESTful API 设计
- 完整的业务逻辑与数据持久化分离

## ✨ 功能特性

### 核心交易功能

- 📊 **实时行情**: 支持新浪、东方财富等多个行情数据源自动切换
- 📈 **行情监控**: 实时显示股票价格、涨跌幅、成交量等信息
- 🎯 **策略分析**: 支持 MACD、移动平均线等多种技术指标策略
- 💹 **模拟交易**: 支持买卖订单、实时成交匹配、持仓管理
- 💰 **账户管理**: 现金余额、持仓市值、总资产实时更新
- 📝 **交易记录**: 完整的订单、成交、持仓、资金流水记录

### 策略类型

- **MACD 策略**: 基于指数平滑移动平均线的趋势追踪策略
- **移动平均线策略**: 基于短期/长期均线的交叉信号策略

### 系统功能

- 🔐 **用户认证**: JWT Token 的完整用户认证系统
- 📊 **投资组合分析**: 持仓分析、收益计算、风险评估
- 📋 **报表生成**: 交易历史、持仓汇总、收益报告
- 🏥 **系统监控**: 健康检查、性能指标、运行状态
- 📚 **API 文档**: 完整的 OpenAPI/Swagger 接口文档

## 🚀 安装指南

### 环境要求

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ (或使用 Docker)
- Redis 6+ (或使用 Docker)

### 快速开始（Docker Compose）

```bash
# 克隆项目
git clone https://github.com/Diaoff/leek-trader.git
cd leek-trader

# 启动所有服务
docker compose up
```

服务地址：
- 后端 API: http://localhost:8000
- 前端界面: http://localhost:5173
- API 文档: http://localhost:8000/docs

### 本地开发环境

#### 后端设置

```bash
cd backend

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp ../.env.example .env
# 编辑 .env 文件，修改数据库连接配置

# 启动后端服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 前端设置

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 数据库初始化

首次运行时，系统会自动创建数据库表结构和初始数据：

- 默认模拟账户（现金: 1,000,000 元）
- 基础市场数据

## 📖 使用说明

### 访问系统

1. 打开浏览器访问 http://localhost:5173
2. 使用默认账户登录或注册新账户
3. 开始模拟交易

### API 接口

完整的 API 接口文档请访问：http://localhost:8000/docs

主要 API 端点：

| 模块 | 端点 | 说明 |
|------|------|------|
| 认证 | `/api/v1/auth/login` | 用户登录 |
| 认证 | `/api/v1/auth/register` | 用户注册 |
| 账户 | `/api/v1/accounts` | 账户信息 |
| 行情 | `/api/v1/quotes` | 股票行情 |
| 订单 | `/api/v1/orders` | 订单管理 |
| 持仓 | `/api/v1/positions` | 持仓查询 |
| 策略 | `/api/v1/strategies` | 策略列表 |
| 组合 | `/api/v1/portfolio/summary` | 组合概要 |

### 测试

```bash
# 运行所有测试
pytest

# 运行单个测试文件
pytest backend/tests/test_orders.py

# 运行单个测试用例
pytest backend/tests/test_orders.py::test_create_order_persists_and_lists_order -q
```

## 🤝 贡献方法

### 开发流程

1. **Fork 仓库**: 点击 GitHub 仓库页面的 Fork 按钮
2. **克隆仓库**:
   ```bash
   git clone https://github.com/Diaoff/leek-trader.git
   cd leek-trader
   ```
3. **创建分支**:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **开发调试**: 按照本地开发环境说明进行开发
5. **提交代码**:
   ```bash
   git add .
   git commit -m "Add: your feature description"
   ```
6. **推送分支**:
   ```bash
   git push origin feature/your-feature-name
   ```
7. **创建 Pull Request**: 在 GitHub 仓库页面创建 PR

### 代码规范

- 遵循 PEP 8 Python 代码规范
- 使用中文编写注释和文档
- 所有 API 接口添加完整的 docstring
- 新增功能必须包含测试用例

### 问题反馈

如发现问题或有改进建议，请通过以下方式反馈：

- [GitHub Issues](https://github.com/Diaoff/leek-trader.git/issues)
- [GitHub Pull Requests](https://github.com/Diaoff/leek-trader.git/pulls)

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 📊 项目进度

### 已完成功能

- ✅ 用户认证系统（注册、登录、JWT Token）
- ✅ 账户管理（余额查询、账户信息）
- ✅ 实时行情（多数据源自动切换）
- ✅ 订单管理（下单、撤单、订单列表）
- ✅ 持仓管理（持仓查询、持仓明细）
- ✅ 策略系统（MACD、移动平均线）
- ✅ 模拟交易（订单匹配、成交处理）
- ✅ 投资组合分析（收益计算、风险评估）
- ✅ 系统监控（健康检查、性能指标）
- ✅ API 文档（OpenAPI/Swagger）
- ✅ 单元测试和集成测试

### 开发规划

- 🔄 订单详情和成交单查询优化
- 🔄 报表导出功能（Excel、PDF）
- 📋 更多的技术指标策略
- 📋 实盘交易接口对接
- 📋 历史回测功能
- 📋 更多的数据分析功能

### 迭代记录

详见 [progress.txt](progress.txt) 文件

## 📞 联系方式

- **GitHub**: https://github.com/Diaoff/leek-trader.git
- **问题反馈**: https://github.com/Diaoff/leek-trader.git/issues

---

<p align="center">
  使用 ❤️ 和 ☕ 构建
</p>
