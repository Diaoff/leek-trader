from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.account import Account, AccountStatus
from app.models.ai_config import AiConfig
from app.models.app_preference import AppPreference
from app.models.user import User
from app.preferences.service import DEFAULT_STRATEGY_SCHEDULER_PREFERENCES, DEFAULT_TRADING_PREFERENCES
from app.watchlist.service import WatchlistService


def ensure_user_resources(db: Session, user: User) -> None:
    """Create idempotent personal defaults for a user."""
    _ensure_account(db, user)
    _ensure_preferences(db, user)
    _ensure_ai_config(db, user)
    WatchlistService().ensure_default_groups(db, settings.default_tenant_id, user.id)
    db.commit()


def assign_legacy_local_data(db: Session) -> None:
    """Attach pre-user local data to the first admin, earliest user, or a new local admin."""
    user = _legacy_owner(db)
    if user is None:
        from app.core.auth import get_password_hash

        user = User(
            tenant_id=settings.default_tenant_id,
            username="local-admin",
            email="local-admin@example.com",
            password_hash=get_password_hash("local-admin"),
            full_name="本地管理员",
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        db.flush()

    for model in _legacy_user_singleton_models():
        _assign_legacy_singleton_model(db, model, user.id)

    for model in _legacy_user_owned_models():
        db.query(model).filter(model.user_id.is_(None)).update({"user_id": user.id}, synchronize_session=False)

    db.query(Account).filter(Account.user_id.is_(None)).update({"user_id": user.id}, synchronize_session=False)
    db.commit()
    ensure_user_resources(db, user)


def _ensure_account(db: Session, user: User) -> Account:
    account = db.scalar(
        select(Account).where(
            Account.user_id == user.id,
            Account.name == settings.default_account_name,
        )
    )
    if account is not None:
        return account

    initial_cash = Decimal("1000000.00")
    account = Account(
        tenant_id=settings.default_tenant_id,
        user_id=user.id,
        name=settings.default_account_name,
        currency="CNY",
        initial_cash=initial_cash,
        available_cash=initial_cash,
        frozen_cash=Decimal("0.00"),
        total_equity=initial_cash,
        status=AccountStatus.ACTIVE,
    )
    db.add(account)
    db.flush()
    return account


def _ensure_preferences(db: Session, user: User) -> AppPreference:
    preference = db.scalar(select(AppPreference).where(AppPreference.user_id == user.id))
    if preference is not None:
        return preference

    preference = AppPreference(
        tenant_id=settings.default_tenant_id,
        user_id=user.id,
        trading_preferences=DEFAULT_TRADING_PREFERENCES.copy(),
        strategy_scheduler_preferences=DEFAULT_STRATEGY_SCHEDULER_PREFERENCES.copy(),
    )
    db.add(preference)
    db.flush()
    return preference


def _ensure_ai_config(db: Session, user: User) -> AiConfig:
    config = db.scalar(select(AiConfig).where(AiConfig.user_id == user.id))
    if config is not None:
        return config

    config = AiConfig(tenant_id=settings.default_tenant_id, user_id=user.id, provider="openai_compatible")
    db.add(config)
    db.flush()
    return config


def _legacy_owner(db: Session) -> User | None:
    return db.scalar(select(User).where(User.is_superuser.is_(True)).order_by(User.created_at.asc(), User.id.asc())) or db.scalar(
        select(User).order_by(User.created_at.asc(), User.id.asc())
    )


def _legacy_user_owned_models() -> tuple[type, ...]:
    from app.models.smart_selection_run import SmartSelectionRun
    from app.models.strategy import Strategy
    from app.models.strategy_run import StrategyRun
    from app.models.watchlist import WatchlistItem
    from app.models.watchlist_group import WatchlistGroup

    return (
        WatchlistGroup,
        WatchlistItem,
        Strategy,
        StrategyRun,
        SmartSelectionRun,
    )


def _legacy_user_singleton_models() -> tuple[type, ...]:
    from app.models.ai_config import AiConfig
    from app.models.app_preference import AppPreference
    from app.models.smart_selection_config import SmartSelectionConfig

    return (AppPreference, AiConfig, SmartSelectionConfig)


def _assign_legacy_singleton_model(db: Session, model: type, user_id: int) -> None:
    existing = db.scalar(select(model).where(model.user_id == user_id))
    legacy_rows = db.scalars(
        select(model)
        .where(model.user_id.is_(None))
        .order_by(model.created_at.asc(), model.id.asc())
    ).all()

    if existing is not None:
        for row in legacy_rows:
            db.delete(row)
        return

    if not legacy_rows:
        return

    keeper = legacy_rows[0]
    keeper.user_id = user_id
    for row in legacy_rows[1:]:
        db.delete(row)
