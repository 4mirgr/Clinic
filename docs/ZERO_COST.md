# Zero-payment deployment profile — 2026-11-16

Owner constraint: **no purchases, card, paid trial, billing activation or automatic upgrade**. Free limits may stop the service; they must not become authorization to spend. Do not create more accounts to bypass provider limits. The existing GitHub/email identities can be used for normal signup. No extra Google account is required by this design.

## Current hosting checkpoint — Render and Northflank card barriers

The owner's live screenshots show Render **Free / $0** selected, but creation opens **Add Card**. The owner confirmed the **Pre-Deploy Command is empty**; Free does not offer a persistent disk. No card, payment, service creation or hosted Clinic runtime has been verified. The earlier no-card Render recommendation was not validated for this account. Do not keep asking the owner to change unrelated fields or buy a card.

The replacement candidate **Northflank Sandbox is now blocked too**: the owner's screenshot shows a Free team, connected GitHub identity and Europe West/London, but the combined-service form explicitly says **Payment method required / Creating this service requires a card**. The official [pricing page](https://northflank.com/pricing) still says **Free / No card needed**; that does not establish service eligibility for this account. Fresh official documentation did not prove that switching regions or service settings removes the gate. Stop creation; no payment or upgrade is authorized. The owner may ask support to clarify cardless eligibility, but no support message was sent and no exemption is promised. See [NORTHFLANK_PREVIEW.md](NORTHFLANK_PREVIEW.md).

The public website stays on the existing Cloudflare Pages project. The same dedicated Clinic Neon PostgreSQL, database-backed private files, Django identities/roles and same-origin bridge remain the design. No Northflank database/addon, second patient authority, DNS, Google consent, actual patient data or secret has been changed. The Render blueprint below remains historical/optional; it is not an active no-card route for this owner.

## Selected services

| Part | Service | Boundary |
| --- | --- | --- |
| Public site | Existing Cloudflare Pages | Keep its existing Git integration and independent IntMed/AUS. No R2/billing activation. |
| Django process | Undecided; Render and Northflank creation blocked on card | Preserve the existing Docker app. No verified cardless runtime yet; no paid fallback or repeated signup without stronger evidence. |
| Canonical account/records/files | Dedicated Neon Free PostgreSQL | Official current Free limits: 100 CU-hours/project/month, 1 GB storage/project and 5 GB network transfer/month. Limits can suspend compute or reject storage growth; they do not grant permission to upgrade. The account's actual Free label/limits must be checked before setup. |
| Optional confirmation email | Brevo Free via HTTPS | Official free plan: up to 300 emails/day after account approval, no card. Sender/domain setup is still required. SMTP ports are blocked on Render Free, so use the optional HTTPS backend. No campaigns are enabled. |

These are limited free services, not an availability guarantee. Before any real patient use, evaluate private backup/restore and remaining operational controls from the handoff; a successful build is not deployment approval. No paid fallback is automatic. The original Render limits/steps below describe the old candidate only; signup is currently blocked on a card for this owner.

## Current Neon selection and setup evidence

