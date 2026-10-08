# upc-005 — University CSV import — implementation plan

Spec: `docs/superpowers/specs/2026-10-08-upc-005-university-import-design.md`. Branch `feature/upc-005`. TDD per task (red → green → refactor).

## Phase 3 review notes (folded into the tasks)

- **API (api-and-interface-design):** The new routes are additive, and no existing contract changes. `POST …/import` is `201`, because a
  batch is created, even when every row is a duplicate. A replay is `201` with the same body (tel-006 precedent). File problems are
  `422`/`413` with a string `detail`, like every bulk surface. Lists are `{items,total,limit,offset}`. The router must be included
  before `partnership_universities.router` (`/{university_id}` is a UUID path).
- **Transactions:** one transaction per import; the batch claim, the inserts and the audits all commit together. The claim is a
  SAVEPOINT, so a racing duplicate key replays instead of failing. A slug `IntegrityError` rolls everything back (`409`, retry
  with the same key).
- **Security (security-and-hardening):**
  - Roles are checked before reading the file body.
  - The IDOR rule is that history and report lookups filter by uploader (`404` otherwise; `super_admin` sees all).
  - Only `UniversityCreate`-validated values reach the DB, with no raw SQL built from input; the lock keys are bound parameters.
  - The CSV report cells go through `_safe_cell` (formula injection), and `Content-Disposition` names are fixed strings.
  - Size and row caps bound memory.
  - Logs carry ids and counts only.
  - The rendered report is React text, so cells are escaped and there is no XSS.
  - CSRF follows the existing cookie and same-origin proxy conventions of the other multipart uploads (tel-006, ENH-028).
- **Frontend (frontend-ui-engineering):**
  - Reuse `BulkColumnReference`, `toneClass`, `newIdempotencyKey`, `detailMessage` and the `table bulk-report` styles; the table
    has data-labels for mobile cards.
  - Focus moves to the result heading, there is a `role=status` busy message and a `form-error[role=alert]` for errors.
  - The submit button is disabled while busy, with an `inFlight` ref against double clicks.
  - Empty history gets an empty-state line.

## Tasks

1. **Model + migration** — `UniversityImportBatch` in `models.py`; `0113_university_imports` (guarded create, downgrade refusal). Tests:
   `test_upc_005_migration.py` (chain/single head, model parity, round trip in a throwaway DB, refusal).
2. **Service** — `services/university_import.py`: `COLUMNS`/`REQUIRED`, `parse_row` (label normalisation → `UniversityCreate`),
   `resolve_country`, `run(db, user, batch, filled)` (set-based: countries, key locks, existing matches, in-file duplicates, codes,
   slugs, insert, audits), `report`, `report_csv`. `partnership_universities.duplicate_lock_key` is shared with `check_duplicates`.
3. **API** — `api/university_import.py`: template, import, history, report, report.csv; `main.py` registration. Tests:
   `test_upc_005_import.py` (every behaviour in spec §5 pytest).
4. **Web lib + panel + history + page + list link** — vitest `UniversityImportPanel.test.tsx` (the panel renders the history, so it covers both).
5. **Playwright** — `tests/e2e/upc-005-university-import.spec.ts` (AC1, AC2, manager without the link).
6. **Docs** — DEC-SCOPE-128, API §12AV, RBAC §2.54, DATA_MODEL addendum, backlog status.
