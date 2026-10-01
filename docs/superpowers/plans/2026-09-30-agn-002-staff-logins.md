# AGN-002 Agent Staff Logins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an agency's Master create, edit, deactivate, reactivate and reset staff logins (codes `<PREFIX>-S###`), with staff limited to the organisation's students and applications.

**Architecture:** Staff are `role='agent'` users with an `AgentOrgMember(role='staff')` row (migration `0047`), numbered from a new `agent_orgs.staff_seq` under the existing organisation row lock. New staff functions live in `services/agent_orgs.py`; new routes in `api/agent_team.py`; the Master-only points (team, commissions, Master rules, admin lists) check `rbac.is_agent_staff`. Sessions end on reset/deactivation through a `users.session_version` counter carried as the `sv` token claim. Frontend adds three small components beside `AgentTeamPanel`, reusing `sendJson`/`isPage` and the existing CSS classes.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, PostgreSQL 16; Next.js (App Router), React, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-30-agn-002-staff-logins-design.md` (read it with this plan). Decision: `DEC-SCOPE-040` (S1–S6) + spec E1–E7.

## Global Constraints

- Scope is AGN-002 only (spec §2). No change to change-password / forgot-password, admin `PATCH /users` (E4), Master reactivation (D8), organisation transitions, or any non-agent route.
- No new dependency (Python or npm).
- Existing tests and e2e specs are **not edited**, with exactly two recorded exceptions (see Deviations). Any other existing test failing is a regression signal: stop and report.
- Migration `0047_agent_org_staff` is additive (two columns with server defaults, two constraints widened); no row changes; `downgrade()` refuses while staff exist.
- Codes: Master `f"{prefix}-M{seq:03d}"` (unchanged), staff `f"{prefix}-S{seq:03d}"`. Numbers are never reused.
- Limits: staff creations + rejected creations + resets ≤ `20` per agency per rolling 24 h; Master invites keep `10`; per-account reset cooldown = existing `RESEND_COOLDOWN_SECONDS` (60).
- Messages (verbatim):
  - "Only an agency Master can manage the team" · "Only an agency Master can view commissions" · "Only an agency Master can open this page"
  - "Staff member not found" · "Already deactivated" · "Already active" · "Reactivate this staff member first" · "Email already exists" · "Nothing to update" · "Full name is required"
  - throttle: `f"This agency has created or reset {STAFF_ACTION_LIMIT} staff logins in the last 24 hours. Try again later."`
  - reset cooldown: `f"A link was just sent; wait {wait} seconds before resetting again"`
  - sessions: "Session ended"
  - admin: "Staff accounts are managed by their agency"
- Audit rows: `action` `agent_org.staff_create|staff_create_rejected|staff_update|staff_deactivate|staff_reactivate|staff_reset`, `entity_type="agent_org"`, `entity_id=str(org.id)`, `metadata_json` with `member_id` and `code` (update adds `fields`); never an email, password or token.
- Operational logs: `app.agent_orgs` logger, `extra={"extra_fields": {...}}` with ids/codes only (existing pattern).
- Lock order: organisation row (`lock_org`) → target user row (`FOR UPDATE`) → tokens. Welcome-link order: create/reset + `issue_welcome_token` + audit → **commit** → `deliver_welcome_link`.
- Test-module imports are kept at the top of each file (ruff clean, no suppressions).

## Deviations from the spec / existing tests (record in the RTM)

- **`tests/test_agn_001_schema.py` is edited in two places (Task 1)**, both forced by the approved decision: the head pin `"0046_agent_orgs"` becomes "one head, and `0046_agent_orgs` is in the chain" (the relaxation ENH-013/ENH-025/ENH-027 received), and `{"role": "staff"}` leaves the "bad member values" parametrisation (staff is now valid; `{"role": "owner"}` replaces it so the check is still exercised).
- **E2E activation of a staff account uses the admin Re-send route** (`POST /admin/users/{id}/welcome-links` as the seeded Overseas Admin returns `development_welcome_token` in dev/test) because the staff-create response never carries the token (S3). No product change.

## Test commands (PowerShell, from the worktree root)

Isolated Compose project `agn002`. **The user builds and starts the stack** (standing preference); the agent only runs one-off `run --rm` containers that mount this worktree's source.

```powershell
# User, once:
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn002 --profile ci build api-test web-test
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn002 --profile ci up -d --wait postgres redis

# Agent:
function dc { docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn002 --profile ci @args }
dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test alembic upgrade head
dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test python -m pytest -q tests/test_agn_002_staff.py
dc run --rm --no-deps -v "${PWD}\apps\web\components:/app/components" -v "${PWD}\apps\web\lib:/app/lib" -v "${PWD}\apps\web\tests:/app/tests" -v "${PWD}\apps\web\app:/app/app" web-test npx vitest run tests/components/AgentStaffPanel.test.tsx
```

Below, **API(x)** = the pytest command with `x` as its arguments; **WEB(x)** = the vitest command; **MIGRATE** = `alembic upgrade head`; **LINT** = `dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test ruff check app tests`.

**Regression set R** (must stay green after every backend task): API(`tests/test_agn_001_team.py tests/test_agn_001_tenancy.py tests/test_agn_001_registration_and_gate.py tests/test_agn_001_org_admin.py tests/test_agn_001_prefix.py tests/test_agn_001_schema.py tests/test_agt_001_registration_approval.py tests/test_agt_002_referrals.py tests/test_agt_003_commission_accrual.py tests/test_agt_004_commission_payout.py tests/test_enh_003_first_time_provisioning.py tests/test_sec_001_audit_trail.py`) plus every `tests/test_enh_006_*.py` (change-password, touches sessions).

## Review Focus

1. **A staff member's browser still holding pre-reset or pre-deactivation cookies** — every request and `/auth/refresh` must be `401`, including after reactivation; a user who never had staff changes (no `sv` claim in old cookies) must stay signed in. Task 2 tests legacy tokens; Task 5 tests post-reactivation cookies.
2. **Two Masters of one agency adding staff at the same moment** — distinct codes, never a 500, `staff_seq` equals the number of staff. Task 4 race test.
3. **A Master of agency A using a member id from agency B, or a Master's own id, on every staff route** — always `404 "Staff member not found"`, nothing changed. Task 5 test loops all four mutating routes.
4. **The email failing to send on create or reset** — the account/reset stays committed, the response says so, and the UI tells the Master to use Reset. Tasks 4 (API) and 8/9 (UI).
5. **The Team screen on a phone and by keyboard** — long names/emails wrap, all actions reachable by Tab, Escape cancels edit, confirmations return focus, every result announced. Tasks 8–10 tests + browser validation.

---

### Task 1: Migration `0047`, model columns and constraints

**Files:**
- Create: `apps/api/alembic/versions/0047_agent_org_staff.py`
- Modify: `apps/api/app/models.py` (class `User` near `agent_membership`; classes `AgentOrg`, `AgentOrgMember` ~L852–892)
- Modify (recorded deviation): `apps/api/tests/test_agn_001_schema.py`
- Test: `apps/api/tests/test_agn_002_schema.py`

**Interfaces:**
- Produces: `AgentOrg.staff_seq: int`, `User.session_version: int`, member role `"master" | "staff"`, unique `(org_id, role, seq)`; migration function `assert_no_staff(bind)`.

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_agn_002_schema.py`

```python
"""AGN-002 -- migration 0047: staff members, per-role numbering, staff counter, session version (spec §4)."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.models import AgentOrg, AgentOrgMember, User
from tests.agn001_helpers import mk_user

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_002_migration_0047", VERSIONS / "0047_agent_org_staff.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def _org(**overrides) -> AgentOrg:
    return AgentOrg(**{"name": "Staff Chk", "prefix": f"Q{uuid.uuid4().hex[:6].upper()}", "status": "active", "master_seq": 1, **overrides})


def test_migration_follows_0046_and_is_the_single_head():
    assert _migration.revision == "0047_agent_org_staff"
    assert _migration.down_revision == "0046_agent_orgs"
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        parent = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
        if rev:
            parents[rev] = parent
    assert len(set(parents) - set(parents.values())) == 1


@pytest.mark.asyncio
async def test_new_columns_default_to_zero(db_session):
    user = await mk_user(db_session, role="agent")
    org = _org()
    db_session.add(org)
    await db_session.commit()
    assert (await db_session.get(User, user.id, populate_existing=True)).session_version == 0
    assert (await db_session.get(AgentOrg, org.id, populate_existing=True)).staff_seq == 0

    def _cols(sync_conn):
        return {t: {c["name"]: c for c in inspect(sync_conn).get_columns(t)} for t in ("users", "agent_orgs")}

    cols = await (await db_session.connection()).run_sync(_cols)
    assert cols["users"]["session_version"]["nullable"] is False
    assert cols["agent_orgs"]["staff_seq"]["nullable"] is False


@pytest.mark.asyncio
async def test_a_staff_member_and_a_master_may_share_a_number(db_session):
    master, staff = await mk_user(db_session, role="agent"), await mk_user(db_session, role="agent")
    org = _org(staff_seq=1)
    db_session.add(org)
    await db_session.flush()
    db_session.add_all([
        AgentOrgMember(org_id=org.id, user_id=master.id, role="master", seq=1, code=f"{org.prefix}-M001", status="active"),
        AgentOrgMember(org_id=org.id, user_id=staff.id, role="staff", seq=1, code=f"{org.prefix}-S001", status="active"),
    ])
    await db_session.commit()


@pytest.mark.asyncio
async def test_two_staff_members_may_not_share_a_number(db_session):
    a, b = await mk_user(db_session, role="agent"), await mk_user(db_session, role="agent")
    org = _org(staff_seq=1)
    db_session.add(org)
    await db_session.flush()
    db_session.add(AgentOrgMember(org_id=org.id, user_id=a.id, role="staff", seq=1, code=f"{org.prefix}-S001", status="active"))
    await db_session.flush()
    db_session.add(AgentOrgMember(org_id=org.id, user_id=b.id, role="staff", seq=1, code=f"{org.prefix}-S001X", status="active"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_staff_seq_cannot_be_negative(db_session):
    db_session.add(_org(staff_seq=-1))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_downgrade_guard_refuses_while_staff_exist(db_session):
    staff = await mk_user(db_session, role="agent")
    org = _org(staff_seq=1)
    db_session.add(org)
    await db_session.flush()
    db_session.add(AgentOrgMember(org_id=org.id, user_id=staff.id, role="staff", seq=1, code=f"{org.prefix}-S001", status="active"))
    await db_session.commit()
    conn = await db_session.connection()
    with pytest.raises(RuntimeError, match="staff members exist"):
        await conn.run_sync(_migration.assert_no_staff)
    assert await db_session.scalar(text("SELECT count(*) FROM agent_org_members WHERE role = 'staff'")) >= 1
```

- [ ] **Step 2: Run it** — API(`tests/test_agn_002_schema.py`). Expected: FAIL at collection — `FileNotFoundError` for `0047_agent_org_staff.py`.

- [ ] **Step 3: Write the migration** — `apps/api/alembic/versions/0047_agent_org_staff.py`

```python
"""AGN-002 -- staff members of an agent organisation, and a per-user session version.

Revision ID: 0047_agent_org_staff
Revises: 0046_agent_orgs

docs/superpowers/specs/2026-09-30-agn-002-staff-logins-design.md §4 (DEC-SCOPE-040). Additive: `agent_orgs.staff_seq` and
`users.session_version` (server default 0, so no backfill), the member role check widened to master|staff, and member numbers
made unique per role (M001 and S001 coexist). No existing row changes. The columns are only added when missing, so a database
whose schema was created by `auto_create_schema` still upgrades. `downgrade()` refuses while a staff member exists: it never
silently deletes logins.
"""

import sqlalchemy as sa

from alembic import op

revision = "0047_agent_org_staff"
down_revision = "0046_agent_orgs"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    if op.get_context().as_sql:
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def assert_no_staff(bind) -> None:
    if bind.execute(sa.text("SELECT 1 FROM agent_org_members WHERE role = 'staff' LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0047_agent_org_staff: staff members exist. Remove them deliberately first.")


def upgrade() -> None:
    if "staff_seq" not in _columns("agent_orgs"):
        op.add_column("agent_orgs", sa.Column("staff_seq", sa.Integer(), nullable=False, server_default="0"))
        op.create_check_constraint("ck_agent_orgs_staff_seq", "agent_orgs", "staff_seq >= 0")
    op.drop_constraint("ck_agent_org_members_role", "agent_org_members", type_="check")
    op.create_check_constraint("ck_agent_org_members_role", "agent_org_members", "role IN ('master', 'staff')")
    op.drop_constraint("uq_agent_org_members_org_seq", "agent_org_members", type_="unique")
    op.create_unique_constraint("uq_agent_org_members_org_role_seq", "agent_org_members", ["org_id", "role", "seq"])
    if "session_version" not in _columns("users"):
        op.add_column("users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    assert_no_staff(op.get_bind())
    op.drop_column("users", "session_version")
    op.drop_constraint("uq_agent_org_members_org_role_seq", "agent_org_members", type_="unique")
    op.create_unique_constraint("uq_agent_org_members_org_seq", "agent_org_members", ["org_id", "seq"])
    op.drop_constraint("ck_agent_org_members_role", "agent_org_members", type_="check")
    op.create_check_constraint("ck_agent_org_members_role", "agent_org_members", "role = 'master'")
    op.drop_constraint("ck_agent_orgs_staff_seq", "agent_orgs", type_="check")
    op.drop_column("agent_orgs", "staff_seq")
```

