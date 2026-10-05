# bdm-007 Meeting Reports — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completing a BDM appointment requires filing a meeting report; a follow-up date creates exactly one follow-up; the author
may correct the report on its IST filing day; past open appointments are flagged "Outcome pending".

**Architecture:** Extend bdm-006's flat module (`app/api/bdm_appointments.py` routes → `app/services/bdm_appointments.py` rules,
one commit per route). New tables `bdm_meeting_reports` and a minimal `bdm_tasks` in migration `0072_bdm_meeting_reports`
(with a legacy backfill). `outcome` / `next_follow_up_on` stay on `bdm_appointments`. Web: extend `lib/bdmAppointments.ts`,
rename `BdmAppointmentCompleteForm` → `BdmMeetingReportForm`, add `BdmMeetingReportSection`, extend Actions / Detail / Panel.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, PostgreSQL 16; Next.js App Router, React, Vitest, Testing
Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-05-bdm-007-meeting-reports-design.md` (read it with this plan).

## Global Constraints

- Branch `feature/bdm-007-meeting-outcomes` (from `origin/main` @ `2e057b3a`); migration `0072_bdm_meeting_reports`
  (down_revision `0071_bdm_activities`); decision `DEC-SCOPE-070`. Before the PR: `git fetch origin` and renumber if `main` gained
  a migration / DEC.
- No new dependency (backend or web).
- Report fields: `discussion` required 1–4000 multi-line; `requirements`, `opportunity` ≤ 2000 multi-line; `next_action` ≤ 1000
  multi-line; `responsible_person` ≤ 200 single line; blanks → null; control characters → 422 "<Label> contains invalid characters".
- Outcome lists unchanged (bdm-006 A8). Follow-up date: on or after IST today when set or changed.
- Edit window: not legacy and IST date of `submitted_at` == IST date of `db_now()`.
- Lock order: appointment → report → follow-up. Services never commit; the route commits once; audit rows in that transaction.
- Logs / audit carry ids, outcome key, field names, follow-up action — never report text or the responsible person.
- Errors `{"detail": ...}`; out-of-scope ids → 404 "Appointment not found"; non-owner writes → 403 "Only the appointment's BDM can
  change it".
- Tests: **lite only** (never the full suites; the owner runs them). Not COMPLETE until browser validation + independent Codex review.

## Review Focus

1. **A report edited just after midnight IST** — the window closes on the IST day, not UTC. Task 4 test
   `test_edit_window_closes_on_the_next_ist_day`.
2. **Clearing then re-setting the follow-up date** reuses the same follow-up row (never two). Task 4 test
   `test_follow_up_cleared_then_set_again_reuses_the_row`.
3. **Double-click on "Save report and complete"** (two concurrent completes) → one 200, one 409, exactly one report and one
   follow-up. Task 6 test `test_double_complete_files_one_report`.
4. **A whitespace-only discussion** → 422 "Discussion is required" (not stored as blank). Task 2 test
   `test_blank_discussion_is_required`.
5. **The 409 on save keeps the typed report** (another tab completed it) — the form stays open with the text. Task 8 test
   `keeps the typed report on a 409`.

## How to run tests (worktree)

The user starts Docker. From the worktree root in Git Bash. `<P>` = test paths.

```bash
W="C:/Users/kunam/Documents/project/trainwebsite/.claude/worktrees/bdm-007"
# Backend
docker compose -p bdm007 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "$W/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <P>"
# Web (vitest / tsc / eslint)
MSYS_NO_PATHCONV=1 docker compose -p bdm007 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps \
  -v "$W/apps/web:/app" -v /app/node_modules web-test sh -c "npx vitest run <paths>"
