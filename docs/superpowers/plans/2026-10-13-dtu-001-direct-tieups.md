# dtu-001 Direct Tie-ups — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load the owner's 35 direct tie-up universities (with courses, scholarships, fees, intakes, deadlines, campuses and logos)
into the shared catalogue, and add a university-level agent commission visible only to super_admin, overseas_admin and agent Masters.

**Architecture:** Migration 0157 adds nullable columns to `universities` and `overseas_courses`. A pure parser turns the xlsx into a
committed JSON (coverage-checked: 0 unmapped cells); an idempotent loader writes it through the existing models. The agent commission
is emitted by exactly two serializers (university master detail, new agent Partner Universities endpoints) guarded by one access
module; it is edited through one dedicated PUT route.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic + Pydantic v2 (apps/api), Next.js/React + vitest + Playwright (apps/web), Postgres.

**Spec:** `docs/superpowers/specs/2026-10-13-dtu-001-direct-tieups-design.md` (read it first; DT1–DT14 are the owner's answers).

## Global Constraints

- Worktree: `C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/direct-tieups`, branch `feature/direct-tieups`.
- Migration `0157_direct_tieups` (down_revision `0156_marketing_budgets`); decision `DEC-SCOPE-209`; RBAC `§2.134`; API contract `§12DW`.
  Before Task 1 and before the docs task: `git fetch origin main` and confirm none of these numbers were taken; if taken, stop and ask.
- Agent commission viewers: `super_admin`, `overseas_admin` (overseas division), agent **Master**. Editors: `super_admin`, `overseas_admin`.
  Everyone else (agent staff, `it_admin`, `partnership_manager`, `partnership_head`, `partner`, `accountant`, counselor, university_rep,
  bdm, student, anonymous) never receives an `agent_commission` key — absent, not null.
- `partnership_access.COMMISSION_ROLES`, `COMMISSION_FIELDS`, `strip_commission` and the course `commission_*` columns are NOT changed.
- Never modify `docs/sources/`. Never commit the xlsx. No new runtime dependency (openpyxl is used only by the parser CLI on a dev machine).
- Test DB is shared and never truncated: every test value must be unique (`uuid4().hex[:8]` suffixes).
- pytest `asyncio_mode = "strict"`: async tests need `@pytest.mark.asyncio`, async fixtures `@pytest_asyncio.fixture`.
- Backend test command (lite set only; the owner runs the full suite):
  ```bash
  cd /c/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere
  docker compose -p dtu -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
    -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/direct-tieups/apps/api:/app" \
    api-test sh -c "alembic upgrade head && python -m pytest -q <paths>"
  ```
  (Use the Windows-form mount path; a `$PWD` mount silently mounts a stale tree.)
- Web test command:
  ```bash
  MSYS_NO_PATHCONV=1 docker compose -p dtu -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps \
    -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/direct-tieups/apps/web:/app" -v /app/node_modules \
    web-test sh -c "npx vitest run <paths> && npx tsc --noEmit && npx eslint <paths>"
  ```
- The owner starts/stops docker stacks; one-off `run --rm` test containers are fine. Do not `git push`; give the owner the command.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A partnership_manager / partnership_head opening the university detail must not see `agent_commission` (the envelope is shared
   with admins) → test in Task 2 (`test_partnership_roles_do_not_get_the_key`).
2. An agent **staff** member calling the Partner Universities endpoints must get the list without the rate, and a pending/suspended
   agency gets 403 → tests in Task 4.
3. Re-running the loader on a database where an admin has since edited a university must not overwrite their edits → Task 7
   `test_existing_values_are_never_overwritten`.
4. A malformed commission text ("16 %", "£4,000 flat", "1,50,000 INR flat", blank) must parse or be reported, never silently become 0
   → Task 5 parametrized `test_parse_commission`.
5. Public endpoints (anonymous) must never carry the key even when the university has a rate → Task 3
   `test_public_never_carries_agent_commission`.

---

### Task 1: Migration 0157 + model columns

**Files:**
- Create: `apps/api/alembic/versions/0157_direct_tieups.py`
- Modify: `apps/api/app/models.py` (after `UNIVERSITY_PROBABILITY_CHECKS` ~line 1070; `University` class ~1087; `OverseasCourse` ~1702)
- Test: `apps/api/tests/test_dtu_001_migration.py`

**Interfaces:**
- Produces: `app.models.UNIVERSITY_AGENT_COMMISSION_CHECKS: dict[str, str]`; `University.logo_url/campuses/fee_structure/
  agent_commission_percent/agent_commission_amount/agent_commission_currency/agent_commission_note`;
  `OverseasCourse.campus/fee_text/intake_text`.

- [ ] **Step 1: Write the failing test** `apps/api/tests/test_dtu_001_migration.py`

```python
"""dtu-001 -- migration 0157_direct_tieups (spec §3). Round trip runs in a throwaway database (the upc-023 pattern)."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_dtu_001_migration_0157", VERSIONS / "0157_direct_tieups.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0156_marketing_budgets", "0157_direct_tieups"
UNI_COLUMNS = {"logo_url", "campuses", "fee_structure", "agent_commission_percent", "agent_commission_amount", "agent_commission_currency", "agent_commission_note"}
COURSE_COLUMNS = {"campus", "fee_text", "intake_text"}


def test_migration_chains_after_0156_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import UNIVERSITY_AGENT_COMMISSION_CHECKS, OverseasCourse, University

    assert UNIVERSITY_AGENT_COMMISSION_CHECKS == _migration.CHECKS
    assert UNI_COLUMNS == {name for name, _ in _migration.UNIVERSITY_COLUMNS}
    assert COURSE_COLUMNS == {name for name, _ in _migration.COURSE_COLUMNS}
    assert UNI_COLUMNS <= {c.name for c in University.__table__.columns}
    assert COURSE_COLUMNS <= {c.name for c in OverseasCourse.__table__.columns}
    by_name = {c.name: str(c.sqltext) for c in University.__table__.constraints if getattr(c, "sqltext", None) is not None}
    for name, sql in _migration.CHECKS.items():
        assert by_name[name] == sql


@pytest.mark.asyncio
async def test_columns_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    uni, course, checks = await conn.run_sync(lambda s: (
        {c["name"] for c in inspect(s).get_columns("universities")},
        {c["name"] for c in inspect(s).get_columns("overseas_courses")},
        {c["name"] for c in inspect(s).get_check_constraints("universities")},
    ))
    assert UNI_COLUMNS <= uni and COURSE_COLUMNS <= course and set(_migration.CHECKS) <= checks


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"dtu001_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip(isolated_db):
    command.upgrade(isolated_db["cfg"], HEAD)
    rows = _sql(isolated_db["url"], "SELECT column_name FROM information_schema.columns WHERE table_name = 'universities'")
    assert UNI_COLUMNS <= {r[0] for r in rows}
    command.downgrade(isolated_db["cfg"], BASE)
    rows = _sql(isolated_db["url"], "SELECT column_name FROM information_schema.columns WHERE table_name = 'universities'")
    assert not (UNI_COLUMNS & {r[0] for r in rows})


def test_downgrade_refuses_while_an_agent_commission_exists(isolated_db):
    command.upgrade(isolated_db["cfg"], HEAD)
    _sql(isolated_db["url"], "UPDATE universities SET agent_commission_percent = 10 WHERE id = (SELECT id FROM universities LIMIT 1)", autocommit=True)
    count = _sql(isolated_db["url"], "SELECT count(*) FROM universities WHERE agent_commission_percent IS NOT NULL")[0][0]
    if count == 0:
        pytest.skip("fresh database has no university rows to mark")
    with pytest.raises(RuntimeError, match="agent commissions exist"):
        command.downgrade(isolated_db["cfg"], BASE)
```

Before writing: open `tests/test_upc_001_migration.py` and confirm `_sql(url, sql, autocommit=False)` returns a list of rows for
SELECT; adapt the two `_sql(...)` reads if it returns something else.

- [ ] **Step 2: Run, expect FAIL** (`FileNotFoundError` for 0157). Command: Global Constraints, paths `tests/test_dtu_001_migration.py`.

- [ ] **Step 3: Model.** In `app/models.py` directly after `UNIVERSITY_PROBABILITY_CHECKS`:

```python
# dtu-001 (DEC-SCOPE-209, spec §3): what EduSphere pays an agent Master per university (DT2) -- NOT upc-016's university commission.
# Exactly one of % or fixed amount; migration 0157 repeats these (test_dtu_001_migration).
UNIVERSITY_AGENT_COMMISSION_CHECKS = {
    "ck_universities_agent_commission_one": "agent_commission_percent IS NULL OR agent_commission_amount IS NULL",
    "ck_universities_agent_commission_percent": "agent_commission_percent IS NULL OR (agent_commission_percent > 0 AND agent_commission_percent <= 100)",
    "ck_universities_agent_commission_amount": "(agent_commission_amount IS NULL) = (agent_commission_currency IS NULL) AND (agent_commission_amount IS NULL OR agent_commission_amount > 0)",
    "ck_universities_agent_commission_currency": "agent_commission_currency IS NULL OR agent_commission_currency IN ('INR', 'USD', 'GBP', 'EUR', 'CAD', 'AUD', 'NZD', 'AED')",
}
```

Check `COUNSELING_CURRENCIES` in models.py: if it lacks `AED`, add `"AED"` there **only if** no CHECK elsewhere is generated from it
(grep `_one_of("…currency", COUNSELING_CURRENCIES)` / `COURSE_CURRENCIES`); if one is, do NOT widen it — keep the literal list above
(it is this column's own list) and use `AGENT_COMMISSION_CURRENCIES = ("INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD", "AED")`.
Course tuition in AED (GBS Dubai, BIGS) then has no structured amount: the loader leaves `tuition_amount` null and keeps `fee_text`.

In `University.__table_args__` add `*(CheckConstraint(sql, name=name) for name, sql in UNIVERSITY_AGENT_COMMISSION_CHECKS.items()),`.
Append to `University` columns (after `probability_override_reason`):

```python
    # dtu-001 (DEC-SCOPE-209): the catalogue's logo, campus list and fee block (public), and the agent commission (DT4: restricted).
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    campuses: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    fee_structure: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_commission_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    agent_commission_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    agent_commission_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    agent_commission_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
```

Append to `OverseasCourse` (after `commission_currency`):

```python
    # dtu-001: verbatim catalogue texts (the structured amount / months stay the source for tuition_fee / intake).
    campus: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fee_text: Mapped[str | None] = mapped_column(String(300), nullable=True)
    intake_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
```

- [ ] **Step 4: Migration** `apps/api/alembic/versions/0157_direct_tieups.py`:

```python
"""dtu-001 -- Direct Tie-ups: catalogue logo / campuses / fee block, course texts, and the agent commission.

Revision ID: 0157_direct_tieups
Revises: 0156_marketing_budgets

docs/superpowers/specs/2026-10-13-dtu-001-direct-tieups-design.md §3 (DEC-SCOPE-209). All columns nullable (campuses defaults to []),
no backfill. 0001 builds a fresh database from the current models, so every step is guarded. CHECKS repeats
app.models.UNIVERSITY_AGENT_COMMISSION_CHECKS (test_dtu_001_migration). downgrade() refuses while any agent commission exists.
"""

import sqlalchemy as sa

from alembic import op

revision = "0157_direct_tieups"
down_revision = "0156_marketing_budgets"
branch_labels = None
depends_on = None

CHECKS = {
    "ck_universities_agent_commission_one": "agent_commission_percent IS NULL OR agent_commission_amount IS NULL",
    "ck_universities_agent_commission_percent": "agent_commission_percent IS NULL OR (agent_commission_percent > 0 AND agent_commission_percent <= 100)",
    "ck_universities_agent_commission_amount": "(agent_commission_amount IS NULL) = (agent_commission_currency IS NULL) AND (agent_commission_amount IS NULL OR agent_commission_amount > 0)",
    "ck_universities_agent_commission_currency": "agent_commission_currency IS NULL OR agent_commission_currency IN ('INR', 'USD', 'GBP', 'EUR', 'CAD', 'AUD', 'NZD', 'AED')",
}  # must equal app.models.UNIVERSITY_AGENT_COMMISSION_CHECKS
UNIVERSITY_COLUMNS = (
    ("logo_url", sa.String(500)),
    ("campuses", sa.JSON()),
    ("fee_structure", sa.Text()),
    ("agent_commission_percent", sa.Numeric(5, 2)),
    ("agent_commission_amount", sa.Numeric(12, 2)),
    ("agent_commission_currency", sa.String(3)),
    ("agent_commission_note", sa.String(300)),
)
COURSE_COLUMNS = (("campus", sa.String(200)), ("fee_text", sa.String(300)), ("intake_text", sa.String(200)))


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())


def _add(inspector, table: str, columns) -> None:
    present = set() if inspector is None else {c["name"] for c in inspector.get_columns(table)}
    for name, type_ in columns:
        if name not in present:
            default = sa.text("'[]'") if name == "campuses" else None
            op.add_column(table, sa.Column(name, type_, nullable=True, server_default=default))


def upgrade() -> None:
    inspector = _inspector()
    _add(inspector, "universities", UNIVERSITY_COLUMNS)
    _add(inspector, "overseas_courses", COURSE_COLUMNS)
    checks = set() if inspector is None else {c["name"] for c in inspector.get_check_constraints("universities")}
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, "universities", sql)


def downgrade() -> None:
    if not op.get_context().as_sql:
        found = op.get_bind().execute(sa.text(
            "SELECT 1 FROM universities WHERE agent_commission_percent IS NOT NULL OR agent_commission_amount IS NOT NULL LIMIT 1"
        )).first()
        if found:
            raise RuntimeError("Cannot downgrade 0157_direct_tieups: agent commissions exist. Remove them deliberately first.")
    for name in reversed(CHECKS):
        op.drop_constraint(name, "universities", type_="check")
    for name, _ in reversed(COURSE_COLUMNS):
        op.drop_column("overseas_courses", name)
    for name, _ in reversed(UNIVERSITY_COLUMNS):
        op.drop_column("universities", name)
```

Note: the model's `campuses` is NOT NULL-less (nullable by default in `mapped_column` with `Mapped[list]`? — `Mapped[list]` makes it
NOT NULL). Make the model match the migration: `mapped_column(JSON, nullable=True, default=list, server_default=text("'[]'"))` and
read it as `uni.campuses or []` everywhere.

- [ ] **Step 5: Run the test, expect PASS.** Also run `tests/test_upc_023_migration.py tests/test_upc_016_migration.py` (single-head checks).
- [ ] **Step 6: Commit** `feat(dtu-001): migration 0157 -- university logo/campuses/fee block, course texts, agent commission`.

---

### Task 2: Agent commission access, PUT route, master detail key, upc-033 sweep extension

**Files:**
- Create: `apps/api/app/services/agent_commission_access.py`
- Modify: `apps/api/app/schemas.py` (`UniversityDetail` ~7079; add `AgentCommissionOut`, `AgentCommissionIn` near it)
- Modify: `apps/api/app/services/partnership_universities.py` (`detail_out` ~268)
- Modify: `apps/api/app/api/partnership_universities.py` (every `response_model=UniversityEnvelope` decorator; new PUT route)
- Modify: `apps/api/tests/test_upc_033_commission_sweep.py` (`_leaks` + its caller), `apps/api/tests/test_upc_033_matrix.py` (new row)
- Test: `apps/api/tests/test_dtu_001_access.py`

**Interfaces:**
- Consumes: Task 1 columns.
- Produces: `agent_commission_access.can_view_agent_commission(user) -> bool`, `can_edit_agent_commission(user) -> bool`,
  `agent_commission_out(uni) -> dict | None`, `with_agent_commission(user, uni, payload: dict) -> dict` (adds key only for viewers).
  Route `PUT /api/v1/partnership/universities/{university_id}/agent-commission`.

- [ ] **Step 1: Read the helpers** `tests/upc001_helpers.py` (`as_role`, `make_head`), `tests/agn001_helpers.py` (`mk_user`,
  `mk_active_org`, `client_for`), `tests/agn004_helpers.py` (`mk_staff`), `tests/upc003_helpers.py` (`BASE`, `create`, `payload`,
  `catalogue_country`). Note their exact signatures; the test below assumes: `as_role(client, db, role, division) -> dict[headers]`,
  `create(client, headers, **over) -> dict(university)`. Adjust calls to the real signatures (keep the assertions).

- [ ] **Step 2: Write the failing test** `apps/api/tests/test_dtu_001_access.py`

```python
"""dtu-001 (DEC-SCOPE-209 §5): the agent commission reaches only super_admin, overseas_admin and an agent Master; one edit route."""

import pytest

from tests.upc001_helpers import as_role
from tests.upc003_helpers import BASE, create

RATE = {"percent": "16.00", "note": "0.16"}


async def _uni_with_rate(client, db_session):
    admin = await as_role(client, db_session, "super_admin", "overseas")
    uni = await create(client, admin)
    r = await client.put(f"{BASE}/{uni['id']}/agent-commission", json=RATE, headers=admin)
    assert r.status_code == 200, r.text
    return uni, admin


@pytest.mark.asyncio
async def test_admins_see_the_rate_on_the_master_detail(client, db_session):
    uni, admin = await _uni_with_rate(client, db_session)
    body = (await client.get(f"{BASE}/{uni['id']}", headers=admin)).json()["university"]
    assert body["agent_commission"] == {"percent": "16.00", "amount": None, "currency": None, "note": "0.16"}
    ovs = await as_role(client, db_session, "overseas_admin", "overseas")
    assert (await client.get(f"{BASE}/{uni['id']}", headers=ovs)).json()["university"]["agent_commission"]["percent"] == "16.00"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partnership_manager", "partnership_head"])
async def test_partnership_roles_do_not_get_the_key(client, db_session, role):
    uni, _ = await _uni_with_rate(client, db_session)
    headers = await as_role(client, db_session, role, "overseas")
    r = await client.get(f"{BASE}/{uni['id']}", headers=headers)
    if r.status_code == 200:  # a manager outside the team gets 403/404 -- either way no key
        assert "agent_commission" not in r.json()["university"]
    assert "agent_commission" not in r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "status"), [
    ("partnership_manager", "overseas", 403), ("partnership_head", "overseas", 403), ("it_admin", "it", 403), ("counselor", "overseas", 403),
])
async def test_only_admins_edit(client, db_session, role, division, status):
    uni, _ = await _uni_with_rate(client, db_session)
    headers = await as_role(client, db_session, role, division)
    r = await client.put(f"{BASE}/{uni['id']}/agent-commission", json={"percent": "20"}, headers=headers)
    assert r.status_code == status


@pytest.mark.asyncio
async def test_anonymous_put_is_401(client, db_session):
    uni, _ = await _uni_with_rate(client, db_session)
    assert (await client.put(f"{BASE}/{uni['id']}/agent-commission", json={"percent": "20"})).status_code == 401


@pytest.mark.asyncio
async def test_put_validates_one_rate_and_clears_with_null(client, db_session):
    uni, admin = await _uni_with_rate(client, db_session)
    url = f"{BASE}/{uni['id']}/agent-commission"
    assert (await client.put(url, json={"percent": "10", "amount": "100", "currency": "GBP"}, headers=admin)).status_code == 422
    assert (await client.put(url, json={"amount": "100"}, headers=admin)).status_code == 422  # amount needs a currency
    assert (await client.put(url, json={"percent": "0"}, headers=admin)).status_code == 422
    assert (await client.put(url, json={"percent": "100.01"}, headers=admin)).status_code == 422
    r = await client.put(url, json={"amount": "4000", "currency": "GBP", "note": "4000GBP flat"}, headers=admin)
    assert r.json()["university"]["agent_commission"] == {"percent": None, "amount": "4000.00", "currency": "GBP", "note": "4000GBP flat"}
    r = await client.put(url, json=None, headers=admin)
    assert r.status_code == 200 and r.json()["university"]["agent_commission"] is None
```

- [ ] **Step 3: Run, expect FAIL** (404 on PUT).

- [ ] **Step 4: Access module** `apps/api/app/services/agent_commission_access.py`:

```python
"""dtu-001 (DEC-SCOPE-209 §5, DT4/DT5/DT13): who sees and edits the agent commission -- what EduSphere pays an agent Master for a
university (DT2). Not upc-016's university commission: `partnership_access` stays as it is (DT7). The key is added only for a viewer,
so every other caller's payload has no `agent_commission` key at all."""

from app.core.rbac import agent_denial_reason, is_agent_staff
from app.models import University, User

AGENT_COMMISSION_ADMIN_ROLES = frozenset({"super_admin", "overseas_admin"})


def can_edit_agent_commission(user: User) -> bool:
    return user.role == "super_admin" or (user.role == "overseas_admin" and user.division == "overseas")


def can_view_agent_commission(user: User) -> bool:
    if can_edit_agent_commission(user):
        return True
    return user.role == "agent" and user.division == "overseas" and not is_agent_staff(user) and not agent_denial_reason(user)


def _money(value) -> str | None:
    return None if value is None else f"{value:.2f}"


def agent_commission_out(uni: University) -> dict | None:
    if uni.agent_commission_percent is None and uni.agent_commission_amount is None:
        return None
    return {
        "percent": _money(uni.agent_commission_percent),
        "amount": _money(uni.agent_commission_amount),
        "currency": uni.agent_commission_currency,
        "note": uni.agent_commission_note,
    }


def with_agent_commission(user: User, uni: University, payload: dict) -> dict:
    return {**payload, "agent_commission": agent_commission_out(uni)} if can_view_agent_commission(user) else payload
```

Confirm `is_agent_staff(user)` / `agent_denial_reason(user)` take a `User` (app/core/rbac.py:95, :118). If `user.division` is not
the attribute name, use what `require_reader` in services/partnership_universities.py uses for the overseas-division check.

- [ ] **Step 5: Schemas** in `app/schemas.py` before `class UniversityDetail`:

```python
class AgentCommissionOut(BaseModel):
    """dtu-001 (DEC-SCOPE-209): EduSphere -> agent Master, per university. Present only for its viewers (agent_commission_access)."""

    percent: str | None
    amount: str | None
    currency: str | None
    note: str | None


class AgentCommissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    percent: Decimal | None = Field(default=None, gt=0, le=100, max_digits=5, decimal_places=2)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    currency: Literal["INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD", "AED"] | None = None
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _one_rate(self):
        if (self.percent is None) == (self.amount is None):
            raise ValueError("Give either a percent or a fixed amount")
        if (self.amount is None) != (self.currency is None):
            raise ValueError("A fixed amount needs its currency (and a percent has none)")
        return self
```

(Use the imports schemas.py already has; add `Decimal`, `Field`, `Literal`, `model_validator` to its imports only if missing.)
Add to `UniversityDetail` (last field): `agent_commission: AgentCommissionOut | None = None  # dtu-001: only for its viewers`.

- [ ] **Step 6: detail_out.** In `services/partnership_universities.py` import `from app.services.agent_commission_access import with_agent_commission`
  and change `detail_out`'s `return {...}` to `return with_agent_commission(user, uni, {...})`.

- [ ] **Step 7: Envelope routes.** In `api/partnership_universities.py` add `response_model_exclude_unset=True` to every decorator with
  `response_model=UniversityEnvelope` (POST "", GET "/{id}", PATCH, assign, publish, unpublish, deactivate, reactivate). Every other
  `UniversityDetail` field is required, so nothing else changes. Then add the route (place after the PATCH route):

```python
@router.put("/{university_id}/agent-commission", response_model=UniversityEnvelope, response_model_exclude_unset=True)
async def set_agent_commission(university_id: UUID, payload: AgentCommissionIn | None = Body(None), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """dtu-001 (DEC-SCOPE-209, DT5): super_admin / overseas_admin set or clear (null) the agent commission; audited old -> new."""
    if not can_edit_agent_commission(user):
        raise HTTPException(403, "Only a super admin or an overseas admin can change the agent commission")
    uni = await svc.load(db, university_id, lock=True)
    before = agent_commission_out(uni)
    uni.agent_commission_percent = payload.percent if payload else None
    uni.agent_commission_amount = payload.amount if payload else None
    uni.agent_commission_currency = payload.currency if payload else None
    uni.agent_commission_note = payload.note if payload else None
    after = agent_commission_out(uni)
    if before != after:
        svc.audit(db, user, "agent_commission", uni.id, {"before": before, "after": after})
    await db.commit()
    return {"university": await svc.detail_out(db, user, uni)}
```

Check `svc.load(db, id, lock=True)` exists in services/partnership_universities.py (used by university_courses.writable_university);
check `svc.audit` writes `university.<action>`. Import `Body` from fastapi, `AgentCommissionIn` from app.schemas,
`agent_commission_out, can_edit_agent_commission` from the new module.

- [ ] **Step 8: Sweep extension.** In `tests/test_upc_033_commission_sweep.py`:

```python
# dtu-001 (DEC-SCOPE-209 DT4): the agent commission (EduSphere -> agent Master) is a separate figure; overseas_admin may see it on the
# university master. It stays a leak for every other caller, and U2's sentinels are untouched.
AGENT_COMMISSION_VIEWERS = {"ovs_admin"}


def _leaks(response, role: str | None = None) -> list[str]:
    body = response.text
    found = [f"sentinel {name}={value}" for name, value in SENTINELS.items() if value in body]
    if response.headers.get("content-type", "").startswith("application/json"):
        found += [
            f"key {k}" for k in _keys(json.loads(body))
            if (k == "factors" or "commission" in k.lower()) and not (k.startswith("agent_commission") and role in AGENT_COMMISSION_VIEWERS)
        ]
    return found
```

and in `test_no_commission_reaches_a_non_commission_role` call `_leaks(response, role)`. (Keep the docstrings; add the comment.)

- [ ] **Step 9: Matrix row.** In `tests/test_upc_033_matrix.py` add, next to the other `/partnership/universities/{uni}` rows:
  `R("put", "/partnership/universities/{uni}/agent-commission", {"percent": "12"}, **_all(200, "super", "ovs_admin")),`
  Read how `R`/`_all` treat unlisted roles (expected 403; anon 401) and how a body is passed; match that form exactly.

- [ ] **Step 10: Run** `tests/test_dtu_001_access.py tests/test_upc_033_commission_sweep.py tests/test_upc_033_matrix.py tests/test_upc_003*.py` → PASS.
- [ ] **Step 11: Commit** `feat(dtu-001): agent commission access, PUT route, master detail key; upc-033 sweep tolerates it for overseas_admin only`.

---

### Task 3: Public catalogue fields (logo, campuses, fee block, course texts)

**Files:**
- Modify: `apps/api/app/schemas.py` — `UniversityOut` (1570), `UniversityRow` (7035), `UniversityDetail`, `UniversityCreate` (6938),
  `UniversityUpdate` (6960), `CourseIn` (9761), `CourseUpdate` (9784)
- Modify: `apps/api/app/services/partnership_universities.py` (`row_out`, `detail_out` tuple)
- Modify: `apps/api/app/services/university_courses.py` (`FIELDS`, `course_out`)
- Modify: `apps/api/app/services/university_view.py` (`PROFILE_FIELDS`, `COURSE_FIELDS`)
- Modify: `apps/api/app/api/public.py` (course dicts at 161 and 179)
- Test: `apps/api/tests/test_dtu_001_catalogue.py`

**Interfaces:**
- Produces: public JSON keys `logo_url`, `campuses`, `fee_structure` on universities; `campus`, `fee_text`, `intake_text` on courses.

- [ ] **Step 1: Failing test** `apps/api/tests/test_dtu_001_catalogue.py`

```python
"""dtu-001 §6: the catalogue's new public fields, everywhere a university / course is read; never the agent commission in public."""

import pytest

from tests.upc001_helpers import as_role
from tests.upc003_helpers import BASE, create

API = "/api/v1"


async def _published(client, db_session):
    admin = await as_role(client, db_session, "super_admin", "overseas")
    uni = await create(client, admin, logo_url="/universities/logos/x.png", campuses=["Cardiff", "Newport"], fee_structure="UG: £1 – £2")
    r = await client.post(f"{BASE}/{uni['id']}/courses", json={
        "title": "MBA Global", "level": "PG", "category": "Business", "duration": "Not specified",
        "campus": "Newport Campus", "fee_text": "£18,970", "intake_text": "January / September",
    }, headers=admin)
    assert r.status_code == 201, r.text
    await client.put(f"{BASE}/{uni['id']}/agent-commission", json={"percent": "13"}, headers=admin)
    pub = await client.post(f"{BASE}/{uni['id']}/publish", headers=admin)
    assert pub.status_code == 200, pub.text
    return uni, admin


@pytest.mark.asyncio
async def test_master_round_trips_the_new_fields(client, db_session):
    uni, admin = await _published(client, db_session)
    body = (await client.get(f"{BASE}/{uni['id']}", headers=admin)).json()["university"]
    assert body["logo_url"] == "/universities/logos/x.png" and body["campuses"] == ["Cardiff", "Newport"] and body["fee_structure"] == "UG: £1 – £2"
    course = (await client.get(f"{BASE}/{uni['id']}/courses", headers=admin)).json()["items"][0]
    assert (course["campus"], course["fee_text"], course["intake_text"]) == ("Newport Campus", "£18,970", "January / September")


@pytest.mark.asyncio
async def test_public_detail_and_lists_show_them(client, db_session):
    uni, _ = await _published(client, db_session)
    d = (await client.get(f"{API}/public/universities/{uni['slug']}")).json()
    assert d["university"]["logo_url"] == "/universities/logos/x.png" and d["university"]["campuses"] == ["Cardiff", "Newport"]
    assert d["courses"][0]["campus"] == "Newport Campus" and d["courses"][0]["fee_text"] == "£18,970"
    listed = (await client.get(f"{API}/public/universities", params={"q": uni["name"]})).json()
    assert listed[0]["logo_url"] == "/universities/logos/x.png"


@pytest.mark.asyncio
async def test_public_never_carries_agent_commission(client, db_session):
    uni, _ = await _published(client, db_session)
    for path in (f"/public/universities/{uni['slug']}", f"/public/universities?q={uni['name']}", "/public/overseas-courses?category=Business"):
        assert "agent_commission" not in (await client.get(API + path)).text
```

Read `upc003_helpers.create` / `payload`: if `create` does not accept extra fields, call `client.post(BASE, json={**payload(...), ...})`
directly. Read the publish route requirements (`check_publishable`: catalogue country + overview) and make `create` satisfy them.

- [ ] **Step 2: Run, expect FAIL** (422 extra fields).
- [ ] **Step 3: Implement.**
  - `UniversityOut`: add `logo_url: str | None = None`, `campuses: list | None = None`, `fee_structure: str | None = None`.
  - `UniversityRow`: add `logo_url: str | None`. `row_out`: add `"logo_url": uni.logo_url`.
  - `UniversityDetail`: add `campuses: list[str]`, `fee_structure: str | None`. `detail_out`: add `"fee_structure"` to the attribute
    tuple and `"campuses": uni.campuses or []` to the dict.
  - `UniversityCreate`/`UniversityUpdate`: add `logo_url: UniversityWebsite = None` (reuse the website type only if it accepts a
    site-relative path; otherwise declare `LogoUrl = Annotated[str | None, Field(max_length=500, pattern=r"^(/universities/logos/[a-z0-9-]+\.(png|svg|jpg|jpeg|webp)|https://\S+)$")]`),
    `campuses: list[Annotated[str, Field(min_length=1, max_length=120)]] | None = Field(default=None, max_length=20)`,
    `fee_structure: str | None = Field(default=None, max_length=4000)`. In the create route `values` already flows into `University(**values)`;
    convert `campuses=None` to `[]` there (`values["campuses"] = values.get("campuses") or []`).
  - `CourseIn`/`CourseUpdate`: add `campus: _university_str(200) = None`, `fee_text: _university_str(300) = None`,
    `intake_text: _university_str(200) = None` (check `_university_str(n)` without `required=True` yields an optional str).
  - `university_courses.FIELDS`: append `"campus", "fee_text", "intake_text"`. `course_out`: add them to the first `getattr` tuple.
  - `university_view.COURSE_FIELDS` += `"campus", "fee_text", "intake_text"`; `PROFILE_FIELDS` += `"logo_url", "campuses", "fee_structure"`.
  - `public.py` both course dicts: add `"campus": c.campus, "fee_text": c.fee_text, "intake_text": c.intake_text`.
  - `services/course_import.py` `COLUMNS`: append `"campus", "fee_text", "intake_text"` (CSV parity with the form).
- [ ] **Step 4: Run** `tests/test_dtu_001_catalogue.py tests/test_upc_017*.py tests/test_upc_030*.py tests/test_upc_033_commission_sweep.py`
  plus any test file asserting the exact key set of `UniversityOut` / public detail (`grep -l "public/universities" tests/`) → PASS.
- [ ] **Step 5: Commit** `feat(dtu-001): catalogue logo, campuses, fee block and course campus/fee/intake texts`.

---

### Task 4: Agent Partner Universities endpoints

**Files:**
- Create: `apps/api/app/services/agent_partner_universities.py`
- Modify: `apps/api/app/api/agent_shortlist.py` (two GET routes; the router prefix is `/workflows/overseas/agent/crm`)
- Test: `apps/api/tests/test_dtu_001_agent_partners.py`

**Interfaces:**
- Consumes: `with_agent_commission` (Task 2), Task 3 fields, `_gate` from `app.api.agent_students`.
- Produces: `GET /api/v1/workflows/overseas/agent/crm/partner-universities?q=&country=&limit=&offset=` →
  `{"items": [{id, slug, name, logo_url, city, campuses, country: {id, name, iso2}, course_count, agent_commission?}], "total": int}`;
  `GET …/partner-universities/{id}` → `{"university": {…list fields, website, overview, fee_structure, deadlines, scholarships,
  courses: [{id, title, level, category, duration, campus, fee_text, intake_text, tuition_fee, intake}], agent_commission?}}`.

- [ ] **Step 1: Failing test** `apps/api/tests/test_dtu_001_agent_partners.py`

```python
"""dtu-001 §6: agents browse the published catalogue; only a Master gets the agent commission."""

import pytest

from tests.agn001_helpers import client_for, mk_active_org
from tests.agn004_helpers import mk_staff
from tests.test_dtu_001_catalogue import _published

URL = "/api/v1/workflows/overseas/agent/crm/partner-universities"


@pytest.mark.asyncio
async def test_master_sees_the_rate_staff_do_not(client, db_session):
    uni, _ = await _published(client, db_session)
    org = await mk_active_org(db_session)
    staff = await mk_staff(db_session, org)
    await db_session.commit()
    async with client_for(org["master"].email) as master:
        items = (await master.get(URL, params={"q": uni["name"]})).json()["items"]
        assert items[0]["agent_commission"]["percent"] == "13.00" and items[0]["course_count"] == 1
        detail = (await master.get(f"{URL}/{uni['id']}")).json()["university"]
        assert detail["agent_commission"]["percent"] == "13.00" and detail["courses"][0]["campus"] == "Newport Campus"
    async with client_for(staff["user"].email) as s:
        r = await s.get(URL, params={"q": uni["name"]})
        assert r.status_code == 200 and "agent_commission" not in r.text
        assert "agent_commission" not in (await s.get(f"{URL}/{uni['id']}")).text


@pytest.mark.asyncio
async def test_hidden_or_inactive_university_is_404(client, db_session):
    uni, admin = await _published(client, db_session)
    await client.post(f"/api/v1/partnership/universities/{uni['id']}/unpublish", headers=admin)
    org = await mk_active_org(db_session)
    await db_session.commit()
    async with client_for(org["master"].email) as master:
        assert (await master.get(f"{URL}/{uni['id']}")).status_code == 404
        assert all(i["id"] != uni["id"] for i in (await master.get(URL, params={"q": uni["name"]})).json()["items"])


@pytest.mark.asyncio
async def test_non_agents_and_pending_agencies_are_refused(client, db_session):
    from tests.upc001_helpers import as_role

    for role, division in (("counselor", "overseas"), ("overseas_admin", "overseas"), ("student", "overseas")):
        assert (await client.get(URL, headers=await as_role(client, db_session, role, division))).status_code == 403
    assert (await client.get(URL)).status_code == 401
```

Check `mk_active_org` / `mk_staff` / `client_for` signatures and how a *pending* org is made (add a pending-agency assertion
returning 403 using whatever `agn001_helpers` offers — e.g. `mk_org(status="pending")`; if none exists, set `org["org"].status = "pending"`).

- [ ] **Step 2: Run, expect FAIL** (404 route).
- [ ] **Step 3: Service** `apps/api/app/services/agent_partner_universities.py`:

```python
"""dtu-001 (DEC-SCOPE-209 §6): the agent portal's Partner Universities -- the published catalogue (public_visible) with its courses.
Read-only. The agent commission is added only for a Master (agent_commission_access)."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Country, OverseasCourse, University, User
from app.services.agent_commission_access import with_agent_commission
from app.services.partnership_universities import public_visible

COURSE_KEYS = ("id", "title", "level", "category", "duration", "campus", "fee_text", "intake_text", "tuition_fee", "intake")


def _row(user: User, uni: University, country: Country, course_count: int) -> dict:
    return with_agent_commission(user, uni, {
        "id": uni.id, "slug": uni.slug, "name": uni.name, "logo_url": uni.logo_url, "city": uni.city, "campuses": uni.campuses or [],
        "country": {"id": country.id, "name": country.name, "iso2": country.iso2}, "course_count": course_count,
    })


async def page(db: AsyncSession, user: User, *, q: str | None, country: UUID | None, limit: int, offset: int) -> dict:
    courses = select(OverseasCourse.university_id, func.count().label("n")).where(OverseasCourse.active.is_(True)).group_by(OverseasCourse.university_id).subquery()
    stmt = select(University, Country, func.coalesce(courses.c.n, 0)).join(Country, University.country_id == Country.id).outerjoin(courses, courses.c.university_id == University.id).where(*public_visible())
    if q:
        stmt = stmt.where(or_(University.name.ilike(f"%{q}%"), University.city.ilike(f"%{q}%")))
    if country:
        stmt = stmt.where(University.country_id == country)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(University.name, University.id).limit(limit).offset(offset))).all()
    return {"items": [_row(user, u, c, n) for u, c, n in rows], "total": total}


async def detail(db: AsyncSession, user: User, university_id: UUID) -> dict:
    found = (await db.execute(select(University, Country).join(Country, University.country_id == Country.id).where(University.id == university_id, *public_visible()))).first()
    if found is None:
        raise HTTPException(404, "University not found")
    uni, country = found
    cs = (await db.scalars(select(OverseasCourse).where(OverseasCourse.university_id == uni.id, OverseasCourse.active.is_(True)).order_by(OverseasCourse.level, OverseasCourse.title))).all()
    body = {
        **_row(user, uni, country, len(cs)),
        "website": uni.website, "overview": uni.overview, "fee_structure": uni.fee_structure, "deadlines": uni.deadlines, "scholarships": uni.scholarships,
        "courses": [{k: getattr(c, k) for k in COURSE_KEYS} for c in cs],
    }
    return {"university": body}
```

Confirm `public_visible()` is importable from `services/partnership_universities.py` (line ~72; `public.py` imports it from there).

- [ ] **Step 4: Routes** in `api/agent_shortlist.py` (before the `/universities` routes; import `from app.services import agent_partner_universities as partners`):

```python
@router.get("/partner-universities")
async def partner_universities(
    q: str | None = Query(None, max_length=100),
    country: UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """dtu-001: the published catalogue for agents (Master and staff); the agent commission for a Master only (DT4)."""
    _gate(user)
    return await partners.page(db, user, q=q, country=country, limit=limit, offset=offset)


@router.get("/partner-universities/{university_id}")
async def partner_university(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _gate(user)
    return await partners.detail(db, user, university_id)
```

- [ ] **Step 5: Run** `tests/test_dtu_001_agent_partners.py tests/test_agn_007*.py` → PASS.
- [ ] **Step 6: Commit** `feat(dtu-001): agent Partner Universities endpoints (Master sees the agent commission)`.

---

### Task 5: Parser (pure) + coverage check + CLI

**Files:**
- Create: `apps/api/app/direct_tieups/__init__.py` (empty), `apps/api/app/direct_tieups/parse.py`
- Test: `apps/api/tests/test_dtu_001_parse.py`

**Interfaces:**
- Produces: `parse_workbook(sheets: dict[str, list[tuple]]) -> tuple[list[dict], list[tuple]]` (universities, unmapped cells);
  `parse_commission(value) -> dict | None` → `{"percent": "13.00"} | {"amount": "4000.00", "currency": "GBP"}` plus `"note"`;
  `parse_fee(text) -> tuple[str | None, str | None]` (low-end amount, currency); `months(text) -> list[str]`;
  `category_of(title) -> str`; CLI `python -m app.direct_tieups.parse <xlsx> <out_dir>`.
  University dict shape (the JSON contract Task 7 consumes):
  `{"name", "country_iso2", "city", "campuses": [], "institution_type", "website", "overview", "fee_structure", "deadlines": [],
    "scholarships": [], "agent_commission": {...}|None, "courses": [{"title", "level", "category", "duration", "campus",
    "fee_text", "tuition_amount", "tuition_currency", "intakes": [], "intake_text", "scholarships": []}], "flags": [str],
    "source": "Direct Tie-up's!B37"}`

- [ ] **Step 1: Failing test** `apps/api/tests/test_dtu_001_parse.py` (fixture rows copy the sheet's real shapes, one per layout):

```python
"""dtu-001 §4: the parser maps every non-empty cell (0 unmapped) and parses commission / fee / intake texts."""

import pytest

from app.direct_tieups.parse import category_of, months, parse_commission, parse_fee, parse_workbook

HEAD_A = ("Name of the university", "Destination and campus", "Commission", "Ug Courses", "Campus", "Available Intake", "Tution fee", "Scholarship",
          "Pg courses with campus", "Campus", "Tution fee", "Scholarship", None, "Intakes", "Tution Fee", "University Link")


def _sheets(main_rows):
    return {
        "Direct Tie-up's": main_rows,
        "iu": [("Name of the University", "Destination", "Commission"), ("University of East Anglia", "UK", "4000GBP flat"), ("University of Hull", "UK", 0.18)],
        "uc": [("Coventry University",), ("University of Greenwich",)],
    }


def _main():
    rows = [HEAD_A]
    rows.append(("University of Southwales", "UK__ Cardiff Campus,Newport Campus", 0.13, "BA (Hons) Business and Management", "Cardiff Campus", " January 2027",
                 "£15,800 – £16,200 per year", "£1,500-£2,500", "MBA Global", "Newport Campus", "£18,970", "£1,500-£2,500", None, "January / September", None,
                 "https://www.southwales.ac.uk/"))
    rows.append((None, None, None, "BSc (Hons) Computing", "Cardiff Campus", " January 2027", "£15,800 – £16,200 per year", None, None, None, None, None, None,
                 "January / September", None, None))
    rows += [(None,) * 16] * (35 - len(rows))  # pad to the layout-B header row 36
    rows.append(("University Name", "Destination and campus", None, "UG Courses Offered", None, "PG Courses Offered", "Tuition Fee Structure",
                 "Scholarships & Financial Aid", "Available Intakes", "Application Deadlines", "Application Link", None, None, None, None, None))
    rows.append(("BPP University", "UK(London Campus,Birmingham)", None, "• BSc (Hons) Accounting and Finance\n• BSc (Hons) Law", None,
                 "• Master's in Business Administration (MBA)", "• UG: £11,000 – £13,366 / year\n• PG (12 Mo): £14,000 – £16,000",
                 "• International PG Bursary: £1,000 – £1,500", "• January / February\n• September", "• Jan Intake: Mid-November", "https://www.bpp.com/",
                 None, None, None, None, None))
    rows += [(None,) * 16] * (63 - len(rows))
    rows.append(("Walbrook", "UK,London campus", None, "BSc (Hons) Banking and Digital Finance", "£14,500 – £16,500 per year", "MSc Business and Management",
                 "£16,000 – £18,500 per year", "Early Enrolment Discounts:2000,4000 pounds", "Jan,Sep,OCT,NOV", "Mid-November 2026 for Jan",
                 "https://www.walbrook.ac.uk/", None, None, None, None, None))
    return rows


def test_every_cell_is_mapped_and_universities_are_built():
    unis, unmapped = parse_workbook(_sheets(_main()))
    assert unmapped == []
    names = {u["name"] for u in unis}
    assert {"University of Southwales", "BPP University", "Walbrook", "University of East Anglia", "University of Hull", "Coventry University", "University of Greenwich"} <= names
    sw = next(u for u in unis if u["name"] == "University of Southwales")
    assert sw["country_iso2"] == "GB" and sw["campuses"] == ["Cardiff Campus", "Newport Campus"] and sw["city"] == "Cardiff Campus"
    assert sw["agent_commission"] == {"percent": "13.00", "note": "0.13"}
    ug = next(c for c in sw["courses"] if c["title"] == "BA (Hons) Business and Management")
    assert (ug["level"], ug["campus"], ug["tuition_amount"], ug["tuition_currency"], ug["intakes"], ug["intake_text"]) == ("UG", "Cardiff Campus", "15800.00", "GBP", ["Jan"], "January 2027")
    pg = next(c for c in sw["courses"] if c["title"] == "MBA Global")
    assert pg["intakes"] == ["Jan", "Sep"] and pg["fee_text"] == "£18,970"  # column N applies to PG (spec §4.3)
    bpp = next(u for u in unis if u["name"] == "BPP University")
    assert [c["title"] for c in bpp["courses"]] == ["BSc (Hons) Accounting and Finance", "BSc (Hons) Law", "Master's in Business Administration (MBA)"]
    assert bpp["courses"][2]["duration"] == "12 months" and bpp["courses"][0]["tuition_amount"] == "11000.00"
    assert bpp["deadlines"] == ["Jan Intake: Mid-November"] and bpp["scholarships"] == ["International PG Bursary: £1,000 – £1,500"]
    assert next(u for u in unis if u["name"] == "Coventry University")["country_iso2"] == "GB"


def test_an_unknown_cell_is_reported():
    rows = _main()
    rows[1] = rows[1][:12] + ("stray",) + rows[1][13:]  # column M is unmapped
    _, unmapped = parse_workbook(_sheets(rows))
    assert unmapped == [("Direct Tie-up's", 2, 13, "stray")]


@pytest.mark.parametrize(("value", "expected"), [
    (0.13, {"percent": "13.00", "note": "0.13"}),
    (0.175, {"percent": "17.50", "note": "0.175"}),
    ("4000GBP flat", {"amount": "4000.00", "currency": "GBP", "note": "4000GBP flat"}),
    ("2500GBP flat", {"amount": "2500.00", "currency": "GBP", "note": "2500GBP flat"}),
    ("1,50,000 INR flat", {"amount": "150000.00", "currency": "INR", "note": "1,50,000 INR flat"}),
    ("16 %", {"percent": "16.00", "note": "16 %"}),
    (None, None),
    ("", None),
])
def test_parse_commission(value, expected):
    assert parse_commission(value) == expected


def test_parse_commission_rejects_garbage():
    with pytest.raises(ValueError, match="commission"):
        parse_commission("ask partner")


@pytest.mark.parametrize(("text", "expected"), [
    ("£15,800 – £16,200 per year", ("15800.00", "GBP")), ("A$60,000 total", ("60000.00", "AUD")), ("€6,000 – €7,500 / year", ("6000.00", "EUR")),
    ("~$21,000 – $24,000 / year", ("21000.00", "USD")), ("AED 85,200", (None, None)), ("₹3,500,000 – ₹6,000,000 total", ("3500000.00", "INR")), ("", (None, None)),
])
def test_parse_fee(text, expected):
    assert parse_fee(text) == expected


def test_months_and_category():
    assert months("January / February\nMay / June\nSeptember / October") == ["Jan", "Feb", "May", "Jun", "Sep", "Oct"]
    assert months("Jan,Sep,OCT,NOV") == ["Jan", "Sep", "Oct", "Nov"]
    assert months("Monthly modular entry") == []
    assert category_of("MBA Global (Finance / Financial Services)") == "Business"
    assert category_of("BSc (Hons) Computer Science & AI") == "Computing & IT"
    assert category_of("BSc (Hons) Chiropractic") == "Health"
    assert category_of("International Foundation Year") == "General"
```

AED: the course master's currency list (`COUNSELING_CURRENCIES`) has no AED (check; if it has, expect `("85200.00", "AED")`), so AED
fees keep `fee_text` only. Write the test to whatever Task 1 decided.

- [ ] **Step 2: Run, expect FAIL** (ImportError).
- [ ] **Step 3: Implement `parse.py`.** Required behaviour (write it to satisfy the tests above and spec §4.2–§4.3):
  - Layout by main-sheet row number: A rows 2–34 (map in spec §4.2), B rows 37–62, C rows ≥ 63; header rows {1, 36, 44, 50} skipped;
    a cell equal to `"__"` counts as empty. Column maps are module constants `LAYOUT_A`, `LAYOUT_B`, `LAYOUT_C` (1-based column → destination key).
    Any non-empty cell whose column has no destination is appended to `unmapped` as `(sheet, row, column, str(value))`.
    For layout A, column 14 (`Intakes`) → PG courses' intakes; column 15 is mapped to `uni.tuition_fee` and, when non-empty,
    is recorded on the university flags (`"column O had a value: …"`) — it is empty today.
  - A row with column A set starts a university; following rows with A empty add courses to it.
  - `bullets(text)`: split on newlines, strip leading `•`, `-`, `*` and whitespace, drop empties.
  - Destination: `"UK__ Cardiff Campus,Newport Campus"` / `"UK(London Campus,Birmingham)"` / `"Australia,Sydney Campus"` /
    `"France__(EMA Paris campus)"` / `"Dubai"` / `"Paris , Berlin,Nancy"` → `(iso2, campuses)`. Country words map:
    `{"uk": "GB", "usa": "US", "us": "US", "australia": "AU", "france": "FR", "germany": "DE", "malta": "MT", "dubai": "AE", "uae": "AE", "paris": "FR"}`.
    Name-based overrides: `Schiller` → US, `Berlin School of Business` → DE, `GBS Dubai` → AE, `GBS Malta` → MT, `ICN` → FR.
    `uc` sheet → GB; `iu` destination column → country.
    `city` = first campus with the word "Campus"/"campus" kept as written; when there is no campus, the capital
    `{"GB": "London", "US": "Washington", "AU": "Canberra", "FR": "Paris", "DE": "Berlin", "MT": "Valletta", "AE": "Dubai"}` and flag it.
  - Name clean-up: strip, collapse whitespace/newlines; text in parentheses after a newline ("Schiller International University\n(US, Spain, France, Germany)")
    is moved to the overview ("Also in: US, Spain, France, Germany").
  - `parse_commission`: float < 1 → percent ×100 (2 dp); `"N %"` → percent; `"<digits> <CUR> flat"` / `"<digits><CUR> flat"` → amount
    (strip commas; Indian grouping "1,50,000" → 150000) with currency; None/"" → None; anything else → `ValueError("commission: …")`.
    `note` = the raw text (`str(value)` for floats, e.g. `"0.13"`).
  - `parse_fee`: currency by symbol/prefix (`£`→GBP, `€`→EUR, `A$`→AUD, `$`→USD, `₹`→INR, `AED`→AED); first number = low end;
    returns `(None, None)` when the currency is not in the course master's list or no number.
  - Layout B fee block: the bullet starting `UG` applies to UG courses, `PG` to PG courses (fee_text = that bullet without the
    `UG:`/`PG …:` label; tuition from `parse_fee`); `"(12 Mo)"` in the PG label → duration "12 months". Whole block → `fee_structure`.
    No UG/PG labels (e.g. "Pathway Programs: …") → applied to every course.
  - `months`: find month names/abbreviations in order, dedupe, map to `COURSE_MONTHS` codes (`Jan`…`Dec`).
  - `category_of`: keyword table from spec §4.3, first match wins, else "General". Duration default "Not specified".
  - `institution_type`: spec §4.3 (`university` if "University" in the name, else `institute` for Institute/Institutions/School/College/
    Ecole/Pathway/BIGS/Walbrook names).
  - Website/application link: a value starting with `http` (also inside parentheses, e.g. `(https://arizona.avila.edu/)`) → `website`;
    otherwise `overview` gets `"Application portal: <text>"`.
  - Scholarship: layout A per-course cells → the course's `scholarships` list and the university's list (deduped); layouts B/C →
    university list; a float (BIGS `0.25`) → `"25% tuition scholarship"`.
  - Deadlines: bullets → `deadlines`.
  - Overview default (required by publish): `"<name> — direct tie-up partner in <city>, <country name>."` plus any extra lines above.
  - CLI `main(argv)`: `import openpyxl` inside the function; read the three sheets (`values_only=True`); run `parse_workbook`; if
    `unmapped` → print them and `sys.exit(1)`; write `<out_dir>/direct_tieups.json` (sorted by name, `ensure_ascii=False`, indent 2)
    and `<out_dir>/direct_tieups_review.csv` (one row per course plus one per university without courses: university, country,
    city, campuses, agent commission, course, level, category, duration, campus, fee_text, tuition, intakes, intake_text, flags).
- [ ] **Step 4: Run test → PASS.**
- [ ] **Step 5: Run the CLI on the real file** (dev machine, openpyxl present):
  ```bash
  cd /c/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/direct-tieups/apps/api
  PYTHONIOENCODING=utf-8 python -m app.direct_tieups.parse "C:/Users/admin/Downloads/Direct Tie-ups.xlsx" seed
  ```
  Expected: exit 0, 35 universities in `seed/direct_tieups.json`. If unmapped cells are printed, fix the layout map (not the data).
- [ ] **Step 6: Commit** `feat(dtu-001): Direct Tie-ups parser with coverage check; generated seed JSON + review CSV`.
- [ ] **Step 7: OWNER CHECKPOINT.** Stop. Show the owner a summary (35 universities, course count, every flag) and the path
  `apps/api/seed/direct_tieups_review.csv`; ask (AskUserQuestion, one question) whether to proceed or what to correct. Corrections
  go into the parser rules (re-run Step 5), never by hand-editing the JSON.

---

### Task 6: Logos

**Files:**
- Create: `apps/web/public/universities/logos/<slug>.<ext>` (one per university found)
- Modify: `apps/api/seed/direct_tieups.json` (`logo_url` per university) via a small scratch script
- Create: `apps/api/seed/direct_tieups_logos.csv` (name, official site, source URL of the image, file, retrieved date)

- [ ] **Step 1:** For each university: start from `website`; otherwise web-search "<name> official site" and take the institution's
  own domain only. On the home page find, in order: an `<img>` inside the header/nav whose `src`/`alt`/`class` contains "logo";
  `link[rel=icon][type=image/svg+xml]`; `meta[property=og:image]`; `link[rel=apple-touch-icon]`. Download over https with a 10 s timeout
  and ≤ 200 KB; keep `.svg/.png/.jpg/.webp` only. Save as `<slug>.<ext>` where `slug` = `slugify(name)` (lowercase, `[^a-z0-9]+` → `-`).
  Write downloads into the scratchpad first (untrusted downloads: own directory, never executed), then copy the vetted file in.
- [ ] **Step 2:** Open each image (Read tool) and confirm it is the institution's logo/crest (not a hero photo or a cookie banner).
  Reject and leave `logo_url` null otherwise. Shared-brand sites (gedu.global serves GBS UK/Dubai/Malta, MLA, EMA): use a logo only
  if it names that institution; else null (the UI shows a monogram).
- [ ] **Step 3:** Set `logo_url: "/universities/logos/<file>"` in the JSON; record provenance in `direct_tieups_logos.csv`.
- [ ] **Step 4: Commit** `feat(dtu-001): university logos from official sites (provenance in seed/direct_tieups_logos.csv)`.

---

### Task 7: Idempotent loader

**Files:**
- Create: `apps/api/app/direct_tieups/load.py`
- Test: `apps/api/tests/test_dtu_001_load.py`

**Interfaces:**
- Consumes: the JSON contract from Task 5 (+ `logo_url` from Task 6); `services.university_courses.title_key`, `derive_texts`;
  `services.partnership_universities.next_code`, `free_slug`, `name_key_of`.
- Produces: `async def load(db, data: list[dict]) -> dict[str, int]` returning counts
  `{"universities_created", "universities_updated", "courses_created", "courses_skipped", "scholarships_created", "conflicts"}`;
  CLI `python -m app.direct_tieups.load [--dry-run] [--file seed/direct_tieups.json]`.

- [ ] **Step 1: Failing test** `apps/api/tests/test_dtu_001_load.py`

```python
"""dtu-001 §4.4: the loader creates, then a second run changes nothing; existing values are never overwritten."""

import uuid

import pytest
from sqlalchemy import select

from app.direct_tieups.load import load
from app.models import AuditLog, OverseasCourse, Scholarship, University


def _data(name: str) -> list[dict]:
    return [{
        "name": name, "country_iso2": "GB", "city": "Cardiff Campus", "campuses": ["Cardiff Campus", "Newport Campus"], "institution_type": "university",
        "website": "https://example.ac.uk/", "overview": f"{name} — direct tie-up partner.", "fee_structure": None, "deadlines": ["Jan: Mid-November"],
        "scholarships": ["£1,500-£2,500"], "agent_commission": {"percent": "13.00", "note": "0.13"}, "logo_url": None, "flags": [], "source": "test",
        "courses": [{"title": "MBA Global", "level": "PG", "category": "Business", "duration": "Not specified", "campus": "Newport Campus", "fee_text": "£18,970",
                     "tuition_amount": "18970.00", "tuition_currency": "GBP", "intakes": ["Jan", "Sep"], "intake_text": "January / September", "scholarships": ["£1,500-£2,500"]}],
    }]


@pytest.mark.asyncio
async def test_creates_then_is_a_no_op(db_session):
    name = f"Dtu Load University {uuid.uuid4().hex[:8]}"
    first = await load(db_session, _data(name))
    assert first["universities_created"] == 1 and first["courses_created"] == 1 and first["scholarships_created"] == 1
    uni = await db_session.scalar(select(University).where(University.name == name))
    assert uni.catalogue_visible and uni.active and uni.agent_commission_percent == 13 and uni.campuses == ["Cardiff Campus", "Newport Campus"]
    course = await db_session.scalar(select(OverseasCourse).where(OverseasCourse.university_id == uni.id))
    assert course.tuition_fee and course.intake == "Jan, Sep" and course.campus == "Newport Campus" and len(course.scholarship_ids) == 1
    assert await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(uni.id), AuditLog.action == "university.direct_tieup_load"))
    second = await load(db_session, _data(name))
    assert second == {"universities_created": 0, "universities_updated": 0, "courses_created": 0, "courses_skipped": 1, "scholarships_created": 0, "conflicts": 0}


@pytest.mark.asyncio
async def test_existing_values_are_never_overwritten(db_session):
    name = f"Dtu Existing University {uuid.uuid4().hex[:8]}"
    await load(db_session, _data(name))
    uni = await db_session.scalar(select(University).where(University.name == name))
    uni.website, uni.agent_commission_percent = "https://edited.example/", 20
    await db_session.commit()
    data = _data(name)
    data[0]["fee_structure"] = "UG: £1"
    report = await load(db_session, data)
    await db_session.refresh(uni)
    assert uni.website == "https://edited.example/" and uni.agent_commission_percent == 20 and uni.fee_structure == "UG: £1"
    assert report["universities_updated"] == 1 and report["conflicts"] == 1  # the differing agent commission is reported, not changed


@pytest.mark.asyncio
async def test_unknown_country_fails_the_whole_run(db_session):
    data = _data(f"Dtu Bad Country {uuid.uuid4().hex[:8]}")
    data[0]["country_iso2"] = "ZZ"
    with pytest.raises(ValueError, match="ZZ"):
        await load(db_session, data)
```

`load` commits; `--dry-run` is the CLI's job (it calls `load` inside a transaction it rolls back — implement `load(db, data, commit=True)`).

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `load.py`:**
  - Resolve every `country_iso2` first (`select(Country).where(Country.iso2 == code)`); any missing → `ValueError(f"unknown country {code}")`
    before writing anything.
  - Match a university: `University.country_id == country.id and University.name_key == name_key_of(name)`; if several, take the
    oldest and add a conflict.
  - New: `University(university_code=await next_code(db), slug=await free_slug(db, name, code), catalogue_visible=True, active=True,
    requirements=[], eligibility="", <the JSON fields>, agent_commission_* from the dict)`; `db.flush()`.
  - Existing: for `logo_url, campuses, fee_structure, website, overview, deadlines, scholarships`: set only when the stored value is
    empty (`None`, `""`, `[]`); agent commission: set only when both stored percent and amount are NULL; if set and different → conflict.
    Count `universities_updated` when any field was filled.
  - Scholarship rows: per text, `select(Scholarship).where(Scholarship.university_id == uni.id, func.lower(Scholarship.title) == text.lower())`;
    create `Scholarship(title=text[:200], university_id=uni.id, country_id=country.id, eligibility="See university", amount=text[:120], active=True)`.
  - Courses: existing keys via `title_key(c.title, c.level)` for the university's courses; skip duplicates; else
    `OverseasCourse(university_id=…, title, level, category, duration, tuition_fee="", intake="", tuition_amount=Decimal(...) | None,
    tuition_currency, intakes, campus, fee_text, intake_text, scholarship_ids=[str(id) …], active=True)` then
    `derive_texts(course, {"tuition_amount", "tuition_currency", "intakes"})` (check its exact `changed` parameter type).
  - Audit: `AuditLog(user_id=None, action="university.direct_tieup_load", entity_type="university", entity_id=str(uni.id),
    metadata_json={"created": bool, "fields": [...], "courses_created": n})` per university touched.
  - `commit=True` → `await db.commit()`; else `await db.rollback()`.
  - CLI: `asyncio.run(main())` using the same session factory as `app/seed.py` (copy its engine/session setup); prints the counts as JSON.
- [ ] **Step 4: Run** `tests/test_dtu_001_load.py` → PASS. Then a dry run against the dev DB is the owner's (Task 10).
- [ ] **Step 5: Commit** `feat(dtu-001): idempotent Direct Tie-ups loader`.

---

### Task 8: Web — catalogue logo, detail fields, master form, agent commission card

**Files:**
- Create: `apps/web/components/UniversityLogo.tsx`, `apps/web/components/AgentCommissionCard.tsx`, `apps/web/lib/agentCommission.ts`
- Modify: `apps/web/lib/types.ts` (`University`), `apps/web/lib/universities.ts` (`UniversityRow`, `University`), `apps/web/lib/courseMaster.ts`
  (`Course`), `apps/web/lib/universityView.ts` (`ViewProfile`, `ViewCourse`)
- Modify: `apps/web/components/UniversityCatalogue.tsx`, `apps/web/app/overseas/universities/[slug]/page.tsx`,
  `apps/web/app/partnership/universities/[id]/page.tsx`, `apps/web/components/UniversityForm.tsx`, `apps/web/components/UniversityView.tsx`,
  the course list component used by `UniversityCourses` (show campus / fee_text / intake_text)
- Test: `apps/web/tests/components/UniversityLogo.test.tsx`, `apps/web/tests/components/AgentCommissionCard.test.tsx`

**Interfaces:**
- Produces: `<UniversityLogo name logoUrl size? />`; `type AgentCommission = {percent: string|null; amount: string|null; currency: string|null; note: string|null}`;
  `formatAgentCommission(c: AgentCommission | null | undefined): string` ("16.00%" / "GBP 4,000.00" / "—");
  `<AgentCommissionCard universityId value canEdit />` (PUT then `router.refresh()`).

- [ ] **Step 1: Failing tests**

```tsx
// apps/web/tests/components/UniversityLogo.test.tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import UniversityLogo from "@/components/UniversityLogo";

afterEach(cleanup);
describe("UniversityLogo", () => {
  it("renders the logo image with the university name as alt text", () => {
    render(<UniversityLogo name="University of South Wales" logoUrl="/universities/logos/university-of-south-wales.png" />);
    expect(screen.getByRole("img", { name: "University of South Wales logo" }).getAttribute("src")).toContain("university-of-south-wales.png");
  });
  it("falls back to a monogram without a logo", () => {
    render(<UniversityLogo name="University of South Wales" logoUrl={null} />);
    expect(screen.getByLabelText("University of South Wales").textContent).toBe("US");
  });
});
```

```tsx
// apps/web/tests/components/AgentCommissionCard.test.tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AgentCommissionCard from "@/components/AgentCommissionCard";
import { formatAgentCommission } from "@/lib/agentCommission";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("agent commission", () => {
  it("formats percent, fixed and empty", () => {
    expect(formatAgentCommission({ percent: "16.00", amount: null, currency: null, note: null })).toBe("16.00%");
    expect(formatAgentCommission({ percent: null, amount: "4000.00", currency: "GBP", note: "4000GBP flat" })).toBe("GBP 4,000.00");
    expect(formatAgentCommission(null)).toBe("—");
  });
  it("read-only without canEdit", () => {
    render(<AgentCommissionCard universityId="u1" value={{ percent: "13.00", amount: null, currency: null, note: "0.13" }} canEdit={false} />);
    expect(screen.getByText("13.00%")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save agent commission" })).toBeNull();
  });
  it("saves a percent with PUT", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ university: {} })));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentCommissionCard universityId="u1" value={null} canEdit />);
    fireEvent.change(screen.getByLabelText("Percent"), { target: { value: "16" } });
    fireEvent.click(screen.getByRole("button", { name: "Save agent commission" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/partnership/universities/u1/agent-commission");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual({ percent: "16" });
  });
});
```

Check how other client components call the API (e.g. `CommissionTermForm.tsx`): if they use a helper (`clientApi`/`apiFetch`) that
adds CSRF headers or a base URL, use it and assert on that helper's call instead of raw `fetch`.

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**

```tsx
// apps/web/components/UniversityLogo.tsx
// dtu-001: the university's logo (from its official site), or a monogram tile when there is none.
export default function UniversityLogo({ name, logoUrl, size = 48 }: { name: string; logoUrl: string | null | undefined; size?: number }) {
  const box = { width: size, height: size, borderRadius: 8, flex: "none" } as const;
  if (logoUrl) return <img src={logoUrl} alt={`${name} logo`} width={size} height={size} loading="lazy" style={{ ...box, objectFit: "contain", background: "#fff" }} />;
  const initials = name.split(/\s+/).filter((w) => /^[A-Z]/.test(w)).slice(0, 2).map((w) => w[0]).join("") || name.slice(0, 1).toUpperCase();
  return <span aria-label={name} role="img" style={{ ...box, display: "inline-grid", placeItems: "center", fontWeight: 700, background: "var(--surface-2, #eef1f6)" }}>{initials}</span>;
}
```

(With `role="img"` + `aria-label`, `getByLabelText(name)` finds the monogram; "University of South Wales" → "US".)

```ts
// apps/web/lib/agentCommission.ts
// dtu-001 (DEC-SCOPE-209): what EduSphere pays an agent Master per university. Sent only to super_admin, overseas_admin and Masters.
export type AgentCommission = { percent: string | null; amount: string | null; currency: string | null; note: string | null };
export const AGENT_COMMISSION_EDITORS = new Set(["super_admin", "overseas_admin"]);
export function formatAgentCommission(c: AgentCommission | null | undefined): string {
  if (!c) return "—";
  if (c.percent) return `${c.percent}%`;
  return `${c.currency} ${Number(c.amount).toLocaleString("en-GB", { minimumFractionDigits: 2 })}`;
}
```

`AgentCommissionCard.tsx` ("use client"): a `section.card` titled "Agent commission" showing `formatAgentCommission(value)` and the
note; when `canEdit`, a small form: radio "Percent" / "Fixed amount", inputs labelled "Percent", "Amount", select "Currency"
(INR USD GBP EUR CAD AUD NZD AED), "Note", buttons "Save agent commission" and "Clear"; body `{percent}` or `{amount, currency}` plus
`note` when non-empty; Clear sends `null`; on 2xx `router.refresh()`; on 422 show the API `detail` text in a `role="alert"`.

Wiring:
- Types: add `logo_url?: string | null; campuses?: string[]; fee_structure?: string | null` to `lib/types.ts` `University`;
  `logo_url: string | null` to `UniversityRow`; `campuses: string[]; fee_structure: string | null; agent_commission?: AgentCommission | null`
  to master `University`; `campus/fee_text/intake_text: string | null` to `Course` and `ViewCourse`; `logo_url/campuses/fee_structure` to `ViewProfile`.
- `UniversityCatalogue.tsx`: put `<UniversityLogo name={university.name} logoUrl={university.logo_url} />` before the city badge.
- Public detail page: logo in the hero; under "Admission information" add "Campuses" (when non-empty) and "Fee structure"
  (`white-space: pre-line`); in each course card show `c.campus` and prefer `c.fee_text ?? c.tuition_fee`, `c.intake_text ?? c.intake`.
- Partnership detail page: logo next to the title; add Facts rows "Campuses", "Fee structure"; render
  `{"agent_commission" in university && <AgentCommissionCard universityId={university.id} value={university.agent_commission ?? null} canEdit={AGENT_COMMISSION_EDITORS.has(user.role)} />}`
  near the commission ledger card.
- `UniversityForm.tsx`: inputs "Logo URL" (`logo_url`), "Campuses" (one per line → array), "Fee structure" (textarea), included in the
  POST/PATCH body only when changed (follow how `popular_programs` is handled).
- `UniversityView.tsx` (counselor 360): logo in the profile header; course rows show campus / fee_text / intake_text.
- Course table/cards in the partnership course list: add the three texts (read-only columns) and inputs in the course form.
- [ ] **Step 4: Run** vitest for the two new tests + existing `UniversityCatalogue*`, `UniversityDetailPage*`, `UniversityForm*`,
  `UniversityView*`, `UniversityCourses*` tests; `tsc --noEmit`; eslint on changed files → PASS.
- [ ] **Step 5: Commit** `feat(dtu-001): logos, campuses, fee block, course texts and the agent commission card in the web app`.

---

### Task 9: Web — agent Partner Universities section

**Files:**
- Create: `apps/web/components/AgentPartnerUniversitiesPanel.tsx`, `apps/web/lib/agentPartnerUniversities.ts`
- Modify: `apps/web/lib/navigation.ts` (agent list ~line 272, `AGENT_NAV_LABELS`), `apps/web/components/PortalPage.tsx` (lines 6–33)
- Test: `apps/web/tests/components/AgentPartnerUniversitiesPanel.test.tsx`

**Interfaces:**
- Consumes: Task 4 JSON; `UniversityLogo`, `formatAgentCommission`.
- Produces: section `partner-universities` at `/overseas/agent/partner-universities` (detail via `?id=<uuid>` in the same panel).

- [ ] **Step 1: Failing test** (pattern: `tests/components/AgentUniversitiesPanel.test.tsx`)

```tsx
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AgentPartnerUniversitiesPanel from "@/components/AgentPartnerUniversitiesPanel";

const item = { id: "u1", slug: "usw", name: "University of South Wales", logo_url: null, city: "Cardiff Campus", campuses: ["Cardiff Campus"], country: { id: "c1", name: "United Kingdom", iso2: "GB" }, course_count: 33 };
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("AgentPartnerUniversitiesPanel", () => {
  it("shows the agent commission column for a Master", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ items: [{ ...item, agent_commission: { percent: "13.00", amount: null, currency: null, note: "0.13" } }], total: 1 }))));
    render(<AgentPartnerUniversitiesPanel memberRole="master" />);
    await waitFor(() => expect(screen.getByText("University of South Wales")).toBeTruthy());
    expect(screen.getByRole("columnheader", { name: "Agent commission" })).toBeTruthy();
    expect(screen.getByText("13.00%")).toBeTruthy();
  });
  it("has no commission column for staff", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ items: [item], total: 1 }))));
    render(<AgentPartnerUniversitiesPanel memberRole="staff" />);
    await waitFor(() => expect(screen.getByText("University of South Wales")).toBeTruthy());
    expect(screen.queryByRole("columnheader", { name: "Agent commission" })).toBeNull();
  });
});
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - `lib/agentPartnerUniversities.ts`: `PARTNERS_URL = "/api/v1/workflows/overseas/agent/crm/partner-universities"`; types
    `PartnerUniversity`, `PartnerUniversityDetail`, `PartnerPage` matching Task 4.
  - Panel ("use client"): search box (debounced 300 ms, `q`), table columns Logo · University · Country · Campuses · Courses ·
    (Master only) "Agent commission"; Prev/Next paging (`limit=20`); clicking a name sets `?id=` and shows the detail (logo, website
    link `rel="noopener noreferrer"`, overview, campuses, fee structure, deadlines, scholarships, courses table: title, level, campus,
    fee (`fee_text ?? tuition_fee`), intake (`intake_text ?? intake`), and the Master's agent commission). Column visibility is decided by
    `memberRole === "master"` **and** the key being present (the server is the gate; the UI only hides an empty column).
    Loading, empty ("No partner universities found") and error (`role="alert"`) states.
  - `navigation.ts`: insert `"partner-universities"` after `"universities"` in the agent list; `AGENT_NAV_LABELS["partner-universities"] = "Partner Universities"`.
    Staff keep it (not in `STAFF_HIDDEN`).
  - `PortalPage.tsx`: `const agentPartners=key==="overseas/agent"&&section==="partner-universities";` — add it to the 404-tolerant
    list next to `agentTasks` and render `agentPartners?<AgentPartnerUniversitiesPanel memberRole={user.agent_member_role}/>` in the
    `main` chain before the `!data?null` branch. Check whether `/api/v1/portal/overseas/agent/partner-universities` 404s; if the
    portal API rejects unknown sections with 404 the tolerance covers it, otherwise add the section key to the portal section list
    in `app/services/portal.py` returning the agent's base payload.
- [ ] **Step 4: Run** the new test + `AgentUniversitiesPanel.test.tsx` + navigation tests (`grep -l agentNavFor tests/`) + tsc + eslint → PASS.
- [ ] **Step 5: Commit** `feat(dtu-001): agent portal Partner Universities section`.

---

### Task 10: Docs, e2e, verification

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append `### DEC-SCOPE-209 — Direct Tie-ups load + agent commission (`dtu-001`)`
  after DEC-SCOPE-208 at ~line 8153, same structure: question/answer table DT1–DT14, Consequences, New Feature ID authorized, Status)
- Modify: `docs/architecture/RBAC_MATRIX.md` (`### 2.134 Agent commission & Partner Universities *(added 2026-10-13 — DEC-SCOPE-209, dtu-001)*`:
  rows for `PUT …/agent-commission`, master detail `agent_commission` key, the two agent endpoints, per role)
- Modify: `docs/architecture/API_CONTRACT.md` (`## 12DW. Direct Tie-ups & agent commission (dtu-001) — addendum, 2026-10-13`)
- Modify: the delivery backlog/status file used for one-off features (find where ENH-/AGN- items record status; add `dtu-001`)
- Create: `apps/web/e2e/dtu-001-partner-universities.spec.ts` (Master sees "Agent commission", staff do not) — follow the newest
  agent e2e spec's login helpers.

- [ ] **Step 1:** `git fetch origin main`; confirm 0157 / 209 / 2.134 / 12DW are still free (else stop and ask).
- [ ] **Step 2:** Write the docs above.
- [ ] **Step 3:** Lite backend run: `tests/test_dtu_001_*.py tests/test_upc_033_*.py tests/test_upc_003*.py tests/test_upc_016*.py tests/test_upc_017*.py tests/test_upc_030*.py tests/test_agn_007*.py` plus any public-university test files → all PASS; paste the summary line.
- [ ] **Step 4:** Web: full vitest for touched components, `tsc --noEmit`, eslint; Playwright e2e for the new spec (needs the owner's stack;
  ask the owner to start it and run the loader first: `docker compose exec api alembic upgrade head` then
  `docker compose exec api python -m app.direct_tieups.load --dry-run` then without `--dry-run`).
- [ ] **Step 5: Commit** `docs(dtu-001): DEC-SCOPE-209, RBAC 2.134, API 12DW, backlog status; e2e`.
- [ ] **Step 6:** Report: lite files run (full suite not run, by the owner's standing choice), loader counts, logos found vs monograms,
  and the push command `git push -u origin feature/direct-tieups` for the owner.
