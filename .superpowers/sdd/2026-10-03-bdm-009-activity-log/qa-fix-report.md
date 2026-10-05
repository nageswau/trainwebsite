# bdm-009 browser-QA fix report (HEAD 5de59d95)

RED run (4 test files, web-test): 8 failed / 44 passed. Failures by finding:
- QA9-01: BdmOrganizationDetail "has exactly one status live region" -> "expected [ ...(2) ] to have a length of 1 but got 2"; Timeline tests asserting `onNotice` ("Activity logged." / locked "") -> "expected spy to be called with ...".
- QA9-02: BdmActivityForm "carries the activity-form layout class" failed (no `activity-form` / `activity-direction` classes).
- QA9-03: Timeline "opening Log activity or Edit clears the previous notice" (last onNotice call not ""); Day "starting the next Log activity clears the previous notice" failed.
- QA9-04: Day "logging onto another day announces which day" failed (ISO date printed).
GREEN: `vitest run tests/components/Bdm tests/lib/bdm tests/lib/navigation` 23 files / 212 tests pass; `tsc --noEmit` clean; eslint on touched files clean; `next build` OK; ruff clean; `pytest tests/test_bdm_009_service.py` 9 passed.

## Changes
- QA9-01/05: BdmActivityTimeline drops its own role=status; takes `onNotice(text, focusStatus?)`. BdmOrganizationDetail passes a callback that sets `notice`, clears `failure`, and focuses `statusId` when `focusStatus` is true (logged / deleted only: the saved path keeps focus on the Edit button, as before). Texts unchanged. bdm-002 e2e spec untouched.
- QA9-02: form gets `form-grid activity-form`; globals.css: align-items:start, message + actions span both columns, Direction fieldset (`activity-direction`) bordered like fieldset.form-section; legend kept. 640px single-column rule still applies (not changed). Visual check pending in browser after rebuild.
- QA9-03: notice cleared when Log opens (Timeline + Day), when Edit opens (new optional `onEdit` prop on BdmActivityItem), and on `onLocked` (both).
- QA9-04: past-day notice uses `formatCalendarDate(went)` ("05 Oct 2026").
- DOC: bdm_activities.py `refused` docstring reworded (no behaviour change).

Deviation: `onNotice` has an optional second arg `focusStatus` so that the "saved" notice does not steal focus from the Edit button.
