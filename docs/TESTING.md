# Testing Strategy & Acceptance Criteria

---

## 1. Unit Test Points (Backend)

### Rule Engine
- `test_2way_match_exact` — exact match returns MATCHED
- `test_2way_match_within_price_tolerance` — 1.5% variance, 2% tolerance → MATCHED
- `test_2way_match_exceeds_price_tolerance` — 3% variance, 2% tolerance → PRICE_MISMATCH
- `test_2way_match_qty_over_tolerance` — qty 105 vs 100, 2% tolerance → QTY_MISMATCH
- `test_3way_match_missing_grn` — no GRN for PO line → GRN_NOT_FOUND
- `test_3way_match_partial_receipt` — 3 GRNs covering full PO → MATCHED
- `test_tolerance_resolution_priority` — vendor+category > vendor > category > default
- `test_duplicate_detection_same_invoice_number` — same vendor + invoice# → duplicate
- `test_duplicate_detection_same_amount_date` — same amount + date → duplicate
- `test_duplicate_detection_no_false_positive` — similar but different vendor → not duplicate
- `test_approval_routing_single_level` — $5000 invoice → correct approver
- `test_approval_routing_multi_level` — $100k invoice → 2 approval tasks created
- `test_approval_routing_capex` — CAPEX cost center → additional CFO level

### Extraction Validation
- `test_extraction_valid_json` — well-formed extraction passes validation
- `test_extraction_math_check` — line sum + tax ≠ total → validation error
- `test_extraction_missing_required_field` — no invoice_number → validation error
- `test_extraction_low_confidence` — min confidence 0.60 → needs_manual_review=True

### Rule Version Management
- `test_publish_rule_version_archives_previous` — publishing v5 archives v4
- `test_cannot_publish_draft_version` — draft must go through in_review first
- `test_only_one_published_version_at_a_time`

---

## 2. Integration Test Points

- **Invoice upload → extraction**: Upload PDF → Celery task fires → invoice fields populated
- **Full 2-way match flow**: Seed PO + invoice → trigger match → correct match_result created
- **Exception creation**: PRICE_MISMATCH invoice → exception record created with correct type/severity
- **Approval task routing**: Invoice approved by analyst → correct approval tasks created per matrix
- **Multi-level approval sequential**: Level 1 approve → Level 2 task activates
- **Audit log completeness**: Every status transition → audit_log entry with correct actor/action
- **CSV import PO**: Upload CSV → POs created + line items
- **Duplicate detection integration**: Submit same invoice twice → second flagged as duplicate
- **Rule version applied in match**: Publish new tolerance → next match uses new version ID

---

## 3. End-to-End Test Cases (10 minimum)

### E2E-01: Happy path — touchless invoice
1. Upload invoice PDF (matches PO exactly)
2. System extracts fields (mock LLM response)
3. System runs 2-way match → MATCHED
4. Invoice auto-approved (under threshold)
5. Invoice status = `approved`
6. Audit trail contains all 5 state transitions

**Pass**: Invoice approved without any human interaction; audit trail complete.

---

### E2E-02: Price mismatch → exception → resolve → approve
1. Upload invoice with price 10% over PO (tolerance 2%)
2. Match → PRICE_MISMATCH exception created
3. AP Analyst opens exception, reads match evidence
4. Analyst adds comment: "Price approved by procurement"
5. Analyst resolves exception
6. Approval task created for Manager
7. Manager approves
8. Invoice status = `approved`

**Pass**: Full thread in audit; exception marked resolved; approval task linked to correct approver.

---

### E2E-03: Missing PO → manual link → proceed
1. Upload invoice with no PO number
2. Exception: PO_NOT_FOUND
3. Analyst searches vendors, finds PO, manually links via API
4. System re-triggers match
5. Match succeeds
6. Approval flow proceeds normally

**Pass**: Manual PO link logged in audit as human override.

---

