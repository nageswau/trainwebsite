# bdm-009 BDM Activity Log — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The assigned BDM logs calls, WhatsApp messages, emails, visits, meetings and other contacts against an organization;
every reader of the organization sees its activity timeline; the BDM and their manager see a day's activities with exact
per-channel counts.

**Architecture:** Flat feature module (spec §2, Approach A), the shape of bdm-002/006/010: `app/api/bdm_activities.py` (routes,
locks, one commit) over `app/services/bdm_activities.py` (time rules, scope, rows, `day_counts`, audit; never commits), one new
table in migration `0069_bdm_activities`. The web adds `lib/bdmActivities.ts`, five components, two pages and one section on
the organization profile.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, PostgreSQL; Next.js (App Router), React, Vitest, Testing
Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-03-bdm-009-activity-log-design.md`. Read it with this plan.

## Global Constraints

- Branch `feature/bdm-009-activities` (from `origin/main` @ `65a8ece0`); migration `0069_bdm_activities` (down_revision
  `0068_bdm_trips`); decision `DEC-SCOPE-065`. Before Task 1 and before the PR: `git fetch origin` and check `main` for a newer
  migration / DEC (bdm-006 and bdm-003 are in flight); if one landed, renumber.
- No new dependency (backend or web).
- Channels: `call, whatsapp, email, visit, meeting, other`. Directions: `outbound, inbound` — required for `call, whatsapp, email`,
  NULL for the rest. UI labels: Outgoing / Incoming.
- Time: `occurred_at` is timezone-aware; more than 5 minutes after `now` → 422, up to 5 minutes after → saved as `now` (V9); IST date
  ≥ IST today − 7; edit / delete only when the activity's IST date is IST today; a PATCH cannot move `occurred_at` off IST today.
  IST = `Asia/Kolkata`; `now` = the database clock read once per request.
- Daily cap (V10): at most 200 activities per BDM per IST day; the 201st create → 409 "You've logged 200 activities for this day".
- People in responses are `{id, full_name}` (bdm-010's `PersonRef`): the logger is `bdm: {id, full_name}`.
- Owner / assignee 403s on a write ("not the assigned BDM", "not the logger") log a `bdm_activity_write_refused` warning (actor, ids, route, status) — never text fields. Wrong-role 403s from the shared `bdm_context` / `caller_scope` are not logged as refusals (bdm-002's `bdm_org_write_refused` precedent).
- Spec §12 (Revision 2) lists every API / UI / security finding; the tasks below already include the applied ones.
- Note: optional, trimmed, ≤ 500 characters, `\n \r \t` allowed, other control characters refused (reuse `TripNote`).
- Errors are `{"detail": ...}`: a string for 403 / 404 / 409 and service 422s; FastAPI's list for schema 422s.
  Out-of-scope ids → 404 "Activity not found" / "Organization not found".
- Only the organization's assigned BDM logs; only the logger edits / deletes; `bdm_manager` reads the team; `super_admin` reads all;
  manager / super_admin writes → 403; any other role → 403.
- Lock order: organization, then activity. Services never commit; the route commits once; the audit row is in that transaction.
- Audit: `bdm_activity.created|updated|deleted`, `entity_type="bdm_activity"`, metadata = `organization_id`, `channel`, changed field
  names. Never the note or contact name — in audit rows or logs.
- Lists are `{items, total, limit, offset}` newest first (`occurred_at desc, id desc`); `LIMIT`/`OFFSET` from `app/api/bdm.py`.
- Tests: only the lite set. Never run the full backend suite (the owner runs it).

## Review Focus

1. **A PATCH that changes a call to a visit but leaves the stored direction** → 422 "Direction applies only to calls, WhatsApp and
   email" (the UI sends `direction: null`; the API never guesses). Task 4 test `test_patch_channel_change_needs_direction_cleared`.
2. **A viewer outside India logs at 20:00 UTC** (01:30 IST the next day) → it counts on the IST day, not the UTC day. Task 3 test
   `test_day_counts_use_ist_days_not_utc_days`.
3. **The organization is reassigned while the Log form is open** → the save shows "Only the organization's assigned BDM can log
   activity" and keeps the entry. Task 6 test `shows a refusal and keeps the entry`.
4. **A whitespace-only note** → stored as no note (NULL), not as spaces. Task 2 test `test_blank_note_becomes_null`.
5. **Deleting an item from a timeline after "Load more"** → the item leaves, the total drops by one and "Load more" still asks
   for the right offset. Task 7 test `delete drops the total and keeps the next offset`.
6. **A laptop clock a minute fast** → "now" saves (as the server's now) instead of 422 (V9). Task 4 test
   `test_a_time_slightly_ahead_is_saved_as_now`.
7. **An unchanged contact sent with another change** → the stored contact name is not rewritten (§12.1 A2). Task 4 test
   `test_resending_the_same_contact_keeps_the_snapshot`.

## How to run tests (worktree)

The user starts and stops Docker. Run from the worktree root in Git Bash. `<P>` = space-separated test paths.

Backend:

```bash
docker compose -p bdm009 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/bdm-009/apps/api:/app" \
  api-test sh -c "alembic upgrade head && python -m pytest -q <P>"
```

Web (vitest / tsc / eslint; the worktree has no node_modules):

```bash
MSYS_NO_PATHCONV=1 docker compose -p bdm009 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps \
  -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/bdm-009/apps/web:/app" \
  -v /app/node_modules web-test sh -c "npx vitest run <paths>"
```

If the test DB carries a stale alembic stamp from another branch: `alembic stamp --purge 0068_bdm_trips` then `alembic upgrade head`
(inside the same `api-test` command).

LITE = `tests/test_bdm_009_*.py tests/test_bdm_010_*.py tests/test_bdm_002_*.py tests/test_bdm_001_*.py tests/test_enh_027_schemas.py`
(check the last file name with `ls apps/api/tests | grep enh_027`; use what exists).

---

### Task 1: Migration 0069, model, head-pin relaxation

**Files:**
- Create: `apps/api/alembic/versions/0069_bdm_activities.py`
- Modify: `apps/api/app/models.py` (append after `BdmOrganizationContact`, before `class LiveSession`, ~line 1085)
- Modify: `apps/api/tests/test_bdm_010_migration.py:36-38` (single-head assertion)
- Test: `apps/api/tests/test_bdm_009_migration.py`

**Interfaces:**
- Produces: `app.models.BdmActivity`; `app.models.BDM_ACTIVITY_CHANNELS: tuple[str, ...]`;
  `app.models.BDM_ACTIVITY_DIRECTIONAL: tuple[str, ...]` (`("call", "whatsapp", "email")`).

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_bdm_009_migration.py`:

```python
"""bdm-009 -- migration 0069_bdm_activities (spec §4; AC10). Round trip and the downgrade refusal run in a throwaway database
(the bdm-001 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_bdm_009_migration_0069", VERSIONS / "0069_bdm_activities.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0068_bdm_trips", "0069_bdm_activities"
USERS = "SELECT id, email, role FROM users ORDER BY id"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0068_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert ScriptDirectory.from_config(_config()).get_heads() == [HEAD]


def test_model_matches_the_migration():
    from app.models import BdmActivity

    table = BdmActivity.__table__
    assert {c.name for c in table.columns} == {
        "id", "bdm_user_id", "organization_id", "contact_id", "contact_name", "channel", "direction", "occurred_at", "note",
        "created_at", "updated_at",
    }
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {
        "ck_bdm_activities_channel", "ck_bdm_activities_direction", "ck_bdm_activities_direction_channel",
        "ix_bdm_activities_bdm_user_id_occurred_at", "ix_bdm_activities_organization_id_occurred_at",
    } <= names
    fks = {fk.parent.name: fk.ondelete for fk in table.foreign_keys}
    assert fks == {"bdm_user_id": "RESTRICT", "organization_id": "RESTRICT", "contact_id": "SET NULL"}


@pytest.mark.asyncio
async def test_table_exists_in_the_shared_database(db_session):
    rows = (await db_session.execute(sa.text("SELECT relname FROM pg_class WHERE relname = 'bdm_activities'"))).all()
    assert rows == [("bdm_activities",)]


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
    """A fresh database at 0068 with one BDM user and one organization."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm009_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        owner, org = uuid.uuid4(), uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'Owner', 'bdm', 'it', true, true, 'en-GB', '{}')",
            {"id": owner, "email": f"owner-{name}@example.local"},
        )
        _sql(
            url,
            "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, "
            "created_by_user_id) VALUES (:id, :code, 'college', 'college', 'St Mary', 'st mary', 'Kochi', 'kochi', :owner, :owner)",
            {"id": org, "code": f"ORG-{uuid.uuid4().hex[:6]}", "owner": owner},
        )
        yield {"cfg": cfg, "url": url, "owner": owner, "org": org}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


ACTIVITY = (
    "INSERT INTO bdm_activities (id, bdm_user_id, organization_id, channel, direction, occurred_at) "
    "VALUES (:id, :owner, :org, :channel, :direction, now())"
)


def _activity(db, **over) -> dict:
    params = {"id": uuid.uuid4(), "owner": db["owner"], "org": db["org"], "channel": "call", "direction": "outbound"}
    params.update(over)
    return params


def test_round_trip_keeps_users(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, USERS)
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT count(*) FROM pg_class WHERE relname = 'bdm_activities'")[0][0] == 0
    command.upgrade(cfg, HEAD)
    assert _sql(url, USERS) == before


def test_checks_hold_and_downgrade_refuses_while_activities_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    for over, constraint in (
        ({"channel": "fax"}, "ck_bdm_activities_channel"),
        ({"direction": "sideways"}, "ck_bdm_activities_direction"),
        ({"channel": "call", "direction": None}, "ck_bdm_activities_direction_channel"),
        ({"channel": "visit", "direction": "outbound"}, "ck_bdm_activities_direction_channel"),
    ):
        with pytest.raises(Exception, match=constraint):
            _sql(url, ACTIVITY, _activity(isolated_db, **over))
    _sql(url, ACTIVITY, _activity(isolated_db, channel="visit", direction=None))
    with pytest.raises(Exception, match="activities exist"):
        command.downgrade(cfg, BASE)
```

- [ ] **Step 2: Run it to verify it fails**

Run (backend command) with `<P>` = `tests/test_bdm_009_migration.py`.
Expected: FAIL / collection error — `0069_bdm_activities.py` does not exist.

- [ ] **Step 3: Write the migration** — `apps/api/alembic/versions/0069_bdm_activities.py`:

```python
"""bdm-009 -- bdm_activities.

Revision ID: 0069_bdm_activities
Revises: 0068_bdm_trips

docs/superpowers/specs/2026-10-03-bdm-009-activity-log-design.md §4 (DEC-SCOPE-065). Additive: one table; no existing row is read or
written. 0001 builds a fresh database from the current models, which already carry it, so creation is guarded (0061's idiom).
downgrade() refuses while activities exist: they are the only record of each call, message and visit.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0069_bdm_activities"
down_revision = "0068_bdm_trips"
branch_labels = None
depends_on = None

TABLE = "bdm_activities"
CHANNELS = "'call', 'whatsapp', 'email', 'visit', 'meeting', 'other'"
DIRECTIONAL = "'call', 'whatsapp', 'email'"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("bdm_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("organization_id", uuid, sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contact_id", uuid, sa.ForeignKey("bdm_organization_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_name", sa.String(200), nullable=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(10), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"channel IN ({CHANNELS})", name="ck_bdm_activities_channel"),
        sa.CheckConstraint("direction IS NULL OR direction IN ('outbound', 'inbound')", name="ck_bdm_activities_direction"),
        sa.CheckConstraint(f"(channel IN ({DIRECTIONAL})) = (direction IS NOT NULL)", name="ck_bdm_activities_direction_channel"),
    )
    op.create_index("ix_bdm_activities_bdm_user_id_occurred_at", TABLE, ["bdm_user_id", "occurred_at"])
    op.create_index("ix_bdm_activities_organization_id_occurred_at", TABLE, ["organization_id", "occurred_at"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0069_bdm_activities: BDM activities exist. Remove them deliberately first.")
    op.drop_table(TABLE)
```

- [ ] **Step 4: Add the model** — in `apps/api/app/models.py`, directly after `class BdmOrganizationContact` (before `class LiveSession`):

```python
BDM_ACTIVITY_CHANNELS = ("call", "whatsapp", "email", "visit", "meeting", "other")
BDM_ACTIVITY_DIRECTIONAL = ("call", "whatsapp", "email")  # V6: these need a direction; the rest must have none


class BdmActivity(Base, TimestampMixin):
    """bdm-009 (DEC-SCOPE-065): one call, WhatsApp, email, visit, meeting or other contact a BDM logged by hand (D9; nothing is sent).
    `contact_name` is the contact's name at save, kept when bdm-002 hard-deletes the contact (`contact_id` -> NULL)."""

    __tablename__ = "bdm_activities"
    __table_args__ = (
        CheckConstraint(_in_list("channel", BDM_ACTIVITY_CHANNELS), name="ck_bdm_activities_channel"),
        CheckConstraint("direction IS NULL OR direction IN ('outbound', 'inbound')", name="ck_bdm_activities_direction"),
        CheckConstraint(f"({_in_list('channel', BDM_ACTIVITY_DIRECTIONAL)}) = (direction IS NOT NULL)", name="ck_bdm_activities_direction_channel"),
        Index("ix_bdm_activities_bdm_user_id_occurred_at", "bdm_user_id", "occurred_at"),
        Index("ix_bdm_activities_organization_id_occurred_at", "organization_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    bdm_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organizations.id", ondelete="RESTRICT"))
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organization_contacts.id", ondelete="SET NULL"), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    channel: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 5: Relax bdm-010's head pin** — `apps/api/tests/test_bdm_010_migration.py`, replace the test at lines 36-38:

```python
def test_migration_chains_after_0067_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1  # later revisions (bdm-009) chain after this one
```

- [ ] **Step 6: Run the tests to verify they pass**

`<P>` = `tests/test_bdm_009_migration.py tests/test_bdm_010_migration.py`. Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/alembic/versions/0069_bdm_activities.py apps/api/app/models.py apps/api/tests/test_bdm_009_migration.py apps/api/tests/test_bdm_010_migration.py
git commit -m "feat(bdm-009): bdm_activities table, model and migration 0069"
```

---

### Task 2: Schemas

**Files:**
- Modify: `apps/api/app/schemas.py` (append at the end of the file, after `BdmOrganizationEnvelope`)
- Test: `apps/api/tests/test_bdm_009_schemas.py`

**Interfaces:**
- Consumes: `app.models.BDM_ACTIVITY_DIRECTIONAL`; `TripNote` (already in `schemas.py`).
- Produces: `BdmActivityChannel`, `BdmActivityDirection`, `BdmActivityCreate`, `BdmActivityUpdate`, `BdmActivityOut`,
  `BdmActivityPage`, `BdmActivityDayCounts`, `BdmActivityDayPage`, constants `ACTIVITY_DIRECTION_REQUIRED`,
  `ACTIVITY_DIRECTION_REFUSED`.

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_bdm_009_schemas.py`:

```python
"""bdm-009 -- request schemas (spec §5.1; AC1, AC2, V6)."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas import (
    ACTIVITY_DIRECTION_REFUSED,
    ACTIVITY_DIRECTION_REQUIRED,
    BdmActivityCreate,
    BdmActivityUpdate,
)

WHEN = datetime(2026, 10, 3, 5, 0, tzinfo=UTC)


def body(**over) -> dict:
    data = {"organization_id": str(uuid.uuid4()), "channel": "call", "direction": "outbound", "occurred_at": WHEN.isoformat()}
    data.update(over)
    return data


@pytest.mark.parametrize("channel", ["call", "whatsapp", "email"])
def test_directional_channels_need_a_direction(channel):
    assert BdmActivityCreate(**body(channel=channel)).direction == "outbound"
    with pytest.raises(ValidationError) as exc:
        BdmActivityCreate(**body(channel=channel, direction=None))
    assert ACTIVITY_DIRECTION_REQUIRED in str(exc.value)
    with pytest.raises(ValidationError):
        BdmActivityCreate(**{k: v for k, v in body(channel=channel).items() if k != "direction"})


@pytest.mark.parametrize("channel", ["visit", "meeting", "other"])
def test_other_channels_refuse_a_direction(channel):
    assert BdmActivityCreate(**body(channel=channel, direction=None)).direction is None
    with pytest.raises(ValidationError) as exc:
        BdmActivityCreate(**body(channel=channel, direction="inbound"))
    assert ACTIVITY_DIRECTION_REFUSED in str(exc.value)


def test_direction_error_sits_on_the_direction_field():
    with pytest.raises(ValidationError) as exc:
        BdmActivityCreate(**body(direction=None))
    assert exc.value.errors()[0]["loc"] == ("direction",)


def test_unknown_channel_and_naive_time_are_refused():
    with pytest.raises(ValidationError):
        BdmActivityCreate(**body(channel="fax"))
    with pytest.raises(ValidationError):
        BdmActivityCreate(**body(occurred_at="2026-10-03T10:00:00"))


def test_note_is_trimmed_capped_and_multiline():
    assert BdmActivityCreate(**body(note="  line one\nline two  ")).note == "line one\nline two"
    with pytest.raises(ValidationError):
        BdmActivityCreate(**body(note="x" * 501))
    with pytest.raises(ValidationError):
        BdmActivityCreate(**body(note="bad\x07bell"))


def test_blank_note_becomes_null():
    assert BdmActivityCreate(**body(note="   ")).note is None


@pytest.mark.parametrize("field", ["bdm_user_id", "contact_name", "id"])
def test_server_owned_fields_are_refused(field):
    with pytest.raises(ValidationError, match="extra"):
        BdmActivityCreate(**body(**{field: "x"}))


def test_update_has_no_organization_and_refuses_clearing_required_fields():
    with pytest.raises(ValidationError, match="extra"):
        BdmActivityUpdate(organization_id=str(uuid.uuid4()))
    with pytest.raises(ValidationError, match="Channel can't be empty"):
        BdmActivityUpdate(channel=None)
    with pytest.raises(ValidationError, match="When can't be empty"):
        BdmActivityUpdate(occurred_at=None)
    patch = BdmActivityUpdate(direction=None, contact_id=None, note=None)
    assert patch.model_fields_set == {"direction", "contact_id", "note"}
```

- [ ] **Step 2: Run it to verify it fails**

`<P>` = `tests/test_bdm_009_schemas.py`. Expected: FAIL with `ImportError: cannot import name 'ACTIVITY_DIRECTION_REFUSED'`.

- [ ] **Step 3: Append the schemas** — at the end of `apps/api/app/schemas.py`. Also add `BDM_ACTIVITY_DIRECTIONAL` to the
  existing `from app.models import GENDERS` line (`from app.models import BDM_ACTIVITY_DIRECTIONAL, GENDERS`):

```python
# --- bdm-009: activity log (DEC-SCOPE-065; docs/superpowers/specs/2026-10-03-bdm-009-activity-log-design.md §5.1) ---

BdmActivityChannel = Literal["call", "whatsapp", "email", "visit", "meeting", "other"]
BdmActivityDirection = Literal["outbound", "inbound"]
ACTIVITY_DIRECTION_REQUIRED = "Choose outgoing or incoming for a call, WhatsApp or email"
ACTIVITY_DIRECTION_REFUSED = "Direction applies only to calls, WhatsApp and email"


def activity_direction_error(channel: str | None, direction: str | None) -> str | None:
    """V6, shared by the create schema and the service's PATCH check (which sees the merged row)."""
    if channel is None:
        return None  # the channel failed its own validation; one error is enough
    if channel in BDM_ACTIVITY_DIRECTIONAL and direction is None:
        return ACTIVITY_DIRECTION_REQUIRED
    if channel not in BDM_ACTIVITY_DIRECTIONAL and direction is not None:
        return ACTIVITY_DIRECTION_REFUSED
    return None


