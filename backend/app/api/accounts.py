from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.db import get_db
from app.models.account import Account
from app.models.user import User
from app.schemas.account import AccountRead

router = APIRouter(prefix="/accounts")


@router.get("", response_model=list[AccountRead])
def list_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[AccountRead]:
    accounts = db.scalars(select(Account).where(Account.user_id == current_user.id).order_by(Account.id)).all()
    return [AccountRead.model_validate(account) for account in accounts]
