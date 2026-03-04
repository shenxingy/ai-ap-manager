"""Dual-pass LLM invoice extraction.

All LLM calls are logged to ai_call_logs. When the configured provider is 'none'
or unavailable, the extractor returns an empty result rather than crashing.
"""
import json
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AICallLog

logger = logging.getLogger(__name__)

# ─── Prompts ───

_PASS1_PROMPT = """Extract all invoice fields from the following OCR text. \
Return ONLY a valid JSON object with these keys (use null for missing fields):
{
  "invoice_number": string|null,
  "vendor_name": string|null,
  "vendor_address": string|null,
  "invoice_date": string|null,
  "due_date": string|null,
  "currency": string|null,
  "subtotal": number|null,
  "tax_amount": number|null,
  "total_amount": number|null,
  "payment_terms": string|null,
  "line_items": [
    {
      "line_number": integer,
      "description": string,
      "quantity": number|null,
      "unit_price": number|null,
      "unit": string|null,
      "line_total": number|null
    }
  ]
}

OCR TEXT:
"""

_PASS2_PROMPT = """You are a senior AP auditor reviewing an invoice. \
Independently extract all key financial fields from the text below. \
Return ONLY a valid JSON object with the same schema as Pass 1:
{
  "invoice_number": string|null,
  "vendor_name": string|null,
  "vendor_address": string|null,
  "invoice_date": string|null,
  "due_date": string|null,
  "currency": string|null,
  "subtotal": number|null,
  "tax_amount": number|null,
  "total_amount": number|null,
  "payment_terms": string|null,
  "line_items": [
    {
      "line_number": integer,
      "description": string,
      "quantity": number|null,
      "unit_price": number|null,
      "unit": string|null,
      "line_total": number|null
    }
  ]
}

INVOICE TEXT:
"""

# Fields compared between passes (line_items compared shallowly by count)
_SCALAR_FIELDS = [
    "invoice_number",
    "vendor_name",
    "vendor_address",
    "invoice_date",
    "due_date",
    "currency",
    "subtotal",
    "tax_amount",
    "total_amount",
    "payment_terms",
]


# ─── Internal helpers ───

def _call_llm(prompt: str, raw_text: str) -> tuple[str, int, int, int, str]:
    """Call LLM via provider abstraction. Returns (text, prompt_tokens, completion_tokens, latency_ms, model)."""
    from app.ai.llm_client import get_llm_client

    client = get_llm_client("extraction")
    full_prompt = prompt + raw_text
    resp = client.complete([{"role": "user", "content": full_prompt}], max_tokens=2048)
    return resp.text, resp.prompt_tokens, resp.completion_tokens, resp.latency_ms, resp.model


def _parse_json_response(text: str) -> dict:
    """Extract JSON from the model response, tolerating markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` fences
        lines = text.split("\n")
        inner = [l for l in lines if not l.startswith("```")]
        text = "\n".join(inner).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse LLM JSON: %s — raw: %.200s", exc, text)
        return {}


def _log_ai_call(
    db: Session,
    invoice_id: uuid.UUID | None,
    call_type: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    model: str,
    status: str = "success",
    error_message: str | None = None,
    request_snippet: str | None = None,
    response_snippet: str | None = None,
) -> None:
    entry = AICallLog(
        invoice_id=invoice_id,
        call_type=call_type,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        status=status,
        error_message=error_message,
        request_json=request_snippet,
        response_json=response_snippet,
    )
    db.add(entry)
    db.flush()


# ─── Public API ───

def run_extraction_pass(
    db: Session,
    raw_text: str,
    pass_number: int,
    invoice_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Call Claude for one extraction pass.

    Returns a dict with keys:
        fields: dict — extracted invoice fields
        tokens_prompt: int
        tokens_completion: int
        latency_ms: int
        error: str | None
    """
    call_type = f"extraction_pass_{pass_number}"
    prompt = _PASS1_PROMPT if pass_number == 1 else _PASS2_PROMPT

    try:
        response_text, p_tokens, c_tokens, latency_ms, model = _call_llm(prompt, raw_text)
        fields = _parse_json_response(response_text)
        _log_ai_call(
            db=db,
            invoice_id=invoice_id,
            call_type=call_type,
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
            latency_ms=latency_ms,
            model=model,
            status="success",
            request_snippet=raw_text[:500] if raw_text else None,
            response_snippet=response_text[:1000] if response_text else None,
        )
        return {
            "fields": fields,
            "tokens_prompt": p_tokens,
            "tokens_completion": c_tokens,
            "latency_ms": latency_ms,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM extraction pass %d failed: %s", pass_number, exc)
        _log_ai_call(
            db=db,
            invoice_id=invoice_id,
            call_type=call_type,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
            model="unknown",
            status="error",
            error_message="Extraction failed. See server logs.",
        )
        return {
            "fields": {},
            "tokens_prompt": 0,
            "tokens_completion": 0,
            "latency_ms": 0,
            "error": str(exc),
        }


def compare_passes(pass1_fields: dict, pass2_fields: dict) -> list[str]:
    """Return list of scalar field names that differ between the two passes."""
    discrepancies: list[str] = []
    for field in _SCALAR_FIELDS:
        v1 = pass1_fields.get(field)
        v2 = pass2_fields.get(field)
        # Normalize to string for comparison (avoids float repr issues)
        if str(v1).strip().lower() != str(v2).strip().lower():
            discrepancies.append(field)
    # Compare line_item count as a proxy
    li1 = pass1_fields.get("line_items") or []
    li2 = pass2_fields.get("line_items") or []
    if len(li1) != len(li2):
        discrepancies.append("line_items_count")
    return discrepancies


def merge_passes(pass1_fields: dict, pass2_fields: dict, discrepancies: list[str]) -> dict:
    """Merge two extraction passes. Pass 1 wins for non-discrepant fields.

    For discrepant fields, pass1 value is kept (primary extraction) but
    discrepancy_fields list will flag them for human review.
    """
    merged = dict(pass1_fields)
    # Ensure line_items is a list
    if not merged.get("line_items"):
        merged["line_items"] = pass2_fields.get("line_items") or []
    return merged
