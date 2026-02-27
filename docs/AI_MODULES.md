# AI Modules Design

**Core Principle**: LLM is a *structuring tool*, not a *decision maker*.
Every LLM output goes through a deterministic validation layer before affecting the system.
All LLM calls are logged to `ai_call_logs` with input, output, tokens, and latency.

---

## Module Overview

| Module | LLM Role | Deterministic Layer |
|--------|----------|-------------------|
| Invoice Extraction | OCR text → structured JSON | Schema validation + confidence gating |
| Policy Parsing | PDF text → rule JSON | Admin review + rule version flow |
| Self-Optimization | Override history → rule suggestions | Human approval before any rule change |
| Root Cause Analysis | Event log stats → narrative | Read-only, no system changes |

---

## 1. Invoice Extraction Module

### Pipeline

```
PDF/Image → Tesseract OCR → raw_text → LLM Structuring → validated_fields → DB
                                              ↓ (if confidence < 0.75)
                                        OCR_LOW_CONFIDENCE exception
                                        → AP Analyst manual review
```

### LLM Prompt Template

```python
EXTRACTION_PROMPT = """
You are an AP document extraction assistant. Extract the following fields from the invoice text below.
Return ONLY valid JSON matching the schema. If a field is not found, use null.
Add a "confidence" field (0.0–1.0) for each extracted value.

Required fields:
- invoice_number: string
- invoice_date: ISO date (YYYY-MM-DD)
- due_date: ISO date (YYYY-MM-DD) or null
- vendor_name: string
- vendor_tax_id: string or null
- po_number: string or null
- currency: 3-letter code (e.g. "USD")
- subtotal: number
- tax_amount: number or null
- freight_amount: number or null
- total_amount: number
- line_items: array of {
    line_number: int,
    description: string,
    quantity: number,
    unit_price: number,
    unit: string or null,
    line_total: number,
    confidence: float
  }

Invoice text:
{raw_text}

JSON output:
"""
```

### Validation Layer

```python
def validate_extraction(raw_json: dict) -> ExtractionResult:
    errors = []

    # Required fields present?
    for field in ["invoice_number", "total_amount", "vendor_name"]:
        if raw_json.get(field) is None:
            errors.append(f"Missing required field: {field}")

    # Math check: sum(line_totals) + tax + freight ≈ total
    line_sum = sum(li["line_total"] for li in raw_json.get("line_items", []))
    tax = raw_json.get("tax_amount") or 0
    freight = raw_json.get("freight_amount") or 0
    expected_total = line_sum + tax + freight
    actual_total = raw_json.get("total_amount", 0)
    if abs(expected_total - actual_total) > 1.0:
        errors.append(f"Total mismatch: sum={expected_total}, stated={actual_total}")

    # Overall confidence = min of field confidences
    field_confidences = [raw_json.get(f"confidence_{field}", 1.0) for field in ["invoice_number", "total_amount"]]
    li_confidences = [li.get("confidence", 1.0) for li in raw_json.get("line_items", [])]
    overall_confidence = min(field_confidences + li_confidences, default=0.5)

    return ExtractionResult(
        data=raw_json,
        overall_confidence=overall_confidence,
        validation_errors=errors,
        needs_manual_review=overall_confidence < 0.75 or len(errors) > 0
    )
```

---

## 2. Policy/Contract Parsing Module

### Pipeline

```
PDF upload → text extraction (pdfplumber/PyMuPDF) → LLM extraction
→ structured rule candidates → stored as policy_rules (reviewed=false)
→ Admin reviews in UI → selects rules to include → creates rule_version (draft)
→ rule_version goes through draft → review → published flow
```

### LLM Prompt Template

```python
POLICY_PARSE_PROMPT = """
You are an AP policy analyst. Read the following document and extract all rules that relate to:
1. Price tolerance thresholds (allowed % or absolute variance)
2. Quantity tolerance thresholds
3. Approval thresholds (who approves what amount)
4. Payment terms (Net X days)
5. Prohibited charges (what vendor cannot bill for)
6. Exceptions to standard rules (specific vendors or categories)

For each rule found, output a JSON object with:
- rule_type: "tolerance" | "approval_threshold" | "payment_term" | "prohibition" | "other"
- subject: what the rule applies to (vendor name, category, or "global")
- rule_json: the structured rule (see examples below)
- source_text: the exact text from the document that supports this rule (quote it)
- confidence: 0.0–1.0

Examples of rule_json formats:
- Tolerance: {"price_tolerance_pct": 2.0, "qty_tolerance_pct": 3.0}
- Approval threshold: {"amount": 50000, "approver_role": "FINANCE_VP"}
- Payment term: {"net_days": 30, "early_pay_discount_pct": 2.0, "early_pay_days": 10}
- Prohibition: {"prohibited_charge": "freight", "reason": "vendor absorbs shipping costs"}

Document text:
{document_text}

Output a JSON array of rules:
"""
```

