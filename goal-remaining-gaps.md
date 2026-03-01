# Goal: Fix All Remaining Gaps — AI AP Manager (Round 2)

## Context

All 15 original gaps from docs/GAP_ANALYSIS.md are closed. A second-pass audit found
additional incomplete features. Fix them all.

---

## Requirements

### DONE (already fixed before loop)
- [x] Celery task name mismatch: `detect_recurring_patterns` fixed to `app.workers.tasks.detect_recurring_patterns`

---

### [x] GAP-A: entity_id FK on PurchaseOrder and GoodsReceipt

**Priority**: P1

`backend/app/models/invoice.py` and `backend/app/models/vendor.py` already have `entity_id`.
BUT `purchase_order.py` and `goods_receipt.py` do NOT. Multi-entity support is incomplete.

**What to implement**:
1. Add to `backend/app/models/purchase_order.py`:
   ```python
   entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"), nullable=True, index=True)
   ```
2. Add same column to `backend/app/models/goods_receipt.py`
3. Generate migration: `alembic revision --autogenerate -m "add entity_id to purchase_orders and goods_receipts"`
4. Run migration in container

**Success criteria**:
- `grep "entity_id" backend/app/models/purchase_order.py` → has FK line
- `grep "entity_id" backend/app/models/goods_receipt.py` → has FK line
- `ls backend/alembic/versions/ | grep entity_id` → migration file exists

---

### GAP-B: GL Classifier Status API + Frontend Settings Card

**Priority**: P1

The GL ML classifier (`backend/app/services/gl_classifier.py`) trains and saves models to MinIO,
but there is no API endpoint to query its status, and the frontend `/admin/settings` page
does not show model version, accuracy, or last retrain time.

**What to implement**:

**Backend** — add to `backend/app/api/v1/admin.py` (or create a separate small file):
```
GET /admin/gl-classifier/status
```
Response:
```json
{
  "model_version": "v3",
  "accuracy": 0.89,
  "trained_at": "2026-02-28T04:00:00Z",
  "training_samples": 142,
  "status": "ready"   // or "not_trained" if no model in MinIO
}
```
The gl_classifier module already has `_model_cache` dict and MinIO storage. Read the latest
model metadata from MinIO object tags or a small JSON sidecar file `models/gl-coding-latest.json`
that `retrain_gl_classifier` writes after each successful train.

Update `backend/app/workers/ml_tasks.py` `retrain_gl_classifier()` to write
`models/gl-coding-latest.json` with: `{version, accuracy, trained_at, training_samples}` after
saving the model pkl.

**Frontend** — add a card to `frontend/src/app/(app)/admin/settings/page.tsx`:
- Query `GET /api/v1/admin/gl-classifier/status`
- Show: Model Version, Accuracy (%), Last Retrain date, Training Samples
- Show "Not trained yet" state if no model
- Place below the existing Email Ingestion Status card

**Success criteria**:
- `curl /api/v1/admin/gl-classifier/status` returns JSON (200 or 200 with status=not_trained)
- `grep "gl-classifier" frontend/src/app/(app)/admin/settings/page.tsx` → found

---

### [x] GAP-C: Entity Selector in Frontend Header

**Priority**: P2

The `entities` API exists (`GET /api/v1/entities`), but there is no UI to switch between entities.
Users managing multiple business entities have no way to scope the view.

**What to implement**:
- In `frontend/src/components/layout/AppShell.tsx` (or `Sidebar.tsx`), add an entity selector:
  - Query `GET /api/v1/entities`
  - If only 1 entity (or 0 entities), hide the selector
  - If >1 entity, show a `<Select>` dropdown in the header/sidebar top area
  - Store selected entity_id in `localStorage` (key: `selectedEntityId`)
  - Display "All Entities" as default option
- This is a pure UI component; no backend changes needed

**Success criteria**:
- `grep -r "EntitySelector\|selectedEntityId\|/entities" frontend/src/components/layout/` → found

**COMPLETED**: Added entity selector to Sidebar.tsx with localStorage persistence (24ec120)

