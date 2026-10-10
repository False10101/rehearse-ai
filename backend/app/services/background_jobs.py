"""Protect running jobs across workers and fail interrupted work after restart."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text

from app.db.models import Job, Presentation, UploadPracticeSession
from app.db.session import get_engine, get_session_factory

logger = logging.getLogger(__name__)
ACTIVE = ("queued", "running", "processing")


def lock_key(job_id: uuid.UUID) -> int:
    return int.from_bytes(job_id.bytes[:8], "big", signed=True)


def fail_job(session, job, message: str) -> None:
    job.status = "failed"
    job.error_code = "JOB_INTERRUPTED"
    job.error_message = message
    job.completed_at = datetime.now(UTC)
    if job.job_type in ("slide_analysis", "transcript_prepare"):
        record = session.get(Presentation, job.target_id)
        if record and record.status in ("queued", "processing", "analyzing"):
            record.status = "failed"
            record.processing_error_code = "JOB_INTERRUPTED"
    elif job.job_type == "upload_practice":
        record = session.get(UploadPracticeSession, job.target_id)
        if record and record.status in ("queued", "processing"):
            record.status = "failed"
            record.processing_error_code = "JOB_INTERRUPTED"
            record.processing_error_message = message + " Please upload the recording again."
            record.completed_at = job.completed_at


def run_background_job(job_id: uuid.UUID, task, *args) -> None:
    # A dedicated connection holds the lock throughout the task, not its DB sessions.
    with get_engine().connect() as connection:
        key = lock_key(job_id)
        if not connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}):
            return
        try:
            with get_session_factory()() as session:
                job = session.get(Job, job_id)
                if not job or job.status not in ACTIVE:
                    return
                job.status = "running"
                job.started_at = datetime.now(UTC)
                session.commit()
            try:
                task(*args)
                with get_session_factory()() as session:
                    job = session.get(Job, job_id)
                    if job and job.status in ACTIVE:
                        fail_job(session, job, "Processing ended without a completed result.")
                        session.commit()
            except Exception:
                logger.exception("Background job %s failed", job_id)
                with get_session_factory()() as session:
                    job = session.get(Job, job_id)
                    if job and job.status in ACTIVE:
                        fail_job(session, job, "Processing stopped before it could finish.")
                        session.commit()
        finally:
            try:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            except Exception:
                connection.invalidate()
                logger.exception("Could not release job lock %s", job_id)


def recover_interrupted_jobs(before: datetime) -> int:
    recovered = 0
    with get_session_factory()() as session:
        ids = session.scalars(
            select(Job.id).where(
                Job.status.in_(ACTIVE),
                Job.created_at < before,
            )
        ).all()
    for job_id in ids:
        with get_engine().connect() as connection:
            key = lock_key(job_id)
            if not connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}):
                continue  # Another worker still owns this job.
            try:
                with get_session_factory()() as session:
                    job = session.get(Job, job_id)
                    if job and job.status in ACTIVE:
                        fail_job(session, job, "Processing was interrupted by a server restart.")
                        session.commit()
                        recovered += 1
            finally:
                try:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                except Exception:
                    connection.invalidate()
                    raise
    if recovered:
        logger.warning("Marked %s interrupted jobs failed; completed results preserved", recovered)
    return recovered
