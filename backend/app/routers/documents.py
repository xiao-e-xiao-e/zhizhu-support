"""文档管理路由：上传、列表、分块预览、删除、检索调试。"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..schemas import (
    ChunkHit,
    ChunkOut,
    DocumentOut,
    SearchRequest,
    StatsOut,
    UploadResponse,
    UploadResult,
)
from ..services import vectorstore
from ..services.parser import parse_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _safe_name(raw: str | None) -> str:
    """只保留文件名部分，防止路径穿越。"""
    return Path(raw or "unnamed").name or "unnamed"


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    files: list[UploadFile] = File(...),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(100),
) -> UploadResponse:
    """上传并入库。单个文件失败不影响其他文件。"""
    results: list[UploadResult] = []
    total_chunks = 0
    failed = 0

    for upload in files:
        name = _safe_name(upload.filename)
        try:
            content = await upload.read()
            if not content:
                raise ValueError("文件内容为空")

            chunks = parse_file(
                name,
                content,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            if not chunks:
                raise ValueError("未能从文件中提取到有效文本")

            count = vectorstore.add_documents(name, chunks)
            total_chunks += count
            results.append(UploadResult(filename=name, chunks=count, ok=True))
        except Exception as exc:  # noqa: BLE001 - 逐文件兜底，失败要回传给前端
            logger.exception("解析入库失败: %s", name)
            failed += 1
            results.append(
                UploadResult(filename=name, chunks=0, ok=False, error=str(exc))
            )

    return UploadResponse(results=results, total_chunks=total_chunks, failed=failed)


@router.post("/preview")
async def preview_document(
    file: UploadFile = File(...),
    limit: int = Form(2000),
) -> dict:
    """只解析预览，不写入向量库。"""
    from ..services.parser import extract_text

    name = _safe_name(file.filename)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    try:
        text = extract_text(name, content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"解析失败: {exc}") from exc

    return {
        "filename": name,
        "characters": len(text),
        "truncated": len(text) > limit,
        "text": text[:limit],
    }


@router.get("", response_model=list[DocumentOut])
async def list_documents() -> list[DocumentOut]:
    return [DocumentOut(**row) for row in vectorstore.list_documents()]


@router.get("/stats", response_model=StatsOut)
async def get_stats() -> StatsOut:
    return StatsOut(**vectorstore.get_stats())


@router.post("/search", response_model=list[ChunkHit])
async def search_documents(payload: SearchRequest) -> list[ChunkHit]:
    hits = vectorstore.search(
        payload.query,
        top_k=payload.top_k,
        similarity_threshold=payload.similarity_threshold,
    )
    return [ChunkHit(**hit) for hit in hits]


@router.get("/{filename}/chunks", response_model=list[ChunkOut])
async def get_document_chunks(filename: str) -> list[ChunkOut]:
    rows = vectorstore.get_document_chunks(_safe_name(filename))
    if not rows:
        raise HTTPException(status_code=404, detail=f"未找到文档: {filename}")
    return [ChunkOut(**row) for row in rows]


@router.delete("/{filename}")
async def delete_document(filename: str) -> dict:
    deleted = vectorstore.delete_document(_safe_name(filename))
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"未找到文档: {filename}")
    return {"deleted_chunks": deleted, "filename": filename}
