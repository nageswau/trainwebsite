# AGN-008 Agent Applications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An agency's Masters and their assigned Staff can create, edit, view and move forward or withdraw overseas applications for agent students, with or without a login. Each application records an Application ID, a submission date and two deadlines. The sidebar has status filters, and every shared application list shows these applications with the right owner.

**Architecture:**
- **Migration.** One additive migration (`0057_agent_applications`) adds a nullable `overseas_applications.agent_student_id` bridge and three dates.
- **Service.** A new `services/agent_applications.py` owns:
  - the stage rules, status groups, owner join, duplicate check and throttle
  - `with_owner()` / `owned()`, the NULL-safe owner join that the shared lists switch to
- **Router.** A new `api/agent_applications.py` serves `/workflows/overseas/agent/crm/applications`, next to AGN-004's `crm/students`, using the same gate, org lock, 404 masking and same-transaction audit.
- **Web.** The web gets a Section, a Panel, Detail/Edit/Status components, the reused Create panel, and sidebar sub-links.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL, Pydantic 2, pytest + pytest-asyncio + httpx; Next.js 15 (App Router), React, TypeScript, vitest + Testing Library, Playwright. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-02-agn-008-agent-applications-design.md` (revision 2, plus the Task 0 amendments). Read it with this plan.

## Global Constraints

**Identifiers and numbering**
- Branch `feature/agn-008-agent-applications`, from `main` at `41fba25`. Recheck `origin/main` before Task 1 and before Task 9; renumber on a collision.
- Decision ID `DEC-SCOPE-050` (provisional). Migration revision `0057_agent_applications`, `down_revision = "0054_school_onboarding_bulk"`.
- Router prefix `/workflows/overseas/agent/crm/applications`, tag `agent-applications`, logger `app.agent_applications`.

**Authorization**
- Use the inline pattern: `agent_students._gate`, then `student_scope` / `application_scope` in the WHERE clause. Never use `require_role` / `require_permission`.
- `super_admin` is refused (403).

**Errors**
- Format: FastAPI `{"detail": ...}`.
- Order of checks: gate 403 → throttle 429 → scope 404 → archived 409 → withdrawn 409 → stale 409 → role 403 → validation 422 → duplicate 409.
- Error strings, used exactly:

| Constant | Message |
|---|---|
| `NOT_FOUND` | `"Application not found"` |
| `ARCHIVED` | `"Unarchive this student first"` |
| `WITHDRAWN_REFUSED` | `"This application is withdrawn"` |
| `STALE` | `"This application changed since you opened it -- reload to see its current status"` |
| `ENROLLED_REFUSED` | `"Only a counselor, university representative or admin can mark an application enrolled"` |
| `ENROLLED_NOT_WITHDRAWABLE` | `"An enrolled application cannot be withdrawn"` |
| `DUPLICATE` | `"An application for this university/course already exists"` |
| `THROTTLED` | `"Too many applications created today -- try again later"` |
| Course mismatch | `"Course does not belong to selected university"` |
| Missing university | `"University not found"` |

**Transactions and logging**
- Every write follows one order: lock the organisation (`lock_active_org`), then the application row `FOR UPDATE`, then write the history row, the audit row in the same transaction, one commit, then the structured log.
- Audit metadata carries ids, field names and from/to status only; never notes, next-action text, references or names.

**Data and limits**
- Statuses: `OVERSEAS_APPLICATION_STAGES` (7 stages) plus `"withdrawn"`. `AGENT_MAX_STAGE = "status_tracking"`. `CREATE_LIMIT = 200` per agency per rolling 24 hours.
- Dates must fall between `2000-01-01` and `2100-12-31`. `submitted_on` may be at most the UTC date plus one day.
- Lengths: `intake` 1–80 · `application_reference` ≤ 140 · `next_action` ≤ 500 · `notes` ≤ 2000. Text is trimmed and control/bidi characters are refused (`clean_free_text`).

**Process**
- Existing tests are edited only where the requirement changes them. Each such edit is listed in its task:
  - `test_agn_003_matrix.py`
  - `test_agn_021_activity.py`
  - `Enh031ExistingPickers.test.tsx`
- Tests are run for real. Outcomes come from exit codes and output, never from reasoning. Per task, run the lite set only (the owner runs the full backend suite).
- No new dependency. `npm ci` installs the existing lockfile only.
- No completion claim. Browser validation and the independent Codex review are the owner's.

## Test commands (used by every task)

**Setup (owner).** The owner manages Docker. Before Task 1, the owner:
1. Copies `.env` from the main checkout into this worktree.
2. Starts the isolated test databases:

```bash
docker compose -p agn008 -f docker-compose.yml -f docker-compose.ci.yml up -d postgres redis
```

**`API_TEST <paths>`** runs the API tests in a one-off container. Use the Windows-form absolute mount path; `$PWD` mounts a stale tree in Git Bash:

```bash
docker compose -p agn008 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/agn-008/apps/api:/app" \
  api-test sh -c "alembic upgrade head && python -m pytest -q <paths>"
```

If `alembic upgrade head` fails on an unknown stamped revision, run `alembic stamp --purge 0054_school_onboarding_bulk` first.

**`WEB_TEST <paths>`** runs on the host after a one-time `cd apps/web && npm ci`:

```bash
cd apps/web && npx vitest run <paths>
```

## Review Focus

1. **A no-login student's application on screens that read `student.id`.** For example, the agent roster's `latest_application_by_student` map, or appointment lookups by `student_id`. Expected: those rows are skipped there, not crashed on. Pinned in Task 3 (`test_agent_portal_pages_render_with_a_no_login_application`).
2. **A School-bridged application next to agent ones.** It must stay out of every list it is out of today, while agent no-login rows appear. Pinned in Task 2 (`test_school_bridged_rows_stay_out_of_the_lists`) and Task 3.
3. **An application made before AGN-008 for a linked student** (`agent_student_id` NULL). It must still count for duplicates, be editable and movable, honour the archived rule through the linked record, and match the `student` filter. Pinned in Task 6 (`test_legacy_linked_application_is_a_duplicate`) and Task 7 (`test_legacy_application_follows_the_archived_record`).
4. **Two tabs: one withdraws while the other still shows the old status and moves it forward.** Expected: 409 stale, nothing written. Pinned in Task 7 (`test_stale_expected_status_is_refused`).
5. **A notification or commit failure mid-create.** Expected: nothing persists (no application, history or audit row). Pinned in Task 6 (`test_a_failure_before_commit_leaves_nothing`).

---

## File Structure

**Backend — create**
- `apps/api/alembic/versions/0057_agent_applications.py`: four nullable columns plus an index; guarded upgrade; the downgrade refuses to drop AGN-008 data.
- `apps/api/app/services/agent_applications.py`:
  - stage constants, `Owner` / `with_owner` / `owned`, status groups
  - serialisers, `load_scoped`, `owner_record`, `duplicate_exists`, `check_course`, `check_transition`, `create_wait_seconds`, `list_page`, `detail`
- `apps/api/app/api/agent_applications.py`: the router.
- `apps/api/tests/agn008_helpers.py`: `APPS`, `mk_application`, `agency_world`.
- Test files:
  - `apps/api/tests/test_agn_008_migration.py`
  - `test_agn_008_null_owner.py`
  - `test_agn_008_schemas.py`
  - `test_agn_008_read.py`
  - `test_agn_008_create.py`
  - `test_agn_008_edit.py`
  - `test_agn_008_status.py`
  - `test_agn_008_security.py`

**Backend — modify**
- `apps/api/app/models.py`: `OverseasApplication` gains four columns; the stale comment is fixed.
- `apps/api/app/services/agent_orgs.py`: extract `retry_after()` from `_wait_seconds` (no behaviour change).
- `apps/api/app/services/agent_students.py`: the staff clause of `application_scope` gains `agent_student_id`.
- `apps/api/app/api/workflows.py`:
  - import the stages and default next action from the service
  - `list_overseas_applications` and `agent_commissions` use `with_owner`
  - withdrawn guard on PATCH and `/advance`
- `apps/api/app/api/admin.py`: `/admin/applications` uses `with_owner`.
- `apps/api/app/services/portal.py`: `_agent`, the counselor/rep/admin block, visa, visa aging and admin commissions use `with_owner`.
- `apps/api/app/api/lookups.py`: `AgentStudent.full_name` joins the coalesce.
- `apps/api/app/api/inbound.py`: guard `_notify_student`.
- `apps/api/app/services/staff_activity.py`: AgentStudent name for application subjects; three new actions.
- `apps/api/app/schemas.py`: `AgentApplicationCreate`, `AgentApplicationUpdate`, `AgentApplicationStatus`.
- `apps/api/app/main.py`: register the router.
- `apps/api/tests/test_agn_003_matrix.py`: Edit Application and Change Application Status become enforced rows.
- `apps/api/tests/test_agn_021_activity.py`: the new actions.

**Web — create**
- `apps/web/lib/agentApplications.ts`
- Components:
  - `apps/web/components/AgentApplicationsSection.tsx`
  - `AgentApplicationsPanel.tsx`
  - `AgentApplicationDetail.tsx`
  - `AgentApplicationEditForm.tsx`
  - `AgentApplicationStatusForm.tsx`
  - `NavGroup.tsx`
- Tests:
  - `apps/web/tests/lib/agentApplications.test.ts`
  - `apps/web/tests/components/AgentApplicationsPanel.test.tsx`
  - `AgentApplicationDetail.test.tsx`
  - `AgentApplicationCreatePanel.test.tsx`
  - `PortalShell.children.test.tsx`
- `apps/web/tests/e2e/agn-008-agent-applications.spec.ts`

**Web — modify**
- `apps/web/components/AgentApplicationCreatePanel.tsx`: CRM students (server search), new fields, the new route, `onCreated`.
- `apps/web/components/PortalShell.tsx`: render `children` via `NavGroup`; flatten for mobile.
- `apps/web/components/PortalPage.tsx`: the `applications` branch.
- `apps/web/components/WorkflowPanel.tsx`: stop mounting the create panel.
- `apps/web/lib/navigation.ts`: Applications `children`.
- `apps/web/lib/agentStaff.ts`: three activity labels.
- `apps/web/app/globals.css`: `.portal-subnav`.
- `apps/web/tests/components/Enh031ExistingPickers.test.tsx`: the new student source.
- `apps/web/tests/lib/navigation.agent.test.ts`: the children assertion (existing assertions unchanged).

**Docs — modify (Task 0, Task 15):** spec amendments, then the §11 documentation set.

---

### Task 0: Spec amendments found while planning

**Files:**
- Modify: `docs/superpowers/specs/2026-10-02-agn-008-agent-applications-design.md`

- [ ] **Step 1: Apply the six amendments, each marked "(plan, 2026-10-02)"**

  - §5.3 status-change rules: replace "call `_maybe_trigger_agent_commission` … (a no-op …)" with "no commission call: an agent can never reach `enrolled`, and AC05 asserts no commission row".
  - §6.2 and §6.6: replace the side-by-side detail layout with "the detail expands under its card, at every width (an `aria-expanded` View/Close button)". Replace "`status`, `offset`" URL state with "`status` only (paging is local and resets on a filter change)".
  - §6.2: replace "Withdrawn and enrolled applications are read-only" with "A withdrawn application, or one whose student is archived, is read-only (`read_only_reason`). An enrolled application keeps Edit but shows no status control."
  - §6.3: replace the option text rule with "`<name> — <email>` when the student has a login, `<name> — no login` otherwise". The picker uses SearchableSelect **server mode** against `RECORDS_URL?q=&limit=20`, so agencies with more than 100 students still work.
  - §6.5: change the labels to "Edited an application", "Moved an application forward" and "Withdrew an application" (the existing "Created an application" style).
  - §5.3 GET `/{id}`: detail also returns `university_slug` (the edit form's course list) and `read_only_reason` (`"withdrawn" | "archived" | null`).

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-10-02-agn-008-agent-applications-design.md
git commit -m "docs(agn-008): spec amendments found while planning"
```

---

### Task 1: Migration `0057_agent_applications` and model columns

**Files:**
- Create: `apps/api/alembic/versions/0057_agent_applications.py`
- Modify: `apps/api/app/models.py` (`OverseasApplication`, ~L424-446)
- Test: `apps/api/tests/test_agn_008_migration.py`

**Interfaces:**
- Produces: `OverseasApplication.agent_student_id: UUID | None`, `.submitted_on`, `.application_deadline`, `.offer_deadline: date | None`. Migration module constants `TABLE`, `INDEX`, `DATES`.

- [ ] **Step 1: Write the failing test**

```python
"""AGN-008 -- migration 0057_agent_applications (spec §4). Round trip and downgrade refusals run in a throwaway database built from
scratch (the AGN-004 / ENH-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls
asyncio.run() itself."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_008_migration_0057", VERSIONS / "0057_agent_applications.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0054_school_onboarding_bulk"
APP_COLUMNS = "SELECT id, student_id, university_id, status, intake, agent_id FROM overseas_applications ORDER BY id"
NEW = ("agent_student_id", *_migration.DATES)


def test_migration_chains_after_0054_and_is_the_single_head():
    assert _migration.revision == "0057_agent_applications"
    assert _migration.down_revision == BASE
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    heads = set(parents) - set(parents.values())
    assert len(heads) == 1


def test_model_declares_the_new_columns_nullable():
    from app.models import OverseasApplication

    columns = OverseasApplication.__table__.columns
    for name in NEW:
        assert name in columns and columns[name].nullable, name
    assert columns["agent_student_id"].index


@pytest.mark.asyncio
async def test_new_columns_and_index_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    cols = await conn.run_sync(lambda sync: {c["name"]: c for c in inspect(sync).get_columns("overseas_applications")})
    indexes = await conn.run_sync(lambda sync: {i["name"] for i in inspect(sync).get_indexes("overseas_applications")})
    for name in NEW:
        assert name in cols and cols[name]["nullable"], name
    assert _migration.INDEX in indexes


def _sql(url: str, sql: str, params: dict | None = None, *, autocommit: bool = False):
    async def _inner():
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT") if autocommit else create_async_engine(url)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(sa.text(sql), params or {})
                return result.fetchall() if result.returns_rows else None
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


@pytest.fixture
def isolated_db():
    """A fresh database at 0054 with one agency student and one application for a student with an account."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"agn008_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("agent", "student", "country", "university", "application", "record")}
        for key, role in (("agent", "agent"), ("student", "overseas_student")):
            _sql(
                url,
                "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
                "VALUES (:id, :email, 'x', :name, :role, 'overseas', true, true, 'en-GB', '{}')",
                {"id": ids[key], "email": f"{key}-{name}@example.local", "name": f"{key} user", "role": role},
            )
        _sql(
            url,
            "INSERT INTO countries (id, slug, name, overview, tuition, living_expenses, visa_process, work_opportunities, post_study_work, pr_opportunities, faq) "
            "VALUES (:id, :slug, 'Testland', '', '', '', '[]', '', '', '', '[]')",
            {"id": ids["country"], "slug": f"c-{name}"},
        )
        _sql(
            url,
            "INSERT INTO universities (id, country_id, slug, name, city, overview, eligibility, requirements, deadlines, scholarships) "
            "VALUES (:id, :country, :slug, 'Mig University', 'Town', '', '', '[]', '[]', '[]')",
            {"id": ids["university"], "country": ids["country"], "slug": f"u-{name}"},
        )
        _sql(
            url,
            "INSERT INTO overseas_applications (id, student_id, university_id, agent_id, status, intake) VALUES (:id, :student, :university, :agent, 'enquiry', 'Fall 2027')",
            {"id": ids["application"], "student": ids["student"], "university": ids["university"], "agent": ids["agent"]},
        )
        _sql(url, "INSERT INTO agent_students (id, agent_id, student_id, status, full_name) VALUES (:id, :agent, NULL, 'active', 'No Login')", {"id": ids["record"], "agent": ids["agent"]})
        yield {"cfg": cfg, "url": url, "ids": ids}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_existing_rows_identical(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, APP_COLUMNS)
    command.upgrade(cfg, "0057_agent_applications")
    assert _sql(url, APP_COLUMNS) == before
    assert _sql(url, "SELECT agent_student_id, submitted_on, application_deadline, offer_deadline FROM overseas_applications") == [(None, None, None, None)]
    command.downgrade(cfg, BASE)
    assert _sql(url, APP_COLUMNS) == before
    command.upgrade(cfg, "0057_agent_applications")
    assert _sql(url, APP_COLUMNS) == before


@pytest.mark.parametrize(
    ("setup_sql", "message"),
    [
        ("UPDATE overseas_applications SET agent_student_id = :record", "applications of agency students exist"),
        ("UPDATE overseas_applications SET submitted_on = DATE '2026-09-01'", "application dates exist"),
        ("UPDATE overseas_applications SET offer_deadline = DATE '2026-12-01'", "application dates exist"),
    ],
)
def test_downgrade_refuses_to_lose_agn008_data(isolated_db, setup_sql, message):
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, "0057_agent_applications")
    _sql(url, setup_sql, {"record": ids["record"]})
    with pytest.raises(RuntimeError, match=message):
        command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT version_num FROM alembic_version") == [("0057_agent_applications",)]
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `API_TEST tests/test_agn_008_migration.py`
Expected: FAIL. Collection error: `FileNotFoundError … 0057_agent_applications.py`.

- [ ] **Step 3: Write the migration**

```python
"""AGN-008 -- overseas_applications.agent_student_id + submitted_on, application_deadline, offer_deadline.

Revision ID: 0057_agent_applications
Revises: 0054_school_onboarding_bulk

docs/superpowers/specs/2026-10-02-agn-008-agent-applications-design.md §4 (DEC-SCOPE-050, provisional). Four nullable columns and one
index; no existing row is read or written. `withdrawn` needs no DDL (status is String(50)). 0001 builds a fresh database from the
current models, which already carry these columns, so every add is guarded (0054's idiom). downgrade() refuses while AGN-008 data
exists rather than silently dropping it: an application of a student with no login would lose its only owner. Provisional number:
AGN-006 holds 0055 and AGN-007 0056 on unmerged branches -- re-chain on merge.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0057_agent_applications"
down_revision = "0054_school_onboarding_bulk"
branch_labels = None
depends_on = None

TABLE = "overseas_applications"
INDEX = "ix_overseas_applications_agent_student_id"
DATES = ("submitted_on", "application_deadline", "offer_deadline")


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    existing = set() if inspector is None else {c["name"] for c in inspector.get_columns(TABLE)}
    if "agent_student_id" not in existing:
        op.add_column(TABLE, sa.Column("agent_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_students.id"), nullable=True))
    for name in DATES:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, sa.Date(), nullable=True))
    indexes = set() if inspector is None else {i["name"] for i in inspector.get_indexes(TABLE)}
    if INDEX not in indexes:
        op.create_index(INDEX, TABLE, ["agent_student_id"])


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        if bind.execute(sa.text(f"SELECT count(*) FROM {TABLE} WHERE agent_student_id IS NOT NULL")).scalar():
            raise RuntimeError("Refusing to downgrade 0057_agent_applications: applications of agency students exist")
        dated = " OR ".join(f"{name} IS NOT NULL" for name in DATES)
        if bind.execute(sa.text(f"SELECT count(*) FROM {TABLE} WHERE {dated}")).scalar():
            raise RuntimeError("Refusing to downgrade 0057_agent_applications: application dates exist")
    op.drop_index(INDEX, table_name=TABLE)
    for name in reversed(DATES):
        op.drop_column(TABLE, name)
    op.drop_column(TABLE, "agent_student_id")
```

- [ ] **Step 4: Add the model columns**

In `apps/api/app/models.py`, edit `OverseasApplication`. Replace the comment block above `student_id` (lines ~427-434) with:

```python
    # Owner (DEC-SCOPE-018, AGN-008 DEC-SCOPE-050). Exactly one of `school_student_id` or the agent pair is set, enforced at every
    # write site (app-level, this table's style). A School-bridged row has `school_student_id` only. An agency's application has
    # `agent_student_id` (its record, AGN-004), plus `student_id` when that student has a login. Rows made before AGN-008 have
    # `student_id` only. Shared lists join the owner with `services.agent_applications.with_owner` (outer joins), so a student with
    # no login is listed rather than dropped; School-bridged rows stay out of them, as before.
```

After `offer_letter_url`, add:

```python
    agent_student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_students.id"), nullable=True, index=True)
    submitted_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    application_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    offer_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `API_TEST tests/test_agn_008_migration.py tests/test_agn_004_migration.py`
Expected: PASS, with 0 failures.

- [ ] **Step 6: Refactor check**

Read the diff. Nothing else changed in `models.py`.

- [ ] **Step 7: Commit**

```bash
git add apps/api/alembic/versions/0057_agent_applications.py apps/api/app/models.py apps/api/tests/test_agn_008_migration.py
git commit -m "feat(agn-008): migration 0057 -- agent_student_id bridge and application dates"
```

---

### Task 2: Owner join, scope, and the workflows/admin lists

**Files:**
- Create: `apps/api/app/services/agent_applications.py` (first part)
- Create: `apps/api/tests/agn008_helpers.py`
- Modify: `apps/api/app/services/agent_students.py:36-41`
- Modify: `apps/api/app/api/workflows.py`
  - imports
  - L1722 (stages)
  - L1799 (default next action)
  - L1842-1872 (list)
  - L2368-2397 (agent commissions)
- Modify: `apps/api/app/api/admin.py:306-326`
- Test: `apps/api/tests/test_agn_008_null_owner.py` (first part)

**Interfaces:**
- Produces (service):
  - `OVERSEAS_APPLICATION_STAGES: list[str]`, `WITHDRAWN = "withdrawn"`, `AGENT_MAX_STAGE = "status_tracking"`, `DEFAULT_NEXT_ACTION: str`
  - `class Owner(NamedTuple): id: UUID | None; full_name: str | None`
  - `with_owner(stmt: Select) -> Select`
  - `owned(rows) -> list[tuple]`
- Produces (helpers):
  - `APPS = "/api/v1/workflows/overseas/agent/crm/applications"`
  - `async mk_application(db, *, agent, university, record=None, student=None, status="enquiry", course_id=None, school_student=None, **fields) -> OverseasApplication`
  - `async agency_world(db) -> dict` with keys `master, member, org, staff, other_staff, other, record, linked_record, linked_user, university, school_student`

- [ ] **Step 1: Write the helpers**

`apps/api/tests/agn008_helpers.py`:

```python
"""AGN-008 test helpers: an agency with staff, a student with no login, a linked student, a university, and applications built
directly (the API under test builds them in the feature tests)."""

from app.models import AgentStudent, OverseasApplication, SchoolStudent
from tests.agn001_helpers import mk_active_org, mk_user, uniq
from tests.agn003_helpers import mk_university
from tests.agn004_helpers import mk_record, mk_staff
from tests.enh005_helpers import mk_school

APPS = "/api/v1/workflows/overseas/agent/crm/applications"


async def mk_application(db, *, agent, university, record: AgentStudent | None = None, student=None, status: str = "enquiry", course_id=None, school_student=None, **fields) -> OverseasApplication:
    """`record` -> an AGN-008 row (agent_student_id, plus student_id when the record has a login); `student` alone -> a row made
    before AGN-008; `school_student` -> a School-bridged row (DEC-SCOPE-018)."""
    row = OverseasApplication(
        agent_id=agent.id if agent else None,
        agent_student_id=record.id if record else None,
        student_id=(record.student_id if record else None) or (student.id if student else None),
        school_student_id=school_student.id if school_student else None,
        university_id=university.id,
        course_id=course_id,
        status=status,
        intake=fields.pop("intake", "Fall 2027"),
        **fields,
    )
    db.add(row)
    await db.commit()
    return row


async def mk_school_student(db) -> SchoolStudent:
    """A School-affiliated student (no login) for a DEC-SCOPE-018 bridged row -- ENH-005's school builder."""
    return (await mk_school(db, students=1, with_teacher=False))["students"][0]


