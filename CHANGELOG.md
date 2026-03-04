# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-03-04

### Added

**Core Pipeline**
- Invoice ingestion via PDF/image upload and Email IMAP polling
- Tesseract OCR with LLM-assisted field correction
- 2-way match engine (Invoice vs PO with configurable tolerances)
- 3-way match engine (+ Goods Receipt Note with multi-GRN aggregation)
- 4-way match engine (+ Inspection Report for quality workflows)
- Typed exception queue with auto-routing rules
- Multi-level approval workflow with email-token approvals (HMAC-signed)
- Approval escalation with configurable SLA

**Intelligence Layer**
- GL account ML classifier (TF-IDF + Logistic Regression, weekly auto-retrain)
- Fraud scoring (rule-based: duplicate vendor/bank, round-amount, velocity checks)
- Rule self-optimization recommendations from override history
- LLM root-cause analysis for exception rate spikes
- Policy PDF parsing (LLM extracts rules, human reviews, publish)
- Recurring invoice detection and duplicate detection

**Analytics & Admin**
- KPI dashboard (touchless rate, cycle time, exception rate, GL accuracy, fraud catch rate)
- Cash flow forecast and audit trail export (CSV)
- RBAC with 5 roles: AP_CLERK, AP_ANALYST, APPROVER, ADMIN, AUDITOR
- Multi-entity support (subsidiaries with entity selector)
- ERP CSV sync (SAP PO import, Oracle GRN import)
- Multi-currency with daily ECB FX rates
- Vendor portal for status checks, disputes, and invoice submissions
- Vendor risk scoring (weekly automated assessment)
- GDPR data retention automation
- Slack/Teams webhook notifications
- In-app notification center

**LLM Providers**
- 4 pluggable backends: Anthropic API, Claude Code CLI, Ollama (local), None (disabled)
- Per-use-case provider overrides via environment variables

**Infrastructure**
- Docker Compose for local development (one-command `make demo`)
- Production stack with Nginx reverse proxy and Gunicorn
- CI pipeline (GitHub Actions)
