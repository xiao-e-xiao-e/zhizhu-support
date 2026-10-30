"""Persist assistant tool runs as ordinary, owner-scoped conversation turns."""

import re

from fastapi import HTTPException
from sqlalchemy import select

from ..core.database import session_factory
from ..models import AgentRun, Conversation, Message, utcnow
from . import sessions


def name_for_run(question, run_id):
    title = re.sub(r"[/\\\x00-\x1f]", " ", question).strip()[:50] or "对话"
    return f"{title} · {run_id[:8]}"


def conversation(db, run):
    item = (
        db.get(Conversation, run.input.get("conversation_id")) if run.input.get("conversation_id") else None
    )
    return item if item and item.owner_id == run.owner_id else None


def message(db, run):
    item = conversation(db, run)
    return (
        db.scalar(
            select(Message).where(
                Message.assistant_run_id == run.id,
                Message.conversation_id == item.id,
                Message.role == "assistant",
            )
        )
        if item
        else None
    )


def attach(db, user, run, name):
    item = db.scalar(
        select(Conversation)
        .where(
            Conversation.owner_id == user.id,
            Conversation.name == name,
        )
        .with_for_update()
    )
    if item:
        if not sessions.visible(db, item, user.id):
            raise HTTPException(404, "会话不存在")
        if (item.product_id, item.version_id) != (run.product_id, run.version_id):
            raise HTTPException(409, "请新建会话后切换产品或版本")
    else:
        item = Conversation(owner_id=user.id, name=name, product_id=run.product_id, version_id=run.version_id)
        db.add(item)
        db.flush()
    rows = list(
        db.scalars(
            select(Message).where(Message.conversation_id == item.id).order_by(Message.id.desc()).limit(12)
        )
    )
    history, budget = [], 12000
    for row in rows:
        if not row.content:
            continue
        content = row.content
        linked = db.get(AgentRun, row.assistant_run_id) if row.assistant_run_id else None
        if linked and linked.owner_id == user.id:
            if linked.ticket_id:
                content += f"\n[本轮由用户确认提交的新工单编号：{linked.ticket_id}]"
            statuses = linked.result.get("ticket_statuses") or (
                [linked.result["ticket_status"]] if linked.result.get("ticket_status") else []
            )
            for status in statuses[:5]:
                content += f"\n[本轮查询过的工单：{status['id']}，标题：{status['title']}]"
            for ticket in linked.result.get("related_tickets", [])[:5]:
                content += f"\n[仅作为相似案例参考的历史工单：{ticket['id']}，标题：{ticket['title']}；不是本轮新建工单]"
        text = content[: min(4000, budget)]
        if not text:
            break
        history.append({"role": row.role, "content": text})
        budget -= len(text)
    run.input = {**run.input, "session": name, "conversation_id": item.id, "history": list(reversed(history))}
    db.add(Message(conversation_id=item.id, role="user", content=run.input["question"]))
    db.flush()
    db.add(Message(conversation_id=item.id, role="assistant", content="", assistant_run_id=run.id))
    item.updated_at = utcnow()
    db.flush()


def sync(db, run):
    row = message(db, run)
    if row:
        row.content = run.result.get("answer") or run.error or ""
        row.sources = run.result.get("sources", [])
        row.contexts = run.result.get("contexts", [])
        item = conversation(db, run)
        item.updated_at = utcnow()


def adopt_history():
    """Idempotently expose actual legacy assistant runs in the shared history."""
    count = 0
    with session_factory()() as db, db.begin():
        for run in db.scalars(
            select(AgentRun).where(AgentRun.kind == "assistant", AgentRun.retired.is_(False))
        ):
            if run.input.get("session") or run.input.get("conversation_id"):
                continue
            name = name_for_run(run.input.get("question", "历史记录"), run.id)
            existing = db.scalar(
                select(Conversation.id).where(
                    Conversation.owner_id == run.owner_id, Conversation.name == name
                )
            )
            if existing:
                raise RuntimeError("历史记录名称冲突，不会接管已有会话")
            item = Conversation(
                owner_id=run.owner_id,
                name=name,
                product_id=run.product_id,
                version_id=run.version_id,
                created_at=run.created_at,
                updated_at=run.updated_at,
            )
            db.add(item)
            db.flush()
            run.input = {**run.input, "session": name, "conversation_id": item.id, "history": []}
            db.add(
                Message(
                    conversation_id=item.id,
                    role="user",
                    content=run.input.get("question", ""),
                    created_at=run.created_at,
                )
            )
            db.flush()
            db.add(
                Message(
                    conversation_id=item.id,
                    role="assistant",
                    assistant_run_id=run.id,
                    content=run.result.get("answer") or run.error or "",
                    sources=run.result.get("sources", []),
                    contexts=run.result.get("contexts", []),
                    created_at=run.updated_at,
                )
            )
            count += 1
    return count