class BdmActivityCreate(BaseModel):
    """V1-V6. Owner, contact name and timestamps are server-owned (`extra="forbid"` → 422). Time rules need "now", so the service
    checks them (spec §4.2)."""

    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    channel: BdmActivityChannel
    direction: BdmActivityDirection | None = Field(default=None, validate_default=True)
    contact_id: UUID | None = None
    occurred_at: AwareDatetime
    note: TripNote = None

    @field_validator("direction")
    @classmethod
    def _direction_fits_channel(cls, value: str | None, info: ValidationInfo) -> str | None:
        error = activity_direction_error(info.data.get("channel"), value)
        if error:
            raise ValueError(error)
        return value


class BdmActivityUpdate(BaseModel):
    """Only the fields sent change (`model_fields_set`). The organization is fixed after create. `null` clears direction, contact and
    note; channel and When can't be cleared."""

    model_config = ConfigDict(extra="forbid")
    channel: BdmActivityChannel | None = None
    direction: BdmActivityDirection | None = None
    contact_id: UUID | None = None
    occurred_at: AwareDatetime | None = None
    note: TripNote = None

    @model_validator(mode="after")
    def _required_stay_set(self) -> "BdmActivityUpdate":
        for field, label in (("channel", "Channel"), ("occurred_at", "When")):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{label} can't be empty")
        return self


class BdmActivityOrganization(BaseModel):
    id: UUID
    code: str
    name: str
    org_type: str


class BdmActivityLogger(BaseModel):
    """bdm-010's `PersonRef` shape (§12.1 A1)."""

    id: UUID
    full_name: str


class BdmActivityPermissions(BaseModel):
    can_change: bool


class BdmActivityOut(BaseModel):
    id: UUID
    organization: BdmActivityOrganization
    bdm: BdmActivityLogger
    contact_id: UUID | None
    contact_name: str | None
    contact_removed: bool
    channel: BdmActivityChannel
    direction: BdmActivityDirection | None
    occurred_at: datetime
    note: str | None
    created_at: datetime
    updated_at: datetime
    permissions: BdmActivityPermissions


class BdmActivityPage(BaseModel):
    items: list[BdmActivityOut]
    total: int
    limit: int
    offset: int


class BdmActivityChannelCounts(BaseModel):
    call: int
    whatsapp: int
    email: int
    visit: int
    meeting: int
    other: int


class BdmActivityDayCounts(BaseModel):
    day: date
    by_channel: BdmActivityChannelCounts
    calls_made: int
    organizations_contacted: int


class BdmActivityDayPage(BdmActivityPage):
    counts: BdmActivityDayCounts
```

- [ ] **Step 4: Run the tests to verify they pass**

`<P>` = `tests/test_bdm_009_schemas.py`. Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas.py apps/api/tests/test_bdm_009_schemas.py
git commit -m "feat(bdm-009): activity request and response schemas"
```

---

### Task 3: Service — time rules, rows, day counts, audit

**Files:**
- Create: `apps/api/app/services/bdm_activities.py`
- Create: `apps/api/tests/bdm009_helpers.py`
- Test: `apps/api/tests/test_bdm_009_service.py`

**Interfaces:**
- Consumes: `BdmActivity`, `BDM_ACTIVITY_CHANNELS`, `BDM_ACTIVITY_DIRECTIONAL` (Task 1); `activity_direction_error` (Task 2);
  `services.bdm_organizations.caller_scope`; `services.bdm_travel.INDIA`.
- Produces (all in `app.services.bdm_activities`):
  - constants `NOT_FOUND, OWNER_ONLY, NOT_ASSIGNED, ARCHIVED, CONTACT_INVALID, FUTURE, TOO_OLD, NOT_TODAY, MOVE_TODAY, FUTURE_DAY,
    CAP_REACHED, BACKDATE_DAYS, CLOCK_TOLERANCE, DAILY_CAP`
  - `async db_now(db) -> datetime`
  - `india_date(moment: datetime) -> date`
  - `day_range(day: date) -> tuple[datetime, datetime]`
  - `day_filters(day: date) -> list`
  - `check_time(occurred_at: datetime, now: datetime) -> datetime` (422; returns the instant to store, clamped to `now`)
  - `async check_daily_cap(db, bdm_user_id: UUID, day: date) -> None` (409)
  - `refused(user: User, route: str, status: int, detail: str, **ids) -> HTTPException` (logs, returns the exception)
  - `editable(activity: BdmActivity, now: datetime) -> bool`
  - `check_direction(channel: str, direction: str | None) -> None` (422)
  - `async contact_for(db, org_id: UUID, contact_id: UUID) -> BdmOrganizationContact` (422)
  - `optional_filters(channel: str | None, organization_id: UUID | None) -> list`
  - `async page(db, filters: list, limit: int, offset: int, user: User, now: datetime) -> dict`
  - `async one(db, user: User, activity_id: UUID, now: datetime) -> dict`
  - `async day_counts(db, filters: list, day: date) -> dict`
  - `async load_readable(db, user: User, activity_id: UUID, *, lock: bool = False) -> BdmActivity` (404)
  - `audit(db, user: User, action: str, activity: BdmActivity, fields: list[str] | None = None) -> None`
  - `log(event: str, user: User, activity_id, **extra) -> None`
- Produces (in `tests/bdm009_helpers.py`): `ACTIVITIES`, `TEAM_ACTIVITIES`, `org_activities(org_id)`, `async bdm_with_org(client, db,
  bdm_type="college") -> tuple[User, User, dict]`, `async add_activity(db, bdm_id, org_id, occurred_at, channel="call",
  direction="outbound", contact_id=None, contact_name=None) -> BdmActivity`, `activity_body(org_id, **over) -> dict`.

- [ ] **Step 1: Write the helpers** — `apps/api/tests/bdm009_helpers.py`:

```python
"""bdm-009 test builders. Unique values per call: the test database is shared and never truncated."""

from datetime import UTC, datetime, timedelta

from app.models import BdmActivity, User
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm

ACTIVITIES = "/api/v1/bdm/activities"
TEAM_ACTIVITIES = "/api/v1/bdm/manager/activities"


def org_activities(org_id) -> str:
    return f"/api/v1/bdm/organizations/{org_id}/activities"


async def bdm_with_org(client, db, bdm_type: str = "college", **org_over) -> tuple[User, User, dict]:
    """A manager, one BDM reporting to them, and an organization assigned to that BDM. Leaves the client signed in as the BDM."""
    manager = await make_manager(db)
    bdm = await make_bdm(db, manager, bdm_type)
    client.cookies.clear()
    await login(client, bdm)
    org = await create_org(client, org_type=bdm_type, **org_over)  # college / school / agent are all organization types
    return manager, bdm, org


def activity_body(org_id, **over) -> dict:
    body = {"organization_id": str(org_id), "channel": "call", "direction": "outbound",
            "occurred_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}
    body.update(over)
    return body


async def add_activity(db, bdm_id, org_id, occurred_at: datetime, channel: str = "call", direction: str | None = "outbound",
                       contact_id=None, contact_name: str | None = None) -> BdmActivity:
    """A row written straight to the table (past days, boundary instants) -- the API's time window doesn't apply."""
    activity = BdmActivity(bdm_user_id=bdm_id, organization_id=org_id, channel=channel, direction=direction, occurred_at=occurred_at,
                           contact_id=contact_id, contact_name=contact_name)
    db.add(activity)
    await db.commit()
    return activity
```

- [ ] **Step 2: Write the failing test** — `apps/api/tests/test_bdm_009_service.py`:

```python
"""bdm-009 -- service rules (spec §4.2, §5.2; AC2, AC3, AC4)."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.models import BdmActivity
from app.services import bdm_activities as svc
from app.services.bdm_travel import INDIA
from tests.bdm009_helpers import add_activity, bdm_with_org

NOW = datetime(2026, 10, 3, 6, 0, tzinfo=UTC)  # 11:30 IST on 3 Oct


def test_day_range_is_the_ist_calendar_day():
    start, end = svc.day_range(date(2026, 10, 3))
    assert start == datetime(2026, 10, 2, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 10, 3, 18, 30, tzinfo=UTC)


def test_check_time_clamps_small_skew_refuses_future_and_more_than_seven_ist_days_back():
    assert svc.check_time(NOW, NOW) == NOW
    assert svc.check_time(NOW + timedelta(minutes=5), NOW) == NOW  # V9: within tolerance -> saved as now
    with pytest.raises(HTTPException) as exc:
        svc.check_time(NOW + timedelta(minutes=5, seconds=1), NOW)
    assert (exc.value.status_code, exc.value.detail) == (422, svc.FUTURE)
    seven_back = datetime(2026, 9, 26, 0, 0, tzinfo=INDIA)  # first instant of IST today - 7
    assert svc.check_time(seven_back, NOW) == seven_back
    with pytest.raises(HTTPException) as exc:
        svc.check_time(seven_back - timedelta(seconds=1), NOW)
    assert (exc.value.status_code, exc.value.detail) == (422, svc.TOO_OLD)


def test_editable_is_true_only_on_the_activitys_ist_day():
    today = BdmActivity(occurred_at=datetime(2026, 10, 2, 18, 30, tzinfo=UTC))  # 00:00 IST on 3 Oct
    yesterday = BdmActivity(occurred_at=datetime(2026, 10, 2, 18, 29, 59, tzinfo=UTC))
    assert svc.editable(today, NOW) is True
    assert svc.editable(yesterday, NOW) is False


def test_check_direction_uses_the_shared_rule():
    svc.check_direction("call", "inbound")
    svc.check_direction("visit", None)
    for channel, direction in (("call", None), ("visit", "outbound")):
        with pytest.raises(HTTPException) as exc:
            svc.check_direction(channel, direction)
        assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_day_counts_are_exact_per_channel_and_ignore_other_bdms_and_days(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    _, other_bdm, other_org = await bdm_with_org(client, db_session)
    org_id, other_id = uuid.UUID(org["id"]), uuid.UUID(other_org["id"])
    day = date(2026, 9, 20)
    start, end = svc.day_range(day)
    for channel, direction, moment in (
        ("call", "outbound", start),                         # first instant of the day
        ("call", "outbound", start + timedelta(hours=3)),
        ("call", "inbound", start + timedelta(hours=4)),
        ("whatsapp", "outbound", start + timedelta(hours=5)),
        ("visit", None, end - timedelta(seconds=1)),          # last second of the day
    ):
        await add_activity(db_session, bdm.id, org_id, moment, channel, direction)
    await add_activity(db_session, bdm.id, other_id, start + timedelta(hours=6), "email", "outbound")
    await add_activity(db_session, bdm.id, org_id, end, "meeting", None)                    # the next IST day
    await add_activity(db_session, bdm.id, org_id, start - timedelta(seconds=1), "call", "outbound")  # the day before
    await add_activity(db_session, other_bdm.id, other_id, start + timedelta(hours=1), "call", "outbound")  # someone else
    counts = await svc.day_counts(db_session, [BdmActivity.bdm_user_id == bdm.id], day)
    assert counts == {
        "day": day,
        "by_channel": {"call": 3, "whatsapp": 1, "email": 1, "visit": 1, "meeting": 0, "other": 0},
        "calls_made": 2,
        "organizations_contacted": 2,
    }


@pytest.mark.asyncio
async def test_day_counts_use_ist_days_not_utc_days(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    late_utc = datetime(2026, 9, 21, 20, 0, tzinfo=UTC)  # 01:30 IST on 22 Sep
    await add_activity(db_session, bdm.id, uuid.UUID(org["id"]), late_utc, "email", "outbound")
    mine = [BdmActivity.bdm_user_id == bdm.id]
    assert (await svc.day_counts(db_session, mine, date(2026, 9, 22)))["by_channel"]["email"] == 1
    assert (await svc.day_counts(db_session, mine, date(2026, 9, 21)))["by_channel"]["email"] == 0


@pytest.mark.asyncio
async def test_page_is_newest_first_with_logger_and_contact_flags(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    org_id = uuid.UUID(org["id"])
    older = await add_activity(db_session, bdm.id, org_id, datetime(2026, 9, 20, 5, tzinfo=UTC), contact_name="Dr Rao")
    newer = await add_activity(db_session, bdm.id, org_id, datetime(2026, 9, 20, 6, tzinfo=UTC), "visit", None)
    result = await svc.page(db_session, [BdmActivity.organization_id == org_id], 50, 0, bdm, NOW)
    assert [i["id"] for i in result["items"]] == [newer.id, older.id]
    assert result["total"] == 2
    first, second = result["items"]
    assert first["bdm"] == {"id": bdm.id, "full_name": bdm.full_name}
    assert first["organization"]["code"] == org["code"]
    assert second["contact_removed"] is True  # a name with no contact row: bdm-002 deleted the contact
    assert first["contact_removed"] is False
    assert first["permissions"] == {"can_change": False}  # not today


@pytest.mark.asyncio
async def test_daily_cap_counts_only_that_bdms_ist_day(client, db_session, monkeypatch):
    _, bdm, org = await bdm_with_org(client, db_session)
    monkeypatch.setattr(svc, "DAILY_CAP", 2)  # the rule, not the number, is under test
    day = date(2026, 9, 18)
    start, _ = svc.day_range(day)
    await svc.check_daily_cap(db_session, bdm.id, day)
    for minutes in (1, 2):
        await add_activity(db_session, bdm.id, uuid.UUID(org["id"]), start + timedelta(minutes=minutes))
    with pytest.raises(HTTPException) as exc:
        await svc.check_daily_cap(db_session, bdm.id, day)
    assert exc.value.status_code == 409
    await svc.check_daily_cap(db_session, bdm.id, day + timedelta(days=1))  # another day is free
```

`check_daily_cap` reads `DAILY_CAP` at call time (module global), so the monkeypatch works; the message constant `CAP_REACHED`
keeps the real number.

- [ ] **Step 3: Run it to verify it fails**

`<P>` = `tests/test_bdm_009_service.py`. Expected: FAIL with `ImportError: cannot import name 'bdm_activities'`.

- [ ] **Step 4: Write the service** — `apps/api/app/services/bdm_activities.py`:

