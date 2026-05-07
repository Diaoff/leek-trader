import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    test_db_path = tmp_path / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{test_db_path}"
    os.environ["REDIS_URL"] = "redis://localhost:6379/15"

    import app.core.config as config_module
    import app.core.db as db_module
    import app.db.init_db as init_db_module
    from app.db.base import Base

    importlib.reload(config_module)
    importlib.reload(db_module)
    importlib.reload(init_db_module)

    Base.metadata.drop_all(bind=db_module.engine)
    Base.metadata.create_all(bind=db_module.engine)
    init_db_module.initialize_database()

    from app.core.db import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import app.main as main_module
    from app.risk.service import RiskService
    from app.trading.service import TradingService

    importlib.reload(main_module)

    monkeypatch.setattr(RiskService, "_is_trading_time", staticmethod(lambda now=None: True))
    monkeypatch.setattr(TradingService, "_get_quote_snapshot", lambda self, symbol: {"price": 100.0, "change_percent": 0.0, "is_halted": False})

    with TestClient(main_module.app) as test_client:
        login_response = test_client.post(
            "/api/v1/auth/login",
            data={"username": "local-admin", "password": "local-admin"},
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client
