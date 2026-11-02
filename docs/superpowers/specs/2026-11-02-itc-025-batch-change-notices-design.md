# itc-025 — Batch, course and timetable change notifications (design)

**Decision:** DEC-SCOPE-346. **Backlog:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` §itc-025 (source §7 row "Course/batch/timetable
changed"; source PDF `UNVERIFIED`, owner Q-01 approved all phases for build in waves). **Dependencies (all merged on `main`):** itc-002
(typed `notify()`), itc-003 (`ItStudentCounselor`), itc-020 (timetable service). **Migration:** none. **API:** §12IR (additive: a new
portal section only). **RBAC:** §2.246 (no grant change).

## 1. Requirement (backlog, verbatim intent)
A batch date, trainer or timetable change, or a student transfer, notifies the affected students and their linked counselors, with a
summary of what changed.
- AC1 Every listed change produces one notification per affected user.
- AC2 A no-op save sends nothing.
- \+ The trainer changes: 30 students plus 4 counselors are notified (one each).
- E A transfer between batches with different counselors.

## 2. Discovery (graphify + reads)
| Class | Item |
|---|---|
| MUST CHANGE | `api/admin.py` `update_batch` (PATCH `/admin/batches/{id}`) and `update_enrollment` (PATCH `/admin/enrollments/{id}`, the transfer); `services/batch_timetable.py` `create_slot`/`update_slot`/`delete_slot`/`cancel_class`; `notifications/events.py` (counselor event + change labels) |
| MAY CHANGE | `services/portal.py` `_it_counselor` + `lib/navigation.ts` + `components/PortalPage.tsx` (an IT counselor Notifications page, so the notice is visible in-app — the backlog's "FE: none beyond notifications") |
| SHOULD NOT CHANGE | `communications.py` live-session notices (nehn-029, untyped, students only — not in this item's list); `notify()` dedupe/rollback semantics; itc-003 counselor-assign notices |
| HIGH REGRESSION RISK | `test_adm_003_*`, `test_adm_005_*` (admin batch/enrolment PATCH), `test_itc_020_timetable.py` (cancel notice), `test_itc_002_notify.py` (catalogue) |

## 3. Design (selected: smallest change that reuses itc-002)
1. **Summary of what changed without free text.** itc-002 forbids free text in a notice (no amounts/notes can leak into an email subject
   or SMS). `notify()` gains an optional `changes=("trainer", "start_date")` of **field keys** from a fixed `CHANGE_LABELS` vocabulary;
   the body becomes `<fixed body> Changed: trainer, start date.` An unknown key raises `ValueError` (same as an unknown event). Values
   (new dates, trainer names, reasons) are never put in the notice — the recipient opens EduSphere for them.
   *Alternatives rejected:* per-field event types (catalogue explosion); free-text summary (breaks itc-002's §7 guarantee).
2. **Counselors get their own event** `it.batch.student_changed` ("Student's batch updated"), because the student text says "Your
   course…". Link `/it/counselor/timetable` (itc-020's counselor calendar of their students' batches).
3. **One helper** `services/batch_notices.py::notify_batch_change(db, batch_id, changes, *, students=None, action_url)`: the batch's
   `active` enrolments (same rule as itc-020 and nehn-029) — or the given students — plus the distinct linked counselors of those
   students (`ItStudentCounselor`). `notify()` dedupes per (recipient, event, record) in the transaction, so a counselor of 4 students
   gets one notice (AC1). Never commits; the caller's transaction publishes (rollback sends nothing).
4. **Emitters**
   | Change | Where | changes | Student link |
   |---|---|---|---|
   | Batch name/start/end/trainer/schedule/time zone/mode | `update_batch` — compares before/after values; no difference → nothing (AC2) | changed keys | `/it/student/course` |
   | Weekly slot added / edited (a real difference) / removed | `create_slot` / `update_slot` / `delete_slot` | `timetable` | `/it/student/timetable` |
   | One class cancelled | `cancel_class` (students already notified by itc-020; counselors added) | `cancelled_class` | `/it/student/timetable` |
   | Student transfer (batch_id to a different batch) | `update_enrollment` — only that student and their counselor; record = the new batch | `batch` | `/it/student/course` |
   Capacity, enrolment-open and status are admin-internal and do not notify (`NEEDS_CONFIRMATION` if the owner wants status, e.g. a
   cancelled batch, to notify). A transfer to the same batch is a no-op.
5. **Edge E (different counselors):** counselors belong to the student (itc-003 Q-03), not the batch; the transferred student's own
   counselor is told once; other students' counselors are not.
6. **IT counselor Notifications page:** `notifications` joins the IT counselor nav; the portal section is header-only and PortalPage
   mounts the shared list (`GET /workflows/notifications`), exactly as itc-002 (student) and itc-009 (IT admin) did.

## 4. Reviews (Phase 3)
- **API:** no request/response change on the admin PATCH routes (notification is a side effect in the same transaction). New portal
  section `GET /portal/it/counselor/notifications` (counselor-only, header payload). Backward compatible.
- **Security:** AuthZ unchanged (`ensure_admin` + `it_admin`/`super_admin` on PATCH; `EDITORS` on timetable). Recipients are derived
  server-side; nobody outside the batch/link receives anything (no IDOR surface). Notices carry fixed text + field labels only;
  logs carry counts/ids only. Deactivated users are skipped by `notify()`.
- **Concurrency/transactions:** batch row is already `FOR UPDATE` in `update_batch` and the timetable writes; the notice rows are added
  in the same transaction.
- **Performance:** two queries per change (students, counselors) + itc-002's bulk inserts; fan-out = batch size (≤ 20 by DEC-WF-002).
- **Frontend:** reuse `SchoolNotificationList`; empty state text names what lands there; same layout as the student/admin pages.

## 5. Plan (TDD, one task at a time)
1. `events.py`: `CHANGE_LABELS`, `changes=` on `notify`, counselor event — unit tests (labels in body, unknown key → ValueError).
2. `services/batch_notices.py` + batch PATCH emitter — API tests: trainer change → N students + distinct counselors, one each; no-op
   PATCH → none; capacity-only → none; withdrawn student → none.
3. Timetable emitters — API tests: slot create/edit/delete notify students + counselor; unchanged edit → none; cancel → counselor too.
4. Transfer emitter — API test: transfer notifies only the moved student + their counselor (record = new batch); same batch → none.
5. Counselor Notifications page — API test (section 200 for IT counselor) + vitest (nav item, list mounted, empty state).
6. Docs: DEC-SCOPE-346, API §12IR, RBAC §2.246, backlog status line.
