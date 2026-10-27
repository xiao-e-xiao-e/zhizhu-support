"""FastAPI 应用入口。

启动：
    cd backend
    .venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
接口文档：
    http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .routers import chat, documents, sessions
from .routers import config as system_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时预热嵌入模型，避免首个请求卡在模型加载/下载上。"""
    from .services.embedding import get_embedding_service

    try:
        dimension = await asyncio.to_thread(get_embedding_service().warmup)
        logger.info("嵌入模型就绪，向量维度 %d", dimension)
    except Exception:  # noqa: BLE001 - 预热失败不阻止服务启动
        logger.exception("嵌入模型预热失败，相关接口将在首次调用时重试")

    # 校验向量集合的距离空间。旧版用默认 L2 空间建的空集合会被自动重建为 cosine，
    # 否则 `1 - distance` 的相似度换算会一直错下去且没有任何提示。
    try:
        from .services import vectorstore

        info = await asyncio.to_thread(vectorstore.describe_collection)
        logger.info(
            "向量集合 %s 就绪 | 距离空间=%s | 当前 %d 条",
            info["name"],
            info["space"],
            info["count"],
        )
    except Exception:  # noqa: BLE001
        logger.exception("向量集合校验失败，相关接口将在首次调用时报错")

    yield


settings = get_settings()

app = FastAPI(
    title="RAG 知识库问答 API",
    description="基于向量检索增强生成的本地知识库问答服务",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system_router.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(sessions.router)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "service": "RAG 知识库问答 API",
        "version": "2.0.0",
        "docs": "/docs",
    }
