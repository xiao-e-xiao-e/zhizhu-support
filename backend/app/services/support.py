"""客服业务事务：归属校验、幂等建单、版本冲突与审计。"""

from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from ..models import (
    Conversation,
    Feedback,
    Message,
    Product,
    ProductVersion,
    Ticket,
    TicketEvent,
    User,
    iso_utc,
    utcnow,
)
from .catalog import validate_scope


def is_staff(user: User) -> bool:
    return user.role in {"admin", "staff"}


def visible_ticket(db, user, ticket_id, *, revision=None):
    ticket = (
        db.scalar(select(Ticket).where(Ticket.id == ticket_id).with_for_update())
        if revision
        else db.get(Ticket, ticket_id)
    )
    if not ticket or (not is_staff(user) and ticket.creator_id != user.id):
        raise HTTPException(404, "工单不存在")
    if revision is not None and ticket.revision != revision:
        raise HTTPException(409, "工单已被更新，请刷新后重试")
    return ticket


def ticket_outputs(db, tickets, *, detail=False):
    user_ids = {t.creator_id for t in tickets} | {t.assignee_id for t in tickets if t.assignee_id}
    users = {u.id: u.username for u in db.scalars(select(User).where(User.id.in_(user_ids)))}
    product_ids = {t.product_id for t in tickets if t.product_id}
    products = {p.id: p.name for p in db.scalars(select(Product).where(Product.id.in_(product_ids)))}
    version_ids = {t.version_id for t in tickets if t.version_id}
    versions = {
        v.id: v.name for v in db.scalars(select(ProductVersion).where(ProductVersion.id.in_(version_ids)))
    }
    result = []
    for ticket in tickets:
        item = {
            "id": ticket.id,
            "title": ticket.title,
            "priority": ticket.priority,
            "status": ticket.status,
            "creator_id": ticket.creator_id,
            "creator_name": users.get(ticket.creator_id, ""),
            "assignee_id": ticket.assignee_id,
            "assignee_name": users.get(ticket.assignee_id),
            "product_id": ticket.product_id,
            "product_name": products.get(ticket.product_id),
            "version_id": ticket.version_id,
            "version_name": versions.get(ticket.version_id),
            "revision": ticket.revision,
            "created_at": iso_utc(ticket.created_at),
            "updated_at": iso_utc(ticket.updated_at),
        }
        if detail:
            item.update(
                description=ticket.description,
                conversation_id=ticket.conversation_id,
                message_id=ticket.message_id,
                conversation_snapshot=ticket.conversation_snapshot,
            )
        result.append(item)
    return result


def ticket_output(db, ticket):
    return ticket_outputs(db, [ticket], detail=True)[0]


def _event(db, ticket, actor, kind, content="", **details):
    db.add(TicketEvent(ticket_id=ticket.id, actor_id=actor.id, kind=kind, content=content, details=details))
    if kind != "created":
        ticket.updated_at = utcnow()


def _commit(db):
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        raise HTTPException(409, "工单已被更新，请刷新后重试") from None


def _replay(db, user_id, key, fingerprint):
    existing = db.scalar(select(Ticket).where(Ticket.creator_id == user_id, Ticket.idempotency_key == key))
    if existing and existing.request_hash != fingerprint:
        raise HTTPException(409, "该提交标识已经用于其他内容，请重新创建工单")
    return existing


def create_ticket(db, user, payload, *, commit=True):
    fingerprint = hashlib.sha256(
        json.dumps(
            payload.model_dump(exclude={"idempotency_key"}), sort_keys=True, ensure_ascii=False
        ).encode()
    ).hexdigest()
    existing = _replay(db, user.id, payload.idempotency_key, fingerprint)
    if existing:
        return ticket_output(db, existing), False
    product_id, version_id = payload.product_id, payload.version_id
    conversation = None
    snapshot = []
    if payload.conversation_name:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.owner_id == user.id, Conversation.name == payload.conversation_name
            )
        )
        if not conversation:
            raise HTTPException(404, "关联会话不存在")
        validate_scope(db, conversation.product_id, conversation.version_id, user.id)
        if payload.message_id:
            message = db.get(Message, payload.message_id)
            if not message or message.conversation_id != conversation.id or message.role != "assistant":
                raise HTTPException(404, "关联回答不存在")
        if not product_id:
            product_id, version_id = conversation.product_id, conversation.version_id
        rows_query = select(Message).where(Message.conversation_id == conversation.id)
        if payload.message_id:
            rows_query = rows_query.where(Message.id <= payload.message_id)
        rows = db.scalars(rows_query.order_by(Message.id.desc()).limit(12)).all()
        budget = 16000
        for message in rows:
            content = message.content[: min(4000, budget)]
            if not content:
                break
            snapshot.append({"role": message.role, "content": content, "sources": message.sources[:20]})
            budget -= len(content)
        snapshot.reverse()
    validate_scope(db, product_id, version_id, user.id)
    ticket = Ticket(
        creator_id=user.id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        product_id=product_id,
        version_id=version_id,
        conversation_id=conversation.id if conversation else None,
        message_id=payload.message_id,
        conversation_snapshot=snapshot,
        idempotency_key=payload.idempotency_key,
        request_hash=fingerprint,
    )
    db.add(ticket)
    try:
        db.flush()
        _event(db, ticket, user, "created", "工单已提交", priority=ticket.priority)
        if payload.message_id:
            feedback = db.scalar(
                select(Feedback).where(Feedback.user_id == user.id, Feedback.message_id == payload.message_id)
            )
            if feedback:
                feedback.ticket_id = ticket.id
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError:
        db.rollback()
        existing = _replay(db, user.id, payload.idempotency_key, fingerprint)
        if existing:
            return ticket_output(db, existing), False
        raise HTTPException(409, "关联数据发生变化，请刷新后重试") from None
    return ticket_output(db, ticket), True