- [ ] **Step 4: Update the models** — `apps/api/app/models.py`

In `class User`, directly after the `agent_membership` relationship:

```python
    # AGN-002 (DEC-SCOPE-040 S3, spec §5): copied into every token as `sv`; a staff reset or deactivation increments it, which ends
    # every session issued before. Tokens without the claim count as 0.
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
```

In `class AgentOrg`: docstring appends "`staff_seq` is the highest staff number ever issued (AGN-002)."; `__table_args__` gains `CheckConstraint("staff_seq >= 0", name="ck_agent_orgs_staff_seq"),`; add after `master_seq`:

```python
    staff_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
```

In `class AgentOrgMember`: docstring becomes `"""AGN-001: a user's membership of exactly one agent organisation, for good (`user_id` unique). AGN-002 adds `staff` (DEC-SCOPE-040): Masters and staff are numbered separately (M001 and S001 coexist)."""`; replace the two constraints:

```python
        UniqueConstraint("org_id", "role", "seq", name="uq_agent_org_members_org_role_seq"),
        CheckConstraint("role IN ('master', 'staff')", name="ck_agent_org_members_role"),
```

- [ ] **Step 5: Edit `test_agn_001_schema.py` (recorded deviation)** — in `test_alembic_head_is_0046`, rename to `test_alembic_head_is_the_single_head_and_includes_0046` and replace the assertion with:

```python
    head = await db_session.scalar(text("SELECT version_num FROM alembic_version"))
    assert head == script.get_current_head()
    # AGN-002 chained 0047 after 0046: keep the intent (0046 applied, one head) without pinning the head.
    assert "0046_agent_orgs" in {rev.revision for rev in script.walk_revisions()}
```

and in `test_member_checks_reject_bad_values` change the parametrisation to `[{"role": "owner"}, {"status": "invited"}]`.

- [ ] **Step 6: Run** — MIGRATE, then API(`tests/test_agn_002_schema.py tests/test_agn_001_schema.py`). Expected: all PASS.

- [ ] **Step 7: Regression + lint** — API(R), LINT. Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/api/alembic/versions/0047_agent_org_staff.py apps/api/app/models.py apps/api/tests/test_agn_002_schema.py apps/api/tests/test_agn_001_schema.py
git commit -m "feat(agn-002): migration 0047 -- staff members, staff counter, session version"
```

---

### Task 2: Session version on tokens

**Files:**
- Modify: `apps/api/app/core/security.py` (`create_token`)
- Modify: `apps/api/app/api/auth.py` (`_set_auth_cookies`, `refresh`)
- Modify: `apps/api/app/api/deps.py` (`get_current_user`)
- Test: `apps/api/tests/test_agn_002_sessions.py`

**Interfaces:**
- Consumes: `User.session_version` (Task 1).
- Produces: `create_token(subject, role, division, token_type="access", session_version=0) -> str` with claim `sv`; both auth dependencies reject a mismatched `sv` with `401 "Session ended"`.

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_agn_002_sessions.py`

```python
"""AGN-002 -- session version (spec §5, E1): a bumped users.session_version ends every older session; legacy tokens still work."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import update

from app.core.config import settings
from app.core.security import ALGORITHM, create_token, decode_token
from app.models import User
from tests.agn001_helpers import login, mk_user


def _legacy_token(user: User, token_type: str) -> str:
    """A token minted the way every token was before AGN-002: no `sv` claim."""
    exp = datetime.now(UTC) + timedelta(minutes=5)
    return jwt.encode({"sub": str(user.id), "role": user.role, "division": user.division, "type": token_type, "exp": exp}, settings.secret_key, algorithm=ALGORITHM)


def test_create_token_carries_the_session_version():
    assert decode_token(create_token("u", "agent", "overseas", "access", session_version=3))["sv"] == 3
    assert decode_token(create_token("u", "agent", "overseas"))["sv"] == 0


@pytest.mark.asyncio
async def test_a_token_without_sv_still_works(client, db_session):
    user = await mk_user(db_session, role="overseas_student")
    client.cookies.set("edusphere_access", _legacy_token(user, "access"))
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    client.cookies.set("edusphere_refresh", _legacy_token(user, "refresh"))
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200


@pytest.mark.asyncio
async def test_bumping_the_version_ends_access_and_refresh(client, db_session):
    user = await mk_user(db_session, role="overseas_student")
    await login(client, user.email)
    old_access, old_refresh = client.cookies.get("edusphere_access"), client.cookies.get("edusphere_refresh")
    await db_session.execute(update(User).where(User.id == user.id).values(session_version=User.session_version + 1))
    await db_session.commit()
    client.cookies.set("edusphere_access", old_access)
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 401 and me.json()["detail"] == "Session ended"
    client.cookies.set("edusphere_refresh", old_refresh)
    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 401 and refreshed.json()["detail"] == "Session ended"


@pytest.mark.asyncio
async def test_signing_in_again_after_a_bump_works_immediately(client, db_session):
    user = await mk_user(db_session, role="overseas_student")
    await db_session.execute(update(User).where(User.id == user.id).values(session_version=5))
    await db_session.commit()
    await login(client, user.email)
    assert decode_token(client.cookies.get("edusphere_access"))["sv"] == 5
    assert (await client.get("/api/v1/auth/me")).status_code == 200
```

- [ ] **Step 2: Run it** — API(`tests/test_agn_002_sessions.py`). Expected: FAIL — `TypeError: create_token() got an unexpected keyword argument 'session_version'` and `KeyError: 'sv'`; the bump test returns `200` instead of `401`.

- [ ] **Step 3: Implement**

`apps/api/app/core/security.py`:

```python
def create_token(subject: str, role: str, division: str, token_type: str = "access", session_version: int = 0) -> str:
    """AGN-002: `sv` is the user's session version at issue time; `deps.get_current_user` and `/auth/refresh` refuse a token whose
    `sv` no longer matches, so incrementing `users.session_version` ends every older session."""
    exp = datetime.now(UTC) + (timedelta(days=settings.refresh_token_days) if token_type == "refresh" else timedelta(minutes=settings.access_token_minutes))
    return jwt.encode({"sub": subject, "role": role, "division": division, "type": token_type, "exp": exp, "sv": session_version}, settings.secret_key, algorithm=ALGORITHM)
```

`apps/api/app/api/auth.py` — `_set_auth_cookies`:

```python
    access = create_token(str(user.id), user.role, user.division, "access", user.session_version)
    refresh = create_token(str(user.id), user.role, user.division, "refresh", user.session_version)
```

`refresh`, after `if not user: raise HTTPException(401, "User unavailable")`:

```python
    if p.get("sv", 0) != user.session_version:  # AGN-002: ended by a staff reset or deactivation
        raise HTTPException(401, "Session ended")
```

`apps/api/app/api/deps.py` — after `if not user: raise HTTPException(401, "User unavailable")`:

```python
    # AGN-002 (spec §5): a token issued before the user's session version was incremented (staff reset / deactivation) is refused.
    # Tokens from before AGN-002 carry no `sv` and count as 0, the column's default.
    if p.get("sv", 0) != user.session_version:
        raise HTTPException(401, "Session ended")
```

- [ ] **Step 4: Run** — API(`tests/test_agn_002_sessions.py`). Expected: PASS.

- [ ] **Step 5: Regression + lint** — API(R), LINT. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/core/security.py apps/api/app/api/auth.py apps/api/app/api/deps.py apps/api/tests/test_agn_002_sessions.py
git commit -m "feat(agn-002): session version claim ends older sessions"
```

---

### Task 3: Master-only rules ignore staff; staff blocked from team routes

**Files:**
- Create: `apps/api/tests/agn002_helpers.py`
- Modify: `apps/api/app/core/rbac.py` (add `is_agent_staff`)
- Modify: `apps/api/app/services/agent_orgs.py` (`count_active_masters`, `deactivate_master`, `notification_recipients`)
- Modify: `apps/api/app/api/agent_team.py` (`_require_master`, `team`)
- Test: `apps/api/tests/test_agn_002_master_rules.py`

**Interfaces:**
- Consumes: member role `staff`, `AgentOrg.staff_seq` (Task 1).
- Produces: `rbac.is_agent_staff(user) -> bool`; `tests.agn002_helpers.mk_staff(db, org, *, full_name="Staff Member", active=True) -> dict(user, member)` (inserts a staff member directly, password = `PASSWORD`, approved assignment); `_require_master` returns the membership only for `role == "master"`.

- [ ] **Step 1: Write the helper** — `apps/api/tests/agn002_helpers.py`

```python
"""AGN-002 test helpers: a staff member inserted directly (the API path is tested in test_agn_002_staff.py)."""

from app.models import AgentOrg, AgentOrgMember, UserRoleAssignment
from tests.agn001_helpers import mk_user

STAFF = "/api/v1/workflows/overseas/agent/team/staff"


async def mk_staff(db, org: AgentOrg, *, full_name: str = "Staff Member", active: bool = True) -> dict:
    org = await db.get(AgentOrg, org.id, populate_existing=True)
    user = await mk_user(db, role="agent", full_name=full_name, active=active)
    db.add(UserRoleAssignment(user_id=user.id, division="overseas", role="agent", approval_status="approved"))
    org.staff_seq += 1
    member = AgentOrgMember(
        org_id=org.id, user_id=user.id, role="staff", seq=org.staff_seq, code=f"{org.prefix}-S{org.staff_seq:03d}", status="active" if active else "deactivated"
    )
    db.add(member)
    await db.commit()
    return {"user": user, "member": member}
```

- [ ] **Step 2: Write the failing tests** — `apps/api/tests/test_agn_002_master_rules.py`

```python
"""AGN-002 -- AC09 / S2: staff never count as Masters; AC07: staff cannot manage the team."""

import pytest

from app.services.agent_orgs import count_active_masters, notification_recipients
from tests.agn001_helpers import client_for, login, mk_active_org, uniq
from tests.agn002_helpers import mk_staff

TEAM = "/api/v1/workflows/overseas/agent/team"


@pytest.mark.asyncio
async def test_staff_do_not_count_toward_the_master_limit(client, db_session):
    ctx = await mk_active_org(db_session, name="Limit Staff")
    for _ in range(3):
        await mk_staff(db_session, ctx["org"])
    assert await count_active_masters(db_session, ctx["org"].id) == 1
    await login(client, ctx["master"].email)
    for _ in range(2):
        response = await client.post(TEAM + "/masters", json={"full_name": "M", "email": f"{uniq('m')}@example.local"})
        assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_an_active_staff_member_does_not_let_the_last_master_go(client, db_session):
    ctx = await mk_active_org(db_session, name="Last Master")
    await mk_staff(db_session, ctx["org"])
    await login(client, ctx["master"].email)
    response = await client.post(f"{TEAM}/masters/{ctx['member'].id}/deactivate")
    assert response.status_code == 422 and response.json()["detail"] == "An agency must keep at least one active Master"


@pytest.mark.asyncio
async def test_the_master_deactivate_route_does_not_touch_staff(client, db_session):
    ctx = await mk_active_org(db_session, name="Not A Master")
    staff = await mk_staff(db_session, ctx["org"])
    await login(client, ctx["master"].email)
    response = await client.post(f"{TEAM}/masters/{staff['member'].id}/deactivate")
    assert response.status_code == 404 and response.json()["detail"] == "Master not found"


@pytest.mark.asyncio
async def test_commission_notifications_reach_masters_only(db_session):
    ctx = await mk_active_org(db_session, name="Notify Masters")
    staff = await mk_staff(db_session, ctx["org"])
    recipients = await notification_recipients(db_session, staff["user"])
    assert [u.id for u in recipients] == [ctx["master"].id]


@pytest.mark.asyncio
async def test_team_lists_masters_only(client, db_session):
    ctx = await mk_active_org(db_session, name="Masters Only")
    await mk_staff(db_session, ctx["org"])
    await login(client, ctx["master"].email)
    body = (await client.get(TEAM)).json()
    assert [m["code"] for m in body["masters"]] == [f"{ctx['org'].prefix}-M001"]


_UNTIL_TASK_4 = pytest.mark.xfail(strict=True, reason="staff routes arrive in Task 4")


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path"), [
    ("get", ""),
    ("post", "/masters"),
    pytest.param("get", "/staff", marks=_UNTIL_TASK_4),
    pytest.param("post", "/staff", marks=_UNTIL_TASK_4),
])
async def test_staff_cannot_use_team_routes(db_session, method, path):
    ctx = await mk_active_org(db_session, name="Staff Blocked")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as c:
        kwargs = {"json": {"full_name": "X", "email": f"{uniq('x')}@example.local"}} if method == "post" else {}
        response = await getattr(c, method)(TEAM + path, **kwargs)
    assert response.status_code == 403 and response.json()["detail"] == "Only an agency Master can manage the team"
```

(Task 4 Step 6 deletes `_UNTIL_TASK_4` and turns the two `pytest.param(...)` entries back into plain tuples.)

- [ ] **Step 3: Run it** — API(`tests/test_agn_002_master_rules.py`). Expected: FAIL — limit test `422 "This agency already has 3 active Masters"`; last-Master test `200`; notification test includes the staff member; team list includes `S001`; staff get `200` on `GET /team`.

- [ ] **Step 4: Implement**

`apps/api/app/core/rbac.py`, after `agent_denial_reason`:

```python
def is_agent_staff(user) -> bool:
    """AGN-002 (DEC-SCOPE-040 S1/S2): a staff member of an agent organisation. Staff share `role='agent'` with Masters, so the
    Master-only actions (team management, commissions) call this. Reads the membership `get_current_user` eager-loads."""

    if user.role != "agent":
        return False
    membership = user.agent_membership
    return membership is not None and membership.role == "staff"
