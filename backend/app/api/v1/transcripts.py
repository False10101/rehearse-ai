# ruff: noqa: E501

import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from difflib import SequenceMatcher
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.api.v1.presentations import authenticated_user, owned_presentation
from app.core.config import get_settings
from app.db.models import (
    Job,
    Presentation,
    PresentationTranscript,
    Slide,
    SlideTranscript,
    SlideVocabularyUpgrade,
    TranscriptComplexTerm,
    TranscriptParagraph,
    TranscriptRevision,
    TranscriptVersion,
)
from app.db.session import get_db_session, get_session_factory
from app.services.processing_diagnostics import log_processing_state
from app.services.provider_requests import ProviderRequestError
from app.services.transcript_enhancer import (
    TRANSCRIPT_MODEL,
    TRANSCRIPT_PROMPT_VERSION,
    analyze_script,
    enhance_selection,
    generate_script,
)

router = APIRouter(
    prefix="/api/v1/presentations/{presentation_id}/transcript",
    tags=["transcript"],
)
logger = logging.getLogger(__name__)

Tone = Literal["auto", "persuasive", "informative", "conversational"]
Style = Literal["natural", "formal"]
AudienceLevel = Literal["beginner", "general", "specialist"]


class ToneCheckResponse(BaseModel):
    classification: str | None = None
    confidence: float | None = None
    rationale: str | None = None


class ComplexTermResponse(BaseModel):
    term: str
    definition: str
    pronunciation: str | None = None


class VocabularyUpgradeResponse(BaseModel):
    original: str
    suggested: str
    reason: str


class ParagraphResponse(BaseModel):
    id: uuid.UUID
    position: int
    original: str | None
    current: str


class SlideTranscriptResponse(BaseModel):
    slide_number: int
    title: str | None
    image_url: str | None
    transcript_id: uuid.UUID | None = None
    revision: int | None = None
    mode: str | None = None
    requested_tone: str | None = None
    requested_style: str | None = None
    requested_audience_level: str | None = None
    requested_duration_seconds: int | None = None
    tone_matches_request: bool | None = None
    coaching_analysis_available: bool = False
    paragraphs: list[ParagraphResponse] = []
    complex_terms: list[ComplexTermResponse] = []
    tone_check: ToneCheckResponse | None = None
    vocabulary_upgrades: list[VocabularyUpgradeResponse] = []


class TranscriptResponse(BaseModel):
    preparation_progress: int | None = None
    preparation_status: str | None = None
    presentation_id: uuid.UUID
    filename: str
    status: str
    processing_error_code: str | None
    bulk_generation_status: str | None
    bulk_generation_progress: int | None
    bulk_generation_error_code: str | None = None
    slide_count: int | None
    slides: list[SlideTranscriptResponse]


class GenerateSlideRequest(BaseModel):
    slide_number: int = Field(ge=1)
    duration_seconds: Literal[45, 75, 105] = 75
    tone: Tone = "auto"
    style: Style = "natural"
    audience_level: AudienceLevel = "general"


class GenerateAllRequest(BaseModel):
    replace_existing: bool = False
    duration_seconds: Literal[45, 75, 105] = 75
    tone: Tone = "auto"
    style: Style = "natural"
    audience_level: AudienceLevel = "general"
    start_slide: int = Field(ge=1)
    end_slide: int = Field(ge=1)


class BulkGenerationResponse(BaseModel):
    job_id: uuid.UUID
    status: str


class CreateHumanDraftRequest(BaseModel):
    slide_number: int = Field(ge=1)


class SelectionPoint(BaseModel):
    paragraph_id: uuid.UUID
    offset: int = Field(ge=0)


class EnhanceSelectionRequest(BaseModel):
    slide_transcript_id: uuid.UUID
    base_revision: int = Field(ge=1)
    start: SelectionPoint
    end: SelectionPoint
    tone: Tone = "auto"
    style: Style = "natural"
    audience_level: AudienceLevel = "general"


class AcceptEnhancementRequest(EnhanceSelectionRequest):
    replacement_paragraphs: list[str] = Field(min_length=1)


class EnhancementPreviewResponse(BaseModel):
    slide_number: int
    base_revision: int
    before: list[str]
    after: list[str]
    changed: bool


class TranscriptHistoryResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    base_revision: int
    result_revision: int
    before: str | None
    after: str
    tone: str | None = None
    style: str | None = None
    audience_level: str | None = None


class TranscriptVersionResponse(BaseModel):
    id: uuid.UUID
    revision: int
    change_type: str
    created_at: datetime
    paragraphs: list[str]
    settings: dict
    is_current: bool
    legacy: bool = False
    restored_from_id: uuid.UUID | None = None


class RestoreVersionRequest(BaseModel):
    slide_transcript_id: uuid.UUID
    base_revision: int = Field(ge=1)


class SaveParagraph(BaseModel):
    id: uuid.UUID | None = None
    text: str


class SaveScriptRequest(BaseModel):
    slide_transcript_id: uuid.UUID
    base_revision: int = Field(ge=1)
    paragraphs: list[SaveParagraph] = Field(min_length=1)


def _slide_for_number(session: Session, presentation: Presentation, slide_number: int) -> Slide:
    slide = session.scalar(
        select(Slide).where(
            Slide.presentation_id == presentation.id,
            Slide.slide_number == slide_number,
        )
    )
    if slide is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slide not found.")
    return slide


def _paragraphs(session: Session, slide_transcript_id: uuid.UUID) -> list[TranscriptParagraph]:
    return list(
        session.scalars(
            select(TranscriptParagraph)
            .where(TranscriptParagraph.slide_transcript_id == slide_transcript_id)
            .order_by(TranscriptParagraph.position)
        )
    )