async def agency_world(db) -> dict:
    ctx = await mk_active_org(db, name=f"Apps {uniq()}")
    other = await mk_active_org(db, name=f"Other {uniq()}")
    staff = await mk_staff(db, ctx["org"], full_name="Apps Staff")
    other_staff = await mk_staff(db, ctx["org"], full_name="Apps Other Staff")
    record = await mk_record(db, agent=ctx["master"], full_name=f"No Login {uniq()}", assigned_member=staff["member"])
    linked_user = await mk_user(db, role="overseas_student", full_name=f"Linked {uniq()}")
    linked_record = AgentStudent(agent_id=ctx["master"].id, student_id=linked_user.id, status="active", assigned_member_id=staff["member"].id)
    db.add(linked_record)
    await db.commit()
    university = await mk_university(db)
    return ctx | {"staff": staff, "other_staff": other_staff, "other": other, "record": record, "linked_record": linked_record, "linked_user": linked_user, "university": university}
```

- [ ] **Step 2: Write the failing tests**

`apps/api/tests/test_agn_008_null_owner.py`:

```python
"""AGN-008 AC08/AC09 -- applications of students with no login appear, with their owner, in every shared list; School-bridged rows
stay out exactly where they were out before (spec §5.6, A6, A12)."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for, mk_user
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import agency_world, mk_application, mk_school_student


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["no_login_app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    w["linked_app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["linked_record"])
    w["school_app"] = await mk_application(db_session, agent=None, university=w["university"], school_student=await mk_school_student(db_session))
    w["rep"] = await mk_user(db_session, role="university_rep", full_name="Rep", profile={"university_id": str(w["university"].id)})
    w["admin"] = await mk_user(db_session, role="overseas_admin", full_name="Admin")
    return w


def _by_id(rows, key="id"):
    return {str(r[key]): r for r in rows}


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["rep", "admin", "master"])
async def test_workflows_list_shows_the_no_login_owner(world, who):
    user = world[who]
    async with client_for(user.email) as c:
        response = await c.get("/api/v1/workflows/overseas/applications")
    assert response.status_code == 200, response.text
    rows = _by_id(response.json())
    no_login = rows[str(world["no_login_app"].id)]
    assert no_login["student"] == world["record"].full_name and no_login["student_id"] is None
    assert rows[str(world["linked_app"].id)]["student"] == world["linked_user"].full_name
    assert str(world["school_app"].id) not in rows


@pytest.mark.asyncio
async def test_admin_applications_shows_the_no_login_owner(world):
    async with client_for(world["admin"].email) as c:
        response = await c.get("/api/v1/admin/applications")
    assert response.status_code == 200, response.text
    rows = _by_id(response.json())
    assert rows[str(world["no_login_app"].id)]["student"] == world["record"].full_name
    assert str(world["school_app"].id) not in rows


@pytest.mark.asyncio
async def test_staff_see_their_assigned_no_login_application_and_not_others(db_session, world):
    unassigned = await mk_application(db_session, agent=world["master"], university=world["university"], record=await mk_record(db_session, agent=world["master"], full_name="Unassigned"))
    async with client_for(world["staff"]["user"].email) as c:
        rows = _by_id((await c.get("/api/v1/workflows/overseas/applications")).json())
    assert str(world["no_login_app"].id) in rows and str(world["linked_app"].id) in rows
    assert str(unassigned.id) not in rows
    async with client_for(world["other_staff"]["user"].email) as c:
        rows = _by_id((await c.get("/api/v1/workflows/overseas/applications")).json())
    assert str(world["no_login_app"].id) not in rows


@pytest.mark.asyncio
async def test_school_bridged_rows_stay_out_of_the_lists(world):
    for who in ("admin", "rep"):
        async with client_for(world[who].email) as c:
            ids = {str(r["id"]) for r in (await c.get("/api/v1/workflows/overseas/applications")).json()}
        assert str(world["school_app"].id) not in ids
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `API_TEST tests/test_agn_008_null_owner.py`
Expected: FAIL. The `no_login_app` id is missing from the rows (`KeyError`) because the inner join on users drops it, and the staff test fails on `no_login_app` not in rows.

- [ ] **Step 4: Write the service, first part**

`apps/api/app/services/agent_applications.py`:

```python
"""AGN-008 / DEC-SCOPE-050 -- an agency's applications for its students, with or without a login; and the NULL-safe owner join
every shared application list uses.

Functions only (the services/agent_students.py shape): nothing here commits -- the router locks, writes, audits and commits.
Spec: docs/superpowers/specs/2026-10-02-agn-008-agent-applications-design.md.
"""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import Select, func

from app.models import AgentStudent, OverseasApplication, User

# DEC-WF-001 / OVS-003: the confirmed stage sequence (moved here from api/workflows.py, which imports it back -- one definition).
OVERSEAS_APPLICATION_STAGES = ["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled"]
WITHDRAWN = "withdrawn"  # A1: terminal; only an agent sets it (spec §5.3)
AGENT_MAX_STAGE = "status_tracking"  # A4: `enrolled` stays with counselor, university and admin
DEFAULT_NEXT_ACTION = "Complete profile and required document checklist"


class Owner(NamedTuple):
    """An application's student: `id` is their account (None when the student has no login); `full_name` is the account's name,
    else the agency record's."""

    id: UUID | None
    full_name: str | None


OWNER_NAME = func.coalesce(User.full_name, AgentStudent.full_name)


def with_owner(stmt: Select) -> Select:
    """Add the owner (account row + display name) to a query over overseas_applications as OUTER joins, so an application of a
    student with no login is listed instead of silently dropped (A6). School-bridged rows stay out, exactly as the old inner join on
    users left them out (A12)."""
    return (
        stmt.add_columns(User, OWNER_NAME)
        .outerjoin(User, User.id == OverseasApplication.student_id)
        .outerjoin(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)
        .where(OverseasApplication.school_student_id.is_(None))
    )


def owned(rows) -> list[tuple]:
    """`with_owner` rows with the trailing (account, name) pair folded into one `Owner`, so `for a, u, s in rows: s.full_name`
    keeps working; `s.id` is None for a student with no login."""
    return [(*row[:-2], Owner(row[-2].id if row[-2] is not None else None, row[-1])) for row in rows]
```

- [ ] **Step 5: Widen staff scope**

In `apps/api/app/services/agent_students.py`, replace `application_scope`:

```python
def application_scope(user: User) -> list[ColumnElement]:
    """The organisation's applications; a staff member only those of their assigned students (G4) -- by the student's account, or,
    for a student with no login, by the agency record the application belongs to (AGN-008)."""
    clauses = [OverseasApplication.agent_id.in_(org_member_ids(user))]
    if is_agent_staff(user):
        clauses.append(
            or_(
                OverseasApplication.student_id.in_(visible_student_user_ids(user)),
                OverseasApplication.agent_student_id.in_(select(AgentStudent.id).where(*student_scope(user))),
            )
        )
    return clauses
```

- [ ] **Step 6: Switch the workflows and admin lists**

In `apps/api/app/api/workflows.py`:
- Delete the `OVERSEAS_APPLICATION_STAGES = [...]` line (L1722). Keep the comment above it.
- Add to the imports: `from app.services.agent_applications import DEFAULT_NEXT_ACTION, OVERSEAS_APPLICATION_STAGES, WITHDRAWN, owned, with_owner`.
- In `create_overseas_application`, replace the literal next action with `DEFAULT_NEXT_ACTION`.
- In `list_overseas_applications`, replace the statement and the row loop:

```python
    stmt = with_owner(select(OverseasApplication, University).join(University))
    ...
    rows = owned((await db.execute(stmt.order_by(OverseasApplication.updated_at.desc()).limit(500))).all())
```

  Keep the row dict as it is. `student.id` and `student.full_name` now read the `Owner` (`id` may be `None`).
- In `agent_commissions`, replace `select(AgentCommission, OverseasApplication, University, User) ... .join(User, User.id == OverseasApplication.student_id)` with:

```python
    rows = owned(
        (
            await db.execute(
                with_owner(
                    select(AgentCommission, OverseasApplication, University)
                    .select_from(AgentCommission)
                    .join(OverseasApplication, OverseasApplication.id == AgentCommission.application_id)
                    .join(University, University.id == OverseasApplication.university_id)
                )
                .where(AgentCommission.agent_id.in_(org_member_ids(user)))
                .order_by(AgentCommission.created_at.desc())
            )
        ).all()
    )
```

In `apps/api/app/api/admin.py` `applications`:

```python
        rows = owned(
            (
                await db.execute(
                    with_owner(select(OverseasApplication, University).join(University, University.id == OverseasApplication.university_id))
                    .order_by(OverseasApplication.updated_at.desc())
                    .limit(500)
                )
            ).all()
        )
```

Then add `from app.services.agent_applications import owned, with_owner`. The dict comprehension is unchanged (`student.full_name`).

Also run `grep -rn "workflows import OVERSEAS_APPLICATION_STAGES\|OVERSEAS_APPLICATION_STAGES" apps/api`. Every importer must still resolve: `workflows.OVERSEAS_APPLICATION_STAGES` stays importable through the new import.

- [ ] **Step 7: Run the tests and confirm they pass**

Run: `API_TEST tests/test_agn_008_null_owner.py tests/test_agn_004_staff_scope.py tests/test_ovs_002_application.py tests/test_ovs_003_eligibility.py tests/test_uni_001_university_rep_portal.py tests/test_agt_003_commission_accrual.py tests/test_agt_004_commission_payout.py tests/test_sch_010_overseas_bridge.py`
Expected: PASS.

- [ ] **Step 8: Refactor and re-run**

Check that no other `join(User, User.id == OverseasApplication.student_id)` remains in `workflows.py` or `admin.py`:
`grep -n "User.id == OverseasApplication.student_id" apps/api/app/api/workflows.py apps/api/app/api/admin.py`
Expected: none. Re-run Step 7.

- [ ] **Step 9: Commit**

```bash
git add apps/api/app/services/agent_applications.py apps/api/app/services/agent_students.py apps/api/app/api/workflows.py apps/api/app/api/admin.py apps/api/tests/agn008_helpers.py apps/api/tests/test_agn_008_null_owner.py
git commit -m "feat(agn-008): NULL-safe owner join; staff scope reaches no-login students' applications"
```

---

### Task 3: Portal, lookups, inbound and staff activity read the owner safely

**Files:**
- Modify: `apps/api/app/services/portal.py`
  - `_agent` L680-692
  - the counselor/rep/admin block L945
  - visa L1006-1013
  - reports visa aging L1139-1146
  - admin commissions L1418-1426
- Modify: `apps/api/app/api/lookups.py:152-160`
- Modify: `apps/api/app/api/inbound.py:69-72`
- Modify: `apps/api/app/services/staff_activity.py` (`_subjects`)
- Test: `apps/api/tests/test_agn_008_null_owner.py` (append)

**Interfaces:**
- Consumes: `with_owner`, `owned`, `Owner` (Task 2).

- [ ] **Step 1: Write the failing tests (append)**

```python
from sqlalchemy import select

from app.api import inbound
from app.models import AgentCommission, AuditLog, VisaCase
from app.services.staff_activity import _subjects

PORTAL = "/api/v1/portal/overseas"


@pytest.mark.asyncio
@pytest.mark.parametrize(("who", "path"), [
    ("master", "/agent/dashboard"), ("master", "/agent/students"), ("master", "/agent/applications"), ("master", "/agent/documents"),
    ("rep", "/university/dashboard"), ("rep", "/university/applications"), ("rep", "/university/offer-letters"),
    ("admin", "/admin/dashboard"), ("admin", "/admin/applications"), ("admin", "/admin/visa"), ("admin", "/admin/reports"),
    ("admin", "/admin/commissions"),
])
async def test_agent_portal_pages_render_with_a_no_login_application(db_session, world, who, path):
    db_session.add(VisaCase(application_id=world["no_login_app"].id, status="checklist"))
    db_session.add(AgentCommission(agent_id=world["master"].id, application_id=world["no_login_app"].id, amount=0, status="estimated"))
    await db_session.commit()
    async with client_for(world[who].email) as c:
        response = await c.get(PORTAL + path)
    assert response.status_code == 200, f"{path}: {response.text}"


@pytest.mark.asyncio
async def test_rep_and_admin_portal_rows_name_the_no_login_owner(world):
    for who, path in (("rep", "/university/applications"), ("admin", "/admin/applications")):
        async with client_for(world[who].email) as c:
            rows = (await c.get(PORTAL + path)).json()["rows"]
        names = {r.get("student") for r in rows}
        assert world["record"].full_name in names, path


@pytest.mark.asyncio
async def test_commission_lists_name_the_no_login_owner(db_session, world):
    db_session.add(AgentCommission(agent_id=world["master"].id, application_id=world["no_login_app"].id, amount=0, status="estimated"))
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        rows = (await c.get("/api/v1/workflows/overseas/agent/commissions")).json()
    assert world["record"].full_name in {r["student"] for r in rows}
    async with client_for(world["admin"].email) as c:
        rows = (await c.get(PORTAL + "/admin/commissions")).json()["rows"]
    assert world["record"].full_name in {r["student"] for r in rows}


@pytest.mark.asyncio
async def test_lookup_labels_the_no_login_owner(world):
    async with client_for(world["master"].email) as c:
        items = (await c.get("/api/v1/lookups/overseas-applications", params={"q": world["record"].full_name[:20]})).json()["items"]
    assert world["record"].full_name in {i["label"] for i in items}


@pytest.mark.asyncio
async def test_inbound_notify_skips_an_application_with_no_login(db_session, world):
    await inbound._notify_student(db_session, type("Email", (), {"subject": "x"})(), world["no_login_app"])  # must not raise


@pytest.mark.asyncio
async def test_staff_activity_subject_names_the_no_login_owner(db_session, world):
    row = AuditLog(user_id=world["staff"]["user"].id, action="overseas.application.create", entity_type="overseas_application", entity_id=str(world["no_login_app"].id))
    names = await _subjects(db_session, [row])
    assert names[("overseas_application", world["no_login_app"].id)].startswith(world["record"].full_name)
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `API_TEST tests/test_agn_008_null_owner.py`
Expected: FAIL. The names are missing from the rep/admin portal rows, commissions, lookup and activity, and the inbound test raises or warns (`db.get(User, None)`).

- [ ] **Step 3: Implement the portal changes**

All edits are in `apps/api/app/services/portal.py`. Add `from app.services.agent_applications import owned, with_owner`.

`_agent` applications query:

```python
    applications = owned(
        (
            await db.execute(
                with_owner(select(OverseasApplication, University).join(University, University.id == OverseasApplication.university_id))
                .where(*application_scope(user))
                .order_by(OverseasApplication.updated_at.desc())
            )
        ).all()
    )
```

Then the roster map, which only links students with a login:

```python
    for a, u, s in applications:
        if s.id is not None:
            latest_application_by_student.setdefault(s.id, (a, u))
```

Counselor/rep/admin block, L945:

```python
        stmt = with_owner(select(OverseasApplication, University).join(University, University.id == OverseasApplication.university_id))
        ...
        applications = owned((await db.execute(stmt.order_by(OverseasApplication.updated_at.desc()).limit(500))).all())
```

The `appointments` section: `student_ids = [a.student_id for a, _, _ in applications if a.student_id]`.

The visa section and the reports visa aging, each:

```python
                        with_owner(select(VisaCase, OverseasApplication).join(OverseasApplication, OverseasApplication.id == VisaCase.application_id))
                        .where(VisaCase.application_id.in_(app_ids))
```

Wrap the `execute(...).all()` in `owned(...)`; the aging query keeps its `.order_by(VisaCase.updated_at.asc())`.

Admin commissions:

```python
            rows = owned(
                (
                    await db.execute(
                        with_owner(
                            select(AgentCommission, University)
                            .join(OverseasApplication, OverseasApplication.id == AgentCommission.application_id)
                            .join(University, University.id == OverseasApplication.university_id)
                        ).order_by(AgentCommission.created_at.desc())
                    )
                ).all()
            )
```

- [ ] **Step 4: Implement the lookups, inbound and activity changes**

`apps/api/app/api/lookups.py`:
- `student_name = func.coalesce(User.full_name, AgentStudent.full_name, SchoolStudent.full_name)`
- Add `.outerjoin(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)` after the SchoolStudent outer join.
- Import `AgentStudent`.
- Update the docstring: "Agency students with no login (AGN-008) are labelled with the agency record's name."

`apps/api/app/api/inbound.py` `_notify_student`:

```python
async def _notify_student(db: AsyncSession, email: InboundUniversityEmail, application: OverseasApplication) -> None:
    # A School-bridged row or an agency student with no login has no account to notify (DEC-SCOPE-018, AGN-008); db.get(User, None)
    # is a documented SAWarning / future error, so return before it.
    if application.student_id is None:
        return
    student = await db.get(User, application.student_id)
```

`apps/api/app/services/staff_activity.py` `_subjects`, overseas_application branch:

