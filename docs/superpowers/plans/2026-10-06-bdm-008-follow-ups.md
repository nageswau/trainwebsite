# bdm-008 Follow-ups and tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One place where a BDM sees, adds, completes, edits and cancels follow-ups and tasks (Today / Overdue / Upcoming / Done /
Cancelled on IST dates, counted by organization type), read by their manager, on top of bdm-007's `bdm_tasks`.

**Architecture:** Additive migration `0076` on `bdm_tasks`; a new `services/bdm_tasks.py` + `api/bdm_tasks.py` pair following
bdm-006/009 (scope filters in SQL, one commit per route, audit in the transaction, db clock once per request); one-line hooks in
bdm-007's `sync_follow_up` and bdm-002's archive. Web: `lib/bdmTasks.ts`, `BdmTaskForm`, `BdmTaskItem`, `BdmTasksPanel`,
`BdmOrganizationTasks`, two pages and a nav entry, reusing `SearchableSelect`, `BdmAppointmentReasonForm`, `sendJson`, `fieldErrors`.

**Tech Stack:** FastAPI, Pydantic v2, async SQLAlchemy 2, Alembic, PostgreSQL; Next.js App Router, React, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-06-bdm-008-follow-ups-design.md` (decisions F1–F7, `DEC-SCOPE-074`).

## Global Constraints

- Migration `0076_bdm_tasks_followups`, `down_revision = "0075_telecaller_profiles"`; additive only; downgrade refuses while `manual` tasks exist.
- Decision id `DEC-SCOPE-074`.
- Today = `today_ist(db_now(db))`, read once per request.
- Title 1–200 single line; notes ≤ 2000 multi-line; reason ≤ 500 (bdm-006's `BdmAppointmentReason`); due date strict `YYYY-MM-DD`, ≥ IST today on create and when changed.
- Daily create cap 200 manual items per BDM per IST day → 409 "You've added 200 tasks today".
- Errors `{"detail": str}` (service) / FastAPI list (schema 422). Out of scope = 404 "Task not found". Non-owner write = 403 "Only the assigned BDM can change this task".
- Logs and audit: ids, kind, source, field names, counts — never title, notes or reason text.
- Lock order: organization → task; appointment → (report →) task; never a task before an organization or appointment.
- No new dependency. Existing CSS classes only. No colour-only state.
- Lite tests only (the owner runs the full suites). Do not claim completion: browser validation and Codex review follow.

## Review Focus

1. **A follow-up due on the IST day that has just begun (18:30–23:59 UTC of the previous UTC day)** must be "today", not "overdue" — Task 4 `test_overdue_uses_the_ist_date`.
2. **Counts vs list with a type filter** — pressing "College" must show a list whose length equals the College chip — Task 5 `test_counts_match_the_list`.
3. **Archive while the BDM has the row open in another tab, then they press Done** → 409 with words, list reloads, nothing reopened — Task 9 `test_complete_after_archive_is_409` + Task 12 `reloads on a 409`.
4. **Editing an old open task without touching its (now past) due date** must save the title — Task 7 `test_unchanged_past_due_date_is_accepted`.
5. **A manager pressing Done through a crafted request** → 403, row unchanged, refusal logged — Task 7 `test_manager_cannot_write`.

## How to run tests (worktree)

The user starts Docker. From the worktree root in Git Bash. `<P>` = test paths.

```bash
W="C:/Users/kunam/Documents/project/trainwebsite/.claude/worktrees/bdm-008"
# Backend
docker compose -p bdm008 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "$W/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <P>"
# Web (vitest / tsc / eslint)
MSYS_NO_PATHCONV=1 docker compose -p bdm008 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps \
  -v "$W/apps/web:/app" -v /app/node_modules web-test sh -c "npx vitest run <paths>"
