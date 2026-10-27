"""显式启用的本地演示：仅初始化有归属标记的样例，不覆盖真实账号或已编辑资料。"""

from __future__ import annotations

import time
from functools import lru_cache

from sqlalchemy import func, select

from ..business_schemas import TicketCreate
from ..core.auth import password_hasher, verify_password
from ..core.config import BACKEND_DIR, get_settings
from ..core.database import session_factory
from ..models import (
    AgentRun,
    Conversation,
    DemoResource,
    DocumentRevision,
    FAQDraft,
    Feedback,
    KnowledgeDocument,
    Message,
    Product,
    ProductVersion,
    Ticket,
    TicketEvent,
    User,
)
from ..workflow_schemas import FAQAction, FAQCreate, FAQReview, RunCreate
from . import agent, faq, ingestion, knowledge, support

DEMO_PASSWORD = "Demo@2026!Start"
ACCOUNTS = [
    {
        "username": "demo_user",
        "role": "user",
        "label": "普通用户 · Atlas",
        "description": "体验版本问答、本人会话和待处理工单",
    },
    {
        "username": "demo_staff",
        "role": "staff",
        "label": "客服",
        "description": "接单回复、检索相似工单、编辑 FAQ 草稿",
    },
    {
        "username": "demo_admin",
        "role": "admin",
        "label": "管理员",
        "description": "审核 FAQ、发布与回滚知识、管理账号",
    },
    {
        "username": "demo_other",
        "role": "user",
        "label": "另一位用户 · Orion",
        "description": "体验邀请排障和不同用户间的数据隔离",
    },
]
PRODUCTS = {"atlas": "Atlas 智能客服平台（演示）", "orion": "Orion 协作空间（演示）"}
DOCS = [
    ("atlas-v2-account.md", "atlas", "2.0", "演示-Atlas-账号与登录.md"),
    ("atlas-v3-account.md", "atlas", "3.0", "演示-Atlas-账号与登录.md"),
    ("atlas-v2-upload.md", "atlas", "2.0", "演示-Atlas-文档上传.md"),
    ("atlas-v3-upload.md", "atlas", "3.0", "演示-Atlas-文档上传.md"),
    ("atlas-v2-ticket.md", "atlas", "2.0", "演示-Atlas-工单政策.md"),
    ("atlas-v3-ticket.md", "atlas", "3.0", "演示-Atlas-工单政策.md"),
    ("atlas-knowledge-operations.md", "atlas", "3.0", "演示-Atlas-知识运营指南.md"),
    ("atlas-error-codes.md", "atlas", "2.0", "演示-Atlas-常见问题速查.md"),
    ("orion-invitation.md", "orion", "1.0", "演示-Orion-成员邀请.md"),
    ("orion-permissions.md", "orion", "1.0", "演示-Orion-权限与通知.md"),
    ("workbench-guide.md", None, None, "演示-工作台体验指南.md"),
]


def require_demo():
    if not get_settings().demo_mode or get_settings().app_env == "production":
        raise RuntimeError("请仅在本地演示环境设置 DEMO_MODE=true 后初始化")


def owned(db, key, model):
    record = db.get(DemoResource, key)
    if record:
        item = db.get(model, record.resource_id)
        if not item:
            raise RuntimeError(f"演示资源 {key} 已被删除；为避免覆盖，需人工核对后恢复")
        return item
    return None


def bind(db, key, kind, item, details=None):
    db.add(DemoResource(key=key, kind=kind, resource_id=item.id, details=details or {}))


