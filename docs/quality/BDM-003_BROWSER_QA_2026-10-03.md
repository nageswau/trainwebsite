# bdm-003 — Exploratory browser QA (first pass, no code changed)

**Date:** 2026-10-03 · **Branch:** `feature/bdm-003-type-specific-profile-fields` @ `51e12c9`+docs · **Feature:** type-specific organization profiles (`DEC-SCOPE-063`)

**Environment:** isolated compose project `bdm003` (web `http://localhost:3003`, API `8003`, Postgres/Redis private to the project), migration head `0068_bdm_org_profiles`, seeded. The test database is shared with the `api-test` runner, so the lists also hold API-test fixtures.

**Tools:**
- **Browser Use** driving an **isolated Chrome 154** (its own throwaway profile, remote-debugging port 9333 — the user's Chrome session was never touched).
- **Playwright** (web-test container, Chromium): `bdm-003-type-profiles`, `bdm-002-organization-crm`, `bdm-001-bdm-profile` → **10 passed**.

**Accounts** (throwaway, created through the real admin API and activated with their welcome tokens): BDM Manager; School BDM; a second School BDM (same-module peer); Agent BDM; College BDM; plus the seeded `student.overseas@edusphere.local`.

**Harness notes (not product findings):** CDP coordinate clicks and screenshots were unreliable while the isolated tab was in the background, so controls were driven with DOM `click()` / React-safe value setters (React's real handlers still ran) after `activate_tab`. Chrome logged "Blocked attempt to show a 'beforeunload' confirmation panel…" when the script navigated away from a dirty form — evidence that the unsaved-changes guard is armed.

---

## Result

**No Critical, High or Medium issues.** 2 Low, 4 Info. All 20 requested areas were exercised; console showed only deliberate 4xx responses; no broken images; no unexpected redirects.

| # | Area | Result |
|---|---|---|
| 1 | Happy path | PASS — School created (Board CBSE, Private, LKG–12, two-line address, Principal contact) → `ORG-000261 created.`; Agent created (country, territory, source, staff 25) with "Commission: Available after onboarding"; School → College via the two saves; College details with multi-line Courses |
| 2 | Invalid inputs | PASS — staff `abc`, `-5`, `100001`, `12.5` → "Number of staff must be a whole number from 0 to 100,000" on the field, focus moved, nothing cleared; grade 10 > Nursery → client message, focus on Highest grade, **no request sent**; crafted API calls: another type's field (also with `null`), `commission` (profile and top level), smuggled `bdm_type`, bad enum, `profile: null`, address > 500, tab in address, `board=cbse` filter → 422 with exact `loc`; `%` in Territory matches literally |
| 3 | Empty states | PASS — "No organizations match these filters." for an empty Board / Territory filter; "No school details yet. Use Edit to add them." (assignee) / without the hint for others |
| 4 | Server errors | PASS — a 500 (JSON or plain text) on create/edit → "Unable to save this organization." / the server text; entry kept; still editing — see QA3-02 for the list |
| 5 | Loading states | PASS — while saving: button "Saving…", disabled, form `aria-busy="true"` |
| 6 | Cancel / back | PASS — Cancel and in-app links ask "You have unsaved changes…" when profile/address changed; declining keeps the editor; browser Back from detail returns to the filtered list |
| 7 | Refresh | PASS — filtered URL restores Board value and rows; detail refresh shows server data; the one-shot success message is not repeated |
| 8 | Duplicate submission | PASS — a second click while saving sends nothing; two clicks in one tick → **one** organization; retry after a network drop creates exactly once |
| 9 | Unauthorized user | PASS — signed out → `/bdm/sign-in`, API 401; student → "Access unavailable / BDM role required", API 403 |
| 10 | Incorrect role / scope | PASS — same-module peer: read-only, profile visible, PATCH 403 "Only the assigned BDM can edit this organization"; other module: "Organization not found", API 404; manager: read-only (no Edit), PATCH 403, POST 403; manager on the BDM path → "Access unavailable" |
| 11–13 | Desktop 1366 / tablet 768 / mobile 375 / narrow 320 | PASS — form, detail and filtered list: `scrollWidth == clientWidth` at every size; single-column fields; 44 px controls (checkbox/radio inside 44 px label rows) |
| 14 | Navigation | PASS — Type select help text "The details section below changes with the type." (tied by `aria-describedby`); Board appears only for School, Territory for Agent, Affiliation for College/University; changing Type drops a filter that no longer applies; Clear filters resets all |
| 15 | Success messages | PASS — "Organization ORG-… created.", "Changes saved.", "No changes to save." |
| 16 | Error messages | PASS — per-field 422s; structured 409 shown as "Clear the School details before changing the type: Board, School type, Lowest grade, Highest grade." (focus on Type); after clearing in the form: "Save the cleared School details first: change the type back to School and save, then change the type."; network drop: "The request did not complete. Check your connection and try again; your entry is kept." |
| 17 | Broken images | PASS — none on form, detail, list at any size |
| 18 | Console errors | PASS — only Chrome's "Failed to load resource" for deliberate 422 validations; no exceptions |
| 19 | Failed network calls | PASS — only the deliberate 422/409/500/drop cases above |
| 20 | Unexpected redirects | PASS — none; role/portal redirects as designed |

Also observed: contact Role list puts the type's people first (School: Principal, Management, Counselor; Agent: Owner) in both the create form and the detail page's contact editor; the API's 409 lists only field **names**, never values.

---

## Issues

### QA3-01 — URL-only profile filter narrows the list with no visible control
- **Severity:** Low · **Role:** any BDM (seen as School BDM) · **Page:** `/bdm/organizations`
- **Steps:** open `/bdm/organizations?board=CBSE` (Type = All types), or `?org_type=agent&board=CBSE`.
- **Expected:** a filter that doesn't belong to the selected Type is dropped (as the Type select already does), or its control is shown.
- **Actual:** the list is narrowed to CBSE schools (20 rows instead of the full page) but no Board control is shown; only "Clear filters" reveals that a filter is active.
- **Evidence:** network `GET /api/v1/bdm/organizations?limit=50&offset=0&board=CBSE` → 200; filter labels on the page: `Name or code, City, Type, Assigned to me, Show archived`. Same as the whole-branch review's deferred minor.

### QA3-02 — An invalid Board in the URL shows "Unable to load organizations."
- **Severity:** Low · **Role:** School BDM · **Page:** `/bdm/organizations?org_type=school&board=bogus`
- **Steps:** edit the URL to an unknown board and load it; press Retry.
- **Expected:** the unknown value is ignored (list shown) or explained.
- **Actual:** "Unable to load organizations." with a Retry that can never succeed; the Board select shows no selection.
- **Evidence:** `GET …&board=bogus` → **422** (`literal_error`, `loc: ["query","board"]`); console "Failed to load resource: … 422".

### QA3-03 — Tabs in pasted Address / Courses are refused (Info, by design)
- **Role:** any BDM · **Page:** organization form · Pasting text with a tab (e.g. from a spreadsheet) → "Address contains invalid characters". Matches `DEC-SCOPE-063` P14 (only line breaks are allowed). Evidence: `PATCH {address: "a\tb"}` → 422 `value_error`.

### QA3-04 — A type change over entered details takes two saves (Info, by design)
- **Role:** assigned BDM · **Page:** organization edit · Matches P4; the form now explains the path. Users may still find the two saves surprising — a product decision, not a defect.

### QA3-05 — Number of staff is only validated by the server (Info)
- **Role:** Agent BDM · **Page:** organization form · `abc` / `-5` / `12.5` reach the API (one round trip) and come back as a clear field error. Correct and safe; a client-side check would only save the round trip.

### QA3-06 — On phones the type's section is far below the Type select (Info, UX)
- **Role:** any BDM · **Page:** organization form at 375 px · The Agent/School/College details follow ~10 common fields; the help text under Type says the section is below. Screenshot: `qa_10_mobile_form.png`.

---

## Fix pass (owner: "Yes fix", 2026-10-03)

QA3-01 and QA3-02 fixed test-first in `aa3e4af` (`BdmOrganizationsPanel.readFilters`): a profile filter is read only with the Type it belongs to, and an unknown Board is dropped instead of being sent.
- **RED:** `BdmOrganizationsPanel.test.tsx` "ignores a profile filter that does not belong to the URL's Type (browser QA3-01)" and "ignores an unknown Board in the URL instead of failing to load (browser QA3-02)" failed (`board=…` was sent); **GREEN** after the change.
- **Web BDM set:** 13 files, **129 passed**; `tsc` 0; `eslint --max-warnings=0` on the changed files 0.
- **Re-checked in the isolated browser** after rebuilding the web container: `?board=CBSE` (All types) → full list (50 rows), no hidden filter, no "Clear filters"; `?org_type=school&board=bogus` → school list (44 rows), Board "All boards", no error; regression `?org_type=school&board=ICSE` → 6 rows, Board ICSE; no console errors or failed requests.
- **Playwright** bdm-003 + bdm-002 + bdm-001 → **10 passed**.

QA3-03…06 are Info items (by design or UX suggestions) and were left as they are.

## Evidence files (scratchpad, not committed)

Screenshots `qa_02_school_filled.png`, `qa_03_school_detail.png`, `qa_10_{desktop,tablet,mobile,narrow}_form.png`, `qa_11_*_detail.png`, `qa_12_*_list.png`; scripts `qa_s07_tamper.py` (API tampering), `qa_s08_authz.py` (roles/scope), `qa_s09_filters.py`, `qa_s10_errors.py` (Fetch interception: busy state, 500, network drop, duplicate submit), `qa_s11_nav.py`, `qa_s12_layout.py`, `qa_s13_misc.py`.

**Data created:** ORG-000261 (School → College), ORG-000262 (Agent), the filter/error/double-submit schools (ORG-000263…265), all assigned to the throwaway QA BDMs.
