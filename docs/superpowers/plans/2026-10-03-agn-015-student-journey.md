# AGN-015 — Agent Student Journey + Complete History Implementation Plan

> **Renumbered after this plan was executed:** on merging `main` @ `c5cdc8a` (bdm-002, PR #50, which holds `DEC-SCOPE-060` and
> `0066_bdm_organizations`) the decision became `DEC-SCOPE-061` and the migration `0067_audit_entity_index` (after `0066_bdm_organizations`).
> The `060` / `0066` numbers below are the plan as written.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An agency Master or assigned Staff member opening one student sees a step tracker (steps 1–4 for the student, steps 5–9 per
application) that matches stored data, and a paginated newest-first history where every source event appears once with its actor.

**Architecture:** One read-only service `app/services/agent_journey.py` gathers the student's scoped applications, documents,
requests, deposits and visa cases once, then (a) derives tracker states in pure functions and (b) builds one SQLAlchemy Core
`union_all` over eight sources, ordered and paged in PostgreSQL with `count(*) OVER ()`. Two GET routes are added to the existing
`api/agent_students.py` router. One additive index migration. The web adds `lib/agentJourney.ts` and two components mounted in
`AgentStudentDetailPanel`.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL 16; Next.js App Router + TypeScript; pytest; vitest; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-03-agn-015-student-journey-design.md` (`DEC-SCOPE-060`).

## Global Constraints

- Read-only: no lock, no write, no commit, no cache, no new audit action, no rate limit.
- Scope: student `load_scoped`; applications `application_scope` ∧ owner ∧ `school_student_id IS NULL`; documents `document_scope` ∧
  `student_clause`; requests `request_scope` ∧ `agent_student_id`; audit rows only by ids from those sets. Out of scope → 404 "Student not found".
- Item keys always present: `id, at, kind, actor, application, document, from_status, to_status, fields, notes`.
- Never returned: field values, amounts, visa decision, emails, phones, file keys, raw audit metadata.
- Actor labels: `EduSphere counsellor`, `EduSphere admin`, `Student`, `Parent`, `University`, `Agency user`, `EduSphere user`, `System`.
- Order: `at DESC, rank DESC, seq DESC, row_id DESC`. `limit` 1–100 (default 20), `offset` 0–10 000.
- Migration `0066_audit_entity_index` after `0065_agent_notifications`: index `ix_audit_logs_entity (entity_type, entity_id, created_at)`, guarded add (0001 builds from models).
- Logs: `agent_student_journey_viewed`, `agent_student_timeline_viewed` with ids and offset only.
- No new dependencies. Existing responses unchanged.
- Lite tests only (owner runs full suites separately): `tests/test_agn_015_*.py` + `tests/test_agn_017_migration.py`; web: touched vitest files + `tsc --noEmit` + lint on touched files.

## Test command

```
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn015 --profile ci run --rm \
  -v "$PWD/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <files>"
```

Web: `cd apps/web && npx vitest run <files> && npx tsc --noEmit`.

## Review Focus

1. A linked (login) student who is also linked by **another agency** with its own application — expect that application, its
   history, deposit, visa and documents absent from both endpoints (Task 4 test).
2. A Staff member asking for an **unassigned** student's `/timeline` — expect 404, identical body to an unknown id (Task 4).
3. A counsellor's `overseas.application.update` audit row whose metadata holds values (`{"next_action": "..."}`) — expect only the
   key names in `fields`, never the value (Task 3).
4. A document uploaded **before AGN-009** (no `uploaded` event) — expect exactly one `document_uploaded` event; a document uploaded
   through AGN-009 — exactly one too (Task 3).
5. Offset past the end (`offset=5000` with 3 events) — expect `items: []` and the true `total` (Task 3).

---

### Task 1: Audit entity index migration

**Files:**
- Create: `apps/api/alembic/versions/0066_audit_entity_index.py`
- Modify: `apps/api/app/models.py` (`AuditLog`: add `__table_args__`)
- Modify: `apps/api/tests/test_agn_017_migration.py:46` (single-head assertion no longer pins 0065)
- Test: `apps/api/tests/test_agn_015_migration.py`

**Interfaces:** Produces index `ix_audit_logs_entity`.

- [ ] **Step 1: Write the failing test** `tests/test_agn_015_migration.py`

```python
"""AGN-015 -- migration 0066_audit_entity_index (spec §6): one additive index, no row read or written."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

API_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("_agn_015_migration_0066", API_ROOT / "alembic" / "versions" / "0066_audit_entity_index.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_chains_after_0065_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == ("0066_audit_entity_index", "0065_agent_notifications")
    assert ScriptDirectory.from_config(_config()).get_heads() == ["0066_audit_entity_index"]


def test_model_declares_the_index():
    from app.models import AuditLog

    index = {i.name: i for i in AuditLog.__table__.indexes}["ix_audit_logs_entity"]
    assert [c.name for c in index.columns] == ["entity_type", "entity_id", "created_at"]


@pytest.mark.asyncio
async def test_index_exists_in_the_shared_database(db_session):
    indexdef = await db_session.scalar(sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_audit_logs_entity'"))
    assert indexdef is not None and "(entity_type, entity_id, created_at)" in indexdef
```

- [ ] **Step 2: Run, expect FAIL** (file `0066_audit_entity_index.py` not found).
- [ ] **Step 3: Implement** the migration (guarded, 0065 idiom), the model index, and relax `test_agn_017_migration.py:46` to
  `assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1` (the AGN-013 form; its chain assertion is unchanged).

```python
"""AGN-015 -- audit_logs (entity_type, entity_id, created_at) for per-entity history reads.

Revision ID: 0066_audit_entity_index
Revises: 0065_agent_notifications

