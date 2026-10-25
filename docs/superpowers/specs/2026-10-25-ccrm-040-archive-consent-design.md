# ccrm-040 — Archive instead of delete; overseas consent capture — design

Backlog: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` § `ccrm-040` (spec §2 "prefer archive/withdrawn statuses", §16 consent and
communication preferences). Dependency `ccrm-008` merged (PR #314). Numbers: migration `0193_student_archive_consent`,
`DEC-SCOPE-275`, API §12GB, RBAC §2.189 (recheck at merge: ccrm-038 runs in parallel).

The owner asked for the session to proceed on recommended answers, so every rule below is a default marked `NEEDS_CONFIRMATION`.

## Existing behaviour (verified on main @ cdc5b25d)

- No route deletes an overseas student or application, and none archives them. The agency has its own student archive
  (`AgentStudent.status = 'archived'`, AGN-008 A15: archived → read-only, "Unarchive this student first" → 409).
- `ConsentRecord` (STU-009) is insert-only, unique per (user, agreement), with IP; `Agreement` rows have a `division` only. The IT
  enrolment agreement is `division='it'`. Nothing exists for overseas.
- Communication preferences already exist for every user: `NotificationPreference` (WhatsApp/SMS opt-in, ENH-014), edited on
  `/account/profile`, honoured by `queue_deliveries` — which ccrm-030's reminders use. ccrm-037 is not built; it will use the same
  dispatcher. So "communication preferences honoured" needs no new mechanism; the consent card links to the existing page.

## Archive rules

- **AR1 — who:** the student's csc-001 counselor (`OverseasStudentCounselor`) or the Overseas Admin archives; **only the Overseas
  Admin restores**. A counselor who only has applications for the student but is not their counselor → 403. Out of csc-001 scope → 404
  (`student_profiles.staff_student`, the 360's gate).
- **AR2 — only a finished caseload:** archiving is refused (409, listing the APP- codes) while the student has an **open**
  application (not closed by an outcome and not enrolled — the 360's `open` rule), direct or agency. Withdraw or close them first.
  So archiving never hides live work, reminders (ccrm-030 RM5) already skip every remaining application, and no application write
  route needs a new guard.
- **AR3 — reason required:** 3–500 characters, kept on the archive row and in the audit metadata (as ccrm-033).
- **AR4 — storage:** a table `overseas_student_archives` (one row per archived student: who, when, reason). The student's applications
  are archived **with** the student (derived: an application whose student has a row), so there is no per-application flag to keep in
  sync. Restore deletes the row; the audit log (`overseas.student.archive` / `overseas.student.restore`) keeps the history, shown on
  the 360 History tab.
- **AR5 — what archive hides:** the counselor's and Overseas Admin's portal application sections (dashboard, students,
  applications, documents, visa … — the shared query), the counselor's linked-students list (`GET /counselor/students`) and the
  staff student picker (`GET /lookups/overseas-students` for counselor/admin). The 360 stays readable with an "Archived" banner. The
  university_rep and agency views are unchanged. Management reports are unchanged (history must still count).
- **AR6 — what archive blocks:** creating a new application for an archived student (any role, `POST
  /workflows/overseas/applications`) → 409 "This student is archived. The Overseas Admin can restore them." Nothing else is blocked; the
  student's login is **not** touched (deactivation stays a separate admin action).
- **AR7 — lists and notices:** `GET /counselor/students/archived` lists archived students (admin: all; counselor: their own linked
  students), newest first, paged. Page `/overseas/{admin|counselor}/archived-students`, linked from the nav. When the Admin archives or
  restores, the student's counselor gets an in-app notice (+ queued channels).

## Consent rules

- **CN1 — two consents:** `data_processing` and `document_sharing` (sharing documents with universities, visa authorities and partners
  for the student's applications). Stored as `Agreement` rows (`division='overseas'`, new column `kind`), version `v1`, seeded by the
  migration. The text is a placeholder for legal review (`NEEDS_CONFIRMATION`). Existing IT rows get `kind='enrolment'`.
- **CN2 — captured from the student at first login:** the overseas student dashboard leads with a consent card until both current
  consents are accepted. The counselor cannot consent on the student's behalf (consent belongs to the data subject); conversion
  (ccrm-008) therefore does not record consent. Not blocking: the rest of the portal works.
- **CN3 — record:** `POST /overseas/me/consents/{agreement_id}/accept` inserts a `ConsentRecord` (user, agreement, version, IP) once;
  repeating is a no-op 200 with the original time. Audited `overseas_consent.accept` (entity = the student, metadata kind + version).
- **CN4 — staff view:** the 360 Overview shows each consent as Given (date, version) or Not yet given. Missing consent blocks nothing
  (`NEEDS_CONFIRMATION`).
- **CN5 — new version:** a newer active agreement of the same kind replaces the old one as "current"; the student is asked again.
- **CN6 — out of scope:** withdrawing consent (handled by the existing data-subject request route), retention periods (PRD open items
  15 and 85), lead `marketing_opt_in` enforcement (ccrm-005's field; no lead messaging change here).

## API (§12GB)

| Method | Path | Who |
| --- | --- | --- |
| POST | `/counselor/students/{id}/archive` `{reason}` → 200 archive | csc-001 counselor, Overseas Admin |
| POST | `/counselor/students/{id}/restore` → 200 | Overseas Admin |
| GET | `/counselor/students/archived?limit&offset` | overseas counselor (own), Overseas Admin (all) |
| GET | `/overseas/me/consents` | overseas_student |
| POST | `/overseas/me/consents/{agreement_id}/accept` → 201 first / 200 repeat | overseas_student |

`GET /counselor/students/{id}/overview` gains `archive` (null or `{archived_at, archived_by, reason}`), `consents` and
`permissions: {archive, restore}`.

## Frontend

- 360 Overview: an "Archived" banner (with Restore for the Admin) or an "Archive student" disclosure with a reason field (counselor
  linked / Admin); a Consent card. Errors shown inline (`role="alert"`), button disabled while saving, `router.refresh()` after.
- Overseas student dashboard: `OverseasConsentCard` (both checkboxes + Accept, link to notification preferences).
- `ArchivedStudentsPage` for both portals; nav item "Archived students".

## Tests

Backend `tests/test_ccrm_040_archive_consent.py` (rules AR1–AR7, CN1–CN5) + `tests/test_ccrm_040_migration.py`; regression: ccrm-009,
csc-002 list, lookups picker, application create, IT agreement (stu-009). Frontend vitest for the consent card and archive panel;
Playwright `ccrm-040-archive-consent.spec.ts`.

## Plan

1. Migration 0191 + models (`OverseasStudentArchive`, `Agreement.kind`) + migration test.
2. `services/student_archive.py` + routes (archive, restore, archived list) — TDD.
3. Exclusions: portal query, linked list, picker, application create — TDD.
4. `services/overseas_consents.py` + `/overseas/me/consents` routes; overview `archive`/`consents`/`permissions`; history labels — TDD.
5. Web: types/lib, 360 archive + consent cards, consent card on the student dashboard, archived students page + nav; vitest.
6. Docs: DEC-SCOPE-275, API §12GB, RBAC §2.189, RTM, backlog status.
