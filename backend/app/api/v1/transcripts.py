# ruff: noqa: E501

import logging
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.api.v1.presentations import authenticated_user, owned_presentation
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
)
from app.db.session import get_db_session, get_session_factory
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
    slide_count: int | None
    slides: list[SlideTranscriptResponse]


class GenerateSlideRequest(BaseModel):
    slide_number: int = Field(ge=1)
    duration_seconds: Literal[45, 75, 105] = 75
    tone: Tone = "auto"
    style: Style = "natural"
    audience_level: AudienceLevel = "general"


class GenerateAllRequest(BaseModel):
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
    latest_revision_source = session.scalar(
        select(TranscriptRevision.source)
        .where(TranscriptRevision.slide_transcript_id == transcript.id)
        .order_by(TranscriptRevision.created_at.desc())
        .limit(1)
    )
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
        .order_by(SlideTranscript.updated_at.desc())
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
    return TranscriptResponse(
        presentation_id=presentation.id,
        preparation_progress=preparation_job.progress_percent if preparation_job else None,
        preparation_status=preparation_job.status if preparation_job else None,
        filename=presentation.original_filename,
        status=presentation.status,
        processing_error_code=presentation.processing_error_code,
        bulk_generation_status=bulk_job.status if bulk_job else None,
        bulk_generation_progress=bulk_job.progress_percent if bulk_job else None,
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


def _require_current_transcript(
    session: Session,
    presentation: Presentation,
    slide: Slide,
    transcript_id: uuid.UUID,
    base_revision: int,
) -> SlideTranscript:
    transcript = session.get(SlideTranscript, transcript_id)
    if transcript is None or transcript.slide_id != slide.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found.")
    parent = session.get(PresentationTranscript, transcript.presentation_transcript_id)
    if parent is None or parent.presentation_id != presentation.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found.")
    if transcript.revision != base_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This script changed elsewhere. Reload it before editing again.",
        )
    return transcript


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
    )
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
    _apply_analysis(session, transcript, result)
    return transcript


def _create_human_draft(
    session: Session,
    presentation: Presentation,
    slide: Slide,
) -> SlideTranscript:
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
) -> None:
    session = get_session_factory()()
    try:
        presentation = session.get(Presentation, presentation_id)
        if presentation is None:
            return
        job = session.scalar(
            select(Job)
            .where(Job.target_id == presentation.id, Job.job_type == "transcript_generate_all")
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
        for index, slide in enumerate(slides, 1):
            existing = latest.get(slide.id)
            has_content = existing is not None and any(
                paragraph.current_text.strip() for paragraph in _paragraphs(session, existing.id)
            )
            if not has_content:
                last_error: Exception | None = None
                for attempt in range(1, 4):
                    try:
                        with session.begin_nested():
                            deck_index = deck_index_by_id[slide.id]
                            transcript = _create_ai_slide_transcript(
                                session,
                                presentation,
                                slide,
                                duration_seconds,
                                tone,
                                style,
                                deck_slides[deck_index - 1] if deck_index > 0 else None,
                                deck_slides[deck_index + 1]
                                if deck_index + 1 < len(deck_slides)
                                else None,
                                deck_slides,
                                audience_level=audience_level,
                            )
                        latest[slide.id] = transcript
                        last_error = None
                        break
                    except Exception as error:
                        last_error = error
                        logger.exception(
                            "Bulk transcript generation attempt %s of 3 failed for presentation %s slide %s",
                            attempt,
                            presentation.id,
                            slide.slide_number,
                        )
                if last_error is not None:
                    raise last_error
            job.progress_percent = round(index / len(slides) * 100)
            session.commit()
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
            .where(Job.target_id == presentation_id, Job.job_type == "transcript_generate_all")
            .order_by(Job.created_at.desc())
        )
        if job:
            job.status = "failed"
            job.error_code = type(error).__name__[:80]
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
            detail="Script generation could not finish. Please retry.",
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
        replacements = enhance_selection(
            slide.extracted_content, selected_parts, request.tone, request.style,
            audience_level=request.audience_level,
        )
    except Exception as error:
        logger.exception(
            "Selected-text enhancement failed for presentation %s slide %s",
            presentation.id,
            slide.slide_number,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Text enhancement could not finish. Please retry.",
        ) from error

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
        _apply_analysis(session, transcript, analysis)
    session.add(
        TranscriptRevision(
            slide_transcript_id=transcript.id,
            base_revision=request.base_revision,
            result_revision=transcript.revision,
            start_paragraph_id=start.id,
            start_offset=request.start.offset,
            end_paragraph_id=end.id,
            end_offset=request.end.offset,
            replacement_text="\n\n".join(replacements),
            source="human-enhance",
        )
    )
    session.commit()
    return _response_for_slide(session, slide, transcript, "human-enhance", presentation)


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
    transcript = _require_current_transcript(
        session, presentation, slide, request.slide_transcript_id, request.base_revision
    )
    paragraphs = _paragraphs(session, transcript.id)
    by_id = {item.id: item for item in paragraphs}
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

    retained_ids = set(submitted_ids)
    removed_ids = [paragraph.id for paragraph in paragraphs if paragraph.id not in retained_ids]
    if removed_ids:
        session.execute(
            delete(TranscriptRevision).where(
                or_(
                    TranscriptRevision.start_paragraph_id.in_(removed_ids),
                    TranscriptRevision.end_paragraph_id.in_(removed_ids),
                )
            )
        )
    for paragraph in paragraphs:
        if paragraph.id not in retained_ids:
            session.delete(paragraph)
        else:
            paragraph.position = -(100_000 + paragraph.position)
    session.flush()

    saved_paragraphs: list[TranscriptParagraph] = []
    for position, update in enumerate(request.paragraphs, 1):
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
    transcript.revision += 1
    session.flush()
    current = [item.current_text for item in saved_paragraphs if item.current_text]
    if not current:
        _clear_analysis(session, transcript)
    else:
        try:
            analysis = analyze_script(current)
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
            replacement_text="\n\n".join(item.text.strip() for item in request.paragraphs),
            source="human-edit",
        )
    )
    session.commit()
    return _response_for_slide(session, slide, transcript, "human-enhance", presentation)
