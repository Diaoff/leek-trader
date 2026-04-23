import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.ai.service import AiAnalysisService
from app.core.config import settings
from app.core.db import get_db
from app.schemas.ai import AiChatRequest, AiChatResponse, AiConfigRead, AiConfigUpdate, AiStockAnalysisRequest, AiStockAnalysisResponse

router = APIRouter(prefix="/ai")
service = AiAnalysisService()


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/config", response_model=AiConfigRead)
def get_ai_config(db: Session = Depends(get_db)) -> AiConfigRead:
    return service.get_config(db, settings.default_tenant_id)


@router.put("/config", response_model=AiConfigRead)
def update_ai_config(payload: AiConfigUpdate, db: Session = Depends(get_db)) -> AiConfigRead:
    return service.update_config(db, settings.default_tenant_id, payload)


@router.post("/chat", response_model=AiChatResponse)
def chat_with_ai(payload: AiChatRequest, db: Session = Depends(get_db)) -> AiChatResponse:
    content, model = service.chat(db, settings.default_tenant_id, payload.messages)
    return AiChatResponse(content=content, model=model)


@router.post("/chat/stream")
def stream_chat_with_ai(payload: AiChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    chunks, model = service.stream_chat(db, settings.default_tenant_id, payload.messages)

    def event_stream():
        yield _sse("meta", {"model": model})
        try:
            for chunk in chunks:
                yield _sse("chunk", {"content": chunk})
        except Exception as exc:
            detail = getattr(exc, "detail", str(exc))
            yield _sse("error", {"detail": detail})
            return
        yield _sse("done", {"model": model})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/analyze-stock", response_model=AiStockAnalysisResponse)
def analyze_stock(payload: AiStockAnalysisRequest, db: Session = Depends(get_db)) -> AiStockAnalysisResponse:
    return service.analyze_stock(db, settings.default_tenant_id, payload.symbol, payload.note)


@router.post("/analyze-stock/stream")
def stream_analyze_stock(payload: AiStockAnalysisRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    response_stub, chunks, model = service.stream_analyze_stock(db, settings.default_tenant_id, payload.symbol, payload.note)

    def event_stream():
        yield _sse(
            "meta",
            {
                "model": model,
                "symbol": response_stub.symbol,
                "security": response_stub.security.model_dump(),
                "generated_at": response_stub.generated_at.isoformat(),
                "latest_price": response_stub.latest_price,
                "change_percent": response_stub.change_percent,
            },
        )
        try:
            for chunk in chunks:
                yield _sse("chunk", {"content": chunk})
        except Exception as exc:
            detail = getattr(exc, "detail", str(exc))
            yield _sse("error", {"detail": detail})
            return
        yield _sse("done", {"model": model})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
