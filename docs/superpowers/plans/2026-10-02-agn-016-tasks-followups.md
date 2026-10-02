# AGN-016 Tasks & Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (owner chose in-session execution with TDD, 2026-10-02).
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** agency Masters and Staff record follow-up tasks on agency students, see open/overdue work, and the agent dashboard shows
"Pending actions".

**Architecture:** one new table `agent_tasks` owned only through `agent_student_id`; scope is AGN-004's `student_scope()` in SQL, so
tasks follow the student on reassignment. A flat router `/workflows/overseas/agent/crm/tasks` reuses AGN-004's gate, lock order and
audit idiom; a functions-only service holds queries and shapes. Frontend: a `tasks` portal section and a per-student card sharing
one panel.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Pydantic 2, Alembic, PostgreSQL 16; Next.js (App Router) + TypeScript; pytest; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-02-agn-016-tasks-followups-design.md` (decisions T1–T8, AC01–AC13).

## Global Constraints

- Route prefix `/workflows/overseas/agent/crm/tasks`; errors are `HTTPException(status, "<text>")`; pages `{items,total,limit,offset}`.
- Out of scope → 404 (`"Task not found"`, `"Student not found"`); gate failures 403 via `api.agent_students._gate`.
- Lock order: `lock_active_org` → scoped row `FOR UPDATE`; audit row in the same transaction; one commit per request.
- Audit actions `agent_student.task_add|task_update|task_complete|task_cancel`, entity = student; metadata ids + field names only.
- Title ≤ 200, notes ≤ 2000 (`clean_free_text`), `due_at` AwareDatetime, status `open|done|cancelled`, cap 100 open tasks per student.
- No new dependencies. No change to `rbac.py`, `workflows.py`, `assign_student`, `next_action`.
- Lite tests only (owner runs the full suite separately): `tests/test_agn_016_*.py` + `test_agn_004_staff_scope.py`,
  `test_agn_001_team.py`, `test_agn_008_dashboard.py`, `test_agn_021_activity.py`; web typecheck + lint.

## Test command

```
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn016 --profile ci run --rm \
  -v "$PWD/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <files>"
