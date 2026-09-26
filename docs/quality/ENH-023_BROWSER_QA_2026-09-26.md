# ENH-023 — Browser QA, fixes and final verification (2026-09-26)

**Scope:** `ENH-023` (`DEC-SCOPE-030`, partnership tier change: upgrade/downgrade workflow). An exploratory QA pass,
test-first fixes for its findings (plus the app-wide date-zone sweep the owner asked for after QA-023-07), then a final
verification pass that retested every acceptance criterion (spec §10, AC-1..AC-18) through the browser. No code was
changed during either QA pass.

**Environment:**
- **Build:** branch `feature/enh-023-tier-change-workflow`. First pass on `9d0bf1b`; fixes `26bdb7a`, `575226d`,
  `45c73c6`, `5a00904`; date sweep `8a933d0`; simplification `8541bbe`. The final pass ran on `8541bbe` — the running
  images were checked against it, not assumed (API: the seven changed `app/` files are byte-identical by SHA-256; web:
  the compiled chunk holding `TierDowngradeConfirm` has the same content hash as a fresh local build of `8541bbe`, and
  neither build contains the pre-`8541bbe` `" IST"` literal).
- **Stack:** isolated Compose project `enh023` — web :3230, API :8230, its own migrated and seeded Postgres and Redis.
- **Browser:** Playwright's bundled Chromium with a throwaway profile, driven over CDP (Browser Use). Console errors,
  page errors, unhandled rejections and every `fetch` (method, URL, status; bodies for the tier and notification
  endpoints) were captured on every page.
- **Hidden-window caveat:** in a background window `requestAnimationFrame` does not run, so `refocus()` (focus back to
  Save after Escape/Cancel) cannot be observed; an early reading of "focus on `<body>`" was this artifact. Focus results
  below were taken with the page visible (`Page.bringToFront`, `document.visibilityState === "visible"`, rAF confirmed
  running).

**Accounts:** the seeded Overseas Admin, Super Admin, coordinator, principal and parent; a school created through the
UI for this pass (`BC16E1FB`, Platinum) with its seeded coordinator; two principals of that school added directly in
the isolated database (one to receive notices, one with none, for the empty state). Test data only — no code.

**Not committed:** the raw screenshots (34), scripts and captured logs.

## First pass — findings and resolution

| ID | Severity | Finding | Status | Evidence of the fix (final pass) |
|---|---|---|---|---|
| QA-023-01 | Medium | Saving a past "valid until" date silently expires the partnership — no warning, no notice to the school. | **Not changed — needs a product decision.** The spec allows it (D6/D11: expiry is not a tier change and is not notified, per `ENH-022` D2/D6). | Recorded as `ENHANCEMENT_BACKLOG.md` ENH-023 follow-up (h). |
| QA-023-02 | Low | Edit panel, Partnership section: the tier select and the valid-until date sat 16 px apart vertically (desktop, tablet). | **Fixed** `26bdb7a` | Same top edge at 1440, 768 (side by side) and 375 (stacked); E2E asserts ≤1 px. |
| QA-023-03 | Low (pre-existing, exposed by ENH-023) | The seeded Sunrise school had no School ID, so the edit panel — the only tier-change UI — could not find it. | **Fixed** `575226d` | `EE6713B5` looks up (Platinum). The seed only fills a missing code. |
| QA-023-04 | Low | A failed save gave no clear outcome. | **Fixed** `26bdb7a` | Injected 500 → "The save could not be confirmed. Look the school up again to check before retrying."; network failure → "…it is not known whether the changes saved…"; both `role="alert"`, focused; nothing saved. |
| QA-023-05 | Low (pre-existing `ENH-009` behaviour) | Saving an unchanged form reported success. | **Fixed** `26bdb7a` | "No changes to save." |
| QA-023-06 | Low (pre-existing) | "—" vs "Not set" tier labels; no `aria-current` on portal navigation; every notice's link was named just "Open"; opening a notice did not mark it read. | **Fixed** `45c73c6` | "Not set" in both panels; `aria-current="page"` on desktop nav and the open mobile menu; links named "Open: {title}"; Open sends `PATCH …/notifications/{id}/read` (200) and the "new" badge is gone on return. |
| QA-023-07 | Low (pre-existing, `ENH-005`) | `/school/coordinator/transfers` threw React hydration error #418 (dates formatted in the server's zone vs the browser's). | **Fixed** `5a00904`, then app-wide in `8a933d0` | No #418 on any page visited, in Asia/Kolkata or America/New_York. |

## Final pass — acceptance criteria (spec §10)

