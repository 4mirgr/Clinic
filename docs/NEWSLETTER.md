# Educational newsletter — first increment

The separate `newsletter` Django app shares `clinic.PortalAccount`; it is not a patient database or a second authentication service. Creating a website account never subscribes the person or creates a Patient. Completing the existing medical profile creates the explicitly owned Patient separately.

## API and consent

- `GET /dash/api/portal/newsletter`: the current account's state and whether opt-in confirmation delivery is configured.
- `POST newsletter` with exactly `{"subscribe": true}` requests a confirmation email to the account's existing email; callers cannot supply a recipient. No clinical text, activity, user name or file is copied to the email. The pending state is not active consent. Requests are rate limited.
- The opaque 24-hour confirmation proof is stored only as a hash. The public page reads the URL fragment and removes it from browser history; opening the page does not confirm. An explicit button posts `newsletter/confirm`, preserving normal Django CSRF. The proof activates only that subscription, is single-use and never logs in the reader. Resending invalidates the previous proof; expired proofs or disabled accounts are rejected.
- `POST newsletter` with `false`, or `POST newsletter/unsubscribe` with a signed stop-only token, cancels consent and invalidates pending confirmation. Cancellation remains available when email delivery is disabled. These routes do not delete an account or medical record. Standard cross-origin/CSRF protections remain active; the public link is a normal confirmation form, not an RFC 8058 endpoint.
- `GET admin/newsletter` gives actual status counts only to the signed, verified website owner. It grants no clinical permission and exports no medical data.

Consent revision, request/confirmation/withdrawal timestamps and the confirmed address are stored with the subscription. Activity tracking and clinician sharing remain separate defaults-off consents. A changed account address would need new email confirmation; future campaign eligibility must also check active account status, active subscription and confirmed address equality.

## Deployment

`python manage.py migrate --noinput` includes the new `newsletter.0001_initial` after Clinic `0008`. No production migration or data seeding occurred in this stage. Existing shared-portal hosting/PostgreSQL/private-file prerequisites still apply.

Outbound confirmation is **disabled by default** (`NEWSLETTER_ENABLED=0`). Set the same environment's `NEWSLETTER_FROM_EMAIL` and `NEWSLETTER_SITE_ORIGIN` securely, verify sender/domain/TLS and only then enable it. The site origin is fixed configuration, never an untrusted request Host. Preview needs its own HTTPS website origin and isolated email sandbox, database and secrets. Do not reuse production recipients in preview. The host must be able to reach the provider.

The default `NEWSLETTER_TRANSPORT=smtp` uses `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, STARTTLS and a bounded timeout. Render Free blocks outbound SMTP ports; its optional free profile instead uses `NEWSLETTER_TRANSPORT=brevo` with `BREVO_API_KEY` and fixed HTTPS transactional delivery. That backend accepts exactly one recipient, rejects CC/BCC/attachments, does not follow redirects or retry ambiguous POSTs, and requires a 201 response with a message ID. Brevo approval and sender verification are not complete; no key/account was connected. See `ZERO_COST.md` for current free limits.

Locmem delivery is allowed only in non-production synthetic tests. Missing transport or a delivery failure does not claim that confirmation succeeded or that membership is active. Addresses, proofs, passwords and provider exception text are not logged by this module.

## Not implemented or enabled

This is subscription management and opt-in confirmation, **not a production bulk mailer**. Editorial issue creation, reviewed campaign previews, durable queue/idempotency, suppression lists, provider bounce/complaint hooks, RFC 8058 one-click unsubscribe, a valid sender/contact address and approval-bound dispatch are required before sending public newsletter issues. No campaigns, timed sends, real emails, DNS changes, billing changes or other-project database changes were performed.

See website `docs/growth-and-patient-path.md` for the editorial funnel, metrics and outstanding local-practice details.
