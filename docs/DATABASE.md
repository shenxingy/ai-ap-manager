# Database Design — ERD & Table Schemas

**Engine**: PostgreSQL 16
**Conventions**: snake_case, UUID primary keys, `created_at`/`updated_at` on every table, soft-delete via `deleted_at`.

---

## Table Overview

```
users ──────────────────────────────────────────────────────┐
roles                                                        │
                                                             │
vendors ←── vendor_aliases                                   │
    ↓                                                        │
purchase_orders ←── po_line_items                            │
    ↓                                                        │
goods_receipts ←── grn_line_items                            │
    ↓                                                        │
invoices ←── invoice_line_items ←── match_results            │
    ↓                                                        │
exceptions ←── exception_comments ←──────────────────────── ┘
    ↓
approval_tasks ←── approval_matrix
    ↓
audit_logs

rule_versions ←── policy_documents ←── policy_rules
ai_call_logs
```

---

## Core Tables

### `users`
```sql
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('AP_CLERK','AP_ANALYST','APPROVER','ADMIN','AUDITOR')),
    is_active   BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
```

### `vendors`
```sql
CREATE TABLE vendors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    tax_id          TEXT,
    bank_account    TEXT,
    bank_routing    TEXT,
    currency        TEXT NOT NULL DEFAULT 'USD',
    payment_terms   INTEGER NOT NULL DEFAULT 30,  -- days
    email           TEXT,
    address         TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);
CREATE INDEX idx_vendors_tax_id ON vendors(tax_id);
CREATE INDEX idx_vendors_name ON vendors USING GIN (to_tsvector('english', name));
```

### `vendor_aliases`
```sql
CREATE TABLE vendor_aliases (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id   UUID NOT NULL REFERENCES vendors(id),
    alias       TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_vendor_aliases_vendor_id ON vendor_aliases(vendor_id);
CREATE UNIQUE INDEX idx_vendor_aliases_unique ON vendor_aliases(vendor_id, alias);
```

### `purchase_orders`
```sql
CREATE TABLE purchase_orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    po_number       TEXT NOT NULL UNIQUE,
    vendor_id       UUID NOT NULL REFERENCES vendors(id),
    status          TEXT NOT NULL DEFAULT 'open'  -- open, partial, closed, cancelled
                    CHECK (status IN ('open','partial','closed','cancelled')),
    currency        TEXT NOT NULL DEFAULT 'USD',
    total_amount    NUMERIC(18,4) NOT NULL,
    cost_center     TEXT,
    gl_account      TEXT,
    buyer_id        UUID REFERENCES users(id),
    issued_at       TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);
CREATE INDEX idx_po_vendor_id ON purchase_orders(vendor_id);
CREATE INDEX idx_po_status ON purchase_orders(status);
```

### `po_line_items`
```sql
CREATE TABLE po_line_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    po_id           UUID NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    line_number     INTEGER NOT NULL,
    description     TEXT NOT NULL,
    quantity        NUMERIC(18,4) NOT NULL,
    unit_price      NUMERIC(18,4) NOT NULL,
    unit            TEXT,
    category        TEXT,
    gl_account      TEXT,
    received_qty    NUMERIC(18,4) NOT NULL DEFAULT 0,  -- aggregated from GRNs
    invoiced_qty    NUMERIC(18,4) NOT NULL DEFAULT 0,  -- aggregated from invoices
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_po_line_po_line ON po_line_items(po_id, line_number);
```

### `goods_receipts`
```sql
CREATE TABLE goods_receipts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grn_number      TEXT NOT NULL UNIQUE,
    po_id           UUID NOT NULL REFERENCES purchase_orders(id),
    vendor_id       UUID NOT NULL REFERENCES vendors(id),
    received_at     TIMESTAMPTZ NOT NULL,
    warehouse       TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_grn_po_id ON goods_receipts(po_id);
```

### `grn_line_items`
```sql
CREATE TABLE grn_line_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grn_id          UUID NOT NULL REFERENCES goods_receipts(id) ON DELETE CASCADE,
    po_line_item_id UUID NOT NULL REFERENCES po_line_items(id),
    quantity_received NUMERIC(18,4) NOT NULL,
    unit            TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_grn_line_grn_id ON grn_line_items(grn_id);
CREATE INDEX idx_grn_line_po_line ON grn_line_items(po_line_item_id);
```

---

## Invoice Tables

