"""Retain the exact slide-analyzer model output.

Revision ID: 20260903_04
Revises: 20260903_03
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260903_04"
down_revision: str | Sequence[str] | None = "20260903_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("presentation_analyses")
    }
    if "raw_output" not in columns:
        op.add_column(
            "presentation_analyses",
            sa.Column(
                "raw_output",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )


def downgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("presentation_analyses")
    }
    if "raw_output" in columns:
        op.drop_column("presentation_analyses", "raw_output")
