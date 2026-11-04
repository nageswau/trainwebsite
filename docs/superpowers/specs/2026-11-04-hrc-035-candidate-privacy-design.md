# hrc-035 — Candidate consent, retention, deletion and access revocation (design)

**Decision:** `DEC-SCOPE-396` (builder's calls, `NEEDS_CONFIRMATION`). **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` hrc-035
(PDF §2 "protect candidate data through … consent", §15 "consent … retention/deletion workflows … access revocation when staff leave or
change roles"; PDF classified `UNVERIFIED`). Scope approved by the owner 2026-11-01 (backlog Q-00). Dependencies hrc-012
(`DEC-SCOPE-382`) and hrc-022 (`DEC-SCOPE-386`) merged. The retention-period decision (Q-31, shared with itc-033) is still a draft
(`docs/architecture/DATA_RETENTION_POLICY.md`, `DEC-PRIV-001` open): the owner said to proceed with the recommended answers, so the
retention job is built but **off until the owner sets a period** (no automatic deletion before legal sign-off).

## Intent
Every candidate record carries a recorded basis for holding it; a candidate can ask for their data to be deleted and the HR Manager
decides; an optional retention rule anonymises candidates nobody has touched for a set time; staff who leave lose access and their
candidate links. Anonymised candidates disappear from every recruiter screen but still count in historical reports.

## Builder's calls (K1–K10)
- **K1 Consent per source.** `candidate_consents` gains `source` (`student`, `portal`, `website`, `manual`, `import`) and `lawful_basis`
  (`consent` = the candidate agreed; `provided_for_placement` = the candidate gave their details for job placement, DPDP Act 2023 s.7(a)
  "voluntarily provided"). The three existing writers record their source with basis `consent`; the migration backfills existing rows
  (no user → website, candidate user → portal, else student). A recruiter creating a candidate and an import batch may send
  `lawful_basis`; when sent, one `opt_in` row (`source` manual/import, version `staff-v1`) is written. Omitted (older clients) = no
  row: the record shows "No basis recorded" rather than an invented one. The recruiter form and import form require the choice.
- **K2 Visible basis.** The recruiter candidate detail gains `consent` — the latest row's source, basis, version and time (or null).
- **K3 Anonymiser (`services/candidate_privacy.anonymise`).** One transaction, the candidate row locked: name → "Anonymised candidate";
  mobile, email, LinkedIn, college, current company, city, source detail, every compensation amount, notice/availability cleared;
  `anonymised_at` + `anonymised_reason` (`request` / `retention`) set, `archived_at` set if empty. Deleted: education, employment,
  certification rows, notes, tasks, collaborators, duplicate pairs, document requests, documents and resumes (stored files and previews
  removed from storage after the commit; `profile_share_items.resume_id` and `job_applications.resume_url` cleared first). Redacted:
  recruiter call notes, recruiter message bodies/subjects, linked website applications (name, email → placeholder, phone, cover note,
  uploaded resume file), consent IP addresses, and the `changes` of the candidate's own audit rows. Kept (aggregate statistics): code,
  source, UTM, status, qualification, experience, state/country, skills, applications, offers, joinings and their histories, consent
  rows (evidence). A linked candidate-portal account is closed like SEC-002's fulfil (name "Deleted user", placeholder email, no phone,
  inactive, `session_version`+1, preferences and open verification tokens removed). A student-linked candidate is never anonymised
  here (the student record has its own policy).
- **K4 Visibility.** `candidates.pool_filter()` also requires `anonymised_at IS NULL`, so search, detail, matching, duplicates, merge,
  notes and pools all drop the record (404). Reports that count applications/joinings do not use the pool filter and keep counting; they
  show the placeholder name.
- **K5 Hold.** A candidate with an offer in `offer_pending`/`offer_received` is held: an approval is refused (409, the request stays
  pending) and retention skips them. Retention also skips candidates with an open application (status not joined/rejected/withdrawn).
- **K6 Deletion request.** The candidate asks from Privacy (`POST /candidate/me/erasure-request`, idempotent: an open request is
  returned with 200, a new one 201). It reuses SEC-002's `data_subject_requests` (type `delete`, status `in_progress`). The Privacy
  response gains `erasure` (status, dates, rejection reason). A candidate's `delete` sent through `/account/data-requests` lands in the
  same queue; the IT-admin SEC-002 fulfil refuses a candidate subject (409, "handled by the HR Manager") so the candidate record is
  never left behind.
- **K7 HR Manager queue.** New permission `candidates.erase` (seeded for `hr_manager`; super_admin implicit). `GET
  /recruiter/candidate-data-requests?state=open|decided` lists candidate deletion requests (code, name, email, requested, open
  applications, offer hold); `POST …/{id}/decision {decision: approve|reject, reason}` — reject needs a reason (≤500); approve runs K3.
  Audit `candidate.erasure_approved` / `candidate.erasure_rejected` with ids only (no PII). Page `/it/hr-manager/data-requests`.
- **K8 Retention.** One-row `candidate_retention_settings` (`months`, NULL = off, 6–120). `GET /recruiter/candidate-retention`
  (`candidates.erase` holders) returns the setting, how many candidates are due now, and the last run; `PUT` is super_admin only
  (audited). Daily beat task 02:00 IST anonymises due candidates in batches of 100 (commit per batch, `SKIP LOCKED`), audit one
  `candidate.retention_run` row with the count. Last activity = the latest of the candidate's `updated_at`, its applications'
  `updated_at` and its website applications' `created_at`.
- **K9 Staff leaving.** When an admin deactivates a user, they are removed as placement-officer owner and as collaborator of every
  candidate (assignment history reason `reassign` — the hrc-012 CHECK allows create/assign/reassign — and one `candidate.assign` audit
  each with reason `deactivated`), and for `placement_officer`,
  `placement_manager`, `hr_team`, `hr_manager` the `session_version` is incremented (recruiters and telecallers already are). A recruiter
  who is a primary owner is still refused until reassigned (hrc-012 O8). No staff role-change path exists today, so none is added.
- **K10 Not built:** a staff-initiated "anonymise now" for candidates without a login, the candidate data export, an email to the
  candidate on a decision (the Privacy page shows it), retention for students (itc-033 policy).

## Numbering
Migration `0273_candidate_privacy` (after `0269_match_engine`, rechained at merge); API §12KO; RBAC §2.290.

## Acceptance criteria
1. Each source writes a consent row with its source and basis; manual/import record the chosen basis; the detail shows it.
2. A candidate requests deletion; the request appears in the HR Manager queue; reject needs a reason and shows on Privacy.
3. Approve anonymises (K3): the candidate 404s for recruiters and is absent from search, its files are gone from storage, its portal
   login fails, and an application count for its requirement is unchanged.
4. A pending offer holds the approval (409) and retention skips it.
5. Retention is off by default; with a period set, only inactive, unheld, non-student candidates past it are anonymised, in batches.
6. A user without `candidates.erase` gets 403 on the queue; only super_admin changes the period; a candidate reads only their own request.
7. Deactivating a placement officer clears their candidate links and ends their session.
