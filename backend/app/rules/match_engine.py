"""2-Way Match Engine — deterministic invoice vs PO matching.

Architecture principle: LLM NEVER makes match/approval decisions.
All decisions are deterministic and reference a rule_version_id for audit.
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ─── Default tolerance config (fallback when no published rule exists) ───

DEFAULT_TOLERANCE = {
    "amount_tolerance_pct": 0.02,
    "amount_tolerance_abs": 50.00,
    "qty_tolerance_pct": 0.00,
    "auto_approve_threshold": 5000.00,
    "auto_approve_requires_match": True,
}


# ─── Result dataclasses ───

@dataclass
class LineMatchDetail:
    invoice_line_id: uuid.UUID
    po_line_id: uuid.UUID | None
    status: str  # matched, qty_variance, price_variance, unmatched
    qty_variance: float | None
    price_variance: float | None
    price_variance_pct: float | None
    exception_code: str | None = None


@dataclass
class MatchResult:
    invoice_id: uuid.UUID
    po_id: uuid.UUID | None
    match_status: str  # matched, partial, exception
    match_type: str = "2way"
    amount_variance: float | None = None
    amount_variance_pct: float | None = None
    rule_version_id: uuid.UUID | None = None
    notes: str | None = None
    line_details: list[LineMatchDetail] = field(default_factory=list)
    exception_codes: list[str] = field(default_factory=list)


# ─── Active rule loading ───

def get_active_match_rules(db: Session) -> tuple[dict, uuid.UUID | None]:
    """Load the latest published matching_tolerance rule from DB.

    Returns (config_dict, rule_version_id). Falls back to DEFAULT_TOLERANCE
    if no published rule exists.
    """
    from app.models.rule import Rule, RuleVersion

    stmt = (
        select(RuleVersion)
        .join(Rule, Rule.id == RuleVersion.rule_id)
        .where(
            Rule.rule_type == "matching_tolerance",
            Rule.is_active.is_(True),
            RuleVersion.status == "published",
        )
        .order_by(RuleVersion.created_at.desc())
    )
    rv = db.execute(stmt).scalars().first()

    if rv is None:
        logger.info("No published matching_tolerance rule found; using defaults.")
        return DEFAULT_TOLERANCE.copy(), None

    try:
        config = json.loads(rv.config_json)
        # Ensure all required keys are present (fall back to defaults for missing keys)
        for k, v in DEFAULT_TOLERANCE.items():
            config.setdefault(k, v)
        return config, rv.id
    except (json.JSONDecodeError, AttributeError) as exc:
        logger.warning("Failed to parse rule config_json: %s. Using defaults.", exc)
        return DEFAULT_TOLERANCE.copy(), rv.id


# ─── PO lookup helpers ───

def _find_po_by_id(db: Session, po_id: uuid.UUID):
    """Load PO by its UUID."""
    from app.models.purchase_order import PurchaseOrder
    from sqlalchemy.orm import selectinload

    stmt = (
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(PurchaseOrder.id == po_id, PurchaseOrder.deleted_at.is_(None))
    )
    return db.execute(stmt).scalars().first()


def _find_po_by_number(db: Session, po_number: str):
    """Load PO by po_number string (exact match, case-insensitive)."""
    from app.models.purchase_order import PurchaseOrder
    from sqlalchemy.orm import selectinload
    from sqlalchemy import func

    stmt = (
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(
            func.lower(PurchaseOrder.po_number) == po_number.lower(),
            PurchaseOrder.deleted_at.is_(None),
        )
    )
    return db.execute(stmt).scalars().first()


def _extract_po_number_from_text(text: str | None) -> str | None:
    """Heuristically extract a PO number from free text (notes/invoice_number).

    Looks for patterns like PO-1234, PO#1234, PO 1234, PO:1234.
    Returns the first candidate found or None.
    """
    if not text:
        return None
    import re
    pattern = r'\bPO[-#:\s]?(\w+)\b'
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return m.group(0).strip()
    return None


def _find_po_for_invoice(db: Session, invoice) -> Any:
    """Try to find the PO associated with an invoice.

    Priority:
    1. invoice.po_id (direct FK)
    2. PO number in invoice.notes
    3. PO number prefix in invoice.invoice_number
    """
    if invoice.po_id:
        po = _find_po_by_id(db, invoice.po_id)
        if po:
            return po

    # Search by PO number hint in notes
    po_number_hint = _extract_po_number_from_text(invoice.notes)
    if po_number_hint:
        po = _find_po_by_number(db, po_number_hint)
        if po:
            return po

    # Try invoice_number prefix (e.g. "PO-1001-INV-001" → PO-1001)
    if invoice.invoice_number:
        po_number_hint2 = _extract_po_number_from_text(invoice.invoice_number)
        if po_number_hint2:
            po = _find_po_by_number(db, po_number_hint2)
            if po:
                return po

    return None


# ─── Line matching helpers ───

def _description_similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity score (0–1)."""
    if not a or not b:
        return 0.0
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    overlap = words_a & words_b
    return len(overlap) / max(len(words_a), len(words_b))


