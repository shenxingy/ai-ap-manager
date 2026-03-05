"""SAP CSV connector — parse and upsert POs from SAP semicolon-delimited export."""
import csv
import io
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

REQUIRED_COLUMNS = {
    "PO_NUMBER",
    "VENDOR_CODE",
    "VENDOR_NAME",
    "LINE_NUMBER",
    "DESCRIPTION",
    "QUANTITY",
    "UNIT_PRICE",
    "CURRENCY",
}


# ─── parse_sap_pos ───


def parse_sap_pos(file_content: str) -> tuple[list[dict], list[str]]:
    """Parse semicolon-delimited SAP PO CSV export.

    Returns (valid_lines, errors). Validates required columns and numeric fields.
    Skips invalid rows and appends an error message for each.
    """
    reader = csv.DictReader(io.StringIO(file_content), delimiter=";")
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
        po_num = row.get("PO_NUMBER", "")

        try:
            quantity = float(row["QUANTITY"])
        except (ValueError, KeyError):
            errors.append(f"Row {i}: QUANTITY is not numeric (PO={po_num})")
            continue

        try:
            unit_price = float(row["UNIT_PRICE"])
        except (ValueError, KeyError):
            errors.append(f"Row {i}: UNIT_PRICE is not numeric (PO={po_num})")
            continue

        valid.append(
            {
                "po_number": po_num,
                "vendor_code": row.get("VENDOR_CODE", ""),
                "vendor_name": row.get("VENDOR_NAME", ""),
                "line_number": row.get("LINE_NUMBER", ""),
                "description": row.get("DESCRIPTION", ""),
                "quantity": quantity,
                "unit_price": unit_price,
                "currency": row.get("CURRENCY", "USD") or "USD",
            }
        )

    return valid, errors


# ─── upsert_sap_pos ───


async def upsert_sap_pos(lines: list[dict], db: AsyncSession) -> dict:
    """Upsert SAP PO lines into purchase_orders and po_line_items.

    Groups rows by PO_NUMBER, finds/creates vendors, then upserts PO headers
    and line items using raw SQL.

    Returns {"created": N, "updated": N, "skipped": N, "errors": []}.
    """
    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    # Group lines by PO number
    pos: dict[str, list[dict]] = {}
    for line in lines:
        po_num = line["po_number"]
        if not po_num:
            errors.append(f"Skipped line with empty PO_NUMBER: {line}")
            skipped += 1
            continue
        pos.setdefault(po_num, []).append(line)

    for po_number, po_lines in pos.items():
        first = po_lines[0]
        vendor_name = first["vendor_name"]
        currency = first["currency"]

        # Find or create vendor by name
        try:
            vendor_result = await db.execute(
                text(
                    "SELECT id FROM vendors "
                    "WHERE name = :name AND deleted_at IS NULL LIMIT 1"
                ),
                {"name": vendor_name},
            )
            vendor_row = vendor_result.fetchone()
            if vendor_row:
                vendor_id = vendor_row[0]
            else:
                new_vendor_id = uuid.uuid4()
                now = datetime.now(UTC)
                await db.execute(
                    text(
                        "INSERT INTO vendors "
                        "(id, name, currency, payment_terms, is_active, created_at, updated_at) "
                        "VALUES (:id, :name, :currency, 30, true, :now, :now)"
                    ),
                    {
                        "id": new_vendor_id,
                        "name": vendor_name,
                        "currency": currency,
                        "now": now,
                    },
                )
                vendor_id = new_vendor_id
        except Exception as exc:
            errors.append(f"PO {po_number}: vendor lookup/create failed: {exc}")
            skipped += 1
            continue

        # Compute total_amount for this PO header
        total_amount = sum(line["quantity"] * line["unit_price"] for line in po_lines)

        # Check if PO already exists to track created vs updated
        existing_result = await db.execute(
            text("SELECT id FROM purchase_orders WHERE po_number = :po_number"),
            {"po_number": po_number},
        )
        existing = existing_result.fetchone()
        is_new = existing is None

        try:
            now = datetime.now(UTC)
            await db.execute(
                text(
                    "INSERT INTO purchase_orders "
                    "(id, po_number, vendor_id, status, currency, total_amount, created_at, updated_at) "
                    "VALUES (:id, :po_number, :vendor_id, 'open', :currency, :total_amount, :now, :now) "
                    "ON CONFLICT (po_number) DO UPDATE SET "
                    "vendor_id = EXCLUDED.vendor_id, "
                    "currency = EXCLUDED.currency, "
                    "total_amount = EXCLUDED.total_amount, "
                    "updated_at = EXCLUDED.updated_at"
                ),
                {
                    "id": uuid.uuid4(),
                    "po_number": po_number,
                    "vendor_id": vendor_id,
                    "currency": currency,
                    "total_amount": total_amount,
                    "now": now,
                },
            )
            # Fetch actual po_id (may differ from :id if ON CONFLICT path taken)
            po_result = await db.execute(
                text("SELECT id FROM purchase_orders WHERE po_number = :po_number"),
                {"po_number": po_number},
            )
            po_id = po_result.fetchone()[0]

            if is_new:
                created += 1
            else:
                updated += 1
        except Exception as exc:
            errors.append(f"PO {po_number}: upsert failed: {exc}")
            skipped += 1
            continue

        # Upsert line items (no unique constraint on po_id+line_number — use SELECT+INSERT/UPDATE)
        for line in po_lines:
            line_num_str = line["line_number"]
            try:
                line_num = int(line_num_str) if line_num_str else 0
            except ValueError:
                errors.append(
                    f"PO {po_number}: invalid LINE_NUMBER '{line_num_str}'"
                )
                continue

            try:
                now = datetime.now(UTC)
                existing_line = await db.execute(
                    text(
                        "SELECT id FROM po_line_items "
                        "WHERE po_id = :po_id AND line_number = :line_number"
                    ),
                    {"po_id": po_id, "line_number": line_num},
                )
                existing_line_row = existing_line.fetchone()

                if existing_line_row:
                    await db.execute(
                        text(
                            "UPDATE po_line_items SET "
                            "description = :description, "
                            "quantity = :quantity, "
                            "unit_price = :unit_price, "
                            "updated_at = :now "
                            "WHERE id = :id"
                        ),
                        {
                            "description": line["description"],
                            "quantity": line["quantity"],
                            "unit_price": line["unit_price"],
                            "now": now,
                            "id": existing_line_row[0],
                        },
                    )
                else:
                    await db.execute(
                        text(
                            "INSERT INTO po_line_items "
                            "(id, po_id, line_number, description, quantity, unit_price, "
                            "received_qty, invoiced_qty, created_at, updated_at) "
                            "VALUES (:id, :po_id, :line_number, :description, :quantity, "
                            ":unit_price, 0, 0, :now, :now)"
                        ),
                        {
                            "id": uuid.uuid4(),
                            "po_id": po_id,
                            "line_number": line_num,
                            "description": line["description"],
                            "quantity": line["quantity"],
                            "unit_price": line["unit_price"],
                            "now": now,
                        },
                    )
            except Exception as exc:
                errors.append(
                    f"PO {po_number} line {line_num}: upsert failed: {exc}"
                )

    await db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}