### Evidence Preservation

Every extracted rule stores the `source_text` quote from the original document.
When a rule is published, the `source_text` is immutable and linked to the `policy_documents` record.
Auditors can trace: "This 1.5% tolerance was set because of clause X in contract Y."

---

## 3. Self-Optimization Module (V2)

### Data Collection

Every human override is captured in `audit_logs` with action `"human_override"`:
- AP Analyst changes exception outcome contrary to initial system recommendation
- Approver reverses a system auto-approve decision
- Analyst manually links a PO when system said `PO_NOT_FOUND`

### Weekly Analysis Job (Celery Beat)

```python
def generate_rule_suggestions(db: Session, lookback_days: int = 30) -> list[RuleSuggestion]:
    overrides = db.query(AuditLog).filter(
        AuditLog.action == "human_override",
        AuditLog.created_at >= now() - timedelta(days=lookback_days)
    ).all()

    # Aggregate: which rules led to exceptions that humans later resolved?
    patterns = analyze_override_patterns(overrides)

    suggestions = []
    for pattern in patterns:
        if pattern.frequency >= SUGGESTION_MIN_FREQUENCY:
            suggestion = RuleSuggestion(
                current_rule=pattern.current_rule,
                suggested_change=pattern.suggested_change,
                evidence_count=pattern.frequency,
                potential_touchless_improvement=estimate_touchless_gain(pattern),
                raw_events=pattern.event_ids  # links to audit_logs for traceability
            )
            suggestions.append(suggestion)
    return suggestions
```

### LLM Narration of Suggestion

```python
SUGGESTION_NARRATE_PROMPT = """
Based on the following pattern of human overrides in our AP system, generate a clear,
concise explanation of what rule change is being suggested and why.

Pattern data:
{pattern_json}

Output:
- summary: 1-2 sentence human-readable explanation
- suggested_rule_change: specific parameter changes in JSON
- risk_assessment: potential downside of this change
- estimated_benefit: expected reduction in manual exceptions
"""
```

All suggestions are stored as `draft` rule versions. Admin must explicitly review and publish.
**LLM cannot self-publish rules** — the `published_by` field requires a human user ID.

---

## 4. Root Cause Analysis Module (V2)

### Trigger

Triggered when:
- Exception rate for a vendor > 2x their 30-day average
- Overall exception rate > 30% for 3+ consecutive days
- Admin manually requests analysis for a time period

### Analysis Pipeline

```python
def run_root_cause_analysis(db: Session, period: DateRange, scope: str = "global") -> RCAReport:
    # Step 1: Collect event statistics (deterministic)
    stats = {
        "exception_count": count_exceptions(db, period),
        "exception_by_type": count_by_type(db, period),
        "exception_by_vendor": count_by_vendor(db, period),
        "avg_cycle_time": avg_cycle_time(db, period),
        "extraction_confidence_avg": avg_confidence(db, period),
        "newly_failed_vendors": vendors_with_spike(db, period),
    }

    # Step 2: Process mining — identify bottleneck transitions
    bottlenecks = identify_bottleneck_steps(db, period)

    # Step 3: LLM narrates findings (read-only, no system changes)
    narrative = llm_narrate_rca(stats, bottlenecks)

    # Step 4: Store report
    report = RCAReport(
        period=period,
        stats_json=stats,
        bottlenecks_json=bottlenecks,
        narrative=narrative,
        generated_at=now()
    )
    return report
```

### LLM Narration (Read-Only)

```python
RCA_NARRATE_PROMPT = """
You are an AP operations analyst. Based on the statistics below, write a clear root cause analysis.

Statistics:
{stats_json}

Bottleneck analysis:
{bottlenecks_json}

Requirements:
- Identify the top 1-3 most likely root causes
- Cite specific statistics as evidence
- Suggest concrete actions (do NOT change any rules yourself)
- Flag any data anomalies that need investigation
- Keep it under 400 words

Format: { "root_causes": [...], "evidence": [...], "recommended_actions": [...], "anomalies": [...] }
"""
```

---

## AI Safety Guardrails Summary

| Guardrail | Implementation |
|-----------|---------------|
| LLM never approves invoices | Match/approval decisions are pure Python rule engine |
| LLM output always validated | Schema validation + math checks before DB write |
| All LLM calls logged | `ai_call_logs` table with input hash, output, latency |
| Rule changes need human | `published_by` requires user auth, no system self-publish |
| Evidence preserved | Source text stored with every extracted rule |
| Confidence gating | Low-confidence extraction → mandatory human review |
| Suggestions are drafts only | `rule_versions.status = draft` until admin publishes |
| RCA is read-only | Narration stored, no system mutation |