docs/superpowers/specs/2026-10-03-agn-015-student-journey-design.md §6 (DEC-SCOPE-060). One index; no row is read or written. 0001
builds a fresh database from the current models, which already carry it, so the add is guarded (0057's idiom).
"""

import sqlalchemy as sa

from alembic import op

revision = "0066_audit_entity_index"
down_revision = "0065_agent_notifications"
branch_labels = None
depends_on = None

NAME = "ix_audit_logs_entity"


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    if inspector is None or NAME not in {i["name"] for i in inspector.get_indexes("audit_logs")}:
        op.create_index(NAME, "audit_logs", ["entity_type", "entity_id", "created_at"])


def downgrade() -> None:
    op.drop_index(NAME, table_name="audit_logs")
```

Model (`AuditLog`): `__table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id", "created_at"),)` with a one-line
AGN-015 comment.

- [ ] **Step 4: Run** `tests/test_agn_015_migration.py tests/test_agn_017_migration.py` → PASS.
- [ ] **Step 5: Commit** `feat(agn-015): audit_logs entity index (0066)`.

---

### Task 2: Journey tracker — service + route

**Files:**
- Create: `apps/api/app/services/agent_journey.py`
- Modify: `apps/api/app/api/agent_students.py` (one route)
- Create: `apps/api/tests/agn015_helpers.py`, `apps/api/tests/test_agn_015_journey.py`

**Interfaces:**
- Produces: `async def journey(db, user, record) -> dict`; `def student_steps(counseling, shortlisted: int, documents: list, open_requests: bool) -> list[dict]`;
  `def application_steps(app, deposit, visa) -> list[dict]`; `async def _sources(db, user, record) -> Sources` (used by Task 3).
- Route: `GET /api/v1/workflows/overseas/agent/crm/students/{student_id}/journey`.

- [ ] **Step 1: Helpers** `tests/agn015_helpers.py`

```python
"""AGN-015 test helpers: the AGN-009 world plus builders for history/audit rows and the two URLs."""

from app.models import ApplicationDeposit, ApplicationStatusHistory, AuditLog
from tests.agn004_helpers import RECORDS


def journey_url(student_id) -> str:
    return f"{RECORDS}/{student_id}/journey"


def timeline_url(student_id, **params) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{RECORDS}/{student_id}/timeline" + (f"?{query}" if query else "")


async def mk_history(db, app, *, to_status, from_status=None, by=None, notes=None) -> ApplicationStatusHistory:
    row = ApplicationStatusHistory(application_id=app.id, from_status=from_status, to_status=to_status, changed_by_id=by.id if by else None, notes=notes)
    db.add(row)
    await db.commit()
    return row


async def mk_audit(db, *, user, action, entity_type, entity_id, metadata=None) -> AuditLog:
    row = AuditLog(user_id=user.id if user else None, action=action, entity_type=entity_type, entity_id=str(entity_id), metadata_json=metadata or {})
    db.add(row)
    await db.commit()
    return row


async def mk_deposit(db, app, *, by, status="pending", **fields) -> ApplicationDeposit:
    required = status != "not_required"
    row = ApplicationDeposit(application_id=app.id, required=required, amount=fields.pop("amount", 5000 if required else None), status=status, created_by_user_id=by.id, updated_by_user_id=by.id, **fields)
    db.add(row)
    await db.commit()
    return row
```

(`paid`/`remitted`/`refunded` deposits need a `Payment`; the pure `application_steps` tests cover those states without the DB.)

- [ ] **Step 2: Write failing tests** `tests/test_agn_015_journey.py` — pure state tests (SimpleNamespace stand-ins) for every row
  of spec §4, plus API tests:

```python
import pytest
from types import SimpleNamespace as NS

from app.services.agent_journey import application_steps, student_steps
from tests.agn001_helpers import client_for
from tests.agn008_helpers import mk_application
from tests.agn009_helpers import mk_doc, world
from tests.agn012_helpers import mk_case
from tests.agn015_helpers import journey_url, mk_deposit


def states(steps):
    return {s["key"]: s["state"] for s in steps}


def app_(status="enquiry", submitted_on=None, offer_type=None):
    return NS(status=status, submitted_on=submitted_on, offer_type=offer_type)


def test_student_steps_not_started():
    assert states(student_steps(None, 0, [], False)) == {"create": "done", "counseling": "not_started", "shortlist": "not_started", "documents": "not_started"}


def test_student_steps_in_progress_and_done():
    assert states(student_steps(NS(counseling_completed=False), 0, [NS(verification_status="pending")], False))["counseling"] == "in_progress"
    s = states(student_steps(NS(counseling_completed=True), 2, [NS(verification_status="verified")], False))
    assert (s["counseling"], s["shortlist"], s["documents"]) == ("done", "done", "done")


def test_documents_open_request_or_unverified_is_in_progress():
    assert states(student_steps(None, 0, [], True))["documents"] == "in_progress"
    assert states(student_steps(None, 0, [NS(verification_status="verified")], True))["documents"] == "in_progress"
    assert states(student_steps(None, 0, [NS(verification_status="verified"), NS(verification_status="rejected")], False))["documents"] == "in_progress"


def test_application_steps_fresh():
    assert states(application_steps(app_(), None, None)) == {"application": "in_progress", "offer": "not_started", "deposit": "not_started", "visa": "not_started", "enrollment": "not_started"}


def test_application_steps_progress():
    import datetime as dt

    s = states(application_steps(app_("visa_documentation", dt.date(2026, 5, 1)), NS(status="pending"), NS(decision=None)))
    assert s == {"application": "done", "offer": "done", "deposit": "in_progress", "visa": "in_progress", "enrollment": "not_started"}
    s = states(application_steps(app_("enrolled", dt.date(2026, 5, 1), "unconditional"), NS(status="remitted"), NS(decision="approved")))
    assert s == {"application": "done", "offer": "done", "deposit": "done", "visa": "done", "enrollment": "done"}


def test_offer_type_counts_before_the_stage_moves():
    assert states(application_steps(app_("university_selection", offer_type="conditional"), None, None))["offer"] == "done"


@pytest.mark.parametrize("deposit,state", [("paid", "done"), ("not_required", "not_required"), ("refunded", "refunded")])
def test_deposit_states(deposit, state):
    assert states(application_steps(app_(), NS(status=deposit), None))["deposit"] == state


@pytest.mark.parametrize("decision,state", [("refused", "refused"), ("withdrawn", "withdrawn")])
def test_visa_outcomes(decision, state):
    assert states(application_steps(app_(), None, NS(decision=decision)))["visa"] == state


def test_withdrawn_application_marks_unsettled_steps_withdrawn():
    import datetime as dt

    s = states(application_steps(app_("withdrawn", dt.date(2026, 5, 1), "conditional"), NS(status="not_required"), None))
    assert s == {"application": "done", "offer": "done", "deposit": "not_required", "visa": "withdrawn", "enrollment": "withdrawn"}


@pytest.mark.asyncio
async def test_journey_endpoint_matches_stored_data(db_session):
    w = await world(db_session)
    first = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"], status="offer", offer_type="conditional")
    second = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    await mk_deposit(db_session, first, by=w["master"])
    await mk_case(db_session, first)
    await mk_doc(db_session, record=w["record"], status="verified")
    async with client_for(w["staff"]["user"].email) as c:
        r = await c.get(journey_url(w["record"].id))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["student"] == {"id": str(w["record"].id), "full_name": w["record"].full_name, "status": "active"}
    assert states(body["steps"]) == {"create": "done", "counseling": "not_started", "shortlist": "not_started", "documents": "done"}
    assert [a["id"] for a in body["applications"]] == [str(first.id), str(second.id)]
    assert set(body["applications"][0]) == {"id", "university", "intake", "status", "steps"}
    assert states(body["applications"][0]["steps"]) == {"application": "in_progress", "offer": "done", "deposit": "in_progress", "visa": "in_progress", "enrollment": "not_started"}
    assert states(body["applications"][1]["steps"])["offer"] == "not_started"


@pytest.mark.asyncio
async def test_student_with_no_applications(db_session):
    w = await world(db_session)
    async with client_for(w["master"].email) as c:
        r = await c.get(journey_url(w["unassigned"].id))
    assert r.status_code == 200 and r.json()["applications"] == []
```

- [ ] **Step 3: Run, expect FAIL** (`ModuleNotFoundError: app.services.agent_journey`).
- [ ] **Step 4: Implement** `services/agent_journey.py` (journey part) and the route:

```python
"""AGN-015 / DEC-SCOPE-060 -- one agency student's journey (step tracker) and complete history (timeline).

Spec: docs/superpowers/specs/2026-10-03-agn-015-student-journey-design.md. Read-only: no lock, no write, no cache. Every source is
narrowed by the existing scopes (AGN-004 G4, AGN-008, AGN-009) before a row is read, and audit rows are selected only by entity ids
taken from those scoped sets (§6). Only names, labels, statuses, field NAMES and the notes the same viewer already reads leave this
module -- never field values, amounts, the visa decision, emails, phones or file keys (§3).
"""

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentStudent, AgentStudentCounseling, AgentStudentShortlistEntry, ApplicationDeposit, DocumentRequest, OverseasApplication,
    StudentDocument, University, User, VisaCase,
)
from app.services.agent_applications import OVERSEAS_APPLICATION_STAGES, WITHDRAWN
from app.services.agent_documents import document_scope, request_scope, student_clause
from app.services.agent_students import application_scope

_OFFER = OVERSEAS_APPLICATION_STAGES.index("offer")
_DEPOSIT_STATES = {"pending": "in_progress", "paid": "done", "remitted": "done", "not_required": "not_required", "refunded": "refunded"}
_SETTLED = {"done", "not_required", "refunded", "refused"}  # §4: a withdrawn application keeps these; every other step reads withdrawn


@dataclass
class Sources:
    """The student's in-scope rows, read once per request (§6)."""

    apps: list[tuple[OverseasApplication, str | None]]  # (application, university name), oldest first
    documents: dict
    requests: dict
    deposits: dict  # by deposit id
    visas: dict  # by visa case id


async def _sources(db: AsyncSession, user: User, record: AgentStudent) -> Sources:
    owner = OverseasApplication.agent_student_id == record.id
    if record.student_id is not None:  # the AGN-008 owner filter: the record, or (pre-AGN-008 rows) the linked login
        owner = or_(owner, OverseasApplication.student_id == record.student_id)
    apps = (
        await db.execute(
            select(OverseasApplication, University.name)
            .outerjoin(University, University.id == OverseasApplication.university_id)
            .where(OverseasApplication.school_student_id.is_(None), *application_scope(user), owner)
            .order_by(OverseasApplication.created_at, OverseasApplication.id)
        )
    ).all()
    app_ids = [a.id for a, _ in apps]
    documents = {d.id: d for d in (await db.scalars(select(StudentDocument).where(*document_scope(user), student_clause(record)))).all()}
    requests = {r.id: r for r in (await db.scalars(select(DocumentRequest).where(*request_scope(user), DocumentRequest.agent_student_id == record.id))).all()}
    deposits = {d.id: d for d in (await db.scalars(select(ApplicationDeposit).where(ApplicationDeposit.application_id.in_(app_ids)))).all()} if app_ids else {}
    visas = {v.id: v for v in (await db.scalars(select(VisaCase).where(VisaCase.application_id.in_(app_ids)))).all()} if app_ids else {}
    return Sources([(a, name) for a, name in apps], documents, requests, deposits, visas)


def _steps(states: dict[str, str]) -> list[dict]:
    return [{"key": key, "state": state} for key, state in states.items()]


def student_steps(counseling, shortlisted: int, documents: list, open_requests: bool) -> list[dict]:
    """Spec §4, steps 1-4."""
    if counseling is None:
        counseled = "not_started"
    else:
        counseled = "done" if counseling.counseling_completed else "in_progress"
    if not documents and not open_requests:
        docs = "not_started"
    elif documents and not open_requests and all(d.verification_status == "verified" for d in documents):
        docs = "done"
    else:
        docs = "in_progress"
    return _steps({"create": "done", "counseling": counseled, "shortlist": "done" if shortlisted else "not_started", "documents": docs})


def _visa_state(visa) -> str:
    if visa is None:
        return "not_started"
    return {"approved": "done", "refused": "refused", "withdrawn": "withdrawn"}.get(visa.decision, "in_progress")


def application_steps(app, deposit, visa) -> list[dict]:
    """Spec §4, steps 5-9, from the application's own columns, its deposit and its visa case."""
    stage = OVERSEAS_APPLICATION_STAGES.index(app.status) if app.status in OVERSEAS_APPLICATION_STAGES else -1
    states = {
        "application": "done" if app.submitted_on else "in_progress",
        "offer": "done" if app.offer_type or stage >= _OFFER else "not_started",
        "deposit": "not_started" if deposit is None else _DEPOSIT_STATES[deposit.status],
        "visa": _visa_state(visa),
        "enrollment": "done" if app.status == "enrolled" else "not_started",
    }
    if app.status == WITHDRAWN:
        states = {key: state if state in _SETTLED else "withdrawn" for key, state in states.items()}
    return _steps(states)


async def _full_name(db: AsyncSession, record: AgentStudent) -> str | None:
    """A linked student's name comes from their own account (AGN-004 F2)."""
    if record.student_id is None:
        return record.full_name
    return await db.scalar(select(User.full_name).where(User.id == record.student_id))


async def journey(db: AsyncSession, user: User, record: AgentStudent) -> dict:
    src = await _sources(db, user, record)
    counseling = await db.scalar(select(AgentStudentCounseling).where(AgentStudentCounseling.agent_student_id == record.id))
    shortlisted = await db.scalar(select(func.count()).select_from(AgentStudentShortlistEntry).where(AgentStudentShortlistEntry.agent_student_id == record.id))
    open_requests = any(r.status == "open" for r in src.requests.values())
    deposit_of = {d.application_id: d for d in src.deposits.values()}
    visa_of = {v.application_id: v for v in src.visas.values()}
    return {
        "student": {"id": record.id, "full_name": await _full_name(db, record), "status": record.status},
        "steps": student_steps(counseling, shortlisted or 0, list(src.documents.values()), open_requests),
        "applications": [
            {"id": a.id, "university": name, "intake": a.intake, "status": a.status, "steps": application_steps(a, deposit_of.get(a.id), visa_of.get(a.id))}
            for a, name in src.apps
        ],
    }
```

Route in `api/agent_students.py` (after `get_student`):

```python
@router.get("/{student_id}/journey")
async def get_student_journey(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-015 (DEC-SCOPE-060 §4): the step tracker. Read-only; out of scope is the same 404 as the detail."""
    membership = _gate(user)
    row = await load_scoped(db, user, student_id)
    result = await journey(db, user, row)
    _log("agent_student_journey_viewed", membership, user, row.id)
    return result
```

- [ ] **Step 5: Run** `tests/test_agn_015_journey.py` → PASS. **Step 6: Commit** `feat(agn-015): student journey step tracker`.

---

### Task 3: Timeline — union query, actors, route

**Files:** Modify `apps/api/app/services/agent_journey.py`, `apps/api/app/api/agent_students.py`; Create `apps/api/tests/test_agn_015_timeline.py`.

**Interfaces:**
- Consumes: `_sources` (Task 2).
- Produces: `async def timeline_page(db, user, record, *, limit: int, offset: int) -> dict`; `MAX_TIMELINE_OFFSET = 10_000`;
  `AUDIT_KINDS: dict[str, str]`; `ROLE_LABELS: dict[str, str]`.
- Route: `GET …/students/{student_id}/timeline?limit&offset`.

- [ ] **Step 1: Write failing tests** — each spec §3 source appears once with the right kind and actor; excluded duplicates don't
  appear; order newest first with rank ties; outside actor labels; field names only; pagination/total; legacy upload fallback.

```python
import pytest
from sqlalchemy import update

from app.models import AuditLog, DocumentEvent
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import mk_application
from tests.agn009_helpers import mk_doc, world
from tests.agn015_helpers import mk_audit, mk_history, timeline_url

KEYS = {"id", "at", "kind", "actor", "application", "document", "from_status", "to_status", "fields", "notes"}


async def _get(email, student_id, **params):
    async with client_for(email) as c:
        r = await c.get(timeline_url(student_id, **params))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_every_source_event_appears_once_with_its_actor(db_session):
    w = await world(db_session)
    rec, master, staff = w["record"], w["master"], w["staff"]["user"]
    app = await mk_application(db_session, agent=master, university=w["university"], record=rec)
    await mk_history(db_session, app, to_status="enquiry", by=staff)
    await mk_audit(db_session, user=staff, action="overseas.application.create", entity_type="overseas_application", entity_id=app.id)  # duplicate of history: excluded
    await mk_history(db_session, app, from_status="enquiry", to_status="offer", by=master, notes="Offer recorded: Conditional")
    await mk_audit(db_session, user=master, action="agent_student.assign", entity_type="agent_student", entity_id=rec.id, metadata={"from": None, "to": "x"})
    await mk_audit(db_session, user=staff, action="agent_student.counseling", entity_type="agent_student", entity_id=rec.id, metadata={"fields": ["budget_amount"]})
    await mk_audit(db_session, user=staff, action="agent_student.create", entity_type="agent_student", entity_id=rec.id)  # S1 holds it: excluded
    doc = await mk_doc(db_session, record=rec)
    db_session.add(DocumentEvent(document_id=doc.id, event="uploaded", actor_user_id=staff.id, to_status="pending"))
    await db_session.commit()
    await mk_audit(db_session, user=staff, action="document.upload", entity_type="student_document", entity_id=doc.id)  # S7 holds it: excluded
    body = await _get(master.email, rec.id)
    kinds = [i["kind"] for i in body["items"]]
    assert sorted(kinds) == sorted(["student_created", "application_created", "application_stage_changed", "student_assigned", "counseling_saved", "document_uploaded"])
    assert body["total"] == 6 and all(set(i) == KEYS for i in body["items"])
    by_kind = {i["kind"]: i for i in body["items"]}
    assert by_kind["application_stage_changed"]["actor"] == master.full_name
    assert (by_kind["application_stage_changed"]["from_status"], by_kind["application_stage_changed"]["to_status"]) == ("enquiry", "offer")
    assert by_kind["application_stage_changed"]["notes"] == "Offer recorded: Conditional"
    assert by_kind["application_stage_changed"]["application"] == {"id": str(app.id), "university": w["university"].name}
    assert by_kind["counseling_saved"]["fields"] == ["budget_amount"]
    assert by_kind["document_uploaded"]["document"] == {"id": str(doc.id), "type": "Passport"}
    assert by_kind["student_created"]["actor"] == master.full_name


@pytest.mark.asyncio
async def test_newest_first_and_same_transaction_ties_follow_source_rank(db_session):
    w = await world(db_session)
    rec, master = w["record"], w["master"]
    app = await mk_application(db_session, agent=master, university=w["university"], record=rec)
    h = await mk_history(db_session, app, to_status="enquiry", by=master)
    a = await mk_audit(db_session, user=master, action="overseas.application.update", entity_type="overseas_application", entity_id=app.id, metadata={"fields": ["intake"]})
    await db_session.execute(update(AuditLog).where(AuditLog.id == a.id).values(created_at=h.created_at))  # one transaction: shared now()
    await db_session.commit()
    kinds = [i["kind"] for i in (await _get(master.email, rec.id))["items"]]
    assert kinds.index("application_edited") < kinds.index("application_created")  # rank 4 (S4) before rank 3 (S3) at equal time, newest first
    assert kinds[-1] == "student_created"


@pytest.mark.asyncio
async def test_outside_actors_are_role_labels_and_values_never_leave(db_session):
    w = await world(db_session)
    rec, master = w["record"], w["master"]
    app = await mk_application(db_session, agent=master, university=w["university"], record=rec)
    counselor = await mk_user(db_session, role="counselor", full_name="Secret Counsellor")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Secret Admin")
    await mk_audit(db_session, user=counselor, action="overseas.application.update", entity_type="overseas_application", entity_id=app.id, metadata={"next_action": "call +44 7700 900123"})
    await mk_audit(db_session, user=None, action="overseas.application.deposit_paid", entity_type="overseas_application", entity_id=app.id, metadata={"payment_id": "p"})
    await mk_audit(db_session, user=admin, action="agent_student.archive", entity_type="agent_student", entity_id=rec.id)
    body = await _get(master.email, rec.id)
    text = str(body)
    assert "Secret" not in text and "7700" not in text
    by_kind = {i["kind"]: i for i in body["items"]}
    assert by_kind["application_edited"]["actor"] == "EduSphere counsellor" and by_kind["application_edited"]["fields"] == ["next_action"]
    assert by_kind["deposit_paid"]["actor"] == "System"
    assert by_kind["student_archived"]["actor"] == "EduSphere admin"


@pytest.mark.asyncio
async def test_unmapped_actions_are_not_events(db_session):
    w = await world(db_session)
    rec, master = w["record"], w["master"]
    app = await mk_application(db_session, agent=master, university=w["university"], record=rec)
    for action in ("overseas.application.deposit_checkout", "agent.commission_auto_create", "overseas.application.advance", "overseas.application.offer", "overseas.application.enroll"):
        await mk_audit(db_session, user=master, action=action, entity_type="overseas_application", entity_id=app.id)
    assert [i["kind"] for i in (await _get(master.email, rec.id))["items"]] == ["student_created"]


@pytest.mark.asyncio
async def test_legacy_upload_without_event_appears_once(db_session):
    w = await world(db_session)
    rec, master, staff = w["record"], w["master"], w["staff"]["user"]
    legacy = await mk_doc(db_session, record=rec)
    legacy.uploaded_by_user_id = staff.id
    current = await mk_doc(db_session, record=rec, document_type="CV")
    db_session.add(DocumentEvent(document_id=current.id, event="uploaded", actor_user_id=staff.id))
    await db_session.commit()
    items = (await _get(master.email, rec.id))["items"]
    uploads = [i for i in items if i["kind"] == "document_uploaded"]
    assert sorted(i["document"]["type"] for i in uploads) == ["CV", "Passport"]
    assert all(i["actor"] == staff.full_name for i in uploads)


@pytest.mark.asyncio
async def test_pagination_and_offset_past_the_end(db_session):
    w = await world(db_session)
    rec, master = w["record"], w["master"]
    for n in range(4):
        await mk_audit(db_session, user=master, action="agent_student.update", entity_type="agent_student", entity_id=rec.id, metadata={"fields": [f"f{n}"]})
    first = await _get(master.email, rec.id, limit=2, offset=0)
    second = await _get(master.email, rec.id, limit=2, offset=2)
    assert (first["total"], second["total"], first["limit"], second["offset"]) == (5, 5, 2, 2)
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})
    beyond = await _get(master.email, rec.id, offset=5000)
    assert beyond["items"] == [] and beyond["total"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10001}])
async def test_bad_paging_is_422(db_session, params):
    w = await world(db_session)
    async with client_for(w["master"].email) as c:
        assert (await c.get(timeline_url(w["record"].id, **params))).status_code == 422
```

- [ ] **Step 2: Run, expect FAIL** (404 on `/timeline`).
- [ ] **Step 3: Implement** — append to `services/agent_journey.py`:

```python
import uuid

from sqlalchemy import JSON, BigInteger, Integer, String, Text, Uuid, cast, exists, literal_column, null, union_all

from app.models import AgentOrgMember, ApplicationStatusHistory, AuditLog, DocumentEvent
from app.services.agent_orgs import org_member_ids

MAX_TIMELINE_OFFSET = 10_000

# §3: audit action -> kind. Anything else (create/advance/withdraw/offer/enroll, document.*, checkout, commission) is not an event.
STUDENT_AUDIT_KINDS = {
    "agent_student.update": "student_updated",
    "agent_student.duplicate_override": "student_duplicate_override",
    "agent_student.assign": "student_assigned",
    "agent_student.archive": "student_archived",
    "agent_student.unarchive": "student_restored",
    "agent_student.counseling": "counseling_saved",
    "agent_student.shortlist_add": "shortlist_added",
    "agent_student.shortlist_update": "shortlist_updated",
    "agent_student.shortlist_remove": "shortlist_removed",
    "agent_student.task_add": "task_added",
    "agent_student.task_update": "task_updated",
    "agent_student.task_complete": "task_completed",
    "agent_student.task_cancel": "task_cancelled",
}
APPLICATION_AUDIT_KINDS = {
    "overseas.application.update": "application_edited",
    "overseas.application.enrollment_update": "enrollment_updated",
    "overseas.application.visa_start": "visa_started",
    "overseas.application.visa_update": "visa_updated",
    "overseas.application.visa_advance": "visa_stage_changed",
    "overseas.application.visa_decision": "visa_decision_recorded",
    "overseas.application.deposit": "deposit_set",
    "overseas.application.deposit_paid": "deposit_paid",
}
DEPOSIT_AUDIT_KINDS = {"overseas.deposit.remit": "deposit_remitted", "overseas.deposit.refund": "deposit_refunded"}
VISA_AUDIT_KINDS = {"visa.create": "visa_started", "visa.update": "visa_updated"}
AUDIT_KINDS = STUDENT_AUDIT_KINDS | APPLICATION_AUDIT_KINDS | DEPOSIT_AUDIT_KINDS | VISA_AUDIT_KINDS
# Counselor paths store the changed VALUES as metadata (workflows.py); only their keys are shown (§3).
_KEY_FIELD_ACTIONS = {"overseas.application.update", "visa.update"}
_DOCUMENT_KINDS = {"cancelled": "document_request_cancelled"}

# §3 / J4: anyone outside the viewer's organisation is a role, never a name.
ROLE_LABELS = {
    "counselor": "EduSphere counsellor",
    "career_counselor": "EduSphere counsellor",
    "overseas_admin": "EduSphere admin",
    "super_admin": "EduSphere admin",
    "overseas_student": "Student",
    "it_student": "Student",
    "school_parent": "Parent",
    "university_rep": "University",
    "agent": "Agency user",
}
OTHER_USER, SYSTEM = "EduSphere user", "System"

_S, _N, _U = String(), Integer(), Uuid(as_uuid=True)


def _const(value: str):
    return literal_column(f"'{value}'", _S)  # module constants only -- never request input


def _branch(src: str, rank: int, row_id, at, raw, actor, *, ref=None, ref2=None, seq=None, from_status=None, to_status=None, notes=None, meta=None):
    return select(
        _const(src).label("src"),
        literal_column(str(rank), _N).label("rank"),
        cast(row_id, _S).label("row_id"),
        at.label("at"),
        (seq if seq is not None else cast(literal_column("0"), BigInteger)).label("seq"),
        raw.label("raw"),
        (actor if actor is not None else cast(null(), _U)).label("actor"),
        (cast(ref, _S) if ref is not None else cast(null(), _S)).label("ref"),
        (cast(ref2, _S) if ref2 is not None else cast(null(), _S)).label("ref2"),
        (from_status if from_status is not None else cast(null(), _S)).label("from_status"),
        (to_status if to_status is not None else cast(null(), _S)).label("to_status"),
        (notes if notes is not None else cast(null(), Text)).label("notes"),
        (meta if meta is not None else cast(null(), JSON)).label("meta"),
    )


def _audit_branch(src: str, rank: int, entity_type: str, ids, actions):
    return _branch(src, rank, AuditLog.id, AuditLog.created_at, AuditLog.action, AuditLog.user_id, ref=AuditLog.entity_id, meta=AuditLog.metadata_json).where(
        AuditLog.entity_type == entity_type, AuditLog.entity_id.in_([str(i) for i in ids]), AuditLog.action.in_(list(actions))
    )


def _branches(record: AgentStudent, src: Sources) -> list:
    app_ids = [a.id for a, _ in src.apps]
    H = ApplicationStatusHistory
    branches = [
        _branch("s1", 1, AgentStudent.id, AgentStudent.created_at, _const("student_created"), AgentStudent.agent_id).where(AgentStudent.id == record.id),
        _audit_branch("s2", 2, "agent_student", [record.id], STUDENT_AUDIT_KINDS),
    ]
    if app_ids:
        branches += [
            _branch("s3", 3, H.id, H.created_at, _const("history"), H.changed_by_id, ref=H.application_id, from_status=H.from_status, to_status=H.to_status, notes=H.notes).where(H.application_id.in_(app_ids)),
            _audit_branch("s4", 4, "overseas_application", app_ids, APPLICATION_AUDIT_KINDS),
        ]
    if src.deposits:
        branches.append(_audit_branch("s5", 5, "application_deposit", list(src.deposits), DEPOSIT_AUDIT_KINDS))
    if src.visas:
        branches.append(_audit_branch("s6", 6, "visa_case", list(src.visas), VISA_AUDIT_KINDS))
    E = DocumentEvent
    subject = [c for c in (E.document_id.in_(list(src.documents)) if src.documents else None, E.request_id.in_(list(src.requests)) if src.requests else None) if c is not None]
    if subject:
        branches.append(
            _branch("s7", 7, E.id, E.created_at, E.event, E.actor_user_id, ref=E.document_id, ref2=E.request_id, seq=E.seq, from_status=E.from_status, to_status=E.to_status, notes=E.notes).where(or_(*subject))
        )
    if src.documents:
        D = StudentDocument
        uploaded = exists().where(E.document_id == D.id, E.event == "uploaded")
        branches.append(_branch("s8", 8, D.id, D.created_at, _const("legacy_upload"), D.uploaded_by_user_id, ref=D.id).where(D.id.in_(list(src.documents)), ~uploaded))
    return branches


def _as_uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _history_kind(from_status, to_status) -> str:
    if from_status is None:
        return "application_created"
    if to_status == WITHDRAWN:
        return "application_withdrawn"
    if to_status == "enrolled" and from_status != "enrolled":
        return "application_enrolled"
    return "application_stage_changed" if from_status != to_status else "application_updated"


def _fields(raw: str, meta) -> list[str] | None:
    meta = meta if isinstance(meta, dict) else {}
    value = meta.get("fields")
    if isinstance(value, list):
        return [f for f in value if isinstance(f, str)]
    if raw in _KEY_FIELD_ACTIONS:
        return sorted(k for k in meta if isinstance(k, str))
    return None


async def _actors(db: AsyncSession, user: User, ids: set) -> dict:
    if not ids:
        return {}
    member = User.id.in_(org_member_ids(user))
    rows = (await db.execute(select(User.id, User.full_name, User.role, member).where(User.id.in_(ids)))).all()
    return {uid: name if is_member else ROLE_LABELS.get(role, OTHER_USER) for uid, name, role, is_member in rows}


def _item(row, src: Sources, universities: dict, actors: dict) -> dict:
    kind, fields, from_status, to_status, notes, app_id, document = None, None, None, None, None, None, None
    if row.src == "s1":
        kind = "student_created"
    elif row.src == "s3":
        kind, from_status, to_status, notes, app_id = _history_kind(row.from_status, row.to_status), row.from_status, row.to_status, row.notes, _as_uuid(row.ref)
    elif row.src in ("s2", "s4", "s5", "s6"):
        kind, fields = AUDIT_KINDS[row.raw], _fields(row.raw, row.meta)
        meta = row.meta if isinstance(row.meta, dict) else {}
        if row.raw == "overseas.application.visa_advance":
            from_status, to_status = meta.get("from_stage"), meta.get("to_stage")
        ref = _as_uuid(row.ref)
        app_id = {"s4": ref, "s5": getattr(src.deposits.get(ref), "application_id", None), "s6": getattr(src.visas.get(ref), "application_id", None)}.get(row.src)
    else:  # s7 document events, s8 legacy uploads
        kind = "document_uploaded" if row.src == "s8" else _DOCUMENT_KINDS.get(row.raw, f"document_{row.raw}")
        if row.src == "s7":
            from_status, to_status, notes = row.from_status, row.to_status, row.notes
        doc, req = src.documents.get(_as_uuid(row.ref)), src.requests.get(_as_uuid(row.ref2))
        if doc is not None:
            document, app_id = {"id": doc.id, "type": doc.document_type}, doc.application_id
        elif req is not None:
            document = {"id": req.id, "type": req.document_type}
    return {
        "id": f"{row.src}:{row.row_id}",
        "at": row.at,
        "kind": kind,
        "actor": actors.get(row.actor, OTHER_USER) if row.actor is not None else SYSTEM,
        "application": {"id": app_id, "university": universities.get(app_id)} if app_id in universities else None,
        "document": document,
        "from_status": from_status,
        "to_status": to_status,
        "fields": fields,
        "notes": notes,
    }


async def timeline_page(db: AsyncSession, user: User, record: AgentStudent, *, limit: int, offset: int) -> dict:
    """Spec §3/§5: one statement orders and pages every source; `total` comes from the same snapshot (count(*) OVER ())."""
    src = await _sources(db, user, record)
    events = union_all(*_branches(record, src)).subquery()
    stmt = select(events, func.count().over().label("total")).order_by(events.c.at.desc(), events.c.rank.desc(), events.c.seq.desc(), events.c.row_id.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).all()
    total = rows[0].total if rows else await db.scalar(select(func.count()).select_from(events))
    universities = {a.id: name for a, name in src.apps}
    actors = await _actors(db, user, {r.actor for r in rows if r.actor is not None})
    return {"items": [_item(r, src, universities, actors) for r in rows], "total": total or 0, "limit": limit, "offset": offset}
```

Route (after the journey route):

```python
@router.get("/{student_id}/timeline")
async def get_student_timeline(
    student_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=MAX_TIMELINE_OFFSET),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AGN-015 (DEC-SCOPE-060 §3/§5): the student's complete history, newest first. Read-only; out of scope is the same 404."""
    membership = _gate(user)
    row = await load_scoped(db, user, student_id)
    page = await timeline_page(db, user, row, limit=limit, offset=offset)
    _log("agent_student_timeline_viewed", membership, user, row.id, offset=offset)
    return page
```

- [ ] **Step 4: Run** `tests/test_agn_015_timeline.py tests/test_agn_015_journey.py` → PASS.
- [ ] **Step 5: Refactor** (imports grouped at module top; no behaviour change) → rerun → PASS. **Commit** `feat(agn-015): complete student history timeline`.

---

### Task 4: Authorization and isolation tests

**Files:** Create `apps/api/tests/test_agn_015_security.py`. No production change expected; any failure is a real bug fixed in Task 2/3 code.

- [ ] **Step 1: Tests**

```python
import pytest

from app.models import AgentStudent
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import mk_application
from tests.agn009_helpers import mk_doc, world
from tests.agn015_helpers import journey_url, mk_history, timeline_url


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [journey_url, timeline_url])
async def test_out_of_scope_is_the_same_404(db_session, url):
    w = await world(db_session)
    async with client_for(w["plain"]["user"].email) as c:  # staff, not assigned
        unassigned = await c.get(url(w["record"].id))
        unknown = await c.get(url("00000000-0000-0000-0000-000000000000"))
    async with client_for(w["other"]["master"].email) as c:
        other = await c.get(url(w["record"].id))
    assert unassigned.status_code == unknown.status_code == other.status_code == 404
    assert unassigned.json() == unknown.json() == other.json() == {"detail": "Student not found"}


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [journey_url, timeline_url])
async def test_non_agent_roles_are_refused(db_session, url):
    w = await world(db_session)
    counselor = await mk_user(db_session, role="counselor")
    async with client_for(counselor.email) as c:
        assert (await c.get(url(w["record"].id))).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [journey_url, timeline_url])
