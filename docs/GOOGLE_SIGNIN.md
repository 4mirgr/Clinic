# Shared password and Google sign-in

> Current identity note (2026-11-22): the owner's subsequent shared Supabase decision and deployed preview identity gate supersede historical standalone/CMS-only statements below. See [SHARED_SUPABASE_IDENTITY.md](SHARED_SUPABASE_IDENTITY.md) and the top of PROJECT_HANDOFF.md. Native private SHARED_AUTH_ENABLED stays off; standalone development features remain available.

The canonical identity is the existing Django User/PortalAccount, with server-side sessions. `/dash/account/` supports self-chosen username/password registration and username/email login through the existing bounded, CSRF-protected API. Public registration creates patients only. Physician/secretary roles remain explicitly provisioned by the operator; a matching email never grants them.

Google OpenID Connect is implemented separately from Google Calendar. No Supabase project, billing or live Google connection was created. This avoids duplicating existing clinical identities while meeting the requested two login methods. The public `/clinic/account/` shows disabled controls and never collects credentials.

## Activation on the future private backend

Configure a Google OAuth **Web application** for the real HTTPS origin and register this exact redirect URI:

`https://drgerami-md.ir/dash/account/google/callback/`

Supply these through the backend secret manager, never Git or browser JavaScript:

```text
GOOGLE_AUTH_CLIENT_ID
GOOGLE_AUTH_CLIENT_SECRET
GOOGLE_AUTH_REDIRECT_URI=https://drgerami-md.ir/dash/account/google/callback/
SITE_ACCOUNT_URL=/dash/account/
```

Only `openid`, email and profile scopes are requested, with online access. No Calendar permission or refresh-token storage is used for sign-in. Existing `GOOGLE_CLIENT_*` variables belong to Calendar and are not reused. Do not weaken HTTPS/CSRF or enable insecure OAuth transport for deployment.

For an existing physician or password account: sign in with the existing password, open `/dash/account/?manage=1`, and explicitly link Google. An anonymous Google login whose email matches an existing account is refused until this link is made. This prevents automatically joining private records by email. A new Google identity creates one patient account with an unusable password, no clinical groups and no existing patient-record match. Repeated Google login uses the verified subject's existing account. Choosing a local password for a Google-only account is not yet an account-settings feature.

The flow uses session-bound state, PKCE and a nonce; signed ID tokens are checked for audience, issuer, verified email, nonce and Google subject. Callbacks expire after ten minutes and are consumed once. Linking binds to the initiating user/authentication hash and rechecks account revocation under a lock. Normal private-document and patient-ownership checks still apply. Provider tokens/codes are not persisted or logged.

## Website account

The future website login and native portal must call the same existing API/session, as described in [SHARED_PORTAL.md](SHARED_PORTAL.md). The current website's GitHub CMS login is for content administration only; patient SSO is not live there. After HTTPS private-backend activation, verify both password and actual Google consent across the website and Clinic with isolated accounts before claiming live SSO. Current Google tests mock provider responses and do not establish real consent or production cookie/proxy behavior.
