from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user
from app.core.db import get_db
from app.models.user import User
from app.reporting.service import ReportingService
from app.schemas.reporting import EquityCurvePoint, PeriodStat, ReportingSummary

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
