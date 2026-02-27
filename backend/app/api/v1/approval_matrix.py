"""Approval matrix and user delegation API endpoints."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.db.session import get_session
from app.models.approval_matrix import ApprovalMatrixRule, UserDelegation
from app.models.user import User
from app.schemas.approval_matrix import (
    ApprovalMatrixRuleIn,
    ApprovalMatrixRuleOut,
    ApprovalMatrixRuleUpdate,
    UserDelegationIn,
    UserDelegationOut,
)

router = APIRouter()

# ─── Approval Matrix Rules ───

@router.get(
    "",
    response_model=list[ApprovalMatrixRuleOut],
    summary="List all active approval matrix rules (ADMIN)",
)
async def list_rules(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    result = await db.execute(
        select(ApprovalMatrixRule)
        .where(ApprovalMatrixRule.is_active.is_(True))
        .order_by(ApprovalMatrixRule.step_order, ApprovalMatrixRule.amount_min)
    )
    return [ApprovalMatrixRuleOut.model_validate(r) for r in result.scalars().all()]


@router.post(
    "",
    response_model=ApprovalMatrixRuleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an approval matrix rule (ADMIN)",
)
async def create_rule(
    body: ApprovalMatrixRuleIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    rule = ApprovalMatrixRule(**body.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return ApprovalMatrixRuleOut.model_validate(rule)


@router.put(
    "/{rule_id}",
    response_model=ApprovalMatrixRuleOut,
    summary="Update an approval matrix rule (ADMIN)",
)
async def update_rule(
    rule_id: uuid.UUID,
    body: ApprovalMatrixRuleUpdate,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    result = await db.execute(
        select(ApprovalMatrixRule).where(ApprovalMatrixRule.id == rule_id)
    )
    rule = result.scalars().first()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)

    await db.commit()
    await db.refresh(rule)
    return ApprovalMatrixRuleOut.model_validate(rule)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete an approval matrix rule (ADMIN)",
)
async def delete_rule(
    rule_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    result = await db.execute(
        select(ApprovalMatrixRule).where(ApprovalMatrixRule.id == rule_id)
    )
    rule = result.scalars().first()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")

    rule.is_active = False
    await db.commit()


# ─── User Delegation sub-router ───

delegation_router = APIRouter()


@delegation_router.put(
    "/{user_id}/delegation",
    response_model=UserDelegationOut,
    summary="Set or update delegation for a user (APPROVER or ADMIN)",
)
async def set_delegation(
    user_id: uuid.UUID,
    body: UserDelegationIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("APPROVER", "ADMIN"))],
):
    # Only ADMIN can set delegation for any user; APPROVER can only set for themselves
    if current_user.role == "APPROVER" and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="APPROVER can only set delegation for themselves.",
        )

    # Deactivate any existing active delegation for this delegator
    existing_result = await db.execute(
        select(UserDelegation).where(
            UserDelegation.delegator_id == user_id,
            UserDelegation.is_active.is_(True),
        )
    )
    for existing in existing_result.scalars().all():
        existing.is_active = False

    delegation = UserDelegation(
        delegator_id=user_id,
        delegate_id=body.delegate_id,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        is_active=True,
    )
    db.add(delegation)
    await db.commit()
    await db.refresh(delegation)
    return UserDelegationOut.model_validate(delegation)


@delegation_router.delete(
    "/{user_id}/delegation",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove active delegation for a user (APPROVER or ADMIN)",
)
async def remove_delegation(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("APPROVER", "ADMIN"))],
):
    if current_user.role == "APPROVER" and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="APPROVER can only remove their own delegation.",
        )

    result = await db.execute(
        select(UserDelegation).where(
            UserDelegation.delegator_id == user_id,
            UserDelegation.is_active.is_(True),
        )
    )
    delegations = result.scalars().all()
    if not delegations:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active delegation found.")

    for d in delegations:
        d.is_active = False
    await db.commit()
