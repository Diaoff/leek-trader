from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.reporting.service import ReportingService
from app.schemas.reporting import EquityCurvePoint, PeriodStat, ReportingSummary

router = APIRouter(prefix="/reporting")
service = ReportingService()


@router.get("/summary", response_model=ReportingSummary)
def get_reporting_summary(db: Session = Depends(get_db)) -> ReportingSummary:
    return ReportingSummary(**service.get_summary(db))


@router.get("/equity-curve", response_model=list[EquityCurvePoint])
def get_equity_curve(db: Session = Depends(get_db)) -> list[EquityCurvePoint]:
    return [EquityCurvePoint(**item) for item in service.get_equity_curve(db)]


@router.get("/monthly-stats", response_model=list[PeriodStat])
def get_monthly_stats(db: Session = Depends(get_db)) -> list[PeriodStat]:
    return [PeriodStat(**item) for item in service.get_monthly_stats(db)]


@router.get("/yearly-stats", response_model=list[PeriodStat])
def get_yearly_stats(db: Session = Depends(get_db)) -> list[PeriodStat]:
    return [PeriodStat(**item) for item in service.get_yearly_stats(db)]