```

## Review Focus

1. A task whose student is reassigned between the list read and a write — expect 404 on the write, never a cross-staff edit.
2. `due_at` sent from a browser without an offset (`2026-10-03T10:00`) — expect 422, not a silently UTC-shifted time.
3. An application of the same student but `withdrawn` or School-bridged — expect 422 on link.
4. A PATCH with only `notes: null` on an open task — clears notes, audits `["notes"]`; `title: null` → 422.
5. `view=all` paging across open and closed tasks — stable order (open by due, then closed by closed_at desc, id tiebreak).

Each line has a test in the owning task below.

---

### Task 1: Model and migration

**Files:** Modify `apps/api/app/models.py` (after `AgentStudentShortlistEntry`); Create
`apps/api/alembic/versions/0059_agent_tasks.py`; Test `apps/api/tests/test_agn_016_migration.py`.

**Produces:** `AgentTask` (columns per spec §2); `TASK_STATUSES = ("open", "done", "cancelled")`.

- [ ] RED: tests — revision chains after `0057_agent_applications` and is the single head; model columns/nullability/index;
  round trip in a throwaway database (upgrade creates table + CHECKs; a row violating `ck_agent_tasks_closed` is rejected;
  downgrade drops it; downgrade refuses while rows exist).
- [ ] Run → fails (module missing).
- [ ] GREEN: model + guarded migration (`0057` idiom).
- [ ] Run → pass. Commit `feat(agn-016): agent_tasks table`.

### Task 2: Schemas

**Files:** Modify `apps/api/app/schemas.py` (after AGN-008 block); Test `apps/api/tests/test_agn_016_schemas.py`.

**Produces:** `AgentTaskCreate(agent_student_id: UUID, title: str, due_at: AwareDatetime, notes: str|None, application_id: UUID|None)`;
`AgentTaskUpdate(title?, notes?, due_at?, application_id?, status?: Literal["done","cancelled"])`.

- [ ] RED: blank/201-char title, 2001-char notes, naive `due_at`, unknown field, `status` + `title`, `title: null`, `due_at: null`
  → ValidationError; trimmed title; blank notes → None; empty update valid.
- [ ] GREEN, run, commit `feat(agn-016): task schemas`.

### Task 3: Create and read (service + router)

**Files:** Create `apps/api/app/services/agent_tasks.py`, `apps/api/app/api/agent_tasks.py`; Modify `apps/api/app/main.py:66`;
Create `apps/api/tests/agn016_helpers.py`, `apps/api/tests/test_agn_016_create_read.py`.

**Consumes:** `student_scope`, `load_scoped` (students), `application_scope`, `_gate`, `_locked_row`, `lock_active_org`.
**Produces:** `task_scope(user) -> list[ColumnElement]`, `load_scoped_task(db, user, task_id, *, lock=False) -> AgentTask`,
`task_detail(db, task, now) -> dict`, `check_application(db, user, student, application_id)`, `ensure_capacity(db, student_id)`,
helpers `mk_task(db, *, record, author, title=..., due_at=..., status="open", application=None)`, `TASKS` URL.

- [ ] RED: AC01 (Master/no-login, Staff/linked → 201, audit row, no title in metadata); AC02 create/read IDOR (unassigned,
  other agency, other staff → 404; non-agent, super_admin → 403); AC07 (other student's / other agency's / withdrawn / bridged
  application → 422); AC06 create on archived → 409; AC13 cap → 409.
- [ ] GREEN, run, refactor, commit `feat(agn-016): create and read tasks`.

### Task 4: List and overdue

**Files:** Modify service + router; Test `apps/api/tests/test_agn_016_list.py`.

**Produces:** `list_page(db, user, *, view, student, limit, offset, now) -> dict`.

- [ ] RED: views open/overdue/done/cancelled/all with exact ids and order (Review Focus 5); AC04 boundary (due 1 s before vs
  after now); archived student's open task excluded from open/overdue but shown with `student=`; Staff list = own students only;
  out-of-scope `student` → empty page; `limit`/`offset` bounds → 422.
- [ ] GREEN, run, commit `feat(agn-016): task list and overdue`.

### Task 5: Edit and close

**Files:** Modify service + router; Test `apps/api/tests/test_agn_016_update.py`, `apps/api/tests/test_agn_016_concurrency.py`.

- [ ] RED: AC05 edits (field names audited; no-op → no audit; notes null clears — Review Focus 4); close done/cancelled stamps
  `closed_at`/`closed_by`, audits `task_complete`/`task_cancel`; write to closed → 409; archived → 409; application relink rules;
  AC09 two concurrent completes → 200 + 409 (forced interleaving, AGN-008 concurrency idiom); AC03 + Review Focus 1: reassigned
  student → old Staff 404 on GET/PATCH, new Staff 200, task row unchanged.
- [ ] GREEN, run, commit `feat(agn-016): edit, complete and cancel tasks`.

### Task 6: Dashboard KPI and staff activity

**Files:** Modify `apps/api/app/services/portal.py` (`_agent` dashboard; `tasks` header section), `apps/api/app/services/staff_activity.py`;
Test `apps/api/tests/test_agn_016_dashboard.py`.

- [ ] RED: AC10 Master and Staff "Pending actions" counts (archived and closed excluded), "Students"/"Applications" unchanged and
  "Pending actions" right after "Applications"; `GET /portal/overseas/agent/tasks` → 200 header payload; AC11 AGN-021 activity
  lists `agent_student.task_add` for the staff member.
- [ ] GREEN, run with the four existing lite files, commit `feat(agn-016): pending actions KPI and activity`.

### Task 7: Frontend

**Files:** Create `apps/web/lib/agentTasks.ts`, `apps/web/components/AgentTasksSection.tsx`, `AgentTasksPanel.tsx`,
`AgentTaskCard.tsx`, `AgentTaskForm.tsx`; Modify `apps/web/lib/navigation.ts:81`, `apps/web/components/PortalPage.tsx`,
`apps/web/components/AgentStudentDetailPanel.tsx`, `apps/web/components/AgentApplicationCreatePanel.tsx` (import
`searchStudents`), `apps/web/lib/agentStudents.ts`, `apps/web/lib/agentStaff.ts` (activity labels).

**Produces:** `TASKS_URL`, `TASK_VIEWS`, `parseView`, `VIEW_LABELS`, `EMPTY_TEXT`, `type AgentTask`, `toIsoWithOffset(local: string)`,
`isPast(local: string, now: Date)`.

- [ ] Write `apps/web/tests/e2e/agn-016-tasks.spec.ts` (AC12): Master creates a task for a student; Staff sees it in Tasks and
  marks it done; an overdue task shows the "Overdue" text; keyboard-only create; 320 px viewport has no horizontal scroll.
- [ ] Implement; run `npx tsc --noEmit` and `npx eslint` on changed files → clean. Commit `feat(agn-016): tasks UI`.

### Task 8: Documentation

**Files:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-053`), `docs/delivery/ENHANCEMENT_BACKLOG.md` (AGN-016
row + section, status IN PROGRESS — not COMPLETE until browser QA and Codex review), `docs/quality/RTM.md`,
`docs/architecture/API_CONTRACT.md` (wherever AGN-008 is recorded).

- [ ] Write entries; commit `docs(agn-016): decision, backlog, RTM, API contract`.