### E2E-04: Duplicate invoice rejected
1. Upload invoice A (processed normally)
2. Upload exact same invoice A again (same vendor, invoice#, amount)
3. System detects duplicate
4. Exception: DUPLICATE_INVOICE, severity=critical
5. Invoice B status = `exception`
6. Analyst reviews, rejects duplicate
7. Invoice B status = `rejected`

**Pass**: Only invoice A reaches approval; invoice B rejected; audit trail shows duplicate detection.

---

### E2E-05: 3-way match with partial GRN
1. Create PO with 5 line items
2. Create GRN covering only 3 of 5 PO lines
3. Upload invoice covering all 5 lines
4. 3-way match: 3 lines MATCHED, 2 lines GRN_NOT_FOUND
5. 2 exceptions created
6. Analyst resolves GRN exceptions (GRN received after invoice date, confirmed)
7. Approval proceeds for full invoice

**Pass**: Correct per-line match results; partial match handled; exceptions link to correct lines.

---

### E2E-06: Multi-level approval chain
1. Upload high-value invoice ($120,000)
2. Approval matrix: >$50k → VP approval; >$100k → also CFO
3. Two approval tasks created (VP + CFO, sequential)
4. VP approves (Level 1 done)
5. CFO approval task now active
6. CFO approves
7. Invoice approved

**Pass**: Level 2 task only activates after Level 1; both logged with decisions.

---

### E2E-07: Policy upload → rule extraction → publish → applied in match
1. Admin uploads vendor contract PDF (contains "Price tolerance for materials: 1.5%")
2. LLM extracts rule (mock: returns tolerance=1.5%)
3. Admin reviews extracted rules, confirms
4. Admin creates rule version draft, adds extracted rule
5. Admin submits for review, then publishes (v5)
6. Upload invoice with 1.4% price variance for "materials" category
7. Match runs with v5 rules → MATCHED (1.4% < 1.5%)
8. match_result.rule_version_id = v5 UUID

**Pass**: Rule change reflected in match outcome; rule version traceable.

---

### E2E-08: Approver rejects → back to analyst → re-code → re-approve
1. Invoice goes to approval
2. Approver rejects: "Wrong cost center — should be CC-5100"
3. Invoice status = `rejected`
4. AP Analyst is notified
5. Analyst corrects cost center field
6. Analyst re-submits for approval (creates new approval task)
7. Approver (same or different) approves

**Pass**: Full rejection thread in audit; re-submission creates new approval task; original rejection preserved.

---

### E2E-09: Low OCR confidence → forced manual review
1. Upload low-quality scanned invoice (mock: OCR confidence 0.55)
2. Extraction completes but OCR_LOW_CONFIDENCE exception created
3. Invoice status stuck at `extracted` (not auto-matched)
4. AP Analyst opens workbench, sees flagged invoice
5. Analyst manually corrects all highlighted fields
6. Analyst marks fields as "manually verified"
7. System re-runs match
8. Normal flow proceeds

**Pass**: No auto-match with low confidence; manual review required; manual correction logged.

---

### E2E-10: KPI dashboard reflects real data
1. Process 10 invoices (6 touchless, 4 with exceptions)
2. Open KPI dashboard for today
3. Verify: touchless_rate = 0.60
4. Verify: exception_rate = 0.40
5. Verify: total invoice count = 10
6. Verify trend chart shows today's data point

**Pass**: KPI numbers match processed data; no stale cache.

---

## 4. Success Metrics & Acceptance Criteria

| Metric | MVP Acceptance | V1 Acceptance |
|--------|---------------|---------------|
| Touchless rate (test data) | ≥ 50% | ≥ 70% |
| Exception classification accuracy | ≥ 90% | ≥ 95% |
| Extraction accuracy (field level) | ≥ 85% | ≥ 92% |
| Audit completeness | 100% | 100% |
| API response time (P95) | < 500ms | < 300ms |
| Extraction latency (P95) | < 30s | < 15s |
| Uptime | N/A (local) | 99.5% |
| Rule version traceability | 100% | 100% |
