"""Approval workflow API endpoints.

In-app endpoints (JWT required):
  GET  /approvals              — list pending tasks for current user
  GET  /approvals/{task_id}    — task detail with invoice summary
  POST /approvals/{task_id}/approve
  POST /approvals/{task_id}/reject

Email token endpoint (no auth):
  GET  /approvals/email?token=<raw_token>
"""
import logging
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.deps import get_current_user, require_role
from app.schemas.approval import (
    ApprovalDecisionRequest,
    ApprovalListResponse,
    ApprovalTaskOut,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Sync session factory for approval service calls ───

def _get_sync_session() -> Session:
    """Create a one-off sync session for approval service calls.

    The approval service uses sync SQLAlchemy (shared with Celery tasks).
    API handlers create a fresh engine+session per request.
    """
    engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return SessionLocal()


# ─── In-app: list pending tasks ───

@router.get(
    "",
    response_model=ApprovalListResponse,
    summary="List pending approval tasks for the current user",
)
async def list_my_approvals(
    include_resolved: bool = Query(False, description="If true, return resolved (approved/rejected) tasks instead of pending"),
    current_user=Depends(require_role("APPROVER", "ADMIN")),
):
    """Return pending or resolved ApprovalTasks assigned to the authenticated user."""
    from app.services.approval import get_pending_tasks_for_approver, get_resolved_tasks_for_approver
    from app.models.invoice import Invoice

    db = _get_sync_session()
    try:
        if include_resolved:
            tasks = get_resolved_tasks_for_approver(db, current_user.id)
        else:
            tasks = get_pending_tasks_for_approver(db, current_user.id)
        items: list[ApprovalTaskOut] = []
        for task in tasks:
            invoice = db.execute(
                select(Invoice).where(Invoice.id == task.invoice_id)
            ).scalars().first()

            out = ApprovalTaskOut.model_validate(task)
            if invoice:
                out.invoice_number = invoice.invoice_number
                out.vendor_name_raw = invoice.vendor_name_raw
                out.total_amount = (
                    Decimal(str(invoice.total_amount)) if invoice.total_amount else None
                )
            items.append(out)

        return ApprovalListResponse(items=items, total=len(items))
    finally:
        db.close()


# ─── In-app: task detail ───

@router.get(
    "/{task_id}",
    response_model=ApprovalTaskOut,
    summary="Get approval task detail with invoice summary",
)
async def get_approval_task(
    task_id: uuid.UUID,
    current_user=Depends(require_role("APPROVER", "ADMIN")),
):
    """Return a single ApprovalTask (with invoice summary) for the current user."""
    from app.models.approval import ApprovalTask
    from app.models.invoice import Invoice

    db = _get_sync_session()
    try:
        task = db.execute(
            select(ApprovalTask).where(ApprovalTask.id == task_id)
        ).scalars().first()

        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

        # Ensure the requester is the assigned approver (or ADMIN)
        if str(task.approver_id) != str(current_user.id) and current_user.role != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not the assigned approver for this task.",
            )

        invoice = db.execute(
            select(Invoice).where(Invoice.id == task.invoice_id)
        ).scalars().first()

        out = ApprovalTaskOut.model_validate(task)
        if invoice:
            out.invoice_number = invoice.invoice_number
            out.vendor_name_raw = invoice.vendor_name_raw
            out.total_amount = (
                Decimal(str(invoice.total_amount)) if invoice.total_amount else None
            )
        return out
    finally:
        db.close()


# ─── In-app: approve ───

