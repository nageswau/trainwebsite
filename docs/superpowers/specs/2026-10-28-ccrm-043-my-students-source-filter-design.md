# ccrm-043 — Counselor "My students" with Source filter and search (design)

Source: `docs/delivery/COUNSELOR_CRM_BACKLOG_2.md` `ccrm-043` (owner request 2026-10-28, Q10 "All my students + Source filter
(Walk-in, Lead conversion, Self-registered, Agency) + search"). Dependencies: none. The owner pre-authorised recommended answers;
every builder's default below is `NEEDS_CONFIRMATION`.

## Intent

`/overseas/counselor/students` shows only walk-in students (csc-001 links). Students who reach the counselor through an application
(self-registered, agency, lead conversion) appear only in the application table. The counselor wants one list of all their students,
filterable by how the student arrived, and searchable.

## Design (simplest: extend the existing route and card)

**API** — `GET /api/v1/counselor/students` keeps its path, auth (`require_overseas_counselor`, else 403) and `{items,total,limit,offset}`
shape. Additive:

- Rows = `overseas_student` users in `visible_student_ids(counselor)` (csc-001 link ∪ applications with `counselor_id == me`), not archived
  (`student_archive.not_archived`). Each student once.
- Params: `source` ∈ `walk_in | lead_conversion | self_registered | agency` (anything else → 422 via `Literal`); `q` (≤100 chars) —
  literal, case-insensitive substring of name / email / student code, phone also matched on digits (ccrm-012 helpers `like_pattern`,
  `counselor_search._matches/_digits_pattern`). Blank `q` = no filter.
- Item adds: `source`, `applications` (count of all the student's applications — the 360 shows all of them, V1), `linked_since`
  (earliest of the caller's link and the caller's first application), `linked` (true when the csc-001 link is to the caller — only
  those rows can Edit/Resend, since csc-003 routes 404 otherwise).
- Order: `linked_since` desc, `User.id` (unchanged for link-only rows: newest link first).
- Source (builder's default, mutually exclusive, first match wins): `registration_source == counselor_walk_in` → walk_in;
  `== lead_conversion` → lead_conversion; an `AgentStudent` row for the student or an agency application (`agent_id` or
  `agent_student_id` set) → agency; else (incl. `self_service` / missing) → self_registered.
- One query for the page (outer-joined grouped subqueries — no N+1), one count, plus `provisioning_statuses` (two queries).
- `POST` create/resend/edit responses unchanged.

**UI** — `components/CounselorWalkInStudents.tsx` card retitled "My students"; filter bar (search box + Search button, Source select
that applies at once, Clear); rows add a Source badge, application count and "Linked since"; Edit/Resend only when `linked` and pending.
Empty state distinguishes "No students yet" from "No students match these filters." Pager resets to page 1 on a filter change.
Add-walk-in form unchanged.

**Out of scope:** Overseas Admin view (unchanged, `NEEDS_CONFIRMATION`), new route, migration, index.

## Acceptance criteria (backlog AC1–AC7 + edges)

AC1 self-registered student with my application listed (Self-registered); AC2 walk-in listed as Walk-in; AC3 converted lead as Lead
conversion; AC4 agency student with my application as Agency; AC5 filter narrows; AC6 archived excluded; AC7 another counselor's
students never listed; E1 search by phone digits; E2 invalid source → 422; E3 walk-in with my application listed once; E4 application
moved to another counselor → drops off; E5 legacy user without `registration_source` → Self-registered.

## Security

Rows only from `visible_student_ids`; no new data beyond what 360 shows (no agency contact data); `q` is a bound ILIKE parameter
(escaped); React escapes output; GET only (no CSRF surface); search text never logged.

## Regression risks

csc-002 list test asserts the exact item dict (updated for the additive fields); ccrm-040 archive test; csc-002 e2e (form name unchanged);
ccrm-041 matrix (no new route).

## Plan

1. RED/GREEN backend `tests/test_ccrm_043_my_students.py` (AC1–AC7, E1–E5, 403/401) → `services/counselor_students.page`, route params.
2. RED/GREEN vitest `CounselorWalkInStudents.test.tsx` (title, source/applications/linked-since, filter URL, empty-filter state,
   Edit only when linked) → component.
3. Playwright `tests/e2e/ccrm-043-my-students.spec.ts` (desktop/mobile, filter + search).
4. Docs: API §12HN, DEC-SCOPE-316, RBAC §2.149 note.
