# nehn-039 — School portal: document statuses, application depth, bulk-upload reconfirmation (design)

**Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-039` (§21 L561-577, §26 L804-809, actions 18/19;
`UNVERIFIED` backlog). Client input CI-05 / OD-13 is still open, so every choice below is a **builder's default**
(owner pre-authorised recommended answers) and stays `NEEDS_CONFIRMATION`. Dependency `nehn-003` is done; documents themselves
are NOT made viewable, so nothing here depends on file access.

## Why

School representatives can see their students, progress and the high-level Global Education stage, but not whether the
documents an overseas application needs (passport, transcripts, English test…) are in order. A principal wants to answer
"whose passport is verified?" without phoning the counselor. Minors' data: the projection must be minimal and audited.

## What exists (discovery)

- 4 school roles on the shared login, scoped by `profile.school_id` (`schools.py` `_own_school_id`, `_load_readable_student`:
  coordinator/principal own school, teacher assigned students, parent linked children).
- A school-bridged application (`overseas_applications.school_student_id`) can carry a ccrm-019 document checklist
  (`application_checklist_items`: type, label, required, counselor `mark`, linked documents). `student_documents` cannot be owned by
  a school student (owner check), so for a bridged application the item status is the counselor's mark, or `missing`.
- No school-side read of any document or checklist status.
- Bulk roster upload is built (`POST /school/students/bulk-upload`, coordinator only) although `DEC-SCOPE-009` deferred it.

## Builder's defaults (D1–D7, `NEEDS_CONFIRMATION`)

- **D1 Login.** The existing four school roles on the shared login are the "dedicated institution login"; no branded
  `/school/login` route is added.
- **D2 What is shown.** Statuses only — per bridged application, each checklist item's name, required flag and status
  (`app.application_checklists.item_status`, labelled). Never files, filenames, document ids, notes, marks' authors or reviewer
  notes.
- **D3 Allowed types.** Every checklist item except the financial class (ccrm-022 SD1: the higher of the item's stored
  sensitivity and `type_sensitivity(type, label)`). Identity (passport) stays visible — the backlog's positive scenario.
- **D4 Who.** All four school roles, each through the existing reader scope (teacher: assigned only; parent: linked children only).
  Any student outside that scope — another school, a transferred-out student, an unassigned/unlinked one, or a missing id — is
  **404** (AC2; no existence leak). A non-school role is 403.
- **D5 Application depth.** Unchanged: university, stage and visa stage stay as the overview already shows them; the new read
  adds only the university name as the grouping label. No intake, dates, references or notes.
- **D6 Audit.** Each successful read writes one `AuditLog` row `school.document_statuses_view` (student id, application and item
  counts; no types or statuses). Refusals are logged.
- **D7 Bulk upload.** Keep it as built, coordinator only; recorded as a decision that supersedes `DEC-SCOPE-009`'s deferral.

## Interface

`GET /api/v1/school/students/{student_id}/document-statuses` (read-only, no pagination — a student has a handful of applications)

```json
{"student_id": "…", "applications": [
  {"application_id": "…", "university_name": "…", "has_checklist": true,
   "items": [{"name": "Passport", "required": true, "status": "verified", "status_label": "Verified"}]}]}
```

Applications newest first (as the overview); items in checklist order. An application with no checklist has
`has_checklist: false, items: []`.

## UI

`SchoolDocumentStatusesCard` (server component, FundingRecordsCard pattern) on the coordinator, principal, teacher and parent
student pages: loading via the page's own parallel read with `.catch(() => null)` (null → "couldn't be loaded"), empty states
("No overseas applications linked yet." / "No document checklist yet."), a table per application with Document / Required /
Status pill (complete → green, needs action → error, else pending), and a note that financial documents are not shown.

## Non-goals

No document download, no school-side review/upload, no new tables or migration, no change to existing endpoints.

## Tests

API: per-role happy path, financial item hidden, other-school/teacher-unassigned/parent-unlinked/missing → 404, non-school
role → 403, transferred student (old school 404, new school 200), no-checklist and no-application shapes, audit row written,
no sensitive keys in the body. Web: card states (null / empty / items / no checklist). E2E: coordinator sees the statuses.