```python
"""bdm-009 (DEC-SCOPE-065, spec §4.2, §5.2): activity time rules, scope, rows, day counts and audit.

Functions only; nothing here commits -- the route owns the transaction. Every `{activity_id}` resolves through `load_readable`, so an
activity on an organization the caller can't read is the same 404 as a missing one. Logs and audit rows carry ids, channel and field
names -- never the note or the contact's name."""

import logging
from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import BDM_ACTIVITY_CHANNELS, AuditLog, BdmActivity, BdmOrganization, BdmOrganizationContact, BdmProfile, User
from app.schemas import activity_direction_error
from app.services.bdm_organizations import caller_scope
from app.services.bdm_travel import INDIA

logger = logging.getLogger("app.bdm")

BACKDATE_DAYS = 7  # V4
CLOCK_TOLERANCE = timedelta(minutes=5)  # V9: a browser clock slightly ahead of the server
DAILY_CAP = 200  # V10: an abuse bound, far above real use
NOT_FOUND = "Activity not found"
CAP_REACHED = f"You've logged {DAILY_CAP} activities for this day"
OWNER_ONLY = "Only the BDM who logged this activity can change it"
NOT_ASSIGNED = "Only the organization's assigned BDM can log activity"
ARCHIVED = "This organization is archived"
CONTACT_INVALID = "Choose a contact of this organization"
FUTURE = "When can't be in the future"
TOO_OLD = f"Activities can be logged up to {BACKDATE_DAYS} days back"
NOT_TODAY = "Only today's activities can be changed"
MOVE_TODAY = "An activity can only be moved within today"
FUTURE_DAY = "That date hasn't happened yet"
NEWEST = (BdmActivity.occurred_at.desc(), BdmActivity.id.desc())
Logger = aliased(User)


async def db_now(db: AsyncSession) -> datetime:
    """The database clock, read once per request: every time rule compares against the same instant."""
    return await db.scalar(select(func.now()))


def india_date(moment: datetime) -> date:
    return moment.astimezone(INDIA).date()


def day_range(day: date) -> tuple[datetime, datetime]:
    """An IST calendar day as a half-open instant range (index-friendly; no cast on the column)."""
    start = datetime.combine(day, time.min, tzinfo=INDIA)
    return start, start + timedelta(days=1)


def day_filters(day: date) -> list:
    start, end = day_range(day)
    return [BdmActivity.occurred_at >= start, BdmActivity.occurred_at < end]


def check_time(occurred_at: datetime, now: datetime) -> datetime:
    """V4 + V9. Returns the instant to store: up to CLOCK_TOLERANCE ahead is saved as `now`, so no future row is ever stored."""
    if occurred_at > now + CLOCK_TOLERANCE:
        raise HTTPException(422, FUTURE)
    if india_date(occurred_at) < india_date(now) - timedelta(days=BACKDATE_DAYS):
        raise HTTPException(422, TOO_OLD)
    return min(occurred_at, now)


async def check_daily_cap(db: AsyncSession, bdm_user_id: UUID, day: date) -> None:
    """V10, create only. A soft bound: two concurrent saves on different organizations may pass it by one or two."""
    count = await db.scalar(select(func.count()).select_from(BdmActivity).where(BdmActivity.bdm_user_id == bdm_user_id, *day_filters(day)))
    if (count or 0) >= DAILY_CAP:
        raise HTTPException(409, CAP_REACHED)


def refused(user: User, route: str, status: int, detail: str, **ids) -> HTTPException:
    """§12.3 S10: every refused write is visible in the logs (ids, route, status -- never text fields), as bdm-002's
    `bdm_org_write_refused`. Returns the exception for the caller to raise."""
    logger.warning("bdm_activity_write_refused", extra={"extra_fields": {
        "actor_id": str(user.id), "route": route, "status": status, **{k: str(v) for k, v in ids.items()}}})
    return HTTPException(status, detail)


def editable(activity: BdmActivity, now: datetime) -> bool:
    """AC4: the single gate for PATCH and DELETE. bdm-015 adds "and that day's report is not submitted" here."""
    return india_date(activity.occurred_at) == india_date(now)


def check_direction(channel: str, direction: str | None) -> None:
    error = activity_direction_error(channel, direction)
    if error:
        raise HTTPException(422, error)


async def contact_for(db: AsyncSession, org_id: UUID, contact_id: UUID) -> BdmOrganizationContact:
    contact = await db.scalar(select(BdmOrganizationContact).where(
        BdmOrganizationContact.id == contact_id, BdmOrganizationContact.organization_id == org_id))
    if contact is None:
        raise HTTPException(422, CONTACT_INVALID)
    return contact


def optional_filters(channel: str | None, organization_id: UUID | None) -> list:
    filters = []
    if channel:
        filters.append(BdmActivity.channel == channel)
    if organization_id:
        filters.append(BdmActivity.organization_id == organization_id)
    return filters


def _rows(filters: list):
    """One query for a list: activity + organization + logger name. Joined to the logger's profile so team scope (`team_filter`) can be
    expressed on it."""
    return (
        select(BdmActivity, BdmOrganization, Logger.full_name)
        .join(BdmOrganization, BdmOrganization.id == BdmActivity.organization_id)
        .join(Logger, Logger.id == BdmActivity.bdm_user_id)
        .join(BdmProfile, BdmProfile.user_id == BdmActivity.bdm_user_id)
        .where(*filters)
    )


def _out(activity: BdmActivity, org: BdmOrganization, logger_name: str, user: User, now: datetime) -> dict:
    return {
        "id": activity.id,
        "organization": {"id": org.id, "code": org.code, "name": org.name, "org_type": org.org_type},
        "bdm": {"id": activity.bdm_user_id, "full_name": logger_name},
        "contact_id": activity.contact_id,
        "contact_name": activity.contact_name,
        "contact_removed": activity.contact_name is not None and activity.contact_id is None,
        "channel": activity.channel,
        "direction": activity.direction,
        "occurred_at": activity.occurred_at,
        "note": activity.note,
        "created_at": activity.created_at,
        "updated_at": activity.updated_at,
        "permissions": {"can_change": user.id == activity.bdm_user_id and editable(activity, now)},
    }


async def page(db: AsyncSession, filters: list, limit: int, offset: int, user: User, now: datetime) -> dict:
    stmt = _rows(filters)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    result = (await db.execute(stmt.order_by(*NEWEST).limit(limit).offset(offset).execution_options(populate_existing=True))).all()
    return {"items": [_out(a, o, n, user, now) for a, o, n in result], "total": total or 0, "limit": limit, "offset": offset}


async def one(db: AsyncSession, user: User, activity_id: UUID, now: datetime) -> dict:
    row = (await db.execute(_rows([BdmActivity.id == activity_id]).execution_options(populate_existing=True))).one()
    return _out(row[0], row[1], row[2], user, now)


async def day_counts(db: AsyncSession, filters: list, day: date) -> dict:
    """AC3, reused by bdm-015: one query over the same filters as the list, for the whole IST day (not the page)."""
    per_channel = [func.count().filter(BdmActivity.channel == channel) for channel in BDM_ACTIVITY_CHANNELS]
    calls_made = func.count().filter(and_(BdmActivity.channel == "call", BdmActivity.direction == "outbound"))
    stmt = (
        select(*per_channel, calls_made, func.count(distinct(BdmActivity.organization_id)))
        .select_from(BdmActivity)
        .join(BdmProfile, BdmProfile.user_id == BdmActivity.bdm_user_id)
        .where(*filters, *day_filters(day))
    )
    row = (await db.execute(stmt)).one()
    n = len(BDM_ACTIVITY_CHANNELS)
    return {"day": day, "by_channel": dict(zip(BDM_ACTIVITY_CHANNELS, row[:n], strict=True)), "calls_made": row[n],
            "organizations_contacted": row[n + 1]}


async def load_readable(db: AsyncSession, user: User, activity_id: UUID, *, lock: bool = False) -> BdmActivity:
    """V5: readable = its organization is readable (`caller_scope`; any other role is 403 there)."""
    stmt = (select(BdmActivity).join(BdmOrganization, BdmOrganization.id == BdmActivity.organization_id)
            .where(BdmActivity.id == activity_id, *await caller_scope(db, user)))
    if lock:
        stmt = stmt.with_for_update(of=BdmActivity).execution_options(populate_existing=True)
    activity = await db.scalar(stmt)
    if activity is None:
        raise HTTPException(404, NOT_FOUND)
    return activity


def audit(db: AsyncSession, user: User, action: str, activity: BdmActivity, fields: list[str] | None = None) -> None:
    """Same transaction as the write (fail closed); ids, channel and field names only."""
    meta: dict = {"organization_id": str(activity.organization_id), "channel": activity.channel}
    if fields is not None:
        meta["fields"] = fields
    db.add(AuditLog(user_id=user.id, action=f"bdm_activity.{action}", entity_type="bdm_activity", entity_id=str(activity.id),
                    metadata_json=meta))


def log(event: str, user: User, activity_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "activity_id": str(activity_id), **extra}})
```

- [ ] **Step 5: Run the tests to verify they pass**

`<P>` = `tests/test_bdm_009_service.py`. Expected: all PASS. (`bdm_with_org` calls the bdm-002 create route, so the shared DB
must be at head.)

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/bdm_activities.py apps/api/tests/bdm009_helpers.py apps/api/tests/test_bdm_009_service.py
git commit -m "feat(bdm-009): activity service -- IST time rules, rows, exact day counts, audit"
```

---

### Task 4: Router — log, my day, edit, delete

**Files:**
- Create: `apps/api/app/api/bdm_activities.py`
- Modify: `apps/api/app/main.py` (import `bdm_activities` in the `from app.api import (...)` list; append `bdm_activities.router`
  to the router tuple after `bdm_travel.router`)
- Test: `apps/api/tests/test_bdm_009_activities.py`

**Interfaces:**
- Consumes: Task 2 schemas; Task 3 service; `services.bdm_organizations.load_scoped`; `services.bdm.bdm_context`;
  `app.api.bdm.LIMIT, OFFSET`.
- Produces: `app.api.bdm_activities.router` (prefix `/bdm`) with `GET/POST /activities`, `PATCH/DELETE /activities/{activity_id}`.
  Task 5 adds two more routes to this module.

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_bdm_009_activities.py`:

```python
"""bdm-009 -- log, list my day, edit, delete (spec §5.3-§5.5; AC1, AC2, AC4, AC7, AC8)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, BdmActivity
from app.services import bdm_activities as svc
from app.services.bdm_travel import india_today
from tests.bdm009_helpers import ACTIVITIES, activity_body, add_activity, bdm_with_org

CHANNELS = [("call", "outbound"), ("whatsapp", "inbound"), ("email", "outbound"), ("visit", None), ("meeting", None), ("other", None)]


@pytest.mark.asyncio
@pytest.mark.parametrize("channel,direction", CHANNELS)
async def test_each_channel_is_loggable_against_an_organization(client, db_session, channel, direction):
    _, bdm, org = await bdm_with_org(client, db_session)
    response = await client.post(ACTIVITIES, json=activity_body(org["id"], channel=channel, direction=direction, note="Discussed intake"))
    assert response.status_code == 201, response.text
    data = response.json()
    assert (data["channel"], data["direction"], data["note"]) == (channel, direction, "Discussed intake")
    assert data["organization"]["id"] == org["id"]
    assert data["bdm"] == {"id": str(bdm.id), "full_name": bdm.full_name}
    assert data["permissions"] == {"can_change": True}


@pytest.mark.asyncio
async def test_a_time_slightly_ahead_is_saved_as_now(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    ahead = datetime.now(UTC) + timedelta(minutes=2)
    response = await client.post(ACTIVITIES, json=activity_body(org["id"], occurred_at=ahead.isoformat()))
    assert response.status_code == 201, response.text
    saved = datetime.fromisoformat(response.json()["occurred_at"].replace("Z", "+00:00"))
    assert saved < ahead  # clamped to the server's now (V9)


@pytest.mark.asyncio
async def test_the_daily_cap_refuses_the_next_log(client, db_session, monkeypatch):
    _, _, org = await bdm_with_org(client, db_session)
    monkeypatch.setattr(svc, "DAILY_CAP", 1)
    assert (await client.post(ACTIVITIES, json=activity_body(org["id"]))).status_code == 201
    response = await client.post(ACTIVITIES, json=activity_body(org["id"]))
    assert (response.status_code, response.json()["detail"]) == (409, svc.CAP_REACHED)


@pytest.mark.asyncio
async def test_future_and_too_old_occurred_at_are_422(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    future = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    response = await client.post(ACTIVITIES, json=activity_body(org["id"], occurred_at=future))
    assert (response.status_code, response.json()["detail"]) == (422, svc.FUTURE)
    old = (datetime.now(UTC) - timedelta(days=9)).isoformat()
    response = await client.post(ACTIVITIES, json=activity_body(org["id"], occurred_at=old))
    assert (response.status_code, response.json()["detail"]) == (422, svc.TOO_OLD)
    six_days = (datetime.now(UTC) - timedelta(days=6)).isoformat()
    assert (await client.post(ACTIVITIES, json=activity_body(org["id"], occurred_at=six_days))).status_code == 201


@pytest.mark.asyncio
async def test_my_day_lists_newest_first_with_exact_counts_independent_of_the_page(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    base = datetime.now(UTC) - timedelta(minutes=30)
    for i, (channel, direction) in enumerate([("call", "outbound"), ("call", "outbound"), ("call", "inbound"), ("visit", None)]):
        body = activity_body(org["id"], channel=channel, direction=direction, occurred_at=(base + timedelta(minutes=i)).isoformat())
        assert (await client.post(ACTIVITIES, json=body)).status_code == 201
    data = (await client.get(ACTIVITIES, params={"limit": 2})).json()
    assert len(data["items"]) == 2 and data["total"] == 4
    assert data["items"][0]["channel"] == "visit"  # newest first
    assert data["counts"]["by_channel"]["call"] == 3
    assert data["counts"]["calls_made"] == 2
    assert data["counts"]["organizations_contacted"] == 1
    assert data["counts"]["day"] == str(india_today())


@pytest.mark.asyncio
async def test_my_day_of_a_future_date_is_422_and_a_past_date_shows_that_day(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    tomorrow = india_today() + timedelta(days=1)
    assert (await client.get(ACTIVITIES, params={"date": str(tomorrow)})).status_code == 422
    past = india_today() - timedelta(days=20)
    start, _ = svc.day_range(past)
    await add_activity(db_session, bdm.id, uuid.UUID(org["id"]), start + timedelta(hours=2))
    data = (await client.get(ACTIVITIES, params={"date": str(past)})).json()
    assert data["total"] == 1 and data["items"][0]["permissions"]["can_change"] is False


@pytest.mark.asyncio
async def test_patch_today_changes_fields_and_audits_names_only(client, db_session):
    _, _, org = await bdm_with_org(client, db_session, contacts=[{"name": "Dr Rao"}, {"name": "Ms Iyer"}])
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"], note="secret note"))).json()
    contact = org["contacts"][1]
    body = {"direction": "inbound", "contact_id": contact["id"], "note": "call back Tuesday"}
    response = await client.patch(f"{ACTIVITIES}/{created['id']}", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["direction"], data["contact_name"], data["note"]) == ("inbound", "Ms Iyer", "call back Tuesday")
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == created["id"]).order_by(AuditLog.created_at))).all()
    assert [r.action for r in rows] == ["bdm_activity.created", "bdm_activity.updated"]
    assert sorted(rows[1].metadata_json["fields"]) == ["contact_id", "direction", "note"]
    flat = str([r.metadata_json for r in rows])
    for secret in ("secret note", "call back Tuesday", "Ms Iyer"):
        assert secret not in flat


@pytest.mark.asyncio
async def test_resending_the_same_contact_keeps_the_snapshot(client, db_session):
    _, _, org = await bdm_with_org(client, db_session, contacts=[{"name": "Dr Rao"}])
    rao = org["contacts"][0]["id"]
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"], contact_id=rao))).json()
    renamed = await client.patch(f"/api/v1/bdm/organizations/{org['id']}/contacts/{rao}", json={"name": "Dr K Rao"})  # bdm-002 route
    assert renamed.status_code == 200, renamed.text
    response = await client.patch(f"{ACTIVITIES}/{created['id']}", json={"contact_id": rao, "note": "follow-up"})
    assert response.status_code == 200
    assert response.json()["contact_name"] == "Dr Rao"  # the name at save, not the renamed one
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == created["id"], AuditLog.action == "bdm_activity.updated"))
    assert row.metadata_json["fields"] == ["note"]


@pytest.mark.asyncio
async def test_abuse_cases_server_owned_fields_and_markup(client, db_session):
    """AC13: mass assignment is refused; markup is stored and returned as plain text (React renders it as text)."""
    _, bdm, org = await bdm_with_org(client, db_session)
    for field, value in (("bdm_user_id", str(uuid.uuid4())), ("contact_name", "Forged"), ("id", str(uuid.uuid4()))):
        assert (await client.post(ACTIVITIES, json=activity_body(org["id"], **{field: value}))).status_code == 422
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"], note="<script>alert(1)</script>"))).json()
    assert created["note"] == "<script>alert(1)</script>"
    assert created["bdm"]["id"] == str(bdm.id)
    response = await client.patch(f"{ACTIVITIES}/{created['id']}", json={"organization_id": str(uuid.uuid4())})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_channel_change_needs_direction_cleared(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"]))).json()
    response = await client.patch(f"{ACTIVITIES}/{created['id']}", json={"channel": "visit"})
    assert (response.status_code, response.json()["detail"]) == (422, "Direction applies only to calls, WhatsApp and email")
    response = await client.patch(f"{ACTIVITIES}/{created['id']}", json={"channel": "visit", "direction": None})
    assert response.status_code == 200 and response.json()["direction"] is None


@pytest.mark.asyncio
async def test_patch_cannot_move_off_today_and_past_activities_are_locked(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"]))).json()
    yesterday = (datetime.now(UTC) - timedelta(days=1, hours=1)).isoformat()
    response = await client.patch(f"{ACTIVITIES}/{created['id']}", json={"occurred_at": yesterday})
    assert (response.status_code, response.json()["detail"]) == (422, svc.MOVE_TODAY)
    start, _ = svc.day_range(india_today() - timedelta(days=1))
    old = await add_activity(db_session, bdm.id, uuid.UUID(org["id"]), start + timedelta(hours=1))
    for request in (client.patch(f"{ACTIVITIES}/{old.id}", json={"note": "late"}), client.delete(f"{ACTIVITIES}/{old.id}")):
        response = await request
        assert (response.status_code, response.json()["detail"]) == (409, svc.NOT_TODAY)


@pytest.mark.asyncio
async def test_empty_patch_changes_nothing_and_writes_no_audit(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"]))).json()
    assert (await client.patch(f"{ACTIVITIES}/{created['id']}", json={})).status_code == 200
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == created["id"]))).all()
    assert actions == ["bdm_activity.created"]


@pytest.mark.asyncio
async def test_delete_today_removes_the_row_and_audits(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"], note="private"))).json()
    response = await client.delete(f"{ACTIVITIES}/{created['id']}")
    assert response.status_code == 204
    assert await db_session.get(BdmActivity, uuid.UUID(created["id"]), populate_existing=True) is None
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == created["id"], AuditLog.action == "bdm_activity.deleted"))
    assert row.metadata_json == {"organization_id": org["id"], "channel": "call"}
    assert (await client.delete(f"{ACTIVITIES}/{created['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_contact_must_belong_to_the_organization_and_survives_contact_delete(client, db_session):
    _, _, other = await bdm_with_org(client, db_session)
    foreign = other["contacts"][0]["id"]
    _, _, org = await bdm_with_org(client, db_session, contacts=[{"name": "Dr Rao", "role": "principal"}, {"name": "Ms Iyer"}])
    response = await client.post(ACTIVITIES, json=activity_body(org["id"], contact_id=foreign))
    assert (response.status_code, response.json()["detail"]) == (422, svc.CONTACT_INVALID)
    iyer = org["contacts"][1]["id"]
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"], contact_id=iyer))).json()
    assert created["contact_name"] == "Ms Iyer"
    assert (await client.delete(f"/api/v1/bdm/organizations/{org['id']}/contacts/{iyer}")).status_code == 200  # bdm-002 route
    listed = (await client.get(ACTIVITIES)).json()["items"]
    mine = next(i for i in listed if i["id"] == created["id"])
    assert (mine["contact_id"], mine["contact_name"], mine["contact_removed"]) == (None, "Ms Iyer", True)
```

