from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.database import session_factory
from app.models import Feedback, Ticket


def payload(**changes):
    return {
        "title": "升级后登录失败",
        "description": "Windows 客户端升级后无法登录，已尝试重启。",
        "idempotency_key": uuid4().hex,
        **changes,
    }


def create(client, **changes):
    response = client.post("/api/tickets", json=payload(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def catalog(client):
    product = client.post("/api/products", json={"name": "测试产品"}).json()
    version = client.post(f"/api/products/{product['id']}/versions", json={"name": "2.0"}).json()
    return product, version


@pytest.mark.parametrize(
    "path", ["/api/products", "/api/tickets", "/api/feedback", "/api/tickets/unknown/events"]
)
def test_support_requires_auth(client, path):
    assert client.get(path).status_code == 401


def test_catalog_permissions_versions_and_archive(client, login):
    login()
    assert client.post("/api/products", json={"name": "p"}).status_code == 403
    login("staff")
    product, version = catalog(client)
    assert "id" in version
    assert client.post("/api/products", json={"name": "测试产品"}).status_code == 409
    assert client.post(f"/api/products/{product['id']}/versions", json={"name": "2.0"}).status_code == 409
    other = client.post("/api/products", json={"name": "其他产品"}).json()
    assert (
        client.patch(
            f"/api/products/{other['id']}/versions/{version['id']}", json={"is_active": False}
        ).status_code
        == 404
    )
    assert client.patch(f"/api/products/{product['id']}", json={"is_active": False}).status_code == 200
    login()
    assert [p["name"] for p in client.get("/api/products").json()] == ["其他产品"]
    assert client.post("/api/tickets", json=payload(product_id=product["id"])).status_code == 422


def test_ticket_end_to_end_and_audit(client, login):
    owner = login()
    ticket = create(client)
    assert ticket["created_at"].endswith("+00:00")
    login("bob")
    assert client.get("/api/tickets").json()["total"] == 0
    assert client.get(f"/api/tickets/{ticket['id']}").status_code == 404
    assert client.get(f"/api/tickets/{ticket['id']}/events").status_code == 404
    assert (
        client.post(
            f"/api/tickets/{ticket['id']}/comments",
            json={"expected_revision": ticket["revision"], "content": "窥探"},
        ).status_code
        == 404
    )
    staff = login("staff")
    assert client.get("/api/tickets").json()["total"] == 1
    response = client.post(
        f"/api/tickets/{ticket['id']}/assignee",
        json={"assignee_id": staff["id"], "expected_revision": ticket["revision"]},
    )
    assert response.status_code == 200, response.text
    ticket = response.json()
    assert ticket["status"] == "in_progress" and ticket["assignee_id"] == staff["id"]
    ticket = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "请重新获取登录令牌。", "expected_revision": ticket["revision"]},
    ).json()
    assert (
        client.post(
            f"/api/tickets/{ticket['id']}/status",
            json={"status": "resolved", "expected_revision": ticket["revision"]},
        ).status_code
        == 422
    )
    ticket = client.post(
        f"/api/tickets/{ticket['id']}/status",
        json={"status": "resolved", "note": "重新登录后已恢复。", "expected_revision": ticket["revision"]},
    ).json()
    assert ticket["status"] == "resolved"
    assert (
        client.post(
            f"/api/tickets/{ticket['id']}/status",
            json={"status": "closed", "expected_revision": ticket["revision"]},
        ).status_code
        == 403
    )
    login()
    ticket = client.post(
        f"/api/tickets/{ticket['id']}/status",
        json={"status": "closed", "expected_revision": ticket["revision"]},
    ).json()
    assert ticket["status"] == "closed" and ticket["creator_id"] == owner["id"]
    assert (
        client.post(
            f"/api/tickets/{ticket['id']}/comments",
            json={"content": "再问", "expected_revision": ticket["revision"]},
        ).status_code
        == 409
    )
    events = client.get(f"/api/tickets/{ticket['id']}/events").json()
    assert events["total"] == 6
    assert events["items"][0]["details"]["to_status"] == "closed"
    assert {e["actor_name"] for e in events["items"]} == {"alice", "staff"}


