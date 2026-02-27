# Plan: AI AP Operations Manager — Initial Architecture

**Date**: 2026-02-26
**Status**: Completed (documentation phase)

## Context

New project: AI-driven Accounts Payable automation platform for manufacturing/supply chain.
Full lifecycle: invoice ingestion → OCR extraction → 2/3-way match → exception handling → approval workflow → payment recommendation → KPI.

## Self-Challenge Notes

**Necessity check**:
- OCR libraries: Tesseract (open source) is good enough for MVP. Don't over-engineer with expensive cloud OCR from day 1.
- Rule engine: Pure Python is fine. No need for a specialized rule engine framework (Drools etc.) — adds complexity for no gain at MVP.
- Workflow engine: Celery (already in stack for OCR) handles job sequencing fine. Temporal is overkill for MVP.
- LLM: Claude claude-sonnet-4-6 is the right choice. Only for extraction + policy parsing — never for decisions.

**Blind spots identified**:
- Vendor fuzzy matching is harder than it looks. Same vendor can appear as "Acme Corp", "ACME CORPORATION", "Acme Corp Ltd". Need fuzzy match from day 1 (not an afterthought).
- Multi-currency was deprioritized to V2 but the data model must support it from day 1 (currency fields on all monetary tables).
- OCR confidence threshold (0.75) is a guess — needs calibration with real invoice samples.
- Rule version caching in Redis: must invalidate cache immediately on publish, not lazily.

**Rollback cost**: Low — MVP is mock data only, no real ERP connection. Failed pivot costs at most 2 weeks of work.

**Simplest approach**: The match engine is ~200 lines of pure Python. Don't abstract prematurely.

## Approach Chosen

**Core architecture**: FastAPI + Celery + Postgres + MinIO + Redis
**LLM**: Claude claude-sonnet-4-6 (extraction + policy parsing only)
**Frontend**: Next.js 14 + shadcn/ui

Key architectural decision: **Deterministic rule engine owns all AP decisions**. LLM is purely a structuring assistant. This is non-negotiable for compliance and auditability.

## File Change Summary

### Documentation created
- `CLAUDE.md` — project briefing, tech stack, commands, conventions
- `GOALS.md` — vision, phase milestones, north star metrics
- `TODO.md` — P0/P1/P2 task breakdown
- `PROGRESS.md` — lessons log (initialized)
- `BRAINSTORM.md` — ideas inbox (4 initial AI-suggested ideas)
- `docs/PRD.md` — user roles, journey, 17 scenarios, MVP/V1/V2 scope
- `docs/ARCHITECTURE.md` — module map, data flow, audit chain design, docker-compose
- `docs/DATABASE.md` — all table schemas with fields, indexes, FK constraints
- `docs/API.md` — all MVP endpoints with request/response JSON examples
- `docs/RULES_ENGINE.md` — match pseudocode, tolerance config, duplicate detection, exception taxonomy, approval routing, rule version flow
- `docs/AI_MODULES.md` — extraction pipeline, policy parsing, self-optimization, root cause analysis, safety guardrails
- `docs/UI_IA.md` — all 13 pages with components, table columns, interactions
- `docs/SECURITY.md` — RBAC matrix, auth design, data masking, audit requirements, API security controls
- `docs/TESTING.md` — 13 unit tests, 9 integration tests, 10 E2E test cases, acceptance metrics
- `docs/MILESTONES.md` — week-by-week tickets with dependency map + demo script

## Verification Steps

1. [ ] Backend team can start with BE-01 through BE-05 independently
2. [ ] Frontend team can start with FE-01 through FE-04 independently
3. [ ] DB schema is complete enough to write all migrations without revisiting docs
4. [ ] Any ambiguous scenario (partial GRN, multi-currency, duplicate detection) has an explicit decision recorded
5. [ ] All 10 E2E tests have clear pass criteria

## Lessons for Next Time

- Create `docs/` directory structure at the start of planning, before writing any code
- The "7 roles" (BA/SA/UI/BE/Integration/OpsAnalyst/ContinuousImprovement) framework is excellent for ensuring nothing is missed in a full-stack AI project
- Separating "LLM role" from "rule engine role" explicitly in the design prevents the classic mistake of letting the AI make irreversible decisions
