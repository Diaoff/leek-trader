from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.db import get_db
from app.models.user import User
from app.reporting.service import ReportingService
from app.schemas.reporting import EquityCurvePoint, EventLogRead, PeriodStat, ReportingSummary

router = APIRouter(prefix="/reporting")
service = ReportingService()


@router.get("/summary", response_model=ReportingSummary)
def get_reporting_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ReportingSummary:
    return ReportingSummary(**service.get_summary(db, current_user.id))


@router.get("/equity-curve", response_model=list[EquityCurvePoint])
def get_equity_curve(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[EquityCurvePoint]:
    return [EquityCurvePoint(**item) for item in service.get_equity_curve(db, current_user.id)]


@router.get("/monthly-stats", response_model=list[PeriodStat])
def get_monthly_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[PeriodStat]:
    return [PeriodStat(**item) for item in service.get_monthly_stats(db, current_user.id)]


@router.get("/yearly-stats", response_model=list[PeriodStat])
def get_yearly_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[PeriodStat]:
    return [PeriodStat(**item) for item in service.get_yearly_stats(db, current_user.id)]


@router.get("/export/trades.csv")
def export_trades_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    csv_payload = service.export_trades_csv(db, current_user.id)
    return Response(
        content=csv_payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="trades.csv"'},
    )


@router.get("/events", response_model=list[EventLogRead])
def get_reporting_events(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    strategy_id: int | None = Query(default=None),
    strategy_run_id: int | None = Query(default=None),
    order_id: int | None = Query(default=None),
    symbol: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[EventLogRead]:
    return [
        EventLogRead(**item)
        for item in service.list_events(
            db,
            user_id=current_user.id,
            start_at=start_at,
            end_at=end_at,
            strategy_id=strategy_id,
            strategy_run_id=strategy_run_id,
            order_id=order_id,
            symbol=symbol,
            event_type=event_type,
            correlation_id=correlation_id,
        )
    ]
