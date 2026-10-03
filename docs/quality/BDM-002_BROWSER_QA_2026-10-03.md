# bdm-002 — Browser QA, first pass (2026-10-03)

**Scope:** `bdm-002` Organization CRM (`DEC-SCOPE-060`), branch `feature/bdm-002-organization-crm` @ `d88a0d4`.
**Method:** Browser Use (CDP) driving an **isolated** Chrome 154 (throwaway profile, its own CDP port 9333) against the worktree
stack `bdm002` (web `http://localhost:3102`, API `:8102`, migration head `0066_bdm_organizations`, seeded). Exploratory, no code
changed. Console and network were captured through CDP (`Runtime`, `Log`, `Network`) for every step.
**Accounts** (throwaway, created through `POST /admin/users` and activated with the development welcome token; stamp `995117`):
College BDMs A and B and a School BDM (all reporting to Manager One), Manager Two (another team with one College BDM), and the seeded
`itadmin@edusphere.local`.
**Note on data:** the stack shares its database with the `api-test` runs, so the College list also holds test-suite rows (e.g. a
200-character "ß…" name), which made a useful stress case.

## Summary

15 findings: **0 Critical, 0 High, 2 Medium, 10 Low, 3 Info.** Every authorization, scope, validation, duplicate, archive/restore,
reassign, offline and error-state check behaved as specified. No console errors or failed network calls other than the
deliberate 4xx responses (`409` duplicate / archived, `422` validation, `403`/`401`/`404` access probes) and the deliberate
offline / blocked requests.

| ID | Severity | Role | Page | Summary |
|---|---|---|---|---|
| QA-01 | Medium | BDM, manager | Organization list | One long unbroken name widens the Name column and pushes every other column out of view |
| QA-09 | Medium | BDM | Add organization (full load / refresh) | Contact 1's ids differ between server and client render: focus does not move to its error; id collisions possible |
| QA-15 | Low | BDM, manager | Organization list | No loading signal when filters or the page change (stale rows, `aria-busy=false`) |
| QA-14 | Low | BDM (assignee) | Organization detail | Archive is available while the edit form is open; the form stays open and the next Save fails with 409 |
| QA-10 | Low | BDM | Add organization | After "Go back" in the duplicate warning, keyboard focus drops to `<body>` |
| QA-12 | Low | BDM (assignee) | Organization detail | After Cancel / Save changes in the edit form, keyboard focus drops to `<body>` |
| QA-06 | Low | All | Organization detail — Contacts | Contact details are an unlabelled "— · — · — · email" line; designation and role read the same |
| QA-08 | Low | BDM | Organization detail | Refresh (or a shared link) repeats "Organization ORG-… created." (`?created=1` stays in the URL) |
| QA-11 | Low | BDM | Add organization | Cancel discards a filled-in form without asking |
| QA-03 | Low | All | List, detail | Organization-name links and "Back to organizations" look like plain text (no colour or underline) |
| QA-02 | Low | All | Organization list | The code wraps mid-code ("ORG-" / "000249") |
| QA-04 | Low | BDM | Add / edit organization | Student-count error uses the raw validator text "Input should be greater than or equal to 0" |
| QA-05 | Info | BDM | Add / edit organization | A website typed without a scheme ("stjoseph.edu") is rejected; the hint does say to include it |
| QA-13 | Info | BDM (assignee) | Organization detail | Saving the edit form with no change says "Changes saved." (no request is sent) |
| QA-07 | Info | BDM (assignee) | Organization detail — Contacts | "Make primary" shows a double space (visually hidden name between the words) |

## Findings

### QA-01 — Medium — a long unbroken name hides every other column
- **Role / page:** College BDM A (also managers) — `/bdm/organizations`.
- **Steps:** sign in as a College BDM, open Organizations (unfiltered) where an organization has a long name with no spaces (test row `ORG-000249`, 200 × "ß").
- **Expected:** long names wrap or truncate inside the Name column; Type, City, Primary contact, Assigned BDM and the meeting columns stay visible.
- **Actual:** the table is 2993 px wide inside a 1033 px scroll region. On a 1440 px desktop only Code and Name are visible for **every** row, and the rest needs horizontal scrolling inside the table. On a phone only part of the name is visible. The page itself doesn't overflow (`scrollWidth − innerWidth = −15`).
- **Evidence:** `.table-wrap` scrollWidth 2993 / clientWidth 1033, `overflow-x: auto`. No console or network errors. Screenshots `01-bdm-list-desktop.png`, `15-mobile-list.png`.

