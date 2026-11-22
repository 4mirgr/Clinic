# Validation — 2026-11-15

Development code and isolated checks are complete for the Jalali scheduling increment. The domain is not deployed and the real Google account is not connected.

## Final source checks

- **81/81 Django tests on SQLite and 81/81 on temporary PostgreSQL 17**. The local PostgreSQL transport does not verify a production Supabase endpoint or its TLS.
- **4/4 Chromium acceptance flows**: manager records/advice/print/themes/mobile and secretary limits; OAuth navigation; staff Jalali selection and same-event editing; canonical patient signup/profile and own-slot booking on 390px mobile.
- Browser tests use actual collected CSS/local font and app JavaScript. OAuth navigation uses a closed loopback proxy for external hosts and verifies the outgoing authorization request, not consent. Other Google responses/events are controlled synthetic fixtures. No real Google credentials or appointments were used.
- **3/3 Node Cloudflare proxy contract tests**. No real Cloudflare deployment.
- No migration drift; pip check and diff whitespace check pass. Runtime dependency audit reports no known vulnerabilities at execution time. Dependencies are pinned, without hash-lock.
- Docker image rebuilt with verified TLS and the environment CA passed as an optional build secret. Gunicorn smoke passes with non-root process/read-only filesystem, temporary data, full migrations, actual HTTP CSRF login, private cache headers and static CSS. Temporary containers/data are removed.
- Existing production configuration has two intentional HSTS warnings for includeSubdomains/preload; unknown other domain projects must be checked before enabling them. They were not hidden.

## Reviewed boundaries and regressions

- Manager/secretary scheduling gate is distinct from clinical access. Patients see/book only their own linked record; foreign patient POST, staff routes and event exclusions are denied. Session revocation is rechecked in the reservation transaction. Website admin status grants no clinical permission.
- Jalali conversion/leap boundaries, Persian/Arabic digits, Tehran today, date overrides, selected-slot revalidation and repeated request keys have regressions.
- Google identity is verified using signed ID token, expected email, verified-email flag, audience/issuer and nonce. Same verified identity reconnect preserves event generation.
- Same-event PATCH, ambiguous-response recovery, preservation of both old/new holds, conflicts and cancellation are tested. A failed cancellation of an uncertain edit retains both holds until deletion is acknowledged. Distinct simultaneous PostgreSQL booking/edit transactions have not been specifically exercised; shared-row locking was independently reviewed.
- Final independent read-only review found no Critical/Important issues. Its Minor conflict message was corrected after a failing regression: an unreserved conflict no longer claims a held time.
- Patient browser navigation initially raced page loading; explicit load/navigation waiting fixes the test harness. No product access control or CSRF protection was bypassed.
- Earlier independent-review fixes remain covered: Unicode login throttling, Persian/Arabic advice search, OAuth CSP navigation, conflict cancellation uniqueness, pagination and out-of-prefix favicon/CSRF interference.

## Still unverified or unfinished

- Domain/real HTTPS proxy/cache/TLS, production hosting/PostgreSQL/private storage/accounts, secure backups/restore and malware scanning.
- Actual Google consent, refresh, real event collision/edit/cancellation, host retry job, and Google-to-panel manual-edit reconciliation. Only app-owned events can be edited; arbitrary existing personal events are not imported.
- MFA, device sessions, patient messaging, WhatsApp/Telegram, DICOM viewer and advice assignment/version history.
- Original Drive template and local original logo files could not be fetched here. Current artwork is generated decorative art with provenance, not a faithful template or original logo installation.

See PROJECT_HANDOFF.md for stage history/commit and push evidence, README.md for startup and docs/GOOGLE_CALENDAR.md for the exact OAuth callback. Cloud environment setup/start instructions are saved in a draft; that does not publish/apply the environment or deploy the application.

## Education library / packet update (2026-11-17)

Original site logo is now installed with provenance in `static/clinic/brand/PROVENANCE.md`; the older logo-unavailable note above describes the earlier stage. Combined advice assignment, immutable ordered snapshots, source metadata and an explicitly published patient summary are now implemented. Full library revision history, production hosting, MFA and actual patient activation remain separate work.

Stage 8 evidence: 106/106 SQLite; 104/106 PostgreSQL 17 with two intentional SQLite-only skips; six native Chromium workflows; three proxy and two preview Node tests. Packet race covered on both databases. Synthetic five-page WeasyPrint PDF has only embedded Vazirmatn fonts, repeated branding and a raster-decoded final QR. Chromium public-preview PDF repeats the brand on every page with table header/footer space reserved and wrapped long bullets; PDF coordinate/font regressions pass. Final Docker build and non-root/read-only temporary-container PDF smoke pass. This is local verification, not a claim that remote CI or the native clinical service is deployed.

Stage 9: 107/107 SQLite, 3+2 Node, migration drift and pip check pass. The preview test now clicks the actual Print/PDF control and verifies `window.print` is reached (the former main.images error was reproduced). Patient-entry and final-output metadata regressions pass; sources remain in review and stored snapshots. Five-page synthetic PDF regenerated and raster QR/font/branding checks pass. Gray gradients and raised topic headings were visually checked in both PDF engines. See PROJECT_HANDOFF.md for the native browser retry and exact live revision evidence.