async def test_no_session_is_401(client, url):
    assert (await client.get(url("00000000-0000-0000-0000-000000000000"))).status_code == 401


@pytest.mark.asyncio
async def test_another_agencys_application_for_the_same_login_is_invisible(db_session):
    w = await world(db_session)
    other_record = AgentStudent(agent_id=w["other"]["master"].id, student_id=w["linked_user"].id, status="active")
    db_session.add(other_record)
    await db_session.commit()
    theirs = await mk_application(db_session, agent=w["other"]["master"], university=w["university"], record=other_record)
    await mk_history(db_session, theirs, to_status="enquiry", by=w["other"]["master"])
    await mk_doc(db_session, record=other_record)
    async with client_for(w["staff"]["user"].email) as c:
        j = (await c.get(journey_url(w["linked_record"].id))).json()
        t = (await c.get(timeline_url(w["linked_record"].id))).json()
    assert j["applications"] == [] and j["student"]["full_name"] == w["linked_user"].full_name
    assert [i["kind"] for i in t["items"]] == ["student_created"]


@pytest.mark.asyncio
async def test_archived_student_is_readable(db_session):
    w = await world(db_session)
    w["record"].status = "archived"
    await db_session.commit()
    async with client_for(w["master"].email) as c:
        assert (await c.get(journey_url(w["record"].id))).json()["student"]["status"] == "archived"
        assert (await c.get(timeline_url(w["record"].id))).status_code == 200
