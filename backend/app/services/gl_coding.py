"""GL Smart Coding service — frequency-based GL account suggestion.

Uses vendor invoice history (approved invoices) to suggest GL account codes
for each line item. Falls back to PO line GL account if no history.
No LLM used — purely deterministic frequency lookup.
"""
import logging
import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MIN_SIMILARITY_SCORE = 0.3  # minimum word overlap to consider a historical line

# ─── Simple category → GL fallback map ───

CATEGORY_GL_MAP = {
    "parts": "6010-PARTS",
    "fasteners": "6010-PARTS",
    "equipment": "1500-EQUIPMENT",
    "services": "6100-SERVICES",
    "maintenance": "6200-MAINTENANCE",
}


def _word_similarity(a: str | None, b: str | None) -> float:
    """Word overlap similarity (0.0-1.0)."""
    if not a or not b:
        return 0.0
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


async def suggest_gl_codes(
    db: AsyncSession,
    invoice_id: uuid.UUID,
) -> list[dict]:
    """Return GL code suggestions for each line item of the given invoice.

    Suggestion priority:
      1. vendor_history — most frequent gl_account from approved invoices of same
         vendor with similar line descriptions (word overlap >= MIN_SIMILARITY_SCORE)
      2. po_line — GL account from the matched PO line item
      3. category_default — hardcoded category → GL mapping
      4. none — no suggestion available

    Returns list of dicts matching GLLineSuggestion fields.
    """
    from app.models.invoice import Invoice, InvoiceLineItem
    from app.models.purchase_order import POLineItem

    # ── Load target invoice ──
    inv_stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    invoice = (await db.execute(inv_stmt)).scalars().first()
    if invoice is None:
        return []

    # ── Load its line items ──
    lines_stmt = (
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.line_number)
    )
    lines = list((await db.execute(lines_stmt)).scalars().all())

    # ── Pre-fetch vendor history lines (one query for all lines) ──
    history_lines: list[InvoiceLineItem] = []
    if invoice.vendor_id:
        history_stmt = (
            select(InvoiceLineItem)
            .join(Invoice, Invoice.id == InvoiceLineItem.invoice_id)
            .where(
                Invoice.vendor_id == invoice.vendor_id,
                Invoice.status == "approved",
                Invoice.deleted_at.is_(None),
                Invoice.id != invoice_id,
                InvoiceLineItem.gl_account.isnot(None),
            )
        )
        history_lines = list((await db.execute(history_stmt)).scalars().all())

    suggestions = []

    for line in lines:
        gl_account = None
        cost_center = None
        confidence = 0.0
        source = "none"

        # ── 1. Vendor history ──
        similar_lines = [
            hl for hl in history_lines
            if _word_similarity(line.description, hl.description) >= MIN_SIMILARITY_SCORE
        ]

        if similar_lines:
            gl_counter: Counter = Counter(hl.gl_account for hl in similar_lines if hl.gl_account)
            cc_counter: Counter = Counter(hl.cost_center for hl in similar_lines if hl.cost_center)
            if gl_counter:
                top_gl, top_count = gl_counter.most_common(1)[0]
                gl_account = top_gl
                cost_center = cc_counter.most_common(1)[0][0] if cc_counter else None
                confidence = top_count / len(similar_lines)
                source = "vendor_history"

        # ── 2. PO line fallback ──
        if not gl_account and line.po_line_item_id:
            po_line = (await db.execute(
                select(POLineItem).where(POLineItem.id == line.po_line_item_id)
            )).scalars().first()
            if po_line and po_line.gl_account:
                gl_account = po_line.gl_account
                confidence = 0.5
                source = "po_line"

        # ── 3. Category default ──
        if not gl_account and line.category:
            mapped = CATEGORY_GL_MAP.get((line.category or "").lower())
            if mapped:
                gl_account = mapped
                confidence = 0.3
                source = "category_default"

        suggestions.append({
            "line_id": line.id,
            "line_number": line.line_number,
            "description": line.description,
            "gl_account": gl_account,
            "cost_center": cost_center,
            "confidence_pct": round(confidence, 4),
            "source": source,
        })

    return suggestions
