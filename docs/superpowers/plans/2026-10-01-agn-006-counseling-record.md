# AGN-006 Counseling Record Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An agency Master or the assigned staff member records and reads back one counseling record (completed, career interest,
course preference, country preference, budget + currency, remarks) per agency student with no login.

**Architecture:** A new one-to-one table `agent_student_counseling` (create-table-only migration 0054) written by a new
`PUT /workflows/overseas/agent/crm/students/{id}/counseling` in the existing AGN-004 router, reusing its gate, organisation-then-row
lock, scope (404) and audit helpers; read back as an additive `counseling` key on the student detail. The web detail panel gains a
view card and a separate form; the AGN-021 Staff Activity allowlist gains one action.

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy 2 async + Alembic + PostgreSQL; pytest + pytest-asyncio + httpx (`client_for`);
Next.js + React + Vitest + Testing Library; Playwright; Docker Compose `ci` profile.

**Spec:** `docs/superpowers/specs/2026-10-01-agn-006-counseling-record-design.md` (read it first; decisions C1–C9).

## Global Constraints

- No new dependency (Python or npm); no new CSS rule; no change to unrelated modules.
- The AGN-004 `PATCH /students/{id}` contract, the list item shape (`record_item`) and every existing message stay unchanged.
- Migration revision `0054_agent_student_counseling`, `down_revision = "0053_school_funding_records"` — **recheck `origin/main` before
  Task 1 and before merging**; AGN-007 may take 0054 / `DEC-SCOPE-047` first, then renumber (precedent 0052, 0053).
- Currencies, exactly: `INR, USD, GBP, EUR, CAD, AUD, NZD` (default `INR`). Amount: `0 ≤ amount ≤ 99,999,999.99`, ≤ 2 decimals.
- Text limits: `career_interest` 200, `course_preference` 200, `country_preference` 120, `remarks` 2000.
- 404 text `Student not found`; 409 texts `Counseling is recorded only for students without a login` and `Unarchive this student first`.
- Audit action `agent_student.counseling`, metadata `{"fields": [sorted changed names]}` — names only, never values. Log event
  `agent_student_counseling_saved` with ids and field names only.
- Response money: `budget_amount` is a string with exactly 2 decimals (`"2500000.00"`); never the counseling row id or any user id.
- Downgrade refuses while any counseling record exists.
- Tests run with real tools (pytest / Vitest / Playwright); verify from exit codes and output, never by reasoning. Per feature run the
  **lite** backend set only (the owner runs the full suite every 4–5 stories).
- The owner controls Docker: ask them to start the services; never start/stop the main stack yourself.

## Review Focus

1. **Amount typed with Indian grouping** ("25,00,000") must save as 2500000.00, not be rejected → Task 5 `counselingPayload` test.
2. **Re-saving an untouched form** must send nothing and audit nothing → Task 3 normalisation test + Task 6 "unchanged Save" test.
3. **A staff member unassigned while the form is open** must get 404 on save, shown as an alert, form kept → Task 3 out-of-scope test
   (`s1` on `unassigned`) + Task 6 404 alert test.
4. **Two people saving the first record at once** must leave exactly one row, both 200 → Task 3 concurrency test.
5. **Hostile remarks** (`<script>`, NUL byte, 2001 chars) must render as text / be refused with 422 → Task 3 validation test + Task 7
   literal-render test.

## Test commands (PowerShell, from the worktree root)

Ask the owner to start the isolated test services once:

```powershell
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn006 --profile ci build api-test web-test
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn006 --profile ci up -d --wait postgres redis
```

Then (use the **Windows-form absolute path** for the mount — `$PWD` under Git Bash mounts a stale tree):

```powershell
function dc { docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn006 --profile ci @args }
$API = "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/agn-006/apps/api"
$WEB = "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/agn-006/apps/web"
dc run --rm --no-deps -v "${API}:/app" api-test alembic upgrade head
```

- **API(x)** = `dc run --rm --no-deps -v "${API}:/app" api-test sh -c "alembic upgrade head && python -m pytest -q x"`
- **LINT(x)** = `dc run --rm --no-deps -v "${API}:/app" api-test ruff check x`
- **WEB(x)** = `dc run --rm --no-deps -v "${WEB}/components:/app/components" -v "${WEB}/lib:/app/lib" -v "${WEB}/tests:/app/tests" -v "${WEB}/app:/app/app" web-test npx vitest run x`
- **TSC** = `dc run --rm --no-deps -v "${WEB}/components:/app/components" -v "${WEB}/lib:/app/lib" -v "${WEB}/tests:/app/tests" -v "${WEB}/app:/app/app" web-test npx tsc --noEmit`

If the isolated test DB carries a stale alembic stamp: `alembic stamp --purge 0053_school_funding_records` then `alembic upgrade head`.

## File map

| File | Responsibility |
|---|---|
| Create `apps/api/alembic/versions/0054_agent_student_counseling.py` | Create table; refuse downgrade while rows exist |
| Modify `apps/api/app/models.py` (after `AgentStudent`, ~L882) | `COUNSELING_CURRENCIES`, `AgentStudentCounseling` |
| Modify `apps/api/app/schemas.py` (after `AgentStudentAssign`, ~L559) | `CounselingCurrency`, `AgentStudentCounselingSave` |
| Modify `apps/api/app/services/agent_students.py` | `counseling_detail`, `save_counseling`; `record_detail` adds `counseling` |
| Modify `apps/api/app/api/agent_students.py` | `PUT /{student_id}/counseling` |
| Modify `apps/api/app/services/staff_activity.py` | allowlist + `_fields` |
| Create `apps/api/tests/test_agn_006_migration.py`, `test_agn_006_schemas.py`, `test_agn_006_counseling.py`, `test_agn_006_activity.py` | AC01–AC09, AC12 |
| Modify `apps/api/tests/test_agn_003_matrix.py` (`BOTH_ALLOWED`) | the new route in the §6 matrix |
| Modify `apps/web/lib/agentStudents.ts` | types, constants, payload/validate/format helpers |
| Modify `apps/web/lib/agentStaff.ts` | activity label |
| Create `apps/web/components/AgentStudentCounselingForm.tsx` | the form |
| Create `apps/web/components/AgentStudentCounselingCard.tsx` | the view + opener |
| Modify `apps/web/components/AgentStudentDetailPanel.tsx`, `AgentStudentsPanel.tsx` | one form at a time; notice |
| Create `apps/web/tests/lib/agentStudentsCounseling.test.ts`, `tests/components/AgentStudentCounselingForm.test.tsx`, `tests/components/AgentStudentCounselingCard.test.tsx`, `tests/e2e/agn-006-counseling.spec.ts` | AC10, AC11 |
| Docs (Task 9) | backlog, decision register, contracts, RTM |

---

### Task 1: Table, model and migration 0054 (AC09)

**Files:**
- Create: `apps/api/alembic/versions/0054_agent_student_counseling.py`
- Modify: `apps/api/app/models.py` (insert after the `AgentStudent` class, before `class AgentCommission`)
- Test: `apps/api/tests/test_agn_006_migration.py`

**Interfaces:**
- Produces: `app.models.COUNSELING_CURRENCIES: tuple[str, ...]`, `app.models.AgentStudentCounseling` (columns per spec §4),
  migration module attributes `revision`, `down_revision`, `CURRENCIES`.

- [ ] **Step 0: Recheck main**

Run: `git fetch origin` then `git log --oneline -3 origin/main` and `git ls-tree --name-only origin/main apps/api/alembic/versions/ | Select-Object -Last 3`.
Expected: the newest revision is still `0053_school_funding_records`. If a `0054_*` exists, stop and ask the owner (renumber to 0055).

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_agn_006_migration.py`:

```python
"""AGN-006 -- migration 0054_agent_student_counseling (spec §4, AC09): single head after 0053, create-table only, matches the model,
database checks enforced, round trip keeps existing rows, downgrade refuses while counseling records exist.

Round trips run in a throwaway database built from scratch (the AGN-004 / ENH-001 pattern): a downgrade never runs against the shared
test database. Plain (non-async) round-trip tests: alembic/env.py calls asyncio.run() itself."""

import asyncio
import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path
from typing import get_args

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings
from app.models import COUNSELING_CURRENCIES, AgentStudentCounseling
from tests.agn001_helpers import mk_active_org, uniq
from tests.agn004_helpers import mk_record

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_006_migration_0054", VERSIONS / "0054_agent_student_counseling.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

REV = "0054_agent_student_counseling"
BASE = "0053_school_funding_records"
TABLE = "agent_student_counseling"
STUDENTS = "SELECT id, agent_id, student_id, status, full_name FROM agent_students ORDER BY id"


def test_migration_follows_0053_and_is_the_single_head():
    assert _migration.revision == REV
    assert _migration.down_revision == BASE
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    heads = set(parents) - set(parents.values())
    assert len(heads) == 1


def test_currency_lists_agree():
    assert _migration.CURRENCIES == COUNSELING_CURRENCIES == ("INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD")


@pytest.mark.asyncio
async def test_table_matches_the_model(db_session):
    conn = await db_session.connection()
    cols = await conn.run_sync(lambda sync: {c["name"]: c["nullable"] for c in inspect(sync).get_columns(TABLE)})
    model = {c.name: c.nullable for c in AgentStudentCounseling.__table__.columns}
    assert cols == model
    assert cols["agent_student_id"] is False and cols["counseling_completed"] is False and cols["updated_by_user_id"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"budget_amount": Decimal("-1"), "budget_currency": "INR"}, "ck_agent_student_counseling_budget"),
        ({"budget_currency": "INR"}, "ck_agent_student_counseling_budget_pair"),
        ({"budget_amount": Decimal("5")}, "ck_agent_student_counseling_budget_pair"),
        ({"budget_amount": Decimal("5"), "budget_currency": "JPY"}, "ck_agent_student_counseling_currency"),
        ({"counseling_completed": True}, "ck_agent_student_counseling_completed"),
    ],
    ids=["negative", "currency-alone", "amount-alone", "unknown-currency", "completed-unstamped"],
)
async def test_the_database_refuses_invalid_rows(db_session, overrides, constraint):
    ctx = await mk_active_org(db_session, name=f"Counseling DB {uniq()}")
    row = await mk_record(db_session, agent=ctx["master"], full_name="Db Check")
    db_session.add(AgentStudentCounseling(**({"agent_student_id": row.id, "counseling_completed": False, "updated_by_user_id": ctx["master"].id} | overrides)))
    with pytest.raises(IntegrityError, match=constraint):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_one_record_per_student(db_session):
    ctx = await mk_active_org(db_session, name=f"Counseling One {uniq()}")
    row = await mk_record(db_session, agent=ctx["master"], full_name="Only Once")
    db_session.add(AgentStudentCounseling(agent_student_id=row.id, counseling_completed=False, updated_by_user_id=ctx["master"].id))
    await db_session.commit()
    db_session.add(AgentStudentCounseling(agent_student_id=row.id, counseling_completed=False, updated_by_user_id=ctx["master"].id))
    with pytest.raises(IntegrityError, match="uq_agent_student_counseling_student"):
        await db_session.commit()
    await db_session.rollback()


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


def _has_table(url: str) -> bool:
    return _sql(url, f"SELECT to_regclass('public.{TABLE}') IS NOT NULL")[0][0]


