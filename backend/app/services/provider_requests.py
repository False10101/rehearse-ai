"""Bounded OpenRouter retries, separate from retries for invalid model output."""

import logging
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import requests

logger = logging.getLogger(__name__)
MAX_RETRY_WAIT_SECONDS = 300


class ProviderRequestError(requests.HTTPError):
    def __init__(self, response, error_code, retry_after=None):
        messages = {
            "AI_PROVIDER_BUSY": (
                "The AI service is temporarily busy. Please try again in a few minutes."
            ),
            "AI_PROVIDER_CREDITS": (
                "The AI service has reached its credit or spending limit. "
                "Please contact the app owner."
            ),
            "AI_PROVIDER_UNAVAILABLE": (
                "The AI service is temporarily unavailable. Please try again later."
            ),
            "AI_PROVIDER_REQUEST_FAILED": (
                "The AI service could not accept this request. Please contact the app owner."
            ),
        }
        self.error_code = error_code
        self.retry_after = retry_after
        super().__init__(messages[error_code], response=response)


def _retry_seconds(value):
    if value is None:
        return None
    try:
        return max(1, int(value))
    except (ValueError, TypeError):
        try:
            date = parsedate_to_datetime(str(value))
            if date.tzinfo is None:
                date = date.replace(tzinfo=UTC)
            return max(1, int((date - datetime.now(UTC)).total_seconds()) + 1)
        except (ValueError, TypeError, OverflowError):
            return None


def post_provider_request(url, *, headers, json, timeout):
    for attempt in range(1, 4):
        response = requests.post(url, headers=headers, json=json, timeout=timeout)
        # Successful responses are decoded/validated by the calling feature.
        status = getattr(response, "status_code", 200)
        if status < 400:
            return response
        try:
            body = response.json()
        except ValueError:
            body = {}
        error = body.get("error", {}) if isinstance(body, dict) else {}
        metadata = error.get("metadata", {}) if isinstance(error, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        embedded_headers = metadata.get("headers", {})
        embedded_headers = embedded_headers if isinstance(embedded_headers, dict) else {}
        delay = _retry_seconds(
            response.headers.get("Retry-After") or embedded_headers.get("Retry-After")
        )
        temporary_budget = status == 402 and (
            metadata.get("limit_source") == "openrouter_in_flight_budget"
        )
        retryable = status in (429, 503) or (temporary_budget and delay is not None)
        code = (
            "AI_PROVIDER_BUSY" if temporary_budget or status == 429
            else "AI_PROVIDER_CREDITS" if status == 402
            else "AI_PROVIDER_UNAVAILABLE" if status == 503
            else "AI_PROVIDER_REQUEST_FAILED"
        )
        if retryable and delay is None:
            delay = attempt * 5
        safe_body = response.text
        token = headers.get("Authorization", "").removeprefix("Bearer ")
        if token:
            safe_body = safe_body.replace(token, "[REDACTED]")
        logger.error(
            "AI provider HTTP %s model=%s attempt=%s/3 code=%s retry_after=%s response=%s",
            status, json.get("model"), attempt, code, delay, safe_body,
        )
        if not retryable or attempt == 3 or delay > MAX_RETRY_WAIT_SECONDS:
            raise ProviderRequestError(response, code, delay)
        logger.warning(
            "AI provider retry scheduled model=%s wait_seconds=%s next_attempt=%s/3",
            json.get("model"), delay, attempt + 1,
        )
        time.sleep(delay)
    raise AssertionError("Provider retry loop did not return or raise")
