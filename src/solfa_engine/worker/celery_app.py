"""Celery application configuration for asynchronous audio transcription tasks."""

from celery import Celery
from solfa_engine.config import settings

celery_app = Celery(
    "solfa_engine",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["solfa_engine.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)
