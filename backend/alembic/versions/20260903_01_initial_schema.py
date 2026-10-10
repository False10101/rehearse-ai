"""Create the initial Rehearse AI PostgreSQL schema.

Revision ID: 20260903_01
Revises:
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import app.db.models  # noqa: F401
from alembic import op
from app.db.base import Base

revision: str = "20260903_01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
