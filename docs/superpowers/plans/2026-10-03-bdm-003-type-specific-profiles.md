# bdm-003 Type-specific Organization Profiles Implementation Plan

**ID note (merge of `main` @ `65a8ece`, 2026-10-03):** written as `DEC-SCOPE-063` and migration `0068_bdm_org_profiles`; bdm-010 (`DEC-SCOPE-063`, `0068_bdm_trips`, PR #53) reached `main` first, so bdm-003 is now **`DEC-SCOPE-064`** and **`0069_bdm_org_profiles`** (after `0068_bdm_trips`). Mentions of `063` / `0068_bdm_org_profiles` below mean this decision / migration.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agent, School and College/University organizations get their own typed profile fields (plus a common Address) on `bdm_organizations`, exposed as a nested `profile` object validated per `org_type`, with the form, detail page and list filters to match.

**Architecture:** Approach A of the spec: twelve nullable columns + CHECKs (migration `0068`), one `BdmOrgProfileIn` schema (`extra="forbid"`), and one service check (`check_profile` / `check_type_change`) run after the row lock in create and PATCH. The web form gets a profile-fields module that also owns the profile's form logic; the detail page gets a small profile view.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, PostgreSQL; Next.js (App Router), React, TypeScript, vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-03-bdm-003-type-specific-profiles-design.md` (Revision 2). Read it with this plan.

## Global Constraints

- Branch `feature/bdm-003-type-specific-profile-fields`; migration `0068_bdm_org_profiles` after `0067_audit_entity_index`; decision `DEC-SCOPE-063`. Recheck `origin/main` before Task 1 and before merge; renumber if taken.
- Additive only: no existing column, route, status code or response field changes; no data written by the migration.
- No new dependency (backend or web).
- Profile key presence rule: a key outside the effective type's group is 422 even when its value is `null`.
- Live agent figures (`commission`, `students`, `applications`, `enrollments`, `master_login`) are never accepted anywhere.
- Enums exactly: Board `CBSE, ICSE, State, IB, Other`; School type `private, government, aided, international, other`; College type `engineering, arts_science, management, medical, polytechnic, other`; Source `referral, website, event, cold_call, walk_in, other`; grades `-2…12` (−2 Nursery, −1 LKG, 0 UKG); staff 0–100 000.
- Multi-line rule (P14) for `address` (500), `courses` (1000), `courses_interested` (1000): `\r\n`/`\r` → `\n`, `\n` allowed, every other control character rejected.
- Logs and audit carry ids and field names only — never address, country, territory, affiliation or courses text.
- Tests run in docker (the worktree has no node_modules / venv). Lite sets only; the owner runs the full suites.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

**Commands** (run from the worktree root `C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/bdm-003`; project `bdm003` keeps containers apart from other worktrees):

```bash
WT="C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/bdm-003"
# API tests: API_TEST "<pytest args>"
API_TEST() { docker compose -p bdm003 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm -v "$WT/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q $1"; }
# Web tests: WEB_TEST "<command>"
WEB_TEST() { MSYS_NO_PATHCONV=1 docker compose -p bdm003 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps -v "$WT/apps/web:/app" -v /app/node_modules web-test sh -c "$1"; }
```

## Review Focus

1. **Organizations created before bdm-003** (all profile columns NULL) — editing only their name must not trip any profile check, and the detail shows "No college details yet." → Task 6 test `test_pre_bdm003_organization_edits_cleanly`; Task 11 test "shows the empty line".
2. **A non-numeric value in Number of staff** (`"abc"`, `"6.5"`) — `Number("abc")` is `NaN`, which `JSON.stringify` turns into `null` and would silently clear the field; the value must be sent as typed so the server's plain 422 names the field → Task 10 test "sends a non-whole number as typed".
3. **Clearing a select back to "Choose…" on edit** must send `null` (clears), never `""` → Task 10 test "clears with null".
4. **Changing the type and changing it back before saving** must not block the save → Task 11 test "type changed and changed back is not blocked".
5. **Text pasted with Windows line endings** in Address / Courses → stored with `\n`, length counted after normalising → Task 3 test `test_multiline_rule`.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `apps/api/app/models.py` (modify, bdm block ~L959–1000) | Enum tuples, group map, 12 columns, 8 CHECKs | 1 |
| `apps/api/alembic/versions/0068_bdm_org_profiles.py` (create) | Additive DDL, guarded; downgrade refusal | 2 |
| `apps/api/tests/test_bdm_003_migration.py` (create) | Chain, model = migration, CHECKs, round trip | 1, 2 |
| `apps/api/tests/test_bdm_002_migration.py` (modify L42–60) | Exact-column assert → subset | 1 |
| `apps/api/app/schemas.py` (modify, bdm-002 block ~L3137–3367) | Multi-line rule, profile in/out models, address | 3 |
| `apps/api/tests/test_bdm_003_schemas.py` (create) | Schema unit tests | 3 |
| `apps/api/app/services/bdm_organizations.py` (modify) | `check_profile`, `check_type_change`, `profile_out`, output | 4 |
| `apps/api/app/api/bdm_organizations.py` (modify) | Create, PATCH, list filters | 5, 6, 7 |
| `apps/api/tests/bdm003_helpers.py` (create) | Builders for type BDMs and profiles | 4 |
| `apps/api/tests/test_bdm_003_profiles.py` (create) | API behaviour, authz, filters, logs, races | 4–8 |
| `apps/web/lib/bdmOrganizations.ts` (modify) | Enums, labels, group map, types, helpers | 9 |
| `apps/web/components/BdmOrganizationProfileFields.tsx` (create) | Profile inputs + profile form logic | 10 |
| `apps/web/components/BdmOrganizationProfileDetails.tsx` (create) | Profile view + shared `DetailList` | 12 |
| `apps/web/components/BdmOrganizationFields.tsx` (modify) | Address, Type help text | 11 |
| `apps/web/components/BdmOrganizationForm.tsx` (modify) | Wire profile state, errors, type-change block | 11 |
| `apps/web/components/BdmOrganizationDetail.tsx` (modify) | Address row, profile view, `DetailList` | 12 |
| `apps/web/components/BdmContactFields.tsx`, `BdmOrganizationContacts.tsx` (modify) | Suggested roles first | 13 |
| `apps/web/components/BdmOrganizationsPanel.tsx` (modify) | Board / Affiliation / Territory filters | 14 |
| `apps/web/tests/...` | Unit tests per component | 9–14 |
| `apps/web/tests/e2e/bdm-003-type-profiles.spec.ts` (create) | Journey, keyboard-only, 320 px | 15 |
| `docs/...` | DEC-SCOPE-063, backlog, data model, RTM | 16 |

---

### Task 0: Preflight

- [ ] **Step 1: Recheck `main` for numbers**

```bash
git fetch origin -q && git ls-tree --name-only origin/main apps/api/alembic/versions/ | sort | tail -2
git show origin/main:docs/decisions/PRODUCT_DECISION_REGISTER.md | grep -o "DEC-SCOPE-06[0-9]" | sort -u | tail -1
```
Expected: last migration `0067_audit_entity_index.py`; last decision `DEC-SCOPE-062`. If either moved, merge `origin/main` first and renumber `0068`/`063` everywhere in this plan.

- [ ] **Step 2: Baseline the bdm-002 lite set (green before any change)**

Run: `API_TEST "tests/test_bdm_002_schemas.py tests/test_bdm_002_organizations.py tests/test_bdm_002_migration.py"`
Expected: all pass. If not, stop and report — do not build on a red baseline.

---

### Task 1: Model — columns, enums, CHECKs

**Files:**
- Modify: `apps/api/app/models.py` (after `BDM_CONTACT_ROLES` L960; inside `BdmOrganization` L969–999)
- Modify: `apps/api/tests/test_bdm_002_migration.py:42-60`
- Create: `apps/api/tests/test_bdm_003_migration.py`

**Interfaces:**
- Produces: `BDM_ORG_SOURCES`, `BDM_SCHOOL_BOARDS`, `BDM_SCHOOL_TYPES`, `BDM_COLLEGE_TYPES` (tuples of str); `BDM_GRADE_MIN = -2`, `BDM_GRADE_MAX = 12`, `BDM_STAFF_MAX = 100_000`; `BDM_PROFILE_GROUP: dict[str, str]` (`agent→agent, school→school, college→college, university→college`); `BDM_PROFILE_FIELDS: dict[str, tuple[str, ...]]`; `BDM_PROFILE_CHECKS: dict[str, str]` (CHECK name → SQL); `BdmOrganization` columns `address, country, territory, source, staff_count, board, school_type, grade_from, grade_to, affiliation, college_type, courses`.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/test_bdm_003_migration.py`:

```python
"""bdm-003 -- migration 0068_bdm_org_profiles (spec §4). Round trip and the downgrade refusal run in a throwaway database (the
bdm-002 pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
BASE = "0067_audit_entity_index"
HEAD = "0068_bdm_org_profiles"
NEW_COLUMNS = {"address", "country", "territory", "source", "staff_count", "board", "school_type", "grade_from", "grade_to", "affiliation", "college_type", "courses"}


def _migration():
    spec = importlib.util.spec_from_file_location("_bdm_003_migration_0068", VERSIONS / f"{HEAD}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _model_checks() -> dict[str, str]:
    from app.models import BdmOrganization

    return {c.name: str(c.sqltext) for c in BdmOrganization.__table__.constraints if isinstance(c, CheckConstraint)}


def test_model_has_the_profile_columns_and_checks():
    from app.models import BDM_PROFILE_CHECKS, BdmOrganization

    assert NEW_COLUMNS <= {c.name for c in BdmOrganization.__table__.columns}
    assert all(BdmOrganization.__table__.c[name].nullable for name in NEW_COLUMNS)
    assert set(BDM_PROFILE_CHECKS) == {
        "ck_bdm_organizations_source", "ck_bdm_organizations_staff_count", "ck_bdm_organizations_board", "ck_bdm_organizations_school_type",
        "ck_bdm_organizations_grades", "ck_bdm_organizations_college_type", "ck_bdm_organizations_agent_profile",
        "ck_bdm_organizations_school_profile", "ck_bdm_organizations_college_profile",
    }
    assert BDM_PROFILE_CHECKS.items() <= _model_checks().items()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `API_TEST "tests/test_bdm_003_migration.py::test_model_has_the_profile_columns_and_checks"`
Expected: FAIL — `ImportError: cannot import name 'BDM_PROFILE_CHECKS'`.

- [ ] **Step 3: Implement** — in `apps/api/app/models.py`, after `BDM_CONTACT_ROLES = (...)` (L960) add:

```python
# bdm-003 (DEC-SCOPE-063, spec §4): the type-specific profile. `board` keeps ENH-009's exact values so bdm-018 can copy it onto
# `schools.board`; the other enums are lower snake case like `org_type`. Grades: -2 Nursery, -1 LKG, 0 UKG, then 1-12.
BDM_ORG_SOURCES = ("referral", "website", "event", "cold_call", "walk_in", "other")
BDM_SCHOOL_BOARDS = ("CBSE", "ICSE", "State", "IB", "Other")
BDM_SCHOOL_TYPES = ("private", "government", "aided", "international", "other")
BDM_COLLEGE_TYPES = ("engineering", "arts_science", "management", "medical", "polytechnic", "other")
BDM_GRADE_MIN, BDM_GRADE_MAX = -2, 12
BDM_STAFF_MAX = 100_000
BDM_PROFILE_GROUP = {"agent": "agent", "school": "school", "college": "college", "university": "college"}
BDM_PROFILE_FIELDS = {
    "agent": ("country", "territory", "source", "staff_count"),
    "school": ("board", "school_type", "grade_from", "grade_to"),
    "college": ("affiliation", "college_type", "courses"),
}
```

After `def _in_list(...)` (L965–966) add:

```python
def _group_only(group: str) -> str:
    """A group's columns stay NULL unless org_type belongs to the group (spec §4.2) -- the backstop under check_profile."""
    types = tuple(t for t, g in BDM_PROFILE_GROUP.items() if g == group)
    return f"{_in_list('org_type', types)} OR ({' AND '.join(f'{c} IS NULL' for c in BDM_PROFILE_FIELDS[group])})"


def _grade(column: str) -> str:
    return f"{column} IS NULL OR {column} BETWEEN {BDM_GRADE_MIN} AND {BDM_GRADE_MAX}"


BDM_PROFILE_CHECKS = {  # migration 0068 repeats these strings; test_bdm_003_migration asserts they stay identical
    "ck_bdm_organizations_source": f"source IS NULL OR {_in_list('source', BDM_ORG_SOURCES)}",
    "ck_bdm_organizations_staff_count": f"staff_count IS NULL OR staff_count BETWEEN 0 AND {BDM_STAFF_MAX}",
    "ck_bdm_organizations_board": f"board IS NULL OR {_in_list('board', BDM_SCHOOL_BOARDS)}",
    "ck_bdm_organizations_school_type": f"school_type IS NULL OR {_in_list('school_type', BDM_SCHOOL_TYPES)}",
    "ck_bdm_organizations_grades": f"({_grade('grade_from')}) AND ({_grade('grade_to')}) AND (grade_from IS NULL OR grade_to IS NULL OR grade_from <= grade_to)",
    "ck_bdm_organizations_college_type": f"college_type IS NULL OR {_in_list('college_type', BDM_COLLEGE_TYPES)}",
    "ck_bdm_organizations_agent_profile": _group_only("agent"),
    "ck_bdm_organizations_school_profile": _group_only("school"),
    "ck_bdm_organizations_college_profile": _group_only("college"),
}
```

In `BdmOrganization.__table_args__`, after the `ck_bdm_organizations_student_count` line, add:

```python
        *(CheckConstraint(sql, name=name) for name, sql in BDM_PROFILE_CHECKS.items()),
```

Extend the class docstring with: `bdm-003 (DEC-SCOPE-063): a common address plus one typed profile group per org_type (BDM_PROFILE_FIELDS); a group's columns are NULL for every other type.` After `student_count` add:

```python
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    territory: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    staff_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    board: Mapped[str | None] = mapped_column(String(10), nullable=True)
    school_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    grade_from: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    grade_to: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    affiliation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    college_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    courses: Mapped[str | None] = mapped_column(String(1000), nullable=True)
```

(`SmallInteger` is already imported — `AgentStudent.graduation_year` uses it.)

- [ ] **Step 4: Change the bdm-002 exact-column assertion to a subset** — in `apps/api/tests/test_bdm_002_migration.py::test_models_match_the_migration`, change `assert {c.name for c in org.columns} == {` to `assert {c.name for c in org.columns} >= {` and add above it the comment `# bdm-003 adds profile columns (test_bdm_003_migration); bdm-002's own columns must all still be here.`

- [ ] **Step 5: Run to verify it passes**

Run: `API_TEST "tests/test_bdm_003_migration.py::test_model_has_the_profile_columns_and_checks tests/test_bdm_002_migration.py::test_models_match_the_migration"`
Expected: 2 passed. (The shared DB is not yet migrated; these tests only read metadata.)

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/models.py apps/api/tests/test_bdm_003_migration.py apps/api/tests/test_bdm_002_migration.py
git commit -m "feat(bdm-003): profile columns, enums and CHECKs on BdmOrganization"
```

---

### Task 2: Migration `0068_bdm_org_profiles`

**Files:**
- Create: `apps/api/alembic/versions/0068_bdm_org_profiles.py`
- Modify: `apps/api/tests/test_bdm_003_migration.py`

**Interfaces:**
- Consumes: `BDM_PROFILE_CHECKS` (Task 1) — only in the test, to assert the migration's literal `CHECKS` match.
- Produces: revision `0068_bdm_org_profiles`; module constants `COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...]`, `CHECKS: dict[str, str]`.

- [ ] **Step 1: Write the failing tests** — append to `test_bdm_003_migration.py`:

```python
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


