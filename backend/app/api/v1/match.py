"""Match result endpoints — GET match result and POST trigger re-match."""
import uuid
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, require_role
from app.db.session import get_session
from app.models.goods_receipt import GoodsReceipt, GRLineItem
from app.models.inspection_report import InspectionReport
from app.models.invoice import Invoice, InvoiceLineItem
from app.models.matching import MatchResult, LineItemMatch
from app.models.purchase_order import PurchaseOrder, POLineItem
from app.models.user import User
from app.schemas.match import GRLineOut, GRNSummaryOut, MatchResultOut, MatchTriggerResponse

logger = logging.getLogger(__name__)

router = APIRouter()
gr_router = APIRouter()


# ─── Schemas for inspection endpoint ───

class InspectionCreateIn(BaseModel):
    result: str  # pass, fail, partial
    notes: str | None = None


class InspectionReportOut(BaseModel):
    id: uuid.UUID
    gr_id: uuid.UUID
    invoice_id: uuid.UUID | None
    inspector_id: uuid.UUID | None
    result: str
    notes: str | None
    inspected_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


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
    """Return the MatchResult with enriched LineItemMatches (descriptions, amounts, GRN data)."""
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

    out = MatchResultOut.model_validate(match_result)

    # ── Enrich: PO number ──
    if match_result.po_id:
        po_row = await db.execute(
            select(PurchaseOrder).where(PurchaseOrder.id == match_result.po_id)
        )
        po = po_row.scalars().first()
        if po:
            out.po_number = po.po_number

    # ── Enrich: GRN data (3-way only) ──
    if match_result.match_type == "3way" and match_result.gr_id:
        gr_row = await db.execute(
            select(GoodsReceipt)
            .where(GoodsReceipt.id == match_result.gr_id)
            .options(selectinload(GoodsReceipt.line_items))
        )
        gr = gr_row.scalars().first()
        if gr:
            out.gr_number = gr.gr_number

            # Fetch latest inspection report for this GR
            insp_row = await db.execute(
                select(InspectionReport)
                .where(InspectionReport.gr_id == gr.id)
                .order_by(desc(InspectionReport.inspected_at))
                .limit(1)
            )
            inspection = insp_row.scalars().first()
            inspection_status = inspection.result if inspection else None

            out.grn_data = GRNSummaryOut(
                id=gr.id,
                gr_number=gr.gr_number,
                received_at=gr.received_at,
                inspection_status=inspection_status,
                lines=[
                    GRLineOut(
                        id=li.id,
                        line_number=li.line_number,
                        description=li.description,
                        qty_received=float(li.quantity),
                        unit=li.unit,
                    )
                    for li in sorted(gr.line_items, key=lambda x: x.line_number)
                ],
            )

    # ── Enrich: line match descriptions and amounts ──
    if match_result.line_matches:
        inv_line_ids = [lm.invoice_line_id for lm in match_result.line_matches]
        po_line_ids = [lm.po_line_id for lm in match_result.line_matches if lm.po_line_id]
        gr_line_ids = [lm.gr_line_id for lm in match_result.line_matches if lm.gr_line_id]

        inv_lines: dict[uuid.UUID, InvoiceLineItem] = {}
        if inv_line_ids:
            rows = await db.execute(
                select(InvoiceLineItem).where(InvoiceLineItem.id.in_(inv_line_ids))
            )
            for li in rows.scalars():
                inv_lines[li.id] = li

        po_lines: dict[uuid.UUID, POLineItem] = {}
        if po_line_ids:
            rows = await db.execute(
                select(POLineItem).where(POLineItem.id.in_(po_line_ids))
            )
            for li in rows.scalars():
                po_lines[li.id] = li

        gr_lines: dict[uuid.UUID, GRLineItem] = {}
        if gr_line_ids:
            rows = await db.execute(
                select(GRLineItem).where(GRLineItem.id.in_(gr_line_ids))
            )
            for li in rows.scalars():
                gr_lines[li.id] = li

        # Build lookup from ORM line_matches (keyed by id for safe mapping)
        orm_lm_by_id: dict[uuid.UUID, LineItemMatch] = {lm.id: lm for lm in match_result.line_matches}

        for lm_out in out.line_matches:
            orm_lm = orm_lm_by_id.get(lm_out.id)
            if not orm_lm:
                continue
            inv_li = inv_lines.get(orm_lm.invoice_line_id)
            po_li = po_lines.get(orm_lm.po_line_id) if orm_lm.po_line_id else None
            gr_li = gr_lines.get(orm_lm.gr_line_id) if orm_lm.gr_line_id else None

            lm_out.description = inv_li.description if inv_li else None
            lm_out.invoice_amount = float(inv_li.line_total) if inv_li and inv_li.line_total is not None else None
            lm_out.qty_invoiced = float(inv_li.quantity) if inv_li and inv_li.quantity is not None else None
            lm_out.po_amount = float(po_li.unit_price * po_li.quantity) if po_li else None
            lm_out.qty_on_po = float(po_li.quantity) if po_li else None
            lm_out.qty_received = float(gr_li.quantity) if gr_li else None

            # Populate GRN_NOT_FOUND exception code for 3-way lines missing a GR line
            if out.match_type == "3way" and orm_lm.gr_line_id is None:
                lm_out.exception_code = "GRN_NOT_FOUND"

            # Populate grn_lines_used from the GR number already fetched above
            if gr_li is not None and out.gr_number:
                lm_out.grn_lines_used = [out.gr_number]

    return out


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
    match_type: str = Query(
        default="auto",
        description=(
            "Match strategy: 'auto' selects 3-way if GRNs exist for the PO, "
            "else 2-way. '2way' forces 2-way. '3way' forces 3-way."
        ),
    ),
):
    """Trigger a synchronous re-match for the invoice.

    Uses a sync DB session internally (match engine is sync).
    Updates invoice status in place and returns the result.
    """
    if match_type not in ("auto", "2way", "3way"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="match_type must be 'auto', '2way', or '3way'.",
        )

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
        from sqlalchemy import create_engine, update
        from sqlalchemy.orm import sessionmaker
        from app.core.config import settings
        from app.rules.match_engine import run_2way_match, run_3way_match
        from app.models.goods_receipt import GoodsReceipt

        sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        SyncSession = sessionmaker(bind=sync_engine, expire_on_commit=False)
        sync_db = SyncSession()

        try:
            # Set status to matching
            sync_db.execute(
                update(Invoice).where(Invoice.id == invoice_id).values(status="matching")
            )
            sync_db.commit()

            # ── Auto-select match strategy ──
            if match_type == "auto":
                # Reload invoice in sync session to access po_id
                inv_sync = sync_db.execute(
                    select(Invoice).where(Invoice.id == invoice_id)
                ).scalars().first()
                use_3way = False
                if inv_sync and inv_sync.po_id:
                    grn_exists = sync_db.execute(
                        select(GoodsReceipt).where(
                            GoodsReceipt.po_id == inv_sync.po_id,
                            GoodsReceipt.deleted_at.is_(None),
                        )
                    ).scalars().first()
                    use_3way = grn_exists is not None
                resolved_type = "3way" if use_3way else "2way"
            else:
                resolved_type = match_type

            if resolved_type == "3way":
                match_result = run_3way_match(sync_db, invoice_id)
            else:
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
        message=f"Re-match complete ({resolved_type}). Match status: {match_result.match_status}.",
        match_status=match_result.match_status,
        invoice_status=invoice.status,
    )


