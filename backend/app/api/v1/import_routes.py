"""CSV bulk import endpoints for POs, GRNs, and Vendors."""
import csv
import io
import difflib
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.db.session import get_session
from app.models.purchase_order import PurchaseOrder
from app.models.goods_receipt import GoodsReceipt
from app.models.vendor import Vendor
from app.schemas.imports import ImportResult, ImportRowError

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Constants ───

LARGE_FILE_THRESHOLD = 1000


# ─── Helpers ───

def _parse_csv(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _missing_cols(row_keys: list[str], required: list[str]) -> list[str]:
    lowered = {k.lower().strip() for k in row_keys}
    return [r for r in required if r.lower() not in lowered]


def _get(row: dict[str, str], key: str) -> str:
    """Case-insensitive dict get, stripped."""
    for k, v in row.items():
        if k.lower().strip() == key.lower():
            return (v or "").strip()
    return ""


def _parse_date(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _parse_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


# ─── POST /import/pos ───

@router.post("/pos", response_model=ImportResult, summary="Bulk import Purchase Orders from CSV (ADMIN, AP_ANALYST)")
async def import_pos(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(require_role("ADMIN", "AP_ANALYST"))],
    file: UploadFile = File(...),
):
    content = await file.read()
    rows = _parse_csv(content)

    if len(rows) > LARGE_FILE_THRESHOLD:
        return {"message": "queued"}  # type: ignore[return-value]

    required = ["po_number", "vendor_name", "total_amount", "currency", "issue_date"]
    if rows:
        missing = _missing_cols(list(rows[0].keys()), required)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Missing required columns: {', '.join(missing)}",
            )

    created = updated = skipped = 0
    errors: list[ImportRowError] = []

    # Cache vendor lookups
    vendor_cache: dict[str, Vendor | None] = {}

    for idx, row in enumerate(rows, start=2):  # row 1 = header
        po_number = _get(row, "po_number")
        vendor_name = _get(row, "vendor_name")
        total_str = _get(row, "total_amount")
        currency = _get(row, "currency").upper() or "USD"
        issue_date_str = _get(row, "issue_date")

        if not po_number:
            errors.append(ImportRowError(row=idx, field="po_number", message="po_number is required"))
            skipped += 1
            continue
        if not vendor_name:
            errors.append(ImportRowError(row=idx, field="vendor_name", message="vendor_name is required"))
            skipped += 1
            continue

        total_amount = _parse_decimal(total_str)
        if total_amount is None:
            errors.append(ImportRowError(row=idx, field="total_amount", message=f"Invalid total_amount: '{total_str}'"))
            skipped += 1
            continue

        issued_at = _parse_date(issue_date_str) if issue_date_str else None

        # Resolve vendor
        if vendor_name not in vendor_cache:
            result = await db.execute(
                select(Vendor).where(Vendor.name == vendor_name, Vendor.deleted_at.is_(None))
            )
            vendor = result.scalar_one_or_none()
            if vendor is None:
                # Create vendor on-the-fly
                vendor = Vendor(name=vendor_name, currency=currency, payment_terms=30)
                db.add(vendor)
                await db.flush()
            vendor_cache[vendor_name] = vendor
        vendor = vendor_cache[vendor_name]

        # Upsert PO by po_number
        result = await db.execute(
            select(PurchaseOrder).where(PurchaseOrder.po_number == po_number)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.vendor_id = vendor.id
            existing.total_amount = float(total_amount)
            existing.currency = currency
            if issued_at:
                existing.issued_at = issued_at
            db.add(existing)
            updated += 1
        else:
            po = PurchaseOrder(
                po_number=po_number,
                vendor_id=vendor.id,
                total_amount=float(total_amount),
                currency=currency,
                issued_at=issued_at,
                status="open",
            )
            db.add(po)
            created += 1

    await db.commit()
    return ImportResult(created=created, updated=updated, skipped=skipped, errors=errors)


# ─── POST /import/grns ───

@router.post("/grns", response_model=ImportResult, summary="Bulk import Goods Receipts from CSV (ADMIN, AP_ANALYST)")
async def import_grns(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(require_role("ADMIN", "AP_ANALYST"))],
    file: UploadFile = File(...),
):
    content = await file.read()
    rows = _parse_csv(content)

    if len(rows) > LARGE_FILE_THRESHOLD:
        return {"message": "queued"}  # type: ignore[return-value]

    required = ["gr_number", "po_number", "received_date", "total_received_value"]
    if rows:
        missing = _missing_cols(list(rows[0].keys()), required)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Missing required columns: {', '.join(missing)}",
            )

    created = updated = skipped = 0
    errors: list[ImportRowError] = []

    # Cache PO lookups
    po_cache: dict[str, PurchaseOrder | None] = {}

    for idx, row in enumerate(rows, start=2):
        gr_number = _get(row, "gr_number")
        po_number = _get(row, "po_number")
        received_date_str = _get(row, "received_date")

        if not gr_number:
            errors.append(ImportRowError(row=idx, field="gr_number", message="gr_number is required"))
            skipped += 1
            continue
        if not po_number:
            errors.append(ImportRowError(row=idx, field="po_number", message="po_number is required"))
            skipped += 1
            continue

        received_at = _parse_date(received_date_str)
        if received_at is None:
            errors.append(ImportRowError(row=idx, field="received_date", message=f"Invalid received_date: '{received_date_str}'"))
            skipped += 1
            continue

        # Resolve PO
        if po_number not in po_cache:
            result = await db.execute(
                select(PurchaseOrder).where(PurchaseOrder.po_number == po_number)
            )
            po_cache[po_number] = result.scalar_one_or_none()

        po = po_cache[po_number]
        if po is None:
            errors.append(ImportRowError(row=idx, field="po_number", message=f"PO '{po_number}' not found"))
            skipped += 1
            continue

        # Upsert GRN by gr_number
        result = await db.execute(
            select(GoodsReceipt).where(GoodsReceipt.gr_number == gr_number)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.po_id = po.id
            existing.vendor_id = po.vendor_id
            existing.received_at = received_at
            db.add(existing)
            updated += 1
        else:
            grn = GoodsReceipt(
                gr_number=gr_number,
                po_id=po.id,
                vendor_id=po.vendor_id,
                received_at=received_at,
            )
            db.add(grn)
            created += 1

    await db.commit()
    return ImportResult(created=created, updated=updated, skipped=skipped, errors=errors)


# ─── POST /import/vendors ───

@router.post("/vendors", response_model=ImportResult, summary="Bulk import Vendors from CSV (ADMIN)")
async def import_vendors(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(require_role("ADMIN"))],
    file: UploadFile = File(...),
):
    content = await file.read()
    rows = _parse_csv(content)

    if len(rows) > LARGE_FILE_THRESHOLD:
        return {"message": "queued"}  # type: ignore[return-value]

    required = ["vendor_name", "tax_id", "payment_terms", "currency"]
    if rows:
        missing = _missing_cols(list(rows[0].keys()), required)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Missing required columns: {', '.join(missing)}",
            )

    created = updated = skipped = 0
    errors: list[ImportRowError] = []
    warnings: list[str] = []

    # Load all existing vendors for fuzzy dedup
    all_vendors_result = await db.execute(
        select(Vendor).where(Vendor.deleted_at.is_(None))
    )
    existing_vendors: list[Vendor] = list(all_vendors_result.scalars().all())
    existing_by_tax_id: dict[str, Vendor] = {v.tax_id: v for v in existing_vendors if v.tax_id}
    existing_names = [(v.name, v) for v in existing_vendors]

    for idx, row in enumerate(rows, start=2):
        vendor_name = _get(row, "vendor_name")
        tax_id = _get(row, "tax_id")
        payment_terms_str = _get(row, "payment_terms")
        currency = _get(row, "currency").upper() or "USD"

        if not vendor_name:
            errors.append(ImportRowError(row=idx, field="vendor_name", message="vendor_name is required"))
            skipped += 1
            continue

        try:
            payment_terms = int(payment_terms_str) if payment_terms_str else 30
        except ValueError:
            errors.append(ImportRowError(row=idx, field="payment_terms", message=f"Invalid payment_terms: '{payment_terms_str}'"))
            skipped += 1
            continue

        # Tax ID match → update
        if tax_id and tax_id in existing_by_tax_id:
            vendor = existing_by_tax_id[tax_id]
            vendor.name = vendor_name
            vendor.payment_terms = payment_terms
            vendor.currency = currency
            db.add(vendor)
            updated += 1
            continue

        # Fuzzy name dedup check
        fuzzy_match: Vendor | None = None
        best_ratio = 0.0
        for name, v in existing_names:
            ratio = difflib.SequenceMatcher(None, vendor_name.lower(), name.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                fuzzy_match = v

        if best_ratio >= 0.90 and fuzzy_match is not None:
            warnings.append(
                f"Row {idx}: '{vendor_name}' is {best_ratio:.0%} similar to existing vendor '{fuzzy_match.name}' — check for duplicates"
            )

        # Create new vendor
        vendor = Vendor(
            name=vendor_name,
            tax_id=tax_id if tax_id else None,
            payment_terms=payment_terms,
            currency=currency,
        )
        db.add(vendor)
        await db.flush()

        # Update caches for subsequent rows in same file
        if tax_id:
            existing_by_tax_id[tax_id] = vendor
        existing_names.append((vendor_name, vendor))
        created += 1

    await db.commit()
    return ImportResult(created=created, updated=updated, skipped=skipped, errors=errors, warnings=warnings)
