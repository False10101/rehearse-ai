"""Isolated guest workspace credentials."""
from alembic import op
import sqlalchemy as sa

revision = "20261111_17"
down_revision = "20261111_16"
branch_labels = None
depends_on = None


def upgrade():
    if "guest_sessions" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table("guest_sessions",
            sa.Column("token_hash", sa.String(64), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    op.drop_table("guest_sessions")
