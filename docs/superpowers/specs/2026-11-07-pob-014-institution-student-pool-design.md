# pob-014 — Institution-supplied student pool with permission tracking (design)

- **Feature:** `pob-014` (`docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md`), decision `DEC-SCOPE-425`.
- **Source:** backlog §6.1 student data, §6.2 "collect authorised student data", the privacy note ("only with appropriate authority,
  notice and consent … restrict access … according to the institution agreement"), §17 "import college/TPO candidate data only through
  authorised files … preserving source and permission details". Source classified `UNVERIFIED`.
- **Authority:** the owner assigned pob-014 on 2026-11-07 and said to proceed with the recommended answers, so S1–S14 below are **the
  builder's calls (`NEEDS_CONFIRMATION`)** answering Q-11. Dependencies pob-013 (`DEC-SCOPE-410`), hrc-013 (`DEC-SCOPE-391`), hrc-014
  (`DEC-SCOPE-377`) and hrc-019 (`DEC-SCOPE-399`) are merged.

## Intent

A college hands the placement team a list of its students under an agreement that says who may use the data, for what, and until when.
pob-014 imports that list into the candidate master through the hrc-013 import, stamps every new student with the college and the
permission record, and makes those students visible **only** to the people the agreement names while it is in force.

## Goals / non-goals

- AC1 an imported list carries its source and permission. AC2 a user outside the agreement cannot see those candidates (404).
  AC3 once the permission expires, a candidate is hidden and not shareable.
- Also: search by institution; the pool view filters by batch (pass-out year) and course; a placement status per student from applications.
- Non-goals: vacancy sharing with the institution and campus outcomes (pob-015); student logins (hrc-022); editing a student's notice
  status after import; a per-row purpose.
- Anti-goals: an institution student leaking through any list, search, count, duplicate panel or report to someone outside the agreement;
  changing an existing candidate because a college list mentions them (hrc-013 I7).

## Builder's calls (`NEEDS_CONFIRMATION`)

- **S1 Permission record.** `institution_data_permissions`: the college (a pob-013 college), an optional MoU (one of the college's
  `bdm_mous`), agreement reference (required, ≤ 100), permitted purposes (≥ 1 of `placement`, `internship`, `training`, `campus_drive`),
  valid from / expires on (dates, expires ≥ from), notes ≤ 500, creator, revoked at/by.
- **S2 Active** = not revoked and `valid_from ≤ today (IST) ≤ expires_on`. Expiry needs no job: it is evaluated in every query.
- **S3 Who is permitted.** Each permission lists its users explicitly (`institution_data_permission_users`). Only users with a candidate
  reader role (`placement_team`, `placement_manager`, `hr_team`, `super_admin`) who are active can be listed. **No role bypasses the list**,
  `super_admin` included: the agreement names people.
- **S4 Who manages permissions.** `placement_manager` and `super_admin` (in their pob-013 college scope) create, edit (expiry, purposes,
  users, notes) and revoke. A revoke is final. Every write is audited (`institution_permission.*`, ids and field names only).
- **S5 Candidate columns.** `institution_org_id`, `institution_permission_id`, `institution_notice_status` (`notice_sent` | `consented`).
- **S6 Visibility (AC2/AC3).** A candidate with a permission is in the pool only for a viewer listed on that permission while it is
  active. `candidates.pool_filter(viewer_id)` gains the predicate; with no viewer it **fails closed** (institution students are hidden).
  Recruiter routes pass the caller; system reads (talent-pool counts, dashboards, insights, matching, the duplicate queue, merge) do not,
  so they never show these students. Out of scope = 404 on every candidate route, absent from lists and search, 422 "not in the pool" on
  share and apply.
- **S7 Import.** The hrc-013 preview and commit take an optional `institution_permission_id` and, with it, a required `notice_status`.
  The caller must hold `candidates.import` and be listed on an **active** permission (else 404 "Permission not found"). Each created row
  gets the college, the permission and the notice status (and `college` = the college's name when the cell is empty). A matched row is
  unchanged (I7); when the matched candidate is invisible to the importer the report names no one ("Already a candidate (restricted
  record)"). The batch keeps the permission (AC1); a replay with another permission under the same key is 422.
- **S8 Duplicate panel.** `find_matches` never names an institution student (the panels have no viewer, so permitted people see the
  redaction too): name "Restricted record", no id or code. The block itself still holds.
- **S9 Sharing (AC3).** A share needs every institution student to be visible to the sharer (expired = 422) **and** their permission to
  include `placement` (purpose limitation, 422 otherwise). Shares are already audited per candidate (`profile_share.create`).
- **S10 Pool view.** `GET /recruiter/colleges/{org_id}/student-pool` (pob-013 readers): the permissions the caller may see (managers:
  all of the college's; others: those they are listed on) with status and student counts, and a page of the visible students filtered by
  permission, pass-out year, course (qualification) and name/code; each with its latest application status as the placement status
  ("Not applied" when none).
- **S11 Search.** `GET /recruiter/candidates?institution_id=` (exact college). The hrc-019 skill search requires a skill or resume
  text, which an imported student does not have, so the filter lives on the candidate list. Batch filtering lives in the pool view.
- **S12 Existing EduSphere student** (edge case): matched and left unchanged with its own consent; recording a second consent is
  `NEEDS_CONFIRMATION`.
- **S13 Performance.** Partial index on `candidates.institution_permission_id` (not null); permission users keyed
  `(permission_id, user_id)` plus an index on `user_id` (the visibility sub-select starts from the viewer).
- **S14 Placement roles.** As pob-013 P15: `placement_officer` is not granted.

## API (`/api/v1`, §12LR)

| Method | Path | Who |
|---|---|---|
| GET | `/recruiter/colleges/{org_id}/student-pool` | pob-013 readers |
| POST | `/recruiter/colleges/{org_id}/data-permissions` | placement_manager, super_admin |
| PATCH | `/recruiter/colleges/{org_id}/data-permissions/{permission_id}` | placement_manager, super_admin |
| POST | `/recruiter/colleges/{org_id}/data-permissions/{permission_id}/revoke` | placement_manager, super_admin |
| POST | `/recruiter/candidate-imports[/preview]` | + form `institution_permission_id`, `notice_status` |
| GET | `/recruiter/candidates` | + `institution_id` |

## Data (migration `0306_institution_student_pool`, guarded, additive)

Two tables; three nullable columns on `candidates`; one on `candidate_import_batches`. FKs `ON DELETE RESTRICT`. Downgrade drops them.

## Web

- `InstitutionStudentPool` on `/recruiter/colleges/[id]`: permissions (manager form to add/extend/revoke), the student table with
  filters, loading/empty/error states, and "Import students" → `/recruiter/candidates/import?permission=<id>`.
- The import wizard shows the chosen permission and asks for the notice status.

## Tests

API: AC1–AC3, the fail-closed paths (list, search, detail, notes, duplicate panel, share, apply, talent-pool count), manager-only
permission writes and their validation, the import report redaction, migration guard, rec-038 matrix rows. Web: vitest for the pool
section and the import wizard's permission mode; a Playwright spec for import → pool → outsider 404.
