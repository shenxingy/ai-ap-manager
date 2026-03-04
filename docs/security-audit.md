# Dependency Security Audit Report

**Date**: 2026-03-03
**Scope**: Backend (Python) and Frontend (Node.js)
**Tools**: pip-audit 2.10.0, npm audit

---

## Backend (pip-audit)

**Total Vulnerabilities Found**: 14 across 7 packages

### Detailed Findings

| Package | Version | Vulnerability | Severity | Fix Version | Notes |
|---------|---------|---|----------|---|---|
| python-multipart | 0.0.12 | CVE-2024-53981 | HIGH | 0.0.18 | File upload handling |
| python-multipart | 0.0.12 | CVE-2026-24486 | HIGH | 0.0.22 | File upload handling |
| python-jose | 3.3.0 | PYSEC-2024-233 (x2) | HIGH | 3.4.0 | JWT/auth token handling |
| python-jose | 3.3.0 | PYSEC-2024-232 (x2) | HIGH | 3.4.0 | JWT/auth token handling |
| scikit-learn | 1.4.2 | PYSEC-2024-110 (x2) | MEDIUM | 1.5.0 | ML/data processing |
| Pillow | 11.0.0 | CVE-2026-25990 | MEDIUM | 12.1.1 | Image processing (OCR) |
| pdfminer-six | 20231228 | CVE-2025-64512 | HIGH | 20251107 | PDF extraction |
| pdfminer-six | 20231228 | CVE-2025-70559 | HIGH | 20251230 | PDF extraction |
| starlette | 0.38.6 | CVE-2024-47874 | HIGH | 0.40.0 | HTTP request handling |
| starlette | 0.38.6 | CVE-2025-54121 | HIGH | 0.47.2 | HTTP request handling |
| ecdsa | 0.19.1 | CVE-2024-23342 | MEDIUM | (latest) | Cryptography utility |

### Critical Packages Requiring Immediate Update

**1. python-multipart (0.0.12 → 0.0.22)**
   - Current: `0.0.12` in `backend/requirements.txt` line 3
   - Impact: File upload vulnerability affecting invoice ingestion pipeline
   - Action: Update to `0.0.22` (or at minimum `0.0.18`)
   - Risk: Used directly by FastAPI for multipart form data parsing

**2. python-jose (3.3.0 → 3.4.0)**
   - Current: `3.3.0` in `backend/requirements.txt` line 19
   - Impact: JWT token generation/validation for auth & approval workflows
   - Action: Update to `3.4.0`
   - Risk: Core auth mechanism; token vulnerabilities could bypass access control

**3. starlette (0.38.6 → 0.47.2)**
   - Current: FastAPI 0.115.0 depends on starlette
   - Impact: HTTP request parsing DoS; possible deserialization attacks
   - Action: Update FastAPI and/or starlette to fix indirect dependency
   - Risk: All API endpoints affected; potential request smuggling

**4. pdfminer-six (20231228 → 20251230)**
   - Current: `20231228` in `backend/requirements.txt` line 40
   - Impact: PDF extraction (used for invoice document handling)
   - Action: Update to `20251230`
   - Risk: Malicious PDFs could trigger crashes or code execution

### Lower Priority (Update in Next Release Cycle)

- **scikit-learn**: 1.4.2 → 1.5.0 (MEDIUM, used in fraud scoring)
- **Pillow**: 11.0.0 → 12.1.1 (MEDIUM, used for OCR preprocessing)
- **ecdsa**: 0.19.1 → latest (MEDIUM, indirect crypto dependency)

---

## Frontend (npm audit)

**Total Vulnerabilities Found**: 4 high severity across 2 packages

### Detailed Findings

| Package | Severity | CVE/Advisory | Fix | Notes |
|---------|----------|---|---|---|
| glob | HIGH | GHSA-5j98-mcp5-4vw2 | Update eslint-config-next | Command injection in CLI |
| next | HIGH | GHSA-9g9p-9gw9-jx7f | Update to 16.1.6+ | Image Optimizer DoS |
| next | HIGH | GHSA-h25m-26qc-wcjf | Update to 16.1.6+ | RSC deserialization DoS |

### Critical Packages Requiring Immediate Update

**1. next 14.2.35 → 16.1.6 (or latest 15.x)**
   - Current: `14.2.35` in `frontend/package.json` line 24
   - Impact: Two HIGH severity vulnerabilities in Next.js core
     - DoS via Image Optimizer misconfiguration
     - DoS via React Server Component deserialization
   - Action: Run `npm install next@latest` to upgrade to 16.1.6+
   - Risk: Production deployments vulnerable to request-based DoS attacks

**2. glob (transitive via @next/eslint-plugin-next)**
   - Current: Pulled in indirectly; pin is in eslint-config-next
   - Impact: Command injection in ESLint glob CLI
   - Action: Upgrade eslint-config-next to 16.1.6+ (comes with glob fix)
   - Risk: Affects dev build pipeline; low production impact but build-time vulnerability

### Update Path

```bash
cd frontend
npm install next@latest eslint-config-next@latest
npm audit fix  # for any remaining transitive deps
```

---

## Summary

### Vulnerability Counts

| Severity | Backend | Frontend | Total |
|----------|---------|----------|-------|
| CRITICAL | 0 | 0 | 0 |
| HIGH | 10 | 2 | **12** |
| MEDIUM | 4 | 0 | **4** |
| LOW | 0 | 2 | **2** |

### Recommended Immediate Actions

**URGENT (this sprint)**:
1. Update `backend/requirements.txt`:
   - `python-multipart==0.0.22` (was 0.0.12)
   - `python-jose==3.4.0` (was 3.3.0)
   - `pdfminer-six==20251230` (was 20231228)
2. Update `frontend/package.json`:
   - `next@16.1.6` (was 14.2.35)
3. Test invoice upload, authentication, and PDF processing pipelines after updates

**PLANNED (next release)**:
1. Update scikit-learn to 1.5.0
2. Update Pillow to 12.1.1
3. Update ecdsa to latest
4. Run full regression tests on fraud scoring and OCR features

### Testing Scope After Updates

- **Backend**: Re-run invoice ingestion e2e (upload → OCR → extraction), auth flow, PDF extraction
- **Frontend**: Verify dashboard loads, no Image Optimizer errors, build completes

### Notes

- No `requirements-dev.txt` found; all audit scope covered by `requirements.txt`
- Frontend npm audit reports 4 high severity issues; all resolvable via Next.js major version upgrade
- No CRITICAL vulnerabilities identified
- Worktree isolation note: All findings apply to main repo; commit and merge to main branch to ensure Docker build pulls updated deps

---

**Next Review**: 2026-03-10 (weekly audit cycle)
