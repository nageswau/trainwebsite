# bdm-025 Deactivation + Portfolio Handover Implementation Plan

> **For agentic workers:** executed natively (superpowers:executing-plans) in the bdm-025 session, TDD per task.

**Goal:** Deactivating a BDM requires a handover choice; open work moves atomically and audited; managers can't be deactivated
while they still have BDMs; pending approvals follow the current manager.

**Architecture:** one new service `app/services/bdm_lifecycle.py` (portfolio filters, locking, move, cancel, notify) and one admin
router `app/api/bdm_lifecycle.py`. `admin.update_user` gains a refusal. One new append-only table, `bdm_assignment_history`. The
web adds `AdminBdmHandover` (row dialog) and `AdminBdmManagersCard`.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL; Next.js/React, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-06-bdm-025-deactivation-handover-design.md`

## Global Constraints
- Every refusal happens before any write. One transaction per route. Lock order: the source's organizations, then the source
  user, then the target `FOR SHARE`.
- Invalid BDM target → 422 "Choose an active BDM of the same module". Invalid manager target → 422 "Choose another active BDM manager".
- PATCH refusals are 422 (never 409: the Users page treats a 409 as the cascade prompt).
- Logs and audit metadata carry ids and counts only.
- Inline authorization pattern (`ensure_admin` + `require_creator_may`); no `require_*` dependencies.

## Review Focus
1. An appointment that starts exactly now or in the past stays with A (`starts_at > now()` boundary) — `test_history_stays`.
2. An archived organization of A stays with A; a later restore keeps A — `test_history_stays`.
3. A second deactivate (double click / two tabs) → 409, with nothing moved twice — `test_bdm_025_concurrency.py`.
4. An Overseas admin trying a College BDM → 403, nothing written — `test_scope`.
5. Target = the BDM itself, or a BDM of another module, or an inactive BDM → the same 422 — `test_invalid_targets`.

## How to run (worktree, Git Bash)
```bash
W="C:/Users/kunam/Documents/project/trainwebsite/.claude/worktrees/bdm-025"
docker compose -p bdm025 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "$W/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <P>"
MSYS_NO_PATHCONV=1 docker compose -p bdm025 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps \
  -v "$W/apps/web:/app" -v /app/node_modules web-test sh -c "npx vitest run <paths>"