@pytest.fixture
def isolated_db():
    """A fresh database at 0053 with one agent and one agency student with no login."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"agn006_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {"agent": uuid.uuid4(), "student": uuid.uuid4()}
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'Mig Agent', 'agent', 'overseas', true, true, 'en-GB', '{}')",
            {"id": ids["agent"], "email": f"agent-{name}@example.local"},
        )
        _sql(url, "INSERT INTO agent_students (id, agent_id, student_id, status, full_name) VALUES (:id, :agent, NULL, 'active', 'Mig Student')", {"id": ids["student"], "agent": ids["agent"]})
        yield {"cfg": cfg, "url": url, "ids": ids}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_existing_rows(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, STUDENTS)
    command.upgrade(cfg, REV)
    assert _has_table(url)
    command.downgrade(cfg, BASE)
    assert not _has_table(url)
    assert _sql(url, STUDENTS) == before
    command.upgrade(cfg, REV)
    assert _has_table(url)
    assert _sql(url, STUDENTS) == before


def test_downgrade_refuses_while_counseling_records_exist(isolated_db):
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, REV)
    _sql(
        url,
        f"INSERT INTO {TABLE} (id, agent_student_id, counseling_completed, updated_by_user_id) VALUES (:id, :student, false, :agent)",
        {"id": uuid.uuid4(), "student": ids["student"], "agent": ids["agent"]},
    )
    with pytest.raises(RuntimeError, match="counseling records exist"):
        command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT version_num FROM alembic_version") == [(REV,)]
    assert _sql(url, f"SELECT count(*) FROM {TABLE}") == [(1,)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: API(`tests/test_agn_006_migration.py`)
Expected: collection ERROR — `ImportError: cannot import name 'COUNSELING_CURRENCIES' from 'app.models'`.

- [ ] **Step 3: Add the model**

In `apps/api/app/models.py`, insert after the `AgentStudent` class (after its `__table_args__`), before `class AgentCommission`:

```python
COUNSELING_CURRENCIES = ("INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD")  # AGN-006 C2; schemas.CounselingCurrency mirrors it


class AgentStudentCounseling(Base, TimestampMixin):
    """AGN-006 (DEC-SCOPE-047, EVID-015 §5 Step 2): one counseling record per agency student with no login. Replaced whole on every
    save (C1); its history is the audit log. `completed_at`/`completed_by_user_id` are stamped by the server (C5)."""

    __tablename__ = "agent_student_counseling"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    agent_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_students.id"))
    counseling_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    career_interest: Mapped[str | None] = mapped_column(String(200), nullable=True)
    course_preference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country_preference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    budget_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    budget_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    __table_args__ = (
        UniqueConstraint("agent_student_id", name="uq_agent_student_counseling_student"),
        CheckConstraint(
            "counseling_completed = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL)",
            name="ck_agent_student_counseling_completed",
        ),
        CheckConstraint("budget_amount IS NULL OR budget_amount >= 0", name="ck_agent_student_counseling_budget"),
        CheckConstraint(
            "budget_currency IS NULL OR budget_currency IN (" + ", ".join(f"'{c}'" for c in COUNSELING_CURRENCIES) + ")",
            name="ck_agent_student_counseling_currency",
        ),
        CheckConstraint("(budget_amount IS NULL) = (budget_currency IS NULL)", name="ck_agent_student_counseling_budget_pair"),
    )
```

- [ ] **Step 4: Add the migration**

Create `apps/api/alembic/versions/0054_agent_student_counseling.py`:

```python
"""AGN-006 -- agent_student_counseling.

Revision ID: 0054_agent_student_counseling
Revises: 0053_school_funding_records

docs/superpowers/specs/2026-10-01-agn-006-counseling-record-design.md §4 (DEC-SCOPE-047). Create-table only: no existing table is
altered and no existing row is read or written. Guarded like 0053: on a fresh database 0001_initial's create_all() has already built
the table from the model. `downgrade()` refuses while any counseling record exists (the 0049 pattern), so no counseling data is dropped
by accident; otherwise it drops the empty table.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0054_agent_student_counseling"
down_revision = "0053_school_funding_records"
branch_labels = None
depends_on = None

TABLE = "agent_student_counseling"
CURRENCIES = ("INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD")  # frozen copy: a migration never imports the models


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    currency_list = ", ".join(f"'{c}'" for c in CURRENCIES)
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_students.id"), nullable=False),
        sa.Column("counseling_completed", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("career_interest", sa.String(200), nullable=True),
        sa.Column("course_preference", sa.String(200), nullable=True),
        sa.Column("country_preference", sa.String(120), nullable=True),
        sa.Column("budget_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("budget_currency", sa.String(3), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("agent_student_id", name="uq_agent_student_counseling_student"),
        sa.CheckConstraint(
            "counseling_completed = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL)",
            name="ck_agent_student_counseling_completed",
        ),
        sa.CheckConstraint("budget_amount IS NULL OR budget_amount >= 0", name="ck_agent_student_counseling_budget"),
        sa.CheckConstraint(f"budget_currency IS NULL OR budget_currency IN ({currency_list})", name="ck_agent_student_counseling_currency"),
        sa.CheckConstraint("(budget_amount IS NULL) = (budget_currency IS NULL)", name="ck_agent_student_counseling_budget_pair"),
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0054_agent_student_counseling: counseling records exist. Remove them deliberately first.")
    op.drop_table(TABLE)
```

- [ ] **Step 5: Run test to verify it passes**

Run: API(`tests/test_agn_006_migration.py`) and LINT(`app/models.py alembic/versions/0054_agent_student_counseling.py tests/test_agn_006_migration.py`)
Expected: 11 passed; ruff "All checks passed!". If `test_table_matches_the_model` fails on `created_at`/`updated_at` nullability, compare with
`TimestampMixin` (the model's columns are not-null via `Mapped[datetime]`) and fix the migration, not the test.

- [ ] **Step 6: Commit**

```powershell
git add apps/api/app/models.py apps/api/alembic/versions/0054_agent_student_counseling.py apps/api/tests/test_agn_006_migration.py
git commit -m "feat(agn-006): agent_student_counseling table and migration 0054"
```

---

### Task 2: Request schema (AC03 at the unit level)

**Files:**
- Modify: `apps/api/app/schemas.py` (insert after `class AgentStudentAssign`, ~L559)
- Test: `apps/api/tests/test_agn_006_schemas.py`

**Interfaces:**
- Consumes: `app.models.COUNSELING_CURRENCIES` (Task 1).
- Produces: `app.schemas.CounselingCurrency` (a `Literal` of the 7 codes), `app.schemas.AgentStudentCounselingSave` with fields
  `counseling_completed: bool`, `career_interest`, `course_preference`, `country_preference`, `remarks: str | None`,
  `budget_amount: Decimal | None`, `budget_currency: CounselingCurrency | None`. `model_dump()` returns every field (Decimal kept).

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_agn_006_schemas.py`:

```python
"""AGN-006 -- AgentStudentCounselingSave (spec §5.1): normalisation, the budget pair rule, bounds, mass assignment."""

from decimal import Decimal
from typing import get_args

import pytest
from pydantic import ValidationError

from app.models import COUNSELING_CURRENCIES
from app.schemas import AgentStudentCounselingSave, CounselingCurrency


def test_literal_matches_the_model_list():
    assert get_args(CounselingCurrency) == COUNSELING_CURRENCIES


def test_text_is_trimmed_and_blank_becomes_null():
    body = AgentStudentCounselingSave(counseling_completed=False, career_interest="  Law  ", course_preference="   ", remarks="Line one\nLine two")
    assert body.career_interest == "Law" and body.course_preference is None and body.remarks == "Line one\nLine two"


def test_an_amount_alone_defaults_to_inr_and_a_numeric_string_is_accepted():
    body = AgentStudentCounselingSave(counseling_completed=False, budget_amount="1500.5")
    assert body.budget_amount == Decimal("1500.5") and body.budget_currency == "INR"


def test_omitted_fields_dump_as_null():
    assert AgentStudentCounselingSave(counseling_completed=True).model_dump() == {
        "counseling_completed": True, "career_interest": None, "course_preference": None, "country_preference": None,
        "budget_amount": None, "budget_currency": None, "remarks": None,
    }


@pytest.mark.parametrize(
    "fields",
    [
        {"budget_amount": -1},
        {"budget_amount": "100000000"},
        {"budget_amount": "10.123"},
        {"budget_amount": "NaN"},
        {"budget_amount": "Infinity"},
        {"budget_amount": 5, "budget_currency": "JPY"},
        {"budget_currency": "USD"},
        {"completed_at": "2026-10-01T00:00:00Z"},
        {"career_interest": "x" * 201},
        {"country_preference": "x" * 121},
        {"remarks": "x" * 2001},
        {"remarks": "bad\x00byte"},
    ],
    ids=["negative", "over-max", "three-decimals", "nan", "infinity", "unknown-currency", "currency-alone", "server-owned", "career-long", "country-long", "remarks-long", "nul"],
)
def test_invalid_input_is_refused(fields):
    with pytest.raises(ValidationError):
        AgentStudentCounselingSave(**({"counseling_completed": False} | fields))


def test_counseling_completed_is_required():
    with pytest.raises(ValidationError):
        AgentStudentCounselingSave(career_interest="Law")


def test_the_maximum_is_accepted():
    assert AgentStudentCounselingSave(counseling_completed=False, budget_amount="99999999.99", budget_currency="NZD").budget_amount == Decimal("99999999.99")
```

- [ ] **Step 2: Run test to verify it fails**

Run: API(`tests/test_agn_006_schemas.py`)
Expected: collection ERROR — `ImportError: cannot import name 'AgentStudentCounselingSave'`.

- [ ] **Step 3: Write the schema**

In `apps/api/app/schemas.py`, after `class AgentStudentAssign` (keep the existing imports: `Decimal`, `Annotated`, `Literal`, `Field`,
`field_validator`, `model_validator`, `PydanticCustomError` are already imported there; `clean_free_text` is defined later in the module
and is called at validation time, as `_AgentStudentRecordFields` already does):

```python
CounselingCurrency = Literal["INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD"]  # models.COUNSELING_CURRENCIES; test_agn_006_schemas
_COUNSELING_LIMITS = {"career_interest": 200, "course_preference": 200, "country_preference": 120, "remarks": 2000}


class AgentStudentCounselingSave(BaseModel):
    """AGN-006 (DEC-SCOPE-047 C1-C5, EVID-015 §5 Step 2): the whole counseling record, replaced on every save -- an omitted optional
    field is stored as null. Server-owned fields (completed at/by, updated by) are not accepted: `extra="forbid"` answers 422."""

    model_config = {"extra": "forbid"}
    counseling_completed: bool
    career_interest: str | None = None
    course_preference: str | None = None
    country_preference: str | None = None
    budget_amount: Annotated[Decimal, Field(ge=0, le=Decimal("99999999.99"), max_digits=10, decimal_places=2)] | None = None
    budget_currency: CounselingCurrency | None = None
    remarks: str | None = None

    @field_validator("career_interest", "course_preference", "country_preference", "remarks")
    @classmethod
    def _text(cls, value, info):
        return clean_free_text(value, _COUNSELING_LIMITS[info.field_name])

    @model_validator(mode="after")
    def _budget_pair(self):
        if self.budget_amount is None and self.budget_currency is not None:
            raise PydanticCustomError("currency_without_amount", "Enter a budget amount, or leave the currency empty")
        if self.budget_amount is not None and self.budget_currency is None:
            self.budget_currency = "INR"
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: API(`tests/test_agn_006_schemas.py`) and LINT(`app/schemas.py tests/test_agn_006_schemas.py`)
Expected: 18 passed; ruff clean. If `"NaN"` is accepted, add `allow_inf_nan=False` to the `Field(...)` (pydantic's default is already
False for Decimal; the test proves it).

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/schemas.py apps/api/tests/test_agn_006_schemas.py
git commit -m "feat(agn-006): counseling save schema"
```

---

### Task 3: Service, PUT route and read-back (AC01–AC08, AC12)

**Files:**
- Modify: `apps/api/app/services/agent_students.py` (imports; new section before `# --- duplicate warning`; `record_detail`)
- Modify: `apps/api/app/api/agent_students.py` (imports; new route at the end)
- Modify: `apps/api/tests/test_agn_003_matrix.py` (`BOTH_ALLOWED`, after the `Edit Student` row)
- Test: `apps/api/tests/test_agn_006_counseling.py`

**Interfaces:**
- Consumes: `AgentStudentCounseling` (Task 1), `AgentStudentCounselingSave` (Task 2); existing `_gate`, `_locked_row`, `_audit`, `_log`,
  `record_detail`, `load_scoped`.
- Produces: `services.agent_students.counseling_detail(db, row) -> dict | None`,
  `services.agent_students.save_counseling(db, row, user, data: dict) -> list[str]`, route
  `PUT /api/v1/workflows/overseas/agent/crm/students/{student_id}/counseling` → `200 {"student": detail}`; detail key `counseling` with
  exactly the keys `counseling_completed, completed_at, completed_by, career_interest, course_preference, country_preference,
  budget_amount, budget_currency, remarks, updated_at, updated_by`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_agn_006_counseling.py`:

```python
"""AGN-006 -- an agency student's counseling record (spec §5; DEC-SCOPE-047 C1-C6; AC01-AC08, AC12)."""

import asyncio
import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AgentOrg, AgentStudent, AgentStudentCounseling, AuditLog
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn004_helpers import RECORDS, mk_record, mk_staff

FULL = {
    "counseling_completed": True,
    "career_interest": "Data science",
    "course_preference": "MSc Data Science",
    "country_preference": "Ireland",
    "budget_amount": 2500000,
    "budget_currency": "INR",
    "remarks": "Needs scholarship options.\nPrefers the September intake.",
}
COUNSELING_KEYS = {
    "counseling_completed", "completed_at", "completed_by", "career_interest", "course_preference", "country_preference",
    "budget_amount", "budget_currency", "remarks", "updated_at", "updated_by",
}


def url(sid) -> str:
    return f"{RECORDS}/{sid}/counseling"


@pytest_asyncio.fixture
async def agency(db_session):
    ctx = await mk_active_org(db_session, name=f"Counseling Agency {uniq()}")
    other = await mk_active_org(db_session, name=f"Counseling Other {uniq()}")
    s1 = await mk_staff(db_session, ctx["org"], full_name="Couns One")
    s2 = await mk_staff(db_session, ctx["org"], full_name="Couns Two")
    row = await mk_record(db_session, agent=ctx["master"], full_name="Asha Rao", assigned_member=s1["member"])
    unassigned = await mk_record(db_session, agent=ctx["master"], full_name="Nobody Assigned")
    archived = await mk_record(db_session, agent=ctx["master"], full_name="Archived Student", assigned_member=s1["member"], status="archived")
    account = await mk_user(db_session, role="overseas_student", full_name="Linked Student")
    linked = AgentStudent(agent_id=ctx["master"].id, student_id=account.id, status="active", assigned_member_id=s1["member"].id)
    db_session.add(linked)
    await db_session.commit()
    return ctx | {"other": other, "s1": s1, "s2": s2, "row": row, "unassigned": unassigned, "archived": archived, "linked": linked}


async def _records(db, sid) -> list[AgentStudentCounseling]:
    stmt = select(AgentStudentCounseling).where(AgentStudentCounseling.agent_student_id == sid).execution_options(populate_existing=True)
    return list((await db.scalars(stmt)).all())


async def _audits(db, sid) -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.action == "agent_student.counseling", AuditLog.entity_id == str(sid)))).all())


