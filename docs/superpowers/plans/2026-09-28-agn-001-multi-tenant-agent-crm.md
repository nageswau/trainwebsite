# AGN-001 Multi-Tenant Agent CRM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every agent company a separate tenant (agent organisation) with up to three Master logins, move the agent approval gate and all agent data scoping to the organisation, and let Overseas Admin approve / reject / suspend / reinstate organisations.

**Architecture:** Two new tables (`agent_orgs`, `agent_org_members`, migration `0045`) and one functions-only service module (`app/services/agent_orgs.py`). Business tables are untouched: agent rows keep `agent_id` = acting user, and every agent query filters `agent_id IN (member user ids of the caller's organisation)`. The gate (`core/rbac.agent_is_approved`) reads the membership + organisation that `get_current_user` eager-loads on each request. Master invites reuse the `DEC-SCOPE-019` welcome-link functions. Frontend reuses the existing panel patterns (`SchoolTeamPanel`, `AgentApprovalPanel`, `WorkflowPanel` flags).

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, PostgreSQL 16; Next.js (App Router), React, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-28-agn-001-multi-tenant-agent-crm-design.md` (read it with this plan). Decision: `DEC-SCOPE-036` (D1–D13) + spec E1–E12.

## Global Constraints

- Scope is AGN-001 only. No Staff roles, no change to `UserOut`, JWT/cookies, non-agent scoping, ADM-001's `PATCH /admin/users`, the frozen `app/agents/` package, or Zoho/CRM webhook code.
- No new dependency (Python or npm).
- Existing tests and e2e specs are **never edited**. If one fails, stop and report it — it is a regression signal, not a fixture to fix.
- No existing table is altered; migration `0046_agent_orgs` only creates and fills the two new tables; `downgrade()` drops only them.
- Organisation statuses: `pending`, `active`, `rejected`, `suspended`. Member status: `active`, `deactivated`. Member role: `master`. Master limit: `3`.
- Prefix (D5): Latin letters of the name, first three, uppercased, padded with `X` to three; none → `AGT`; collision → lowest free of `ABC`, `ABC2`, `ABC3`… Code: `f"{prefix}-M{seq:03d}"`.
- Messages (verbatim):
  - gate: "Agent registration is pending approval" (pending/rejected/no org) · "Your agency's account is suspended" · "Your Master account is deactivated"
  - transitions: `f"Cannot {action} an organisation that is {status}"` · "Agent organisation not found"
  - team: "This agency already has 3 active Masters" · "Email already exists" · "Master not found" · "Already deactivated" · "An agency must keep at least one active Master"
  - link: "Student is already linked to this agency" · prefix retries exhausted: "Please try again"
- Audit rows: `action` `agent_org.approve|reject|suspend|reinstate|master_invite|master_deactivate`, `entity_type="agent_org"`, `entity_id=str(org.id)`. Old routes keep `agent.approve` / `agent.reject` on `user_role_assignment` (E4).
- Every lock uses `SELECT … FOR UPDATE` with `populate_existing=True` on the `agent_orgs` row.
- Welcome-link order (DEC-SCOPE-019): create + `issue_welcome_token` + audit → **commit** → `deliver_welcome_link`.
- Imports shown mid-file in a task's test code are moved to the test module's top import block when appended (ruff clean, no suppressions).

## Deviations from the spec (found while planning; record in the RTM)

- **Commission claim takes a row lock** (Task 6). Spec §5.3 lists claim as "unchanged apart from scope", but once two Masters share a commission, an unlocked read-then-update lets both claim it (two claim references). The claim now selects the row `FOR UPDATE`; a race test pins it.
- **`_flush_unique_email` moves to `services/provisioning.py`** as `flush_unique_email` (Task 3), imported back into `admin.py` under its old name, so the invite path reuses it without importing a route module.
- **`RegisterForm` labels gain `htmlFor`/`id`** (Task 9) so the fields are reachable by label (tests and assistive tech); names and behaviour are unchanged.

## Test commands (PowerShell, from the worktree root)

This worktree uses its own isolated Compose project `agn001`. **The user starts the stack** (standing preference); one-off `run --rm` containers mount this worktree's source.

```powershell
# User, once:
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn001 --profile ci build api-test web-test
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn001 --profile ci up -d --wait postgres redis

# Agent:
function dc { docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn001 --profile ci @args }
dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test alembic upgrade head
dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test python -m pytest -q tests/test_agn_001_prefix.py
dc run --rm --no-deps -v "${PWD}\apps\web\components:/app/components" -v "${PWD}\apps\web\lib:/app/lib" -v "${PWD}\apps\web\tests:/app/tests" -v "${PWD}\apps\web\app:/app/app" web-test npx vitest run tests/components/AgentTeamPanel.test.tsx
```

Below, **API(x)** = the pytest command with `x` as its arguments; **WEB(x)** = the vitest command with `x`; **MIGRATE** = the `alembic upgrade head` command.

**Regression set R** (must stay green, unedited, after every backend task): API(`tests/test_agt_001_registration_approval.py tests/test_agt_002_referrals.py tests/test_agt_003_commission_accrual.py tests/test_agt_004_commission_payout.py tests/test_sec_001_audit_trail.py tests/test_rpt_002_overseas_reporting.py tests/test_role_assignments.py tests/test_provider_services.py tests/test_enh_003_first_time_provisioning.py`).

## Review Focus

1. **Two Masters acting on one shared row at once** (claiming the same commission, linking the same student) — must not double-claim or double-link, and never 500. Task 6 adds a row lock to claim and an org lock to link, each with a race test.
2. **A super_admin opening agent routes or the agent portal** — has no membership; must behave as today (empty own-scope results), never an `AttributeError` 500. Task 6 test.
3. **Deploying over a database where the new tables already exist** (dev `auto_create_schema`) — the migration must still backfill agents without a membership, and running it twice must not duplicate organisations. Task 2 (idempotent backfill) + manual step.
4. **Two agencies inviting the same email at the same moment** — one `201`, one `409 "Email already exists"`, never a 500, and the loser's `master_seq` not advanced (no half-created member). Task 8 test.
5. **The approval and team screens on a phone / keyboard only** — actions reachable, confirms usable, errors announced, no horizontal scroll at 320 px. Tasks 10, 11, 13.

---

### Task 1: Prefix and code functions

**Files:**
- Create: `apps/api/app/services/agent_orgs.py`
- Test: `apps/api/tests/test_agn_001_prefix.py`

**Interfaces:**
- Produces: `derive_prefix_base(name: str | None) -> str`, `pick_prefix(base: str, taken: set[str]) -> str`, `member_code(prefix: str, seq: int) -> str`, constants `MASTER_LIMIT = 3`, `ORG_STATUSES = ("pending", "active", "rejected", "suspended")`.

- [ ] **Step 1: Write the failing test** `apps/api/tests/test_agn_001_prefix.py`

```python
import pytest

from app.services.agent_orgs import MASTER_LIMIT, derive_prefix_base, member_code, pick_prefix


@pytest.mark.parametrize(("name", "expected"), [
    ("ABC Overseas Consultants", "ABC"),
    ("abc overseas", "ABC"),
    ("A1 Consultants", "ACO"),
    ("AB", "ABX"),
    ("A", "AXX"),
    ("12 34", "AGT"),
    ("शिक्षा", "AGT"),
    ("", "AGT"),
    (None, "AGT"),
    ("E2E Agent", "EEA"),
])
def test_prefix_base_follows_d5(name, expected):
    assert derive_prefix_base(name) == expected


def test_pick_prefix_uses_the_base_when_free():
    assert pick_prefix("ABC", set()) == "ABC"
    assert pick_prefix("ABC", {"ABD", "XYZ"}) == "ABC"


def test_pick_prefix_takes_the_lowest_free_suffix_from_2():
    assert pick_prefix("ABC", {"ABC"}) == "ABC2"
    assert pick_prefix("ABC", {"ABC", "ABC2", "ABC4"}) == "ABC3"


def test_member_code_is_zero_padded():
    assert member_code("ABC", 1) == "ABC-M001"
    assert member_code("ABC2", 12) == "ABC2-M012"
    assert member_code("ABC", 1000) == "ABC-M1000"


def test_the_master_limit_is_three():
    assert MASTER_LIMIT == 3
```

- [ ] **Step 2: Run — expect FAIL.** API(`tests/test_agn_001_prefix.py`) → `ModuleNotFoundError: No module named 'app.services.agent_orgs'`.

- [ ] **Step 3: Create** `apps/api/app/services/agent_orgs.py`

```python
"""AGN-001 / DEC-SCOPE-036 -- agent organisations (tenants) and their Master members.

Functions only -- no class layer (same shape as `services/provisioning.py`). Spec:
docs/superpowers/specs/2026-09-28-agn-001-multi-tenant-agent-crm-design.md.
"""

import re

MASTER_LIMIT = 3
ORG_STATUSES = ("pending", "active", "rejected", "suspended")

_LATIN = re.compile(r"[A-Za-z]")


def derive_prefix_base(name: str | None) -> str:
    """D5: the first three Latin letters, uppercased, padded with X; no Latin letters -> AGT."""
    letters = _LATIN.findall(name or "")
    if not letters:
        return "AGT"
    return "".join(letters[:3]).upper().ljust(3, "X")


def pick_prefix(base: str, taken: set[str]) -> str:
    """D5 collision rule: the base if free, else the lowest free base+N for N >= 2."""
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def member_code(prefix: str, seq: int) -> str:
    return f"{prefix}-M{seq:03d}"
```

- [ ] **Step 4: Run — expect PASS.** API(`tests/test_agn_001_prefix.py`).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/agent_orgs.py apps/api/tests/test_agn_001_prefix.py
git commit -m "feat(agn-001): prefix and Master code rules (D5)"
```

---

### Task 2: Models and migration `0046_agent_orgs` (with backfill)

**Files:**
- Modify: `apps/api/app/models.py` (add `AgentOrg`, `AgentOrgMember` after `AgentCommission`; add `User.agent_membership`)
- Create: `apps/api/alembic/versions/0046_agent_orgs.py`
- Test: `apps/api/tests/test_agn_001_schema.py`

**Interfaces:**
- Produces: `AgentOrg(id, name, prefix, status, master_seq, status_changed_by_user_id, status_changed_at)`, `AgentOrgMember(id, org_id, user_id, role, seq, code, status, invited_by_user_id, deactivated_by_user_id, deactivated_at, org)`, `User.agent_membership: AgentOrgMember | None` (view-only, `lazy="raise"` — must be eager-loaded).

- [ ] **Step 1: Write the failing test** `apps/api/tests/test_agn_001_schema.py`

```python
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import AgentOrg, AgentOrgMember
from tests.agn001_helpers import mk_user


@pytest.mark.asyncio
async def test_alembic_head_is_0045(db_session):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert await db_session.scalar(text("SELECT version_num FROM alembic_version")) == script.get_current_head() == "0046_agent_orgs"


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [{"status": "approved"}, {"master_seq": -1}])
async def test_org_checks_reject_bad_values(db_session, overrides):
    db_session.add(AgentOrg(**{"name": "Chk", "prefix": f"Q{uuid.uuid4().hex[:6].upper()}", "status": "pending", "master_seq": 0, **overrides}))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_a_user_belongs_to_one_organisation_only(db_session):
    user = await mk_user(db_session, role="agent")
    orgs = [AgentOrg(name="One", prefix=f"Q{uuid.uuid4().hex[:6].upper()}", status="pending", master_seq=1) for _ in range(2)]
    db_session.add_all(orgs)
    await db_session.flush()
    db_session.add(AgentOrgMember(org_id=orgs[0].id, user_id=user.id, role="master", seq=1, code=f"{orgs[0].prefix}-M001", status="active"))
    await db_session.flush()
    db_session.add(AgentOrgMember(org_id=orgs[1].id, user_id=user.id, role="master", seq=1, code=f"{orgs[1].prefix}-M001", status="active"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [{"role": "staff"}, {"status": "invited"}])
async def test_member_checks_reject_bad_values(db_session, overrides):
    user = await mk_user(db_session, role="agent")
    org = AgentOrg(name="Chk", prefix=f"Q{uuid.uuid4().hex[:6].upper()}", status="pending", master_seq=1)
    db_session.add(org)
    await db_session.flush()
    db_session.add(AgentOrgMember(**{"org_id": org.id, "user_id": user.id, "role": "master", "seq": 1, "code": f"{org.prefix}-M001", "status": "active", **overrides}))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
```

- [ ] **Step 2: Create the shared test helpers** `apps/api/tests/agn001_helpers.py` (used by every AGN-001 test file; `mk_active_org` is completed in Task 3 when `ensure_agent_org` exists — until then it is not imported by any test):

```python
import uuid
from contextlib import asynccontextmanager

import httpx
from httpx import ASGITransport
from sqlalchemy import select

from app.core.security import hash_password
from app.main import app
from app.models import AgentOrg, AgentOrgMember, User

PASSWORD = "Sup3r-Secret-Pass!"


def uniq(label: str = "agn") -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


async def mk_user(db, *, role: str, division: str = "overseas", full_name: str = "AGN User", active: bool = True, profile: dict | None = None) -> User:
    user = User(email=f"{uniq(role)}@example.local", password_hash=hash_password(PASSWORD), full_name=full_name, role=role, division=division, active=active, profile=profile or {})
    db.add(user)
    await db.commit()
    return user


async def login(client, email: str, division: str = "overseas") -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": division})
    assert response.status_code == 200, response.text


async def register_agent(client, **overrides) -> dict:
    payload = {"email": f"{uniq('agn-reg')}@example.local", "password": PASSWORD, "full_name": "Test Agent", "division": "overseas", "account_type": "agent", **overrides}
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def membership(db, user_id) -> AgentOrgMember | None:
    return await db.scalar(select(AgentOrgMember).where(AgentOrgMember.user_id == user_id).execution_options(populate_existing=True))


async def org_of(db, user_id) -> AgentOrg | None:
    member = await membership(db, user_id)
    return None if member is None else await db.get(AgentOrg, member.org_id, populate_existing=True)


@asynccontextmanager
async def client_for(email: str):
    """A separate ASGI client with its own cookie jar, so two users can be in flight at once."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await login(c, email)
        yield c
```

- [ ] **Step 3: Run — expect FAIL.** API(`tests/test_agn_001_schema.py`) → `ImportError: cannot import name 'AgentOrg'`.

- [ ] **Step 4: Add the models** in `apps/api/app/models.py`, directly after `class AgentCommission`:

