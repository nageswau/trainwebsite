# AGN-004 Agent Students Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Masters and Staff of an agent organisation create, edit, view and (Masters) archive students who never log in, with Staff narrowed to their assigned students on every agent path and a within-agency duplicate warning.

**Architecture:** Extend `agent_students` (nullable `student_id`, identity columns, assignment, archive) in one migration that also carries AGN-002's Staff schema pieces behind idempotency guards. A new `services/agent_students.py` owns scoping (`student_scope`, `visible_student_user_ids`, `application_scope`), the duplicate check and writes; a new `api/agent_students.py` router exposes the CRUD. Existing agent paths swap their org-wide clause for the scope helpers (identical for Masters). The web adds `lib/agentStudents.ts`, `AgentStudentForm` and `AgentStudentsPanel` on the existing Students page.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL, Pydantic 2, pytest + pytest-asyncio + httpx; Next.js (App Router), React, TypeScript, vitest + Testing Library, Playwright. No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-30-agn-004-agent-students-design.md` (revision 2). Read it with this plan.

## Global Constraints

- Branch `feature/agn-004-agent-students`, from `main` at `9d355e8`; independent of `feature/agn-002-staff-logins` (G1).
- Every Staff piece listed in spec G2 uses AGN-002's exact identifiers and wording: `MASTER, STAFF = "master", "staff"`; `is_agent_staff`; `staff_seq`; `ck_agent_orgs_staff_seq`; `ck_agent_org_members_role` = `role IN ('master', 'staff')`; `uq_agent_org_members_org_role_seq`; `MASTER_ONLY = "Only an agency Master can manage the team"`; `"Only an agency Master can view commissions"`; `"Only an agency Master can open this page"`; `"Staff accounts are managed by their agency"`; `UserOut.agent_member_role`; `agentNavFor(nav, memberRole)`.
- Decision ID `DEC-SCOPE-041` (provisional). Migration revision `0047_agent_students_crm`, `down_revision = "0046_agent_orgs"`.
- Authorization follows the inline pattern (`User.role` + `agent_denial_reason` + scope helpers); never `require_role`/`require_permission`.
- Errors are FastAPI `{"detail": ...}`; `422` for validation, `404` masks out-of-scope rows on the new routes, `409` for state conflicts.
- Every write: one transaction, organisation row locked, audit row in the same transaction, then commit. Logs and audit metadata carry ids, codes, field names and counts only.
- No existing test is edited to make it pass, except `test_agn_001_schema.py`'s two AGN-002-identical edits (Task 1), recorded as a decision change.
- Tests are run for real; outcomes are read from exit codes and output, never reasoned.
- No new dependency (web `npm ci` installs the existing lockfile only).

## Test commands (used by every task)

The owner runs Docker. Before Task 1 the owner starts an isolated stack (ports free-checked first):

```bash
docker compose -p agn004 -f docker-compose.yml -f docker-compose.ci.yml up -d postgres redis
```

API tests run in a one-off container with the worktree's source mounted (migrations applied first):

```bash
docker compose -p agn004 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "$PWD/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <TEST_PATHS>"
```

Referred to below as **`API_TEST <paths>`**. Web tests run on the host after a one-time `cd apps/web && npm ci`:
**`WEB_TEST <paths>`** = `cd apps/web && npx vitest run <paths>`.

## Review Focus

1. **A Staff member reaching another Staff member's student through an application or document id** (not the student routes) — expected: the existing out-of-scope `403`. Pinned in Task 4 (`test_staff_cannot_reach_another_staff_members_application_or_document`).
2. **An archived linked student whose application still exists** — the application and its documents must still appear on Master portal pages and history, while the roster hides the link. Pinned in Task 4 (`test_archived_link_keeps_its_applications_visible`).
3. **Phone typed with spaces, `+`, dashes or brackets** (`+91 98765-43210` vs `9876543210`) — expected: same digits → duplicate warning; fewer than 7 digits never matches. Pinned in Task 6 (`test_phone_formats_match_on_digits_only`).
4. **Search text containing `%`, `_` or `\`** — expected: matched literally, not as wildcards. Pinned in Task 6 (`test_search_metacharacters_match_literally`).
5. **Two browser tabs: a slow earlier search resolving after a newer one** — expected: the newer result stays on screen. Pinned in Task 11 (`keeps the newest search when an older response arrives late`).

---

## File Structure

**Backend — create**
- `apps/api/alembic/versions/0047_agent_students_crm.py` — Staff schema pieces (guarded) + `agent_students` columns, CHECKs, indexes; guarded downgrade.
- `apps/api/app/services/agent_students.py` — scope helpers, `phone_digits`, serialisers, duplicate check, write functions (no commit).
- `apps/api/app/api/agent_students.py` — the `/workflows/overseas/agent/crm/students` router.
- `apps/api/tests/agn004_helpers.py` — `mk_staff`, `mk_record`, URL constants.
- `apps/api/tests/test_agn_004_schema.py`, `test_agn_004_migration.py`, `test_agn_004_schemas.py`, `test_agn_004_staff_guards.py`, `test_agn_004_staff_scope.py`, `test_agn_004_students.py`, `test_agn_004_student_actions.py`.

**Backend — modify**
- `apps/api/app/models.py` — `AgentOrg.staff_seq`, `AgentOrgMember` constraints, `AgentStudent` columns.
- `apps/api/app/core/rbac.py` — `is_agent_staff`.
- `apps/api/app/services/agent_orgs.py` — `MASTER`/`STAFF`, role filters, `lock_active_org`.
- `apps/api/app/api/agent_team.py` — Staff refused; Masters-only listing; `_locked_active_org` delegates to `lock_active_org`.
- `apps/api/app/api/workflows.py` — `_require_agent_master`; scope helpers in six agent paths; roster/link changes.
- `apps/api/app/api/portal.py` — Staff refused on team/commissions.
- `apps/api/app/services/portal.py` — `_agent` uses scope helpers, hides archived, hides commissions from Staff, Masters-only team.
- `apps/api/app/api/lookups.py` — agent branches use scope helpers.
- `apps/api/app/api/admin.py` — Staff excluded from per-agent approve/reject and listings.
- `apps/api/app/api/auth.py`, `apps/api/app/schemas.py` — `agent_member_role`; record schemas.
- `apps/api/app/main.py` — register the router.
- `apps/api/tests/test_agn_001_schema.py` — the two AGN-002-identical edits.

**Web — create**
- `apps/web/lib/agentStudents.ts`, `apps/web/components/AgentStudentForm.tsx`, `apps/web/components/AgentStudentsPanel.tsx`.
- `apps/web/tests/lib/agentStudents.test.ts`, `apps/web/tests/components/AgentStudentForm.test.tsx`, `apps/web/tests/components/AgentStudentsPanel.test.tsx`, `apps/web/tests/lib/navigation.agent.test.ts`.
- `apps/web/tests/e2e/agn-004-agent-students.spec.ts`.

**Web — modify**
- `apps/web/lib/types.ts`, `apps/web/lib/navigation.ts`, `apps/web/components/PortalPage.tsx`, `apps/web/components/WorkflowPanel.tsx`, `apps/web/app/globals.css`.

**Docs — modify** (Task 13): decision register, backlog, DATA_MODEL, API_CONTRACT, RBAC_MATRIX, SECURITY_CONTROLS, THREAT_MODEL, PRD_OPEN_ITEMS, CONFLICT_MATRIX, SCREEN_CATALOG (+json), RTM.

---

### Task 1: Migration 0047 and models (Staff pieces + agent_students columns)

**Files:**
- Create: `apps/api/alembic/versions/0047_agent_students_crm.py`
- Modify: `apps/api/app/models.py` (imports line 5; `AgentStudent` ~L828; `AgentOrg` ~L853; `AgentOrgMember` ~L872)
- Modify: `apps/api/tests/test_agn_001_schema.py` (two AGN-002-identical edits)
- Create: `apps/api/tests/agn004_helpers.py`, `apps/api/tests/test_agn_004_schema.py`

**Interfaces:**
- Produces: `AgentStudent` columns `full_name, email, phone, phone_digits, date_of_birth, highest_qualification, institution, graduation_year, preferred_country, preferred_course, preferred_intake, notes, assigned_member_id, archived_at, archived_by_user_id, updated_by_user_id`; `student_id` nullable; `AgentOrg.staff_seq`; member role `staff` allowed.
- Produces (tests): `tests.agn004_helpers.mk_staff(db, org, *, full_name="Staff Member", active=True) -> {"user", "member"}`, `mk_record(db, *, agent, full_name, email=None, phone=None, assigned_member=None, status="active") -> AgentStudent`, `RECORDS = "/api/v1/workflows/overseas/agent/crm/students"`.

- [ ] **Step 1: Write the helpers and the failing schema tests**

`apps/api/tests/agn004_helpers.py`:

```python
"""AGN-004 test helpers. Staff are inserted directly with AGN-002's data shape (AGN-002 owns the Staff API)."""

import re

from app.models import AgentOrg, AgentOrgMember, AgentStudent, UserRoleAssignment
from tests.agn001_helpers import mk_user

RECORDS = "/api/v1/workflows/overseas/agent/crm/students"


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


async def mk_record(db, *, agent, full_name: str, email: str | None = None, phone: str | None = None, assigned_member=None, status: str = "active") -> AgentStudent:
    row = AgentStudent(
        agent_id=agent.id, student_id=None, status=status, full_name=full_name, email=email, phone=phone,
        phone_digits=(re.sub(r"\D", "", phone or "") or None), assigned_member_id=assigned_member.id if assigned_member else None,
    )
    db.add(row)
    await db.commit()
    return row
```

`apps/api/tests/test_agn_004_schema.py`:

```python
"""AGN-004 -- model constraints added by migration 0047_agent_students_crm (spec §4)."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import AgentOrg, AgentOrgMember, AgentStudent
from tests.agn001_helpers import mk_active_org, mk_user
from tests.agn004_helpers import mk_staff


@pytest.mark.asyncio
async def test_staff_member_role_is_allowed_and_numbered_apart_from_masters(db_session):
    ctx = await mk_active_org(db_session, name="Schema Staff")
    staff = await mk_staff(db_session, ctx["org"])
    assert staff["member"].code.endswith("-S001") and ctx["member"].code.endswith("-M001")
    assert staff["member"].seq == ctx["member"].seq == 1  # uq_agent_org_members_org_role_seq lets M001 and S001 coexist


@pytest.mark.asyncio
async def test_member_role_check_rejects_unknown_roles(db_session):
    user = await mk_user(db_session, role="agent")
    org = AgentOrg(name="Chk", prefix=f"Q{uuid.uuid4().hex[:6].upper()}", status="pending", master_seq=1)
    db_session.add(org)
    await db_session.flush()
    db_session.add(AgentOrgMember(org_id=org.id, user_id=user.id, role="owner", seq=1, code=f"{org.prefix}-M001", status="active"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_student_without_login_needs_a_name(db_session):
    ctx = await mk_active_org(db_session, name="Schema Identity")
    db_session.add(AgentStudent(agent_id=ctx["master"].id, student_id=None, status="active"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_student_status_is_active_or_archived(db_session):
    ctx = await mk_active_org(db_session, name="Schema Status")
    db_session.add(AgentStudent(agent_id=ctx["master"].id, student_id=None, full_name="Asha", status="deleted"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_student_without_login_is_stored_with_no_user(db_session):
    ctx = await mk_active_org(db_session, name="Schema Store")
    row = AgentStudent(agent_id=ctx["master"].id, student_id=None, full_name="Asha Rao", status="active", preferred_country="Canada")
    db_session.add(row)
    await db_session.commit()
    assert row.student_id is None and row.full_name == "Asha Rao"
```

Edit `apps/api/tests/test_agn_001_schema.py` exactly as AGN-002 does (a decision change — `DEC-SCOPE-041` G2 widens the role set; record it in the Task 13 RTM row):

```python
@pytest.mark.asyncio
async def test_alembic_head_is_the_single_head_and_includes_0046(db_session):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    script = ScriptDirectory.from_config(config)
    head = await db_session.scalar(text("SELECT version_num FROM alembic_version"))
    assert head == script.get_current_head()
    # AGN-002 chained 0047 after 0046: keep the intent (0046 applied, one head) without pinning the head.
    assert "0046_agent_orgs" in {rev.revision for rev in script.walk_revisions()}
```

and in `test_member_checks_reject_bad_values` change the parametrize to `[{"role": "owner"}, {"status": "invited"}]`.

- [ ] **Step 2: Run to verify failure**

Run: `API_TEST tests/test_agn_004_schema.py`
Expected: FAIL — `AttributeError: 'AgentOrg' object has no attribute 'staff_seq'` (and `full_name` unknown on `AgentStudent`).

- [ ] **Step 3: Write the migration**

`apps/api/alembic/versions/0047_agent_students_crm.py`:

```python
"""AGN-004 -- students with no login on agent_students, plus AGN-002's staff member pieces.

Revision ID: 0047_agent_students_crm
Revises: 0046_agent_orgs

docs/superpowers/specs/2026-09-30-agn-004-agent-students-design.md §4 (DEC-SCOPE-041). The staff pieces (agent_orgs.staff_seq,
member role master|staff, member numbers unique per role) are identical to AGN-002's 0047_agent_org_staff and guarded, so whichever
of the two runs second skips them. agent_students gains nullable identity, assignment and archive columns; student_id becomes
nullable. No existing row changes. downgrade() refuses while a student with no login, an assignment or a staff member exists: it never
silently deletes students or logins.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0047_agent_students_crm"
down_revision = "0046_agent_orgs"
branch_labels = None
depends_on = None

STUDENT_COLUMNS = (
    ("full_name", sa.String(160)),
    ("email", sa.String(320)),
    ("phone", sa.String(40)),
    ("phone_digits", sa.String(20)),
    ("date_of_birth", sa.Date()),
    ("highest_qualification", sa.String(200)),
    ("institution", sa.String(200)),
    ("graduation_year", sa.SmallInteger()),
    ("preferred_country", sa.String(120)),
    ("preferred_course", sa.String(200)),
    ("preferred_intake", sa.String(40)),
    ("notes", sa.Text()),
    ("archived_at", sa.DateTime(timezone=True)),
)
FK_COLUMNS = (
    ("assigned_member_id", "agent_org_members.id"),
    ("archived_by_user_id", "users.id"),
    ("updated_by_user_id", "users.id"),
)
INDEXES = (
    ("ix_agent_students_agent_status", ["agent_id", "status"]),
    ("ix_agent_students_agent_phone_digits", ["agent_id", "phone_digits"]),
    ("ix_agent_students_assigned_member", ["assigned_member_id"]),
)


def _columns(table: str) -> set[str]:
    if op.get_context().as_sql:
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _unique_constraints(table: str) -> set[str]:
    if op.get_context().as_sql:
        return {"uq_agent_org_members_org_seq"}
    return {c["name"] for c in sa.inspect(op.get_bind()).get_unique_constraints(table)}


def _refuse_if(bind, sql: str, message: str) -> None:
    if bind.execute(sa.text(sql)).first():
        raise RuntimeError(message)


