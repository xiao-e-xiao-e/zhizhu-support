# ruff: noqa: F811
from uuid import uuid4

from sqlalchemy import func, select
from test_workflows import execute, fake_model, model_response, new_run, workflow  # noqa: F401


def publish(p):
    item = p.knowledge.enqueue(
        "account.md", "重置链接有效期30分钟。过期后重新申请。".encode(), p.users["admin"].id, p.product, p.v1
    )
    p.ingestion.run_once()
    p.knowledge.change(
        item["document_id"],
        "publish",
        p.users["admin"].id,
        p.knowledge.history(item["document_id"])["revision"],
        item["revision_id"],
    )
    return item


def test_multi_turn_history_sources_feedback_and_replay(workflow, client, login, monkeypatch):  # noqa: F811
    p = workflow
    publish(p)
    captured, _ = fake_model(
        monkeypatch,
        [
            model_response("search_knowledge", {"query": "重置链接"}),
            model_response(answer="有效期30分钟。[资料1]"),
            model_response("search_knowledge", {"query": "重置链接过期"}),
            model_response(answer="过期后重新申请。[资料1]"),
        ],
    )
    login()
    key = uuid4().hex
    first = new_run(
        client,
        session="账号咨询",
        question="重置链接多久有效？",
        product_id=p.product,
        version_id=p.v1,
        request_key=key,
    )
    assert first["message_id"] and first["session"] == "账号咨询"
    assert (
        new_run(
            client,
            session="账号咨询",
            question="重置链接多久有效？",
            product_id=p.product,
            version_id=p.v1,
            request_key=key,
        )["id"]
        == first["id"]
    )
    first = execute(client, first)
    second = execute(
        client,
        new_run(client, session="账号咨询", question="那过期了呢？", product_id=p.product, version_id=p.v1),
    )
    assert [m["content"] for m in captured[2]["messages"][:4]] == [
        p.agent.PROMPT,
        "重置链接多久有效？",
        "有效期30分钟。[资料1]",
        "那过期了呢？",
    ]
    detail = client.get("/api/sessions/账号咨询").json()
    assert len(detail["messages"]) == 4
    assert detail["messages"][1]["run"]["id"] == first["id"]
    assert detail["messages"][3]["id"] == second["message_id"]
    assert detail["messages"][3]["sources"] == ["account.md"]
    assert (
        client.put(f"/api/feedback/messages/{second['message_id']}", json={"rating": "helpful"}).status_code
        == 200
    )
    assert client.get("/api/sessions/账号咨询/export").status_code == 200
    assert (
        client.post(
            "/api/agent/runs",
            json={"question": "篡改上下文", "session": "账号咨询", "request_key": uuid4().hex, "history": []},
        ).status_code
        == 422
    )
    login("bob")
    assert client.get(f"/api/agent/runs/{first['id']}").status_code == 404
    assert client.get("/api/sessions/账号咨询").status_code == 404


def test_confirm_ticket_is_bound_to_chat_and_can_be_followed_up(workflow, client, login, monkeypatch):  # noqa: F811
    from app.core.database import session_factory
    from app.models import Ticket

    p = workflow
    fake_model(
        monkeypatch,
        [
            model_response(
                "create_ticket", {"title": "登录异常", "description": "重登后仍然失败", "priority": "normal"}
            )
        ],
    )
    login()
    draft = execute(client, new_run(client, session="登录处理", product_id=p.product, version_id=p.v1))
    with session_factory()() as db:
        assert db.scalar(select(func.count(Ticket.id))) == 0
    assert client.patch("/api/sessions/登录处理", json={"name": "新的名称"}).status_code == 409
    payload = {**draft["result"]["proposal"], "confirmed": True}
    created = client.post(f"/api/agent/runs/{draft['id']}/confirm-ticket", json=payload)
    assert created.status_code == 200, created.text
    ticket = created.json()
    assert ticket["conversation_id"] and ticket["message_id"] == draft["message_id"]
    assert ticket["conversation_snapshot"][0]["role"] == "user"
    assert (
        client.post(f"/api/agent/runs/{draft['id']}/confirm-ticket", json=payload).json()["id"]
        == ticket["id"]
    )
    transcript = client.get("/api/sessions/登录处理").json()
    assert transcript["messages"][1]["run"]["ticket_id"] == ticket["id"]
    captured, _ = fake_model(
        monkeypatch,
        [
            model_response("get_ticket_status", {"ticket_id": ticket["id"]}),
            model_response(answer="工单待处理。"),
        ],
    )
    follow = execute(
        client,
        new_run(
            client,
            session="登录处理",
            question="刚才提交的工单现在什么状态？",
            product_id=p.product,
            version_id=p.v1,
        ),
    )
    assert follow["result"]["ticket_status"]["id"] == ticket["id"]
    assert ticket["id"] in str(captured[0]["messages"][1:3])
    renamed = client.patch("/api/sessions/登录处理", json={"name": "账号支持"})
    assert renamed.status_code == 200
    assert renamed.json()["messages"][1]["id"] == draft["message_id"]


