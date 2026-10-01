# AGN-003 Agent Staff Permissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce the `EVID-015` §6 Master-vs-Staff matrix on the existing agent routes. Staff are limited to the student journey, and two optional rows (Verify Documents, Reports) are switched per staff member by a Master and take effect on the next request.

**Architecture:**
- **Storage:** two `BOOLEAN NOT NULL DEFAULT false` columns on `agent_org_members` (migration `0048`).
- **Reads:** `get_current_user` already eager-loads the membership on every request, so the flags are fresh without caching.
- **Checks:** `core/rbac.py` gains `agent_may` / `agent_permissions` beside `is_agent_staff`, called inline at:
  - the portal Reports section
  - a new agent-only branch of the existing document verify route
- **Toggle route:** a Master sets the flags through `PUT …/team/staff/{id}/permissions`, reusing the AGN-002 lock, scope, audit and commit helpers.
- **Frontend:**
  - a Permissions form in the staff row
  - Reports hidden from staff navigation unless their toggle is on
  - the existing counselor review panel, generalised with props, reused on the agent Documents page

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, PostgreSQL 16; Next.js 15 (App Router), React 19, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-01-agn-003-staff-permissions-design.md`. Read it with this plan; §3 is the matrix. Decision: `DEC-SCOPE-044` (P1–P9).

## Global Constraints

**Scope**
- AGN-003 only (spec §2).
- No change to:
  - assignment/ownership
  - the counselor/admin verify path (its statements stay byte-identical)
  - `_assigned_application`
  - `/files/*`
  - notifications, support, communications
  - any non-agent route
- No new dependency (Python or npm).

**Migration and data**
- Migration `0051_agent_staff_permissions`, `down_revision = "0047_agent_org_staff"`.
- Columns `can_verify_documents`, `can_view_reports` on `agent_org_members`: `Boolean`, `nullable=False`, `server_default false`.
- No row rewrite.

**API**
- **Permission keys** (column names = API keys) are exactly `can_verify_documents`, `can_view_reports`.
- **Staff member shape** gains `"permissions": {"can_verify_documents": bool, "can_view_reports": bool}`.
- **`/auth/me`** gains `agent_permissions`:
  - `{"can_verify_documents": bool, "can_view_reports": bool}` for an agent with a membership (a Master gets both `true`)
  - `null` otherwise
- **Messages (verbatim)**, as `core/rbac.py` constants:
  - `REPORTS_REFUSED = "Your agency Master hasn't given you access to reports"`
  - `VERIFY_REFUSED = "Your agency Master hasn't given you permission to verify documents"`
  - `REVIEW_MASTER_ONLY = "Only an agency Master can reject documents or request changes"`
- **Messages (verbatim), inline in the route:**
  - `"This document has already been reviewed"` (409)
  - `"Document is outside your assigned scope"` (403, unattached document)
  - `"Document not found"` (404)
- **Messages (existing, unchanged):**
  - `"Only an agency Master can manage the team"`
  - `"Staff member not found"`
  - `"Application is outside your assigned scope"`

**Audit**
- Toggle: `action="agent_org.staff_permissions"`, `entity_type="agent_org"`, `entity_id=str(org.id)`, `outcome="updated"`, `metadata_json={"member_id", "code", "before": {...}, "after": {...}}`.
  - Written **only when a value changes**.
- Agent review: `action="document.verify"`, metadata = `{"verification_status", "notes", "member_role"}` (validated dump; never the raw payload).

**Request/transaction rules**
- **Order inside the agent verify branch:**
  1. toggle check (403)
  2. body validation (422)
  3. staff-outcome check (403)
  4. `SELECT … FOR UPDATE` (404)
  5. scope (403)
  6. pending check (409)
  7. write, notify, audit, commit
- **Lock order for toggles:** organisation row (`lock_org` via `_staff_org`) → staff user row (`_staff_member`). Commit through `_commit_staff_change`.

**Code style**
- Logs: `app.agent_orgs` logger, ids and codes only.
- Test-module imports at the top of each file (ruff clean, no suppressions).
- Frontend reuses existing classes only: `action-card`, `card`, `btn small`, `btn secondary small`, `form`, `field`, `fieldset.form-section`, `form-error`, `form-message`, `muted`, `badge`. No inline colours.

## Deviations from existing tests (record in the RTM)

These are forced by `DEC-SCOPE-044`. They are behaviour changes, not test-only edits.

- `tests/test_agn_002_staff_access.py::test_staff_dashboard_and_reports_leave_out_commission_figures` and `tests/test_agn_002_qa_messages.py::test_staff_pages_never_mention_commissions` create their staff member with `can_view_reports=True`. Reports is off by default now (P1); their "no commission figures" intent is unchanged (Task 3).
- `tests/agn002_helpers.mk_staff` gains keyword arguments `can_verify_documents=False, can_view_reports=False`. Existing callers are unaffected (Task 1).
- `apps/web/tests/components/AgentStaffRow.test.tsx` and `AgentStaffPanel.test.tsx` fixtures gain `permissions`. The staff shape now always carries it (Task 9).
- `apps/web/tests/e2e/agn-002-staff.spec.ts`: its local `signIn` / `adminActivate` / `registerApprovedAgency` move to `tests/e2e/helpers/agency.ts` and are imported. This is a test-only refactor so agn-003 can reuse them; agn-002 must stay green (Task 10).

## Test commands (PowerShell, from the worktree root)

Isolated Compose project `agn003`. **The user builds and starts the stack** (standing preference). The agent only runs one-off `run --rm` containers that mount this worktree's source.

```powershell
# User, once:
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn003 --profile ci build api-test web-test
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn003 --profile ci up -d --wait postgres redis

# Agent:
function dc { docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn003 --profile ci @args }
dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test alembic upgrade head
dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test python -m pytest -q tests/test_agn_003_schema.py
dc run --rm --no-deps -v "${PWD}\apps\web\components:/app/components" -v "${PWD}\apps\web\lib:/app/lib" -v "${PWD}\apps\web\tests:/app/tests" -v "${PWD}\apps\web\app:/app/app" web-test npx vitest run tests/lib/navigation.test.ts
```

**Shorthands used below:**
- **API(x)** = the pytest command with `x` as its arguments.
- **WEB(x)** = the vitest command.
- **MIGRATE** = `alembic upgrade head`.
- **LINT** = `dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test ruff check app tests`.
- **TYPECHECK** = `dc run --rm --no-deps -v "${PWD}\apps\web\components:/app/components" -v "${PWD}\apps\web\lib:/app/lib" -v "${PWD}\apps\web\tests:/app/tests" -v "${PWD}\apps\web\app:/app/app" web-test npx tsc --noEmit`.

**Regression set R** (must stay green after every backend task):

API(`tests/test_agn_001_team.py tests/test_agn_001_tenancy.py tests/test_agn_001_registration_and_gate.py tests/test_agn_001_org_admin.py tests/test_agn_001_prefix.py tests/test_agn_001_schema.py tests/test_agn_002_staff.py tests/test_agn_002_staff_access.py tests/test_agn_002_master_rules.py tests/test_agn_002_sessions.py tests/test_agn_002_schema.py tests/test_agn_002_qa_messages.py tests/test_agt_001_registration_approval.py tests/test_agt_002_referrals.py tests/test_agt_003_commission_accrual.py tests/test_agt_004_commission_payout.py tests/test_ovs_005_documents.py tests/test_sec_001_audit_trail.py`) plus `tests/test_enh_031_*.py`.

The **full backend suite is not run** per feature (the owner runs it every 4–5 stories).

## Review Focus

These are the five failure modes the spec implies that a user is most likely to hit. Each is pinned by the test named in brackets.

1. **A staff member keeps a tab open while the Master switches Reports or Verify off.** Their next request must be refused (`403` with the plain message), not served from a stale value. The same cookie jar is used before and after. [Task 4 `test_toggle_applies_on_next_request`; Task 5 `test_verify_toggle_applies_on_next_request`]
2. **Two people decide the same pending document.** The second agent must get `409` and the first decision must stand. A counselor can still overwrite an agent's decision afterwards. [Task 5 `test_a_second_review_is_refused_and_the_first_stands`, `test_a_counselor_can_still_re_review_an_agent_decision`]
3. **A staff member with Verify sends `rejected` or `changes_required`** through a hand-crafted request or a stale form. It must be `403`, with the document untouched and no student notification. [Task 5 `test_staff_with_verify_cannot_reject_or_request_changes`]
4. **A body that looks right but isn't:** `"true"` as a string, a missing key, an extra key such as `"is_master"`, notes over 10 000 characters. It must be `422` and change nothing. [Task 4 `test_bad_bodies_are_refused`; Task 5 `test_bad_agent_review_bodies_are_refused`]
5. **The counselor's own review queue after the panel is generalised.** Same URL, same three decisions, same success text. A failed load now says so instead of "No documents…". [Task 8 characterisation tests, written before the change]

---

### Task 1: Migration `0048` and the two staff flags

**Files:**
- Create: `apps/api/alembic/versions/0051_agent_staff_permissions.py`
- Modify: `apps/api/app/models.py` (class `AgentOrgMember`, after `deactivated_at`)
- Modify: `apps/api/tests/agn002_helpers.py` (`mk_staff`)
- Test: `apps/api/tests/test_agn_003_schema.py`

**Interfaces:**
- Produces:
  - `AgentOrgMember.can_verify_documents: bool`, `AgentOrgMember.can_view_reports: bool`
  - `mk_staff(db, org, *, full_name="Staff Member", active=True, can_verify_documents=False, can_view_reports=False) -> {"user", "member"}`

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_agn_003_schema.py`

```python
"""AGN-003 -- migration 0048: per-staff permission flags (spec §5, AGN-003-AC09)."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect

from app.models import AgentOrgMember
from tests.agn001_helpers import mk_active_org
from tests.agn002_helpers import mk_staff

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_003_migration_0048", VERSIONS / "0051_agent_staff_permissions.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

FLAGS = ("can_verify_documents", "can_view_reports")


def test_migration_follows_0047():
    assert _migration.revision == "0051_agent_staff_permissions"
    assert _migration.down_revision == "0047_agent_org_staff"


@pytest.mark.asyncio
async def test_flags_are_not_null_with_a_false_server_default(db_session):
    def _cols(sync_conn):
        return {c["name"]: c for c in inspect(sync_conn).get_columns("agent_org_members")}

    cols = await (await db_session.connection()).run_sync(_cols)
    for name in FLAGS:
        assert cols[name]["nullable"] is False
        assert "false" in str(cols[name]["default"]).lower()


@pytest.mark.asyncio
async def test_new_members_start_with_both_flags_off(db_session):
    ctx = await mk_active_org(db_session, name="Flags Default")
    staff = await mk_staff(db_session, ctx["org"])
    for member_id in (staff["member"].id, ctx["member"].id):
        member = await db_session.get(AgentOrgMember, member_id, populate_existing=True)
        assert (member.can_verify_documents, member.can_view_reports) == (False, False)


@pytest.mark.asyncio
async def test_mk_staff_can_switch_flags_on(db_session):
    ctx = await mk_active_org(db_session, name="Flags On")
    staff = await mk_staff(db_session, ctx["org"], can_verify_documents=True, can_view_reports=True)
    member = await db_session.get(AgentOrgMember, staff["member"].id, populate_existing=True)
    assert (member.can_verify_documents, member.can_view_reports) == (True, True)
```

- [ ] **Step 2: Run it to verify it fails**

Run: API(`tests/test_agn_003_schema.py`)
Expected: FAIL. Collection raises `FileNotFoundError` for `0051_agent_staff_permissions.py`.

- [ ] **Step 3: Write the migration** — `apps/api/alembic/versions/0051_agent_staff_permissions.py`

```python
"""AGN-003 -- per-staff optional permissions: Verify Documents and Reports (DEC-SCOPE-044 P1/P2).

Revision ID: 0051_agent_staff_permissions
Revises: 0047_agent_org_staff

docs/superpowers/specs/2026-10-01-agn-003-staff-permissions-design.md §5. Additive: two NOT NULL booleans on agent_org_members with
server default false, so every existing member reads false (existing staff lose Reports until a Master switches it on -- P1) and no
row is rewritten. A column is only added when missing, so a database created from the current models still upgrades. downgrade()
drops the two flags.
"""

import sqlalchemy as sa

from alembic import op

revision = "0051_agent_staff_permissions"
down_revision = "0047_agent_org_staff"
branch_labels = None
depends_on = None

FLAGS = ("can_verify_documents", "can_view_reports")


def _columns() -> set[str]:
    if op.get_context().as_sql:
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("agent_org_members")}


def upgrade() -> None:
    existing = _columns()
    for name in FLAGS:
        if name not in existing:
            op.add_column("agent_org_members", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    for name in reversed(FLAGS):
        op.drop_column("agent_org_members", name)
```

- [ ] **Step 4: Add the model columns** — in `apps/api/app/models.py`, class `AgentOrgMember`, directly after the `deactivated_at` line:

```python
    # AGN-003 (DEC-SCOPE-044 P1/P2): the two optional §6 rows for staff. Stored on every member but never read for a Master
    # (`core.rbac.agent_may` always allows Masters).
    can_verify_documents: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    can_view_reports: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
```

`Boolean` and `text` are already imported on line 5. Extend the class docstring's last sentence with: `AGN-003 adds two per-staff permission flags (DEC-SCOPE-044).`

- [ ] **Step 5: Extend `mk_staff`** — replace the function in `apps/api/tests/agn002_helpers.py`:

```python
async def mk_staff(db, org: AgentOrg, *, full_name: str = "Staff Member", active: bool = True, can_verify_documents: bool = False, can_view_reports: bool = False) -> dict:
    org = await db.get(AgentOrg, org.id, populate_existing=True)
    user = await mk_user(db, role="agent", full_name=full_name, active=active)
    db.add(UserRoleAssignment(user_id=user.id, division="overseas", role="agent", approval_status="approved"))
    org.staff_seq += 1
    member = AgentOrgMember(
        org_id=org.id, user_id=user.id, role="staff", seq=org.staff_seq, code=staff_code(org.prefix, org.staff_seq), status="active" if active else "deactivated",
        can_verify_documents=can_verify_documents, can_view_reports=can_view_reports,
    )
    db.add(member)
    await db.commit()
    return {"user": user, "member": member}
```

- [ ] **Step 6: Migrate and run**

Run: MIGRATE, then API(`tests/test_agn_003_schema.py tests/test_agn_002_schema.py tests/test_agn_001_schema.py`)
Expected: PASS. The two older schema tests stay green because they assert "one head", not a pinned head.

- [ ] **Step 7: Lint and commit**

Run: LINT. Expected: `All checks passed!`

```bash
git add apps/api/alembic/versions/0051_agent_staff_permissions.py apps/api/app/models.py apps/api/tests/agn002_helpers.py apps/api/tests/test_agn_003_schema.py
git commit -m "feat(agn-003): migration 0048 -- per-staff Verify Documents and Reports flags"
```

---

### Task 2: `agent_may` / `agent_permissions` and `/auth/me`

**Files:**
- Modify: `apps/api/app/core/rbac.py` (after `is_agent_staff`)
- Modify: `apps/api/app/schemas.py` (`UserOut`)
- Modify: `apps/api/app/api/auth.py` (`me`)
- Test: `apps/api/tests/test_agn_003_permissions.py` (created here, extended in Task 4)

**Interfaces:**
- Consumes: the Task 1 columns.
- Produces:
  - `rbac.STAFF_PERMISSIONS: tuple[str, str]`
  - `rbac.agent_may(user, permission: str) -> bool`
  - `rbac.agent_permissions(user) -> dict[str, bool] | None`
  - `rbac.REPORTS_REFUSED`, `rbac.VERIFY_REFUSED`, `rbac.REVIEW_MASTER_ONLY` (str)
  - `UserOut.agent_permissions: dict[str, bool] | None`

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/test_agn_003_permissions.py`

```python
"""AGN-003 -- per-staff permissions: effective permissions on /auth/me, the Master's toggle route, Reports gating, next-request
effect (spec §6, §8; AGN-003-AC03, AC05, AC06, AC08)."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import AgentOrg, AgentOrgMember, AuditLog
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import STAFF, mk_staff

ME = "/api/v1/auth/me"
REPORTS = "/api/v1/portal/overseas/agent/reports"
NONE_ON = {"can_verify_documents": False, "can_view_reports": False}
ALL_ON = {"can_verify_documents": True, "can_view_reports": True}


@pytest.mark.asyncio
async def test_auth_me_reports_effective_permissions(db_session):
    ctx = await mk_active_org(db_session, name=f"Me Perms {uniq()}")
    plain = await mk_staff(db_session, ctx["org"], full_name="Plain Staff")
    reports_only = await mk_staff(db_session, ctx["org"], full_name="Reports Staff", can_view_reports=True)
    async with client_for(plain["user"].email) as c:
        assert (await c.get(ME)).json()["agent_permissions"] == NONE_ON
    async with client_for(reports_only["user"].email) as c:
        assert (await c.get(ME)).json()["agent_permissions"] == {"can_verify_documents": False, "can_view_reports": True}
    async with client_for(ctx["master"].email) as m:
        assert (await m.get(ME)).json()["agent_permissions"] == ALL_ON  # a Master is never limited (P2)
    student = await mk_user(db_session, role="overseas_student")
    async with client_for(student.email) as s:
        assert (await s.get(ME)).json()["agent_permissions"] is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: API(`tests/test_agn_003_permissions.py`)
Expected: FAIL with `KeyError: 'agent_permissions'`.

- [ ] **Step 3: Implement the helpers** — in `apps/api/app/core/rbac.py`, append after `is_agent_staff`:

```python
# AGN-003 (DEC-SCOPE-044): the two optional §6 rows. The column names on AgentOrgMember are also the API keys.
STAFF_PERMISSIONS = ("can_verify_documents", "can_view_reports")
REPORTS_REFUSED = "Your agency Master hasn't given you access to reports"
VERIFY_REFUSED = "Your agency Master hasn't given you permission to verify documents"
REVIEW_MASTER_ONLY = "Only an agency Master can reject documents or request changes"


def agent_may(user, permission: str) -> bool:
    """AGN-003 (DEC-SCOPE-044 P1/P2): whether the caller may use an optional §6 row. Masters (and every non-staff caller -- route
    role checks run first) are never limited; staff follow their own flag. Reads the membership `get_current_user` eager-loads on
    every request, so a Master's change applies on the staff member's next request."""

    assert permission in STAFF_PERMISSIONS, permission
    if not is_agent_staff(user):
        return True
    return bool(getattr(user.agent_membership, permission))


def agent_permissions(user) -> dict[str, bool] | None:
    """The effective permissions an agency member's portal shows (GET /auth/me); None for anyone without a membership."""

    if user.role != "agent" or user.agent_membership is None:
        return None
    return {name: agent_may(user, name) for name in STAFF_PERMISSIONS}
```

- [ ] **Step 4: Expose it on `/auth/me`**

In `apps/api/app/schemas.py`, class `UserOut`, add directly after `agent_member_role`:

```python
    # AGN-003: set by GET /auth/me only -- effective permissions (a Master gets both True); None for non-agents.
    agent_permissions: dict[str, bool] | None = None
```

In `apps/api/app/api/auth.py`:
- Extend the `app.core.rbac` import (or add `from app.core.rbac import agent_permissions` beside the existing imports).
- In `me`, before `return out`, add:

```python
    out.agent_permissions = agent_permissions(user)
```

- [ ] **Step 5: Run the tests**

Run: API(`tests/test_agn_003_permissions.py tests/test_agn_002_staff_access.py::test_auth_me_reports_the_member_role`)
Expected: PASS.

- [ ] **Step 6: Lint and commit**

```bash
git add apps/api/app/core/rbac.py apps/api/app/schemas.py apps/api/app/api/auth.py apps/api/tests/test_agn_003_permissions.py
git commit -m "feat(agn-003): effective staff permissions in rbac and on /auth/me"
```

---

### Task 3: Reports is refused to staff without the toggle

**Files:**
- Modify: `apps/api/app/api/portal.py:5` (import), `:34-36` (section check)
- Modify: `apps/api/tests/test_agn_002_staff_access.py:44-54`, `apps/api/tests/test_agn_002_qa_messages.py:60-69` (recorded deviation)
- Test: `apps/api/tests/test_agn_003_permissions.py`

**Interfaces:**
- Consumes: `agent_may`, `REPORTS_REFUSED` (Task 2), the `mk_staff` flags (Task 1).
- Produces: `GET /portal/overseas/agent/reports` refuses staff whose `can_view_reports` is off, with `403 REPORTS_REFUSED`.

- [ ] **Step 1: Write the failing tests** — append to `apps/api/tests/test_agn_003_permissions.py`:

```python
@pytest.mark.asyncio
async def test_reports_is_off_for_staff_by_default(db_session):
    ctx = await mk_active_org(db_session, name=f"Reports Off {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as c:
        response = await c.get(REPORTS)
    assert response.status_code == 403
    assert response.json()["detail"] == "Your agency Master hasn't given you access to reports"


@pytest.mark.asyncio
async def test_reports_on_shows_the_staff_report_without_commission(db_session):
    ctx = await mk_active_org(db_session, name=f"Reports On {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], can_view_reports=True)
    async with client_for(staff["user"].email) as c:
        response = await c.get(REPORTS)
    assert response.status_code == 200
    assert "commission" not in str(response.json()).lower()


@pytest.mark.asyncio
async def test_masters_always_see_reports(db_session):
    ctx = await mk_active_org(db_session, name=f"Reports Master {uniq()}")
    async with client_for(ctx["master"].email) as m:
        response = await m.get(REPORTS)
    assert response.status_code == 200 and "Paid commission" in str(response.json())
```

- [ ] **Step 2: Run them to verify they fail**

Run: API(`tests/test_agn_003_permissions.py -k reports`)
Expected: `test_reports_is_off_for_staff_by_default` FAILS (200 != 403); the other two pass.

- [ ] **Step 3: Implement** — in `apps/api/app/api/portal.py`:
- Change the import to `from app.core.rbac import REPORTS_REFUSED, agent_denial_reason, agent_may, is_agent_staff`.
- After the existing `team`/`commissions` staff check, add:

```python
    # AGN-003 (DEC-SCOPE-044 P1): Reports is an optional §6 row -- off for staff until their Master switches it on.
    if section == "reports" and user.role == "agent" and not agent_may(user, "can_view_reports"):
        raise HTTPException(403, REPORTS_REFUSED)
```

- [ ] **Step 4: Update the two AGN-002 tests (recorded deviation)**
- In `tests/test_agn_002_staff_access.py`, test `test_staff_dashboard_and_reports_leave_out_commission_figures`, replace `staff = await mk_staff(db_session, ctx["org"])` with:

```python
    # AGN-003 (DEC-SCOPE-044 P1): Reports is off for staff by default; this test keeps its intent with it switched on.
    staff = await mk_staff(db_session, ctx["org"], can_view_reports=True)
```

- Make the same replacement, with the same comment, in `tests/test_agn_002_qa_messages.py`, test `test_staff_pages_never_mention_commissions`.

- [ ] **Step 5: Run**

Run: API(`tests/test_agn_003_permissions.py tests/test_agn_002_staff_access.py tests/test_agn_002_qa_messages.py`)
Expected: PASS.

- [ ] **Step 6: Lint and commit**

```bash
git add apps/api/app/api/portal.py apps/api/tests/test_agn_003_permissions.py apps/api/tests/test_agn_002_staff_access.py apps/api/tests/test_agn_002_qa_messages.py
git commit -m "feat(agn-003): staff Reports page follows the Reports toggle (off by default)"
```

---

### Task 4: The Master's toggle route `PUT …/team/staff/{id}/permissions`

**Files:**
- Modify: `apps/api/app/schemas.py` (new `AgentStaffPermissions` after `AgentStaffUpdate`)
- Modify: `apps/api/app/services/agent_orgs.py` (new `set_staff_permissions` after `reset_staff`)
- Modify: `apps/api/app/api/agent_team.py` (imports, `_staff_out`, new route after `reset_staff_login`)
- Test: `apps/api/tests/test_agn_003_permissions.py`

**Interfaces:**
- Consumes: `_staff_org`, `_staff_member`, `_staff_audit`, `_commit_staff_change` (AGN-002).
- Produces:
  - `AgentStaffPermissions(can_verify_documents: StrictBool, can_view_reports: StrictBool)`, `extra="forbid"`
  - `set_staff_permissions(db, org, member_id, actor, *, can_verify_documents: bool, can_view_reports: bool) -> tuple[AgentOrgMember, User]`
  - Route `PUT /api/v1/workflows/overseas/agent/team/staff/{member_id}/permissions` → `200 {"member": {..., "permissions": {...}}}`

- [ ] **Step 1: Write the failing tests** — append to `apps/api/tests/test_agn_003_permissions.py`:

```python
def _perms(member_id) -> str:
    return f"{STAFF}/{member_id}/permissions"


async def _audits(db_session, org_id) -> list[AuditLog]:
    return (await db_session.scalars(
        select(AuditLog).where(AuditLog.action == "agent_org.staff_permissions", AuditLog.entity_id == str(org_id)).execution_options(populate_existing=True)
    )).all()


@pytest.mark.asyncio
async def test_a_master_sets_permissions_and_the_change_is_audited(db_session):
    ctx = await mk_active_org(db_session, name=f"Set Perms {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(ctx["master"].email) as m:
        response = await m.put(_perms(staff["member"].id), json={"can_verify_documents": True, "can_view_reports": False})
        assert response.status_code == 200, response.text
        assert response.json()["member"]["permissions"] == {"can_verify_documents": True, "can_view_reports": False}
        listed = (await m.get(STAFF)).json()["items"]
        assert next(i for i in listed if i["id"] == str(staff["member"].id))["permissions"]["can_verify_documents"] is True
    member = await db_session.get(AgentOrgMember, staff["member"].id, populate_existing=True)
    assert (member.can_verify_documents, member.can_view_reports) == (True, False)
    [row] = await _audits(db_session, ctx["org"].id)
    assert row.user_id == ctx["master"].id and row.outcome == "updated"
    assert row.metadata_json == {"member_id": str(staff["member"].id), "code": staff["member"].code, "before": NONE_ON, "after": {"can_verify_documents": True, "can_view_reports": False}}


@pytest.mark.asyncio
async def test_saving_the_same_permissions_again_writes_nothing(db_session):
    ctx = await mk_active_org(db_session, name=f"Noop Perms {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], can_view_reports=True)
    async with client_for(ctx["master"].email) as m:
        response = await m.put(_perms(staff["member"].id), json={"can_verify_documents": False, "can_view_reports": True})
    assert response.status_code == 200
    assert await _audits(db_session, ctx["org"].id) == []


@pytest.mark.asyncio
async def test_permissions_can_be_set_on_a_deactivated_staff_member(db_session):
    ctx = await mk_active_org(db_session, name=f"Deact Perms {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], active=False)
    async with client_for(ctx["master"].email) as m:
        response = await m.put(_perms(staff["member"].id), json=ALL_ON)
    assert response.status_code == 200 and response.json()["member"]["status"] == "deactivated"


@pytest.mark.asyncio
async def test_only_a_master_of_the_same_agency_can_set_permissions(db_session):
    ctx = await mk_active_org(db_session, name=f"Scope Perms {uniq()}")
    other = await mk_active_org(db_session, name=f"Other Perms {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    peer = await mk_staff(db_session, ctx["org"], full_name="Peer Staff")
    async with client_for(other["master"].email) as o:
        response = await o.put(_perms(staff["member"].id), json=ALL_ON)
        assert response.status_code == 404 and response.json()["detail"] == "Staff member not found"
    async with client_for(ctx["master"].email) as m:
        assert (await m.put(_perms(ctx["member"].id), json=ALL_ON)).status_code == 404  # a Master's member id
        assert (await m.put(_perms(uuid.uuid4()), json=ALL_ON)).status_code == 404
    async with client_for(peer["user"].email) as p:
        for target in (staff["member"].id, peer["member"].id):  # another staff member, or themselves
            response = await p.put(_perms(target), json=ALL_ON)
            assert response.status_code == 403 and response.json()["detail"] == "Only an agency Master can manage the team"
    member = await db_session.get(AgentOrgMember, staff["member"].id, populate_existing=True)
    assert (member.can_verify_documents, member.can_view_reports) == (False, False)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {},
    {"can_verify_documents": True},
    {"can_verify_documents": "true", "can_view_reports": False},
    {"can_verify_documents": 1, "can_view_reports": False},
    {"can_verify_documents": True, "can_view_reports": True, "is_master": True},
])
async def test_bad_bodies_are_refused(db_session, body):
    ctx = await mk_active_org(db_session, name=f"Bad Perms {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(ctx["master"].email) as m:
        assert (await m.put(_perms(staff["member"].id), json=body)).status_code == 422
    member = await db_session.get(AgentOrgMember, staff["member"].id, populate_existing=True)
    assert (member.can_verify_documents, member.can_view_reports) == (False, False)


@pytest.mark.asyncio
async def test_a_suspended_agency_cannot_change_permissions(db_session):
    ctx = await mk_active_org(db_session, name=f"Susp Perms {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    org = await db_session.get(AgentOrg, ctx["org"].id, populate_existing=True)
    org.status = "suspended"
    await db_session.commit()
    async with client_for(ctx["master"].email) as m:
        assert (await m.put(_perms(staff["member"].id), json=ALL_ON)).status_code == 403


@pytest.mark.asyncio
async def test_toggle_applies_on_next_request(db_session):  # AGN-003-AC05, Review Focus 1
    ctx = await mk_active_org(db_session, name=f"Next Req {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as s, client_for(ctx["master"].email) as m:
        assert (await s.get(REPORTS)).status_code == 403
        assert (await m.put(_perms(staff["member"].id), json={"can_verify_documents": False, "can_view_reports": True})).status_code == 200
        assert (await s.get(REPORTS)).status_code == 200  # same cookie jar, no sign-in
        assert (await s.get(ME)).json()["agent_permissions"]["can_view_reports"] is True
        assert (await m.put(_perms(staff["member"].id), json=NONE_ON)).status_code == 200
        assert (await s.get(REPORTS)).status_code == 403
    count = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "agent_org.staff_permissions", AuditLog.entity_id == str(ctx["org"].id)))
    assert count == 2
```

- [ ] **Step 2: Run them to verify they fail**

Run: API(`tests/test_agn_003_permissions.py`)
Expected: the new tests FAIL with `405 Method Not Allowed`, or a `KeyError: 'permissions'` on the list.

- [ ] **Step 3: Add the schema** — in `apps/api/app/schemas.py`, after `class AgentStaffUpdate` (`StrictBool` is already imported on line 8):

```python
class AgentStaffPermissions(BaseModel):
    """AGN-003 (DEC-SCOPE-044 P1/P2): one staff member's whole optional-permission set. PUT replaces both; strict booleans and no
    other key, so no other privilege can be named."""

    model_config = {"extra": "forbid"}
    can_verify_documents: StrictBool
    can_view_reports: StrictBool
```

- [ ] **Step 4: Add the service function** — in `apps/api/app/services/agent_orgs.py`, after `reset_staff`:

```python
async def set_staff_permissions(db: AsyncSession, org: AgentOrg, member_id, actor: User, *, can_verify_documents: bool, can_view_reports: bool):
    """No commit; `org` locked. DEC-SCOPE-044 P2/P8: any staff member of the organisation, whatever their status; audited only when
    a value changes (a repeated save writes nothing), with the before/after flags."""
    member, user = await _staff_member(db, org, member_id)
    after = {"can_verify_documents": can_verify_documents, "can_view_reports": can_view_reports}
    before = {name: getattr(member, name) for name in after}
    if before != after:
        for name, value in after.items():
            setattr(member, name, value)
        _staff_audit(db, actor, org, member, "staff_permissions", "updated", before=before, after=after)
    return member, user
```

- [ ] **Step 5: Add the route and the shape field** — in `apps/api/app/api/agent_team.py`:
- Add `AgentStaffPermissions` to the `app.schemas` import and `set_staff_permissions` to the `app.services.agent_orgs` import.
- Update the module docstring's AGN-002 line with: `AGN-003 -- a staff member's optional permissions (DEC-SCOPE-044; spec §8).`
- Replace `_staff_out`:

```python
def _staff_out(member: AgentOrgMember, staff: User, statuses: dict) -> dict:
    """AGN-002 member shape; `setup` is the DEC-SCOPE-019 provisioning status (None once the staff member has a password).
    AGN-003 adds `permissions` (the two optional §6 rows)."""
    return {
        "id": member.id, "code": member.code, "full_name": staff.full_name, "email": staff.email, "phone": staff.phone, "status": member.status,
        "setup": statuses.get(staff.id),
        "permissions": {"can_verify_documents": member.can_verify_documents, "can_view_reports": member.can_view_reports},
    }
```

- Append the route after `reset_staff_login`:

```python
@router.put("/staff/{member_id}/permissions")
async def staff_permissions(member_id: UUID, payload: AgentStaffPermissions, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-003 (DEC-SCOPE-044 P2): replace one staff member's optional permissions. Effective on their next request."""
    org = await _staff_org(db, user)
    member, staff = await set_staff_permissions(db, org, member_id, user, **payload.model_dump())
    return {"member": await _commit_staff_change(db, "agent_org_staff_permissions_updated", org, user, member, staff, await provisioning_statuses(db, [staff.id]))}
```

- [ ] **Step 6: Run**

Run: API(`tests/test_agn_003_permissions.py tests/test_agn_002_staff.py tests/test_agn_002_master_rules.py`)
Expected: PASS. If `test_agn_002_staff.py` compares a whole member dict, it must still pass. A failure there means an exact-dict assertion. Stop and report it; don't edit the test silently.

- [ ] **Step 7: Lint and commit**

```bash
git add apps/api/app/schemas.py apps/api/app/services/agent_orgs.py apps/api/app/api/agent_team.py apps/api/tests/test_agn_003_permissions.py
git commit -m "feat(agn-003): Masters set a staff member's Verify Documents and Reports permissions"
```

---

### Task 5: Agent document review (agent branch of the verify route)

**Files:**
- Create: `apps/api/tests/agn003_helpers.py`
- Modify: `apps/api/app/schemas.py` (new `AgentDocumentReview`)
- Modify: `apps/api/app/api/workflows.py` (imports; new `_agent_document_review` above `verify_document`; one role added plus an early return in `verify_document`)
- Test: `apps/api/tests/test_agn_003_verify.py`

**Interfaces:**
- Consumes:
  - `agent_may`, `is_agent_staff`, `VERIFY_REFUSED`, `REVIEW_MASTER_ONLY` (Task 2)
  - `mk_staff` flags (Task 1)
  - `_assigned_application`, `_notify_user`, `_audit`, `org_member_ids` (existing)
- Produces:
  - `AgentDocumentReview(verification_status: Literal["verified","rejected","changes_required"], notes: str | None)`
  - `agency_document(db, ctx, *, attached=True, status="pending") -> {"student", "university", "application", "document"}`, used by Tasks 5 and 6

- [ ] **Step 1: Write the shared fixture helper** — `apps/api/tests/agn003_helpers.py`

```python
"""AGN-003 test helpers: an agency student with an application and one document (the agent review and §6 matrix tests)."""

import uuid

from app.models import AgentStudent, Country, OverseasApplication, StudentDocument, University
from tests.agn001_helpers import mk_user

DOC_VERIFY = "/api/v1/workflows/overseas/documents/{}/verify"


async def mk_university(db) -> University:
    country = Country(
        slug=f"agn003-country-{uuid.uuid4().hex[:8]}", name="Testland", overview="", tuition="", living_expenses="",
        visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[],
    )
    db.add(country)
    await db.flush()
    university = University(
        country_id=country.id, slug=f"agn003-university-{uuid.uuid4().hex[:8]}", name="AGN003 University", city="Testville",
        overview="", eligibility="", requirements=[], deadlines=[], scholarships=[],
    )
    db.add(university)
    await db.commit()
    return university


async def agency_document(db, ctx: dict, *, attached: bool = True, status: str = "pending", counselor=None) -> dict:
    """A student linked to the agency's Master, an application referred by that Master, and one document on it (or, with
    attached=False, a document on the student only)."""
    student = await mk_user(db, role="overseas_student", full_name="Agency Student")
    db.add(AgentStudent(agent_id=ctx["master"].id, student_id=student.id, status="active"))
    university = await mk_university(db)
    application = OverseasApplication(
        student_id=student.id, university_id=university.id, agent_id=ctx["master"].id, counselor_id=counselor.id if counselor else None,
        intake="Fall 2027", status="enquiry",
    )
    db.add(application)
    await db.flush()
    document = StudentDocument(
        student_id=student.id, application_id=application.id if attached else None, document_type="Passport",
        file_url="uploads/agn003-passport.pdf", verification_status=status,
    )
    db.add(document)
    await db.commit()
    return {"student": student, "university": university, "application": application, "document": document}
```

- [ ] **Step 2: Write the failing tests** — `apps/api/tests/test_agn_003_verify.py`

```python
"""AGN-003 -- agents decide pending documents of their agency (spec §7; AGN-003-AC04, AC07; DEC-SCOPE-044 P5/P6)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Notification, StudentDocument
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import STAFF, mk_staff
from tests.agn003_helpers import DOC_VERIFY, agency_document

VERIFY_REFUSED = "Your agency Master hasn't given you permission to verify documents"
REVIEW_MASTER_ONLY = "Only an agency Master can reject documents or request changes"


async def _doc(db_session, document_id) -> StudentDocument:
    return await db_session.get(StudentDocument, document_id, populate_existing=True)


async def _notifications(db_session, student_id) -> list[Notification]:
    return (await db_session.scalars(select(Notification).where(Notification.user_id == student_id).execution_options(populate_existing=True))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["verified", "rejected", "changes_required"])
async def test_a_master_decides_a_pending_document(db_session, decision):
    ctx = await mk_active_org(db_session, name=f"Master Review {uniq()}")
    world = await agency_document(db_session, ctx)
    async with client_for(ctx["master"].email) as m:
        response = await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": decision, "notes": "Checked"})
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == decision
    doc = await _doc(db_session, world["document"].id)
    assert (doc.verification_status, doc.verified_by_id, doc.reviewer_notes) == (decision, ctx["master"].id, "Checked")
    assert [n.title for n in await _notifications(db_session, world["student"].id)] == ["Document reviewed"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "document.verify", AuditLog.entity_id == str(doc.id)))
    assert audit.metadata_json == {"verification_status": decision, "notes": "Checked", "member_role": "master"}


@pytest.mark.asyncio
async def test_staff_without_verify_are_refused_before_anything_is_read(db_session):
    ctx = await mk_active_org(db_session, name=f"Staff No Verify {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    world = await agency_document(db_session, ctx)
    async with client_for(staff["user"].email) as s:
        for body in ({"verification_status": "verified"}, {"verification_status": "nonsense"}):
            response = await s.patch(DOC_VERIFY.format(world["document"].id), json=body)
            assert response.status_code == 403 and response.json()["detail"] == VERIFY_REFUSED
        unknown = await s.patch(DOC_VERIFY.format(uuid.uuid4()), json={"verification_status": "verified"})
        assert unknown.status_code == 403  # never 404: a refused caller learns nothing about existence
    assert (await _doc(db_session, world["document"].id)).verification_status == "pending"


@pytest.mark.asyncio
async def test_staff_with_verify_mark_a_document_verified(db_session):
    ctx = await mk_active_org(db_session, name=f"Staff Verify {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], can_verify_documents=True)
    world = await agency_document(db_session, ctx)
    async with client_for(staff["user"].email) as s:
        response = await s.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "verified"})
    assert response.status_code == 200
    doc = await _doc(db_session, world["document"].id)
    assert (doc.verification_status, doc.verified_by_id) == ("verified", staff["user"].id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "document.verify", AuditLog.entity_id == str(doc.id)))
    assert audit.metadata_json["member_role"] == "staff"


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["rejected", "changes_required"])
async def test_staff_with_verify_cannot_reject_or_request_changes(db_session, decision):  # Review Focus 3
    ctx = await mk_active_org(db_session, name=f"Staff Reject {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], can_verify_documents=True)
    world = await agency_document(db_session, ctx)
    async with client_for(staff["user"].email) as s:
        response = await s.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": decision})
    assert response.status_code == 403 and response.json()["detail"] == REVIEW_MASTER_ONLY
    assert (await _doc(db_session, world["document"].id)).verification_status == "pending"
    assert await _notifications(db_session, world["student"].id) == []


@pytest.mark.asyncio
async def test_a_second_review_is_refused_and_the_first_stands(db_session):  # Review Focus 2
    ctx = await mk_active_org(db_session, name=f"Second Review {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], can_verify_documents=True)
    world = await agency_document(db_session, ctx)
    async with client_for(ctx["master"].email) as m, client_for(staff["user"].email) as s:
        assert (await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "rejected"})).status_code == 200
        again = await s.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "verified"})
        assert again.status_code == 409 and again.json()["detail"] == "This document has already been reviewed"
        repeat = await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "rejected"})
        assert repeat.status_code == 409
    assert (await _doc(db_session, world["document"].id)).verification_status == "rejected"
    assert len(await _notifications(db_session, world["student"].id)) == 1


@pytest.mark.asyncio
async def test_a_document_already_decided_by_a_counselor_is_not_overwritten(db_session):
    ctx = await mk_active_org(db_session, name=f"Counselor First {uniq()}")
    world = await agency_document(db_session, ctx, status="verified")
    async with client_for(ctx["master"].email) as m:
        response = await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "rejected"})
    assert response.status_code == 409
    assert (await _doc(db_session, world["document"].id)).verification_status == "verified"


@pytest.mark.asyncio
async def test_a_counselor_can_still_re_review_an_agent_decision(db_session):  # Review Focus 2, P5
    ctx = await mk_active_org(db_session, name=f"Counselor After {uniq()}")
    counselor = await mk_user(db_session, role="counselor")
    world = await agency_document(db_session, ctx, counselor=counselor)
    async with client_for(ctx["master"].email) as m:
        assert (await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "verified"})).status_code == 200
    async with client_for(counselor.email) as c:
        assert (await c.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "rejected"})).status_code == 200
    assert (await _doc(db_session, world["document"].id)).verification_status == "rejected"


@pytest.mark.asyncio
async def test_an_unattached_document_of_an_agency_student_can_be_reviewed(db_session):
    ctx = await mk_active_org(db_session, name=f"Unattached {uniq()}")
    world = await agency_document(db_session, ctx, attached=False)
    async with client_for(ctx["master"].email) as m:
        response = await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "verified"})
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(("attached", "detail"), [(True, "Application is outside your assigned scope"), (False, "Document is outside your assigned scope")])
async def test_another_agencys_document_is_out_of_scope(db_session, attached, detail):
    ctx = await mk_active_org(db_session, name=f"Mine {uniq()}")
    other = await mk_active_org(db_session, name=f"Theirs {uniq()}")
    world = await agency_document(db_session, other, attached=attached)
    async with client_for(ctx["master"].email) as m:
        response = await m.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "verified"})
    assert response.status_code == 403 and response.json()["detail"] == detail
    assert (await _doc(db_session, world["document"].id)).verification_status == "pending"


@pytest.mark.asyncio
async def test_an_unknown_document_is_not_found_for_a_master(db_session):
    ctx = await mk_active_org(db_session, name=f"Unknown Doc {uniq()}")
    async with client_for(ctx["master"].email) as m:
        response = await m.patch(DOC_VERIFY.format(uuid.uuid4()), json={"verification_status": "verified"})
    assert response.status_code == 404 and response.json()["detail"] == "Document not found"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {},
    {"verification_status": "approved"},
    {"verification_status": "verified", "notes": "x" * 10001},
    {"verification_status": "verified", "verified_by_id": "00000000-0000-0000-0000-000000000000"},
])
async def test_bad_agent_review_bodies_are_refused(db_session, body):  # Review Focus 4
    ctx = await mk_active_org(db_session, name=f"Bad Review {uniq()}")
    world = await agency_document(db_session, ctx)
    async with client_for(ctx["master"].email) as m:
        response = await m.patch(DOC_VERIFY.format(world["document"].id), json=body)
    assert response.status_code == 422 and isinstance(response.json()["detail"], list)
    assert (await _doc(db_session, world["document"].id)).verification_status == "pending"


@pytest.mark.asyncio
async def test_verify_toggle_applies_on_next_request(db_session):  # Review Focus 1
    ctx = await mk_active_org(db_session, name=f"Verify Next {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    first, second = await agency_document(db_session, ctx), await agency_document(db_session, ctx)
    on = {"can_verify_documents": True, "can_view_reports": False}
    async with client_for(staff["user"].email) as s, client_for(ctx["master"].email) as m:
        assert (await s.patch(DOC_VERIFY.format(first["document"].id), json={"verification_status": "verified"})).status_code == 403
        assert (await m.put(f"{STAFF}/{staff['member'].id}/permissions", json=on)).status_code == 200
        assert (await s.patch(DOC_VERIFY.format(first["document"].id), json={"verification_status": "verified"})).status_code == 200
        off = {"can_verify_documents": False, "can_view_reports": False}
        assert (await m.put(f"{STAFF}/{staff['member'].id}/permissions", json=off)).status_code == 200
        assert (await s.patch(DOC_VERIFY.format(second["document"].id), json={"verification_status": "verified"})).status_code == 403
```

- [ ] **Step 3: Run them to verify they fail**

Run: API(`tests/test_agn_003_verify.py`)
Expected: FAIL. Agents get `403 "This role cannot perform this operation"` everywhere.

- [ ] **Step 4: Add the review schema** — in `apps/api/app/schemas.py`, after `StudentDocumentCreate` (`Literal` is imported on line 5):

```python
class AgentDocumentReview(BaseModel):
    """AGN-003 (DEC-SCOPE-044 P5/P6, spec §7): an agency member's decision on a pending document. The counselor/admin body of the
    same route is not parsed by this (unchanged)."""

    model_config = {"extra": "forbid"}
    verification_status: Literal["verified", "rejected", "changes_required"]
    notes: str | None = Field(default=None, max_length=10000)
```

- [ ] **Step 5: Implement the agent branch** — in `apps/api/app/api/workflows.py`:

1. **Imports:**
   - `from fastapi.exceptions import RequestValidationError`
   - `from pydantic import ValidationError`
   - extend `from app.core.rbac import …` with `REVIEW_MASTER_ONLY, VERIFY_REFUSED, agent_may`
   - add `AgentDocumentReview` to the `app.schemas` import

2. **Insert directly above `@router.patch("/overseas/documents/{document_id}/verify")`:**

```python
async def _agent_document_review(db: AsyncSession, user: User, document_id: UUID, payload: dict) -> dict:
    """AGN-003 (DEC-SCOPE-044 P3/P5/P6, spec §7): an agency member decides a PENDING document of their agency. Permission checks
    come before any read (a refused caller learns nothing about the document); the row lock makes a second agent decision see the
    first and get 409. Same notification and audit action as the counselor path, with validated metadata only."""
    if not agent_may(user, "can_verify_documents"):
        raise HTTPException(403, VERIFY_REFUSED)
    try:
        review = AgentDocumentReview.model_validate(payload)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    if is_agent_staff(user) and review.verification_status != "verified":
        raise HTTPException(403, REVIEW_MASTER_ONLY)
    item = await db.scalar(select(StudentDocument).where(StudentDocument.id == document_id).with_for_update())
    if not item:
        raise HTTPException(404, "Document not found")
    if item.application_id:
        await _assigned_application(db, user, item.application_id)
    elif not await db.scalar(select(AgentStudent.id).where(AgentStudent.student_id == item.student_id, AgentStudent.agent_id.in_(org_member_ids(user)))):
        raise HTTPException(403, "Document is outside your assigned scope")
    if item.verification_status != "pending":
        raise HTTPException(409, "This document has already been reviewed")
    item.verification_status = review.verification_status
    item.verified_by_id = user.id
    item.reviewer_notes = review.notes
    student = await db.get(User, item.student_id)
    if student:
        await _notify_user(db, student, "Document reviewed", f"{item.document_type}: {item.verification_status}.", "/overseas/student/documents")
    await _audit(db, user, "document.verify", "student_document", item.id, {**review.model_dump(), "member_role": user.agent_membership.role})
    await db.commit()
    return {"id": item.id, "verification_status": item.verification_status}
```

3. **In `verify_document`, change only its first line and add the early return.** Every following line stays byte-identical:

```python
    _require(user, {"counselor", "overseas_admin", "agent"}, "overseas")
    if user.role == "agent":  # AGN-003: the agent path is fully separate; the counselor/admin lines below are unchanged
        return await _agent_document_review(db, user, document_id, payload)
```

- [ ] **Step 6: Run**

Run: API(`tests/test_agn_003_verify.py tests/test_ovs_005_documents.py tests/test_agn_003_permissions.py`)
Expected: PASS. `test_ovs_005_documents.py` proves the counselor path is unchanged.

- [ ] **Step 7: Lint and commit**

```bash
git add apps/api/app/schemas.py apps/api/app/api/workflows.py apps/api/tests/agn003_helpers.py apps/api/tests/test_agn_003_verify.py
git commit -m "feat(agn-003): agents decide pending agency documents; staff verify only with the toggle"
```

---

### Task 6: The §6 matrix test (every ❌ is 403, every ✅ succeeds)

**Files:**
- Test: `apps/api/tests/test_agn_003_matrix.py`

**Interfaces:**
- Consumes: `agency_document`, `DOC_VERIFY` (Task 5); `mk_staff` (Task 1); `STAFF` (AGN-002).
- Produces: AGN-003-AC01/AC02 evidence. It runs green immediately: it proves the matrix that Tasks 3–5 built.

- [ ] **Step 1: Write the matrix test** — `apps/api/tests/test_agn_003_matrix.py`

```python
"""AGN-003-AC01/AC02 -- the EVID-015 §6 matrix as built (spec §3). Staff have both optional toggles OFF here; the toggles' ON side
is tested in test_agn_003_permissions.py and test_agn_003_verify.py. Rows with no route for any agent (Edit/Delete/Assign Student,
Edit Application, Change Application Status, Staff Performance, CRM Settings) are N/A in spec §3 and have nothing to call."""

import pytest

from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import STAFF, mk_staff
from tests.agn003_helpers import agency_document, mk_university

TEAM = "/api/v1/workflows/overseas/agent/team"
VERIFY = "/api/v1/workflows/overseas/documents/{document}/verify"
PORTAL = "/api/v1/portal/overseas/agent"
ALL_ON = {"can_verify_documents": True, "can_view_reports": True}

# (§6 row, method, path, json body). "{name}" placeholders are filled from the world built for each test.
STAFF_REFUSED = [
    ("Staff Management", "get", STAFF, None),
    ("Staff Management", "patch", STAFF + "/{other_staff}", {"full_name": "Renamed"}),
    ("Staff Management", "put", STAFF + "/{other_staff}/permissions", ALL_ON),
    ("Staff Management", "get", TEAM, None),
    ("Staff Management", "get", PORTAL + "/team", None),
    ("Staff Management", "post", TEAM + "/masters", {"full_name": "New Master", "email": "{fresh_email}"}),
    ("Staff Management", "post", TEAM + "/masters/{master_member}/deactivate", None),
    ("Create Staff Login", "post", STAFF, {"full_name": "New Staff", "email": "{fresh_email}"}),
    ("Create Staff Login", "post", STAFF + "/{other_staff}/reset", None),
    ("Deactivate Staff", "post", STAFF + "/{other_staff}/deactivate", None),
    ("Deactivate Staff", "post", STAFF + "/{other_staff}/reactivate", None),
    ("Verify Documents", "patch", VERIFY, {"verification_status": "verified"}),
    ("Reject Documents", "patch", VERIFY, {"verification_status": "rejected"}),
    ("Reject Documents", "patch", VERIFY, {"verification_status": "changes_required"}),
    ("Reports", "get", PORTAL + "/reports", None),
    ("Commission", "get", "/api/v1/workflows/overseas/agent/commissions", None),
    ("Commission", "post", "/api/v1/workflows/overseas/agent/commissions/{zero}/claim", None),
    ("Commission", "get", PORTAL + "/commissions", None),
    ("Add University", "post", "/api/v1/admin/universities", {}),
]

# (§6 row, method, path, json body, expected status) -- succeeds for staff AND for a Master.
BOTH_ALLOWED = [
    ("Dashboard", "get", PORTAL + "/dashboard", None, 200),
    ("Create Student", "post", "/api/v1/workflows/overseas/agent/students", {"student_id": "{unlinked_student}"}, 201),
    ("View Students", "get", "/api/v1/workflows/overseas/agent/students", None, 200),
    ("View Students", "get", PORTAL + "/students", None, 200),
    ("View Students", "get", "/api/v1/lookups/overseas-students", None, 200),
    # A second university: the student already has an application at `{university}`, and the API refuses a duplicate (409).
    ("Create Application", "post", "/api/v1/workflows/overseas/applications", {"university_id": "{other_university}", "student_id": "{student}"}, 201),
    ("View Applications", "get", "/api/v1/workflows/overseas/applications", None, 200),
    ("View Applications", "get", PORTAL + "/applications", None, 200),
    ("View Applications", "get", "/api/v1/lookups/overseas-applications", None, 200),
    ("Upload Documents", "post", "/api/v1/workflows/overseas/documents", {"student_id": "{student}", "application_id": "{application}", "document_type": "Transcript", "file_url": "uploads/agn003-transcript.pdf"}, 201),
    ("Upload Documents", "get", PORTAL + "/documents", None, 200),
    ("University Database", "get", "/api/v1/public/universities", None, 200),
]

# Master-only cells that succeed for a Master.
MASTER_ALLOWED = [
    ("Staff Management", "get", STAFF, None, 200),
    ("Staff Management", "get", TEAM, None, 200),
    ("Staff Management", "get", PORTAL + "/team", None, 200),
    ("Staff Management", "put", STAFF + "/{other_staff}/permissions", ALL_ON, 200),
    ("Create Staff Login", "post", STAFF, {"full_name": "New Staff", "email": "{fresh_email}"}, 201),
    ("Deactivate Staff", "post", STAFF + "/{other_staff}/deactivate", None, 200),
    ("Verify Documents", "patch", VERIFY, {"verification_status": "verified"}, 200),
    ("Reject Documents", "patch", VERIFY, {"verification_status": "rejected"}, 200),
    ("Reports", "get", PORTAL + "/reports", None, 200),
    ("Commission", "get", "/api/v1/workflows/overseas/agent/commissions", None, 200),
    ("Commission", "get", PORTAL + "/commissions", None, 200),
]


def _fill(value, ids: dict):
    if isinstance(value, str):
        return value.format(**ids)
    if isinstance(value, dict):
        return {k: _fill(v, ids) for k, v in value.items()}
    return value


async def _world(db_session) -> tuple[dict, dict, dict]:
    ctx = await mk_active_org(db_session, name=f"Matrix {uniq()}")
    caller = await mk_staff(db_session, ctx["org"], full_name="Caller Staff")
    other = await mk_staff(db_session, ctx["org"], full_name="Other Staff")
    world = await agency_document(db_session, ctx)
    unlinked = await mk_user(db_session, role="overseas_student", full_name="Unlinked Student")
    other_university = await mk_university(db_session)
    ids = {
        "other_staff": other["member"].id, "master_member": ctx["member"].id, "document": world["document"].id,
        "student": world["student"].id, "application": world["application"].id, "university": world["university"].id,
        "other_university": other_university.id,
        "unlinked_student": unlinked.id, "zero": "00000000-0000-0000-0000-000000000000", "fresh_email": f"{uniq('fresh')}@example.local",
    }
    return ctx, caller, ids


async def _call(client, method: str, path: str, body, ids: dict):
    kwargs = {} if body is None else {"json": _fill(body, ids)}
    return await getattr(client, method)(_fill(path, ids), **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize(("row", "method", "path", "body"), STAFF_REFUSED, ids=[f"{r[0]}-{r[1]}-{r[2]}" for r in STAFF_REFUSED])
async def test_staff_refused(db_session, row, method, path, body):  # AGN-003-AC01
    _, caller, ids = await _world(db_session)
    async with client_for(caller["user"].email) as c:
        response = await _call(c, method, path, body, ids)
    assert response.status_code == 403, f"{row}: {response.status_code} {response.text}"


@pytest.mark.asyncio
@pytest.mark.parametrize(("row", "method", "path", "body", "status"), BOTH_ALLOWED, ids=[f"{r[0]}-{r[1]}-{r[2]}" for r in BOTH_ALLOWED])
async def test_staff_allowed(db_session, row, method, path, body, status):  # AGN-003-AC02
    _, caller, ids = await _world(db_session)
    async with client_for(caller["user"].email) as c:
        response = await _call(c, method, path, body, ids)
    assert response.status_code == status, f"{row}: {response.status_code} {response.text}"


@pytest.mark.asyncio
@pytest.mark.parametrize(("row", "method", "path", "body", "status"), BOTH_ALLOWED + MASTER_ALLOWED, ids=[f"{r[0]}-{r[1]}-{r[2]}" for r in BOTH_ALLOWED + MASTER_ALLOWED])
async def test_master_allowed(db_session, row, method, path, body, status):  # AGN-003-AC02
    ctx, _, ids = await _world(db_session)
    async with client_for(ctx["master"].email) as m:
        response = await _call(m, method, path, body, ids)
    assert response.status_code == status, f"{row}: {response.status_code} {response.text}"


@pytest.mark.asyncio
async def test_add_university_is_refused_to_masters_too(db_session):  # spec §3: deliberate departure from §6's Master ✅ (P3)
    ctx, _, ids = await _world(db_session)
    async with client_for(ctx["master"].email) as m:
        response = await _call(m, "post", "/api/v1/admin/universities", {}, ids)
    assert response.status_code == 403
```

- [ ] **Step 2: Run**

Run: API(`tests/test_agn_003_matrix.py`)
Expected: PASS (about 43 cases). A failing case names its §6 row. Fix the product only if it contradicts spec §3; otherwise stop and report the mismatch. Never weaken an assertion.

- [ ] **Step 3: Lint and commit**

```bash
git add apps/api/tests/test_agn_003_matrix.py
git commit -m "test(agn-003): the §6 Master-vs-Staff matrix, every refused and every allowed cell"
```

---

### Task 7: Staff navigation follows the Reports toggle

**Files:**
- Modify: `apps/web/lib/types.ts:9`
- Modify: `apps/web/lib/navigation.ts:77-82`
- Modify: `apps/web/components/PortalPage.tsx` (the `agentNavFor(` call)
- Test: `apps/web/tests/lib/navigation.test.ts`

**Interfaces:**
- Produces:
  - `export type AgentPermissions = { can_verify_documents: boolean; can_view_reports: boolean }` in `lib/types.ts`
  - `User.agent_permissions?: AgentPermissions | null`
  - `agentNavFor(nav: NavItem[], memberRole?: string | null, permissions?: AgentPermissions | null): NavItem[]`

- [ ] **Step 1: Write the failing tests** — add inside the `describe` in `apps/web/tests/lib/navigation.test.ts` (rename the describe to `"agentNavFor (AGN-002, AGN-003)"`):

```ts
  it("hides Reports from staff unless their Reports permission is on (AGN-003)", () => {
    const off = agentNavFor(nav, "staff", { can_verify_documents: true, can_view_reports: false }).map((item) => item.href);
    expect(off).not.toContain("/overseas/agent/reports");
    expect(off).toContain("/overseas/agent/documents");
    expect(agentNavFor(nav, "staff").map((item) => item.href)).not.toContain("/overseas/agent/reports");
    const on = agentNavFor(nav, "staff", { can_verify_documents: false, can_view_reports: true }).map((item) => item.href);
    expect(on).toContain("/overseas/agent/reports");
    expect(on).not.toContain("/overseas/agent/team");
  });

  it("never limits a Master's nav by permissions", () => {
    expect(agentNavFor(nav, "master", { can_verify_documents: false, can_view_reports: false })).toEqual(nav);
  });
```

- [ ] **Step 2: Run it to verify it fails**

Run: WEB(`tests/lib/navigation.test.ts`)
Expected: FAIL. Reports is still present for staff.

- [ ] **Step 3: Implement**

In `apps/web/lib/types.ts`, add above `export type User`:

```ts
// AGN-003 (DEC-SCOPE-044): an agency member's effective optional permissions (GET /auth/me; a Master gets both true).
export type AgentPermissions = { can_verify_documents: boolean; can_view_reports: boolean };
```

and add `agent_permissions?:AgentPermissions|null` to the end of the `User` type (after `agent_member_role?:…`).

In `apps/web/lib/navigation.ts`:
- Add `import type { AgentPermissions } from "@/lib/types";` at the top.
- Replace `agentNavFor`:

```ts
const STAFF_REPORTS = "/overseas/agent/reports";
// AGN-003 (DEC-SCOPE-044 P1): Reports is optional for staff -- shown only once their Master switches it on (the server refuses it
// regardless; this keeps a dead link out of the sidebar). Masters are never limited.
export function agentNavFor(nav: NavItem[], memberRole?: string | null, permissions?: AgentPermissions | null): NavItem[] {
  if (memberRole !== "staff") return nav;
  return nav.filter((item) => !STAFF_HIDDEN.has(item.href) && (item.href !== STAFF_REPORTS || permissions?.can_view_reports === true));
}
```

In `apps/web/components/PortalPage.tsx`, change `agentNavFor(nav,user.agent_member_role)` to `agentNavFor(nav,user.agent_member_role,user.agent_permissions)`.

- [ ] **Step 4: Run**

Run: WEB(`tests/lib/navigation.test.ts`), then TYPECHECK.
Expected: PASS; `tsc` exits 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/types.ts apps/web/lib/navigation.ts apps/web/components/PortalPage.tsx apps/web/tests/lib/navigation.test.ts
git commit -m "feat(agn-003): staff sidebar shows Reports only when their Reports permission is on"
```

---

### Task 8: Reusable document review panel and the agent Documents page

**Files:**
- Modify: `apps/web/components/CounselorDocumentReviewPanel.tsx` (whole file)
- Modify: `apps/web/components/WorkflowPanel.tsx` (one `show…` flag and one JSX insert)
- Test: `apps/web/tests/components/CounselorDocumentReviewPanel.test.tsx` (new), `apps/web/tests/components/WorkflowPanel.agentDocuments.test.tsx` (new)

**Interfaces:**
- Consumes: `User.agent_permissions`, `User.agent_member_role` (Task 7).
- Produces: `CounselorDocumentReviewPanel({ queueUrl?, decisions?, pendingOnly?, emptyText? })` and `export type ReviewDecision = "verified" | "rejected" | "changes_required"`. Every prop is optional; the defaults equal today's counselor panel.

- [ ] **Step 1: Write the characterisation tests first** (they pass on today's code) — create `apps/web/tests/components/CounselorDocumentReviewPanel.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorDocumentReviewPanel from "@/components/CounselorDocumentReviewPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const rows = [
  { id: "d1", student: "Asha Rao", document: "Passport", status: "pending" },
  { id: "d2", student: "Ravi Iyer", document: "Transcript", status: "verified" },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("CounselorDocumentReviewPanel -- counselor defaults (unchanged by AGN-003)", () => {
  it("loads the counselor queue and offers all three decisions", async () => {
    const mock = vi.fn().mockResolvedValueOnce(json({ rows })).mockResolvedValueOnce(json({ id: "d1", verification_status: "rejected" })).mockResolvedValue(json({ rows }));
    vi.stubGlobal("fetch", mock);
    render(<CounselorDocumentReviewPanel />);
    expect(mock).toHaveBeenCalledWith("/api/v1/portal/overseas/counselor/documents");
    fireEvent.click((await screen.findAllByRole("button", { name: "Review" }))[1]); // decided rows stay reviewable for counselors
    const select = screen.getByLabelText("Decision") as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["verified", "rejected", "changes_required"]);
    fireEvent.change(select, { target: { value: "rejected" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit review" }));
    expect(await screen.findByText("Document reviewed -- the student has been notified.")).toBeInTheDocument();
    expect(mock.mock.calls[1][0]).toBe("/api/v1/workflows/overseas/documents/d2/verify");
    expect(JSON.parse(mock.mock.calls[1][1].body)).toEqual({ verification_status: "rejected", notes: null });
  });

  it("says when nothing is waiting", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ rows: [] })));
    render(<CounselorDocumentReviewPanel />);
    expect(await screen.findByText("No documents are awaiting your review yet.")).toBeInTheDocument();
  });
});

describe("CounselorDocumentReviewPanel -- AGN-003 options", () => {
  it("shows a load error with Try again instead of an empty queue", async () => {
    const mock = vi.fn().mockResolvedValueOnce(json({ detail: "boom" }, 500)).mockResolvedValue(json({ rows }));
    vi.stubGlobal("fetch", mock);
    render(<CounselorDocumentReviewPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load documents.");
    expect(screen.queryByText("No documents are awaiting your review yet.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Passport")).toBeInTheDocument();
    expect(mock).toHaveBeenCalledTimes(2);
  });

  it("announces loading", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<CounselorDocumentReviewPanel />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading your review queue…");
  });

  it("with pendingOnly offers Review on pending rows only, from the given queue", async () => {
    const mock = vi.fn().mockResolvedValue(json({ rows }));
    vi.stubGlobal("fetch", mock);
    render(<CounselorDocumentReviewPanel queueUrl="/api/v1/portal/overseas/agent/documents" pendingOnly />);
    expect(await screen.findAllByRole("button", { name: "Review" })).toHaveLength(1);
    expect(mock).toHaveBeenCalledWith("/api/v1/portal/overseas/agent/documents");
  });

  it("with one decision shows a single Mark verified button, no select", async () => {
    const mock = vi.fn().mockResolvedValueOnce(json({ rows })).mockResolvedValueOnce(json({ id: "d1", verification_status: "verified" })).mockResolvedValue(json({ rows }));
    vi.stubGlobal("fetch", mock);
    render(<CounselorDocumentReviewPanel pendingOnly decisions={["verified"]} />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    expect(screen.queryByLabelText("Decision")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Mark verified" }));
    await waitFor(() => expect(mock).toHaveBeenCalledTimes(3));
    expect(JSON.parse(mock.mock.calls[1][1].body)).toEqual({ verification_status: "verified", notes: null });
  });

  it("shows the server's refusal on the row and keeps the form open", async () => {
    const refusal = "Only an agency Master can reject documents or request changes";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json({ rows })).mockResolvedValueOnce(json({ detail: refusal }, 403)));
    render(<CounselorDocumentReviewPanel pendingOnly />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit review" }));
    expect(await screen.findByText(refusal)).toBeInTheDocument();
    expect(screen.getByLabelText("Decision")).toBeInTheDocument();
  });

  it("uses the given empty text", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ rows: [] })));
    render(<CounselorDocumentReviewPanel emptyText="No documents have been uploaded for your agency's applications yet." />);
    expect(await screen.findByText("No documents have been uploaded for your agency's applications yet.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run**

Run: WEB(`tests/components/CounselorDocumentReviewPanel.test.tsx`)
Expected: the two "counselor defaults" tests PASS on today's code, which locks the behaviour. Every "AGN-003 options" test FAILS.

- [ ] **Step 3: Rewrite the panel** — replace `apps/web/components/CounselorDocumentReviewPanel.tsx` with:

```tsx
"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type DocumentRow = { id: string; student: string; document: string; status: string; notes?: string | null };
export type ReviewDecision = "verified" | "rejected" | "changes_required";

const ALL_DECISIONS: ReviewDecision[] = ["verified", "rejected", "changes_required"];
const DECISION_LABELS: Record<ReviewDecision, string> = { verified: "Verified", rejected: "Rejected", changes_required: "Changes required" };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to complete this action.";
}

type Props = { queueUrl?: string; decisions?: ReviewDecision[]; pendingOnly?: boolean; emptyText?: string };

// OVS-005: a Counselor's assigned document queue with a real "View document" download action and Verify/Reject controls.
// AGN-003 (DEC-SCOPE-044 P5/P6): reused on the agent Documents page -- `pendingOnly` (agents decide pending documents only) and
// `decisions` (staff: verified only). Every prop defaults to the counselor panel exactly as before; a failed load now says so.
export default function CounselorDocumentReviewPanel({
  queueUrl = "/api/v1/portal/overseas/counselor/documents",
  decisions = ALL_DECISIONS,
  pendingOnly = false,
  emptyText = "No documents are awaiting your review yet.",
}: Props) {
  const router = useRouter();
  const [rows, setRows] = useState<DocumentRow[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  const load = useCallback(() => {
    fetch(queueUrl)
      .then((res) => {
        if (!res.ok) throw new Error(String(res.status));
        return res.json();
      })
      .then((data) => {
        setLoadFailed(false);
        setRows(data.rows || []);
      })
      .catch(() => {
        setLoadFailed(true);
        setRows([]);
      });
  }, [queueUrl]);

  useEffect(load, [load]);

  // After a review the queue reloads; keep keyboard users on the row's result instead of the top of the page.
  useEffect(() => {
    if (message) document.getElementById(`review-status-${message.id}`)?.focus();
  }, [message, rows]);

  function retry() {
    setRows(null);
    setLoadFailed(false);
    load();
  }

  async function view(row: DocumentRow) {
    setBusyId(row.id);
    setMessage(null);
    const response = await fetch(`/api/v1/workflows/overseas/documents/${row.id}/download`);
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: row.id, text: detailMessage(data.detail), failed: true });
      return;
    }
    window.open(data.url, "_blank", "noreferrer");
  }

  async function submit(event: FormEvent<HTMLFormElement>, documentId: string) {
    event.preventDefault();
    setBusyId(documentId);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch(`/api/v1/workflows/overseas/documents/${documentId}/verify`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verification_status: String(form.get("verification_status")), notes: String(form.get("notes") || "") || null }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: documentId, text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ id: documentId, text: "Document reviewed -- the student has been notified.", failed: false });
    setOpenId(null);
    router.refresh();
    load();
  }

  if (loadFailed) {
    return (
      <div className="action-card">
        <h3>Document Verification</h3>
        <p className="form-error" role="alert">Couldn&apos;t load documents.</p>
        <div><button className="btn secondary small" onClick={retry}>Try again</button></div>
      </div>
    );
  }

  if (rows === null) {
    return (
      <div className="action-card">
        <h3>Document Verification</h3>
        <p className="muted" role="status">Loading your review queue…</p>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="action-card">
        <h3>Document Verification</h3>
        <p className="muted">{emptyText}</p>
      </div>
    );
  }

  const single = decisions.length === 1 ? decisions[0] : null;

  return (
    <div className="action-card">
      <h3>Document Verification</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {rows.map((row) => (
          <div className="card" key={row.id}>
            <span className="badge">{row.status}</span>
            <h4 style={{ marginTop: 10 }}>{row.document}</h4>
            <p className="muted" style={{ fontSize: 13 }}>{row.student}</p>
            <button className="btn small" disabled={busyId === row.id} onClick={() => view(row)}>
              {busyId === row.id ? "Preparing…" : "View document"}
            </button>
            {openId === row.id ? (
              <form className="form" onSubmit={(event) => submit(event, row.id)} style={{ marginTop: 8 }}>
                {single ? (
                  <input type="hidden" name="verification_status" value={single} />
                ) : (
                  <div className="field">
                    <label htmlFor={`decision-${row.id}`}>Decision</label>
                    <select id={`decision-${row.id}`} name="verification_status" required>
                      {decisions.map((value) => <option key={value} value={value}>{DECISION_LABELS[value]}</option>)}
                    </select>
                  </div>
                )}
                <div className="field">
                  <label htmlFor={`notes-${row.id}`}>Reviewer notes</label>
                  <textarea id={`notes-${row.id}`} name="notes" maxLength={10000} />
                </div>
                <button className="btn small" disabled={busyId === row.id}>
                  {busyId === row.id ? "Submitting…" : single ? `Mark ${DECISION_LABELS[single].toLowerCase()}` : "Submit review"}
                </button>
              </form>
            ) : (
              (!pendingOnly || row.status === "pending") && <button className="btn small" style={{ marginLeft: 8 }} onClick={() => setOpenId(row.id)}>Review</button>
            )}
            {message?.id === row.id && (
              <div id={`review-status-${row.id}`} tabIndex={-1} className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8, fontSize: 13 }}>
                {message.text}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire the agent Documents page** — create `apps/web/tests/components/WorkflowPanel.agentDocuments.test.tsx` first:

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const agent = (memberRole: "master" | "staff", canVerify: boolean) =>
  ({ id: "u1", email: "a@example.local", full_name: "A", role: "agent", division: "overseas", profile: {}, agent_member_role: memberRole, agent_permissions: { can_verify_documents: canVerify, can_view_reports: false } }) as unknown as User;

function stub() {
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.startsWith("/api/v1/portal/overseas/agent/documents") ? json({ rows: [{ id: "d1", student: "Asha Rao", document: "Passport", status: "pending" }] }) : json([]))));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WorkflowPanel agent Documents (AGN-003)", () => {
  it("shows no review queue without the Verify permission", () => {
    stub();
    render(<WorkflowPanel user={agent("staff", false)} section="documents" />);
    expect(screen.queryByRole("heading", { name: "Document Verification" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Upload document" })).toBeInTheDocument();
  });

  it("gives staff with Verify a Mark verified action only", async () => {
    stub();
    render(<WorkflowPanel user={agent("staff", true)} section="documents" />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    expect(screen.getByRole("button", { name: "Mark verified" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Decision")).toBeNull();
  });

  it("gives a Master all three decisions", async () => {
    stub();
    render(<WorkflowPanel user={agent("master", true)} section="documents" />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    expect([...(screen.getByLabelText("Decision") as HTMLSelectElement).options].map((o) => o.value)).toEqual(["verified", "rejected", "changes_required"]);
  });
});
```

Run: WEB(`tests/components/WorkflowPanel.agentDocuments.test.tsx`). Expected: the last two tests FAIL (no review queue).

Then edit `apps/web/components/WorkflowPanel.tsx`:
- After the line `const showCounselorDocumentReview = user.role === "counselor" && section === "documents";`, add:

```tsx
  // AGN-003 (DEC-SCOPE-044 P5/P6): agents review pending agency documents -- Masters always, staff when their Master allows it.
  const showAgentDocumentReview = user.role === "agent" && section === "documents" && user.agent_permissions?.can_verify_documents === true;
```

- In the JSX, replace `{showCounselorDocumentReview && <CounselorDocumentReviewPanel/>}` with:

```tsx
{showCounselorDocumentReview && <CounselorDocumentReviewPanel/>}{showAgentDocumentReview && <CounselorDocumentReviewPanel queueUrl="/api/v1/portal/overseas/agent/documents" pendingOnly emptyText="No documents have been uploaded for your agency's applications yet." decisions={user.agent_member_role === "staff" ? ["verified"] : undefined}/>}
```

- [ ] **Step 5: Run**

Run: WEB(`tests/components/CounselorDocumentReviewPanel.test.tsx tests/components/WorkflowPanel.agentDocuments.test.tsx tests/components/WorkflowPanel.lookups.test.tsx`), then TYPECHECK.
Expected: PASS; `tsc` exits 0.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/CounselorDocumentReviewPanel.tsx apps/web/components/WorkflowPanel.tsx apps/web/tests/components/CounselorDocumentReviewPanel.test.tsx apps/web/tests/components/WorkflowPanel.agentDocuments.test.tsx
git commit -m "feat(agn-003): agent Documents review queue reusing the counselor panel; load error with Try again"
```

---

### Task 9: "Set permissions" on the staff row

**Files:**
- Create: `apps/web/components/AgentStaffPermissionsForm.tsx`
- Modify: `apps/web/components/AgentStaffRow.tsx`, `apps/web/components/AgentStaffPanel.tsx:64`, `apps/web/lib/agentStaff.ts:5`, `apps/web/lib/apiErrors.ts:38` (`sendJson` accepts `"PUT"`; additive)
- Modify (recorded deviation, fixtures only): `apps/web/tests/components/AgentStaffRow.test.tsx:8`, `apps/web/tests/components/AgentStaffPanel.test.tsx:7`
- Test: `apps/web/tests/components/AgentStaffPermissionsForm.test.tsx` (new), `apps/web/tests/components/AgentStaffRow.test.tsx` (new cases)

**Interfaces:**
- Consumes:
  - `AgentPermissions` (Task 7)
  - `PUT …/permissions` → `{member}` (Task 4)
  - `STAFF_URL`, `staffFailure`, `sendJson` (AGN-002)
- Produces:
  - `StaffMember.permissions: AgentPermissions`
  - `AgentStaffPermissionsForm({ idPrefix, name, value, busy, onSave, onCancel })`

- [ ] **Step 1: Write the failing form tests** — `apps/web/tests/components/AgentStaffPermissionsForm.test.tsx`

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStaffPermissionsForm from "@/components/AgentStaffPermissionsForm";

afterEach(cleanup);

function renderForm(busy = false) {
  const onSave = vi.fn();
  const onCancel = vi.fn();
  render(<AgentStaffPermissionsForm idPrefix="p-s1" name="Rahul Kumar" value={{ can_verify_documents: true, can_view_reports: false }} busy={busy} onSave={onSave} onCancel={onCancel} />);
  return { onSave, onCancel };
}

describe("AgentStaffPermissionsForm (AGN-003)", () => {
  it("labels each permission, explains it, and starts on the first box with the saved values", () => {
    renderForm();
    expect(screen.getByRole("group", { name: "What Rahul Kumar can do" })).toBeInTheDocument();
    const verify = screen.getByRole("checkbox", { name: "Verify documents" });
    const reports = screen.getByRole("checkbox", { name: "View reports" });
    expect(verify).toBeChecked();
    expect(reports).not.toBeChecked();
    expect(verify).toHaveFocus();
    expect(verify).toHaveAccessibleDescription("Mark pending documents as verified. Only Masters can reject or request changes.");
    expect(reports).toHaveAccessibleDescription("See the agency's application summary.");
  });

  it("saves both values", () => {
    const { onSave } = renderForm();
    fireEvent.click(screen.getByRole("checkbox", { name: "View reports" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).toHaveBeenCalledWith({ can_verify_documents: true, can_view_reports: true });
  });

  it("Escape and Cancel cancel", () => {
    const { onCancel } = renderForm();
    fireEvent.keyDown(screen.getByRole("checkbox", { name: "Verify documents" }), { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it("shows Saving… and disables both buttons while busy", () => {
    renderForm(true);
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });
});
```

Run: WEB(`tests/components/AgentStaffPermissionsForm.test.tsx`). Expected: FAIL (module not found).

- [ ] **Step 2: Create the form** — `apps/web/components/AgentStaffPermissionsForm.tsx`

```tsx
"use client";

import { FormEvent } from "react";

import type { AgentPermissions } from "@/lib/types";

const OPTIONS: { key: keyof AgentPermissions; label: string; hint: string }[] = [
  { key: "can_verify_documents", label: "Verify documents", hint: "Mark pending documents as verified. Only Masters can reject or request changes." },
  { key: "can_view_reports", label: "View reports", hint: "See the agency's application summary." },
];

// AGN-003 (DEC-SCOPE-044 P1/P2): what one staff member may do beyond the student journey. Native checkboxes in the ENH-025
// form-section fieldset; each hint is tied to its box (aria-describedby). The row owns the request, busy state and errors.
export default function AgentStaffPermissionsForm({ idPrefix, name, value, busy, onSave, onCancel }: {
  idPrefix: string; name: string; value: AgentPermissions; busy: boolean; onSave: (next: AgentPermissions) => void; onCancel: () => void;
}) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSave({ can_verify_documents: data.get("can_verify_documents") === "on", can_view_reports: data.get("can_view_reports") === "on" });
  }

  return (
    <form className="form" onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()} aria-label={`Permissions for ${name}`} style={{ marginTop: 8 }}>
      <fieldset className="form-section">
        <legend>What {name} can do</legend>
        {OPTIONS.map(({ key, label, hint }, index) => (
          <div key={key} className="field">
            <label htmlFor={`${idPrefix}-${key}`} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input id={`${idPrefix}-${key}`} name={key} type="checkbox" defaultChecked={value[key]} aria-describedby={`${idPrefix}-${key}-hint`} autoFocus={index === 0} style={{ width: "auto" }} />
              {label}
            </label>
            <p id={`${idPrefix}-${key}-hint`} className="muted" style={{ fontSize: 13, margin: 0 }}>{hint}</p>
          </div>
        ))}
      </fieldset>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
```

Run: WEB(`tests/components/AgentStaffPermissionsForm.test.tsx`). Expected: PASS.

- [ ] **Step 3: Update the type and fixtures (recorded deviation)**

In `apps/web/lib/agentStaff.ts`:
- Add `import type { AgentPermissions } from "@/lib/types";` at the top.
- Append `; permissions: AgentPermissions` inside the `StaffMember` type, after `setup: …`.

Fixture edits:
- `tests/components/AgentStaffRow.test.tsx:8`: add `permissions: { can_verify_documents: false, can_view_reports: false }` to `active`.
- `tests/components/AgentStaffPanel.test.tsx:7`: add `permissions: { can_verify_documents: false, can_view_reports: false }` to the `staff(n)` object.

- [ ] **Step 4: Write the failing row tests** — append inside the `describe` in `apps/web/tests/components/AgentStaffRow.test.tsx`:

```tsx
  it("summarises permissions as text", () => {
    renderRow();
    expect(screen.getByText("Student journey only")).toBeInTheDocument();
    cleanup();
    renderRow({ ...active, permissions: { can_verify_documents: true, can_view_reports: true } });
    expect(screen.getByText("Can verify documents · Can view reports")).toBeInTheDocument();
  });

  it.each(["active", "deactivated"] as const)("offers Permissions while %s", (status) => {
    renderRow({ ...active, status });
    expect(screen.getByRole("button", { name: "Permissions for Rahul Kumar" })).toBeInTheDocument();
  });

  it("saves permissions with PUT, announces it and returns focus", async () => {
    const mock = vi.fn().mockResolvedValue(res({ member: { ...active, permissions: { can_verify_documents: false, can_view_reports: true } } }));
    vi.stubGlobal("fetch", mock);
    const onChanged = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Permissions for Rahul Kumar" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "View reports" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("ABC-S001 permissions saved."));
    const [url, init] = mock.mock.calls[0];
    expect(url).toBe("/api/v1/workflows/overseas/agent/team/staff/s1/permissions");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ can_verify_documents: false, can_view_reports: true });
    expect(screen.getByRole("button", { name: "Permissions for Rahul Kumar" })).toHaveFocus();
  });

  it("Escape closes Permissions and returns focus", () => {
    renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Permissions for Rahul Kumar" }));
    fireEvent.keyDown(screen.getByRole("checkbox", { name: "Verify documents" }), { key: "Escape" });
    expect(screen.getByRole("button", { name: "Permissions for Rahul Kumar" })).toHaveFocus();
  });

  it("shows a refusal in the row's status region and keeps the form open", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Only an agency Master can manage the team" }, 403)));
    renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Permissions for Rahul Kumar" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByTestId("staff-row-status-s1")).toHaveTextContent("Only an agency Master can manage the team");
    expect(screen.getByRole("checkbox", { name: "Verify documents" })).toBeInTheDocument();
  });
```

Add `waitFor` to the `@testing-library/react` import at the top of the file.
Run: WEB(`tests/components/AgentStaffRow.test.tsx`). Expected: the new cases FAIL.

- [ ] **Step 5a: Let `sendJson` send PUT** — in `apps/web/lib/apiErrors.ts`, change the signature to `export async function sendJson(url: string, method: "POST" | "PATCH" | "PUT", body: unknown): Promise<SendOutcome>`. This only widens the type; existing callers are unchanged.

- [ ] **Step 5: Implement in `AgentStaffRow.tsx`**
1. **Imports:** add `import AgentStaffPermissionsForm from "./AgentStaffPermissionsForm";` and `import type { AgentPermissions } from "@/lib/types";`.
2. **Types:**
   - `type Mode = "view" | "edit" | "confirm-deactivate" | "confirm-reset" | "permissions";`
   - In `Action`, change `method?: "POST" | "PATCH"` to `method?: "POST" | "PATCH" | "PUT"`.
3. **After `badge()`, add:**

```tsx
// AGN-003: what this staff member may do beyond the student journey, as text (never colour alone).
function permissionSummary(p: AgentPermissions): string {
  const granted = [p.can_verify_documents && "Can verify documents", p.can_view_reports && "Can view reports"].filter(Boolean);
  return granted.length ? granted.join(" · ") : "Student journey only";
}
```

4. **Summary line:** directly after the `{label && <span className="badge">{label}</span>}` line, add:

```tsx
      <div className="muted" style={{ fontSize: 13 }}>{permissionSummary(member.permissions)}</div>
```

5. **Permissions mode:** after the `confirm-reset` block, add:

```tsx
      {mode === "permissions" && (
        <AgentStaffPermissionsForm
          idPrefix={id("perm")} name={member.full_name} value={member.permissions} busy={busy} onCancel={() => close("permissions")}
          onSave={(next) => run({ path: "/permissions", method: "PUT", body: next, keepsEntry: true, focusNext: "permissions", message: `${member.code} permissions saved.` })}
        />
      )}
```

6. **Button:** in the view-mode button bar, directly after the Edit button, add:

```tsx
          <button id={id("permissions")} className="btn secondary small" aria-label={`Permissions for ${member.full_name}`} onClick={() => setMode("permissions")}>Permissions</button>
```

7. **Comment:** update the component comment's first line to `// AGN-002/AGN-003: one staff member with its actions (edit, permissions, deactivate/reactivate, reset).`

- [ ] **Step 6: Update the panel help text** — in `apps/web/components/AgentStaffPanel.tsx:64`, replace the paragraph text with:

`Staff work on your agency&apos;s students and applications. Only Masters see the team and commissions. Use Permissions to let a staff member verify documents or view reports.`

- [ ] **Step 7: Run**

Run: WEB(`tests/components/AgentStaffPermissionsForm.test.tsx tests/components/AgentStaffRow.test.tsx tests/components/AgentStaffPanel.test.tsx tests/components/AgentStaffCreateForm.test.tsx tests/components/AgentTeamPanel.test.tsx`), then TYPECHECK.
Expected: PASS; `tsc` exits 0. `AgentStaffRow.tsx` stays under 200 lines (`(Get-Content apps/web/components/AgentStaffRow.tsx).Count`).

- [ ] **Step 8: Commit**

```bash
git add apps/web/components/AgentStaffPermissionsForm.tsx apps/web/components/AgentStaffRow.tsx apps/web/components/AgentStaffPanel.tsx apps/web/lib/agentStaff.ts apps/web/lib/apiErrors.ts apps/web/tests/components/AgentStaffPermissionsForm.test.tsx apps/web/tests/components/AgentStaffRow.test.tsx apps/web/tests/components/AgentStaffPanel.test.tsx
git commit -m "feat(agn-003): Set permissions on the staff row (Verify documents, View reports)"
```

---

### Task 10: End-to-end — a Master switches a staff member's permissions

**Files:**
- Create: `apps/web/tests/e2e/helpers/agency.ts`
- Modify: `apps/web/tests/e2e/agn-002-staff.spec.ts` (import the moved helpers; recorded deviation)
- Create: `apps/web/tests/e2e/agn-003-staff-permissions.spec.ts`

**Interfaces:**
- Produces:
  - `signIn(page, email, password, landing?)`
  - `adminActivate(request, email)`
  - `registerApprovedAgency(page, unique, prefix?) -> masterEmail`

- [ ] **Step 1: Move the helpers** — create `apps/web/tests/e2e/helpers/agency.ts`. Move `signIn`, `adminActivate` and `registerApprovedAgency` from `agn-002-staff.spec.ts` verbatim, then make three changes:
- export each function;
- add a `label = "agn002"` parameter to `registerApprovedAgency`, used as `` `${label}-m-${unique}@example.local` ``;
- import `activateWithToken` from `./welcome` and the Playwright types.

```ts
import { expect, type APIRequestContext, type Page } from "@playwright/test";

import { activateWithToken } from "./welcome";

// Shared by agn-002 and agn-003: sign-in, admin activation of a staff login (the staff-create response never carries the link
// token -- S3 -- so the spec activates it the way an admin re-sends it), and a freshly registered + approved agency.

export async function signIn(page: Page, email: string, password: string, landing = "/overseas/agent/dashboard") {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

export async function adminActivate(request: APIRequestContext, email: string) {
  const login = await request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  expect(login.ok()).toBeTruthy();
  const users = await (await request.get("/api/v1/admin/users?role=agent&provisioning_status=pending_setup")).json();
  const staff = users.find((u: { email: string }) => u.email === email);
  const resend = await (await request.post(`/api/v1/admin/users/${staff.id}/welcome-links`)).json();
  await activateWithToken(request, resend.development_welcome_token);
  await request.post("/api/v1/auth/logout");
}

export async function registerApprovedAgency(page: Page, unique: number, label = "agn002") {
  const email = `${label}-m-${unique}@example.local`;
  const agency = `Sigma Overseas ${unique}`;
  await page.goto("/overseas/register");
  await page.fill('input[name="full_name"]', "Sigma Master");
  await page.fill('input[name="email"]', email);
  await page.selectOption('select[name="account_type"]', "agent");
  await page.fill('input[name="agency_name"]', agency);
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/overseas/agent/dashboard");
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/agents");
  await page.locator(".card", { hasText: agency }).getByRole("button", { name: "Approve" }).click();
  await expect(page.locator(".card", { hasText: agency }).getByText("Approved")).toBeVisible();
  return email;
}
```

In `agn-002-staff.spec.ts`:
- Delete the three local functions.
- Change the imports to `import { test, expect, type Browser } from "@playwright/test";`, `import { E2E_PASSWORD } from "./helpers/welcome";` and `import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";`.
- Keep `staffPage` and the test body unchanged.

- [ ] **Step 2: Write the AGN-003 spec** — `apps/web/tests/e2e/agn-003-staff-permissions.spec.ts`

```ts
import { test, expect, type APIRequestContext } from "@playwright/test";

import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";
import { E2E_PASSWORD } from "./helpers/welcome";

// AGN-003 -- staff start on the student journey only; their Master switches Reports and Verify documents on and off, and the
// change shows on the staff member's next page load. Requires the stack running with `python -m app.seed` applied (seeded
// universities). A fresh overseas student is registered per run, so a re-run never meets the duplicate-application rule (409).

async function agencyDocument(request: APIRequestContext, scratch: APIRequestContext, unique: number) {
  const studentEmail = `agn003-st-${unique}@example.local`;
  const registered = await scratch.post("/api/v1/auth/register", { data: { email: studentEmail, password: "Sup3r-Secret-Pass!", full_name: `AGN003 Student ${unique}`, division: "overseas", account_type: "student" } });
  expect(registered.status()).toBe(201);
  // purpose=link matches an email only when typed in full (AGN-001 D2 as revised).
  const found = await (await request.get(`/api/v1/lookups/overseas-students?q=${encodeURIComponent(studentEmail)}&purpose=link`)).json();
  const studentId = found.items[0].id;
  expect((await request.post("/api/v1/workflows/overseas/agent/students", { data: { student_id: studentId } })).status()).toBe(201);
  const universities = await (await request.get("/api/v1/public/universities")).json();
  const application = await request.post("/api/v1/workflows/overseas/applications", { data: { university_id: universities[0].id, student_id: studentId } });
  expect(application.status()).toBe(201);
  const applicationId = (await application.json()).id;
  const doc = await request.post("/api/v1/workflows/overseas/documents", { data: { student_id: studentId, application_id: applicationId, document_type: "AGN003 Passport", file_url: "uploads/agn003-e2e.pdf" } });
  expect(doc.status()).toBe(201);
}

test("a Master switches a staff member's Reports and Verify permissions (AGN-003)", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "agn003");
  const staffEmail = `agn003-s-${unique}@example.local`;

  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  expect((await page.request.post("/api/v1/workflows/overseas/agent/team/staff", { data: { full_name: "Tau Staff", email: staffEmail } })).status()).toBe(201);
  const scratch = await browser.newContext(); // the student's own registration cookies stay out of the Master's and staff's sessions
  await agencyDocument(page.request, scratch.request, unique);
  await scratch.close();

  const staffContext = await browser.newContext();
  const staff = await staffContext.newPage();
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);

  // Student journey only: no Reports link, the page refuses, no review queue.
  await expect(staff.getByRole("link", { name: "Reports", exact: true })).toHaveCount(0);
  await staff.goto("/overseas/agent/reports");
  await expect(staff.getByText("Your agency Master hasn't given you access to reports")).toBeVisible();
  await staff.goto("/overseas/agent/documents");
  await expect(staff.getByRole("heading", { name: "Document Verification" })).toHaveCount(0);

  // The Master switches both on.
  await page.goto("/overseas/agent/team");
  await expect(page.getByText("Student journey only")).toBeVisible();
  await page.getByRole("button", { name: "Permissions for Tau Staff" }).click();
  await page.getByRole("checkbox", { name: "Verify documents" }).check();
  await page.getByRole("checkbox", { name: "View reports" }).check();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/-S001 permissions saved\./)).toBeVisible();
  await expect(page.getByText("Can verify documents · Can view reports")).toBeVisible();

  // Next page load: Reports is there, and the staff member can only mark a pending document verified.
  await staff.goto("/overseas/agent/dashboard");
  await expect(staff.getByRole("link", { name: "Reports", exact: true })).toBeVisible();
  await staff.goto("/overseas/agent/documents");
  const card = staff.locator(".card", { hasText: "AGN003 Passport" });
  await card.getByRole("button", { name: "Review" }).click();
  await expect(card.getByLabel("Decision")).toHaveCount(0);
  await card.getByRole("button", { name: "Mark verified" }).click();
  await expect(card.getByText("Document reviewed -- the student has been notified.")).toBeVisible();
  await expect(card.getByRole("button", { name: "Review" })).toHaveCount(0);

  // The Master switches both off; the staff member's next request is refused.
  await page.getByRole("button", { name: "Permissions for Tau Staff" }).click();
  await page.getByRole("checkbox", { name: "Verify documents" }).uncheck();
  await page.getByRole("checkbox", { name: "View reports" }).uncheck();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Student journey only")).toBeVisible();
  await staff.goto("/overseas/agent/reports");
  await expect(staff.getByText("Your agency Master hasn't given you access to reports")).toBeVisible();
  await staffContext.close();
});
```

- [ ] **Step 3: Run both specs** (the stack must be up; ask the user to start it with this worktree's ports, per the standing preference)

Run: `cd apps/web; $env:E2E_BASE_URL="http://localhost:30xx"; npx playwright test tests/e2e/agn-002-staff.spec.ts tests/e2e/agn-003-staff-permissions.spec.ts --reporter=line`. Use the base-URL variable the repo's `playwright.config.ts` reads.
Expected: `2 passed`. On failure, open only that test's trace/screenshot.

- [ ] **Step 4: Commit**

```bash
git add apps/web/tests/e2e/helpers/agency.ts apps/web/tests/e2e/agn-002-staff.spec.ts apps/web/tests/e2e/agn-003-staff-permissions.spec.ts
git commit -m "test(agn-003): e2e -- a Master switches staff Reports and Verify permissions; shared agency e2e helpers"
```

---

### Task 11: Documentation and traceability

**Files:**
- Modify:
  - `docs/architecture/RBAC_MATRIX.md` (§2.8, after the AGN-002 block ~:146-157)
  - `docs/architecture/API_CONTRACT.md` (§8, after the AGN-002 table ~:206-229)
  - `docs/architecture/DATA_MODEL.md` (new §6.8c before §6.9 ~:450)
  - `docs/ux/SCREEN_CATALOG.md` (SCR-AGT-005 ~:1743, SCR-AGT-007 ~:1779-1805)
  - `docs/ux/ROLE_NAVIGATION.md` (~:146-157)
  - `docs/quality/RTM.md` (AGN-003 addendum after the AGN-002 addendum ~:339-344)
  - `docs/delivery/ENHANCEMENT_BACKLOG.md` (AGN-003 status line)

- [ ] **Step 1: RBAC_MATRIX §2.8** — add a block titled `**AGN-003 addendum (2026-10-01, DEC-SCOPE-044).**`. It contains the spec §3 table verbatim (§6 row / routes / Master / Staff) plus one line each for:
- toggles: per staff member, off by default, Master-only `PUT`, effective next request
- Verify gives `verified` only; Reject is Master-only
- N/A rows and the Add University departure

- [ ] **Step 2: API_CONTRACT §8** — add an `AGN-003` table with three rows:
- **`PUT /workflows/overseas/agent/team/staff/{member_id}/permissions`:** Master of the staff member's active organisation. Body is strict booleans, `extra=forbid`. Refusals: `404` another agency, Master id or unknown; `403` staff or suspended; `422` bad body. It is idempotent: a no-op writes nothing, and a change writes one `agent_org.staff_permissions` audit row with before/after. Response `{member}` with `permissions`.
- **`PATCH /workflows/overseas/documents/{id}/verify` — agent addendum:**
  - Check order 403 → 422 → 403 → 404 → 403 → 409, with the verbatim messages from Global Constraints.
  - Pending only.
  - Staff need `can_verify_documents` and may send `verified` only.
  - Audit metadata is validated plus `member_role`.
  - Counselor/admin behaviour unchanged.
- **`GET /auth/me` / staff shape:** additive `agent_permissions` (effective; Master both true; non-agent `null`) and `permissions`. Also record `GET /portal/overseas/agent/reports` → `403 REPORTS_REFUSED` for staff without the toggle.

- [ ] **Step 3: DATA_MODEL §6.8c** — "AgentOrgMember permission flags (AGN-003, migration `0051_agent_staff_permissions`)". Two `BOOLEAN NOT NULL DEFAULT false` columns; staff-only semantics; existing rows read `false`; downgrade drops them.

- [ ] **Step 4: SCREEN_CATALOG and ROLE_NAVIGATION**
- **SCR-AGT-007 Team:**
  - a Permissions action on each staff row (fieldset form, two checkboxes with hints, Save/Cancel, Escape)
  - the text summary
  - the new panel help text
- **SCR-AGT-005 Documents:**
  - a review queue for Masters and for staff with Verify
  - pending-only Review
  - staff see "Mark verified" only
  - load error with Try again
- **ROLE_NAVIGATION Agent:** staff see Reports only with the Reports permission.

- [ ] **Step 5: RTM** — add an `AGN-003` addendum row:
- AC01–AC09 → test files (`test_agn_003_schema.py`, `_permissions.py`, `_verify.py`, `_matrix.py`; the web tests; `agn-003-staff-permissions.spec.ts`)
- the four recorded deviations (top of this plan)
- the known limitations from spec §10, plus one found while planning: the agent Documents page (and so the review queue) lists only documents attached to an agency application. That predates AGN-003. An unattached document can be reviewed through the API (tested) but has no queue row.
- "full backend suite not run for this feature (owner's standing choice); lite set R ran"
- evidence lines (counts and exit codes) filled from Task 12's actual output

- [ ] **Step 6: Commit**

```bash
git add docs/architecture/RBAC_MATRIX.md docs/architecture/API_CONTRACT.md docs/architecture/DATA_MODEL.md docs/ux/SCREEN_CATALOG.md docs/ux/ROLE_NAVIGATION.md docs/quality/RTM.md docs/delivery/ENHANCEMENT_BACKLOG.md
git commit -m "docs(agn-003): RBAC matrix, API contract, data model, screens, navigation and RTM"
```

---

### Task 12: Verification gate

- [ ] **Step 1: Backend**

Run: MIGRATE; API(`tests/test_agn_003_schema.py tests/test_agn_003_permissions.py tests/test_agn_003_verify.py tests/test_agn_003_matrix.py`); then the regression set **R**; then LINT.
Expected: all pass; `ruff` reports `All checks passed!`. Record the pass counts.

- [ ] **Step 2: Frontend**

Run:
- WEB(`tests/lib/navigation.test.ts tests/components/CounselorDocumentReviewPanel.test.tsx tests/components/WorkflowPanel.agentDocuments.test.tsx tests/components/WorkflowPanel.lookups.test.tsx tests/components/Enh031ExistingPickers.test.tsx tests/components/AgentStaffPermissionsForm.test.tsx tests/components/AgentStaffRow.test.tsx tests/components/AgentStaffPanel.test.tsx tests/components/AgentStaffCreateForm.test.tsx tests/components/AgentTeamPanel.test.tsx tests/components/AccessUnavailable.test.tsx`)
- TYPECHECK
- `npx eslint components lib tests` in the same container

Expected: all pass, `tsc` 0, eslint 0 errors.

- [ ] **Step 3: E2E** — `agn-002-staff`, `agn-003-staff-permissions`, and the neighbours that sign in as the seeded Master: `agt-002-referrals`, `agt-004-commission-payout`, `enh-031-searchable-pickers`.
Expected: all pass. Open traces only for failures.

- [ ] **Step 4: Spec coverage check** — walk spec §3 row by row and AGN-003-AC01…AC09. For each, name the test that proves it. Paste that list into the RTM row (Task 11 Step 5), then commit the RTM evidence:

```bash
git add docs/quality/RTM.md
git commit -m "docs(agn-003): record verification evidence"
```