def upgrade() -> None:
    # --- AGN-002 staff pieces (identical names; guarded) ---
    if "staff_seq" not in _columns("agent_orgs"):
        op.add_column("agent_orgs", sa.Column("staff_seq", sa.Integer(), nullable=False, server_default="0"))
        op.create_check_constraint("ck_agent_orgs_staff_seq", "agent_orgs", "staff_seq >= 0")
    op.drop_constraint("ck_agent_org_members_role", "agent_org_members", type_="check")
    op.create_check_constraint("ck_agent_org_members_role", "agent_org_members", "role IN ('master', 'staff')")
    if "uq_agent_org_members_org_seq" in _unique_constraints("agent_org_members"):
        op.drop_constraint("uq_agent_org_members_org_seq", "agent_org_members", type_="unique")
        op.create_unique_constraint("uq_agent_org_members_org_role_seq", "agent_org_members", ["org_id", "role", "seq"])

    # --- AGN-004 agent_students ---
    bind = op.get_bind()
    if not op.get_context().as_sql:
        _refuse_if(bind, "SELECT 1 FROM agent_students WHERE status NOT IN ('active', 'archived') LIMIT 1", "agent_students has a status other than active/archived; fix it before 0047")
    existing = _columns("agent_students")
    for name, type_ in STUDENT_COLUMNS:
        if name not in existing:
            op.add_column("agent_students", sa.Column(name, type_, nullable=True))
    for name, target in FK_COLUMNS:
        if name not in existing:
            op.add_column("agent_students", sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey(target), nullable=True))
    op.alter_column("agent_students", "student_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_check_constraint("ck_agent_students_identity", "agent_students", "student_id IS NOT NULL OR full_name IS NOT NULL")
    op.create_check_constraint("ck_agent_students_status", "agent_students", "status IN ('active', 'archived')")
    for name, cols in INDEXES:
        op.create_index(name, "agent_students", cols)
    op.create_index("ix_agent_students_agent_email_lower", "agent_students", ["agent_id", sa.text("lower(email)")])


def downgrade() -> None:
    bind = op.get_bind()
    _refuse_if(bind, "SELECT 1 FROM agent_students WHERE student_id IS NULL LIMIT 1", "Cannot downgrade 0047_agent_students_crm: students with no login exist. Remove them deliberately first.")
    _refuse_if(bind, "SELECT 1 FROM agent_students WHERE assigned_member_id IS NOT NULL LIMIT 1", "Cannot downgrade 0047_agent_students_crm: assigned students exist. Unassign them deliberately first.")
    op.drop_index("ix_agent_students_agent_email_lower", table_name="agent_students")
    for name, _ in INDEXES:
        op.drop_index(name, table_name="agent_students")
    op.drop_constraint("ck_agent_students_status", "agent_students", type_="check")
    op.drop_constraint("ck_agent_students_identity", "agent_students", type_="check")
    op.alter_column("agent_students", "student_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    for name, _ in reversed(FK_COLUMNS):
        op.drop_column("agent_students", name)
    for name, _ in reversed(STUDENT_COLUMNS):
        op.drop_column("agent_students", name)
    # AGN-002's rule: never turn staff into Masters by a rollback.
    _refuse_if(bind, "SELECT 1 FROM agent_org_members WHERE role = 'staff' LIMIT 1", "Cannot downgrade 0047_agent_students_crm: staff members exist. Remove them deliberately first.")
    op.drop_constraint("uq_agent_org_members_org_role_seq", "agent_org_members", type_="unique")
    op.create_unique_constraint("uq_agent_org_members_org_seq", "agent_org_members", ["org_id", "seq"])
    op.drop_constraint("ck_agent_org_members_role", "agent_org_members", type_="check")
    op.create_check_constraint("ck_agent_org_members_role", "agent_org_members", "role = 'master'")
    op.drop_constraint("ck_agent_orgs_staff_seq", "agent_orgs", type_="check")
    op.drop_column("agent_orgs", "staff_seq")
```

- [ ] **Step 4: Update the models**

`apps/api/app/models.py` line 5 — add `SmallInteger` to the `sqlalchemy` import.

Replace `class AgentStudent` with:

```python
class AgentStudent(Base, TimestampMixin):
    """AGT-002 link of an agent to a student with an account; AGN-004 (DEC-SCOPE-041) adds students with no login
    (`student_id` NULL, identity on the row), assignment to a staff member, and archive. `agent_id` is the member who created
    or linked the row; it fixes the agency (membership is permanent)."""

    __tablename__ = "agent_students"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    student_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    full_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    phone_digits: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    highest_qualification: Mapped[str | None] = mapped_column(String(200), nullable=True)
    institution: Mapped[str | None] = mapped_column(String(200), nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    preferred_country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    preferred_course: Mapped[str | None] = mapped_column(String(200), nullable=True)
    preferred_intake: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_member_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_org_members.id"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    __table_args__ = (
        UniqueConstraint("agent_id", "student_id", name="uq_agent_student"),
        CheckConstraint("student_id IS NOT NULL OR full_name IS NOT NULL", name="ck_agent_students_identity"),
        CheckConstraint("status IN ('active', 'archived')", name="ck_agent_students_status"),
        Index("ix_agent_students_agent_status", "agent_id", "status"),
        Index("ix_agent_students_agent_phone_digits", "agent_id", "phone_digits"),
        Index("ix_agent_students_assigned_member", "assigned_member_id"),
    )
```

In `AgentOrg`: docstring gains AGN-002's sentence ("`staff_seq` is the highest staff number ever issued (AGN-002)."), `__table_args__` gains `CheckConstraint("staff_seq >= 0", name="ck_agent_orgs_staff_seq")`, and add
`staff_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")` after `master_seq`.

In `AgentOrgMember`: docstring becomes AGN-002's ("AGN-001: a user's membership of exactly one agent organisation, for good (`user_id` unique). AGN-002 adds `staff` (DEC-SCOPE-040): Masters and staff are numbered separately (M001 and S001 coexist)."); replace the two constraints with
`UniqueConstraint("org_id", "role", "seq", name="uq_agent_org_members_org_role_seq")` and `CheckConstraint("role IN ('master', 'staff')", name="ck_agent_org_members_role")`.

- [ ] **Step 5: Run to verify pass**

Run: `API_TEST tests/test_agn_004_schema.py tests/test_agn_001_schema.py tests/test_agn_001_tenancy.py tests/test_agt_002_referrals.py`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add apps/api/alembic/versions/0047_agent_students_crm.py apps/api/app/models.py apps/api/tests/agn004_helpers.py apps/api/tests/test_agn_004_schema.py apps/api/tests/test_agn_001_schema.py
git commit -m "feat(agn-004): migration 0047 -- students with no login, assignment, archive, staff member role"
```

---

### Task 2: Migration round trip and guards

**Files:**
- Create: `apps/api/tests/test_agn_004_migration.py`

**Interfaces:**
- Consumes: migration module `0047_agent_students_crm` (`revision`, `down_revision`, `STUDENT_COLUMNS`, `FK_COLUMNS`).

- [ ] **Step 1: Write the failing tests**

```python
"""AGN-004 -- migration 0047_agent_students_crm (spec §4, AC12)."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_004_migration_0047", VERSIONS / "0047_agent_students_crm.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def _alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=API_ROOT, capture_output=True, text=True)


def test_migration_chains_after_0046():
    assert _migration.revision == "0047_agent_students_crm"
    assert _migration.down_revision == "0046_agent_orgs"


def test_model_declares_every_new_column_nullable():
    from app.models import AgentStudent

    columns = AgentStudent.__table__.columns
    for name, _ in (*_migration.STUDENT_COLUMNS, *_migration.FK_COLUMNS):
        assert name in columns and columns[name].nullable, name
    assert columns["student_id"].nullable


@pytest.mark.asyncio
async def test_new_columns_exist_in_the_database(db_session):
    conn = await db_session.connection()
    cols = await conn.run_sync(lambda sync: {c["name"]: c for c in inspect(sync).get_columns("agent_students")})
    for name, _ in (*_migration.STUDENT_COLUMNS, *_migration.FK_COLUMNS):
        assert name in cols and cols[name]["nullable"], name


@pytest.mark.asyncio
async def test_round_trip_keeps_existing_rows_identical(db_session):
    """Upgrade -> downgrade -> upgrade on the test database; pre-existing link rows are unchanged. Runs only when no row with no
    login, no assignment and no staff member exists (the downgrade guards would refuse otherwise -- that is test_downgrade_refuses...)."""
    blockers = await db_session.scalar(
        text("SELECT (SELECT count(*) FROM agent_students WHERE student_id IS NULL OR assigned_member_id IS NOT NULL) + (SELECT count(*) FROM agent_org_members WHERE role = 'staff')")
    )
    if blockers:
        pytest.skip("database holds AGN-004 rows; the refusal path is covered by test_downgrade_refuses_while_students_without_login_exist")
    before = (await db_session.execute(text("SELECT id, agent_id, student_id, status FROM agent_students ORDER BY id"))).all()
    await db_session.close()
    down = _alembic("downgrade", "0046_agent_orgs")
    assert down.returncode == 0, down.stderr
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    from app.core.database import SessionLocal

    async with SessionLocal() as fresh:
        after = (await fresh.execute(text("SELECT id, agent_id, student_id, status FROM agent_students ORDER BY id"))).all()
    assert after == before


@pytest.mark.asyncio
async def test_downgrade_refuses_while_students_without_login_exist(db_session):
    from tests.agn001_helpers import mk_active_org
    from tests.agn004_helpers import mk_record

    ctx = await mk_active_org(db_session, name="Downgrade Guard")
    await mk_record(db_session, agent=ctx["master"], full_name="Guarded Student")
    await db_session.close()
    down = _alembic("downgrade", "0046_agent_orgs")
    assert down.returncode != 0
    assert "students with no login exist" in down.stderr
    assert _alembic("current").stdout.strip().startswith("0047_agent_students_crm")
```

- [ ] **Step 2: Run to verify** — `API_TEST tests/test_agn_004_migration.py`. Expected: the first three PASS already (Task 1 built the migration); run the whole file and confirm the two round-trip tests pass. If `test_round_trip…` fails, the downgrade has a bug — fix the migration, not the test. (This task is a verification task: its RED is the absence of the file; the behaviour exists from Task 1.)

- [ ] **Step 3: Run offline SQL once and read it**

Run: `docker compose -p agn004 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm -v "$PWD/apps/api:/app" api-test alembic upgrade 0046_agent_orgs:0047_agent_students_crm --sql`
Expected: only `ADD COLUMN … NULL`, constraint and index DDL; no `UPDATE`/`DELETE`.

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/test_agn_004_migration.py
git commit -m "test(agn-004): migration 0047 round trip and downgrade guards"
```

---

### Task 3: Staff guards (G2, identical to AGN-002)

**Files:**
- Modify: `apps/api/app/core/rbac.py` (after `agent_denial_reason`), `apps/api/app/services/agent_orgs.py`, `apps/api/app/api/agent_team.py`, `apps/api/app/api/workflows.py` (commissions ~L2306, ~L2337), `apps/api/app/api/portal.py`, `apps/api/app/services/portal.py` (`_agent`), `apps/api/app/api/admin.py` (~L1008, ~L1054, ~L1088–1096), `apps/api/app/api/auth.py` (`me`), `apps/api/app/schemas.py` (`UserOut`)
- Create: `apps/api/tests/test_agn_004_staff_guards.py`

**Interfaces:**
- Produces: `app.core.rbac.is_agent_staff(user) -> bool`; `app.services.agent_orgs.MASTER`, `STAFF`; `app.services.agent_orgs.lock_active_org(db, org_id) -> AgentOrg` (403 when the org is not active); `workflows._require_agent_master(user) -> None`; `UserOut.agent_member_role: str | None`.

- [ ] **Step 1: Write the failing tests**

```python
"""AGN-004 G2/G3 -- staff keep AGN-002's reach: Team and Commissions stay Master-only (identical to AGN-002 S1)."""

import pytest
from sqlalchemy import select

from app.models import AgentCommission, AgentOrg, Notification, OverseasApplication
from app.services.agent_orgs import count_active_masters, notification_recipients
from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn004_helpers import mk_staff


@pytest.fixture
async def agency(db_session):
    ctx = await mk_active_org(db_session, name="Guard Agency")
    return ctx | {"staff": await mk_staff(db_session, ctx["org"])}


MASTER_ONLY = [
    ("get", "/api/v1/workflows/overseas/agent/team", 403),
    ("post", "/api/v1/workflows/overseas/agent/team/masters", 403),
    ("get", "/api/v1/workflows/overseas/agent/commissions", 403),
    ("get", "/api/v1/portal/overseas/agent/team", 403),
    ("get", "/api/v1/portal/overseas/agent/commissions", 403),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "url", "status"), MASTER_ONLY)
async def test_staff_are_refused_master_only_pages(agency, method, url, status):
    async with client_for(agency["staff"]["user"].email) as c:
        body = {"full_name": "X", "email": "x@example.local"} if method == "post" else None
        response = await getattr(c, method)(url, **({"json": body} if body else {}))
    assert response.status_code == status, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["dashboard", "students", "applications", "documents", "reports"])
async def test_staff_open_the_other_agent_pages(agency, section):
    async with client_for(agency["staff"]["user"].email) as c:
        response = await c.get(f"/api/v1/portal/overseas/agent/{section}")
    assert response.status_code == 200
    # The dashboard's description sentence mentions commissions; the KPI and report rows are what AGN-002 hides.
    assert "Claimable commission" not in response.text and "Paid commission" not in response.text


@pytest.mark.asyncio
async def test_staff_never_count_as_masters_or_get_commission_notifications(db_session, agency):
    assert await count_active_masters(db_session, agency["org"].id) == 1
    recipients = await notification_recipients(db_session, agency["staff"]["user"])
    assert [u.id for u in recipients] == [agency["master"].id]


@pytest.mark.asyncio
async def test_team_lists_masters_only(agency):
    async with client_for(agency["master"].email) as c:
        body = (await c.get("/api/v1/workflows/overseas/agent/team")).json()
    assert [m["code"] for m in body["masters"]] == [agency["member"].code]


@pytest.mark.asyncio
async def test_me_reports_the_member_role(agency):
    async with client_for(agency["staff"]["user"].email) as c:
        assert (await c.get("/api/v1/auth/me")).json()["agent_member_role"] == "staff"
    async with client_for(agency["master"].email) as c:
        assert (await c.get("/api/v1/auth/me")).json()["agent_member_role"] == "master"


@pytest.mark.asyncio
async def test_overseas_admin_cannot_approve_a_staff_user(db_session, agency):
    admin = await mk_user(db_session, role="overseas_admin")
    async with client_for(admin.email) as c:
        response = await c.post(f"/api/v1/overseas-admin/agents/{agency['staff']['user'].id}/approve")
        listed = await c.get("/api/v1/overseas-admin/agents")
    assert response.status_code == 422 and response.json()["detail"] == "Staff accounts are managed by their agency"
    assert listed.status_code == 200 and agency["staff"]["user"].email not in listed.text


@pytest.mark.asyncio
async def test_suspended_agency_denies_its_staff(db_session, agency):
    org = await db_session.get(AgentOrg, agency["org"].id, populate_existing=True)
    org.status = "suspended"
    await db_session.commit()
    async with client_for(agency["staff"]["user"].email) as c:
        response = await c.get("/api/v1/portal/overseas/agent/students")
    assert response.status_code == 403 and response.json()["detail"] == "Your agency's account is suspended"
```

- [ ] **Step 2: Run to verify failure** — `API_TEST tests/test_agn_004_staff_guards.py`. Expected: FAIL — staff get `200` on team/commissions, `agent_member_role` missing (`KeyError`), `count_active_masters` returns 2.

- [ ] **Step 3: Implement (copy AGN-002's code verbatim)**

`core/rbac.py`, after `agent_denial_reason`:

```python
def is_agent_staff(user) -> bool:
    """AGN-002 (DEC-SCOPE-040 S1/S2): a staff member of an agent organisation. Staff share `role='agent'` with Masters, so the
    Master-only actions (team management, commissions) call this. Reads the membership `get_current_user` eager-loads."""

    if user.role != "agent":
        return False
    membership = user.agent_membership
    return membership is not None and membership.role == "staff"
```

`services/agent_orgs.py`:
- After `MASTER_LIMIT = 3`: `MASTER, STAFF = "master", "staff"  # AgentOrgMember.role (AGN-002 adds staff)`.
- `count_active_masters` → AGN-002's body (docstring `"""Active Masters only; staff never count (AGN-002 S2)."""`, filter `AgentOrgMember.role == MASTER`).
- `deactivate_master`: member lookup and the `others` query gain `AgentOrgMember.role == MASTER` (AGN-002's lines).
- `notification_recipients`: AGN-002's version (filter `role == MASTER`, docstring "every active Master (never staff, AGN-002)").
- Add, after `lock_org`:

```python
async def lock_active_org(db: AsyncSession, org_id) -> AgentOrg:
    """`lock_org`, then refuse an organisation suspended (or no longer active) between the request's gate check and the lock."""
    from app.core.rbac import PENDING_MESSAGE, SUSPENDED_MESSAGE

    org = await lock_org(db, org_id)
    if org.status != "active":
        raise HTTPException(403, SUSPENDED_MESSAGE if org.status == "suspended" else PENDING_MESSAGE)
    return org
```

`api/agent_team.py`: import `is_agent_staff` and `MASTER`, `lock_active_org`; add `MASTER_ONLY = "Only an agency Master can manage the team"`; in `_require_master` after the denial check add AGN-002's lines `if is_agent_staff(user):  # AGN-002 (S1): staff never manage the team` / `raise HTTPException(403, MASTER_ONLY)`; `team()` query gains `AgentOrgMember.role == MASTER` (AGN-002's formatting); `_locked_active_org` body becomes `return await lock_active_org(db, membership.org_id)`.

`api/workflows.py`: import `is_agent_staff`; add AGN-002's `_require_agent_master` after `_require`; call it right after `_require(user, {"agent"}, "overseas")` in `agent_commissions` and `claim_commission`.

`api/portal.py`: AGN-002's lines after the denial check:

```python
    # AGN-002 (DEC-SCOPE-040 S1): the agency's team and commissions are Master-only pages.
    if is_agent_staff(user) and section in {"team", "commissions"}:
        raise HTTPException(403, "Only an agency Master can open this page")
```

`services/portal._agent`: AGN-002's `staff = is_agent_staff(user)`, `commissions = [] if staff else …`, dashboard KPIs and reports "Paid commission" row omitted for staff, `team` query `AgentOrgMember.role == "master"` — copy the AGN-002 hunk shown in spec §5.1 / the AGN-002 branch verbatim.

`api/admin.py`: AGN-002's three hunks (`_pending_agent_assignment` staff check → `422 "Staff accounts are managed by their agency"`; `list_agents` excludes staff; agent-org search and masters list filter `role == "master"`).

`schemas.UserOut`: add `agent_member_role: str | None = None` with AGN-002's comment. `auth.me`:

```python
@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    out = UserOut.model_validate(user)
    # AGN-002: the portal hides Master-only pages from staff (the server refuses them regardless).
    out.agent_member_role = user.agent_membership.role if user.agent_membership else None
    return out
```

- [ ] **Step 4: Run to verify pass** — `API_TEST tests/test_agn_004_staff_guards.py tests/test_agn_001_team.py tests/test_agn_001_org_admin.py tests/test_agn_001_registration_and_gate.py tests/test_agt_003_commission_accrual.py tests/test_agt_004_commission_payout.py tests/test_sec_001_audit_trail.py`. Expected: PASS.

