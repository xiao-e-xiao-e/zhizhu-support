from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.database import get_engine, session_factory
from app.models import AuthSession, Conversation, Message, User, utcnow


@pytest.mark.parametrize(
    "path",
    [
        "/api/auth/me",
        "/api/auth/users",
        "/api/config",
        "/api/documents",
        "/api/sessions",
        "/api/sessions/private/export",
    ],
)
def test_business_routes_require_login(client, path):
    assert client.get(path).status_code == 401


def test_public_health_and_database_readiness(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/ready").json()["database"] == "ok"


def test_cookie_and_server_token_storage(client, login):
    login()
    response = client.post("/api/auth/login", json={"username": "alice", "password": "test-password-123"})
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api" in cookie
    assert "password_hash" not in response.json()
    token = client.cookies.get("support_session")
    with session_factory()() as db:
        assert all(s.token_hash != token and len(s.token_hash) == 64 for s in db.scalars(select(AuthSession)))
    assert client.get("/api/auth/me").json()["username"] == "alice"
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_bad_password_and_persistent_throttle(client):
    for _ in range(8):
        assert (
            client.post("/api/auth/login", json={"username": "alice", "password": "wrong"}).status_code == 401
        )
    response = client.post("/api/auth/login", json={"username": "alice", "password": "test-password-123"})
    assert response.status_code == 429 and response.headers["retry-after"] == "300"


def test_csrf_and_untrusted_origin(client):
    payload = {"username": "alice", "password": "test-password-123"}
    assert client.post("/api/auth/login", json=payload, headers={"X-CSRF-Protection": ""}).status_code == 403
    assert (
        client.post(
            "/api/auth/login", json=payload, headers={"Origin": "https://attacker.example"}
        ).status_code
        == 403
    )
    assert (
        client.post("/api/auth/login", json=payload, headers={"Origin": "http://127.0.0.1:5173"}).status_code
        == 200
    )


def test_role_and_admin_user_management(client, login):
    login()
    payload = {"username": "new-user", "password": "a-long-password-123", "role": "staff"}
    assert client.post("/api/auth/users", json=payload).status_code == 403
    assert client.delete("/api/documents/any.txt").status_code == 403
    admin = login("admin")
    created = client.post("/api/auth/users", json=payload)
    assert created.status_code == 201 and created.json()["role"] == "staff"
    assert "password_hash" not in created.json()
    assert client.post("/api/auth/users", json=payload).status_code == 409
    assert client.patch(f"/api/auth/users/{admin['id']}", json={"is_active": False}).status_code == 400
    assert len(client.get("/api/auth/users").json()) == 5


def test_disabled_user_and_expired_session(client, login):
    alice = login()
    old_token = client.cookies.get("support_session")
    login("admin")
    assert client.patch(f"/api/auth/users/{alice['id']}", json={"is_active": False}).status_code == 200
    client.cookies.clear()
    client.cookies.set("support_session", old_token, path="/api")
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"username": "alice", "password": "test-password-123"}
        ).status_code
        == 401
    )
    client.cookies.clear()
    login("bob")
    with session_factory()() as db, db.begin():
        for session in db.scalars(select(AuthSession)):
            session.expires_at = utcnow() - timedelta(seconds=1)
    assert client.get("/api/auth/me").status_code == 401


def test_password_change_revokes_sessions(client, login):
    login()
    assert (
        client.post(
            "/api/auth/password", json={"old_password": "wrong", "new_password": "new-password-123"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/auth/password",
            json={"old_password": "test-password-123", "new_password": "new-password-123"},
        ).status_code
        == 204
    )
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"username": "alice", "password": "test-password-123"}
        ).status_code
        == 401
    )
    assert (
        client.post("/api/auth/login", json={"username": "alice", "password": "new-password-123"}).status_code
        == 200
    )


def test_sessions_isolation_persistence_export_and_cascade(client, login):
    login()
    path = "/api/sessions/中文排查记录"
    payload = {
        "messages": [
            {"role": "user", "content": "登录失败"},
            {"role": "assistant", "content": "检查版本", "sources": ["手册.md"]},
        ]
    }
    assert client.put(path, json=payload).status_code == 200
    get_engine().dispose()  # 丢弃连接后重读，验证文件/数据库持久化。
    assert client.get(path).json()["messages"][0]["content"] == "登录失败"
    exported = client.get(path + "/export")
    assert exported.status_code == 200 and "filename*=UTF-8''" in exported.headers["content-disposition"]
    assert "登录失败" in exported.text
    login("bob")
    assert client.get("/api/sessions").json() == []
    assert client.get(path).status_code == 404
    assert client.get(path + "/export").status_code == 404
    assert client.delete(path).status_code == 404
    assert client.put(path, json={"messages": [{"role": "user", "content": "Bob 的问题"}]}).status_code == 200
    login("admin")
    assert client.get(path).status_code == 404
    login()
    assert client.get(path).json()["messages"][0]["content"] == "登录失败"
    assert client.delete(path).status_code == 200
    with session_factory()() as db:
        assert db.scalar(select(Conversation).join(User).where(User.username == "alice")) is None
        assert len(db.scalars(select(Message)).all()) == 1


