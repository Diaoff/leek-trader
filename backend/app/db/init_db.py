from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Column, Table

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.db.base import Base
from app.models.account import Account


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    sync_postgresql_comments(engine)

    with SessionLocal() as db:
        existing_account = db.scalar(
            select(Account).where(
                Account.tenant_id == settings.default_tenant_id,
                Account.name == settings.default_account_name,
            )
        )
        if existing_account is not None:
            return

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
