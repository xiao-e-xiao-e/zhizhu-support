"""数据库连接与事务。数据库结构统一由 Alembic 管理。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine():
    url = make_url(get_settings().database_url)
    options = {"pool_pre_ping": True}
    if url.get_backend_name() == "sqlite":
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        options["connect_args"] = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, **options)
    if url.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def sqlite_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def session_factory() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False)


def get_db():
    with session_factory()() as db:
        yield db
