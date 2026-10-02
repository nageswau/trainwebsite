# bdm-001 — BDM and BDM Manager Roles, Profile, Provisioning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** add the `bdm` and `bdm_manager` roles, a 1:1 BDM profile, admin provisioning through the existing set-password flow, the BDM and manager landing pages, and an admin BDM page. This is bdm-001, AC01–AC16.

**Architecture:**
- `POST/PATCH /admin/users` gains a role-gated branch, following the existing `role == "agent"` branch.
- A new `bdm_profiles` table, from migration `0058_bdm_profiles`.
- New code follows the flat module convention: `app/api/bdm.py` for routes, `app/services/bdm.py` for rules and scope, Pydantic models in `schemas.py`.
- Web: `ROLE_DASHBOARD_PATH` and middleware entries, server-rendered `/bdm/*` pages, and an `AdminBdm*` component set that follows the AGN-002 `AgentStaff*` split.

**Tech stack:** FastAPI, SQLAlchemy 2 (async), Alembic, Postgres, Pydantic v2; Next.js 15 (app router), React, vitest with Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-02-bdm-001-bdm-profile-design.md`, Revision 2. Read it alongside this plan.

## Global constraints

- Branch `feature/bdm-001-bdm-profile`, worktree `.claude/worktrees/bdm-001`. Cut from `main` `268d132`.
- Decision ID: **`DEC-SCOPE-052`**. Migration: **`0058_bdm_profiles`**, down_revision `0057_agent_applications`.
- `BDM_DIVISION = {"college": "it", "agent": "overseas", "school": "overseas"}`.
- `CREATOR_TYPES = {super_admin: all, it_admin: {college}, overseas_admin: {agent, school}}`. Only `super_admin` creates `bdm_manager`.
- Managers have **no** profile row. `bdm_type` can't be changed (PATCH with a different value → 422).
- Required at create: `bdm_type`, `employee_id` (1–40 characters, trimmed, no control characters, unique ignoring case) and `reporting_manager_user_id` (must be an active `bdm_manager`). Optional: designation, department, territory (≤ 120 characters each) and phone (existing column).
- Error bodies are FastAPI `{"detail": "<string>"}`. Fields are snake_case. Lists are `{items, total, limit, offset}` with `limit` defaulting to 50, at most 100, and `offset` ≥ 0.
- Contracts that must not change: `PATCH /admin/users` still returns `{"ok": true}`; the `/admin/users` payload stays an untyped dict; `GET /admin/users` is untouched; `auth.login` is untouched; set-password URLs are untouched.
- Additive keys that are **always present**: `POST /admin/users` → `bdm_profile` (null for roles other than BDM); `POST /auth/reset-password` → `login_portal` (`"admin"` for a `bdm_manager`, otherwise null).
- Logs carry IDs, route and type only. Never email, phone or Employee ID.
- Authorization uses the inline `User.role` checks and scope helpers. No `require_*` dependencies.
- No new dependencies, no new rate limiter.
- Tests run for real (pytest, vitest, Playwright). Only the **lite** set runs; the user runs the full suite separately.
- Don't start or stop the docker stack (the user controls it). One-off `run --rm` test containers are fine.

## Commands used by every task

```bash
# Worktree root (Windows form — a $PWD mount silently mounts a stale tree)
WT="C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/bdm-001"

# API tests (lite): pass the test paths in place of <PATHS>
docker compose -p bdm001 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "$WT/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <PATHS>"

# Web unit tests / typecheck
MSYS_NO_PATHCONV=1 docker compose -p bdm001 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps \
  -v "$WT/apps/web:/app" -v /app/node_modules web-test sh -c "npx vitest run <PATHS>"
