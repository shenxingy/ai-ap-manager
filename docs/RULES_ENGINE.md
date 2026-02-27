# Rules Engine Design

The rules engine is **fully deterministic** — no LLM in the hot path.
LLM is only used to *extract* rules from documents. Once rules are published,
all matching and routing decisions are made by this engine.

---

## 1. Match Engine Pseudocode

### 2-Way Match (Invoice vs PO)

```python
def run_2way_match(invoice: Invoice, po: PurchaseOrder, config: MatchConfig) -> MatchResult:
    results = []
    for inv_line in invoice.line_items:
        po_line = find_po_line(po, inv_line)  # match by description/GL/sequence
        if po_line is None:
            results.append(LineMatchResult(
                status=MISMATCH,
                exception_type=PO_NOT_FOUND,
                description=f"No matching PO line for: {inv_line.description}"
            ))
            continue

        tolerance = config.get_tolerance(vendor=invoice.vendor, category=po_line.category)

        # Price check
        price_variance_pct = abs(inv_line.unit_price - po_line.unit_price) / po_line.unit_price
        price_ok = price_variance_pct <= tolerance.price_pct

        # Quantity check
        qty_variance_pct = abs(inv_line.quantity - po_line.quantity) / po_line.quantity
        qty_ok = qty_variance_pct <= tolerance.qty_pct

        if price_ok and qty_ok:
            status = MATCHED
        elif price_variance_pct > tolerance.price_pct and qty_ok:
            status = MISMATCH
            exception_type = PRICE_MISMATCH
        elif not qty_ok and price_ok:
            status = MISMATCH
            exception_type = QTY_MISMATCH
        else:
            status = MISMATCH
            exception_type = PRICE_MISMATCH  # dominant

        results.append(LineMatchResult(
            status=status,
            exception_type=exception_type if status != MATCHED else None,
            price_variance=inv_line.unit_price - po_line.unit_price,
            price_variance_pct=price_variance_pct,
            qty_variance=inv_line.quantity - po_line.quantity,
            qty_variance_pct=qty_variance_pct,
            tolerance_used=tolerance,
            rule_version_id=config.rule_version_id
        ))

    overall_status = aggregate_status(results)
    log_to_audit(invoice, results, config.rule_version_id)
    return MatchResult(overall_status=overall_status, line_results=results)
```

### 3-Way Match Extension

```python
def run_3way_match(invoice: Invoice, po: PurchaseOrder, grns: list[GRN], config: MatchConfig):
    # Step 1: Aggregate received quantities across all GRNs for each PO line
    received_qty_by_line = {}
    for grn in grns:
        for grn_line in grn.line_items:
            received_qty_by_line[grn_line.po_line_item_id] = (
                received_qty_by_line.get(grn_line.po_line_item_id, 0) + grn_line.quantity_received
            )

    results = []
    for inv_line in invoice.line_items:
        po_line = find_po_line(po, inv_line)
        if po_line is None:
            results.append(LineMatchResult(status=MISMATCH, exception_type=PO_NOT_FOUND))
            continue

        received_qty = received_qty_by_line.get(po_line.id, 0)
        if received_qty == 0:
            results.append(LineMatchResult(status=MISMATCH, exception_type=GRN_NOT_FOUND))
            continue

        # Invoice quantity must not exceed received quantity
        if inv_line.quantity > received_qty * (1 + tolerance.qty_pct):
            results.append(LineMatchResult(
                status=MISMATCH,
                exception_type=QTY_MISMATCH,
                description=f"Invoice qty {inv_line.quantity} > GRN qty {received_qty}"
            ))
            continue

        # Then do standard 2-way price check
        # ...
```

---

## 2. Tolerance Configuration

Tolerance is resolved in priority order:
1. Vendor + Category specific
2. Vendor-only
3. Category-only
4. Default (global)

### Tolerance Config Schema (stored in `rule_versions.rules_json`)

```json
{
  "tolerances": [
    {
      "vendor_id": "v-uuid-acme",
      "category": "materials",
      "price_tolerance_pct": 1.5,
      "qty_tolerance_pct": 2.0,
      "price_tolerance_abs": 500.00
    },
    {
      "vendor_id": "v-uuid-acme",
      "category": null,
      "price_tolerance_pct": 3.0,
      "qty_tolerance_pct": 3.0,
      "price_tolerance_abs": null
    },
    {
      "vendor_id": null,
      "category": "services",
      "price_tolerance_pct": 5.0,
      "qty_tolerance_pct": 0.0,
      "price_tolerance_abs": null
    },
    {
      "vendor_id": null,
      "category": null,
      "price_tolerance_pct": 2.0,
      "qty_tolerance_pct": 2.0,
      "price_tolerance_abs": 100.00
    }
  ],
  "auto_approve_threshold": 5000.00,
  "duplicate_window_days": 7
}
```

### Tolerance Resolution Function

```python
def get_tolerance(config: dict, vendor_id: str, category: str) -> Tolerance:
    candidates = config["tolerances"]
    # Priority: exact match first, then fallback
    for priority_fn in [
        lambda t: t["vendor_id"] == vendor_id and t["category"] == category,
        lambda t: t["vendor_id"] == vendor_id and t["category"] is None,
        lambda t: t["vendor_id"] is None and t["category"] == category,
        lambda t: t["vendor_id"] is None and t["category"] is None,
    ]:
        match = next((t for t in candidates if priority_fn(t)), None)
        if match:
            return Tolerance(**match)
    raise ConfigError("No default tolerance configured")
```

