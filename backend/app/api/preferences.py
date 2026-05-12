from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.preferences.service import PreferenceService
from app.schemas.preferences import PreferencesRead, PreferencesUpdate, RiskRuleVersionRead

router = APIRouter(prefix="/preferences")
service = PreferenceService()


@router.get("", response_model=PreferencesRead)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PreferencesRead:
    return service.get_preferences(db, settings.default_tenant_id, current_user.id)


@router.put("", response_model=PreferencesRead)
def update_preferences(
    payload: PreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PreferencesRead:
    return service.update_preferences(db, payload, settings.default_tenant_id, current_user.id)


@router.get("/risk-rule-version", response_model=RiskRuleVersionRead)
def get_risk_rule_version(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RiskRuleVersionRead:
    return service.risk_rule_version(db=db, user_id=current_user.id)