def test_chains_after_0067_and_is_the_single_head():
    migration = _migration()
    assert (migration.revision, migration.down_revision) == (HEAD, BASE)
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_migration_checks_equal_the_model():
    from app.models import BDM_PROFILE_CHECKS, BdmOrganization

    migration = _migration()
    assert migration.CHECKS == BDM_PROFILE_CHECKS
    assert {name for name, _ in migration.COLUMNS} == NEW_COLUMNS
    for name, type_ in migration.COLUMNS:  # same SQL type and length as the model
        assert str(type_) == str(BdmOrganization.__table__.c[name].type), name


@pytest.mark.asyncio
async def test_columns_and_checks_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    columns = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_columns("bdm_organizations")})
    checks = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_check_constraints("bdm_organizations")})
    assert NEW_COLUMNS <= columns
    assert set(_migration().CHECKS) <= checks


@pytest.fixture
def isolated_db():
    """A fresh database at 0067 with one bdm user and one organization (no profile)."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"bdm003_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'it', true, true, 'en-GB', '{}')",
            {"id": user_id, "email": f"bdm-{name}@example.local"},
        )
        yield {"cfg": cfg, "url": url, "user": user_id, "org": org_id}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


INSERT = (
    "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, created_by_user_id{extra_cols}) "
    "VALUES (:id, :code, :org_type, 'school', 'A', 'a', 'K', 'k', :u, :u{extra_vals})"
)


def _insert(db, org_type: str, **values):
    sql = INSERT.format(extra_cols="".join(f", {k}" for k in values), extra_vals="".join(f", :{k}" for k in values))
    _sql(db["url"], sql, {"id": uuid.uuid4(), "code": f"ORG-{uuid.uuid4().hex[:8]}", "org_type": org_type, "u": db["user"], **values})


def test_round_trip_runs_the_real_ddl_keeps_rows_and_enforces_every_check(isolated_db):
    """0001 builds BASE from the current models (columns already there), so go up, down to 0067 (the migration drops them), and up again:
    the CHECKs below are 0068's own DDL, not create_all's."""
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    cols = {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'bdm_organizations'")}
    assert not (NEW_COLUMNS & cols)
    _sql(url, INSERT.format(extra_cols="", extra_vals=""), {"id": isolated_db["org"], "code": "ORG-KEEP", "org_type": "college", "u": isolated_db["user"]})
    before = _sql(url, "SELECT id, code, org_type, name FROM bdm_organizations ORDER BY id")
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT id, code, org_type, name FROM bdm_organizations ORDER BY id") == before  # no row read or written
    bad = [
        ("school", {"board": "XX"}, "ck_bdm_organizations_board"),
        ("school", {"school_type": "charter"}, "ck_bdm_organizations_school_type"),
        ("school", {"grade_from": -3}, "ck_bdm_organizations_grades"),
        ("school", {"grade_to": 13}, "ck_bdm_organizations_grades"),
        ("school", {"grade_from": 8, "grade_to": 6}, "ck_bdm_organizations_grades"),
        ("agent", {"source": "tv"}, "ck_bdm_organizations_source"),
        ("agent", {"staff_count": -1}, "ck_bdm_organizations_staff_count"),
        ("agent", {"staff_count": 100_001}, "ck_bdm_organizations_staff_count"),
        ("college", {"college_type": "law"}, "ck_bdm_organizations_college_type"),
        ("college", {"board": "CBSE"}, "ck_bdm_organizations_school_profile"),
        ("school", {"country": "India"}, "ck_bdm_organizations_agent_profile"),
        ("agent", {"courses": "MBA"}, "ck_bdm_organizations_college_profile"),
    ]
    for org_type, values, check in bad:
        with pytest.raises(Exception, match=check):
            _insert(isolated_db, org_type, **values)
    _insert(isolated_db, "university", affiliation="VTU", college_type="engineering", courses="B.Tech CSE\nMBA")
    _insert(isolated_db, "school", board="CBSE", grade_from=-2, grade_to=12, address="1 Main Rd")


def test_downgrade_refuses_while_profile_values_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _insert(isolated_db, "agent", country="India")
    with pytest.raises(Exception, match="profile values exist"):
        command.downgrade(cfg, BASE)
    _sql(url, "UPDATE bdm_organizations SET country = NULL")
    command.downgrade(cfg, BASE)  # nothing entered any more: allowed
```

- [ ] **Step 2: Run to verify they fail**

Run: `API_TEST "tests/test_bdm_003_migration.py"`
Expected: FAIL — `alembic upgrade head` succeeds (no 0068 yet) but `test_chains_after_0067…` fails with `FileNotFoundError … 0068_bdm_org_profiles.py`; the shared-database test fails on missing columns.

- [ ] **Step 3: Create `apps/api/alembic/versions/0068_bdm_org_profiles.py`**

```python
"""bdm-003 -- type-specific organization profiles: twelve nullable columns and nine CHECKs on bdm_organizations.

Revision ID: 0068_bdm_org_profiles
Revises: 0067_audit_entity_index

docs/superpowers/specs/2026-10-03-bdm-003-type-specific-profiles-design.md §4 (DEC-SCOPE-063). No row is read or written by upgrade():
every existing row has NULL in every new column, which satisfies every CHECK. 0001 builds a fresh database from the current models (which
already carry the columns and CHECKs), so each column and CHECK is added only when missing. downgrade() refuses while any profile value
exists: entered data is never dropped silently. CHECKS must equal app.models.BDM_PROFILE_CHECKS (test_bdm_003_migration).
"""

import sqlalchemy as sa

from alembic import op

revision = "0068_bdm_org_profiles"
down_revision = "0067_audit_entity_index"
branch_labels = None
depends_on = None

TABLE = "bdm_organizations"
COLUMNS = (
    ("address", sa.String(500)),
    ("country", sa.String(120)),
    ("territory", sa.String(120)),
    ("source", sa.String(20)),
    ("staff_count", sa.Integer()),
    ("board", sa.String(10)),
    ("school_type", sa.String(20)),
    ("grade_from", sa.SmallInteger()),
    ("grade_to", sa.SmallInteger()),
    ("affiliation", sa.String(200)),
    ("college_type", sa.String(20)),
    ("courses", sa.String(1000)),
)
CHECKS = {
    "ck_bdm_organizations_source": "source IS NULL OR source IN ('referral', 'website', 'event', 'cold_call', 'walk_in', 'other')",
    "ck_bdm_organizations_staff_count": "staff_count IS NULL OR staff_count BETWEEN 0 AND 100000",
    "ck_bdm_organizations_board": "board IS NULL OR board IN ('CBSE', 'ICSE', 'State', 'IB', 'Other')",
    "ck_bdm_organizations_school_type": "school_type IS NULL OR school_type IN ('private', 'government', 'aided', 'international', 'other')",
    "ck_bdm_organizations_grades": "(grade_from IS NULL OR grade_from BETWEEN -2 AND 12) AND (grade_to IS NULL OR grade_to BETWEEN -2 AND 12) AND (grade_from IS NULL OR grade_to IS NULL OR grade_from <= grade_to)",
    "ck_bdm_organizations_college_type": "college_type IS NULL OR college_type IN ('engineering', 'arts_science', 'management', 'medical', 'polytechnic', 'other')",
    "ck_bdm_organizations_agent_profile": "org_type IN ('agent') OR (country IS NULL AND territory IS NULL AND source IS NULL AND staff_count IS NULL)",
    "ck_bdm_organizations_school_profile": "org_type IN ('school') OR (board IS NULL AND school_type IS NULL AND grade_from IS NULL AND grade_to IS NULL)",
    "ck_bdm_organizations_college_profile": "org_type IN ('college', 'university') OR (affiliation IS NULL AND college_type IS NULL AND courses IS NULL)",
}


def _present() -> tuple[set[str], set[str]]:
    if op.get_context().as_sql:  # offline SQL: emit everything
        return set(), set()
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(TABLE)}, {c["name"] for c in inspector.get_check_constraints(TABLE)}


def upgrade() -> None:
    columns, checks = _present()
    for name, type_ in COLUMNS:
        if name not in columns:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, sql)


def downgrade() -> None:
    if not op.get_context().as_sql:
        filled = " OR ".join(f"{name} IS NOT NULL" for name, _ in COLUMNS)
        if op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} WHERE {filled} LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0068_bdm_org_profiles: organization profile values exist. Clear them deliberately first.")
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    for name, _ in reversed(COLUMNS):
        op.drop_column(TABLE, name)
```

- [ ] **Step 4: Run to verify they pass**

Run: `API_TEST "tests/test_bdm_003_migration.py tests/test_bdm_002_migration.py tests/test_agn_015_migration.py tests/test_agn_017_migration.py"`
Expected: all pass. If `test_migration_checks_equal_the_model` fails on whitespace or quoting, fix the **migration literal** to equal the model string (the model is the source).

- [ ] **Step 5: Commit**

```bash
git add apps/api/alembic/versions/0068_bdm_org_profiles.py apps/api/tests/test_bdm_003_migration.py
git commit -m "feat(bdm-003): migration 0068_bdm_org_profiles (additive, guarded, refusing downgrade)"
```

---

### Task 3: Schemas — multi-line rule, profile in/out, address

**Files:**
- Modify: `apps/api/app/schemas.py` (bdm-002 block, L3137–3367)
- Create: `apps/api/tests/test_bdm_003_schemas.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–2 at runtime (Literals repeat the values; Task 3 test asserts they equal the model tuples).
- Produces: `BdmOrgProfileIn` (fields `country, territory, source, staff_count, board, school_type, grade_from, grade_to, affiliation, college_type, courses`); `BdmOrganizationCreate.address`, `.profile: BdmOrgProfileIn | None`; `BdmOrganizationUpdate.address`, `.profile: BdmOrgProfileIn` (default `None`, explicit null → 422); `BdmOrganizationOut.address: str | None`, `.profile: BdmOrgProfileOut | None` where `BdmOrgProfileOut` is discriminated on `kind`; `BDM_ORG_FIELDS` gains `"address"`; `BdmSchoolBoard` Literal (used by the list route, Task 7).

- [ ] **Step 1: Write the failing tests** — create `apps/api/tests/test_bdm_003_schemas.py`:

```python
"""bdm-003 -- profile schemas and the multi-line rule (spec §5.1, P14; AC3, AC4, AC10)."""

from typing import get_args

import pytest
from pydantic import ValidationError

from app import models
from app.schemas import (
    BdmCollegeType,
    BdmOrganizationCreate,
    BdmOrganizationOut,
    BdmOrganizationUpdate,
    BdmOrgProfileIn,
    BdmOrgSource,
    BdmSchoolBoard,
    BdmSchoolType,
)

CONTACT = {"name": "Dr Rao"}


def org(**overrides) -> dict:
    return {"org_type": "school", "name": "St Mary", "city": "Kochi", "contacts": [CONTACT], **overrides}


def messages(exc: ValidationError) -> str:
    return " | ".join(e["msg"] for e in exc.errors())


def test_literals_equal_the_model_tuples():
    assert get_args(BdmOrgSource) == models.BDM_ORG_SOURCES
    assert get_args(BdmSchoolBoard) == models.BDM_SCHOOL_BOARDS
    assert get_args(BdmSchoolType) == models.BDM_SCHOOL_TYPES
    assert get_args(BdmCollegeType) == models.BDM_COLLEGE_TYPES


def test_profile_accepts_every_field_and_keeps_unset_apart_from_null():
    full = {"country": "India", "territory": " South ", "source": "referral", "staff_count": 12, "board": "CBSE", "school_type": "private",
            "grade_from": -2, "grade_to": 12, "affiliation": "VTU", "college_type": "arts_science", "courses": "B.Tech CSE"}
    parsed = BdmOrgProfileIn.model_validate(full)
    assert parsed.territory == "South" and parsed.grade_from == -2
    assert BdmOrgProfileIn.model_validate({"board": None}).model_dump(exclude_unset=True) == {"board": None}
    assert BdmOrgProfileIn.model_validate({}).model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize("key", ["commission", "students", "applications", "enrollments", "master_login", "bdm_type", "nope"])
def test_live_metrics_and_unknown_keys_are_rejected_in_profile_and_at_top_level(key):
    with pytest.raises(ValidationError) as exc:
        BdmOrgProfileIn.model_validate({key: 1})
    assert exc.value.errors()[0]["type"] == "extra_forbidden"
    with pytest.raises(ValidationError) as exc:
        BdmOrganizationCreate.model_validate(org(**{key: 1}))
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"source": "tv"}, "Input should be"),
        ({"board": "cbse"}, "Input should be"),
        ({"school_type": "charter"}, "Input should be"),
        ({"college_type": "law"}, "Input should be"),
        ({"staff_count": -1}, "Number of staff must be a whole number from 0 to 100,000"),
        ({"staff_count": 100_001}, "Number of staff must be a whole number from 0 to 100,000"),
        ({"staff_count": "12"}, "Number of staff must be a whole number from 0 to 100,000"),
        ({"staff_count": 1.5}, "Number of staff must be a whole number from 0 to 100,000"),
        ({"grade_from": -3}, "Grade must be Nursery, LKG, UKG or 1 to 12"),
        ({"grade_to": 13}, "Grade must be Nursery, LKG, UKG or 1 to 12"),
        ({"country": "x" * 121}, "at most 120"),
        ({"affiliation": "x" * 201}, "at most 200"),
        ({"courses": "x" * 1001}, "at most 1000"),
        ({"territory": "Bad\x00"}, "Territory contains invalid characters"),
    ],
)
def test_profile_rejects_bad_values_readably(value, expected):
    with pytest.raises(ValidationError) as exc:
        BdmOrgProfileIn.model_validate(value)
    assert expected in messages(exc.value)


def test_multiline_rule():
    """P14 (Review Focus 5): \\r\\n and \\r become \\n before the length check; \\n is kept; every other control character is rejected."""
    parsed = BdmOrganizationCreate.model_validate(org(address="1 Main Rd\r\nKochi\rKerala", courses_interested="MBA\nBBA", profile={"courses": "A\r\nB"}))
    assert parsed.address == "1 Main Rd\nKochi\nKerala" and parsed.courses_interested == "MBA\nBBA" and parsed.profile.courses == "A\nB"
    assert BdmOrganizationCreate.model_validate(org(address="a\r\n" * 166 + "ab")).address  # 500 after normalising, 666 before
    for bad in ("tab\there", "esc\x1b", "nul\x00"):
        with pytest.raises(ValidationError, match="Address contains invalid characters"):
            BdmOrganizationCreate.model_validate(org(address=bad))
    with pytest.raises(ValidationError, match="Organization name contains invalid characters"):  # single-line fields keep the old rule
        BdmOrganizationCreate.model_validate(org(name="St\nMary"))
    with pytest.raises(ValidationError, match="at most 500"):
        BdmOrganizationCreate.model_validate(org(address="x" * 501))


def test_create_and_update_profile_and_address():
    created = BdmOrganizationCreate.model_validate(org(address="", profile={"board": "CBSE"}))
    assert created.address is None and created.profile.board == "CBSE"
    assert BdmOrganizationCreate.model_validate(org()).profile is None
    assert BdmOrganizationUpdate.model_validate({"profile": {"grade_to": 10}}).model_dump(exclude_unset=True) == {"profile": {"grade_to": 10}}
    with pytest.raises(ValidationError):
        BdmOrganizationUpdate.model_validate({"profile": None})


def test_output_profile_is_discriminated_on_kind():
    base = {
        "id": "00000000-0000-0000-0000-000000000001", "code": "ORG-000001", "name": "A", "org_type": "school", "bdm_type": "school", "city": "K",
        "state": None, "existing_partner": False, "assigned_bdm": {"id": "00000000-0000-0000-0000-000000000002", "full_name": "B", "active": True},
        "primary_contact": None, "archived": False, "last_meeting_at": None, "next_meeting_at": None,
        "permissions": {"can_edit": True, "can_archive": True, "can_restore": False, "can_reassign": False}, "phone": None, "email": None,
        "website": None, "courses_interested": None, "student_count": None, "contacts": [], "created_by_name": "B", "archived_at": None,
        "created_at": "2026-10-03T00:00:00Z", "updated_at": "2026-10-03T00:00:00Z", "address": None,
    }
    school = BdmOrganizationOut.model_validate({**base, "profile": {"kind": "school", "board": "CBSE", "school_type": None, "grade_from": 6, "grade_to": 12}})
    assert school.model_dump(mode="json")["profile"] == {"kind": "school", "board": "CBSE", "school_type": None, "grade_from": 6, "grade_to": 12}
    assert BdmOrganizationOut.model_validate({**base, "profile": None}).profile is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `API_TEST "tests/test_bdm_003_schemas.py"`
Expected: FAIL — `ImportError: cannot import name 'BdmCollegeType' from 'app.schemas'`.

- [ ] **Step 3: Implement in `apps/api/app/schemas.py`** (all inside the bdm-002 block):

(a) Labels and fields — extend `BDM_ORG_LABELS` with `"address": "Address", "country": "Country", "territory": "Territory", "affiliation": "University / affiliation", "courses": "Courses"`; change `BDM_ORG_FIELDS` to `("org_type", "name", "city", "state", "address", "phone", "email", "website", "existing_partner", "courses_interested", "student_count")`.

(b) After `_BDM_BARE_SITE = ...` add:

```python
_BDM_CONTROL_MULTILINE = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")  # P14: like _BDM_CONTROL, but a line break (\n) is allowed
```

(c) After `_bdm_org_text` add:

```python
def _bdm_org_multiline_text(value: str | None, info: ValidationInfo) -> str | None:
    """bdm-003 P14: multi-line fields (address, courses, courses_interested) keep line breaks; every other control character is refused."""
    if value is not None and _BDM_CONTROL_MULTILINE.search(value):
        raise ValueError(f"{BDM_ORG_LABELS.get(info.field_name, info.field_name)} contains invalid characters")
    return value or None


def _bdm_newlines(value):
    """Before the length check, so the limit counts the stored form (as _bdm_website_prefix)."""
    return value.replace("\r\n", "\n").replace("\r", "\n") if isinstance(value, str) else value
```

(d) After `_bdm_org_mandatory` add:

```python
def _bdm_org_multiline(max_length: int):
    inner = Annotated[Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)] | None, AfterValidator(_bdm_org_multiline_text)]
    return Annotated[inner, BeforeValidator(_bdm_newlines)]
```

(e) Replace `BdmOrgCourses = _bdm_org_optional(1000)` with:

```python
BdmOrgCourses = _bdm_org_multiline(1000)  # P14: courses_interested and the College `courses`
BdmOrgAddress = _bdm_org_multiline(500)
BdmOrgMedium = _bdm_org_optional(200)
```

(f) Replace `_bdm_student_count` / `BdmStudentCount` with one helper used three times:

```python
def _bdm_whole_number(message: str, low: int, high: int):
    """Browser QA-04: strict whole numbers; every way one fails reads as one plain sentence."""

    def wrap(value, handler):
        try:
            return handler(value)
        except ValidationError:
            raise ValueError(message) from None

    return Annotated[Annotated[StrictInt, Field(ge=low, le=high)] | None, WrapValidator(wrap)]


BdmStudentCount = _bdm_whole_number("Number of students must be a whole number from 0 to 1,000,000", 0, 1_000_000)
BdmStaffCount = _bdm_whole_number("Number of staff must be a whole number from 0 to 100,000", 0, 100_000)
BdmGrade = _bdm_whole_number("Grade must be Nursery, LKG, UKG or 1 to 12", -2, 12)
BdmOrgSource = Literal["referral", "website", "event", "cold_call", "walk_in", "other"]
BdmSchoolBoard = Literal["CBSE", "ICSE", "State", "IB", "Other"]  # ENH-009's SchoolBoard values exactly (bdm-018 copies them)
BdmSchoolType = Literal["private", "government", "aided", "international", "other"]
BdmCollegeType = Literal["engineering", "arts_science", "management", "medical", "polytechnic", "other"]
```

(g) Before `class BdmOrganizationCreate` add:

```python
class BdmOrgProfileIn(BaseModel):
    """bdm-003 (DEC-SCOPE-063, spec §5.1): the type-specific fields. Omitted = not sent; null = clear. Which keys an org_type accepts is
    checked by services.bdm_organizations.check_profile (it needs the effective type); unknown keys -- the live agent figures commission,
    students, applications, enrollments and master_login among them -- are refused here (AC4)."""

    model_config = ConfigDict(extra="forbid")
    country: BdmOrgShort = Field(None, description="Agent: country (free text).")
    territory: BdmOrgShort = Field(None, description="Agent: territory (free text).")
    source: BdmOrgSource | None = Field(None, description="Agent: how the agency was found.")
    staff_count: BdmStaffCount = Field(None, description="Agent: number of staff, entered by the BDM (0-100000).")
    board: BdmSchoolBoard | None = Field(None, description="School: board, ENH-009's values.")
    school_type: BdmSchoolType | None = Field(None, description="School: school type.")
    grade_from: BdmGrade = Field(None, description="School: lowest grade. -2 Nursery, -1 LKG, 0 UKG, then 1-12.")
    grade_to: BdmGrade = Field(None, description="School: highest grade, same codes; not below grade_from.")
    affiliation: BdmOrgMedium = Field(None, description="College/University: university or affiliation (free text).")
    college_type: BdmCollegeType | None = Field(None, description="College/University: college type.")
    courses: BdmOrgCourses = Field(None, description="College/University: courses the college teaches; line breaks allowed.")
```

(h) In `BdmOrganizationCreate` add after `state`: `address: BdmOrgAddress = None`, and after `student_count`: `profile: BdmOrgProfileIn | None = None`. In `BdmOrganizationUpdate` add after `state`: `address: BdmOrgAddress = None`, and after `student_count`: `profile: BdmOrgProfileIn = None  # omitted = unchanged; an explicit null is a 422 (bdm-001's PATCH idiom)`.

(i) After `class BdmOrgPermissions` add:

```python
class BdmAgentProfileOut(BaseModel):
    kind: Literal["agent"]
    country: str | None
    territory: str | None
    source: str | None
    staff_count: int | None


class BdmSchoolProfileOut(BaseModel):
    kind: Literal["school"]
    board: str | None
    school_type: str | None
    grade_from: int | None
    grade_to: int | None


class BdmCollegeProfileOut(BaseModel):
    kind: Literal["college"]
    affiliation: str | None
    college_type: str | None
    courses: str | None


BdmOrgProfileOut = Annotated[BdmAgentProfileOut | BdmSchoolProfileOut | BdmCollegeProfileOut, Field(discriminator="kind")]
```

(j) In `BdmOrganizationOut` add after `website`: `address: str | None`, and after `student_count`: `profile: BdmOrgProfileOut | None  # null for corporate / training_institute / other (spec §5.1)`.

- [ ] **Step 4: Run to verify they pass, plus the bdm-002 schema tests (the student-count refactor and P14 must not break them)**

Run: `API_TEST "tests/test_bdm_003_schemas.py tests/test_bdm_002_schemas.py"`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas.py apps/api/tests/test_bdm_003_schemas.py
git commit -m "feat(bdm-003): profile schemas, address and the multi-line rule (P14)"
```

---

### Task 4: Service — profile checks and output

**Files:**
- Modify: `apps/api/app/services/bdm_organizations.py`
- Create: `apps/api/tests/bdm003_helpers.py`
- Create: `apps/api/tests/test_bdm_003_profiles.py` (service unit tests first)

**Interfaces:**
- Consumes: `BDM_PROFILE_GROUP`, `BDM_PROFILE_FIELDS` (Task 1).
- Produces:
  - `profile_group(org_type: str) -> str | None`
  - `check_profile(org_type: str, sent: dict, stored: BdmOrganization | None) -> None` — raises `RequestValidationError` (422, `loc=("body", "profile", key)`).
  - `check_type_change(user: User, org: BdmOrganization, new_type: str) -> None` — raises `HTTPException(409, {"message", "code": "profile_not_empty", "fields"})`.
  - `profile_out(org: BdmOrganization) -> dict | None`
  - `organization_out(...)` now includes `"address"` and `"profile"`.
  - tests: `bdm003_helpers.bdm_of(db, bdm_type) -> User`, `profile_org(client, org_type, **profile) -> dict`.

- [ ] **Step 1: Create the helpers** — `apps/api/tests/bdm003_helpers.py`:

```python
"""bdm-003 test builders, on top of bdm-002's. Unique values per call: the test database is shared and never truncated."""

