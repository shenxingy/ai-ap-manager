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

## [2026-02-27] Backend review and quality fixes

**Result**: success

**What was done**:
- Reviewed all 22 backend Python files for bugs, type inconsistencies, and import issues
- Fixed `User.deleted_at` column type: was `String` instead of `DateTime(timezone=True)` — inconsistent with all other soft-delete columns
- Removed unused imports in `auth.py` (`timedelta`, `hash_password as get_password_hash`)
- Added `broker_connection_retry_on_startup=True` to Celery config to eliminate CPendingDeprecationWarning in worker
- Created missing `__init__.py` for `app/`, `app/core/`, `app/db/` packages
- Added test scaffold: `tests/__init__.py`, `tests/test_health.py`, `tests/test_auth.py`

**Lessons**:
- When reviewing models for consistency, always check that all soft-delete columns use the same type. `User.deleted_at` used `String` while all other models correctly used `DateTime(timezone=True)`.
- Celery 5+ emits `CPendingDeprecationWarning` unless `broker_connection_retry_on_startup=True` is explicitly set — add this to all new Celery configs.
- Docker containers own their `__pycache__` directories; using `python3 -m py_compile` from host will fail with PermissionError on cache write — use `ast.parse()` instead for host-side syntax validation.
- The test scaffold uses `httpx.AsyncClient` with `ASGITransport` for in-process ASGI testing, and mocks `get_session` via `app.dependency_overrides` to avoid needing a real database.

## [2026-02-27] Invoice Ingestion & OCR Extraction Pipeline

**Result**: success

**What was done**:
- Created `app/services/storage.py` — thin MinIO SDK wrapper (upload, download, presigned URL, delete, bucket auto-create on startup)
- Created `app/services/audit.py` — sync `log()` helper that writes to `audit_logs`; uses `db.flush()` so caller controls commit
- Created `app/ai/extractor.py` — dual-pass Claude extraction: `run_extraction_pass()`, `compare_passes()`, `merge_passes()`; all calls logged to `ai_call_logs`; invalid/missing API key caught gracefully (WARNING log, empty fields returned)
- Created `app/schemas/invoice.py` — `InvoiceUploadResponse`, `InvoiceListItem`, `InvoiceDetail`, `InvoiceListResponse`, `InvoiceLineItemOut`, `ExtractionResultOut`
- Created `app/api/v1/invoices.py` — `POST /upload` (multipart, 20MB limit, MIME validation), `GET /` (paginated, filtered), `GET /{id}` (with line_items + extraction_results eager-loaded)
- Updated `app/api/v1/router.py` — wired invoice router
- Updated `app/workers/tasks.py` — implemented full `process_invoice` Celery task: fetch invoice → MinIO download → OCR (pdf2image + pytesseract) → dual-pass LLM → store ExtractionResult records → update Invoice fields → set status extracted/exception → audit log
- Updated `app/main.py` — `ensure_bucket()` called in lifespan startup

**Verified end-to-end**:
- `POST /api/v1/invoices/upload` → 201, invoice_id in response, DB record status=ingested
- Celery worker picks up task, sets status=extracting, runs OCR + LLM, stores 2 ExtractionResult rows, sets status=exception (expected with placeholder API key)
- `GET /api/v1/invoices` → paginated list
- `GET /api/v1/invoices/{id}` → full detail with extraction_results
- Swagger `/api/docs` includes all 3 invoice routes

**Lessons**:
- Celery workers don't hot-reload like uvicorn — must `docker-compose restart worker` after tasks.py changes
- Celery tasks must use sync SQLAlchemy session (`DATABASE_URL_SYNC` + `create_engine`), not async — async sessions cannot be used in synchronous Celery workers
- `audit_svc.log()` uses `db.flush()` not `db.commit()` — the caller controls transaction boundaries. This is the correct pattern to avoid partial commits mid-task.
- For MinIO `put_object`, length must be computed before passing a stream — seek to end, get position, seek back to 0.
- Worker subprocess inherits the Celery env; imports inside the task function (lazy imports) prevent import-time failures when optional packages (anthropic) are not yet available.
- The `process_invoice` task correctly transitions to `exception` when both OCR text is empty AND both LLM passes fail — this is correct behavior for the placeholder API key scenario.

<!-- Future entries go here, newest first -->
<!-- Format:
## [YYYY-MM-DD] Task: <what was done>
**Result**: success / partial / failed
**Lessons**:
- What worked: ...
- What failed: ...
- Key insight: ...
-->
