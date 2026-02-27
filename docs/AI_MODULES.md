# AI Modules Design

**Core Principle**: LLM is a *structuring tool*, not a *decision maker*.
Every LLM output goes through a deterministic validation layer before affecting the system.
All LLM calls are logged to `ai_call_logs` with input, output, tokens, and latency.

---

## Module Overview

| Module | LLM Role | Deterministic Layer |
|--------|----------|-------------------|
| Invoice Extraction (Dual-Pass) | OCR text → structured JSON ×2, compare | Schema validation + field-level comparison + confidence gating |
| GL Smart Coding | Line description + vendor history → GL/cost center suggestion | ML classifier, human confirms, never auto-posts |
| Policy Parsing | PDF text → rule JSON | Admin review + rule version flow |
| Fraud Scoring | Invoice metadata → risk signals narrative | Rule-based behavioral checks, human review required on HIGH |
| Self-Optimization | Override history → rule suggestions | Human approval before any rule change |
| Root Cause Analysis | Event log stats → narrative | Read-only, no system changes |
| Conversational Query (V2) | Natural language question → SQL/filter → result | Result shown, user confirms before any action |

---

## 1. Invoice Extraction Module — Dual-Pass Architecture

Inspired by Coupa's ICE (Invoice Capture Extraction): run two independent extraction passes and compare field-by-field. Discrepancies surface as explicit flags, not silent errors.

### Pipeline

```
PDF/Image → Tesseract OCR → raw_text ──┬──→ LLM Pass A (prompt strategy A) ──┐
                                        └──→ LLM Pass B (prompt strategy B) ──┤
                                                                               ↓
                                              Field-Level Comparator: compare A vs B
                                              ↓ (matched fields)              ↓ (mismatched fields)
                                        high confidence                  flag for human review
                                              ↓
                                        validated_fields → DB
                                              ↓ (if overall confidence < 0.75 OR ≥2 field mismatches)
                                        OCR_LOW_CONFIDENCE exception → AP Analyst
```

### Two Prompt Strategies

**Pass A — Structured Extraction**: Explicit field-by-field extraction with JSON schema enforcement.

**Pass B — Document Understanding**: Ask the model to "read this invoice as a human would" and output key facts in free-form, then parse the structured data from that. Different failure modes than Pass A.

### Field Comparison Logic

```python
def compare_extraction_passes(pass_a: dict, pass_b: dict) -> ComparisonResult:
    mismatches = []
    for field in CRITICAL_FIELDS:  # invoice_number, total_amount, invoice_date, vendor_name
        val_a = pass_a.get(field)
        val_b = pass_b.get(field)
        if val_a is None and val_b is None:
            continue
        if field in NUMERIC_FIELDS:
            # Allow $0.01 rounding tolerance
            if abs((val_a or 0) - (val_b or 0)) > 0.01:
                mismatches.append(FieldMismatch(field, val_a, val_b, severity="high"))
        elif field in DATE_FIELDS:
            if val_a != val_b:
                mismatches.append(FieldMismatch(field, val_a, val_b, severity="high"))
        else:
            # String: flag if edit distance > 10% of string length
            if edit_distance_ratio(str(val_a), str(val_b)) > 0.10:
                mismatches.append(FieldMismatch(field, val_a, val_b, severity="medium"))

    # Use Pass A value as primary; flag mismatches for human review
    merged = {**pass_a, "_mismatches": mismatches}
    return ComparisonResult(merged=merged, mismatches=mismatches,
                            needs_review=len([m for m in mismatches if m.severity == "high"]) > 0)
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

## 2. GL Smart Coding Module

Inspired by Medius SmartFlow and Basware SmartCoding. Critical for non-PO invoices (services, utilities, subscriptions) which cannot be matched against a PO.

### When It Activates

- Invoice has no PO number, OR
- Invoice is matched to a PO but lines have no GL account populated

### Data Sources for Prediction

```python
CODING_SIGNALS = [
    "vendor_id",              # Same vendor always coded to same GL?
    "line_description",       # "Office Rent" → GL 6100, "AWS Services" → GL 6210
    "invoice_line_amount",    # Large amounts → different GL than small amounts?
    "invoice_month",          # Seasonal patterns (utilities spike in winter)
    "vendor_category",        # Vendor tagged as "Software" → Software GL accounts
    "cost_center_history",    # This vendor always goes to which cost center?
]
```

### ML Approach

For MVP: **Frequency-based lookup** (what GL was used last 5 times for this vendor + description?)

For V1: **Scikit-learn text classifier** trained on historical invoice lines:
- Features: vendor_name (encoded), line_description (TF-IDF), amount_bucket
- Labels: gl_account, cost_center
- Retrain weekly on approved invoices (human-confirmed labels)

```python
def suggest_gl_coding(invoice_line: InvoiceLineItem, db: Session) -> GLCodingSuggestion:
    # Step 1: Check exact vendor+description match in history
    history = db.query(InvoiceLineItem).filter(
        InvoiceLineItem.vendor_id == invoice_line.invoice.vendor_id,
        InvoiceLineItem.gl_account.isnot(None),
    ).order_by(InvoiceLineItem.created_at.desc()).limit(50).all()

    # Step 2: Frequency vote
    gl_votes = Counter(h.gl_account for h in history)
    cc_votes = Counter(h.cost_center for h in history)

    best_gl = gl_votes.most_common(1)[0] if gl_votes else None
    best_cc = cc_votes.most_common(1)[0] if cc_votes else None

    # Step 3: Confidence = frequency / total
    gl_confidence = best_gl[1] / len(history) if best_gl else 0.0
    cc_confidence = best_cc[1] / len(history) if best_cc else 0.0

    return GLCodingSuggestion(
        gl_account=best_gl[0] if best_gl else None,
        cost_center=best_cc[0] if best_cc else None,
        gl_confidence=gl_confidence,
        cc_confidence=cc_confidence,
        based_on_n_invoices=len(history),
        requires_confirmation=True  # ALWAYS — never auto-post
    )