```

- [ ] **Step 2: Run** all `tests/test_agn_015_*.py` → PASS (RED expected only if a scope bug exists). **Commit** `test(agn-015): scope, role and isolation`.

---

### Task 5: Web library `lib/agentJourney.ts`

**Files:** Create `apps/web/lib/agentJourney.ts`, `apps/web/tests/lib/agentJourney.test.ts`.

**Interfaces (Produces):** `journeyUrl(id)`, `timelineUrl(id, limit, offset)`, types `JourneyStep`, `JourneyApplication`, `Journey`,
`TimelineItem`, `STEP_LABELS`, `STATE_LABELS`, `kindLabel(kind)`, `isJourney(body)`, `currentStep(steps)`.

- [ ] **Step 1: Failing test**

```ts
import { describe, expect, it } from "vitest";

import { currentStep, isJourney, journeyUrl, kindLabel, STATE_LABELS, STEP_LABELS, timelineUrl } from "@/lib/agentJourney";

describe("agentJourney (AGN-015)", () => {
  it("builds the two URLs", () => {
    expect(journeyUrl("s1")).toBe("/api/v1/workflows/overseas/agent/crm/students/s1/journey");
    expect(timelineUrl("s1", 20, 40)).toBe("/api/v1/workflows/overseas/agent/crm/students/s1/timeline?limit=20&offset=40");
  });
  it("labels all nine steps and every state", () => {
    expect(Object.keys(STEP_LABELS)).toEqual(["create", "counseling", "shortlist", "documents", "application", "offer", "deposit", "visa", "enrollment"]);
    expect(STATE_LABELS.not_required).toBe("Not required");
  });
  it("labels kinds and humanises unknown ones", () => {
    expect(kindLabel("application_stage_changed")).toBe("Application stage changed");
    expect(kindLabel("document_request_cancelled")).toBe("Document request cancelled");
    expect(kindLabel("brand_new_kind")).toBe("Brand new kind");
  });
  it("guards the journey shape", () => {
    expect(isJourney({ student: { id: "s1" }, steps: [], applications: [] })).toBe(true);
    expect(isJourney({ items: [], total: 0 })).toBe(false);
    expect(isJourney(null)).toBe(false);
  });
  it("finds the first unfinished step", () => {
    expect(currentStep([{ key: "create", state: "done" }, { key: "counseling", state: "in_progress" }])).toBe("counseling");
    expect(currentStep([{ key: "create", state: "done" }])).toBeNull();
  });
});
```

- [ ] **Step 2: Run** `npx vitest run tests/lib/agentJourney.test.ts` → FAIL (module missing).
- [ ] **Step 3: Implement**

```ts
import { RECORDS_URL } from "./agentStudents";

