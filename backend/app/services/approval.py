"""Approval task lifecycle service.

All functions accept a sync SQLAlchemy Session — safe to call from
Celery tasks (which cannot use async sessions).
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_approval_token, verify_approval_token
from app.services import audit as audit_svc

logger = logging.getLogger(__name__)


# ─── Create approval task ───

def create_approval_task(
    db: Session,
    invoice_id: uuid.UUID,
    approver_id: uuid.UUID,
    step_order: int = 1,
    due_hours: int = 48,
) -> "ApprovalTask":
    """Create an ApprovalTask with two one-time tokens (approve + reject).

    Generates approve and reject ApprovalToken rows, logs to audit,
    then fires the mock email notification.

    Returns the created ApprovalTask ORM object.
    """
    from app.models.approval import ApprovalTask, ApprovalToken
    from app.models.invoice import Invoice
    from app.models.user import User
    from app.services import email as email_svc

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=due_hours)

    # Create the approval task
    task = ApprovalTask(
        invoice_id=invoice_id,
        approver_id=approver_id,
        step_order=step_order,
        status="pending",
        due_at=expires_at,
    )
    db.add(task)
    db.flush()  # get task.id before creating tokens

    # Generate approve + reject tokens
    raw_tokens: dict[str, str] = {}
    for action in ("approve", "reject"):
        raw_token, token_hash = create_approval_token(str(task.id), action)
        token_row = ApprovalToken(
            task_id=task.id,
            token_hash=token_hash,
            action=action,
            expires_at=expires_at,
        )
        db.add(token_row)
        raw_tokens[action] = raw_token

    db.flush()

    # Audit log
    audit_svc.log(
        db=db,
        action="approval_task_created",
        entity_type="approval_task",
        entity_id=task.id,
        actor_id=None,
        after={
            "task_id": str(task.id),
            "invoice_id": str(invoice_id),
            "approver_id": str(approver_id),
            "step_order": step_order,
            "due_at": expires_at.isoformat(),
        },
        notes="Approval task created automatically after match",
    )

    db.commit()

    # Send email notification (console mock in MVP)
    invoice = db.execute(
        select(Invoice).where(Invoice.id == invoice_id)
    ).scalars().first()

    base_url = settings.APP_BASE_URL.rstrip("/")
    approve_url = f"{base_url}/api/v1/approvals/email?token={raw_tokens['approve']}"
    reject_url = f"{base_url}/api/v1/approvals/email?token={raw_tokens['reject']}"

    if invoice:
        email_svc.send_approval_request_email(
            task=task,
            invoice=invoice,
            approve_url=approve_url,
            reject_url=reject_url,
        )
    else:
        logger.warning("Invoice %s not found when sending approval email.", invoice_id)

    return task


# ─── Process approval decision ───

def process_approval_decision(
    db: Session,
    task_id: uuid.UUID,
    action: str,
    actor_id: uuid.UUID | None = None,
    token_raw: str | None = None,
    channel: str = "web",
    notes: str | None = None,
) -> "ApprovalTask":
    """Apply an approve or reject decision to an ApprovalTask.

    Args:
        db: Sync SQLAlchemy session.
        task_id: UUID of the ApprovalTask to act on.
        action: "approve" or "reject".
        actor_id: User ID (required for channel="web").
        token_raw: Raw email token string (required for channel="email").
        channel: "web" (JWT auth) or "email" (token auth).
        notes: Optional decision notes.

    Returns:
        The updated ApprovalTask ORM object.

    Raises:
        ValueError: On invalid task state, bad token, or auth failure.
    """
    from app.models.approval import ApprovalTask, ApprovalToken
    from app.models.invoice import Invoice

    if action not in ("approve", "reject"):
        raise ValueError(f"Invalid action '{action}'. Must be 'approve' or 'reject'.")

    # Load task
    task = db.execute(
        select(ApprovalTask).where(ApprovalTask.id == task_id)
    ).scalars().first()
    if task is None:
        raise ValueError(f"ApprovalTask {task_id} not found.")

    if task.status != "pending":
        raise ValueError(
            f"ApprovalTask {task_id} is already decided (status={task.status})."
        )

    now = datetime.now(timezone.utc)

    if channel == "email":
        # Validate raw token against stored hash
        if not token_raw:
            raise ValueError("Email channel requires token_raw.")

        # Find the matching token by looking up the hash
        raw_token_hash = _compute_token_hash(token_raw)
        token_row = db.execute(
            select(ApprovalToken).where(
                ApprovalToken.task_id == task_id,
                ApprovalToken.token_hash == raw_token_hash,
                ApprovalToken.action == action,
            )
        ).scalars().first()

        if token_row is None:
            raise ValueError("Invalid token: no matching token found for this task/action.")

        if not verify_approval_token(token_raw, token_row.token_hash):
            raise ValueError("Invalid token: HMAC verification failed.")

        if token_row.is_used:
            raise ValueError("Token has already been used.")

        if token_row.expires_at < now:
            raise ValueError("Token has expired.")

        # Mark token as used
        token_row.is_used = True
        token_row.used_at = now
        db.flush()

    elif channel == "web":
        # Validate actor has APPROVER role and is the assigned approver
        if actor_id is None:
            raise ValueError("Web channel requires actor_id.")
        if str(actor_id) != str(task.approver_id):
            # Allow ADMIN to override
            from app.models.user import User
            actor = db.execute(
                select(User).where(User.id == actor_id)
            ).scalars().first()
            if actor is None or actor.role not in ("APPROVER", "ADMIN"):
                raise ValueError(
                    "Actor is not the assigned approver for this task."
                )
    else:
        raise ValueError(f"Unknown channel '{channel}'.")

    # Load invoice for snapshot
    invoice = db.execute(
        select(Invoice).where(Invoice.id == task.invoice_id)
    ).scalars().first()
    if invoice is None:
        raise ValueError(f"Invoice {task.invoice_id} not found.")

    before_snapshot = {
        "invoice_status": invoice.status,
        "task_status": task.status,
    }

    # Apply decision
    new_task_status = "approved" if action == "approve" else "rejected"
    new_invoice_status = "approved" if action == "approve" else "rejected"

    task.status = new_task_status
    task.decided_at = now
    task.decision_channel = channel
    if notes:
        task.notes = notes

    invoice.status = new_invoice_status
    db.flush()

    after_snapshot = {
        "invoice_status": invoice.status,
        "task_status": task.status,
        "decision_channel": channel,
        "actor_id": str(actor_id) if actor_id else None,
    }

    audit_action = "invoice_approved" if action == "approve" else "invoice_rejected"
    audit_svc.log(
        db=db,
        action=audit_action,
        entity_type="invoice",
        entity_id=invoice.id,
        actor_id=actor_id,
        before=before_snapshot,
        after=after_snapshot,
        notes=f"Decision via {channel} channel. Notes: {notes}",
    )

    db.commit()

    logger.info(
        "Approval decision: task=%s action=%s channel=%s invoice=%s",
        task_id, action, channel, invoice.id,
    )

    return task


# ─── List pending tasks for approver ───

def get_pending_tasks_for_approver(db: Session, approver_id: uuid.UUID) -> list:
    """Return all pending ApprovalTasks assigned to the given approver."""
    from app.models.approval import ApprovalTask

    stmt = select(ApprovalTask).where(
        ApprovalTask.approver_id == approver_id,
        ApprovalTask.status == "pending",
    ).order_by(ApprovalTask.due_at.asc())

    return list(db.execute(stmt).scalars().all())


# ─── Auto-create approval task after match ───

def auto_create_approval_task(db: Session, invoice_id: uuid.UUID) -> "ApprovalTask | None":
    """Create an approval task for the first APPROVER user found.

    Called after match succeeds but the invoice total exceeds the auto-approve
    threshold (i.e., the invoice is NOT auto-approved).

    Returns None if no user with role=APPROVER is found in the DB.
    """
    from app.models.user import User

    approver = db.execute(
        select(User).where(
            User.role == "APPROVER",
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    ).scalars().first()

    if approver is None:
        logger.warning(
            "auto_create_approval_task: no active APPROVER user found for invoice %s. "
            "Approval task NOT created.",
            invoice_id,
        )
        return None

    logger.info(
        "auto_create_approval_task: creating task for invoice=%s approver=%s",
        invoice_id, approver.id,
    )

    return create_approval_task(
        db=db,
        invoice_id=invoice_id,
        approver_id=approver.id,
        step_order=1,
        due_hours=settings.APPROVAL_TOKEN_EXPIRE_HOURS,
    )


# ─── Internal helper ───

def _compute_token_hash(raw_token: str) -> str:
    """Recompute the HMAC-SHA256 hash of a raw token string."""
    import hashlib
    import hmac
    return hmac.new(
        settings.APPROVAL_TOKEN_SECRET.encode(),
        raw_token.encode(),
        hashlib.sha256,
    ).hexdigest()