| AC | Verdict | Browser evidence |
|---|---|---|
| AC-1 | **PASS** | Gold → Platinum saved with no confirmation; the outcome lists the 7 gained services and takes focus; audit row `direction: upgrade`, `from_tier: gold`, `to_tier: platinum`, `gained`. Coordinator, principal and acting admin each got the notice (10 tier changes → 10 in-app notices and 10 email `NotificationDelivery` rows per role; email status `not_configured`, no provider in this stack). |
| AC-2 | **PASS** | Each downgrade and removal notified all three roles with exactly the lost services and "Work already started for them can still be completed." |
| AC-3 | **PASS** | A valid-until-only save wrote a `direction: unchanged` audit row and sent no notice; the 409 attempt sent none either. |
| AC-4 | **PASS** | PATCH responses carry `tier_change`; a branch-only save returned `tier_change: null` and wrote no tier audit row. |
| AC-5 | **PASS** | Preview: coordinator 403, anonymous 401, unknown school 404, bad tier / malformed id 422, same tier `direction: unchanged`. |
| AC-6 | **PASS** (1 of 14 routes in the browser) | After Platinum → Gold, attendance on a campus visit created before the downgrade succeeded; one `school.tier_grandfathered` row, no denial row. The other 13 routes are covered by `test_enh_023_tier_change.py`. |
| AC-7 | **PASS** (browser part) | A new campus visit after the downgrade: 403 "This school's Gold partnership does not include Monthly campus visits (requires Platinum or higher)." The direct-database case is covered by tests. |
| AC-8 | **PASS** | The same grandfathered visit was refused once the Gold partnership expired ("…partnership expired on 01 Sep 2026."); `school.tier_access_denied`, `reason: expired`. |
| AC-9 | **PASS** | Downgrade then re-upgrade left distinct `school.tier_update` rows (7+ in sequence). |
| AC-10 | NOT TESTABLE in a browser | `test_concurrent_tier_changes_queue_and_record_true_transitions` passes. |
| AC-11 | NOT TESTABLE in a browser | `test_failing_email_never_fails_or_undoes_the_tier_change` passes. |
| AC-12 | **PASS** | Upgrade: no confirmation. Downgrade: the lost list, Confirm focused, Enter confirms; Escape and Cancel return focus to Save and keep the selection; changing the tier while the confirmation is open dismisses it (nothing saved). Preview 500 / network and save 500 / network each render `role="alert"`, save nothing, and leave no button disabled. |
| AC-13 | NOT TESTABLE in a browser | The `ENH-022` suites pass unedited. |
| AC-14 | **PASS** | Principal page lists the notices; a principal with none sees "No notifications yet. You will be told here when your school's partnership changes."; coordinator, Overseas Admin and parent get "School Principal role required". |
| AC-15 | **PASS** | Another admin's change, then a save from the stale form: 409 "This school's tier changed to Gold since you looked it up. Look it up again before changing the tier." as an alert; nothing saved, no notice. |
| AC-16 | **PASS** | `tier: ""` stored as null, audited `to_tier: null`; preview `tier=` is a removal; "Not set" in the UI asks for confirmation listing every lost service. |
| AC-17 | **PASS** | `/openapi.json`: PATCH → `SchoolUpdateOut` (`tier_change`: `TierChangeOut` or null), preview → `TierChangeOut`, `SchoolUpdate.expected_tier`. |
| AC-18 | NOT TESTABLE in a browser | The failure-log test asserts exactly `{school_id, recipient_id, error_type}`, no `exc_info`. |

**Viewports:** 1440×900, 768×1024, 375×812 — no horizontal scroll on the edit panel, the confirmation, or the
coordinator and principal notification pages; the confirmation's buttons are 49 px tall and inside the viewport.
**Console:** no errors. **Network:** every 4xx was intended; the public pages' 401 on `/api/v1/auth/me` is the
signed-out session check. **Server logs:** no 500s or tracebacks during the pass.
**Date zones:** school-portal times stay India time with "IST" for a New York viewer; public event/webinar times follow
the viewer ("13:39 EDT" / "23:09 IST"); admin transfer dates follow the viewer.

## Observations (not acceptance failures)

- Removal outcome reads "Partnership is now no partnership tier." — awkward copy (follow-up (i)).
- A preview failure shows the server's raw `detail` ("Internal Server Error"); the save path has friendlier wording
  (follow-up (i)).
- Two `fetch` failures without a URL appeared once, while the harness signed out and navigated with the mobile menu
  open; not reproducible on the page itself. Most likely in-flight route prefetches aborted by navigation — cause not
  proven.
