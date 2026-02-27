# Progress — AI AP Operations Manager

## Project Start: 2026-02-26

Initial planning complete. Full documentation suite created covering:
- PRD (product requirements, user journeys, 15+ scenarios)
- System architecture (modules, data flow, event log design)
- Database ERD (all MVP tables with fields, keys, indexes)
- API design (all MVP endpoints with request/response examples)
- Rules engine design (match pseudocode, tolerance config, exception taxonomy)
- AI modules design (extraction, policy parsing, self-optimization, root cause)
- UI information architecture (all pages, components, table columns)
- Security & compliance design (RBAC, audit, data masking)
- Testing strategy (unit, integration, E2E test cases)
- Milestone plan (week-by-week tickets)

**Next step**: Scaffold backend and frontend, implement DB models, start invoice upload flow.

---

## [2026-02-26] Competitive Research: 8 Products Analyzed

**Result**: success — major plan improvements identified and implemented.

**Products researched**: Tipalti, Medius, Basware, Coupa, SAP Ariba, Stampli, Bill.com, Ramp, Rossum/Hypatos.

**Key gaps found and fixed**:

1. **GL Smart Coding** (Medius SmartFlow, Basware SmartCoding) — critical for non-PO invoices (~40% of manufacturing spend). Added ML-based suggestion module to MVP, full ML classifier to V1.

2. **Dual-Extraction Accuracy** (Coupa ICE) — run two independent LLM extraction passes, compare field-by-field. Catches silent errors before they reach the match engine. Upgraded extraction module.

3. **Vendor Communication Hub** (Stampli "invoice as conversation") — messaging between AP team and vendor embedded in invoice context, all audit-logged. Added `vendor_messages` table, Communications tab on invoice detail, vendor portal reply flow. Moved to V1.

4. **Email-Based Approval** (Tipalti) — signed token URL in notification email, approver clicks Approve/Reject without logging in. Huge adoption driver for occasional approvers. Added to MVP.

5. **Recurring Invoice Detection** (Basware) — pattern detection on historical invoices, fast-track processing for matches. Added `recurring_invoice_patterns` table and auto-detection job to V1.

6. **Fraud Scoring** (Ramp, Bill.com) — behavioral pattern signals before payment: bank account change, ghost vendor, amount spike. Rule-based scoring with HIGH → auto-hold, CRITICAL → dual auth. Added basic scoring to MVP, behavioral upgrade to V1.

7. **Exception Auto-Routing by Type** (Medius) — PRICE_MISMATCH → procurement, GRN_NOT_FOUND → warehouse, TAX_DISCREPANCY → tax team. Reduces assignment lag. Added to V1.

8. **Vendor Compliance Doc Tracking** — W-9, W-8BEN, VAT registration tracking with auto-chase. Added `vendor_compliance_docs` table to V1.

**Strategic positioning clarified**:
- Moat = manufacturing-native 3-way match + conversational exception handling + explainable self-improving rules
- Not competing on: global payments (Tipalti), supplier network (Basware), enterprise suite (Coupa)

**Metrics revised upward** based on best-in-class benchmarks:
- Extraction accuracy target: 92% → 96% → 98% (Coupa ICE: 99%+)
- Touchless rate target: 55% → 75% → 85% (more realistic with GL coding + recurring)
- GL coding accuracy: new metric, 75% → 90% → 95%

**New documents created**: `docs/COMPETITIVE_ANALYSIS.md`

---

<!-- Future entries go here, newest first -->
<!-- Format:
## [YYYY-MM-DD] Task: <what was done>
**Result**: success / partial / failed
**Lessons**:
- What worked: ...
- What failed: ...
- Key insight: ...
-->
