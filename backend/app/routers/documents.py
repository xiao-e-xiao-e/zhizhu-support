"""文档异步入库、修订审阅与发布。"""

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from ..business_schemas import KnowledgeScope
from ..core.auth import current_user, require_admin, require_staff
from ..core.config import get_settings
from ..core.database import session_factory
from ..models import User
from ..schemas import SearchRequest
from ..services import knowledge
from ..services.catalog import validate_scope
from ..services.parser import extract_text

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    revision_id: str | None = None


class ScopeAction(KnowledgeScope):
    revision: int = Field(ge=1)


async def _read_upload(upload):
    limit = get_settings().max_upload_mb * 1024 * 1024
    content = await upload.read(limit + 1)
    if len(content) > limit:
        raise ValueError(f"单文件不能超过 {get_settings().max_upload_mb} MB")
    return content


@router.post("/upload", status_code=202)
async def upload_documents(
    files: list[UploadFile] = File(...),
    chunk_size: int = Form(500, ge=100, le=3000),
    chunk_overlap: int = Form(100, ge=0, le=1000),
    product_id: str | None = Form(None),
    version_id: str | None = Form(None),
    user: User = Depends(require_staff),
):
    if len(files) > 10 or chunk_overlap >= chunk_size:
        raise HTTPException(422, "单次最多上传 10 个文件，且重叠必须小于块大小")
    with session_factory()() as db:
        validate_scope(db, product_id, version_id, user.id)
    results = []
    for upload in files:
        try:
            content = await _read_upload(upload)
            result = await run_in_threadpool(
                knowledge.enqueue,
                upload.filename or "unnamed.txt",
                content,
                user.id,
                product_id,
                version_id,
                chunk_size,
                chunk_overlap,
            )
            results.append({"filename": upload.filename, "chunks": 0, "ok": True, **result})
        except (ValueError, HTTPException) as exc:
            results.append(
                {
                    "filename": upload.filename,
                    "chunks": 0,
                    "ok": False,
                    "error": str(exc) if isinstance(exc, ValueError) else exc.detail,
                }
            )
        finally:
            await upload.close()
    return {"results": results, "total_chunks": 0, "failed": sum(not r["ok"] for r in results)}


@router.post("/preview", dependencies=[Depends(require_staff)])
async def preview_document(file: UploadFile = File(...), limit: int = Form(2000, ge=1, le=10000)):
    try:
        content = await _read_upload(file)
        if not content:
            raise ValueError("文件内容为空")
        text = await run_in_threadpool(extract_text, Path(file.filename or "unnamed").name, content)
        return {
            "filename": file.filename,
            "characters": len(text),
            "truncated": len(text) > limit,
            "text": text[:limit],
        }
    except Exception as exc:
        raise HTTPException(400, "文件解析失败，请检查大小与格式") from exc
    finally:
        await file.close()


@router.get("")
def list_documents(user: User = Depends(current_user)):
    return knowledge.documents(user.role in {"staff", "admin"}, user.id)


@router.get("/stats")
def stats(user: User = Depends(current_user)):
    docs = knowledge.documents(user_id=user.id)
    return {
        "total_chunks": sum(d["chunks"] for d in docs),
        "sources": len(docs),
        "space": "cosine",
        "embedding_model": get_settings().embedding_model,
    }


@router.get("/jobs")
def jobs(user: User = Depends(require_staff)):
    return knowledge.queue_status(user.id)


@router.post("/jobs/{job_id}/retry")
def retry(job_id: str, user: User = Depends(require_staff)):
    return knowledge.retry_job(job_id, user.id)


@router.post("/search")
def search(payload: SearchRequest, user: User = Depends(current_user)):
    with session_factory()() as db:
        validate_scope(db, payload.product_id, payload.version_id, user.id)
    return knowledge.search(
        payload.query,
        payload.top_k,
        payload.similarity_threshold,
        payload.product_id,
        payload.version_id,
        user.id,
    )


@router.get("/{key}/revisions")
def revisions(key: str, user: User = Depends(require_staff)):
    knowledge.check_access(key, user.id)
    return knowledge.history(key)


@router.get("/{key}/revisions/{revision_id}/original")
def original(key: str, revision_id: str, user: User = Depends(require_staff)):
    knowledge.check_access(key, user.id)
    try:
        name, content = knowledge.original(key, revision_id)
    except ValueError as exc:
        raise HTTPException(409, "原始文件缺失或校验失败，请联系管理员") from exc
    return Response(
        content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{key}/{action}")
def action(key: str, action: str, payload: DocumentAction, user: User = Depends(require_admin)):
    knowledge.check_access(key, user.id)
    if action not in {"publish", "withdraw", "archive", "restore"}:
        raise HTTPException(404, "操作不存在")
    return knowledge.change(key, action, user.id, payload.revision, payload.revision_id)


@router.patch("/{key}/scope")
def scope(key: str, payload: ScopeAction, user: User = Depends(require_staff)):
    knowledge.check_access(key, user.id)
    return knowledge.change(
        key, "scope", user.id, payload.revision, product_id=payload.product_id, version_id=payload.version_id
    )


@router.get("/{key}/chunks")
def chunks(key: str, revision_id: str | None = None, user: User = Depends(current_user)):
    return knowledge.chunks(key, user.role in {"staff", "admin"}, revision_id, user.id)


@router.delete("/{key}")
def archive(key: str, revision: int = Query(ge=1), user: User = Depends(require_admin)):
    knowledge.check_access(key, user.id)
    return knowledge.change(key, "archive", user.id, revision)
