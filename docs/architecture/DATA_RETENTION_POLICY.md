# Data retention, erasure and backup policy — DRAFT (`itc-033`, `DEC-SCOPE-357` C6/C7)

**Status: DRAFT. Every period below is a proposal marked `NEEDS_CONFIRMATION`. Nothing here deletes data.**
Owner, legal review and the backup verification owner are open (backlog Q-31, `DEC-PRIV-001`, `PRD_OPEN_ITEMS.md` items 15 and 85).
The source requirement is PDF §10 ("retention rules", "backup and recovery process", "applicable Indian privacy and data-protection
requirements"). That points to the Digital Personal Data Protection Act 2023, but the PDF is classified `UNVERIFIED`.

## 1. What the code does today (verified)

| Rule | Where | Source |
|---|---|---|
| No hard delete of financial, audit or consent records without a confirmed retention rule | `Payment`, `AuditLog`, `ConsentRecord`, `AgentCommission` | `DATA_MODEL.md` §8 |
| An erasure request is refused while a payment or a signed enrolment agreement exists (hold rule) | `api/account.py` `_retention_hold_reason` | `PRD_OPEN_ITEMS.md` item 15 |
| A user can request an export or erasure of their data; an admin fulfils it | `/account/data-requests`, admin data-request fulfil | STU-010 |
| Consent evidence: WhatsApp/SMS opt-in times (ENH-014) and the call opt-out time (itc-033) plus `notification_preference.update` audit rows | `notification_preferences`, `audit_logs` | `DEC-NOT-001`, `DEC-SCOPE-357` |
| Resume versions are never deleted automatically; every download is audited | `student_resumes` | `DEC-SCOPE-350` R5/R7 |
| No scheduled purge or anonymisation job runs by default. hrc-035 added a candidate anonymisation job that stays **off** until super_admin sets a period (6–120 months); students are never in it | `app/worker.py` beat schedule, `candidate_retention_settings` | `DEC-SCOPE-396` K8 |
| A candidate's "delete my data" request is decided by the HR Manager; approval anonymises the candidate and deletes their files | `services/candidate_privacy.py` | `DEC-SCOPE-396` K3/K7 |

## 2. Proposed retention periods (all `NEEDS_CONFIRMATION`; not implemented)

| Category | Examples | Proposed period | Then |
|---|---|---|---|
| Financial records | payments, invoices, receipts, refunds | 8 years after the financial year (Indian accounting and GST record-keeping) | keep; no erasure |
| Audit log | `audit_logs` | 8 years | delete |
| Consent evidence | preferences, `consent_records`, opt-in/opt-out audit rows | as long as the account exists + 3 years | delete |
| Student record | profile, enrolments, attendance, assessments, certificates | as long as the account is active + 3 years after the last enrolment ends (certificate verification needs the certificate number longer) | anonymise |
| Resumes and documents | `student_resumes`, profile documents | 3 years after the last enrolment ends, or on erasure | delete file + row |
| Leads that never converted | `enquiries`, calls, messages, notes | 2 years after the lead closes | anonymise |
| Staff accounts | users with staff roles | as long as employment lasts + the period HR policy sets | `NEEDS_CONFIRMATION` |

Before any purge job is built, the owner (with legal review) must confirm: the periods above, anonymise vs. delete for each category,
who approves a purge run, and whether a dry-run report is reviewed first. A purge job is then its own Feature ID (on `app/worker.py`'s
beat schedule, with a dry-run mode and an audit row per run).

## 3. Backup and recovery (checklist; no code)

| Item | Today | Owner action (`NEEDS_CONFIRMATION`) |
|---|---|---|
| PostgreSQL | DigitalOcean Managed PostgreSQL automated backups (provider) — `DEC-INFRA-002` | Confirm the retention window and point-in-time recovery; do a test restore and record the date |
| Uploads volume (`/data/uploads`) or Spaces | **Not verified**: no confirmed snapshot schedule for the Volume | Turn on a scheduled Volume snapshot (or Spaces versioning) and record the schedule |
| Restore drill | none recorded | Restore a backup into a throwaway environment once per quarter; record the time taken |
| Backups after erasure | erased data stays in backups until they expire | State this in the privacy notice; keep the backup window no longer than needed |

## 4. Malware scanning (`DEC-SCOPE-357` C5)

Resume uploads are scanned only when `CLAMAV_HOST` is set (a clamd daemon reachable from the API). With it set, an infected file is
refused (422, audited as `it.resume.scan_rejected`) and an unavailable scanner refuses the upload (503). Adding the ClamAV container
to the deployment is a DEC-INFRA follow-up. Other upload routes are not scanned yet.
