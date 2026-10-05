# bdm-009 — Independent exploratory QA, pass 2 (2026-10-05)

**No code was changed in this pass.** Build under test: `feature/bdm-009-activities` @ `9e873aa5` (web rebuilt from `c09d8af7` + `aec4586a`),
compose project `bdm009` (web `localhost:3009`, API `localhost:8009`, DB at `0070_bdm_activities`).
**Tools:** Playwright (throwaway exploratory specs, run in the `web-test` container, deleted afterwards — they record console errors, page
errors, 4xx/5xx responses, failed requests and main-frame navigations per scenario) and Browser Use on an isolated Chrome profile (CDP 9333).
**Accounts** (real admin API + welcome tokens): BDM Manager A (team: College BDM1, College BDM2, School BDM3), BDM Manager B (no team), an
IT admin; org "QA Orchid College" assigned to BDM1, org "QA Banyan College" assigned to BDM2.
Evidence files (screenshots, per-scenario JSON) are in `artifacts/ci/qa9b/` (git-ignored).

## Coverage

| # | Area | Result |
|---|---|---|
| 1 | Happy path | Pass — log (call + contact + note), edit ("Activity saved."), delete with confirm ("Activity deleted."), empty state returns; My Activities via the organization picker, contacts load after the pick, counts correct |
| 2 | Invalid inputs | Pass — no direction → "Check the highlighted fields." + field error, focus on Outgoing; +30 min → "When can't be in the future"; −10 days → "Activities can be logged up to 7 days back" (focus on When); empty When → "Enter when it happened."; 600-char note → capped at 500 (counter 500/500); whitespace-only note stored as null. URL-level invalid dates → **QA9B-01** |
| 3 | Empty states | Pass — new organization, old day (all counts 0), manager without a team, manager filtered to a BDM |
| 4 | Server errors (mocked) | POST 500 keeps the entry (**QA9B-04** wording); offline POST → "The request did not complete… your entry is kept."; DELETE 503 and PATCH 503 → reason shown, item / form kept; PATCH 409 → reason shown, item read-only (**QA9B-03** focus); day re-read 500 after a save → **QA9B-02** |
| 5 | Loading states | Pass — Save shows "Saving…", Save and Cancel disabled during a slow (2.5 s) request |
| 6 | Cancel / back | Pass — Cancel closes the form (focus back to Log activity), reopening starts empty; dirty form + in-app link → confirm "Discard this activity?" (Cancel keeps the note, OK leaves); browser Back with a dirty form → beforeunload prompt; Back / Forward after a save keep the new item |
| 7 | Refresh | Pass — data persists after reload; dirty form + reload → beforeunload prompt |
| 8 | Duplicate submission | Pass — double-click Save → 1 row; Enter twice → 1 row; double-click "Yes, delete" → 1 row removed, no error |
| 9 | Unauthenticated | Pass — `/bdm/activities` and the org profile → `/bdm/sign-in?next=…`; `/bdm/manager/activities` → `/admin/login?next=…`; API GET / POST → 401 |
| 10 | Incorrect role / other users | Pass — IT admin: "Access unavailable — BDM role required" / "This page is for BDM managers.", API POST 403; School BDM on a College org → "Organization not found", API POST 404; peer College BDM2 sees BDM1's timeline read-only (no buttons), API POST / PATCH / DELETE 403; Manager A writes 403, BDM pages refused; Manager B → other team's org "Organization not found" (see **QA9B-05**); BDM on the manager page → refused |
| 11–13 | Desktop / tablet / mobile | Pass — 1440, 1024, 768, 375, 320 px on the org profile (log form open), My Activities and Team activities: no horizontal overflow; 8 KPI tiles; see **QA9B-06** |
| 14 | Navigation | Pass — "Activities" in both sidebars, `aria-current="page"` on the active item; organization links from day lists |
| 15–16 | Success / error messages | See QA9B-02, QA9B-04 |
| 17 | Broken images | None on any page / width |
| 18 | Console errors | No JavaScript exceptions (`pageerror`) in any scenario. The only console errors are the browser's own "Failed to load resource" lines for intentional 4xx/5xx responses (validation 422s, mocked 5xx, refusals) — expected |
| 19 | Failed network calls | Only intentional ones (mocked) and `net::ERR_ABORTED` on Next.js link prefetches (benign, cancelled prefetch) |
| 20 | Unexpected redirects | None — signed-out redirects carry `next=` back to the requested page |

## Issues

