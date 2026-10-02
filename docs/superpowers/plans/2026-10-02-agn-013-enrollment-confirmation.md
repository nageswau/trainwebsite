# AGN-013 Enrollment Confirmation Implementation Plan

> **Historical plan.** Written before merging `main` @ `9adcbca`. Since then the migration is `0060_agent_app_enrollment` (after
> `0059_agent_tasks`; it was `0058` here) and the decision is `DEC-SCOPE-054` (it was `052` here). The code is the authority.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An agency Master confirms an application's enrollment (date, optional university student ID) through a dedicated route
that moves it to `enrolled` and fires the existing commission trigger exactly once; corrections never duplicate it.

**Architecture:** One `PUT …/agent/crm/applications/{id}/enrollment` route in the AGN-008 router (`app/api/agent_applications.py`),
using its lock order (organisation → row), its audit and log helpers, and `workflows._maybe_trigger_agent_commission` unchanged.
Three nullable columns on `overseas_applications` (migration `0058`). The intake check is a pure function computed on read. One new
React component in the application detail.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL, Pydantic 2, pytest + pytest-asyncio + httpx; Next.js 15, React,
TypeScript, vitest + Testing Library, Playwright. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-02-agn-013-enrollment-confirmation-design.md`

## Global Constraints

- Route: `PUT /api/v1/workflows/overseas/agent/crm/applications/{id}/enrollment`; response `{"application": detail}`.
- Master only (`403 "Only an agency Master can confirm enrollment"`); enrollable stages `offer`, `visa_documentation`, `status_tracking`
  (else `422 "An offer is needed before enrollment"`).
- `enrollment_date` required, 2000–2100; `university_student_id` optional, ≤ 60, `clean_free_text`; `expected_status` required; `notes` ≤ 2000.
- `enrollment_check` ∈ `"after_intake" | "intake_unrecognised" | null`, computed on read, never blocks.
- No change to `agent_commissions`, to `POST …/status` (still 403 for `enrolled`), or to any counselor/admin/rep route.
- The university student ID and notes never appear in logs or audit metadata.
- Lite test runs only (the owner runs the full suites). No completion claim: browser validation and Codex review follow.

## Test commands

`API_TEST <paths>` (isolated compose project `agn013`; Postgres/Redis already up):

```bash
docker compose -p agn013 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "C:/Users/kunam/Documents/project/trainwebsite/.claude/worktrees/agn-013/apps/api:/app" \
  api-test sh -c "alembic upgrade head && python -m pytest -q <paths>"
```

`WEB_TEST <paths>`: `cd apps/web && npx vitest run <paths>`

## Review Focus

1. A counselor enrolls while a Master's confirmation is queued on the row lock → the Master's request is a 409 (stale); no second
   commission. Pinned in Task 4 (`test_counselor_enrolment_landing_first_turns_the_agency_call_into_a_stale_refusal`).
2. An application a counselor enrolled long ago (no details) → a Master can add details; no commission row is created by that call.
   Pinned in Task 3 (`test_master_adds_details_to_a_counselor_enrolled_application`).
3. Intake text with a month name inside other words ("Fall 2027", "Next intake", "Spring") → `intake_unrecognised`, not a crash or a
   wrong month. Pinned in Task 1.
4. A Staff member sending a well-formed body for an application in their own scope → 403, nothing written. Pinned in Task 3.
5. A double click on "Yes, confirm enrollment" → one request. Pinned in Task 5 (in-flight guard test).

---

### Task 1: Intake parser and `enrollment_check` (pure)

**Files:**
- Modify: `apps/api/app/services/agent_applications.py`
- Test: `apps/api/tests/test_agn_013_intake.py`

**Interfaces:**
- Produces: `intake_end(text: str | None) -> date | None`; `enrollment_check(app, today: date) -> str | None` (reads
  `app.enrollment_date`, `app.intake`); constants `ENROLLABLE = ("offer", "visa_documentation", "status_tracking")`,
  `OFFER_NEEDED`, `MASTER_ONLY_ENROLLMENT`.

- [ ] **Step 1: failing tests**

```python
"""AGN-013 (DEC-SCOPE-052 E2) -- the best-effort intake parser and the enrollment date check; pure functions."""

from datetime import date
from types import SimpleNamespace

import pytest

from app.services.agent_applications import enrollment_check, intake_end


@pytest.mark.parametrize(
    ("text", "end"),
    [
        ("Sep 2027", date(2027, 9, 30)),
        ("Sept. 2027", date(2027, 9, 30)),
        ("September 2027", date(2027, 9, 30)),
        ("february 2028", date(2028, 2, 29)),
        ("09/2027", date(2027, 9, 30)),
        ("9-2027", date(2027, 9, 30)),
        ("2027-09", date(2027, 9, 30)),
        ("2027/1", date(2027, 1, 31)),
        ("Intake: Jan 2028 (main)", date(2028, 1, 31)),
    ],
)
def test_intake_end_recognises_month_and_year(text, end):
    assert intake_end(text) == end


@pytest.mark.parametrize("text", [None, "", "Next intake", "Fall 2027", "Spring", "13/2027", "2027", "Sep 1999", "Mayday 2027"])
def test_intake_end_returns_none_when_unrecognised(text):
    assert intake_end(text) is None


def _app(enrolled, intake="Sep 2027"):
    return SimpleNamespace(enrollment_date=enrolled, intake=intake)


TODAY = date(2026, 10, 2)


@pytest.mark.parametrize(
    ("enrolled", "intake", "expected"),
    [
        (None, "Sep 2027", None),
        (date(2027, 9, 15), "Sep 2027", None),
        (date(2027, 10, 1), "Sep 2027", "after_intake"),
        (date(2026, 9, 1), "Jan 2026", None),  # after the intake, but not in the future
        (date(2027, 10, 1), "Next intake", "intake_unrecognised"),
    ],
)
def test_enrollment_check(enrolled, intake, expected):
    assert enrollment_check(_app(enrolled, intake), TODAY) == expected