Note for the implementer: `create_org` in `bdm002_helpers` takes `**overrides` merged into the payload, so `contacts=[...]` replaces
the default contact list.

- [ ] **Step 2: Run it to verify it fails**

`<P>` = `tests/test_bdm_009_activities.py`. Expected: FAIL — `404 Not Found` on `POST /api/v1/bdm/activities`.

- [ ] **Step 3: Write the router** — `apps/api/app/api/bdm_activities.py`:

```python
"""bdm-009 (DEC-SCOPE-065, spec §5.3): the BDM activity log.

Every `{activity_id}` resolves through `services.bdm_activities.load_readable` (unreadable = 404). Every write is one transaction --
scope (404), owner / assignee (403), lock (organization, then activity), rules (422 / 409), change, audit, one commit here. Lists are
{items, total, limit, offset}, newest first; the day lists also carry that whole day's counts."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BdmActivity, User
from app.schemas import BdmActivityChannel, BdmActivityCreate, BdmActivityDayPage, BdmActivityOut, BdmActivityUpdate
from app.services import bdm_activities as svc
from app.services import bdm_organizations as org_svc
from app.services.bdm import bdm_context

router = APIRouter(prefix="/bdm", tags=["bdm-activities"])
DAY = Query(None, alias="date", description="IST calendar date, YYYY-MM-DD; default today")


def _day(day: date | None, now) -> date:
    today = svc.india_date(now)
    chosen = day or today
    if chosen > today:
        raise HTTPException(422, svc.FUTURE_DAY)
    return chosen


@router.get("/activities", response_model=BdmActivityDayPage)
async def my_activities(day: date | None = DAY, channel: BdmActivityChannel | None = None, organization_id: UUID | None = None,
                        limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await bdm_context(db, user)
    now = await svc.db_now(db)
    chosen = _day(day, now)
    filters = [BdmActivity.bdm_user_id == user.id, *svc.optional_filters(channel, organization_id)]
    listed = await svc.page(db, [*filters, *svc.day_filters(chosen)], limit, offset, user, now)
    return {**listed, "counts": await svc.day_counts(db, filters, chosen)}


@router.post("/activities", status_code=201, response_model=BdmActivityOut)
async def log_activity(payload: BdmActivityCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await bdm_context(db, user)
    org = await org_svc.load_scoped(db, user, payload.organization_id, lock=True)  # out of type -> 404; serializes with archive/assign
    if org.assigned_bdm_user_id != user.id:
        raise svc.refused(user, "activity_create", 403, svc.NOT_ASSIGNED, organization_id=org.id)
    if org.archived_at is not None:
        raise HTTPException(422, svc.ARCHIVED)
    contact = await svc.contact_for(db, org.id, payload.contact_id) if payload.contact_id else None
    now = await svc.db_now(db)
    occurred_at = svc.check_time(payload.occurred_at, now)  # V9: clamped to now when slightly ahead
    await svc.check_daily_cap(db, user.id, svc.india_date(occurred_at))
    activity = BdmActivity(
        bdm_user_id=user.id, organization_id=org.id, contact_id=contact.id if contact else None,
        contact_name=contact.name if contact else None, channel=payload.channel, direction=payload.direction,
        occurred_at=occurred_at, note=payload.note,
    )
    db.add(activity)
    await db.flush()
    svc.audit(db, user, "created", activity)
    await db.commit()
    svc.log("bdm_activity_created", user, activity.id, channel=activity.channel)
    return await svc.one(db, user, activity.id, now)


async def _owned(db: AsyncSession, user: User, activity_id: UUID, route: str):
    """Scope (404) and owner (403) before any lock; then organization, then activity (spec §5.5); then the day gate (409)."""
    current = await svc.load_readable(db, user, activity_id)
    if current.bdm_user_id != user.id:
        raise svc.refused(user, route, 403, svc.OWNER_ONLY, activity_id=activity_id)
    org = await org_svc.load_scoped(db, user, current.organization_id, lock=True)
    activity = await svc.load_readable(db, user, activity_id, lock=True)  # a concurrent delete -> 404 here
    now = await svc.db_now(db)
    if not svc.editable(activity, now):
        raise HTTPException(409, svc.NOT_TODAY)
    return org, activity, now


@router.patch("/activities/{activity_id}", response_model=BdmActivityOut)
async def update_activity(activity_id: UUID, payload: BdmActivityUpdate, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    org, activity, now = await _owned(db, user, activity_id, "activity_update")
    changes = payload.model_dump(exclude_unset=True)
    if "occurred_at" in changes:
        changes["occurred_at"] = svc.check_time(changes["occurred_at"], now)
        if svc.india_date(changes["occurred_at"]) != svc.india_date(now):
            raise HTTPException(422, svc.MOVE_TODAY)
    if "contact_id" in changes:
        if changes["contact_id"] == activity.contact_id:
            del changes["contact_id"]  # §12.1 A2: the same contact again never rewrites the stored name
        else:
            contact = await svc.contact_for(db, org.id, changes["contact_id"]) if changes["contact_id"] else None
            changes["contact_name"] = contact.name if contact else None
    svc.check_direction(changes.get("channel", activity.channel), changes.get("direction", activity.direction))
    changed = sorted(k for k, v in changes.items() if k != "contact_name" and getattr(activity, k) != v)
    if not changed:
        return await svc.one(db, user, activity.id, now)
    for key, value in changes.items():
        setattr(activity, key, value)
    await db.flush()
    svc.audit(db, user, "updated", activity, changed)
    await db.commit()
    svc.log("bdm_activity_updated", user, activity.id, fields=changed)
    return await svc.one(db, user, activity.id, now)


@router.delete("/activities/{activity_id}", status_code=204)
async def delete_activity(activity_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """V8: a hard delete; the audit row keeps the id, organization and channel (never the note)."""
    _, activity, _ = await _owned(db, user, activity_id, "activity_delete")
    svc.audit(db, user, "deleted", activity)
    await db.delete(activity)
    await db.commit()
    svc.log("bdm_activity_deleted", user, activity_id)
    return Response(status_code=204)
```

- [ ] **Step 4: Register the router** — `apps/api/app/main.py`: add `bdm_activities,` to the `from app.api import (` list (keep it
  alphabetical, before `bdm_organizations`), and add `bdm_activities.router` to the router tuple right after `bdm_travel.router`.

- [ ] **Step 5: Run the tests to verify they pass**

`<P>` = `tests/test_bdm_009_activities.py tests/test_bdm_009_service.py`. Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/bdm_activities.py apps/api/app/main.py apps/api/tests/test_bdm_009_activities.py
git commit -m "feat(bdm-009): log, list, edit and delete activities"
```

---

### Task 5: Router — organization timeline, team list, scope and concurrency

**Files:**
- Modify: `apps/api/app/api/bdm_activities.py` (append two routes)
- Test: `apps/api/tests/test_bdm_009_scope.py`, `apps/api/tests/test_bdm_009_concurrency.py`

**Interfaces:**
- Consumes: Task 4 module; `services.bdm.require_manager`, `team_filter`; `BdmActivityPage` (Task 2).
- Produces: `GET /bdm/organizations/{org_id}/activities` → `BdmActivityPage`; `GET /bdm/manager/activities` → `BdmActivityDayPage`.

- [ ] **Step 1: Write the failing scope test** — `apps/api/tests/test_bdm_009_scope.py`:

```python
"""bdm-009 -- authorization (spec §5.4; AC5, AC6)."""

import pytest

from tests.bdm001_helpers import login, make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm009_helpers import ACTIVITIES, TEAM_ACTIVITIES, activity_body, bdm_with_org, org_activities


async def as_user(client, user) -> None:
    client.cookies.clear()
    await login(client, user)


@pytest.mark.asyncio
async def test_out_of_type_org_is_404_and_unassigned_same_type_is_403(client, db_session):
    manager, _, org = await bdm_with_org(client, db_session, "college")
    await as_user(client, await make_bdm(db_session, manager, "school"))
    assert (await client.post(ACTIVITIES, json=activity_body(org["id"]))).status_code == 404
    await as_user(client, await make_bdm(db_session, manager, "college"))
    response = await client.post(ACTIVITIES, json=activity_body(org["id"]))
    assert (response.status_code, response.json()["detail"]) == (403, "Only the organization's assigned BDM can log activity")


