# csc-005 — Overseas Admin views and reassigns a student's counselor (design)

`DEC-SCOPE-230`, API `12EP`, RBAC `2.152`, no migration (csc-001's `overseas_student_counselors`). Backlog:
`docs/delivery/COUNSELOR_WALKIN_BACKLOG.md` §3 `csc-005`; owner answers W3 ("Overseas Admin can reassign") and W6 ("deactivation and
reassignment stay with Overseas Admin").

## Intent

A walk-in student belongs to the counselor who created them (csc-001/002). When that counselor leaves or the caseload must move, the
Overseas Admin moves the student to another active overseas counselor — so no student is stranded.

## API — `PUT /admin/users/{user_id}/counselor` → 200

Body `{"counselor_id": uuid}` (AGN-023's assign body: required, swap only). Mirrors AGN-023's application reassign:

- Only `overseas_admin` in `overseas` (`super_admin` excluded, as AGN-023 H2) → else `403 "Only the Overseas Admin can assign a
  counselor"`.
- The target must be an `overseas_student` → else `404 "Student not found"`. Row-locked.
- The counselor must be an active `counselor` in `overseas` → else `422 "Choose an active overseas counselor"`.
- No link yet → the link is created (assign); same counselor → `{"changed": false}`, nothing written; otherwise the link moves
  (`assigned_by_user_id` = the admin).
- Audit `overseas.student.counselor_assign` `{from_counselor_id, to_counselor_id}`; in-app + queued notifications to the new counselor
  ("Student assigned to you" → `/overseas/counselor/students`) and, if active, the previous one ("Student reassigned").
- Response `{"id", "counselor_id", "counselor_name", "changed"}`.

Applications keep their own counselor (AGN-023 governs those); csc-001's union means the new counselor sees the student at once and the
previous counselor still sees them through any application they hold.

## Admin view

The Overseas Admin's **Users** directory (`/overseas/admin/users`, the role-scoped user table) gains an **EduSphere counsellor** column
(on each overseas student row: the linked counselor, else "Not assigned"; staff rows blank) and the AGN-023 assign/change control on
student rows, declared by the server as a new column type `assign_student_counselor`. Not on **Students**: for the Overseas Admin that
page lists applications (AGN-023 H11), so a walk-in with no application would be missing there (found by the first test run). `AssignCounselorButton` takes an optional `url` (default: the application route) so the same picker,
focus handling and messages serve both. Every other section and role is unchanged.

## Builder's calls (owner: proceed with recommended answers)

- C13 — Overseas Admin only; `super_admin` cannot reassign (AGN-023 H2 precedent; backlog §5 question closed this way).
- C14 — assigning a student who has no link yet is allowed (it creates the link); there is no "unassign" (swap only, as AGN-023 H8).
- C15 — the Overseas Admin's appointment list (application-based, noted in csc-001) stays as it is; not this item.

## Tests

`test_csc_005_reassign_student_counselor.py`: reassign moves the link + audit + both notifications; first assign creates the link; same
counselor → `changed: false`, no audit; inactive / IT / non-counselor → 422; non-student / unknown → 404; super_admin, IT admin,
counselor, student → 403; anonymous 401; after reassignment the new counselor's picker has the student and the old one's does not
(csc-001 scope); the Students section shows the counselor and the assign column for the Overseas Admin only. Vitest: DataTable renders
the student control with the admin URL; AssignCounselorButton uses a given `url`. e2e: the admin reassigns a walk-in student and the
counselor column updates.