```

`apps/api/app/services/agent_orgs.py`:

```python
MASTER, STAFF = "master", "staff"
```

(top, after `MASTER_LIMIT = 3`), and add `AgentOrgMember.role == MASTER` to: the `where` of `count_active_masters`; the member lookup and the `others` query in `deactivate_master`; the `where` of `notification_recipients`'s final query. Update docstrings: `count_active_masters` → "Active Masters only; staff never count (AGN-002 S2).", `notification_recipients` → "D12: every active Master (never staff, AGN-002) of the agent's organisation; …".

`apps/api/app/api/agent_team.py`:

```python
MASTER_ONLY = "Only an agency Master can manage the team"


def _require_master(user: User) -> AgentOrgMember:
    if user.role != "agent" or user.division != "overseas":
        raise HTTPException(403, "This role cannot perform this operation")
    reason = agent_denial_reason(user)
    if reason:
        raise HTTPException(403, reason)
    if is_agent_staff(user):  # AGN-002 (S1): staff never manage the team
        raise HTTPException(403, MASTER_ONLY)
    return user.agent_membership
```

and in `team`, the rows query gains `AgentOrgMember.role == MASTER` (import `MASTER` from the service, `is_agent_staff` from `app.core.rbac`).

- [ ] **Step 5: Run** — API(`tests/test_agn_002_master_rules.py`). Expected: PASS (two xfail).

- [ ] **Step 6: Regression + lint** — API(R), LINT. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/core/rbac.py apps/api/app/services/agent_orgs.py apps/api/app/api/agent_team.py apps/api/tests/agn002_helpers.py apps/api/tests/test_agn_002_master_rules.py
git commit -m "feat(agn-002): Master rules count Masters only; staff cannot manage the team"
```

---

### Task 4: Create and list staff

**Files:**
- Modify: `apps/api/app/schemas.py` (after `AgentMasterInvite`)
- Modify: `apps/api/app/services/agent_orgs.py` (throttle generalisation, rejection helper, `staff_code`, `create_staff`)
- Modify: `apps/api/app/api/agent_team.py` (`_staff_out`, `_deliver`, `GET /staff`, `POST /staff`)
- Modify: `apps/api/tests/test_agn_002_master_rules.py` (remove the two xfail marks)
- Test: `apps/api/tests/test_agn_002_staff.py`

**Interfaces:**
- Consumes: `_require_master`, `MASTER/STAFF` (Task 3); `lock_org`, `issue_welcome_token`, `deliver_welcome_link`, `provisioning_statuses`, `flush_unique_email`, `unusable_password_hash`.
- Produces: `AgentStaffCreate`; `staff_code(prefix: str, seq: int) -> str`; `STAFF_ACTION_LIMIT = 20`; `_wait_seconds(db, org_id, actions: tuple[str, ...], limit: int) -> int`; `_check_staff_budget(db, org_id, actor_id) -> None`; `create_staff(db, org, actor, *, full_name, email, phone) -> tuple[AgentOrgMember, User, IssuedWelcome]`; routes `GET /staff`, `POST /staff`; helpers `_staff_out(member, user, statuses: dict) -> dict`, `_deliver(target, issued, actor) -> dict` in `agent_team.py`.

- [ ] **Step 1: Write the failing tests** — `apps/api/tests/test_agn_002_staff.py`

```python
"""AGN-002 -- staff logins through the API (DEC-SCOPE-040; spec §6-§7; AGN-002-AC01..AC10)."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import func, select

from app.main import app
from app.models import AgentOrg, AuditLog, User
from app.services import agent_orgs, provisioning
from tests.agn001_helpers import client_for, login, mk_active_org, mk_user, uniq
from tests.agn002_helpers import STAFF, mk_staff

# (`httpx`, `ASGITransport`, `app`, `func` are first used by the Task 5 tests appended below; ruff runs after Task 5 too.)

NEW_PASSWORD = "Staff-Secret-Pass-1!"


async def _create(client, **overrides):
    return await client.post(STAFF, json={"full_name": "Rahul Staff", "email": f"{uniq('s')}@example.local", **overrides})


def _capture(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def capture(channel, payload):
        sent.append(payload)
        return "sent", None

    monkeypatch.setattr(provisioning, "send_notification", capture)
    return sent


# --- AC01: codes -----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_codes_are_s001_s002_and_independent_of_masters(client, db_session):
    ctx = await mk_active_org(db_session, name="Codes Agency")
    await login(client, ctx["master"].email)
    first, second = (await _create(client)).json(), (await _create(client)).json()
    prefix = ctx["org"].prefix
    assert [first["member"]["code"], second["member"]["code"]] == [f"{prefix}-S001", f"{prefix}-S002"]
    invited = await client.post("/api/v1/workflows/overseas/agent/team/masters", json={"full_name": "M2", "email": f"{uniq('m')}@example.local"})
    assert invited.json()["member"]["code"] == f"{prefix}-M002"


@pytest.mark.asyncio
async def test_two_agencies_each_start_at_s001(client, db_session):
    for name in ("Alpha Staff", "Beta Staff"):
        ctx = await mk_active_org(db_session, name=name)
        async with client_for(ctx["master"].email) as c:
            assert (await _create(c)).json()["member"]["code"] == f"{ctx['org'].prefix}-S001"


@pytest.mark.asyncio
async def test_concurrent_creates_get_distinct_codes(db_session):  # Review Focus 2
    ctx = await mk_active_org(db_session, name="Race Staff")
    async with client_for(ctx["master"].email) as a, client_for(ctx["master"].email) as b:
        responses = await asyncio.gather(_create(a), _create(b))
    assert sorted(r.status_code for r in responses) == [201, 201]
    assert sorted(r.json()["member"]["code"] for r in responses) == [f"{ctx['org'].prefix}-S001", f"{ctx['org'].prefix}-S002"]
    assert (await db_session.get(AgentOrg, ctx["org"].id, populate_existing=True)).staff_seq == 2


# --- AC02: the set-password email --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_reports_the_email_and_never_returns_the_token(client, db_session, monkeypatch):
    sent = _capture(monkeypatch)
    ctx = await mk_active_org(db_session, name="Mail Agency")
    await login(client, ctx["master"].email)
    response = await _create(client, phone="+91 90000 00000")
    assert response.status_code == 201
    body = response.json()
    assert body["email_status"] == "sent" and body["expires_at"] and "development_welcome_token" not in body
    assert body["member"] | {"id": None} == {
        "id": None, "code": f"{ctx['org'].prefix}-S001", "full_name": "Rahul Staff", "email": body["member"]["email"],
        "phone": "+91 90000 00000", "status": "active", "setup": "pending_setup",
    }
    staff = await db_session.scalar(select(User).where(User.email == body["member"]["email"]))
    assert staff.role == "agent" and staff.division == "overseas" and staff.active and staff.profile["registration_source"] == "agent_staff_create"
    token = next(p["reset_token"] for p in sent if p.get("to") == staff.email)
    await client.post("/api/v1/auth/logout")
    assert (await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})).status_code == 200
    signed_in = await client.post("/api/v1/auth/login", json={"email": staff.email, "password": NEW_PASSWORD, "division": "overseas"})
    assert signed_in.status_code == 200


@pytest.mark.asyncio
async def test_a_failed_send_keeps_the_account_and_says_so(client, db_session, monkeypatch):  # Review Focus 4
    async def fail(channel, payload):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(provisioning, "send_notification", fail)
    ctx = await mk_active_org(db_session, name="No Mail Agency")
    await login(client, ctx["master"].email)
    response = await _create(client)
    assert response.status_code == 201 and response.json()["email_status"] != "sent"
    assert await db_session.scalar(select(User.id).where(User.email == response.json()["member"]["email"])) is not None


# --- validation and duplicates ----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"full_name": "   ", "email": "a@example.local"}, {"full_name": "A", "email": "not-an-email"}, {"full_name": "A"}])
async def test_create_validates(client, db_session, body):
    ctx = await mk_active_org(db_session, name="Valid Agency")
    await login(client, ctx["master"].email)
    assert (await client.post(STAFF, json=body)).status_code == 422


@pytest.mark.asyncio
async def test_an_existing_email_is_409_audited_and_not_numbered(client, db_session):
    ctx = await mk_active_org(db_session, name="Dup Staff")
    other = await mk_user(db_session, role="overseas_student")
    await login(client, ctx["master"].email)
    response = await _create(client, email=other.email.upper())
    assert response.status_code == 409 and response.json()["detail"] == "Email already exists"
    assert (await db_session.get(AgentOrg, ctx["org"].id, populate_existing=True)).staff_seq == 0
    rejected = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_org.staff_create_rejected", AuditLog.entity_id == str(ctx["org"].id)))
    assert rejected is not None and other.email not in str(rejected.metadata_json)


# --- AC08 (create) and list ---------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_is_audited_without_personal_data(client, db_session):
    ctx = await mk_active_org(db_session, name="Audit Staff")
    await login(client, ctx["master"].email)
    body = (await _create(client)).json()
    log = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_org.staff_create", AuditLog.entity_id == str(ctx["org"].id)))
    assert log.entity_type == "agent_org" and log.user_id == ctx["master"].id
    assert log.metadata_json == {"member_id": body["member"]["id"], "code": body["member"]["code"]}


@pytest.mark.asyncio
async def test_list_is_paginated_in_code_order(client, db_session):
    ctx = await mk_active_org(db_session, name="List Staff")
    for _ in range(3):
        await mk_staff(db_session, ctx["org"])
    await login(client, ctx["master"].email)
    first = (await client.get(STAFF, params={"limit": 2})).json()
    second = (await client.get(STAFF, params={"limit": 2, "offset": 2})).json()
    prefix = ctx["org"].prefix
    assert (first["total"], first["limit"], first["offset"]) == (3, 2, 0)
    assert [m["code"] for m in first["items"] + second["items"]] == [f"{prefix}-S001", f"{prefix}-S002", f"{prefix}-S003"]
    assert first["items"][0]["setup"] is None  # inserted with a password: set-up complete
    assert (await client.get(STAFF, params={"limit": 101})).status_code == 422


# --- AC10 (create part) -------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_21st_staff_action_in_a_day_is_429_and_master_invites_are_unaffected(client, db_session):
    ctx = await mk_active_org(db_session, name="Throttle Staff")
    now = datetime.now(UTC)
    db_session.add_all(
        AuditLog(user_id=ctx["master"].id, action="agent_org.staff_create", entity_type="agent_org", entity_id=str(ctx["org"].id), outcome="created", metadata_json={}, created_at=now - timedelta(hours=1))
        for _ in range(agent_orgs.STAFF_ACTION_LIMIT)
    )
    await db_session.commit()
    await login(client, ctx["master"].email)
    response = await _create(client)
    assert response.status_code == 429 and int(response.headers["Retry-After"]) > 0
    assert response.json()["detail"] == f"This agency has created or reset {agent_orgs.STAFF_ACTION_LIMIT} staff logins in the last 24 hours. Try again later."
    invite = await client.post("/api/v1/workflows/overseas/agent/team/masters", json={"full_name": "M", "email": f"{uniq('m')}@example.local"})
    assert invite.status_code == 201
```

- [ ] **Step 2: Run it** — API(`tests/test_agn_002_staff.py`). Expected: FAIL — `404 Not Found` for `POST /staff` / `GET /staff`; `AttributeError: module 'app.services.agent_orgs' has no attribute 'STAFF_ACTION_LIMIT'`.

- [ ] **Step 3: Implement the schema** — `apps/api/app/schemas.py`, after `AgentMasterInvite`:

```python
class AgentStaffCreate(AgentMasterInvite):
    """AGN-002 (DEC-SCOPE-040 S4): a Master adding a staff login -- the same fields and rules as a Master invite."""
```

- [ ] **Step 4: Implement the service** — `apps/api/app/services/agent_orgs.py`

Add below `member_code`:

```python
def staff_code(prefix: str, seq: int) -> str:
    return f"{prefix}-S{seq:03d}"
```

Replace `_invite_wait_seconds` with a general function and update its one caller in `invite_master` to `wait = await _wait_seconds(db, org_id, INVITE_ACTIONS, INVITE_LIMIT)`:

```python
INVITE_ACTIONS = ("agent_org.master_invite", "agent_org.master_invite_rejected")  # QA-10: failed attempts count too
STAFF_ACTION_LIMIT = 20
STAFF_ACTIONS = ("agent_org.staff_create", "agent_org.staff_create_rejected", "agent_org.staff_reset")


async def _wait_seconds(db: AsyncSession, org_id, actions: tuple[str, ...], limit: int) -> int:
    """Seconds before this agency may perform another of `actions`; 0 means allowed. Counted from the audit rows (the
    change-password throttle's no-new-table pattern), so the count is shared by every API instance. Master invites (R1, budget
    INVITE_LIMIT) and staff creations + resets (AGN-002 E2, budget STAFF_ACTION_LIMIT) are separate budgets. Runs under the
    organisation lock, so it is race-free."""
    now = datetime.now(UTC)
    recent = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.entity_type == "agent_org", AuditLog.entity_id == str(org_id), AuditLog.action.in_(actions), AuditLog.created_at > now - INVITE_WINDOW)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    ).all()
    if len(recent) < limit:
        return 0
    return max(1, math.ceil((recent[-1] + INVITE_WINDOW - now).total_seconds()))
```

Generalise `_reject_invite` (update the two calls in `invite_master` to `await _reject_existing_email(db, org_id, actor_id, action="agent_org.master_invite_rejected", event="agent_org_invite_rejected")`):