@pytest.mark.asyncio
async def test_archived_org_refuses_a_new_log_but_today_entries_stay_editable(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"]))).json()
    assert (await client.post(f"/api/v1/bdm/organizations/{org['id']}/archive")).status_code == 200
    response = await client.post(ACTIVITIES, json=activity_body(org["id"]))
    assert (response.status_code, response.json()["detail"]) == (422, "This organization is archived")
    assert (await client.patch(f"{ACTIVITIES}/{created['id']}", json={"note": "fixed"})).status_code == 200


@pytest.mark.asyncio
async def test_only_the_logger_changes_an_activity(client, db_session):
    manager, _, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"]))).json()
    for user in (await make_bdm(db_session, manager, "college"), manager, await make_user(db_session, "super_admin", "global")):
        await as_user(client, user)
        assert (await client.patch(f"{ACTIVITIES}/{created['id']}", json={"note": "x"})).status_code == 403
        assert (await client.delete(f"{ACTIVITIES}/{created['id']}")).status_code == 403
    await as_user(client, await make_bdm(db_session, manager, "agent"))
    assert (await client.patch(f"{ACTIVITIES}/{created['id']}", json={"note": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_timeline_is_visible_to_every_reader_of_the_organization(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    await client.post(ACTIVITIES, json=activity_body(org["id"]))
    for user in (await make_bdm(db_session, manager, "college"), manager, await make_user(db_session, "super_admin", "global")):
        await as_user(client, user)
        data = (await client.get(org_activities(org["id"]))).json()
        assert data["total"] == 1 and data["items"][0]["bdm"]["id"] == str(bdm.id)
        assert data["items"][0]["permissions"]["can_change"] is False
    await as_user(client, await make_bdm(db_session, manager, "school"))
    assert (await client.get(org_activities(org["id"]))).status_code == 404
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(org_activities(org["id"]))).status_code == 403


@pytest.mark.asyncio
async def test_manager_reads_the_team_only_and_bdm_filter_only_narrows(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    await client.post(ACTIVITIES, json=activity_body(org["id"]))
    other_manager, outsider, outsider_org = await bdm_with_org(client, db_session)
    await client.post(ACTIVITIES, json=activity_body(outsider_org["id"]))
    await as_user(client, manager)
    team = (await client.get(TEAM_ACTIVITIES)).json()
    assert {i["bdm"]["id"] for i in team["items"]} == {str(bdm.id)}
    assert team["counts"]["by_channel"]["call"] == 1
    narrowed = (await client.get(TEAM_ACTIVITIES, params={"bdm_user_id": str(outsider.id)})).json()
    assert narrowed["total"] == 0 and narrowed["counts"]["by_channel"]["call"] == 0
    assert (await client.post(ACTIVITIES, json=activity_body(org["id"]))).status_code == 403
    await as_user(client, bdm)
    assert (await client.get(TEAM_ACTIVITIES)).status_code == 403


@pytest.mark.asyncio
async def test_refused_writes_are_logged_with_ids_only(client, db_session, caplog):
    """§12.3 S10: a 403 on a write leaves a warning with ids, route and status -- never the note."""
    manager, _, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"], note="private words"))).json()
    await as_user(client, await make_bdm(db_session, manager, "college"))
    with caplog.at_level("WARNING", logger="app.bdm"):
        assert (await client.delete(f"{ACTIVITIES}/{created['id']}")).status_code == 403
        assert (await client.post(ACTIVITIES, json=activity_body(org["id"], note="more words"))).status_code == 403
    refusals = [r for r in caplog.records if r.getMessage() == "bdm_activity_write_refused"]
    assert [r.extra_fields["route"] for r in refusals] == ["activity_delete", "activity_create"]
    assert all(r.extra_fields["status"] == 403 for r in refusals)
    assert "words" not in str([r.extra_fields for r in refusals])


@pytest.mark.asyncio
async def test_other_roles_are_refused(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    for role, division in (("it_admin", "it"), ("overseas_admin", "overseas")):
        await as_user(client, await make_user(db_session, role, division))
        assert (await client.get(ACTIVITIES)).status_code == 403
        assert (await client.post(ACTIVITIES, json=activity_body(org["id"]))).status_code == 403
        assert (await client.get(TEAM_ACTIVITIES)).status_code == 403
```

- [ ] **Step 2: Write the failing concurrency test** — `apps/api/tests/test_bdm_009_concurrency.py`:

```python
"""bdm-009 -- AC9: the organization lock serializes log vs archive; the activity lock lets one of two deletes win."""

import asyncio
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.bdm001_helpers import login
from tests.bdm009_helpers import ACTIVITIES, activity_body, bdm_with_org


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_two_deletes_one_wins(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    created = (await client.post(ACTIVITIES, json=activity_body(org["id"]))).json()
    async with _client() as a, _client() as b:
        await login(a, bdm)
        await login(b, bdm)
        results = await asyncio.gather(a.delete(f"{ACTIVITIES}/{created['id']}"), b.delete(f"{ACTIVITIES}/{created['id']}"))
    assert sorted(r.status_code for r in results) == [204, 404]


@pytest.mark.asyncio
async def test_log_and_archive_race_never_leaves_a_log_after_the_archive(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    async with _client() as a, _client() as b:
        await login(a, bdm)
        await login(b, bdm)
        logged, archived = await asyncio.gather(
            a.post(ACTIVITIES, json=activity_body(org["id"])), b.post(f"/api/v1/bdm/organizations/{org['id']}/archive"))
    assert archived.status_code == 200
    assert logged.status_code in (201, 422)
    if logged.status_code == 201:  # logged first: created before the archive committed
        created_at = datetime.fromisoformat(logged.json()["created_at"].replace("Z", "+00:00"))
        archived_at = datetime.fromisoformat(archived.json()["organization"]["archived_at"].replace("Z", "+00:00"))
        assert created_at <= archived_at
    else:
        assert logged.json()["detail"] == "This organization is archived"
```

- [ ] **Step 3: Run them to verify they fail**

`<P>` = `tests/test_bdm_009_scope.py tests/test_bdm_009_concurrency.py`. Expected: the timeline and team tests FAIL with 404 (routes
missing); the rest may already pass.

- [ ] **Step 4: Append the two routes** — `apps/api/app/api/bdm_activities.py`. Extend the imports:
  `from app.schemas import BdmActivityChannel, BdmActivityCreate, BdmActivityDayPage, BdmActivityOut, BdmActivityPage, BdmActivityUpdate`
  and `from app.services.bdm import bdm_context, require_manager, team_filter`. Then append:

```python
@router.get("/organizations/{org_id}/activities", response_model=BdmActivityPage)
async def organization_activities(org_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db)):
    """V5: every BDM's activities on the organization, for anyone who can read it (out of scope -> 404)."""
    org = await org_svc.load_scoped(db, user, org_id)
    now = await svc.db_now(db)
    return await svc.page(db, [BdmActivity.organization_id == org.id], limit, offset, user, now)


@router.get("/manager/activities", response_model=BdmActivityDayPage)
async def team_activities(day: date | None = DAY, bdm_user_id: UUID | None = None, channel: BdmActivityChannel | None = None,
                          limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Team scope (D4); `bdm_user_id` is ANDed with it, so it can only narrow."""
    require_manager(user)
    now = await svc.db_now(db)
    chosen = _day(day, now)
    filters = [*team_filter(user), *svc.optional_filters(channel, None)]
    if bdm_user_id:
        filters.append(BdmActivity.bdm_user_id == bdm_user_id)
    listed = await svc.page(db, [*filters, *svc.day_filters(chosen)], limit, offset, user, now)
    return {**listed, "counts": await svc.day_counts(db, filters, chosen)}
```

- [ ] **Step 5: Run the backend bdm-009 set**

`<P>` = `tests/test_bdm_009_*.py`. Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/bdm_activities.py apps/api/tests/test_bdm_009_scope.py apps/api/tests/test_bdm_009_concurrency.py
git commit -m "feat(bdm-009): organization timeline and team activity list; scope and race tests"
```

---

### Task 6: Web — activity library, item and form

**Files:**
- Create: `apps/web/lib/bdmActivities.ts`, `apps/web/components/BdmActivityForm.tsx`, `apps/web/components/BdmActivityItem.tsx`
- Test: `apps/web/tests/lib/bdmActivities.test.ts`, `apps/web/tests/components/BdmActivityForm.test.tsx`,
  `apps/web/tests/components/BdmActivityItem.test.tsx`

**Interfaces:**
- Consumes: `sendJson`, `sendRequest`, `isPage`, `Page` (`lib/apiErrors`); `fieldErrors` (`lib/bdmTravel`); `localToIso`,
  `toLocalInput` (`lib/agentTasks`); `ORGS_URL`, `ORG_TYPE_LABEL`, `type OrgType`, `LINK_STYLE` (`lib/bdmOrganizations`);
  `SearchableSelect`; `BdmConfirm`; `LocalTime`; `useLeaveGuard`; `useFocusAfterRender`.
- Produces (`lib/bdmActivities.ts`): `CHANNELS`, `type Channel`, `type Direction`, `CHANNEL_LABEL`, `DIRECTION_LABEL`,
  `needsDirection(c)`, `NOTE_MAX = 500`, `TIMELINE_PAGE = 20`, `DAY_PAGE = 50`, `type Activity`, `type DayCounts`,
  `type ActivityDayPage`, `ACTIVITIES_URL`, `TEAM_ACTIVITIES_URL`, `activityUrl(id)`, `orgActivitiesUrl(orgId, offset)`,
  `isActivity(data)`, `isDayPage(data)`, `contactText(a)`, `activityRuleField(detail)`, `assignedOrgSearch(q, signal)`,
  `placeNewest(items, a)`.
- Produces (components):
  - `BdmActivityForm({ organizationId?, contacts?, activity?, onSaved(a: Activity, created: boolean), onCancel })`
  - `BdmActivityItem({ activity, showOrganization?, orgBasePath?, onChanged(a: Activity), onDeleted(id: string) })`

- [ ] **Step 1: Write the failing library test** — `apps/web/tests/lib/bdmActivities.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { activityRuleField, contactText, isDayPage, needsDirection, placeNewest, type Activity } from "@/lib/bdmActivities";

const a = (over: Partial<Activity> = {}): Activity => ({
  id: "a1", organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college" }, bdm: { id: "b1", full_name: "Asha" },
  contact_id: null, contact_name: null, contact_removed: false, channel: "call", direction: "outbound", occurred_at: "2026-10-03T05:00:00Z",
  note: null, created_at: "2026-10-03T05:00:00Z", updated_at: "2026-10-03T05:00:00Z", permissions: { can_change: true }, ...over,
});

describe("bdmActivities", () => {
  it("knows which channels carry a direction", () => {
    expect(["call", "whatsapp", "email"].every((c) => needsDirection(c as Activity["channel"]))).toBe(true);
    expect(["visit", "meeting", "other"].some((c) => needsDirection(c as Activity["channel"]))).toBe(false);
  });

  it("words a removed contact", () => {
    expect(contactText(a())).toBeNull();
    expect(contactText(a({ contact_id: "c1", contact_name: "Dr Rao" }))).toBe("Dr Rao");
    expect(contactText(a({ contact_name: "Dr Rao", contact_removed: true }))).toBe("Dr Rao (removed)");
  });

  it("puts the API's time and contact sentences on their fields", () => {
    expect(activityRuleField("When can't be in the future")).toEqual({ occurred_at: "When can't be in the future" });
    expect(activityRuleField("Activities can be logged up to 7 days back")).toHaveProperty("occurred_at");
    expect(activityRuleField("An activity can only be moved within today")).toHaveProperty("occurred_at");
    expect(activityRuleField("Choose a contact of this organization")).toHaveProperty("contact_id");
    expect(activityRuleField("Only the organization's assigned BDM can log activity")).toEqual({});
    expect(activityRuleField([{ loc: ["body", "x"] }])).toEqual({});
  });

  it("places an activity newest first and replaces an edited one", () => {
    const list = [a({ id: "a2", occurred_at: "2026-10-03T06:00:00Z" }), a({ id: "a1" })];
    expect(placeNewest(list, a({ id: "a3", occurred_at: "2026-10-03T05:30:00Z" })).map((x) => x.id)).toEqual(["a2", "a3", "a1"]);
    expect(placeNewest(list, a({ id: "a1", occurred_at: "2026-10-03T07:00:00Z" })).map((x) => x.id)).toEqual(["a1", "a2"]);
  });

  it("trusts a day page only with counts", () => {
    expect(isDayPage({ items: [], total: 0, limit: 50, offset: 0 })).toBe(false);
    expect(isDayPage({ items: [], total: 0, limit: 50, offset: 0, counts: { day: "2026-10-03", by_channel: {}, calls_made: 0, organizations_contacted: 0 } })).toBe(true);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Web command with `npx vitest run tests/lib/bdmActivities.test.ts`. Expected: FAIL — cannot resolve `@/lib/bdmActivities`.

- [ ] **Step 3: Write the library** — `apps/web/lib/bdmActivities.ts`:

```ts
import { isPage, type Page } from "@/lib/apiErrors";
import { ORGS_URL, type OrgType } from "@/lib/bdmOrganizations";
import type { LookupPage } from "@/lib/lookups";

// bdm-009 (DEC-SCOPE-065): activity types, labels and endpoints for the organization timeline and the activity pages. The API decides
// every rule; `permissions.can_change` only tells the UI whether to offer Edit / Delete.
export const CHANNELS = ["call", "whatsapp", "email", "visit", "meeting", "other"] as const;
export type Channel = (typeof CHANNELS)[number];
export type Direction = "outbound" | "inbound";
export const CHANNEL_LABEL: Record<Channel, string> = { call: "Call", whatsapp: "WhatsApp", email: "Email", visit: "Visit", meeting: "Meeting", other: "Other" };
export const DIRECTION_LABEL: Record<Direction, string> = { outbound: "Outgoing", inbound: "Incoming" };
export const needsDirection = (channel: Channel) => channel === "call" || channel === "whatsapp" || channel === "email";
export const NOTE_MAX = 500;
export const BACKDATE_DAYS = 7; // V4 (the API decides; used in the When hint)
export const TIMELINE_PAGE = 20;
export const DAY_PAGE = 50;
const PICKER_LIMIT = 20;

export type Activity = {
  id: string;
  organization: { id: string; code: string; name: string; org_type: OrgType };
  bdm: { id: string; full_name: string }; // bdm-010's PersonRef shape (spec §12.1 A1)
  contact_id: string | null; contact_name: string | null; contact_removed: boolean;
  channel: Channel; direction: Direction | null; occurred_at: string; note: string | null;
  created_at: string; updated_at: string; permissions: { can_change: boolean };
};
export type DayCounts = { day: string; by_channel: Record<Channel, number>; calls_made: number; organizations_contacted: number };
export type ActivityDayPage = Page<Activity> & { counts: DayCounts };

export const ACTIVITIES_URL = "/api/v1/bdm/activities";
export const TEAM_ACTIVITIES_URL = "/api/v1/bdm/manager/activities";
export const activityUrl = (id: string) => `${ACTIVITIES_URL}/${id}`;
export const orgActivitiesUrl = (orgId: string, offset = 0) => `${ORGS_URL}/${orgId}/activities?limit=${TIMELINE_PAGE}&offset=${offset}`;

export function isActivity(data: unknown): data is Activity {
  const d = data as Partial<Activity> | null;
  return !!d && typeof d.id === "string" && !!d.organization && typeof d.occurred_at === "string";
}

export function isDayPage(data: unknown): data is ActivityDayPage {
  return isPage(data) && !!(data as { counts?: unknown }).counts && typeof (data as { counts: object }).counts === "object";
}

export function contactText(a: Activity): string | null {
  if (!a.contact_name) return null;
  return a.contact_removed ? `${a.contact_name} (removed)` : a.contact_name;
}

/** The API answers its time and contact rules as one sentence; put each on the field it is about (the bdm-010 dateRuleField idea). */
export function activityRuleField(detail: unknown): Record<string, string> {
  if (typeof detail !== "string") return {};
  if (detail.startsWith("When") || detail.startsWith("Activities can be logged") || detail.startsWith("An activity can only be moved")) return { occurred_at: detail };
  if (detail.startsWith("Choose a contact")) return { contact_id: detail };
  return {};
}

/** A saved activity in a newest-first list: replaced if present, otherwise inserted in time order. */
export function placeNewest(items: Activity[], activity: Activity): Activity[] {
  const rest = items.filter((x) => x.id !== activity.id);
  return [...rest, activity].sort((x, y) => (x.occurred_at === y.occurred_at ? y.id.localeCompare(x.id) : y.occurred_at.localeCompare(x.occurred_at)));
}

/** The activities page's organization picker: the BDM's own assigned, active organizations (V1). */
export async function assignedOrgSearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ assigned: "me", limit: String(PICKER_LIMIT) });
  if (q) query.set("q", q);
  const response = await fetch(`${ORGS_URL}?${query}`, { signal });
  if (!response.ok) throw new Error(`Organization search failed (${response.status})`);
  const page = (await response.json()) as { items: { id: string; code: string; name: string; city: string }[]; total: number };
  return { items: page.items.map((o) => ({ id: o.id, label: o.name, detail: `${o.code} · ${o.city}` })), truncated: page.total > page.items.length };
}
```

- [ ] **Step 4: Run the library test** — expected PASS.

- [ ] **Step 5: Write the failing form test** — `apps/web/tests/components/BdmActivityForm.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmActivityForm from "@/components/BdmActivityForm";
import type { Activity } from "@/lib/bdmActivities";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const saved = (over: Partial<Activity> = {}): Activity => ({
  id: "a1", organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college" }, bdm: { id: "b1", full_name: "Asha" },
  contact_id: null, contact_name: null, contact_removed: false, channel: "call", direction: "outbound", occurred_at: "2026-10-03T05:00:00Z",
  note: null, created_at: "2026-10-03T05:00:00Z", updated_at: "2026-10-03T05:00:00Z", permissions: { can_change: true }, ...over,
});
const contacts = [{ id: "c1", name: "Dr Rao" }, { id: "c2", name: "Ms Iyer" }];
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmActivityForm (bdm-009 §6.3)", () => {
  it("shows direction only for call, WhatsApp and email and clears it on a channel change", () => {
    render(<BdmActivityForm organizationId="o1" contacts={contacts} onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("group", { name: "Direction (required)" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "visit" } });
    expect(screen.queryByRole("group", { name: /Direction/ })).toBeNull();
  });

  it("logs a call with the picked contact and a UTC time", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(saved({ contact_id: "c2", contact_name: "Ms Iyer" }), 201)));
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();
    render(<BdmActivityForm organizationId="o1" contacts={contacts} onSaved={onSaved} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Outgoing"));
    fireEvent.change(screen.getByLabelText("Contact"), { target: { value: "c2" } });
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Asked about the MoU" } });
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ id: "a1" }), true));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/bdm/activities");
    const body = JSON.parse(String(init.body));
    expect(body).toMatchObject({ organization_id: "o1", channel: "call", direction: "outbound", contact_id: "c2", note: "Asked about the MoU" });
    expect(body.occurred_at).toMatch(/Z$/);
  });

  it("asks for a direction before sending and focuses it", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityForm organizationId="o1" contacts={contacts} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    expect(screen.getByText("Choose outgoing or incoming.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Check the highlighted fields.");
    await waitFor(() => expect(screen.getByLabelText("Outgoing")).toHaveFocus());
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("focuses Channel on open and shows the time and privacy hints", async () => {
    render(<BdmActivityForm organizationId="o1" contacts={contacts} onSaved={vi.fn()} onCancel={vi.fn()} />);
    await waitFor(() => expect(screen.getByLabelText("Channel (required)")).toHaveFocus());
    expect(screen.getByLabelText("When (required)")).toHaveAccessibleDescription(/Your local time\. Up to 7 days back\./);
    expect(screen.getByLabelText("Note")).toHaveAccessibleDescription(/Everyone who can see this organization can read this note\./);
  });

  it("puts a time-rule 422 on the When field", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "When can't be in the future" }, 422))));
    render(<BdmActivityForm organizationId="o1" contacts={contacts} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Incoming"));
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    expect(await screen.findByText("When can't be in the future")).toHaveAttribute("id", expect.stringContaining("occurred_at"));
  });

  it("shows a refusal and keeps the entry", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Only the organization's assigned BDM can log activity" }, 403))));
    render(<BdmActivityForm organizationId="o1" contacts={contacts} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Outgoing"));
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "keep me" } });
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only the organization's assigned BDM can log activity");
    expect(screen.getByLabelText("Note")).toHaveValue("keep me");
  });

  it("edits only the changed fields and sends direction null when the channel no longer needs one", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(saved({ channel: "visit", direction: null }))));
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();
    render(<BdmActivityForm organizationId="o1" contacts={contacts} activity={saved()} onSaved={onSaved} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "visit" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ channel: "visit" }), false));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect([url, init.method]).toEqual(["/api/v1/bdm/activities/a1", "PATCH"]);
    expect(JSON.parse(String(init.body))).toEqual({ channel: "visit", direction: null });
  });

  it("loads the organization's contacts when it is picked (activities page)", async () => {
    const fetchMock = vi.fn((url: string) =>
      Promise.resolve(url.includes("?") ? res({ items: [{ id: "o9", code: "ORG-000009", name: "St Jude", city: "Kochi" }], total: 1 }) : res({ organization: { id: "o9", contacts } })),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityForm onSaved={vi.fn()} onCancel={vi.fn()} />);
    const picker = screen.getByRole("combobox", { name: /Organization/ });
    fireEvent.focus(picker);
    fireEvent.change(picker, { target: { value: "Jude" } });
    fireEvent.click(await screen.findByRole("option", { name: /St Jude/ }));
    await waitFor(() => expect(screen.getByRole("option", { name: "Ms Iyer" })).toBeInTheDocument());
  });
});
```

- [ ] **Step 6: Run it to verify it fails** — `npx vitest run tests/components/BdmActivityForm.test.tsx`. Expected: FAIL —
  cannot resolve `@/components/BdmActivityForm`.

- [ ] **Step 7: Write the form** — `apps/web/components/BdmActivityForm.tsx`:

```tsx
"use client";
import { type FormEvent, useEffect, useId, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { localToIso, toLocalInput } from "@/lib/agentTasks";
import { sendJson } from "@/lib/apiErrors";
import {
  ACTIVITIES_URL, type Activity, activityRuleField, activityUrl, assignedOrgSearch, BACKDATE_DAYS, type Channel, CHANNEL_LABEL, CHANNELS,
  type Direction, DIRECTION_LABEL, isActivity, needsDirection, NOTE_MAX,
} from "@/lib/bdmActivities";
import { fieldErrors } from "@/lib/bdmTravel";
import { ORGS_URL } from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

type ContactOption = { id: string; name: string };
type Draft = { channel: Channel; direction: Direction | null; occurredLocal: string; contactId: string; note: string };

const fromActivity = (a: Activity): Draft => ({
  channel: a.channel, direction: a.direction, occurredLocal: toLocalInput(a.occurred_at), contactId: a.contact_id ?? "", note: a.note ?? "",
});
const fresh = (): Draft => ({ channel: "call", direction: null, occurredLocal: toLocalInput(new Date().toISOString()), contactId: "", note: "" });

// bdm-009 (spec §6.3): log or edit one activity. The organization is fixed on the profile, or picked (the BDM's own assigned ones) on
// the activities page; the contacts come with it. The API decides every rule; the client only hints (direction, max time).
export default function BdmActivityForm({
  organizationId, contacts, activity, onSaved, onCancel,
}: {
  organizationId?: string;
  contacts?: ContactOption[];
  activity?: Activity;
  onSaved: (a: Activity, created: boolean) => void;
  onCancel: () => void;
}) {
  const idp = useId();
  const editing = !!activity;
  const [initial] = useState<Draft>(() => (activity ? fromActivity(activity) : fresh())); // fixed at open: "now" must not move the dirty check
  const [draft, setDraft] = useState<Draft>(initial);
  const [orgId, setOrgId] = useState(organizationId ?? activity?.organization.id ?? "");
  const [options, setOptions] = useState<ContactOption[]>(contacts ?? []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);
  useLeaveGuard(dirty && !busy, "Discard this activity?");

  useEffect(() => {
    if (contacts || !orgId) return;
    const controller = new AbortController();
    fetch(`${ORGS_URL}/${orgId}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setOptions(data?.organization?.contacts?.map((c: ContactOption) => ({ id: c.id, name: c.name })) ?? []))
      .catch(() => setOptions([]));
    return () => controller.abort();
  }, [contacts, orgId]);

  const fieldId = (name: string) => `${idp}-${name}`;
  const focus = useFocusAfterRender();
  const pickerId = fieldId("organization_id");
  const picking = !organizationId && !editing;
  useEffect(() => focus(picking ? pickerId : fieldId("channel")), []); // eslint-disable-line react-hooks/exhaustive-deps -- once, on open (§12.2 F4)

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  // §12.2 F4: after a refused save, focus the first field that carries an error, else the top message (the TripForm pattern).
  const FIELD_ORDER = ["organization_id", "direction", "occurred_at", "contact_id", "note"];
  const focusFirst = (found: Record<string, string>) => {
    const first = FIELD_ORDER.find((name) => found[name]);
    focus(first === "direction" ? `${fieldId("direction")}-outbound` : first ? fieldId(first) : fieldId("message"));
  };
  const errorId = (name: string) => `${idp}-${name}-error`;
  const err = (name: string) => // the TripForm convention: a .form-error paragraph the input points at
    errors[name] ? <p id={errorId(name)} className="form-error">{errors[name]}</p> : null;
  const described = (name: string) => ({ "aria-invalid": errors[name] ? true : undefined, "aria-describedby": errors[name] ? errorId(name) : undefined });

  function body(): Record<string, unknown> {
    const occurred_at = localToIso(draft.occurredLocal);
    const full = { channel: draft.channel, direction: needsDirection(draft.channel) ? draft.direction : null, contact_id: draft.contactId || null,
      occurred_at, note: draft.note.trim() || null };
    if (!editing) return { organization_id: orgId, ...full };
    const before = fromActivity(activity!);
    const out: Record<string, unknown> = {};
    if (draft.channel !== before.channel) out.channel = full.channel;
    if (full.direction !== before.direction) out.direction = full.direction;
    if (draft.contactId !== before.contactId) out.contact_id = full.contact_id;
    if (draft.occurredLocal !== before.occurredLocal) out.occurred_at = full.occurred_at;
    if (draft.note !== before.note) out.note = full.note;
    return out;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const local: Record<string, string> = {};
    if (!orgId) local.organization_id = "Choose an organization.";
    if (needsDirection(draft.channel) && !draft.direction) local.direction = "Choose outgoing or incoming.";
    if (!localToIso(draft.occurredLocal)) local.occurred_at = "Enter when it happened.";
    setErrors(local);
    setFailure(null);
    if (Object.keys(local).length) {
      setFailure("Check the highlighted fields.");
      return focusFirst(local);
    }
    setBusy(true);
    const outcome = editing ? await sendJson(activityUrl(activity!.id), "PATCH", body()) : await sendJson(ACTIVITIES_URL, "POST", body());
    setBusy(false);
    if (outcome.ok && isActivity(outcome.data)) return onSaved(outcome.data, !editing);
    if (outcome.ok) {
      setFailure("Unable to save this activity.");
      return focusFirst({});
    }
    const mapped = { ...fieldErrors(outcome.detail), ...activityRuleField(outcome.detail) };
    setErrors(mapped);
    setFailure(Object.keys(mapped).length ? "Check the highlighted fields." : outcome.message);
    focusFirst(mapped);
  }

  return (
    <form onSubmit={submit} noValidate aria-label={editing ? "Edit activity" : "Log activity"} className="form-grid">
      {failure && <p id={fieldId("message")} tabIndex={-1} className="form-error" role="alert">{failure}</p>}
      {picking && (
        <div className="field">
          <SearchableSelect id={pickerId} label="Organization (required)" noun="organization" required search={assignedOrgSearch}
            onChange={(o) => { setOrgId(o?.id ?? ""); set("contactId", ""); }} />
          {err("organization_id")}
        </div>
      )}
      <div className="field">
        <label htmlFor={fieldId("channel")}>Channel (required)</label>
        <select id={fieldId("channel")} value={draft.channel}
          onChange={(e) => setDraft((d) => ({ ...d, channel: e.target.value as Channel, direction: needsDirection(e.target.value as Channel) ? d.direction : null }))}>
          {CHANNELS.map((c) => <option key={c} value={c}>{CHANNEL_LABEL[c]}</option>)}
        </select>
      </div>
      {needsDirection(draft.channel) && (
        <fieldset className="field" aria-describedby={errors.direction ? errorId("direction") : undefined}>
          <legend>Direction (required)</legend>
          {(Object.keys(DIRECTION_LABEL) as Direction[]).map((d) => (
            <label key={d} style={{ display: "flex", gap: 6, alignItems: "center", minHeight: 44 }}>
              <input id={`${fieldId("direction")}-${d}`} type="radio" name={fieldId("direction")} value={d} checked={draft.direction === d}
                onChange={() => set("direction", d)} />
              {DIRECTION_LABEL[d]}
            </label>
          ))}
          {err("direction")}
        </fieldset>
      )}
      <div className="field">
        <label htmlFor={fieldId("occurred_at")}>When (required)</label>
        <input id={fieldId("occurred_at")} type="datetime-local" value={draft.occurredLocal} max={toLocalInput(new Date().toISOString())}
          aria-invalid={errors.occurred_at ? true : undefined} aria-describedby={`${fieldId("occurred_at")}-hint${errors.occurred_at ? ` ${errorId("occurred_at")}` : ""}`}
          onChange={(e) => set("occurredLocal", e.target.value)} />
        <p id={`${fieldId("occurred_at")}-hint`} className="field-hint">Your local time. Up to {BACKDATE_DAYS} days back.</p>
        {err("occurred_at")}
      </div>
      <div className="field">
        <label htmlFor={fieldId("contact_id")}>Contact</label>
        <select id={fieldId("contact_id")} value={draft.contactId} onChange={(e) => set("contactId", e.target.value)} {...described("contact_id")}>
          <option value="">No contact</option>
          {options.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        {err("contact_id")}
      </div>
      <div className="field">
        <label htmlFor={fieldId("note")}>Note</label>
        <textarea id={fieldId("note")} value={draft.note} maxLength={NOTE_MAX} rows={3} onChange={(e) => set("note", e.target.value)}
          aria-invalid={errors.note ? true : undefined} aria-describedby={`${fieldId("note")}-hint ${fieldId("note")}-count${errors.note ? ` ${errorId("note")}` : ""}`} />
        <p id={`${fieldId("note")}-hint`} className="field-hint">Everyone who can see this organization can read this note.</p>
        <p id={`${fieldId("note")}-count`} className="muted">{draft.note.length} / {NOTE_MAX}</p>
        {err("note")}
      </div>
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : editing ? "Save changes" : "Save activity"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}
```

- [ ] **Step 7b: Let the picker say "organizations"** — `apps/web/components/SearchableSelect.tsx` lines 13-14 (the noun is only used in
  status text; no behaviour change):

```tsx
export type Noun = "student" | "application" | "school" | "candidate" | "manager" | "BDM" | "organization";
const PLURAL: Record<Noun, string> = { student: "students", application: "applications", school: "schools", candidate: "candidates", manager: "managers", BDM: "BDMs", organization: "organizations" };
```

- [ ] **Step 8: Run the form test** — expected PASS. If the "Direction (required)" group query fails, check that the `<fieldset>`
  has the `<legend>` as its first child (that gives the group its name).

- [ ] **Step 9: Write the failing item test** — `apps/web/tests/components/BdmActivityItem.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmActivityItem from "@/components/BdmActivityItem";
import type { Activity } from "@/lib/bdmActivities";

const res = (body: unknown, status = 200) => new Response(body === null ? null : JSON.stringify(body), { status });
const item = (over: Partial<Activity> = {}): Activity => ({
  id: "a1", organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college" }, bdm: { id: "b1", full_name: "Asha" },
  contact_id: null, contact_name: "Dr Rao", contact_removed: true, channel: "whatsapp", direction: "inbound", occurred_at: "2026-10-03T05:00:00Z",
  note: "Sent brochure", created_at: "2026-10-03T05:00:00Z", updated_at: "2026-10-03T05:00:00Z", permissions: { can_change: true }, ...over,
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmActivityItem (bdm-009 §6.3)", () => {
  it("shows channel, direction, removed contact, logger and note; org link only when asked", () => {
    const { rerender } = render(<BdmActivityItem activity={item()} onChanged={vi.fn()} onDeleted={vi.fn()} />);
    expect(screen.getByText("WhatsApp · Incoming")).toBeInTheDocument();
    expect(screen.getByText(/Dr Rao \(removed\)/)).toBeInTheDocument();
    expect(screen.getByText(/Asha/)).toBeInTheDocument();
    expect(screen.getByText("Sent brochure")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "St Mary" })).toBeNull();
    rerender(<BdmActivityItem activity={item()} showOrganization orgBasePath="/bdm/organizations" onChanged={vi.fn()} onDeleted={vi.fn()} />);
    expect(screen.getByRole("link", { name: "St Mary" })).toHaveAttribute("href", "/bdm/organizations/o1");
  });

  it("shows markup in a note as text (AC13, §12.3 S5)", () => {
    const { container } = render(<BdmActivityItem activity={item({ note: "<script>alert(1)</script><b>x</b>" })} onChanged={vi.fn()} onDeleted={vi.fn()} />);
    expect(screen.getByText("<script>alert(1)</script><b>x</b>")).toBeInTheDocument();
    expect(container.querySelector("script, b")).toBeNull();
  });

  it("hides Edit and Delete without can_change", () => {
    render(<BdmActivityItem activity={item({ permissions: { can_change: false } })} onChanged={vi.fn()} onDeleted={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Edit|Delete/ })).toBeNull();
  });

  it("deletes after a confirm", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(null, 204))));
    const onDeleted = vi.fn();
    render(<BdmActivityItem activity={item()} onChanged={vi.fn()} onDeleted={onDeleted} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("a1"));
  });

  it("a 409 makes the item read-only with the reason; a 404 removes it", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Only today's activities can be changed" }, 409))));
    const onChanged = vi.fn();
    render(<BdmActivityItem activity={item()} onChanged={onChanged} onDeleted={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only today's activities can be changed");
    expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ permissions: { can_change: false } }));
    cleanup();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Activity not found" }, 404))));
    const onDeleted = vi.fn();
    render(<BdmActivityItem activity={item()} onChanged={vi.fn()} onDeleted={onDeleted} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("a1"));
  });
});
```

- [ ] **Step 10: Run it to verify it fails** — expected FAIL (module missing).

- [ ] **Step 11: Write the item** — `apps/web/components/BdmActivityItem.tsx`:

```tsx
"use client";
import Link from "next/link";
import { useState } from "react";

import BdmActivityForm from "@/components/BdmActivityForm";
import BdmConfirm from "@/components/BdmConfirm";
import LocalTime from "@/components/LocalTime";
import { sendRequest } from "@/lib/apiErrors";
import { type Activity, activityUrl, CHANNEL_LABEL, contactText, DIRECTION_LABEL } from "@/lib/bdmActivities";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-009 (spec §6.3): one activity in a timeline or a day list. Edit / Delete only when the API says `can_change` (owner, today).
// A 403 / 409 makes the item read-only with the reason; a 404 means it is already gone (there is no single-activity GET).
export default function BdmActivityItem({
  activity, showOrganization = false, orgBasePath = "/bdm/organizations", onChanged, onDeleted,
}: {
  activity: Activity;
  showOrganization?: boolean;
  orgBasePath?: string;
  onChanged: (a: Activity) => void;
  onDeleted: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const editId = `activity-${activity.id}-edit`;
  const deleteId = `activity-${activity.id}-delete`;
  const contact = contactText(activity);
  const heading = `${CHANNEL_LABEL[activity.channel]}${activity.direction ? ` · ${DIRECTION_LABEL[activity.direction]}` : ""}`;

  async function remove() {
    setBusy(true);
    setFailure(null);
    const outcome = await sendRequest(activityUrl(activity.id), { method: "DELETE" });
    setBusy(false);
    setConfirming(false);
    if (outcome.ok || outcome.status === 404) return onDeleted(activity.id);
    setFailure(outcome.message);
    if (outcome.status === 403 || outcome.status === 409) onChanged({ ...activity, permissions: { can_change: false } });
  }

  return (
    <li className="jtl-row">
      <div className="jtl-rail" aria-hidden="true"><span className="jtl-node" /></div>
      <div className="jtl-body">
        <div className="jtl-date"><LocalTime value={activity.occurred_at} time /></div>
        <div className="jtl-title">
          <span className="jtl-badge">{heading}</span>
          {showOrganization && (
            <> <Link href={`${orgBasePath}/${activity.organization.id}`} style={LINK_STYLE}>{activity.organization.name}</Link></>
          )}
        </div>
        <p className="jtl-detail" style={{ margin: 0 }}>
          {contact ? `${contact} · ` : ""}Logged by {activity.bdm.full_name}
        </p>
        {activity.note && <p className="jtl-detail" style={{ margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{activity.note}</p>}
        {failure && <p className="form-error" role="alert">{failure}</p>}
        {editing ? (
          <BdmActivityForm organizationId={activity.organization.id} activity={activity}
            onSaved={(a) => { setEditing(false); onChanged(a); focus(editId); }}
            onCancel={() => { setEditing(false); focus(editId); }} />
        ) : (
          activity.permissions.can_change && (
            <div className="actions">
              <button id={editId} type="button" className="btn secondary small" onClick={() => setEditing(true)}>Edit</button>
              <button id={deleteId} type="button" className="btn secondary small" onClick={() => setConfirming(true)} disabled={busy}>Delete</button>
            </div>
          )
        )}
        {confirming && (
          <BdmConfirm label="Confirm delete" confirmText="Yes, delete" busyText="Deleting…" cancelText="Keep it" busy={busy}
            onConfirm={() => void remove()} onCancel={() => { setConfirming(false); focus(deleteId); }}>
            Delete this {CHANNEL_LABEL[activity.channel].toLowerCase()}? It is removed from today&apos;s counts.
          </BdmConfirm>
        )}
      </div>
    </li>
  );
}
```

- [ ] **Step 12: Run the three web tests** — `npx vitest run tests/lib/bdmActivities.test.ts tests/components/BdmActivityForm.test.tsx
  tests/components/BdmActivityItem.test.tsx`. Expected: all PASS.

- [ ] **Step 13: Commit**

```bash
git add apps/web/lib/bdmActivities.ts apps/web/components/BdmActivityForm.tsx apps/web/components/BdmActivityItem.tsx apps/web/components/SearchableSelect.tsx apps/web/tests/lib/bdmActivities.test.ts apps/web/tests/components/BdmActivityForm.test.tsx apps/web/tests/components/BdmActivityItem.test.tsx
git commit -m "feat(bdm-009): activity form and item components"
```

---

### Task 7: Web — organization timeline on the profile

**Files:**
- Create: `apps/web/components/BdmActivityTimeline.tsx`
- Modify: `apps/web/components/BdmOrganizationDetail.tsx` (new optional prop; render the section after `<BdmOrganizationContacts>`)
- Modify: `apps/web/app/bdm/organizations/[id]/page.tsx`, `apps/web/app/bdm/manager/organizations/[id]/page.tsx` (fetch the
  first timeline page)
- Test: `apps/web/tests/components/BdmActivityTimeline.test.tsx`; extend `apps/web/tests/components/BdmOrganizationPages.test.tsx`

**Interfaces:**
- Consumes: Task 6 (`BdmActivityItem`, `BdmActivityForm`, `orgActivitiesUrl`, `placeNewest`, `TIMELINE_PAGE`, `Activity`).
- Produces: `BdmActivityTimeline({ organization: Organization, initial: Page<Activity> | null, canLog: boolean, orgBasePath: string })`;
  `BdmOrganizationDetail` gains `activities?: Page<Activity> | null` (undefined = no section; null = load failed).

- [ ] **Step 1: Write the failing timeline test** — `apps/web/tests/components/BdmActivityTimeline.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmActivityTimeline from "@/components/BdmActivityTimeline";
import type { Activity } from "@/lib/bdmActivities";
import type { Organization } from "@/lib/bdmOrganizations";

const res = (body: unknown, status = 200) => new Response(body === null ? null : JSON.stringify(body), { status });
const act = (id: string, at: string, over: Partial<Activity> = {}): Activity => ({
  id, organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college" }, bdm: { id: "b1", full_name: "Asha" },
  contact_id: null, contact_name: null, contact_removed: false, channel: "call", direction: "outbound", occurred_at: at, note: null,
  created_at: at, updated_at: at, permissions: { can_change: true }, ...over,
});
const org = { id: "o1", contacts: [{ id: "c1", name: "Dr Rao" }] } as unknown as Organization;
const page = (items: Activity[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmActivityTimeline (bdm-009 §6.3, AC6, AC11)", () => {
  it("shows the empty state", () => {
    render(<BdmActivityTimeline organization={org} initial={page([])} canLog={false} orgBasePath="/bdm/organizations" />);
    expect(screen.getByText("No activity logged yet.")).toBeInTheDocument();
  });

  it("a failed first load offers Try again, which reads the first page", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(page([act("a1", "2026-10-03T04:00:00Z")]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityTimeline organization={org} initial={null} canLog={false} orgBasePath="/bdm/organizations" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Activity couldn't be loaded.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(1));
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/bdm/organizations/o1/activities?limit=20&offset=0");
  });

  it("offers Log activity only when allowed and inserts the saved one in time order", async () => {
    const { rerender } = render(<BdmActivityTimeline organization={org} initial={page([act("a1", "2026-10-03T04:00:00Z")])} canLog={false} orgBasePath="/bdm/organizations" />);
    expect(screen.queryByRole("button", { name: "Log activity" })).toBeNull();
    rerender(<BdmActivityTimeline organization={org} initial={page([act("a1", "2026-10-03T04:00:00Z")])} canLog orgBasePath="/bdm/organizations" />);
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(act("a2", "2026-10-03T05:00:00Z", { channel: "visit", direction: null }), 201))));
    fireEvent.click(screen.getByRole("button", { name: "Log activity" }));
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "visit" } });
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    const list = await screen.findByRole("list", { name: "Activity" });
    await waitFor(() => expect(within(list).getAllByRole("listitem")[0]).toHaveTextContent("Visit"));
    expect(screen.getByRole("status")).toHaveTextContent("Activity logged.");
  });

  it("loads more with the next offset", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(page([act("a3", "2026-10-01T04:00:00Z")], 3, 2))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityTimeline organization={org} initial={page([act("a1", "2026-10-03T04:00:00Z"), act("a2", "2026-10-02T04:00:00Z")], 3)} canLog={false} orgBasePath="/bdm/organizations" />);
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(3));
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/bdm/organizations/o1/activities?limit=20&offset=2");
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });

  it("delete drops the total and keeps the next offset", async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(url.includes("offset=") ? res(page([act("a9", "2026-09-30T04:00:00Z")], 2, 1)) : res(null, 204)));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityTimeline organization={org} initial={page([act("a1", "2026-10-03T04:00:00Z"), act("a2", "2026-10-02T04:00:00Z")], 3)} canLog={false} orgBasePath="/bdm/organizations" />);
    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/bdm/organizations/o1/activities?limit=20&offset=1"));
  });
});
```

- [ ] **Step 2: Run it to verify it fails** — expected FAIL (module missing).

- [ ] **Step 3: Write the timeline** — `apps/web/components/BdmActivityTimeline.tsx`:

```tsx
"use client";
import { useState } from "react";

import BdmActivityForm from "@/components/BdmActivityForm";
import BdmActivityItem from "@/components/BdmActivityItem";
import { isPage, type Page } from "@/lib/apiErrors";
import { type Activity, orgActivitiesUrl, placeNewest } from "@/lib/bdmActivities";
import type { Organization } from "@/lib/bdmOrganizations";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-009 (spec §6.2, §6.3; V5): every BDM's activities on this organization, newest first, for anyone who can read it. Writes apply the
// returned activity locally (no router.refresh -- bdm-010 QA10-16). `null` = the server page could not load the first page.
export default function BdmActivityTimeline({
  organization, initial, canLog, orgBasePath,
}: { organization: Organization; initial: Page<Activity> | null; canLog: boolean; orgBasePath: string }) {
  const [items, setItems] = useState(initial?.items ?? []);
  const [total, setTotal] = useState(initial?.total ?? 0);
  const [loaded, setLoaded] = useState(initial !== null); // false: the server page couldn't read the first page (§12.2 F6)
  const [logging, setLogging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const logId = `org-${organization.id}-log-activity`;
  const statusId = `org-${organization.id}-activity-status`;

  async function load(offset: number) {
    setLoading(true);
    setFailure(null);
    try {
      const response = await fetch(orgActivitiesUrl(organization.id, offset));
      const data = response.ok ? await response.json() : null;
      if (!isPage<Activity>(data)) throw new Error("bad page");
      setItems((current) => (offset === 0 ? data.items : [...current, ...data.items.filter((a) => !current.some((c) => c.id === a.id))]));
      setTotal(data.total);
      setLoaded(true);
    } catch {
      setFailure(offset === 0 ? "Activity couldn't be loaded." : "More activity couldn't be loaded. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="action-card wide" aria-labelledby={`org-${organization.id}-activity`}>
      <div className="portal-title" style={{ gap: 12, flexWrap: "wrap" }}>
        <h3 id={`org-${organization.id}-activity`}>Activity</h3>
        {canLog && !logging && (
          <button id={logId} type="button" className="btn small" onClick={() => setLogging(true)}>Log activity</button>
        )}
      </div>
      <div id={statusId} tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      {logging && (
        <BdmActivityForm organizationId={organization.id} contacts={organization.contacts.map((c) => ({ id: c.id, name: c.name }))}
          onSaved={(a) => { setItems((current) => placeNewest(current, a)); setTotal((t) => t + 1); setLogging(false); setNotice("Activity logged."); focus(statusId); }}
          onCancel={() => { setLogging(false); focus(logId); }} />
      )}
      {!loaded ? (
        <div role="alert">
          <p className="form-error">Activity couldn&apos;t be loaded.</p>
          <button type="button" className="btn secondary small" onClick={() => void load(0)} disabled={loading}>{loading ? "Loading…" : "Try again"}</button>
        </div>
      ) : items.length === 0 ? (
        <p className="muted">No activity logged yet.</p>
      ) : (
        <ol className="jtl" aria-label="Activity" style={{ listStyle: "none", padding: 0 }}>
          {items.map((a) => (
            <BdmActivityItem key={a.id} activity={a} orgBasePath={orgBasePath}
              onChanged={(next) => { setItems((current) => placeNewest(current, next)); setNotice("Activity saved."); }}
              onDeleted={(id) => { setItems((current) => current.filter((x) => x.id !== id)); setTotal((t) => t - 1); setNotice("Activity deleted."); focus(statusId); }} />
          ))}
        </ol>
      )}
      {loaded && failure && <p className="form-error" role="alert">{failure}</p>}
      {loaded && items.length < total && (
        <button type="button" className="btn secondary small" onClick={() => void load(items.length)} disabled={loading}>{loading ? "Loading…" : "Load more"}</button>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Wire it into the detail** — `apps/web/components/BdmOrganizationDetail.tsx`:
  - Imports: `import BdmActivityTimeline from "@/components/BdmActivityTimeline";`, `import type { Page } from "@/lib/apiErrors";`,
    `import type { Activity } from "@/lib/bdmActivities";`.
  - Signature: add `activities` to the props:
    `{ initial, basePath, created = false, activities }: { initial: Organization; basePath: string; created?: boolean; activities?: Page<Activity> | null }`.
  - Directly after `<BdmOrganizationContacts organization={org} onChanged={changed} />` add:

```tsx
      {activities !== undefined && ( // bdm-009: the BDM view logs (assigned and not archived = can_edit); the manager view reads
        <BdmActivityTimeline organization={org} initial={activities} canLog={basePath === "/bdm/organizations" && p.can_edit} orgBasePath={basePath} />
      )}
```

- [ ] **Step 5: Fetch the first page in both organization pages, alongside the organization** (§12.2 F2). In
  `apps/web/app/bdm/organizations/[id]/page.tsx` (import `type Page` from `@/lib/apiErrors`, `type Activity, orgActivitiesUrl` from
  `@/lib/bdmActivities`, `isUuid` from `@/lib/bdmTravel`), start the timeline read **before** the organization `try` — it needs only
  the route id — and await it after:

```tsx
  // bdm-009 (spec §6.2, §12.2 F2): the first timeline page, read alongside the organization. It never rejects: a failure is null and
  // the section offers "Try again"; a malformed id isn't sent (the organization read answers "not found" for it).
  const timeline: Promise<Page<Activity> | null> = isUuid(id)
    ? serverApi<Page<Activity>>(orgActivitiesUrl(id)).catch(() => null)
    : Promise.resolve(null);
```

  then, after the organization `try/catch`: `const activities = organization ? await timeline : null;` and pass
  `activities={activities}` to `<BdmOrganizationDetail ...>`. Make the same changes in
  `apps/web/app/bdm/manager/organizations/[id]/page.tsx` (start `timeline` right after `const { id } = await params;`).

- [ ] **Step 6: Extend the page test** — in `apps/web/tests/components/BdmOrganizationPages.test.tsx`, add inside the existing
  organization-detail `describe` (reuse its `me` fixture and add a minimal org fixture if one isn't there):

```tsx
  it("bdm-009: passes the first activity page, or null when only that call fails", async () => {
    const id = "00000000-0000-4000-8000-000000000001";
    const organization = { id, code: "ORG-000001", name: "St Mary" };
    const activities = { items: [], total: 0, limit: 20, offset: 0 };
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/bdm/me") return me;
      if (p === `/api/v1/bdm/organizations/${id}`) return { organization };
      if (p.startsWith(`/api/v1/bdm/organizations/${id}/activities`)) return activities;
      throw new ApiError("x", 401);
    });
    let tree = elements(await BdmOrganization({ params: Promise.resolve({ id }), searchParams: Promise.resolve({}) }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props.activities).toEqual(activities);
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/bdm/me") return me;
      if (p === `/api/v1/bdm/organizations/${id}`) return { organization };
      throw new ApiError("boom", 500);
    });
    tree = elements(await BdmOrganization({ params: Promise.resolve({ id }), searchParams: Promise.resolve({}) }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props.activities).toBeNull();
  });
```

- [ ] **Step 7: Run the web tests** — `npx vitest run tests/components/BdmActivityTimeline.test.tsx
  tests/components/BdmOrganizationPages.test.tsx tests/components/BdmOrganizationDetail.test.tsx`. Expected: all PASS (the existing
  detail tests render without `activities`, so no section appears).

- [ ] **Step 8: Commit**

```bash
git add apps/web/components/BdmActivityTimeline.tsx apps/web/components/BdmOrganizationDetail.tsx "apps/web/app/bdm/organizations/[id]/page.tsx" "apps/web/app/bdm/manager/organizations/[id]/page.tsx" apps/web/tests/components/BdmActivityTimeline.test.tsx apps/web/tests/components/BdmOrganizationPages.test.tsx
git commit -m "feat(bdm-009): activity timeline on the organization profile"
```

---

### Task 8: Web — My Activities and team pages, counts, navigation

**Files:**
- Create: `apps/web/components/BdmActivityCounts.tsx`, `apps/web/components/BdmActivityDay.tsx`
- Create: `apps/web/app/bdm/activities/page.tsx`, `apps/web/app/bdm/activities/loading.tsx`
- Create: `apps/web/app/bdm/manager/activities/page.tsx`, `apps/web/app/bdm/manager/activities/loading.tsx`
- Modify: `apps/web/lib/navigation.ts` (`BDM_NAV`, `BDM_MANAGER_NAV`), `apps/web/tests/lib/navigation.bdm.test.ts`
- Test: `apps/web/tests/components/BdmActivityPages.test.tsx`

**Interfaces:**
- Consumes: Task 6 library and item; `isIsoDate`, `indiaToday` (`lib/bdmTravel`); `bdmNav`, `bdmManagerNav`; `PortalShell`,
  `PortalLoading`, `accessUnavailable`, `accessDenied`.
- Produces: `BdmActivityCounts({ counts: DayCounts })`; `BdmActivityDay({ initial: ActivityDayPage, url: string, canLog: boolean,
  orgBasePath: string })` where `url` is the API URL with `date` and filters but without `limit`/`offset`.

- [ ] **Step 1: Write the failing test** — `apps/web/tests/components/BdmActivityPages.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BdmActivityCounts from "@/components/BdmActivityCounts";
import BdmActivityDay from "@/components/BdmActivityDay";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ActivityDayPage } from "@/lib/bdmActivities";
import ManagerActivities from "@/app/bdm/manager/activities/page";
import MyActivities from "@/app/bdm/activities/page";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const me = {
  id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, division: "it",
  bdm_profile: { bdm_type: "college", employee_id: "E-1", designation: null, department: null, territory: null, reporting_manager: { id: "m1", full_name: "Meera", active: true } },
};
const B1 = "00000000-0000-4000-8000-0000000000b1"; // the manager page only sends a UUID as ?bdm
const counts = { day: "2026-10-03", by_channel: { call: 3, whatsapp: 1, email: 0, visit: 1, meeting: 0, other: 0 }, calls_made: 2, organizations_contacted: 2 };
const day = (over: Partial<ActivityDayPage> = {}): ActivityDayPage => ({ items: [], total: 0, limit: 50, offset: 0, counts, ...over });
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => vi.mocked(serverApi).mockReset());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("bdm-009 activity pages", () => {
  it("My Activities reads the chosen IST date and ignores a malformed one", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/bdm/me" ? me : p.includes("unread") ? { unread: 0 } : day()));
    const tree = elements(await MyActivities({ searchParams: Promise.resolve({ date: "2026-10-01" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/activities?date=2026-10-01&limit=50&offset=0");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("College BDM");
    expect(tree.find((el) => el.type === BdmActivityDay)!.props.canLog).toBe(true);
    vi.mocked(serverApi).mockClear();
    await MyActivities({ searchParams: Promise.resolve({ date: "20261-10-01" }) });
    expect(vi.mocked(serverApi).mock.calls.some(([p]) => String(p).includes("20261"))).toBe(false);
  });

  it("the team page passes the BDM filter and never logs", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/auth/me") return { id: "m1", full_name: "Meera", role: "bdm_manager" };
      if (p.startsWith("/api/v1/bdm/manager/team")) return { items: [{ id: B1, full_name: "Asha" }], total: 1, limit: 100, offset: 0 };
      if (p.includes("unread")) return { unread: 0 };
      return day();
    });
    const tree = elements(await ManagerActivities({ searchParams: Promise.resolve({ date: "2026-10-01", bdm: B1 }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/bdm/manager/activities?date=2026-10-01&bdm_user_id=${B1}&limit=50&offset=0`);
    const dayList = tree.find((el) => el.type === BdmActivityDay)!;
    expect(dayList.props.canLog).toBe(false);
    expect(dayList.props.emptyText).toBe("No activities from Asha on this day.");
  });

  it("a refused page shows the access card", async () => {
    vi.mocked(serverApi).mockImplementation(async () => {
      throw new ApiError("BDM role required", 403);
    });
    const tree = elements(await MyActivities({ searchParams: Promise.resolve({}) }));
    expect(tree.some((el) => el.props && el.props.message === "BDM role required")).toBe(true);
  });

  it("the counts strip shows every channel, calls made and organizations contacted", () => {
    render(<BdmActivityCounts counts={counts} />);
    for (const [label, value] of [["Call", "3"], ["WhatsApp", "1"], ["Email", "0"], ["Calls made", "2"], ["Organizations contacted", "2"]]) {
      expect(screen.getByText(label).nextElementSibling).toHaveTextContent(value);
    }
  });

  it("the day list shows the empty state and opens Log activity with the organization picker", () => {
    render(<BdmActivityDay header={<h2>My activities</h2>} initial={day()} url="/api/v1/bdm/activities?date=2026-10-03" canLog orgBasePath="/bdm/organizations" />);
    expect(screen.getByText("No activities on this day.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Log activity" }));
    expect(screen.getByRole("form", { name: "Log activity" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /Organization/ })).toBeInTheDocument();
  });

  it("the day list re-reads the day after a delete so the counts stay exact", async () => {
    const item = { id: "a1", organization: { id: "o1", code: "ORG-1", name: "St Mary", org_type: "college" }, bdm: { id: "b1", full_name: "Asha" },
      contact_id: null, contact_name: null, contact_removed: false, channel: "call", direction: "outbound", occurred_at: "2026-10-03T05:00:00Z",
      note: null, created_at: "2026-10-03T05:00:00Z", updated_at: "2026-10-03T05:00:00Z", permissions: { can_change: true } } as const;
    const after = day({ counts: { ...counts, by_channel: { ...counts.by_channel, call: 2 }, calls_made: 1 } });
    const fetchMock = vi.fn((url: string) => Promise.resolve(url.includes("/activities/a1") ? new Response(null, { status: 204 }) : res(after)));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityDay header={<h2>My activities</h2>} initial={day({ items: [item], total: 1 })} url="/api/v1/bdm/activities?date=2026-10-03" canLog orgBasePath="/bdm/organizations" />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/bdm/activities?date=2026-10-03&limit=50&offset=0"));
    await waitFor(() => expect(screen.getByText("Calls made").nextElementSibling).toHaveTextContent("1"));
    expect(screen.getByText("No activities on this day.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it to verify it fails** — expected FAIL (modules missing).

- [ ] **Step 3: Write the counts strip** — `apps/web/components/BdmActivityCounts.tsx`:

```tsx
import { CHANNEL_LABEL, CHANNELS, type DayCounts } from "@/lib/bdmActivities";

// bdm-009 (AC3): the whole day's counts from the API (never summed from the visible page), on AGN-018's KPI tiles (§12.2 F1:
// one column on phones, two from 768 px, four from 1024 px). `busy` marks a re-read in progress; the old numbers stay visible.
export default function BdmActivityCounts({ counts, busy = false }: { counts: DayCounts; busy?: boolean }) {
  const tiles: [string, number][] = [
    ["Calls made", counts.calls_made],
    ["Organizations contacted", counts.organizations_contacted],
    ...CHANNELS.map((c): [string, number] => [CHANNEL_LABEL[c], counts.by_channel[c] ?? 0]),
  ];
  return (
    <dl className="kpi-grid" aria-label="Day counts" aria-busy={busy || undefined}>
      {tiles.map(([label, value]) => (
        <div className="kpi-tile" key={label}>
          <dt>{label}</dt>
          <dd className="kpi-value">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
```

- [ ] **Step 4: Write the day list** — `apps/web/components/BdmActivityDay.tsx`:

```tsx
"use client";
import { type ReactNode, useState } from "react";

import BdmActivityCounts from "@/components/BdmActivityCounts";
import BdmActivityForm from "@/components/BdmActivityForm";
import BdmActivityItem from "@/components/BdmActivityItem";
import { type ActivityDayPage, DAY_PAGE, isDayPage } from "@/lib/bdmActivities";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-009 (spec §6.2, §12.2 F3/F7/F8): one IST day of activities with its counts, under the page's own title (`header`), with Log
// activity among the title's actions. After any write the day is re-read (first page) so the counts stay exact; while it re-reads,
// the old list and counts stay visible and are marked busy. "Load more" appends the next page.
export default function BdmActivityDay({
  header, initial, url, canLog, orgBasePath, emptyText = "No activities on this day.",
}: { header: ReactNode; initial: ActivityDayPage; url: string; canLog: boolean; orgBasePath: string; emptyText?: string }) {
  const [day, setDay] = useState(initial);
  const [logging, setLogging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const sep = url.includes("?") ? "&" : "?";

  async function read(offset: number, append: boolean, text?: string) {
    setBusy(true);
    setFailure(null);
    try {
      const response = await fetch(`${url}${sep}limit=${DAY_PAGE}&offset=${offset}`);
      const data = response.ok ? await response.json() : null;
      if (!isDayPage(data)) throw new Error("bad page");
      setDay((current) => (append ? { ...data, items: [...current.items, ...data.items.filter((a) => !current.items.some((c) => c.id === a.id))] } : data));
      if (text) setNotice(text);
    } catch {
      setFailure("The day couldn't be refreshed. Reload the page to see the latest counts.");
    } finally {
      setBusy(false);
      focus("activity-day-status");
    }
  }

  return (
    <>
      <div className="portal-title">
        <div>{header}</div>
        {canLog && !logging && (
          <button id="activity-day-log" type="button" className="btn" onClick={() => setLogging(true)}>Log activity</button>
        )}
      </div>
      {logging && (
        <section className="action-card wide" aria-label="Log activity">
          <BdmActivityForm onSaved={() => { setLogging(false); void read(0, false, "Activity logged."); }} onCancel={() => { setLogging(false); focus("activity-day-log"); }} />
        </section>
      )}
      <BdmActivityCounts counts={day.counts} busy={busy} />
      <div id="activity-day-status" tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {day.items.length === 0 ? (
        <p className="empty">{emptyText}</p>
      ) : (
        <ol className="jtl" aria-label="Activities" aria-busy={busy || undefined} style={{ listStyle: "none", padding: 0 }}>
          {day.items.map((a) => (
            <BdmActivityItem key={a.id} activity={a} showOrganization orgBasePath={orgBasePath}
              onChanged={() => void read(0, false, "Activity saved.")} onDeleted={() => void read(0, false, "Activity deleted.")} />
          ))}
        </ol>
      )}
      {day.items.length < day.total && (
        <button type="button" className="btn secondary small" disabled={busy} onClick={() => void read(day.items.length, true)}>{busy ? "Loading…" : "Load more"}</button>
      )}
    </>
  );
}
```

Note: `BdmActivityItem` calls `onChanged` with a read-only copy after a 403/409; re-reading the day in that case is correct too (the
API decides `can_change`).

- [ ] **Step 5: Write the BDM page** — `apps/web/app/bdm/activities/page.tsx`:

```tsx
import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmActivityDay from "@/components/BdmActivityDay";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { ACTIVITIES_URL, type ActivityDayPage, DAY_PAGE } from "@/lib/bdmActivities";
import { bdmNav } from "@/lib/bdmNav";
import { indiaToday, isIsoDate } from "@/lib/bdmTravel";
import { BDM_SIGN_IN } from "@/lib/navigation";

const PATH = "/bdm/activities";

// bdm-009 (spec §6.2): my activities on one IST day with that day's counts. The date lives in the URL (a plain GET form, no JS); a
// malformed date is ignored (today), a future one is refused by the API.
export default async function MyActivitiesPage({ searchParams }: { searchParams: Promise<{ date?: string }> }) {
  const nav = bdmNav(); // the unread badge, read alongside the page's own data (never rejects)
  const raw = (await searchParams).date;
  const today = indiaToday();
  const chosen = raw && isIsoDate(raw) ? raw : today;
  const url = `${ACTIVITIES_URL}?date=${chosen}`;
  let me: BdmMe, day: ActivityDayPage;
  try {
    [me, day] = await Promise.all([serverApi<BdmMe>("/api/v1/bdm/me"), serverApi<ActivityDayPage>(`${url}&limit=${DAY_PAGE}&offset=0`)]);
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  return (
    <PortalShell nav={await nav} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        {/* A BDM can log from any day's page: backdating is allowed, and the API applies the 7-day rule. */}
        <BdmActivityDay
          key={chosen}
          header={
            <>
              <div className="eyebrow">Activities</div>
              <h2>My activities</h2>
              <p className="muted">Calls, WhatsApp messages, emails, visits and meetings you logged. You can change an entry on the day it happened.</p>
              <form className="analytics-form" method="get" action={PATH} aria-label="Choose a day">
                <div className="field">
                  <label htmlFor="activity-date">Day</label>
                  <input id="activity-date" type="date" name="date" defaultValue={chosen} max={today} />
                </div>
                <button className="btn secondary" type="submit">Show</button>
              </form>
            </>
          }
          initial={day}
          url={url}
          canLog
          orgBasePath="/bdm/organizations"
        />
      </div>
    </PortalShell>
  );
}
```

- [ ] **Step 6: Write the team page** — `apps/web/app/bdm/manager/activities/page.tsx`:

```tsx
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmActivityDay from "@/components/BdmActivityDay";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { type ActivityDayPage, DAY_PAGE, TEAM_ACTIVITIES_URL } from "@/lib/bdmActivities";
import { bdmManagerNav } from "@/lib/bdmNav";
import { indiaToday, isIsoDate, isUuid } from "@/lib/bdmTravel";
import type { User } from "@/lib/types";

const PATH = "/bdm/manager/activities";

// bdm-009 (spec §6.2): the team's activities on one IST day, optionally for one BDM. Read-only (managers do not log, Q-17).
export default async function ManagerActivitiesPage({ searchParams }: { searchParams: Promise<{ date?: string; bdm?: string }> }) {
  const nav = bdmManagerNav();
  const sp = await searchParams;
  const today = indiaToday();
  const chosen = sp.date && isIsoDate(sp.date) ? sp.date : today;
  const bdm = sp.bdm && isUuid(sp.bdm) ? sp.bdm : null;
  const url = `${TEAM_ACTIVITIES_URL}?date=${chosen}${bdm ? `&bdm_user_id=${bdm}` : ""}`;
  let user: User, team: Page<{ id: string; full_name: string }>, day: ActivityDayPage;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
    [team, day] = await Promise.all([
      serverApi<Page<{ id: string; full_name: string }>>("/api/v1/bdm/manager/team?limit=100&offset=0"),
      serverApi<ActivityDayPage>(`${url}&limit=${DAY_PAGE}&offset=0`),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const chosenName = bdm ? team.items.find((b) => b.id === bdm)?.full_name ?? null : null; // §12.2 F7
  return (
    <PortalShell nav={await nav} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <BdmActivityDay
          key={`${chosen}-${bdm ?? "all"}`}
          header={
            <>
              <div className="eyebrow">Activities</div>
              <h2>Team activities</h2>
              <p className="muted">What your BDMs logged on the chosen day, with that day&apos;s counts.</p>
              <form className="analytics-form" method="get" action={PATH} aria-label="Filter activities">
                <div className="field">
                  <label htmlFor="team-activity-date">Day</label>
                  <input id="team-activity-date" type="date" name="date" defaultValue={chosen} max={today} />
                </div>
                <div className="field">
                  <label htmlFor="team-activity-bdm">BDM</label>
                  <select id="team-activity-bdm" name="bdm" defaultValue={bdm ?? ""}>
                    <option value="">Everyone</option>
                    {team.items.map((b) => <option key={b.id} value={b.id}>{b.full_name}</option>)}
                  </select>
                </div>
                <button className="btn secondary" type="submit">Show</button>
              </form>
            </>
          }
          initial={day}
          url={url}
          canLog={false}
          orgBasePath="/bdm/manager/organizations"
          emptyText={chosenName ? `No activities from ${chosenName} on this day.` : "No activities on this day."}
        />
      </div>
    </PortalShell>
  );
}
```

`/api/v1/bdm/manager/team` (bdm-001, `api/bdm.py:72`) takes `limit` (max 100) / `offset` and returns `{items: [{id, full_name, ...}]}`
ordered by name. A team over 100 BDMs would list only the first 100 in the select; recorded as accepted (no team is that size).

- [ ] **Step 7: Loading skeletons** — `apps/web/app/bdm/activities/loading.tsx`:

```tsx
import PortalLoading from "@/components/PortalLoading";
import { BDM_NAV } from "@/lib/navigation";

export default function Loading() {
  return <PortalLoading nav={BDM_NAV} label="your activities" />;
}
```

`apps/web/app/bdm/manager/activities/loading.tsx`:

```tsx
import PortalLoading from "@/components/PortalLoading";
import { BDM_MANAGER_NAV } from "@/lib/navigation";

export default function Loading() {
  return <PortalLoading nav={BDM_MANAGER_NAV} label="team activities" />;
}
```

- [ ] **Step 8: Navigation** — `apps/web/lib/navigation.ts`: insert `{ label: "Activities", href: "/bdm/activities" }` after
  Organizations in `BDM_NAV`, and `{ label: "Activities", href: "/bdm/manager/activities" }` after Organizations in
  `BDM_MANAGER_NAV`; extend the comment above them with "bdm-009: Activities in both." Update
  `apps/web/tests/lib/navigation.bdm.test.ts` expected arrays:

```ts
    expect(BDM_NAV.map((x) => x.href)).toEqual(["/bdm/my-day", "/bdm/organizations", "/bdm/activities", "/bdm/travel", "/bdm/notifications", "/bdm/profile"]);
    expect(BDM_MANAGER_NAV.map((x) => x.href)).toEqual([
      "/bdm/manager/dashboard", "/bdm/manager/team", "/bdm/manager/organizations", "/bdm/manager/activities", "/bdm/manager/approvals",
      "/bdm/manager/notifications",
    ]);
```

- [ ] **Step 9: Run the web BDM set** — `npx vitest run tests/components/BdmActivity*.test.tsx tests/lib/bdmActivities.test.ts
  tests/lib/navigation.bdm.test.ts tests/components/BdmOrganization*.test.tsx tests/components/BdmPages.test.tsx`. Expected: all PASS.

- [ ] **Step 10: Type, lint, build** — web command with `sh -c "npx tsc --noEmit && npx eslint app components lib tests && npx next build"`.
  Expected: no errors.

- [ ] **Step 11: Commit**

```bash
git add apps/web/components/BdmActivityCounts.tsx apps/web/components/BdmActivityDay.tsx apps/web/app/bdm/activities apps/web/app/bdm/manager/activities apps/web/lib/navigation.ts apps/web/tests/lib/navigation.bdm.test.ts apps/web/tests/components/BdmActivityPages.test.tsx
git commit -m "feat(bdm-009): My Activities and team activity pages with day counts"
```

---

### Task 9: End to end (Playwright)

**Files:**
- Create: `apps/web/tests/e2e/bdm-009-activities.spec.ts`

**Interfaces:**
- Consumes: `E2E_PASSWORD`, `activateWithToken` (`tests/e2e/helpers/welcome`); the running stack (the user starts it).

- [ ] **Step 1: Write the spec** — `apps/web/tests/e2e/bdm-009-activities.spec.ts`:

```ts
import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-009 (AC1, AC3, AC4, AC6, AC12): a College BDM logs a call and a visit on an organization, sees them on the timeline and in the day
// counts, edits and deletes one; the manager sees the team's day; keyboard-only logging; nothing overflows at 375 px.
test.describe.configure({ timeout: 120_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function noOverflow(page: Page) {
  for (const width of [320, 375]) { // §12.2 F9
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
}

test("BDM activity log: log, timeline, counts, edit, delete, manager view", async ({ page }) => {
  const stamp = Date.now();
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm009-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm009-b-${stamp}@example.local`,
            bdm_profile: { bdm_type: "college", employee_id: `E2E9-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  const created = await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", role: "principal" }] },
  });
  const org = (await created.json()).organization;

  // AC1 + AC6: log a call on the profile; it shows on the timeline.
  await page.goto(`/bdm/organizations/${org.id}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Log activity" }).click();
  await page.getByLabel("Outgoing").check();
  await page.getByLabel("Contact").selectOption({ label: "Dr Rao" });
  await page.getByLabel("Note").fill("Discussed the MoU");
  await page.getByRole("button", { name: "Save activity" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Activity logged." })).toBeVisible();
  const timeline = page.getByRole("list", { name: "Activity" });
  await expect(timeline.getByText("Call · Outgoing")).toBeVisible();
  await expect(timeline.getByText("Discussed the MoU")).toBeVisible();

  // a visit, keyboard only (AC12)
  await page.getByRole("button", { name: "Log activity" }).focus();
  await page.keyboard.press("Enter");
  await page.getByLabel("Channel (required)").focus();
  await page.getByLabel("Channel (required)").selectOption("visit"); // a focused native select, as the keyboard would set it
  await page.getByRole("button", { name: "Save activity" }).focus();
  await page.keyboard.press("Enter");
  await expect(timeline.getByText("Visit", { exact: true })).toBeVisible();

  // AC3: the day's counts
  await page.getByRole("link", { name: "Activities" }).first().click();
  await page.waitForURL("**/bdm/activities");
  const counts = page.getByLabel("Day counts");
  await expect(counts.getByText("Call", { exact: true }).locator("xpath=following-sibling::dd")).toHaveText("1");
  await expect(counts.getByText("Visit", { exact: true }).locator("xpath=following-sibling::dd")).toHaveText("1");
  await expect(counts.getByText("Organizations contacted").locator("xpath=following-sibling::dd")).toHaveText("1");

  // AC4: edit today's call, delete the visit; counts follow
  const list = page.getByRole("list", { name: "Activities" });
  await list.getByRole("listitem").filter({ hasText: "Call" }).getByRole("button", { name: "Edit" }).click();
  await page.getByLabel("Note").fill("MoU draft next week");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(list.getByText("MoU draft next week")).toBeVisible();
  await list.getByRole("listitem").filter({ hasText: "Visit" }).getByRole("button", { name: "Delete" }).click();
  await page.getByRole("button", { name: "Yes, delete" }).click();
  await expect(counts.getByText("Visit", { exact: true }).locator("xpath=following-sibling::dd")).toHaveText("0");

  await noOverflow(page);
  await page.goto(`/bdm/organizations/${org.id}`);
  await noOverflow(page);

  // the manager sees the team's day
  await signIn(page, "admin", manager.email, E2E_PASSWORD, "/bdm/manager/dashboard");
  await page.goto("/bdm/manager/activities");
  await expect(page.getByRole("list", { name: "Activities" }).getByText("MoU draft next week")).toBeVisible();
  await expect(page.getByRole("button", { name: /Edit|Delete|Log activity/ })).toHaveCount(0);
  await noOverflow(page);
});
```

The manager landing path `/bdm/manager/dashboard` is the one bdm-002's spec waits for (`bdm-002-organization-crm.spec.ts:86`).

- [ ] **Step 2: Ask the user to start the stack**, then run (web container, `-e E2E_BASE_URL=http://host.docker.internal:<web port>`):
  `npx playwright test tests/e2e/bdm-009-activities.spec.ts --repeat-each=2`. Expected: 2 passed. Also re-run
  `tests/e2e/bdm-002-organization-crm.spec.ts` and `tests/e2e/bdm-010-travel.spec.ts` (neighbours: the org profile and the nav changed).

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/bdm-009-activities.spec.ts
git commit -m "test(bdm-009): end-to-end activity log journey"
```

---

### Task 10: Documentation and decision record

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append `DEC-SCOPE-065` after `DEC-SCOPE-064`)
- Modify: `docs/delivery/BDM_CRM_BACKLOG.md` (status line under `### bdm-009`)
- Modify: `docs/architecture/DATA_MODEL.md` (`bdm_activities`)
- Modify: `docs/quality/RTM.md` (bdm-009 rows)

- [ ] **Step 1: Decision record** — append to `PRODUCT_DECISION_REGISTER.md`, in the format of `DEC-SCOPE-063`, after `DEC-SCOPE-064` (AGN-022):

```markdown
---

### DEC-SCOPE-065 — BDM activity log (`bdm-009`)

**Question:** how do BDMs log calls, WhatsApp messages, emails, visits and meetings, who may log, see and change them, and how are the
day's counts defined (`BDM_CRM_BACKLOG.md` §4 bdm-009)?

**Evidence:** `EVID-016` (`BDM Functionalities.md`, `DERIVED_BLUEPRINT`) §4 Common "Activity" (1288–1298), §11 (371–397), Agent §G
(759–781), School §G (1000–1022); backlog decisions D9, Q-02, Q-13, Q-20 (`DERIVED_BLUEPRINT`).

**Resolution:** owner, in-session 2026-10-03 (`EXPLICIT_APPROVAL` — answers to structured questions and five design-section reviews):

- **V1** Only the organization's assigned BDM logs (out of type → 404, not assigned → 403, archived → 422).
- **V2** Channels: call, whatsapp, email, visit, meeting, other. No follow-up channel (bdm-008 tasks). Meetings in the daily report come
  from completed appointments (bdm-015); meeting / visit activities count only under their own channel.
- **V3** Appointment and task links are deferred to bdm-006 / bdm-008 (their own migrations and FKs).
- **V4** `occurred_at` not in the future, at most 7 IST days back; edit / delete only on the activity's IST day (`editable()`, which
  bdm-015 extends with the report lock).
- **V5** The organization timeline is visible to everyone who can read the organization.
- **V6** Direction (outbound / inbound) required for call, WhatsApp, email; empty otherwise. Calls made = outbound calls.
- **V7** Pages: org timeline + Log activity, `/bdm/activities`, `/bdm/manager/activities`.
- **V8** Delete is hard, with an audit row (ids and channel only).
- **V9** (Revision 2) A time up to 5 minutes after the server clock is saved as the server's now; more than 5 minutes ahead → 422.
- **V10** (Revision 2) At most 200 activities per BDM per IST day (409); a soft abuse bound.
- Defaults: super_admin reads only; the contact must belong to the organization and its name is kept after the contact is deleted
  (as bdm-006 A5); an edit cannot move an activity off today; no idempotency key (duplicate fixed by a same-day delete); no general
  rate limiter (as bdm-010). Notes are visible to every reader of the organization (the form says so). Retention / erasure of BDM data
  remains `NEEDS_CONFIRMATION` (as bdm-001 / 002 / 006).

**Status:** `EXPLICIT_APPROVAL`. Spec `docs/superpowers/specs/2026-10-03-bdm-009-activity-log-design.md`; migration
`0069_bdm_activities`.
```

- [ ] **Step 2: Backlog status line** — directly under `### bdm-009 — Activity log (call / WhatsApp / email / visit / meeting)`:

```markdown
> **Status (2026-10-03):** implemented on `feature/bdm-009-activities` (`DEC-SCOPE-065`, migration `0069_bdm_activities`). Channels
> exclude "follow-up" (V2); appointment / task links deferred to bdm-006 / bdm-008 (V3); backdate window 7 IST days and same-day edits
> (V4). AC4's "report submitted" lock is completed by bdm-015 through `editable()`. Spec:
> `docs/superpowers/specs/2026-10-03-bdm-009-activity-log-design.md`.
```

- [ ] **Step 3: DATA_MODEL, RTM and API_CONTRACT** — open each file, find the bdm-010 entry, and add the same shape for bdm-009:
  - `DATA_MODEL.md`: the `bdm_activities` table (columns, checks, indexes, FKs from spec §4.1).
  - `RTM.md`: one row per AC1–AC13 mapping to the test files listed in spec §8 (AC13 → `test_bdm_009_activities.py`
    `test_abuse_cases_server_owned_fields_and_markup`, `test_bdm_009_scope.py`, `BdmActivityItem.test.tsx`).
  - `API_CONTRACT.md` (after the bdm-010 addendum, `API_CONTRACT.md:391`): "**`bdm-009` / `DEC-SCOPE-065`** — BDM activity log." List
    the six routes (spec §5.3), the status table (spec §12.1 A4), the retry semantics (A3: POST not retry-safe, PATCH idempotent,
    second DELETE → 404), V9 and V10, and "no existing route or field changes" (A10).

- [ ] **Step 4: Commit**

```bash
git add docs/decisions/PRODUCT_DECISION_REGISTER.md docs/delivery/BDM_CRM_BACKLOG.md docs/architecture/DATA_MODEL.md docs/architecture/API_CONTRACT.md docs/quality/RTM.md
git commit -m "docs(bdm-009): DEC-SCOPE-065, backlog status, data model and RTM"
```

---

### Task 11: Verification gates

**Files:** none (evidence only).

- [ ] **Step 1: Recheck `main`** — `git fetch origin` and `git log --oneline HEAD..origin/main`. If a migration `0069_*` or
  `DEC-SCOPE-065` landed, merge `main`, renumber this branch's migration / DEC (file name, `revision`, test `BASE`/`HEAD`, docs),
  and confirm `alembic heads` prints one line.
- [ ] **Step 2: Backend lite set** — `<P>` = LITE (see "How to run tests"). Expected: all pass. Record the count.
- [ ] **Step 3: Backend static** — api-test container: `ruff check app tests && mypy app` — no new mypy errors over main's 342.
- [ ] **Step 4: Web set + static + build** — Task 8 Step 9 and Step 10 commands. Expected: pass / clean.
- [ ] **Step 5: Playwright** — Task 9 Step 2 (bdm-009 with `--repeat-each=2`, plus bdm-002 and bdm-010 specs).
- [ ] **Step 6: Browser check** — on the running stack, walk AC1–AC12 in a real browser at 1280 px and 375 px (keyboard-only for one
  log), and record findings in `docs/quality/BDM-009_BROWSER_QA_2026-10-03.md`.
- [ ] **Step 7: Report** — list exactly which test files ran and their counts; state that the full backend suite was not run (the
  owner runs it).
```