```python
class AgentOrg(Base, TimestampMixin):
    """AGN-001 / DEC-SCOPE-036: an agent company -- a separate tenant. Its `status` is the agent approval gate
    (`core.rbac.agent_denial_reason`); `master_seq` is the highest Master number ever issued, so codes are never reused."""

    __tablename__ = "agent_orgs"
    __table_args__ = (
        UniqueConstraint("prefix", name="uq_agent_orgs_prefix"),
        CheckConstraint("status IN ('pending', 'active', 'rejected', 'suspended')", name="ck_agent_orgs_status"),
        CheckConstraint("master_seq >= 0", name="ck_agent_orgs_master_seq"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160))
    prefix: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(20), index=True)
    master_seq: Mapped[int] = mapped_column(Integer, default=0)
    status_changed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentOrgMember(Base, TimestampMixin):
    """AGN-001: a user's membership of exactly one agent organisation, for good (`user_id` unique). Only `master`
    exists today (D13: Staff is not decided)."""

    __tablename__ = "agent_org_members"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_agent_org_members_user"),
        UniqueConstraint("code", name="uq_agent_org_members_code"),
        UniqueConstraint("org_id", "seq", name="uq_agent_org_members_org_seq"),
        CheckConstraint("role = 'master'", name="ck_agent_org_members_role"),
        CheckConstraint("status IN ('active', 'deactivated')", name="ck_agent_org_members_status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_orgs.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20), default="master")
    seq: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(20), default="active")
    invited_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    deactivated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    org: Mapped["AgentOrg"] = relationship(lazy="raise")
```

and in `class User`, after `role_assignments`:

```python
    # AGN-001: eager-loaded (with `.org`) by `deps.get_current_user` for every request; `lazy="raise"` makes any other
    # unloaded access fail loudly instead of an async lazy-load crash.
    agent_membership: Mapped["AgentOrgMember | None"] = relationship(
        foreign_keys="AgentOrgMember.user_id", viewonly=True, uselist=False, lazy="raise"
    )
```

- [ ] **Step 5: Create the migration** `apps/api/alembic/versions/0046_agent_orgs.py`

```python
"""AGN-001 -- agent organisations (tenants) and their Master members.

Revision ID: 0046_agent_orgs
Revises: 0044_skill_india_certification

docs/superpowers/specs/2026-09-28-agn-001-multi-tenant-agent-crm-design.md §4 (DEC-SCOPE-036 D10). Creates two tables and
backfills one organisation + Master M001 per existing agent. No existing table or row is altered. The backfill only touches
agents that have no membership yet, so it is safe if the tables were already created by `auto_create_schema` and safe to
re-run. `downgrade()` drops only the two new tables.
"""

import re
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0046_agent_orgs"
down_revision = "0044_skill_india_certification"
branch_labels = None
depends_on = None

_LATIN = re.compile(r"[A-Za-z]")


# Verbatim copies of app.services.agent_orgs (a migration never imports live app code).
def _prefix_base(name):
    letters = _LATIN.findall(name or "")
    return "AGT" if not letters else "".join(letters[:3]).upper().ljust(3, "X")


def _pick(base, taken):
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def upgrade() -> None:
    bind = op.get_bind()
    existing = set() if op.get_context().as_sql else set(sa.inspect(bind).get_table_names())
    if "agent_orgs" not in existing:
        op.create_table(
            "agent_orgs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("prefix", sa.String(8), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("master_seq", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status_changed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("prefix", name="uq_agent_orgs_prefix"),
            sa.CheckConstraint("status IN ('pending', 'active', 'rejected', 'suspended')", name="ck_agent_orgs_status"),
            sa.CheckConstraint("master_seq >= 0", name="ck_agent_orgs_master_seq"),
        )
        op.create_index("ix_agent_orgs_status", "agent_orgs", ["status"])
    if "agent_org_members" not in existing:
        op.create_table(
            "agent_org_members",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_orgs.id"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role", sa.String(20), nullable=False, server_default="master"),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(16), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("deactivated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", name="uq_agent_org_members_user"),
            sa.UniqueConstraint("code", name="uq_agent_org_members_code"),
            sa.UniqueConstraint("org_id", "seq", name="uq_agent_org_members_org_seq"),
            sa.CheckConstraint("role = 'master'", name="ck_agent_org_members_role"),
            sa.CheckConstraint("status IN ('active', 'deactivated')", name="ck_agent_org_members_status"),
        )
        op.create_index("ix_agent_org_members_org_id", "agent_org_members", ["org_id"])
    if op.get_context().as_sql:
        return  # offline SQL generation: no data to backfill
    _backfill(bind)


def _backfill(bind) -> None:
    """D10: each agent without a membership becomes M001 of its own organisation; approved -> active, anything else -> pending."""
    taken = {row[0] for row in bind.execute(sa.text("SELECT prefix FROM agent_orgs"))}
    agents = bind.execute(sa.text(
        "SELECT u.id, u.full_name, u.profile->>'agency_name' AS agency_name, "
        "(SELECT a.approval_status FROM user_role_assignments a WHERE a.user_id = u.id AND a.division = 'overseas' AND a.role = 'agent') AS approval "
        "FROM users u WHERE u.role = 'agent' AND NOT EXISTS (SELECT 1 FROM agent_org_members m WHERE m.user_id = u.id) "
        "ORDER BY u.created_at, u.id"
    )).all()
    for user_id, full_name, agency_name, approval in agents:
        name = (agency_name or "").strip() or full_name
        prefix = _pick(_prefix_base(name), taken)
        taken.add(prefix)
        org_id = uuid.uuid4()
        bind.execute(
            sa.text("INSERT INTO agent_orgs (id, name, prefix, status, master_seq) VALUES (:id, :name, :prefix, :status, 1)"),
            {"id": org_id, "name": name[:160], "prefix": prefix, "status": "active" if approval == "approved" else "pending"},
        )
        bind.execute(
            sa.text("INSERT INTO agent_org_members (id, org_id, user_id, role, seq, code, status) VALUES (:id, :org, :user, 'master', 1, :code, 'active')"),
            {"id": uuid.uuid4(), "org": org_id, "user": user_id, "code": f"{prefix}-M001"},
        )


def downgrade() -> None:
    op.drop_index("ix_agent_org_members_org_id", table_name="agent_org_members")
    op.drop_table("agent_org_members")
    op.drop_index("ix_agent_orgs_status", table_name="agent_orgs")
    op.drop_table("agent_orgs")
```

- [ ] **Step 6: Migrate and run — expect PASS.** MIGRATE, then API(`tests/test_agn_001_schema.py tests/test_agn_001_prefix.py`), then regression set **R** (unedited, green).

- [ ] **Step 7: Migration round trip with legacy data (AC05).** On a throwaway database (`createdb agn001_mig` inside the postgres container, `DATABASE_URL` pointed at it for these commands): `alembic upgrade 0044_skill_india_certification`; insert with `psql` four agents — (a) approved assignment, `profile.agency_name='ABC Overseas'`; (b) pending; (c) rejected; (d) no assignment and `active=false` — plus one `agent_students` and one `overseas_applications` row for (a); `alembic upgrade head`; verify with SQL: four orgs; statuses `active, pending, pending, pending`; (a) prefix `ABC`, name `ABC Overseas`; every member `M001` active; `agent_students`/`overseas_applications` rows byte-identical (compare `md5(row::text)` before/after). Then `alembic downgrade 0044_skill_india_certification` (tables gone, business rows unchanged) and `alembic upgrade head` twice (second run adds nothing). Record the outputs for the RTM (Task 13). Drop the throwaway database.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/models.py apps/api/alembic/versions/0046_agent_orgs.py apps/api/tests/test_agn_001_schema.py apps/api/tests/agn001_helpers.py
git commit -m "feat(agn-001): agent_orgs and agent_org_members with legacy backfill (migration 0045)"
```

---

### Task 3: Organisations created on registration, login and admin create; seed

**Files:**
- Modify: `apps/api/app/services/agent_orgs.py` (add `ensure_agent_org`, `next_free_prefix`)
- Modify: `apps/api/app/services/provisioning.py` (move `_flush_unique_email` here as `flush_unique_email`)
- Modify: `apps/api/app/api/admin.py:141-148` (import the moved function under its old name), `admin.py:create_user` (call `ensure_agent_org`)
- Modify: `apps/api/app/api/auth.py:53-82` (`_sync_role_assignment`), `auth.py:108-135` (`register`)
- Modify: `apps/api/app/schemas.py` (`RegistrationRequest.agency_name`)
- Modify: `apps/api/app/seed.py:82-95`
- Modify: `apps/api/tests/agn001_helpers.py` (add `mk_active_org`)
- Test: `apps/api/tests/test_agn_001_registration_and_gate.py`

**Interfaces:**
- Consumes: Task 1 functions; Task 2 models.
- Produces: `async ensure_agent_org(db, user: User, *, agency_name: str | None = None, status: str | None = None) -> AgentOrgMember` (no commit; idempotent); `async next_free_prefix(db, base: str) -> str`; `flush_unique_email(db)` in `services/provisioning.py`; test helper `async mk_active_org(db, *, name="AGN Agency") -> dict` with keys `master`, `org`, `member`.

- [ ] **Step 1: Write the failing tests** `apps/api/tests/test_agn_001_registration_and_gate.py`

```python
import asyncio
import re

import pytest
from sqlalchemy import func, select

from app.models import AgentOrg, AgentOrgMember, UserRoleAssignment
from tests.agn001_helpers import login, membership, mk_user, org_of, register_agent, uniq


