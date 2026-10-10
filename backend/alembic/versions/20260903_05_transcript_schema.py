"""Create persistent transcript-generation tables.

Revision ID: 20260903_05
Revises: 20260903_04
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import app.db.models  # noqa: F401
from alembic import op
from app.db.base import Base

revision: str = "20260903_05"
down_revision: str | Sequence[str] | None = "20260903_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "presentation_transcripts",
    "slide_transcripts",
    "transcript_paragraphs",
    "transcript_complex_terms",
    "slide_vocabulary_upgrades",
    "transcript_revisions",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)
