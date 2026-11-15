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