```

- [ ] **Step 2:** `API_TEST tests/test_agn_013_intake.py` → FAIL (`ImportError: cannot import name 'enrollment_check'`).
- [ ] **Step 3: implement** in `services/agent_applications.py` (add `import calendar`, `import re`):

```python
ENROLLABLE = ("offer", "visa_documentation", "status_tracking")  # AGN-013 E6: an offer is needed before enrollment
OFFER_NEEDED = "An offer is needed before enrollment"
MASTER_ONLY_ENROLLMENT = "Only an agency Master can confirm enrollment"
_MONTHS = {
    name: number
    for number, names in enumerate(("jan january", "feb february", "mar march", "apr april", "may", "jun june", "jul july", "aug august", "sep sept september", "oct october", "nov november", "dec december"), 1)
    for name in names.split()
}
_NAMED_INTAKE = re.compile(r"\b([a-z]+)\.?\s*,?\s*(\d{4})\b")
_NUMERIC_INTAKE = re.compile(r"\b(?:(\d{1,2})\s*[/-]\s*(\d{4})|(\d{4})\s*[/-]\s*(\d{1,2}))\b")


def intake_end(text: str | None) -> date | None:
    """AGN-013 E2: intake is free text, so this is best effort -- the last day of the month in "Sep 2027", "September 2027",
    "09/2027" or "2027-09"; None when no month and year are found (the caller says so instead of guessing)."""
    value = (text or "").lower()
    found = next(((int(year), _MONTHS[word]) for word, year in _NAMED_INTAKE.findall(value) if word in _MONTHS), None)
    if found is None and (match := _NUMERIC_INTAKE.search(value)):
        found = (int(match[2]), int(match[1])) if match[1] else (int(match[3]), int(match[4]))
    if found is None or not 1 <= found[1] <= 12 or not 2000 <= found[0] <= 2100:
        return None
    year, month = found
    return date(year, month, calendar.monthrange(year, month)[1])


def enrollment_check(app, today: date) -> str | None:
    """AGN-013 E2: a warning, never a block -- a future enrollment date after the intake month, or an intake that cannot be read."""
    if app.enrollment_date is None:
        return None
    end = intake_end(app.intake)
    if end is None:
        return "intake_unrecognised"
    return "after_intake" if app.enrollment_date > end and app.enrollment_date > today else None
```

- [ ] **Step 4:** rerun → PASS.
- [ ] **Step 5:** commit `feat(agn-013): best-effort intake parser and enrollment date check`.

---

### Task 2: Columns, migration `0058`, schema, detail fields

**Files:**
- Modify: `apps/api/app/models.py` (`OverseasApplication`), `apps/api/app/schemas.py`, `apps/api/app/services/agent_applications.py` (`detail`)
- Create: `apps/api/alembic/versions/0058_agent_app_enrollment.py`
- Test: `apps/api/tests/test_agn_013_migration.py`, `apps/api/tests/test_agn_013_schemas.py`

**Interfaces:**
- Produces: columns `enrollment_date: date | None`, `university_student_id: str | None` (60), `enrollment_confirmed_at: datetime | None`;
  `AgentApplicationEnrollment(enrollment_date: date, university_student_id: str | None, expected_status: str, notes: str | None)`;
  `detail()` keys `enrollment_date`, `university_student_id`, `enrollment_confirmed_at`, `enrollment_check`; migration `COLUMNS`.

- [ ] **Step 1: failing tests** — migration (chain/head, model nullable, shared DB columns, round trip keeps rows, downgrade
  refusal; the AGN-008 throwaway-database pattern) and schema bounds:

```python
# test_agn_013_schemas.py
"""AGN-013 -- the enrollment body: required date and expected status, bounded optional fields, no extras."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import AgentApplicationEnrollment

OK = {"enrollment_date": "2027-09-20", "expected_status": "offer"}


def test_minimal_body_and_blank_student_id_is_none():
    body = AgentApplicationEnrollment(**OK, university_student_id="   ")
    assert body.enrollment_date == date(2027, 9, 20) and body.university_student_id is None and body.notes is None


def test_student_id_is_trimmed():
    assert AgentApplicationEnrollment(**OK, university_student_id="  S-123 ").university_student_id == "S-123"


@pytest.mark.parametrize(
    "bad",
    [
        {"expected_status": "offer"},
        {"enrollment_date": "2027-09-20"},
        {**OK, "enrollment_date": "1999-12-31"},
        {**OK, "enrollment_date": "2101-01-01"},
        {**OK, "university_student_id": "x" * 61},
        {**OK, "university_student_id": "S\u0000"},
        {**OK, "notes": "n" * 2001},
        {**OK, "status": "enrolled"},
        {**OK, "agent_id": "00000000-0000-0000-0000-000000000000"},
    ],
)
def test_rejected(bad):
    with pytest.raises(ValidationError):
        AgentApplicationEnrollment(**bad)
```

```python
# test_agn_013_migration.py -- module header as test_agn_008_migration.py, loading 0058 instead
BASE = "0057_agent_applications"
NEW = ("enrollment_date", "university_student_id", "enrollment_confirmed_at")

def test_migration_chains_after_0057_and_is_the_single_head(): ...   # same body as AGN-008's, revision/down_revision 0058/0057
def test_model_declares_the_new_columns_nullable(): ...              # each NEW column nullable
async def test_new_columns_exist_in_the_shared_database(db_session): ...
def test_round_trip_keeps_existing_rows_identical(isolated_db): ...  # upgrade 0058, NEW all NULL, downgrade 0057, rows identical
@pytest.mark.parametrize("column, value", [("enrollment_date", "DATE '2027-09-01'"), ("university_student_id", "'S-1'"), ("enrollment_confirmed_at", "now()")])
def test_downgrade_refuses_to_lose_enrollment_data(isolated_db, column, value): ...  # RuntimeError "enrollment details exist"; row intact
```

(The executor writes these bodies out in full from `test_agn_008_migration.py`, with `BASE = "0057_agent_applications"` and the
isolated database built at `BASE`.)

- [ ] **Step 2:** `API_TEST tests/test_agn_013_schemas.py tests/test_agn_013_migration.py` → FAIL (import errors).
- [ ] **Step 3: implement.**

`models.py`, after `offer_deadline`:

```python
    # AGN-013 (DEC-SCOPE-052): recorded by an agency Master at enrollment (PUT .../enrollment); NULL until then.
    enrollment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    university_student_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    enrollment_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

`0058_agent_app_enrollment.py`:

```python
"""AGN-013 -- overseas_applications.enrollment_date, university_student_id, enrollment_confirmed_at.

