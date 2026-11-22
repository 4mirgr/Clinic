# Patient communication and reminders

This is a native Django feature, not an active service in the public `/clinic/` preview. No real messages, provider credentials, paid services or patient data were used during development. All channels are disabled by default. The physician console is `/dash/communications/`; patients choose reminder channels and kinds in their private portal. Secretary/content-administrator status grants no clinical communication access.

## Consent and destination verification

Patient opt-in is separate for email, Telegram and WhatsApp; reminders can be limited to appointments, follow-ups and newly recorded advice. Each channel also requires explicit physician-attested contact ownership. A signup email is **not** treated as verified. The physician enters the account's exact email or registered mobile number after confirming it directly with that patient. WhatsApp uses `98…` for the existing Iranian `09…` number; no matching to another medical record is attempted.

For Telegram, an optional **connect Telegram** button avoids typing a chat ID. While logged into their own portal, the patient obtains a one-time deep link to the configured clinic bot and presses Start. A secret-authenticated Telegram webhook consumes the fifteen-minute pairing token and verifies that the message came from a private chat whose positive sender/chat IDs match. The token is bound to the account's current authentication generation; only a hash is stored, and reuse, expiry, account suspension/revocation or a secretary account cannot bind it. Creating another link invalidates the old one. Pairing never automatically opts the patient into messages.

Manual physician attestation remains a fallback: the patient starts the bot and shows their private numeric chat ID; the physician confirms ownership before saving it. Group IDs, bot usernames and arbitrary patient-submitted chat IDs are not accepted. Contact changes invalidate queued work; preferences can be withdrawn at any time.

### Optional Telegram pairing setup

Provide `TELEGRAM_BOT_USERNAME` and `TELEGRAM_WEBHOOK_SECRET` (at least 32 random characters) alongside the server-only bot token. The private backend's fixed webhook address is:

`https://drgerami-md.ir/dash/api/communications/telegram/webhook`

The operator must register that HTTPS endpoint with Telegram's official `setWebhook` API using the same `secret_token` and configure the ingress to preserve `X-Telegram-Bot-Api-Secret-Token`. No registration is performed by this code or during development. Only this isolated external callback is CSRF-exempt; patient challenge issuance and preference changes keep normal CSRF protection. The callback requires the secret header before parsing at most 8 KiB, consumes only an exact private `/start <opaque token>` message and makes no outbound reply/network call. No medical data or account identifier is placed in the `t.me` link. Treat it as a short-lived bearer pairing secret and do not share it.

Pairing can be available while outbound delivery stays disabled. The configuration flag reports that keys/username are present; it cannot prove that the real webhook was registered or Telegram can reach the private backend. The public synthetic preview never issues a real pairing token. Official webhook reference: https://core.telegram.org/bots/api#setwebhook .

## Providers

- **Email**: Django SMTP backend, actual host/port, TLS, sender and credentials through the private backend secret manager. SMTP acceptance is not proof of delivery/read. A console/locmem backend is never reported as a connected email service.
- **Telegram**: Bot API `sendMessage` over HTTPS at `api.telegram.org`; `TELEGRAM_BOT_TOKEN` is a server-only secret. The patient must have started the bot. No personal Telegram-account automation.
- **WhatsApp**: official WhatsApp Business Cloud `/messages` endpoint with a provider-approved template in the configured language. This can require Meta/business approval and charges; this stage provisions nothing and changes no budget. No WhatsApp Web automation, scraping or personal account sessions. The approved template must be a generic clinic-portal reminder containing the fixed portal URL and no variable patient/medical data; this implementation sends no template parameters. Templates needing parameters are not supported by this version.

Settings: `COMMUNICATIONS_ENABLED`, `COMMUNICATION_PORTAL_URL`, Django `EMAIL_*`/`DEFAULT_FROM_EMAIL`, `TELEGRAM_BOT_TOKEN`, optional `TELEGRAM_BOT_USERNAME`/`TELEGRAM_WEBHOOK_SECRET`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_TEMPLATE_NAME`, `WHATSAPP_TEMPLATE_LANGUAGE`, `WHATSAPP_API_VERSION`. Keep tokens/passwords in the backend secret manager. Readiness means configuration is present, not a live provider authentication/delivery check.

Only a general reminder and fixed HTTPS portal-entry link is sent. No patient name, identifier, diagnosis, medication, report, advice title, secret URL token or medical summary is put in email/messenger text. Portal authentication/ownership remains necessary to see details. Patients may still infer the service relationship from a reminder, so channels are optional.

## Durable outbox and worker

Planning scans confirmed future appointments (24 hours before), pending dated follow-ups (08:00 Tehran on the preceding day) and advice packets/standalone advice recorded in the last seven days. It does not inspect draft recommendations or send clinical content. The current source time/status is revalidated before dispatch. Changed/cancelled appointments, completed follow-ups, expired reminders, inactive/revoked accounts, changed destinations, secretary accounts and withdrawn consent cancel pending work. Packet deliveries do not create duplicate notices for each included guide.

The unique dedup key includes account, source/version, channel, destination fingerprint and authentication generation. Previously accepted or uncertain sends suppress replacement notices for the same event/channel. Queue rows contain IDs/fingerprints/status, not message bodies or provider secrets. An atomic conditional claim prevents normal concurrent workers from submitting the same row twice. A worker interrupted during send becomes `unknown` after fifteen minutes; it is never automatically retried. Exactly-once delivery across an external provider/network crash cannot be guaranteed.

Safe rejected/pre-send failures may retry at most three times, at least fifteen minutes apart. Read timeouts, uncertain HTTP responses/5xx, incomplete successful responses and ambiguous SMTP results become `unknown` for manual investigation. `sent` means the provider accepted the submission, not the patient received/read it. The physician UI can retry only bounded `failed` rows and never `sent`/`unknown` rows.

Commands default to no delivery:

```sh
python manage.py send_patient_notifications --check
python manage.py plan_patient_reminders --dry-run
python manage.py send_patient_notifications --dry-run
```

After the separately hosted private backend, verified contacts, provider configuration, and a controlled synthetic-recipient connectivity test are ready, an operator can schedule:

```sh
# Example scheduler jobs, every five minutes; not installed by this change.
python manage.py plan_patient_reminders --commit
python manage.py send_patient_notifications --send --limit 50
```

Never install these jobs against the public synthetic export. Preview scripts must strip native communication scripts/disable choices. Before enabling live channels, verify approved WhatsApp template contents, provider authentication, actual recipient binding, TLS and opt-out with a recipient the owner controls. Tests mock providers and cannot prove real delivery or an external messaging account exists.

Official implementation references: https://core.telegram.org/bots/api#sendmessage and https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-message-templates/ . No API request to a real recipient is made by setup or health-check commands.
