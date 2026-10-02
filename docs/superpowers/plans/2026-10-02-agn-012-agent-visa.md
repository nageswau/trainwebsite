# AGN-012 — Visa for agent-managed applications: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** an agency Master or Staff member starts and runs the visa case of an agent-managed application — documents checklist,
visa application date, appointment, interview, forward-only stage and a final decision — without changing any existing visa behavior.

**Architecture:** two routes (`POST`/`PATCH …/crm/applications/{id}/visa`) in the AGN-008 router reuse its gate, lock order and
closed-application checks; the rules live in a new `app/services/agent_visa.py`; the application detail gains an additive `visa`
block; a new `AgentApplicationVisa` panel (plus a shared `AgentVisaDetailsForm`) copies the AGN-013 enrollment pattern.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL, Pydantic 2, pytest + pytest-asyncio + httpx; Next.js 15, React,
TypeScript, vitest + Testing Library, Playwright. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-02-agn-012-agent-visa-design.md` (`DEC-SCOPE-055`).

## Global Constraints

- Routes: `POST /api/v1/workflows/overseas/agent/crm/applications/{id}/visa` (`201`) and `PATCH …/{id}/visa` (`200`); both return `{"application": detail}`.
- Master and Staff (Staff: assigned students only); out of scope `404`; non-agents `403`; anonymous `401`.
- A case starts at `checklist`, only from application stage `offer`, `visa_documentation` or `status_tracking` (`422 "An offer is needed before a visa case"`).
- Stage moves forward-only, skips allowed; leaving `checklist` requires every checklist item's newest attached document `verified`
  (`422 "Cannot advance past the checklist stage -- not yet verified: X, Y."`).
- `decision` ∈ `approved | refused | withdrawn`, only when the case is already at `decision`; final once recorded (`409`).
- `interview_date >= visa_application_date` when both set (same day allowed), else `422` with `loc` `["body", "interview_date"]`.
- Checklist items: `AgentDocumentType` without "Other", unique, at most 8.
- Writes refused (`409`) on withdrawn/enrolled applications and archived students; stale `expected_status`/`expected_stage` or a PATCH with no case → `409`.
- Existing visa routes and responses (`/overseas/visa`, `visa-checklist`, `visa-status`, `interview-prep`), the list endpoint, the status and enrollment routes: unchanged.
- Logs carry ids and stages only — never the decision or any date. Audit rows: field names, stages, item count, decision.
- Lite test runs only (the owner runs the full suites). No completion claim: browser validation and Codex review follow.

## Test commands

`API_TEST <paths>` (isolated compose project `agn012`; Postgres/Redis started with
`docker compose --project-directory ../.. -p agn012 -f ../../docker-compose.yml -f ../../docker-compose.ci.yml --profile ci up -d postgres redis`
from `apps/api`):

```bash
docker compose -p agn012 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "C:/Users/kunam/Documents/project/trainwebsite/.claude/worktrees/agn-012/apps/api:/app" \
  api-test sh -c "alembic upgrade head && python -m pytest -q <paths>"
```
(run from the worktree root).

`WEB_TEST <paths>`: `cd apps/web && npx vitest run <paths>`

## Review Focus

1. A case opened by an overseas admin through the old route (stage `not_started`, free-text checklist "Visa form") reaches the agency:
   it reads, shows "Visa form: Not uploaded", and the agency can move it to `checklist` (forward from a legacy stage) but not past it.
   Pinned in Task 3 (`test_legacy_admin_case_is_readable_and_moves_forward_only_through_the_gate`).
2. A verified document is replaced (AGN-009 replace resets it to `pending`) or a newer upload of the same type is pending → the gate
   blocks again. Pinned in Task 3 (`test_the_newest_document_of_a_type_decides`).
3. Setting a visa application date later than an already stored interview date → `422` on `interview_date`, nothing written.
   Pinned in Task 3 (`test_date_order_uses_stored_values`).
4. A double click on "Yes, record decision" → one request. Pinned in Task 6 (in-flight test).
5. A Staff member whose student was reassigned away after the screen loaded → `404`, nothing written. Pinned in Task 4
   (`test_staff_out_of_scope_is_404_and_writes_nothing`).

## Spec deviations (recorded in the spec's §11 in Task 8)

- `VISA_CASE_STAGES` and `VISA_DECISION_DISCLAIMER` move, unchanged, from `api/workflows.py` to `services/agent_visa.py`;
  `workflows.py` imports them back (`services.agent_applications` is imported by `workflows.py`, so the service cannot import the API
  module). `from app.api.workflows import VISA_CASE_STAGES` keeps working (`school_global_education.py`).
- The date-order rule runs in the service for both POST and PATCH (one place, same `loc`), not as a schema validator.
- `visa` is optional in the TS type, so the AGN-008/013 component fixtures need no change; the `test_agn_003_matrix.py` row is replaced
  by the Master/Staff cases in `test_agn_012_security.py` (the matrix fixtures have no application at `offer`).

---

### Task 1: Visa rules module and request schemas (pure)

**Files:**
- Create: `apps/api/app/services/agent_visa.py`
- Modify: `apps/api/app/api/workflows.py:2163-2166, 2226-2230` (constants move), `apps/api/app/schemas.py` (after `AgentApplicationEnrollment`)
- Test: `apps/api/tests/test_agn_012_schemas.py`

**Interfaces:**
- Produces: `VISA_CASE_STAGES: list[str]`, `VISA_DECISIONS: tuple[str, ...]`, `VISA_DECISION_DISCLAIMER: str`, `stage_index(stage: str) -> int`,
  `check_dates(application_date: date | None, interview_date: date | None) -> None` (raises `RequestValidationError`), message constants
  `VISA_EXISTS, VISA_OFFER_NEEDED, VISA_ENROLLED, VISA_STALE, VISA_DECIDED, VISA_CHECKLIST_LOCKED, VISA_DECISION_STAGE, VISA_FORWARD_ONLY,
  INTERVIEW_BEFORE_APPLICATION`; schemas `AgentVisaStart`, `AgentVisaUpdate`.

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_agn_012_schemas.py`

```python
"""AGN-012 (DEC-SCOPE-055) -- request schemas and the pure rules of services/agent_visa.py (spec §4, §10.1)."""

from datetime import date

import pytest
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.schemas import AgentVisaStart, AgentVisaUpdate
from app.services.agent_visa import INTERVIEW_BEFORE_APPLICATION, VISA_CASE_STAGES, check_dates, stage_index


def test_stage_list_is_unchanged_and_still_importable_from_workflows():
    from app.api.workflows import VISA_CASE_STAGES as from_workflows, VISA_DECISION_DISCLAIMER as disclaimer

    assert VISA_CASE_STAGES == ["checklist", "documentation", "interview_prep", "tracking", "decision"]
    assert from_workflows is VISA_CASE_STAGES
    assert disclaimer.startswith("Visa decisions are made by the relevant government")


@pytest.mark.parametrize(("stage", "index"), [("checklist", 0), ("decision", 4), ("not_started", -1), ("", -1)])
def test_stage_index_counts_a_legacy_stage_as_before_checklist(stage, index):
    assert stage_index(stage) == index


def test_start_accepts_named_document_types_and_optional_dates():
    body = AgentVisaStart.model_validate({"expected_status": "offer", "checklist": ["Passport", "Financial documents"], "interview_date": "2027-06-01"})
    assert body.checklist == ["Passport", "Financial documents"] and body.interview_date == date(2027, 6, 1) and body.visa_application_date is None
    assert AgentVisaStart.model_validate({"expected_status": "offer"}).checklist == []


@pytest.mark.parametrize(
    "body",
    [
        {"expected_status": "offer", "checklist": ["Other"]},
        {"expected_status": "offer", "checklist": ["Passport", "Passport"]},
        {"expected_status": "offer", "checklist": ["Visa form"]},
        {"expected_status": "offer", "checklist": ["Passport"] * 9},
        {"expected_status": "offer", "status": "decision"},  # no stage field: a case always starts at checklist
        {"expected_status": "offer", "visa_application_date": "1999-12-31"},
        {"checklist": []},
    ],
)
def test_start_rejects(body):
    with pytest.raises(ValidationError):
        AgentVisaStart.model_validate(body)


def test_update_keeps_absent_and_null_apart():
    body = AgentVisaUpdate.model_validate({"expected_stage": "documentation", "interview_date": None})
    assert body.model_dump(exclude_unset=True) == {"expected_stage": "documentation", "interview_date": None}


@pytest.mark.parametrize(
    "body",
    [
        {"expected_stage": "decision", "decision": "pending"},
        {"expected_stage": "decision", "decision": None},
        {"expected_stage": "checklist", "to_stage": None},
        {"expected_stage": "checklist", "to_stage": "approved"},
        {"expected_stage": "checklist", "checklist": None},
        {"expected_stage": "checklist", "checklist": ["Other"]},
        {"expected_stage": "checklist", "tracking_reference": "X"},
        {"to_stage": "documentation"},
    ],
)
def test_update_rejects(body):
    with pytest.raises(ValidationError):
        AgentVisaUpdate.model_validate(body)


def test_date_order_allows_same_day_and_either_alone():
    check_dates(date(2027, 5, 1), date(2027, 5, 1))
    check_dates(None, date(2027, 5, 1))
    check_dates(date(2027, 5, 1), None)


def test_interview_before_application_is_a_field_error():
    with pytest.raises(RequestValidationError) as caught:
        check_dates(date(2027, 5, 2), date(2027, 5, 1))
    (error,) = caught.value.errors()
    assert error["loc"] == ("body", "interview_date") and error["msg"] == INTERVIEW_BEFORE_APPLICATION
```

- [ ] **Step 2: Run it — expect FAIL** (`ImportError: cannot import name 'AgentVisaStart'` / `No module named 'app.services.agent_visa'`)

`API_TEST tests/test_agn_012_schemas.py`

- [ ] **Step 3: Implement** — create `apps/api/app/services/agent_visa.py`:

```python
"""AGN-012 -- the visa case of an agency's application (DEC-SCOPE-055; docs/superpowers/specs/2026-10-02-agn-012-agent-visa-design.md §4).

Also the home of the visa stage list and the compliance sentence the counselor/student routes in `api/workflows.py` use: they moved
here unchanged because `workflows.py` imports `services.agent_applications`, which needs them, so this module cannot import the API
layer."""

from datetime import date

from fastapi.exceptions import RequestValidationError

# DATA_MODEL.md #6.5, DEC-SCOPE-006: the four confirmed category names plus a terminal `decision` state. The outcomes are not stages:
# DEC-SCOPE-055 V2 records them for agency cases in their own column, so this list is unchanged.
VISA_CASE_STAGES = ["checklist", "documentation", "interview_prep", "tracking", "decision"]
VISA_DECISIONS = ("approved", "refused", "withdrawn")

# VISA-003-AC02: a fixed compliance sentence, sourced from the reference implementation's own compliance language (DATA_MODEL.md
# #6.5) -- never invented, and never varied per case, so no response can ever imply EduSphere decides visa outcomes.
VISA_DECISION_DISCLAIMER = "Visa decisions are made by the relevant government or immigration authority. EduSphere does not decide visa outcomes."

VISA_EXISTS = "A visa case already exists for this application"
VISA_OFFER_NEEDED = "An offer is needed before a visa case"
VISA_ENROLLED = "This application is enrolled, so its visa case can no longer be changed"
VISA_STALE = "This visa case changed since you opened it -- reload to see its current stage"
VISA_DECIDED = "The visa decision is recorded, so this case can no longer be changed"
VISA_CHECKLIST_LOCKED = "The checklist can only be changed at the checklist stage"
VISA_DECISION_STAGE = "Move the case to the decision stage before recording a decision"
VISA_FORWARD_ONLY = "A visa case can only move forward"
INTERVIEW_BEFORE_APPLICATION = "The interview date cannot be before the visa application date"


def stage_index(stage: str) -> int:
    """A stage outside the list (the seed's legacy `not_started`) counts as before `checklist`."""
    return VISA_CASE_STAGES.index(stage) if stage in VISA_CASE_STAGES else -1


def check_dates(application_date: date | None, interview_date: date | None) -> None:
    """V4: on the resulting values (request merged over stored). Same day is fine. Raised as FastAPI's own 422 list so the form puts
    the message on the interview field, whichever route found it."""
    if application_date and interview_date and interview_date < application_date:
        raise RequestValidationError([{"type": "value_error", "loc": ("body", "interview_date"), "msg": INTERVIEW_BEFORE_APPLICATION, "input": interview_date.isoformat()}])
```

