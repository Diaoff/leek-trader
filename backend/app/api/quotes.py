from fastapi import APIRouter, Query, Request

from app.market.service import QuoteService
from app.schemas.quote import QuoteRead

router = APIRouter(prefix="/quotes")
service = QuoteService()


@router.get("", response_model=list[QuoteRead])
def list_quotes(request: Request, symbols: list[str] = Query(default=[])) -> list[QuoteRead]:
    legacy_symbols = request.query_params.getlist("symbols[]")
    target_symbols = list(dict.fromkeys([*symbols, *legacy_symbols]))
    return service.list_quotes(target_symbols)
