# PRD — AI AP Operations Manager

## 1. User Roles

| Role | Description | Key Permissions |
|------|-------------|-----------------|
| **AP Clerk** | Front-line invoice processor | Upload invoices, view queue, add comments, message vendors |
| **AP Analyst** | Senior AP, handles exceptions | All Clerk perms + resolve exceptions, correct extractions, view audit, GL coding review |
| **Approver** | Business owner or finance manager | Approve/reject via in-app OR email link (no login required) |
| **Admin** | System administrator | Manage users, roles, approval matrix, tolerance rules, GL coding rules, master data, vendor compliance docs |
| **Auditor** | Compliance / internal audit | Read-only access to all data, full audit trail, vendor messages, export |
| **Vendor** | Supplier (external) | Submit invoices via portal, view invoice status, reply to AP messages, upload compliance docs (W-9 etc.) |

---

## 2. User Journey — Invoice Ingestion to Payment Recommendation

```
[Vendor] → Invoice arrives (email / upload / API)
    ↓
[System] Ingestion: save to storage, create invoice record (status: received)
    ↓
[System] OCR Extraction: Tesseract → raw text (status: extracting)
    ↓
[AI] LLM Structuring: raw text → JSON fields + line items (status: extracted)
    ↓
[AP Analyst] Review & correct extraction (if confidence < threshold)
    ↓
[System] Master Data Validation: vendor exists? PO number valid? GL codes valid?
    ↓
[System] Duplicate Detection: same vendor + amount + invoice number + date range?
    ↓
[System] 2-way / 3-way Match Engine
    ├─→ MATCHED → auto-approve if within auto-approve threshold → status: approved
    └─→ EXCEPTION → create exception record → status: exception
    ↓
[AP Analyst] Exception Queue: review, add context, resolve or escalate
    ↓
[System] Approval Routing: lookup approval matrix → create approval task(s)
    ↓
[Approver] Review invoice + supporting docs → Approve / Reject / Send back
    ↓
[System] Payment Recommendation: generate payment record with due date, bank details
    ↓
[System] ERP Push: send voucher to SAP/Oracle for payment processing
    ↓
[System] KPI Update: update touchless rate, cycle time, exception stats
```

---

## 3. Key Scenarios (15+)

### Happy Path Scenarios

**S-01: Standard 3-way match, auto-approved**
- Invoice matches PO and GRN exactly, amount within tolerance
- System auto-approves, no human touch, logs decision
- Expected: touchless, cycle time < 5 min

**S-02: Invoice slightly over PO price within tolerance**
- Price difference 1.2%, tolerance set to 2%
- System auto-approves, records tolerance override in audit
- Expected: touchless

**S-03: Multi-line invoice with partial receipt**
- 10-line PO, GRN covers 7 lines
- System matches 7 lines, flags 3 as `MISSING_GRN`
- Exception created only for unmatched lines; matched lines proceed
- Expected: partial exception, analyst resolves 3 lines

**S-04: Multi-level approval routing**
- Invoice amount $85,000, threshold for VP approval at $50,000
- System creates two tasks: Manager approval → VP approval (sequential)
- Expected: correct routing, each approver notified in sequence

**S-05: Policy document upload and rule extraction**
- Admin uploads vendor contract PDF
- LLM extracts: "Payment terms: Net 30; Tolerance: ±1.5% on materials, ±3% on services"
- Admin reviews extracted rules, publishes as rule version v4
- Expected: new tolerance applied to all future invoices for this vendor

### Exception Scenarios

**S-06: Missing PO number**
- Invoice arrives with no PO reference
- Exception type: `PO_NOT_FOUND`
- Analyst searches by vendor + approximate amount, links to PO manually
- Expected: exception resolved with manual link, audit trail preserved

**S-07: Price mismatch beyond tolerance**
- Invoice price $12.50/unit vs PO price $10.00/unit (25% over, tolerance 2%)
- Exception type: `PRICE_MISMATCH`
- Analyst contacts vendor, uploads credit memo
- Expected: exception resolved via credit memo, original invoice updated

