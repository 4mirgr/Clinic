# Theme, artwork and Google Calendar implementation plan

> Execute inline with superpowers:executing-plans. Existing user authorization to perform necessary work persists. Preserve each stage in PROJECT_HANDOFF.md and push normal commits to origin/main; never force push.

**Goal:** Preserve project continuity, add polished light/dark experience and real Google Calendar OAuth/scheduling integration that fails closed until configured.
**Architecture:** Extend the existing Django application. User preferences are server-persisted; only theme preference may be mirrored in a cookie. OAuth uses the official Google library; refresh tokens are encrypted with a dedicated Fernet key. Durable local appointments/outbox plus provider free/busy checks and idempotent event IDs.
**Tech stack:** Existing Django/PostgreSQL/Python, Google OAuth library, cryptography, local CSS/JS, GPT ImageGen decorative artwork.
**Spec:** PROJECT_HANDOFF.md user requirements and existing docs/superpowers/specs/2026-11-15-dash-design.md. No real calendar writes before owner OAuth consent and explicit office-hour configuration.

## Constraints / defaults
- Preserve clinical routes and all server-side role restrictions. Secretary has no scheduling rights until specified.
- Do not change current core layout or claim inaccessible template fidelity. Generate original artwork; do not fabricate the original logo.
- Print always uses a light paper background. No patient data in cookies/localStorage/artwork.
- Clinic timezone Asia/Tehran. Workdays/hours are owner-configured, not guessed; default booking disabled.
- Google connection is for Calendar, not replacement of the application's login. Use a dedicated app-created calendar and primary calendar free/busy. Never send name/national ID/clinical notes to Google by default.
- External credentials/network are not present. Finish independent code/tests/docs; report live consent/setup as remaining requirements, not a working live account.

## Review focus
Theme state across anonymous/login/mobile, no CSS load regressions, light print in dark mode. OAuth state/PKCE, expiry, owner binding and callback errors. No plaintext refresh tokens. Deterministic Google event IDs and recoverable uncertain writes. No double reservation inside app or outside work hours; do not claim atomic conflict prevention against unrelated Google clients. Provider failures never become confirmed bookings.

## Stage 1: continuity baseline
- [x] Create PROJECT_HANDOFF.md and AGENTS.md, inspect remote, commit existing app and push to new main branch.
- [x] Verify remote commit. Record historical evidence and gaps without secrets.

## Stage 2: theme + artwork
Files: clinic/models.py, clinic/context.py, clinic/views_preferences.py, tests/test_preferences.py; shared templates, static/clinic/theme-init.js, app.js/app.css, art/.
Interface: UserPreference(user, theme), POST /dash/preferences/theme/ with theme=light|dark and safe local next path.
- [ ] Write failing tests for stored theme, anonymous cookie, role independence, invalid input/CSRF/redirect boundary.
- [ ] Implement theme and migration. Generate original transparent illustration using GPT ImageGen and store optimized artifact/provenance in repo.
- [ ] Exercise day/night/reload/mobile and light PDF in real Chromium; whole Django suite passes.
- [ ] Update handoff with results and commit/push stage.

## Stage 3: calendar + appointments
Files: clinic/calendar_models.py (registered by models.py), calendar_service.py, calendar_views.py, calendar_forms.py; templates/clinic/calendar*.html; tests/test_calendar.py; management command sync_calendar; migration.
Interfaces: singleton CalendarConnection and ScheduleSettings; Appointment(UUID, patient, start/end, status, remote event ID); provider service free_busy/ensure_event/remove_event; request-bound OAuth start/callback; slot selection and booking service under database lock.
- [ ] Write failing tests for missing config and role boundaries; OAuth one-time state/expiry/manager binding; encrypted token persistence; availability and local/provider conflicts; retry idempotency, failures and cancellation.
- [ ] Implement official OAuth flow with PKCE and explicit offline consent, dedicated calendar creation, secret isolation and manager-only connection/settings/appointments pages.
- [ ] Implement owner-configured schedule, automatic next slot within requested date, synchronization outbox and safe retries. Provide a manual retry command for periodic hosting scheduler.
- [ ] Add Google setup guide and required environment variable names; never store actual secrets in Git.
- [ ] Run whole suite, browser tests, Postgres tests and build/checks as applicable. Independent whole-change review; fix important findings with regression tests. Update handoff and commit/push.

## Stage 4: final record
- [ ] Verify remote HEAD, clean worktree, no secret/data tracked. Update validation evidence and environment startup instructions if needed.
- [ ] Report implemented features versus untested live OAuth/hosting and outstanding office-hour inputs.
