"""Ask AI endpoint — natural language queries over AP data with SQL whitelist safety."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.db.session import get_session
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Whitelist: only these tables may be queried ───

ALLOWED_TABLES = frozenset([
    "invoices",
    "invoice_line_items",
    "exception_records",
    "approval_tasks",
    "vendors",
])

# Keywords that indicate DML/DDL — always blocked
BLOCKED_KEYWORDS = frozenset([
    "insert", "update", "delete", "drop", "truncate",
    "alter", "create", "grant", "revoke", "execute",
    "--", "/*", "*/", ";",
])


class AskAiRequest(BaseModel):
    question: str


class AskAiResponse(BaseModel):
    question: str
    answer: str
    sql_used: str | None = None
    row_count: int | None = None


@router.post(
    "",
    response_model=AskAiResponse,
    summary="Ask a natural language question about AP data (AP_ANALYST+)",
)
async def ask_ai(
    body: AskAiRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_ANALYST", "AP_MANAGER", "ADMIN", "AUDITOR"))],
):
    """Natural language query against AP data.

    The LLM generates a SELECT-only SQL query. We validate it against a whitelist
    of allowed tables and reject any DML/DDL. Results are returned as a summary.
    """
    from app.core.config import settings

    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured (ANTHROPIC_API_KEY not set).",
        )

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty.")

    # Step 1: Ask LLM to generate SQL
    sql_query = await _generate_sql(question, settings)

    # Step 2: Validate SQL safety
    _validate_sql_safety(sql_query)

    # Step 3: Execute and summarize
    try:
        result = await db.execute(text(sql_query))
        rows = result.fetchmany(50)  # Cap at 50 rows
        columns = list(result.keys()) if result.keys() else []
        row_count = len(rows)
    except Exception as exc:
        logger.warning("ask_ai SQL execution failed: %s | SQL: %s", exc, sql_query)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query execution failed: {exc}",
        )

    # Step 4: Ask LLM to summarize the result
    answer = await _summarize_result(question, sql_query, columns, rows, settings)

    return AskAiResponse(
        question=question,
        answer=answer,
        sql_used=sql_query,
        row_count=row_count,
    )


def _validate_sql_safety(sql: str) -> None:
    """Validate that SQL is safe: SELECT-only, uses only whitelisted tables."""
    sql_lower = sql.lower().strip()

    # Must start with SELECT
    if not sql_lower.startswith("select"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only SELECT queries are allowed.",
        )

    # Check for blocked keywords
    for kw in BLOCKED_KEYWORDS:
        if kw in sql_lower:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Query contains blocked keyword: '{kw}'",
            )

    # Check that only allowed tables are referenced (basic FROM/JOIN extraction)
    # This is a heuristic check — not foolproof but catches obvious violations
    import re
    table_refs = re.findall(r'(?:from|join)\s+([a-zA-Z_][a-zA-Z_0-9]*)', sql_lower)
    for table in table_refs:
        if table not in ALLOWED_TABLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Table '{table}' is not in the allowed query set: {sorted(ALLOWED_TABLES)}",
            )


async def _generate_sql(question: str, settings) -> str:
    """Use LLM to convert natural language to SQL."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        schema_hint = """
Tables available (SELECT only):
- invoices: id, invoice_number, vendor_id, status, total_amount, due_date, created_at, currency, fraud_score
- invoice_line_items: id, invoice_id, description, quantity, unit_price, gl_account, line_total
- exception_records: id, invoice_id, exception_code, severity, status, created_at, resolved_at
- approval_tasks: id, invoice_id, approver_id, status, created_at, decided_at, decision
- vendors: id, name, email, country, payment_terms
"""
        prompt = f"""You are a SQL expert for an Accounts Payable system. Generate a single PostgreSQL SELECT query for the following question.
{schema_hint}
Rules:
- Only use the tables listed above
- No DML (INSERT/UPDATE/DELETE), no DROP, no ALTER
- Use proper JOINs if needed
- Limit results to 50 rows max with LIMIT 50
- Return ONLY the SQL query, no explanation

Question: {question}

SQL:"""

        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        sql = response.content[0].text.strip() if response.content else ""
        # Strip markdown code blocks if present
        if sql.startswith("```"):
            sql = "\n".join(sql.split("\n")[1:])
        if sql.endswith("```"):
            sql = "\n".join(sql.split("\n")[:-1])
        return sql.strip()

    except Exception as exc:
        logger.error("_generate_sql LLM call failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to generate SQL query from AI.",
        )


async def _summarize_result(
    question: str,
    sql: str,
    columns: list[str],
    rows: list,
    settings,
) -> str:
    """Use LLM to summarize query results in natural language."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        rows_preview = []
        for row in rows[:10]:  # Only first 10 rows for the summary prompt
            rows_preview.append(dict(zip(columns, [str(v) for v in row])))

        prompt = f"""You are an AP analyst. A user asked: "{question}"

The query returned {len(rows)} rows. Here is a preview:
{rows_preview}

Provide a concise, friendly 2-3 sentence summary of what the data shows. Be specific with numbers."""

        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip() if response.content else f"Query returned {len(rows)} rows."

    except Exception as exc:
        logger.warning("_summarize_result failed: %s", exc)
        return f"Query returned {len(rows)} rows with columns: {', '.join(columns)}."