from app.models import User
from tests.bdm001_helpers import make_manager
from tests.bdm002_helpers import create_org, make_bdm

MODULE_OF = {"agent": "agent", "school": "school", "college": "college", "university": "college", "corporate": "college"}


async def bdm_of(db, bdm_type: str, manager: User | None = None) -> User:
    return await make_bdm(db, manager or await make_manager(db), bdm_type)


async def profile_org(client, org_type: str, **profile) -> dict:
    return await create_org(client, org_type=org_type, **({"profile": profile} if profile else {}))
```

- [ ] **Step 2: Write the failing unit tests** — create `apps/api/tests/test_bdm_003_profiles.py`:

```python
"""bdm-003 -- type-specific profiles through the service and the API (spec §5, §7 AC1-AC8, §12)."""

import asyncio
import logging
import uuid

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, BdmOrganization
from app.services import bdm_organizations as svc
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import ORGS, create_org, unique_name
from tests.bdm003_helpers import bdm_of, profile_org


def _org(org_type: str, **values) -> BdmOrganization:
    return BdmOrganization(id=uuid.uuid4(), org_type=org_type, **values)


def _locs(exc: RequestValidationError) -> dict[str, str]:
    return {e["loc"][-1]: e["msg"] for e in exc.errors()}


def test_check_profile_allows_the_group_and_refuses_other_keys_by_presence():
    svc.check_profile("school", {"board": "CBSE", "grade_from": 6}, None)
    svc.check_profile("university", {"affiliation": "VTU"}, None)
    svc.check_profile("corporate", {}, None)
    with pytest.raises(RequestValidationError) as exc:
        svc.check_profile("college", {"board": None, "country": "India", "affiliation": "VTU"}, None)
    assert _locs(exc.value) == {"board": "Board is not a field for College organizations", "country": "Country is not a field for College organizations"}
    assert all(e["loc"][:2] == ("body", "profile") for e in exc.value.errors())
    with pytest.raises(RequestValidationError) as exc:
        svc.check_profile("other", {"courses": "MBA"}, None)
    assert _locs(exc.value) == {"courses": "Courses is not a field for Other organizations"}


def test_check_profile_grade_order_uses_stored_values_overlaid_by_sent():
    stored = _org("school", grade_from=6, grade_to=12)
    svc.check_profile("school", {"grade_to": 8}, stored)
    svc.check_profile("school", {"grade_from": None, "grade_to": 3}, stored)
    for sent in ({"grade_to": 5}, {"grade_from": 13 - 1, "grade_to": 6}, {"grade_from": 12, "grade_to": None} | {"grade_to": 11}):
        with pytest.raises(RequestValidationError) as exc:
            svc.check_profile("school", sent, stored)
        assert _locs(exc.value) == {"grade_to": "Lowest grade can't be above the highest grade"}


def test_check_type_change_refuses_across_groups_while_the_old_group_has_data():
    user = type("U", (), {"id": uuid.uuid4()})()
    svc.check_type_change(user, _org("college", affiliation="VTU"), "university")  # same group
    svc.check_type_change(user, _org("school"), "college")  # nothing entered
    svc.check_type_change(user, _org("corporate"), "school")  # no old group
    with pytest.raises(HTTPException) as exc:
        svc.check_type_change(user, _org("school", board="CBSE", grade_to=10), "agent")
    assert exc.value.status_code == 409
    assert exc.value.detail == {"message": "Clear the School details before changing the type", "code": "profile_not_empty", "fields": ["board", "grade_to"]}


def test_profile_out_per_group():
    assert svc.profile_out(_org("agent", country="India", staff_count=4)) == {"kind": "agent", "country": "India", "territory": None, "source": None, "staff_count": 4}
    assert svc.profile_out(_org("university", courses="MBA"))["kind"] == "college"
    assert svc.profile_out(_org("training_institute")) is None
```

- [ ] **Step 3: Run to verify they fail**

Run: `API_TEST "tests/test_bdm_003_profiles.py"`
Expected: FAIL — `AttributeError: module 'app.services.bdm_organizations' has no attribute 'check_profile'`.

- [ ] **Step 4: Implement in `apps/api/app/services/bdm_organizations.py`**

Imports: add `from fastapi.exceptions import RequestValidationError` and extend the models import with `BDM_PROFILE_FIELDS, BDM_PROFILE_GROUP`. After `STATE_REFUSALS` add:

```python
ORG_TYPE_LABELS = {"college": "College", "university": "University", "agent": "Agent", "school": "School", "corporate": "Corporate", "training_institute": "Training Institute", "other": "Other"}
GROUP_LABELS = {"agent": "Agent", "school": "School", "college": "College"}
PROFILE_LABELS = {
    "country": "Country", "territory": "Territory", "source": "Source", "staff_count": "Number of staff", "board": "Board", "school_type": "School type",
    "grade_from": "Lowest grade", "grade_to": "Highest grade", "affiliation": "University / affiliation", "college_type": "College type", "courses": "Courses",
}
GRADE_ORDER = "Lowest grade can't be above the highest grade"
```

Before `def _person` add:

```python
def profile_group(org_type: str) -> str | None:
    return BDM_PROFILE_GROUP.get(org_type)


def _profile_error(key: str, msg: str, value) -> dict:
    return {"type": "value_error", "loc": ("body", "profile", key), "msg": msg, "input": value}


def check_profile(org_type: str, sent: dict, stored: BdmOrganization | None) -> None:
    """spec §5.2 (AC2, AC6): the keys the effective org_type accepts -- by presence, so {"board": null} on a College is refused too -- and
    the grade order on the stored values overlaid by the sent ones. One 422 in FastAPI's own shape, each error at its field (the
    agent_visa precedent), so the form can mark the field. Runs after the row lock on PATCH, so `stored` is current."""
    allowed = BDM_PROFILE_FIELDS.get(profile_group(org_type), ())
    errors = [_profile_error(k, f"{PROFILE_LABELS[k]} is not a field for {ORG_TYPE_LABELS[org_type]} organizations", v) for k, v in sent.items() if k not in allowed]
    if not errors and "grade_from" in allowed:
        low, high = (sent[k] if k in sent else getattr(stored, k, None) for k in ("grade_from", "grade_to"))
        if low is not None and high is not None and low > high:
            errors.append(_profile_error("grade_to", GRADE_ORDER, sent.get("grade_to", high)))
    if errors:
        raise RequestValidationError(errors)


def check_type_change(user: User, org: BdmOrganization, new_type: str) -> None:
    """P4 / AC5: a type change into another profile group is a 409 while the old group has data; the BDM clears it first. College <->
    University share a group. Structured like possible_duplicate, so the form names the fields without parsing text (§12.1 A1)."""
    old = profile_group(org.org_type)
    if old is None or old == profile_group(new_type):
        return
    filled = [k for k in BDM_PROFILE_FIELDS[old] if getattr(org, k) is not None]
    if filled:
        log("bdm_org_type_change_refused", user, org.id, from_group=old, fields=filled)
        raise HTTPException(409, {"message": f"Clear the {GROUP_LABELS[old]} details before changing the type", "code": "profile_not_empty", "fields": filled})


def profile_out(org: BdmOrganization) -> dict | None:
    group = profile_group(org.org_type)
    return None if group is None else {"kind": group, **{k: getattr(org, k) for k in BDM_PROFILE_FIELDS[group]}}
```

In `organization_out`, after `"website": org.website,` add `"address": org.address,`, and after `"student_count": org.student_count,` add `"profile": profile_out(org),`.

- [ ] **Step 5: Run to verify they pass**

Run: `API_TEST "tests/test_bdm_003_profiles.py"`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/bdm_organizations.py apps/api/tests/bdm003_helpers.py apps/api/tests/test_bdm_003_profiles.py
git commit -m "feat(bdm-003): check_profile, check_type_change and profile output in the organization service"
```

