from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.core.config import BACKEND_DIR
from app.core.database import Base, get_engine, session_factory
from app.models import User


def test_schema_matches_models_and_migration_round_trip(app):
    with get_engine().connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.downgrade(config, "base")
    assert "users" not in inspect(get_engine()).get_table_names()
    command.upgrade(config, "head")
    with get_engine().connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_legacy_import_skips_existing_and_preserves_source(app, tmp_path, monkeypatch, capsys):
    import json
    import sys

    from sqlalchemy import select

    from app.services import sessions
    from manage import main

    source = tmp_path / "legacy.json"
    raw = {"旧会话": [{"role": "user", "content": "旧问题"}]}
    source.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    original = source.read_bytes()
    monkeypatch.setattr(
        sys, "argv", ["manage.py", "import-sessions", "--username", "alice", "--file", str(source)]
    )
    main()
    assert "已导入 1 个会话" in capsys.readouterr().out
    main()
    assert "已导入 0 个会话" in capsys.readouterr().out
    with session_factory()() as db:
        owner = db.scalar(select(User).where(User.username == "alice"))
        assert len(sessions.get_session(owner.id, "旧会话")["messages"]) == 1
    assert source.read_bytes() == original


def test_m2_upgrade_and_downgrade_preserve_existing_messages(app):
    from sqlalchemy import select, text

    from app.models import User
    from app.services import sessions

    with session_factory()() as db:
        owner_id = db.scalar(select(User.id).where(User.username == "alice"))
    saved = sessions.save_session(owner_id, "已有数据", [{"role": "user", "content": "不能丢失的消息"}])
    original_id = saved["messages"][0]["id"]
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.downgrade(config, "0001")
    with get_engine().connect() as connection:
        assert (
            connection.execute(
                text("SELECT content FROM messages WHERE id=:id"), {"id": original_id}
            ).scalar_one()
            == "不能丢失的消息"
        )
    command.upgrade(config, "head")
    assert sessions.get_session(owner_id, "已有数据")["messages"][0]["id"] == original_id
