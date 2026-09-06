import asyncio

from celery import Celery

from .config import get_settings
from .database import SessionLocal
from .models import EvaluationRun
from .services.evaluation import EvaluationService
from .services.ingestion import ingest_document

settings = get_settings()
celery_app = Celery("coach", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_track_started=True, task_acks_late=True, worker_prefetch_multiplier=1)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def ingest_document_task(self, document_id: str):
    with SessionLocal() as db:
        return asyncio.run(ingest_document(db, document_id))


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def evaluation_task(self, evaluation_id: str):
    with SessionLocal() as db:
        evaluation = db.get(EvaluationRun, evaluation_id)
        if evaluation:
            asyncio.run(EvaluationService(db).run(evaluation))
