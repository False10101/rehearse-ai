"""Persist the audience knowledge level selected for transcript generation."""

from alembic import op
import sqlalchemy as sa

revision = "20261010_14"
down_revision = "20261005_13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older schema migrations use current ORM metadata when creating tables.
    # A fresh database may therefore already have this column.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("presentation_transcripts")}
    if "target_audience_level" not in columns:
        op.add_column("presentation_transcripts", sa.Column("target_audience_level", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("presentation_transcripts", "target_audience_level")
