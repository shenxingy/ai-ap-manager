# Proposed Tasks — Complete All Remaining Gaps (15-Gap Goal)

> Generated: 2026-03-01
> Goal file: `goal-complete-all-gaps.md`
> Parallelization: Wave 1 (Phase 1-2 concurrent) → Wave 2 (Phase 3-4) → Wave 3 (Phase 5-6)

---

## Wave 1 — Phase 1: Email IMAP + Phase 2 Data Layer (run in parallel)

---

### Task 1A: Email IMAP Ingestion (Phase 1, GAP-1)

**Goal**: Implement real IMAP email polling for AP invoice ingestion (replaces file-drop testing mode).

**Context**:
- Work in `/home/alexshen/projects/ai-ap-manager`
- Backend: `docker exec ai-ap-manager-backend-1 <cmd>`
- Migrations: `docker exec ai-ap-manager-backend-1 alembic upgrade head`
- Commits: `committer "type: msg" file1 file2`
- Reference: `goal-complete-all-gaps.md` Phase 1 GAP-1 sections

**Acceptance Criteria**:
1. `docker exec ai-ap-manager-backend-1 python -c "from app.core.config import settings; print(settings.IMAP_HOST, settings.IMAP_USER)"` → prints empty strings (defaults)
2. `docker exec ai-ap-manager-backend-1 python -c "from app.workers.email_ingestion import poll_ap_mailbox; r = poll_ap_mailbox(); assert r['status'] in ('ok', 'skipped')"` → OK (skipped when IMAP not configured)
3. `docker exec ai-ap-manager-backend-1 alembic current` → head includes email migration
4. `docker exec ai-ap-manager-backend-1 python -c "from app.models.invoice import Invoice; import sqlalchemy; print(hasattr(Invoice, 'email_from'))"` → True

**Implementation** (follow `goal-complete-all-gaps.md` Phase 1 GAP-1 exactly):

#### Step 1: Config
Add IMAP settings to `backend/app/core/config.py`:
```python
IMAP_HOST: str = ""
IMAP_PORT: int = 993
IMAP_USER: str = ""
IMAP_PASSWORD: str = ""
IMAP_MAILBOX: str = "INBOX"
IMAP_POLL_INTERVAL_SECONDS: int = 300
```

#### Step 2: Migration
Create `backend/alembic/versions/XXX_add_email_fields_to_invoices.py` (get current head from `alembic history | head -3`).
Include: add columns `email_from`, `email_subject`, `email_received_at` to invoices table.

#### Step 3: Invoice Model
Add to `backend/app/models/invoice.py`:
```python
email_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
email_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
email_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

#### Step 4: IMAP Worker
Replace `poll_ap_mailbox()` in `backend/app/workers/email_ingestion.py` with real IMAP implementation.
Use `imaplib.IMAP4_SSL`, decode email headers, extract PDF/image attachments, create Invoice records via `_queue_email_invoice()` helper.

#### Step 5: Config Example
Update `.env.example` with IMAP block.

**Commits** (2 separate):
```
committer "feat: add IMAP config and email metadata migration" \
  backend/app/core/config.py \
  backend/alembic/versions/XXX_add_email_fields_to_invoices.py

committer "feat: implement real IMAP polling in email_ingestion worker" \
  backend/app/models/invoice.py \
  backend/app/workers/email_ingestion.py \
  .env.example
```

**OWN_FILES**:
- `backend/alembic/versions/XXX_add_email_fields_to_invoices.py` (create)
- `backend/app/workers/email_ingestion.py` (modify)
- `.env.example` (modify)

**SHARED_FILES**:
- `backend/app/core/config.py` (add IMAP settings)
- `backend/app/models/invoice.py` (add email fields)

---

### Task 2A: Multi-Currency FX Support (Phase 2, GAP-3)

**Goal**: Add FX rate model, ECB daily fetch task, and normalized_amount_usd for multi-currency matching.

**Context**: Same as Task 1A. Reference: `goal-complete-all-gaps.md` Phase 2 GAP-3.

**Acceptance Criteria**:
1. `docker exec ai-ap-manager-backend-1 python -c "from app.models.fx_rate import FxRate; print('OK')"` → OK
2. `docker exec ai-ap-manager-backend-1 python -c "from app.workers.fx_tasks import fetch_fx_rates; print(fetch_fx_rates.name)"` → app.workers.fx_tasks.fetch_fx_rates
3. `docker exec ai-ap-manager-backend-1 alembic current` → includes fx_rates migration
4. `docker exec ai-ap-manager-backend-1 python -c "from app.models.invoice import Invoice; print(hasattr(Invoice, 'normalized_amount_usd'))"` → True

**Implementation**:

#### Step 1: FX Model
Create `backend/app/models/fx_rate.py`:
```python
class FxRate(Base):
    __tablename__ = "fx_rates"
    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3))
    quote_currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[float]
    valid_date: Mapped[date]
    source: Mapped[str] = mapped_column(default="ecb")
    fetched_at: Mapped[datetime]
    # UNIQUE(base_currency, quote_currency, valid_date)
