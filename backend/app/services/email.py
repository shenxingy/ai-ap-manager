"""Email notification service — console mock for MVP (MAIL_ENABLED=False).

When MAIL_ENABLED is False, email content is printed to logs instead of
being sent via SMTP. Set MAIL_ENABLED=True to wire a real transport.
"""
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


# ─── Approval request email ───

def send_approval_request_email(
    task,
    invoice,
    approve_url: str,
    reject_url: str,
) -> None:
    """Send (or mock-log) an approval request email to the approver.

    Args:
        task: ApprovalTask ORM object (must have .approver_id).
        invoice: Invoice ORM object (invoice_number, vendor_name_raw, total_amount).
        approve_url: Full URL for one-click approval via email token.
        reject_url: Full URL for one-click rejection via email token.
    """
    invoice_number = getattr(invoice, "invoice_number", None) or str(invoice.id)
    vendor_name = getattr(invoice, "vendor_name_raw", None) or "Unknown Vendor"
    total_amount = getattr(invoice, "total_amount", None)
    amount_str = f"${float(total_amount):,.2f}" if total_amount is not None else "N/A"

    if not settings.MAIL_ENABLED:
        logger.info(
            "\n"
            "=== APPROVAL REQUEST EMAIL ===\n"
            "To: approver@example.com\n"
            "Subject: Action Required: Invoice %s — %s\n"
            "Approve: %s\n"
            "Reject:  %s\n"
            "==============================",
            invoice_number,
            amount_str,
            approve_url,
            reject_url,
        )
        return

    # Real SMTP path (not implemented in MVP)
    logger.warning(
        "MAIL_ENABLED=True but SMTP transport is not configured. "
        "Falling back to console log for invoice %s.",
        invoice_number,
    )
    logger.info(
        "APPROVAL EMAIL (unsent): invoice=%s vendor=%s amount=%s approve=%s reject=%s",
        invoice_number, vendor_name, amount_str, approve_url, reject_url,
    )
