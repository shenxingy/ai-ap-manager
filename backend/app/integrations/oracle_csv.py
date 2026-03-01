"""Oracle CSV connector — parse and upsert GRNs from Oracle comma-delimited export."""
import csv
import io
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

REQUIRED_COLUMNS = {
    "RECEIPT_NUMBER",
    "PO_NUMBER",
    "LINE_NUMBER",
    "ITEM_DESCRIPTION",
    "QUANTITY_RECEIVED",
    "RECEIVED_DATE",
}


# ─── parse_oracle_grns ───


def parse_oracle_grns(file_content: str) -> tuple[list[dict], list[str]]:
    """Parse comma-delimited Oracle GRN CSV export.

    Returns (valid_lines, errors). Validates required columns and numeric fields.
    Skips invalid rows and appends an error message for each.
    """
    reader = csv.DictReader(io.StringIO(file_content), delimiter=",")
    if not reader.fieldnames:
        return [], ["CSV has no headers"]

    headers = {f.strip() for f in reader.fieldnames}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        return [], [f"Missing required columns: {', '.join(sorted(missing))}"]

    valid: list[dict] = []
    errors: list[str] = []

    for i, raw_row in enumerate(reader, start=2):
        row = {k.strip(): (v.strip() if v else "") for k, v in raw_row.items()}
        receipt_num = row.get("RECEIPT_NUMBER", "")

        try:
            quantity_received = float(row["QUANTITY_RECEIVED"])
        except (ValueError, KeyError):
            errors.append(
                f"Row {i}: QUANTITY_RECEIVED is not numeric (RECEIPT={receipt_num})"
            )
            continue

        received_date_str = row.get("RECEIVED_DATE", "")
        if not received_date_str:
            errors.append(f"Row {i}: RECEIVED_DATE is empty (RECEIPT={receipt_num})")
            continue

        valid.append(
            {
                "receipt_number": receipt_num,
                "po_number": row.get("PO_NUMBER", ""),
                "line_number": row.get("LINE_NUMBER", ""),
                "item_description": row.get("ITEM_DESCRIPTION", ""),
                "quantity_received": quantity_received,
                "received_date": received_date_str,
            }
        )

    return valid, errors


# ─── upsert_oracle_grns ───


async def upsert_oracle_grns(lines: list[dict], db: AsyncSession) -> dict:
    """Upsert Oracle GRN lines into goods_receipts and gr_line_items.

    Groups rows by RECEIPT_NUMBER, looks up PO by PO_NUMBER (skips if not found),
    then upserts GR headers and line items.

    Returns {"created": N, "updated": N, "skipped": N, "errors": []}.
    """
    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    # Group lines by receipt number
    grns: dict[str, list[dict]] = {}
    for line in lines:
        receipt_num = line["receipt_number"]
        if not receipt_num:
            errors.append(f"Skipped line with empty RECEIPT_NUMBER: {line}")
            skipped += 1
            continue
        grns.setdefault(receipt_num, []).append(line)

    for receipt_number, gr_lines in grns.items():
        first = gr_lines[0]
        po_number = first["po_number"]
        received_date_str = first["received_date"]

        # Parse received_at — support YYYY-MM-DD and MM/DD/YYYY
        try:
            try:
                received_at = datetime.strptime(received_date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                received_at = datetime.strptime(received_date_str, "%m/%d/%Y").replace(
                    tzinfo=timezone.utc
                )
        except ValueError:
            errors.append(
                f"GRN {receipt_number}: cannot parse RECEIVED_DATE '{received_date_str}'"
            )
            skipped += 1
            continue

        # Look up PO to get po_id and vendor_id
        try:
            po_result = await db.execute(
                text(
                    "SELECT id, vendor_id FROM purchase_orders "
                    "WHERE po_number = :po_number AND deleted_at IS NULL LIMIT 1"
                ),
                {"po_number": po_number},
            )
            po_row = po_result.fetchone()
        except Exception as exc:
            errors.append(f"GRN {receipt_number}: PO lookup failed: {exc}")
            skipped += 1
            continue

        if not po_row:
            errors.append(
                f"GRN {receipt_number}: PO '{po_number}' not found — skipping"
            )
            skipped += 1
            continue

        po_id, vendor_id = po_row[0], po_row[1]

        # Check if GRN already exists
        existing_result = await db.execute(
            text(
                "SELECT id FROM goods_receipts WHERE gr_number = :gr_number"
            ),
            {"gr_number": receipt_number},
        )
        existing = existing_result.fetchone()
        is_new = existing is None

        try:
            now = datetime.now(timezone.utc)
            await db.execute(
                text(
                    "INSERT INTO goods_receipts "
                    "(id, gr_number, po_id, vendor_id, received_at, created_at, updated_at) "
                    "VALUES (:id, :gr_number, :po_id, :vendor_id, :received_at, :now, :now) "
                    "ON CONFLICT (gr_number) DO UPDATE SET "
                    "po_id = EXCLUDED.po_id, "
                    "vendor_id = EXCLUDED.vendor_id, "
                    "received_at = EXCLUDED.received_at, "
                    "updated_at = EXCLUDED.updated_at"
                ),
                {
                    "id": uuid.uuid4(),
                    "gr_number": receipt_number,
                    "po_id": po_id,
                    "vendor_id": vendor_id,
                    "received_at": received_at,
                    "now": now,
                },
            )
            # Fetch actual gr_id
            gr_result = await db.execute(
                text("SELECT id FROM goods_receipts WHERE gr_number = :gr_number"),
                {"gr_number": receipt_number},
            )
            gr_id = gr_result.fetchone()[0]

            if is_new:
                created += 1
            else:
                updated += 1
        except Exception as exc:
            errors.append(f"GRN {receipt_number}: upsert failed: {exc}")
            skipped += 1
            continue

        # Upsert line items (no unique constraint on gr_id+line_number — use SELECT+INSERT/UPDATE)
        for line in gr_lines:
            line_num_str = line["line_number"]
            try:
                line_num = int(line_num_str) if line_num_str else 0
            except ValueError:
                errors.append(
                    f"GRN {receipt_number}: invalid LINE_NUMBER '{line_num_str}'"
                )
                continue

            try:
                now = datetime.now(timezone.utc)
                existing_line = await db.execute(
                    text(
                        "SELECT id FROM gr_line_items "
                        "WHERE gr_id = :gr_id AND line_number = :line_number"
                    ),
                    {"gr_id": gr_id, "line_number": line_num},
                )
                existing_line_row = existing_line.fetchone()

                if existing_line_row:
                    await db.execute(
                        text(
                            "UPDATE gr_line_items SET "
                            "description = :description, "
                            "quantity = :quantity, "
                            "updated_at = :now "
                            "WHERE id = :id"
                        ),
                        {
                            "description": line["item_description"],
                            "quantity": line["quantity_received"],
                            "now": now,
                            "id": existing_line_row[0],
                        },
                    )
                else:
                    await db.execute(
                        text(
                            "INSERT INTO gr_line_items "
                            "(id, gr_id, line_number, description, quantity, created_at, updated_at) "
                            "VALUES (:id, :gr_id, :line_number, :description, :quantity, :now, :now)"
                        ),
                        {
                            "id": uuid.uuid4(),
                            "gr_id": gr_id,
                            "line_number": line_num,
                            "description": line["item_description"],
                            "quantity": line["quantity_received"],
                            "now": now,
                        },
                    )
            except Exception as exc:
                errors.append(
                    f"GRN {receipt_number} line {line_num}: upsert failed: {exc}"
                )

    await db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}