```
LITE = `tests/test_bdm_025_*.py tests/test_bdm_001_*.py tests/test_bdm_002_assign.py tests/test_bdm_010_approvals.py tests/test_enh_003_first_time_provisioning.py tests/test_adm_001*.py`

---

### Task 1: Migration + model `BdmAssignmentHistory`
**Files:** create `alembic/versions/0080_bdm_assignment_history.py`; modify `app/models.py` (BDM section); test `tests/test_bdm_025_migration.py`.
- [ ] RED: the test asserts the table and CHECKs exist (inserting a bad `entity_type` / `reason` raises), and that the downgrade
  SQL refuses while rows exist (0077's guard idiom), with a single head.
- [ ] GREEN: the model plus a migration with the `create_all` guard, indexes `ix_bdm_assignment_history_entity` and
  `ix_bdm_assignment_history_from`, and a guarded downgrade.
- [ ] Commit `feat(bdm-025): bdm_assignment_history table (0078)`.

### Task 2: Schemas
`BdmDeactivate {mode: Literal["reassign","leave"], reassign_to: UUID|None}` (extra forbid; a model validator enforces "reassign
needs a target, leave forbids one"); `BdmHandover {reassign_to: UUID}`; `BdmManagerDeactivate {reassign_to: UUID|None}`;
`BdmPortfolio {organizations, appointments, tasks, trips}`; `BdmManagerOption.bdm_count: int = 0`.
Test `tests/test_bdm_025_schemas.py` (parametrized valid/invalid bodies). Commit.

### Task 3: Service `bdm_lifecycle` + deactivate / portfolio routes
**Interfaces (produced):**
- `async portfolio_counts(db, user_id) -> dict[str,int]`
- `async load_bdm(db, actor, bdm_id) -> tuple[User, BdmProfile]` (404 / division 403 / creator 403)
- `async lock_source(db, user_id) -> User` (organizations FOR UPDATE, then user FOR UPDATE, populate_existing)
- `async locked_target(db, profile, target_id, source_id) -> User`
- `async move_portfolio(db, actor, source, target, reason) -> dict[str,int]` (bulk UPDATE … RETURNING, history rows)
- `async cancel_trips(db, actor, source) -> int`
- `async notify_handover(db, source, target, moved)`
- `async deactivate_user(db, actor, user)` (active False, revoke tokens)

Tests `tests/test_bdm_025_deactivate.py`:
- `test_deactivate_without_choice_is_422` (no mode; reassign without a target; leave with a target) — AC1.
- `test_reassign_moves_every_open_item_and_notifies` — 3 organizations, 2 future appointments, 2 open tasks → target. History
  rows, a notification for the target, audit `bdm.deactivate` with counts, login of A → 401 — AC2/AC5.
- `test_history_stays` — completed / cancelled appointments, a past open appointment, a done task, an archived organization, and
  an in-progress trip keep A as owner — AC2.
- `test_not_started_trips_cancelled` — draft / submitted / approved planned trips → cancelled with an audit reason; the approvals
  queue drops the submitted one.
- `test_leave_keeps_items` — mode=leave: nothing moves, A is inactive.
- `test_invalid_targets` — another type, inactive, self, a manager, a random uuid → 422, nothing written.
- `test_scope` — overseas_admin on a College BDM → 403; it_admin on a College BDM → 200; a non-bdm id → 404; a manager role → 403.
- `test_already_inactive_is_409`.
- `test_portfolio_counts`.
Commit per green group.

### Task 4: Handover route (inactive BDM)
`tests/test_bdm_025_handover.py`: leave then handover moves everything (`portfolio_handover` reason, audit, notify); an active
source → 409; nothing open → 409; reactivation restores login but owns nothing that was moved. Commit.

### Task 5: Manager deactivation + `bdm_count` + PATCH refusals
`tests/test_bdm_025_managers.py`:
- `test_patch_deactivate_bdm_is_422`
- `test_patch_deactivate_manager_with_bdms_is_422`; a manager without BDMs via PATCH → 200
- `test_manager_deactivate_moves_team` (active and inactive BDMs; audit; notification; super_admin only → others 403; invalid target 422; inactive source 409)
- `test_pending_trip_follows_manager_change` — a submitted trip: after a PATCH manager change, the new manager can approve and the old one gets 404 — AC3
- `test_pending_trip_follows_bulk_manager_move`
- `test_bdm_managers_list_has_bdm_count`
Update setup-only lines in `test_bdm_001_reads.py` / `test_bdm_001_profiles.py` that deactivate a BDM or manager via PATCH (direct
DB write instead; assertions unchanged). Commit.

### Task 6: bdm-002 reassign writes history
`test_bdm_025_deactivate.py::test_single_reassign_writes_history`; modify `api/bdm_organizations.py` assign. Commit.

### Task 7: Concurrency
`tests/test_bdm_025_concurrency.py`: two concurrent deactivates on separate sessions → exactly one 200 and one 409; each
item moved once (history count == items). Commit.

### Task 8: Web lib + `AdminBdmHandover`
`lib/bdm.ts`: `BdmPortfolio` type, `portfolioUrl`, `bdmSearch(type, excludeId)` (SearchableSelect server mode over
`/admin/bdms?active=true&bdm_type=`). The component `components/AdminBdmHandover.tsx` takes props
`{row, mode: "deactivate"|"handover", onDone(notice), onCancel}`. Test `AdminBdmHandover.test.tsx`: loading → counts; load error
+ Retry; confirm disabled until a choice; reassign requires a picked BDM; leave posts `{mode:"leave"}`; a server 422 is shown in
the alert and focused; the trips note; handover mode with zero counts → "Nothing to hand over."; Escape cancels. Commit.

### Task 9: `AdminBdmRow` + `AdminBdmManagersCard` + panel
Row: Deactivate opens AdminBdmHandover; an inactive row gets "Hand over". The card lists managers (GET `/admin/bdm-managers?limit=50`
with paging) with a count and a Deactivate group (picker when count > 0). Panel: the card is shown for super_admin only. Tests:
update `AdminBdmRow.test.tsx` and `AdminBdmPanel.test.tsx`, new `AdminBdmManagersCard.test.tsx`. tsc + eslint. Commit.

### Task 10: e2e + docs
`tests/e2e/bdm-025-deactivation.spec.ts` (super_admin: create 2 BDMs + organization via API → deactivate A with handover to B
in the UI → counts shown → success notice → A Inactive, "Hand over" visible). Docs: `DEC-SCOPE-080`, backlog status, RTM row,
`API_CONTRACT.md`, `DATA_MODEL.md`, `RBAC_MATRIX.md`. Commit.
