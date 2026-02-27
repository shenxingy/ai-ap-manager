# API Design — REST API v1

**Base URL**: `/api/v1`
**Auth**: Bearer JWT in `Authorization` header
**Content-Type**: `application/json`

## Error Response Format
```json
{
  "error": {
    "code": "INVOICE_NOT_FOUND",
    "message": "Invoice with id 'abc-123' does not exist.",
    "details": {}
  }
}
```

## Error Codes
| HTTP | Code | Meaning |
|------|------|---------|
| 400 | `VALIDATION_ERROR` | Request body fails validation |
| 401 | `UNAUTHORIZED` | Missing or invalid token |
| 403 | `FORBIDDEN` | Valid token, insufficient role |
| 404 | `NOT_FOUND` | Resource not found |
| 409 | `CONFLICT` | Duplicate resource |
| 422 | `UNPROCESSABLE` | Business rule violation |
| 500 | `INTERNAL_ERROR` | Server error |

---

## Auth Endpoints

### POST `/auth/login`
```json
// Request
{ "email": "analyst@company.com", "password": "secret" }

// Response 200
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_in": 3600,
  "user": { "id": "uuid", "email": "analyst@company.com", "role": "AP_ANALYST" }
}
```

### POST `/auth/refresh`
```json
// Request
{ "refresh_token": "eyJ..." }
// Response 200 — same as login
```

---

## Invoice Endpoints

### POST `/invoices/upload`
Upload a new invoice document.
- **Role**: AP_CLERK, AP_ANALYST, ADMIN
- **Content-Type**: `multipart/form-data`
- **Fields**: `file` (PDF/PNG/JPG), `vendor_id` (optional), `po_number` (optional)

```json
// Response 201
{
  "id": "inv-uuid",
  "invoice_number": null,
  "status": "received",
  "storage_path": "invoices/2026/02/inv-uuid.pdf",
  "created_at": "2026-02-26T10:00:00Z",
  "job_id": "celery-task-uuid"  // async extraction job
}
```

### GET `/invoices`
List invoices with filters.
- **Role**: All
- **Query params**: `status`, `vendor_id`, `date_from`, `date_to`, `po_number`, `page`, `page_size`

```json
// Response 200
{
  "items": [
    {
      "id": "inv-uuid",
      "invoice_number": "INV-2026-001",
      "vendor": { "id": "v-uuid", "name": "Acme Corp" },
      "status": "exception",
      "total_amount": 15420.00,
      "currency": "USD",
      "invoice_date": "2026-02-20",
      "due_date": "2026-03-22",
      "created_at": "2026-02-26T10:00:00Z"
    }
  ],
  "total": 142,
  "page": 1,
  "page_size": 20
}
```

### GET `/invoices/{id}`
Full invoice detail with line items, match results, exceptions, approvals.
```json
// Response 200
{
  "id": "inv-uuid",
  "invoice_number": "INV-2026-001",
  "vendor": { "id": "v-uuid", "name": "Acme Corp" },
  "po": { "id": "po-uuid", "po_number": "PO-2025-5500" },
  "status": "exception",
  "document_type": "invoice",
  "currency": "USD",
  "subtotal": 14800.00,
  "tax_amount": 620.00,
  "freight_amount": 0,
  "total_amount": 15420.00,
  "invoice_date": "2026-02-20",
  "due_date": "2026-03-22",
  "extraction_confidence": 0.92,
  "manually_corrected": false,
  "line_items": [
    {
      "id": "li-uuid",
      "line_number": 1,
      "description": "Steel Plate 10mm",
      "quantity": 200,
      "unit_price": 74.00,
      "unit": "EA",
      "line_total": 14800.00,
      "extraction_confidence": 0.94
    }
  ],
  "match_results": [...],
  "exceptions": [...],
  "approval_tasks": [...],
  "created_at": "2026-02-26T10:00:00Z",
  "updated_at": "2026-02-26T10:05:00Z"
}
```

