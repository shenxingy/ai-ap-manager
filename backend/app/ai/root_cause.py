"""LLM-powered root cause narrative generation for AP analytics."""
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Rate limit: one report per 60 minutes per user
REPORT_RATE_LIMIT_MINUTES = 60


def generate_narrative(
    process_mining_data: list[dict],
    anomaly_data: list[dict],
    kpi_summary: dict,
    report_id: str,
) -> tuple[str, int, int, str]:
    """Generate a 3-5 paragraph root cause narrative using Claude.

    Returns: (narrative_text, prompt_tokens, completion_tokens, model_used)
    """
    from app.core.config import settings

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    except ImportError:
        logger.error("anthropic package not installed")
        return _fallback_narrative(process_mining_data, anomaly_data, kpi_summary), 0, 0, "fallback"

    prompt = _build_prompt(process_mining_data, anomaly_data, kpi_summary)

    try:
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        narrative = response.content[0].text if response.content else ""
        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens
        model_used = settings.ANTHROPIC_MODEL

        # Log to ai_call_logs
        _log_ai_call(report_id, prompt, narrative, prompt_tokens, completion_tokens, model_used)

        return narrative, prompt_tokens, completion_tokens, model_used

    except Exception as exc:
        logger.error("LLM call failed for report %s: %s", report_id, exc)
        narrative = _fallback_narrative(process_mining_data, anomaly_data, kpi_summary)
        return narrative, 0, 0, "fallback"


def _build_prompt(
    process_mining_data: list[dict],
    anomaly_data: list[dict],
    kpi_summary: dict,
) -> str:
    """Build a structured prompt for the root cause analysis."""
    pm_lines = []
    for step in process_mining_data:
        pm_lines.append(
            f"  - {step.get('step', 'N/A')}: median={step.get('median_hours', 0):.1f}h, "
            f"p90={step.get('p90_hours', 0):.1f}h, count={step.get('invoice_count', 0)}"
        )
    pm_text = "\n".join(pm_lines) if pm_lines else "  (no data)"

    anomaly_lines = []
    for a in anomaly_data[:5]:  # Top 5 anomalies only
        anomaly_lines.append(
            f"  - Vendor '{a.get('vendor_name', 'N/A')}' in period {a.get('period', 'N/A')}: "
            f"exception rate {a.get('exception_rate', 0)*100:.1f}% (z={a.get('z_score', 0):.2f}, "
            f"{a.get('direction', 'N/A')})"
        )
    anomaly_text = "\n".join(anomaly_lines) if anomaly_lines else "  (no anomalies detected)"

    total_inv = kpi_summary.get("total_invoices", 0)
    pending = kpi_summary.get("pending_count", 0)
    exception_rate = kpi_summary.get("exception_rate_pct", 0)
    avg_days = kpi_summary.get("avg_processing_days", 0)

    return f"""You are an expert Accounts Payable operations analyst. Analyze the following AP system metrics and provide a concise root cause analysis report in 3-5 paragraphs.

## KPI Summary
- Total invoices: {total_inv}
- Pending invoices: {pending}
- Exception rate: {exception_rate:.1f}%
- Average processing time: {avg_days:.1f} days

## Process Mining — Step Durations
{pm_text}

## Vendor Anomalies (last 6 months)
{anomaly_text}

## Instructions
Write 3-5 paragraphs covering:
1. Overall AP pipeline health and key bottlenecks
2. Root causes of exceptions and anomalies (be specific about vendors/steps where data shows it)
3. Recommended immediate actions (prioritized by impact)
4. Preventive measures for systemic issues

Be concise, specific, and actionable. Use AP domain language. Do not make up data beyond what is provided."""


def _fallback_narrative(
    process_mining_data: list[dict],
    anomaly_data: list[dict],
    kpi_summary: dict,
) -> str:
    """Generate a basic narrative without LLM if API is unavailable."""
    total_inv = kpi_summary.get("total_invoices", 0)
    exception_rate = kpi_summary.get("exception_rate_pct", 0)

    bottleneck = None
    max_hours = 0
    for step in process_mining_data:
        if step.get("median_hours", 0) > max_hours:
            max_hours = step["median_hours"]
            bottleneck = step.get("step")

    lines = [
        f"The AP pipeline currently has {total_inv} invoices with an overall exception rate of "
        f"{exception_rate:.1f}%. "
    ]
    if bottleneck:
        lines.append(
            f"The primary bottleneck is the '{bottleneck}' step with a median duration of "
            f"{max_hours:.1f} hours, indicating a potential backlog or manual intervention point. "
        )
    if anomaly_data:
        top_anomaly = anomaly_data[0]
        lines.append(
            f"Vendor '{top_anomaly.get('vendor_name', 'N/A')}' shows an anomalous exception rate in "
            f"period {top_anomaly.get('period', 'N/A')} (z-score: {top_anomaly.get('z_score', 0):.2f}), "
            "warranting immediate vendor-level review. "
        )
    lines.append(
        "Recommended actions: (1) Review SLA compliance for overdue invoices, "
        "(2) Investigate high-exception vendors, "
        "(3) Consider tolerance rule adjustments for frequently corrected fields. "
        "\n\n[Note: This report was generated without LLM assistance. Enable ANTHROPIC_API_KEY for detailed analysis.]"
    )
    return " ".join(lines)


def _log_ai_call(
    report_id: str,
    prompt: str,
    response: str,
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
) -> None:
    """Log AI call to ai_call_logs table."""
    try:
        from app.core.config import settings
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        Session = sessionmaker(bind=engine)
        with Session() as session:
            session.execute(
                text("""
                    INSERT INTO ai_call_logs
                        (id, model, prompt, response, prompt_tokens, completion_tokens,
                         latency_ms, purpose, entity_type, entity_id, created_at)
                    VALUES
                        (gen_random_uuid(), :model, :prompt, :response,
                         :prompt_tokens, :completion_tokens, 0,
                         'root_cause_narrative', 'analytics_report', :entity_id::uuid,
                         NOW())
                """),
                {
                    "model": model,
                    "prompt": prompt[:4000],
                    "response": response[:4000],
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "entity_id": report_id,
                },
            )
            session.commit()
    except Exception as exc:
        logger.warning("Failed to log AI call: %s", exc)
