# ccrm-046 — Counselor creates and manages multiple applications for a student (design)

Source: `docs/delivery/COUNSELOR_CRM_BACKLOG_2.md` § `ccrm-046` (owner request 2026-10-28, `MEETING_TRANSCRIPT_REQUEST`-equivalent).
Dependencies: ccrm-047 (IntakePicker, PR #386) and ccrm-045 (360 page, PR #385) are merged on `origin/main`.
Decision: `DEC-SCOPE-324`. API: §12HV. RBAC: §2.227.

## Intent

The owner: "Counsellor also should be able to apply to a university on behalf of student" / "create and manage multiple university
applications for one student". The API already admitted the counselor but had no UI and no caseload check (a counselor could create an
application for any overseas student — an IDOR-class gap).

## Behaviour

- **Student 360 → Applications tab (counselor portal, student not archived):** an "Add application" disclosure holds the existing
  apply form (country → university → course → intake picker) for that student. Submit creates the application; the tab list and count
  refresh in place; the form stays open for the next university/course (AC1, repeatable).
- **`POST /workflows/overseas/applications` as a counselor:**
  - student outside the counselor's caseload (`counselor_students.is_visible_student`: own application or csc-001 link) → **403**
    "This student is not in your caseload" — checked before the archive guard, so it does not reveal the archive state (AC4);
  - `counselor_id` naming another counselor, or any `agent_id` → **403**: a counselor's application is theirs and direct;
  - otherwise unchanged: `counselor_id = me`, APP- code, stage `enquiry` (AC2), duplicate open → 409 (AC3), archived → 409 (AC5),
    withdrawn / closed outcomes free the slot, same university with a different course allowed, student notified (AC6).
- Student, Overseas Admin and agent paths are unchanged.

## Calls made without the owner (NEEDS_CONFIRMATION defaults)

- Overseas Admin gets no 360 "Add application" UI (API unchanged).
- Course active/published rule unchanged (none on the API); the form lists the public catalogue only.
- A counselor-created application for an agency student is direct (no `agent_id`).

## Non-goals

No migration, no new route, no change to the duplicate key, the code sequence, the evaluation panel, or the student self-apply form.

## Tests

- pytest `tests/test_ccrm_046_counselor_applications.py`: AC1–AC6, edge cases, the 403s, admin path unchanged.
- vitest `OverseasApplyPanel.test.tsx`: `studentId` mode sends `student_id`, skips the student list, refreshes.
- Playwright `tests/e2e/ccrm-046-counselor-applications.spec.ts`: counselor adds two applications on the 360; duplicate → error.