- [ ] **Step 5: Refactor check** — `git diff feature/agn-002-staff-logins -- apps/api/app/core/rbac.py` shows no difference in `is_agent_staff`; repeat for the other G2 hunks and align any wording drift.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/core/rbac.py apps/api/app/services/agent_orgs.py apps/api/app/api/agent_team.py apps/api/app/api/workflows.py apps/api/app/api/portal.py apps/api/app/services/portal.py apps/api/app/api/admin.py apps/api/app/api/auth.py apps/api/app/schemas.py apps/api/tests/test_agn_004_staff_guards.py
git commit -m "feat(agn-004): staff guards identical to AGN-002 -- team and commissions Master-only"
```

---

### Task 4: Scope helpers and Staff narrowing on existing agent paths (G4)

**Files:**
- Create: `apps/api/app/services/agent_students.py` (scope helpers only in this task)
- Modify: `apps/api/app/api/workflows.py` (`_assigned_application` ~L152; `create_overseas_application` ~L1749; `list_overseas_applications` ~L1838; `add_document` ~L1999; `download_student_document` ~L2065; `agent_students` ~L2279; `add_agent_student` ~L2286), `apps/api/app/api/lookups.py` (~L115–125, ~L164), `apps/api/app/services/portal.py` (`_agent`)
- Create: `apps/api/tests/test_agn_004_staff_scope.py`

**Interfaces:**
- Produces: `app.services.agent_students.student_scope(user) -> list[ColumnElement]`, `visible_student_user_ids(user) -> Select`, `application_scope(user) -> list[ColumnElement]`, `phone_digits(phone: str | None) -> str | None`.

- [ ] **Step 1: Write the failing tests**

```python
"""AGN-004 G4 -- staff see only their assigned students on every existing agent path; Masters unchanged (spec §5.3, AC02, AC04, AC06)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AgentStudent, Country, OverseasApplication, StudentDocument, University
from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn004_helpers import mk_staff


async def _university(db) -> University:
    country = Country(slug=f"a4-c-{uuid.uuid4().hex[:8]}", name="Testland", overview="", tuition="", living_expenses="", visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[])
    db.add(country)
    await db.flush()
    uni = University(country_id=country.id, slug=f"a4-u-{uuid.uuid4().hex[:8]}", name=f"A4 Uni {uuid.uuid4().hex[:6]}", city="", overview="", eligibility="", requirements=[], deadlines=[], scholarships=[])
    db.add(uni)
    await db.commit()
    return uni


async def _linked(db, *, master, member, name: str, university) -> dict:
    student = await mk_user(db, role="overseas_student", full_name=name)
    link = AgentStudent(agent_id=master.id, student_id=student.id, status="active", assigned_member_id=member.id if member else None)
    db.add(link)
    app = OverseasApplication(student_id=student.id, university_id=university.id, agent_id=master.id, intake="Sep 2027", status="submitted")
    db.add(app)
    await db.flush()
    doc = StudentDocument(student_id=student.id, application_id=app.id, document_type="passport", file_url="local/a4.pdf")
    db.add(doc)
    await db.commit()
    return {"student": student, "link": link, "application": app, "document": doc}


@pytest.fixture
async def agency(db_session):
    ctx = await mk_active_org(db_session, name="Scope Agency")
    uni = await _university(db_session)
    s1, s2 = await mk_staff(db_session, ctx["org"], full_name="Staff One"), await mk_staff(db_session, ctx["org"], full_name="Staff Two")
    mine = await _linked(db_session, master=ctx["master"], member=s1["member"], name="Mine Student", university=uni)
    theirs = await _linked(db_session, master=ctx["master"], member=s2["member"], name="Theirs Student", university=uni)
    unassigned = await _linked(db_session, master=ctx["master"], member=None, name="Nobody Student", university=uni)
    return ctx | {"s1": s1, "s2": s2, "mine": mine, "theirs": theirs, "unassigned": unassigned, "uni": uni}


LISTS = [
    ("/api/v1/workflows/overseas/agent/students", "student_id", "student"),
    ("/api/v1/workflows/overseas/applications", "id", "application"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("url", "key", "kind"), LISTS)
async def test_staff_lists_hold_only_their_assigned_students(agency, url, key, kind):
    async with client_for(agency["s1"]["user"].email) as c:
        ids = {str(r[key]) for r in (await c.get(url)).json()}
    assert str(agency["mine"][kind].id) in ids
    assert str(agency["theirs"][kind].id) not in ids and str(agency["unassigned"][kind].id) not in ids


@pytest.mark.asyncio
@pytest.mark.parametrize(("url", "key", "kind"), LISTS)
async def test_master_lists_are_unchanged(agency, url, key, kind):
    async with client_for(agency["master"].email) as c:
        ids = {str(r[key]) for r in (await c.get(url)).json()}
    assert {str(agency[x][kind].id) for x in ("mine", "theirs", "unassigned")} <= ids


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["dashboard", "students", "applications", "documents", "reports"])
async def test_staff_portal_pages_never_mention_another_staff_members_student(agency, section):
    async with client_for(agency["s1"]["user"].email) as c:
        text = (await c.get(f"/api/v1/portal/overseas/agent/{section}")).text
    assert "Theirs Student" not in text and "Nobody Student" not in text


@pytest.mark.asyncio
async def test_staff_cannot_reach_another_staff_members_application_or_document(agency):
    theirs = agency["theirs"]
    async with client_for(agency["s1"]["user"].email) as c:
        upload = await c.post("/api/v1/workflows/overseas/documents", json={"student_id": str(theirs["student"].id), "application_id": str(theirs["application"].id), "document_type": "transcript", "file_url": "local/x.pdf", "content_type": "application/pdf", "file_size": 10})
        download = await c.get(f"/api/v1/workflows/overseas/documents/{theirs['document'].id}/download")
        create = await c.post("/api/v1/workflows/overseas/applications", json={"student_id": str(theirs["student"].id), "university_id": str(agency["uni"].id), "intake": "Jan 2028"})
    assert upload.status_code == 403 and download.status_code == 403 and create.status_code == 403


@pytest.mark.asyncio
async def test_staff_lookups_are_narrowed(agency):
    async with client_for(agency["s1"]["user"].email) as c:
        students = (await c.get("/api/v1/lookups/overseas-students")).json()["items"]
        apps = (await c.get("/api/v1/lookups/overseas-applications")).json()["items"]
    assert {i["id"] for i in students} == {str(agency["mine"]["student"].id)}
    assert {i["id"] for i in apps} == {str(agency["mine"]["application"].id)}


@pytest.mark.asyncio
async def test_a_staff_link_is_assigned_to_them(db_session, agency):
    student = await mk_user(db_session, role="overseas_student", full_name="Linked By Staff")
    async with client_for(agency["s1"]["user"].email) as c:
        response = await c.post("/api/v1/workflows/overseas/agent/students", json={"student_id": str(student.id)})
    assert response.status_code == 201
    link = await db_session.scalar(select(AgentStudent).where(AgentStudent.student_id == student.id).execution_options(populate_existing=True))
    assert link.assigned_member_id == agency["s1"]["member"].id


@pytest.mark.asyncio
async def test_archived_link_leaves_the_roster_and_cannot_be_relinked(db_session, agency):
    link = await db_session.get(AgentStudent, agency["unassigned"]["link"].id, populate_existing=True)
    link.status = "archived"
    await db_session.commit()
    async with client_for(agency["master"].email) as c:
        roster = {r["student_id"] for r in (await c.get("/api/v1/workflows/overseas/agent/students")).json()}
        relink = await c.post("/api/v1/workflows/overseas/agent/students", json={"student_id": str(agency["unassigned"]["student"].id)})
    assert str(agency["unassigned"]["student"].id) not in roster
    assert relink.status_code == 409 and relink.json()["detail"] == "This student is archived — unarchive them first"


@pytest.mark.asyncio
async def test_archived_link_keeps_its_applications_visible(db_session, agency):
    link = await db_session.get(AgentStudent, agency["unassigned"]["link"].id, populate_existing=True)
    link.status = "archived"
    await db_session.commit()
    async with client_for(agency["master"].email) as c:
        apps = {r["id"] for r in (await c.get("/api/v1/workflows/overseas/applications")).json()}
        docs_page = (await c.get("/api/v1/portal/overseas/agent/documents")).text
        students_page = (await c.get("/api/v1/portal/overseas/agent/students")).text
    assert str(agency["unassigned"]["application"].id) in apps
    assert str(agency["unassigned"]["document"].id) in docs_page
    assert "Nobody Student" not in students_page
```

- [ ] **Step 2: Run to verify failure** — `API_TEST tests/test_agn_004_staff_scope.py`. Expected: FAIL — staff lists contain "Theirs Student"; staff link `assigned_member_id is None`; archived link still in roster; relink says "already linked".

- [ ] **Step 3: Implement the helpers**

`apps/api/app/services/agent_students.py` (first slice; Task 6 appends to it):

```python
"""AGN-004 / DEC-SCOPE-041 -- agent students: scoping, students with no login, duplicate warning.

Functions only (the shape of services/agent_orgs.py); write functions never commit -- the router locks the organisation, writes,
audits and commits. Spec: docs/superpowers/specs/2026-09-30-agn-004-agent-students-design.md.
"""

import logging
import re

from sqlalchemy import ColumnElement, Select, select

from app.core.rbac import is_agent_staff
from app.models import AgentStudent, OverseasApplication, User
from app.services.agent_orgs import org_member_ids

logger = logging.getLogger("app.agent_students")

PHONE_MIN_DIGITS = 7


def student_scope(user: User) -> list[ColumnElement]:
    """The agent_students rows the caller may see: the organisation's (AGN-001 D1); a staff member only those assigned to them
    (G4). For a Master this is exactly the AGN-001 clause."""
    clauses = [AgentStudent.agent_id.in_(org_member_ids(user))]
    if is_agent_staff(user):
        clauses.append(AgentStudent.assigned_member_id == user.agent_membership.id)
    return clauses


def visible_student_user_ids(user: User) -> Select:
    """User ids of the linked students (with an account) the caller may see."""
    return select(AgentStudent.student_id).where(*student_scope(user), AgentStudent.student_id.is_not(None))


def application_scope(user: User) -> list[ColumnElement]:
    """The organisation's applications; a staff member only those of their assigned students (G4)."""
    clauses = [OverseasApplication.agent_id.in_(org_member_ids(user))]
    if is_agent_staff(user):
        clauses.append(OverseasApplication.student_id.in_(visible_student_user_ids(user)))
    return clauses


