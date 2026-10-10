"""Retain timed speech and focused coaching excerpts.

Revision ID: 20260926_12
Revises: 20260926_11
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260926_12"
down_revision = "20260926_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("timed_transcript", "speech_moments"):
        op.add_column(
            "upload_practice_sessions",
            sa.Column(
                name,
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )


def downgrade() -> None:
    op.drop_column("upload_practice_sessions", "speech_moments")
    op.drop_column("upload_practice_sessions", "timed_transcript")
