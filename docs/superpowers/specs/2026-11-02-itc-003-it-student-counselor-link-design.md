# itc-003 — Counselor ↔ IT student ownership link (design)

**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-003 (classification `UNVERIFIED` PDF, owner-approved for build in waves by
Q-01, 2026-11-01). **Owner answers used:** Q-03 (2026-11-01): a new IT-only table `it_student_counselors` following the csc-001 pattern,
overseas code untouched; one counselor per student (a second enrolment keeps the same counselor; IT admin reassigns with a reason).
**Decision:** `DEC-SCOPE-337`. **Dependencies:** none (backlog). itc-001 (audit diff helper) and itc-002 (notification event type) are
being built in parallel and are *not* required: the reassignment's audit row already carries before/after (`from_counselor_id`,
`to_counselor_id`) in the csc-005 shape, and notices use today's `Notification` + `queue_deliveries`.

## Intent

The system must know who "the IT counselor" of an IT student is, so later items (itc-011 conversion, itc-023/025/027 notices, itc-029
360, itc-030 counselor workspace) can scope and route by it. Today only overseas has that link (csc-001).

## Behaviour

1. **Table** `it_student_counselors` (`id`, `student_user_id` UNIQUE → users, `counselor_user_id` → users indexed, `assigned_by_user_id`
   → users, timestamps). Migration `0222_it_student_counselors` (additive). It **backfills** one row per existing IT lead that is linked
   to a student (`enquiries.converted_user_id`) and owned by an IT counselor (`assigned_by` = the person who linked it). Downgrade
   refuses while rows exist (csc-001 idiom).
2. **Set on link-student** (counselor `POST /counselor/leads/{id}/student-link`, admin `POST /admin/leads/{id}/conversion`; itc-011's
   one-step conversion will call the same `lead_handover.link_student`): for an IT lead whose owner is an IT counselor, the student gets
   that counselor **only if they have none yet** (one per student; an existing counselor is kept — the admin reassigns). Audited
   `it.student.counselor_link`. The student row is already locked by `link_student`, which serialises it with a reassignment.
3. **Unlink** (`DELETE …/student-link` / admin unconvert): the link is removed when it still points at the lead's owner, so a mistaken
   link does not leave the student in that counselor's caseload. A link the admin has since moved is kept.
4. **Reassign** `PUT /admin/it/students/{id}/counselor` `{counselor_id, reason?}` (csc-005 / ccrm-033 rules): IT Admin only (403 for
   anyone else, `super_admin` included — csc-005 C13 precedent, `NEEDS_CONFIRMATION`); the student must be an `it_student` (404); the
   counselor an active IT counselor (422); same counselor → `changed: false`, nothing written; replacing a counselor needs a reason
   (422); first assignment may omit it. Audited `it.student.counselor_assign` with from/to/reason; both counselors get an in-app notice
   (+ consented channels) with the reason; a deactivated previous counselor is not notified.
5. **Counselor reads** `GET /counselor/it/students` (paged `{items,total,limit,offset}`, `q` filter on name/email/Student ID) and
   `GET /counselor/it/students/{id}`: IT counselors only (an overseas counselor or any other role → 403); only linked students; any other
   id → 404 (no disclosure).
6. **Picker** `GET /lookups/it-counselors` (IT Admin): active IT counselors, name + id.
7. **UI:**
   - IT Admin → Students: "EduSphere counsellor" column and the existing `AssignCounselorButton` (pointed at the IT URL and IT picker).
   - IT counselor nav → **Students** ("My students": Student ID, name, email, phone, since).
   - IT student dashboard: a **"Your counselor"** tile (name, or "Not assigned yet"). The student only ever reads their own link.

## Non-goals

Counselor deactivation blocking (tel-025 style) — left as is: the admin reassigns (`NEEDS_CONFIRMATION`). No per-enrolment counselor.
No change to overseas tables or tests. No student 360 / notes (itc-029/028).

## Calls made by the builder (`NEEDS_CONFIRMATION`)

C1 IT Admin only (not super_admin) reassigns. C2 the backfill of existing linked IT leads. C3 unlink removes the auto link when it still
points at the lead owner. C4 the student sees only the counselor's name (no phone/email). C5 an existing counselor is kept when a second
lead links the same student (impossible today: one lead per student, `uq_enquiries_converted_user`).

## Plan (TDD, small tasks)

1. Model + migration + migration test (fresh table, backfill, downgrade refusal).
2. Service `services/it_student_counselors.py` (`link_on_conversion`, `unlink`, `assign`, `page`, `one`, `counselor_name`).
3. Hook into `lead_handover.link_student` / `unlink_student`; tests via the counselor and admin link routes.
4. API router `api/it_student_counselors.py` + lookup; tests for 200/403/404/422/changed:false/notices/audit.
5. Portal: admin Students column, counselor Students section, student dashboard tile; nav entry; tests.
6. Web: `AssignCounselorButton` `lookup` prop, DataTable column type `assign_it_student_counselor`; vitest.
7. Docs: DEC-SCOPE-337, API §12II, RBAC §2.239, backlog status. Playwright spec + browser QA.

## Regression risks

`lead_handover` link/unlink (tel-018, bdm-017, ccrm-008 tests); portal payload shapes for IT admin Students / IT counselor / IT student
dashboard (metric count); DataTable; route matrices that require every route to be documented.
