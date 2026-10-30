"""Upgrade explicitly owned starter resources to ordinary business accounts and knowledge.

Run after a consistent backup. Unregistered users and resources are never changed.
Credentials are generated once and saved to private storage, never served by HTTP.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from sqlalchemy import delete, select

from ..core.auth import password_hasher
from ..core.config import BACKEND_DIR
from ..core.database import session_factory
from ..models import (
    AgentRun,
    AuthSession,
    Conversation,
    DemoResource,
    DocumentRevision,
    FAQDraft,
    FAQEvent,
    Feedback,
    KnowledgeDocument,
    Message,
    Product,
    ProductGrant,
    ProductVersion,
    Ticket,
    TicketEvent,
    User,
)
from . import faq, knowledge, rag
from .catalog import product_visible
from .demo import DOCS, owned, wait_ready

PROFILES = [
    ("demo_user", "chen.yu", "user", "atlas"),
    ("demo_other", "lin.wei", "user", "orion"),
    ("demo_staff", "wang.min", "staff", None),
    ("demo_admin", "zhao.ning", "admin", None),
]
PRODUCTS = {"atlas": "Atlas 智能客服平台", "orion": "Orion 协作空间"}
TICKETS = {
    "new": (
        "升级后登录仍提示 E401",
        "升级客户端后反复提示 E401，已退出并重新登录，仍无法进入工作台，请协助检查会话和账号状态。",
        "",
    ),
    "progress": (
        "DOCX 文档解析失败",
        "上传的 DOCX 处理失败，文件设置了打开密码。需要保留文档内容并完成知识入库。",
        "",
    ),
    "reset": (
        "密码重置链接已过期",
        "打开昨天收到的密码重置链接，页面提示链接失效，需要重新获取有效链接。",
        "Atlas 2.0 的重置链接有效期为 30 分钟。重新申请，并使用最新邮件中的链接完成重置。",
    ),
    "invite": (
        "成员邀请邮件未收到",
        "管理员发送成员邀请后未在收件箱找到邮件，检查垃圾邮件后找到邀请并加入空间。",
        "核对邮箱拼写，检查垃圾邮件及企业邮件隔离区，再请管理员重发邀请。Orion 1.0 邀请链接有效期为 24 小时，请使用最新链接加入。",
    ),
    "large": (
        "加入空间后无法查看项目",
        "已接受空间邀请，但无法打开交付项目。需要检查项目成员列表和访问角色。",
        "空间成员身份不会自动授予所有项目权限。请管理员在目标项目成员列表添加该成员，按职责分配协作者或只读角色，再刷新页面。",
    ),
}


def record(db, key):
    item = db.get(DemoResource, key)
    if not item:
        raise RuntimeError(f"缺少归属登记 {key}；不会按名称接管已有业务数据")
    return item


def accounts(credential_path):
    credential_path = Path(credential_path)
    with session_factory()() as db:
        for old, name, _, _ in PROFILES:
            marker = record(db, "user:" + old)
            existing = db.scalar(select(User).where(User.username == name))
            if existing and existing.id != marker.resource_id:
                raise RuntimeError(f"账号 {name} 已存在，不会覆盖")
        for code, name in PRODUCTS.items():
            marker = record(db, "product:" + code)
            existing = db.scalar(select(Product).where(Product.name == name))
            if existing and existing.id != marker.resource_id:
                raise RuntimeError(f"产品 {name} 已存在，不会覆盖")
        needs_credentials = any(
            not record(db, "user:" + old).details.get("business_v1") for old, *_ in PROFILES
        )
    if needs_credentials:
        credential_path.parent.mkdir(parents=True, exist_ok=True)
        if credential_path.exists():
            credentials = json.loads(credential_path.read_text(encoding="utf-8"))
        else:
            credentials = {name: secrets.token_urlsafe(15) for _, name, _, _ in PROFILES}
            with credential_path.open("x", encoding="utf-8") as target:
                json.dump(credentials, target, ensure_ascii=False, indent=2)
            credential_path.chmod(0o600)
        if any(name not in credentials for _, name, _, _ in PROFILES):
            raise RuntimeError("凭据文件不完整，请核对后继续")
    with session_factory()() as db, db.begin():
        for code, name in PRODUCTS.items():
            product = owned(db, "product:" + code, Product)
            if not record(db, "product:" + code).details.get("business_v1"):
                product.name = name
                product.description = (
                    "面向客户服务团队的产品知识、问题排查与工单协作平台。"
                    if code == "atlas"
                    else "面向项目团队的空间成员、项目权限与任务通知协作产品。"
                )
                record(db, "product:" + code).details = {"business_v1": True}
        for old, name, role, code in PROFILES:
            marker = record(db, "user:" + old)
            user = owned(db, marker.key, User)
            if not marker.details.get("business_v1"):
                user.username, user.role = name, role
                user.password_hash = password_hasher.hash(credentials[name])
                user.restrict_products = code is not None
                db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
                db.execute(delete(ProductGrant).where(ProductGrant.user_id == user.id))
                if code:
                    db.add(ProductGrant(user_id=user.id, product_id=owned(db, "product:" + code, Product).id))
                marker.kind, marker.details = "business_user", {"business_v1": True}
        for marker in db.scalars(select(DemoResource).where(DemoResource.kind == "run")):
            run = db.get(AgentRun, marker.resource_id)
            if run:
                run.retired = True


def stage_document(key, filename, content, admin_id):
    with session_factory()() as db, db.begin():
        marker = record(db, key)
        if marker.details.get("business_revision"):
            return marker.details["business_revision"]
        doc = owned(db, key, KnowledgeDocument)
        new_key = knowledge.scope_key(filename, doc.product_id, doc.version_id)
        conflict = db.scalar(
            select(KnowledgeDocument.id).where(
                KnowledgeDocument.scope_key == new_key, KnowledgeDocument.id != doc.id
            )
        )
        if conflict:
            raise RuntimeError(f"目标资料 {filename} 已存在，不会合并或覆盖")
        for revision in db.scalars(select(DocumentRevision).where(DocumentRevision.document_id == doc.id)):
            if revision.state == "published":
                revision.state = "superseded"
            revision.retired = True
        db.flush()
        doc.filename, doc.scope_key = filename, new_key
        doc.archived = False
        staged = knowledge.enqueue(filename, content, admin_id, doc.product_id, doc.version_id, db=db)
        marker.details = {**marker.details, "business_revision": staged["revision_id"], "business_v1": False}
        return staged["revision_id"]


def publish_document(key, admin_id):
    with session_factory()() as db, db.begin():
        marker = record(db, key)
        if marker.details.get("business_v1"):
            return
        doc = owned(db, key, KnowledgeDocument)
        knowledge.change(
            doc.id, "publish", admin_id, doc.revision, marker.details["business_revision"], db=db
        )
        marker.details = {**marker.details, "business_v1": True}


def documents(admin_id, *, inline, timeout):
    staged = []
    for file, _, _, old_name in DOCS:
        filename = old_name.removeprefix("演示-").replace("体验指南", "操作指南")
        content = (BACKEND_DIR / "business_documents" / file).read_bytes()
        staged.append(stage_document("document:" + file, filename, content, admin_id))
    wait_ready(staged, timeout=timeout, inline=inline)
    for file, *_ in DOCS:
        publish_document("document:" + file, admin_id)


def conversations():
    titles = {
        "login": "E401 登录问题排查",
        "upload": "DOCX 文档入库问题",
        "invitation": "空间成员邀请",
        "operations": "知识修订发布与回滚",
        "publication": "FAQ 审核与发布",
    }
    tasks = [("session:" + code, title) for code, title in titles.items()]
    # Personal history created through the old interface keeps its IDs and questions;
    # only conversations citing the exact registered legacy sources are refreshed.
    with session_factory()() as db, db.begin():
        owners = [owned(db, "user:" + old, User).id for old, *_ in PROFILES]
        registered = {
            m.resource_id
            for m in db.scalars(
                select(DemoResource).where(DemoResource.kind.in_(["session", "business_session"]))
            )
        }
        old_sources = {name for *_, name in DOCS}
        for convo in db.scalars(select(Conversation).where(Conversation.owner_id.in_(owners))):
            if convo.id in registered:
                continue
            rows = list(db.scalars(select(Message).where(Message.conversation_id == convo.id)))
            if any(old_sources.intersection(m.sources or []) for m in rows):
                key = "session:business-" + convo.id
                db.add(DemoResource(key=key, kind="business_session", resource_id=convo.id, details={}))
                tasks.append((key, convo.name))
        for marker in db.scalars(select(DemoResource).where(DemoResource.kind == "business_session")):
            if marker.key not in {key for key, _ in tasks}:
                tasks.append((marker.key, db.get(Conversation, marker.resource_id).name))
    for key, title in tasks:
        with session_factory()() as db:
            if record(db, key).details.get("business_v1"):
                continue
            convo = owned(db, key, Conversation)
            messages = list(
                db.scalars(select(Message).where(Message.conversation_id == convo.id).order_by(Message.id))
            )
            scope = (convo.product_id, convo.version_id, convo.owner_id)
            inaccessible = convo.product_id and not product_visible(db, convo.product_id, convo.owner_id)
        if inaccessible:
            with session_factory()() as db, db.begin():
                record(db, key).details = {"business_v1": True, "restricted_history": True}
            continue
        history = []
        updates = []
        for message in messages:
            if message.role == "user":
                question = message.content
                history.append({"role": "user", "content": question})
            else:
                result = rag.ask(
                    question, history=history[:-1], product_id=scope[0], version_id=scope[1], user_id=scope[2]
                )
                if not result["contexts"]:
                    raise RuntimeError("业务对话未检索到已发布资料，不写入无依据的历史回答")
                updates.append((message.id, result))
                history.append({"role": "assistant", "content": result["answer"]})
        with session_factory()() as db, db.begin():
            owned(db, key, Conversation).name = title
            for message_id, result in updates:
                message = db.get(Message, message_id)
                message.content, message.sources, message.contexts = (
                    result["answer"],
                    result["sources"],
                    result["contexts"],
                )
            record(db, key).details = {
                "business_v1": True,
                "generation": "rag",
                "usage": [r["usage"] for _, r in updates],
            }


def stories(admin_id):
    with session_factory()() as db, db.begin():
        for code, (title, description, solution) in TICKETS.items():
            key = "ticket:" + code
            if record(db, key).details.get("business_v1"):
                continue
            ticket = owned(db, key, Ticket)
            ticket.title, ticket.description = title, description
            if code == "large":
                ticket.product_id = owned(db, "product:orion", Product).id
                ticket.version_id = owned(db, "version:orion:1.0", ProductVersion).id
            for event in db.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)):
                if event.kind == "assigned":
                    event.content, event.details = (
                        "客服已接单",
                        {"to_assignee": "wang.min", "from_assignee": None},
                    )
                elif event.kind == "comment":
                    event.content = "已收到问题。请补充操作步骤和错误提示，附件请隐去账号凭据。"
                elif event.kind == "status":
                    target = event.details.get("to_status")
                    event.content = (
                        solution
                        if target == "resolved"
                        else "提交者确认问题已解决"
                        if target == "closed"
                        else "正在排查问题"
                    )
            if ticket.conversation_id:
                ticket.conversation_snapshot = [
                    {"role": m.role, "content": m.content, "sources": m.sources}
                    for m in db.scalars(
                        select(Message)
                        .where(Message.conversation_id == ticket.conversation_id)
                        .order_by(Message.id)
                    )
                ]
            record(db, key).details = {"business_v1": True}
        for code, reason in [
            ("unresolved", "重新登录后仍失败，已提交工单请求进一步排查。"),
            ("helpful", "已在垃圾邮件中找到邀请，成功加入空间。"),
        ]:
            key = "feedback:" + code
            if record(db, key).details.get("business_v1"):
                continue
            item = owned(db, key, Feedback)
            message = db.get(Message, item.message_id)
            item.answer, item.sources, item.reason = message.content, message.sources, reason
            record(db, key).details = {"business_v1": True}
        for code in ["reset", "large", "invite"]:
            key = "faq:" + code
            if record(db, key).details.get("business_v1"):
                continue
            item = owned(db, key, FAQDraft)
            ticket = db.get(Ticket, item.ticket_id)
            _, resolution, snapshot = faq.resolution_snapshot(db, db.get(User, admin_id), ticket.id)
            item.source_snapshot, item.source_resolution_id = snapshot, resolution.id
            item.product_id, item.version_id = ticket.product_id, ticket.version_id
            item.question = {
                "reset": "Atlas 2.0 密码重置链接失效怎么办？",
                "large": "Orion 1.0 加入空间后无法查看项目怎么办？",
                "invite": "Orion 1.0 收不到成员邀请邮件怎么办？",
            }[code]
            item.answer = TICKETS[code][2]
            item.review_note = "已核对解决步骤、适用版本与敏感信息" if code == "invite" else ""
            for event in db.scalars(select(FAQEvent).where(FAQEvent.faq_id == item.id)):
                if "演示" in event.note or "虚构" in event.note:
                    event.note = "已核对适用版本与解决步骤"
            record(db, key).details = {**record(db, key).details, "business_v1": True}


def prepare(credential_path, *, inline=False, timeout=180):
    accounts(credential_path)
    with session_factory()() as db:
        admin_id = owned(db, "user:demo_admin", User).id
    documents(admin_id, inline=inline, timeout=timeout)
    content = f"# Orion 1.0 收不到成员邀请邮件怎么办？\n\n{TICKETS['invite'][2]}\n".encode()
    revision_id = stage_document("document:faq-invite", "Orion-成员邀请常见问题.md", content, admin_id)
    wait_ready([revision_id], timeout=timeout, inline=inline)
    publish_document("document:faq-invite", admin_id)
    conversations()
    stories(admin_id)
    with session_factory()() as db:
        faq_id = owned(db, "faq:invite", FAQDraft).id
    with session_factory()() as db, db.begin():
        db.get(FAQDraft, faq_id).revision_id = revision_id
    return {
        "accounts": [name for _, name, _, _ in PROFILES],
        "published_documents": len(knowledge.documents()),
        "credentials_file": str(credential_path),
    }