```python
async def _reject_existing_email(db: AsyncSession, org_id, actor_id, *, action: str, event: str) -> NoReturn:
    """Browser QA-10: a Master invite or staff creation for an existing address is audited and COUNTED toward its throttle, so
    probing which emails have accounts is capped per agency per day. Committed before the 409 (a raised request would otherwise
    roll the row back). The address itself is never recorded."""
    db.add(AuditLog(user_id=actor_id, action=action, entity_type="agent_org", entity_id=str(org_id), outcome="rejected", metadata_json={"reason": "email_exists"}))
    await db.commit()
    logger.info(event, extra={"extra_fields": {"org_id": str(org_id), "actor_id": str(actor_id), "reason": "email_exists"}})
    raise HTTPException(409, "Email already exists")
```

(`from typing import NoReturn`.) Then add:

```python
async def _check_staff_budget(db: AsyncSession, org_id, actor_id) -> None:
    wait = await _wait_seconds(db, org_id, STAFF_ACTIONS, STAFF_ACTION_LIMIT)
    if wait:
        logger.warning("agent_org_staff_throttled", extra={"extra_fields": {"org_id": str(org_id), "actor_id": str(actor_id), "wait_seconds": wait}})
        raise HTTPException(
            429, f"This agency has created or reset {STAFF_ACTION_LIMIT} staff logins in the last 24 hours. Try again later.", headers={"Retry-After": str(wait)}
        )


async def create_staff(db: AsyncSession, org: AgentOrg, actor: User, *, full_name: str, email: str, phone: str | None):
    """No commit; `org` must be locked. AGN-002 (S2-S4): a real agent account with an unusable password, an approved agent
    assignment, a staff member numbered from `staff_seq` (never reused) and a DEC-SCOPE-019 welcome token."""
    org_id, actor_id = org.id, actor.id  # plain values: a rollback below expires the ORM objects
    await _check_staff_budget(db, org_id, actor_id)
    email = email.lower().strip()
    rejected = {"action": "agent_org.staff_create_rejected", "event": "agent_org_staff_create_rejected"}
    if await db.scalar(select(User.id).where(User.email == email)):
        await _reject_existing_email(db, org_id, actor_id, **rejected)
    now = datetime.now(UTC)
    user = User(email=email, password_hash=unusable_password_hash(), full_name=full_name, role="agent", division="overseas", phone=phone, active=True, email_verified=False, profile={"registration_source": "agent_staff_create"})
    db.add(user)
    try:
        await flush_unique_email(db)  # a collision rolls back (releasing the org lock) and raises 409
    except HTTPException:
        await _reject_existing_email(db, org_id, actor_id, **rejected)
    db.add(UserRoleAssignment(user_id=user.id, division="overseas", role="agent", is_active=True, assigned_by_user_id=actor_id, approval_status="approved", approved_by_user_id=actor_id, approved_at=now))
    org.staff_seq += 1
    member = AgentOrgMember(org_id=org_id, user_id=user.id, role=STAFF, seq=org.staff_seq, code=staff_code(org.prefix, org.staff_seq), status="active", invited_by_user_id=actor_id)
    db.add(member)
    await db.flush()
    issued = await issue_welcome_token(db, user=user, issued_by=actor)
    db.add(AuditLog(user_id=actor_id, action="agent_org.staff_create", entity_type="agent_org", entity_id=str(org_id), outcome="created", metadata_json={"member_id": str(member.id), "code": member.code}))
    return member, user, issued
```

- [ ] **Step 5: Implement the routes** — `apps/api/app/api/agent_team.py` (imports: `import logging`, `from fastapi import Query`, `from sqlalchemy import func`, `from app.schemas import AgentMasterInvite, AgentStaffCreate`, service `STAFF, create_staff`; `logger = logging.getLogger("app.agent_orgs")`):

```python
def _staff_out(member: AgentOrgMember, staff: User, statuses: dict) -> dict:
    """AGN-002 member shape; `setup` is the DEC-SCOPE-019 provisioning status (None once the staff member has a password)."""
    return {"id": member.id, "code": member.code, "full_name": staff.full_name, "email": staff.email, "phone": staff.phone, "status": member.status, "setup": statuses.get(staff.id)}


async def _deliver(target: User, issued, actor: User) -> dict:
    """After the commit. A Master never receives the raw link token (S3), even in development/test."""
    delivery = await deliver_welcome_link(user=target, issued=issued, issued_by=actor)
    delivery.pop("development_welcome_token", None)
    return delivery


@router.get("/staff")
async def staff_list(limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-002: the agency's staff, in code order, `{items, total, limit, offset}` (the organisation-list shape)."""
    membership = _require_master(user)
    scope = (AgentOrgMember.org_id == membership.org_id, AgentOrgMember.role == STAFF)
    total = await db.scalar(select(func.count()).select_from(AgentOrgMember).where(*scope))
    rows = (await db.execute(select(AgentOrgMember, User).join(User, User.id == AgentOrgMember.user_id).where(*scope).order_by(AgentOrgMember.seq).limit(limit).offset(offset))).all()
    statuses = await provisioning_statuses(db, [u.id for _, u in rows])
    return {"items": [_staff_out(m, u, statuses) for m, u in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.post("/staff", status_code=201)
async def create_staff_login(payload: AgentStaffCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _require_master(user)
    org = await _locked_active_org(db, membership)
    member, staff, issued = await create_staff(db, org, user, full_name=payload.full_name, email=payload.email, phone=payload.phone)
    out = _staff_out(member, staff, {staff.id: "pending_setup"})
    org_id = org.id
    await db.commit()
    logger.info("agent_org_staff_created", extra={"extra_fields": {"org_id": str(org_id), "actor_id": str(user.id), "member_id": str(out["id"]), "code": out["code"]}})
    return {"member": out, **await _deliver(staff, issued, user)}
```

Refactor the existing `invite` route to use `_deliver` (behaviour unchanged).

- [ ] **Step 6: Remove the xfail marks** in `test_agn_002_master_rules.py` (delete `_UNTIL_TASK_4`; the two `pytest.param` entries become `("get", "/staff")` and `("post", "/staff")`).

- [ ] **Step 7: Run** — API(`tests/test_agn_002_staff.py tests/test_agn_002_master_rules.py`). Expected: PASS.

- [ ] **Step 8: Regression + lint** — API(R), LINT. Expected: PASS (the Master invite throttle tests in `test_agn_001_team.py` prove the refactor kept R1).

- [ ] **Step 9: Commit**

```bash
git add apps/api/app/schemas.py apps/api/app/services/agent_orgs.py apps/api/app/api/agent_team.py apps/api/tests/test_agn_002_staff.py apps/api/tests/test_agn_002_master_rules.py
git commit -m "feat(agn-002): Masters create and list staff logins (S001...)"
```

---

### Task 5: Edit, deactivate, reactivate and reset staff

**Files:**
- Modify: `apps/api/app/schemas.py` (`AgentStaffUpdate`)
- Modify: `apps/api/app/services/agent_orgs.py` (`_staff_member`, `update_staff`, `deactivate_staff`, `reactivate_staff`, `reset_staff`)
- Modify: `apps/api/app/api/agent_team.py` (four routes)
- Test: `apps/api/tests/test_agn_002_staff.py` (append)

**Interfaces:**
- Consumes: Task 4's `_check_staff_budget`, `_staff_out`, `_deliver`, `STAFF`; Task 2's session check; `revoke_welcome_tokens`, `resend_wait_seconds`, `provisioning_statuses`.
- Produces: `AgentStaffUpdate`; `update_staff(db, org, member_id, actor, changes: dict) -> (member, user)`; `deactivate_staff / reactivate_staff(db, org, member_id, actor) -> (member, user)`; `reset_staff(db, org, member_id, actor) -> (member, user, issued)`; routes `PATCH /staff/{member_id}`, `POST /staff/{member_id}/deactivate|reactivate|reset`.

- [ ] **Step 1: Append the failing tests** to `apps/api/tests/test_agn_002_staff.py`

```python
async def _staff_via_api(client, monkeypatch) -> tuple[dict, str]:
    """Create a staff member as the signed-in Master and set their password; returns (member, email)."""
    sent = _capture(monkeypatch)
    member = (await _create(client)).json()["member"]
    token = next(p["reset_token"] for p in sent if p.get("to") == member["email"])
    assert (await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})).status_code == 200
    return member, member["email"]


async def _staff_client(email: str, password: str = NEW_PASSWORD) -> httpx.AsyncClient:
    """A signed-in client for the staff member (own cookie jar); the caller closes it."""
    c = httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    response = await c.post("/api/v1/auth/login", json={"email": email, "password": password, "division": "overseas"})
    assert response.status_code == 200, response.text
    return c


async def _login_status(email: str, password: str = NEW_PASSWORD) -> int:
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return (await c.post("/api/v1/auth/login", json={"email": email, "password": password, "division": "overseas"})).status_code


# --- AC03: edit -------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_changes_name_and_phone_only(client, db_session, monkeypatch):
    ctx = await mk_active_org(db_session, name="Edit Staff")
    await login(client, ctx["master"].email)
    member, email = await _staff_via_api(client, monkeypatch)
    response = await client.patch(f"{STAFF}/{member['id']}", json={"full_name": "  Rahul K  ", "phone": "+91 1"})
    assert response.status_code == 200 and response.json()["member"]["full_name"] == "Rahul K" and response.json()["member"]["phone"] == "+91 1"
    assert (await client.patch(f"{STAFF}/{member['id']}", json={"phone": None})).json()["member"]["phone"] is None
    log = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_org.staff_update", AuditLog.entity_id == str(ctx["org"].id)).order_by(AuditLog.created_at.desc()))
    assert log.metadata_json == {"member_id": member["id"], "code": member["code"], "fields": ["phone"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(("body", "detail"), [({}, "Nothing to update"), ({"email": "new@example.local"}, None), ({"full_name": None}, "Full name is required"), ({"full_name": "  "}, "Full name is required")])
async def test_edit_validates(client, db_session, monkeypatch, body, detail):
    ctx = await mk_active_org(db_session, name="Edit Valid")
    await login(client, ctx["master"].email)
    member, _ = await _staff_via_api(client, monkeypatch)
    response = await client.patch(f"{STAFF}/{member['id']}", json=body)
    assert response.status_code == 422
    if detail:
        assert detail in str(response.json()["detail"])


# --- AC04 / AC05: deactivate and reactivate ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivated_staff_are_refused_everywhere_and_reactivation_restores_login(client, db_session, monkeypatch):
    ctx = await mk_active_org(db_session, name="Deact Staff")
    await login(client, ctx["master"].email)
    member, email = await _staff_via_api(client, monkeypatch)
    staff_client = await _staff_client(email)
    old_access, old_refresh = staff_client.cookies.get("edusphere_access"), staff_client.cookies.get("edusphere_refresh")
    try:
        response = await client.post(f"{STAFF}/{member['id']}/deactivate")
        assert response.status_code == 200 and response.json()["member"]["status"] == "deactivated"
        for path in ("/api/v1/auth/me", "/api/v1/workflows/overseas/agent/students", "/api/v1/portal/overseas/agent/dashboard"):
            assert (await staff_client.get(path)).status_code == 401, path
        assert (await staff_client.post("/api/v1/auth/refresh")).status_code == 401
        assert await _login_status(email) == 401
        assert (await client.post(f"{STAFF}/{member['id']}/deactivate")).json()["detail"] == "Already deactivated"

        reactivated = await client.post(f"{STAFF}/{member['id']}/reactivate")
        assert reactivated.status_code == 200 and reactivated.json()["member"]["status"] == "active"
        again = await _staff_client(email)
        assert (await again.get("/api/v1/auth/me")).status_code == 200
        await again.aclose()
        # E6: cookies from before the deactivation stay dead after reactivation.
        staff_client.cookies.set("edusphere_access", old_access)
        staff_client.cookies.set("edusphere_refresh", old_refresh)
        assert (await staff_client.get("/api/v1/auth/me")).status_code == 401
        assert (await staff_client.post("/api/v1/auth/refresh")).status_code == 401
        assert (await client.post(f"{STAFF}/{member['id']}/reactivate")).json()["detail"] == "Already active"
    finally:
        await staff_client.aclose()


@pytest.mark.asyncio
async def test_deactivation_revokes_an_unused_link_and_reactivation_does_not_revive_it(client, db_session, monkeypatch):  # E3
    sent = _capture(monkeypatch)
    ctx = await mk_active_org(db_session, name="Link Staff")
    await login(client, ctx["master"].email)
    member = (await _create(client)).json()["member"]
    token = next(p["reset_token"] for p in sent if p.get("to") == member["email"])
    await client.post(f"{STAFF}/{member['id']}/deactivate")
    await client.post(f"{STAFF}/{member['id']}/reactivate")
    assert (await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})).status_code == 400
    listed = (await client.get(STAFF)).json()["items"][0]
    assert listed["setup"] == "link_expired"


# --- AC06: reset --------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_kills_the_password_and_sessions_and_sends_a_working_link(client, db_session, monkeypatch):
    ctx = await mk_active_org(db_session, name="Reset Staff")
    await login(client, ctx["master"].email)
    member, email = await _staff_via_api(client, monkeypatch)
    sent = _capture(monkeypatch)
    staff_client = await _staff_client(email)
    try:
        # The create link is the account's only welcome token, so the first reset is inside `resend_wait_seconds`' free pass.
        response = await client.post(f"{STAFF}/{member['id']}/reset")
        assert response.status_code == 200 and response.json()["member"]["setup"] == "pending_setup" and "development_welcome_token" not in response.json()
        assert (await staff_client.get("/api/v1/auth/me")).status_code == 401
        assert await _login_status(email) == 401
        token = next(p["reset_token"] for p in sent if p.get("to") == email)
        assert (await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "Brand-New-Pass-22!"})).status_code == 200
        assert await _login_status(email, "Brand-New-Pass-22!") == 200
        second = await client.post(f"{STAFF}/{member['id']}/reset")
        assert second.status_code == 429 and second.json()["detail"].startswith("A link was just sent; wait ")
        assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "agent_org.staff_reset", AuditLog.entity_id == str(ctx["org"].id))) == 1
    finally:
        await staff_client.aclose()


@pytest.mark.asyncio
async def test_reset_of_deactivated_staff_is_409(client, db_session):
    ctx = await mk_active_org(db_session, name="Reset Deact")
    staff = await mk_staff(db_session, ctx["org"], active=False)
    await login(client, ctx["master"].email)
    response = await client.post(f"{STAFF}/{staff['member'].id}/reset")
    assert response.status_code == 409 and response.json()["detail"] == "Reactivate this staff member first"


# --- AC07 (team routes) / Review Focus 3 ------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_another_agency_and_master_ids_get_404_on_every_staff_route(db_session):
    mine, theirs = await mk_active_org(db_session, name="Mine Staff"), await mk_active_org(db_session, name="Theirs Staff")
    their_staff = await mk_staff(db_session, theirs["org"])
    targets = {"their staff": their_staff["member"].id, "a master": mine["member"].id}
    async with client_for(mine["master"].email) as c:
        assert (await c.get(STAFF)).json()["total"] == 0
        for label, member_id in targets.items():
            for method, path, kwargs in (("patch", "", {"json": {"full_name": "Hacked"}}), ("post", "/deactivate", {}), ("post", "/reactivate", {}), ("post", "/reset", {})):
                response = await getattr(c, method)(f"{STAFF}/{member_id}{path}", **kwargs)
                assert response.status_code == 404 and response.json()["detail"] == "Staff member not found", (label, path)
    untouched = await db_session.get(User, their_staff["user"].id, populate_existing=True)
    assert untouched.full_name == "Staff Member" and untouched.active


# --- AC08: every action audited ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_action_writes_one_audit_row(client, db_session, monkeypatch):
    ctx = await mk_active_org(db_session, name="Audit All")
    await login(client, ctx["master"].email)
    member, _ = await _staff_via_api(client, monkeypatch)
    await client.patch(f"{STAFF}/{member['id']}", json={"full_name": "Renamed"})
    await client.post(f"{STAFF}/{member['id']}/deactivate")
    await client.post(f"{STAFF}/{member['id']}/reactivate")
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(ctx["org"].id), AuditLog.action.like("agent_org.staff_%")))).all()
    assert sorted(r.action for r in rows) == ["agent_org.staff_create", "agent_org.staff_deactivate", "agent_org.staff_reactivate", "agent_org.staff_update"]
    assert all(r.entity_type == "agent_org" and r.metadata_json["member_id"] == member["id"] and "@" not in str(r.metadata_json) for r in rows)
```

