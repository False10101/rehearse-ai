"""Store the complete uploaded-practice pace series.

Revision ID: 20260926_11
Revises: 20260924_10
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260926_11"
down_revision: str | Sequence[str] | None = "20260924_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "upload_practice_sessions",
        sa.Column(
            "pace_samples",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("upload_practice_sessions", "pace_samples")
