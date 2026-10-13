import io
import logging
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Auth0Principal, get_current_auth0_principal
from app.db.models import Job, Presentation, PresentationAnalysis, Slide
from app.db.session import get_db_session
from app.services.agenda_generator import (
    AGENDA_LAYOUTS,
    AGENDA_THEMES,
    AgendaGenerationError,
    generate_agenda_deck,
)
from app.services.agenda_layouts import agenda_catalog
from app.services.processing_diagnostics import log_processing_state
from app.services.report_export import feedback_workbook
from app.services.slide_analyzer import (
    PROMPT_VERSION,
    extract_slides,
    render_slides_to_images,
    run_slide_analysis,
    run_transcript_preparation,
    validate_slide_analysis_result,
)
from app.services.storage import presentation_upload_key, save_upload, slide_image_key, storage_path
from app.services.users import get_or_create_user

router = APIRouter(prefix="/api/v1/presentations", tags=["presentations"])
logger = logging.getLogger(__name__)

MAX_PRESENTATION_BYTES = 30 * 1024 * 1024


def preserve_visual_context(extracted: dict, previous: dict) -> dict:
    content = dict(extracted)
    visual_context = previous.get("img_context")
    if visual_context:
        content["img_context"] = visual_context
    return content


def shift_slide_references(value: str, insert_after_slide: int) -> str:
    """Shift slide numbers in model prose without touching unrelated numbers."""
    pattern = re.compile(
        r"\b(slides?)\s+(\d+(?:\s*(?:,|and|&|to|[-–])\s*\d+)*)",
        re.IGNORECASE,
    )

    def replace(match: re.Match[str]) -> str:
        numbers = re.sub(
            r"\d+",
            lambda number: (
                str(int(number.group()) + 1)
                if int(number.group()) > insert_after_slide
                else number.group()
            ),
            match.group(2),
        )
        return f"{match.group(1)} {numbers}"

    return pattern.sub(replace, value)


def shift_deck_feedback_references(raw_output: dict, insert_after_slide: int) -> dict:
    shifted = dict(raw_output)
    for field in (
        "score_rationale",
        "deck_top_priorities",
        "examiner_red_flags",
        "cohesion_feedback",
    ):
        value = shifted.get(field)
        if isinstance(value, str):
            shifted[field] = shift_slide_references(value, insert_after_slide)
        elif isinstance(value, list):
            shifted[field] = [
                shift_slide_references(item, insert_after_slide) if isinstance(item, str) else item
                for item in value
            ]
    return shifted


@router.get("/agenda/templates")
def get_agenda_templates(
    _principal: Auth0Principal = Depends(get_current_auth0_principal),
) -> dict:
    return agenda_catalog()


class UploadPresentationResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    status: str


class PresentationListItem(BaseModel):
    id: uuid.UUID
    title: str
    original_filename: str
    status: str
    slide_count: int | None
    created_at: datetime


class SlideResponse(BaseModel):
    number: int
    title: str | None
    layout_name: str | None
    image_url: str | None
    generated_by_agenda: bool = False


class PresentationResponse(PresentationListItem):
    processing_error_code: str | None
    job_status: str | None
    job_progress_percent: int | None
    analysis: dict[str, Any] | None
    slides: list[SlideResponse]


class GenerateAgendaRequest(BaseModel):
    layout: Literal[
        "paired-sections",
        "editorial-list",
        "ruled-list",
        "statement-grid",
        "capsule-columns",
    ]
    theme: Literal["violet", "ocean", "forest", "sunset", "midnight", "slate"]


class GenerateAgendaResponse(BaseModel):
    inserted_slide_number: int
    items: list[str]


def owned_presentation(
    session: Session, user_id: uuid.UUID, presentation_id: uuid.UUID
) -> Presentation:
    presentation = session.scalar(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == user_id,
        )
    )
    if presentation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presentation not found.")
    return presentation


def authenticated_user(
    principal: Auth0Principal = Depends(get_current_auth0_principal),
    session: Session = Depends(get_db_session),
):
    user = get_or_create_user(session, principal.subject)
    session.commit()
    return user


