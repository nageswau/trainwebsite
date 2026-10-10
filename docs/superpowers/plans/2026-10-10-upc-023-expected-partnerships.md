# upc-023 Expected partnerships Implementation Plan

> **For agentic workers:** executed natively (superpowers:executing-plans) in the upc-023 session. Steps use checkbox syntax.

**Goal:** the §23 Expected University Partnerships screen, the §24 probability (stage + override) and the weighted forecast (E1–E4).
**Architecture:** a pure forecast fold in `services/partnership_metrics.py`, a read route + an override route in a new
`api/partnership_expected.py`, two nullable columns on `universities`, a server-rendered Next page plus forecast cards on the targets page.
**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Next.js (app router), vitest, Playwright.
**Spec:** `docs/superpowers/specs/2026-10-10-upc-023-expected-partnerships-design.md`

## Global Constraints
- Probability per stage = `app.partnership_stages.PROBABILITY`; override integer 0–100 with a reason ≤ 500 chars.
- IST dates from the DB clock (`india_date(await db_now(db))`); calendar quarters.
- Readers: partnership_manager (profile), partnership_head, super_admin; others 403. Override: `can_move_stage`.
- Weighted = round(Σ probability / 100, 1).

## Review Focus
- Expected date exactly on the last day of the month / quarter → inside that window (test the boundaries).
- A university with an override of 0 → counts in `count`, adds 0 to `weighted` (0 is not "no override").
- Lost or inactive university with an expected date → never listed.
- A reason sent with `probability: null` → 422 (clearing takes no reason); whitespace-only reason → 422.
- `offset` past the end → empty items, figures unchanged.

---

### Task 1: Migration + model + detail field
**Files:** `alembic/versions/0143_university_probability.py`, `app/models.py`, `app/services/partnership_universities.py`,
`app/schemas.py`, `tests/test_upc_023_migration.py`
- [ ] RED: parity test (model checks == migration CHECKS, single head after 0142, columns in shared DB, round trip + downgrade refusal).
- [ ] GREEN: migration, `UNIVERSITY_PROBABILITY_CHECKS`, columns; `probability_out(uni)` in detail.

### Task 2: Forecast fold + GET /partnership/expected
**Files:** `app/services/partnership_metrics.py` (`effective_probability`, `windows_for(today)`, `forecast(rows, today)`),
`app/api/partnership_expected.py`, `app/main.py`, `app/schemas.py`, `tests/test_upc_023_expected.py`
- [ ] RED: roles/401/403, scope, AC1, windows + boundaries, exclusions, undated, paging, 422 window.
- [ ] GREEN: implement.

### Task 3: PUT /partnership/universities/{id}/probability
**Files:** same router, `tests/test_upc_023_probability.py`
- [ ] RED: set / clear / 422s / 403 other team / 409 inactive / audit / no-op no audit.
- [ ] GREEN: implement.

### Task 4: Web lib + page + cards
**Files:** `lib/partnershipExpected.ts`, `components/ExpectedForecastCards.tsx`, `app/partnership/expected/page.tsx`,
`app/partnership/targets/page.tsx`, tests in `tests/lib`, `tests/components`.

### Task 5: Override form on the timeline
**Files:** `components/UniversityTimeline.tsx`, `lib/partnershipMilestones.ts` (type), detail page props, vitest.

### Task 6: E2E + docs
**Files:** `tests/e2e/upc-023-expected-partnerships.spec.ts`; DEC-SCOPE-161, API §12CC, RBAC §2.87, DATA_MODEL, backlog status, screen
catalog.
