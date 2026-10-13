import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

from app.api.v1.auth import router as auth_router
from app.api.v1.live import router as live_router
from app.api.v1.practice import router as practice_router
from app.api.v1.presentations import router as presentations_router
from app.api.v1.transcripts import router as transcripts_router
from app.core.config import get_settings
from app.core.request_logging import RequestLoggingMiddleware
from app.services.background_jobs import recover_interrupted_jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    cutoff = datetime.now(UTC)

    async def recover():
        while True:
            try:
                await asyncio.to_thread(recover_interrupted_jobs, cutoff)
                return
            except Exception:
                logging.getLogger(__name__).exception(
                    "Job recovery unavailable; retrying in 30 seconds"
                )
                await asyncio.sleep(30)

    recovery = asyncio.create_task(recover())
    try:
        yield
    finally:
        recovery.cancel()
        try:
            await recovery
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    app = FastAPI(
        lifespan=lifespan,
        title="Rehearse AI API",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    @app.exception_handler(HTTPException)
    async def log_http_error(request: Request, error: HTTPException):
        logging.getLogger(__name__).warning(
            "API rejection request_id=%s method=%s path=%s status=%s reason=%s",
            getattr(request.state, "request_id", "unknown"),
            request.method, request.url.path, error.status_code, error.detail,
        )
        return await http_exception_handler(request, error)

    @app.exception_handler(RequestValidationError)
    async def log_validation_error(request: Request, error: RequestValidationError):
        logging.getLogger(__name__).warning(
            "API validation failed request_id=%s method=%s path=%s fields=%s",
            getattr(request.state, "request_id", "unknown"),
            request.method, request.url.path,
            [(item["loc"], item["type"]) for item in error.errors()],
        )
        return await request_validation_exception_handler(request, error)
    app.include_router(auth_router)
    app.include_router(live_router)
    app.include_router(practice_router)
    app.include_router(presentations_router)
    app.include_router(transcripts_router)

    @app.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        return {"status": "ok", "environment": settings.app_env}

    return app


app = create_app()
