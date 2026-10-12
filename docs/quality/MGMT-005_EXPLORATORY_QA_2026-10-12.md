# mgmt-005 — Automatic ledger sources — exploratory browser QA (2026-10-12)

- **Build under test:** `feature/mgmt-005` (production web image, isolated stack `mgmt005`, `http://localhost:13005`, API `:18005`), seeded
  with `python -m app.seed`; the shared test DB also holds the backend tests' source rows (random past months).
- **Tools:** Playwright (Chromium, isolated contexts per role) driven by a scripted exploratory pass, plus the committed specs
  `tests/e2e/mgmt-005-auto-lines.spec.ts` and `mgmt-004-ledger.spec.ts`. Console errors, page errors, failed requests and 4xx/5xx API
  responses were captured on every page.
- **Roles:** accountant, partner one, super admin, IT admin, signed out.
- **Viewports:** 375×812, 768×1024, 1366×900.

## Covered

- **Happy path.** "Lines: Manual + automatic" → automatic rows with the "Automatic" badge, source and kind text, no link. Totals read
  "Income (approved + automatic)".
- **Data cases.**
  - 2024-06 shows a BDM trip expense (Travel, IT Training) and a paid agent commission (Agent commissions, Abroad Education).
  - 2021-04 shows a GBP university receipt as "£300.00 · Not counted" with the note "Not counted (not in rupees): £300.00 income
    (1 line)."
  - Recruiter payment and INR university receipt lines are shown. No line carries a person name.
- **Filters.**
  - An empty month shows "No ledger entries match these filters."
  - `status=approved` and a category filter leave no automatic rows.
  - A hand-edited `include=everything` falls back to "Manual entries only" with no error.
- **Navigation.**
  - Apply → back → forward → reload keeps the selection.
  - The Next page link keeps `include=auto`.
  - The Lines select is reachable by Tab after Status.
- **Access.**
  - The partner sees automatic lines.
  - The super admin and the IT admin get "Access unavailable"; the API returns `403`.
  - Signed out is sent to `/admin/login?next=…include%3Dauto`.
- **Layout and health.**
  - No horizontal page overflow at any viewport; the table scrolls in its own region on a phone (mgmt-004 QA-03 pattern).
  - No broken images and no console errors.
  - The only failed requests were Next.js `_rsc` prefetches aborted by navigation (framework behaviour, not this feature).

## Issues

None found in the first pass. Nothing in this feature needed fixing.

## Not in scope / observations

- Agent-deposit exclusion and per-source reconciliation are proven by the backend tests (`test_ac2…`, `test_ac4…`). The browser cannot
  link a line to its payment type.
- Drill-down from an automatic line to its source (`source` + `id`) is mgmt-033. The rows are plain text until then.
- Student and agent names stay off automatic lines until Q-32 is answered.
