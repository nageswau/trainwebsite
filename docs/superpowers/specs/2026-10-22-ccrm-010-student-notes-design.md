# ccrm-010 — Internal notes on an overseas student (counselling history) (design)

`DEC-SCOPE-241`, API `12ET`, RBAC `2.156`, migration `0168_overseas_student_notes` (chained after ccrm-002's `0167_lead_notes`, itself after ccrm-011's
`0166_application_codes`; 240 / 12ER–12ES / 2.154–2.155 left for the parallel ccrm-014). Backlog: `docs/delivery/COUNSELOR_CRM_BACKLOG.md`
`ccrm-010` (supersedes `nehn-037` part 5). Dependencies: none (backlog). Source: UNVERIFIED spec PDF §5 Activities, §6 internal notes;
owner instruction "implement all this" (2026-10-22).

## Intent

Today the only place a counselor can write anything about an application is `ApplicationStatusHistory.notes` (via a status PATCH), and
there is nowhere to write about a student at all. A counselor needs a running, internal counselling history for each student — kept
when the student moves to another counselor — that the student and the agent never see.

## Data — `overseas_student_notes` (append-only)

`id`, `student_user_id` (FK users, indexed with `created_at`), `application_id` (FK overseas_applications, NULL), `author_user_id`
(FK users), `body` (Text, 1–4000 chars), `created_at`/`updated_at` (TimestampMixin; never updated). No update or delete path exists in
code. Additive migration; `downgrade()` refuses while notes exist (0165's idiom).

## API — `/counselor/students/{student_id}/notes`

- `GET ?limit=20 (1..50)&offset=0` → `{"student": {id, full_name, student_code}, "applications": [{id, label}], "items": [note],
  "total", "limit", "offset"}`; newest first. `note = {id, body, author_name, author_role, application: {id, label} | null,
  created_at}`. `applications` = the applications the caller may attach a note to (below); `label` = "University · reference" (reference
  omitted when empty).
- `POST {"body": str, "application_id": uuid | null}` → 201 `note`. `extra="forbid"`; body trimmed, blank → 422.

**Who (N1/N2).** An overseas `counselor` for a student in csc-001 scope (`is_visible_student`: own applications ∪ linked); the
`overseas_admin` (division `overseas`) for any `overseas_student`. Both read and write. Any other role (student, agent, university_rep,
IT counselor, super_admin, other admins) → 403 "Only an overseas counselor or the Overseas Admin can see student notes". A student out of
the counselor's scope, an unknown id or a non-student → 404 "Student not found" (no disclosure). No student- or agent-facing route
returns notes.

**Application link (N3).** Optional. Counselor: one of this student's applications assigned to the caller (`counselor_id == caller`,
direct or agency — CC4). Admin: any of this student's applications. Otherwise 422 "Choose one of this student's applications".

**History (N4).** A counselor sees every note on the student, whoever wrote it — so the history survives a csc-005 reassignment.
Append-only: no edit or delete (owner-facing correction = a further note).

Transactions: one insert + commit; append-only, so no lost-update race. Logging: `student_note_created` with actor, student and note ids
— never the body. No notification and no AuditLog row: the note row *is* the record (author + time).

## UI

`StudentNotesPage` (server page shell + `StudentNotesPanel` client component) at `/overseas/counselor/students/[id]/notes` and
`/overseas/admin/students/[id]/notes`: the student's name and code, a form (textarea with counter, optional "Application" select from
`applications`, Save), then the history list (author, role, date, application label, body with `white-space: pre-wrap`), "Load more"
paging. Loading, empty ("No notes yet"), error (status region) and in-flight states; Save is guarded against double submit; the
textarea keeps its text on failure. Body rendered as text (React escapes; no HTML).

Entry points (server-declared column type `student_notes`, href in the cell): the counselor's and the Overseas Admin's **Students**
section (application rows with a student login; bridged agency rows without one get no link) and the Overseas Admin's **Users**
directory (overseas student rows, so a walk-in with no application is reachable). The counselor's walk-in list rows get a "Notes" link.
`ccrm-009` will later host the same panel in the student 360 Activities tab.

## Builder's calls (owner: proceed with recommended answers)

- N1 — overseas_admin only among admins (csc-005 C13 precedent); super_admin excluded.
- N2 — the Overseas Admin may also write notes (CC3: escalation point).
- N3 — a counselor attaches only to applications assigned to them; the admin to any of the student's applications.
- N4 — all notes visible to anyone with the student in scope, including a previous counselor's notes; append-only.
- N5 — ccrm-004 (appointment outcome notes) joins this history when it is built; not this item.

## Security review (Phase 3)

IDOR: scope checked in the service before any read/write; out of scope = 404. Role escalation: role + division checked on every call.
Input: Pydantic length bounds, `extra="forbid"`, UUIDs typed. XSS: text only. CSRF: the existing cookie-auth + same-origin rules
(`sendJson`) as every other POST. SQL: ORM only. No secrets/PII in logs. Rate limit: not added (internal staff, no mail sent).

## Tests

`test_ccrm_010_student_notes.py`: counselor adds/reads notes (own app student, linked walk-in); note on own application; note on another
counselor's application → 422; foreign application → 422; out-of-scope student → 404; unknown / non-student → 404; blank/too long/extra
field → 422; admin reads + writes any student and any application; previous counselor's notes visible after reassign; student, agent,
IT counselor, super_admin → 403; anonymous → 401; paging newest first; students section and admin users directory carry the
`student_notes` column, other sections unchanged. Migration up/down test. Vitest: panel loads, empty state, posts, error kept;
DataTable renders the link. e2e: counselor writes a note on a walk-in student, admin sees it.