**S-08: Duplicate invoice detection**
- Vendor re-submits invoice (retry after system timeout)
- System detects: same vendor, same invoice number, same amount, within 7 days
- Exception type: `DUPLICATE_INVOICE`
- Analyst confirms it's a duplicate, rejects second submission
- Expected: only one invoice proceeds to payment

**S-09: Quantity over-delivered**
- GRN shows 95 units received, invoice bills for 100 units
- Exception type: `QTY_MISMATCH`
- Analyst approves 95 units, flags 5 units for follow-up PO
- Expected: partial approval workflow triggered

**S-10: Tax/freight discrepancy**
- PO has freight = $0 (vendor absorbs), invoice adds $450 freight
- Exception type: `UNEXPECTED_CHARGE`
- Analyst escalates to procurement to verify agreement
- Expected: exception with escalation comment, SLA tracked

**S-11: Vendor master data mismatch**
- Invoice bank account differs from vendor master record
- Exception type: `VENDOR_DATA_MISMATCH` (potential fraud signal)
- System auto-holds payment, alerts AP Manager
- Expected: mandatory human review before any payment action

**S-12: Invoice in foreign currency**
- Invoice in EUR, PO in USD, FX rate tolerance ±2%
- System converts at daily rate, checks tolerance
- Expected: matches if within FX tolerance, exception if not

**S-13: Approval rejection with feedback**
- Approver rejects invoice: "Wrong cost center coded"
- System routes back to AP Analyst with rejection reason
- Analyst re-codes cost center, re-submits for approval
- Expected: full thread preserved in audit, cycle time updated

**S-14: OCR extraction failure**
- Scanned invoice is low-resolution, OCR confidence < 60%
- System flags for manual data entry (all fields highlighted)
- AP Clerk manually keys fields, marks as "manually entered"
- Expected: low-confidence flag in audit, no auto-processing until human validates

**S-15: SLA breach alert**
- Invoice due date in 2 days, still in exception queue, no owner assigned
- System auto-escalates to AP Manager, sends alert
- Expected: SLA status `BREACHED`, escalation logged

**S-16: Admin changes tolerance mid-period**
- Admin changes tolerance from 2% to 0.5% for vendor ABC
- Rule version v3 published; all new invoices use new tolerance
- Previously matched invoices are NOT retroactively re-evaluated
- Expected: rule version tracked per match result, clear audit

**S-18: Email-based approval (no login required)**
- Invoice routes to VP for approval, $80,000 amount
- VP receives email notification with invoice summary + line items
- Email contains signed "Approve" and "Reject" buttons (token-based, 48h expiry)
- VP clicks Approve from mobile email client
- System validates token, records approval with timestamp and device info
- Invoice proceeds to next level
- Expected: Approver never opens the web app; full audit trail preserved

**S-19: GL smart coding suggestion on non-PO invoice**
- Vendor submits monthly software subscription invoice (no PO)
- No PO to match against; system switches to "coding mode"
- SmartCoding ML looks at: vendor name, line description, invoice history for this vendor
- Suggests: GL 6210 (Software Subscriptions), Cost Center CC-IT-001, approval route: IT Manager
- AP Analyst sees suggestions pre-filled with confidence %, reviews and confirms in one click
- Invoice routed to IT Manager for approval
- Expected: Non-PO invoice processed touchless after analyst one-click confirmation

**S-20: Vendor communication on price dispute (Stampli-style)**
- Price mismatch exception created ($12.50 vs PO $10.00)
- AP Analyst types message directly on the invoice page: "Hi Acme, PO #5500 shows $10.00 unit price. Can you clarify?"
- System sends message to vendor contact email + shows in vendor portal
- Vendor logs into portal, replies: "Rate increase per Q1 amendment, see attached signed amendment"
- Vendor attaches signed amendment PDF in portal
- All messages + attachment stored in `vendor_messages`, linked to invoice
- AP Analyst sees full thread in invoice "Communications" tab
- Analyst resolves exception with note: "Vendor confirmed per attachment"
- Expected: Zero emails outside the system; full vendor communication audit trail

