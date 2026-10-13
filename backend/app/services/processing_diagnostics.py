"""Log the processing state behind successful status responses and failure screens."""

import json
import logging

logger = logging.getLogger(__name__)


def log_processing_state(presentation, job, *, event, analysis=None, available=False, reason=None):
    state = {
        "event": event,
        "presentation_id": str(presentation.id),
        "presentation_status": presentation.status,
        "processing_error_code": presentation.processing_error_code,
        "slide_count": presentation.slide_count,
        "analysis_id": str(analysis.id) if analysis is not None else None,
        "analysis_available": available,
        "analysis_unavailable_reason": reason,
        "job_id": str(job.id) if job is not None else None,
        "job_type": job.job_type if job is not None else None,
        "job_status": job.status if job is not None else None,
        "job_progress_percent": job.progress_percent if job is not None else None,
        "job_error_code": job.error_code if job is not None else None,
        "job_error_message": job.error_message if job is not None else None,
        "job_started_at": job.started_at if job is not None else None,
        "job_completed_at": job.completed_at if job is not None else None,
    }
    level = logging.WARNING if (
        presentation.status == "failed" or presentation.processing_error_code
        or (job is not None and job.status == "failed")
        or (reason is not None and presentation.status == "completed")
    ) else logging.INFO
    logger.log(level, "Processing state: %s", json.dumps(state, default=str))
