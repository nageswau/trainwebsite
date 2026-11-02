# itc-028 — Internal vs student-visible IT student notes (design + plan)

`DEC-SCOPE-351` · migration `0234_it_student_notes` · API §12IW · RBAC §2.251 (numbers one past the active siblings itc-021 /
itc-026; renumber only this feature's lines on merge).

## Source and authority

- `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-028 (PDF §2 access rule, §9 "respecting field-level visibility", §10 "field-level
  visibility for internal notes, HR screening comments, and student-facing messages"). The PDF is `UNVERIFIED`; the owner's Q-01 answer
  (2026-11-01) approved all phases for build in waves. Dependency itc-003 (`DEC-SCOPE-337`) is built.
- The owner asked to proceed with recommended answers. Every call below marked **(call)** is the builder's and `NEEDS_CONFIRMATION`.

## Intent

Counselors, HR and trainers keep notes on an IT student. By default a note is internal. The author can explicitly share a note with the
student, and the student then sees it in an "Updates" feed on their portal. **The main risk is a leak**: internal text must never reach
any student response or notification.

## Decisions

- **N1 — table (Q-03 notes part) (call):** a new IT-only table `it_student_notes`. This follows the owner's itc-003 answer (IT-only
  tables; overseas code untouched). The overseas `overseas_student_notes` and ccrm-010 are not changed.
- **N2 — writers and readers (staff), each in their existing scope; anything outside it is 404, any other role 403:**
  - IT counselor (`counselor`, division `it`): students linked to them (itc-003).
  - HR (`hr_team`): the nehn-017 HR population, with the `student_progress.view` grant HR's student page already needs.
  - Trainer (`trainer`): students seated (enrolment status not `pending_consent`/`rejected`) in a batch they teach.
  - IT Admin (`it_admin`, division `it`): any IT student (PDF §2 Admin/CRM Manager).
  - Not super_admin, placement or overseas roles (itc-003 C1 precedent) **(call)**.
- **N3 — staff see all notes on a student they can reach, whoever wrote them (call):** this is the "one shared student record". It is
  restricted only for the student.
- **N4 — a note starts internal and is append-only:** body ≤ 4000 characters, not blank; no edit or delete (ccrm-010 precedent). This
  answers the backlog's edge case "editing a shared note": to correct a note, write a new one **(call)**. `extra="forbid"`, so a create
  request cannot set visibility.
- **N5 — visibility changes only by an explicit action:** `PUT …/notes/{note_id}/visibility {visibility: internal|student}`. Only the
  note's author or the IT Admin may change it (403 otherwise). Setting the same value is a no-op (`changed: false`, no audit, no
  notice). A change writes the audit row `it.student_note.visibility` with before/after visibility, using the itc-001 `audit_change`
  helper (ids and visibility only, never the body). Un-sharing a note shared by mistake is allowed **(call)**. The UI asks for
  confirmation before sharing.
- **N6 — Q-27 second approver: no** (one explicit, confirmed, audited action) **(call)**.
- **N7 — the student feed:** `GET /it/me/updates` (IT student only, 403 otherwise) returns only the student's own `student` notes,
  newest share first. Its serializer uses an explicit allow-list: `id`, `body`, `author_name`, `author_role`, `shared_at`. There is no
  `visibility`, author id or internal timestamps.
- **N8 — notice on share (call):** sharing sends the student one generic in-app Notification ("New update from your {role}",
  `action_url=/it/student/updates`). It never includes the note text. Un-sharing sends nothing.
- **N9 — pagination:** the staff list and the feed use `limit` (1–100, default 20) / `offset`, the `Page` shape.

## API (§12IW)

| Method | Path | Who | Result |
|---|---|---|---|
| GET | `/api/v1/it/students/{student_id}/notes?limit&offset` | N2 staff | `{student, items[], total, limit, offset}` |
| POST | `/api/v1/it/students/{student_id}/notes` `{body}` | N2 staff | 201 note (internal) |
| PUT | `/api/v1/it/students/{student_id}/notes/{note_id}/visibility` `{visibility}` | author / IT Admin | `{…note, changed}` |
| GET | `/api/v1/it/me/updates?limit&offset` | IT student | page of allow-listed items |

A staff note item: `id, body, visibility, author_name, author_role, created_at, shared_at, can_change_visibility`. A malformed UUID is
422, as everywhere else.

## UI

- `components/ItStudentNotesPage.tsx` (server page) and `ItStudentNotesPanel.tsx` (client). There is one page per portal:
  `/it/{counselor|admin|hr|trainer}/students/[id]/notes`. If a user opens another portal's address, they are redirected to their own
  portal (QA-01 pattern). A 404/422 shows Not found, and a 401/403 shows the access card.
- Panel: an add form (counter, keeps the text on failure, guards against double submit) and a history list. Each note shows author, role
  badge, time and an "Internal" or "Shared with student" badge, with a "Share with student" or "Stop sharing" button (behind
  `window.confirm`) for the author or the admin. It has load more and error, empty and loading states.
- Links: a Notes button in the IT counselor's My Students and the IT Admin's Students tables (existing `student_notes` column type), on
  HR's student page, and in each row of the trainer's Student Progress table.
- Student: a new "Updates" nav section `/it/student/updates`. Its portal payload is header-only, and the panel reads `/it/me/updates`
  (with empty, error and load-more states).

## Security review (Phase 3)

- IDOR: every staff route resolves the student through the caller's scope query, so an out-of-scope student is the same 404 as a
  missing one. The note is fetched with `student_user_id == student.id` (another student's note id → 404).
- Escalation: visibility can be changed only by the author or the IT Admin, and the request body is `extra="forbid"`.
- Leak (AC1): student serializer allow-list; generic notice; a sweep test (below). Logs carry ids only and never the body.
- XSS: React text rendering only (no `dangerouslySetInnerHTML`). CSRF: the existing cookie and same-site setup with the `sendJson`
  helper. SQLi: ORM only.

## Tests (TDD)

Backend `tests/test_itc_028_it_student_notes.py`:
1. The counselor adds a note; it is internal by default; the list shows it with the author and role.
2. Scope: a counselor on an unlinked student, a trainer of another batch, and HR without the grant or outside the pool → 404/403. Overseas
   counselor, placement and super_admin → 403. An IT student on staff routes → 403.
3. Validation: a blank or 4001-character body → 422; an extra field (`visibility`) on create → 422; a bad visibility → 422.
4. Share: author-only (another staff member → 403; IT Admin → ok); the audit row has before/after and no body; a no-op does not audit;
   the student gets one generic notice without the text; un-share removes the note from the feed.
5. Feed: the student sees only their own shared notes; the keys equal the allow-list; another student's notes never appear; a note id of
   another student → 404 on the visibility route.
6. **AC1 sweep:** plant an internal sentinel and a shared one. As the IT student, GET every parameter-less API route plus every
   `/portal/it/student/{section}` and assert the internal sentinel is absent. Every notification row of the student must also lack it.
   The positive control is that the shared sentinel appears in `/it/me/updates`.
7. Migration round trip `tests/test_itc_028_migration.py`.

Web (vitest): the panel's share/unshare flow and the student feed render. Playwright e2e
`tests/e2e/itc-028-it-student-notes.spec.ts`: a counselor adds and shares a note → the student sees it in Updates; an internal note never
shows.

## Plan (small tasks)

1. Model `ItStudentNote` + migration 0234 + migration test.
2. Schemas `ItStudentNoteCreate`, `ItStudentNoteVisibility`.
3. Service `services/it_student_notes.py` (scope, page, create, set_visibility, feed) and router `api/it_student_notes.py`, registered in
   `main.py`; backend tests 1–6 red → green.
4. Portal: the notes link in the counselor and admin student rows; the student `updates` section; `navigation.ts` "Updates".
5. Web: lib + panel + pages + HR/trainer links + student feed; vitest.
6. Docs: API §12IW, RBAC §2.251, DEC-SCOPE-351, backlog status line.
7. Browser QA, e2e, graphify update.

## Regression risks

`portal.py` student rows (itc-003/012 tests), the nav pin tests (`it/student` list), `TrainerProgressPanel` tests, `HrStudentPage`
tests, and migration head pins in sibling tests.
