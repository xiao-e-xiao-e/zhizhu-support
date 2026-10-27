"""用户隔离的数据库会话。每次操作使用独立事务，流式生成不持有连接。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from ..core.database import session_factory
from ..models import AgentRun, AgentStep, Conversation, Feedback, Message, User, iso_utc, utcnow
from .catalog import product_visible, validate_scope


def _iso(value) -> str:
    return iso_utc(value)


def _find(db, owner_id: str, name: str, *, lock: bool = False):
    query = select(Conversation).where(Conversation.owner_id == owner_id, Conversation.name == name)
    return db.scalar(query.with_for_update() if lock else query)


def visible(db, conversation, owner_id):
    if conversation is None or (
        conversation.product_id and not product_visible(db, conversation.product_id, owner_id)
    ):
        return False
    user = db.get(User, owner_id)
    if user is None:
        return False
    condition = AgentRun.retired.is_(True)
    if user.role not in {"admin", "staff"}:
        condition = condition | AgentRun.input["staff_only"].as_boolean().is_(True)
    return not db.scalar(
        select(AgentRun.id)
        .join(Message, Message.assistant_run_id == AgentRun.id)
        .where(Message.conversation_id == conversation.id, condition)
        .limit(1)
    )


def ensure_access(owner_id, name):
    with session_factory()() as db:
        conversation = _find(db, owner_id, name)
        if conversation is not None and not visible(db, conversation, owner_id):
            raise HTTPException(404, "会话不存在")


def _messages(db, conversation_id: str) -> list[dict]:
    from .agent import run_out

    rows = db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    ).all()
    feedback = {
        f.message_id: {"rating": f.rating, "reason": f.reason, "ticket_id": f.ticket_id}
        for f in db.scalars(select(Feedback).where(Feedback.message_id.in_([m.id for m in rows])))
    }
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "sources": m.sources,
            "contexts": m.contexts,
            "feedback": feedback.get(m.id),
            "run": run_out(db, run)
            if m.assistant_run_id and (run := db.get(AgentRun, m.assistant_run_id))
            else None,
        }
        for m in rows
    ]


def list_sessions(owner_id: str) -> list[dict]:
    with session_factory()() as db:
        rows = db.execute(
            select(Conversation, func.count(Message.id))
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .where(Conversation.owner_id == owner_id)
            .group_by(Conversation.id)
            .order_by(Conversation.updated_at.desc())
        ).all()
        return [
            {
                "name": c.name,
                "message_count": count,
                "created_at": _iso(c.created_at),
                "updated_at": _iso(c.updated_at),
            }
            for c, count in rows
            if visible(db, c, owner_id)
        ]


def get_session(owner_id: str, name: str) -> dict | None:
    with session_factory()() as db:
        conversation = _find(db, owner_id, name)
        if not visible(db, conversation, owner_id):
            return None
        return {
            "id": conversation.id,
            "name": conversation.name,
            "product_id": conversation.product_id,
            "version_id": conversation.version_id,
            "created_at": _iso(conversation.created_at),
            "updated_at": _iso(conversation.updated_at),
            "messages": _messages(db, conversation.id),
        }


def _write(owner_id: str, name: str, messages: list[dict], *, append: bool, scope=None) -> dict:
    # 同名会话首次并发创建时，唯一约束决定赢家；失败事务重试一次。
    for attempt in range(2):
        try:
            with session_factory()() as db, db.begin():
                conversation = _find(db, owner_id, name, lock=True)
                if conversation is not None and not visible(db, conversation, owner_id):
                    raise HTTPException(404, "会话不存在")
                if not append and conversation is not None and active_runs(db, conversation.id):
                    raise HTTPException(409, "请先完成或取消当前回复与工单草稿，再修改会话")
                if scope is not None:
                    validate_scope(db, *scope, owner_id)
                if conversation is None:
                    conversation = Conversation(owner_id=owner_id, name=name)
                    if scope is not None:
                        conversation.product_id, conversation.version_id = scope
                    db.add(conversation)
                    db.flush()
                else:
                    if scope is not None and scope != (conversation.product_id, conversation.version_id):
                        raise ValueError("当前会话的产品范围已确定，请新建会话后切换产品")
                    if not append:
                        existing = db.scalars(
                            select(Message)
                            .where(Message.conversation_id == conversation.id)
                            .order_by(Message.id)
                        ).all()
                        prefix = 0
                        for old, incoming in zip(existing, messages, strict=False):
                            if any(
                                getattr(old, key)
                                != incoming.get(key, [] if key in {"sources", "contexts"} else "")
                                for key in ("role", "content", "sources", "contexts")
                            ):
                                break
                            prefix += 1
                        # 未变化的消息保留 ID 和反馈；删除或重生成的消息仅移除关联，工单快照保留。
                        remove_ids = [m.id for m in existing[prefix:]]
                        if remove_ids:
                            db.execute(delete(Message).where(Message.id.in_(remove_ids)))
                        messages = messages[prefix:]
                written = []
                for message in messages:
                    row = Message(
                        conversation_id=conversation.id,
                        role=message["role"],
                        content=message["content"],
                        sources=message.get("sources", []),
                        contexts=message.get("contexts", []),
                    )
                    db.add(row)
                    written.append(row)
                conversation.updated_at = utcnow()
                db.flush()
                written_ids = [row.id for row in written]
            result = get_session(owner_id, name)
            if append:
                result["written_message_ids"] = written_ids
            return result
        except IntegrityError:
            if attempt:
                raise
    raise RuntimeError("会话保存失败")


def save_session(owner_id: str, name: str, messages: list[dict], *, scope=None) -> dict:
    return _write(owner_id, name, messages, append=False, scope=scope)


def append_messages(owner_id: str, name: str, messages: list[dict], *, scope=None) -> dict:
    return _write(owner_id, name, messages, append=True, scope=scope)


def delete_session(owner_id: str, name: str) -> bool:
    with session_factory()() as db, db.begin():
        conversation = _find(db, owner_id, name, lock=True)
        if not visible(db, conversation, owner_id):
            return False
        for run in active_runs(db, conversation.id):
            run.status, run.error_code, run.error = "cancelled", "cancelled", "会话已删除；没有自动创建工单。"
            for step in db.scalars(
                select(AgentStep).where(
                    AgentStep.run_id == run.id, AgentStep.status.in_(["running", "awaiting_confirmation"])
                )
            ):
                step.status, step.error = "failed", "会话已删除"
        db.delete(conversation)
        return True


def recent_history(owner_id: str, name: str | None, limit: int = 12, budget: int = 16000) -> list[dict]:
    if not name:
        return []
    with session_factory()() as db:
        conversation = _find(db, owner_id, name)
        if conversation is None:
            return []
        if not visible(db, conversation, owner_id):
            raise HTTPException(404, "会话不存在")
        rows = db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.id.desc())
            .limit(limit)
        ).all()
        history = []
        for row in rows:
            if len(row.content) > budget:
                break
            history.append({"role": row.role, "content": row.content})
            budget -= len(row.content)
        return list(reversed(history))


def export_markdown(owner_id: str, name: str) -> str | None:
    session = get_session(owner_id, name)
    if session is None:
        return None
    lines = [f"# {name}", "", f"导出时间：{utcnow().isoformat()}", ""]
    for message in session["messages"]:
        role = "👤 用户" if message["role"] == "user" else "🤖 助手"
        lines.extend([f"## {role}", "", message["content"], ""])
        if message["sources"]:
            lines.extend([f"> 参考来源：{', '.join(message['sources'])}", ""])
        run = message.get("run")
        if run:
            if run.get("ticket_id"):
                lines.extend([f"> 已确认提交的工单：{run['ticket_id']}", ""])
            statuses = run["result"].get("ticket_statuses") or (
                [run["result"]["ticket_status"]] if run["result"].get("ticket_status") else []
            )
            for ticket in statuses:
                lines.extend(
                    [
                        f"> [{ticket.get('citation', '工单')}] {ticket['title']} · {ticket['id']} · {ticket['status']}",
                        "",
                    ]
                )
        lines.extend(["---", ""])
    return "\n".join(lines)


def active_runs(db, conversation_id):
    return list(
        db.scalars(
            select(AgentRun)
            .join(Message, Message.assistant_run_id == AgentRun.id)
            .where(
                Message.conversation_id == conversation_id,
                AgentRun.status.in_(["queued", "running", "awaiting_confirmation"]),
            )
        )
    )


def rename_session(owner_id, name, new_name):
    try:
        with session_factory()() as db, db.begin():
            conversation = _find(db, owner_id, name, lock=True)
            if not visible(db, conversation, owner_id):
                raise HTTPException(404, "会话不存在")
            if active_runs(db, conversation.id):
                raise HTTPException(409, "请先完成或取消当前回复与工单草稿")
            if name != new_name and _find(db, owner_id, new_name):
                raise HTTPException(409, "已有同名会话，请使用其他名称")
            conversation.name, conversation.updated_at = new_name, utcnow()
    except IntegrityError:
        raise HTTPException(409, "已有同名会话，请使用其他名称") from None
    result = get_session(owner_id, new_name)
    if result is None:
        raise HTTPException(404, "会话不存在")
    return result
