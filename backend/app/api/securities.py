from fastapi import APIRouter, Query

from app.market.security_catalog import search_securities
from app.schemas.security import SecuritySearchResult

router = APIRouter(prefix="/securities")


@router.get("/search", response_model=list[SecuritySearchResult])
def search_security(q: str = Query(min_length=1)) -> list[SecuritySearchResult]:
    return [SecuritySearchResult(**item) for item in search_securities(q)]
