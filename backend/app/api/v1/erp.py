"""ERP sync endpoints — SAP PO and Oracle GRN CSV upload (ADMIN only)."""
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.db.session import get_session
from app.integrations.oracle_csv import parse_oracle_grns, upsert_oracle_grns
from app.integrations.sap_csv import parse_sap_pos, upsert_sap_pos

router = APIRouter()


# ─── POST /admin/erp/sync/sap-pos ───


@router.post(
    "/erp/sync/sap-pos",
    summary="Upload SAP PO CSV and sync purchase orders (ADMIN only)",
    dependencies=[Depends(require_role("ADMIN"))],
)
async def sync_sap_pos(
    file: UploadFile,
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """Accept a semicolon-delimited SAP PO CSV, parse it, and upsert into purchase_orders."""
    content = (await file.read()).decode("utf-8")
    lines, parse_errors = parse_sap_pos(content)

    if not lines and parse_errors:
        # Fatal parse failure (missing columns, empty file)
        return {"created": 0, "updated": 0, "skipped": 0, "errors": parse_errors}

    result = await upsert_sap_pos(lines, db)
    result["errors"] = parse_errors + result["errors"]
    return result


# ─── POST /admin/erp/sync/oracle-grns ───


@router.post(
    "/erp/sync/oracle-grns",
    summary="Upload Oracle GRN CSV and sync goods receipts (ADMIN only)",
    dependencies=[Depends(require_role("ADMIN"))],
)
async def sync_oracle_grns(
    file: UploadFile,
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """Accept a comma-delimited Oracle GRN CSV, parse it, and upsert into goods_receipts."""
    content = (await file.read()).decode("utf-8")
    lines, parse_errors = parse_oracle_grns(content)

    if not lines and parse_errors:
        return {"created": 0, "updated": 0, "skipped": 0, "errors": parse_errors}

    result = await upsert_oracle_grns(lines, db)
    result["errors"] = parse_errors + result["errors"]
    return result