def _apply_analysis(session: Session, transcript: SlideTranscript, result: dict) -> None:
    tone = result.get("tone_check") if isinstance(result.get("tone_check"), dict) else {}
    transcript.tone_classification = str(tone.get("classification") or "") or None
    confidence = tone.get("confidence")
    transcript.tone_confidence = float(confidence) if isinstance(confidence, int | float) else None
    transcript.tone_rationale = str(tone.get("rationale") or "") or None

    session.execute(
        delete(TranscriptComplexTerm).where(
            TranscriptComplexTerm.slide_transcript_id == transcript.id
        )
    )
    session.execute(
        delete(SlideVocabularyUpgrade).where(
            SlideVocabularyUpgrade.slide_transcript_id == transcript.id
        )
    )
    for term in result.get("complex_terms", []):
        if isinstance(term, dict) and term.get("term") and term.get("definition"):
            session.add(
                TranscriptComplexTerm(
                    slide_transcript_id=transcript.id,
                    term=str(term["term"]),
                    definition=str(term["definition"]),
                    pronunciation_text=str(term.get("pronunciation") or "") or None,
                )
            )
    for upgrade in result.get("vocabulary_upgrades", []):
        if isinstance(upgrade, dict) and all(
            upgrade.get(key) for key in ("original", "suggested", "reason")
        ):
            session.add(
                SlideVocabularyUpgrade(
                    slide_transcript_id=transcript.id,
                    original_phrase=str(upgrade["original"]),
                    suggested_phrase=str(upgrade["suggested"]),
                    reason=str(upgrade["reason"]),
                )
            )


def _clear_analysis(session: Session, transcript: SlideTranscript) -> None:
    transcript.tone_classification = None
    transcript.tone_confidence = None
    transcript.tone_rationale = None
    session.execute(
        delete(TranscriptComplexTerm).where(
            TranscriptComplexTerm.slide_transcript_id == transcript.id
        )
    )
    session.execute(
        delete(SlideVocabularyUpgrade).where(
            SlideVocabularyUpgrade.slide_transcript_id == transcript.id
        )
    )


def _response_for_slide(
    session: Session,
    slide: Slide,
    transcript: SlideTranscript | None,
    mode: str | None,
    presentation: Presentation,
) -> SlideTranscriptResponse:
    image_url = (
        f"/api/v1/presentations/{presentation.id}/slides/{slide.slide_number}/image"
        if slide.image_storage_key
        else None
    )
    if transcript is None:
        return SlideTranscriptResponse(
            slide_number=slide.slide_number,
            title=slide.title,
            image_url=image_url,
        )
    paragraphs = [
        ParagraphResponse(
            id=item.id,
            position=item.position,
            original=item.original_text,
            current=item.current_text,
        )
        for item in _paragraphs(session, transcript.id)
    ]
    terms = list(
        session.scalars(
            select(TranscriptComplexTerm)
            .where(TranscriptComplexTerm.slide_transcript_id == transcript.id)
            .order_by(TranscriptComplexTerm.term)
        )
    )
    upgrades = list(
        session.scalars(
            select(SlideVocabularyUpgrade)
            .where(SlideVocabularyUpgrade.slide_transcript_id == transcript.id)
            .order_by(SlideVocabularyUpgrade.id)
        )
    )
    latest_revision = session.scalar(
        select(TranscriptRevision)
        .where(TranscriptRevision.slide_transcript_id == transcript.id)
        .order_by(TranscriptRevision.created_at.desc(), TranscriptRevision.result_revision.desc())
        .limit(1)
    )
    latest_revision_source = latest_revision.source if latest_revision else None
    # Opening the editor must not expose old AI self-review suggestions.
    vocabulary_changes = []
    if latest_revision_source == "human-edit":
        try:
            saved_edit = json.loads(latest_revision.replacement_text)
        except (ValueError, TypeError):
            saved_edit = None
        if isinstance(saved_edit, dict) and saved_edit.get("format") == "human-edit-v2":
            vocabulary_changes = saved_edit.get("human_changes", [])
    if not vocabulary_changes:
        upgrades = []
    current_mode = (
        "human-enhance" if latest_revision_source in {"human-enhance", "human-edit"} else mode
    )
    parent = session.get(PresentationTranscript, transcript.presentation_transcript_id)
    requested_tone = parent.target_tone if parent and current_mode == "ai-gen" else None
    requested_style = parent.target_style if parent and current_mode == "ai-gen" else None
    requested_duration = (
        parent.target_duration_seconds if parent and current_mode == "ai-gen" else None
    )
    detected_tone = (
        transcript.tone_classification.casefold() if transcript.tone_classification else None
    )
    tone_matches_request = (
        detected_tone == requested_tone.casefold()
        if requested_tone not in {None, "auto"} and detected_tone is not None
        else None
    )
    return SlideTranscriptResponse(
        slide_number=slide.slide_number,
        title=slide.title,
        image_url=image_url,
        transcript_id=transcript.id,
        revision=transcript.revision,
        mode=current_mode,
        requested_tone=requested_tone,
        requested_style=requested_style,
        requested_audience_level=(parent.target_audience_level or "general") if parent else None,
        requested_duration_seconds=requested_duration,
        tone_matches_request=tone_matches_request,
        coaching_analysis_available=transcript.tone_classification is not None,
        paragraphs=paragraphs,
        complex_terms=[
            ComplexTermResponse(
                term=item.term,
                definition=item.definition,
                pronunciation=item.pronunciation_text,
            )
            for item in terms
        ],
        tone_check=ToneCheckResponse(
            classification=transcript.tone_classification,
            confidence=transcript.tone_confidence,
            rationale=transcript.tone_rationale,
        ),
        vocabulary_upgrades=[
            VocabularyUpgradeResponse(
                original=item.original_phrase,
                suggested=item.suggested_phrase,
                reason=item.reason,
            )
            for item in upgrades
        ],
    )


def _latest_by_slide(
    session: Session, presentation_id: uuid.UUID
) -> tuple[dict[uuid.UUID, SlideTranscript], dict[uuid.UUID, str]]:
    rows = session.execute(
        select(SlideTranscript, PresentationTranscript.mode)
        .join(PresentationTranscript)
        .where(PresentationTranscript.presentation_id == presentation_id)
        .order_by(SlideTranscript.revision.desc(), SlideTranscript.updated_at.desc())
        .execution_options(populate_existing=True)
    ).all()
    transcripts: dict[uuid.UUID, SlideTranscript] = {}
    modes: dict[uuid.UUID, str] = {}
    for transcript, mode in rows:
        if transcript.slide_id not in transcripts:
            transcripts[transcript.slide_id] = transcript
            modes[transcript.slide_id] = mode
    return transcripts, modes


