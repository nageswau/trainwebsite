# ENH-033 — Dual enrolment: IT ⇄ Overseas on one login (design)

- **Date:** 2026-11-13. **Decision:** `DEC-SCOPE-441` (owner answers D1–D9, `EXPLICIT_APPROVAL`). Extends `DEC-ROLE-001`.
- **Backlog:** `docs/delivery/ENHANCEMENT_BACKLOG.md` ENH-033 (AC1–AC8). **API:** §12MH. **RBAC:** §2.331.
- **Migration:** none. `user_role_assignments` (unique `user_id, division, role`), `overseas_student_counselors` and
  `it_student_counselors` (one row per student each) already hold everything this needs.

## 1. Model

A student holds one `UserRoleAssignment` per division they are enrolled in (`it/it_student`, `overseas/overseas_student`).
`User.role` / `User.division` keep their meaning for every existing route: **the active portal**. Invariant: they are always
one of the user's own active student assignment pairs, and are only ever changed together (never `overseas` + `it_student`).

Two kinds of question exist in the code, and they get different answers:

| Question | Read from | Sites |
|---|---|---|
| "Which portal is the caller in?" (caller gate) | `User.role` / `User.division` — unchanged | ≈75, §5 bucket A |
| "Is this person a student of division X?" (subject check / set query) | an active assignment | 35, §5 buckets B and C |

New helpers in `app/services/student_divisions.py`:
- `STUDENT_ROLE = {"it": "it_student", "overseas": "overseas_student"}`
- `student_of(division)` → SQL expression: `User.id.in_(select(URA.user_id).where(URA.division == d, URA.role == STUDENT_ROLE[d], URA.is_active))` for set queries.
- `async is_student_of(db, user_id, division) -> bool` for subject checks.
- `async held_student_divisions(db, user_id) -> list[str]`.

## 2. Staff action: add a division (D1, D2, D4, D5, D6)

Routes (target division `{d}` in `it|overseas`; caller must be `counselor` or `telecaller` with `User.division == d`):

- `GET /workflows/{d}/dual-enrolment/lookup?ref=` — `ref` = email (case-insensitive) or 8-char Student ID. Matches only active
  users holding an active student assignment in the *other* division. Returns `{id, full_name, student_code, divisions}`; 404
  "No student found" otherwise (same message whether absent, inactive or staff, so it reveals nothing beyond a student match).
- `POST /workflows/{d}/dual-enrolment` body `{student_id, counselor_id, student_requested: true}`:
  1. `student_requested` must be `true` → else 422 "Confirm the student asked to enrol".
  2. Student: active, holds the other division's student assignment → else 404 (as lookup).
  3. Already holds an active `{d}` student assignment → 409 "Already enrolled in <Division>". An inactive row for `{d}` →
     409 "This student's <Division> access was ended; ask an admin" (reactivation is part of the deferred D7 item).
  4. `counselor_id`: active `counselor` with `division == d` → else 422 "Pick a <Division> counselor".
  5. Insert the assignment (`assigned_by_user_id` = caller, `approval_status="approved"`); upsert the division's counselor row
     (`overseas_student_counselors` / `it_student_counselors`, `assigned_by_user_id` = caller). A unique-constraint race → 409 as 3.
  6. `AuditLog(action="student.dual_enrol", entity_type="user", entity_id=student, metadata={division, counselor_id, student_requested: true, by_role})`.
  7. Notify the student (in-app `Notification` with `action_url` to the new portal's dashboard, plus email through the existing
     generic-notification mailer; delivery failure never fails the request) and the chosen counselor (in-app).
  8. 201 `{student_id, division, counselor_id}`.
- Student code, password, sessions and the active portal are untouched (D4). No program enrolment or application (D6).

Counselor pickers: `GET /lookups/overseas-counselors` and `/lookups/it-counselors` additionally allow `counselor` and
`telecaller` of that division (admins unchanged).

## 3. Portal switching (D3, D8)

- `POST /auth/switch-portal` body `{division}`: caller's `User.role` must be a student role and `is_student_of(target)` → else
  403 "You are not enrolled in <Division>". Same division → 200 no-op. Sets `User.role`/`User.division` together, re-issues
  the auth cookies (same `session_version` — other tabs follow because every request reloads the user), audits
  `auth.switch_portal`, returns `LoginResponse`.
- `POST /auth/login`: when `payload.division != user.division`, the user's active role is a student role and
  `is_student_of(payload.division)`, switch to that division before issuing cookies (D8). Everyone else keeps today's
  "Use the correct EduSphere portal" 403.
