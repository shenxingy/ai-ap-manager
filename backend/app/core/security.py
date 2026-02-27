import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── Password ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ─── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(
        {"sub": subject, "role": role, "exp": expire, "type": "access"},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    return jwt.encode(
        {"sub": subject, "exp": expire, "type": "refresh"},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    """Raises JWTError on invalid/expired token."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


# ─── Email Approval Tokens ────────────────────────────────────────────────────

def create_approval_token(task_id: str, action: str) -> tuple[str, str]:
    """
    Returns (raw_token, token_hash).
    raw_token is sent in email URL; token_hash is stored in DB.
    action: 'approve' | 'reject'
    """
    raw = f"{task_id}:{action}:{uuid.uuid4()}"
    token_hash = hmac.new(
        settings.APPROVAL_TOKEN_SECRET.encode(),
        raw.encode(),
        hashlib.sha256,
    ).hexdigest()
    return raw, token_hash


def verify_approval_token(raw_token: str, stored_hash: str) -> bool:
    expected = hmac.new(
        settings.APPROVAL_TOKEN_SECRET.encode(),
        raw_token.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, stored_hash)
