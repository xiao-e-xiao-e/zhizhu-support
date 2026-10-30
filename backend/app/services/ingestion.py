"""数据库租约队列：原子领取、心跳、失效恢复以及幂等向量写入。"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select, update

from ..core.config import get_settings
from ..core.database import session_factory
from ..models import DocumentRevision, IngestionJob, KnowledgeDocument, WorkerHeartbeat, utcnow
from .embedding import get_embedding_service
from .knowledge import event, read_original
from .parser import parse_file
from .vectorstore import upsert_revision

logger = logging.getLogger(__name__)


def heartbeat(worker_id):
    with session_factory()() as db, db.begin():
        row = db.get(WorkerHeartbeat, worker_id)
        if row:
            row.last_seen = utcnow()
        else:
            db.add(WorkerHeartbeat(id=worker_id, last_seen=utcnow()))


def claim():
    now = utcnow()
    eligible = or_(
        and_(IngestionJob.state == "queued", IngestionJob.available_at <= now),
        and_(IngestionJob.state == "running", IngestionJob.lease_until < now),
    )
    with session_factory()() as db, db.begin():
        candidates = list(
            db.scalars(select(IngestionJob.id).where(eligible).order_by(IngestionJob.created_at).limit(20))
        )
        for job_id in candidates:
            token = str(uuid4())
            changed = db.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id, eligible)
                .values(
                    state="running",
                    lease_token=token,
                    lease_until=now + timedelta(seconds=get_settings().job_lease_seconds),
                    attempts=IngestionJob.attempts + 1,
                    phase="读取文件",
                    progress=5,
                    updated_at=now,
                )
            )
            if changed.rowcount:
                job = db.get(IngestionJob, job_id)
                if job.attempts > job.max_attempts:
                    job.state, job.phase, job.error = (
                        "failed",
                        "重试次数已耗尽",
                        "任务多次中断，请检查 worker 后手动重试",
                    )
                    job.lease_until, job.lease_token = None, None
                    db.get(DocumentRevision, job.revision_id).state = "failed"
                    continue
                db.get(DocumentRevision, job.revision_id).state = "processing"
                return job_id, token
    return None


def renew(job_id, token, phase=None, progress=None):
    with session_factory()() as db, db.begin():
        values = {
            "lease_until": utcnow() + timedelta(seconds=get_settings().job_lease_seconds),
            "updated_at": utcnow(),
        }
        if phase:
            values.update(phase=phase, progress=progress)
        result = db.execute(
            update(IngestionJob)
            .where(
                IngestionJob.id == job_id,
                IngestionJob.state == "running",
                IngestionJob.lease_token == token,
                IngestionJob.lease_until > utcnow(),
            )
            .values(**values)
        )
        return bool(result.rowcount)


def finish(job_id, token, count=0, error=None):
    with session_factory()() as db, db.begin():
        job = db.scalar(
            select(IngestionJob)
            .where(
                IngestionJob.id == job_id,
                IngestionJob.state == "running",
                IngestionJob.lease_token == token,
                IngestionJob.lease_until > utcnow(),
            )
            .with_for_update()
        )
        if not job:
            return False
        rev = db.get(DocumentRevision, job.revision_id)
        if error:
            again = job.attempts < job.max_attempts
            job.state, rev.state = ("queued", "queued") if again else ("failed", "failed")
            job.phase, job.error = ("等待自动重试" if again else "入库失败"), error
            if again:
                job.progress = 0
            job.available_at = utcnow() + timedelta(seconds=min(300, 5 * 2**job.attempts))
        else:
            job.state, job.phase, job.progress = "succeeded", "入库完成，待发布", 100
            job.error = None
            rev.state, rev.chunks, rev.embedding_model = "ready", count, get_settings().embedding_model
        job.lease_token, job.lease_until, job.updated_at = None, None, utcnow()
        event(
            db,
            db.get(KnowledgeDocument, rev.document_id),
            "index_failed" if error else "index_ready",
            revision=rev.id,
        )
        return True


def run_once():
    lease = claim()
    if not lease:
        return False
    job_id, token = lease
    stopped, lost = threading.Event(), threading.Event()

    def keep_alive():
        while not stopped.wait(get_settings().job_lease_seconds / 3):
            try:
                if not renew(job_id, token):
                    lost.set()
                    return
            except Exception:
                logger.exception("任务租约续期失败")
                lost.set()
                return

    thread = threading.Thread(target=keep_alive, daemon=True)
    thread.start()
    try:
        with session_factory()() as db:
            job = db.get(IngestionJob, job_id)
            revision = db.get(DocumentRevision, job.revision_id)
            content = read_original(revision)
        chunks = parse_file(revision.filename, content, revision.chunk_size, revision.chunk_overlap)
        if not chunks:
            raise ValueError("未提取到有效文本，扫描 PDF 需先进行 OCR")
        if not renew(job_id, token, "生成向量", 25):
            return True
        embeddings = get_embedding_service().embed_documents(chunks)
        if lost.is_set() or not renew(job_id, token, "写入向量", 80):
            return True
        upsert_revision(
            revision.document_id, revision.id, revision.number, revision.filename, chunks, embeddings
        )
        finish(job_id, token, len(chunks))
    except Exception as exc:
        logger.exception("任务入库失败 job=%s", job_id)
        # 不将第三方服务地址、密钥或底层异常全文回传给客户端。
        error = (
            str(exc)[:300] if isinstance(exc, ValueError) else "文档处理失败，请检查 worker 日志和存储连接"
        )
        finish(job_id, token, error=error)
    finally:
        stopped.set()
        thread.join(timeout=2)
    return True