MSYS_NO_PATHCONV=1 docker compose -p bdm001 ... web-test sh -c "npx tsc --noEmit && npx eslint <PATHS>"
```

If `alembic upgrade head` fails on a stale stamp, run `alembic stamp --purge 0057_agent_applications` and then `upgrade head`.

## Review focus

Inputs the spec implies but the acceptance criteria don't name directly. Each line has a test in the task that owns the code.

1. **Editing a BDM whose manager has since been deactivated** (other fields only) must still succeed. Only a *change* of manager is re-checked. Task 4 has the test `test_patch_other_fields_when_manager_inactive_succeeds`.
2. **A whitespace-padded Employee ID** (`"  E-1 "`) must be stored trimmed, and `"e-1"` must then collide with it (409). Task 3 has `test_employee_id_trimmed_and_case_insensitive`.
3. **`limit=0`, `limit=101` or `offset=-1`** on any list → 422, never a 500 and never an unbounded query. Task 5 has `test_list_bounds_are_422`.
4. **A `bdm_profile` that isn't an object** (a string, list or null) on create or PATCH → 422 with a field message, not a 500. Tasks 3 and 4 have `test_profile_not_an_object_is_422`.
5. **A signed-out visit to `/bdm/manager` with no trailing segment**, and `/bdmx`, must be handled correctly: `/bdm/manager` redirects to `/admin/login`, and `/bdmx` is not matched. Task 7 has `middleware.test.ts` cases.

---

## File map

| File | Responsibility | Task |
|---|---|---|
| `apps/api/app/models.py` | + `BdmProfile` | 1 |
| `apps/api/alembic/versions/0058_bdm_profiles.py` | new table, guarded, refusing downgrade | 1 |
| `apps/api/tests/test_bdm_001_migration.py` | chain, round trip, refusal | 1 |
| `apps/api/app/core/rbac.py` | + 2 roles | 2 |
| `apps/api/app/schemas.py` | + input and output models | 2 |
| `apps/api/app/services/bdm.py` | rules, locks, scope, shapes (no commit) | 2 |
| `apps/api/tests/test_bdm_001_service.py` | unit tests for the service and schemas | 2 |
| `apps/api/app/api/admin.py` | create and update branches | 3, 4 |
| `apps/api/tests/bdm001_helpers.py` | shared test builders | 3 |
| `apps/api/tests/test_bdm_001_profiles.py` | create, update and AC tests | 3, 4 |
| `apps/api/app/api/bdm.py` + `main.py` | 4 read routes | 5 |
| `apps/api/tests/test_bdm_001_reads.py` | read routes | 5 |
| `apps/api/app/api/auth.py` | `login_portal` | 6 |
| `apps/api/tests/test_bdm_001_reset_portal.py` | reset-password portal | 6 |
| `apps/web/lib/navigation.ts`, `middleware.ts`, `components/ResetPasswordForm.tsx`, `components/WorkflowPanel.tsx`, `app/admin/login/page.tsx`, `lib/bdm.ts` | web foundations | 7 |
| `apps/web/app/bdm/**`, `components/BdmProfileCard.tsx`, `components/BdmTeamTable.tsx` | BDM and manager pages | 8 |
| `apps/web/components/AdminBdm{Panel,CreateForm,Row,Page}.tsx`, `app/{admin,it/admin,overseas/admin}/bdms/page.tsx` | admin UI | 9 |
| `apps/web/tests/e2e/bdm-001-bdm-profile.spec.ts` | end-to-end journey | 10 |
| docs (register, backlog, RBAC matrix, role navigation) | traceability | 11 |

---

### Task 1: `BdmProfile` model and migration `0058_bdm_profiles`

**Files:**
- Modify: `apps/api/app/models.py` (add the class after `AuditLog`, about line 828)
- Create: `apps/api/alembic/versions/0058_bdm_profiles.py`
- Test: `apps/api/tests/test_bdm_001_migration.py`

**Interfaces:**
- Produces: `app.models.BdmProfile` with `id, user_id, bdm_type, employee_id, designation, department, territory, reporting_manager_user_id, created_at, updated_at`. Constraint and index names: `uq_bdm_profiles_user`, `ck_bdm_profiles_type`, `uq_bdm_profiles_employee_id` (on `lower(employee_id)`) and `ix_bdm_profiles_reporting_manager`.

- [ ] **Step 1: Write the failing migration test.** Copy the `isolated_db` / `_sql` scaffolding from `test_agn_008_migration.py`.

```python
"""bdm-001 -- migration 0058_bdm_profiles (spec §4). Round trip and refusal run in a throwaway database (AGN-008 pattern)."""

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
_spec = importlib.util.spec_from_file_location("_bdm_001_migration_0058", VERSIONS / "0058_bdm_profiles.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)
BASE = "0057_agent_applications"
USERS = "SELECT id, email, role, division FROM users ORDER BY id"


def test_migration_chains_after_0057_and_is_the_single_head():
    assert _migration.revision == "0058_bdm_profiles"
    assert _migration.down_revision == BASE
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    assert len(set(parents) - set(parents.values())) == 1


def test_model_matches_the_migration():
    from app.models import BdmProfile

    t = BdmProfile.__table__
    assert {c.name for c in t.columns} == {"id", "user_id", "bdm_type", "employee_id", "designation", "department", "territory", "reporting_manager_user_id", "created_at", "updated_at"}
    assert not t.c.employee_id.nullable and not t.c.reporting_manager_user_id.nullable and t.c.designation.nullable
    names = {i.name for i in t.indexes} | {c.name for c in t.constraints}
    assert {"uq_bdm_profiles_user", "ck_bdm_profiles_type", "uq_bdm_profiles_employee_id", "ix_bdm_profiles_reporting_manager"} <= names


@pytest.mark.asyncio
async def test_table_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    indexes = await conn.run_sync(lambda s: {i["name"]: i for i in inspect(s).get_indexes("bdm_profiles")})
    assert indexes["uq_bdm_profiles_employee_id"]["unique"]
    assert "ix_bdm_profiles_reporting_manager" in indexes


def _sql(url, sql, params=None, *, autocommit=False):
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
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"bdm001_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("manager", "bdm")}
        for key, role, division in (("manager", "bdm_manager", "global"), ("bdm", "counselor", "overseas")):
            _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
                 "VALUES (:id, :email, 'x', :name, :role, :division, true, true, 'en-GB', '{}')",
                 {"id": ids[key], "email": f"{key}-{name}@example.local", "name": key, "role": role, "division": division})
        yield {"cfg": cfg, "url": url, "ids": ids}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_users_identical(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, USERS)
    command.upgrade(cfg, "0058_bdm_profiles")
    command.upgrade(cfg, "0058_bdm_profiles")  # idempotent re-run
    assert _sql(url, USERS) == before
    command.downgrade(cfg, BASE)
    assert _sql(url, USERS) == before
    command.upgrade(cfg, "0058_bdm_profiles")
    assert _sql(url, USERS) == before


def test_constraints_hold_and_downgrade_refuses_while_profiles_exist(isolated_db):
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, "0058_bdm_profiles")
    insert = ("INSERT INTO bdm_profiles (id, user_id, bdm_type, employee_id, reporting_manager_user_id) "
              "VALUES (:id, :user, :type, :emp, :mgr)")
    with pytest.raises(Exception, match="ck_bdm_profiles_type"):
        _sql(url, insert, {"id": uuid.uuid4(), "user": ids["bdm"], "type": "it", "emp": "E1", "mgr": ids["manager"]})
    _sql(url, insert, {"id": uuid.uuid4(), "user": ids["bdm"], "type": "college", "emp": "E1", "mgr": ids["manager"]})
    with pytest.raises(Exception, match="uq_bdm_profiles_employee_id"):
        _sql(url, insert, {"id": uuid.uuid4(), "user": ids["manager"], "type": "agent", "emp": "e1", "mgr": ids["manager"]})
    with pytest.raises(Exception, match="profiles exist"):
        command.downgrade(cfg, BASE)
```

- [ ] **Step 2: Run it and confirm the RED state.**
Run: API tests with `<PATHS>` = `tests/test_bdm_001_migration.py`.
Expected: FAIL with `FileNotFoundError` for `0058_bdm_profiles.py`, or `ImportError: cannot import name 'BdmProfile'`.

- [ ] **Step 3: Add the model** to `models.py`, after `AuditLog`.

```python
class BdmProfile(Base, TimestampMixin):
    """bdm-001 (DEC-SCOPE-052): a BDM's §1 profile, 1:1 with a `bdm` user. Name, email, mobile and active stay on `users`.
    The reporting manager must be an active `bdm_manager` -- enforced in `services/bdm.py` under a row lock (no cross-table CHECK)."""

    __tablename__ = "bdm_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_bdm_profiles_user"),
        CheckConstraint("bdm_type IN ('agent', 'school', 'college')", name="ck_bdm_profiles_type"),
        Index("uq_bdm_profiles_employee_id", text("lower(employee_id)"), unique=True),
        Index("ix_bdm_profiles_reporting_manager", "reporting_manager_user_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    bdm_type: Mapped[str] = mapped_column(String(20))
    employee_id: Mapped[str] = mapped_column(String(40))
    designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    territory: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reporting_manager_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
```

- [ ] **Step 4: Add the migration**, `0058_bdm_profiles.py`.

```python
"""bdm-001 -- bdm_profiles (1:1 with a `bdm` user).

Revision ID: 0058_bdm_profiles
Revises: 0057_agent_applications

docs/superpowers/specs/2026-10-02-bdm-001-bdm-profile-design.md §4 (DEC-SCOPE-052). Adds one table; no existing row is read or
written. 0001 builds a fresh database from the current models, so creation is guarded (0055's idiom). downgrade() refuses while
profiles exist: they are the only record of each BDM's type and reporting manager.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0058_bdm_profiles"
down_revision = "0057_agent_applications"
branch_labels = None
depends_on = None

TABLE = "bdm_profiles"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("bdm_type", sa.String(20), nullable=False),
        sa.Column("employee_id", sa.String(40), nullable=False),
        sa.Column("designation", sa.String(120), nullable=True),
        sa.Column("department", sa.String(120), nullable=True),
        sa.Column("territory", sa.String(120), nullable=True),
        sa.Column("reporting_manager_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_bdm_profiles_user"),
        sa.CheckConstraint("bdm_type IN ('agent', 'school', 'college')", name="ck_bdm_profiles_type"),
    )
    op.create_index("uq_bdm_profiles_employee_id", TABLE, [sa.text("lower(employee_id)")], unique=True)
    op.create_index("ix_bdm_profiles_reporting_manager", TABLE, ["reporting_manager_user_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0058_bdm_profiles: BDM profiles exist. Remove them deliberately first.")
    op.drop_table(TABLE)
```

- [ ] **Step 5: Run the tests and confirm GREEN.** Same command. Expected: 6 passed.
- [ ] **Step 6: Commit** — `feat(bdm-001): bdm_profiles model and migration 0058`.

---

### Task 2: Roles, schemas and `services/bdm.py`

**Files:**
- Modify: `apps/api/app/core/rbac.py` (`PERMISSIONS`, after `psychometric_team`)
- Modify: `apps/api/app/schemas.py` (append a `# --- bdm-001 ---` block at the end)
- Create: `apps/api/app/services/bdm.py`
- Test: `apps/api/tests/test_bdm_001_service.py`

**Interfaces:**
- Consumes: `BdmProfile` (Task 1).
- Produces (`app.services.bdm`):
  - Constants: `BDM_TYPES`, `BDM_DIVISION`, `CREATOR_TYPES`.
  - `creatable_types(actor) -> frozenset[str]`
  - `require_creator_may(actor, bdm_type, route) -> None` (403)
  - `parse_profile_create(raw) -> BdmProfileCreate` (422)
  - `parse_profile_update(raw) -> BdmProfileUpdate` (422)
  - `async locked_active_manager(db, manager_id) -> User` (422)
  - `async flush_profile(db) -> None` (409 on a duplicate Employee ID)
  - `profile_snapshot(p) -> dict`
  - `profile_out(p, manager) -> dict`
  - `async bdm_context(db, user) -> BdmProfile` (403)
  - `require_manager(user) -> None` (403)
  - `team_filter(user) -> list`
  - `admin_type_filter(actor, bdm_type) -> list` (403)
- Produces (`app.schemas`): `BdmProfileCreate`, `BdmProfileUpdate`, `BdmManagerRef`, `BdmProfileOut`, `BdmMeOut`, `BdmTeamRow`, `BdmAdminRow`, `BdmManagerOption`, `BdmTeamPage`, `BdmAdminPage`, `BdmManagerPage`.

- [ ] **Step 1: Write the failing unit tests.**

```python
"""bdm-001 -- services/bdm.py and the profile schemas (spec §5.2, §5.3). Pure units; no HTTP."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.rbac import PERMISSIONS
from app.services import bdm

MGR = str(uuid.uuid4())


def _actor(role):
    return SimpleNamespace(id=uuid.uuid4(), role=role)


def test_roles_registered():
    assert PERMISSIONS["bdm"] == {"bdm:self"} and PERMISSIONS["bdm_manager"] == {"bdm:team"}


def test_division_map_and_creator_matrix():
    assert bdm.BDM_DIVISION == {"college": "it", "agent": "overseas", "school": "overseas"}
    assert bdm.creatable_types(_actor("super_admin")) == {"agent", "school", "college"}
    assert bdm.creatable_types(_actor("it_admin")) == {"college"}
    assert bdm.creatable_types(_actor("overseas_admin")) == {"agent", "school"}
    assert bdm.creatable_types(_actor("counselor")) == frozenset()


@pytest.mark.parametrize(("role", "bdm_type"), [("it_admin", "agent"), ("overseas_admin", "college"), ("counselor", "school")])
def test_creator_refusal_is_403_and_logged_without_pii(role, bdm_type, caplog):
    import logging

    logging.getLogger("app.bdm").disabled = False
    with caplog.at_level(logging.WARNING, logger="app.bdm"), pytest.raises(HTTPException) as exc:
        bdm.require_creator_may(_actor(role), bdm_type, "/api/v1/admin/users")
    assert exc.value.status_code == 403
    record = next(r for r in caplog.records if r.getMessage() == "bdm_creator_type_refused")
    assert set(record.extra_fields) == {"actor_id", "route", "bdm_type"}


def test_parse_create_trims_and_clears_blank_optionals():
    p = bdm.parse_profile_create({"bdm_type": "college", "employee_id": "  E-1 ", "designation": " ", "reporting_manager_user_id": MGR})
    assert p.employee_id == "E-1" and p.designation is None and str(p.reporting_manager_user_id) == MGR


@pytest.mark.parametrize("raw", [None, "x", [], 5])
def test_profile_not_an_object_is_422(raw):
    for parse in (bdm.parse_profile_create, bdm.parse_profile_update):
        with pytest.raises(HTTPException) as exc:
            parse(raw)
        assert exc.value.status_code == 422


@pytest.mark.parametrize(
    "patch",
    [
        {"bdm_type": "it"},
        {"employee_id": "   "},
        {"employee_id": "x" * 41},
        {"employee_id": "E\x07"},
        {"designation": "d" * 121},
        {"reporting_manager_user_id": "not-a-uuid"},
        {"user_id": MGR},
        {"surprise": 1},
    ],
)
def test_create_rejects_bad_fields_with_a_named_422(patch):
    raw = {"bdm_type": "college", "employee_id": "E-1", "reporting_manager_user_id": MGR, **patch}
    with pytest.raises(HTTPException) as exc:
        bdm.parse_profile_create(raw)
    assert exc.value.status_code == 422 and exc.value.detail.startswith("bdm_profile.")


def test_update_null_semantics():
    assert bdm.parse_profile_update({"territory": None}).model_dump(exclude_unset=True) == {"territory": None}
    assert bdm.parse_profile_update({"territory": ""}).territory is None
    for key in ("employee_id", "reporting_manager_user_id", "bdm_type"):
        with pytest.raises(HTTPException) as exc:
            bdm.parse_profile_update({key: None})
        assert exc.value.status_code == 422
    assert bdm.parse_profile_update({}).model_dump(exclude_unset=True) == {}


def test_scope_helpers():
    manager, sa_ = _actor("bdm_manager"), _actor("super_admin")
    assert bdm.team_filter(sa_) == [] and len(bdm.team_filter(manager)) == 1
    for role in ("bdm", "counselor", "it_admin"):
        with pytest.raises(HTTPException) as exc:
            bdm.require_manager(_actor(role))
        assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        bdm.admin_type_filter(_actor("it_admin"), "agent")
    assert exc.value.status_code == 403
    assert len(bdm.admin_type_filter(_actor("it_admin"), None)) == 1
```

- [ ] **Step 2: Run it and confirm RED.** `<PATHS>` = `tests/test_bdm_001_service.py`. Expected: `ModuleNotFoundError: app.services.bdm`.

- [ ] **Step 3: Implement.** First, the `rbac.py` entries:

```python
    # bdm-001 (DEC-SCOPE-052): BDM CRM. Type/own/team scope is enforced in services/bdm.py, not by these bundles alone.
    "bdm": {"bdm:self"},
    "bdm_manager": {"bdm:team"},
```

Then the block appended to `schemas.py`. It needs `import re` at the top, if that isn't already imported.

```python
# --- bdm-001 (DEC-SCOPE-052): BDM profile -------------------------------------------------------------------------------
BdmType = Literal["agent", "school", "college"]
_BDM_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _bdm_employee_id(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Employee ID is required")
    if len(value) > 40:
        raise ValueError("Employee ID must be at most 40 characters")
    if _BDM_CONTROL.search(value):
        raise ValueError("Employee ID contains invalid characters")
    return value


def _bdm_optional(value: str | None) -> str | None:
    return (value.strip() or None) if value is not None else None


BdmEmployeeId = Annotated[str, AfterValidator(_bdm_employee_id)]
BdmText = Annotated[str | None, Field(max_length=120), AfterValidator(_bdm_optional)]


class BdmProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bdm_type: BdmType
    employee_id: BdmEmployeeId
    designation: BdmText = None
    department: BdmText = None
    territory: BdmText = None
    reporting_manager_user_id: UUID


class BdmProfileUpdate(BaseModel):
    """Omitted = unchanged. The optional texts accept null/"" (clears). The three non-optional keys reject null: the default None is
    never validated, but an explicit null is checked against the non-nullable type and fails."""

    model_config = ConfigDict(extra="forbid")
    bdm_type: BdmType = None
    employee_id: BdmEmployeeId = None
    designation: BdmText = None
    department: BdmText = None
    territory: BdmText = None
    reporting_manager_user_id: UUID = None


class BdmManagerRef(BaseModel):
    id: UUID
    full_name: str
    active: bool


class BdmProfileOut(BaseModel):
    bdm_type: str
    employee_id: str
    designation: str | None
    department: str | None
    territory: str | None
    reporting_manager: BdmManagerRef


class BdmMeOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    active: bool
    division: str
    bdm_profile: BdmProfileOut


class BdmTeamRow(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    active: bool
    bdm_type: str
    employee_id: str
    designation: str | None
    department: str | None
    territory: str | None


class BdmAdminRow(BdmTeamRow):
    reporting_manager: BdmManagerRef
    manager_active: bool


class BdmManagerOption(BaseModel):
    id: UUID
    full_name: str


class BdmTeamPage(BaseModel):
    items: list[BdmTeamRow]
    total: int
    limit: int
    offset: int


class BdmAdminPage(BaseModel):
    items: list[BdmAdminRow]
    total: int
    limit: int
    offset: int


class BdmManagerPage(BaseModel):
    items: list[BdmManagerOption]
    total: int
    limit: int
    offset: int
```

Then `services/bdm.py`:

```python
"""bdm-001 (DEC-SCOPE-052, spec §5.3): BDM provisioning rules and the type/own/team scope every later bdm item calls.
Functions only; nothing here commits -- the route owns the transaction. Logs carry ids, route and type, never email/phone/Employee ID."""

import logging

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BdmProfile, User
from app.schemas import BdmProfileCreate, BdmProfileUpdate

logger = logging.getLogger("app.bdm")

BDM_TYPES = ("agent", "school", "college")
BDM_DIVISION = {"college": "it", "agent": "overseas", "school": "overseas"}  # D3
CREATOR_TYPES = {  # D10 (Q-01)
    "super_admin": frozenset(BDM_TYPES),
    "it_admin": frozenset({"college"}),
    "overseas_admin": frozenset({"agent", "school"}),
}
EMPLOYEE_ID_INDEX = "uq_bdm_profiles_employee_id"
PROFILE_FIELDS = ("bdm_type", "employee_id", "designation", "department", "territory")


def creatable_types(actor: User) -> frozenset[str]:
    return CREATOR_TYPES.get(actor.role, frozenset())


def require_creator_may(actor: User, bdm_type: str, route: str) -> None:
    if bdm_type not in creatable_types(actor):
        logger.warning("bdm_creator_type_refused", extra={"extra_fields": {"actor_id": str(actor.id), "route": route, "bdm_type": bdm_type}})
        raise HTTPException(403, f"Your role cannot manage {bdm_type} BDMs")


def _validation_detail(exc: ValidationError) -> str:
    error = exc.errors()[0]
    field = ".".join(str(part) for part in error["loc"])
    return f"bdm_profile.{field}: {error['msg']}" if field else f"bdm_profile: {error['msg']}"


def parse_profile_create(raw) -> BdmProfileCreate:
    if not isinstance(raw, dict):
        raise HTTPException(422, "BDM profile is required")
    try:
        return BdmProfileCreate.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(422, _validation_detail(exc)) from None


def parse_profile_update(raw) -> BdmProfileUpdate:
    if not isinstance(raw, dict):
        raise HTTPException(422, "bdm_profile must be an object")
    try:
        return BdmProfileUpdate.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(422, _validation_detail(exc)) from None


async def locked_active_manager(db: AsyncSession, manager_id) -> User:
    """FOR UPDATE: a concurrent deactivation of this manager (an UPDATE of the same row) is serialised with the assignment, so a
    BDM is never committed against a manager deactivated in the same instant (spec §5.8)."""
    manager = await db.scalar(select(User).where(User.id == manager_id).with_for_update())
    if not manager or not manager.active or manager.role != "bdm_manager":
        raise HTTPException(422, "Reporting manager must be an active BDM manager")
    return manager


async def flush_profile(db: AsyncSession) -> None:
    """The unique index decides a duplicate Employee ID (case-insensitive) even under a race; the whole transaction rolls back."""
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if EMPLOYEE_ID_INDEX in str(exc.orig):
            raise HTTPException(409, "Employee ID already exists") from None
        raise


def profile_snapshot(profile: BdmProfile) -> dict:
    return {**{k: getattr(profile, k) for k in PROFILE_FIELDS}, "reporting_manager_user_id": str(profile.reporting_manager_user_id)}


def profile_out(profile: BdmProfile, manager: User) -> dict:
    return {
        **{k: getattr(profile, k) for k in PROFILE_FIELDS},
        "reporting_manager": {"id": manager.id, "full_name": manager.full_name, "active": manager.active},
    }


async def bdm_context(db: AsyncSession, user: User) -> BdmProfile:
    if user.role != "bdm":
        raise HTTPException(403, "BDM role required")
    profile = await db.scalar(select(BdmProfile).where(BdmProfile.user_id == user.id))
    if not profile:
        raise HTTPException(403, "BDM profile not set up — contact your administrator")
    return profile


def require_manager(user: User) -> None:
    if user.role not in ("bdm_manager", "super_admin"):
        raise HTTPException(403, "BDM manager role required")


def team_filter(user: User) -> list:
    return [] if user.role == "super_admin" else [BdmProfile.reporting_manager_user_id == user.id]


def admin_type_filter(actor: User, bdm_type: str | None) -> list:
    allowed = creatable_types(actor)
    if bdm_type is not None:
        if bdm_type not in allowed:
            raise HTTPException(403, f"Your role cannot manage {bdm_type} BDMs")
        return [BdmProfile.bdm_type == bdm_type]
    return [BdmProfile.bdm_type.in_(sorted(allowed))]
```

- [ ] **Step 4: Run and confirm GREEN.** Expected: all pass. Also run `tests/test_adm_012_roles_permissions.py tests/test_rbac.py` to confirm adding the roles broke nothing (expected: pass).
- [ ] **Step 5: REFACTOR.** Check for duplication between `parse_profile_create` and `parse_profile_update`. Fold them into a `_parse(model, raw, missing_detail)` helper only if the result is clearer; re-run the tests.
- [ ] **Step 6: Commit** — `feat(bdm-001): bdm roles, profile schemas and services/bdm`.

---

### Task 3: `POST /admin/users` — the BDM and manager create branch

**Files:**
- Modify: `apps/api/app/api/admin.py:411-452` (`create_user`) and its imports
- Create: `apps/api/tests/bdm001_helpers.py`
- Test: `apps/api/tests/test_bdm_001_profiles.py`

**Interfaces:**
- Consumes: everything from Task 2.
- Produces: `bdm001_helpers` with `email()`, `make_user(db, role, division, active=True)`, `login(client, user)`, `make_manager(db, active=True)`, `create_bdm(client, manager_id, **overrides) -> Response` and `PASSWORD`. Every API test task reuses these.

- [ ] **Step 1: Write the helpers and the failing tests.**

`bdm001_helpers.py`:

```python
"""bdm-001 test builders. Every value is unique per call: the test database is shared and never truncated."""

import uuid

from app.core.security import hash_password
from app.models import User

PASSWORD = "Sup3r-Secret-Pass!"
USERS = "/api/v1/admin/users"
LOGIN_DIVISION = {"it": "it", "overseas": "overseas", "global": "global"}


def email(prefix: str = "bdm001") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.local"


def emp() -> str:
    return f"E-{uuid.uuid4().hex[:10]}"


async def make_user(db, role: str, division: str, *, active: bool = True, name: str | None = None) -> User:
    user = User(email=email(role), password_hash=hash_password(PASSWORD), full_name=name or f"{role} {uuid.uuid4().hex[:4]}", role=role, division=division, active=active, email_verified=True)
    db.add(user)
    await db.commit()
    return user


async def make_manager(db, *, active: bool = True, name: str | None = None) -> User:
    return await make_user(db, "bdm_manager", "global", active=active, name=name)


async def login(client, user: User):
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD, "division": LOGIN_DIVISION[user.division]})
    assert response.status_code == 200, response.text
    return response


def bdm_payload(manager_id, *, bdm_type: str = "college", **overrides) -> dict:
    payload = {"role": "bdm", "email": email("bdm"), "full_name": "Asha BDM", "phone": "+91 90000 00000",
               "bdm_profile": {"bdm_type": bdm_type, "employee_id": emp(), "designation": "BDM", "territory": "Kochi", "reporting_manager_user_id": str(manager_id)}}
    payload.update(overrides)
    return payload


async def create_bdm(client, manager_id, **overrides):
    return await client.post(USERS, json=bdm_payload(manager_id, **overrides))
```

`test_bdm_001_profiles.py`, the create half:

```python
"""bdm-001 -- POST/PATCH /admin/users BDM branches (spec §5.4, §5.5; AC01-AC04, AC07-AC09, AC14-AC16)."""

import asyncio
import logging

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, BdmProfile, PasswordResetToken, User
from app.core.security import verify_password
from tests.bdm001_helpers import PASSWORD, USERS, bdm_payload, create_bdm, emp, login, make_manager, make_user


@pytest.fixture(autouse=True)
def _loggers_enabled():
    for name in ("app.bdm", "app.admin", "app.provisioning"):
        logging.getLogger(name).disabled = False


async def _super(client, db):
    admin = await make_user(db, "super_admin", "global")
    await login(client, admin)
    return admin


# --- AC01 / AC08: who may create what -------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "bdm_type", "expected_division"), [
    ("super_admin", "global", "agent", "overseas"), ("it_admin", "it", "college", "it"),
    ("overseas_admin", "overseas", "school", "overseas"), ("overseas_admin", "overseas", "agent", "overseas"),
])
async def test_authorized_admin_creates_a_bdm_with_a_link_and_no_password(client, db_session, role, division, bdm_type, expected_division):
    manager = await make_manager(db_session)
    await login(client, await make_user(db_session, role, division))
    response = await create_bdm(client, manager.id, bdm_type=bdm_type)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "bdm" and body["division"] == expected_division
    assert body["bdm_profile"]["bdm_type"] == bdm_type and body["bdm_profile"]["reporting_manager"]["id"] == str(manager.id)
    assert not any("password" in k.lower() for k in body)
    user = await db_session.scalar(select(User).where(User.email == response.json()["email"]))
    assert not verify_password(PASSWORD, user.password_hash)
    assert await db_session.scalar(select(func.count()).select_from(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.purpose == "welcome")) == 1
    assert await db_session.scalar(select(BdmProfile).where(BdmProfile.user_id == user.id)) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "bdm_type"), [("it_admin", "it", "agent"), ("it_admin", "it", "school"), ("overseas_admin", "overseas", "college")])
async def test_admin_outside_its_types_gets_403_and_nothing_is_written(client, db_session, role, division, bdm_type):
    manager = await make_manager(db_session)
    await login(client, await make_user(db_session, role, division))
    payload = bdm_payload(manager.id, bdm_type=bdm_type)
    assert (await client.post(USERS, json=payload)).status_code == 403
    assert await db_session.scalar(select(User).where(User.email == payload["email"])) is None


@pytest.mark.asyncio
async def test_only_super_admin_creates_a_manager(client, db_session):
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.post(USERS, json={"role": "bdm_manager", "division": "global", "email": f"m-{emp()}@example.local", "full_name": "M"})).status_code == 403
    await _super(client, db_session)
    response = await client.post(USERS, json={"role": "bdm_manager", "division": "global", "email": f"m-{emp()}@example.local", "full_name": "M"})
    assert response.status_code == 201 and response.json()["bdm_profile"] is None


@pytest.mark.asyncio
async def test_supplied_password_is_422(client, db_session):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    assert (await create_bdm(client, manager.id, password="Whatever-123!")).status_code == 422


# --- AC02: division -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("bdm_type", "division"), [("college", "overseas"), ("agent", "it"), ("school", "global")])
async def test_mismatched_division_is_422(client, db_session, bdm_type, division):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    response = await create_bdm(client, manager.id, bdm_type=bdm_type, division=division)
    assert response.status_code == 422 and "Division must be" in response.json()["detail"]


# --- AC03: Employee ID ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_employee_id_trimmed_and_case_insensitive(client, db_session):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    code = emp()
    first = bdm_payload(manager.id)
    first["bdm_profile"]["employee_id"] = f"  {code} "
    assert (await client.post(USERS, json=first)).json()["bdm_profile"]["employee_id"] == code
    dup = bdm_payload(manager.id)
    dup["bdm_profile"]["employee_id"] = code.lower()
    before = await db_session.scalar(select(func.count()).select_from(User))
    response = await client.post(USERS, json=dup)
    assert response.status_code == 409 and response.json()["detail"] == "Employee ID already exists"
    assert await db_session.scalar(select(func.count()).select_from(User)) == before


@pytest.mark.asyncio
async def test_concurrent_duplicate_employee_id_is_one_201_one_409(client, db_session):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    a, b = bdm_payload(manager.id), bdm_payload(manager.id)
    b["bdm_profile"]["employee_id"] = a["bdm_profile"]["employee_id"]
    results = await asyncio.gather(client.post(USERS, json=a), client.post(USERS, json=b))
    assert sorted(r.status_code for r in results) == [201, 409]


# --- AC04: reporting manager ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["missing", "inactive", "counselor", "bdm_user"])
async def test_invalid_manager_is_422(client, db_session, kind):
    import uuid as _uuid

    await _super(client, db_session)
    if kind == "missing":
        target = _uuid.uuid4()
    elif kind == "inactive":
        target = (await make_manager(db_session, active=False)).id
    elif kind == "counselor":
        target = (await make_user(db_session, "counselor", "overseas")).id
    else:
        target = (await make_user(db_session, "bdm", "it")).id
    payload = bdm_payload(target)
    response = await client.post(USERS, json=payload)
    assert response.status_code == 422 and response.json()["detail"] == "Reporting manager must be an active BDM manager"
    assert await db_session.scalar(select(User).where(User.email == payload["email"])) is None


# --- AC09 / AC15 / AC16 shapes and malformed input ------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("profile", [None, "x", [], 5])
async def test_profile_not_an_object_is_422(client, db_session, profile):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    assert (await create_bdm(client, manager.id, bdm_profile=profile)).status_code == 422


@pytest.mark.asyncio
async def test_bdm_without_profile_is_422_and_profile_on_other_role_is_422(client, db_session):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    payload = bdm_payload(manager.id)
    del payload["bdm_profile"]
    assert (await client.post(USERS, json=payload)).status_code == 422
    other = bdm_payload(manager.id, role="counselor", division="overseas")
    assert (await client.post(USERS, json=other)).status_code == 422


@pytest.mark.asyncio
async def test_non_bdm_create_has_null_bdm_profile_and_is_otherwise_unchanged(client, db_session):
    await _super(client, db_session)
    response = await client.post(USERS, json={"role": "counselor", "division": "overseas", "email": f"c-{emp()}@example.local", "full_name": "C"})
    assert response.status_code == 201
    assert set(response.json()) >= {"id", "email", "role", "division", "email_status", "bdm_profile"} and response.json()["bdm_profile"] is None


# --- AC07: audit ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_writes_one_audit_row_with_the_profile(client, db_session):
    manager = await make_manager(db_session)
    admin = await _super(client, db_session)
    body = (await create_bdm(client, manager.id)).json()
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "user.create", AuditLog.entity_id == str(body["id"])))).all()
    assert len(rows) == 1 and rows[0].user_id == admin.id
    meta = rows[0].metadata_json
    assert meta["role"] == "bdm" and meta["bdm_profile"]["employee_id"] == body["bdm_profile"]["employee_id"]
    assert meta["bdm_profile"]["reporting_manager_user_id"] == str(manager.id)
```

- [ ] **Step 2: Run and confirm RED.** `<PATHS>` = `tests/test_bdm_001_profiles.py`. Expected: the create tests fail with `422 Role is not valid for the selected division` (the `bdm` role isn't allowed yet) and `KeyError: 'bdm_profile'`.

- [ ] **Step 3: Implement in `create_user`.** Add the imports `from app.models import BdmProfile` (or extend the existing models import) and `from app.services import bdm as bdm_rules`. Then:

```python
USERS_ROUTE = "/api/v1/admin/users"  # module level, next to USER_LIST_CAP


@router.post("/users", status_code=201)
async def create_user(payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    from app.models import AuditLog

    division = payload.get("division", user.division)
    role = payload["role"]
    # bdm-001 (spec §5.4): BDM type rules run BEFORE the cross-division gate, so a super_admin's mismatched division is the
    # AC2 422 and a division admin's wrong type is the D10 403. Every other role skips this block entirely.
    bdm_input = None
    if role == "bdm":
        bdm_input = bdm_rules.parse_profile_create(payload.get("bdm_profile"))
        bdm_rules.require_creator_may(user, bdm_input.bdm_type, USERS_ROUTE)
        mapped = bdm_rules.BDM_DIVISION[bdm_input.bdm_type]
        if "division" not in payload:
            division = mapped
        elif division != mapped:
            raise HTTPException(422, f"Division must be {mapped} for a {bdm_input.bdm_type} BDM")
    elif "bdm_profile" in payload:
        raise HTTPException(422, "Only a BDM has a BDM profile")
    elif role == "bdm_manager" and user.role != "super_admin":
        raise HTTPException(403, "Only a Super Admin can create BDM managers")
    if user.role != "super_admin" and division != user.division:
        raise HTTPException(403, "Cannot create users in another division")
    _reject_supplied_password(payload, user, USERS_ROUTE, "password")
    allowed_by_division = {
        "it": {"it_student", "trainer", "placement_team", "hr_team", "it_admin", "bdm"},
        "overseas": {"overseas_student", "counselor", "university_rep", "agent", "overseas_admin", "bdm"},
        "global": {"super_admin", "bdm_manager"},
    }
    # ... existing lines unchanged through `await _flush_unique_email(db)` and the agent block ...
    profile = manager = None
    if bdm_input is not None:
        manager = await bdm_rules.locked_active_manager(db, bdm_input.reporting_manager_user_id)
        profile = BdmProfile(user_id=item.id, **bdm_input.model_dump())
        db.add(profile)
        await bdm_rules.flush_profile(db)
    issued = await issue_welcome_token(db, user=item, issued_by=user)
    metadata = {"role": role, "division": division}
    if profile is not None:
        metadata["bdm_profile"] = bdm_rules.profile_snapshot(profile)
    db.add(AuditLog(user_id=user.id, action="user.create", entity_type="user", entity_id=str(item.id), metadata_json=metadata))
    await db.commit()
    delivery = await deliver_welcome_link(user=item, issued=issued, issued_by=user)
    return {"id": item.id, "email": item.email, "role": item.role, "division": item.division, **delivery,
            "bdm_profile": bdm_rules.profile_out(profile, manager) if profile is not None else None}
```

The existing string literal `"/api/v1/admin/users"` passed to `_reject_supplied_password` becomes `USERS_ROUTE`; the value is identical.

- [ ] **Step 4: Run and confirm GREEN.** Expected: all the create tests pass.
- [ ] **Step 5: Regression check (lite).** `<PATHS>` = `tests/test_adm_001_admin_crud.py tests/test_enh_003_first_time_provisioning.py tests/test_enh_029_provision_refactor.py tests/test_sch_school_staff_provisioning.py`, plus the AGN-001 admin-created agent test (`grep -l "agency_name" tests/test_agn_001*.py`). Expected: pass, unchanged.
- [ ] **Step 6: REFACTOR.** If `create_user` now reads poorly, move the bdm pre-check into one service function, `bdm_rules.resolve_create(user, payload, division) -> (bdm_input, division)`, and re-run steps 4–5.
- [ ] **Step 7: Commit** — `feat(bdm-001): create BDMs and BDM managers through /admin/users`.

---

### Task 4: `PATCH /admin/users/{id}` — editing the BDM profile

**Files:**
- Modify: `apps/api/app/api/admin.py:455-482` (`update_user`)
- Test: `apps/api/tests/test_bdm_001_profiles.py` (append)

**Interfaces:**
- Consumes: `parse_profile_update`, `locked_active_manager`, `flush_profile`, `profile_snapshot` and `require_creator_may` (Task 2); `bdm001_helpers` (Task 3).

- [ ] **Step 1: Write the failing tests** (appended):

```python
async def _bdm(client, db_session, **overrides):
    manager = await make_manager(db_session)
    await _super(client, db_session)
    body = (await create_bdm(client, manager.id, **overrides)).json()
    return body, manager


def _patch(client, user_id, payload):
    return client.patch(f"{USERS}/{user_id}", json=payload)


@pytest.mark.asyncio
async def test_patch_profile_fields_and_audit_before_after(client, db_session):
    body, _ = await _bdm(client, db_session)
    other = await make_manager(db_session)
    response = await _patch(client, body["id"], {"bdm_profile": {"territory": "Kollam", "designation": None, "reporting_manager_user_id": str(other.id)}})
    assert response.status_code == 200 and response.json() == {"ok": True}
    profile = await db_session.scalar(select(BdmProfile).where(BdmProfile.user_id == body["id"]))
    assert profile.territory == "Kollam" and profile.designation is None and profile.reporting_manager_user_id == other.id
    row = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "user.update", AuditLog.entity_id == str(body["id"])))).all()[-1]
    assert row.metadata_json["bdm_profile_before"]["territory"] == "Kochi"
    assert row.metadata_json["bdm_profile_after"]["territory"] == "Kollam"


@pytest.mark.asyncio
async def test_patch_type_change_is_422_and_same_type_is_a_noop(client, db_session):
    body, _ = await _bdm(client, db_session)
    assert (await _patch(client, body["id"], {"bdm_profile": {"bdm_type": "agent"}})).json()["detail"] == "BDM type cannot be changed"
    assert (await _patch(client, body["id"], {"bdm_profile": {"bdm_type": "college"}})).status_code == 200


@pytest.mark.asyncio
async def test_patch_duplicate_employee_id_is_409_and_nothing_changes(client, db_session):
    first, _ = await _bdm(client, db_session)
    second, _ = await _bdm(client, db_session)
    response = await _patch(client, second["id"], {"full_name": "Changed", "bdm_profile": {"employee_id": first["bdm_profile"]["employee_id"].upper()}})
    assert response.status_code == 409
    db_session.expire_all()
    assert (await db_session.get(User, second["id"])).full_name == "Asha BDM"


@pytest.mark.asyncio
async def test_patch_invalid_manager_is_422(client, db_session):
    body, _ = await _bdm(client, db_session)
    inactive = await make_manager(db_session, active=False)
    assert (await _patch(client, body["id"], {"bdm_profile": {"reporting_manager_user_id": str(inactive.id)}})).status_code == 422


@pytest.mark.asyncio
async def test_patch_other_fields_when_manager_inactive_succeeds(client, db_session):
    body, manager = await _bdm(client, db_session)
    assert (await _patch(client, manager.id, {"active": False})).status_code == 200
    assert (await _patch(client, body["id"], {"bdm_profile": {"territory": "Thrissur"}})).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", [{"employee_id": None}, {"reporting_manager_user_id": None}, {"user_id": "x"}, "x", None])
async def test_patch_bad_profile_is_422(client, db_session, profile):
    body, _ = await _bdm(client, db_session)
    assert (await _patch(client, body["id"], {"bdm_profile": profile})).status_code == 422


@pytest.mark.asyncio
async def test_patch_profile_on_non_bdm_is_422(client, db_session):
    await _super(client, db_session)
    target = await make_user(db_session, "counselor", "overseas")
    assert (await _patch(client, target.id, {"bdm_profile": {"territory": "X"}})).status_code == 422


@pytest.mark.asyncio
async def test_patch_ignores_role_and_division_escalation(client, db_session):
    body, _ = await _bdm(client, db_session)
    assert (await _patch(client, body["id"], {"role": "super_admin", "division": "global"})).status_code == 200
    db_session.expire_all()
    user = await db_session.get(User, body["id"])
    assert (user.role, user.division) == ("bdm", "it")


@pytest.mark.asyncio
async def test_division_admin_cannot_patch_a_type_it_does_not_manage(client, db_session):
    body, _ = await _bdm(client, db_session, bdm_type="agent")
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await _patch(client, body["id"], {"bdm_profile": {"territory": "X"}})).status_code == 403


@pytest.mark.asyncio
async def test_concurrent_patches_both_audited_and_chain(client, db_session):
    body, _ = await _bdm(client, db_session)
    await asyncio.gather(_patch(client, body["id"], {"bdm_profile": {"territory": "A"}}), _patch(client, body["id"], {"bdm_profile": {"territory": "B"}}))
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "user.update", AuditLog.entity_id == str(body["id"])).order_by(AuditLog.created_at))).all()[-2:]
    assert rows[1].metadata_json["bdm_profile_before"]["territory"] == rows[0].metadata_json["bdm_profile_after"]["territory"]
```

- [ ] **Step 2: Run and confirm RED.** The new tests fail. `bdm_profile` is silently ignored today, so the territory is unchanged and there is no 409, 422 or 403.

- [ ] **Step 3: Implement.** Add this to `update_user` right after the division 403 and **before** the trainer guard, so every refusal happens before any write:

```python
    # bdm-001 (spec §5.5): the profile row is locked so concurrent edits serialise and each audit before/after is exact.
    profile = None
    if item.role == "bdm":
        profile = await db.scalar(select(BdmProfile).where(BdmProfile.user_id == item.id).with_for_update())
        if profile is not None:
            bdm_rules.require_creator_may(user, profile.bdm_type, f"{USERS_ROUTE}/{{id}}")
    profile_before = profile_after = None
    if "bdm_profile" in payload:
        if profile is None:
            raise HTTPException(422, "Only a BDM has a BDM profile")
        changes = bdm_rules.parse_profile_update(payload["bdm_profile"]).model_dump(exclude_unset=True)
        if "bdm_type" in changes and changes.pop("bdm_type") != profile.bdm_type:
            raise HTTPException(422, "BDM type cannot be changed")
        new_manager = changes.get("reporting_manager_user_id")
        if new_manager is not None and new_manager != profile.reporting_manager_user_id:
            await bdm_rules.locked_active_manager(db, new_manager)
        profile_before = bdm_rules.profile_snapshot(profile)
        for key, value in changes.items():
            setattr(profile, key, value)
        await bdm_rules.flush_profile(db)
        profile_after = bdm_rules.profile_snapshot(profile)
```

Change the audit line to:

```python
    metadata = {k: v for k, v in payload.items() if k != "password"}
    if profile_before is not None:
        metadata.update(bdm_profile_before=profile_before, bdm_profile_after=profile_after)
    db.add(AuditLog(user_id=user.id, action="user.update", entity_type="user", entity_id=str(item.id), metadata_json=metadata))
```

- [ ] **Step 4: Run and confirm GREEN** for the whole `tests/test_bdm_001_profiles.py`.
- [ ] **Step 5: Regression check (lite).** `tests/test_adm_001_admin_crud.py tests/test_adm_004_directory.py tests/test_enh_003_first_time_provisioning.py`. Expected: pass.
- [ ] **Step 6: REFACTOR.** If the update block is longer than about 20 lines in the route, move it into `bdm_rules.apply_profile_update(db, actor, profile, raw) -> (before, after)`. Re-run.
- [ ] **Step 7: Commit** — `feat(bdm-001): edit the BDM profile through PATCH /admin/users`.

---

### Task 5: Read routes — `app/api/bdm.py`

**Files:**
- Create: `apps/api/app/api/bdm.py`
- Modify: `apps/api/app/main.py` (the import tuple, alphabetical, and the router tuple: append `bdm.router, bdm.admin_router`)
- Test: `apps/api/tests/test_bdm_001_reads.py`

**Interfaces:**
- Consumes: Task 2 helpers and schemas; `admin.ensure_admin`.
- Produces: `GET /api/v1/bdm/me` → `BdmMeOut`; `GET /api/v1/bdm/manager/team` → `BdmTeamPage`; `GET /api/v1/admin/bdms` → `BdmAdminPage`; `GET /api/v1/admin/bdm-managers` → `BdmManagerPage`.

- [ ] **Step 1: Write the failing tests.**

```python
"""bdm-001 -- read routes (spec §5.7; AC06, AC10, AC11, AC15, AC16)."""

import pytest

from tests.bdm001_helpers import create_bdm, login, make_manager, make_user

ME, TEAM, BDMS, MANAGERS = "/api/v1/bdm/me", "/api/v1/bdm/manager/team", "/api/v1/admin/bdms", "/api/v1/admin/bdm-managers"


async def _team_of_two(client, db):
    """Manager M1 with 2 BDMs (one deactivated), manager M2 with 1. Created by a super_admin session."""
    m1, m2 = await make_manager(db), await make_manager(db)
    await login(client, await make_user(db, "super_admin", "global"))
    a = (await create_bdm(client, m1.id)).json()
    b = (await create_bdm(client, m1.id, bdm_type="agent")).json()
    c = (await create_bdm(client, m2.id, bdm_type="school")).json()
    assert (await client.patch(f"/api/v1/admin/users/{b['id']}", json={"active": False})).status_code == 200
    return m1, m2, a, b, c


@pytest.mark.asyncio
async def test_manager_team_is_exactly_their_reports(client, db_session):
    m1, _, a, b, c = await _team_of_two(client, db_session)
    await login(client, m1)
    body = (await client.get(TEAM)).json()
    assert {r["id"] for r in body["items"]} == {a["id"], b["id"]} and body["total"] == 2
    assert {r["id"]: r["active"] for r in body["items"]}[b["id"]] is False
    assert c["id"] not in {r["id"] for r in body["items"]}


@pytest.mark.asyncio
async def test_super_admin_sees_every_bdm_in_team_route(client, db_session):
    _, _, a, b, c = await _team_of_two(client, db_session)
    body = (await client.get(TEAM, params={"limit": 100})).json()
    assert {a["id"], b["id"], c["id"]} <= {r["id"] for r in body["items"]} or body["total"] > 100


@pytest.mark.asyncio
async def test_team_route_refuses_bdm_and_other_roles(client, db_session):
    for role, division in (("bdm", "it"), ("counselor", "overseas"), ("it_admin", "it")):
        await login(client, await make_user(db_session, role, division))
        assert (await client.get(TEAM)).status_code == 403


@pytest.mark.asyncio
async def test_bdm_me_returns_own_profile_only(client, db_session):
    m1, _, a, _, _ = await _team_of_two(client, db_session)
    from app.models import User
    from sqlalchemy import select

    user = await db_session.scalar(select(User).where(User.id == a["id"]))
    from app.core.security import hash_password
    from tests.bdm001_helpers import PASSWORD

    user.password_hash = hash_password(PASSWORD)
    await db_session.commit()
    await login(client, user)
    body = (await client.get(ME)).json()
    assert body["id"] == a["id"] and body["bdm_profile"]["reporting_manager"]["id"] == str(m1.id)
    assert set(body) == {"id", "full_name", "email", "phone", "active", "division", "bdm_profile"}


@pytest.mark.asyncio
async def test_bdm_me_without_profile_and_other_roles_are_403(client, db_session):
    await login(client, await make_user(db_session, "bdm", "it"))
    response = await client.get(ME)
    assert response.status_code == 403 and "not set up" in response.json()["detail"]
    await login(client, await make_manager(db_session))
    assert (await client.get(ME)).status_code == 403


@pytest.mark.asyncio
async def test_admin_bdms_scoped_by_creator_types_and_flags_inactive_manager(client, db_session):
    m1, m2, a, b, c = await _team_of_two(client, db_session)
    assert (await client.patch(f"/api/v1/admin/users/{m2.id}", json={"active": False})).status_code == 200
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    items = (await client.get(BDMS, params={"limit": 100})).json()["items"]
    assert all(r["bdm_type"] in ("agent", "school") for r in items)
    assert {r["id"]: r["manager_active"] for r in items}[c["id"]] is False
    assert (await client.get(BDMS, params={"bdm_type": "college"})).status_code == 403
    assert (await client.get(BDMS, params={"bdm_type": "it"})).status_code == 422
    assert all(r["active"] is False for r in (await client.get(BDMS, params={"active": "false", "limit": 100})).json()["items"])


@pytest.mark.asyncio
async def test_manager_picker_lists_active_managers_without_email(client, db_session):
    active, inactive = await make_manager(db_session), await make_manager(db_session, active=False)
    await login(client, await make_user(db_session, "it_admin", "it"))
    body = (await client.get(MANAGERS, params={"limit": 100})).json()
    ids = {r["id"] for r in body["items"]}
    assert str(inactive.id) not in ids and (str(active.id) in ids or body["total"] > 100)
    assert all(set(r) == {"id", "full_name"} for r in body["items"])
    await login(client, await make_user(db_session, "counselor", "overseas"))
    assert (await client.get(MANAGERS)).status_code == 403


@pytest.mark.asyncio
async def test_pages_are_stable_and_shaped(client, db_session):
    m1, _, a, b, _ = await _team_of_two(client, db_session)
    await login(client, m1)
    first, second = (await client.get(TEAM, params={"limit": 1})).json(), (await client.get(TEAM, params={"limit": 1, "offset": 1})).json()
    assert (first["limit"], first["offset"], first["total"]) == (1, 0, 2)
    assert {first["items"][0]["id"], second["items"][0]["id"]} == {a["id"], b["id"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
async def test_list_bounds_are_422(client, db_session, params):
    await login(client, await make_user(db_session, "super_admin", "global"))
    for url in (TEAM, BDMS, MANAGERS):
        assert (await client.get(url, params=params)).status_code == 422
```

- [ ] **Step 2: Run and confirm RED.** `tests/test_bdm_001_reads.py` → 404s (the routes don't exist yet).

- [ ] **Step 3: Implement `app/api/bdm.py`.**

```python
"""bdm-001 (DEC-SCOPE-052, spec §5.7): BDM and BDM-manager reads, and the admin BDM list and manager picker.
Read-only. Scope always comes from the session (no user id in any path), so there is no IDOR surface."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.admin import ensure_admin
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import BdmProfile, User
from app.schemas import BdmAdminPage, BdmManagerPage, BdmMeOut, BdmTeamPage
from app.services.bdm import admin_type_filter, bdm_context, profile_out, require_manager, team_filter

router = APIRouter(prefix="/bdm", tags=["bdm"])
admin_router = APIRouter(prefix="/admin", tags=["bdm-admin"])
Manager = aliased(User)
Limit = Query(50, ge=1, le=100)
Offset = Query(0, ge=0)


def _team_row(profile: BdmProfile, user: User, manager: User) -> dict:
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active,
        "bdm_type": profile.bdm_type, "employee_id": profile.employee_id, "designation": profile.designation,
        "department": profile.department, "territory": profile.territory,
    }


def _admin_row(profile: BdmProfile, user: User, manager: User) -> dict:
    return {**_team_row(profile, user, manager), "reporting_manager": {"id": manager.id, "full_name": manager.full_name, "active": manager.active}, "manager_active": manager.active}


async def _page(db: AsyncSession, filters: list, limit: int, offset: int, shape) -> dict:
    base = (
        select(BdmProfile, User, Manager)
        .join(User, User.id == BdmProfile.user_id)
        .join(Manager, Manager.id == BdmProfile.reporting_manager_user_id)
        .where(*filters)
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(base.order_by(User.full_name, User.id).limit(limit).offset(offset))).all()
    return {"items": [shape(p, u, m) for p, u, m in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.get("/me", response_model=BdmMeOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await bdm_context(db, user)
    manager = await db.get(User, profile.reporting_manager_user_id)
    return {"id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active,
            "division": user.division, "bdm_profile": profile_out(profile, manager)}


@router.get("/manager/team", response_model=BdmTeamPage)
async def team(limit: int = Limit, offset: int = Offset, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    return await _page(db, team_filter(user), limit, offset, _team_row)


@admin_router.get("/bdms", response_model=BdmAdminPage)
async def admin_bdms(
    bdm_type: Literal["agent", "school", "college"] | None = None,
    active: bool | None = None,
    limit: int = Limit,
    offset: int = Offset,
    user: User = Depends(ensure_admin),
    db: AsyncSession = Depends(get_db),
):
    filters = admin_type_filter(user, bdm_type)
    if active is not None:
        filters.append(User.active.is_(active))
    return await _page(db, filters, limit, offset, _admin_row)


@admin_router.get("/bdm-managers", response_model=BdmManagerPage)
async def bdm_managers(limit: int = Limit, offset: int = Offset, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    base = select(User.id, User.full_name).where(User.role == "bdm_manager", User.active.is_(True))
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(base.order_by(User.full_name, User.id).limit(limit).offset(offset))).all()
    return {"items": [{"id": r.id, "full_name": r.full_name} for r in rows], "total": total or 0, "limit": limit, "offset": offset}
```

In `main.py`, add `bdm` to the `from app.api import (...)` list, and `bdm.router, bdm.admin_router` to the router tuple.

- [ ] **Step 4: Run and confirm GREEN.** `tests/test_bdm_001_reads.py`.
- [ ] **Step 5: REFACTOR.** `bdm_managers` duplicates the count/page lines from `_page`. If clearer, extract `_paged(db, stmt, order, limit, offset, shape)` and use it for both; re-run.
- [ ] **Step 6: Commit** — `feat(bdm-001): BDM, manager-team and admin BDM read routes`.

---

### Task 6: `POST /auth/reset-password` returns `login_portal`

**Files:**
- Modify: `apps/api/app/api/auth.py:288` (the `return {"ok": True}` of `reset_password`)
- Test: `apps/api/tests/test_bdm_001_reset_portal.py`

**Interfaces:**
- Produces: the reset response `{"ok": true, "login_portal": "admin" | null}`. Consumed by `ResetPasswordForm` (Task 7).

- [ ] **Step 1: Write the failing test.**

```python
"""bdm-001 -- reset-password names the sign-in portal for a BDM manager (spec §5.6; AC05, AC15)."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import PasswordResetToken
from tests.bdm001_helpers import make_manager, make_user


async def _token(db, user):
    raw = uuid.uuid4().hex * 2
    db.add(PasswordResetToken(user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), purpose="welcome", expires_at=datetime.now(UTC) + timedelta(hours=72)))
    await db.commit()
    return raw


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "portal"), [("bdm_manager", "global", "admin"), ("bdm", "it", None), ("it_student", "it", None), ("super_admin", "global", None)])
async def test_login_portal_is_admin_only_for_a_manager(client, db_session, role, division, portal):
    user = await make_manager(db_session) if role == "bdm_manager" else await make_user(db_session, role, division)
    response = await client.post("/api/v1/auth/reset-password", json={"token": await _token(db_session, user), "new_password": "Brand-New-Pass-1!"})
    assert response.status_code == 200 and response.json() == {"ok": True, "login_portal": portal}


@pytest.mark.asyncio
async def test_invalid_link_is_still_the_generic_400(client):
    response = await client.post("/api/v1/auth/reset-password", json={"token": "nope", "new_password": "Brand-New-Pass-1!"})
    assert response.status_code == 400 and "login_portal" not in response.json()
```

- [ ] **Step 2: Run and confirm RED.** The response equals `{"ok": True}`, so the assertion fails.
- [ ] **Step 3: Implement.** Replace the final return:

```python
    # bdm-001 (spec §5.6): a BDM manager (division `global`) signs in at /admin/login; the reset form follows this. Always present.
    return {"ok": True, "login_portal": "admin" if user.role == "bdm_manager" else None}
```

- [ ] **Step 4: Run and confirm GREEN**, plus the regression check `tests/test_enh_006_change_password.py tests/test_enh_003_first_time_provisioning.py -k "reset or welcome"`. Expected: pass. If any existing test asserts `== {"ok": True}` exactly, update it to the new always-present shape and note that in the commit message.
- [ ] **Step 5: Commit** — `feat(bdm-001): reset-password names the admin portal for BDM managers`.

---

### Task 7: Web foundations — navigation, middleware, reset redirect, roles dropdown, login heading, `lib/bdm.ts`

**Files:**
- Modify: `apps/web/lib/navigation.ts`, `apps/web/middleware.ts`, `apps/web/components/ResetPasswordForm.tsx:52`, `apps/web/components/WorkflowPanel.tsx:363-367`, `apps/web/app/admin/login/page.tsx`
- Create: `apps/web/lib/bdm.ts`
- Test: `apps/web/tests/lib/navigation.test.ts` (append), `apps/web/tests/lib/middleware.test.ts` (new), `apps/web/tests/components/ResetPasswordForm.test.tsx` (append), `apps/web/tests/lib/bdm.test.ts` (new)

**Interfaces:**
- Produces:
  - From `lib/navigation`: `ROLE_DASHBOARD_PATH.bdm`, `ROLE_DASHBOARD_PATH.bdm_manager`, `BDM_NAV`, `BDM_MANAGER_NAV`, `BDM_SIGN_IN = "/bdm/sign-in"`.
  - From `lib/bdm`: the types `BdmType`, `BdmManagerRef`, `BdmProfile`, `BdmMe`, `BdmTeamRow`, `BdmAdminRow`, `BdmManagerOption`; `BDM_TYPE_LABEL`, `creatableTypes(role)`, `BDMS_URL`, `MANAGERS_URL`, `USERS_URL`, `PAGE_SIZE = 50` and `statusLabel(active)`.

- [ ] **Step 1: Write the failing tests.**

`tests/lib/middleware.test.ts`:

```ts
// @vitest-environment node
import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { config, middleware } from "@/middleware";

const go = (path: string, cookie = false) => {
  const req = new NextRequest(`http://localhost${path}`);
  if (cookie) req.cookies.set("edusphere_access", "x");
  return middleware(req).headers.get("location");
};

describe("middleware /bdm (bdm-001 AC12)", () => {
  it("sends a signed-out manager route to the admin sign-in with next", () => {
    expect(go("/bdm/manager/team?offset=50")).toBe("http://localhost/admin/login?next=%2Fbdm%2Fmanager%2Fteam%3Foffset%3D50");
    expect(go("/bdm/manager")).toBe("http://localhost/admin/login?next=%2Fbdm%2Fmanager");
  });
  it("sends other signed-out /bdm routes to the chooser", () => {
    expect(go("/bdm/my-day")).toBe("http://localhost/bdm/sign-in?next=%2Fbdm%2Fmy-day");
  });
  it("leaves the chooser public, unrelated paths alone, and signed-in visits through", () => {
    expect(go("/bdm/sign-in")).toBeNull();
    expect(go("/bdmx")).toBeNull();
    expect(go("/bdm/my-day", true)).toBeNull();
  });
  it("keeps the old portals unchanged", () => {
    expect(go("/it/admin/users")).toBe("http://localhost/it/login?next=%2Fit%2Fadmin%2Fusers");
    expect(go("/admin/bdms")).toBe("http://localhost/admin/login?next=%2Fadmin%2Fbdms");
    expect(config.matcher).toContain("/bdm/:path*");
  });
});
```

Appended to `tests/lib/navigation.test.ts`:

```ts
import { BDM_MANAGER_NAV, BDM_NAV, PORTAL_NAV, ROLE_DASHBOARD_PATH, SUPER_ADMIN_NAV } from "@/lib/navigation";

describe("bdm-001 navigation", () => {
  it("lands each BDM role on its page (AC05)", () => {
    expect(ROLE_DASHBOARD_PATH.bdm).toBe("/bdm/my-day");
    expect(ROLE_DASHBOARD_PATH.bdm_manager).toBe("/bdm/manager/dashboard");
  });
  it("has BDM navs and a BDMs entry for each admin", () => {
    expect(BDM_NAV.map((x) => x.href)).toEqual(["/bdm/my-day", "/bdm/profile"]);
    expect(BDM_MANAGER_NAV.map((x) => x.href)).toEqual(["/bdm/manager/dashboard", "/bdm/manager/team"]);
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "BDMs", href: "/admin/bdms" });
    expect(PORTAL_NAV["it/admin"]).toContainEqual({ label: "BDMs", href: "/it/admin/bdms" });
    expect(PORTAL_NAV["overseas/admin"]).toContainEqual({ label: "BDMs", href: "/overseas/admin/bdms" });
  });
});
```

Appended to `ResetPasswordForm.test.tsx`, using the file's own `stubFetch`, `json`, `submit` and `push` helpers:

```tsx
describe("bdm-001 login_portal", () => {
  it.each([
    [{ ok: true, login_portal: "admin" }, "/admin/login"],
    [{ ok: true, login_portal: null }, "/overseas/login"],
    [{ ok: true }, "/overseas/login"],
    [{ ok: true, login_portal: "//evil" }, "/overseas/login"],
  ])("routes %j to %s", async (body, path) => {
    stubFetch(json(body, 200));
    render(<ResetPasswordForm division="overseas" />);
    await submit();
    await waitFor(() => expect(push).toHaveBeenCalledWith(path));
  });
});
```

`tests/lib/bdm.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { creatableTypes, statusLabel } from "@/lib/bdm";

describe("lib/bdm", () => {
  it("mirrors the server's creator matrix for display only", () => {
    expect(creatableTypes("super_admin")).toEqual(["agent", "school", "college"]);
    expect(creatableTypes("it_admin")).toEqual(["college"]);
    expect(creatableTypes("overseas_admin")).toEqual(["agent", "school"]);
    expect(creatableTypes("counselor")).toEqual([]);
  });
  it("labels status in words", () => {
    expect(statusLabel(true)).toBe("Active");
    expect(statusLabel(false)).toBe("Inactive");
  });
});
```

- [ ] **Step 2: Run and confirm RED.** `<PATHS>` = `tests/lib/middleware.test.ts tests/lib/navigation.test.ts tests/lib/bdm.test.ts tests/components/ResetPasswordForm.test.tsx`. Expected: the new assertions fail (missing exports, `undefined` dashboard path, `/bdm` not matched, `/overseas/login` pushed for "admin").

- [ ] **Step 3: Implement.**

In `navigation.ts`, inside `ROLE_DASHBOARD_PATH`:

```ts
  // bdm-001 (DEC-SCOPE-052): the BDM CRM roles.
  bdm: "/bdm/my-day",
  bdm_manager: "/bdm/manager/dashboard",
```

and new exports:

```ts
// bdm-001: BDM and BDM-manager sidebars, and the signed-out chooser (College BDMs sign in at /it, Agent/School at /overseas).
export const BDM_NAV: NavItem[] = [{ label: "My Day", href: "/bdm/my-day" }, { label: "Profile", href: "/bdm/profile" }];
export const BDM_MANAGER_NAV: NavItem[] = [{ label: "Dashboard", href: "/bdm/manager/dashboard" }, { label: "Team", href: "/bdm/manager/team" }];
export const BDM_SIGN_IN = "/bdm/sign-in";
```

Add `{label:"BDMs",href:"/it/admin/bdms"}` to `PORTAL_NAV["it/admin"]` and `{label:"BDMs",href:"/overseas/admin/bdms"}` to `PORTAL_NAV["overseas/admin"]`, appended to each `.map(...)` result as `[...(...).map(...), {label:"BDMs", href:...}]`. Insert `{label:"BDMs",href:"/admin/bdms"}` into `SUPER_ADMIN_NAV` before the School Analytics entry. The auto-generated label would read "Bdms", so these entries are written out by hand.

`middleware.ts`:

```ts
import { NextRequest, NextResponse } from "next/server";
export function middleware(req:NextRequest) {
  const p=req.nextUrl.pathname;
  // bdm-001 (AC12): /bdm is protected; /bdm/sign-in is the public chooser.
  const protectedRoute = p!=="/admin/login" && p!=="/bdm/sign-in" && /^\/(it\/(student|trainer|placement|hr|admin)|overseas\/(student|counselor|university|agent|admin)|admin|bdm)(\/|$)/.test(p);
  if (protectedRoute && !req.cookies.get("edusphere_access")) {
    // AGN-008 QA8-07: `next` keeps the query string (e.g. an Applications filter); LoginForm only follows a same-origin path.
    const next=encodeURIComponent(p+req.nextUrl.search);
    // bdm-001: managers (division global) sign in at /admin; a BDM's portal depends on their type, so they pick on /bdm/sign-in.
    if(p.startsWith("/admin")||/^\/bdm\/manager(\/|$)/.test(p)) return NextResponse.redirect(new URL(`/admin/login?next=${next}`,req.url));
    if(p.startsWith("/bdm")) return NextResponse.redirect(new URL(`/bdm/sign-in?next=${next}`,req.url));
    const division=p.startsWith("/overseas")?"overseas":"it";
    return NextResponse.redirect(new URL(`/${division}/login?next=${next}`,req.url));
  }
  return NextResponse.next();
}
export const config={matcher:["/it/:path*","/overseas/:path*","/admin/:path*","/bdm/:path*"]};
```

`ResetPasswordForm.tsx`, replacing line 52:

```ts
    // bdm-001 (spec §5.6): a BDM manager signs in at /admin. Only the literal "admin" is honoured -- never a free-form path.
    router.push(`/${data.login_portal === "admin" ? "admin" : division}/login`);
```

`WorkflowPanel.tsx`: `global: ["super_admin", "bdm_manager"],`, with the comment `// bdm-001: managers have no profile, so the generic form creates them; a BDM needs the BDMs page (profile required).`

`app/admin/login/page.tsx`: change `<h2 style={{marginTop:22}}>Super Admin Login</h2><p className="muted">Restricted administrative access.</p>` to `<h2 style={{marginTop:22}}>Administration sign-in</h2><p className="muted">For Super Admins and BDM Managers.</p>`.

`lib/bdm.ts`:

```ts
// bdm-001 (DEC-SCOPE-052): BDM types, labels and endpoints shared by the BDM pages and the admin BDM page.
export type BdmType = "agent" | "school" | "college";
export type BdmManagerRef = { id: string; full_name: string; active: boolean };
export type BdmProfile = { bdm_type: BdmType; employee_id: string; designation: string | null; department: string | null; territory: string | null; reporting_manager: BdmManagerRef };
export type BdmMe = { id: string; full_name: string; email: string; phone: string | null; active: boolean; division: string; bdm_profile: BdmProfile };
export type BdmTeamRow = { id: string; full_name: string; email: string; phone: string | null; active: boolean; bdm_type: BdmType; employee_id: string; designation: string | null; department: string | null; territory: string | null };
export type BdmAdminRow = BdmTeamRow & { reporting_manager: BdmManagerRef; manager_active: boolean };
export type BdmManagerOption = { id: string; full_name: string };

export const BDM_TYPE_LABEL: Record<BdmType, string> = { agent: "Agent", school: "School", college: "College" };
// Display only -- the API decides (services/bdm.CREATOR_TYPES, D10).
const CREATOR_TYPES: Record<string, BdmType[]> = { super_admin: ["agent", "school", "college"], it_admin: ["college"], overseas_admin: ["agent", "school"] };
export const creatableTypes = (role: string): BdmType[] => CREATOR_TYPES[role] ?? [];
export const statusLabel = (active: boolean) => (active ? "Active" : "Inactive");

export const BDMS_URL = "/api/v1/admin/bdms";
export const MANAGERS_URL = "/api/v1/admin/bdm-managers";
export const USERS_URL = "/api/v1/admin/users";
export const PAGE_SIZE = 50;
```

- [ ] **Step 4: Run and confirm GREEN**, plus the regression check `tests/components/HeaderAuthActions.test.tsx tests/components/LoginForm.next.test.tsx tests/lib/navigation.agent.test.ts tests/lib/safeNext.test.ts` and any `WorkflowPanel*.test.tsx`. Then `npx tsc --noEmit`. Expected: pass.
- [ ] **Step 5: Commit** — `feat(bdm-001): web nav, /bdm middleware, manager reset redirect, roles dropdown`.

---

### Task 8: BDM and manager pages

**Files:**
- Create: `apps/web/components/BdmProfileCard.tsx`, `apps/web/components/BdmTeamTable.tsx`
- Create: `apps/web/app/bdm/my-day/page.tsx`, `app/bdm/profile/page.tsx`, `app/bdm/manager/dashboard/page.tsx`, `app/bdm/manager/team/page.tsx`, `app/bdm/sign-in/page.tsx`
- Test: `apps/web/tests/components/BdmPages.test.tsx`

**Interfaces:**
- Consumes: `serverApi`, `accessUnavailable` (`components/AccessUnavailable`), `PortalShell`, `BDM_NAV`, `BDM_MANAGER_NAV`, `BDM_SIGN_IN`, `lib/bdm` types and labels, `safeNextPath` (`lib/safeNext`).
- Produces: `BdmProfileCard({ me }: { me: BdmMe })` and `BdmTeamTable({ page }: { page: Page<BdmTeamRow> })`, where `Page` comes from `lib/apiErrors`.

- [ ] **Step 1: Write the failing page tests.** Use the `AccountPasswordPage.test.tsx` style: mock `serverApi`, keep the real `ApiError`, and walk the tree with `tests/helpers/elementTree`.

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";

import BdmProfileCard from "@/components/BdmProfileCard";
import BdmTeamTable from "@/components/BdmTeamTable";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import MyDay from "@/app/bdm/my-day/page";
import ManagerDashboard from "@/app/bdm/manager/dashboard/page";
import ManagerTeam from "@/app/bdm/manager/team/page";
import SignIn from "@/app/bdm/sign-in/page";
import { elements, text } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: function PortalShell({ children }: { children: React.ReactNode }) { return children; } }));

const me = { id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, division: "it", bdm_profile: { bdm_type: "college", employee_id: "E-1", designation: null, department: null, territory: "Kochi", reporting_manager: { id: "m1", full_name: "Meera", active: true } } };
const row = (id: string, active = true) => ({ id, full_name: `BDM ${id}`, email: `${id}@x.local`, phone: null, active, bdm_type: "agent", employee_id: `E-${id}`, designation: null, department: null, territory: null });
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 50, offset });

beforeEach(() => { vi.mocked(serverApi).mockReset(); });

describe("bdm-001 pages", () => {
  it("My Day shows the profile summary and the neutral note", async () => {
    vi.mocked(serverApi).mockResolvedValue(me);
    const tree = elements(await MyDay());
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/me");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("College BDM");
    expect(tree.some((el) => el.type === BdmProfileCard)).toBe(true);
    expect(tree.some((el) => el.type === "p" && text(el).includes("appointments, travel and follow-ups will appear here"))).toBe(true);
  });

  it("My Day shows the API's no-profile message and a sign-in link to the chooser", async () => {
    vi.mocked(serverApi).mockRejectedValueOnce(new ApiError("BDM profile not set up — contact your administrator", 403)).mockRejectedValueOnce(new ApiError("x", 401));
    const tree = elements(await MyDay());
    const card = tree.find((el) => (el.props as { message?: string })?.message?.includes("not set up"));
    expect(card).toBeTruthy();
    expect((card!.props as { loginHref: string }).loginHref).toBe("/bdm/sign-in");
  });

  it("manager dashboard counts active and inactive and links to the team", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/auth/me" ? { full_name: "Meera" } : page([row("a"), row("b", false)])) as never);
    const tree = elements(await ManagerDashboard());
    expect(serverApi).toHaveBeenCalledWith("/api/v1/auth/me");
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/manager/team?limit=50");
    expect(tree.find((el) => el.type === PortalShell)!.props.userName).toBe("Meera");
    const all = tree.map(text).join(" ");
    expect(all).toContain("1 active") && expect(all).toContain("1 inactive");
    expect(tree.some((el) => el.type === "a" || (el.props as { href?: string })?.href === "/bdm/manager/team")).toBe(true);
  });

  it("team page passes the offset and renders the table; empty state when none", async () => {
    const teams = [page([row("a")], 51, 50), page([])];
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/auth/me" ? { full_name: "Meera" } : teams.shift()) as never);
    let tree = elements(await ManagerTeam({ searchParams: Promise.resolve({ offset: "50" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/manager/team?limit=50&offset=50");
    expect(tree.some((el) => el.type === BdmTeamTable)).toBe(true);
    tree = elements(await ManagerTeam({ searchParams: Promise.resolve({}) }));
    expect(tree.map(text).join(" ")).toContain("No BDMs report to you yet.");
  });

  it("team page clamps a junk offset to 0", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/auth/me" ? { full_name: "Meera" } : page([])) as never);
    await ManagerTeam({ searchParams: Promise.resolve({ offset: "-5abc" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/manager/team?limit=50&offset=0");
  });

  it("sign-in chooser carries a safe next and drops an unsafe one", async () => {
    let tree = elements(await SignIn({ searchParams: Promise.resolve({ next: "/bdm/my-day" }) }));
    const hrefs = tree.map((el) => (el.props as { href?: string })?.href).filter(Boolean);
    expect(hrefs).toContain("/it/login?next=%2Fbdm%2Fmy-day");
    expect(hrefs).toContain("/overseas/login?next=%2Fbdm%2Fmy-day");
    tree = elements(await SignIn({ searchParams: Promise.resolve({ next: "//evil.example" }) }));
    expect(tree.map((el) => (el.props as { href?: string })?.href).filter(Boolean)).toEqual(expect.arrayContaining(["/it/login", "/overseas/login"]));
  });
});
```

And a component test for the table (`tests/components/BdmTeamTable.test.tsx`), which renders through Testing Library:

```tsx
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import BdmTeamTable from "@/components/BdmTeamTable";

const row = (id: string, active: boolean) => ({ id, full_name: `BDM ${id}`, email: "", phone: "+91 1", active, bdm_type: "school" as const, employee_id: `E-${id}`, designation: null, department: null, territory: "Kochi" });

describe("BdmTeamTable", () => {
  it("renders a labelled, focusable region with status in words and a pager", () => {
    render(<BdmTeamTable page={{ items: [row("a", true), row("b", false)], total: 60, limit: 50, offset: 0 }} />);
    const region = screen.getByRole("region", { name: "Team" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(within(region).getByText("Inactive")).toBeInTheDocument();
    const pager = screen.getByRole("navigation", { name: "Team pages" });
    expect(within(pager).getByText("Showing 1–2 of 60")).toBeInTheDocument();
    expect(within(pager).getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/bdm/manager/team?offset=50");
  });
});
```

- [ ] **Step 2: Run and confirm RED.** Expected: the imports fail (the pages and components don't exist yet).

- [ ] **Step 3: Implement.**

`components/BdmProfileCard.tsx`:

```tsx
import { BDM_TYPE_LABEL, statusLabel, type BdmMe } from "@/lib/bdm";

// bdm-001: the BDM's §1 profile as label/value pairs (a <dl>, so assistive tech announces the pairs). Read-only.
export default function BdmProfileCard({ me }: { me: BdmMe }) {
  const p = me.bdm_profile;
  const rows: [string, string][] = [
    ["Name", me.full_name], ["Employee ID", p.employee_id], ["Module", BDM_TYPE_LABEL[p.bdm_type]],
    ["Designation", p.designation ?? "—"], ["Department", p.department ?? "—"], ["Territory", p.territory ?? "—"],
    ["Mobile", me.phone ?? "—"], ["Email", me.email],
    ["Reporting manager", `${p.reporting_manager.full_name}${p.reporting_manager.active ? "" : " (inactive)"}`],
    ["Status", statusLabel(me.active)],
  ];
  return (
    <div className="card" style={{ padding: 16 }}>
      <dl style={{ display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "8px 16px", margin: 0 }}>
        {rows.map(([label, value]) => [<dt key={`${label}-t`} className="muted">{label}</dt>, <dd key={`${label}-d`} style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>])}
      </dl>
    </div>
  );
}
```

`components/BdmTeamTable.tsx`:

```tsx
import Link from "next/link";
import type { Page } from "@/lib/apiErrors";
import { BDM_TYPE_LABEL, statusLabel, type BdmTeamRow } from "@/lib/bdm";

// bdm-001 (AC06): a manager's BDMs. Server-rendered; paging is a link (?offset=) so a page can be shared and needs no client JS.
export default function BdmTeamTable({ page }: { page: Page<BdmTeamRow> }) {
  const end = page.offset + page.items.length;
  return (
    <>
      <div className="table-wrap" role="region" aria-label="Team" tabIndex={0}>
        <table>
          <caption className="muted" style={{ textAlign: "left" }}>BDMs who report to you</caption>
          <thead><tr><th scope="col">Name</th><th scope="col">Employee ID</th><th scope="col">Module</th><th scope="col">Territory</th><th scope="col">Mobile</th><th scope="col">Status</th></tr></thead>
          <tbody>
            {page.items.map((r) => (
              <tr key={r.id}>
                <td>{r.full_name}</td><td>{r.employee_id}</td><td>{BDM_TYPE_LABEL[r.bdm_type]}</td><td>{r.territory ?? "—"}</td><td>{r.phone ?? "—"}</td>
                <td><span className="badge">{statusLabel(r.active)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {page.total > page.limit && (
        <nav aria-label="Team pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
          <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{end} of {page.total}</span>
          {page.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={`/bdm/manager/team?offset=${Math.max(0, page.offset - page.limit)}`}>Previous</Link>}
          {end < page.total && <Link className="btn secondary small" aria-label="Next page" href={`/bdm/manager/team?offset=${end}`}>Next</Link>}
        </nav>
      )}
    </>
  );
}
```

`app/bdm/my-day/page.tsx`:

```tsx
import BdmProfileCard from "@/components/BdmProfileCard";
import PortalShell from "@/components/PortalShell";
import { accessUnavailable } from "@/components/AccessUnavailable";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { BDM_NAV, BDM_SIGN_IN } from "@/lib/navigation";

// bdm-001 (AC05, B2): the BDM landing page -- a minimal shell; bdm-014 fills My Day. The API is the gate: any other role, or a
// BDM without a profile, gets its 403 message here with a link home.
export default async function BdmMyDayPage() {
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  return (
    <PortalShell nav={BDM_NAV} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">My Day</div>
            <h2>Welcome, {me.full_name}</h2>
            <p className="muted">Your appointments, travel and follow-ups will appear here.</p>
          </div>
        </div>
        <BdmProfileCard me={me} />
      </div>
    </PortalShell>
  );
}
```

`app/bdm/profile/page.tsx` is the same shell with the eyebrow "Profile", h2 "My profile", the muted line "Your details as recorded by your administrator. Contact them to change anything." and `<BdmProfileCard me={me} />`.

`app/bdm/manager/dashboard/page.tsx`:

```tsx
import Link from "next/link";
import PortalShell from "@/components/PortalShell";
import { accessUnavailable } from "@/components/AccessUnavailable";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import type { BdmTeamRow } from "@/lib/bdm";
import type { User } from "@/lib/types";
import { BDM_MANAGER_NAV } from "@/lib/navigation";

// bdm-001 (AC05, B2): the manager landing page -- team counts; bdm-023 adds the management dashboard.
export default async function BdmManagerDashboardPage() {
  let user: User, team: Page<BdmTeamRow>;
  try {
    [user, team] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Page<BdmTeamRow>>("/api/v1/bdm/manager/team?limit=50")]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const active = team.items.filter((r) => r.active).length;
  const inactive = team.items.length - active;
  return (
    <PortalShell nav={BDM_MANAGER_NAV} roleLabel="BDM Manager" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title"><div><div className="eyebrow">Dashboard</div><h2>Your team</h2>
          <p className="muted">{team.total === 0 ? "No BDMs report to you yet." : `${team.total} BDM${team.total === 1 ? "" : "s"} report to you: ${active} active, ${inactive} inactive${team.total > team.items.length ? " on this page" : ""}.`}</p>
        </div></div>
        {team.total > 0 && <Link className="btn" href="/bdm/manager/team">View team</Link>}
      </div>
    </PortalShell>
  );
}
```

`app/bdm/manager/team/page.tsx`:

```tsx
import BdmTeamTable from "@/components/BdmTeamTable";
import PortalShell from "@/components/PortalShell";
import { accessUnavailable } from "@/components/AccessUnavailable";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { PAGE_SIZE, type BdmTeamRow } from "@/lib/bdm";
import type { User } from "@/lib/types";
import { BDM_MANAGER_NAV } from "@/lib/navigation";

export default async function BdmManagerTeamPage({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  const raw = Number.parseInt((await searchParams).offset ?? "0", 10);
  const offset = Number.isFinite(raw) && raw > 0 ? raw : 0;
  let user: User, team: Page<BdmTeamRow>;
  try {
    [user, team] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Page<BdmTeamRow>>(`/api/v1/bdm/manager/team?limit=${PAGE_SIZE}&offset=${offset}`)]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={BDM_MANAGER_NAV} roleLabel="BDM Manager" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title"><div><div className="eyebrow">Team</div><h2>BDMs who report to you</h2></div></div>
        {team.total === 0 ? <p className="empty" role="status">No BDMs report to you yet.</p> : <BdmTeamTable page={team} />}
      </div>
    </PortalShell>
  );
}
```

The manager pages make two `serverApi` calls (`/auth/me` plus the team); the Step 1 mocks answer by path. My Day and Profile need only `/bdm/me`, because it contains the name.

`app/bdm/sign-in/page.tsx`:

```tsx
import Link from "next/link";
import { safeNextPath } from "@/lib/safeNext";

// bdm-001 (B9, AC12): a signed-out BDM picks their portal -- College BDMs belong to the IT division, Agent/School BDMs to Overseas.
export default async function BdmSignInPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const next = safeNextPath((await searchParams).next ?? null);
  const suffix = next ? `?next=${encodeURIComponent(next)}` : "";
  return (
    <div className="auth-form-wrap" style={{ minHeight: "100vh" }}>
      <div className="auth-card">
        <Link href="/" className="muted">← Corporate website</Link>
        <h1 style={{ marginTop: 22, fontSize: 28 }}>BDM sign-in</h1>
        <p className="muted">Choose the portal for your module. BDM Managers sign in at <Link href={`/admin/login${suffix}`}>Administration</Link>.</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 16 }}>
          <Link className="btn" style={{ flex: "1 1 220px", textAlign: "center" }} href={`/it/login${suffix}`}>College BDM</Link>
          <Link className="btn" style={{ flex: "1 1 220px", textAlign: "center" }} href={`/overseas/login${suffix}`}>Agent / School BDM</Link>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run and confirm GREEN**, then `tsc --noEmit` and `eslint` on the new files.
- [ ] **Step 5: REFACTOR.** `my-day` and `profile` share their fetch-and-shell code. If both stay under about 30 lines, leave them; otherwise extract a `BdmSelfPage({ eyebrow, title, note })` server component. Re-run.
- [ ] **Step 6: Commit** — `feat(bdm-001): BDM My Day, profile, manager dashboard/team and sign-in chooser`.

---

### Task 9: Admin BDM page — `AdminBdmPanel`, `AdminBdmCreateForm`, `AdminBdmRow`

**Files:**
- Create: `apps/web/components/AdminBdmPanel.tsx`, `AdminBdmCreateForm.tsx`, `AdminBdmRow.tsx`, `AdminBdmPage.tsx` (the shared server page body)
- Create: `apps/web/app/admin/bdms/page.tsx`, `apps/web/app/it/admin/bdms/page.tsx`, `apps/web/app/overseas/admin/bdms/page.tsx`
- Test: `apps/web/tests/components/AdminBdmPanel.test.tsx`, `AdminBdmCreateForm.test.tsx`, `AdminBdmRow.test.tsx`, `AdminBdmPage.test.tsx`

**Interfaces:**
- Consumes:
  - `lib/bdm` (Task 7);
  - `lib/apiErrors`: `sendJson(url, method, body) -> SendOutcome`, `detailMessage(detail, fallback)`, `NOT_COMPLETED`, `Page<T>`, `isPage(data)`;
  - `lib/welcomeLink`: `welcomeLinkFeedback`, `toneClass`, `Feedback`;
  - `lib/useFocusAfterRender`: `useFocusAfterRender() -> (...ids) => void`;
  - `lib/usersChanged`: `announceUsersChanged()`.
- Produces:
  - `AdminBdmPanel({ role }: { role: string })`;
  - `AdminBdmCreateForm({ role, managers, onCreated }: { role: string; managers: BdmManagerOption[] | null; onCreated: () => void })`;
  - `AdminBdmRow({ row, managers, onChanged }: { row: BdmAdminRow; managers: BdmManagerOption[] | null; onChanged: (notice: string) => void })`;
  - `AdminBdmPage({ roles, nav, roleLabel }: { roles: string[]; nav: NavItem[]; roleLabel: string })` (async server component).

- [ ] **Step 1: Write the failing tests.** Follow the `AgentStaffPanel.test.tsx` style (stubbed `fetch`, `res()` and `page()` helpers).

`AdminBdmPanel.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AdminBdmPanel from "@/components/AdminBdmPanel";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pg = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 50, offset });
const row = (n: number, managerActive = true) => ({ id: `b${n}`, full_name: `BDM ${n}`, email: `b${n}@x.local`, phone: null, active: true, bdm_type: "college", employee_id: `E-${n}`, designation: null, department: null, territory: "Kochi", reporting_manager: { id: "m1", full_name: "Meera", active: managerActive }, manager_active: managerActive });
const route = (bdms: Response[], managers = res(pg([{ id: "m1", full_name: "Meera" }]))) => {
  const mock = vi.fn((url: string) => Promise.resolve(url.startsWith("/api/v1/admin/bdm-managers") ? managers.clone() : bdms.shift()!));
  vi.stubGlobal("fetch", mock);
  return mock;
};

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("AdminBdmPanel (bdm-001 AC13)", () => {
  it("shows loading, then rows with a no-active-manager badge", async () => {
    route([res(pg([row(1), row(2, false)]))]);
    render(<AdminBdmPanel role="super_admin" />);
    expect(screen.getByText("Loading BDMs…")).toBeInTheDocument();
    expect(await screen.findByText("E-1")).toBeInTheDocument();
    expect(screen.getByText("No active manager")).toBeInTheDocument();
  });
  it("shows the empty state", async () => {
    route([res(pg([]))]);
    render(<AdminBdmPanel role="it_admin" />);
    expect(await screen.findByText("No BDMs yet. Use Create BDM above to add the first one.")).toBeInTheDocument();
  });
  it("shows an error with Retry, including a non-page body", async () => {
    route([res({ detail: "boom" }, 500), res("<html>"), res(pg([row(1)]))]);
    render(<AdminBdmPanel role="super_admin" />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("E-1")).toBeInTheDocument();
  });
  it("pages, keeping the previous rows visible while the next page loads", async () => {
    const fifty = Array.from({ length: 50 }, (_, i) => row(i + 1));
    const mock = route([res(pg(fifty, 51)), res(pg([row(51)], 51, 50))]);
    render(<AdminBdmPanel role="super_admin" />);
    const pager = await screen.findByRole("navigation", { name: "BDM pages" });
    fireEvent.click(within(pager).getByRole("button", { name: "Next page" }));
    expect(screen.getByText("E-1")).toBeInTheDocument();
    expect(await screen.findByText("E-51")).toBeInTheDocument();
    expect(mock).toHaveBeenCalledWith("/api/v1/admin/bdms?limit=50&offset=50");
  });
});
```

`AdminBdmCreateForm.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AdminBdmCreateForm from "@/components/AdminBdmCreateForm";
import * as usersChanged from "@/lib/usersChanged";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const managers = [{ id: "m1", full_name: "Meera" }];
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function fill() {
  fireEvent.change(screen.getByLabelText("Full name (required)"), { target: { value: "Asha" } });
  fireEvent.change(screen.getByLabelText("Email (required)"), { target: { value: "asha@x.local" } });
  fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: "E-9" } });
  fireEvent.change(screen.getByLabelText("Reporting manager (required)"), { target: { value: "m1" } });
}

describe("AdminBdmCreateForm (bdm-001)", () => {
  it("offers only the types the admin may create; a single type is fixed text", () => {
    const { unmount } = render(<AdminBdmCreateForm role="overseas_admin" managers={managers} onCreated={() => {}} />);
    expect(screen.getAllByRole("option", { name: /Agent|School/ })).toHaveLength(2);
    unmount();
    render(<AdminBdmCreateForm role="it_admin" managers={managers} onCreated={() => {}} />);
    expect(screen.queryByLabelText("Module (required)")).toBeNull();
    expect(screen.getByText("College")).toBeInTheDocument();
  });
  it("disables submit and explains when there is no active manager", () => {
    render(<AdminBdmCreateForm role="super_admin" managers={[]} onCreated={() => {}} />);
    expect(screen.getByText("No active BDM manager — a Super Admin must create one first.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create BDM" })).toBeDisabled();
  });
  it("posts the nested profile, shows the link feedback, announces the change", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ id: "b9", email_status: "sent", bdm_profile: {} }, 201));
    vi.stubGlobal("fetch", fetchMock);
    const announce = vi.spyOn(usersChanged, "announceUsersChanged");
    const onCreated = vi.fn();
    render(<AdminBdmCreateForm role="it_admin" managers={managers} onCreated={onCreated} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Create BDM" }));
    expect(await screen.findByText(/set-password link was emailed/)).toBeInTheDocument();
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toMatchObject({ role: "bdm", full_name: "Asha", email: "asha@x.local", bdm_profile: { bdm_type: "college", employee_id: "E-9", reporting_manager_user_id: "m1" } });
    expect(body).not.toHaveProperty("password");
    expect(announce).toHaveBeenCalled();
    expect(onCreated).toHaveBeenCalled();
  });
  it("shows a 409 inline, focuses it, and keeps the entry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Employee ID already exists" }, 409)));
    render(<AdminBdmCreateForm role="it_admin" managers={managers} onCreated={() => {}} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Create BDM" }));
    const msg = await screen.findByText("Employee ID already exists");
    await waitFor(() => expect(msg).toHaveFocus());
    expect(screen.getByLabelText("Employee ID (required)")).toHaveValue("E-9");
  });
  it("keeps the entry and says so on a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<AdminBdmCreateForm role="it_admin" managers={managers} onCreated={() => {}} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Create BDM" }));
    expect(await screen.findByText(/your entry is kept/)).toBeInTheDocument();
    expect(screen.getByLabelText("Full name (required)")).toHaveValue("Asha");
  });
});
```

`AdminBdmRow.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AdminBdmRow from "@/components/AdminBdmRow";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = { id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, bdm_type: "college" as const, employee_id: "E-1", designation: null, department: null, territory: "Kochi", reporting_manager: { id: "m1", full_name: "Meera", active: true }, manager_active: true };
const managers = [{ id: "m1", full_name: "Meera" }, { id: "m2", full_name: "Ravi" }];
const mount = (onChanged = vi.fn()) => render(<table><tbody><AdminBdmRow row={row} managers={managers} onChanged={onChanged} /></tbody></table>);
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("AdminBdmRow (bdm-001)", () => {
  it("edits inline with the type read-only, and focuses the first field", () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    expect(screen.getByLabelText("Full name (required)")).toHaveFocus();
    expect(screen.queryByLabelText("Module")).toBeNull();
    expect(screen.getByText("College (cannot be changed)")).toBeInTheDocument();
  });
  it("Esc cancels and returns focus to Edit", () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    fireEvent.keyDown(screen.getByLabelText("Full name (required)"), { key: "Escape" });
    expect(screen.getByRole("button", { name: "Edit Asha" })).toHaveFocus();
  });
  it("saves user fields and profile in one PATCH, and only reports after success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    mount(onChanged);
    fireEvent.click(screen.getByRole("button", { name: "Edit Asha" }));
    fireEvent.change(screen.getByLabelText("Territory"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Reporting manager (required)"), { target: { value: "m2" } });
    expect(onChanged).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Saved Asha."));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/admin/users/b1");
    expect(JSON.parse(init.body)).toEqual({ full_name: "Asha", phone: null, bdm_profile: { employee_id: "E-1", designation: null, department: null, territory: null, reporting_manager_user_id: "m2" } });
  });
  it("deactivation needs a second, explicit confirm", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Asha" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(/can no longer sign in/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ active: false }));
  });
});
```

`AdminBdmPage.test.tsx`: mock `serverApi`. A user with a role outside `roles` gets `accessDenied`, whose message includes "Administrator role required". An allowed role renders `AdminBdmPanel` with `role` passed through.

- [ ] **Step 2: Run and confirm RED.** Expected: the imports fail.

- [ ] **Step 3: Implement.**

`AdminBdmPanel.tsx`:

```tsx
"use client";
import { useCallback, useEffect, useState } from "react";
import AdminBdmCreateForm from "@/components/AdminBdmCreateForm";
import AdminBdmRow from "@/components/AdminBdmRow";
import { isPage, type Page } from "@/lib/apiErrors";
import { BDMS_URL, MANAGERS_URL, PAGE_SIZE, type BdmAdminRow, type BdmManagerOption } from "@/lib/bdm";

// bdm-001 (spec §6.3): admins' BDM list -- loading / error+Retry / empty / pager (AgentStaffPanel's pattern). The API scopes rows
// to the types this admin manages; nothing here filters for security.
export default function AdminBdmPanel({ role }: { role: string }) {
  const [data, setData] = useState<Page<BdmAdminRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [offset, setOffset] = useState(0);
  const [managers, setManagers] = useState<BdmManagerOption[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback((at: number) => {
    setLoadFailed(false);
    fetch(`${BDMS_URL}?limit=${PAGE_SIZE}&offset=${at}`)
      .then(async (r) => { const body = await r.json().catch(() => null); if (!r.ok || !isPage<BdmAdminRow>(body)) throw new Error(); setData(body); })
      .catch(() => setLoadFailed(true));
  }, []);
  useEffect(() => { load(offset); }, [load, offset]);
  useEffect(() => {
    fetch(`${MANAGERS_URL}?limit=100`).then((r) => r.json()).then((b) => setManagers(isPage<BdmManagerOption>(b) ? b.items : [])).catch(() => setManagers([]));
  }, []);
  const reload = () => load(offset);

  return (
    <>
      <AdminBdmCreateForm role={role} managers={managers} onCreated={reload} />
      <div className="action-card" aria-busy={data === null && !loadFailed}>
        <h3>BDMs</h3>
        <div className={notice ? "form-message" : undefined} role="status" aria-live="polite">{notice}</div>
        {loadFailed ? (
          <><p className="form-error" role="alert">Unable to load BDMs.</p><button className="btn secondary small" onClick={reload}>Retry</button></>
        ) : data === null ? (
          <p className="muted">Loading BDMs…</p>
        ) : data.total === 0 ? (
          <p className="empty" role="status">No BDMs yet. Use Create BDM above to add the first one.</p>
        ) : (
          <>
            <div className="table-wrap" role="region" aria-label="BDMs" tabIndex={0}>
              <table>
                <thead><tr><th scope="col">Name</th><th scope="col">Employee ID</th><th scope="col">Module</th><th scope="col">Territory</th><th scope="col">Manager</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>{data.items.map((r) => <AdminBdmRow key={r.id} row={r} managers={managers} onChanged={(text) => { setNotice(text); reload(); }} />)}</tbody>
              </table>
            </div>
            {data.total > PAGE_SIZE && (
              <nav aria-label="BDM pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
                <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
                <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
              </nav>
            )}
          </>
        )}
      </div>
    </>
  );
}
```

Check that `.sr-only` exists in `globals.css` (`grep -n "sr-only" apps/web/app/globals.css`). If it doesn't, use `aria-label="Actions"` on the `<th>` instead. Don't add CSS.

`AdminBdmCreateForm.tsx`:

```tsx
"use client";
import { useState } from "react";
import { NOT_COMPLETED, detailMessage, sendJson } from "@/lib/apiErrors";
import { BDM_TYPE_LABEL, USERS_URL, creatableTypes, type BdmManagerOption } from "@/lib/bdm";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { announceUsersChanged } from "@/lib/usersChanged";
import { toneClass, welcomeLinkFeedback, type Feedback } from "@/lib/welcomeLink";

const text = (form: FormData, name: string) => String(form.get(name) ?? "").trim();
const optional = (form: FormData, name: string) => text(form, name) || null;

// bdm-001 (AC01, spec §6.3): creates a BDM through POST /admin/users with the nested profile. No password field exists.
export default function AdminBdmCreateForm({ role, managers, onCreated }: { role: string; managers: BdmManagerOption[] | null; onCreated: () => void }) {
  const types = creatableTypes(role);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const focus = useFocusAfterRender();
  const noManagers = managers !== null && managers.length === 0;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    setBusy(true);
    const outcome = await sendJson(USERS_URL, "POST", {
      role: "bdm", full_name: text(form, "full_name"), email: text(form, "email"), phone: optional(form, "phone"),
      bdm_profile: { bdm_type: text(form, "bdm_type"), employee_id: text(form, "employee_id"), designation: optional(form, "designation"),
        department: optional(form, "department"), territory: optional(form, "territory"), reporting_manager_user_id: text(form, "manager") },
    });
    setBusy(false);
    if (!outcome.ok) {
      setFeedback({ text: outcome.status ? outcome.message : NOT_COMPLETED, tone: "error" });
      focus("bdm-create-feedback");
      return;
    }
    setFeedback(welcomeLinkFeedback("BDM created.", outcome.data));
    formEl.reset();
    announceUsersChanged();
    onCreated();
    focus("bdm-create-feedback");
  }

  return (
    <form className="action-card form" onSubmit={submit} aria-describedby="bdm-create-feedback" noValidate={false}>
      <h3>Create BDM</h3>
      <div className="field"><label htmlFor="bdm-name">Full name (required)</label><input id="bdm-name" name="full_name" required maxLength={160} disabled={busy} /></div>
      <div className="field"><label htmlFor="bdm-email">Email (required)</label><input id="bdm-email" name="email" type="email" required maxLength={255} autoComplete="off" disabled={busy} /></div>
      <div className="field"><label htmlFor="bdm-phone">Mobile</label><input id="bdm-phone" name="phone" type="tel" inputMode="tel" maxLength={40} disabled={busy} /></div>
      {types.length === 1 ? (
        <div className="field"><span className="muted">Module</span><strong>{BDM_TYPE_LABEL[types[0]]}</strong><input type="hidden" name="bdm_type" value={types[0]} /></div>
      ) : (
        <div className="field"><label htmlFor="bdm-type">Module (required)</label>
          <select id="bdm-type" name="bdm_type" required disabled={busy}>{types.map((t) => <option key={t} value={t}>{BDM_TYPE_LABEL[t]}</option>)}</select></div>
      )}
      <div className="field"><label htmlFor="bdm-employee-id">Employee ID (required)</label><input id="bdm-employee-id" name="employee_id" required maxLength={40} disabled={busy} /></div>
      <div className="field"><label htmlFor="bdm-designation">Designation</label><input id="bdm-designation" name="designation" maxLength={120} disabled={busy} /></div>
      <div className="field"><label htmlFor="bdm-department">Department</label><input id="bdm-department" name="department" maxLength={120} disabled={busy} /></div>
      <div className="field"><label htmlFor="bdm-territory">Territory</label><input id="bdm-territory" name="territory" maxLength={120} disabled={busy} /></div>
      <div className="field"><label htmlFor="bdm-manager">Reporting manager (required)</label>
        <select id="bdm-manager" name="manager" required disabled={busy || managers === null || noManagers} defaultValue="">
          <option value="" disabled>{managers === null ? "Loading managers…" : "Select a manager"}</option>
          {(managers ?? []).map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
        </select>
        {noManagers && <p className="muted" style={{ fontSize: 13 }}>No active BDM manager — a Super Admin must create one first.</p>}
      </div>
      <button className="btn" disabled={busy || noManagers || managers === null}>{busy ? "Creating…" : "Create BDM"}</button>
      <div id="bdm-create-feedback" tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>{feedback?.text}</div>
    </form>
  );
}
```

`sendJson` returns `{ok:false, status?}`. A missing `status` means a network failure, which shows `NOT_COMPLETED`. Check the `SendOutcome` type in `lib/apiErrors.ts:35-60` and adjust if its fields differ.

`AdminBdmRow.tsx`:

```tsx
"use client";
import { useRef, useState } from "react";
import { NOT_COMPLETED, sendJson } from "@/lib/apiErrors";
import { BDM_TYPE_LABEL, USERS_URL, statusLabel, type BdmAdminRow, type BdmManagerOption } from "@/lib/bdm";

const value = (form: FormData, name: string) => String(form.get(name) ?? "").trim();
const optional = (form: FormData, name: string) => value(form, name) || null;

// bdm-001 (spec §6.3): one BDM -- view, inline edit (type read-only, B7), activate/deactivate with an inline confirm.
export default function AdminBdmRow({ row, managers, onChanged }: { row: BdmAdminRow; managers: BdmManagerOption[] | null; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const editButton = useRef<HTMLButtonElement>(null);
  const errorId = `bdm-row-error-${row.id}`;

  function close() { setEditing(false); setError(null); setTimeout(() => editButton.current?.focus(), 0); }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    const outcome = await sendJson(`${USERS_URL}/${row.id}`, "PATCH", {
      full_name: value(form, "full_name"), phone: optional(form, "phone"),
      bdm_profile: { employee_id: value(form, "employee_id"), designation: optional(form, "designation"), department: optional(form, "department"),
        territory: optional(form, "territory"), reporting_manager_user_id: value(form, "manager") },
    });
    setBusy(false);
    if (!outcome.ok) { setError(outcome.status ? outcome.message : NOT_COMPLETED); return; }
    close();
    onChanged(`Saved ${row.full_name}.`);
  }

  async function setActive(active: boolean) {
    setBusy(true);
    const outcome = await sendJson(`${USERS_URL}/${row.id}`, "PATCH", { active });
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) { setError(outcome.status ? outcome.message : NOT_COMPLETED); return; }
    onChanged(`${active ? "Reactivated" : "Deactivated"} ${row.full_name}.`);
  }

  if (editing) {
    return (
      <tr><td colSpan={7}>
        <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={errorId}>
          <div className="field"><label htmlFor={`n-${row.id}`}>Full name (required)</label><input id={`n-${row.id}`} name="full_name" defaultValue={row.full_name} required maxLength={160} autoFocus disabled={busy} /></div>
          <div className="field"><label htmlFor={`p-${row.id}`}>Mobile</label><input id={`p-${row.id}`} name="phone" type="tel" inputMode="tel" defaultValue={row.phone ?? ""} maxLength={40} disabled={busy} /></div>
          <div className="field"><span className="muted">Module</span><strong>{BDM_TYPE_LABEL[row.bdm_type]} (cannot be changed)</strong></div>
          <div className="field"><label htmlFor={`e-${row.id}`}>Employee ID (required)</label><input id={`e-${row.id}`} name="employee_id" defaultValue={row.employee_id} required maxLength={40} disabled={busy} /></div>
          <div className="field"><label htmlFor={`d-${row.id}`}>Designation</label><input id={`d-${row.id}`} name="designation" defaultValue={row.designation ?? ""} maxLength={120} disabled={busy} /></div>
          <div className="field"><label htmlFor={`dp-${row.id}`}>Department</label><input id={`dp-${row.id}`} name="department" defaultValue={row.department ?? ""} maxLength={120} disabled={busy} /></div>
          <div className="field"><label htmlFor={`t-${row.id}`}>Territory</label><input id={`t-${row.id}`} name="territory" defaultValue={row.territory ?? ""} maxLength={120} disabled={busy} /></div>
          <div className="field"><label htmlFor={`m-${row.id}`}>Reporting manager (required)</label>
            <select id={`m-${row.id}`} name="manager" defaultValue={row.reporting_manager.id} required disabled={busy}>
              {!row.manager_active && <option value={row.reporting_manager.id}>{row.reporting_manager.full_name} (inactive)</option>}
              {(managers ?? []).map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
            </select></div>
          <div id={errorId} className={error ? "form-error" : undefined} role="alert">{error}</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            <button type="button" className="btn secondary small" onClick={close} disabled={busy}>Cancel</button>
          </div>
        </form>
      </td></tr>
    );
  }
  return (
    <tr>
      <td>{row.full_name}<br /><span className="muted" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{row.email}</span></td>
      <td>{row.employee_id}</td><td>{BDM_TYPE_LABEL[row.bdm_type]}</td><td>{row.territory ?? "—"}</td>
      <td>{row.reporting_manager.full_name}{!row.manager_active && <> <span className="badge">No active manager</span></>}</td>
      <td><span className="badge">{statusLabel(row.active)}</span></td>
      <td>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button ref={editButton} type="button" className="btn secondary small" aria-label={`Edit ${row.full_name}`} onClick={() => setEditing(true)} disabled={busy}>Edit</button>
          {row.active && !confirming && <button type="button" className="btn secondary small" aria-label={`Deactivate ${row.full_name}`} onClick={() => setConfirming(true)} disabled={busy}>Deactivate</button>}
          {!row.active && <button type="button" className="btn secondary small" aria-label={`Reactivate ${row.full_name}`} onClick={() => setActive(true)} disabled={busy}>Reactivate</button>}
        </div>
        {confirming && (
          <div role="group" aria-label={`Confirm deactivating ${row.full_name}`} style={{ marginTop: 6 }}>
            <p className="muted" style={{ fontSize: 13 }}>Their reporting line and data stay; they can no longer sign in.</p>
            <button type="button" className="btn small" onClick={() => setActive(false)} disabled={busy}>Confirm deactivate</button>{" "}
            <button type="button" className="btn secondary small" onClick={() => setConfirming(false)} disabled={busy}>Keep active</button>
          </div>
        )}
        {error && !editing && <p className="form-error" role="alert">{error}</p>}
      </td>
    </tr>
  );
}
```

On save, the PATCH sends only the profile keys that can be edited. `bdm_type` is never sent.

`AdminBdmPage.tsx` (server):

```tsx
import AdminBdmPanel from "@/components/AdminBdmPanel";
import PortalShell from "@/components/PortalShell";
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import { serverApi } from "@/lib/api";
import type { NavItem } from "@/lib/navigation";
import type { User } from "@/lib/types";

// bdm-001: the one body behind /admin/bdms, /it/admin/bdms and /overseas/admin/bdms (static routes win over [module]/[section]).
// The role check only spares other roles a screen that can only fail; the API enforces it (D10).
export default async function AdminBdmPage({ roles, nav, roleLabel }: { roles: string[]; nav: NavItem[]; roleLabel: string }) {
  let user: User;
  try { user = await serverApi<User>("/api/v1/auth/me"); } catch (e) { return accessUnavailable(e); }
  if (!roles.includes(user.role)) return accessDenied(user, `${roleLabel} role required`);
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content"><div className="portal-title"><div>
        <div className="eyebrow">Workspace</div><h2>BDMs</h2>
        <p className="muted">Create Business Development Managers, set their reporting manager and keep their profiles current. Each new BDM gets an emailed set-password link.</p>
      </div></div></div>
      <div className="portal-content action-center"><div className="action-grid"><AdminBdmPanel role={user.role} /></div></div>
    </PortalShell>
  );
}
```

The three route pages:
- `app/admin/bdms/page.tsx`: `export default function Page() { return <AdminBdmPage roles={["super_admin"]} nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" />; }`
- `/it/admin/bdms`: `roles={["it_admin","super_admin"]} nav={PORTAL_NAV["it/admin"]} roleLabel="IT Administrator"`
- `/overseas/admin/bdms`: `roles={["overseas_admin","super_admin"]} nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator"`

Before writing these, check the label strings against `app/it/admin/[section]/page.tsx` and use the same ones.

- [ ] **Step 4: Run and confirm GREEN** (the four new test files), then `tsc` and `eslint` on the new files, then the regression check `tests/components/AdminUserManagementPanel.test.tsx` and the `AgentStaff*` tests (shared helpers are untouched). Expected: pass.
- [ ] **Step 5: REFACTOR.** Each file stays under about 160 lines. The `text`/`optional` helpers appear in both the form and the row: move them to `lib/bdm.ts` as `formText` and `formOptional`, then re-run.
- [ ] **Step 6: Commit** — `feat(bdm-001): admin BDM page — create, list, inline edit, deactivate`.

---

### Task 10: End-to-end journey (Playwright)

**Files:**
- Create: `apps/web/tests/e2e/bdm-001-bdm-profile.spec.ts`

**Interfaces:**
- Consumes: `tests/e2e/helpers/welcome` (`E2E_PASSWORD`, `activateWithToken`); the seeded `superadmin@edusphere.local` / `Demo@123`. This needs a running worktree stack, which **the user starts**; I'll give them the command.

- [ ] **Step 1: Write the spec.**

```ts
import { expect, test, type Page } from "@playwright/test";
import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-001 (AC01, AC05, AC06, AC12): a Super Admin creates a manager and a College BDM; each activates from its link and lands on
// its page; the BDM is in the manager's team. Throwaway accounts through the real admin API.
async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await expect(page.getByRole("heading", { name: "Administration sign-in" })).toBeVisible();
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("manager and College BDM: create, activate, land, team", async ({ page }) => {
  const stamp = Date.now();
  await superAdmin(page);
  const mgr = await (await page.request.post("/api/v1/admin/users", { data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm001-m-${stamp}@example.local` } })).json();
  const bdm = await page.request.post("/api/v1/admin/users", { data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm001-b-${stamp}@example.local`,
    bdm_profile: { bdm_type: "college", employee_id: `E2E-${stamp}`, territory: "Kochi", reporting_manager_user_id: mgr.id } } });
  expect(bdm.status()).toBe(201);
  const bdmBody = await bdm.json();
  expect(bdmBody.division).toBe("it");
  await page.request.post("/api/v1/auth/logout");

  await activateWithToken(page.request, bdmBody.development_welcome_token);
  await signIn(page, "it", bdmBody.email, "/bdm/my-day");
  await expect(page.getByText(`E2E-${stamp}`)).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  await page.goto(`/it/reset-password?token=${mgr.development_welcome_token}`);
  await page.fill("#new-password", E2E_PASSWORD);
  await page.getByRole("button", { name: "Reset password" }).click();
  await page.waitForURL("**/admin/login");
  await signIn(page, "admin", mgr.email, "/bdm/manager/dashboard");
  await page.getByRole("link", { name: "View team" }).click();
  await expect(page.getByRole("region", { name: "Team" }).getByText(`E2E BDM ${stamp}`)).toBeVisible();
});

