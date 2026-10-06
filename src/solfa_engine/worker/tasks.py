"""Celery background tasks for SolfaLedger audio processing."""

import asyncio
import logging
from solfa_engine.worker.celery_app import celery_app
from solfa_engine.transcription.pipeline import run_transcription_worker, retry_unbilled_jobs

logger = logging.getLogger(__name__)


@celery_app.task(name="transcribe_audio_job", bind=True, max_retries=3)
def transcribe_audio_job(self, job_id: str) -> bool:
    """Execute audio transcription worker asynchronously in Celery worker process."""
    logger.info(f"Celery executing transcription task for job {job_id}")
    try:
        asyncio.run(run_transcription_worker(job_id))
        return True
    except Exception as exc:
        logger.exception(f"Celery task failed for job {job_id}: {exc}")
        raise self.retry(exc=exc, countdown=10)


@celery_app.task(name="retry_unbilled_settlements")
def retry_unbilled_settlements() -> int:
    """Periodic Celery Beat task to retry on-chain credit deductions for unbilled jobs."""
    logger.info("Executing periodic unbilled settlement retry task")
    return asyncio.run(retry_unbilled_jobs())