def base_resources():
    with session_factory()() as db, db.begin():
        # 先核对全部固定名称，发生冲突时整个初始化事务回滚。
        for spec in ACCOUNTS:
            existing = db.scalar(select(User).where(User.username == spec["username"]))
            record = db.get(DemoResource, "user:" + spec["username"])
            if existing and (not record or record.resource_id != existing.id or record.kind != "user"):
                raise RuntimeError(f"账号 {spec['username']} 已存在且不属于演示初始化，不会覆盖")
        for code, name in PRODUCTS.items():
            existing = db.scalar(select(Product).where(Product.name == name))
            record = db.get(DemoResource, "product:" + code)
            if existing and (not record or record.resource_id != existing.id):
                raise RuntimeError(f"产品 {name} 已存在，不会覆盖")
        users, products, versions = {}, {}, {}
        for spec in ACCOUNTS:
            key = "user:" + spec["username"]
            user = owned(db, key, User)
            if not user:
                user = User(
                    username=spec["username"],
                    role=spec["role"],
                    password_hash=password_hasher.hash(DEMO_PASSWORD),
                )
                db.add(user)
                db.flush()
                bind(db, key, "user", user)
            users[spec["username"]] = user
        for code, name in PRODUCTS.items():
            key = "product:" + code
            product = owned(db, key, Product)
            if not product:
                product = Product(
                    name=name, description="虚构的演示产品资料，用于体验问答、版本隔离与客服工作流。"
                )
                db.add(product)
                db.flush()
                bind(db, key, "product", product)
            products[code] = product
            for version in ["2.0", "3.0"] if code == "atlas" else ["1.0"]:
                key = f"version:{code}:{version}"
                item = owned(db, key, ProductVersion)
                if not item:
                    if db.scalar(
                        select(ProductVersion.id).where(
                            ProductVersion.product_id == product.id, ProductVersion.name == version
                        )
                    ):
                        raise RuntimeError("演示版本名称已被使用，不会接管已有版本")
                    item = ProductVersion(product_id=product.id, name=version)
                    db.add(item)
                    db.flush()
                    bind(db, key, "version", item)
                versions[(code, version)] = item
        return users, products, versions


def wait_ready(revision_ids, *, timeout, inline):
    deadline = time.monotonic() + timeout
    while True:
        with session_factory()() as db:
            rows = list(db.scalars(select(DocumentRevision).where(DocumentRevision.id.in_(revision_ids))))
            if len(rows) != len(set(revision_ids)):
                raise RuntimeError("演示入库修订缺失")
            if any(r.state == "failed" for r in rows):
                raise RuntimeError("演示资料入库失败，请在文档管理重试后重新运行初始化")
            if all(r.state in {"ready", "published", "superseded"} for r in rows):
                return
        if time.monotonic() >= deadline:
            raise RuntimeError("等待演示资料入库超时，请确认 worker 在线；已保存的资料可继续处理")
        if inline and ingestion.run_once():
            continue
        time.sleep(0.5)


def seed_documents(admin, products, versions, *, timeout, inline):
    pending = []
    for file, code, version, filename in DOCS:
        content = (BACKEND_DIR / "demo_documents" / file).read_bytes()
        with session_factory()() as db, db.begin():
            key = "document:" + file
            record = db.get(DemoResource, key)
            if record:
                owned(db, key, KnowledgeDocument)
                if not record.details.get("initialized"):
                    pending.append(record.details["revision_id"])
                continue
            product_id = products[code].id if code else None
            version_id = versions[(code, version)].id if code else None
            if db.scalar(
                select(KnowledgeDocument.id).where(
                    KnowledgeDocument.scope_key == knowledge.scope_key(filename, product_id, version_id)
                )
            ):
                raise RuntimeError(f"资料 {filename} 已存在，不会接管或覆盖")
            result = knowledge.enqueue(filename, content, admin.id, product_id, version_id, db=db)
            doc = db.get(KnowledgeDocument, result["document_id"])
            bind(db, key, "document", doc, {"revision_id": result["revision_id"], "initialized": False})
            pending.append(result["revision_id"])
    if pending:
        wait_ready(pending, timeout=timeout, inline=inline)
    with session_factory()() as db, db.begin():
        for record in db.scalars(select(DemoResource).where(DemoResource.kind == "document")):
            if record.details.get("initialized"):
                continue
            revision = db.get(DocumentRevision, record.details["revision_id"])
            doc = db.get(KnowledgeDocument, record.resource_id)
            current = db.scalar(
                select(DocumentRevision).where(
                    DocumentRevision.document_id == doc.id, DocumentRevision.state == "published"
                )
            )
            if not doc.archived and not current and revision.state in {"ready", "superseded"}:
                knowledge.change(doc.id, "publish", admin.id, doc.revision, revision.id, db=db)
            record.details = {**record.details, "initialized": True}


