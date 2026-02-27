"""Unit tests for approval token generation and verification.

Tests cover:
  - create_approval_token + verify_approval_token round-trip
  - Expired token check (via process_approval_decision)
  - Reuse rejection check (via process_approval_decision)
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.core.security import create_approval_token, verify_approval_token
from app.services.approval import process_approval_decision, _compute_token_hash


# ─── Token HMAC tests ─────────────────────────────────────────────────────────

def test_create_and_verify_token():
    """Generated token verifies successfully against its own stored hash."""
    task_id = str(uuid.uuid4())
    raw_token, token_hash = create_approval_token(task_id, "approve")

    assert raw_token is not None
    assert token_hash is not None
    assert verify_approval_token(raw_token, token_hash) is True


def test_tampered_token_fails_verification():
    """A modified raw token does not verify against the original hash."""
    task_id = str(uuid.uuid4())
    raw_token, token_hash = create_approval_token(task_id, "approve")

    tampered = raw_token + "-tampered"
    assert verify_approval_token(tampered, token_hash) is False


# ─── process_approval_decision: expired and reused tokens ─────────────────────

def _make_task_mock(task_id: uuid.UUID) -> MagicMock:
    task = MagicMock()
    task.id = task_id
    task.status = "pending"
    task.approver_id = uuid.uuid4()
    task.approval_required_count = 1
    return task


def _make_db_for_email_decision(task: MagicMock, token_row: MagicMock) -> MagicMock:
    """DB mock for process_approval_decision(channel='email').

    Call order:
      1. ApprovalTask query → task
      2. ApprovalToken query → token_row
    """
    db = MagicMock()
    r_task = MagicMock()
    r_task.scalars.return_value.first.return_value = task
    r_token = MagicMock()
    r_token.scalars.return_value.first.return_value = token_row
    db.execute.side_effect = [r_task, r_token]
    return db


def test_expired_token():
    """process_approval_decision raises ValueError when token is expired."""
    task_id = uuid.uuid4()
    raw_token, token_hash = create_approval_token(str(task_id), "approve")

    mock_token = MagicMock()
    mock_token.token_hash = _compute_token_hash(raw_token)
    mock_token.action = "approve"
    mock_token.is_used = False
    mock_token.expires_at = datetime.now(timezone.utc) - timedelta(days=1)

    task = _make_task_mock(task_id)
    db = _make_db_for_email_decision(task, mock_token)

    with pytest.raises(ValueError, match="expired"):
        process_approval_decision(
            db=db,
            task_id=task_id,
            action="approve",
            token_raw=raw_token,
            channel="email",
        )


def test_reuse_rejected():
    """process_approval_decision raises ValueError when token is already used."""
    task_id = uuid.uuid4()
    raw_token, token_hash = create_approval_token(str(task_id), "approve")

    mock_token = MagicMock()
    mock_token.token_hash = _compute_token_hash(raw_token)
    mock_token.action = "approve"
    mock_token.is_used = True   # already used
    mock_token.expires_at = datetime.now(timezone.utc) + timedelta(days=1)

    task = _make_task_mock(task_id)
    db = _make_db_for_email_decision(task, mock_token)

    with pytest.raises(ValueError, match="already been used"):
        process_approval_decision(
            db=db,
            task_id=task_id,
            action="approve",
            token_raw=raw_token,
            channel="email",
        )