---

### GAP-D: FX Normalized Amount in Invoice Detail

**Priority**: P2

The FX rates table is populated daily, but invoice detail doesn't show the normalized USD amount
when the invoice currency is not USD. Users can't see "Original: €5,200 → $5,618 (rate: 1.08)"

**What to implement**:

**Backend** — extend `GET /api/v1/invoices/{id}` response schema to include:
- `normalized_amount_usd: float | None` — the invoice total in USD (if FX rate available)
- `fx_rate_used: float | None` — the FX rate applied
- `fx_rate_date: str | None` — date of the FX rate

In `backend/app/api/v1/invoices.py` invoice detail endpoint, after fetching the invoice,
if `invoice.currency != "USD"` and `invoice.total_amount`:
  - Query `fx_rates` table for latest rate: `SELECT rate FROM fx_rates WHERE base_currency='USD' AND quote_currency=invoice.currency ORDER BY valid_date DESC LIMIT 1`
  - Compute `normalized_amount_usd = total_amount / rate` (since rates are quote/base = currency/USD)
  - Add to response

**Frontend** — in `frontend/src/app/(app)/invoices/[id]/page.tsx`:
- After the `Total Amount` field, if `normalized_amount_usd` is present and currency != USD:
  - Show: `≈ $5,618 USD (rate: 1.0804 on 2026-02-26)`
  - Use muted/secondary text styling

**Success criteria**:
- `grep "normalized_amount_usd" backend/app/api/v1/invoices.py` → found
- `grep "normalized_amount_usd\|fx_rate_used" frontend/src/app/(app)/invoices/[id]/page.tsx` → found

---

### [x] GAP-E: TODO.md Drift Cleanup

**Priority**: P3 (documentation)

Many items in TODO.md are marked `[ ]` but are actually implemented. Update them to `[x]`.

Key items to mark done (verify each against codebase first):
- Email IMAP ingestion (line ~453) ✓
- RecurringInvoicePattern model + detection (lines ~537-560) ✓
- GL ML classifier training pipeline (lines ~683-697) ✓
- ERP integration (SAP + Oracle CSV, lines ~797-816) ✗ (not implemented)
- FX rates infrastructure (lines ~828-843) ✓
- Mobile PWA manifest + responsive approvals (lines ~888-891, leave service worker [ ]) ✓
- Benchmark endpoint + dashboard card (lines ~969-972) ✓
- Inspection reports + 4-way match (lines ~980-990) ✓
- Slack/Teams notifications (lines ~997-1001, leave in-app notifications [ ]) ✓
- Invoice templates (lines ~1007-1009) ✓
- Vendor risk scoring (lines ~1022-1025) ✓
- GDPR retention (lines ~1028-1033) ✗ (not implemented)
- Multi-entity tables + API (lines ~1039-1042, leave "entity selector in frontend header" as [ ] — being done in GAP-C above) ✓

**Success criteria**:
- `grep -c "^\- \[ \]" TODO.md` → count reduced significantly (from ~211 to ~80 or fewer)

**COMPLETED**: Marked 11/13 items as complete in TODO.md (da9e6d5). ERP integration and GDPR retention remain unimplemented.

---

## Success Criteria (Overall)

All of the following must be true:
1. `grep "entity_id" backend/app/models/purchase_order.py` → FK line present
2. `grep "entity_id" backend/app/models/goods_receipt.py` → FK line present
3. `curl /api/v1/admin/gl-classifier/status` returns 200 (or JSON with status field)
4. `grep "gl-classifier" frontend/src/app/(app)/admin/settings/page.tsx` → found
5. `grep -r "selectedEntityId\|EntitySelector" frontend/src/components/layout/` → found
6. `grep "normalized_amount_usd" backend/app/api/v1/invoices.py` → found
7. `grep -c "^\- \[ \]" TODO.md` → less than 120

STATUS: GAP-A (pending), GAP-B (pending), GAP-C (✓ DONE), GAP-D (pending), GAP-E (✓ DONE)
