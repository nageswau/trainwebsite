# hrc-006 — Vacancy co-ownership and assignment history (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-006` (PDF §4.1 "one or more recruiters and placement officers … with a
  primary owner"; §12 "Shared vacancy ownership … Preserve ownership and reassignment history"; PDF `UNVERIFIED`). Scope approved by the
  owner 2026-11-01 (backlog Q-00). Dependency hrc-002 (the `placement_officer` role, `DEC-SCOPE-374`) is merged.
- **Decision:** `DEC-SCOPE-384`. The backlog lists no open question for hrc-006; the owner said to proceed with the recommended answers,
  so O1–O12 are **the builder's calls (`NEEDS_CONFIRMATION`)**.

## Intent

A vacancy has one primary recruiter, optionally one placement-officer owner, and any number of collaborators (recruiters or placement
officers). Every assignee reads and edits the same requirement; only the primary owner or a manager changes who is on it; every change
is kept, with actor and time.

Non-goals: candidate ownership (hrc-012), notifying owners (hrc-032), a placement officer's access to the candidate pipeline, applications,
interviews, offers, shares or revenue (candidate data waits for hrc-012, hrc-002 R3), the employer and legacy job forms.
Anti-goal: an assignee scope that leaks into the candidate-side routes for a role that has none today.

## Builder's calls

- **O1 data model.** The primary stays `jobs.assigned_recruiter_user_id` (a single column, so "exactly one primary" is structural, and
  the ~10 readers — metrics, drill, lifecycle, follow-ups, meetings, legacy — keep working). The new `job_assignments` table holds the
  **other** owners: `(id, job_id, user_id, role ∈ {placement_officer, collaborator}, added_by_user_id, created_at)`, unique `(job_id,
  user_id)`, index `(user_id, job_id)` (the scope join), partial unique `(job_id) WHERE role = 'placement_officer'` (one placement-officer
  owner). This departs from the backlog's "the table holds the primary" on purpose: two places for the primary would drift.