### QA-09 — Medium — Add organization: contact 1's ids differ after a full page load
- **Role / page:** College BDM — `/bdm/organizations/new` opened directly, refreshed, or from a bookmark (not reached through the in-app link).
- **Steps:** load `/bdm/organizations/new` directly; choose a type and fill name and city; leave Contact name empty; click Save organization.
- **Expected:** "Contact name is required" is shown and focus moves to Contact 1's name field, as it does when the page is reached through "Add organization".
- **Actual:** the error is shown and linked, but focus stays on the Save button. The server-rendered input keeps id `org-new-c16-name`, while React tracks the contact as `c1`. Its `aria-describedby` is `org-new-c1-name-error`, and focus calls target `org-new-c1-name`, which doesn't exist. A contact added afterwards gets `org-new-c2-name`, so ids are mixed. When the server and client counters line up, two contacts can share an id: labels and focus then point at the wrong contact. The same miss applies to a server 422 on contact 1.
- **Evidence:** `input.id = org-new-c16-name`, `aria-describedby = org-new-c1-name-error`, `document.activeElement = BUTTON`. The suffix grows with every server render (c11 → c16 across reloads): the contact-key counter is module-level and runs on the server. No console warning (production React doesn't report attribute mismatches). Screenshot `06-contact-focus-after-fullload.png`.

### QA-15 — Low — no loading signal when filters change
- **Role / page:** BDM — `/bdm/organizations`.
- **Steps:** emulate a slow network (2.5 s latency), type in "Name or code" and Search.
- **Expected:** some loading cue (status text, `aria-busy`, or dimmed rows) while the new page loads.
- **Actual:** the previous rows stay as they were with `aria-busy="false"` and no status for 2.5 s, so it looks as if the search did nothing. The first load does show "Loading organizations…".
- **Evidence:** at +0.6 s: `aria-busy=false`, no `role=status` text, old row count unchanged. Screenshot `14-list-loading.png`.

### QA-14 — Low — Archive while editing
- **Role / page:** College BDM B (assignee) — organization detail.
- **Steps:** Edit → (form open) Archive → Yes, archive → change State → Save changes.
- **Expected:** Archive is unavailable while editing, or archiving closes the edit form.
- **Actual:** "Organization archived." is shown with the edit form still open; Save then returns "Restore this organization first".
- **Evidence:** `PATCH /api/v1/bdm/organizations/{id}` → 409. Screenshot `12-archive-while-editing.png`. (Also listed as a deferred minor, M4, in the whole-branch review.)

### QA-10 — Low — focus after "Go back" in the duplicate warning
- **Role / page:** BDM — Add organization.
- **Steps:** enter a name and city that match an existing organization, Save, then press "Go back".
- **Expected:** focus returns to the Save button (or the name field).
- **Actual:** the warning disappears and focus goes to `<body>`; a keyboard user starts again from the top of the page.
- **Evidence:** `document.activeElement = BODY`. The warning itself is correct: `role=alert`, focus moves to its heading, Save is disabled, the entry is kept. Screenshot `07-duplicate-warning.png`.

### QA-12 — Low — focus after closing the edit form
- **Role / page:** BDM (assignee) — organization detail.
- **Steps:** Edit → Cancel; or Edit → change a field → Save changes.
- **Expected:** focus returns to the Edit button (or the success message).
- **Actual:** focus goes to `<body>`. The status "Changes saved." is announced.
- **Evidence:** `document.activeElement = BODY` after both actions.

### QA-06 — Low — unlabelled contact detail line
- **Role / page:** everyone — organization detail, Contacts.
- **Steps:** look at a contact with few details, or one whose designation and role are both "Placement Officer".
- **Expected:** each value is labelled (or blanks are omitted), so it's clear which is phone, email, role or designation.
- **Actual:** "— · — · — · thomas@stjoseph.edu" and "Placement Officer · Placement Officer · +91 98470 00000 · —".
- **Evidence:** screenshots `04-created-detail.png`, `15-mobile-detail.png`.

### QA-08 — Low — success message repeats on refresh
- **Role / page:** BDM — organization detail just after create.
- **Steps:** create an organization, then refresh the detail page (or share its URL).
- **Expected:** the "created" message appears once.
- **Actual:** "Organization ORG-000258 created." appears again on every load while `?created=1` is in the URL.

### QA-11 — Low — Cancel discards a filled-in form
- **Role / page:** BDM — Add organization.
- **Steps:** fill several fields, press Cancel.
- **Expected:** a confirmation when there are unsaved entries (the AgentStudentForm pattern), or none if that's intended.
- **Actual:** navigates straight to the list; the entry is lost.

### QA-03 — Low — links don't look like links
- **Role / page:** everyone — list (organization names) and detail ("Back to organizations").
- **Actual:** links inherit the text colour with no underline (computed `color: rgb(11,31,58)`, `text-decoration: none`, cursor pointer only), so it isn't obvious that rows open the organization.

### QA-02 — Low — code wraps mid-code
- **Page:** list. "ORG-000249" breaks after the hyphen when the Name column is wide (screenshot `01-bdm-list-desktop.png`).

### QA-04 — Low — raw validator text for the student count
- **Steps:** enter −5 in "Number of students" and Save.
- **Actual:** "Input should be greater than or equal to 0". The other fields use plain messages ("Enter a valid email address", "Website must start with http:// or https://").

### QA-05 — Info — website needs a scheme
- "stjoseph.edu" is rejected with "Website must start with http:// or https://"; the hint under the field says so in advance.

### QA-13 — Info — "Changes saved." on a no-op save
- Edit → Save changes with nothing changed shows "Changes saved." although no request is sent.

### QA-07 — Info — "Make  primary"
- The visually hidden contact name between "Make" and "primary" leaves a visible double space.

## Checks that passed

| Area | Result |
|---|---|
| Happy path (BDM) | Add with two contacts → detail with "Organization ORG-000258 created."; Contact person = primary contact; Last/Next meeting "—" |
| Invalid inputs | Empty submit: four field errors, `aria-invalid`, focus on Type. Server 422s land on the right fields, **including contact 1's email** (I1 fix), with focus on the first |
| Duplicate submission | Double-click on Save created exactly one organization (button disabled while saving) |
| Duplicate warning | Case/space/whitespace variant of name + city in the same module → 409 warning with code, name, city, assignee; Save disabled; entry kept |
| Empty / no-match states | "No organizations match these filters." + Clear filters; filters, type and "Assigned to me" in the URL, kept across refresh |
| Cancel / Back | Cancel → list; Back from detail → add page; edit Cancel discards changes |
| Contacts | Edit, Make primary (Contact person updates), Delete with inline confirm, Escape cancels and returns focus, focus on "Add contact" after add/delete (M5 fix), last contact cannot be deleted (disabled + reason) |
| Archive / restore | Archive hides by default; "Show archived" lists it with an "Archived" badge; manager restores; archived = read-only (409) |
| Reassign (manager) | Picker shows only active same-type team BDMs; confirm "Reassign ORG-000258 to …?"; Assigned BDM updates; button disarmed after success (M1 fix) |
| Unauthorized / wrong role | Same-type peer: read-only, PATCH → 403. School BDM → "Organization not found" (404). Other team's manager → not found. Manager on a BDM page → "BDM role required". `it_admin` → "Access unavailable" on all four pages, API 403. Previous assignee loses edit rights after reassignment |
| Signed out | `/bdm/organizations*` → `/bdm/sign-in?next=…`; `/bdm/manager/organizations/*` → `/admin/login?next=…`; API 401 |
| Server errors | List API blocked → "Unable to load organizations." + Retry, which recovers. Offline save → "The request did not complete… your entry is kept", focus on the message |
| Loading | First list load shows "Loading organizations…" (see QA-15 for later loads) |
| Layouts | Desktop 1440, tablet 820, mobile 375: no page-level horizontal scroll on list / add / detail; detail and contacts stack cleanly on mobile |
| Navigation | Sidebar "Organizations" highlighted (`aria-current`); mobile "Open menu" → Organizations navigates and closes the menu |
| Broken images | None |
| Console / network | Only the deliberate 4xx responses and offline/blocked requests; no exceptions, no unexpected redirects |

Screenshots are in the QA session's scratch directory (`qa_shots/`, not committed).

## Fix pass (2026-10-03, owner: "proceed")

Fixed test-first: each test was seen failing for the reported reason, then passing. Each fix was then re-checked in the isolated browser against the rebuilt `bdm002` web container.

| ID | Fix | Test (RED → GREEN) | Browser re-check |
|---|---|---|---|
| QA-09 | Contact keys come from the list (`c1`, then highest + 1), not a module counter, so server and browser ids agree | `BdmOrganizationForm.test.tsx` "same ids on every render" (was `c10` vs `c9`); "ids unique after remove/add" (guard) | Contact 1 is `org-new-c1-name` on first load and after reload; focus reaches it on a missing name |
| QA-01 (+QA-02) | `overflow-wrap: anywhere` on the whole table (a 120-character city did the same as the name); codes `white-space: nowrap`; Name `min-width` 160 px | `BdmOrganizationsPanel.test.tsx` "long names and codes lay out" | Desktop table 1033/1033 px, all 8 columns visible (was 2993 px); mobile has no page overflow |
| QA-15 | The card is `aria-busy` and shows "Updating organizations…" (rows dimmed) from the moment a filter or page changes, through the router's server round trip, until the results arrive; no busy state when nothing changed | "signals a later load", "busy from the moment a filter changes", "not busy when a search changes nothing" | With 2 s latency: busy from +0.5 s (before the URL changes) until the results; then clears |
| QA-14 | Archive is hidden while the edit form is open | `BdmOrganizationDetail.test.tsx` "hides Archive while the edit form is open" | No Archive while editing |
| QA-12 | Closing the edit form (Cancel or Save) returns focus to Edit | "returns focus to Edit when the edit form closes" | Focus on Edit after Cancel |
| QA-10 | "Go back" in the duplicate warning returns focus to Save | "returns focus to Save after Go back" | Focus on "Save organization" |

**Verification:** web BDM set (18 files) 138 passed; `tsc --noEmit` 0; `eslint` 0. Playwright `bdm-002` 2 + `bdm-001` 8 + `auth-001` 6 → 16 passed.

**Not fixed in this pass:** QA-03, QA-04, QA-05, QA-06, QA-07, QA-08, QA-11, QA-13 — fixed in the second pass below.

## Second fix pass (2026-10-03, owner: "Fix them")

The remaining eight items, fixed test-first (each test seen failing first), then re-checked in the isolated browser against
rebuilt `api` + `web` containers.

| ID | Fix | Test (RED → GREEN) | Browser re-check |
|---|---|---|---|
| QA-03 | Organization names and "Back to organizations" use the project's link style (`var(--blue)`, underline; the AgentUniversitiesPanel convention) | Panel "styles organization names as links"; Detail "styles Back to organizations as a link" | `rgb(7, 85, 185) underline` on both |
| QA-04 | One plain message for any bad student count: "Number of students must be a whole number from 0 to 1,000,000" (negative, too large, fractional) | `test_bdm_002_schemas.py::test_student_count_errors_read_plainly` ×3 | — (API message) |
| QA-05 | A bare domain ("stjoseph.edu", "www.mary.ac.in/admissions") is stored as `https://…`; any other scheme (`javascript:`, `data:`, `ftp:`, `mailto:`) and non-addresses are still refused. Hint: "For example stjoseph.edu or https://stjoseph.edu" | `test_a_bare_domain_is_accepted_as_https` ×3, `test_other_schemes_and_non_addresses_are_still_rejected` ×6 (guard), Form hint test | "infosys.com" saved as `https://infosys.com` |
| QA-06 | Contact details are labelled ("Designation: … · Role: … · Phone: … · Email: …"), blanks left out, "No other details" when there are none | Contacts read-only test (updated assertions), "says so when a contact has no other details" | "No other details" for a name-only contact |
| QA-07 | "Make primary" is spaced once; the contact name moves to `aria-label` ("Make Ms Iyer primary") | "reads Make primary with single spacing" | Visible text `Make primary` |
| QA-08 | `?created=1` is removed from the address (`router.replace`) once the message is shown | Detail "drops ?created=1…", "does not touch the address when nothing was just created" | URL without the flag after create; refresh shows no message |
| QA-11 | Unsaved input asks before it is thrown away: Cancel, in-app links (capture phase) and reload/close (beforeunload) — the AgentStudentForm guard | Form "asks before Cancel discards unsaved input", "cancels without asking when nothing was entered" | Native confirm on Cancel (dismiss keeps the entry) and on the sidebar link (accept navigates) |
| QA-13 | A save with nothing to change says "No changes to save." (`onSaved(org, saved)`) | Detail "says when a save had nothing to change" | "No changes to save." |

**Verification:** backend lite set (all `test_bdm_002_*` + `test_bdm_001_*`) 194 passed; ruff clean on the changed code; web BDM
set (18 files) 148 passed; `tsc --noEmit` 0; `eslint` 0. Playwright `bdm-002` 2 + `bdm-001` 8 + `auth-001` 6 → 16 passed.
**All 15 browser-QA findings are now fixed.**

