from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "ap_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks",
        "app.workers.rules_tasks",
        "app.workers.sla_tasks",
        "app.workers.email_ingestion",
        "app.workers.feedback_tasks",
        "app.workers.analytics_tasks",
    ],
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
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "check-sla-alerts-daily": {
        "task": "app.workers.sla_tasks.check_sla_alerts",
        "schedule": crontab(hour=9, minute=0),
    },
    "poll-ap-mailbox": {
        "task": "app.workers.email_ingestion.poll_ap_mailbox",
        "schedule": crontab(minute="*/5"),
    },
    "analyze-overrides-weekly": {
        "task": "app.workers.analytics_tasks.weekly_digest",
        "schedule": crontab(hour=0, minute=0, day_of_week="sun"),
    },
    "detect-recurring-patterns-weekly": {
        "task": "tasks.detect_recurring_patterns",
        "schedule": crontab(hour=2, minute=0, day_of_week="mon"),
    },
}
