# tel-001 Telecaller Roles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `telecaller` and `telecaller_manager` roles with a `telecaller_profiles` table, admin provisioning, sign-in routing,
minimal landing pages, a self-service phone edit, a manager team list and an admin Telecallers page.

**Architecture:** A copy of bdm-001's design. `POST/PATCH /admin/users` gain a `telecaller_profile` branch, and a new flat
`api/telecaller.py` + `services/telecaller.py` pair holds the reads and the scope helpers later tel items call. The web side adds a
`/telecaller/*` area with its own sign-in chooser, and an admin page mounted under the three admin portals.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic + Pydantic v2 (apps/api); Next.js App Router + React + vitest + Playwright (apps/web).

**Spec:** `docs/superpowers/specs/2026-10-05-tel-001-telecaller-roles-design.md` (approved 2026-10-05). Template: bdm-001
(`docs/superpowers/specs/2026-10-02-bdm-001-bdm-profile-design.md`).

## Global Constraints

- Decision `DEC-SCOPE-073`; migration `0075_telecaller_profiles` revising `0074_enquiry_bdm_attribution`. Before Task 1 and again before
  merge: `git fetch origin main` and check `git log feature/tel-001..origin/main` for a new migration or DEC-SCOPE; if one landed,
  renumber and say so.
- Authorization follows the inline pattern (`User.role` checks + scope helpers). Never use `require_role`/`require_permission`.
- Logs carry ids, route and team only — never email, phone or Employee ID.
- Lists are `{items, total, limit, offset}`; `limit` 1–100 default 50; `offset` ≥ 0; sorted `full_name, id`.
- Error texts (exact):
  - 403 `"Your role cannot manage IT telecallers"` / `"Your role cannot manage Overseas telecallers"`
  - 403 `"Only a Super Admin can create telecaller managers"`
  - 403 `"Telecaller role required"`, `"Telecaller profile not set up — contact your administrator"`, `"Telecaller manager role required"`
  - 422 `"Telecaller profile is required"`, `"Only a telecaller has a telecaller profile"`, `"Division must match the telecaller's team"`,
    `"Reporting manager must be an active telecaller manager"`, `"Team cannot be changed here"`
  - 409 `"Employee ID already exists"`
- UI copy: role labels "IT Telecaller", "Overseas Telecaller", "Telecaller Manager"; team labels "IT", "Overseas"; nav label "Telecallers".
- No new npm or pip dependencies.
- Never change product behavior to make a draft test pass; tests are executed with real tools, never judged by reasoning.

**Test commands** (worktree on Windows; the user owns the docker stack — ask for the compose project name if `edusphere-tel001` isn't
it, and never start/stop the stack yourself):

```bash
# API (TESTS = space-separated test paths)
docker compose -p edusphere-tel001 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/tel-001/apps/api:/app" \
  api-test sh -c "alembic upgrade head && python -m pytest -q $TESTS"

# Web (CMD = e.g. "npx vitest run tests/lib/middleware.test.ts")
MSYS_NO_PATHCONV=1 docker compose -p edusphere-tel001 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps \
  -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/tel-001/apps/web:/app" \
  -v /app/node_modules web-test sh -c "$CMD"
```

If the test database carries a stale alembic stamp, `alembic stamp --purge 0074_enquiry_bdm_attribution` then `upgrade head`.

## Review Focus

1. **A BDM payload with a stray `telecaller_profile` (or the reverse).** Expect 422 and nothing written — pinned in Task 3
   (`test_profiles_cannot_cross_roles`).
2. **An Employee ID that differs only by case or surrounding spaces from an existing one.** Expect 409 — pinned in Task 3
   (`test_duplicate_employee_id_is_409_case_and_space_insensitive`).
3. **A telecaller PATCHing `/telecaller/profile` with `employee_id`, `team` or `reporting_manager_user_id`.** Expect 422 and nothing
   changed — pinned in Task 5 (`test_self_update_rejects_other_fields`).
4. **A `next` that points off-site on `/telecaller/sign-in`** (`?next=https://evil.example`). Expect the links to carry no `next` —
   pinned in Task 6 (`TelecallerSignIn.test.tsx`).
5. **A manager who is deactivated while still having reports.** Expect the admin list to show "No active manager" and the manager's
   team route to stop working for them (sign-in refused), with the telecaller rows intact — pinned in Task 5
   (`test_admin_list_flags_inactive_manager`) and Task 8 (`AdminTelecallerRow.test.tsx`).

---

## File map

**API (apps/api):**
- Create `alembic/versions/0075_telecaller_profiles.py` — the table.
- Modify `app/models.py` — `TelecallerProfile` after `BdmProfile`.
- Modify `app/schemas.py` — telecaller section at the end of the file.
- Create `app/services/telecaller.py` — rules + scope helpers.
- Create `app/api/telecaller.py` — five routes.
- Modify `app/main.py` — register the two routers.
- Modify `app/api/admin.py` — `create_user` / `update_user` branches.
- Modify `app/core/rbac.py` — two roles.
- Modify `app/services/provisioning.py` — `ADMIN_PORTAL_ROLES`.
- Modify `app/api/auth.py` — reset response uses `ADMIN_PORTAL_ROLES`.
- Tests: create `tests/tel001_helpers.py`, `tests/test_tel_001_migration.py`, `test_tel_001_service.py`, `test_tel_001_provisioning.py`,
  `test_tel_001_update.py`, `test_tel_001_reads.py`, `test_tel_001_login.py`; modify `tests/test_bdm_017_migration.py` (head check),
  and `tests/test_bdm_001_admin_portal_links.py` (add telecaller rows).

**Web (apps/web):**
- Modify `lib/navigation.ts`, `middleware.ts`, `components/WorkflowPanel.tsx`, `app/admin/login/page.tsx`, and comments in
  `app/admin/forgot-password/page.tsx`, `components/LoginForm.tsx`, `components/ResetPasswordForm.tsx`.
- Create `lib/telecaller.ts`; `app/telecaller/page.tsx`, `app/telecaller/sign-in/page.tsx`, `app/telecaller/dashboard/page.tsx`,
  `app/telecaller/profile/page.tsx`, `app/telecaller/manager/page.tsx`, `app/telecaller/manager/team/page.tsx`;
  `components/TelecallerProfileCard.tsx`, `components/TelecallerPhoneForm.tsx`, `components/TelecallerTeamTable.tsx`;
  `components/AdminTelecallerPage.tsx`, `AdminTelecallerPanel.tsx`, `AdminTelecallerCreateForm.tsx`, `AdminTelecallerRow.tsx`;
  `app/admin/telecallers/page.tsx`, `app/it/admin/telecallers/page.tsx`, `app/overseas/admin/telecallers/page.tsx`.
- Tests: `tests/lib/middleware.test.ts` (extend), `tests/lib/navigation.telecaller.test.ts`, `tests/components/TelecallerSignIn.test.tsx`,
  `TelecallerPhoneForm.test.tsx`, `TelecallerTeamTable.test.tsx`, `AdminTelecallerCreateForm.test.tsx`, `AdminTelecallerRow.test.tsx`,
  `AdminTelecallerPanel.test.tsx`; `tests/e2e/tel-001-telecaller-roles.spec.ts`; modify `tests/e2e/adm-001-admin-crud.spec.ts`
  (role options).

**Docs:** `docs/decisions/PRODUCT_DECISION_REGISTER.md`, `docs/architecture/RBAC_MATRIX.md`, `docs/architecture/API_CONTRACT.md`,
`docs/ux/ROLE_NAVIGATION.md`, `docs/ux/SCREEN_CATALOG.md`, `docs/delivery/TELECALLER_CRM_BACKLOG.md`.

---

### Task 1: Migration 0075 and the `TelecallerProfile` model

**Files:**
- Create: `apps/api/alembic/versions/0075_telecaller_profiles.py`
- Modify: `apps/api/app/models.py` (after `class BdmProfile`, before the `BDM_TRIP_CODE_SEQ` comment, ~line 978)
- Modify: `apps/api/tests/test_bdm_017_migration.py:38`
- Test: `apps/api/tests/test_tel_001_migration.py`

**Interfaces:**
- Produces: `app.models.TelecallerProfile` with columns `id, user_id, team, employee_id, reporting_manager_user_id, created_at,
  updated_at`; constraint/index names `uq_telecaller_profiles_user`, `ck_telecaller_profiles_team`,
  `uq_telecaller_profiles_employee_id`, `ix_telecaller_profiles_reporting_manager`.

- [ ] **Step 1: Re-check main for collisions**

Run: `git fetch origin main && git log --oneline feature/tel-001..origin/main -- apps/api/alembic/versions docs/decisions/PRODUCT_DECISION_REGISTER.md`
Expected: no output. If a `0075_*` migration or `DEC-SCOPE-073` appears, stop and tell the user before continuing.

- [ ] **Step 2: Write the failing migration test**

Create `apps/api/tests/test_tel_001_migration.py`:

```python
"""tel-001 -- migration 0075_telecaller_profiles (spec §4). Round trip and the downgrade refusal run in a throwaway database built from
scratch (the bdm-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_tel_001_migration_0075", VERSIONS / "0075_telecaller_profiles.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0074_enquiry_bdm_attribution", "0075_telecaller_profiles"
USERS = "SELECT id, email, role, division FROM users ORDER BY id"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0074_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert ScriptDirectory.from_config(_config()).get_heads() == [HEAD]


def test_model_matches_the_migration():
    from app.models import TelecallerProfile

    table = TelecallerProfile.__table__
    assert {c.name for c in table.columns} == {"id", "user_id", "team", "employee_id", "reporting_manager_user_id", "created_at", "updated_at"}
    assert not table.c.employee_id.nullable and not table.c.reporting_manager_user_id.nullable and not table.c.team.nullable
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {"uq_telecaller_profiles_user", "ck_telecaller_profiles_team", "uq_telecaller_profiles_employee_id", "ix_telecaller_profiles_reporting_manager"} <= names


@pytest.mark.asyncio
async def test_table_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    indexes = await conn.run_sync(lambda sync: {i["name"]: i for i in inspect(sync).get_indexes("telecaller_profiles")})
    assert indexes["uq_telecaller_profiles_employee_id"]["unique"]
    assert "ix_telecaller_profiles_reporting_manager" in indexes


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
    """A fresh database at 0074 with one telecaller_manager and one other user."""
    cfg = _config()
    original = settings.database_url
    name = f"tel001_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("manager", "caller")}
        for key, role, division in (("manager", "telecaller_manager", "global"), ("caller", "counselor", "overseas")):
            _sql(
                url,
                "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
                "VALUES (:id, :email, 'x', :name, :role, :division, true, true, 'en-GB', '{}')",
                {"id": ids[key], "email": f"{key}-{name}@example.local", "name": key, "role": role, "division": division},
            )
        yield {"cfg": cfg, "url": url, "ids": ids}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_users_identical(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, USERS)
    command.upgrade(cfg, HEAD)
    assert _sql(url, USERS) == before
    command.downgrade(cfg, BASE)
    assert _sql(url, USERS) == before
    command.upgrade(cfg, HEAD)
    assert _sql(url, USERS) == before


def test_constraints_hold_and_downgrade_refuses_while_profiles_exist(isolated_db):
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, HEAD)
    insert = (
        "INSERT INTO telecaller_profiles (id, user_id, team, employee_id, reporting_manager_user_id) "
        "VALUES (:id, :user, :team, :emp, :mgr)"
    )
    with pytest.raises(Exception, match="ck_telecaller_profiles_team"):
        _sql(url, insert, {"id": uuid.uuid4(), "user": ids["caller"], "team": "global", "emp": "T1", "mgr": ids["manager"]})
    _sql(url, insert, {"id": uuid.uuid4(), "user": ids["caller"], "team": "it", "emp": "T1", "mgr": ids["manager"]})
    with pytest.raises(Exception, match="uq_telecaller_profiles_employee_id"):
        _sql(url, insert, {"id": uuid.uuid4(), "user": ids["manager"], "team": "overseas", "emp": "t1", "mgr": ids["manager"]})
    with pytest.raises(Exception, match="uq_telecaller_profiles_user"):
        _sql(url, insert, {"id": uuid.uuid4(), "user": ids["caller"], "team": "it", "emp": "T2", "mgr": ids["manager"]})
    with pytest.raises(Exception, match="profiles exist"):
        command.downgrade(cfg, BASE)
```

- [ ] **Step 3: Run it to verify it fails**

Run the API command with `TESTS=tests/test_tel_001_migration.py`.
Expected: FAIL — `FileNotFoundError` / `ModuleNotFoundError` for `0075_telecaller_profiles.py` at import.

- [ ] **Step 4: Write the migration**

Create `apps/api/alembic/versions/0075_telecaller_profiles.py`:

```python
"""tel-001 -- telecaller_profiles (1:1 with a `telecaller` user).

Revision ID: 0075_telecaller_profiles
Revises: 0074_enquiry_bdm_attribution

docs/superpowers/specs/2026-10-05-tel-001-telecaller-roles-design.md §4 (DEC-SCOPE-073). Adds one table; no existing row is read or
written. 0001 builds a fresh database from the current models, which already carry this table, so creation is guarded (0061's idiom).
downgrade() refuses while profiles exist: they are the only record of each telecaller's team and reporting manager.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0075_telecaller_profiles"
down_revision = "0074_enquiry_bdm_attribution"
branch_labels = None
depends_on = None

TABLE = "telecaller_profiles"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("team", sa.String(20), nullable=False),
        sa.Column("employee_id", sa.String(40), nullable=False),
        sa.Column("reporting_manager_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_telecaller_profiles_user"),
        sa.CheckConstraint("team IN ('it', 'overseas')", name="ck_telecaller_profiles_team"),
    )
    op.create_index("uq_telecaller_profiles_employee_id", TABLE, [sa.text("lower(employee_id)")], unique=True)
    op.create_index("ix_telecaller_profiles_reporting_manager", TABLE, ["reporting_manager_user_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0075_telecaller_profiles: telecaller profiles exist. Remove them deliberately first.")
    op.drop_table(TABLE)
```

- [ ] **Step 5: Add the model**

In `apps/api/app/models.py`, directly after `class BdmProfile` (ends at the `reporting_manager_user_id` column, ~line 976):

```python


class TelecallerProfile(Base, TimestampMixin):
    """tel-001 (DEC-SCOPE-073): a telecaller's profile, 1:1 with a `telecaller` user. Name, email, mobile and active stay on `users`.
    `team` is the user's division (T22); the reporting manager must be an active `telecaller_manager`. Both rules span tables, so
    `services/telecaller.py` enforces them under a row lock (no cross-table CHECK)."""

    __tablename__ = "telecaller_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_telecaller_profiles_user"),
        CheckConstraint("team IN ('it', 'overseas')", name="ck_telecaller_profiles_team"),
        Index("uq_telecaller_profiles_employee_id", text("lower(employee_id)"), unique=True),
        Index("ix_telecaller_profiles_reporting_manager", "reporting_manager_user_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    team: Mapped[str] = mapped_column(String(20))
    employee_id: Mapped[str] = mapped_column(String(40))
    reporting_manager_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
```

- [ ] **Step 6: Relax bdm-017's head assertion**

`0074` is no longer the head. In `apps/api/tests/test_bdm_017_migration.py`, line 38, replace
`assert ScriptDirectory.from_config(_config()).get_heads() == [HEAD]` with
`assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1  # tel-001's 0075 now follows this revision`.
Leave the rest of that test (it still checks `revision`/`down_revision`).

- [ ] **Step 7: Run the tests to verify they pass**

Run the API command with `TESTS="tests/test_tel_001_migration.py tests/test_bdm_017_migration.py tests/test_bdm_001_migration.py"`.
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/api/alembic/versions/0075_telecaller_profiles.py apps/api/app/models.py apps/api/tests/test_tel_001_migration.py apps/api/tests/test_bdm_017_migration.py
git commit -m "feat(tel-001): telecaller_profiles table and model (0075)"
```

---

### Task 2: Schemas and the telecaller service

**Files:**
- Modify: `apps/api/app/schemas.py` (append at the end of the file)
- Create: `apps/api/app/services/telecaller.py`
- Create: `apps/api/tests/tel001_helpers.py`
- Test: `apps/api/tests/test_tel_001_service.py`

**Interfaces:**
- Consumes: `TelecallerProfile` (Task 1); existing `BdmEmployeeId`, `BdmLeadPhone`, `BdmManagerRef` in `schemas.py`.
- Produces (schemas): `TelecallerTeam`, `TELECALLER_FIELD_LABELS`, `TelecallerProfileCreate(team, employee_id, reporting_manager_user_id)`,
  `TelecallerProfileUpdate` (all optional), `TelecallerSelfUpdate(phone)`, `TelecallerProfileOut`, `TelecallerMeOut`, `TelecallerTeamRow`,
  `TelecallerAdminRow`, `TelecallerTeamPage`, `TelecallerAdminPage`.
- Produces (service `app.services.telecaller`): `TEAMS`, `TEAM_LABEL`, `CREATOR_TEAMS`, `creatable_teams(actor) -> frozenset[str]`,
  `require_creator_may(actor, team, route) -> None`, `parse_profile_create(raw) -> TelecallerProfileCreate`,
  `parse_profile_update(raw) -> TelecallerProfileUpdate`, `parse_self_update(raw) -> TelecallerSelfUpdate`,
  `async locked_active_manager(db, manager_id) -> User`, `async flush_profile(db) -> None`, `profile_snapshot(profile) -> dict`,
  `person_ref(user) -> dict`, `profile_out(profile, manager) -> dict`, `async apply_profile_update(db, profile, raw) -> tuple[dict, dict]`,
  `async telecaller_context(db, user) -> TelecallerProfile`, `require_manager(user) -> None`, `team_filter(user) -> list`,
  `admin_team_filter(actor, team) -> list`.
- Produces (test helpers `tests.tel001_helpers`): `PASSWORD`, `USERS`, `emp()`, `make_user(db, role, division, *, active=True, name=None)`,
  `login(client, user)`, `make_tl_manager(db, *, active=True, name=None)`, `tel_payload(manager_id, *, team="it", **overrides) -> dict`,
  `async create_telecaller(client, manager_id, **overrides)`, `async sign_in_as_created(client, db, created: dict) -> User`.

- [ ] **Step 1: Write the test helpers**

Create `apps/api/tests/tel001_helpers.py`:

```python
"""tel-001 test builders, on top of bdm-001's. Every value is unique per call: the test database is shared and never truncated."""