Revision ID: 0058_agent_app_enrollment
Revises: 0057_agent_applications

docs/superpowers/specs/2026-10-02-agn-013-enrollment-confirmation-design.md §3 (DEC-SCOPE-052). Three nullable columns; no
existing row is read or written. Adds are guarded (0001 builds a fresh database from the current models). downgrade() refuses
while enrollment details exist rather than silently dropping them.
"""

import sqlalchemy as sa

from alembic import op

revision = "0058_agent_app_enrollment"
down_revision = "0057_agent_applications"
branch_labels = None
depends_on = None

TABLE = "overseas_applications"
COLUMNS = (("enrollment_date", sa.Date()), ("university_student_id", sa.String(60)), ("enrollment_confirmed_at", sa.DateTime(timezone=True)))


def upgrade() -> None:
    existing = set() if op.get_context().as_sql else {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    if not op.get_context().as_sql:
        recorded = " OR ".join(f"{name} IS NOT NULL" for name, _ in COLUMNS)
        if op.get_bind().execute(sa.text(f"SELECT count(*) FROM {TABLE} WHERE {recorded}")).scalar():
            raise RuntimeError("Refusing to downgrade 0058_agent_app_enrollment: enrollment details exist")
    for name, _ in reversed(COLUMNS):
        op.drop_column(TABLE, name)
```

`schemas.py`, after `AgentApplicationStatus`:

```python
class AgentApplicationEnrollment(BaseModel):
    """AGN-013 (DEC-SCOPE-052): confirm or correct an application's enrollment. `expected_status` is required: confirming is the
    commission-triggering act, so a stale screen gets a 409 instead of acting."""

    model_config = {"extra": "forbid"}
    enrollment_date: date
    university_student_id: str | None = None
    expected_status: str = Field(max_length=50)
    notes: str | None = None

    @field_validator("enrollment_date")
    @classmethod
    def _enrollment_date(cls, value):
        return _application_date(value)

    @field_validator("university_student_id")
    @classmethod
    def _student_id(cls, value):
        return clean_free_text(value, 60)

    @field_validator("notes")
    @classmethod
    def _notes(cls, value):
        return clean_free_text(value, 2000)
```

`detail()` return dict, after `"read_only_reason": reason,`:

```python
        "enrollment_date": found.enrollment_date,
        "university_student_id": found.university_student_id,
        "enrollment_confirmed_at": found.enrollment_confirmed_at,
        "enrollment_check": enrollment_check(found, datetime.now(UTC).date()),
```

- [ ] **Step 4:** rerun → PASS; also `API_TEST tests/test_agn_008_migration.py tests/test_agn_008_read.py` (single head, detail shape) → PASS.
- [ ] **Step 5:** commit `feat(agn-013): enrollment columns (0058), request schema, detail fields`.

---

### Task 3: The enrollment route

**Files:**
- Modify: `apps/api/app/api/agent_applications.py`
- Test: `apps/api/tests/test_agn_013_enrollment.py`

**Interfaces:**
- Consumes: Task 1 constants, Task 2 schema/columns, `workflows._maybe_trigger_agent_commission(db, application, old_status, changed_by)`.
- Produces: `PUT {APPS}/{id}/enrollment`.

- [ ] **Step 1: failing tests** (`world` = `agency_world` + an application at `offer` for the no-login record):

```python
"""AGN-013 AC01-AC06, AC08 -- Master confirms enrollment once; corrections never duplicate the commission; refusals write nothing."""

import logging
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentCommission, ApplicationStatusHistory, AuditLog, OverseasApplication
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import APPS, agency_world, mk_application


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"], status="offer", intake="Sep 2027")
    return w


def _body(expected="offer", **over):
    return {"enrollment_date": "2027-09-20", "university_student_id": "S-123", "expected_status": expected, **over}


async def _put(c, app_id, body):
    return await c.put(f"{APPS}/{app_id}/enrollment", json=body)


async def _count(db, model, app_id):
    column = model.application_id if model is not AuditLog else None
    if model is AuditLog:
        return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(app_id)))
    return await db.scalar(select(func.count()).select_from(model).where(column == app_id))


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["offer", "visa_documentation", "status_tracking"])
async def test_master_confirms_and_one_estimated_commission_is_created(db_session, world, stage):
    row = await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)
    row.status = stage
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await _put(c, world["app"].id, _body(stage, notes="Joined in person"))
        assert r.status_code == 200, r.text
        a = r.json()["application"]
        assert (a["status"], a["enrollment_date"], a["university_student_id"], a["enrollment_check"]) == ("enrolled", "2027-09-20", "S-123", None)
        assert a["enrollment_confirmed_at"]
        assert [(h["from_status"], h["to_status"], h["notes"]) for h in a["history"]] == [(stage, "enrolled", "Joined in person")]
        commissions = (await c.get("/api/v1/workflows/overseas/agent/commissions")).json()
    item = (await db_session.scalars(select(AgentCommission).where(AgentCommission.application_id == world["app"].id))).one()
    assert (item.status, float(item.amount), item.created_by, item.agent_id) == ("estimated", 0.0, "system_trigger", world["master"].id)
    assert str(item.id) in str(commissions)
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id.in_([str(world["app"].id), str(item.id)])))).all()
    assert sorted(actions) == ["agent.commission_auto_create", "overseas.application.enroll"]


@pytest.mark.asyncio
async def test_resaving_corrects_details_without_a_second_commission(db_session, world):
    async with client_for(world["master"].email) as c:
        assert (await _put(c, world["app"].id, _body())).status_code == 200
        r = await _put(c, world["app"].id, _body("enrolled", enrollment_date="2027-09-22", university_student_id=None))
        assert r.status_code == 200 and r.json()["application"]["enrollment_date"] == "2027-09-22"
        assert r.json()["application"]["university_student_id"] is None
        assert (await _put(c, world["app"].id, _body("enrolled", enrollment_date="2027-09-22", university_student_id=None))).status_code == 200
    assert await _count(db_session, AgentCommission, world["app"].id) == 1
    assert await _count(db_session, ApplicationStatusHistory, world["app"].id) == 1
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "overseas.application.enrollment_update", AuditLog.entity_id == str(world["app"].id)))).all()
    assert [r.metadata_json for r in rows] == [{"fields": ["enrollment_date", "university_student_id"]}]


@pytest.mark.asyncio
async def test_missing_date_is_422_and_writes_nothing(db_session, world):
    body = _body()
    del body["enrollment_date"]
    async with client_for(world["master"].email) as c:
        assert (await _put(c, world["app"].id, body)).status_code == 422
    await _assert_untouched(db_session, world, "offer")


@pytest.mark.asyncio
@pytest.mark.parametrize(("enrolled", "intake", "check"), [("2027-10-05", "Sep 2027", "after_intake"), ("2027-10-05", "Next intake", "intake_unrecognised"), ("2027-09-05", "Sep 2027", None)])
async def test_date_check_is_a_warning_not_a_block(db_session, world, enrolled, intake, check):
    row = await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)
    row.intake = intake
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await _put(c, world["app"].id, _body(enrollment_date=enrolled))
    assert r.status_code == 200 and r.json()["application"]["enrollment_check"] == check


async def _assert_untouched(db, world, status):
    assert (await db.get(OverseasApplication, world["app"].id, populate_existing=True)).status == status
    for model in (ApplicationStatusHistory, AgentCommission, AuditLog):
        assert await _count(db, model, world["app"].id) == 0, model


@pytest.mark.asyncio
async def test_staff_is_403_even_in_scope(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        r = await _put(c, world["app"].id, _body())
        assert r.status_code == 403 and r.json()["detail"] == "Only an agency Master can confirm enrollment"
        assert (await c.get(f"{APPS}/{world['app'].id}")).status_code == 200  # Staff still read it
    await _assert_untouched(db_session, world, "offer")


@pytest.mark.asyncio
async def test_other_org_master_is_404(db_session, world):
    async with client_for(world["other"]["master"].email) as c:
        assert (await _put(c, world["app"].id, _body())).status_code == 404
    await _assert_untouched(db_session, world, "offer")


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["counselor", "overseas_admin", "overseas_student"])
async def test_non_agents_are_403(db_session, world, who):
    user = await mk_user(db_session, role=who)
    async with client_for(user.email) as c:
        assert (await _put(c, world["app"].id, _body())).status_code == 403
    await _assert_untouched(db_session, world, "offer")


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client, world):
    assert (await _put(client, world["app"].id, _body())).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(("setup", "code", "status"), [("withdrawn", 409, "withdrawn"), ("archived", 409, "offer"), ("stale", 409, "offer"), ("enquiry", 422, "enquiry"), ("university_selection", 422, "university_selection")])
async def test_refusals_write_nothing(db_session, world, setup, code, status):
    row = await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)
    expected = "offer"
    if setup in ("withdrawn", "enquiry", "university_selection"):
        row.status = expected = setup
    if setup == "archived":
        world["record"].status = "archived"
        db_session.add(world["record"])
    if setup == "stale":
        expected = "status_tracking"
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await _put(c, world["app"].id, _body(expected))
    assert r.status_code == code, r.text
    if setup in ("enquiry", "university_selection"):
        assert r.json()["detail"] == "An offer is needed before enrollment"
    await _assert_untouched(db_session, world, status)


@pytest.mark.asyncio
async def test_extra_fields_are_422(db_session, world):
    async with client_for(world["master"].email) as c:
        for extra in ({"status": "enrolled"}, {"agent_id": str(world["master"].id)}, {"university_id": str(world["university"].id)}):
            assert (await _put(c, world["app"].id, _body(**extra))).status_code == 422
    await _assert_untouched(db_session, world, "offer")


@pytest.mark.asyncio
async def test_master_adds_details_to_a_counselor_enrolled_application(db_session, world):
    row = await db_session.get(OverseasApplication, world["app"].id, populate_existing=True)
    row.status = "enrolled"
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await _put(c, world["app"].id, _body("enrolled"))
    assert r.status_code == 200 and r.json()["application"]["enrollment_confirmed_at"]
    assert await _count(db_session, AgentCommission, world["app"].id) == 0
    assert await _count(db_session, ApplicationStatusHistory, world["app"].id) == 0


@pytest.mark.asyncio
async def test_status_route_still_refuses_enrolled(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await c.post(f"{APPS}/{world['app'].id}/status", json={"to_status": "enrolled", "expected_status": "offer"})
    assert r.status_code == 403
    await _assert_untouched(db_session, world, "offer")


@pytest.mark.asyncio
async def test_logs_and_audit_never_carry_the_student_id_or_notes(db_session, world, caplog):
    caplog.set_level(logging.INFO, logger="app.agent_applications")
    async with client_for(world["master"].email) as c:
        await _put(c, world["app"].id, _body(university_student_id="SECRET-ID-9", notes="private note"))
        await _put(c, world["app"].id, _body("enrolled", university_student_id="SECRET-ID-10"))
    events = [r.msg for r in caplog.records if r.name == "app.agent_applications"]
    assert events == ["agent_application_enrolled", "agent_application_enrollment_updated"]
    text = " ".join(str(getattr(r, "extra_fields", "")) for r in caplog.records) + str((await db_session.scalars(select(AuditLog.metadata_json))).all())
    assert "SECRET-ID" not in text and "private note" not in text
```

- [ ] **Step 2:** `API_TEST tests/test_agn_013_enrollment.py` → FAIL (`405 Method Not Allowed` on PUT).
- [ ] **Step 3: implement** in `api/agent_applications.py` (imports: `datetime`/`UTC`; `AgentApplicationEnrollment`; from the service
  `ENROLLABLE`, `MASTER_ONLY_ENROLLMENT`, `OFFER_NEEDED`; `from app.api.workflows import _maybe_trigger_agent_commission, _notify_user`;
  `from app.core.rbac import is_agent_staff`), and extend the module docstring's A4 sentence:

```python
@router.put("/{application_id}/enrollment")
async def save_enrollment(application_id: UUID, payload: AgentApplicationEnrollment, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-013 (DEC-SCOPE-052): a Master confirms enrollment from offer onwards -- `enrolled`, one history row and the AGT-003 commission
    trigger, which creates at most one commission per application -- or, once enrolled, corrects the date and student ID (no history,
    no commission). Locks as every agency write: organisation, then the row."""
    membership = _gate(user)
    if is_agent_staff(user):  # E1: refused before any load, so staff learn nothing about ids
        raise HTTPException(403, MASTER_ONLY_ENROLLMENT)
    item = await _locked(db, user, membership, application_id)
    record = await _refuse_closed(db, user, item)
    if payload.expected_status != item.status:
        raise HTTPException(409, STALE)
    fields = {"enrollment_date": payload.enrollment_date, "university_student_id": payload.university_student_id}
    if item.status == "enrolled":
        changed = sorted(k for k, v in fields.items() if getattr(item, k) != v)
        for key in changed:
            setattr(item, key, fields[key])
        if changed:
            item.enrollment_confirmed_at = item.enrollment_confirmed_at or datetime.now(UTC)
            _audit(db, user, "enrollment_update", item.id, {"fields": changed})
        await db.commit()
        if changed:
            _log("agent_application_enrollment_updated", membership, user, item.id, fields=changed)
        return {"application": await detail(db, user, item, record=record)}
    if item.status not in ENROLLABLE:
        raise HTTPException(422, OFFER_NEEDED)
    old = item.status
    for key, value in fields.items():
        setattr(item, key, value)
    item.enrollment_confirmed_at = datetime.now(UTC)
    item.status = "enrolled"
    db.add(ApplicationStatusHistory(application_id=item.id, from_status=old, to_status=item.status, next_action=item.next_action, notes=payload.notes, changed_by_id=user.id))
    await _maybe_trigger_agent_commission(db, item, old, user)
    _audit(db, user, "enroll", item.id, {"from_status": old, "to_status": item.status})
    await db.commit()
    _log("agent_application_enrolled", membership, user, item.id, from_status=old)
    return {"application": await detail(db, user, item, record=record)}
