from fastapi import APIRouter, Query

from app.market.service import QuoteService
from app.schemas.quote import QuoteRead

router = APIRouter(prefix="/quotes")
service = QuoteService()


@router.get("", response_model=list[QuoteRead])
def list_quotes(symbols: list[str] = Query(default=[])) -> list[QuoteRead]:
    return service.list_quotes(symbols)