@pytest.mark.asyncio
async def test_master_saves_and_reads_back_every_field(agency):  # AC01
    async with client_for(agency["master"].email) as c:
        saved = await c.put(url(agency["row"].id), json=FULL)
        read = await c.get(f"{RECORDS}/{agency['row'].id}")
    assert saved.status_code == 200, saved.text
    counseling = read.json()["student"]["counseling"]
    assert saved.json()["student"]["counseling"] == counseling
    assert {k: counseling[k] for k in FULL} == {**FULL, "budget_amount": "2500000.00"}
    assert counseling["completed_at"] and counseling["completed_by"] == agency["master"].full_name
    assert counseling["updated_by"] == agency["master"].full_name


@pytest.mark.asyncio
async def test_assigned_staff_can_save(db_session, agency):  # AC02
    async with client_for(agency["s1"]["user"].email) as c:
        response = await c.put(url(agency["row"].id), json={"counseling_completed": False, "career_interest": "Law"})
    assert response.status_code == 200, response.text
    [record] = await _records(db_session, agency["row"].id)
    assert record.career_interest == "Law" and record.updated_by_user_id == agency["s1"]["user"].id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("caller", "target"),
    [("s2", "row"), ("s1", "unassigned"), ("other", "row"), ("master", "unknown")],
    ids=["other-staff", "unassigned-to-caller", "other-agency", "unknown-id"],
)
async def test_out_of_scope_is_404_and_writes_nothing(db_session, agency, caller, target):  # AC02, AC12; Review Focus 3
    email = {"s2": agency["s2"]["user"].email, "s1": agency["s1"]["user"].email, "other": agency["other"]["master"].email, "master": agency["master"].email}[caller]
    sid = uuid.uuid4() if target == "unknown" else agency[target].id
    async with client_for(email) as c:
        response = await c.put(url(sid), json=FULL)
    assert response.status_code == 404 and response.json()["detail"] == "Student not found"
    assert await _records(db_session, sid) == [] and await _audits(db_session, sid) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {**FULL, "budget_amount": -1},
        {**FULL, "budget_amount": "-0.01"},
        {**FULL, "budget_amount": 100000000},
        {**FULL, "budget_amount": "10.123"},
        {**FULL, "budget_amount": "NaN"},
        {**FULL, "budget_currency": "JPY"},
        {**FULL, "budget_amount": None, "budget_currency": "USD"},
        {**FULL, "completed_by": "someone"},
        {k: v for k, v in FULL.items() if k != "counseling_completed"},
        {**FULL, "career_interest": "x" * 201},
        {**FULL, "remarks": "x" * 2001},
        {**FULL, "remarks": "bad\x00byte"},
    ],
    ids=["negative", "negative-cents", "over-max", "three-decimals", "nan", "unknown-currency", "currency-alone", "server-owned", "missing-completed", "career-long", "remarks-long", "nul"],
)
async def test_invalid_body_is_422_and_writes_nothing(db_session, agency, body):  # AC03; Review Focus 5
    async with client_for(agency["master"].email) as c:
        response = await c.put(url(agency["row"].id), json=body)
    assert response.status_code == 422
    assert await _records(db_session, agency["row"].id) == []


@pytest.mark.asyncio
async def test_amount_alone_is_inr_and_a_numeric_string_is_accepted(agency):  # AC03, AC12
    async with client_for(agency["master"].email) as c:
        response = await c.put(url(agency["row"].id), json={"counseling_completed": False, "budget_amount": "1500.5"})
    counseling = response.json()["student"]["counseling"]
    assert (counseling["budget_amount"], counseling["budget_currency"]) == ("1500.50", "INR")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "detail"),
    [("linked", "Counseling is recorded only for students without a login"), ("archived", "Unarchive this student first")],
)
async def test_login_or_archived_student_is_409(db_session, agency, target, detail):  # AC04
    async with client_for(agency["master"].email) as c:
        response = await c.put(url(agency[target].id), json=FULL)
    assert response.status_code == 409 and response.json()["detail"] == detail
    assert await _records(db_session, agency[target].id) == []


@pytest.mark.asyncio
async def test_completed_stamp_is_set_kept_and_cleared(db_session, agency):  # AC05
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c:
        first = (await c.put(url(sid), json=FULL)).json()["student"]["counseling"]
    async with client_for(agency["s1"]["user"].email) as c:
        kept = (await c.put(url(sid), json={**FULL, "remarks": "Staff follow-up"})).json()["student"]["counseling"]
        cleared = (await c.put(url(sid), json={**FULL, "counseling_completed": False})).json()["student"]["counseling"]
    assert first["completed_at"] and first["completed_by"] == agency["master"].full_name
    assert kept["completed_at"] == first["completed_at"] and kept["completed_by"] == agency["master"].full_name  # yes -> yes keeps
    assert kept["updated_by"] == "Couns One"
    assert cleared["completed_at"] is None and cleared["completed_by"] is None
    [record] = await _records(db_session, sid)
    assert record.completed_by_user_id is None


@pytest.mark.asyncio
async def test_audit_names_changed_fields_only_and_repeat_saves_write_none(db_session, agency):  # AC06; Review Focus 2
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c:
        assert (await c.put(url(sid), json=FULL)).status_code == 200
        assert (await c.put(url(sid), json=FULL)).status_code == 200  # identical: no-op
        same = {**FULL, "budget_amount": "2500000.00", "career_interest": "  Data science  "}  # equal after normalisation
        assert (await c.put(url(sid), json=same)).status_code == 200
        assert (await c.put(url(sid), json={**FULL, "remarks": "Changed remark 4417"})).status_code == 200
    audits = await _audits(db_session, sid)
    assert sorted((a.metadata_json for a in audits), key=lambda m: -len(m["fields"])) == [{"fields": sorted(FULL)}, {"fields": ["remarks"]}]
    blob = json.dumps([a.metadata_json for a in audits])
    assert "2500000" not in blob and "scholarship" not in blob and "4417" not in blob