def _response(session: Session, presentation: Presentation) -> TranscriptResponse:
    slides = list(
        session.scalars(
            select(Slide)
            .where(Slide.presentation_id == presentation.id)
            .order_by(Slide.slide_number)
        )
    )
    latest, modes = _latest_by_slide(session, presentation.id)
    preparation_job = session.scalar(
        select(Job)
        .where(
            Job.target_id == presentation.id,
            Job.job_type.in_(["transcript_prepare", "slide_analysis"]),
        )
        .order_by(Job.created_at.desc())
    )
    bulk_job = session.scalar(
        select(Job)
        .where(Job.target_id == presentation.id, Job.job_type == "transcript_generate_all")
        .order_by(Job.created_at.desc())
    )
    log_processing_state(presentation, preparation_job, event="transcript_preparation_response")
    if bulk_job is not None:
        log_processing_state(presentation, bulk_job, event="transcript_bulk_status_response")
    return TranscriptResponse(
        presentation_id=presentation.id,
        preparation_progress=preparation_job.progress_percent if preparation_job else None,
        preparation_status=preparation_job.status if preparation_job else None,
        filename=presentation.original_filename,
        status=presentation.status,
        processing_error_code=presentation.processing_error_code,
        bulk_generation_status=bulk_job.status if bulk_job else None,
        bulk_generation_progress=bulk_job.progress_percent if bulk_job else None,
        bulk_generation_error_code=bulk_job.error_code if bulk_job else None,
        slide_count=presentation.slide_count,
        slides=[
            _response_for_slide(
                session, slide, latest.get(slide.id), modes.get(slide.id), presentation
            )
            for slide in slides
        ],
    )


@router.get("/export")
def export_transcript(
    presentation_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
):
    presentation = owned_presentation(session, user.id, presentation_id)
    latest, _ = _latest_by_slide(session, presentation_id)
    slides = session.scalars(
        select(Slide).where(Slide.presentation_id == presentation_id).order_by(Slide.slide_number)
    ).all()
    parts = [presentation.original_filename, ""]
    has_content = False
    for slide in slides:
        transcript = latest.get(slide.id)
        paragraphs = _paragraphs(session, transcript.id) if transcript else []
        text = "\n\n".join(p.current_text for p in paragraphs)
        has_content = has_content or bool(text.strip())
        parts.extend([f"Slide {slide.slide_number}: {slide.title or ''}", text, ""])
    if not has_content:
        raise HTTPException(status_code=409, detail="Save or generate a script before exporting.")
    return Response(
        "\n\n".join(parts),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="presentation-script.txt"',
            "Cache-Control": "private, no-store",
        },
    )


def _version_snapshot(session: Session, transcript: SlideTranscript) -> dict:
    parent = session.get(PresentationTranscript, transcript.presentation_transcript_id)
    response = _response_for_slide(
        session, session.get(Slide, transcript.slide_id), transcript, parent.mode,
        session.get(Presentation, parent.presentation_id),
    )
    return {
        "paragraphs": [p.current for p in response.paragraphs],
        "mode": response.mode,
        "settings": {
            "tone": parent.target_tone, "style": parent.target_style,
            "audience_level": parent.target_audience_level,
            "duration_seconds": parent.target_duration_seconds,
            "model_id": parent.model_id, "prompt_version": parent.prompt_version,
        },
        "complex_terms": [term.model_dump() for term in response.complex_terms],
        "tone_check": response.tone_check.model_dump() if response.tone_check else {},
    }


def _version_id(transcript: SlideTranscript) -> uuid.UUID:
    # Stable even when an older script is first listed before its baseline is
    # persisted. A cached history entry must never point at later edited text.
    return uuid.uuid5(uuid.NAMESPACE_URL, f"rehearse:transcript:{transcript.id}:{transcript.revision}")


def _record_version(
    session: Session, transcript: SlideTranscript, change_type: str,
    *, settings: dict | None = None, restored_from_id: uuid.UUID | None = None,
) -> TranscriptVersion:
    # Flush paragraphs, feedback and edit provenance before taking the snapshot.
    # Old fragment revisions remain intact but are never used to reconstruct text.
    session.flush()
    existing = session.scalar(select(TranscriptVersion).where(
        TranscriptVersion.slide_transcript_id == transcript.id,
        TranscriptVersion.revision == transcript.revision,
    ))
    if existing:
        return existing
    snapshot = _version_snapshot(session, transcript)
    if settings is not None:
        snapshot["settings"] = settings
    version = TranscriptVersion(
        id=_version_id(transcript), slide_transcript_id=transcript.id, revision=transcript.revision,
        change_type=change_type, snapshot=json.dumps(snapshot, ensure_ascii=False),
        restored_from_id=restored_from_id,
        **({"created_at": transcript.updated_at} if change_type == "saved" else {}),
    )
    session.add(version)
    session.flush()
    return version


def _lock_slide(session: Session, slide: Slide) -> None:
    # All script writers use the same slide lock, including new generation rows.
    # A transcript-only lock cannot protect against a simultaneous regeneration.
    session.refresh(slide, with_for_update=True)


def _require_current_transcript(
    session: Session,
    presentation: Presentation,
    slide: Slide,
    transcript_id: uuid.UUID,
    base_revision: int,
) -> SlideTranscript:
    transcript = session.get(SlideTranscript, transcript_id, populate_existing=True)
    if transcript is None or transcript.slide_id != slide.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found.")
    parent = session.get(PresentationTranscript, transcript.presentation_transcript_id)
    if parent is None or parent.presentation_id != presentation.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found.")
    latest, _ = _latest_by_slide(session, presentation.id)
    if latest.get(slide.id) is None or latest[slide.id].id != transcript.id:
        raise HTTPException(
            status_code=409, detail="A newer script exists. Reload it before applying this change."
        )
    if transcript.revision != base_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This script changed elsewhere. Reload it before editing again.",
        )
    return transcript