def change_status(db, user, ticket_id, payload):
    ticket = visible_ticket(db, user, ticket_id, revision=payload.expected_revision)
    old, target = ticket.status, payload.status
    allowed = {
        "new": {"in_progress"},
        "in_progress": {"resolved"},
        "resolved": {"in_progress", "closed"},
        "closed": set(),
    }
    if target not in allowed[old]:
        raise HTTPException(409, "当前状态不允许该变更")
    if target == "closed":
        if ticket.creator_id != user.id:
            raise HTTPException(403, "只能由工单提交者确认关闭")
    elif target == "resolved" or old == "new":
        if not is_staff(user):
            raise HTTPException(403, "只有客服可以处理和解决工单")
    if target == "resolved" and not payload.note:
        raise HTTPException(422, "请填写解决说明")
    ticket.status = target
    _event(db, ticket, user, "status", payload.note, from_status=old, to_status=target)
    _commit(db)
    return ticket_output(db, ticket)


def assign_ticket(db, user, ticket_id, payload):
    if not is_staff(user):
        raise HTTPException(403, "只有客服可以分配工单")
    ticket = visible_ticket(db, user, ticket_id, revision=payload.expected_revision)
    if ticket.status == "closed":
        raise HTTPException(409, "已关闭的工单不能重新分配")
    assignee = db.get(User, payload.assignee_id) if payload.assignee_id else None
    if payload.assignee_id and (not assignee or not assignee.is_active or not is_staff(assignee)):
        raise HTTPException(422, "处理人必须是有效的客服或管理员")
    if ticket.assignee_id == payload.assignee_id:
        return ticket_output(db, ticket)
    previous = ticket.assignee_id
    previous_user = db.get(User, previous) if previous else None
    ticket.assignee_id = payload.assignee_id
    _event(
        db,
        ticket,
        user,
        "assigned",
        from_assignee=previous_user.username if previous_user else None,
        to_assignee=assignee.username if assignee else None,
    )
    if ticket.status == "new" and assignee:
        ticket.status = "in_progress"
        _event(db, ticket, user, "status", "客服已接单", from_status="new", to_status="in_progress")
    _commit(db)
    return ticket_output(db, ticket)


def add_comment(db, user, ticket_id, payload):
    ticket = visible_ticket(db, user, ticket_id, revision=payload.expected_revision)
    if ticket.status == "closed":
        raise HTTPException(409, "工单已关闭，不能继续回复")
    _event(db, ticket, user, "comment", payload.content)
    _commit(db)
    return ticket_output(db, ticket)


def feedback_output(db, feedback):
    owner = db.get(User, feedback.user_id)
    return {
        "id": feedback.id,
        "message_id": feedback.message_id,
        "rating": feedback.rating,
        "reason": feedback.reason,
        "question": feedback.question,
        "answer": feedback.answer,
        "sources": feedback.sources,
        "ticket_id": feedback.ticket_id,
        "user_name": owner.username,
        "updated_at": iso_utc(feedback.updated_at),
    }


def save_feedback(db, user, message_id, payload):
    message = db.scalar(
        select(Message)
        .join(Conversation)
        .where(Message.id == message_id, Message.role == "assistant", Conversation.owner_id == user.id)
    )
    if not message:
        raise HTTPException(404, "回答不存在")
    previous_question = (
        db.scalar(
            select(Message.content)
            .where(
                Message.conversation_id == message.conversation_id,
                Message.role == "user",
                Message.id < message.id,
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        or ""
    )
    for attempt in range(2):
        feedback = db.scalar(
            select(Feedback).where(Feedback.user_id == user.id, Feedback.message_id == message_id)
        )
        if feedback is None:
            feedback = Feedback(
                user_id=user.id,
                message_id=message_id,
                conversation_id=message.conversation_id,
                question=previous_question,
                answer=message.content,
                sources=list(message.sources),
            )
            db.add(feedback)
        feedback.rating, feedback.reason, feedback.updated_at = payload.rating, payload.reason, utcnow()
        try:
            db.commit()
            return feedback_output(db, feedback)
        except IntegrityError:
            db.rollback()
            if attempt:
                raise HTTPException(409, "回答记录发生变化，请刷新后重试") from None
    raise RuntimeError("反馈保存失败")


def list_feedback(db, user, rating, page, page_size):
    conditions = [] if is_staff(user) else [Feedback.user_id == user.id]
    if rating:
        conditions.append(Feedback.rating == rating)
    total = db.scalar(select(func.count()).select_from(Feedback).where(*conditions))
    rows = db.scalars(
        select(Feedback)
        .where(*conditions)
        .order_by(Feedback.updated_at.desc(), Feedback.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [feedback_output(db, f) for f in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