```

#### Step 2: Migration
Create migration for fx_rates table + normalized_amount_usd column on invoices.

#### Step 3: Config
Add to `backend/app/core/config.py`:
```python
BASE_CURRENCY: str = "USD"
FX_RATES_SOURCE: str = "ecb"
```

#### Step 4: FX Fetch Task
Create `backend/app/workers/fx_tasks.py`:
- `fetch_fx_rates()` Celery task
- Downloads ECB daily XML feed
- Parses EUR/X rates, derives USD/X rates
- Upserts into fx_rates table

#### Step 5: Beat Schedule
Register in `backend/app/workers/celery_app.py`:
```python
"fetch-fx-rates-daily": {
    "task": "app.workers.fx_tasks.fetch_fx_rates",
    "schedule": crontab(hour=6, minute=0),
}
```

#### Step 6: Invoice Model
Add to `backend/app/models/invoice.py`:
```python
normalized_amount_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
```

**Commits** (2 separate):
```
committer "feat: add FxRate model, migration, and ECB fetch task" \
  backend/app/models/fx_rate.py \
  backend/alembic/versions/XXX_add_fx_rates.py \
  backend/app/core/config.py \
  backend/app/models/invoice.py

committer "feat: register daily FX fetch in Celery beat schedule" \
  backend/app/workers/fx_tasks.py \
  backend/app/workers/celery_app.py
```

**OWN_FILES**:
- `backend/app/models/fx_rate.py` (create)
- `backend/alembic/versions/XXX_add_fx_rates.py` (create)
- `backend/app/workers/fx_tasks.py` (create)

**SHARED_FILES**:
- `backend/app/core/config.py` (add FX config)
- `backend/app/models/invoice.py` (add normalized_amount_usd)
- `backend/app/workers/celery_app.py` (add beat task)

---

### Task 3A: Vendor Risk Scoring (Phase 2, GAP-11)

**Goal**: Add vendor_risk_scores table, weekly scoring job, and auto-routing for HIGH/CRITICAL risk.

**Context**: Same as Task 1A. Reference: `goal-complete-all-gaps.md` Phase 2 GAP-11.

**Acceptance Criteria**:
1. `docker exec ai-ap-manager-backend-1 python -c "from app.models.vendor_risk import VendorRiskScore; print('OK')"` → OK
2. `docker exec ai-ap-manager-backend-1 python -c "from app.workers.vendor_risk_tasks import compute_vendor_risk_scores; print(compute_vendor_risk_scores.name)"` → OK
3. Alembic head includes vendor_risk_scores migration

**Implementation**:

#### Step 1: VendorRiskScore Model
Create `backend/app/models/vendor_risk.py`:
```python
class VendorRiskScore(Base):
    __tablename__ = "vendor_risk_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vendors.id"), index=True)
    ocr_error_rate: Mapped[float] = mapped_column(default=0.0)
    exception_rate: Mapped[float] = mapped_column(default=0.0)
    avg_extraction_confidence: Mapped[float] = mapped_column(default=1.0)
    score: Mapped[float] = mapped_column(default=0.0)  # 0.0–1.0, higher=riskier
    risk_level: Mapped[str] = mapped_column(String(10), default="LOW")  # LOW/MEDIUM/HIGH/CRITICAL
    computed_at: Mapped[datetime]