async def _upload_presentation_for_job(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    session: Session,
    user,
    *,
    job_type: str,
    task,
) -> UploadPresentationResponse:
    filename = file.filename or ""
    if Path(filename).suffix.lower() != ".pptx":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload a .pptx presentation.",
        )

    presentation = Presentation(
        user_id=user.id,
        title=Path(filename).stem[:255] or "Untitled presentation",
        original_filename=Path(filename).name[:255],
        status="queued",
    )
    session.add(presentation)
    session.flush()
    presentation.storage_key = presentation_upload_key(user.id, presentation.id)

    try:
        await save_upload(file, presentation.storage_key, MAX_PRESENTATION_BYTES)
    except ValueError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(error),
        ) from error

    job = Job(
        user_id=user.id,
        job_type=job_type,
        target_type="presentation",
        target_id=presentation.id,
        status="queued",
    )
    session.add(job)
    session.commit()

    from app.services.background_jobs import run_background_job
    background_tasks.add_task(run_background_job, job.id, task, presentation.id)
    return UploadPresentationResponse(id=presentation.id, job_id=job.id, status=presentation.status)


@router.post("", response_model=UploadPresentationResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_presentation(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> UploadPresentationResponse:
    return await _upload_presentation_for_job(
        background_tasks,
        file,
        session,
        user,
        job_type="slide_analysis",
        task=run_slide_analysis,
    )


@router.post(
    "/transcript",
    response_model=UploadPresentationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_transcript_presentation(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> UploadPresentationResponse:
    return await _upload_presentation_for_job(
        background_tasks,
        file,
        session,
        user,
        job_type="transcript_prepare",
        task=run_transcript_preparation,
    )


@router.post(
    "/{presentation_id}/analyze",
    response_model=UploadPresentationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_existing_presentation(
    presentation_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> UploadPresentationResponse:
    presentation = owned_presentation(session, user.id, presentation_id)
    if not presentation.storage_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The original presentation file is unavailable.",
        )
    if presentation.status in {"queued", "processing"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This presentation is already being prepared.",
        )
    completed_analysis = session.scalar(
        select(PresentationAnalysis)
        .where(
            PresentationAnalysis.presentation_id == presentation.id,
            PresentationAnalysis.status == "completed",
        )
        .order_by(PresentationAnalysis.created_at.desc())
    )
    latest_analysis_job = session.scalar(
        select(Job)
        .where(Job.target_id == presentation.id, Job.job_type == "slide_analysis")
        .order_by(Job.created_at.desc())
    )
    analysis_is_valid = False
    if completed_analysis is not None and completed_analysis.prompt_version == PROMPT_VERSION:
        slide_numbers = [
            slide.slide_number
            for slide in session.scalars(
                select(Slide)
                .where(Slide.presentation_id == presentation.id)
                .order_by(Slide.slide_number)
            )
            if slide.extracted_content.get("generated_by") != "agenda"
        ]
        try:
            validate_slide_analysis_result(completed_analysis.raw_output, slide_numbers)
            analysis_is_valid = True
        except (ValidationError, ValueError):
            logger.exception(
                "Stored analysis cannot be reused presentation_id=%s analysis_id=%s",
                presentation.id, completed_analysis.id,
            )
    if analysis_is_valid and not (latest_analysis_job and latest_analysis_job.status == "failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This presentation already has a completed analysis.",
        )
    job = Job(
        user_id=user.id,
        job_type="slide_analysis",
        target_type="presentation",
        target_id=presentation.id,
        status="queued",
    )
    presentation.status = "queued"
    presentation.processing_error_code = None
    session.add(job)
    session.commit()
    from app.services.background_jobs import run_background_job
    background_tasks.add_task(run_background_job, job.id, run_slide_analysis, presentation.id)
    return UploadPresentationResponse(id=presentation.id, job_id=job.id, status=presentation.status)


@router.get("", response_model=list[PresentationListItem])
def list_presentations(
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> list[Presentation]:
    return list(
        session.scalars(
            select(Presentation)
            .where(Presentation.user_id == user.id)
            .order_by(Presentation.created_at.desc())
        )
    )


@router.get("/{presentation_id}", response_model=PresentationResponse)
def get_presentation(
    presentation_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> PresentationResponse:
    presentation = owned_presentation(session, user.id, presentation_id)
    job = session.scalar(
        select(Job).where(Job.target_id == presentation.id).order_by(Job.created_at.desc())
    )
    analysis = session.scalar(
        select(PresentationAnalysis)
        .where(
            PresentationAnalysis.presentation_id == presentation.id,
            PresentationAnalysis.status == "completed",
        )
        .order_by(PresentationAnalysis.created_at.desc())
    )
    slides = list(
        session.scalars(
            select(Slide)
            .where(Slide.presentation_id == presentation.id)
            .order_by(Slide.slide_number)
        )
    )
    analysis_payload: dict[str, Any] | None = None
    analysis_error = presentation.processing_error_code
    unavailable_reason = "no_completed_analysis" if analysis is None else None
    latest_analysis_failed = bool(
        job and job.job_type == "slide_analysis" and job.status == "failed"
    )
    if analysis and analysis.prompt_version != PROMPT_VERSION:
        unavailable_reason = "prompt_version_mismatch"
        logger.warning(
            "Analysis withheld presentation_id=%s analysis_id=%s "
            "stored_version=%s current_version=%s",
            presentation.id, analysis.id, analysis.prompt_version, PROMPT_VERSION,
        )
        analysis_error = "This analysis uses an older analyzer version. Run Slide Analyzer again."
    elif analysis and not latest_analysis_failed:
        analyzed_slide_numbers = [
            slide.slide_number
            for slide in slides
            if slide.extracted_content.get("generated_by") != "agenda"
        ]
        try:
            analysis_payload = validate_slide_analysis_result(
                analysis.raw_output,
                analyzed_slide_numbers,
            )
        except (ValidationError, ValueError):
            logger.exception(
                "Stored analysis validation failed presentation_id=%s analysis_id=%s "
                "slide_numbers=%s",
                presentation.id, analysis.id, analyzed_slide_numbers,
            )
            unavailable_reason = "stored_analysis_validation_failed"
            analysis_error = "Previous analysis data is incomplete. Run Slide Analyzer again."
    elif latest_analysis_failed:
        unavailable_reason = "latest_slide_analysis_job_failed"
    log_processing_state(
        presentation, job, event="presentation_status_response", analysis=analysis,
        available=analysis_payload is not None, reason=unavailable_reason,
    )
    return PresentationResponse(
        id=presentation.id,
        title=presentation.title,
        original_filename=presentation.original_filename,
        status=presentation.status,
        slide_count=presentation.slide_count,
        created_at=presentation.created_at,
        processing_error_code=analysis_error,
        job_status=job.status if job else None,
        job_progress_percent=job.progress_percent if job else None,
        analysis=analysis_payload,
        slides=[
            SlideResponse(
                number=slide.slide_number,
                title=slide.title,
                layout_name=slide.layout_name,
                image_url=(
                    f"/api/v1/presentations/{presentation.id}/slides/{slide.slide_number}/image?v={presentation.updated_at.timestamp():.6f}"
                    if slide.image_storage_key
                    else None
                ),
                generated_by_agenda=slide.extracted_content.get("generated_by") == "agenda",
            )
            for slide in slides
        ],
    )


@router.get("/{presentation_id}/slides/{slide_number}/image")
def get_slide_image(
    presentation_id: uuid.UUID,
    slide_number: int,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> FileResponse:
    presentation = owned_presentation(session, user.id, presentation_id)
    slide = session.scalar(
        select(Slide).where(
            Slide.presentation_id == presentation.id,
            Slide.slide_number == slide_number,
        )
    )
    if slide is None or not slide.image_storage_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rendered slide not found.",
        )
    image_path = storage_path(slide.image_storage_key)
    if not image_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rendered slide is unavailable.",
        )
    return FileResponse(image_path, media_type="image/png")


@router.get("/{presentation_id}/export")
def export_presentation(
    presentation_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
):
    presentation = owned_presentation(session, user.id, presentation_id)
    if presentation.status in ("queued", "processing"):
        raise HTTPException(
            status_code=409, detail="Wait for processing to finish before exporting."
        )
    source = storage_path(presentation.storage_key) if presentation.storage_key else None
    if source is None or not source.is_file():
        raise HTTPException(status_code=404, detail="Presentation file unavailable.")
    analysis = session.scalar(
        select(PresentationAnalysis)
        .where(
            PresentationAnalysis.presentation_id == presentation.id,
            PresentationAnalysis.status == "completed",
        )
        .order_by(PresentationAnalysis.created_at.desc())
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(source, Path(presentation.original_filename).name)
        if analysis and isinstance(analysis.raw_output, dict):
            archive.writestr("slide-feedback.xlsx", feedback_workbook(analysis.raw_output))
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="presentation-export.zip"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/{presentation_id}/agenda")
def generate_agenda(
    presentation_id: uuid.UUID,
    request: GenerateAgendaRequest,
    session: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> GenerateAgendaResponse:
    presentation = owned_presentation(session, user.id, presentation_id)
    if presentation.status != "completed" or not presentation.storage_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analyze the presentation before creating an agenda.",
        )
    if request.layout not in AGENDA_LAYOUTS or request.theme not in AGENDA_THEMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown agenda layout or theme.",
        )

    slides = list(
        session.scalars(
            select(Slide)
            .where(Slide.presentation_id == presentation.id)
            .order_by(Slide.slide_number)
        )
    )
    if any(slide.extracted_content.get("generated_by") == "agenda" for slide in slides):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This presentation already has a generated agenda.",
        )
    source_path = storage_path(presentation.storage_key)
    try:
        with tempfile.TemporaryDirectory(prefix="rehearse-agenda-") as temp_dir:
            temporary_directory = Path(temp_dir)
            generated_path = temporary_directory / "with-agenda.pptx"
            items, insert_after_slide = generate_agenda_deck(
                source_path,
                generated_path,
                [slide.extracted_content for slide in slides],
                request.layout,
                request.theme,
            )
            rendered_images = render_slides_to_images(generated_path, temporary_directory)
            extracted_slides = extract_slides(generated_path)
            inserted_slide_number = insert_after_slide + 1

            # The source stored for this presentation is the working copy used by
            # the app. Replace it only after generation and rendering both succeed.
            shutil.copy2(generated_path, source_path)

            # Shift from the end to retain the unique (presentation, number) index.
            for slide in reversed(slides):
                if slide.slide_number > insert_after_slide:
                    slide.slide_number += 1
                    session.flush()

            slides_by_number = {slide.slide_number: slide for slide in slides}
            agenda_slide = Slide(
                presentation_id=presentation.id,
                slide_number=inserted_slide_number,
                title="Agenda",
                layout_name="Generated agenda",
                extracted_content={},
            )
            session.add(agenda_slide)
            session.flush()
            slides_by_number[inserted_slide_number] = agenda_slide

            for extracted in extracted_slides:
                number = extracted["num"]
                slide = slides_by_number[number]
                content = dict(extracted)
                if number == inserted_slide_number:
                    content.update(
                        {
                            "generated_by": "agenda",
                            "title": "Agenda",
                            "agenda_items": items,
                            "agenda_layout": request.layout,
                            "agenda_theme": request.theme,
                        }
                    )
                    slide.title = "Agenda"
                    slide.layout_name = "Generated agenda"
                else:
                    content = preserve_visual_context(content, slide.extracted_content)
                    slide.title = extracted["title"] or None
                    slide.layout_name = extracted["layout"]
                slide.extracted_content = content
                slide.background_color = extracted["bg_color"]
                image_key = slide_image_key(user.id, presentation.id, number)
                image_path = storage_path(image_key)
                image_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(rendered_images[number], image_path)
                slide.image_storage_key = image_key

            presentation.slide_count = len(extracted_slides)
            analysis = session.scalar(
                select(PresentationAnalysis)
                .where(
                    PresentationAnalysis.presentation_id == presentation.id,
                    PresentationAnalysis.status == "completed",
                )
                .order_by(PresentationAnalysis.created_at.desc())
            )
            if analysis:
                raw_output = shift_deck_feedback_references(
                    analysis.raw_output,
                    insert_after_slide,
                )
                shifted_feedback = []
                for feedback in raw_output.get("per_slide", []):
                    if not isinstance(feedback, dict):
                        continue
                    updated_feedback = dict(feedback)
                    if (
                        isinstance(updated_feedback.get("num"), int)
                        and updated_feedback["num"] > insert_after_slide
                    ):
                        updated_feedback["num"] += 1
                    shifted_feedback.append(updated_feedback)
                raw_output["per_slide"] = shifted_feedback
                raw_output["agenda_status"] = "found"
                raw_output["generated_agenda"] = {
                    "slide_number": inserted_slide_number,
                    "items": items,
                    "layout": request.layout,
                    "theme": request.theme,
                }
                analysis.agenda_status = "found"
                analysis.raw_output = raw_output
            session.commit()
    except AgendaGenerationError as error:
        session.rollback()
        logger.warning("Agenda generation failed for presentation %s: %s", presentation.id, error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
    except Exception as error:
        session.rollback()
        logger.exception("Agenda generation failed for presentation %s", presentation.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agenda generation could not finish.",
        ) from error

    return GenerateAgendaResponse(inserted_slide_number=inserted_slide_number, items=items)