In `apps/api/app/api/workflows.py`, delete the `VISA_CASE_STAGES` definition with its 3-line comment (lines 2163-2166) and the
`VISA_DECISION_DISCLAIMER` definition with its 3-line comment (lines 2226-2230); add next to the other service imports (line ~108):

```python
from app.services.agent_visa import VISA_CASE_STAGES, VISA_DECISION_DISCLAIMER
```

In `apps/api/app/schemas.py`, add the import `from app.services.agent_visa import VISA_CASE_STAGES` at the top (after `from app.models import GENDERS`) and after `AgentApplicationEnrollment`:

```python
# --- AGN-012: the visa case of an agency's application (DEC-SCOPE-055; docs/superpowers/specs/2026-10-02-agn-012-agent-visa-design.md §4) ---


def _visa_checklist(value: list[str] | None) -> list[str]:
    """V6: named agency document types only (an "Other" document has no fixed type to match), each once."""
    if value is None:
        raise PydanticCustomError("not_clearable", "The checklist cannot be cleared; send an empty list")
    if "Other" in value:
        raise PydanticCustomError("visa_checklist_other", "Choose a named document type for the checklist")
    if len(set(value)) != len(value):
        raise PydanticCustomError("visa_checklist_duplicate", "Each document type can appear once")
    return value


class _AgentVisaDates(BaseModel):
    model_config = {"extra": "forbid"}
    visa_application_date: date | None = None
    appointment_date: date | None = None
    interview_date: date | None = None

    @field_validator("visa_application_date", "appointment_date", "interview_date")
    @classmethod
    def _dates(cls, value):
        return _application_date(value)


class AgentVisaStart(_AgentVisaDates):
    """Start a case. There is no stage field: a case always starts at `checklist` (V3), so the checklist gate cannot be skipped at
    creation. `expected_status` is the application stage the screen shows (stale screen -> 409)."""

    expected_status: str = Field(max_length=50)
    checklist: list[AgentDocumentType] = Field(default_factory=list, max_length=8)

    @field_validator("checklist")
    @classmethod
    def _checklist(cls, value):
        return _visa_checklist(value)


class AgentVisaUpdate(_AgentVisaDates):
    """A partial update: an absent key is unchanged, an explicit null clears a date. The checklist, the target stage and the decision
    cannot be cleared. `expected_stage` is the visa stage the screen shows."""

    expected_stage: str = Field(max_length=50)
    checklist: list[AgentDocumentType] | None = Field(default=None, max_length=8)
    to_stage: str | None = None
    decision: Literal["approved", "refused", "withdrawn"] | None = None

    @field_validator("checklist")
    @classmethod
    def _checklist(cls, value):
        return _visa_checklist(value)

    @field_validator("to_stage")
    @classmethod
    def _to_stage(cls, value):
        if value not in VISA_CASE_STAGES:
            raise PydanticCustomError("visa_stage", "Choose a visa stage: {stages}", {"stages": ", ".join(VISA_CASE_STAGES)})
        return value

    @field_validator("decision")
    @classmethod
    def _decision(cls, value):
        if value is None:
            raise PydanticCustomError("not_clearable", "A recorded decision cannot be cleared")
        return value
```

(`field_validator` runs on an explicitly sent value, including `null`, and never on an absent key — Pydantic's `validate_default` is off.)

- [ ] **Step 4: Run it — expect PASS** `API_TEST tests/test_agn_012_schemas.py tests/test_visa_001_checklist.py tests/test_visa_003_status.py`
  (the two VISA files prove the moved constants still serve the old routes).

- [ ] **Step 5: Lint and commit**

```bash
cd apps/api && python -m ruff check app/services/agent_visa.py app/schemas.py app/api/workflows.py tests/test_agn_012_schemas.py
git add apps/api/app/services/agent_visa.py apps/api/app/schemas.py apps/api/app/api/workflows.py apps/api/tests/test_agn_012_schemas.py
git commit -m "feat(agn-012): visa rules module and request schemas"
```

---

### Task 2: Migration `0061_agent_visa_details` and model columns

**Files:**
- Create: `apps/api/alembic/versions/0061_agent_visa_details.py`
- Modify: `apps/api/app/models.py:552-559` (`VisaCase`), `apps/api/tests/test_agn_013_migration.py:39-43` (head pin)
- Test: `apps/api/tests/test_agn_012_migration.py`

**Interfaces:**
- Produces: `VisaCase.visa_application_date: date | None`, `VisaCase.interview_date: date | None`, `VisaCase.decision: str | None`,
  `VisaCase.decided_at: datetime | None`; constraint `ck_visa_cases_decision`.

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_agn_012_migration.py` (the AGN-013 throwaway-database pattern):

```python
"""AGN-012 -- migration 0061_agent_visa_details (spec §3). Round trip and downgrade refusals run in a throwaway database built from
scratch; a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run() itself."""

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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_012_migration_0061", VERSIONS / "0061_agent_visa_details.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0060_agent_app_enrollment"
HEAD = "0061_agent_visa_details"
CASE_COLUMNS = "SELECT id, application_id, status, appointment_date, checklist::text, tracking_reference FROM visa_cases ORDER BY id"
NEW = ("visa_application_date", "interview_date", "decision", "decided_at")


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0060_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(HEAD) <= 32  # alembic_version.version_num is VARCHAR(32)
    assert tuple(name for name, _ in _migration.COLUMNS) == NEW
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_model_declares_the_new_columns_nullable_with_the_decision_check():
    from app.models import VisaCase

    columns = VisaCase.__table__.columns
    for name in NEW:
        assert name in columns and columns[name].nullable, name
    checks = {c.name: str(c.sqltext) for c in VisaCase.__table__.constraints if isinstance(c, sa.CheckConstraint)}
    assert checks == {"ck_visa_cases_decision": _migration.DECISION_CHECK}


@pytest.mark.asyncio
async def test_new_columns_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    cols = await conn.run_sync(lambda sync: {c["name"]: c for c in inspect(sync).get_columns("visa_cases")})
    for name in NEW:
        assert name in cols and cols[name]["nullable"], name


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
    """A fresh database at 0060 with one application and one legacy visa case."""
    cfg = _config()
    original = settings.database_url
    name = f"agn012_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("student", "country", "university", "application", "case")}
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'student user', 'overseas_student', 'overseas', true, true, 'en-GB', '{}')",
            {"id": ids["student"], "email": f"student-{name}@example.local"},
        )
        _sql(
            url,
            "INSERT INTO countries (id, slug, name, overview, tuition, living_expenses, visa_process, work_opportunities, post_study_work, pr_opportunities, faq) "
            "VALUES (:id, :slug, 'Testland', '', '', '', '[]', '', '', '', '[]')",
            {"id": ids["country"], "slug": f"c-{name}"},
        )
        _sql(
            url,
            "INSERT INTO universities (id, country_id, slug, name, city, overview, eligibility, requirements, deadlines, scholarships) "
            "VALUES (:id, :country, :slug, 'Mig University', 'Town', '', '', '[]', '[]', '[]')",
            {"id": ids["university"], "country": ids["country"], "slug": f"u-{name}"},
        )
        _sql(
            url,
            "INSERT INTO overseas_applications (id, student_id, university_id, status, intake) VALUES (:id, :student, :university, 'visa_documentation', 'Sep 2027')",
            {"id": ids["application"], "student": ids["student"], "university": ids["university"]},
        )
        _sql(
            url,
            "INSERT INTO visa_cases (id, application_id, status, appointment_date, checklist, tracking_reference) "
            "VALUES (:id, :app, 'not_started', DATE '2027-05-01', '[\"Passport\", \"Visa form\"]', 'TR-1')",
            {"id": ids["case"], "app": ids["application"]},
        )
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_existing_cases_identical(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, CASE_COLUMNS)
    command.upgrade(cfg, HEAD)
    assert _sql(url, CASE_COLUMNS) == before
    assert _sql(url, f"SELECT {', '.join(NEW)} FROM visa_cases") == [(None, None, None, None)]
    command.downgrade(cfg, BASE)
    assert _sql(url, CASE_COLUMNS) == before
    command.upgrade(cfg, HEAD)
    assert _sql(url, CASE_COLUMNS) == before


def test_the_database_refuses_an_unknown_decision(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(IntegrityError):
        _sql(url, "UPDATE visa_cases SET decision = 'pending'")
    _sql(url, "UPDATE visa_cases SET decision = 'refused'")


@pytest.mark.parametrize(("column", "value"), [("visa_application_date", "DATE '2027-04-01'"), ("interview_date", "DATE '2027-05-02'"), ("decision", "'approved'"), ("decided_at", "now()")])
def test_downgrade_refuses_to_lose_visa_details(isolated_db, column, value):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _sql(url, f"UPDATE visa_cases SET {column} = {value}")
    with pytest.raises(RuntimeError, match="visa details exist"):
        command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT version_num FROM alembic_version") == [(HEAD,)]
    assert _sql(url, f"SELECT count(*) FROM visa_cases WHERE {column} IS NOT NULL") == [(1,)]
```

Also relax the AGN-013 head pin (`test_agn_013_migration.py:39-43`), as `d871cdd` did for AGN-016:

```python
def test_migration_chains_after_0059_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(HEAD) <= 32  # alembic_version.version_num is VARCHAR(32)
    assert tuple(name for name, _ in _migration.COLUMNS) == NEW
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1  # AGN-012 chains 0061 after this one
```

- [ ] **Step 2: Run it — expect FAIL** (`FileNotFoundError` for `0061_agent_visa_details.py`). Run with plain pytest (no `alembic upgrade head` in the
  container command, since the revision does not exist yet): `… api-test sh -c "python -m pytest -q tests/test_agn_012_migration.py"`

- [ ] **Step 3: Implement** — `apps/api/alembic/versions/0061_agent_visa_details.py`:

```python
"""AGN-012 -- visa_cases.visa_application_date, interview_date, decision, decided_at.

Revision ID: 0061_agent_visa_details
Revises: 0060_agent_app_enrollment

docs/superpowers/specs/2026-10-02-agn-012-agent-visa-design.md §3 (DEC-SCOPE-055). Four nullable columns and a CHECK on the decision;
no existing row is read or written. 0001 builds a fresh database from the current models, which already carry these columns and the
constraint, so every add is guarded (0057's and 0041's idioms). downgrade() refuses while visa details exist rather than silently
dropping them.
"""

import sqlalchemy as sa

from alembic import op

revision = "0061_agent_visa_details"
down_revision = "0060_agent_app_enrollment"
branch_labels = None
depends_on = None

TABLE = "visa_cases"
COLUMNS = (("visa_application_date", sa.Date()), ("interview_date", sa.Date()), ("decision", sa.String(20)), ("decided_at", sa.DateTime(timezone=True)))
DECISION_CHECK = "decision IN ('approved', 'refused', 'withdrawn')"
CHECK_NAME = "ck_visa_cases_decision"


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns(TABLE)}
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints(TABLE)}
    if CHECK_NAME not in checks:
        op.create_check_constraint(CHECK_NAME, TABLE, DECISION_CHECK)


def downgrade() -> None:
    if not op.get_context().as_sql:
        recorded = " OR ".join(f"{name} IS NOT NULL" for name, _ in COLUMNS)
        if op.get_bind().execute(sa.text(f"SELECT count(*) FROM {TABLE} WHERE {recorded}")).scalar():
            raise RuntimeError("Refusing to downgrade 0061_agent_visa_details: visa details exist")
    op.drop_constraint(CHECK_NAME, TABLE, type_="check")
    for name, _ in reversed(COLUMNS):
        op.drop_column(TABLE, name)