- Organization supplied by owner: `org-curly-heart-56903127`.
- Existing project: `blue-voice-09006552` ([Console](https://console.neon.tech/app/projects/blue-voice-09006552/)). A second project is not created as a substitute for failed access.
- Owner screenshots confirmed display name `my-first-project`, **Free plan**, Frankfurt region and default branch `production`. Owner supplied database `neondb` and role `neondb_owner`. An empty `clinic_preview` database was requested within the same project; its creation and the pooled/direct URLs have not been confirmed. A storage figure alone does not prove that an existing database is empty.
- Official `neon` CLI 9.5.0 installed. Official `neon init` was run for this exact project/org with no JavaScript scaffold; the PostgreSQL skill and project-scoped OAuth MCP config were installed. MCP starts read-only for inspection.
- CLI login is currently blocked by the cloud environment's enforced network allowlist (`api.neon.tech` proxy CONNECT 403). Init explicitly reported **Project skipped**. No connection URL was retrieved and no `.env` or hosted schema was fabricated. No “Neon Setup Complete” claim is made.
- Current Codex Cloud navigation from official docs: Settings → Codex Cloud → Environments → select this environment → Edit → Public internet access. Allow `api.neon.tech`, `console.neon.tech`, `oauth2.neon.tech`, `mcp.neon.tech`, save/publish, then retry browser login. A specific PostgreSQL endpoint may also need network access after its real hostname is known. If the UI differs, inspect the actual settings instead of guessing another menu.
- After authentication, inspect the existing branch/schema and verify the Free plan. Fetch connection values only to a gitignored secret file/vault. Runtime uses pooled `DATABASE_URL`; migrations/dumps use direct `DATABASE_URL_UNPOOLED`. Keep `verify-full` certificate/hostname validation. Never paste these values into chat.

## Durable private documents without a paid disk

`CLINIC_DOCUMENT_STORAGE=database` selects `document_store.storage.DatabaseDocumentStorage`. The existing `Document` metadata, file paths, patient ownership, doctor/secretary permissions and attachment-only authenticated routes stay unchanged. Raw bytes and hashes are stored in the **same dedicated Clinic database**, not D1, public media, Google Drive or another project's database. The app can restart on an empty local filesystem without losing stored document bytes.

- A shared transaction/row lock accounts for all stored document bytes. The default application budget is 128 MiB, below the database allowance. This is a document-byte budget, not a measurement of total PostgreSQL/table/index/TOAST/backup usage; monitor actual provider storage/egress too.
- At the budget boundary, new uploads fail explicitly with `document_storage_full`/507; existing files remain readable. No automatic deletion or upgrade occurs. The existing 5 MiB patient / 20 MiB staff limits remain.
- No public `url()` or filesystem `path()` is provided. Checksums are verified before returning bytes. Metadata failures roll back database bytes/accounting together.
- Run full `migrate`, including `document_store.0001_initial`, on a dedicated isolated preview first. Storage mode is an installation choice; **do not switch a deployment with existing files** without a separately tested copy/verification/rollback procedure. Defaults preserve the existing filesystem mode.
- A coherent database backup now includes document bytes. An encrypted backup outside the database and an actual restore test remain required before real records. Keep backup frequency/size within free egress; the provider's short free restore window is not an independent backup.

## Deployment order

1. Owner creates normal Free Render/Neon accounts without a card. No service is created by adding `render.yaml` to Git. The blueprint is explicitly a Free preview, auto deploy off, no disks/databases/cron. If any provider requires payment, stop instead of supplying a card or enabling billing.
2. Verify project, Free plan, branch, region and schema before migrations. Separate preview and production DBs/secrets; never branch-copy real patient data into tests. Confirm schema-only isolation when data exists. A single free Render process is sufficient for the first preview; do not keep simultaneous 24/7 preview and production services that exceed the shared 750 hours.
3. Configure Render secrets securely. `RENDER_EXTERNAL_HOSTNAME` adds only its exact valid onrender.com host to Django's allowlist. Set the exact preview website origin in `DJANGO_CSRF_TRUSTED_ORIGINS`. Supply a securely generated 64+ character `DJANGO_SECRET_KEY` through the secret store; Render's native generated 256-bit base64 value is only 44 characters, below this application's 50-character minimum, so the blueprint deliberately prompts for this key. Native generation is sufficient for the separate 32-character-minimum proxy key. No known/default staff password exists.
4. Apply migrations and create the real manager through the existing secure management command from an authorized terminal with the direct database connection. Free Render does not supply its paid SSH/shell features. The local development environment can run these commands after secure network/auth setup; this blueprint deliberately does not auto-migrate or bootstrap identities on every restart.
5. `/healthz` is a generic upstream hosting/DB probe only. It returns no project/user details and does not prove the shared portal, migrations, files or backups work. All product routes remain `/dash/`; the public website root is preserved.
6. Connect only matching Preview `CLINIC_ORIGIN`/`CLINIC_PROXY_KEY` in Cloudflare. Perform synthetic shared-login/profile/file/logout/revocation/CSRF/isolation smoke, persistence/restart and backup/restore. Production keeps its existing release gate until these succeed. Expect the free cold start to outlast the current first request timeout; a temporary unavailable result is honest and must not create fallback identities.
7. Email remains disabled until Free Brevo approval and sender verification. Set `NEWSLETTER_TRANSPORT=brevo`, `BREVO_API_KEY`, the sender and the exact same environment's `NEWSLETTER_SITE_ORIGIN`. The backend accepts one confirmation recipient, rejects CC/BCC/attachments, uses fixed HTTPS with no redirects, and treats quota/error/ambiguous acceptance as failure. It never retries a potentially accepted POST automatically. Use an isolated sandbox/captured test, not real patient mail.

Retention jobs, private backup automation, MFA and scan/quarantine remain operational work from the existing handoff. No monitoring/retention workflow is deployed or charged in this stage. Free quotas are actual limits; zero cost does not mean unlimited records, uploads, messages or uninterrupted availability.

## Official sources checked

- [Render free limits and SMTP restrictions](https://render.com/docs/free)
- [Render's no-card statement](https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026)
- [Neon Free quotas and limit behavior](https://neon.com/pricing)
- [Brevo Free and transactional API availability](https://www.brevo.com/pricing/)
- [Codex Cloud configuration](https://developers.openai.com/codex/environments/cloud-environments)
- [User-requested Neon setup](https://neon.com/get-started/prompt.md)

Recheck actual account UI/terms at provisioning time. Owner screenshots show Neon Free and Northflank Free/GitHub-connected, but Northflank service creation requires a card. No authenticated provider access by the agent or hosted Clinic runtime is claimed.

Additional official sources checked for the replacement candidate:

- [Northflank Sandbox pricing and explicit no-card statement](https://northflank.com/pricing)
- [Northflank public HTTP ports and automatically generated TLS](https://northflank.com/docs/v1/application/network/configure-ports)
- [Northflank migration guide: compatible external databases are supported](https://northflank.com/blog/how-to-migrate-off-of-railway)
- [Render pre-deploy commands are paid-service features](https://render.com/docs/deploys#pre-deploy-command)
