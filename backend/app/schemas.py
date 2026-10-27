"""API 请求 / 响应模型。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .business_schemas import KnowledgeScope


class HistoryMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=8000)


class AskRequest(KnowledgeScope):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(..., min_length=1, max_length=6000, description="用户问题")
    session: str | None = Field(default=None, min_length=1, max_length=120, description="会话名，留空则不落盘")
    top_k: int = Field(default=5, ge=1, le=20)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    similarity_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=12)


class SearchRequest(KnowledgeScope):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    similarity_threshold: float = Field(default=0.0, ge=0.0, le=1.0)


class ChunkOut(BaseModel):
    chunk_index: int
    content: str


class ChunkHit(BaseModel):
    id: str
    content: str
    source: str
    chunk_index: int
    similarity: float
    distance: float


class DocumentOut(BaseModel):
    source: str
    chunks: int
    product_id: str | None = None
    version_id: str | None = None


class StatsOut(BaseModel):
    total_chunks: int
    sources: int
    space: str
    embedding_model: str


class MessageIn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(max_length=20000)
    sources: list[str] = Field(default_factory=list)
    contexts: list[dict] = Field(default_factory=list)


class SessionSaveRequest(KnowledgeScope):
    messages: list[MessageIn] = Field(max_length=1000)


class SessionSummary(BaseModel):
    name: str
    message_count: int
    created_at: str = ""
    updated_at: str = ""


class SessionDetail(BaseModel):
    name: str
    id: str | None = None
    product_id: str | None = None
    version_id: str | None = None
    created_at: str = ""
    updated_at: str = ""
    messages: list[dict] = Field(default_factory=list)


class UploadResult(BaseModel):
    filename: str
    chunks: int
    ok: bool
    error: str | None = None


class UploadResponse(BaseModel):
    results: list[UploadResult]
    total_chunks: int
    failed: int