@pytest.mark.asyncio
async def test_a_first_save_of_just_no_creates_the_record(db_session, agency):  # AC06, AC08
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c:
        counseling = (await c.put(url(sid), json={"counseling_completed": False})).json()["student"]["counseling"]
    assert counseling["counseling_completed"] is False and counseling["career_interest"] is None
    [audit] = await _audits(db_session, sid)
    assert audit.metadata_json == {"fields": ["counseling_completed"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["student", "super_admin", "suspended"])
async def test_non_agents_and_suspended_agencies_are_403(db_session, agency, who):  # AC07
    if who == "suspended":
        org = await db_session.get(AgentOrg, agency["org"].id, populate_existing=True)
        org.status = "suspended"
        await db_session.commit()
        email = agency["master"].email
    else:
        user = await mk_user(db_session, role="overseas_student" if who == "student" else "super_admin", division="overseas" if who == "student" else "global")
        email = user.email
    async with client_for(email) as c:
        response = await c.put(url(agency["row"].id), json=FULL)
    assert response.status_code == 403
    assert await _records(db_session, agency["row"].id) == []


@pytest.mark.asyncio
async def test_put_replaces_the_record_and_other_contracts_are_unchanged(agency):  # AC08
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c:
        before = (await c.get(f"{RECORDS}/{sid}")).json()["student"]
        await c.put(url(sid), json=FULL)
        replaced = (await c.put(url(sid), json={"counseling_completed": True})).json()["student"]["counseling"]
        listed = (await c.get(RECORDS, params={"q": "Asha Rao"})).json()["items"]
        patched = await c.patch(f"{RECORDS}/{sid}", json={"preferred_country": "Canada"})
    assert before["counseling"] is None
    assert replaced["counseling_completed"] is True
    assert (replaced["career_interest"], replaced["budget_amount"], replaced["budget_currency"], replaced["remarks"]) == (None, None, None, None)
    assert listed and all("counseling" not in item for item in listed)
    assert patched.status_code == 200
    body = patched.json()["student"]
    assert body["preferred_country"] == "Canada" and body["counseling"]["counseling_completed"] is True  # C3: separate fields


@pytest.mark.asyncio
async def test_the_record_exposes_no_ids(db_session, agency):  # AC12
    async with client_for(agency["master"].email) as c:
        counseling = (await c.put(url(agency["row"].id), json=FULL)).json()["student"]["counseling"]
    assert set(counseling) == COUNSELING_KEYS
    [record] = await _records(db_session, agency["row"].id)
    text = json.dumps(counseling)
    for value in (record.id, record.updated_by_user_id, record.completed_by_user_id):
        assert str(value) not in text


@pytest.mark.asyncio
async def test_two_first_saves_at_once_leave_one_record(db_session, agency):  # Review Focus 4
    sid = agency["row"].id
    async with client_for(agency["master"].email) as c1, client_for(agency["s1"]["user"].email) as c2:
        results = await asyncio.gather(c1.put(url(sid), json=FULL), c2.put(url(sid), json={**FULL, "remarks": "Other"}))
    assert [r.status_code for r in results] == [200, 200]
    assert len(await _records(db_session, sid)) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: API(`tests/test_agn_006_counseling.py`)
Expected: FAIL — the PUT answers `405 Method Not Allowed` (no route), and `before["counseling"]` raises `KeyError`.

- [ ] **Step 3: Implement the service**

In `apps/api/app/services/agent_students.py`:

1. Imports — `from datetime import UTC, datetime` is already there; change the models import to:

```python
from app.models import AgentOrgMember, AgentStudent, AgentStudentCounseling, OverseasApplication, User
```

2. In `record_detail`, add the key after `"updated_at": student.updated_at,`:

```python
        "counseling": await counseling_detail(db, student),
```

3. Insert this section immediately before `# --- duplicate warning (D7, F3, F4) ---`:

```python
# --- counseling record (AGN-006, DEC-SCOPE-047) -------------------------------------------------------------------------------------

COUNSELING_FIELDS = ("counseling_completed", "career_interest", "course_preference", "country_preference", "budget_amount", "budget_currency", "remarks")
Completer = aliased(User)
Updater = aliased(User)


async def counseling_detail(db: AsyncSession, row: AgentStudent) -> dict | None:
    """The student's counseling record or None. Found only through the already-scoped student row; an explicit allowlist -- the
    record's own id and every user id stay server-side, people are named. Money is a 2-decimal string (no float rounding)."""
    found = (
        await db.execute(
            select(AgentStudentCounseling, Completer.full_name, Updater.full_name)
            .outerjoin(Completer, Completer.id == AgentStudentCounseling.completed_by_user_id)
            .outerjoin(Updater, Updater.id == AgentStudentCounseling.updated_by_user_id)
            .where(AgentStudentCounseling.agent_student_id == row.id)
            .execution_options(populate_existing=True)
        )
    ).first()
    if found is None:
        return None
    record, completed_by, updated_by = found
    return {
        "counseling_completed": record.counseling_completed,
        "completed_at": record.completed_at,
        "completed_by": completed_by,
        "career_interest": record.career_interest,
        "course_preference": record.course_preference,
        "country_preference": record.country_preference,
        "budget_amount": None if record.budget_amount is None else f"{record.budget_amount:.2f}",
        "budget_currency": record.budget_currency,
        "remarks": record.remarks,
        "updated_at": record.updated_at,
        "updated_by": updated_by,
    }


async def save_counseling(db: AsyncSession, row: AgentStudent, user: User, data: dict) -> list[str]:
    """Replace the record (C1); no commit -- the router holds the organisation and student locks, audits and commits. Returns the
    sorted names of the fields whose value changed; a first save is never a no-op (`counseling_completed` plus every non-empty field).
    C5: stamped on the change to yes, kept while yes, cleared on no."""
    record = await db.scalar(select(AgentStudentCounseling).where(AgentStudentCounseling.agent_student_id == row.id))
    if record is None:
        record = AgentStudentCounseling(agent_student_id=row.id, updated_by_user_id=user.id)
        db.add(record)
        changed = ["counseling_completed", *(f for f in COUNSELING_FIELDS[1:] if data[f] is not None)]
    else:
        changed = [f for f in COUNSELING_FIELDS if getattr(record, f) != data[f]]
    for field in COUNSELING_FIELDS:
        setattr(record, field, data[field])
    if not data["counseling_completed"]:
        record.completed_at = record.completed_by_user_id = None
    elif record.completed_at is None:
        record.completed_at, record.completed_by_user_id = datetime.now(UTC), user.id
    if changed:
        record.updated_by_user_id = user.id
    return sorted(changed)
```

(`aliased` is already imported in this module for `Assignee`.)

- [ ] **Step 4: Implement the route**

In `apps/api/app/api/agent_students.py`:

1. Change the schemas import to:

```python
from app.schemas import AgentStudentAssign, AgentStudentCounselingSave, AgentStudentRecordCreate, AgentStudentRecordUpdate
```

2. Add `save_counseling,` to the `from app.services.agent_students import (...)` list (alphabetical, after `record_detail,`).

3. Append at the end of the module:

```python
@router.put("/{student_id}/counseling")
async def save_student_counseling(student_id: UUID, payload: AgentStudentCounselingSave, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-006 (DEC-SCOPE-047): replace the student's counseling record. Same locks and scope as an edit: out of scope is 404 before
    any other check; a student with a login or an archived student is 409. A save that changes nothing is 200 with no audit row."""
    membership = _gate(user)
    row = await _locked_row(db, user, membership, student_id)
    if row.student_id is not None:
        raise HTTPException(409, "Counseling is recorded only for students without a login")
    if row.status == "archived":
        raise HTTPException(409, "Unarchive this student first")
    changed = await save_counseling(db, row, user, payload.model_dump())
    if changed:
        _audit(db, user, "counseling", row.id, {"fields": changed})
    await db.commit()
    if changed:
        _log("agent_student_counseling_saved", membership, user, row.id, fields=changed)
    return {"student": await record_detail(db, row)}
```

- [ ] **Step 5: Add the matrix row**

In `apps/api/tests/test_agn_003_matrix.py`, in `BOTH_ALLOWED`, after the `("Edit Student", "patch", ...)` row add:

```python
    # AGN-006: §5 Step 2 counseling on an assigned student with no login -- Master and staff alike.
    ("Counseling", "put", RECORDS + "/{record}/counseling", {"counseling_completed": True}, 200),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: API(`tests/test_agn_006_counseling.py tests/test_agn_003_matrix.py`) and LINT(`app/services/agent_students.py app/api/agent_students.py tests/test_agn_006_counseling.py tests/test_agn_003_matrix.py`)
Expected: all PASS; ruff clean. If the concurrency test sees a 500 (`IntegrityError` on `uq_agent_student_counseling_student`), the
organisation lock is not being taken first — check `_locked_row` is used, never `load_scoped` directly.

- [ ] **Step 7: Run the AGN-004/005 regression set**

Run: API(`tests/test_agn_004_students.py tests/test_agn_004_student_actions.py tests/test_agn_004_staff_scope.py tests/test_agn_004_staff_guards.py tests/test_agn_004_schemas.py tests/test_agn_005_qa_fixes.py`)
Expected: all PASS (the detail gained one additive key; their key checks are supersets).

- [ ] **Step 8: Commit**

```powershell
git add apps/api/app/services/agent_students.py apps/api/app/api/agent_students.py apps/api/tests/test_agn_006_counseling.py apps/api/tests/test_agn_003_matrix.py
git commit -m "feat(agn-006): PUT counseling record and read-back on the student detail"
```

---

### Task 4: Staff Activity shows counseling saves (AC06, C7)

**Files:**
- Modify: `apps/api/app/services/staff_activity.py` (`STAFF_ACTIVITY_ACTIONS`, `_fields`)
- Modify: `apps/web/lib/agentStaff.ts` (`ACTIVITY_LABELS`)
- Modify: `apps/web/tests/components/AgentStaffActivity.test.tsx` (the `activityLabel` describe block)
- Test: `apps/api/tests/test_agn_006_activity.py`

**Interfaces:**
- Consumes: the PUT route (Task 3).
- Produces: activity items with `action == "agent_student.counseling"`, `fields` = changed names; `activityLabel("agent_student.counseling") === "Recorded counseling"`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_agn_006_activity.py`:

```python
"""AGN-006 -- a counseling save appears in the Master's Staff Activity with field names only (spec §5.6; DEC-SCOPE-047 C7; AC06)."""

import pytest

from tests.agn001_helpers import client_for, mk_active_org, uniq
from tests.agn002_helpers import STAFF, mk_staff
from tests.agn004_helpers import RECORDS, mk_record


@pytest.mark.asyncio
async def test_counseling_save_shows_field_names_and_no_values(db_session):
    ctx = await mk_active_org(db_session, name=f"Counseling Activity {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], full_name="Activity Counselor")
    row = await mk_record(db_session, agent=ctx["master"], full_name="Ravi Kumar", assigned_member=staff["member"])
    async with client_for(staff["user"].email) as s:
        saved = await s.put(f"{RECORDS}/{row.id}/counseling", json={"counseling_completed": True, "budget_amount": "4200000", "remarks": "Private remark 7731"})
    assert saved.status_code == 200, saved.text
    async with client_for(ctx["master"].email) as m:
        page = await m.get(f"{STAFF}/{staff['member'].id}/activity")
    assert page.status_code == 200
    [item] = page.json()["items"]
    assert (item["action"], item["subject"], item["fields"]) == ("agent_student.counseling", "Ravi Kumar", ["budget_amount", "budget_currency", "counseling_completed", "remarks"])
    assert "4200000" not in page.text and "7731" not in page.text
```

In `apps/web/tests/components/AgentStaffActivity.test.tsx`, inside `describe("activityLabel (AGN-021)", ...)`, add:

```tsx
  it("labels a counseling save (AGN-006)", () => {
    expect(activityLabel("agent_student.counseling")).toBe("Recorded counseling");
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: API(`tests/test_agn_006_activity.py`) — Expected: FAIL, `ValueError: not enough values to unpack (expected 1, got 0)` (the action is not on the allowlist).
Run: WEB(`tests/components/AgentStaffActivity.test.tsx`) — Expected: FAIL, received "Other activity".

- [ ] **Step 3: Implement**

In `apps/api/app/services/staff_activity.py`, add to `STAFF_ACTIVITY_ACTIONS` after `"agent_student.duplicate_override",`:

```python
    "agent_student.counseling",  # AGN-006 (DEC-SCOPE-047 C7): field names only, like an edit
```

and change `_fields`:

```python
def _fields(row: AuditLog) -> list[str] | None:
    """Edited field NAMES for an edit or a counseling save only (A3; AGN-006 C7); anything that is not a list of strings is dropped."""
    if row.action not in ("agent_student.update", "agent_student.counseling"):
        return None
```

(the rest of `_fields` is unchanged). Update the module docstring's A1 sentence only if it enumerates actions — it does not; leave it.

In `apps/web/lib/agentStaff.ts`, in `ACTIVITY_LABELS` after the `"agent_student.duplicate_override"` line:

```ts
  "agent_student.counseling": "Recorded counseling",
```

- [ ] **Step 4: Run tests to verify they pass, plus the AGN-021 regression**

Run: API(`tests/test_agn_006_activity.py tests/test_agn_021_activity.py`) and WEB(`tests/components/AgentStaffActivity.test.tsx`)
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/services/staff_activity.py apps/api/tests/test_agn_006_activity.py apps/web/lib/agentStaff.ts apps/web/tests/components/AgentStaffActivity.test.tsx
git commit -m "feat(agn-006): counseling saves in Staff Activity, field names only"
```

---

### Task 5: Web helpers (types, payload, validation, formatting)

**Files:**
- Modify: `apps/web/lib/agentStudents.ts` (type field on `AgentStudentDetail`; new section at the end)
- Test: `apps/web/tests/lib/agentStudentsCounseling.test.ts`

**Interfaces:**
- Produces (all exported from `@/lib/agentStudents`):
  - `type Currency = "INR" | "USD" | "GBP" | "EUR" | "CAD" | "AUD" | "NZD"`, `const CURRENCIES: readonly Currency[]`
  - `type Counseling = { counseling_completed: boolean; completed_at: string | null; completed_by: string | null; career_interest: string | null; course_preference: string | null; country_preference: string | null; budget_amount: string | null; budget_currency: Currency | null; remarks: string | null; updated_at: string; updated_by: string | null }`
  - `AgentStudentDetail.counseling?: Counseling | null`
  - `type CounselingValues = { counseling_completed: boolean; career_interest: string; course_preference: string; country_preference: string; budget_amount: string; budget_currency: Currency; remarks: string }`
  - `type CounselingField = keyof CounselingValues`
  - `counselingUrl(id: string): string`, `counselingValues(c?: Counseling | null): CounselingValues`,
    `counselingPayload(v: CounselingValues): Record<string, unknown>`, `validateCounseling(v: CounselingValues): Partial<Record<CounselingField, string>>`,
    `formatBudget(amount: string | null, currency: string | null): string`

- [ ] **Step 1: Write the failing test**

Create `apps/web/tests/lib/agentStudentsCounseling.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { counselingPayload, counselingUrl, counselingValues, CURRENCIES, formatBudget, validateCounseling, type Counseling } from "@/lib/agentStudents";

const record: Counseling = {
  counseling_completed: true, completed_at: "2026-10-01T09:00:00Z", completed_by: "Priya", career_interest: "Data science",
  course_preference: null, country_preference: "Ireland", budget_amount: "2500000.00", budget_currency: "USD", remarks: null,
  updated_at: "2026-10-01T09:00:00Z", updated_by: "Priya",
};

describe("counseling helpers (AGN-006)", () => {
  it("builds the sub-resource URL and lists the seven currencies", () => {
    expect(counselingUrl("s1")).toBe("/api/v1/workflows/overseas/agent/crm/students/s1/counseling");
    expect(CURRENCIES).toEqual(["INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD"]);
  });

  it("starts empty with INR when nothing is recorded, and from the record otherwise", () => {
    expect(counselingValues(null)).toEqual({ counseling_completed: false, career_interest: "", course_preference: "", country_preference: "", budget_amount: "", budget_currency: "INR", remarks: "" });
    expect(counselingValues(record)).toMatchObject({ counseling_completed: true, career_interest: "Data science", course_preference: "", budget_amount: "2500000.00", budget_currency: "USD" });
  });

  it("sends the whole record: trimmed text, blanks as null, amount as a string without grouping, currency only with an amount", () => {
    const values = { ...counselingValues(null), career_interest: "  Law ", budget_amount: "25,00,000", remarks: "  " };
    expect(counselingPayload(values)).toEqual({
      counseling_completed: false, career_interest: "Law", course_preference: null, country_preference: null,
      budget_amount: "2500000", budget_currency: "INR", remarks: null,
    });
    expect(counselingPayload({ ...values, budget_amount: "", budget_currency: "GBP" })).toMatchObject({ budget_amount: null, budget_currency: null });
  });

  it("refuses a negative, too large or too precise amount and over-long text", () => {
    const base = counselingValues(null);
    expect(validateCounseling({ ...base, budget_amount: "-5" })).toEqual({ budget_amount: "Budget cannot be negative" });
    expect(validateCounseling({ ...base, budget_amount: "100000000" }).budget_amount).toMatch(/up to 99,999,999.99/);
    expect(validateCounseling({ ...base, budget_amount: "10.123" }).budget_amount).toMatch(/at most 2 decimals/);
    expect(validateCounseling({ ...base, budget_amount: "abc" }).budget_amount).toBeTruthy();
    expect(validateCounseling({ ...base, country_preference: "x".repeat(121) })).toEqual({ country_preference: "Must be 120 characters or fewer" });
    expect(validateCounseling({ ...base, remarks: "x".repeat(2001) }).remarks).toBe("Must be 2000 characters or fewer");
    expect(validateCounseling({ ...base, budget_amount: "99,999,999.99" })).toEqual({});
  });

  it("formats a budget in its currency", () => {
    expect(formatBudget("2500000.00", "INR")).toBe("₹25,00,000.00");
    expect(formatBudget("1500.50", "USD")).toBe("US$1,500.50");
    expect(formatBudget(null, null)).toBe("—");
  });
});
```

(If the Node ICU in the web-test image prints `$1,500.50` for USD in `en-GB`, keep the implementation and adjust only that expected
string to what `new Intl.NumberFormat("en-GB", {style:"currency",currency:"USD"}).format(1500.5)` prints in that image — run it once
with `node -e` inside the container and record the value.)

- [ ] **Step 2: Run test to verify it fails**

Run: WEB(`tests/lib/agentStudentsCounseling.test.ts`)
Expected: FAIL — `counselingUrl is not a function` (not exported).

- [ ] **Step 3: Implement**

In `apps/web/lib/agentStudents.ts`, add to `AgentStudentDetail` after `updated_at: string;`:

```ts
  // AGN-006: always sent by the server; optional here so records built before AGN-006 (tests, fixtures) stay valid.
  counseling?: Counseling | null;
```

Append at the end of the file:

```ts
// AGN-006 (DEC-SCOPE-047): the counseling record (EVID-015 §5 Step 2), replaced whole by PUT …/counseling. Mirrors
// schemas.AgentStudentCounselingSave; the server remains the authority.
export const CURRENCIES = ["INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD"] as const;
export type Currency = (typeof CURRENCIES)[number];
export type Counseling = {
  counseling_completed: boolean;
  completed_at: string | null;
  completed_by: string | null;
  career_interest: string | null;
  course_preference: string | null;
  country_preference: string | null;
  budget_amount: string | null;
  budget_currency: Currency | null;
  remarks: string | null;
  updated_at: string;
  updated_by: string | null;
};
export type CounselingValues = {
  counseling_completed: boolean;
  career_interest: string;
  course_preference: string;
  country_preference: string;
  budget_amount: string;
  budget_currency: Currency;
  remarks: string;
};
export type CounselingField = keyof CounselingValues;

const COUNSELING_LIMITS = { career_interest: 200, course_preference: 200, country_preference: 120, remarks: NOTES_MAX } as const;
const AMOUNT = /^\d{1,8}(\.\d{1,2})?$/; // 0 to 99,999,999.99 with at most 2 decimals (the server's bounds)

export function counselingUrl(id: string): string {
  return `${RECORDS_URL}/${id}/counseling`;
}

export function counselingValues(c?: Counseling | null): CounselingValues {
  return {
    counseling_completed: c?.counseling_completed ?? false,
    career_interest: c?.career_interest ?? "",
    course_preference: c?.course_preference ?? "",
    country_preference: c?.country_preference ?? "",
    budget_amount: c?.budget_amount ?? "",
    budget_currency: c?.budget_currency ?? "INR",
    remarks: c?.remarks ?? "",
  };
}

// "25,00,000" and "2 500 000" are what people type; the server gets digits only.
function plainAmount(value: string): string {
  return value.replace(/[,\s]/g, "");
}

export function counselingPayload(v: CounselingValues): Record<string, unknown> {
  const text = (s: string) => s.trim() || null;
  const amount = plainAmount(v.budget_amount);
  return {
    counseling_completed: v.counseling_completed,
    career_interest: text(v.career_interest),
    course_preference: text(v.course_preference),
    country_preference: text(v.country_preference),
    budget_amount: amount || null, // a string: no float rounding on the way
    budget_currency: amount ? v.budget_currency : null,
    remarks: text(v.remarks),
  };
}

export function validateCounseling(v: CounselingValues): Partial<Record<CounselingField, string>> {
  const errors: Partial<Record<CounselingField, string>> = {};
  for (const [key, max] of Object.entries(COUNSELING_LIMITS) as [keyof typeof COUNSELING_LIMITS, number][]) {
    if (v[key].trim().length > max) errors[key] = `Must be ${max} characters or fewer`;
  }
  const amount = plainAmount(v.budget_amount);
  if (amount.startsWith("-")) errors.budget_amount = "Budget cannot be negative";
  else if (amount && !AMOUNT.test(amount)) errors.budget_amount = "Enter an amount up to 99,999,999.99 with at most 2 decimals";
  return errors;
}

export function formatBudget(amount: string | null, currency: string | null): string {
  if (amount === null || !currency) return "—";
  try {
    return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-GB", { style: "currency", currency }).format(Number(amount));
  } catch {
    return `${currency} ${amount}`;
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: WEB(`tests/lib/agentStudentsCounseling.test.ts tests/lib/agentStudents.test.ts`) and TSC
Expected: all PASS; `tsc` exits 0.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/lib/agentStudents.ts apps/web/tests/lib/agentStudentsCounseling.test.ts
git commit -m "feat(agn-006): web counseling types and helpers"
```

---

### Task 6: Counseling form component (AC10, form half)

**Files:**
- Create: `apps/web/components/AgentStudentCounselingForm.tsx`
- Test: `apps/web/tests/components/AgentStudentCounselingForm.test.tsx`

**Interfaces:**
- Consumes: Task 5 helpers; `detailMessage`, `NOT_COMPLETED` (`@/lib/apiErrors`); `refocus` (`@/lib/focus`).
- Produces: `export default function AgentStudentCounselingForm(props: { detail: AgentStudentDetail; onSaved: (s: AgentStudentDetail) => void; onCancel: () => void })`.
  Element ids: `counseling-{detail.id}-{field}` for each `CounselingField`, `counseling-{detail.id}-save`. Form accessible name:
  "Record counseling for {name}" (no record) / "Edit counseling for {name}". Buttons "Save counseling", "Cancel".

- [ ] **Step 1: Write the failing test**

Create `apps/web/tests/components/AgentStudentCounselingForm.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentCounselingForm from "@/components/AgentStudentCounselingForm";
import type { AgentStudentDetail, Counseling } from "@/lib/agentStudents";

const student: AgentStudentDetail = {
  id: "s1", has_login: false, full_name: "Asha", email: null, phone: null, preferred_country: null, preferred_intake: null, status: "active",
  assigned_to: null, created_at: "", date_of_birth: null, highest_qualification: null, institution: null, graduation_year: null,
  preferred_course: null, notes: null, created_by: "M", archived_at: null, archived_by: null, updated_at: "", counseling: null,
};
const recorded: Counseling = {
  counseling_completed: true, completed_at: "2026-10-01T09:00:00Z", completed_by: "Priya", career_interest: "Law", course_preference: null,
  country_preference: null, budget_amount: "1000.00", budget_currency: "INR", remarks: null, updated_at: "2026-10-01T09:00:00Z", updated_by: "Priya",
};
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const save = () => fireEvent.click(screen.getByRole("button", { name: "Save counseling" }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AgentStudentCounselingForm (AGN-006)", () => {
  it("names the form, opens on the checkbox and offers the seven currencies", () => {
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("form", { name: "Record counseling for Asha" })).toBeInTheDocument();
    expect(screen.getByLabelText("Counseling completed")).toHaveFocus();
    expect(screen.getByLabelText("Amount")).toHaveAttribute("inputmode", "decimal");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD"]);
  });

  it("refuses a negative budget without sending and focuses the amount", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={vi.fn()} />);
    type("Amount", "-500");
    save();
    expect(screen.getByText("Budget cannot be negative")).toBeInTheDocument();
    expect(screen.getByLabelText("Amount")).toHaveFocus();
    expect(screen.getByLabelText("Amount")).toHaveAttribute("aria-invalid", "true");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("closes without a request when nothing changed", () => {
    const fetchMock = vi.fn();
    const onCancel = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentCounselingForm detail={{ ...student, counseling: recorded }} onSaved={vi.fn()} onCancel={onCancel} />);
    expect(screen.getByRole("form", { name: "Edit counseling for Asha" })).toBeInTheDocument();
    save();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onCancel).toHaveBeenCalled();
  });

  it("PUTs the whole record and hands back the saved student", async () => {
    const savedStudent = { ...student, counseling: recorded };
    const fetchMock = vi.fn().mockResolvedValue(res({ student: savedStudent }));
    const onSaved = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentCounselingForm detail={student} onSaved={onSaved} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Counseling completed"));
    type("Career interest", "Law");
    type("Amount", "1,000");
    save();
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(savedStudent));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/workflows/overseas/agent/crm/students/s1/counseling");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ counseling_completed: true, career_interest: "Law", course_preference: null, country_preference: null, budget_amount: "1000", budget_currency: "INR", remarks: null });
  });

  it("puts a 422 on its field and a 409 or 404 in one alert", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(res({ detail: [{ loc: ["body", "career_interest"], msg: "Value error, must be 200 characters or fewer" }] }, 422))
      .mockResolvedValueOnce(res({ detail: "Unarchive this student first" }, 409))
      .mockResolvedValueOnce(res({ detail: "Student not found" }, 404));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={vi.fn()} />);
    type("Career interest", "Law");
    save();
    expect(await screen.findByText("Must be 200 characters or fewer")).toBeInTheDocument();
    expect(screen.getByLabelText("Career interest")).toHaveAttribute("aria-invalid", "true");
    type("Career interest", "Law again");
    save();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unarchive this student first");
    save();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Student not found"));
  });

  it("keeps the entry when the network drops", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={vi.fn()} />);
    type("Career interest", "Law");
    save();
    expect(await screen.findByRole("alert")).toHaveTextContent("The request did not complete");
    expect(screen.getByLabelText("Career interest")).toHaveValue("Law");
  });

  it("disables the form while saving and sends once on a double click", async () => {
    let resolve: (r: Response) => void = () => {};
    const fetchMock = vi.fn().mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={vi.fn()} />);
    type("Career interest", "Law");
    save();
    save();
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolve(res({ student }));
  });

  it("asks before cancelling unsaved changes", () => {
    const onCancel = vi.fn();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={onCancel} />);
    type("Remarks", "Draft");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("counts remarks characters", () => {
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={vi.fn()} />);
    type("Remarks", "Hello");
    expect(screen.getByText("5 / 2000")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: WEB(`tests/components/AgentStudentCounselingForm.test.tsx`)
Expected: FAIL — `Failed to resolve import "@/components/AgentStudentCounselingForm"`.

- [ ] **Step 3: Implement**

Create `apps/web/components/AgentStudentCounselingForm.tsx`:

```tsx
"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";
import {
  AgentStudentDetail,
  counselingPayload,
  counselingUrl,
  counselingValues,
  CounselingField,
  CounselingValues,
  CURRENCIES,
  Currency,
  NOTES_MAX,
  validateCounseling,
} from "@/lib/agentStudents";

// AGN-006 (DEC-SCOPE-047): record a student's counseling outcome (EVID-015 §5 Step 2). The whole record is sent (PUT); the server
// stamps who completed it and when. Validation mirrors the server's schema; the server remains the authority.
const TEXT_FIELDS: { key: "career_interest" | "course_preference" | "country_preference"; label: string }[] = [
  { key: "career_interest", label: "Career interest" },
  { key: "course_preference", label: "Course preference" },
  { key: "country_preference", label: "Country preference" },
];
const FOCUS_ORDER: CounselingField[] = ["counseling_completed", "career_interest", "course_preference", "country_preference", "budget_amount", "budget_currency", "remarks"];
const LEAVE_PROMPT = "You have unsaved counseling changes. Leave without saving?";

// FastAPI's 422 list -> {field: message} for this form's fields, or null when any error is not one of them (then the whole detail is
// shown as one message, so nothing is hidden) -- the AgentStudentForm rule.
function fieldErrors(detail: unknown): Partial<Record<CounselingField, string>> | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const out: Partial<Record<CounselingField, string>> = {};
  for (const item of detail as { loc?: unknown[] }[]) {
    const field = item?.loc?.[item.loc.length - 1];
    if (typeof field !== "string" || !FOCUS_ORDER.includes(field as CounselingField)) return null;
    out[field as CounselingField] = detailMessage([item]);
  }
  return out;
}