def seed_stories(users, products, versions):
    def messages(question, answer, source):
        return [
            {"role": "user", "content": question},
            {
                "role": "assistant",
                "content": "（预置演示回答，依据样例资料整理）\n\n" + answer,
                "sources": [source],
            },
        ]

    stories = [
        (
            "login",
            "demo_user",
            "演示｜E401 登录排查",
            "atlas",
            "2.0",
            messages(
                "Atlas 2.0 登录提示 E401 怎么处理？",
                "E401 表示会话过期，请退出后重新登录。仍然失败时记录版本和复现步骤，再提交工单。[资料1]",
                "演示-Atlas-账号与登录.md",
            )
            + messages(
                "那密码重置链接多久失效？",
                "Atlas 2.0 的重置链接有效期为 30 分钟，过期后重新申请。[资料1]",
                "演示-Atlas-账号与登录.md",
            ),
        ),
        (
            "upload",
            "demo_user",
            "演示｜Atlas3.0 上传限制",
            "atlas",
            "3.0",
            messages(
                "Atlas 3.0 支持 DOCX 吗，单文件多大？",
                "演示产品 Atlas 3.0 支持 DOCX，规则上限为 50 MB；当前工作台实际上传上限以服务器配置为准。加密文档需另存为不加密文件后再处理。[资料1]",
                "演示-Atlas-文档上传.md",
            ),
        ),
        (
            "invitation",
            "demo_other",
            "演示｜Orion 邀请成员",
            "orion",
            "1.0",
            messages(
                "Orion 邀请邮件没有收到怎么办？",
                "先检查邮箱拼写、垃圾邮件和企业隔离区，再请空间管理员重新发送。邀请链接有效期为 24 小时。[资料1]",
                "演示-Orion-成员邀请.md",
            ),
        ),
        (
            "operations",
            "demo_staff",
            "演示｜文档入库排障",
            "atlas",
            "3.0",
            messages(
                "资料一直等待入库应该检查什么？",
                "查看后台心跳，确认 worker 在线，再检查任务错误及文件格式。扫描 PDF 需先 OCR，任务恢复后可重试。[资料1]",
                "演示-Atlas-知识运营指南.md",
            ),
        ),
        (
            "publication",
            "demo_admin",
            "演示｜知识发布巡检",
            "atlas",
            "3.0",
            messages(
                "发布知识之前应该检查哪些项目？",
                "核对产品版本、分块完整性及敏感信息。新修订发布后可回滚，归档的资料不参与后续检索。[资料1]",
                "演示-Atlas-知识运营指南.md",
            ),
        ),
    ]
    with session_factory()() as db, db.begin():
        conversations = {}
        for code, owner, name, product, version, rows in stories:
            key = "session:" + code
            convo = owned(db, key, Conversation)
            if not convo:
                if db.scalar(
                    select(Conversation.id).where(
                        Conversation.owner_id == users[owner].id, Conversation.name == name
                    )
                ):
                    raise RuntimeError("演示会话名称已被使用，不会覆盖")
                convo = Conversation(
                    owner_id=users[owner].id,
                    name=name,
                    product_id=products[product].id,
                    version_id=versions[(product, version)].id,
                )
                db.add(convo)
                db.flush()
                db.add_all([Message(conversation_id=convo.id, **row) for row in rows])
                bind(db, key, "session", convo)
            conversations[code] = convo
        specs = [
            (
                "new",
                "demo_user",
                "atlas",
                "2.0",
                "演示｜升级后仍报 E401",
                "升级后反复出现 E401，重新登录仍然失败，请协助排查。",
                "new",
                "high",
                "login",
                "",
            ),
            (
                "progress",
                "demo_user",
                "atlas",
                "3.0",
                "演示｜DOCX 文档解析失败",
                "上传 DOCX 后处理失败，已经确认文档有打开密码。",
                "in_progress",
                "normal",
                "upload",
                "",
            ),
            (
                "reset",
                "demo_user",
                "atlas",
                "2.0",
                "演示｜密码重置链接过期",
                "使用昨天收到的密码重置链接时提示失效。",
                "resolved",
                "normal",
                None,
                "Atlas 2.0 的重置链接有效期为 30 分钟。重新申请，使用最新邮件中的链接完成重置。",
            ),
            (
                "invite",
                "demo_other",
                "orion",
                "1.0",
                "演示｜邀请邮件未收到",
                "团队邀请邮件未送达，客户在垃圾邮件中找到邀请。",
                "closed",
                "normal",
                "invitation",
                "检查邮箱拼写、垃圾邮件和企业隔离区，再请管理员重发。Orion 邀请链接有效期为 24 小时。",
            ),
            (
                "large",
                "demo_other",
                "atlas",
                "3.0",
                "演示｜E413 文件超限",
                "Atlas 3.0 演示产品上传 65 MB 文件时提示 E413。",
                "resolved",
                "low",
                None,
                "Atlas 3.0 演示规则上限为 50 MB，拆分为每份不超过 50 MB 后上传；当前工作台实际限制以服务器配置为准。",
            ),
        ]
        tickets = {}
        for (
            code,
            owner,
            product,
            version,
            title,
            description,
            status,
            priority,
            conversation,
            solution,
        ) in specs:
            key = "ticket:" + code
            row = owned(db, key, Ticket)
            if not row:
                convo = conversations[conversation] if conversation else None
                message = (
                    db.scalar(
                        select(Message)
                        .where(Message.conversation_id == convo.id, Message.role == "assistant")
                        .order_by(Message.id.desc())
                    )
                    if convo
                    else None
                )
                result, _ = support.create_ticket(
                    db,
                    users[owner],
                    TicketCreate(
                        title=title,
                        description="预置演示工单（虚构内容）：" + description,
                        product_id=products[product].id,
                        version_id=versions[(product, version)].id,
                        priority=priority,
                        conversation_name=convo.name if convo else None,
                        message_id=message.id if message else None,
                        idempotency_key="demo_story_v1_" + code,
                    ),
                    commit=False,
                )
                row = db.get(Ticket, result["id"])
                if status != "new":
                    row.assignee_id = users["demo_staff"].id
                    db.add(
                        TicketEvent(
                            ticket_id=row.id,
                            actor_id=users["demo_staff"].id,
                            kind="assigned",
                            content="预置演示：客服接单",
                            details={"to_assignee": "demo_staff", "from_assignee": None},
                        )
                    )
                    db.add(
                        TicketEvent(
                            ticket_id=row.id,
                            actor_id=users["demo_staff"].id,
                            kind="status",
                            content="预置演示：进入处理",
                            details={"from_status": "new", "to_status": "in_progress"},
                        )
                    )
                    db.add(
                        TicketEvent(
                            ticket_id=row.id,
                            actor_id=users["demo_staff"].id,
                            kind="comment",
                            content="预置演示回复：已收到问题，请补充操作步骤；不要提供密码或密钥。",
                        )
                    )
                if status in {"resolved", "closed"}:
                    db.add(
                        TicketEvent(
                            ticket_id=row.id,
                            actor_id=users["demo_staff"].id,
                            kind="status",
                            content=solution,
                            details={"from_status": "in_progress", "to_status": "resolved"},
                        )
                    )
                if status == "closed":
                    db.add(
                        TicketEvent(
                            ticket_id=row.id,
                            actor_id=users[owner].id,
                            kind="status",
                            content="预置演示：提交者确认问题已解决",
                            details={"from_status": "resolved", "to_status": "closed"},
                        )
                    )
                row.status = status
                db.flush()
                bind(db, key, "ticket", row)
            tickets[code] = row
        for code, owner, conversation, rating, reason, target in [
            (
                "unresolved",
                "demo_user",
                "login",
                "unresolved",
                "预置演示：重登后仍失败，已转人工处理。",
                "new",
            ),
            (
                "helpful",
                "demo_other",
                "invitation",
                "helpful",
                "预置演示：在垃圾邮件中找到邀请，问题已解决。",
                "invite",
            ),
        ]:
            if not owned(db, "feedback:" + code, Feedback):
                convo = conversations[conversation]
                question = db.scalar(
                    select(Message)
                    .where(Message.conversation_id == convo.id, Message.role == "user")
                    .order_by(Message.id)
                )
                response = db.scalar(
                    select(Message)
                    .where(Message.conversation_id == convo.id, Message.role == "assistant")
                    .order_by(Message.id)
                )
                feedback = Feedback(
                    user_id=users[owner].id,
                    conversation_id=convo.id,
                    message_id=response.id,
                    ticket_id=tickets[target].id,
                    question=question.content,
                    answer=response.content,
                    sources=response.sources,
                    rating=rating,
                    reason=reason,
                )
                db.add(feedback)
                db.flush()
                bind(db, "feedback:" + code, "feedback", feedback)
        return tickets


