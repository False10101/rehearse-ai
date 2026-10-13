import json
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.api.v1 import presentations
from app.services.processing_diagnostics import log_processing_state


def make_records():
    presentation = SimpleNamespace(
        id=uuid4(), status="failed", processing_error_code="ValueError", slide_count=13,
        title="Test", original_filename="Test.pptx", created_at=datetime.now(UTC),
    )
    job = SimpleNamespace(
        id=uuid4(), job_type="slide_analysis", status="failed", progress_percent=5,
        error_code="ValueError", error_message="Unrecognized shape geometry",
        started_at=datetime.now(UTC), completed_at=datetime.now(UTC),
    )
    return presentation, job


def test_failed_status_logs_stored_failure_even_when_http_request_succeeds(caplog):
    presentation, job = make_records()
    with caplog.at_level(logging.WARNING):
        log_processing_state(presentation, job, event="presentation_status_response")
    state = json.loads(caplog.records[-1].message.split("Processing state: ", 1)[1])
    assert state["presentation_id"] == str(presentation.id)
    assert state["job_id"] == str(job.id)
    assert state["job_type"] == "slide_analysis"
    assert state["job_error_message"] == "Unrecognized shape geometry"
    assert state["processing_error_code"] == "ValueError"


def test_presentation_response_logs_no_completed_analysis(monkeypatch, caplog):
    presentation, job = make_records()
    job.job_type = "transcript_generate_all"
    monkeypatch.setattr(presentations, "owned_presentation", lambda *args: presentation)
    session = Mock()
    session.scalar.side_effect = [job, None]
    session.scalars.return_value = []
    with caplog.at_level(logging.WARNING):
        response = presentations.get_presentation(
            presentation.id, session, SimpleNamespace(id=uuid4())
        )
    assert response.status == "failed"
    assert response.analysis is None
    assert "no_completed_analysis" in caplog.text
    assert str(presentation.id) in caplog.text


def test_presentation_response_logs_exact_validation_failure(monkeypatch, caplog):
    presentation, job = make_records()
    presentation.status = "completed"
    presentation.processing_error_code = None
    job.status = "completed"
    job.error_code = job.error_message = None
    analysis = SimpleNamespace(
        id=uuid4(), prompt_version=presentations.PROMPT_VERSION, raw_output={}
    )
    monkeypatch.setattr(presentations, "owned_presentation", lambda *args: presentation)
    monkeypatch.setattr(
        presentations, "validate_slide_analysis_result",
        Mock(side_effect=ValueError("Missing per-slide result for slide 7")),
    )
    session = Mock()
    session.scalar.side_effect = [job, analysis]
    session.scalars.return_value = []
    with caplog.at_level(logging.WARNING):
        response = presentations.get_presentation(
            presentation.id, session, SimpleNamespace(id=uuid4())
        )
    assert response.analysis is None
    assert "Missing per-slide result for slide 7" in caplog.text
    assert "stored_analysis_validation_failed" in caplog.text


def test_successful_status_is_logged_without_a_failure(caplog):
    presentation, job = make_records()
    presentation.status = job.status = "completed"
    presentation.processing_error_code = job.error_code = job.error_message = None
    with caplog.at_level(logging.INFO):
        log_processing_state(presentation, job, event="slide_analysis_saved", available=True)
    assert caplog.records[-1].levelno == logging.INFO
    assert '"analysis_available": true' in caplog.text
