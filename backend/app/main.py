from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import setup_exception_handlers
from app.db.init_db import initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


def custom_openapi():
    """自定义 OpenAPI 文档"""
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Leek Trader API",
        version="1.0.0",
        description="股票模拟交易系统 API 文档",
        routes=app.routes,
        tags=[
            {"name": "system", "description": "系统相关接口"},
            {"name": "monitoring", "description": "监控相关接口"},
            {"name": "authentication", "description": "认证相关接口"},
            {"name": "ai", "description": "AI 分析相关接口"},
            {"name": "accounts", "description": "账户相关接口"},
            {"name": "orders", "description": "订单相关接口"},
            {"name": "positions", "description": "持仓相关接口"},
            {"name": "quotes", "description": "行情相关接口"},
            {"name": "reporting", "description": "报表相关接口"},
            {"name": "strategies", "description": "策略相关接口"},
            {"name": "trading", "description": "交易相关接口"},
            {"name": "portfolio", "description": "投资组合相关接口"},
            {"name": "watchlists", "description": "自选股相关接口"},
        ],
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app = FastAPI(
    title="Leek Trader API",
    description="股票模拟交易系统 API 文档",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 设置异常处理器
setup_exception_handlers(app)

app.include_router(api_router, prefix=settings.api_prefix)
app.openapi = custom_openapi


@app.get("/", summary="系统状态", description="获取系统运行状态")
def read_root() -> dict[str, str]:
    """获取系统运行状态"""
    return {
        "message": f"{settings.app_name} backend is running",
        "version": "1.0.0",
        "status": "healthy"
    }
