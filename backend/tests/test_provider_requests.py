import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
import requests

from app.api.v1 import transcripts
from app.services import provider_requests, slide_analyzer, transcript_enhancer


def response(status, source=None, reason=None, delay=None, embedded=False):
    result = requests.Response()
    result.status_code = status
    result.url = "https://openrouter.ai/api/v1/chat/completions"
    metadata = {"limit_source": source, "reason": reason}
    if delay is not None:
        if embedded:
            metadata["headers"] = {"Retry-After": str(delay)}
        else:
            result.headers["Retry-After"] = str(delay)
    result._content = json.dumps({"error": {"metadata": metadata}}).encode()
    return result


def setup(monkeypatch, responses):
    calls, sleeps = [], []
    iterator = iter(responses)

    def post(*args, **kwargs):
        calls.append(kwargs)
        return next(iterator)

    monkeypatch.setattr(provider_requests.requests, "post", post)
    monkeypatch.setattr(provider_requests.time, "sleep", sleeps.append)
    return calls, sleeps


def request():
    return provider_requests.post_provider_request(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": "Bearer private-key"}, json={"model": "test-model"}, timeout=120,
    )


@pytest.mark.parametrize("embedded", [False, True])
def test_temporary_budget_waits_before_retry_then_returns_success(monkeypatch, embedded):
    success = response(200)
    calls, sleeps = setup(monkeypatch, [
        response(402, "openrouter_in_flight_budget", "in_flight_budget_exhausted", 120, embedded),
        success,
    ])
    assert request() is success
    assert sleeps == [120]
    assert len(calls) == 2


@pytest.mark.parametrize("source,reason", [
    ("openrouter_credits", "weight_exceeds_budget"),
    ("openrouter_key_limit", "limit_exhausted"), (None, None),
])
def test_permanent_402_never_retries_even_with_retry_header(monkeypatch, source, reason):
    calls, sleeps = setup(monkeypatch, [response(402, source, reason, 120)])
    with pytest.raises(provider_requests.ProviderRequestError) as caught:
        request()
    assert caught.value.error_code == "AI_PROVIDER_CREDITS"
    assert len(calls) == 1
    assert sleeps == []


def test_exhausted_budget_has_only_three_attempts(monkeypatch):
    calls, sleeps = setup(monkeypatch, [
        response(402, "openrouter_in_flight_budget", delay=120) for _ in range(3)
    ])
    with pytest.raises(provider_requests.ProviderRequestError) as caught:
        request()
    assert caught.value.error_code == "AI_PROVIDER_BUSY"
    assert len(calls) == 3
    assert sleeps == [120, 120]


def test_large_delay_is_not_shortened_to_retry_too_early(monkeypatch):
    calls, sleeps = setup(monkeypatch, [response(402, "openrouter_in_flight_budget", delay=600)])
    with pytest.raises(provider_requests.ProviderRequestError) as caught:
        request()
    assert caught.value.retry_after == 600
    assert len(calls) == 1
    assert sleeps == []


def test_rate_limit_and_unavailable_respect_retry_after(monkeypatch):
    _, sleeps = setup(
        monkeypatch, [response(429, delay=30), response(503, delay=20), response(200)]
    )
    request()
    assert sleeps == [30, 20]


def test_provider_log_redacts_credentials(monkeypatch, caplog):
    rejected = response(401)
    rejected._content = b'{"error":{"message":"private-key"}}'
    setup(monkeypatch, [rejected])
    with pytest.raises(provider_requests.ProviderRequestError):
        request()
    assert "private-key" not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_slide_analysis_does_not_multiply_exhausted_provider_retries(monkeypatch):
    calls, sleeps = setup(monkeypatch, [
        response(402, "openrouter_in_flight_budget", delay=120) for _ in range(3)
    ])
    monkeypatch.setattr(slide_analyzer, "openrouter_headers", lambda: {})
    with pytest.raises(slide_analyzer.SlideAnalysisGenerationError) as caught:
        slide_analyzer.analyze([{"num": 1, "text": []}])
    assert caught.value.error_code == "AI_PROVIDER_BUSY"
    assert len(calls) == 3
    assert sleeps == [120, 120]


def test_transcript_uses_shared_retry_policy(monkeypatch):
    success = response(200)
    success._content = b'{"choices":[{"message":{"content":"{}"}}]}'
    _, sleeps = setup(
        monkeypatch, [response(402, "openrouter_in_flight_budget", delay=120), success]
    )
    monkeypatch.setattr(transcript_enhancer, "openrouter_headers", lambda: {})
    assert transcript_enhancer._request_json("test") == {}
    assert sleeps == [120]


def test_bulk_generation_does_not_restart_provider_retry_cycle(monkeypatch):
    calls, sleeps = setup(monkeypatch, [
        response(402, "openrouter_in_flight_budget", delay=120) for _ in range(3)
    ])
    presentation = SimpleNamespace(id=uuid4())
    job = SimpleNamespace(status="queued")
    slide = SimpleNamespace(id=uuid4(), slide_number=1)
    session = Mock()
    session.get.return_value = presentation
    session.scalar.return_value = job
    session.scalars.return_value = [slide]
    session.begin_nested.side_effect = nullcontext
    monkeypatch.setattr(transcripts, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(transcripts, "_latest_by_slide", lambda *args: ({}, {}))
    monkeypatch.setattr(transcripts, "_create_ai_slide_transcript", lambda *args, **kw: request())
    transcripts.run_generate_all_transcripts(presentation.id, 75, "informative", "natural", 1, 1)
    assert job.status == "failed"
    assert job.error_code == "AI_PROVIDER_BUSY"
    assert len(calls) == 3
    assert sleeps == [120, 120]


@pytest.mark.parametrize("slide_count", [1, None])
def test_slide_job_preserves_provider_failure_category(monkeypatch, slide_count):
    presentation = SimpleNamespace(
        id=uuid4(), storage_key="test", status="queued", processing_error_code=None,
        slide_count=slide_count,
    )
    job = SimpleNamespace(
        id=uuid4(), job_type="slide_analysis", status="queued", progress_percent=0,
        error_code=None, error_message=None, started_at=None, completed_at=None,
    )
    session = Mock()
    session.get.return_value = presentation
    monkeypatch.setattr(slide_analyzer, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(slide_analyzer, "_latest_job", lambda *args: job)
    monkeypatch.setattr(
        slide_analyzer, "prepare_presentation_slides", lambda *args, **kw: ([{"num": 1}], {})
    )
    monkeypatch.setattr(slide_analyzer, "analyze", Mock(side_effect=(
        slide_analyzer.SlideAnalysisGenerationError(
            "Temporarily busy", error_code="AI_PROVIDER_BUSY"
        )
    )))
    slide_analyzer.run_slide_analysis(presentation.id)
    assert presentation.status == ("completed" if slide_count else "failed")
    assert presentation.processing_error_code == "AI_PROVIDER_BUSY"
    assert job.error_code == "AI_PROVIDER_BUSY"
    assert job.status == "failed"


def test_retry_after_http_date_and_malformed_header():
    assert provider_requests._retry_seconds("Wed, 01 Jan 2020 00:00:00 GMT") == 1
    assert provider_requests._retry_seconds("invalid") is None
    assert provider_requests._retry_seconds(None) is None
