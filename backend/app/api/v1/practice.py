from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.auth import Auth0Principal, get_current_auth0_principal
from app.core.config import get_settings
from app.db.models import Job, UploadPracticeSession
from app.db.session import get_db_session
from app.services.background_jobs import run_background_job
from app.services.speech_evidence import run_retry_speech_coaching
from app.services.storage import (
    save_limited_upload,
    storage_path,
    upload_practice_source_key,
)
from app.services.upload_practice import (
    _pace_events,
    build_coaching_report,
    evidence_path,
    run_upload_practice,
)
from app.services.users import get_or_create_user

router = APIRouter(prefix="/api/v1/practice/upload", tags=["upload-practice"])


class PoseEventResponse(BaseModel):
    evidence_video_url: str | None = None
    type: str
    label: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    confidence: float
    feedback: str
    evidence_image_url: str | None


class CoachingFindingResponse(BaseModel):
    id: str
    category: str
    headline: str
    observation: str
    impact: str
    recommendation: str
    drill: str
    start_seconds: float
    end_seconds: float
    evidence_image_url: str | None


class UploadPracticeResponse(BaseModel):
    speech_coaching_status: str | None = None
    id: uuid.UUID
    original_filename: str
    status: str
    progress_percent: int
    duration_seconds: float | None
    video_width: int | None
    video_height: int | None
    video_codec: str | None
    transcript: str | None
    word_count: int | None
    speech_duration_seconds: float | None
    words_per_minute: float | None
    filler_events: list[dict[str, Any]]
    filler_clusters: list[dict[str, Any]]
    pause_events: list[dict[str, Any]]
    pace_samples: list[dict[str, Any]]
    speech_moments: list[dict[str, Any]]
    pace_events: list[dict[str, Any]]
    repetition_events: list[dict[str, Any]]
    sensitive_term_flags: list[dict[str, Any]]
    pose_events: list[PoseEventResponse]
    pose_tracking: dict[str, Any] | None = None
    coaching_findings: list[CoachingFindingResponse]
    coaching_strengths: list[str]
    practice_plan: list[str]
    processing_error_code: str | None
    processing_error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class UploadPracticeCreatedResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    status: str


def authenticated_user(
    principal: Auth0Principal = Depends(get_current_auth0_principal),
    session: Session = Depends(get_db_session),
):
    user = get_or_create_user(session, principal.subject)
    session.commit()
    return user


def owned_session(
    database: Session, user_id: uuid.UUID, practice_session_id: uuid.UUID
) -> UploadPracticeSession:
    practice_session = database.scalar(
        select(UploadPracticeSession).where(
            UploadPracticeSession.id == practice_session_id,
            UploadPracticeSession.user_id == user_id,
        )
    )
    if practice_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Practice report not found.",
        )
    return practice_session