- [ ] **Step 2: Run** — API(`tests/test_agn_002_staff.py`). Expected: the new tests FAIL with `404`/`405` (routes missing); the Task 4 tests still PASS.

- [ ] **Step 3: Implement the schema** — `apps/api/app/schemas.py`, after `AgentStaffCreate`:

```python
class AgentStaffUpdate(BaseModel):
    """AGN-002 (DEC-SCOPE-040 S4): name and phone only. Email is fixed after creation, so a Master can never redirect a staff
    member's set-password link to an address they control. Omitted = unchanged; phone null or "" clears it."""

    model_config = {"extra": "forbid"}
    full_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("full_name")
    @classmethod
    def full_name_present(cls, value: str | None) -> str:
        value = (value or "").strip()
        if not value:
            raise PydanticCustomError("blank_full_name", "Full name is required")
        return value

    @field_validator("phone")
    @classmethod
    def phone_blank_is_none(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

    @model_validator(mode="after")
    def something_to_update(self):
        if not self.model_fields_set:
            raise PydanticCustomError("nothing_to_update", "Nothing to update")
        return self
```

(`model_validator` added to the pydantic import if missing.)

- [ ] **Step 4: Implement the service** — `apps/api/app/services/agent_orgs.py` (import `resend_wait_seconds` from provisioning):

```python
async def _staff_member(db: AsyncSession, org: AgentOrg, member_id) -> tuple[AgentOrgMember, User]:
    """The caller's organisation's staff member, else 404 -- another agency's member and every Master read the same (no
    disclosure). The user row is locked after the organisation (lock order: org -> user -> tokens, as reset-password/Re-send)."""
    member = await db.scalar(
        select(AgentOrgMember).where(AgentOrgMember.id == member_id, AgentOrgMember.org_id == org.id, AgentOrgMember.role == STAFF).execution_options(populate_existing=True)
    )
    if not member:
        raise HTTPException(404, "Staff member not found")
    user = await db.get(User, member.user_id, with_for_update=True, populate_existing=True)
    return member, user


def _staff_audit(db: AsyncSession, actor: User, org: AgentOrg, member: AgentOrgMember, action: str, outcome: str, **extra) -> None:
    db.add(AuditLog(user_id=actor.id, action=f"agent_org.{action}", entity_type="agent_org", entity_id=str(org.id), outcome=outcome, metadata_json={"member_id": str(member.id), "code": member.code, **extra}))


async def update_staff(db: AsyncSession, org: AgentOrg, member_id, actor: User, changes: dict) -> tuple[AgentOrgMember, User]:
    """No commit; `org` locked. S4: `changes` holds only `full_name` / `phone`; audited by field name, never by value."""
    member, user = await _staff_member(db, org, member_id)
    for field, value in changes.items():
        setattr(user, field, value)
    _staff_audit(db, actor, org, member, "staff_update", "updated", fields=sorted(changes))
    return member, user


async def deactivate_staff(db: AsyncSession, org: AgentOrg, member_id, actor: User) -> tuple[AgentOrgMember, User]:
    """No commit; `org` locked. S5 + E6: login disabled (every API refuses on the next request), sessions ended by the version,
    any open set-password link revoked."""
    member, user = await _staff_member(db, org, member_id)
    if member.status != "active":
        raise HTTPException(409, "Already deactivated")
    member.status, member.deactivated_at, member.deactivated_by_user_id = "deactivated", datetime.now(UTC), actor.id
    user.active = False
    user.session_version += 1
    await revoke_welcome_tokens(db, user.id)
    _staff_audit(db, actor, org, member, "staff_deactivate", "deactivated")
    return member, user


async def reactivate_staff(db: AsyncSession, org: AgentOrg, member_id, actor: User) -> tuple[AgentOrgMember, User]:
    """No commit; `org` locked. S5 / E3: restores the login only. Open links stay revoked (as admin reactivation); a staff
    member who never set a password is sent a new link with Reset."""
    member, user = await _staff_member(db, org, member_id)
    if member.status == "active":
        raise HTTPException(409, "Already active")
    member.status, member.deactivated_at, member.deactivated_by_user_id = "active", None, None
    user.active = True
    await revoke_welcome_tokens(db, user.id)
    _staff_audit(db, actor, org, member, "staff_reactivate", "reactivated")
    return member, user


async def reset_staff(db: AsyncSession, org: AgentOrg, member_id, actor: User):
    """No commit; `org` locked. S3: the password stops working, every session ends, and a new DEC-SCOPE-019 link (which revokes
    the previous one) goes to the staff member's own address. Counts toward the staff budget; E7: per-account 60 s cooldown."""
    member, user = await _staff_member(db, org, member_id)
    if member.status != "active":
        raise HTTPException(409, "Reactivate this staff member first")
    await _check_staff_budget(db, org.id, actor.id)
    wait = await resend_wait_seconds(db, user.id)
    if wait:
        logger.warning("agent_org_staff_reset_cooldown", extra={"extra_fields": {"org_id": str(org.id), "member_id": str(member.id), "wait_seconds": wait}})
        raise HTTPException(429, f"A link was just sent; wait {wait} seconds before resetting again", headers={"Retry-After": str(wait)})
    user.password_hash = unusable_password_hash()
    user.session_version += 1
    issued = await issue_welcome_token(db, user=user, issued_by=actor)
    _staff_audit(db, actor, org, member, "staff_reset", "reset")
    return member, user, issued
```

Also switch `create_staff`'s inline audit to `_staff_audit(db, actor, org, member, "staff_create", "created")` (same row; the Task 4 audit test proves it).

- [ ] **Step 5: Implement the routes** — `apps/api/app/api/agent_team.py`:

```python
async def _staff_action(db: AsyncSession, user: User, member_id: UUID, action) -> tuple[dict, str]:
    """Lock the caller's active organisation, run the service `action`, build the response before the commit."""
    membership = _require_master(user)
    org = await _locked_active_org(db, membership)
    member, staff = await action(db, org, member_id, user)
    statuses = await provisioning_statuses(db, [staff.id])
    return _staff_out(member, staff, statuses), str(org.id)


def _log(event: str, org_id: str, actor: User, out: dict) -> None:
    logger.info(event, extra={"extra_fields": {"org_id": org_id, "actor_id": str(actor.id), "member_id": str(out["id"]), "code": out["code"]}})


@router.patch("/staff/{member_id}")
async def edit_staff(member_id: UUID, payload: AgentStaffUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    changes = payload.model_dump(exclude_unset=True)
    out, org_id = await _staff_action(db, user, member_id, lambda d, o, m, a: update_staff(d, o, m, a, changes))
    await db.commit()
    _log("agent_org_staff_updated", org_id, user, out)
    return {"member": out}


@router.post("/staff/{member_id}/deactivate")
async def deactivate_staff_login(member_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    out, org_id = await _staff_action(db, user, member_id, deactivate_staff)
    await db.commit()
    _log("agent_org_staff_deactivated", org_id, user, out)
    return {"member": out}


@router.post("/staff/{member_id}/reactivate")
async def reactivate_staff_login(member_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    out, org_id = await _staff_action(db, user, member_id, reactivate_staff)
    await db.commit()
    _log("agent_org_staff_reactivated", org_id, user, out)
    return {"member": out}


@router.post("/staff/{member_id}/reset")
async def reset_staff_login(member_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _require_master(user)
    org = await _locked_active_org(db, membership)
    member, staff, issued = await reset_staff(db, org, member_id, user)
    out, org_id = _staff_out(member, staff, {staff.id: "pending_setup"}), str(org.id)
    await db.commit()
    _log("agent_org_staff_reset", org_id, user, out)
    return {"member": out, **await _deliver(staff, issued, user)}
```

Imports: `AgentStaffUpdate`, `update_staff, deactivate_staff, reactivate_staff, reset_staff`.

- [ ] **Step 6: Run** — API(`tests/test_agn_002_staff.py`). Expected: PASS.

- [ ] **Step 7: Refactor** — `create_staff_login` uses `_log("agent_org_staff_created", …)`; rerun API(`tests/test_agn_002_staff.py tests/test_agn_002_master_rules.py`). Expected: PASS.

- [ ] **Step 8: Regression + lint** — API(R), LINT. Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add apps/api/app/schemas.py apps/api/app/services/agent_orgs.py apps/api/app/api/agent_team.py apps/api/tests/test_agn_002_staff.py
git commit -m "feat(agn-002): edit, deactivate, reactivate and reset staff logins"
```

---

### Task 6: Staff outside the team routes — commissions, portal, admin, `/auth/me`

**Files:**
- Modify: `apps/api/app/api/workflows.py` (`agent_commissions`, `claim_commission`)
- Modify: `apps/api/app/api/portal.py`
- Modify: `apps/api/app/services/portal.py` (`_agent`)
- Modify: `apps/api/app/api/admin.py` (`list_agent_orgs`, `list_agents`, `_pending_agent_assignment`)
- Modify: `apps/api/app/schemas.py` (`UserOut.agent_member_role`), `apps/api/app/api/auth.py` (`me`)
- Test: `apps/api/tests/test_agn_002_staff_access.py`

**Interfaces:**
- Consumes: `is_agent_staff` (Task 3), `mk_staff` helper.
- Produces: `UserOut.agent_member_role: str | None = None` (set only by `GET /auth/me`).

- [ ] **Step 1: Write the failing tests** — `apps/api/tests/test_agn_002_staff_access.py`

```python
"""AGN-002 -- AC07/AC09 outside the team routes: staff reach organisation students/applications, never commissions."""

import pytest

from app.models import AgentStudent
from tests.agn001_helpers import client_for, login, mk_active_org, mk_user
from tests.agn002_helpers import mk_staff


async def _org_with_student(db_session, name: str):
    ctx = await mk_active_org(db_session, name=name)
    student = await mk_user(db_session, role="overseas_student", full_name=f"{name} Student")
    db_session.add(AgentStudent(agent_id=ctx["master"].id, student_id=student.id, status="active"))
    await db_session.commit()
    return ctx, student


