# ENH-018 — School Activity Feedback — Design

## 1. Problem

`School CRM.md §31` (`ORIGINAL_REQUIREMENT`, `functionalities/edusphere_markdown/School CRM.md:986-1004`):
"After every Edusphere activity: **School Coordinator → Feedback**. Track: Activity, Date, Trainer/Counsellor,
Student participation, School satisfaction, Feedback, Suggestions, Rating." `docs/delivery/ENHANCEMENT_BACKLOG.md:1777`
(`DERIVED_BLUEPRINT`) marks it a gap. Acceptance criterion: *a coordinator submits feedback tied to a specific activity;
Edusphere management can view it.*

A Graphify-oriented investigation (2026-09-23) corrected three backlog assumptions:

1. The backlog says to FK "SCH-004's activity/session entity". SCH-004 has none (`SchoolCareerRecord` is a per-student
   note). The real activity entity is `SchoolActivity` (`school_activities`, `apps/api/app/models.py:1127`, SCH-001).
2. The backlog names `edusphere_school_manager` as viewer. That role has **no RBAC grants** and `RBAC_MATRIX.md:239`
   forbids inventing one; it was deliberately removed from `SCHOOL_DOMAIN_ROLES` (`schools.py:69-77`).
3. `SchoolActivity` has no trainer field and no "Edusphere-delivered" flag; its nullable `activity_type` (DEC-SCOPE-017
   entitlement categories) is the only marker.

## 2. Goals and non-goals

**Goals.** A coordinator records one structured feedback per completed Edusphere activity of their own school; the
school's principal can read it; Edusphere admins read all schools' feedback.

**Non-goals.** No change to how activities are created, listed or attended. No feedback on ENH-011 skill sessions or on
untyped school events. No edit/delete of submitted feedback. No `edusphere_school_manager` grants. No aggregate
feedback analytics (ENH-016's dashboards may later read this table). No new rate limiter (none exists anywhere in the
codebase; one write per activity bounds this endpoint).

## 3. Decisions confirmed in-session (2026-09-23)

| # | Decision |
|---|---|
| D1 | Feedback applies only to `SchoolActivity` rows with `activity_type` set (career_seminar, career_awareness_session, parent_orientation, campus_visit). |
| D2 | Viewers: `overseas_admin` + `super_admin` (the existing cross-school pair, `admin.py:1134`). No RBAC change. |
| D3 | Trainer/Counsellor is optional free text on the feedback (max 200). |
| D4 | Student participation is computed at read time from `SchoolActivityAttendance` (`present` of `marked`), never stored. |
| D5 | One feedback per activity; a second submit is `409`. Immutable once submitted. |
| D6 | `rating` and `satisfaction` are separate required integers 1–5. |
| D7 | Submission only once `scheduled_at <= now` (the table has no "completed" status). |
| D8 | `school_principal` reads their own school's feedback (read-only). |
| D9 | New module `apps/api/app/api/school_feedback.py` with a `/school` router and an `/overseas-admin` router — the ENH-005 `school_transfers.py` shape — so `schools.py`/`admin.py` do not grow. |

## 4. Data model

New table `school_activity_feedback` (migration `0039_school_activity_feedback`, down `0038_portfolio`; create-only,
`downgrade()` drops it; no existing table altered, no existing row read or written):

| column | type | rule |
|---|---|---|
| id | UUID PK | |
| activity_id | UUID FK `school_activities.id` | `uq_activity_feedback_activity` UNIQUE (D5, race-safe) |
| school_id | UUID FK `schools.id` | indexed; copied from the activity server-side |
| submitted_by_user_id | UUID FK `users.id` | from the session |
| trainer_name | String(200) NULL | |
| rating | Integer | `ck_activity_feedback_rating` 1–5 |
| satisfaction | Integer | `ck_activity_feedback_satisfaction` 1–5 |
| feedback | Text | required |
| suggestions | Text NULL | |
| created_at / updated_at | TimestampMixin | `created_at` is the submission time; indexed for newest-first |

`SchoolActivity` has no delete/update endpoint, so the FK cannot dangle and D1/D7 eligibility cannot change after submit.

## 5. API (all new; no existing contract changes)

