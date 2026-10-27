"""Link assistant turns to conversation messages without rebuilding existing tables."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("messages", sa.Column("assistant_run_id", sa.String(36), nullable=True))
    op.create_index("ix_messages_assistant_run_id", "messages", ["assistant_run_id"])


def downgrade():
    op.drop_index("ix_messages_assistant_run_id", table_name="messages")
    op.drop_column("messages", "assistant_run_id")
