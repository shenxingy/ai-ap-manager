"""Unit tests for policy upload text extraction and LLM JSON parsing.

Tests the helper functions in app/workers/rules_tasks.py:
  - _extract_text_from_bytes: TXT, DOCX, PDF-fallback
  - _extract_docx_text: DOCX XML extraction
  - _call_llm: JSON parsing, error handling, api_call_log writes
  - extract_rules_from_policy: state transition draft → in_review
"""
import io
import json
import uuid
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from app.workers.rules_tasks import (
    _extract_text_from_bytes,
    _extract_docx_text,
    _call_llm,
)


# ─── _extract_text_from_bytes ─────────────────────────────────────────────────

def test_extract_txt_returns_utf8():
    text = "Invoice tolerance: 5%\nAuto-approve below $5,000"
    result = _extract_text_from_bytes(text.encode("utf-8"), "policy.txt")
    assert "Invoice tolerance" in result
    assert "5,000" in result


def test_extract_unknown_extension_falls_back_to_utf8():
    text = "policy content here"
    result = _extract_text_from_bytes(text.encode("utf-8"), "policy.md")
    assert result == text


def _build_minimal_docx(content: str) -> bytes:
    """Create a minimal in-memory DOCX with the given text in the document XML."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{content}</w:t></w:r></w:p></w:body>"
        "</w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_extract_docx_text():
    docx_bytes = _build_minimal_docx("tolerance 3%")
    result = _extract_docx_text(docx_bytes)
    assert "tolerance 3%" in result


def test_extract_docx_text_invalid_bytes():
    """Invalid DOCX bytes return empty string, not an exception."""
    result = _extract_docx_text(b"not a zip file")
    assert result == ""


def test_extract_docx_via_dispatch():
    docx_bytes = _build_minimal_docx("approval threshold 10000")
    result = _extract_text_from_bytes(docx_bytes, "policy.docx")
    assert "approval threshold 10000" in result


# ─── _call_llm JSON parsing ───────────────────────────────────────────────────
# Anthropic is imported lazily inside _call_llm, so we patch the source module.

def _make_db_for_llm() -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    return db


def _mock_anthropic_response(text: str) -> MagicMock:
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    return response


def test_call_llm_clean_json():
    """LLM returns valid JSON → parsed dict returned."""
    expected = {"tolerance_pct": 0.03, "auto_approve_threshold": 5000.0, "notes": None}
    db = _make_db_for_llm()
    version_id = uuid.uuid4()

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_anthropic_response(
        json.dumps(expected)
    )

    # Anthropic is imported inside _call_llm via "from anthropic import Anthropic"
    with patch("anthropic.Anthropic", return_value=mock_client):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = "test-key"
            mock_settings.ANTHROPIC_MODEL = "claude-sonnet-4-6"
            result = _call_llm(db, "Invoice tolerance is 3%", version_id)

    assert result["tolerance_pct"] == 0.03
    assert result["auto_approve_threshold"] == 5000.0
    db.add.assert_called_once()
    db.flush.assert_called_once()


def test_call_llm_invalid_json_returns_notes():
    """LLM returns non-JSON text → result dict has 'notes' key with raw snippet."""
    db = _make_db_for_llm()
    version_id = uuid.uuid4()

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_anthropic_response(
        "Sorry, I cannot extract rules from this document."
    )

    with patch("anthropic.Anthropic", return_value=mock_client):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = "test-key"
            mock_settings.ANTHROPIC_MODEL = "claude-sonnet-4-6"
            result = _call_llm(db, "some policy text", version_id)

    assert "notes" in result
    assert "Parse error" in result["notes"]


def test_call_llm_api_error_returns_empty():
    """LLM API call raises exception → empty dict returned, ai_call_log still written."""
    db = _make_db_for_llm()
    version_id = uuid.uuid4()

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API unavailable")

    with patch("anthropic.Anthropic", return_value=mock_client):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = "test-key"
            mock_settings.ANTHROPIC_MODEL = "claude-sonnet-4-6"
            result = _call_llm(db, "some policy text", version_id)

    assert result == {}
    db.add.assert_called_once()  # ai_call_log still logged


# ─── State transition: draft → in_review ─────────────────────────────────────
# extract_rules_from_policy uses lazy imports inside the function body.
# We patch the modules at their canonical paths.

def test_extract_rules_state_transition():
    """After extraction, RuleVersion.status is in_review and ai_extracted=True."""
    version_id = uuid.uuid4()
    version_id_str = str(version_id)
    file_key = "policies/test.txt"
    extracted_config = {"tolerance_pct": 0.03, "auto_approve_threshold": 5000.0}

    mock_version = MagicMock()
    mock_version.id = version_id
    mock_version.status = "draft"
    mock_version.ai_extracted = False
    mock_version.config_json = None

    # DB mock: execute().scalar_one_or_none() returns mock_version
    db = MagicMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = mock_version
    db.execute.return_value = exec_result
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.close = MagicMock()

    mock_engine = MagicMock()
    # session_factory() must return db directly
    mock_session_factory = MagicMock()
    mock_session_factory.return_value = db

    with patch("sqlalchemy.create_engine", return_value=mock_engine):
        with patch("sqlalchemy.orm.sessionmaker", return_value=mock_session_factory):
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.DATABASE_URL_SYNC = "postgresql://mock"
                mock_settings.MINIO_BUCKET_NAME = "ap-documents"
                # storage_svc imported lazily as module; patch the function on the module
                with patch("app.services.storage.download_file", return_value=b"Invoice tolerance 3%"):
                    with patch("app.workers.rules_tasks._call_llm", return_value=extracted_config):
                        with patch("app.services.audit.log"):
                            from app.workers.rules_tasks import extract_rules_from_policy
                            try:
                                extract_rules_from_policy.run(version_id_str, file_key)
                            except Exception:
                                pass  # Celery retry may raise; state mutation precedes it

    assert mock_version.status == "in_review"
    assert mock_version.ai_extracted is True
    assert json.loads(mock_version.config_json) == extracted_config