def _find_best_po_line(inv_line, po_lines):
    """Find the best matching PO line for an invoice line.

    Matches first by line_number, then by description similarity.
    Returns (po_line, score) or (None, 0).
    """
    if not po_lines:
        return None, 0.0

    # Try exact line_number match first
    for pl in po_lines:
        if pl.line_number == inv_line.line_number:
            return pl, 1.0

    # Fall back to description similarity
    best_pl = None
    best_score = 0.0
    for pl in po_lines:
        score = _description_similarity(
            str(inv_line.description or ""),
            str(pl.description or ""),
        )
        if score > best_score:
            best_score = score
            best_pl = pl

    return best_pl, best_score


# ─── Core match logic ───

def run_2way_match(db: Session, invoice_id: uuid.UUID) -> MatchResult:
    """Run 2-way match for the given invoice against its PO.

    Steps:
    1. Load invoice + line items
    2. Find PO (by po_id, notes, or invoice_number prefix)
    3. Header amount check
    4. Line-level qty + price check
    5. Create MatchResult + LineItemMatch rows
    6. Create ExceptionRecord rows for out-of-tolerance lines
    7. Auto-approve if within threshold; set invoice.status
    8. Write audit log

    Returns: MatchResult dataclass (not the DB model).
    """
    from app.models.invoice import Invoice, InvoiceLineItem
    from app.models.matching import MatchResult as MatchResultModel, LineItemMatch
    from app.models.exception_record import ExceptionRecord
    from app.services import audit as audit_svc

    # ── 1. Load invoice ──
    stmt = (
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    )
    invoice = db.execute(stmt).scalars().first()
    if invoice is None:
        raise ValueError(f"Invoice {invoice_id} not found")

    # Load line items
    line_items_stmt = select(InvoiceLineItem).where(
        InvoiceLineItem.invoice_id == invoice_id
    ).order_by(InvoiceLineItem.line_number)
    inv_lines = db.execute(line_items_stmt).scalars().all()

    # ── Load active rules ──
    tolerance, rule_version_id = get_active_match_rules(db)
    amt_tol_pct = float(tolerance["amount_tolerance_pct"])
    amt_tol_abs = float(tolerance["amount_tolerance_abs"])
    qty_tol_pct = float(tolerance["qty_tolerance_pct"])
    auto_approve_threshold = float(tolerance["auto_approve_threshold"])
    auto_approve_requires_match = bool(tolerance.get("auto_approve_requires_match", True))

    # ── 2. Find PO ──
    po = _find_po_for_invoice(db, invoice)

    if po is None:
        # No PO found → exception
        match_result = MatchResult(
            invoice_id=invoice_id,
            po_id=None,
            match_status="exception",
            match_type="2way",
            rule_version_id=rule_version_id,
            notes="No matching PO found",
            exception_codes=["MISSING_PO"],
        )
        _persist_match_result(
            db=db,
            invoice=invoice,
            result=match_result,
            rule_version_id=rule_version_id,
            audit_svc=audit_svc,
        )
        return match_result

    po_lines = list(po.line_items)

    # ── 3. Header amount check ──
    inv_total = float(invoice.total_amount or 0)
    po_total = float(po.total_amount or 0)
    amt_diff = abs(inv_total - po_total)

    if po_total > 0:
        amt_diff_pct = amt_diff / po_total
    else:
        amt_diff_pct = 0.0 if inv_total == 0 else 1.0

    header_ok = (amt_diff_pct <= amt_tol_pct) or (amt_diff <= amt_tol_abs)

    # ── 4. Line-level check ──
    line_details: list[LineMatchDetail] = []
    out_of_tolerance_count = 0
    unmatched_count = 0
    exception_codes: set[str] = set()

    for inv_line in inv_lines:
        po_line, similarity = _find_best_po_line(inv_line, po_lines)

        if po_line is None or similarity < 0.1:
            # No matching PO line
            detail = LineMatchDetail(
                invoice_line_id=inv_line.id,
                po_line_id=None,
                status="unmatched",
                qty_variance=None,
                price_variance=None,
                price_variance_pct=None,
                exception_code="MISSING_PO",
            )
            unmatched_count += 1
            exception_codes.add("MISSING_PO")
        else:
            inv_qty = float(inv_line.quantity or 0)
            po_qty = float(po_line.quantity or 0)
            inv_price = float(inv_line.unit_price or 0)
            po_price = float(po_line.unit_price or 0)

            qty_var = inv_qty - po_qty
            price_var = inv_price - po_price
            price_var_pct = (abs(price_var) / po_price) if po_price > 0 else 0.0

            qty_ok = (abs(qty_var) / po_qty <= qty_tol_pct) if po_qty > 0 else (qty_var == 0)
            price_ok = price_var_pct <= amt_tol_pct or abs(price_var) <= amt_tol_abs

            if qty_ok and price_ok:
                line_status = "matched"
                exc_code = None
            elif not qty_ok and not price_ok:
                line_status = "qty_variance"
                exc_code = "QTY_VARIANCE"
                out_of_tolerance_count += 1
                exception_codes.add("QTY_VARIANCE")
                exception_codes.add("PRICE_VARIANCE")
            elif not qty_ok:
                line_status = "qty_variance"
                exc_code = "QTY_VARIANCE"
                out_of_tolerance_count += 1
                exception_codes.add("QTY_VARIANCE")
            else:
                line_status = "price_variance"
                exc_code = "PRICE_VARIANCE"
                out_of_tolerance_count += 1
                exception_codes.add("PRICE_VARIANCE")

            detail = LineMatchDetail(
                invoice_line_id=inv_line.id,
                po_line_id=po_line.id,
                status=line_status,
                qty_variance=qty_var if po_line else None,
                price_variance=price_var if po_line else None,
                price_variance_pct=price_var_pct if po_line else None,
                exception_code=exc_code,
            )

        line_details.append(detail)

    # ── 5. Determine overall match_status ──
    total_lines = len(inv_lines)
    matched_lines = sum(1 for d in line_details if d.status == "matched")

    if not header_ok:
        # Header amount way off → exception regardless of lines
        overall_status = "exception"
        exception_codes.add("PRICE_VARIANCE")
    elif total_lines == 0:
        # No line items — header-only match
        overall_status = "matched" if header_ok else "exception"
    elif out_of_tolerance_count == 0 and unmatched_count == 0:
        overall_status = "matched"
    elif matched_lines == 0:
        overall_status = "exception"
    else:
        overall_status = "partial"

    match_result = MatchResult(
        invoice_id=invoice_id,
        po_id=po.id,
        match_status=overall_status,
        match_type="2way",
        amount_variance=amt_diff if po_total > 0 else None,
        amount_variance_pct=amt_diff_pct if po_total > 0 else None,
        rule_version_id=rule_version_id,
        line_details=line_details,
        exception_codes=sorted(exception_codes),
        notes=f"Header variance: {amt_diff:.2f} ({amt_diff_pct*100:.2f}%). "
              f"Lines: {matched_lines}/{total_lines} matched.",
    )

    # ── Persist ──
    _persist_match_result(
        db=db,
        invoice=invoice,
        result=match_result,
        rule_version_id=rule_version_id,
        audit_svc=audit_svc,
        po=po,
        auto_approve_threshold=auto_approve_threshold,
        auto_approve_requires_match=auto_approve_requires_match,
    )

    return match_result


