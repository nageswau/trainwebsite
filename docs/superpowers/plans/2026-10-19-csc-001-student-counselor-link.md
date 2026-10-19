# csc-001 — Student → counselor link (plan)

Spec: `docs/superpowers/specs/2026-10-19-csc-001-student-counselor-link-design.md`. TDD per task: write the test, see it fail for the
expected reason, implement the minimum, rerun.

| # | Task | Test first | Files |
| --- | --- | --- | --- |
| 1 | Model + migration 0165 | `test_csc_001_migration.py` (head, columns, round trip, downgrade refusal) | `models.py`, `alembic/versions/0165_overseas_student_counselors.py` |
| 2 | Shared scope | lookup tests in `test_csc_001_counselor_students.py` (linked visible, once, other counselor not visible, `q`) | `services/counselor_students.py`, `api/lookups.py` |
| 3 | Appointment write follows the picker | appointment tests in the same file (linked → 201, other counselor's → 403) | `api/workflows.py` |
| 4 | Regression | rerun `test_enh_031_lookups_students.py`, `test_cns_001_counselor_workspace.py`, `test_tel_017_it_counselor.py`, previous migration test `test_agn_024_migration.py` | — |
| 5 | Docs | — | decision register (DEC-SCOPE-226), `DATA_MODEL.md`, `RBAC_MATRIX.md` 2.148, `API_CONTRACT.md` notes, `RTM.md`, backlog status |
| 6 | Browser QA | e2e: counselor's *Schedule appointment* picker offers a linked student and the booking succeeds | `apps/web/tests/e2e/csc-001-*.spec.ts` |

Earlier migration tests assert "one head, and this revision is in the history", which stays true after 0165 — no edits needed.

**Phase 3 review (2026-10-19).** API: no new route, shapes/codes/texts unchanged, read-only scope inside the existing request
transaction. Frontend: none — the existing picker simply offers more rows; its loading/empty/error states are ENH-031's. Security:
per-counselor scope (IDOR test with two counselors), division gates unchanged, ORM-built SQL only, no new logging, no audit row (reads,
ENH-016 D15). No plan change.