```python
        query = (
            select(OverseasApplication.id, func.coalesce(User.full_name, AgentStudent.full_name), University.name)
            .outerjoin(User, User.id == OverseasApplication.student_id)
            .outerjoin(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)
            .outerjoin(University, University.id == OverseasApplication.university_id)
            .where(OverseasApplication.id.in_(wanted["overseas_application"]))
        )
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `API_TEST tests/test_agn_008_null_owner.py tests/test_rpt_002_overseas_reporting.py tests/test_visa_003_status.py tests/test_uni_001_university_rep_portal.py tests/test_agt_002_referrals.py tests/test_agn_021_activity.py tests/test_cns_001_counselor_workspace.py`
Also run `grep -l "inbound" apps/api/tests/*.py` and add the inbound test file(s) it lists.
Expected: PASS.

- [ ] **Step 6: Refactor and re-run**

`grep -n "User.id == OverseasApplication.student_id" apps/api/app/services/portal.py` should list only the `_overseas_student` sites, which filter by `user.id` and are unaffected. Re-run Step 5.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/services/portal.py apps/api/app/api/lookups.py apps/api/app/api/inbound.py apps/api/app/services/staff_activity.py apps/api/tests/test_agn_008_null_owner.py
git commit -m "feat(agn-008): portal, lookups, inbound and activity show no-login owners without crashing"
```

---

### Task 4: Request schemas

**Files:**
- Modify: `apps/api/app/schemas.py`
  - imports at L4: `from datetime import UTC, date, datetime, timedelta`
  - new block after `AgentStudentAssign` (~L559)
- Test: `apps/api/tests/test_agn_008_schemas.py`

**Interfaces:**
- Produces:
  - `AgentApplicationCreate(agent_student_id: UUID, university_id: UUID, intake: str, course_id: UUID | None, application_reference: str | None, submitted_on/application_deadline/offer_deadline: date | None, next_action: str | None)`
  - `AgentApplicationUpdate`: the same optional fields plus `intake: str | None`, no ids except `course_id`
  - `AgentApplicationStatus(to_status: str, expected_status: str | None, notes: str | None, next_action: str | None)`

- [ ] **Step 1: Write the failing test**

```python
"""AGN-008 spec §5.4 -- request schemas: forbid extras, trim, bounds, date sanity, null semantics."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas import AgentApplicationCreate, AgentApplicationStatus, AgentApplicationUpdate

IDS = {"agent_student_id": str(uuid.uuid4()), "university_id": str(uuid.uuid4())}


def test_create_trims_and_blanks_become_none():
    body = AgentApplicationCreate(**IDS, intake="  Fall 2027 ", application_reference="  ", next_action=" Send SOP ")
    assert (body.intake, body.application_reference, body.next_action) == ("Fall 2027", None, "Send SOP")


@pytest.mark.parametrize("extra", [{"agent_id": str(uuid.uuid4())}, {"status": "offer"}, {"student_id": str(uuid.uuid4())}])
def test_create_forbids_server_owned_fields(extra):
    with pytest.raises(ValidationError):
        AgentApplicationCreate(**IDS, intake="Fall", **extra)


@pytest.mark.parametrize("intake", ["", "   ", "x" * 81])
def test_create_needs_an_intake_of_1_to_80(intake):
    with pytest.raises(ValidationError):
        AgentApplicationCreate(**IDS, intake=intake)


def test_reference_and_next_action_limits_and_control_characters():
    with pytest.raises(ValidationError):
        AgentApplicationCreate(**IDS, intake="Fall", application_reference="x" * 141)
    with pytest.raises(ValidationError):
        AgentApplicationCreate(**IDS, intake="Fall", next_action="x" * 501)
    with pytest.raises(ValidationError):
        AgentApplicationCreate(**IDS, intake="Fall", application_reference="AB\x00C")


@pytest.mark.parametrize("field", ["submitted_on", "application_deadline", "offer_deadline"])
@pytest.mark.parametrize("value", [date(1999, 12, 31), date(2101, 1, 1)])
def test_dates_outside_2000_to_2100_are_refused(field, value):
    with pytest.raises(ValidationError):
        AgentApplicationCreate(**IDS, intake="Fall", **{field: value})


def test_submission_date_allows_one_day_ahead_of_utc_and_no_more():
    today = datetime.now(UTC).date()
    AgentApplicationCreate(**IDS, intake="Fall", submitted_on=today + timedelta(days=1))
    with pytest.raises(ValidationError, match="Submission date cannot be in the future"):
        AgentApplicationCreate(**IDS, intake="Fall", submitted_on=today + timedelta(days=2))


def test_past_deadlines_are_allowed():
    AgentApplicationCreate(**IDS, intake="Fall", application_deadline=date(2020, 1, 1))


def test_update_absent_is_unchanged_null_clears_and_intake_cannot_clear():
    body = AgentApplicationUpdate(application_reference=None)
    assert body.model_fields_set == {"application_reference"} and body.application_reference is None
    with pytest.raises(ValidationError):
        AgentApplicationUpdate(intake=None)
    with pytest.raises(ValidationError):
        AgentApplicationUpdate(university_id=str(uuid.uuid4()))


def test_status_body_bounds():
    AgentApplicationStatus(to_status="offer", expected_status="enquiry", notes="ok")
    with pytest.raises(ValidationError):
        AgentApplicationStatus(to_status="offer", notes="x" * 2001)
    with pytest.raises(ValidationError):
        AgentApplicationStatus(to_status="offer", agent_id="x")
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `API_TEST tests/test_agn_008_schemas.py`
Expected: FAIL with `ImportError: cannot import name 'AgentApplicationCreate'`.

- [ ] **Step 3: Implement the schemas**

Change the import line to `from datetime import UTC, date, datetime, timedelta`. After `AgentStudentAssign`, add:

```python
# --- AGN-008: agent applications (DEC-SCOPE-050; docs/superpowers/specs/2026-10-02-agn-008-agent-applications-design.md §5.4) ---

_APPLICATION_DATE_MIN, _APPLICATION_DATE_MAX = date(2000, 1, 1), date(2100, 12, 31)


def _application_date(value: date | None) -> date | None:
    """Catches typed-year slips (0202, 20226) before they reach a deadline list."""
    if value is not None and not (_APPLICATION_DATE_MIN <= value <= _APPLICATION_DATE_MAX):
        raise PydanticCustomError("invalid_application_date", "Dates must be between 2000 and 2100")
    return value


def _intake(value: str | None) -> str:
    value = clean_free_text(value, 80)
    if not value:
        raise PydanticCustomError("blank_intake", "Intake is required")
    return value


class _AgentApplicationFields(BaseModel):
    """Server-owned fields (agent, student, status, university on edit) are not accepted -- `extra="forbid"` answers 422."""

    model_config = {"extra": "forbid"}
    course_id: UUID | None = None
    application_reference: str | None = None
    submitted_on: date | None = None
    application_deadline: date | None = None
    offer_deadline: date | None = None
    next_action: str | None = None

    @field_validator("application_reference")
    @classmethod
    def _reference(cls, value):
        return clean_free_text(value, 140)

    @field_validator("next_action")
    @classmethod
    def _next_action(cls, value):
        return clean_free_text(value, 500)

    @field_validator("application_deadline", "offer_deadline")
    @classmethod
    def _deadline(cls, value):
        return _application_date(value)

    @field_validator("submitted_on")
    @classmethod
    def _submitted(cls, value):
        value = _application_date(value)
        # One day ahead of UTC is allowed: a user east of UTC (IST after midnight) is already on tomorrow's date.
        if value is not None and value > datetime.now(UTC).date() + timedelta(days=1):
            raise PydanticCustomError("future_submission_date", "Submission date cannot be in the future")
        return value


class AgentApplicationCreate(_AgentApplicationFields):
    agent_student_id: UUID
    university_id: UUID
    intake: str

    @field_validator("intake")
    @classmethod
    def _intake_required(cls, value):
        return _intake(value)


class AgentApplicationUpdate(_AgentApplicationFields):
    """Omitted = unchanged; null clears an optional field; intake cannot be cleared; the university is fixed (A10)."""

    intake: str | None = None

    @model_validator(mode="after")
    def _intake_when_sent(self):
        if "intake" in self.model_fields_set:
            self.intake = _intake(self.intake)
        return self


class AgentApplicationStatus(BaseModel):
    """`expected_status`: the status the caller saw; a mismatch is a 409, so a stale screen cannot act on a changed application."""

    model_config = {"extra": "forbid"}
    to_status: str = Field(max_length=50)
    expected_status: str | None = Field(default=None, max_length=50)
    notes: str | None = None
    next_action: str | None = None

    @field_validator("notes")
    @classmethod
    def _notes(cls, value):
        return clean_free_text(value, 2000)

    @field_validator("next_action")
    @classmethod
    def _next_action(cls, value):
        return clean_free_text(value, 500)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `API_TEST tests/test_agn_008_schemas.py tests/test_agn_004_schemas.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas.py apps/api/tests/test_agn_008_schemas.py
git commit -m "feat(agn-008): request schemas for agent applications"
```

---

### Task 5: Read routes — list with status groups, detail with history

**Files:**
- Modify: `apps/api/app/services/agent_applications.py` (append)
- Create: `apps/api/app/api/agent_applications.py`
- Modify: `apps/api/app/main.py:64` (add `agent_applications.router` after `agent_students.router`; import it)
- Test: `apps/api/tests/test_agn_008_read.py`

**Interfaces:**
- Produces (service):
  - `STATUS_GROUPS = ("all", "draft", "submitted", "offer", "visa", "enrolled", "withdrawn")`
  - `group_clause(group: str)`
  - `nearest_deadline(app, today) -> dict | None`
  - `item(row, today) -> dict`
  - `async load_scoped(db, user, application_id, *, lock=False) -> OverseasApplication` (404 `NOT_FOUND`)
  - `async owner_record(db, user, app) -> AgentStudent | None`
  - `async detail(db, user, app) -> dict`
  - `async list_page(db, user, *, group, agent_student_id, limit, offset) -> dict`
- Produces (router): `router`, `_audit(db, user, action, application_id, metadata=None)`, `_log(event, membership, user, application_id, **extra)`, `_locked(db, user, membership, application_id)`.

- [ ] **Step 1: Write the failing test**

```python
"""AGN-008 AC07 + read side of AC01/AC02 -- list (status groups, student filter, paging, scope) and detail with history."""

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio

from app.models import ApplicationStatusHistory
from tests.agn001_helpers import client_for, mk_user
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import APPS, agency_world, mk_application

GROUPS = {
    "draft": {"pre_unsubmitted"},
    "submitted": {"pre_submitted"},
    "offer": {"offer"},
    "visa": {"visa", "tracking"},
    "enrolled": {"enrolled"},
    "withdrawn": {"withdrawn"},
    "all": {"pre_unsubmitted", "pre_submitted", "offer", "visa", "tracking", "enrolled"},
}


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    u = w["university"]
    m = w["master"]
    rows = {
        "pre_unsubmitted": await mk_application(db_session, agent=m, university=u, record=w["record"], status="eligibility_evaluation"),
        "pre_submitted": await mk_application(db_session, agent=m, university=u, record=w["record"], status="university_selection", submitted_on=date(2026, 9, 1), intake="Spring 2028"),
        "offer": await mk_application(db_session, agent=m, university=u, record=w["record"], status="offer", intake="Fall 2028"),
        "visa": await mk_application(db_session, agent=m, university=u, record=w["record"], status="visa_documentation", intake="Spring 2029"),
        "tracking": await mk_application(db_session, agent=m, university=u, record=w["record"], status="status_tracking", intake="Fall 2029"),
        "enrolled": await mk_application(db_session, agent=m, university=u, record=w["record"], status="enrolled", intake="Spring 2030"),
        "withdrawn": await mk_application(db_session, agent=m, university=u, record=w["record"], status="withdrawn", intake="Fall 2030"),
    }
    return w | {"apps": rows}


@pytest.mark.asyncio
@pytest.mark.parametrize("group", list(GROUPS))
async def test_each_status_group_returns_exactly_its_subset(world, group):
    async with client_for(world["master"].email) as c:
        body = (await c.get(APPS, params={"status": group, "student": str(world["record"].id), "limit": 100})).json()
    expected = {str(world["apps"][k].id) for k in GROUPS[group]}
    assert {i["id"] for i in body["items"]} == expected
    assert body["total"] == len(expected)


@pytest.mark.asyncio
async def test_unknown_group_is_422(world):
    async with client_for(world["master"].email) as c:
        assert (await c.get(APPS, params={"status": "rejected"})).status_code == 422


@pytest.mark.asyncio
async def test_paging_shape_and_totals(world):
    async with client_for(world["master"].email) as c:
        first = (await c.get(APPS, params={"student": str(world["record"].id), "limit": 2, "offset": 0})).json()
        second = (await c.get(APPS, params={"student": str(world["record"].id), "limit": 2, "offset": 2})).json()
    assert (first["total"], first["limit"], first["offset"], len(first["items"])) == (6, 2, 0, 2)
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}


@pytest.mark.asyncio
async def test_item_shape_is_an_allowlist(world):
    async with client_for(world["master"].email) as c:
        item = (await c.get(APPS, params={"status": "offer"})).json()["items"][0]
    assert set(item) == {
        "id", "agent_student_id", "student", "has_login", "university", "course", "intake", "status", "application_reference",
        "submitted_on", "application_deadline", "offer_deadline", "nearest_deadline", "next_action", "updated_at",
    }
    assert item["student"] == world["record"].full_name and item["has_login"] is False


@pytest.mark.asyncio
async def test_nearest_deadline_prefers_the_next_upcoming_then_the_latest_past(db_session, world):
    today = date.today()
    soon = await mk_application(db_session, agent=world["master"], university=world["university"], record=world["record"], intake="N1", application_deadline=today + timedelta(days=3), offer_deadline=today + timedelta(days=30))
    past = await mk_application(db_session, agent=world["master"], university=world["university"], record=world["record"], intake="N2", application_deadline=today - timedelta(days=9), offer_deadline=today - timedelta(days=2))
    async with client_for(world["master"].email) as c:
        a = (await c.get(f"{APPS}/{soon.id}")).json()["application"]
        b = (await c.get(f"{APPS}/{past.id}")).json()["application"]
    assert a["nearest_deadline"] == {"kind": "application", "date": str(today + timedelta(days=3))}
    assert b["nearest_deadline"] == {"kind": "offer", "date": str(today - timedelta(days=2))}


@pytest.mark.asyncio
async def test_staff_list_only_assigned_and_other_org_sees_nothing(db_session, world):
    stranger = await mk_record(db_session, agent=world["master"], full_name="Unassigned")
    hidden = await mk_application(db_session, agent=world["master"], university=world["university"], record=stranger)
    async with client_for(world["staff"]["user"].email) as c:
        ids = {i["id"] for i in (await c.get(APPS, params={"limit": 100})).json()["items"]}
    assert str(world["apps"]["offer"].id) in ids and str(hidden.id) not in ids
    async with client_for(world["other"]["master"].email) as c:
        assert (await c.get(APPS)).json()["total"] == 0


@pytest.mark.asyncio
async def test_detail_has_history_and_read_only_reason(db_session, world):
    app = world["apps"]["withdrawn"]
    db_session.add(ApplicationStatusHistory(application_id=app.id, from_status=None, to_status="enquiry", changed_by_id=world["master"].id))
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        body = (await c.get(f"{APPS}/{app.id}")).json()["application"]
    assert body["read_only_reason"] == "withdrawn"
    assert body["history"][0]["to_status"] == "enquiry" and body["history"][0]["changed_by"] == world["master"].full_name
    assert {"university_id", "university_slug", "course_id", "created_at"} <= set(body)
    assert not {"agent_id", "student_id", "counselor_id", "email", "phone"} & set(body)


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["other_staff", "other_master"])
async def test_detail_out_of_scope_is_404(world, who):
    user = world["other_staff"]["user"] if who == "other_staff" else world["other"]["master"]
    async with client_for(user.email) as c:
        response = await c.get(f"{APPS}/{world['apps']['offer'].id}")
    assert response.status_code == 404 and response.json()["detail"] == "Application not found"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["super_admin", "counselor", "university_rep", "overseas_student"])
async def test_non_agents_are_refused(db_session, world, role):
    user = await mk_user(db_session, role=role, division="global" if role == "super_admin" else "overseas")
    async with client_for(user.email) as c:
        assert (await c.get(APPS)).status_code == 403


@pytest.mark.asyncio
async def test_unknown_id_is_404(world):
    async with client_for(world["master"].email) as c:
        assert (await c.get(f"{APPS}/{uuid.uuid4()}")).status_code == 404
```

`client_for` logs in with division `overseas`. If super_admin login needs division `global`, give `client_for` a `division` argument by adding the keyword to the helper (default unchanged), or log in with `login(c, email, "global")` directly in that one test.

- [ ] **Step 2: Run it and confirm it fails**

Run: `API_TEST tests/test_agn_008_read.py`
Expected: FAIL, with 404 on every call because the route is not registered.

- [ ] **Step 3: Write the service, read side (append)**

```python
from datetime import date

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import ApplicationStatusHistory, OverseasCourse, University
from app.services.agent_students import application_scope, student_scope

NOT_FOUND = "Application not found"
PRE_OFFER = ("enquiry", "eligibility_evaluation", "university_selection")
STATUS_GROUPS = ("all", "draft", "submitted", "offer", "visa", "enrolled", "withdrawn")


def group_clause(group: str):
    """A7/A9: the sidebar filters. Draft and Submitted split the pre-offer stages by `submitted_on`; All hides withdrawn."""
    status = OverseasApplication.status
    return {
        "draft": and_(status.in_(PRE_OFFER), OverseasApplication.submitted_on.is_(None)),
        "submitted": and_(status.in_(PRE_OFFER), OverseasApplication.submitted_on.is_not(None)),
        "offer": status == "offer",
        "visa": status.in_(("visa_documentation", "status_tracking")),
        "enrolled": status == "enrolled",
        "withdrawn": status == WITHDRAWN,
    }.get(group, status != WITHDRAWN)


def _rows_stmt() -> Select:
    return with_owner(
        select(OverseasApplication, University.name, University.slug, OverseasCourse.title)
        .join(University, University.id == OverseasApplication.university_id)
        .outerjoin(OverseasCourse, OverseasCourse.id == OverseasApplication.course_id)
    )


def nearest_deadline(app: OverseasApplication, today: date) -> dict | None:
    """The earliest deadline that is today or later; if none is upcoming, the most recent past one (the UI marks it past)."""
    dates = [(d, kind) for kind, d in (("application", app.application_deadline), ("offer", app.offer_deadline)) if d]
    if not dates:
        return None
    upcoming = [x for x in dates if x[0] >= today]
    when, kind = min(upcoming) if upcoming else max(dates)
    return {"kind": kind, "date": when}


def item(row: tuple, today: date) -> dict:
    """List shape -- an explicit allowlist: no agent, counselor or account ids, no email or phone."""
    app, university, _slug, course, owner = row
    return {
        "id": app.id,
        "agent_student_id": app.agent_student_id,
        "student": owner.full_name or "Unnamed student",
        "has_login": owner.id is not None,
        "university": university,
        "course": course,
        "intake": app.intake,
        "status": app.status,
        "application_reference": app.application_reference,
        "submitted_on": app.submitted_on,
        "application_deadline": app.application_deadline,
        "offer_deadline": app.offer_deadline,
        "nearest_deadline": nearest_deadline(app, today),
        "next_action": app.next_action,
        "updated_at": app.updated_at,
    }


async def load_scoped(db: AsyncSession, user: User, application_id, *, lock: bool = False) -> OverseasApplication:
    """The caller's application or 404 -- scope is in the WHERE clause, never checked after loading."""
    stmt = (
        select(OverseasApplication)
        .where(OverseasApplication.id == application_id, OverseasApplication.school_student_id.is_(None), *application_scope(user))
        .execution_options(populate_existing=True)
    )
    row = await db.scalar(stmt.with_for_update(of=OverseasApplication) if lock else stmt)
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row


async def owner_record(db: AsyncSession, user: User, app: OverseasApplication) -> AgentStudent | None:
    """The agency record the application belongs to: its own link (AGN-008), else -- an application made before AGN-008 -- the
    caller's record of the same logged-in student."""
    if app.agent_student_id is not None:
        return await db.get(AgentStudent, app.agent_student_id, populate_existing=True)
    if app.student_id is None:
        return None
    return await db.scalar(select(AgentStudent).where(AgentStudent.student_id == app.student_id, *student_scope(user)).order_by(AgentStudent.created_at).limit(1))


Changer = aliased(User)


async def detail(db: AsyncSession, user: User, app: OverseasApplication) -> dict:
    row = owned([(await db.execute(_rows_stmt().where(OverseasApplication.id == app.id).execution_options(populate_existing=True))).one()])[0]
    found = row[0]
    history = (
        await db.execute(
            select(ApplicationStatusHistory, Changer.full_name)
            .outerjoin(Changer, Changer.id == ApplicationStatusHistory.changed_by_id)
            .where(ApplicationStatusHistory.application_id == found.id)
            .order_by(ApplicationStatusHistory.created_at, ApplicationStatusHistory.id)
        )
    ).all()
    record = await owner_record(db, user, found)
    reason = WITHDRAWN if found.status == WITHDRAWN else "archived" if record is not None and record.status == "archived" else None
    return {
        **item(row, date.today()),
        "university_id": found.university_id,
        "university_slug": row[2],
        "course_id": found.course_id,
        "created_at": found.created_at,
        "read_only_reason": reason,
        "history": [
            {"from_status": h.from_status, "to_status": h.to_status, "next_action": h.next_action, "notes": h.notes, "changed_by": name, "created_at": h.created_at}
            for h, name in history
        ],
    }


async def list_page(db: AsyncSession, user: User, *, group: str, agent_student_id, limit: int, offset: int) -> dict:
    filters = [*application_scope(user), group_clause(group)]
    if agent_student_id is not None:
        login = select(AgentStudent.student_id).where(AgentStudent.id == agent_student_id).scalar_subquery()
        filters.append(or_(OverseasApplication.agent_student_id == agent_student_id, and_(OverseasApplication.student_id.is_not(None), OverseasApplication.student_id == login)))
    base = _rows_stmt().where(*filters)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = owned((await db.execute(base.order_by(OverseasApplication.updated_at.desc(), OverseasApplication.id).limit(limit).offset(offset))).all())
    today = date.today()
    return {"items": [item(r, today) for r in rows], "total": total or 0, "limit": limit, "offset": offset}
```

Merge these imports into the module's single import block at the top. Do not leave a second import block in the middle.

- [ ] **Step 4: Write the router, read side**

`apps/api/app/api/agent_applications.py`:

```python
"""AGN-008 -- an agency's applications for its students, with or without a login (DEC-SCOPE-050; spec §5.3).

Masters see the agency's applications; staff only those of students assigned to them (G4); anything outside the caller's scope is
404. Every write locks the organisation row first and the application row second (AGN-004's lock order), writes its history and
audit rows in the same transaction and commits once, so the duplicate check, the throttle and the status rules hold under
concurrency. Agents move an application forward up to status_tracking or withdraw it; `enrolled` stays with counselor, university
and admin, so an agent never accrues their own commission (A4).
"""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_students import _gate
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AgentOrgMember, AuditLog, User
from app.services.agent_applications import detail, list_page, load_scoped
from app.services.agent_orgs import lock_active_org

logger = logging.getLogger("app.agent_applications")

router = APIRouter(prefix="/workflows/overseas/agent/crm/applications", tags=["agent-applications"])

StatusGroup = Literal["all", "draft", "submitted", "offer", "visa", "enrolled", "withdrawn"]


def _audit(db: AsyncSession, user: User, action: str, application_id, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed, SEC-001); ids, field names and statuses only. The `overseas.application.*`
    names are the ones the existing paths write, so AGN-021 activity and the throttle read one record."""
    db.add(AuditLog(user_id=user.id, action=f"overseas.application.{action}", entity_type="overseas_application", entity_id=str(application_id), metadata_json=metadata or {}))


def _log(event: str, membership: AgentOrgMember, user: User, application_id, *, level: int = logging.INFO, **extra) -> None:
    logger.log(level, event, extra={"extra_fields": {"org_id": str(membership.org_id), "actor_id": str(user.id), "application_id": str(application_id), **extra}})


async def _locked(db: AsyncSession, user: User, membership: AgentOrgMember, application_id: UUID):
    """Organisation lock first (the order every agency write uses), then the scoped row -- out of scope stays 404."""
    await lock_active_org(db, membership.org_id)
    return await load_scoped(db, user, application_id, lock=True)


@router.get("")
async def list_applications(
    status: StatusGroup = "all",
    student: UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _gate(user)
    return await list_page(db, user, group=status, agent_student_id=student, limit=limit, offset=offset)


@router.get("/{application_id}")
async def get_application(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _gate(user)
    return {"application": await detail(db, user, await load_scoped(db, user, application_id))}
```

In `apps/api/app/main.py`, import `agent_applications` alongside `agent_students`, and add `agent_applications.router` right after `agent_students.router` in the router tuple.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `API_TEST tests/test_agn_008_read.py`
Expected: PASS.

- [ ] **Step 6: Refactor and re-run**

There should be one import block in the service, and `item()` should be used by both `list_page` and `detail`. Re-run Step 5.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/services/agent_applications.py apps/api/app/api/agent_applications.py apps/api/app/main.py apps/api/tests/test_agn_008_read.py
git commit -m "feat(agn-008): agent applications list (status groups) and detail with history"
```

---

### Task 6: Create — scope, archived, course, duplicate, throttle, notification, failure

**Files:**
- Modify: `apps/api/app/services/agent_orgs.py:204-221` (extract `retry_after`)
- Modify: `apps/api/app/services/agent_applications.py` (append)
- Modify: `apps/api/app/api/agent_applications.py` (append the POST route)
- Test: `apps/api/tests/test_agn_008_create.py`

**Interfaces:**
- Produces (agent_orgs): `retry_after(recent: list[datetime], limit: int, now: datetime) -> int`.
- Produces (service):
  - `CREATE_LIMIT = 200`, `ARCHIVED`, `DUPLICATE`, `THROTTLED`
  - `async create_wait_seconds(db, user) -> int`
  - `async check_course(db, university_id, course_id) -> None`
  - `async duplicate_exists(db, *, agent_student_id, student_id, university_id, course_id, exclude_id=None) -> bool`

- [ ] **Step 1: Write the failing test**

```python
"""AGN-008 AC01-AC03, AC14, AC15 create side -- POST creates an application of an agency student with or without a login."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.api import agent_applications as router_module
from app.models import ApplicationStatusHistory, AuditLog, Notification, OverseasApplication, OverseasCourse
from app.services import agent_applications as service
from tests.agn001_helpers import client_for
from tests.agn003_helpers import mk_university
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import APPS, agency_world, mk_application


@pytest_asyncio.fixture
async def world(db_session):
    return await agency_world(db_session)


def _body(w, **over):
    return {"agent_student_id": str(w["record"].id), "university_id": str(w["university"].id), "intake": "Fall 2027", **over}


async def _count(db, model, *where):
    return await db.scalar(select(func.count()).select_from(model).where(*where))


@pytest.mark.asyncio
async def test_master_creates_for_a_student_with_no_login(db_session, world):
    async with client_for(world["master"].email) as c:
        response = await c.post(APPS, json=_body(world, application_reference="UCAS-1", submitted_on="2026-09-01", offer_deadline="2027-01-15"))
    assert response.status_code == 201, response.text
    body = response.json()["application"]
    assert (body["status"], body["has_login"], body["application_reference"], body["submitted_on"]) == ("enquiry", False, "UCAS-1", "2026-09-01")
    row = await db_session.get(OverseasApplication, uuid.UUID(body["id"]), populate_existing=True)
    assert (row.agent_student_id, row.student_id, row.agent_id) == (world["record"].id, None, world["master"].id)
    history = (await db_session.scalars(select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == row.id))).all()
    assert [(h.from_status, h.to_status) for h in history] == [(None, "enquiry")]
    assert await _count(db_session, AuditLog, AuditLog.action == "overseas.application.create", AuditLog.entity_id == str(row.id)) == 1


@pytest.mark.asyncio
async def test_linked_student_gets_student_id_and_the_existing_notification(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        response = await c.post(APPS, json=_body(world, agent_student_id=str(world["linked_record"].id)))
    assert response.status_code == 201, response.text
    row = await db_session.get(OverseasApplication, uuid.UUID(response.json()["application"]["id"]), populate_existing=True)
    assert row.student_id == world["linked_user"].id and row.agent_id == world["staff"]["user"].id
    assert await _count(db_session, Notification, Notification.user_id == world["linked_user"].id, Notification.title == "Application created") == 1


@pytest.mark.asyncio
async def test_staff_cannot_create_for_an_unassigned_or_foreign_student(db_session, world):
    unassigned = await mk_record(db_session, agent=world["master"], full_name="Unassigned")
    foreign = await mk_record(db_session, agent=world["other"]["master"], full_name="Foreign")
    async with client_for(world["staff"]["user"].email) as c:
        for record in (unassigned, foreign):
            response = await c.post(APPS, json=_body(world, agent_student_id=str(record.id)))
            assert response.status_code == 404 and response.json()["detail"] == "Student not found"


@pytest.mark.asyncio
async def test_archived_student_is_409(db_session, world):
    archived = await mk_record(db_session, agent=world["master"], full_name="Archived", status="archived")
    async with client_for(world["master"].email) as c:
        response = await c.post(APPS, json=_body(world, agent_student_id=str(archived.id)))
    assert response.status_code == 409 and response.json()["detail"] == "Unarchive this student first"


@pytest.mark.asyncio
async def test_unknown_university_404_and_foreign_course_422(db_session, world):
    other_uni = await mk_university(db_session)
    course = OverseasCourse(university_id=other_uni.id, title="MSc", level="PG", category="x", duration="1y", tuition_fee="1", intake="Sep")
    db_session.add(course)
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        assert (await c.post(APPS, json=_body(world, university_id=str(uuid.uuid4())))).status_code == 404
        response = await c.post(APPS, json=_body(world, course_id=str(course.id)))
    assert response.status_code == 422 and response.json()["detail"] == "Course does not belong to selected university"


@pytest.mark.asyncio
async def test_duplicate_is_409_until_withdrawn(db_session, world):
    async with client_for(world["master"].email) as c:
        first = await c.post(APPS, json=_body(world))
        assert first.status_code == 201
        again = await c.post(APPS, json=_body(world))
        assert again.status_code == 409 and again.json()["detail"] == "An application for this university/course already exists"
        row = await db_session.get(OverseasApplication, uuid.UUID(first.json()["application"]["id"]), populate_existing=True)
        row.status = "withdrawn"
        await db_session.commit()
        assert (await c.post(APPS, json=_body(world))).status_code == 201


@pytest.mark.asyncio
async def test_legacy_linked_application_is_a_duplicate(db_session, world):
    await mk_application(db_session, agent=world["master"], university=world["university"], student=world["linked_user"])  # pre-AGN-008 row
    async with client_for(world["master"].email) as c:
        response = await c.post(APPS, json=_body(world, agent_student_id=str(world["linked_record"].id)))
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_throttle_429_with_retry_after_and_other_org_unaffected(db_session, world, monkeypatch):
    monkeypatch.setattr(service, "CREATE_LIMIT", 2)
    for _ in range(2):
        db_session.add(AuditLog(user_id=world["staff"]["user"].id, action="overseas.application.create", entity_type="overseas_application", entity_id=str(uuid.uuid4())))
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        response = await c.post(APPS, json=_body(world))
    assert response.status_code == 429 and int(response.headers["Retry-After"]) > 0
    assert response.json()["detail"] == "Too many applications created today -- try again later"
    other_record = await mk_record(db_session, agent=world["other"]["master"], full_name="Other Org Student")
    async with client_for(world["other"]["master"].email) as c:
        assert (await c.post(APPS, json=_body(world, agent_student_id=str(other_record.id)))).status_code == 201


def test_create_limit_is_200():
    assert service.CREATE_LIMIT == 200


@pytest.mark.asyncio
async def test_a_failure_before_commit_leaves_nothing(db_session, world, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("notification store down")

    monkeypatch.setattr(router_module, "_notify_user", boom)
    async with client_for(world["master"].email) as c:
        with pytest.raises(RuntimeError):
            await c.post(APPS, json=_body(world, agent_student_id=str(world["linked_record"].id)))
    assert await _count(db_session, OverseasApplication, OverseasApplication.agent_student_id == world["linked_record"].id) == 0
    assert await _count(db_session, AuditLog, AuditLog.action == "overseas.application.create", AuditLog.user_id == world["master"].id) == 0


@pytest.mark.asyncio
async def test_create_is_logged_without_personal_data(world, caplog):
    import logging

    logging.getLogger("app.agent_applications").disabled = False
    caplog.set_level(logging.INFO, logger="app.agent_applications")
    async with client_for(world["master"].email) as c:
        await c.post(APPS, json=_body(world, application_reference="SECRET-REF"))
    record = next(r for r in caplog.records if r.getMessage() == "agent_application_created")
    assert set(record.extra_fields) >= {"org_id", "actor_id", "application_id"} and "SECRET-REF" not in str(record.extra_fields)
```

If `ASGITransport` returns a 500 instead of raising, assert `response.status_code == 500` in `test_a_failure_before_commit_leaves_nothing`. `raise_app_exceptions` defaults to True, so raising is expected.

- [ ] **Step 2: Run it and confirm it fails**

Run: `API_TEST tests/test_agn_008_create.py`
Expected: FAIL with 405 Method Not Allowed on POST, plus `AttributeError: CREATE_LIMIT`.

- [ ] **Step 3: Extract `retry_after` in `agent_orgs.py`**

The behaviour is the same:

```python
def retry_after(recent: list[datetime], limit: int, now: datetime) -> int:
    """Seconds until the oldest of the last `limit` actions leaves THROTTLE_WINDOW; 0 while under the limit. `recent` is newest
    first and holds at most `limit` timestamps."""
    if len(recent) < limit:
        return 0
    return max(1, math.ceil((recent[-1] + THROTTLE_WINDOW - now).total_seconds()))
```

`_wait_seconds` ends with `return retry_after(recent, limit, now)`.

- [ ] **Step 4: Write the service, create side (append)**

```python
from datetime import UTC, datetime

from app.models import AuditLog
from app.services.agent_orgs import THROTTLE_WINDOW, org_member_ids, retry_after

CREATE_LIMIT = 200  # A14: per agency per rolling 24 hours
ARCHIVED = "Unarchive this student first"
DUPLICATE = "An application for this university/course already exists"
THROTTLED = "Too many applications created today -- try again later"


async def create_wait_seconds(db: AsyncSession, user: User) -> int:
    """A14: counted from the agency's `overseas.application.create` audit rows (every path that creates one), the
    DEC-SCOPE-038 R1 no-new-table pattern; runs under the organisation lock, so it is race-free."""
    now = datetime.now(UTC)
    recent = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.action == "overseas.application.create", AuditLog.user_id.in_(org_member_ids(user)), AuditLog.created_at > now - THROTTLE_WINDOW)
            .order_by(AuditLog.created_at.desc())
            .limit(CREATE_LIMIT)
        )
    ).all()
    return retry_after(list(recent), CREATE_LIMIT, now)


async def check_course(db: AsyncSession, university_id, course_id) -> None:
    if course_id is None:
        return
    course = await db.get(OverseasCourse, course_id)
    if course is None or course.university_id != university_id:
        raise HTTPException(422, "Course does not belong to selected university")


async def duplicate_exists(db: AsyncSession, *, agent_student_id, student_id, university_id, course_id, exclude_id=None) -> bool:
    """OVS-002's rule for an agency student: same student, university and course (both NULL counts as the same), not withdrawn. The
    student is the agency record or -- when it has a login -- that account, so a row made before AGN-008 still counts."""
    owners = [OverseasApplication.agent_student_id == agent_student_id] if agent_student_id is not None else []
    if student_id is not None:
        owners.append(OverseasApplication.student_id == student_id)
    if not owners:
        return False
    course = OverseasApplication.course_id.is_(None) if course_id is None else OverseasApplication.course_id == course_id
    clauses = [or_(*owners), OverseasApplication.university_id == university_id, course, OverseasApplication.status != WITHDRAWN]
    if exclude_id is not None:
        clauses.append(OverseasApplication.id != exclude_id)
    return (await db.scalar(select(OverseasApplication.id).where(*clauses).limit(1))) is not None
```

Merge the imports into the top block.

- [ ] **Step 5: Write the router POST**

Add to the router imports: `from fastapi import HTTPException`; from `app.models`, `ApplicationStatusHistory, OverseasApplication, University`; `from app.schemas import AgentApplicationCreate`; `from app.api.workflows import _notify_user`; and from the service, `ARCHIVED, DEFAULT_NEXT_ACTION, DUPLICATE, THROTTLED, check_course, create_wait_seconds, duplicate_exists`. Also add `from app.services.agent_students import load_scoped as load_scoped_student`.

```python
@router.post("", status_code=201)
async def create_application(payload: AgentApplicationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    await lock_active_org(db, membership.org_id)  # serialises the throttle count and the duplicate check for the agency
    wait = await create_wait_seconds(db, user)
    if wait:
        _log("agent_application_create_throttled", membership, user, "-", level=logging.WARNING, wait_seconds=wait)
        raise HTTPException(429, THROTTLED, headers={"Retry-After": str(wait)})
    record = await load_scoped_student(db, user, payload.agent_student_id)  # 404 "Student not found" outside scope
    if record.status == "archived":
        raise HTTPException(409, ARCHIVED)
    university = await db.get(University, payload.university_id)
    if university is None:
        raise HTTPException(404, "University not found")
    await check_course(db, university.id, payload.course_id)
    if await duplicate_exists(db, agent_student_id=record.id, student_id=record.student_id, university_id=university.id, course_id=payload.course_id):
        raise HTTPException(409, DUPLICATE)
    item = OverseasApplication(
        agent_id=user.id,
        agent_student_id=record.id,
        student_id=record.student_id,
        university_id=university.id,
        course_id=payload.course_id,
        intake=payload.intake,
        status="enquiry",
        application_reference=payload.application_reference,
        submitted_on=payload.submitted_on,
        application_deadline=payload.application_deadline,
        offer_deadline=payload.offer_deadline,
        next_action=payload.next_action or DEFAULT_NEXT_ACTION,
    )
    db.add(item)
    await db.flush()
    db.add(ApplicationStatusHistory(application_id=item.id, from_status=None, to_status=item.status, next_action=item.next_action, changed_by_id=user.id))
    _audit(db, user, "create", item.id, {"agent_student_id": str(record.id), "university_id": str(university.id)})
    if record.student_id is not None:  # A8: a student with a login keeps today's notification
        student = await db.get(User, record.student_id)
        if student is not None:
            await _notify_user(db, student, "Application created", f"Your application to {university.name} has been created.", "/overseas/student/applications")
    await db.commit()
    _log("agent_application_created", membership, user, item.id)
    return {"application": await detail(db, user, item)}
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `API_TEST tests/test_agn_008_create.py tests/test_agn_001_team.py tests/test_agn_002_staff.py`
The AGN-001 and AGN-002 files cover the `retry_after` refactor.
Expected: PASS.

- [ ] **Step 7: Refactor and re-run**

`_wait_seconds` should have no duplicated math. Re-run Step 6.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/services/agent_orgs.py apps/api/app/services/agent_applications.py apps/api/app/api/agent_applications.py apps/api/tests/test_agn_008_create.py
git commit -m "feat(agn-008): create agent applications -- duplicate, archived, throttle, one transaction"
```

---

### Task 7: Edit, status change, withdraw, and the withdrawn guard on existing endpoints

**Files:**
- Modify: `apps/api/app/services/agent_applications.py` (append `check_transition` + messages)
- Modify: `apps/api/app/api/agent_applications.py` (PATCH, POST `/status`, `_refuse_closed`)
- Modify: `apps/api/app/api/workflows.py` (PATCH L1875+, `/advance` L1940+)
- Modify: `apps/api/app/services/staff_activity.py` (`STAFF_ACTIVITY_ACTIONS`)
- Test: `apps/api/tests/test_agn_008_edit.py`, `apps/api/tests/test_agn_008_status.py`

**Interfaces:**
- Produces (service): `WITHDRAWN_REFUSED`, `STALE`, `ENROLLED_REFUSED`, `ENROLLED_NOT_WITHDRAWABLE`, `check_transition(current: str, target: str) -> None`.

- [ ] **Step 1: Write the failing edit test**

`test_agn_008_edit.py`:

```python
"""AGN-008 AC04, AC15 (edit) -- PATCH editable fields; university fixed; course re-checks; withdrawn/archived 409."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import ApplicationStatusHistory, AuditLog, OverseasApplication, OverseasCourse
from tests.agn001_helpers import client_for
from tests.agn008_helpers import APPS, agency_world, mk_application


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    course = OverseasCourse(university_id=w["university"].id, title="MSc Data", level="PG", category="x", duration="1y", tuition_fee="1", intake="Sep")
    db_session.add(course)
    await db_session.commit()
    w["course"] = course
    w["app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    return w


@pytest.mark.asyncio
async def test_staff_edits_fields_and_null_clears(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        r = await c.patch(f"{APPS}/{world['app'].id}", json={"application_reference": "APP-9", "intake": "Spring 2028", "submitted_on": "2026-09-10", "application_deadline": "2026-12-01", "offer_deadline": "2027-02-01", "next_action": "Chase SOP", "course_id": str(world["course"].id)})
        assert r.status_code == 200, r.text
        r2 = await c.patch(f"{APPS}/{world['app'].id}", json={"application_reference": None})
    body = r2.json()["application"]
    assert body["application_reference"] is None and body["intake"] == "Spring 2028" and body["course"] == "MSc Data"
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "overseas.application.update", AuditLog.entity_id == str(world["app"].id)).order_by(AuditLog.created_at))).all()
    assert audit[0].metadata_json["fields"] == sorted(["application_reference", "intake", "submitted_on", "application_deadline", "offer_deadline", "next_action", "course_id"])
    history = (await db_session.scalars(select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == world["app"].id))).all()
    assert [(h.from_status, h.to_status, h.next_action) for h in history] == [("enquiry", "enquiry", "Chase SOP")]


@pytest.mark.asyncio
async def test_no_change_writes_nothing(db_session, world):
    async with client_for(world["master"].email) as c:
        assert (await c.patch(f"{APPS}/{world['app'].id}", json={"intake": "Fall 2027"})).status_code == 200
    assert (await db_session.scalars(select(AuditLog).where(AuditLog.action == "overseas.application.update", AuditLog.entity_id == str(world["app"].id)))).all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"university_id": str(uuid.uuid4())}, {"status": "offer"}, {"agent_id": str(uuid.uuid4())}, {"intake": ""}])
async def test_forbidden_or_invalid_fields_are_422(world, body):
    async with client_for(world["master"].email) as c:
        assert (await c.patch(f"{APPS}/{world['app'].id}", json=body)).status_code == 422


@pytest.mark.asyncio
async def test_course_change_rechecks_duplicate(db_session, world):
    await mk_application(db_session, agent=world["master"], university=world["university"], record=world["record"], course_id=world["course"].id, intake="Other")
    async with client_for(world["master"].email) as c:
        r = await c.patch(f"{APPS}/{world['app'].id}", json={"course_id": str(world["course"].id)})
    assert r.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(("setup", "detail"), [("withdrawn", "This application is withdrawn"), ("archived", "Unarchive this student first")])
async def test_closed_application_is_409(db_session, world, setup, detail):
    if setup == "withdrawn":
        row = await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)
        row.status = "withdrawn"
    else:
        world["record"].status = "archived"
        db_session.add(world["record"])
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await c.patch(f"{APPS}/{world['app'].id}", json={"intake": "X"})
    assert r.status_code == 409 and r.json()["detail"] == detail


@pytest.mark.asyncio
async def test_other_staff_edit_is_404(world):
    async with client_for(world["other_staff"]["user"].email) as c:
        assert (await c.patch(f"{APPS}/{world['app'].id}", json={"intake": "X"})).status_code == 404
```

- [ ] **Step 2: Write the failing status test**

`test_agn_008_status.py`:

```python
"""AGN-008 AC05, AC06, AC16 -- forward-only to status_tracking, withdraw, terminal, stale, no commission; counselor guards."""

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentCommission, ApplicationStatusHistory, AuditLog, OverseasApplication
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import APPS, agency_world, mk_application


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    return w


async def _status(c, app_id, to, expected=None, **extra):
    body = {"to_status": to, **({"expected_status": expected} if expected else {}), **extra}
    return await c.post(f"{APPS}/{app_id}/status", json=body)


@pytest.mark.asyncio
async def test_forward_and_skip_write_one_history_row_each(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        assert (await _status(c, world["app"].id, "eligibility_evaluation", "enquiry")).status_code == 200
        r = await _status(c, world["app"].id, "visa_documentation", "eligibility_evaluation", notes="Offer came early")
        assert r.status_code == 200 and r.json()["application"]["status"] == "visa_documentation"
        assert (await _status(c, world["app"].id, "status_tracking")).status_code == 200
    rows = (await db_session.scalars(select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == world["app"].id).order_by(ApplicationStatusHistory.created_at))).all()
    assert [(h.from_status, h.to_status) for h in rows] == [("enquiry", "eligibility_evaluation"), ("eligibility_evaluation", "visa_documentation"), ("visa_documentation", "status_tracking")]
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(world["app"].id)))).all()
    assert actions.count("overseas.application.advance") == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "target", "code"), [("offer", "offer", 422), ("offer", "eligibility_evaluation", 422), ("offer", "rejected", 422), ("offer", "enrolled", 403)])
async def test_backward_same_unknown_422_enrolled_403(db_session, world, start, target, code):
    row = await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)
    row.status = start
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await _status(c, world["app"].id, target)
    assert r.status_code == code
    assert (await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)).status == start
    assert await db_session.scalar(select(func.count()).select_from(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == world["app"].id)) == 0
    assert await db_session.scalar(select(func.count()).select_from(AgentCommission).where(AgentCommission.application_id == world["app"].id)) == 0


@pytest.mark.asyncio
async def test_withdraw_then_everything_is_409(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await _status(c, world["app"].id, "withdrawn", "enquiry")
        assert r.status_code == 200 and r.json()["application"]["read_only_reason"] == "withdrawn"
        for to in ("offer", "withdrawn"):
            assert (await _status(c, world["app"].id, to)).status_code == 409
        assert (await c.patch(f"{APPS}/{world['app'].id}", json={"intake": "X"})).status_code == 409
    assert "overseas.application.withdraw" in (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(world["app"].id)))).all()


@pytest.mark.asyncio
async def test_enrolled_cannot_be_withdrawn(db_session, world):
    row = await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)
    row.status = "enrolled"
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await _status(c, world["app"].id, "withdrawn")
    assert r.status_code == 409 and r.json()["detail"] == "An enrolled application cannot be withdrawn"


@pytest.mark.asyncio
async def test_stale_expected_status_is_refused(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await _status(c, world["app"].id, "offer", expected="university_selection")
    assert r.status_code == 409 and r.json()["detail"].startswith("This application changed since you opened it")
    assert (await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)).status == "enquiry"


@pytest.mark.asyncio
async def test_legacy_application_follows_the_archived_record(db_session, world):
    legacy = await mk_application(db_session, agent=world["master"], university=world["university"], student=world["linked_user"], intake="Legacy")
    world["linked_record"].status = "archived"
    db_session.add(world["linked_record"])
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        assert (await _status(c, legacy.id, "offer")).status_code == 409


@pytest.mark.asyncio
async def test_counselor_cannot_revive_a_withdrawn_application(db_session, world):
    counselor = await mk_user(db_session, role="counselor", full_name="Counselor")
    row = await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)
    row.status, row.counselor_id = "withdrawn", counselor.id
    await db_session.commit()
    async with client_for(counselor.email) as c:
        advance = await c.post(f"/api/v1/workflows/overseas/applications/{world['app'].id}/advance", json={"to_status": "offer"})
        patch = await c.patch(f"/api/v1/workflows/overseas/applications/{world['app'].id}", json={"status": "offer"})
        notes_only = await c.patch(f"/api/v1/workflows/overseas/applications/{world['app'].id}", json={"next_action": "Archive the file"})
    assert (advance.status_code, patch.status_code) == (409, 409)
    assert notes_only.status_code == 200  # only a status change is refused
    assert (await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)).status == "withdrawn"


@pytest.mark.asyncio
async def test_status_change_is_logged(world, caplog):
    import logging

    logging.getLogger("app.agent_applications").disabled = False
    caplog.set_level(logging.INFO, logger="app.agent_applications")
    async with client_for(world["master"].email) as c:
        await _status(c, world["app"].id, "offer")
    record = next(r for r in caplog.records if r.getMessage() == "agent_application_advanced")
    assert record.extra_fields["from_status"] == "enquiry" and record.extra_fields["to_status"] == "offer"
```

- [ ] **Step 3: Run them and confirm they fail**

Run: `API_TEST tests/test_agn_008_edit.py tests/test_agn_008_status.py`
Expected: FAIL with 405 on PATCH and POST `/status`, and the counselor revive test returns 200 instead of 409.

- [ ] **Step 4: Write the service transition rules (append)**

```python
WITHDRAWN_REFUSED = "This application is withdrawn"
STALE = "This application changed since you opened it -- reload to see its current status"
ENROLLED_REFUSED = "Only a counselor, university representative or admin can mark an application enrolled"
ENROLLED_NOT_WITHDRAWABLE = "An enrolled application cannot be withdrawn"


def check_transition(current: str, target: str) -> None:
    """A4: withdraw from any stage but enrolled; otherwise strictly forward, at most to status_tracking. A current value outside the
    stages (legacy free text) counts as before the first stage, as counselor /advance treats it."""
    if target == WITHDRAWN:
        if current == "enrolled":
            raise HTTPException(409, ENROLLED_NOT_WITHDRAWABLE)
        return
    if target == "enrolled":
        raise HTTPException(403, ENROLLED_REFUSED)
    if target not in OVERSEAS_APPLICATION_STAGES:
        raise HTTPException(422, f"'{target}' is not a supported application stage")
    current_index = OVERSEAS_APPLICATION_STAGES.index(current) if current in OVERSEAS_APPLICATION_STAGES else -1
    if OVERSEAS_APPLICATION_STAGES.index(target) <= current_index:
        raise HTTPException(422, f"Cannot move from '{current}' to '{target}' -- an agent can only move an application forward")
```

`AGENT_MAX_STAGE` is enforced because the only stage after it is `enrolled`, which is refused above. Assert that in a test:

```python
def test_only_enrolled_lies_beyond_the_agent_maximum():
    from app.services.agent_applications import AGENT_MAX_STAGE, OVERSEAS_APPLICATION_STAGES

    assert OVERSEAS_APPLICATION_STAGES[OVERSEAS_APPLICATION_STAGES.index(AGENT_MAX_STAGE) + 1:] == ["enrolled"]
```

Add that test to `test_agn_008_status.py`.

- [ ] **Step 5: Write the router PATCH and `/status`**

```python
async def _refuse_closed(db: AsyncSession, user: User, item) -> None:
    """A15 then A1: an archived student's applications and a withdrawn application are read-only."""
    record = await owner_record(db, user, item)
    if record is not None and record.status == "archived":
        raise HTTPException(409, ARCHIVED)
    if item.status == WITHDRAWN:
        raise HTTPException(409, WITHDRAWN_REFUSED)


@router.patch("/{application_id}")
async def update_application(application_id: UUID, payload: AgentApplicationUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    item = await _locked(db, user, membership, application_id)
    await _refuse_closed(db, user, item)
    changes = payload.model_dump(exclude_unset=True)
    changed = sorted(k for k, v in changes.items() if getattr(item, k) != v)
    if "course_id" in changed:
        await check_course(db, item.university_id, changes["course_id"])
        if await duplicate_exists(db, agent_student_id=item.agent_student_id, student_id=item.student_id, university_id=item.university_id, course_id=changes["course_id"], exclude_id=item.id):
            raise HTTPException(409, DUPLICATE)
    for key in changed:
        setattr(item, key, changes[key])
    if changed:
        if "next_action" in changed:  # the existing PATCH's rule: a next-action change is part of the status timeline
            db.add(ApplicationStatusHistory(application_id=item.id, from_status=item.status, to_status=item.status, next_action=item.next_action, changed_by_id=user.id))
        _audit(db, user, "update", item.id, {"fields": changed})
    await db.commit()
    if changed:
        _log("agent_application_updated", membership, user, item.id, fields=changed)
    return {"application": await detail(db, user, item)}


@router.post("/{application_id}/status")
async def change_status(application_id: UUID, payload: AgentApplicationStatus, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    item = await _locked(db, user, membership, application_id)
    await _refuse_closed(db, user, item)
    if payload.expected_status is not None and payload.expected_status != item.status:
        raise HTTPException(409, STALE)
    check_transition(item.status, payload.to_status)
    old = item.status
    item.status = payload.to_status
    if payload.next_action is not None:
        item.next_action = payload.next_action
    db.add(ApplicationStatusHistory(application_id=item.id, from_status=old, to_status=item.status, next_action=item.next_action, notes=payload.notes, changed_by_id=user.id))
    withdrawn = item.status == WITHDRAWN
    _audit(db, user, "withdraw" if withdrawn else "advance", item.id, {"from_status": old, "to_status": item.status})
    await db.commit()
    _log("agent_application_withdrawn" if withdrawn else "agent_application_advanced", membership, user, item.id, from_status=old, to_status=item.status)
    return {"application": await detail(db, user, item)}
```

Add the imports: `AgentApplicationStatus, AgentApplicationUpdate` from schemas, and `STALE, WITHDRAWN, WITHDRAWN_REFUSED, check_transition, owner_record` from the service.

- [ ] **Step 6: Add the withdrawn guard to the existing endpoints**

In `apps/api/app/api/workflows.py`.

`update_overseas_application`, right after `changes = payload.model_dump(exclude_unset=True)`:

```python
    # AGN-008 (A1): `withdrawn` is terminal -- no generic status write revives it (nothing set it before AGN-008).
    if "status" in changes and item.status == WITHDRAWN:
        raise HTTPException(409, "This application is withdrawn")
```

`advance_overseas_application`, right after `item = await _assigned_application(...)`:

```python
    if item.status == WITHDRAWN:  # AGN-008 (A1): otherwise index -1 would let any target revive it
        raise HTTPException(409, "This application is withdrawn")
```

- [ ] **Step 7: Add the activity actions**

In `apps/api/app/services/staff_activity.py`, add to `STAFF_ACTIVITY_ACTIONS`, after `"overseas.application.create",`:

```python
    "overseas.application.update",
    "overseas.application.advance",
    "overseas.application.withdraw",
```

- [ ] **Step 8: Run the tests and confirm they pass**

Run: `API_TEST tests/test_agn_008_edit.py tests/test_agn_008_status.py tests/test_agn_008_read.py tests/test_agn_008_create.py tests/test_ovs_003_eligibility.py tests/test_ovs_004_status_tracking.py tests/test_agn_021_activity.py`
Expected: PASS. If an AGN-021 test pins the exact allow-list tuple, it fails here. Update that assertion in Task 8, Step 3, and record it as a requirement-driven edit.

- [ ] **Step 9: Refactor and re-run**

Route handlers should hold no business rule that the service doesn't own, other than the order of calls. Re-run Step 8.

- [ ] **Step 10: Commit**

```bash
git add apps/api/app/services/agent_applications.py apps/api/app/api/agent_applications.py apps/api/app/api/workflows.py apps/api/app/services/staff_activity.py apps/api/tests/test_agn_008_edit.py apps/api/tests/test_agn_008_status.py
git commit -m "feat(agn-008): edit, forward-only status, withdraw; withdrawn is terminal on every path"
```

---

### Task 8: Matrix, activity and security abuse cases; backend checkpoint

**Files:**
- Modify: `apps/api/tests/test_agn_003_matrix.py` (docstring + `BOTH_ALLOWED` + `_world` ids)
- Modify: `apps/api/tests/test_agn_021_activity.py` (the new actions)
- Create: `apps/api/tests/test_agn_008_security.py`

- [ ] **Step 1: Update the matrix**

This is a requirement-driven edit, recorded in DEC-SCOPE-050. Edit the docstring so that the sentence about N/A rows reads: "Rows with no route for any agent (Staff Performance, CRM Settings) are N/A and have nothing to call; Edit Application and Change Application Status became enforced rows with AGN-008 (DEC-SCOPE-050)."

In `_world`, add after `archived = ...`:

```python
    from tests.agn008_helpers import mk_application  # noqa: PLC0415 -- move to the top import block

    record_app = await mk_application(db_session, agent=ctx["master"], university=other_university, record=record)
```

Then add `"record_app": record_app.id` to `ids`, and move the import to the top import block.

Append to `BOTH_ALLOWED`:

```python
    ("Create Application", "post", "/api/v1/workflows/overseas/agent/crm/applications", {"agent_student_id": "{record}", "university_id": "{university}", "intake": "Fall 2027"}, 201),
    ("View Applications", "get", "/api/v1/workflows/overseas/agent/crm/applications", None, 200),
    ("View Applications", "get", "/api/v1/workflows/overseas/agent/crm/applications/{record_app}", None, 200),
    ("Edit Application", "patch", "/api/v1/workflows/overseas/agent/crm/applications/{record_app}", {"intake": "Spring 2028"}, 200),
    ("Change Application Status", "post", "/api/v1/workflows/overseas/agent/crm/applications/{record_app}/status", {"to_status": "eligibility_evaluation"}, 200),
```

- [ ] **Step 2: Write `test_agn_008_security.py`**

It covers the §7 abuse cases. Each case asserts the code and that no history, audit or commission row was written.

```python
"""AGN-008 AC17 -- the spec §7 abuse cases. Each asserts the stated code AND that nothing was written."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentCommission, AgentOrgMember, ApplicationStatusHistory, AuditLog, OverseasApplication
from tests.agn001_helpers import client_for, mk_user
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import APPS, agency_world, mk_application


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    return w


async def _nothing_written(db, app_id):
    for model, column in ((ApplicationStatusHistory, ApplicationStatusHistory.application_id), (AgentCommission, AgentCommission.application_id)):
        assert await db.scalar(select(func.count()).select_from(model).where(column == app_id)) == 0
    assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(app_id))) == 0


@pytest.mark.asyncio
async def test_staff_cannot_reach_another_staff_members_application(db_session, world):  # abuse 1
    async with client_for(world["other_staff"]["user"].email) as c:
        for call in (c.get(f"{APPS}/{world['app'].id}"), c.patch(f"{APPS}/{world['app'].id}", json={"intake": "X"}), c.post(f"{APPS}/{world['app'].id}/status", json={"to_status": "offer"})):
            assert (await call).status_code == 404
    await _nothing_written(db_session, world["app"].id)


@pytest.mark.asyncio
async def test_other_org_cannot_post_this_orgs_student(db_session, world):  # abuse 2
    async with client_for(world["other"]["master"].email) as c:
        r = await c.post(APPS, json={"agent_student_id": str(world["record"].id), "university_id": str(world["university"].id), "intake": "Fall"})
    assert r.status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(OverseasApplication).where(OverseasApplication.agent_id == world["other"]["master"].id)) == 0


@pytest.mark.asyncio
async def test_agent_cannot_set_enrolled(db_session, world):  # abuse 3
    async with client_for(world["master"].email) as c:
        assert (await c.post(f"{APPS}/{world['app'].id}/status", json={"to_status": "enrolled"})).status_code == 403
    await _nothing_written(db_session, world["app"].id)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"agent_id": str(uuid.uuid4())}, {"status": "enrolled"}, {"university_id": str(uuid.uuid4())}, {"student_id": str(uuid.uuid4())}, {"school_student_id": str(uuid.uuid4())}])
async def test_mass_assignment_is_422(db_session, world, body):  # abuse 4
    async with client_for(world["master"].email) as c:
        assert (await c.patch(f"{APPS}/{world['app'].id}", json=body)).status_code == 422
    await _nothing_written(db_session, world["app"].id)


@pytest.mark.asyncio
async def test_deactivated_staff_is_refused(db_session, world):  # abuse 8
    member = await db_session.get(AgentOrgMember, world["staff"]["member"].id, populate_existing=True)
    async with client_for(world["staff"]["user"].email) as c:
        member.status = "deactivated"
        user = await db_session.get(type(world["staff"]["user"]), world["staff"]["user"].id, populate_existing=True)
        user.active = False
        await db_session.commit()
        r = await c.get(APPS)
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["counselor", "university_rep", "overseas_admin"])
async def test_other_roles_are_refused(db_session, world, role):  # abuse 9
    user = await mk_user(db_session, role=role)
    async with client_for(user.email) as c:
        assert (await c.post(f"{APPS}/{world['app'].id}/status", json={"to_status": "offer"})).status_code == 403
    await _nothing_written(db_session, world["app"].id)


@pytest.mark.asyncio
async def test_responses_never_carry_internal_ids_or_contact_details(world):
    async with client_for(world["master"].email) as c:
        listing = (await c.get(APPS)).json()["items"]
        one = (await c.get(f"{APPS}/{world['app'].id}")).json()["application"]
    for body in (*listing, one):
        assert not {"agent_id", "student_id", "counselor_id", "school_student_id", "email", "phone"} & set(body)
```

Abuse cases 5 (stale), 6 (throttle) and 7 (archived) are pinned in `test_agn_008_status.py`, `test_agn_008_create.py` and `test_agn_008_edit.py`. List them in this file's docstring by test name.

- [ ] **Step 3: Update `test_agn_021_activity.py`**

Add one test where a staff member edits, advances and withdraws an agent application. The Master's activity page must then show the three actions with subject `"<record name> — <university>"`:

```python
@pytest.mark.asyncio
async def test_agent_application_actions_appear_with_the_no_login_student(db_session):
    from tests.agn008_helpers import APPS, agency_world, mk_application

    w = await agency_world(db_session)
    app = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    async with client_for(w["staff"]["user"].email) as s:
        await s.patch(f"{APPS}/{app.id}", json={"intake": "Spring 2028"})
        await s.post(f"{APPS}/{app.id}/status", json={"to_status": "offer"})
        await s.post(f"{APPS}/{app.id}/status", json={"to_status": "withdrawn"})
    async with client_for(w["master"].email) as m:
        items = (await m.get(f"/api/v1/workflows/overseas/agent/team/staff/{w['staff']['member'].id}/activity")).json()["items"]
    got = [(i["action"], i["subject"]) for i in items[:3]]
    subject = f"{w['record'].full_name} — {w['university'].name}"
    assert got == [("overseas.application.withdraw", subject), ("overseas.application.advance", subject), ("overseas.application.update", subject)]
```

Use the file's existing imports (`client_for`). If an existing assertion pins `STAFF_ACTIVITY_ACTIONS` exactly, extend it with the three names. That is a requirement-driven edit.

- [ ] **Step 4: Run them and confirm the expected parts fail first**

Run: `API_TEST tests/test_agn_003_matrix.py tests/test_agn_021_activity.py tests/test_agn_008_security.py`
The new matrix rows, security tests and activity test exercise already-built behaviour, so they should pass. If any fails, it is a real defect. Fix it in the owning task's code. Do not weaken the test.

- [ ] **Step 5: Backend checkpoint (the lite set)**

Run:

```
API_TEST tests/test_agn_008_migration.py tests/test_agn_008_null_owner.py tests/test_agn_008_schemas.py tests/test_agn_008_read.py tests/test_agn_008_create.py tests/test_agn_008_edit.py tests/test_agn_008_status.py tests/test_agn_008_security.py tests/test_agn_003_matrix.py tests/test_agn_021_activity.py tests/test_agn_004_staff_scope.py tests/test_agn_004_students.py tests/test_agn_004_student_actions.py tests/test_agn_001_tenancy.py tests/test_agn_001_team.py tests/test_agn_002_staff.py tests/test_agn_003_verify.py tests/test_agn_005_qa_fixes.py tests/test_agt_002_referrals.py tests/test_agt_003_commission_accrual.py tests/test_agt_004_commission_payout.py tests/test_ovs_002_application.py tests/test_ovs_003_eligibility.py tests/test_ovs_004_status_tracking.py tests/test_ovs_005_documents.py tests/test_uni_001_university_rep_portal.py tests/test_rpt_002_overseas_reporting.py tests/test_visa_001_checklist.py tests/test_visa_003_status.py tests/test_sch_010_overseas_bridge.py tests/test_cns_001_counselor_workspace.py
```

Expected: 0 failures. Record the pass count. The full suite is the owner's.

- [ ] **Step 6: Commit**

```bash
git add apps/api/tests/test_agn_003_matrix.py apps/api/tests/test_agn_021_activity.py apps/api/tests/test_agn_008_security.py
git commit -m "test(agn-008): §6 matrix rows enforced, activity actions, security abuse cases"
```

---

### Task 9: Web shared library

Before this task, recheck `origin/main`.

**Files:**
- Create: `apps/web/lib/agentApplications.ts`
- Modify: `apps/web/lib/agentStaff.ts` (`ACTIVITY_LABELS`)
- Test: `apps/web/tests/lib/agentApplications.test.ts`

**Interfaces:**
- Produces: `APPLICATIONS_URL`, `STAGES`, `AGENT_MAX_STAGE`, `stageLabel(status)`, `STATUS_GROUPS`, `StatusGroup`, `GROUP_LABELS`, `parseGroup(value)`, `nextStages(current)`, `canWithdraw(current)`, `NearestDeadline`, `deadlineText(nearest, today)`, `todayIso()`, `AgentApplicationItem`, `HistoryEntry`, `AgentApplicationDetail`, `READ_ONLY_TEXT`.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from "vitest";

import { canWithdraw, deadlineText, GROUP_LABELS, nextStages, parseGroup, stageLabel } from "@/lib/agentApplications";
import { activityLabel } from "@/lib/agentStaff";

describe("agent application rules (AGN-008)", () => {
  it("offers only later stages, never past status_tracking", () => {
    expect(nextStages("enquiry")).toEqual(["eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking"]);
    expect(nextStages("visa_documentation")).toEqual(["status_tracking"]);
    expect(nextStages("status_tracking")).toEqual([]);
    expect(nextStages("enrolled")).toEqual([]);
    expect(nextStages("withdrawn")).toEqual([]);
    expect(nextStages("university_review")).toEqual(["enquiry", ...nextStages("enquiry")]); // legacy value = before the first stage
  });

  it("withdraws anything but enrolled or already withdrawn", () => {
    expect(canWithdraw("offer")).toBe(true);
    expect(canWithdraw("enrolled")).toBe(false);
    expect(canWithdraw("withdrawn")).toBe(false);
  });

  it("parses the sidebar filter, falling back to all", () => {
    expect(parseGroup("offer")).toBe("offer");
    expect(parseGroup("rejected")).toBe("all");
    expect(parseGroup(null)).toBe("all");
    expect(GROUP_LABELS.offer).toBe("Offer received");
  });

  it("words deadlines in text, not colour", () => {
    expect(deadlineText(null, "2026-10-02")).toBeNull();
    expect(deadlineText({ kind: "offer", date: "2026-10-01" }, "2026-10-02")).toBe("Offer deadline 2026-10-01 (past)");
    expect(deadlineText({ kind: "application", date: "2026-10-02" }, "2026-10-02")).toBe("Application deadline 2026-10-02 (today)");
    expect(deadlineText({ kind: "application", date: "2026-10-03" }, "2026-10-02")).toBe("Application deadline 2026-10-03 (in 1 day)");
    expect(deadlineText({ kind: "application", date: "2026-10-30" }, "2026-10-02")).toBe("Application deadline 2026-10-30");
  });

  it("labels stages and the new activity actions", () => {
    expect(stageLabel("visa_documentation")).toBe("Visa documentation");
    expect(stageLabel("withdrawn")).toBe("Withdrawn");
    expect(activityLabel("overseas.application.update")).toBe("Edited an application");
    expect(activityLabel("overseas.application.advance")).toBe("Moved an application forward");
    expect(activityLabel("overseas.application.withdraw")).toBe("Withdrew an application");
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `WEB_TEST tests/lib/agentApplications.test.ts`
Expected: FAIL. `Cannot find module '@/lib/agentApplications'`.

- [ ] **Step 3: Implement the library**

```ts
// AGN-008 (DEC-SCOPE-050): an agency's applications -- the shapes, labels and stage rules the list, detail and forms share. The
// server is the authority (forward-only, enrolled, stale, archived); these only keep the screens from offering a refused action.

export const APPLICATIONS_URL = "/api/v1/workflows/overseas/agent/crm/applications";

export const STAGES = ["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled"] as const;
export const AGENT_MAX_STAGE = "status_tracking";
const STAGE_LABELS: Record<string, string> = {
  enquiry: "Enquiry",
  eligibility_evaluation: "Eligibility evaluation",
  university_selection: "University selection",
  offer: "Offer",
  visa_documentation: "Visa documentation",
  status_tracking: "Status tracking",
  enrolled: "Enrolled",
  withdrawn: "Withdrawn",
};

export function stageLabel(status: string): string {
  return STAGE_LABELS[status] ?? status.replaceAll("_", " ");
}

export const STATUS_GROUPS = ["all", "draft", "submitted", "offer", "visa", "enrolled", "withdrawn"] as const;
export type StatusGroup = (typeof STATUS_GROUPS)[number];
export const GROUP_LABELS: Record<StatusGroup, string> = {
  all: "All applications",
  draft: "Draft",
  submitted: "Submitted",
  offer: "Offer received",
  visa: "Visa",
  enrolled: "Enrolled",
  withdrawn: "Withdrawn",
};

export function parseGroup(value: string | null | undefined): StatusGroup {
  return (STATUS_GROUPS as readonly string[]).includes(value ?? "") ? (value as StatusGroup) : "all";
}

// The stages an agent may move to next: every later stage up to status_tracking (skips allowed, as counselor /advance allows).
export function nextStages(current: string): string[] {
  if (current === "withdrawn" || current === "enrolled") return [];
  const at = (STAGES as readonly string[]).indexOf(current); // a legacy value counts as before the first stage (-1)
  return STAGES.slice(at + 1, STAGES.indexOf(AGENT_MAX_STAGE) + 1);
}

export function canWithdraw(current: string): boolean {
  return current !== "withdrawn" && current !== "enrolled";
}

export type NearestDeadline = { kind: "application" | "offer"; date: string } | null;

export function deadlineText(nearest: NearestDeadline, today: string): string | null {
  if (!nearest) return null;
  const label = nearest.kind === "offer" ? "Offer deadline" : "Application deadline";
  const days = Math.round((Date.parse(nearest.date) - Date.parse(today)) / 86_400_000);
  if (days < 0) return `${label} ${nearest.date} (past)`;
  if (days === 0) return `${label} ${nearest.date} (today)`;
  if (days <= 7) return `${label} ${nearest.date} (in ${days} day${days === 1 ? "" : "s"})`;
  return `${label} ${nearest.date}`;
}

export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export type AgentApplicationItem = {
  id: string;
  agent_student_id: string | null;
  student: string;
  has_login: boolean;
  university: string;
  course: string | null;
  intake: string;
  status: string;
  application_reference: string | null;
  submitted_on: string | null;
  application_deadline: string | null;
  offer_deadline: string | null;
  nearest_deadline: NearestDeadline;
  next_action: string | null;
  updated_at: string;
};
export type HistoryEntry = { from_status: string | null; to_status: string; next_action: string | null; notes: string | null; changed_by: string | null; created_at: string };
export type AgentApplicationDetail = AgentApplicationItem & {
  university_id: string;
  university_slug: string;
  course_id: string | null;
  created_at: string;
  read_only_reason: "withdrawn" | "archived" | null;
  history: HistoryEntry[];
};

export const READ_ONLY_TEXT: Record<"withdrawn" | "archived", string> = {
  withdrawn: "This application is withdrawn, so it can no longer be changed.",
  archived: "This student is archived. Unarchive them on the Students page to change this application.",
};
```

Add to `ACTIVITY_LABELS` in `lib/agentStaff.ts`:

```ts
  "overseas.application.update": "Edited an application",
  "overseas.application.advance": "Moved an application forward",
  "overseas.application.withdraw": "Withdrew an application",
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `WEB_TEST tests/lib/agentApplications.test.ts tests/lib`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/agentApplications.ts apps/web/lib/agentStaff.ts apps/web/tests/lib/agentApplications.test.ts
git commit -m "feat(agn-008): web stage rules, filters, deadline text, activity labels"
```

---

### Task 10: Sidebar filter links

**Files:**
- Create: `apps/web/components/NavGroup.tsx`
- Modify: `apps/web/components/PortalShell.tsx`
- Modify: `apps/web/lib/navigation.ts` (the agent nav)
- Modify: `apps/web/app/globals.css` (`.portal-subnav`)
- Test: `apps/web/tests/components/PortalShell.children.test.tsx`; `apps/web/tests/lib/navigation.agent.test.ts` (one added test)

**Interfaces:**
- Produces: `NavGroup({ item, pathname })`. The agent nav's applications item has `children: NavItem[]` with hrefs `/overseas/agent/applications?status=<group>`.

- [ ] **Step 1: Write the failing tests**

`PortalShell.children.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PortalShell from "@/components/PortalShell";

let search = "status=offer";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/overseas/agent/applications",
  useSearchParams: () => new URLSearchParams(search),
}));

const nav = [
  { href: "/overseas/agent/dashboard", label: "Dashboard" },
  {
    href: "/overseas/agent/applications",
    label: "Applications",
    children: [
      { href: "/overseas/agent/applications?status=draft", label: "Draft" },
      { href: "/overseas/agent/applications?status=offer", label: "Offer received" },
    ],
  },
];

afterEach(cleanup);

describe("PortalShell sidebar filters (AGN-008)", () => {
  it("renders children under their parent and marks the active filter, not the parent", () => {
    search = "status=offer";
    const { container } = render(<PortalShell nav={nav} roleLabel="Agent" userName="A"><p>x</p></PortalShell>);
    const desktop = container.querySelector(".portal-nav") as HTMLElement;
    const group = within(desktop).getByRole("list", { name: "Applications filters" });
    expect(within(group).getByRole("link", { name: "Offer received" })).toHaveAttribute("aria-current", "page");
    expect(within(group).getByRole("link", { name: "Draft" })).not.toHaveAttribute("aria-current");
    expect(within(desktop).getByRole("link", { name: "Applications" })).not.toHaveAttribute("aria-current");
  });

  it("marks the parent when no filter is set", () => {
    search = "";
    const { container } = render(<PortalShell nav={nav} roleLabel="Agent" userName="A"><p>x</p></PortalShell>);
    const desktop = container.querySelector(".portal-nav") as HTMLElement;
    expect(within(desktop).getByRole("link", { name: "Applications" })).toHaveAttribute("aria-current", "page");
  });

  it("lists the filters in the mobile menu after their parent", () => {
    search = "";
    const { container } = render(<PortalShell nav={nav} roleLabel="Agent" userName="A"><p>x</p></PortalShell>);
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const mobile = container.querySelector("#portal-mobile-nav-panel") as HTMLElement;
    const names = within(mobile).getAllByRole("link").map((a) => a.textContent);
    expect(names.slice(-3)).toEqual(["Applications", "Applications: Draft", "Applications: Offer received"]);
  });
});
```

In `navigation.agent.test.ts`, add:

```ts
  it("gives Applications the status filters for Masters and staff (AGN-008)", () => {
    const children = (items: ReturnType<typeof agentNavFor>) => items.find((i) => i.href === "/overseas/agent/applications")?.children?.map((c) => c.href.split("=")[1]);
    const expected = ["draft", "submitted", "offer", "visa", "enrolled", "withdrawn"];
    expect(children(agentNavFor(nav, "master"))).toEqual(expected);
    expect(children(agentNavFor(nav, "staff"))).toEqual(expected);
  });
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `WEB_TEST tests/components/PortalShell.children.test.tsx tests/lib/navigation.agent.test.ts tests/components/PortalShell.test.tsx`
Expected: the new tests FAIL (no list "Applications filters"; `children` undefined). The existing tests PASS.

- [ ] **Step 3: Implement the nav children**

In `navigation.ts`, replace the agent line with a definition that keeps the same top-level items and adds children:

```ts
  // AGN-008 (DEC-SCOPE-050 A7): Applications carries the EVID-015 §4 sidebar filters as sub-links (same page, ?status=).
  "overseas/agent": ["dashboard","students","applications","documents","commissions","reports","team"].map(x=>({label:x.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase()),href:`/overseas/agent/${x}`,...(x==="applications"?{children:AGENT_APPLICATION_FILTERS}:{})})),
```

Above `PORTAL_NAV`, define:

```ts
import { GROUP_LABELS, STATUS_GROUPS } from "./agentApplications";
const AGENT_APPLICATION_FILTERS: NavItem[] = STATUS_GROUPS.filter((g) => g !== "all").map((g) => ({ label: GROUP_LABELS[g], href: `/overseas/agent/applications?status=${g}` }));
```

The existing tests compare `.map(i => i.href)` and `toEqual(nav)` for Masters, so they still pass.

`NavGroup.tsx`:

```tsx
"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import type { NavItem } from "@/lib/navigation";

// AGN-008: a parent link with indented sub-links that differ only in their query string (the agency Applications filters). Only
// rendered for an item that has `children`, so every other portal's sidebar is unchanged.
function matches(href: string, pathname: string, params: URLSearchParams): boolean {
  const target = new URL(href, "http://nav.local");
  if (target.pathname !== pathname) return false;
  for (const [key, value] of target.searchParams) if (params.get(key) !== value) return false;
  return true;
}

export default function NavGroup({ item, pathname }: { item: NavItem; pathname: string }) {
  const params = useSearchParams();
  const children = item.children ?? [];
  const active = children.find((child) => matches(child.href, pathname, params));
  return (
    <>
      <Link href={item.href} aria-current={pathname === item.href && !active ? "page" : undefined}>
        {item.label}
      </Link>
      <ul className="portal-subnav" aria-label={`${item.label} filters`}>
        {children.map((child) => (
          <li key={child.href}>
            <Link href={child.href} aria-current={child === active ? "page" : undefined}>
              {child.label}
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
```

`PortalShell.tsx`: import `{ Fragment, Suspense }` and `NavGroup`. Replace the `nav.map(...)` inside `.portal-nav` with:

```tsx
{nav.map(x=>x.children?.length?<Suspense key={x.href} fallback={<Link href={x.href}>{x.label}</Link>}><NavGroup item={x} pathname={pathname}/></Suspense>:<Link key={x.href} href={x.href} aria-current={pathname===x.href?"page":undefined}>{x.label}</Link>)}
```

Replace the `MobileNavToggle` nav prop's `...nav` with `...nav.flatMap(x=>[x,...(x.children??[]).map(c=>({href:c.href,label:`${x.label}: ${c.label}`}))])`.

`globals.css`: append `.portal-subnav{list-style:none;margin:0 0 4px;padding:0 0 0 12px;display:grid;gap:2px}.portal-subnav a{font-size:13px}`.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `WEB_TEST tests/components/PortalShell.children.test.tsx tests/components/PortalShell.test.tsx tests/lib/navigation.agent.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/NavGroup.tsx apps/web/components/PortalShell.tsx apps/web/lib/navigation.ts apps/web/app/globals.css apps/web/tests/components/PortalShell.children.test.tsx apps/web/tests/lib/navigation.agent.test.ts
git commit -m "feat(agn-008): agency sidebar application filters with aria-current"
```

---

### Task 11: Create panel — agency students (server search), dates, new route

**Files:**
- Modify: `apps/web/components/AgentApplicationCreatePanel.tsx`
- Modify: `apps/web/tests/components/Enh031ExistingPickers.test.tsx`. This is a requirement-driven edit: the student source changes, while the option text and ids stay the same.
- Test: `apps/web/tests/components/AgentApplicationCreatePanel.test.tsx`

**Interfaces:**
- Produces: `AgentApplicationCreatePanel({ onCreated }: { onCreated?: () => void })`.
- Kept: ids `#agent-app-student`, `#agent-app-student-list`, `#agent-app-university`; combobox name "Linked student"; button "Create application"; success text "Application created.".

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationCreatePanel from "@/components/AgentApplicationCreatePanel";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 20, offset: 0 });
const students = [
  { id: "r1", has_login: false, full_name: "Asha Rao", email: null, status: "active" },
  { id: "r2", has_login: true, full_name: "Ravi Iyer", email: "ravi@example.local", status: "active" },
];

function stub(post: (body: Record<string, unknown>) => Response) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/v1/workflows/overseas/agent/crm/students")) return Promise.resolve(json(page(students)));
    if (url === "/api/v1/public/universities") return Promise.resolve(json([{ id: "u1", slug: "u1", name: "Uni One", city: "X" }]));
    if (url.startsWith("/api/v1/public/universities/")) return Promise.resolve(json({ courses: [] }));
    if (init?.method === "POST") return Promise.resolve(post(JSON.parse(String(init.body))));
    return Promise.resolve(json({}));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function pick(name: string) {
  const input = await screen.findByRole("combobox", { name: "Linked student" });
  fireEvent.focus(input);
  fireEvent.click(await screen.findByRole("option", { name }));
}

describe("AgentApplicationCreatePanel (AGN-008)", () => {
  it("offers agency students with and without a login", async () => {
    stub(() => json({}, 201));
    render(<AgentApplicationCreatePanel />);
    const input = await screen.findByRole("combobox", { name: "Linked student" });
    fireEvent.focus(input);
    expect(await screen.findByRole("option", { name: "Asha Rao — no login" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Ravi Iyer — ravi@example.local" })).toBeInTheDocument();
  });

  it("posts the record id and the new fields, then reports and resets", async () => {
    const onCreated = vi.fn();
    const fetchMock = stub(() => json({ application: { id: "a1" } }, 201));
    render(<AgentApplicationCreatePanel onCreated={onCreated} />);
    await pick("Asha Rao — no login");
    fireEvent.change(screen.getByLabelText("University (required)"), { target: { value: "u1" } });
    fireEvent.change(screen.getByLabelText("Application ID"), { target: { value: "UCAS-1" } });
    fireEvent.change(screen.getByLabelText("Offer deadline"), { target: { value: "2027-01-15" } });
    fireEvent.click(screen.getByRole("button", { name: "Create application" }));
    const status = await screen.findByText("Application created.");
    expect(status).toHaveFocus();
    expect(onCreated).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "POST")!;
    expect(url).toBe("/api/v1/workflows/overseas/agent/crm/applications");
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({ agent_student_id: "r1", university_id: "u1", application_reference: "UCAS-1", offer_deadline: "2027-01-15", submitted_on: null });
  });

  it("shows the server's 409 in an alert and keeps the entry", async () => {
    stub(() => json({ detail: "An application for this university/course already exists" }, 409));
    render(<AgentApplicationCreatePanel />);
    await pick("Asha Rao — no login");
    fireEvent.change(screen.getByLabelText("University (required)"), { target: { value: "u1" } });
    fireEvent.change(screen.getByLabelText("Application ID"), { target: { value: "KEEP" } });
    fireEvent.click(screen.getByRole("button", { name: "Create application" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
    expect(screen.getByLabelText("Application ID")).toHaveValue("KEEP");
  });

  it("limits the submission date to today", async () => {
    stub(() => json({}, 201));
    render(<AgentApplicationCreatePanel />);
    await screen.findByRole("combobox", { name: "Linked student" });
    expect(screen.getByLabelText("Submitted on")).toHaveAttribute("max");
  });
});
```

Update `Enh031ExistingPickers.test.tsx` → "the agent's Create application picker empties after a successful create":
- Stub `url.startsWith("/api/v1/workflows/overseas/agent/crm/students")` → `json({ items: [{ id: "s1", has_login: true, full_name: "Asha Rao", email: "asha@example.local", status: "active" }], total: 1, limit: 20, offset: 0 })`.
- Pick with `fireEvent.click(await screen.findByRole("option", { name: "Asha Rao — asha@example.local" }))`.
- Use the label "University (required)".
- The rest is unchanged.

- [ ] **Step 2: Run them and confirm they fail**

Run: `WEB_TEST tests/components/AgentApplicationCreatePanel.test.tsx tests/components/Enh031ExistingPickers.test.tsx`
Expected: FAIL. There are no "no login" options, and the label is still "University".

- [ ] **Step 3: Rewrite the panel**

`AgentApplicationCreatePanel.tsx`:

```tsx
"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import SearchableSelect from "@/components/SearchableSelect";
import { isPage, sendJson } from "@/lib/apiErrors";
import { APPLICATIONS_URL, todayIso } from "@/lib/agentApplications";
import { AgentStudentItem, RECORDS_URL } from "@/lib/agentStudents";
import type { LookupPage } from "@/lib/lookups";
import type { University } from "@/lib/types";

type Course = { id: string; title: string; level: string };

// AGN-008 (DEC-SCOPE-050): create an application for any of the agency's students -- with or without a login -- searched on the
// server (AGN-004's records list), so a large agency is never truncated. University/course reuse OVS-002's cascading picker. Ids,
// the "Linked student" name and the success text are kept for ENH-031's specs.
async function searchStudents(q: string, signal: AbortSignal): Promise<LookupPage> {
  const params = new URLSearchParams({ limit: "20" });
  if (q) params.set("q", q);
  const response = await fetch(`${RECORDS_URL}?${params}`, { signal });
  const data = await response.json().catch(() => null);
  if (!response.ok || !isPage<AgentStudentItem>(data)) throw new Error(`Student search failed (${response.status})`);
  return {
    items: data.items.map((s) => ({ id: s.id, label: s.full_name, detail: s.has_login ? s.email : "no login" })),
    truncated: data.total > data.items.length,
  };
}

const OPTIONAL = [
  ["application_reference", "Application ID", "text"],
  ["submitted_on", "Submitted on", "date"],
  ["application_deadline", "Application deadline", "date"],
  ["offer_deadline", "Offer deadline", "date"],
] as const;

export default function AgentApplicationCreatePanel({ onCreated }: { onCreated?: () => void }) {
  const [universities, setUniversities] = useState<University[] | null>(null);
  const [studentId, setStudentId] = useState("");
  const [universityId, setUniversityId] = useState("");
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [courseId, setCourseId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [formVersion, setFormVersion] = useState(0); // ENH-031: bumped after a create so the picker remounts empty
  const messageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/public/universities")
      .then((res) => (res.ok ? res.json() : []))
      .then((data: University[]) => !cancelled && setUniversities(data))
      .catch(() => !cancelled && setUniversities([]));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setCourseId("");
    if (!universityId) return setCourses(null);
    const university = universities?.find((u) => u.id === universityId);
    if (!university) return;
    let cancelled = false;
    fetch(`/api/v1/public/universities/${university.slug}`)
      .then((res) => (res.ok ? res.json() : { courses: [] }))
      .then((data) => !cancelled && setCourses(data.courses || []))
      .catch(() => !cancelled && setCourses([]));
    return () => {
      cancelled = true;
    };
  }, [universityId, universities]);

  useEffect(() => {
    if (message) messageRef.current?.focus();
  }, [message]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const optional = Object.fromEntries(OPTIONAL.map(([key]) => [key, String(form.get(key) ?? "").trim() || null]));
    setBusy(true);
    setMessage(null);
    const outcome = await sendJson(APPLICATIONS_URL, "POST", {
      agent_student_id: studentId,
      university_id: universityId,
      course_id: courseId || null,
      intake: String(form.get("intake") ?? "").trim(),
      ...optional,
    });
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: outcome.message, failed: true });
    setMessage({ text: "Application created.", failed: false });
    formElement.reset();
    setStudentId("");
    setFormVersion((v) => v + 1);
    setUniversityId("");
    setCourses(null);
    onCreated?.();
  }

  if (universities === null) {
    return (
      <div className="action-card">
        <h3>Create application</h3>
        <p className="muted">Loading universities…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Create application</h3>
      <form className="form" onSubmit={submit} aria-label="Create application">
        <SearchableSelect key={formVersion} id="agent-app-student" label="Linked student" required noun="student" search={searchStudents} onChange={(option) => setStudentId(option?.id ?? "")} />
        <div className="field">
          <label htmlFor="agent-app-university">University (required)</label>
          <select id="agent-app-university" value={universityId} onChange={(event) => setUniversityId(event.target.value)} required>
            <option value="">Select university</option>
            {universities.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name} -- {u.city}
              </option>
            ))}
          </select>
        </div>
        {universityId && (
          <div className="field">
            <label htmlFor="agent-app-course">Course (optional)</label>
            <select id="agent-app-course" value={courseId} onChange={(event) => setCourseId(event.target.value)} disabled={courses === null}>
              <option value="">Undecided / any course</option>
              {(courses || []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title} ({c.level})
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="field">
          <label htmlFor="agent-app-intake">Intake (required)</label>
          <input id="agent-app-intake" name="intake" defaultValue="Next intake" maxLength={80} required />
        </div>
        {OPTIONAL.map(([key, label, type]) => (
          <div className="field" key={key}>
            <label htmlFor={`agent-app-${key}`}>{label}</label>
            <input
              id={`agent-app-${key}`}
              name={key}
              type={type}
              maxLength={type === "text" ? 140 : undefined}
              max={key === "submitted_on" ? todayIso() : undefined}
              aria-describedby={key === "submitted_on" ? "agent-app-submitted-hint" : undefined}
            />
            {key === "submitted_on" && (
              <small id="agent-app-submitted-hint" className="muted">
                Leave empty until submitted.
              </small>
            )}
          </div>
        ))}
        <button className="btn" disabled={busy || !studentId || !universityId}>
          {busy ? "Creating…" : "Create application"}
        </button>
      </form>
      {message && (
        <div ref={messageRef} tabIndex={-1} className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
    </div>
  );
}
```

The test expects the button name "Create application" exactly, while the button shows "Creating…" while busy. ENH-031 e2e uses `/Create application/`, which is fine. The form's `aria-label="Create application"` gives it the role `form`. If that collides with `getByRole("button", { name: ... })` queries, remove the `aria-label`. Buttons are not affected by a form's name.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `WEB_TEST tests/components/AgentApplicationCreatePanel.test.tsx tests/components/Enh031ExistingPickers.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/AgentApplicationCreatePanel.tsx apps/web/tests/components/AgentApplicationCreatePanel.test.tsx apps/web/tests/components/Enh031ExistingPickers.test.tsx
git commit -m "feat(agn-008): create applications for any agency student, with ID, dates and deadlines"
```

---

### Task 12: Detail, edit and status components

**Files:**
- Create: `apps/web/components/AgentApplicationDetail.tsx`, `AgentApplicationEditForm.tsx`, `AgentApplicationStatusForm.tsx`
- Test: `apps/web/tests/components/AgentApplicationDetail.test.tsx`

**Interfaces:**
- Produces:
  - `AgentApplicationDetail({ id, onChanged, onClose })`, where `onChanged(detail: AgentApplicationDetail)`.
  - `AgentApplicationEditForm({ detail, onSaved, onFailed, onCancel })`.
  - `AgentApplicationStatusForm({ detail, onSaved, onFailed })`.
  - `onSaved(detail, message)` and `onFailed(message, status?)`.

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationDetail from "@/components/AgentApplicationDetail";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const detail = (over: Record<string, unknown> = {}) => ({
  id: "a1", agent_student_id: "r1", student: "Asha Rao", has_login: false, university: "Uni One", university_id: "u1", university_slug: "u1",
  course: null, course_id: null, intake: "Fall 2027", status: "offer", application_reference: "UCAS-1", submitted_on: "2026-09-01",
  application_deadline: null, offer_deadline: "2027-01-15", nearest_deadline: { kind: "offer", date: "2027-01-15" }, next_action: "Send deposit",
  updated_at: "", created_at: "", read_only_reason: null,
  history: [{ from_status: null, to_status: "enquiry", next_action: null, notes: null, changed_by: "Master One", created_at: "2026-09-01T10:00:00Z" }],
  ...over,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentApplicationDetail (AGN-008)", () => {
  it("loads, focuses its heading, and shows fields and history", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ application: detail() }))));
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    const heading = await screen.findByRole("heading", { name: "Asha Rao — Uni One" });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(screen.getByText("UCAS-1")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Status history" })).getByText(/Enquiry/)).toBeInTheDocument();
  });

  it("offers only later stages up to status tracking", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ application: detail() }))));
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    const select = await screen.findByLabelText("Move to");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Visa documentation", "Status tracking"]);
  });

  it("sends the displayed status as expected_status and reports success", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn((_: string, init?: RequestInit) => Promise.resolve(json({ application: init?.method === "POST" ? detail({ status: "visa_documentation" }) : detail() })));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationDetail id="a1" onChanged={onChanged} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Update status" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Status updated to Visa documentation.");
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body))).toMatchObject({ to_status: "visa_documentation", expected_status: "offer" });
    expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "visa_documentation" }));
  });

  it("asks before withdrawing, and Escape cancels", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ application: detail() }))));
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Withdraw application" }));
    const confirm = screen.getByRole("group", { name: "Confirm withdrawal" });
    fireEvent.keyDown(confirm, { key: "Escape" });
    expect(screen.queryByRole("group", { name: "Confirm withdrawal" })).toBeNull();
    expect(screen.getByRole("button", { name: "Withdraw application" })).toHaveFocus();
  });

  it("on a 409 shows the server's words and reloads the application", async () => {
    let posted = false;
    const fetchMock = vi.fn((_: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posted = true;
        return Promise.resolve(json({ detail: "This application changed since you opened it -- reload to see its current status" }, 409));
      }
      return Promise.resolve(json({ application: posted ? detail({ status: "withdrawn", read_only_reason: "withdrawn" }) : detail() }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Update status" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed since you opened it");
    expect(await screen.findByText("This application is withdrawn, so it can no longer be changed.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
  });

  it("edits, saving only changed fields, and Cancel returns focus to Edit", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/public/universities/")) return Promise.resolve(json({ courses: [] }));
      if (init?.method === "PATCH") return Promise.resolve(json({ application: detail({ intake: "Spring 2028" }) }));
      return Promise.resolve(json({ application: detail() }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Edit" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Intake (required)"), { target: { value: "Spring 2028" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved.");
    const patch = fetchMock.mock.calls.find(([, i]) => i?.method === "PATCH")!;
    expect(JSON.parse(String(patch[1]!.body))).toEqual({ intake: "Spring 2028" });
  });

  it("says when the application is gone", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ detail: "Application not found" }, 404))));
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    expect(await screen.findByText("This application is no longer available.")).toBeInTheDocument();
  });

  it("keeps Edit but hides the status control for an enrolled application", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ application: detail({ status: "enrolled" }) }))));
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    expect(await screen.findByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Move to")).toBeNull();
    expect(screen.queryByRole("button", { name: "Withdraw application" })).toBeNull();
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `WEB_TEST tests/components/AgentApplicationDetail.test.tsx`
Expected: FAIL with a module-not-found error.

- [ ] **Step 3: Write `AgentApplicationStatusForm.tsx`**

```tsx
"use client";

import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { sendJson } from "@/lib/apiErrors";
import { AgentApplicationDetail, APPLICATIONS_URL, canWithdraw, nextStages, stageLabel } from "@/lib/agentApplications";

type Props = { detail: AgentApplicationDetail; onSaved: (d: AgentApplicationDetail, message: string) => void; onFailed: (message: string, status?: number) => void };

// AGN-008 A4: forward to a later stage (up to status tracking) or withdraw; the displayed status travels as `expected_status`, so a
// stale screen gets the server's 409 instead of acting on an application someone else just changed.
export default function AgentApplicationStatusForm({ detail, onSaved, onFailed }: Props) {
  const options = nextStages(detail.status);
  const [target, setTarget] = useState(options[0] ?? "");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const withdrawRef = useRef<HTMLButtonElement>(null);

  async function send(to: string) {
    setBusy(true);
    const outcome = await sendJson(`${APPLICATIONS_URL}/${detail.id}/status`, "POST", { to_status: to, expected_status: detail.status, notes: notes.trim() || null });
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) return onFailed(outcome.message, outcome.status);
    const next = (outcome.data as { application?: AgentApplicationDetail }).application;
    if (!next) return onFailed("The change could not be confirmed. Reload to see the current status.");
    setNotes("");
    onSaved(next, to === "withdrawn" ? "Application withdrawn." : `Status updated to ${stageLabel(to)}.`);
  }

  function cancelConfirm() {
    setConfirming(false);
    requestAnimationFrame(() => withdrawRef.current?.focus());
  }

  if (!options.length && !canWithdraw(detail.status)) return null;
  return (
    <div>
      <h5>Change status</h5>
      {options.length > 0 && (
        <form className="form" onSubmit={(event: FormEvent) => (event.preventDefault(), send(target))}>
          <div className="field">
            <label htmlFor={`move-${detail.id}`}>Move to</label>
            <select id={`move-${detail.id}`} value={target} onChange={(event) => setTarget(event.target.value)}>
              {options.map((stage) => (
                <option key={stage} value={stage}>
                  {stageLabel(stage)}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={`notes-${detail.id}`}>Note (optional)</label>
            <textarea id={`notes-${detail.id}`} value={notes} maxLength={2000} onChange={(event) => setNotes(event.target.value)} />
          </div>
          <button className="btn small" disabled={busy || !target}>
            {busy ? "Updating…" : "Update status"}
          </button>
        </form>
      )}
      {canWithdraw(detail.status) &&
        (confirming ? (
          <div role="group" aria-label="Confirm withdrawal" onKeyDown={(event: KeyboardEvent) => event.key === "Escape" && cancelConfirm()} style={{ marginTop: 12 }}>
            <p>Withdraw this application? This cannot be undone.</p>
            <div className="actions">
              <button type="button" className="btn small" disabled={busy} onClick={() => send("withdrawn")} autoFocus>
                Yes, withdraw
              </button>
              <button type="button" className="btn ghost small" onClick={cancelConfirm}>
                Keep application
              </button>
            </div>
          </div>
        ) : (
          <button ref={withdrawRef} type="button" className="btn ghost small" style={{ marginTop: 12 }} onClick={() => setConfirming(true)}>
            Withdraw application
          </button>
        ))}
    </div>
  );
}
```

If the withdraw-button focus assertion fails in jsdom because `requestAnimationFrame` has not run, focus synchronously in a `useEffect` keyed on `confirming` instead. Keep the behaviour the test asserts.

- [ ] **Step 4: Write `AgentApplicationEditForm.tsx`**

```tsx
"use client";

import { FormEvent, useEffect, useState } from "react";
import { sendJson } from "@/lib/apiErrors";
import { AgentApplicationDetail, APPLICATIONS_URL, todayIso } from "@/lib/agentApplications";

type Props = {
  detail: AgentApplicationDetail;
  onSaved: (d: AgentApplicationDetail, message: string) => void;
  onFailed: (message: string, status?: number) => void;
  onCancel: () => void;
};
type Course = { id: string; title: string; level: string };
const FIELDS = [
  ["application_reference", "Application ID", "text", 140],
  ["intake", "Intake (required)", "text", 80],
  ["submitted_on", "Submitted on", "date", 0],
  ["application_deadline", "Application deadline", "date", 0],
  ["offer_deadline", "Offer deadline", "date", 0],
  ["next_action", "Next action", "text", 500],
] as const;
type Key = (typeof FIELDS)[number][0] | "course_id";

// AGN-008 A10: everything but the university is editable; only changed fields are sent (null clears).
export default function AgentApplicationEditForm({ detail, onSaved, onFailed, onCancel }: Props) {
  const initial = Object.fromEntries([...FIELDS.map(([k]) => [k, (detail[k] as string | null) ?? ""]), ["course_id", detail.course_id ?? ""]]) as Record<Key, string>;
  const [values, setValues] = useState(initial);
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/v1/public/universities/${detail.university_slug}`)
      .then((res) => (res.ok ? res.json() : { courses: [] }))
      .then((data) => !cancelled && setCourses(data.courses || []))
      .catch(() => !cancelled && setCourses([]));
    return () => {
      cancelled = true;
    };
  }, [detail.university_slug]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const changed = Object.fromEntries(
      (Object.keys(values) as Key[]).filter((k) => values[k].trim() !== initial[k]).map((k) => [k, values[k].trim() || null]),
    );
    if (!Object.keys(changed).length) return onCancel();
    setBusy(true);
    const outcome = await sendJson(`${APPLICATIONS_URL}/${detail.id}`, "PATCH", changed);
    setBusy(false);
    if (!outcome.ok) return onFailed(outcome.message, outcome.status);
    const next = (outcome.data as { application?: AgentApplicationDetail }).application;
    if (!next) return onFailed("The change could not be confirmed. Reload to see the application.");
    onSaved(next, "Saved.");
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Edit application">
      <p className="muted">University: {detail.university}. To change university, withdraw and create a new application.</p>
      <div className="field">
        <label htmlFor={`edit-course-${detail.id}`}>Course (optional)</label>
        <select id={`edit-course-${detail.id}`} value={values.course_id} disabled={courses === null} onChange={(e) => setValues({ ...values, course_id: e.target.value })}>
          <option value="">Undecided / any course</option>
          {(courses ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.title} ({c.level})
            </option>
          ))}
        </select>
      </div>
      {FIELDS.map(([key, label, type, max]) => (
        <div className="field" key={key}>
          <label htmlFor={`edit-${key}-${detail.id}`}>{label}</label>
          <input
            id={`edit-${key}-${detail.id}`}
            type={type}
            value={values[key]}
            required={key === "intake"}
            maxLength={max || undefined}
            max={key === "submitted_on" ? todayIso() : undefined}
            onChange={(e) => setValues({ ...values, [key]: e.target.value })}
          />
        </div>
      ))}
      <div className="actions">
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : "Save"}
        </button>
        <button type="button" className="btn ghost small" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
```

- [ ] **Step 5: Write `AgentApplicationDetail.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AgentApplicationEditForm from "./AgentApplicationEditForm";
import AgentApplicationStatusForm from "./AgentApplicationStatusForm";
import { detailMessage } from "@/lib/apiErrors";
import { AgentApplicationDetail as Detail, APPLICATIONS_URL, deadlineText, READ_ONLY_TEXT, stageLabel, todayIso } from "@/lib/agentApplications";

type Props = { id: string; onChanged: (d: Detail) => void; onClose: () => void };

// AGN-008: one application -- fields, status history, edit and status change. A 409/422 from a write shows the server's words and
// reloads, so the screen always ends on the real state (stale, withdrawn, archived).
export default function AgentApplicationDetail({ id, onChanged, onClose }: Props) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "gone" | "error">("loading");
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const editRef = useRef<HTMLButtonElement>(null);
  const focusHeading = useRef(true);

  const load = useCallback(async () => {
    try {
      const response = await fetch(`${APPLICATIONS_URL}/${id}`);
      const body = await response.json().catch(() => null);
      if (response.status === 404) return setState("gone");
      if (!response.ok || !body?.application) return setState("error");
      setDetail(body.application);
      setState("ready");
    } catch {
      setState("error");
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (state === "ready" && focusHeading.current) {
      focusHeading.current = false;
      headingRef.current?.focus();
    }
  }, [state]);

  function saved(next: Detail, message: string) {
    setDetail(next);
    setEditing(false);
    setNotice({ text: message, failed: false });
    onChanged(next);
  }
  function failed(message: string, status?: number) {
    setNotice({ text: message, failed: true });
    if (status === 404) return setState("gone");
    if (status === 409 || status === 422) load();
  }

  if (state === "loading") return <p className="muted" aria-busy="true">Loading application…</p>;
  if (state === "gone") return <p className="form-error" role="alert">This application is no longer available.</p>;
  if (state === "error" || !detail)
    return (
      <p className="form-error" role="alert">
        {detailMessage(null, "The application could not be loaded.")}{" "}
        <button type="button" className="btn secondary small" onClick={() => (setState("loading"), load())}>
          Retry
        </button>
      </p>
    );

  const title = `${detail.student} — ${detail.university}`;
  const deadline = deadlineText(detail.nearest_deadline, todayIso());
  return (
    <section aria-labelledby={`detail-${id}`} style={{ marginTop: 12 }}>
      <h4 id={`detail-${id}`} ref={headingRef} tabIndex={-1}>
        {title}
      </h4>
      <p>
        <span className={detail.status === "withdrawn" ? "status error" : "badge"}>{stageLabel(detail.status)}</span>
        {deadline && <span className="muted"> · {deadline}</span>}
      </p>
      {notice && (
        <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} aria-live="polite">
          {notice.text}
        </p>
      )}
      {detail.read_only_reason && <p className="muted">{READ_ONLY_TEXT[detail.read_only_reason]}</p>}
      {editing ? (
        <AgentApplicationEditForm detail={detail} onSaved={saved} onFailed={failed} onCancel={() => (setEditing(false), requestAnimationFrame(() => editRef.current?.focus()))} />
      ) : (
        <>
          <dl className="card-stack">
            <dt>Application ID</dt>
            <dd>{detail.application_reference ?? "—"}</dd>
            <dt>Course</dt>
            <dd>{detail.course ?? "Undecided"}</dd>
            <dt>Intake</dt>
            <dd>{detail.intake}</dd>
            <dt>Submitted on</dt>
            <dd>{detail.submitted_on ?? "Not submitted"}</dd>
            <dt>Application deadline</dt>
            <dd>{detail.application_deadline ?? "—"}</dd>
            <dt>Offer deadline</dt>
            <dd>{detail.offer_deadline ?? "—"}</dd>
            <dt>Next action</dt>
            <dd>{detail.next_action ?? "—"}</dd>
          </dl>
          {!detail.read_only_reason && (
            <button ref={editRef} type="button" className="btn secondary small" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
        </>
      )}
      {!detail.read_only_reason && !editing && <AgentApplicationStatusForm key={detail.status} detail={detail} onSaved={saved} onFailed={failed} />}
      <h5>Status history</h5>
      <ol aria-label="Status history">
        {detail.history.map((h, i) => (
          <li key={i}>
            {h.from_status ? `${stageLabel(h.from_status)} → ` : ""}
            {stageLabel(h.to_status)}
            {h.changed_by && ` · ${h.changed_by}`} · {new Date(h.created_at).toLocaleString()}
            {h.notes && <div className="muted">{h.notes}</div>}
          </li>
        ))}
      </ol>
      <button type="button" className="btn ghost small" onClick={onClose}>
        Close
      </button>
    </section>
  );
}
```

The Cancel-focus test runs synchronously. If `requestAnimationFrame` defers the focus in jsdom, focus `editRef` in a `useEffect` keyed on `editing` going false after a cancel, and keep the test unchanged.

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `WEB_TEST tests/components/AgentApplicationDetail.test.tsx`
Expected: PASS.

- [ ] **Step 7: Refactor and re-run**

Each file should stay at or below about 200 lines, with no duplicated fetch or error code (`sendJson`, `detailMessage`). Re-run Step 6.

- [ ] **Step 8: Commit**

```bash
git add apps/web/components/AgentApplicationDetail.tsx apps/web/components/AgentApplicationEditForm.tsx apps/web/components/AgentApplicationStatusForm.tsx apps/web/tests/components/AgentApplicationDetail.test.tsx
git commit -m "feat(agn-008): application detail with history, edit and forward-only status"
```

---

### Task 13: List panel, section, and page wiring

**Files:**
- Create: `apps/web/components/AgentApplicationsPanel.tsx`, `apps/web/components/AgentApplicationsSection.tsx`
- Modify: `apps/web/components/PortalPage.tsx`
- Modify: `apps/web/components/WorkflowPanel.tsx` (remove the create-panel mount: import, const, early-return term, render term)
- Test: `apps/web/tests/components/AgentApplicationsPanel.test.tsx`

**Interfaces:**
- Produces: `AgentApplicationsPanel({ group, reloadKey })` and `AgentApplicationsSection({ user })`.

- [ ] **Step 1: Write the failing test**

```tsx
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationsPanel from "@/components/AgentApplicationsPanel";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const item = (over: Record<string, unknown> = {}) => ({
  id: "a1", agent_student_id: "r1", student: "Asha Rao", has_login: false, university: "Uni One", course: null, intake: "Fall 2027",
  status: "offer", application_reference: "UCAS-1", submitted_on: null, application_deadline: null, offer_deadline: null,
  nearest_deadline: null, next_action: "Send deposit", updated_at: "", ...over,
});
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentApplicationsPanel (AGN-008)", () => {
  it("shows loading, then cards with text status and a no-login tag", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json(page([item()])))));
    render(<AgentApplicationsPanel group="all" reloadKey={0} />);
    expect(screen.getByText("Loading applications…")).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Applications" });
    const card = within(list).getByRole("listitem");
    expect(card).toHaveTextContent("Asha Rao");
    expect(card).toHaveTextContent("Offer");
    expect(card).toHaveTextContent("no login");
  });

  it("requests the filter it is given", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(json(page([]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationsPanel group="visa" reloadKey={0} />);
    await screen.findByText("No applications match this filter.");
    expect(String(fetchMock.mock.calls[0][0])).toContain("status=visa");
    expect(screen.getByRole("link", { name: "Show all applications" })).toHaveAttribute("href", "/overseas/agent/applications");
  });

  it("shows the unfiltered empty state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json(page([])))));
    render(<AgentApplicationsPanel group="all" reloadKey={0} />);
    expect(await screen.findByText(/No applications yet/)).toBeInTheDocument();
  });

  it("shows an error with Retry that refetches", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({ detail: "boom" }, 500)).mockResolvedValue(json(page([item()])));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationsPanel group="all" reloadKey={0} />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
  });

  it("pages with Previous and Next", async () => {
    const many = Array.from({ length: 20 }, (_, i) => item({ id: `a${i}`, student: `S${i}` }));
    const fetchMock = vi.fn((url: string) => Promise.resolve(json(url.includes("offset=20") ? page([item({ id: "z", student: "Last" })], 21, 20) : page(many, 21))));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationsPanel group="all" reloadKey={0} />);
    fireEvent.click(await screen.findByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Last")).toBeInTheDocument();
    expect(screen.getByText("Showing 21–21 of 21")).toBeInTheDocument();
  });

  it("opens the detail under its card and returns focus on Close", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(json(url.includes("/a1") ? { application: { ...item(), university_id: "u1", university_slug: "u1", course_id: null, created_at: "", read_only_reason: null, history: [] } } : page([item()])))));
    render(<AgentApplicationsPanel group="all" reloadKey={0} />);
    const view = await screen.findByRole("button", { name: "View Asha Rao — Uni One" });
    fireEvent.click(view);
    expect(view).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(await screen.findByRole("button", { name: "Close" }));
    expect(view).toHaveFocus();
  });

  it("refetches when reloadKey changes (after a create)", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(json(page([]))));
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(<AgentApplicationsPanel group="all" reloadKey={0} />);
    await screen.findByText(/No applications yet/);
    await act(async () => rerender(<AgentApplicationsPanel group="all" reloadKey={1} />));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `WEB_TEST tests/components/AgentApplicationsPanel.test.tsx`
Expected: FAIL with a module-not-found error.

- [ ] **Step 3: Write `AgentApplicationsPanel.tsx`**

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import AgentApplicationDetail from "./AgentApplicationDetail";
import { detailMessage, isPage, Page } from "@/lib/apiErrors";
import { AgentApplicationDetail as Detail, AgentApplicationItem, APPLICATIONS_URL, deadlineText, GROUP_LABELS, StatusGroup, stageLabel, todayIso } from "@/lib/agentApplications";

const PAGE_SIZE = 20;
const LOAD_FAILED = "The applications could not be loaded.";

// AGN-008: the agency's applications for one sidebar filter. Paging is local (a new filter remounts this panel at page one); the
// previous page stays visible, dimmed, while the next loads; only the newest request may fill the list.
export default function AgentApplicationsPanel({ group, reloadKey }: { group: StatusGroup; reloadKey: number }) {
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Page<AgentApplicationItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);

  useEffect(() => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setLoadError(null);
    const params = new URLSearchParams({ status: group, limit: String(PAGE_SIZE), offset: String(offset) });
    fetch(`${APPLICATIONS_URL}?${params}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (controller.signal.aborted) return;
        if (!response.ok || !isPage<AgentApplicationItem>(body)) return setLoadError(detailMessage(body?.detail, LOAD_FAILED));
        setData(body);
      })
      .catch(() => !controller.signal.aborted && setLoadError("Network error. Check your connection and try again."))
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [group, offset, reloadKey, attempt]);

  function replace(next: Detail) {
    setData((current) => current && { ...current, items: current.items.map((a) => (a.id === next.id ? { ...a, ...next } : a)) });
  }
  function close(id: string) {
    setOpenId(null);
    requestAnimationFrame(() => document.getElementById(`view-${id}`)?.focus());
  }

  const today = todayIso();
  return (
    <section className="action-card" aria-labelledby="agent-applications-heading" style={{ gridColumn: "1 / -1" }}>
      <h3 id="agent-applications-heading">{GROUP_LABELS[group]}</h3>
      {loadError && (
        <p className="form-error" role="alert">
          {loadError}{" "}
          <button type="button" className="btn secondary small" onClick={() => setAttempt((a) => a + 1)}>
            Retry
          </button>
        </p>
      )}
      {!data && loading && !loadError && <p className="muted" aria-busy="true">Loading applications…</p>}
      {data && !data.items.length && !loading &&
        (group === "all" ? (
          <p className="muted">No applications yet. Use Create application to add the first one.</p>
        ) : (
          <p className="muted">
            No applications match this filter. <a href="/overseas/agent/applications">Show all applications</a>
          </p>
        ))}
      {data && data.items.length > 0 && (
        <ul aria-label="Applications" aria-busy={loading} className="card-stack" style={{ listStyle: "none", padding: 0, opacity: loading ? 0.6 : 1 }}>
          {data.items.map((a) => {
            const title = `${a.student} — ${a.university}`;
            const deadline = deadlineText(a.nearest_deadline, today);
            return (
              <li key={a.id} className="card" style={{ padding: 16 }}>
                <strong>{title}</strong>
                {!a.has_login && <span className="badge" style={{ marginLeft: 8 }}>no login</span>}
                <div>
                  <span className={a.status === "withdrawn" ? "status error" : "badge"}>{stageLabel(a.status)}</span>
                  {a.application_reference && <span className="muted"> · ID {a.application_reference}</span>}
                  {a.course && <span className="muted"> · {a.course}</span>}
                  <span className="muted"> · {a.intake}</span>
                </div>
                {deadline && <div className="muted">{deadline}</div>}
                {a.next_action && <div className="muted">Next: {a.next_action}</div>}
                <button
                  type="button"
                  id={`view-${a.id}`}
                  className="btn secondary small"
                  aria-expanded={openId === a.id}
                  aria-label={`${openId === a.id ? "Hide" : "View"} ${title}`}
                  onClick={() => (openId === a.id ? close(a.id) : setOpenId(a.id))}
                  style={{ marginTop: 8 }}
                >
                  {openId === a.id ? "Hide" : "View"}
                </button>
                {openId === a.id && <AgentApplicationDetail id={a.id} onChanged={replace} onClose={() => close(a.id)} />}
              </li>
            );
          })}
        </ul>
      )}
      {data && data.total > 0 && (
        <div className="actions" style={{ marginTop: 12, alignItems: "center" }}>
          <span className="muted">
            Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}
          </span>
          <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            Previous
          </button>
          <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total || loading} onClick={() => setOffset(offset + PAGE_SIZE)}>
            Next
          </button>
        </div>
      )}
    </section>
  );
}
```

The test expects the open button to keep the "View …" accessible name while `aria-expanded` is true. Make the label stay `View ${title}` in both states and change only the visible text. Set `aria-label={`View ${title}`}` and keep the text toggle.

- [ ] **Step 4: Write `AgentApplicationsSection.tsx`**

```tsx
"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import AgentApplicationCreatePanel from "./AgentApplicationCreatePanel";
import AgentApplicationsPanel from "./AgentApplicationsPanel";
import { parseGroup } from "@/lib/agentApplications";
import type { User } from "@/lib/types";

// AGN-008: the agency Applications page -- create, then the list for the sidebar filter in the URL (?status=). Staff see only
// their assigned students' applications (G4); a non-agency viewer (Super Admin) gets a note, as on the Students page.
function Filtered({ reloadKey }: { reloadKey: number }) {
  const group = parseGroup(useSearchParams().get("status"));
  return <AgentApplicationsPanel key={group} group={group} reloadKey={reloadKey} />;
}

export default function AgentApplicationsSection({ user }: { user: User }) {
  const [reloadKey, setReloadKey] = useState(0);
  const member = user.role === "agent";
  const intro = !member
    ? "Agency applications are managed by the agency's own Masters and Staff."
    : user.agent_member_role === "staff"
      ? "Applications of students assigned to you, with or without a login."
      : "Every application of your agency, for students with or without a login.";
  return (
    <div className="portal-content">
      <div className="portal-title">
        <div>
          <div className="eyebrow">Workspace</div>
          <h2>Applications</h2>
          <p className="muted">{intro}</p>
        </div>
      </div>
      {member && (
        <div className="action-grid">
          <AgentApplicationCreatePanel onCreated={() => setReloadKey((k) => k + 1)} />
          <Suspense fallback={<p className="muted">Loading applications…</p>}>
            <Filtered reloadKey={reloadKey} />
          </Suspense>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Wire the page**

`PortalPage.tsx`: import `AgentApplicationsSection`. Change `main` so it handles `applications` before the generic table:

```tsx
const main=agent&&section==="students"?<>
<AgentStudentsSection user={user}/>
<PortalSection data={{...data,title:"Application status",subtitle:"Students who have a login, with each one's current application (AGT-002)."}}/>
</>:agent&&section==="applications"?<AgentApplicationsSection user={user}/>:<PortalSection data={data}/>;
```

Add a comment above it: `// AGN-008: the agency Applications page is the applications panel (list, detail, filters); the generic table is replaced there only.`

`WorkflowPanel.tsx`:
- Delete the `AgentApplicationCreatePanel` import (L40).
- Delete the `showAgentApplicationCreate` const (L468).
- Delete ` && !showAgentApplicationCreate` from the early-return condition.
- Delete `{showAgentApplicationCreate && <AgentApplicationCreatePanel/>}` from L478.
- Update the comment at L322 to: "AGN-008: "applications" is the AgentApplicationsSection on PortalPage (create panel included)."

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `WEB_TEST tests/components/AgentApplicationsPanel.test.tsx tests/components tests/lib`
Expected: PASS. All component and lib tests pass, including the existing WorkflowPanel tests.

- [ ] **Step 7: Type-check and build**

Run: `cd apps/web && npx tsc --noEmit && npm run build`
Expected: exit 0. If `useSearchParams` reports a missing-Suspense error, check that both uses (`NavGroup`, `Filtered`) sit inside `<Suspense>`.

- [ ] **Step 8: Commit**

```bash
git add apps/web/components/AgentApplicationsPanel.tsx apps/web/components/AgentApplicationsSection.tsx apps/web/components/PortalPage.tsx apps/web/components/WorkflowPanel.tsx apps/web/tests/components/AgentApplicationsPanel.test.tsx
git commit -m "feat(agn-008): agency Applications page -- filtered list, detail, create"
```

---

### Task 14: Playwright end-to-end

**Files:**
- Create: `apps/web/tests/e2e/agn-008-agent-applications.spec.ts`

The owner starts the app stack for e2e. The ports follow the convention, web `3008` and API `8008`; ask before running.

- [ ] **Step 1: Write the spec**

```ts
import { expect, test, type Page } from "@playwright/test";

import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";
import { pickFromList } from "./helpers/pick";

// AGN-008 -- an agency's applications for students with no login: create with ID/dates, edit, forward-only status, withdraw;
// sidebar filters; staff scope; the admin and university_rep lists name the owner; 320 px. Unique names per run (shared E2E DB).
const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

async function addNoLoginStudent(page: Page, name: string) {
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  await form.getByRole("button", { name: "Save student" }).click();
  await expect(page.getByText(`${name} added.`)).toBeVisible();
}

async function manchesterId(page: Page): Promise<string> {
  const universities = await (await page.request.get("/api/v1/public/universities")).json();
  return universities.find((u: { slug: string }) => u.slug === "university-of-manchester").id;
}

async function createApplication(page: Page, name: string, reference: string) {
  await page.goto("/overseas/agent/applications");
  await pickFromList(page.getByRole("combobox", { name: "Linked student" }), name, new RegExp(`^${name} — no login$`));
  await page.locator("#agent-app-university").selectOption(await manchesterId(page));
  await page.getByLabel("Application ID").fill(reference);
  await page.getByLabel("Offer deadline").fill("2027-01-15");
  await page.getByRole("button", { name: /Create application/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "Application created." })).toBeVisible();
}

test("a Master creates, edits, moves forward and withdraws an application for a student with no login (AC01/04/05/06/11)", async ({ page }) => {
  const name = `E2E App ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await addNoLoginStudent(page, name);
  await createApplication(page, name, `REF-${stamp()}`);

  const list = page.getByRole("list", { name: "Applications" });
  const view = list.getByRole("button", { name: new RegExp(`^View ${name} — `) });
  await view.click();
  const detail = page.getByRole("region", { name: new RegExp(`^${name} — `) });
  await detail.getByRole("button", { name: "Edit" }).click();
  await detail.getByLabel("Intake (required)").fill("Spring 2028");
  await detail.getByRole("button", { name: "Save" }).click();
  await expect(detail.getByRole("status")).toHaveText("Saved.");

  await detail.getByLabel("Move to").selectOption("offer");
  await detail.getByRole("button", { name: "Update status" }).click();
  await expect(detail.getByRole("status")).toHaveText("Status updated to Offer.");
  const options = await detail.getByLabel("Move to").locator("option").allTextContents();
  expect(options).toEqual(["Visa documentation", "Status tracking"]); // never backward, never Enrolled

  await page.getByRole("navigation").getByRole("link", { name: "Offer received" }).click();
  await expect(page.getByRole("heading", { name: "Offer received" })).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("link", { name: "Offer received" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("list", { name: "Applications" })).toContainText(name);

  await page.getByRole("list", { name: "Applications" }).getByRole("button", { name: new RegExp(`^View ${name} — `) }).click();
  const again = page.getByRole("region", { name: new RegExp(`^${name} — `) });
  await again.getByRole("button", { name: "Withdraw application" }).click();
  await again.getByRole("button", { name: "Yes, withdraw" }).click();
  await expect(again.getByRole("status")).toHaveText("Application withdrawn.");
  await expect(again.getByText("This application is withdrawn, so it can no longer be changed.")).toBeVisible();
});

test("the admin and university_rep lists name a no-login owner (AC08)", async ({ page, request }) => {
  const name = `E2E Owner ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await addNoLoginStudent(page, name);
  await createApplication(page, name, `OWN-${stamp()}`);
  for (const [email, url] of [
    ["overseasadmin@edusphere.local", "/api/v1/admin/applications"],
    ["university.rep@edusphere.local", "/api/v1/workflows/overseas/applications"],
  ]) {
    expect((await request.post("/api/v1/auth/login", { data: { email, password: "Demo@123", division: "overseas" } })).ok()).toBeTruthy();
    const rows = await (await request.get(url)).json();
    expect(rows.map((r: { student: string }) => r.student)).toContain(name);
    await request.post("/api/v1/auth/logout");
  }
});

test("staff see only their assigned students' applications through the filters (AC02/AC11)", async ({ page, request }) => {
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "agn008");
  const staffEmail = `agn008-s-${unique}@example.local`;
  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await page.goto("/overseas/agent/team");
  await page.getByRole("button", { name: "Add staff" }).click();
  await page.getByLabel("Full name").fill("Apps Staff");
  await page.getByLabel("Email").fill(staffEmail);
  await page.getByRole("button", { name: "Create staff login" }).click();
  await adminActivate(request, staffEmail);
  const mine = `E2E Mine ${stamp()}`;
  const theirs = `E2E Theirs ${stamp()}`;
  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await addNoLoginStudent(page, mine);
  await addNoLoginStudent(page, theirs);
  await createApplication(page, mine, `M-${stamp()}`);
  await createApplication(page, theirs, `T-${stamp()}`);
  // Assign `mine` to the staff member (AGN-004's assign control on the Students page).
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: `View ${mine}`, exact: true }).click();
  await page.getByRole("button", { name: "Assign" }).click();
  await page.getByLabel("Assign to").selectOption({ label: /Apps Staff/ });
  await page.getByRole("button", { name: "Save assignment" }).click();
  await signIn(page, staffEmail, "Sup3r-Secret-Pass!");
  await page.goto("/overseas/agent/applications?status=draft");
  const list = page.getByRole("list", { name: "Applications" });
  await expect(list).toContainText(mine);
  await expect(list).not.toContainText(theirs);
});

test("no horizontal scroll at 320px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await page.goto("/overseas/agent/applications");
  await expect(page.getByRole("heading", { name: "Applications", level: 2 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
```

Before running, take the staff-creation and assignment control names from `agn-002-staff.spec.ts` and `agn-004-agent-students.spec.ts` (the assign test), and replace the four lines above with the exact names those specs use. Do not invent labels.

- [ ] **Step 2: Run the spec and the neighbours**

Run (owner's stack up):

```bash
cd apps/web && npx playwright test tests/e2e/agn-008-agent-applications.spec.ts tests/e2e/enh-031-searchable-pickers.spec.ts tests/e2e/agn-004-agent-students.spec.ts tests/e2e/agt-002-referrals.spec.ts tests/e2e/agt-003-commission-accrual.spec.ts tests/e2e/ovs-002-application.spec.ts tests/e2e/ovs-003-eligibility.spec.ts tests/e2e/ovs-004-status-tracking.spec.ts tests/e2e/uni-001-university-rep-portal.spec.ts
```

Expected: PASS. Open traces only for failures.

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/agn-008-agent-applications.spec.ts
git commit -m "test(agn-008): e2e -- create/edit/status/withdraw, filters, staff scope, owner in admin/rep lists, 320px"
```

---

### Task 15: Documentation and traceability

**Files (modify):**
- `docs/decisions/PRODUCT_DECISION_REGISTER.md`: add `DEC-SCOPE-050` after `DEC-SCOPE-047`.
- `docs/delivery/ENHANCEMENT_BACKLOG.md`: a summary row and an AGN-008 section with AC01–AC18.
- `docs/quality/RTM.md`: an AGN-008 row with evidence links to the test files.
- `docs/architecture/DATA_MODEL.md` §6.2: the new columns, `withdrawn`, and the owner invariant.
- `docs/architecture/API_CONTRACT.md` (whichever file holds the AGN-004 table): the agent applications table, and nullable `student_id` in `GET /workflows/overseas/applications`.
- `RBAC_MATRIX.md`, `SECURITY_CONTROLS.md`, `THREAT_MODEL.md`: A4, A14, A15, the abuse cases.
- `docs/product/PRD_OPEN_ITEMS.md` item 68: the agent half is resolved for applications.
- `docs/evidence/CONFLICT_MATRIX.md` C-10: a note that the EVID-015 §2 Applications, §4 sidebar Applications and §5 Step 5 slices are decided (DEC-SCOPE-050).
- `SCREEN_CATALOG.md` and `.json`: validate the JSON with `python -m json.tool`.

Locate each file with `ls docs/*/` and follow the format of AGN-004's entries in that same file.

- [ ] **Step 1: Write the DEC entry**

Use the AGN-004 format: Title (AGN-008), ID note (provisional; 048/049 claimed by AGN-006/007), Question (the owner's statement quoted), Evidence (graphify impact analysis, 2026-10-01), Conflicts recorded, Resolution (A1–A15, `EXPLICIT_APPROVAL` in-session 2026-10-01/02), Consequences (D8 lifted; matrix rows enforced; 0057).

- [ ] **Step 2: Update the rest of the docs**

Make the remaining edits in the list above. Then validate: `python -m json.tool docs/<path>/SCREEN_CATALOG.json > /dev/null`.

- [ ] **Step 3: Commit**

```bash
git add docs
git commit -m "docs(agn-008): DEC-SCOPE-050, backlog, RTM, data model, API contract, RBAC, security, C-10, screens"
```

---

### Task 16: Verification sweep (no completion claim)

- [ ] **Step 1: Recheck main**

Run: `git fetch origin && git log --oneline HEAD..origin/main`. If AGN-006, AGN-007 or anything touching 0055/0056, DEC-048/049 or the shared anchors has landed, stop and report. Do not merge without the owner.

- [ ] **Step 2: Backend lite set (real run)**

Run the Task 8, Step 5 command. Record the pass and fail counts.

- [ ] **Step 3: Web tests and build**

Run: `WEB_TEST tests` and `cd apps/web && npx tsc --noEmit && npm run build`. Record the results.

- [ ] **Step 4: E2E (owner's stack)**

Run the Task 14, Step 2 command. Record the results.

- [ ] **Step 5: Migration**

The Task 1 tests cover upgrade, downgrade and refusal. Confirm they are in the Step 2 output.

- [ ] **Step 6: Report**

Report to the owner:
- every command with its exit code and counts;
- the full backend suite NOT run (the owner's standing choice);
- AC01–AC18 mapped to their tests;
- the remaining gates: browser QA, the independent Codex review, the full suite, and the merge renumbering against AGN-006/007.

Make no completion claim.

---

## Self-review notes

**1. Spec coverage**

| Spec section | Task(s) |
|---|---|
| §4 migration | 1 |
| §5.1 scope | 2 |
| §5.2 service | 2, 5, 6, 7 |
| §5.3 routes | 5 (read), 6 (create), 7 (edit, status) |
| §5.4 schemas | 4 |
| §5.5 withdrawn guard | 7 |
| §5.6 shared lists | 2, 3 |
| §5.7 races (org lock, row lock) | 6, 7 |
| §5.7 transaction failure | 6 |
| §6.1–6.6 frontend | 9–13 |
| §7 security | 6, 7, 8 |
| §8 AC01–AC18 | 1–14 |
| §9 tests | every task |
| §11 docs | 15 |
| §13 gates | 16 |

**2. Placeholder scan.** Several steps tell the implementer to confirm a name in the repo rather than guess it:
- the School-student builder (Task 2, 1a);
- the portal payload rows key (Task 3);
- the activity-label export (Task 9);
- the e2e staff and assignment control names (Task 14).

Each is a lookup with a stated fallback, not an unspecified behaviour. There are no TBDs.

**3. Type consistency.** `Owner`, `with_owner` and `owned` are used the same way in Tasks 2 and 3. `item(row, today)` takes the 5-tuple `(app, university_name, university_slug, course_title, owner)` in Task 5. The `APPLICATIONS_URL` and `AgentApplicationDetail` fields match the server's `detail()`: `university_slug`, `read_only_reason` and `history[].changed_by`.

**4. Review Focus.** All five lines are pinned to named tests in Tasks 2, 3, 6 and 7.
