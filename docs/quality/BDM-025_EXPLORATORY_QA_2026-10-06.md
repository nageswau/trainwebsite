# bdm-025 — Exploratory browser QA, pass 1 (no code changes) — 2026-10-06

**Build under test:** `worktree-bdm-025` @ the "BDM managers card" commit (migration head `0078_bdm_assignment_history`, `DEC-SCOPE-076` at the time; renumbered `0080` / `DEC-SCOPE-079` on merging `main` @ `230a043f`, then `DEC-SCOPE-080` at `6655e284`, then `0081` / `DEC-SCOPE-081` at `a38955d5`. then `0082` / `DEC-SCOPE-082` at `3986958c`. The findings are unchanged).

**Environment:** an isolated stack, `docker compose -p bdm025`:
- web `http://localhost:13025`, API `:18025`;
- seeded with `python -m app.seed`.

**Browser:** **Browser Use is not installed on this machine** (the same as for bdm-007 and bdm-008), so an isolated headless Chromium was
used instead. It ran through Playwright in the `web-test` container, against the stack through `tests/ci-proxy.mjs`. The QA script is
a throwaway spec mounted from the session scratchpad and is never committed. Screenshots are in the scratchpad: `artifacts/qa025/*.png`.

**Accounts:** all throwaway, created through the real admin API:
- super_admin (seed);
- BDM manager M (6 BDMs), plus a spare manager S;
- College BDMs A, B, E, F, G and School BDM C;
- A owns one organization, one future appointment, one open task and one draft trip (created as A through A's own login);
- G owns one organization.

## 1. Automated evidence

| Run | Result |
|---|---|
| Playwright `bdm-025-deactivation.spec.ts` (2) + `bdm-001-bdm-profile.spec.ts` (7) | **9 passed** |
| Exploratory script (7 scenario groups) | the observations below |

## 2. Coverage of the 20 requested areas

| # | Area | Result |
|---|---|---|
| 1 | Happy path | ✅ A → B. The dialog shows "Open work: 1 organization, 1 appointment and 1 follow-up/task." and "1 trip not yet started will be cancelled." The notice reads "Deactivated … handed over to … 1 not-started trip was cancelled." The row shows Inactive. The organization's `assigned_bdm` is now B |
| 2 | Invalid inputs | ✅ The picker offers only active College BDMs, never A itself or School BDM C. API: a School target → 422 "Choose an active BDM of the same module"; an empty body → 422 "Choose who takes over this BDM's open work"; PATCH `active:false` on a BDM → 422 with directions; PATCH on manager M → 422 "This manager has 6 BDMs. Move them …" |
| 3 | Empty state | ✅ "F has no open work to hand over." — no choice is asked; Confirm sends `leave` |
| 4 | Server errors | ✅ A preview 500 → "Unable to load F's open work." + Retry (recovers). A network drop → "The request did not complete…". ⚠️ **QA25-03**: a deactivate 500 shows the raw "Internal Server Error" |
| 5 | Loading | ✅ "Loading open work…" (role=status) while the preview is held |
| 6 | Cancel / back | ✅ Keep active closes the group and returns focus to Deactivate. ⚠️ **QA25-01**: Escape does nothing right after opening (focus is on `<body>`) |
| 7 | Refresh | ✅ After a reload the row is still Inactive; the notice is not repeated |
| 8 | Duplicate submission | ✅ A double click on Confirm deactivate → exactly 1 POST |
| 9 | Unauthorized (signed out) | ✅ `/admin/bdms` → `/admin/login?next=%2Fadmin%2Fbdms`; API 401 |
| 10 | Incorrect role | ✅ A BDM manager on `/admin/bdms` sees "Access unavailable — Super Administrator role required"; API 403. The BDM managers card is hidden from it_admin (component test) |
| 11–13 | Desktop / tablet / mobile | ✅ Dialog open at 1366, 768, 375 and 320 px: no horizontal overflow (0 px). The card's rows stack below 640 px |
| 14 | Navigation | ✅ The search URL `?q=` keeps the row in view; Back works (bdm-001 behaviour unchanged) |
| 15 | Success messages | ✅ The deactivate, leave, handover and manager notices go through the list's `role=status` line |
| 16 | Error messages | ✅ In `role=alert` inside the group, focused (component tests). ⚠️ QA25-03 wording |
| 17 | Broken images | ✅ None |
| 18 | Console errors | ✅ Only the browser's own "Failed to load resource" lines for the deliberately provoked 500 / abort |
| 19 | Failed network calls | ✅ Only the provoked ones |
| 20 | Unexpected redirects | ✅ None |
| — | Leave + later handover | ✅ G with mode "Keep with G…" → "Their open work stays with them until you hand it over." Then the inactive row → Hand over → "Open work: 1 organization…" → "Handed over 1 organization … from G to B." |
| — | Manager card | ✅ "QA25 Mgr … 6 BDMs"; the replacement picker offers only the spare manager (not M itself) |

## 3. Findings

| ID | Severity | Role | Page | Steps | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| **QA25-01** | Medium (keyboard / a11y) | super_admin, it_admin, overseas_admin | `/admin/bdms` BDM row | 1. Click or press Enter on "Deactivate X". 2. Press Escape | Focus moves into the dialog (as bdm-001's confirm did) and Escape closes it | The Deactivate button unmounts and focus falls to `<body>`; Escape does nothing until the user tabs back in. The same applies to "Hand over" | script: `[focus after open] BODY`, `[escape closed group] false` |
| **QA25-02** | Medium (keyboard / a11y) | super_admin | `/admin/bdms` BDM managers card | Click "Deactivate M" | Focus moves into the group | Same cause: focus is lost to `<body>` | same pattern (the card's Deactivate also unmounts) |
| **QA25-03** | Low | admins | deactivate / handover / manager group | Server answers 5xx | Plain words ("We couldn't … Please try again."), the bdm-006 QA6-04 precedent | "Internal Server Error" (the raw detail) | `04-deactivate-500.png`; `[deactivate 500 message] Internal Server Error` |

All three are caused by bdm-025 and are in scope. They are fixed below, each test-first.

**Found during the re-check (screenshot review):**

| ID | Severity | Role | Page | Steps | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| **QA25-04** | Low (responsive) | super_admin | `/admin/bdms` BDM managers card, ≤640 px | Open on a phone | A labelled card per manager, like the BDM list (tel-001 QA-04 pattern) | A cramped 3-column table (no overflow, but squeezed) | `layout-375.png` before the fix |

## 4. Fix pass (2026-10-06, test-first, each test seen failing first)

| ID | Fix | Test |
|---|---|---|
| QA25-01 | `AdminBdmHandover` gives its group `tabIndex=-1` and focuses it on open (`useFocusAfterRender`), so Escape and Tab work at once | `AdminBdmHandover.test.tsx` "takes focus when it opens…" |
| QA25-02 | The same for the managers card's group (`manager-group-<id>`) | `AdminBdmManagersCard.test.tsx` "the group takes focus…" |
| QA25-03 | A 5xx now reads "We couldn't deactivate X. Please try again." / "We couldn't hand over X's work. Please try again."; a 4xx keeps the server's sentence | `AdminBdmHandover.test.tsx` "words a server error" ×2, the card test |
| QA25-04 | The card carries `.bdm-managers`, added to the ≤640 px phone-card rules in `globals.css`; its first cell is labelled `Name` like the BDM list | `AdminBdmManagersCard.test.tsx` "uses the stacked phone layout…" |

**Re-check on the rebuilt web container:**
- The web BDM admin set passed 63/63; `tsc` 0; eslint 0.
- Exploratory script: "[focus after open] DIV …", "[escape closed group] true", "[deactivate 500 message] We couldn't deactivate … Please try again."
- No sideways scroll at 1366, 768, 375 or 320 px; `managers-375.png` shows the stacked cards.
- Playwright `bdm-025-deactivation.spec.ts`: 2 passed.

One harness note: a re-run once stalled on the admin sign-in page, because the script's rapid repeated logins hit the existing login
throttle. A single login a minute later returned 200, and the affected groups then passed. This is not a product issue.

**Found in verification (Phase 8 LITE run): QA25-05 (Medium, concurrency)**

- **Symptom:** `test_bdm_002_assign.py::test_concurrent_reassigns_serialize` failed: two concurrent reassigns of one organization by
  its manager answered `[200, 404]` instead of `[200, 200]` / `[200, 409]`. It is intermittent on `main` too (2/15 runs at
  `442ce465`). bdm-025's extra history insert widens the window (6/15).
- **Root cause:** `bdm_organizations.load_scoped(lock=True)` used `FOR UPDATE` with the manager scope as a semi-join on
  `bdm_profiles`. Postgres's READ COMMITTED re-check combines the updated organization row with the *originally joined* profile row
  (the old assignee's), so a row still in scope was dropped → 404.
- **Fix:** lock by id, then evaluate the scope in a fresh statement.
- **Evidence:** the race test 30× plus the bdm-025 race tests 30× → 120/120 passed (it was 6/15 failing before the fix).
- `test_bdm_025_concurrency.py` keeps 404 as a legitimate outcome only when the deactivation moved the organization to another
  manager's team first.

**After QA25-05 (on `2efee1c9`):**
- all `test_bdm_*` passed except 3 failures that are pre-existing on `main` (see the backlog status);
- Playwright bdm-025 / 001 / 002 / 010 / 006: 17 passed on the rebuilt stack.

**Open issues caused by bdm-025: none.**