```

Stale alembic stamp from another branch: prefix `alembic stamp --purge 0075_telecaller_profiles &&`.

LITE = `tests/test_bdm_008_*.py tests/test_bdm_007_*.py tests/test_bdm_002_organizations.py tests/test_tel_001_migration.py`

## File map

| File | Responsibility |
|---|---|
| `apps/api/alembic/versions/0076_bdm_tasks_followups.py` (new) | columns, backfill, CHECKs, guarded downgrade |
| `apps/api/app/models.py` (modify `BdmTask`) | three columns, two CHECKs |
| `apps/api/app/schemas.py` (append) | `BdmTaskCreate/Update/Out/Page` and refs |
| `apps/api/app/services/bdm_tasks.py` (new) | scope, buckets, counts, output, write loading, cap, archive cancel, audit/log |
| `apps/api/app/api/bdm_tasks.py` (new) + `main.py` | five routes |
| `apps/api/app/services/bdm_appointments.py` (modify `sync_follow_up`) | fill `cancelled_*` |
| `apps/api/app/api/bdm_organizations.py` (modify `_set_archived`) | cancel open items on archive |
| `apps/api/tests/bdm008_helpers.py` + `test_bdm_008_*.py` (new) | tests |
| `apps/web/lib/bdmTasks.ts`, `bdmTasksServer.ts` (new) | types, URLs, guards, server first page |
| `apps/web/components/BdmTaskForm.tsx`, `BdmTaskItem.tsx`, `BdmTasksPanel.tsx`, `BdmOrganizationTasks.tsx` (new) | UI |
| `apps/web/app/bdm/follow-ups/*`, `apps/web/app/bdm/manager/follow-ups/*` (new) | pages |
| `apps/web/lib/navigation.ts`, `BdmOrganizationDetail.tsx`, organization pages (modify) | wiring |
| docs (API_CONTRACT, DATA_MODEL, decision register, backlog, RTM, SCREEN_CATALOG + json, ROLE_NAVIGATION) | traceability |

---

### Task 1: Migration 0076 and the model

**Files:**
- Create: `apps/api/alembic/versions/0076_bdm_tasks_followups.py`
- Modify: `apps/api/app/models.py` (`class BdmTask`)
- Modify: `apps/api/tests/test_bdm_007_migration.py` (`test_models_match_the_migration` column set)
- Modify: `apps/api/tests/test_tel_001_migration.py:39` (single head → on the chain)
- Test: `apps/api/tests/test_bdm_008_migration.py`

**Interfaces:** Produces `BdmTask.notes: str | None`, `BdmTask.cancelled_at: datetime | None`, `BdmTask.cancel_reason: str | None`;
constraint names `ck_bdm_tasks_cancelled`, `ck_bdm_tasks_cancel_reason`; migration constants `REPORT_CLEARED`, `CHECKS`.

- [ ] **Step 1: Write the failing test** `apps/api/tests/test_bdm_008_migration.py`

```python
"""bdm-008 -- migration 0076_bdm_tasks_followups (spec §4). Isolated database per test (the bdm-007 pattern)."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_bdm_008_migration_0076", VERSIONS / "0076_bdm_tasks_followups.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0075_telecaller_profiles"
HEAD = "0076_bdm_tasks_followups"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_chains_after_0075_and_is_on_the_single_chain():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_models_match_the_migration():
    from app.models import BdmTask

    table = BdmTask.__table__
    assert {"notes", "cancelled_at", "cancel_reason"} <= {c.name for c in table.columns}
    assert (table.c.notes.type.length, table.c.cancel_reason.type.length) == (2000, 500)
    assert set(_migration.CHECKS) <= {c.name for c in table.constraints}


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


TASK = (
    "INSERT INTO bdm_tasks (id, kind, title, due_on, source, assignee_user_id, status, updated_at) "
    "VALUES (:id, 'follow_up', 'T', '2026-09-22', :source, :u, :status, '2026-09-20T10:00:00+00')"
)


@pytest.fixture
def isolated_db():
    """A fresh database at 0075 whose bdm_tasks is put back to 0072's shape (0001's create_all builds it from the models), holding one
    open and one cancelled (bdm-007 "date cleared") task."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm008_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        _sql(url, "ALTER TABLE bdm_tasks DROP CONSTRAINT IF EXISTS ck_bdm_tasks_cancelled, DROP CONSTRAINT IF EXISTS ck_bdm_tasks_cancel_reason, "
                  "DROP COLUMN IF EXISTS notes, DROP COLUMN IF EXISTS cancelled_at, DROP COLUMN IF EXISTS cancel_reason")
        user = uuid.uuid4()
        _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'it', true, true, 'en-GB', '{}')", {"id": user, "email": f"bdm-{name}@example.local"})
        tasks = {"open": uuid.uuid4(), "cancelled": uuid.uuid4()}
        for status, task_id in tasks.items():
            _sql(url, TASK, {"id": task_id, "source": "manual", "u": user, "status": status})
        yield {"cfg": cfg, "url": url, "user": user, "tasks": tasks}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_adds_the_columns_and_backfills_cancelled_rows(isolated_db):
    url, tasks = isolated_db["url"], isolated_db["tasks"]
    command.upgrade(isolated_db["cfg"], HEAD)
    rows = dict((r[0], r[1:]) for r in _sql(url, "SELECT id, cancelled_at, cancel_reason, notes FROM bdm_tasks"))
    assert rows[tasks["open"]] == (None, None, None)
    at, reason, notes = rows[tasks["cancelled"]]
    assert at.isoformat().startswith("2026-09-20T10:00") and reason == _migration.REPORT_CLEARED and notes is None


def test_constraints_hold(isolated_db):
    cfg, url, user = isolated_db["cfg"], isolated_db["url"], isolated_db["user"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="ck_bdm_tasks_cancelled"):
        _sql(url, TASK, {"id": uuid.uuid4(), "source": "manual", "u": user, "status": "cancelled"})  # no cancelled_at
    with pytest.raises(Exception, match="ck_bdm_tasks_cancel_reason"):
        _sql(url, "UPDATE bdm_tasks SET cancel_reason = 'x' WHERE id = :id", {"id": isolated_db["tasks"]["open"]})


def test_downgrade_refuses_while_manual_tasks_exist_and_round_trips_otherwise(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="manual tasks exist"):
        command.downgrade(cfg, BASE)
    _sql(url, "UPDATE bdm_tasks SET source = 'mou'")  # nothing manual left: allowed
    command.downgrade(cfg, BASE)
    assert "cancel_reason" not in {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'bdm_tasks'")}
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT count(*) FROM bdm_tasks WHERE status = 'cancelled' AND cancelled_at IS NOT NULL") == [(1,)]
```

- [ ] **Step 2: Run it to see it fail**

Run: `… pytest -q tests/test_bdm_008_migration.py`
Expected: FAIL / ERROR — `FileNotFoundError` for `0076_bdm_tasks_followups.py`.

- [ ] **Step 3: Write the migration** `apps/api/alembic/versions/0076_bdm_tasks_followups.py`

```python
"""bdm-008 (DEC-SCOPE-074): follow-ups and tasks -- notes, cancelled_at and cancel_reason on bdm_tasks.

Rows bdm-007 already cancelled (the meeting report's follow-up date was cleared) get their time and reason, so "cancelled <=> a
cancellation time" holds for every row. Additive: no column is dropped or retyped.

Revision ID: 0076_bdm_tasks_followups
Revises: 0075_telecaller_profiles
"""

import sqlalchemy as sa

from alembic import op

revision = "0076_bdm_tasks_followups"
down_revision = "0075_telecaller_profiles"
branch_labels = None
depends_on = None

TASKS = "bdm_tasks"
REPORT_CLEARED = "Follow-up date removed from the meeting report"  # = services.bdm_appointments.FOLLOW_UP_CLEARED
CHECKS = {
    "ck_bdm_tasks_cancelled": "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
    "ck_bdm_tasks_cancel_reason": "cancel_reason IS NULL OR status = 'cancelled'",
}
# Set-based and idempotent, so it also runs when 0001's create_all already built the columns.
BACKFILL = f"UPDATE {TASKS} SET cancelled_at = updated_at, cancel_reason = '{REPORT_CLEARED}' WHERE status = 'cancelled' AND cancelled_at IS NULL"


def _built_by_models() -> bool:
    if op.get_context().as_sql:
        return False
    return "cancelled_at" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TASKS)}


def upgrade() -> None:
    fresh = _built_by_models()
    if not fresh:
        op.add_column(TASKS, sa.Column("notes", sa.String(2000), nullable=True))
        op.add_column(TASKS, sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(TASKS, sa.Column("cancel_reason", sa.String(500), nullable=True))
    op.execute(BACKFILL)
    if not fresh:
        for name, sql in CHECKS.items():
            op.create_check_constraint(name, TASKS, sql)


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TASKS} WHERE source = 'manual' LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0076_bdm_tasks_followups: manual tasks exist. Remove them deliberately first.")
    for name in CHECKS:
        op.drop_constraint(name, TASKS, type_="check")
    for column in ("cancel_reason", "cancelled_at", "notes"):
        op.drop_column(TASKS, column)
```

- [ ] **Step 4: Extend the model** (`apps/api/app/models.py`, `class BdmTask`)

Docstring: append "bdm-008 (DEC-SCOPE-074) adds notes, the cancellation time and reason, manual tasks and completion."
Add to `__table_args__` after `ck_bdm_tasks_completed`:

```python
        CheckConstraint("(status = 'cancelled') = (cancelled_at IS NOT NULL)", name="ck_bdm_tasks_cancelled"),
        CheckConstraint("cancel_reason IS NULL OR status = 'cancelled'", name="ck_bdm_tasks_cancel_reason"),
```

Add after `completed_at`:

```python
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
```

- [ ] **Step 5: Update the pinned tests**

`test_bdm_007_migration.py::test_models_match_the_migration` — the `task` column set gains `"notes", "cancelled_at", "cancel_reason"`.
`test_tel_001_migration.py:39` — replace `assert ScriptDirectory.from_config(_config()).get_heads() == [HEAD]` with
```python
    script = ScriptDirectory.from_config(_config())  # bdm-008's 0076 follows; 0075 stays on the single chain
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}
```

- [ ] **Step 6: Run** `tests/test_bdm_008_migration.py tests/test_bdm_007_migration.py tests/test_tel_001_migration.py` — Expected: PASS.
- [ ] **Step 7: Commit** `feat(bdm-008): migration 0076 -- notes and cancellation on bdm_tasks`

---

### Task 2: Schemas

**Files:** Modify `apps/api/app/schemas.py` (append after the bdm-007 block); Test `apps/api/tests/test_bdm_008_schemas.py`

**Interfaces — Produces:** `BdmTaskKind`, `BdmTaskBucket`, `BdmTaskOrgType`, `BdmTaskCreate`, `BdmTaskUpdate`, `BdmTaskOut`, `BdmTaskPage`
(and refs `BdmTaskOrgRef`, `BdmTaskAppointmentRef`, `BdmTaskPermissions`, `BdmTaskCounts`, `BdmTaskTypeCount`, `BdmTaskBucketCounts`).
Cancel reuses `BdmAppointmentReason`.

- [ ] **Step 1: Failing test** `apps/api/tests/test_bdm_008_schemas.py`

```python
"""bdm-008 -- request schemas (spec §6.2, §6.3)."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import BdmTaskCreate, BdmTaskUpdate

OK = {"kind": "task", "title": "Send brochure", "due_on": "2030-01-07"}


def _msgs(exc: ValidationError) -> list[str]:
    return [e["msg"] for e in exc.errors()]


def test_create_parses_and_trims():
    body = BdmTaskCreate.model_validate({**OK, "title": "  Send brochure  ", "notes": "line 1\nline 2"})
    assert (body.title, body.due_on, body.notes, body.organization_id) == ("Send brochure", date(2030, 1, 7), "line 1\nline 2", None)


@pytest.mark.parametrize(("over", "message"), [
    ({"title": "   "}, "Title is required"),
    ({"title": "a\nb"}, "Title contains invalid characters"),
    ({"title": "x" * 201}, "at most 200"),
    ({"notes": "bad\x07"}, "Notes contains invalid characters"),
    ({"notes": "x" * 2001}, "at most 2000"),
    ({"due_on": "22/09/2026"}, "Enter a valid due date"),
    ({"due_on": "202026-09-22"}, "Enter a valid due date"),
    ({"kind": "meeting"}, "follow_up"),
    ({"assignee_user_id": "00000000-0000-0000-0000-000000000000"}, "Extra inputs are not permitted"),
    ({"status": "done"}, "Extra inputs are not permitted"),
])
def test_create_refuses(over, message):
    with pytest.raises(ValidationError) as exc:
        BdmTaskCreate.model_validate({**OK, **over})
    assert any(message in m for m in _msgs(exc.value))


def test_blank_notes_become_null():
    assert BdmTaskCreate.model_validate({**OK, "notes": "  "}).notes is None


def test_update_is_partial_and_refuses_null_title_and_due():
    assert BdmTaskUpdate.model_validate({}).model_dump(exclude_unset=True) == {}
    assert BdmTaskUpdate.model_validate({"notes": None}).model_dump(exclude_unset=True) == {"notes": None}
    for field, message in (("title", "Title is required"), ("due_on", "Due date is required")):
        with pytest.raises(ValidationError) as exc:
            BdmTaskUpdate.model_validate({field: None})
        assert message in " ".join(_msgs(exc.value))
    with pytest.raises(ValidationError):
        BdmTaskUpdate.model_validate({"kind": "task"})  # kind and organization are fixed after create
```

- [ ] **Step 2: Run** — Expected: FAIL `ImportError: cannot import name 'BdmTaskCreate'`.
- [ ] **Step 3: Implement** (append to `schemas.py`)

```python
# --- bdm-008 (DEC-SCOPE-074, spec §6): follow-ups and tasks ---------------------------------------------------------------------
BDM_TASK_LABELS = {"title": "Title", "notes": "Notes"}
BdmTaskKind = Literal["follow_up", "task"]
BdmTaskBucket = Literal["today", "overdue", "upcoming", "open", "done", "cancelled"]
BdmTaskOrgType = BdmOrgType | Literal["none"]
BdmTaskTitle = Annotated[str, _trimmed(200), AfterValidator(_trip_text(_BDM_CONTROL, True, BDM_TASK_LABELS))]
BdmTaskNotes = Annotated[Annotated[str, _trimmed(2000)] | None, AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, False, BDM_TASK_LABELS))]
BdmTaskDue = Annotated[date, BeforeValidator(_trip_date("due date"))]


class BdmTaskCreate(BaseModel):
    """§6.2: a manual follow-up or task. Assignee, source, status and timestamps are server-owned (unknown fields here)."""

    model_config = ConfigDict(extra="forbid")
    kind: BdmTaskKind
    title: BdmTaskTitle
    due_on: BdmTaskDue
    organization_id: UUID | None = None
    notes: BdmTaskNotes = None


class BdmTaskUpdate(BaseModel):
    """§6.3: omitted = unchanged; `notes: null` clears; a sent null title or due date is refused (both are always set)."""

    model_config = ConfigDict(extra="forbid")
    title: BdmTaskTitle | None = None
    due_on: BdmTaskDue | None = None
    notes: BdmTaskNotes = None

    @field_validator("title", "due_on")
    @classmethod
    def _not_null(cls, value, info: ValidationInfo):
        """Omitted = unchanged (the default is not validated); a sent null is refused."""
        if value is None:
            raise ValueError(f"{'Title' if info.field_name == 'title' else 'Due date'} is required")
        return value


class BdmTaskOrgRef(BaseModel):
    id: UUID
    code: str
    name: str
    org_type: str
    archived: bool


class BdmTaskAppointmentRef(BaseModel):
    id: UUID
    code: str


class BdmTaskPermissions(BaseModel):
    can_edit: bool
    can_complete: bool
    can_cancel: bool


class BdmTaskOut(BaseModel):
    id: UUID
    kind: str
    title: str
    notes: str | None
    due_on: date
    status: str
    source: str
    overdue: bool
    organization: BdmTaskOrgRef | None
    appointment: BdmTaskAppointmentRef | None
    assignee: BdmOrgPerson
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime
    permissions: BdmTaskPermissions


class BdmTaskBucketCounts(BaseModel):
    today: int
    overdue: int
    upcoming: int
    done: int
    cancelled: int


class BdmTaskTypeCount(BaseModel):
    org_type: str | None
    count: int


class BdmTaskCounts(BaseModel):
    buckets: BdmTaskBucketCounts
    by_org_type: list[BdmTaskTypeCount]


class BdmTaskPage(BaseModel):
    items: list[BdmTaskOut]
    total: int
    limit: int
    offset: int
    today: date
    counts: BdmTaskCounts
```

(If `BdmOrgPerson` is defined after this point, place the block after it; it is defined in the bdm-002 section, before bdm-006.)

- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `feat(bdm-008): task request and response schemas`

---

### Task 3: bdm-007's sync fills the cancellation

**Files:** Modify `apps/api/app/services/bdm_appointments.py` (`sync_follow_up` + constant); Test: add to `apps/api/tests/test_bdm_007_reports.py`

**Interfaces — Produces:** `services.bdm_appointments.FOLLOW_UP_CLEARED = "Follow-up date removed from the meeting report"`.

- [ ] **Step 1: Failing test** (append to `test_bdm_007_reports.py`)

```python
@pytest.mark.asyncio
async def test_clearing_the_date_records_when_and_why_and_setting_it_again_clears_both(client, db_session):
    """bdm-008 (spec §4.1): a cancelled follow-up carries its time and reason; a reopened one carries neither."""
    _, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org, next_follow_up_on=in_days(2))
    await client.patch(report_url(a), json={"next_follow_up_on": None})
    row = (await db_session.execute(select(BdmTask.cancelled_at, BdmTask.cancel_reason).where(BdmTask.source_appointment_id == a["id"]).execution_options(populate_existing=True))).one()
    assert row.cancelled_at is not None and row.cancel_reason == "Follow-up date removed from the meeting report"
    await client.patch(report_url(a), json={"next_follow_up_on": in_days(3)})
    row = (await db_session.execute(select(BdmTask.status, BdmTask.cancelled_at, BdmTask.cancel_reason).where(BdmTask.source_appointment_id == a["id"]).execution_options(populate_existing=True))).one()
    assert tuple(row) == ("open", None, None)
```

- [ ] **Step 2: Run** — Expected: FAIL with `IntegrityError ... ck_bdm_tasks_cancelled` (the CHECK now requires the time).
- [ ] **Step 3: Implement** — in `services/bdm_appointments.py` add beside `FOLLOW_UP_DONE`:

```python
FOLLOW_UP_CLEARED = "Follow-up date removed from the meeting report"  # bdm-008 §4.1; 0076 backfills the same words
```

and in `sync_follow_up`:

```python
    if due_on is None:
        if task.status == "cancelled":
            return None
        task.status, task.cancelled_at, task.cancel_reason = "cancelled", func.now(), FOLLOW_UP_CLEARED
        return "cancelled"
    if task.status == "cancelled":
        task.status, task.due_on, task.cancelled_at, task.cancel_reason = "open", due_on, None, None
        return "reopened"
```

(`func` is already imported in this module; check and add `from sqlalchemy import func` if not.)

- [ ] **Step 4: Run** `tests/test_bdm_007_reports.py tests/test_bdm_007_concurrency.py` — PASS. **Step 5: Commit** `feat(bdm-008): a cleared report follow-up records its cancellation`

---

### Task 4: The task service

**Files:** Create `apps/api/app/services/bdm_tasks.py`; Test `apps/api/tests/test_bdm_008_service.py`

**Interfaces — Produces** (used by Tasks 5–9):
- `NOT_FOUND`, `OWNER_ONLY`, `FROM_REPORT`, `PAST_DUE`, `NOT_ASSIGNED`, `ARCHIVED`, `ORG_ARCHIVED`, `DAILY_CAP`, `TABS`
- `async caller_filters(db, user) -> list`
- `bucket_filter(bucket: str, today: date)`, `org_type_filter(org_type: str)`, `is_overdue(status: str, due_on: date, today: date) -> bool`
- `permissions(user, task) -> dict[str, bool]`
- `async page(db, user, base: list, bucket: str, org_type: str | None, today: date, limit: int, offset: int) -> dict`
- `async one(db, user, task_id: UUID, today: date) -> dict`
- `async load_for_write(db, user, task_id: UUID, action: str) -> BdmTask`
- `require_open(task)`, `require_manual(task)`
- `async created_today(db, user_id: UUID, today: date) -> int`
- `async cancel_open_for_organization(db, org_id: UUID) -> int`
- `audit(db, user, action: str, task_id, metadata: dict | None = None)`, `log(event: str, user, task_id, **extra)`

- [ ] **Step 1: Failing test** `apps/api/tests/test_bdm_008_service.py`

```python
"""bdm-008 -- pure rules (spec §5): IST buckets, overdue and permissions."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.services.bdm_appointments import today_ist
from app.services.bdm_tasks import is_overdue, permissions


def test_overdue_uses_the_ist_date():
    """AC2: at 18:31 UTC on 22 Sep it is already 23 Sep in India -- a task due 23 Sep is today, one due 22 Sep is overdue."""
    today = today_ist(datetime(2026, 9, 22, 18, 31, tzinfo=UTC))
    assert today == date(2026, 9, 23)
    assert not is_overdue("open", date(2026, 9, 23), today)
    assert is_overdue("open", date(2026, 9, 22), today)
    assert today_ist(datetime(2026, 9, 22, 18, 29, tzinfo=UTC)) == date(2026, 9, 22)


def test_done_and_cancelled_are_never_overdue():
    assert not is_overdue("done", date(2020, 1, 1), date(2026, 9, 23))
    assert not is_overdue("cancelled", date(2020, 1, 1), date(2026, 9, 23))


def _task(**over):
    base = {"assignee_user_id": uuid4(), "status": "open", "source": "manual"}
    return SimpleNamespace(**{**base, **over})


def test_permissions_follow_owner_state_and_source():
    owner = SimpleNamespace(id=uuid4(), role="bdm")
    manual = _task(assignee_user_id=owner.id)
    assert permissions(owner, manual) == {"can_edit": True, "can_complete": True, "can_cancel": True}
    outcome = _task(assignee_user_id=owner.id, source="appointment_outcome")
    assert permissions(owner, outcome) == {"can_edit": False, "can_complete": True, "can_cancel": False}
    assert permissions(owner, _task(assignee_user_id=owner.id, status="done")) == {"can_edit": False, "can_complete": False, "can_cancel": False}
    manager = SimpleNamespace(id=uuid4(), role="bdm_manager")
    assert not any(permissions(manager, manual).values())
    other = SimpleNamespace(id=uuid4(), role="bdm")
    assert not any(permissions(other, manual).values())
```

- [ ] **Step 2: Run** — FAIL `ModuleNotFoundError: app.services.bdm_tasks`.
- [ ] **Step 3: Implement** `apps/api/app/services/bdm_tasks.py`

```python
"""bdm-008 (DEC-SCOPE-074, spec §5-§7): follow-up and task scope, buckets, counts, permissions and output.

Functions only; nothing here commits -- the route owns the transaction. Every `{task_id}` resolves through the caller's scope in SQL,
so another BDM's task is the same 404 as a missing one. Lock order: an outcome follow-up's appointment before the task (bdm-007's
order); an organization before its tasks. Logs and audit carry ids, kind, source, field names and counts -- never title, notes or
reason text.
"""

import logging
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BDM_ORG_TYPES, AuditLog, BdmAppointment, BdmOrganization, BdmProfile, BdmTask, User
from app.services.bdm import bdm_context, person_ref
from app.services.bdm_activities import day_range

logger = logging.getLogger("app.bdm")

NOT_FOUND = "Task not found"
OWNER_ONLY = "Only the assigned BDM can change this task"
STATE_REFUSALS = {"done": "This task is already done", "cancelled": "This task was cancelled"}
FROM_REPORT = "Change this follow-up from its meeting report"
PAST_DUE = "Due date can't be in the past"
NOT_ASSIGNED = "Only the assigned BDM can add tasks for this organization"
ARCHIVED = "This organization is archived — restore it before adding tasks"
ORG_ARCHIVED = "Organization archived"
DAILY_CAP = 200  # an abuse bound, far above real use (bdm-009 V10's pattern); the route words the 409 from it
TABS = ("today", "overdue", "upcoming", "done", "cancelled")
ORG_JOIN = BdmOrganization.id == BdmTask.organization_id


async def caller_filters(db: AsyncSession, user: User) -> list:
    """Read scope: a BDM their own items; a manager their team's (sub-select, so a row lock never touches bdm_profiles); super_admin
    all; any other role 403."""
    if user.role == "bdm":
        await bdm_context(db, user)
        return [BdmTask.assignee_user_id == user.id]
    if user.role == "bdm_manager":
        team = select(BdmProfile.user_id).where(BdmProfile.reporting_manager_user_id == user.id)
        return [BdmTask.assignee_user_id.in_(team)]
    if user.role == "super_admin":
        return []
    raise HTTPException(403, "BDM role required")


def bucket_filter(bucket: str, today: date):
    is_open = BdmTask.status == "open"
    return {
        "today": and_(is_open, BdmTask.due_on == today),
        "overdue": and_(is_open, BdmTask.due_on < today),
        "upcoming": and_(is_open, BdmTask.due_on > today),
        "open": is_open,
        "done": BdmTask.status == "done",
        "cancelled": BdmTask.status == "cancelled",
    }[bucket]


def org_type_filter(org_type: str):
    """`none` = no organization. Every query here outer-joins the organization, so the type is read from the join."""
    return BdmTask.organization_id.is_(None) if org_type == "none" else BdmOrganization.org_type == org_type


def is_overdue(status: str, due_on: date, today: date) -> bool:
    return status == "open" and due_on < today


def permissions(user: User, task: BdmTask) -> dict[str, bool]:
    """F2/F3/F4: only the assigned BDM writes; outcome follow-ups are only completed here (their date lives on the appointment)."""
    can_complete = user.role == "bdm" and task.assignee_user_id == user.id and task.status == "open"
    can_change = can_complete and task.source == "manual"
    return {"can_edit": can_change, "can_complete": can_complete, "can_cancel": can_change}


def _ordering(bucket: str) -> tuple:
    if bucket == "done":
        return (BdmTask.completed_at.desc(), BdmTask.id)
    if bucket == "cancelled":
        return (BdmTask.cancelled_at.desc(), BdmTask.id)
    return (BdmTask.due_on, BdmTask.created_at, BdmTask.id)


def _rows():
    """One page query: organization (outer), assignee and source appointment code (outer) -- no N+1."""
    return (
        select(BdmTask, BdmOrganization, User, BdmAppointment.code)
        .select_from(BdmTask)
        .outerjoin(BdmOrganization, ORG_JOIN)
        .join(User, User.id == BdmTask.assignee_user_id)
        .outerjoin(BdmAppointment, BdmAppointment.id == BdmTask.source_appointment_id)
    )


def _count(*filters):
    return select(func.count()).select_from(BdmTask).outerjoin(BdmOrganization, ORG_JOIN).where(*filters)


def _out(user: User, task: BdmTask, org: BdmOrganization | None, assignee: User, appt_code: str | None, today: date) -> dict:
    return {
        "id": task.id, "kind": task.kind, "title": task.title, "notes": task.notes, "due_on": task.due_on, "status": task.status,
        "source": task.source, "overdue": is_overdue(task.status, task.due_on, today),
        "organization": None if org is None else {
            "id": org.id, "code": org.code, "name": org.name, "org_type": org.org_type, "archived": org.archived_at is not None,
        },
        "appointment": None if task.source_appointment_id is None else {"id": task.source_appointment_id, "code": appt_code},
        "assignee": person_ref(assignee),
        "completed_at": task.completed_at, "cancelled_at": task.cancelled_at, "cancel_reason": task.cancel_reason,
        "created_at": task.created_at, "updated_at": task.updated_at,
        "permissions": permissions(user, task),
    }


async def _bucket_counts(db: AsyncSession, filters: list, today: date) -> dict:
    row = (await db.execute(
        select(*(func.count().filter(bucket_filter(b, today)) for b in TABS)).select_from(BdmTask).outerjoin(BdmOrganization, ORG_JOIN).where(*filters)
    )).one()
    return dict(zip(TABS, (n or 0 for n in row), strict=True))


async def _type_counts(db: AsyncSession, filters: list) -> list[dict]:
    rows = (await db.execute(
        select(BdmOrganization.org_type, func.count()).select_from(BdmTask).outerjoin(BdmOrganization, ORG_JOIN)
        .where(*filters).group_by(BdmOrganization.org_type)
    )).all()
    found = {t: n for t, n in rows}
    return [{"org_type": t, "count": found[t]} for t in (*BDM_ORG_TYPES, None) if found.get(t)]


async def page(db: AsyncSession, user: User, base: list, bucket: str, org_type: str | None, today: date, limit: int, offset: int) -> dict:
    """AC4: the tab counts use every filter but the bucket; the type counts every filter but the type -- so they add up to the list."""
    in_bucket = bucket_filter(bucket, today)
    of_type = [org_type_filter(org_type)] if org_type else []
    filters = [*base, in_bucket, *of_type]
    total = await db.scalar(_count(*filters))
    rows = (await db.execute(_rows().where(*filters).order_by(*_ordering(bucket)).limit(limit).offset(offset))).all()
    return {
        "items": [_out(user, t, o, u, code, today) for t, o, u, code in rows],
        "total": total or 0, "limit": limit, "offset": offset, "today": today,
        "counts": {"buckets": await _bucket_counts(db, [*base, *of_type], today), "by_org_type": await _type_counts(db, [*base, in_bucket])},
    }


async def one(db: AsyncSession, user: User, task_id: UUID, today: date) -> dict:
    """The row as written (populate_existing: never a stale identity-map copy after a commit)."""
    task, org, assignee, code = (await db.execute(_rows().where(BdmTask.id == task_id).execution_options(populate_existing=True))).one()
    return _out(user, task, org, assignee, code, today)


async def load_for_write(db: AsyncSession, user: User, task_id: UUID, action: str) -> BdmTask:
    """§6.6 steps 1-3: scope (404); locks in the global order (an outcome follow-up's appointment first); then the owner (403)."""
    task = await db.scalar(select(BdmTask).where(BdmTask.id == task_id, *await caller_filters(db, user)))
    if task is None:
        raise HTTPException(404, NOT_FOUND)
    if task.source_appointment_id is not None:
        await db.execute(select(BdmAppointment.id).where(BdmAppointment.id == task.source_appointment_id).with_for_update())
    locked = await db.scalar(select(BdmTask).where(BdmTask.id == task_id).with_for_update().execution_options(populate_existing=True))
    assert locked is not None  # RESTRICT foreign keys: a task row is never deleted
    if user.role != "bdm" or locked.assignee_user_id != user.id:
        logger.warning("bdm_task_write_refused", extra={"extra_fields": {"actor_id": str(user.id), "task_id": str(task_id), "action": action}})
        raise HTTPException(403, OWNER_ONLY)
    return locked


def require_open(task: BdmTask) -> None:
    if task.status != "open":
        raise HTTPException(409, STATE_REFUSALS[task.status])


def require_manual(task: BdmTask) -> None:
    if task.source != "manual":
        raise HTTPException(409, FROM_REPORT)


async def created_today(db: AsyncSession, user_id: UUID, today: date) -> int:
    """The daily cap's count (create only). A soft bound: two concurrent saves may pass it by one (bdm-009 V10's accepted race)."""
    start, end = day_range(today)
    count = await db.scalar(select(func.count()).select_from(BdmTask).where(
        BdmTask.assignee_user_id == user_id, BdmTask.source == "manual", BdmTask.created_at >= start, BdmTask.created_at < end))
    return count or 0


async def cancel_open_for_organization(db: AsyncSession, org_id: UUID) -> int:
    """F6: the archive's transaction (the caller holds the organization lock) cancels every assignee's open items on it."""
    result = await db.execute(
        update(BdmTask).where(BdmTask.organization_id == org_id, BdmTask.status == "open")
        .values(status="cancelled", cancelled_at=func.now(), cancel_reason=ORG_ARCHIVED, updated_at=func.now())
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


def audit(db: AsyncSession, user: User, action: str, task_id, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed); ids, kind, source, field names only."""
    db.add(AuditLog(user_id=user.id, action=f"bdm_task.{action}", entity_type="bdm_task", entity_id=str(task_id), metadata_json=metadata or {}))


def log(event: str, user: User, task_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "task_id": str(task_id), **extra}})
```

Check `day_range(day)` returns the UTC `(start, end)` of the IST day (`bdm_activities.py:42`).

- [ ] **Step 4: Run** `tests/test_bdm_008_service.py` — PASS. **Step 5: Commit** `feat(bdm-008): task service -- scope, IST buckets, counts, permissions`

---

### Task 5: List route

**Files:** Create `apps/api/app/api/bdm_tasks.py`; Modify `apps/api/app/main.py` (import + router tuple); Create `apps/api/tests/bdm008_helpers.py`; Test `apps/api/tests/test_bdm_008_tasks.py`

**Interfaces — Produces:** `router` (prefix `/bdm/tasks`); helpers `TASKS`, `ist_day(n) -> date`, `insert_task(db, assignee_id, **)`, `create_task(client, **) -> dict`, `listed(client, **params) -> dict`.

- [ ] **Step 1: Helpers** `apps/api/tests/bdm008_helpers.py`

```python
"""bdm-008 test builders (on bdm-006's). Unique per call: the shared test database is never truncated, so every test uses fresh BDMs."""

from datetime import date, datetime, timedelta

from sqlalchemy import func

from app.models import BdmTask
from app.services.bdm_appointments import IST

TASKS = "/api/v1/bdm/tasks"


def ist_day(n: int = 0) -> date:
    return (datetime.now(IST) + timedelta(days=n)).date()


def task_body(**over) -> dict:
    return {"kind": "task", "title": "Send brochure", "due_on": ist_day().isoformat(), **over}


async def create_task(client, **over) -> dict:
    response = await client.post(TASKS, json=task_body(**over))
    assert response.status_code == 201, response.text
    return response.json()


async def insert_task(db, assignee_id, *, due_on: date | None = None, org_id=None, kind="follow_up", status="open", source="manual",
                      title="Seeded") -> BdmTask:
    """A row the API can't create (a past due date, a done / cancelled state, an `mou` source)."""
    task = BdmTask(
        kind=kind, title=title, due_on=due_on or ist_day(), organization_id=org_id, source=source, assignee_user_id=assignee_id, status=status,
        completed_at=func.now() if status == "done" else None,
        cancelled_at=func.now() if status == "cancelled" else None, cancel_reason="Seeded" if status == "cancelled" else None,
    )
    db.add(task)
    await db.commit()
    return task


async def listed(client, **params) -> dict:
    response = await client.get(TASKS, params=params)
    assert response.status_code == 200, response.text
    return response.json()
```

- [ ] **Step 2: Failing tests** `apps/api/tests/test_bdm_008_tasks.py` (list part)

```python
"""bdm-008 -- the follow-ups list, create, edit, complete and cancel (spec §5, §6; AC1-AC6, AC8)."""

import logging

import pytest
from sqlalchemy import select

from app.models import AuditLog, BdmTask
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm006_helpers import bdm_with_org
from tests.bdm007_helpers import completed
from tests.bdm008_helpers import TASKS, create_task, insert_task, ist_day, listed


@pytest.mark.asyncio
async def test_buckets_split_open_items_on_the_ist_date(client, db_session):
    """AC2: due yesterday = overdue, today = today, tomorrow = upcoming; each row says whether it is overdue."""
    _, bdm, _ = await bdm_with_org(client, db_session)
    for n in (-1, 0, 1):
        await insert_task(db_session, bdm.id, due_on=ist_day(n), title=f"d{n}")
    today = await listed(client)
    assert today["today"] == ist_day().isoformat() and [t["title"] for t in today["items"]] == ["d0"]
    assert [(t["title"], t["overdue"]) for t in (await listed(client, bucket="overdue"))["items"]] == [("d-1", True)]
    assert [t["title"] for t in (await listed(client, bucket="upcoming"))["items"]] == ["d1"]
    assert today["counts"]["buckets"] == {"today": 1, "overdue": 1, "upcoming": 1, "done": 0, "cancelled": 0}


@pytest.mark.asyncio
async def test_outcome_follow_up_is_listed_with_its_appointment(client, db_session):
    """AC1: a meeting report's follow-up date shows here, linked to its appointment, complete-only (AC6)."""
    _, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org, next_follow_up_on=ist_day(2).isoformat())
    [item] = (await listed(client, bucket="upcoming"))["items"]
    assert (item["source"], item["kind"], item["appointment"], item["organization"]["id"]) == (
        "appointment_outcome", "follow_up", {"id": a["id"], "code": a["code"]}, org["id"])
    assert item["permissions"] == {"can_edit": False, "can_complete": True, "can_cancel": False}


@pytest.mark.asyncio
async def test_counts_match_the_list(client, db_session):
    """AC4: type counts sum to the total; a type filter's total equals that type's count; tab counts equal each tab's total."""
    _, bdm, college = await bdm_with_org(client, db_session)
    university = await create_org(client, org_type="university")
    for org_id in (college["id"], college["id"], university["id"], None):
        await insert_task(db_session, bdm.id, org_id=org_id)
    await insert_task(db_session, bdm.id, org_id=college["id"], status="done")
    page = await listed(client)
    assert page["counts"]["by_org_type"] == [{"org_type": "college", "count": 2}, {"org_type": "university", "count": 1}, {"org_type": None, "count": 1}]
    assert sum(c["count"] for c in page["counts"]["by_org_type"]) == page["total"] == 4
    filtered = await listed(client, org_type="college")
    assert filtered["total"] == 2 and {t["organization"]["org_type"] for t in filtered["items"]} == {"college"}
    assert filtered["counts"]["by_org_type"] == page["counts"]["by_org_type"]  # the chips keep showing every type
    assert (await listed(client, org_type="none"))["total"] == 1
    for tab, n in filtered["counts"]["buckets"].items():
        assert (await listed(client, bucket=tab, org_type="college"))["total"] == n


@pytest.mark.asyncio
async def test_done_and_cancelled_are_kept_and_ordered_newest_first(client, db_session):
    """AC3."""
    _, bdm, _ = await bdm_with_org(client, db_session)
    await insert_task(db_session, bdm.id, status="done", title="d1")
    await insert_task(db_session, bdm.id, status="done", title="d2")
    await insert_task(db_session, bdm.id, status="cancelled", title="c1")
    done = await listed(client, bucket="done")
    assert {t["title"] for t in done["items"]} == {"d1", "d2"} and all(t["completed_at"] for t in done["items"])
    [c] = (await listed(client, bucket="cancelled"))["items"]
    assert (c["title"], c["cancel_reason"], c["overdue"]) == ("c1", "Seeded", False)


@pytest.mark.asyncio
async def test_list_refuses_bad_filters(client, db_session):
    await bdm_with_org(client, db_session)
    for params in ({"bucket": "soon"}, {"org_type": "hospital"}, {"kind": "meeting"}, {"limit": 101}):
        assert (await client.get(TASKS, params=params)).status_code == 422
    other = await client.get(TASKS, params={"bdm_user_id": "00000000-0000-0000-0000-000000000000"})
    assert (other.status_code, other.json()["detail"]) == (422, "bdm_user_id is only for managers")
```

- [ ] **Step 3: Run** — FAIL (404 on `/api/v1/bdm/tasks`).
- [ ] **Step 4: Implement** `apps/api/app/api/bdm_tasks.py` (list only for now)

```python
"""bdm-008 (DEC-SCOPE-074, spec §6): BDM follow-ups and tasks.

Every `{task_id}` resolves through `services.bdm_tasks` scope (out of scope = 404); every write is one transaction -- scope, locks
(appointment or organization before the task), owner, state, validation, change, audit, one commit here, log. Lists carry the
counts the tabs and type chips show, computed from the same filters."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BdmTask, User
from app.schemas import BdmTaskBucket, BdmTaskKind, BdmTaskOrgType, BdmTaskPage
from app.services import bdm_tasks as svc
from app.services.bdm_appointments import db_now, today_ist

router = APIRouter(prefix="/bdm/tasks", tags=["bdm-tasks"])


@router.get("", response_model=BdmTaskPage)
async def list_tasks(
    bucket: BdmTaskBucket = "today",
    kind: BdmTaskKind | None = None,
    org_type: BdmTaskOrgType | None = None,
    organization_id: UUID | None = None,
    bdm_user_id: UUID | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Filters are ANDed with the caller's scope, so they only narrow it (bdm-006 R-A10)."""
    base = await svc.caller_filters(db, user)
    if bdm_user_id is not None:
        if user.role == "bdm":
            raise HTTPException(422, "bdm_user_id is only for managers")
        base.append(BdmTask.assignee_user_id == bdm_user_id)
    if kind:
        base.append(BdmTask.kind == kind)
    if organization_id:
        base.append(BdmTask.organization_id == organization_id)
    return await svc.page(db, user, base, bucket, org_type, today_ist(await db_now(db)), limit, offset)
```

`main.py`: add `bdm_tasks,` to the `from app.api import (...)` list and `bdm_tasks.router` after `bdm_activities.router` in the tuple.

- [ ] **Step 5: Run** `tests/test_bdm_008_tasks.py` — PASS. **Step 6: Commit** `feat(bdm-008): GET /bdm/tasks with IST buckets and counts`

---

### Task 6: Create

**Files:** Modify `apps/api/app/api/bdm_tasks.py`; Test: append to `apps/api/tests/test_bdm_008_tasks.py`

- [ ] **Step 1: Failing tests**

```python
@pytest.mark.asyncio
async def test_create_a_manual_task_with_and_without_an_organization(client, db_session):
    """AC1: manual items; the server owns assignee, source and status."""
    _, bdm, org = await bdm_with_org(client, db_session)
    t = await create_task(client, kind="follow_up", organization_id=org["id"], notes="Ask for\nthe prospectus", due_on=ist_day(1).isoformat())
    assert (t["source"], t["status"], t["assignee"]["id"], t["notes"], t["organization"]["code"]) == ("manual", "open", str(bdm.id), "Ask for\nthe prospectus", org["code"])
    assert t["permissions"] == {"can_edit": True, "can_complete": True, "can_cancel": True}
    general = await create_task(client)
    assert general["organization"] is None and general["kind"] == "task"


@pytest.mark.asyncio
async def test_create_refusals(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    past = await client.post(TASKS, json={"kind": "task", "title": "x", "due_on": ist_day(-1).isoformat()})
    assert (past.status_code, past.json()["detail"]) == (422, "Due date can't be in the past")
    other = await make_bdm(db_session, manager)
    await login(client, other)
    theirs = await client.post(TASKS, json={"kind": "task", "title": "x", "due_on": ist_day().isoformat(), "organization_id": org["id"]})
    assert (theirs.status_code, theirs.json()["detail"]) == (403, "Only the assigned BDM can add tasks for this organization")
    await login(client, bdm)
    assert (await client.post(f"/api/v1/bdm/organizations/{org['id']}/archive")).status_code == 200
    archived = await client.post(TASKS, json={"kind": "task", "title": "x", "due_on": ist_day().isoformat(), "organization_id": org["id"]})
    assert (archived.status_code, archived.json()["detail"]) == (422, "This organization is archived — restore it before adding tasks")
    await login(client, manager)
    assert (await client.post(TASKS, json={"kind": "task", "title": "x", "due_on": ist_day().isoformat()})).status_code == 403


@pytest.mark.asyncio
async def test_create_cap(client, db_session, monkeypatch):
    from app.services import bdm_tasks

    monkeypatch.setattr(bdm_tasks, "DAILY_CAP", 1)
    await bdm_with_org(client, db_session)
    await create_task(client)
    again = await client.post(TASKS, json={"kind": "task", "title": "x", "due_on": ist_day().isoformat()})
    assert again.status_code == 409
```

(The cap message is built from the module constant at import time; the test asserts only the status.)

- [ ] **Step 2: Run** — FAIL (405 Method Not Allowed).
- [ ] **Step 3: Implement** (append to `api/bdm_tasks.py`; extend imports with `BdmTaskCreate`, `BdmTaskOut`, `bdm_organizations as org_svc`, `bdm_context`)

```python
@router.post("", status_code=201, response_model=BdmTaskOut)
async def create_task(payload: BdmTaskCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§6.2, in this order so each refusal is exactly one rule. Not idempotent (a retry adds a second task; the cap bounds abuse)."""
    await bdm_context(db, user)
    if payload.organization_id is not None:
        org = await org_svc.load_scoped(db, user, payload.organization_id, lock=True)  # out of type scope -> 404; serializes with archive
        if org.assigned_bdm_user_id != user.id:
            raise HTTPException(403, svc.NOT_ASSIGNED)
        if org.archived_at is not None:
            raise HTTPException(422, svc.ARCHIVED)
    today = today_ist(await db_now(db))
    if payload.due_on < today:
        raise HTTPException(422, svc.PAST_DUE)
    if await svc.created_today(db, user.id, today) >= svc.DAILY_CAP:
        raise HTTPException(409, f"You've added {svc.DAILY_CAP} tasks today")
    task = BdmTask(
        kind=payload.kind, title=payload.title, notes=payload.notes, due_on=payload.due_on, organization_id=payload.organization_id,
        source="manual", assignee_user_id=user.id, status="open",
    )
    db.add(task)
    await db.flush()
    svc.audit(db, user, "create", task.id, {"kind": task.kind, "organization": task.organization_id is not None})
    await db.commit()
    svc.log("bdm_task_created", user, task.id, kind=task.kind)
    return await svc.one(db, user, task.id, today)
```

The cap is read from `svc.DAILY_CAP` at request time, so the test's monkeypatch applies.

- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `feat(bdm-008): POST /bdm/tasks`

---

### Task 7: Edit, complete, cancel

**Files:** Modify `apps/api/app/api/bdm_tasks.py`; Tests: append to `test_bdm_008_tasks.py`; create `apps/api/tests/test_bdm_008_scope.py`

- [ ] **Step 1: Failing tests** — append to `test_bdm_008_tasks.py`:

```python
def url(t: dict, action: str = "") -> str:
    return f"{TASKS}/{t['id']}{'/' + action if action else ''}"


@pytest.mark.asyncio
async def test_edit_changes_only_what_differs(client, db_session):
    await bdm_with_org(client, db_session)
    t = await create_task(client, notes="old")
    same = (await client.patch(url(t), json={"title": t["title"]})).json()
    assert same["updated_at"] == t["updated_at"]  # nothing changed: no bump, no audit
    moved = (await client.patch(url(t), json={"due_on": ist_day(3).isoformat(), "notes": None})).json()
    assert (moved["due_on"], moved["notes"]) == (ist_day(3).isoformat(), None)
    rows = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == t["id"], AuditLog.action == "bdm_task.update"))).all()
    assert rows == [{"fields": ["due_on", "notes"]}]
    past = await client.patch(url(t), json={"due_on": ist_day(-1).isoformat()})
    assert (past.status_code, past.json()["detail"]) == (422, "Due date can't be in the past")


@pytest.mark.asyncio
async def test_unchanged_past_due_date_is_accepted(client, db_session):
    """Review Focus 4: an overdue task's title can still be corrected."""
    _, bdm, _ = await bdm_with_org(client, db_session)
    seeded = await insert_task(db_session, bdm.id, due_on=ist_day(-5))
    fixed = await client.patch(f"{TASKS}/{seeded.id}", json={"title": "Call back", "due_on": ist_day(-5).isoformat()})
    assert fixed.status_code == 200 and fixed.json()["title"] == "Call back"


@pytest.mark.asyncio
async def test_complete_then_everything_is_final(client, db_session):
    """AC3: done is kept and final."""
    await bdm_with_org(client, db_session)
    t = await create_task(client)
    done = (await client.post(url(t, "complete"))).json()
    assert done["status"] == "done" and done["completed_at"] and not any(done["permissions"].values())
    for method, path, body in (("post", "complete", None), ("post", "cancel", {"reason": "x"}), ("patch", "", {"title": "y"})):
        refused = await client.request(method.upper(), url(t, path), json=body)
        assert (refused.status_code, refused.json()["detail"]) == (409, "This task is already done")


@pytest.mark.asyncio
async def test_cancel_needs_a_reason_and_is_kept(client, db_session):
    await bdm_with_org(client, db_session)
    t = await create_task(client)
    assert (await client.post(url(t, "cancel"), json={"reason": "  "})).status_code == 422
    c = (await client.post(url(t, "cancel"), json={"reason": "Principal on leave"})).json()
    assert (c["status"], c["cancel_reason"]) == ("cancelled", "Principal on leave") and c["cancelled_at"]
    refused = await client.post(url(t, "complete"))
    assert (refused.status_code, refused.json()["detail"]) == (409, "This task was cancelled")


@pytest.mark.asyncio
async def test_outcome_follow_up_is_complete_only(client, db_session):
    """AC6 / F2."""
    _, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org, next_follow_up_on=ist_day(1).isoformat())
    task = {"id": a["follow_up"]["id"]}
    for method, path, body in (("patch", "", {"title": "y"}), ("post", "cancel", {"reason": "x"})):
        refused = await client.request(method.upper(), url(task, path), json=body)
        assert (refused.status_code, refused.json()["detail"]) == (409, "Change this follow-up from its meeting report")
    assert (await client.post(url(task, "complete"))).json()["status"] == "done"


@pytest.mark.asyncio
async def test_no_task_text_in_audit_or_logs(client, db_session, caplog):
    """AC8."""
    await bdm_with_org(client, db_session)
    caplog.set_level(logging.INFO, logger="app.bdm")
    t = await create_task(client, title="SECRET-TITLE", notes="SECRET-NOTES")
    await client.patch(url(t), json={"title": "SECRET-TITLE-2"})
    await client.post(url(t, "cancel"), json={"reason": "SECRET-REASON"})
    metadata = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == t["id"]))).all()
    assert len(metadata) == 3 and "SECRET" not in repr(metadata) and "SECRET" not in caplog.text
```

`apps/api/tests/test_bdm_008_scope.py`:

```python
"""bdm-008 -- who reads and who writes (spec §6.6, §8; AC5; Review Focus 5)."""

import logging

import pytest

from app.models import BdmTask
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm006_helpers import bdm_with_org
from tests.bdm008_helpers import TASKS, create_task, listed


@pytest.mark.asyncio
async def test_another_bdm_gets_404_everywhere(client, db_session):
    manager, _, _ = await bdm_with_org(client, db_session)
    t = await create_task(client)
    await login(client, await make_bdm(db_session, manager))
    for method, path, body in (("PATCH", "", {"title": "x"}), ("POST", "/complete", None), ("POST", "/cancel", {"reason": "x"})):
        r = await client.request(method, f"{TASKS}/{t['id']}{path}", json=body)
        assert (r.status_code, r.json()["detail"]) == (404, "Task not found")
    assert (await listed(client))["total"] == 0


@pytest.mark.asyncio
async def test_manager_reads_the_team_and_cannot_write(client, db_session, caplog):
    manager, bdm, _ = await bdm_with_org(client, db_session)
    t = await create_task(client)
    await login(client, manager)
    page = await listed(client)
    assert [i["id"] for i in page["items"]] == [t["id"]] and not any(page["items"][0]["permissions"].values())
    assert (await listed(client, bdm_user_id=str(bdm.id)))["total"] == 1
    caplog.set_level(logging.WARNING, logger="app.bdm")
    r = await client.post(f"{TASKS}/{t['id']}/complete")
    assert (r.status_code, r.json()["detail"]) == (403, "Only the assigned BDM can change this task")
    assert "bdm_task_write_refused" in caplog.text
    row = await db_session.get(BdmTask, t["id"], populate_existing=True)
    assert row.status == "open"


@pytest.mark.asyncio
async def test_other_manager_and_filters_never_widen_scope(client, db_session):
    _, bdm, _ = await bdm_with_org(client, db_session)
    await create_task(client)
    await login(client, await make_manager(db_session))
    assert (await listed(client))["total"] == 0
    assert (await listed(client, bdm_user_id=str(bdm.id)))["total"] == 0


@pytest.mark.asyncio
async def test_super_admin_reads_all_and_other_roles_are_refused(client, db_session):
    _, bdm, _ = await bdm_with_org(client, db_session)
    t = await create_task(client)
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert t["id"] in [i["id"] for i in (await listed(client, bdm_user_id=str(bdm.id)))["items"]]
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(TASKS)).status_code == 403
```

(`make_user` division for super_admin: use what `bdm001_helpers`/existing tests use for super_admin — check `grep -n "super_admin" tests/test_bdm_006_*.py` and copy.)

- [ ] **Step 2: Run** — FAIL (405).
- [ ] **Step 3: Implement** (append to `api/bdm_tasks.py`; imports `BdmTaskUpdate`, `BdmAppointmentReason`)

```python
@router.patch("/{task_id}", response_model=BdmTaskOut)
async def update_task(task_id: UUID, payload: BdmTaskUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§6.3. Values equal to the stored ones are not changes (no audit, no updated_at bump); only a changed due date must be today or later."""
    task = await svc.load_for_write(db, user, task_id, "update")
    svc.require_open(task)
    svc.require_manual(task)
    today = today_ist(await db_now(db))
    changes = payload.model_dump(exclude_unset=True)
    changed = sorted(k for k, v in changes.items() if getattr(task, k) != v)
    if "due_on" in changed and changes["due_on"] < today:
        raise HTTPException(422, svc.PAST_DUE)
    for key in changed:
        setattr(task, key, changes[key])
    if changed:
        svc.audit(db, user, "update", task.id, {"fields": changed})
    await db.commit()
    if changed:
        svc.log("bdm_task_updated", user, task.id, fields=changed)
    return await svc.one(db, user, task.id, today)


@router.post("/{task_id}/complete", response_model=BdmTaskOut)
async def complete_task(task_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Any open item of the assignee, outcome follow-ups included (F2). A second complete meets `done` under the lock -> 409."""
    task = await svc.load_for_write(db, user, task_id, "complete")
    svc.require_open(task)
    now = await db_now(db)
    task.status, task.completed_at = "done", now
    svc.audit(db, user, "complete", task.id, {"source": task.source})
    await db.commit()
    svc.log("bdm_task_completed", user, task.id, source=task.source)
    return await svc.one(db, user, task.id, today_ist(now))


@router.post("/{task_id}/cancel", response_model=BdmTaskOut)
async def cancel_task(task_id: UUID, payload: BdmAppointmentReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Manual items only (F3); the reason is kept and never logged."""
    task = await svc.load_for_write(db, user, task_id, "cancel")
    svc.require_open(task)
    svc.require_manual(task)
    now = await db_now(db)
    task.status, task.cancelled_at, task.cancel_reason = "cancelled", now, payload.reason
    svc.audit(db, user, "cancel", task.id)
    await db.commit()
    svc.log("bdm_task_cancelled", user, task.id)
    return await svc.one(db, user, task.id, today_ist(now))
```

- [ ] **Step 4: Run** `tests/test_bdm_008_tasks.py tests/test_bdm_008_scope.py` — PASS. **Step 5: Commit** `feat(bdm-008): edit, complete and cancel a task`

---

### Task 8: Concurrency

**Files:** Test `apps/api/tests/test_bdm_008_concurrency.py` (fix code only if a test fails)

- [ ] **Step 1: Tests**

```python
"""bdm-008 -- races (spec §7). Two real sessions through the app (bdm-006/007 pattern)."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models import BdmTask
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm006_helpers import create_appt, move_to_past
from tests.bdm007_helpers import REPORT
from tests.bdm008_helpers import TASKS, ist_day, task_body


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _logged_in(db, one: AsyncClient, two: AsyncClient) -> None:
    """Two sessions of one fresh BDM (call inside `async with` -- an httpx client opens once)."""
    bdm = await make_bdm(db, await make_manager(db))
    await login(one, bdm)
    await login(two, bdm)


@pytest.mark.asyncio
async def test_double_complete(db_session):
    async with _client() as one, _client() as two:
        await _logged_in(db_session, one, two)
        t = (await one.post(TASKS, json=task_body())).json()
        results = await asyncio.gather(one.post(f"{TASKS}/{t['id']}/complete"), two.post(f"{TASKS}/{t['id']}/complete"))
    assert sorted(r.status_code for r in results) == [200, 409]


@pytest.mark.asyncio
async def test_complete_and_report_date_edit_serialize_on_the_appointment(db_session):
    async with _client() as one, _client() as two:
        await _logged_in(db_session, one, two)
        org = await create_org(one)
        a = await create_appt(one, org)
        await move_to_past(db_session, a["id"])
        a = (await one.post(f"/api/v1/bdm/appointments/{a['id']}/complete", json={**REPORT, "next_follow_up_on": ist_day(2).isoformat()})).json()["appointment"]
        done, edit = await asyncio.gather(
            one.post(f"{TASKS}/{a['follow_up']['id']}/complete"),
            two.patch(f"/api/v1/bdm/appointments/{a['id']}/report", json={"next_follow_up_on": ist_day(4).isoformat()}),
        )
    assert done.status_code == 200 and edit.status_code in (200, 409)
    row = (await db_session.execute(select(BdmTask.status, BdmTask.due_on).where(BdmTask.id == a["follow_up"]["id"]).execution_options(populate_existing=True))).one()
    assert row.status == "done"  # never reopened or duplicated


@pytest.mark.asyncio
async def test_create_and_archive_serialize_on_the_organization(db_session):
    async with _client() as one, _client() as two:
        await _logged_in(db_session, one, two)
        org = await create_org(one)
        created, archived = await asyncio.gather(
            one.post(TASKS, json=task_body(organization_id=org["id"])), two.post(f"/api/v1/bdm/organizations/{org['id']}/archive"))
    assert archived.status_code == 200 and created.status_code in (201, 422)
    rows = (await db_session.scalars(select(BdmTask.status).where(BdmTask.organization_id == org["id"]).execution_options(populate_existing=True))).all()
    assert all(s == "cancelled" for s in rows)  # a task created first was cancelled by the archive; none is left open
```

- [ ] **Step 2: Run** — Expected PASS (the locks from Tasks 4–7). If a test deadlocks or fails, fix the lock order in `load_for_write` / the archive per spec §7 before continuing.
- [ ] **Step 3: Commit** `test(bdm-008): races on complete, report edit and archive`

---

### Task 9: Archive cancels open items

**Files:** Modify `apps/api/app/api/bdm_organizations.py` (`_set_archived`); Test `apps/api/tests/test_bdm_008_archive.py`

- [ ] **Step 1: Failing tests**

```python
"""bdm-008 -- archiving an organization cancels its open items (F6, AC7)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.bdm006_helpers import bdm_with_org
from tests.bdm007_helpers import completed
from tests.bdm008_helpers import TASKS, create_task, insert_task, ist_day, listed

ORGS = "/api/v1/bdm/organizations"


@pytest.mark.asyncio
async def test_archive_cancels_open_items_and_restore_keeps_them_cancelled(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    manual = await create_task(client, organization_id=org["id"])
    a = await completed(client, db_session, org, next_follow_up_on=ist_day(1).isoformat())
    done = await insert_task(db_session, bdm.id, org_id=org["id"], status="done")
    general = await create_task(client)
    assert (await client.post(f"{ORGS}/{org['id']}/archive")).status_code == 200
    cancelled = {t["id"]: t for t in (await listed(client, bucket="cancelled"))["items"]}
    assert {manual["id"], a["follow_up"]["id"]} == set(cancelled) and all(t["cancel_reason"] == "Organization archived" for t in cancelled.values())
    assert [t["id"] for t in (await listed(client, bucket="done"))["items"]] == [str(done.id)]
    assert [t["id"] for t in (await listed(client))["items"]] == [general["id"]]
    meta = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == org["id"], AuditLog.action == "bdm_organization.archive"))).one()
    assert meta == {"tasks_cancelled": 2}
    from tests.bdm001_helpers import login

    await login(client, manager)
    assert (await client.post(f"{ORGS}/{org['id']}/restore")).status_code == 200
    await login(client, bdm)
    assert (await listed(client, bucket="cancelled"))["total"] == 2


@pytest.mark.asyncio
async def test_archive_with_nothing_open_keeps_todays_audit(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    await client.post(f"{ORGS}/{org['id']}/archive")
    meta = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == org["id"], AuditLog.action == "bdm_organization.archive"))).one()
    assert meta == {}


@pytest.mark.asyncio
async def test_complete_after_archive_is_409(client, db_session):
    """Review Focus 3."""
    _, _, org = await bdm_with_org(client, db_session)
    t = await create_task(client, organization_id=org["id"])
    await client.post(f"{ORGS}/{org['id']}/archive")
    r = await client.post(f"{TASKS}/{t['id']}/complete")
    assert (r.status_code, r.json()["detail"]) == (409, "This task was cancelled")
```

- [ ] **Step 2: Run** — FAIL (items stay open).
- [ ] **Step 3: Implement** — `api/bdm_organizations.py`: `from app.services import bdm_tasks as task_svc`; in `_set_archived` replace the audit/commit/log lines with:

```python
    org.archived_at = datetime.now(UTC) if archive else None
    cancelled = await task_svc.cancel_open_for_organization(db, org.id) if archive else 0  # bdm-008 F6; restore reopens nothing
    extra = {"tasks_cancelled": cancelled} if cancelled else {}
    svc.audit(db, user, action, org.id, extra or None)
    await db.commit()
    svc.log(f"bdm_org_{action}d", user, org.id, **extra)
```

- [ ] **Step 4: Run** `tests/test_bdm_008_archive.py tests/test_bdm_008_concurrency.py tests/test_bdm_002_organizations.py` — PASS. **Step 5: Commit** `feat(bdm-008): archiving an organization cancels its open follow-ups`

---

### Task 10: Web library

**Files:** Create `apps/web/lib/bdmTasks.ts`, `apps/web/lib/bdmTasksServer.ts`; Test `apps/web/tests/lib/bdmTasks.test.ts`

**Interfaces — Produces:** `TASKS_URL`, `TABS`, `Tab`, `TAB_LABEL`, `EMPTY_TEXT`, `KINDS`, `TaskKind`, `KIND_LABEL`, `TITLE_MAX`, `NOTES_MAX`, `TASK_PAGE`,
`Task`, `TaskPage`, `TypeCount`, `TaskQuery`, `taskUrl(id)`, `tasksUrl(q)`, `orgTasksUrl(orgId)`, `isTask`, `isTaskPage`, `orgTypeText`, `taskRuleField`,
`daysOverdue(due, today)`; server `firstTaskPage(orgId)`.

- [ ] **Step 1: Failing test** `apps/web/tests/lib/bdmTasks.test.ts`

```ts
import { describe, expect, it } from "vitest";

import { daysOverdue, isTask, isTaskPage, orgTasksUrl, orgTypeText, taskRuleField, tasksUrl } from "@/lib/bdmTasks";

describe("bdmTasks (bdm-008 §6, §9)", () => {
  it("builds list URLs with only the filters that are set", () => {
    expect(tasksUrl({ bucket: "today" })).toBe("/api/v1/bdm/tasks?bucket=today&limit=50&offset=0");
    expect(tasksUrl({ bucket: "overdue", kind: "task", orgType: "none", bdm: "b1", offset: 50 })).toBe(
      "/api/v1/bdm/tasks?bucket=overdue&limit=50&offset=50&kind=task&org_type=none&bdm_user_id=b1");
    expect(orgTasksUrl("o1")).toBe("/api/v1/bdm/tasks?bucket=open&limit=50&offset=0&organization_id=o1");
  });

  it("guards response shapes", () => {
    expect(isTask({ id: "t", title: "x", due_on: "2030-01-01", permissions: {} })).toBe(true);
    expect(isTask({ id: "t" })).toBe(false);
    expect(isTaskPage({ items: [], total: 0, limit: 50, offset: 0, today: "2030-01-01", counts: { buckets: {}, by_org_type: [] } })).toBe(true);
    expect(isTaskPage({ items: [], total: 0, limit: 50, offset: 0 })).toBe(false);
  });

  it("words types, rules and overdue days", () => {
    expect(orgTypeText("training_institute")).toBe("Training Institute");
    expect(orgTypeText(null)).toBe("No organization");
    expect(taskRuleField("Due date can't be in the past")).toEqual({ due_on: "Due date can't be in the past" });
    expect(taskRuleField("This organization is archived — restore it before adding tasks")).toEqual({ organization_id: "This organization is archived — restore it before adding tasks" });
    expect(taskRuleField("boom")).toEqual({});
    expect(daysOverdue("2026-09-20", "2026-09-23")).toBe(3);
  });
});
```

- [ ] **Step 2: Run** — FAIL (module not found).
- [ ] **Step 3: Implement** `apps/web/lib/bdmTasks.ts`

```ts
import { isPage, type Page } from "@/lib/apiErrors";
import { ORG_TYPE_LABEL, type OrgType } from "@/lib/bdmOrganizations";

// bdm-008 (DEC-SCOPE-074, spec §6, §9): follow-up and task types, labels and URLs. The API decides every rule; `permissions` only tells
// the UI which actions to offer.
export const TASKS_URL = "/api/v1/bdm/tasks";
export const TABS = ["today", "overdue", "upcoming", "done", "cancelled"] as const;
export type Tab = (typeof TABS)[number];
export const TAB_LABEL: Record<Tab, string> = { today: "Today", overdue: "Overdue", upcoming: "Upcoming", done: "Done", cancelled: "Cancelled" };
export const EMPTY_TEXT: Record<Tab, string> = {
  today: "Nothing due today.", overdue: "No overdue follow-ups.", upcoming: "Nothing upcoming.", done: "Nothing done yet.", cancelled: "Nothing cancelled.",
};
export const KINDS = ["follow_up", "task"] as const;
export type TaskKind = (typeof KINDS)[number];
export const KIND_LABEL: Record<TaskKind, string> = { follow_up: "Follow-up", task: "Task" };
export const TITLE_MAX = 200;
export const NOTES_MAX = 2000;
export const TASK_PAGE = 50;

export type Task = {
  id: string; kind: TaskKind; title: string; notes: string | null; due_on: string; status: "open" | "done" | "cancelled";
  source: "appointment_outcome" | "mou" | "manual"; overdue: boolean;
  organization: { id: string; code: string; name: string; org_type: OrgType; archived: boolean } | null;
  appointment: { id: string; code: string } | null; assignee: { id: string; full_name: string; active: boolean };
  completed_at: string | null; cancelled_at: string | null; cancel_reason: string | null; created_at: string; updated_at: string;
  permissions: { can_edit: boolean; can_complete: boolean; can_cancel: boolean };
};
export type TypeCount = { org_type: OrgType | null; count: number };
export type TaskPage = Page<Task> & { today: string; counts: { buckets: Record<Tab, number>; by_org_type: TypeCount[] } };
export type TaskQuery = { bucket: Tab | "open"; kind?: string; orgType?: string; organization?: string; bdm?: string; offset?: number };

export const taskUrl = (id: string) => `${TASKS_URL}/${encodeURIComponent(id)}`;

export function tasksUrl(q: TaskQuery): string {
  const query = new URLSearchParams({ bucket: q.bucket, limit: String(TASK_PAGE), offset: String(q.offset ?? 0) });
  if (q.kind) query.set("kind", q.kind);
  if (q.orgType) query.set("org_type", q.orgType);
  if (q.organization) query.set("organization_id", q.organization);
  if (q.bdm) query.set("bdm_user_id", q.bdm);
  return `${TASKS_URL}?${query}`;
}

export const orgTasksUrl = (orgId: string) => tasksUrl({ bucket: "open", organization: orgId });

export function isTask(data: unknown): data is Task {
  const d = data as Partial<Task> | null;
  return !!d && typeof d.id === "string" && typeof d.title === "string" && typeof d.due_on === "string" && !!d.permissions;
}

export function isTaskPage(data: unknown): data is TaskPage {
  if (!isPage(data)) return false;
  const counts = (data as { counts?: { by_org_type?: unknown } }).counts;
  return !!counts && Array.isArray(counts.by_org_type);
}

export const orgTypeText = (t: OrgType | null) => (t ? ORG_TYPE_LABEL[t] : "No organization");

/** The API answers its date and organization rules as one sentence; put each on the field it is about. */
export function taskRuleField(detail: unknown): Record<string, string> {
  if (typeof detail !== "string") return {};
  if (detail.startsWith("Due date")) return { due_on: detail };
  if (detail.startsWith("This organization") || detail.startsWith("Only the assigned BDM can add")) return { organization_id: detail };
  return {};
}

