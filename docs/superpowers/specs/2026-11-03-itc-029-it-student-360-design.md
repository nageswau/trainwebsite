# itc-029 — IT student 360 for counselor, HR and admin (design)

**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-029 (classification `UNVERIFIED` PDF §6/§11/§12, owner-approved for build in
waves by Q-01, 2026-11-01). **Decision:** `DEC-SCOPE-360`. **Dependencies (all merged on `main`):** itc-003 (counselor link), itc-013
(fee account), itc-021 (attendance policy), itc-023 (risk flags), itc-026 (resumes), itc-027 (HR review), itc-028 (notes). itc-022
(computed progress, structured trainer feedback) is **not** built; its sections use today's data (S6). **Q-28 is unanswered**; the
builder's call is S3 (`NEEDS_CONFIRMATION`).

## Intent

A counselor, HR or the IT Admin today opens four or five pages (profile, notes, resumes, fee, at-risk) to understand one IT student. The
PDF (§11 screen 2) asks for one 360 profile: contact details, timeline, course, notes, documents, fee, attendance, progress, HR stage
and notifications — each section read live from its own source record, so it is never stale (§14, AC1).

## Behaviour

1. **No new table, no migration.** `services/it_student_360.py` is a read-only aggregator over the existing services' readers
   (`fee_accounts.accounts`, `student_resumes.listing`, `hr_reviews._staff`, `it_student_notes.page`, `lead_timeline.page`,
   `training_progress.attendance`). Nothing is copied, so a write anywhere shows on the next read (AC1).
2. **API** (`api/it_student_360.py`, one role-scoped route like itc-028's notes):
   - `GET /it/students/{id}/360` → `{student, viewer, sections, ...one key per allowed section}`; `Cache-Control: no-store`.
   - `GET /it/students/{id}/360/lead-timeline?limit&offset` → the itc-003 lead's tel-015 timeline page (pre-conversion history);
     `{items: [], total: 0}` when the student came from no IT lead. Counselor and IT Admin only (the `lead` section's audience).
3. **Scope (S1)** — reuses `it_student_notes.staff_student`: the IT counselor their itc-003 linked students, HR (`hr_team` with
   `student_progress.view`) the nehn-017 placement pool, the IT Admin any IT student. A trainer and every other role → 403 (the
   backlog names counselor, HR, admin only). A student out of scope, a non-IT user, or a missing id → the same 404 (AC2).
4. **Sections and the per-role allow-list (S2/S3)** — a section the reader may not see is *omitted* (no key), never `null`:

   | Section | Content | Counselor | IT Admin | HR |
   |---|---|---|---|---|
   | `contact` | email, phone, the itc-003 counselor | ✓ | ✓ | ✓ |
   | `profile` | itc-012 city, qualification, emergency contact, calls preference | ✓ | ✓ | — (itc-012 C1) |
   | `lead` | the converted IT lead (code, stage, owner, dates, link) — its timeline via the route above | ✓ | ✓ | — |
   | `enrollments` | course, batch, trainer, status, effective dates/mode, progress %, attendance % (itc-021 policy) | ✓ | ✓ | ✓ (attendance % only with `attendance.view`, nehn-017's rule) |
   | `fee` | itc-013 account per enrolment + the total balance | ✓ | ✓ | — (Q-28) |
   | `risk` | open itc-023 flags (reasons, figures, raised at) | ✓ | ✓ | — (itc-023 R8 readers) |
   | `feedback` | the 5 latest graded assignment / assessment feedbacks (title, score, excerpt ≤ 300, grader, date) | ✓ | ✓ | ✓ |
   | `resumes` | itc-026 versions (version, type, size, visibility, uploader, date); HR sees `hr` versions only, as on its own route | ✓ all | ✓ all | ✓ `hr` only |
   | `hr_review` | itc-027 staff view (stage, owner, next action) | ✓ | ✓ | ✓ |
   | `notes` | itc-028: the 5 latest notes + total (staff read all notes, N3) | ✓ | ✓ | ✓ |
   | `notifications` | the 10 latest in-app notices sent to the student: title, event type, sent at, read — never the body | ✓ | ✓ | — |
5. **Query count (AC3)** — a fixed number of queries whatever the number of enrolments, notes or resumes (batched `IN` reads). The test
   pins **≤ 22** for the IT Admin and asserts the count is the same for a student with one and with three enrolments.
6. **UI** — `ItStudent360Page` (server component, `ItStudentNotesPage` pattern): the API is the gate; each reader stays in their own
   portal (an IT counselor opening the admin path is redirected). Pages:
   `/it/counselor/students/[id]`, `/it/admin/students/[id]`, `/it/hr/students/[id]/360`. One `action-card` per section in the table's
   order; an empty section says so ("No enrolments yet."). The lead timeline reuses `LeadTimeline` (client, its own loading / failed /
   empty states and "Show older"). Links out to the existing Profile, Notes and lead pages. A failed load → `accessUnavailable` card; 404 /
   422 → `notFound()`.
   - Entry points: an **Open** button (the existing `student_360` DataTable type) on the counselor's My Students and the IT Admin's
     Students tables; a **360 view** button on HR's student page (`HrStudentPage`).

## Calls made by the builder (`NEEDS_CONFIRMATION`)

- **S1:** a trainer gets no 360 (403) — the backlog's roles are counselor, HR and IT Admin.
- **S2:** single route `/it/students/{id}/360` (itc-028's newest pattern) instead of the backlog's `/counselor/it/students/{id}/360`.
- **S3 (Q-28):** HR's 360 omits `fee`, `profile`, `lead`, `risk` and `notifications` — matching HR's existing rules (nehn-017 "nothing
  financial", itc-012 C1, itc-023 R8) so no new data reaches HR.
- **S4:** notifications show title and event type only (bodies of pre-itc-002 notices are free text).
- **S5:** reading a 360 is not audited (no other read of these sections is; the resume *download* audit stays on its own route).
- **S6:** until itc-022: progress % is `Enrollment.progress_percent` (trainer-entered) and "trainer feedback" is graded
  assignment/assessment feedback.

## Non-goals

No write from the 360 (every edit stays on its own page and route). No change to existing routes, tables or the HR student page's data.
No 360 for trainers or students. No PDF/export.

## Acceptance criteria (testable)

1. After an update (a payment recorded, a note added), the next 360 read shows it (no cache, `no-store`).
2. Out-of-scope requests return 404 (unlinked counselor, HR outside the pool, non-IT user, missing id); trainer / overseas counselor 403.
3. Query count ≤ 22 and independent of the number of enrolments.
4. + After accounts records a payment, the counselor's 360 shows the new balance.
5. − HR's 360 has no `fee` key (and no `profile`, `lead`, `risk`, `notifications`).
6. E: a student with no enrolment yet → empty `enrollments`, `fee.accounts` empty, balance `null`; the page says "No enrolments yet."

## Regression risks

Low: a new read path. The two portal tables gain one column (existing column tests are updated deliberately).
