# bdm-004 Organization Pipelines — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each BDM module (Agent, School, College) has its own 14-step pipeline; the assigned BDM (or super_admin) moves an
organization between manual stages, marks it Lost or revives it, every change is recorded as a history row and an audit row,
and BDMs / managers see per-stage counts in their scope.

**Architecture:** Spec Approach A. A constants-only catalogue (`app/bdm_stages.py`) feeds the model CHECK, the migration parity
test, the service and the schemas. `bdm_organizations` gains `pipeline_stage`, `lost_at`, `lost_reason`; a new append-only
`bdm_pipeline_events` table holds history (migration `0072_bdm_pipeline`). A new service (`services/bdm_pipeline.py`, never
commits) and router (`api/bdm_pipeline.py`, one commit per write) reuse bdm-002's `load_scoped` / `require` / `audit` / `log`.
The web adds `lib/bdmPipeline.ts`, a pipeline section + history on both organization detail pages, and two server-rendered
pipeline pages.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, PostgreSQL; Next.js 15 App Router, React 19, Vitest,
Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-05-bdm-004-organization-pipelines-design.md` (`DEC-SCOPE-070`). Read it with this plan.

## Global Constraints

- Branch `feature/bdm-004-pipeline-stages` (from `origin/main` @ `2e057b3a`); migration `0072_bdm_pipeline`
  (down_revision `0071_bdm_activities`); decision `DEC-SCOPE-070`. Before Task 1 and before the PR: `git fetch origin` and
  check `main` for a newer migration / DEC; if one landed, renumber both.
- No new dependency (backend or web).
- Stored stages are manual stages only; every organization starts at `prospect`; no history row on create or backfill.
- Who writes: the organization's assigned BDM and `super_admin` (`require(user, org, "can_edit", route)`); `bdm_manager` reads
  only; other roles 403. Out of scope → 404 "Organization not found" (`load_scoped`).
- Error order on every pipeline write: 401 → 403 role (`caller_scope`) → 404 scope → 403 `can_edit` (logged by `require`) →
  409 archived "Restore this organization first" → 409 lost / not lost → 409 `stage_changed` → 422 field errors.
- 409 bodies are `{"detail": {"message", "code", ...}}`; field 422s are FastAPI's list with `loc` `["body", "<field>"]`.
- Note / reason: trimmed, ≤ 500 characters, `\r\n`/`\r` → `\n` before the length check, `\n \r \t` allowed, other control
  characters refused; a blank note is `null`; a blank reason is "Reason is required".
- One transaction per write: `load_scoped(lock=True)` → checks → mutate + event + audit → `commit` → `log`. Services never
  commit. Only the organization row is locked.
- Audit actions `bdm_organization.stage_changed|lost|revived` (`entity_type="bdm_organization"`). Metadata holds stage keys and
  booleans only — never note or reason text, in audit rows or logs.
- Existing contracts unchanged: list rows (`BdmOrganizationRow`), the four permission keys, every existing route and status
  code. Only the organization detail gains `pipeline`.
- Lists are `{items, total, limit, offset}`; `LIMIT` (50, ≤ 100) / `OFFSET` from `app/api/bdm.py`.
- Tests: only the lite set (below). Never run the full backend or web suites (the owner runs them separately).

## Review Focus

1. **A double-clicked or retried Move** → the second request is 409 `stage_changed` with `current_stage` equal to the chosen stage;
   the UI must show the move as done, not as an error. Task 10 test `a retried move that already landed reads as done`.
2. **The organization is reassigned while its page is open** → Move answers 403 "Only the assigned BDM can edit this
   organization"; the form keeps the choice and note. Task 10 test `a refusal keeps the choice and note`.
3. **A hand-edited pipeline address (`?stage=<script>` or another type's key)** → the page shows "That filter isn't valid" with a
   reset link instead of an error page. Task 11 test `an invalid stage in the address shows a reset link`.
4. **A manager whose address names a type none of their BDMs has** → the page falls back to the first type in the team. Task 11
   test `falls back to the team's first type`.
5. **A note pasted from Windows (`\r\n`)** at exactly 500 visible characters → accepted (the limit counts the stored form).
   Task 3 test `test_crlf_counts_as_one_character`.

## How to run tests (worktree)

Run from the worktree root in Git Bash. `<P>` = space-separated test paths. The first run builds the images.

Backend:

```bash
docker compose -p bdm004 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "C:/Users/kunam/Documents/project/trainwebsite/.claude/worktrees/bdm-004/apps/api:/app" \
  api-test sh -c "alembic upgrade head && python -m pytest -q <P>"
```

Web (vitest / tsc / eslint; the worktree has no node_modules):

```bash
MSYS_NO_PATHCONV=1 docker compose -p bdm004 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps \
  -v "C:/Users/kunam/Documents/project/trainwebsite/.claude/worktrees/bdm-004/apps/web:/app" \
  -v /app/node_modules web-test sh -c "npx vitest run <paths>"
```

If the test DB carries a stale alembic stamp from another branch: `alembic stamp --purge 0071_bdm_activities` then
`alembic upgrade head` (inside the same `api-test` command).

LITE (backend) = `tests/test_bdm_004_*.py tests/test_bdm_002_*.py tests/test_bdm_003_*.py tests/test_bdm_006_*.py tests/test_bdm_009_*.py`
LITE (web) = `tests/lib/bdmPipeline.test.ts tests/lib/navigation.bdm.test.ts tests/components/BdmOrganization*.test.tsx tests/components/BdmStageHistory.test.tsx tests/components/BdmPipeline*.test.tsx tests/components/BdmActivity*.test.tsx`

---

### Task 1: Stage catalogue

**Files:**
- Create: `apps/api/app/bdm_stages.py`
- Test: `apps/api/tests/test_bdm_004_catalogue.py`

**Interfaces:**
- Produces: `Step(NamedTuple: key, label, kind)`; `PIPELINES: dict[str, tuple[Step, ...]]`; `MANUAL_STAGES: dict[str, tuple[str, ...]]`;
  `FIRST_STAGE = "prospect"`; `AGENT_STATUSES: tuple[str, ...]`; `AGENT_STATUS: dict[str, str]` (stage key → status);
  `MANUAL, LIVE, VOLUME` kind strings.

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_bdm_004_catalogue.py`:

```python
"""bdm-004 -- the stage catalogues (spec §4, S2, S4; AC1, AC9). Pure: no database."""

import re

from app.bdm_stages import AGENT_STATUS, AGENT_STATUSES, FIRST_STAGE, LIVE, MANUAL, MANUAL_STAGES, PIPELINES, VOLUME

# EVID-016 Agent §E (685-741), School §D (897-951), College §D (1136-1190), in source order and wording.
SOURCE = {
    "agent": [
        "Agent Prospect", "Contacted", "Meeting Scheduled", "Meeting Completed", "Interested", "Proposal / Agreement",
        "Agreement Signed", "Agent Onboarding", "Master Login Created", "Staff Logins Created", "Active Agent", "Students",
        "Applications", "Enrollments",
    ],
    "school": [
        "School Prospect", "Contacted", "Meeting", "Presentation", "Proposal", "Negotiation", "MoU", "Signed", "School Onboarding",
        "Teachers / Parents / Students Created", "Career Guidance", "Psychometric", "Student Profile Building", "University Planning",
    ],
    "college": [
        "College Prospect", "Contacted", "Meeting", "Presentation", "Proposal", "MoU Negotiation", "MoU Signed", "College Activated",
        "Course Promotion", "Student Leads", "Training", "Internship", "Recruitment", "Placement",
    ],
}
KIND_COUNTS = {"agent": (7, 4, 3), "school": (8, 6, 0), "college": (8, 0, 6)}


def test_labels_match_the_source_in_order():
    assert set(PIPELINES) == {"agent", "school", "college"}
    for bdm_type, labels in SOURCE.items():
        assert [s.label for s in PIPELINES[bdm_type]] == labels


def test_kinds_per_type_with_manual_first_then_live_then_volume():
    order = [MANUAL, LIVE, VOLUME]
    for bdm_type, (manual, live, volume) in KIND_COUNTS.items():
        kinds = [s.kind for s in PIPELINES[bdm_type]]
        assert (kinds.count(MANUAL), kinds.count(LIVE), kinds.count(VOLUME)) == (manual, live, volume)
        assert kinds == sorted(kinds, key=order.index)


def test_keys_are_unique_snake_case_and_start_at_prospect():
    for steps in PIPELINES.values():
        keys = [s.key for s in steps]
        assert len(set(keys)) == len(keys) == 14
        assert all(re.fullmatch(r"[a-z_]{1,40}", k) for k in keys)
        assert keys[0] == FIRST_STAGE == "prospect"


def test_manual_stages_are_the_manual_keys_in_order():
    for bdm_type, steps in PIPELINES.items():
        assert MANUAL_STAGES[bdm_type] == tuple(s.key for s in steps if s.kind == MANUAL)
    assert MANUAL_STAGES["college"][-1] == "college_activated"  # S2
    assert MANUAL_STAGES["agent"][-1] == "agreement_signed" and MANUAL_STAGES["school"][-1] == "signed"


def test_agent_status_is_derived_per_s4():
    assert AGENT_STATUSES == ("Prospect", "Contacted", "Meeting", "Interested", "Agreement", "Onboarding", "Active", "Inactive")
    assert AGENT_STATUS == {
        "prospect": "Prospect", "contacted": "Contacted", "meeting_scheduled": "Meeting", "meeting_completed": "Meeting",
        "interested": "Interested", "proposal_agreement": "Agreement", "agreement_signed": "Agreement",
        "agent_onboarding": "Onboarding", "master_login_created": "Onboarding", "staff_logins_created": "Onboarding",
        "active_agent": "Active",
    }
    assert set(AGENT_STATUS.values()) <= set(AGENT_STATUSES)
```

- [ ] **Step 2: Run it to verify it fails**

Run: backend command with `<P>` = `tests/test_bdm_004_catalogue.py`
Expected: collection error `ModuleNotFoundError: No module named 'app.bdm_stages'`.

- [ ] **Step 3: Write the module** — `apps/api/app/bdm_stages.py`:

```python
"""bdm-004 (DEC-SCOPE-070, spec §4): the three BDM pipelines, in source order and wording (EVID-016 Agent §E, School §D,
College §D).

Constants only, with no app imports, so the model CHECK, the migration's parity test, the service and the schemas share one list.
kind: "manual" -- the BDM sets it; "live" -- read from the onboarded partner record (bdm-018 / bdm-019, S3); "volume" -- counted
from live records (bdm-019 / bdm-021 / bdm-022, S2). Only manual stages are ever stored."""

from typing import NamedTuple

MANUAL, LIVE, VOLUME = "manual", "live", "volume"
FIRST_STAGE = "prospect"


class Step(NamedTuple):
    key: str
    label: str
    kind: str


PIPELINES: dict[str, tuple[Step, ...]] = {
    "agent": (
        Step("prospect", "Agent Prospect", MANUAL),
        Step("contacted", "Contacted", MANUAL),
        Step("meeting_scheduled", "Meeting Scheduled", MANUAL),
        Step("meeting_completed", "Meeting Completed", MANUAL),
        Step("interested", "Interested", MANUAL),
        Step("proposal_agreement", "Proposal / Agreement", MANUAL),
        Step("agreement_signed", "Agreement Signed", MANUAL),
        Step("agent_onboarding", "Agent Onboarding", LIVE),
        Step("master_login_created", "Master Login Created", LIVE),
        Step("staff_logins_created", "Staff Logins Created", LIVE),
        Step("active_agent", "Active Agent", LIVE),
        Step("students", "Students", VOLUME),
        Step("applications", "Applications", VOLUME),
        Step("enrollments", "Enrollments", VOLUME),
    ),
    "school": (
        Step("prospect", "School Prospect", MANUAL),
        Step("contacted", "Contacted", MANUAL),
        Step("meeting", "Meeting", MANUAL),
        Step("presentation", "Presentation", MANUAL),
        Step("proposal", "Proposal", MANUAL),
        Step("negotiation", "Negotiation", MANUAL),
        Step("mou", "MoU", MANUAL),
        Step("signed", "Signed", MANUAL),
        Step("school_onboarding", "School Onboarding", LIVE),
        Step("users_created", "Teachers / Parents / Students Created", LIVE),
        Step("career_guidance", "Career Guidance", LIVE),
        Step("psychometric", "Psychometric", LIVE),
        Step("profile_building", "Student Profile Building", LIVE),
        Step("university_planning", "University Planning", LIVE),
    ),
    "college": (
        Step("prospect", "College Prospect", MANUAL),
        Step("contacted", "Contacted", MANUAL),
        Step("meeting", "Meeting", MANUAL),
        Step("presentation", "Presentation", MANUAL),
        Step("proposal", "Proposal", MANUAL),
        Step("mou_negotiation", "MoU Negotiation", MANUAL),
        Step("mou_signed", "MoU Signed", MANUAL),
        Step("college_activated", "College Activated", MANUAL),
        Step("course_promotion", "Course Promotion", VOLUME),
        Step("student_leads", "Student Leads", VOLUME),
        Step("training", "Training", VOLUME),
        Step("internship", "Internship", VOLUME),
        Step("recruitment", "Recruitment", VOLUME),
        Step("placement", "Placement", VOLUME),
    ),
}
MANUAL_STAGES: dict[str, tuple[str, ...]] = {t: tuple(s.key for s in steps if s.kind == MANUAL) for t, steps in PIPELINES.items()}

# S4 (D13): the 8-value agent status (Agent §B) is derived on read, never stored. "Inactive" needs the linked Agent Organization
# (suspended / rejected), so nothing maps to it until bdm-019.
AGENT_STATUSES = ("Prospect", "Contacted", "Meeting", "Interested", "Agreement", "Onboarding", "Active", "Inactive")
AGENT_STATUS: dict[str, str] = {
    "prospect": "Prospect",
    "contacted": "Contacted",
    "meeting_scheduled": "Meeting",
    "meeting_completed": "Meeting",
    "interested": "Interested",
    "proposal_agreement": "Agreement",
    "agreement_signed": "Agreement",
    "agent_onboarding": "Onboarding",
    "master_login_created": "Onboarding",
    "staff_logins_created": "Onboarding",
    "active_agent": "Active",
}
```

- [ ] **Step 4: Run it to verify it passes** — same command. Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/bdm_stages.py apps/api/tests/test_bdm_004_catalogue.py
git commit -m "feat(bdm-004): stage catalogues per BDM type (spec §4, S2, S4)"
```

---

### Task 2: Model, migration `0072_bdm_pipeline`, head-pin relaxation

**Files:**
- Modify: `apps/api/app/models.py` (after `BDM_PROFILE_CHECKS` ~line 1067; `BdmOrganization.__table_args__` and columns ~1070-1115;
  new `BdmPipelineEvent` after `BdmOrganizationContact`)
- Create: `apps/api/alembic/versions/0072_bdm_pipeline.py`
- Modify: `apps/api/tests/test_bdm_009_migration.py:35-37`
- Test: `apps/api/tests/test_bdm_004_migration.py`

**Interfaces:**
- Consumes: `app.bdm_stages.MANUAL_STAGES`, `FIRST_STAGE`.
- Produces: `BdmOrganization.pipeline_stage: str`, `.lost_at: datetime | None`, `.lost_reason: str | None`;
  `app.models.BDM_PIPELINE_CHECKS: dict[str, str]`; `app.models.BDM_PIPELINE_EVENT_KINDS = ("move", "lost", "revived")`;
  `app.models.BdmPipelineEvent` (`id, organization_id, actor_user_id, kind, from_stage, to_stage, note, position, created_at`).

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_bdm_004_migration.py`:

```python
"""bdm-004 -- migration 0072_bdm_pipeline (spec §5; AC10). Round trip and the downgrade refusal run in a throwaway database (the
bdm-003 pattern); a downgrade never runs against the shared test database."""

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
BASE, HEAD = "0071_bdm_activities", "0072_bdm_pipeline"
NEW_COLUMNS = {"pipeline_stage", "lost_at", "lost_reason"}


