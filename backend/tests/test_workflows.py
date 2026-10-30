import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select


@pytest.fixture
def workflow(client, monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.core.database import session_factory
    from app.models import Product, ProductVersion, User
    from app.services import agent, ingestion, knowledge, vectorstore

    get_settings().chroma_dir = tmp_path / "vectors"
    monkeypatch.setattr(vectorstore, "_client", None)
    monkeypatch.setattr(vectorstore, "_ENSURED", False)
    embedder = SimpleNamespace(
        embed_query=lambda text: [1.0, 0.0], embed_documents=lambda texts: [[1.0, 0.0] for _ in texts]
    )
    for module in [agent, vectorstore, ingestion]:
        monkeypatch.setattr(module, "get_embedding_service", lambda: embedder)
    with session_factory()() as db, db.begin():
        users = {u.username: u for u in db.scalars(select(User))}
        product = Product(name="Atlas", description="test")
        db.add(product)
        db.flush()
        versions = [ProductVersion(product_id=product.id, name=v) for v in ["2.0", "3.0"]]
        db.add_all(versions)
    return SimpleNamespace(
        agent=agent,
        knowledge=knowledge,
        ingestion=ingestion,
        users=users,
        product=product.id,
        v1=versions[0].id,
        v2=versions[1].id,
    )


def model_response(name=None, arguments=None, answer="处理完成[资料1]", tokens=40):
    calls = (
        [
            SimpleNamespace(
                id="call_" + uuid4().hex,
                function=SimpleNamespace(
                    name=name, arguments=json.dumps(arguments or {}, ensure_ascii=False)
                ),
            )
        ]
        if name
        else []
    )
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(tool_calls=calls, content=answer),
                finish_reason="tool_calls" if calls else "stop",
            )
        ],
        usage=SimpleNamespace(total_tokens=tokens),
    )


def fake_model(monkeypatch, responses):
    from app.services import rag

    captured, closed = [], []

    class Stream:
        def __init__(self, response):
            self.response = response

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def __iter__(self):
            if hasattr(self.response, "chunks"):
                yield from self.response.chunks
                return
            message = self.response.choices[0].message
            for index, call in enumerate(message.tool_calls):
                args = call.function.arguments
                for start in range(0, len(args), 3):
                    yield SimpleNamespace(
                        usage=None,
                        choices=[
                            SimpleNamespace(
                                finish_reason=None,
                                delta=SimpleNamespace(
                                    content=None,
                                    tool_calls=[
                                        SimpleNamespace(
                                            index=index,
                                            id=call.id if start == 0 else None,
                                            function=SimpleNamespace(
                                                name=call.function.name if start == 0 else None,
                                                arguments=args[start : start + 3],
                                            ),
                                        )
                                    ],
                                ),
                            )
                        ],
                    )
            if not message.tool_calls:
                for start in range(0, len(message.content), 2):
                    yield SimpleNamespace(
                        usage=None,
                        choices=[
                            SimpleNamespace(
                                finish_reason=None,
                                delta=SimpleNamespace(
                                    content=message.content[start : start + 2], tool_calls=None
                                ),
                            )
                        ],
                    )
            yield SimpleNamespace(
                usage=self.response.usage,
                choices=[
                    SimpleNamespace(
                        finish_reason=self.response.choices[0].finish_reason,
                        delta=SimpleNamespace(content=None, tool_calls=None),
                    )
                ],
            )

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append(True)

        def with_options(self, **kwargs):
            return self

        @property
        def chat(self):
            return SimpleNamespace(completions=self)

        def create(self, **kwargs):
            captured.append(kwargs)
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return Stream(response) if kwargs.get("stream") else response

    monkeypatch.setattr(rag, "_build_client", lambda _: Client())
    return captured, closed


def new_run(client, **changes):
    response = client.post(
        "/api/agent/runs", json={"question": "帮我处理登录问题", "request_key": uuid4().hex, **changes}
    )
    assert response.status_code == 202, response.text
    return response.json()


def execute(client, run):
    response = client.post(f"/api/agent/runs/{run['id']}/execute")
    assert response.status_code == 200, response.text
    return response.json()


