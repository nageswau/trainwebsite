# bdm-006 — Browser QA pass 1 (exploratory, no code changes) — 2026-10-03

**Build under test:** `feature/bdm-006-appointments` @ `c3b5413a` (bdm-010 merged; migration `0069_bdm_appointments`, `DEC-SCOPE-064`).
**Environment:** isolated stack `docker compose -p bdm006` — web `http://localhost:3006`, API `:8006`, DB at `0069_bdm_appointments (head)`, seeded.
**ID note (merge of `main` @ `e376c25c`, 2026-10-05):** this pass ran on the build numbered `DEC-SCOPE-064` / `0069_bdm_appointments`; after bdm-003 (`0069_bdm_org_profiles`) and AGN-019 / AGN-020 / AGN-022 merged first, bdm-006 is `DEC-SCOPE-068` with migration `0070_bdm_appointments`. The findings are unchanged.
**Browsers:** Browser Use against an **isolated Microsoft Edge 154** (own profile, CDP port 9340 — Chrome was in use by another session); Playwright (Python, isolated headless Chromium) for scripted checks with route interception and CDP network throttling; the repo's Playwright e2e specs in the `web-test` container.
**Accounts:** throwaway, created through the real admin API — College BDM (owner), College peer BDM (no organizations), School BDM, BDM manager (team), other BDM manager (empty team), super_admin; one archived organization.
**Scope rule for this pass:** observe and report only — nothing was fixed.

## 1. Automated evidence

| Run | Result |
|---|---|
| Playwright e2e `bdm-001-bdm-profile`, `bdm-002-organization-crm`, `bdm-006-appointments` (`--workers=1`) | **10 / 10 passed** (4.7 min). The bdm-006 journey books from the organization page, confirms, reschedules (history keeps the old time), waits for the start, completes with an outcome, checks the archived organization and the manager's read-only view and the 375 px list. An earlier, concurrent run had one transient `waitForURL` timeout in bdm-002; it did not reproduce. |
| Scripted exploratory QA (`qa_full.py`, 34 checks) | 30 pass; the 4 fails triaged below — 1 real issue (QA6-01), 3 test artefacts re-verified as working. |
| Scripted scenario QA (`qa_bdm006.py`, 16 checks) | 15 pass; 1 fail (overlap alert focus) re-verified by hand in Edge as working (focus lands on the alert heading within 0.5 s). |

## 2. Coverage of the 20 requested areas

| # | Area | Result | Evidence |
|---|---|---|---|
| 1 | Happy path | ✅ org page → Add appointment → book → detail ("Appointment APT-… booked."), confirm, reschedule (history "moved from …"), edit, cancel; complete with outcome in e2e | q01-booked.png, 08-history (e2e) |
| 2 | Invalid inputs | ✅ past time blocked (browser `min`; server 422 "Choose a time in the future" behind it); Type required blocks submit; whitespace-only cancel reason → "Enter a reason."; malformed id URL → "Appointment not found". ⚠️ QA6-01 (bad query value), QA6-05 (numeric errors only as browser bubble) | q02-bad-status.png |
| 3 | Empty states | ✅ new BDM "No appointments yet." + Book; no assigned organizations → disabled Book + "Only organizations assigned to you can be booked." hint; filters "No appointments match these filters."; other manager "Your team has no appointments in this period." | q03-peer-new.png |
| 4 | Server errors | ✅ list 500 → "Unable to load appointments." + Retry (recovers); booking 500 → alert, entry kept; network drop on an action → "The request did not complete … your entry is kept." ⚠️ QA6-04 (generic wording) | q04-list-500.png, q04-book-500.png, probe3-retry.png |
| 5 | Loading states | ✅ "Loading appointments…"; under 2.5 s latency "Saving…", "Confirming…", action toggles disabled while busy | probe3-saving.png |
| 6 | Cancel / back | ✅ Reschedule Cancel and Escape close the group and return focus to the trigger; Edit Cancel restores the details; browser Back restores the previous filter | — |
| 7 | Refresh | ✅ booked notice shown once (not repeated on reload); list filters survive reload | — |
| 8 | Duplicate submission | ✅ double-click Book → 1 POST; double-click Confirm → 1 POST | — |
| 9 | Unauthorized (signed out) | ✅ `/bdm/appointments(/id)` → `/bdm/sign-in?next=…`; `/bdm/manager/appointments` → `/admin/login?next=…`; API 401 | — |
| 10 | Incorrect role / scope | ✅ peer BDM: another BDM's appointment → "Appointment not found", another BDM's organization not preselected; School BDM sees school types only and cannot open the college appointment; manager & super_admin: read-only detail (no action buttons), BDM-portal pages → "Access unavailable — BDM role required"; other manager → not found | q10-manager-detail.png, q10-manager-on-bdm-page.png |
| 11 | Desktop layout (1366) | ✅ no overflow. ⚠️ QA6-02, QA6-03 (visual), QA6-06 (pre-existing shell) | q11-desktop-*.png, bu-overlap.png |
| 12 | Tablet layout (768) | ✅ no horizontal page scroll | q11-tablet-*.png, bu-tablet-*.png |
| 13 | Mobile layout (375 / 320) | ✅ no horizontal page scroll; detail `<dl>` and action buttons wrap; table scrolls in its own region | q11-mobile*-*.png, bu-mobile-*.png |
| 14 | Navigation | ✅ "Appointments" in both sidebars and highlighted (`aria-current`); code cell links to detail; "Back to appointments"; organization link on the detail goes to the right portal | — |
| 15 | Success messages | ✅ "Appointment APT-… booked.", "Appointment confirmed.", "Appointment rescheduled.", "Appointment cancelled.", "Changes saved." (role=status) | — |
| 16 | Error messages | ✅ readable server messages (archived, foreign type, past time, 409 "This appointment changed — it is now Cancelled."). ⚠️ QA6-04 | 10-stale.png |
| 17 | Broken images | ✅ none on list / new / detail / organization pages | — |
| 18 | Console errors | ✅ no application errors or hydration warnings. Only the browser's native "Failed to load resource" lines for the deliberately provoked 409 / 422 / 500 / offline (QA6-07, info) | qa_full.json |
| 19 | Failed network calls | ✅ only the intentionally simulated ones; ~300 `net::ERR_ABORTED` are Next.js link-prefetches cancelled by navigation (benign) | qa_full.json |
| 20 | Unexpected redirects | ✅ none — only the expected sign-in redirects and post-create navigation to the detail page | qa_full.json |