import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.models import User
from tests.bdm001_helpers import PASSWORD, USERS, email, emp, login, make_user

__all__ = ["PASSWORD", "USERS", "create_telecaller", "emp", "login", "make_tl_manager", "make_user", "sign_in_as_created", "tel_payload"]


async def make_tl_manager(db, *, active: bool = True, name: str | None = None) -> User:
    return await make_user(db, "telecaller_manager", "global", active=active, name=name)


def tel_payload(manager_id, *, team: str = "it", **overrides) -> dict:
    payload = {
        "role": "telecaller", "email": email("tel"), "full_name": "Ravi Telecaller", "phone": "+91 90000 00001",
        "telecaller_profile": {"team": team, "employee_id": emp(), "reporting_manager_user_id": str(manager_id)},
    }
    payload.update(overrides)
    return payload


async def create_telecaller(client, manager_id, **overrides):
    return await client.post(USERS, json=tel_payload(manager_id, **overrides))


async def sign_in_as_created(client, db, created: dict) -> User:
    """An admin-created account has an unusable password; give it the test password so it can sign in."""
    user = await db.scalar(select(User).where(User.id == uuid.UUID(created["id"])))
    user.password_hash = hash_password(PASSWORD)
    await db.commit()
    await login(client, user)
    return user
```

- [ ] **Step 2: Write the failing service test**

Create `apps/api/tests/test_tel_001_service.py`:

```python
"""tel-001 -- services/telecaller.py rules and scope helpers (spec §5.3)."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models import TelecallerProfile
from app.services import telecaller as rules
from tests.tel001_helpers import emp, make_tl_manager, make_user


def _actor(role: str):
    return SimpleNamespace(id=uuid.uuid4(), role=role)


@pytest.mark.parametrize(("role", "teams"), [("super_admin", {"it", "overseas"}), ("it_admin", {"it"}), ("overseas_admin", {"overseas"}), ("counselor", set())])
def test_creatable_teams(role, teams):
    assert rules.creatable_teams(_actor(role)) == teams


def test_require_creator_may_names_the_team():
    with pytest.raises(HTTPException) as caught:
        rules.require_creator_may(_actor("it_admin"), "overseas", "/admin/users")
    assert caught.value.status_code == 403 and caught.value.detail == "Your role cannot manage Overseas telecallers"
    rules.require_creator_may(_actor("it_admin"), "it", "/admin/users")


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (None, "Telecaller profile is required"),
        ({"employee_id": "E1", "reporting_manager_user_id": str(uuid.uuid4())}, "Team is required"),
        ({"team": "global", "employee_id": "E1", "reporting_manager_user_id": str(uuid.uuid4())}, "Team: Input should be 'it' or 'overseas'"),
        ({"team": "it", "employee_id": "   ", "reporting_manager_user_id": str(uuid.uuid4())}, "Employee ID is required"),
        ({"team": "it", "employee_id": "E1", "reporting_manager_user_id": "nope"}, "Reporting manager: choose a manager from the list"),
        ({"team": "it", "employee_id": "E1", "reporting_manager_user_id": str(uuid.uuid4()), "designation": "x"}, "Unknown field: designation"),
    ],
)
def test_parse_profile_create_gives_readable_422(raw, message):
    with pytest.raises(HTTPException) as caught:
        rules.parse_profile_create(raw)
    assert caught.value.status_code == 422 and caught.value.detail == message


def test_parse_profile_create_trims_employee_id():
    parsed = rules.parse_profile_create({"team": "it", "employee_id": "  E-7 ", "reporting_manager_user_id": str(uuid.uuid4())})
    assert parsed.employee_id == "E-7"


@pytest.mark.parametrize(("raw", "phone"), [({"phone": " +91 98 "}, "+91 98"), ({"phone": ""}, None), ({"phone": None}, None)])
def test_parse_self_update_accepts_and_clears_phone(raw, phone):
    assert rules.parse_self_update(raw).phone == phone


@pytest.mark.parametrize(
    ("raw", "message"),
    [({}, "Phone is required"), ({"phone": "abc"}, "Phone may contain only digits, spaces and + - ( )"), ({"phone": "1", "employee_id": "E"}, "Unknown field: employee_id")],
)
def test_parse_self_update_refuses(raw, message):
    with pytest.raises(HTTPException) as caught:
        rules.parse_self_update(raw)
    assert caught.value.status_code == 422 and caught.value.detail == message


@pytest.mark.asyncio
async def test_locked_active_manager_accepts_only_an_active_telecaller_manager(db_session):
    good = await make_tl_manager(db_session)
    assert (await rules.locked_active_manager(db_session, good.id)).id == good.id
    for bad in (await make_tl_manager(db_session, active=False), await make_user(db_session, "bdm_manager", "global")):
        with pytest.raises(HTTPException) as caught:
            await rules.locked_active_manager(db_session, bad.id)
        assert caught.value.status_code == 422 and caught.value.detail == "Reporting manager must be an active telecaller manager"
    with pytest.raises(HTTPException):
        await rules.locked_active_manager(db_session, uuid.uuid4())


def test_scope_helpers():
    assert rules.team_filter(_actor("super_admin")) == []
    assert len(rules.team_filter(_actor("telecaller_manager"))) == 1
    rules.require_manager(_actor("telecaller_manager"))
    rules.require_manager(_actor("super_admin"))
    for role in ("telecaller", "bdm_manager", "it_admin"):
        with pytest.raises(HTTPException) as caught:
            rules.require_manager(_actor(role))
        assert caught.value.status_code == 403 and caught.value.detail == "Telecaller manager role required"


def test_admin_team_filter():
    assert len(rules.admin_team_filter(_actor("it_admin"), None)) == 1
    assert len(rules.admin_team_filter(_actor("it_admin"), "it")) == 1
    with pytest.raises(HTTPException) as caught:
        rules.admin_team_filter(_actor("it_admin"), "overseas")
    assert caught.value.status_code == 403


@pytest.mark.asyncio
async def test_telecaller_context_requires_role_and_profile(db_session):
    with pytest.raises(HTTPException) as caught:
        await rules.telecaller_context(db_session, await make_user(db_session, "counselor", "overseas"))
    assert caught.value.detail == "Telecaller role required"
    bare = await make_user(db_session, "telecaller", "it")
    with pytest.raises(HTTPException) as caught:
        await rules.telecaller_context(db_session, bare)
    assert caught.value.detail == "Telecaller profile not set up — contact your administrator"
    manager = await make_tl_manager(db_session)
    db_session.add(TelecallerProfile(user_id=bare.id, team="it", employee_id=emp(), reporting_manager_user_id=manager.id))
    await db_session.commit()
    assert (await rules.telecaller_context(db_session, bare)).team == "it"
```

- [ ] **Step 3: Run it to verify it fails**

Run the API command with `TESTS=tests/test_tel_001_service.py`.
Expected: FAIL — `ImportError: cannot import name 'telecaller' from 'app.services'`.

- [ ] **Step 4: Add the schemas**

Append to the end of `apps/api/app/schemas.py`:

```python


# --- tel-001 (DEC-SCOPE-073): telecaller profile ------------------------------------------------------------------------
TelecallerTeam = Literal["it", "overseas"]
TELECALLER_FIELD_LABELS = {"team": "Team", "employee_id": "Employee ID", "reporting_manager_user_id": "Reporting manager", "phone": "Phone"}


class TelecallerProfileCreate(BaseModel):
    """spec §5.2 / TL6: team, Employee ID and reporting manager, all required; nothing optional."""

    model_config = ConfigDict(extra="forbid")
    team: TelecallerTeam
    employee_id: BdmEmployeeId
    reporting_manager_user_id: UUID


class TelecallerProfileUpdate(BaseModel):
    """Omitted = unchanged. An explicit null for any key fails (all three are required on the row). `team` exists only so an equal
    value is a no-op; a different one is refused by services/telecaller.apply_profile_update (TL7)."""

    model_config = ConfigDict(extra="forbid")
    team: TelecallerTeam = None
    employee_id: BdmEmployeeId = None
    reporting_manager_user_id: UUID = None


class TelecallerSelfUpdate(BaseModel):
    """TL3: a telecaller may change only their phone. The key is required; null or "" clears it. bdm-017's lead phone rule
    (trimmed, max 40, digits/spaces/+-(), no control characters) is reused, not copied."""

    model_config = ConfigDict(extra="forbid")
    phone: BdmLeadPhone


class TelecallerProfileOut(BaseModel):
    team: str
    employee_id: str
    reporting_manager: BdmManagerRef


class TelecallerMeOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    active: bool
    division: str
    telecaller_profile: TelecallerProfileOut


class TelecallerTeamRow(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None
    active: bool
    team: str
    employee_id: str


class TelecallerAdminRow(TelecallerTeamRow):
    reporting_manager: BdmManagerRef
    manager_active: bool


class TelecallerTeamPage(BaseModel):
    items: list[TelecallerTeamRow]
    total: int
    limit: int
    offset: int


class TelecallerAdminPage(BaseModel):
    items: list[TelecallerAdminRow]
    total: int
    limit: int
    offset: int
```

`BdmLeadPhone`'s message uses `BDM_LEAD_LABELS["phone"]` = "Phone", so the text matches the test.

- [ ] **Step 5: Write the service**

Create `apps/api/app/services/telecaller.py`:

```python
"""tel-001 (DEC-SCOPE-073, spec §5.3): telecaller provisioning rules and the self/team scope every later tel item calls.

Functions only; nothing here commits -- the route owns the transaction. Logs carry ids, route and team, never email, phone or
Employee ID."""

import logging

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TelecallerProfile, User
from app.schemas import TELECALLER_FIELD_LABELS, TelecallerProfileCreate, TelecallerProfileUpdate, TelecallerSelfUpdate

logger = logging.getLogger("app.telecaller")

TEAMS = ("it", "overseas")
TEAM_LABEL = {"it": "IT", "overseas": "Overseas"}
CREATOR_TEAMS = {  # T21: super_admin creates both teams; a division admin only its own (only super_admin creates managers, admin.create_user)
    "super_admin": frozenset(TEAMS),
    "it_admin": frozenset({"it"}),
    "overseas_admin": frozenset({"overseas"}),
}
EMPLOYEE_ID_INDEX = "uq_telecaller_profiles_employee_id"


def creatable_teams(actor: User) -> frozenset[str]:
    return CREATOR_TEAMS.get(actor.role, frozenset())


def _cannot_manage(team: str) -> HTTPException:
    return HTTPException(403, f"Your role cannot manage {TEAM_LABEL.get(team, team)} telecallers")


def require_creator_may(actor: User, team: str, route: str) -> None:
    if team not in creatable_teams(actor):
        logger.warning("telecaller_creator_team_refused", extra={"extra_fields": {"actor_id": str(actor.id), "route": route, "team": team}})
        raise _cannot_manage(team)


def _readable(error: dict) -> str:
    """The admin sees a sentence naming the field, not a pydantic path (bdm-001 QA-08)."""
    field = str(error["loc"][0]) if error["loc"] else ""
    label = TELECALLER_FIELD_LABELS.get(field, field)
    if error["type"] == "extra_forbidden":
        return f"Unknown field: {field}"
    explicit_null = "input" in error and error["input"] is None
    if error["type"] == "missing" or (explicit_null and field in TELECALLER_FIELD_LABELS and field != "phone"):
        return f"{label} is required"
    if error["type"] == "value_error":
        return error["msg"].removeprefix("Value error, ")
    if error["type"] == "uuid_parsing":
        return f"{label}: choose a manager from the list"
    return f"{label}: {error['msg']}"


def _parse(model: type[BaseModel], raw, not_an_object: str):
    """The /admin/users payload is an untyped dict (existing contract), so nested objects are validated here; the first error becomes
    a readable 422."""
    if not isinstance(raw, dict):
        raise HTTPException(422, not_an_object)
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(422, _readable(exc.errors()[0])) from None


def parse_profile_create(raw) -> TelecallerProfileCreate:
    return _parse(TelecallerProfileCreate, raw, "Telecaller profile is required")


def parse_profile_update(raw) -> TelecallerProfileUpdate:
    return _parse(TelecallerProfileUpdate, raw, "telecaller_profile must be an object")


def parse_self_update(raw) -> TelecallerSelfUpdate:
    return _parse(TelecallerSelfUpdate, raw, "The request body must be an object")


async def locked_active_manager(db: AsyncSession, manager_id) -> User:
    """FOR SHARE: a concurrent deactivation of this manager (an UPDATE of the same row) waits for the assignment's commit, so a
    telecaller is never committed against a manager deactivated in the same instant (spec §5.8)."""
    manager = await db.scalar(select(User).where(User.id == manager_id).with_for_update(read=True))
    if not manager or not manager.active or manager.role != "telecaller_manager":
        raise HTTPException(422, "Reporting manager must be an active telecaller manager")
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


def profile_snapshot(profile: TelecallerProfile) -> dict:
    """The audit form (JSON-safe)."""
    return {"team": profile.team, "employee_id": profile.employee_id, "reporting_manager_user_id": str(profile.reporting_manager_user_id)}


def person_ref(user: User) -> dict:
    return {"id": user.id, "full_name": user.full_name, "active": user.active}


def profile_out(profile: TelecallerProfile, manager: User) -> dict:
    return {"team": profile.team, "employee_id": profile.employee_id, "reporting_manager": person_ref(manager)}


async def apply_profile_update(db: AsyncSession, profile: TelecallerProfile, raw) -> tuple[dict, dict]:
    """PATCH semantics on a profile the caller has already locked: the team is fixed here (TL7, tel-025 moves teams); a manager is
    re-checked only when it changes; a duplicate Employee ID is the 409 from flush_profile. Returns the audit (before, after)."""
    changes = parse_profile_update(raw).model_dump(exclude_unset=True)
    if "team" in changes and changes.pop("team") != profile.team:
        raise HTTPException(422, "Team cannot be changed here")
    new_manager = changes.get("reporting_manager_user_id")
    if new_manager is not None and new_manager != profile.reporting_manager_user_id:
        await locked_active_manager(db, new_manager)
    before = profile_snapshot(profile)
    for key, value in changes.items():
        setattr(profile, key, value)
    await flush_profile(db)
    return before, profile_snapshot(profile)


async def telecaller_context(db: AsyncSession, user: User) -> TelecallerProfile:
    """Every telecaller route's gate: the caller is a `telecaller` with a profile row; otherwise 403."""
    if user.role != "telecaller":
        raise HTTPException(403, "Telecaller role required")
    profile = await db.scalar(select(TelecallerProfile).where(TelecallerProfile.user_id == user.id))
    if not profile:
        raise HTTPException(403, "Telecaller profile not set up — contact your administrator")
    return profile


def require_manager(user: User) -> None:
    if user.role not in ("telecaller_manager", "super_admin"):
        raise HTTPException(403, "Telecaller manager role required")


def team_filter(user: User) -> list:
    """T23: a manager's telecallers are exactly their direct reports; super_admin sees all."""
    return [] if user.role == "super_admin" else [TelecallerProfile.reporting_manager_user_id == user.id]


def admin_team_filter(actor: User, team: str | None) -> list:
    allowed = creatable_teams(actor)
    if team is not None:
        if team not in allowed:
            raise _cannot_manage(team)
        return [TelecallerProfile.team == team]
    return [TelecallerProfile.team.in_(sorted(allowed))]
```

Note the `_readable` rule for `phone`: an explicit `null` phone is valid (it clears), so it never maps to "is required"; a missing
`phone` key is `type == "missing"` and still does.

- [ ] **Step 6: Run the tests to verify they pass**

Run the API command with `TESTS=tests/test_tel_001_service.py`.
Expected: all PASS. If the `"Team: Input should be 'it' or 'overseas'"` case fails only on pydantic's wording, print the actual
`detail` and align the test's expected text to it (the prefix `"Team: "` is the contract; pydantic owns the rest).

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/schemas.py apps/api/app/services/telecaller.py apps/api/tests/tel001_helpers.py apps/api/tests/test_tel_001_service.py
git commit -m "feat(tel-001): telecaller schemas and service rules"
```

---

### Task 3: Roles, provisioning through `POST /admin/users`, and the admin-portal reset routing