# ─── POST /gr/{gr_id}/inspection ───

@gr_router.post(
    "/{gr_id}/inspection",
    response_model=InspectionReportOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a quality inspection report for a Goods Receipt (ADMIN or AP_ANALYST)",
)
async def create_inspection_report(
    gr_id: uuid.UUID,
    body: InspectionCreateIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_ANALYST", "ADMIN"))],
):
    """Create an InspectionReport for the given GR.

    - If result == 'fail': finds all open invoices linked to this GR via their PO,
      and creates an INSPECTION_FAILED ExceptionRecord on each (idempotent).
    - Returns the created InspectionReport.
    """
    # Validate result value
    if body.result not in ("pass", "fail", "partial"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="result must be 'pass', 'fail', or 'partial'.",
        )

    # Verify GR exists
    gr_row = await db.execute(
        select(GoodsReceipt).where(
            GoodsReceipt.id == gr_id,
            GoodsReceipt.deleted_at.is_(None),
        )
    )
    gr = gr_row.scalars().first()
    if gr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goods receipt not found.")

    now = datetime.now(timezone.utc)

    # Create InspectionReport
    report = InspectionReport(
        gr_id=gr_id,
        inspector_id=current_user.id,
        result=body.result,
        notes=body.notes,
        inspected_at=now,
    )
    db.add(report)
    await db.flush()  # get report.id

    # If fail: create INSPECTION_FAILED exceptions on open invoices linked via PO
    if body.result == "fail" and gr.po_id is not None:
        from app.models.exception_record import ExceptionRecord

        # Find all open invoices linked to this PO
        inv_rows = await db.execute(
            select(Invoice).where(
                Invoice.po_id == gr.po_id,
                Invoice.deleted_at.is_(None),
                Invoice.status.notin_(["approved", "paid", "rejected"]),
            )
        )
        affected_invoices = inv_rows.scalars().all()

        for inv in affected_invoices:
            # Idempotent: skip if INSPECTION_FAILED exception already open
            existing = await db.execute(
                select(ExceptionRecord).where(
                    ExceptionRecord.invoice_id == inv.id,
                    ExceptionRecord.exception_code == "INSPECTION_FAILED",
                    ExceptionRecord.status == "open",
                )
            )
            if existing.scalars().first() is not None:
                continue

            exc_rec = ExceptionRecord(
                invoice_id=inv.id,
                exception_code="INSPECTION_FAILED",
                description=(
                    f"Quality inspection failed for GR {gr.gr_number}. "
                    f"Inspector notes: {body.notes or 'N/A'}"
                ),
                severity="high",
                status="open",
            )
            db.add(exc_rec)

    await db.commit()
    await db.refresh(report)

    return report