// AGN-015 (DEC-SCOPE-060): the student's step tracker and complete history (spec §4-§5).
export const journeyUrl = (id: string) => `${RECORDS_URL}/${id}/journey`;
export const timelineUrl = (id: string, limit: number, offset: number) => `${RECORDS_URL}/${id}/timeline?limit=${limit}&offset=${offset}`;

export type StepState = "not_started" | "in_progress" | "done" | "not_required" | "refunded" | "refused" | "withdrawn";
export type JourneyStep = { key: string; state: StepState };
export type JourneyApplication = { id: string; university: string | null; intake: string; status: string; steps: JourneyStep[] };
export type Journey = { student: { id: string; full_name: string | null; status: string }; steps: JourneyStep[]; applications: JourneyApplication[] };
export type TimelineItem = {
  id: string;
  at: string;
  kind: string;
  actor: string;
  application: { id: string; university: string | null } | null;
  document: { id: string; type: string } | null;
  from_status: string | null;
  to_status: string | null;
  fields: string[] | null;
  notes: string | null;
};

export const STEP_LABELS: Record<string, string> = {
  create: "Create", counseling: "Counseling", shortlist: "Shortlist", documents: "Documents", application: "Application",
  offer: "Offer", deposit: "Deposit", visa: "Visa", enrollment: "Enrollment",
};