**Files:**
- Modify: `apps/api/app/core/rbac.py:51-52`
- Modify: `apps/api/app/api/admin.py` (imports ~line 19–75; `create_user` ~465–532)
- Modify: `apps/api/app/services/provisioning.py:66-70`
- Modify: `apps/api/app/api/auth.py` (imports; `reset_password` return ~line 289–291)
- Modify: `apps/api/tests/test_bdm_001_admin_portal_links.py` (the reset `login_portal` cases for the new roles live in the new provisioning test)
- Test: `apps/api/tests/test_tel_001_provisioning.py`, `apps/api/tests/test_tel_001_login.py`

**Interfaces:**
- Consumes: Task 2's service and helpers.
- Produces: `app.services.provisioning.ADMIN_PORTAL_ROLES: frozenset[str]`; `POST /admin/users` response gains key
  `telecaller_profile` (`profile_out` dict or `null`) for every role.

- [ ] **Step 1: Write the failing provisioning test**

Create `apps/api/tests/test_tel_001_provisioning.py`:

```python
"""tel-001 -- POST /admin/users telecaller branch (spec §5.4, §5.6; AC1, AC2)."""

import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.security import verify_password
from app.models import AuditLog, PasswordResetToken, TelecallerProfile, User
from tests.bdm001_helpers import bdm_payload, make_manager
from tests.tel001_helpers import PASSWORD, USERS, create_telecaller, emp, login, make_tl_manager, make_user, tel_payload


@pytest.fixture(autouse=True)
def _loggers_enabled():
    """An earlier in-process migration test's fileConfig disables existing app.* loggers (see ENH-003's note)."""
    for name in ("app.telecaller", "app.admin", "app.provisioning"):
        logging.getLogger(name).disabled = False


async def _as(client, db, role: str, division: str):
    actor = await make_user(db, role, division)
    await login(client, actor)
    return actor


async def _by_email(db, address):
    return await db.scalar(select(User).where(User.email == address))


def _manager_payload():
    return {"role": "telecaller_manager", "division": "global", "email": f"tm-{emp().lower()}@example.local", "full_name": "Meena Manager"}


# --- AC1 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "team"), [("super_admin", "global", "it"), ("super_admin", "global", "overseas"), ("it_admin", "it", "it"), ("overseas_admin", "overseas", "overseas")])
async def test_authorized_admin_creates_a_telecaller_with_a_link_and_no_password(client, db_session, role, division, team):
    manager = await make_tl_manager(db_session)
    await _as(client, db_session, role, division)
    response = await create_telecaller(client, manager.id, team=team)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "telecaller" and body["division"] == team and body["bdm_profile"] is None
    assert body["telecaller_profile"]["team"] == team
    assert body["telecaller_profile"]["reporting_manager"] == {"id": str(manager.id), "full_name": manager.full_name, "active": True}
    assert not any("password" in key.lower() for key in body)
    user = await _by_email(db_session, body["email"])
    assert not verify_password(PASSWORD, user.password_hash)
    welcome = select(func.count()).select_from(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.purpose == "welcome")
    assert await db_session.scalar(welcome) == 1
    assert await db_session.scalar(select(TelecallerProfile).where(TelecallerProfile.user_id == user.id)) is not None


@pytest.mark.asyncio
async def test_super_admin_creates_a_manager_without_a_profile(client, db_session):
    await _as(client, db_session, "super_admin", "global")
    response = await client.post(USERS, json=_manager_payload())
    assert response.status_code == 201, response.text
    assert response.json()["division"] == "global" and response.json()["telecaller_profile"] is None


@pytest.mark.asyncio
async def test_audit_row_carries_the_profile_snapshot(client, db_session):
    manager = await make_tl_manager(db_session)
    await _as(client, db_session, "super_admin", "global")
    body = (await create_telecaller(client, manager.id)).json()
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"], AuditLog.action == "user.create"))
    assert row.metadata_json["telecaller_profile"]["team"] == "it"
    assert row.metadata_json["telecaller_profile"]["reporting_manager_user_id"] == str(manager.id)


# --- AC2 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "team"), [("it_admin", "it", "overseas"), ("overseas_admin", "overseas", "it")])
async def test_division_admin_cannot_create_the_other_team(client, db_session, role, division, team):
    manager = await make_tl_manager(db_session)
    await _as(client, db_session, role, division)
    payload = tel_payload(manager.id, team=team)
    response = await client.post(USERS, json=payload)
    assert response.status_code == 403
    assert response.json()["detail"] == f"Your role cannot manage {'Overseas' if team == 'overseas' else 'IT'} telecallers"
    assert await _by_email(db_session, payload["email"]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_admin", "it"), ("overseas_admin", "overseas")])
async def test_only_super_admin_creates_a_manager(client, db_session, role, division):
    await _as(client, db_session, role, division)
    response = await client.post(USERS, json=_manager_payload())
    assert response.status_code == 403 and response.json()["detail"] == "Only a Super Admin can create telecaller managers"


# --- validation and conflicts -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_profile_and_mismatched_division_are_422(client, db_session):
    manager = await make_tl_manager(db_session)
    await _as(client, db_session, "super_admin", "global")
    missing = tel_payload(manager.id)
    del missing["telecaller_profile"]
    response = await client.post(USERS, json=missing)
    assert response.status_code == 422 and response.json()["detail"] == "Telecaller profile is required"
    response = await create_telecaller(client, manager.id, team="it", division="overseas")
    assert response.status_code == 422 and response.json()["detail"] == "Division must match the telecaller's team"


@pytest.mark.asyncio
async def test_profiles_cannot_cross_roles(client, db_session):
    tl_manager, bdm_manager = await make_tl_manager(db_session), await make_manager(db_session)
    await _as(client, db_session, "super_admin", "global")
    stray_tel = bdm_payload(bdm_manager.id, telecaller_profile={"team": "it", "employee_id": emp(), "reporting_manager_user_id": str(tl_manager.id)})
    response = await client.post(USERS, json=stray_tel)
    assert response.status_code == 422 and response.json()["detail"] == "Only a telecaller has a telecaller profile"
    assert await _by_email(db_session, stray_tel["email"]) is None
    stray_bdm = tel_payload(tl_manager.id, bdm_profile={"bdm_type": "college", "employee_id": emp(), "reporting_manager_user_id": str(bdm_manager.id)})
    assert (await client.post(USERS, json=stray_bdm)).status_code == 422
    counselor = {"role": "counselor", "division": "overseas", "email": f"c-{emp().lower()}@example.local", "full_name": "C", "telecaller_profile": {}}
    assert (await client.post(USERS, json=counselor)).status_code == 422


@pytest.mark.asyncio
async def test_reporting_manager_must_be_an_active_telecaller_manager(client, db_session):
    inactive, bdm_manager = await make_tl_manager(db_session, active=False), await make_manager(db_session)
    await _as(client, db_session, "super_admin", "global")
    for bad in (inactive.id, bdm_manager.id, uuid.uuid4()):
        payload = tel_payload(bad)
        response = await client.post(USERS, json=payload)
        assert response.status_code == 422 and response.json()["detail"] == "Reporting manager must be an active telecaller manager"
        assert await _by_email(db_session, payload["email"]) is None


@pytest.mark.asyncio
async def test_duplicate_employee_id_is_409_case_and_space_insensitive(client, db_session):
    manager = await make_tl_manager(db_session)
    await _as(client, db_session, "super_admin", "global")
    first = tel_payload(manager.id)
    assert (await client.post(USERS, json=first)).status_code == 201
    again = tel_payload(manager.id)
    again["telecaller_profile"]["employee_id"] = f"  {first['telecaller_profile']['employee_id'].lower()} "
    response = await client.post(USERS, json=again)
    assert response.status_code == 409 and response.json()["detail"] == "Employee ID already exists"
    assert await _by_email(db_session, again["email"]) is None


@pytest.mark.asyncio
async def test_supplied_password_is_422(client, db_session):
    manager = await make_tl_manager(db_session)
    await _as(client, db_session, "super_admin", "global")
    assert (await create_telecaller(client, manager.id, password="Whatever-123!")).status_code == 422


# --- set-password link and reset routing (spec §5.6) ------------------------------------------------------------------------
async def _token(db, user, purpose: str = "welcome") -> str:
    raw = uuid.uuid4().hex * 2
    db.add(PasswordResetToken(user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), purpose=purpose, expires_at=datetime.now(UTC) + timedelta(hours=72)))
    await db.commit()
    return raw


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "portal"), [("telecaller_manager", "global", "admin"), ("telecaller", "it", None), ("telecaller", "overseas", None)])
async def test_reset_names_the_admin_portal_only_for_a_telecaller_manager(client, db_session, role, division, portal):
    user = await make_user(db_session, role, division)
    response = await client.post("/api/v1/auth/reset-password", json={"token": await _token(db_session, user), "new_password": "Brand-New-Pass-1!"})
    assert response.json() == {"ok": True, "login_portal": portal}
```

Create `apps/api/tests/test_tel_001_login.py`:

```python
"""tel-001 AC3 -- a telecaller signs in at its team's portal; any other portal gets the existing 'use the correct portal' 403, which
names the right one. Unchanged auth code; this pins the behavior for the new roles."""

import pytest

from tests.tel001_helpers import PASSWORD, make_tl_manager, make_user

LOGIN = "/api/v1/auth/login"


async def _try(client, user, division):
    return await client.post(LOGIN, json={"email": user.email, "password": PASSWORD, "division": division})


@pytest.mark.asyncio
@pytest.mark.parametrize(("team", "other"), [("it", "overseas"), ("overseas", "it")])
async def test_telecaller_signs_in_only_at_its_team_portal(client, db_session, team, other):
    user = await make_user(db_session, "telecaller", team)
    assert (await _try(client, user, team)).status_code == 200
    response = await _try(client, user, other)
    assert response.status_code == 403 and f"/{team}/login" in response.json()["detail"]


@pytest.mark.asyncio
async def test_manager_signs_in_only_at_admin(client, db_session):
    manager = await make_tl_manager(db_session)
    assert (await _try(client, manager, "global")).status_code == 200
    response = await _try(client, manager, "it")
    assert response.status_code == 403 and "/admin/login" in response.json()["detail"]
```

Extend the existing bdm-001 parametrized cases — in `apps/api/tests/test_bdm_001_admin_portal_links.py`, add to the parametrize list:
`("telecaller_manager", "global", "admin"), ("telecaller", "it", "it"), ("telecaller", "overseas", "overseas")`.

- [ ] **Step 2: Run them to verify they fail**

Run the API command with `TESTS="tests/test_tel_001_provisioning.py tests/test_tel_001_login.py tests/test_bdm_001_admin_portal_links.py"`.
Expected: FAIL — provisioning creates return 422 "Role is not valid for the selected division"; the portal-links telecaller_manager case
returns `/it/`; login tests pass already (the division rule is unchanged) — that is expected for `test_tel_001_login.py`.

- [ ] **Step 3: Add the roles**

In `apps/api/app/core/rbac.py`, after line 52 (`"bdm_manager": {"bdm:team"},`):

```python
    # tel-001 (DEC-SCOPE-073): coarse bundles; self/team scope is enforced in services/telecaller.py.
    "telecaller": {"telecaller:self"},
    "telecaller_manager": {"telecaller:team"},
```

- [ ] **Step 4: Route manager links and resets to the admin portal**

In `apps/api/app/services/provisioning.py`, above `def _set_password_url`:

```python
# bdm-001 QA-05 / tel-001 §5.6: the `global` manager roles sign in at /admin, so their set-password and reset pages are the admin
# portal's own. auth.reset_password reads the same set for its `login_portal`.
ADMIN_PORTAL_ROLES = frozenset({"bdm_manager", "telecaller_manager"})
```

and change the `segment` line to:

```python
    segment = "admin" if user.role in ADMIN_PORTAL_ROLES else ("overseas" if user.division == "overseas" else "it")
```

In `apps/api/app/api/auth.py`, add `from app.services.provisioning import ADMIN_PORTAL_ROLES` with the other `app.services` imports
(if `auth.py` already imports from `app.services.provisioning`, add the name to that import), and change the reset return to:

```python
    # bdm-001 (spec §5.6) / tel-001: a `global` manager signs in at /admin/login, and the reset form follows this. The key is always
    # present (null for everyone else), so the response shape never varies by role.
    return {"ok": True, "login_portal": "admin" if user.role in ADMIN_PORTAL_ROLES else None}
```

- [ ] **Step 5: Add the create branch**

In `apps/api/app/api/admin.py`:

Imports — add `TelecallerProfile` to the `from app.models import (...)` block, and next to `from app.services import bdm as bdm_rules`:

```python
from app.services import telecaller as tel_rules
```

In `create_user`, directly after the BDM `if/elif/elif` block (the one ending with
`raise HTTPException(403, "Only a Super Admin can create BDM managers")`) and before
`if user.role != "super_admin" and division != user.division:`, insert:

```python
    # tel-001 (spec §5.4): same placement and order as the BDM block -- profile, then creator team (403), then division (422) -- so a
    # super_admin's mismatch is the 422 and a division admin's other team is the 403. Every other role skips it (bar a stray profile).
    tel_input = None
    if role == "telecaller":
        tel_input = tel_rules.parse_profile_create(payload.get("telecaller_profile"))
        tel_rules.require_creator_may(user, tel_input.team, USERS_ROUTE)
        if "division" not in payload:
            division = tel_input.team
        elif division != tel_input.team:
            raise HTTPException(422, "Division must match the telecaller's team")
    elif "telecaller_profile" in payload:
        raise HTTPException(422, "Only a telecaller has a telecaller profile")
    elif role == "telecaller_manager" and user.role != "super_admin":
        raise HTTPException(403, "Only a Super Admin can create telecaller managers")
```

Change `allowed_by_division` to:

```python
    allowed_by_division = {
        "it": {"it_student", "trainer", "placement_team", "hr_team", "it_admin", "bdm", "telecaller"},
        "overseas": {"overseas_student", "counselor", "university_rep", "agent", "overseas_admin", "bdm", "telecaller"},
        "global": {"super_admin", "bdm_manager", "telecaller_manager"},
    }
```

After the BDM profile block (the one ending `await bdm_rules.flush_profile(db)`), before `issued = await issue_welcome_token(...)`:

```python
    tel_profile = tel_manager = None
    if tel_input is not None:
        # Same transaction as the user, token and audit row; the manager row is locked against a concurrent deactivation.
        tel_manager = await tel_rules.locked_active_manager(db, tel_input.reporting_manager_user_id)
        tel_profile = TelecallerProfile(user_id=item.id, **tel_input.model_dump())
        db.add(tel_profile)
        await tel_rules.flush_profile(db)
```

After `metadata["bdm_profile"] = ...`'s `if`:

```python
    if tel_profile is not None:
        metadata["telecaller_profile"] = tel_rules.profile_snapshot(tel_profile)
```

And in the return dict, after the `"bdm_profile": ...` entry:

```python
        "telecaller_profile": tel_rules.profile_out(tel_profile, tel_manager) if tel_profile is not None else None,
```

- [ ] **Step 6: Run the tests to verify they pass**

Run the API command with
`TESTS="tests/test_tel_001_provisioning.py tests/test_tel_001_login.py tests/test_bdm_001_admin_portal_links.py tests/test_bdm_001_reset_portal.py tests/test_bdm_001_profiles.py tests/test_adm_001_admin_crud.py tests/test_enh_003_first_time_provisioning.py tests/test_adm_012_roles_permissions.py tests/test_rbac.py"`.
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/core/rbac.py apps/api/app/api/admin.py apps/api/app/services/provisioning.py apps/api/app/api/auth.py apps/api/tests/test_tel_001_provisioning.py apps/api/tests/test_tel_001_login.py apps/api/tests/test_bdm_001_admin_portal_links.py
git commit -m "feat(tel-001): provision telecallers and managers via /admin/users"
```

---

### Task 4: Editing a telecaller through `PATCH /admin/users/{id}`

**Files:**
- Modify: `apps/api/app/api/admin.py` (`update_user`, ~535–575)
- Test: `apps/api/tests/test_tel_001_update.py`

**Interfaces:**
- Consumes: `tel_rules.require_creator_may`, `tel_rules.apply_profile_update` (Task 2).
- Produces: audit `user.update` metadata keys `telecaller_profile_before` / `telecaller_profile_after`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_tel_001_update.py`:

