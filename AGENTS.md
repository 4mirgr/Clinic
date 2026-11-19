# Project continuity

Latest 2026-11-19 continuation: owner keeps Clinic synthetic/read-only and without paid hosting, but explicitly requests shared website login and role-aware doctor/patient entry at `/clinic/` and `/clinic/portal/`. The optional preview identity wrapper may verify the website session and gate HTML; it must not activate medical writes, uploads, native hosting or patient linking. Native `SHARED_AUTH_ENABLED` remains off until private hosting is authorized and ready.

Read `PROJECT_HANDOFF.md` before changing this project. It is the maintained handoff for the owner and future AI/developers, not a substitute for reading current code.

Current owner decision (2026-11-17): continue improving the app in development and on GitHub without buying hosting or allocating a hosting budget. Permanent hosting and live-domain activation are deferred, not blockers for feature development. Do not create paid services or real Google connections as part of this development phase.

The owner subsequently authorized publication at `https://drgerami-md.ir/clinic` and explicitly chose a design preview with synthetic data. Only the read-only export in `deploy/preview/` is authorized there for this stage: no live patient API, password collection, uploads or real records. Keep the native Django application and its `/dash/` authentication intact. Do not silently replace this preview with an active clinical system.

At the end of every meaningful stage, update the same `PROJECT_HANDOFF.md` with actual changes, decisions, commands/results, remaining limitations and next steps. Commit it together with related code. The user explicitly requests persistence on GitHub; push stage commits to the established remote branch when authorized access works. Never force push or overwrite concurrent remote changes. Record failures honestly. A local commit is not a remote push or live deployment.

Never commit `.data`, `.env`, `.local-secret`, patient records, OAuth tokens, credentials, the private CV, or real-data screenshots. Do not include secrets in the handoff. Use isolated test accounts/data. Use existing cloud checkout; no extra worktrees unless requested.

Latest owner decision (2026-11-19, website task): use the existing IntMed Supabase Auth project `upwbktvnybsjugdegjji`, without a third project. The verified existing `Dr.Gerami.MD@gmail.com` identity is website/Clinic admin; other identities default to user. Keep educational entitlements/approval separate from app roles and all medical records. Google sign-in is through this common Auth, independent from Calendar OAuth. The optional `SHARED_AUTH_ENABLED` bridge stays OFF until native private hosting and same-origin `/dash/` ingress are ready. Do not auto-link any existing clinical account or patient by email/national ID.

Keep server-side role checks. In the owner's new shared mode, secretary can open and manage the patient panel; finer secretary restrictions are explicitly deferred for the owner to specify. Only the seven explicit patient CRUD/document routes gain this capability; physician approval, prescription workspace, account administration and Calendar OAuth remain manager-only. In existing standalone development mode, preserve the previous scheduling-only secretary scope. Patient booking must be scoped to an explicitly verified linked patient account. Do not weaken CSRF, TLS, private-file controls or authentication for UI/testing convenience. Preserve the root site; native product routes remain under `/dash/`.

For code changes run relevant existing tests and record real results. Run the whole Django suite before claiming a feature complete, and browser checks for visual/user-flow changes. Use `README.md` and `docs/VALIDATION.md` for commands and deployment conditions.
