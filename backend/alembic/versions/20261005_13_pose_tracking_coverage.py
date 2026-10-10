"""Save pose visibility coverage; legacy reports remain explicitly unknown."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261005_13"
down_revision = "20260926_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "upload_practice_sessions",
        sa.Column(
            "pose_tracking",
            postgresql.JSONB(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("upload_practice_sessions", "pose_tracking")
