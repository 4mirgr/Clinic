# Local validation — 2026-11-15

This is an initial development increment, not a live deployment or approval for real patient data.

## Latest increment: persistent themes, GPT artwork and Calendar (2026-11-15)

- Living handoff `PROJECT_HANDOFF.md` and `AGENTS.md` added; baseline and theme stage committed/pushed to GitHub main. Calendar stage is committed with its updated handoff; remote verification is recorded there.
- Final Django suite: 47/47 on SQLite and 47/47 on temporary PostgreSQL 17. Browser: 2/2; Node proxy: 3/3.
- Browser checks actual CSS/fonts, theme persistence/reload, desktop and 390px mobile, light print while dark mode is active, office-hours form, secretary denial, and configured OAuth authorization navigation. The OAuth browser uses a closed local proxy for external hosts; it verifies CSP/navigation, not real Google consent.
- Official Google OAuth Flow token exchange is doubled at the network boundary in unit tests. Calendar API responses are controlled fixtures. No real account, access/refresh token or patient appointment was used.
- Independent review's three important findings fixed with regressions: Google navigation blocked by form-action policy; conflict cancellation violating a reused slot's uniqueness; inaccessible nearest appointments after 60 entries.
- Additional direct-login CSRF regression fixed: an out-of-prefix favicon error page must not issue a new clinic CSRF cookie. Explicit favicon and prefix-limited theme form remove the interference.
- cryptography upgraded from 47.0.0 to 50.0.2 after vulnerability audit findings. Re-audit: no known vulnerabilities in pinned runtime requirements.
- Docker rebuilt with new dependencies; native migrations/system checks pass. Existing intentional HSTS warnings and production/live-account limitations remain.
- Original GPT-generated artwork is committed under static/clinic/art with provenance; it is decorative, not the owner's original logo. Theme cookie holds only a preference; account theme is persisted server-side.

## Verified on the final source

- Django suite: 26/26 passed on local SQLite.
- Same Django suite: 26/26 passed on a temporary PostgreSQL 17 container. This uses local test transport; it does not verify the real Supabase endpoint/TLS configuration.
- Chromium acceptance: 1/1 passed, including genuine CSS/font loading, real CSRF login, creation of a test patient, visit note, mobile navigation/logout, advice creation, QR image, PDF, and secretary denial.
- Node Cloudflare path-proxy contract tests: 3/3 passed. No real Cloudflare account execution/publication.
- Docker image built with TLS verification preserved; environment proxy CA passed through an optional BuildKit secret.
- Container/Gunicorn smoke passed with a non-root process, read-only filesystem and temporary data volume: migrations, actual HTTP login with CSRF, dashboard/private cache headers and static CSS. Only isolated test credentials/data were used, then the container was removed.
- Migration drift check: no changes detected. Django system check: no issues. pip check: no broken requirements.
- pip-audit of pinned runtime requirements: no known vulnerabilities reported at execution time. Dependencies are pinned but do not yet have a hash-locked installation file.
- Production security configuration check: no errors; two visible HSTS warnings (includeSubdomains/preload) intentionally remain disabled until other domain projects are understood.
- Sample PDF: A4, one page, Persian text extractable. Example is synthetic test text, not medical advice.
- Screenshots inspected for desktop and 390px mobile; no horizontal overflow in tested dashboard/patient view.

## Independent review and corrections

Read-only independent review found a Unicode username throttle bypass. Equivalent NFKC usernames now share the same lock; regression observed failing then passing.

Review also found Arabic/Persian educational search inconsistency. Classified as an important workflow issue and corrected; regression covers letter/digit variants and preserved paragraph breaks.

Real-browser testing independently caught the no-referrer/Origin:null login problem; same-origin referrer policy fixes it while retaining CSRF checks. It also caught the mobile logout visibility issue. The static test harness was corrected to load real collected assets rather than treating unstyled HTML as a visual pass.

## Intentionally not verified / remaining

- Live domain, actual Cloudflare Worker/route/cache/TLS settings, real Supabase credentials/connectivity, production account provisioning.
- Backup restoration, durable/encrypted production storage and malware scanning/quarantine.
- MFA, secure self-service password recovery, device session management.
- Patient portal/messaging, WhatsApp/Telegram, appointments, DICOM viewer, advice assignment/version history.
- Original template and locally installed logo assets; the current interface is an initial design, not a faithful template implementation.

See README.md for exact startup, deployment steps and limitations. Environment install_script and start_skill were saved in the configuration draft; saving is not publication.
