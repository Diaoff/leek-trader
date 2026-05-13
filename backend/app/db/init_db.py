from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Column, Table

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.db.base import Base
from app.models.user import User
from app.users.initialization import assign_legacy_local_data, ensure_user_resources


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    upgrade_schema(engine)
    sync_postgresql_comments(engine)

    with SessionLocal() as db:
        assign_legacy_local_data(db)
        for user in db.scalars(select(User).where(User.is_active.is_(True))).all():
            ensure_user_resources(db, user)


def upgrade_schema(db_engine: Engine) -> None:
    required_columns = {
        "accounts": {
            "user_id": "INTEGER",
        },
        "watchlist_items": {
            "user_id": "INTEGER",
            "group_id": "INTEGER",
            "note": "VARCHAR(255)",
            "is_pinned": "BOOLEAN DEFAULT FALSE",
            "is_special_attention": "BOOLEAN DEFAULT FALSE",
        },
        "watchlist_groups": {
            "user_id": "INTEGER",
        },
        "app_preferences": {
            "user_id": "INTEGER",
            "risk_rule_changed_at": "TIMESTAMP",
        },
        "orders": {
            "risk_rule_version": "VARCHAR(64)",
        },
        "ai_configs": {
            "user_id": "INTEGER",
            "provider": "VARCHAR(32) DEFAULT 'openai_compatible'",
        },
        "strategies": {
            "user_id": "INTEGER",
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
        "strategy_runs": {
            "user_id": "INTEGER",
        },
        "smart_selection_configs": {
            "user_id": "INTEGER",
        },
        "smart_selection_runs": {
            "user_id": "INTEGER",
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
        "market_intraday_bars": {
            "source": "VARCHAR(32) DEFAULT 'eastmoney'",
            "turnover": "FLOAT DEFAULT 0",
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
        if not inspector.has_table("strategy_versions"):
            connection.execute(
                text(
                    """
                    CREATE TABLE strategy_versions (
                        id INTEGER PRIMARY KEY,
                        tenant_id VARCHAR(64) DEFAULT 'local',
                        user_id INTEGER,
                        strategy_id INTEGER NOT NULL,
                        version INTEGER NOT NULL,
                        name VARCHAR(128) NOT NULL,
                        symbol VARCHAR(32) DEFAULT '',
                        strategy_type VARCHAR(32) NOT NULL,
                        execution_mode VARCHAR(32) NOT NULL,
                        target_type VARCHAR(32) NOT NULL,
                        target_config JSON,
                        parameters JSON,
                        created_at TIMESTAMP
                    )
                    """
                )
            )
        if not inspector.has_table("daily_reviews"):
            connection.execute(
                text(
                    """
                    CREATE TABLE daily_reviews (
                        id INTEGER PRIMARY KEY,
                        tenant_id VARCHAR(64) DEFAULT 'local',
                        user_id INTEGER,
                        review_date DATE,
                        symbol VARCHAR(32) DEFAULT '',
                        strategy_id INTEGER,
                        strategy_name VARCHAR(128),
                        strategy_type VARCHAR(32) DEFAULT '',
                        headline VARCHAR(255) NOT NULL,
                        highlights JSON,
                        risks JSON,
                        next_actions JSON,
                        backtest_summary JSON,
                        payload JSON,
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP
                    )
                    """
                )
            )

        for table_name, columns in required_columns.items():
            if not inspector.has_table(table_name):
                continue

            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_definition in columns.items():
                if column_name in existing_columns:
                    continue
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"))

        _sync_user_scoped_indexes(connection, inspector, db_engine.dialect.name)

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


def _sync_user_scoped_indexes(connection, inspector, dialect_name: str) -> None:
    legacy_indexes = {
        "watchlist_items": ("idx_watchlist_tenant_symbol", "idx_watchlist_tenant_sort_order"),
        "watchlist_groups": ("idx_watchlist_group_tenant_name", "idx_watchlist_group_tenant_sort_order"),
        "app_preferences": ("ix_app_preferences_tenant_id",),
        "ai_configs": ("idx_ai_config_tenant",),
        "smart_selection_configs": ("ix_smart_selection_configs_tenant_id",),
    }
    target_indexes = {
        "watchlist_items": (
            ("idx_watchlist_user_symbol", ("user_id", "symbol"), True),
            ("idx_watchlist_user_sort_order", ("user_id", "sort_order"), False),
        ),
        "watchlist_groups": (
            ("idx_watchlist_group_user_name", ("user_id", "name"), True),
            ("idx_watchlist_group_user_sort_order", ("user_id", "sort_order"), False),
        ),
        "app_preferences": (("idx_app_preference_user", ("user_id",), True),),
        "ai_configs": (("idx_ai_config_user", ("user_id",), True),),
        "smart_selection_configs": (("idx_smart_selection_config_user", ("user_id",), True),),
    }
    legacy_unique_constraints = {
        "app_preferences": ("app_preferences_tenant_id_key",),
        "smart_selection_configs": ("smart_selection_configs_tenant_id_key",),
    }

    for table_name, index_names in legacy_indexes.items():
        if not inspector.has_table(table_name):
            continue
        existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        for index_name in index_names:
            if index_name not in existing_indexes:
                continue
            if dialect_name == "postgresql":
                connection.execute(text(f'DROP INDEX IF EXISTS "{index_name}"'))
            elif dialect_name == "sqlite":
                connection.execute(text(f'DROP INDEX IF EXISTS {index_name}'))

    if dialect_name == "postgresql":
        for table_name, constraint_names in legacy_unique_constraints.items():
            if not inspector.has_table(table_name):
                continue
            existing_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)}
            for constraint_name in constraint_names:
                if constraint_name in existing_constraints:
                    connection.execute(text(f'ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS "{constraint_name}"'))

    for table_name, index_specs in target_indexes.items():
        if not inspector.has_table(table_name):
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        for index_name, columns, unique in index_specs:
            if index_name in existing_indexes or not set(columns).issubset(existing_columns):
                continue
            unique_sql = "UNIQUE " if unique else ""
            columns_sql = ", ".join(columns)
            connection.execute(text(f"CREATE {unique_sql}INDEX {index_name} ON {table_name} ({columns_sql})"))


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