def _migration():
    spec = importlib.util.spec_from_file_location("_bdm_004_migration_0072", VERSIONS / f"{HEAD}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_chains_after_0071_and_is_the_single_head():
    migration = _migration()
    assert (migration.revision, migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_frozen_stage_lists_and_checks_equal_the_model():
    from app.bdm_stages import MANUAL_STAGES
    from app.models import BDM_PIPELINE_CHECKS, BdmOrganization

    migration = _migration()
    assert migration.MANUAL_STAGES == MANUAL_STAGES
    assert migration.CHECKS == BDM_PIPELINE_CHECKS
    model_checks = {c.name: str(c.sqltext) for c in BdmOrganization.__table__.constraints if isinstance(c, CheckConstraint)}
    assert BDM_PIPELINE_CHECKS.items() <= model_checks.items()
    table = BdmOrganization.__table__
    assert NEW_COLUMNS <= {c.name for c in table.columns}
    assert not table.c.pipeline_stage.nullable and table.c.pipeline_stage.server_default.arg == "prospect"
    assert table.c.lost_at.nullable and table.c.lost_reason.nullable
    assert "ix_bdm_organizations_type_stage" in {i.name for i in table.indexes}


def test_event_model_matches_the_migration():
    from app.models import BdmPipelineEvent

    table = BdmPipelineEvent.__table__
    assert {c.name for c in table.columns} == {
        "id", "organization_id", "actor_user_id", "kind", "from_stage", "to_stage", "note", "position", "created_at",
    }
    assert {fk.parent.name: fk.ondelete for fk in table.foreign_keys} == {"organization_id": "RESTRICT", "actor_user_id": "RESTRICT"}
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {"ck_bdm_pipeline_events_kind", "ck_bdm_pipeline_events_note", "ix_bdm_pipeline_events_org"} <= names


@pytest.mark.asyncio
async def test_columns_and_table_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    columns = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_columns("bdm_organizations")})
    tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
    assert NEW_COLUMNS <= columns and "bdm_pipeline_events" in tables


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
    """A fresh database at 0071_bdm_activities with one bdm user."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm004_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        user_id = uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'it', true, true, 'en-GB', '{}')",
            {"id": user_id, "email": f"bdm-{name}@example.local"},
        )
        yield {"cfg": cfg, "url": url, "user": user_id}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


INSERT = (
    "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, created_by_user_id{extra_cols}) "
    "VALUES (:id, :code, 'college', :bdm_type, 'A', 'a', 'K', 'k', :u, :u{extra_vals})"
)


def _insert(db, bdm_type: str, **values) -> uuid.UUID:
    org_id = uuid.uuid4()
    sql = INSERT.format(extra_cols="".join(f", {k}" for k in values), extra_vals="".join(f", :{k}" for k in values))
    _sql(db["url"], sql, {"id": org_id, "code": f"ORG-{uuid.uuid4().hex[:8]}", "bdm_type": bdm_type, "u": db["user"], **values})
    return org_id


def test_round_trip_backfills_prospect_and_enforces_the_checks(isolated_db):
    """0001 builds BASE from the current models, so go up, down to BASE (the migration drops the columns), insert a row, and up
    again: the default and the CHECKs below are 0072's own DDL."""
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    cols = {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'bdm_organizations'")}
    assert not (NEW_COLUMNS & cols)
    kept = _insert(isolated_db, "school")
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT pipeline_stage, lost_at, lost_reason FROM bdm_organizations WHERE id = :id", {"id": kept}) == [("prospect", None, None)]
    assert _sql(url, "SELECT count(*) FROM bdm_pipeline_events") == [(0,)]
    bad = [
        ("college", {"pipeline_stage": "signed"}, "ck_bdm_organizations_pipeline_stage"),  # a School stage
        ("agent", {"pipeline_stage": "master_login_created"}, "ck_bdm_organizations_pipeline_stage"),  # live: never stored
        ("college", {"pipeline_stage": "placement"}, "ck_bdm_organizations_pipeline_stage"),  # volume: never stored
        ("school", {"lost_reason": "No budget"}, "ck_bdm_organizations_lost"),  # a reason without lost_at
    ]
    for bdm_type, values, check in bad:
        with pytest.raises(Exception, match=check):
            _insert(isolated_db, bdm_type, **values)
    _insert(isolated_db, "college", pipeline_stage="college_activated")
    _insert(isolated_db, "agent", pipeline_stage="agreement_signed")
    with pytest.raises(Exception, match="ck_bdm_pipeline_events_note"):
        _sql(url, "INSERT INTO bdm_pipeline_events (id, organization_id, actor_user_id, kind, from_stage, to_stage) VALUES (:id, :o, :u, 'lost', 'prospect', 'prospect')",
             {"id": uuid.uuid4(), "o": kept, "u": isolated_db["user"]})


def test_downgrade_refuses_while_pipeline_data_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    moved = _insert(isolated_db, "college", pipeline_stage="contacted")
    with pytest.raises(Exception, match="pipeline data exists"):
        command.downgrade(cfg, BASE)
    _sql(url, "UPDATE bdm_organizations SET pipeline_stage = 'prospect' WHERE id = :id", {"id": moved})
    _sql(url, "INSERT INTO bdm_pipeline_events (id, organization_id, actor_user_id, kind, from_stage, to_stage) VALUES (:id, :o, :u, 'move', 'prospect', 'contacted')",
         {"id": uuid.uuid4(), "o": moved, "u": isolated_db["user"]})
    with pytest.raises(Exception, match="pipeline data exists"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM bdm_pipeline_events")
    command.downgrade(cfg, BASE)  # nothing recorded any more: allowed
```

- [ ] **Step 2: Run it to verify it fails**

Run: backend command with `<P>` = `tests/test_bdm_004_migration.py`
Expected: FAIL — `FileNotFoundError` for `0072_bdm_pipeline.py` / `ImportError: cannot import name 'BDM_PIPELINE_CHECKS'`.

- [ ] **Step 3: Model.** In `apps/api/app/models.py`:

At the imports (top of file, after the `sqlalchemy` imports):

```python
from app.bdm_stages import FIRST_STAGE as BDM_FIRST_STAGE
from app.bdm_stages import MANUAL_STAGES as BDM_MANUAL_STAGES
```

After the `BDM_PROFILE_CHECKS = {...}` block:

```python
# bdm-004 (DEC-SCOPE-070, spec §5.1): only a manual stage of the organization's own pipeline is stored (S3: live stages arrive with
# bdm-018 / bdm-019, which widen this CHECK). Lost is a flag with a reason on top of the stage (S5). Migration 0072 repeats these
# strings; test_bdm_004_migration asserts they stay identical.
BDM_PIPELINE_CHECKS = {
    "ck_bdm_organizations_pipeline_stage": " OR ".join(
        f"(bdm_type = '{bdm_type}' AND {_in_list('pipeline_stage', stages)})" for bdm_type, stages in BDM_MANUAL_STAGES.items()
    ),
    "ck_bdm_organizations_lost": "(lost_at IS NULL) = (lost_reason IS NULL)",
}
BDM_PIPELINE_EVENT_KINDS = ("move", "lost", "revived")
```

In `BdmOrganization.__table_args__`, after `*(CheckConstraint(sql, name=name) for name, sql in BDM_PROFILE_CHECKS.items()),`:

```python
        *(CheckConstraint(sql, name=name) for name, sql in BDM_PIPELINE_CHECKS.items()),
```

and after `Index("ix_bdm_organizations_duplicate_key", ...)`:

```python
        Index("ix_bdm_organizations_type_stage", "bdm_type", "pipeline_stage"),
```

Append to the class docstring: `bdm-004 (DEC-SCOPE-070): pipeline_stage (a manual stage of bdm_type's pipeline) and the Lost flag.`
After `archived_at`:

```python
    pipeline_stage: Mapped[str] = mapped_column(String(40), default=BDM_FIRST_STAGE, server_default=BDM_FIRST_STAGE)
    lost_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
```

After the `BdmOrganizationContact` class:

```python
class BdmPipelineEvent(Base):
    """bdm-004 (DEC-SCOPE-070, spec §5.2): one row per stage move, Lost or Revive. Append-only. `from_stage` = `to_stage` for lost /
    revived; `note` is the move note or the required reason. No stage CHECK: history must survive a future catalogue change.
    `position` orders rows created in one transaction."""

    __tablename__ = "bdm_pipeline_events"
    __table_args__ = (
        CheckConstraint(_in_list("kind", BDM_PIPELINE_EVENT_KINDS), name="ck_bdm_pipeline_events_kind"),
        CheckConstraint("kind = 'move' OR note IS NOT NULL", name="ck_bdm_pipeline_events_note"),
        Index("ix_bdm_pipeline_events_org", "organization_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organizations.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(10))
    from_stage: Mapped[str] = mapped_column(String(40))
    to_stage: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Migration** — `apps/api/alembic/versions/0072_bdm_pipeline.py`:

```python
"""bdm-004 -- organization pipelines: pipeline_stage + Lost on bdm_organizations, and bdm_pipeline_events.

Revision ID: 0072_bdm_pipeline
Revises: 0071_bdm_activities

docs/superpowers/specs/2026-10-05-bdm-004-organization-pipelines-design.md §5 (DEC-SCOPE-070). Additive: existing rows get
'prospect' from the column default (valid for all three types) and no history row. 0001 builds a fresh database from the current
models, which already carry the columns, CHECKs, index and table, so each is created only when missing. MANUAL_STAGES is a frozen copy
of app.bdm_stages.MANUAL_STAGES and CHECKS must equal app.models.BDM_PIPELINE_CHECKS (test_bdm_004_migration). downgrade() refuses
while any pipeline data exists: recorded moves are never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0072_bdm_pipeline"
down_revision = "0071_bdm_activities"
branch_labels = None
depends_on = None

TABLE = "bdm_organizations"
EVENTS = "bdm_pipeline_events"
INDEX = "ix_bdm_organizations_type_stage"
MANUAL_STAGES = {
    "agent": ("prospect", "contacted", "meeting_scheduled", "meeting_completed", "interested", "proposal_agreement", "agreement_signed"),
    "school": ("prospect", "contacted", "meeting", "presentation", "proposal", "negotiation", "mou", "signed"),
    "college": ("prospect", "contacted", "meeting", "presentation", "proposal", "mou_negotiation", "mou_signed", "college_activated"),
}


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {
    "ck_bdm_organizations_pipeline_stage": " OR ".join(
        f"(bdm_type = '{bdm_type}' AND {_in_list('pipeline_stage', stages)})" for bdm_type, stages in MANUAL_STAGES.items()
    ),
    "ck_bdm_organizations_lost": "(lost_at IS NULL) = (lost_reason IS NULL)",
}


def _present() -> tuple[set[str], set[str], set[str], set[str]]:
    if op.get_context().as_sql:  # offline SQL: emit everything
        return set(), set(), set(), set()
    inspector = sa.inspect(op.get_bind())
    return (
        {c["name"] for c in inspector.get_columns(TABLE)},
        {c["name"] for c in inspector.get_check_constraints(TABLE)},
        {i["name"] for i in inspector.get_indexes(TABLE)},
        set(inspector.get_table_names()),
    )


def upgrade() -> None:
    columns, checks, indexes, tables = _present()
    if "pipeline_stage" not in columns:
        op.add_column(TABLE, sa.Column("pipeline_stage", sa.String(40), nullable=False, server_default="prospect"))
    if "lost_at" not in columns:
        op.add_column(TABLE, sa.Column("lost_at", sa.DateTime(timezone=True), nullable=True))
    if "lost_reason" not in columns:
        op.add_column(TABLE, sa.Column("lost_reason", sa.String(500), nullable=True))
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, sql)
    if INDEX not in indexes:
        op.create_index(INDEX, TABLE, ["bdm_type", "pipeline_stage"])
    if EVENTS not in tables:
        uuid = postgresql.UUID(as_uuid=True)
        op.create_table(
            EVENTS,
            sa.Column("id", uuid, primary_key=True),
            sa.Column("organization_id", uuid, sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("actor_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("from_stage", sa.String(40), nullable=False),
            sa.Column("to_stage", sa.String(40), nullable=False),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("kind IN ('move', 'lost', 'revived')", name="ck_bdm_pipeline_events_kind"),
            sa.CheckConstraint("kind = 'move' OR note IS NOT NULL", name="ck_bdm_pipeline_events_note"),
        )
        op.create_index("ix_bdm_pipeline_events_org", EVENTS, ["organization_id", "position"])


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        recorded = bind.execute(sa.text(f"SELECT 1 FROM {EVENTS} LIMIT 1")).first()
        moved = bind.execute(sa.text(f"SELECT 1 FROM {TABLE} WHERE pipeline_stage <> 'prospect' OR lost_at IS NOT NULL LIMIT 1")).first()
        if recorded or moved:
            raise RuntimeError("Cannot downgrade 0072_bdm_pipeline: pipeline data exists. Clear it deliberately first.")
    op.drop_table(EVENTS)
    op.drop_index(INDEX, TABLE)
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    for name in ("lost_reason", "lost_at", "pipeline_stage"):
        op.drop_column(TABLE, name)
```

- [ ] **Step 5: Relax the bdm-009 head pin** — in `apps/api/tests/test_bdm_009_migration.py` replace the body of
  `test_migration_chains_after_0070_and_is_the_single_head`:

```python
def test_migration_chains_after_0070_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())  # bdm-004: a later migration may be the head; 0071 must be on the one line
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}
```

- [ ] **Step 6: Run** `<P>` = `tests/test_bdm_004_migration.py tests/test_bdm_009_migration.py tests/test_bdm_002_migration.py tests/test_bdm_003_migration.py`
Expected: all pass.

- [ ] **Step 7: Offline SQL review** — run
`... api-test sh -c "alembic upgrade 0071_bdm_activities:0072_bdm_pipeline --sql"` and check: three `ADD COLUMN`, two
`ADD CONSTRAINT ... CHECK`, one `CREATE INDEX`, one `CREATE TABLE bdm_pipeline_events`, no `UPDATE` / `DELETE`.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/models.py apps/api/alembic/versions/0072_bdm_pipeline.py apps/api/tests/test_bdm_004_migration.py apps/api/tests/test_bdm_009_migration.py
git commit -m "feat(bdm-004): pipeline_stage, Lost flag and bdm_pipeline_events (migration 0072)"
```

---

### Task 3: Request and response schemas

**Files:**
- Modify: `apps/api/app/schemas.py` (pipeline output classes immediately before `class BdmOrganizationRow` ~line 3755;
  `BdmOrganizationOut` gains `pipeline`; input + page classes after `class BdmOrganizationEnvelope`)
- Test: `apps/api/tests/test_bdm_004_schemas.py`

**Interfaces:**
- Produces: `BdmStageMove {from_stage, to_stage, note}`, `BdmLostIn {reason}`, `BdmReviveIn {reason}` (all `extra="forbid"`);
  `BdmPipelineStepOut`, `BdmPipelineLost`, `BdmOrgPipelineOut`; `BdmOrganizationOut.pipeline: BdmOrgPipelineOut`;
  `BdmStageEventOut`, `BdmStageEventPage`; `BdmPipelineStageCount`, `BdmPipelineItem`, `BdmPipelinePage`.

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_bdm_004_schemas.py`:

```python
"""bdm-004 -- request schemas (spec §6.1): stage-key shape, note / reason rules, unknown fields."""

import pytest
from pydantic import ValidationError

from app.schemas import BdmLostIn, BdmReviveIn, BdmStageMove


def _move(**over) -> BdmStageMove:
    return BdmStageMove(**{"from_stage": "prospect", "to_stage": "contacted", **over})


def test_note_is_optional_trimmed_and_line_breaks_normalized():
    assert _move().note is None
    assert _move(note="  first\r\nsecond\rthird  ").note == "first\nsecond\nthird"


def test_blank_note_is_none():
    assert _move(note="   ").note is None


def test_crlf_counts_as_one_character():
    assert len(_move(note="a" * 498 + "\r\n" + "b").note) == 500
    with pytest.raises(ValidationError):
        _move(note="a" * 501)


def test_control_characters_are_refused_but_tabs_allowed():
    assert _move(note="a\tb").note == "a\tb"
    with pytest.raises(ValidationError, match="Note contains invalid characters"):
        _move(note="a\x07b")


@pytest.mark.parametrize("key", ["Contacted", "x" * 41, "", "prospect;drop", "pro spect", "<script>"])
def test_stage_keys_are_lower_snake_case(key):
    with pytest.raises(ValidationError):
        _move(to_stage=key)
    with pytest.raises(ValidationError):
        _move(from_stage=key)


def test_unknown_fields_are_refused():
    with pytest.raises(ValidationError):
        _move(stage="contacted")
    with pytest.raises(ValidationError):
        BdmLostIn(reason="x", lost_at="2026-01-01")


def test_reason_is_required_trimmed_and_normalized():
    for model in (BdmLostIn, BdmReviveIn):
        assert model(reason=" No budget\r\nthis year ").reason == "No budget\nthis year"
        with pytest.raises(ValidationError, match="Reason is required"):
            model(reason="   ")
        with pytest.raises(ValidationError):
            model()
        with pytest.raises(ValidationError):
            model(reason="r" * 501)
```

- [ ] **Step 2: Run it** (`<P>` = `tests/test_bdm_004_schemas.py`). Expected: `ImportError: cannot import name 'BdmLostIn'`.

- [ ] **Step 3: Implement.** Immediately before `class BdmOrganizationRow(BaseModel):` add:

```python
# --- bdm-004 (DEC-SCOPE-070, spec §6.1): the pipeline on the organization detail ------------------------------------------------
class BdmPipelineStepOut(BaseModel):
    key: str
    label: str
    kind: Literal["manual", "live", "volume"]
    state: Literal["done", "current", "upcoming", "awaiting_handover", "not_tracked"]


class BdmPipelineLost(BaseModel):
    at: datetime
    reason: str


class BdmOrgPipelineOut(BaseModel):
    stage: str
    stage_label: str
    lost: BdmPipelineLost | None
    agent_status: str | None  # S4: Agent organizations only
    steps: list[BdmPipelineStepOut]
```

In `class BdmOrganizationOut(BdmOrganizationRow):` after `profile: ...` add:

```python
    pipeline: BdmOrgPipelineOut  # bdm-004: detail only; list rows are unchanged
```

After `class BdmOrganizationEnvelope(BaseModel): ...` add:

```python
# --- bdm-004 (DEC-SCOPE-070, spec §6.1): stage moves, Lost / Revive, history and the pipeline view -------------------------------
BdmStageKey = Annotated[str, StringConstraints(pattern=r"^[a-z_]{1,40}$")]
# P14 / TripNote: trimmed, at most 500 after \r\n -> \n, line breaks and tabs allowed, other control characters refused, blank -> None.
BdmPipelineNote = Annotated[TripNote, BeforeValidator(_bdm_newlines)]
BdmPipelineReason = Annotated[
    Annotated[Annotated[str, _trimmed(500)], AfterValidator(_trip_text(_BDM_MULTILINE_CONTROL, True))], BeforeValidator(_bdm_newlines)
]


class BdmStageMove(BaseModel):
    """S6: `from_stage` is the stage the form was showing -- a different stored stage is 409 `stage_changed`."""

    model_config = ConfigDict(extra="forbid")
    from_stage: BdmStageKey
    to_stage: BdmStageKey
    note: BdmPipelineNote = None


class BdmLostIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: BdmPipelineReason


class BdmReviveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: BdmPipelineReason


class BdmStageEventOut(BaseModel):
    id: UUID
    kind: Literal["move", "lost", "revived"]
    from_stage: str
    from_label: str
    to_stage: str
    to_label: str
    note: str | None
    actor: BdmPersonRef
    created_at: datetime


class BdmStageEventPage(BaseModel):
    items: list[BdmStageEventOut]
    total: int
    limit: int
    offset: int


class BdmPipelineStageCount(BaseModel):
    key: str
    label: str
    kind: Literal["manual", "live", "volume"]
    count: int | None  # null for live / volume steps (S2, S3)


class BdmPipelineItem(BaseModel):
    id: UUID
    code: str
    name: str
    city: str
    org_type: str
    assigned_bdm: BdmOrgPerson
    stage: str
    stage_label: str
    lost: bool


class BdmPipelinePage(BaseModel):
    bdm_type: BdmType
    stages: list[BdmPipelineStageCount]
    lost_count: int
    items: list[BdmPipelineItem]
    total: int
    limit: int
    offset: int
```

(`TripNote`, `_trimmed`, `_trip_text`, `_BDM_MULTILINE_CONTROL`, `_bdm_newlines`, `BdmPersonRef`, `BdmOrgPerson`, `BdmType` already
exist earlier in `schemas.py`; `BeforeValidator`, `AfterValidator`, `StringConstraints`, `ConfigDict` are already imported.)

- [ ] **Step 4: Run it.** Expected: all pass. (Organization routes now fail response validation until Task 4 adds `pipeline` — do
  not commit before Task 4's Step 4 passes; Tasks 3 and 4 share one commit.)

---

### Task 4: Pipeline on the organization detail (service `pipeline_out`)

**Files:**
- Create: `apps/api/app/services/bdm_pipeline.py`
- Modify: `apps/api/app/services/bdm_organizations.py:281-303` (`organization_out` adds `"pipeline"`)
- Test: `apps/api/tests/test_bdm_004_stage.py` (first part), `apps/api/tests/bdm004_helpers.py`

**Interfaces:**
- Consumes: `app.bdm_stages.*`; `BdmOrganization.pipeline_stage/lost_at/lost_reason`.
- Produces: `bdm_pipeline.pipeline_out(org) -> dict`; `bdm_pipeline.live_status(org) -> None`;
  `bdm_pipeline.label_of(bdm_type: str, key: str) -> str`; helpers `tests/bdm004_helpers.py`: `STAGE(org_id) -> str`,
  `move(client, org, to_stage, note=None, from_stage=None) -> httpx.Response`, `events(db, org_id) -> list[BdmPipelineEvent]`,
  `audits(db, org_id, action) -> list[AuditLog]`.

- [ ] **Step 1: Helpers** — `apps/api/tests/bdm004_helpers.py`:

```python
"""bdm-004 test builders, on top of bdm-002/003's. Unique values per call: the test database is shared and never truncated."""

from uuid import UUID

from sqlalchemy import select

from app.models import AuditLog, BdmPipelineEvent
from tests.bdm002_helpers import ORGS

PIPELINE = "/api/v1/bdm/pipeline"


def url(org_id: str, action: str) -> str:
    return f"{ORGS}/{org_id}/{action}"


async def move(client, org: dict, to_stage: str, note: str | None = None, from_stage: str | None = None):
    body = {"from_stage": from_stage or org["pipeline"]["stage"], "to_stage": to_stage}
    if note is not None:
        body["note"] = note
    return await client.post(url(org["id"], "stage"), json=body)


async def events(db, org_id: str) -> list[BdmPipelineEvent]:
    db.expire_all()
    stmt = select(BdmPipelineEvent).where(BdmPipelineEvent.organization_id == UUID(org_id)).order_by(BdmPipelineEvent.position)
    return list((await db.scalars(stmt)).all())


async def audits(db, org_id: str, action: str) -> list[AuditLog]:
    db.expire_all()
    stmt = select(AuditLog).where(AuditLog.entity_id == org_id, AuditLog.action == f"bdm_organization.{action}").order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())
```

- [ ] **Step 2: Write the failing tests** — `apps/api/tests/test_bdm_004_stage.py` (this task's part):

```python
"""bdm-004 -- the pipeline on the organization detail and stage moves (spec §6; AC1-AC4, AC7 stale, AC9, AC12)."""

import pytest

from app.bdm_stages import PIPELINES
from tests.bdm001_helpers import login
from tests.bdm002_helpers import ORGS, create_org
from tests.bdm003_helpers import bdm_of
from tests.bdm004_helpers import audits, events, move

EXPECTED_STATE = {"manual": "upcoming", "live": "awaiting_handover", "volume": "not_tracked"}


@pytest.mark.asyncio
@pytest.mark.parametrize("bdm_type", ["agent", "school", "college"])
async def test_a_new_organization_starts_at_prospect_with_its_own_pipeline(client, db_session, bdm_type):
    await login(client, await bdm_of(db_session, bdm_type))
    org = await create_org(client)
    p = org["pipeline"]
    assert (p["stage"], p["lost"]) == ("prospect", None)
    assert p["stage_label"] == PIPELINES[bdm_type][0].label
    assert [(s["key"], s["label"], s["kind"]) for s in p["steps"]] == [tuple(s) for s in PIPELINES[bdm_type]]
    assert p["steps"][0]["state"] == "current"
    assert [s["state"] for s in p["steps"][1:]] == [EXPECTED_STATE[s.kind] for s in PIPELINES[bdm_type][1:]]
    assert p["agent_status"] == ("Prospect" if bdm_type == "agent" else None)
    assert await events(db_session, org["id"]) == []  # no history row on create (spec §5.2)
    detail = (await client.get(f"{ORGS}/{org['id']}")).json()["organization"]
    assert detail["pipeline"] == p


@pytest.mark.asyncio
async def test_list_rows_do_not_change(client, db_session):
    """AC12: only the detail gains `pipeline`."""
    await login(client, await bdm_of(db_session, "college"))
    org = await create_org(client)
    row = (await client.get(ORGS, params={"q": org["code"]})).json()["items"][0]
    assert "pipeline" not in row and set(row["permissions"]) == {"can_edit", "can_archive", "can_restore", "can_reassign"}
```

- [ ] **Step 3: Run it** (`<P>` = `tests/test_bdm_004_stage.py`). Expected: FAIL — the response has no `pipeline` (KeyError) /
  response validation error "Field required: pipeline".

- [ ] **Step 4: Implement.** `apps/api/app/services/bdm_pipeline.py` (first part):

```python
"""bdm-004 (DEC-SCOPE-070, spec §6.2): pipeline output, move / Lost / Revive rules, history and the pipeline view.

Functions only; nothing here commits -- the route owns the transaction (bdm-002's rule). Every check runs on the row locked by
`load_scoped(lock=True)`. Audit metadata and logs carry stage keys and flags only, never the note or reason text (spec §6.6)."""

from app.bdm_stages import AGENT_STATUS, LIVE, MANUAL, PIPELINES, VOLUME
from app.models import BdmOrganization

_LATER_STATE = {MANUAL: "upcoming", LIVE: "awaiting_handover", VOLUME: "not_tracked"}


def label_of(bdm_type: str, key: str) -> str:
    """A stage key's source label; a key no longer in the catalogue (history after a future change) is shown as stored."""
    return next((s.label for s in PIPELINES[bdm_type] if s.key == key), key)


def live_status(org: BdmOrganization) -> None:
    """S3: the live post-handover stage, read from the linked School (bdm-018) or Agent Organization (bdm-019). Nothing is linked
    yet, so live steps show "Awaiting handover"."""
    return None


def pipeline_out(org: BdmOrganization) -> dict:
    steps = PIPELINES[org.bdm_type]
    current = next(i for i, s in enumerate(steps) if s.key == org.pipeline_stage)

    def state(i: int, kind: str) -> str:
        return "done" if i < current else "current" if i == current else _LATER_STATE[kind]

    return {
        "stage": org.pipeline_stage,
        "stage_label": steps[current].label,
        "lost": {"at": org.lost_at, "reason": org.lost_reason} if org.lost_at else None,
        "agent_status": AGENT_STATUS[org.pipeline_stage] if org.bdm_type == "agent" else None,
        "steps": [{"key": s.key, "label": s.label, "kind": s.kind, "state": state(i, s.kind)} for i, s in enumerate(steps)],
    }
```

In `services/bdm_organizations.py` `organization_out`, after `"profile": profile_out(org),` add:

```python
        "pipeline": pipeline_out(org),  # bdm-004
```

and import at the top of `services/bdm_organizations.py` (below `from app.services.bdm import ...`):

```python
from app.services.bdm_pipeline import pipeline_out
```

(`services/bdm_pipeline.py` must not import `services/bdm_organizations.py` at module level for this part — it doesn't.)

- [ ] **Step 5: Run** `<P>` = `tests/test_bdm_004_stage.py tests/test_bdm_004_schemas.py tests/test_bdm_002_organizations.py tests/test_bdm_003_profiles.py`.
Expected: all pass.

- [ ] **Step 6: Commit (Tasks 3 + 4)**

```bash
git add apps/api/app/schemas.py apps/api/app/services/bdm_pipeline.py apps/api/app/services/bdm_organizations.py apps/api/tests/test_bdm_004_schemas.py apps/api/tests/test_bdm_004_stage.py apps/api/tests/bdm004_helpers.py
git commit -m "feat(bdm-004): pipeline schemas and the pipeline on the organization detail"
```

---

### Task 5: `POST /bdm/organizations/{id}/stage`

**Files:**
- Modify: `apps/api/app/services/bdm_pipeline.py` (rules + `record_event`)
- Create: `apps/api/app/api/bdm_pipeline.py`
- Modify: `apps/api/app/main.py` (import + router tuple, ~lines 23-27 and 77)
- Test: `apps/api/tests/test_bdm_004_stage.py` (append), `apps/api/tests/test_bdm_004_scope.py`, `apps/api/tests/test_bdm_004_concurrency.py`

**Interfaces:**
- Consumes: `org_svc.load_scoped`, `org_svc.require`, `org_svc.audit`, `org_svc.log`, `org_svc.organization_out`.
- Produces: `bdm_pipeline.check_move(user, org, payload: BdmStageMove) -> bool` (backward); `bdm_pipeline.record_event(db, user,
  org, kind, from_stage, to_stage, note)`; `bdm_pipeline.LOST_CONFLICT`, `NOT_LOST_CONFLICT`; `api.bdm_pipeline.router`
  (prefix `/bdm`).

- [ ] **Step 1: Write the failing tests** — append to `apps/api/tests/test_bdm_004_stage.py`:

```python
from sqlalchemy import select  # noqa: E402  (keep with the other imports at the top when writing the file)

from app.models import BdmOrganization  # noqa: E402
from app.services import bdm_organizations as org_svc  # noqa: E402


def _field(response, field: str) -> str:
    assert response.status_code == 422, response.text
    errors = [e for e in response.json()["detail"] if e["loc"][-1] == field]
    assert errors, response.json()
    return errors[0]["msg"]


async def _college(client, db):
    await login(client, await bdm_of(db, "college"))
    return await create_org(client)


@pytest.mark.asyncio
async def test_forward_moves_may_skip_and_write_one_history_and_one_audit_row(client, db_session):
    org = await _college(client, db_session)
    response = await move(client, org, "proposal")
    assert response.status_code == 200, response.text
    p = response.json()["organization"]["pipeline"]
    assert (p["stage"], p["stage_label"]) == ("proposal", "Proposal")
    assert [s["state"] for s in p["steps"][:6]] == ["done", "done", "done", "done", "current", "upcoming"]
    [event] = await events(db_session, org["id"])
    assert (event.kind, event.from_stage, event.to_stage, event.note) == ("move", "prospect", "proposal", None)
    [audit] = await audits(db_session, org["id"], "stage_changed")
    assert audit.metadata_json == {"from": "prospect", "to": "proposal", "backward": False, "note": False}


@pytest.mark.asyncio
async def test_backward_needs_a_note(client, db_session):
    org = await _college(client, db_session)
    org = (await move(client, org, "presentation")).json()["organization"]
    assert _field(await move(client, org, "contacted"), "note") == "Add a note to move an organization back"
    assert _field(await move(client, org, "contacted", note="   "), "note") == "Add a note to move an organization back"
    response = await move(client, org, "contacted", note="Wrong stage chosen")
    assert response.status_code == 200 and response.json()["organization"]["pipeline"]["stage"] == "contacted"
    last = (await events(db_session, org["id"]))[-1]
    assert (last.from_stage, last.to_stage, last.note) == ("presentation", "contacted", "Wrong stage chosen")
    audit = (await audits(db_session, org["id"], "stage_changed"))[-1]
    assert audit.metadata_json == {"from": "presentation", "to": "contacted", "backward": True, "note": True}
    assert "Wrong stage" not in str(audit.metadata_json)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bdm_type, to_stage, message",
    [
        ("agent", "master_login_created", "This stage is set by the onboarding handover"),
        ("school", "school_onboarding", "This stage is set by the onboarding handover"),
        ("agent", "enrollments", "This step is counted from live records, not set by hand"),
        ("college", "placement", "This step is counted from live records, not set by hand"),
        ("college", "agreement_signed", "Choose a stage of this organization's pipeline"),
        ("school", "nope", "Choose a stage of this organization's pipeline"),
        ("college", "prospect", "The organization is already at this stage"),
    ],
)
async def test_stages_that_cannot_be_set_by_hand_are_422_and_write_nothing(client, db_session, bdm_type, to_stage, message):
    await login(client, await bdm_of(db_session, bdm_type))
    org = await create_org(client)
    assert _field(await move(client, org, to_stage), "to_stage") == message
    assert (await client.get(f"{ORGS}/{org['id']}")).json()["organization"]["pipeline"]["stage"] == "prospect"
    assert await events(db_session, org["id"]) == [] and await audits(db_session, org["id"], "stage_changed") == []


@pytest.mark.asyncio
async def test_a_stale_from_stage_is_409_with_the_current_stage(client, db_session):
    org = await _college(client, db_session)
    await move(client, org, "contacted")
    response = await move(client, org, "meeting", from_stage="prospect")
    assert response.status_code == 409
    assert response.json()["detail"] == {"message": "This organization moved to Contacted meanwhile", "code": "stage_changed", "current_stage": "contacted"}


@pytest.mark.asyncio
async def test_archived_organizations_are_read_only(client, db_session):
    org = await _college(client, db_session)
    assert (await client.post(f"{ORGS}/{org['id']}/archive")).status_code == 200
    response = await move(client, org, "contacted")
    assert response.status_code == 409 and response.json()["detail"] == "Restore this organization first"


@pytest.mark.asyncio
async def test_agent_status_follows_the_stage(client, db_session):
    await login(client, await bdm_of(db_session, "agent"))
    org = await create_org(client)
    org = (await move(client, org, "meeting_completed")).json()["organization"]
    assert org["pipeline"]["agent_status"] == "Meeting"
    org = (await move(client, org, "agreement_signed")).json()["organization"]
    assert org["pipeline"]["agent_status"] == "Agreement"


@pytest.mark.asyncio
async def test_a_failure_before_commit_leaves_nothing(client, db_session, monkeypatch):
    """Transaction failure: the audit write raising rolls back the stage and the history row."""
    org = await _college(client, db_session)

    def boom(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(org_svc, "audit", boom)
    with pytest.raises(RuntimeError):
        await move(client, org, "contacted")
    db_session.expire_all()
    stored = await db_session.scalar(select(BdmOrganization.pipeline_stage).where(BdmOrganization.id == org["id"]))
    assert stored == "prospect" and await events(db_session, org["id"]) == []
```

(When writing the file, move the three late imports to the top import block and drop the `noqa` comments.)

`apps/api/tests/test_bdm_004_scope.py`:

```python
"""bdm-004 -- every pipeline route x the bdm-002 actors (AC6; spec §6.4, §7 IDOR / elevation)."""

import uuid

import pytest

from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import ORGS, create_org, make_bdm
from tests.bdm004_helpers import move, url


async def _world(client, db):
    manager = await make_manager(db)
    owner, peer = await make_bdm(db, manager), await make_bdm(db, manager)
    world = {
        "owner": owner,
        "peer": peer,
        "other_type": await make_bdm(db, manager, "school"),
        "manager": manager,
        "other_manager": await make_manager(db),
        "super_admin": await make_user(db, "super_admin", "global"),
        "it_admin": await make_user(db, "it_admin", "it"),
        "student": await make_user(db, "student", "it"),
        "no_profile": await make_user(db, "bdm", "it"),
    }
    await login(client, owner)
    world["org"] = await create_org(client)
    return world


# actor -> (move, history read)
EXPECTED = {
    "owner": (200, 200),
    "peer": (403, 200),
    "other_type": (404, 404),
    "manager": (403, 200),
    "other_manager": (404, 404),
    "super_admin": (200, 200),
    "it_admin": (403, 403),
    "student": (403, 403),
    "no_profile": (403, 403),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", list(EXPECTED))
async def test_scope_matrix(client, db_session, actor):
    w = await _world(client, db_session)
    moved, history = EXPECTED[actor]
    await login(client, w[actor])
    assert (await move(client, w["org"], "contacted")).status_code == moved
    assert (await client.get(url(w["org"]["id"], "stage-history"))).status_code == history


@pytest.mark.asyncio
async def test_refusals_are_explained_and_unknown_ids_look_out_of_scope(client, db_session):
    w = await _world(client, db_session)
    await login(client, w["peer"])
    assert (await move(client, w["org"], "contacted")).json()["detail"] == "Only the assigned BDM can edit this organization"
    await login(client, w["other_type"])
    out_of_scope = await move(client, w["org"], "contacted")
    missing = await move(client, {**w["org"], "id": str(uuid.uuid4())}, "contacted")
    assert out_of_scope.json() == missing.json() == {"detail": "Organization not found"}


@pytest.mark.asyncio
async def test_signed_out_is_401(client, db_session):
    w = await _world(client, db_session)
    await client.post("/api/v1/auth/logout")
    assert (await move(client, w["org"], "contacted")).status_code == 401
    assert (await client.get(f"{ORGS}/{w['org']['id']}/stage-history")).status_code == 401
```

`apps/api/tests/test_bdm_004_concurrency.py`:

```python
"""bdm-004 -- AC7: the organization row lock serializes two moves from the same stage; exactly one wins."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.bdm001_helpers import login
from tests.bdm002_helpers import create_org
from tests.bdm003_helpers import bdm_of
from tests.bdm004_helpers import events, move


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_two_moves_from_the_same_stage_one_wins(client, db_session):
    bdm = await bdm_of(db_session, "college")
    await login(client, bdm)
    org = await create_org(client)
    async with _client() as a, _client() as b:
        await login(a, bdm)
        await login(b, bdm)
        results = await asyncio.gather(move(a, org, "contacted"), move(b, org, "meeting"))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert len(await events(db_session, org["id"])) == 1
```

- [ ] **Step 2: Run** `<P>` = `tests/test_bdm_004_stage.py tests/test_bdm_004_scope.py tests/test_bdm_004_concurrency.py`.
Expected: FAIL — 404 Not Found for `/stage` and `/stage-history` (routes missing). The scope test's history column stays red until
Task 7.

- [ ] **Step 3: Service rules** — append to `apps/api/app/services/bdm_pipeline.py` (extend its imports as shown):

```python
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BdmOrganization, BdmPipelineEvent, User
from app.schemas import BdmStageMove

STAGE_UNKNOWN = "Choose a stage of this organization's pipeline"
STAGE_LIVE = "This stage is set by the onboarding handover"
STAGE_VOLUME = "This step is counted from live records, not set by hand"
STAGE_SAME = "The organization is already at this stage"
NOTE_REQUIRED = "Add a note to move an organization back"
LOST_CONFLICT = {"message": "This organization is marked lost. Revive it first.", "code": "organization_lost"}
NOT_LOST_CONFLICT = {"message": "This organization is not marked lost.", "code": "organization_not_lost"}


def _invalid(field: str, msg: str, value) -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": msg, "input": value}])


def check_move(user: User, org: BdmOrganization, payload: BdmStageMove) -> bool:
    """Spec §6.4 steps 6-8 on the locked row (the route already ran require: 403, archived 409). Returns whether the move is
    backward (S6)."""
    if org.lost_at is not None:
        raise HTTPException(409, LOST_CONFLICT)
    if payload.from_stage != org.pipeline_stage:
        log_conflict(user, org, payload.to_stage)
        current = label_of(org.bdm_type, org.pipeline_stage)
        raise HTTPException(409, {"message": f"This organization moved to {current} meanwhile", "code": "stage_changed", "current_stage": org.pipeline_stage})
    steps = PIPELINES[org.bdm_type]
    keys = [s.key for s in steps]
    if payload.to_stage not in keys:
        raise _invalid("to_stage", STAGE_UNKNOWN, payload.to_stage)
    kind = steps[keys.index(payload.to_stage)].kind
    if kind != MANUAL:
        raise _invalid("to_stage", STAGE_LIVE if kind == LIVE else STAGE_VOLUME, payload.to_stage)
    if payload.to_stage == org.pipeline_stage:
        raise _invalid("to_stage", STAGE_SAME, payload.to_stage)
    backward = keys.index(payload.to_stage) < keys.index(org.pipeline_stage)
    if backward and payload.note is None:
        raise _invalid("note", NOTE_REQUIRED, payload.note)
    return backward


def record_event(db: AsyncSession, user: User, org: BdmOrganization, kind: str, from_stage: str, to_stage: str, note: str | None) -> None:
    db.add(BdmPipelineEvent(organization_id=org.id, actor_user_id=user.id, kind=kind, from_stage=from_stage, to_stage=to_stage, note=note))


def log_conflict(user: User, org: BdmOrganization, to_stage: str) -> None:
    """Operational signal for two people (or two tabs) moving one organization; ids and keys only."""
    from app.services.bdm_organizations import log  # local: bdm_organizations imports this module

    log("bdm_org_stage_conflict", user, org.id, current_stage=org.pipeline_stage, to_stage=to_stage)
```

- [ ] **Step 4: Router** — `apps/api/app/api/bdm_pipeline.py`:

```python
"""bdm-004 (DEC-SCOPE-070, spec §6.3): stage moves, Lost / Revive, stage history and the pipeline view.

Every `{org_id}` resolves through `services.bdm_organizations.load_scoped` (out of scope = 404); every write is one transaction --
scope, row lock, `require(can_edit)` (S1: the assigned BDM or super_admin), the pipeline rules, change + history row + audit row,
one commit here, then the log line."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import BdmOrganizationEnvelope, BdmStageMove
from app.services import bdm_organizations as org_svc
from app.services import bdm_pipeline as svc

router = APIRouter(prefix="/bdm", tags=["bdm-pipeline"])


@router.post("/organizations/{org_id}/stage", response_model=BdmOrganizationEnvelope)
async def move_stage(org_id: UUID, payload: BdmStageMove, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """S6: any manual stage; backward needs a note; a stale `from_stage` is 409 `stage_changed`."""
    org = await org_svc.load_scoped(db, user, org_id, lock=True)
    org_svc.require(user, org, "can_edit", "stage")
    backward = svc.check_move(user, org, payload)
    from_stage = org.pipeline_stage
    org.pipeline_stage = payload.to_stage
    svc.record_event(db, user, org, "move", from_stage, payload.to_stage, payload.note)
    org_svc.audit(db, user, "stage_changed", org.id, {"from": from_stage, "to": payload.to_stage, "backward": backward, "note": payload.note is not None})
    await db.commit()
    org_svc.log("bdm_org_stage_changed", user, org.id, from_stage=from_stage, to_stage=payload.to_stage, backward=backward)
    return {"organization": await org_svc.organization_out(db, user, org)}
```

In `apps/api/app/main.py` add `bdm_pipeline` to the `from app.api import ...` line(s) that import `bdm_organizations`, and
`bdm_pipeline.router,` immediately after `bdm_organizations.router,` in the router tuple.

- [ ] **Step 5: Run** `<P>` = `tests/test_bdm_004_stage.py tests/test_bdm_004_concurrency.py tests/test_bdm_004_scope.py::test_refusals_are_explained_and_unknown_ids_look_out_of_scope`.
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/bdm_pipeline.py apps/api/app/api/bdm_pipeline.py apps/api/app/main.py apps/api/tests/test_bdm_004_stage.py apps/api/tests/test_bdm_004_scope.py apps/api/tests/test_bdm_004_concurrency.py
git commit -m "feat(bdm-004): POST /bdm/organizations/{id}/stage with history, audit and stale-move 409"
```

---

### Task 6: Lost and Revive

**Files:**
- Modify: `apps/api/app/api/bdm_pipeline.py`
- Test: `apps/api/tests/test_bdm_004_lost.py`

**Interfaces:**
- Consumes: `svc.LOST_CONFLICT`, `svc.NOT_LOST_CONFLICT`, `svc.record_event`; `BdmLostIn`, `BdmReviveIn`.
- Produces: `POST /bdm/organizations/{id}/lost`, `POST /bdm/organizations/{id}/revive` → `{organization}`.

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_bdm_004_lost.py`:

```python
"""bdm-004 -- Lost / Revive (S5; AC2, AC8)."""

import pytest

from tests.bdm001_helpers import login
from tests.bdm002_helpers import ORGS, create_org
from tests.bdm003_helpers import bdm_of
from tests.bdm004_helpers import audits, events, move, url


async def _org_at(client, db, stage: str = "proposal"):
    await login(client, await bdm_of(db, "college"))
    org = await create_org(client)
    return (await move(client, org, stage)).json()["organization"]


@pytest.mark.asyncio
async def test_lost_keeps_the_stage_and_needs_a_reason(client, db_session):
    org = await _org_at(client, db_session)
    blank = await client.post(url(org["id"], "lost"), json={"reason": "  "})
    assert blank.status_code == 422 and blank.json()["detail"][0]["loc"][-1] == "reason"
    response = await client.post(url(org["id"], "lost"), json={"reason": "No budget this year"})
    assert response.status_code == 200, response.text
    p = response.json()["organization"]["pipeline"]
    assert p["stage"] == "proposal" and p["lost"]["reason"] == "No budget this year" and p["lost"]["at"]
    last = (await events(db_session, org["id"]))[-1]
    assert (last.kind, last.from_stage, last.to_stage, last.note) == ("lost", "proposal", "proposal", "No budget this year")
    [audit] = await audits(db_session, org["id"], "lost")
    assert audit.metadata_json == {"stage": "proposal"}


@pytest.mark.asyncio
async def test_a_lost_organization_cannot_move_or_be_lost_again(client, db_session):
    org = await _org_at(client, db_session)
    await client.post(url(org["id"], "lost"), json={"reason": "Went with a competitor"})
    moved = await move(client, org, "mou_signed")
    assert moved.status_code == 409 and moved.json()["detail"]["code"] == "organization_lost"
    again = await client.post(url(org["id"], "lost"), json={"reason": "Again"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "organization_lost"


@pytest.mark.asyncio
async def test_revive_returns_to_the_same_stage(client, db_session):
    org = await _org_at(client, db_session)
    await client.post(url(org["id"], "lost"), json={"reason": "Paused"})
    assert (await client.post(url(org["id"], "revive"), json={})).status_code == 422
    response = await client.post(url(org["id"], "revive"), json={"reason": "New principal is keen"})
    assert response.status_code == 200
    p = response.json()["organization"]["pipeline"]
    assert (p["stage"], p["lost"]) == ("proposal", None)
    last = (await events(db_session, org["id"]))[-1]
    assert (last.kind, last.from_stage, last.to_stage, last.note) == ("revived", "proposal", "proposal", "New principal is keen")
    [audit] = await audits(db_session, org["id"], "revived")
    assert audit.metadata_json == {"stage": "proposal"}
    assert (await move(client, response.json()["organization"], "mou_negotiation")).status_code == 200


@pytest.mark.asyncio
async def test_revive_when_not_lost_is_409(client, db_session):
    org = await _org_at(client, db_session)
    response = await client.post(url(org["id"], "revive"), json={"reason": "x"})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "organization_not_lost"


@pytest.mark.asyncio
async def test_archived_refuses_lost_and_revive(client, db_session):
    org = await _org_at(client, db_session)
    await client.post(f"{ORGS}/{org['id']}/archive")
    for action in ("lost", "revive"):
        response = await client.post(url(org["id"], action), json={"reason": "x"})
        assert response.status_code == 409 and response.json()["detail"] == "Restore this organization first"
```

- [ ] **Step 2: Run** (`<P>` = `tests/test_bdm_004_lost.py`). Expected: FAIL 404/405 on `/lost`.

- [ ] **Step 3: Implement** — append to `apps/api/app/api/bdm_pipeline.py` (add `from datetime import UTC, datetime`,
`from fastapi import HTTPException`, and `BdmLostIn, BdmReviveIn` to the schema import):

```python
@router.post("/organizations/{org_id}/lost", response_model=BdmOrganizationEnvelope)
async def mark_lost(org_id: UUID, payload: BdmLostIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """S5: a flag with a reason on top of the stage; the stage is kept."""
    org = await org_svc.load_scoped(db, user, org_id, lock=True)
    org_svc.require(user, org, "can_edit", "lost")
    if org.lost_at is not None:
        raise HTTPException(409, svc.LOST_CONFLICT)
    org.lost_at, org.lost_reason = datetime.now(UTC), payload.reason
    svc.record_event(db, user, org, "lost", org.pipeline_stage, org.pipeline_stage, payload.reason)
    org_svc.audit(db, user, "lost", org.id, {"stage": org.pipeline_stage})
    await db.commit()
    org_svc.log("bdm_org_lost", user, org.id, stage=org.pipeline_stage)
    return {"organization": await org_svc.organization_out(db, user, org)}


@router.post("/organizations/{org_id}/revive", response_model=BdmOrganizationEnvelope)
async def revive(org_id: UUID, payload: BdmReviveIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """S5: clears the flag with a reason; the organization is back at the stage it was lost at."""
    org = await org_svc.load_scoped(db, user, org_id, lock=True)
    org_svc.require(user, org, "can_edit", "revive")
    if org.lost_at is None:
        raise HTTPException(409, svc.NOT_LOST_CONFLICT)
    org.lost_at = org.lost_reason = None
    svc.record_event(db, user, org, "revived", org.pipeline_stage, org.pipeline_stage, payload.reason)
    org_svc.audit(db, user, "revived", org.id, {"stage": org.pipeline_stage})
    await db.commit()
    org_svc.log("bdm_org_revived", user, org.id, stage=org.pipeline_stage)
    return {"organization": await org_svc.organization_out(db, user, org)}
```

- [ ] **Step 4: Run** `<P>` = `tests/test_bdm_004_lost.py tests/test_bdm_004_stage.py`. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/bdm_pipeline.py apps/api/tests/test_bdm_004_lost.py
git commit -m "feat(bdm-004): mark lost and revive with reason, history and audit (S5)"
```

---

### Task 7: Stage history

**Files:**
- Modify: `apps/api/app/services/bdm_pipeline.py`, `apps/api/app/api/bdm_pipeline.py`
- Test: `apps/api/tests/test_bdm_004_history.py`

**Interfaces:**
- Produces: `bdm_pipeline.history_page(db, org, limit, offset) -> dict` (`{items, total, limit, offset}`, newest first);
  `GET /bdm/organizations/{id}/stage-history`.

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_bdm_004_history.py`:

```python
"""bdm-004 -- the stage history (spec §6.3; AC2): newest first, labels, actor, note; readable in the read scope."""

import pytest

from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm004_helpers import move, url


@pytest.mark.asyncio
async def test_history_is_newest_first_with_labels_actor_and_note(client, db_session):
    manager = await make_manager(db_session)
    bdm = await make_bdm(db_session, manager, "school")
    await login(client, bdm)
    org = await create_org(client)
    empty = (await client.get(url(org["id"], "stage-history"))).json()
    assert empty == {"items": [], "total": 0, "limit": 50, "offset": 0}
    org = (await move(client, org, "presentation")).json()["organization"]
    org = (await move(client, org, "contacted", note="Back to basics")).json()["organization"]
    await client.post(url(org["id"], "lost"), json={"reason": "Board changed"})
    page = (await client.get(url(org["id"], "stage-history"), params={"limit": 2})).json()
    assert page["total"] == 3 and page["limit"] == 2 and len(page["items"]) == 2
    lost, back = page["items"]
    assert (lost["kind"], lost["from_label"], lost["to_label"], lost["note"]) == ("lost", "Contacted", "Contacted", "Board changed")
    assert (back["kind"], back["from_label"], back["to_label"], back["note"]) == ("move", "Presentation", "Contacted", "Back to basics")
    assert back["actor"] == {"id": str(bdm.id), "full_name": bdm.full_name}
    first = (await client.get(url(org["id"], "stage-history"), params={"limit": 2, "offset": 2})).json()["items"]
    assert [(e["from_label"], e["to_label"]) for e in first] == [("School Prospect", "Presentation")]
    await login(client, manager)  # S1: the manager reads the team's history
    assert (await client.get(url(org["id"], "stage-history"))).json()["total"] == 3
```

- [ ] **Step 2: Run** (`<P>` = `tests/test_bdm_004_history.py`). Expected: FAIL 404 (route missing).

- [ ] **Step 3: Implement.** Append to `services/bdm_pipeline.py` (add `from sqlalchemy import func, select` to its imports):

```python
async def history_page(db: AsyncSession, org: BdmOrganization, limit: int, offset: int) -> dict:
    where = BdmPipelineEvent.organization_id == org.id
    total = await db.scalar(select(func.count()).select_from(BdmPipelineEvent).where(where))
    stmt = select(BdmPipelineEvent, User).join(User, User.id == BdmPipelineEvent.actor_user_id).where(where)
    rows = (await db.execute(stmt.order_by(BdmPipelineEvent.position.desc()).limit(limit).offset(offset))).all()
    items = [
        {
            "id": e.id, "kind": e.kind, "from_stage": e.from_stage, "from_label": label_of(org.bdm_type, e.from_stage),
            "to_stage": e.to_stage, "to_label": label_of(org.bdm_type, e.to_stage), "note": e.note,
            "actor": {"id": actor.id, "full_name": actor.full_name}, "created_at": e.created_at,
        }
        for e, actor in rows
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}
```

Append to `api/bdm_pipeline.py` (add `from app.api.bdm import LIMIT, OFFSET` and `BdmStageEventPage` to imports):

```python
@router.get("/organizations/{org_id}/stage-history", response_model=BdmStageEventPage)
async def stage_history(org_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Readable by everyone who can read the organization (bdm, its manager, super_admin)."""
    org = await org_svc.load_scoped(db, user, org_id)
    return await svc.history_page(db, org, limit, offset)
```

- [ ] **Step 4: Run** `<P>` = `tests/test_bdm_004_history.py tests/test_bdm_004_scope.py`. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/bdm_pipeline.py apps/api/app/api/bdm_pipeline.py apps/api/tests/test_bdm_004_history.py
git commit -m "feat(bdm-004): GET stage-history, newest first with labels and actor"
```

---

### Task 8: Pipeline view `GET /bdm/pipeline`

**Files:**
- Modify: `apps/api/app/services/bdm_pipeline.py`, `apps/api/app/api/bdm_pipeline.py`
- Test: `apps/api/tests/test_bdm_004_pipeline.py`

**Interfaces:**
- Consumes: `org_svc.caller_scope`, `services.bdm.bdm_context`, `services.bdm.person_ref`, `api.bdm_organizations._assigned`.
- Produces: `bdm_pipeline.LOST = "lost"`; `bdm_pipeline.view_type(db, user, bdm_type) -> str`;
  `bdm_pipeline.pipeline_view(db, filters, bdm_type, stage, limit, offset) -> dict`.

- [ ] **Step 1: Write the failing test** — `apps/api/tests/test_bdm_004_pipeline.py`:

```python
"""bdm-004 -- the pipeline view (S7; AC5): per-stage counts in scope, Lost apart, archived excluded, list per stage.

The shared database is never truncated: exact counts use a fresh BDM (`assigned=me`) or a fresh manager's team; whole-module counts
are compared as before / after deltas."""

import pytest

from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import ORGS, create_org, make_bdm
from tests.bdm004_helpers import PIPELINE, move, url


def _counts(view) -> dict:
    return {s["key"]: s["count"] for s in view["stages"]}


async def _seed(client, bdm):
    """Prospect x1, Contacted x2 (one of them lost), Proposal x1 archived."""
    await login(client, bdm)
    a = await create_org(client)
    b = (await move(client, await create_org(client), "contacted")).json()["organization"]
    c = (await move(client, await create_org(client), "contacted")).json()["organization"]
    await client.post(url(c["id"], "lost"), json={"reason": "No budget"})
    d = (await move(client, await create_org(client), "proposal")).json()["organization"]
    await client.post(f"{ORGS}/{d['id']}/archive")
    return a, b, c, d


@pytest.mark.asyncio
async def test_my_pipeline_counts_and_lists(client, db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session), "college")
    a, b, c, _ = await _seed(client, bdm)
    view = (await client.get(PIPELINE, params={"assigned": "me"})).json()
    assert view["bdm_type"] == "college"
    counts = _counts(view)
    assert (counts["prospect"], counts["contacted"], counts["proposal"]) == (1, 1, 0)
    assert counts["placement"] is None and counts["course_promotion"] is None  # volumes: not tracked
    assert view["lost_count"] == 1
    assert {i["id"] for i in view["items"]} == {a["id"], b["id"]} and view["total"] == 2  # all open, archived and lost excluded
    contacted = (await client.get(PIPELINE, params={"assigned": "me", "stage": "contacted"})).json()
    assert [(i["id"], i["stage_label"], i["lost"]) for i in contacted["items"]] == [(b["id"], "Contacted", False)]
    lost = (await client.get(PIPELINE, params={"assigned": "me", "stage": "lost"})).json()
    assert [(i["id"], i["lost"]) for i in lost["items"]] == [(c["id"], True)]
    assert (await client.get(PIPELINE, params={"assigned": "me", "stage": "placement"})).json()["items"] == []
    paged = (await client.get(PIPELINE, params={"assigned": "me", "limit": 1, "offset": 1})).json()
    assert paged["total"] == 2 and len(paged["items"]) == 1


@pytest.mark.asyncio
async def test_whole_module_toggle_counts_peers(client, db_session):
    manager = await make_manager(db_session)
    me, peer = await make_bdm(db_session, manager, "agent"), await make_bdm(db_session, manager, "agent")
    await login(client, me)
    before = _counts((await client.get(PIPELINE)).json())
    await login(client, peer)
    await create_org(client)
    await login(client, me)
    after = _counts((await client.get(PIPELINE)).json())
    assert after["prospect"] - before["prospect"] >= 1
    assert _counts((await client.get(PIPELINE, params={"assigned": "me"})).json())["prospect"] == 0


@pytest.mark.asyncio
async def test_type_rules(client, db_session):
    manager = await make_manager(db_session)
    bdm = await make_bdm(db_session, manager, "school")
    await login(client, bdm)
    assert (await client.get(PIPELINE, params={"bdm_type": "school"})).status_code == 200
    other = await client.get(PIPELINE, params={"bdm_type": "college"})
    assert other.status_code == 422 and other.json()["detail"] == "You can only view your own module's pipeline"
    assert (await client.get(PIPELINE, params={"stage": "college_activated"})).status_code == 422  # another type's key
    assert (await client.get(PIPELINE, params={"stage": "<script>"})).status_code == 422
    await login(client, manager)
    missing = await client.get(PIPELINE)
    assert missing.status_code == 422 and missing.json()["detail"] == "Choose a BDM type"
    assert (await client.get(PIPELINE, params={"bdm_type": "school", "assigned": "me"})).status_code == 422  # `me` is BDM-only


@pytest.mark.asyncio
async def test_manager_sees_their_team_and_one_bdm(client, db_session):
    manager = await make_manager(db_session)
    first, second = await make_bdm(db_session, manager, "college"), await make_bdm(db_session, manager, "college")
    await _seed(client, first)
    await login(client, second)
    await create_org(client)
    outsider = await make_bdm(db_session, await make_manager(db_session), "college")
    await login(client, outsider)
    await create_org(client)
    await login(client, manager)
    team = (await client.get(PIPELINE, params={"bdm_type": "college"})).json()
    assert (_counts(team)["prospect"], _counts(team)["contacted"], team["lost_count"]) == (2, 1, 1)
    one = (await client.get(PIPELINE, params={"bdm_type": "college", "assigned": str(second.id)})).json()
    assert (_counts(one)["prospect"], one["total"]) == (1, 1)
    assert (await client.get(PIPELINE, params={"bdm_type": "college", "assigned": str(outsider.id)})).json()["total"] == 0


@pytest.mark.asyncio
async def test_super_admin_sees_every_bdm_and_other_roles_are_refused(client, db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session), "school")
    admin = await make_user(db_session, "super_admin", "global")
    await login(client, admin)
    before = _counts((await client.get(PIPELINE, params={"bdm_type": "school"})).json())["prospect"]
    await login(client, bdm)
    await create_org(client)
    await login(client, admin)
    assert _counts((await client.get(PIPELINE, params={"bdm_type": "school"})).json())["prospect"] - before >= 1
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(PIPELINE, params={"bdm_type": "school"})).status_code == 403
```

- [ ] **Step 2: Run** (`<P>` = `tests/test_bdm_004_pipeline.py`). Expected: FAIL 404 (route missing).

- [ ] **Step 3: Service** — append to `services/bdm_pipeline.py` (add `from app.services.bdm import bdm_context, person_ref`):

```python
LOST = "lost"  # the pipeline view's Lost bucket (S5)
TYPE_REQUIRED = "Choose a BDM type"
TYPE_NOT_YOURS = "You can only view your own module's pipeline"
VIEW_STAGE_UNKNOWN = "Choose a stage of this pipeline"


async def view_type(db: AsyncSession, user: User, bdm_type: str | None) -> str:
    """S7: a BDM sees their own module; a manager / super_admin names the type (a team may mix types, D26). Call after
    caller_scope, which refuses other roles with 403."""
    if user.role == "bdm":
        own = (await bdm_context(db, user)).bdm_type
        if bdm_type not in (None, own):
            raise HTTPException(422, TYPE_NOT_YOURS)
        return own
    if bdm_type is None:
        raise HTTPException(422, TYPE_REQUIRED)
    return bdm_type


async def pipeline_view(db: AsyncSession, filters: list, bdm_type: str, stage: str | None, limit: int, offset: int) -> dict:
    """One grouped count over the (bdm_type, pipeline_stage) index, then one page. Archived organizations are excluded; Lost ones are
    counted only in lost_count and listed only under stage=lost."""
    steps = PIPELINES[bdm_type]
    if stage is not None and stage != LOST and stage not in {s.key for s in steps}:
        raise HTTPException(422, VIEW_STAGE_UNKNOWN)
    scope = [*filters, BdmOrganization.bdm_type == bdm_type, BdmOrganization.archived_at.is_(None)]
    is_lost = BdmOrganization.lost_at.is_not(None)
    grouped = (await db.execute(select(BdmOrganization.pipeline_stage, is_lost, func.count()).where(*scope).group_by(BdmOrganization.pipeline_stage, is_lost))).all()
    counts = {key: n for key, lost, n in grouped if not lost}
    lost_count = sum(n for _, lost, n in grouped if lost)
    page = [*scope, is_lost if stage == LOST else BdmOrganization.lost_at.is_(None)]
    if stage not in (None, LOST):
        page.append(BdmOrganization.pipeline_stage == stage)
    total = await db.scalar(select(func.count()).select_from(BdmOrganization).where(*page))
    stmt = select(BdmOrganization, User).join(User, User.id == BdmOrganization.assigned_bdm_user_id).where(*page)
    rows = (await db.execute(stmt.order_by(BdmOrganization.name, BdmOrganization.id).limit(limit).offset(offset))).all()
    return {
        "bdm_type": bdm_type,
        "stages": [{"key": s.key, "label": s.label, "kind": s.kind, "count": counts.get(s.key, 0) if s.kind == MANUAL else None} for s in steps],
        "lost_count": lost_count,
        "items": [
            {
                "id": org.id, "code": org.code, "name": org.name, "city": org.city, "org_type": org.org_type, "assigned_bdm": person_ref(assignee),
                "stage": org.pipeline_stage, "stage_label": label_of(bdm_type, org.pipeline_stage), "lost": org.lost_at is not None,
            }
            for org, assignee in rows
        ],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }
```

Append to `api/bdm_pipeline.py` (add `from fastapi import Query`; `from app.api.bdm_organizations import _assigned`;
`from app.models import BdmOrganization`; `BdmPipelinePage, BdmType` to the schema import):

```python
@router.get("/pipeline", response_model=BdmPipelinePage)
async def pipeline(
    bdm_type: BdmType | None = None,
    assigned: str | None = Query(None, max_length=36),
    stage: str | None = Query(None, max_length=40),
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """S7: counts per stage in the caller's read scope (bdm: module; manager: team; super_admin: all), optionally one assignee
    (`me` or a BDM id, the organization list's rule); the page lists one stage, `lost`, or every open organization."""
    filters = await org_svc.caller_scope(db, user)
    chosen = await svc.view_type(db, user, bdm_type)
    assignee = _assigned(user, assigned)
    if assignee is not None:
        filters.append(BdmOrganization.assigned_bdm_user_id == assignee)
    return await svc.pipeline_view(db, filters, chosen, stage, limit, offset)
```

- [ ] **Step 4: Run** `<P>` = `tests/test_bdm_004_pipeline.py`. Expected: all pass.

- [ ] **Step 5: Backend lite + ruff**

Run: backend command with `<P>` = LITE (backend), then
`... api-test sh -c "python -m ruff check app/bdm_stages.py app/services/bdm_pipeline.py app/api/bdm_pipeline.py alembic/versions/0072_bdm_pipeline.py tests/test_bdm_004_*.py tests/bdm004_helpers.py"`.
Expected: all pass; ruff clean. REFACTOR now if anything reads awkwardly (no behavior change), then rerun.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/bdm_pipeline.py apps/api/app/api/bdm_pipeline.py apps/api/tests/test_bdm_004_pipeline.py
git commit -m "feat(bdm-004): GET /bdm/pipeline -- per-stage counts in scope, Lost bucket, list per stage"
```

---

### Task 9: Web client library, navigation, server loaders

**Files:**
- Create: `apps/web/lib/bdmPipeline.ts`, `apps/web/lib/bdmPipelineServer.ts`
- Modify: `apps/web/lib/bdmOrganizations.ts:35-38` (`Organization.pipeline`), `apps/web/lib/navigation.ts:44-60`,
  `apps/web/lib/bdmActivities.ts` (`appendUnique` generic)
- Test: `apps/web/tests/lib/bdmPipeline.test.ts`, `apps/web/tests/lib/navigation.bdm.test.ts`

**Interfaces:**
- Produces (`lib/bdmPipeline.ts`): types `StepKind`, `StepState`, `PipelineStep`, `Pipeline`, `StageEvent`, `StageCount`,
  `PipelineItem`, `PipelineView`, `PipelineParams`; constants `PIPELINE_URL = "/api/v1/bdm/pipeline"`, `LOST = "lost"`,
  `HISTORY_PAGE = 20`, `STATE_TEXT`; functions `orgActionUrl(orgId, action: "stage" | "lost" | "revive")`,
  `historyUrl(orgId, offset = 0)`, `isBackward(p, to)`, `stageChanged(detail): string | null`, `fieldErrors(detail)`,
  `pipelineQuery(params)`.
- Produces (`lib/bdmPipelineServer.ts`): `firstStageHistory(id): Promise<Page<StageEvent> | null>`,
  `readPipeline(params): Promise<PipelineView | "invalid">`.
- `appendUnique<T extends { id: string }>(current: T[], incoming: T[]): T[]`.

- [ ] **Step 1: Write the failing tests** — `apps/web/tests/lib/bdmPipeline.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { fieldErrors, historyUrl, isBackward, orgActionUrl, type Pipeline, pipelineQuery, stageChanged } from "@/lib/bdmPipeline";

const pipeline = (stage: string): Pipeline => ({
  stage, stage_label: stage, lost: null, agent_status: null,
  steps: ["prospect", "contacted", "meeting", "proposal"].map((key) => ({ key, label: key, kind: "manual", state: "upcoming" })),
});

describe("bdm-004 pipeline helpers", () => {
  it("builds the organization action and history URLs", () => {
    expect(orgActionUrl("o1", "stage")).toBe("/api/v1/bdm/organizations/o1/stage");
    expect(historyUrl("o1", 20)).toBe("/api/v1/bdm/organizations/o1/stage-history?limit=20&offset=20");
  });

  it("knows a backward move from the catalogue order", () => {
    expect(isBackward(pipeline("meeting"), "contacted")).toBe(true);
    expect(isBackward(pipeline("meeting"), "proposal")).toBe(false);
  });

  it("reads the stale-move 409 and the field 422s", () => {
    expect(stageChanged({ code: "stage_changed", current_stage: "contacted", message: "x" })).toBe("contacted");
    expect(stageChanged("Restore this organization first")).toBeNull();
    expect(fieldErrors([{ loc: ["body", "note"], msg: "Value error, Note contains invalid characters" }, { loc: ["body", "to_stage"], msg: "Choose a stage" }]))
      .toEqual({ note: "Note contains invalid characters", to_stage: "Choose a stage" });
    expect(fieldErrors("plain")).toEqual({});
  });

  it("drops empty filters from the query", () => {
    expect(pipelineQuery({ assigned: "me", stage: undefined, offset: 0 })).toBe("assigned=me&limit=50&offset=0");
    expect(pipelineQuery({ bdm_type: "school", stage: "lost", offset: 50 })).toBe("bdm_type=school&stage=lost&limit=50&offset=50");
  });
});
```

In `apps/web/tests/lib/navigation.bdm.test.ts` change the two expected lists to:

```ts
    expect(BDM_NAV.map((x) => x.href)).toEqual([
      "/bdm/my-day", "/bdm/organizations", "/bdm/pipeline", "/bdm/appointments", "/bdm/activities", "/bdm/travel", "/bdm/notifications", "/bdm/profile",
    ]);
    expect(BDM_MANAGER_NAV.map((x) => x.href)).toEqual([
      "/bdm/manager/dashboard", "/bdm/manager/team", "/bdm/manager/organizations", "/bdm/manager/pipeline", "/bdm/manager/appointments",
      "/bdm/manager/activities", "/bdm/manager/approvals", "/bdm/manager/notifications",
    ]);
```

- [ ] **Step 2: Run** the web command with `npx vitest run tests/lib/bdmPipeline.test.ts tests/lib/navigation.bdm.test.ts`.
Expected: FAIL — cannot resolve `@/lib/bdmPipeline`; nav lists differ.

- [ ] **Step 3: Implement** `apps/web/lib/bdmPipeline.ts`:

```ts
import { detailMessage } from "@/lib/apiErrors";
import type { BdmType } from "@/lib/bdm";
import { PAGE_SIZE } from "@/lib/bdm";
import { ORGS_URL, type OrgPerson, type OrgType } from "@/lib/bdmOrganizations";

// bdm-004 (DEC-SCOPE-070): the organization pipeline. The API owns the catalogue (labels, kinds, states come with every organization)
// and every rule; these helpers only shape requests and read responses.
export type StepKind = "manual" | "live" | "volume";
export type StepState = "done" | "current" | "upcoming" | "awaiting_handover" | "not_tracked";
export type PipelineStep = { key: string; label: string; kind: StepKind; state: StepState };
export type Pipeline = { stage: string; stage_label: string; lost: { at: string; reason: string } | null; agent_status: string | null; steps: PipelineStep[] };
export type StageEvent = {
  id: string; kind: "move" | "lost" | "revived"; from_stage: string; from_label: string; to_stage: string; to_label: string;
  note: string | null; actor: { id: string; full_name: string }; created_at: string;
};
export type StageCount = { key: string; label: string; kind: StepKind; count: number | null };
export type PipelineItem = { id: string; code: string; name: string; city: string; org_type: OrgType; assigned_bdm: OrgPerson; stage: string; stage_label: string; lost: boolean };
export type PipelineView = { bdm_type: BdmType; stages: StageCount[]; lost_count: number; items: PipelineItem[]; total: number; limit: number; offset: number };
export type PipelineParams = { bdm_type?: BdmType; assigned?: string; stage?: string; offset?: number };

export const PIPELINE_URL = "/api/v1/bdm/pipeline";
export const LOST = "lost";
export const HISTORY_PAGE = 20;
export const STATE_TEXT: Record<StepState, string> = {
  done: "Done", current: "Current", upcoming: "Upcoming", awaiting_handover: "Awaiting handover", not_tracked: "Not tracked",
};

export const orgActionUrl = (orgId: string, action: "stage" | "lost" | "revive") => `${ORGS_URL}/${orgId}/${action}`;
export const historyUrl = (orgId: string, offset = 0) => `${ORGS_URL}/${orgId}/stage-history?limit=${HISTORY_PAGE}&offset=${offset}`;

/** S6: moving to an earlier stage needs a note. */
export function isBackward(p: Pipeline, to: string): boolean {
  const keys = p.steps.map((s) => s.key);
  return keys.indexOf(to) < keys.indexOf(p.stage);
}

/** The 409 `stage_changed` body names the stage someone else moved the organization to. */
export function stageChanged(detail: unknown): string | null {
  const d = detail as { code?: unknown; current_stage?: unknown } | null;
  return d && typeof d === "object" && d.code === "stage_changed" && typeof d.current_stage === "string" ? d.current_stage : null;
}

/** FastAPI's 422 list as {field: message}, worded by detailMessage (no "Value error," prefix). */
export function fieldErrors(detail: unknown): Record<string, string> {
  if (!Array.isArray(detail)) return {};
  return Object.fromEntries(detail.map((d: { loc?: unknown[] }) => [String(d?.loc?.at(-1) ?? ""), detailMessage([d])]));
}

export function pipelineQuery(params: PipelineParams): string {
  const q = new URLSearchParams();
  if (params.bdm_type) q.set("bdm_type", params.bdm_type);
  if (params.assigned) q.set("assigned", params.assigned);
  if (params.stage) q.set("stage", params.stage);
  q.set("limit", String(PAGE_SIZE));
  q.set("offset", String(params.offset ?? 0));
  return q.toString();
}
```

`apps/web/lib/bdmPipelineServer.ts`:

```ts
import { ApiError, serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { historyUrl, PIPELINE_URL, type PipelineParams, pipelineQuery, type PipelineView, type StageEvent } from "@/lib/bdmPipeline";
import { isUuid } from "@/lib/bdmTravel";

// Server-only (serverApi reads next/headers): kept out of lib/bdmPipeline.ts, which client components import.
/** The organization pages' first history page, read alongside the organization (the firstActivityPage pattern). Never rejects: a
 * failure is null and the section offers "Try again"; a malformed id isn't sent. */
export function firstStageHistory(id: string): Promise<Page<StageEvent> | null> {
  return isUuid(id) ? serverApi<Page<StageEvent>>(historyUrl(id)).catch(() => null) : Promise.resolve(null);
}

/** A hand-edited address (unknown stage, another module) is "invalid", shown with a reset link; anything else is the page's error. */
export async function readPipeline(params: PipelineParams): Promise<PipelineView | "invalid"> {
  try {
    return await serverApi<PipelineView>(`${PIPELINE_URL}?${pipelineQuery(params)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) return "invalid";
    throw e;
  }
}
```

`lib/bdmOrganizations.ts`: add `import type { Pipeline } from "@/lib/bdmPipeline";` and in `Organization` add
`pipeline: Pipeline;` after `profile: OrgProfile | null;`.

`lib/bdmActivities.ts`: make `appendUnique` generic (same body):

```ts
export function appendUnique<T extends { id: string }>(current: T[], incoming: T[]): T[] {
  return [...current, ...incoming.filter((a) => !current.some((c) => c.id === a.id))];
}
```

`lib/navigation.ts`: add to the comment block `// bdm-004: Pipeline in both.`; in `BDM_NAV` insert
`{ label: "Pipeline", href: "/bdm/pipeline" },` after Organizations; in `BDM_MANAGER_NAV` insert
`{ label: "Pipeline", href: "/bdm/manager/pipeline" },` after Organizations.

`tests/components/BdmOrganizationDetail.test.tsx`: the `org()` fixture gains (after `profile: null,`)
`pipeline: { stage: "prospect", stage_label: "College Prospect", lost: null, agent_status: null, steps: [] },`.

- [ ] **Step 4: Run** `npx vitest run tests/lib/bdmPipeline.test.ts tests/lib/navigation.bdm.test.ts tests/lib/bdmActivities.test.ts tests/components/BdmOrganizationDetail.test.tsx`
then `npx tsc --noEmit`. Expected: pass; tsc 0 errors (fix any fixture typed as `Organization` that tsc names, by adding the same
`pipeline` value).

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/bdmPipeline.ts apps/web/lib/bdmPipelineServer.ts apps/web/lib/bdmOrganizations.ts apps/web/lib/bdmActivities.ts apps/web/lib/navigation.ts apps/web/tests/lib/bdmPipeline.test.ts apps/web/tests/lib/navigation.bdm.test.ts apps/web/tests/components/BdmOrganizationDetail.test.tsx
git commit -m "feat(bdm-004): web pipeline client, server loaders and Pipeline nav items"
```

---

### Task 10: Pipeline section, history and detail integration

**Files:**
- Create: `apps/web/components/BdmOrganizationPipeline.tsx`, `apps/web/components/BdmStageHistory.tsx`
- Modify: `apps/web/components/BdmOrganizationDetail.tsx` (props + render after the confirm, before Details),
  `apps/web/app/bdm/organizations/[id]/page.tsx`, `apps/web/app/bdm/manager/organizations/[id]/page.tsx`
- Test: `apps/web/tests/components/BdmOrganizationPipeline.test.tsx`, `apps/web/tests/components/BdmStageHistory.test.tsx`,
  `apps/web/tests/components/BdmOrganizationPages.test.tsx` (expected props gain `stageHistory: null`)

**Interfaces:**
- Consumes: Task 9 exports; `sendJson`, `sendRequest`, `isPage`, `Page` (`lib/apiErrors`); `isOrganizationBody`, `ORGS_URL`;
  `useFocusAfterRender`; `formatSchoolDateTime`, `formatDate`; `appendUnique`.
- Produces: `<BdmOrganizationPipeline organization onChanged(o, text) />`; `<BdmStageHistory orgId initial version />`;
  `BdmOrganizationDetail` prop `stageHistory?: Page<StageEvent> | null`.

- [ ] **Step 1: Write the failing tests** — `apps/web/tests/components/BdmOrganizationPipeline.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationPipeline from "@/components/BdmOrganizationPipeline";
import type { Organization } from "@/lib/bdmOrganizations";
import type { Pipeline } from "@/lib/bdmPipeline";

const KEYS = [["prospect", "College Prospect", "manual"], ["contacted", "Contacted", "manual"], ["meeting", "Meeting", "manual"], ["placement", "Placement", "volume"]] as const;
const pipeline = (stage = "contacted", over: Partial<Pipeline> = {}): Pipeline => {
  const at = KEYS.findIndex(([k]) => k === stage);
  return {
    stage, stage_label: KEYS[at][1], lost: null, agent_status: null,
    steps: KEYS.map(([key, label, kind], i) => ({ key, label, kind, state: i < at ? "done" : i === at ? "current" : kind === "volume" ? "not_tracked" : "upcoming" })),
    ...over,
  };
};
const org = (p: Pipeline = pipeline(), canEdit = true) =>
  ({ id: "o1", code: "ORG-000001", name: "St Mary", bdm_type: "college", permissions: { can_edit: canEdit, can_archive: canEdit, can_restore: false, can_reassign: false }, pipeline: p }) as unknown as Organization;
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmOrganizationPipeline (bdm-004 §8.2)", () => {
  it("shows every step with its state as text and marks the current one", () => {
    render(<BdmOrganizationPipeline organization={org()} onChanged={vi.fn()} />);
    const steps = screen.getByRole("list", { name: "Pipeline stages" });
    expect(within(steps).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["✓College ProspectDone", "•ContactedCurrent", "–MeetingUpcoming", "–PlacementNot tracked"]);
    expect(within(steps).getByText("Contacted").closest("li")).toHaveAttribute("aria-current", "step");
  });

  it("is read-only without can_edit", () => {
    render(<BdmOrganizationPipeline organization={org(pipeline(), false)} onChanged={vi.fn()} />);
    expect(screen.queryByLabelText("Move to")).toBeNull();
    expect(screen.queryByRole("button", { name: /Mark lost|Revive|Move/ })).toBeNull();
  });

  it("offers only manual stages, the current one disabled, and needs a reason to move back", () => {
    render(<BdmOrganizationPipeline organization={org()} onChanged={vi.fn()} />);
    const select = screen.getByLabelText("Move to") as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual(["Choose a stage", "College Prospect", "Contacted (current)", "Meeting"]);
    expect(select.querySelector('option[value="contacted"]')).toBeDisabled();
    fireEvent.change(select, { target: { value: "prospect" } });
    expect(screen.getByLabelText("Reason (required when moving back)")).toBeRequired();
    fireEvent.change(select, { target: { value: "meeting" } });
    expect(screen.getByLabelText("Note (optional)")).not.toBeRequired();
  });

  it("moves and reports the new stage", async () => {
    const moved = org(pipeline("meeting"));
    const fetchMock = vi.fn().mockResolvedValue(res({ organization: moved }));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    render(<BdmOrganizationPipeline organization={org()} onChanged={onChanged} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "meeting" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(moved, "Moved to Meeting."));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/bdm/organizations/o1/stage");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ from_stage: "contacted", to_stage: "meeting" });
  });

  it("shows a 422 beside its field", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: [{ loc: ["body", "note"], msg: "Add a note to move an organization back" }] }, 422)));
    render(<BdmOrganizationPipeline organization={org()} onChanged={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "prospect" } });
    fireEvent.change(screen.getByLabelText("Reason (required when moving back)"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    const note = screen.getByLabelText("Reason (required when moving back)");
    await waitFor(() => expect(note).toHaveAccessibleDescription("Add a note to move an organization back"));
  });

  it("a refusal keeps the choice and note", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Only the assigned BDM can edit this organization" }, 403)));
    render(<BdmOrganizationPipeline organization={org()} onChanged={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "meeting" } });
    fireEvent.change(screen.getByLabelText("Note (optional)"), { target: { value: "Met the dean" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only the assigned BDM can edit this organization");
    expect(screen.getByLabelText("Move to")).toHaveValue("meeting");
    expect(screen.getByLabelText("Note (optional)")).toHaveValue("Met the dean");
  });

  it("a stale move reloads the organization and says where it is now", async () => {
    const fresh = org(pipeline("prospect"));
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(res({ detail: { code: "stage_changed", current_stage: "prospect", message: "This organization moved to College Prospect meanwhile" } }, 409))
      .mockResolvedValueOnce(res({ organization: fresh })));
    const onChanged = vi.fn();
    render(<BdmOrganizationPipeline organization={org()} onChanged={onChanged} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "meeting" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(fresh, "This organization moved to College Prospect meanwhile. Check the stage and try again."));
  });

  it("a retried move that already landed reads as done", async () => {
    const fresh = org(pipeline("meeting"));
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(res({ detail: { code: "stage_changed", current_stage: "meeting", message: "x" } }, 409))
      .mockResolvedValueOnce(res({ organization: fresh })));
    const onChanged = vi.fn();
    render(<BdmOrganizationPipeline organization={org()} onChanged={onChanged} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "meeting" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(fresh, "Moved to Meeting."));
  });

  it("marks lost with a reason; a lost organization shows the reason and offers Revive only", async () => {
    const lost = org(pipeline("contacted", { lost: { at: "2026-10-05T10:00:00Z", reason: "No budget" } }));
    const fetchMock = vi.fn().mockResolvedValue(res({ organization: lost }));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    const { rerender } = render(<BdmOrganizationPipeline organization={org()} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark lost" }));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "No budget" } });
    fireEvent.click(screen.getByRole("button", { name: "Yes, mark lost" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(lost, "Marked lost."));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ reason: "No budget" });
    rerender(<BdmOrganizationPipeline organization={lost} onChanged={onChanged} />);
    expect(screen.getByText(/Marked lost on/)).toHaveTextContent("No budget");
    expect(screen.queryByLabelText("Move to")).toBeNull();
    expect(screen.getByRole("button", { name: "Revive" })).toBeInTheDocument();
  });

  it("shows the derived agent status", () => {
    render(<BdmOrganizationPipeline organization={org(pipeline("contacted", { agent_status: "Contacted" }))} onChanged={vi.fn()} />);
    expect(screen.getByText("Agent status:")).toHaveTextContent("Agent status: Contacted");
  });
});
```

`apps/web/tests/components/BdmStageHistory.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmStageHistory from "@/components/BdmStageHistory";
import type { StageEvent } from "@/lib/bdmPipeline";

const event = (id: string, over: Partial<StageEvent> = {}): StageEvent => ({
  id, kind: "move", from_stage: "prospect", from_label: "College Prospect", to_stage: "contacted", to_label: "Contacted", note: null,
  actor: { id: "b1", full_name: "Asha" }, created_at: "2026-10-05T10:00:00Z", ...over,
});
const page = (items: StageEvent[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmStageHistory (bdm-004 §8.2)", () => {
  it("lists moves, Lost and Revive with actor and note", () => {
    render(<BdmStageHistory orgId="o1" initial={page([event("e2", { kind: "lost", from_label: "Contacted", to_label: "Contacted", note: "No budget" }), event("e1", { note: "First call" })])} version={0} />);
    const list = screen.getByRole("list", { name: "Stage history" });
    const [lost, moved] = within(list).getAllByRole("listitem");
    expect(lost).toHaveTextContent("Marked lost at Contacted");
    expect(lost).toHaveTextContent("Reason: No budget");
    expect(moved).toHaveTextContent("College Prospect → Contacted");
    expect(moved).toHaveTextContent("By Asha");
    expect(moved).toHaveTextContent("Note: First call");
  });

  it("says when there is no history yet", () => {
    render(<BdmStageHistory orgId="o1" initial={page([])} version={0} />);
    expect(screen.getByText("No stage changes yet.")).toBeInTheDocument();
  });

  it("loads more without repeating rows", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([event("e1"), event("e0")], 3, 1))));
    render(<BdmStageHistory orgId="o1" initial={page([event("e2"), event("e1")], 3)} version={0} />);
    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(3));
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
  });

  it("reloads the first page when the organization changes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(page([event("e9", { to_label: "Meeting" })])));
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(<BdmStageHistory orgId="o1" initial={page([])} version={0} />);
    rerender(<BdmStageHistory orgId="o1" initial={page([])} version={1} />);
    await waitFor(() => expect(screen.getByText("College Prospect → Meeting")).toBeInTheDocument());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/bdm/organizations/o1/stage-history?limit=20&offset=0");
  });

  it("a failed first load offers Try again", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([event("e1")]))));
    render(<BdmStageHistory orgId="o1" initial={null} version={0} />);
    expect(screen.getByText("Unable to load the stage history.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByText("College Prospect → Contacted")).toBeInTheDocument());
  });
});
```

In `apps/web/tests/components/BdmOrganizationPages.test.tsx`, the two `toEqual` prop assertions become
`{ initial: organization, basePath: "/bdm/organizations", created: true, activities: null, stageHistory: null }` and
`{ initial: organization, basePath: "/bdm/manager/organizations", activities: null, stageHistory: null }`.

- [ ] **Step 2: Run** `npx vitest run tests/components/BdmOrganizationPipeline.test.tsx tests/components/BdmStageHistory.test.tsx tests/components/BdmOrganizationPages.test.tsx`.
Expected: FAIL — modules not found; page props lack `stageHistory`.

- [ ] **Step 3: Implement** `apps/web/components/BdmStageHistory.tsx`:

```tsx
"use client";
import { useEffect, useRef, useState } from "react";