def phone_digits(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")[:20]
    return digits or None
```

- [ ] **Step 4: Apply the helpers at each existing path** (import `from app.services.agent_students import application_scope, student_scope, visible_student_user_ids`):

`workflows._assigned_application` — replace the `agent_in_scope` line:

```python
    # AGN-001 (D1): the organisation's applications; AGN-004 (G4): a staff member only their assigned students'.
    agent_in_scope = user.role == "agent" and bool(
        await db.scalar(select(OverseasApplication.id).where(OverseasApplication.id == item.id, *application_scope(user)))
    )
```

`create_overseas_application` agent link check:

```python
        linked = await db.scalar(select(AgentStudent.id).where(*student_scope(user), AgentStudent.student_id == student_id, AgentStudent.status == "active"))
```

`list_overseas_applications` agent branch: `stmt = stmt.where(*application_scope(user))`.

`add_document` agent branch: `linked = await db.scalar(select(AgentStudent.id).where(AgentStudent.student_id == student_id, *student_scope(user)))`.

`download_student_document` agent branch: `assigned = await db.scalar(select(AgentStudent.id).where(AgentStudent.student_id == item.student_id, *student_scope(user)))`.

Roster:

```python
@router.get("/overseas/agent/students")
async def agent_students(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require(user, {"agent"}, "overseas")
    # AGN-004: archived links leave this list (D5); a staff member sees only their assigned students (G4).
    rows = (
        await db.execute(
            select(AgentStudent, User).join(User, User.id == AgentStudent.student_id).where(*student_scope(user), AgentStudent.status == "active").order_by(User.full_name)
        )
    ).all()
    return [{"link_id": link.id, "student_id": student.id, "student": student.full_name, "email": student.email, "phone": student.phone, "status": link.status} for link, student in rows]
```

Link (keep the org-wide duplicate check; add archived message and staff assignment):

```python
    existing = await db.scalar(select(AgentStudent).where(AgentStudent.agent_id.in_(org_member_ids(user)), AgentStudent.student_id == student.id))
    if existing:
        raise HTTPException(409, "This student is archived — unarchive them first" if existing.status == "archived" else "Student is already linked to this agency")
    assigned = user.agent_membership.id if is_agent_staff(user) else None  # AGN-004 D4: a staff member's link is theirs
    item = AgentStudent(agent_id=user.id, student_id=student.id, status="active", assigned_member_id=assigned)
    db.add(item)
    await db.flush()
    await _audit(db, user, "agent.student_link", "agent_student", item.id, {"student_id": student.id, **({"assigned_member_id": str(assigned)} if assigned else {})})
```

`lookups.py` agent non-link branch (`purpose != "link"`): `stmt = stmt.where(User.id.in_(visible_student_user_ids(user)))`; `overseas-applications` agent branch: `stmt = stmt.where(*application_scope(user))`. The `purpose == "link"` exclusion stays org-wide.

`services/portal._agent` top queries:

```python
    # AGN-001 (D1) organisation scope; AGN-004 (G4) a staff member's assigned students only; archived links leave the list (D5).
    students = (await db.execute(select(AgentStudent, User).join(User, User.id == AgentStudent.student_id).where(*student_scope(user), AgentStudent.status == "active"))).all()
    applications = (
        await db.execute(
            select(OverseasApplication, University, User)
            .join(University, University.id == OverseasApplication.university_id)
            .join(User, User.id == OverseasApplication.student_id)
            .where(*application_scope(user))
            .order_by(OverseasApplication.updated_at.desc())
        )
    ).all()
```

(Import `student_scope`, `application_scope` inside `services/portal.py` from `app.services.agent_students`.)

- [ ] **Step 5: Run to verify pass** — `API_TEST tests/test_agn_004_staff_scope.py tests/test_agn_001_tenancy.py tests/test_agt_002_referrals.py tests/test_enh_031_lookups_students.py tests/test_rpt_002_overseas_reporting.py tests/test_agt_003_commission_accrual.py`. Expected: PASS.

- [ ] **Step 6: Refactor sweep** — `grep -n "org_member_ids(user)" apps/api/app/api/workflows.py apps/api/app/api/lookups.py apps/api/app/services/portal.py`; every remaining hit must be a commissions query, the link duplicate check, or the link-lookup exclusion (org-wide by design). Rerun the Step 5 command.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/services/agent_students.py apps/api/app/api/workflows.py apps/api/app/api/lookups.py apps/api/app/services/portal.py apps/api/tests/test_agn_004_staff_scope.py
git commit -m "feat(agn-004): staff narrowed to assigned students on every agent path; archived links leave the roster"
```

---

### Task 5: Record schemas

**Files:**
- Modify: `apps/api/app/schemas.py` (after `AgentMasterInvite`)
- Create: `apps/api/tests/test_agn_004_schemas.py`

**Interfaces:**
- Produces: `AgentStudentRecordCreate`, `AgentStudentRecordUpdate`, `AgentStudentAssign` (Pydantic, `extra="forbid"`), and `RECORD_FIELDS: tuple[str, ...]` (the editable field names).

- [ ] **Step 1: Write the failing tests**

```python
"""AGN-004 -- request schemas for students with no login (spec §5.5)."""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas import AgentStudentAssign, AgentStudentRecordCreate, AgentStudentRecordUpdate


def test_minimal_create_needs_only_a_name():
    rec = AgentStudentRecordCreate(full_name="  Asha Rao  ")
    assert rec.full_name == "Asha Rao" and rec.confirm_duplicate is False


@pytest.mark.parametrize("payload", [
    {"full_name": "   "},
    {"full_name": "A" * 161},
    {"full_name": "Asha", "email": "not-an-email"},
    {"full_name": "Asha", "date_of_birth": (date.today() + timedelta(days=1)).isoformat()},
    {"full_name": "Asha", "date_of_birth": "1899-12-31"},
    {"full_name": "Asha", "graduation_year": 1949},
    {"full_name": "Asha", "graduation_year": date.today().year + 7},
    {"full_name": "Asha", "notes": "x" * 2001},
    {"full_name": "Asha‮evil"},
    {"full_name": "Asha", "institution": "Bad\x00Uni"},
    {"full_name": "Asha", "status": "archived"},
    {"full_name": "Asha", "assigned_member_id": "00000000-0000-0000-0000-000000000000"},
    {"full_name": "Asha", "agent_id": "00000000-0000-0000-0000-000000000000"},
])
def test_create_rejects_bad_or_server_owned_input(payload):
    with pytest.raises(ValidationError):
        AgentStudentRecordCreate(**payload)


def test_email_is_lowercased_and_blank_optional_fields_become_none():
    rec = AgentStudentRecordCreate(full_name="Asha", email=" Asha@Example.COM ", phone="  ", preferred_country="")
    assert rec.email == "asha@example.com" and rec.phone is None and rec.preferred_country is None


def test_notes_keep_line_breaks():
    assert AgentStudentRecordCreate(full_name="Asha", notes="line one\nline two").notes == "line one\nline two"


def test_update_tracks_only_sent_fields_and_refuses_clearing_the_name():
    upd = AgentStudentRecordUpdate(phone=None)
    assert upd.model_fields_set == {"phone"}
    with pytest.raises(ValidationError):
        AgentStudentRecordUpdate(full_name=None)
    with pytest.raises(ValidationError):
        AgentStudentRecordUpdate(student_id="00000000-0000-0000-0000-000000000000")


def test_assign_accepts_a_member_or_null():
    assert AgentStudentAssign(member_id=None).member_id is None
    with pytest.raises(ValidationError):
        AgentStudentAssign()
```

- [ ] **Step 2: Run to verify failure** — `API_TEST tests/test_agn_004_schemas.py`. Expected: FAIL — `ImportError: cannot import name 'AgentStudentAssign'`.

- [ ] **Step 3: Implement** (in `schemas.py`, after `AgentMasterInvite`; `clean_free_text` is defined later in the module, so the validators call it at run time — fine):

```python
RECORD_FIELDS = (
    "full_name", "email", "phone", "date_of_birth", "highest_qualification", "institution", "graduation_year",
    "preferred_country", "preferred_course", "preferred_intake", "notes",
)
_RECORD_LIMITS = {"full_name": 160, "phone": 40, "highest_qualification": 200, "institution": 200, "preferred_country": 120, "preferred_course": 200, "preferred_intake": 40, "notes": 2000}
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class _AgentStudentRecordFields(BaseModel):
    """AGN-004 (DEC-SCOPE-041, EVID-015 §5 Step 1): a student with no login. Server-owned fields (agent, account, status,
    assignment, archive) are not accepted -- `extra="forbid"` answers 422 (mass assignment)."""

    model_config = {"extra": "forbid"}
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = None
    date_of_birth: date | None = None
    highest_qualification: str | None = None
    institution: str | None = None
    graduation_year: int | None = None
    preferred_country: str | None = None
    preferred_course: str | None = None
    preferred_intake: str | None = None
    notes: str | None = None

    @field_validator("phone", "highest_qualification", "institution", "preferred_country", "preferred_course", "preferred_intake", "notes")
    @classmethod
    def _text(cls, value, info):
        return clean_free_text(value, _RECORD_LIMITS[info.field_name])

    @field_validator("email")
    @classmethod
    def _email(cls, value):
        value = (value or "").strip().lower()
        if not value:
            return None
        if not _EMAIL.match(value):
            raise PydanticCustomError("invalid_email", "Enter a valid email address")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, value):
        if value is not None and not (date(1900, 1, 1) <= value <= date.today()):
            raise PydanticCustomError("invalid_date_of_birth", "Date of birth must be between 1900 and today")
        return value

    @field_validator("graduation_year")
    @classmethod
    def _year(cls, value):
        if value is not None and not (1950 <= value <= date.today().year + 6):
            raise PydanticCustomError("invalid_graduation_year", "Graduation year is out of range")
        return value


class AgentStudentRecordCreate(_AgentStudentRecordFields):
    full_name: str
    confirm_duplicate: bool = False

    @field_validator("full_name")
    @classmethod
    def _name(cls, value):
        value = clean_free_text(value, 160)
        if not value:
            raise PydanticCustomError("blank_full_name", "Full name is required")
        return value


class AgentStudentRecordUpdate(_AgentStudentRecordFields):
    """Omitted = unchanged; null clears an optional field; the name cannot be cleared."""

    full_name: str | None = None
    confirm_duplicate: bool = False

    @field_validator("full_name")
    @classmethod
    def _name(cls, value):
        value = clean_free_text(value, 160) if value is not None else None
        if not value:
            raise PydanticCustomError("blank_full_name", "Full name is required")
        return value


class AgentStudentAssign(BaseModel):
    model_config = {"extra": "forbid"}
    member_id: UUID | None
```

Note: `field_validator` does not run for an omitted field, so `AgentStudentRecordUpdate()` with no `full_name` is valid; sending `full_name: null` runs `_name` → error (pydantic runs validators on explicit `None` when the field type allows `None` and the validator is mode "after"). Verify with the test.

- [ ] **Step 4: Run to verify pass** — `API_TEST tests/test_agn_004_schemas.py`. Expected: PASS. If `full_name=None` does not fail, change `_name` in `AgentStudentRecordUpdate` to `mode="before"`-free explicit check via `@model_validator(mode="after")`: `if "full_name" in self.model_fields_set and not self.full_name: raise …`, and rerun.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas.py apps/api/tests/test_agn_004_schemas.py
git commit -m "feat(agn-004): request schemas for students with no login"
```

---

### Task 6: Router — list, create, detail, duplicate warning

**Files:**
- Modify: `apps/api/app/services/agent_students.py` (append)
- Create: `apps/api/app/api/agent_students.py`
- Modify: `apps/api/app/main.py` (import + router tuple)
- Create: `apps/api/tests/test_agn_004_students.py`

**Interfaces:**
- Consumes: `student_scope`, `phone_digits` (Task 4); `lock_active_org` (Task 3); schemas (Task 5).
- Produces (service): `record_item(row, account, assignee_member, assignee_user) -> dict`, `record_detail(db, row) -> dict`, `load_scoped(db, user, student_id, *, lock=False) -> AgentStudent` (404), `find_duplicates(db, user, *, email, digits, exclude_id=None) -> tuple[list[dict], int]`, `create_record(db, user, data: dict) -> AgentStudent`, `list_page(db, user, *, q, include_archived, assigned, limit, offset) -> dict`.
- Produces (router): `router` with `GET ""`, `POST ""`, `GET /{student_id}`; helpers `_gate(user) -> AgentOrgMember`, `_require_master_action(user, message)`.

- [ ] **Step 1: Write the failing tests**

```python
"""AGN-004 -- list, create, detail and the duplicate warning (spec §5.4-§5.5; AC01, AC02, AC05, AC07, AC08, AC11)."""

import asyncio
import logging

import pytest
from sqlalchemy import func, select

from app.api import agent_students as router_module
from app.models import AgentStudent, AuditLog, User
from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn004_helpers import RECORDS, mk_record, mk_staff


@pytest.fixture
async def agency(db_session):
    ctx = await mk_active_org(db_session, name="Records Agency")
    other = await mk_active_org(db_session, name="Other Agency")
    s1, s2 = await mk_staff(db_session, ctx["org"], full_name="Rec Staff One"), await mk_staff(db_session, ctx["org"], full_name="Rec Staff Two")
    return ctx | {"other": other, "s1": s1, "s2": s2}


@pytest.mark.asyncio
async def test_master_creates_a_student_with_no_login_and_no_user_row(db_session, agency):
    users_before = await db_session.scalar(select(func.count()).select_from(User))
    async with client_for(agency["master"].email) as c:
        response = await c.post(RECORDS, json={"full_name": "Asha Rao", "email": "asha.rec@example.local", "preferred_country": "Canada"})
    assert response.status_code == 201, response.text
    body = response.json()["student"]
    assert body["has_login"] is False and body["assigned_to"] is None and body["status"] == "active"
    assert await db_session.scalar(select(func.count()).select_from(User)) == users_before
    row = await db_session.get(AgentStudent, body["id"], populate_existing=True)
    assert row.student_id is None and row.agent_id == agency["master"].id
    assert set(body) >= {"id", "has_login", "full_name", "email", "phone", "preferred_country", "preferred_intake", "status", "assigned_to", "created_at"}
    assert not {"agent_id", "student_id", "phone_digits"} & set(body)


@pytest.mark.asyncio
async def test_staff_creation_is_assigned_to_the_creator(agency):
    async with client_for(agency["s1"]["user"].email) as c:
        body = (await c.post(RECORDS, json={"full_name": "Staff Made"})).json()["student"]
    assert body["assigned_to"]["id"] == str(agency["s1"]["member"].id) and body["assigned_to"]["code"].endswith("-S001")


@pytest.mark.asyncio
async def test_staff_list_and_detail_are_assigned_only(db_session, agency):
    mine = await mk_record(db_session, agent=agency["master"], full_name="Mine Rec", assigned_member=agency["s1"]["member"])
    theirs = await mk_record(db_session, agent=agency["master"], full_name="Theirs Rec", assigned_member=agency["s2"]["member"])
    unassigned = await mk_record(db_session, agent=agency["master"], full_name="Nobody Rec")
    foreign = await mk_record(db_session, agent=agency["other"]["master"], full_name="Foreign Rec")
    async with client_for(agency["s1"]["user"].email) as c:
        ids = {i["id"] for i in (await c.get(RECORDS)).json()["items"]}
        codes = {sid: (await c.get(f"{RECORDS}/{sid}")).status_code for sid in (mine.id, theirs.id, unassigned.id, foreign.id)}
        filtered = await c.get(RECORDS, params={"assigned": "none"})
    assert ids == {str(mine.id)}
    assert codes == {mine.id: 200, theirs.id: 404, unassigned.id: 404, foreign.id: 404}
    assert filtered.status_code == 422


@pytest.mark.asyncio
async def test_other_agency_master_gets_404_and_never_sees_rows(db_session, agency):
    row = await mk_record(db_session, agent=agency["master"], full_name="Private Rec")
    async with client_for(agency["other"]["master"].email) as c:
        assert (await c.get(f"{RECORDS}/{row.id}")).status_code == 404
        assert str(row.id) not in {i["id"] for i in (await c.get(RECORDS)).json()["items"]}


@pytest.mark.asyncio
async def test_list_filters_paging_and_archived(db_session, agency):
    a = await mk_record(db_session, agent=agency["master"], full_name="Paging Alpha")
    b = await mk_record(db_session, agent=agency["master"], full_name="Paging Beta", status="archived")
    async with client_for(agency["master"].email) as c:
        default = {i["id"] for i in (await c.get(RECORDS, params={"q": "Paging"})).json()["items"]}
        everything = {i["id"] for i in (await c.get(RECORDS, params={"q": "Paging", "include_archived": "true"})).json()["items"]}
        page = (await c.get(RECORDS, params={"q": "Paging", "include_archived": "true", "limit": 1})).json()
        bad = [(await c.get(RECORDS, params=p)).status_code for p in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"q": "x" * 101}, {"assigned": "someone"})]
    assert default == {str(a.id)} and everything == {str(a.id), str(b.id)}
    assert page["total"] == 2 and len(page["items"]) == 1 and page["limit"] == 1 and page["offset"] == 0
    assert bad == [422] * 5


@pytest.mark.asyncio
async def test_search_metacharacters_match_literally(db_session, agency):
    await mk_record(db_session, agent=agency["master"], full_name="Percent 100% Student")
    await mk_record(db_session, agent=agency["master"], full_name="Plain Student")
    async with client_for(agency["master"].email) as c:
        names = {i["full_name"] for i in (await c.get(RECORDS, params={"q": "100%"})).json()["items"]}
        underscore = (await c.get(RECORDS, params={"q": "_"})).json()["items"]
    assert names == {"Percent 100% Student"} and underscore == []


@pytest.mark.asyncio
async def test_duplicate_email_warns_then_saves_with_confirmation(db_session, agency):
    await mk_record(db_session, agent=agency["master"], full_name="First Dup", email="dup@example.local", status="archived")
    async with client_for(agency["master"].email) as c:
        warned = await c.post(RECORDS, json={"full_name": "Second Dup", "email": "DUP@example.local"})
        saved = await c.post(RECORDS, json={"full_name": "Second Dup", "email": "DUP@example.local", "confirm_duplicate": True})
    detail = warned.json()["detail"]
    assert warned.status_code == 409 and detail["code"] == "possible_duplicate" and detail["message"]
    assert detail["matches"][0]["matched_on"] == ["email"] and detail["matches"][0]["status"] == "archived"
    assert saved.status_code == 201
    override = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_student.duplicate_override", AuditLog.entity_id == saved.json()["student"]["id"]))
    assert override is not None and "dup@" not in str(override.metadata_json)


@pytest.mark.asyncio
async def test_phone_formats_match_on_digits_only(db_session, agency):
    await mk_record(db_session, agent=agency["master"], full_name="Phone One", phone="+91 98765-43210")
    async with client_for(agency["master"].email) as c:
        same = await c.post(RECORDS, json={"full_name": "Phone Two", "phone": "(91) 9876543210"})
        short = await c.post(RECORDS, json={"full_name": "Phone Three", "phone": "12-34"})
        await c.post(RECORDS, json={"full_name": "Phone Four", "phone": "1234"})
    assert same.status_code == 409 and same.json()["detail"]["matches"][0]["matched_on"] == ["phone"]
    assert short.status_code == 201


@pytest.mark.asyncio
async def test_linked_student_account_email_counts_as_a_duplicate(db_session, agency):
    student = await mk_user(db_session, role="overseas_student", full_name="Linked Dup")
    db_session.add(AgentStudent(agent_id=agency["master"].id, student_id=student.id, status="active"))
    await db_session.commit()
    async with client_for(agency["master"].email) as c:
        response = await c.post(RECORDS, json={"full_name": "Typed Again", "email": student.email})
    assert response.status_code == 409 and response.json()["detail"]["matches"][0]["has_login"] is True


@pytest.mark.asyncio
async def test_other_agency_never_triggers_the_warning(db_session, agency):
    await mk_record(db_session, agent=agency["other"]["master"], full_name="Elsewhere", email="elsewhere@example.local")
    async with client_for(agency["master"].email) as c:
        assert (await c.post(RECORDS, json={"full_name": "Here", "email": "elsewhere@example.local"})).status_code == 201


@pytest.mark.asyncio
async def test_staff_see_invisible_matches_only_as_a_count(db_session, agency):
    await mk_record(db_session, agent=agency["master"], full_name="Hidden Match", email="hidden@example.local", assigned_member=agency["s2"]["member"])
    async with client_for(agency["s1"]["user"].email) as c:
        detail = (await c.post(RECORDS, json={"full_name": "Probe", "email": "hidden@example.local"})).json()["detail"]
    assert detail["matches"] == [] and detail["hidden_matches"] == 1
    assert "Hidden Match" not in str(detail)


@pytest.mark.asyncio
async def test_concurrent_creates_with_one_email_save_once(db_session, agency):
    async with client_for(agency["master"].email) as c1, client_for(agency["master"].email) as c2:
        results = await asyncio.gather(
            c1.post(RECORDS, json={"full_name": "Racer A", "email": "race@example.local"}),
            c2.post(RECORDS, json={"full_name": "Racer B", "email": "race@example.local"}),
        )
    assert sorted(r.status_code for r in results) == [201, 409]


@pytest.mark.asyncio
async def test_super_admin_is_not_admitted(db_session):
    admin = await mk_user(db_session, role="super_admin", division="global")
    async with client_for(admin.email) as c:
        assert (await c.get(RECORDS)).status_code == 403


@pytest.mark.asyncio
async def test_create_writes_an_audit_row_without_personal_data(db_session, agency, caplog):
    caplog.set_level(logging.INFO, logger="app.agent_students")
    async with client_for(agency["master"].email) as c:
        sid = (await c.post(RECORDS, json={"full_name": "Audit Me", "email": "audit.me@example.local", "phone": "9999988888"})).json()["student"]["id"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_student.create", AuditLog.entity_id == sid))
    assert audit is not None
    for secret in ("Audit Me", "audit.me@example.local", "9999988888"):
        assert secret not in str(audit.metadata_json) and secret not in caplog.text


def _boom(*args, **kwargs):
    raise RuntimeError("simulated audit-log write failure")


@pytest.mark.asyncio
async def test_create_fails_closed_if_the_audit_write_fails(db_session, agency, monkeypatch, client):
    from tests.agn001_helpers import login

    await login(client, agency["master"].email)
    monkeypatch.setattr(router_module, "AuditLog", _boom)
    with pytest.raises(RuntimeError, match="simulated audit-log write failure"):
        await client.post(RECORDS, json={"full_name": "Never Saved"})
    assert await db_session.scalar(select(AgentStudent).where(AgentStudent.full_name == "Never Saved")) is None


@pytest.mark.asyncio
async def test_server_owned_fields_are_refused(agency):
    async with client_for(agency["s1"]["user"].email) as c:
        response = await c.post(RECORDS, json={"full_name": "Sneaky", "assigned_member_id": str(agency["s2"]["member"].id)})
    assert response.status_code == 422
```

- [ ] **Step 2: Run to verify failure** — `API_TEST tests/test_agn_004_students.py`. Expected: FAIL — `ImportError: cannot import name 'agent_students' from 'app.api'`.

- [ ] **Step 3: Append the service functions** to `services/agent_students.py` (add imports `from fastapi import HTTPException`, `from sqlalchemy import func, or_`, `from sqlalchemy.orm import aliased`, `from app.models import AgentOrgMember`):

```python
Assignee = aliased(User)


def _identity(row: AgentStudent, account: User | None) -> dict:
    """Linked students read name/email/phone from their own account (F2)."""
    source = account if account is not None else row
    return {"full_name": source.full_name, "email": source.email, "phone": source.phone}


def record_item(row: AgentStudent, account: User | None, member: AgentOrgMember | None, member_user: User | None) -> dict:
    return {
        "id": row.id,
        "has_login": row.student_id is not None,
        **_identity(row, account),
        "preferred_country": row.preferred_country,
        "preferred_intake": row.preferred_intake,
        "status": row.status,
        "assigned_to": {"id": member.id, "code": member.code, "full_name": member_user.full_name, "status": member.status} if member else None,
        "created_at": row.created_at,
    }


def _rows_stmt():
    return (
        select(AgentStudent, User, AgentOrgMember, Assignee)
        .outerjoin(User, User.id == AgentStudent.student_id)
        .outerjoin(AgentOrgMember, AgentOrgMember.id == AgentStudent.assigned_member_id)
        .outerjoin(Assignee, Assignee.id == AgentOrgMember.user_id)
    )


async def record_detail(db, row: AgentStudent) -> dict:
    found = (await db.execute(_rows_stmt().where(AgentStudent.id == row.id))).one()
    created_by = await db.get(User, row.agent_id)
    archived_by = await db.get(User, row.archived_by_user_id) if row.archived_by_user_id else None
    return {
        **record_item(*found),
        "date_of_birth": row.date_of_birth,
        "highest_qualification": row.highest_qualification,
        "institution": row.institution,
        "graduation_year": row.graduation_year,
        "preferred_course": row.preferred_course,
        "notes": row.notes,
        "created_by": created_by.full_name if created_by else None,
        "archived_at": row.archived_at,
        "archived_by": archived_by.full_name if archived_by else None,
        "updated_at": row.updated_at,
    }


async def load_scoped(db, user: User, student_id, *, lock: bool = False) -> AgentStudent:
    stmt = select(AgentStudent).where(AgentStudent.id == student_id, *student_scope(user)).execution_options(populate_existing=True)
    row = await db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise HTTPException(404, "Student not found")
    return row


def _like(column, term: str):
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


async def list_page(db, user: User, *, q: str | None, include_archived: bool, assigned, limit: int, offset: int) -> dict:
    filters = list(student_scope(user))
    if not include_archived:
        filters.append(AgentStudent.status == "active")
    if assigned == "none":
        filters.append(AgentStudent.assigned_member_id.is_(None))
    elif assigned is not None:
        filters.append(AgentStudent.assigned_member_id == assigned)
    term = (q or "").strip()
    if term:
        name, email, phone = func.coalesce(User.full_name, AgentStudent.full_name), func.coalesce(User.email, AgentStudent.email), func.coalesce(User.phone, AgentStudent.phone)
        filters.append(or_(_like(name, term), _like(email, term), _like(phone, term)))
    base = _rows_stmt().where(*filters)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(base.order_by(func.coalesce(User.full_name, AgentStudent.full_name), AgentStudent.id).limit(limit).offset(offset))).all()
    return {"items": [record_item(*r) for r in rows], "total": total or 0, "limit": limit, "offset": offset}


