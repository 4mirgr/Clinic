# Shared website / clinic patient portal

> Current identity note (2026-11-22): the owner's subsequent shared Supabase decision and deployed preview identity gate supersede historical standalone/CMS-only statements below. See [SHARED_SUPABASE_IDENTITY.md](SHARED_SUPABASE_IDENTITY.md) and the top of PROJECT_HANDOFF.md. Native private SHARED_AUTH_ENABLED stays off; standalone development features remain available.

This stage uses one patient identity and record authority: this Django application and its dedicated PostgreSQL database/private document volume. The intended website integration is a same-origin client, not a second patient database. No patients are matched automatically by self-declared email, phone or national ID. Complete patient profiles create their own Patient record; clinician notes and patient-reported text remain separate.

## Current activation status — 2026-11-19

The referenced main-website thread was read before integration decisions. Its current `origin/main` (`5f9a65b…`) has a GitHub CMS-owner account client, not a deployed patient signup or Clinic API proxy. That content-management identity remains separate and never grants a clinical role. Another task is editing the website; this stage does not change or deploy it.

The ready native shared entry is `/dash/account/`: chosen username/email + password, or Google OpenID Connect when its dedicated keys are configured. Both methods use Django User/PortalAccount and the same session; see [GOOGLE_SIGNIN.md](GOOGLE_SIGNIN.md). No Supabase Auth project or second identity authority was created. `SITE_ACCOUNT_URL` defaults to the native entry. Change it to `/account/` only after the website client/proxy described below actually exists and passes same-origin integration checks.

Public `/clinic/account/` is an inert design preview. No real passwords, Google consent, patient signup, uploads or backend API are enabled by publishing it. The native private backend is still not deployed.

## Surfaces and authorization

- `/dash/portal/`: patient interface; `/dash/account/`: current shared account entry. Future website `/account/` and header modal must read/write this same API/session once implemented.
- `/dash/api/portal/session`: safe user/capabilities, CSRF token and consent flags. GET sets the CSRF cookie; all browser mutations retain Django CSRF protection.
- POST `signup`, `login`, `logout`, `password`, `recovery`, `reset-password`; GET/POST `profile`, `privacy`, `activity`, `documents`.
- `documents/<uuid>/download`: patient ownership check on every request, attachment-only response and no public media route. The existing manager document route remains restricted to clinical managers; website admin status gives no clinical access. Secretary remains denied.
- Patient file uploads are 5 MiB maximum, at most 100 files per patient, PNG/JPEG are decoded/verified with pinned Pillow, PDF header and terminal marker are checked. This is format validation, not a malware-scanning claim. Existing clinical staff limits remain unchanged.
- `admin/users`: registered portal users and recovery requests. Verified clinic managers and website co-admins may read; only the signed website owner may change site roles/status or create reset links. Those actions never create clinic groups, staff or superuser rights. Clinical staff accounts are protected.
- Website owner claims use HMAC-SHA256 with the proxy key over timestamp, method, complete downstream path/query, SHA256 body and fixed owner ID; maximum age 30 seconds. Browser-supplied claims are stripped by the website proxy. Claims do not authorize medical-file access. Normal CSRF checks still apply to signed mutations.

Clinic and website share a root-path HttpOnly session. Production uses `__Host-gerami-clinic; Path=/; Secure; HttpOnly; SameSite=Lax`; the CSRF cookie also has root scope. Password changes and resets invalidate old Django authentication hashes. Explicit account revocation uses a portal generation checked on each request and again before patient mutations. Row locks use consistent user/account order and avoid locking the nullable Patient side of PostgreSQL joins.

Activity starts off. Saving events and sharing them with the clinician require separate explicit consent. Disabling tracking clears sharing and history; erasure is also available separately. Bounded search/article-opening events are not diagnoses or proof of completed reading. Contact details, long identifiers and URLs are suppressed. Reads show the recent 90-day window, and a maintenance job purges inactive accounts' expired events.

## Activation contract

The application is not deployed in this stage. Do not point preview traffic at a production patient database. Provide separate development/preview and production hosts/databases/storage and secret values.

1. Run the existing Docker/Python deployment with a dedicated PostgreSQL database (`verify-full` TLS), persistent private document volume, encrypted backups and an actual restore check. See README and the handoff's remaining operational requirements. No patient files or secrets belong in Git or the web's public directory.
2. Set the Clinic secrets/host allowlist from `.env.example`. Set `CLINIC_PROXY_KEY` to a strong random value in the server secret manager and the same environment's Cloudflare Pages secret. Restrict direct origin access. Set Clinic's allowed host to the real upstream hostname and CSRF trusted origins to the actual public site. `TRUST_HTTPS_PROXY=1` is only for an ingress that overwrites that header.
3. Implement/restore and review the same-origin website client/proxy first; it is not present on the inspected current main branch. Then on the website, set `CLINIC_ORIGIN` to the HTTPS origin only (no path, credentials, query or fragment). The website proxy accepts the fixed origin or a configured `CLINIC_APP` binding, filters cookies/headers, bounds request bodies and never follows authentication redirects. A missing/unavailable clinic fails closed, with no second patient-signup fallback.
4. Run `python manage.py migrate --noinput` (including both `0006` branches, merge `0007_merge_calendar_portal` and Calendar `0008`, plus workspace/auth migrations through `0014`) and `collectstatic --noinput`. Schedule `python manage.py purge_portal_activity` daily in the host/container; it touches only expired optional activity, not medical records. Keep the existing scheduling worker separately.
5. Verify real HTTPS cookies, CSRF, signup → website profile/upload → native `/dash/portal/` → native edit → website read; logout/password revocation, cross-patient/secretary denial and private backups/storage. Use synthetic isolated preview data only, then clean it up. Do not seed real users or send recovery email as a test.
6. The website's GitHub-owner/AUS D1 services and IntMed/AUS backends remain independent. No copy/synchronization of those credentials is part of this portal. Calendar/notifications remain disabled until separately configured/authorized.

The Python host, PostgreSQL and persistent private storage are still missing. Cloudflare R2 is not enabled and was not enabled by this stage. No billing, DNS, production patient data, Google consent, email or appointments were changed.

## Shared account appointment selection

The native `/dash/booking/` reuses this PortalAccount, session and linked Patient. Profile completion is required; no national-ID/phone claim of an existing medical record is allowed. Patient inputs can only name their own linked patient. Account revocation is rechecked inside the booking transaction. Patients see only their own appointments and aggregate free times; staff lists, edit/cancel/retry, availability configuration and OAuth remain staff-only. Website admin status does not grant staff permissions. Jalali dates default to today in Tehran. Real calendar availability requires the separately configured, verified Google connection. See GOOGLE_CALENDAR.md.