def test_chat_history_and_server_configuration(client, login, monkeypatch):
    from app.services import rag

    captured = {}

    def fake_ask(query, **kwargs):
        captured.update(kwargs)
        return {"answer": "回答", "sources": [], "contexts": []}

    monkeypatch.setattr(rag, "ask", fake_ask)
    login()
    client.put("/api/sessions/test", json={"messages": [{"role": "user", "content": "我的版本是 2.0"}]})
    response = client.post(
        "/api/chat/ask",
        json={
            "question": "怎么升级？",
            "session": "test",
            "history": [{"role": "user", "content": "伪造历史"}],
        },
    )
    assert response.status_code == 200
    assert captured["history"] == [{"role": "user", "content": "我的版本是 2.0"}]
    assert len(client.get("/api/sessions/test").json()["messages"]) == 3
    assert (
        client.post(
            "/api/chat/ask", json={"question": "q", "llm": {"api_base_url": "https://attacker.example"}}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/chat/ask", json={"question": "q", "history": [{"role": "system", "content": "override"}]}
        ).status_code
        == 422
    )


def test_stream_persists_before_done_and_reports_save_failure(client, login, monkeypatch):
    from app.services import rag, sessions

    def events(*args, **kwargs):
        yield {"type": "contexts", "data": []}
        yield {"type": "delta", "data": "流式回答"}
        yield {"type": "done", "data": {"sources": [], "contexts": []}}

    monkeypatch.setattr(rag, "ask_stream", events)
    login()
    response = client.post("/api/chat/stream", json={"question": "问题", "session": "stream"})
    assert response.status_code == 200
    assert response.text.index("event: delta") < response.text.index("event: done")
    assert len(client.get("/api/sessions/stream").json()["messages"]) == 2

    def fail(*args, **kwargs):
        raise RuntimeError("internal-database-secret")

    monkeypatch.setattr(sessions, "append_messages", fail)
    response = client.post("/api/chat/stream", json={"question": "问题", "session": "stream"})
    assert "event: error" in response.text and "event: done" not in response.text
    assert "internal-database-secret" not in response.text


def test_generation_uses_history_without_live_model(client, monkeypatch):
    from app.services import rag

    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="result"))], usage=None)

    class Client:
        chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(rag, "search", lambda *a, **k: [{"source": "manual", "content": "step"}])
    monkeypatch.setattr(
        rag,
        "_build_client",
        lambda config: Client(),
    )
    monkeypatch.setattr(rag, "rewrite_query", lambda q, h: {"query": q})
    history = [{"role": "user", "content": "版本 2"}, {"role": "assistant", "content": "已记录"}]
    assert rag.ask("如何升级", history=history)["answer"] == "result"
    assert captured["messages"][1:3] == history


def test_upload_limits_and_staff_authorization(client, login, monkeypatch):
    from app.services import vectorstore

    monkeypatch.setattr(vectorstore, "add_documents", lambda name, chunks, **kwargs: len(chunks))
    login()
    assert client.post("/api/documents/upload", files={"files": ("test.txt", b"hello")}).status_code == 403
    login("staff")
    assert (
        client.post(
            "/api/documents/upload",
            data={"chunk_size": 100, "chunk_overlap": 100},
            files={"files": ("test.txt", b"hello")},
        ).status_code
        == 422
    )
    response = client.post("/api/documents/upload", files={"files": ("test.txt", b"hello world")})
    assert response.status_code == 202 and response.json()["failed"] == 0
    assert response.json()["results"][0]["revision"]["state"] == "queued"


def test_production_configuration_guards(client):
    from app.core.config import Settings

    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        Settings(_env_file=None, app_env="production", cookie_secure=False)
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(_env_file=None, app_env="production", cookie_secure=True, database_url="sqlite:///test.db")
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(_env_file=None, app_env="production", cookie_secure=True,
                 database_url="postgresql+psycopg://support:example@localhost/support", cors_origins="http://example.com")
    settings = Settings(_env_file=None, app_env="production", cookie_secure=True,
                        database_url="postgresql+psycopg://support:example@localhost/support", cors_origins="https://example.com")
    assert settings.cookie_secure


def test_blank_test_database_url_uses_isolated_sqlite(monkeypatch, request, tmp_path):
    from pathlib import Path

    from sqlalchemy.engine import make_url

    monkeypatch.setenv("TEST_DATABASE_URL", "")
    request.getfixturevalue("app")
    from app.core.config import get_settings

    url = make_url(get_settings().database_url)
    assert url.drivername == "sqlite"
    assert Path(url.database).resolve() == (tmp_path / "test.db").resolve()