@pytest.mark.asyncio
async def test_staff_see_the_organisations_students(db_session):
    ctx, student = await _org_with_student(db_session, "Staff Sees")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as c:
        response = await c.get("/api/v1/workflows/overseas/agent/students")
        assert response.status_code == 200 and str(student.id) in response.text
        assert (await c.get("/api/v1/portal/overseas/agent/students")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path", "detail"), [
    ("get", "/api/v1/workflows/overseas/agent/commissions", "Only an agency Master can view commissions"),
    ("post", "/api/v1/workflows/overseas/agent/commissions/00000000-0000-0000-0000-000000000000/claim", "Only an agency Master can view commissions"),
    ("get", "/api/v1/portal/overseas/agent/commissions", "Only an agency Master can open this page"),
    ("get", "/api/v1/portal/overseas/agent/team", "Only an agency Master can open this page"),
])
async def test_staff_are_refused_master_only_pages(db_session, method, path, detail):
    ctx = await mk_active_org(db_session, name="Staff Refused")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as c:
        response = await getattr(c, method)(path)
    assert response.status_code == 403 and response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_staff_dashboard_and_reports_leave_out_commission_figures(db_session):
    ctx = await mk_active_org(db_session, name="Staff Figures")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as c:
        dashboard = (await c.get("/api/v1/portal/overseas/agent/dashboard")).json()
        reports = (await c.get("/api/v1/portal/overseas/agent/reports")).json()
    assert "commission" not in str(dashboard).lower() and "Claims" not in str(dashboard)
    assert "commission" not in str(reports["rows"]).lower()
    async with client_for(ctx["master"].email) as m:
        assert "Claimable commission" in str((await m.get("/api/v1/portal/overseas/agent/dashboard")).json())


@pytest.mark.asyncio
async def test_auth_me_reports_the_member_role(db_session):
    ctx = await mk_active_org(db_session, name="Me Role")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as c:
        assert (await c.get("/api/v1/auth/me")).json()["agent_member_role"] == "staff"
    async with client_for(ctx["master"].email) as m:
        assert (await m.get("/api/v1/auth/me")).json()["agent_member_role"] == "master"
    student = await mk_user(db_session, role="overseas_student")
    async with client_for(student.email) as s:
        assert (await s.get("/api/v1/auth/me")).json()["agent_member_role"] is None


@pytest.mark.asyncio
async def test_admin_lists_show_masters_only_and_staff_cannot_be_approved_as_agents(client, db_session):
    ctx = await mk_active_org(db_session, name="Admin View Staff")
    staff = await mk_staff(db_session, ctx["org"])
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    orgs = (await client.get("/api/v1/overseas-admin/agent-orgs", params={"q": ctx["org"].prefix})).json()["items"]
    mine = next(o for o in orgs if o["id"] == str(ctx["org"].id))
    assert [m["code"] for m in mine["masters"]] == [f"{ctx['org'].prefix}-M001"]
    assert (await client.get("/api/v1/overseas-admin/agent-orgs", params={"q": staff["member"].code})).json()["total"] == 0
    assert str(staff["user"].id) not in (await client.get("/api/v1/overseas-admin/agents")).text
    response = await client.post(f"/api/v1/overseas-admin/agents/{staff['user'].id}/approve")
    assert response.status_code == 422 and response.json()["detail"] == "Staff accounts are managed by their agency"
```

- [ ] **Step 2: Run** — API(`tests/test_agn_002_staff_access.py`). Expected: FAIL — staff get `200` on commissions/team; dashboard contains "Claimable commission"; `agent_member_role` missing (`KeyError`); admin list shows `S001`; approve returns `200`.

- [ ] **Step 3: Implement**

`workflows.py` — in `agent_commissions` and `claim_commission`, right after `_require(user, {"agent"}, "overseas")`:

```python
    if is_agent_staff(user):  # AGN-002 (S1): commissions are Master-only
        raise HTTPException(403, "Only an agency Master can view commissions")
```

`api/portal.py` — after the `agent_denial_reason` block:

```python
    # AGN-002 (S1): the agency's team and commissions are Master-only pages.
    if is_agent_staff(user) and section in {"team", "commissions"}:
        raise HTTPException(403, "Only an agency Master can open this page")
```

`services/portal.py` `_agent` — `staff = is_agent_staff(user)`; `commissions = [] if staff else (await db.scalars(...)).all()`; the dashboard stat tuple becomes:

```python
            (
                {"label": "Students", "value": len(students)},
                {"label": "Applications", "value": len(applications)},
                *(() if staff else (
                    {"label": "Claimable commission", "value": f"INR {sum(float(c.amount) for c in commissions if c.status in {'eligible', 'estimated'}):,.0f}"},
                    {"label": "Claims", "value": sum(1 for c in commissions if c.status == "claimed")},
                )),
                *(({"label": "Your code", "value": user.agent_membership.code},) if user.agent_membership else ()),
            ),
```

and the reports rows drop `{"metric": "Paid commission", …}` when `staff` (same `*(() if staff else (...,))` shape). The team section's rows query gains `AgentOrgMember.role == "master"`.

`admin.py`:
- `list_agent_orgs`: `member_match` gains `.where(AgentOrgMember.role == "master")`; the masters rows query gains `AgentOrgMember.role == "master"`.
- `list_agents`: `stmt` gains `.where(User.id.not_in(select(AgentOrgMember.user_id).where(AgentOrgMember.role == "staff")))`.
- `_pending_agent_assignment`, after the `agent.role != "agent"` check:

```python
    # AGN-002: a staff login belongs to its agency's Masters; approving/rejecting it here would act on the whole organisation.
    if await db.scalar(select(AgentOrgMember.id).where(AgentOrgMember.user_id == agent.id, AgentOrgMember.role == "staff")):
        raise HTTPException(422, "Staff accounts are managed by their agency")
```

`schemas.py` `UserOut`: add `agent_member_role: str | None = None` with the comment `# AGN-002: set by GET /auth/me only (login/refresh do not load the membership).`

`auth.py` `me`:

```python
@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    out = UserOut.model_validate(user)
    # AGN-002: the portal hides Master-only pages from staff (the server refuses them regardless).
    out.agent_member_role = user.agent_membership.role if user.agent_membership else None
    return out
```

- [ ] **Step 4: Run** — API(`tests/test_agn_002_staff_access.py`). Expected: PASS.

- [ ] **Step 5: Regression + lint** — API(R + `tests/test_agn_001_registration_and_gate.py`), LINT. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/workflows.py apps/api/app/api/portal.py apps/api/app/services/portal.py apps/api/app/api/admin.py apps/api/app/schemas.py apps/api/app/api/auth.py apps/api/tests/test_agn_002_staff_access.py
git commit -m "feat(agn-002): staff reach organisation data but never commissions or admin agent actions"
```

---

### Task 7: Staff navigation

**Files:**
- Modify: `apps/web/lib/navigation.ts`, `apps/web/lib/types.ts`, `apps/web/components/PortalPage.tsx`
- Test: `apps/web/tests/lib/navigation.test.ts`

**Interfaces:**
- Consumes: `agent_member_role` on `/auth/me` (Task 6).
- Produces: `agentNavFor(nav: NavItem[], memberRole?: string | null): NavItem[]`; `User.agent_member_role?: "master" | "staff" | null`.

- [ ] **Step 1: Write the failing test** — `apps/web/tests/lib/navigation.test.ts`

```ts
import { describe, expect, it } from "vitest";

import { agentNavFor, PORTAL_NAV } from "@/lib/navigation";

describe("agentNavFor (AGN-002)", () => {
  const nav = PORTAL_NAV["overseas/agent"];

  it("hides Team and Commissions from staff", () => {
    const hrefs = agentNavFor(nav, "staff").map((item) => item.href);
    expect(hrefs).not.toContain("/overseas/agent/team");
    expect(hrefs).not.toContain("/overseas/agent/commissions");
    expect(hrefs).toContain("/overseas/agent/students");
  });

  it("keeps the full nav for Masters and unknown roles", () => {
    expect(agentNavFor(nav, "master")).toEqual(nav);
    expect(agentNavFor(nav, null)).toEqual(nav);
  });
});
```

- [ ] **Step 2: Run** — WEB(`tests/lib/navigation.test.ts`). Expected: FAIL — `agentNavFor is not a function` (not exported).

- [ ] **Step 3: Implement**

`lib/navigation.ts` (after `PORTAL_NAV`):

```ts
// AGN-002 (DEC-SCOPE-040 S1): an agency's staff work on students and applications; Team and Commissions stay Master-only (the
// server refuses them regardless -- this only keeps dead links out of the sidebar).
const STAFF_HIDDEN = new Set(["/overseas/agent/team", "/overseas/agent/commissions"]);
export function agentNavFor(nav: NavItem[], memberRole?: string | null): NavItem[] {
  return memberRole === "staff" ? nav.filter((item) => !STAFF_HIDDEN.has(item.href)) : nav;
}
```

`lib/types.ts` `User`: add `agent_member_role?: "master" | "staff" | null;`.

`components/PortalPage.tsx`: import `agentNavFor`; after the data fetch compute `const staff=key==="overseas/agent"&&user.agent_member_role==="staff";` and render `<PortalShell nav={staff?agentNavFor(nav,"staff"):nav} roleLabel={staff?"Agency Staff":labels[key]||role} …>` (the `notFound()` check keeps using the full `nav`, so a staff member typing `/overseas/agent/team` reaches the server's `403` card, not a 404).

- [ ] **Step 4: Run** — WEB(`tests/lib/navigation.test.ts tests/components/PortalShell.test.tsx`). Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/navigation.ts apps/web/lib/types.ts apps/web/components/PortalPage.tsx apps/web/tests/lib/navigation.test.ts
git commit -m "feat(agn-002): staff sidebar hides Team and Commissions"
```

---

### Task 8: `AgentStaffCreateForm`

**Files:**
- Create: `apps/web/components/AgentStaffCreateForm.tsx`
- Test: `apps/web/tests/components/AgentStaffCreateForm.test.tsx`

**Interfaces:**
- Consumes: `sendJson` (`@/lib/apiErrors`); `POST /team/staff` (Task 4).
- Produces: `export const STAFF_URL = "/api/v1/workflows/overseas/agent/team/staff"` (in this file; imported by Tasks 9–10); `default function AgentStaffCreateForm({ onCreated }: { onCreated: () => void })`.

- [ ] **Step 1: Write the failing test** — `apps/web/tests/components/AgentStaffCreateForm.test.tsx`

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStaffCreateForm from "@/components/AgentStaffCreateForm";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const member = { id: "s1", code: "ABC-S001", full_name: "Rahul", email: "rahul@example.local", phone: null, status: "active", setup: "pending_setup" };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function fill() {
  fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Rahul" } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "rahul@example.local" } });
}

