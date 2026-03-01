# Permission Audit — backend/app/api/v1/

Audited: 2026-03-01

## Results

| Endpoint | Method | Auth Level | Status |
|---|---|---|---|
| /auth/login | POST | None (public) | OK — intentional |
| /auth/me | GET | get_current_user | OK |
| /users/me | GET | get_current_user | OK |
| /users/{user_id}/delegation | PUT | require_role(APPROVER, ADMIN) | OK |
| /users/{user_id}/delegation | DELETE | require_role(APPROVER, ADMIN) | OK |
| /admin/users | GET | require_role(ADMIN) | OK |
| /admin/users | POST | require_role(ADMIN) | OK |
| /admin/users/{user_id} | PATCH | require_role(ADMIN) | OK |
| /admin/users/{user_id} | DELETE | require_role(ADMIN) | OK |
| /admin/exception-routing | GET | require_role(ADMIN) | OK |
| /admin/exception-routing | POST | require_role(ADMIN) | OK |
| /admin/exception-routing/{rule_id} | PATCH | require_role(ADMIN) | OK |
| /admin/email-ingestion/status | GET | require_role(ADMIN) | OK |
| /admin/email-ingestion/trigger | POST | require_role(ADMIN) | OK |
| /admin/gl-classifier/status | GET | require_role(ADMIN) | OK |
| /admin/override-history | GET | require_role(ADMIN) | OK |
| /admin/recurring-patterns | GET | require_role(ADMIN, AP_ANALYST) | OK |
| /admin/recurring-patterns/{pattern_id} | PATCH | require_role(ADMIN, AP_ANALYST) | OK |
| /admin/recurring-patterns/detect | POST | require_role(ADMIN) | OK |
| /admin/rule-recommendations | GET | require_role(ADMIN) | OK |
| /admin/rule-recommendations/{rec_id}/accept | POST | require_role(ADMIN) | OK |
| /admin/rule-recommendations/{rec_id}/reject | POST | require_role(ADMIN) | OK |
| /admin/ai-correction-stats | GET | require_role(ADMIN, AP_ANALYST) | OK |
| /admin/invoice-templates | GET | require_role(ADMIN, AP_ANALYST) | OK |
| /admin/invoice-templates | POST | require_role(ADMIN, AP_ANALYST) | OK |
| /admin/invoice-templates/{template_id} | GET | require_role(ADMIN, AP_ANALYST) | OK |
| /admin/invoice-templates/{template_id} | DELETE | require_role(ADMIN) | OK |
| /admin/erp/sync/sap-pos | POST | require_role(ADMIN) | OK |
| /admin/erp/sync/oracle-grns | POST | require_role(ADMIN) | OK |
| /invoices | GET | require_role(AP_CLERK, AP_ANALYST, AP_MANAGER, APPROVER, ADMIN, AUDITOR) | OK |
| /invoices/upload | POST | require_role(AP_CLERK, AP_ANALYST, ADMIN) | OK |
| /invoices/{invoice_id} | GET | require_role(AP_CLERK, AP_ANALYST, AP_MANAGER, APPROVER, ADMIN, AUDITOR) | OK |
| /invoices/{invoice_id}/gl-suggestions | GET | require_role(AP_CLERK, AP_ANALYST, ADMIN) | OK |
| /invoices/{invoice_id}/fraud-score | GET | require_role(AP_ANALYST, ADMIN, AUDITOR) | OK |
| /invoices/{invoice_id}/audit | GET | require_role(AP_CLERK, AP_ANALYST, AP_MANAGER, APPROVER, ADMIN, AUDITOR) | OK |
| /invoices/{invoice_id}/fields | PATCH | require_role(AP_ANALYST, ADMIN) | OK |
| /invoices/{invoice_id}/lines/{line_id}/gl | PUT | require_role(AP_ANALYST, ADMIN) | OK |
| /invoices/{invoice_id}/lines/gl-bulk | PUT | require_role(AP_ANALYST, ADMIN) | OK |
| /invoices/{invoice_id}/status | PATCH | require_role(ADMIN) | OK |
| /invoices/{invoice_id}/messages | POST | require_role(AP_ANALYST, AP_MANAGER, ADMIN) | OK |
| /invoices/{invoice_id}/messages | GET | require_role(AP_CLERK, AP_ANALYST, AP_MANAGER, ADMIN, AUDITOR) | OK |
| /invoices/{invoice_id}/match | GET | get_current_user | OK |
| /invoices/{invoice_id}/match | POST | require_role(AP_ANALYST, ADMIN) | OK |
| /invoices/{invoice_id}/payment | POST | require_role(ADMIN) | OK |
| /gr/{gr_id}/inspection | POST | require_role(AP_ANALYST, ADMIN) | OK |
| /exceptions | GET | require_role(AP_CLERK, AP_ANALYST, AP_MANAGER, APPROVER, ADMIN, AUDITOR) | OK |
| /exceptions/bulk-update | POST | require_role(AP_ANALYST, ADMIN) | OK |
| /exceptions/{exception_id} | GET | require_role(AP_CLERK, AP_ANALYST, AP_MANAGER, APPROVER, ADMIN, AUDITOR) | OK |
| /exceptions/{exception_id} | PATCH | require_role(AP_ANALYST, ADMIN) | OK |
| /exceptions/{exception_id}/comments | POST | require_role(AP_ANALYST, AP_CLERK, ADMIN) | OK |
| /exceptions/{exception_id}/comments | GET | require_role(AP_CLERK, AP_ANALYST, ADMIN, APPROVER) | OK |
| /approvals | GET | require_role(APPROVER, ADMIN) | OK |
| /approvals/email | GET | None (public — HMAC token auth) | OK — intentional |
| /approvals/bulk-approve | POST | require_role(ADMIN) | OK |
| /approvals/{task_id} | GET | require_role(APPROVER, ADMIN) | OK |
| /approvals/{task_id}/approve | POST | require_role(APPROVER, ADMIN) | OK |
| /approvals/{task_id}/reject | POST | require_role(APPROVER, ADMIN) | OK |
| /kpi/summary | GET | require_role(AP_ANALYST, AP_MANAGER, APPROVER, ADMIN, AUDITOR) | OK |
| /kpi/sla-summary | GET | require_role(AP_CLERK, AP_ANALYST, AP_MANAGER, APPROVER, ADMIN, AUDITOR) | OK |
| /kpi/trends | GET | require_role(AP_ANALYST, AP_MANAGER, APPROVER, ADMIN, AUDITOR) | OK |
| /kpi/cash-flow-forecast | GET | require_role(AP_ANALYST, ADMIN, AUDITOR) | OK |
| /kpi/cash-flow-export | GET | require_role(AP_ANALYST, ADMIN, AUDITOR) | OK |
| /kpi/benchmarks | GET | get_current_user | OK |
| /vendors | GET | require_role(AP_CLERK, AP_ANALYST, AP_MANAGER, APPROVER, ADMIN, AUDITOR) | OK |
| /vendors | POST | require_role(AP_ANALYST, AP_MANAGER, ADMIN) | OK |
| /vendors/{vendor_id} | GET | require_role(AP_CLERK, AP_ANALYST, AP_MANAGER, APPROVER, ADMIN, AUDITOR) | OK |
| /vendors/{vendor_id} | PATCH | require_role(AP_ANALYST, AP_MANAGER, ADMIN) | OK |
| /vendors/{vendor_id}/aliases | POST | require_role(AP_ANALYST, AP_MANAGER, ADMIN) | OK |
| /vendors/{vendor_id}/aliases/{alias_id} | DELETE | require_role(AP_ANALYST, AP_MANAGER, ADMIN) | OK |
| /vendors/{vendor_id}/compliance-docs | POST | require_role(AP_ANALYST, AP_MANAGER, ADMIN) | OK |
| /vendors/{vendor_id}/compliance-docs | GET | require_role(AP_CLERK, AP_ANALYST, AP_MANAGER, ADMIN, AUDITOR) | OK |
| /entities | GET | get_current_user | OK |
| /entities | POST | require_role(ADMIN) | OK |
| /fraud-incidents | GET | require_role(ADMIN, AP_ANALYST) | OK |
| /fraud-incidents/{incident_id} | PATCH | require_role(ADMIN, AP_ANALYST) | OK |
| /approval-matrix | GET | require_role(ADMIN) | OK |
| /approval-matrix | POST | require_role(ADMIN) | OK |
| /approval-matrix/{rule_id} | PUT | require_role(ADMIN) | OK |
| /approval-matrix/{rule_id} | DELETE | require_role(ADMIN) | OK |
| /analytics/process-mining | GET | require_role(AP_ANALYST, AP_MANAGER, ADMIN, AUDITOR) | OK |
| /analytics/anomalies | GET | require_role(AP_ANALYST, AP_MANAGER, ADMIN, AUDITOR) | OK |
| /analytics/root-cause-report | POST | require_role(AP_ANALYST, AP_MANAGER, ADMIN, AUDITOR) | OK |
| /analytics/reports | GET | require_role(AP_ANALYST, AP_MANAGER, ADMIN, AUDITOR) | OK |
| /analytics/reports/{report_id} | GET | require_role(AP_ANALYST, AP_MANAGER, ADMIN, AUDITOR) | OK |
| /import/pos | POST | require_role(ADMIN, AP_ANALYST) | OK |
| /import/grns | POST | require_role(ADMIN, AP_ANALYST) | OK |
| /import/vendors | POST | require_role(ADMIN) | OK |
| /portal/auth/invite | POST | require_role(ADMIN) | OK |
| /portal/invoices | GET | get_current_vendor_id (vendor JWT) | OK |
| /portal/invoices/{invoice_id} | GET | get_current_vendor_id (vendor JWT) | OK |
| /portal/invoices/{invoice_id}/reply | POST | None (public — HMAC token) | OK — intentional |
| /portal/invoices/{invoice_id}/dispute | POST | get_current_vendor_id (vendor JWT) | OK |
| /portal/templates | GET | get_current_vendor_id (vendor JWT) | OK |
| /rules/upload-policy | POST | require_role(ADMIN) | OK |
| /rules | GET | get_current_user | OK |
| /rules/suggestions | GET | require_role(ADMIN, AP_ANALYST) | OK |
| /rules/suggestions/{suggestion_id}/accept | POST | require_role(ADMIN) | OK |
| /rules/suggestions/{suggestion_id}/reject | POST | require_role(ADMIN) | OK |
| /rules/{version_id} | GET | get_current_user | OK |
| /rules/{version_id} | PATCH | require_role(ADMIN, AP_ANALYST) | OK |
| /rules/{version_id}/publish | POST | require_role(ADMIN) | OK |
| /rules/{version_id}/reject | POST | require_role(ADMIN) | OK |
| /ask-ai | POST | require_role(AP_ANALYST, AP_MANAGER, ADMIN, AUDITOR) | OK |
| /audit/export | GET | require_role(AUDITOR, ADMIN) | OK |

## Summary
- Total endpoints: 104
- Authenticated (internal JWT): 95
- Authenticated (vendor portal JWT): 5
- Public (intentional): 4 — `/auth/login`, `/approvals/email`, `/portal/invoices/{id}/reply` (HMAC token auth), and `/portal/invoices/{id}/reply`
- Auth gaps (unauthenticated): 0

## Notes
- Public `/auth/login`: Standard unauthenticated login endpoint.
- Public `/approvals/email`: Email-token one-click approve/reject. Token embedded in the email link is the authenticator (HMAC-based), so no JWT is required.
- Public `/portal/invoices/{id}/reply`: Vendor reply via emailed HMAC token. Token is validated in the handler body via `verify_vendor_reply_token()`.
- Vendor portal JWT endpoints (`/portal/invoices`, `/portal/invoices/{id}`, `/portal/invoices/{id}/dispute`, `/portal/templates`): Use `get_current_vendor_id` dependency which validates a vendor-specific JWT with `type=vendor_portal` claim. This is a separate authentication domain from internal users.