### QA9B-01 — Medium — A future or impossible `?date=` replaces the whole page with "Access unavailable"
- **Role:** BDM (also Manager page with `?date=`). **Page:** `/bdm/activities`.
- **Steps:** sign in as a BDM → open `/bdm/activities?date=2099-12-31` (or `?date=2026-02-30`).
- **Expected:** stay inside the portal (sidebar, title, day picker) with a field-level message such as "Choose a day up to today", or fall back to today.
- **Actual:** a bare full-page card "Access unavailable — That date hasn't happened yet" with "Go to your dashboard" / "Sign out"; no navigation, and the heading wrongly suggests a permission problem. `2026-02-30` passes the client's `isIsoDate` (JS `Date.parse` rolls it over) and reaches the API.
- **Evidence:** API answers 422 `"That date hasn't happened yet"` to the page's server-side read (`GET /api/v1/bdm/activities?date=2099-12-31…`), which `accessUnavailable()` renders; no console error. Screenshot `03-future-date.png`. The date input's `max` prevents choosing a future day in the UI, so this is reached through edited / shared / bookmarked URLs.

Fixed in c4c25b9d: strict `isCalendarDate` + `activityDay`; an invalid or future date shows today with an in-page note, the API is never called with it.

### QA9B-02 — Medium — After a successful save, a failed refresh hides the success and invites a duplicate
- **Role:** BDM. **Page:** `/bdm/activities` (Log activity).
- **Steps:** open Log activity, pick the organization, choose Visit, Save while the day re-read (`GET /api/v1/bdm/activities?date=…`) fails (mocked 500).
- **Expected:** the user is told the activity **was saved** (e.g. "Activity logged. The list couldn't be refreshed — reload to see it.").
- **Actual:** only "The day couldn't be refreshed. Reload the page to see the latest counts."; no success notice; the new activity is not in the list and the counts are stale, so a user is likely to log it again.
- **Evidence:** `POST /api/v1/bdm/activities` → 201, then `GET /api/v1/bdm/activities?date=2026-10-05&limit=50&offset=0` → 500; status region empty. Screenshot `05-day-reread-500.png`.

Fixed in c4c25b9d: the success notice is set even when the re-read fails; the failure reads "The list couldn't be refreshed. Reload the page to see the latest entries and counts."

### QA9B-03 — Low (accessibility) — Focus is lost after a refused edit
- **Role:** BDM. **Page:** organization profile (also My Activities).
- **Steps:** Edit an activity → change the note → Save when the server answers 409 "Only today's activities can be changed" (or 403).
- **Expected:** focus moves to the refusal message or the item.
- **Actual:** the form closes and Edit / Delete disappear (correct), but focus falls to `<body>`; keyboard users lose their place (the alert is announced).
- **Evidence:** `PATCH /api/v1/bdm/activities/{id}` → 409; `document.activeElement` = `BODY`. Screenshot `05-patch-409.png`.

Fixed in c4c25b9d: the refusal alert has a stable id and tabIndex -1 and takes focus after a 403 / 409.

### QA9B-04 — Low — A 500 with a non-JSON body shows only "Something went wrong."
- **Role:** BDM. **Page:** organization profile (Log activity).
- **Steps:** Save while the API returns 500 with a plain-text body (proxy / server error page).
- **Expected:** a message that tells the user what to do, as the offline case does ("…try again; your entry is kept.").
- **Actual:** "Something went wrong." (entry kept, focus on the message — correct otherwise).
- **Evidence:** `POST /api/v1/bdm/activities` → 500 `Internal Server Error`; form alert text. Screenshot `05-post-500.png`.

Fixed in c4c25b9d: a 5xx or an unreadable body shows "The server couldn't save this activity. Your entry is kept — try again."

### QA9B-05 — Low — Manager filter shows "Everyone" while silently filtering to a BDM outside the team
- **Role:** BDM Manager (not that BDM's manager). **Page:** `/bdm/manager/activities?bdm=<other team BDM id>`.
- **Expected:** the filter is ignored (shows the team) or the page says the BDM isn't in the team.
- **Actual:** the BDM select shows "Everyone", but the list and counts are filtered to the outside BDM → empty "No activities on this day." and all counts 0. No data leak (the API ANDs the team scope).
- **Evidence:** Browser Use: select value `""`, empty text "No activities on this day.".

Fixed in c4c25b9d: a BDM outside the team list is dropped (no bdm_user_id) with the note "That BDM isn't in your team — showing everyone."

### QA9B-06 — Low (cosmetic) — "Log activity" wraps onto two lines at tablet width
- **Role:** BDM. **Page:** `/bdm/activities` at 768 px.
- **Actual:** the title-action button renders as a tall two-line "Log / activity" block beside the heading. Screenshot `10-_bdm_activities-768.png`.

Fixed in c4c25b9d: `no-wrap` class on the Log activity button (visual check after rebuild).

## Not tested in this pass
- A real API outage during a server-rendered page load (needs the API container stopped; the owner controls the stack) — the error-card path was exercised through QA9B-01.
- The route-level `loading.tsx` skeleton (pages render too fast on this stack to observe it reliably).

## Notes
- Coordination risk (not a product defect): the parallel bdm-006 branch now also claims migration `0070` / `DEC-SCOPE-068`; whichever merges
  second must renumber.
- Browser Use (CDP) input was unreliable on this machine for some button activations and scrolling in emulated viewports; every affected
  check was re-run with Playwright, and nothing was reported from tool artefacts alone.
