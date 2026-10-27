from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url


@pytest.fixture
def app(tmp_path, monkeypatch):
    test_url = os.getenv("TEST_DATABASE_URL") or None
    if test_url and not (make_url(test_url).database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用测试库")
    monkeypatch.setenv(
        "DATABASE_URL", test_url or f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("WARMUP_ON_STARTUP", "false")
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path / "originals"))
    monkeypatch.setenv("CHROMA_HOST", "")
    from app.core.config import get_settings
    from app.core.database import get_engine

    get_settings.cache_clear()
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    from manage import migrate

    migrate()
    from app.core.auth import password_hasher
    from app.core.database import Base, session_factory
    from app.models import User

    # PostgreSQL 测试库可复用，但每个用例的数据完全清空。
    with get_engine().begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    with session_factory()() as db, db.begin():
        for name, role in [("admin", "admin"), ("staff", "staff"), ("alice", "user"), ("bob", "user")]:
            db.add(User(username=name, password_hash=password_hasher.hash("test-password-123"), role=role))
    from app.main import app

    yield app
    get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
def client(app):
    with TestClient(app, headers={"X-CSRF-Protection": "1"}) as client:
        yield client


@pytest.fixture
def login(client):
    def perform(username="alice"):
        response = client.post(
            "/api/auth/login", json={"username": username, "password": "test-password-123"}
        )
        assert response.status_code == 200, response.text
        return response.json()

    return perform
