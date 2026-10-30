from types import SimpleNamespace

import pytest
from sqlalchemy import func, select


@pytest.fixture
def demo_env(client, monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.services import agent, demo, ingestion, vectorstore

    get_settings().demo_mode = True
    get_settings().chroma_dir = tmp_path / "demo-vectors"
    monkeypatch.setattr(vectorstore, "_client", None)
    monkeypatch.setattr(vectorstore, "_ENSURED", False)
    embed = SimpleNamespace(
        embed_documents=lambda texts: [[1.0, 0.0] for _ in texts], embed_query=lambda text: [1.0, 0.0]
    )
    monkeypatch.setattr(vectorstore, "get_embedding_service", lambda: embed)
    monkeypatch.setattr(ingestion, "get_embedding_service", lambda: embed)
    monkeypatch.setattr(agent, "get_embedding_service", lambda: embed)
    return demo


def test_demo_disabled_by_default_and_production_rejected(client):
    from app.core.config import Settings
    from app.services.demo import seed_demo

    assert client.get("/api/demo").status_code == 404
    with pytest.raises(RuntimeError, match="DEMO_MODE"):
        seed_demo(inline=True)
    with pytest.raises(ValueError, match="DEMO_MODE"):
        Settings(_env_file=None, app_env="production", demo_mode=True)


def test_demo_complete_content_and_all_accounts(demo_env, client):
    from app.core.database import session_factory
    from app.models import FAQDraft, Ticket

    result = demo_env.seed_demo(inline=True)
    assert result == {
        "user": 4,
        "product": 2,
        "version": 3,
        "document": 12,
        "session": 5,
        "ticket": 5,
        "feedback": 2,
        "faq": 3,
    }
    info = demo_env.public_info()
    assert info["enabled"] and info["published_documents"] == 12
    assert len(info["accounts"]) == 4
    for account in info["accounts"]:
        response = client.post(
            "/api/auth/login", json={"username": account["username"], "password": account["password"]}
        )
        assert response.status_code == 200 and response.json()["role"] == account["role"]
        client.post("/api/auth/logout")
    with session_factory()() as db:
        assert {t.status for t in db.scalars(select(Ticket))} == {"new", "in_progress", "resolved", "closed"}
        assert {f.state for f in db.scalars(select(FAQDraft))} == {"draft", "review", "published"}


def test_demo_idempotent_preserves_edits_credentials_and_real_accounts(demo_env):
    from app.core.auth import password_hasher
    from app.core.database import session_factory
    from app.models import Conversation, DemoResource, KnowledgeDocument, Message, Ticket, User

    first = demo_env.seed_demo(inline=True)
    with session_factory()() as db, db.begin():
        original = db.scalar(select(User).where(User.username == "admin"))
        original_hash = original.password_hash
        demo_user = db.scalar(select(User).where(User.username == "demo_user"))
        changed_hash = password_hasher.hash("my-edited-demo-password")
        demo_user.password_hash = changed_hash
        doc = db.get(KnowledgeDocument, db.get(DemoResource, "document:atlas-v2-account.md").resource_id)
        doc.archived = True
        convo = db.get(Conversation, db.get(DemoResource, "session:login").resource_id)
        db.scalar(
            select(Message).where(Message.conversation_id == convo.id).order_by(Message.id)
        ).content = "我编辑过的内容"
        ticket = db.get(Ticket, db.get(DemoResource, "ticket:new").resource_id)
        ticket.description = "我编辑过的工单"
    assert demo_env.seed_demo(inline=True) == first
    with session_factory()() as db:
        assert db.scalar(select(func.count(User.id))) == 8
        assert db.get(User, original.id).password_hash == original_hash
        assert db.get(User, demo_user.id).password_hash == changed_hash
        assert db.get(KnowledgeDocument, doc.id).archived
        assert (
            db.scalar(select(Message).where(Message.conversation_id == convo.id).order_by(Message.id)).content
            == "我编辑过的内容"
        )
        assert db.get(Ticket, ticket.id).description == "我编辑过的工单"
    assert "demo_user" not in [a["username"] for a in demo_env.public_info()["accounts"]]


def test_demo_name_collision_does_not_take_over_account(demo_env, client):
    from app.core.auth import password_hasher
    from app.core.database import session_factory
    from app.models import DemoResource, User

    with session_factory()() as db, db.begin():
        db.add(
            User(
                username="demo_admin",
                role="admin",
                password_hash=password_hasher.hash("reserved-user-password"),
            )
        )
    with pytest.raises(RuntimeError, match="不会覆盖"):
        demo_env.seed_demo(inline=True)
    with session_factory()() as db:
        assert db.scalar(select(func.count(User.id))) == 5
        assert db.scalar(select(func.count(DemoResource.key))) == 0
    assert client.get("/api/demo").status_code == 404


def test_disabling_demo_blocks_login_and_existing_cookie(demo_env, client, login):
    from app.core.config import get_settings

    demo_env.seed_demo(inline=True)
    assert (
        client.post(
            "/api/auth/login", json={"username": "demo_user", "password": demo_env.DEMO_PASSWORD}
        ).status_code
        == 200
    )
    assert client.get("/api/auth/me").status_code == 200
    get_settings().demo_mode = False
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"username": "demo_user", "password": demo_env.DEMO_PASSWORD}
        ).status_code
        == 401
    )
    assert client.get("/api/demo").status_code == 404
    login("admin")
    assert client.get("/api/auth/me").status_code == 200


