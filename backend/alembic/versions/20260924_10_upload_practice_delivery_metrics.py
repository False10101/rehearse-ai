"""Add uploaded-practice delivery metrics.

Revision ID: 20260924_10
Revises: 20260924_09
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260924_10"
down_revision: str | Sequence[str] | None = "20260924_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column_name in (
        "filler_clusters",
        "pause_events",
        "pace_events",
        "repetition_events",
    ):
        op.add_column(
            "upload_practice_sessions",
            sa.Column(
                column_name,
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    for column_name in (
        "repetition_events",
        "pace_events",
        "pause_events",
        "filler_clusters",
    ):
        op.drop_column("upload_practice_sessions", column_name)
