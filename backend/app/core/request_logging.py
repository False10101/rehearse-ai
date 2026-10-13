"""Request diagnostics without logging headers, bodies, or URL queries."""

import logging
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.monotonic()
        status = None

        async def logged_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", request_id.encode())
                ]
            await send(message)

        try:
            await self.app(scope, receive, logged_send)
        except Exception:
            logger.exception(
                "API exception request_id=%s method=%s path=%s response_status=%s",
                request_id, scope["method"], scope["path"], status,
            )
            raise
        else:
            if status is not None and status >= 400:
                logger.warning(
                    "API request failed request_id=%s method=%s path=%s status=%s duration_ms=%s",
                    request_id, scope["method"], scope["path"], status,
                    round((time.monotonic() - started) * 1000),
                )
