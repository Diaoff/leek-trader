from fastapi import APIRouter

from app.api.accounts import router as accounts_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.monitoring import router as monitoring_router
from app.api.orders import router as orders_router
from app.api.portfolio import router as portfolio_router
from app.api.positions import router as positions_router
from app.api.quotes import router as quotes_router
from app.api.reporting import router as reporting_router
from app.api.strategies import router as strategies_router
from app.api.trading import router as trading_router
from app.api.watchlists import router as watchlists_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["system"])
api_router.include_router(monitoring_router, prefix="/monitoring", tags=["monitoring"])
api_router.include_router(auth_router, prefix="/auth", tags=["authentication"])
api_router.include_router(accounts_router, tags=["accounts"])
api_router.include_router(orders_router, tags=["orders"])
api_router.include_router(positions_router, tags=["positions"])
api_router.include_router(quotes_router, tags=["quotes"])
api_router.include_router(reporting_router, tags=["reporting"])
api_router.include_router(strategies_router, tags=["strategies"])
api_router.include_router(trading_router, tags=["trading"])
api_router.include_router(portfolio_router, tags=["portfolio"])
api_router.include_router(watchlists_router, tags=["watchlists"])