def seed_faqs(users, tickets, *, timeout, inline):
    for code, ticket_code, target in [
        ("reset", "reset", "draft"),
        ("large", "large", "review"),
        ("invite", "invite", "published"),
    ]:
        key = "faq:" + code
        with session_factory()() as db:
            record = db.get(DemoResource, key)
            if record and record.details.get("initialized"):
                continue
        draft, _ = faq.create(
            users["demo_staff"],
            FAQCreate(
                ticket_id=tickets[ticket_code].id, mode="manual", request_key="demo_faq_seed_v1_" + code
            ),
        )
        with session_factory()() as db, db.begin():
            if not db.get(DemoResource, key):
                bind(db, key, "faq", db.get(FAQDraft, draft["id"]), {"initialized": False})
        if target != "draft" and draft["state"] == "draft":
            draft = faq.action(
                users["demo_staff"], draft["id"], "submit", FAQAction(revision=draft["revision"])
            )
        if target == "published":
            if draft["state"] == "review":
                draft = faq.action(
                    users["demo_admin"],
                    draft["id"],
                    "review",
                    FAQReview(
                        revision=draft["revision"],
                        decision="approve",
                        reviewed_no_sensitive_data=True,
                        note="预置演示资料：已核对虚构内容及适用版本",
                    ),
                )
            if draft["state"] == "indexing":
                wait_ready([draft["revision_id"]], timeout=timeout, inline=inline)
                draft = faq.action(
                    users["demo_admin"], draft["id"], "publish", FAQAction(revision=draft["revision"])
                )
            if draft["state"] != "published":
                raise RuntimeError("演示 FAQ 状态已经变化，请人工核对；不会覆盖现有编辑")
        with session_factory()() as db, db.begin():
            db.get(DemoResource, key).details = {"initialized": True}
            if draft.get("document_id") and not db.get(DemoResource, "document:faq-invite"):
                bind(
                    db,
                    "document:faq-invite",
                    "document",
                    db.get(KnowledgeDocument, draft["document_id"]),
                    {"initialized": True, "revision_id": draft["revision_id"]},
                )