@pytest.mark.asyncio
async def test_registering_creates_one_pending_org_and_m001(client, db_session):  # AC01
    body = await register_agent(client, agency_name="Qwerty Overseas")
    member = await membership(db_session, body["user"]["id"])
    org = await org_of(db_session, body["user"]["id"])
    assert org.status == "pending" and org.name == "Qwerty Overseas" and org.master_seq == 1
    assert re.fullmatch(r"QWE\d*", org.prefix)
    assert member.seq == 1 and member.code == f"{org.prefix}-M001" and member.status == "active" and member.role == "master"
    assert await db_session.scalar(select(func.count()).select_from(AgentOrgMember).where(AgentOrgMember.org_id == org.id)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("agency_name", [None, "", "   "])
async def test_a_missing_agency_name_falls_back_to_the_full_name(client, db_session, agency_name):  # E2
    overrides = {"full_name": "Zulu Yankee"} | ({} if agency_name is None else {"agency_name": agency_name})
    body = await register_agent(client, **overrides)
    org = await org_of(db_session, body["user"]["id"])
    assert org.name == "Zulu Yankee" and re.fullmatch(r"ZUL\d*", org.prefix)


@pytest.mark.asyncio
async def test_registration_response_shape_is_unchanged(client):  # E8
    body = await register_agent(client, agency_name="Shape Check")
    assert set(body) == {"user", "expires_in_minutes"}
    assert "agent_membership" not in body["user"]


@pytest.mark.asyncio
async def test_an_agency_name_over_160_characters_is_422(client):
    response = await client.post("/api/v1/auth/register", json={"email": "long@example.local", "password": "Sup3r-Secret-Pass!", "full_name": "Long Name", "division": "overseas", "account_type": "agent", "agency_name": "A" * 161})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_student_registration_creates_no_org(client, db_session):
    response = await client.post("/api/v1/auth/register", json={"email": f"{uniq('agn-student')}@example.local", "password": "Sup3r-Secret-Pass!", "full_name": "A Student", "division": "overseas"})
    assert response.status_code == 201
    assert await membership(db_session, response.json()["user"]["id"]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("approval", "expected"), [("approved", "active"), ("pending", "pending"), ("rejected", "pending")])
async def test_a_legacy_agent_without_an_org_gets_one_on_login(client, db_session, approval, expected):  # E7, D10 mapping
    agent = await mk_user(db_session, role="agent", full_name="Legacy Person")
    db_session.add(UserRoleAssignment(user_id=agent.id, division="overseas", role="agent", approval_status=approval))
    await db_session.commit()
    await login(client, agent.email)
    org = await org_of(db_session, agent.id)
    assert org.status == expected and re.fullmatch(r"LEG\d*", org.prefix)
    await login(client, agent.email)  # idempotent: a second login adds nothing
    assert await db_session.scalar(select(func.count()).select_from(AgentOrgMember).where(AgentOrgMember.user_id == agent.id)) == 1


@pytest.mark.asyncio
async def test_an_admin_created_agent_gets_a_pending_org(client, db_session):  # AC09
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    response = await client.post("/api/v1/admin/users", json={"role": "agent", "division": "overseas", "email": f"{uniq('agn-admin-made')}@example.local", "full_name": "Made By Admin", "profile": {"agency_name": "Admin Made Agency"}})
    assert response.status_code == 201
    member = await membership(db_session, response.json()["id"])
    org = await org_of(db_session, response.json()["id"])
    assert org.status == "pending" and org.name == "Admin Made Agency" and member.code == f"{org.prefix}-M001"


@pytest.mark.asyncio
async def test_same_prefix_registrations_racing_get_distinct_prefixes(db_session):  # race: prefix
    import httpx
    from httpx import ASGITransport

    from app.main import app

    async def one():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            return await register_agent(c, agency_name="Racecar Agency")

    first, second = await asyncio.gather(one(), one())
    prefixes = {(await org_of(db_session, b["user"]["id"])).prefix for b in (first, second)}
    assert len(prefixes) == 2
```

- [ ] **Step 2: Run — expect FAIL.** API(`tests/test_agn_001_registration_and_gate.py`) → registration test fails (`membership(...)` is `None`); `agency_name` 422 test fails (extra field ignored → 201).

- [ ] **Step 3: Move `_flush_unique_email`.** Cut `async def _flush_unique_email` (`admin.py:141-148`) and paste into `apps/api/app/services/provisioning.py` (after `unusable_password_hash`) as:

```python
async def flush_unique_email(db: AsyncSession) -> None:
    """Flush a new account; two simultaneous creates for one email are settled by the unique
    constraint (409 for the loser, never a 500). Rolling back also drops anything created with it."""
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Email already exists") from None
```

adding `from fastapi import HTTPException` and `from sqlalchemy.exc import IntegrityError` to provisioning's imports. In `admin.py`, extend the existing `from app.services.provisioning import (...)` line with `flush_unique_email as _flush_unique_email` so every existing call site is unchanged.

- [ ] **Step 4: Add `ensure_agent_org`** to `apps/api/app/services/agent_orgs.py` (extend the imports at the top):

```python
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrg, AgentOrgMember, User, UserRoleAssignment

_PREFIX_ATTEMPTS = 5


async def next_free_prefix(db: AsyncSession, base: str) -> str:
    taken = set((await db.scalars(select(AgentOrg.prefix).where(AgentOrg.prefix.like(f"{base}%")))).all())
    return pick_prefix(base, taken)


async def _status_from_assignment(db: AsyncSession, user: User) -> str:
    """D10 mapping, shared by the migration backfill and runtime creation: approved -> active, else pending."""
    approval = await db.scalar(
        select(UserRoleAssignment.approval_status).where(UserRoleAssignment.user_id == user.id, UserRoleAssignment.division == "overseas", UserRoleAssignment.role == "agent")
    )
    return "active" if approval == "approved" else "pending"


async def ensure_agent_org(db: AsyncSession, user: User, *, agency_name: str | None = None, status: str | None = None) -> AgentOrgMember:
    """No commit. Idempotent: returns the user's membership, creating their organisation + Master M001 when missing (E7).

    Two creations racing for one prefix are settled by `uq_agent_orgs_prefix`: the loser's savepoint rolls back and it
    retries with the next free prefix. Two creations racing for one USER are settled by `uq_agent_org_members_user`: the
    loser re-reads and returns the winner's membership."""
    existing = await db.scalar(select(AgentOrgMember).where(AgentOrgMember.user_id == user.id))
    if existing:
        return existing
    name = (agency_name or "").strip()[:160] or user.full_name
    status = status or await _status_from_assignment(db, user)
    for _ in range(_PREFIX_ATTEMPTS):
        prefix = await next_free_prefix(db, derive_prefix_base(name))
        try:
            async with db.begin_nested():
                org = AgentOrg(name=name, prefix=prefix, status=status, master_seq=1)
                db.add(org)
                await db.flush()
                member = AgentOrgMember(org_id=org.id, user_id=user.id, role="master", seq=1, code=member_code(prefix, 1), status="active")
                db.add(member)
                await db.flush()
            return member
        except IntegrityError as exc:
            if "uq_agent_org_members_user" in str(exc.orig):
                winner = await db.scalar(select(AgentOrgMember).where(AgentOrgMember.user_id == user.id))
                if winner:
                    return winner
    raise HTTPException(409, "Please try again")
```

- [ ] **Step 5: Wire registration, login sync and admin create.**

`apps/api/app/schemas.py` — in `RegistrationRequest` add the field and validator:

```python
    agency_name: str | None = Field(default=None, max_length=160)

    @field_validator("agency_name")
    @classmethod
    def blank_agency_name_is_none(cls, value: str | None) -> str | None:
        return (value or "").strip() or None
```

`apps/api/app/api/auth.py` — import `from app.services.agent_orgs import ensure_agent_org`; in `_sync_role_assignment` replace the early return and the final return so an agent always has an organisation:

```python
    if existing:
        if user.role == "agent":
            await ensure_agent_org(db, user)
        return existing
    ...
    db.add(assignment)
    await db.flush()
    if user.role == "agent":
        await ensure_agent_org(db, user)
    return assignment
```

and in `register`, directly after the first `await db.flush()` (before `_sync_role_assignment`):

```python
    if role == "agent":
        await ensure_agent_org(db, user, agency_name=payload.agency_name, status="pending")
```

`apps/api/app/api/admin.py` — import `ensure_agent_org`; in `create_user`, after `await _flush_unique_email(db)`:

```python
    if role == "agent":
        await ensure_agent_org(db, item, agency_name=(item.profile or {}).get("agency_name"), status="pending")
```

`apps/api/app/seed.py` — after the demo-agent assignment block (line ~95), add (import `AgentOrg` and `ensure_agent_org`):

```python
        # AGN-001 (E7): the demo agent's organisation, active like its assignment above.
        await db.flush()
        demo_member = await ensure_agent_org(db, us["agent"], agency_name=us["agent"].profile.get("agency_name"), status="active")
        (await db.get(AgentOrg, demo_member.org_id)).status = "active"
```

- [ ] **Step 6: Add `mk_active_org`** to `apps/api/tests/agn001_helpers.py`:

```python
async def mk_active_org(db, *, name: str = "AGN Agency") -> dict:
    """An approved agent who is M001 of an active organisation."""
    from app.models import UserRoleAssignment
    from app.services.agent_orgs import ensure_agent_org

    master = await mk_user(db, role="agent", full_name=f"{name} Master")
    db.add(UserRoleAssignment(user_id=master.id, division="overseas", role="agent", approval_status="approved"))
    await db.flush()
    member = await ensure_agent_org(db, master, agency_name=name, status="active")
    await db.commit()
    return {"master": master, "member": member, "org": await db.get(AgentOrg, member.org_id)}
```

- [ ] **Step 7: Run — expect PASS.** API(`tests/test_agn_001_registration_and_gate.py`), then **R**, then API(`tests/test_adm_001_admin_crud.py`) (unedited, green). Run the seed once in the container (`python -m app.seed`) — exit 0.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/services/agent_orgs.py apps/api/app/services/provisioning.py apps/api/app/api/admin.py apps/api/app/api/auth.py apps/api/app/schemas.py apps/api/app/seed.py apps/api/tests/agn001_helpers.py apps/api/tests/test_agn_001_registration_and_gate.py
git commit -m "feat(agn-001): create the organisation and M001 on registration, login and admin create"
```

---

### Task 4: The organisation is the gate

**Files:**
- Modify: `apps/api/app/api/deps.py:24-26`
- Modify: `apps/api/app/core/rbac.py:75-88`
- Modify: `apps/api/app/api/workflows.py:100-111` (`_require`)
- Modify: `apps/api/app/api/portal.py:28-32`
- Test: `apps/api/tests/test_agn_001_registration_and_gate.py` (append)

**Interfaces:**
- Produces: `rbac.agent_denial_reason(user) -> str | None`; constants `rbac.PENDING_MESSAGE`, `rbac.SUSPENDED_MESSAGE`, `rbac.DEACTIVATED_MESSAGE`; `agent_is_approved(user) -> bool` (unchanged signature).

- [ ] **Step 1: Append the failing tests**

```python
AGENT_ROUTES = [
    ("get", "/api/v1/workflows/overseas/agent/students"),
    ("get", "/api/v1/workflows/overseas/agent/commissions"),
    ("get", "/api/v1/workflows/overseas/applications"),
    ("get", "/api/v1/portal/overseas/agent/dashboard"),
    ("get", "/api/v1/portal/overseas/agent/students"),
    ("get", "/api/v1/portal/overseas/agent/commissions"),
]


async def _set_org_status(db, user_id, status):
    org = await org_of(db, user_id)
    org.status = status
    await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "rejected"])
async def test_a_pending_or_rejected_org_is_denied_every_agent_route(client, db_session, status):  # AC02
    ctx = await mk_active_org(db_session, name="Gate Agency")
    await _set_org_status(db_session, ctx["master"].id, status)
    await login(client, ctx["master"].email)
    for method, url in AGENT_ROUTES:
        response = await getattr(client, method)(url)
        assert response.status_code == 403 and response.json()["detail"] == "Agent registration is pending approval", url


@pytest.mark.asyncio
async def test_suspension_applies_on_the_next_request_and_reinstatement_restores(client, db_session):  # AC04
    ctx = await mk_active_org(db_session, name="Suspend Agency")
    await login(client, ctx["master"].email)
    assert (await client.get("/api/v1/workflows/overseas/agent/students")).status_code == 200
    await _set_org_status(db_session, ctx["master"].id, "suspended")
    for method, url in AGENT_ROUTES:
        response = await getattr(client, method)(url)
        assert response.status_code == 403 and response.json()["detail"] == "Your agency's account is suspended", url
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    assert (await client.get("/api/v1/workflows/notifications")).status_code == 200
    assert (await client.post("/api/v1/auth/logout")).status_code == 200
    await login(client, ctx["master"].email)
    await _set_org_status(db_session, ctx["master"].id, "active")
    assert (await client.get("/api/v1/workflows/overseas/agent/students")).status_code == 200


@pytest.mark.asyncio
async def test_a_deactivated_member_whose_login_was_re_enabled_is_still_denied(client, db_session):  # E9, E10
    ctx = await mk_active_org(db_session, name="Deact Agency")
    member = await membership(db_session, ctx["master"].id)
    member.status = "deactivated"
    await db_session.commit()
    await login(client, ctx["master"].email)
    response = await client.get("/api/v1/workflows/overseas/agent/students")
    assert response.status_code == 403 and response.json()["detail"] == "Your Master account is deactivated"
```

Add `mk_active_org` to the test module's imports. (`GET /api/v1/workflows/notifications` is ungated — it never calls `_require` — so it must stay 200 while suspended.)

- [ ] **Step 2: Run — expect FAIL.** API(`tests/test_agn_001_registration_and_gate.py -k "denied or suspension or deactivated"`) → suspended org still gets 200 (gate reads the assignment).

- [ ] **Step 3: Implement.**

`apps/api/app/api/deps.py` — extend the options (import `AgentOrgMember`):

```python
        select(User).where(User.id == uid, User.active.is_(True)).options(
            selectinload(User.role_assignments), selectinload(User.agent_membership).selectinload(AgentOrgMember.org)
        )
```

`apps/api/app/core/rbac.py` — replace `agent_is_approved` with:

```python
PENDING_MESSAGE = "Agent registration is pending approval"
SUSPENDED_MESSAGE = "Your agency's account is suspended"
DEACTIVATED_MESSAGE = "Your Master account is deactivated"


def agent_denial_reason(user) -> str | None:
    """AGN-001 (DEC-SCOPE-036 D6, spec E10): why an agent is denied every agent route, or None.

    Reads `user.agent_membership` (+ `.org`), eager-loaded by `get_current_user` on every request, so a suspension
    applies on the member's next request. The organisation's status is the gate (AGT-001-AC02 preserved: a pending or
    rejected organisation is denied with the same message as before). Non-agents are never denied here."""

    if user.role != "agent":
        return None
    membership = user.agent_membership
    if membership is None:
        return PENDING_MESSAGE
    if membership.status != "active":
        return DEACTIVATED_MESSAGE
    if membership.org.status == "suspended":
        return SUSPENDED_MESSAGE
    if membership.org.status != "active":
        return PENDING_MESSAGE
    return None


def agent_is_approved(user) -> bool:
    return agent_denial_reason(user) is None
```

`apps/api/app/api/workflows.py` — import `agent_denial_reason` instead of `agent_is_approved`; replace the last two lines of `_require`:

```python
    reason = agent_denial_reason(user)
    if reason:
        raise HTTPException(403, reason)
```

`apps/api/app/api/portal.py` — same replacement for the gate block:

```python
    reason = agent_denial_reason(user)
    if reason:
        raise HTTPException(403, reason)
```

- [ ] **Step 4: Run — expect PASS.** API(`tests/test_agn_001_registration_and_gate.py`), then **R** (unedited; `test_agt_001`'s pending/rejected cases now pass through the org gate).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/deps.py apps/api/app/core/rbac.py apps/api/app/api/workflows.py apps/api/app/api/portal.py apps/api/tests/test_agn_001_registration_and_gate.py
git commit -m "feat(agn-001): the organisation's status is the agent approval gate"
```

---

### Task 5: Overseas Admin organisation actions; old routes act on the organisation

**Files:**
- Modify: `apps/api/app/services/agent_orgs.py` (add `TRANSITIONS`, `lock_org`, `set_org_status`, `transition_org`)
- Modify: `apps/api/app/api/admin.py:981-1026` (old routes; new `agent-orgs` routes on `agents_router`)
- Test: `apps/api/tests/test_agn_001_org_admin.py`

**Interfaces:**
- Consumes: `ensure_agent_org` (Task 3).
- Produces: `async lock_org(db, org_id) -> AgentOrg` (404 "Agent organisation not found"); `async set_org_status(db, org, status: str, actor: User, *, write_through: bool) -> None`; `async transition_org(db, org_id, action: str, actor: User) -> AgentOrg` (no commit); `TRANSITIONS` dict.

- [ ] **Step 1: Write the failing tests** `apps/api/tests/test_agn_001_org_admin.py`

```python
import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, UserRoleAssignment
from tests.agn001_helpers import login, mk_active_org, mk_user, org_of, register_agent

ORG_ACTION = "/api/v1/overseas-admin/agent-orgs/{oid}/{action}"


async def _admin(client, db):
    admin = await mk_user(db, role="overseas_admin")
    await login(client, admin.email)
    return admin


async def _audits(db, org_id, action):
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(org_id), AuditLog.action == action))


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "action", "end"), [
    ("pending", "approve", "active"), ("rejected", "approve", "active"), ("pending", "reject", "rejected"),
    ("active", "suspend", "suspended"), ("suspended", "reinstate", "active"),
])
async def test_valid_transitions_change_status_and_audit(client, db_session, start, action, end):  # AC03
    ctx = await mk_active_org(db_session, name="Trans Agency")
    ctx["org"].status = start
    await db_session.commit()
    admin = await _admin(client, db_session)
    response = await client.post(ORG_ACTION.format(oid=ctx["org"].id, action=action))
    assert response.status_code == 200 and response.json() == {"id": str(ctx["org"].id), "status": end}
    org = await org_of(db_session, ctx["master"].id)
    assert org.status == end and org.status_changed_by_user_id == admin.id and org.status_changed_at is not None
    log = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(org.id), AuditLog.action == f"agent_org.{action}"))
    assert log.entity_type == "agent_org" and log.outcome == end and log.metadata_json == {"from": start} and log.user_id == admin.id


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "action"), [
    ("active", "approve"), ("suspended", "approve"), ("active", "reject"), ("rejected", "reject"), ("suspended", "reject"),
    ("pending", "suspend"), ("suspended", "suspend"), ("rejected", "suspend"),
    ("pending", "reinstate"), ("active", "reinstate"), ("rejected", "reinstate"),
])
async def test_invalid_transitions_are_409_with_no_change_and_no_audit(client, db_session, start, action):  # AC03
    ctx = await mk_active_org(db_session, name="Bad Trans")
    ctx["org"].status = start
    await db_session.commit()
    await _admin(client, db_session)
    response = await client.post(ORG_ACTION.format(oid=ctx["org"].id, action=action))
    assert response.status_code == 409 and response.json()["detail"] == f"Cannot {action} an organisation that is {start}"
    assert (await org_of(db_session, ctx["master"].id)).status == start
    assert await _audits(db_session, ctx["org"].id, f"agent_org.{action}") == 0


@pytest.mark.asyncio
async def test_unknown_org_is_404_and_non_admin_is_403(client, db_session):
    await _admin(client, db_session)
    assert (await client.post(ORG_ACTION.format(oid=uuid.uuid4(), action="approve"))).status_code == 404
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    ctx = await mk_active_org(db_session, name="Forbid")
    assert (await client.post(ORG_ACTION.format(oid=ctx["org"].id, action="suspend"))).status_code == 403
    assert (await client.get("/api/v1/overseas-admin/agent-orgs")).status_code == 403


@pytest.mark.asyncio
async def test_approve_and_reject_write_through_to_master_assignments(client, db_session):  # E11
    body = await register_agent(client, agency_name="Write Through")
    org = await org_of(db_session, body["user"]["id"])
    await _admin(client, db_session)
    await client.post(ORG_ACTION.format(oid=org.id, action="approve"))
    assignment = await db_session.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == uuid.UUID(body["user"]["id"])).execution_options(populate_existing=True))
    assert assignment.approval_status == "approved"
    await client.post(ORG_ACTION.format(oid=org.id, action="suspend"))
    await db_session.refresh(assignment)
    assert assignment.approval_status == "approved"  # suspend does not touch assignments