---

### Task 5: Create route

**Files:**
- Modify: `apps/api/app/api/bdm_organizations.py` (`create_organization`, L87–132)
- Modify: `apps/api/tests/test_bdm_003_profiles.py`

**Interfaces:**
- Consumes: `svc.check_profile` (Task 4); `BdmOrganizationCreate.profile` / `.address` (Task 3).

- [ ] **Step 1: Write the failing tests** — append:

```python
async def _audit(db, org_id, action: str) -> dict:
    row = await db.scalar(select(AuditLog).where(AuditLog.entity_id == str(org_id), AuditLog.action == f"bdm_organization.{action}").order_by(AuditLog.created_at.desc()))
    return row.metadata_json if row else None


@pytest.mark.asyncio
async def test_creates_each_type_with_its_profile_and_always_returns_both_keys(client, db_session):
    await login(client, await bdm_of(db_session, "school"))
    school = await create_org(client, org_type="school", address="1 Main Rd\nKochi", profile={"board": "CBSE", "school_type": "private", "grade_from": 6, "grade_to": 12})
    assert school["profile"] == {"kind": "school", "board": "CBSE", "school_type": "private", "grade_from": 6, "grade_to": 12}
    assert school["address"] == "1 Main Rd\nKochi"
    assert (await client.get(f"{ORGS}/{school['id']}")).json()["organization"]["profile"] == school["profile"]
    metadata = await _audit(db_session, school["id"], "create")
    assert {"address", "board", "school_type", "grade_from", "grade_to"} <= set(metadata["fields"])
    assert "Kochi" not in str(metadata) and "CBSE" not in str(metadata)  # names only, never values
    corporate = await create_org(client, org_type="corporate", profile={})
    assert corporate["profile"] is None and corporate["address"] is None
    await login(client, await bdm_of(db_session, "agent"))
    agent = await create_org(client, org_type="agent", profile={"country": "India", "territory": "South", "source": "referral", "staff_count": 8})
    assert agent["profile"] == {"kind": "agent", "country": "India", "territory": "South", "source": "referral", "staff_count": 8}
    await login(client, await bdm_of(db_session, "college"))
    uni = await create_org(client, org_type="university", profile={"affiliation": "VTU", "college_type": "engineering", "courses": "B.Tech CSE\nMBA"})
    assert uni["profile"]["kind"] == "college" and uni["profile"]["courses"] == "B.Tech CSE\nMBA"
    plain = await create_org(client)  # a bdm-002-style payload: unchanged behaviour (AC7)
    assert plain["profile"] == {"kind": "college", "affiliation": None, "college_type": None, "courses": None}


@pytest.mark.asyncio
async def test_create_refuses_another_types_field_and_consumes_no_code(client, db_session):
    await login(client, await bdm_of(db_session, "college"))
    first = await create_org(client)
    name = unique_name()
    refused = await client.post(ORGS, json={"org_type": "college", "name": name, "city": "Kochi", "contacts": [{"name": "Dr Rao"}], "profile": {"board": "CBSE", "grade_to": 3}})
    assert refused.status_code == 422
    assert [(e["loc"], e["msg"]) for e in refused.json()["detail"]] == [
        (["body", "profile", "board"], "Board is not a field for College organizations"),
        (["body", "profile", "grade_to"], "Highest grade is not a field for College organizations"),
    ]
    assert await db_session.scalar(select(BdmOrganization).where(BdmOrganization.name == name)) is None
    second = await create_org(client)
    assert int(second["code"][4:]) == int(first["code"][4:]) + 1  # the refused create took no ORG- number
    order = await client.post(ORGS, json={"org_type": "school", "name": unique_name(), "city": "K", "contacts": [{"name": "A"}], "profile": {"grade_from": 10, "grade_to": 6}})
    assert order.status_code == 422 and order.json()["detail"][0]["msg"] == "Lowest grade can't be above the highest grade"


@pytest.mark.asyncio
async def test_create_refuses_live_metrics_bad_enums_and_a_bad_contact_email(client, db_session):
    await login(client, await bdm_of(db_session, "agent"))
    for profile in ({"commission": 10}, {"students": 1}, {"applications": 1}, {"enrollments": 1}, {"master_login": "x"}, {"source": "tv"}, {"staff_count": "8"}):
        assert (await client.post(ORGS, json={"org_type": "agent", "name": unique_name(), "city": "K", "contacts": [{"name": "A"}], "profile": profile})).status_code == 422, profile
    assert (await client.post(ORGS, json={"org_type": "agent", "name": unique_name(), "city": "K", "contacts": [{"name": "A"}], "commission": 10})).status_code == 422
    bad_email = await client.post(ORGS, json={"org_type": "agent", "name": unique_name(), "city": "K", "contacts": [{"name": "A", "email": "no"}]})
    assert bad_email.status_code == 422
```

- [ ] **Step 2: Run to verify they fail**

Run: `API_TEST "tests/test_bdm_003_profiles.py -k create"`
Expected: FAIL — creating with `profile` raises `TypeError: 'profile' is an invalid keyword argument` (500) or the profile comes back with `null` values; the refused-create test gets 201.

- [ ] **Step 3: Implement** — in `create_organization`, after `profile = await bdm_context(db, user)` rename that local to `bdm_profile` (it is the BDM's profile, not the organization's; update its two uses `profile.bdm_type`). Then add right after it:

```python
    sent = payload.profile.model_dump(exclude_unset=True) if payload.profile else {}
    svc.check_profile(payload.org_type, sent, None)  # before the duplicate check and next_code: a refusal takes no ORG- number
```

In the `BdmOrganization(...)` call add `**sent,` after `**{k: getattr(payload, k) for k in BDM_ORG_FIELDS},`. In the create audit metadata replace the `"fields"` value with:

```python
            "fields": sorted([k for k in BDM_ORG_FIELDS if getattr(payload, k) not in (None, False)] + [k for k, v in sent.items() if v is not None]),
```

Update the docstring's first line to: `AC1/AC2 (bdm-002) + bdm-003 AC1/AC2: BDMs only; the profile is checked against org_type before anything is written.`

- [ ] **Step 4: Run to verify they pass, plus bdm-002's organization tests**

Run: `API_TEST "tests/test_bdm_003_profiles.py tests/test_bdm_002_organizations.py"`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/bdm_organizations.py apps/api/tests/test_bdm_003_profiles.py
git commit -m "feat(bdm-003): create accepts address and a per-type profile"
```

---

### Task 6: PATCH route — profile edits and type change

**Files:**
- Modify: `apps/api/app/api/bdm_organizations.py` (`update_organization`, L140–167)
- Modify: `apps/api/tests/test_bdm_003_profiles.py`

**Interfaces:**
- Consumes: `svc.check_profile`, `svc.check_type_change` (Task 4).

- [ ] **Step 1: Write the failing tests** — append:

```python
@pytest.mark.asyncio
async def test_patch_partial_clear_no_op_and_null_profile(client, db_session):
    await login(client, await bdm_of(db_session, "school"))
    org = await profile_org(client, "school", board="CBSE", grade_from=6, grade_to=12)
    url = f"{ORGS}/{org['id']}"
    cleared = await client.patch(url, json={"profile": {"board": None}, "address": "Kochi"})
    assert cleared.status_code == 200
    assert cleared.json()["organization"]["profile"] == {"kind": "school", "board": None, "school_type": None, "grade_from": 6, "grade_to": 12}
    assert sorted((await _audit(db_session, org["id"], "update"))["fields"]) == ["address", "board"]
    before = await db_session.scalar(select(AuditLog.id).where(AuditLog.entity_id == org["id"]).order_by(AuditLog.created_at.desc()))
    assert (await client.patch(url, json={"profile": {}})).status_code == 200
    assert (await client.patch(url, json={"profile": {"grade_to": 12}})).status_code == 200  # equal to stored: not a change
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.entity_id == org["id"]).order_by(AuditLog.created_at.desc())) == before
    assert (await client.patch(url, json={"profile": None})).status_code == 422
    order = await client.patch(url, json={"profile": {"grade_to": 5}})
    assert order.status_code == 422 and order.json()["detail"][0]["loc"] == ["body", "profile", "grade_to"]


@pytest.mark.asyncio
async def test_type_change_is_409_until_cleared_and_college_university_is_free(client, db_session):
    await login(client, await bdm_of(db_session, "school"))
    org = await profile_org(client, "school", board="CBSE", grade_to=10)
    url = f"{ORGS}/{org['id']}"
    refused = await client.patch(url, json={"org_type": "college"})
    assert refused.status_code == 409
    assert refused.json()["detail"] == {"message": "Clear the School details before changing the type", "code": "profile_not_empty", "fields": ["board", "grade_to"]}
    both = await client.patch(url, json={"org_type": "college", "profile": {"board": None}})  # the old group's keys belong to another type now
    assert both.status_code == 422 and both.json()["detail"][0]["loc"] == ["body", "profile", "board"]
    assert (await client.patch(url, json={"profile": {"board": None, "grade_to": None}})).status_code == 200
    moved = await client.patch(url, json={"org_type": "college", "profile": {"affiliation": "VTU"}})
    assert moved.status_code == 200 and moved.json()["organization"]["profile"] == {"kind": "college", "affiliation": "VTU", "college_type": None, "courses": None}
    uni = await client.patch(url, json={"org_type": "university"})
    assert uni.status_code == 200 and uni.json()["organization"]["profile"]["affiliation"] == "VTU"
    assert sorted((await _audit(db_session, org["id"], "update"))["fields"]) == ["org_type"]


@pytest.mark.asyncio
async def test_pre_bdm003_organization_edits_cleanly(client, db_session):
    """Review Focus 1: an organization saved before bdm-003 (every profile column NULL) edits its common fields with no profile check."""
    await login(client, await bdm_of(db_session, "college"))
    org = await create_org(client)
    edited = await client.patch(f"{ORGS}/{org['id']}", json={"name": unique_name(), "org_type": "agent"})
    assert edited.status_code == 200 and edited.json()["organization"]["profile"]["kind"] == "agent"


@pytest.mark.asyncio
async def test_profile_writes_keep_bdm002_authorization(client, db_session):
    manager = await make_manager(db_session)
    owner = await bdm_of(db_session, "school", manager)
    await login(client, owner)
    org = await profile_org(client, "school", board="CBSE")
    url = f"{ORGS}/{org['id']}"
    await login(client, await bdm_of(db_session, "school", manager))  # same type, not assigned
    assert (await client.patch(url, json={"profile": {"board": "ICSE"}})).status_code == 403
    await login(client, manager)
    assert (await client.patch(url, json={"profile": {"board": "ICSE"}})).status_code == 403
    await login(client, await bdm_of(db_session, "agent"))  # other module: out of scope
    assert (await client.patch(url, json={"profile": {"board": "ICSE"}})).status_code == 404
    await login(client, owner)
    assert (await client.post(f"{url}/archive")).status_code == 200
    assert (await client.patch(url, json={"profile": {"board": "ICSE"}})).status_code == 409
```

- [ ] **Step 2: Run to verify they fail**

Run: `API_TEST "tests/test_bdm_003_profiles.py -k 'patch or type_change or pre_bdm003 or authorization'"`
Expected: FAIL — PATCH with `profile` crashes in the diff (`AttributeError: 'BdmOrganization' object has no attribute 'profile'`) and the type change returns 200 instead of 409.

- [ ] **Step 3: Implement** — in `update_organization` replace

```python
    changes = payload.model_dump(exclude_unset=True, exclude={"confirm_duplicate"})
```

with

```python
    changes = payload.model_dump(exclude_unset=True, exclude={"confirm_duplicate", "profile"})
    new_type = changes.get("org_type", org.org_type)
    svc.check_profile(new_type, payload.profile.model_dump(exclude_unset=True) if payload.profile else {}, org)  # after the lock: org is current
    if new_type != org.org_type:
        svc.check_type_change(user, org, new_type)
    if payload.profile:
        changes |= payload.profile.model_dump(exclude_unset=True)  # profile keys are columns: the diff, audit and no-op rules below apply as-is
```

Extend the docstring: `bdm-003: the profile is checked against the effective type (the new one when org_type changes) after the lock; a type change into another profile group is a 409 while the old group has data (P4).`

- [ ] **Step 4: Run to verify they pass, plus bdm-002's organization and assign tests**

Run: `API_TEST "tests/test_bdm_003_profiles.py tests/test_bdm_002_organizations.py tests/test_bdm_002_assign.py"`
Expected: all pass.

- [ ] **Step 5: Refactor** — `payload.profile.model_dump(exclude_unset=True)` is computed twice; bind it once (`sent = payload.profile.model_dump(exclude_unset=True) if payload.profile else {}`) and use `sent` in both places. Rerun Step 4's command; expected all pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/bdm_organizations.py apps/api/tests/test_bdm_003_profiles.py
git commit -m "feat(bdm-003): PATCH edits the profile and refuses a type change over entered data"
```

---

### Task 7: List filters — Board, Affiliation, Territory

**Files:**
- Modify: `apps/api/app/api/bdm_organizations.py` (`list_organizations`, L52–84)
- Modify: `apps/api/tests/test_bdm_003_profiles.py`

**Interfaces:**
- Consumes: `BdmSchoolBoard` (Task 3).
- Produces: query params `board`, `affiliation`, `territory` on `GET /bdm/organizations` (web Task 14 sends them by these names).

- [ ] **Step 1: Write the failing test** — append:

```python
@pytest.mark.asyncio
async def test_profile_filters_narrow_within_scope(client, db_session):
    await login(client, await bdm_of(db_session, "school"))
    tag = uuid.uuid4().hex[:8]
    cbse = await create_org(client, org_type="school", name=f"School {tag} A", profile={"board": "CBSE"})
    await create_org(client, org_type="school", name=f"School {tag} B", profile={"board": "ICSE"})
    page = (await client.get(ORGS, params={"q": tag, "board": "CBSE"})).json()
    assert [r["id"] for r in page["items"]] == [cbse["id"]] and page["total"] == 1
    assert (await client.get(ORGS, params={"q": tag, "board": "cbse"})).status_code == 422
    assert (await client.get(ORGS, params={"q": tag, "org_type": "college", "board": "CBSE"})).json()["total"] == 0  # impossible combination: empty, not 422
    await login(client, await bdm_of(db_session, "agent"))
    assert (await client.get(ORGS, params={"q": tag, "board": "CBSE"})).json()["total"] == 0  # another module's schools stay out of scope
    south = await create_org(client, org_type="agent", name=f"Agency {tag}", profile={"territory": "South_100%"})
    await create_org(client, org_type="agent", name=f"Agency {tag} 2", profile={"territory": "South 1000"})
    assert [r["id"] for r in (await client.get(ORGS, params={"q": tag, "territory": "h_100%"})).json()["items"]] == [south["id"]]  # % and _ literal
    await login(client, await bdm_of(db_session, "college"))
    vtu = await create_org(client, org_type="college", name=f"College {tag}", profile={"affiliation": "VTU Belagavi"})
    assert [r["id"] for r in (await client.get(ORGS, params={"q": tag, "affiliation": "vtu"})).json()["items"]] == [vtu["id"]]
    assert (await client.get(ORGS, params={"territory": "x" * 121})).status_code == 422
```

- [ ] **Step 2: Run to verify it fails**

Run: `API_TEST "tests/test_bdm_003_profiles.py::test_profile_filters_narrow_within_scope"`
Expected: FAIL — the `board` param is ignored, so the first assertion sees two rows.

- [ ] **Step 3: Implement** — add `BdmSchoolBoard` to the schemas import; add parameters after `city`:

```python
    board: BdmSchoolBoard | None = None,
    affiliation: str | None = Query(None, max_length=200),
    territory: str | None = Query(None, max_length=120),
```

and after the `city` filter line:

```python
    if board:
        filters.append(BdmOrganization.board == board)
    filters += _matching(like_pattern(affiliation), BdmOrganization.affiliation)  # bdm-003: literal, case-insensitive substrings
    filters += _matching(like_pattern(territory), BdmOrganization.territory)
```

- [ ] **Step 4: Run to verify it passes, with the bdm-002 list test**

Run: `API_TEST "tests/test_bdm_003_profiles.py tests/test_bdm_002_organizations.py::test_list_filters_paging_and_archived_default"`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/bdm_organizations.py apps/api/tests/test_bdm_003_profiles.py
git commit -m "feat(bdm-003): Board, Affiliation and Territory list filters"
```

---

### Task 8: Races and sensitive logs

**Files:**
- Modify: `apps/api/tests/test_bdm_003_profiles.py` (tests only; production code changes only if a test exposes a defect)

- [ ] **Step 1: Write the tests** — append:

```python
async def _two_clients(owner, org_type: str, **profile):
    one = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    two = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    await login(one, owner)
    await login(two, owner)
    return one, two, await profile_org(one, org_type, **profile)


@pytest.mark.asyncio
async def test_type_change_and_profile_edit_race_has_one_consistent_outcome(db_session):
    """§5.4: both lock the row; the second re-checks against the committed type. Either the board lands and the type change is 409, or
    the type change lands and the board is 422 -- never a School board on a College (the group CHECK would make that a 500)."""
    owner = await bdm_of(db_session, "school")
    one, two, org = await _two_clients(owner, "school")
    url = f"{ORGS}/{org['id']}"
    async with one, two:
        results = await asyncio.gather(one.patch(url, json={"org_type": "college"}), two.patch(url, json={"profile": {"board": "CBSE"}}))
    codes = sorted(r.status_code for r in results)
    assert codes in ([200, 409], [200, 422]), [r.text for r in results]
    stored = await db_session.scalar(select(BdmOrganization).where(BdmOrganization.id == uuid.UUID(org["id"])).execution_options(populate_existing=True))
    assert (stored.org_type, stored.board) in (("college", None), ("school", "CBSE"))


@pytest.mark.asyncio
async def test_conflicting_grade_edits_race_leaves_a_valid_range(db_session):
    owner = await bdm_of(db_session, "school")
    one, two, org = await _two_clients(owner, "school")
    url = f"{ORGS}/{org['id']}"
    async with one, two:
        results = await asyncio.gather(one.patch(url, json={"profile": {"grade_from": 8}}), two.patch(url, json={"profile": {"grade_to": 6}}))
    assert sorted(r.status_code for r in results) == [200, 422], [r.text for r in results]
    stored = await db_session.scalar(select(BdmOrganization).where(BdmOrganization.id == uuid.UUID(org["id"])).execution_options(populate_existing=True))
    assert stored.grade_from is None or stored.grade_to is None


@pytest.mark.asyncio
async def test_logs_carry_ids_and_field_names_never_profile_text(client, db_session, caplog):
    caplog.set_level(logging.INFO, logger="app.bdm")
    await login(client, await bdm_of(db_session, "school"))
    secret = f"Plot {uuid.uuid4().hex[:6]} Lane"
    org = await create_org(client, org_type="school", address=secret, profile={"board": "CBSE"})
    assert (await client.patch(f"{ORGS}/{org['id']}", json={"org_type": "agent"})).status_code == 409
    assert "bdm_org_type_change_refused" in caplog.text
    assert secret not in caplog.text and "CBSE" not in caplog.text
```

- [ ] **Step 2: Run them**

Run: `API_TEST "tests/test_bdm_003_profiles.py -k 'race or logs'"`
Expected: 3 passed (the row lock from bdm-002 and Task 6's ordering already serialize these). If a race test fails, it is a real defect: fix the route (check ordering after `load_scoped(lock=True)`), not the test.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_bdm_003_profiles.py
git commit -m "test(bdm-003): profile races and log hygiene"
```

- [ ] **Step 4: Backend lite regression**

Run: `API_TEST "tests/test_bdm_003_migration.py tests/test_bdm_003_schemas.py tests/test_bdm_003_profiles.py tests/test_bdm_002_migration.py tests/test_bdm_002_schemas.py tests/test_bdm_002_service.py tests/test_bdm_002_organizations.py tests/test_bdm_002_assign.py tests/test_bdm_002_contacts.py tests/test_agn_015_migration.py tests/test_agn_017_migration.py tests/test_bdm_001_*.py"`
Expected: all pass. Record the counts for the completion report.

---

### Task 9: Web library — enums, labels, helpers, types

**Files:**
- Modify: `apps/web/lib/bdmOrganizations.ts`
- Modify: `apps/web/tests/components/BdmOrganizationDetail.test.tsx` (fixture gains `address: null, profile: null` so `tsc` stays green)
- Create or modify: `apps/web/tests/lib/bdmOrganizations.test.ts`

**Interfaces:**
- Produces: `ProfileGroup`, `profileGroup(orgType: string): ProfileGroup | null`, `PROFILE_GROUP_LABEL`, `PROFILE_FIELDS`, `ALL_PROFILE_FIELDS`, `ProfileField`, `PROFILE_LABEL`, `SOURCES`/`SOURCE_LABEL`, `BOARDS`/`BOARD_LABEL`, `SCHOOL_TYPES`/`SCHOOL_TYPE_LABEL`, `COLLEGE_TYPES`/`COLLEGE_TYPE_LABEL`, `GRADES`, `gradeLabel(g: number): string`, `gradeRange(from: number | null, to: number | null): string`, `labelOf(map: Record<string, string>, value: string | null): string`, `rolesFor(orgType?: string): ContactRole[]`, `profileNotEmpty(detail: unknown): string[] | null`, `typeChangeMessage(group: ProfileGroup, fields: string[]): string`, `OrgProfile`; `Organization` gains `address: string | null; profile: OrgProfile | null`.

- [ ] **Step 1: Write the failing test** — `apps/web/tests/lib/bdmOrganizations.test.ts` (create it if absent; if present, append the `describe`):

```ts
import { describe, expect, it } from "vitest";

import { BOARD_LABEL, gradeRange, labelOf, profileGroup, profileNotEmpty, rolesFor, typeChangeMessage } from "@/lib/bdmOrganizations";

describe("bdm-003 profile helpers", () => {
  it("maps org types to profile groups", () => {
    expect(["agent", "school", "college", "university", "corporate", "training_institute", "other", ""].map(profileGroup)).toEqual(["agent", "school", "college", "college", null, null, null, null]);
  });
  it("writes grade ranges with pre-primary names", () => {
    expect(gradeRange(-1, 12)).toBe("LKG–12");
    expect(gradeRange(6, 12)).toBe("6–12");
    expect(gradeRange(-2, null)).toBe("From Nursery");
    expect(gradeRange(null, 0)).toBe("Up to UKG");
    expect(gradeRange(null, null)).toBe("—");
  });
  it("labels known values and shows an unknown one as it is", () => {
    expect(labelOf(BOARD_LABEL, "State")).toBe("State board");
    expect(labelOf(BOARD_LABEL, "Cambridge")).toBe("Cambridge");
    expect(labelOf(BOARD_LABEL, null)).toBe("—");
  });
  it("puts the type's suggested roles first and keeps every role", () => {
    expect(rolesFor("college").slice(0, 4)).toEqual(["principal", "dean", "hod", "placement_officer"]);
    expect(rolesFor("agent")[0]).toBe("owner");
    expect(new Set(rolesFor("school")).size).toBe(8);
    expect(rolesFor()).toEqual(rolesFor("corporate"));
  });
  it("reads the profile_not_empty conflict and words it", () => {
    expect(profileNotEmpty({ code: "profile_not_empty", message: "x", fields: ["board", "grade_to"] })).toEqual(["board", "grade_to"]);
    expect(profileNotEmpty({ code: "possible_duplicate", matches: [] })).toBeNull();
    expect(typeChangeMessage("school", ["board", "grade_to"])).toBe("Clear the School details before changing the type: Board, Highest grade.");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `WEB_TEST "npx vitest run tests/lib/bdmOrganizations.test.ts"`
Expected: FAIL — `gradeRange` (and the others) are not exported.

- [ ] **Step 3: Implement** — append to `apps/web/lib/bdmOrganizations.ts`:

```ts
// bdm-003 (DEC-SCOPE-063, spec §6.1): type-specific profiles. The API validates every value; these drive the form, labels and filters.
export type ProfileGroup = "agent" | "school" | "college";
const PROFILE_GROUP: Partial<Record<string, ProfileGroup>> = { agent: "agent", school: "school", college: "college", university: "college" };
export const profileGroup = (orgType: string): ProfileGroup | null => PROFILE_GROUP[orgType] ?? null;
export const PROFILE_GROUP_LABEL: Record<ProfileGroup, string> = { agent: "Agent", school: "School", college: "College" };
export const PROFILE_FIELDS = {
  agent: ["country", "territory", "source", "staff_count"],
  school: ["board", "school_type", "grade_from", "grade_to"],
  college: ["affiliation", "college_type", "courses"],
} as const;
export type ProfileField = (typeof PROFILE_FIELDS)[ProfileGroup][number];
export const ALL_PROFILE_FIELDS: ProfileField[] = [...PROFILE_FIELDS.agent, ...PROFILE_FIELDS.school, ...PROFILE_FIELDS.college];
export const PROFILE_LABEL: Record<ProfileField, string> = {
  country: "Country", territory: "Territory", source: "Source", staff_count: "Number of staff", board: "Board", school_type: "School type",
  grade_from: "Lowest grade", grade_to: "Highest grade", affiliation: "University / affiliation", college_type: "College type", courses: "Courses",
};
export const SOURCES = ["referral", "website", "event", "cold_call", "walk_in", "other"] as const;
export const SOURCE_LABEL: Record<string, string> = { referral: "Referral", website: "Website", event: "Event", cold_call: "Cold call", walk_in: "Walk-in", other: "Other" };
export const BOARDS = ["CBSE", "ICSE", "State", "IB", "Other"] as const;
export const BOARD_LABEL: Record<string, string> = { CBSE: "CBSE", ICSE: "ICSE", State: "State board", IB: "IB", Other: "Other" };
export const SCHOOL_TYPES = ["private", "government", "aided", "international", "other"] as const;
export const SCHOOL_TYPE_LABEL: Record<string, string> = { private: "Private", government: "Government", aided: "Aided", international: "International", other: "Other" };
export const COLLEGE_TYPES = ["engineering", "arts_science", "management", "medical", "polytechnic", "other"] as const;
export const COLLEGE_TYPE_LABEL: Record<string, string> = {
  engineering: "Engineering", arts_science: "Arts & Science", management: "Management", medical: "Medical", polytechnic: "Polytechnic", other: "Other",
};
export const GRADES = [-2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] as const;
const PRE_PRIMARY: Record<number, string> = { [-2]: "Nursery", [-1]: "LKG", 0: "UKG" };
export const gradeLabel = (grade: number): string => PRE_PRIMARY[grade] ?? String(grade);

export function gradeRange(from: number | null, to: number | null): string {
  if (from !== null && to !== null) return `${gradeLabel(from)}–${gradeLabel(to)}`;
  if (from !== null) return `From ${gradeLabel(from)}`;
  if (to !== null) return `Up to ${gradeLabel(to)}`;
  return "—";
}

/** A stored enum value as words; an unknown (newer) value is shown as it is instead of breaking the page (spec §12.2 F8). */
export const labelOf = (labels: Record<string, string>, value: string | null): string => (value === null ? "—" : (labels[value] ?? value));

const SUGGESTED_ROLES: Record<ProfileGroup, ContactRole[]> = { agent: ["owner"], school: ["principal", "management", "counselor"], college: ["principal", "dean", "hod", "placement_officer"] };
/** P8: every role stays valid on every type; the type's named people come first in the Role list. */
export function rolesFor(orgType?: string): ContactRole[] {
  const group = orgType ? profileGroup(orgType) : null;
  const first = group ? SUGGESTED_ROLES[group] : [];
  return [...first, ...CONTACT_ROLES.filter((r) => !first.includes(r))];
}

/** The fields of a `profile_not_empty` 409 (spec §5.2), or null for any other body. */
export function profileNotEmpty(detail: unknown): string[] | null {
  const d = detail as { code?: string; fields?: unknown } | null;
  return d && typeof d === "object" && d.code === "profile_not_empty" && Array.isArray(d.fields) ? d.fields.map(String) : null;
}

export const typeChangeMessage = (group: ProfileGroup, fields: string[]): string =>
  `Clear the ${PROFILE_GROUP_LABEL[group]} details before changing the type: ${fields.map((f) => PROFILE_LABEL[f as ProfileField] ?? f).join(", ")}.`;

export type OrgProfile =
  | { kind: "agent"; country: string | null; territory: string | null; source: string | null; staff_count: number | null }
  | { kind: "school"; board: string | null; school_type: string | null; grade_from: number | null; grade_to: number | null }
  | { kind: "college"; affiliation: string | null; college_type: string | null; courses: string | null };
```

In the `Organization` type add `address: string | null;` after `website` and `profile: OrgProfile | null;` after `student_count`. In `tests/components/BdmOrganizationDetail.test.tsx` add `address: null, profile: null,` to the `org()` fixture (after `student_count: null,`).

- [ ] **Step 4: Run to verify it passes, and type-check**

Run: `WEB_TEST "npx vitest run tests/lib/bdmOrganizations.test.ts && npx tsc --noEmit"`
Expected: tests pass; `tsc` exits 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/bdmOrganizations.ts apps/web/tests/lib/bdmOrganizations.test.ts apps/web/tests/components/BdmOrganizationDetail.test.tsx
git commit -m "feat(bdm-003): web profile enums, labels and helpers"
```

---

### Task 10: `BdmOrganizationProfileFields` — inputs and profile form logic

**Files:**
- Create: `apps/web/components/BdmOrganizationProfileFields.tsx`
- Create: `apps/web/tests/components/BdmOrganizationProfileFields.test.tsx`

**Interfaces:**
- Consumes: Task 9 exports.
- Produces: default `BdmOrganizationProfileFields({ idPrefix, group, values, errors, onChange })` (input ids `${idPrefix}-${field}`); `type ProfileValues = Record<ProfileField, string>`; `profileValuesOf(profile?: OrgProfile | null): ProfileValues`; `profilePayload(group: ProfileGroup | null, values: ProfileValues, original?: ProfileValues): Record<string, unknown> | null`; `profileErrors(group: ProfileGroup | null, values: ProfileValues): Partial<Record<ProfileField, string>>`; `filledFields(group: ProfileGroup | null, values: ProfileValues): ProfileField[]`.

