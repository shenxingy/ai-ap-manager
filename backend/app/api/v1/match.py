"""Match result endpoints — GET match result and POST trigger re-match."""
import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, require_role
from app.db.session import get_session
from app.models.invoice import Invoice
from app.models.matching import MatchResult, LineItemMatch
from app.models.user import User
from app.schemas.match import MatchResultOut, MatchTriggerResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── GET /invoices/{invoice_id}/match ───

@router.get(
    "/{invoice_id}/match",
    response_model=MatchResultOut,
    summary="Get match result for an invoice",
)
async def get_match_result(
    invoice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Return the MatchResult with LineItemMatches for the given invoice."""
    # Verify invoice exists
    inv_result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    )
    invoice = inv_result.scalars().first()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    # Load match result with line matches
    stmt = (
        select(MatchResult)
        .where(MatchResult.invoice_id == invoice_id)
        .options(selectinload(MatchResult.line_matches))
    )
    mr_result = await db.execute(stmt)
    match_result = mr_result.scalars().first()

    if match_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No match result found for this invoice. Match may not have run yet.",
        )

    return MatchResultOut.model_validate(match_result)


# ─── POST /invoices/{invoice_id}/match ───

@router.post(
    "/{invoice_id}/match",
    response_model=MatchTriggerResponse,
    summary="Manually trigger re-match for an invoice (AP_ANALYST+)",
)
async def trigger_match(
    invoice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_ANALYST", "ADMIN"))],
):
    """Trigger a synchronous re-match for the invoice.

    Uses a sync DB session internally (match engine is sync).
    Updates invoice status in place and returns the result.
    """
    # Verify invoice exists
    inv_result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    )
    invoice = inv_result.scalars().first()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    # Run match engine synchronously via a sync DB session
    # (match_engine uses sync SQLAlchemy; we cannot call it from async context directly
    #  without running in an executor — here we use a simple sync session)
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.core.config import settings
        from app.rules.match_engine import run_2way_match

        sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        SyncSession = sessionmaker(bind=sync_engine, expire_on_commit=False)
        sync_db = SyncSession()

        try:
            # Set status to matching
            from sqlalchemy import update
            sync_db.execute(
                update(Invoice).where(Invoice.id == invoice_id).values(status="matching")
            )
            sync_db.commit()

            match_result = run_2way_match(sync_db, invoice_id)
            # match engine commits and sets invoice.status
        finally:
            sync_db.close()
            sync_engine.dispose()

    except Exception as exc:
        logger.exception("Re-match failed for invoice %s: %s", invoice_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Match engine error: {str(exc)}",
        )

    # Refresh invoice status from DB
    await db.refresh(invoice)

    return MatchTriggerResponse(
        message=f"Re-match complete. Match status: {match_result.match_status}.",
        match_status=match_result.match_status,
        invoice_status=invoice.status,
    )
