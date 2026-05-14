from __future__ import annotations

from fastapi import APIRouter, Query

from app.market.research_service import MarketResearchService
from app.schemas.market import DragonTigerListRead, DragonTigerSeatRead, DragonTigerStockRead, ResearchNorthboundSummaryRead, ResearchStatusRead, StockFundFlowRead

router = APIRouter()
research_service = MarketResearchService()


@router.get("/research/fund-flow", response_model=StockFundFlowRead)
def get_stock_fund_flow(symbol: str = Query(..., min_length=1)) -> StockFundFlowRead:
    payload = research_service.get_stock_fund_flow(symbol)
    return StockFundFlowRead(
        source=payload.source,
        symbol=payload.symbol,
        trade_date=payload.trade_date,
        main_net_inflow=payload.main_net_inflow,
        super_large_net_inflow=payload.super_large_net_inflow,
        large_net_inflow=payload.large_net_inflow,
        medium_net_inflow=payload.medium_net_inflow,
        small_net_inflow=payload.small_net_inflow,
        main_net_ratio=payload.main_net_ratio,
        status=ResearchStatusRead(code=payload.status.code, notes=payload.status.notes),
    )


@router.get("/research/dragon-tiger", response_model=DragonTigerListRead)
def get_dragon_tiger(
    trade_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    symbol: str | None = Query(default=None, min_length=1),
) -> DragonTigerListRead:
    payload = research_service.get_dragon_tiger(trade_date=trade_date, symbol=symbol)
    items = [
        DragonTigerStockRead(
            source=item.source,
            symbol=item.symbol,
            stock_name=item.stock_name,
            trade_date=item.trade_date,
            reason=item.reason,
            close_price=item.close_price,
            change_percent=item.change_percent,
            turnover_rate=item.turnover_rate,
            buy_amount=item.buy_amount,
            sell_amount=item.sell_amount,
            net_amount=item.net_amount,
            seats=[
                DragonTigerSeatRead(
                    seat_name=seat.seat_name,
                    role=seat.role,
                    amount=seat.amount,
                    net_amount=seat.net_amount,
                    tag=seat.tag,
                )
                for seat in item.seats
            ],
            status=ResearchStatusRead(code=item.status.code, notes=item.status.notes),
        )
        for item in payload.items
        if item.status.code == "ok" or item.symbol or item.trade_date
    ]
    return DragonTigerListRead(source=payload.source, trade_date=trade_date, symbol=symbol, items=items)


@router.get("/research/northbound", response_model=ResearchNorthboundSummaryRead)
def get_northbound_summary(
    start_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> ResearchNorthboundSummaryRead:
    payload = research_service.get_northbound_summary(start_date=start_date)
    return ResearchNorthboundSummaryRead(
        source=payload.source,
        trade_date=payload.trade_date,
        net_inflow=payload.net_inflow,
        unit=payload.unit,
        status=ResearchStatusRead(code=payload.status.code, notes=payload.status.notes),
    )
