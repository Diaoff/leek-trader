from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.account import Account
from app.schemas.account import AccountRead

router = APIRouter(prefix="/accounts")


@router.get("", response_model=list[AccountRead])
def list_accounts(db: Session = Depends(get_db)) -> list[AccountRead]:
    accounts = db.scalars(select(Account).order_by(Account.id)).all()
    return [AccountRead.model_validate(account) for account in accounts]