def test_user_cannot_process_but_can_reopen_resolved_ticket(client, login):
    login()
    ticket = create(client)
    path = f"/api/tickets/{ticket['id']}/status"
    assert (
        client.post(path, json={"status": "in_progress", "expected_revision": ticket["revision"]}).status_code
        == 403
    )
    assert (
        client.post(path, json={"status": "closed", "expected_revision": ticket["revision"]}).status_code
        == 409
    )
    login("staff")
    ticket = client.post(path, json={"status": "in_progress", "expected_revision": ticket["revision"]}).json()
    ticket = client.post(
        path, json={"status": "resolved", "note": "方案已提供", "expected_revision": ticket["revision"]}
    ).json()
    login()
    ticket = client.post(
        path, json={"status": "in_progress", "note": "仍未解决", "expected_revision": ticket["revision"]}
    ).json()
    assert ticket["status"] == "in_progress"
    assert (
        client.post(
            path, json={"status": "resolved", "note": "假冒客服", "expected_revision": ticket["revision"]}
        ).status_code
        == 403
    )


def test_assignment_and_revision_conflicts(client, login):
    alice = login()
    ticket = create(client)
    assert (
        client.post(
            f"/api/tickets/{ticket['id']}/assignee",
            json={"assignee_id": alice["id"], "expected_revision": ticket["revision"]},
        ).status_code
        == 403
    )
    staff = login("staff")
    assert (
        client.post(
            f"/api/tickets/{ticket['id']}/assignee",
            json={"assignee_id": alice["id"], "expected_revision": ticket["revision"]},
        ).status_code
        == 422
    )
    updated = client.post(
        f"/api/tickets/{ticket['id']}/assignee",
        json={"assignee_id": staff["id"], "expected_revision": ticket["revision"]},
    ).json()
    assert updated["revision"] > ticket["revision"]
    response = client.post(
        f"/api/tickets/{ticket['id']}/comments",
        json={"content": "过期页面", "expected_revision": ticket["revision"]},
    )
    assert response.status_code == 409
    assert client.get(f"/api/tickets/{ticket['id']}/events").json()["total"] == 3


def test_ticket_idempotency_and_content_collision(client, login):
    login()
    request = payload()
    first = client.post("/api/tickets", json=request)
    second = client.post("/api/tickets", json=request)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert client.post("/api/tickets", json={**request, "title": "另一个问题"}).status_code == 409
    assert client.get("/api/tickets").json()["total"] == 1
    login("bob")
    assert client.post("/api/tickets", json=request).status_code == 201


def test_concurrent_ticket_creation_is_idempotent(client, login):
    login()
    request = payload()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: client.post("/api/tickets", json=request), range(2)))
    assert sorted(r.status_code for r in results) == [200, 201], [r.text for r in results]
    assert results[0].json()["id"] == results[1].json()["id"]
    with session_factory()() as db:
        assert len(db.scalars(select(Ticket)).all()) == 1


def test_concurrent_comments_do_not_overwrite(client, login):
    login()
    ticket = create(client)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda i: client.post(
                    f"/api/tickets/{ticket['id']}/comments",
                    json={"content": f"回复 {i}", "expected_revision": ticket["revision"]},
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]
    assert client.get(f"/api/tickets/{ticket['id']}/events").json()["total"] == 2


def test_feedback_snapshots_and_ticket_survive_conversation_deletion(client, login):
    login()
    messages = [
        {"role": "user", "content": "怎么登录"},
        {"role": "assistant", "content": "检查令牌", "sources": ["手册.md"]},
    ]
    session = client.put("/api/sessions/关联会话", json={"messages": messages}).json()
    answer_id = session["messages"][-1]["id"]
    feedback = client.put(
        f"/api/feedback/messages/{answer_id}", json={"rating": "unresolved", "reason": "步骤无效"}
    )
    assert feedback.status_code == 200 and feedback.json()["question"] == "怎么登录"
    same = client.put("/api/sessions/关联会话", json={"messages": messages}).json()
    assert same["messages"][-1]["id"] == answer_id
    assert same["messages"][-1]["feedback"]["rating"] == "unresolved"
    ticket = create(client, conversation_name="关联会话", message_id=answer_id)
    assert len(ticket["conversation_snapshot"]) == 2
    assert client.get("/api/feedback").json()["items"][0]["ticket_id"] == ticket["id"]
    assert client.delete("/api/sessions/关联会话").status_code == 200
    detail = client.get(f"/api/tickets/{ticket['id']}").json()
    assert detail["conversation_id"] is None and detail["message_id"] is None
    assert detail["conversation_snapshot"][-1]["content"] == "检查令牌"
    with session_factory()() as db:
        saved = db.get(Feedback, feedback.json()["id"])
        assert saved.message_id is None and saved.answer == "检查令牌"


