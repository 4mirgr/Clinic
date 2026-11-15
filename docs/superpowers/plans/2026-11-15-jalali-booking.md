# Jalali booking, secretary/patient access and Google event edits

> Inline execution under existing user authorization. Update PROJECT_HANDOFF.md and push each completed stage; do not touch real accounts without owner OAuth consent. Existing isolated checkout, no extra worktree.

**Goal:** Tehran-based Jalali popup with today default, configurable free dates/hours, explicit slot selection for staff/patients, and durable updates of existing Google events for dr.gerami.md@gmail.com.
**Architecture:** Keep Gregorian UTC database timestamps and Google ISO timestamps; convert only presentation/input. Backend jdatetime + locally vendored Jalaali JS. Weekly schedule plus dated overrides. Manager/secretary scheduling gate separate from clinical permissions. Patient identity uses the concurrently added canonical PortalAccount and its existing profile linkage; never claim an existing patient by guessed national ID. Existing Google event IDs remain stable across edits; retain old/new reservations until remote acknowledgment.
**Spec:** User's latest request and PROJECT_HANDOFF.md; latest secretary scheduling authorization overrides older blanket calendar denial. No public self-enrollment without identity verification.

## Review focus
- Jalali leap/month boundaries, Tehran day differing from UTC/browser timezone, default today.
- Secretary/patient direct URL/POST/record ownership boundaries; no patient directory leakage.
- Available slots exclude local pending/confirmed/old-update holds and Google busy; no fake availability on provider failure.
- Update same event ID, safe retries and cancellation, preserve old time on uncertain update; account/nonce verified.
- Persist every stage and honest external blockers; no live consent or account verification claims from synthetic fixtures.

## Stage A — calendar and staff scheduling
Files: clinic/jalali.py, templatetags/clinic_dates.py; widgets/templates; static picker/vendor/slots JS+CSS; availability models/forms/service; calendar views/access.
- [x] Write failing tests for Jalali dates/leap/Tehran today, overrides and selected-slot validation; update old secretary expectations to current authorization.
- [x] Implement popup, today default, Jalali rendering, weekly + dated two-window availability, staff slot selection and reservation checks.
- [x] Add HTTP submission request keys to prevent duplicate booking retries. Test browser popup/day selection and night/mobile.
- [x] Whole suite, handoff update, commit/push.

## Stage B — account identity and editing Google events
Files: calendar_api.py, calendar_oauth.py, scheduling.py, calendar_models.py, calendar_views.py/forms/templates, sync_calendar command.
- [ ] Write failing tests for expected Google email/OIDC nonce, same-ID PATCH, uncertain update recovery, old/new holds and conflict/cancellation.
- [ ] Request OpenID email identity and verify signed ID token/audience/issuer/nonce/email. Bind connection to dr.gerami.md@gmail.com. Legacy unverified connections require reconnect.
- [ ] Add edit workflow for existing synced appointments, durable update intent and old-time holds; retry PATCH safely and keep clinical data out of payloads.
- [ ] Tests, handoff update, commit/push.

## Stage C — patient slot selection
Files: existing PortalAccount integration, patient calendar template and scoped endpoints.
- [ ] Write failing ownership and enrollment tests. Implement patient portal limited to own appointments/booking and shared free-slot aggregate.
- [ ] Reuse shared portal login/profile and account revocation checks; no duplicate identities or insecure claim-by-national-ID path.
- [ ] Full SQLite/PostgreSQL, browser, dependency/build checks; independent read-only review and regression fixes.
- [ ] Final docs and GitHub verification; real Google account/hosting still require external setup/consent.
