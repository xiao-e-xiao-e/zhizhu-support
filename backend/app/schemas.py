"""API 请求 / 响应模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LLMOverride(BaseModel):
    api_key: str | None = None
    api_base_url: str | None = None
    chat_model: str | None = None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户问题")
    session: str | None = Field(default=None, description="会话名，留空则不落盘")
    top_k: int = Field(default=5, ge=1, le=20)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    similarity_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    llm: LLMOverride | None = None


class SearchRequest(BaseModel):
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


class StatsOut(BaseModel):
    total_chunks: int
    sources: int
    space: str
    embedding_model: str


class MessageIn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str
    sources: list[str] = Field(default_factory=list)
    contexts: list[dict] = Field(default_factory=list)


class SessionSaveRequest(BaseModel):
    messages: list[MessageIn]


class SessionSummary(BaseModel):
    name: str
    message_count: int
    created_at: str = ""
    updated_at: str = ""


class SessionDetail(BaseModel):
    name: str
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