```

`apps/api/app/models.py` — `VisaCase` becomes:

```python
class VisaCase(Base, TimestampMixin):
    __tablename__ = "visa_cases"
    __table_args__ = (CheckConstraint("decision IN ('approved', 'refused', 'withdrawn')", name="ck_visa_cases_decision"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("overseas_applications.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="checklist")
    appointment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    checklist: Mapped[list] = mapped_column(JSON, default=list)
    tracking_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # AGN-012 (DEC-SCOPE-055; migration 0061): written only by the agency visa routes; the counselor/student routes neither read nor
    # write them (V8). `decision` is the authority's outcome as the agency records it, final once set (V2).
    visa_application_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    interview_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Run — expect PASS** `API_TEST tests/test_agn_012_migration.py tests/test_agn_013_migration.py`

- [ ] **Step 5: Commit** `git commit -m "feat(agn-012): migration 0061 -- visa application date, interview date and decision"`

---

### Task 3: Agency visa routes, rules and the detail block

**Files:**
- Modify: `apps/api/app/services/agent_visa.py` (DB helpers), `apps/api/app/services/agent_applications.py:154-182` (`detail`),
  `apps/api/app/api/agent_applications.py` (two routes, imports, docstring), `apps/api/app/services/staff_activity.py:25-40` (allowlist)
- Create: `apps/api/tests/agn012_helpers.py`
- Test: `apps/api/tests/test_agn_012_visa.py`

**Interfaces:**
- Consumes: Task 1 constants/schemas, Task 2 columns; `_gate`, `_locked`, `_refuse_closed`, `_audit`, `_log`, `detail`, `STALE`, `OFFER_STAGES_ON`.
- Produces: `load_case(db, application_id) -> VisaCase | None`, `checklist_status(db, application_id, items) -> list[dict]`,
  `visa_block(db, application_id) -> dict | None`, `update_case(db, case, changes: dict) -> tuple[str, dict] | None`;
  detail key `visa`; audit actions `overseas.application.visa_start|visa_update|visa_advance|visa_decision`;
  log events `agent_visa_started|agent_visa_updated|agent_visa_advanced|agent_visa_decided|agent_visa_gate_blocked`.

- [ ] **Step 1: Write the failing tests** — `apps/api/tests/agn012_helpers.py`:

```python
"""AGN-012 test helpers: the AGN-009 world (a Master, a Verify staff member who is assigned the students, a plain staff member, an
unassigned student, another agency) plus an application at `offer` for the no-login student, and direct builders for visa cases."""

from sqlalchemy import func, select

from app.models import AuditLog, VisaCase
from tests.agn008_helpers import APPS, mk_application
from tests.agn009_helpers import mk_doc, world as documents_world

VISA = APPS + "/{}/visa"


async def visa_world(db, *, status: str = "offer") -> dict:
    w = await documents_world(db)
    w["app"] = await mk_application(db, agent=w["master"], university=w["university"], record=w["record"], status=status)
    return w


async def mk_case(db, app, **fields) -> VisaCase:
    case = VisaCase(application_id=app.id, status=fields.pop("status", "checklist"), checklist=fields.pop("checklist", []), **fields)
    db.add(case)
    await db.commit()
    return case


async def case_of(db, app) -> VisaCase | None:
    return await db.scalar(select(VisaCase).where(VisaCase.application_id == app.id).execution_options(populate_existing=True))


async def visa_audits(db, app) -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action.like("overseas.application.visa%")).order_by(AuditLog.created_at))).all())


async def count_cases(db, app) -> int:
    return await db.scalar(select(func.count()).select_from(VisaCase).where(VisaCase.application_id == app.id))


async def verified(db, w, *types: str, status: str = "verified") -> None:
    for document_type in types:
        await mk_doc(db, record=w["record"], application=w["app"], status=status, document_type=document_type)
```

`apps/api/tests/test_agn_012_visa.py`:

```python
"""AGN-012 AC1-AC7, AC12 -- an agency starts and runs a visa case (spec §4); refusals write nothing; logs and audit stay clean."""

import logging

import pytest
import pytest_asyncio

from app.models import OverseasApplication, VisaCase
from tests.agn001_helpers import client_for
from tests.agn008_helpers import APPS, mk_application
from tests.agn009_helpers import mk_doc
from tests.agn012_helpers import VISA, case_of, count_cases, mk_case, verified, visa_audits, visa_world


@pytest_asyncio.fixture
async def world(db_session):
    return await visa_world(db_session)


async def _start(c, app_id, **body):
    return await c.post(VISA.format(app_id), json={"expected_status": "offer", **body})


async def _patch(c, app_id, **body):
    return await c.patch(VISA.format(app_id), json=body)


@pytest.mark.asyncio
async def test_the_detail_has_no_visa_block_until_a_case_starts(world):
    async with client_for(world["master"].email) as c:
        assert (await c.get(f"{APPS}/{world['app'].id}")).json()["application"]["visa"] is None


@pytest.mark.asyncio
async def test_full_flow_to_an_approved_decision(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await _start(c, world["app"].id, checklist=["Passport", "Financial documents"], visa_application_date="2027-05-01")
        assert r.status_code == 201, r.text
        v = r.json()["application"]["visa"]
        assert (v["stage"], v["visa_application_date"], v["decision"]) == ("checklist", "2027-05-01", None)
        assert v["checklist"] == [{"item": "Passport", "verification_status": "not_uploaded"}, {"item": "Financial documents", "verification_status": "not_uploaded"}]
        assert v["disclaimer"].startswith("Visa decisions are made by")
        await verified(db_session, world, "Passport", "Financial documents")
        for old, new in (("checklist", "documentation"), ("documentation", "interview_prep")):
            r = await _patch(c, world["app"].id, expected_stage=old, to_stage=new)
            assert r.status_code == 200, r.text
        r = await _patch(c, world["app"].id, expected_stage="interview_prep", interview_date="2027-05-20", appointment_date="2027-05-10")
        assert r.status_code == 200 and r.json()["application"]["visa"]["interview_date"] == "2027-05-20"
        assert (await _patch(c, world["app"].id, expected_stage="interview_prep", to_stage="decision")).status_code == 200  # a skip
        r = await _patch(c, world["app"].id, expected_stage="decision", decision="approved")
        assert r.status_code == 200, r.text
        a = r.json()["application"]
    assert (a["visa"]["decision"], a["status"]) == ("approved", "offer")  # V5: the application stage never moves
    assert a["visa"]["decided_at"]
    actions = [(row.action, row.metadata_json) for row in await visa_audits(db_session, world["app"])]
    assert actions == [
        ("overseas.application.visa_start", {"checklist_items": 2}),
        ("overseas.application.visa_advance", {"from_stage": "checklist", "to_stage": "documentation"}),
        ("overseas.application.visa_advance", {"from_stage": "documentation", "to_stage": "interview_prep"}),
        ("overseas.application.visa_update", {"fields": ["appointment_date", "interview_date"]}),
        ("overseas.application.visa_advance", {"from_stage": "interview_prep", "to_stage": "decision"}),
        ("overseas.application.visa_decision", {"decision": "approved"}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["offer", "visa_documentation", "status_tracking"])
async def test_a_case_starts_from_an_offer_onwards(db_session, stage):
    w = await visa_world(db_session, status=stage)
    async with client_for(w["master"].email) as c:
        assert (await _start(c, w["app"].id, expected_status=stage)).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected", "archived", "code", "detail"),
    [
        ("enquiry", "enquiry", False, 422, "An offer is needed before a visa case"),
        ("University review", "University review", False, 422, "An offer is needed before a visa case"),  # legacy free text
        ("offer", "visa_documentation", False, 409, "This application changed since you opened it -- reload to see its current status"),
        ("withdrawn", "withdrawn", False, 409, "This application is withdrawn"),
        ("enrolled", "enrolled", False, 409, "This application is enrolled, so its visa case can no longer be changed"),
        ("offer", "offer", True, 409, "Unarchive this student first"),
    ],
)
async def test_start_refusals_write_nothing(db_session, world, status, expected, archived, code, detail):
    row = await db_session.get(OverseasApplication, world["app"].id)
    row.status = status
    if archived:
        world["record"].status = "archived"
        db_session.add(world["record"])
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await _start(c, world["app"].id, expected_status=expected)
    assert (r.status_code, r.json()["detail"]) == (code, detail)
    assert await count_cases(db_session, world["app"]) == 0 and await visa_audits(db_session, world["app"]) == []


@pytest.mark.asyncio
async def test_a_second_start_is_409(db_session, world):
    await mk_case(db_session, world["app"])
    async with client_for(world["master"].email) as c:
        r = await _start(c, world["app"].id)
    assert (r.status_code, r.json()["detail"]) == (409, "A visa case already exists for this application")
    assert await count_cases(db_session, world["app"]) == 1


@pytest.mark.asyncio
async def test_start_checks_the_date_order(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await _start(c, world["app"].id, visa_application_date="2027-05-02", interview_date="2027-05-01")
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "interview_date"]
    assert await count_cases(db_session, world["app"]) == 0


@pytest.mark.asyncio
async def test_the_gate_blocks_until_every_item_is_verified(db_session, world):
    await mk_case(db_session, world["app"], checklist=["Passport", "SOP"])
    await verified(db_session, world, "Passport")
    await verified(db_session, world, "SOP", status="pending")
    async with client_for(world["master"].email) as c:
        r = await _patch(c, world["app"].id, expected_stage="checklist", to_stage="tracking")
        assert (r.status_code, r.json()["detail"]) == (422, "Cannot advance past the checklist stage -- not yet verified: SOP.")
        assert (await case_of(db_session, world["app"])).status == "checklist"
        await verified(db_session, world, "SOP")
        assert (await _patch(c, world["app"].id, expected_stage="checklist", to_stage="tracking")).status_code == 200


@pytest.mark.asyncio
async def test_the_newest_document_of_a_type_decides(db_session, world):
    await mk_case(db_session, world["app"], checklist=["Passport"])
    await verified(db_session, world, "Passport")
    await verified(db_session, world, "Passport", status="pending")  # a newer upload, not yet reviewed
    async with client_for(world["master"].email) as c:
        r = await _patch(c, world["app"].id, expected_stage="checklist", to_stage="documentation")
    assert r.status_code == 422 and "Passport" in r.json()["detail"]


@pytest.mark.asyncio
async def test_documents_outside_the_application_do_not_count(db_session, world):
    await mk_case(db_session, world["app"], checklist=["Passport"])
    other_app = await mk_application(db_session, agent=world["master"], university=world["university"], record=world["record"], status="offer", course_id=None, intake="Jan 2028")
    await mk_doc(db_session, record=world["record"], application=other_app, status="verified")
    await mk_doc(db_session, record=world["record"], application=None, status="verified")
    async with client_for(world["master"].email) as c:
        r = await c.get(f"{APPS}/{world['app'].id}")
        assert r.json()["application"]["visa"]["checklist"] == [{"item": "Passport", "verification_status": "not_uploaded"}]
        assert (await _patch(c, world["app"].id, expected_stage="checklist", to_stage="documentation")).status_code == 422


@pytest.mark.asyncio
async def test_the_gate_reads_the_checklist_sent_with_the_move(db_session, world):
    await mk_case(db_session, world["app"], checklist=["Passport"])
    async with client_for(world["master"].email) as c:
        r = await _patch(c, world["app"].id, expected_stage="checklist", checklist=[], to_stage="documentation")
    assert r.status_code == 200 and r.json()["application"]["visa"]["checklist"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stage", "body", "detail"),
    [
        ("documentation", {"to_stage": "checklist"}, "A visa case can only move forward"),
        ("documentation", {"to_stage": "documentation"}, "A visa case can only move forward"),
        ("documentation", {"checklist": ["Passport"]}, "The checklist can only be changed at the checklist stage"),
        ("tracking", {"decision": "approved"}, "Move the case to the decision stage before recording a decision"),
        ("tracking", {"to_stage": "decision", "decision": "approved"}, "Move the case to the decision stage before recording a decision"),
    ],
)
async def test_rule_refusals_are_422_and_write_nothing(db_session, world, stage, body, detail):
    await mk_case(db_session, world["app"], status=stage)
    async with client_for(world["master"].email) as c:
        r = await _patch(c, world["app"].id, expected_stage=stage, **body)
    assert (r.status_code, r.json()["detail"]) == (422, detail)
    case = await case_of(db_session, world["app"])
    assert (case.status, case.checklist, case.decision) == (stage, [], None)
    assert await visa_audits(db_session, world["app"]) == []


@pytest.mark.asyncio
async def test_a_recorded_decision_is_final(db_session, world):
    await mk_case(db_session, world["app"], status="decision", decision="refused")
    async with client_for(world["master"].email) as c:
        for body in ({"decision": "approved"}, {"interview_date": "2027-06-01"}):
            r = await _patch(c, world["app"].id, expected_stage="decision", **body)
            assert (r.status_code, r.json()["detail"]) == (409, "The visa decision is recorded, so this case can no longer be changed")
    case = await case_of(db_session, world["app"])
    assert (case.decision, case.interview_date) == ("refused", None)


@pytest.mark.asyncio
async def test_stale_stage_and_missing_case_are_409(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await _patch(c, world["app"].id, expected_stage="checklist", interview_date="2027-06-01")
        assert (r.status_code, r.json()["detail"]) == (409, "This visa case changed since you opened it -- reload to see its current stage")
        await mk_case(db_session, world["app"], status="documentation")
        assert (await _patch(c, world["app"].id, expected_stage="checklist", to_stage="tracking")).status_code == 409
    assert (await case_of(db_session, world["app"])).status == "documentation"


@pytest.mark.asyncio
async def test_date_order_uses_stored_values(db_session, world):
    from datetime import date

    await mk_case(db_session, world["app"], status="documentation", interview_date=date(2027, 5, 10))
    async with client_for(world["master"].email) as c:
        r = await _patch(c, world["app"].id, expected_stage="documentation", visa_application_date="2027-05-11")
        assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "interview_date"]
        assert (await _patch(c, world["app"].id, expected_stage="documentation", visa_application_date="2027-05-10")).status_code == 200  # same day
        r = await _patch(c, world["app"].id, expected_stage="documentation", interview_date=None, appointment_date=None)
    assert r.status_code == 200 and r.json()["application"]["visa"]["interview_date"] is None
    assert (await case_of(db_session, world["app"])).visa_application_date == date(2027, 5, 10)


@pytest.mark.asyncio
async def test_an_unchanged_patch_writes_nothing(db_session, world):
    await mk_case(db_session, world["app"], checklist=["Passport"])
    async with client_for(world["master"].email) as c:
        r = await _patch(c, world["app"].id, expected_stage="checklist", checklist=["Passport"], interview_date=None)
    assert r.status_code == 200 and await visa_audits(db_session, world["app"]) == []


@pytest.mark.asyncio
async def test_legacy_admin_case_is_readable_and_moves_forward_only_through_the_gate(db_session, world):
    await mk_case(db_session, world["app"], status="not_started", checklist=["Passport", "Visa form"])
    async with client_for(world["master"].email) as c:
        v = (await c.get(f"{APPS}/{world['app'].id}")).json()["application"]["visa"]
        assert v["stage"] == "not_started" and v["checklist"][1] == {"item": "Visa form", "verification_status": "not_uploaded"}
        assert (await _patch(c, world["app"].id, expected_stage="not_started", to_stage="documentation")).status_code == 422  # the gate
        assert (await _patch(c, world["app"].id, expected_stage="not_started", to_stage="checklist")).status_code == 200
        r = await _patch(c, world["app"].id, expected_stage="checklist", checklist=["Passport"])
    assert r.status_code == 200 and [i["item"] for i in r.json()["application"]["visa"]["checklist"]] == ["Passport"]


@pytest.mark.asyncio
async def test_list_items_carry_no_visa_block(db_session, world):
    await mk_case(db_session, world["app"])
    async with client_for(world["master"].email) as c:
        items = (await c.get(APPS, params={"status": "all"})).json()["items"]
    assert items and all("visa" not in item for item in items)


@pytest.mark.asyncio
async def test_a_failed_write_leaves_nothing_behind(db_session, world, monkeypatch):
    from app.api import agent_applications

    def broken(*args, **kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(agent_applications, "_audit", broken)
    async with client_for(world["master"].email) as c:
        with pytest.raises(RuntimeError):
            await _start(c, world["app"].id, checklist=["Passport"])
    assert await count_cases(db_session, world["app"]) == 0  # one transaction: no case without its audit row


@pytest.mark.asyncio
async def test_logs_carry_no_decision_or_dates(db_session, world, caplog):
    logging.getLogger("app.agent_applications").disabled = False  # alembic's fileConfig disables loggers (AGN-004 precedent)
    caplog.set_level(logging.INFO, logger="app.agent_applications")
    async with client_for(world["master"].email) as c:
        assert (await _start(c, world["app"].id, visa_application_date="2027-05-01")).status_code == 201
        assert (await _patch(c, world["app"].id, expected_stage="checklist", to_stage="documentation")).status_code == 200
        assert (await _patch(c, world["app"].id, expected_stage="documentation", interview_date="2027-05-21")).status_code == 200
        await db_session.execute(VisaCase.__table__.update().where(VisaCase.application_id == world["app"].id).values(status="decision"))
        await db_session.commit()
        assert (await _patch(c, world["app"].id, expected_stage="decision", decision="refused")).status_code == 200
    records = [r for r in caplog.records if r.name == "app.agent_applications"]
    assert [r.msg for r in records] == ["agent_visa_started", "agent_visa_advanced", "agent_visa_updated", "agent_visa_decided"]
    text = " ".join(str(r.extra_fields) for r in records)
    assert "refused" not in text and "2027-05" not in text
    assert records[1].extra_fields["to_stage"] == "documentation" and records[2].extra_fields["fields"] == ["interview_date"]
```

(`with pytest.raises(RuntimeError)` works because httpx's `ASGITransport` re-raises application exceptions, as the AGN tests rely on.)

- [ ] **Step 2: Run — expect FAIL** (`KeyError: 'visa'` in the first test; `405 Method Not Allowed` for the routes)
  `API_TEST tests/test_agn_012_visa.py`

- [ ] **Step 3: Implement.** Append to `apps/api/app/services/agent_visa.py` (and extend its imports):

```python
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StudentDocument, VisaCase

DETAIL_FIELDS = ("checklist", "visa_application_date", "appointment_date", "interview_date")


async def load_case(db: AsyncSession, application_id: UUID) -> VisaCase | None:
    """V7: one case per application. The counselor route refuses a second one; ordering keeps a pre-existing duplicate deterministic."""
    return await db.scalar(select(VisaCase).where(VisaCase.application_id == application_id).order_by(VisaCase.created_at, VisaCase.id).limit(1))


async def checklist_status(db: AsyncSession, application_id: UUID, items: list[str]) -> list[dict]:
    """V6: each item's newest document of that type attached to this application (one query); documents elsewhere do not count.
    `workflows._checklist_verification` keeps its own (unordered) pick for the counselor route."""
    latest: dict[str, str] = {}
    if items:
        rows = await db.execute(
            select(StudentDocument.document_type, StudentDocument.verification_status)
            .where(StudentDocument.application_id == application_id, StudentDocument.document_type.in_(items))
            .order_by(StudentDocument.created_at, StudentDocument.id)
        )
        latest = {document_type: status for document_type, status in rows}  # ascending, so the newest wins
    return [{"item": item, "verification_status": latest.get(item, "not_uploaded")} for item in items]


async def visa_block(db: AsyncSession, application_id: UUID) -> dict | None:
    """§4.5: the agency detail's `visa` key -- agency-only (V8)."""
    case = await load_case(db, application_id)
    if case is None:
        return None
    return {
        "id": case.id,
        "stage": case.status,
        "checklist": await checklist_status(db, application_id, list(case.checklist or [])),
        "visa_application_date": case.visa_application_date,
        "appointment_date": case.appointment_date,
        "interview_date": case.interview_date,
        "decision": case.decision,
        "decided_at": case.decided_at,
        "disclaimer": VISA_DECISION_DISCLAIMER,
    }


async def update_case(db: AsyncSession, case: VisaCase, changes: dict) -> tuple[str, dict] | None:
    """§4.2 checks 2-9 (the route did entry and check 1, under the application row lock). Every check precedes every write, so a
    refusal changes nothing. Returns the audit (action, metadata), or None when nothing changed."""
    if case.decision is not None:
        raise HTTPException(409, VISA_DECIDED)
    if changes["expected_stage"] != case.status:
        raise HTTPException(409, VISA_STALE)
    current = stage_index(case.status)
    if "checklist" in changes and current > 0:
        raise HTTPException(422, VISA_CHECKLIST_LOCKED)
    if "decision" in changes and case.status != "decision":
        raise HTTPException(422, VISA_DECISION_STAGE)
    target = changes.get("to_stage")
    if target is not None and stage_index(target) <= current:
        raise HTTPException(422, VISA_FORWARD_ONLY)
    if target is not None and current <= 0 < stage_index(target):  # VISA-001-AC02, on the checklist this request leaves behind
        checklist = changes.get("checklist", list(case.checklist or []))
        unverified = [c["item"] for c in await checklist_status(db, case.application_id, checklist) if c["verification_status"] != "verified"]
        if unverified:
            raise HTTPException(422, f"Cannot advance past the checklist stage -- not yet verified: {', '.join(unverified)}.")
    check_dates(changes.get("visa_application_date", case.visa_application_date), changes.get("interview_date", case.interview_date))
    changed = [key for key in DETAIL_FIELDS if key in changes and changes[key] != getattr(case, key)]
    for key in changed:
        setattr(case, key, changes[key])
    fields = {"fields": changed} if changed else {}
    if "decision" in changes:
        case.decision, case.decided_at = changes["decision"], datetime.now(UTC)
        return "visa_decision", {"decision": case.decision, **fields}
    if target is not None:
        old, case.status = case.status, target
        return "visa_advance", {"from_stage": old, "to_stage": target, **fields}
    return ("visa_update", fields) if changed else None
```

`apps/api/app/services/agent_applications.py` — import and one detail key (after `"enrollment_check"`):

```python
from app.services.agent_visa import visa_block
...
        "enrollment_check": enrollment_check(found, datetime.now(UTC).date()),
        "visa": await visa_block(db, found.id),  # AGN-012 (DEC-SCOPE-055): agency-only, single-application detail only
```

`apps/api/app/api/agent_applications.py` — docstring gains one sentence (`AGN-012 (DEC-SCOPE-055): Master and Staff run the visa case of an
application from an offer onwards, through its own two routes; the case never moves the application stage.`); imports:

```python
from app.models import AgentOrgMember, AgentStudent, ApplicationStatusHistory, AuditLog, OverseasApplication, University, User, VisaCase
from app.schemas import AgentApplicationCreate, AgentApplicationEnrollment, AgentApplicationStatus, AgentApplicationUpdate, AgentVisaStart, AgentVisaUpdate
from app.services.agent_applications import (..., OFFER_STAGES_ON, ...)
from app.services.agent_visa import VISA_ENROLLED, VISA_EXISTS, VISA_OFFER_NEEDED, VISA_STALE, check_dates, load_case, update_case
```

and the routes, after `save_enrollment`:

```python
async def _visa_entry(db: AsyncSession, user: User, membership: AgentOrgMember, application_id: UUID):
    """AGN-012: the enrollment route's entry (organisation lock, scoped row lock, archived/withdrawn 409) plus enrolled 409 (V5). The
    case is read after the application lock, so every agency visa write for one application is serialised."""
    item = await _locked(db, user, membership, application_id)
    record = await _refuse_closed(db, user, item)
    if item.status == "enrolled":
        raise HTTPException(409, VISA_ENROLLED)
    return item, record


@router.post("/{application_id}/visa", status_code=201)
async def start_visa(application_id: UUID, payload: AgentVisaStart, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-012 (DEC-SCOPE-055) §4.1: start the application's visa case at `checklist`, from an offer onwards; one case per application."""
    membership = _gate(user)
    item, record = await _visa_entry(db, user, membership, application_id)
    if payload.expected_status != item.status:
        raise HTTPException(409, STALE)
    if item.status not in OFFER_STAGES_ON:
        raise HTTPException(422, VISA_OFFER_NEEDED)
    if await load_case(db, item.id) is not None:
        raise HTTPException(409, VISA_EXISTS)
    check_dates(payload.visa_application_date, payload.interview_date)
    db.add(VisaCase(application_id=item.id, status="checklist", checklist=payload.checklist, visa_application_date=payload.visa_application_date, appointment_date=payload.appointment_date, interview_date=payload.interview_date))
    _audit(db, user, "visa_start", item.id, {"checklist_items": len(payload.checklist)})
    await db.commit()
    _log("agent_visa_started", membership, user, item.id, checklist_items=len(payload.checklist))
    return {"application": await detail(db, user, item, record=record)}


@router.patch("/{application_id}/visa")
async def update_visa_case(application_id: UUID, payload: AgentVisaUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-012 §4.2: dates, the checklist (at `checklist` only), a forward move through the checklist gate, or the final decision."""
    membership = _gate(user)
    item, record = await _visa_entry(db, user, membership, application_id)
    case = await load_case(db, item.id)
    if case is None:  # the screen believed a case exists; a 404 would read as "the application is gone"
        raise HTTPException(409, VISA_STALE)
    try:
        outcome = await update_case(db, case, payload.model_dump(exclude_unset=True))
    except HTTPException as refused:
        if refused.status_code == 422 and str(refused.detail).startswith("Cannot advance past the checklist stage"):
            _log("agent_visa_gate_blocked", membership, user, item.id, level=logging.WARNING, from_stage=case.status)
        raise
    if outcome is not None:
        action, metadata = outcome
        _audit(db, user, action, item.id, metadata)
    await db.commit()
    if outcome is not None:
        event = {"visa_decision": "agent_visa_decided", "visa_advance": "agent_visa_advanced", "visa_update": "agent_visa_updated"}[action]
        _log(event, membership, user, item.id, **{k: v for k, v in metadata.items() if k != "decision"})  # never the outcome (§10.3)
    return {"application": await detail(db, user, item, record=record)}
```

`apps/api/app/services/staff_activity.py` — after `"overseas.application.withdraw",`:

```python
    # AGN-012 (DEC-SCOPE-055): visa work on an application; the view shows field names only, never the decision.
    "overseas.application.visa_start",
    "overseas.application.visa_update",
    "overseas.application.visa_advance",
    "overseas.application.visa_decision",
```

- [ ] **Step 4: Run — expect PASS** `API_TEST tests/test_agn_012_visa.py tests/test_agn_013_enrollment.py`
- [ ] **Step 5: Refactor check** — `python -m ruff check app tests/test_agn_012_visa.py tests/agn012_helpers.py`; re-run the same tests.
- [ ] **Step 6: Commit** `git commit -m "feat(agn-012): agency visa routes, checklist gate and detail block"`

---

### Task 4: Authorization, concurrency and unchanged existing behavior

**Files:**
- Test: `apps/api/tests/test_agn_012_security.py`, `apps/api/tests/test_agn_012_concurrency.py`, `apps/api/tests/test_agn_012_unchanged.py`,
  `apps/api/tests/test_agn_021_activity.py` (one test)

These pin behavior Task 3 already produces through the reused gate and lock; each is first run against the Task 3 code. A test that
passes on first run is a characterization guard (recorded as such); one that fails is fixed in the route before moving on.

- [ ] **Step 1: Write the tests** — `apps/api/tests/test_agn_012_security.py`:

```python
"""AGN-012 AC8 -- Master: the organisation; Staff: assigned students only (V1); everyone else refused; refusals write nothing."""

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for, mk_user
from tests.agn012_helpers import VISA, count_cases, mk_case, visa_audits, visa_world

START = {"expected_status": "offer", "checklist": ["Passport"]}


@pytest_asyncio.fixture
async def world(db_session):
    return await visa_world(db_session)


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["master", "staff", "plain"])
async def test_master_and_staff_in_scope_start_and_update(db_session, who):
    w = await visa_world(db_session)
    if who == "plain":  # a staff member without Verify, assigned this student
        w["record"].assigned_member_id = w["plain"]["member"].id
        db_session.add(w["record"])
        await db_session.commit()
    email = w["master"].email if who == "master" else w[who]["user"].email
    async with client_for(email) as c:
        assert (await c.post(VISA.format(w["app"].id), json=START)).status_code == 201
        assert (await c.patch(VISA.format(w["app"].id), json={"expected_stage": "checklist", "appointment_date": "2027-05-01"})).status_code == 200


@pytest.mark.asyncio
async def test_staff_out_of_scope_is_404_and_writes_nothing(db_session, world):
    await mk_case(db_session, world["app"])
    world["record"].assigned_member_id = None  # reassigned away after the screen loaded
    db_session.add(world["record"])
    await db_session.commit()
    async with client_for(world["staff"]["user"].email) as c:
        assert (await c.patch(VISA.format(world["app"].id), json={"expected_stage": "checklist", "appointment_date": "2027-05-01"})).status_code == 404
    assert await visa_audits(db_session, world["app"]) == []


@pytest.mark.asyncio
async def test_other_agency_is_404_for_both_routes(db_session, world):
    async with client_for(world["other"]["master"].email) as c:
        assert (await c.post(VISA.format(world["app"].id), json=START)).status_code == 404
        await mk_case(db_session, world["app"])
        assert (await c.patch(VISA.format(world["app"].id), json={"expected_stage": "checklist", "to_stage": "documentation"})).status_code == 404
    assert await count_cases(db_session, world["app"]) == 1 and await visa_audits(db_session, world["app"]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["counselor", "overseas_admin", "overseas_student", "super_admin"])
async def test_non_agents_are_403(db_session, world, role):
    user = await mk_user(db_session, role=role)
    async with client_for(user.email) as c:
        assert (await c.post(VISA.format(world["app"].id), json=START)).status_code == 403
    assert await count_cases(db_session, world["app"]) == 0


@pytest.mark.asyncio
async def test_the_linked_student_cannot_use_the_agency_route(world):
    # A student with a login linked to the agency is an overseas_student: refused by the agency gate.
    async with client_for(world["linked_user"].email) as c:
        assert (await c.post(VISA.format(world["app"].id), json=START)).status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client, db_session, world):
    assert (await client.post(VISA.format(world["app"].id), json=START)).status_code == 401
    assert (await client.patch(VISA.format(world["app"].id), json={"expected_stage": "checklist"})).status_code == 401
    assert await count_cases(db_session, world["app"]) == 0


@pytest.mark.asyncio
async def test_unknown_application_is_404(world):
    async with client_for(world["master"].email) as c:
        assert (await c.post(VISA.format("00000000-0000-0000-0000-000000000000"), json=START)).status_code == 404
```

`apps/api/tests/test_agn_012_concurrency.py`:

```python
"""AGN-012 AC9 -- two starts at once create one case; two advances from the same stage: one wins, the other is stale."""

import asyncio

import pytest

from tests.agn001_helpers import client_for
from tests.agn012_helpers import VISA, case_of, count_cases, mk_case, visa_audits, visa_world


@pytest.mark.asyncio
async def test_two_simultaneous_starts_create_one_case(db_session):
    w = await visa_world(db_session)
    url, body = VISA.format(w["app"].id), {"expected_status": "offer"}
    async with client_for(w["master"].email) as a, client_for(w["staff"]["user"].email) as b:
        first, second = await asyncio.gather(a.post(url, json=body), b.post(url, json=body))
    assert sorted([first.status_code, second.status_code]) == [201, 409]
    assert await count_cases(db_session, w["app"]) == 1


@pytest.mark.asyncio
async def test_two_simultaneous_advances_one_wins(db_session):
    w = await visa_world(db_session)
    await mk_case(db_session, w["app"], status="documentation")
    url = VISA.format(w["app"].id)
    async with client_for(w["master"].email) as a, client_for(w["staff"]["user"].email) as b:
        first, second = await asyncio.gather(
            a.patch(url, json={"expected_stage": "documentation", "to_stage": "interview_prep"}),
            b.patch(url, json={"expected_stage": "documentation", "to_stage": "tracking"}),
        )
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert (await case_of(db_session, w["app"])).status in {"interview_prep", "tracking"}
    assert len(await visa_audits(db_session, w["app"])) == 1
```

`apps/api/tests/test_agn_012_unchanged.py`:

```python
"""AGN-012 AC10 -- the counselor/admin/student visa routes and responses are unchanged on a case that carries the new columns (V8)."""

from datetime import UTC, date, datetime

import pytest

from app.models import OverseasApplication
from tests.agn001_helpers import client_for, mk_user
from tests.agn003_helpers import mk_university
from tests.agn012_helpers import mk_case

BASE = "/api/v1/workflows/overseas"


@pytest.mark.asyncio
async def test_student_and_admin_responses_keep_their_keys(db_session):
    student = await mk_user(db_session, role="overseas_student")
    admin = await mk_user(db_session, role="overseas_admin")
    university = await mk_university(db_session)
    app = OverseasApplication(student_id=student.id, university_id=university.id, status="visa_documentation", intake="Sep 2027")
    db_session.add(app)
    await db_session.commit()
    case = await mk_case(db_session, app, status="documentation", checklist=["Passport"], visa_application_date=date(2027, 5, 1), interview_date=date(2027, 5, 9), decision="approved", decided_at=datetime.now(UTC))
    async with client_for(student.email) as c:
        checklist = (await c.get(f"{BASE}/applications/{app.id}/visa-checklist")).json()
        status = (await c.get(f"{BASE}/applications/{app.id}/visa-status")).json()
    assert set(checklist) == {"exists", "id", "status", "appointment_date", "tracking_reference", "checklist"}
    assert set(status) == {"exists", "status", "appointment_date", "tracking_reference", "disclaimer"}
    async with client_for(admin.email) as c:
        r = await c.patch(f"{BASE}/visa/{case.id}", json={"status": "checklist"})  # the old route still allows a backward move
        assert (r.status_code, set(r.json())) == (200, {"id", "status"})
        assert (await c.post(f"{BASE}/visa", json={"application_id": str(app.id)})).status_code == 409
```

`apps/api/tests/test_agn_021_activity.py` — append:

```python
@pytest.mark.asyncio
async def test_agent_visa_actions_appear_without_the_decision(db_session):  # AGN-012 §4.6
    from tests.agn012_helpers import VISA, visa_world  # noqa: PLC0415

    w = await visa_world(db_session)
    async with client_for(w["staff"]["user"].email) as s:
        await s.post(VISA.format(w["app"].id), json={"expected_status": "offer"})
        await s.patch(VISA.format(w["app"].id), json={"expected_stage": "checklist", "appointment_date": "2027-05-01"})
    async with client_for(w["master"].email) as m:
        items = (await m.get(f"/api/v1/workflows/overseas/agent/team/staff/{w['staff']['member'].id}/activity")).json()["items"]
    assert [i["action"] for i in items[:2]] == ["overseas.application.visa_update", "overseas.application.visa_start"]
```

- [ ] **Step 2: Run** `API_TEST tests/test_agn_012_security.py tests/test_agn_012_concurrency.py tests/test_agn_012_unchanged.py "tests/test_agn_021_activity.py::test_agent_visa_actions_appear_without_the_decision"`
  — expected PASS (characterization of the reused gate/lock). Any failure: fix the route, re-run.
- [ ] **Step 3: Commit** `git commit -m "test(agn-012): authorization, concurrency and unchanged-behavior guards"`

---

### Task 5: Frontend visa helpers and types

**Files:**
- Modify: `apps/web/lib/agentApplications.ts`
- Test: `apps/web/tests/lib/agentApplications.test.ts` (append a `describe`)

**Interfaces:**
- Produces: `VISA_STAGES`, `VISA_DECISIONS`, `VisaDecision`, `VISA_DECISION_LABELS`, `VISA_DOCUMENT_TYPES`, `VisaChecklistItem`, `Visa`,
  `canStartVisa(status)`, `nextVisaStages(stage)`, `visaChecklistEditable(stage)`, `checklistStatusLabel(status)`; `visa?: Visa | null`
  on `AgentApplicationDetail`.

- [ ] **Step 1: Write the failing test** — append to `apps/web/tests/lib/agentApplications.test.ts` (extend its import list):

```ts
describe("visa helpers (AGN-012)", () => {
  it("offers forward stages only, a legacy stage counting as before checklist", () => {
    expect(nextVisaStages("checklist")).toEqual(["documentation", "interview_prep", "tracking", "decision"]);
    expect(nextVisaStages("tracking")).toEqual(["decision"]);
    expect(nextVisaStages("decision")).toEqual([]);
    expect(nextVisaStages("not_started")).toEqual(["checklist", "documentation", "interview_prep", "tracking", "decision"]);
  });
  it("edits the checklist only at checklist or a legacy stage", () => {
    expect(visaChecklistEditable("checklist")).toBe(true);
    expect(visaChecklistEditable("not_started")).toBe(true);
    expect(visaChecklistEditable("documentation")).toBe(false);
  });
  it("starts a case from an offer onwards", () => {
    expect(["enquiry", "offer", "visa_documentation", "status_tracking", "enrolled", "withdrawn"].map(canStartVisa)).toEqual([false, true, true, true, false, false]);
  });
  it("lists the named document types and words each checklist status", () => {
    expect(VISA_DOCUMENT_TYPES).not.toContain("Other");
    expect(VISA_DOCUMENT_TYPES).toHaveLength(8);
    expect(["verified", "pending", "changes_required", "not_uploaded"].map(checklistStatusLabel)).toEqual(["Verified", "Pending review", "Changes required", "Not uploaded"]);
  });
});
```

- [ ] **Step 2: Run — expect FAIL** (`nextVisaStages is not exported`) `WEB_TEST tests/lib/agentApplications.test.ts`

- [ ] **Step 3: Implement** — in `apps/web/lib/agentApplications.ts` add `import { DOCUMENT_TYPES, OTHER, statusLabel } from "@/lib/agentDocuments";`
  at the top, `visa?: Visa | null;` in `AgentApplicationDetail` (after `enrollment_check`), and after the enrollment block:

```ts
// AGN-012 (DEC-SCOPE-055): the visa case of an application (EVID-015 §5 Step 8). Mirrors services/agent_visa.py; the server is the
// authority (forward-only, the checklist gate, a decision only at `decision`, final once recorded).
export const VISA_STAGES = ["checklist", "documentation", "interview_prep", "tracking", "decision"] as const;
export const VISA_DECISIONS = ["approved", "refused", "withdrawn"] as const;
export type VisaDecision = (typeof VISA_DECISIONS)[number];
export const VISA_DECISION_LABELS: Record<VisaDecision, string> = { approved: "Approved", refused: "Refused", withdrawn: "Withdrawn" };
export const VISA_DOCUMENT_TYPES: readonly string[] = DOCUMENT_TYPES.filter((type) => type !== OTHER); // V6: a named type to match
export type VisaChecklistItem = { item: string; verification_status: string };
export type Visa = {
  id: string;
  stage: string;
  checklist: VisaChecklistItem[];
  visa_application_date: string | null;
  appointment_date: string | null;
  interview_date: string | null;
  decision: VisaDecision | null;
  decided_at: string | null;
  disclaimer: string;
};

// V5: a case starts from an offer onwards -- the stages enrollment uses.
export function canStartVisa(status: string): boolean {
  return canConfirmEnrollment(status);
}
// V3: every later stage (skips allowed); a legacy stage such as `not_started` counts as before checklist.
export function nextVisaStages(stage: string): string[] {
  return VISA_STAGES.slice((VISA_STAGES as readonly string[]).indexOf(stage) + 1);
}
export function visaChecklistEditable(stage: string): boolean {
  return (VISA_STAGES as readonly string[]).indexOf(stage) <= 0;
}
export function checklistStatusLabel(status: string): string {
  return status === "not_uploaded" ? "Not uploaded" : statusLabel(status);
}
```

- [ ] **Step 4: Run — expect PASS** `WEB_TEST tests/lib/agentApplications.test.ts tests/lib/agentDocuments.test.ts`; `npx tsc --noEmit -p .`
- [ ] **Step 5: Commit** `git commit -m "feat(agn-012): visa helpers and types for the agency application"`

---

### Task 6: Visa panel, shared details form, one section form at a time

**Files:**
- Create: `apps/web/components/AgentVisaDetailsForm.tsx`, `apps/web/components/AgentApplicationVisa.tsx`
- Modify: `apps/web/components/AgentApplicationDetail.tsx:5,15,20,52-77,142-148`
- Test: `apps/web/tests/components/AgentApplicationVisa.test.tsx`

**Interfaces:**
- Consumes: Task 5 helpers; `sendJson`, `fieldErrors`, `useFocusAfterRender`, `SESSION_EXPIRED`, `SIGN_IN_PATH`, `formatDateTimeIn`.
- Produces: `<AgentApplicationVisa detail onSaved onFailed onOpenChange />`; `<AgentVisaDetailsForm appId visa checklistEditable busy errors failure onSubmit onCancel />`,
  exports `DETAIL_FIELDS`, `VisaDetails`. Element ids `visa-<part>-<applicationId>`.

- [ ] **Step 1: Write the failing test** — `apps/web/tests/components/AgentApplicationVisa.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationDetail from "@/components/AgentApplicationDetail";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const detail = (over: Record<string, unknown> = {}) => ({
  id: "a1", agent_student_id: "r1", student: "Asha Rao", has_login: false, university: "Uni One", university_id: "u1", university_slug: "u1",
  course: "MSc Data", course_id: "c1", intake: "Sep 2027", status: "offer", application_reference: null, submitted_on: null,
  application_deadline: null, offer_deadline: null, nearest_deadline: null, next_action: null, updated_at: "", created_at: "", read_only_reason: null,
  history: [], enrollment_date: null, university_student_id: null, enrollment_confirmed_at: null, enrollment_check: null, visa: null, ...over,
});
const visa = (over: Record<string, unknown> = {}) => ({
  id: "v1", stage: "checklist", checklist: [{ item: "Passport", verification_status: "not_uploaded" }], visa_application_date: null,
  appointment_date: null, interview_date: null, decision: null, decided_at: null, disclaimer: "Visa decisions are made by the authority.", ...over,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// GET answers with `get`; a write answers with a fresh `write()` Response (a body reads once).
const api = (get: unknown, write: () => Response = () => json({ application: get })) =>
  vi.fn((_: string, init?: RequestInit) => Promise.resolve(init?.method && init.method !== "GET" ? write() : json({ application: get })));
const writes = (fetchMock: ReturnType<typeof vi.fn>) => fetchMock.mock.calls.filter(([, i]) => i?.method && i.method !== "GET");

function mount(fetchMock: ReturnType<typeof vi.fn>, isMaster = true) {
  vi.stubGlobal("fetch", fetchMock);
  render(<AgentApplicationDetail id="a1" isMaster={isMaster} onChanged={vi.fn()} onClose={vi.fn()} />);
}
const region = () => screen.getByRole("region", { name: "Visa" });

describe("AgentApplicationVisa (AGN-012)", () => {
  it("is absent before an offer", async () => {
    mount(api(detail({ status: "university_selection" })));
    await screen.findByText("Asha Rao — Uni One");
    expect(screen.queryByRole("region", { name: "Visa" })).toBeNull();
  });

  it("starts a case: dates and checklist, the displayed status, focus on the notice (Staff too)", async () => {
    const fetchMock = api(detail(), () => json({ application: detail({ visa: visa() }) }, 201));
    mount(fetchMock, false);
    expect(await screen.findByText("No visa case yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start visa case" }));
    await waitFor(() => expect(screen.getByLabelText("Visa application date (optional)")).toHaveFocus());
    fireEvent.change(screen.getByLabelText("Visa application date (optional)"), { target: { value: "2027-05-01" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Passport" }));
    fireEvent.click(within(screen.getByRole("form", { name: "Start visa case" })).getByRole("button", { name: "Start visa case" }));
    await waitFor(() => expect(screen.getByText("Visa case started.")).toHaveFocus());
    const [url, init] = writes(fetchMock)[0];
    expect([url, init!.method]).toEqual(["/api/v1/workflows/overseas/agent/crm/applications/a1/visa", "POST"]);
    expect(JSON.parse(String(init!.body))).toEqual({ expected_status: "offer", checklist: ["Passport"], visa_application_date: "2027-05-01", appointment_date: null, interview_date: null });
    expect(within(region()).getByText("Passport: Not uploaded")).toBeInTheDocument();
  });

  it("puts a date-order 422 on the interview field and keeps the entry", async () => {
    const error = [{ type: "value_error", loc: ["body", "interview_date"], msg: "The interview date cannot be before the visa application date" }];
    mount(api(detail({ visa: visa({ stage: "documentation" }) }), () => json({ detail: error }, 422)));
    fireEvent.click(await screen.findByRole("button", { name: "Edit visa details" }));
    fireEvent.change(screen.getByLabelText("Interview date (optional)"), { target: { value: "2027-04-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save visa details" }));
    const input = screen.getByLabelText("Interview date (optional)");
    await waitFor(() => expect(input).toHaveFocus());
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveValue("2027-04-01");
    expect(screen.getByText("The interview date cannot be before the visa application date")).toHaveAttribute("id", input.getAttribute("aria-describedby"));
    expect(screen.queryByRole("checkbox")).toBeNull(); // past checklist: the checklist is not editable
  });

  it("shows the checklist gate refusal as an alert in the move form", async () => {
    const message = "Cannot advance past the checklist stage -- not yet verified: Passport.";
    const fetchMock = api(detail({ visa: visa() }), () => json({ detail: message }, 422));
    mount(fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Move visa stage" }));
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "documentation" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(message));
    expect(screen.getByRole("alert")).toHaveFocus();
    expect(JSON.parse(String(writes(fetchMock)[0][1]!.body))).toEqual({ expected_stage: "checklist", to_stage: "documentation" });
  });

  it("confirms a skip; Escape goes back to Move", async () => {
    const fetchMock = api(detail({ visa: visa({ stage: "documentation" }) }), () => json({ application: detail({ visa: visa({ stage: "decision" }) }) }));
    mount(fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Move visa stage" }));
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "decision" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    const group = screen.getByRole("group", { name: "Confirm move" });
    expect(within(group).getByText(/skips 2 stages/)).toBeInTheDocument();
    fireEvent.keyDown(group, { key: "Escape" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Move" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, move" }));
    await waitFor(() => expect(screen.getByText("Visa case moved to Decision.")).toHaveFocus());
    expect(writes(fetchMock)).toHaveLength(1);
  });

  it("records a decision once, after confirmation, then is read-only with the disclaimer", async () => {
    const decided = detail({ visa: visa({ stage: "decision", decision: "approved", decided_at: "2026-10-02T10:00:00Z" }) });
    let release: (r: Response) => void = () => {};
    const fetchMock = vi.fn((_: string, init?: RequestInit) =>
      init?.method === "PATCH" ? new Promise<Response>((resolve) => (release = resolve)) : Promise.resolve(json({ application: detail({ visa: visa({ stage: "decision" }) }) })),
    );
    mount(fetchMock);
    expect(await screen.findByText("Visa decisions are made by the authority.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Record decision" }));
    fireEvent.click(screen.getByRole("radio", { name: "Approved" }));
    fireEvent.click(screen.getByRole("button", { name: "Record decision" }));
    const yes = within(screen.getByRole("group", { name: "Confirm decision" })).getByRole("button", { name: "Yes, record decision" });
    fireEvent.click(yes);
    fireEvent.click(yes); // same tick: the in-flight guard drops it
    release(json({ application: decided }));
    await waitFor(() => expect(screen.getByText("Visa decision recorded.")).toHaveFocus());
    expect(writes(fetchMock)).toHaveLength(1);
    expect(JSON.parse(String(writes(fetchMock)[0][1]!.body))).toEqual({ expected_stage: "decision", decision: "approved" });
    expect(within(region()).getByText("Approved")).toBeInTheDocument();
    expect(within(region()).queryByRole("button")).toBeNull();
  });

  it("a 409 reloads the detail and announces the server's words", async () => {
    const fetchMock = api(detail({ visa: visa({ stage: "documentation" }) }), () => json({ detail: "This visa case changed since you opened it -- reload to see its current stage" }, 409));
    mount(fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Edit visa details" }));
    fireEvent.click(screen.getByRole("button", { name: "Save visa details" }));
    await waitFor(() => expect(screen.getByText(/changed since you opened it/)).toHaveFocus());
    expect(fetchMock.mock.calls.filter(([, i]) => !i?.method || i.method === "GET")).toHaveLength(2);
    expect(screen.queryByRole("form", { name: "Edit visa details" })).toBeNull();
  });

  it.each([
    [401, /Sign in again/],
    [500, /Something went wrong on our side/],
  ])("a %s keeps the entry with its own message", async (status, text) => {
    mount(api(detail({ visa: visa({ stage: "documentation" }) }), () => json({ detail: "x" }, status)));
    fireEvent.click(await screen.findByRole("button", { name: "Edit visa details" }));
    fireEvent.click(screen.getByRole("button", { name: "Save visa details" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(text));
    expect(screen.getByRole("form", { name: "Edit visa details" })).toBeInTheDocument();
  });

  it("one section form at a time; Cancel returns focus to its opener", async () => {
    mount(api(detail({ visa: visa() })));
    fireEvent.click(await screen.findByRole("button", { name: "Edit visa details" }));
    expect(screen.queryByRole("button", { name: "Enroll student" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Update status" })).toBeNull(); // the application status form is hidden too
    fireEvent.click(within(screen.getByRole("form", { name: "Edit visa details" })).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit visa details" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Enroll student" }));
    expect(screen.queryByRole("region", { name: "Visa" })).toBeNull();
  });

  it.each([
    ["withdrawn", { status: "withdrawn", read_only_reason: "withdrawn" }],
    ["enrolled", { status: "enrolled" }],
  ])("a %s application shows its case without actions", async (_, over) => {
    mount(api(detail({ ...over, visa: visa({ stage: "documentation" }) })));
    expect(await screen.findByText("Passport: Not uploaded")).toBeInTheDocument();
    expect(within(region()).queryByRole("button")).toBeNull();
  });
});
```

- [ ] **Step 2: Run — expect FAIL** (`Unable to find role="region" name="Visa"` / text "No visa case yet.")
  `WEB_TEST tests/components/AgentApplicationVisa.test.tsx`

- [ ] **Step 3: Implement** — `apps/web/components/AgentVisaDetailsForm.tsx`:

```tsx
"use client";

import { FormEvent, ReactNode, useState } from "react";
import { Visa, VISA_DOCUMENT_TYPES } from "@/lib/agentApplications";

export const DETAIL_FIELDS = ["visa_application_date", "appointment_date", "interview_date", "checklist"] as const;
export type DetailField = (typeof DETAIL_FIELDS)[number];
type DateField = Exclude<DetailField, "checklist">;
export type VisaDetails = { checklist: string[] } & Record<DateField, string | null>;

type Props = {
  appId: string;
  visa: Visa | null; // null: starting a case
  checklistEditable: boolean;
  busy: boolean;
  errors: Partial<Record<DetailField, string>>;
  failure: ReactNode;
  onSubmit: (values: VisaDetails) => void;
  onCancel: () => void;
};

const DATES: { field: DateField; label: string }[] = [
  { field: "visa_application_date", label: "Visa application date (optional)" },
  { field: "appointment_date", label: "Appointment date (optional)" },
  { field: "interview_date", label: "Interview date (optional)" },
];

// AGN-012 (DEC-SCOPE-055): the dates and document checklist of a visa case, shared by Start and Edit. An emptied date is sent as null
// (it clears the stored one). The server checks the date order and the checklist; its field errors arrive in `errors`.
export default function AgentVisaDetailsForm({ appId, visa, checklistEditable, busy, errors, failure, onSubmit, onCancel }: Props) {
  const [checklist, setChecklist] = useState<string[]>(visa ? visa.checklist.map((c) => c.item) : []);
  const [dates, setDates] = useState<Record<DateField, string>>({
    visa_application_date: visa?.visa_application_date ?? "",
    appointment_date: visa?.appointment_date ?? "",
    interview_date: visa?.interview_date ?? "",
  });
  const id = (part: string) => `visa-${part}-${appId}`;
  const described = (field: DetailField) => (errors[field] ? { "aria-invalid": true as const, "aria-describedby": id(`${field}-error`) } : {});
  const error = (field: DetailField) =>
    errors[field] && (
      <p id={id(`${field}-error`)} className="form-error">
        {errors[field]}
      </p>
    );

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit({ checklist, visa_application_date: dates.visa_application_date || null, appointment_date: dates.appointment_date || null, interview_date: dates.interview_date || null });
  }
  return (
    <form className="form" aria-label={visa ? "Edit visa details" : "Start visa case"} aria-busy={busy} onSubmit={submit}>
      {DATES.map(({ field, label }) => (
        <div className="field" key={field}>
          <label htmlFor={id(field)}>{label}</label>
          <input id={id(field)} type="date" min="2000-01-01" max="2100-12-31" value={dates[field]} onChange={(event) => setDates((now) => ({ ...now, [field]: event.target.value }))} {...described(field)} />
          {error(field)}
        </div>
      ))}
      {checklistEditable && (
        <fieldset id={id("checklist")} tabIndex={-1} className="form-section" {...described("checklist")}>
          <legend>Documents the visa needs</legend>
          {VISA_DOCUMENT_TYPES.map((type) => (
            <label key={type} className="pf-check">
              <input type="checkbox" checked={checklist.includes(type)} onChange={(event) => setChecklist((now) => (event.target.checked ? [...now, type] : now.filter((t) => t !== type)))} />
              {type}
            </label>
          ))}
          {error("checklist")}
        </fieldset>
      )}
      {failure}
      <div className="actions">
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : visa ? "Save visa details" : "Start visa case"}
        </button>
        <button type="button" className="btn ghost small" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
```

`apps/web/components/AgentApplicationVisa.tsx`:

```tsx
"use client";

import Link from "next/link";
import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import AgentVisaDetailsForm, { DETAIL_FIELDS, VisaDetails } from "./AgentVisaDetailsForm";
import { SESSION_EXPIRED, SIGN_IN_PATH } from "@/lib/activityFeedback";
import { sendJson } from "@/lib/apiErrors";
import {
  AgentApplicationDetail,
  APPLICATIONS_URL,
  canStartVisa,
  checklistStatusLabel,
  nextVisaStages,
  stageLabel,
  VISA_DECISION_LABELS,
  VISA_DECISIONS,
  VisaDecision,
  visaChecklistEditable,
} from "@/lib/agentApplications";
import { fieldErrors } from "@/lib/agentStudents";
import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Props = {
  detail: AgentApplicationDetail;
  onSaved: (d: AgentApplicationDetail, message: string) => void;
  onFailed: (message: string, status?: number) => void;
  onOpenChange?: (open: boolean) => void;
};
type Mode = "details" | "move" | "decide" | null;

// The enrollment form's wording (AGN-013 browser QA): the form words its own failures and keeps the entry; a 409/404 goes to the
// detail, which reloads to the real state.
const EXPIRED = `${SESSION_EXPIRED} Your entry is kept; sign in again in a new tab, then save.`;
const SERVER_ERROR = "Something went wrong on our side. Please try again; your entry is kept.";
const FIELDS = [...DETAIL_FIELDS, "to_stage", "decision"] as const;
type Field = (typeof FIELDS)[number];

// AGN-012 (DEC-SCOPE-055): Step 8. Master and Staff start the visa case from an offer onwards, keep its dates and document checklist,
// move it forward (a skip is confirmed) and record the authority's decision once (confirmed; final). The displayed stage travels as
// `expected_stage`, so a stale screen gets a 409 and the detail reloads. Read-only for a withdrawn/archived/enrolled application.
export default function AgentApplicationVisa({ detail, onSaved, onFailed, onOpenChange }: Props) {
  const visa = detail.visa ?? null;
  const [mode, setMode] = useState<Mode>(null);
  const [target, setTarget] = useState("");
  const [decision, setDecision] = useState<VisaDecision | "">("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ text: string; expired?: boolean } | null>(null);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const inFlight = useRef(false); // a same-tick second click sends nothing
  const focusAfter = useFocusAfterRender();
  const id = (part: string) => `visa-${part}-${detail.id}`;

  const writable = !detail.read_only_reason && detail.status !== "enrolled" && !visa?.decision;
  if (!visa && (!writable || !canStartVisa(detail.status))) return null;
  const forward = visa ? nextVisaStages(visa.stage) : [];
  const skipped = forward.indexOf(target);

  function open(next: Exclude<Mode, null>, focus: string) {
    setMode(next);
    onOpenChange?.(true); // the detail hides Enrollment and the status form while this form is open
    focusAfter(id(focus));
  }
  function close(opener: string) {
    setMode(null);
    setTarget("");
    setDecision("");
    setConfirming(false);
    setFailure(null);
    setErrors({});
    onOpenChange?.(false);
    focusAfter(id(opener));
  }
  async function send(body: Record<string, unknown>, message: string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    setErrors({});
    const outcome = await sendJson(`${APPLICATIONS_URL}/${detail.id}/visa`, visa ? "PATCH" : "POST", body); // never throws
    inFlight.current = false;
    setBusy(false);
    setConfirming(false);
    if (!outcome.ok) {
      if (outcome.status === 409 || outcome.status === 404) {
        setMode(null); // stale input must not stay on screen; the detail reloads the real state
        return onFailed(outcome.message, outcome.status);
      }
      const onFields = outcome.status === 422 ? fieldErrors(outcome.detail, FIELDS) : null;
      if (onFields) {
        setErrors(onFields);
        return focusAfter(id(FIELDS.find((f) => onFields[f])!));
      }
      const status = outcome.status ?? 0;
      setFailure(status === 401 ? { text: EXPIRED, expired: true } : { text: status >= 500 ? SERVER_ERROR : outcome.message });
      return focusAfter(id("failure"));
    }
    const next = (outcome.data as { application?: AgentApplicationDetail }).application;
    if (!next) return onFailed("The change could not be confirmed. Reload to see the current visa case.");
    onSaved(next, message);
  }
  function saveDetails({ checklist, ...dates }: VisaDetails) {
    if (!visa) return send({ expected_status: detail.status, checklist, ...dates }, "Visa case started.");
    send({ expected_stage: visa.stage, ...dates, ...(visaChecklistEditable(visa.stage) ? { checklist } : {}) }, "Visa details saved.");
  }
  const move = () => send({ expected_stage: visa!.stage, to_stage: target }, `Visa case moved to ${stageLabel(target)}.`);
  const decide = () => send({ expected_stage: visa!.stage, decision }, "Visa decision recorded.");
  function submitMove(event: FormEvent) {
    event.preventDefault();
    if (skipped > 0) setConfirming(true); // a skip is confirmed first
    else move();
  }
  function submitDecision(event: FormEvent) {
    event.preventDefault();
    setConfirming(true);
  }
  function back(focus: string) {
    setConfirming(false);
    focusAfter(id(focus));
  }
  const invalid = (field: Field) => (errors[field] ? { "aria-invalid": true as const, "aria-describedby": id(`${field}-error`) } : {});
  const fieldError = (field: Field) =>
    errors[field] && (
      <p id={id(`${field}-error`)} className="form-error">
        {errors[field]}
      </p>
    );
  const failureNode = failure && (
    <p id={id("failure")} tabIndex={-1} className="form-error" role="alert">
      {failure.text}
      {failure.expired && (
        <>
          {" "}
          <Link href={SIGN_IN_PATH} target="_blank" rel="noopener">
            Sign in again
          </Link>
        </>
      )}
    </p>
  );
  const confirmGroup = (label: string, text: string, yes: string, onYes: () => void, backTo: string) => (
    <div role="group" aria-label={label} onKeyDown={(event: KeyboardEvent) => event.key === "Escape" && back(backTo)}>
      <p>{text}</p>
      <div className="actions">
        <button type="button" className="btn small" disabled={busy} onClick={onYes} autoFocus>
          {busy ? "Saving…" : yes}
        </button>
        <button type="button" className="btn ghost small" onClick={() => back(backTo)}>
          Go back
        </button>
      </div>
    </div>
  );
  const submitRow = (submitId: string, label: string, disabled: boolean, opener: string) => (
    <div className="actions">
      <button id={id(submitId)} className="btn small" disabled={busy || disabled}>
        {busy ? "Saving…" : label}
      </button>
      <button type="button" className="btn ghost small" onClick={() => close(opener)}>
        Cancel
      </button>
    </div>
  );

  return (
    <section aria-labelledby={id("heading")}>
      <h5 id={id("heading")}>Visa</h5>
      {!visa ? (
        <p className="muted">No visa case yet.</p>
      ) : (
        <>
          <p>
            <span className="badge">{stageLabel(visa.stage)}</span>
          </p>
          <dl className="card-stack">
            <dt>Visa application date</dt>
            <dd>{visa.visa_application_date ?? "Not recorded"}</dd>
            <dt>Appointment</dt>
            <dd>{visa.appointment_date ?? "Not recorded"}</dd>
            <dt>Interview</dt>
            <dd>{visa.interview_date ?? "Not recorded"}</dd>
            {visa.decision && (
              <>
                <dt>Decision</dt>
                <dd>{VISA_DECISION_LABELS[visa.decision]}</dd>
                <dt>Recorded</dt>
                <dd>{visa.decided_at ? formatDateTimeIn(visa.decided_at, viewerTimeZone(), true) : "—"}</dd>
              </>
            )}
          </dl>
          <h6>Document checklist</h6>
          {visa.checklist.length === 0 ? (
            <p className="muted">No documents are required on this checklist.</p>
          ) : (
            <ul aria-label="Document checklist">
              {visa.checklist.map((c) => (
                <li key={c.item}>
                  {c.item}: {checklistStatusLabel(c.verification_status)}
                </li>
              ))}
            </ul>
          )}
          {writable && visaChecklistEditable(visa.stage) && visa.checklist.length > 0 && (
            <p className="muted">Upload each document for this application under Documents; it counts once it is verified.</p>
          )}
          {(visa.decision || visa.stage === "decision") && <p className="muted">{visa.disclaimer}</p>}
        </>
      )}
      {writable && mode === null && (
        <div className="actions">
          <button id={id(visa ? "edit" : "start")} type="button" className="btn secondary small" onClick={() => open("details", "visa_application_date")}>
            {visa ? "Edit visa details" : "Start visa case"}
          </button>
          {forward.length > 0 && (
            <button id={id("move")} type="button" className="btn secondary small" onClick={() => open("move", "to_stage")}>
              Move visa stage
            </button>
          )}
          {visa?.stage === "decision" && (
            <button id={id("decide")} type="button" className="btn secondary small" onClick={() => open("decide", "decision")}>
              Record decision
            </button>
          )}
        </div>
      )}
      {mode === "details" && (
        <AgentVisaDetailsForm
          appId={detail.id}
          visa={visa}
          checklistEditable={!visa || visaChecklistEditable(visa.stage)}
          busy={busy}
          errors={errors}
          failure={failureNode}
          onSubmit={saveDetails}
          onCancel={() => close(visa ? "edit" : "start")}
        />
      )}
      {mode === "move" && (
        <form className="form" aria-label="Move visa stage" onSubmit={submitMove}>
          <div className="field">
            <label htmlFor={id("to_stage")}>Move to</label>
            <select id={id("to_stage")} value={target} onChange={(event) => (setTarget(event.target.value), setConfirming(false))} {...invalid("to_stage")}>
              <option value="">Choose a stage</option>
              {forward.map((stage) => (
                <option key={stage} value={stage}>
                  {stageLabel(stage)}
                </option>
              ))}
            </select>
            {fieldError("to_stage")}
          </div>
          {failureNode}
          {confirming
            ? confirmGroup("Confirm move", `This skips ${skipped} stage${skipped === 1 ? "" : "s"}. Move to ${stageLabel(target)} anyway?`, "Yes, move", move, "move-submit")
            : submitRow("move-submit", "Move", !target, "move")}
        </form>
      )}
      {mode === "decide" && (
        <form className="form" aria-label="Record visa decision" onSubmit={submitDecision}>
          <fieldset id={id("decision")} tabIndex={-1} className="form-section" {...invalid("decision")}>
            <legend>The authority&apos;s decision</legend>
            {VISA_DECISIONS.map((value) => (
              <label key={value} className="pf-check">
                <input type="radio" name={id("decision-value")} value={value} checked={decision === value} onChange={() => (setDecision(value), setConfirming(false))} />
                {VISA_DECISION_LABELS[value]}
              </label>
            ))}
            {fieldError("decision")}
          </fieldset>
          {failureNode}
          {confirming && decision
            ? confirmGroup("Confirm decision", `Record “${VISA_DECISION_LABELS[decision]}”? A recorded decision cannot be changed.`, "Yes, record decision", decide, "decide-submit")
            : submitRow("decide-submit", "Record decision", !decision, "decide")}
        </form>
      )}
    </section>
  );
}
```

`apps/web/components/AgentApplicationDetail.tsx`:
- import `AgentApplicationVisa from "./AgentApplicationVisa";`
- header comment gains: `AGN-012: the Visa section (Master and Staff); one section form (Visa or Enrollment) is open at a time.`
- replace `const [enrolling, setEnrolling] = useState(false); …` with
  `const [openForm, setOpenForm] = useState<"enrollment" | "visa" | null>(null); // QA13-06, AGN-012: one section form at a time, no competing status action`
- in `saved` and `failed`, `setEnrolling(false)` → `setOpenForm(null)`
- rename `enrollmentSaved` → `sectionSaved` (same body)
- the action block becomes:

```tsx
      {!editing && (
        // A status, visa stage or decision change starts the section forms afresh.
        <Fragment key={`${detail.status}|${detail.visa?.stage ?? ""}|${detail.visa?.decision ?? ""}`}>
          {openForm !== "enrollment" && (
            <AgentApplicationVisa detail={detail} onSaved={sectionSaved} onFailed={editFailed} onOpenChange={(open) => setOpenForm(open ? "visa" : null)} />
          )}
          {openForm !== "visa" && (
            <AgentApplicationEnrollment detail={detail} isMaster={isMaster} onSaved={sectionSaved} onFailed={editFailed} onOpenChange={(open) => setOpenForm(open ? "enrollment" : null)} />
          )}
          {!detail.read_only_reason && !openForm && <AgentApplicationStatusForm detail={detail} onSaved={saved} onFailed={failed} />}
        </Fragment>
      )}
```

- [ ] **Step 4: Run — expect PASS** `WEB_TEST tests/components/AgentApplicationVisa.test.tsx tests/components/AgentApplicationEnrollment.test.tsx tests/components/AgentApplicationDetail.test.tsx`
- [ ] **Step 5: Refactor + static checks** — `npx tsc --noEmit -p .` and `npx eslint components/AgentApplicationVisa.tsx components/AgentVisaDetailsForm.tsx components/AgentApplicationDetail.tsx lib/agentApplications.ts`; re-run Step 4.
- [ ] **Step 6: Commit** `git commit -m "feat(agn-012): agency Visa section in the application detail"`

---

### Task 7: Browser spec (written now; run in the browser-validation phase)

**Files:**
- Create: `apps/web/tests/e2e/agn-012-visa.spec.ts`

- [ ] **Step 1: Write the spec** (the `applicationAtOffer` helper of `agn-013-enrollment.spec.ts`, copied — specs in this repo do not
  import each other):

```ts
import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { pickFromList } from "./helpers/pick";

// AGN-012 (DEC-SCOPE-055) -- a Master starts a visa case from an offer, the date-order error lands on the interview field, a skip is
// confirmed, the decision is recorded once and the case turns read-only; 320 px. Unique names per run (shared E2E DB); the set-up is
// agn-013-enrollment.spec.ts's.
const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

async function applicationAtOffer(page: Page, name: string) {
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  await form.getByRole("button", { name: "Save student" }).click();
  await expect(page.getByText(`${name} added.`)).toBeVisible();

  const universities = await (await page.request.get("/api/v1/public/universities")).json();
  await page.goto("/overseas/agent/applications");
  await pickFromList(page.getByRole("combobox", { name: "Linked student" }), name, new RegExp(`^${name} — no login$`));
  await page.locator("#agent-app-university").selectOption(universities.find((u: { slug: string }) => u.slug === "university-of-manchester").id);
  await page.getByLabel("Intake (required)").fill("Sep 2027");
  await page.getByRole("button", { name: /Create application/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "Application created." })).toBeVisible();

  await page.getByRole("list", { name: "Applications", exact: true }).getByRole("button", { name: new RegExp(`^View ${name} — `) }).click();
  const detail = page.getByRole("region", { name: new RegExp(`^${name} — `) });
  await detail.getByLabel("Move to").selectOption("offer");
  await detail.getByRole("button", { name: "Update status" }).click();
  await expect(detail.getByRole("status")).toHaveText("Status updated to Offer.");
  return detail;
}

test("a Master runs a visa case from an offer to a recorded decision (AC1-AC5, AC11)", async ({ page }) => {
  const name = `E2E Visa ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  const detail = await applicationAtOffer(page, name);
  const visa = detail.getByRole("region", { name: "Visa" });
  await visa.getByRole("button", { name: "Start visa case" }).click();
  await visa.getByLabel("Visa application date (optional)").fill("2027-05-01");
  await visa.getByRole("form", { name: "Start visa case" }).getByRole("button", { name: "Start visa case" }).click();
  await expect(detail.getByText("Visa case started.")).toBeVisible();
  await visa.getByRole("button", { name: "Edit visa details" }).click();
  await visa.getByLabel("Interview date (optional)").fill("2027-04-01");
  await visa.getByRole("button", { name: "Save visa details" }).click();
  await expect(visa.getByText("The interview date cannot be before the visa application date")).toBeVisible();
  await visa.getByLabel("Interview date (optional)").fill("2027-05-20");
  await visa.getByRole("button", { name: "Save visa details" }).click();
  await expect(visa.getByText("2027-05-20")).toBeVisible();
  await visa.getByRole("button", { name: "Move visa stage" }).click();
  await visa.getByLabel("Move to").selectOption("decision");
  await visa.getByRole("button", { name: "Move", exact: true }).click();
  await visa.getByRole("button", { name: "Yes, move" }).click();
  await visa.getByRole("button", { name: "Record decision" }).click();
  await visa.getByRole("radio", { name: "Approved" }).check();
  await visa.getByRole("button", { name: "Record decision" }).click();
  await visa.getByRole("button", { name: "Yes, record decision" }).click();
  await expect(detail.getByText("Visa decision recorded.")).toBeVisible();
  await expect(visa.getByRole("button")).toHaveCount(0);
});

test("the visa section fits a 320 px screen (AC11)", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await signIn(page, "agent@edusphere.local", "Demo@123");
  const detail = await applicationAtOffer(page, `E2E Visa320 ${stamp()}`);
  await detail.getByRole("region", { name: "Visa" }).getByRole("button", { name: "Start visa case" }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
```

- [ ] **Step 2: Type-check only** — `npx tsc --noEmit -p .` (the spec runs against a live stack in the browser-validation phase).
- [ ] **Step 3: Commit** `git commit -m "test(agn-012): browser spec for the agency visa flow"`

---

### Task 8: Documentation and traceability

**Files:** `docs/architecture/API_CONTRACT.md` (after the AGN-013 block), `docs/architecture/DATA_MODEL.md` §6.5, `docs/architecture/RBAC_MATRIX.md`
(§6 agent table: row "Manage Visa Case" — Master ✓, Staff ✓ assigned), `docs/delivery/ENHANCEMENT_BACKLOG.md` (an `## AGN-012` section before
`## 2. Dependency graph`), `docs/quality/RTM.md` (AGN-012 row: AC1–AC12 → tests), `docs/delivery/AGENT_CRM_BACKLOG.md` (status table row
and ang-012 status line), spec §11 "Implementation notes" (the three deviations above), plan checkboxes.

- [ ] **Step 1:** write each entry in the style of its AGN-013 neighbour, citing `DEC-SCOPE-055`, the routes, migration `0061`, the tests;
  status "implemented; browser validation and Codex review pending" — never "complete".
- [ ] **Step 2:** `git diff --stat` to confirm only docs changed; commit `docs(agn-012): contract, data model, RBAC, backlog and RTM`.

---

## Self-review

- Spec coverage: §3 → Task 2; §4.1–4.5 → Tasks 1, 3; §4.6 → Task 3 (+ Task 4 activity test); §5 → Tasks 5–6; §6/§10.3 → Tasks 3–4;
  §7 AC1–AC7, AC12 → Task 3, AC8–AC10 → Task 4, AC11 → Tasks 6–7; §8 → all; docs → Task 8.
- Types: `visa_block` keys = TS `Visa` fields; `update_case` actions = audit names = allowlist = log events map; element ids `visa-<part>-<id>`
  match the focus targets (`visa_application_date`, `to_stage`, `decision`, `checklist`, `failure`, `move-submit`, `decide-submit`, `edit`, `start`, `move`, `decide`).
- Review Focus 1–5 each name their pinning test.