```

- [ ] **Step 4:** rerun → PASS; regression lite `API_TEST tests/test_agn_008_status.py tests/test_agn_008_security.py tests/test_agt_003_commission_accrual.py` → PASS.
- [ ] **Step 5:** refactor (shared helpers in the test file only if duplicated), rerun; commit `feat(agn-013): Master-only enrollment route with one commission`.

---

### Task 4: Concurrency

**Files:** Test: `apps/api/tests/test_agn_013_concurrency.py` (no production change expected; if a test fails, fix the route).

- [ ] **Step 1: tests**

```python
"""AGN-013 AC07 -- two confirmations at once, and a counselor's enrolment landing first: exactly one commission either way. The
interleaving is forced with a separate transaction holding the row lock (AGN-008's method), not left to timing."""

import asyncio
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import AgentCommission, ApplicationStatusHistory, OverseasApplication
from tests.agn001_helpers import client_for
from tests.agn008_helpers import APPS, agency_world, mk_application

BODY = {"enrollment_date": "2027-09-20", "expected_status": "status_tracking"}


@pytest_asyncio.fixture
async def world(db_session):
    w = await agency_world(db_session)
    w["app"] = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"], status="status_tracking")
    return w


async def _commissions(db, app_id):
    return await db.scalar(select(func.count()).select_from(AgentCommission).where(AgentCommission.application_id == app_id))


