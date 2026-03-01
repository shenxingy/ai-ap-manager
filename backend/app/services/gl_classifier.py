"""GL Coding ML Classifier — TF-IDF + Logistic Regression on confirmed GL assignments.

Trained on approved invoice lines with confirmed gl_account values.
Model persisted to MinIO. Loaded lazily and cached in-process.
"""
# ─── Imports ───
import io
import logging
from typing import Optional, Tuple

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer

from app.core.config import settings

logger = logging.getLogger(__name__)

MIN_TRAINING_SAMPLES = 20
MODEL_PREFIX = "models/gl-coding-v"
BUCKET = settings.MINIO_BUCKET_NAME

# In-memory cache: (model, version)
_cached_model: Optional[Tuple[Pipeline, int]] = None


# ─── Train ───

def train_model(db) -> Tuple[Pipeline, float, int]:
    """Train TF-IDF + LogisticRegression on confirmed GL assignments.

    Queries invoice_line_items joined to invoices + vendors where
    gl_account IS NOT NULL. Feature: "{vendor_name} {description}".
    Label: gl_account.

    Raises ValueError if < MIN_TRAINING_SAMPLES training samples.
    Returns (pipeline, accuracy, sample_count).
    """
    from sqlalchemy import select, text
    from app.models.invoice import Invoice, InvoiceLineItem
    from app.models.vendor import Vendor

    stmt = (
        select(
            InvoiceLineItem.description,
            InvoiceLineItem.gl_account,
            Vendor.name.label("vendor_name"),
        )
        .join(Invoice, Invoice.id == InvoiceLineItem.invoice_id)
        .outerjoin(Vendor, Vendor.id == Invoice.vendor_id)
        .where(
            InvoiceLineItem.gl_account.isnot(None),
            Invoice.deleted_at.is_(None),
        )
    )

    rows = db.execute(stmt).fetchall()

    if len(rows) < MIN_TRAINING_SAMPLES:
        raise ValueError(
            f"Not enough training samples: {len(rows)} < {MIN_TRAINING_SAMPLES}"
        )

    features = [
        f"{row.vendor_name or ''} {row.description or ''}".strip()
        for row in rows
    ]
    labels = [row.gl_account for row in rows]

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=5000,
            sublinear_tf=True,
        )),
        ("clf", LogisticRegression(
            max_iter=500,
            C=1.0,
            class_weight="balanced",
        )),
    ])

    from sklearn.model_selection import cross_val_score
    import numpy as np

    # Cross-validate only if enough samples per class; otherwise just fit
    unique_labels = list(set(labels))
    if len(unique_labels) >= 2 and len(rows) >= 30:
        cv_folds = min(5, len(rows) // len(unique_labels))
        cv_folds = max(2, cv_folds)
        try:
            scores = cross_val_score(pipeline, features, labels, cv=cv_folds, scoring="accuracy")
            accuracy = float(np.mean(scores))
        except Exception:
            accuracy = 0.0
    else:
        accuracy = 0.0

    pipeline.fit(features, labels)
    logger.info("GL classifier trained on %d samples, cv_accuracy=%.3f", len(rows), accuracy)
    return pipeline, accuracy, len(rows)


# ─── Save to MinIO ───

def save_model_to_minio(model: Pipeline, version: int) -> str:
    """Serialize model with joblib, upload to MinIO as models/gl-coding-v{version}.pkl.

    Returns the object key.
    """
    from app.services.storage import get_client

    buf = io.BytesIO()
    joblib.dump(model, buf)
    buf.seek(0)
    model_bytes = buf.read()

    object_key = f"{MODEL_PREFIX}{version}.pkl"
    client = get_client()
    client.put_object(
        bucket_name=BUCKET,
        object_name=object_key,
        data=io.BytesIO(model_bytes),
        length=len(model_bytes),
        content_type="application/octet-stream",
    )
    logger.info("Saved GL classifier model to MinIO: %s", object_key)
    return object_key


# ─── Load from MinIO ───

def load_latest_model() -> Tuple[Optional[Pipeline], Optional[int]]:
    """Download latest gl-coding-v*.pkl from MinIO. Cache in-process.

    Returns (model, version) or (None, None) if no model exists.
    """
    global _cached_model

    if _cached_model is not None:
        return _cached_model

    from app.services.storage import get_client

    client = get_client()

    try:
        objects = list(client.list_objects(BUCKET, prefix=MODEL_PREFIX))
    except Exception as exc:
        logger.warning("Cannot list GL classifier models from MinIO: %s", exc)
        return None, None

    if not objects:
        logger.info("No GL classifier model found in MinIO (prefix=%s)", MODEL_PREFIX)
        return None, None

    # Pick the one with the highest version (largest timestamp suffix)
    def _version(obj) -> int:
        name = obj.object_name  # e.g. models/gl-coding-v1709123456.pkl
        stem = name.rsplit(".", 1)[0]  # strip .pkl
        suffix = stem[len(MODEL_PREFIX):]  # strip prefix
        try:
            return int(suffix)
        except ValueError:
            return 0

    latest_obj = max(objects, key=_version)
    version = _version(latest_obj)

    try:
        model_bytes = _download_object(client, BUCKET, latest_obj.object_name)
        model: Pipeline = joblib.load(io.BytesIO(model_bytes))
        _cached_model = (model, version)
        logger.info("Loaded GL classifier model %s (version=%d)", latest_obj.object_name, version)
        return _cached_model
    except Exception as exc:
        logger.error("Failed to load GL classifier model from MinIO: %s", exc)
        return None, None


def _download_object(client, bucket: str, object_name: str) -> bytes:
    response = client.get_object(bucket_name=bucket, object_name=object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


# ─── Predict ───

def predict_gl_account(
    vendor_name: str,
    description: str,
    amount: float,  # noqa: ARG001 — reserved for future amount-aware features
) -> Tuple[Optional[str], float]:
    """Returns (account_code, confidence) or (None, 0.0) if no model loaded."""
    model, version = load_latest_model()
    if model is None:
        return None, 0.0

    feature = f"{vendor_name} {description}".strip()
    try:
        proba = model.predict_proba([feature])[0]
        confidence = float(proba.max())
        account = model.classes_[proba.argmax()]
        return account, confidence
    except Exception as exc:
        logger.warning("GL classifier predict failed: %s", exc)
        return None, 0.0


def invalidate_cache() -> None:
    """Clear the in-process model cache (call after retraining)."""
    global _cached_model
    _cached_model = None
