"""Main FastAPI application entrypoint for SolfaLedger Engine."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from solfa_engine.config import settings
from solfa_engine.api.auth import router as auth_router
from solfa_engine.api.me import router as me_router
from solfa_engine.api.jobs import router as jobs_router
from solfa_engine.transcription.security import cleanup_expired_audio_files


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle events."""
    # Ensure local storage and upload directories exist
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.export_dir.mkdir(parents=True, exist_ok=True)

    # Initial housekeeping: cleanup expired audio files
    try:
        cleanup_expired_audio_files()
    except Exception:
        pass

    # Background task: periodically retry on-chain credit settlement for unbilled jobs
    import asyncio
    from solfa_engine.transcription.pipeline import retry_unbilled_jobs

    stop_event = asyncio.Event()

    async def periodic_settlement_retry():
        while not stop_event.is_set():
            try:
                await asyncio.sleep(60)
                await retry_unbilled_jobs()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    retry_task = asyncio.create_task(periodic_settlement_retry())

    yield

    stop_event.set()
    retry_task.cancel()
    try:
        await retry_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "SolfaLedger audio-to-tonic-solfa transcription API and Stellar Soroban integration service. "
        "Transcribes songs into movable-do tonic solfa notation (d r m f s l t d) with key, tempo, "
        "meter, and timing breakdown, secured by on-chain Soroban payments."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(auth_router)
app.include_router(me_router)
app.include_router(jobs_router)


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint for container probes and uptime monitors."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "network": settings.stellar_network,
    }
