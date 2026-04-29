from decimal import Decimal

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Column, Table

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.db.base import Base
from app.models.account import Account
from app.watchlist.service import WatchlistService


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    upgrade_schema(engine)
    sync_postgresql_comments(engine)

    with SessionLocal() as db:
        existing_account = db.scalar(
            select(Account).where(
                Account.tenant_id == settings.default_tenant_id,
                Account.name == settings.default_account_name,
            )
        )
        if existing_account is None:
            account = Account(
                tenant_id=settings.default_tenant_id,
                name=settings.default_account_name,
                currency="CNY",
                initial_cash=Decimal("1000000.00"),
                available_cash=Decimal("1000000.00"),
                frozen_cash=Decimal("0.00"),
                total_equity=Decimal("1000000.00"),
            )
            db.add(account)
            db.commit()
            WatchlistService().ensure_default_groups(db, settings.default_tenant_id)


def upgrade_schema(db_engine: Engine) -> None:
    required_columns = {
        "accounts": {
            "user_id": "INTEGER",
        },
        "watchlist_items": {
            "group_id": "INTEGER",
            "note": "VARCHAR(255)",
            "is_pinned": "BOOLEAN DEFAULT FALSE",
            "is_special_attention": "BOOLEAN DEFAULT FALSE",
        },
        "strategies": {
            "symbol": "VARCHAR(32)",
            "target_type": "VARCHAR(32) DEFAULT 'single_symbol'",
            "target_config": "JSON",
            "execution_mode": "VARCHAR(32) DEFAULT 'signal_only'",
        },
        "positions": {
            "stop_loss_price": "NUMERIC(18, 4)",
            "take_profit_price": "NUMERIC(18, 4)",
            "strategy_add_count": "INTEGER DEFAULT 0",
            "exit_guard_status": "VARCHAR(32) DEFAULT 'inactive'",
            "exit_trigger_reason": "VARCHAR(32)",
            "exit_triggered_at": "TIMESTAMP",
        },
        "smart_selection_runs": {
            "progress_step": "INTEGER DEFAULT 0",
            "progress_total": "INTEGER DEFAULT 0",
            "progress_label": "VARCHAR(64)",
        },
        "market_daily_bars": {
            "source": "VARCHAR(32) DEFAULT 'baostock'",
            "adjustflag": "VARCHAR(8) DEFAULT '2'",
            "turnover": "FLOAT DEFAULT 0",
            "amplitude_pct": "FLOAT",
            "change_pct": "FLOAT",
            "turnover_rate": "FLOAT",
            "preclose": "FLOAT",
            "trade_status": "INTEGER",
            "pe_ttm": "FLOAT",
            "pb_mrq": "FLOAT",
            "ps_ttm": "FLOAT",
            "pcf_ncf_ttm": "FLOAT",
            "is_st": "BOOLEAN",
            "created_at": "TIMESTAMP",
            "updated_at": "TIMESTAMP",
        },
    }

    inspector = inspect(db_engine)

    if db_engine.dialect.name == "postgresql":
        _ensure_postgresql_enum_values(
            db_engine,
            "strategytype",
            ("moving_average", "macd", "rl_trading"),
        )
        _ensure_postgresql_enum_values(
            db_engine,
            "strategystatus",
            ("draft", "active", "paused"),
        )

    with db_engine.begin() as connection:
        for table_name, columns in required_columns.items():
            if not inspector.has_table(table_name):
                continue

            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_definition in columns.items():
                if column_name in existing_columns:
                    continue
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"))

        if inspector.has_table("strategies"):
            existing_columns = {column["name"] for column in inspector.get_columns("strategies")}
            if "target_type" in existing_columns:
                connection.execute(
                    text(
                        """
                        UPDATE strategies
                        SET target_type = COALESCE(NULLIF(target_type, ''), 'single_symbol')
                        WHERE target_type IS NULL OR target_type = ''
                        """
                    )
                )
            connection.execute(
                text(
                    """
                    UPDATE strategies
                    SET execution_mode = CASE execution_mode
                        WHEN 'SIGNAL_ONLY' THEN 'signal_only'
                        WHEN 'AUTO_TRADE' THEN 'auto_trade'
                        ELSE execution_mode
                    END
                    WHERE execution_mode IN ('SIGNAL_ONLY', 'AUTO_TRADE')
                    """
                )
            )
            if db_engine.dialect.name == "postgresql":
                connection.execute(
                    text(
                        """
                        UPDATE strategies
                        SET strategy_type = CASE strategy_type::text
                            WHEN 'MOVING_AVERAGE' THEN 'moving_average'::strategytype
                            WHEN 'MACD' THEN 'macd'::strategytype
                            WHEN 'RL_TRADING' THEN 'rl_trading'::strategytype
                            ELSE strategy_type
                        END
                        WHERE strategy_type::text IN ('MOVING_AVERAGE', 'MACD', 'RL_TRADING')
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        UPDATE strategies
                        SET status = CASE status::text
                            WHEN 'DRAFT' THEN 'draft'::strategystatus
                            WHEN 'ACTIVE' THEN 'active'::strategystatus
                            WHEN 'PAUSED' THEN 'paused'::strategystatus
                            ELSE status
                        END
                        WHERE status::text IN ('DRAFT', 'ACTIVE', 'PAUSED')
                        """
                    )
                )


def _ensure_postgresql_enum_values(db_engine: Engine, enum_name: str, values: tuple[str, ...]) -> None:
    with db_engine.begin() as connection:
        existing_values = set(
            connection.execute(
                text(
                    """
                    SELECT enumlabel
                    FROM pg_type type
                    JOIN pg_enum enum_value ON type.oid = enum_value.enumtypid
                    WHERE type.typname = :enum_name
                    """
                ),
                {"enum_name": enum_name},
            ).scalars()
        )

    for value in values:
        if value in existing_values:
            continue
        escaped_value = value.replace("'", "''")
        with db_engine.begin() as connection:
            connection.execute(text(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{escaped_value}'"))


def sync_postgresql_comments(db_engine: Engine) -> None:
    if db_engine.dialect.name != "postgresql":
        return

    preparer = db_engine.dialect.identifier_preparer

    with db_engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if table.comment:
                comment = table.comment.replace("'", "''")
                connection.execute(text(f"COMMENT ON TABLE {_qualified_table_name(preparer, table)} IS '{comment}'"))
            for column in table.columns:
                if column.comment:
                    comment = column.comment.replace("'", "''")
                    connection.execute(text(f"COMMENT ON COLUMN {_qualified_column_name(preparer, table, column)} IS '{comment}'"))


def _qualified_table_name(preparer, table: Table) -> str:
    table_name = preparer.quote(table.name)
    if table.schema:
        return f"{preparer.quote_schema(table.schema)}.{table_name}"
    return table_name


def _qualified_column_name(preparer, table: Table, column: Column) -> str:
    return f"{_qualified_table_name(preparer, table)}.{preparer.quote(column.name)}"
