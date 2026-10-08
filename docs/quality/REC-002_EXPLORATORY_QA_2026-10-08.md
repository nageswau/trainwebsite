# rec-002 exploratory QA — 2026-10-08

## Setup
- Stack: isolated `rec002` (web `:3122`, API `:8122`, SMTP disabled), seeded.
- Browser: isolated Edge 154 over CDP (port 9333, temporary profile), driven by browser-use. Keyboard-only checks ran in Playwright
  (`web-test` container), because CDP-synthesised Enter does not submit forms.
- Roles exercised:
  - `placement_manager` (seed)
  - `placement_team` (seed recruiter)
  - `hr_team`
  - `it_admin`
  - `super_admin`
  - signed out
- Console and failed-request capture was injected on every document. No console errors appeared in any scenario. The only failed
  requests were the expected 401, 403, 409 and 422 responses.

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | Manager signs in at `/admin/login` → Team → **Catalogues** | Lands on `/recruiter/manager/catalogue/lead-sources`; the tab has `aria-current="page"`; the 15 §2 values are in source order ✅ |
| 2 | Add a name of spaces only | 422 "Name is required", focus on the message ✅ |
| 3 | Add `linkedin` (the seed is `LinkedIn`) | One POST → 409 "A value named “linkedin” already exists in this list"; the input is kept ✅ |
| 4 | Type 130 characters | The input caps at 120 (the API cap) ✅ |
| 5 | Add `<b>QA</b> …` | Stored and shown as text; no `<b>` element is rendered ✅ |
| 6 | Search with no match, refresh, Clear search | `?q=` in the URL; "No lead sources match this filter."; refresh keeps the search; Clear search returns to the full list ✅ |
| 7 | List request blocked (job categories, campaigns) | "Unable to load …" + Retry; Retry refetches and recovers ✅ |
| 8 | Lead-source picker request blocked on Campaigns | "Unable to load lead sources." + "Retry loading lead sources"; Create stays disabled until the retry fills the picker ✅ |
| 9 | Keyboard only: add (Enter), Edit, Esc, rename, Deactivate → Confirm, rename onto an existing name | Focus goes to the feedback, then the edit input, back to Edit after Esc, to Confirm deactivate, then to Reactivate; the duplicate rename shows an inline 409 ✅ |
| 10 | Back/Forward between tabs | Back returns to the previous tab with its list loaded; Forward works ✅ |
| 11 | Campaign whose lead source was deactivated | Row shows the "Lead source inactive" badge; Edit pre-selects "<name> (inactive)"; Save keeps it (one PATCH, 200, "Saved …") ✅ |
| 12 | End date before start (create) | Refused in the browser with "End date cannot be before the start date" and no request ✅ |
| 13 | Signed out → catalogue URL | → `/admin/login?next=…` ✅ |
| 14 | Recruiter | Page: Access unavailable "Placement manager role required"; API GET 200 (active only), POST 403 ✅ |
| 15 | `hr_team`, `it_admin` | Page refused; API GET 403, POST 403 (C3) ✅ |
| 16 | `super_admin` | Page works under the Super Admin nav; GET 200, POST 201 ✅ |
| 17 | Desktop 1366, tablet 820, mobile 390 (lead sources, campaigns) | No horizontal scroll; tabs wrap; "Create/Add" jump link on tablet and mobile; rows become labelled cards on mobile; no broken images ✅ |
| 18 | `/recruiter/manager/catalogue`, `/recruiter/manager/catalogue/colours` | The index redirects to Lead sources; an unknown tab is a 404 (Playwright) ✅ |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA-01 | Low (copy) | placement_manager | every catalogue tab | Open any tab and read the intro | Plain guidance for the manager | Internal evidence references shown to users ("EVID-018 §2", "(§9)", …), and "The list starts empty" stayed on the Industries tab even after values were added | **Fixed:** the intros were rewritten without references; a vitest guard (`RecruiterCatalogue.test.tsx`) prevents a regression; re-verified in the browser |

## Observations (not defects; no change)
- `super_admin` has no sidebar link to the catalogue. The page works by URL, which is the same as rec-001's manager team page. Add a
  link if the owner wants one.
- The API tests and the app share the stack's database, so test rows (for example "Src 1a2b…") appear in the QA stack lists. This is
  the existing worktree setup and does not happen in production.
