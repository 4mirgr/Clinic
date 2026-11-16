# Northflank Sandbox preview — service creation blocked — 2026-11-16

The owner has no payment card or purchasing ability. Render displayed Add Card despite Free/$0 and an empty Pre-Deploy Command. The owner's later Northflank screenshot confirms a **Free** team and connected GitHub identity, but the London combined-service creation form explicitly says **Payment method required** and **Creating this service requires a card**. Both runtime candidates are therefore blocked for this owner's no-card constraint. Signup is not service eligibility. No hosted Clinic runtime, payment or database connection has been verified.

The official pricing page still advertises **Free / No card needed**. A fresh check of pricing, project creation, Add a card and the August/September 2026 changelog did not establish a no-card exemption for this account, or show that changing regions removes the gate. Do not advise a region change, another signup, card entry or account upgrade as an unverified fix.

## Current owner action

Stop the creation form. If the owner chooses to contact Northflank support, request clarification whether this existing Free team can create one CPU-only Docker service **without any card or billing activation**. No support message has been sent by the agent and no exemption is promised. Do not enter payment details, purchase credit, link a paid cloud account or create another identity to evade limits. Preserve the existing project; no deletion is needed.

Only runtime hosting is undecided. Keep the existing Neon project/database authority, Cloudflare public site, IntMed/AUS separation and Django account/medical permissions. Do not create a Northflank database addon or migrate real patient data as part of signup.

## Prepared service configuration

The configuration below is retained preparation, **not an instruction to proceed through the current card gate**. Use it only after cardless service creation is explicitly confirmed for the actual account, with a Free resource selection:

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

Only owner screenshots of the Free team, connected GitHub and card gate are verified setup evidence. No hosted database connection, migration, certificate, backup, email or patient workflow has been verified. Provider documentation is not a production-readiness claim.

## Official references checked

- <https://northflank.com/pricing>
- <https://northflank.com/docs/v1/application/network/configure-ports>
- <https://northflank.com/blog/how-to-migrate-off-of-railway>
- <https://render.com/docs/deploys#pre-deploy-command>
- <https://northflank.com/docs/v1/application/getting-started/create-a-project>
- <https://northflank.com/docs/v1/application/billing/add-a-card>
- <https://northflank.com/changelog/august-and-september-2026>