@pytest.mark.asyncio
async def test_list_groups_masters_and_filters_by_status(client, db_session):
    ctx = await mk_active_org(db_session, name="Listed Agency")
    await _admin(client, db_session)
    rows = (await client.get("/api/v1/overseas-admin/agent-orgs?status=active")).json()
    row = next(r for r in rows if r["id"] == str(ctx["org"].id))
    assert row["name"] == "Listed Agency" and row["prefix"] == ctx["org"].prefix and row["status"] == "active"
    assert row["masters"] == [{"id": str(ctx["member"].id), "code": ctx["member"].code, "full_name": ctx["master"].full_name, "email": ctx["master"].email, "status": "active"}]
    assert all(r["status"] == "active" for r in rows)
    assert (await client.get("/api/v1/overseas-admin/agent-orgs?status=approved")).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(("action", "end", "audit"), [("approve", "active", "agent.approve"), ("reject", "rejected", "agent.reject")])
async def test_old_routes_keep_their_audit_and_set_the_org(client, db_session, action, end, audit):  # E4
    body = await register_agent(client, agency_name="Old Route")
    await _admin(client, db_session)
    response = await client.post(f"/api/v1/overseas-admin/agents/{body['user']['id']}/{action}")
    assert response.status_code == 200 and response.json()["approval_status"] == ("approved" if action == "approve" else "rejected")
    assert (await org_of(db_session, body["user"]["id"])).status == end
    assert await db_session.scalar(select(AuditLog).where(AuditLog.action == audit, AuditLog.entity_type == "user_role_assignment").order_by(AuditLog.created_at.desc())) is not None


@pytest.mark.asyncio
async def test_old_reject_still_works_on_an_active_org(client, db_session):  # E4 any-state
    ctx = await mk_active_org(db_session, name="Any State")
    await _admin(client, db_session)
    assert (await client.post(f"/api/v1/overseas-admin/agents/{ctx['master'].id}/reject")).status_code == 200
    assert (await org_of(db_session, ctx["master"].id)).status == "rejected"
```

- [ ] **Step 2: Run — expect FAIL.** API(`tests/test_agn_001_org_admin.py`) → 404 on `/agent-orgs/...` (routes missing).

- [ ] **Step 3: Implement** in `apps/api/app/services/agent_orgs.py` (extend imports with `from datetime import UTC, datetime`, `update`, `AuditLog`):

```python
TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "approve": (frozenset({"pending", "rejected"}), "active"),
    "reject": (frozenset({"pending"}), "rejected"),
    "suspend": (frozenset({"active"}), "suspended"),
    "reinstate": (frozenset({"suspended"}), "active"),
}


async def lock_org(db: AsyncSession, org_id) -> AgentOrg:
    """Row lock on the organisation; serialises every status change and member change for it."""
    org = await db.scalar(select(AgentOrg).where(AgentOrg.id == org_id).with_for_update().execution_options(populate_existing=True))
    if not org:
        raise HTTPException(404, "Agent organisation not found")
    return org


async def set_org_status(db: AsyncSession, org: AgentOrg, status: str, actor: User, *, write_through: bool) -> None:
    """No commit. E11: approve/reject also set the Master assignments' approval_status; suspend/reinstate do not."""
    now = datetime.now(UTC)
    org.status = status
    org.status_changed_by_user_id = actor.id
    org.status_changed_at = now
    if write_through:
        await db.execute(
            update(UserRoleAssignment)
            .where(UserRoleAssignment.role == "agent", UserRoleAssignment.division == "overseas", UserRoleAssignment.user_id.in_(select(AgentOrgMember.user_id).where(AgentOrgMember.org_id == org.id)))
            .values(approval_status="approved" if status == "active" else "rejected", approved_by_user_id=actor.id, approved_at=now)
        )


async def transition_org(db: AsyncSession, org_id, action: str, actor: User) -> AgentOrg:
    """No commit. D6/D7: validate the move under the row lock, change status, audit in the same transaction."""
    org = await lock_org(db, org_id)
    allowed, target = TRANSITIONS[action]
    if org.status not in allowed:
        raise HTTPException(409, f"Cannot {action} an organisation that is {org.status}")
    previous = org.status
    await set_org_status(db, org, target, actor, write_through=action in {"approve", "reject"})
    db.add(AuditLog(user_id=actor.id, action=f"agent_org.{action}", entity_type="agent_org", entity_id=str(org.id), outcome=target, metadata_json={"from": previous}))
    return org
```

In `apps/api/app/api/admin.py` (import `AgentOrg`, `AgentOrgMember`, `ensure_agent_org`, `lock_org`, `set_org_status`, `transition_org`, `ORG_STATUSES`, `Literal` from typing):

Old routes — in `approve_agent`, after `assignment.approved_at = ...` and before the `AuditLog`:

```python
    agent = await db.get(User, agent_id)
    member = await ensure_agent_org(db, agent)
    await set_org_status(db, await lock_org(db, member.org_id), "active", user, write_through=True)
```

and in `reject_agent` the same with `"rejected"`. Keep both routes' existing audit rows and responses exactly as they are.

New routes, after `list_agents`:

```python
def _require_overseas_admin(user: User) -> None:
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")