@router.post(
    "/{task_id}/approve",
    response_model=ApprovalTaskOut,
    summary="Approve an invoice (in-app, JWT required)",
)
async def approve_task(
    task_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    current_user=Depends(require_role("APPROVER", "ADMIN")),
):
    from app.services.approval import process_approval_decision
    from app.models.invoice import Invoice

    db = _get_sync_session()
    try:
        try:
            task = process_approval_decision(
                db=db,
                task_id=task_id,
                action="approve",
                actor_id=current_user.id,
                channel="web",
                notes=body.notes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

        invoice = db.execute(
            select(Invoice).where(Invoice.id == task.invoice_id)
        ).scalars().first()

        out = ApprovalTaskOut.model_validate(task)
        if invoice:
            out.invoice_number = invoice.invoice_number
            out.vendor_name_raw = invoice.vendor_name_raw
            out.total_amount = (
                Decimal(str(invoice.total_amount)) if invoice.total_amount else None
            )
        return out
    finally:
        db.close()


# ─── In-app: reject ───

@router.post(
    "/{task_id}/reject",
    response_model=ApprovalTaskOut,
    summary="Reject an invoice (in-app, JWT required)",
)
async def reject_task(
    task_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    current_user=Depends(require_role("APPROVER", "ADMIN")),
):
    from app.services.approval import process_approval_decision
    from app.models.invoice import Invoice

    db = _get_sync_session()
    try:
        try:
            task = process_approval_decision(
                db=db,
                task_id=task_id,
                action="reject",
                actor_id=current_user.id,
                channel="web",
                notes=body.notes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

        invoice = db.execute(
            select(Invoice).where(Invoice.id == task.invoice_id)
        ).scalars().first()

        out = ApprovalTaskOut.model_validate(task)
        if invoice:
            out.invoice_number = invoice.invoice_number
            out.vendor_name_raw = invoice.vendor_name_raw
            out.total_amount = (
                Decimal(str(invoice.total_amount)) if invoice.total_amount else None
            )
        return out
    finally:
        db.close()


# ─── Email token: approve or reject without login ───

@router.get(
    "/email",
    response_class=HTMLResponse,
    summary="Email-token approval/rejection (no auth required)",
)
async def email_token_decision(
    token: str = Query(..., description="Raw HMAC approval token from email link"),
):
    """Handle one-click Approve/Reject from email link.

    Token format: "{task_id}:{action}:{uuid4}"
    No JWT required — the token is the authenticator.
    Returns a simple HTML confirmation page.
    """
    from app.services.approval import process_approval_decision

    # Parse token: task_id:action:uuid
    parts = token.split(":")
    if len(parts) < 3:
        return HTMLResponse(
            content=_html_page(
                "Invalid Token",
                "The approval link is malformed. Please contact your AP team.",
                success=False,
            ),
            status_code=400,
        )

    task_id_str = parts[0]
    action = parts[1]

    try:
        task_id = uuid.UUID(task_id_str)
    except ValueError:
        return HTMLResponse(
            content=_html_page(
                "Invalid Token",
                "The approval link contains an invalid task ID.",
                success=False,
            ),
            status_code=400,
        )

    if action not in ("approve", "reject"):
        return HTMLResponse(
            content=_html_page(
                "Invalid Action",
                f"Unknown action '{action}'. Expected 'approve' or 'reject'.",
                success=False,
            ),
            status_code=400,
        )

    db = _get_sync_session()
    try:
        try:
            process_approval_decision(
                db=db,
                task_id=task_id,
                action=action,
                token_raw=token,
                channel="email",
            )
        except ValueError as exc:
            error_msg = str(exc)
            return HTMLResponse(
                content=_html_page("Action Failed", error_msg, success=False),
                status_code=400,
            )

        action_label = "Approved" if action == "approve" else "Rejected"
        return HTMLResponse(
            content=_html_page(
                f"Invoice {action_label}",
                f"Thank you. The invoice has been {action_label.lower()} successfully. "
                "You may close this window.",
                success=True,
            ),
            status_code=200,
        )
    finally:
        db.close()


# ─── HTML helper ───

def _html_page(title: str, message: str, success: bool) -> str:
    color = "#2ecc71" if success else "#e74c3c"
    icon = "✓" if success else "✗"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            display: flex; align-items: center; justify-content: center;
            min-height: 100vh; margin: 0; background: #f5f5f5; }}
    .card {{ background: white; border-radius: 8px; padding: 40px 48px;
             box-shadow: 0 2px 12px rgba(0,0,0,0.08); text-align: center;
             max-width: 420px; width: 90%; }}
    .icon {{ font-size: 48px; color: {color}; margin-bottom: 16px; }}
    h1 {{ margin: 0 0 12px; font-size: 24px; color: #1a1a1a; }}
    p {{ color: #555; font-size: 16px; line-height: 1.5; margin: 0; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>{title}</h1>
    <p>{message}</p>
  </div>
</body>
</html>"""