### `invoices`
```sql
CREATE TABLE invoices (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number      TEXT NOT NULL,
    vendor_id           UUID REFERENCES vendors(id),
    po_id               UUID REFERENCES purchase_orders(id),
    status              TEXT NOT NULL DEFAULT 'received'
                        CHECK (status IN (
                            'received','extracting','extracted','validating',
                            'matching','matched','exception','pending_approval',
                            'approved','rejected','paid','cancelled'
                        )),
    document_type       TEXT NOT NULL DEFAULT 'invoice'
                        CHECK (document_type IN ('invoice','credit_memo','debit_memo','pro_forma')),
    currency            TEXT NOT NULL DEFAULT 'USD',
    subtotal            NUMERIC(18,4),
    tax_amount          NUMERIC(18,4),
    freight_amount      NUMERIC(18,4),
    total_amount        NUMERIC(18,4),
    invoice_date        DATE,
    due_date            DATE,
    payment_terms_days  INTEGER,
    -- Extraction metadata
    storage_path        TEXT NOT NULL,  -- MinIO object key
    ocr_raw_text        TEXT,
    extraction_confidence NUMERIC(5,4),  -- 0.0 to 1.0
    manually_corrected  BOOLEAN NOT NULL DEFAULT false,
    -- Duplicate detection
    is_duplicate        BOOLEAN NOT NULL DEFAULT false,
    duplicate_of        UUID REFERENCES invoices(id),
    -- Soft delete
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ
);
CREATE UNIQUE INDEX idx_invoice_number_vendor ON invoices(invoice_number, vendor_id)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_invoice_status ON invoices(status);
CREATE INDEX idx_invoice_vendor ON invoices(vendor_id);
CREATE INDEX idx_invoice_po ON invoices(po_id);
CREATE INDEX idx_invoice_due_date ON invoices(due_date);
```

### `invoice_line_items`
```sql
CREATE TABLE invoice_line_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id      UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    line_number     INTEGER NOT NULL,
    po_line_item_id UUID REFERENCES po_line_items(id),  -- linked during matching
    description     TEXT,
    quantity        NUMERIC(18,4),
    unit_price      NUMERIC(18,4),
    unit            TEXT,
    line_total      NUMERIC(18,4),
    tax_rate        NUMERIC(5,4),
    gl_account      TEXT,
    cost_center     TEXT,
    extraction_confidence NUMERIC(5,4),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_inv_line_invoice ON invoice_line_items(invoice_id);
```

---

## Matching & Exception Tables

### `match_results`
```sql
CREATE TABLE match_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id      UUID NOT NULL REFERENCES invoices(id),
    invoice_line_id UUID REFERENCES invoice_line_items(id),
    po_line_id      UUID REFERENCES po_line_items(id),
    grn_line_id     UUID REFERENCES grn_line_items(id),
    match_type      TEXT NOT NULL CHECK (match_type IN ('2_WAY','3_WAY')),
    match_status    TEXT NOT NULL CHECK (match_status IN (
                        'MATCHED','PARTIAL_MATCH','MISMATCH','PO_NOT_FOUND','GRN_NOT_FOUND'
                    )),
    -- Variance details
    qty_variance    NUMERIC(18,4),
    qty_variance_pct NUMERIC(8,4),
    price_variance  NUMERIC(18,4),
    price_variance_pct NUMERIC(8,4),
    -- Tolerance applied
    qty_tolerance_pct NUMERIC(8,4),
    price_tolerance_pct NUMERIC(8,4),
    within_tolerance BOOLEAN NOT NULL DEFAULT false,
    -- Rule traceability
    rule_version_id UUID,  -- which rule version was active
    matched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_match_invoice ON match_results(invoice_id);
```

### `exceptions`
```sql
CREATE TABLE exceptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id      UUID NOT NULL REFERENCES invoices(id),
    exception_type  TEXT NOT NULL CHECK (exception_type IN (
                        'PRICE_MISMATCH','QTY_MISMATCH','PO_NOT_FOUND','GRN_NOT_FOUND',
                        'DUPLICATE_INVOICE','VENDOR_DATA_MISMATCH','TAX_DISCREPANCY',
                        'FREIGHT_DISCREPANCY','UNEXPECTED_CHARGE','OCR_LOW_CONFIDENCE',
                        'MISSING_REQUIRED_FIELD','SLA_BREACH','OTHER'
                    )),
    severity        TEXT NOT NULL DEFAULT 'medium'
                    CHECK (severity IN ('low','medium','high','critical')),
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open','in_progress','resolved','escalated','rejected')),
    description     TEXT NOT NULL,
    resolution_note TEXT,
    assigned_to     UUID REFERENCES users(id),
    resolved_by     UUID REFERENCES users(id),
    resolved_at     TIMESTAMPTZ,
    sla_due_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_exception_invoice ON exceptions(invoice_id);
CREATE INDEX idx_exception_status ON exceptions(status);
CREATE INDEX idx_exception_assigned ON exceptions(assigned_to);
```

