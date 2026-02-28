from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.session import get_session
from app.models.user import User
from app.schemas.auth import Token, UserOut
from app.services import audit as audit_svc

router = APIRouter()


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(User).where(User.email == form.username, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    token = create_access_token(subject=str(user.id), role=user.role)

    # Log user login for SOC2 compliance
    audit_svc.log(
        db,
        action="user_login",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        actor_email=user.email,
        after={"email": user.email, "role": user.role},
        notes=f"Login from IP {request.client.host if request.client else 'unknown'}",
    )
    await db.flush()

    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