def session_response(
    record: UploadPracticeSession, database: Session | None = None
) -> UploadPracticeResponse:
    coaching_job = (
        database.scalar(
            select(Job)
            .where(
                Job.target_id == record.id,
                Job.job_type == "upload_speech_coaching",
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        if database is not None
        else None
    )
    events: list[PoseEventResponse] = []
    for event in record.pose_events:
        if not isinstance(event, dict):
            continue
        evidence_index = event.get("evidence_index")
        image_url = (
            f"/api/v1/practice/upload/sessions/{record.id}/evidence/{evidence_index}"
            if isinstance(evidence_index, int)
            else None
        )
        events.append(
            PoseEventResponse(
                type=str(event.get("type") or "pose_event"),
                label=str(event.get("label") or "Pose event"),
                start_seconds=float(event.get("start_seconds") or 0),
                end_seconds=float(event.get("end_seconds") or 0),
                duration_seconds=float(event.get("duration_seconds") or 0),
                confidence=float(event.get("confidence") or 0),
                feedback=str(event.get("feedback") or "Review this moment in your rehearsal."),
                evidence_image_url=image_url,
                evidence_video_url=(
                    f"/api/v1/practice/upload/sessions/{record.id}/gesture/{event['clip_index']}"
                    if event.get("clip_index")
                    else None
                ),
            )
        )
    samples = [
        sample
        for sample in (record.pace_samples or [])
        if float(sample["end_seconds"]) - float(sample["start_seconds"]) >= 14.99
    ]
    pace_events = _pace_events(samples) if record.pace_samples else record.pace_events
    generated_coaching = build_coaching_report(
        {
            "words_per_minute": record.words_per_minute,
            "filler_events": record.filler_events,
            "filler_clusters": record.filler_clusters,
            "pause_events": record.pause_events,
            "pace_events": pace_events,
            "repetition_events": record.repetition_events,
        },
        record.pose_events,
        record.pose_tracking,
    )
    stored_findings = list(generated_coaching["findings"])
    stored_strengths = list(generated_coaching["strengths"])
    stored_plan = list(generated_coaching["practice_plan"])
    contextual = {
        moment["kind"]: moment
        for moment in (record.speech_moments or [])
        if moment.get("coaching_status") == "ready"
    }
    if contextual:
        stored_plan = [str(moment["recommendation"]) for moment in list(contextual.values())[:3]]
    findings: list[CoachingFindingResponse] = []
    for finding in stored_findings:
        if not isinstance(finding, dict):
            continue
        moment = contextual.get(finding.get("id"))
        if moment:
            finding["recommendation"] = moment["recommendation"]
            finding["drill"] = moment["suggested_delivery"]
        evidence_index = (
            finding.get("evidence_index") if finding.get("category") == "Body language" else None
        )
        image_url = (
            f"/api/v1/practice/upload/sessions/{record.id}/evidence/{evidence_index}"
            if isinstance(evidence_index, int)
            else None
        )
        findings.append(
            CoachingFindingResponse(
                id=str(finding.get("id") or "coaching-finding"),
                category=str(finding.get("category") or "Presentation delivery"),
                headline=str(finding.get("headline") or "Review this moment"),
                observation=str(finding.get("observation") or ""),
                impact=str(finding.get("impact") or ""),
                recommendation=str(finding.get("recommendation") or ""),
                drill=str(finding.get("drill") or ""),
                start_seconds=float(finding.get("start_seconds") or 0),
                end_seconds=float(finding.get("end_seconds") or 0),
                evidence_image_url=image_url,
            )
        )
    return UploadPracticeResponse(
        id=record.id,
        original_filename=record.original_filename,
        status=record.status,
        progress_percent=record.progress_percent,
        duration_seconds=record.duration_seconds,
        video_width=record.video_width,
        video_height=record.video_height,
        video_codec=record.video_codec,
        transcript=record.transcript,
        word_count=record.word_count,
        speech_duration_seconds=record.speech_duration_seconds,
        words_per_minute=record.words_per_minute,
        filler_events=record.filler_events,
        filler_clusters=record.filler_clusters,
        pause_events=record.pause_events,
        pace_samples=samples,
        speech_coaching_status=coaching_job.status if coaching_job else None,
        speech_moments=[
            {
                **moment,
                "audio_url": (
                    f"/api/v1/practice/upload/sessions/{record.id}/speech/{moment['id']}"
                    if moment.get("audio_available")
                    else None
                ),
            }
            for moment in (record.speech_moments or [])
        ],
        pace_events=pace_events,
        repetition_events=record.repetition_events,
        sensitive_term_flags=record.sensitive_term_flags,
        pose_events=events,
        pose_tracking=record.pose_tracking,
        coaching_findings=findings,
        coaching_strengths=[str(item) for item in stored_strengths],
        practice_plan=[str(item) for item in stored_plan],
        processing_error_code=record.processing_error_code,
        processing_error_message=record.processing_error_message,
        created_at=record.created_at,
        completed_at=record.completed_at,
    )


@router.post(
    "/sessions",
    response_model=UploadPracticeCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_upload_practice_session(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    database: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> UploadPracticeCreatedResponse:
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() != ".mp4":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload an MP4 rehearsal video encoded with H.264.",
        )
    practice_session = UploadPracticeSession(
        user_id=user.id,
        original_filename=filename[:255] or "rehearsal.mp4",
        status="queued",
    )
    database.add(practice_session)
    database.flush()
    source_key = upload_practice_source_key(user.id, practice_session.id)
    try:
        await save_limited_upload(
            file,
            source_key,
            get_settings().upload_practice_max_bytes,
            "The rehearsal video exceeds the 500 MB upload limit.",
        )
    except ValueError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(error),
        ) from error
    job = Job(
        user_id=user.id,
        job_type="upload_practice",
        target_type="upload_practice_session",
        target_id=practice_session.id,
        status="queued",
    )
    database.add(job)
    database.commit()
    background_tasks.add_task(
        run_background_job, job.id, run_upload_practice, practice_session.id, source_key
    )
    return UploadPracticeCreatedResponse(
        id=practice_session.id,
        job_id=job.id,
        status=practice_session.status,
    )


@router.post("/sessions/{practice_session_id}/speech/retry", status_code=202)
def retry_speech_coaching(
    practice_session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    database: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
):
    record = owned_session(database, user.id, practice_session_id)
    database.refresh(record, with_for_update=True)
    if record.status != "completed":
        raise HTTPException(409, "Wait for the recording analysis to finish.")
    active = database.scalar(
        select(Job).where(
            Job.target_id == record.id,
            Job.job_type == "upload_speech_coaching",
            Job.status.in_(["queued", "running"]),
        )
    )
    if active:
        return {"job_id": active.id, "status": active.status}
    if not any(m.get("coaching_status") != "ready" for m in (record.speech_moments or [])):
        raise HTTPException(409, "There is no missing speech feedback to retry.")
    job = Job(
        user_id=user.id,
        job_type="upload_speech_coaching",
        target_type="upload_practice_session",
        target_id=record.id,
        status="queued",
    )
    database.add(job)
    database.commit()
    background_tasks.add_task(
        run_background_job, job.id, run_retry_speech_coaching, record.id, job.id
    )
    return {"job_id": job.id, "status": job.status}


@router.get("/sessions", response_model=list[UploadPracticeResponse])
def list_upload_practice_sessions(
    database: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> list[UploadPracticeResponse]:
    records = database.scalars(
        select(UploadPracticeSession)
        .where(UploadPracticeSession.user_id == user.id)
        .order_by(UploadPracticeSession.created_at.desc())
        .limit(25)
    )
    return [session_response(record) for record in records]


@router.get("/sessions/{practice_session_id}", response_model=UploadPracticeResponse)
def get_upload_practice_session(
    practice_session_id: uuid.UUID,
    database: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> UploadPracticeResponse:
    return session_response(owned_session(database, user.id, practice_session_id), database)


@router.get("/sessions/{practice_session_id}/evidence/{evidence_index}")
def get_upload_practice_evidence(
    practice_session_id: uuid.UUID,
    evidence_index: int,
    database: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> FileResponse:
    record = owned_session(database, user.id, practice_session_id)
    pose_event = next(
        (
            item
            for item in record.pose_events
            if isinstance(item, dict) and item.get("evidence_index") == evidence_index
        ),
        None,
    )
    image = evidence_path(user.id, practice_session_id, evidence_index)
    if pose_event is None and not image.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence frame not found.",
        )
    if not image.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence frame not found.",
        )
    return FileResponse(image, media_type="image/jpeg")


@router.get("/sessions/{practice_session_id}/gesture/{clip_index}")
def get_gesture_clip(
    practice_session_id: uuid.UUID,
    clip_index: int,
    database: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> FileResponse:
    record = owned_session(database, user.id, practice_session_id)
    if not any(event.get("clip_index") == clip_index for event in record.pose_events):
        raise HTTPException(status_code=404, detail="Gesture clip not found.")
    path = storage_path(
        f"practice-reports/{user.id}/{practice_session_id}/gesture_{clip_index:03d}.mp4"
    )
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Gesture clip not found.")
    return FileResponse(
        path, media_type="video/mp4", headers={"Cache-Control": "private, no-store"}
    )


@router.delete("/sessions/{practice_session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upload_practice_session(
    practice_session_id: uuid.UUID,
    database: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> None:
    record = owned_session(database, user.id, practice_session_id)
    report_directory = storage_path(f"practice-reports/{user.id}/{practice_session_id}")
    temporary_directory = storage_path(f"temporary/upload-practice/{user.id}/{practice_session_id}")
    database.execute(delete(Job).where(Job.target_id == practice_session_id))
    database.delete(record)
    database.commit()
    shutil.rmtree(report_directory, ignore_errors=True)
    shutil.rmtree(temporary_directory, ignore_errors=True)


@router.get("/sessions/{practice_session_id}/speech/{moment_id}")
def get_speech_excerpt(
    practice_session_id: uuid.UUID,
    moment_id: int,
    database: Session = Depends(get_db_session),
    user=Depends(authenticated_user),
) -> FileResponse:
    record = owned_session(database, user.id, practice_session_id)
    moment = next(
        (
            m
            for m in (record.speech_moments or [])
            if m.get("id") == moment_id and m.get("audio_available")
        ),
        None,
    )
    if moment is None:
        raise HTTPException(status_code=404, detail="Audio excerpt not found.")
    path = storage_path(
        f"practice-reports/{user.id}/{practice_session_id}/speech_{moment_id:03d}.mp3"
    )
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio excerpt not found.")
    return FileResponse(
        path,
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, no-store"},
    )