def seed_assistants(users, products, versions):
    for code, owner, question in [
        (
            "knowledge",
            "demo_user",
            "请检索知识库，Atlas 2.0 出现 E401 应该怎么处理？只需提供排查建议，不要准备工单。",
        ),
        ("similar", "demo_staff", "请检索相似的已解决工单，密码重置链接过期通常如何解决？不要准备工单。"),
    ]:
        key = "run:" + code
        with session_factory()() as db:
            record = db.get(DemoResource, key)
            previous = db.get(AgentRun, record.resource_id) if record else None
            retried = bool(record and record.details.get("retried"))
            if previous and (previous.status != "failed" or retried):
                continue
        run = (
            agent.get_run(users[owner], previous.id)
            if previous
            else agent.create_run(
                users[owner],
                RunCreate(
                    question=question,
                    product_id=products["atlas"].id,
                    version_id=versions[("atlas", "2.0")].id,
                    request_key="demo_assistant_seed_v1_" + code,
                ),
            )
        )
        if run["status"] == "queued":
            for _ in agent.execute(users[owner], run["id"]):
                pass
        run = agent.get_run(users[owner], run["id"])
        previous_id = None
        if run["status"] == "failed" and not retried:
            previous_id = run["id"]
            run = agent.retry_run(users[owner], run["id"], "demo_assistant_retry_v1_" + code)
            if run["status"] == "queued":
                for _ in agent.execute(users[owner], run["id"]):
                    pass
            retried = True
        with session_factory()() as db, db.begin():
            record = db.get(DemoResource, key)
            if record:
                record.resource_id, record.details = (
                    run["id"],
                    {"retried": retried, "previous_run_id": previous_id},
                )
            else:
                bind(
                    db,
                    key,
                    "run",
                    db.get(AgentRun, run["id"]),
                    {"retried": retried, "previous_run_id": previous_id},
                )