- **O2 history.** `job_assignment_history` (append-only): `(id, job_id, user_id, role ∈ {primary, placement_officer, collaborator}, action
  ∈ {added, removed}, reason ∈ {null, reassign, deactivated, backfill}, changed_by_user_id NULL = the system, created_at)`, index `(job_id,
  created_at)`. Every primary change (create, `/assign`, rec-037 bulk reassign, legacy `/workflows/it/jobs` create) and every owner
  add/remove writes rows in the write's transaction. A primary change is two rows (old removed, new added). Migration `0261_job_assignments`
  backfills one `added primary` row (reason `backfill`, actor NULL, at the job's `created_at`) per job with a recruiter — the backlog's
  "backfilled from `assigned_recruiter_user_id`".
- **O3 who can be an owner.** Collaborator: an active `placement_team` or `placement_officer` user. Placement-officer owner: an active
  `placement_officer`. The target user row is read `FOR SHARE` (an inactive or wrong-role user = 422 "Choose an active recruiter or
  placement officer" / "Choose an active placement officer"). The primary cannot also be a collaborator (409); one role per user per job (409
  "Already an owner of this requirement"); a second placement-officer owner is 409 ("This requirement already has a placement officer
  owner"). The API has no "primary" role: `role: "primary"` is 422, so a second primary cannot be added (AC −); the primary changes only by
  reassignment.
- **O4 scope (the risk).** `caller_scope`:
  - recruiter: today's (primary, or the company's recruiter) **or** an assignee of the job;
  - placement manager: today's (team primary / team company / unassigned) **or** a team member is an assignee;
  - `placement_officer`: **only** where a route opts in (`officers=True`), and then only jobs they are an assignee of. Every other caller
    of `caller_scope` / `load_scoped` (applications, interviews, offers, joinings, revenue, shares, metrics, legacy, matches) keeps
    refusing the role with 403. Opted-in routes: the requirement list, statuses, detail, history, edit, status, submit, the owner routes
    and the JD routes (read and write).
  - super_admin and the company's BDM are unchanged. A non-assignee is 404 (AC2).
- **O5 permissions.** `can_edit` / `can_change_status` / `submit`: recruiters, placement officers (in scope = an assignee) and super_admin.
  New `can_manage_owners`: the primary owner, a placement manager in scope, or super_admin, on a job that is not cancelled. `can_reassign`
  (the primary) stays manager/super_admin only. New `can_view_candidates` = not a placement officer (the web hides Candidates, Shares,
  Revenue and the company link for them).
- **O6 remove.** `DELETE …/assignments/{user_id}` removes a collaborator or the placement-officer owner. Removing the primary (including the
  primary removing themselves) is 409 "A placement manager must reassign the primary owner first" (edge case E). A missing assignment is 404.
- **O7 reassignment.** `/assign` and the rec-037 bulk reassign write the primary history; when the new primary was a collaborator or the
  placement-officer owner, that row is removed (history `removed`, reason `reassign`) so one person never holds two roles.
- **O8 deactivation (AC4).** The rec-037 rule stays: a recruiter who is the primary on open work cannot be deactivated until a manager
  reassigns it (that reassignment moves the primary and records it). On any deactivation, the user's remaining `job_assignments` rows are
  removed (history `removed`, reason `deactivated`, actor = the admin), in the deactivation's transaction, after the user row is locked.
- **O9 concurrency.** Every owner write locks the job row (`load_scoped(lock=True)`) and then the target user `FOR SHARE`, the `/assign`
  order; deactivation locks the user `FOR UPDATE`, so it either sees the new row or the add sees an inactive user. The job lock serialises
  every owner write of one job, so the 409 checks run in order; the unique indexes guard the data itself. Owner writes set `updated_by_user_id` (the row's `updated_at` moves, like `/assign`).
- **O10 audit.** One `AuditLog` row per write, in the same transaction: `recruiter_requirement.owner_added` / `owner_removed` with
  `{user_id, role, changes: {<role label>: [old, new]}}` (names, so hrc-004's history tab shows it). Logs carry ids only.
- **O11 API** (`/recruiter/requirements/{id}`):
  - detail gains `owners: [{user, role, role_label, added_by, added_at}]` (placement officer first, then collaborators by name) and
    `permissions.can_manage_owners`, `permissions.can_view_candidates`;
  - `POST /assignments {user_id, role}` → 201 `{requirement}`; `DELETE /assignments/{user_id}` → 200 `{requirement}`;
  - `GET /assignment-options?role=&q=&limit=` → `{items:[{id, full_name, email, role}], total}` (eligible active users who are not
    already on the job; `can_manage_owners` holders only, else 403);
  - `GET /assignment-history?limit=&offset=` → `{items:[{user, role, role_label, action, reason, changed_by, created_at}], total, limit,
    offset}`, newest first, the requirement's readers.
  Order of checks: role (403) → scope (404) → permission (403) → state (409) → body (422).
- **O12 UI.** The requirement detail gains an **Owners** card after Assignment: the primary, the placement-officer owner and the
  collaborators (name, email, role, "added by X on <date>"); for `can_manage_owners`, a role select (Collaborator / Placement officer owner)
  + searchable person picker + "Add owner", and a "Remove" per non-primary owner behind a confirm. Below, **Ownership history** ("<actor>
  added <person> as Collaborator", time), 20 at a time with "Show more". A placement officer gets a "Job requirements" nav entry (their
  dashboard and `/recruiter/requirements`), sees only their requirements, and the page hides the candidate-side sections.

## Acceptance criteria

1. A collaborator (recruiter or placement officer) sees the requirement in the list and detail, and edits it (PATCH, status, JD).
2. A non-assignee recruiter or placement officer gets 404 on the requirement (and the officer sees none in the list).
3. The ownership history lists every add, remove and primary change with actor and time (including create, `/assign`, bulk reassign,
   deactivation and the backfill).
4. Deactivation: after a manager's bulk reassign moves the primary (history recorded), deactivating the recruiter succeeds and removes
   their collaborator rows (history `deactivated`).
5. + A placement officer is added as co-owner (placement-officer owner). − A second primary is refused (422), a second placement-officer
   owner is refused (409). E: the primary cannot remove themselves (409 until a manager reassigns).
6. Only the primary owner, a manager in scope or super_admin manage owners; a collaborator is 403.
7. A placement officer remains 403 on applications, interviews, offers, matches and the other candidate-side routes.

## Regression risks

`caller_scope` is shared by ~15 modules (O4 keeps the placement officer out of them); rec-007 / rec-037 / rec-038 scope tests (the matrix
gains the four routes and `officer` becomes 200 on the list/statuses and 404 on requirement rows); `test_hrc_002_*` (the officer is no
longer refused the requirement list); the hrc-007 approval and hrc-005 detail output; the detail page's sections for a placement officer.

## Alternatives considered

- **Primary in `job_assignments` too (backlog wording):** every writer of `assigned_recruiter_user_id` would have to keep two copies in
  step; rejected (O1).
- **Add the placement officer to `caller_scope` everywhere:** opens applications, interviews, offers and revenue to a role that has no
  candidate access today (hrc-002 R3); rejected (O4).
- **Reuse `AuditLog` as the history:** the backlog asks for a table and the company side already has one (`CompanyAssignmentHistory`).

## Plan (TDD, small tasks)

1. Model + migration test (red): `JobAssignment`, `JobAssignmentHistory`, frozen role lists, chain, round trip with backfill.
2. API tests (red) `test_hrc_006_co_ownership.py`: add/remove/options/history, scope (collaborator read/write, non-assignee 404, officer
   list), refusals (O3, O6, 403 for a collaborator managing), primary history on create/assign/bulk reassign, deactivation, officer 403 on
   applications/matches.
3. Backend: models, migration `0261_job_assignments`, schemas, `services/recruiter_requirements.py` (scope, permissions, owner functions,
   output), routes, JD routes opt-in, `recruiter_lifecycle`, `admin.update_user`, legacy create.
4. rec-038 matrix rows; hrc-002 officer expectations.
5. Web tests (red): owners panel (list, add, remove confirm, refusals, history paging), officer nav. Then `RequirementOwners.tsx`,
   `lib/recruiterRequirements.ts`, detail wiring, `companyShell`, `navigation.ts`, list page copy.
6. e2e `hrc-006-co-ownership.spec.ts`: a manager adds a placement officer owner and a collaborator; the officer signs in, opens and edits
   the requirement; history shows the changes; mobile layout.
7. Docs: decision register, API contract §12KC, RBAC §2.281, data model, backlog status.