---

## 3. Duplicate Invoice Detection

**Strategy**: multi-signal hash comparison with configurable time window.

```python
def detect_duplicate(new_invoice: Invoice, db: Session, window_days: int = 7) -> Invoice | None:
    candidates = db.query(Invoice).filter(
        Invoice.vendor_id == new_invoice.vendor_id,
        Invoice.deleted_at.is_(None),
        Invoice.id != new_invoice.id,
        Invoice.created_at >= now() - timedelta(days=window_days)
    ).all()

    for candidate in candidates:
        # Signal 1: Same invoice number (strongest signal)
        if candidate.invoice_number and candidate.invoice_number == new_invoice.invoice_number:
            return candidate

        # Signal 2: Same amount + same invoice date
        if (candidate.total_amount == new_invoice.total_amount and
                candidate.invoice_date == new_invoice.invoice_date):
            return candidate

        # Signal 3: Fuzzy amount match (within 0.1%) + same date range
        if (candidate.invoice_date == new_invoice.invoice_date and
                abs(candidate.total_amount - new_invoice.total_amount) / max(candidate.total_amount, 0.01) < 0.001):
            return candidate

    return None
```

---

## 4. Exception Taxonomy

| Exception Type | Trigger Condition | Default Severity | Auto-Resolvable? |
|---------------|-------------------|------------------|------------------|
| `PRICE_MISMATCH` | Unit price variance > tolerance | medium | No — needs human |
| `QTY_MISMATCH` | Quantity variance > tolerance | medium | No |
| `PO_NOT_FOUND` | No PO number on invoice / no matching PO | high | No |
| `GRN_NOT_FOUND` | 3-way: no GRN for PO line | medium | No |
| `DUPLICATE_INVOICE` | Matches existing invoice by signals | critical | No — mandatory review |
| `VENDOR_DATA_MISMATCH` | Bank account / tax ID differs from master | critical | No — fraud risk |
| `TAX_DISCREPANCY` | Tax amount ≠ expected (rate × subtotal) | low | Yes if diff < $5 |
| `FREIGHT_DISCREPANCY` | Freight on invoice but PO says 0 | low | No |
| `UNEXPECTED_CHARGE` | Line item not in PO | medium | No |
| `OCR_LOW_CONFIDENCE` | Extraction confidence < threshold | medium | No — needs human |
| `MISSING_REQUIRED_FIELD` | invoice_number / total_amount missing | high | No |
| `SLA_BREACH` | Invoice not approved by due date - buffer | high | No |
| `OTHER` | Manually flagged | medium | No |

### Auto-Resolvable Exceptions

Some low-severity exceptions can be auto-resolved by the system (with audit log):

```python
AUTO_RESOLVE_RULES = [
    {
        "exception_type": "TAX_DISCREPANCY",
        "condition": lambda exc: abs(exc.metadata.get("tax_diff", 999)) < 5.00,
        "resolution": "Auto-resolved: Tax rounding difference < $5.00 (within policy)"
    }
]
```

---

## 5. Approval Routing Logic

```python
def route_approval(invoice: Invoice, db: Session) -> list[ApprovalTask]:
    matrix = db.query(ApprovalMatrix).filter(
        ApprovalMatrix.is_active == True,
        ApprovalMatrix.amount_min <= invoice.total_amount,
        or_(ApprovalMatrix.amount_max.is_(None),
            ApprovalMatrix.amount_max >= invoice.total_amount),
        or_(ApprovalMatrix.cost_center.is_(None),
            ApprovalMatrix.cost_center == invoice.cost_center),
    ).order_by(ApprovalMatrix.level).all()

    tasks = []
    for rule in matrix:
        approver = (
            rule.approver_id  # specific user override
            or find_approver_by_role(rule.approver_role, db)
        )
        if approver is None:
            raise RoutingError(f"No approver found for role {rule.approver_role}")
        tasks.append(ApprovalTask(
            invoice_id=invoice.id,
            approver_id=approver.id,
            level=rule.level,
            due_at=now() + timedelta(hours=48)
        ))
    return tasks
```

### Authorization Matrix Example

| Amount Range | Cost Center | Approver Role | Level |
|---|---|---|---|
| $0 – $10,000 | Any | AP_ANALYST (auto) | 1 |
| $10,001 – $50,000 | Any | DEPT_MANAGER | 1 |
| $50,001 – $200,000 | Any | FINANCE_VP | 1 |
| $200,001+ | Any | CFO | 1 |
| Any | CAPEX | CFO | 2 (additional) |

---

## 6. Rule Version Flow

```
DRAFT → IN_REVIEW → PUBLISHED → ARCHIVED
         ↑               ↑
    [Admin submits]  [Admin approves review]

Only one version can be PUBLISHED at a time.
Publishing a new version auto-archives the previous one.
All match_results reference the rule_version_id used.
```

```python
def publish_rule_version(version_id: UUID, admin: User, db: Session):
    version = db.get(RuleVersion, version_id)
    assert version.status == "in_review", "Can only publish in_review versions"

    # Archive current published
    current = db.query(RuleVersion).filter_by(status="published").first()
    if current:
        current.status = "archived"

    version.status = "published"
    version.published_at = now()
    version.published_by = admin.id
    db.commit()

    log_audit("rule_version", version_id, admin, "published",
              old_value={"status": "in_review"}, new_value={"status": "published"})
```
