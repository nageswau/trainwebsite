# ccrm-009 — Counselor student 360 page (design)

NO-ASSUMPTION MODE. Source: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` §`ccrm-009` (spec PDF §5, `UNVERIFIED`, owner request).
Dependency `ccrm-007` is merged (PR #311). Decision: `DEC-SCOPE-253`. API §12FF. RBAC §2.168. **No migration.**

## Intent

One place where the overseas counselor (and the Overseas Admin) sees everything about one student, instead of hopping between
the application table, the notes page and the profile page.

## Owner answers (2026-10-24)

- **V1 — scope inside the page:** a counselor who can see the student (csc-001: owns one of the student's applications, or is linked
  to the student) sees **all** the student's applications, current documents and history, read-only, each application marked
  "yours" or not. Every write and every download keeps today's rule (own applications only); the page offers a download only where
  that rule allows.
- **V2 — tab layout:** Academic = Personal details + Academic history + Work experience; Preferences = Study preferences;
  English = English tests. Each tab saves the whole profile (ccrm-007 P5), so a save on one tab never wipes another tab.

## Builder's calls (recommended defaults, `NEEDS_CONFIRMATION`)

- **B1** Hidden tabs: Finance (ccrm-039) and the journey stage (ccrm-017) are not built, so they are not shown. Messages are not shown
  in Activities (no per-student message read exists for the counselor).
- **B2** Activities = notes (ccrm-010 panel, reused), the student's appointments, and the leads linked to the student (tel-018
  `converted_user_id`) with their stage; the counselor gets a link to the lead page only for a lead they own.
- **B3** History = status history of all the student's applications (ccrm-016 helper, staff view) + audit rows about the student
  (profile saves, account edits, creation, counselor assignment, link resends) + document uploads, reviews and replacements. Newest
  first, latest 200 entries, author name shown, field names only (never values).
- **B4** Lazy tabs = link tabs (`?tab=`); the server fetches only the selected tab's data. The ENH-013 school `Student360Tabs` is not
  reused because it renders every panel up front; its `s360-*` styles are.
- **B5** The existing `/students/{id}/notes` and `/students/{id}/profile` pages stay as they are. The counselor student table and
  the admin Users table gain an **Open** link to the 360.
- **B6** Overview: name, student ID, email, phone, account status, assigned counselor, application counts (total / open), documents
  awaiting review, next actions of the open applications.

## API (all `GET`, read-only, under `/api/v1/counselor/students/{id}`)

| Route | Returns |
| --- | --- |
| `/overview` | `student`, `counselor`, `account_status`, `applications[]` (code, university, course, intake, stage + label, sub-status label, outcome summary, next action, counselor name, agency flag, `mine`), `counts` |
| `/documents` | current (non-archived) documents of the student: type, label, application code, status + label, expiry, reviewer, reviewed_at, uploaded_at, `can_download` |
| `/activities` | `appointments[]` (type, time, mode, status, staff name), `leads[]` (code, stage label, owner name, `href` or null) |
| `/history` | `items[]` (`at`, `kind` = status/audit/document, `summary`, `actor`, `application_code`) |

Authorization: `student_profiles.staff_student` (overseas counselor with csc-001 scope, or Overseas Admin; else 403; out of scope or
not an overseas student → 404). Profile and notes tabs use the existing ccrm-007 / ccrm-010 routes.

## UI

`/overseas/{counselor|admin}/students/[id]` — `PortalShell`, header (name, student ID, back link), link tab bar (Overview,
Academic, Preferences, English, Documents, Applications, Activities, History), one panel. Reader in the wrong portal is redirected to
their own (ccrm-010 QA-02 rule); a 404/422 is `notFound()`, another role the 403 card. A failed tab load shows an inline error card
with the rest of the page intact. Empty tabs say so in words.

## Non-goals

No writes on the 360 beyond the reused profile form and notes panel; no new tables; no change to existing scopes or routes.

## Acceptance

- A student with three applications shows three independent statuses (backlog AC).
- Another counselor's student → 404 (backlog AC); a student/agent/IT counselor → 403.
- A linked counselor sees an application owned by another counselor marked not-yours, and its document has no download.
- Saving the Preferences tab keeps the qualifications entered on the Academic tab.
- Tabs fetch only their own data; no console errors; works at 375 px.