- [ ] **Step 1: Write the failing tests** — `apps/web/tests/components/BdmOrganizationProfileFields.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationProfileFields, { filledFields, profileErrors, profilePayload, profileValuesOf } from "@/components/BdmOrganizationProfileFields";

afterEach(cleanup);
const blank = profileValuesOf(null);

describe("BdmOrganizationProfileFields (bdm-003 AC1, AC4, §12.2)", () => {
  it("renders exactly each type's fields under a legend, and nothing for common-only types", () => {
    const { rerender, container } = render(<BdmOrganizationProfileFields idPrefix="f" group="school" values={blank} errors={{}} onChange={vi.fn()} />);
    expect(screen.getByRole("group", { name: "School details" })).toBeInTheDocument();
    expect(["Board", "School type", "Lowest grade", "Highest grade"].map((l) => screen.getByLabelText(l).tagName)).toEqual(["SELECT", "SELECT", "SELECT", "SELECT"]);
    expect(screen.getByRole("option", { name: "LKG" })).toHaveValue("-1");
    rerender(<BdmOrganizationProfileFields idPrefix="f" group="college" values={blank} errors={{}} onChange={vi.fn()} />);
    expect(screen.getByLabelText("Courses").tagName).toBe("TEXTAREA");
    expect(screen.queryByLabelText("Board")).toBeNull();
    rerender(<BdmOrganizationProfileFields idPrefix="f" group="agent" values={blank} errors={{}} onChange={vi.fn()} />);
    expect(screen.getByLabelText("Number of staff")).toHaveAttribute("inputmode", "numeric");
    expect(screen.getByText("Commission: Available after onboarding").tagName).toBe("P"); // text, never an input
    expect(screen.queryByLabelText(/Commission/)).toBeNull();
    rerender(<BdmOrganizationProfileFields idPrefix="f" group={null} values={blank} errors={{}} onChange={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("reports changes and ties errors to their field", () => {
    const onChange = vi.fn();
    render(<BdmOrganizationProfileFields idPrefix="f" group="school" values={blank} errors={{ grade_to: "Lowest grade can't be above the highest grade" }} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Board"), { target: { value: "CBSE" } });
    expect(onChange).toHaveBeenCalledWith("board", "CBSE");
    expect(screen.getByLabelText("Highest grade")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Highest grade")).toHaveAccessibleDescription("Lowest grade can't be above the highest grade");
  });

  it("builds the create payload from the current group's filled fields only", () => {
    const values = { ...blank, board: "CBSE", grade_from: "6", grade_to: "12", country: "India" };
    expect(profilePayload("school", values)).toEqual({ board: "CBSE", grade_from: 6, grade_to: 12 });
    expect(profilePayload("school", blank)).toBeNull();
    expect(profilePayload(null, values)).toBeNull();
  });

  it("builds the edit payload from changes only and clears with null (Review Focus 3)", () => {
    const original = profileValuesOf({ kind: "school", board: "CBSE", school_type: "private", grade_from: 6, grade_to: 12 });
    expect(original.grade_from).toBe("6");
    expect(profilePayload("school", { ...original, board: "", grade_to: "10" }, original)).toEqual({ board: null, grade_to: 10 });
    expect(profilePayload("school", original, original)).toBeNull();
  });

  it("sends a non-whole number as typed so the server names the field (Review Focus 2)", () => {
    expect(profilePayload("agent", { ...blank, staff_count: "abc" })).toEqual({ staff_count: "abc" });
    expect(profilePayload("agent", { ...blank, staff_count: "6.5" })).toEqual({ staff_count: "6.5" });
    expect(JSON.stringify(profilePayload("agent", { ...blank, staff_count: "12" }))).toBe('{"staff_count":12}');
  });

  it("checks the grade order and lists filled fields", () => {
    expect(profileErrors("school", { ...blank, grade_from: "8", grade_to: "-1" })).toEqual({ grade_to: "Lowest grade can't be above the highest grade" });
    expect(profileErrors("school", { ...blank, grade_from: "-2", grade_to: "0" })).toEqual({});
    expect(filledFields("school", { ...blank, board: "CBSE", affiliation: "VTU" })).toEqual(["board"]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `WEB_TEST "npx vitest run tests/components/BdmOrganizationProfileFields.test.tsx"`
Expected: FAIL — cannot resolve `@/components/BdmOrganizationProfileFields`.

- [ ] **Step 3: Implement** — create `apps/web/components/BdmOrganizationProfileFields.tsx`:

```tsx
"use client";
import type { ChangeEvent } from "react";

import {
  ALL_PROFILE_FIELDS,
  BOARD_LABEL,
  BOARDS,
  COLLEGE_TYPE_LABEL,
  COLLEGE_TYPES,
  gradeLabel,
  GRADES,
  type OrgProfile,
  PROFILE_FIELDS,
  PROFILE_GROUP_LABEL,
  PROFILE_LABEL,
  type ProfileField,
  type ProfileGroup,
  SCHOOL_TYPE_LABEL,
  SCHOOL_TYPES,
  SOURCE_LABEL,
  SOURCES,
} from "@/lib/bdmOrganizations";

// bdm-003 (spec §6.2): the type-specific fields of one organization, plus the profile's form logic (values, payload, checks), the way
// BdmContactFields owns blankContact -- so BdmOrganizationForm stays small (§12.2 F1). Only the current type's group is shown or sent.
export type ProfileValues = Record<ProfileField, string>;
type Errors = Partial<Record<ProfileField, string>>;
const NUMERIC: ProfileField[] = ["staff_count", "grade_from", "grade_to"];
const GRADE_ORDER = "Lowest grade can't be above the highest grade";

export function profileValuesOf(profile?: OrgProfile | null): ProfileValues {
  const values = Object.fromEntries(ALL_PROFILE_FIELDS.map((k) => [k, ""])) as ProfileValues;
  for (const [key, value] of Object.entries(profile ?? {})) if (key !== "kind" && value !== null) values[key as ProfileField] = String(value);
  return values;
}

/** Blank is null (clears on edit); a whole number is a number; anything else goes as typed, so the server's plain 422 names the field
 * (Number("abc") is NaN, which JSON would turn into a silent null -- Review Focus 2). */
function wire(key: ProfileField, value: string): unknown {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  return NUMERIC.includes(key) && /^-?\d+$/.test(trimmed) ? Number(trimmed) : trimmed;
}

/** Create (no `original`): the group's filled fields. Edit: the group's changed fields. Null when there is nothing to send. */
export function profilePayload(group: ProfileGroup | null, values: ProfileValues, original?: ProfileValues): Record<string, unknown> | null {
  if (!group) return null;
  const keys = PROFILE_FIELDS[group].filter((k) => (original ? values[k].trim() !== original[k].trim() : values[k].trim() !== ""));
  return keys.length ? Object.fromEntries(keys.map((k) => [k, wire(k, values[k])])) : null;
}

/** A convenience before sending (the server decides): the grade order. */
export function profileErrors(group: ProfileGroup | null, values: ProfileValues): Errors {
  if (group !== "school" || values.grade_from === "" || values.grade_to === "") return {};
  return Number(values.grade_from) > Number(values.grade_to) ? { grade_to: GRADE_ORDER } : {};
}

export function filledFields(group: ProfileGroup | null, values: ProfileValues): ProfileField[] {
  return group ? PROFILE_FIELDS[group].filter((k) => values[k].trim() !== "") : [];
}

type Option = readonly [string, string];
type Spec = { key: ProfileField; kind: "text" | "number" | "textarea"; max: number } | { key: ProfileField; kind: "select"; options: Option[] };
const options = (values: readonly string[], labels: Record<string, string>): Option[] => values.map((v) => [v, labels[v]] as const);
const GRADE_OPTIONS: Option[] = GRADES.map((g) => [String(g), gradeLabel(g)] as const);
const SPECS: Record<ProfileGroup, Spec[]> = {
  agent: [
    { key: "country", kind: "text", max: 120 },
    { key: "territory", kind: "text", max: 120 },
    { key: "source", kind: "select", options: options(SOURCES, SOURCE_LABEL) },
    { key: "staff_count", kind: "number", max: 100_000 },
  ],
  school: [
    { key: "board", kind: "select", options: options(BOARDS, BOARD_LABEL) },
    { key: "school_type", kind: "select", options: options(SCHOOL_TYPES, SCHOOL_TYPE_LABEL) },
    { key: "grade_from", kind: "select", options: GRADE_OPTIONS },
    { key: "grade_to", kind: "select", options: GRADE_OPTIONS },
  ],
  college: [
    { key: "affiliation", kind: "text", max: 200 },
    { key: "college_type", kind: "select", options: options(COLLEGE_TYPES, COLLEGE_TYPE_LABEL) },
    { key: "courses", kind: "textarea", max: 1000 },
  ],
};

export default function BdmOrganizationProfileFields({
  idPrefix,
  group,
  values,
  errors,
  onChange,
}: {
  idPrefix: string;
  group: ProfileGroup | null;
  values: ProfileValues;
  errors: Errors;
  onChange: (key: ProfileField, value: string) => void;
}) {
  if (!group) return null;
  const field = (spec: Spec) => {
    const id = `${idPrefix}-${spec.key}`;
    const control = {
      id,
      value: values[spec.key],
      "aria-invalid": errors[spec.key] ? true : undefined,
      "aria-describedby": errors[spec.key] ? `${id}-error` : undefined,
      onChange: (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => onChange(spec.key, e.target.value),
    };
    return (
      <div className="field" key={spec.key}>
        <label htmlFor={id}>{PROFILE_LABEL[spec.key]}</label>
        {spec.kind === "select" ? (
          <select {...control}>
            <option value="">Choose…</option>
            {spec.options.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        ) : spec.kind === "textarea" ? (
          <textarea {...control} rows={3} maxLength={spec.max} />
        ) : spec.kind === "number" ? (
          <input {...control} type="number" inputMode="numeric" min={0} max={spec.max} />
        ) : (
          <input {...control} type="text" maxLength={spec.max} />
        )}
        {errors[spec.key] && (
          <p className="form-error" id={`${id}-error`}>
            {errors[spec.key]}
          </p>
        )}
      </div>
    );
  };
  return (
    <fieldset className="form" style={{ border: 0, padding: 0, margin: 0 }}>
      <legend style={{ fontWeight: 800 }}>{PROFILE_GROUP_LABEL[group]} details</legend>
      {SPECS[group].map(field)}
      {group === "agent" && (
        <p className="muted" style={{ margin: 0 }}>
          Commission: Available after onboarding
        </p>
      )}
    </fieldset>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `WEB_TEST "npx vitest run tests/components/BdmOrganizationProfileFields.test.tsx && npx tsc --noEmit"`
Expected: pass; `tsc` 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/BdmOrganizationProfileFields.tsx apps/web/tests/components/BdmOrganizationProfileFields.test.tsx
git commit -m "feat(bdm-003): profile fields component with its form logic"
```

---

### Task 11: Form — Address, Type help, profile state, errors, type-change block

**Files:**
- Modify: `apps/web/components/BdmOrganizationFields.tsx`
- Modify: `apps/web/components/BdmOrganizationForm.tsx`
- Modify: `apps/web/tests/components/BdmOrganizationForm.test.tsx`

**Interfaces:**
- Consumes: Task 9 (`profileGroup`, `ALL_PROFILE_FIELDS`, `profileNotEmpty`, `typeChangeMessage`, `ProfileField`); Task 10 (`BdmOrganizationProfileFields`, `profileValuesOf`, `profilePayload`, `profileErrors`, `filledFields`, `ProfileValues`); `BdmContactFields` gains `orgType` in Task 13 (pass it there, not here).
- Produces: `OrgValues.address`; `ORG_FIELDS` includes `"address"` after `"state"`.

- [ ] **Step 1: Write the failing tests** — append to `BdmOrganizationForm.test.tsx` (inside the file, a new `describe`):

```tsx
const SCHOOL = {
  ...ORG, org_type: "school", state: null, phone: null, email: null, website: null, existing_partner: false, courses_interested: null, student_count: null, address: null,
  profile: { kind: "school", board: "CBSE", school_type: null, grade_from: 6, grade_to: 12 },
} as never;

describe("BdmOrganizationForm profile (bdm-003 AC1, AC2, AC5, AC10, §12.2)", () => {
  it("shows the type's section, tells screen readers it follows the type, and sends only that group", async () => {
    const mock = serve(res({ organization: ORG }, 201));
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fillRequired();
    expect(screen.getByLabelText("Type (required)")).toHaveAccessibleDescription("The details section below changes with the type.");
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "agent" } });
    fireEvent.change(screen.getByLabelText("Country"), { target: { value: "India" } });
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "school" } });
    fireEvent.change(screen.getByLabelText("Board"), { target: { value: "CBSE" } });
    fireEvent.change(screen.getByLabelText("Address"), { target: { value: "1 Main Rd\nKochi" } });
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    await waitFor(() => expect(mock).toHaveBeenCalled());
    expect(body(mock).profile).toEqual({ board: "CBSE" }); // the agent's Country typed earlier is not sent
    expect(body(mock).address).toBe("1 Main Rd\nKochi");
  });

  it("checks the grade order before sending", async () => {
    const mock = serve();
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fillRequired();
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "school" } });
    fireEvent.change(screen.getByLabelText("Lowest grade"), { target: { value: "8" } });
    fireEvent.change(screen.getByLabelText("Highest grade"), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    expect(await screen.findByText("Lowest grade can't be above the highest grade")).toBeInTheDocument();
    expect(screen.getByLabelText("Highest grade")).toHaveFocus();
    expect(mock).not.toHaveBeenCalled();
  });

  it("puts a server profile 422 on its field", async () => {
    serve(res({ detail: [{ loc: ["body", "profile", "board"], msg: "Board is not a field for College organizations" }] }, 422));
    render(<BdmOrganizationForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fillRequired();
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "school" } });
    fireEvent.change(screen.getByLabelText("Board"), { target: { value: "CBSE" } });
    fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
    expect(await screen.findByText("Board is not a field for College organizations")).toBeInTheDocument();
    expect(screen.getByLabelText("Board")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Board")).toHaveFocus();
  });

  it("edits send only changed profile fields", async () => {
    const mock = serve(res({ organization: SCHOOL }));
    render(<BdmOrganizationForm mode="edit" organization={SCHOOL} onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByLabelText("Board")).toHaveValue("CBSE");
    fireEvent.change(screen.getByLabelText("Highest grade"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(mock).toHaveBeenCalled());
    expect(body(mock)).toEqual({ profile: { grade_to: 10 } });
  });

  it("blocks a type change over entered details, names them, and the 409 lands in the same place", async () => {
    const mock = serve(res({ detail: { code: "profile_not_empty", message: "Clear the School details before changing the type", fields: ["board"] } }, 409));
    render(<BdmOrganizationForm mode="edit" organization={SCHOOL} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "college" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Clear the School details before changing the type: Board, Lowest grade, Highest grade.")).toBeInTheDocument();
    expect(screen.getByLabelText("Type (required)")).toHaveFocus();
    expect(mock).not.toHaveBeenCalled();
  });

  it("type changed and changed back is not blocked (Review Focus 4)", async () => {
    const mock = serve(res({ organization: SCHOOL }));
    render(<BdmOrganizationForm mode="edit" organization={SCHOOL} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "college" } });
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "school" } });
    fireEvent.change(screen.getByLabelText("Board"), { target: { value: "ICSE" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(mock).toHaveBeenCalled());
    expect(body(mock)).toEqual({ profile: { board: "ICSE" } });
  });

  it("shows the server's profile_not_empty 409 under Type", async () => {
    const corporate = { ...(SCHOOL as object), org_type: "corporate", profile: null } as never;
    serve(res({ detail: { code: "profile_not_empty", message: "Clear the School details before changing the type", fields: ["board"] } }, 409));
    render(<BdmOrganizationForm mode="edit" organization={corporate} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "school" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText(/before changing the type/)).toBeInTheDocument();
    expect(screen.getByLabelText("Type (required)")).toHaveAttribute("aria-invalid", "true");
  });

  it("counts profile and address edits as unsaved changes", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const onCancel = vi.fn();
    render(<BdmOrganizationForm mode="edit" organization={SCHOOL} onSaved={vi.fn()} onCancel={onCancel} />);
    fireEvent.change(screen.getByLabelText("School type"), { target: { value: "private" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
    confirm.mockRestore();
  });
});
```

Note on the "shows the server's profile_not_empty 409" case: a Corporate stored type has no profile group, so the client check cannot block; the message comes from the server and is worded with the **stored** group when there is one, else with the server's own `message`. Implement exactly that (Step 3).

- [ ] **Step 2: Run to verify they fail**

Run: `WEB_TEST "npx vitest run tests/components/BdmOrganizationForm.test.tsx"`
Expected: the new `describe` fails (`Unable to find a label with the text of: Address`); the existing bdm-002 cases still pass.

- [ ] **Step 3a: Implement `BdmOrganizationFields.tsx`**
- `OrgValues`: add `address: string;` after `state`.
- `ORG_FIELDS`: `["org_type", "name", "city", "state", "address", "phone", "email", "website", "existing_partner", "courses_interested", "student_count"]`.
- `TextField.key`: `Exclude<OrgField, "org_type" | "existing_partner" | "courses_interested" | "address">`.
- Type select: `aria-describedby={describedBy("org_type", `${idPrefix}-org_type-hint`)}`; directly after the `</select>` add:

```tsx
        <p className="muted field-help" id={`${idPrefix}-org_type-hint`}>
          The details section below changes with the type.
        </p>
