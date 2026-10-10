"""Allow Auth0-only users without copied profile fields.

Revision ID: 20260903_03
Revises: 20260903_02
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260903_03"
down_revision: str | Sequence[str] | None = "20260903_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns("users")}

    optional_profile_columns = (
        ("email", sa.String(length=320)),
        ("display_name", sa.String(length=120)),
    )
    for column_name, column_type in optional_profile_columns:
        if not columns[column_name]["nullable"]:
            op.alter_column(
                "users",
                column_name,
                existing_type=column_type,
                existing_nullable=False,
                nullable=True,
            )


def downgrade() -> None:
    op.alter_column(
        "users",
        "display_name",
        existing_type=sa.String(length=120),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        "users",
        "email",
        existing_type=sa.String(length=320),
        existing_nullable=True,
        nullable=False,
    )