async def find_duplicates(db, user: User, *, email: str | None, digits: str | None, exclude_id=None) -> tuple[list[dict], int]:
    """D7/F3/F4: same email or same phone digits inside the caller's agency, archived and linked included. Staff get the rows they
    can see; the others only as a count. Never searches `users` beyond the agency's own linked rows."""
    conditions = []
    if email:
        conditions += [func.lower(AgentStudent.email) == email, func.lower(User.email) == email]
    if digits and len(digits) >= PHONE_MIN_DIGITS:
        conditions += [AgentStudent.phone_digits == digits, func.regexp_replace(User.phone, r"\D", "", "g") == digits]
    if not conditions:
        return [], 0
    stmt = select(AgentStudent, User).outerjoin(User, User.id == AgentStudent.student_id).where(AgentStudent.agent_id.in_(org_member_ids(user)), or_(*conditions))
    if exclude_id is not None:
        stmt = stmt.where(AgentStudent.id != exclude_id)
    staff_member_id = user.agent_membership.id if is_agent_staff(user) else None
    matches, hidden = [], 0
    for row, account in (await db.execute(stmt)).all():
        if staff_member_id is not None and row.assigned_member_id != staff_member_id:
            hidden += 1
            continue
        ident = _identity(row, account)
        matched_on = [label for label, hit in (("email", bool(email) and (ident["email"] or "").lower() == email), ("phone", bool(digits) and phone_digits(ident["phone"]) == digits)) if hit]
        matches.append({"id": row.id, "full_name": ident["full_name"], "has_login": row.student_id is not None, "status": row.status, "matched_on": matched_on})
    return matches, hidden


def duplicate_conflict(matches: list[dict], hidden: int) -> HTTPException:
    return HTTPException(
        409,
        {"message": "A student with this email or phone already exists in your agency", "code": "possible_duplicate", "matches": matches, "hidden_matches": hidden},
    )


def create_record(db, user: User, data: dict) -> AgentStudent:
    """No commit. D4: a staff creator is the assignee; a Master's student starts unassigned."""
    row = AgentStudent(
        agent_id=user.id,
        student_id=None,
        status="active",
        assigned_member_id=user.agent_membership.id if is_agent_staff(user) else None,
        phone_digits=phone_digits(data.get("phone")),
        updated_by_user_id=user.id,
        **data,
    )
    db.add(row)
    return row
