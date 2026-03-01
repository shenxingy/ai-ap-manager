"""Slack/Teams webhook notification service.

Sends notifications to Slack and Teams for approval requests, decisions, and fraud alerts.
Uses only urllib.request and json — no external dependencies.
"""
import json
import logging
import urllib.request
from typing import Optional

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

    Args:
        invoice_number: Invoice ID
        vendor_name: Vendor name
        amount: Invoice amount
        currency: Currency code (e.g., "USD")
        approver_email: Email of the approver
        approve_url: URL to approve (with token)
        reject_url: URL to reject (with token)
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
    notes: Optional[str] = None,
) -> None:
    """Send approval decision notification to Slack/Teams.

    Args:
        invoice_number: Invoice ID
        decision: "approved" or "rejected"
        actor_email: Email of the person who made the decision
        notes: Optional decision notes
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

    Only sends if risk_level is "HIGH" or "CRITICAL".

    Args:
        invoice_number: Invoice ID
        vendor_name: Vendor name
        fraud_score: Fraud score (0-100)
        risk_level: Risk level ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        signals: List of triggered fraud signals
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
    """POST JSON to Slack webhook."""
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
    """POST JSON to Teams webhook."""
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