### GET `/invoices/{id}/audit`
Full audit trail for an invoice.
```json
// Response 200
{
  "invoice_id": "inv-uuid",
  "events": [
    {
      "id": 1001,
      "action": "status_changed",
      "actor": { "id": "user-uuid", "name": "System", "type": "system" },
      "old_value": { "status": "received" },
      "new_value": { "status": "extracting" },
      "metadata": { "job_id": "celery-task-uuid" },
      "created_at": "2026-02-26T10:00:05Z"
    },
    {
      "id": 1002,
      "action": "extraction_complete",
      "actor": { "id": null, "name": "AI Extractor", "type": "ai" },
      "old_value": null,
      "new_value": { "total_amount": 15420.00, "invoice_number": "INV-2026-001" },
      "metadata": { "ai_call_log_id": "ai-log-uuid", "confidence": 0.92 },
      "created_at": "2026-02-26T10:00:18Z"
    }
  ]
}
```

### PATCH `/invoices/{id}/fields`
Manually correct extracted fields (AP Analyst).
```json
// Request
{
  "invoice_number": "INV-2026-001",
  "total_amount": 15420.00,
  "invoice_date": "2026-02-20",
  "line_items": [
    { "id": "li-uuid", "quantity": 200, "unit_price": 74.00 }
  ]
}
// Response 200 — updated invoice
```

### POST `/invoices/{id}/trigger-match`
Manually trigger matching (after correction).
- **Role**: AP_ANALYST, ADMIN
```json
// Response 202
{ "job_id": "celery-task-uuid", "message": "Matching triggered" }
```

---

## Exception Endpoints

### GET `/exceptions`
- **Role**: AP_ANALYST, ADMIN, AUDITOR
- **Query**: `status`, `exception_type`, `vendor_id`, `assigned_to`, `severity`, `page`, `page_size`

```json
// Response 200
{
  "items": [
    {
      "id": "exc-uuid",
      "invoice": { "id": "inv-uuid", "invoice_number": "INV-2026-001" },
      "vendor": { "id": "v-uuid", "name": "Acme Corp" },
      "exception_type": "PRICE_MISMATCH",
      "severity": "medium",
      "status": "open",
      "description": "Unit price $74.00 vs PO $60.00 (+23.3%, tolerance 2%)",
      "assigned_to": null,
      "sla_due_at": "2026-02-28T10:00:00Z",
      "created_at": "2026-02-26T10:05:00Z"
    }
  ],
  "total": 38,
  "page": 1,
  "page_size": 20
}
```

### GET `/exceptions/{id}`
Full exception detail with comments and match evidence.

### PATCH `/exceptions/{id}`
Update exception status, assign owner, add note.
```json
// Request
{
  "status": "in_progress",
  "assigned_to": "user-uuid",
  "resolution_note": "Contacted vendor, price increase approved by procurement."
}
```

### POST `/exceptions/{id}/comments`
```json
// Request
{ "body": "Vendor confirmed this is a rate adjustment per Q1 contract amendment." }
// Response 201
{ "id": "comment-uuid", "body": "...", "author": {...}, "created_at": "..." }
```

### POST `/exceptions/{id}/resolve`
Mark exception as resolved and proceed invoice to next step.
- **Role**: AP_ANALYST, ADMIN
```json
// Request
{ "resolution_note": "Price difference approved by procurement team (email attached)." }
```

---

## Approval Endpoints

### GET `/approvals`
My pending approval tasks.
- **Role**: APPROVER, ADMIN
```json
// Response 200
{
  "items": [
    {
      "id": "task-uuid",
      "invoice": { "id": "inv-uuid", "invoice_number": "INV-2026-001", "total_amount": 15420.00 },
      "vendor": { "id": "v-uuid", "name": "Acme Corp" },
      "level": 1,
      "status": "pending",
      "due_at": "2026-02-28T10:00:00Z",
      "created_at": "2026-02-26T10:10:00Z"
    }
  ]
}
```