def ticket(p, owner="alice", status="resolved", version=None, solution="退出并重新登录。"):
    from app.core.database import session_factory
    from app.models import Ticket, TicketEvent

    with session_factory()() as db, db.begin():
        row = Ticket(
            creator_id=p.users[owner].id,
            title="E401 登录会话过期",
            description="登录报 E401，联系 alice@example.com，手机号13800138000。",
            status=status,
            priority="normal",
            idempotency_key=uuid4().hex,
            request_hash="test",
            product_id=p.product,
            version_id=version or p.v1,
        )
        db.add(row)
        db.flush()
        if status in {"resolved", "closed"}:
            db.add(
                TicketEvent(
                    ticket_id=row.id,
                    actor_id=p.users["staff"].id,
                    kind="status",
                    content=solution,
                    details={"from_status": "in_progress", "to_status": "resolved"},
                )
            )
    return row


def faq_create(client, row, mode="manual"):
    result = client.post("/api/faqs", json={"ticket_id": row.id, "mode": mode, "request_key": uuid4().hex})
    assert result.status_code in {200, 201, 202}, result.text
    return result.json()


def faq_action(client, draft, action, **fields):
    response = client.post(
        f"/api/faqs/{draft['id']}/{action}", json={"revision": draft["revision"], **fields}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_workflow_auth_and_run_owner_isolation(workflow, client, login):
    assert client.get("/api/agent/runs").status_code == 401
    assert client.get("/api/faqs").status_code == 401
    login()
    run = new_run(client)
    login("bob")
    for action in ["", "/execute", "/stream", "/cancel"]:
        response = (
            client.get(f"/api/agent/runs/{run['id']}")
            if not action
            else client.post(f"/api/agent/runs/{run['id']}{action}")
        )
        assert response.status_code == 404
    assert client.get("/api/agent/runs").json()["total"] == 0
    assert client.get("/api/faqs").status_code == 403
    login("admin")
    assert client.get(f"/api/agent/runs/{run['id']}").status_code == 404


def test_run_request_idempotence_and_active_limit(workflow, client, login):
    login()
    key = uuid4().hex
    run = new_run(client, request_key=key)
    assert new_run(client, request_key=key)["id"] == run["id"]
    assert (
        client.post("/api/agent/runs", json={"question": "different", "request_key": key}).status_code == 409
    )
    assert (
        client.post("/api/agent/runs", json={"question": "other", "request_key": uuid4().hex}).status_code
        == 409
    )
    assert client.post(f"/api/agent/runs/{run['id']}/cancel").json()["status"] == "cancelled"
    assert new_run(client)["id"] != run["id"]


def test_agent_published_knowledge_and_scoped_tools(workflow, client, login, monkeypatch):
    p = workflow
    old = p.knowledge.enqueue(
        "manual.txt", "E401 请退出重新登录".encode(), p.users["admin"].id, p.product, p.v1
    )
    p.ingestion.run_once()
    hist = p.knowledge.history(old["document_id"])
    p.knowledge.change(
        old["document_id"], "publish", p.users["admin"].id, hist["revision"], old["revision_id"]
    )
    p.knowledge.enqueue("draft.txt", b"draft secret", p.users["admin"].id, p.product, p.v1)
    p.ingestion.run_once()
    captured, closed = fake_model(
        monkeypatch,
        [
            model_response("search_knowledge", {"query": "E401"}),
            model_response(answer="请退出重新登录[资料1]"),
        ],
    )
    login()
    run = execute(client, new_run(client, product_id=p.product, version_id=p.v1))
    assert run["status"] == "completed" and len(run["result"]["contexts"]) == 1
    assert run["result"]["contexts"][0]["revision_id"] == old["revision_id"]
    assert run["result"]["usage"]["model_calls"] == 2
    assert [s["name"] for s in run["steps"]] == ["model", "search_knowledge", "model"]
    assert len(captured) == 2 and closed == [True]
    for schema in captured[0]["tools"]:
        assert "user_id" not in schema["function"]["parameters"]["properties"]
        assert "product_id" not in schema["function"]["parameters"]["properties"]


def test_agent_cannot_query_another_users_ticket(workflow, client, login, monkeypatch):
    other = ticket(workflow, owner="bob")
    fake_model(
        monkeypatch,
        [model_response("get_ticket_status", {"ticket_id": other.id}), model_response(answer="偷偷获取状态")],
    )
    login()
    result = execute(client, new_run(client))
    assert result["result"]["ticket_status"] is None
    assert result["steps"][1]["status"] == "failed" and "不存在" in result["steps"][1]["error"]
    assert "偷偷" not in result["result"]["answer"]


def test_similar_ticket_scope_role_and_semantic_ranking(workflow):
    p = workflow
    mine = ticket(p)
    other = ticket(p, owner="bob")
    ticket(p, owner="alice", version=p.v2)
    ticket(p, owner="alice", status="in_progress")
    assert [
        r["id"] for r in p.agent.search_resolved_tickets(p.users["alice"].id, "登录", 5, p.product, p.v1)
    ] == [mine.id]
    rows = p.agent.search_resolved_tickets(p.users["staff"].id, "登录", 5, p.product, p.v1)
    assert {r["id"] for r in rows} == {mine.id, other.id}
    assert all("alice@example.com" not in str(r) for r in rows)


@pytest.mark.parametrize(
    "name,args",
    [
        ("delete_database", {}),
        ("search_knowledge", {"query": "q", "user_id": "other"}),
        ("search_knowledge", {"query": "q", "top_k": 1000}),
        ("create_ticket", {"title": "x", "description": "x", "creator_id": "other"}),
    ],
)
def test_unregistered_and_invalid_tool_arguments(workflow, client, login, monkeypatch, name, args):
    fake_model(monkeypatch, [model_response(name, args), model_response()])
    login()
    result = execute(client, new_run(client))
    assert result["steps"][1]["status"] == "failed" and result["steps"][1]["input"] == {}
    from app.core.database import session_factory
    from app.models import Ticket

    with session_factory()() as db:
        assert db.scalar(select(func.count(Ticket.id))) == 0


def test_model_write_is_only_proposal_confirmation_exactly_once(workflow, client, login, monkeypatch):
    p = workflow
    fake_model(
        monkeypatch,
        [
            model_response(
                "create_ticket",
                {"title": "登录故障", "description": "无法登录，已尝试重启", "priority": "high"},
            )
        ],
    )
    login()
    run = execute(client, new_run(client, product_id=p.product, version_id=p.v1))
    assert run["status"] == "awaiting_confirmation"
    from app.core.database import session_factory
    from app.models import Ticket

    with session_factory()() as db:
        assert db.scalar(select(func.count(Ticket.id))) == 0
    payload = {**run["result"]["proposal"], "confirmed": True}
    assert (
        client.post(
            f"/api/agent/runs/{run['id']}/confirm-ticket", json={**payload, "confirmed": False}
        ).status_code
        == 422
    )
    login("bob")
    assert client.post(f"/api/agent/runs/{run['id']}/confirm-ticket", json=payload).status_code == 404
    login()
    response = client.post(f"/api/agent/runs/{run['id']}/confirm-ticket", json=payload)
    assert response.status_code == 200, response.text
    created = response.json()
    assert created["creator_id"] == p.users["alice"].id and created["version_id"] == p.v1
    assert (
        client.post(f"/api/agent/runs/{run['id']}/confirm-ticket", json=payload).json()["id"] == created["id"]
    )
    assert (
        client.post(
            f"/api/agent/runs/{run['id']}/confirm-ticket", json={**payload, "title": "改动"}
        ).status_code
        == 409
    )
    with session_factory()() as db:
        assert db.scalar(select(func.count(Ticket.id))) == 1


def test_confirmation_rolls_back_ticket_with_run(workflow, client, login, monkeypatch):
    from app.services import support
    from app.workflow_schemas import ConfirmTicket

    p = workflow
    fake_model(
        monkeypatch, [model_response("create_ticket", {"title": "登录故障", "description": "操作失败"})]
    )
    login()
    run = execute(client, new_run(client))
    original = support.create_ticket

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("crash before transaction commit")

    monkeypatch.setattr(support, "create_ticket", interrupted)
    with pytest.raises(RuntimeError):
        p.agent.confirm_ticket(
            p.users["alice"], run["id"], ConfirmTicket(**run["result"]["proposal"], confirmed=True)
        )
    from app.core.database import session_factory
    from app.models import Ticket

    with session_factory()() as db:
        assert db.scalar(select(func.count(Ticket.id))) == 0
    assert p.agent.get_run(p.users["alice"], run["id"])["status"] == "awaiting_confirmation"


def test_concurrent_confirmation_single_ticket(workflow, client, login, monkeypatch):
    from app.workflow_schemas import ConfirmTicket

    p = workflow
    fake_model(
        monkeypatch, [model_response("create_ticket", {"title": "登录故障", "description": "操作失败"})]
    )
    login()
    run = execute(client, new_run(client))
    payload = ConfirmTicket(**run["result"]["proposal"], confirmed=True)

    def confirm(_):
        try:
            return p.agent.confirm_ticket(p.users["alice"], run["id"], payload)["id"]
        except HTTPException as exc:
            assert exc.status_code == 409
            return None

    with ThreadPoolExecutor(max_workers=3) as pool:
        ids = [i for i in pool.map(confirm, range(3)) if i]
    assert len(set(ids)) == 1


def test_provider_failure_retry_and_stale_recovery(workflow, client, login, monkeypatch):
    p = workflow
    fake_model(monkeypatch, [TimeoutError("private-api-key")])
    login()
    result = execute(client, new_run(client))
    assert result["status"] == "failed" and "private-api" not in str(result)
    assert result["steps"][0]["status"] == "failed"
    retry = client.post(f"/api/agent/runs/{result['id']}/retry", json={"request_key": uuid4().hex}).json()
    assert retry["parent_id"] == result["id"]
    from app.core.database import session_factory
    from app.models import AgentRun, utcnow

    with session_factory()() as db, db.begin():
        db.get(AgentRun, retry["id"]).expires_at = utcnow() - timedelta(seconds=1)
    stale = p.agent.get_run(p.users["alice"], retry["id"])
    assert stale["status"] == "failed" and stale["error_code"] == "timeout"


def test_generator_disconnect_and_proposal_expiry(workflow, client, login, monkeypatch):
    p = workflow
    login()
    run = new_run(client)
    stream = p.agent.execute(p.users["alice"], run["id"])
    next(stream)
    stream.close()
    assert p.agent.get_run(p.users["alice"], run["id"])["status"] == "cancelled"
    fake_model(monkeypatch, [model_response("create_ticket", {"title": "故障", "description": "现象"})])
    proposal = execute(client, new_run(client))
    from app.core.database import session_factory
    from app.models import AgentRun, utcnow

    with session_factory()() as db, db.begin():
        db.get(AgentRun, proposal["id"]).expires_at = utcnow() - timedelta(seconds=1)
    payload = {**proposal["result"]["proposal"], "confirmed": True}
    assert client.post(f"/api/agent/runs/{proposal['id']}/confirm-ticket", json=payload).status_code == 409


def test_tool_and_token_limits(workflow, client, login, monkeypatch):
    from app.core.config import get_settings

    get_settings().agent_max_steps = 1
    fake_model(
        monkeypatch,
        [
            model_response("search_knowledge", {"query": "q"}),
            model_response("search_knowledge", {"query": "again"}),
        ],
    )
    login()
    result = execute(client, new_run(client))
    assert result["status"] == "failed" and result["error_code"] == "step_limit"
    get_settings().agent_token_budget = 1
    result = execute(client, new_run(client))
    assert result["error_code"] == "token_limit"


def test_faq_review_index_publish_and_private_source(workflow, client, login):
    p = workflow
    row = ticket(p)
    login()
    assert (
        client.post(
            "/api/faqs", json={"ticket_id": row.id, "mode": "manual", "request_key": uuid4().hex}
        ).status_code
        == 403
    )
    login("staff")
    draft = faq_create(client, row)
    assert "alice@example.com" not in str(draft["source_snapshot"])
    assert faq_create(client, row)["id"] == draft["id"]
    submitted = faq_action(client, draft, "submit")
    assert (
        client.post(
            f"/api/faqs/{draft['id']}/review",
            json={
                "revision": submitted["revision"],
                "decision": "approve",
                "reviewed_no_sensitive_data": True,
            },
        ).status_code
        == 403
    )
    login("admin")
    assert (
        client.post(
            f"/api/faqs/{draft['id']}/review", json={"revision": submitted["revision"], "decision": "approve"}
        ).status_code
        == 422
    )
    approved = faq_action(client, submitted, "review", decision="approve", reviewed_no_sensitive_data=True)
    assert approved["state"] == "indexing" and p.knowledge.search("E401") == []
    assert (
        client.post(f"/api/faqs/{draft['id']}/publish", json={"revision": approved["revision"]}).status_code
        == 409
    )
    p.ingestion.run_once()
    published = faq_action(client, approved, "publish")
    assert published["state"] == "published" and published["knowledge_state"] == "published"
    hits = p.knowledge.search("E401")
    assert len(hits) == 1 and row.id not in hits[0]["content"]
    assert "source_snapshot" not in hits[0]["content"]
    login()
    assert client.get(f"/api/faqs/{draft['id']}").status_code == 403
    assert client.get("/api/documents").json()[0]["id"] == published["document_id"]


def test_faq_reject_edit_stale_and_source_reopen_guard(workflow, client, login):
    p = workflow
    row = ticket(p)
    login("staff")
    draft = faq_create(client, row)
    submitted = faq_action(client, draft, "submit")
    login("admin")
    rejected = faq_action(client, submitted, "review", decision="reject", note="补充适用条件")
    assert rejected["state"] == "rejected"
    assert (
        client.patch(
            f"/api/faqs/{draft['id']}", json={"revision": draft["revision"], "question": "q", "answer": "a"}
        ).status_code
        == 409
    )
    updated = client.patch(
        f"/api/faqs/{draft['id']}",
        json={"revision": rejected["revision"], "question": "E401如何处理", "answer": "退出重新登录"},
    ).json()
    submitted = faq_action(client, updated, "submit")
    response = client.post(
        f"/api/tickets/{row.id}/status",
        json={"expected_revision": row.revision, "status": "in_progress", "note": "仍然失败"},
    )
    assert response.status_code == 200
    assert (
        client.post(
            f"/api/faqs/{draft['id']}/review",
            json={
                "revision": submitted["revision"],
                "decision": "approve",
                "reviewed_no_sensitive_data": True,
            },
        ).status_code
        == 409
    )


def test_faq_generation_trace_failure_and_manual_fallback(workflow, client, login, monkeypatch):
    row = ticket(workflow)
    fake_model(monkeypatch, [model_response(answer='{"question":"E401如何处理","answer":"退出重新登录。"}')])
    login("staff")
    draft = faq_create(client, row, "model")
    assert draft["state"] == "generating"
    generated = client.post(f"/api/faqs/{draft['id']}/generate").json()
    assert generated["state"] == "draft"
    assert client.post(f"/api/faqs/{draft['id']}/generate").json()["question"] == "E401如何处理"
    login("admin")
    assert client.get(f"/api/agent/runs/{generated['run_id']}").status_code == 200
    login()
    assert client.get(f"/api/agent/runs/{generated['run_id']}").status_code == 404
    login("staff")
    regenerated = client.post(
        f"/api/faqs/{draft['id']}/regenerate",
        json={"revision": generated["revision"], "request_key": uuid4().hex},
    ).json()
    assert regenerated["state"] == "generating"
    fake_model(monkeypatch, [model_response(answer="invalid-json-private-secret")])
    failed = client.post(f"/api/faqs/{draft['id']}/generate").json()
    assert failed["state"] == "failed" and "private-secret" not in str(failed)
    saved = client.patch(
        f"/api/faqs/{draft['id']}",
        json={"revision": failed["revision"], "question": "人工FAQ", "answer": "人工核实答案"},
    ).json()
    assert saved["state"] == "draft"


def test_faq_atomic_publication_and_new_draft_preserve_published(workflow, client, login, monkeypatch):
    from app.services import faq

    p = workflow
    row = ticket(p)
    login("admin")
    draft = faq_create(client, row)
    submitted = faq_action(client, draft, "submit")
    approved = faq_action(client, submitted, "review", decision="approve", reviewed_no_sensitive_data=True)
    p.ingestion.run_once()
    original = faq.event

    def crash(db, draft, user, action, note=""):
        if action == "publish":
            raise RuntimeError("simulated commit failure")
        original(db, draft, user, action, note)

    monkeypatch.setattr(faq, "event", crash)
    with pytest.raises(RuntimeError):
        faq_action(client, approved, "publish")
    assert p.knowledge.eligible_revisions() == []
    monkeypatch.setattr(faq, "event", original)
    published = faq_action(client, approved, "publish")
    revised = faq_action(client, published, "revise")
    assert revised["state"] == "draft" and len(p.knowledge.search("E401")) == 1


def test_faq_requires_solved_ticket_and_knowledge_gap_statistics(workflow, client, login):
    row = ticket(workflow, status="in_progress")
    login("staff")
    assert (
        client.post(
            "/api/faqs", json={"ticket_id": row.id, "mode": "manual", "request_key": uuid4().hex}
        ).status_code
        == 409
    )
    from app.core.database import session_factory
    from app.models import Feedback

    with session_factory()() as db, db.begin():
        for _ in range(2):
            db.add(
                Feedback(
                    user_id=workflow.users["alice"].id,
                    rating="unresolved",
                    question="E401 仍未解决",
                    answer="请重登",
                )
            )
    gaps = client.get("/api/faqs/gaps").json()
    assert gaps[0]["count"] == 2
    login()
    assert client.get("/api/faqs/gaps").status_code == 403


def test_staff_run_hidden_after_demotion_and_permissions_never_expand(workflow, client, login, monkeypatch):
    p = workflow
    row = ticket(p, owner="bob")
    login("staff")
    staff_key = uuid4().hex
    staff_run = new_run(client, request_key=staff_key)
    from app.core.database import session_factory
    from app.models import User

    with session_factory()() as db, db.begin():
        db.get(User, p.users["staff"].id).role = "user"
    assert client.get(f"/api/agent/runs/{staff_run['id']}").status_code == 404
    assert client.get("/api/agent/runs").json()["total"] == 0
    assert (
        client.post(
            "/api/agent/runs", json={"question": "帮我处理登录问题", "request_key": staff_key}
        ).status_code
        == 404
    )
    assert client.post(f"/api/agent/runs/{staff_run['id']}/execute").status_code == 404
    login()
    normal_run = new_run(client)
    with session_factory()() as db, db.begin():
        db.get(User, p.users["alice"].id).role = "staff"
    fake_model(monkeypatch, [model_response("get_ticket_status", {"ticket_id": row.id}), model_response()])
    result = execute(client, normal_run)
    assert result["result"]["ticket_status"] is None


def test_tool_timeout_is_recorded_and_cancelled_proposal_is_unusable(workflow, client, login, monkeypatch):
    p = workflow

    def timeout(*args):
        raise p.agent.RunStopped("tool_timeout", "工具执行超时")

    monkeypatch.setattr(p.agent, "bounded_read", timeout)
    fake_model(monkeypatch, [model_response("search_knowledge", {"query": "q"}), model_response()])
    login()
    result = execute(client, new_run(client))
    assert result["steps"][1]["status"] == "failed" and "超时" in result["steps"][1]["error"]
    fake_model(monkeypatch, [model_response("create_ticket", {"title": "故障", "description": "现象"})])
    pending = execute(client, new_run(client))
    cancelled = client.post(f"/api/agent/runs/{pending['id']}/cancel").json()
    assert cancelled["steps"][-1]["status"] == "failed"
    assert (
        client.post(
            f"/api/agent/runs/{pending['id']}/confirm-ticket",
            json={**pending["result"]["proposal"], "confirmed": True},
        ).status_code
        == 409
    )