export const STATE_LABELS: Record<StepState, string> = {
  not_started: "Not started", in_progress: "In progress", done: "Done", not_required: "Not required", refunded: "Refunded",
  refused: "Refused", withdrawn: "Withdrawn",
};

// Settled states end a step: the tracker marks the first step NOT in this set as the current one.
const SETTLED: StepState[] = ["done", "not_required", "refunded", "refused", "withdrawn"];

const KIND_LABELS: Record<string, string> = {
  student_created: "Student created", student_updated: "Student details edited", student_duplicate_override: "Saved despite a possible duplicate",
  student_assigned: "Assigned to staff", student_archived: "Archived", student_restored: "Restored",
  counseling_saved: "Counseling saved", shortlist_added: "University shortlisted", shortlist_updated: "Shortlist entry edited",
  shortlist_removed: "University removed from shortlist", task_added: "Task added", task_updated: "Task edited", task_completed: "Task completed",
  task_cancelled: "Task cancelled", application_created: "Application created", application_stage_changed: "Application stage changed",
  application_withdrawn: "Application withdrawn", application_enrolled: "Enrolled", application_updated: "Application updated",
  application_edited: "Application details edited", enrollment_updated: "Enrollment details corrected", visa_started: "Visa case started",
  visa_updated: "Visa details updated", visa_stage_changed: "Visa stage changed", visa_decision_recorded: "Visa decision recorded",
  deposit_set: "Deposit set", deposit_paid: "Deposit paid", deposit_remitted: "Deposit remitted", deposit_refunded: "Deposit refunded",
  document_uploaded: "Document uploaded", document_replaced: "Document replaced", document_verified: "Document verified",
  document_rejected: "Document rejected", document_changes_required: "Document changes requested", document_requested: "Document requested",
  document_fulfilled: "Document request fulfilled", document_request_cancelled: "Document request cancelled", document_downloaded: "Document downloaded",
};

const humanise = (value: string) => value.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? humanise(kind);
}

export function isJourney(body: unknown): body is Journey {
  const b = body as Partial<Journey> | null;
  return !!b && typeof b === "object" && !!b.student && Array.isArray(b.steps) && Array.isArray(b.applications);
}

export function currentStep(steps: JourneyStep[]): string | null {
  return steps.find((s) => !SETTLED.includes(s.state))?.key ?? null;
}
```

- [ ] **Step 4: Run** → PASS. **Commit** `feat(agn-015): web journey library`.

---

### Task 6: `AgentStudentJourney` tracker component + CSS

**Files:** Create `apps/web/components/AgentStudentJourney.tsx`, `apps/web/tests/components/AgentStudentJourney.test.tsx`; Modify `apps/web/app/globals.css` (append `.jny-*`).

**Interfaces:** `export default function AgentStudentJourney({ studentId, refreshKey }: { studentId: string; refreshKey?: string })`.

- [ ] **Step 1: Failing test**

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentJourney from "@/components/AgentStudentJourney";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const journey = {
  student: { id: "s1", full_name: "Asha", status: "active" },
  steps: [{ key: "create", state: "done" }, { key: "counseling", state: "in_progress" }, { key: "shortlist", state: "not_started" }, { key: "documents", state: "not_started" }],
  applications: [{ id: "a1", university: "Leeds", intake: "Fall 2027", status: "offer", steps: [
    { key: "application", state: "done" }, { key: "offer", state: "done" }, { key: "deposit", state: "not_required" }, { key: "visa", state: "in_progress" }, { key: "enrollment", state: "not_started" },
  ] }],
};

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("AgentStudentJourney (AGN-015)", () => {
  it("shows loading, then each step with its state as text and the current step marked", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(journey)));
    render(<AgentStudentJourney studentId="s1" />);
    expect(screen.getByText("Loading journey…")).toBeInTheDocument();
    const steps = await screen.findByRole("list", { name: "Student steps" });
    expect(within(steps).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["CreateDone", "CounselingIn progress", "ShortlistNot started", "DocumentsNot started"]);
    expect(within(steps).getByText("Counseling").closest("li")).toHaveAttribute("aria-current", "step");
    const app = screen.getByRole("list", { name: "Steps for Leeds" });
    expect(within(app).getByText("Deposit").closest("li")).toHaveTextContent("Not required");
    expect(within(app).getByText("Visa").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText(/Leeds · Fall 2027 · Offer/)).toBeInTheDocument();
  });

  it("says when there are no applications", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ ...journey, applications: [] })));
    render(<AgentStudentJourney studentId="s1" />);
    expect(await screen.findByText("No applications yet.")).toBeInTheDocument();
  });

  it("shows an error with Try again, and recovers", async () => {
    const mock = vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res(journey));
    vi.stubGlobal("fetch", mock);
    render(<AgentStudentJourney studentId="s1" />);
    expect(await screen.findByText("Unable to load the journey.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("list", { name: "Student steps" })).toBeInTheDocument();
  });

  it("offers sign-in on an expired session", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({}, 401)));
    render(<AgentStudentJourney studentId="s1" />);
    expect(await screen.findByRole("link", { name: "Sign in again" })).toBeInTheDocument();
  });

  it("treats an unexpected body as an error, not a crash", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ items: [], total: 0 })));
    render(<AgentStudentJourney studentId="s1" />);
    expect(await screen.findByText("Unable to load the journey.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**

```tsx
"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { SESSION_EXPIRED, SIGN_IN_PATH } from "@/lib/activityFeedback";
import { stageLabel } from "@/lib/agentApplications";
import { currentStep, isJourney, journeyUrl, STATE_LABELS, STEP_LABELS, type Journey, type JourneyStep } from "@/lib/agentJourney";

