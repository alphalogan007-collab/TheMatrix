"""Celery worker entry-point.

Tasks:
- process_knowledge_embedding: embed a KnowledgePattern chunk via embedding provider
- export_training_feedback: export feedback JSONL for offline training

Run with:
    celery -A app.worker worker --loglevel=info
"""

from __future__ import annotations

import asyncio

import structlog
from celery import Celery

from app.config import get_settings

settings = get_settings()
logger = structlog.get_logger(__name__)

celery_app = Celery(
    "mindai",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="mindai.embed_knowledge_pattern", bind=True, max_retries=3)
def embed_knowledge_pattern(self, pattern_id: str) -> dict:
    """Embed a knowledge pattern chunk and store the vector in pgvector."""
    try:
        # TODO: implement async DB lookup + embedding provider call
        logger.info("embed_knowledge_pattern.start", pattern_id=pattern_id)
        return {"status": "ok", "pattern_id": pattern_id}
    except Exception as exc:
        logger.error("embed_knowledge_pattern.error", pattern_id=pattern_id, error=str(exc))
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="mindai.export_training_feedback", bind=True)
def export_training_feedback(self, since_iso: str | None = None) -> dict:
    """Export feedback JSONL for training pipeline."""
    try:
        logger.info("export_training_feedback.start", since=since_iso)
        from app.services.training_pipeline import export_feedback_jsonl
        filepath = export_feedback_jsonl(feedback_records=[], output_dir="/tmp/mindai_training")
        return {"status": "ok", "filepath": filepath}
    except Exception as exc:
        logger.error("export_training_feedback.error", error=str(exc))
        raise