@pytest.mark.asyncio
async def test_two_simultaneous_confirmations_create_one_commission(db_session, world):
    async with client_for(world["master"].email) as a, client_for(world["master"].email) as b:
        first, second = await asyncio.gather(a.put(f"{APPS}/{world['app'].id}/enrollment", json=BODY), b.put(f"{APPS}/{world['app'].id}/enrollment", json=BODY))
    assert sorted([first.status_code, second.status_code]) == [200, 409]  # the loser saw `enrolled` != expected status_tracking
    assert await _commissions(db_session, world["app"].id) == 1
    assert await db_session.scalar(select(func.count()).select_from(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == world["app"].id)) == 1


@asynccontextmanager
async def _counselor_enrolling(app_id):
    session = SessionLocal()
    try:
        row = await session.scalar(select(OverseasApplication).where(OverseasApplication.id == app_id).with_for_update())
        row.status = "enrolled"
        await session.flush()
        yield
        await session.commit()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_counselor_enrolment_landing_first_turns_the_agency_call_into_a_stale_refusal(db_session, world):
    async with client_for(world["master"].email) as c:
        async with _counselor_enrolling(world["app"].id):
            task = asyncio.create_task(c.put(f"{APPS}/{world['app'].id}/enrollment", json=BODY))
            await asyncio.sleep(0.7)
            assert not task.done(), "the request did not wait for the row lock"
        r = await asyncio.wait_for(task, timeout=20)
    assert r.status_code == 409  # the screen showed status_tracking; it must reload, then a re-save is a correction
    assert await _commissions(db_session, world["app"].id) == 0  # the simulated counselor write created none; the agency call none