**S-21: Recurring invoice auto-detection and fast-track**
- Monthly utility invoice from City Power Co. ($4,200 ±5%)
- System detects pattern: same vendor, amounts within 10%, first week of each month for 6 months
- Invoice tagged as "Recurring" in UI with badge
- System skips full matching and immediately routes to streamlined 1-click approval
- AP Analyst sees "Recurring Invoice — amount within expected range" card
- One-click confirmation → approved in < 2 minutes
- Expected: Recurring invoices never sit in exception queue

**S-22: Pre-payment fraud flag — vendor bank account change**
- Vendor updates their bank account in the vendor portal
- System detects: bank account changed 3 days before a pending $120,000 invoice payment
- Fraud score elevated: HIGH RISK (behavioral pattern: account change + large invoice)
- System auto-holds payment, creates FRAUD_RISK exception, alerts AP Manager + Admin
- Exception requires dual authorization to clear (two ADMIN users must review)
- AP Manager calls vendor directly to verify change, confirms legitimate
- Dual-authorized to clear hold; audit records both authorizing users
- Expected: No payment leaves without explicit fraud clearance on high-risk changes

**S-23: Dual-extraction discrepancy flagged for review**
- Invoice uploaded, OCR extracts raw text
- Model A extracts: total = $15,420.00, invoice_date = 2026-02-20
- Model B extracts: total = $15,402.00, invoice_date = 2026-02-02
- System detects: total differs by $18, date differs significantly
- Both discrepant fields highlighted in red in the analyst review UI
- AP Analyst manually verifies against the PDF — correct values are $15,420 and Feb 20
- Analyst confirms correct values; system uses confirmed values for matching
- Expected: Silent extraction errors caught before they reach the match engine

**S-17: Auditor exports full audit trail**
- Auditor requests full history for all invoices in Q4 2025
- System exports: invoice details, extraction confidence, match results, exceptions, approvals, actor info, timestamps
- Expected: complete, tamper-evident export

---

## 4. MVP Scope vs V1 vs V2

### MVP (Must have for demo/pilot)
- Invoice upload (manual only)
- Dual-extraction OCR (two model passes, field-level comparison for accuracy)
- 2-way match with tolerance
- Exception queue (view + comment + resolve)
- Single-level approval (in-app + email link approval)
- GL smart coding suggestions on invoice lines (ML-based from history)
- Basic KPI dashboard (touchless rate, exception rate, cycle time)
- JWT auth with 6 roles (including Vendor)
- Audit trail (append-only, includes all vendor messages)
- Seed data for demo

### V1 (Production-ready pilot)
- 3-way match with partial receipts
- Multi-level approval with matrix config + out-of-office delegation
- Email ingestion (monitored mailbox → auto-extract attachments)
- CSV import (PO, GRN, vendors)
- Policy/contract → rule extraction → review → publish
- Duplicate detection (multi-signal)
- Full RBAC enforcement
- Vendor communication hub (AP↔vendor messaging on invoice, audit-logged)
- Vendor portal (invoice status, message reply, compliance doc upload)
- Vendor compliance doc tracking (W-9, W-8BEN status, auto-chase alerts)
- Recurring invoice detection and fast-track processing
- Fraud scoring (behavioral pattern analysis before payment)
- Exception auto-routing by type (pricing → procurement, GRN → warehouse)
- Vendor master data UI

### V2 (Intelligence layer)
- Rule self-optimization from override history
- Root cause analysis + narrative reports
- Conversational AI query interface ("Ask AI: which invoices from Acme are overdue?")
- ERP integration (SAP/Oracle)
- Multi-currency + FX tolerance
- Predictive cash flow forecasting (based on pending approvals + payment terms)
- Industry benchmark comparison on KPI dashboard
- Vendor invoice templating in portal (vendor drafts invoice from template)
- SLA alerting + escalation
- 4-way matching (adds inspection report layer)
- Mobile approver view
