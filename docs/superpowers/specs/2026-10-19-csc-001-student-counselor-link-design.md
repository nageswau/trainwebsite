# csc-001 — Student → counselor link (design)

`DEC-SCOPE-226`, migration `0165_overseas_student_counselors`, RBAC `2.148`. Backlog: `docs/delivery/COUNSELOR_WALKIN_BACKLOG.md` §3.
Owner answers W1 (Overseas `counselor` only) and W3 (a new student→counselor link; application-based scoping unchanged).

## Intent

A walk-in student the counselor creates (csc-002) must stay in that counselor's caseload before any application exists. Today a
counselor reaches a student only through `OverseasApplication.counselor_id`, so a student with no application is unreachable.

## What changes

1. **Table `overseas_student_counselors`** (model `OverseasStudentCounselor`): `id`, `student_user_id` (FK `users`, **unique** —
   one counselor per student), `counselor_user_id` (FK `users`, indexed), `assigned_by_user_id` (FK `users`), `created_at`,
   `updated_at`. Additive; no existing row changes. Nothing writes it in csc-001 — csc-002 (create) and csc-005 (reassign) do.
2. **One scope, `services/counselor_students.py`:** `visible_student_ids(counselor)` = students of the counselor's own applications
   **∪** students linked to the counselor; `is_visible_student(db, counselor, student_id)`.
3. **The two places that use it:**
   - `GET /lookups/overseas-students`, counselor branch (`api/lookups.py`) — the picker.
   - `POST /workflows/overseas/appointments`, counselor check (`api/workflows.py`) — the write that picker feeds. ENH-031 §5: a picker
     never offers a value its write would refuse, so both move together.

Response shapes, status codes and error texts are unchanged.

## Backlog deviation (recorded, builder's call)

The backlog's AC said "the create-application picker". Verified on main @1e90f32e: a counselor has **no** create-application UI
(`OverseasApplyPanel` is student-only); the counselor's only `overseas-students` picker is *Schedule appointment*
(`WorkflowPanel.tsx` `appointmentSpec(true)`). `POST /workflows/overseas/applications` already accepts any overseas student from a
counselor, so it needs no change.

## Not changed (SHOULD NOT CHANGE)

Application-level scopes (`portal.py` counselor sections, `application_filters`, `inbound`, `university_view`, `admin.py` school
applications), document add/verify/download (`workflows.py`), counselor chat, the agent and admin lookup branches, the frontend.
Widening documents/chat to linked students is a follow-up for csc-002, not this item.

## Security

- The scope is per counselor: a student linked to counselor B never appears to, or is schedulable by, counselor A.
- IT counselors stay refused by the existing division gates (`_allow(..., "overseas")`, `_require(..., "overseas")`).
- No PII is logged; the lookup's count-only log line is unchanged.

## Edge cases

- A student both linked and on an application is listed once (SQL `UNION` + `IN`).
- Bridged school applications have `student_id` NULL; a NULL inside `IN (…)` matches nothing and is harmless (only `NOT IN` breaks).
- A deactivated counselor cannot sign in; reassignment is csc-005.

## Migration

`0165` creates the table and its indexes only when missing (0001 builds fresh databases from the models — the 0164 idiom).
`downgrade()` refuses while link rows exist, so caseload data is never dropped silently.

## Tests

- `test_csc_001_migration.py`: single head after 0164, model ↔ migration columns, round trip, downgrade refusal.
- `test_csc_001_counselor_students.py`: linked student in the lookup; listed once; another counselor's link not visible; `q` still
  filters; appointment for a linked student → 201; appointment for another counselor's linked student → 403; application-based
  behaviour unchanged (existing ENH-031 / CNS-001 tests rerun).
