import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth import router as auth_router
from app.api.v1.live import router as live_router
from app.api.v1.practice import router as practice_router
from app.api.v1.presentations import router as presentations_router
from app.api.v1.transcripts import router as transcripts_router
from app.core.config import get_settings
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