def _neighboring_script_context(
    session: Session, presentation: Presentation, current_slide: Slide,
) -> list[dict]:
    """Nearest written script on each side, for continuity rather than evidence.

    Single-slide generation sees the latest human edits. Parallel bulk requests
    use a snapshot of saved scripts instead of depending on in-flight results.
    """
    latest, _ = _latest_by_slide(session, presentation.id)
    slides = list(session.scalars(
        select(Slide).where(Slide.presentation_id == presentation.id).order_by(Slide.slide_number)
    ))
    contexts = []
    before = [slide for slide in slides if slide.slide_number < current_slide.slide_number]
    after = [slide for slide in slides if slide.slide_number > current_slide.slide_number]
    for candidates in (reversed(before), iter(after)):
        for slide in candidates:
            script = latest.get(slide.id)
            if script is None:
                continue
            parts = [p.current_text for p in _paragraphs(session, script.id) if p.current_text.strip()]
            if not parts:
                continue
            contexts.append({
                "slide_number": slide.slide_number,
                "title": slide.title,
                "script": "\n\n".join(parts)[:6000],
            })
            break
    return contexts


def _create_ai_slide_transcript(
    session: Session,
    presentation: Presentation,
    slide: Slide,
    duration_seconds: int,
    tone: Tone,
    style: Style,
    previous_slide: Slide | None = None,
    next_slide: Slide | None = None,
    deck_slides: list[Slide] | None = None,
    audience_level: AudienceLevel = "general",
) -> SlideTranscript:
    result = generate_script(
        slide.extracted_content,
        duration_seconds,
        tone,
        style,
        previous_slide.extracted_content if previous_slide else None,
        next_slide.extracted_content if next_slide else None,
        [item.extracted_content for item in deck_slides] if deck_slides else None,
        audience_level=audience_level,
        neighboring_scripts=_neighboring_script_context(session, presentation, slide),
    )
    return _save_ai_slide_transcript(
        session, presentation, slide, result, duration_seconds, tone, style, audience_level
    )


def _save_ai_slide_transcript(
    session: Session,
    presentation: Presentation,
    slide: Slide,
    result: dict,
    duration_seconds: int,
    tone: Tone,
    style: Style,
    audience_level: AudienceLevel,
) -> SlideTranscript:
    _lock_slide(session, slide)
    latest, _ = _latest_by_slide(session, presentation.id)
    prior = latest.get(slide.id)
    if prior:
        _record_version(session, prior, "saved")
    parent = PresentationTranscript(
        presentation_id=presentation.id,
        mode="ai-gen",
        target_tone=tone,
        target_style=style,
        target_audience_level=audience_level,
        target_duration_seconds=duration_seconds,
        model_id=TRANSCRIPT_MODEL,
        prompt_version=TRANSCRIPT_PROMPT_VERSION,
        status="completed",
    )
    session.add(parent)
    session.flush()
    latest, _ = _latest_by_slide(session, presentation.id)
    prior = latest.get(slide.id)
    transcript = SlideTranscript(
        presentation_transcript_id=parent.id,
        slide_id=slide.id,
        revision=(prior.revision + 1) if prior else 1,
    )
    session.add(transcript)
    session.flush()
    for position, paragraph in enumerate(result["paragraphs"], 1):
        session.add(
            TranscriptParagraph(
                slide_transcript_id=transcript.id,
                position=position,
                original_text=None,
                current_text=paragraph,
            )
        )
    _apply_analysis(session, transcript, {**result, "vocabulary_upgrades": []})
    _record_version(session, transcript, "generated")
    return transcript


def _create_human_draft(
    session: Session,
    presentation: Presentation,
    slide: Slide,
) -> SlideTranscript:
    _lock_slide(session, slide)
    latest, _ = _latest_by_slide(session, presentation.id)
    if slide.id in latest:
        return latest[slide.id]
    parent = PresentationTranscript(
        presentation_id=presentation.id,
        mode="human-write",
        model_id="human-authored",
        prompt_version="human-write-v1",
        status="completed",
    )
    session.add(parent)
    session.flush()
    latest, _ = _latest_by_slide(session, presentation.id)
    prior = latest.get(slide.id)
    transcript = SlideTranscript(
        presentation_transcript_id=parent.id,
        slide_id=slide.id,
        revision=(prior.revision + 1) if prior else 1,
    )
    session.add(transcript)
    session.flush()
    session.add(
        TranscriptParagraph(
            slide_transcript_id=transcript.id,
            position=1,
            original_text=None,
            current_text="",
        )
    )
    return transcript