```

- [ ] **Step 2:** `API_TEST tests/test_agn_013_concurrency.py` → expected PASS on first run (behaviour comes from Task 3's locks); if
  it fails, that is the bug to fix. Record the outcome honestly.
- [ ] **Step 3:** commit `test(agn-013): concurrent confirmations and counselor race`.


---

### Task 5: Web — client types and the enrollment component

**Files:**
- Modify: `apps/web/lib/agentApplications.ts`, `apps/web/components/AgentApplicationDetail.tsx`,
  `apps/web/components/AgentApplicationsPanel.tsx`, `apps/web/components/AgentApplicationsSection.tsx`
- Create: `apps/web/components/AgentApplicationEnrollment.tsx`
- Test: `apps/web/tests/lib/agentApplications.test.ts` (extend), `apps/web/tests/components/AgentApplicationEnrollment.test.tsx`

**Interfaces:**
- Produces: `ENROLLABLE_STAGES`, `canConfirmEnrollment(status: string): boolean`, `EnrollmentCheck`, `ENROLLMENT_CHECK_TEXT`;
  `AgentApplicationDetail` gains `enrollment_date: string | null`, `university_student_id: string | null`,
  `enrollment_confirmed_at: string | null`, `enrollment_check: EnrollmentCheck`; `AgentApplicationDetail` component gains
  `isMaster?: boolean` (default false); `AgentApplicationsPanel` gains `isMaster?: boolean`.

- [ ] **Step 1: failing tests.**

`tests/lib/agentApplications.test.ts` (append):

```ts
describe("canConfirmEnrollment (AGN-013 E6)", () => {
  it("allows offer, visa documentation and status tracking only", () => {
    expect(["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled", "withdrawn", "University review"].filter(canConfirmEnrollment)).toEqual(["offer", "visa_documentation", "status_tracking"]);
  });
});
```

`tests/components/AgentApplicationEnrollment.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationDetail from "@/components/AgentApplicationDetail";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const detail = (over: Record<string, unknown> = {}) => ({
  id: "a1", agent_student_id: "r1", student: "Asha Rao", has_login: false, university: "Uni One", university_id: "u1", university_slug: "u1",
  course: "MSc Data", course_id: "c1", intake: "Sep 2027", status: "offer", application_reference: null, submitted_on: null,
  application_deadline: null, offer_deadline: null, nearest_deadline: null, next_action: null, updated_at: "", created_at: "", read_only_reason: null,
  history: [], enrollment_date: null, university_student_id: null, enrollment_confirmed_at: null, enrollment_check: null, ...over,
});
const enrolled = detail({ status: "enrolled", enrollment_date: "2027-10-05", university_student_id: "S-1", enrollment_confirmed_at: "2026-10-02T10:00:00Z", enrollment_check: "after_intake" });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mount(fetchMock: ReturnType<typeof vi.fn>, isMaster = true) {
  vi.stubGlobal("fetch", fetchMock);
  render(<AgentApplicationDetail id="a1" isMaster={isMaster} onChanged={vi.fn()} onClose={vi.fn()} />);
}

