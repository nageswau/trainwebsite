# nehn-040 — Student ID coverage and lookup (design + plan)

**Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-040` (PDF §22 L578-587, §23 L592/L596, actions 21/22;
the PDF is `UNVERIFIED`). **Decision:** `DEC-SCOPE-279` (builder's defaults; owner pre-authorised recommended answers,
`NEEDS_CONFIRMATION`). Builds on `DEC-DATA-003` (CONFIRMED_CURRENT 2026-09-15: 8-character hex Student ID, students only, no Agent ID).

## Intent

A counselor, admin or agent hears a Student ID on the phone and finds the student. Today the ID exists but agent-created students and
admin-provisioned students have none, and the admin users list, the overseas-student picker, the agency student list and the agent
network list neither show nor search it.

## Builder's calls (`NEEDS_CONFIRMATION`)

| # | Call |
|---|---|
| N1 | **Agent ID stays out of scope.** `DEC-DATA-003` (an actual approval record) says students only; the PDF is `UNVERIFIED` and does not supersede it. AC4 does not apply. Agency member codes (`M001`/`S001`) already exist. |
| N2 | Agency students with **no login** get `agent_students.student_code` (8-char hex, unique, nullable). A **linked** row (has a login) keeps NULL and shows its account's `users.student_code` — one person, one code. |
| N3 | `users.student_code` and `agent_students.student_code` are **one code space**: every new code (registration, seed, walk-in, admin-provisioned, agency-created) is checked against both columns, because the agency list shows both kinds side by side. `school_students` stays its own space (`DEC-DATA-003`). |
| N4 | **Admin-provisioned** `it_student`/`overseas_student` accounts (`POST /admin/users`) now get a code; they had none since `0028`. |
| N5 | Migration `0194_agent_student_codes` adds the column and backfills (a) every no-login agency student and (b) every student account still without a code. Additive; downgrade drops the column only (users keep their codes). |
| N6 | Search is the existing case-insensitive literal substring (`ILIKE`, escaped), so a full code and a partial code both match — the backlog's "prefix only" question is answered "substring, like the other fields". Scopes are unchanged; nothing outside the caller's scope matches. |
| N7 | The anti-enumeration agent link search (`/lookups/overseas-students?purpose=link`) is **unchanged**. |
| N8 | There is no flow that turns a no-login agency row into a login, so no code merge is built. |
| N9 | Display label is **"Student ID"** (the label the app already uses on walk-in rows, the student 360 and the archive page). |

## Changes

**API (additive, no new route, no RBAC change):**
- `GET /admin/users` items gain `student_code` (string|null). `POST /admin/users` assigns one to student roles.
- `GET /lookups/overseas-students` (not `purpose=link`): `q` also matches `student_code`; `detail` is `email · CODE`.
- `GET /workflows/overseas/agent/crm/students` (AGN-004 list) and its detail/create/update responses gain `student_code`; `q` also matches it.
- `GET /overseas-admin/agent-orgs/{id}/students` items gain `student_code`.

**Web:** admin users panel — "Student ID" column and search ("Search by name, email, role, or Student ID"); agency student cards and the
detail header show "Student ID …"; search placeholder "Name, email, phone or Student ID"; agent network students table — "Student ID" column.

## Plan (TDD, one slice at a time)

1. `core/identifiers.unique_student_code(db, *columns)` — unique across every column given. Callers pass `User.student_code,
   AgentStudent.student_code` (auth, seed, counselor walk-in, admin create, agency create).
2. Model column + migration `0194` with backfill; migration test (backfill, no collision with users, round trip).
3. `services/agent_students`: async `create_record` assigns a code; `record_item` returns `student_code`; `list_page` `q` matches it.
4. `admin.py`: `/users` returns `student_code`; create assigns it.
5. `lookups.py`: `q` matches code; `detail` shows it.
6. `agent_network.org_students` + `AgentNetworkStudentOut.student_code`.
7. Web: types, panels, unit tests; Playwright `nehn-040-student-id.spec.ts`.
8. Docs: register, API §12GE, RBAC §2.193, RTM.

## Acceptance criteria

| AC | Criterion |
|---|---|
| AC1 | Searching a student's code in admin users finds that student (API returns it; panel search matches it). |
| AC2 | Every agency-created (no-login) student has a code — new ones at create, existing ones after the backfill. |
| AC3 | The code shows in list rows (admin users, agency students, agent network) and the agency student detail header. |
| AC4 | (Agent ID) not applicable — N1. |
| AC5 | Search by code is scoped: an agent never finds another agency's student, a counselor only visible students. |
| AC6 | New codes never collide across `users` and `agent_students`. |

## Regression risks

`0028` uniqueness tests; AGN-004 create/list tests (`create_record` becomes async); the admin users panel tests; ENH-031 lookup tests
(`detail` string changes only for non-link lookups).
