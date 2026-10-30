"""配置与健康检查路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..core.auth import current_user
from ..core.config import get_settings
from ..core.database import session_factory
from ..services import vectorstore
from ..services.embedding import get_embedding_service

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
def ready():
    try:
        with session_factory()() as db:
            db.execute(text("SELECT 1 FROM users LIMIT 1"))
    except Exception:
        return JSONResponse({"status": "unavailable", "database": "error"}, status_code=503)
    return {"status": "ok", "database": "ok"}


@router.get("/config", dependencies=[Depends(current_user)])
def get_config() -> dict:
    """返回前端需要的默认配置。API Key 永不回传，只回报是否已配置。"""
    settings = get_settings()

    embedding_dimension: int | None = None
    embedding_error: str | None = None
    try:
        embedding_dimension = get_embedding_service().dimension
    except Exception:  # noqa: BLE001 - 模型不可用不应拖垮整个配置接口
        embedding_error = "嵌入模型暂不可用，请联系管理员"

    try:
        collection = vectorstore.describe_collection()
    except Exception:  # noqa: BLE001
        collection = {"error": "向量库暂不可用，请联系管理员"}

    return {
        "llm_configured": settings.llm_ready,
        "api_base_url": settings.api_base_url,
        "chat_model": settings.chat_model,
        "embedding_model": settings.embedding_model,
        "embedding_dimension": embedding_dimension,
        "embedding_error": embedding_error,
        "max_tokens": settings.max_tokens,
        "defaults": {
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "top_k": settings.top_k,
            "temperature": settings.temperature,
            "similarity_threshold": settings.similarity_threshold,
        },
        "collection": collection,
    }