Conventions kept: snake_case, `{"detail": ...}` errors, `limit` (1–100, default 25) / `offset` paging with
`{items, total, limit, offset}` (ENH-005's page shape). `detail` strings are module constants (a client may match them).

### 5.1 `POST /api/v1/school/activities/{activity_id}/feedback` → 201 `ActivityFeedbackOut`

Body `ActivityFeedbackCreate` (`extra="forbid"`): `rating` int 1–5, `satisfaction` int 1–5, `feedback` required ≤5000,
`suggestions` optional ≤5000, `trainer_name` optional ≤200 single-line. Text is cleaned with the house rule
(`clean_free_text`: trim, blank→None, reject NUL/bidi overrides/control chars, keep newlines for textareas).

Check order: 401 no session → 403 not coordinator / unlinked (`_require_coordinator_user`, resolved before body
validation) → 422 body → 404 `Activity not found` (loaded `WHERE id AND school_id = own`; another school's activity is
indistinguishable from a missing one) → 422 `Feedback is only collected for Edusphere activities` (no type) → 422
`Feedback opens once the activity has taken place` (future) → 409 `Feedback has already been submitted for this activity`.

Transaction: insert feedback + `AuditLog(action="school.activity_feedback_submit", entity_type="school_activity",
metadata={school_id, feedback_id, rating, satisfaction, request_id})` → one commit. `IntegrityError` → rollback → 409.
No pre-check SELECT: the unique constraint picks the winner, so concurrent submits yield exactly one 201.
A retry after a lost response gets 409; the UI then reloads and shows the stored feedback.

### 5.2 `GET /api/v1/school/activity-feedback?status=all|awaiting|submitted&limit&offset` → `SchoolFeedbackPage`

Roles `school_coordinator`, `school_principal`; school from `_own_school_id(user)`. Items: eligible activities (typed,
`scheduled_at <= now`) of that school, `scheduled_at` desc, each
`{activity_id, title, activity_type, scheduled_at, participation{present, marked}, feedback: ActivityFeedbackOut|null}`.

### 5.3 `GET /api/v1/overseas-admin/school-activity-feedback?school_id&limit&offset` → `AdminFeedbackPage`

Roles `overseas_admin`, `super_admin` (403 otherwise, as a dependency). Submitted feedback across schools, newest
submission first; item = `ActivityFeedbackOut` + `school_id, school_name, activity_title, activity_type, scheduled_at,
participation`. `school_id` is a typed UUID (malformed → 422; unknown → empty page).

`ActivityFeedbackOut`: `id, activity_id, trainer_name, rating, satisfaction, feedback, suggestions, submitted_by_name,
submitted_at`. Submitter email is never returned.

### 5.4 Queries

Each list: one count + one page query (joins activity/school/user), plus one grouped attendance query over the page's
activity IDs (`count(*)`, `count(*) FILTER (present)`). No per-row queries.

### 5.5 Logging

`logger = get_logger("app.school.feedback")`. `activity_feedback_submitted` (info) and `activity_feedback_duplicate`
(info) with IDs only; `activity_feedback_rejected` (info) with the reason token. Free text is never logged or audited.

## 6. Security

| Concern | Treatment |
|---|---|
| AuthN / session | Existing httpOnly SameSite=Lax cookie via `get_current_user`; unchanged. |
| AuthZ | Server-side on every route; principal has no write route; admin route is a 403 dependency. |
| IDOR | Activity loaded jointly with the caller's school → 404; reads filtered by own school. `school_id`/`submitted_by` never from input; `extra="forbid"` rejects them. |
| Role escalation | No role writes; no client-supplied role trusted. |
| Validation | Pydantic ranges/lengths + house text cleaning + DB CHECKs. |
| XSS | React text rendering only, `white-space: pre-wrap`; no `dangerouslySetInnerHTML`. |
| CSRF | Unchanged posture: SameSite=Lax + JSON-only POST + CORS pinned to `frontend_url`. |
| SQLi | ORM with bound parameters only. |
| Secrets | None introduced. |
| Logs / PII | IDs and scores only. Form help text asks not to include student personal details (students are minors). |
| Rate limiting | Not added (none exists; one write per activity). Recorded as a pre-existing gap. |
| Audit | One `AuditLog` row per accepted submission, in the same transaction. |

## 7. Frontend

Reuse: `PortalShell`, `serverApi`, `accessUnavailable`/`accessDenied`, `loading.tsx` skeleton (ENH-011),
`.card/.table-wrap/.table/.form/.field/.form-grid/.form-message/.form-error/.badge/.btn`, ENH-005's
`role=status`/`role=alert` focus pattern and "Showing X of Y" paging.

1. **`/school/coordinator/feedback`, `/school/principal/feedback`** — new `SCHOOL_NAV` entries; both render
   `SchoolActivityFeedbackPanel` (`canSubmit` true for coordinator only). Status filter select; a `.link-list` (the
   ENH-005 list, which reflows on a phone, rather than a table) whose rows show Activity, type, Date, Participation
   ("N of M present" / "Not marked"), Status (text badge "Awaiting feedback"/"Submitted") and the action. Submitted
   feedback expands via native `<details><summary>`.
2. **`ActivityFeedbackForm`** — inline `.action-card` below the table (the attendance pattern). Rating and satisfaction:
   `<fieldset><legend>` with five native radios labelled "1 – Poor … 5 – Excellent". Trainer/Counsellor input
   (maxLength 200); Feedback (required) and Suggestions textareas (maxLength 5000); privacy help text. Focus moves to the
   form heading on open and back to the trigger on cancel. Submit disabled + "Saving…" while pending; on error values are
   kept and a `role=alert` message is focused; on 409 a message is shown and the list refreshes; on success a
   `role=status` message and `router.refresh()`.
3. **`/overseas/admin/activity-feedback`** — static page (wins over `[section]`), role-checked like ENH-005's
   `school-transfers/page.tsx`; nav entry added to `PORTAL_NAV["overseas/admin"]`. `AdminActivityFeedbackPanel`: school
   filter from existing `GET /overseas-admin/schools`; each feedback as a card with a `<dl>` (reflows at 640px); "Load
   more"; inline retry on fetch error.
4. **`SchoolActivitiesPanel`** — one additive link, "Give feedback", on typed past rows → `/school/coordinator/feedback`.
   Its fetch and props are unchanged except reading the already-returned `activity_type`.

States: loading (skeleton `loading.tsx`), page-load failure (`accessUnavailable`), fetch failure (inline alert + Retry),
empty ("No completed Edusphere activities yet…" + link to Activities; "Nothing awaiting feedback"; admin "No feedback
submitted yet").

## 8. Acceptance criteria

- AC1 Coordinator submits feedback (all §31 fields) on a past typed activity of their school → 201, row stored, audit row written.
- AC2 Another school's / nonexistent activity → 404; untyped → 422; future → 422; invalid body → 422.
- AC3 Second submit → 409; two concurrent submits → exactly one 201 and one 409, one row.
- AC4 Non-coordinator POST (principal, teacher, parent, admin) → 403.
- AC5 Coordinator and principal list their own school's eligible activities with participation and feedback; other schools' never appear; status filter works.
- AC6 `overseas_admin`/`super_admin` list all schools' submitted feedback, filterable by school, paged; every other role → 403.
- AC7 Existing `/school/activities`, attendance, dashboard, reports, entitlements, parent overview and timeline responses are byte-for-byte unchanged in shape.
- AC8 UI: coordinator submits from the Feedback page; principal sees read-only; admin sees the cross-school list; loading/empty/error states render; keyboard-only submission works; layout works at 320px.

## 9. Tests (written before code, per task)

- **Model/migration (no DB):** table shape, unique + checks, offline-rendered migration creates only the new table, downgrade drops only it (ENH-011 pattern).
- **Schemas (no DB):** ranges, required/optional, trimming, blank→None, control/bidi rejection, `extra` rejection.
- **API (Postgres):** AC1–AC6 incl. principal read-only, IDOR, concurrency via two sessions (ENH-005 concurrency pattern), audit row content has no free text, participation counts, paging/filter.
- **Regression:** existing `test_sch_001`, `test_sch_007`, `test_sch_008`, `test_sch_011`, `test_sch_reports` unchanged and green.
- **Component (vitest):** form validation/states/focus, panel empty/awaiting/submitted/principal read-only, admin panel paging/error/retry.
- **Playwright:** coordinator submits → principal reads → admin reads; duplicate blocked; keyboard path.

## 10. Regression risks

| Area | Risk | Mitigation |
|---|---|---|
| Existing activity readers (dashboard, reports, entitlements, parent, timeline) | None structurally — no change to `school_activities` | Rerun their suites |
| Migration chain | Second head if another branch adds `0039` | Single-head check; renumber on merge (ENH-012 precedent) |
| `SchoolActivitiesPanel` | New link only | Existing sch-001 e2e + component test |
| Nav arrays | New entries shift nav order | Existing PortalShell tests |
