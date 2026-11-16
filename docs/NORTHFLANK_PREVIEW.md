# Northflank Sandbox preview candidate — 2026-11-16

The owner has no payment card or purchasing ability. Render displayed Add Card despite Free/$0 and an empty Pre-Deploy Command, so it is not the verified cardless path. Northflank's current official pricing explicitly advertises Sandbox **Free / No card needed**, two services, two jobs and one database, with no sleeping. Actual owner signup and deployment remain unverified. No resource, billing, database or credential was created in this preparation stage.

## First owner action

Use the existing GitHub identity at <https://app.northflank.com/signup>. Keep **Sandbox / Free** and confirm the dashboard opens without adding a card. Do not select Pay as you go, purchase credit, link a paid cloud account or create another identity to evade limits. If the actual account requires a card, stop and report that fact instead of assuming the marketing statement overrides it.

Only runtime hosting is changing. Keep the existing Neon project/database authority, Cloudflare public site, IntMed/AUS separation and Django account/medical permissions. Do not create a Northflank database addon or migrate real patient data as part of signup.

## Prepared service configuration

After the actual Free account is confirmed, configure one build-and-deploy/combined service using the existing repository:

| Setting | Value |
| --- | --- |
| Repository | `4mirgr/Clinic` only |
| Branch | `feat/education-newsletter` while PR2 remains unmerged |
| Build | Existing repository-root `Dockerfile` and context |
| Start | Existing Docker CMD; Gunicorn listens on `0.0.0.0:8000` |
| Resources | Only a resource selection explicitly included in Sandbox; one replica; verify $0 before creation |
| Deployment automation | Keep manual/off during preview provisioning |
| Networking | Public **HTTP** port `8000`; Northflank supplies its HTTPS domain and certificate |
| Patient files | Existing `CLINIC_DOCUMENT_STORAGE=database`; no public volume/media route |

Official port documentation permits ports 1–65535 and exposes public HTTP ports through 80/443 with automatic TLS and HTTP→HTTPS redirection. External database use is documented, but successful TCP/TLS access from this account to the actual Neon endpoint must be demonstrated before calling the connection ready.

## Runtime variables

Enter values in the provider's private runtime/secret interface; never in Git, chat, screenshots, build arguments or a public image. Preserve existing prepared preview secrets if they were already securely generated; no D1 pepper, GitHub OAuth or other project's secret is rotated.

| Variable | Value/source |
| --- | --- |
| `CLINIC_ENV` | `production` for secure runtime behavior, including the isolated preview |
| `DJANGO_SECRET_KEY` | Secure random 64+ characters; on the owner's Mac, `openssl rand -hex 32 \| pbcopy` copies 64 hex characters without printing them |
| `CLINIC_PROXY_KEY` | Independent random 32+ characters, later paired only with the same Cloudflare preview |
| `DATABASE_URL` | Actual pooled connection for an empty isolated Clinic preview database |
| `DATABASE_URL_UNPOOLED` | Actual direct connection to that exact same database; used by migrations |
| `DJANGO_ALLOWED_HOSTS` | Exact generated upstream hostname, without scheme/path; obtain it from the created service, not a guessed/wildcard domain |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://feat-member-access-hub.gerami-website.pages.dev` for the current website preview |
| `TRUST_HTTPS_PROXY` | `1` only behind the platform ingress that overwrites the forwarded-proto header; verify real HTTPS behavior |
| `CLINIC_DOCUMENT_STORAGE` | `database` |
| `CLINIC_DOCUMENT_BUDGET_MB` | `128` |
| `NEWSLETTER_ENABLED` | `0`; no live email/provider confirmation is configured |

The current code already accepts `DJANGO_ALLOWED_HOSTS`; the Render-specific hostname inference is not used here. The Dockerfile already collects static assets without production secrets. No runtime rewrite or weakened host/TLS validation is needed.

## Activation gates retained

- Verify actual account Free status, isolated empty database name and endpoint, private secret handling and provider quotas before any migration. No source/protocol fallback to a second patient database is allowed.
- Starting a container is not a schema migration. Apply the full `python manage.py migrate --noinput` chain once from an authorized environment against the direct preview database, with the exact reviewed image/source. Northflank advertises two included jobs; any one-off migration-job setup must first be verified as Free in the account and must not seed users or flush data. No such job exists yet.
- An internal TCP check may prove that port 8000 is listening. Separately verify real **HTTPS `/healthz`** and database TLS; do not mistake Django's HTTP→HTTPS redirect for a successful database probe. `/healthz` itself still does not prove migrations, authentication, private files or backups.
- Configure only matching Cloudflare **Preview** `CLINIC_ORIGIN` (actual HTTPS origin without path) and `CLINIC_PROXY_KEY`. Keep the production patient feature unactivated.
- Run synthetic signup/shared session/profile/private-file/logout/revocation/CSRF/cross-patient/secretary denial smoke, persistence after restart and independent encrypted backup/restore. Clean only those synthetic records afterward.
- Native manager setup uses the existing authorized flow with the real owner; no default/invented medical staff identity is created. Consent purge, calendar retry, newsletter sender/transport and operational scanning/MFA remain separate unfinished work.

No real account, hosted database connection, migration, certificate, backup, email or patient workflow has been verified by this document. Provider documentation is setup evidence, not a production-readiness claim.

## Official references checked

- <https://northflank.com/pricing>
- <https://northflank.com/docs/v1/application/network/configure-ports>
- <https://northflank.com/blog/how-to-migrate-off-of-railway>
- <https://render.com/docs/deploys#pre-deploy-command>