@agents_router.get("/agent-orgs")
async def list_agent_orgs(status: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_overseas_admin(user)
    if status is not None and status not in ORG_STATUSES:
        raise HTTPException(422, "Unknown organisation status")
    stmt = select(AgentOrg).order_by(AgentOrg.created_at.desc())
    if status:
        stmt = stmt.where(AgentOrg.status == status)
    orgs = (await db.scalars(stmt)).all()
    masters: dict = {}
    if orgs:
        rows = (await db.execute(select(AgentOrgMember, User).join(User, User.id == AgentOrgMember.user_id).where(AgentOrgMember.org_id.in_([o.id for o in orgs])).order_by(AgentOrgMember.seq))).all()
        for member, member_user in rows:
            masters.setdefault(member.org_id, []).append({"id": member.id, "code": member.code, "full_name": member_user.full_name, "email": member_user.email, "status": member.status})
    return [{"id": o.id, "name": o.name, "prefix": o.prefix, "status": o.status, "created_at": o.created_at, "masters": masters.get(o.id, [])} for o in orgs]


@agents_router.post("/agent-orgs/{org_id}/{action}")
async def act_on_agent_org(org_id: UUID, action: Literal["approve", "reject", "suspend", "reinstate"], user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_overseas_admin(user)
    org = await transition_org(db, org_id, action, user)
    result = {"id": org.id, "status": org.status}
    await db.commit()
    return result
```

(An unknown `action` segment is rejected by FastAPI's `Literal` validation with 422.)

- [ ] **Step 4: Run — expect PASS.** API(`tests/test_agn_001_org_admin.py tests/test_agn_001_registration_and_gate.py`), then **R**.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/agent_orgs.py apps/api/app/api/admin.py apps/api/tests/test_agn_001_org_admin.py
git commit -m "feat(agn-001): Overseas Admin approve/reject/suspend/reinstate agent organisations"
```

---

### Task 6: Tenant scoping on every agent read and write

**Files:**
- Modify: `apps/api/app/services/agent_orgs.py` (add `org_member_ids`, `member_user_ids`)
- Modify: `apps/api/app/api/workflows.py` — `_assigned_application` (~145-160), `create_overseas_application` (~1744-1747), `list_overseas_applications` (~1834-1835), `add_document` (~1991-1997), `download_student_document` (~2060-2063), `agent_students` (~2277), `add_agent_student` (~2287-2290), `agent_commissions` (~2307), `claim_commission` (~2331-2333)
- Modify: `apps/api/app/services/portal.py:677-695` (`_agent`)
- Test: `apps/api/tests/test_agn_001_tenancy.py`

**Interfaces:**
- Consumes: `lock_org` (Task 5); `User.agent_membership` loaded by `get_current_user` (Task 4).
- Produces: `org_member_ids(user) -> Select` (a one-column select of user ids; for a user with no membership it selects just `user.id`, preserving today's self-scope); `async member_user_ids(db, user) -> set[UUID]`.

- [ ] **Step 1: Write the failing tests** `apps/api/tests/test_agn_001_tenancy.py`

```python
import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentCommission, AgentOrgMember, AgentStudent, Country, OverseasApplication, StudentDocument, University, User, UserRoleAssignment
from tests.agn001_helpers import client_for, login, mk_active_org, mk_user


async def _university(db) -> University:
    country = Country(slug=f"agn-c-{uuid.uuid4().hex[:8]}", name="Testland", overview="", tuition="", living_expenses="", visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[])
    db.add(country)
    await db.flush()
    university = University(country_id=country.id, slug=f"agn-u-{uuid.uuid4().hex[:8]}", name=f"AGN Uni {uuid.uuid4().hex[:6]}", city="", overview="", eligibility="", requirements=[], deadlines=[], scholarships=[])
    db.add(university)
    await db.commit()
    return university


async def _tenant(db, name: str) -> dict:
    ctx = await mk_active_org(db, name=name)
    student = await mk_user(db, role="overseas_student", full_name=f"{name} Student")
    university = await _university(db)
    db.add(AgentStudent(agent_id=ctx["master"].id, student_id=student.id, status="active"))
    application = OverseasApplication(student_id=student.id, university_id=university.id, agent_id=ctx["master"].id, intake="Sep 2027", status="enrolled")
    db.add(application)
    await db.flush()
    document = StudentDocument(student_id=student.id, application_id=application.id, document_type="passport", file_url="local/agn.pdf")
    commission = AgentCommission(agent_id=ctx["master"].id, application_id=application.id, amount=1000, currency="INR", status="eligible")
    db.add_all([document, commission])
    await db.commit()
    return ctx | {"student": student, "university": university, "application": application, "document": document, "commission": commission}


async def _second_master(db, tenant) -> User:
    """M002 of the tenant's organisation, with a usable password (bypasses the invite for scoping tests)."""
    org = tenant["org"]
    user = await mk_user(db, role="agent", full_name="Second Master")
    db.add(UserRoleAssignment(user_id=user.id, division="overseas", role="agent", approval_status="approved"))
    org = await db.get(type(org), org.id, populate_existing=True)
    org.master_seq += 1
    db.add(AgentOrgMember(org_id=org.id, user_id=user.id, role="master", seq=org.master_seq, code=f"{org.prefix}-M{org.master_seq:03d}", status="active"))
    await db.commit()
    return user


@pytest_asyncio.fixture
async def world(db_session):
    return {"a": await _tenant(db_session, "Alpha Agency"), "b": await _tenant(db_session, "Bravo Agency")}


READS = [
    ("/api/v1/workflows/overseas/agent/students", "student_id", "student"),
    ("/api/v1/workflows/overseas/agent/commissions", "id", "commission"),
    ("/api/v1/workflows/overseas/applications", "id", "application"),
]
PORTAL_SECTIONS = ["dashboard", "students", "applications", "documents", "commissions", "reports"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("url", "key", "kind"), READS)
async def test_lists_show_own_org_rows_and_never_the_other_orgs(client, world, url, key, kind):  # AC06 reads
    await login(client, world["a"]["master"].email)
    ids = {str(row[key]) for row in (await client.get(url)).json()}
    assert str(world["a"][kind].id) in ids and str(world["b"][kind].id) not in ids


@pytest.mark.asyncio
@pytest.mark.parametrize("section", PORTAL_SECTIONS)
async def test_portal_sections_never_mention_the_other_org(client, world, section):  # AC06 portal
    await login(client, world["a"]["master"].email)
    response = await client.get(f"/api/v1/portal/overseas/agent/{section}")
    assert response.status_code == 200
    text = response.text
    for thing in ("student", "application", "document", "commission"):
        assert str(world["b"][thing].id) not in text
    assert world["b"]["student"].full_name not in text and world["b"]["master"].email not in text


@pytest.mark.asyncio
async def test_writes_on_the_other_orgs_rows_are_refused(client, world, db_session):  # AC06 writes
    a, b = world["a"], world["b"]
    await login(client, a["master"].email)
    claim = await client.post(f"/api/v1/workflows/overseas/agent/commissions/{b['commission'].id}/claim")
    assert claim.status_code == 404
    app = await client.post("/api/v1/workflows/overseas/applications", json={"student_id": str(b["student"].id), "university_id": str(b["university"].id), "intake": "Jan 2028"})
    assert app.status_code == 403
    doc_on_app = await client.post("/api/v1/workflows/overseas/documents", json={"student_id": str(b["student"].id), "application_id": str(b["application"].id), "document_type": "passport", "file_url": "local/x.pdf"})
    assert doc_on_app.status_code == 403
    doc_plain = await client.post("/api/v1/workflows/overseas/documents", json={"student_id": str(b["student"].id), "document_type": "passport", "file_url": "local/x.pdf"})
    assert doc_plain.status_code == 403
    download = await client.get(f"/api/v1/workflows/overseas/documents/{b['document'].id}/download")
    assert download.status_code == 403
    await db_session.refresh(b["commission"])
    assert b["commission"].status == "eligible"


@pytest.mark.asyncio
async def test_a_second_master_sees_and_claims_what_the_first_created(client, world, db_session):  # D1 in-org sharing
    a = world["a"]
    second = await _second_master(db_session, a)
    await login(client, second.email)
    students = (await client.get("/api/v1/workflows/overseas/agent/students")).json()
    assert str(a["student"].id) in {s["student_id"] for s in students}
    assert (await client.post(f"/api/v1/workflows/overseas/agent/commissions/{a['commission'].id}/claim")).status_code == 200


@pytest.mark.asyncio
async def test_linking_a_student_already_linked_by_another_master_is_409(client, world, db_session):  # E12
    second = await _second_master(db_session, world["a"])
    await login(client, second.email)
    response = await client.post("/api/v1/workflows/overseas/agent/students", json={"student_id": str(world["a"]["student"].id)})
    assert response.status_code == 409 and response.json()["detail"] == "Student is already linked to this agency"


@pytest.mark.asyncio
async def test_another_org_may_still_refer_the_same_student(client, world):  # E12, today's behaviour
    await login(client, world["b"]["master"].email)
    response = await client.post("/api/v1/workflows/overseas/agent/students", json={"student_id": str(world["a"]["student"].id)})
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_two_masters_claiming_one_commission_at_once_claim_it_once(world, db_session):  # race: claim
    second = await _second_master(db_session, world["a"])
    url = f"/api/v1/workflows/overseas/agent/commissions/{world['a']['commission'].id}/claim"
    async with client_for(world["a"]["master"].email) as c1, client_for(second.email) as c2:
        results = await asyncio.gather(c1.post(url), c2.post(url))
    assert sorted(r.status_code for r in results) == [200, 409]


@pytest.mark.asyncio
async def test_two_masters_linking_one_student_at_once_link_it_once(world, db_session):  # race: link
    second = await _second_master(db_session, world["a"])
    student = await mk_user(db_session, role="overseas_student")
    body = {"student_id": str(student.id)}
    async with client_for(world["a"]["master"].email) as c1, client_for(second.email) as c2:
        results = await asyncio.gather(c1.post("/api/v1/workflows/overseas/agent/students", json=body), c2.post("/api/v1/workflows/overseas/agent/students", json=body))
    assert sorted(r.status_code for r in results) == [201, 409]
    assert await db_session.scalar(select(func.count()).select_from(AgentStudent).where(AgentStudent.student_id == student.id)) == 1


@pytest.mark.asyncio
async def test_a_super_admin_on_agent_routes_behaves_as_before(client, db_session):  # Review Focus 2
    admin = await mk_user(db_session, role="super_admin", division="global")
    await login(client, admin.email)
    assert (await client.get("/api/v1/workflows/overseas/agent/students")).json() == []
    assert (await client.get("/api/v1/workflows/overseas/agent/commissions")).json() == []
    assert (await client.get("/api/v1/portal/overseas/agent/dashboard")).status_code == 200
```

(The `team` portal section is added and tested in Task 8. `login` skips the division check for `super_admin`, so logging in through the overseas portal is valid.)

- [ ] **Step 2: Run — expect FAIL.** API(`tests/test_agn_001_tenancy.py`) → in-org sharing fails (M002 sees an empty roster), E12 test gets 201, claim race yields `[200, 200]`.

- [ ] **Step 3: Add the scoping helpers** to `apps/api/app/services/agent_orgs.py`:

```python
from sqlalchemy import Select


def org_member_ids(user: User) -> Select:
    """The user ids whose agent rows the caller may see: every member of the caller's organisation (D1). A user with no
    membership (super_admin passing `_require`) keeps today's self-scope."""
    membership = user.agent_membership
    if membership is None:
        return select(User.id).where(User.id == user.id)
    return select(AgentOrgMember.user_id).where(AgentOrgMember.org_id == membership.org_id)


async def member_user_ids(db: AsyncSession, user: User) -> set:
    return set((await db.scalars(org_member_ids(user))).all())
```

- [ ] **Step 4: Replace each scope site** in `apps/api/app/api/workflows.py` (import `lock_org`, `member_user_ids`, `org_member_ids`):

`_assigned_application` — before `allowed = (`:

```python
    agent_in_scope = user.role == "agent" and item.agent_id in await member_user_ids(db, user)
```

and replace `or user.role == "agent"\n        and item.agent_id == user.id` with `or agent_in_scope`.

`create_overseas_application`:

```python
        linked = await db.scalar(select(AgentStudent.id).where(AgentStudent.agent_id.in_(org_member_ids(user)), AgentStudent.student_id == student_id, AgentStudent.status == "active"))
```

`list_overseas_applications`: `stmt = stmt.where(OverseasApplication.agent_id.in_(org_member_ids(user)))`

`add_document` agent branch: `linked = await db.scalar(select(AgentStudent.id).where(AgentStudent.student_id == student_id, AgentStudent.agent_id.in_(org_member_ids(user))))`

`download_student_document` agent branch: `assigned = await db.scalar(select(AgentStudent.id).where(AgentStudent.student_id == item.student_id, AgentStudent.agent_id.in_(org_member_ids(user))))`

`agent_students`: `.where(AgentStudent.agent_id.in_(org_member_ids(user)))`

`add_agent_student` — replace the duplicate check block:

```python
    if user.agent_membership is not None:
        await lock_org(db, user.agent_membership.org_id)  # E12: serialise this organisation's links
    existing = await db.scalar(select(AgentStudent.id).where(AgentStudent.agent_id.in_(org_member_ids(user)), AgentStudent.student_id == student.id))
    if existing:
        raise HTTPException(409, "Student is already linked to this agency")
```

`agent_commissions`: `.where(AgentCommission.agent_id.in_(org_member_ids(user)))`

`claim_commission`:

```python
    item = await db.scalar(
        select(AgentCommission).where(AgentCommission.id == commission_id, AgentCommission.agent_id.in_(org_member_ids(user))).with_for_update().execution_options(populate_existing=True)
    )
    if not item:
        raise HTTPException(404, "Commission not found")
```

`apps/api/app/services/portal.py` `_agent` — the three `== user.id` filters become `.in_(org_member_ids(user))` (`AgentStudent.agent_id`, `OverseasApplication.agent_id`, `AgentCommission.agent_id`); import `org_member_ids`.

- [ ] **Step 5: Run — expect PASS.** API(`tests/test_agn_001_tenancy.py`), then **R**.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/agent_orgs.py apps/api/app/api/workflows.py apps/api/app/services/portal.py apps/api/tests/test_agn_001_tenancy.py
git commit -m "feat(agn-001): scope every agent read and write to the caller's organisation"
```

---

### Task 7: Commission notifications reach every active Master

**Files:**
- Modify: `apps/api/app/services/agent_orgs.py` (add `notification_recipients`)
- Modify: `apps/api/app/api/workflows.py` — `_maybe_trigger_agent_commission` (~1731-1733), `create_commission` (~2363)
- Test: `apps/api/tests/test_agn_001_tenancy.py` (append)

**Interfaces:**
- Produces: `async notification_recipients(db, agent: User) -> list[User]`.

- [ ] **Step 1: Append the failing test**

```python
from app.models import Notification  # move to the top import block


@pytest.mark.asyncio
async def test_commission_notifications_reach_every_active_master_and_no_one_else(client, world, db_session):  # AC10
    a, b = world["a"], world["b"]
    second = await _second_master(db_session, a)
    deactivated = await _second_master(db_session, a)
    member = await db_session.scalar(select(AgentOrgMember).where(AgentOrgMember.user_id == deactivated.id))
    member.status = "deactivated"
    # A fresh enrolled application with no commission yet (an application holds at most one commission).
    fresh = OverseasApplication(student_id=a["student"].id, university_id=(await _university(db_session)).id, agent_id=a["master"].id, intake="Jan 2028", status="enrolled")
    db_session.add(fresh)
    await db_session.commit()
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    response = await client.post("/api/v1/workflows/overseas/agent/commissions", json={"agent_id": str(a["master"].id), "application_id": str(fresh.id), "amount": 500})
    assert response.status_code == 201
    recipients = set((await db_session.scalars(select(Notification.user_id).where(Notification.title == "Commission eligible", Notification.user_id.in_([a["master"].id, second.id, deactivated.id, b["master"].id])))).all())
    assert recipients == {a["master"].id, second.id}
```

- [ ] **Step 2: Run — expect FAIL.** API(`tests/test_agn_001_tenancy.py -k notifications`) → recipients `{a.master}` only.

- [ ] **Step 3: Implement** in `apps/api/app/services/agent_orgs.py`:

```python
async def notification_recipients(db: AsyncSession, agent: User) -> list[User]:
    """D12: every active Master of the agent's organisation; the agent alone when it has no membership."""
    org_id = await db.scalar(select(AgentOrgMember.org_id).where(AgentOrgMember.user_id == agent.id))
    if org_id is None:
        return [agent]
    return list(
        (await db.scalars(select(User).join(AgentOrgMember, AgentOrgMember.user_id == User.id).where(AgentOrgMember.org_id == org_id, AgentOrgMember.status == "active").order_by(AgentOrgMember.seq))).all()
    )
```

In `workflows.py`, `_maybe_trigger_agent_commission`:

```python
    agent = await db.get(User, application.agent_id)
    if agent:
        for recipient in await notification_recipients(db, agent):
            await _notify_user(db, recipient, "Commission estimated", "A referred student has enrolled -- a commission is now estimated and awaiting an amount from Overseas Admin.", "/overseas/agent/commissions")
```

`create_commission`:

```python
    for recipient in await notification_recipients(db, agent):
        await _notify_user(db, recipient, "Commission eligible", f"A {payload.currency} {payload.amount:,.2f} commission is available to claim.", "/overseas/agent/commissions")
```

- [ ] **Step 4: Run — expect PASS.** API(`tests/test_agn_001_tenancy.py`), then **R** (`test_agt_003` unedited).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/agent_orgs.py apps/api/app/api/workflows.py apps/api/tests/test_agn_001_tenancy.py
git commit -m "feat(agn-001): commission notifications go to every active Master (D12)"
```

---

### Task 8: Master team API, portal `team` section and dashboard code

**Files:**
- Modify: `apps/api/app/services/agent_orgs.py` (add `invite_master`, `deactivate_master`, `count_active_masters`)
- Create: `apps/api/app/api/agent_team.py`
- Modify: `apps/api/app/main.py:9-30,54` (import and mount `agent_team.router`)
- Modify: `apps/api/app/schemas.py` (add `AgentMasterInvite`)
- Modify: `apps/api/app/services/portal.py` `_agent` (`team` section; dashboard metric)
- Test: `apps/api/tests/test_agn_001_team.py`; `apps/api/tests/test_agn_001_tenancy.py` (append)

**Interfaces:**
- Consumes: `lock_org`, `member_code`, `MASTER_LIMIT` (Tasks 1, 5); `flush_unique_email`, `issue_welcome_token`, `deliver_welcome_link`, `revoke_welcome_tokens`, `provisioning_statuses`, `unusable_password_hash` (provisioning).
- Produces: `GET /api/v1/workflows/overseas/agent/team` → `{org: {id, name, prefix, status}, masters: [{id, code, full_name, email, status, invite_pending, is_you}], limit: 3}`; `POST …/team/masters` → `201 {member: {…same shape…}, email_status, expires_at[, development_welcome_token]}`; `POST …/team/masters/{member_id}/deactivate` → `200 {member: {…}}`.

- [ ] **Step 1: Write the failing tests** `apps/api/tests/test_agn_001_team.py`

```python
import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import AuditLog, PasswordResetToken, User
from tests.agn001_helpers import PASSWORD, client_for, login, membership, mk_active_org, mk_user, org_of, uniq

TEAM = "/api/v1/workflows/overseas/agent/team"
INVITE = TEAM + "/masters"
DEACTIVATE = TEAM + "/masters/{mid}/deactivate"


async def _invite(client, **overrides):
    return await client.post(INVITE, json={"full_name": "Invited Master", "email": f"{uniq('m')}@example.local", **overrides})


@pytest.mark.asyncio
async def test_invite_creates_m002_with_a_welcome_link_and_an_audit_row(client, db_session):  # AC08
    ctx = await mk_active_org(db_session, name="Team Agency")
    await login(client, ctx["master"].email)
    response = await _invite(client)
    assert response.status_code == 201
    body = response.json()
    assert body["member"]["code"] == f"{ctx['org'].prefix}-M002" and body["member"]["invite_pending"] is True and body["member"]["status"] == "active"
    assert body["email_status"] in {"sent", "not_configured", "failed"}
    invited = await db_session.scalar(select(User).where(User.email == body["member"]["email"]))
    assert invited.role == "agent" and invited.division == "overseas" and invited.active is True
    assert await db_session.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == invited.id, PasswordResetToken.purpose == "welcome")) is not None
    log = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_org.master_invite", AuditLog.entity_id == str(ctx["org"].id)))
    assert log.entity_type == "agent_org" and log.user_id == ctx["master"].id
    team = (await client.get(TEAM)).json()
    assert [m["code"] for m in team["masters"]] == [f"{ctx['org'].prefix}-M001", f"{ctx['org'].prefix}-M002"] and team["limit"] == 3


@pytest.mark.asyncio
async def test_the_invited_master_sets_a_password_and_sees_the_org(client, db_session):  # AC08 end to end
    ctx = await mk_active_org(db_session, name="Invite Flow")
    await login(client, ctx["master"].email)
    body = (await _invite(client)).json()
    await client.post("/api/v1/auth/logout")
    assert (await client.post("/api/v1/auth/reset-password", json={"token": body["development_welcome_token"], "new_password": "An0ther-Secret-Pass!"})).status_code == 200
    login_response = await client.post("/api/v1/auth/login", json={"email": body["member"]["email"], "password": "An0ther-Secret-Pass!", "division": "overseas"})
    assert login_response.status_code == 200
    assert (await client.get(TEAM)).json()["org"]["id"] == str(ctx["org"].id)


@pytest.mark.asyncio
async def test_a_fourth_active_master_is_422(client, db_session):  # AC07
    ctx = await mk_active_org(db_session, name="Limit Agency")
    await login(client, ctx["master"].email)
    assert (await _invite(client)).status_code == 201
    assert (await _invite(client)).status_code == 201
    response = await _invite(client)
    assert response.status_code == 422 and response.json()["detail"] == "This agency already has 3 active Masters"


@pytest.mark.asyncio
async def test_an_existing_email_is_409(client, db_session):
    ctx = await mk_active_org(db_session, name="Dup Agency")
    other = await mk_user(db_session, role="overseas_student")
    await login(client, ctx["master"].email)
    response = await _invite(client, email=other.email)
    assert response.status_code == 409 and response.json()["detail"] == "Email already exists"
    assert (await org_of(db_session, ctx["master"].id)).master_seq == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"full_name": "", "email": "x@example.local"}, {"full_name": "A", "email": "not-an-email"}, {"full_name": "A" * 161, "email": "y@example.local"}])
async def test_invalid_invites_are_422(client, db_session, payload):
    ctx = await mk_active_org(db_session, name="Bad Invite")
    await login(client, ctx["master"].email)
    assert (await client.post(INVITE, json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_deactivation_disables_login_revokes_the_link_and_codes_are_never_reused(client, db_session):  # AC07, E3
    ctx = await mk_active_org(db_session, name="Deact Team")
    await login(client, ctx["master"].email)
    second = (await _invite(client)).json()["member"]
    response = await client.post(DEACTIVATE.format(mid=second["id"]))
    assert response.status_code == 200 and response.json()["member"]["status"] == "deactivated"
    user = await db_session.scalar(select(User).where(User.email == second["email"]).execution_options(populate_existing=True))
    assert user.active is False
    token = await db_session.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    assert token.superseded_at is not None
    assert (await client.post(DEACTIVATE.format(mid=second["id"]))).json()["detail"] == "Already deactivated"
    third = (await _invite(client)).json()["member"]
    assert third["code"] == f"{ctx['org'].prefix}-M003"
    assert (await _invite(client)).json()["member"]["code"] == f"{ctx['org'].prefix}-M004"
    assert (await client.post(f"{TEAM}/masters/{second['id']}/reactivate")).status_code == 404  # no reactivation path (D8)


@pytest.mark.asyncio
async def test_the_last_active_master_cannot_be_deactivated(client, db_session):  # AC07
    ctx = await mk_active_org(db_session, name="Last Master")
    await login(client, ctx["master"].email)
    response = await client.post(DEACTIVATE.format(mid=ctx["member"].id))
    assert response.status_code == 422 and response.json()["detail"] == "An agency must keep at least one active Master"


@pytest.mark.asyncio
async def test_a_master_may_deactivate_themselves_when_not_last(client, db_session):
    ctx = await mk_active_org(db_session, name="Self Deact")
    await login(client, ctx["master"].email)
    await _invite(client)
    assert (await client.post(DEACTIVATE.format(mid=ctx["member"].id))).status_code == 200
    assert (await client.get(TEAM)).status_code == 401  # login disabled: next request is refused


@pytest.mark.asyncio
async def test_other_orgs_members_are_404_and_non_agents_are_403(client, db_session):  # AC06/AC08 team routes
    a = await mk_active_org(db_session, name="Team A")
    b = await mk_active_org(db_session, name="Team B")
    await login(client, a["master"].email)
    assert (await client.post(DEACTIVATE.format(mid=b["member"].id))).status_code == 404
    assert (await client.post(DEACTIVATE.format(mid=uuid.uuid4()))).status_code == 404
    assert b["master"].email not in (await client.get(TEAM)).text
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    assert (await client.get(TEAM)).status_code == 403
    assert (await _invite(client)).status_code == 403


@pytest.mark.asyncio
async def test_a_suspended_org_cannot_use_the_team_routes(client, db_session):
    ctx = await mk_active_org(db_session, name="Susp Team")
    ctx["org"].status = "suspended"
    await db_session.commit()
    await login(client, ctx["master"].email)
    assert (await client.get(TEAM)).status_code == 403
    assert (await _invite(client)).status_code == 403


@pytest.mark.asyncio
async def test_two_invites_racing_for_the_last_place_admit_one(db_session):  # race: invite
    ctx = await mk_active_org(db_session, name="Race Invite")
    async with client_for(ctx["master"].email) as c:
        assert (await _invite(c)).status_code == 201
        results = await asyncio.gather(_invite(c), _invite(c))
    assert sorted(r.status_code for r in results) == [201, 422]


@pytest.mark.asyncio
async def test_two_masters_deactivating_each_other_leave_one_active(db_session):  # race: deactivate
    ctx = await mk_active_org(db_session, name="Race Deact")
    async with client_for(ctx["master"].email) as c1:
        second = (await _invite(c1)).json()["member"]
        user = await db_session.scalar(select(User).where(User.email == second["email"]))
        user.password_hash = hash_password(PASSWORD)  # skip the email step: M002 can sign in
        await db_session.commit()
        async with client_for(user.email) as c2:
            results = await asyncio.gather(c1.post(DEACTIVATE.format(mid=second["id"])), c2.post(DEACTIVATE.format(mid=ctx["member"].id)))
    # The org lock serialises the two: the loser sees either the 422 (last Master) or, if the winner deactivated the
    # loser itself first, a 401 (its login is already disabled). Either way exactly one Master stays active.
    assert sorted(r.status_code for r in results) in ([200, 401], [200, 422])
    states = [(await membership(db_session, uid)).status for uid in (ctx["master"].id, user.id)]
    assert states.count("active") == 1


@pytest.mark.asyncio
async def test_two_agencies_inviting_one_email_at_once_is_201_and_409_not_500(db_session):  # Review Focus 4
    # Different organisations hold different locks, so both pass the "email exists?" check; the users.email unique
    # constraint settles it inside flush_unique_email. (Self-registration's own race handling is pre-existing and out
    # of AGN-001's scope.)
    a = await mk_active_org(db_session, name="Email Race A")
    b = await mk_active_org(db_session, name="Email Race B")
    email = f"{uniq('race')}@example.local"
    async with client_for(a["master"].email) as ca, client_for(b["master"].email) as cb:
        results = await asyncio.gather(ca.post(INVITE, json={"full_name": "Racer", "email": email}), cb.post(INVITE, json={"full_name": "Racer", "email": email}))
    assert sorted(r.status_code for r in results) == [201, 409]
    seqs = sorted([(await org_of(db_session, a["master"].id)).master_seq, (await org_of(db_session, b["master"].id)).master_seq])
    assert seqs == [1, 2]  # the loser's master_seq was not advanced


@pytest.mark.asyncio
async def test_the_team_portal_section_lists_only_own_masters(client, db_session):  # AC06 portal team
    a = await mk_active_org(db_session, name="Portal Team A")
    b = await mk_active_org(db_session, name="Portal Team B")
    await login(client, a["master"].email)
    response = await client.get("/api/v1/portal/overseas/agent/team")
    assert response.status_code == 200
    assert [row["code"] for row in response.json()["rows"]] == [a["member"].code]
    assert b["master"].email not in response.text
```

Also append to `test_agn_001_tenancy.py`:

```python
@pytest.mark.asyncio
async def test_the_dashboard_shows_the_callers_code(client, world):
    await login(client, world["a"]["master"].email)
    metrics = (await client.get("/api/v1/portal/overseas/agent/dashboard")).json()["metrics"]
    assert {"label": "Your code", "value": world["a"]["member"].code} in metrics
```

- [ ] **Step 2: Run — expect FAIL.** API(`tests/test_agn_001_team.py`) → 404 on `/team`.

- [ ] **Step 3: Add the schema** to `apps/api/app/schemas.py`:

```python
class AgentMasterInvite(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=320)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("full_name")
    @classmethod
    def full_name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Full name is required")
        return value
```

- [ ] **Step 4: Add the service functions** to `apps/api/app/services/agent_orgs.py` (import `func`, `IssuedWelcome`, `flush_unique_email`, `issue_welcome_token`, `revoke_welcome_tokens`, `unusable_password_hash` from `app.services.provisioning`):

```python
async def count_active_masters(db: AsyncSession, org_id) -> int:
    return await db.scalar(select(func.count()).select_from(AgentOrgMember).where(AgentOrgMember.org_id == org_id, AgentOrgMember.status == "active"))


async def invite_master(db: AsyncSession, org: AgentOrg, actor: User, *, full_name: str, email: str, phone: str | None):
    """No commit; `org` must be locked. D4/D9/E5/E6: a real agent account with an unusable password + a DEC-SCOPE-019
    welcome token; the next code is master_seq + 1."""
    if await count_active_masters(db, org.id) >= MASTER_LIMIT:
        raise HTTPException(422, "This agency already has 3 active Masters")
    email = email.lower().strip()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    now = datetime.now(UTC)
    user = User(email=email, password_hash=unusable_password_hash(), full_name=full_name, role="agent", division="overseas", phone=phone, active=True, email_verified=False, profile={"registration_source": "agent_master_invite"})
    db.add(user)
    await flush_unique_email(db)
    db.add(UserRoleAssignment(user_id=user.id, division="overseas", role="agent", is_active=True, assigned_by_user_id=actor.id, approval_status="approved", approved_by_user_id=actor.id, approved_at=now))
    org.master_seq += 1
    member = AgentOrgMember(org_id=org.id, user_id=user.id, role="master", seq=org.master_seq, code=member_code(org.prefix, org.master_seq), status="active", invited_by_user_id=actor.id)
    db.add(member)
    await db.flush()
    issued = await issue_welcome_token(db, user=user, issued_by=actor)
    db.add(AuditLog(user_id=actor.id, action="agent_org.master_invite", entity_type="agent_org", entity_id=str(org.id), outcome="invited", metadata_json={"member_id": str(member.id), "code": member.code}))
    return member, user, issued


async def deactivate_master(db: AsyncSession, org: AgentOrg, member_id, actor: User) -> tuple[AgentOrgMember, User]:
    """No commit; `org` must be locked. D8/E3: never the last active Master; login disabled; open invite revoked."""
    member = await db.scalar(select(AgentOrgMember).where(AgentOrgMember.id == member_id, AgentOrgMember.org_id == org.id).execution_options(populate_existing=True))
    if not member:
        raise HTTPException(404, "Master not found")
    if member.status != "active":
        raise HTTPException(409, "Already deactivated")
    if await count_active_masters(db, org.id) <= 1:
        raise HTTPException(422, "An agency must keep at least one active Master")
    member.status = "deactivated"
    member.deactivated_at = datetime.now(UTC)
    member.deactivated_by_user_id = actor.id
    target = await db.get(User, member.user_id, populate_existing=True)
    target.active = False
    await revoke_welcome_tokens(db, target.id)
    db.add(AuditLog(user_id=actor.id, action="agent_org.master_deactivate", entity_type="agent_org", entity_id=str(org.id), outcome="deactivated", metadata_json={"member_id": str(member.id), "code": member.code}))
    return member, target
```

Note: `flush_unique_email` rolls back the session on a collision, which also releases the org lock — correct, since the request then ends with 409.

- [ ] **Step 5: Create** `apps/api/app/api/agent_team.py`

```python
"""AGN-001 -- an agency's Master team: list, invite, deactivate (DEC-SCOPE-036 D4, D8, D9; spec §5.4).

Only an active Master of an ACTIVE organisation reaches these routes (same gate as every agent route); every change
locks the organisation row so the 3-Master limit and the last-Master rule hold under concurrency.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rbac import agent_denial_reason
from app.models import AgentOrgMember, User
from app.schemas import AgentMasterInvite
from app.services.agent_orgs import MASTER_LIMIT, deactivate_master, invite_master, lock_org
from app.services.provisioning import deliver_welcome_link, provisioning_statuses

router = APIRouter(prefix="/workflows/overseas/agent/team", tags=["agent-team"])


def _require_master(user: User) -> AgentOrgMember:
    if user.role != "agent" or user.division != "overseas":
        raise HTTPException(403, "This role cannot perform this operation")
    reason = agent_denial_reason(user)
    if reason:
        raise HTTPException(403, reason)
    return user.agent_membership


def _member_out(member: AgentOrgMember, member_user: User, pending: set, caller: User) -> dict:
    return {"id": member.id, "code": member.code, "full_name": member_user.full_name, "email": member_user.email, "status": member.status, "invite_pending": member_user.id in pending, "is_you": member_user.id == caller.id}


async def _locked_active_org(db: AsyncSession, membership: AgentOrgMember):
    org = await lock_org(db, membership.org_id)
    if org.status != "active":  # suspended between the gate check and the lock
        raise HTTPException(403, "Your agency's account is suspended" if org.status == "suspended" else "Agent registration is pending approval")
    return org


@router.get("")
async def team(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _require_master(user)
    org = membership.org
    rows = (await db.execute(select(AgentOrgMember, User).join(User, User.id == AgentOrgMember.user_id).where(AgentOrgMember.org_id == org.id).order_by(AgentOrgMember.seq))).all()
    pending = set(await provisioning_statuses(db, [u.id for _, u in rows]))
    return {"org": {"id": org.id, "name": org.name, "prefix": org.prefix, "status": org.status}, "masters": [_member_out(m, u, pending, user) for m, u in rows], "limit": MASTER_LIMIT}


@router.post("/masters", status_code=201)
async def invite(payload: AgentMasterInvite, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _require_master(user)
    org = await _locked_active_org(db, membership)
    member, invited, issued = await invite_master(db, org, user, full_name=payload.full_name, email=payload.email, phone=payload.phone)
    out = _member_out(member, invited, {invited.id}, user)
    await db.commit()
    delivery = await deliver_welcome_link(user=invited, issued=issued, issued_by=user)
    return {"member": out, **delivery}


@router.post("/masters/{member_id}/deactivate")
async def deactivate(member_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _require_master(user)
    org = await _locked_active_org(db, membership)
    member, target = await deactivate_master(db, org, member_id, user)
    out = _member_out(member, target, set(), user)
    await db.commit()
    return {"member": out}
```

Mount it: in `apps/api/app/main.py` add `agent_team` to the `from app.api import (...)` list and `agent_team.router` to the router tuple (after `workflows.router`).

- [ ] **Step 6: Portal `team` section and dashboard metric** in `services/portal._agent` (import `AgentOrgMember`). In the dashboard metrics tuple, append:

```python
                *(({"label": "Your code", "value": user.agent_membership.code},) if user.agent_membership else ()),
```

and before the `reports` branch add:

```python
    if section == "team":
        membership = user.agent_membership
        rows = (
            (await db.execute(select(AgentOrgMember, User).join(User, User.id == AgentOrgMember.user_id).where(AgentOrgMember.org_id == membership.org_id).order_by(AgentOrgMember.seq))).all()
            if membership
            else []
        )
        return _payload(
            "Team",
            "Your agency's Master accounts (AGN-001). Up to 3 can be active at once.",
            (("code", "Code"), ("name", "Name"), ("email", "Email"), ("status", "Status")),
            ({"code": m.code, "name": u.full_name, "email": u.email, "status": m.status} for m, u in rows),
        )
```

- [ ] **Step 7: Run — expect PASS.** API(`tests/test_agn_001_team.py tests/test_agn_001_tenancy.py`), then **R**. If the deactivate race test observes `[200, 401]` that is the self-lockout ordering (the second request's user was already deactivated before its request read the user) — both outcomes keep exactly one active Master, which the test asserts.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/services/agent_orgs.py apps/api/app/api/agent_team.py apps/api/app/main.py apps/api/app/schemas.py apps/api/app/services/portal.py apps/api/tests/test_agn_001_team.py apps/api/tests/test_agn_001_tenancy.py
git commit -m "feat(agn-001): Master team - list, invite (DEC-SCOPE-019 link), deactivate"
```

---

### Task 9: Registration form — optional agency name

**Files:**
- Modify: `apps/web/components/RegisterForm.tsx`
- Test: `apps/web/tests/components/RegisterForm.test.tsx`

**Interfaces:**
- Consumes: `POST /api/v1/auth/register` `agency_name` (Task 3).

- [ ] **Step 1: Write the failing test** `apps/web/tests/components/RegisterForm.test.tsx`

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RegisterForm from "@/components/RegisterForm";

const { push, refresh } = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function fill() {
  fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Asha Rao" } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "asha@example.local" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Sup3r-Secret-Pass!" } });
}

describe("RegisterForm (AGN-001)", () => {
  it("shows the agency name field only for an education agent", () => {
    render(<RegisterForm division="overseas" />);
    expect(screen.queryByLabelText("Agency name (optional)")).toBeNull();
    fireEvent.change(screen.getByLabelText("Account type"), { target: { value: "agent" } });
    expect(screen.getByLabelText("Agency name (optional)")).toHaveAttribute("maxLength", "160");
  });

  it("sends agency_name for an agent", async () => {
    const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user: { role: "agent" } }), { status: 201 }));
    vi.stubGlobal("fetch", mock);
    render(<RegisterForm division="overseas" />);
    fill();
    fireEvent.change(screen.getByLabelText("Account type"), { target: { value: "agent" } });
    fireEvent.change(screen.getByLabelText("Agency name (optional)"), { target: { value: "ABC Overseas" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/overseas/agent/dashboard"));
    expect(JSON.parse(mock.mock.calls[0][1].body)).toMatchObject({ account_type: "agent", agency_name: "ABC Overseas" });
  });

  it("sends no agency_name for a student", async () => {
    const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user: { role: "overseas_student" } }), { status: 201 }));
    vi.stubGlobal("fetch", mock);
    render(<RegisterForm division="overseas" />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(JSON.parse(mock.mock.calls[0][1].body)).not.toHaveProperty("agency_name");
  });
});
```

- [ ] **Step 2: Run — expect FAIL.** WEB(`tests/components/RegisterForm.test.tsx`) → `getByLabelText("Full name")` fails (labels are not associated with inputs) — the fix below adds `htmlFor`/`id`, which also improves accessibility.

- [ ] **Step 3: Replace** `apps/web/components/RegisterForm.tsx` (same behaviour, labels associated, controlled account type, optional agency name):

```tsx
"use client";
import {FormEvent,useState} from "react";
import {useRouter} from "next/navigation";

function detail(value:unknown){if(typeof value==="string")return value;if(Array.isArray(value))return value.map((item:{msg?:string})=>item.msg||"Invalid input").join("; ");return "Registration failed."}

export default function RegisterForm({division}:{division:"it"|"overseas"}){
  const router=useRouter();const[busy,setBusy]=useState(false);const[message,setMessage]=useState("");const[accountType,setAccountType]=useState("student");
  async function submit(event:FormEvent<HTMLFormElement>){event.preventDefault();setBusy(true);setMessage("");const form=new FormData(event.currentTarget);const agency=String(form.get("agency_name")||"").trim();const body={full_name:form.get("full_name"),email:form.get("email"),phone:form.get("phone")||null,password:form.get("password"),division,account_type:accountType,...(accountType==="agent"&&agency?{agency_name:agency}:{})};const response=await fetch("/api/v1/auth/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const data=await response.json().catch(()=>({}));setBusy(false);if(!response.ok){setMessage(detail(data.detail));return}router.push(data.user.role==="agent"?"/overseas/agent/dashboard":division==="it"?"/it/student/dashboard":"/overseas/student/dashboard");router.refresh()}
  return <form className="form" onSubmit={submit}><div className="field"><label htmlFor="reg-full-name">Full name</label><input id="reg-full-name" name="full_name" autoComplete="name" required/></div><div className="field"><label htmlFor="reg-email">Email</label><input id="reg-email" name="email" type="email" autoComplete="email" required/></div><div className="field"><label htmlFor="reg-phone">Phone</label><input id="reg-phone" name="phone" type="tel" autoComplete="tel"/></div>{division==="overseas"&&<div className="field"><label htmlFor="reg-account-type">Account type</label><select id="reg-account-type" name="account_type" value={accountType} onChange={e=>setAccountType(e.target.value)}><option value="student">Student</option><option value="agent">Education agent</option></select></div>}{division==="overseas"&&accountType==="agent"&&<div className="field"><label htmlFor="reg-agency-name">Agency name (optional)</label><input id="reg-agency-name" name="agency_name" maxLength={160} autoComplete="organization"/></div>}<div className="field"><label htmlFor="reg-password">Password</label><input id="reg-password" name="password" type="password" minLength={10} autoComplete="new-password" required/><span className="muted" style={{fontSize:12}}>Use at least 10 characters.</span></div>{message&&<div className="form-error" role="alert">{message}</div>}<button className="btn" disabled={busy}>{busy?"Creating account…":"Create account"}</button></form>
}
```

(`name="account_type"` stays, so `agt-001-registration-approval.spec.ts`'s `selectOption('select[name="account_type"]', "agent")` keeps working.)

- [ ] **Step 4: Run — expect PASS.** WEB(`tests/components/RegisterForm.test.tsx`).

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/RegisterForm.tsx apps/web/tests/components/RegisterForm.test.tsx
git commit -m "feat(agn-001): optional agency name on agent registration"
```

---

### Task 10: Agent Approvals panel works on organisations

**Files:**
- Modify: `apps/web/components/AgentApprovalPanel.tsx` (rewrite)
- Test: `apps/web/tests/components/AgentApprovalPanel.test.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/overseas-admin/agent-orgs`, `POST /api/v1/overseas-admin/agent-orgs/{id}/{action}` (Task 5).

- [ ] **Step 1: Write the failing test** `apps/web/tests/components/AgentApprovalPanel.test.tsx`

```tsx
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApprovalPanel from "@/components/AgentApprovalPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const master = { id: "m1", code: "ABC-M001", full_name: "Asha Rao", email: "asha@example.local", status: "active" };
const org = (id: string, status: string, name = `Agency ${id}`) => ({ id, name, prefix: "ABC", status, created_at: "2026-09-28T00:00:00Z", masters: [master] });
const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentApprovalPanel (AGN-001)", () => {
  it("shows a loading state, then groups organisations by status with the right actions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok([org("p", "pending"), org("a", "active"), org("s", "suspended"), org("r", "rejected")])));
    render(<AgentApprovalPanel />);
    expect(screen.getByText("Loading agent organisations…")).toBeInTheDocument();
    const pending = await screen.findByRole("region", { name: "Pending" });
    expect(within(pending).getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(within(pending).getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(within(pending).getByText("ABC-M001 · Asha Rao")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Approved" })).getByRole("button", { name: "Suspend" })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Suspended" })).getByRole("button", { name: "Reinstate" })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Rejected" })).getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it("shows an error with a working Retry instead of an empty list", async () => {
    const mock = vi.fn().mockResolvedValueOnce(new Response("{}", { status: 500 })).mockResolvedValueOnce(ok([org("p", "pending")]));
    vi.stubGlobal("fetch", mock);
    render(<AgentApprovalPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("region", { name: "Pending" })).toBeInTheDocument();
  });

  it("shows the empty text when nothing awaits approval", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok([])));
    render(<AgentApprovalPanel />);
    expect(await screen.findByText("No organisations awaiting approval.")).toBeInTheDocument();
  });

  it("asks for confirmation before suspending and ignores repeat clicks", async () => {
    let release!: (r: Response) => void;
    const mock = vi.fn().mockResolvedValueOnce(ok([org("a", "active")])).mockReturnValueOnce(new Promise<Response>((r) => { release = r; })).mockResolvedValue(ok([org("a", "suspended")]));
    vi.stubGlobal("fetch", mock);
    render(<AgentApprovalPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Suspend" }));
    const confirm = screen.getByRole("button", { name: "Confirm suspend" });
    act(() => { fireEvent.click(confirm); fireEvent.click(confirm); });
    expect(mock).toHaveBeenCalledTimes(2);
    expect(mock.mock.calls[1][0]).toBe("/api/v1/overseas-admin/agent-orgs/a/suspend");
    release(ok({ id: "a", status: "suspended" }));
    expect(await screen.findByRole("button", { name: "Reinstate" })).toBeInTheDocument();
  });

  it("shows a server error on the card", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(ok([org("p", "pending")])).mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Cannot approve an organisation that is active" }), { status: 409 })));
    render(<AgentApprovalPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Cannot approve an organisation that is active")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run — expect FAIL.** WEB(`tests/components/AgentApprovalPanel.test.tsx`).

- [ ] **Step 3: Rewrite** `apps/web/components/AgentApprovalPanel.tsx`

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Master = { id: string; code: string; full_name: string; email: string; status: string };
type Org = { id: string; name: string; prefix: string; status: string; created_at: string; masters: Master[] };
type Action = "approve" | "reject" | "suspend" | "reinstate";

// AGN-001 (DEC-SCOPE-036 D6/D7): Overseas Admin acts on the agent ORGANISATION. Active organisations are labelled
// "Approved" -- the admin-facing word, and what agt-001-registration-approval.spec.ts looks for after approving.
const GROUPS: { status: string; label: string; empty: string; actions: Action[] }[] = [
  { status: "pending", label: "Pending", empty: "No organisations awaiting approval.", actions: ["approve", "reject"] },
  { status: "active", label: "Approved", empty: "No approved organisations.", actions: ["suspend"] },
  { status: "suspended", label: "Suspended", empty: "No suspended organisations.", actions: ["reinstate"] },
  { status: "rejected", label: "Rejected", empty: "No rejected organisations.", actions: ["approve"] },
];
const LABEL: Record<Action, string> = { approve: "Approve", reject: "Reject", suspend: "Suspend", reinstate: "Reinstate" };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  return "Unable to complete this action.";
}

export default function AgentApprovalPanel() {
  const router = useRouter();
  const [orgs, setOrgs] = useState<Org[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string } | null>(null);
  const inFlight = useRef<Set<string>>(new Set());

  const load = useCallback(() => {
    setLoadFailed(false);
    fetch("/api/v1/overseas-admin/agent-orgs")
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((rows: Org[]) => setOrgs(rows))
      .catch(() => setLoadFailed(true));
  }, []);

  useEffect(load, [load]);

  async function act(org: Org, action: Action) {
    if (inFlight.current.has(org.id)) return;
    inFlight.current.add(org.id);
    setBusyId(org.id);
    setMessage(null);
    try {
      const response = await fetch(`/api/v1/overseas-admin/agent-orgs/${org.id}/${action}`, { method: "POST" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setMessage({ id: org.id, text: detailMessage(data.detail) });
        return;
      }
      setConfirming(null);
      router.refresh();
      load();
    } finally {
      inFlight.current.delete(org.id);
      setBusyId(null);
    }
  }

  if (loadFailed) {
    return (
      <div className="action-card">
        <h3>Agent Approvals</h3>
        <p className="form-error" role="alert">Unable to load agent organisations.</p>
        <button className="btn secondary small" onClick={load}>Retry</button>
      </div>
    );
  }
  if (orgs === null) {
    return (
      <div className="action-card">
        <h3>Agent Approvals</h3>
        <p className="muted">Loading agent organisations…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Agent Approvals</h3>
      {GROUPS.map((group) => {
        const rows = orgs.filter((o) => o.status === group.status);
        const headingId = `agent-orgs-${group.status}`;
        return (
          <section key={group.status} aria-labelledby={headingId} style={{ marginTop: 16 }}>
            <h4 id={headingId}>{group.label}</h4>
            {rows.length === 0 ? (
              <p className="muted">{group.empty}</p>
            ) : (
              <div className="grid two">
                {rows.map((org) => (
                  <div className="card" key={org.id}>
                    <span className="badge">{group.label}</span>
                    <h4 style={{ marginTop: 10 }}>{org.name} <span className="muted">({org.prefix})</span></h4>
                    <ul style={{ fontSize: 13, paddingLeft: 18 }}>
                      {org.masters.map((m) => (
                        <li key={m.id}>
                          <span>{m.code} · {m.full_name}</span> <span className="muted">{m.email}{m.status !== "active" ? " (deactivated)" : ""}</span>
                        </li>
                      ))}
                    </ul>
                    {confirming === org.id ? (
                      <div role="group" aria-label="Confirm suspension">
                        <p style={{ fontSize: 13 }}>Suspend {org.name}? Every Master loses access on their next request.</p>
                        <button className="btn small" disabled={busyId === org.id} onClick={() => act(org, "suspend")} style={{ marginRight: 8 }}>
                          {busyId === org.id ? "Working…" : "Confirm suspend"}
                        </button>
                        <button className="btn secondary small" disabled={busyId === org.id} onClick={() => setConfirming(null)}>Cancel</button>
                      </div>
                    ) : (
                      group.actions.map((action, i) => (
                        <button
                          key={action}
                          className={i === 0 ? "btn small" : "btn secondary small"}
                          disabled={busyId === org.id}
                          onClick={() => (action === "suspend" ? setConfirming(org.id) : act(org, action))}
                          style={{ marginRight: 8 }}
                        >
                          {busyId === org.id ? "Working…" : LABEL[action]}
                        </button>
                      ))
                    )}
                    {message?.id === org.id && (
                      <div className="form-error" role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>{message.text}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Run — expect PASS.** WEB(`tests/components/AgentApprovalPanel.test.tsx`).

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/AgentApprovalPanel.tsx apps/web/tests/components/AgentApprovalPanel.test.tsx
git commit -m "feat(agn-001): Agent Approvals panel acts on organisations, with error and confirm states"
```

---

### Task 11: Master Team panel, navigation and WorkflowPanel wiring

**Files:**
- Create: `apps/web/components/AgentTeamPanel.tsx`
- Modify: `apps/web/components/WorkflowPanel.tsx` (import; `showAgentTeam` flag; render; the "nothing to show" guard)
- Modify: `apps/web/lib/navigation.ts:75` (add `"team"`)
- Test: `apps/web/tests/components/AgentTeamPanel.test.tsx`

**Interfaces:**
- Consumes: team API (Task 8).

- [ ] **Step 1: Write the failing test** `apps/web/tests/components/AgentTeamPanel.test.tsx`

```tsx
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentTeamPanel from "@/components/AgentTeamPanel";

const { push, refresh } = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

const me = { id: "m1", code: "ABC-M001", full_name: "Asha Rao", email: "asha@example.local", status: "active", invite_pending: false, is_you: true };
const other = { id: "m2", code: "ABC-M002", full_name: "Ravi Iyer", email: "ravi@example.local", status: "active", invite_pending: true, is_you: false };
const team = (masters: unknown[]) => ({ org: { id: "o1", name: "ABC Overseas", prefix: "ABC", status: "active" }, masters, limit: 3 });
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("AgentTeamPanel (AGN-001)", () => {
  it("loads, lists Masters with the invite-pending badge, and hides Deactivate for the last active Master", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(team([me]))));
    render(<AgentTeamPanel />);
    expect(screen.getByText("Loading your team…")).toBeInTheDocument();
    expect(await screen.findByText("ABC-M001")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Deactivate/ })).toBeNull();
  });

  it("shows an error with Retry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({}, 500)).mockResolvedValueOnce(res(team([me]))));
    render(<AgentTeamPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("ABC-M001")).toBeInTheDocument();
  });

  it("disables the invite form at the limit", async () => {
    const third = { ...other, id: "m3", code: "ABC-M003" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(team([me, other, third]))));
    render(<AgentTeamPanel />);
    expect(await screen.findByText("Limit reached: 3 active Masters. Deactivate one to invite another.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send invite" })).toBeDisabled();
  });

  it("invites and reports an undelivered email", async () => {
    const mock = vi.fn()
      .mockResolvedValueOnce(res(team([me])))
      .mockResolvedValueOnce(res({ member: other, email_status: "not_configured" }, 201))
      .mockResolvedValueOnce(res(team([me, other])));
    vi.stubGlobal("fetch", mock);
    render(<AgentTeamPanel />);
    await screen.findByText("ABC-M001");
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Ravi Iyer" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "ravi@example.local" } });
    fireEvent.click(screen.getByRole("button", { name: "Send invite" }));
    expect(await screen.findByText("Invite created, but the email was not delivered. Ask Overseas Admin to re-send the link.")).toBeInTheDocument();
    expect(await screen.findByText("Invite pending")).toBeInTheDocument();
    expect(JSON.parse(mock.mock.calls[1][1].body)).toEqual({ full_name: "Ravi Iyer", email: "ravi@example.local", phone: null });
  });

  it("shows the server's 422 on invite", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res(team([me]))).mockResolvedValueOnce(res({ detail: "This agency already has 3 active Masters" }, 422)));
    render(<AgentTeamPanel />);
    await screen.findByText("ABC-M001");
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "X" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "x@example.local" } });
    fireEvent.click(screen.getByRole("button", { name: "Send invite" }));
    expect(await screen.findByText("This agency already has 3 active Masters")).toBeInTheDocument();
  });

  it("confirms before deactivating, ignores repeat clicks, and shows a race 422", async () => {
    let release!: (r: Response) => void;
    const mock = vi.fn().mockResolvedValueOnce(res(team([me, other]))).mockReturnValueOnce(new Promise<Response>((r) => { release = r; }));
    vi.stubGlobal("fetch", mock);
    render(<AgentTeamPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Ravi Iyer" }));
    const confirm = screen.getByRole("button", { name: "Confirm deactivate" });
    act(() => { fireEvent.click(confirm); fireEvent.click(confirm); });
    expect(mock).toHaveBeenCalledTimes(2);
    release(res({ detail: "An agency must keep at least one active Master" }, 422));
    expect(await screen.findByText("An agency must keep at least one active Master")).toBeInTheDocument();
  });

  it("sends a Master who deactivated themselves to the login page", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res(team([me, other]))).mockResolvedValueOnce(res({ member: { ...me, status: "deactivated" } })));
    render(<AgentTeamPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Asha Rao (you)" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/overseas/login"));
  });
});
```

- [ ] **Step 2: Run — expect FAIL.** WEB(`tests/components/AgentTeamPanel.test.tsx`) → module not found.

- [ ] **Step 3: Create** `apps/web/components/AgentTeamPanel.tsx`

```tsx
"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Master = { id: string; code: string; full_name: string; email: string; status: string; invite_pending: boolean; is_you: boolean };
type Team = { org: { id: string; name: string; prefix: string; status: string }; masters: Master[]; limit: number };

const TEAM_URL = "/api/v1/workflows/overseas/agent/team";

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to complete this action.";
}

