"""Slack/Teams webhook notification service.

Sends notifications to Slack and Teams for approval requests, decisions, and fraud alerts.
Uses only urllib.request and json — no external dependencies.
"""
import json
import logging
import urllib.request

from app.core.config import settings

logger = logging.getLogger(__name__)

# Webhook timeout (seconds)
WEBHOOK_TIMEOUT = 5


def send_approval_request(
    invoice_number: str,
    vendor_name: str,
    amount: float,
    currency: str,
    approver_email: str,
    approve_url: str,
    reject_url: str,
) -> None:
    """Send approval request notification to Slack/Teams.

    Notifies the approver of a pending invoice awaiting their decision via
    configured Slack and/or Teams webhooks. Does nothing if no webhooks are configured.

    Args:
        invoice_number: Invoice ID or number.
        vendor_name: Name of the vendor/supplier.
        amount: Invoice amount (numeric).
        currency: Currency code (e.g., "USD", "EUR").
        approver_email: Email address of the approver.
        approve_url: URL to approve invoice (includes secure token).
        reject_url: URL to reject invoice (includes secure token).

    Returns:
        None. Notification delivery is fire-and-forget; errors are logged but not raised.
    """
    # Return immediately if both webhooks are not configured
    if not settings.SLACK_WEBHOOK_URL and not settings.TEAMS_WEBHOOK_URL:
        return

    message = (
        f"Invoice {invoice_number} from {vendor_name} ({currency} {amount:.2f}) "
        f"awaits approval by {approver_email}"
    )

    if settings.SLACK_WEBHOOK_URL:
        _send_slack(message)

    if settings.TEAMS_WEBHOOK_URL:
        _send_teams(message)


def send_approval_decision(
    invoice_number: str,
    decision: str,
    actor_email: str,
    notes: str | None = None,
) -> None:
    """Send approval decision notification to Slack/Teams.

    Notifies stakeholders that an invoice has been approved or rejected via
    configured Slack and/or Teams webhooks. Does nothing if no webhooks are configured.

    Args:
        invoice_number: Invoice ID or number.
        decision: Decision outcome, either "approved" or "rejected".
        actor_email: Email address of the person who made the decision.
        notes: Optional notes explaining the decision. Appended to the message if provided.

    Returns:
        None. Notification delivery is fire-and-forget; errors are logged but not raised.
    """
    # Return immediately if both webhooks are not configured
    if not settings.SLACK_WEBHOOK_URL and not settings.TEAMS_WEBHOOK_URL:
        return

    message = f"Invoice {invoice_number} has been {decision} by {actor_email}"
    if notes:
        message += f". Notes: {notes}"

    if settings.SLACK_WEBHOOK_URL:
        _send_slack(message)

    if settings.TEAMS_WEBHOOK_URL:
        _send_teams(message)


def send_fraud_alert(
    invoice_number: str,
    vendor_name: str,
    fraud_score: int,
    risk_level: str,
    signals: list[str],
) -> None:
    """Send fraud alert notification to Slack/Teams.

    Notifies the fraud team of high or critical-risk invoices detected by the fraud
    scoring engine. Alerts are only sent if risk_level is "HIGH" or "CRITICAL"; lower
    risks are silently dropped. Configured via Slack and/or Teams webhooks.

    Args:
        invoice_number: Invoice ID or number.
        vendor_name: Name of the vendor/supplier.
        fraud_score: Fraud risk score on a 0-100 scale.
        risk_level: Risk category: "LOW", "MEDIUM", "HIGH", or "CRITICAL".
            Only "HIGH" and "CRITICAL" trigger notifications.
        signals: List of triggered fraud detection signals (e.g., ["duplicate_vendor", "amount_anomaly"]).
            If empty, shown as "none" in the alert.

    Returns:
        None. Notification delivery is fire-and-forget; errors are logged but not raised.
    """
    # Return immediately if both webhooks are not configured
    if not settings.SLACK_WEBHOOK_URL and not settings.TEAMS_WEBHOOK_URL:
        return

    # Only send for HIGH or CRITICAL risk
    if risk_level not in ("HIGH", "CRITICAL"):
        return

    message = (
        f"⚠️  Fraud Alert: Invoice {invoice_number} from {vendor_name} "
        f"has {risk_level} risk (score: {fraud_score}/100). "
        f"Signals: {', '.join(signals) if signals else 'none'}"
    )

    if settings.SLACK_WEBHOOK_URL:
        _send_slack(message)

    if settings.TEAMS_WEBHOOK_URL:
        _send_teams(message)


# ─── Internal helpers ───


def _send_slack(message: str) -> None:
    """Post a message to Slack via configured webhook.

    Internal helper that sends a simple JSON payload to the Slack incoming webhook URL.
    Errors (network, timeout, invalid URL) are caught and logged; exceptions are not raised.

    Args:
        message: Text message to send to Slack.

    Returns:
        None. Delivery errors are logged but not propagated.
    """
    try:
        payload = json.dumps({"text": message})
        req = urllib.request.Request(
            settings.SLACK_WEBHOOK_URL,
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=WEBHOOK_TIMEOUT) as response:
            response.read()
        logger.debug("Slack notification sent: %s", message)
    except Exception as e:
        logger.error("Failed to send Slack notification: %s", e)


def _send_teams(message: str) -> None:
    """Post a message to Teams via configured webhook.

    Internal helper that sends a MessageCard JSON payload to the Teams incoming webhook URL.
    Errors (network, timeout, invalid URL) are caught and logged; exceptions are not raised.

    Args:
        message: Text message to include in the Teams MessageCard.

    Returns:
        None. Delivery errors are logged but not propagated.
    """
    try:
        payload = json.dumps({
            "@type": "MessageCard",
            "text": message,
        })
        req = urllib.request.Request(
            settings.TEAMS_WEBHOOK_URL,
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=WEBHOOK_TIMEOUT) as response:
            response.read()
        logger.debug("Teams notification sent: %s", message)
    except Exception as e:
        logger.error("Failed to send Teams notification: %s", e)