export function daysOverdue(due: string, today: string): number {
  return Math.round((Date.parse(`${today}T00:00:00Z`) - Date.parse(`${due}T00:00:00Z`)) / 86_400_000);
}
```

`apps/web/lib/bdmTasksServer.ts`:

```ts
import { serverApi } from "@/lib/api";
import { isUuid } from "@/lib/bdmTravel";
import { orgTasksUrl, type TaskPage } from "@/lib/bdmTasks";

// Server-only (serverApi reads next/headers). The organization pages' first page of open items, read alongside the organization. It never
// rejects: a failure is null and the section offers "Try again".
export function firstTaskPage(id: string): Promise<TaskPage | null> {
  return isUuid(id) ? serverApi<TaskPage>(orgTasksUrl(id)).catch(() => null) : Promise.resolve(null);
}
```

- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `feat(bdm-008): web task library`

---

### Task 11: BdmTaskForm

**Files:** Create `apps/web/components/BdmTaskForm.tsx`; Test `apps/web/tests/components/BdmTaskForm.test.tsx`

**Interfaces:** `BdmTaskForm({ task?, organization?, onSaved(task: Task), onCancel() })`.

- [ ] **Step 1: Failing test**

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmTaskForm from "@/components/BdmTaskForm";
import type { Task } from "@/lib/bdmTasks";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const task = (over: Partial<Task> = {}): Task => ({
  id: "t1", kind: "task", title: "Send brochure", notes: null, due_on: "2030-01-07", status: "open", source: "manual", overdue: false,
  organization: null, appointment: null, assignee: { id: "b1", full_name: "Asha", active: true }, completed_at: null, cancelled_at: null,
  cancel_reason: null, created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-01T00:00:00Z",
  permissions: { can_edit: true, can_complete: true, can_cancel: true }, ...over,
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("BdmTaskForm (bdm-008 §9)", () => {
  it("creates with the organization fixed and sends blanks as null", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res(task(), 201)));
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();
    render(<BdmTaskForm organization={{ id: "o1", name: "St Mary" }} onSaved={onSaved} onCancel={vi.fn()} />);
    expect(screen.getByLabelText("Title (required)")).toHaveFocus();
    fireEvent.change(screen.getByLabelText("Title (required)"), { target: { value: "Send brochure" } });
    fireEvent.change(screen.getByLabelText("Due date (IST, required)"), { target: { value: "2030-01-07" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ kind: "follow_up", title: "Send brochure", due_on: "2030-01-07", notes: null, organization_id: "o1" });
    expect(screen.getByText("St Mary")).toBeInTheDocument();
  });

  it("checks required fields before sending", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmTaskForm onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(screen.getByText("Title is required")).toBeInTheDocument();
    expect(screen.getByText("Choose a due date")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("puts a 422 on its field and keeps the typed text", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Due date can't be in the past" }, 422))));
    render(<BdmTaskForm task={task()} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Title (required)"), { target: { value: "Changed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Due date can't be in the past")).toBeInTheDocument();
    expect(screen.getByLabelText("Due date (IST, required)")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Title (required)")).toHaveValue("Changed");
    expect(screen.queryByRole("radio")).toBeNull(); // kind is fixed after create
  });

  it("Escape cancels", () => {
    const onCancel = vi.fn();
    render(<BdmTaskForm onSaved={vi.fn()} onCancel={onCancel} />);
    fireEvent.keyDown(screen.getByLabelText("Title (required)"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run** — FAIL (module not found).
- [ ] **Step 3: Implement** `apps/web/components/BdmTaskForm.tsx`

```tsx
"use client";
import { type ChangeEvent, type FormEvent, useId, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { myOrganizationSearch, todayIst } from "@/lib/bdmAppointments";
import { isTask, KIND_LABEL, KINDS, NOTES_MAX, type Task, type TaskKind, TASKS_URL, taskRuleField, taskUrl, TITLE_MAX } from "@/lib/bdmTasks";
import { fieldErrors } from "@/lib/bdmTravel";
import type { PickOption } from "@/lib/lookups";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

// bdm-008 (spec §9): add a follow-up or task, or change an open one of your own. The API decides every rule (dates, organization,
// lengths); this form only helps. Typed text is never cleared by a failed save; leaving with unsaved text asks first.
export default function BdmTaskForm({ task, organization, onSaved, onCancel }: {
  task?: Task; organization?: { id: string; name: string }; onSaved: (task: Task) => void; onCancel: () => void;
}) {
  const id = useId();
  const [start] = useState({ kind: (task?.kind ?? "follow_up") as TaskKind, title: task?.title ?? "", due_on: task?.due_on ?? "", notes: task?.notes ?? "" });
  const [v, setV] = useState(start);
  const [org, setOrg] = useState<PickOption | null>(null);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [today] = useState(todayIst);
  useLeaveGuard(!busy && (v.title !== start.title || v.notes !== start.notes || v.due_on !== start.due_on), "Discard this task?");
  const fid = (key: string) => `${id}-${key}`;
  const set = (key: keyof typeof v) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setV({ ...v, [key]: e.target.value });
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const missing: Record<string, string> = {};
    if (!v.title.trim()) missing.title = "Title is required";
    if (!v.due_on) missing.due_on = "Choose a due date";
    if (Object.keys(missing).length) return setErrors(missing);
    setBusy(true);
    setErrors({});
    setFailure(null);
    const common = { title: v.title, due_on: v.due_on, notes: v.notes.trim() || null };
    const orgId = organization?.id ?? org?.id;
    const result = task
      ? await sendJson(taskUrl(task.id), "PATCH", common)
      : await sendJson(TASKS_URL, "POST", { kind: v.kind, ...common, ...(orgId ? { organization_id: orgId } : {}) });
    setBusy(false);
    if (result.ok && isTask(result.data)) return onSaved(result.data);
    if (result.ok) return setFailure("The task couldn't be saved. Try again.");
    const placed = { ...fieldErrors(result.detail), ...taskRuleField(result.detail) };
    if (Object.keys(placed).length) return setErrors(placed);
    setFailure(result.message);
  }

  return (
    <form aria-label={task ? "Edit task" : "Add follow-up or task"} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      {!task && (
        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend>Kind</legend>
          {KINDS.map((k) => (
            <label key={k} style={{ marginRight: 16 }}>
              <input type="radio" name={fid("kind")} value={k} checked={v.kind === k} onChange={() => setV({ ...v, kind: k })} /> {KIND_LABEL[k]}
            </label>
          ))}
        </fieldset>
      )}
      <div className="field">
        <label htmlFor={fid("title")}>Title (required)</label>
        <input id={fid("title")} autoFocus required aria-required="true" maxLength={TITLE_MAX} value={v.title} onChange={set("title")} {...invalid("title")} />
        {error("title")}
      </div>
      <div className="field">
        <label htmlFor={fid("due_on")}>Due date (IST, required)</label>
        <input id={fid("due_on")} type="date" required aria-required="true" min={task && start.due_on < today ? undefined : today} value={v.due_on} onChange={set("due_on")} {...invalid("due_on")} />
        {error("due_on")}
      </div>
      {!task && (organization ? (
        <p className="field" style={{ margin: 0 }}><span className="muted">Organization: </span>{organization.name}</p>
      ) : (
        <div className="field">
          <SearchableSelect label="Organization (optional)" noun="organization" search={myOrganizationSearch()} initial={null} onChange={setOrg} />
          {error("organization_id")}
        </div>
      ))}
      <div className="field">
        <label htmlFor={fid("notes")}>Notes</label>
        <textarea id={fid("notes")} rows={3} maxLength={NOTES_MAX} value={v.notes} onChange={set("notes")} aria-describedby={`${fid("notes")}-count`} {...(errors.notes ? invalid("notes") : {})} />
        <p id={`${fid("notes")}-count`} className="muted" style={{ margin: 0 }}>{v.notes.length}/{NOTES_MAX}</p>
        {error("notes")}
      </div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : task ? "Save changes" : "Add"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
```

(Check `SearchableSelect`'s props in `components/SearchableSelect.tsx` — `label`, `noun`, `search`, `initial`, `onChange` are used by `BdmAppointmentForm`; match them exactly.)

- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `feat(bdm-008): task form`

---

### Task 12: BdmTaskItem

**Files:** Create `apps/web/components/BdmTaskItem.tsx`; Test `apps/web/tests/components/BdmTaskItem.test.tsx`

**Interfaces:** `BdmTaskItem({ task, today, basePath: "/bdm" | "/bdm/manager", showAssignee, onChanged(task: Task, notice: string), onRefused(message: string) })`.

- [ ] **Step 1: Failing test**

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmTaskItem from "@/components/BdmTaskItem";
import type { Task } from "@/lib/bdmTasks";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const task = (over: Partial<Task> = {}): Task => ({
  id: "t1", kind: "follow_up", title: "Call the principal", notes: "Line 1\nLine 2", due_on: "2030-01-04", status: "open", source: "manual", overdue: true,
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college", archived: false }, appointment: null,
  assignee: { id: "b1", full_name: "Asha", active: true }, completed_at: null, cancelled_at: null, cancel_reason: null,
  created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-01T00:00:00Z", permissions: { can_edit: true, can_complete: true, can_cancel: true }, ...over,
});
const props = { today: "2030-01-07", basePath: "/bdm" as const, showAssignee: false, onChanged: vi.fn(), onRefused: vi.fn() };

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

describe("BdmTaskItem (bdm-008 §9)", () => {
  it("shows overdue in words, the organization and the notes", () => {
    render(<ul><BdmTaskItem task={task()} {...props} /></ul>);
    expect(screen.getByText("Overdue · 3 days")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "St Mary" })).toHaveAttribute("href", "/bdm/organizations/o1");
    expect(screen.getByText("College")).toBeInTheDocument();
    expect(screen.getByText(/Line 1/)).toHaveStyle({ whiteSpace: "pre-wrap" });
  });

  it("completes and reports the change", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(task({ status: "done", completed_at: "2030-01-07T05:00:00Z" })))));
    render(<ul><BdmTaskItem task={task()} {...props} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(props.onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "done" }), "Marked done."));
  });

  it("cancels with a reason", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res(task({ status: "cancelled", cancel_reason: "Clash" }))));
    vi.stubGlobal("fetch", fetchMock);
    render(<ul><BdmTaskItem task={task()} {...props} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Cancel task" }));
    fireEvent.change(screen.getByLabelText("Reason (required)"), { target: { value: "Clash" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel it" }));
    await waitFor(() => expect(props.onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "cancelled" }), "Cancelled."));
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ reason: "Clash" });
  });

  it("hands a 409 to the list (reloads on a 409)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "This task was cancelled" }, 409))));
    render(<ul><BdmTaskItem task={task()} {...props} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(props.onRefused).toHaveBeenCalledWith("This task was cancelled"));
  });

  it("offers only what permissions allow and links an outcome follow-up to its appointment", () => {
    const outcome = task({ source: "appointment_outcome", appointment: { id: "a1", code: "APT-000001" }, permissions: { can_edit: false, can_complete: true, can_cancel: false } });
    render(<ul><BdmTaskItem task={outcome} {...props} basePath="/bdm/manager" showAssignee /></ul>);
    expect(screen.getByRole("link", { name: "From APT-000001" })).toHaveAttribute("href", "/bdm/manager/appointments/a1");
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancel task" })).toBeNull();
    expect(screen.getByText("Asha")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** `apps/web/components/BdmTaskItem.tsx`

```tsx
"use client";
import Link from "next/link";
import { useState } from "react";

import BdmAppointmentReasonForm from "@/components/BdmAppointmentReasonForm";
import BdmTaskForm from "@/components/BdmTaskForm";
import { sendJson } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { daysOverdue, isTask, KIND_LABEL, orgTypeText, type Task, taskUrl } from "@/lib/bdmTasks";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";

// bdm-008 (spec §9): one follow-up or task. Actions render from `permissions` only -- the server enforces every rule. A refused write
// (409/403/404) goes to the list, which says why and reloads; a dropped network keeps the row as it was with the message.
export default function BdmTaskItem({ task, today, basePath, showAssignee, onChanged, onRefused }: {
  task: Task; today: string; basePath: "/bdm" | "/bdm/manager"; showAssignee: boolean;
  onChanged: (task: Task, notice: string) => void; onRefused: (message: string) => void;
}) {
  const [mode, setMode] = useState<"view" | "edit" | "cancel">("view");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const p = task.permissions;

  async function act(path: "complete" | "cancel", body: unknown, notice: string) {
    setBusy(true);
    setFailure(null);
    const result = await sendJson(`${taskUrl(task.id)}/${path}`, "POST", body);
    setBusy(false);
    if (result.ok && isTask(result.data)) return onChanged(result.data, notice);
    if (!result.ok && result.status) return onRefused(result.message);
    setFailure(result.ok ? "That didn't save. Try again." : result.message);
  }

  const due = formatCalendarDate(task.due_on);
  return (
    <li className="action-card" style={{ listStyle: "none" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <strong style={{ overflowWrap: "anywhere" }}>{task.title}</strong>
        <span className="badge">{KIND_LABEL[task.kind]}</span>
        {task.overdue && <span className="badge status error">Overdue · {daysOverdue(task.due_on, today)} days</span>}
      </div>
      <p className="muted" style={{ margin: "4px 0", display: "flex", flexWrap: "wrap", gap: 8 }}>
        <span>Due {due}</span>
        {task.organization ? (
          <span>
            <Link href={`${basePath}/organizations/${task.organization.id}`} style={LINK_STYLE}>{task.organization.name}</Link>
            {" · "}{orgTypeText(task.organization.org_type)}
            {task.organization.archived && <> <span className="badge">Archived</span></>}
          </span>
        ) : <span>{orgTypeText(null)}</span>}
        {task.appointment ? (
          <Link href={`${basePath}/appointments/${task.appointment.id}`} style={LINK_STYLE}>From {task.appointment.code}</Link>
        ) : task.source === "manual" && <span>Added by hand</span>}
        {showAssignee && <span>{task.assignee.full_name}{!task.assignee.active && " (inactive)"}</span>}
      </p>
      {task.notes && <p style={{ whiteSpace: "pre-wrap", margin: "4px 0" }}>{task.notes}</p>}
      {task.completed_at && <p className="muted" style={{ margin: 0 }}>Done {formatSchoolDateTime(task.completed_at)}</p>}
      {task.cancelled_at && (
        <p className="muted" style={{ margin: 0, whiteSpace: "pre-wrap" }}>Cancelled {formatSchoolDateTime(task.cancelled_at)}{task.cancel_reason && ` — ${task.cancel_reason}`}</p>
      )}
      {mode === "edit" && <BdmTaskForm task={task} onSaved={(t) => { setMode("view"); onChanged(t, "Changes saved."); }} onCancel={() => setMode("view")} />}
      {mode === "cancel" && (
        <BdmAppointmentReasonForm label="Cancel task" submitText="Cancel it" busyText="Cancelling…" busy={busy}
          onSubmit={(reason) => void act("cancel", { reason }, "Cancelled.")} onCancel={() => setMode("view")} />
      )}
      {mode === "view" && (p.can_complete || p.can_edit || p.can_cancel) && (
        <div className="actions">
          {p.can_complete && <button type="button" className="btn small" disabled={busy} onClick={() => void act("complete", undefined, "Marked done.")}>{busy ? "Saving…" : "Done"}</button>}
          {p.can_edit && <button type="button" className="btn secondary small" onClick={() => setMode("edit")}>Edit</button>}
          {p.can_cancel && <button type="button" className="btn secondary small" onClick={() => setMode("cancel")}>Cancel task</button>}
        </div>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
    </li>
  );
}
```

(`sendJson(url, "POST", undefined)` sends `body: undefined` → JSON `undefined` string; if `sendJson` stringifies `undefined`, pass `{}` for complete instead — the route takes no body and ignores it. Verify with the test's request assertion.)

- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `feat(bdm-008): task row with done, edit and cancel`

---

### Task 13: Panel, pages and navigation

**Files:** Create `apps/web/components/BdmTasksPanel.tsx`, `apps/web/app/bdm/follow-ups/page.tsx`, `apps/web/app/bdm/follow-ups/loading.tsx`,
`apps/web/app/bdm/manager/follow-ups/page.tsx`, `apps/web/app/bdm/manager/follow-ups/loading.tsx`; Modify `apps/web/lib/navigation.ts`,
`apps/web/tests/lib/navigation.bdm.test.ts`; Test `apps/web/tests/components/BdmTasksPanel.test.tsx`

**Interfaces:** `BdmTasksPanel({ isBdm: boolean })` (URL state `bucket`, `kind`, `org_type`, `bdm`, `offset`).

- [ ] **Step 1: Failing tests** — `navigation.bdm.test.ts` expected arrays gain `"/bdm/follow-ups"` after `"/bdm/appointments"` and
`"/bdm/manager/follow-ups"` after `"/bdm/manager/appointments"`. `BdmTasksPanel.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmTasksPanel from "@/components/BdmTasksPanel";
import type { Task, TaskPage } from "@/lib/bdmTasks";

const router = vi.hoisted(() => ({ push: vi.fn() }));
const search = vi.hoisted(() => ({ value: "" }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/bdm/follow-ups", useSearchParams: () => new URLSearchParams(search.value) }));
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const task = (over: Partial<Task> = {}): Task => ({
  id: "t1", kind: "follow_up", title: "Call the principal", notes: null, due_on: "2030-01-07", status: "open", source: "manual", overdue: false,
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college", archived: false }, appointment: null,
  assignee: { id: "b1", full_name: "Asha", active: true }, completed_at: null, cancelled_at: null, cancel_reason: null,
  created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-01T00:00:00Z", permissions: { can_edit: true, can_complete: true, can_cancel: true }, ...over,
});
const page = (items: Task[], over: Partial<TaskPage> = {}): TaskPage => ({
  items, total: items.length, limit: 50, offset: 0, today: "2030-01-07",
  counts: { buckets: { today: items.length, overdue: 2, upcoming: 0, done: 0, cancelled: 0 }, by_org_type: [{ org_type: "college", count: items.length }, { org_type: null, count: 0 }].filter((c) => c.count) },
  ...over,
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); router.push.mockClear(); search.value = ""; });

describe("BdmTasksPanel (bdm-008 §9)", () => {
  it("asks for today and shows tabs with counts, type chips and rows", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res(page([task()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmTasksPanel isBdm />);
    expect(await screen.findByText("Call the principal")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/v1/bdm/tasks?bucket=today&limit=50&offset=0");
    const tabs = screen.getByRole("navigation", { name: "Follow-up lists" });
    expect(within(tabs).getByRole("button", { name: "Today (1)" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(within(tabs).getByRole("button", { name: "Overdue (2)" }));
    expect(router.push).toHaveBeenCalledWith("/bdm/follow-ups?bucket=overdue", { scroll: false });
    fireEvent.click(screen.getByRole("button", { name: "College 1" }));
    expect(router.push).toHaveBeenLastCalledWith("/bdm/follow-ups?org_type=college", { scroll: false });
  });

  it("marks the pressed chip and ignores bad URL values", async () => {
    search.value = "org_type=college&bucket=soon&kind=meeting";
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(res(page([task()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmTasksPanel isBdm />);
    expect(await screen.findByRole("button", { name: "College 1" })).toHaveAttribute("aria-pressed", "true");
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/v1/bdm/tasks?bucket=today&limit=50&offset=0&org_type=college");
  });

  it("shows the tab's empty text with Add, and retries after a failure", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res(page([])));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmTasksPanel isBdm />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Nothing due today.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add follow-up or task" }).length).toBeGreaterThan(0);
  });

  it("after Done says so with next-step links and reloads", async () => {
    const fetchMock = vi.fn<typeof fetch>((url) => Promise.resolve(String(url).endsWith("/complete") ? res(task({ status: "done" })) : res(page([task()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmTasksPanel isBdm />);
    fireEvent.click(await screen.findByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.getByText("Marked done.")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Log activity" })).toHaveAttribute("href", "/bdm/organizations/o1#org-o1-activity");
    expect(screen.getByRole("link", { name: "Book appointment" })).toHaveAttribute("href", "/bdm/appointments/new?organization=o1");
    expect(fetchMock.mock.calls.filter((c) => String(c[0]).startsWith("/api/v1/bdm/tasks?")).length).toBe(2);
  });

  it("reads only for managers, with a BDM filter and no Add", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([task({ permissions: { can_edit: false, can_complete: false, can_cancel: false } })])))));
    render(<BdmTasksPanel isBdm={false} />);
    expect(await screen.findByText("Asha")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add follow-up or task" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Done" })).toBeNull();
    expect(screen.getByLabelText("BDM")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement**

`apps/web/lib/navigation.ts`: in `BDM_NAV` insert `{ label: "Follow-ups", href: "/bdm/follow-ups" }` after Appointments; in `BDM_MANAGER_NAV` insert
`{ label: "Follow-ups", href: "/bdm/manager/follow-ups" }` after Appointments.

`apps/web/components/BdmTasksPanel.tsx`:

```tsx
"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import BdmTaskForm from "@/components/BdmTaskForm";
import BdmTaskItem from "@/components/BdmTaskItem";
import SearchableSelect from "@/components/SearchableSelect";
import { teamMemberSearch } from "@/lib/bdmAppointments";
import { LINK_STYLE, ORG_TYPES } from "@/lib/bdmOrganizations";
import { EMPTY_TEXT, isTaskPage, KIND_LABEL, KINDS, orgTypeText, TAB_LABEL, TABS, type Tab, type Task, TASK_PAGE, type TaskPage, tasksUrl } from "@/lib/bdmTasks";
import type { PickOption } from "@/lib/lookups";

// bdm-008 (spec §9): a BDM's follow-ups and tasks, or a manager's team's (read only). The API scopes the rows and computes the counts
// from the same filters, so the chips always add up to the list. Filters live in the URL; every value is checked before it reaches the API.
type Filters = { bucket: Tab; kind: string; orgType: string; bdm: string; offset: number };
const TYPES: readonly string[] = [...ORG_TYPES, "none"];

function readFilters(params: URLSearchParams): Filters {
  const bucket = params.get("bucket") ?? "";
  const kind = params.get("kind") ?? "";
  const orgType = params.get("org_type") ?? "";
  const n = Number.parseInt(params.get("offset") ?? "", 10);
  return {
    bucket: (TABS as readonly string[]).includes(bucket) ? (bucket as Tab) : "today",
    kind: (KINDS as readonly string[]).includes(kind) ? kind : "",
    orgType: TYPES.includes(orgType) ? orgType : "",
    bdm: params.get("bdm") ?? "",
    offset: Number.isFinite(n) && n > 0 ? n : 0,
  };
}

function toUrl(f: Filters): URLSearchParams {
  const next = new URLSearchParams();
  if (f.bucket !== "today") next.set("bucket", f.bucket);
  if (f.kind) next.set("kind", f.kind);
  if (f.orgType) next.set("org_type", f.orgType);
  if (f.bdm) next.set("bdm", f.bdm);
  if (f.offset > 0) next.set("offset", String(f.offset));
  return next;
}

export default function BdmTasksPanel({ isBdm }: { isBdm: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const filters = readFilters(useSearchParams());
  const apiUrl = tasksUrl({ bucket: filters.bucket, kind: filters.kind, orgType: filters.orgType, bdm: filters.bdm, offset: filters.offset });
  const [data, setData] = useState<TaskPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<{ text: string; done?: Task } | null>(null);
  const [picked, setPicked] = useState<PickOption | null>(null);
  const basePath = isBdm ? "/bdm" : "/bdm/manager";

  useEffect(() => {
    let live = true;
    setFailed(false);
    setFetching(true);
    fetch(apiUrl)
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || !isTaskPage(body)) throw new Error("not a page");
        if (live) setData(body);
      })
      .catch(() => live && setFailed(true))
      .finally(() => live && setFetching(false));
    return () => { live = false; };
  }, [apiUrl, version]);

  function go(next: Partial<Filters>) {
    const url = toUrl({ ...filters, offset: 0, ...next });
    router.push(url.size ? `${pathname}?${url}` : pathname, { scroll: false });
  }
  const reload = () => setVersion((v) => v + 1);
  const changed = (task: Task, text: string) => { setNotice({ text, done: task.status === "done" ? task : undefined }); setAdding(false); reload(); };
  const refused = (message: string) => { setNotice({ text: `${message}. This item changed elsewhere — the list has been reloaded.` }); reload(); };
  const filtered = Boolean(filters.kind || filters.orgType || filters.bdm);
  const add = isBdm && !adding && <button type="button" className="btn small" onClick={() => setAdding(true)}>Add follow-up or task</button>;
  const doneOrg = notice?.done?.organization && !notice.done.organization.archived ? notice.done.organization : null;

  return (
    <div className="action-card wide" aria-busy={fetching && !failed}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3>Follow-ups and tasks</h3>
        {add}
      </div>
      <div role="status" aria-live="polite">
        {notice && (
          <p style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "8px 0" }}>
            <span>{notice.text}</span>
            {doneOrg && <Link href={`/bdm/organizations/${doneOrg.id}#org-${doneOrg.id}-activity`} style={LINK_STYLE}>Log activity</Link>}
            {doneOrg && <Link href={`/bdm/appointments/new?organization=${doneOrg.id}`} style={LINK_STYLE}>Book appointment</Link>}
          </p>
        )}
      </div>
      {adding && <BdmTaskForm onSaved={(t) => changed(t, "Added.")} onCancel={() => setAdding(false)} />}
      <nav aria-label="Follow-up lists" style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "8px 0" }}>
        {TABS.map((tab) => {
          const n = data?.counts.buckets[tab];
          return (
            <button key={tab} type="button" aria-current={filters.bucket === tab ? "page" : undefined}
              className={`btn small${filters.bucket === tab ? "" : " secondary"}`} onClick={() => go({ bucket: tab })}>
              {TAB_LABEL[tab]}{n === undefined ? "" : ` (${n})`}
            </button>
          );
        })}
      </nav>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        {data?.counts.by_org_type.map((c) => {
          const value = c.org_type ?? "none";
          const pressed = filters.orgType === value;
          return (
            <button key={value} type="button" aria-pressed={pressed} className={`btn small${pressed ? "" : " secondary"}`} onClick={() => go({ orgType: pressed ? "" : value })}>
              {orgTypeText(c.org_type)} {c.count}
            </button>
          );
        })}
        <div className="field" style={{ flex: "0 1 180px", margin: 0 }}>
          <label htmlFor="task-filter-kind">Kind</label>
          <select id="task-filter-kind" value={filters.kind} onChange={(e) => go({ kind: e.target.value })}>
            <option value="">All</option>
            {KINDS.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}s</option>)}
          </select>
        </div>
        {!isBdm && (
          <div style={{ flex: "1 1 220px" }}>
            <SearchableSelect key={filters.bdm || "all"} label="BDM" noun="BDM" search={teamMemberSearch()}
              initial={picked && picked.id === filters.bdm ? picked : null} onChange={(o) => { setPicked(o); go({ bdm: o?.id ?? "" }); }} />
          </div>
        )}
        {filtered && <button type="button" className="btn secondary small" onClick={() => go({ kind: "", orgType: "", bdm: "" })}>Clear filters</button>}
      </div>
      {failed ? (
        <div role="alert">
          <p className="form-error">Unable to load follow-ups.</p>
          <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
        </div>
      ) : data === null ? (
        <p className="muted" role="status">Loading follow-ups…</p>
      ) : data.total === 0 ? (
        <div role="status">
          <p className="empty">{filtered ? "No items match these filters." : EMPTY_TEXT[filters.bucket]}</p>
          {filtered ? <button type="button" className="btn secondary small" onClick={() => go({ kind: "", orgType: "", bdm: "" })}>Clear filters</button> : add}
        </div>
      ) : data.items.length === 0 ? (
        <div role="status">
          <p className="empty">This page is past the end of the list.</p>
          <button type="button" className="btn secondary small" onClick={() => go({})}>Go to the first page</button>
        </div>
      ) : (
        <>
          {fetching && <p className="muted" role="status" style={{ margin: 0 }}>Updating…</p>}
          <ul aria-label={TAB_LABEL[filters.bucket]} style={{ padding: 0, margin: 0, opacity: fetching ? 0.6 : undefined }}>
            {data.items.map((t) => (
              <BdmTaskItem key={t.id} task={t} today={data.today} basePath={basePath} showAssignee={!isBdm} onChanged={changed} onRefused={refused} />
            ))}
          </ul>
          {data.total > TASK_PAGE && (
            <nav aria-label="Follow-up pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" disabled={data.offset === 0} onClick={() => go({ offset: Math.max(0, filters.offset - TASK_PAGE) })}>Previous</button>
              <button type="button" className="btn secondary small" disabled={data.offset + data.items.length >= data.total} onClick={() => go({ offset: filters.offset + TASK_PAGE })}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
```

Pages — `apps/web/app/bdm/follow-ups/page.tsx`:

```tsx
import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmTasksPanel from "@/components/BdmTasksPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { bdmNav } from "@/lib/bdmNav";
import { BDM_SIGN_IN } from "@/lib/navigation";

// bdm-008: the BDM's own follow-ups and tasks. The API is the gate.
export default async function BdmFollowUpsPage() {
  const nav = bdmNav(); // the unread badge, read alongside the page's own data (never rejects)
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Follow-ups</div>
            <h2>Your follow-ups and tasks</h2>
            <p className="muted">Dates are India time (IST).</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading follow-ups…</p>}>
          <BdmTasksPanel isBdm />
        </Suspense>
      </div>
    </PortalShell>
  );
}
```

`apps/web/app/bdm/follow-ups/loading.tsx`:

```tsx
import PortalLoading from "@/components/PortalLoading";
import { BDM_NAV } from "@/lib/navigation";

export default function Loading() {
  return <PortalLoading nav={BDM_NAV} label="your follow-ups" />;
}
```

Manager page: copy `apps/web/app/bdm/manager/appointments/page.tsx`'s gate, nav (`bdmManagerNav`) and role label exactly; title
"Your team's follow-ups and tasks"; body `<BdmTasksPanel isBdm={false} />` in the same `Suspense`. Its `loading.tsx` uses
`BDM_MANAGER_NAV` and label "your team's follow-ups".

- [ ] **Step 4: Run** `tests/components/BdmTasksPanel.test.tsx tests/lib/navigation.bdm.test.ts` — PASS. **Step 5: Commit** `feat(bdm-008): follow-ups pages, panel and navigation`

---

### Task 14: Organization profile section

**Files:** Create `apps/web/components/BdmOrganizationTasks.tsx`; Modify `apps/web/components/BdmOrganizationDetail.tsx`,
`apps/web/app/bdm/organizations/[id]/page.tsx`, `apps/web/app/bdm/manager/organizations/[id]/page.tsx`; Test
`apps/web/tests/components/BdmOrganizationTasks.test.tsx` (+ keep `BdmOrganizationDetail.test.tsx` green)

**Interfaces:** `BdmOrganizationTasks({ organization: { id, name, archived_at }, initial: TaskPage | null, canAdd, basePath, version, onNotice(text, focusStatus?) })`;
`BdmOrganizationDetail` gains optional prop `tasks?: TaskPage | null`.

- [ ] **Step 1: Failing test**

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationTasks from "@/components/BdmOrganizationTasks";
import type { Task, TaskPage } from "@/lib/bdmTasks";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const task = (over: Partial<Task> = {}): Task => ({
  id: "t1", kind: "task", title: "Send brochure", notes: null, due_on: "2030-01-07", status: "open", source: "manual", overdue: false,
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college", archived: false }, appointment: null,
  assignee: { id: "b1", full_name: "Asha", active: true }, completed_at: null, cancelled_at: null, cancel_reason: null,
  created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-01T00:00:00Z", permissions: { can_edit: true, can_complete: true, can_cancel: true }, ...over,
});
const page = (items: Task[]): TaskPage => ({ items, total: items.length, limit: 50, offset: 0, today: "2030-01-07", counts: { buckets: { today: 0, overdue: 0, upcoming: 0, done: 0, cancelled: 0 }, by_org_type: [] } });
const org = { id: "o1", name: "St Mary" };

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("BdmOrganizationTasks (bdm-008 §9)", () => {
  it("lists open items and offers Add to the BDM", () => {
    render(<BdmOrganizationTasks organization={org} initial={page([task()])} canAdd basePath="/bdm" version={0} onNotice={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Follow-ups & tasks" })).toBeInTheDocument();
    expect(screen.getByText("Send brochure")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    expect(screen.getByText("St Mary")).toBeInTheDocument(); // the organization is fixed in the form
  });

  it("is read-only without canAdd and says when nothing is open", () => {
    render(<BdmOrganizationTasks organization={org} initial={page([])} canAdd={false} basePath="/bdm/manager" version={0} onNotice={vi.fn()} />);
    expect(screen.getByText("No open follow-ups or tasks.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add task" })).toBeNull();
  });

  it("offers Try again when the first page couldn't load, and reloads when the version changes", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(page([task()]))));
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(<BdmOrganizationTasks organization={org} initial={null} canAdd basePath="/bdm" version={0} onNotice={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Send brochure")).toBeInTheDocument();
    rerender(<BdmOrganizationTasks organization={org} initial={null} canAdd basePath="/bdm" version={1} onNotice={vi.fn()} />);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** `apps/web/components/BdmOrganizationTasks.tsx`

```tsx
"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import BdmTaskForm from "@/components/BdmTaskForm";
import BdmTaskItem from "@/components/BdmTaskItem";
import { isTaskPage, orgTasksUrl, type TaskPage } from "@/lib/bdmTasks";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-008 (spec §9): the organization's open follow-ups and tasks (the caller's own for a BDM, the team's for a manager). Every write
// reloads the first page; `version` changes when the organization is archived on this page (the archive cancelled them). Notices go
// to the profile's one live region.
export default function BdmOrganizationTasks({ organization, initial, canAdd, basePath, version, onNotice }: {
  organization: { id: string; name: string }; initial: TaskPage | null; canAdd: boolean; basePath: "/bdm" | "/bdm/manager"; version: number;
  onNotice: (text: string, focusStatus?: boolean) => void;
}) {
  const [data, setData] = useState<TaskPage | null>(initial);
  const [failed, setFailed] = useState(initial === null);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const latest = useRef(0);
  const focus = useFocusAfterRender();
  const addId = `org-${organization.id}-add-task`;

  const load = useCallback(async () => {
    const ticket = ++latest.current;
    setLoading(true);
    const response = await fetch(orgTasksUrl(organization.id)).catch(() => null);
    const body: unknown = response?.ok ? await response.json().catch(() => null) : null;
    if (ticket !== latest.current) return;
    setLoading(false);
    if (!isTaskPage(body)) return setFailed(true);
    setFailed(false);
    setData(body);
  }, [organization.id]);

  useEffect(() => {
    if (version > 0) void load();
  }, [version, load]);

  const changed = (text: string) => { onNotice(text, true); setAdding(false); void load(); };
  return (
    <section className="action-card wide" aria-labelledby={`org-${organization.id}-tasks`}>
      <div className="portal-title" style={{ gap: 12, flexWrap: "wrap" }}>
        <h3 id={`org-${organization.id}-tasks`}>Follow-ups &amp; tasks</h3>
        {canAdd && !adding && <button id={addId} type="button" className="btn small" onClick={() => { setAdding(true); onNotice(""); }}>Add task</button>}
      </div>
      {adding && <BdmTaskForm organization={organization} onSaved={() => changed("Added.")} onCancel={() => { setAdding(false); focus(addId); }} />}
      {failed ? (
        <div role="alert">
          <p className="form-error">Follow-ups couldn&apos;t be loaded.</p>
          <button type="button" className="btn secondary small" onClick={() => void load()} disabled={loading}>{loading ? "Loading…" : "Try again"}</button>
        </div>
      ) : !data || data.total === 0 ? (
        <p className="muted">No open follow-ups or tasks.</p>
      ) : (
        <>
          <ul aria-label="Open follow-ups and tasks" style={{ padding: 0, margin: 0 }}>
            {data.items.map((t) => (
              <BdmTaskItem key={t.id} task={t} today={data.today} basePath={basePath} showAssignee={basePath === "/bdm/manager"}
                onChanged={(_, text) => changed(text)} onRefused={(message) => changed(`${message}. The list has been reloaded.`)} />
            ))}
          </ul>
          {data.total > data.items.length && (
            <p className="muted">Showing {data.items.length} of {data.total}. <Link href={`${basePath}/follow-ups?bucket=today`} style={LINK_STYLE}>See all follow-ups</Link></p>
          )}
        </>
      )}
    </section>
  );
}
```

`BdmOrganizationDetail.tsx`: add prop `tasks?: TaskPage | null`; state `const [tasksVersion, setTasksVersion] = useState(0);`;
where the archive action succeeds (the `act("archive")` success path, after `setOrg`), add `setTasksVersion((v) => v + 1);`.
Render after the activity timeline:

```tsx
      {tasks !== undefined && ( // bdm-008: the BDM view adds (assigned and not archived = can_edit); the manager view reads
        <BdmOrganizationTasks organization={{ id: org.id, name: org.name }} initial={tasks} canAdd={basePath === "/bdm/organizations" && p.can_edit}
          basePath={basePath === "/bdm/organizations" ? "/bdm" : "/bdm/manager"} version={tasksVersion} onNotice={notify} />
      )}
```

Both organization pages: `import { firstTaskPage } from "@/lib/bdmTasksServer";`, `const taskPage = firstTaskPage(id);` next to the
other first pages, add it to the `Promise.all` (and `null` to the fallback tuple), pass `tasks={tasks}`.

- [ ] **Step 4: Run** `tests/components/BdmOrganizationTasks.test.tsx tests/components/BdmOrganizationDetail.test.tsx tests/components/BdmOrganizationPages.test.tsx` — PASS.
- [ ] **Step 5: Commit** `feat(bdm-008): follow-ups on the organization profile`

---

### Task 15: E2E spec, docs, static checks

**Files:** Create `apps/web/tests/e2e/bdm-008-follow-ups.spec.ts`; Modify `docs/architecture/API_CONTRACT.md`, `docs/architecture/DATA_MODEL.md`,
`docs/decisions/PRODUCT_DECISION_REGISTER.md`, `docs/delivery/BDM_CRM_BACKLOG.md`, `docs/quality/RTM.md`, `docs/ux/SCREEN_CATALOG.md`,
`docs/ux/screen_catalog.json`, `docs/ux/ROLE_NAVIGATION.md`

- [ ] **Step 1: E2E spec** (written now; run during browser validation)

```ts
import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-008 (AC1, AC3, AC4, AC9): a College BDM adds a follow-up for an organization (due today) and a general task (due tomorrow); the
// counts match the list; Done offers the next steps; Cancel keeps the reason; the manager reads only; the page fits a phone.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

function istDate(days: number): string {
  return new Date(Date.now() + 330 * 60_000 + days * 86_400_000).toISOString().slice(0, 10);
}

test("BDM follow-ups: add, counts, done, cancel, manager read-only, phone width", async ({ page }) => {
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm008-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm008-b-${stamp}@example.local`, bdm_profile: { bdm_type: "college", employee_id: `E2E8-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, "/bdm/my-day");
  const org = (await (await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E Follow College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", designation: "Principal", is_primary: true }] },
  })).json()).organization;

  await page.goto(`/bdm/organizations/${org.id}`);
  await page.getByRole("button", { name: "Add task" }).click();
  await page.getByLabel("Title (required)").fill("Call the principal");
  await page.getByLabel("Due date (IST, required)").fill(istDate(0));
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("Call the principal")).toBeVisible();

  await page.goto("/bdm/follow-ups");
  await page.getByRole("button", { name: "Add follow-up or task" }).first().click();
  await page.getByLabel("Task").check();
  await page.getByLabel("Title (required)").fill("Prepare the travel plan");
  await page.getByLabel("Due date (IST, required)").fill(istDate(1));
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const tabs = page.getByRole("navigation", { name: "Follow-up lists" });
  await expect(tabs.getByRole("button", { name: "Today (1)" })).toBeVisible();
  await expect(tabs.getByRole("button", { name: "Upcoming (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "College 1" })).toBeVisible();

  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByText("Marked done.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Book appointment" })).toHaveAttribute("href", `/bdm/appointments/new?organization=${org.id}`);

  await tabs.getByRole("button", { name: "Upcoming (1)" }).click();
  await expect(page.getByRole("button", { name: "No organization 1" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel task" }).click();
  await page.getByLabel("Reason (required)").fill("Trip postponed");
  await page.getByRole("button", { name: "Cancel it" }).click();
  await tabs.getByRole("button", { name: "Cancelled (1)" }).click();
  await expect(page.getByText(/Trip postponed/)).toBeVisible();
  await tabs.getByRole("button", { name: "Done (1)" }).click();
  await expect(page.getByText("Call the principal")).toBeVisible();

  await page.setViewportSize({ width: 360, height: 780 });
  await expect(page.getByRole("heading", { name: "Your follow-ups and tasks" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await page.setViewportSize({ width: 1280, height: 800 });
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  await page.goto("/bdm/manager/follow-ups?bucket=done");
  await expect(page.getByText("Call the principal")).toBeVisible();
  await expect(page.getByRole("button", { name: "Done", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add follow-up or task" })).toHaveCount(0);
});
```

(Confirm the manager's sign-in portal and landing in `bdm-007-meeting-reports.spec.ts` and copy them.)

- [ ] **Step 2: Docs**
  - `DATA_MODEL.md` (`bdm_tasks` entry): append "bdm-008 (0076): `notes` (2000), `cancelled_at`, `cancel_reason` (500); `ck_bdm_tasks_cancelled`, `ck_bdm_tasks_cancel_reason`; archive cancels open items."
  - `API_CONTRACT.md`: a bdm-008 section with the five endpoints, parameters, `BdmTaskOut`, `BdmTaskPage.counts`, errors (spec §6) and the archive side effect.
  - Decision register: `### DEC-SCOPE-074 — Follow-ups and tasks (bdm-008)` with Question, Evidence (EVID-016 §5/§13/§15/§4 Common), Answer F1–F7 + defaults, Status `EXPLICIT_APPROVAL` (in-session 2026-10-05/06), links to spec/plan, migration `0076`.
  - Backlog bdm-008: a status block "implemented on `feature/bdm-008-follow-ups` (DEC-SCOPE-074, 0076) — NOT COMPLETE: awaiting browser validation and Codex review" + lite evidence.
  - RTM: a `bdm-008` row (requirement → decision → AC1–AC9 → screens → API/DB → tests → code).
  - SCREEN_CATALOG (+ json) and ROLE_NAVIGATION: `/bdm/follow-ups`, `/bdm/manager/follow-ups`, the organization profile section, the nav entries.
- [ ] **Step 3: Static checks** — `npx tsc --noEmit`; `npx eslint` on the changed web files; `python -m ruff check` on the changed api files; `python -m mypy app` and compare with `main`'s count.
- [ ] **Step 4: LITE backend + web set** — run LITE and the web files from Tasks 10–14 plus `BdmOrganizationDetail`, `BdmOrganizationPages`, `navigation.bdm`.
- [ ] **Step 5: Commit** `docs(bdm-008): traceability, contract, data model; e2e spec`
- [ ] **Step 6:** `graphify update .` (AST only), and do not claim completion — report that browser validation and the Codex review are next.