// AGN-001 (DEC-SCOPE-036 D4/D8/D9): an agency's Master accounts. Up to 3 active at once; invites use the
// DEC-SCOPE-019 set-password email; the last active Master cannot be deactivated (server-enforced, 422 shown on a race).
export default function AgentTeamPanel() {
  const router = useRouter();
  const [team, setTeam] = useState<Team | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [inviteMessage, setInviteMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowMessage, setRowMessage] = useState<{ id: string; text: string } | null>(null);
  const inFlight = useRef<Set<string>>(new Set());
  const inviteInFlight = useRef(false);

  const load = useCallback(() => {
    setLoadFailed(false);
    fetch(TEAM_URL)
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((body: Team) => setTeam(body))
      .catch(() => setLoadFailed(true));
  }, []);

  useEffect(load, [load]);

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inviteInFlight.current) return;
    inviteInFlight.current = true;
    setInviting(true);
    setInviteMessage(null);
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const response = await fetch(`${TEAM_URL}/masters`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: form.get("full_name"), email: form.get("email"), phone: form.get("phone") || null }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setInviteMessage({ text: detailMessage(data.detail), failed: true });
        return;
      }
      formElement.reset();
      setInviteMessage(
        data.email_status === "sent"
          ? { text: "Invite sent.", failed: false }
          : { text: "Invite created, but the email was not delivered. Ask Overseas Admin to re-send the link.", failed: true },
      );
      load();
    } finally {
      inviteInFlight.current = false;
      setInviting(false);
    }
  }

  async function deactivate(master: Master) {
    if (inFlight.current.has(master.id)) return;
    inFlight.current.add(master.id);
    setBusyId(master.id);
    setRowMessage(null);
    try {
      const response = await fetch(`${TEAM_URL}/masters/${master.id}/deactivate`, { method: "POST" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setRowMessage({ id: master.id, text: detailMessage(data.detail) });
        return;
      }
      setConfirming(null);
      if (master.is_you) {
        router.push("/overseas/login");
        return;
      }
      router.refresh();
      load();
    } finally {
      inFlight.current.delete(master.id);
      setBusyId(null);
    }
  }

  if (loadFailed) {
    return (
      <div className="action-card">
        <h3>Team</h3>
        <p className="form-error" role="alert">Unable to load your team.</p>
        <button className="btn secondary small" onClick={load}>Retry</button>
      </div>
    );
  }
  if (team === null) {
    return (
      <div className="action-card">
        <h3>Team</h3>
        <p className="muted">Loading your team…</p>
      </div>
    );
  }

  const active = team.masters.filter((m) => m.status === "active");
  const atLimit = active.length >= team.limit;

  return (
    <div className="action-card">
      <h3>Team — {team.org.name}</h3>
      <ul style={{ paddingLeft: 0, listStyle: "none" }}>
        {team.masters.map((m) => (
          <li className="card" key={m.id} style={{ marginBottom: 8 }}>
            <strong>{m.code}</strong> {m.full_name}{m.is_you ? " (you)" : ""} <span className="muted" style={{ fontSize: 13 }}>{m.email}</span>{" "}
            {m.status !== "active" ? <span className="badge">Deactivated</span> : m.invite_pending ? <span className="badge">Invite pending</span> : null}
            {m.status === "active" && active.length > 1 && (
              confirming === m.id ? (
                <div role="group" aria-label={`Confirm deactivating ${m.full_name}`} style={{ marginTop: 8 }}>
                  <p style={{ fontSize: 13 }}>{m.is_you ? "Deactivate your own account? You will be signed out." : `Deactivate ${m.full_name}? They will no longer be able to sign in.`}</p>
                  <button className="btn small" disabled={busyId === m.id} onClick={() => deactivate(m)} style={{ marginRight: 8 }}>
                    {busyId === m.id ? "Working…" : "Confirm deactivate"}
                  </button>
                  <button className="btn secondary small" disabled={busyId === m.id} onClick={() => setConfirming(null)}>Cancel</button>
                </div>
              ) : (
                <button className="btn secondary small" aria-label={`Deactivate ${m.full_name}${m.is_you ? " (you)" : ""}`} onClick={() => setConfirming(m.id)} style={{ marginLeft: 8 }}>
                  Deactivate
                </button>
              )
            )}
            {rowMessage?.id === m.id && <div className="form-error" role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>{rowMessage.text}</div>}
          </li>
        ))}
      </ul>
      <form className="form" onSubmit={invite} aria-label="Invite a Master">
        <h4>Invite a Master</h4>
        {atLimit && <p className="muted">Limit reached: {team.limit} active Masters. Deactivate one to invite another.</p>}
        <div className="field"><label htmlFor="team-full-name">Full name</label><input id="team-full-name" name="full_name" maxLength={160} required disabled={atLimit} /></div>
        <div className="field"><label htmlFor="team-email">Email</label><input id="team-email" name="email" type="email" maxLength={320} required disabled={atLimit} /></div>
        <div className="field"><label htmlFor="team-phone">Phone (optional)</label><input id="team-phone" name="phone" type="tel" maxLength={40} disabled={atLimit} /></div>
        <button className="btn" disabled={atLimit || inviting}>{inviting ? "Sending…" : "Send invite"}</button>
        {inviteMessage && <div className={inviteMessage.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>{inviteMessage.text}</div>}
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Wire it.** In `apps/web/components/WorkflowPanel.tsx`: add `import AgentTeamPanel from "./AgentTeamPanel";` beside the other agent panel imports; after `const showAgentApplicationCreate = …` add `const showAgentTeam = user.role === "agent" && section === "team";`; append `&& !showAgentTeam` to the "nothing to show" guard condition; render `{showAgentTeam && <AgentTeamPanel/>}` right after `{showAgentApplicationCreate && <AgentApplicationCreatePanel/>}`. In `apps/web/lib/navigation.ts:75` change the agent list to `["dashboard","students","applications","documents","commissions","reports","team"]`.

- [ ] **Step 5: Run — expect PASS.** WEB(`tests/components/AgentTeamPanel.test.tsx tests/components/WorkflowPanel.create-user.test.tsx tests/components/WorkflowPanel.expired-links.test.tsx`), then the whole web unit suite `WEB()` (no argument) and `npx tsc --noEmit` in the web-test container.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/AgentTeamPanel.tsx apps/web/components/WorkflowPanel.tsx apps/web/lib/navigation.ts apps/web/tests/components/AgentTeamPanel.test.tsx
git commit -m "feat(agn-001): Team screen - Masters list, invite, deactivate"
```

---

### Task 12: End-to-end spec

**Files:**
- Create: `apps/web/tests/e2e/agn-001-multi-tenant.spec.ts`

**Interfaces:**
- Consumes: the whole feature on the running stack (seeded `overseasadmin@edusphere.local` / `Demo@123`).

- [ ] **Step 1: Write the spec**

```ts
import { test, expect, type Page } from "@playwright/test";

// AGN-001 -- agency registration -> approval -> Master invite -> suspend -> reinstate, through the real UI.
// Requires the stack running with `python -m app.seed` applied (seeds the overseas admin).

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function adminAct(page: Page, agency: string, button: string) {
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/agents");
  const card = page.locator(".card", { hasText: agency });
  await card.getByRole("button", { name: button }).click();
  if (button === "Suspend") await card.getByRole("button", { name: "Confirm suspend" }).click();
}

test("an agency registers, is approved, invites a second Master, and is suspended then reinstated (AGN-001)", async ({ page }) => {
  const unique = Date.now();
  const agency = `Kappa Overseas ${unique}`;
  const email = `agn001-e2e-${unique}@example.local`;

  await page.goto("/overseas/register");
  await page.fill('input[name="full_name"]', "Kappa Master");
  await page.fill('input[name="email"]', email);
  await page.selectOption('select[name="account_type"]', "agent");
  await page.fill('input[name="agency_name"]', agency);
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/overseas/agent/dashboard");
  await expect(page.getByText(/pending approval/)).toBeVisible();

  await adminAct(page, agency, "Approve");
  await expect(page.locator(".card", { hasText: agency }).getByText("Approved")).toBeVisible();

  await signIn(page, email, "Sup3r-Secret-Pass!", "/overseas/agent/dashboard");
  await expect(page.getByText(/KAP\d*-M001/)).toBeVisible();
  await page.goto("/overseas/agent/team");
  await page.getByLabel("Full name").fill("Kappa Second");
  await page.getByLabel("Email").fill(`agn001-e2e-m2-${unique}@example.local`);
  await page.getByRole("button", { name: "Send invite" }).click();
  await expect(page.getByText(/KAP\d*-M002/).first()).toBeVisible();
  await expect(page.getByText("Invite pending").first()).toBeVisible();

  await adminAct(page, agency, "Suspend");
  await signIn(page, email, "Sup3r-Secret-Pass!", "/overseas/agent/dashboard");
  await expect(page.getByText("Your agency's account is suspended")).toBeVisible();

  await adminAct(page, agency, "Reinstate");
  await signIn(page, email, "Sup3r-Secret-Pass!", "/overseas/agent/dashboard");
  await expect(page.getByRole("heading", { name: "Access unavailable" })).not.toBeVisible();
});
```

- [ ] **Step 2: Run against the user-started stack** (rebuilt from this branch; the user starts it): `npx playwright test tests/e2e/agn-001-multi-tenant.spec.ts tests/e2e/agt-001-registration-approval.spec.ts tests/e2e/agt-002-referrals.spec.ts tests/e2e/agt-003-commission-accrual.spec.ts tests/e2e/agt-004-commission-payout.spec.ts tests/e2e/adm-001-admin-crud.spec.ts` — all PASS, the `agt-*`/`adm-001` specs unedited. On failure, open only that test's trace.

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/agn-001-multi-tenant.spec.ts
git commit -m "test(agn-001): end-to-end agency lifecycle"
```

---

### Task 13: Docs, full gates, browser check

**Files:**
- Modify: `docs/architecture/DATA_MODEL.md` §6.8a (planned → built: real table/column names, migration `0045`)
- Modify: `docs/architecture/API_CONTRACT.md` §8 AGN-001 block (real paths and shapes from Tasks 5 and 8)
- Modify: `docs/architecture/RBAC_MATRIX.md` §2.8 AGN-001 note ("NOT YET BUILT" → built; team routes)
- Modify: `docs/ux/SCREEN_CATALOG.md`, `docs/ux/screen_catalog.json`, `docs/ux/ROLE_NAVIGATION.md` (new `SCR-AGT-` Team screen, next free ID; Agent Approvals screen note)
- Modify: `docs/quality/RTM.md` AGN-001 row (evidence), `docs/delivery/ENHANCEMENT_BACKLOG.md` AGN-001 status

- [ ] **Step 1: Update the docs** listed above with the as-built facts only (no claims not backed by a run). Record the follow-up found while planning: the admin portal's generic "Agent Registrations" table (`services/portal.py` `agents` section) still shows the assignment's `approval_status`, so a suspended organisation reads "approved" there; the Agent Approvals panel above it is correct. Out of AGN-001's approved scope — logged, not changed.

- [ ] **Step 2: Full backend suite.** `dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test python -m pytest -q` — expected: only the 14 known provider-credential failures (Razorpay/Zoho, empty CI keys); anything else is investigated with superpowers:systematic-debugging before continuing.

- [ ] **Step 3: Web gates.** In the web-test container: `npx vitest run` (all pass), `npx tsc --noEmit` (exit 0), `npx eslint .` (0 errors; no new warnings in changed files), `npm run build` (exit 0).

- [ ] **Step 4: Migration gates.** `alembic heads` → exactly `0046_agent_orgs`; Task 2 Step 7's round trip recorded.

- [ ] **Step 5: Full e2e suite** on the user-started stack; compare against the `main` baseline; only pre-existing failures (e.g. `enh-022:43`, `sch-004:13` recorded on `main`) may remain.

- [ ] **Step 6: Browser check** (webapp-testing / Playwright screenshots) at 320, 768, 1280 px: register (agent + agency name), pending message, Agent Approvals (all four groups, confirm suspend, error state via stopped API), Team (list, invite, limit, deactivate confirm, self-deactivate redirect), suspended message. No horizontal scroll; every control reachable by keyboard; status messages announced. Fix defects test-first; record results in the RTM.

- [ ] **Step 7: Commit**

```bash
git add docs/
git commit -m "docs(agn-001): as-built data model, API, RBAC, screens and RTM evidence"
```
