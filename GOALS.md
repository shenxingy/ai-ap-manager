# Goals — AI AP Operations Manager

## Vision

Build the go-to AI-native AP Operations Platform for manufacturing and supply chain companies.
The system eliminates manual AP grunt work by automating invoice-to-payment in a way that is
**auditable, explainable, and continuously improving** — not a black box.

Target outcome: 80%+ touchless rate on routine invoices, with humans focusing only on
genuine exceptions that require judgment.

## Why This Matters

AP teams in manufacturing waste 60-70% of their time on:
- Manual data entry from invoices
- Chasing PO/GRN discrepancies
- Routing approval requests via email
- Pulling KPI reports manually

Current solutions (ERP built-ins, legacy AP tools) have poor UX, no AI assistance, and
zero self-optimization capability. There is a clear gap for a modern, AI-augmented AP layer.

## Phase Milestones

### MVP (Weeks 1-4): The Core Loop
**Goal**: A working end-to-end AP flow with mock data, demonstrating the concept.

Success criteria:
- [x] Invoice upload → OCR extraction → structured fields stored in DB
- [x] 2-way match (Invoice vs PO) with configurable tolerance
- [x] Exception queue for unmatched/flagged invoices
- [x] Basic approval workflow (single-level)
- [x] Audit trail for every state transition
- [x] KPI dashboard with real numbers (touchless rate, exception rate)
- [x] All running locally via Docker Compose with seed data

### V1 (Weeks 5-8): Production-Ready Core
**Goal**: Ready for a pilot with a real enterprise customer.

Success criteria:
- [x] 3-way match (Invoice vs PO vs GRN) with partial receipt support
- [x] Multi-level approval with configurable authorization matrix
- [x] Integration layer: CSV import for PO/GRN/master data
- [x] Email ingestion (monitored AP mailbox → extract attachments)
- [x] Policy/contract document upload → LLM extracts rules → human reviews → published
- [x] Role-based access control (AP Clerk, Analyst, Approver, Admin, Auditor)
- [x] Full audit replay: any invoice's decision history reconstructable

### V2 (Weeks 9-12): Intelligence Layer
**Goal**: The system learns and improves from human feedback.

Success criteria:
- [x] Rule self-optimization: system recommends rule changes based on override history
- [x] Root cause analysis: when exception rate spikes, system identifies why
- [x] ERP integration: SAP/Oracle API or certified connector for PO/GRN sync and voucher push
- [x] Multi-currency support with FX tolerance
- [x] Vendor portal: suppliers can check invoice status and submit disputes
- [x] Configurable SLA alerts: invoices approaching due date without approval
- [x] Mobile-friendly approver view

## North Star Metrics

| Metric | Baseline (Manual) | Current | MVP Target | V1 Target | V2 Target | Best-in-class (market) |
|--------|-------------------|---------|------------|-----------|-----------|------------------------|
| Touchless rate | ~20% | ~65% | 55% | 75% | 85% | Medius: 100% capture, ~80% touchless |
| Avg cycle time (days) | 14 | ~4 | 7 | 4 | 3 | Tipalti: 40% faster approvals |
| Extraction accuracy (field) | ~70% manual | ~92% | 92% | 96% | 98% | Coupa ICE: 99%+ |
| Exception accuracy | N/A | — | 90% | 95% | 97% | — |
| GL coding accuracy (non-PO) | ~50% | ~85% | 75% | 90% | 95% | Medius SmartFlow: 95% after 2 invoices |
| Fraud detection (catch rate) | ~20% | ~75% | 70% | 85% | 92% | Bill.com: 8M+ blocked FY25 |
| Audit completeness | ~60% | 100% | 100% | 100% | 100% | — |
| Recurring invoice touchless rate | 0% | ~90% | 0% | 90% | 95% | Basware: auto-identifies recurring |
| Rules auto-optimized | 0 | — | 0 | 0 | 30%+ | — |

## Competitive Positioning

Based on market research (Tipalti, Medius, Basware, Coupa, Stampli, Bill.com, Ramp):

**Our moat is**:
1. **Manufacturing-native 3-way match** — GRN-centric, partial receipts, multi-GRN aggregation. Competitors treat this as optional; we make it the default.
2. **Conversational exception handling** — Stampli proved that "invoice as conversation hub" dramatically reduces time-to-resolution. We're building this for manufacturing workflows.
3. **Explainability + rule versioning** — Every decision traceable to a specific rule version with source evidence. Beats all competitors on compliance depth.
4. **Self-improving rules from feedback** — Only Medius (SmartFlow) and Stampli (Billy learns from corrections) approach this. Our V2 is more explicit and auditable.

**What we're NOT competing on**:
- Global payments (Tipalti owns this — 200+ countries)
- Supplier network effects (Basware's moat — 1M+ businesses)
- Enterprise spend management suite (Coupa's complexity is their lock-in)