def test_guide_owner_isolation_and_version_documents(demo_env, client):
    from app.core.database import session_factory
    from app.models import DemoResource
    from app.services import knowledge

    demo_env.seed_demo(inline=True)
    for name, sessions, tickets, faqs in [
        ("demo_user", 2, 3, 0),
        ("demo_other", 1, 2, 0),
        ("demo_staff", 1, 5, 3),
        ("demo_admin", 1, 5, 3),
    ]:
        client.post("/api/auth/login", json={"username": name, "password": demo_env.DEMO_PASSWORD})
        with session_factory()() as db:
            from app.models import User

            guide = demo_env.guide(db.scalar(select(User).where(User.username == name)))
        assert (len(guide["sessions"]), len(guide["tickets"]), len(guide["faqs"])) == (
            sessions,
            tickets,
            faqs,
        )
        assert len(guide["scenarios"]) == 3
        client.post("/api/auth/logout")
    with session_factory()() as db:
        v2 = db.get(DemoResource, "document:atlas-v2-account.md")
        v3 = db.get(DemoResource, "document:atlas-v3-account.md")
    assert "30 分钟" in "".join(c["content"] for c in knowledge.chunks(v2.resource_id))
    assert "15 分钟" in "".join(c["content"] for c in knowledge.chunks(v3.resource_id))


def test_demo_assistant_has_one_bounded_retry_and_does_not_replay(demo_env, monkeypatch):
    import json

    from test_workflows import fake_model

    from app.core.database import session_factory
    from app.models import AgentRun, DemoResource

    def response(tool=None):
        tools = (
            [
                SimpleNamespace(
                    id="sample-call",
                    function=SimpleNamespace(name=tool, arguments=json.dumps({"query": "密码重置"})),
                )
            ]
            if tool
            else []
        )
        return SimpleNamespace(
            usage=SimpleNamespace(total_tokens=10),
            choices=[
                SimpleNamespace(
                    finish_reason="tool_calls" if tool else "stop",
                    message=SimpleNamespace(content="请重新申请链接。[资料1]", tool_calls=tools),
                )
            ],
        )

    responses = [
        TimeoutError("temporary outage"),
        response("search_knowledge"),
        response(),
        response("search_resolved_tickets"),
        response(),
    ]

    calls, _ = fake_model(monkeypatch, responses)
    result = demo_env.seed_demo(inline=True, with_assistant=True)
    assert result["run"] == 2 and len(calls) == 5
    with session_factory()() as db:
        assert db.scalar(select(func.count(AgentRun.id))) == 3
        record = db.get(DemoResource, "run:knowledge")
        assert record.details["retried"] and db.get(AgentRun, record.resource_id).status == "completed"
    demo_env.seed_demo(inline=True, with_assistant=True)
    assert len(calls) == 5