## 3. Issues

| ID | Severity | Role | Page | Reproduction | Expected | Actual | Console / network evidence | Screenshot |
|---|---|---|---|---|---|---|---|---|
| **QA6-01** | Low | BDM (any list user) | `/bdm/appointments?status=bogus` (also an invalid `date_from` / `type` in the URL) | 1. Sign in as a BDM. 2. Open `/bdm/appointments?status=bogus` (e.g. an edited or stale bookmark). 3. Click Retry. | Invalid URL filter values are ignored (fall back to defaults) or the page says which filter is invalid; the list still loads. | "Unable to load appointments." with Retry; Retry repeats the same failing request forever. (Also noted by the final code review as a deferred minor.) | `GET /api/v1/bdm/appointments?limit=50&offset=0&date_from=2026-10-03&status=bogus → 422`; console "Failed to load resource: … 422" | q02-bad-status.png |
| **QA6-02** | Low (visual) | BDM | `/bdm/appointments/new`, Edit form | Open Book appointment at any width. | Fieldset groups ("Who", "When", "Details", "Estimates") styled like the app's cards / sections. | Raw browser-default fieldset borders (grey groove) and cut-in legends — visually out of step with the rest of the portal. | — | q11-desktop-new.png, bu-mobile-new.png |
| **QA6-03** | Low (visual / UX) | BDM | `/bdm/appointments/new`, Reschedule | Book a time that overlaps an existing appointment. | The overlap warning reads as a warning (alert styling, colour/icon) near the action that triggered it. | Plain white card at the very bottom of a long form (below the fold on desktop); same look as ordinary cards. Focus does move to its heading (works for keyboard/screen-reader users). | `POST /api/v1/bdm/appointments → 409 possible_overlap` (expected) | bu-overlap.png |
| **QA6-04** | Low | BDM | `/bdm/appointments/new` (and actions) | Simulate a server failure on booking (POST returns 500 with a non-JSON body). | An actionable sentence, e.g. "We couldn't save the appointment. Please try again." | "Something went wrong." (entry is kept — good). | simulated `POST /api/v1/bdm/appointments → 500` | q04-book-500.png |
| **QA6-05** | Low (a11y) | BDM | `/bdm/appointments/new` | Enter `-3` in Expected leads and `-10` in Expected revenue; submit. | Inline field error tied to the field (`aria-invalid` + message), as spec §12.2 R-F6 describes. | Submit is blocked only by the browser's native validation bubble (no request sent — data safe); no inline message. (R-F6 gap already recorded as inherited from the brief.) | no POST sent | — |
| **QA6-06** | Info — pre-existing, not bdm-006 | all portal users | any long page (e.g. Book appointment on desktop) | Open a page taller than the viewport and scroll. | Sidebar background spans the full page height. | The dark sidebar ends at the first viewport height; white below it. Comes from the shared `PortalShell`, not from bdm-006 code. | — | q11-desktop-new.png |
| **QA6-07** | Info | BDM | new / list | Trigger an overlap 409 or a bad filter 422. | — | Browsers log every 4xx/5xx fetch as a console "Failed to load resource" line; no application-level console errors or hydration warnings were seen in any run. | console | — |

**Already known, re-confirmed (not new):** no "View appointments" link from the organization page (the list supports `?organization=` but nothing links there); the default list starts at today, so open past (overdue) appointments are hidden — owner decided to keep this (spec §6.2).

