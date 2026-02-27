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
- [ ] Invoice upload → OCR extraction → structured fields stored in DB
- [ ] 2-way match (Invoice vs PO) with configurable tolerance
- [ ] Exception queue for unmatched/flagged invoices
- [ ] Basic approval workflow (single-level)
- [ ] Audit trail for every state transition
- [ ] KPI dashboard with real numbers (touchless rate, exception rate)
- [ ] All running locally via Docker Compose with seed data

### V1 (Weeks 5-8): Production-Ready Core
**Goal**: Ready for a pilot with a real enterprise customer.

Success criteria:
- [ ] 3-way match (Invoice vs PO vs GRN) with partial receipt support
- [ ] Multi-level approval with configurable authorization matrix
- [ ] Integration layer: CSV import for PO/GRN/master data
- [ ] Email ingestion (monitored AP mailbox → extract attachments)
- [ ] Policy/contract document upload → LLM extracts rules → human reviews → published
- [ ] Role-based access control (AP Clerk, Analyst, Approver, Admin, Auditor)
- [ ] Full audit replay: any invoice's decision history reconstructable

### V2 (Weeks 9-12): Intelligence Layer
**Goal**: The system learns and improves from human feedback.

Success criteria:
- [ ] Rule self-optimization: system recommends rule changes based on override history
- [ ] Root cause analysis: when exception rate spikes, system identifies why
- [ ] ERP integration: SAP/Oracle API or certified connector for PO/GRN sync and voucher push
- [ ] Multi-currency support with FX tolerance
- [ ] Vendor portal: suppliers can check invoice status and submit disputes
- [ ] Configurable SLA alerts: invoices approaching due date without approval
- [ ] Mobile-friendly approver view

## North Star Metrics

| Metric | Baseline (Manual) | MVP Target | V1 Target | V2 Target | Best-in-class (market) |
|--------|-------------------|------------|-----------|-----------|------------------------|
| Touchless rate | ~20% | 55% | 75% | 85% | Medius: 100% capture, ~80% touchless |
| Avg cycle time (days) | 14 | 7 | 4 | 3 | Tipalti: 40% faster approvals |
| Extraction accuracy (field) | ~70% manual | 92% | 96% | 98% | Coupa ICE: 99%+ |
| Exception accuracy | N/A | 90% | 95% | 97% | — |
| GL coding accuracy (non-PO) | ~50% | 75% | 90% | 95% | Medius SmartFlow: 95% after 2 invoices |
| Fraud detection (catch rate) | ~20% | 70% | 85% | 92% | Bill.com: 8M+ blocked FY25 |
| Audit completeness | ~60% | 100% | 100% | 100% | — |
| Recurring invoice touchless rate | 0% | 0% | 90% | 95% | Basware: auto-identifies recurring |
| Rules auto-optimized | 0 | 0 | 0 | 30%+ | — |

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
