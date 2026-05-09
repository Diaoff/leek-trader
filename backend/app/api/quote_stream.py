from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.market.service import QuoteService

router = APIRouter(prefix="/quotes")
service = QuoteService()


@router.websocket("/stream")
async def stream_quotes(
    websocket: WebSocket,
    symbols: list[str] = Query(default=[]),
    interval_seconds: float = Query(default=5.0, ge=1.0, le=60.0),
) -> None:
    await websocket.accept()
    target_symbols = list(dict.fromkeys(symbols or settings.market_refresh_symbol_list))
    try:
        await websocket.send_json({"type": "subscribed", "symbols": target_symbols, "interval_seconds": interval_seconds})
        while True:
            quotes = service.list_quotes(target_symbols) if target_symbols else []
            await websocket.send_json({"type": "quotes", "symbols": target_symbols, "quotes": [quote.model_dump() for quote in quotes]})
            await asyncio.sleep(interval_seconds)
    except WebSocketDisconnect:
        return
