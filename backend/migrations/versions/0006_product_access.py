"""Product grants and retired historical resources."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("restrict_products", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "document_revisions", sa.Column("retired", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("agent_runs", sa.Column("retired", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "product_grants",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "product_id", sa.String(36), sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
        ),
    )


def downgrade():
    op.drop_table("product_grants")
    op.drop_column("agent_runs", "retired")
    op.drop_column("document_revisions", "retired")
    op.drop_column("users", "restrict_products")
