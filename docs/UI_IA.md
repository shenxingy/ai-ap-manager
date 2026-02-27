# UI Information Architecture

**Framework**: Next.js 14 App Router + shadcn/ui + Tailwind CSS
**Layout**: Persistent left sidebar navigation, main content area, right panel for details

---

## Navigation Structure

```
/                         → redirect to /dashboard
/login                    → Login page
/dashboard                → AP Analyst Workbench (default landing)
/invoices                 → Invoice List
/invoices/[id]            → Invoice Detail + Audit Trail
/invoices/upload          → Invoice Upload
/exceptions               → Exception Queue
/exceptions/[id]          → Exception Detail
/approvals                → My Approval Tasks
/approvals/[id]           → Approval Detail
/kpi                      → KPI Dashboard
/admin/users              → User Management (ADMIN only)
/admin/matrix             → Approval Matrix Config (ADMIN only)
/admin/rules              → Rule Version Management (ADMIN only)
/admin/vendors            → Vendor Master Data (ADMIN only)
/admin/policies           → Policy Document Upload & Rule Review (ADMIN only)
/audit                    → Audit Log Explorer (AUDITOR, ADMIN)
```

---

## Pages & Components

### 1. Login `/login`
- **Components**: Logo, email input, password input, submit button
- **States**: loading, error (invalid credentials)

---

### 2. AP Analyst Workbench `/dashboard`
The primary landing page for AP_ANALYST and AP_CLERK.

**Summary Cards (top row)**
| Card | Value | Sub-label |
|------|-------|-----------|
| Invoices Today | 24 | ↑5 from yesterday |
| Pending Review | 8 | Require attention |
| Open Exceptions | 30 | 5 critical |
| Avg Cycle Time | 28.4h | Target: 24h |

**Main Content (two columns)**
- Left: "Needs Action" feed — recent invoices in status `extracted` (need review) or `exception`
- Right: Quick stats chart — touchless rate trend (7 days)

**Needs Action Table columns**:
`Invoice #` | `Vendor` | `Amount` | `Status` | `Age` | `Action`

---

### 3. Invoice List `/invoices`

**Filters (sidebar or top bar)**
- Status (multiselect): received, extracting, extracted, matching, matched, exception, pending_approval, approved, rejected, paid
- Vendor (searchable dropdown)
- Date range (from / to)
- Amount range (min / max)
- PO Number (text search)

**Table columns**:
| Column | Notes |
|--------|-------|
| Invoice # | Clickable → detail |
| Vendor | Vendor name |
| PO # | If linked |
| Status | Badge with color |
| Amount | Right-aligned, currency |
| Invoice Date | |
| Due Date | Red if overdue |
| Confidence | % badge (hidden if manually entered) |
| Created | |
| Actions | View, Re-trigger match |

**Pagination**: 20 per page, total count shown

---

### 4. Invoice Detail `/invoices/[id]`

**Header Section**
- Invoice number, status badge, vendor name, total amount
- Action buttons: `Correct Fields`, `Re-trigger Match`, `View Document`

**Tab Layout**
1. **Overview**
   - Header fields: invoice_date, due_date, currency, subtotal, tax, freight, total
   - Extraction confidence badge
   - PO link
   - Line items table: `Line #` | `Description` | `Qty` | `Unit Price` | `Unit` | `Total` | `Confidence`

2. **Match Results**
   - Match type (2-way / 3-way)
   - Per-line match status with variance details
   - PO line comparison side-by-side
   - GRN details (if 3-way)
   - Rule version used (with link)

3. **Exceptions**
   - List of all exceptions for this invoice
   - Status, type, severity, assigned to
   - Quick link to each exception detail

4. **Approvals**
   - Approval chain visualization (level 1 → level 2 → ...)
   - Each task: approver name, status, decision note, decided_at

5. **Audit Trail**
   - Timeline view, newest first
   - Each event: timestamp, actor (user/system/AI), action, old→new value
   - AI events show link to `ai_call_logs` detail

---

### 5. Invoice Upload `/invoices/upload`

**Upload Area**
- Drag & drop zone or file browser
- Accepted: PDF, PNG, JPG, JPEG (max 20MB)
- Optional pre-fill: Vendor (dropdown), PO Number (text)

**After Upload**
- Progress indicator: Uploading → OCR → Extracting → Done
- Auto-redirect to invoice detail on completion

---

### 6. Exception Queue `/exceptions`

The most-used page for AP Analysts. Must be fast and filterable.

