# PRD — AI AP Operations Manager

## 1. User Roles

| Role | Description | Key Permissions |
|------|-------------|-----------------|
| **AP Clerk** | Front-line invoice processor | Upload invoices, view queue, add comments |
| **AP Analyst** | Senior AP, handles exceptions | All Clerk perms + resolve exceptions, correct extractions, view audit |
| **Approver** | Business owner or finance manager | Approve/reject assigned approval tasks |
| **Admin** | System administrator | Manage users, roles, approval matrix, tolerance rules, master data |
| **Auditor** | Compliance / internal audit | Read-only access to all data, full audit trail, export |

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

**S-17: Auditor exports full audit trail**
- Auditor requests full history for all invoices in Q4 2025
- System exports: invoice details, extraction confidence, match results, exceptions, approvals, actor info, timestamps
- Expected: complete, tamper-evident export

---

## 4. MVP Scope vs V1 vs V2

### MVP (Must have for demo/pilot)
- Invoice upload (manual only)
- OCR + LLM extraction
- 2-way match with tolerance
- Exception queue (view + comment + resolve)
- Single-level approval
- Basic KPI dashboard (touchless rate, exception rate, cycle time)
- JWT auth with 5 roles
- Audit trail (append-only)
- Seed data for demo

### V1 (Production-ready pilot)
- 3-way match with partial receipts
- Multi-level approval with matrix config
- Email ingestion (monitored mailbox)
- CSV import (PO, GRN, vendors)
- Policy/contract → rule extraction → review → publish
- Duplicate detection
- Full RBAC enforcement
- Vendor master data UI

### V2 (Intelligence layer)
- Rule self-optimization from override history
- Root cause analysis + narrative reports
- ERP integration (SAP/Oracle)
- Multi-currency
- Vendor portal
- SLA alerting + escalation
- Mobile approver view
