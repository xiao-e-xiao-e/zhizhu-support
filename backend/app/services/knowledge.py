"""知识资料登记、不可变修订与发布门禁；SQL 是可检索性的唯一依据。"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from ..core.config import get_settings
from ..core.database import session_factory
from ..models import (
    DocumentRevision,
    IngestionJob,
    KnowledgeDocument,
    KnowledgeEvent,
    Product,
    ProductVersion,
    WorkerHeartbeat,
    iso_utc,
    utcnow,
)
from . import vectorstore
from .catalog import product_visible, validate_scope


@contextmanager
def _transaction(existing=None):
    if existing is not None:
        yield existing
    else:
        with session_factory()() as db, db.begin():
            yield db


def scope_key(filename, product_id, version_id):
    return hashlib.sha256(
        json.dumps([filename, product_id, version_id], ensure_ascii=False).encode()
    ).hexdigest()


def resolve(db, key):
    doc = db.get(KnowledgeDocument, key)
    if doc:
        return doc
    docs = list(db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.filename == key)))
    if len(docs) > 1:
        raise HTTPException(409, "同名资料有多个分类，请使用文档 ID")
    if not docs:
        raise HTTPException(404, "文档不存在")
    return docs[0]


def active_scope(db, doc):
    return (not doc.product_id or bool((p := db.get(Product, doc.product_id)) and p.is_active)) and (
        not doc.version_id or bool((v := db.get(ProductVersion, doc.version_id)) and v.is_active)
    )


def event(db, doc, action, actor=None, revision=None):
    db.add(KnowledgeEvent(document_id=doc.id, revision_id=revision, actor_id=actor, action=action))
    doc.updated_at = utcnow()


def job_out(job):
    return {
        "id": job.id,
        "revision_id": job.revision_id,
        "state": job.state,
        "phase": job.phase,
        "progress": job.progress,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "error": job.error,
        "available_at": iso_utc(job.available_at),
        "updated_at": iso_utc(job.updated_at),
    }


def revision_out(db, revision):
    job = db.scalar(select(IngestionJob).where(IngestionJob.revision_id == revision.id))
    return {
        "id": revision.id,
        "number": revision.number,
        "state": revision.state,
        "sha256": revision.sha256,
        "size_bytes": revision.size_bytes,
        "chunks": revision.chunks,
        "chunk_size": revision.chunk_size,
        "chunk_overlap": revision.chunk_overlap,
        "embedding_model": revision.embedding_model,
        "original_available": bool(revision.raw_path),
        "created_at": iso_utc(revision.created_at),
        "published_at": iso_utc(revision.published_at),
        "job": job_out(job) if job else None,
    }


def enqueue(
    filename: str,
    content: bytes,
    actor: str,
    product_id=None,
    version_id=None,
    chunk_size=500,
    chunk_overlap=100,
    *,
    db=None,
):
    filename = re.split(r"[/\\]", filename)[-1].strip()
    if not filename or len(filename) > 180 or any(ord(c) < 32 for c in filename):
        raise ValueError("文件名必须为 1 至 180 个可见字符")
    if not content:
        raise ValueError("文件内容为空")
    if Path(filename).suffix.lower() not in {
        ".txt",
        ".md",
        ".markdown",
        ".pdf",
        ".docx",
        ".csv",
        ".html",
        ".htm",
    }:
        raise ValueError("不支持该文件格式")
    if not 100 <= chunk_size <= 3000 or not 0 <= chunk_overlap < chunk_size:
        raise ValueError("分块参数无效")
    digest = hashlib.sha256(content).hexdigest()
    raw = None
    try:
        with _transaction(db) as db:
            validate_scope(db, product_id, version_id, actor)
            key = scope_key(filename, product_id, version_id)
            doc = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.scope_key == key))
            if not doc:
                doc = KnowledgeDocument(
                    filename=filename, scope_key=key, product_id=product_id, version_id=version_id
                )
                db.add(doc)
                db.flush()
            if doc.archived:
                raise HTTPException(409, "请先恢复已归档文档")
            prior = db.scalar(
                select(DocumentRevision)
                .where(
                    DocumentRevision.document_id == doc.id,
                    DocumentRevision.sha256 == digest,
                    DocumentRevision.retired.is_(False),
                    DocumentRevision.chunk_size == chunk_size,
                    DocumentRevision.chunk_overlap == chunk_overlap,
                )
                .order_by(DocumentRevision.number.desc())
            )
            if prior:
                return {
                    "document_id": doc.id,
                    "revision_id": prior.id,
                    "deduplicated": True,
                    "revision": revision_out(db, prior),
                }
            revision = DocumentRevision(
                id=str(uuid4()),
                document_id=doc.id,
                number=doc.next_number,
                filename=filename,
                sha256=digest,
                size_bytes=len(content),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                created_by=actor,
            )
            doc.next_number += 1
            root = get_settings().document_storage_dir
            root.mkdir(parents=True, exist_ok=True)
            revision.raw_path = revision.id + ".bin"
            raw = root / revision.raw_path
            with raw.open("xb") as dest:
                dest.write(content)
            db.add(revision)
            db.flush()
            db.add(IngestionJob(revision_id=revision.id))
            event(db, doc, "upload", actor, revision.id)
            db.flush()
            return {
                "document_id": doc.id,
                "revision_id": revision.id,
                "deduplicated": False,
                "revision": revision_out(db, revision),
            }
    except (IntegrityError, StaleDataError) as exc:
        if raw:
            raw.unlink(missing_ok=True)
        raise HTTPException(409, "文档正在变更，请重试上传") from exc
    except Exception:
        if raw:
            raw.unlink(missing_ok=True)
        raise


def documents(staff=False, user_id=None):
    with session_factory()() as db:
        rows = []
        for doc in db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.updated_at.desc())):
            if not product_visible(db, doc.product_id, user_id):
                continue
            published = db.scalar(
                select(DocumentRevision).where(
                    DocumentRevision.document_id == doc.id,
                    DocumentRevision.state == "published",
                    DocumentRevision.retired.is_(False),
                )
            )
            if not staff and (doc.archived or not published or not active_scope(db, doc)):
                continue
            latest = (
                db.scalar(
                    select(DocumentRevision)
                    .where(DocumentRevision.document_id == doc.id, DocumentRevision.retired.is_(False))
                    .order_by(DocumentRevision.number.desc())
                )
                if staff
                else published
            )
            rows.append(
                {
                    "id": doc.id,
                    "source": doc.filename,
                    "chunks": published.chunks if published else 0,
                    "product_id": doc.product_id,
                    "version_id": doc.version_id,
                    "archived": doc.archived,
                    "revision": doc.revision,
                    "published_revision": published.number if published else None,
                    "published_revision_id": published.id if published else None,
                    "latest": revision_out(db, latest) if latest else None,
                }
            )
        return rows


def history(key):
    with session_factory()() as db:
        doc = resolve(db, key)
        return {
            "revision": doc.revision,
            "revisions": [
                revision_out(db, r)
                for r in db.scalars(
                    select(DocumentRevision)
                    .where(DocumentRevision.document_id == doc.id, DocumentRevision.retired.is_(False))
                    .order_by(DocumentRevision.number.desc())
                )
            ],
            "events": [
                {
                    "action": e.action,
                    "revision_id": e.revision_id,
                    "actor_id": e.actor_id,
                    "created_at": iso_utc(e.created_at),
                }
                for e in db.scalars(
                    select(KnowledgeEvent)
                    .where(KnowledgeEvent.document_id == doc.id)
                    .order_by(KnowledgeEvent.id.desc())
                    .limit(200)
                )
            ],
        }


def check_access(key, user_id):
    with session_factory()() as db:
        doc = resolve(db, key)
        if not product_visible(db, doc.product_id, user_id):
            raise HTTPException(404, "文档不存在")


def change(
    key, action, actor, expected_revision, revision_id=None, product_id=None, version_id=None, *, db=None
):
    try:
        with _transaction(db) as db:
            doc = resolve(db, key)
            if doc.revision != expected_revision:
                raise HTTPException(409, "文档已变更，请刷新后重试")
            current = db.scalar(
                select(DocumentRevision).where(
                    DocumentRevision.document_id == doc.id, DocumentRevision.state == "published"
                )
            )
            target = db.get(DocumentRevision, revision_id) if revision_id else None
            if revision_id and (not target or target.document_id != doc.id):
                raise HTTPException(404, "修订不存在")
            if action == "publish":
                validate_scope(db, doc.product_id, doc.version_id, actor)
                if (
                    doc.archived
                    or not target
                    or target.retired
                    or target.state not in {"ready", "superseded"}
                ):
                    raise HTTPException(409, "仅可发布入库完成的修订，请先恢复归档文档")
                if target.embedding_model != get_settings().embedding_model:
                    raise HTTPException(409, "嵌入模型已改变，请重新入库")
                if current:
                    current.state = "superseded"
                    db.flush()
                target.state = "published"
                target.published_at, target.published_by = utcnow(), actor
            elif action in {"withdraw", "archive"}:
                if current:
                    current.state = "ready"
                if action == "archive":
                    doc.archived = True
            elif action == "restore":
                doc.archived = False
            elif action == "scope":
                if current:
                    raise HTTPException(409, "请先撤回发布，再修改分类")
                validate_scope(db, product_id, version_id, actor)
                doc.product_id, doc.version_id = product_id, version_id
                doc.scope_key = scope_key(doc.filename, product_id, version_id)
            else:
                raise ValueError("未知文档操作")
            doc.revision += 1
            event(db, doc, action, actor, revision_id)
            db.flush()
            return {"revision": doc.revision, "ok": True}
    except (StaleDataError, IntegrityError) as exc:
        raise HTTPException(409, "文档已变更或目标分类中存在同名资料，请刷新重试") from exc


def read_original(revision):
    if not revision.raw_path:
        raise HTTPException(404, "旧资料没有保存原始文件")
    root = get_settings().document_storage_dir.resolve()
    path = (root / revision.raw_path).resolve()
    if path.parent != root or not path.is_file():
        raise ValueError("原始文件缺失")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != revision.sha256:
        raise ValueError("原始文件校验失败")
    return content


def original(key, revision_id):
    with session_factory()() as db:
        doc = resolve(db, key)
        revision = db.get(DocumentRevision, revision_id)
        if not revision or revision.retired or revision.document_id != doc.id:
            raise HTTPException(404, "修订不存在")
        return revision.filename, read_original(revision)


def eligible_revisions(product_id=None, version_id=None, user_id=None):
    with session_factory()() as db:
        query = (
            select(DocumentRevision.id, KnowledgeDocument)
            .join(KnowledgeDocument, DocumentRevision.document_id == KnowledgeDocument.id)
            .where(
                DocumentRevision.state == "published",
                DocumentRevision.retired.is_(False),
                KnowledgeDocument.archived.is_(False),
            )
        )
        if product_id:
            query = query.where(KnowledgeDocument.product_id == product_id)
        if version_id:
            query = query.where(KnowledgeDocument.version_id == version_id)
        return [
            rev
            for rev, doc in db.execute(query)
            if active_scope(db, doc) and product_visible(db, doc.product_id, user_id)
        ]


def search(query, top_k=5, similarity_threshold=0.0, product_id=None, version_id=None, user_id=None):
    ids = eligible_revisions(product_id, version_id, user_id)
    hits = vectorstore.search(query, top_k=top_k, similarity_threshold=similarity_threshold, revision_ids=ids)
    # 发布状态可能在向量检索期间被撤回；返回前再次检查。
    current = set(eligible_revisions(product_id, version_id, user_id))
    return [h for h in hits if h.get("revision_id") in current]


def chunks(key, staff=False, revision_id=None, user_id=None):
    with session_factory()() as db:
        doc = resolve(db, key)
        if not product_visible(db, doc.product_id, user_id):
            raise HTTPException(404, "文档不存在")
        query = select(DocumentRevision).where(
            DocumentRevision.document_id == doc.id, DocumentRevision.retired.is_(False)
        )
        if revision_id:
            query = query.where(DocumentRevision.id == revision_id)
        else:
            query = query.where(DocumentRevision.state == "published")
        rev = db.scalar(query)
        if not rev or (not staff and (rev.state != "published" or doc.archived or not active_scope(db, doc))):
            raise HTTPException(404, "无可查看的已发布修订")
        data = vectorstore.get_collection().get(
            where={"revision_id": rev.id}, include=["documents", "metadatas"]
        )
        return sorted(
            [
                {"chunk_index": meta["chunk_index"], "content": text}
                for meta, text in zip(data["metadatas"], data["documents"], strict=True)
            ],
            key=lambda row: row["chunk_index"],
        )


def queue_status(user_id=None):
    with session_factory()() as db:
        online = bool(
            db.scalar(
                select(WorkerHeartbeat.id).where(WorkerHeartbeat.last_seen > utcnow() - timedelta(seconds=60))
            )
        )
        jobs = list(
            db.scalars(
                select(IngestionJob)
                .join(DocumentRevision, IngestionJob.revision_id == DocumentRevision.id)
                .where(DocumentRevision.retired.is_(False))
                .order_by(IngestionJob.created_at.desc())
                .limit(100)
            )
        )
        if user_id is not None:
            jobs = [
                j
                for j in jobs
                if product_visible(
                    db,
                    db.get(KnowledgeDocument, db.get(DocumentRevision, j.revision_id).document_id).product_id,
                    user_id,
                )
            ]
        return {"worker_online": online, "jobs": [job_out(j) for j in jobs]}


def retry_job(job_id, actor):
    with session_factory()() as db, db.begin():
        job = db.get(IngestionJob, job_id)
        if not job:
            raise HTTPException(404, "任务不存在")
        target = db.get(DocumentRevision, job.revision_id)
        if target.retired or not product_visible(
            db, db.get(KnowledgeDocument, target.document_id).product_id, actor
        ):
            raise HTTPException(404, "任务不存在")
        if job.state != "failed":
            raise HTTPException(409, "仅失败任务可以重试")
        result = db.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job_id, IngestionJob.state == "failed")
            .values(
                state="queued",
                phase="等待重试",
                progress=0,
                error=None,
                available_at=utcnow(),
                lease_until=None,
                lease_token=None,
                max_attempts=IngestionJob.attempts + 3,
                updated_at=utcnow(),
            )
        )
        if not result.rowcount:
            raise HTTPException(409, "任务已在重试中，请刷新")
        db.refresh(job)
        rev = db.get(DocumentRevision, job.revision_id)
        rev.state = "queued"
        event(db, db.get(KnowledgeDocument, rev.document_id), "retry", actor, rev.id)
        return job_out(job)


def adopt_legacy():
    """只补登记及元数据，不重写向量或虚构原始文件；可重复执行。"""
    collection = vectorstore.get_collection()
    data = collection.get(include=["documents", "metadatas"])
    count = 0
    with session_factory()() as db, db.begin():
        known = set(db.scalars(select(DocumentRevision.id)))
        groups = {}
        for i, meta in enumerate(data["metadatas"] or []):
            meta = meta or {}
            if meta.get("revision_id") in known:
                continue
            filename = meta.get("source") or "legacy.txt"
            group = (filename, meta.get("product_id") or None, meta.get("version_id") or None)
            groups.setdefault(group, []).append(i)
        for (filename, product_id, version_id), indexes in groups.items():
            validate_scope(db, product_id, version_id)
            key = scope_key(filename, product_id, version_id)
            doc = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.scope_key == key))
            if not doc:
                doc = KnowledgeDocument(
                    filename=filename, scope_key=key, product_id=product_id, version_id=version_id
                )
                db.add(doc)
                db.flush()
            existing = db.scalar(
                select(DocumentRevision.id).where(
                    DocumentRevision.document_id == doc.id, DocumentRevision.state == "published"
                )
            )
            rev = DocumentRevision(
                document_id=doc.id,
                number=doc.next_number,
                filename=filename,
                sha256=hashlib.sha256("\n".join(data["documents"][i] for i in indexes).encode()).hexdigest(),
                chunks=len(indexes),
                state="ready" if existing else "published",
                embedding_model=get_settings().embedding_model,
                published_at=None if existing else utcnow(),
            )
            doc.next_number += 1
            db.add(rev)
            db.flush()
            collection.update(
                ids=[data["ids"][i] for i in indexes],
                metadatas=[
                    {
                        **(data["metadatas"][i] or {}),
                        "document_id": doc.id,
                        "revision_id": rev.id,
                        "revision_number": rev.number,
                        "chunk_index": j,
                    }
                    for j, i in enumerate(indexes)
                ],
            )
            event(db, doc, "legacy_import", revision=rev.id)
            count += 1
    return count