def run_generate_all_transcripts(
    presentation_id: uuid.UUID,
    duration_seconds: int,
    tone: Tone,
    style: Style,
    start_slide: int,
    end_slide: int,
    audience_level: AudienceLevel = "general",
    replace_existing: bool = False,
) -> None:
    session = get_session_factory()()
    try:
        presentation = session.get(Presentation, presentation_id)
        if presentation is None:
            return
        job = session.scalar(
            select(Job)
            .where(
                Job.target_id == presentation.id,
                Job.job_type == "transcript_generate_all",
            )
            .order_by(Job.created_at.desc())
        )
        if job is None:
            return
        deck_slides = list(
            session.scalars(
                select(Slide)
                .where(Slide.presentation_id == presentation.id)
                .order_by(Slide.slide_number)
            )
        )
        slides = [slide for slide in deck_slides if start_slide <= slide.slide_number <= end_slide]
        deck_index_by_id = {slide.id: index for index, slide in enumerate(deck_slides)}
        job.status = "running"
        job.progress_percent = 0
        job.started_at = datetime.now().astimezone()
        session.commit()
        latest, _ = _latest_by_slide(session, presentation.id)
        # Snapshot source data and saved continuity on this thread. Workers only
        # call the provider; SQLAlchemy sessions and ORM objects stay here.
        saved_scripts = []
        written_slide_ids = set()
        starting_revisions = {
            slide_id: (script.id, script.revision) for slide_id, script in latest.items()
        }
        for slide in deck_slides:
            existing = latest.get(slide.id)
            parts = (
                [
                    p.current_text
                    for p in _paragraphs(session, existing.id)
                    if p.current_text.strip()
                ]
                if existing
                else []
            )
            if parts:
                written_slide_ids.add(slide.id)
                saved_scripts.append(
                    {
                        "slide_number": slide.slide_number,
                        "title": slide.title,
                        "script": "\n\n".join(parts)[:6000],
                    }
                )
        deck_context = [slide.extracted_content for slide in deck_slides]
        tasks = []
        for slide in slides:
            if slide.id in written_slide_ids and not replace_existing:
                continue
            deck_index = deck_index_by_id[slide.id]
            before = [item for item in saved_scripts if item["slide_number"] < slide.slide_number]
            after = [item for item in saved_scripts if item["slide_number"] > slide.slide_number]
            tasks.append(
                (
                    slide.id,
                    {
                        "slide": slide.extracted_content,
                        "duration_seconds": duration_seconds,
                        "tone": tone,
                        "style": style,
                        "audience_level": audience_level,
                        "previous_slide": deck_context[deck_index - 1] if deck_index > 0 else None,
                        "next_slide": deck_context[deck_index + 1]
                        if deck_index + 1 < len(deck_context)
                        else None,
                        "deck_slides": deck_context,
                        "neighboring_scripts": before[-1:] + after[:1],
                    },
                )
            )
        completed = len(slides) - len(tasks)
        job.progress_percent = round(completed / len(slides) * 100) if slides else 100
        session.commit()  # Release the DB connection while waiting for provider results.
        first_error = None
        if tasks:
            workers = max(1, min(get_settings().transcript_generation_workers, len(tasks)))
            logger.info(
                "Bulk transcript generation presentation=%s pending=%s skipped=%s workers=%s",
                presentation_id,
                len(tasks),
                completed,
                workers,
            )
            with ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="transcript-gen"
            ) as pool:
                futures = {
                    pool.submit(generate_script, **payload): slide_id for slide_id, payload in tasks
                }
                for future in as_completed(futures):
                    slide_id = futures[future]
                    try:
                        result = future.result()
                        # Content may have been written while this request ran.
                        # Recheck before saving so a late result does not replace it.
                        session.expire_all()
                        slide = session.get(Slide, slide_id)
                        _lock_slide(session, slide)
                        current, _ = _latest_by_slide(session, presentation_id)
                        existing = current.get(slide_id)
                        has_content = existing is not None and any(
                            p.current_text.strip() for p in _paragraphs(session, existing.id)
                        )
                        current_revision = (existing.id, existing.revision) if existing else None
                        # Explicit replacement covers scripts present when the job
                        # began, never a newer edit saved while AI was writing.
                        unchanged = current_revision == starting_revisions.get(slide_id)
                        if (replace_existing and unchanged) or (not replace_existing and not has_content):
                            with session.begin_nested():
                                slide = session.get(Slide, slide_id)
                                _save_ai_slide_transcript(
                                    session,
                                    presentation,
                                    slide,
                                    result,
                                    duration_seconds,
                                    tone,
                                    style,
                                    audience_level,
                                )
                        job.progress_percent = round((completed + 1) / len(slides) * 100)
                        session.commit()
                        completed += 1
                    except Exception as error:
                        session.rollback()
                        logger.exception(
                            "Bulk transcript generation failed presentation=%s slide_id=%s",
                            presentation_id,
                            slide_id,
                        )
                        if first_error is None:
                            first_error = error
                        # Other requests may already have produced useful scripts.
                        # Save their results too; the batch is marked failed afterward.
            if first_error is not None:
                raise first_error
        job.status = "completed"
        job.progress_percent = 100
        job.completed_at = datetime.now().astimezone()
        session.commit()
    except Exception as error:
        logger.exception(
            "All-slide transcript generation failed for presentation %s",
            presentation_id,
        )
        session.rollback()
        job = session.scalar(
            select(Job)
            .where(
                Job.target_id == presentation_id,
                Job.job_type == "transcript_generate_all",
            )
            .order_by(Job.created_at.desc())
        )
        if job:
            job.status = "failed"
            job.error_code = getattr(error, "error_code", type(error).__name__)[:80]
            job.error_message = str(error)[:1000]
            job.completed_at = datetime.now().astimezone()
            session.commit()
    finally:
        session.close()


@router.get("", response_model=TranscriptResponse)
def get_transcript(
    presentation_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> TranscriptResponse:
    presentation = owned_presentation(session, user.id, presentation_id)
    return _response(session, presentation)


@router.post("/generate", response_model=SlideTranscriptResponse)
def generate_slide_transcript(
    presentation_id: uuid.UUID,
    request: GenerateSlideRequest,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> SlideTranscriptResponse:
    presentation = owned_presentation(session, user.id, presentation_id)
    slide = _slide_for_number(session, presentation, request.slide_number)
    slides = list(
        session.scalars(
            select(Slide)
            .where(Slide.presentation_id == presentation.id)
            .order_by(Slide.slide_number)
        )
    )
    slide_index = slides.index(slide)
    try:
        transcript = _create_ai_slide_transcript(
            session,
            presentation,
            slide,
            request.duration_seconds,
            request.tone,
            request.style,
            slides[slide_index - 1] if slide_index else None,
            slides[slide_index + 1] if slide_index + 1 < len(slides) else None,
            slides,
            audience_level=request.audience_level,
        )
    except Exception as error:
        logger.exception(
            "Transcript generation failed for presentation %s slide %s",
            presentation.id,
            slide.slide_number,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error) if isinstance(error, ProviderRequestError)
            else "Script generation could not finish. Please retry.",
        ) from error

    session.commit()
    return _response_for_slide(session, slide, transcript, "ai-gen", presentation)


@router.post(
    "/generate-all", response_model=BulkGenerationResponse, status_code=status.HTTP_202_ACCEPTED
)
def generate_all_slide_transcripts(
    presentation_id: uuid.UUID,
    request: GenerateAllRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> BulkGenerationResponse:
    presentation = owned_presentation(session, user.id, presentation_id)
    if presentation.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wait for the presentation to finish preparing first.",
        )
    slides_exist = session.scalar(
        select(Slide.id).where(Slide.presentation_id == presentation.id).limit(1)
    )
    if slides_exist is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No slides are ready yet.")
    slide_numbers = set(
        session.scalars(select(Slide.slide_number).where(Slide.presentation_id == presentation.id))
    )
    if (
        request.start_slide > request.end_slide
        or request.start_slide not in slide_numbers
        or request.end_slide not in slide_numbers
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Choose a valid starting and ending slide.",
        )
    active_job = session.scalar(
        select(Job).where(
            Job.target_id == presentation.id,
            Job.job_type == "transcript_generate_all",
            Job.status.in_(["queued", "running"]),
        )
    )
    if active_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="All-slide generation is already running.",
        )
    job = Job(
        user_id=user.id,
        job_type="transcript_generate_all",
        target_type="presentation",
        target_id=presentation.id,
        status="queued",
    )
    session.add(job)
    session.commit()
    from app.services.background_jobs import run_background_job
    background_tasks.add_task(
        run_background_job,
        job.id,
        run_generate_all_transcripts,
        presentation.id,
        request.duration_seconds,
        request.tone,
        request.style,
        request.start_slide,
        request.end_slide,
        request.audience_level,
        request.replace_existing,
    )
    return BulkGenerationResponse(job_id=job.id, status=job.status)