def test_feedback_and_conversation_link_are_owner_only(client, login):
    login()
    session = client.put(
        "/api/sessions/private",
        json={"messages": [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]},
    ).json()
    user_id, answer_id = session["messages"][0]["id"], session["messages"][1]["id"]
    assert client.put(f"/api/feedback/messages/{user_id}", json={"rating": "helpful"}).status_code == 404
    assert client.put(f"/api/feedback/messages/{answer_id}", json={"rating": "helpful"}).status_code == 200
    assert client.put(f"/api/feedback/messages/{answer_id}", json={"rating": "unresolved"}).status_code == 200
    assert client.get("/api/feedback").json()["total"] == 1
    login("bob")
    assert client.get("/api/feedback").json()["total"] == 0
    assert client.put(f"/api/feedback/messages/{answer_id}", json={"rating": "helpful"}).status_code == 404
    assert (
        client.post(
            "/api/tickets", json=payload(conversation_name="private", message_id=answer_id)
        ).status_code
        == 404
    )
    login("staff")
    assert client.get("/api/feedback?rating=unresolved").json()["total"] == 1
    assert client.put(f"/api/feedback/messages/{answer_id}", json={"rating": "helpful"}).status_code == 404


def test_ticket_scope_and_pagination(client, login):
    login("staff")
    product, version = catalog(client)
    second = client.post("/api/products", json={"name": "第二产品"}).json()
    login()
    assert (
        client.post(
            "/api/tickets", json=payload(product_id=second["id"], version_id=version["id"])
        ).status_code
        == 422
    )
    assert client.post("/api/tickets", json=payload(version_id=version["id"])).status_code == 422
    create(client, product_id=product["id"], version_id=version["id"])
    create(client)
    page = client.get("/api/tickets?page_size=1").json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert client.get(f"/api/tickets?product_id={product['id']}").json()["total"] == 1
    assert client.get("/api/tickets?status=closed").json()["total"] == 0
    assert client.get("/api/tickets?page_size=10000").status_code == 422


def test_chat_product_scope_is_persisted_and_cannot_switch(client, login, monkeypatch):
    from app.services import rag

    login("staff")
    product, version = catalog(client)
    captured = {}

    def ask(*args, **kwargs):
        captured.update(kwargs)
        return {"answer": "a", "sources": [], "contexts": []}

    monkeypatch.setattr(rag, "ask", ask)
    login()
    response = client.post(
        "/api/chat/ask",
        json={"question": "q", "session": "scoped", "product_id": product["id"], "version_id": version["id"]},
    )
    assert response.status_code == 200 and response.json()["message_id"]
    assert captured["product_id"] == product["id"] and captured["version_id"] == version["id"]
    assert client.get("/api/sessions/scoped").json()["product_id"] == product["id"]
    assert client.post("/api/chat/ask", json={"question": "q", "session": "scoped"}).status_code == 409


def test_concurrent_session_appends_return_their_own_message_ids(client, login):
    from app.models import Message
    from app.services import sessions

    user = login()
    sessions.save_session(user["id"], "并发回答", [])

    def append(number):
        result = sessions.append_messages(
            user["id"], "并发回答", [{"role": "assistant", "content": f"回答{number}"}]
        )
        return result["written_message_ids"][-1], f"回答{number}"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(append, range(2)))
    assert len({value[0] for value in results}) == 2
    with session_factory()() as db:
        for message_id, expected in results:
            assert db.get(Message, message_id).content == expected