describe("AgentApplicationEnrollment (AGN-013)", () => {
  it("a Master confirms after an explicit confirmation step, sending the displayed status", async () => {
    const fetchMock = vi.fn((_: string, init?: RequestInit) => Promise.resolve(json({ application: init?.method === "PUT" ? enrolled : detail() })));
    mount(fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Enroll student" }));
    const form = screen.getByRole("form", { name: "Enrollment" });
    expect(within(form).getByText("Uni One")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Enrollment date (required)"), { target: { value: "2027-10-05" } });
    fireEvent.change(screen.getByLabelText("University student ID (optional)"), { target: { value: " S-1 " } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm enrollment" }));
    const confirm = screen.getByRole("group", { name: "Confirm enrollment" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Yes, confirm enrollment" }));
    await screen.findByText("Enrollment confirmed.");
    const put = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT")!;
    expect(put[0]).toBe("/api/v1/workflows/overseas/agent/crm/applications/a1/enrollment");
    expect(JSON.parse(String(put[1]!.body))).toEqual({ enrollment_date: "2027-10-05", university_student_id: "S-1", expected_status: "offer", notes: null });
    expect(screen.getByText("Enrolled", { selector: ".badge" })).toBeInTheDocument();
    expect(screen.getByText(/after the intake/)).toHaveClass("form-warning");
  });

  it("sends one request on a double click", async () => {
    let resolvePut: (r: Response) => void = () => {};
    const fetchMock = vi.fn((_: string, init?: RequestInit) => (init?.method === "PUT" ? new Promise<Response>((r) => (resolvePut = r)) : Promise.resolve(json({ application: detail() }))));
    mount(fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Enroll student" }));
    fireEvent.change(screen.getByLabelText("Enrollment date (required)"), { target: { value: "2027-09-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm enrollment" }));
    const yes = screen.getByRole("button", { name: "Yes, confirm enrollment" });
    fireEvent.click(yes);
    fireEvent.click(yes);
    expect(fetchMock.mock.calls.filter(([, i]) => i?.method === "PUT")).toHaveLength(1);
    resolvePut(json({ application: enrolled }));
    await screen.findByText("Enrollment confirmed.");
  });

  it("Escape on the confirmation goes back and returns focus", async () => {
    mount(vi.fn(() => Promise.resolve(json({ application: detail() }))));
    fireEvent.click(await screen.findByRole("button", { name: "Enroll student" }));
    fireEvent.change(screen.getByLabelText("Enrollment date (required)"), { target: { value: "2027-09-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm enrollment" }));
    fireEvent.keyDown(screen.getByRole("group", { name: "Confirm enrollment" }), { key: "Escape" });
    expect(screen.queryByRole("group", { name: "Confirm enrollment" })).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm enrollment" })).toHaveFocus());
  });

  it("a 422 keeps the form and the input, and announces the server's words", async () => {
    const fetchMock = vi.fn((_: string, init?: RequestInit) => Promise.resolve(init?.method === "PUT" ? json({ detail: "An offer is needed before enrollment" }, 422) : json({ application: detail() })));
    mount(fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Enroll student" }));
    fireEvent.change(screen.getByLabelText("Enrollment date (required)"), { target: { value: "2027-09-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm enrollment" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, confirm enrollment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("An offer is needed before enrollment");
    expect(screen.getByLabelText("Enrollment date (required)")).toHaveValue("2027-09-20");
  });

  it("Staff see who confirms, not the action", async () => {
    mount(vi.fn(() => Promise.resolve(json({ application: detail() }))), false);
    expect(await screen.findByText("An agency Master confirms enrollment.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enroll student" })).toBeNull();
  });

  it("an enrolled application shows the final status and details; a Master can correct them without a confirmation step", async () => {
    const fetchMock = vi.fn((_: string, init?: RequestInit) => Promise.resolve(json({ application: init?.method === "PUT" ? { ...enrolled, university_student_id: "S-2" } : enrolled })));
    mount(fetchMock);
    expect(await screen.findByText("S-1")).toBeInTheDocument();
    expect(screen.queryByLabelText("Move to")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Edit enrollment details" }));
    fireEvent.change(screen.getByLabelText("University student ID (optional)"), { target: { value: "S-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save enrollment details" }));
    await screen.findByText("Enrollment details saved.");
    const put = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT")!;
    expect(JSON.parse(String(put[1]!.body))).toEqual({ enrollment_date: "2027-10-05", university_student_id: "S-2", expected_status: "enrolled" });
  });

  it("Staff see enrolled details read-only; before an offer there is no enrollment section", async () => {
    mount(vi.fn(() => Promise.resolve(json({ application: enrolled }))), false);
    expect(await screen.findByText("S-1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit enrollment details" })).toBeNull();
    cleanup();
    mount(vi.fn(() => Promise.resolve(json({ application: detail({ status: "enquiry" }) }))));
    await screen.findByRole("heading", { name: "Asha Rao — Uni One" });
    expect(screen.queryByRole("heading", { name: "Enrollment" })).toBeNull();
  });
});
```

- [ ] **Step 2:** `WEB_TEST tests/lib/agentApplications.test.ts tests/components/AgentApplicationEnrollment.test.tsx` → FAIL.
- [ ] **Step 3: implement.**

`lib/agentApplications.ts` (after `canWithdraw`, and the type fields):

```ts
// AGN-013 E6: a Master confirms enrollment from an offer onwards (the server is the authority).
export const ENROLLABLE_STAGES = ["offer", "visa_documentation", "status_tracking"] as const;
export function canConfirmEnrollment(status: string): boolean {
  return (ENROLLABLE_STAGES as readonly string[]).includes(status);
}
export type EnrollmentCheck = "after_intake" | "intake_unrecognised" | null;
export const ENROLLMENT_CHECK_TEXT: Record<Exclude<EnrollmentCheck, null>, string> = {
  after_intake: "The enrollment date is in the future and after the intake month. Check the date.",
  intake_unrecognised: "The intake is not a month and year, so the enrollment date was not checked against it.",
};
```

and in `AgentApplicationDetail`: `enrollment_date: string | null; university_student_id: string | null; enrollment_confirmed_at: string | null; enrollment_check: EnrollmentCheck;`.

`components/AgentApplicationEnrollment.tsx`:

```tsx
"use client";

import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { sendJson } from "@/lib/apiErrors";
import { AgentApplicationDetail, APPLICATIONS_URL, canConfirmEnrollment, ENROLLMENT_CHECK_TEXT } from "@/lib/agentApplications";
import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Props = {
  detail: AgentApplicationDetail;
  isMaster: boolean;
  onSaved: (d: AgentApplicationDetail, message: string) => void;
  onFailed: (message: string, status?: number) => void;
};

// AGN-013 (DEC-SCOPE-052): Step 9. A Master confirms enrollment from an offer onwards, after an explicit confirmation (it estimates a
// commission and ends withdrawal); once enrolled, a Master corrects the date and student ID. Staff read. The server decides.
export default function AgentApplicationEnrollment({ detail, isMaster, onSaved, onFailed }: Props) {
  const enrolled = detail.status === "enrolled";
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(detail.enrollment_date ?? "");
  const [studentId, setStudentId] = useState(detail.university_student_id ?? "");
  const [notes, setNotes] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a same-tick second click sends nothing
  const focusAfter = useFocusAfterRender();
  const id = (part: string) => `enrollment-${part}-${detail.id}`;

  if (!enrolled && (!canConfirmEnrollment(detail.status) || detail.read_only_reason)) return null;

  async function save() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    let outcome: Awaited<ReturnType<typeof sendJson>>;
    try {
      const body = { enrollment_date: date, university_student_id: studentId.trim() || null, expected_status: detail.status, ...(enrolled ? {} : { notes: notes.trim() || null }) };
      outcome = await sendJson(`${APPLICATIONS_URL}/${detail.id}/enrollment`, "PUT", body);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
    setConfirming(false);
    if (!outcome.ok) return onFailed(outcome.message, outcome.status);
    const next = (outcome.data as { application?: AgentApplicationDetail }).application;
    if (!next) return onFailed("The change could not be confirmed. Reload to see the current status.");
    setOpen(false);
    onSaved(next, enrolled ? "Enrollment details saved." : "Enrollment confirmed.");
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (enrolled) save();
    else setConfirming(true);
  }
  function back() {
    focusAfter(id("submit"));
    setConfirming(false);
  }
  function cancel() {
    focusAfter(id("open"));
    setOpen(false);
  }

  const canAct = isMaster && !detail.read_only_reason;
  return (
    <section aria-labelledby={id("heading")}>
      <h5 id={id("heading")}>Enrollment</h5>
      {enrolled && (
        <>
          <p>
            <span className="badge badge-done">Enrolled</span> <span className="muted">Final status</span>
          </p>
          <dl className="card-stack">
            <dt>University</dt>
            <dd>{detail.university}</dd>
            <dt>Course</dt>
            <dd>{detail.course ?? "Undecided"}</dd>
            <dt>Intake</dt>
            <dd>{detail.intake}</dd>
            <dt>Enrollment date</dt>
            <dd>{detail.enrollment_date ?? "Not recorded"}</dd>
            <dt>University student ID</dt>
            <dd>{detail.university_student_id ?? "Not recorded"}</dd>
            <dt>Confirmed by the agency</dt>
            <dd>{detail.enrollment_confirmed_at ? formatDateTimeIn(detail.enrollment_confirmed_at, viewerTimeZone(), true) : "—"}</dd>
          </dl>
        </>
      )}
      {detail.enrollment_check && <p className="form-warning">{ENROLLMENT_CHECK_TEXT[detail.enrollment_check]}</p>}
      {!enrolled && !isMaster && <p className="muted">An agency Master confirms enrollment.</p>}
      {canAct && !open && (
        <button id={id("open")} type="button" className="btn secondary small" onClick={() => setOpen(true)}>
          {!enrolled ? "Enroll student" : detail.enrollment_date ? "Edit enrollment details" : "Add enrollment details"}
        </button>
      )}
      {canAct && open && (
        <form className="form" aria-label="Enrollment" onSubmit={submit}>
          {!enrolled && (
            <dl className="card-stack">
              <dt>University</dt>
              <dd>{detail.university}</dd>
              <dt>Course</dt>
              <dd>{detail.course ?? "Undecided"}</dd>
              <dt>Intake</dt>
              <dd>{detail.intake}</dd>
            </dl>
          )}
          <div className="field">
            <label htmlFor={id("date")}>Enrollment date (required)</label>
            <input id={id("date")} type="date" required min="2000-01-01" max="2100-12-31" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor={id("student")}>University student ID (optional)</label>
            <input id={id("student")} maxLength={60} autoComplete="off" value={studentId} onChange={(e) => setStudentId(e.target.value)} />
          </div>
          {!enrolled && (
            <div className="field">
              <label htmlFor={id("notes")}>Note (optional)</label>
              <textarea id={id("notes")} maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
          )}
          {confirming ? (
            <div role="group" aria-label="Confirm enrollment" onKeyDown={(e: KeyboardEvent) => e.key === "Escape" && back()}>
              <p>Confirm enrollment? A commission will be estimated and the application can no longer be withdrawn.</p>
              <div className="actions">
                <button type="button" className="btn small" disabled={busy} onClick={save} autoFocus>
                  {busy ? "Saving…" : "Yes, confirm enrollment"}
                </button>
                <button type="button" className="btn ghost small" onClick={back}>
                  Go back
                </button>
              </div>
            </div>
          ) : (
            <div className="actions">
              <button id={id("submit")} className="btn small" disabled={busy || !date}>
                {busy ? "Saving…" : enrolled ? "Save enrollment details" : "Confirm enrollment"}
              </button>
              <button type="button" className="btn ghost small" onClick={cancel}>
                Cancel
              </button>
            </div>
          )}
        </form>
      )}
    </section>
  );
}
```

`AgentApplicationDetail.tsx`: props `isMaster = false`; after the fields/Edit fragment and before the status form:

```tsx
      {!editing && <AgentApplicationEnrollment key={detail.status} detail={detail} isMaster={isMaster} onSaved={enrollmentSaved} onFailed={editFailed} />}
```

with

```tsx
  function enrollmentSaved(next: Detail, message: string) {
    saved(next, message);
    focusAfter(noticeId); // the opener is gone: the announced notice takes focus
  }
```

`AgentApplicationsPanel.tsx`: props `{ group, reloadKey, isMaster = false }`; pass `isMaster={isMaster}` to `AgentApplicationDetail`.
`AgentApplicationsSection.tsx`: `<AgentApplicationsPanel key={group} group={group} reloadKey={reloadKey} isMaster={isMaster} />` through
`Filtered`, with `const isMaster = user.agent_member_role !== "staff";`.

- [ ] **Step 4:** rerun → PASS; regression lite `WEB_TEST tests/components/AgentApplicationDetail.test.tsx tests/components/AgentApplicationsPanel.test.tsx tests/components/PortalPage.agentApplications.test.tsx` and `npx tsc --noEmit -p .` → PASS.
- [ ] **Step 5:** refactor (the University/Course/Intake `<dl>` appears twice: extract a local `Placement` function component in the same file), rerun, commit `feat(agn-013): enrollment step in the agency application detail`.

---

### Task 6: Playwright spec and documentation

**Files:**
- Create: `apps/web/tests/e2e/agn-013-enrollment.spec.ts` (modelled on `agn-008-agent-applications.spec.ts`: Master moves a seeded
  application to offer, enrolls with date + ID, sees the badge; Staff sees no "Enroll student"; 320 px viewport has no horizontal scroll).
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-052`, E1–E8), `docs/architecture/API_CONTRACT.md` (the route),
  `docs/architecture/DATA_MODEL.md` (three columns), `docs/architecture/RBAC_MATRIX.md` (Master-only enrollment),
  `docs/quality/RTM.md` (AGN-013 row: AC → tests), `docs/delivery/AGENT_CRM_BACKLOG.md` (ang-013 status: implemented, pending
  browser validation and Codex review).

- [ ] **Step 1:** write the spec file; `npx tsc --noEmit -p .` → PASS (it runs in the owner's browser-validation session).
- [ ] **Step 2:** docs edits.
- [ ] **Step 3:** final lite run of every `test_agn_013_*` file plus the regression lite set; commit `docs+test(agn-013): e2e spec, decision, contract, RTM`.
