import uuid
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """Validate JWT and return the User ORM object."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exc
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    from app.models.user import User
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exc
    return user


def require_role(*roles: str):
    """Dependency factory — raises 403 if user role not in allowed list."""
    async def check(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not permitted for this action.",
            )
        return user
    return check


async def get_current_vendor_id(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> uuid.UUID:
    """Validate a vendor portal JWT and return the vendor_id.

    Vendor tokens have type='vendor_portal' and a 'vendor_id' claim.
    They are issued via POST /portal/auth/invite (ADMIN-only).
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate vendor credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "vendor_portal":
            raise credentials_exc
        vendor_id_str: str | None = payload.get("vendor_id")
        if not vendor_id_str:
            raise credentials_exc
        return UUID(vendor_id_str)
    except (JWTError, ValueError):
        raise credentials_exc