def seed_demo(*, timeout=180, inline=False, with_assistant=False):
    require_demo()
    users, products, versions = base_resources()
    seed_documents(users["demo_admin"], products, versions, timeout=timeout, inline=inline)
    tickets = seed_stories(users, products, versions)
    seed_faqs(users, tickets, timeout=timeout, inline=inline)
    if with_assistant:
        seed_assistants(users, products, versions)
    with session_factory()() as db:
        return dict(db.execute(select(DemoResource.kind, func.count()).group_by(DemoResource.kind)).all())


@lru_cache(maxsize=32)
def credential_matches(password_hash):
    return verify_password(password_hash, DEMO_PASSWORD)


def public_info():
    if not get_settings().demo_mode:
        return {"enabled": False, "accounts": []}
    with session_factory()() as db:
        accounts = []
        for spec in ACCOUNTS:
            record = db.get(DemoResource, "user:" + spec["username"])
            user = db.get(User, record.resource_id) if record and record.kind == "user" else None
            if (
                user
                and user.username == spec["username"]
                and user.role == spec["role"]
                and user.is_active
                and credential_matches(user.password_hash)
            ):
                accounts.append({**spec, "password": DEMO_PASSWORD})
        documents = list(db.scalars(select(DemoResource.resource_id).where(DemoResource.kind == "document")))
        count = db.scalar(
            select(func.count(DocumentRevision.id))
            .join(KnowledgeDocument)
            .where(
                KnowledgeDocument.id.in_(documents),
                KnowledgeDocument.archived.is_(False),
                DocumentRevision.state == "published",
            )
        )
        return {
            "enabled": True,
            "accounts": accounts,
            "published_documents": count,
            "description": "本地演示账号与虚构资料，可切换角色体验。预置对话已明确标记，助手执行记录来自实际模型调用。",
        }


def guide(user):
    require_demo()
    with session_factory()() as db:
        sessions = list(
            db.scalars(
                select(Conversation)
                .join(DemoResource, DemoResource.resource_id == Conversation.id)
                .where(DemoResource.kind == "session", Conversation.owner_id == user.id)
            )
        )
        tickets = list(
            db.scalars(
                select(Ticket)
                .join(DemoResource, DemoResource.resource_id == Ticket.id)
                .where(DemoResource.kind == "ticket")
            )
        )
        tickets = [t for t in tickets if support.is_staff(user) or t.creator_id == user.id]
        scopes = []
        for code, version, question in [
            ("atlas", "2.0", "密码重置链接多久失效？"),
            ("atlas", "3.0", "支持哪些上传格式，单文件上限是多少？"),
            ("orion", "1.0", "邀请邮件没有收到怎么办？"),
        ]:
            product = owned(db, "product:" + code, Product)
            item = owned(db, f"version:{code}:{version}", ProductVersion)
            if product and item and product.is_active and item.is_active:
                scopes.append(
                    {
                        "product_id": product.id,
                        "version_id": item.id,
                        "label": product.name + " " + version,
                        "question": question,
                    }
                )
        return {
            "scenarios": scopes,
            "sessions": [
                {"name": s.name, "product_id": s.product_id, "version_id": s.version_id} for s in sessions
            ],
            "tickets": [{"id": t.id, "title": t.title, "status": t.status} for t in tickets],
            "is_staff": support.is_staff(user),
            "faqs": [
                {"id": f.id, "question": f.question, "state": f.state}
                for f in db.scalars(
                    select(FAQDraft)
                    .join(DemoResource, DemoResource.resource_id == FAQDraft.id)
                    .where(DemoResource.kind == "faq")
                )
            ]
            if support.is_staff(user)
            else [],
            "runs": [
                {"id": r.id, "question": r.input.get("question"), "status": r.status}
                for r in db.scalars(
                    select(AgentRun)
                    .join(DemoResource, DemoResource.resource_id == AgentRun.id)
                    .where(DemoResource.kind == "run", AgentRun.owner_id == user.id)
                )
            ],
        }
