"""Create uploaded rehearsal practice reports.

Revision ID: 20260924_09
Revises: 20260904_08
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import app.db.models  # noqa: F401
from alembic import op
from app.db.base import Base

revision: str = "20260924_09"
down_revision: str | Sequence[str] | None = "20260904_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.tables["upload_practice_sessions"].create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.tables["upload_practice_sessions"].drop(bind=op.get_bind(), checkfirst=True)
