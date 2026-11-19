# Physician and patient workspace — 2026-11-19

Public previews: [physician](https://drgerami-md.ir/clinic/), [patient](https://drgerami-md.ir/clinic/portal/), [account design](https://drgerami-md.ir/clinic/account/). All records are synthetic; clinical/account forms are disabled. Native runtime addresses remain `/dash/`, `/dash/portal/` and `/dash/account/`, with role-based routing after shared login. The website's `/admin/` remains content management.

The physician sees actual aggregate visit counts, recent patients, today's appointments and follow-ups. `/dash/visits/` filters by patient, visit type or due follow-up. Patient records append in-person/online visits, complaint, note, assessment, plan, optional measured vitals with units and Jalali follow-up date. Marking a follow-up complete records an audit event; it does not send a message or create a calendar event. Online mode records the consultation type, without a built-in video service.

Physician edits retain field-level before/after values and actor/time. Patient intake retains prior versions of complaint/onset, medical/surgical/family history, medications, supplements, allergies and social history. Previously saved reported medical text is captured before the first changed write when no prior snapshot exists; that baseline timestamp is its capture time, not an invented historical submission date. No-change saves avoid duplicate snapshots. These histories are append-only in ordinary application saves, not database-level protection from an operator's direct SQL. Medical text stays outside generic audit events. Patient-reported text does not overwrite clinician notes or publish a summary automatically.

## Prescription workspace

`/dash/prescriptions/` is physician-only. It opens an official provider in an external popup (or ordinary new tab):

- DrNext: https://panel.drnext.ir/
- Tamin: https://ep.tamin.ir/
- IHIO: https://eservices.ihio.gov.ir/ihioerx/

No patient identifier is put in these links. Login and transmission occur at the provider. This workspace can save a manually entered provider/reference and physician note against a patient; it does not transmit, retrieve or validate the prescription. Notes and references are visible to the physician in both worklist and record.

Official DrNext pages https://drnext.ir/doctors/ and https://drnext.ir/landings/doctors describe institutional HIS/web-service integration. No usable public API contract was found. Unauthenticated panel/Tamin requests returned 403 and IHIO timed out; those results cannot establish authenticated framing policy. No iframe restriction is asserted or bypassed, no third-party credentials are collected, and no undocumented API was invented. A supported direct integration needs provider-issued documentation/access before implementation.

## Accounts and limits

See [GOOGLE_SIGNIN.md](GOOGLE_SIGNIN.md) and [SHARED_PORTAL.md](SHARED_PORTAL.md). Secretary scheduling rights, clinical-role checks, patient ownership, revocation, CSRF and private files remain enforced. This stage adds no paid service, active clinical hosting or external patient-data transfer. Actual Google sign-in and website SSO await private-backend/OAuth activation; synthetic preview publication does not enable either.
