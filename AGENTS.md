# Project continuity

Read `PROJECT_HANDOFF.md` before changing this project. It is the maintained handoff for the owner and future AI/developers, not a substitute for reading current code.

Current owner decision (2026-11-17): continue improving the app in development and on GitHub without buying hosting or allocating a hosting budget. Permanent hosting and live-domain activation are deferred, not blockers for feature development. Do not create paid services or real Google connections as part of this development phase.

The owner subsequently authorized publication at `https://drgerami-md.ir/clinic` and explicitly chose a design preview with synthetic data. Only the read-only export in `deploy/preview/` is authorized there for this stage: no live patient API, password collection, uploads or real records. Keep the native Django application and its `/dash/` authentication intact. Do not silently replace this preview with an active clinical system.

At the end of every meaningful stage, update the same `PROJECT_HANDOFF.md` with actual changes, decisions, commands/results, remaining limitations and next steps. Commit it together with related code. The user explicitly requests persistence on GitHub; push stage commits to the established remote branch when authorized access works. Never force push or overwrite concurrent remote changes. Record failures honestly. A local commit is not a remote push or live deployment.

Never commit `.data`, `.env`, `.local-secret`, patient records, OAuth tokens, credentials, the private CV, or real-data screenshots. Do not include secrets in the handoff. Use isolated test accounts/data. Use existing cloud checkout; no extra worktrees unless requested.

Keep server-side role checks: secretary has no clinical access. The owner now explicitly authorizes secretary appointment/calendar scheduling and availability configuration; OAuth connection/disconnection stays manager-only. Patient booking, when enabled, must be scoped to an explicitly verified linked patient account, never a guessed national ID. Do not weaken CSRF, TLS, private-file controls or authentication for UI/testing convenience. Preserve the existing root site; all product routes are under `/dash/`.

For code changes run relevant existing tests and record real results. Run the whole Django suite before claiming a feature complete, and browser checks for visual/user-flow changes. Use `README.md` and `docs/VALIDATION.md` for commands and deployment conditions.
