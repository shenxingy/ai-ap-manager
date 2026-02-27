"""Celery task: extract AP matching rules from an uploaded policy document via LLM."""
import io
import json
import logging
import time
import uuid

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


# ─── Text extraction helpers ───

def _extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from file bytes.

    - PDF: uses pdfminer.six (high-fidelity text layer extraction)
    - DOCX: basic XML extraction via zipfile
    - TXT / other: UTF-8 decode
    """
    fname_lower = filename.lower()

    if fname_lower.endswith(".pdf"):
        return _extract_pdf_text(file_bytes)
    elif fname_lower.endswith(".docx"):
        return _extract_docx_text(file_bytes)
    else:
        # Plain text or unknown — decode as UTF-8
        try:
            return file_bytes.decode("utf-8", errors="replace")
        except Exception:
            return ""


def _extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from PDF using pdfminer.six; fallback to raw bytes decode on failure."""
    try:
        from pdfminer.high_level import extract_text
        stream = io.BytesIO(file_bytes)
        text = extract_text(stream)
        return text or ""
    except ImportError:
        logger.warning("pdfminer.six not installed; falling back to raw text extraction")
        return file_bytes.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("PDF text extraction failed: %s", exc)
        return ""


def _extract_docx_text(file_bytes: bytes) -> str:
    """Extract text from a DOCX file by reading the embedded XML."""
    import zipfile
    import re

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            with z.open("word/document.xml") as f:
                xml_content = f.read().decode("utf-8", errors="replace")
        # Strip XML tags to get plain text
        text = re.sub(r"<[^>]+>", " ", xml_content)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception as exc:
        logger.warning("DOCX text extraction failed: %s", exc)
        return ""


# ─── LLM call ───

SYSTEM_PROMPT = (
    "You are an AP policy parser. "
    "Extract matching tolerance rules from the provided AP policy text and return them as JSON. "
    "Output ONLY a JSON object with these keys: "
    "tolerance_pct (float, percentage variance allowed for amount matching, e.g. 0.05 for 5%), "
    "max_line_variance (float, max variance per line item in absolute currency units), "
    "auto_approve_threshold (float, invoice total below which auto-approval is allowed), "
    "notes (string, any caveats or additional policy notes). "
    "If a value cannot be determined from the text, use null. "
    "Return only the JSON object, no other text."
)

USER_PROMPT_TEMPLATE = (
    "Please extract the AP matching tolerance rules from the following policy document:\n\n{text}"
)


def _call_llm(db, policy_text: str, rule_version_id: uuid.UUID) -> dict:
    """Call Claude LLM to extract rule config from policy text.

    Logs the call to ai_call_logs. Returns parsed JSON dict.
    """
    from anthropic import Anthropic
    from app.core.config import settings
    from app.models.audit import AICallLog

    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    # Truncate text to avoid excessive token usage (keep ~15K chars)
    truncated_text = policy_text[:15000]
    user_message = USER_PROMPT_TEMPLATE.format(text=truncated_text)

    request_payload = {
        "model": settings.ANTHROPIC_MODEL,
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_message}],
    }

    start_ts = time.monotonic()
    call_status = "success"
    error_message = None
    response_text = ""
    prompt_tokens = 0
    completion_tokens = 0

    try:
        response = client.messages.create(**request_payload)
        response_text = response.content[0].text if response.content else ""
        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens
    except Exception as exc:
        call_status = "error"
        error_message = str(exc)
        logger.error("LLM call failed for rule version %s: %s", rule_version_id, exc)

    latency_ms = int((time.monotonic() - start_ts) * 1000)

    # Log to ai_call_logs
    log_entry = AICallLog(
        call_type="policy_parse",
        model=settings.ANTHROPIC_MODEL,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        status=call_status,
        error_message=error_message,
        request_json=json.dumps(request_payload, default=str),
        response_json=json.dumps({"text": response_text}) if response_text else None,
    )
    db.add(log_entry)
    db.flush()

    if call_status == "error":
        return {}

    # Parse JSON from response
    try:
        extracted = json.loads(response_text)
        if not isinstance(extracted, dict):
            raise ValueError("LLM returned non-dict JSON")
        return extracted
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse LLM response as JSON for version %s: %s", rule_version_id, exc)
        return {"notes": f"Parse error: {exc}. Raw: {response_text[:500]}"}


# ─── Main Celery task ───

@celery_app.task(bind=True, name="rules_tasks.extract_rules_from_policy", max_retries=2)
def extract_rules_from_policy(self, version_id_str: str, file_key: str) -> dict:
    """Extract AP matching rules from a policy document stored in MinIO.

    Steps:
    1. Load file bytes from MinIO
    2. Extract text (PDF via pdfminer, DOCX via zipfile, TXT via decode)
    3. Call Claude LLM with system prompt "You are an AP policy parser..."
    4. Log to ai_call_logs
    5. Update RuleVersion: config_json=extracted, status=in_review, ai_extracted=True
    6. Write audit log: action=policy_parsed_by_ai
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker, Session
    from app.core.config import settings
    from app.models.rule import RuleVersion
    from app.services import storage as storage_svc
    from app.services import audit as audit_svc

    logger.info("extract_rules_from_policy started: version=%s file=%s", version_id_str, file_key)

    engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db: Session = SessionLocal()

    version_uuid = uuid.UUID(version_id_str)
    filename = file_key.rsplit("/", 1)[-1]  # last path segment

    try:
        # 1. Fetch RuleVersion
        from sqlalchemy import select
        version = db.execute(
            select(RuleVersion).where(RuleVersion.id == version_uuid)
        ).scalar_one_or_none()

        if version is None:
            logger.error("RuleVersion %s not found", version_id_str)
            return {"version_id": version_id_str, "status": "not_found"}

        # 2. Download file from MinIO
        try:
            file_bytes = storage_svc.download_file(
                bucket=settings.MINIO_BUCKET_NAME,
                object_name=file_key,
            )
        except Exception as exc:
            logger.warning("MinIO download failed for %s: %s", file_key, exc)
            raise self.retry(exc=exc, countdown=30)

        # 3. Extract text
        policy_text = _extract_text_from_bytes(file_bytes, filename)
        logger.info(
            "Text extracted from %s: %d chars", filename, len(policy_text)
        )

        if not policy_text.strip():
            logger.warning("No text extracted from %s — storing empty config", filename)
            extracted_config = {"notes": "No text could be extracted from the document."}
        else:
            # 4. Call LLM
            extracted_config = _call_llm(db, policy_text, version_uuid)

        db.commit()  # flush ai_call_log

        # 5. Update RuleVersion
        version.config_json = json.dumps(extracted_config, default=str)
        version.status = "in_review"
        version.ai_extracted = True

        # 6. Write audit log
        audit_svc.log(
            db=db,
            action="policy_parsed_by_ai",
            entity_type="rule_version",
            entity_id=version_uuid,
            after={"status": "in_review", "ai_extracted": True, "config": extracted_config},
            notes=f"Policy text length: {len(policy_text)} chars; file: {file_key}",
        )
        db.commit()

        logger.info(
            "extract_rules_from_policy complete: version=%s config=%s",
            version_id_str, list(extracted_config.keys()),
        )
        return {"version_id": version_id_str, "status": "in_review", "config_keys": list(extracted_config.keys())}

    except Exception as exc:
        db.rollback()
        logger.exception("extract_rules_from_policy failed for %s: %s", version_id_str, exc)
        raise self.retry(exc=exc, countdown=60)

    finally:
        db.close()