test("signed-out /bdm visits go to the right sign-in", async ({ page }) => {
  await page.goto("/bdm/my-day");
  await page.waitForURL("**/bdm/sign-in?next=%2Fbdm%2Fmy-day");
  await expect(page.getByRole("link", { name: "College BDM" })).toHaveAttribute("href", "/it/login?next=%2Fbdm%2Fmy-day");
  await page.goto("/bdm/manager/team");
  await page.waitForURL("**/admin/login?next=%2Fbdm%2Fmanager%2Fteam");
});

test("admin BDM page works at phone width without horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await superAdmin(page);
  await page.goto("/admin/bdms");
  await expect(page.getByRole("heading", { name: "Create BDM" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
```

Before writing, check the selectors (`#login-email`, `#new-password`, the button names) against `LoginForm` and `ResetPasswordForm`, and that the seeded super admin lands on `/admin`.

- [ ] **Step 2: Ask the user to start the isolated stack.** For example: `docker compose -p bdm001 -f docker-compose.yml up -d --build` with this worktree's `.env` ports, and `exec -T api python -m app.seed`. Wait for their confirmation.
- [ ] **Step 3: Run the spec plus its lite neighbours.** `bdm-001-bdm-profile.spec.ts auth-001-login.spec.ts enh-003-first-time-provisioning.spec.ts adm-001-admin-crud.spec.ts` in `web-test` with `-e E2E_BASE_URL=http://host.docker.internal:<web port>`. Expected: pass. Read failure traces and screenshots only if something fails.
- [ ] **Step 4: Commit** — `test(bdm-001): end-to-end manager/BDM journey and /bdm sign-in redirects`.

---

### Task 11: Documentation, traceability and the lite verification run

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append `### DEC-SCOPE-052`)
- Modify: `docs/delivery/BDM_CRM_BACKLOG.md` (replace `DEC-SCOPE-037` with `DEC-SCOPE-052`; set the bdm-001 status to "Implemented on branch — pending browser QA and independent review")
- Modify: `docs/architecture/RBAC_MATRIX.md` (the `bdm` and `bdm_manager` rows with their scope rules)
- Modify: `docs/ux/ROLE_NAVIGATION.md` (landing pages, navs, `/bdm/sign-in`, the `/admin/login` text)

- [ ] **Step 1: Write `DEC-SCOPE-052`.** Use the layout of the `DEC-SCOPE-050` entry. Include: classification `EXPLICIT_APPROVAL` (owner, in-session); D1–D32 dated 2026-09-28, copied from `BDM_CRM_BACKLOG.md` §3.1–3.3 with a note that they were previously mis-cited as 037; B1–B9 dated 2026-10-02 from spec §3; and the evidence (`EVID-016`).
- [ ] **Step 2: Update the backlog, RBAC matrix and role navigation docs.** Then confirm: `grep -rn "DEC-SCOPE-037" docs/delivery/BDM_CRM_BACKLOG.md` → no hits.
- [ ] **Step 3: Run the lite backend set:**
  - `tests/test_bdm_001_migration.py tests/test_bdm_001_service.py tests/test_bdm_001_profiles.py tests/test_bdm_001_reads.py tests/test_bdm_001_reset_portal.py`
  - `tests/test_adm_001_admin_crud.py tests/test_adm_004_directory.py tests/test_adm_012_roles_permissions.py tests/test_adm_014_super_admin_console.py`
  - `tests/test_enh_003_first_time_provisioning.py tests/test_enh_006_change_password.py tests/test_enh_029_provision_refactor.py tests/test_sch_school_staff_provisioning.py tests/test_rbac.py tests/test_role_assignments.py`
  - the AGN-001 admin-create test file.

  Expected: all pass. Record the counts.
- [ ] **Step 4: Run the lite web set:** every `tests/**/*bdm*`, `AdminBdm*`, `BdmPages`, `BdmTeamTable`, `middleware`, `navigation*`, `ResetPasswordForm`, `HeaderAuthActions`, `LoginForm.next`, `AdminUserManagementPanel` and `WorkflowPanel*` test, then `npx tsc --noEmit`, `npx eslint .` and `npx next build`. Expected: pass.
- [ ] **Step 5: Check before committing:** `git diff --cached | grep -iE "password|secret|api_key|token"` should match only test fixtures and existing names, never real values.
- [ ] **Step 6: Commit** — `docs(bdm-001): DEC-SCOPE-052, backlog, RBAC matrix, role navigation`.
- [ ] **Step 7: Report the status. Do NOT claim completion.** List the AC01–AC16 evidence (the test names that passed), the lite files run with their counts, and a plain statement that **the full backend suite was not run (by the user's standing choice)**. Pending: browser validation (spec §11 responsive and accessibility gates) and the independent Codex review.

---

## Self-review

- **Spec coverage:**

  | Spec section | Task |
  |---|---|
  | §4 | 1 |
  | §5.1–5.3 | 2 |
  | §5.4 | 3 |
  | §5.5 | 4 |
  | §5.6 | 6 |
  | §5.7 | 5 |
  | §5.8 | 3 (create race), 4 (concurrent PATCH), 5 (no IDOR) |
  | §6.1 | 7 |
  | §6.2 | 8 |
  | §6.3 | 9 |
  | §8 e2e | 10 |
  | §10 | 11 |
  | §12 findings | folded into Tasks 2–9 |

- **AC map:**

  | AC | Task(s) |
  |---|---|
  | AC01 | 3, 10 |
  | AC02 | 3 |
  | AC03 | 3, 4 |
  | AC04 | 3, 4 |
  | AC05 | 6, 7, 10 |
  | AC06 | 5, 8, 10 |
  | AC07 | 3, 4 |
  | AC08 | 3 |
  | AC09 | 3, 4 |
  | AC10 | 5 |
  | AC11 | 5 |
  | AC12 | 7, 8, 10 |
  | AC13 | 9 |
  | AC14 | 3–6 regression steps, 11 |
  | AC15 | 3, 5, 6 |
  | AC16 | 2, 4, 5 |

- **Type consistency:** the service names from Task 2 (`parse_profile_create`, `locked_active_manager`, `flush_profile`, `profile_snapshot`, `profile_out`, `bdm_context`, `require_manager`, `team_filter`, `admin_type_filter`, `require_creator_may`) are used with identical names in Tasks 3–5. The web names `creatableTypes`, `statusLabel`, `BDMS_URL`, `MANAGERS_URL`, `USERS_URL`, `PAGE_SIZE`, `BDM_TYPE_LABEL`, `BDM_NAV`, `BDM_MANAGER_NAV` and `BDM_SIGN_IN` are consistent across Tasks 7–9.
- **Placeholder scan:** no TBD or TODO entries. Three items are marked "check against the file before writing": the `SendOutcome` fields, the admin page label strings and the e2e selectors. They name the exact file to check, and the default behavior is spelled out.
