"""Immutable full-slide transcript version history."""

import sqlalchemy as sa

from alembic import op

revision = "20261109_15"
down_revision = "20261010_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The initial migration imports current ORM metadata on fresh installs.
    if "transcript_versions" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "transcript_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "slide_transcript_id",
            sa.Uuid(),
            sa.ForeignKey("slide_transcripts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.String(32), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("restored_from_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "slide_transcript_id", "revision", name="uq_transcript_version_revision"
        ),
    )
    op.create_index(
        "ix_transcript_versions_slide_transcript_id", "transcript_versions", ["slide_transcript_id"]
    )


def downgrade() -> None:
    op.drop_table("transcript_versions")
