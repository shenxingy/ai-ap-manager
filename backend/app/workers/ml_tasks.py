"""ML Celery tasks — GL classifier retraining."""
import io
import json
import logging
import time
from datetime import UTC, datetime

from celery import shared_task

logger = logging.getLogger(__name__)


def _get_sync_session():
    """Return a sync SQLAlchemy session. Caller must close it."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings

    engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return Session()


@shared_task(name="retrain_gl_classifier")
def retrain_gl_classifier() -> dict:
    """Retrain the GL coding ML classifier on current approved invoice data.

    Saves the new model to MinIO and invalidates the in-process cache.
    Returns a status dict with accuracy and model key on success.
    """
    from app.services.gl_classifier import invalidate_cache, save_model_to_minio, train_model

    db = _get_sync_session()
    try:
        model, accuracy, training_samples = train_model(db)
    except ValueError as e:
        logger.info("GL classifier retrain skipped: %s", e)
        return {"status": "skipped", "reason": str(e)}
    except Exception as e:
        logger.error("GL classifier retrain failed during training: %s", e)
        return {"status": "error", "reason": str(e)}
    finally:
        db.close()

    try:
        version = int(time.time())
        key = save_model_to_minio(model, version)
        invalidate_cache()  # force next request to reload from MinIO

        # Write JSON sidecar so the status API can report model metadata without
        # having to list and parse all model objects.
        from app.core.config import settings
        from app.services.storage import get_client

        sidecar = {
            "version": str(version),
            "accuracy": accuracy,
            "trained_at": datetime.now(UTC).isoformat(),
            "training_samples": training_samples,
        }
        sidecar_bytes = json.dumps(sidecar).encode()
        minio_client = get_client()
        minio_client.put_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name="models/gl-coding-latest.json",
            data=io.BytesIO(sidecar_bytes),
            length=len(sidecar_bytes),
            content_type="application/json",
        )
        logger.info("GL classifier retrained: version=%d accuracy=%.3f key=%s", version, accuracy, key)
        return {"status": "ok", "accuracy": accuracy, "model_key": key}
    except Exception as e:
        logger.error("GL classifier retrain failed during save: %s", e)
        return {"status": "error", "reason": str(e)}
