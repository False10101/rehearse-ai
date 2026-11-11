"""Hold generated replacements for explicit per-slide review."""
import sqlalchemy as sa
from alembic import op
revision = "20261111_16"
down_revision = "20261109_15"
branch_labels = None
depends_on = None


def upgrade():
    if "transcript_generation_drafts" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "transcript_generation_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slide_id", sa.Uuid(), sa.ForeignKey("slides.id", ondelete="CASCADE"), nullable=False),
        sa.Column("base_transcript_id", sa.Uuid(), nullable=True),
        sa.Column("base_revision", sa.Integer(), nullable=True),
        sa.Column("before_text", sa.Text(), nullable=False),
        sa.Column("generated_result", sa.Text(), nullable=False),
        sa.Column("settings", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_transcript_generation_drafts_slide_id", "transcript_generation_drafts", ["slide_id"])


def downgrade():
    op.drop_table("transcript_generation_drafts")
