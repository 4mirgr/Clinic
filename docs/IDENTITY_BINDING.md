# Explicit migration of an existing local Clinic identity

The optional shared Auth bridge refuses to attach an existing local account by email. A `409 explicit_account_link_required` is a deliberate boundary, not a reason to guess a matching patient or create another doctor account. `bind_shared_identity` supplies an operator-controlled resolution after the intended provider UUID and exact existing local username have been reviewed.

The command does not match accounts by email, phone or national ID, grant clinical roles, create patients, change a patient link or rewrite an existing identity binding. Canonical email is used only to reject conflicting contact data and populate a new, unlinked PortalAccount when the chosen local user has none. Any existing PortalAccount remains attached to the same patient. Existing staff/superuser/inactive accounts, conflicting clinical groups, existing subject/user bindings and website-role inconsistencies are refused. This is not a bulk migration or a general role-management tool.

## Review without changes

Run in the intended private backend's environment, using an explicitly selected local username and UUID from the correct shared Auth project:

```sh
python manage.py bind_shared_identity EXACT_LOCAL_USERNAME \
  --issuer https://upwbktvnybsjugdegjji.supabase.co/auth/v1 \
  --subject CANONICAL_ACCOUNT_UUID
```

The default is a dry run: no network, account/password/session mutation or token-file read. `--dry-run` is also accepted. It checks local eligibility and reports the required canonical role: local manager → `admin`, local secretary → `secretary`, other local user → `user`. It does not prove that the provider UUID exists or belongs to the intended person; operator review and live verification are still required for commit.

## Deliberate commit during private-backend activation

This operation is for the authorized private shared-identity migration, not the public `/clinic/` preview. `SHARED_AUTH_ENABLED=1` must already be active in that backend environment; otherwise commit is refused to keep the standalone doctor's password usable. Take the normal private database backup and review the chosen mapping before committing.

Obtain a current access token for the **explicitly selected canonical account**, through its normal authenticated shared sign-in. Place only that token in a regular file owned by the command's OS user, with mode **0600**, outside Git and public directories. Never put its contents in command arguments, shell history, documentation, a screenshot or chat. Symlinks and permissive files are refused. No token file is read during a dry run.

```sh
python manage.py bind_shared_identity EXACT_LOCAL_USERNAME \
  --issuer https://upwbktvnybsjugdegjji.supabase.co/auth/v1 \
  --subject CANONICAL_ACCOUNT_UUID \
  --commit --confirm-username EXACT_LOCAL_USERNAME \
  --session-token-file /private/path/shared-access-token
```

The command verifies that token once through the existing fixed HTTPS website session endpoint, without redirects or arbitrary issuer URLs. The verified UUID must match the explicit target and the authoritative shared role must equal the local clinical role. A provider outage, subject/role mismatch or conflicting local contact data aborts without partial writes. It does not call the normal bridge's role-synchronization routine while binding.

Commit atomically creates the exact issuer/subject/user mapping, invalidates the chosen user's local password, advances the portal authentication generation and records a revocation cutoff and safe audit ID. Current clinical groups and any patient link are retained. The provider session used for verification predates the cutoff: the person must perform a **fresh shared sign-in** afterward. Future bridge requests still honor authoritative role changes and account revocation. Disabling shared mode later will not restore the old local password; any rollback needs deliberate operator recovery rather than toggling the flag.

Delete the temporary token file after use. This development change performs no real account binding, provider login or medical-record migration. Tests use synthetic accounts and mocked provider responses; actual private HTTPS/ingress/SSO activation is separate work.