@router.post("/human", response_model=SlideTranscriptResponse)
def create_human_draft(
    presentation_id: uuid.UUID,
    request: CreateHumanDraftRequest,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> SlideTranscriptResponse:
    presentation = owned_presentation(session, user.id, presentation_id)
    slide = _slide_for_number(session, presentation, request.slide_number)
    transcript = _create_human_draft(session, presentation, slide)
    session.commit()
    return _response_for_slide(session, slide, transcript, "human-write", presentation)


@router.post("/enhance", response_model=SlideTranscriptResponse)
def enhance_transcript_selection(
    presentation_id: uuid.UUID,
    request: EnhanceSelectionRequest,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> SlideTranscriptResponse:
    return _enhance_transcript_selection(presentation_id, request, session, user)


@router.post("/enhance/preview", response_model=EnhancementPreviewResponse)
def preview_transcript_selection(
    presentation_id: uuid.UUID,
    request: EnhanceSelectionRequest,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
):
    return _enhance_transcript_selection(presentation_id, request, session, user, preview=True)


@router.post("/enhance/accept", response_model=SlideTranscriptResponse)
def accept_transcript_selection(
    presentation_id: uuid.UUID,
    request: AcceptEnhancementRequest,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
):
    # Accept exactly the reviewed wording; never call the model again here.
    return _enhance_transcript_selection(
        presentation_id, request, session, user,
        replacements_override=request.replacement_paragraphs,
    )


def _enhance_transcript_selection(
    presentation_id, request, session, user, *, preview=False, replacements_override=None,
):
    presentation = owned_presentation(session, user.id, presentation_id)
    transcript = session.get(SlideTranscript, request.slide_transcript_id)
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found.")
    slide = session.get(Slide, transcript.slide_id)
    if slide is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slide not found.")
    transcript = _require_current_transcript(
        session, presentation, slide, request.slide_transcript_id, request.base_revision
    )
    paragraphs = _paragraphs(session, transcript.id)
    by_id = {item.id: item for item in paragraphs}
    start = by_id.get(request.start.paragraph_id)
    end = by_id.get(request.end.paragraph_id)
    if start is None or end is None or start.position > end.position:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid selection."
        )
    if request.start.offset > len(start.current_text) or request.end.offset > len(end.current_text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid selection offsets."
        )
    if start.id == end.id and request.start.offset >= request.end.offset:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select some text first."
        )

    selected_paragraphs = [
        item for item in paragraphs if start.position <= item.position <= end.position
    ]
    if start.id == end.id:
        selected_parts = [start.current_text[request.start.offset : request.end.offset]]
    else:
        selected_parts = [start.current_text[request.start.offset :]]
        selected_parts.extend(
            item.current_text
            for item in paragraphs
            if start.position < item.position < end.position
        )
        selected_parts.append(end.current_text[: request.end.offset])
    if any(not part.strip() for part in selected_parts):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The selection includes an empty paragraph. Select text within written paragraphs.",
        )
    try:
        replacements = replacements_override if replacements_override is not None else enhance_selection(
            slide.extracted_content, selected_parts, request.tone, request.style,
            audience_level=request.audience_level,
            selection_boundaries={
                "first_part_starts_paragraph": request.start.offset == 0,
                "last_part_ends_paragraph": request.end.offset == len(end.current_text),
            },
            surrounding_text={
                "before": "\n\n".join(
                    [p.current_text for p in paragraphs if p.position < start.position]
                    + [start.current_text[:request.start.offset]]
                )[-6000:],
                "after": "\n\n".join(
                    [end.current_text[request.end.offset:]]
                    + [p.current_text for p in paragraphs if p.position > end.position]
                )[:6000],
            },
        )
    except Exception as error:
        logger.exception(
            "Selected-text enhancement failed for presentation %s slide %s",
            presentation.id,
            slide.slide_number,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error) if isinstance(error, ProviderRequestError)
            else "Text enhancement could not finish. Please retry.",
        ) from error

    if len(replacements) != len(selected_parts) or any(not part.strip() for part in replacements):
        raise HTTPException(status_code=422, detail="The replacement must preserve the selected paragraphs.")
    if preview:
        return EnhancementPreviewResponse(
            slide_number=slide.slide_number, base_revision=transcript.revision,
            before=selected_parts, after=replacements, changed=selected_parts != replacements,
        )
    # Lock only when writing, after the potentially slow provider call. Refresh
    # catches another tab saving while this request was waiting for the model.
    _lock_slide(session, slide)
    session.refresh(transcript, with_for_update=True)
    _require_current_transcript(
        session, presentation, slide, request.slide_transcript_id, request.base_revision
    )
    if transcript.revision != request.base_revision:
        raise HTTPException(status_code=409, detail="This script changed. Reload it and review a new suggestion.")
    session.refresh(start)
    if end.id != start.id:
        session.refresh(end)

    _record_version(session, transcript, "saved")
    start_prefix = start.current_text[: request.start.offset]
    end_suffix = end.current_text[request.end.offset :]
    for item in selected_paragraphs:
        if item.original_text is None:
            item.original_text = item.current_text
    if start.id == end.id:
        start.current_text = start_prefix + replacements[0] + end_suffix
    else:
        start.current_text = start_prefix + replacements[0]
        for item, replacement in zip(selected_paragraphs[1:-1], replacements[1:-1]):
            item.current_text = replacement
        end.current_text = replacements[-1] + end_suffix
    transcript.revision += 1
    session.flush()
    updated_paragraphs = [
        item.current_text for item in _paragraphs(session, transcript.id) if item.current_text
    ]
    try:
        analysis = analyze_script(updated_paragraphs)
    except Exception:
        logger.exception(
            "Coaching analysis failed after text enhancement for presentation %s slide %s",
            presentation.id,
            slide.slide_number,
        )
        _clear_analysis(session, transcript)
    else:
        _apply_analysis(session, transcript, {**analysis, "vocabulary_upgrades": []})
    session.add(
        TranscriptRevision(
            slide_transcript_id=transcript.id,
            base_revision=request.base_revision,
            result_revision=transcript.revision,
            start_paragraph_id=start.id,
            start_offset=request.start.offset,
            end_paragraph_id=end.id,
            end_offset=request.end.offset,
            replacement_text=json.dumps({
                "format": "enhancement-review-v1",
                "before": "\n\n".join(selected_parts),
                "after": "\n\n".join(replacements),
                "tone": request.tone, "style": request.style,
                "audience_level": request.audience_level,
            }, ensure_ascii=False),
            source="human-enhance",
        )
    )
    session.flush()
    settings = _version_snapshot(session, transcript)["settings"]
    settings.update(tone=request.tone, style=request.style, audience_level=request.audience_level)
    _record_version(session, transcript, "enhanced", settings=settings)
    session.commit()
    return _response_for_slide(session, slide, transcript, "human-enhance", presentation)


