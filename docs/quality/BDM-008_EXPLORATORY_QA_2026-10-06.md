# bdm-008 — Exploratory browser QA and Playwright (2026-10-06)

**Build under test:** `feature/bdm-008-follow-ups`, compose project `bdm008qa` (web `localhost:3108`, API `localhost:8108`, DB at
`0076_bdm_tasks_followups`, seeded). The web container was rebuilt after the fixes below and every scenario re-run.
**Tools:** Browser Use is not installed on this machine; as for bdm-007, the pass used throwaway Playwright scripts in the `web-test`
container — an isolated Chromium per scenario (base URL `http://host.docker.internal:3108`) recording console errors, page errors,
4xx/5xx responses and failed requests, with screenshots. Scripts were kept outside the repository; evidence in `artifacts/ci/pw008/`
(git-ignored).
**Accounts and data** (real admin API + welcome tokens): BDM Manager A (team: College BDM1, College BDM2), BDM Manager B (no team).
BDM1: organizations "QA Lotus College", "QA Banyan University", "QA Archive College"; six manual items (today, university, a 200-char
unbroken title with a 600-char unbroken note, an upcoming task, one on the organization to archive) plus one item moved three days into
the past by SQL (the API never accepts a past due date) and one meeting-report follow-up (appointment moved into the past by SQL, then
completed through the API with a follow-up date).

## Coverage (final run: 15 / 15 scenarios pass, 0 page errors)

| # | Area | Result |
|---|---|---|
| 1 | Happy path | Pass — nav "Follow-ups" → tabs `Today (2) · Overdue (1) · Upcoming (4)`; chips College 1 / University 1; pressing College filters the list to 1 row (= the chip) with `aria-pressed`; Overdue shows "Overdue · 3 days" in words; Done → "Marked done." + Log activity / Book appointment; Log activity opens the organization |
| 2 | Meeting-report follow-up | Pass — "From APT-…" link opens the appointment; Done offered; no Edit / Cancel task |
| 3 | Forms + keyboard | Pass — focus on Title; required messages with no request; Escape closes, **focus back on Add (QA8-02)**; double-click Add → one POST (201) and one row; edit → "Changes saved."; cancel needs a reason; cancelled item kept with its reason |
| 4 | Errors | Pass — list 500 → "Unable to load follow-ups." + Retry recovers; Done offline → the connection message, row kept; Done 409 → "…changed elsewhere — the list has been reloaded." |
| 5 | Empty states | Pass — BDM2 "Nothing due today." + Add; filtered "No items match these filters." |
| 6 | Manager A / B | Pass — A reads BDM1's items with assignee, no Done / Add, organization links to the manager view; manager on `/bdm/follow-ups` → access unavailable; B sees nothing of A's team |
| 7 | Signed out | Pass — `/bdm/follow-ups` → `/bdm/sign-in?next=…`; `/bdm/manager/follow-ups` → `/admin/login`; API 401 |
| 8 | Organization section | Pass — open items listed; Add task from the section; Archive → section reloads to "No open follow-ups or tasks.", no Add task; the items show under Cancelled with "Organization archived" |
| 9 | Widths 1440 / 1024 / 768 / 390 / 320 | Pass after QA8-01 — no horizontal overflow with the list and with the form open |
| 10 | Keyboard on tabs | Pass — Enter on a tab switches it, `aria-current="page"`, focus stays on the tab |

Console: only the browser's "Failed to load resource" lines for the intentional 500 / 409 / offline cases.

## Issues (all fixed test-first, re-checked in the browser)

| ID | Severity | Finding | Fix |
|---|---|---|---|
| QA8-01 | High (layout) | A 600-character unbroken note (or reason) rendered on one line: the page scrolled sideways by ~2 900–3 700 px at every width, 320 px included | Notes and cancel reasons use `overflow-wrap: anywhere` with `pre-wrap` (`BdmTaskItem`); test `wraps unbroken notes and reasons…` |
| QA8-02 | Medium (a11y) | Escape on the add form left focus nowhere — the Add button had been unmounted while the form was open. Same for Edit / Cancel task on a row | Focus returns to the opener (`useFocusAfterRender`, `BdmTasksPanel` / `BdmTaskItem`); tests `returns focus to Add…`, `returns focus to Edit / Cancel task…` |

Test-only corrections (product unchanged): the e2e spec's `getByLabel("Task")` also matched the form "Add follow-up or task" → the
radio by role; its `name: "Done"` also matched the "Done (n)" tab → `exact: true`.

## Playwright (`--workers=1`, against this stack)

- `bdm-008-follow-ups.spec.ts` — **passed** (twice, after the selector fixes).
- Neighbouring specs on the same build: `bdm-002-organization-crm` (2), `bdm-006-appointments`, `bdm-007-meeting-reports`,
  `bdm-009-activities` — **5 passed**.

**Not covered here:** the full backend / web suites (owner), the independent Codex review.
