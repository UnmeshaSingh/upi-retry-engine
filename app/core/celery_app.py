from celery import Celery
from app.core.config import settings

# Create Celery app using Redis as both broker and backend
celery_app = Celery(
    "upi_retry_engine",
    broker=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/1",
    backend=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/2",
    include=["app.tasks.db_tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.tasks.db_tasks.save_payment_async": {"queue": "db_writes"},
        "app.tasks.db_tasks.save_retry_async":   {"queue": "db_writes"},
    }
)