# hrc-016 — Candidate notes, tasks and a complete timeline (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` hrc-016 (PDF §12 "Activity timeline", "Task assignment", "Internal comments";
  PDF classified `UNVERIFIED`). Scope approved by the owner 2026-11-01 (backlog Q-00). Dependency hrc-012 (`DEC-SCOPE-382`) is merged.
  Decision `DEC-SCOPE-385`.
- **Open question Q-16** (extend `RecruiterFollowUp` or a new table): the owner said to proceed with the recommended answers, so T1–T12
  below are **the builder's calls (`NEEDS_CONFIRMATION`)**.

## Intent
A recruiter has nowhere to write an internal note about a candidate, cannot hand a teammate a candidate task (screen this resume,
coordinate that interview, chase the employer's feedback), and the candidate timeline misses notes, ownership changes, profile edits and
screening. hrc-016 adds private notes, assignable candidate tasks with a "My tasks" list, and those five event kinds on the timeline.

**Non-goals:** editing or deleting notes; push/email reminders beyond the in-app assignment notice (the rec-024 daily lists are the
reminder); employer- or candidate-visible notes; changing rec-024 company follow-ups.
**Anti-goal:** a note's text reaching any candidate, student, employer or public response, a log line or an audit row.

## Rules

**T1 — Q-16: a new table `candidate_tasks`.** `RecruiterFollowUp` belongs to a company's scope (rec-024 FU4) and has no assignee; making
`company_id` nullable would break its scope rule, the per-company cap and its tests. The new table reuses the follow-up shape and its
Today / Overdue / Upcoming views.

**T2 — Notes (`candidate_notes`).** Append-only (the `lead_notes` pattern): author, body 1–2000 characters, created_at. Candidate readers
(`placement_team`, `placement_manager`, `super_admin`, `hr_team`) read them; writers add them. An archived or merged candidate → 409
"Restore this candidate first". Notes are served only by `GET /recruiter/candidates/{id}/notes` and the timeline excerpt — never by the
candidate detail, list, search, shares, employer, student or public routes (AC1, leak tests). Audit `candidate_note.create` carries ids
only; nothing is logged but ids.

**T3 — Tasks.** `task_type` ∈ `follow_up`, `resume_screening`, `interview_coordination`, `employer_feedback`; `title` 1–200; `notes`
≤ 2000 (optional); `due_at` (must be in the future when set or changed, rec-024's `check_due` horizon); `assignee_user_id`; optional link
to one of the candidate's applications (`application_id`, the job is taken from it) or a requirement (`job_id`). An application of another
candidate, or a job that does not match the application → 422. Status `open` → `done` | `cancelled` (stamped with time and user).

**T4 — Assignee.** An active user who can work candidates: `placement_team` with a recruiter profile, `placement_manager` or
`super_admin`. Anyone else (inactive, other role, unknown) → 422 "Choose an active recruiter or manager". +/−/E: a task whose assignee is
later deactivated stays on the candidate, shows "(inactive)" and can be reassigned; it does not block the deactivation.

**T5 — Who changes tasks.** Every candidate writer, on any candidate (R11: the pool is shared). `hr_team` reads only. A done/cancelled
task → 409 on edit, complete or cancel (row lock, so a double complete is a 409).

**T6 — Edit.** `PATCH` an open task's `task_type`, `title`, `notes`, `due_at`, `assignee_user_id`. Equal values are not changes. Audit
`candidate_task.update` with field names.

**T7 — Notice.** `it.candidate.task_assigned` ("Candidate task assigned to you", fixed text) to the assignee on create and reassignment,
never to the actor themselves. Links to `/recruiter/tasks`.

**T8 — My tasks.** `GET /recruiter/candidate-tasks?due=today|overdue|upcoming` — open tasks assigned to the caller (writers; others 403),
oldest due first, IST day boundaries exactly as rec-024 (Today = due before tonight, overdue included), with the three counts.
Page `/recruiter/tasks` ("My Tasks" in the recruiter and manager navs).

**T9 — Timeline (AC3).** The candidate timeline adds:
`note` (excerpt), `task` (`scheduled` / `done` / `cancelled`; type, title, assignee, due), `assignment` (hrc-012 history: owner, placement
officer, collaborator added/removed, from → to), `profile` (the candidate's own audit rows `create`, `update` (field count), `archive`,
`restore`, `merge`, `merged_into`), and `screening` (the `recruiter_application.screening` audit row: result, requirement, company).
Still one paginated `UNION ALL`, two queries. No field names or values beyond the count; no salary.

**T10 — Merge (hrc-014).** Notes and tasks move to the survivor with the other child rows (`moved.notes`, `moved.tasks`).

**T11 — Candidate tasks on the candidate page.** `GET /recruiter/candidates/{id}/tasks` — open first by due, then closed newest first.

**T12 — Numbering.** Migration `0262_candidate_notes_tasks`; API §12KD; RBAC §2.281 (no grant key: the candidate role rule).

## API (§12KD)
- `GET /recruiter/candidates/{id}/notes?limit&offset` → `{items: [{id, body, author: person, created_at}], total, limit, offset}`, newest
  first, `Cache-Control: no-store`; readers.
- `POST /recruiter/candidates/{id}/notes` `{body}` → 201 note; writers; archived 409.
- `GET /recruiter/candidates/{id}/tasks?limit&offset` → page of tasks; readers.
- `POST /recruiter/candidates/{id}/tasks` `{task_type, title, notes?, due_at, assignee_user_id, application_id?, job_id?}` → 201 task.
- `PATCH /recruiter/candidate-tasks/{task_id}`, `POST /recruiter/candidate-tasks/{task_id}/complete`, `…/cancel` → task.
- `GET /recruiter/candidate-tasks?due=` → `{items, total, limit, offset, day, counts}`.
- `GET /recruiter/candidate-tasks/assignees?q=` → `[{id, full_name, role}]` (≤ 20); writers.
- Task: `{id, task_type, title, notes, due_at, status, overdue, assignee: {id, full_name, active}, candidate: {id, candidate_code, name},
  application_id, requirement: {id, code, title} | null, created_by, created_at, completed_at, completed_by, cancelled_at, can_change}`.
- `GET /recruiter/candidates/{id}/timeline` gains kinds `note`, `task`, `assignment`, `profile`, `screening` (additive).

## Frontend
Candidate page: a **Notes** card (list, Add note textarea with counter, "Private — never shown to candidates or employers") and a
**Tasks** card (open/closed list, Add task form: type, title, due, assignee picker, optional application, notes; per open task Done,
Cancel, Edit) above the Timeline; each write bumps the timeline. `/recruiter/tasks`: Today / Overdue / Upcoming tabs with counts, each row
linking to the candidate, Done in place. Loading, empty, error-with-Retry states; errors take focus; buttons disable while sending.

## Security
Notes and tasks are read only through readers' routes; every id in a body is resolved server-side (application of this candidate,
active assignee under FOR SHARE). Audit and logs carry ids and field names, never note or task text.

## Regression risks
rec-027 timeline tests (new kinds only add rows where those sources exist), hrc-014 merge `moved` dict (two new keys), rec-038 matrix (new
routes need rows), the candidate detail page vitest/e2e.
