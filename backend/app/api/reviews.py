from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.config import settings
from app.core.db import get_db
from app.models.daily_review import DailyReview
from app.models.user import User
from app.schemas.review import DailyReviewListRead, DailyReviewRead

router = APIRouter(prefix="/reviews")


@router.get("/daily", response_model=DailyReviewListRead)
def list_daily_reviews(
    review_date: date | None = None,
    symbol: str | None = None,
    strategy_id: int | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DailyReviewListRead:
    safe_limit = max(1, min(limit, 100))
    query = select(DailyReview).where(
        DailyReview.tenant_id == settings.default_tenant_id,
        DailyReview.user_id == current_user.id,
    )
    if review_date is not None:
        query = query.where(DailyReview.review_date == review_date)
    if symbol:
        query = query.where(DailyReview.symbol == symbol.strip())
    if strategy_id is not None:
        query = query.where(DailyReview.strategy_id == strategy_id)

    reviews = db.scalars(query.order_by(desc(DailyReview.review_date), desc(DailyReview.id)).limit(safe_limit)).all()
    return DailyReviewListRead(reviews=[DailyReviewRead.model_validate(item) for item in reviews])


@router.get("/daily/{review_id}", response_model=DailyReviewRead)
def get_daily_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DailyReviewRead:
    review = db.scalar(
        select(DailyReview).where(
            DailyReview.id == review_id,
            DailyReview.tenant_id == settings.default_tenant_id,
            DailyReview.user_id == current_user.id,
        )
    )
    if review is None:
        raise HTTPException(status_code=404, detail="daily review not found")
    return DailyReviewRead.model_validate(review)
