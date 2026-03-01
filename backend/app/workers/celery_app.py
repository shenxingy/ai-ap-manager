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
        "app.workers.ml_tasks",
        "app.workers.retention_tasks",
        "app.workers.vendor_risk_tasks",
        "app.workers.fx_tasks",
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
    "escalate-overdue-approvals-daily": {
        "task": "app.workers.sla_tasks.escalate_overdue_approvals",
        "schedule": crontab(hour=9, minute=30),
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
        "task": "app.workers.tasks.detect_recurring_patterns",
        "schedule": crontab(hour=2, minute=0, day_of_week="mon"),
    },
    "expire-compliance-docs-weekly": {
        "task": "app.workers.sla_tasks.expire_compliance_docs",
        "schedule": crontab(hour=1, minute=0, day_of_week="mon"),
    },
    "gl-classifier-retrain-weekly": {
        "task": "retrain_gl_classifier",
        "schedule": crontab(hour=4, minute=0, day_of_week=6),  # Saturday 4 AM UTC
    },
    "data-retention-monthly": {
        "task": "run_data_retention",
        "schedule": crontab(day_of_month=1, hour=3, minute=0),
    },
    "vendor-risk-weekly": {
        "task": "vendor_risk.compute_vendor_risk_scores",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),  # Sunday 2 AM
    },
    "fetch-fx-rates": {
        "task": "app.workers.fx_tasks.fetch_fx_rates",
        "schedule": crontab(hour=6, minute=0),
    },
}