def test_deleting_chat_cancels_pending_confirmation_and_retry_keeps_renamed_session(
    workflow, client, login, monkeypatch
):  # noqa: F811
    login()
    fake_model(monkeypatch, [RuntimeError("provider down")])
    run = execute(client, new_run(client, session="原名称"))
    assert run["status"] == "failed"
    assert client.patch("/api/sessions/原名称", json={"name": "新名称"}).status_code == 200
    retry = client.post(f"/api/agent/runs/{run['id']}/retry", json={"request_key": uuid4().hex})
    assert retry.status_code == 202 and retry.json()["session"] == "新名称"
    retry = retry.json()
    assert client.delete("/api/sessions/新名称").status_code == 200
    assert client.get(f"/api/agent/runs/{retry['id']}").json()["status"] == "cancelled"
    assert (
        client.post(
            f"/api/agent/runs/{retry['id']}/confirm-ticket",
            json={"title": "标题", "description": "描述", "priority": "normal", "confirmed": True},
        ).status_code
        == 409
    )


def test_legacy_runs_adopt_once_and_demotion_hides_shared_chat(workflow, client, login, monkeypatch):  # noqa: F811
    from app.core.database import session_factory
    from app.models import User
    from app.services.assistant_chat import adopt_history

    login("staff")
    fake_model(
        monkeypatch,
        [model_response("create_ticket", {"title": "标题", "description": "描述", "priority": "normal"})],
    )
    old = execute(client, new_run(client))
    # Recreate the pre-upgrade shape: a real run without a conversation link.
    from sqlalchemy import delete

    from app.models import AgentRun, Conversation, Message

    with session_factory()() as db, db.begin():
        run = db.get(AgentRun, old["id"])
        conversation_id = run.input["conversation_id"]
        db.execute(delete(Message).where(Message.conversation_id == conversation_id))
        db.execute(delete(Conversation).where(Conversation.id == conversation_id))
        run.input = {
            key: value
            for key, value in run.input.items()
            if key not in {"session", "history", "conversation_id"}
        }
    assert adopt_history() == 1
    assert adopt_history() == 0
    old = client.get(f"/api/agent/runs/{old['id']}").json()
    assert old["session"] and old["message_id"]
    assert client.get("/api/sessions").json()[0]["name"] == old["session"]
    with session_factory()() as db, db.begin():
        db.scalar(select(User).where(User.username == "staff")).role = "user"
    assert client.get("/api/sessions").json() == []
    assert client.get(f"/api/sessions/{old['session']}").status_code == 404


def test_conversation_names_and_fixed_product_scope(workflow, client, login):
    p = workflow
    login()
    run = new_run(client, question="PDF/DOCX\\文件\n解析失败", product_id=p.product, version_id=p.v1)
    assert all(char not in run["session"] for char in ["/", "\\", "\n"])
    assert client.get(f"/api/sessions/{run['session']}").status_code == 200
    assert client.post(f"/api/agent/runs/{run['id']}/cancel").status_code == 200
    assert (
        client.post(
            "/api/agent/runs",
            json={
                "question": "另一版本",
                "session": run["session"],
                "request_key": uuid4().hex,
                "product_id": p.product,
                "version_id": p.v2,
            },
        ).status_code
        == 409
    )
    assert client.patch(f"/api/sessions/{run['session']}", json={"name": "path/name"}).status_code == 422
    assert client.patch(f"/api/sessions/{run['session']}", json={"name": "   "}).status_code == 422
    assert (
        client.post(
            "/api/agent/runs", json={"question": "问题", "session": "path/name", "request_key": uuid4().hex}
        ).status_code
        == 422
    )


def test_ticket_status_evidence_preserves_all_tickets_and_unique_citations():
    from app.services.agent import _merge_evidence

    result = {"contexts": [], "sources": [], "related_tickets": [], "ticket_status": None}
    reference = _merge_evidence(result, {"tickets": [{"id": "old", "title": "历史案例", "solution": "方案"}]})
    current = _merge_evidence(result, {"ticket": {"id": "new", "title": "本次工单", "status": "new"}})
    assert reference["tickets"][0]["citation"] == "工单1"
    assert current["ticket"]["citation"] == "工单2"
    _merge_evidence(result, {"ticket": {"id": "old", "title": "历史案例", "status": "resolved"}})
    _merge_evidence(result, {"ticket": {"id": "new", "title": "本次工单", "status": "in_progress"}})
    assert len(result["ticket_statuses"]) == 2
    assert result["ticket_statuses"][0]["status"] == "in_progress"
    assert result["ticket_statuses"][0]["citation"] == "工单2"


def test_missing_details_are_requested_without_claiming_knowledge_or_creating_ticket(
    workflow, client, login, monkeypatch
):
    from app.core.database import session_factory
    from app.models import Ticket

    login()
    captured, _ = fake_model(
        monkeypatch,
        [model_response("ask_clarification", {"question": "请说明遇到问题的产品、版本和错误提示。"})],
    )
    run = execute(client, new_run(client, question="我遇到了问题", session="问题排查"))
    assert captured[0]["tool_choice"] == "required"
    assert run["status"] == "completed" and run["result"]["needs_input"]
    assert run["result"]["contexts"] == []
    assert "产品" in run["result"]["answer"]
    with session_factory()() as db:
        assert db.scalar(select(func.count(Ticket.id))) == 0
    assert client.get("/api/sessions/问题排查").json()["messages"][1]["content"] == run["result"]["answer"]
