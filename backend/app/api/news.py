from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.news.service import NewsProvider
from app.schemas.news import NewsBriefResponse, NewsFeedResponse

router = APIRouter(prefix="/news")
provider = NewsProvider()


@router.get("/market", response_model=NewsFeedResponse)
def get_market_news(limit: int = Query(default=20, ge=1, le=100)) -> NewsFeedResponse:
    return provider.get_market_feed(limit=limit)


@router.get("/search", response_model=NewsFeedResponse)
def search_news(keyword: str = Query(min_length=1), limit: int = Query(default=10, ge=1, le=50)) -> NewsFeedResponse:
    if not keyword.strip():
        raise HTTPException(status_code=422, detail="keyword cannot be empty")
    return provider.get_discussion_feed(keyword=keyword, limit=limit)


@router.get("/xueqiu", response_model=NewsFeedResponse)
def get_xueqiu_news(limit: int = Query(default=20, ge=1, le=100)) -> NewsFeedResponse:
    return provider.get_xueqiu_feed(limit=limit)


@router.get("/brief", response_model=NewsBriefResponse)
def get_news_brief(keyword: str = Query(min_length=1), limit: int = Query(default=10, ge=1, le=50)) -> NewsBriefResponse:
    if not keyword.strip():
        raise HTTPException(status_code=422, detail="keyword cannot be empty")
    return provider.get_brief(keyword=keyword, limit=limit)
