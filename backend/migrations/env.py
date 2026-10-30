from alembic import context

from app import models  # noqa: F401 -- 注册 ORM 元数据
from app.core.database import Base, get_engine

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(url=get_engine().url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True,
                          render_as_batch=connection.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()