# ─── 3-Way match ───

def run_3way_match(db: Session, invoice_id: uuid.UUID) -> MatchResult:
    """3-way match: Invoice qty must not exceed total qty received via GRNs for the PO.

    Steps:
    1. Load invoice + line items
    2. Find PO (same helpers as 2-way)
    3. Load all GoodsReceipts for that po_id
    4. Load all GRLineItems for those GRNs
    5. Aggregate total_grn_qty per PO line item
    6. If no GRNs found → GRN_NOT_FOUND exception (severity HIGH)
    7. Per invoice line: invoice qty must not exceed total received qty + tolerance
       → QTY_OVER_RECEIPT exception (severity HIGH) if violated
    8. Persist MatchResult with match_type="3way"
    9. Auto-approve if no exceptions (same threshold logic as 2-way)
    """
    from app.models.invoice import Invoice, InvoiceLineItem
    from app.models.goods_receipt import GoodsReceipt, GRLineItem
    from app.services import audit as audit_svc

    # ── 1. Load invoice ──
    stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    invoice = db.execute(stmt).scalars().first()
    if invoice is None:
        raise ValueError(f"Invoice {invoice_id} not found")

    line_items_stmt = (
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice_id)
        .order_by(InvoiceLineItem.line_number)
    )
    inv_lines = db.execute(line_items_stmt).scalars().all()

    # ── Load active rules ──
    tolerance, rule_version_id = get_active_match_rules(db)
    qty_tol_pct = float(tolerance["qty_tolerance_pct"])
    auto_approve_threshold = float(tolerance["auto_approve_threshold"])
    auto_approve_requires_match = bool(tolerance.get("auto_approve_requires_match", True))

    # ── 2. Find PO ──
    po = _find_po_for_invoice(db, invoice)

    if po is None:
        match_result = MatchResult(
            invoice_id=invoice_id,
            po_id=None,
            match_status="exception",
            match_type="3way",
            rule_version_id=rule_version_id,
            notes="No matching PO found",
            exception_codes=["MISSING_PO"],
        )
        _persist_match_result(
            db=db, invoice=invoice, result=match_result,
            rule_version_id=rule_version_id, audit_svc=audit_svc,
        )
        return match_result

    po_lines = list(po.line_items)

    # ── 3. Load all GoodsReceipts for this PO ──
    grn_stmt = select(GoodsReceipt).where(
        GoodsReceipt.po_id == po.id,
        GoodsReceipt.deleted_at.is_(None),
    )
    grns = db.execute(grn_stmt).scalars().all()

    # ── 6. If no GRNs found → exception ──
    if not grns:
        match_result = MatchResult(
            invoice_id=invoice_id,
            po_id=po.id,
            match_status="exception",
            match_type="3way",
            rule_version_id=rule_version_id,
            notes="No goods receipts found for PO",
            exception_codes=["GRN_NOT_FOUND"],
        )
        _persist_match_result(
            db=db, invoice=invoice, result=match_result,
            rule_version_id=rule_version_id, audit_svc=audit_svc,
            po=po,
            auto_approve_threshold=auto_approve_threshold,
            auto_approve_requires_match=auto_approve_requires_match,
        )
        return match_result

    # ── 4. Load all GRLineItems for those GRNs ──
    grn_ids = [grn.id for grn in grns]
    gr_lines_stmt = select(GRLineItem).where(GRLineItem.gr_id.in_(grn_ids))
    gr_lines = db.execute(gr_lines_stmt).scalars().all()

    # ── 5. Aggregate total received qty per PO line item ──
    # GR lines with po_line_item_id → aggregate directly.
    # GR lines without → match by line_number/description to PO lines and aggregate.
    grn_qty_by_po_line_id: dict[uuid.UUID, float] = {}
    for grl in gr_lines:
        if grl.po_line_item_id is not None:
            grn_qty_by_po_line_id[grl.po_line_item_id] = (
                grn_qty_by_po_line_id.get(grl.po_line_item_id, 0.0)
                + float(grl.quantity or 0)
            )
        else:
            best_pl, score = _find_best_po_line(grl, po_lines)
            if best_pl is not None and score >= 0.1:
                grn_qty_by_po_line_id[best_pl.id] = (
                    grn_qty_by_po_line_id.get(best_pl.id, 0.0)
                    + float(grl.quantity or 0)
                )

    # ── 7. For each invoice line: check invoice qty vs total received ──
    line_details: list[LineMatchDetail] = []
    exception_codes: set[str] = set()
    out_of_tolerance_count = 0
    unmatched_count = 0

    for inv_line in inv_lines:
        po_line, similarity = _find_best_po_line(inv_line, po_lines)

        if po_line is None or similarity < 0.1:
            detail = LineMatchDetail(
                invoice_line_id=inv_line.id,
                po_line_id=None,
                status="unmatched",
                qty_variance=None,
                price_variance=None,
                price_variance_pct=None,
                exception_code="MISSING_PO",
            )
            unmatched_count += 1
            exception_codes.add("MISSING_PO")
        else:
            inv_qty = float(inv_line.quantity or 0)
            total_received = grn_qty_by_po_line_id.get(po_line.id, 0.0)
            qty_var = inv_qty - total_received

            # Over-receipt: invoice qty must not exceed received qty + tolerance
            if total_received > 0:
                qty_ok = inv_qty <= total_received * (1.0 + qty_tol_pct)
            else:
                # Nothing received yet; any positive invoice qty is over-receipt
                qty_ok = inv_qty <= 0

            if qty_ok:
                line_status = "matched"
                exc_code = None
            else:
                line_status = "qty_variance"
                exc_code = "QTY_OVER_RECEIPT"
                out_of_tolerance_count += 1
                exception_codes.add("QTY_OVER_RECEIPT")

            detail = LineMatchDetail(
                invoice_line_id=inv_line.id,
                po_line_id=po_line.id,
                status=line_status,
                qty_variance=qty_var,
                price_variance=None,
                price_variance_pct=None,
                exception_code=exc_code,
            )

        line_details.append(detail)

    # ── Determine overall match_status ──
    total_lines = len(inv_lines)
    matched_lines = sum(1 for d in line_details if d.status == "matched")

    if total_lines == 0 or (out_of_tolerance_count == 0 and unmatched_count == 0):
        overall_status = "matched"
    elif matched_lines == 0:
        overall_status = "exception"
    else:
        overall_status = "partial"

    match_result = MatchResult(
        invoice_id=invoice_id,
        po_id=po.id,
        match_status=overall_status,
        match_type="3way",
        rule_version_id=rule_version_id,
        line_details=line_details,
        exception_codes=sorted(exception_codes),
        notes=(
            f"3-way match: {matched_lines}/{total_lines} lines matched against GRNs "
            f"({len(grns)} GRN(s), {len(gr_lines)} GR line(s))."
        ),
    )

    _persist_match_result(
        db=db,
        invoice=invoice,
        result=match_result,
        rule_version_id=rule_version_id,
        audit_svc=audit_svc,
        po=po,
        auto_approve_threshold=auto_approve_threshold,
        auto_approve_requires_match=auto_approve_requires_match,
    )

    return match_result


