# AGN-017 — Exploratory browser QA (first pass, 2026-10-02)

**Build:** `feature/agn-017-notifications` @ `f07c7fd` (the stack was built from this worktree). **Stack:** isolated compose project `agn017qa` — web http://localhost:13017, API 18017, `alembic` head
`0061_agent_notifications`, `python -m app.seed` applied, worker and beat running, no email webhook/SMTP configured.
**Browser:** Browser Use 0.13.10 (`uvx`), attached over CDP (port 9317) to an isolated headless Chromium 153 with a fresh profile.
Trusted input was verified first (capture-phase listeners: `mousedown`/`click` `isTrusted: true` on the first page and after a
navigation — the AGN-013 failure did not reproduce). Console errors, uncaught exceptions, HTTP ≥ 400 and failed requests were collected
from CDP (`Runtime`, `Log`, `Network`) on every step. **No product code was changed during this pass.**

**Data.** Created through the running app's API only (no direct database writes): seeded Master `agent@edusphere.local`; two new staff
logins (`QA Staff One` `EDU-S004`, `QA Staff Two` `EDU-S005`, activated through the Overseas Admin welcome link); a no-login student
assigned to Staff One and one unassigned. The Master assigned the student, requested a Passport, created a task (due in 2 days) and an
already-overdue task, created an application (deadline = tomorrow, India date) and advanced it. The daily job was run by calling the
beat task (`app.worker.send_daily_reminders_task`) in the API container.

## Results by check

| # | Check | Result |
|---|---|---|
| 1 | Happy path | PASS — Staff One: nav "Notifications 7 unread"; page lists 7 notices newest first (Overdue tasks, Deadline tomorrow, New task ×2, Application status changed, Document requested, Student assigned to you), each with "new", the body, a time, and "Open: {title}" to the right section. Every notice had exactly one `email` delivery, recorded `not_configured` (no webhook), never raised. Job run twice more: `{'created': 0, 'duplicate': 2, 'failed': 0}` both times. |
| 2 | Invalid inputs | PASS — document request "Other" with label `<img onerror…>rahul@example.com\r\nBcc: …` accepted by AGN-009 (see QA17-10) but the notice says only "A document was requested…"; a task title with CR/LF is refused (422) by AGN-016; invalid `due_at` 422; `PATCH …/not-a-uuid/read` 422; unknown id 404. No HTML, email or CR/LF in any notice. |
| 3 | Empty states | PASS — Staff Two and the seeded Master: "No notifications yet. You'll be told here about assignments, document requests, status changes, new tasks and upcoming deadlines."; no badge; nav name "Notifications". |
| 4 | Server errors | PASS (feature) / QA17-08 (pre-existing) — mark-read forced to 500 (CDP `Fetch`): navigation still happens, the notice stays unread, no error shown (fire-and-forget by design). API container stopped: the page answers after ~5 s with "Access unavailable — fetch failed — Return to login" (QA17-08). The list-only failure state ("This section couldn't load") cannot be produced black-box; covered by component tests. |
| 5 | Loading states | QA17-07 — 2.5 s latency: clicking Notifications leaves the previous page with no indicator until the new page arrives (same as the other agency sections). |
| 6 | Cancel / back | PASS — Open → Students; browser Back → Notifications with the count re-read (6). |
| 7 | Refresh | PASS — reload keeps the read state (6 unread). |
| 8 | Duplicate submission | PASS — rapid double-click on Open: one navigation, one read. Two concurrent identical status changes: 200 + 409, exactly one notice. Two concurrent identical assigns: 200 + 200, exactly one "Student assigned to you". Reading the same notice twice: 200 both. Job re-run: no duplicates. |
| 9 | Unauthorized user | PASS — signed out → `/overseas/login?next=%2Foverseas%2Fagent%2Fnotifications`; API `unread-count`/list 401; another user's notice 404; deactivated staff's old session 401 and sign-in refused; pending (unapproved) agency → "Access unavailable — Agent registration is pending approval". |
| 10 | Incorrect role | PASS — counselor, overseas student, Overseas Admin, School Principal → "Access unavailable — Role/division mismatch". Super Admin → the agency note, no badge, plus the admin "Send notification" panel (QA17-06). |
| 11 | Desktop layout | PASS — 1280×900: sidebar item with a compact count badge; card list; no overflow. |
| 12 | Tablet layout | PASS with QA17-05 — 768×1024: collapsed menu, list readable, Open buttons on the right, no overflow. |
| 13 | Mobile layout | PASS with QA17-05 — 375 and 320 px: no horizontal overflow; full-width Open buttons (≥ 44 px tall); menu item "Notifications (4 unread)". |
| 14 | Navigation | PASS — Notifications after Tasks for Master and Staff; `aria-current` on the page; each Open goes to its section; keyboard: focus Open + Enter navigates. Badge on every agency page. |
| 15 | Success messages | N/A — the page has no forms; reading is silent by design. |
| 16 | Error messages | See 4 and QA17-08. |
| 17 | Broken images | PASS — none on any page visited. |
| 18 | Console errors | PASS — none, except those the step itself caused (offline, wrong password). |
| 19 | Failed network calls | PASS — none outside the injected failures. |
| 20 | Unexpected redirects | PASS — only the expected sign-in redirect with `next=`. |