```python
"""tel-001 -- PATCH /admin/users/{id} telecaller branch (spec §5.5; TL7)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, TelecallerProfile
from tests.tel001_helpers import create_telecaller, emp, login, make_tl_manager, make_user

USER = "/api/v1/admin/users/{}"


async def _created(client, db, *, team: str = "it"):
    m1, m2 = await make_tl_manager(db), await make_tl_manager(db)
    await login(client, await make_user(db, "super_admin", "global"))
    body = (await create_telecaller(client, m1.id, team=team)).json()
    return m1, m2, body


async def _profile(db, user_id):
    db.expire_all()
    return await db.scalar(select(TelecallerProfile).where(TelecallerProfile.user_id == user_id))


@pytest.mark.asyncio
async def test_admin_changes_employee_id_and_manager_with_an_audit_trail(client, db_session):
    m1, m2, body = await _created(client, db_session)
    new_emp = emp()
    response = await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"employee_id": new_emp, "reporting_manager_user_id": str(m2.id)}})
    assert response.status_code == 200, response.text
    profile = await _profile(db_session, body["id"])
    assert profile.employee_id == new_emp and profile.reporting_manager_user_id == m2.id
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"], AuditLog.action == "user.update"))
    assert row.metadata_json["telecaller_profile_before"]["reporting_manager_user_id"] == str(m1.id)
    assert row.metadata_json["telecaller_profile_after"]["reporting_manager_user_id"] == str(m2.id)


@pytest.mark.asyncio
async def test_team_cannot_change_but_an_equal_team_is_a_no_op(client, db_session):
    _, _, body = await _created(client, db_session)
    response = await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"team": "overseas"}})
    assert response.status_code == 422 and response.json()["detail"] == "Team cannot be changed here"
    assert (await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"team": "it"}})).status_code == 200


@pytest.mark.asyncio
async def test_inactive_or_wrong_manager_and_null_required_fields_are_422(client, db_session):
    _, _, body = await _created(client, db_session)
    inactive = await make_tl_manager(db_session, active=False)
    response = await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"reporting_manager_user_id": str(inactive.id)}})
    assert response.status_code == 422 and response.json()["detail"] == "Reporting manager must be an active telecaller manager"
    response = await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"employee_id": None}})
    assert response.status_code == 422 and response.json()["detail"] == "Employee ID is required"


@pytest.mark.asyncio
async def test_duplicate_employee_id_on_edit_is_409(client, db_session):
    m1, _, body = await _created(client, db_session)
    other = (await create_telecaller(client, m1.id)).json()
    response = await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"employee_id": other["telecaller_profile"]["employee_id"].upper()}})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_profile_on_a_non_telecaller_is_422(client, db_session):
    await login(client, await make_user(db_session, "super_admin", "global"))
    counselor = await make_user(db_session, "counselor", "overseas")
    response = await client.patch(USER.format(counselor.id), json={"telecaller_profile": {"employee_id": emp()}})
    assert response.status_code == 422 and response.json()["detail"] == "Only a telecaller has a telecaller profile"


@pytest.mark.asyncio
async def test_division_admin_cannot_edit_the_other_team(client, db_session):
    _, _, body = await _created(client, db_session, team="overseas")
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.patch(USER.format(body["id"]), json={"full_name": "X"})).status_code == 403
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await client.patch(USER.format(body["id"]), json={"telecaller_profile": {"employee_id": emp()}})).status_code == 200
```

- [ ] **Step 2: Run it to verify it fails**

Run the API command with `TESTS=tests/test_tel_001_update.py`.
Expected: FAIL — profile edits are ignored (200 with nothing changed) and the "Only a telecaller…" case returns 200.

- [ ] **Step 3: Add the update branch**

In `apps/api/app/api/admin.py` `update_user`, directly after the BDM block
(`if "bdm_profile" in payload: ... profile_before, profile_after = await bdm_rules.apply_profile_update(...)`), insert:

```python
    # tel-001 (spec §5.5): the same shape as the BDM branch. The team is fixed here (TL7); a moved manager is re-checked.
    tel_profile = None
    if item.role == "telecaller":
        tel_profile = await db.scalar(select(TelecallerProfile).where(TelecallerProfile.user_id == item.id).with_for_update())
        if tel_profile is not None:
            tel_rules.require_creator_may(user, tel_profile.team, f"{USERS_ROUTE}/{{id}}")
    tel_before = tel_after = None
    if "telecaller_profile" in payload:
        if tel_profile is None:
            raise HTTPException(422, "Only a telecaller has a telecaller profile")
        tel_before, tel_after = await tel_rules.apply_profile_update(db, tel_profile, payload["telecaller_profile"])
```

and after `if profile_before is not None: metadata.update(bdm_profile_before=..., bdm_profile_after=...)`:

```python
    if tel_before is not None:
        metadata.update(telecaller_profile_before=tel_before, telecaller_profile_after=tel_after)
```

`metadata` is built from `payload`, so it also carries the raw `telecaller_profile` dict, exactly as the BDM branch does.

- [ ] **Step 4: Run the tests to verify they pass**

Run the API command with `TESTS="tests/test_tel_001_update.py tests/test_bdm_001_profiles.py tests/test_adm_001_admin_crud.py"`.
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/admin.py apps/api/tests/test_tel_001_update.py
git commit -m "feat(tel-001): edit a telecaller's profile via /admin/users"
```

---

### Task 5: Read routes and the self-service phone edit — `api/telecaller.py`

**Files:**
- Create: `apps/api/app/api/telecaller.py`
- Modify: `apps/api/app/main.py` (import list ~line 9–30; router tuple line 79)
- Test: `apps/api/tests/test_tel_001_reads.py`

**Interfaces:**
- Consumes: Task 2 service; `app.api.bdm` helpers `LIMIT`, `OFFSET`, `SEARCH`, `_matching`, `_paged`; `app.api.admin.ensure_admin`;
  `app.api.lookups._pattern`.
- Produces (HTTP): `GET /api/v1/telecaller/me`, `PATCH /api/v1/telecaller/profile`, `GET /api/v1/telecaller/manager/team`,
  `GET /api/v1/admin/telecallers`, `GET /api/v1/admin/telecaller-managers` (shapes in spec §5.7).

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_tel_001_reads.py`:

```python
"""tel-001 -- read routes and the phone self-edit (spec §5.7; AC4, TL3)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, User
from tests.tel001_helpers import create_telecaller, login, make_tl_manager, make_user, sign_in_as_created

ME, PROFILE, TEAM = "/api/v1/telecaller/me", "/api/v1/telecaller/profile", "/api/v1/telecaller/manager/team"
ADMIN_LIST, MANAGERS = "/api/v1/admin/telecallers", "/api/v1/admin/telecaller-managers"


async def _teams(client, db):
    """M1 has an IT and an Overseas telecaller (the Overseas one deactivated); M2 has one IT telecaller. Signed in as super_admin."""
    m1, m2 = await make_tl_manager(db), await make_tl_manager(db)
    await login(client, await make_user(db, "super_admin", "global"))
    a = (await create_telecaller(client, m1.id, team="it")).json()
    b = (await create_telecaller(client, m1.id, team="overseas")).json()
    c = (await create_telecaller(client, m2.id, team="it")).json()
    assert (await client.patch(f"/api/v1/admin/users/{b['id']}", json={"active": False})).status_code == 200
    return m1, m2, a, b, c


async def _all_ids(client, url, **params) -> set:
    ids, offset = set(), 0
    while True:
        page = (await client.get(url, params={"limit": 100, "offset": offset, **params})).json()
        ids |= {r["id"] for r in page["items"]}
        offset += 100
        if offset >= page["total"]:
            return ids


# --- AC4 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_sees_only_direct_reports(client, db_session):
    m1, _, a, b, c = await _teams(client, db_session)
    await login(client, m1)
    body = (await client.get(TEAM)).json()
    assert body["total"] == 2 and {r["id"] for r in body["items"]} == {a["id"], b["id"]}
    assert {r["id"]: r["active"] for r in body["items"]} == {a["id"]: True, b["id"]: False}
    assert set(body["items"][0]) == {"id", "full_name", "email", "phone", "active", "team", "employee_id"}


@pytest.mark.asyncio
async def test_super_admin_sees_every_telecaller_on_the_team_route(client, db_session):
    _, _, a, b, c = await _teams(client, db_session)
    assert {a["id"], b["id"], c["id"]} <= await _all_ids(client, TEAM)


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("telecaller", "it"), ("bdm_manager", "global"), ("it_admin", "it")])
async def test_team_route_refuses_other_roles(client, db_session, role, division):
    await login(client, await make_user(db_session, role, division))
    response = await client.get(TEAM)
    assert response.status_code == 403


# --- /me and the phone self-edit -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_me_returns_own_profile(client, db_session):
    m1, _, a, _, _ = await _teams(client, db_session)
    await sign_in_as_created(client, db_session, a)
    body = (await client.get(ME)).json()
    assert body["id"] == a["id"] and body["division"] == "it"
    assert body["telecaller_profile"]["reporting_manager"] == {"id": str(m1.id), "full_name": m1.full_name, "active": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("telecaller_manager", "global")])
async def test_me_and_profile_refuse_other_roles(client, db_session, role, division):
    await login(client, await make_user(db_session, role, division))
    assert (await client.get(ME)).status_code == 403
    assert (await client.patch(PROFILE, json={"phone": "123"})).status_code == 403


@pytest.mark.asyncio
async def test_self_update_sets_and_clears_phone_with_audit(client, db_session):
    _, _, a, _, _ = await _teams(client, db_session)
    await sign_in_as_created(client, db_session, a)
    response = await client.patch(PROFILE, json={"phone": " +91 98765 43210 "})
    assert response.status_code == 200 and response.json()["phone"] == "+91 98765 43210"
    assert (await client.patch(PROFILE, json={"phone": ""})).json()["phone"] is None
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == a["id"], AuditLog.action == "telecaller.profile_update"))).all()
    assert len(rows) == 2 and all(r.metadata_json == {"fields": ["phone"]} for r in rows)


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{"employee_id": "HACK"}, {"team": "overseas"}, {"reporting_manager_user_id": "00000000-0000-0000-0000-000000000000"}, {"full_name": "X"}])
async def test_self_update_rejects_other_fields(client, db_session, extra):
    _, _, a, _, _ = await _teams(client, db_session)
    user = await sign_in_as_created(client, db_session, a)
    before = (await client.get(ME)).json()
    response = await client.patch(PROFILE, json={"phone": "1", **extra})
    assert response.status_code == 422 and response.json()["detail"].startswith("Unknown field: ")
    db_session.expire_all()
    assert (await client.get(ME)).json() == before
    assert (await db_session.get(User, user.id)).phone == before["phone"]


# --- admin list and manager picker --------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_list_is_scoped_to_the_admins_team(client, db_session):
    _, _, a, b, c = await _teams(client, db_session)
    await login(client, await make_user(db_session, "it_admin", "it"))
    ids = await _all_ids(client, ADMIN_LIST)
    assert {a["id"], c["id"]} <= ids and b["id"] not in ids
    assert (await client.get(ADMIN_LIST, params={"team": "overseas"})).status_code == 403
    assert (await client.get(ADMIN_LIST, params={"team": "global"})).status_code == 422


@pytest.mark.asyncio
async def test_admin_list_filters_and_searches(client, db_session):
    _, _, a, b, _ = await _teams(client, db_session)
    found = (await client.get(ADMIN_LIST, params={"q": a["telecaller_profile"]["employee_id"]})).json()
    assert [r["id"] for r in found["items"]] == [a["id"]]
    assert b["id"] in await _all_ids(client, ADMIN_LIST, active="false")
    assert b["id"] not in await _all_ids(client, ADMIN_LIST, active="true")


@pytest.mark.asyncio
async def test_admin_list_flags_inactive_manager(client, db_session):
    m1, _, a, _, _ = await _teams(client, db_session)
    assert (await client.patch(f"/api/v1/admin/users/{m1.id}", json={"active": False})).status_code == 200
    found = (await client.get(ADMIN_LIST, params={"q": a["telecaller_profile"]["employee_id"]})).json()["items"][0]
    assert found["manager_active"] is False and found["reporting_manager"]["active"] is False


@pytest.mark.asyncio
async def test_manager_picker_lists_active_managers_only(client, db_session):
    active, inactive = await make_tl_manager(db_session, name="Picker Active"), await make_tl_manager(db_session, active=False, name="Picker Inactive")
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    ids = await _all_ids(client, MANAGERS)
    assert str(active.id) in ids and str(inactive.id) not in ids
    hit = (await client.get(MANAGERS, params={"q": active.email})).json()["items"]
    assert hit == [{"id": str(active.id), "full_name": "Picker Active", "email": active.email}]
    await login(client, await make_user(db_session, "telecaller", "it"))
    assert (await client.get(MANAGERS)).status_code == 403
```

- [ ] **Step 2: Run it to verify it fails**

Run the API command with `TESTS=tests/test_tel_001_reads.py`.
Expected: FAIL — 404 for every `/telecaller/*` and `/admin/telecaller*` route.

- [ ] **Step 3: Write the router**

Create `apps/api/app/api/telecaller.py`:

```python
"""tel-001 (DEC-SCOPE-073, spec §5.7): telecaller and manager reads, the telecaller's phone self-edit (TL3), the admin telecaller
list and the reporting-manager picker.

Scope always comes from the session -- no /telecaller route takes a user id -- so there is no IDOR surface; the admin list is
narrowed by team in SQL (T21). Lists reuse bdm-001's paging helpers: {items, total, limit, offset}, ordered by name then id."""

from typing import Literal

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.admin import ensure_admin
from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching, _paged
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import AuditLog, TelecallerProfile, User
from app.schemas import BdmManagerPage, TelecallerAdminPage, TelecallerMeOut, TelecallerTeamPage
from app.services.telecaller import admin_team_filter, parse_self_update, person_ref, profile_out, require_manager, team_filter, telecaller_context

router = APIRouter(prefix="/telecaller", tags=["telecaller"])
admin_router = APIRouter(prefix="/admin", tags=["telecaller-admin"])
Manager = aliased(User)


def _team_row(profile: TelecallerProfile, user: User) -> dict:
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active,
        "team": profile.team, "employee_id": profile.employee_id,
    }


def _admin_row(profile: TelecallerProfile, user: User, manager: User) -> dict:
    return {**_team_row(profile, user), "reporting_manager": person_ref(manager), "manager_active": manager.active}


def _profiles(filters: list):
    """One query: profile + its user + its manager (no N+1)."""
    return (
        select(TelecallerProfile, User, Manager)
        .join(User, User.id == TelecallerProfile.user_id)
        .join(Manager, Manager.id == TelecallerProfile.reporting_manager_user_id)
        .where(*filters)
    )


def _me(user: User, profile: TelecallerProfile, manager: User) -> dict:
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active,
        "division": user.division, "telecaller_profile": profile_out(profile, manager),
    }


@router.get("/me", response_model=TelecallerMeOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await telecaller_context(db, user)
    return _me(user, profile, await db.get(User, profile.reporting_manager_user_id))


@router.patch("/profile", response_model=TelecallerMeOut)
async def update_own_profile(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """TL3: the phone only; every other key is a 422 (TelecallerSelfUpdate forbids extras). The audit row names the field, not the
    value (no phone numbers in the log)."""
    profile = await telecaller_context(db, user)
    user.phone = parse_self_update(payload).phone
    db.add(AuditLog(user_id=user.id, action="telecaller.profile_update", entity_type="user", entity_id=str(user.id), metadata_json={"fields": ["phone"]}))
    out = _me(user, profile, await db.get(User, profile.reporting_manager_user_id))
    await db.commit()
    return out


@router.get("/manager/team", response_model=TelecallerTeamPage)
async def team(q: str | None = SEARCH, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """T23 / AC4: a manager's direct reports (inactive included, with their status); super_admin sees all. `q` only narrows."""
    require_manager(user)
    filters = team_filter(user) + _matching(like_pattern(q), User.full_name, User.email, TelecallerProfile.employee_id)
    return await _paged(db, _profiles(filters), limit, offset, lambda profile, member, _manager: _team_row(profile, member))


@admin_router.get("/telecallers", response_model=TelecallerAdminPage)
async def admin_telecallers(
    team: Literal["it", "overseas"] | None = None,
    active: bool | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(ensure_admin),
    db: AsyncSession = Depends(get_db),
):
    """`q` matches name, email or Employee ID; it is ANDed with the caller's team scope, so it can never widen it."""
    filters = admin_team_filter(user, team)
    if active is not None:
        filters.append(User.active.is_(active))
    filters += _matching(like_pattern(q), User.full_name, User.email, TelecallerProfile.employee_id)
    return await _paged(db, _profiles(filters), limit, offset, _admin_row)


@admin_router.get("/telecaller-managers", response_model=BdmManagerPage)
async def telecaller_managers(q: str | None = SEARCH, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """The reporting-manager picker: active telecaller managers only, searchable by name or email; email tells same-name managers apart."""
    stmt = select(User.id, User.full_name, User.email).where(
        User.role == "telecaller_manager", User.active.is_(True), *_matching(like_pattern(q), User.full_name, User.email)
    )
    return await _paged(db, stmt, limit, offset, lambda id_, full_name, email: {"id": id_, "full_name": full_name, "email": email})
```

`BdmManagerPage`'s item model (`id`, `full_name`, `email`) is role-neutral, so it is reused rather than copied.

- [ ] **Step 4: Register the routers**

In `apps/api/app/main.py`, add `telecaller,` to the `from app.api import (...)` list (alphabetical position), and append
`telecaller.router, telecaller.admin_router` to the router tuple on line 79 (after `bdm_leads.router`).

- [ ] **Step 5: Run the tests to verify they pass**

