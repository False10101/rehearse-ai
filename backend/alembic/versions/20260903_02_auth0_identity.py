"""Use Auth0 as the sole user identity provider.

Revision ID: 20260903_02
Revises: 20260903_01
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260903_02"
down_revision: str | Sequence[str] | None = "20260903_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    user_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}

    if "password_hash" in user_columns:
        op.drop_column("users", "password_hash")
    if "google_subject" in user_columns:
        op.alter_column(
            "users",
            "google_subject",
            new_column_name="auth0_subject",
            existing_type=sa.String(length=255),
            existing_nullable=True,
            nullable=False,
        )


def downgrade() -> None:
    op.alter_column(
        "users",
        "auth0_subject",
        new_column_name="google_subject",
        existing_type=sa.String(length=255),
        existing_nullable=False,
        nullable=True,
    )
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
