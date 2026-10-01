# AGN-005 — Browser QA (2026-10-01)

**Build:** branch `feature/agn-005-staff-permission-matrix`; isolated Compose project `agn005` (web `:3005`, API `:8005`), seeded demo data.
**Browser:** isolated headless Chrome (own profile, CDP port 9235) driven by browser-use.
**Accounts:** Master `agent@edusphere.local` (EDU-M001); staff EDU-S001 Priya and EDU-S002 Ravi, created on the Team page and activated
through the admin welcome-link flow; `student.overseas@`, `overseasadmin@`, `superadmin@edusphere.local`.

**Method limits (recorded).** CDP mouse and key events were not delivered to the page in this environment (the harness doctor reported
healthy), so controls were found by accessible role and name and clicked through the DOM (`element.click()`, which runs the app's
handlers); Tab/Enter keyboard traversal was not exercised in the browser (it is covered by vitest and AGN-004's keyboard-only
Playwright test). Native `confirm`/`beforeunload` dialogs were answered from the script. 5xx and offline were injected in the page's
`fetch` for the student routes only. A university named "e31-… Uni" is pytest data from the shared database, not a product issue.

## First pass — findings

| ID | Severity | Role | Page | Finding | Status |
|---|---|---|---|---|---|
| QA5-01 | Low–Medium | Master, Staff | Students → Add/Edit | Phone accepted any text: "abc" saved (`phone='abc'`, `phone_digits` NULL), so it could never match as a duplicate | **Fixed** `fb32c4f` |
| QA5-02 | Medium (a11y) | Master, Staff | Students → Add student | Focus fell to `<body>` on open (opener disabled), and was not returned after Cancel or a save | **Fixed** `fb32c4f`, `df9a563` |
| QA5-03 | Low (copy) | Staff | Students | Intro said "Every student of your agency…" while staff see only their assigned students | **Fixed** `efb797f` |
| QA5-04 | — | — | Students | Raw "Internal Server Error" on a 5xx — an artefact of the injected JSON body; a real plain-text 500/502 shows "Unable to load students." with Retry | **Withdrawn** |
| QA5-05 | Low | Super Admin | `/overseas/agent/students` | Panel showed "This role cannot perform this operation" with a Retry that cannot help, and an Add student form that can only fail | **Fixed** `efb797f` |

Owner decisions (in-session 2026-10-01): QA5-01 reuses the school mobile rule (`schemas._MOBILE`); QA5-05 shows a note instead of
the panel (the API refusal is unchanged).

## First pass — passed

Happy paths (Master add/edit/archive/unarchive/assign with confirm, Cancel and focus return; staff assigned-only view, add, edit; no
Archive/Unarchive/Assign or "Assigned to" filter for staff); **AGN-005-AC06** (staff with Show archived see View only; detail
read-only); staff direct API calls (own archive/unarchive/assign `403` with the exact messages, another staff member's student `404`
for view/edit/archive/assign, team/permissions/reports `403`; database and audit unchanged); invalid inputs (name, email, year caught
client-side; duplicate email any case warns); duplicate submission (3 clicks → 1 POST → 1 row); Cancel/discard prompt both answers;
refresh/Back/Forward keep `?archived=1`; loading, empty, 5xx, offline, Retry; failed edit/create keep the entry; failed archive
announced on the card; signed out → login redirect, API `401`; student and Overseas Admin → "Access unavailable", API `403`; Reports
toggle on/off applies on the staff member's next request; 1440/820/390 px with no page overflow; no broken images; no console errors.
Confirmed again: a malformed assign body gets `422` before the staff `403` (AGN-004 behaviour, recorded in the spec §10).

## Re-check after the fixes (rebuilt `agn005` web + API)

| ID | Observed |
|---|---|
| QA5-01 | Form: "abc" → "Enter a phone number of 7–20 digits, spaces, +, -, ( or ) with at least 7 digits", focus on Phone, no request. API: a 4-digit phone → `422 invalid_phone` on `body.phone`. `(022) 2345-NNNN` saves. A student saved with "abc" before the rule was renamed (PATCH 200, phone kept, one audit row). |
| QA5-02 | Open → focus on Full name; Cancel → focus on Add student; after "… added." → focus on Add student. (The first fix focused on the next frame and missed after a save; re-fixed with an effect, `df9a563`.) |
| QA5-03 | Staff intro: "Students assigned to you, with or without a login. Those who have a login also appear under Application status below." Master intro unchanged. |
| QA5-05 | Super Admin: "Agency student records are managed by the agency's own Masters and Staff."; no Add student, no Retry; no `/crm/students` request. |

Console: no errors. Playwright (`--workers=1`, against `:3005`): agn-002, agn-003, agn-004, agt-002 — **9 passed**.