- Frontend: `PortalShell.tsx` header shows a "Portal" menu (IT Student / Overseas Student, current ticked) only when
  `role_assignments` has both active student rows; choosing one calls the switch route then navigates to that portal's home.

## 4. Payment lock and own-data scope (security)

- `student_access.require` / `summary` must not depend on the active portal: the IT payment lock applies when the *resource* is
  IT-learning data and the user is an IT student by assignment. Change the early return to
  `if not await is_student_of(db, user.id, "it"): return`. Covers the submission-file download (`workflows.py` ~678), the only
  route whose ownership check does not also gate on `it_student`.
- **D9 (owner, 2026-11-13): each portal shows only its own division's money.** Fee accounts are already IT-portal only
  (`fee_accounts` caller gate). A student's own payment list, receipt and invoice reads additionally require
  `Payment.division == User.division`; a payment of the other division is a 404 from this portal.
- Caller gates that check role without division (workflows 1656/1992, communications 158, recruiter_offers 172,
  trainer_profiles) stay safe because of the §1 invariant; a test asserts switching always writes a valid pair.

## 5. Site inventory

From a read-only sweep of `apps/api/app` (tests/seed excluded), 2026-11-13 @ `52dda52d`.

**A — caller gates, unchanged (≈75).** `workflows.py` (≈45 lines), `communications` 158, `fee_accounts` 72/98,
`fee_discounts` 63, `lookups` 209/219, `payments` 215, `api/portal.py` 34, `services/portal` 2156/2160, `batch_timetable`
170/201, `candidate_jobs` 159, `it_conversion` 217, `it_progress` 479, `it_status_labels` 44, `hr_reviews` 315,
`candidate_portal` 131, `placement_pool` 35, `it_student_profiles` 32, `it_student_notes` 112, `student_profiles` 50,
`recruiter_offers` 172, `trainer_profiles` 101/107, `application_interviews` 90, reader sets in `application_checklists`,
`application_offers`, `document_access`. (`student_access` 90 moves to §4.)

**B — subject checks → `is_student_of` (17).** workflows 516 (staff enrols IT student), 2433 (placement profile update),
2529 (staff creates application), 3003 (staff adds document), 3541 (staff books appointment), 3626 (agent links student);
communications 52 (recipient division) and 56 (counselor caseload — IT equivalent via `it_student_counselors`);
payments 61 (receipt notice: key on the payment's division); inbound 44; counselor_students 228; it_student_profiles 43;
it_student_notes 52; student_notes 28; student_profiles 43; services/portal 1833; appointment_invites 67 (URL from the
appointment's division, not the recipient's active role).

**C — set queries → `student_of(division)` (18).** workflows 2222, 2402; inbound 58; lookups 117; services/portal 1758,
1807–1812; student_search 66, 86; counselor_students 280; counselor_dashboard 173; counselor_search 97;
it_counselor_dashboard 97; it_student_counselors 102; hr_students 18; placement_pool 45–46; reports/placement 29;
lead_handover 313; recruitment_notices 77/85.

**D — other.** `auth.register` / `admin` user create already create the first assignment (via `_sync_role_assignment` /
explicitly) — unchanged. `payments` 27 and `management_metrics` 66/70 use `role.in_(both)` → a dual student counts once —
unchanged. `admin` 674 user count by division counts a dual student only in the active division — switched to assignments
for students. Label/permission maps (`rbac`, `agent_journey`, `student_search` kind constants) and log strings — unchanged.

Every B/C site is re-read at implementation time; a site whose code differs from this table is re-classified, not forced.

## 6. Acceptance-criteria map

| AC | Proved by |
|---|---|
| AC1, AC2 | `tests/test_enh_033_dual_enrolment.py` enrol both directions (assignment, counselor row, notification, unchanged code/password) |
| AC3 | same file: wrong division, wrong role, wrong counselor, no tick, duplicate, inactive row, non-student, race |
| AC4, AC5 | `test_enh_033_switch.py`: switch, no-op, refused switch, login on either page, single-division refusal kept |
| AC6 | `test_enh_033_subject_and_sets.py`: for each B/C site group, a dual student in the *other* active portal is still found once |
| AC7 | same file: caller gates follow the active portal; IT payment lock holds from the overseas portal |
| AC8 | audit rows asserted in the enrol and switch tests |
| UI | Playwright `enh-033-dual-enrolment.spec.ts`: counselor adds Overseas to an IT student; student switches portals |

## 7. Out of scope
Removing a division (D7), student self-service requests, a merged dashboard, staff with multiple role assignments.
