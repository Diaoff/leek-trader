from copy import deepcopy
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.app_preference import AppPreference
from app.schemas.preferences import (
    PreferencesRead,
    PreferencesUpdate,
    SmartSelectionPreferences,
    SmartSelectionPreferencesUpdate,
    StrategySchedulerPreferences,
    StrategySchedulerPreferencesUpdate,
    TradingPreferences,
    TradingPreferencesUpdate,
)
from app.schemas.smart_selection import SmartSelectionConfigUpdate
from app.smart_selection.service import SmartSelectionService


DEFAULT_TRADING_PREFERENCES = TradingPreferences().model_dump()
DEFAULT_STRATEGY_SCHEDULER_PREFERENCES = StrategySchedulerPreferences().model_dump()


class PreferenceService:
    def __init__(self, smart_selection_service: SmartSelectionService | None = None) -> None:
        self.smart_selection_service = smart_selection_service or SmartSelectionService()

    def get_preferences(self, db: Session, tenant_id: str = settings.default_tenant_id, user_id: int | None = None) -> PreferencesRead:
        preference = self._ensure_preferences(db, tenant_id, user_id)
        return self._serialize(db, preference, tenant_id, user_id)

    def update_preferences(
        self,
        db: Session,
        payload: PreferencesUpdate,
        tenant_id: str = settings.default_tenant_id,
        user_id: int | None = None,
    ) -> PreferencesRead:
        preference = self._ensure_preferences(db, tenant_id, user_id)

        if payload.trading is not None:
            current = self.trading_preferences(preference).model_dump()
            current.update(self._exclude_none(payload.trading))
            preference.trading_preferences = TradingPreferences(**current).model_dump()

        if payload.strategy_scheduler is not None:
            current = self.strategy_scheduler_preferences(preference).model_dump()
            current.update(self._exclude_none(payload.strategy_scheduler))
            preference.strategy_scheduler_preferences = StrategySchedulerPreferences(**current).model_dump()

        if payload.smart_selection is not None:
            self._update_smart_selection(db, tenant_id, payload.smart_selection, user_id)

        preference.updated_at = datetime.utcnow()
        db.add(preference)
        db.commit()
        db.refresh(preference)
        return self._serialize(db, preference, tenant_id, user_id)

    def trading_preferences(self, preference: AppPreference | None = None, db: Session | None = None, user_id: int | None = None) -> TradingPreferences:
        if preference is None:
            if db is None:
                return TradingPreferences()
            preference = self._ensure_preferences(db, settings.default_tenant_id, user_id)
        return TradingPreferences(**(preference.trading_preferences or {}))

    def strategy_scheduler_preferences(
        self,
        preference: AppPreference | None = None,
        db: Session | None = None,
        user_id: int | None = None,
    ) -> StrategySchedulerPreferences:
        if preference is None:
            if db is None:
                return StrategySchedulerPreferences()
            preference = self._ensure_preferences(db, settings.default_tenant_id, user_id)
        return StrategySchedulerPreferences(**(preference.strategy_scheduler_preferences or {}))

    def _ensure_preferences(self, db: Session, tenant_id: str, user_id: int | None = None) -> AppPreference:
        if user_id is None:
            preference = db.scalar(select(AppPreference).where(AppPreference.tenant_id == tenant_id, AppPreference.user_id.is_(None)))
        else:
            preference = db.scalar(select(AppPreference).where(AppPreference.user_id == user_id))
        if preference is None:
            preference = AppPreference(
                tenant_id=tenant_id,
                user_id=user_id,
                trading_preferences=TradingPreferences().model_dump(),
                strategy_scheduler_preferences=StrategySchedulerPreferences().model_dump(),
            )
            db.add(preference)
            db.commit()
            db.refresh(preference)
            return preference

        normalized_trading = TradingPreferences(**(preference.trading_preferences or {})).model_dump()
        normalized_scheduler = StrategySchedulerPreferences(**(preference.strategy_scheduler_preferences or {})).model_dump()
        if normalized_trading != (preference.trading_preferences or {}) or normalized_scheduler != (
            preference.strategy_scheduler_preferences or {}
        ):
            preference.trading_preferences = normalized_trading
            preference.strategy_scheduler_preferences = normalized_scheduler
            db.add(preference)
            db.commit()
            db.refresh(preference)
        return preference

    def _serialize(self, db: Session, preference: AppPreference, tenant_id: str, user_id: int | None = None) -> PreferencesRead:
        smart_selection_config = self.smart_selection_service.get_config(db, tenant_id, user_id)
        return PreferencesRead(
            tenant_id=tenant_id,
            trading=self.trading_preferences(preference),
            smart_selection=SmartSelectionPreferences(
                enabled=smart_selection_config.enabled,
                schedule_time=smart_selection_config.schedule_time,
                config_payload=smart_selection_config.config_payload,
            ),
            strategy_scheduler=self.strategy_scheduler_preferences(preference),
            updated_at=preference.updated_at.isoformat(),
        )

    def _update_smart_selection(
        self,
        db: Session,
        tenant_id: str,
        payload: SmartSelectionPreferencesUpdate,
        user_id: int | None = None,
    ) -> None:
        current = self.smart_selection_service.get_config(db, tenant_id, user_id)
        config_payload = deepcopy(current.config_payload)
        if payload.config_payload is not None:
            config_payload = payload.config_payload
        self.smart_selection_service.update_config(
            db,
            tenant_id,
            SmartSelectionConfigUpdate(enabled=payload.enabled, config_payload=config_payload),
            user_id=user_id,
        )

    @staticmethod
    def _exclude_none(
        payload: TradingPreferencesUpdate | StrategySchedulerPreferencesUpdate,
    ) -> dict[str, object]:
        return payload.model_dump(exclude_none=True)