def _changed_words(before: str, after: str) -> list[str]:
    """New/replaced word spans only; surrounding AI text is not human authorship."""
    old_words = list(re.finditer(r"\S+", before))
    new_words = list(re.finditer(r"\S+", after))
    changes = []
    for operation, _, _, start, end in SequenceMatcher(
        None, [word.group() for word in old_words],
        [word.group() for word in new_words], autojunk=False,
    ).get_opcodes():
        if operation in {"insert", "replace"} and start < end:
            text = after[new_words[start].start():new_words[end - 1].end()]
            if re.search(r"\w", text):
                changes.append(text)
    return changes


@router.patch("/slides/{slide_number}", response_model=SlideTranscriptResponse)
def save_transcript_script(
    presentation_id: uuid.UUID,
    slide_number: int,
    request: SaveScriptRequest,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> SlideTranscriptResponse:
    presentation = owned_presentation(session, user.id, presentation_id)
    slide = _slide_for_number(session, presentation, slide_number)
    _lock_slide(session, slide)
    transcript = _require_current_transcript(
        session, presentation, slide, request.slide_transcript_id, request.base_revision
    )
    paragraphs = _paragraphs(session, transcript.id)
    by_id = {item.id: item for item in paragraphs}
    before_text = {item.id: item.current_text for item in paragraphs}
    submitted_ids = [item.id for item in request.paragraphs if item.id is not None]
    if len(submitted_ids) != len(set(submitted_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A paragraph was submitted more than once. Reload the script and try again.",
        )
    if any(item_id not in by_id for item_id in submitted_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown paragraph."
        )

    _record_version(session, transcript, "saved")
    retained_ids = set(submitted_ids)
    removed_ids = [paragraph.id for paragraph in paragraphs if paragraph.id not in retained_ids]
    for paragraph in paragraphs:
        paragraph.position = -(100_000 + paragraph.position)
    session.flush()

    saved_paragraphs: list[TranscriptParagraph] = []
    vocabulary_changes: list[str] = []
    for position, update in enumerate(request.paragraphs, 1):
        vocabulary_changes.extend(_changed_words(before_text.get(update.id, ""), update.text.strip()))
        paragraph = by_id.get(update.id) if update.id is not None else None
        if paragraph is None:
            paragraph = TranscriptParagraph(
                slide_transcript_id=transcript.id,
                position=-(200_000 + position),
                original_text=None,
                current_text=update.text.strip(),
            )
            session.add(paragraph)
        else:
            if paragraph.original_text is None:
                paragraph.original_text = paragraph.current_text
            paragraph.current_text = update.text.strip()
        saved_paragraphs.append(paragraph)
    session.flush()

    for position, paragraph in enumerate(saved_paragraphs, 1):
        paragraph.position = position
    session.flush()

    first = saved_paragraphs[0]
    last = saved_paragraphs[-1]
    if removed_ids:
        # History contains its own before/after text. Re-anchor its foreign keys
        # before deleting paragraphs so removing text cannot erase the history.
        revisions = session.scalars(select(TranscriptRevision).where(
            or_(TranscriptRevision.start_paragraph_id.in_(removed_ids),
                TranscriptRevision.end_paragraph_id.in_(removed_ids))
        ))
        for revision in revisions:
            if revision.start_paragraph_id in removed_ids:
                revision.start_paragraph_id = first.id
            if revision.end_paragraph_id in removed_ids:
                revision.end_paragraph_id = first.id
        session.flush()
        for paragraph in paragraphs:
            if paragraph.id in removed_ids:
                session.delete(paragraph)
        session.flush()
    transcript.revision += 1
    session.flush()
    current = [item.current_text for item in saved_paragraphs if item.current_text]
    if not current:
        _clear_analysis(session, transcript)
    else:
        try:
            analysis = analyze_script(current, vocabulary_text=vocabulary_changes)
        except Exception:
            logger.exception(
                "Coaching analysis failed after manual edit for presentation %s slide %s",
                presentation.id,
                slide.slide_number,
            )
            _clear_analysis(session, transcript)
        else:
            _apply_analysis(session, transcript, analysis)
    session.add(
        TranscriptRevision(
            slide_transcript_id=transcript.id,
            base_revision=request.base_revision,
            result_revision=transcript.revision,
            start_paragraph_id=first.id,
            start_offset=0,
            end_paragraph_id=last.id,
            end_offset=len(last.current_text),
            replacement_text=json.dumps({
                "format": "human-edit-v2",
                "text": "\n\n".join(item.text.strip() for item in request.paragraphs),
                "human_changes": vocabulary_changes,
            }, ensure_ascii=False),
            source="human-edit",
        )
    )
    _record_version(session, transcript, "edited")
    session.commit()
    return _response_for_slide(session, slide, transcript, "human-enhance", presentation)


@router.get("/slides/{slide_number}/history", response_model=list[TranscriptHistoryResponse])
def transcript_selection_history(
    presentation_id: uuid.UUID,
    slide_number: int,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
):
    presentation = owned_presentation(session, user.id, presentation_id)
    slide = _slide_for_number(session, presentation, slide_number)
    rows = session.scalars(
        select(TranscriptRevision).join(SlideTranscript,
            SlideTranscript.id == TranscriptRevision.slide_transcript_id)
        .where(SlideTranscript.slide_id == slide.id, TranscriptRevision.source == "human-enhance")
        .order_by(TranscriptRevision.created_at.desc(), TranscriptRevision.result_revision.desc())
    )
    history = []
    for row in rows:
        try:
            detail = json.loads(row.replacement_text)
        except (ValueError, TypeError):
            detail = None
        if not isinstance(detail, dict) or detail.get("format") != "enhancement-review-v1":
            detail = {"before": None, "after": row.replacement_text}
        history.append(TranscriptHistoryResponse(
            id=row.id, created_at=row.created_at, base_revision=row.base_revision,
            result_revision=row.result_revision, before=detail.get("before"),
            after=detail["after"], tone=detail.get("tone"), style=detail.get("style"),
            audience_level=detail.get("audience_level"),
        ))
    return history


@router.get("/slides/{slide_number}/versions", response_model=list[TranscriptVersionResponse])
def transcript_versions(
    presentation_id: uuid.UUID, slide_number: int,
    session: Session = Depends(get_db_session), user=Depends(authenticated_user),
):
    presentation = owned_presentation(session, user.id, presentation_id)
    slide = _slide_for_number(session, presentation, slide_number)
    latest, _ = _latest_by_slide(session, presentation.id)
    current = latest.get(slide.id)
    transcripts = list(session.scalars(select(SlideTranscript).where(SlideTranscript.slide_id == slide.id)))
    rows = list(session.scalars(select(TranscriptVersion).join(SlideTranscript).where(
        SlideTranscript.slide_id == slide.id,
    ).order_by(TranscriptVersion.revision.desc(), TranscriptVersion.created_at.desc())))
    entries = []
    covered = set()
    for row in rows:
        snapshot = json.loads(row.snapshot)
        covered.add((row.slide_transcript_id, row.revision))
        entries.append(TranscriptVersionResponse(
            id=row.id, revision=row.revision, change_type=row.change_type,
            created_at=row.created_at, paragraphs=snapshot["paragraphs"],
            settings=snapshot["settings"], restored_from_id=row.restored_from_id,
            is_current=bool(current and current.id == row.slide_transcript_id and current.revision == row.revision),
        ))
    # Pre-feature generation rows retain their last saved full text, not every
    # historical edit. Expose exactly that, labelled honestly, without GET writes.
    for transcript in transcripts:
        if (transcript.id, transcript.revision) in covered:
            continue
        snapshot = _version_snapshot(session, transcript)
        entries.append(TranscriptVersionResponse(
            id=_version_id(transcript), revision=transcript.revision, change_type="saved",
            created_at=transcript.updated_at, paragraphs=snapshot["paragraphs"],
            settings=snapshot["settings"], legacy=True,
            is_current=bool(current and current.id == transcript.id),
        ))
    return sorted(entries, key=lambda entry: entry.revision, reverse=True)


@router.post("/slides/{slide_number}/versions/{version_id}/restore", response_model=SlideTranscriptResponse)
def restore_transcript_version(
    presentation_id: uuid.UUID, slide_number: int, version_id: uuid.UUID,
    request: RestoreVersionRequest,
    session: Session = Depends(get_db_session), user=Depends(authenticated_user),
):
    presentation = owned_presentation(session, user.id, presentation_id)
    slide = _slide_for_number(session, presentation, slide_number)
    _lock_slide(session, slide)
    current = _require_current_transcript(
        session, presentation, slide, request.slide_transcript_id, request.base_revision,
    )
    version = session.get(TranscriptVersion, version_id)
    source = session.get(SlideTranscript, version.slide_transcript_id) if version else next((
        item for item in session.scalars(select(SlideTranscript).where(SlideTranscript.slide_id == slide.id))
        if _version_id(item) == version_id
    ), None)
    if source is None or source.slide_id != slide.id:
        raise HTTPException(status_code=404, detail="Version not found.")
    if version is None:
        version = _record_version(session, source, "saved")
    snapshot = json.loads(version.snapshot)
    if version.slide_transcript_id == current.id and version.revision == current.revision:
        raise HTTPException(status_code=409, detail="This version is already the current script.")
    _record_version(session, current, "saved")
    settings = snapshot["settings"]
    parent = PresentationTranscript(
        presentation_id=presentation.id, mode=snapshot["mode"] or "human-write",
        target_tone=settings.get("tone"), target_style=settings.get("style"),
        target_audience_level=settings.get("audience_level"),
        target_duration_seconds=settings.get("duration_seconds"),
        model_id=settings.get("model_id") or "restored-script",
        prompt_version=settings.get("prompt_version") or "restored-script-v1", status="completed",
    )
    session.add(parent)
    session.flush()
    restored = SlideTranscript(
        presentation_transcript_id=parent.id, slide_id=slide.id, revision=current.revision + 1,
    )
    session.add(restored)
    session.flush()
    for position, text in enumerate(snapshot["paragraphs"] or [""], 1):
        session.add(TranscriptParagraph(slide_transcript_id=restored.id, position=position, current_text=text))
    # The exact same text has its matching saved feedback. Restoration does not
    # call the provider or invent fresh vocabulary recommendations.
    _apply_analysis(session, restored, snapshot)
    _record_version(session, restored, "restored", settings=settings, restored_from_id=version.id)
    session.commit()
    return _response_for_slide(session, slide, restored, parent.mode, presentation)