describe("AgentStaffCreateForm (AGN-002)", () => {
  it("creates, says the email was sent, clears the form and tells the parent", async () => {
    const mock = vi.fn().mockResolvedValue(res({ member, email_status: "sent" }, 201));
    vi.stubGlobal("fetch", mock);
    const onCreated = vi.fn();
    render(<AgentStaffCreateForm onCreated={onCreated} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Add staff" }));
    expect(await screen.findByText("ABC-S001 created. A set-password link was emailed to rahul@example.local.")).toBeInTheDocument();
    expect(onCreated).toHaveBeenCalledTimes(1);
    expect((screen.getByLabelText("Full name") as HTMLInputElement).value).toBe("");
    expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({ full_name: "Rahul", email: "rahul@example.local", phone: null });
  });

  it("tells the Master to use Reset when the email was not delivered", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ member, email_status: "not_configured" }, 201)));
    render(<AgentStaffCreateForm onCreated={vi.fn()} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Add staff" }));
    expect(await screen.findByText("ABC-S001 created, but the email was not delivered. Use Reset to send a new link.")).toBeInTheDocument();
  });

  it.each([
    [409, { detail: "Email already exists" }, "Email already exists"],
    [429, { detail: "This agency has created or reset 20 staff logins in the last 24 hours. Try again later." }, "This agency has created or reset 20 staff logins in the last 24 hours. Try again later."],
  ])("shows the server's %s and keeps the entry", async (status, body, text) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(body, status)));
    const onCreated = vi.fn();
    render(<AgentStaffCreateForm onCreated={onCreated} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Add staff" }));
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe("rahul@example.local");
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("reports a dropped network and blocks a double submit", async () => {
    let reject: (e: Error) => void = () => {};
    const mock = vi.fn().mockReturnValue(new Promise((_, r) => { reject = r; }));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffCreateForm onCreated={vi.fn()} />);
    fill();
    const button = screen.getByRole("button", { name: "Add staff" });
    fireEvent.click(button);
    expect(await screen.findByRole("button", { name: "Adding…" })).toBeDisabled();
    fireEvent.submit(button.closest("form")!);
    expect(mock).toHaveBeenCalledTimes(1);
    reject(new Error("offline"));
    expect(await screen.findByText(/The request did not complete/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** — WEB(`tests/components/AgentStaffCreateForm.test.tsx`). Expected: FAIL — cannot resolve `@/components/AgentStaffCreateForm`.

- [ ] **Step 3: Implement** — `apps/web/components/AgentStaffCreateForm.tsx`

```tsx
"use client";

import { FormEvent, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";

export const STAFF_URL = "/api/v1/workflows/overseas/agent/team/staff";

type Created = { member: { code: string; email: string }; email_status: string };

// AGN-002 (DEC-SCOPE-040 S3/S4): a Master adds a staff login. The staff member sets their own password from the emailed link;
// the Master never sees it. The entry is kept on any failure so it can be corrected and re-sent.
export default function AgentStaffCreateForm({ onCreated }: { onCreated: () => void }) {
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const inFlight = useRef(false);
  const messageRef = useRef<HTMLDivElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setSending(true);
    setMessage(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const phone = String(data.get("phone") ?? "").trim();
    const outcome = await sendJson(STAFF_URL, "POST", { full_name: String(data.get("full_name") ?? ""), email: String(data.get("email") ?? ""), phone: phone || null });
    inFlight.current = false;
    setSending(false);
    if (!outcome.ok) {
      setMessage({ text: outcome.message, failed: true });
    } else {
      const { member, email_status } = outcome.data as unknown as Created;
      setMessage({
        text: email_status === "sent" ? `${member.code} created. A set-password link was emailed to ${member.email}.` : `${member.code} created, but the email was not delivered. Use Reset to send a new link.`,
        failed: false,
      });
      form.reset();
      onCreated();
    }
    messageRef.current?.focus();
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Add a staff member">
      <h4>Add staff</h4>
      <div className="field"><label htmlFor="staff-full-name">Full name</label><input id="staff-full-name" name="full_name" maxLength={160} required autoComplete="off" /></div>
      <div className="field"><label htmlFor="staff-email">Email</label><input id="staff-email" name="email" type="email" maxLength={320} required autoComplete="off" /></div>
      <div className="field"><label htmlFor="staff-phone">Phone (optional)</label><input id="staff-phone" name="phone" type="tel" maxLength={40} autoComplete="off" /></div>
      <button className="btn" disabled={sending}>{sending ? "Adding…" : "Add staff"}</button>
      <div ref={messageRef} tabIndex={-1} className={message ? (message.failed ? "form-error" : "form-message") : undefined} role="status" aria-live="polite" style={message ? { marginTop: 8, overflowWrap: "anywhere" } : undefined}>
        {message?.text}
      </div>
    </form>
  );
}
```

- [ ] **Step 4: Run** — WEB(`tests/components/AgentStaffCreateForm.test.tsx`). Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/AgentStaffCreateForm.tsx apps/web/tests/components/AgentStaffCreateForm.test.tsx
git commit -m "feat(agn-002): add-staff form"
```

---

### Task 9: `AgentStaffRow`

**Files:**
- Create: `apps/web/components/AgentStaffRow.tsx`
- Test: `apps/web/tests/components/AgentStaffRow.test.tsx`

**Interfaces:**
- Consumes: `STAFF_URL` (Task 8), `sendJson`; routes from Task 5.
- Produces: `export type StaffMember = { id: string; code: string; full_name: string; email: string; phone: string | null; status: "active" | "deactivated"; setup: "pending_setup" | "link_expired" | null }`; `default function AgentStaffRow({ member, onChanged }: { member: StaffMember; onChanged: (message: string) => void })` rendering one `<li className="card">`.

- [ ] **Step 1: Write the failing test** — `apps/web/tests/components/AgentStaffRow.test.tsx`

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStaffRow, { type StaffMember } from "@/components/AgentStaffRow";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const active: StaffMember = { id: "s1", code: "ABC-S001", full_name: "Rahul Kumar", email: "rahul@example.local", phone: "+91 1", status: "active", setup: null };

function renderRow(member: StaffMember = active) {
  const onChanged = vi.fn();
  render(<ul><AgentStaffRow member={member} onChanged={onChanged} /></ul>);
  return onChanged;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentStaffRow (AGN-002)", () => {
  it.each([
    [{ status: "deactivated" }, "Deactivated"],
    [{ setup: "pending_setup" }, "Set-up pending"],
    [{ setup: "link_expired" }, "Link expired"],
  ] as const)("labels %o as text", (patch, label) => {
    renderRow({ ...active, ...patch } as StaffMember);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("edits name and phone, Escape cancels and returns focus", async () => {
    const mock = vi.fn().mockResolvedValue(res({ member: { ...active, full_name: "Rahul K" } }));
    vi.stubGlobal("fetch", mock);
    const onChanged = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Edit Rahul Kumar" }));
    fireEvent.keyDown(screen.getByLabelText("Full name"), { key: "Escape" });
    expect(screen.getByRole("button", { name: "Edit Rahul Kumar" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Edit Rahul Kumar" }));
    expect(screen.getByText("rahul@example.local")).toBeInTheDocument(); // email shown, not editable
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Rahul K" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await vi.waitFor(() => onChanged.mock.calls[0][0])).toBe("ABC-S001 updated.");
    expect(mock.mock.calls[0][0]).toBe("/api/v1/workflows/overseas/agent/team/staff/s1");
    expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({ full_name: "Rahul K", phone: "+91 1" });
  });

  it("deactivates after confirmation; Cancel returns focus", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ member: { ...active, status: "deactivated" } })));
    const onChanged = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Rahul Kumar" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Deactivate Rahul Kumar" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Rahul Kumar" }));
    expect(screen.getByRole("button", { name: "Confirm deactivate" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    expect(await vi.waitFor(() => onChanged.mock.calls[0][0])).toBe("ABC-S001 Rahul Kumar deactivated. They have been signed out.");
  });

  it("reactivates and reminds to Reset when set-up never finished", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ member: { ...active, setup: "link_expired" } })));
    const onChanged = renderRow({ ...active, status: "deactivated", setup: "link_expired" });
    fireEvent.click(screen.getByRole("button", { name: "Reactivate Rahul Kumar" }));
    expect(await vi.waitFor(() => onChanged.mock.calls[0][0])).toBe("ABC-S001 Rahul Kumar reactivated. They have not set a password yet: use Reset to send a new link.");
  });

  it("resets after confirmation and shows a 429 on the row", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "A link was just sent; wait 42 seconds before resetting again" }, 429)));
    const onChanged = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Reset Rahul Kumar" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm reset" }));
    expect(await screen.findByText("A link was just sent; wait 42 seconds before resetting again")).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("offers Reset and Deactivate only while active, Reactivate only while deactivated", () => {
    renderRow({ ...active, status: "deactivated" });
    expect(screen.queryByRole("button", { name: /^Reset / })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Deactivate / })).toBeNull();
    expect(screen.getByRole("button", { name: "Reactivate Rahul Kumar" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** — WEB(`tests/components/AgentStaffRow.test.tsx`). Expected: FAIL — cannot resolve `@/components/AgentStaffRow`.

- [ ] **Step 3: Implement** — `apps/web/components/AgentStaffRow.tsx`

```tsx
"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";

import { STAFF_URL } from "./AgentStaffCreateForm";

export type StaffMember = { id: string; code: string; full_name: string; email: string; phone: string | null; status: "active" | "deactivated"; setup: "pending_setup" | "link_expired" | null };
type Mode = "view" | "edit" | "confirm-deactivate" | "confirm-reset";

const BADGE = (m: StaffMember) => (m.status === "deactivated" ? "Deactivated" : m.setup === "link_expired" ? "Link expired" : m.setup === "pending_setup" ? "Set-up pending" : null);

// AGN-002: one staff member with its actions. Confirmations are inline (AgentTeamPanel's pattern): focus goes to Confirm, and
// Cancel/Escape return it to the button that opened them. Server messages (409/429) show on the row.
export default function AgentStaffRow({ member, onChanged }: { member: StaffMember; onChanged: (message: string) => void }) {
  const [mode, setMode] = useState<Mode>("view");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const returnFocusTo = useRef<string | null>(null);
  const id = (action: string) => `staff-${action}-${member.id}`;
  const who = `${member.code} ${member.full_name}`;

  useEffect(() => {
    if (mode === "view" && returnFocusTo.current) {
      document.getElementById(returnFocusTo.current)?.focus();
      returnFocusTo.current = null;
    }
  }, [mode]);

  function close(action: string) {
    returnFocusTo.current = id(action);
    setMode("view");
  }

  async function run(path: string, method: "POST" | "PATCH", body: unknown, done: (data: Record<string, unknown>) => string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    const outcome = await sendJson(`${STAFF_URL}/${member.id}${path}`, method, body);
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    setMode("view");
    onChanged(done(outcome.data));
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const phone = String(data.get("phone") ?? "").trim();
    run("", "PATCH", { full_name: String(data.get("full_name") ?? ""), phone: phone || null }, () => `${member.code} updated.`);
  }

  const badge = BADGE(member);
  const active = member.status === "active";
  const confirm = (label: string, text: string, onConfirm: () => void, back: string) => (
    <div role="group" aria-label={`${label} ${member.full_name}`} style={{ marginTop: 8 }}>
      <p style={{ fontSize: 13 }}>{text}</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button className="btn small" autoFocus disabled={busy} onClick={onConfirm}>{busy ? "Working…" : label}</button>
        <button className="btn secondary small" disabled={busy} onClick={() => close(back)}>Cancel</button>
      </div>
    </div>
  );

  return (
    <li className="card" style={{ marginBottom: 8, overflowWrap: "anywhere" }}>
      <strong>{member.code}</strong> {member.full_name} <span className="muted" style={{ fontSize: 13 }}>{member.email}{member.phone ? ` · ${member.phone}` : ""}</span> {badge && <span className="badge">{badge}</span>}
      {mode === "edit" && (
        <form className="form" onSubmit={save} onKeyDown={(e) => e.key === "Escape" && close("edit")} aria-label={`Edit ${member.full_name}`} style={{ marginTop: 8 }}>
          <div className="field"><label htmlFor={id("name")}>Full name</label><input id={id("name")} name="full_name" defaultValue={member.full_name} maxLength={160} required autoFocus /></div>
          <div className="field"><label htmlFor={id("phone")}>Phone (optional)</label><input id={id("phone")} name="phone" type="tel" defaultValue={member.phone ?? ""} maxLength={40} /></div>
          <p className="muted" style={{ fontSize: 13 }}>Email can&apos;t be changed.</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            <button type="button" className="btn secondary small" disabled={busy} onClick={() => close("edit")}>Cancel</button>
          </div>
        </form>
      )}
      {mode === "confirm-deactivate" && confirm("Confirm deactivate", `Deactivate ${member.full_name}? They will be signed out and can no longer sign in.`, () => run("/deactivate", "POST", {}, () => `${who} deactivated. They have been signed out.`), "deactivate")}
      {mode === "confirm-reset" && confirm("Confirm reset", `Reset ${member.full_name}'s login? Their password stops working, they are signed out, and a new set-password link is emailed to them.`, () => run("/reset", "POST", {}, (data) => (data.email_status === "sent" ? `A new set-password link was emailed to ${member.full_name}.` : `${member.full_name}'s login was reset, but the email was not delivered. Try Reset again in a minute.`)), "reset")}
      {mode === "view" && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
          <button id={id("edit")} className="btn secondary small" aria-label={`Edit ${member.full_name}`} onClick={() => setMode("edit")}>Edit</button>
          {active ? (
            <>
              <button id={id("reset")} className="btn secondary small" aria-label={`Reset ${member.full_name}`} onClick={() => setMode("confirm-reset")}>Reset</button>
              <button id={id("deactivate")} className="btn secondary small" aria-label={`Deactivate ${member.full_name}`} onClick={() => setMode("confirm-deactivate")}>Deactivate</button>
            </>
          ) : (
            <button className="btn secondary small" aria-label={`Reactivate ${member.full_name}`} disabled={busy} onClick={() => run("/reactivate", "POST", {}, () => `${who} reactivated.${member.setup ? " They have not set a password yet: use Reset to send a new link." : ""}`)}>
              {busy ? "Working…" : "Reactivate"}
            </button>
          )}
        </div>
      )}
      {error && <div className="form-error" role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>{error}</div>}
    </li>
  );
}
```

- [ ] **Step 4: Run** — WEB(`tests/components/AgentStaffRow.test.tsx`). Expected: PASS. If the file exceeds 200 lines, extract the `confirm` block into a local `InlineConfirm` component in the same file (no behaviour change) and rerun.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/AgentStaffRow.tsx apps/web/tests/components/AgentStaffRow.test.tsx
git commit -m "feat(agn-002): staff row with edit, deactivate, reactivate and reset"
```

---

### Task 10: `AgentStaffPanel` and Team-screen wiring

**Files:**
- Create: `apps/web/components/AgentStaffPanel.tsx`
- Modify: `apps/web/components/WorkflowPanel.tsx` (the `showAgentTeam` render)
- Test: `apps/web/tests/components/AgentStaffPanel.test.tsx`

**Interfaces:**
- Consumes: `STAFF_URL`, `AgentStaffCreateForm` (Task 8); `AgentStaffRow`, `StaffMember` (Task 9); `isPage`, `Page` (`@/lib/apiErrors`); `GET /team/staff` (Task 4).
- Produces: `default function AgentStaffPanel()`.

- [ ] **Step 1: Write the failing test** — `apps/web/tests/components/AgentStaffPanel.test.tsx`

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStaffPanel from "@/components/AgentStaffPanel";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const staff = (n: number) => ({ id: `s${n}`, code: `ABC-S${String(n).padStart(3, "0")}`, full_name: `Staff ${n}`, email: `s${n}@example.local`, phone: null, status: "active", setup: null });
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentStaffPanel (AGN-002)", () => {
  it("shows loading, then the list", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([staff(1)]))));
    render(<AgentStaffPanel />);
    expect(screen.getByText("Loading staff…")).toBeInTheDocument();
    expect(await screen.findByText("ABC-S001")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Staff pages" })).toBeNull();
  });

  it("shows an empty state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([]))));
    render(<AgentStaffPanel />);
    expect(await screen.findByText("No staff yet. Add your first staff member below.")).toBeInTheDocument();
  });

  it("shows an error with Retry, including for a non-page body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res("<html>", 200)).mockResolvedValueOnce(res(page([staff(1)]))));
    render(<AgentStaffPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("ABC-S001")).toBeInTheDocument();
  });

  it("pages through staff", async () => {
    const mock = vi.fn()
      .mockResolvedValueOnce(res(page(Array.from({ length: 20 }, (_, i) => staff(i + 1)), 21)))
      .mockResolvedValueOnce(res(page([staff(21)], 21, 20)));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffPanel />);
    const pager = await screen.findByRole("navigation", { name: "Staff pages" });
    expect(within(pager).getByText("Showing 1–20 of 21")).toBeInTheDocument();
    expect(within(pager).getByRole("button", { name: "Previous page" })).toBeDisabled();
    fireEvent.click(within(pager).getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("ABC-S021")).toBeInTheDocument();
    expect(mock.mock.calls[1][0]).toBe("/api/v1/workflows/overseas/agent/team/staff?limit=20&offset=20");
  });

  it("steps back a page when the current page comes back empty", async () => {
    const mock = vi.fn()
      .mockResolvedValueOnce(res(page(Array.from({ length: 20 }, (_, i) => staff(i + 1)), 21)))
      .mockResolvedValueOnce(res(page([], 20, 20)))
      .mockResolvedValueOnce(res(page(Array.from({ length: 20 }, (_, i) => staff(i + 1)), 20)));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffPanel />);
    fireEvent.click(within(await screen.findByRole("navigation", { name: "Staff pages" })).getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("ABC-S001")).toBeInTheDocument();
    expect(mock.mock.calls[2][0]).toBe("/api/v1/workflows/overseas/agent/team/staff?limit=20&offset=0");
  });

  it("announces a row change and reloads", async () => {
    const mock = vi.fn()
      .mockResolvedValueOnce(res(page([staff(1)])))
      .mockResolvedValueOnce(res({ member: { ...staff(1), status: "deactivated" } }))
      .mockResolvedValueOnce(res(page([{ ...staff(1), status: "deactivated" }])));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Staff 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivate" }));
    expect(await screen.findByText("ABC-S001 Staff 1 deactivated. They have been signed out.")).toBeInTheDocument();
    expect(await screen.findByText("Deactivated")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** — WEB(`tests/components/AgentStaffPanel.test.tsx`). Expected: FAIL — cannot resolve `@/components/AgentStaffPanel`.

- [ ] **Step 3: Implement** — `apps/web/components/AgentStaffPanel.tsx`

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";

import { isPage, type Page } from "@/lib/apiErrors";

import AgentStaffCreateForm, { STAFF_URL } from "./AgentStaffCreateForm";
import AgentStaffRow, { type StaffMember } from "./AgentStaffRow";

const PAGE_SIZE = 20;

// AGN-002 (DEC-SCOPE-040): the agency's staff logins, 20 per page, below the Masters on the Team screen. Results of row actions
// are announced here; the add form announces its own.
export default function AgentStaffPanel() {
  const [data, setData] = useState<Page<StaffMember> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [offset, setOffset] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback((at: number) => {
    setLoadFailed(false);
    fetch(`${STAFF_URL}?limit=${PAGE_SIZE}&offset=${at}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((body: unknown) => {
        if (!isPage<StaffMember>(body)) throw new Error("not a page");
        // A page emptied by a change (here or by another Master) steps back one page.
        if (body.items.length === 0 && at > 0) return setOffset(Math.max(0, at - PAGE_SIZE));
        setData(body);
      })
      .catch(() => setLoadFailed(true));
  }, []);

  useEffect(() => {
    load(offset);
  }, [load, offset]);

  const reload = () => load(offset);

  if (loadFailed) {
    return (
      <div className="action-card">
        <h3>Staff</h3>
        <p className="form-error" role="alert">Unable to load your staff.</p>
        <button className="btn secondary small" onClick={reload}>Retry</button>
      </div>
    );
  }
  if (data === null) {
    return (
      <div className="action-card" aria-busy="true">
        <h3>Staff</h3>
        <p className="muted">Loading staff…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Staff</h3>
      <p className="muted" style={{ fontSize: 13 }}>Staff work on your agency&apos;s students and applications. Only Masters see the team and commissions.</p>
      <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8, overflowWrap: "anywhere" } : undefined}>{notice}</div>
      {data.items.length === 0 ? (
        <p className="muted">No staff yet. Add your first staff member below.</p>
      ) : (
        <ul style={{ paddingLeft: 0, listStyle: "none" }}>
          {data.items.map((m) => <AgentStaffRow key={m.id} member={m} onChanged={(message) => { setNotice(message); reload(); }} />)}
        </ul>
      )}
      {data.total > PAGE_SIZE && (
        <nav aria-label="Staff pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
          <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
          <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
        </nav>
      )}
      <AgentStaffCreateForm onCreated={reload} />
    </div>
  );
}
```

`WorkflowPanel.tsx`: import `AgentStaffPanel from "./AgentStaffPanel"` next to `AgentTeamPanel`, and change `{showAgentTeam && <AgentTeamPanel/>}` to `{showAgentTeam && <AgentTeamPanel/>}{showAgentTeam && <AgentStaffPanel/>}`; update the comment above `showAgentTeam` to "AGN-001/AGN-002: the agency's Masters (list, invite, deactivate) and staff (add, edit, activate, reset)."

- [ ] **Step 4: Run** — WEB(`tests/components/AgentStaffPanel.test.tsx tests/components/AgentStaffRow.test.tsx tests/components/AgentStaffCreateForm.test.tsx tests/components/AgentTeamPanel.test.tsx`). Expected: PASS.

- [ ] **Step 5: Frontend regression + types** — WEB(`run`) (whole vitest suite) and `dc run --rm --no-deps -v … web-test npx tsc --noEmit` and `npx next lint` (same mounts). Expected: PASS, no new warnings.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/AgentStaffPanel.tsx apps/web/components/WorkflowPanel.tsx apps/web/tests/components/AgentStaffPanel.test.tsx
git commit -m "feat(agn-002): staff panel on the Team screen"
```

---

### Task 11: End-to-end spec

**Files:**
- Create: `apps/web/tests/e2e/agn-002-staff.spec.ts`

**Interfaces:**
- Consumes: the whole feature; `activateWithToken` (`tests/e2e/helpers/welcome.ts`); the seeded Overseas Admin (`overseasadmin@edusphere.local` / `Demo@123`) and admin Re-send route (recorded deviation).

- [ ] **Step 1: Write the spec** — `apps/web/tests/e2e/agn-002-staff.spec.ts`

```ts
import { test, expect, type APIRequestContext, type Browser, type Page } from "@playwright/test";

import { activateWithToken, E2E_PASSWORD } from "./helpers/welcome";

// AGN-002 -- a Master adds staff; staff work on students without Team/Commissions; deactivate signs them out; reactivate; reset.
// Requires the stack running with `python -m app.seed` applied. The staff-create response never carries the link token (S3), so
// the spec activates the account the way an admin would re-send it (the admin Re-send response carries it in dev/test).

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/agent/dashboard");
}

async function adminActivate(request: APIRequestContext, email: string) {
  const login = await request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  expect(login.ok()).toBeTruthy();
  const users = await (await request.get("/api/v1/admin/users?role=agent&provisioning_status=pending_setup")).json();
  const staff = users.find((u: { email: string }) => u.email === email);
  const resend = await (await request.post(`/api/v1/admin/users/${staff.id}/welcome-links`)).json();
  await activateWithToken(request, resend.development_welcome_token);
}

async function registerApprovedAgency(page: Page, unique: number) {
  const email = `agn002-m-${unique}@example.local`;
  await page.goto("/overseas/register");
  await page.fill('input[name="full_name"]', "Sigma Master");
  await page.fill('input[name="email"]', email);
  await page.selectOption('select[name="account_type"]', "agent");
  await page.fill('input[name="agency_name"]', `Sigma Overseas ${unique}`);
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/overseas/agent/dashboard");
  await signInAdminAndApprove(page, `Sigma Overseas ${unique}`);
  return email;
}

async function signInAdminAndApprove(page: Page, agency: string) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");
  await page.goto("/overseas/admin/agents");
  await page.locator(".card", { hasText: agency }).getByRole("button", { name: "Approve" }).click();
  await expect(page.locator(".card", { hasText: agency }).getByText("Approved")).toBeVisible();
}

async function staffPage(browser: Browser) {
  const context = await browser.newContext();
  return context.newPage();
}

test("a Master adds staff who work on students; deactivate, reactivate and reset (AGN-002)", async ({ page, browser }) => {
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique);
  const staffEmail = `agn002-s-${unique}@example.local`;

  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await page.goto("/overseas/agent/team");
  await expect(page.getByText("No staff yet. Add your first staff member below.")).toBeVisible();
  const form = page.getByRole("form", { name: "Add a staff member" });
  await form.getByLabel("Full name").fill("Sigma Staff");
  await form.getByLabel("Email").fill(staffEmail);
  await form.getByRole("button", { name: "Add staff" }).click();
  await expect(page.getByText(/SIG\d*-S001 created/)).toBeVisible();
  await expect(page.getByText("Set-up pending")).toBeVisible();

  const staff = await staffPage(browser);
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);
  const sidebar = staff.getByRole("navigation").first();
  await expect(sidebar.getByRole("link", { name: "Students" })).toBeVisible();
  await expect(sidebar.getByRole("link", { name: "Team" })).toHaveCount(0);
  await expect(sidebar.getByRole("link", { name: "Commissions" })).toHaveCount(0);
  await staff.goto("/overseas/agent/team");
  await expect(staff.getByText("Only an agency Master can open this page")).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: "Deactivate Sigma Staff" }).click();
  await page.getByRole("button", { name: "Confirm deactivate" }).click();
  await expect(page.getByText(/deactivated\. They have been signed out\./)).toBeVisible();
  await staff.goto("/overseas/agent/students");
  await expect(staff.getByRole("heading", { name: "Access unavailable" })).toBeVisible();

  await page.getByRole("button", { name: "Reactivate Sigma Staff" }).click();
  await expect(page.getByText(/reactivated\./)).toBeVisible();
  await signIn(staff, staffEmail, E2E_PASSWORD);

  await page.getByRole("button", { name: "Reset Sigma Staff" }).click();
  await page.getByRole("button", { name: "Confirm reset" }).click();
  await expect(page.getByText(/set-password link was emailed|login was reset/)).toBeVisible();
  await staff.goto("/overseas/agent/students");
  await expect(staff.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
  await staff.goto("/overseas/login");
  await staff.fill("#login-email", staffEmail);
  await staff.fill("#login-password", E2E_PASSWORD);
  await staff.click("button:has-text('Sign in securely')");
  await expect(staff).toHaveURL(/\/overseas\/login/);
  await staff.context().close();
});
```

The Master uses the default `page`; `staffPage` opens a page in its own browser context, so the two users never share cookies.

- [ ] **Step 2: Run against the user-started stack** (rebuilt from this branch; the user starts it): `npx playwright test tests/e2e/agn-002-staff.spec.ts tests/e2e/agn-001-multi-tenant.spec.ts tests/e2e/agt-001-registration-approval.spec.ts tests/e2e/agt-002-referrals.spec.ts tests/e2e/agt-003-commission-accrual.spec.ts tests/e2e/agt-004-commission-payout.spec.ts`. Expected: all PASS. On failure, open only that test's trace.

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/agn-002-staff.spec.ts
git commit -m "test(agn-002): end-to-end staff lifecycle"
```

---

### Task 12: Documentation and full regression

**Files:**
- Modify: `docs/architecture/DATA_MODEL.md`, `docs/architecture/API_CONTRACT.md`, `docs/architecture/RBAC_MATRIX.md`, `docs/ux/SCREEN_CATALOG.md`, `docs/quality/RTM.md`, `docs/delivery/ENHANCEMENT_BACKLOG.md` (AGN-002 status)

- [ ] **Step 1: Update the docs** (each an addendum beside the AGN-001 one, same style):
  - `DATA_MODEL.md`: `agent_orgs.staff_seq`, `agent_org_members` role `master|staff` + `uq_agent_org_members_org_role_seq`, `users.session_version`; migration `0047_agent_org_staff`.
  - `API_CONTRACT.md`: the six staff routes (spec §6 table, member shape, errors), `GET /team` Masters only, `GET /auth/me` `agent_member_role`, token claim `sv` and `401 "Session ended"`.
  - `RBAC_MATRIX.md`: a "Staff (agent member role `staff`)" row: students/applications organisation-wide; no team, no commissions; admin legacy approve `422`.
  - `SCREEN_CATALOG.md` `SCR-AGT-007`: Staff section (states, actions), staff nav without Team/Commissions, role label "Agency Staff".
  - `RTM.md`: AGN-002 row: `DEC-SCOPE-040` → AC01–AC10 → tests (file::test) → code → the two recorded deviations.
  - Backlog AGN-002 status: "implemented on `feature/agn-002-staff-logins`; browser validation and independent review pending".

- [ ] **Step 2: Full backend run** — API(`-q`) (whole suite; the session check touches every route). Expected: PASS apart from failures already on `main`; list any with their `main` baseline.

- [ ] **Step 3: Full frontend unit run + types + lint** — WEB(`run`), `tsc --noEmit`, `next lint`. Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/architecture/DATA_MODEL.md docs/architecture/API_CONTRACT.md docs/architecture/RBAC_MATRIX.md docs/ux/SCREEN_CATALOG.md docs/quality/RTM.md docs/delivery/ENHANCEMENT_BACKLOG.md
git commit -m "docs(agn-002): data model, API contract, RBAC, screen catalogue, RTM"
```

- [ ] **Step 5: Hand-off (not completion).** Report test evidence; the feature is **not** complete until browser validation (320/768/1024/1440 px, keyboard-only, screen-reader announcements) and the independent Codex review are done.
