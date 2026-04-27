from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    app_name: str = "Leek Trader"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/leek_trader"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    default_tenant_id: str = "local"
    default_account_name: str = "模拟账户"
    quote_cache_ttl_seconds: int = 15
    market_refresh_symbols: str = ""
    market_refresh_interval_seconds: int = 30
    async_alert_webhook_url: str | None = None
    async_alert_timeout_seconds: float = 3.0

    model_config = SettingsConfigDict(
        env_file=str(ROOT_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @computed_field
    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @computed_field
    @property
    def market_refresh_symbol_list(self) -> list[str]:
        return [
            symbol.strip().lower()
            for symbol in self.market_refresh_symbols.split(",")
            if symbol.strip()
        ]


settings = Settings()
