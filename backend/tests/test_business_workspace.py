import pytest
from sqlalchemy import select
from test_demo import demo_env  # noqa: F401


def test_normal_accounts_have_different_knowledge(demo_env, client, monkeypatch, tmp_path):  # noqa: F811
    import json

    from app.core.config import get_settings
    from app.core.database import session_factory
    from app.models import Conversation, DemoResource, Message, User
    from app.services import business_workspace, knowledge, rag

    demo_env.seed_demo(inline=True)
    with session_factory()() as db:
        originals = {
            u.id: (u.username, u.password_hash)
            for u in db.scalars(select(User))
            if not u.username.startswith("demo_")
        }

    def answer(question, **kwargs):
        contexts = knowledge.search(
            question,
            product_id=kwargs["product_id"],
            version_id=kwargs["version_id"],
            user_id=kwargs["user_id"],
        )
        return {
            "answer": "请参考适用版本的产品资料。[资料1]",
            "sources": [c["source"] for c in contexts],
            "contexts": contexts,
            "usage": {"total_tokens": 12},
        }

    with session_factory()() as db, db.begin():
        owner_id = db.get(DemoResource, "user:demo_user").resource_id
        extra = Conversation(owner_id=owner_id, name="个人登录咨询")
        db.add(extra)
        db.flush()
        db.add(Message(conversation_id=extra.id, role="user", content="E401 如何处理？"))
        response = Message(
            conversation_id=extra.id, role="assistant", content="旧回答", sources=["演示-Atlas-账号与登录.md"]
        )
        db.add(response)
        db.flush()
        personal_id, message_id = extra.id, response.id
    monkeypatch.setattr(rag, "ask", answer)
    credential_path = tmp_path / "credentials.json"
    result = business_workspace.prepare(credential_path, inline=True)
    assert result["published_documents"] == 12
    with session_factory()() as db:
        assert db.get(Conversation, personal_id).name == "个人登录咨询"
        assert db.get(Message, message_id).content != "旧回答"
        assert all("演示" not in source for source in db.get(Message, message_id).sources)

    assert business_workspace.prepare(credential_path, inline=True) == result
    passwords = json.loads(credential_path.read_text())
    get_settings().demo_mode = False
    assert client.get("/api/demo").status_code == 404
    assert client.get("/api/demo/guide").status_code == 404
    docs_by_user = {}
    for username, count, product in [
        ("chen.yu", 8, "Atlas"),
        ("lin.wei", 3, "Orion"),
        ("wang.min", 12, None),
        ("zhao.ning", 12, None),
    ]:
        assert (
            client.post(
                "/api/auth/login", json={"username": username, "password": passwords[username]}
            ).status_code
            == 200
        )
        docs = client.get("/api/documents").json()
        assert len(docs) == count
        docs_by_user[username] = docs
        assert client.get("/api/documents/stats").json()["sources"] == count
        products = client.get("/api/products").json()
        if product:
            assert len(products) == 1 and products[0]["name"].startswith(product)
        serialized = json.dumps(docs, ensure_ascii=False)
        assert not any(word in serialized for word in ["演示", "测试", "模拟", "虚构"])
        for doc in docs:
            text = json.dumps(client.get(f"/api/documents/{doc['id']}/chunks").json(), ensure_ascii=False)
            assert not any(word in text for word in ["演示", "测试", "模拟", "虚构"])
        client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "chen.yu", "password": passwords["chen.yu"]})
    other_doc = docs_by_user["lin.wei"][0]
    assert client.get(f"/api/documents/{other_doc['id']}/chunks").status_code == 404
    foreign = {
        "question": "邀请邮件",
        "product_id": other_doc["product_id"],
        "version_id": other_doc["version_id"],
    }
    assert client.post("/api/chat/ask", json=foreign).status_code == 404
    assert client.post("/api/chat/stream", json=foreign).status_code == 404
    foreign_search = {"query": "邀请邮件", "product_id": other_doc["product_id"]}
    assert client.post("/api/documents/search", json=foreign_search).status_code == 404
    with session_factory()() as db:
        for user_id, values in originals.items():
            user = db.get(User, user_id)
            assert (user.username, user.password_hash) == values
        old = db.get(DemoResource, "document:orion-invitation.md")
        retired_id = old.details["revision_id"]
    assert retired_id not in knowledge.eligible_revisions()
    with pytest.raises(Exception) as caught:
        knowledge.original(other_doc["id"], retired_id)
    assert caught.value.status_code == 404