import { isPage, type Page } from "@/lib/apiErrors";
import { appendUnique } from "@/lib/bdmActivities";
import { historyUrl, type StageEvent } from "@/lib/bdmPipeline";
import { formatSchoolDateTime } from "@/lib/formatDate";

const UNABLE = "Unable to load the stage history.";

function title(e: StageEvent): string {
  if (e.kind === "lost") return `Marked lost at ${e.to_label}`;
  if (e.kind === "revived") return `Revived at ${e.to_label}`;
  return `${e.from_label} → ${e.to_label}`;
}

// bdm-004 (spec §8.2, AC2): every move, Lost and Revive, newest first; the bdm-006 history look (.jtl). `version` changes after each
// write on this page, which reloads the first page; only the newest request may update the list. Plain text only.
export default function BdmStageHistory({ orgId, initial, version }: { orgId: string; initial: Page<StageEvent> | null; version: number }) {
  const [items, setItems] = useState<StageEvent[]>(initial?.items ?? []);
  const [total, setTotal] = useState(initial?.total ?? 0);
  const [failed, setFailed] = useState(initial === null);
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);

  async function load(offset: number) {
    const ticket = ++latest.current;
    setLoading(true);
    const response = await fetch(historyUrl(orgId, offset)).catch(() => null);
    const data: unknown = response?.ok ? await response.json().catch(() => null) : null;
    if (ticket !== latest.current) return;
    setLoading(false);
    if (!isPage<StageEvent>(data)) {
      if (offset === 0) setFailed(true);
      return;
    }
    setFailed(false);
    setTotal(data.total);
    setItems((current) => (offset === 0 ? data.items : appendUnique(current, data.items)));
  }

  useEffect(() => {
    if (version > 0) void load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only when a write on this page bumps the version
  }, [version]);

  return (
    <section className="action-card wide" aria-label="Stage history">
      <h3>Stage history</h3>
      {failed ? (
        <p className="muted">
          {UNABLE}{" "}
          <button type="button" className="btn secondary small" onClick={() => void load(0)} disabled={loading}>
            Try again
          </button>
        </p>
      ) : items.length === 0 ? (
        <p className="muted">No stage changes yet.</p>
      ) : (
        <ol className="jtl" aria-label="Stage history" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {items.map((e) => (
            <li key={e.id} className="jtl-row">
              <div className="jtl-rail" aria-hidden="true">
                <span className="jtl-node" />
              </div>
              <div>
                <span className="jtl-date">{formatSchoolDateTime(e.created_at, true)}</span>
                <p className="jtl-title">{title(e)}</p>
                <p className="jtl-detail">By {e.actor.full_name}</p>
                {e.note && <p className="jtl-detail" style={{ whiteSpace: "pre-line" }}>{e.kind === "move" ? "Note" : "Reason"}: {e.note}</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
      {!failed && items.length < total && (
        <button type="button" className="btn secondary small" onClick={() => void load(items.length)} disabled={loading}>
          {loading ? "Loading…" : "Show more"}
        </button>
      )}
    </section>
  );
}
```

`apps/web/components/BdmOrganizationPipeline.tsx`:

```tsx
"use client";
import { type FormEvent, useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { isOrganizationBody, type Organization, ORGS_URL } from "@/lib/bdmOrganizations";
import { fieldErrors, isBackward, orgActionUrl, stageChanged, STATE_TEXT } from "@/lib/bdmPipeline";
import { formatDate } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const GLYPH: Record<string, string> = { done: "✓", current: "•", upcoming: "–", awaiting_handover: "…", not_tracked: "–" };

// bdm-004 (spec §8.2): the stepper (state as text, never colour alone), the derived agent status, the Lost banner, and -- for the
// assigned BDM or super_admin (permissions.can_edit) -- Move, Mark lost and Revive. The API enforces every rule; a refusal keeps the
// entry. Each success hands the returned organization to the detail page, which re-renders this section from it.
export default function BdmOrganizationPipeline({ organization: org, onChanged }: { organization: Organization; onChanged: (o: Organization, text: string) => void }) {
  const p = org.pipeline;
  const canWrite = org.permissions.can_edit;
  const [to, setTo] = useState("");
  const [note, setNote] = useState("");
  const [mode, setMode] = useState<"lost" | "revive" | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const id = (part: string) => `pipeline-${org.id}-${part}`;
  const backward = to !== "" && isBackward(p, to);
  const labelOf = (key: string) => p.steps.find((s) => s.key === key)?.label ?? key;

  async function reload(text: string) {
    const fresh = await sendRequest(`${ORGS_URL}/${org.id}`, { method: "GET" });
    if (fresh.ok && isOrganizationBody(fresh.data)) onChanged(fresh.data.organization, text);
    else setFailure(text);
  }

  async function send(action: "stage" | "lost" | "revive", body: Record<string, string>, success: string) {
    setBusy(true);
    setFailure(null);
    setErrors({});
    const outcome = await sendJson(orgActionUrl(org.id, action), "POST", body);
    setBusy(false);
    if (outcome.ok && isOrganizationBody(outcome.data)) {
      setTo("");
      setNote("");
      setReason("");
      setMode(null);
      onChanged(outcome.data.organization, success);
      return;
    }
    if (outcome.ok) return setFailure("Unable to update this organization.");
    const current = stageChanged(outcome.detail);
    if (current !== null) { // Review Focus 1: a retried move that already landed is a success
      setTo("");
      setNote("");
      return void reload(current === body.to_stage ? success : `${(outcome.detail as { message: string }).message}. Check the stage and try again.`);
    }
    const fields = fieldErrors(outcome.detail);
    if (Object.keys(fields).length) setErrors(fields);
    else setFailure(outcome.message);
  }

  function submitMove(event: FormEvent) {
    event.preventDefault();
    void send("stage", { from_stage: p.stage, to_stage: to, ...(note.trim() ? { note } : {}) }, `Moved to ${labelOf(to)}.`);
  }
  function submitFlag(event: FormEvent) {
    event.preventDefault();
    void send(mode === "lost" ? "lost" : "revive", { reason }, mode === "lost" ? "Marked lost." : "Revived.");
  }
  const openFlag = () => {
    setMode(p.lost ? "revive" : "lost");
    focus(id("reason"));
  };
  const cancelFlag = () => {
    setMode(null);
    setReason("");
    focus(id("flag"));
  };
  const fieldError = (field: string) =>
    errors[field] ? <p id={id(`${field}-error`)} className="form-error">{errors[field]}</p> : null;

  return (
    <section className="action-card wide" aria-label="Pipeline">
      <h3>Pipeline</h3>
      {p.agent_status && (
        <p>
          Agent status: <span className="badge">{p.agent_status}</span>
        </p>
      )}
      {p.lost && (
        <p className="form-message" style={{ whiteSpace: "pre-line" }}>
          Marked lost on {formatDate(p.lost.at)}: {p.lost.reason}
        </p>
      )}
      <ol className="jny-steps" aria-label="Pipeline stages">
        {p.steps.map((s) => (
          <li key={s.key} className={`jny-step jny-${s.state}`} aria-current={s.state === "current" ? "step" : undefined}>
            <span className="jny-glyph" aria-hidden="true">{GLYPH[s.state]}</span>
            <span className="jny-name">{s.label}</span>
            <span className="jny-state">{STATE_TEXT[s.state]}</span>
          </li>
        ))}
      </ol>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {canWrite && !p.lost && mode === null && (
        <form className="form-grid" onSubmit={submitMove} aria-label="Move stage" noValidate={false}>
          <div className="field">
            <label htmlFor={id("to")}>Move to</label>
            <select id={id("to")} value={to} onChange={(e) => setTo(e.target.value)} required aria-describedby={errors.to_stage ? id("to_stage-error") : undefined}>
              <option value="">Choose a stage</option>
              {p.steps.filter((s) => s.kind === "manual").map((s) => (
                <option key={s.key} value={s.key} disabled={s.key === p.stage}>
                  {s.label}{s.key === p.stage ? " (current)" : ""}
                </option>
              ))}
            </select>
            {fieldError("to_stage")}
          </div>
          <div className="field">
            <label htmlFor={id("note")}>{backward ? "Reason (required when moving back)" : "Note (optional)"}</label>
            <textarea id={id("note")} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} rows={2} required={backward} aria-describedby={errors.note ? id("note-error") : undefined} />
            {fieldError("note")}
          </div>
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy || to === ""}>
              {busy ? "Saving…" : "Move"}
            </button>
          </div>
        </form>
      )}
      {canWrite && mode === null && (
        <button id={id("flag")} type="button" className="btn secondary small" onClick={openFlag} disabled={busy}>
          {p.lost ? "Revive" : "Mark lost"}
        </button>
      )}
      {canWrite && mode !== null && (
        <form className="form-grid" onSubmit={submitFlag} aria-label={mode === "lost" ? "Mark lost" : "Revive"}>
          <div className="field">
            <label htmlFor={id("reason")}>Reason</label>
            <textarea id={id("reason")} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} rows={2} required aria-describedby={errors.reason ? id("reason-error") : undefined} />
            {fieldError("reason")}
          </div>
          <div className="actions">
            <button type="submit" className="btn small" disabled={busy}>
              {busy ? "Saving…" : mode === "lost" ? "Yes, mark lost" : "Yes, revive"}
            </button>
            <button type="button" className="btn secondary small" onClick={cancelFlag} disabled={busy}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
```

In `apps/web/components/BdmOrganizationDetail.tsx`:
- imports: `import BdmOrganizationPipeline from "@/components/BdmOrganizationPipeline";`,
  `import BdmStageHistory from "@/components/BdmStageHistory";`, `import type { StageEvent } from "@/lib/bdmPipeline";`
- props: add `stageHistory?: Page<StageEvent> | null` to the destructured props and their type.
- state: `const [historyVersion, setHistoryVersion] = useState(0);`
- after the `{confirming && (...)}` block, before `{showEditor ? (`:

```tsx
      <BdmOrganizationPipeline
        organization={org}
        onChanged={(o, text) => {
          changed(o, text);
          setHistoryVersion((v) => v + 1);
          focus(statusId); // the form that was used is reset or gone
        }}
      />
      {stageHistory !== undefined && <BdmStageHistory orgId={org.id} initial={stageHistory} version={historyVersion} />}
```

In both detail pages: `import { firstStageHistory } from "@/lib/bdmPipelineServer";`; next to `const timeline = firstActivityPage(id);`
add `const stages = firstStageHistory(id); // bdm-004: the stage history's first page, read alongside the organization`; next to
`const activities = organization ? await timeline : null;` add `const stageHistory = organization ? await stages : null;`; pass
`stageHistory={stageHistory}` to `BdmOrganizationDetail`.

- [ ] **Step 4: Run** `npx vitest run tests/components/BdmOrganizationPipeline.test.tsx tests/components/BdmStageHistory.test.tsx tests/components/BdmOrganizationPages.test.tsx tests/components/BdmOrganizationDetail.test.tsx`
then `npx tsc --noEmit` and `npx eslint components/BdmOrganizationPipeline.tsx components/BdmStageHistory.tsx components/BdmOrganizationDetail.tsx`.
Expected: pass; 0 errors. If the stepper `textContent` assertion differs only by the glyph map, fix the component, not the test.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/BdmOrganizationPipeline.tsx apps/web/components/BdmStageHistory.tsx apps/web/components/BdmOrganizationDetail.tsx "apps/web/app/bdm/organizations/[id]/page.tsx" "apps/web/app/bdm/manager/organizations/[id]/page.tsx" apps/web/tests/components/BdmOrganizationPipeline.test.tsx apps/web/tests/components/BdmStageHistory.test.tsx apps/web/tests/components/BdmOrganizationPages.test.tsx
git commit -m "feat(bdm-004): pipeline stepper, move / lost / revive and stage history on the organization pages"
```

---

### Task 11: Pipeline pages

**Files:**
- Create: `apps/web/components/BdmPipelineBoard.tsx` (server component, no `"use client"`),
  `apps/web/app/bdm/pipeline/page.tsx`, `apps/web/app/bdm/pipeline/loading.tsx`,
  `apps/web/app/bdm/manager/pipeline/page.tsx`, `apps/web/app/bdm/manager/pipeline/loading.tsx`
- Test: `apps/web/tests/components/BdmPipelinePages.test.tsx`

**Interfaces:**
- Consumes: `readPipeline`, `PipelineView`, `LOST`, `ORG_TYPE_LABEL`, `LINK_STYLE`, `TEAM_URL`, `BDM_TYPE_LABEL`, `BdmTeamRow`,
  `pageOffset`, `PAGE_SIZE`, `accessUnavailable`, `accessDenied`, `PortalShell`, `PortalLoading`, `bdmNav`, `bdmManagerNav`.
- Produces: `<BdmPipelineBoard view href orgBasePath selected emptyText emptyAction? />` where
  `href: (change: { stage?: string | null; offset?: number }) => string`.

- [ ] **Step 1: Write the failing test** — `apps/web/tests/components/BdmPipelinePages.test.tsx`:

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";

import BdmPipelineBoard from "@/components/BdmPipelineBoard";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import ManagerPipeline from "@/app/bdm/manager/pipeline/page";
import BdmPipeline from "@/app/bdm/pipeline/page";
import { elements, text } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const me = {
  id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, division: "it",
  bdm_profile: { bdm_type: "college", employee_id: "E-1", designation: null, department: null, territory: null, reporting_manager: { id: "m1", full_name: "Meera", active: true } },
};
const view = (over = {}) => ({
  bdm_type: "college", lost_count: 1, total: 1, limit: 50, offset: 0,
  stages: [{ key: "prospect", label: "College Prospect", kind: "manual", count: 3 }, { key: "placement", label: "Placement", kind: "volume", count: null }],
  items: [{ id: "o1", code: "ORG-000001", name: "St Mary", city: "Kochi", org_type: "college", assigned_bdm: { id: "b1", full_name: "Asha", active: true }, stage: "prospect", stage_label: "College Prospect", lost: false }],
  ...over,
});
const allText = (tree: ReturnType<typeof elements>) => tree.map((el) => text(el)).join(" ");
const sp = (q: Record<string, string> = {}) => Promise.resolve(q);
const board = (tree: ReturnType<typeof elements>) => tree.find((el) => el.type === BdmPipelineBoard)!;

beforeEach(() => vi.mocked(serverApi).mockReset());

describe("bdm-004 BDM pipeline page", () => {
  it("defaults to my organizations and keeps the filters in the links", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/bdm/me" ? me : view()) as never);
    const tree = elements(await BdmPipeline({ searchParams: sp() }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/pipeline?assigned=me&limit=50&offset=0");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("College BDM");
    const props = board(tree).props;
    expect(props.href({ stage: "lost", offset: 0 })).toBe("/bdm/pipeline?stage=lost");
    expect(props.orgBasePath).toBe("/bdm/organizations");
  });

  it("the All toggle drops the assignee and is kept in the links", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/bdm/me" ? me : view()) as never);
    const tree = elements(await BdmPipeline({ searchParams: sp({ scope: "all", stage: "prospect", offset: "50" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/pipeline?stage=prospect&limit=50&offset=50");
    expect(board(tree).props.href({ offset: 100 })).toBe("/bdm/pipeline?scope=all&stage=prospect&offset=100");
    expect(board(tree).props.selected).toBe("prospect");
  });

  it("an invalid stage in the address shows a reset link", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/bdm/me") return me as never;
      throw new ApiError("Choose a stage of this pipeline", 422);
    });
    const tree = elements(await BdmPipeline({ searchParams: sp({ stage: "<script>" }) }));
    expect(allText(tree)).toContain("That filter isn't valid");
    expect(tree.some((el) => el.props.href === "/bdm/pipeline")).toBe(true);
  });
});

describe("bdm-004 manager pipeline page", () => {
  const team = { items: [{ id: "b2", full_name: "Ravi", bdm_type: "school" }, { id: "b1", full_name: "Asha", bdm_type: "college" }], total: 2, limit: 100, offset: 0 };
  const answer = (user: unknown) => vi.mocked(serverApi).mockImplementation(async (p: string) => {
    if (p === "/api/v1/auth/me") return user as never;
    if (p.startsWith("/api/v1/bdm/manager/team")) return team as never;
    return view() as never;
  });

  it("falls back to the team's first type", async () => {
    answer({ id: "m1", full_name: "Meera", role: "bdm_manager" });
    const tree = elements(await ManagerPipeline({ searchParams: sp({ type: "agent" }) })); // no agent BDMs: first type in Agent, School, College order
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/pipeline?bdm_type=school&limit=50&offset=0");
    expect(board(tree).props.orgBasePath).toBe("/bdm/manager/organizations");
  });

  it("filters to one BDM of the chosen type and drops a BDM of another type", async () => {
    answer({ id: "m1", full_name: "Meera", role: "bdm_manager" });
    await ManagerPipeline({ searchParams: sp({ type: "school", bdm: "b2" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/pipeline?bdm_type=school&assigned=b2&limit=50&offset=0");
    vi.mocked(serverApi).mockClear();
    await ManagerPipeline({ searchParams: sp({ type: "school", bdm: "b1" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/pipeline?bdm_type=school&limit=50&offset=0");
  });

  it("refuses a BDM and says when no BDMs report to the manager", async () => {
    answer({ id: "b1", full_name: "Asha", role: "bdm" });
    let tree = elements(await ManagerPipeline({ searchParams: sp() }));
    expect(tree.find((el) => typeof el.props.message === "string")!.props.message).toBe("This page is for BDM managers.");
    vi.mocked(serverApi).mockImplementation(async (p: string) =>
      (p === "/api/v1/auth/me" ? { id: "m1", full_name: "Meera", role: "bdm_manager" } : { items: [], total: 0, limit: 100, offset: 0 }) as never);
    tree = elements(await ManagerPipeline({ searchParams: sp() }));
    expect(allText(tree)).toContain("No BDMs report to you yet");
    expect(tree.some((el) => el.type === BdmPipelineBoard)).toBe(false);
  });
});

describe("bdm-004 pipeline board", () => {
  it("shows counts as links, volume steps as Not tracked, a Lost tile, and the list", () => {
    const tree = elements(BdmPipelineBoard({ view: view() as never, href: ({ stage }) => `/x?stage=${stage}`, orgBasePath: "/bdm/organizations", selected: "prospect", emptyText: "None" }));
    const tiles = tree.filter((el) => el.props.className === "metric" && typeof el.props.href === "string");
    expect(tiles.map((el) => text(el))).toEqual(["College Prospect3", "Lost1"]);
    expect(tiles.find((el) => el.props.href === "/x?stage=prospect")!.props["aria-current"]).toBe("true");
    expect(allText(tree)).toContain("Not tracked");
    expect(tree.some((el) => el.props.href === "/bdm/organizations/o1")).toBe(true);
  });

  it("says when a stage is empty", () => {
    const tree = elements(BdmPipelineBoard({ view: view({ items: [], total: 0 }) as never, href: () => "/x", orgBasePath: "/o", selected: null, emptyText: "No organizations at this stage." }));
    expect(allText(tree)).toContain("No organizations at this stage.");
  });
});
```

- [ ] **Step 2: Run** `npx vitest run tests/components/BdmPipelinePages.test.tsx`. Expected: FAIL — modules not found.

- [ ] **Step 3: Implement** `apps/web/components/BdmPipelineBoard.tsx`:

```tsx
import Link from "next/link";
import type { ReactNode } from "react";

import { PAGE_SIZE } from "@/lib/bdm";
import { LINK_STYLE, ORG_TYPE_LABEL } from "@/lib/bdmOrganizations";
import { LOST, type PipelineView } from "@/lib/bdmPipeline";

type Change = { stage?: string | null; offset?: number };
const SELECTED = { display: "block", borderColor: "var(--blue)", boxShadow: "0 0 0 1px var(--blue)" } as const;

// bdm-004 (spec §8.3): stage tiles (counts are links; live / volume steps say why they have no count) and the organizations at the
// chosen stage. Server-rendered: every filter is in the address, so the browser's back button and shared links just work.
export default function BdmPipelineBoard({ view, href, orgBasePath, selected, emptyText, emptyAction }: {
  view: PipelineView; href: (change: Change) => string; orgBasePath: string; selected: string | null; emptyText: string; emptyAction?: ReactNode;
}) {
  const tiles = [...view.stages, { key: LOST, label: "Lost", kind: "manual" as const, count: view.lost_count }];
  const heading = tiles.find((t) => t.key === selected)?.label ?? "All open organizations";
  const last = view.offset + view.items.length;
  return (
    <>
      <nav aria-label="Pipeline stages">
        <ul className="metric-grid" style={{ listStyle: "none", padding: 0 }}>
          {tiles.map((t) => (
            <li key={t.key}>
              {t.count === null ? (
                <div className="metric">
                  <span>{t.label}</span>
                  <strong style={{ fontSize: 15 }}>{t.kind === "live" ? "Awaiting handover" : "Not tracked"}</strong>
                </div>
              ) : (
                <Link className="metric" href={href({ stage: t.key, offset: 0 })} aria-current={selected === t.key ? "true" : undefined} style={selected === t.key ? SELECTED : { display: "block" }}>
                  <span>{t.label}</span>
                  <strong>{t.count}</strong>
                </Link>
              )}
            </li>
          ))}
        </ul>
      </nav>
      <section className="action-card wide" aria-label="Organizations at this stage">
        <h3>{heading}</h3>
        {selected && (
          <p>
            <Link href={href({ stage: null, offset: 0 })} style={LINK_STYLE}>Show all stages</Link>
          </p>
        )}
        {view.items.length === 0 ? (
          <>
            <p className="empty" role="status">{view.offset > 0 ? "This page is past the end of the list." : emptyText}</p>
            {emptyAction}
          </>
        ) : (
          <div className="table-wrap" role="region" aria-label="Organizations" tabIndex={0}>
            <table style={{ overflowWrap: "anywhere" }}>
              <thead>
                <tr>
                  <th scope="col">Code</th>
                  <th scope="col">Name</th>
                  <th scope="col">Type</th>
                  <th scope="col">City</th>
                  <th scope="col">Stage</th>
                  <th scope="col">Assigned BDM</th>
                </tr>
              </thead>
              <tbody>
                {view.items.map((r) => (
                  <tr key={r.id}>
                    <td style={{ whiteSpace: "nowrap" }}>{r.code}</td>
                    <td style={{ minWidth: 160 }}>
                      <Link href={`${orgBasePath}/${r.id}`} style={LINK_STYLE}>{r.name}</Link>
                    </td>
                    <td>{ORG_TYPE_LABEL[r.org_type]}</td>
                    <td>{r.city}</td>
                    <td>
                      {r.stage_label}
                      {r.lost && <> <span className="badge">Lost</span></>}
                    </td>
                    <td>{r.assigned_bdm.full_name}{!r.assigned_bdm.active && <span className="muted"> (inactive)</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {view.total > PAGE_SIZE && (
          <nav aria-label="Pipeline pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
            <span className="muted" style={{ fontSize: 13 }}>Showing {view.offset + 1}–{last} of {view.total}</span>
            {view.offset > 0 && <Link className="btn secondary small" href={href({ offset: Math.max(0, view.offset - PAGE_SIZE) })}>Previous</Link>}
            {last < view.total && <Link className="btn secondary small" href={href({ offset: view.offset + PAGE_SIZE })}>Next</Link>}
          </nav>
        )}
      </section>
    </>
  );
}
```

`apps/web/app/bdm/pipeline/page.tsx`:

```tsx
import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmPipelineBoard from "@/components/BdmPipelineBoard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe, pageOffset } from "@/lib/bdm";
import { bdmNav } from "@/lib/bdmNav";
import { readPipeline } from "@/lib/bdmPipelineServer";
import { BDM_SIGN_IN } from "@/lib/navigation";

const PATH = "/bdm/pipeline";
const TOGGLE = { display: "flex", gap: 8, flexWrap: "wrap", margin: "0 0 16px" } as const;

// bdm-004 (S7, spec §8.3): my pipeline by default; "All in module" is the D11 read scope. Filters live in the address.
export default async function BdmPipelinePage({ searchParams }: { searchParams: Promise<{ scope?: string; stage?: string; offset?: string }> }) {
  const nav = bdmNav();
  const sp = await searchParams;
  const all = sp.scope === "all";
  const stage = sp.stage || undefined;
  const offset = pageOffset(sp.offset);
  const href = (change: { stage?: string | null; offset?: number }, scopeAll = all) => {
    const q = new URLSearchParams();
    if (scopeAll) q.set("scope", "all");
    const s = change.stage === undefined ? stage : change.stage;
    if (s) q.set("stage", s);
    const o = change.offset ?? 0;
    if (o > 0) q.set("offset", String(o));
    const query = q.toString();
    return query ? `${PATH}?${query}` : PATH;
  };
  let me: BdmMe;
  let view: Awaited<ReturnType<typeof readPipeline>>;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
    view = await readPipeline({ assigned: all ? undefined : "me", stage, offset });
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  const type = BDM_TYPE_LABEL[me.bdm_profile.bdm_type];
  return (
    <PortalShell nav={await nav} roleLabel={`${type} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Pipeline</div>
            <h2>{type} pipeline</h2>
            <p className="muted">Organizations per stage. Lost organizations are counted apart; archived ones are left out.</p>
          </div>
        </div>
        <nav aria-label="Whose organizations" style={TOGGLE}>
          <Link className={all ? "btn secondary small" : "btn small"} href={href({ stage: null }, false)} aria-current={all ? undefined : "true"}>Mine</Link>
          <Link className={all ? "btn small" : "btn secondary small"} href={href({ stage: null }, true)} aria-current={all ? "true" : undefined}>All in module</Link>
        </nav>
        {view === "invalid" ? (
          <div className="action-card">
            <p>That filter isn&apos;t valid.</p>
            <p><Link href={PATH}>Show my pipeline</Link></p>
          </div>
        ) : (
          <BdmPipelineBoard
            view={view}
            href={href}
            orgBasePath="/bdm/organizations"
            selected={stage ?? null}
            emptyText="No organizations at this stage."
            emptyAction={<Link className="btn small" href="/bdm/organizations/new">Add organization</Link>}
          />
        )}
      </div>
    </PortalShell>
  );
}
```

`apps/web/app/bdm/manager/pipeline/page.tsx`:

```tsx
import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmPipelineBoard from "@/components/BdmPipelineBoard";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { BDM_TYPE_LABEL, type BdmTeamRow, type BdmType, pageOffset } from "@/lib/bdm";
import { bdmManagerNav } from "@/lib/bdmNav";
import { TEAM_URL } from "@/lib/bdmOrganizations";
import { readPipeline } from "@/lib/bdmPipelineServer";
import type { User } from "@/lib/types";

const PATH = "/bdm/manager/pipeline";
const TYPES: BdmType[] = ["agent", "school", "college"];

// bdm-004 (S1, S7, spec §8.3): the team's pipeline per type (super_admin: every BDM), optionally one BDM. Read-only.
export default async function ManagerPipelinePage({ searchParams }: { searchParams: Promise<{ type?: string; bdm?: string; stage?: string; offset?: string }> }) {
  const nav = bdmManagerNav();
  const sp = await searchParams;
  let user: User;
  let team: Page<BdmTeamRow>;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
    team = await serverApi<Page<BdmTeamRow>>(`${TEAM_URL}?limit=100&offset=0`);
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  const types = TYPES.filter((t) => team.items.some((b) => b.bdm_type === t));
  const roleLabel = user.role === "super_admin" ? "Super Admin" : "BDM Manager";
  const header = (
    <div className="portal-title">
      <div>
        <div className="eyebrow">Pipeline</div>
        <h2>Team pipeline</h2>
        <p className="muted">Your BDMs&apos; organizations per stage. Lost organizations are counted apart; archived ones are left out.</p>
      </div>
    </div>
  );
  if (types.length === 0) {
    return (
      <PortalShell nav={await nav} roleLabel={roleLabel} userName={user.full_name}>
        <div className="portal-content">
          {header}
          <p className="empty" role="status">No BDMs report to you yet.</p>
        </div>
      </PortalShell>
    );
  }
  const type = types.includes(sp.type as BdmType) ? (sp.type as BdmType) : types[0]; // Review Focus 4
  const ofType = team.items.filter((b) => b.bdm_type === type);
  const picked = ofType.find((b) => b.id === sp.bdm);
  const stage = sp.stage || undefined;
  const offset = pageOffset(sp.offset);
  const href = (change: { stage?: string | null; offset?: number }) => {
    const q = new URLSearchParams({ type });
    if (picked) q.set("bdm", picked.id);
    const s = change.stage === undefined ? stage : change.stage;
    if (s) q.set("stage", s);
    const o = change.offset ?? 0;
    if (o > 0) q.set("offset", String(o));
    return `${PATH}?${q}`;
  };
  let view: Awaited<ReturnType<typeof readPipeline>>;
  try {
    view = await readPipeline({ bdm_type: type, assigned: picked?.id, stage, offset });
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={await nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        {header}
        <form className="analytics-form" method="get" action={PATH} aria-label="Filter pipeline">
          <div className="field">
            <label htmlFor="pipeline-type">Type</label>
            <select id="pipeline-type" name="type" defaultValue={type}>
              {types.map((t) => <option key={t} value={t}>{BDM_TYPE_LABEL[t]}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="pipeline-bdm">BDM</label>
            <select id="pipeline-bdm" name="bdm" defaultValue={picked?.id ?? ""}>
              <option value="">Everyone</option>
              {team.items.map((b) => <option key={b.id} value={b.id}>{b.full_name} ({BDM_TYPE_LABEL[b.bdm_type]})</option>)}
            </select>
          </div>
          <button className="btn secondary" type="submit">Show</button>
        </form>
        {view === "invalid" ? (
          <div className="action-card">
            <p>That filter isn&apos;t valid.</p>
            <p><Link href={PATH}>Show the team pipeline</Link></p>
          </div>
        ) : (
          <BdmPipelineBoard view={view} href={href} orgBasePath="/bdm/manager/organizations" selected={stage ?? null} emptyText="No organizations at this stage." />
        )}
      </div>
    </PortalShell>
  );
}
```

`apps/web/app/bdm/pipeline/loading.tsx`:

```tsx
import PortalLoading from "@/components/PortalLoading";
import { BDM_NAV } from "@/lib/navigation";

export default function Loading() {
  return <PortalLoading nav={BDM_NAV} label="your pipeline" />;
}
```

`apps/web/app/bdm/manager/pipeline/loading.tsx`:

```tsx
import PortalLoading from "@/components/PortalLoading";
import { BDM_MANAGER_NAV } from "@/lib/navigation";

export default function Loading() {
  return <PortalLoading nav={BDM_MANAGER_NAV} label="the team pipeline" />;
}
```

- [ ] **Step 4: Run** `npx vitest run tests/components/BdmPipelinePages.test.tsx`, then `npx tsc --noEmit`, then
`npx eslint components/BdmPipelineBoard.tsx app/bdm/pipeline app/bdm/manager/pipeline`. Expected: pass; 0 errors.

- [ ] **Step 5: Web lite + build.** Run LITE (web) with vitest, then `npx tsc --noEmit`, `npx eslint .` (0 errors; existing warnings
  only), `npm run build`. Expected: green. REFACTOR now if anything reads awkwardly, then rerun.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/BdmPipelineBoard.tsx apps/web/app/bdm/pipeline apps/web/app/bdm/manager/pipeline apps/web/tests/components/BdmPipelinePages.test.tsx
git commit -m "feat(bdm-004): /bdm/pipeline and /bdm/manager/pipeline with stage tiles and the list per stage"
```

---

### Task 12: End-to-end spec

**Files:**
- Create: `apps/web/tests/e2e/bdm-004-pipeline.spec.ts`

- [ ] **Step 1: Write the spec**:

```ts
import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-004 (AC2, AC3, AC5, AC6, AC8, AC11): a College BDM moves an organization forward, back with a note, marks it lost and revives
// it; the history and the pipeline counts follow; the manager reads but cannot move; nothing overflows at 320 / 375 px.
test.describe.configure({ timeout: 120_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function noOverflow(page: Page) {
  for (const width of [320, 375]) {
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
}

test("BDM pipeline: move, move back with a note, lost, revive, counts, manager read-only", async ({ page }) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm004-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm004-b-${stamp}@example.local`,
            bdm_profile: { bdm_type: "college", employee_id: `E2E4-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, E2E_PASSWORD, "/bdm/my-day");
  const created = await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `E2E College ${stamp}`, city: "Kochi", contacts: [{ name: "Dr Rao", role: "principal" }] },
  });
  const org = (await created.json()).organization;

  await page.goto(`/bdm/organizations/${org.id}`);
  await page.waitForLoadState("networkidle");
  const stages = page.getByRole("list", { name: "Pipeline stages" });
  await expect(stages.getByRole("listitem").filter({ hasText: "College Prospect" })).toHaveAttribute("aria-current", "step");
  await expect(stages.getByRole("listitem").filter({ hasText: "Placement" })).toContainText("Not tracked");

  // AC2 forward (skipping), keyboard only
  await page.getByLabel("Move to").focus();
  await page.getByLabel("Move to").selectOption("proposal");
  await page.getByRole("button", { name: "Move" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "Moved to Proposal." })).toBeVisible();
  const history = page.getByRole("list", { name: "Stage history" });
  await expect(history.getByText("College Prospect → Proposal")).toBeVisible();

  // AC3 back needs a note
  await page.getByLabel("Move to").selectOption("contacted");
  await expect(page.getByLabel("Reason (required when moving back)")).toHaveAttribute("required", "");
  await page.getByLabel("Reason (required when moving back)").fill("Proposal was premature");
  await page.getByRole("button", { name: "Move" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Moved to Contacted." })).toBeVisible();
  await expect(history.getByText("Note: Proposal was premature")).toBeVisible();

  // AC8 lost, then revive
  await page.getByRole("button", { name: "Mark lost" }).click();
  await page.getByLabel("Reason", { exact: true }).fill("No budget this year");
  await page.getByRole("button", { name: "Yes, mark lost" }).click();
  await expect(page.getByText(/Marked lost on .*No budget this year/)).toBeVisible();
  await expect(page.getByLabel("Move to")).toHaveCount(0);
  await page.getByRole("button", { name: "Revive" }).click();
  await page.getByLabel("Reason", { exact: true }).fill("New principal");
  await page.getByRole("button", { name: "Yes, revive" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Revived." })).toBeVisible();
  await noOverflow(page);

  // AC5 my pipeline
  await page.getByRole("link", { name: "Pipeline" }).first().click();
  await page.waitForURL("**/bdm/pipeline");
  const tiles = page.getByRole("navigation", { name: "Pipeline stages" });
  await expect(tiles.getByRole("link", { name: /Contacted\s*1/ })).toBeVisible();
  await tiles.getByRole("link", { name: /Contacted\s*1/ }).click();
  await expect(page.getByRole("region", { name: "Organizations" }).getByText(`E2E College ${stamp}`)).toBeVisible();
  await noOverflow(page);

  // AC6 the manager reads the team pipeline and the organization, without move controls
  await signIn(page, "admin", manager.email, E2E_PASSWORD, "/bdm/manager/dashboard");
  await page.goto("/bdm/manager/pipeline");
  await expect(page.getByRole("navigation", { name: "Pipeline stages" }).getByRole("link", { name: /Contacted\s*1/ })).toBeVisible();
  await page.goto(`/bdm/manager/organizations/${org.id}`);
  await expect(page.getByRole("list", { name: "Pipeline stages" })).toBeVisible();
  await expect(page.getByLabel("Move to")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Mark lost" })).toHaveCount(0);
  await expect(page.getByRole("list", { name: "Stage history" }).getByText("Revived at Contacted")).toBeVisible();
  await noOverflow(page);
});
```

- [ ] **Step 2: Run it** against a stack built from this branch (`docker compose -p bdm004 up -d --build`, then seed) with
`npx playwright test tests/e2e/bdm-004-pipeline.spec.ts --workers=1` (via the `web-test` service or local Playwright, as the
bdm-009 run did). Then the impacted specs: `bdm-002-organization-crm`, `bdm-003-type-profiles`, `bdm-009-activities`.
Expected: green. A first-run timeout on a cold stack: rerun that spec alone before diagnosing.

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/bdm-004-pipeline.spec.ts
git commit -m "test(bdm-004): e2e pipeline flow, counts and manager read-only"
```

---

### Task 13: Documentation and lite verification

**Files:**
- Modify: `docs/delivery/BDM_CRM_BACKLOG.md` (bdm-004 status line under its heading), `docs/quality/RTM.md` (bdm-004 row),
  `docs/architecture/API_CONTRACT.md` (five routes), `docs/architecture/DATA_MODEL.md` (columns + table, migration 0072),
  `docs/decisions/PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-070` **Status** line)

- [ ] **Step 1:** Add each entry following the bdm-009 entries in the same files (search each file for `0071_bdm_activities` and
  mirror the format). Status wording: "implemented on `feature/bdm-004-pipeline-stages`; lite verification green; **not yet
  complete** — browser validation and the independent Codex review are pending."
- [ ] **Step 2: Final lite run** — LITE (backend), LITE (web), `tsc`, `eslint .`, `npm run build`, `alembic heads` (one head),
  Playwright bdm-004 + bdm-002/003/009. Record the counts in the commit message body.
- [ ] **Step 3: Commit**

```bash
git add docs/delivery/BDM_CRM_BACKLOG.md docs/quality/RTM.md docs/architecture/API_CONTRACT.md docs/architecture/DATA_MODEL.md docs/decisions/PRODUCT_DECISION_REGISTER.md
git commit -m "docs(bdm-004): backlog status, RTM, API contract, data model; lite verification evidence"
```

Do **not** claim completion: browser validation (AC11 at 320 / 375 / 768 / 1366 px, keyboard, RBAC) and the independent Codex
review follow.
