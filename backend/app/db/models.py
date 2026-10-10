import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class TimestampedModel:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampedModel, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    auth0_subject: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )


class Presentation(TimestampedModel, Base):
    __tablename__ = "presentations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(
        String(32), default="queued", server_default="queued", nullable=False
    )
    slide_count: Mapped[int | None] = mapped_column(Integer)
    processing_error_code: Mapped[str | None] = mapped_column(String(80))


class Slide(Base):
    __tablename__ = "slides"
    __table_args__ = (
        UniqueConstraint("presentation_id", "slide_number", name="uq_slides_presentation_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("presentations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    slide_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    layout_name: Mapped[str | None] = mapped_column(String(255))
    extracted_content: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    image_storage_key: Mapped[str | None] = mapped_column(String(512))
    background_color: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PresentationAnalysis(Base):
    __tablename__ = "presentation_analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("presentations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_id: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    overall_score: Mapped[float | None] = mapped_column(Float)
    score_rationale: Mapped[str | None] = mapped_column(Text)
    deck_top_priorities: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    examiner_red_flags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    agenda_status: Mapped[str | None] = mapped_column(String(16))
    cohesion_feedback: Mapped[str | None] = mapped_column(Text)
    raw_output: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="queued", server_default="queued", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SlideAnalysis(Base):
    __tablename__ = "slide_analyses"
    __table_args__ = (
        UniqueConstraint("presentation_analysis_id", "slide_id", name="uq_slide_analysis_per_run"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    presentation_analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("presentation_analyses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    slide_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("slides.id", ondelete="CASCADE"), index=True, nullable=False
    )
    slide_score: Mapped[float | None] = mapped_column(Float)
    overload: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    overload_reason: Mapped[str | None] = mapped_column(Text)
    visual_hierarchy_issues: Mapped[str | None] = mapped_column(Text)
    improvement_suggestions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    table_tips: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    refs_found: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class AnalysisComplexTerm(Base):
    __tablename__ = "analysis_complex_terms"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    presentation_analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("presentation_analyses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)


class PresentationTranscript(TimestampedModel, Base):
    __tablename__ = "presentation_transcripts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    presentation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("presentations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    target_tone: Mapped[str | None] = mapped_column(String(32))
    target_style: Mapped[str | None] = mapped_column(String(32))
    target_audience_level: Mapped[str | None] = mapped_column(String(32))
    target_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    model_id: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="queued", server_default="queued", nullable=False
    )


class SlideTranscript(Base):
    __tablename__ = "slide_transcripts"
    __table_args__ = (
        UniqueConstraint(
            "presentation_transcript_id", "slide_id", name="uq_slide_transcript_per_run"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    presentation_transcript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("presentation_transcripts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    slide_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("slides.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tone_classification: Mapped[str | None] = mapped_column(String(32))
    tone_confidence: Mapped[float | None] = mapped_column(Float)
    tone_rationale: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TranscriptParagraph(Base):
    __tablename__ = "transcript_paragraphs"
    __table_args__ = (
        UniqueConstraint(
            "slide_transcript_id", "position", name="uq_transcript_paragraph_position"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slide_transcript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("slide_transcripts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    original_text: Mapped[str | None] = mapped_column(Text)
    current_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TranscriptComplexTerm(Base):
    __tablename__ = "transcript_complex_terms"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slide_transcript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("slide_transcripts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    pronunciation_text: Mapped[str | None] = mapped_column(String(255))
    pronunciation_audio_key: Mapped[str | None] = mapped_column(String(512))


class SlideVocabularyUpgrade(Base):
    __tablename__ = "slide_vocabulary_upgrades"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slide_transcript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("slide_transcripts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    original_phrase: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_phrase: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class TranscriptRevision(Base):
    __tablename__ = "transcript_revisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slide_transcript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("slide_transcripts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    result_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    start_paragraph_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transcript_paragraphs.id"), nullable=False
    )
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_paragraph_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transcript_paragraphs.id"), nullable=False
    )
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    replacement_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UploadPracticeSession(TimestampedModel, Base):
    __tablename__ = "upload_practice_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="queued", server_default="queued", nullable=False
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    video_width: Mapped[int | None] = mapped_column(Integer)
    video_height: Mapped[int | None] = mapped_column(Integer)
    video_codec: Mapped[str | None] = mapped_column(String(64))
    transcript: Mapped[str | None] = mapped_column(Text)
    word_count: Mapped[int | None] = mapped_column(Integer)
    speech_duration_seconds: Mapped[float | None] = mapped_column(Float)
    words_per_minute: Mapped[float | None] = mapped_column(Float)
    filler_events: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    filler_clusters: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    pause_events: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    pace_samples: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    timed_transcript: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    speech_moments: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    pace_events: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    repetition_events: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    sensitive_term_flags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    pose_events: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    pose_tracking: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    processing_error_code: Mapped[str | None] = mapped_column(String(80))
    processing_error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(TimestampedModel, Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="queued", server_default="queued", nullable=False
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
