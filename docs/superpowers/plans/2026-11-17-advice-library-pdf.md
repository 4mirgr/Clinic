# Advice library and patient PDF implementation plan

> Execute inline in the existing checkout. Owner authorized development, stage pushes and synthetic preview updates; no repeated hosting approval.

**Goal:** Source-backed structured bilingual-searchable handouts, stable multi-handout patient packets, branded Vazirmatn PDF and authenticated summary QR.
**Architecture:** Extend Advice metadata and snapshot grouping; add explicitly shared PatientSummary. Render local PDFs and keep public preview synthetic/read-only.
**Spec:** docs/superpowers/specs/2026-11-17-advice-library-pdf-design.md

## Task 1 — Source-backed library
- [x] Read and record authoritative sources; author 24 original Persian drafts in 12 specialties with bilingual tags.
- [x] Write failing tests for normalized search and idempotent non-destructive import, implement metadata/command/UI and migrate.

## Task 2 — Packet and protected summary
- [x] Write failing tests for ordered snapshots, signed revisions, repeat submits, roles, patient ownership/session generation and explicit summary sharing.
- [x] Implement grouped snapshots, full review/confirmation, summary editing and protected reader.

## Task 3 — Print and PDF
- [x] Render structured headings/bullets with real site logo, local full Vazirmatn, repeated branded header/footer, large patient name and final protected-summary QR.
- [x] Verify actual multi-page PDF, embedded fonts, readable RTL text, name/order/branding and no outbound asset fetches. Update runtime dependencies/Docker as needed.

## Task 4 — Read-only preview and delivery
- [x] Demonstrate category/tag search, selection and combined sample printing; all clinical writes remain blocked and all records synthetic.
- [x] Run full Django/browser/Node, PostgreSQL and relevant PDF/build checks; independent review, record findings/fixes.
- [ ] Update handoff, commit/push, publish synthetic preview with pinned SHA and verify live links.