Run the API command with `TESTS="tests/test_tel_001_reads.py tests/test_bdm_001_reads.py"`.
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/telecaller.py apps/api/app/main.py apps/api/tests/test_tel_001_reads.py
git commit -m "feat(tel-001): telecaller reads, phone self-edit, admin list and manager picker"
```

---

### Task 6: Sign-in routing — navigation, middleware, chooser, create-user form, admin login copy

**Files:**
- Modify: `apps/web/lib/navigation.ts` (after the BDM block ~line 63; `ROLE_DASHBOARD_PATH` ~41; `PORTAL_NAV` lines 114 and 118; `SUPER_ADMIN_NAV` line 147)
- Modify: `apps/web/middleware.ts`
- Modify: `apps/web/components/WorkflowPanel.tsx:365-366`
- Modify: `apps/web/app/admin/login/page.tsx` (subtitle text), comments in `app/admin/forgot-password/page.tsx:4`, `components/LoginForm.tsx:55`, `components/ResetPasswordForm.tsx:15,53`
- Create: `apps/web/app/telecaller/sign-in/page.tsx`, `apps/web/app/telecaller/page.tsx`, `apps/web/app/telecaller/manager/page.tsx`
- Modify: `apps/web/tests/lib/middleware.test.ts`, `apps/web/tests/e2e/adm-001-admin-crud.spec.ts:126`
- Test: `apps/web/tests/lib/navigation.telecaller.test.ts`, `apps/web/tests/components/TelecallerSignIn.test.tsx`

**Interfaces:**
- Produces: `TELECALLER_NAV`, `TELECALLER_MANAGER_NAV`, `TELECALLER_SIGN_IN` (= `"/telecaller/sign-in"`) from `@/lib/navigation`;
  `ROLE_DASHBOARD_PATH.telecaller` / `.telecaller_manager`.

- [ ] **Step 1: Write the failing tests**

Append to `apps/web/tests/lib/middleware.test.ts` (inside the file, after the existing `describe`):

```ts
describe("middleware /telecaller (tel-001 AC5, TL1)", () => {
  it("sends a signed-out manager route to the admin sign-in, keeping next", () => {
    expect(go("/telecaller/manager/team?offset=50")).toBe("http://localhost/admin/login?next=%2Ftelecaller%2Fmanager%2Fteam%3Foffset%3D50");
    expect(go("/telecaller/manager")).toBe("http://localhost/admin/login?next=%2Ftelecaller%2Fmanager");
  });

  it("sends other signed-out /telecaller routes to the chooser", () => {
    expect(go("/telecaller/dashboard")).toBe("http://localhost/telecaller/sign-in?next=%2Ftelecaller%2Fdashboard");
    expect(go("/telecaller")).toBe("http://localhost/telecaller/sign-in?next=%2Ftelecaller");
    expect(go("/telecaller/managerial")).toBe("http://localhost/telecaller/sign-in?next=%2Ftelecaller%2Fmanagerial");
  });

  it("leaves the chooser public, unrelated paths alone, and signed-in visits through", () => {
    expect(go("/telecaller/sign-in")).toBeNull();
    expect(go("/telecallerx")).toBeNull();
    expect(go("/telecaller/dashboard", true)).toBeNull();
    expect(go("/admin/telecallers")).toBe("http://localhost/admin/login?next=%2Fadmin%2Ftelecallers");
    expect(config.matcher).toContain("/telecaller/:path*");
    expect(go("/bdm/my-day")).toBe("http://localhost/bdm/sign-in?next=%2Fbdm%2Fmy-day");
  });
});
```

Create `apps/web/tests/lib/navigation.telecaller.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { PORTAL_NAV, ROLE_DASHBOARD_PATH, SUPER_ADMIN_NAV, TELECALLER_MANAGER_NAV, TELECALLER_NAV, TELECALLER_SIGN_IN } from "@/lib/navigation";

describe("tel-001 navigation", () => {
  it("lands each telecaller role on its own page (AC3)", () => {
    expect(ROLE_DASHBOARD_PATH.telecaller).toBe("/telecaller/dashboard");
    expect(ROLE_DASHBOARD_PATH.telecaller_manager).toBe("/telecaller/manager/team");
  });

  it("has a telecaller nav, a manager nav and the sign-in chooser path", () => {
    expect(TELECALLER_NAV.map((x) => x.href)).toEqual(["/telecaller/dashboard", "/telecaller/profile"]);
    expect(TELECALLER_MANAGER_NAV.map((x) => x.href)).toEqual(["/telecaller/manager/team"]);
    expect(TELECALLER_SIGN_IN).toBe("/telecaller/sign-in");
  });

  it("gives each admin a Telecallers entry", () => {
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Telecallers", href: "/admin/telecallers" });
    expect(PORTAL_NAV["it/admin"]).toContainEqual({ label: "Telecallers", href: "/it/admin/telecallers" });
    expect(PORTAL_NAV["overseas/admin"]).toContainEqual({ label: "Telecallers", href: "/overseas/admin/telecallers" });
  });
});
```

Create `apps/web/tests/components/TelecallerSignIn.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import TelecallerSignInPage from "@/app/telecaller/sign-in/page";

afterEach(cleanup);

async function renderWith(next?: string) {
  render(await TelecallerSignInPage({ searchParams: Promise.resolve(next === undefined ? {} : { next }) }));
}