### POST `/approvals/{id}/approve`
```json
// Request
{ "note": "Approved. Budget available." }
// Response 200
{ "task_id": "task-uuid", "status": "approved", "decided_at": "..." }
```

### POST `/approvals/{id}/reject`
```json
// Request
{ "note": "Wrong cost center. Please recode to CC-5100." }
// Response 200
{ "task_id": "task-uuid", "status": "rejected" }
```

---

## KPI Endpoints

### GET `/kpi/summary`
- **Role**: AP_ANALYST, ADMIN, AUDITOR
- **Query**: `date_from`, `date_to`

```json
// Response 200
{
  "period": { "from": "2026-02-01", "to": "2026-02-26" },
  "touchless_rate": 0.63,
  "exception_rate": 0.21,
  "avg_cycle_time_hours": 28.4,
  "total_invoices": 142,
  "total_amount_processed": 2840000.00,
  "by_status": {
    "matched": 89,
    "exception": 30,
    "pending_approval": 15,
    "approved": 8
  },
  "top_exception_types": [
    { "type": "PRICE_MISMATCH", "count": 18 },
    { "type": "PO_NOT_FOUND", "count": 8 }
  ]
}
```

### GET `/kpi/trends`
- **Query**: `metric` (touchless_rate|exception_rate|cycle_time), `granularity` (day|week), `date_from`, `date_to`

```json
// Response 200
{
  "metric": "touchless_rate",
  "granularity": "day",
  "data": [
    { "date": "2026-02-20", "value": 0.58 },
    { "date": "2026-02-21", "value": 0.65 },
    { "date": "2026-02-22", "value": 0.61 }
  ]
}
```

---

## Master Data Import Endpoints

### POST `/import/purchase-orders`
- **Content-Type**: `multipart/form-data`
- **Field**: `file` (CSV)
- CSV columns: `po_number, vendor_tax_id, currency, total_amount, cost_center, gl_account, issued_at, expires_at`

```json
// Response 202
{ "job_id": "celery-uuid", "message": "Import queued. 145 rows detected." }
```

### POST `/import/goods-receipts`
- CSV columns: `grn_number, po_number, received_at, po_line_number, qty_received, warehouse`

### POST `/import/vendors`
- CSV columns: `name, tax_id, bank_account, bank_routing, currency, payment_terms, email`

---

## Policy & Rules Endpoints

### POST `/policies/upload`
Upload a policy/contract document for rule extraction.
- **Role**: ADMIN
- **Content-Type**: `multipart/form-data`
- **Fields**: `file`, `doc_type` (policy|contract|sla), `name`, `vendor_id` (optional)

```json
// Response 201
{
  "id": "doc-uuid",
  "name": "Acme Corp Master Agreement 2026",
  "status": "uploaded",
  "job_id": "celery-uuid"  // async LLM extraction
}
```

### GET `/policies/{id}/extracted-rules`
View LLM-extracted rules pending human review.
```json
// Response 200
{
  "document_id": "doc-uuid",
  "status": "extracted",
  "extracted_rules": [
    {
      "id": "pr-uuid",
      "rule_type": "tolerance",
      "subject": "materials",
      "rule_json": { "price_tolerance_pct": 1.5, "qty_tolerance_pct": 2.0 },
      "source_text": "Price variances for materials shall not exceed 1.5%...",
      "confidence": 0.91,
      "reviewed": false
    }
  ]
}
```

### POST `/rules/versions`
Create a new rule version (start from draft).
- **Role**: ADMIN

### POST `/rules/versions/{id}/submit-review`
Move rule version from draft to in_review.

### POST `/rules/versions/{id}/publish`
Publish a rule version (makes it the active ruleset).
- **Role**: ADMIN
```json
// Response 200
{ "version_id": "rv-uuid", "version_number": 5, "published_at": "..." }
```

### GET `/rules/versions`
List all rule versions with status.

### GET `/rules/versions/active`
Get the currently published (active) ruleset.