**Filters**
- Status: open, in_progress, resolved, escalated
- Exception Type (multiselect)
- Severity: low / medium / high / critical
- Assigned To (dropdown, includes "Unassigned")
- Vendor
- SLA: "SLA at risk" toggle (due in < 24h)

**Table columns**:
| Column | Notes |
|--------|-------|
| Exception ID | |
| Invoice # | Link to invoice |
| Vendor | |
| Type | Badge: PRICE_MISMATCH, PO_NOT_FOUND, etc. |
| Severity | Color-coded badge |
| Status | open / in_progress / resolved |
| Description | Truncated, tooltip on hover |
| Assigned To | Avatar + name, or "Unassigned" |
| SLA Due | Red if < 24h, orange if < 48h |
| Age | "2d 4h" |
| Actions | Assign, Resolve, View |

**Bulk Actions**: Select multiple → assign / change status

---

### 7. Exception Detail `/exceptions/[id]`

**Header**: Exception type badge, status, severity, invoice link

**Evidence Panel (left)**
- Invoice line item values
- PO line item values (side-by-side comparison)
- GRN values (if applicable)
- Highlighted variance fields in red

**Action Panel (right)**
- Assign to (user dropdown)
- Status change (dropdown + save)
- Resolution note (textarea)
- Resolve button

**Comment Thread (bottom)**
- Chronological comments with author avatar and timestamp
- Add comment input (supports markdown)

---

### 8. Approval Tasks `/approvals`

For APPROVER role — their primary working page.

**My Pending Approvals Table**:
| Column | Notes |
|--------|-------|
| Invoice # | |
| Vendor | |
| Amount | Large, prominent |
| PO # | |
| Exception Summary | If was an exception, brief summary |
| Due Date | With urgency indicator |
| Level | e.g. "Level 1 of 2" |
| Actions | `Approve` / `Reject` (inline quick actions) |

---

### 9. Approval Detail `/approvals/[id]`

- Full invoice detail (read-only view)
- Original PDF viewer (embedded)
- Match results summary
- Exception resolution notes (if applicable)
- **Approve** button (green, prominent) with note input
- **Reject** button (red) with mandatory note input
- Approval chain visualization

---

### 10. KPI Dashboard `/kpi`

**Date Range Picker** (top right): Last 7d / 30d / 90d / Custom

**KPI Cards Row**
| Metric | Value | Target | Trend |
|--------|-------|--------|-------|
| Touchless Rate | 63% | 70% | ↑3% |
| Exception Rate | 21% | <15% | ↓2% |
| Avg Cycle Time | 28.4h | 24h | ↔ |
| Total Processed | $2.84M | — | — |

**Charts**
1. Touchless rate trend (line chart, daily)
2. Exception by type (bar chart, top 5 types)
3. Invoice volume by status (stacked bar, daily)
4. Top 10 vendors by exception count (horizontal bar)
5. Cycle time distribution (histogram)

---

### 11. Admin — Rule Versions `/admin/rules`

**Rule Version Table**:
| Version | Name | Status | Created | Published | Actions |
|---------|------|--------|---------|-----------|---------|
| v5 | Q1 2026 Tolerance Update | published | ... | ... | View |
| v4 | Contract Amendment Acme | archived | ... | ... | View |
| v6 (draft) | AI Suggestion: Loosen freight | draft | ... | — | Edit / Submit Review / Delete |

**Version Detail Drawer**:
- Full `rules_json` displayed as readable table
- Diff view vs current published version
- Publish / Archive actions (ADMIN only)

---

### 12. Admin — Approval Matrix `/admin/matrix`

**Matrix Table (editable)**:
| Amount Min | Amount Max | Cost Center | Category | Approver Role | Level |
|-----------|-----------|-------------|----------|---------------|-------|
| $0 | $10,000 | — | — | AP_ANALYST (auto) | 1 |
| $10,001 | $50,000 | — | — | DEPT_MANAGER | 1 |
| $50,001 | $200,000 | — | — | FINANCE_VP | 1 |

**Add Rule** button opens inline form.

---

### 13. Audit Log Explorer `/audit`

For AUDITOR and ADMIN.

**Filters**: Entity type, Entity ID, Actor, Action, Date range

**Table**:
| Timestamp | Entity | Actor | Action | Changes |
|-----------|--------|-------|--------|---------|
| 2026-02-26 10:05 | invoice:INV-2026-001 | AI Extractor | extraction_complete | +invoice_number, +total |
| 2026-02-26 10:10 | exception:exc-001 | Jane Doe | status_changed | open → in_progress |

**Export to CSV** button (AUDITOR role).