describe("/telecaller/sign-in (tel-001 TL1)", () => {
  it("offers both team portals and Administration, carrying a same-site next", async () => {
    await renderWith("/telecaller/dashboard");
    expect(screen.getByRole("heading", { level: 1, name: "Telecaller sign-in" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "IT team" })).toHaveAttribute("href", "/it/login?next=%2Ftelecaller%2Fdashboard");
    expect(screen.getByRole("link", { name: "Overseas team" })).toHaveAttribute("href", "/overseas/login?next=%2Ftelecaller%2Fdashboard");
    expect(screen.getByRole("link", { name: "Administration" })).toHaveAttribute("href", "/admin/login?next=%2Ftelecaller%2Fdashboard");
  });

  it("drops an off-site next", async () => {
    await renderWith("https://evil.example/x");
    expect(screen.getByRole("link", { name: "IT team" })).toHaveAttribute("href", "/it/login");
    expect(screen.getByRole("link", { name: "Overseas team" })).toHaveAttribute("href", "/overseas/login");
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run the web command with `CMD="npx vitest run tests/lib/middleware.test.ts tests/lib/navigation.telecaller.test.ts tests/components/TelecallerSignIn.test.tsx"`.
Expected: FAIL — telecaller redirects are null; `TELECALLER_NAV` undefined; the sign-in page module is missing.

- [ ] **Step 3: Navigation**

In `apps/web/lib/navigation.ts`:

In `ROLE_DASHBOARD_PATH`, after `bdm_manager: "/bdm/manager/dashboard",`:

```ts
  // tel-001 (DEC-SCOPE-073): the Telecaller CRM roles. tel-021 fills the dashboard in; managers land on their team (T23).
  telecaller: "/telecaller/dashboard",
  telecaller_manager: "/telecaller/manager/team",
```

After `export const BDM_SIGN_IN = "/bdm/sign-in";`:

```ts

// tel-001: the telecaller and telecaller-manager sidebars and the signed-out chooser (IT telecallers sign in at /it, Overseas at
// /overseas, managers at /admin). Later tel items add their pages here.
export const TELECALLER_NAV: NavItem[] = [
  { label: "Dashboard", href: "/telecaller/dashboard" }, { label: "Profile", href: "/telecaller/profile" },
];
export const TELECALLER_MANAGER_NAV: NavItem[] = [{ label: "Team", href: "/telecaller/manager/team" }];
export const TELECALLER_SIGN_IN = "/telecaller/sign-in";
```

In `PORTAL_NAV["it/admin"]` (line 114), after `{label:"BDMs",href:"/it/admin/bdms"}` add `,{label:"Telecallers",href:"/it/admin/telecallers"}`.
In `PORTAL_NAV["overseas/admin"]` (line 118), after `{label:"BDMs",href:"/overseas/admin/bdms"}` add `,{label:"Telecallers",href:"/overseas/admin/telecallers"}`.
In `SUPER_ADMIN_NAV` (line 147), after `{label:"BDM Travel Approvals",href:"/admin/bdm-travel-approvals"}` add `,{label:"Telecallers",href:"/admin/telecallers"}`.

- [ ] **Step 4: Middleware**

Replace `apps/web/middleware.ts` with:

```ts
import { NextRequest, NextResponse } from "next/server";
const PUBLIC_PATHS = new Set(["/admin/login", "/admin/forgot-password", "/admin/reset-password", "/bdm/sign-in", "/telecaller/sign-in"]);
export function middleware(req:NextRequest) {
  const p=req.nextUrl.pathname;
  // bdm-001 (AC12): /bdm is protected; /bdm/sign-in is the public chooser. QA-05: the admin portal's recovery pages are public too.
  // tel-001 (AC5, TL1): /telecaller likewise, with /telecaller/sign-in as its chooser.
  const protectedRoute = !PUBLIC_PATHS.has(p) &&/^\/(it\/(student|trainer|placement|hr|admin)|overseas\/(student|counselor|university|agent|admin)|admin|bdm|telecaller)(\/|$)/.test(p);
  if (protectedRoute && !req.cookies.get("edusphere_access")) {
    // AGN-008 QA8-07: `next` keeps the query string (e.g. an Applications filter); LoginForm only follows a same-origin path.
    const next=encodeURIComponent(p+req.nextUrl.search);
    // bdm-001 / tel-001: managers (division global) sign in at /admin; a BDM's or telecaller's portal depends on their module/team,
    // so they pick on their chooser.
    if(p.startsWith("/admin")||/^\/(bdm|telecaller)\/manager(\/|$)/.test(p)) return NextResponse.redirect(new URL(`/admin/login?next=${next}`,req.url));
    if(p.startsWith("/bdm")) return NextResponse.redirect(new URL(`/bdm/sign-in?next=${next}`,req.url));
    if(p.startsWith("/telecaller")) return NextResponse.redirect(new URL(`/telecaller/sign-in?next=${next}`,req.url));
    const division=p.startsWith("/overseas")?"overseas":"it";
    return NextResponse.redirect(new URL(`/${division}/login?next=${next}`,req.url));
  }
  return NextResponse.next();
}
export const config={matcher:["/it/:path*","/overseas/:path*","/admin/:path*","/bdm/:path*","/telecaller/:path*"]};
```

Next's matcher `/telecaller/:path*` matches `/telecaller` itself, so the index is protected too.

- [ ] **Step 5: Chooser and index pages**

Create `apps/web/app/telecaller/sign-in/page.tsx`:

```tsx
import Link from "next/link";

import { safeNextPath } from "@/lib/safeNext";

// tel-001 (TL1, AC5): a signed-out telecaller picks their team's portal (IT telecallers belong to the IT division, Overseas to Overseas);
// managers sign in at Administration. `next` passes through only when it is a same-origin path.
export default async function TelecallerSignInPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const next = safeNextPath((await searchParams).next ?? null);
  const suffix = next ? `?next=${encodeURIComponent(next)}` : "";
  return (
    <div className="auth-form-wrap" style={{ minHeight: "100vh" }}>
      <div className="auth-card">
        <Link href="/" className="muted">← Corporate website</Link>
        <h1 style={{ marginTop: 22, fontSize: 28 }}>Telecaller sign-in</h1>
        <p className="muted">Choose your team&apos;s portal. Telecaller Managers sign in at <Link href={`/admin/login${suffix}`}>Administration</Link>.</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 16 }}>
          <Link className="btn" style={{ flex: "1 1 220px", textAlign: "center" }} href={`/it/login${suffix}`}>IT team</Link>
          <Link className="btn" style={{ flex: "1 1 220px", textAlign: "center" }} href={`/overseas/login${suffix}`}>Overseas team</Link>
        </div>
      </div>
    </div>
  );
}
```

Create `apps/web/app/telecaller/page.tsx`:

```tsx
import { redirect } from "next/navigation";

// tel-001: /telecaller has no page of its own (and is a sign-in `next` target) -- send telecallers to their dashboard.
export default function TelecallerIndex() {
  redirect("/telecaller/dashboard");
}
```

Create `apps/web/app/telecaller/manager/page.tsx`:

```tsx
import { redirect } from "next/navigation";

// tel-001: /telecaller/manager has no page of its own -- the manager's landing is their team.
export default function TelecallerManagerIndex() {
  redirect("/telecaller/manager/team");
}
```

- [ ] **Step 6: Create-user form and admin-login copy**

In `apps/web/components/WorkflowPanel.tsx`, replace lines 365–366 with:

```ts
  // bdm-001 / tel-001: managers have no profile, so this generic form creates them; a BDM or telecaller needs its own admin page
  // (profile required).
  global: ["super_admin", "bdm_manager", "telecaller_manager"],
```

In `apps/web/app/admin/login/page.tsx`, change the text `For Super Admins and BDM Managers.` to
`For Super Admins, BDM Managers and Telecaller Managers.` (text only).

Comments only: in `app/admin/forgot-password/page.tsx:4`, `components/LoginForm.tsx:55` and `components/ResetPasswordForm.tsx:15,53`,
change "BDM Managers"/"BDM managers"/"a BDM manager" to also name telecaller managers (e.g. "BDM and Telecaller Managers"). No logic changes.

In `apps/web/tests/e2e/adm-001-admin-crud.spec.ts:126`, append `"telecaller manager"` after `"bdm manager"` in the expected
`roleOptions` array, and extend the comment on line 125 with "tel-001: and telecaller managers".

- [ ] **Step 7: Run the tests to verify they pass**

Run the web command with
`CMD="npx vitest run tests/lib/middleware.test.ts tests/lib/navigation.telecaller.test.ts tests/lib/navigation.bdm.test.ts tests/lib/navigation.test.ts tests/components/TelecallerSignIn.test.tsx tests/components/WorkflowPanel.create-user.test.tsx tests/components/LoginForm.next.test.tsx tests/components/ResetPasswordForm.test.tsx tests/components/AdminPasswordRecovery.test.tsx"`.
Expected: all PASS. If `WorkflowPanel.create-user.test.tsx` pins the global role list, add `"telecaller_manager"` to its expectation
(the form must mirror the server's allow-list).

- [ ] **Step 8: Commit**

```bash
git add apps/web/lib/navigation.ts apps/web/middleware.ts apps/web/components/WorkflowPanel.tsx apps/web/app/admin/login/page.tsx apps/web/app/admin/forgot-password/page.tsx apps/web/components/LoginForm.tsx apps/web/components/ResetPasswordForm.tsx apps/web/app/telecaller apps/web/tests/lib/middleware.test.ts apps/web/tests/lib/navigation.telecaller.test.ts apps/web/tests/components/TelecallerSignIn.test.tsx apps/web/tests/e2e/adm-001-admin-crud.spec.ts apps/web/tests/components/WorkflowPanel.create-user.test.tsx
git commit -m "feat(tel-001): telecaller sign-in routing, navigation and chooser"
```

---

### Task 7: Telecaller and manager pages — dashboard, profile with phone edit, team

**Files:**
- Create: `apps/web/lib/telecaller.ts`
- Create: `apps/web/components/TelecallerProfileCard.tsx`, `TelecallerPhoneForm.tsx`, `TelecallerTeamTable.tsx`
- Create: `apps/web/app/telecaller/dashboard/page.tsx`, `apps/web/app/telecaller/profile/page.tsx`, `apps/web/app/telecaller/manager/team/page.tsx`
- Test: `apps/web/tests/components/TelecallerPhoneForm.test.tsx`, `apps/web/tests/components/TelecallerTeamTable.test.tsx`

**Interfaces:**
- Consumes: `TELECALLER_NAV`, `TELECALLER_MANAGER_NAV`, `TELECALLER_SIGN_IN` (Task 6); API shapes (Task 5).
- Produces (`@/lib/telecaller`): types `TelecallerTeam`, `ManagerRef`, `TelecallerMe`, `TelecallerTeamRow`, `TelecallerAdminRow`,
  `ManagerOption`; `TEAM_LABEL`, `teamRoleLabel(team)`, `creatableTeams(role)`, `statusLabel(active)`, `formText`, `formOptional`,
  `TELECALLERS_URL`, `MANAGERS_URL`, `USERS_URL`, `PROFILE_URL`, `PAGE_SIZE`, `pageOffset(raw)`, `managerSearch(q, signal)`.

- [ ] **Step 1: Write the failing tests**

Create `apps/web/tests/components/TelecallerPhoneForm.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TelecallerPhoneForm from "@/components/TelecallerPhoneForm";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("TelecallerPhoneForm (tel-001 TL3)", () => {
  it("PATCHes only the phone, announces success and refreshes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ phone: "+91 98" }));
    vi.stubGlobal("fetch", fetchMock);
    render(<TelecallerPhoneForm phone="+91 11" />);
    fireEvent.change(screen.getByLabelText("Mobile"), { target: { value: "+91 98" } });
    fireEvent.click(screen.getByRole("button", { name: "Save mobile" }));
    expect(await screen.findByText("Mobile saved.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/telecaller/profile");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ phone: "+91 98" });
    expect(refresh).toHaveBeenCalled();
  });

  it("sends null for an empty field (clears it)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ phone: null }));
    vi.stubGlobal("fetch", fetchMock);
    render(<TelecallerPhoneForm phone="+91 11" />);
    fireEvent.change(screen.getByLabelText("Mobile"), { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save mobile" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ phone: null });
  });

  it("shows the server's message, keeps the typed value and focuses the message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Phone may contain only digits, spaces and + - ( )" }, 422)));
    render(<TelecallerPhoneForm phone={null} />);
    fireEvent.change(screen.getByLabelText("Mobile"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save mobile" }));
    const message = await screen.findByText("Phone may contain only digits, spaces and + - ( )");
    expect(screen.getByLabelText("Mobile")).toHaveValue("abc");
    await waitFor(() => expect(document.activeElement).toBe(message));
    expect(refresh).not.toHaveBeenCalled();
  });
});
```

Create `apps/web/tests/components/TelecallerTeamTable.test.tsx`:

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import TelecallerTeamTable from "@/components/TelecallerTeamTable";
import type { TelecallerTeamRow } from "@/lib/telecaller";

afterEach(cleanup);

const row = (i: number, active = true): TelecallerTeamRow => ({
  id: `t${i}`, full_name: `Caller ${i}`, email: `c${i}@x.local`, phone: i % 2 ? null : "+91 1", active, team: i % 2 ? "overseas" : "it", employee_id: `E-${i}`,
});

describe("TelecallerTeamTable (tel-001 AC4)", () => {
  it("lists each report with team and a worded status", () => {
    render(<TelecallerTeamTable page={{ items: [row(1), row(2, false)], total: 2, limit: 50, offset: 0 }} />);
    const table = within(screen.getByRole("region", { name: "Team" }));
    expect(table.getByText("Caller 1")).toBeInTheDocument();
    expect(table.getByText("Overseas")).toBeInTheDocument();
    expect(table.getByText("Inactive")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Team pages" })).toBeNull();
  });

  it("pages with links that keep the offset in the URL", () => {
    render(<TelecallerTeamTable page={{ items: [row(51)], total: 120, limit: 50, offset: 50 }} />);
    const pager = within(screen.getByRole("navigation", { name: "Team pages" }));
    expect(pager.getByText("Showing 51–51 of 120")).toBeInTheDocument();
    expect(pager.getByRole("link", { name: "Previous page" })).toHaveAttribute("href", "/telecaller/manager/team?offset=0");
    expect(pager.getByRole("link", { name: "Next page" })).toHaveAttribute("href", "/telecaller/manager/team?offset=51");
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run the web command with `CMD="npx vitest run tests/components/TelecallerPhoneForm.test.tsx tests/components/TelecallerTeamTable.test.tsx"`.
Expected: FAIL — modules not found.

- [ ] **Step 3: Shared web module**

Create `apps/web/lib/telecaller.ts`:

```ts
// tel-001 (DEC-SCOPE-073): telecaller types, labels and endpoints shared by the telecaller pages and the admin Telecallers page.
import type { LookupPage } from "@/lib/lookups";

export type TelecallerTeam = "it" | "overseas";
export type ManagerRef = { id: string; full_name: string; active: boolean };
export type TelecallerProfile = { team: TelecallerTeam; employee_id: string; reporting_manager: ManagerRef };
export type TelecallerMe = { id: string; full_name: string; email: string; phone: string | null; active: boolean; division: string; telecaller_profile: TelecallerProfile };
export type TelecallerTeamRow = { id: string; full_name: string; email: string; phone: string | null; active: boolean; team: TelecallerTeam; employee_id: string };
export type TelecallerAdminRow = TelecallerTeamRow & { reporting_manager: ManagerRef; manager_active: boolean };
export type ManagerOption = { id: string; full_name: string; email: string };

export const TEAM_LABEL: Record<TelecallerTeam, string> = { it: "IT", overseas: "Overseas" };
export const teamRoleLabel = (team: TelecallerTeam) => `${TEAM_LABEL[team]} Telecaller`;
// Display only -- the API decides (services/telecaller.CREATOR_TEAMS).
const CREATOR_TEAMS: Record<string, TelecallerTeam[]> = { super_admin: ["it", "overseas"], it_admin: ["it"], overseas_admin: ["overseas"] };
export const creatableTeams = (role: string): TelecallerTeam[] => CREATOR_TEAMS[role] ?? [];
export const statusLabel = (active: boolean) => (active ? "Active" : "Inactive");

// Form readers: trimmed text, and "" sent as null.
export const formText = (form: FormData, name: string) => String(form.get(name) ?? "").trim();
export const formOptional = (form: FormData, name: string) => formText(form, name) || null;

export const TELECALLERS_URL = "/api/v1/admin/telecallers";
export const MANAGERS_URL = "/api/v1/admin/telecaller-managers";
export const USERS_URL = "/api/v1/admin/users";
export const PROFILE_URL = "/api/v1/telecaller/profile";
export const PAGE_SIZE = 50;
/** A list page's `?offset=`: a positive whole number, anything else is the first page. */
export function pageOffset(raw: string | undefined): number {
  const n = Number.parseInt(raw ?? "0", 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
}
const PICKER_LIMIT = 20;

/** The reporting-manager picker searches the server (SearchableSelect server mode), so every manager is reachable. */
export async function managerSearch(q: string, signal: AbortSignal): Promise<LookupPage> {
  const query = new URLSearchParams({ limit: String(PICKER_LIMIT) });
  if (q) query.set("q", q);
  const response = await fetch(`${MANAGERS_URL}?${query}`, { signal });
  if (!response.ok) throw new Error(`Manager search failed (${response.status})`);
  const page = (await response.json()) as { items: ManagerOption[]; total: number };
  return { items: page.items.map((m) => ({ id: m.id, label: m.full_name, detail: m.email })), truncated: page.total > page.items.length };
}
```

- [ ] **Step 4: Components**

Create `apps/web/components/TelecallerProfileCard.tsx`:

```tsx
import { TEAM_LABEL, statusLabel, type TelecallerMe } from "@/lib/telecaller";

// tel-001: a telecaller's profile as label/value pairs (a <dl>, so assistive tech announces each pair). Read-only; the mobile is
// edited with TelecallerPhoneForm (TL3), everything else by an admin.
export default function TelecallerProfileCard({ me }: { me: TelecallerMe }) {
  const p = me.telecaller_profile;
  const manager = `${p.reporting_manager.full_name}${p.reporting_manager.active ? "" : " (inactive)"}`;
  const rows: [string, string][] = [
    ["Name", me.full_name],
    ["Employee ID", p.employee_id],
    ["Team", TEAM_LABEL[p.team]],
    ["Mobile", me.phone ?? "—"],
    ["Email", me.email],
    ["Reporting manager", manager],
    ["Status", statusLabel(me.active)],
  ];
  return (
    <div className="card" style={{ padding: 16 }}>
      <dl style={{ display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "8px 16px", margin: 0 }}>
        {rows.map(([label, value]) => [
          <dt key={`${label}-t`} className="muted">{label}</dt>,
          <dd key={`${label}-d`} style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>,
        ])}
      </dl>
    </div>
  );
}
```

Create `apps/web/components/TelecallerPhoneForm.tsx`:

```tsx
"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { PROFILE_URL } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const MESSAGE_ID = "telecaller-phone-message";

// tel-001 (TL3): the one field a telecaller edits about themselves. A failed save keeps what was typed and moves focus to the
// server's message; success is announced and the server-rendered card refreshes.
export default function TelecallerPhoneForm({ phone }: { phone: string | null }) {
  const router = useRouter();
  const [value, setValue] = useState(phone ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const focus = useFocusAfterRender();

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const outcome = await sendJson(PROFILE_URL, "PATCH", { phone: value.trim() || null });
    setBusy(false);
    if (outcome.ok) {
      setMessage({ text: "Mobile saved.", error: false });
      router.refresh();
    } else {
      setMessage({ text: outcome.message, error: true });
      focus(MESSAGE_ID);
    }
  }

  return (
    <form className="card form" style={{ padding: 16, marginTop: 16 }} onSubmit={submit} aria-describedby={MESSAGE_ID}>
      <div className="field">
        <label htmlFor="telecaller-phone">Mobile</label>
        <input id="telecaller-phone" name="phone" type="tel" inputMode="tel" maxLength={40} value={value} onChange={(e) => setValue(e.target.value)} disabled={busy} />
      </div>
      <button className="btn small" disabled={busy} aria-label="Save mobile">{busy ? "Saving…" : "Save mobile"}</button>
      <div id={MESSAGE_ID} tabIndex={-1} className={message ? (message.error ? "form-error" : "form-message") : undefined} role="status" aria-live="polite" style={{ marginTop: 8 }}>
        {message?.text}
      </div>
    </form>
  );
}
```

(While busy the button's visible text is "Saving…", but its accessible name stays "Save mobile" so the label does not jump for
screen-reader users.)

Create `apps/web/components/TelecallerTeamTable.tsx`:

```tsx
import Link from "next/link";

import type { Page } from "@/lib/apiErrors";
import { TEAM_LABEL, statusLabel, type TelecallerTeamRow } from "@/lib/telecaller";

const TEAM_PATH = "/telecaller/manager/team";

// tel-001 (AC4): a manager's direct reports. Server-rendered; paging is a link (?offset=) so a page can be shared and needs no client JS.
export default function TelecallerTeamTable({ page }: { page: Page<TelecallerTeamRow> }) {
  const end = page.offset + page.items.length;
  return (
    <>
      <div className="table-wrap" role="region" aria-label="Team" tabIndex={0}>
        <table>
          <caption className="visually-hidden">Telecallers who report to you</caption>
          <thead>
            <tr><th scope="col">Name</th><th scope="col">Employee ID</th><th scope="col">Team</th><th scope="col">Mobile</th><th scope="col">Status</th></tr>
          </thead>
          <tbody>
            {page.items.map((r) => (
              <tr key={r.id}>
                <td>{r.full_name}</td>
                <td>{r.employee_id}</td>
                <td>{TEAM_LABEL[r.team]}</td>
                <td>{r.phone ?? "—"}</td>
                <td><span className="badge">{statusLabel(r.active)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {page.total > page.limit && (
        <nav aria-label="Team pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
          <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{end} of {page.total}</span>
          {page.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={`${TEAM_PATH}?offset=${Math.max(0, page.offset - page.limit)}`}>Previous</Link>}
          {end < page.total && <Link className="btn secondary small" aria-label="Next page" href={`${TEAM_PATH}?offset=${end}`}>Next</Link>}
        </nav>
      )}
    </>
  );
}
```

- [ ] **Step 5: Pages**

Create `apps/web/app/telecaller/dashboard/page.tsx`:

```tsx
import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import TelecallerProfileCard from "@/components/TelecallerProfileCard";
import { serverApi } from "@/lib/api";
import { TELECALLER_NAV, TELECALLER_SIGN_IN } from "@/lib/navigation";
import { teamRoleLabel, type TelecallerMe } from "@/lib/telecaller";

// tel-001 (AC3): the telecaller landing page -- a minimal shell; tel-021 fills it in. The API is the gate: any other role, or a
// telecaller without a profile, gets its 403 message here with a link home.
export default async function TelecallerDashboardPage() {
  let me: TelecallerMe;
  try {
    me = await serverApi<TelecallerMe>("/api/v1/telecaller/me");
  } catch (e) {
    return accessUnavailable(e, TELECALLER_SIGN_IN);
  }
  return (
    <PortalShell nav={TELECALLER_NAV} roleLabel={teamRoleLabel(me.telecaller_profile.team)} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Dashboard</div>
            <h2>Welcome, {me.full_name}</h2>
            <p className="muted">Your leads, calls and follow-ups will appear here.</p>
          </div>
        </div>
        <TelecallerProfileCard me={me} />
      </div>
    </PortalShell>
  );
}
```

Create `apps/web/app/telecaller/profile/page.tsx`:

```tsx
import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import TelecallerPhoneForm from "@/components/TelecallerPhoneForm";
import TelecallerProfileCard from "@/components/TelecallerProfileCard";
import { serverApi } from "@/lib/api";
import { TELECALLER_NAV, TELECALLER_SIGN_IN } from "@/lib/navigation";
import { teamRoleLabel, type TelecallerMe } from "@/lib/telecaller";

// tel-001: the telecaller's own profile; only the mobile is editable here (TL3).
export default async function TelecallerProfilePage() {
  let me: TelecallerMe;
  try {
    me = await serverApi<TelecallerMe>("/api/v1/telecaller/me");
  } catch (e) {
    return accessUnavailable(e, TELECALLER_SIGN_IN);
  }
  return (
    <PortalShell nav={TELECALLER_NAV} roleLabel={teamRoleLabel(me.telecaller_profile.team)} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Profile</div>
            <h2>My profile</h2>
            <p className="muted">You can update your mobile number. Contact your administrator to change anything else.</p>
          </div>
        </div>
        <TelecallerProfileCard me={me} />
        <TelecallerPhoneForm phone={me.phone} />
      </div>
    </PortalShell>
  );
}
```

Create `apps/web/app/telecaller/manager/team/page.tsx`:

```tsx
import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import TelecallerTeamTable from "@/components/TelecallerTeamTable";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { TELECALLER_MANAGER_NAV } from "@/lib/navigation";
import { PAGE_SIZE, pageOffset, type TelecallerTeamRow } from "@/lib/telecaller";
import type { User } from "@/lib/types";

// tel-001 (AC4, T23): exactly the telecallers who report to this manager (the API scopes it). The offset lives in the URL.
export default async function TelecallerManagerTeamPage({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  const offset = pageOffset((await searchParams).offset);
  let user: User, team: Page<TelecallerTeamRow>;
  try {
    [user, team] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Page<TelecallerTeamRow>>(`/api/v1/telecaller/manager/team?limit=${PAGE_SIZE}&offset=${offset}`),
    ]);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={TELECALLER_MANAGER_NAV} roleLabel="Telecaller Manager" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Team</div>
            <h2>Telecallers who report to you</h2>
          </div>
        </div>
        {team.total === 0 ? (
          <p className="empty" role="status">No telecallers report to you yet.</p>
        ) : team.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of your team.</p>
            <Link className="btn secondary small" href="/telecaller/manager/team">Go to the first page</Link>
          </>
        ) : (
          <TelecallerTeamTable page={team} />
        )}
      </div>
    </PortalShell>
  );
}
```

- [ ] **Step 6: Run the tests and type-check**

Run the web command with `CMD="npx vitest run tests/components/TelecallerPhoneForm.test.tsx tests/components/TelecallerTeamTable.test.tsx && npx tsc --noEmit"`.
Expected: tests PASS; `tsc` exits 0.

- [ ] **Step 7: Commit**

```bash
git add apps/web/lib/telecaller.ts apps/web/components/TelecallerProfileCard.tsx apps/web/components/TelecallerPhoneForm.tsx apps/web/components/TelecallerTeamTable.tsx apps/web/app/telecaller/dashboard apps/web/app/telecaller/profile apps/web/app/telecaller/manager/team apps/web/tests/components/TelecallerPhoneForm.test.tsx apps/web/tests/components/TelecallerTeamTable.test.tsx
git commit -m "feat(tel-001): telecaller dashboard, profile with phone edit, manager team"
```

---

### Task 8: Admin Telecallers page

**Files:**
- Create: `apps/web/components/AdminTelecallerPage.tsx`, `AdminTelecallerPanel.tsx`, `AdminTelecallerCreateForm.tsx`, `AdminTelecallerRow.tsx`
- Create: `apps/web/app/admin/telecallers/page.tsx`, `apps/web/app/it/admin/telecallers/page.tsx`, `apps/web/app/overseas/admin/telecallers/page.tsx`
- Modify: `apps/web/app/globals.css:277` (list-before-form on phones)
- Test: `apps/web/tests/components/AdminTelecallerCreateForm.test.tsx`, `AdminTelecallerRow.test.tsx`, `AdminTelecallerPanel.test.tsx`

**Interfaces:**
- Consumes: `@/lib/telecaller` (Task 7); `SearchableSelect`, `sendJson`, `isPage`, `welcomeLinkFeedback`, `toneClass`, `useFocusAfterRender`,
  `announceUsersChanged` (existing).
- Produces: `AdminTelecallerPage({ roles, nav, roleLabel, loginHref })`, `AdminTelecallerPanel({ role })`,
  `AdminTelecallerCreateForm({ role, managersAvailable, onCreated })`, `AdminTelecallerRow({ row, onChanged })`.

- [ ] **Step 1: Write the failing tests**

Create `apps/web/tests/components/AdminTelecallerCreateForm.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminTelecallerCreateForm from "@/components/AdminTelecallerCreateForm";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const managerPage = { items: [{ id: "m1", full_name: "Meena", email: "meena@x.local" }, { id: "m2", full_name: "Meena", email: "meena.k@x.local" }], total: 2, limit: 20, offset: 0 };

function route(post: Response) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) =>
    Promise.resolve(String(url).startsWith("/api/v1/admin/telecaller-managers") ? res(managerPage) : post));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function fill() {
  fireEvent.change(screen.getByLabelText("Full name (required)"), { target: { value: "Ravi" } });
  fireEvent.change(screen.getByLabelText("Email (required)"), { target: { value: "ravi@x.local" } });
  fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: "T-9" } });
  const combo = screen.getByRole("combobox", { name: "Reporting manager (required)" });
  fireEvent.focus(combo);
  fireEvent.change(combo, { target: { value: "meena.k" } });
  fireEvent.click(await screen.findByRole("option", { name: "Meena — meena.k@x.local" }));
}

describe("AdminTelecallerCreateForm (tel-001 AC1, AC2)", () => {
  it("lets a super admin choose the team", () => {
    route(res({}));
    render(<AdminTelecallerCreateForm role="super_admin" managersAvailable onCreated={() => {}} />);
    const select = screen.getByLabelText("Team (required)");
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent)).toEqual(["IT", "Overseas"]);
  });

  it("shows a division admin's only team as fixed text", () => {
    route(res({}));
    render(<AdminTelecallerCreateForm role="overseas_admin" managersAvailable onCreated={() => {}} />);
    expect(screen.queryByLabelText("Team (required)")).toBeNull();
    expect(screen.getByText("Overseas")).toBeInTheDocument();
  });

  it("explains and disables submit when there is no active manager", () => {
    route(res({}));
    render(<AdminTelecallerCreateForm role="super_admin" managersAvailable={false} onCreated={() => {}} />);
    expect(screen.getByText("No active telecaller manager — a Super Admin must create one first.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create telecaller" })).toBeDisabled();
  });

  it("POSTs role + nested profile and reports the welcome link", async () => {
    const mock = route(res({ id: "u1", welcome_link_status: "sent" }, 201));
    const onCreated = vi.fn();
    render(<AdminTelecallerCreateForm role="it_admin" managersAvailable onCreated={onCreated} />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Create telecaller" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("T-9"));
    const post = mock.mock.calls.find(([url]) => url === "/api/v1/admin/users")!;
    expect(JSON.parse(String(post[1]!.body))).toEqual({
      role: "telecaller", full_name: "Ravi", email: "ravi@x.local", phone: null,
      telecaller_profile: { team: "it", employee_id: "T-9", reporting_manager_user_id: "m2" },
    });
  });

  it("keeps the typed values and shows the server's message on 409", async () => {
    route(res({ detail: "Employee ID already exists" }, 409));
    render(<AdminTelecallerCreateForm role="it_admin" managersAvailable onCreated={() => {}} />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Create telecaller" }));
    expect(await screen.findByText("Employee ID already exists")).toBeInTheDocument();
    expect(screen.getByLabelText("Employee ID (required)")).toHaveValue("T-9");
  });
});
```

Before relying on the success assertion, open `apps/web/tests/components/AdminBdmCreateForm.test.tsx` and copy the exact 201 body it
uses for `welcomeLinkFeedback` (the key names `lib/welcomeLink` reads); use that body in place of `{ id: "u1", welcome_link_status: "sent" }`
if they differ.

Create `apps/web/tests/components/AdminTelecallerRow.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminTelecallerRow from "@/components/AdminTelecallerRow";
import type { TelecallerAdminRow } from "@/lib/telecaller";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row: TelecallerAdminRow = {
  id: "t1", full_name: "Ravi", email: "ravi@x.local", phone: null, active: true, team: "overseas", employee_id: "T-1",
  reporting_manager: { id: "m1", full_name: "Meena", active: false }, manager_active: false,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function table(ui: React.ReactNode) {
  return render(<table><tbody>{ui}</tbody></table>);
}

describe("AdminTelecallerRow (tel-001 §6.3)", () => {
  it("shows the team and flags an inactive manager", () => {
    table(<AdminTelecallerRow row={row} onChanged={() => {}} />);
    expect(screen.getByText("Overseas")).toBeInTheDocument();
    expect(screen.getByText("No active manager")).toBeInTheDocument();
  });

  it("edits Employee ID with the team read-only and keeps the current manager", async () => {
    const mock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", mock);
    const onChanged = vi.fn();
    table(<AdminTelecallerRow row={row} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Ravi" }));
    expect(screen.getByText("Overseas (cannot be changed here)")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: "T-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Saved Ravi."));
    expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({
      full_name: "Ravi", phone: null, telecaller_profile: { employee_id: "T-2", reporting_manager_user_id: "m1" },
    });
  });

  it("deactivates only after an inline confirm", async () => {
    const mock = vi.fn().mockResolvedValue(res({ ok: true }));
    vi.stubGlobal("fetch", mock);
    table(<AdminTelecallerRow row={row} onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Ravi" }));
    expect(mock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await waitFor(() => expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({ active: false }));
  });
});
```

Create `apps/web/tests/components/AdminTelecallerPanel.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminTelecallerPanel from "@/components/AdminTelecallerPanel";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/admin/telecallers",
  useSearchParams: () => new URLSearchParams(),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const empty = { items: [], total: 0, limit: 50, offset: 0 };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminTelecallerPanel (tel-001 §6.3)", () => {
  it("shows the empty state", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(res(String(url).includes("telecaller-managers") ? { ...empty, total: 1 } : empty))));
    render(<AdminTelecallerPanel role="super_admin" />);
    expect(await screen.findByText("No telecallers yet. Use the Create telecaller form to add the first one.")).toBeInTheDocument();
  });

  it("shows an error with Retry when the list fails", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(String(url).includes("telecaller-managers") ? res({ ...empty, total: 1 }) : res({ detail: "x" }, 500))));
    render(<AdminTelecallerPanel role="super_admin" />);
    expect(await screen.findByText("Unable to load telecallers.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("lists rows from the server", async () => {
    const page = { items: [{ id: "t1", full_name: "Ravi", email: "r@x", phone: null, active: true, team: "it", employee_id: "T-1", reporting_manager: { id: "m1", full_name: "Meena", active: true }, manager_active: true }], total: 1, limit: 50, offset: 0 };
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(res(String(url).includes("telecaller-managers") ? { ...empty, total: 1 } : page))));
    render(<AdminTelecallerPanel role="it_admin" />);
    expect(await screen.findByText("Ravi")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Telecallers" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run the web command with `CMD="npx vitest run tests/components/AdminTelecallerCreateForm.test.tsx tests/components/AdminTelecallerRow.test.tsx tests/components/AdminTelecallerPanel.test.tsx"`.
Expected: FAIL — modules not found.

- [ ] **Step 3: Create form**

Create `apps/web/components/AdminTelecallerCreateForm.tsx`:

```tsx
"use client";
import { useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { TEAM_LABEL, USERS_URL, creatableTeams, formOptional, formText, managerSearch } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { announceUsersChanged } from "@/lib/usersChanged";
import { toneClass, welcomeLinkFeedback, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "telecaller-create-feedback";

// tel-001 (AC1, AC2; spec §6.3): creates a telecaller through POST /admin/users with the nested profile. No password field: the
// telecaller sets their own from the emailed link. A failed save keeps everything typed. The team list is display-only; the API
// decides (services/telecaller.CREATOR_TEAMS). `managersAvailable`: null while the panel checks, false when none exists.
export default function AdminTelecallerCreateForm({ role, managersAvailable, onCreated }: { role: string; managersAvailable: boolean | null; onCreated: (employeeId: string) => void }) {
  const teams = creatableTeams(role);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const focus = useFocusAfterRender();
  const ready = managersAvailable === true;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const employeeId = formText(form, "employee_id");
    setBusy(true);
    const outcome = await sendJson(USERS_URL, "POST", {
      role: "telecaller", full_name: formText(form, "full_name"), email: formText(form, "email"), phone: formOptional(form, "phone"),
      telecaller_profile: { team: formText(form, "team"), employee_id: employeeId, reporting_manager_user_id: formText(form, "manager") },
    });
    setBusy(false);
    if (outcome.ok) {
      setFeedback(welcomeLinkFeedback("Telecaller created.", outcome.data));
      formEl.reset();
      announceUsersChanged();
      onCreated(employeeId);
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  return (
    <form className="action-card form" onSubmit={submit} aria-describedby={FEEDBACK_ID}>
      <h3>Create telecaller</h3>
      <div className="field"><label htmlFor="tel-name">Full name (required)</label><input id="tel-name" name="full_name" required maxLength={160} disabled={busy} /></div>
      <div className="field"><label htmlFor="tel-email">Email (required)</label><input id="tel-email" name="email" type="email" required maxLength={255} autoComplete="off" disabled={busy} /></div>
      <div className="field"><label htmlFor="tel-phone">Mobile</label><input id="tel-phone" name="phone" type="tel" inputMode="tel" maxLength={40} disabled={busy} /></div>
      {teams.length === 1 ? (
        <div className="field">
          <span className="muted">Team</span> <strong>{TEAM_LABEL[teams[0]]}</strong>
          <input type="hidden" name="team" value={teams[0]} />
        </div>
      ) : (
        <div className="field">
          <label htmlFor="tel-team">Team (required)</label>
          <select id="tel-team" name="team" required disabled={busy}>
            {teams.map((t) => <option key={t} value={t}>{TEAM_LABEL[t]}</option>)}
          </select>
        </div>
      )}
      <div className="field"><label htmlFor="tel-employee-id">Employee ID (required)</label><input id="tel-employee-id" name="employee_id" required maxLength={40} disabled={busy} /></div>
      <SearchableSelect id="tel-manager" name="manager" label="Reporting manager (required)" noun="manager" required search={managerSearch} disabled={busy || !ready} />
      {managersAvailable === false && <p className="muted" style={{ fontSize: 13 }}>No active telecaller manager — a Super Admin must create one first.</p>}
      <button className="btn" disabled={busy || !ready}>{busy ? "Creating…" : "Create telecaller"}</button>
      <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
        {feedback?.text}
      </div>
    </form>
  );
}
```

- [ ] **Step 4: Row**

Create `apps/web/components/AdminTelecallerRow.tsx`:

```tsx
"use client";
import { useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { TEAM_LABEL, USERS_URL, formOptional, formText, managerSearch, statusLabel, type TelecallerAdminRow } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// tel-001 (spec §6.3): one telecaller -- view, inline edit (team read-only, TL7; Esc cancels), and activate/deactivate with an inline
// confirm. The list refreshes only after the server says yes. Focus returns to the row's controls on success and moves to the
// message on error. The manager picker starts on the current manager, so an unrelated edit never silently reassigns the reporting line.
export default function AdminTelecallerRow({ row, onChanged }: { row: TelecallerAdminRow; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (name: string) => `tel-${name}-${row.id}`;
  const currentManager = { id: row.reporting_manager.id, label: `${row.reporting_manager.full_name}${row.manager_active ? "" : " (inactive)"}` };

  function close() {
    setEditing(false);
    setError(null);
    focus(id("edit"));
  }

  function fail(message: string, where: string) {
    setError(message);
    focus(where);
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    const outcome = await sendJson(`${USERS_URL}/${row.id}`, "PATCH", {
      full_name: formText(form, "full_name"), phone: formOptional(form, "phone"),
      telecaller_profile: { employee_id: formText(form, "employee_id"), reporting_manager_user_id: formText(form, "manager") },
    });
    setBusy(false);
    if (!outcome.ok) return fail(outcome.message, id("error"));
    close();
    onChanged(`Saved ${row.full_name}.`);
  }

  async function setActive(active: boolean) {
    setBusy(true);
    const outcome = await sendJson(`${USERS_URL}/${row.id}`, "PATCH", { active });
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) return fail(outcome.message, id("status-error"));
    focus(active ? id("deactivate") : id("reactivate"), id("edit"));
    onChanged(`${active ? "Reactivated" : "Deactivated"} ${row.full_name}.`);
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={6}>
          <form className="form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") close(); }} aria-describedby={id("error")}>
            <div className="field"><label htmlFor={id("name")}>Full name (required)</label><input id={id("name")} name="full_name" defaultValue={row.full_name} required maxLength={160} autoFocus disabled={busy} /></div>
            <div className="field"><label htmlFor={id("phone")}>Mobile</label><input id={id("phone")} name="phone" type="tel" inputMode="tel" defaultValue={row.phone ?? ""} maxLength={40} disabled={busy} /></div>
            <div className="field"><span className="muted">Team</span> <strong>{TEAM_LABEL[row.team]} (cannot be changed here)</strong></div>
            <div className="field"><label htmlFor={id("emp")}>Employee ID (required)</label><input id={id("emp")} name="employee_id" defaultValue={row.employee_id} required maxLength={40} disabled={busy} /></div>
            <SearchableSelect id={id("manager")} name="manager" label="Reporting manager (required)" noun="manager" required search={managerSearch} initial={currentManager} disabled={busy} />
            <div id={id("error")} tabIndex={-1} className={error ? "form-error" : undefined} role="alert">{error}</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
              <button type="button" className="btn secondary small" onClick={close} disabled={busy}>Cancel</button>
            </div>
          </form>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td>{row.full_name}<br /><span className="muted" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{row.email}</span></td>
      <td>{row.employee_id}</td>
      <td>{TEAM_LABEL[row.team]}</td>
      <td>{row.reporting_manager.full_name}{!row.manager_active && <> <span className="badge">No active manager</span></>}</td>
      <td><span className="badge">{statusLabel(row.active)}</span></td>
      <td>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button id={id("edit")} type="button" className="btn secondary small" aria-label={`Edit ${row.full_name}`} onClick={() => setEditing(true)} disabled={busy}>Edit</button>
          {row.active && !confirming && <button id={id("deactivate")} type="button" className="btn secondary small" aria-label={`Deactivate ${row.full_name}`} onClick={() => { setConfirming(true); focus(id("confirm")); }} disabled={busy}>Deactivate</button>}
          {!row.active && <button id={id("reactivate")} type="button" className="btn secondary small" aria-label={`Reactivate ${row.full_name}`} onClick={() => setActive(true)} disabled={busy}>Reactivate</button>}
        </div>
        {confirming && (
          <div role="group" aria-label={`Confirm deactivating ${row.full_name}`} style={{ marginTop: 6 }}>
            <p className="muted" style={{ fontSize: 13 }}>Their reporting line and data stay; they can no longer sign in.</p>
            <button id={id("confirm")} type="button" className="btn small" onClick={() => setActive(false)} disabled={busy}>Confirm deactivate</button>{" "}
            <button type="button" className="btn secondary small" onClick={() => { setConfirming(false); focus(id("deactivate")); }} disabled={busy}>Keep active</button>
          </div>
        )}
        {error && <p id={id("status-error")} tabIndex={-1} className="form-error" role="alert">{error}</p>}
      </td>
    </tr>
  );
}
```

- [ ] **Step 5: Panel**

Create `apps/web/components/AdminTelecallerPanel.tsx`:

```tsx
"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import AdminTelecallerCreateForm from "@/components/AdminTelecallerCreateForm";
import AdminTelecallerRow from "@/components/AdminTelecallerRow";
import { isPage, type Page } from "@/lib/apiErrors";
import { MANAGERS_URL, PAGE_SIZE, TELECALLERS_URL, type TelecallerAdminRow } from "@/lib/telecaller";

// tel-001 (spec §6.3): the admin's telecaller list -- loading / error+Retry / empty / pager, the AdminBdmPanel pattern. The API scopes
// rows to the teams this admin manages (T21); nothing here filters for security. Page and search live in the URL (?offset=&q=), so
// refresh keeps the place and Back returns to the previous page; a newly created telecaller is shown by filtering to its Employee ID.
function urlOffset(raw: string | null): number {
  const n = Number.parseInt(raw ?? "", 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

async function fetchPage<T>(url: string): Promise<Page<T>> {
  const response = await fetch(url);
  const body = await response.json().catch(() => null);
  if (!response.ok || !isPage<T>(body)) throw new Error("not a page");
  return body;
}

export default function AdminTelecallerPanel({ role }: { role: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const fromUrl = { offset: urlOffset(params.get("offset")), query: (params.get("q") ?? "").trim() };
  const [data, setData] = useState<Page<TelecallerAdminRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [offset, setOffset] = useState(fromUrl.offset);
  const [query, setQuery] = useState(fromUrl.query);
  const [draft, setDraft] = useState(fromUrl.query);
  const [version, setVersion] = useState(0);
  const [managersAvailable, setManagersAvailable] = useState<boolean | null>(null);
  const [managersFailed, setManagersFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setOffset(fromUrl.offset);
    setQuery(fromUrl.query);
    setDraft(fromUrl.query);
  }, [fromUrl.offset, fromUrl.query]);

  function go(nextOffset: number, nextQuery: string) {
    setOffset(nextOffset);
    setQuery(nextQuery);
    const next = new URLSearchParams();
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    if (nextQuery) next.set("q", nextQuery);
    router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  }

  useEffect(() => {
    setLoadFailed(false);
    const request = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (query) request.set("q", query);
    fetchPage<TelecallerAdminRow>(`${TELECALLERS_URL}?${request}`).then(setData).catch(() => setLoadFailed(true));
  }, [offset, query, version]);

  // Only "is there any active manager?" -- the picker itself searches the server. A failed check is not "no managers".
  const checkManagers = useCallback(() => {
    setManagersFailed(false);
    setManagersAvailable(null);
    fetchPage(`${MANAGERS_URL}?limit=1`)
      .then((page) => setManagersAvailable(page.total > 0))
      .catch(() => setManagersFailed(true));
  }, []);

  useEffect(() => {
    checkManagers();
  }, [checkManagers]);

  const reload = () => setVersion((v) => v + 1);
  const search = (text: string) => {
    setDraft(text);
    go(0, text.trim());
  };

  return (
    <>
      {managersFailed && (
        <div className="action-card">
          <p className="form-error" role="alert">Unable to load telecaller managers.</p>
          <button type="button" className="btn secondary small" onClick={checkManagers}>Retry loading managers</button>
        </div>
      )}
      <AdminTelecallerCreateForm role={role} managersAvailable={managersAvailable} onCreated={(employeeId) => { search(employeeId); reload(); }} />
      <div className="action-card wide telecaller-list" aria-busy={data === null && !loadFailed}>
        <h3>Telecallers</h3>
        <form role="search" onSubmit={(event) => { event.preventDefault(); search(draft); }} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <input type="search" aria-label="Search telecallers" placeholder="Name, email or Employee ID" value={draft} maxLength={200} onChange={(event) => setDraft(event.target.value)} style={{ flex: "1 1 220px" }} />
          <button type="submit" className="btn secondary small">Search</button>
          {query && <button type="button" className="btn secondary small" onClick={() => search("")}>Clear search</button>}
        </form>
        <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8 } : undefined}>{notice}</div>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">Unable to load telecallers.</p>
            <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted" role="status">Loading telecallers…</p>
        ) : data.total === 0 ? (
          <p className="empty" role="status">{query ? `No telecallers match “${query}”.` : "No telecallers yet. Use the Create telecaller form to add the first one."}</p>
        ) : data.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of the list.</p>
            <button type="button" className="btn secondary small" onClick={() => go(0, query)}>Go to the first page</button>
          </>
        ) : (
          <>
            <div className="table-wrap" role="region" aria-label="Telecallers" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Name</th><th scope="col">Employee ID</th><th scope="col">Team</th>
                    <th scope="col">Manager</th><th scope="col">Status</th><th scope="col"><span className="visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r) => (
                    <AdminTelecallerRow key={r.id} row={r} onChanged={(text) => { setNotice(text); reload(); }} />
                  ))}
                </tbody>
              </table>
            </div>
            {data.total > PAGE_SIZE && (
              <nav aria-label="Telecaller pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
                <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0} onClick={() => go(Math.max(0, offset - PAGE_SIZE), query)}>Previous</button>
                <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => go(offset + PAGE_SIZE, query)}>Next</button>
              </nav>
            )}
          </>
        )}
      </div>
    </>
  );
}
```

In `apps/web/app/globals.css`, change line 277 to put the list first on phones for both admin pages:

```css
@media(max-width:980px){.action-grid > .bdm-list,.action-grid > .telecaller-list{order:-1}}
```

- [ ] **Step 6: Page wrapper and mounts**

Create `apps/web/components/AdminTelecallerPage.tsx`:

```tsx
import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import AdminTelecallerPanel from "@/components/AdminTelecallerPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import type { User } from "@/lib/types";

// tel-001: the one body behind /admin/telecallers, /it/admin/telecallers and /overseas/admin/telecallers (a static route wins over
// [module]/[section]). The role check only spares other roles a screen that can only fail; the API enforces who manages which team.
export default async function AdminTelecallerPage({ roles, nav, roleLabel, loginHref }: { roles: string[]; nav: NavItem[]; roleLabel: string; loginHref: string }) {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, loginHref);
  }
  if (!roles.includes(user.role)) return accessDenied(user, `${roleLabel} role required`);
  const superAdmin = user.role === "super_admin";
  return (
    <PortalShell nav={superAdmin ? SUPER_ADMIN_NAV : nav} roleLabel={superAdmin ? "Super Administrator" : roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>Telecallers</h2>
            <p className="muted">Create telecallers, set their reporting manager and keep their profiles current. Each new telecaller gets an emailed set-password link. Telecaller Managers are created from Users.</p>
          </div>
        </div>
      </div>
      <div className="portal-content action-center">
        <div className="action-grid">
          <Suspense fallback={<p className="muted" role="status">Loading telecallers…</p>}>
            <AdminTelecallerPanel role={user.role} />
          </Suspense>
        </div>
      </div>
    </PortalShell>
  );
}
```

Create `apps/web/app/admin/telecallers/page.tsx`:

```tsx
import AdminTelecallerPage from "@/components/AdminTelecallerPage";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

// tel-001: the Super Admin's Telecallers page (both teams; managers are created from Users).
export default function SuperAdminTelecallersPage() {
  return <AdminTelecallerPage roles={["super_admin"]} nav={SUPER_ADMIN_NAV} roleLabel="Super Administrator" loginHref="/admin/login" />;
}
```

Create `apps/web/app/it/admin/telecallers/page.tsx`:

```tsx
import AdminTelecallerPage from "@/components/AdminTelecallerPage";
import { PORTAL_NAV } from "@/lib/navigation";

// tel-001 (AC2): IT admins manage IT telecallers.
export default function ItAdminTelecallersPage() {
  return <AdminTelecallerPage roles={["it_admin", "super_admin"]} nav={PORTAL_NAV["it/admin"]} roleLabel="IT Administrator" loginHref="/it/login" />;
}
```

Create `apps/web/app/overseas/admin/telecallers/page.tsx`:

```tsx
import AdminTelecallerPage from "@/components/AdminTelecallerPage";
import { PORTAL_NAV } from "@/lib/navigation";

// tel-001: Overseas admins manage Overseas telecallers.
export default function OverseasAdminTelecallersPage() {
  return <AdminTelecallerPage roles={["overseas_admin", "super_admin"]} nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" loginHref="/overseas/login" />;
}
```

- [ ] **Step 7: Run tests, type-check and lint**

Run the web command with
`CMD="npx vitest run tests/components/AdminTelecallerCreateForm.test.tsx tests/components/AdminTelecallerRow.test.tsx tests/components/AdminTelecallerPanel.test.tsx tests/components/AdminBdmPanel.test.tsx && npx tsc --noEmit && npx eslint components/AdminTelecaller*.tsx components/Telecaller*.tsx lib/telecaller.ts app/telecaller app/admin/telecallers app/it/admin/telecallers app/overseas/admin/telecallers middleware.ts lib/navigation.ts"`.
Expected: tests PASS; `tsc` and `eslint` exit 0.

- [ ] **Step 8: Commit**

```bash
git add apps/web/components/AdminTelecaller*.tsx apps/web/app/admin/telecallers apps/web/app/it/admin/telecallers apps/web/app/overseas/admin/telecallers apps/web/app/globals.css apps/web/tests/components/AdminTelecaller*.test.tsx
git commit -m "feat(tel-001): admin Telecallers page"
```

---

### Task 9: End-to-end journey

**Files:**
- Test: `apps/web/tests/e2e/tel-001-telecaller-roles.spec.ts`

**Interfaces:**
- Consumes: everything above; `tests/e2e/helpers/welcome` (`E2E_PASSWORD`, `activateWithToken`); the API's `development_welcome_token`
  in create responses (dev only).

- [ ] **Step 1: Write the spec**

Create `apps/web/tests/e2e/tel-001-telecaller-roles.spec.ts`:

```ts
import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-001 (AC1, AC3, AC4, AC5): a Super Admin creates a telecaller manager and an IT telecaller; each activates from its link and
// lands on its own page; the telecaller edits its mobile; the manager sees it in their team. Throwaway accounts via the real admin API.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await expect(page.getByText("For Super Admins, BDM Managers and Telecaller Managers.")).toBeVisible();
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

test("manager and IT telecaller: create, activate, land, edit mobile, team", async ({ page }) => {
  const stamp = Date.now();
  await superAdmin(page);
  const managerResponse = await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E TL Manager ${stamp}`, email: `tel001-m-${stamp}@example.local` },
  });
  expect(managerResponse.status()).toBe(201);
  const manager = await managerResponse.json();
  const callerResponse = await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Telecaller ${stamp}`, email: `tel001-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `TEL-${stamp}`, reporting_manager_user_id: manager.id },
    },
  });
  expect(callerResponse.status()).toBe(201);
  const caller = await callerResponse.json();
  expect(caller.division).toBe("it");
  await page.request.post("/api/v1/auth/logout");

  await activateWithToken(page.request, caller.development_welcome_token);
  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  await expect(page.getByText(`TEL-${stamp}`)).toBeVisible();
  await page.goto("/telecaller/profile");
  await page.getByLabel("Mobile").fill("+91 98765 00000");
  await page.getByRole("button", { name: "Save mobile" }).click();
  await expect(page.getByText("Mobile saved.")).toBeVisible();
  await expect(page.locator("dd", { hasText: "+91 98765 00000" })).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  // The manager's welcome link opens the admin portal's own reset page (spec §5.6).
  await page.goto(`/admin/reset-password?token=${manager.development_welcome_token}`);
  await page.fill("#reset-new-password", E2E_PASSWORD);
  await page.getByRole("button", { name: "Reset password" }).click();
  await page.waitForURL("**/admin/login");
  await signIn(page, "admin", manager.email, "/telecaller/manager/team");
  await expect(page.getByRole("region", { name: "Team" }).getByText(`E2E Telecaller ${stamp}`)).toBeVisible();
});

test("signed-out /telecaller visits go to the right sign-in (AC5)", async ({ page }) => {
  await page.goto("/telecaller/profile");
  await page.waitForURL("**/telecaller/sign-in?next=%2Ftelecaller%2Fprofile");
  await expect(page.getByRole("link", { name: "IT team" })).toHaveAttribute("href", "/it/login?next=%2Ftelecaller%2Fprofile");
  await page.goto("/telecaller/manager/team");
  await page.waitForURL("**/admin/login?next=%2Ftelecaller%2Fmanager%2Fteam");
});

test("a telecaller at the wrong portal gets the correct-portal message (AC3)", async ({ page }) => {
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E TL M2 ${stamp}`, email: `tel001-m2-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller", full_name: `E2E TL O ${stamp}`, email: `tel001-o-${stamp}@example.local`,
      telecaller_profile: { team: "overseas", employee_id: `TELO-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, caller.development_welcome_token);
  await page.goto("/it/login");
  await page.fill("#login-email", caller.email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await expect(page.getByText(/sign in at \/overseas\/login/)).toBeVisible();
});

test("admin Telecallers page works at phone width without horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await superAdmin(page);
  await page.goto("/admin/telecallers");
  await expect(page.getByRole("heading", { name: "Create telecaller" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const listTop = (await page.getByRole("heading", { name: "Telecallers", exact: true, level: 3 }).boundingBox())!.y;
  const formTop = (await page.getByRole("heading", { name: "Create telecaller" }).boundingBox())!.y;
  expect(listTop).toBeLessThan(formTop);
});
```

- [ ] **Step 2: Ask the user to bring the stack up with this branch**

Per the owner's rule, the user runs `docker compose` themselves. Ask them to (re)build and start the `tel-001` worktree stack and
report the web port; then seed if empty: `docker compose -p edusphere-tel001 -f docker-compose.yml exec -T api python -m app.seed`.

- [ ] **Step 3: Run the e2e specs**

Run the web command with `-e E2E_BASE_URL=http://host.docker.internal:<web port>` added before `web-test`, and
`CMD="npx playwright test tests/e2e/tel-001-telecaller-roles.spec.ts tests/e2e/bdm-001-bdm-profile.spec.ts tests/e2e/adm-001-admin-crud.spec.ts tests/e2e/auth-001-login.spec.ts tests/e2e/auth-002-rbac-ui.spec.ts tests/e2e/enh-003-first-time-provisioning.spec.ts"`.
Expected: all PASS. Note: `bdm-001-bdm-profile.spec.ts` asserts the admin heading only (unchanged), so it still passes.

- [ ] **Step 4: Commit**

```bash
git add apps/web/tests/e2e/tel-001-telecaller-roles.spec.ts
git commit -m "test(tel-001): end-to-end telecaller and manager journey"
```

---

### Task 10: Decision record and documentation

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append after `DEC-SCOPE-072`)
- Modify: `docs/architecture/RBAC_MATRIX.md`, `docs/architecture/API_CONTRACT.md`, `docs/ux/ROLE_NAVIGATION.md`, `docs/ux/SCREEN_CATALOG.md`,
  `docs/delivery/TELECALLER_CRM_BACKLOG.md`

**Interfaces:** none (docs).

- [ ] **Step 1: Register DEC-SCOPE-073**

Append to `docs/decisions/PRODUCT_DECISION_REGISTER.md`, following the `DEC-SCOPE-072` entry's heading/field layout:

```markdown
### DEC-SCOPE-073 — Telecaller CRM scope (T1–T29) and telecaller roles (`tel-001`)

**Evidence:** `EVID-019` (`functionalities/edusphere_markdown/Telecaller Functionalities.md`, `DERIVED_BLUEPRINT`); owner answers in-session
2026-10-05.
**Status:** `EXPLICIT_APPROVAL` (owner, in-session, 2026-10-05) for T1–T29 and TL1–TL7.

**Part A — Telecaller CRM (T1–T29).** Copied verbatim from `docs/delivery/TELECALLER_CRM_BACKLOG.md` §3.1. They lift
`PRD_OPEN_ITEMS.md` item 61 / `CONFLICT_MATRIX.md` for `EVID-019`. T29 supersedes `DEC-SCOPE-072` L2/L7 for leads in the telecaller
pipeline; that supersession takes effect with `tel-018`.

**Part B — tel-001 (TL1–TL7).** Design: `docs/superpowers/specs/2026-10-05-tel-001-telecaller-roles-design.md` §3.
- TL1 Signed-out `/telecaller/*` → public `/telecaller/sign-in` chooser (IT / Overseas); `/telecaller/manager/*` → `/admin/login`.
- TL2 Active status is `users.active` only.
- TL3 A telecaller edits only their phone (`PATCH /telecaller/profile`).
- TL4 Provisioning extends `POST/PATCH /admin/users` (`telecaller_profile`); `/admin/telecallers` is read-only.
- TL5 A telecaller manager has no profile row.
- TL6 Required profile fields: team, Employee ID, reporting manager.
- TL7 Team is fixed in tel-001 (tel-025 moves teams).

**Implementation:** migration `0075_telecaller_profiles`; roles `telecaller` (division = team) and `telecaller_manager` (`global`).
```

Then paste the full T1–T29 table from the backlog §3.1 under Part A.

- [ ] **Step 2: Architecture and UX docs**

- `RBAC_MATRIX.md`: add rows for `telecaller` (`telecaller:self`; `/telecaller/me`, `/telecaller/profile` phone only) and
  `telecaller_manager` (`telecaller:team`; `/telecaller/manager/team` direct reports), and note that `/admin/telecallers` and
  `/admin/telecaller-managers` are for `super_admin` (both teams), `it_admin` (IT), `overseas_admin` (Overseas); only `super_admin`
  creates `telecaller_manager`. Follow the BDM rows' format.
- `API_CONTRACT.md`: the five routes from spec §5.7 (request/response shapes and errors), the `telecaller_profile` branch of
  `POST/PATCH /admin/users`, and `login_portal` now `"admin"` for `telecaller_manager` too.
- `ROLE_NAVIGATION.md`: add a "Telecaller *(net-new, 2026-10-05, `DEC-SCOPE-073`, `tel-001`)*" section (signs in at `/it/login` or
  `/overseas/login` by team; lands on `/telecaller/dashboard`; sidebar Dashboard · Profile) and a "Telecaller Manager" section (signs in
  at `/admin/login`; lands on `/telecaller/manager/team`; sidebar Team), plus the Telecallers entry in the three admin sidebars.
- `SCREEN_CATALOG.md`: `/telecaller/sign-in`, `/telecaller/dashboard`, `/telecaller/profile`, `/telecaller/manager/team`,
  `/admin/telecallers` (+ `/it/admin/telecallers`, `/overseas/admin/telecallers`), each with states (loading/empty/error) as in spec §6.
- `TELECALLER_CRM_BACKLOG.md`: in tel-001, change the API line to "`GET /telecaller/me`, `PATCH /telecaller/profile` (phone only),
  `GET /telecaller/manager/team`, `GET /admin/telecallers`, `GET /admin/telecaller-managers`; create and edit via `POST/PATCH /admin/users`
  (`DEC-SCOPE-073` TL4)", and set the header line's "To be registered" to "Registered as `DEC-SCOPE-073`".

- [ ] **Step 3: Commit**

```bash
git add docs/decisions/PRODUCT_DECISION_REGISTER.md docs/architecture/RBAC_MATRIX.md docs/architecture/API_CONTRACT.md docs/ux/ROLE_NAVIGATION.md docs/ux/SCREEN_CATALOG.md docs/delivery/TELECALLER_CRM_BACKLOG.md
git commit -m "docs(tel-001): DEC-SCOPE-073 and role, API, navigation and screen docs"
```

---

### Task 11: Lite regression, build and completion gates

**Files:** none new.

- [ ] **Step 1: Re-check main**

Run: `git fetch origin main && git log --oneline feature/tel-001..origin/main`.
Expected: no new migration `0075_*` or `DEC-SCOPE-073` on main. If there is one, stop and tell the user (renumber per bdm precedent).

- [ ] **Step 2: Backend lite set**

Run the API command with
`TESTS="tests/test_tel_001_migration.py tests/test_tel_001_service.py tests/test_tel_001_provisioning.py tests/test_tel_001_update.py tests/test_tel_001_reads.py tests/test_tel_001_login.py tests/test_bdm_001_migration.py tests/test_bdm_001_profiles.py tests/test_bdm_001_reads.py tests/test_bdm_001_service.py tests/test_bdm_001_reset_portal.py tests/test_bdm_001_admin_portal_links.py tests/test_bdm_001_portal_message.py tests/test_bdm_017_migration.py tests/test_adm_001_admin_crud.py tests/test_adm_012_roles_permissions.py tests/test_enh_003_first_time_provisioning.py tests/test_enh_006_change_password.py tests/test_rbac.py"`.
Expected: all PASS. (The full backend suite is the owner's, every 4–5 stories.)

- [ ] **Step 3: Web unit tests, types, lint, build**

Run the web command with `CMD="npx vitest run && npx tsc --noEmit && npx eslint . && npx next build"`.
Expected: all exit 0.

- [ ] **Step 4: Record evidence**

Report to the user: the exact pass/fail counts from Steps 2–3 and Task 9 Step 3, the commit list, and any test that was changed
because a role list grew (`test_bdm_017_migration.py`, `adm-001-admin-crud.spec.ts`, `WorkflowPanel.create-user.test.tsx` if touched).
Give the push command (`git push -u origin feature/tel-001`) for the user to run; do not push.