```

- [ ] **Step 4: Write the router** `apps/api/app/api/agent_students.py`:

```python
"""AGN-004 -- an agency's students, including students who never log in (DEC-SCOPE-041; spec §5.4).

Masters see the whole agency; staff only students assigned to them (G4); anything outside the caller's scope is 404. Every write
locks the organisation row, writes an audit row in the same transaction and commits once, so the duplicate check and assignment
hold under concurrency.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rbac import agent_denial_reason, is_agent_staff
from app.models import AgentOrgMember, AuditLog, User
from app.schemas import AgentStudentRecordCreate
from app.services.agent_orgs import lock_active_org
from app.services.agent_students import create_record, duplicate_conflict, find_duplicates, list_page, load_scoped, phone_digits, record_detail

logger = logging.getLogger("app.agent_students")

router = APIRouter(prefix="/workflows/overseas/agent/crm/students", tags=["agent-students"])


def _gate(user: User) -> AgentOrgMember:
    if user.role != "agent" or user.division != "overseas":
        raise HTTPException(403, "This role cannot perform this operation")
    reason = agent_denial_reason(user)
    if reason:
        raise HTTPException(403, reason)
    return user.agent_membership


def _audit(db: AsyncSession, user: User, action: str, student_id, metadata: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id, action=f"agent_student.{action}", entity_type="agent_student", entity_id=str(student_id), metadata_json=metadata or {}))


def _log(event: str, membership: AgentOrgMember, user: User, student_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"org_id": str(membership.org_id), "actor_id": str(user.id), "student_id": str(student_id), **extra}})


def _assigned_filter(user: User, assigned: str | None):
    if assigned is None:
        return None
    if is_agent_staff(user):
        raise HTTPException(422, "assigned is a Master-only filter")
    if assigned == "me":
        return user.agent_membership.id
    if assigned == "none":
        return "none"
    try:
        return UUID(assigned)
    except ValueError:
        raise HTTPException(422, "assigned must be me, none or a member id") from None


@router.get("")
async def list_students(
    q: str | None = Query(None, max_length=100),
    include_archived: bool = False,
    assigned: str | None = Query(None, max_length=36),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _gate(user)
    return await list_page(db, user, q=q, include_archived=include_archived, assigned=_assigned_filter(user, assigned), limit=limit, offset=offset)


@router.post("", status_code=201)
async def create_student(payload: AgentStudentRecordCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    await lock_active_org(db, membership.org_id)
    data = payload.model_dump(exclude={"confirm_duplicate"})
    matches, hidden = await find_duplicates(db, user, email=data.get("email"), digits=phone_digits(data.get("phone")))
    if (matches or hidden) and not payload.confirm_duplicate:
        _log("agent_student_duplicate_warned", membership, user, "-", match_count=len(matches) + hidden)
        raise duplicate_conflict(matches, hidden)
    row = create_record(db, user, data)
    await db.flush()
    _audit(db, user, "create", row.id, {"fields": sorted(k for k, v in data.items() if v is not None), "assigned_member_id": str(row.assigned_member_id) if row.assigned_member_id else None})
    if matches or hidden:
        _audit(db, user, "duplicate_override", row.id, {"match_count": len(matches) + hidden})
    await db.commit()
    _log("agent_student_created", membership, user, row.id)
    if matches or hidden:
        _log("agent_student_duplicate_overridden", membership, user, row.id, match_count=len(matches) + hidden)
    return {"student": await record_detail(db, row)}


@router.get("/{student_id}")
async def get_student(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _gate(user)
    return {"student": await record_detail(db, await load_scoped(db, user, student_id))}
```

`main.py`: add `agent_students` to the `from app.api import (...)` list and `agent_students.router` right after `agent_team.router` in the tuple.

- [ ] **Step 5: Run to verify pass** — `API_TEST tests/test_agn_004_students.py`. Expected: PASS. If `test_concurrent_creates…` gives `[201, 201]`, the lock is not taken before `find_duplicates` — fix the order, never the test.

- [ ] **Step 6: Refactor** — the list and detail both build items through `record_item`; `_like` duplicates the project's `lookups._like` escaping rule — if `lookups._pattern` escapes the same way, import and reuse it instead of the local `_like`, then rerun Step 5.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/services/agent_students.py apps/api/app/api/agent_students.py apps/api/app/main.py apps/api/tests/test_agn_004_students.py
git commit -m "feat(agn-004): list, create and view agency students with a within-agency duplicate warning"
```

---

### Task 7: Router — edit, archive, unarchive, assign

**Files:**
- Modify: `apps/api/app/services/agent_students.py` (append), `apps/api/app/api/agent_students.py` (append)
- Create: `apps/api/tests/test_agn_004_student_actions.py`

**Interfaces:**
- Consumes: Task 6 functions; `AgentStudentRecordUpdate`, `AgentStudentAssign`, `RECORD_FIELDS`.
- Produces (service): `apply_update(row, user, changes: dict) -> list[str]` (changed field names), `set_archived(row, user, archived: bool) -> None`, `active_staff_member(db, user, member_id) -> AgentOrgMember` (422).
- Produces (router): `PATCH /{id}`, `POST /{id}/archive`, `POST /{id}/unarchive`, `POST /{id}/assign`.

- [ ] **Step 1: Write the failing tests**

```python
"""AGN-004 -- edit, archive, unarchive, assign (spec §5.4; AC03, AC04, AC09, AC11)."""

import pytest
from sqlalchemy import select

from app.models import AgentOrgMember, AgentStudent, AuditLog
from tests.agn001_helpers import client_for, mk_active_org, mk_user
from tests.agn004_helpers import RECORDS, mk_record, mk_staff


@pytest.fixture
async def agency(db_session):
    ctx = await mk_active_org(db_session, name="Actions Agency")
    other = await mk_active_org(db_session, name="Actions Other")
    s1, s2 = await mk_staff(db_session, ctx["org"], full_name="Act One"), await mk_staff(db_session, ctx["org"], full_name="Act Two")
    row = await mk_record(db_session, agent=ctx["master"], full_name="Edit Me", email="edit.me@example.local", assigned_member=s1["member"])
    return ctx | {"other": other, "s1": s1, "s2": s2, "row": row}


@pytest.mark.asyncio
async def test_assigned_staff_edit_changed_fields_only(db_session, agency):
    async with client_for(agency["s1"]["user"].email) as c:
        response = await c.patch(f"{RECORDS}/{agency['row'].id}", json={"preferred_country": "Ireland", "phone": None})
    assert response.status_code == 200 and response.json()["student"]["preferred_country"] == "Ireland"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_student.update", AuditLog.entity_id == str(agency["row"].id)))
    assert audit.metadata_json == {"fields": ["phone", "preferred_country"]}


@pytest.mark.asyncio
async def test_no_op_patch_writes_no_audit_row(db_session, agency):
    async with client_for(agency["master"].email) as c:
        response = await c.patch(f"{RECORDS}/{agency['row'].id}", json={"full_name": "Edit Me"})
    assert response.status_code == 200
    assert await db_session.scalar(select(AuditLog).where(AuditLog.action == "agent_student.update", AuditLog.entity_id == str(agency["row"].id))) is None


@pytest.mark.asyncio
async def test_other_staff_get_404_on_every_action(agency):
    sid = agency["row"].id
    async with client_for(agency["s2"]["user"].email) as c:
        codes = [
            (await c.patch(f"{RECORDS}/{sid}", json={"notes": "x"})).status_code,
            (await c.post(f"{RECORDS}/{sid}/archive")).status_code,
            (await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": None})).status_code,
        ]
    assert codes == [404, 404, 404]


@pytest.mark.asyncio
async def test_other_agency_master_gets_404_on_every_action(agency):
    sid = agency["row"].id
    async with client_for(agency["other"]["master"].email) as c:
        codes = [(await c.patch(f"{RECORDS}/{sid}", json={"notes": "x"})).status_code, (await c.post(f"{RECORDS}/{sid}/archive")).status_code]
    assert codes == [404, 404]


@pytest.mark.asyncio
async def test_assigned_staff_cannot_archive_or_assign(agency):
    sid = agency["row"].id
    async with client_for(agency["s1"]["user"].email) as c:
        archive = await c.post(f"{RECORDS}/{sid}/archive")
        assign = await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": None})
    assert archive.status_code == 403 and archive.json()["detail"] == "Only an agency Master can archive students"
    assert assign.status_code == 403


@pytest.mark.asyncio
async def test_master_archives_and_unarchives(db_session, agency):
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c:
        archived = await c.post(f"{RECORDS}/{sid}/archive")
        again = await c.post(f"{RECORDS}/{sid}/archive")
        edit = await c.patch(f"{RECORDS}/{sid}", json={"notes": "x"})
        listed = {i["id"] for i in (await c.get(RECORDS)).json()["items"]}
        detail = await c.get(f"{RECORDS}/{sid}")
        restored = await c.post(f"{RECORDS}/{sid}/unarchive")
        restored_again = await c.post(f"{RECORDS}/{sid}/unarchive")
    assert archived.status_code == 200 and archived.json()["student"]["status"] == "archived" and archived.json()["student"]["archived_by"]
    assert again.status_code == 409 and edit.status_code == 409 and edit.json()["detail"] == "Unarchive this student first"
    assert str(sid) not in listed and detail.status_code == 200
    assert restored.status_code == 200 and restored.json()["student"]["status"] == "active" and restored_again.status_code == 409
    actions = {a.action for a in (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(sid)))).all()}
    assert {"agent_student.archive", "agent_student.unarchive"} <= actions


@pytest.mark.asyncio
async def test_linked_students_cannot_be_edited_here(db_session, agency):
    student = await mk_user(db_session, role="overseas_student", full_name="Has Account")
    link = AgentStudent(agent_id=agency["master"].id, student_id=student.id, status="active")
    db_session.add(link)
    await db_session.commit()
    async with client_for(agency["master"].email) as c:
        response = await c.patch(f"{RECORDS}/{link.id}", json={"notes": "x"})
        archive = await c.post(f"{RECORDS}/{link.id}/archive")
    assert response.status_code == 409 and response.json()["detail"] == "Linked students are edited in their own account"
    assert archive.status_code == 200


@pytest.mark.asyncio
async def test_assign_targets_only_active_staff_of_the_same_agency(db_session, agency):
    sid = agency["row"].id
    foreign = await mk_staff(db_session, agency["other"]["org"], full_name="Foreign Staff")
    gone = await mk_staff(db_session, agency["org"], full_name="Gone Staff", active=False)
    async with client_for(agency["master"].email) as c:
        codes = [(await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": str(m)})).status_code for m in (foreign["member"].id, gone["member"].id, agency["member"].id)]
        moved = await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": str(agency["s2"]["member"].id)})
        same = await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": str(agency["s2"]["member"].id)})
        cleared = await c.post(f"{RECORDS}/{sid}/assign", json={"member_id": None})
    assert codes == [422, 422, 422]
    assert moved.json()["student"]["assigned_to"]["code"] == agency["s2"]["member"].code
    assert same.status_code == 200 and cleared.json()["student"]["assigned_to"] is None
    assigns = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "agent_student.assign", AuditLog.entity_id == str(sid)))).all()
    assert len(assigns) == 2  # the repeat assignment wrote nothing


@pytest.mark.asyncio
async def test_deactivated_staff_keep_their_students(db_session, agency):
    member = await db_session.get(AgentOrgMember, agency["s1"]["member"].id, populate_existing=True)
    member.status = "deactivated"
    await db_session.commit()
    async with client_for(agency["master"].email) as c:
        item = next(i for i in (await c.get(RECORDS)).json()["items"] if i["id"] == str(agency["row"].id))
    assert item["assigned_to"]["id"] == str(member.id) and item["assigned_to"]["status"] == "deactivated"


@pytest.mark.asyncio
async def test_edit_reruns_the_duplicate_check(db_session, agency):
    await mk_record(db_session, agent=agency["master"], full_name="Owner Of Email", email="taken@example.local")
    async with client_for(agency["master"].email) as c:
        warned = await c.patch(f"{RECORDS}/{agency['row'].id}", json={"email": "taken@example.local"})
        forced = await c.patch(f"{RECORDS}/{agency['row'].id}", json={"email": "taken@example.local", "confirm_duplicate": True})
    assert warned.status_code == 409 and forced.status_code == 200
```

- [ ] **Step 2: Run to verify failure** — `API_TEST tests/test_agn_004_student_actions.py`. Expected: FAIL — `405 Method Not Allowed` on PATCH / archive.

- [ ] **Step 3: Append service functions**

```python
def apply_update(row: AgentStudent, user: User, changes: dict) -> list[str]:
    """No commit. Returns the names of fields whose value actually changed (a no-op PATCH audits nothing)."""
    changed = []
    for field, value in changes.items():
        if getattr(row, field) != value:
            setattr(row, field, value)
            changed.append(field)
    if "phone" in changed:
        row.phone_digits = phone_digits(row.phone)
    if changed:
        row.updated_by_user_id = user.id
    return sorted(changed)


def set_archived(row: AgentStudent, user: User, archived: bool) -> None:
    row.status = "archived" if archived else "active"
    row.archived_at = datetime.now(UTC) if archived else None
    row.archived_by_user_id = user.id if archived else None
    row.updated_by_user_id = user.id


async def active_staff_member(db, user: User, member_id) -> AgentOrgMember:
    member = await db.scalar(
        select(AgentOrgMember).where(
            AgentOrgMember.id == member_id, AgentOrgMember.org_id == user.agent_membership.org_id, AgentOrgMember.role == STAFF, AgentOrgMember.status == "active"
        )
    )
    if member is None:
        raise HTTPException(422, "Choose an active Staff member of this agency")
    return member
```

(Add `from datetime import UTC, datetime` and `from app.services.agent_orgs import STAFF, org_member_ids`.)

- [ ] **Step 4: Append routes**

```python
def _require_master_action(user: User, message: str) -> None:
    if is_agent_staff(user):
        raise HTTPException(403, message)


async def _locked_row(db: AsyncSession, user: User, membership: AgentOrgMember, student_id: UUID):
    await lock_active_org(db, membership.org_id)
    return await load_scoped(db, user, student_id, lock=True)


@router.patch("/{student_id}")
async def update_student(student_id: UUID, payload: AgentStudentRecordUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    row = await _locked_row(db, user, membership, student_id)
    if row.student_id is not None:
        raise HTTPException(409, "Linked students are edited in their own account")
    if row.status == "archived":
        raise HTTPException(409, "Unarchive this student first")
    changes = payload.model_dump(exclude_unset=True, exclude={"confirm_duplicate"})
    if {"email", "phone"} & changes.keys():
        email = changes.get("email", row.email)
        matches, hidden = await find_duplicates(db, user, email=email, digits=phone_digits(changes.get("phone", row.phone)), exclude_id=row.id)
        if (matches or hidden) and not payload.confirm_duplicate:
            _log("agent_student_duplicate_warned", membership, user, row.id, match_count=len(matches) + hidden)
            raise duplicate_conflict(matches, hidden)
    else:
        matches, hidden = [], 0
    changed = apply_update(row, user, changes)
    if changed:
        _audit(db, user, "update", row.id, {"fields": changed})
        if matches or hidden:
            _audit(db, user, "duplicate_override", row.id, {"match_count": len(matches) + hidden})
    await db.commit()
    if changed:
        _log("agent_student_updated", membership, user, row.id, fields=changed)
    return {"student": await record_detail(db, row)}


async def _archive(student_id: UUID, user: User, db: AsyncSession, archived: bool) -> dict:
    membership = _gate(user)
    row = await _locked_row(db, user, membership, student_id)  # scope first: another staff member's student stays 404
    _require_master_action(user, "Only an agency Master can archive students")
    if (row.status == "archived") == archived:
        raise HTTPException(409, "Already archived" if archived else "Already active")
    set_archived(row, user, archived)
    _audit(db, user, "archive" if archived else "unarchive", row.id)
    await db.commit()
    _log("agent_student_archived" if archived else "agent_student_unarchived", membership, user, row.id)
    return {"student": await record_detail(db, row)}


@router.post("/{student_id}/archive")
async def archive_student(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _archive(student_id, user, db, True)


@router.post("/{student_id}/unarchive")
async def unarchive_student(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _archive(student_id, user, db, False)


@router.post("/{student_id}/assign")
async def assign_student(student_id: UUID, payload: AgentStudentAssign, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    row = await _locked_row(db, user, membership, student_id)
    _require_master_action(user, "Only an agency Master can assign students")
    if row.status == "archived":
        raise HTTPException(409, "Unarchive this student first")
    target = await active_staff_member(db, user, payload.member_id) if payload.member_id else None
    new_id = target.id if target else None
    if row.assigned_member_id != new_id:
        previous = row.assigned_member_id
        row.assigned_member_id, row.updated_by_user_id = new_id, user.id
        _audit(db, user, "assign", row.id, {"from": str(previous) if previous else None, "to": str(new_id) if new_id else None})
        await db.commit()
        _log("agent_student_assigned", membership, user, row.id, member_id=str(new_id) if new_id else None)
    return {"student": await record_detail(db, row)}
```

(Extend imports: `AgentStudentAssign, AgentStudentRecordUpdate` from schemas; `active_staff_member, apply_update, set_archived` from the service.)

- [ ] **Step 5: Run to verify pass** — `API_TEST tests/test_agn_004_student_actions.py tests/test_agn_004_students.py`. Expected: PASS.

- [ ] **Step 6: Refactor** — `_archive` and `assign_student` share `_gate` + `_locked_row` + master check; keep them as is unless a third caller appears. Rerun Step 5.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/services/agent_students.py apps/api/app/api/agent_students.py apps/api/tests/test_agn_004_student_actions.py
git commit -m "feat(agn-004): edit, archive, unarchive and assign agency students"
```

---

### Task 8: Backend checkpoint (targeted regression, no completion claim)

**Files:** none changed unless a failure is found.

- [ ] **Step 1: Run every AGN-004 file plus the agent-adjacent suites**

Run: `API_TEST tests/test_agn_004_schema.py tests/test_agn_004_migration.py tests/test_agn_004_schemas.py tests/test_agn_004_staff_guards.py tests/test_agn_004_staff_scope.py tests/test_agn_004_students.py tests/test_agn_004_student_actions.py tests/test_agt_001_registration_approval.py tests/test_agt_002_referrals.py tests/test_agt_003_commission_accrual.py tests/test_agt_004_commission_payout.py tests/test_agn_001_org_admin.py tests/test_agn_001_prefix.py tests/test_agn_001_registration_and_gate.py tests/test_agn_001_schema.py tests/test_agn_001_team.py tests/test_agn_001_tenancy.py tests/test_enh_031_lookups_students.py tests/test_sec_001_audit_trail.py tests/test_rpt_002_overseas_reporting.py tests/test_role_assignments.py tests/test_enh_027_migration.py`
Expected: all PASS. Any failure: use superpowers:systematic-debugging; never edit an existing test to pass (except the Task 1 recorded edit).

- [ ] **Step 2: Full backend suite** (the blast radius touches the shared gate and a migration — spec §10; this is the cross-cutting exception to the 3–4-feature cadence)

Run: `API_TEST tests`
Expected: no new failures beyond the recorded provider-credential baseline (11 Razorpay `test_pay_001_stu_010`, 3 Zoho). Record the exact counts for the RTM.

---

### Task 9: Web — types, navigation, PortalPage (G2 frontend, identical to AGN-002)

**Files:**
- Modify: `apps/web/lib/types.ts`, `apps/web/lib/navigation.ts`, `apps/web/components/PortalPage.tsx`
- Create: `apps/web/tests/lib/navigation.agent.test.ts`

**Interfaces:**
- Produces: `User.agent_member_role?: "master" | "staff" | null`; `agentNavFor(nav: NavItem[], memberRole?: string | null): NavItem[]`.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from "vitest";
import { agentNavFor, PORTAL_NAV } from "@/lib/navigation";

describe("agentNavFor", () => {
  const nav = PORTAL_NAV["overseas/agent"];
  it("hides Team and Commissions from staff", () => {
    expect(agentNavFor(nav, "staff").map((i) => i.href)).toEqual([
      "/overseas/agent/dashboard", "/overseas/agent/students", "/overseas/agent/applications", "/overseas/agent/documents", "/overseas/agent/reports",
    ]);
  });
  it("leaves a Master's nav unchanged", () => {
    expect(agentNavFor(nav, "master")).toEqual(nav);
    expect(agentNavFor(nav, null)).toEqual(nav);
  });
});
```

- [ ] **Step 2: Run** — `WEB_TEST tests/lib/navigation.agent.test.ts`. Expected: FAIL — `agentNavFor is not a function`.

- [ ] **Step 3: Implement (AGN-002's lines verbatim)** — `lib/navigation.ts` after `PORTAL_NAV`:

```ts
// AGN-002 (DEC-SCOPE-040 S1): an agency's staff work on students and applications; Team and Commissions stay Master-only (the
// server refuses them regardless -- this only keeps dead links out of the sidebar).
const STAFF_HIDDEN = new Set(["/overseas/agent/team", "/overseas/agent/commissions"]);
export function agentNavFor(nav: NavItem[], memberRole?: string | null): NavItem[] {
  return memberRole === "staff" ? nav.filter((item) => !STAFF_HIDDEN.has(item.href)) : nav;
}
```

`lib/types.ts`: `User` gains `agent_member_role?:"master"|"staff"|null`.
`components/PortalPage.tsx`: AGN-002's version (import `agentNavFor`; `const staff=key==="overseas/agent"&&user.agent_member_role==="staff";` then `nav={staff?agentNavFor(nav,"staff"):nav}` and `roleLabel={staff?"Agency Staff":labels[key]||role}`).

- [ ] **Step 4: Run** — `WEB_TEST tests/lib/navigation.agent.test.ts`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/types.ts apps/web/lib/navigation.ts apps/web/components/PortalPage.tsx apps/web/tests/lib/navigation.agent.test.ts
git commit -m "feat(agn-004): staff sidebar hides Team and Commissions (identical to AGN-002)"
```

---

### Task 10: Web — `lib/agentStudents.ts` and `AgentStudentForm`

**Files:**
- Create: `apps/web/lib/agentStudents.ts`, `apps/web/components/AgentStudentForm.tsx`
- Create: `apps/web/tests/lib/agentStudents.test.ts`, `apps/web/tests/components/AgentStudentForm.test.tsx`

**Interfaces:**
- Produces (`lib/agentStudents.ts`):
  - `type AgentStudentItem = {id:string; has_login:boolean; full_name:string; email:string|null; phone:string|null; preferred_country:string|null; preferred_intake:string|null; status:"active"|"archived"; assigned_to:{id:string; code:string; full_name:string; status:string}|null; created_at:string}`
  - `type AgentStudentDetail = AgentStudentItem & {date_of_birth:string|null; highest_qualification:string|null; institution:string|null; graduation_year:number|null; preferred_course:string|null; notes:string|null; created_by:string|null; archived_at:string|null; archived_by:string|null; updated_at:string}`
  - `type DuplicateDetail = {message:string; matches:{id:string; full_name:string; has_login:boolean; status:string; matched_on:string[]}[]; hidden_matches:number}`
  - `const RECORDS_URL = "/api/v1/workflows/overseas/agent/crm/students"`, `FIELD_KEYS`, `type FormValues = Record<(typeof FIELD_KEYS)[number], string>`
  - `emptyValues(): FormValues`, `valuesFrom(d: AgentStudentDetail): FormValues`, `buildPayload(values: FormValues, original?: FormValues): Record<string, unknown>`, `validate(values: FormValues): Partial<Record<keyof FormValues, string>>`, `duplicateDetail(detail: unknown): DuplicateDetail | null`
- Produces (component): `AgentStudentForm({ mode: "create" | "edit", student?: AgentStudentDetail, onSaved: (s: AgentStudentDetail) => void, onCancel: () => void })`.

- [ ] **Step 1: Write the failing lib test**

```ts
import { describe, expect, it } from "vitest";
import { buildPayload, duplicateDetail, emptyValues, validate } from "@/lib/agentStudents";

describe("agentStudents lib", () => {
  it("builds a create payload without blank fields", () => {
    const v = { ...emptyValues(), full_name: " Asha ", email: "A@X.COM", graduation_year: "2024" };
    expect(buildPayload(v)).toEqual({ full_name: "Asha", email: "a@x.com", graduation_year: 2024 });
  });
  it("sends only changed fields on edit, null for a cleared field", () => {
    const original = { ...emptyValues(), full_name: "Asha", phone: "123" };
    expect(buildPayload({ ...original, phone: "" }, original)).toEqual({ phone: null });
    expect(buildPayload(original, original)).toEqual({});
  });
  it("validates like the server", () => {
    const errors = validate({ ...emptyValues(), full_name: " ", email: "bad", graduation_year: "1900", notes: "x".repeat(2001) });
    expect(Object.keys(errors).sort()).toEqual(["email", "full_name", "graduation_year", "notes"]);
  });
  it("reads only a structured duplicate detail", () => {
    expect(duplicateDetail({ code: "possible_duplicate", message: "m", matches: [], hidden_matches: 2 })?.hidden_matches).toBe(2);
    expect(duplicateDetail("Student not found")).toBeNull();
    expect(duplicateDetail({ code: "other" })).toBeNull();
  });
});
```

- [ ] **Step 2: Run** — `WEB_TEST tests/lib/agentStudents.test.ts`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement `lib/agentStudents.ts`**

```ts
// AGN-004 (DEC-SCOPE-041): the shape and helpers of an agency student (with or without a login), shared by the list, the detail
// panel and the form so they read one definition. Validation mirrors the server's schemas; the server remains the authority.

export const RECORDS_URL = "/api/v1/workflows/overseas/agent/crm/students";

export type Assignee = { id: string; code: string; full_name: string; status: string };
export type AgentStudentItem = {
  id: string; has_login: boolean; full_name: string; email: string | null; phone: string | null;
  preferred_country: string | null; preferred_intake: string | null; status: "active" | "archived";
  assigned_to: Assignee | null; created_at: string;
};
export type AgentStudentDetail = AgentStudentItem & {
  date_of_birth: string | null; highest_qualification: string | null; institution: string | null; graduation_year: number | null;
  preferred_course: string | null; notes: string | null; created_by: string | null; archived_at: string | null; archived_by: string | null; updated_at: string;
};
export type DuplicateMatch = { id: string; full_name: string; has_login: boolean; status: string; matched_on: string[] };
export type DuplicateDetail = { message: string; matches: DuplicateMatch[]; hidden_matches: number };

export const FIELD_KEYS = [
  "full_name", "date_of_birth", "email", "phone", "highest_qualification", "institution", "graduation_year",
  "preferred_country", "preferred_course", "preferred_intake", "notes",
] as const;
export type FieldKey = (typeof FIELD_KEYS)[number];
export type FormValues = Record<FieldKey, string>;

export const NOTES_MAX = 2000;
const LIMITS: Partial<Record<FieldKey, number>> = { full_name: 160, email: 320, phone: 40, highest_qualification: 200, institution: 200, preferred_country: 120, preferred_course: 200, preferred_intake: 40, notes: NOTES_MAX };
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function emptyValues(): FormValues {
  return Object.fromEntries(FIELD_KEYS.map((k) => [k, ""])) as FormValues;
}

export function valuesFrom(d: AgentStudentDetail): FormValues {
  return Object.fromEntries(FIELD_KEYS.map((k) => [k, d[k] == null ? "" : String(d[k])])) as FormValues;
}

function normalise(key: FieldKey, raw: string): unknown {
  const value = raw.trim();
  if (!value) return null;
  if (key === "email") return value.toLowerCase();
  if (key === "graduation_year") return Number(value);
  return value;
}

export function buildPayload(values: FormValues, original?: FormValues): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of FIELD_KEYS) {
    const next = normalise(key, values[key]);
    if (original) {
      if (next !== normalise(key, original[key])) out[key] = next;
    } else if (next !== null) {
      out[key] = next;
    }
  }
  return out;
}

export function validate(values: FormValues): Partial<Record<FieldKey, string>> {
  const errors: Partial<Record<FieldKey, string>> = {};
  if (!values.full_name.trim()) errors.full_name = "Full name is required";
  for (const key of FIELD_KEYS) {
    const max = LIMITS[key];
    if (max && values[key].trim().length > max) errors[key] = `Must be ${max} characters or fewer`;
  }
  if (values.email.trim() && !EMAIL.test(values.email.trim())) errors.email = "Enter a valid email address";
  if (values.date_of_birth) {
    const today = new Date().toISOString().slice(0, 10);
    if (values.date_of_birth > today || values.date_of_birth < "1900-01-01") errors.date_of_birth = "Date of birth must be between 1900 and today";
  }
  if (values.graduation_year.trim()) {
    const year = Number(values.graduation_year);
    const max = new Date().getFullYear() + 6;
    if (!Number.isInteger(year) || year < 1950 || year > max) errors.graduation_year = `Enter a year from 1950 to ${max}`;
  }
  return errors;
}

export function duplicateDetail(detail: unknown): DuplicateDetail | null {
  const d = detail as Partial<DuplicateDetail> & { code?: string } | null;
  if (!d || typeof d !== "object" || d.code !== "possible_duplicate" || !Array.isArray(d.matches)) return null;
  return { message: String(d.message ?? ""), matches: d.matches, hidden_matches: Number(d.hidden_matches ?? 0) };
}
```

- [ ] **Step 4: Run** — `WEB_TEST tests/lib/agentStudents.test.ts`. Expected: PASS. Commit:

```bash
git add apps/web/lib/agentStudents.ts apps/web/tests/lib/agentStudents.test.ts
git commit -m "feat(agn-004): agent student payload, validation and duplicate helpers"
```

- [ ] **Step 5: Write the failing form test**

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import AgentStudentForm from "@/components/AgentStudentForm";

const saved = { id: "s1", has_login: false, full_name: "Asha", email: null, phone: null, preferred_country: null, preferred_intake: null, status: "active", assigned_to: null, created_at: "", date_of_birth: null, highest_qualification: null, institution: null, graduation_year: null, preferred_course: null, notes: null, created_by: "M", archived_at: null, archived_by: null, updated_at: "" };
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

afterEach(() => vi.restoreAllMocks());

describe("AgentStudentForm", () => {
  it("moves focus to the first invalid field and does not submit", async () => {
    const fetchSpy = vi.spyOn(global, "fetch");
    render(<AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/email/i), "bad");
    await userEvent.click(screen.getByRole("button", { name: /save student/i }));
    expect(screen.getByLabelText(/full name/i)).toHaveFocus();
    expect(screen.getByLabelText(/full name/i)).toHaveAttribute("aria-invalid", "true");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("shows the duplicate warning and saves anyway with confirmation", async () => {
    const fetchSpy = vi.spyOn(global, "fetch")
      .mockImplementationOnce(() => json(409, { detail: { code: "possible_duplicate", message: "A student with this email or phone already exists in your agency", matches: [{ id: "x", full_name: "Asha R", has_login: false, status: "archived", matched_on: ["email"] }], hidden_matches: 1 } }))
      .mockImplementationOnce(() => json(201, { student: saved }));
    const onSaved = vi.fn();
    render(<AgentStudentForm mode="create" onSaved={onSaved} onCancel={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/full name/i), "Asha");
    await userEvent.type(screen.getByLabelText(/email/i), "a@x.com");
    await userEvent.click(screen.getByRole("button", { name: /save student/i }));
    expect(await screen.findByText(/Asha R/)).toBeInTheDocument();
    expect(screen.getByText(/1 more you can't view/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /save anyway/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    expect(JSON.parse(String(fetchSpy.mock.calls[1][1]?.body))).toMatchObject({ confirm_duplicate: true, email: "a@x.com" });
  });

  it("blocks a double submit", async () => {
    let resolve: (r: Response) => void = () => {};
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation(() => new Promise((r) => { resolve = r; }));
    render(<AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/full name/i), "Asha");
    const save = screen.getByRole("button", { name: /save student/i });
    fireEvent.click(save);
    fireEvent.click(save);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    resolve(new Response(JSON.stringify({ student: saved }), { status: 201 }));
  });

  it("sends only changed fields when editing", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation(() => json(200, { student: saved }));
    render(<AgentStudentForm mode="edit" student={{ ...saved, phone: "123" }} onSaved={vi.fn()} onCancel={vi.fn()} />);
    await userEvent.clear(screen.getByLabelText(/phone/i));
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    expect(fetchSpy.mock.calls[0][1]?.method).toBe("PATCH");
    expect(JSON.parse(String(fetchSpy.mock.calls[0][1]?.body))).toEqual({ phone: null });
  });

  it("asks before leaving with unsaved changes", async () => {
    render(<AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/full name/i), "A");
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });
});
```

- [ ] **Step 6: Run** — `WEB_TEST tests/components/AgentStudentForm.test.tsx`. Expected: FAIL (component missing).

- [ ] **Step 7: Implement `components/AgentStudentForm.tsx`**

```tsx
"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";
import {
  AgentStudentDetail, buildPayload, DuplicateDetail, duplicateDetail, emptyValues, FieldKey, FormValues, NOTES_MAX, RECORDS_URL, validate, valuesFrom,
} from "@/lib/agentStudents";

// AGN-004: create or edit an agency student who never logs in (EVID-015 §5 Step 1). Only Full name is required. On a possible
// duplicate the server answers 409 and the user decides; "Save anyway" resends the same entry with confirm_duplicate.
type Field = { key: FieldKey; label: string; type?: string; inputMode?: "numeric"; autoComplete?: string };
const GROUPS: { legend: string; fields: Field[] }[] = [
  { legend: "Personal", fields: [{ key: "full_name", label: "Full name (required)", autoComplete: "name" }, { key: "date_of_birth", label: "Date of birth", type: "date" }] },
  { legend: "Contact", fields: [{ key: "email", label: "Email", type: "email", autoComplete: "email" }, { key: "phone", label: "Phone", type: "tel", autoComplete: "tel" }] },
  { legend: "Academic", fields: [{ key: "highest_qualification", label: "Highest qualification" }, { key: "institution", label: "Institution" }, { key: "graduation_year", label: "Graduation year", inputMode: "numeric" }] },
  { legend: "Preferences", fields: [{ key: "preferred_country", label: "Preferred country" }, { key: "preferred_course", label: "Preferred course" }, { key: "preferred_intake", label: "Preferred intake (e.g. Sep 2027)" }] },
];

export default function AgentStudentForm({ mode, student, onSaved, onCancel }: { mode: "create" | "edit"; student?: AgentStudentDetail; onSaved: (s: AgentStudentDetail) => void; onCancel: () => void }) {
  const original = useRef<FormValues>(student ? valuesFrom(student) : emptyValues());
  const [values, setValues] = useState<FormValues>(original.current);
  const [errors, setErrors] = useState<Partial<Record<FieldKey, string>>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<DuplicateDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const idPrefix = mode === "create" ? "agent-student-new" : `agent-student-${student?.id}`;
  const dirty = Object.keys(buildPayload(values, original.current)).length > 0;

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function set(key: FieldKey, value: string) {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => ({ ...e, [key]: undefined }));
    setDuplicate(null);
  }

  async function save(confirmDuplicate: boolean) {
    if (inFlight.current) return;
    const found = validate(values);
    setErrors(found);
    const firstInvalid = GROUPS.flatMap((g) => g.fields).find((f) => found[f.key]);
    if (firstInvalid) { document.getElementById(`${idPrefix}-${firstInvalid.key}`)?.focus(); return; }
    const payload = mode === "create" ? buildPayload(values) : buildPayload(values, original.current);
    if (mode === "edit" && Object.keys(payload).length === 0) { onCancel(); return; }
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    try {
      const response = await fetch(mode === "create" ? RECORDS_URL : `${RECORDS_URL}/${student!.id}`, {
        method: mode === "create" ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(confirmDuplicate ? { ...payload, confirm_duplicate: true } : payload),
      });
      const body = await response.json().catch(() => ({}));
      if (response.ok && body?.student?.id) { original.current = values; onSaved(body.student); return; }
      const dup = response.status === 409 ? duplicateDetail(body.detail) : null;
      if (dup) setDuplicate(dup);
      else setFailure(detailMessage(body.detail, "Unable to save this student."));
    } catch {
      setFailure(NOT_COMPLETED);
    } finally {
      inFlight.current = false;
      setBusy(false);
      refocus(`${idPrefix}-save`);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void save(false); }

  return (
    <form className="form" onSubmit={submit} aria-busy={busy} noValidate aria-labelledby={`${idPrefix}-title`}>
      <h4 id={`${idPrefix}-title`}>{mode === "create" ? "Add student" : `Edit ${student?.full_name}`}</h4>
      {GROUPS.map((group) => (
        <fieldset key={group.legend}>
          <legend>{group.legend}</legend>
          {group.fields.map((f) => {
            const id = `${idPrefix}-${f.key}`;
            return (
              <div className="field" key={f.key}>
                <label htmlFor={id}>{f.label}</label>
                <input id={id} type={f.type ?? "text"} inputMode={f.inputMode} autoComplete={f.autoComplete} value={values[f.key]}
                  max={f.type === "date" ? new Date().toISOString().slice(0, 10) : undefined}
                  aria-invalid={errors[f.key] ? true : undefined} aria-describedby={errors[f.key] ? `${id}-error` : undefined}
                  onChange={(e) => set(f.key, e.target.value)} />
                {errors[f.key] && <p className="form-error" id={`${id}-error`}>{errors[f.key]}</p>}
              </div>
            );
          })}
        </fieldset>
      ))}
      <div className="field">
        <label htmlFor={`${idPrefix}-notes`}>Notes</label>
        <textarea id={`${idPrefix}-notes`} rows={4} value={values.notes} maxLength={NOTES_MAX + 1}
          aria-invalid={errors.notes ? true : undefined} aria-describedby={`${idPrefix}-notes-count${errors.notes ? ` ${idPrefix}-notes-error` : ""}`}
          onChange={(e) => set("notes", e.target.value)} />
        <p className="muted" id={`${idPrefix}-notes-count`} style={{ fontSize: 12 }}>{values.notes.length} / {NOTES_MAX}</p>
        {errors.notes && <p className="form-error" id={`${idPrefix}-notes-error`}>{errors.notes}</p>}
      </div>
      {duplicate && (
        <div role="alert" className="form-error">
          <p>{duplicate.message}</p>
          <ul>{duplicate.matches.map((m) => <li key={m.id}>{m.full_name} — {m.has_login ? "has a login" : "no login"}, {m.status}, same {m.matched_on.join(" and ")}</li>)}</ul>
          {duplicate.hidden_matches > 0 && <p>{duplicate.hidden_matches} more you can't view.</p>}
          <button type="button" className="btn small" onClick={() => void save(true)} disabled={busy}>Save anyway</button>{" "}
          <button type="button" className="btn secondary small" onClick={() => setDuplicate(null)}>Go back</button>
        </div>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      <button id={`${idPrefix}-save`} type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : mode === "create" ? "Save student" : "Save changes"}</button>{" "}
      <button type="button" className="btn secondary small" onClick={onCancel} disabled={busy}>Cancel</button>
    </form>
  );
}
```

- [ ] **Step 8: Run** — `WEB_TEST tests/components/AgentStudentForm.test.tsx tests/lib/agentStudents.test.ts`. Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add apps/web/components/AgentStudentForm.tsx apps/web/tests/components/AgentStudentForm.test.tsx
git commit -m "feat(agn-004): add/edit student form with duplicate confirmation"
```

---

### Task 11: Web — `AgentStudentsPanel`, wiring and responsive CSS

**Files:**
- Create: `apps/web/components/AgentStudentsPanel.tsx`, `apps/web/tests/components/AgentStudentsPanel.test.tsx`
- Modify: `apps/web/components/WorkflowPanel.tsx`, `apps/web/app/globals.css`

**Interfaces:**
- Consumes: `lib/agentStudents.ts`, `AgentStudentForm`, `lib/apiErrors` (`detailMessage`, `isPage`, `Page`).
- Produces: `AgentStudentsPanel({ memberRole }: { memberRole: "master" | "staff" | null | undefined })`.

- [ ] **Step 1: Write the failing tests**

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import AgentStudentsPanel from "@/components/AgentStudentsPanel";

const item = (over: Record<string, unknown> = {}) => ({ id: "s1", has_login: false, full_name: "Asha Rao", email: "a@x.com", phone: null, preferred_country: "Canada", preferred_intake: "Sep 2027", status: "active", assigned_to: null, created_at: "", ...over });
const page = (items: unknown[], total = items.length) => ({ items, total, limit: 20, offset: 0 });
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

afterEach(() => vi.restoreAllMocks());

describe("AgentStudentsPanel", () => {
  it("shows a loading state, then rows", async () => {
    vi.spyOn(global, "fetch").mockImplementation(() => json(200, page([item()])));
    render(<AgentStudentsPanel memberRole="master" />);
    expect(screen.getByText(/loading students/i)).toBeInTheDocument();
    expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
  });

  it("shows the empty state with an Add student action", async () => {
    vi.spyOn(global, "fetch").mockImplementation(() => json(200, page([])));
    render(<AgentStudentsPanel memberRole="staff" />);
    expect(await screen.findByText(/no students yet/i)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /add student/i }).length).toBeGreaterThan(0);
  });

  it("shows an error with Retry", async () => {
    const spy = vi.spyOn(global, "fetch").mockImplementationOnce(() => json(500, { detail: "boom" })).mockImplementation(() => json(200, page([item()])));
    render(<AgentStudentsPanel memberRole="master" />);
    await userEvent.click(await screen.findByRole("button", { name: /retry/i }));
    expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("hides Master-only actions from staff", async () => {
    vi.spyOn(global, "fetch").mockImplementation(() => json(200, page([item()])));
    render(<AgentStudentsPanel memberRole="staff" />);
    await screen.findByText("Asha Rao");
    expect(screen.queryByRole("button", { name: /archive asha rao/i })).toBeNull();
    expect(screen.queryByLabelText(/assigned to/i)).toBeNull();
  });

  it("archives inline with a confirmation and returns focus", async () => {
    vi.spyOn(global, "fetch").mockImplementation((url, init) =>
      init?.method === "POST" ? json(200, { student: { ...item({ status: "archived" }), archived_by: "M" } }) : json(200, page([item()])));
    render(<AgentStudentsPanel memberRole="master" />);
    await userEvent.click(await screen.findByRole("button", { name: /archive asha rao/i }));
    await userEvent.click(screen.getByRole("button", { name: /confirm archive/i }));
    expect(await screen.findByText(/asha rao archived/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: /confirm archive/i })).toBeNull());
  });

  it("keeps the newest search when an older response arrives late", async () => {
    let releaseOld: () => void = () => {};
    vi.spyOn(global, "fetch").mockImplementation((url) => {
      const u = String(url);
      if (u.includes("q=old")) return new Promise((r) => { releaseOld = () => r(new Response(JSON.stringify(page([item({ id: "o", full_name: "Old Result" })])), { status: 200 })); });
      if (u.includes("q=new")) return json(200, page([item({ id: "n", full_name: "New Result" })]));
      return json(200, page([]));
    });
    render(<AgentStudentsPanel memberRole="master" />);
    const box = await screen.findByLabelText(/search students/i);
    await userEvent.type(box, "old");
    await new Promise((r) => setTimeout(r, 350));
    await userEvent.clear(box);
    await userEvent.type(box, "new");
    expect(await screen.findByText("New Result")).toBeInTheDocument();
    releaseOld();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText("Old Result")).toBeNull();
  });

  it("renders markup in a name as text", async () => {
    vi.spyOn(global, "fetch").mockImplementation(() => json(200, page([item({ full_name: "<img src=x onerror=alert(1)>" })])));
    const { container } = render(<AgentStudentsPanel memberRole="master" />);
    expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows has-login and assignment as text, not colour alone", async () => {
    vi.spyOn(global, "fetch").mockImplementation(() => json(200, page([item({ has_login: true, assigned_to: { id: "m", code: "ABC-S001", full_name: "Rahul", status: "deactivated" } })])));
    render(<AgentStudentsPanel memberRole="master" />);
    const row = (await screen.findByText("Asha Rao")).closest("tr")!;
    expect(within(row).getByText(/has login/i)).toBeInTheDocument();
    expect(within(row).getByText(/ABC-S001 · Rahul \(deactivated\)/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** — `WEB_TEST tests/components/AgentStudentsPanel.test.tsx`. Expected: FAIL (component missing).

- [ ] **Step 3: Implement `components/AgentStudentsPanel.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import AgentStudentForm from "./AgentStudentForm";
import { detailMessage, isPage, Page } from "@/lib/apiErrors";
import { AgentStudentDetail, AgentStudentItem, RECORDS_URL } from "@/lib/agentStudents";

// AGN-004 (DEC-SCOPE-041): the agency's students -- with or without a login -- on the Students page. Masters see the agency and
// may archive and assign; staff see their assigned students (the server enforces both; the controls here only follow it).
// Paging follows AgentApprovalPanel (20 per page, page in the URL); archive/assign use the inline confirmation pattern.
const PAGE_SIZE = 20;
type Confirm = { id: string; kind: "archive" | "unarchive" } | null;

function assignedText(a: AgentStudentItem["assigned_to"]): string {
  return a ? `${a.code} · ${a.full_name}${a.status !== "active" ? " (deactivated)" : ""}` : "Unassigned";
}

export default function AgentStudentsPanel({ memberRole }: { memberRole: "master" | "staff" | null | undefined }) {
  const isMaster = memberRole !== "staff";
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [assigned, setAssigned] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Page<AgentStudentItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ id: string; text: string } | null>(null);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [detail, setDetail] = useState<AgentStudentDetail | null>(null);
  const [detailState, setDetailState] = useState<"idle" | "loading" | "gone" | "error">("idle");
  const [editing, setEditing] = useState(false);
  const returnFocusTo = useRef<string | null>(null);
  const request = useRef<AbortController | null>(null);

  useEffect(() => {
    const handle = setTimeout(() => { setQuery(draft.trim().slice(0, 100)); setOffset(0); }, 300);
    return () => clearTimeout(handle);
  }, [draft]);

  const load = useCallback(() => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setLoadError(null);
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (query) params.set("q", query);
    if (showArchived) params.set("include_archived", "true");
    if (isMaster && assigned) params.set("assigned", assigned);
    fetch(`${RECORDS_URL}?${params}`, { signal: controller.signal })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (controller.signal.aborted) return;
        if (!res.ok || !isPage<AgentStudentItem>(body)) { setLoadError(detailMessage(body?.detail, "Unable to load students.")); return; }
        setData(body);
      })
      .catch((e) => { if (!controller.signal.aborted && e?.name !== "AbortError") setLoadError("Unable to load students."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
  }, [offset, query, showArchived, assigned, isMaster]);

  useEffect(load, [load]);

  useEffect(() => {
    if (confirm === null && returnFocusTo.current) { document.getElementById(returnFocusTo.current)?.focus(); returnFocusTo.current = null; }
  }, [confirm]);

  async function openDetail(id: string) {
    setDetailState("loading");
    setEditing(false);
    try {
      const res = await fetch(`${RECORDS_URL}/${id}`);
      const body = await res.json().catch(() => ({}));
      if (res.status === 404) { setDetail(null); setDetailState("gone"); return; }
      if (!res.ok || !body?.student) { setDetailState("error"); return; }
      setDetail(body.student);
      setDetailState("idle");
      requestAnimationFrame(() => document.getElementById("agent-student-detail-heading")?.focus());
    } catch { setDetailState("error"); }
  }

  function closeDetail() {
    const id = detail?.id;
    setDetail(null);
    setDetailState("idle");
    setEditing(false);
    if (id) requestAnimationFrame(() => document.getElementById(`agent-student-view-${id}`)?.focus());
  }

  function applyUpdate(s: AgentStudentDetail) {
    setDetail((d) => (d && d.id === s.id ? s : d));
    const leavesFilter = s.status === "archived" && !showArchived;
    if (leavesFilter) { load(); return; }
    setData((d) => (d ? { ...d, items: d.items.some((i) => i.id === s.id) ? d.items.map((i) => (i.id === s.id ? s : i)) : [s, ...d.items] } : d));
  }

  async function act(item: AgentStudentItem, path: "archive" | "unarchive") {
    setBusyId(item.id);
    setRowError(null);
    try {
      const res = await fetch(`${RECORDS_URL}/${item.id}/${path}`, { method: "POST" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !body?.student) { setRowError({ id: item.id, text: detailMessage(body.detail, "Unable to complete this action.") }); return; }
      setConfirm(null);
      setNotice(`${item.full_name} ${path === "archive" ? "archived" : "restored"}.`);
      applyUpdate(body.student);
    } catch {
      setRowError({ id: item.id, text: "Network error. Check your connection and try again." });
    } finally { setBusyId(null); }
  }

  const empty = data && data.items.length === 0;
  const filtered = Boolean(query || showArchived || assigned);

  return (
    <div className="action-card agent-students">
      <h3>Students</h3>
      <div className={notice ? "form-message" : undefined} role="status" aria-live="polite">{notice}</div>
      <div role="search" style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 8, marginTop: 8 }}>
        <div className="field" style={{ flex: "1 1 220px", margin: 0 }}>
          <label htmlFor="agent-students-search">Search students</label>
          <input id="agent-students-search" type="search" value={draft} maxLength={100} placeholder="Name, email or phone" onChange={(e) => setDraft(e.target.value)} />
        </div>
        <label style={{ display: "flex", gap: 6, alignItems: "center", minHeight: 44 }}>
          <input type="checkbox" checked={showArchived} onChange={(e) => { setShowArchived(e.target.checked); setOffset(0); }} /> Show archived
        </label>
        {isMaster && (
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="agent-students-assigned">Assigned to</label>
            <select id="agent-students-assigned" value={assigned} onChange={(e) => { setAssigned(e.target.value); setOffset(0); }}>
              <option value="">Anyone</option>
              <option value="none">Unassigned</option>
            </select>
          </div>
        )}
        <button type="button" className="btn small" onClick={() => { setAdding(true); setDetail(null); }}>Add student</button>
      </div>

      {adding && (
        <AgentStudentForm mode="create" onCancel={() => setAdding(false)} onSaved={(s) => { setAdding(false); setNotice(`${s.full_name} added.`); applyUpdate(s); }} />
      )}

      <section aria-labelledby="agent-students-list-heading" aria-busy={loading} style={{ marginTop: 16, opacity: loading && data ? 0.6 : 1 }}>
        <h4 id="agent-students-list-heading" className="sr-only">Student list</h4>
        {loadError ? (
          <>
            <p className="form-error" role="alert">{loadError}</p>
            <button type="button" className="btn secondary small" onClick={load}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted">Loading students…</p>
        ) : empty ? (
          filtered ? (
            <p className="muted">No students match. <button type="button" className="btn secondary small" onClick={() => { setDraft(""); setQuery(""); setShowArchived(false); setAssigned(""); }}>Clear filters</button></p>
          ) : (
            <p className="muted">No students yet. <button type="button" className="btn secondary small" onClick={() => setAdding(true)}>Add student</button></p>
          )
        ) : (
          <>
            <table className="table stack-cards">
              <thead><tr><th scope="col">Student</th><th scope="col">Contact</th><th scope="col">Preference</th><th scope="col">Login</th><th scope="col">Assigned to</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {data.items.map((s) => (
                  <tr key={s.id}>
                    <td data-label="Student">{s.full_name}</td>
                    <td data-label="Contact">{[s.email, s.phone].filter(Boolean).join(" · ") || "—"}</td>
                    <td data-label="Preference">{[s.preferred_country, s.preferred_intake].filter(Boolean).join(", ") || "—"}</td>
                    <td data-label="Login"><span className="badge">{s.has_login ? "Has login" : "No login"}</span></td>
                    <td data-label="Assigned to">{assignedText(s.assigned_to)}</td>
                    <td data-label="Status"><span className="badge">{s.status === "archived" ? "Archived" : "Active"}</span></td>
                    <td data-label="Actions">
                      <button id={`agent-student-view-${s.id}`} type="button" className="btn secondary small" aria-label={`View ${s.full_name}`} onClick={() => openDetail(s.id)}>View</button>{" "}
                      {isMaster && (confirm?.id === s.id ? (
                        <span role="group" aria-label={`Confirm ${confirm.kind}`}>
                          <button type="button" className="btn small" autoFocus disabled={busyId === s.id} onClick={() => act(s, confirm.kind)}>{busyId === s.id ? "Working…" : `Confirm ${confirm.kind}`}</button>{" "}
                          <button type="button" className="btn secondary small" disabled={busyId === s.id} onClick={() => { returnFocusTo.current = `agent-student-${confirm.kind}-${s.id}`; setConfirm(null); }}>Cancel</button>
                        </span>
                      ) : (
                        <button id={`agent-student-${s.status === "archived" ? "unarchive" : "archive"}-${s.id}`} type="button" className="btn secondary small"
                          aria-label={`${s.status === "archived" ? "Unarchive" : "Archive"} ${s.full_name}`}
                          onClick={() => setConfirm({ id: s.id, kind: s.status === "archived" ? "unarchive" : "archive" })}>
                          {s.status === "archived" ? "Unarchive" : "Archive"}
                        </button>
                      ))}
                      {rowError?.id === s.id && <p className="form-error" role="status" aria-live="polite" style={{ fontSize: 13 }}>{rowError.text}</p>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <nav aria-label="Student pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
            </nav>
          </>
        )}
      </section>

      {detailState === "loading" && <p className="muted" aria-live="polite">Loading student…</p>}
      {detailState === "gone" && <p className="form-error" role="alert">This student is no longer available.</p>}
      {detailState === "error" && <p className="form-error" role="alert">Unable to load this student.</p>}
      {detail && (
        <section className="card" aria-labelledby="agent-student-detail-heading" onKeyDown={(e) => { if (e.key === "Escape") closeDetail(); }} style={{ marginTop: 16 }}>
          <h4 id="agent-student-detail-heading" tabIndex={-1}>{detail.full_name}</h4>
          {editing ? (
            <AgentStudentForm mode="edit" student={detail} onCancel={() => setEditing(false)} onSaved={(s) => { setEditing(false); setNotice(`${s.full_name} saved.`); applyUpdate(s); }} />
          ) : (
            <>
              <dl className="record-details">
                <dt>Login</dt><dd>{detail.has_login ? "Has login (details come from the student's own account)" : "No login"}</dd>
                <dt>Email</dt><dd>{detail.email ?? "—"}</dd>
                <dt>Phone</dt><dd>{detail.phone ?? "—"}</dd>
                <dt>Date of birth</dt><dd>{detail.date_of_birth ?? "—"}</dd>
                <dt>Highest qualification</dt><dd>{detail.highest_qualification ?? "—"}</dd>
                <dt>Institution</dt><dd>{detail.institution ?? "—"}</dd>
                <dt>Graduation year</dt><dd>{detail.graduation_year ?? "—"}</dd>
                <dt>Preferred country</dt><dd>{detail.preferred_country ?? "—"}</dd>
                <dt>Preferred course</dt><dd>{detail.preferred_course ?? "—"}</dd>
                <dt>Preferred intake</dt><dd>{detail.preferred_intake ?? "—"}</dd>
                <dt>Notes</dt><dd style={{ whiteSpace: "pre-wrap" }}>{detail.notes ?? "—"}</dd>
                <dt>Assigned to</dt><dd>{assignedText(detail.assigned_to)}</dd>
                <dt>Created by</dt><dd>{detail.created_by ?? "—"}</dd>
                {detail.status === "archived" && (<><dt>Archived by</dt><dd>{detail.archived_by ?? "—"}</dd></>)}
              </dl>
              {!detail.has_login && detail.status === "active" && <button type="button" className="btn small" onClick={() => setEditing(true)}>Edit</button>}{" "}
              <button type="button" className="btn secondary small" onClick={closeDetail}>Close</button>
            </>
          )}
        </section>
      )}
    </div>
  );
}
```

(Assigning to a named Staff member needs a Staff list, which AGN-002 provides; on this branch the Assign control offers "Unassigned" only through the filter, and the `POST /assign` route is exercised by API tests. **Record this as a stated gap in Task 13's RTM row** and add an "Assign" picker after the AGN-002 merge — spec §12.)

`WorkflowPanel.tsx`: import `AgentStudentsPanel`; add `const showAgentStudents = user.role === "agent" && section === "students";` next to `showAgentTeam`; add `!showAgentStudents &&` to the early-return condition; render `{showAgentStudents && <AgentStudentsPanel memberRole={user.agent_member_role} />}` **before** `{specs.map(...)}` so the existing "Link student" form stays below. Change the link spec title from "Link student" to **"Link a student with an account"** only if the E2E specs `agt-002-referrals` / `enh-031-searchable-pickers` do not select it by that title — check with `grep -rn "Link student" apps/web/tests` first; if they do, keep the title unchanged.

`app/globals.css`, next to the `.table.psy-records` rule, the same stacked-card rule for `.table.stack-cards` (copy the existing block, swapping the class name).

- [ ] **Step 4: Run** — `WEB_TEST tests/components/AgentStudentsPanel.test.tsx tests/components/AgentStudentForm.test.tsx tests/lib/agentStudents.test.ts tests/components/Enh031ExistingPickers.test.tsx tests/components/AgentTeamPanel.test.tsx`. Expected: PASS.

- [ ] **Step 5: Type and lint** — `cd apps/web && npx tsc --noEmit && npx eslint components/AgentStudentsPanel.tsx components/AgentStudentForm.tsx lib/agentStudents.ts`. Expected: exit 0, no new errors.

- [ ] **Step 6: Refactor** — if `AgentStudentsPanel.tsx` exceeds ~250 lines, extract the detail `<section>` into `AgentStudentDetailPanel.tsx` (props: `detail`, `onClose`, `onSaved`) with no behaviour change; rerun Steps 4–5.

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/AgentStudentsPanel.tsx apps/web/components/WorkflowPanel.tsx apps/web/app/globals.css apps/web/tests/components/AgentStudentsPanel.test.tsx
git commit -m "feat(agn-004): Students panel -- search, archived filter, detail, inline archive, responsive cards"
```

---

### Task 12: Playwright spec (Master flows)

**Files:**
- Create: `apps/web/tests/e2e/agn-004-agent-students.spec.ts`

**Interfaces:**
- Consumes: the demo agent login used by `agt-002-referrals.spec.ts` (read its first 20 lines for the login helper and reuse it verbatim).

- [ ] **Step 1: Write the spec**

```ts
import { expect, test } from "@playwright/test";
// Reuse the exact login helper agt-002-referrals.spec.ts uses (same import path and demo agent credentials).
import { loginAsDemoAgent } from "./helpers/agent";

const stamp = () => Date.now().toString(36);

test.describe("AGN-004 agent students (Master)", () => {
  test("create, duplicate warning, save anyway, edit, archive, unarchive", async ({ page }) => {
    const name = `E2E Student ${stamp()}`;
    const email = `e2e.${stamp()}@example.local`;
    await loginAsDemoAgent(page);
    await page.goto("/overseas/agent/students");
    await page.getByRole("button", { name: "Add student" }).first().click();
    await page.getByLabel("Full name (required)").fill(name);
    await page.getByLabel("Email").fill(email);
    await page.getByRole("button", { name: "Save student" }).click();
    await expect(page.getByRole("status")).toContainText(`${name} added.`);

    await page.getByRole("button", { name: "Add student" }).first().click();
    await page.getByLabel("Full name (required)").fill(`${name} Twin`);
    await page.getByLabel("Email").fill(email.toUpperCase());
    await page.getByRole("button", { name: "Save student" }).click();
    await expect(page.getByRole("alert")).toContainText("already exists in your agency");
    await page.getByRole("button", { name: "Save anyway" }).click();
    await expect(page.getByRole("status")).toContainText(`${name} Twin added.`);

    await page.getByLabel("Search students").fill(name);
    await page.getByRole("button", { name: `View ${name}`, exact: true }).click();
    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByLabel("Preferred country").fill("Ireland");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("status")).toContainText(`${name} saved.`);

    await page.getByRole("button", { name: `Archive ${name}`, exact: true }).click();
    await page.getByRole("button", { name: "Confirm archive" }).click();
    await expect(page.getByRole("status")).toContainText(`${name} archived.`);
    await expect(page.getByRole("cell", { name, exact: true })).toHaveCount(0);
    await page.getByLabel("Show archived").check();
    await page.getByRole("button", { name: `Unarchive ${name}`, exact: true }).click();
    await page.getByRole("button", { name: "Confirm unarchive" }).click();
    await expect(page.getByRole("status")).toContainText(`${name} restored.`);
  });

  test("keyboard only: add a student", async ({ page }) => {
    const name = `Keyboard ${stamp()}`;
    await loginAsDemoAgent(page);
    await page.goto("/overseas/agent/students");
    await page.getByRole("button", { name: "Add student" }).first().focus();
    await page.keyboard.press("Enter");
    await page.getByLabel("Full name (required)").focus();
    await page.keyboard.type(name);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("status")).toContainText(`${name} added.`);
  });

  test("320 px: no horizontal overflow on the Students page", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 800 });
    await loginAsDemoAgent(page);
    await page.goto("/overseas/agent/students");
    await expect(page.getByRole("heading", { name: "Students", level: 3 })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
```

If `agt-002-referrals.spec.ts` logs in inline instead of through a helper, copy its login lines into a local `loginAsDemoAgent` function at the top of this file instead of importing.

- [ ] **Step 2: Run on the owner's rebuilt stack** (the owner starts it; ports per the memory convention, e.g. web 3004 / API 8004):
`cd apps/web && PLAYWRIGHT_BASE_URL=http://127.0.0.1:3004 npx playwright test tests/e2e/agn-004-agent-students.spec.ts tests/e2e/agt-002-referrals.spec.ts tests/e2e/agn-001-multi-tenant.spec.ts tests/e2e/enh-031-searchable-pickers.spec.ts tests/e2e/agt-004-commission-payout.spec.ts`
Expected: PASS. Failures in the four existing specs that also fail on `main` are recorded, not "fixed" here.

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/agn-004-agent-students.spec.ts
git commit -m "test(agn-004): end-to-end Master student lifecycle, keyboard and 320 px"
```

---

### Task 13: Documentation and traceability

**Files:** `docs/decisions/PRODUCT_DECISION_REGISTER.md`, `docs/delivery/ENHANCEMENT_BACKLOG.md`, `docs/architecture/DATA_MODEL.md`, `docs/architecture/API_CONTRACT.md`, `docs/architecture/RBAC_MATRIX.md`, `docs/architecture/SECURITY_CONTROLS.md`, `docs/architecture/THREAT_MODEL.md`, `docs/product/PRD_OPEN_ITEMS.md`, `docs/evidence/CONFLICT_MATRIX.md`, `docs/ux/SCREEN_CATALOG.md`, `docs/ux/screen_catalog.json`, `docs/quality/RTM.md`.

- [ ] **Step 1: Decision register** — append `### DEC-SCOPE-041 — Agent students: students with no login, staff assignment (`AGN-004`)` after `DEC-SCOPE-039`, with: ID note (provisional; AGN-002 holds `DEC-SCOPE-040` on its branch), Question, Evidence (the impact analysis of 2026-09-30 incl. the `agent_students.student_id → users.id` finding), Conflicts recorded (the `DEC-SCOPE-035 D3` citation; `EVID-015` §6 Staff-cannot-delete vs the request's "Master/Staff … archive" → Master-only; AGN-002 S1 agency-wide vs G4), Resolution (D1, D3, D4, D5, D7, D8, G1–G5, F1–F5 verbatim from the spec), Consequences. Add a one-line note under `DEC-SCOPE-038` D13 that staff assignment/ownership is now decided by `DEC-SCOPE-041`.
- [ ] **Step 2: Backlog** — summary-table row `AGN-004 | Agent students — create, edit, view, archive students who never log in; staff assigned-only | Large | High | Yes | AGT-002, AGN-001, AGN-002 (merge)`; a full `## AGN-004` section (requirement, expected behaviour, AC01–AC13 from spec §8, status "Implemented; browser validation and independent Codex review pending"); Appendix B note that staff assignment/ownership left `EVID-015`'s parked list.
- [ ] **Step 3: Architecture docs** — DATA_MODEL §6.8 addendum (columns, CHECKs, indexes, migration `0047_agent_students_crm`) and §6.8a (member role `staff`, `staff_seq`); API_CONTRACT rows for the seven new routes and the three changed existing ones (roster hides archived; link archived `409`; staff scope), with every stable `detail` string; RBAC_MATRIX §2.8 (Master vs Staff table; the `404` existence mask; G4); SECURITY_CONTROLS row; THREAT_MODEL entries (§7 boundaries and residuals).
- [ ] **Step 4: Open items and conflicts** — PRD_OPEN_ITEMS new item: erasure path for students with no login (`NEEDS_CONFIRMATION`); PRD item 68 note (agent half: students with no login now exist); CONFLICT_MATRIX `C-10` note.
- [ ] **Step 5: Screen catalog** — the Students screen entry for `overseas/agent/students` gains the panel, states and Master/Staff differences (both `.md` and `.json`; validate the JSON with `python -m json.tool docs/ux/screen_catalog.json > /dev/null`).
- [ ] **Step 6: RTM** — `AGN-004` row: traceability chain, code and test files, the evidence from Tasks 8, 11 and 12 (exact counts), the recorded `test_agn_001_schema.py` edit, the stated gaps (Staff browser flows and the named-Staff Assign picker wait for AGN-002; erasure residual), and status **"Implemented — NOT COMPLETE: browser validation and independent Codex review pending."**
- [ ] **Step 7: Commit**

```bash
git add docs
git commit -m "docs(agn-004): DEC-SCOPE-041, backlog, data model, API, RBAC, security, screens and RTM"
```

---

### Task 14: Verification sweep (evidence only — no completion claim)

- [ ] **Step 1:** `API_TEST tests` — record passed/failed counts; compare against the provider-credential baseline.
- [ ] **Step 2:** Migration: `alembic upgrade head` → `alembic downgrade 0046_agent_orgs` → `alembic upgrade head` on a scratch database copy with pre-existing link rows; confirm rows identical (Task 2's test covers the automated part).
- [ ] **Step 3:** `cd apps/web && npx vitest run && npx tsc --noEmit && npx eslint . && npm run build` — record counts and exit codes.
- [ ] **Step 4:** Diff scan vs `main`: `git diff --stat origin/main...HEAD`; no skipped tests (`grep -rn "skip\|only(" apps/api/tests/test_agn_004_* apps/web/tests/**/*agent*`), no debug output, no secrets.
- [ ] **Step 5:** Report to the owner with the evidence and the two outstanding gates: **browser validation** and **independent Codex review**. Do not mark AGN-004 complete.

---

## Self-review notes

- **Spec coverage:** §4 → Tasks 1–2; §5.1 → Task 3; §5.2–5.3 → Task 4; §5.4–5.5 → Tasks 5–7; §5.6 → Task 4; §6 → Tasks 9–11; §7 → tests across Tasks 3–7 and 11; §8 AC01–AC13 → Tasks 1–12 (AC12 Task 2, AC13 Tasks 11–12); §9 → every task; §11 → Task 13; §13 gates → Task 14 + the owner's browser validation and Codex review.
- **Stated gap found while planning:** spec §6 lists an Assign control; a named-Staff picker needs a Staff list endpoint that AGN-002 owns. The API route is built and tested; the picker waits for the merge (recorded in Task 11 and the RTM).
- **Type consistency:** `student_scope`, `visible_student_user_ids`, `application_scope`, `phone_digits`, `record_item`, `record_detail`, `load_scoped`, `list_page`, `find_duplicates`, `duplicate_conflict`, `create_record`, `apply_update`, `set_archived`, `active_staff_member`, `lock_active_org`, `is_agent_staff`, `agentNavFor`, `RECORDS_URL`, `AgentStudentItem`, `AgentStudentDetail` are used with the same names and signatures in every task.