## 4. Checks that failed in scripts but were re-verified as working (not issues)

- **List 500 → Retry:** recovers and renders the table (my first check used a wrong locator). probe3-retry.png
- **Busy labels:** "Saving…" / "Confirming…" and disabled toggles appear under real 2.5 s latency (my first check blocked Playwright's event loop with a sleeping route handler). probe3-saving.png
- **Overlap alert focus:** in Edge, focus is on the alert heading 0.5 s after the 409 (the script sampled before React's effect ran).
- **Negative numbers:** the browser blocks the submit (no POST) — recorded as QA6-05 for the missing inline message only.

## 5. Not covered in this pass

- Completing / marking no-show by hand in the browser (needs a past start time; covered by the e2e journey and API tests).
- Screen-reader announcement wording (only ARIA roles/attributes were inspected).
- The independent Codex review (owner).

## 6. Fix pass (2026-10-03) — test-first, independently reviewed

| ID | Fix | Commit |
|---|---|---|
| QA6-01 | The list sanitizes URL filters before calling the API: unknown status/type dropped, invalid or calendar-impossible dates fall back (From → today, To → none), To earlier than From dropped. A stale URL can no longer wedge the list. | 38368e4d |
| QA6-02 | Booking-form groups use the existing `fieldset.form-section` style. | 0d97c130 |
| QA6-03 | The overlap warning reuses bdm-002's duplicate-warning style (`role="alert"` `form-error`), sits directly above the submit button, and its heading is focused and scrolled into view. | 0d97c130 |
| QA6-04 | Server errors (5xx) read "We couldn't save the appointment. Please try again — your entry is kept." (form) / "We couldn't update the appointment. Please try again." (actions); 4xx keep the server's message; a network drop keeps "did not complete". | 8752356a |
| QA6-05 | Expected leads / revenue validated inline before sending: `aria-invalid` + `aria-describedby` message ("…whole number from 0 to 1,000,000." / "…from 0 to 9,999,999,999.99, with up to 2 decimals."), focus to the first invalid field, error clears on edit; native `min` removed so the message isn't pre-empted. | 8752356a, ffb096aa, 6f333652 |
| QA6-06 | Fixed 2026-10-05 (owner asked). Root cause re-measured in Edge 154: while scrolling, the sticky sidebar covers the left column at every position; the white strip appears only in full-page captures / print, because the sidebar is one viewport tall and its grid column had no colour. `globals.css` now paints the 270 px column navy at ≥981 px; ≤980 px unchanged. | `apps/web/app/globals.css` |
| QA6-07 | Informational — nothing to change. | — |

Verification: web vitest (appointment components, panel, lib) 48 passed in the fix wave and 43 passed on the follow-up subset; `tsc --noEmit`, eslint and `next build` exit 0. Independent review: all five ADDRESSED, no new breakage.

**Browser re-check (after `docker compose -p bdm006 -f docker-compose.yml up -d --build web`):**
- Playwright re-check script, 6 / 6 passed: QA6-01 (`?status=bogus&type=nope&date_from=2030-13-99` → list loads); QA6-02 (all four fieldsets `form-section`); QA6-05 (`-3` leads → inline "…whole number from 0 to 1,000,000.", `aria-invalid="true"`, focus on the field, no POST; error clears on edit); QA6-04 (simulated 500 → "We couldn't save the appointment. Please try again — your entry is kept.", entry kept); regression (valid booking with revenue 1500.5 → detail shows ₹1,500.50); QA6-03 (overlap alert `role="alert"` `form-error`, above Book, in the viewport, heading focused).
- Edge (Browser Use): desktop Book appointment form shows styled sections; mobile 375 px has no horizontal scroll (mobile screenshot timed out in the background tab — width checked by script). Screenshots: re-edge-desktop-new.png, re-03-overlap.png, re-05-inline.png, re-01-bad-url.png.
- Playwright e2e `bdm-006-appointments` + `bdm-002-organization-crm`: **3 / 3 passed** (3.8 min).
- Console: only the browser's native "Failed to load resource" lines for the deliberately provoked 500 and 409.

QA6-01 to QA6-06: **closed**. QA6-06 check (Edge, `probe_qa606.py`): before — full-page capture at 1366 white below 768 px; after (rule injected on the running build) — navy to the page bottom at 1366×768 and 1920×600; 980/768/375/320 px keep the plain background and no horizontal scroll. Re-checked on the rebuilt web container (no injection), Edge 154: .portal carries the navy column at 1366x768 and 1920x600, full-page captures navy to the bottom (qa606-after-*.png); 980/768/375/320 px: no gradient, scrollWidth equals the viewport.

## 7. Artefacts

Screenshots, scripts and raw JSON evidence are in the session scratchpad: `scratchpad/qa/*.png`, `scratchpad/qa_full.py`, `qa_full.json`, `qa_bdm006.py`, `qa_results.json`, `qa_probe*.py`, `e2e-bdm006-qa.log`.
