"""身份、产品知识范围、对话、工单与反馈实体。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .core.database import Base


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None) -> str:
    if value is None:
        return ""
    # SQLite 不保留 tzinfo；统一声明为 UTC，避免浏览器当成本地时间。
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'staff', 'user')", name="ck_user_role"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    restrict_products: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DemoResource(Base):
    """显式记录演示资料归属，避免依赖名称猜测或覆盖已有业务数据。"""
    __tablename__ = "demo_resources"
    __table_args__ = (Index("ix_demo_resource_target", "kind", "resource_id"),)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24))
    resource_id: Mapped[str] = mapped_column(String(120))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LoginFailure(Base):
    __tablename__ = "login_failures"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ip_hash: Mapped[str] = mapped_column(String(64), index=True)
    username_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_conversation_owner_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"))
    version_id: Mapped[str | None] = mapped_column(ForeignKey("product_versions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_message_role"),
        Index("ix_message_conversation_created", "conversation_id", "created_at", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    contexts: Mapped[list] = mapped_column(JSON, default=list)
    assistant_run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProductVersion(Base):
    __tablename__ = "product_versions"
    __table_args__ = (UniqueConstraint("product_id", "name", name="uq_product_version_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProductGrant(Base):
    __tablename__ = "product_grants"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("status IN ('new', 'in_progress', 'resolved', 'closed')", name="ck_ticket_status"),
        CheckConstraint("priority IN ('low', 'normal', 'high')", name="ck_ticket_priority"),
        UniqueConstraint("creator_id", "idempotency_key", name="uq_ticket_creator_key"),
        Index("ix_ticket_status_updated", "status", "updated_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    creator_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    version_id: Mapped[str | None] = mapped_column(ForeignKey("product_versions.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    status: Mapped[str] = mapped_column(String(16), default="new")
    conversation_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __mapper_args__ = {"version_id_col": revision}


class TicketEvent(Base):
    __tablename__ = "ticket_events"
    __table_args__ = (
        CheckConstraint("kind IN ('created', 'comment', 'status', 'assigned')", name="ck_ticket_event_kind"),
        Index("ix_ticket_event_ticket_id", "ticket_id", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_feedback_user_message"),
        CheckConstraint("rating IN ('helpful', 'unresolved')", name="ck_feedback_rating"),
        Index("ix_feedback_rating_updated", "rating", "updated_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    ticket_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.id", ondelete="SET NULL"))
    rating: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(1000), default="")
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(180))
    scope_key: Mapped[str] = mapped_column(String(64), unique=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), index=True)
    version_id: Mapped[str | None] = mapped_column(ForeignKey("product_versions.id"))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    next_number: Mapped[int] = mapped_column(default=1)
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __mapper_args__ = {"version_id_col": revision}


class DocumentRevision(Base):
    __tablename__ = "document_revisions"
    __table_args__ = (
        UniqueConstraint("document_id", "number", name="uq_document_revision_number"),
        CheckConstraint("state IN ('queued','processing','ready','published','superseded','failed')", name="ck_revision_state"),
        Index("uq_document_published", "document_id", unique=True,
              sqlite_where=text("state = 'published'"), postgresql_where=text("state = 'published'")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    number: Mapped[int] = mapped_column()
    filename: Mapped[str] = mapped_column(String(180))
    sha256: Mapped[str] = mapped_column(String(64))
    raw_path: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(default=0)
    chunk_size: Mapped[int] = mapped_column(default=500)
    chunk_overlap: Mapped[int] = mapped_column(default=100)
    chunks: Mapped[int] = mapped_column(default=0)
    state: Mapped[str] = mapped_column(String(16), default="queued")
    retired: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    embedding_model: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    published_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint("state IN ('queued','running','succeeded','failed')", name="ck_ingestion_job_state"),
        Index("ix_job_claim", "state", "available_at", "lease_until"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    revision_id: Mapped[str] = mapped_column(ForeignKey("document_revisions.id"), unique=True)
    state: Mapped[str] = mapped_column(String(16), default="queued")
    phase: Mapped[str] = mapped_column(String(40), default="等待处理")
    progress: Mapped[int] = mapped_column(default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeEvent(Base):
    __tablename__ = "knowledge_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    revision_id: Mapped[str | None] = mapped_column(ForeignKey("document_revisions.id"))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("owner_id", "request_key", name="uq_agent_owner_request"),
        CheckConstraint("kind IN ('assistant','faq')", name="ck_agent_kind"),
        CheckConstraint("status IN ('queued','running','awaiting_confirmation','completed','failed','cancelled')", name="ck_agent_status"),
        Index("ix_agent_owner_created", "owner_id", "created_at"),
        Index("uq_agent_active_owner", "owner_id", unique=True,
              sqlite_where=text("kind = 'assistant' AND status IN ('queued','running')"),
              postgresql_where=text("kind = 'assistant' AND status IN ('queued','running')")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(16), default="assistant")
    retired: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    request_key: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    model: Mapped[str] = mapped_column(String(200))
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"))
    version_id: Mapped[str | None] = mapped_column(ForeignKey("product_versions.id"))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    ticket_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.id"))
    confirmation_hash: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(String(500))
    revision: Mapped[int] = mapped_column(default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __mapper_args__ = {"version_id_col": revision}


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "number", name="uq_agent_step_number"),
        CheckConstraint("status IN ('running','succeeded','failed','awaiting_confirmation')", name="ck_agent_step_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column()
    name: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(24), default="running")
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(500))
    elapsed_ms: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FAQDraft(Base):
    __tablename__ = "faq_drafts"
    __table_args__ = (
        CheckConstraint("state IN ('generating','failed','draft','review','rejected','indexing','published')", name="ck_faq_state"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.id", ondelete="SET NULL"), unique=True)
    source_resolution_id: Mapped[int | None] = mapped_column(ForeignKey("ticket_events.id", ondelete="SET NULL"))
    source_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    question: Mapped[str] = mapped_column(String(240), default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(16), default="draft")
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"))
    version_id: Mapped[str | None] = mapped_column(ForeignKey("product_versions.id"))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_note: Mapped[str] = mapped_column(String(1000), default="")
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id"))
    revision_id: Mapped[str | None] = mapped_column(ForeignKey("document_revisions.id"))
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __mapper_args__ = {"version_id_col": revision}


class FAQEvent(Base):
    __tablename__ = "faq_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    faq_id: Mapped[str] = mapped_column(ForeignKey("faq_drafts.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