The committed e2e spec `tests/e2e/agn-017-notifications.spec.ts` was also run against this stack: **2 passed** (17.4 s).

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA17-01 | Medium | Staff | Any agency page after Open | Notifications (7 unread) → Open "Student assigned to you" | Students page shows 6 unread | Students page still shows "Notifications 7 unread"; corrects on the next page load (Back showed 6) | Read PATCH is `keepalive` fire-and-forget while the link navigates; the destination is rendered before the PATCH lands (review M7). No console/network error. |
| QA17-02 | Medium | Staff | Notifications | Two students with work; read the list | Each notice says which record it is about, or Open goes to that record | Bodies say "one of your students"; Open goes to the section list (`/overseas/agent/tasks`, `/documents`, …), not the task/student/application | By design (spec §8: no names); with several students the staff member must search. Product decision needed (e.g. link with a record id, or the agency code if one is added). |
| QA17-03 | Low | Staff (screen reader) | Notifications | Two "New task" notices | Distinct link names | Two links both named "Open: New task" | AX names: `Open: New task` ×2 (WCAG 2.4.4/2.4.9 ambiguity). |
| QA17-04 | Low | Staff | Notifications | Master creates a task already past due | Wording fits a past due date | "A new task on one of your students is due 01 Oct 2026." (on 2 Oct), plus a separate "Overdue tasks" digest | Notice row 3 in the list; DB row title "New task". |
| QA17-05 | Low | Staff | Tablet/mobile (≤ 768 px) | Open the page on a phone | The unread count is noticeable without opening the menu | The count appears only inside the menu, near the bottom of a long list ("Notifications (4 unread)") | Screenshots `04-small-notifications`, `05-small-menu`. |
| QA17-06 | Low | Super Admin | `/overseas/agent/notifications` | Sign in as Super Admin, open the agency Notifications page | Only the agency note | The admin "Actions — Send notification" form (recipient reference, title, message, channels, URL) appears under the note | Screenshot `08-super-admin` (review M5; the generic WorkflowPanel). |
| QA17-07 | Low | Staff | Notifications (navigation) | 2.5 s latency, click Notifications | Some loading feedback | Previous page stays, no indicator, until the new page renders | CDP `Network.emulateNetworkConditions`; same for other agency sections (spec §9 ruling). |
| QA17-08 | Low (pre-existing) | Any signed-in | Any portal page | Stop the API container, load the page | A "temporarily unavailable, try again" message | After ~5 s: "Access unavailable — fetch failed — Return to login" | `curl` 200 in 5.0 s, card text `fetch failed`; shared `accessUnavailable`, not AGN-017 code. |
| QA17-09 | Info | Staff | Notifications | Mark-read PATCH fails (500) | — | Navigation proceeds, notice stays unread, nothing shown | Fire-and-forget by design; acceptable. |
| QA17-10 | Info (other feature) | Master | Document requests (AGN-009) | Request "Other" with a label containing HTML and CR/LF | Same control-character rule as tasks | 201, label stored with CR/LF (tasks refuse them: 422) | Not AGN-017; the notice never shows the label. |

Screenshots: `.superpowers/sdd/2026-10-02-agn-017-notifications/qa-shots/` (git-ignored). No code was changed.

## Fix pass (2026-10-03)

Each fix was test-first (the test seen failing for the expected reason, then passing); the stack `agn017qa` was rebuilt from the fixed
tree and every fix re-checked with Browser Use on the same isolated Chromium. No console errors, HTTP ≥ 400 or failed requests.

| ID | Fix | Test (RED → GREEN) | Browser re-check |
|---|---|---|---|
| QA17-01 | The agency list waits for the read (at most 1.5 s, failure or not) before navigating on a plain click; modified clicks are left to the browser | `SchoolNotificationList.test.tsx` › readBeforeOpen ×4 | Open from "8 unread" → Applications shows **7** |
| QA17-03 | Each Open link is `aria-describedby` its notice text (names unchanged) | › "describes each Open link by its notice's text" | AX tree: `Open: New task` ×4, each with its own description |
| QA17-04 | A task created past due: "was due {date} and is overdue." | `test_agn_017_events.py::test_a_task_created_already_past_due_says_it_was_due` | "A new task on one of your students was due 30 Sep 2026 and is overdue." |
| QA17-05 | Below 980 px the top bar links the unread count (`.topbar-unread`) | `PortalShell.badge.test.tsx` ×2 | Hidden at 1280; shown at 768 and 375 (0 px overflow); tap → Notifications (screenshot `12-recheck-mobile-topbar`) |
| QA17-06 | No generic WorkflowPanel on the agency Notifications page | `PortalPage.agentNotifications.test.tsx` (Super Admin case) | Super Admin: 0 forms, no "Send notification" |

Not changed: QA17-02 (owner decision 2026-10-03: keep as designed — no names, section links; `DEC-SCOPE-055` N11), QA17-07 (spec §9 ruling), QA17-08
(pre-existing shared card), QA17-09 (by design), QA17-10 (AGN-009). Evidence: backend events + AGN-016 create/read 38 passed; web 8 files /
53 passed plus 12 neighbouring files (school pages that render the list or the shell) 75 passed; `tsc` 0; eslint 0 on the changed files;
Playwright on the rebuilt stack: `agn-017` 2, `enh-005` 2, `enh-023` 1 — 5 passed.