def test_admin_product_grants_and_empty_scope(client, login, monkeypatch):
    from app.core.database import session_factory
    from app.models import User
    from app.services import knowledge, rag

    login("admin")
    product = client.post("/api/products", json={"name": "Atlas"}).json()
    alice = next(u for u in client.get("/api/auth/users").json() if u["username"] == "alice")
    edited = client.patch(
        f"/api/auth/users/{alice['id']}", json={"restrict_products": True, "product_ids": [product["id"]]}
    )
    assert edited.status_code == 200 and edited.json()["is_active"]
    assert edited.json()["product_ids"] == [product["id"]]
    assert (
        client.patch(f"/api/auth/users/{alice['id']}", json={"product_ids": ["missing"]}).status_code == 400
    )
    assert client.patch(f"/api/auth/users/{alice['id']}", json={"product_ids": []}).status_code == 200
    login("alice")
    assert client.get("/api/products").json() == []
    assert client.get("/api/documents").json() == []
    with session_factory()() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
    assert knowledge.eligible_revisions(user_id=user.id) == []
    captured = []
    monkeypatch.setattr(rag, "search", lambda query, **kwargs: captured.append(kwargs) or [])
    assert client.post("/api/chat/ask", json={"question": "登录失败"}).status_code == 200
    assert captured[0]["user_id"] == user.id
    rag.ask_stream("登录失败", user_id=user.id).__next__()
    assert captured[-1]["user_id"] == user.id
    assert (
        client.post(
            "/api/auth/users", json={"username": "another", "password": "password-long-enough"}
        ).status_code
        == 403
    )


def test_retired_runs_are_inaccessible_and_tools_bind_owner(client, login, monkeypatch):
    from types import SimpleNamespace

    from app.core.database import session_factory
    from app.models import AgentRun
    from app.services import agent, knowledge

    user = login()
    run = client.post(
        "/api/agent/runs", json={"question": "登录问题", "request_key": "product-access-check-01"}
    ).json()
    with session_factory()() as db, db.begin():
        stored = db.get(AgentRun, run["id"])
        stored.status, stored.retired = "cancelled", True
    assert client.get("/api/agent/runs").json()["total"] == 0
    assert client.get(f"/api/agent/runs/{run['id']}").status_code == 404
    for action in ["execute", "stream", "cancel"]:
        assert client.post(f"/api/agent/runs/{run['id']}/{action}").status_code == 404
    captured = []
    monkeypatch.setattr(agent, "running", lambda _: None)
    monkeypatch.setattr(knowledge, "search", lambda query, **kwargs: captured.append(kwargs) or [])
    agent.read_tool(
        "search_knowledge",
        {"query": "登录", "top_k": 3},
        SimpleNamespace(id="run", owner_id=user["id"], product_id=None, version_id=None, input={}),
    )
    assert captured[0]["user_id"] == user["id"]


def test_product_revocation_hides_history_without_deleting_it(client, login):
    from app.core.database import session_factory
    from app.models import Conversation, Message

    login("admin")
    product = client.post("/api/products", json={"name": "Orion"}).json()
    alice = next(u for u in client.get("/api/auth/users").json() if u["username"] == "alice")
    login("alice")
    saved = client.put(
        "/api/sessions/previous-project",
        json={
            "product_id": product["id"],
            "messages": [{"role": "user", "content": "项目权限"}],
        },
    )
    assert saved.status_code == 200
    conversation_id = saved.json()["id"]
    login("admin")
    assert (
        client.patch(
            f"/api/auth/users/{alice['id']}", json={"restrict_products": True, "product_ids": []}
        ).status_code
        == 200
    )
    login("alice")
    assert client.get("/api/sessions").json() == []
    assert client.get("/api/sessions/previous-project").status_code == 404
    assert client.get("/api/sessions/previous-project/export").status_code == 404
    assert client.put("/api/sessions/previous-project", json={"messages": []}).status_code == 404
    assert (
        client.post("/api/chat/ask", json={"question": "继续", "session": "previous-project"}).status_code
        == 404
    )
    assert client.delete("/api/sessions/previous-project").status_code == 404
    assert client.put("/api/sessions/general", json={"messages": []}).status_code == 200
    with session_factory()() as db:
        assert db.get(Conversation, conversation_id) is not None
        assert (
            db.scalar(select(Message).where(Message.conversation_id == conversation_id)).content == "项目权限"
        )