export default function AgentStudentCounselingForm({
  detail,
  onSaved,
  onCancel,
}: {
  detail: AgentStudentDetail;
  onSaved: (s: AgentStudentDetail) => void;
  onCancel: () => void;
}) {
  const original = useRef<CounselingValues>(counselingValues(detail.counseling));
  const [values, setValues] = useState<CounselingValues>(original.current);
  const [errors, setErrors] = useState<Partial<Record<CounselingField, string>>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const idPrefix = `counseling-${detail.id}`;
  const dirty = JSON.stringify(counselingPayload(values)) !== JSON.stringify(counselingPayload(original.current));

  useEffect(() => {
    document.getElementById(`${idPrefix}-counseling_completed`)?.focus();
  }, [idPrefix]);

  // Leave prompt while there is unsaved input (C9; AgentStudentForm's pattern, browser QA-03): beforeunload covers reload/close; an
  // in-app link navigates client-side, so ask first -- capture phase runs before Next's Link handler.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const guardLinks = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = (event.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!link || link.target === "_blank" || link.hasAttribute("download") || link.origin !== window.location.origin) return;
      if (!window.confirm(LEAVE_PROMPT)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", guardLinks, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", guardLinks, true);
    };
  }, [dirty]);

  function set<K extends CounselingField>(key: K, value: CounselingValues[K]) {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => ({ ...e, [key]: undefined }));
  }

  function cancel() {
    if (dirty && !window.confirm(LEAVE_PROMPT)) return;
    onCancel();
  }

  function focusFirst(found: Partial<Record<CounselingField, string>>): boolean {
    const first = FOCUS_ORDER.find((key) => found[key]);
    if (first) document.getElementById(`${idPrefix}-${first}`)?.focus();
    return Boolean(first);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const found = validateCounseling(values);
    setErrors(found);
    if (focusFirst(found)) return;
    if (!dirty) {
      onCancel();
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    try {
      const response = await fetch(counselingUrl(detail.id), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(counselingPayload(values)),
      });
      const body = await response.json().catch(() => null);
      if (response.ok && body?.student) {
        onSaved(body.student as AgentStudentDetail);
        return;
      }
      const onFields = response.status === 422 ? fieldErrors(body?.detail) : null;
      if (onFields) {
        setErrors(onFields);
        requestAnimationFrame(() => focusFirst(onFields));
      } else {
        setFailure(detailMessage(body?.detail, "Unable to save counseling."));
        refocus(`${idPrefix}-save`);
      }
    } catch {
      setFailure(NOT_COMPLETED);
      refocus(`${idPrefix}-save`);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const describedBy = (key: CounselingField, extra?: string) => [errors[key] ? `${idPrefix}-${key}-error` : null, extra].filter(Boolean).join(" ") || undefined;
  const error = (key: CounselingField) =>
    errors[key] ? (
      <p className="form-error" id={`${idPrefix}-${key}-error`}>
        {errors[key]}
      </p>
    ) : null;

  return (
    <form className="form" onSubmit={submit} aria-busy={busy} noValidate aria-labelledby={`${idPrefix}-title`}>
      <h5 id={`${idPrefix}-title`}>
        {detail.counseling ? "Edit counseling" : "Record counseling"} for {detail.full_name}
      </h5>
      <fieldset className="form-busy-wrap" disabled={busy}>
        <label className="pf-check" htmlFor={`${idPrefix}-counseling_completed`}>
          <input
            id={`${idPrefix}-counseling_completed`}
            type="checkbox"
            checked={values.counseling_completed}
            onChange={(e) => set("counseling_completed", e.target.checked)}
          />
          Counseling completed
        </label>
        {TEXT_FIELDS.map((f) => (
          <div className="field" key={f.key}>
            <label htmlFor={`${idPrefix}-${f.key}`}>{f.label}</label>
            <input
              id={`${idPrefix}-${f.key}`}
              type="text"
              value={values[f.key]}
              aria-invalid={errors[f.key] ? true : undefined}
              aria-describedby={describedBy(f.key)}
              onChange={(e) => set(f.key, e.target.value)}
            />
            {error(f.key)}
          </div>
        ))}
        <fieldset>
          <legend>Budget</legend>
          <p className="muted field-help" id={`${idPrefix}-budget-help`}>
            Leave the amount empty if no budget was discussed.
          </p>
          <div className="form-grid">
            <div className="field">
              <label htmlFor={`${idPrefix}-budget_amount`}>Amount</label>
              <input
                id={`${idPrefix}-budget_amount`}
                type="text"
                inputMode="decimal"
                autoComplete="off"
                value={values.budget_amount}
                aria-invalid={errors.budget_amount ? true : undefined}
                aria-describedby={describedBy("budget_amount", `${idPrefix}-budget-help`)}
                onChange={(e) => set("budget_amount", e.target.value)}
              />
              {error("budget_amount")}
            </div>
            <div className="field">
              <label htmlFor={`${idPrefix}-budget_currency`}>Currency</label>
              <select
                id={`${idPrefix}-budget_currency`}
                value={values.budget_currency}
                aria-invalid={errors.budget_currency ? true : undefined}
                aria-describedby={describedBy("budget_currency")}
                onChange={(e) => set("budget_currency", e.target.value as Currency)}
              >
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              {error("budget_currency")}
            </div>
          </div>
        </fieldset>
        <div className="field">
          <label htmlFor={`${idPrefix}-remarks`}>Remarks</label>
          <textarea
            id={`${idPrefix}-remarks`}
            rows={4}
            value={values.remarks}
            aria-invalid={errors.remarks ? true : undefined}
            aria-describedby={describedBy("remarks", `${idPrefix}-remarks-count`)}
            onChange={(e) => set("remarks", e.target.value)}
          />
          <p className="muted field-help" id={`${idPrefix}-remarks-count`}>
            {values.remarks.length} / {NOTES_MAX}
          </p>
          {error("remarks")}
        </div>
        {failure && (
          <p className="form-error" role="alert">
            {failure}
          </p>
        )}
        <div>
          <button id={`${idPrefix}-save`} type="submit" className="btn small">
            {busy ? "Saving…" : "Save counseling"}
          </button>{" "}
          <button type="button" className="btn secondary small" onClick={cancel}>
            Cancel
          </button>
        </div>
      </fieldset>
    </form>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: WEB(`tests/components/AgentStudentCounselingForm.test.tsx`) and TSC
Expected: 9 passed; `tsc` exits 0. If the 422 test fails because the 422 message reads "Must be 200 characters or fewer" vs the
server's "must be …", note `detailMessage` capitalises the first letter (that is the expected text).

- [ ] **Step 5: Commit**

```powershell
git add apps/web/components/AgentStudentCounselingForm.tsx apps/web/tests/components/AgentStudentCounselingForm.test.tsx
git commit -m "feat(agn-006): counseling form"
```

---

### Task 7: Counseling card in the detail panel (AC10, view half)

**Files:**
- Create: `apps/web/components/AgentStudentCounselingCard.tsx`
- Modify: `apps/web/components/AgentStudentDetailPanel.tsx` (state, Escape, render)
- Modify: `apps/web/components/AgentStudentsPanel.tsx:298-301` (the `onSaved` callback)
- Test: `apps/web/tests/components/AgentStudentCounselingCard.test.tsx`

**Interfaces:**
- Consumes: `AgentStudentCounselingForm` (Task 6), `formatBudget` (Task 5), `formatDate` (`@/lib/formatDate`), `refocus`.
- Produces: `export default function AgentStudentCounselingCard(props: { detail: AgentStudentDetail; editing: boolean; onEditingChange: (open: boolean) => void; onSaved: (s: AgentStudentDetail) => void })`;
  `AgentStudentDetailPanel` prop `onSaved: (s: AgentStudentDetail, notice?: string) => void` (the notice for a counseling save is
  `Counseling saved for {name}.`).

- [ ] **Step 1: Write the failing test**

Create `apps/web/tests/components/AgentStudentCounselingCard.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentDetailPanel from "@/components/AgentStudentDetailPanel";
import type { AgentStudentDetail, Counseling } from "@/lib/agentStudents";

const base: AgentStudentDetail = {
  id: "s1", has_login: false, full_name: "Asha", email: null, phone: null, preferred_country: "Canada", preferred_intake: null, status: "active",
  assigned_to: null, created_at: "", date_of_birth: null, highest_qualification: null, institution: null, graduation_year: null,
  preferred_course: null, notes: null, created_by: "M", archived_at: null, archived_by: null, updated_at: "", counseling: null,
};
const recorded: Counseling = {
  counseling_completed: true, completed_at: "2026-10-01T09:00:00Z", completed_by: "Priya", career_interest: "Law", course_preference: "LLM",
  country_preference: "Ireland", budget_amount: "2500000.00", budget_currency: "INR", remarks: "<script>alert(1)</script>\nSecond line",
  updated_at: "2026-10-01T09:00:00Z", updated_by: "Priya",
};
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const counselingRegion = () => screen.getByRole("region", { name: "Counseling" });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Counseling in the student detail panel (AGN-006)", () => {
  it("says when nothing is recorded and offers to record it", () => {
    render(<AgentStudentDetailPanel detail={base} onClose={vi.fn()} onSaved={vi.fn()} />);
    const region = counselingRegion();
    expect(within(region).getByText("Counseling not recorded yet.")).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: "Record counseling" })).toBeInTheDocument();
  });

  it("shows the record in words, formats the budget and renders remarks as text", () => {
    render(<AgentStudentDetailPanel detail={{ ...base, counseling: recorded }} onClose={vi.fn()} onSaved={vi.fn()} />);
    const region = counselingRegion();
    expect(within(region).getByText(/^Yes — 01 Oct 2026, by Priya$/)).toBeInTheDocument();
    expect(within(region).getByText("₹25,00,000.00")).toBeInTheDocument();
    expect(within(region).getByText("Ireland")).toBeInTheDocument();
    expect(within(region).getByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(within(region).getByRole("button", { name: "Edit counseling" })).toBeInTheDocument();
  });

  it("offers no counseling action for a student with a login or an archived student", () => {
    const { unmount } = render(<AgentStudentDetailPanel detail={{ ...base, has_login: true }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(within(counselingRegion()).getByText("Counseling is recorded only for students without a login.")).toBeInTheDocument();
    expect(within(counselingRegion()).queryByRole("button")).toBeNull();
    unmount();
    render(<AgentStudentDetailPanel detail={{ ...base, status: "archived", counseling: recorded }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(within(counselingRegion()).queryByRole("button")).toBeNull();
    expect(within(counselingRegion()).getByText("Law")).toBeInTheDocument();
  });

  it("keeps one form open at a time and Escape does not close the panel while one is open", async () => {
    const onClose = vi.fn();
    render(<AgentStudentDetailPanel detail={base} onClose={onClose} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Record counseling" }));
    expect(screen.getByRole("form", { name: "Record counseling for Asha" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Close" })).toBeNull();
    fireEvent.keyDown(screen.getByRole("region", { name: "Asha" }), { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Record counseling" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.queryByRole("button", { name: "Record counseling" })).toBeNull();
  });

  it("after a save shows the new record, reports it through the list notice and focuses the Counseling heading", async () => {
    const saved = { ...base, counseling: recorded };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ student: saved })));
    const onSaved = vi.fn();
    const { rerender } = render(<AgentStudentDetailPanel detail={base} onClose={vi.fn()} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole("button", { name: "Record counseling" }));
    fireEvent.change(screen.getByLabelText("Career interest"), { target: { value: "Law" } });
    fireEvent.click(screen.getByRole("button", { name: "Save counseling" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved, "Counseling saved for Asha."));
    rerender(<AgentStudentDetailPanel detail={saved} onClose={vi.fn()} onSaved={onSaved} />);
    expect(within(counselingRegion()).getByText("LLM")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("heading", { name: "Counseling" })).toHaveFocus());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: WEB(`tests/components/AgentStudentCounselingCard.test.tsx`)
Expected: FAIL — `Unable to find role="region" and name "Counseling"`.

- [ ] **Step 3: Implement the card**

Create `apps/web/components/AgentStudentCounselingCard.tsx`:

```tsx
"use client";

import AgentStudentCounselingForm from "./AgentStudentCounselingForm";
import { refocus } from "@/lib/focus";
import { formatDate } from "@/lib/formatDate";
import { AgentStudentDetail, formatBudget } from "@/lib/agentStudents";

function stamp(at: string | null, by: string | null): string {
  return [at ? formatDate(at) : null, by ? `by ${by}` : null].filter(Boolean).join(", ");
}

// AGN-006 (DEC-SCOPE-047): the student's counseling record (EVID-015 §5 Step 2) under the AGN-004 details. It arrives with the
// detail -- no fetch of its own. Recorded only for an active student with no login (C4); everything is rendered as text.
export default function AgentStudentCounselingCard({
  detail,
  editing,
  onEditingChange,
  onSaved,
}: {
  detail: AgentStudentDetail;
  editing: boolean;
  onEditingChange: (open: boolean) => void;
  onSaved: (s: AgentStudentDetail) => void;
}) {
  const c = detail.counseling ?? null;
  const headingId = `counseling-heading-${detail.id}`;
  const openerId = `counseling-open-${detail.id}`;
  const editable = !detail.has_login && detail.status === "active";

  const rows: [string, string | null][] = c
    ? [
        ["Counseling completed", c.counseling_completed ? `Yes — ${stamp(c.completed_at, c.completed_by)}` : "No"],
        ["Career interest", c.career_interest],
        ["Course preference", c.course_preference],
        ["Country preference", c.country_preference],
        ["Budget", c.budget_amount === null ? null : formatBudget(c.budget_amount, c.budget_currency)],
        ["Remarks", c.remarks],
        ["Last updated", stamp(c.updated_at, c.updated_by)],
      ]
    : [];

  return (
    <section aria-labelledby={headingId} style={{ marginTop: 16 }}>
      <h5 id={headingId} tabIndex={-1}>
        Counseling
      </h5>
      {editing ? (
        <AgentStudentCounselingForm
          detail={detail}
          onCancel={() => {
            onEditingChange(false);
            refocus(openerId);
          }}
          onSaved={(s) => {
            onEditingChange(false);
            onSaved(s);
            refocus(headingId);
          }}
        />
      ) : (
        <>
          {c ? (
            <dl className="record-details">
              {rows.map(([label, value]) => (
                <div key={label} style={{ display: "contents" }}>
                  <dt>{label}</dt>
                  <dd style={label === "Remarks" ? { whiteSpace: "pre-wrap" } : undefined}>{value === null || value === "" ? "—" : value}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="muted">{detail.has_login ? "Counseling is recorded only for students without a login." : "Counseling not recorded yet."}</p>
          )}
          {editable && (
            <button id={openerId} type="button" className="btn small" onClick={() => onEditingChange(true)}>
              {c ? "Edit counseling" : "Record counseling"}
            </button>
          )}
        </>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Wire it into the detail panel**

In `apps/web/components/AgentStudentDetailPanel.tsx`:

1. Add the import after `import AgentStudentForm from "./AgentStudentForm";`:

```tsx
import AgentStudentCounselingCard from "./AgentStudentCounselingCard";
```

2. Change the `onSaved` prop type to `onSaved: (s: AgentStudentDetail, notice?: string) => void;` and the state line to:

```tsx
  // One form at a time (AGN-006): the Step 1 edit replaces the details; counseling edits inside its own section.
  const [editing, setEditing] = useState<"none" | "student" | "counseling">("none");
```

3. Escape: `if (e.key === "Escape" && editing === "none") onClose();`

4. Replace the body from `{editing ? (` to the end of that conditional with:

```tsx
      {editing === "student" ? (
        <AgentStudentForm
          mode="edit"
          student={detail}
          onCancel={() => setEditing("none")}
          onSaved={(s) => {
            setEditing("none");
            onSaved(s);
            // The form (and its focused Save button) unmounts: put keyboard focus back on this record.
            requestAnimationFrame(() => document.getElementById(headingId)?.focus());
          }}
        />
      ) : (
        <>
          <dl className="record-details">
            {rows.map(([label, value]) => (
              <div key={label} style={{ display: "contents" }}>
                <dt>{label}</dt>
                <dd style={label === "Notes" ? { whiteSpace: "pre-wrap" } : undefined}>{value === null || value === "" ? "—" : value}</dd>
              </div>
            ))}
          </dl>
          {editing === "none" && !detail.has_login && detail.status === "active" && (
            <button type="button" className="btn small" onClick={() => setEditing("student")}>
              Edit
            </button>
          )}
          <AgentStudentCounselingCard
            detail={detail}
            editing={editing === "counseling"}
            onEditingChange={(open) => setEditing(open ? "counseling" : "none")}
            onSaved={(s) => onSaved(s, `Counseling saved for ${s.full_name}.`)}
          />
          {editing === "none" && (
            <button type="button" className="btn secondary small" onClick={onClose} style={{ marginTop: 16 }}>
              Close
            </button>
          )}
        </>
      )}
```

(The counseling card hides its own "Record/Edit counseling" button only implicitly — it is not rendered while the student form is
open, because the whole view branch is replaced. Inline `style` follows the panel's existing inline styles; no CSS file changes.)

5. In `apps/web/components/AgentStudentsPanel.tsx`, change the `onSaved` callback (lines ~298–301) to:

```tsx
          onSaved={(s, notice) => {
            setNotice(notice ?? `${s.full_name} saved.`);
            applyUpdate(s);
          }}
```

- [ ] **Step 5: Run tests to verify they pass, plus the panel regression**

Run: WEB(`tests/components/AgentStudentCounselingCard.test.tsx tests/components/AgentStudentCounselingForm.test.tsx tests/components/AgentStudentsPanel.test.tsx tests/components/AgentStudentForm.test.tsx tests/components/AgentStudentsSection.test.tsx tests/components/AgentStudentAssign.test.tsx`) and TSC
Expected: all PASS; `tsc` exits 0. `AgentStudentsPanel.test.tsx` "opens the detail panel, and Escape closes it" must still pass
unchanged (no form open → Escape closes).

- [ ] **Step 6: Commit**

```powershell
git add apps/web/components/AgentStudentCounselingCard.tsx apps/web/components/AgentStudentDetailPanel.tsx apps/web/components/AgentStudentsPanel.tsx apps/web/tests/components/AgentStudentCounselingCard.test.tsx
git commit -m "feat(agn-006): counseling section in the agency student detail panel"
```

---

### Task 8: Browser test and the lite regression run (AC11)

**Files:**
- Create: `apps/web/tests/e2e/agn-006-counseling.spec.ts`

**Interfaces:**
- Consumes: the running E2E stack (the owner starts it), the seeded demo agent `agent@edusphere.local` / `Demo@123`.

- [ ] **Step 1: Write the browser test**

Create `apps/web/tests/e2e/agn-006-counseling.spec.ts`:

```ts
import { expect, test, type Page } from "@playwright/test";

// AGN-006 -- a Master records a student's counseling, reloads and reads it back; a negative budget is refused on the field; the form
// works at 320 px. Unique names per run: the E2E database is shared and keeps rows.

const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

async function signInAsDemoAgent(page: Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "agent@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/agent/dashboard");
}

async function openNewStudent(page: Page, name: string) {
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  await form.getByRole("button", { name: "Save student" }).click();
  await expect(page.getByText(`${name} added.`)).toBeVisible();
  const students = page.getByRole("list", { name: "Students" });
  await page.getByLabel("Search students").fill(name);
  await expect(students.getByRole("listitem")).toHaveCount(1);
  await expect(page.getByRole("region", { name: "Student list" })).toHaveAttribute("aria-busy", "false");
  await students.getByRole("button", { name: `View ${name}`, exact: true }).click();
  return page.getByRole("region", { name, exact: true });
}

test("a Master records counseling and reads it back after a reload (AGN-006-AC01/AC11)", async ({ page }) => {
  const name = `E2E Counseling ${stamp()}`;
  await signInAsDemoAgent(page);
  let detail = await openNewStudent(page, name);
  const counseling = detail.getByRole("region", { name: "Counseling" });
  await expect(counseling.getByText("Counseling not recorded yet.")).toBeVisible();
  await counseling.getByRole("button", { name: "Record counseling" }).click();

  await counseling.getByLabel("Amount").fill("-500");
  await counseling.getByRole("button", { name: "Save counseling" }).click();
  await expect(counseling.getByText("Budget cannot be negative")).toBeVisible();
  await expect(counseling.getByLabel("Amount")).toBeFocused();

  await counseling.getByLabel("Counseling completed").check();
  await counseling.getByLabel("Career interest").fill("Data science");
  await counseling.getByLabel("Course preference").fill("MSc Data Science");
  await counseling.getByLabel("Country preference").fill("Ireland");
  await counseling.getByLabel("Amount").fill("25,00,000");
  await counseling.getByLabel("Remarks").fill("Needs scholarship options.");
  await counseling.getByRole("button", { name: "Save counseling" }).click();
  await expect(page.getByText(`Counseling saved for ${name}.`)).toBeVisible();

  await page.reload();
  detail = await (async () => {
    const students = page.getByRole("list", { name: "Students" });
    await page.getByLabel("Search students").fill(name);
    await expect(students.getByRole("listitem")).toHaveCount(1);
    await students.getByRole("button", { name: `View ${name}`, exact: true }).click();
    return page.getByRole("region", { name, exact: true });
  })();
  const after = detail.getByRole("region", { name: "Counseling" });
  await expect(after.getByText(/^Yes — /)).toBeVisible();
  await expect(after.getByText("₹25,00,000.00")).toBeVisible();
  await expect(after.getByText("MSc Data Science")).toBeVisible();
  await expect(after.getByText("Needs scholarship options.")).toBeVisible();
});

test("the counseling form fits a 320 px phone with no horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  const name = `E2E Phone ${stamp()}`;
  await signInAsDemoAgent(page);
  const detail = await openNewStudent(page, name);
  await detail.getByRole("button", { name: "Record counseling" }).click();
  await expect(detail.getByLabel("Amount")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
```

- [ ] **Step 2: Ask the owner to start the E2E stack, then run it**

Ask the owner to bring up the E2E stack (as for AGN-004/005) with this branch's code and migrations applied. Then run, from `apps/web`:
`npx playwright test tests/e2e/agn-006-counseling.spec.ts tests/e2e/agn-004-agent-students.spec.ts`
Expected: all PASS. On a failure, open only that test's trace/screenshot.

- [ ] **Step 3: Run the lite backend set**

Run: API(`tests/test_agn_006_migration.py tests/test_agn_006_schemas.py tests/test_agn_006_counseling.py tests/test_agn_006_activity.py tests/test_agn_003_matrix.py tests/test_agn_003_verify.py tests/test_agn_004_migration.py tests/test_agn_004_schema.py tests/test_agn_004_schemas.py tests/test_agn_004_staff_guards.py tests/test_agn_004_staff_scope.py tests/test_agn_004_student_actions.py tests/test_agn_004_students.py tests/test_agn_005_qa_fixes.py tests/test_agn_021_activity.py`)
and LINT(`app tests/test_agn_006_migration.py tests/test_agn_006_schemas.py tests/test_agn_006_counseling.py tests/test_agn_006_activity.py`).
Expected: all PASS; ruff clean. Record the exact counts for the completion report. The full backend suite is NOT run (owner's standing choice).

- [ ] **Step 4: Run the web unit suite and build checks**

Run: WEB(`tests/components/AgentStudent* tests/components/AgentStaffActivity.test.tsx tests/lib/agentStudents.test.ts tests/lib/agentStudentsCounseling.test.ts`), TSC, and
`dc run --rm --no-deps -v "${WEB}/components:/app/components" -v "${WEB}/lib:/app/lib" -v "${WEB}/tests:/app/tests" -v "${WEB}/app:/app/app" web-test npx eslint components/AgentStudentCounselingCard.tsx components/AgentStudentCounselingForm.tsx components/AgentStudentDetailPanel.tsx lib/agentStudents.ts tests/e2e/agn-006-counseling.spec.ts`
Expected: all PASS, `tsc` 0, eslint 0 problems.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/tests/e2e/agn-006-counseling.spec.ts
git commit -m "test(agn-006): browser test for recording counseling"
```

---

### Task 9: Documentation and traceability

**Files:**
- Modify: `docs/delivery/ENHANCEMENT_BACKLOG.md`, `docs/decisions/PRODUCT_DECISION_REGISTER.md`, `docs/architecture/API_CONTRACT.md`,
  `docs/architecture/DATA_MODEL.md`, `docs/architecture/RBAC_MATRIX.md`, `docs/quality/RTM.md`, `docs/product/PRD_OPEN_ITEMS.md`

- [ ] **Step 1: Recheck main for the decision number**

Run: `git fetch origin` and `git show origin/main:docs/decisions/PRODUCT_DECISION_REGISTER.md | Select-String "DEC-SCOPE-04[7-9]"`.
Expected: no `DEC-SCOPE-047`. If taken, use the next free number everywhere below and in the spec header.

- [ ] **Step 2: Decision register** — append after the `DEC-SCOPE-046` entry, in its format:

```markdown
### DEC-SCOPE-047 — Agent student counseling record (`AGN-006`)

**ID note:** provisional; `AGN-007` (university shortlist) may land a decision first — renumber on merge if so.

**Question:** the owner's `AGN-006` statement (in-session, 2026-10-01): requirement **"record counseling completed, career interest, course preference, country preference, budget and remarks"**; acceptance criteria: **save and read back the record; a negative budget → 422; out-of-scope → 404.** How is the record stored, what is the budget, who may write it, for which students, and is it shown in Staff Activity?

**Evidence:** `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §5 "Staff Student Journey", STEP 2 "Counseling" (the source's wording is not the approval). Design spec `docs/superpowers/specs/2026-10-01-agn-006-counseling-record-design.md`.

**Resolution:** owner, in-session 2026-10-01 (`EXPLICIT_APPROVAL` — the owner's answers, not the source document's wording):

- **C1 — One record per student;** a save overwrites it; history is the audit log.
- **C2 — Budget** = amount + currency (INR default, USD, GBP, EUR, CAD, AUD, NZD); 0 ≤ amount ≤ 99,999,999.99, ≤ 2 decimals; otherwise 422.
- **C3 — Separate preferences:** counseling course/country preference are new fields; Step 1 `preferred_course` / `preferred_country` are untouched.
- **C4 — Access:** the agency Master and the assigned staff member; students with no login only (login or archived → 409; out of scope → 404).
- **C5 — Completed:** yes/no; the server stamps when and by whom on the change to yes, keeps it while yes, clears it on no.
- **C6 — API:** `PUT …/crm/students/{id}/counseling`; read back as `counseling` in the student detail; the AGN-004 PATCH is unchanged.
- **C7 — Staff Activity:** new audit action `agent_student.counseling`, field names only (amends `DEC-SCOPE-046` A1 by one action).
- **C8 — Storage:** a separate one-to-one table `agent_student_counseling`.
- **C9 — Leave prompt** on unsaved counseling changes.

**Consequences:** migration `0054_agent_student_counseling` (create-table only; downgrade refuses while records exist); new route; additive `counseling` key on every student-detail response; Staff Activity allowlist +1; no rate limit added (residual, as AGN-004 writes). §5 Step 2 leaves `EVID-015`'s parked list.
```

- [ ] **Step 3: Backlog** — in `docs/delivery/ENHANCEMENT_BACKLOG.md`:
  - summary table, after the `AGN-005` row: `| AGN-006 | Agent student counseling record — completed, career interest, course/country preference, budget, remarks (§5 Step 2) | Medium | Medium | Yes | AGN-004 (detail), AGN-021 (activity) |`
  - decisions appendix table, after the `AGN-005` row: `| AGN-006 | \`DEC-SCOPE-047\` — storage, budget, access, completed stamp, API, activity | **Resolved 2026-10-01** (C1–C9, \`EXPLICIT_APPROVAL\` in-session; number provisional) |`
  - the `Agent CRM Functionalities.md` row (Appendix B): add "§5 Step 2 counseling moved out to AGN-006 (`DEC-SCOPE-047`)." to the moved-out list and `DEC-SCOPE-047 covers AGN-006` to the decisions cell.
  - a `## AGN-006 — Agent Student Counseling Record` section after `## AGN-005`, in the AGN-021 section's format: business requirement (the owner's statement), source (`EVID-015` §5 Step 2), decision (`DEC-SCOPE-047`), expected behaviour (spec §1/§5/§6 in five bullets), AC01–AC12 copied verbatim from spec §7, status "IMPLEMENTED, NOT COMPLETE — browser QA and independent review pending".

- [ ] **Step 4: API contract** — in `docs/architecture/API_CONTRACT.md`, after the AGN-004 `/crm/students` rows add:

```markdown
| `PUT /workflows/overseas/agent/crm/students/{id}/counseling` | Authenticated | Agent (Master or assigned staff) of an active organisation; **not** `super_admin` (`403`) | AGN-006 / `DEC-SCOPE-047`. Body (all keys; `extra` → `422`): `counseling_completed` (required bool), `career_interest` ≤ 200, `course_preference` ≤ 200, `country_preference` ≤ 120, `remarks` ≤ 2000 (trimmed, blank → null), `budget_amount` number or numeric string 0–99,999,999.99 ≤ 2 dp, `budget_currency` INR\|USD\|GBP\|EUR\|CAD\|AUD\|NZD (defaults INR with an amount; alone → `422`). Replaces the whole record (omitted optional = null); idempotent. Out of scope / unknown → `404 Student not found` (before any other check); student with a login → `409`; archived → `409 Unarchive this student first`. `200 {student}`; a save that changes nothing is `200` with no audit row. |
```

  and, on each existing AGN-004 detail-returning row (create, get, patch, archive, unarchive, assign), append: "Detail also carries `counseling: null | {counseling_completed, completed_at, completed_by, career_interest, course_preference, country_preference, budget_amount (2-dp string), budget_currency, remarks, updated_at, updated_by}` (AGN-006; names, never ids)."

- [ ] **Step 5: Data model** — in `docs/architecture/DATA_MODEL.md`, after the AGN-004 `agent_students` addendum add an
  "**Addendum, 2026-10-01 (`AGN-006` / `DEC-SCOPE-047` — `agent_student_counseling`)**" paragraph: the column table from spec §4, the four
  check constraints and the unique key, "migration `0054_agent_student_counseling` is create-table only; downgrade refuses while any record
  exists (verified: upgrade → downgrade → upgrade, single head)", retention "lives and dies with the student row".

- [ ] **Step 6: RBAC matrix** — in `docs/architecture/RBAC_MATRIX.md`, in the agent student-records section add a row: "Record counseling
  (§5 Step 2, AGN-006): Master ✓ whole agency; Staff ✓ assigned students only; students with a login / archived → 409; others → 404".

- [ ] **Step 7: RTM** — in `docs/quality/RTM.md` add AGN-006-AC01…AC12, each mapped to its test file from spec §7 and to `DEC-SCOPE-047`.

- [ ] **Step 8: PRD open items** — in `docs/product/PRD_OPEN_ITEMS.md`, extend the AGN-004 erasure item: "`NEEDS_CONFIRMATION` — also
  covers AGN-006 counseling records (budget, remarks) of students with no login." and add "AGN-006: no rate limit on counseling saves
  (as AGN-004 writes) — owner to confirm whether agency writes need throttling."

- [ ] **Step 9: Spec status** — in the spec header change `**Status:**` to "approved (2026-10-01); implemented on
  `feature/agn-006-counseling-record` — browser QA and independent review pending".

- [ ] **Step 10: Commit**

```powershell
git add docs
git commit -m "docs(agn-006): backlog, DEC-SCOPE-047, contracts, data model, RBAC, RTM, open items"
```