## Physician/patient workspace and shared login (2026-11-19)

- **118/118 SQLite** Django tests; **116 passed and 2 intentional SQLite-only skips on isolated PostgreSQL 17** (118 discovered). Migration drift and `pip check` pass; **3 proxy + 2 read-only preview Node contracts** pass.
- **7/7 native Chromium flows**, including actual shared password login, chosen-username signup, distinct doctor/patient views, structured online visit, patient intake save and physician readback, mobile widths and official popup isolation. External prescribing content is a stub in this test, not a live-provider login/API check.
- Google OIDC is tested with controlled provider responses: verified subject reuse, patient-only creation, rejected nonce/state/expiry/unverified email, explicit existing-account linking, CSRF and revoked-linking session denial. No actual Google consent, credentials or production HTTPS cookie/proxy test was performed. The button stays disabled without sign-in keys.
- Browser checks now use `scripts/check_browser.py` (also Makefile/CI). Django LiveServer was sharing a single in-memory SQLite connection across parallel HTTP threads, causing intermittent invalid session reads. A ten-cycle password-login/intake-save stress test passed with disposable file-backed SQLite connections; all seven native flows then passed. No application authentication or CSRF checks were weakened. PostgreSQL uses its ordinary isolated test database.
- Independent read-only review found three P2 display issues: patient settings return link, diastolic-only BP and hidden prescription notes. All fixed. Added preservation of pre-upgrade reported medical text before its first changed write, with a regression. Immutable history is ordinary application-save enforcement, not an operator/SQL-proof database claim.
- Isolated synthetic preview rebuilt: **73 pages / 93 allowlisted routes**. Account and medical controls remain disabled and native account/intake scripts are removed. Local Worker Chromium verifies desktop/mobile, search/navigation, disabled forms, Print/PDF click and no failed assets/JS errors/API writes. The five-page synthetic WeasyPrint PDF still embeds only Vazirmatn, preserves one logo watermark per page, repeats header without footer, excludes patient-facing editorial sources and has a raster-decoded final QR.
- No private backend, paid service, Supabase project, real medical records or credential collection was enabled. Main website CMS changes were not deployed by this task. Live Google/website SSO, real prescribing API, persistent private hosting/storage, MFA and deployment/restore requirements remain unfinished.

## Audit, easier intake and communications — 2026-11-22

After integrating concurrent origin/main shared-identity changes: **154/154 SQLite; 152 passed / 2 intentional SQLite-only skips on PostgreSQL17**. Seven native Chromium flows pass including bilingual shortcuts, unsaved-text preservation, partial multi-upload retry and patient preferences. Three proxy and four preview/account-entry Node contracts, migration drift and pip check pass. Runtime pip-audit reports no known vulnerabilities. Synthetic five-page PDF/font/QR regressions pass. Telegram6 additional tests and independent shared-mode secret-webhook reproduction perform no actual provider calls. No real sender, scheduler or delivery was activated. See [AUDIT_2026-11-22.md](AUDIT_2026-11-22.md) for findings and boundaries, and [COMMUNICATIONS.md](COMMUNICATIONS.md) for activation.

## Calendar access and remaining-work completion — 2026-11-22

Final code: **230/230 SQLite**, **228 passed + two intentional SQLite-only skips on PostgreSQL17**, **7 native Chromium workflows**, **3 proxy + 4 preview/identity Node contracts**, migration drift and pip check pass. Native browser now visits advice edit→revision history→revision detail; existing Calendar OAuth navigation/working-hours flows pass. Public Worker Chromium verifies honest preview Calendar diagnostics and all new history links without API writes. Export is **124 synthetic HTML pages / 145 allowlisted routes**. PDF remains five pages with embedded Vazirmatn, final decoded QR and original header/watermark without footer. Isolated encrypted SQLite/document backup drill passes bytes/link/integrity and wrong-key/tamper rejection; it is not a production PostgreSQL/Django restore.

Independent review reproduced and fixed stale updater attribution in Advice partial saves and documented sparse Google deletion tombstones; exact stored ownership remains required, and untrusted events never alter local state. FIFO token-file rejection cannot block waiting for a writer. Reconciliation fairness, stale connection/snapshot checks, local current/previous hold collisions, no personal-event import, no Google writes and ambiguous provider results have regressions.

Live connector access was reauthorized to **dr.gerami.md@gmail.com**. Primary-calendar owner access and FreeBusy succeeded. With the owner's separate explicit create/edit/delete instruction, a private one-minute technical event was created, renamed, read back and deleted; no external guests/default reminders. This verifies the chat connector, not the native application's OAuth client/deployment. Live shared Supabase public settings show Google provider off, email on; no provider config was changed. Owner's existing Google Cloud Client is unverified. No private runtime, worker job, real patient write, billing or sender was enabled. See GOOGLE_SETUP_FA.md and REMAINING_WORK_FA.md for exact required owner steps.