# ─── Persistence helper ───

def _persist_match_result(
    db: Session,
    invoice,
    result: MatchResult,
    rule_version_id: uuid.UUID | None,
    audit_svc,
    po=None,
    auto_approve_threshold: float = 5000.0,
    auto_approve_requires_match: bool = True,
) -> None:
    """Write MatchResult, LineItemMatch, ExceptionRecord rows; update invoice status."""
    from app.models.matching import MatchResult as MatchResultModel, LineItemMatch
    from app.models.exception_record import ExceptionRecord

    now = datetime.now(timezone.utc)
    prev_status = invoice.status

    # ── Delete existing match result (re-match scenario) ──
    from sqlalchemy import delete as sa_delete

    existing = db.execute(
        select(MatchResultModel).where(MatchResultModel.invoice_id == invoice.id)
    ).scalars().first()

    if existing:
        db.execute(sa_delete(LineItemMatch).where(LineItemMatch.match_result_id == existing.id))
        db.delete(existing)
        db.flush()

    # ── Create MatchResult row ──
    mr = MatchResultModel(
        invoice_id=invoice.id,
        po_id=result.po_id,
        gr_id=None,
        match_type=result.match_type,
        match_status=result.match_status,
        rule_version_id=rule_version_id,
        amount_variance=result.amount_variance,
        amount_variance_pct=result.amount_variance_pct,
        matched_at=now,
        notes=result.notes,
    )
    db.add(mr)
    db.flush()  # get mr.id

    # ── Create LineItemMatch rows ──
    for detail in result.line_details:
        lim = LineItemMatch(
            match_result_id=mr.id,
            invoice_line_id=detail.invoice_line_id,
            po_line_id=detail.po_line_id,
            gr_line_id=None,
            status=detail.status,
            qty_variance=detail.qty_variance,
            price_variance=detail.price_variance,
            price_variance_pct=detail.price_variance_pct,
        )
        db.add(lim)

    # ── Create ExceptionRecord rows ──
    for detail in result.line_details:
        if detail.exception_code:
            _create_exception(db, invoice.id, detail.exception_code,
                              f"Line item variance on invoice line {detail.invoice_line_id}")

    if result.match_status == "exception" and "MISSING_PO" in result.exception_codes:
        _create_exception(db, invoice.id, "MISSING_PO", "No matching PO found for this invoice")

    if result.match_status == "exception" and "GRN_NOT_FOUND" in result.exception_codes:
        _create_exception(db, invoice.id, "GRN_NOT_FOUND", "No goods receipts found for this PO")

    # ── Determine auto-approve or set status ──
    inv_total = float(invoice.total_amount or 0)
    can_auto_approve = (
        result.match_status == "matched"
        and inv_total <= auto_approve_threshold
        and (not auto_approve_requires_match or result.match_status == "matched")
    )

    if can_auto_approve:
        new_status = "approved"
        notes_suffix = f" Auto-approved (total={inv_total:.2f} <= threshold={auto_approve_threshold:.2f})."
    elif result.match_status in ("matched", "partial"):
        new_status = "matched"
        notes_suffix = ""
    else:
        new_status = "exception"
        notes_suffix = ""

    invoice.status = new_status
    db.flush()

    # ── Auto-create approval task for matched-but-not-auto-approved invoices ──
    if new_status == "matched":
        try:
            from app.services.approval import auto_create_approval_task
            approval_task = auto_create_approval_task(db, invoice.id)
            if approval_task:
                notes_suffix += f" Approval task created (task_id={approval_task.id})."
        except Exception as approval_exc:
            logger.warning(
                "Failed to auto-create approval task for invoice %s: %s",
                invoice.id, approval_exc,
            )

    # ── Audit log ──
    audit_svc.log(
        db=db,
        action="invoice.match_completed",
        entity_type="invoice",
        entity_id=invoice.id,
        before={"status": prev_status},
        after={
            "status": new_status,
            "match_status": result.match_status,
            "rule_version_id": str(rule_version_id) if rule_version_id else None,
            "amount_variance": result.amount_variance,
            "exception_codes": result.exception_codes,
        },
        notes=f"{result.match_type} match run. Status={result.match_status}.{notes_suffix}",
    )

    db.commit()
    logger.info(
        "Match complete for invoice %s: %s → invoice.status=%s",
        invoice.id, result.match_status, new_status,
    )


def _create_exception(
    db: Session,
    invoice_id: uuid.UUID,
    exception_code: str,
    description: str,
) -> None:
    """Create or update an ExceptionRecord. Avoids duplicates by code+invoice."""
    from app.models.exception_record import ExceptionRecord

    # Check if open exception with same code already exists
    existing = db.execute(
        select(ExceptionRecord).where(
            ExceptionRecord.invoice_id == invoice_id,
            ExceptionRecord.exception_code == exception_code,
            ExceptionRecord.status == "open",
        )
    ).scalars().first()

    if existing:
        return  # Already exists

    severity_map = {
        "MISSING_PO": "high",
        "PRICE_VARIANCE": "medium",
        "QTY_VARIANCE": "medium",
        "DUPLICATE_INVOICE": "high",
        "FRAUD_FLAG": "critical",
        "GRN_NOT_FOUND": "high",
        "QTY_OVER_RECEIPT": "high",
    }
    severity = severity_map.get(exception_code, "medium")

    exc_rec = ExceptionRecord(
        invoice_id=invoice_id,
        exception_code=exception_code,
        description=description,
        severity=severity,
        status="open",
    )
    db.add(exc_rec)
    db.flush()
