# itc-033 — Call consent, retention policy and resume malware scan — Design

**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` `itc-033` (PDF §10 consent / retention / DPDP, §5 "scan uploads for malware
where supported"; PDF classified `UNVERIFIED`). Backlog Q-23 (scanner) and Q-31 (retention periods, backup owner). Scope approved
by the owner 2026-11-01 (backlog Q-01: all phases, built in waves). Dependency itc-026 merged (PR #424, `DEC-SCOPE-350`).
The owner said to proceed with the recommended answers, so every call below is **the builder's call (`NEEDS_CONFIRMATION`)**.

## Intent
PDF §10 asks for consent and communication preferences for calls, email, SMS and WhatsApp, retention rules and a backup process
under the DPDP Act 2023, and §5 asks for an upload malware scan where supported. WhatsApp/SMS opt-in (ENH-014) exists; calls do not.
Retention has only a hold rule. Uploads are never scanned. Backups rely on the provider.

## Decisions (builder's calls)
- **C1 — Call preference (calls).** `notification_preferences` gains `calls_opt_out` (default false) and `calls_opted_out_at`.
  Calls are allowed unless the user says otherwise: a student or staff member who gave a phone number for their course is already
  contacted by phone, so a default-off opt-in would silently forbid existing service calls. No row = calls allowed.
  Turning calls off or on needs no valid phone (it is a permission, not a delivery channel).
- **C2 — API.** `GET/PUT /account/notification-preferences` stays self-only. The response gains `calls: bool` (true = allowed).
  The body gains an **optional** `calls` (StrictBool); omitted = unchanged, so an older client sending only `{whatsapp, sms}` keeps
  working. Extra fields are still 422. The audit row `notification_preference.update` carries `calls` in before/after.
  The data export (`/account/export`) adds `calls` and `calls_opted_out_at`.
- **C3 — Who sees it.** The IT student record (itc-012) shows the student's counselor (itc-003) and the IT Admin "Phone calls: the
  student has asked not to be called" when opted out. Read-only; staff cannot change it (D4 of ENH-014: nobody sets another's consent).
- **C4 — Leads are not changed.** The lead already has ccrm-005 `contact_preference` and `marketing_opt_in`. A lead-level
  do-not-call block would change telecaller calling rules (the backlog's named regression risk), so it is **deferred**
  (`NEEDS_CONFIRMATION`). Telecaller calling is unchanged.
- **C5 — Malware scan (Q-23).** A scan hook on itc-026 resume uploads, **off unless `CLAMAV_HOST` is set** ("where supported").
  When set, the spooled upload is streamed to clamd (`INSTREAM`, TCP `CLAMAV_PORT`, default 3310) **before** it is stored, after the
  size/type checks. `FOUND` → 422 "The file failed a virus scan and was not uploaded" + audit `it.resume.scan_rejected` (ids, type,
  size, signature name; no file name). Scanner unreachable, timeout or error → **fail closed** 503 "Virus scanning is unavailable;
  please try again later" (logged `malware_scan_unavailable`). Synchronous, not async quarantine: a resume is at most 10 MB, it keeps
  one code path and no new "pending" state. The ClamAV container itself is a DEC-INFRA follow-up (not added to compose here).
- **C6 — Retention (Q-31).** `docs/architecture/DATA_RETENTION_POLICY.md`: data categories, where each lives, the existing hold
  rule, **proposed** periods all marked `NEEDS_CONFIRMATION`, and the erasure route that exists (data-subject requests). **No purge
  job**: deleting personal data is irreversible and needs legal sign-off on periods first (as `DEC-PRIV-001`, rec-009 Q-09).
- **C7 — Backups.** The same document lists the backup facts (DO Managed PG provider backups; the uploads Volume snapshot schedule
  **unverified**) and an owner checklist. No code.

## Non-goals
Purge job, lead do-not-call, scanning other upload routes (profile documents, career uploads, payment proofs), a ClamAV container,
quarantine states.

## Acceptance criteria
1. A user's preferences read `calls: true` by default; PUT `{whatsapp, sms, calls:false}` stores the opt-out with a timestamp and
   reads back `calls:false`; PUT `{whatsapp, sms}` leaves `calls` unchanged.
2. Turning calls on/off works without a valid phone; WhatsApp/SMS rules are unchanged.
3. The audit row's before/after includes `calls`; no row when nothing changed.
4. The export includes `calls` and `calls_opted_out_at`.
5. The IT student record shows the opt-out to the linked counselor and the IT Admin (the API's `student.calls_allowed`, also on the
   student's own read, which shows their own value; the student's page is unchanged).
6. The profile page form has a "Phone calls from our team" checkbox saved with the same button.
7. With `CLAMAV_HOST` unset, resume uploads behave exactly as itc-026.
8. With a scanner: clean → 201; infected → 422 + audit row, nothing stored; unreachable → 503, nothing stored.
9. The retention policy document exists, marks every period `NEEDS_CONFIRMATION`, and lists the backup checklist.

## Risks
enh-014 exact-equality tests (updated for the additive key), the enh-014 e2e, the itc-026 upload tests (scan off by default).
