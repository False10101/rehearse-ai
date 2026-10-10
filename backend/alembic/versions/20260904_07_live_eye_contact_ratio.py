"""Store the iris-based eye-contact aggregate for live sessions.

Revision ID: 20260904_07
Revises: 20260904_06
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_07"
down_revision: str | Sequence[str] | None = "20260904_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("live_practice_sessions", sa.Column("eye_contact_ratio", sa.Float()))


def downgrade() -> None:
    op.drop_column("live_practice_sessions", "eye_contact_ratio")
