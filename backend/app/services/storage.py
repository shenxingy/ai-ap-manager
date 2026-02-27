"""MinIO object storage wrapper."""
import io
import logging
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Client singleton ───

def _build_client() -> Minio:
    return Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


_client: Minio | None = None


def get_client() -> Minio:
    global _client
    if _client is None:
        _client = _build_client()
    return _client


# ─── Bucket bootstrap ───

def ensure_bucket(bucket: str = settings.MINIO_BUCKET_NAME) -> None:
    """Create bucket if it does not already exist. Called on startup."""
    client = get_client()
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info("Created MinIO bucket: %s", bucket)
        else:
            logger.debug("MinIO bucket already exists: %s", bucket)
    except S3Error as exc:
        logger.error("Failed to ensure MinIO bucket %s: %s", bucket, exc)
        raise


# ─── Core operations ───

def upload_file(
    bucket: str,
    object_name: str,
    data: bytes | io.IOBase,
    content_type: str,
) -> str:
    """Upload bytes or file-like object to MinIO. Returns the object path."""
    client = get_client()

    if isinstance(data, bytes):
        stream = io.BytesIO(data)
        length = len(data)
    else:
        # Seek to end to get length, then back to start
        data.seek(0, 2)
        length = data.tell()
        data.seek(0)
        stream = data

    client.put_object(
        bucket_name=bucket,
        object_name=object_name,
        data=stream,
        length=length,
        content_type=content_type,
    )
    logger.info("Uploaded %s/%s (%d bytes)", bucket, object_name, length)
    return object_name


def get_presigned_url(
    bucket: str,
    object_name: str,
    expires_seconds: int = 3600,
) -> str:
    """Return a pre-signed GET URL valid for `expires_seconds`."""
    client = get_client()
    url = client.presigned_get_object(
        bucket_name=bucket,
        object_name=object_name,
        expires=timedelta(seconds=expires_seconds),
    )
    return url


def download_file(bucket: str, object_name: str) -> bytes:
    """Download an object and return its raw bytes."""
    client = get_client()
    response = client.get_object(bucket_name=bucket, object_name=object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_object(bucket: str, object_name: str) -> None:
    """Delete an object from MinIO."""
    client = get_client()
    client.remove_object(bucket_name=bucket, object_name=object_name)
    logger.info("Deleted %s/%s", bucket, object_name)
