from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.preferences.service import PreferenceService
from app.schemas.preferences import PreferencesRead, PreferencesUpdate

router = APIRouter(prefix="/preferences")
service = PreferenceService()


@router.get("", response_model=PreferencesRead)
def get_preferences(db: Session = Depends(get_db)) -> PreferencesRead:
    return service.get_preferences(db, settings.default_tenant_id)


@router.put("", response_model=PreferencesRead)
def update_preferences(payload: PreferencesUpdate, db: Session = Depends(get_db)) -> PreferencesRead:
    return service.update_preferences(db, payload, settings.default_tenant_id)
