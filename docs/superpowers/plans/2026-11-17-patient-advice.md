# Patient advice snapshots implementation plan

> Execute inline in the existing checkout under the owner's authorization to develop and push stages. Preserve concurrent work; no new worktree or paid hosting.

**Goal:** Record approved advice as a stable, printable part of each patient's history.
**Architecture:** Additive Django model/migration; manager-only selection and confirmation; shared private print route scoped to manager or linked portal patient.
**Tech Stack:** Existing Django, SQLite/PostgreSQL, templates and Chromium tests.
**Spec:** docs/superpowers/specs/2026-11-17-patient-advice-design.md

## Constraints and review focus
- Preserve secretary isolation, patient session generation and CSRF; no external notifications or real data.
- Check stale previews, withdrawn approval, duplicate POSTs and cross-patient UUID/token use.
- Ensure old snapshots survive all library edits and unauthorized users cannot enumerate them.
- Keep long/multiline text escaped, mobile layout usable and print light in dark mode.
- Do not imply hosting or CI success from a local commit.

## Task 1 — Snapshot workflow
Files: `clinic/advice_views.py`, `clinic/models.py`, new migration, `config/urls.py`, `clinic/views.py`, `clinic/portal_api.py`, advice templates, tests.
- [x] Write HTTP tests for snapshot stability, stale/draft rejection, idempotency, role isolation, patient ownership/generation, escaping and history pagination; observe failures.
- [x] Add `AdviceDelivery` and transactional confirmation with source revision and UUID request key.
- [x] Add searchable selection, full preview, paginated history and private printable snapshot with QR.
- [x] Add browser coverage for doctor confirmation, library edit, unchanged patient snapshot, mobile and PDF.
- [x] Run full Django suite, migration drift, Node checks and browser checks; review independently and fix material findings.

## Task 2 — No-host development continuity
Files: `README.md`, `Makefile`, `docs/previews/`, `PROJECT_HANDOFF.md`.
- [x] Document development without hosting, commands and the new workflow.
- [x] Preserve selected synthetic browser screenshots in `docs/previews/` with clear labeling; no app data, secrets, hosted runtime or artifact storage.
- [x] Record actual results, commit/push without force, verify remote HEAD and report what remains untested.

## Verification ledger
- Initial HTTP tests: 9 failures for missing feature routes, then green.
- Secretary with linked PortalAccount: disclosure regression reproduced, then green.
- Independent reviewer: one P2 SQLite concurrent-write finding; real two-thread regression RED, bounded transaction retry GREEN. No other material findings.
- Final SQLite: 93 passed. PostgreSQL 17 temporary: 91 passed, 2 SQLite-specific skipped. Browser: 5 passed. Node: 3 passed.
- make setup, migration drift, pip check and diff check succeeded. Remote CI is unconfirmed (API network proxy 403).
- Integration: commit/push to established main, verify remote SHA; no hosting or domain activation.