```

#### Step 2: Migration
Create migration for vendor_risk_scores table with vendor_id index.

#### Step 3: Risk Scoring Task
Create `backend/app/workers/vendor_risk_tasks.py`:
- `compute_vendor_risk_scores()` weekly task
- For each vendor: compute OCR error rate, exception rate, confidence
- Weighted score = exception_rate * 0.6 + ocr_error_rate * 0.4
- If HIGH/CRITICAL: create VENDOR_RISK exception on latest unmatched invoice

#### Step 4: Beat Schedule
Register in `backend/app/workers/celery_app.py`:
```python
"compute-vendor-risk-scores-weekly": {
    "task": "app.workers.vendor_risk_tasks.compute_vendor_risk_scores",
    "schedule": crontab(day_of_week=0, hour=2, minute=0),  # Sunday 2 AM
}
```

**Commits** (2 separate):
```
committer "feat: add VendorRiskScore model and weekly computation task" \
  backend/app/models/vendor_risk.py \
  backend/alembic/versions/XXX_add_vendor_risk_scores.py \
  backend/app/workers/vendor_risk_tasks.py

committer "feat: register vendor risk scoring in Celery beat schedule" \
  backend/app/workers/celery_app.py
```

**OWN_FILES**:
- `backend/app/models/vendor_risk.py` (create)
- `backend/alembic/versions/XXX_add_vendor_risk_scores.py` (create)
- `backend/app/workers/vendor_risk_tasks.py` (create)

**SHARED_FILES**:
- `backend/app/workers/celery_app.py` (add beat task)

---

### Task 4A: GDPR Data Retention (Phase 2, GAP-10)

**Goal**: Add retention config, monthly auto-delete task for old invoices and audit logs.

**Context**: Same as Task 1A. Reference: `goal-complete-all-gaps.md` Phase 2 GAP-10.

**Acceptance Criteria**:
1. `docker exec ai-ap-manager-backend-1 python -c "from app.core.config import settings; print(settings.RETENTION_DAYS_INVOICES)"` → 2555
2. `docker exec ai-ap-manager-backend-1 python -c "from app.workers.retention_tasks import run_data_retention; print('OK')"` → OK
3. Task is registered in beat schedule

**Implementation**:

#### Step 1: Config
Add to `backend/app/core/config.py`:
```python
RETENTION_DAYS_INVOICES: int = 2555  # 7 years
RETENTION_DAYS_AUDIT_LOGS: int = 365  # 1 year
RETENTION_ENABLED: bool = False  # must explicitly enable in prod
```

#### Step 2: Retention Task
Create `backend/app/workers/retention_tasks.py`:
- `run_data_retention()` monthly task
- Soft-delete invoices older than retention period (set deleted_at)
- Hard-delete audit logs older than retention period
- Log retention action to audit_logs

#### Step 3: Beat Schedule
Register in `backend/app/workers/celery_app.py`:
```python
"run-data-retention-monthly": {
    "task": "app.workers.retention_tasks.run_data_retention",
    "schedule": crontab(day_of_month=1, hour=3, minute=0),  # 1st of month, 3 AM
}
```

#### Step 4: .env.example
Add RETENTION config vars.

**Commits** (2 separate):
```
committer "feat: add GDPR data retention config and monthly task" \
  backend/app/core/config.py \
  backend/app/workers/retention_tasks.py \
  .env.example

committer "feat: register retention task in Celery beat schedule" \
  backend/app/workers/celery_app.py
```

**OWN_FILES**:
- `backend/app/workers/retention_tasks.py` (create)

**SHARED_FILES**:
- `backend/app/core/config.py` (add retention config)
- `backend/app/workers/celery_app.py` (add beat task)
- `.env.example` (update)

---

## Success Criteria (Wave 1 Complete)

1. All 4 tasks merged to main
2. `docker exec ai-ap-manager-backend-1 alembic current` → shows 4 new migrations at head
3. `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q` → all pass
4. Celery beat schedule has: fetch-fx-rates-daily, compute-vendor-risk-scores-weekly, run-data-retention-monthly
5. IMAP worker gracefully skips when IMAP_HOST is empty

---

## Wave 2 — Phase 3: Feature Layer (Tasks 5A–8A)

Will be queued after Wave 1 completes.

---

## Wave 3 — Phase 4-6: Architecture + Frontend + Tests

Will be queued after Wave 2 completes.