### `exception_comments`
```sql
CREATE TABLE exception_comments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exception_id    UUID NOT NULL REFERENCES exceptions(id) ON DELETE CASCADE,
    author_id       UUID NOT NULL REFERENCES users(id),
    body            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_exc_comment_exception ON exception_comments(exception_id);
```

---

## Approval Tables

### `approval_matrix`
```sql
CREATE TABLE approval_matrix (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    amount_min      NUMERIC(18,4) NOT NULL DEFAULT 0,
    amount_max      NUMERIC(18,4),             -- NULL = unlimited
    cost_center     TEXT,                       -- NULL = all cost centers
    category        TEXT,                       -- NULL = all categories
    approver_role   TEXT NOT NULL,
    approver_id     UUID REFERENCES users(id),  -- specific user override
    level           INTEGER NOT NULL DEFAULT 1, -- for sequential multi-level
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `approval_tasks`
```sql
CREATE TABLE approval_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id      UUID NOT NULL REFERENCES invoices(id),
    approver_id     UUID NOT NULL REFERENCES users(id),
    level           INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','approved','rejected','delegated','expired')),
    decision_note   TEXT,
    decided_at      TIMESTAMPTZ,
    due_at          TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_approval_task_invoice ON approval_tasks(invoice_id);
CREATE INDEX idx_approval_task_approver ON approval_tasks(approver_id, status);
```

---

## Rules & Policy Tables

### `rule_versions`
```sql
CREATE TABLE rule_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_number  INTEGER NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','in_review','published','archived')),
    rules_json      JSONB NOT NULL,  -- serialized rule set
    published_at    TIMESTAMPTZ,
    published_by    UUID REFERENCES users(id),
    reviewed_by     UUID REFERENCES users(id),
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_rule_version_number ON rule_versions(version_number);
CREATE INDEX idx_rule_version_status ON rule_versions(status);
```

### `policy_documents`
```sql
CREATE TABLE policy_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    doc_type        TEXT NOT NULL CHECK (doc_type IN ('policy','contract','sla','other')),
    storage_path    TEXT NOT NULL,
    vendor_id       UUID REFERENCES vendors(id),  -- NULL = global policy
    status          TEXT NOT NULL DEFAULT 'uploaded'
                    CHECK (status IN ('uploaded','processing','extracted','reviewed','archived')),
    extracted_rules JSONB,  -- LLM output before human review
    created_by      UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `policy_rules`
```sql
CREATE TABLE policy_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_doc_id   UUID NOT NULL REFERENCES policy_documents(id),
    rule_version_id UUID REFERENCES rule_versions(id),
    rule_type       TEXT NOT NULL CHECK (rule_type IN (
                        'tolerance','approval_threshold','payment_term','prohibition','other'
                    )),
    subject         TEXT NOT NULL,  -- e.g. "materials", "vendor:ABC"
    rule_json       JSONB NOT NULL,
    source_text     TEXT,  -- original text from document (evidence)
    confidence      NUMERIC(5,4),
    reviewed        BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## Audit & AI Log Tables

### `audit_logs`
```sql
CREATE TABLE audit_logs (
    id              BIGSERIAL PRIMARY KEY,  -- sequential for ordering
    entity_type     TEXT NOT NULL,  -- 'invoice', 'exception', 'approval_task', etc.
    entity_id       UUID NOT NULL,
    actor_id        UUID REFERENCES users(id),
    actor_type      TEXT NOT NULL DEFAULT 'user'
                    CHECK (actor_type IN ('user','system','ai')),
    action          TEXT NOT NULL,  -- 'status_changed', 'field_corrected', 'rule_applied', etc.
    old_value       JSONB,
    new_value       JSONB,
    metadata        JSONB,          -- rule_version_id, match_result_id, etc.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    -- NO updated_at — immutable
);
CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_created_at ON audit_logs(created_at);
CREATE INDEX idx_audit_actor ON audit_logs(actor_id);
```

### `ai_call_logs`
```sql
CREATE TABLE ai_call_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purpose         TEXT NOT NULL CHECK (purpose IN (
                        'extraction','policy_parse','root_cause','rule_suggestion','other'
                    )),
    entity_type     TEXT,
    entity_id       UUID,
    model           TEXT NOT NULL,
    prompt_tokens   INTEGER,
    completion_tokens INTEGER,
    latency_ms      INTEGER,
    success         BOOLEAN NOT NULL,
    error_message   TEXT,
    input_hash      TEXT,       -- hash of prompt for dedup detection
    output_json     JSONB,      -- structured output
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_ai_log_entity ON ai_call_logs(entity_type, entity_id);
CREATE INDEX idx_ai_log_purpose ON ai_call_logs(purpose);
```
