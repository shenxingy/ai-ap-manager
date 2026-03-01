"""ML Celery tasks — GL classifier retraining."""
import logging
import time

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
    from app.services.gl_classifier import train_model, save_model_to_minio, invalidate_cache

    db = _get_sync_session()
    try:
        model, accuracy = train_model(db)
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
        logger.info("GL classifier retrained: version=%d accuracy=%.3f key=%s", version, accuracy, key)
        return {"status": "ok", "accuracy": accuracy, "model_key": key}
    except Exception as e:
        logger.error("GL classifier retrain failed during save: %s", e)
        return {"status": "error", "reason": str(e)}