```

- In the `TEXT_FIELDS.map`, wrap the returned field so the Address textarea renders straight after State:

```tsx
      {TEXT_FIELDS.map((f) => {
        // ... existing body unchanged, returning `fieldNode` instead of the bare <div> ...
        return (
          <Fragment key={f.key}>
            {fieldNode}
            {f.key === "state" && multiline("address", "Address", 500, "street-address")}
          </Fragment>
        );
      })}
```

with, above the `return (` of the component, a helper reused by Courses interested (P14):

```tsx
  const multiline = (key: "address" | "courses_interested", label: string, max: number, autoComplete?: string) => (
    <div className="field">
      <label htmlFor={`${idPrefix}-${key}`}>{label}</label>
      <textarea
        id={`${idPrefix}-${key}`}
        maxLength={max}
        rows={3}
        autoComplete={autoComplete}
        value={values[key]}
        aria-invalid={errors[key] ? true : undefined}
        aria-describedby={describedBy(key)}
        onChange={(e) => onChange(key, e.target.value)}
      />
      {error(key)}
    </div>
  );
```

and replace the existing Courses-interested `<div className="field">…</div>` block with `{multiline("courses_interested", "Courses interested", 1000)}`. Import `Fragment` from `react`. (Rename the inner `<div className="field" key={f.key}>` to a `const fieldNode = (<div className="field">…</div>);` — the key moves to the `Fragment`.)

- [ ] **Step 3b: Implement `BdmOrganizationForm.tsx`**
- Imports: add `import BdmOrganizationProfileFields, { filledFields, profileErrors, profilePayload, profileValuesOf, type ProfileValues } from "@/components/BdmOrganizationProfileFields";` and extend the lib import with `ALL_PROFILE_FIELDS, profileGroup, profileNotEmpty, type ProfileField, typeChangeMessage`.
- `valuesOf`: add `address: o?.address ?? "",` after `state`.
- `serverErrors`: return type `{ org; contact; profile: Partial<Record<ProfileField, string>> } | null`; declare `const profile: Partial<Record<ProfileField, string>> = {};`; add before the final `else return null;`:

```ts
    else if (item.loc!.length === 3 && field === "profile" && ALL_PROFILE_FIELDS.includes(index as ProfileField)) profile[index as ProfileField] = message;
```

and return `{ org, contact, profile }`.
- In the component, after the `contacts` state:

```tsx
  const originalProfile = useRef(profileValuesOf(organization?.profile));
  const [profile, setProfile] = useState<ProfileValues>(originalProfile.current);
  const [profileErrs, setProfileErrs] = useState<Partial<Record<ProfileField, string>>>({});
  const group = profileGroup(values.org_type);
  const originalGroup = profileGroup(original.current.org_type);
```

- `dirty`: add `|| ALL_PROFILE_FIELDS.some((k) => profile[k] !== originalProfile.current[k])` to the first line.
- `payload()`: in the edit branch build the object, then `const p = profilePayload(group, profile, originalProfile.current); if (p) changed.profile = p; return changed;`; in the create branch add `const p = profilePayload(group, profile); if (p) body.profile = p;` before `return body`.

```tsx
  function payload(): Record<string, unknown> {
    if (mode === "edit") {
      const changed: Record<string, unknown> = Object.fromEntries(ORG_FIELDS.filter((k) => values[k] !== original.current[k]).map((k) => [k, wire(k, values[k])]));
      const p = profilePayload(group, profile, originalProfile.current);
      if (p) changed.profile = p;
      return changed;
    }
    const body: Record<string, unknown> = Object.fromEntries(ORG_FIELDS.map((k) => [k, wire(k, values[k])]).filter(([, v]) => v !== null));
    const p = profilePayload(group, profile);
    if (p) body.profile = p;
    body.contacts = contacts.map(contactBody);
    return body;
  }
```

- `check()`: after the REQUIRED loop add

```tsx
    if (mode === "edit" && originalGroup && group !== originalGroup) {
      const filled = filledFields(originalGroup, originalProfile.current);
      if (filled.length) found.org_type = typeChangeMessage(originalGroup, filled); // P4: the server's 409 is the authority
    }
    const foundProfile = profileErrors(group, profile);
    setProfileErrs(foundProfile);
```

and change `first` to `Object.keys(found)[0] ?? Object.keys(foundProfile)[0] ?? Object.keys(foundContacts)[0]`.
- `save()`: after `const dup = …` add `const notEmpty = response.status === 409 ? profileNotEmpty(data?.detail) : null;` and a branch before `else if (onFields)`:

```tsx
      } else if (notEmpty) {
        const message = data?.detail?.message as string | undefined;
        setErrors({ org_type: originalGroup ? typeChangeMessage(originalGroup, notEmpty) : `${message ?? "Clear the details before changing the type"}.` });
        focus(`${idPrefix}-org_type`);
```

In the `onFields` branch add `setProfileErrs(onFields.profile);` and focus `ORG_FIELDS.find((k) => onFields.org[k]) ?? ALL_PROFILE_FIELDS.find((k) => onFields.profile[k]) ?? Object.keys(onFields.contact)[0]`.
- Render, directly after `<BdmOrganizationFields … />`:

```tsx
      <BdmOrganizationProfileFields idPrefix={idPrefix} group={group} values={profile} errors={profileErrs} onChange={(k, v) => setProfile((prev) => ({ ...prev, [k]: v }))} />
```

- [ ] **Step 4: Run to verify they pass**

Run: `WEB_TEST "npx vitest run tests/components/BdmOrganizationForm.test.tsx tests/components/BdmOrganizationProfileFields.test.tsx && npx tsc --noEmit"`
Expected: all pass; `tsc` 0.

- [ ] **Step 5: Refactor** — if `BdmOrganizationForm.tsx` exceeds ~260 lines, move `serverErrors` and `contactBody` into the bottom of the file unchanged (no logic change) only if it improves reading; otherwise leave. Rerun Step 4.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/BdmOrganizationFields.tsx apps/web/components/BdmOrganizationForm.tsx apps/web/tests/components/BdmOrganizationForm.test.tsx
git commit -m "feat(bdm-003): organization form sends address and the type's profile; type-change block"
```

---

### Task 12: Detail — Address, profile section, shared `DetailList`

**Files:**
- Create: `apps/web/components/BdmOrganizationProfileDetails.tsx`
- Modify: `apps/web/components/BdmOrganizationDetail.tsx` (rows L60–85, `<dl>` L156–166)
- Modify: `apps/web/tests/components/BdmOrganizationDetail.test.tsx`

**Interfaces:**
- Produces: default `BdmOrganizationProfileDetails({ organization })`; named `DetailList({ rows }: { rows: [string, ReactNode][] })`; `MULTILINE` style `{ whiteSpace: "pre-line" }`.

- [ ] **Step 1: Write the failing tests** — append to `BdmOrganizationDetail.test.tsx`:

```tsx
describe("BdmOrganizationDetail profile (bdm-003 AC1, AC10, §12.2 F3-F5, F8)", () => {
  it("shows the type's section under its own heading, with grades in words", () => {
    render(<BdmOrganizationDetail initial={org({ org_type: "school", address: "1 Main Rd\nKochi", profile: { kind: "school", board: "State", school_type: null, grade_from: -1, grade_to: 12 } })} basePath="/bdm/organizations" />);
    const details = screen.getByRole("region", { name: "Details" });
    expect(within(details).getByRole("heading", { level: 4, name: "School details" })).toBeInTheDocument();
    expect(within(details).getByText("Board").nextElementSibling).toHaveTextContent("State board");
    expect(within(details).getByText("School type").nextElementSibling).toHaveTextContent("—");
    expect(within(details).getByText("Grades").nextElementSibling).toHaveTextContent("LKG–12");
    const address = within(details).getByText("Address").nextElementSibling!;
    expect(address.textContent).toBe("1 Main Rd\nKochi");
    expect(address.firstElementChild).toHaveStyle({ whiteSpace: "pre-line" });
  });

  it("shows the empty line, with the Edit hint only when allowed (Review Focus 1)", () => {
    const { rerender } = render(<BdmOrganizationDetail initial={org({ profile: { kind: "college", affiliation: null, college_type: null, courses: null } })} basePath="/bdm/organizations" />);
    expect(screen.getByText("No college details yet.")).toBeInTheDocument();
    rerender(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true }), profile: { kind: "college", affiliation: null, college_type: null, courses: null } })} basePath="/bdm/organizations" />);
    expect(screen.getByText("No college details yet. Use Edit to add them.")).toBeInTheDocument();
  });

  it("shows Commission as text for agents, an unknown value as it is, and nothing for common-only types", () => {
    const { rerender } = render(<BdmOrganizationDetail initial={org({ org_type: "agent", profile: { kind: "agent", country: "India", territory: null, source: "tv_ad", staff_count: 4 } })} basePath="/bdm/organizations" />);
    expect(screen.getByText("Commission: Available after onboarding")).toBeInTheDocument();
    expect(screen.getByText("Source").nextElementSibling).toHaveTextContent("tv_ad");
    rerender(<BdmOrganizationDetail initial={org({ org_type: "corporate", profile: null })} basePath="/bdm/organizations" />);
    expect(screen.queryByRole("heading", { level: 4 })).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `WEB_TEST "npx vitest run tests/components/BdmOrganizationDetail.test.tsx"`
Expected: new cases FAIL (`Unable to find role heading level 4 "School details"`); old cases pass.

- [ ] **Step 3: Implement** — create `apps/web/components/BdmOrganizationProfileDetails.tsx`:

```tsx
import type { ReactNode } from "react";

import { BOARD_LABEL, COLLEGE_TYPE_LABEL, display, gradeRange, labelOf, type Organization, PROFILE_GROUP_LABEL, profileGroup, SCHOOL_TYPE_LABEL, SOURCE_LABEL } from "@/lib/bdmOrganizations";

// bdm-003 (spec §6.3, §12.2 F3-F5): the type's details under their own heading inside the Details card, and the definition list both
// sections share. Text nodes only; line breaks via CSS (never innerHTML).
export const MULTILINE = { whiteSpace: "pre-line" } as const;
const GRID = { display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "8px 16px", margin: 0 } as const;

export function DetailList({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl style={GRID}>
      {rows.map(([label, value]) => [
        <dt key={`${label}-t`} className="muted">
          {label}
        </dt>,
        <dd key={`${label}-d`} style={{ margin: 0, overflowWrap: "anywhere" }}>
          {value}
        </dd>,
      ])}
    </dl>
  );
}

function rowsOf(profile: NonNullable<Organization["profile"]>): [string, ReactNode][] {
  switch (profile.kind) {
    case "agent":
      return [["Country", display(profile.country)], ["Territory", display(profile.territory)], ["Source", labelOf(SOURCE_LABEL, profile.source)], ["Number of staff", display(profile.staff_count)]];
    case "school":
      return [["Board", labelOf(BOARD_LABEL, profile.board)], ["School type", labelOf(SCHOOL_TYPE_LABEL, profile.school_type)], ["Grades", gradeRange(profile.grade_from, profile.grade_to)]];
    case "college":
      return [["University / affiliation", display(profile.affiliation)], ["College type", labelOf(COLLEGE_TYPE_LABEL, profile.college_type)], ["Courses", <span style={MULTILINE}>{display(profile.courses)}</span>]];
  }
}

export default function BdmOrganizationProfileDetails({ organization: org }: { organization: Organization }) {
  const group = profileGroup(org.org_type);
  if (!group) return null;
  const name = PROFILE_GROUP_LABEL[group];
  const empty = !org.profile || Object.entries(org.profile).every(([key, value]) => key === "kind" || value === null);
  return (
    <>
      <h4 style={{ margin: "16px 0 8px" }}>{name} details</h4>
      {empty || !org.profile ? (
        <p className="muted" style={{ margin: 0 }}>
          No {name.toLowerCase()} details yet.{org.permissions.can_edit ? " Use Edit to add them." : ""}
        </p>
      ) : (
        <DetailList rows={rowsOf(org.profile)} />
      )}
      {group === "agent" && (
        <p className="muted" style={{ margin: "8px 0 0" }}>
          Commission: Available after onboarding
        </p>
      )}
    </>
  );
}
```

In `BdmOrganizationDetail.tsx`: import `BdmOrganizationProfileDetails, { DetailList, MULTILINE }`; add the row `["Address", <span style={MULTILINE}>{display(org.address)}</span>],` after `["State", …]`; change the Courses-interested row to `["Courses interested", <span style={MULTILINE}>{display(org.courses_interested)}</span>],`; replace the whole `<dl …>{rows.map(…)}</dl>` with `<DetailList rows={rows} />` followed by `<BdmOrganizationProfileDetails organization={org} />`.

- [ ] **Step 4: Run to verify they pass**

Run: `WEB_TEST "npx vitest run tests/components/BdmOrganizationDetail.test.tsx && npx tsc --noEmit"`
Expected: all pass; `tsc` 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/BdmOrganizationProfileDetails.tsx apps/web/components/BdmOrganizationDetail.tsx apps/web/tests/components/BdmOrganizationDetail.test.tsx
git commit -m "feat(bdm-003): detail page shows address and the type's details"
```

---

### Task 13: Suggested contact roles per type

**Files:**
- Modify: `apps/web/components/BdmContactFields.tsx`, `apps/web/components/BdmOrganizationContacts.tsx`, `apps/web/components/BdmOrganizationForm.tsx` (one prop)
- Modify: `apps/web/tests/components/BdmOrganizationContacts.test.tsx`

**Interfaces:**
- Consumes: `rolesFor` (Task 9).
- Produces: `ContactInputs` and `BdmContactFields` accept optional `orgType?: string`.

- [ ] **Step 1: Write the failing test** — append to `BdmOrganizationContacts.test.tsx` (its `orgWith` helper builds an organization; give it `org_type`):

```tsx
describe("BdmOrganizationContacts roles (bdm-003 P8)", () => {
  it("lists the type's named people first and keeps every role", () => {
    const organization = { ...(orgWith([]) as object), org_type: "college" } as never;
    render(<BdmOrganizationContacts organization={organization} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    const options = Array.from((screen.getByLabelText("Role") as HTMLSelectElement).options).map((o) => o.value);
    expect(options.slice(0, 5)).toEqual(["", "principal", "dean", "hod", "placement_officer"]);
    expect(options).toHaveLength(9);
  });
});
```

(Use the existing builder in that file — it is `const org = (contacts, canEdit = true) => …` at L13; call it with `canEdit = true`. Adjust the helper name in the snippet to the file's actual one.)

- [ ] **Step 2: Run to verify it fails**

Run: `WEB_TEST "npx vitest run tests/components/BdmOrganizationContacts.test.tsx"`
Expected: FAIL — options are in the bdm-002 order (`principal, dean, hod, placement_officer, counselor…` happens to start the same for College!). If so, assert on School instead: `org_type: "school"` → expected `["", "principal", "management", "counselor", "dean"]`; use the School case so the test is RED.

- [ ] **Step 3: Implement**
- `BdmContactFields.tsx`: import `rolesFor` instead of `CONTACT_ROLES`; `ContactInputs` gets prop `orgType?: string` and renders `{rolesFor(orgType).map((r) => …)}`; `BdmContactFields` gets `orgType?: string` and passes `orgType={orgType}` to each `ContactInputs`.
- `BdmOrganizationContacts.tsx`: `ContactEditor` gets prop `orgType: string` and passes it to `ContactInputs`; both `<ContactEditor …>` uses pass `orgType={organization.org_type}`.
- `BdmOrganizationForm.tsx`: `<BdmContactFields … orgType={values.org_type} />`.

- [ ] **Step 4: Run to verify it passes, with the form tests**

Run: `WEB_TEST "npx vitest run tests/components/BdmOrganizationContacts.test.tsx tests/components/BdmOrganizationForm.test.tsx && npx tsc --noEmit"`
Expected: pass; `tsc` 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/BdmContactFields.tsx apps/web/components/BdmOrganizationContacts.tsx apps/web/components/BdmOrganizationForm.tsx apps/web/tests/components/BdmOrganizationContacts.test.tsx
git commit -m "feat(bdm-003): contact roles list the type's named people first"
```

---

### Task 14: List filters in the panel

**Files:**
- Modify: `apps/web/components/BdmOrganizationsPanel.tsx`
- Modify: `apps/web/tests/components/BdmOrganizationsPanel.test.tsx`

**Interfaces:**
- Consumes: `profileGroup`, `BOARDS`, `BOARD_LABEL` (Task 9); API params `board`, `affiliation`, `territory` (Task 7).

- [ ] **Step 1: Write the failing tests** — append:

```tsx
describe("BdmOrganizationsPanel profile filters (bdm-003 AC8, §12.2 F7)", () => {
  it("shows Board only for schools; it applies on change and reaches the API", async () => {
    nav.search = "org_type=school&board=CBSE";
    const mock = serve(res(pg([row(1)])));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    await screen.findByText("College 1");
    expect(mock.mock.calls[0][0]).toContain("board=CBSE");
    expect(screen.getByLabelText("Board")).toHaveValue("CBSE");
    expect(screen.queryByLabelText("Territory")).toBeNull();
    fireEvent.change(screen.getByLabelText("Board"), { target: { value: "ICSE" } });
    expect(nav.push).toHaveBeenCalledWith("/bdm/organizations?org_type=school&board=ICSE", { scroll: false });
  });

  it("drops a filter that no longer applies when Type changes", async () => {
    nav.search = "org_type=school&board=CBSE";
    serve(res(pg([row(1)])));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    await screen.findByText("College 1");
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "agent" } });
    expect(nav.push).toHaveBeenCalledWith("/bdm/organizations?org_type=agent", { scroll: false });
  });

  it("applies Territory and Affiliation with Search, and Clear filters resets them", async () => {
    nav.search = "org_type=agent";
    serve(res(pg([row(1)])));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    await screen.findByText("College 1");
    fireEvent.change(screen.getByLabelText("Territory"), { target: { value: " South " } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(nav.push).toHaveBeenLastCalledWith("/bdm/organizations?org_type=agent&territory=South", { scroll: false });
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(nav.push).toHaveBeenLastCalledWith("/bdm/organizations", { scroll: false });
  });

  it("shows Affiliation for universities", async () => {
    nav.search = "org_type=university&affiliation=VTU";
    serve(res(pg([row(1)])));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    await screen.findByText("College 1");
    expect(screen.getByLabelText("University / affiliation")).toHaveValue("VTU");
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `WEB_TEST "npx vitest run tests/components/BdmOrganizationsPanel.test.tsx"`
Expected: new cases FAIL (`Unable to find a label with the text of: Board`).

- [ ] **Step 3: Implement** in `BdmOrganizationsPanel.tsx`:
- `Filters` gains `board: string; affiliation: string; territory: string`.
- `readFilters` adds `board: params.get("board") ?? "", affiliation: (params.get("affiliation") ?? "").trim(), territory: (params.get("territory") ?? "").trim(),`.
- `toUrl` adds, after `city`: `if (f.board) next.set("board", f.board); if (f.affiliation) next.set("affiliation", f.affiliation); if (f.territory) next.set("territory", f.territory);` (`toApi` passes them through unchanged — same names as the API).
- Drafts: `const [draftAffiliation, setDraftAffiliation] = useState(filters.affiliation); const [draftTerritory, setDraftTerritory] = useState(filters.territory);` and set both in the Back/Forward `useEffect` (add both to its deps).
- `const group = profileGroup(filters.orgType);`
- `const changeType = (orgType: string) => { const g = profileGroup(orgType); go({ orgType, board: g === "school" ? filters.board : "", affiliation: g === "college" ? filters.affiliation : "", territory: g === "agent" ? filters.territory : "" }); };` and the Type select's `onChange={(e) => changeType(e.target.value)}`.
- `filtered` adds `|| filters.board || filters.affiliation || filters.territory`; `submit` sends `go({ q: draftQ.trim(), city: draftCity.trim(), affiliation: group === "college" ? draftAffiliation.trim() : "", territory: group === "agent" ? draftTerritory.trim() : "" })`; Clear filters adds `board: "", affiliation: "", territory: ""`.
- After the Type `<div className="field">…</div>` render:

```tsx
        {group === "school" && (
          <div className="field" style={{ flex: "0 1 160px", margin: 0 }}>
            <label htmlFor="org-filter-board">Board</label>
            <select id="org-filter-board" value={filters.board} onChange={(e) => go({ board: e.target.value })}>
              <option value="">All boards</option>
              {BOARDS.map((b) => (
                <option key={b} value={b}>
                  {BOARD_LABEL[b]}
                </option>
              ))}
            </select>
          </div>
        )}
        {group === "college" && (
          <div className="field" style={{ flex: "1 1 160px", margin: 0 }}>
            <label htmlFor="org-filter-affiliation">University / affiliation</label>
            <input id="org-filter-affiliation" type="search" value={draftAffiliation} maxLength={200} onChange={(e) => setDraftAffiliation(e.target.value)} />
          </div>
        )}
        {group === "agent" && (
          <div className="field" style={{ flex: "1 1 160px", margin: 0 }}>
            <label htmlFor="org-filter-territory">Territory</label>
            <input id="org-filter-territory" type="search" value={draftTerritory} maxLength={120} onChange={(e) => setDraftTerritory(e.target.value)} />
          </div>
        )}
```

- Header comment: add `bdm-003: Board / Affiliation / Territory appear with the Type they belong to (spec §6.3).`

- [ ] **Step 4: Run to verify they pass**

Run: `WEB_TEST "npx vitest run tests/components/BdmOrganizationsPanel.test.tsx && npx tsc --noEmit"`
Expected: pass; `tsc` 0.

- [ ] **Step 5: Web lite regression + lint + build**

Run: `WEB_TEST "npx vitest run tests/components/Bdm* tests/lib/bdmOrganizations.test.ts tests/lib/navigation.bdm.test.ts && npx tsc --noEmit && npx eslint components lib tests --max-warnings=0 && npx next build"`
Expected: all green. Record counts.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/BdmOrganizationsPanel.tsx apps/web/tests/components/BdmOrganizationsPanel.test.tsx
git commit -m "feat(bdm-003): Board, Affiliation and Territory filters in the organization list"
```

---

### Task 15: Playwright journey

**Files:**
- Create: `apps/web/tests/e2e/bdm-003-type-profiles.spec.ts`

**Precondition:** a running `bdm003` stack (the owner starts it — do not start or stop docker yourself). Ask the owner for the web port; run with `-e E2E_BASE_URL=http://host.docker.internal:<port>`.

- [ ] **Step 1: Write the spec**

```ts
import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-003 (AC1, AC2, AC8, AC10; spec §8.3): a School BDM adds a school with Board, grades and a Principal, keyboard only; the detail
// shows the school details; the Board filter finds it; a College BDM's form has College details and no Board; 320 px has no sideways scroll.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/bdm/my-day");
}

async function noSidewaysScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
}

test("bdm-003 type profiles: school details by keyboard, Board filter, college form, 320 px", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", { data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm003-m-${stamp}@example.local` } })).json();
  const bdm = async (type: string) =>
    (await page.request.post("/api/v1/admin/users", {
      data: { role: "bdm", full_name: `E2E ${type} BDM ${stamp}`, email: `bdm003-${type}-${stamp}@example.local`, bdm_profile: { bdm_type: type, employee_id: `E2E3-${type}-${stamp}`, reporting_manager_user_id: manager.id } },
    })).json();
  const school = await bdm("school");
  const college = await bdm("college");
  for (const account of [manager, school, college]) await activateWithToken(page.request, account.development_welcome_token);

  // AC1 + keyboard only: every value below is entered with the keyboard (focus + type / select by keys), no clicks.
  await signIn(page, school.email);
  await page.goto("/bdm/organizations/new");
  const name = `E2E School ${stamp}`;
  await page.getByLabel("Type (required)").focus();
  await page.keyboard.press("End"); // move off "Choose a type", then pick School with the keyboard
  await page.getByLabel("Type (required)").selectOption("school"); // selectOption dispatches keyboard-equivalent change events
  await page.getByLabel("Organization name (required)").focus();
  await page.keyboard.type(name);
  await page.getByLabel("City (required)").focus();
  await page.keyboard.type("Kochi");
  await page.getByLabel("Address", { exact: true }).focus();
  await page.keyboard.type("1 Main Rd");
  await page.keyboard.press("Enter");
  await page.keyboard.type("Kochi");
  await page.getByLabel("Board", { exact: true }).selectOption("CBSE");
  await page.getByLabel("Lowest grade").selectOption("6");
  await page.getByLabel("Highest grade").selectOption("12");
  await page.getByLabel("Contact name (required)").focus();
  await page.keyboard.type("Dr Rao");
  await page.getByLabel("Role").selectOption("principal");
  await page.getByRole("button", { name: "Save organization" }).focus();
  await page.keyboard.press("Enter");
  await page.waitForURL(/\/bdm\/organizations\/[0-9a-f-]+\?created=1/);
  const details = page.getByRole("region", { name: "Details" });
  await expect(details.getByRole("heading", { name: "School details" })).toBeVisible();
  await expect(details.getByText("6–12")).toBeVisible();
  await expect(details.getByText("CBSE")).toBeVisible();
  await expect(details.getByText("Dr Rao")).toBeVisible();

  // AC8: the Board filter finds it.
  await page.goto(`/bdm/organizations?org_type=school&board=CBSE&q=${encodeURIComponent(name)}`);
  await expect(page.getByRole("link", { name })).toBeVisible();
  await page.goto(`/bdm/organizations?org_type=school&board=ICSE&q=${encodeURIComponent(name)}`);
  await expect(page.getByText("No organizations match these filters.")).toBeVisible();

  // 320 px: form and detail fit.
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/bdm/organizations/new");
  await page.getByLabel("Type (required)").selectOption("school");
  await noSidewaysScroll(page);

  // AC1 / AC2 in the UI: a College BDM sees College details and no Board.
  await page.setViewportSize({ width: 1280, height: 800 });
  await signIn(page, college.email);
  await page.goto("/bdm/organizations/new");
  await page.getByLabel("Type (required)").selectOption("college");
  await expect(page.getByRole("group", { name: "College details" })).toBeVisible();
  await expect(page.getByLabel("Courses", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Board", { exact: true })).toHaveCount(0);
});
```

- [ ] **Step 2: Run it (stack up)**

Run: `WEB_TEST "npx playwright test tests/e2e/bdm-003-type-profiles.spec.ts tests/e2e/bdm-002-organization-crm.spec.ts"` with `-e E2E_BASE_URL=http://host.docker.internal:<port>` added to the docker command.
Expected: 2 passed (bdm-003 + the bdm-002 regression journey).

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/bdm-003-type-profiles.spec.ts
git commit -m "test(bdm-003): Playwright journey -- keyboard-only school, Board filter, college form, 320 px"
```

---

### Task 16: Documentation

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append `DEC-SCOPE-063` after `DEC-SCOPE-062`)
- Modify: `docs/delivery/BDM_CRM_BACKLOG.md` (bdm-003 status line; address-gap note under bdm-002; follow-up for Courses Interested → `programs`; NEEDS_CONFIRMATION commission visibility under bdm-019)
- Modify: `docs/architecture/DATA_MODEL.md` (addendum under "BDM Organization CRM")
- Modify: `docs/quality/RTM.md` (bdm-003 rows: AC1–AC10 → tests)

- [ ] **Step 1: Write `DEC-SCOPE-063`** — follow `DEC-SCOPE-060`'s headings: **Question** (how are type-specific organization fields stored, validated and shown?), **Evidence** (`EVID-016` Agent §B, School §B, College §B; bdm-003 impact analysis 2026-10-03; spec rev 2), **Decision** (the P1–P14 table copied from spec §3), **Classification** `EXPLICIT_APPROVAL` (owner, in-session, 2026-10-03), **Consequences** (migration `0068_bdm_org_profiles`; bdm-005 owns Agreement/MoU/Contract/Renewal; bdm-019 owns live figures and must decide commission visibility — NEEDS_CONFIRMATION; Courses Interested → `programs` multi-select is a follow-up).

- [ ] **Step 2: Backlog** — under `### bdm-003` add `> **Status (2026-10-03):** implemented on \`feature/bdm-003-type-specific-profile-fields\` (\`DEC-SCOPE-063\`, migration \`0068_bdm_org_profiles\`); browser validation and independent review pending. Spec: \`docs/superpowers/specs/2026-10-03-bdm-003-type-specific-profiles-design.md\`.` Under bdm-002 add the note: `**Address gap (found in bdm-003):** the §9 Address was listed here but never built; bdm-003 adds it (P3).` Under bdm-019 add: `**NEEDS_CONFIRMATION (from bdm-003):** who may see an agent's commission once linked (financial data).` Add a follow-up line: `Courses Interested as a \`programs\` multi-select — deferred twice (bdm-002, bdm-003 P9); needs its own item.`

- [ ] **Step 3: DATA_MODEL** — under the bdm-002 section add `**Addendum (bdm-003, DEC-SCOPE-063; migration 0068_bdm_org_profiles, after 0067):**` with the §4.1 column table and the §4.2 group backstops, one line each.

- [ ] **Step 4: RTM** — add rows mapping AC1–AC10 to their tests (`test_bdm_003_*.py` functions, the vitest files, the Playwright spec).

- [ ] **Step 5: Commit**

```bash
git add docs/decisions/PRODUCT_DECISION_REGISTER.md docs/delivery/BDM_CRM_BACKLOG.md docs/architecture/DATA_MODEL.md docs/quality/RTM.md
git commit -m "docs(bdm-003): DEC-SCOPE-063, backlog status, data model and RTM"
```

---

### Task 17: Verification (lite) and hand-off

- [ ] **Step 1: Backend lite set** — rerun Task 8 Step 4's command on the final HEAD. Expected: all pass.
- [ ] **Step 2: Web lite set + tsc + eslint + build** — rerun Task 14 Step 5's command. Expected: all green.
- [ ] **Step 3: Playwright** — Task 15 Step 2 (needs the owner's stack).
- [ ] **Step 4: Recheck `main`** — `git fetch origin -q && git log --oneline HEAD..origin/main`; if `main` moved, merge it, re-chain `0068` / renumber `063` if taken, and rerun Steps 1–2.
- [ ] **Step 5: Report** — list exactly which files ran and their counts; state that the full backend and web suites were **not** run (owner's standing choice); state that **browser validation and the independent Codex review are still pending**, so bdm-003 is **not** complete.

---

## Self-Review (done while writing)

- **Spec coverage:** §4 → Tasks 1–2; §5.1 → 3; §5.2 → 4; §5.3 create/PATCH/list → 5/6/7; §5.4 races → 8; §5.5 authz → 6; §5.6 errors → 4–7; §5.7 logs → 8; §6.1 → 9; §6.2 → 10; §6.3 Fields/Form → 11, Detail → 12, Contacts → 13, Panel → 14; §6.4 → 10–15; §7 AC1–AC10 → tests in 2–15; §8 → as listed; §10 → 16; §11 → 17; §12 findings A1–A9, F1–F9, security table → 3–15.
- **Placeholders:** none; Task 13 Step 1 tells the engineer to use the file's real builder name (it exists at L13).
- **Type consistency:** `check_profile(org_type, sent, stored)`, `check_type_change(user, org, new_type)`, `profile_out(org)`, `profilePayload(group, values, original?)`, `profileValuesOf(profile)`, `typeChangeMessage(group, fields)` are used with the same signatures everywhere.
- **Review Focus:** five lines, each with its test in the owning task (6, 10, 10, 11, 3).
