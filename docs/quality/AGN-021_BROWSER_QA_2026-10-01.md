# AGN-021 — View Staff Activity: Browser QA (2026-10-01)

**Scope:** exploratory QA of the Master's staff Activity view (Team page) against the running app, then a fix pass and re-verification.
**Environment:** compose project `agn021` (web http://localhost:3021, API 8021, `python -m app.seed` applied), branch
`feature/agn-021-staff-activity`. Isolated Chrome profile (own user-data dir, CDP 9333), driven by browser-use; a page probe recorded
console errors, page errors and every `fetch` with its status.
**Test data:** created through the real API — agency "QA Alpha Overseas" (Master; staff S1 with 19 audited actions incl. a 60-character
name, an edit, a duplicate override, a link, an application, a document upload and a verify with a reviewer note; S2 with none; S3
deactivated with one action) and agency "QA Beta Overseas" (one staff member, one action).

## Findings (first pass) and status

| ID | Severity | Role / page | Finding | Fix | Re-verified |
|---|---|---|---|---|---|
| QA-03 | Medium | Master / Team → Activity | An expired session showed the raw API text "Not authenticated" with Try again / Refresh that could never succeed; no way to sign in. Evidence: `GET …/activity → 401`. | 401 → "Your session has expired. **Sign in again**" (link `/overseas/login`), no retry buttons — the app's `LoadFailureAlert` convention. | ✅ cookies cleared → message + link, only Close; link opens `/overseas/login` |
| QA-04 | Minor (a11y) | Master / Activity | Focus went to **Close** (last control) on open; Tab left the view, so keyboard/screen-reader users skipped the list and reached the pager/Refresh only with Shift+Tab. | Focus moves to the Activity heading (`tabIndex=-1`) on open; Close no longer `autoFocus`. | ✅ Enter → focus "Activity"; Tab → Next page → Refresh → Close; Escape → back to "Activity of Ravi Kumar" |
| QA-01 | Minor (UX) | Master / Activity error state | Error state offered both **Try again** and **Refresh** (same action). | Refresh hidden while an error shows. | ✅ offline → "Unable to load activity." + Try again + Close; recovery restores Refresh |
| QA-02 | Minor (UX) | Master / Activity paging, Refresh | While a newer page/Refresh loaded, the old page stayed with no visible cue (only `aria-busy`, disabled pager). | "Updating activity…" status line and the list dimmed (opacity 0.6) while loading. | ✅ 2.5 s latency → cue + dimmed list, pager disabled; cleared after load; 320 px no overflow |

Fix commit: `aa11adc` (tests first: four new cases in `AgentStaffActivity.test.tsx` failed before the fix and pass after; full web
suite 128 files / 1368 tests passed; `tsc --noEmit` exit 0; eslint clean on the changed files). Web image rebuilt by the owner
(`docker compose -p agn021 -f docker-compose.yml up -d --build web`) before re-verification.

## Checklist (first pass, unchanged by the fix except where noted)

| # | Check | Result |
|---|---|---|
| 1 | Happy path | ✅ 18 → 19 entries, correct labels/subjects, newest first, 2 pages; edit shows field names; reviewer note, email, phone never shown |
| 2 | Invalid inputs | ✅ `limit` 0/101/abc, `offset` −1/10001 → 422; 100 / 10000 → 200; malformed member id → 422 |
| 3 | Empty state | ✅ "No activity yet." |
| 4 | Server errors | ✅ 500 / 422 / non-JSON → "Unable to load activity."; 404 → "Staff member not found"; 401 → QA-03 (fixed) |
| 5 | Loading | ✅ "Loading activity…"; in-flight paging → QA-02 (fixed) |
| 6 | Cancel / back | ✅ Close and Escape return focus to the Activity button; browser Back leaves the Team page (view state not in URL, by design) |
| 7 | Refresh | ✅ a new staff action appears on Refresh |
| 8 | Duplicate submission | ✅ double-click Activity → one request; 5× Refresh → 5 requests, consistent result (deliberate: newest request wins) |
| 9 | Unauthorized | ✅ logged out: page → login redirect; API 401 |
| 10 | Incorrect role | ✅ staff: API 403, typed URL → "Access unavailable", no Activity buttons; other agency's Master → 404; counselor / Overseas Admin / student → 403 |
| 11–13 | Desktop 1440 / tablet 768 / mobile 375, 320 | ✅ no horizontal overflow; long name wraps |
| 14 | Navigation | ✅ |
| 15 | Success messages | n/a (read-only view) |
| 16 | Error messages | ✅ after QA-03 fix |
| 17 | Broken images | ✅ none |
| 18 | Console errors | ✅ none captured |
| 19 | Failed network calls | ✅ only the deliberately simulated ones |
| 20 | Unexpected redirects | ✅ none |

**Notes (no change):** Refresh is not de-duplicated (read-only; latest request wins); times are shown to the minute.
**Still pending (owner requirement):** the independent Codex review.