```

### UI Behavior

- In invoice line item editor: GL and Cost Center fields show pre-filled suggestion with grey text
- Confidence badge next to each suggested field (e.g., "92% confidence, based on 12 invoices")
- AP Analyst clicks "Confirm All" or edits individual fields
- Every confirmation is logged to `audit_logs` as "gl_coding_confirmed" (human actor)
- Every override is logged as "gl_coding_overridden" (feeds ML retraining)

### Safety Guardrail

GL coding suggestions are **proposals, never auto-applied**. The `invoice_line_items.gl_account` field is only written when a human explicitly confirms or edits.

---

## 3. Fraud Scoring Module

Proactive behavioral fraud detection, inspired by Ramp and Bill.com (8M+ fraud attempts blocked in FY25).

### Fraud Signal Checklist (runs automatically on every invoice)

```python
FRAUD_SIGNALS = [
    {
        "name": "bank_account_recently_changed",
        "check": lambda inv: vendor_bank_changed_recently(inv.vendor_id, days=30),
        "weight": 40,  # HIGH weight
        "description": "Vendor bank account changed in last 30 days"
    },
    {
        "name": "first_invoice_new_vendor",
        "check": lambda inv: is_first_invoice(inv.vendor_id),
        "weight": 20,
        "description": "First invoice from this vendor — enhanced review"
    },
    {
        "name": "amount_spike_vs_history",
        "check": lambda inv: invoice_amount_vs_avg(inv) > 3.0,  # 3x average
        "weight": 30,
        "description": "Invoice amount is >3x vendor's historical average"
    },
    {
        "name": "round_number_amount",
        "check": lambda inv: inv.total_amount % 1000 == 0 and inv.total_amount > 10000,
        "weight": 10,
        "description": "Suspiciously round large amount"
    },
    {
        "name": "weekend_submission",
        "check": lambda inv: inv.created_at.weekday() >= 5,
        "weight": 10,
        "description": "Invoice submitted on weekend"
    },
    {
        "name": "duplicate_bank_account",
        "check": lambda inv: another_vendor_has_same_bank(inv.vendor_id),
        "weight": 50,  # CRITICAL
        "description": "Bank account matches another vendor — possible ghost vendor"
    },
]

def calculate_fraud_score(invoice: Invoice, db: Session) -> FraudScore:
    triggered = []
    total_weight = 0
    for signal in FRAUD_SIGNALS:
        if signal["check"](invoice):
            triggered.append(signal)
            total_weight += signal["weight"]

    level = "LOW" if total_weight < 20 else "MEDIUM" if total_weight < 40 else "HIGH"
    return FraudScore(score=total_weight, level=level, triggered_signals=triggered)
```

### Risk Levels and Actions

| Score | Level | Action |
|-------|-------|--------|
| 0-19 | LOW | Normal processing, fraud score stored |
| 20-39 | MEDIUM | Flag in UI, AP Analyst reviews before approval routing |
| 40-59 | HIGH | Auto-hold payment, create FRAUD_RISK exception, alert AP Manager |
| 60+ | CRITICAL | Auto-hold, dual-authorization required (2 ADMIN), alert CISO |

---

## 4. Policy/Contract Parsing Module

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