const UNABLE = "Unable to load the journey.";
const GLYPH: Record<string, string> = { done: "✓", in_progress: "•", not_started: "–", not_required: "✓", refunded: "↺", refused: "✕", withdrawn: "✕" };

function Steps({ label, steps }: { label: string; steps: JourneyStep[] }) {
  const current = currentStep(steps);
  return (
    <ol className="jny-steps" aria-label={label}>
      {steps.map((s) => (
        <li key={s.key} className={`jny-step jny-${s.state}`} aria-current={s.key === current ? "step" : undefined}>
          <span className="jny-glyph" aria-hidden="true">{GLYPH[s.state] ?? "–"}</span>
          <span className="jny-name">{STEP_LABELS[s.key] ?? s.key}</span>
          <span className="jny-state">{STATE_LABELS[s.state] ?? s.state}</span>
        </li>
      ))}
    </ol>
  );
}

// AGN-015 (DEC-SCOPE-060 §4, §7): steps 1-4 once for the student, steps 5-9 per application. Read on open and whenever the student
// changes (refreshKey); only the newest request may update the screen. Errors are inline text, not role="alert" (the detail panel's
// own alerts stay unique).
export default function AgentStudentJourney({ studentId, refreshKey }: { studentId: string; refreshKey?: string }) {
  const [data, setData] = useState<Journey | null>(null);
  const [failure, setFailure] = useState<{ text: string; expired: boolean } | null>(null);
  const latest = useRef(0);

  const load = useCallback(() => {
    const request = ++latest.current;
    setFailure(null);
    fetch(journeyUrl(studentId))
      .then(async (response) => {
        if (response.status === 401) return { text: SESSION_EXPIRED, expired: true };
        const body: unknown = await response.json().catch(() => null);
        if (!response.ok || !isJourney(body)) return { text: UNABLE, expired: false };
        if (request === latest.current) setData(body);
        return null;
      })
      .catch(() => ({ text: UNABLE, expired: false }))
      .then((failed) => {
        if (failed && request === latest.current) setFailure(failed);
      });
  }, [studentId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const headingId = `journey-${studentId}`;
  return (
    <section aria-labelledby={headingId} className="jny" style={{ marginTop: 16 }}>
      <h5 id={headingId} style={{ fontSize: "18px", margin: "0 0 8px" }}>Journey</h5>
      {failure ? (
        failure.expired ? (
          <p className="form-error">{failure.text} <Link href={SIGN_IN_PATH}>Sign in again</Link></p>
        ) : (
          <p className="form-error">
            {failure.text}{" "}
            <button type="button" className="btn secondary small" onClick={load}>Try again</button>
          </p>
        )
      ) : data === null ? (
        <p className="muted" role="status">Loading journey…</p>
      ) : (
        <>
          <Steps label="Student steps" steps={data.steps} />
          {data.applications.length === 0 ? (
            <p className="muted">No applications yet.</p>
          ) : (
            data.applications.map((a) => (
              <div key={a.id} className="jny-app">
                <p className="jny-caption">{[a.university ?? "Unknown university", a.intake, stageLabel(a.status)].join(" · ")}</p>
                <Steps label={`Steps for ${a.university ?? "Unknown university"}`} steps={a.steps} />
              </div>
            ))
          )}
        </>
      )}
    </section>
  );
}
```

CSS appended to `app/globals.css` (existing tokens only):

```css
/* AGN-015: student journey step tracker -- wraps on desktop, one column on phones; state is text, never colour alone. */
.jny-steps{list-style:none;display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px;padding:0}
.jny-step{display:flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:13px;min-width:0}
.jny-step[aria-current="step"]{border-color:var(--blue);box-shadow:0 0 0 1px var(--blue)}
.jny-glyph{font-weight:800;width:1em;text-align:center}
.jny-name{font-weight:700;color:var(--ink)}
.jny-state{color:var(--muted)}
.jny-done .jny-glyph{color:var(--green,#15803d)}
.jny-caption{margin:8px 0 4px;font-size:13px;font-weight:700;color:var(--ink);overflow-wrap:anywhere}
@media (max-width:640px){.jny-steps{flex-direction:column}.jny-step{width:100%}}
```

(Check `stageLabel` is exported from `lib/agentApplications.ts`; it is, line 13.)

- [ ] **Step 4: Run** → PASS. **Commit** `feat(agn-015): journey step tracker component`.

---

### Task 7: `AgentStudentTimeline` history component

**Files:** Create `apps/web/components/AgentStudentTimeline.tsx`, `apps/web/tests/components/AgentStudentTimeline.test.tsx`.

**Interfaces:** `export default function AgentStudentTimeline({ studentId }: { studentId: string })`.

- [ ] **Step 1: Failing test**

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentTimeline from "@/components/AgentStudentTimeline";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const item = (n: number, extra: Record<string, unknown> = {}) => ({
  id: `s2:${n}`, at: "2026-10-01T09:30:00Z", kind: "counseling_saved", actor: "Priya", application: null, document: null,
  from_status: null, to_status: null, fields: ["budget_amount"], notes: null, ...extra,
});
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("AgentStudentTimeline (AGN-015)", () => {
  it("loads nothing until Show history, then lists events with actor, subject and stages", async () => {
    const mock = vi.fn().mockResolvedValue(res(page([
      item(1),
      item(2, { kind: "application_stage_changed", actor: "EduSphere counsellor", application: { id: "a1", university: "Leeds" }, from_status: "enquiry", to_status: "offer", fields: null, notes: "Offer recorded: Conditional" }),
    ])));
    vi.stubGlobal("fetch", mock);
    render(<AgentStudentTimeline studentId="s1" />);
    expect(mock).not.toHaveBeenCalled();
    const toggle = screen.getByRole("button", { name: "Show history" });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const list = await screen.findByRole("list", { name: "Student history" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Counseling saved");
    expect(rows[0]).toHaveTextContent("budget amount");
    expect(rows[0]).toHaveTextContent("Priya");
    expect(rows[1]).toHaveTextContent("Leeds");
    expect(rows[1]).toHaveTextContent("Enquiry → Offer");
    expect(rows[1]).toHaveTextContent("EduSphere counsellor");
    expect(rows[1]).toHaveTextContent("Offer recorded: Conditional");
    expect(mock).toHaveBeenCalledWith("/api/v1/workflows/overseas/agent/crm/students/s1/timeline?limit=20&offset=0");
  });

  it("shows the empty state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([]))));
    render(<AgentStudentTimeline studentId="s1" />);
    fireEvent.click(screen.getByRole("button", { name: "Show history" }));
    expect(await screen.findByText("No history yet.")).toBeInTheDocument();
  });

  it("pages with Next and Previous", async () => {
    const mock = vi.fn()
      .mockResolvedValueOnce(res(page(Array.from({ length: 20 }, (_, i) => item(i)), 25)))
      .mockResolvedValueOnce(res(page([item(99)], 25, 20)));
    vi.stubGlobal("fetch", mock);
    render(<AgentStudentTimeline studentId="s1" />);
    fireEvent.click(screen.getByRole("button", { name: "Show history" }));
    expect(await screen.findByText("Showing 1–20 of 25")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Showing 21–21 of 25")).toBeInTheDocument();
    expect(mock).toHaveBeenLastCalledWith("/api/v1/workflows/overseas/agent/crm/students/s1/timeline?limit=20&offset=20");
  });

  it("shows a retryable error and a sign-in link on 401", async () => {
    const mock = vi.fn().mockResolvedValueOnce(res({}, 500)).mockResolvedValueOnce(res({}, 401));
    vi.stubGlobal("fetch", mock);
    render(<AgentStudentTimeline studentId="s1" />);
    fireEvent.click(screen.getByRole("button", { name: "Show history" }));
    expect(await screen.findByText("Unable to load history.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "Sign in again" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (AGN-021 `AgentStaffActivity` pattern):

```tsx
"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { SESSION_EXPIRED, SIGN_IN_PATH } from "@/lib/activityFeedback";
import { stageLabel } from "@/lib/agentApplications";
import { kindLabel, timelineUrl, type TimelineItem } from "@/lib/agentJourney";
import { isPage, type Page } from "@/lib/apiErrors";
import { formatDate, viewerTimeZone } from "@/lib/formatDate";

const PAGE_SIZE = 20;
const UNABLE = "Unable to load history.";

class LoadFailed extends Error {
  constructor(text: string, readonly expired = false) {
    super(text);
  }
}

function subject(item: TimelineItem): string {
  return [item.application?.university, item.document?.type].filter(Boolean).join(" · ");
}

// AGN-015 (DEC-SCOPE-060 §3, §7): the student's complete history, newest first. Hidden until asked for, so opening a student costs
// one request (the journey), not two. Read on every open / page / Refresh (no cache); only the newest request may update the screen.
export default function AgentStudentTimeline({ studentId }: { studentId: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Page<TimelineItem> | null>(null);
  const [failure, setFailure] = useState<{ text: string; expired: boolean } | null>(null);
  const [loading, setLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const latest = useRef(0);
  const listId = `history-${studentId}`;

  const load = useCallback(
    (at: number) => {
      const request = ++latest.current;
      setLoading(true);
      setFailure(null);
      fetch(timelineUrl(studentId, PAGE_SIZE, at))
        .then(async (response) => {
          if (response.status === 401) throw new LoadFailed(SESSION_EXPIRED, true);
          const body: unknown = await response.json().catch(() => null);
          if (!response.ok || !isPage<TimelineItem>(body)) throw new LoadFailed(UNABLE);
          if (request === latest.current) setData(body);
        })
        .catch((caught: unknown) => {
          if (request !== latest.current) return;
          setFailure(caught instanceof LoadFailed ? { text: caught.message, expired: caught.expired } : { text: UNABLE, expired: false });
        })
        .finally(() => {
          if (request === latest.current) setLoading(false);
        });
    },
    [studentId],
  );

  useEffect(() => {
    if (open) load(offset);
  }, [open, load, offset]);

  return (
    <div style={{ marginTop: 16 }}>
      <button type="button" className="btn secondary small" aria-expanded={open} aria-controls={listId} onClick={() => setOpen(!open)}>
        {open ? "Hide history" : "Show history"}
      </button>
      {open && (
        <div id={listId} style={{ marginTop: 8 }}>
          {failure ? (
            failure.expired ? (
              <p className="form-error" role="alert">{failure.text} <Link href={SIGN_IN_PATH}>Sign in again</Link></p>
            ) : (
              <>
                <p className="form-error" role="alert">{failure.text}</p>
                <button type="button" className="btn secondary small" onClick={() => load(offset)}>Try again</button>
              </>
            )
          ) : data === null ? (
            <p className="muted" role="status">Loading history…</p>
          ) : data.items.length === 0 ? (
            <p className="muted">No history yet.</p>
          ) : (
            <>
              {loading && <p className="muted" role="status" style={{ fontSize: 13, margin: "0 0 4px" }}>Updating history…</p>}
              <ol aria-label="Student history" aria-busy={loading} style={{ paddingLeft: 18, margin: "4px 0", opacity: loading ? 0.6 : 1 }}>
                {data.items.map((item) => (
                  <li key={item.id} style={{ fontSize: 13, marginBottom: 6, overflowWrap: "anywhere" }}>
                    <strong>{kindLabel(item.kind)}</strong>
                    {subject(item) ? ` · ${subject(item)}` : ""}
                    {item.from_status && item.to_status ? ` · ${stageLabel(item.from_status)} → ${stageLabel(item.to_status)}` : ""}
                    {item.fields && item.fields.length > 0 ? ` — ${item.fields.map((f) => f.replaceAll("_", " ")).join(", ")}` : ""}
                    {" · "}{item.actor}{" "}
                    <span className="muted"><time dateTime={item.at}>{formatDate(item.at, true, viewerTimeZone())}</time></span>
                    {item.notes && <span className="history-note" style={{ display: "block" }}>{item.notes}</span>}
                  </li>
                ))}
              </ol>
            </>
          )}
          {data && !failure && data.total > PAGE_SIZE && (
            <nav aria-label="History pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, margin: "4px 0" }}>
              <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" aria-label="Next page" disabled={loading || offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
            </nav>
          )}
          {!failure && data && <button type="button" className="btn secondary small" onClick={() => load(offset)}>Refresh</button>}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run** → PASS. **Commit** `feat(agn-015): student history component`.

---

### Task 8: Mount in `AgentStudentDetailPanel`; keep existing panel tests green

**Files:** Modify `apps/web/components/AgentStudentDetailPanel.tsx`; possibly the fetch routing (not assertions) in
`apps/web/tests/components/AgentStudentsPanel.test.tsx`, `AgentStudentCounselingCard.test.tsx`; Create
`apps/web/tests/components/AgentStudentDetailPanel.journey.test.tsx`.

- [ ] **Step 1: Failing test** — rendering the detail panel shows a "Journey" region and a "Show history" button; while a form is
  open (Edit) neither is shown.

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentDetailPanel from "@/components/AgentStudentDetailPanel";
import type { AgentStudentDetail } from "@/lib/agentStudents";

const res = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
const detail = {
  id: "s1", has_login: false, full_name: "Asha", email: null, phone: null, preferred_country: null, preferred_intake: null, status: "active",
  assigned_to: null, created_at: "2026-10-01T09:00:00Z", date_of_birth: null, highest_qualification: null, institution: null, graduation_year: null,
  preferred_course: null, notes: null, created_by: "Master", archived_at: null, archived_by: null, updated_at: "2026-10-01T09:00:00Z", counseling: null,
} as unknown as AgentStudentDetail;

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("AgentStudentDetailPanel journey (AGN-015)", () => {
  it("shows the Journey and the history toggle beside the record, and hides them while editing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) =>
      Promise.resolve(res(url.endsWith("/journey") ? { student: { id: "s1" }, steps: [], applications: [] } : { items: [], total: 0, limit: 20, offset: 0 }))));
    render(<AgentStudentDetailPanel detail={detail} onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getByRole("region", { name: "Journey" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show history" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.queryByRole("region", { name: "Journey" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Show history" })).toBeNull();
  });
});
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** — in the panel's `editing === "none"` branch, after the record details' Edit
  button: `{editing === "none" && <AgentStudentJourney studentId={detail.id} refreshKey={detail.updated_at ?? undefined} />}`;
  after the Tasks section: `{editing === "none" && <AgentStudentTimeline studentId={detail.id} />}`. Imports added.
- [ ] **Step 4: Run** the new test + `AgentStudentsPanel.test.tsx AgentStudentCounselingCard.test.tsx AgentStudentsSection.test.tsx`.
  If a queued `mockResolvedValueOnce` is consumed by the journey fetch, route `/journey` URLs in that test's fetch stub to a journey
  body (fetch routing only; no assertion changes). → PASS. `npx tsc --noEmit` → clean. **Commit** `feat(agn-015): journey and history on the student detail`.

---

### Task 9: E2E spec (not run here) and documentation

**Files:** Create `apps/web/tests/e2e/agn-015-student-journey.spec.ts` (Master opens a student with an application → "Journey"
region with "Student steps" and "Steps for …" lists; Show history → "Student history" list with "Student created"; 320px no
horizontal overflow — the agn-006 `openStudent` pattern). Modify `docs/decisions/PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-060`),
`docs/architecture/API_CONTRACT.md` (two routes), `docs/architecture/DATA_MODEL.md` (index), `docs/quality/RTM.md`,
`docs/delivery/AGENT_CRM_BACKLOG.md` (status row), `docs/delivery/ENHANCEMENT_BACKLOG.md` (AGN-015 entry).

- [ ] **Step 1:** Write the e2e spec (owner runs it in the full/browser pass). `npx tsc --noEmit` covers its types.
- [ ] **Step 2:** Docs as listed, each citing the spec. **Commit** `docs(agn-015): decision, contracts, RTM`.

Status at the end of this plan: **implemented, lite-tested, not complete** — browser validation and independent review pending.
