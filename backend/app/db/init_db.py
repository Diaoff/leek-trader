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
    }

    inspector = inspect(db_engine)

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
