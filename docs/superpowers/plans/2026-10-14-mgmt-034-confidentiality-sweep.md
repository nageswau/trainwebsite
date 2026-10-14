# mgmt-034 — Confidentiality + permission sweep (plan)

Spec: `docs/superpowers/specs/2026-10-14-mgmt-034-confidentiality-sweep-design.md`. Tests run in the `mgmt034` stack (`docker exec mgmt034-api-1 pytest …`).

1. **Helpers** — `tests/mgmt034_helpers.py`: CS4 roles inserted directly, `headers()` from tel026, `world()` making a ledger category,
   a submitted ledger entry by the accountant, a draft entry, a reversible approved entry, an entry with a receipt, an investment, a department,
   a school, a discussion (owner responsible, one shareable attachment), a task (owner), a far-future plan with an item, a meeting
   (owner invited), a past-month review draft. Verify: a smoke test builds a world.
2. **Matrix + inventory (RED→GREEN)** — `test_mgmt_034_matrix.py`: write the inventory test first (fails until all 97 rows exist), then the
   rows from RBAC §2.112–§2.145. Run; every failing cell is checked against code and docs (CS5): an expectation error is fixed in the row, a
   documented-rule breach is a gap (CS10).
3. **Delta sweep (RED)** — `test_mgmt_034_confidentiality.py`: snapshot → plant → re-read per role; positive control for the partner.
   Expected RED: the accountant's ledger list / accounts / salaries change when a commission receipt is planted (CS1).
4. **CS1 fix (GREEN)** — exclude `university_commission` lines for callers without `can_view_university_commission` in the ledger list
   and totals, the accounts income and receivables, the salary revenue; any other consumer the sweep flags. Rerun mgmt-004/005/011/013 tests.
5. **Assignee slices (CS8)** — exact key sets + another staff member + 404.
6. **upc-033 (CS9)** — add `partner`, `accountant` users and roles; rerun upc-033 matrix + commission sweep.
7. **Frontend check** — if a CS1 field becomes null/absent for the accountant, the page must render it (vitest + tsc + build).
8. **Docs** — RBAC §2.146, DEC-SCOPE-221, API §12EI, backlog status, QA evidence.