```

Stale alembic stamp from another branch: prefix `alembic stamp --purge 0071_bdm_activities &&`.

LITE = `tests/test_bdm_007_*.py tests/test_bdm_006_*.py tests/test_bdm_009_migration.py tests/test_bdm_002_migration.py`

---

### Task 1: Migration 0072, models, migration-test fixtures

**Files:**
- Create: `apps/api/alembic/versions/0072_bdm_meeting_reports.py`
- Modify: `apps/api/app/models.py` (after `BdmAppointmentEvent`, before `BDM_ACTIVITY_CHANNELS`)
- Modify: `apps/api/tests/test_bdm_009_migration.py:35-37` (single head → on the chain)
- Modify: `apps/api/tests/test_bdm_002_migration.py:133`, `apps/api/tests/test_bdm_006_migration.py` (`isolated_db`)
- Test: `apps/api/tests/test_bdm_007_migration.py`

**Interfaces:**
- Produces: `app.models.BdmMeetingReport`, `app.models.BdmTask`, `BDM_TASK_KINDS`, `BDM_TASK_SOURCES`, `BDM_TASK_STATUSES`.

- [ ] **Step 1: Failing test** — `apps/api/tests/test_bdm_007_migration.py`:

```python
"""bdm-007 -- migration 0072_bdm_meeting_reports (spec §4). Isolated database per test (the bdm-006 pattern)."""

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
_spec = importlib.util.spec_from_file_location("_bdm_007_migration_0072", VERSIONS / "0072_bdm_meeting_reports.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0071_bdm_activities"
HEAD = "0072_bdm_meeting_reports"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_chains_after_0071_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert ScriptDirectory.from_config(_config()).get_heads() == [HEAD]


def test_models_match_the_migration():
    from app.models import BDM_TASK_KINDS, BDM_TASK_SOURCES, BDM_TASK_STATUSES, BdmMeetingReport, BdmTask

    report = BdmMeetingReport.__table__
    assert {c.name for c in report.columns} == {
        "id", "appointment_id", "author_user_id", "discussion", "requirements", "opportunity", "next_action", "responsible_person",
        "legacy", "submitted_at", "created_at", "updated_at",
    }
    names = {c.name for c in report.constraints}
    assert {"uq_bdm_meeting_reports_appointment", "ck_bdm_meeting_reports_discussion"} <= names
    task = BdmTask.__table__
    assert {c.name for c in task.columns} == {
        "id", "kind", "title", "due_on", "organization_id", "source", "source_appointment_id", "assignee_user_id", "status",
        "completed_at", "created_at", "updated_at",
    }
    names = {i.name for i in task.indexes} | {c.name for c in task.constraints}
    assert {
        "uq_bdm_tasks_source_appointment", "ck_bdm_tasks_kind", "ck_bdm_tasks_source", "ck_bdm_tasks_status", "ck_bdm_tasks_source_link",
        "ck_bdm_tasks_completed", "ix_bdm_tasks_assignee_status_due",
    } <= names
    assert (_migration.TASK_KINDS, _migration.TASK_SOURCES, _migration.TASK_STATUSES) == (BDM_TASK_KINDS, BDM_TASK_SOURCES, BDM_TASK_STATUSES)


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


APPT = (
    "INSERT INTO bdm_appointments (id, code, bdm_user_id, organization_id, contact_name, starts_at, appointment_type, status, outcome, "
    "next_follow_up_on) VALUES (:id, :code, :u, :org, 'C', now() - interval '2 days', 'college_meeting', :status, :outcome, :follow)"
)


@pytest.fixture
def isolated_db():
    """A fresh database at 0071 whose 0072 tables were dropped (0001's create_all builds them from the models), holding one BDM,
    one organization and three appointments: completed with a follow-up date, completed without, and scheduled."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm007_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        _sql(url, "DROP TABLE IF EXISTS bdm_tasks, bdm_meeting_reports")
        user, org = uuid.uuid4(), uuid.uuid4()
        _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'it', true, true, 'en-GB', '{}')", {"id": user, "email": f"bdm-{name}@example.local"})
        _sql(url, "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, created_by_user_id) VALUES (:id, 'ORG-9', 'college', 'college', 'A', 'a', 'K', 'k', :u, :u)", {"id": org, "u": user})
        appts = {"followed": uuid.uuid4(), "plain": uuid.uuid4(), "open": uuid.uuid4()}
        base = {"u": user, "org": org}
        _sql(url, APPT, {**base, "id": appts["followed"], "code": "APT-1", "status": "completed", "outcome": "interested", "follow": "2026-09-22"})
        _sql(url, APPT, {**base, "id": appts["plain"], "code": "APT-2", "status": "completed", "outcome": "other", "follow": None})
        _sql(url, APPT, {**base, "id": appts["open"], "code": "APT-3", "status": "scheduled", "outcome": None, "follow": None})
        _sql(url, "INSERT INTO bdm_appointment_events (id, appointment_id, actor_user_id, from_status, to_status, created_at) VALUES (:id, :a, :u, 'scheduled', 'completed', '2026-09-20T10:00:00+00')", {"id": uuid.uuid4(), "a": appts["followed"], "u": user})
        yield {"cfg": cfg, "url": url, "user": user, "org": org, "appts": appts}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_backfills_one_legacy_report_per_completed_appointment(isolated_db):
    url, appts = isolated_db["url"], isolated_db["appts"]
    command.upgrade(isolated_db["cfg"], HEAD)
    rows = _sql(url, "SELECT appointment_id, legacy, discussion, author_user_id, submitted_at FROM bdm_meeting_reports ORDER BY submitted_at")
    assert {r[0] for r in rows} == {appts["followed"], appts["plain"]}  # AC1: every completed appointment, nothing else
    assert all(r[1] is True and r[2] is None and r[3] == isolated_db["user"] for r in rows)
    followed = next(r for r in rows if r[0] == appts["followed"])
    assert followed[4].isoformat().startswith("2026-09-20T10:00")  # the completion event's time
    tasks = _sql(url, "SELECT source_appointment_id, kind, source, status, due_on::text, title, organization_id FROM bdm_tasks")
    assert tasks == [(appts["followed"], "follow_up", "appointment_outcome", "open", "2026-09-22", "Follow up on APT-1", isolated_db["org"])]


def test_backfill_is_idempotent_and_the_round_trip_keeps_appointments(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, "SELECT id, status, outcome, next_follow_up_on FROM bdm_appointments ORDER BY id")
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)  # only legacy rows: allowed
    assert _sql(url, "SELECT id, status, outcome, next_follow_up_on FROM bdm_appointments ORDER BY id") == before
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT count(*) FROM bdm_meeting_reports") == [(2,)]
    assert _sql(url, "SELECT count(*) FROM bdm_tasks") == [(1,)]


def test_constraints_hold_and_downgrade_refuses_while_reports_exist(isolated_db):
    cfg, url, appts, user = isolated_db["cfg"], isolated_db["url"], isolated_db["appts"], isolated_db["user"]
    command.upgrade(cfg, HEAD)
    report = "INSERT INTO bdm_meeting_reports (id, appointment_id, author_user_id, discussion, legacy) VALUES (:id, :a, :u, :d, :legacy)"
    with pytest.raises(Exception, match="uq_bdm_meeting_reports_appointment"):
        _sql(url, report, {"id": uuid.uuid4(), "a": appts["plain"], "u": user, "d": "x", "legacy": False})
    with pytest.raises(Exception, match="ck_bdm_meeting_reports_discussion"):
        _sql(url, report, {"id": uuid.uuid4(), "a": appts["open"], "u": user, "d": None, "legacy": False})
    task = (
        "INSERT INTO bdm_tasks (id, kind, title, due_on, source, source_appointment_id, assignee_user_id, status) "
        "VALUES (:id, 'follow_up', 'T', '2030-01-01', :source, :a, :u, 'open')"
    )
    with pytest.raises(Exception, match="uq_bdm_tasks_source_appointment"):
        _sql(url, task, {"id": uuid.uuid4(), "source": "appointment_outcome", "a": appts["followed"], "u": user})
    with pytest.raises(Exception, match="ck_bdm_tasks_source_link"):
        _sql(url, task, {"id": uuid.uuid4(), "source": "manual", "a": appts["plain"], "u": user})
    _sql(url, report, {"id": uuid.uuid4(), "a": appts["open"], "u": user, "d": "Filed", "legacy": False})
    with pytest.raises(Exception, match="meeting reports exist"):
        command.downgrade(cfg, BASE)
```

- [ ] **Step 2: Run, expect FAIL** — `<P>` = `tests/test_bdm_007_migration.py`. Expected: collection error (no `0072_bdm_meeting_reports.py`).

- [ ] **Step 3: Migration** — `apps/api/alembic/versions/0072_bdm_meeting_reports.py`:

```python
"""bdm-007 (DEC-SCOPE-070): meeting reports, a minimal task table (bdm-008 extends it), and the legacy backfill.

Every appointment completed under bdm-006 (outcome only) gets a read-only legacy report, and a follow-up for its stored
follow-up date, so "completed <=> one report" holds for every row. `bdm_appointments` is not altered.

Revision ID: 0072_bdm_meeting_reports
Revises: 0071_bdm_activities
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0072_bdm_meeting_reports"
down_revision = "0071_bdm_activities"
branch_labels = None
depends_on = None

REPORTS = "bdm_meeting_reports"
TASKS = "bdm_tasks"
TASK_KINDS = ("follow_up", "task")
TASK_SOURCES = ("appointment_outcome", "mou", "manual")
TASK_STATUSES = ("open", "done", "cancelled")

# Set-based and idempotent (NOT EXISTS), so it also runs when 0001's create_all already built the tables.
BACKFILL_REPORTS = f"""
INSERT INTO {REPORTS} (id, appointment_id, author_user_id, legacy, submitted_at, created_at, updated_at)
SELECT gen_random_uuid(), a.id, a.bdm_user_id, true, t.at, t.at, t.at
FROM bdm_appointments a
CROSS JOIN LATERAL (
    SELECT COALESCE(
        (SELECT max(e.created_at) FROM bdm_appointment_events e WHERE e.appointment_id = a.id AND e.to_status = 'completed'),
        a.updated_at
    ) AS at
) t
WHERE a.status = 'completed' AND NOT EXISTS (SELECT 1 FROM {REPORTS} r WHERE r.appointment_id = a.id)
"""
BACKFILL_FOLLOW_UPS = f"""
INSERT INTO {TASKS} (id, kind, title, due_on, organization_id, source, source_appointment_id, assignee_user_id, status)
SELECT gen_random_uuid(), 'follow_up', 'Follow up on ' || a.code, a.next_follow_up_on, a.organization_id, 'appointment_outcome',
       a.id, a.bdm_user_id, 'open'
FROM bdm_appointments a
WHERE a.status = 'completed' AND a.next_follow_up_on IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM {TASKS} t WHERE t.source_appointment_id = a.id)
"""


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid(name: str, *args, nullable: bool = False, **kwargs) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, nullable=nullable, **kwargs)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _create_tables() -> None:
    op.create_table(
        REPORTS,
        _uuid("id", primary_key=True),
        _uuid("appointment_id", sa.ForeignKey("bdm_appointments.id", ondelete="RESTRICT")),
        _uuid("author_user_id", sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("discussion", sa.String(4000), nullable=True),
        sa.Column("requirements", sa.String(2000), nullable=True),
        sa.Column("opportunity", sa.String(2000), nullable=True),
        sa.Column("next_action", sa.String(1000), nullable=True),
        sa.Column("responsible_person", sa.String(200), nullable=True),
        sa.Column("legacy", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("appointment_id", name="uq_bdm_meeting_reports_appointment"),
        sa.CheckConstraint("legacy OR discussion IS NOT NULL", name="ck_bdm_meeting_reports_discussion"),
    )
    op.create_table(
        TASKS,
        _uuid("id", primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        _uuid("organization_id", sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("source", sa.String(30), nullable=False),
        _uuid("source_appointment_id", sa.ForeignKey("bdm_appointments.id", ondelete="RESTRICT"), nullable=True),
        _uuid("assignee_user_id", sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("status", sa.String(20), server_default=sa.text("'open'"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("source_appointment_id", name="uq_bdm_tasks_source_appointment"),
        sa.CheckConstraint(_in("kind", TASK_KINDS), name="ck_bdm_tasks_kind"),
        sa.CheckConstraint(_in("source", TASK_SOURCES), name="ck_bdm_tasks_source"),
        sa.CheckConstraint(_in("status", TASK_STATUSES), name="ck_bdm_tasks_status"),
        sa.CheckConstraint("(source = 'appointment_outcome') = (source_appointment_id IS NOT NULL)", name="ck_bdm_tasks_source_link"),
        sa.CheckConstraint("(status = 'done') = (completed_at IS NOT NULL)", name="ck_bdm_tasks_completed"),
    )
    op.create_index("ix_bdm_tasks_assignee_status_due", TASKS, ["assignee_user_id", "status", "due_on"])


def upgrade() -> None:
    if op.get_context().as_sql or REPORTS not in sa.inspect(op.get_bind()).get_table_names():
        _create_tables()
    op.execute(BACKFILL_REPORTS)
    op.execute(BACKFILL_FOLLOW_UPS)


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {REPORTS} WHERE NOT legacy LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0072_bdm_meeting_reports: meeting reports exist. Remove them deliberately first.")
    op.drop_table(TASKS)  # legacy reports and their follow-ups are rebuilt from bdm_appointments on the next upgrade
    op.drop_table(REPORTS)
```

- [ ] **Step 4: Models** — in `apps/api/app/models.py`, after `class BdmAppointmentEvent` (before `BDM_ACTIVITY_CHANNELS`):

```python
BDM_TASK_KINDS = ("follow_up", "task")
BDM_TASK_SOURCES = ("appointment_outcome", "mou", "manual")
BDM_TASK_STATUSES = ("open", "done", "cancelled")


class BdmMeetingReport(Base, TimestampMixin):
    """bdm-007 (DEC-SCOPE-070): the meeting report filed on completing an appointment (one per appointment). The outcome and next
    follow-up date stay on the appointment. `legacy` rows were backfilled by 0072 for bdm-006 completions (outcome only, read-only)."""

    __tablename__ = "bdm_meeting_reports"
    __table_args__ = (
        UniqueConstraint("appointment_id", name="uq_bdm_meeting_reports_appointment"),
        CheckConstraint("legacy OR discussion IS NOT NULL", name="ck_bdm_meeting_reports_discussion"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    appointment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_appointments.id", ondelete="RESTRICT"))
    author_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    discussion: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    requirements: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    opportunity: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    responsible_person: Mapped[str | None] = mapped_column(String(200), nullable=True)
    legacy: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BdmTask(Base, TimestampMixin):
    """bdm-007 creates follow-ups (`source = appointment_outcome`, one per appointment); bdm-008 adds manual tasks, MoU follow-ups,
    completion and the pages."""

    __tablename__ = "bdm_tasks"
    __table_args__ = (
        UniqueConstraint("source_appointment_id", name="uq_bdm_tasks_source_appointment"),
        CheckConstraint(_in_list("kind", BDM_TASK_KINDS), name="ck_bdm_tasks_kind"),
        CheckConstraint(_in_list("source", BDM_TASK_SOURCES), name="ck_bdm_tasks_source"),
        CheckConstraint(_in_list("status", BDM_TASK_STATUSES), name="ck_bdm_tasks_status"),
        CheckConstraint("(source = 'appointment_outcome') = (source_appointment_id IS NOT NULL)", name="ck_bdm_tasks_source_link"),
        CheckConstraint("(status = 'done') = (completed_at IS NOT NULL)", name="ck_bdm_tasks_completed"),
        Index("ix_bdm_tasks_assignee_status_due", "assignee_user_id", "status", "due_on"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    due_on: Mapped[date] = mapped_column(Date)
    organization_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=True)
    source: Mapped[str] = mapped_column(String(30))
    source_appointment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_appointments.id", ondelete="RESTRICT"), nullable=True)
    assignee_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), default="open", server_default=text("'open'"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 5: Fixtures of older migration tests.**
  - `test_bdm_009_migration.py:35-37` → keep the name meaning "on the chain":

```python
def test_migration_chains_after_0070_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    heads = ScriptDirectory.from_config(_config()).get_heads()
    assert len(heads) == 1 and HEAD in {r.revision for r in ScriptDirectory.from_config(_config()).walk_revisions()}
```
  - `test_bdm_002_migration.py:133` → `"DROP TABLE IF EXISTS bdm_tasks, bdm_meeting_reports, bdm_activities, bdm_appointment_events, bdm_appointments"` (and add "bdm-007's reports/tasks" to the comment above).
  - `test_bdm_006_migration.py` `isolated_db`, right after `command.upgrade(cfg, BASE)`:

```python
        # bdm-007's tables (built by 0001's create_all from the current models) reference bdm_appointments, which 0070 drops.
        _sql(url, "DROP TABLE IF EXISTS bdm_tasks, bdm_meeting_reports")
```

- [ ] **Step 6: Run, expect PASS** — `<P>` = `tests/test_bdm_007_migration.py tests/test_bdm_006_migration.py tests/test_bdm_009_migration.py tests/test_bdm_002_migration.py`.

- [ ] **Step 7: Commit** — `feat(bdm-007): meeting reports + follow-up tables, legacy backfill (0072)`.

---

### Task 2: Request / response schemas

**Files:**
- Modify: `apps/api/app/schemas.py` — `_trip_text` gains a `labels` parameter; bdm-006 block: replace `BdmAppointmentComplete`, extend
  `BdmAppointmentPermissions`, `BdmAppointmentRow`, `BdmAppointmentOut`.
- Modify: `apps/api/tests/test_bdm_006_schemas.py:10,78-79`
- Test: `apps/api/tests/test_bdm_007_schemas.py`

**Interfaces:**
- Produces: `BdmMeetingReportCreate`, `BdmMeetingReportUpdate` (fields `outcome, discussion, requirements, opportunity, next_action,
  responsible_person, next_follow_up_on`), `BdmMeetingReportOut`, `BdmFollowUpOut`, `BDM_REPORT_TEXT_FIELDS` (tuple of the five text
  field names).

- [ ] **Step 1: Failing test** — `apps/api/tests/test_bdm_007_schemas.py`:

```python
"""bdm-007 -- report schemas (spec §5.1, §5.2)."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import BDM_REPORT_TEXT_FIELDS, BdmMeetingReportCreate, BdmMeetingReportUpdate

VALID = {"outcome": "interested", "discussion": "Principal keen on IT training."}


def _messages(exc: ValidationError) -> dict[str, str]:
    return {str(e["loc"][-1]): e["msg"] for e in exc.errors()}


def test_minimal_report_and_blanks_become_null():
    r = BdmMeetingReportCreate.model_validate({**VALID, "requirements": "  ", "responsible_person": "", "next_action": "Send proposal"})
    assert (r.requirements, r.responsible_person, r.next_action, r.next_follow_up_on) == (None, None, "Send proposal", None)
    assert BDM_REPORT_TEXT_FIELDS == ("discussion", "requirements", "opportunity", "next_action", "responsible_person")


def test_blank_discussion_is_required():
    with pytest.raises(ValidationError) as missing:
        BdmMeetingReportCreate.model_validate({"outcome": "interested"})
    assert "discussion" in _messages(missing.value)
    with pytest.raises(ValidationError) as blank:
        BdmMeetingReportCreate.model_validate({**VALID, "discussion": "   \n "})
    assert _messages(blank.value)["discussion"] == "Value error, Discussion is required"


def test_multiline_allowed_but_control_characters_and_lengths_refused():
    assert BdmMeetingReportCreate.model_validate({**VALID, "discussion": "Line 1\nLine 2\tend"}).discussion == "Line 1\nLine 2\tend"
    with pytest.raises(ValidationError) as bad:
        BdmMeetingReportCreate.model_validate({**VALID, "opportunity": "a\x07b", "responsible_person": "Mrs\nRao"})
    assert _messages(bad.value) == {
        "opportunity": "Value error, Opportunity contains invalid characters",
        "responsible_person": "Value error, Responsible person contains invalid characters",
    }
    for field, limit in (("discussion", 4000), ("requirements", 2000), ("opportunity", 2000), ("next_action", 1000), ("responsible_person", 200)):
        BdmMeetingReportCreate.model_validate({**VALID, field: "x" * limit})
        with pytest.raises(ValidationError):
            BdmMeetingReportCreate.model_validate({**VALID, field: "x" * (limit + 1)})


def test_server_owned_fields_and_bad_values_are_refused():
    for extra in ({"legacy": True}, {"author_user_id": "00000000-0000-0000-0000-000000000000"}, {"status": "completed"}):
        with pytest.raises(ValidationError):
            BdmMeetingReportCreate.model_validate({**VALID, **extra})
    with pytest.raises(ValidationError):
        BdmMeetingReportCreate.model_validate({**VALID, "outcome": "great"})
    with pytest.raises(ValidationError) as bad_date:
        BdmMeetingReportCreate.model_validate({**VALID, "next_follow_up_on": "22-09-2026"})
    assert _messages(bad_date.value)["next_follow_up_on"] == "Enter a valid follow-up date"
    assert BdmMeetingReportCreate.model_validate({**VALID, "next_follow_up_on": "2030-01-10"}).next_follow_up_on == date(2030, 1, 10)


def test_update_is_partial_and_refuses_null_for_required_fields():
    u = BdmMeetingReportUpdate.model_validate({"next_action": "Call back", "next_follow_up_on": None})
    assert u.model_dump(exclude_unset=True) == {"next_action": "Call back", "next_follow_up_on": None}
    for field in ("outcome", "discussion"):
        with pytest.raises(ValidationError):
            BdmMeetingReportUpdate.model_validate({field: None})
    with pytest.raises(ValidationError):
        BdmMeetingReportUpdate.model_validate({"discussion": "  "})
    with pytest.raises(ValidationError):
        BdmMeetingReportUpdate.model_validate({"legacy": False})
```

- [ ] **Step 2: Run, expect FAIL** — `<P>` = `tests/test_bdm_007_schemas.py` → ImportError `BDM_REPORT_TEXT_FIELDS`.

- [ ] **Step 3: Implement** in `apps/api/app/schemas.py`:
  - `_trip_text` (≈ line 3306): add a `labels` parameter, defaulting to the trip labels (no behavior change for trips):

```python
def _trip_text(pattern: re.Pattern, required: bool, labels: dict[str, str] = BDM_TRIP_FIELD_LABELS):
    def check(value: str | None, info: ValidationInfo) -> str | None:
        field = info.field_name or ""
        label = labels.get(field, field)
```
  - Replace `class BdmAppointmentComplete` with:

```python
# --- bdm-007 (DEC-SCOPE-070, spec §5): the meeting report ----------------------------------------------------------------------
BDM_REPORT_TEXT_FIELDS = ("discussion", "requirements", "opportunity", "next_action", "responsible_person")
BDM_REPORT_LABELS = {
    "discussion": "Discussion", "requirements": "Requirements", "opportunity": "Opportunity", "next_action": "Next action",
    "responsible_person": "Responsible person",
}


def _bdm_report_text(max_length: int, *, required: bool = False, multiline: bool = True):
    """Trimmed, at most `max_length`; line breaks only where the field is multi-line; blank -> None (or "<Label> is required")."""
    check = AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL if multiline else _BDM_CONTROL, required, BDM_REPORT_LABELS))
    text = Annotated[str, _trimmed(max_length)]
    return Annotated[text, check] if required else Annotated[text | None, check]


BdmReportDiscussion = _bdm_report_text(4000, required=True)
BdmReportLongText = _bdm_report_text(2000)
BdmReportNextAction = _bdm_report_text(1000)
BdmReportPerson = _bdm_report_text(200, multiline=False)
BdmFollowUpDate = Annotated[date, BeforeValidator(_trip_date("follow-up date"))]


class BdmMeetingReportCreate(BaseModel):
    """§5.1: the body of `POST /bdm/appointments/{id}/complete` -- filing the report is what completes the appointment. Author,
    `legacy`, `submitted_at` and the status are server-owned (unknown fields here)."""

    model_config = ConfigDict(extra="forbid")
    outcome: BdmAppointmentOutcome
    discussion: BdmReportDiscussion
    requirements: BdmReportLongText = None
    opportunity: BdmReportLongText = None
    next_action: BdmReportNextAction = None
    responsible_person: BdmReportPerson = None
    next_follow_up_on: BdmFollowUpDate | None = None


class BdmMeetingReportUpdate(BaseModel):
    """§5.2: omitted = unchanged; a sent null on `outcome` / `discussion` fails the non-nullable type; `next_follow_up_on: null` clears it."""

    model_config = ConfigDict(extra="forbid")
    outcome: BdmAppointmentOutcome = None
    discussion: BdmReportDiscussion = None
    requirements: BdmReportLongText = None
    opportunity: BdmReportLongText = None
    next_action: BdmReportNextAction = None
    responsible_person: BdmReportPerson = None
    next_follow_up_on: BdmFollowUpDate | None = None


class BdmMeetingReportOut(BaseModel):
    discussion: str | None
    requirements: str | None
    opportunity: str | None
    next_action: str | None
    responsible_person: str | None
    legacy: bool
    author: BdmOrgPerson
    submitted_at: datetime
    updated_at: datetime


class BdmFollowUpOut(BaseModel):
    id: UUID
    due_on: date
    status: str
```
  - `BdmAppointmentPermissions`: add `can_edit_report: bool`. `BdmAppointmentRow`: add `outcome_pending: bool`.
    `BdmAppointmentOut`: add `report: BdmMeetingReportOut | None` and `follow_up: BdmFollowUpOut | None` (after `next_follow_up_on`).
  - `test_bdm_006_schemas.py`: import `BdmMeetingReportCreate` instead of `BdmAppointmentComplete`; lines 78–79 become

```python
        BdmMeetingReportCreate.model_validate({"outcome": "great", "discussion": "x"})
    c = BdmMeetingReportCreate.model_validate({"outcome": "agreement_required", "discussion": "x", "next_follow_up_on": "2030-01-10"})
```

- [ ] **Step 4: Run, expect PASS** — `<P>` = `tests/test_bdm_007_schemas.py tests/test_bdm_006_schemas.py tests/test_bdm_010_schemas.py`
  (the trip schemas share `_trip_text`).

- [ ] **Step 5: Commit** — `feat(bdm-007): meeting report schemas`.

---

### Task 3: Complete = file the report (service + route)

**Files:**
- Modify: `apps/api/app/services/bdm_appointments.py`
- Modify: `apps/api/app/api/bdm_appointments.py` (`complete_appointment`; `list_appointments` row call)
- Modify: `apps/api/tests/test_bdm_006_transitions.py`, `apps/api/tests/test_bdm_006_org_meetings.py:20`,
  `apps/api/tests/test_bdm_006_service.py:85-89`, `apps/api/tests/bdm006_helpers.py`
- Test: `apps/api/tests/test_bdm_007_reports.py`, `apps/api/tests/bdm007_helpers.py`

**Interfaces:**
- Consumes: Task 1 models, Task 2 schemas.
- Produces (service): `REPORT_FIELDS = BDM_REPORT_TEXT_FIELDS`; `NO_REPORT`, `REPORT_LOCKED`, `FOLLOW_UP_DONE` messages;
  `is_pending(appt, now) -> bool`; `pending_filter(pending: bool)`; `report_editable(report, now) -> bool`;
  `async load_report(db, appt_id, *, lock=False) -> BdmMeetingReport | None`;
  `async load_follow_up(db, appt_id, *, lock=False) -> BdmTask | None`;
  `async sync_follow_up(db, appt, due_on: date | None) -> str | None` (`created|moved|cancelled|reopened|None`);
  `permissions(user, appt, now, report=None)`; `row_out(appt, org, owner, now)`.
- Produces (tests): `tests/bdm007_helpers.py` → `REPORT`, `completed(client, db, org, **report) -> dict`.

- [ ] **Step 1: Failing tests** — `apps/api/tests/bdm007_helpers.py`:

```python
"""bdm-007 test builders (on bdm-006's)."""

from tests.bdm006_helpers import APPTS, create_appt, move_to_past

REPORT = {"outcome": "interested", "discussion": "Principal keen on IT training."}


async def completed(client, db, org: dict, **report) -> dict:
    """An appointment of the logged-in BDM, past its start, completed with REPORT (+ overrides)."""
    a = await create_appt(client, org)
    await move_to_past(db, a["id"])
    response = await client.post(f"{APPTS}/{a['id']}/complete", json={**REPORT, **report})
    assert response.status_code == 200, response.text
    return response.json()["appointment"]
```

`apps/api/tests/test_bdm_007_reports.py` (this task's part):

```python
"""bdm-007 -- filing, editing and reading meeting reports (spec §5; AC1-AC7)."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.models import AuditLog, BdmMeetingReport, BdmTask
from app.services.bdm_appointments import IST
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm006_helpers import APPTS, bdm_with_org, create_appt, move_to_past
from tests.bdm007_helpers import REPORT, completed


def today() -> str:
    return datetime.now(IST).date().isoformat()


def in_days(n: int) -> str:
    return (datetime.now(IST) + timedelta(days=n)).date().isoformat()


async def follow_ups(db, appt_id) -> list[tuple]:
    rows = await db.execute(
        select(BdmTask.kind, BdmTask.source, BdmTask.status, BdmTask.due_on, BdmTask.assignee_user_id)
        .where(BdmTask.source_appointment_id == appt_id).execution_options(populate_existing=True)
    )
    return [tuple(r) for r in rows.all()]


@pytest.mark.asyncio
async def test_complete_files_the_report_and_one_follow_up(client, db_session):
    """AC1, AC3: Interested + next action 'Send proposal' + a follow-up date (the source example)."""
    _, bdm, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org, next_action="Send proposal", responsible_person="Mrs Rao", next_follow_up_on=in_days(3))
    assert (a["status"], a["outcome"], a["next_follow_up_on"]) == ("completed", "interested", in_days(3))
    r = a["report"]
    assert (r["discussion"], r["next_action"], r["responsible_person"], r["requirements"], r["legacy"]) == (
        REPORT["discussion"], "Send proposal", "Mrs Rao", None, False)
    assert r["author"]["id"] == str(bdm.id)
    assert a["follow_up"]["status"] == "open" and a["follow_up"]["due_on"] == in_days(3)
    assert a["permissions"]["can_edit_report"] is True and a["outcome_pending"] is False
    assert [(k, s, st, str(d), u) for k, s, st, d, u in await follow_ups(db_session, a["id"])] == [
        ("follow_up", "appointment_outcome", "open", in_days(3), bdm.id)]


@pytest.mark.asyncio
async def test_complete_without_a_date_creates_no_follow_up(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org)
    assert a["follow_up"] is None and await follow_ups(db_session, a["id"]) == []


@pytest.mark.asyncio
async def test_cannot_complete_without_a_report(client, db_session):
    """AC1: the outcome alone (bdm-006's body) is refused; nothing is written."""
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    await move_to_past(db_session, a["id"])
    refused = await client.post(f"{APPTS}/{a['id']}/complete", json={"outcome": "interested"})
    assert refused.status_code == 422 and refused.json()["detail"][0]["loc"][-1] == "discussion"
    assert (await client.get(f"{APPTS}/{a['id']}")).json()["appointment"]["status"] == "scheduled"
    assert await db_session.scalar(select(func.count()).select_from(BdmMeetingReport).where(BdmMeetingReport.appointment_id == a["id"])) == 0


@pytest.mark.asyncio
async def test_report_rules_on_complete(client, db_session):
    """Future appointment -> 422; foreign outcome -> 422; past follow-up -> 422; second complete -> 409."""
    manager = await make_manager(db_session)
    await login(client, await make_bdm(db_session, manager, "agent"))
    org = await create_org(client)
    a = await create_appt(client, org, appointment_type="agent_visit")
    early = await client.post(f"{APPTS}/{a['id']}/complete", json=REPORT)
    assert (early.status_code, early.json()["detail"]) == (422, "You can only complete an appointment after its start time")
    await move_to_past(db_session, a["id"])
    foreign = await client.post(f"{APPTS}/{a['id']}/complete", json={**REPORT, "outcome": "course_promotion_interested"})
    assert (foreign.status_code, foreign.json()["detail"]) == (422, "This outcome is not available for Agent BDMs")
    stale = await client.post(f"{APPTS}/{a['id']}/complete", json={**REPORT, "outcome": "agreement_required", "next_follow_up_on": in_days(-2)})
    assert (stale.status_code, stale.json()["detail"]) == (422, "Next follow-up can't be in the past")
    ok = await client.post(f"{APPTS}/{a['id']}/complete", json={**REPORT, "outcome": "agreement_required", "next_follow_up_on": today()})
    assert ok.status_code == 200
    again = await client.post(f"{APPTS}/{a['id']}/complete", json={**REPORT, "outcome": "agreement_required"})
    assert (again.status_code, again.json()["detail"]) == (409, "Appointment is already completed")


@pytest.mark.asyncio
async def test_manager_reads_the_report_but_cannot_file_it(client, db_session):
    manager, _, org = await bdm_with_org(client, db_session)
    done = await completed(client, db_session, org)
    pending = await create_appt(client, org)
    await move_to_past(db_session, pending["id"])
    await login(client, manager)
    seen = (await client.get(f"{APPTS}/{done['id']}")).json()["appointment"]
    assert seen["report"]["discussion"] == REPORT["discussion"] and seen["permissions"]["can_edit_report"] is False
    refused = await client.post(f"{APPTS}/{pending['id']}/complete", json=REPORT)
    assert (refused.status_code, refused.json()["detail"]) == (403, "Only the appointment's BDM can change it")


@pytest.mark.asyncio
async def test_another_bdm_cannot_see_or_file(client, db_session):
    manager, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    await move_to_past(db_session, a["id"])
    await login(client, await make_bdm(db_session, manager))
    assert (await client.post(f"{APPTS}/{a['id']}/complete", json=REPORT)).status_code == 404  # out of scope, not 403 (IDOR)


@pytest.mark.asyncio
async def test_reschedule_outcome_creates_nothing_server_side(client, db_session):
    """AC6: the UI links to booking; the server books nothing."""
    _, bdm, org = await bdm_with_org(client, db_session)
    await completed(client, db_session, org, outcome="reschedule")
    listed = (await client.get(APPTS, params={"organization_id": org["id"], "date_from": in_days(-3)})).json()
    assert listed["total"] == 1


@pytest.mark.asyncio
async def test_report_text_never_reaches_audit_metadata(client, db_session):
    """AC7."""
    _, _, org = await bdm_with_org(client, db_session)
    secret = "Confidential fee of 9 lakh discussed"
    a = await completed(client, db_session, org, discussion=secret, responsible_person="Mr Secret", next_follow_up_on=in_days(1))
    rows = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == a["id"]))).all()
    assert rows and all(secret not in str(m) and "Mr Secret" not in str(m) for m in rows)
    complete = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == a["id"], AuditLog.action == "bdm_appointment.complete"))).one()
    assert complete == {"from": "scheduled", "to": "completed", "outcome": "interested", "follow_up": True}
```


- [ ] **Step 2: Run, expect FAIL** — `<P>` = `tests/test_bdm_007_reports.py` → `KeyError: 'report'` / 422s.

- [ ] **Step 3: Service** — `apps/api/app/services/bdm_appointments.py`:
  - imports: add `BdmMeetingReport, BdmTask` to the `app.models` import; `from sqlalchemy import and_, func, not_, select`;
    `from app.schemas import BDM_REPORT_TEXT_FIELDS`.
  - constants after `NOT_STARTED`:

```python
REPORT_FIELDS = BDM_REPORT_TEXT_FIELDS  # bdm-007: the narrative on bdm_meeting_reports; outcome / follow-up date stay on the appointment
NO_REPORT = "This appointment has no meeting report"
REPORT_LOCKED = "Meeting reports can only be changed on the day they were filed"
FOLLOW_UP_DONE = "This follow-up is already done"
```
  - functions (after `require_started`):

```python
def is_pending(appt: BdmAppointment, now: datetime) -> bool:
    """bdm-007 AC5: open and past its start -- waiting for a meeting report (bdm-023 AL-6 reads the same rule via `pending_filter`)."""
    return appt.status in BDM_APPOINTMENT_OPEN and appt.starts_at <= now


def pending_filter(pending: bool):
    expr = and_(BdmAppointment.status.in_(BDM_APPOINTMENT_OPEN), BdmAppointment.starts_at <= func.now())
    return expr if pending else not_(expr)


def report_editable(report: BdmMeetingReport, now: datetime) -> bool:
    """spec §5.4 (R2): the IST day it was filed; legacy reports never."""
    return not report.legacy and today_ist(report.submitted_at) == today_ist(now)


async def load_report(db: AsyncSession, appt_id: UUID, *, lock: bool = False) -> BdmMeetingReport | None:
    stmt = select(BdmMeetingReport).where(BdmMeetingReport.appointment_id == appt_id).execution_options(populate_existing=True)
    return await db.scalar(stmt.with_for_update() if lock else stmt)


async def load_follow_up(db: AsyncSession, appt_id: UUID, *, lock: bool = False) -> BdmTask | None:
    stmt = select(BdmTask).where(BdmTask.source_appointment_id == appt_id).execution_options(populate_existing=True)
    return await db.scalar(stmt.with_for_update() if lock else stmt)


async def sync_follow_up(db: AsyncSession, appt: BdmAppointment, due_on: date | None) -> str | None:
    """spec §4.3: the appointment's one follow-up tracks `due_on`; returns what changed (for the audit) or None. Caller holds the
    appointment lock (lock order appointment -> report -> follow-up)."""
    task = await load_follow_up(db, appt.id, lock=True)
    if task is None:
        if due_on is None:
            return None
        db.add(BdmTask(
            kind="follow_up", title=f"Follow up on {appt.code}", due_on=due_on, organization_id=appt.organization_id,
            source="appointment_outcome", source_appointment_id=appt.id, assignee_user_id=appt.bdm_user_id, status="open",
        ))
        return "created"
    if task.status == "done":
        raise HTTPException(409, FOLLOW_UP_DONE)
    if due_on is None:
        if task.status == "cancelled":
            return None
        task.status = "cancelled"
        return "cancelled"
    if task.status == "cancelled":
        task.status, task.due_on = "open", due_on
        return "reopened"
    if task.due_on == due_on:
        return None
    task.due_on = due_on
    return "moved"
```
  - `permissions(user, appt, now, report=None)` adds `"can_edit_report": owner and report is not None and report_editable(report, now)`.
  - `row_out(appt, org, owner, now)` adds `"outcome_pending": is_pending(appt, now)`.
  - `appointment_out`: read `now` before building; load the report with its author and the follow-up:

```python
    now = await db_now(db)
    report_row = (
        await db.execute(
            select(BdmMeetingReport, User).join(User, User.id == BdmMeetingReport.author_user_id)
            .where(BdmMeetingReport.appointment_id == appt.id).execution_options(populate_existing=True)
        )
    ).first()
    report, author = report_row if report_row else (None, None)
    follow_up = await load_follow_up(db, appt.id)
    return {
        **row_out(appt, org, owner, now),
        ...existing keys...,
        "report": None if report is None else {
            **{k: getattr(report, k) for k in REPORT_FIELDS}, "legacy": report.legacy, "author": person_ref(author),
            "submitted_at": report.submitted_at, "updated_at": report.updated_at,
        },
        "follow_up": None if follow_up is None else {"id": follow_up.id, "due_on": follow_up.due_on, "status": follow_up.status},
        "permissions": permissions(user, appt, now, report),
    }
```
- [ ] **Step 4: Route** — `apps/api/app/api/bdm_appointments.py`: import `BdmMeetingReportCreate` (drop `BdmAppointmentComplete`),
  `BdmMeetingReport`; in `list_appointments` add `now = await svc.db_now(db)` and call `svc.row_out(a, o, u, now)`; add helpers
  and replace `complete_appointment`:

```python
async def _outcome_allowed(db: AsyncSession, user: User, outcome: str) -> None:
    bdm_type = (await bdm_context(db, user)).bdm_type
    if outcome not in svc.appointment_outcomes(bdm_type):
        raise HTTPException(422, f"This outcome is not available for {bdm_type.capitalize()} BDMs")


def _follow_up_allowed(due_on: date | None, now) -> None:
    if due_on is not None and due_on < svc.today_ist(now):
        raise HTTPException(422, "Next follow-up can't be in the past")


@router.post("/{appt_id}/complete", response_model=BdmAppointmentEnvelope)
async def complete_appointment(appt_id: UUID, payload: BdmMeetingReportCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """bdm-007 AC1: filing the meeting report is the only way to complete. One transaction: status, report, follow-up (AC3), event,
    audit. A second complete meets `completed` under the row lock -> 409."""
    appt = await _transitioning(db, user, appt_id, "complete", "completed")
    now = await svc.db_now(db)
    svc.require_started(appt, now, "complete")
    await _outcome_allowed(db, user, payload.outcome)
    _follow_up_allowed(payload.next_follow_up_on, now)
    appt.outcome, appt.next_follow_up_on = payload.outcome, payload.next_follow_up_on
    db.add(BdmMeetingReport(appointment_id=appt.id, author_user_id=user.id, submitted_at=now, **{k: getattr(payload, k) for k in svc.REPORT_FIELDS}))
    follow_up = await svc.sync_follow_up(db, appt, payload.next_follow_up_on)
    return await _move(db, user, appt, "complete", "completed", {"outcome": payload.outcome, "follow_up": follow_up is not None})
```
- [ ] **Step 5: Older tests** — every bdm-006 `complete` body gains `"discussion": "Met"`:
  `test_bdm_006_transitions.py` lines 23, 26, 85, 96, 99, 101; `test_bdm_006_org_meetings.py:20`.
  `test_bdm_006_service.py:85` expected dict adds `"can_edit_report": False`.
- [ ] **Step 6: Run, expect PASS** — `<P>` = `tests/test_bdm_007_reports.py tests/test_bdm_006_*.py`.
- [ ] **Step 7: Commit** — `feat(bdm-007): completing an appointment files its meeting report and follow-up`.

---

### Task 4: Same-day report edit (`PATCH /{id}/report`)

**Files:** Modify `apps/api/app/api/bdm_appointments.py`; Test `apps/api/tests/test_bdm_007_reports.py` (append).

**Interfaces:** Consumes Task 3's `load_report`, `report_editable`, `sync_follow_up`, `_outcome_allowed`, `_follow_up_allowed`.

- [ ] **Step 1: Failing tests** (append):

```python
def report_url(appt: dict) -> str:
    return f"{APPTS}/{appt['id']}/report"


async def file_yesterday(db, appt_id) -> None:
    """The only way to test 'the next IST day': move submitted_at back one day."""
    await db.execute(update(BdmMeetingReport).where(BdmMeetingReport.appointment_id == appt_id).values(submitted_at=func.now() - timedelta(days=1)))
    await db.commit()


@pytest.mark.asyncio
async def test_author_edits_on_the_filing_day(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org)
    edited = await client.patch(report_url(a), json={"outcome": "mou_discussion_required", "requirements": "Lab with 40 seats", "next_action": "Send MoU draft"})
    assert edited.status_code == 200, edited.text
    e = edited.json()["appointment"]
    assert (e["outcome"], e["report"]["requirements"], e["report"]["next_action"]) == ("mou_discussion_required", "Lab with 40 seats", "Send MoU draft")
    meta = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == a["id"], AuditLog.action == "bdm_appointment.report_update"))).one()
    assert meta == {"fields": ["next_action", "outcome", "requirements"]}


@pytest.mark.asyncio
async def test_unchanged_values_are_not_an_edit(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org)
    same = await client.patch(report_url(a), json={"outcome": "interested", "discussion": REPORT["discussion"]})
    assert same.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == a["id"], AuditLog.action == "bdm_appointment.report_update")) == 0


@pytest.mark.asyncio
async def test_edit_window_closes_on_the_next_ist_day(client, db_session):
    """AC4."""
    _, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org)
    await file_yesterday(db_session, a["id"])
    seen = (await client.get(f"{APPTS}/{a['id']}")).json()["appointment"]
    assert seen["permissions"]["can_edit_report"] is False
    late = await client.patch(report_url(a), json={"next_action": "Too late"})
    assert (late.status_code, late.json()["detail"]) == (409, "Meeting reports can only be changed on the day they were filed")


@pytest.mark.asyncio
async def test_edit_refusals(client, db_session):
    manager, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org)
    open_ = await create_appt(client, org)
    no_report = await client.patch(report_url(open_), json={"next_action": "x"})
    assert (no_report.status_code, no_report.json()["detail"]) == (409, "This appointment has no meeting report")
    foreign = await client.patch(report_url(a), json={"outcome": "agreement_required"})
    assert (foreign.status_code, foreign.json()["detail"]) == (422, "This outcome is not available for College BDMs")
    past = await client.patch(report_url(a), json={"next_follow_up_on": in_days(-1)})
    assert (past.status_code, past.json()["detail"]) == (422, "Next follow-up can't be in the past")
    assert (await client.patch(report_url(a), json={"discussion": None})).status_code == 422
    await login(client, manager)
    refused = await client.patch(report_url(a), json={"next_action": "x"})
    assert (refused.status_code, refused.json()["detail"]) == (403, "Only the appointment's BDM can change it")
    await login(client, await make_bdm(db_session, manager))
    assert (await client.patch(report_url(a), json={"next_action": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_follow_up_moves_with_the_date(client, db_session):
    """AC3: one row; moved, never duplicated."""
    _, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org, next_follow_up_on=in_days(2))
    moved = (await client.patch(report_url(a), json={"next_follow_up_on": in_days(5)})).json()["appointment"]
    assert moved["follow_up"]["due_on"] == in_days(5) and moved["next_follow_up_on"] == in_days(5)
    assert [(st, str(d)) for _, _, st, d, _ in await follow_ups(db_session, a["id"])] == [("open", in_days(5))]


@pytest.mark.asyncio
async def test_follow_up_cleared_then_set_again_reuses_the_row(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org, next_follow_up_on=in_days(2))
    first_id = a["follow_up"]["id"]
    cleared = (await client.patch(report_url(a), json={"next_follow_up_on": None})).json()["appointment"]
    assert cleared["next_follow_up_on"] is None and cleared["follow_up"]["status"] == "cancelled"
    again = (await client.patch(report_url(a), json={"next_follow_up_on": in_days(4)})).json()["appointment"]
    assert again["follow_up"] == {"id": first_id, "due_on": in_days(4), "status": "open"}
    assert len(await follow_ups(db_session, a["id"])) == 1
    actions = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == a["id"], AuditLog.action == "bdm_appointment.report_update").order_by(AuditLog.created_at))).all()
    assert [m["follow_up"] for m in actions] == ["cancelled", "reopened"]


@pytest.mark.asyncio
async def test_a_date_added_on_edit_creates_the_follow_up(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org)
    added = (await client.patch(report_url(a), json={"next_follow_up_on": today()})).json()["appointment"]
    assert added["follow_up"]["status"] == "open" and len(await follow_ups(db_session, a["id"])) == 1


@pytest.mark.asyncio
async def test_a_done_follow_up_cannot_move(client, db_session):
    """bdm-008 will complete follow-ups; once done, the report can no longer move it."""
    _, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org, next_follow_up_on=in_days(2))
    await db_session.execute(update(BdmTask).where(BdmTask.source_appointment_id == a["id"]).values(status="done", completed_at=func.now()))
    await db_session.commit()
    refused = await client.patch(report_url(a), json={"next_follow_up_on": in_days(3)})
    assert (refused.status_code, refused.json()["detail"]) == (409, "This follow-up is already done")
```

- [ ] **Step 2: Run, expect FAIL** (405 Method Not Allowed on `/report`).
- [ ] **Step 3: Implement** — `apps/api/app/api/bdm_appointments.py` (import `BdmMeetingReportUpdate`):

```python
@router.patch("/{appt_id}/report", response_model=BdmAppointmentEnvelope)
async def update_report(appt_id: UUID, payload: BdmMeetingReportUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """bdm-007 §5.2 (AC4): the author changes the report on the IST day it was filed. Lock order appointment -> report -> follow-up.
    Values equal to the stored ones are not changes (no audit, no updated_at bump)."""
    appt = await svc.load_scoped(db, user, appt_id, lock=True)
    svc.require_owner(user, appt, "report_update")
    report = await svc.load_report(db, appt.id, lock=True)
    if report is None:
        raise HTTPException(409, svc.NO_REPORT)
    now = await svc.db_now(db)
    if not svc.report_editable(report, now):
        raise HTTPException(409, svc.REPORT_LOCKED)
    changes = payload.model_dump(exclude_unset=True)
    target = lambda key: report if key in svc.REPORT_FIELDS else appt  # noqa: E731 -- outcome / follow-up date live on the appointment
    changed = sorted(k for k, v in changes.items() if getattr(target(k), k) != v)
    if "outcome" in changed:
        await _outcome_allowed(db, user, changes["outcome"])
    follow_up = None
    if "next_follow_up_on" in changed:
        _follow_up_allowed(changes["next_follow_up_on"], now)
        follow_up = await svc.sync_follow_up(db, appt, changes["next_follow_up_on"])
    for key in changed:
        setattr(target(key), key, changes[key])
    if changed:
        svc.audit(db, user, "report_update", appt.id, {"fields": changed, **({"follow_up": follow_up} if follow_up else {})})
    await db.commit()
    if changed:
        svc.log("bdm_appt_report_updated", user, appt.id, fields=changed, follow_up=follow_up)
    return await _envelope(db, user, appt)
```
- [ ] **Step 4: Run, expect PASS** — `<P>` = `tests/test_bdm_007_reports.py`.
- [ ] **Step 5: Commit** — `feat(bdm-007): same-day meeting report edits keep one follow-up`.

---

### Task 5: Outcome pending (row flag + list filter)

**Files:** Modify `apps/api/app/api/bdm_appointments.py` (`list_appointments`); Test `test_bdm_007_reports.py` (append).

- [ ] **Step 1: Failing test**:

```python
@pytest.mark.asyncio
async def test_outcome_pending_flag_and_filter(client, db_session):
    """AC5: open + past start = pending; completed / cancelled / future are not. Managers filter their team."""
    manager, _, org = await bdm_with_org(client, db_session)
    pending = await create_appt(client, org)
    await move_to_past(db_session, pending["id"])
    future_ = await create_appt(client, org, starts_at=(datetime.now(IST) + timedelta(days=9)).replace(second=0, microsecond=0).isoformat())
    done = await completed(client, db_session, org)
    window = {"organization_id": org["id"], "date_from": in_days(-3)}
    rows = {r["id"]: r["outcome_pending"] for r in (await client.get(APPTS, params=window)).json()["items"]}
    assert rows == {pending["id"]: True, future_["id"]: False, done["id"]: False}
    only = (await client.get(APPTS, params={**window, "outcome_pending": "true"})).json()
    assert [r["id"] for r in only["items"]] == [pending["id"]] and only["total"] == 1
    others = (await client.get(APPTS, params={**window, "outcome_pending": "false"})).json()
    assert {r["id"] for r in others["items"]} == {future_["id"], done["id"]}
    await login(client, manager)
    team = (await client.get(APPTS, params={**window, "outcome_pending": "true"})).json()
    assert [r["id"] for r in team["items"]] == [pending["id"]]
    assert (await client.get(f"{APPTS}/{pending['id']}")).json()["appointment"]["outcome_pending"] is True
```

- [ ] **Step 2: Run, expect FAIL** (`outcome_pending` ignored → wrong rows).
- [ ] **Step 3: Implement** — `list_appointments` gains `outcome_pending: bool | None = None` (after `bdm_user_id`) and, after the
  status filter: `if outcome_pending is not None: filters.append(svc.pending_filter(outcome_pending))`. Docstring: "bdm-007 AC5:
  `outcome_pending` is the AL-6 rule bdm-023 reuses."
- [ ] **Step 4: Run, expect PASS.** **Step 5: Commit** — `feat(bdm-007): outcome-pending flag and list filter`.

---

### Task 6: Concurrency

**Files:** Test `apps/api/tests/test_bdm_007_concurrency.py`.

- [ ] **Step 1: Test** (expected to pass at once — the row lock exists; it pins the behavior):

```python
"""bdm-007 -- races (spec §6; Review Focus 3). Two real sessions through the app (bdm-006 pattern)."""

import asyncio
from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models import BdmMeetingReport, BdmTask
from app.services.bdm_appointments import IST
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm006_helpers import APPTS, create_appt, move_to_past
from tests.bdm007_helpers import REPORT, completed


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def in_days(n: int) -> str:
    return (datetime.now(IST) + timedelta(days=n)).date().isoformat()


async def _count(db, model, column, appt_id) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(column == appt_id))


@pytest.mark.asyncio
async def test_double_complete_files_one_report(db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session))
    async with _client() as one, _client() as two:
        await login(one, bdm)
        await login(two, bdm)
        a = await create_appt(one, await create_org(one))
        await move_to_past(db_session, a["id"])
        body = {**REPORT, "next_follow_up_on": in_days(2)}
        results = await asyncio.gather(one.post(f"{APPTS}/{a['id']}/complete", json=body), two.post(f"{APPTS}/{a['id']}/complete", json=body))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert await _count(db_session, BdmMeetingReport, BdmMeetingReport.appointment_id, a["id"]) == 1
    assert await _count(db_session, BdmTask, BdmTask.source_appointment_id, a["id"]) == 1


@pytest.mark.asyncio
async def test_complete_and_cancel_race_never_leaves_a_report_on_a_cancelled_appointment(db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session))
    async with _client() as one, _client() as two:
        await login(one, bdm)
        await login(two, bdm)
        a = await create_appt(one, await create_org(one))
        await move_to_past(db_session, a["id"])
        done, cancel = await asyncio.gather(one.post(f"{APPTS}/{a['id']}/complete", json=REPORT), two.post(f"{APPTS}/{a['id']}/cancel", json={"reason": "Clash"}))
    assert sorted((done.status_code, cancel.status_code)) == [200, 409]
    assert await _count(db_session, BdmMeetingReport, BdmMeetingReport.appointment_id, a["id"]) == (1 if done.status_code == 200 else 0)


@pytest.mark.asyncio
async def test_two_edits_of_the_follow_up_keep_one_row(db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session))
    async with _client() as one, _client() as two:
        await login(one, bdm)
        await login(two, bdm)
        a = await completed(one, db_session, await create_org(one), next_follow_up_on=in_days(2))
        url = f"{APPTS}/{a['id']}/report"
        results = await asyncio.gather(one.patch(url, json={"next_follow_up_on": None}), two.patch(url, json={"next_follow_up_on": in_days(6)}))
    assert all(r.status_code == 200 for r in results)
    assert await _count(db_session, BdmTask, BdmTask.source_appointment_id, a["id"]) == 1
```
- [ ] **Step 2: Run, expect PASS** — `<P>` = `tests/test_bdm_007_concurrency.py`. If a 500 appears, the lock order is wrong — fix the route, not the test.
- [ ] **Step 3: Backend lite run** — `<P>` = LITE. Record the count. **Step 4: Commit** — `test(bdm-007): report races`.

---

### Task 7: Web types + `BdmMeetingReportForm`

**Files:**
- Modify: `apps/web/lib/bdmAppointments.ts`
- Rename: `apps/web/components/BdmAppointmentCompleteForm.tsx` → `apps/web/components/BdmMeetingReportForm.tsx` (`git mv`)
- Test: `apps/web/tests/components/BdmMeetingReportForm.test.tsx`

**Interfaces:**
- Produces (`lib/bdmAppointments.ts`):

```ts
export type MeetingReport = {
  discussion: string | null; requirements: string | null; opportunity: string | null; next_action: string | null;
  responsible_person: string | null; legacy: boolean; author: { id: string; full_name: string; active: boolean };
  submitted_at: string; updated_at: string;
};
export type FollowUp = { id: string; due_on: string; status: "open" | "done" | "cancelled" };
export type ReportBody = {
  outcome: string; discussion: string; requirements: string | null; opportunity: string | null; next_action: string | null;
  responsible_person: string | null; next_follow_up_on: string | null;
};
export const REPORT_LIMITS = { discussion: 4000, requirements: 2000, opportunity: 2000, next_action: 1000, responsible_person: 200 } as const;
export const REPORT_FIELD_LABEL: Record<keyof typeof REPORT_LIMITS, string> = {
  discussion: "Discussion", requirements: "Requirements", opportunity: "Opportunity", next_action: "Next action", responsible_person: "Responsible person",
};
```
  `AppointmentPermissions` adds `can_edit_report: boolean`; `AppointmentRow` adds `outcome_pending: boolean`; `Appointment` adds
  `report: MeetingReport | null; follow_up: FollowUp | null`.
- Produces (component): `BdmMeetingReportForm({ bdmType, mode, initial, busy, errors, onSubmit, onCancel })` —
  `mode: "complete" | "edit"`, `initial?: { outcome: string | null; next_follow_up_on: string | null; report: MeetingReport | null }`,
  `errors?: Record<string, string>`, `onSubmit(body: ReportBody)`.

- [ ] **Step 1: Failing test** — `apps/web/tests/components/BdmMeetingReportForm.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import BdmMeetingReportForm from "@/components/BdmMeetingReportForm";

describe("BdmMeetingReportForm", () => {
  it("needs an outcome and a discussion, then sends every field (blanks as null)", () => {
    const onSubmit = vi.fn();
    render(<BdmMeetingReportForm bdmType="college" mode="complete" busy={false} onSubmit={onSubmit} onCancel={() => {}} />);
    const save = screen.getByRole("button", { name: "Save report and complete" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Outcome (required)"), { target: { value: "interested" } });
    fireEvent.change(screen.getByLabelText("Discussion (required)"), { target: { value: "   " } });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Discussion (required)"), { target: { value: "Keen on IT training\nwants fees" } });
    fireEvent.change(screen.getByLabelText("Next action"), { target: { value: "Send proposal" } });
    fireEvent.click(save);
    expect(onSubmit).toHaveBeenCalledWith({
      outcome: "interested", discussion: "Keen on IT training\nwants fees", requirements: null, opportunity: null,
      next_action: "Send proposal", responsible_person: null, next_follow_up_on: null,
    });
  });

  it("offers only the BDM type's outcomes", () => {
    render(<BdmMeetingReportForm bdmType="agent" mode="complete" busy={false} onSubmit={() => {}} onCancel={() => {}} />);
    const values = Array.from((screen.getByLabelText("Outcome (required)") as HTMLSelectElement).options).map((o) => o.value);
    expect(values).toContain("agreement_required");
    expect(values).not.toContain("course_promotion_interested");
  });

  it("prefills in edit mode, limits lengths, and shows field errors accessibly", () => {
    render(
      <BdmMeetingReportForm
        bdmType="college" mode="edit" busy={false} onSubmit={() => {}} onCancel={() => {}}
        initial={{ outcome: "interested", next_follow_up_on: "2030-01-10", report: { discussion: "Met", requirements: null, opportunity: "Lab", next_action: null, responsible_person: "Mrs Rao", legacy: false, author: { id: "u", full_name: "B", active: true }, submitted_at: "2030-01-01T05:00:00Z", updated_at: "2030-01-01T05:00:00Z" } }}
        errors={{ opportunity: "Opportunity contains invalid characters" }}
      />,
    );
    expect(screen.getByLabelText("Discussion (required)")).toHaveValue("Met");
    expect(screen.getByLabelText("Discussion (required)")).toHaveAttribute("maxLength", "4000");
    expect(screen.getByLabelText("Responsible person")).toHaveValue("Mrs Rao");
    expect(screen.getByLabelText("Next follow-up (IST date)")).toHaveValue("2030-01-10");
    const opportunity = screen.getByLabelText("Opportunity");
    expect(opportunity).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Opportunity contains invalid characters")).toHaveAttribute("id", opportunity.getAttribute("aria-describedby"));
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
  });

  it("Escape cancels; busy disables saving", () => {
    const onCancel = vi.fn();
    render(<BdmMeetingReportForm bdmType="college" mode="complete" busy onSubmit={() => {}} onCancel={onCancel} />);
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    fireEvent.keyDown(screen.getByLabelText("Outcome (required)"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });
});
```
- [ ] **Step 2: Run, expect FAIL** — vitest `tests/components/BdmMeetingReportForm.test.tsx` (module not found).
- [ ] **Step 3: Implement** — `git mv` then replace the content of `apps/web/components/BdmMeetingReportForm.tsx`:

```tsx
"use client";
import { type ChangeEvent, type FormEvent, useId, useState } from "react";

import type { BdmType } from "@/lib/bdm";
import { appointmentOutcomes, type MeetingReport, OUTCOME_LABEL, REPORT_FIELD_LABEL, REPORT_LIMITS, type ReportBody, todayIst } from "@/lib/bdmAppointments";

type Initial = { outcome: string | null; next_follow_up_on: string | null; report: MeetingReport | null };
type Values = { outcome: string; discussion: string; requirements: string; opportunity: string; next_action: string; responsible_person: string; next_follow_up_on: string };
const LONG_FIELDS = ["requirements", "opportunity", "next_action"] as const;

// bdm-007 (spec §8): the meeting report -- filed to complete an appointment, or changed on the IST day it was filed. The API is the
// authority (lists, lengths, dates); this form only helps. Blanks are sent as null. Typed text is never cleared by a failed save.
export default function BdmMeetingReportForm({ bdmType, mode, initial, busy, errors = {}, onSubmit, onCancel }: {
  bdmType: BdmType; mode: "complete" | "edit"; initial?: Initial; busy: boolean; errors?: Record<string, string>;
  onSubmit: (body: ReportBody) => void; onCancel: () => void;
}) {
  const id = useId();
  const r = initial?.report;
  const [v, setV] = useState<Values>({
    outcome: initial?.outcome ?? "", discussion: r?.discussion ?? "", requirements: r?.requirements ?? "", opportunity: r?.opportunity ?? "",
    next_action: r?.next_action ?? "", responsible_person: r?.responsible_person ?? "", next_follow_up_on: initial?.next_follow_up_on ?? "",
  });
  const set = (key: keyof Values) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setV({ ...v, [key]: e.target.value });
  const fid = (key: string) => `${id}-${key}`;
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="field-error">{errors[key]}</p>;
  const ready = Boolean(v.outcome && v.discussion.trim());
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    const text = (s: string) => s.trim() || null;
    onSubmit({
      outcome: v.outcome, discussion: v.discussion, requirements: text(v.requirements), opportunity: text(v.opportunity),
      next_action: text(v.next_action), responsible_person: text(v.responsible_person), next_follow_up_on: v.next_follow_up_on || null,
    });
  };
  return (
    <form aria-label={mode === "complete" ? "Meeting report" : "Edit meeting report"} className="action-card" onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="field">
        <label htmlFor={fid("outcome")}>Outcome (required)</label>
        <select id={fid("outcome")} autoFocus required aria-required="true" value={v.outcome} onChange={set("outcome")} {...invalid("outcome")}>
          <option value="">Choose an outcome</option>
          {appointmentOutcomes(bdmType).map((o) => <option key={o} value={o}>{OUTCOME_LABEL[o]}</option>)}
        </select>
        {error("outcome")}
      </div>
      <div className="field">
        <label htmlFor={fid("discussion")}>Discussion (required)</label>
        <textarea id={fid("discussion")} required aria-required="true" rows={4} maxLength={REPORT_LIMITS.discussion} value={v.discussion} onChange={set("discussion")} {...invalid("discussion")} />
        <p className="field-hint">What was discussed. Up to 4,000 characters.</p>
        {error("discussion")}
      </div>
      {LONG_FIELDS.map((key) => (
        <div className="field" key={key}>
          <label htmlFor={fid(key)}>{REPORT_FIELD_LABEL[key]}</label>
          <textarea id={fid(key)} rows={2} maxLength={REPORT_LIMITS[key]} value={v[key]} onChange={set(key)} {...invalid(key)} />
          {error(key)}
        </div>
      ))}
      <div className="field">
        <label htmlFor={fid("responsible_person")}>Responsible person</label>
        <input id={fid("responsible_person")} maxLength={REPORT_LIMITS.responsible_person} value={v.responsible_person} onChange={set("responsible_person")} {...invalid("responsible_person")} />
        {error("responsible_person")}
      </div>
      <div className="field">
        <label htmlFor={fid("next_follow_up_on")}>Next follow-up (IST date)</label>
        <input id={fid("next_follow_up_on")} type="date" min={todayIst()} value={v.next_follow_up_on} onChange={set("next_follow_up_on")} {...invalid("next_follow_up_on")} />
        <p className="field-hint">A date creates one follow-up for you.</p>
        {error("next_follow_up_on")}
      </div>
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || !ready}>
          {busy ? "Saving…" : mode === "complete" ? "Save report and complete" : "Save changes"}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
```
  (Check `.field-error` exists in `app/globals.css`; if the activity form uses another class for field errors, use that one.)
- [ ] **Step 4: Run, expect PASS.** **Step 5: Commit** — `feat(bdm-007): meeting report form`.

---

### Task 8: Actions + report section on the detail page

**Files:**
- Modify: `apps/web/components/BdmAppointmentActions.tsx`, `apps/web/components/BdmAppointmentDetail.tsx`
- Create: `apps/web/components/BdmMeetingReportSection.tsx`
- Test: `apps/web/tests/components/BdmAppointmentActions.test.tsx`, `apps/web/tests/components/BdmAppointmentDetail.test.tsx`,
  `apps/web/tests/components/BdmMeetingReportSection.test.tsx` (new); fixtures in `BdmAppointmentForm.test.tsx` gain the new keys.

**Interfaces:**
- Consumes Task 7. Produces `BdmMeetingReportSection({ appointment, bdmType, onChanged })` (`bdmType` null = manager view).

- [ ] **Step 1: Failing tests.**
  - `BdmAppointmentActions.test.tsx`: the "completes with an outcome" test becomes:

```tsx
  it("completes by filing the meeting report", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ appointment: appt({ status: "completed", outcome: "agreement_required" }) })));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_complete: true } })} bdmType="agent" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Complete" }));
    fireEvent.change(screen.getByLabelText("Outcome (required)"), { target: { value: "agreement_required" } });
    fireEvent.change(screen.getByLabelText("Discussion (required)"), { target: { value: "Agreement terms" } });
    fireEvent.click(screen.getByRole("button", { name: "Save report and complete" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(String(((fetchMock.mock.calls[0] as unknown[])[1] as RequestInit).body))).toEqual({
      outcome: "agreement_required", discussion: "Agreement terms", requirements: null, opportunity: null, next_action: null, responsible_person: null, next_follow_up_on: null,
    });
  });

  it("keeps the typed report on a 409", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Appointment is already completed" }, 409))));
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_complete: true } })} bdmType="college" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Complete" }));
    fireEvent.change(screen.getByLabelText("Outcome (required)"), { target: { value: "interested" } });
    fireEvent.change(screen.getByLabelText("Discussion (required)"), { target: { value: "Long notes" } });
    fireEvent.click(screen.getByRole("button", { name: "Save report and complete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This appointment changed elsewhere — copy your notes, then reload.");
    expect(screen.getByLabelText("Discussion (required)")).toHaveValue("Long notes");
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it("maps a 422 field error onto the report field", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: [{ loc: ["body", "opportunity"], msg: "Value error, Opportunity contains invalid characters" }] }, 422))));
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_complete: true } })} bdmType="college" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Complete" }));
    fireEvent.change(screen.getByLabelText("Outcome (required)"), { target: { value: "interested" } });
    fireEvent.change(screen.getByLabelText("Discussion (required)"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Save report and complete" }));
    expect(await screen.findByText("Opportunity contains invalid characters")).toBeInTheDocument();
  });
```
  (The file's `appt()` fixture and `none` gain `outcome_pending: false, report: null, follow_up: null` and `can_edit_report: false`.)
  - `BdmMeetingReportSection.test.tsx` (new):

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmMeetingReportSection from "@/components/BdmMeetingReportSection";
import type { Appointment } from "@/lib/bdmAppointments";

const report = { discussion: "Line one\nLine two", requirements: null, opportunity: "Lab", next_action: "Send proposal", responsible_person: "Mrs Rao", legacy: false, author: { id: "b1", full_name: "Asha BDM", active: true }, submitted_at: "2030-01-01T05:00:00Z", updated_at: "2030-01-01T05:00:00Z" };
const none = { can_edit: false, can_confirm: false, can_reschedule: false, can_cancel: false, can_no_show: false, can_complete: false, can_edit_report: false };
const appt = (over: Partial<Appointment> = {}): Appointment => ({
  id: "a1", code: "APT-000001", starts_at: "2030-01-01T04:30:00Z", duration_minutes: 60, appointment_type: "college_meeting", status: "completed",
  organization: { id: "o1", code: "ORG-1", name: "Acme College", archived: false }, contact_name: "Dr Rao", bdm: { id: "b1", full_name: "Asha BDM", active: true },
  outcome_pending: false, contact_id: null, contact_designation: null, contact_phone: null, contact_email: null, location: null, purpose: null, remarks: null,
  outcome: "interested", next_follow_up_on: "2030-01-10", expected_leads: null, expected_revenue: null, events: [], permissions: none,
  report, follow_up: { id: "t1", due_on: "2030-01-10", status: "open" }, created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-01T00:00:00Z", ...over,
} as Appointment);
const res = (body: unknown, status = 200) => ({ ok: status < 400, status, json: () => Promise.resolve(body) }) as Response;

afterEach(() => vi.unstubAllGlobals());

describe("BdmMeetingReportSection", () => {
  it("shows every report field as plain text with line breaks kept", () => {
    render(<BdmMeetingReportSection appointment={appt({ report: { ...report, discussion: "<b>bold</b>\nnext" } })} bdmType={null} onChanged={() => {}} />);
    const region = screen.getByRole("region", { name: "Meeting report" });
    expect(region).toHaveTextContent("Interested");
    expect(region).toHaveTextContent("<b>bold</b>");  // escaped, never rendered as HTML
    expect(region).toHaveTextContent("Send proposal");
    expect(region).toHaveTextContent("Mrs Rao");
    expect(region).toHaveTextContent("Asha BDM");
    expect(screen.queryByRole("button", { name: "Edit report" })).toBeNull();
  });

  it("says a legacy report has the outcome only", () => {
    render(<BdmMeetingReportSection appointment={appt({ report: { ...report, legacy: true, discussion: null } })} bdmType="college" onChanged={() => {}} />);
    expect(screen.getByText("Recorded before meeting reports — outcome only.")).toBeInTheDocument();
  });

  it("edits on the filing day and re-renders from the response", async () => {
    const saved = appt({ report: { ...report, next_action: "Call back" }, permissions: { ...none, can_edit_report: true } });
    const fetchMock = vi.fn(() => Promise.resolve(res({ appointment: saved })));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    render(<BdmMeetingReportSection appointment={appt({ permissions: { ...none, can_edit_report: true } })} bdmType="college" onChanged={onChanged} />);
    expect(screen.getByText("You can change this report until midnight IST today.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit report" }));
    fireEvent.change(screen.getByLabelText("Next action"), { target: { value: "Call back" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(saved, "Meeting report saved."));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect([url, init.method]).toEqual(["/api/v1/bdm/appointments/a1/report", "PATCH"]);
  });

  it("keeps the edit text when the window has closed (409)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Meeting reports can only be changed on the day they were filed" }, 409))));
    render(<BdmMeetingReportSection appointment={appt({ permissions: { ...none, can_edit_report: true } })} bdmType="college" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit report" }));
    fireEvent.change(screen.getByLabelText("Next action"), { target: { value: "Late edit" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Meeting reports can only be changed on the day they were filed");
    expect(screen.getByLabelText("Next action")).toHaveValue("Late edit");
  });

  it("offers booking the next meeting after a Reschedule outcome, for the BDM only", () => {
    const { rerender } = render(<BdmMeetingReportSection appointment={appt({ outcome: "reschedule" })} bdmType="college" onChanged={() => {}} />);
    expect(screen.getByRole("link", { name: "Book the next meeting" })).toHaveAttribute("href", "/bdm/appointments/new?organization=o1");
    rerender(<BdmMeetingReportSection appointment={appt({ outcome: "reschedule" })} bdmType={null} onChanged={() => {}} />);
    expect(screen.queryByRole("link", { name: "Book the next meeting" })).toBeNull();
  });

  it("shows a cancelled follow-up as cancelled", () => {
    render(<BdmMeetingReportSection appointment={appt({ next_follow_up_on: null, follow_up: { id: "t1", due_on: "2030-01-10", status: "cancelled" } })} bdmType="college" onChanged={() => {}} />);
    expect(screen.getByRole("region", { name: "Meeting report" })).toHaveTextContent("—");
  });
});
```
  - `BdmAppointmentDetail.test.tsx`: fixtures gain the new keys; line 42 expectation becomes
    `"Outcome pending — file the meeting report, or mark it as a no-show."`; add:

```tsx
  it("tells a manager the outcome is pending", () => {
    render(<BdmAppointmentDetail initial={appt({ status: "confirmed", outcome: null, next_follow_up_on: null, report: null, follow_up: null, outcome_pending: true })} basePath="/bdm/manager/appointments" bdmType={null} />);
    expect(screen.getByRole("note")).toHaveTextContent("Outcome pending — the BDM hasn't filed the meeting report yet.");
    expect(screen.getByText("Outcome pending", { selector: ".badge" })).toBeInTheDocument();
  });
```
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - `BdmAppointmentActions.tsx`: import `BdmMeetingReportForm` (drop CompleteForm) and `fieldErrors` from `@/lib/bdmTravel`; add
    `const [fieldErrs, setFieldErrs] = useState<Record<string, string>>({});`; in `act`, reset `setFieldErrs({})` at the start; before
    the generic 409 refetch, for `path === "complete"`:

```tsx
    if (!outcome.ok && path === "complete") {
      if (outcome.status === 409) return setFailure(CHANGED_ELSEWHERE); // keep the form and the typed report (Review Focus 5)
      const mapped = fieldErrors(outcome.detail);
      if (Object.keys(mapped).length) {
        setFieldErrs(mapped);
        return setFailure("Check the highlighted fields.");
      }
    }
```
    with `const CHANGED_ELSEWHERE = "This appointment changed elsewhere — copy your notes, then reload.";` and, under the failure
    message when it equals `CHANGED_ELSEWHERE`, a `Reload` button: `onClick={async () => { const fresh = await refetch(); if (fresh) { setOpen(null); onChanged(fresh, \`This appointment is now ${STATUS_LABEL[fresh.status]}.\`); } }}`.
    The complete group renders
    `<BdmMeetingReportForm bdmType={bdmType} mode="complete" busy={busy} errors={fieldErrs} onSubmit={(body) => void act("complete", body)} onCancel={() => close("complete")} />`.
  - `BdmMeetingReportSection.tsx`:

```tsx
"use client";
import Link from "next/link";
import { useState } from "react";

import BdmMeetingReportForm from "@/components/BdmMeetingReportForm";
import { sendJson } from "@/lib/apiErrors";
import type { BdmType } from "@/lib/bdm";
import { type Appointment, APPOINTMENTS_URL, isAppointmentBody, OUTCOME_LABEL, type ReportBody } from "@/lib/bdmAppointments";
import { display, LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";
import { fieldErrors } from "@/lib/bdmTravel";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere", margin: 0 } as const;

// bdm-007 (spec §8): the filed meeting report. React renders every value as text (no HTML). The author edits it on the IST day it
// was filed (`can_edit_report`; the API decides). A failed save keeps the form and its text.
export default function BdmMeetingReportSection({ appointment: a, bdmType, onChanged }: { appointment: Appointment; bdmType: BdmType | null; onChanged: (a: Appointment, text: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const focus = useFocusAfterRender();
  const r = a.report;
  if (!r) return null;
  const editId = `appt-${a.id}-edit-report`;

  async function save(body: ReportBody) {
    setBusy(true);
    setFailure(null);
    setErrors({});
    const outcome = await sendJson(`${APPOINTMENTS_URL}/${a.id}/report`, "PATCH", body);
    setBusy(false);
    if (outcome.ok && isAppointmentBody(outcome.data)) {
      setEditing(false);
      return onChanged(outcome.data.appointment, "Meeting report saved.");
    }
    const mapped = outcome.ok ? {} : fieldErrors(outcome.detail);
    setErrors(mapped);
    const server = !outcome.ok && (outcome.status ?? 0) >= 500;
    setFailure(Object.keys(mapped).length ? "Check the highlighted fields." : outcome.ok ? "Unable to save the report." : server ? "We couldn't save the report. Please try again — your text is kept." : outcome.message);
  }

  const followUp = a.next_follow_up_on ? formatCalendarDate(a.next_follow_up_on) : "—";
  const rows: [string, string][] = [
    ["Outcome", OUTCOME_LABEL[a.outcome ?? ""] ?? display(a.outcome)],
    ["Discussion", display(r.discussion)],
    ["Requirements", display(r.requirements)],
    ["Opportunity", display(r.opportunity)],
    ["Next action", display(r.next_action)],
    ["Responsible person", display(r.responsible_person)],
    ["Next follow-up", followUp],
    ["Filed", `${r.author.full_name}, ${formatSchoolDateTime(r.submitted_at, true)}`],
  ];
  return (
    <section className="action-card wide" aria-label="Meeting report">
      <h3>Meeting report</h3>
      {r.legacy && <p className="muted">Recorded before meeting reports — outcome only.</p>}
      {editing && bdmType ? (
        <BdmMeetingReportForm bdmType={bdmType} mode="edit" busy={busy} errors={errors} initial={{ outcome: a.outcome, next_follow_up_on: a.next_follow_up_on, report: r }} onSubmit={(body) => void save(body)} onCancel={() => { setEditing(false); setFailure(null); focus(editId); }} />
      ) : (
        <dl style={{ display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "8px 16px", margin: 0 }}>
          {rows.map(([label, value]) => [
            <dt key={`${label}-t`} className="muted">{label}</dt>,
            <dd key={`${label}-d`} style={TEXT}>{value}</dd>,
          ])}
        </dl>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {!editing && (
        <div className="actions">
          {a.permissions.can_edit_report && bdmType && (
            <>
              <button id={editId} type="button" className="btn secondary small" onClick={() => setEditing(true)}>Edit report</button>
              <span className="field-hint">You can change this report until midnight IST today.</span>
            </>
          )}
          {a.outcome === "reschedule" && bdmType && !a.organization.archived && (
            <Link className="btn small" href={`/bdm/appointments/new?organization=${encodeURIComponent(a.organization.id)}`} style={LINK_STYLE}>Book the next meeting</Link>
          )}
        </div>
      )}
    </section>
  );
}
```
  - `BdmAppointmentDetail.tsx`: replace the "Outcome" section with `<BdmMeetingReportSection appointment={appt} bdmType={bdmType} onChanged={changed} />`;
    replace the `p.can_complete` note text with "Outcome pending — file the meeting report, or mark it as a no-show."; add
    `{appt.outcome_pending && !p.can_complete && <p className="muted" role="note">Outcome pending — the BDM hasn't filed the meeting report yet.</p>}`;
    in the `h2` after the status pill: `{appt.outcome_pending && <span className="badge">Outcome pending</span>}`; drop now-unused imports
    (`OUTCOME_LABEL`, `formatCalendarDate`) if lint flags them.
- [ ] **Step 4: Run, expect PASS** — vitest `tests/components/BdmAppointment*.test.tsx tests/components/BdmMeetingReport*.test.tsx`.
- [ ] **Step 5: Commit** — `feat(bdm-007): file and edit the meeting report from the appointment page`.

---

### Task 9: List — "Outcome pending" filter and badge

**Files:** Modify `apps/web/components/BdmAppointmentsPanel.tsx`; Test `apps/web/tests/components/BdmAppointmentsPanel.test.tsx`.

- [ ] **Step 1: Failing test** (append; reuse the file's `row()` / fetch helpers — add `outcome_pending` to its row fixture):

```tsx
  it("filters outcome-pending appointments and labels them in text", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ items: [row({ outcome_pending: true })], total: 1, limit: 25, offset: 0 })));
    vi.stubGlobal("fetch", fetchMock);
    setParams("status=outcome_pending&date_from=");
    render(<BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={["college_meeting"]} />);
    expect(await screen.findByText("Outcome pending", { selector: ".badge" })).toBeInTheDocument();
    const url = String((fetchMock.mock.calls[0] as unknown[])[0]);
    expect(url).toContain("outcome_pending=true");
    expect(url).not.toContain("status=");
    expect(url).not.toContain("date_from=");
    expect((screen.getByLabelText("Status") as HTMLSelectElement).value).toBe("outcome_pending");
  });
```
  (`setParams` = however the file mocks `useSearchParams`; follow its existing pattern.)
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** — in `BdmAppointmentsPanel.tsx`:
  - `const PENDING = "outcome_pending";` readFilters: `status: (STATUSES as readonly string[]).includes(status) || status === PENDING ? status : ""`.
  - toApi: `if (f.status === PENDING) query.set("outcome_pending", "true"); else if (f.status) query.set("status", f.status);`
  - Status select: after the statuses, `<option value={PENDING}>Outcome pending</option>`; `onChange={(e) => go({ status: e.target.value, ...(e.target.value === PENDING ? { dateFrom: "" } : {}) })}`.
  - Status cell: after the status pill, `{r.outcome_pending && <> <span className="badge">Outcome pending</span></>}`.
- [ ] **Step 4: Run, expect PASS.** **Step 5: Commit** — `feat(bdm-007): outcome-pending filter and badge on the appointment list`.

---

### Task 10: E2E specs, docs, lite verification

**Files:**
- Modify: `apps/web/tests/e2e/bdm-006-appointments.spec.ts:75-82`
- Create: `apps/web/tests/e2e/bdm-007-meeting-reports.spec.ts`
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append `DEC-SCOPE-070`), `docs/delivery/BDM_CRM_BACKLOG.md` (bdm-007 status
  line; bdm-006's "A1" note gains "superseded by bdm-007's report"), `docs/architecture/DATA_MODEL.md` (two tables),
  `docs/architecture/API_CONTRACT.md` (complete body, PATCH report, `outcome_pending`), `docs/quality/RTM.md` (bdm-007 rows → tests).

- [ ] **Step 1: bdm-006 e2e** — lines 80–82 become:

```ts
  await page.getByLabel("Outcome (required)").selectOption("interested");
  await page.getByLabel("Discussion (required)").fill("Principal keen on IT training.");
  await page.getByRole("button", { name: "Save report and complete" }).click();
  await expect(page.getByRole("region", { name: "Meeting report" })).toContainText("Interested");
```
- [ ] **Step 2: bdm-007 e2e** — copy the bdm-006 spec's setup (BDM sign-in, organization, appointment, moving it into the past the
  way that spec does) and assert: the list's "Outcome pending" filter shows the past appointment with the badge; Complete →
  report with "Send proposal" and a follow-up date → the Meeting report region shows them; Edit report → change Next action →
  "Meeting report saved."; a 390 px viewport run of the report form has no horizontal scroll
  (`expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)`). Not run in this
  session (browser validation runs it).
- [ ] **Step 3: Docs** — `DEC-SCOPE-070` entry (question, evidence, resolution R1–R7 + defaults, consequences: migration 0072, the
  `/complete` body change, `bdm_tasks` owned jointly with bdm-008; status `EXPLICIT_APPROVAL`, implementation on the branch, NOT
  COMPLETE pending browser validation + Codex review). Backlog bdm-007 status line in the same wording.
- [ ] **Step 4: Lite verification** — backend LITE; web `npx vitest run tests/components/BdmAppointment* tests/components/BdmMeetingReport* tests/lib/bdmAppointments.test.ts`;
  `npx tsc --noEmit`; `npx eslint` on the changed web files; `ruff check` on the changed api files (if configured in the image).
  Record the counts in the commit message. Do not run the full suites.
- [ ] **Step 5: Commit** — `docs(bdm-007): DEC-SCOPE-070, backlog, data model, API contract, RTM; e2e specs`.
