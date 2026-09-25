# ENH-018 School Activity Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A School Coordinator records one structured feedback (§31 fields) per completed Edusphere activity of their school; the principal reads it; Overseas/Super admins read every school's.

**Architecture:** One new create-only table (`school_activity_feedback`, FK + UNIQUE on `school_activities.id`) and one new API module `app/api/school_feedback.py` with a `/school` router and an `/overseas-admin` router (the ENH-005 `school_transfers.py` shape). Participation is computed from `SchoolActivityAttendance` at read time. Frontend adds a Feedback page for coordinator/principal, an admin page, and a link from the existing Activities list; no existing endpoint or response changes.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 async + asyncpg, Alembic, pytest/pytest-asyncio/httpx; Next.js App Router, React, vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-23-enh-018-school-activity-feedback-design.md`

## Global Constraints

- No change to any existing endpoint, response shape, table, or migration; everything is additive.
- No new dependency (backend or frontend).
- Migration `0039_school_activity_feedback`, `down_revision = "0038_portfolio"`; create-only; downgrade drops only the new table.
- `detail` strings (exact): `"Activity not found"`, `"Feedback is only collected for Edusphere activities"`, `"Feedback opens once the activity has taken place"`, `"Feedback has already been submitted for this activity"`.
- Scores: integers 1–5 (strict JSON integers). `feedback` required ≤ 5000; `suggestions` optional ≤ 5000; `trainer_name` optional ≤ 200, single line.
- Roles: POST `school_coordinator`; school read `school_coordinator`, `school_principal`; admin read `overseas_admin`, `super_admin`.
- Paging: `limit` 1–100 default 25, `offset` ≥ 0, page body `{items, total, limit, offset}`.
- Free text is never logged or written to `AuditLog`.
- Backend DB tests need the Postgres stack (user-run `docker compose up`) with `alembic upgrade head` applied.

## Review Focus

1. Activity exactly around "now" (tz-aware `scheduled_at`): one minute ago is eligible, one minute ahead is 422 — pinned in Task 3.
2. Whitespace-only `feedback` must be 422, never stored blank — pinned in Task 2.
3. A lost response then retry: server answers 409 and the UI shows the stored feedback instead of an error — pinned in Tasks 3 and 8.
4. A coordinator account with no linked school gets 403 on every route, not 500 — pinned in Tasks 3 and 4.
5. A very long unbroken word in feedback must not overflow horizontally at 320px — pinned in Task 11 (e2e) via `overflow-wrap:anywhere`.

---

### Task 1: Model and migration

**Files:**
- Modify: `apps/api/app/models.py` (after `SchoolActivityAttendance`, ~line 1154)
- Create: `apps/api/alembic/versions/0039_school_activity_feedback.py`
- Test: `apps/api/tests/test_enh_018_model.py`

**Interfaces:**
- Produces: `app.models.SchoolActivityFeedback` with columns `id, activity_id, school_id, submitted_by_user_id, trainer_name, rating, satisfaction, feedback, suggestions, created_at, updated_at`; constraint names `uq_activity_feedback_activity`, `ck_activity_feedback_rating`, `ck_activity_feedback_satisfaction`.

- [ ] **Step 1: Write the failing test** (no database needed — ENH-011 pattern)

```python
import importlib.util
import io
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.schema import CheckConstraint, UniqueConstraint

from app.models import SchoolActivityFeedback

# ENH-018 spec §4: one create-only table. Checked through metadata and an offline SQL render; no database needed.

MIGRATION = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0039_school_activity_feedback.py"


def _names(kind):
    return {c.name for c in SchoolActivityFeedback.__table__.constraints if isinstance(c, kind)}


def test_table_shape_matches_the_spec():
    assert SchoolActivityFeedback.__tablename__ == "school_activity_feedback"
    assert set(SchoolActivityFeedback.__table__.c.keys()) == {
        "id", "activity_id", "school_id", "submitted_by_user_id", "trainer_name", "rating", "satisfaction", "feedback", "suggestions", "created_at", "updated_at",
    }
    c = SchoolActivityFeedback.__table__.c
    assert not c.feedback.nullable and not c.rating.nullable and not c.satisfaction.nullable
    assert c.trainer_name.nullable and c.suggestions.nullable and c.trainer_name.type.length == 200


def test_one_feedback_per_activity_and_scores_are_checked_in_the_database():
    assert "uq_activity_feedback_activity" in _names(UniqueConstraint)
    assert {"ck_activity_feedback_rating", "ck_activity_feedback_satisfaction"} <= _names(CheckConstraint)


def _render(fn_name: str) -> str:
    spec = importlib.util.spec_from_file_location("migration_0039", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0039_school_activity_feedback" and module.down_revision == "0038_portfolio"
    buffer = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer})
    with Operations.context(context):
        getattr(module, fn_name)()
    return buffer.getvalue()


def test_migration_creates_only_the_new_table_and_touches_no_existing_row():
    sql = _render("upgrade")
    assert "CREATE TABLE school_activity_feedback" in sql
    for name in ("uq_activity_feedback_activity", "ck_activity_feedback_rating", "ck_activity_feedback_satisfaction"):
        assert name in sql
    assert "ALTER TABLE" not in sql and "UPDATE " not in sql and "DELETE " not in sql


def test_downgrade_drops_only_the_new_table():
    sql = _render("downgrade")
    dropped = {line.split("DROP TABLE ")[1].strip(" ;") for line in sql.splitlines() if "DROP TABLE" in line}
    assert dropped == {"school_activity_feedback"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_enh_018_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'SchoolActivityFeedback'`.

- [ ] **Step 3: Implement the model** (after `SchoolActivityAttendance`)

```python
class SchoolActivityFeedback(Base, TimestampMixin):
    """ENH-018 -- a School Coordinator's feedback on one completed Edusphere activity (`School CRM.md §31`,
    docs/superpowers/specs/2026-09-23-enh-018-school-activity-feedback-design.md §4). One row per activity (D5) and immutable;
    `school_id` is copied from the activity so reads stay scoped without a join. Student participation is NOT stored: it is
    computed from `school_activity_attendance` at read time (D4). `created_at` is the submission time."""

    __tablename__ = "school_activity_feedback"
    __table_args__ = (
        UniqueConstraint("activity_id", name="uq_activity_feedback_activity"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_activity_feedback_rating"),
        CheckConstraint("satisfaction BETWEEN 1 AND 5", name="ck_activity_feedback_satisfaction"),
        Index("ix_school_activity_feedback_created_at", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    activity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_activities.id"))
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"), index=True)
    submitted_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    trainer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rating: Mapped[int] = mapped_column(Integer)
    satisfaction: Mapped[int] = mapped_column(Integer)
    feedback: Mapped[str] = mapped_column(Text)
    suggestions: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Implement the migration** `apps/api/alembic/versions/0039_school_activity_feedback.py`

```python
"""ENH-018 -- school_activity_feedback.

Revision ID: 0039_school_activity_feedback
Revises: 0038_portfolio

docs/superpowers/specs/2026-09-23-enh-018-school-activity-feedback-design.md §4. Create-table only: no existing table is
altered and no existing row is read or written. `downgrade()` drops the table.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0039_school_activity_feedback"
down_revision = "0038_portfolio"
branch_labels = None
depends_on = None

TABLE = "school_activity_feedback"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_activities.id"), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("submitted_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trainer_name", sa.String(200), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("satisfaction", sa.Integer(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("suggestions", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("activity_id", name="uq_activity_feedback_activity"),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_activity_feedback_rating"),
        sa.CheckConstraint("satisfaction BETWEEN 1 AND 5", name="ck_activity_feedback_satisfaction"),
    )
    op.create_index("ix_school_activity_feedback_school_id", TABLE, ["school_id"])
    op.create_index("ix_school_activity_feedback_created_at", TABLE, ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_school_activity_feedback_created_at", table_name=TABLE)
    op.drop_index("ix_school_activity_feedback_school_id", table_name=TABLE)
    op.drop_table(TABLE)
```

- [ ] **Step 5: Run to verify it passes; check single head**

Run: `cd apps/api && python -m pytest tests/test_enh_018_model.py -q && python -m alembic heads`
Expected: 4 passed; exactly one head `0039_school_activity_feedback`.

- [ ] **Step 6: Commit** — `feat(enh-018): school_activity_feedback model and migration`

---

### Task 2: Request/response schemas

**Files:**
- Modify: `apps/api/app/schemas.py` (append at end of file, after the ENH-011/012 blocks so `_required`, `_optional`, `_no_control_characters` exist)
- Test: `apps/api/tests/test_enh_018_schemas.py`

**Interfaces:**
- Produces: `ActivityFeedbackCreate`, `ActivityParticipation(present:int, marked:int)`, `ActivityFeedbackOut`, `SchoolFeedbackActivity`, `SchoolFeedbackPage`, `AdminActivityFeedbackOut`, `AdminFeedbackPage`, `FeedbackStatusFilter = Literal["all","awaiting","submitted"]`, `FEEDBACK_TEXT_MAX = 5000`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from pydantic import ValidationError

from app.schemas import ActivityFeedbackCreate

# ENH-018 spec §5.1: the POST body. No database needed.
VALID = {"rating": 4, "satisfaction": 5, "feedback": "Well run session."}


def test_minimal_valid_body_and_optional_fields_default_to_none():
    body = ActivityFeedbackCreate(**VALID)
    assert (body.rating, body.satisfaction, body.feedback, body.suggestions, body.trainer_name) == (4, 5, "Well run session.", None, None)


@pytest.mark.parametrize("field", ["rating", "satisfaction"])
@pytest.mark.parametrize("value", [0, 6, -1, "5", 4.5, True, None])
def test_scores_are_strict_integers_from_one_to_five(field, value):
    with pytest.raises(ValidationError):
        ActivityFeedbackCreate(**{**VALID, field: value})


@pytest.mark.parametrize("value", [1, 5])
def test_score_bounds_are_inclusive(value):
    assert ActivityFeedbackCreate(**{**VALID, "rating": value}).rating == value


@pytest.mark.parametrize("value", ["", "   ", "\n\t "])
def test_blank_feedback_is_rejected_not_stored(value):
    with pytest.raises(ValidationError):
        ActivityFeedbackCreate(**{**VALID, "feedback": value})


def test_text_is_trimmed_newlines_kept_and_blank_optionals_become_none():
    body = ActivityFeedbackCreate(**{**VALID, "feedback": "  Line one\nLine two  ", "suggestions": "  ", "trainer_name": "  Ms. Rao  "})
    assert body.feedback == "Line one\nLine two"
    assert body.suggestions is None
    assert body.trainer_name == "Ms. Rao"


def test_length_limits():
    ActivityFeedbackCreate(**{**VALID, "feedback": "x" * 5000, "suggestions": "y" * 5000, "trainer_name": "z" * 200})
    for field, size in (("feedback", 5001), ("suggestions", 5001), ("trainer_name", 201)):
        with pytest.raises(ValidationError):
            ActivityFeedbackCreate(**{**VALID, field: "x" * size})


@pytest.mark.parametrize("value", ["bad\x00byte", "bidi‮override"])
def test_nul_and_bidi_overrides_are_rejected(value):
    with pytest.raises(ValidationError):
        ActivityFeedbackCreate(**{**VALID, "feedback": value})


def test_trainer_name_is_single_line():
    with pytest.raises(ValidationError):
        ActivityFeedbackCreate(**{**VALID, "trainer_name": "Ms.\nRao"})


@pytest.mark.parametrize("extra", ["school_id", "submitted_by_user_id", "activity_id", "id"])
def test_server_owned_fields_cannot_be_supplied(extra):
    with pytest.raises(ValidationError):
        ActivityFeedbackCreate(**{**VALID, extra: "00000000-0000-0000-0000-000000000000"})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_enh_018_schemas.py -q`
Expected: FAIL — `ImportError: cannot import name 'ActivityFeedbackCreate'`.

- [ ] **Step 3: Implement** (append to `app/schemas.py`)

```python
# --- ENH-018: school activity feedback (docs/superpowers/specs/2026-09-23-enh-018-school-activity-feedback-design.md §5) ---
# Free text reuses the house `clean_free_text` rule (trim, blank -> None, no NUL/bidi overrides, newlines kept) through
# `_required`/`_optional`; `trainer_name` is single-line, so it also takes `_no_control_characters`.
FEEDBACK_TEXT_MAX = 5000
FeedbackScore = Annotated[int, Field(strict=True, ge=1, le=5)]
FeedbackStatusFilter = Literal["all", "awaiting", "submitted"]


class ActivityFeedbackCreate(BaseModel):
    model_config = {"extra": "forbid"}
    rating: FeedbackScore
    satisfaction: FeedbackScore
    feedback: Annotated[str, AfterValidator(_required(FEEDBACK_TEXT_MAX))]
    suggestions: Annotated[str | None, AfterValidator(_optional(FEEDBACK_TEXT_MAX))] = None
    trainer_name: Annotated[str | None, AfterValidator(_optional(200)), AfterValidator(_no_control_characters)] = None


class ActivityParticipation(BaseModel):
    present: int
    marked: int


class ActivityFeedbackOut(BaseModel):
    id: UUID
    activity_id: UUID
    trainer_name: str | None
    rating: int
    satisfaction: int
    feedback: str
    suggestions: str | None
    submitted_by_name: str
    submitted_at: datetime


class SchoolFeedbackActivity(BaseModel):
    activity_id: UUID
    title: str
    activity_type: str
    scheduled_at: datetime
    participation: ActivityParticipation
    feedback: ActivityFeedbackOut | None


class SchoolFeedbackPage(BaseModel):
    items: list[SchoolFeedbackActivity]
    total: int
    limit: int
    offset: int


class AdminActivityFeedbackOut(ActivityFeedbackOut):
    school_id: UUID
    school_name: str
    activity_title: str
    activity_type: str
    scheduled_at: datetime
    participation: ActivityParticipation


class AdminFeedbackPage(BaseModel):
    items: list[AdminActivityFeedbackOut]
    total: int
    limit: int
    offset: int
```

- [ ] **Step 4: Run to verify it passes** — same command; expected all pass.
- [ ] **Step 5: Commit** — `feat(enh-018): feedback request/response schemas`

---

### Task 3: Coordinator submit endpoint

**Files:**
- Create: `apps/api/app/api/school_feedback.py`
- Modify: `apps/api/app/main.py` (router tuple: add `school_feedback.coordinator_router, school_feedback.admin_router`; import `school_feedback`)
- Create: `apps/api/tests/enh018_helpers.py`
- Test: `apps/api/tests/test_enh_018_submit.py`

**Interfaces:**
- Consumes: `_require_coordinator_user`, `_own_school_id` (`app.api.schools`); Task 1 model; Task 2 schemas; `enh005_helpers.mk_school/login/mk_user`.
- Produces: `coordinator_router`, `admin_router`, `logger`, constants `ACTIVITY_NOT_FOUND`, `NOT_EDUSPHERE_ACTIVITY`, `NOT_YET_HELD`, `ALREADY_SUBMITTED`, `ACTION_SUBMIT = "school.activity_feedback_submit"`; helpers `_feedback_out(feedback, submitter_name) -> ActivityFeedbackOut`, `_participation(db, ids) -> dict[UUID, ActivityParticipation]`, `NO_ATTENDANCE`. Test helper `mk_activity(db, school, coordinator, *, activity_type="career_seminar", days=-1, title=None) -> SchoolActivity`, `FEEDBACK = {...}`.

- [ ] **Step 1: Test helper** `apps/api/tests/enh018_helpers.py`

```python
"""Shared builders for the ENH-018 database tests. Schools come from ENH-005's `mk_school` (coordinator, principal, teacher,
parent, students), so each test owns throwaway rows and runs never collide."""

import uuid
from datetime import UTC, datetime, timedelta

from app.models import SchoolActivity, SchoolActivityAttendance

FEEDBACK = {"rating": 4, "satisfaction": 5, "trainer_name": "Ms. Rao", "feedback": "Students were engaged.", "suggestions": "Longer Q&A."}
URL = "/api/v1/school/activities/{aid}/feedback"


async def mk_activity(db, school, coordinator, *, activity_type: str | None = "career_seminar", minutes: int = -60, title: str | None = None) -> SchoolActivity:
    activity = SchoolActivity(
        school_id=school.id, title=title or f"ENH-018 Activity {uuid.uuid4().hex[:6]}", scheduled_at=datetime.now(UTC) + timedelta(minutes=minutes),
        created_by_user_id=coordinator.id, activity_type=activity_type,
    )
    db.add(activity)
    await db.commit()
    return activity


async def mark(db, activity, coordinator, students_present: list, students_absent: list = ()) -> None:
    for student, present in [*((s, True) for s in students_present), *((s, False) for s in students_absent)]:
        db.add(SchoolActivityAttendance(activity_id=activity.id, school_student_id=student.id, present=present, marked_by_user_id=coordinator.id))
    await db.commit()
```

- [ ] **Step 2: Write the failing tests** `apps/api/tests/test_enh_018_submit.py`

```python
import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from enh005_helpers import login, mk_school, mk_user
from enh018_helpers import FEEDBACK, URL, mk_activity
from httpx import ASGITransport
from sqlalchemy import func, select

from app.main import app
from app.models import AuditLog, SchoolActivityFeedback

# ENH-018 spec §5.1 / AC1-AC4.


async def _rows(db, activity):
    return (await db.scalars(select(SchoolActivityFeedback).where(SchoolActivityFeedback.activity_id == activity.id))).all()


@pytest.mark.asyncio
async def test_coordinator_submits_all_fields_for_a_past_typed_activity(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    await login(client, s["coordinator"].email)
    response = await client.post(URL.format(aid=activity.id), json=FEEDBACK)
    assert response.status_code == 201, response.text
    body = response.json()
    assert {k: body[k] for k in FEEDBACK} == FEEDBACK
    assert body["activity_id"] == str(activity.id) and body["submitted_by_name"] == s["coordinator"].full_name and body["submitted_at"]
    [row] = await _rows(db_session, activity)
    assert row.school_id == s["school"].id and row.submitted_by_user_id == s["coordinator"].id


@pytest.mark.asyncio
async def test_submission_writes_one_audit_row_with_ids_and_scores_only(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    await login(client, s["coordinator"].email)
    await client.post(URL.format(aid=activity.id), json=FEEDBACK)
    [audit] = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.activity_feedback_submit", AuditLog.entity_id == str(activity.id)))).all()
    assert audit.user_id == s["coordinator"].id and audit.entity_type == "school_activity"
    assert audit.metadata_json["rating"] == 4 and audit.metadata_json["satisfaction"] == 5 and audit.metadata_json["school_id"] == str(s["school"].id)
    flat = str(audit.metadata_json)
    for text in (FEEDBACK["feedback"], FEEDBACK["suggestions"], FEEDBACK["trainer_name"]):
        assert text not in flat


@pytest.mark.asyncio
async def test_another_schools_activity_and_an_unknown_id_are_the_same_404(client, db_session):
    a = await mk_school(db_session, label="A")
    b = await mk_school(db_session, label="B")
    theirs = await mk_activity(db_session, b["school"], b["coordinator"])
    await login(client, a["coordinator"].email)
    for aid in (theirs.id, uuid4()):
        response = await client.post(URL.format(aid=aid), json=FEEDBACK)
        assert (response.status_code, response.json()["detail"]) == (404, "Activity not found")
    assert await _rows(db_session, theirs) == []


@pytest.mark.asyncio
async def test_untyped_school_event_is_rejected(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"], activity_type=None)
    await login(client, s["coordinator"].email)
    response = await client.post(URL.format(aid=activity.id), json=FEEDBACK)
    assert (response.status_code, response.json()["detail"]) == (422, "Feedback is only collected for Edusphere activities")


@pytest.mark.asyncio
async def test_eligibility_boundary_one_minute_either_side_of_now(client, db_session):
    s = await mk_school(db_session, label="A")
    past = await mk_activity(db_session, s["school"], s["coordinator"], minutes=-1)
    future = await mk_activity(db_session, s["school"], s["coordinator"], minutes=1)
    await login(client, s["coordinator"].email)
    assert (await client.post(URL.format(aid=past.id), json=FEEDBACK)).status_code == 201
    response = await client.post(URL.format(aid=future.id), json=FEEDBACK)
    assert (response.status_code, response.json()["detail"]) == (422, "Feedback opens once the activity has taken place")


@pytest.mark.asyncio
async def test_second_submission_is_409_and_the_first_is_unchanged(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    await login(client, s["coordinator"].email)
    assert (await client.post(URL.format(aid=activity.id), json=FEEDBACK)).status_code == 201
    response = await client.post(URL.format(aid=activity.id), json={**FEEDBACK, "rating": 1})
    assert (response.status_code, response.json()["detail"]) == (409, "Feedback has already been submitted for this activity")
    [row] = await _rows(db_session, activity)
    assert row.rating == 4


@asynccontextmanager
async def _client_for(email: str):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await login(c, email)
        yield c


@pytest.mark.asyncio
async def test_concurrent_submissions_store_exactly_one_row(db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    async with _client_for(s["coordinator"].email) as one, _client_for(s["coordinator"].email) as two:
        results = await asyncio.gather(*(c.post(URL.format(aid=activity.id), json=FEEDBACK) for c in (one, two, one, two)))
    assert sorted(r.status_code for r in results) == [201, 409, 409, 409]
    assert len(await _rows(db_session, activity)) == 1
    audits = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.activity_feedback_submit", AuditLog.entity_id == str(activity.id)))
    assert audits == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_principal", "school_teacher", "school_parent", "overseas_admin", "super_admin", "career_counselor"])
async def test_only_a_coordinator_may_submit(client, db_session, role):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    other = await mk_user(db_session, role=role, name=f"{role} user", school_id=s["school"].id, assigned_by=s["admin"])
    await db_session.commit()
    await login(client, other.email)
    assert (await client.post(URL.format(aid=activity.id), json=FEEDBACK)).status_code == 403
    assert await _rows(db_session, activity) == []


@pytest.mark.asyncio
async def test_unlinked_coordinator_and_anonymous_caller_are_refused(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    client.cookies.clear()
    assert (await client.post(URL.format(aid=activity.id), json=FEEDBACK)).status_code == 401
    orphan = await mk_user(db_session, role="school_coordinator", name="Unlinked Coordinator", assigned_by=s["admin"])
    await db_session.commit()
    await login(client, orphan.email)
    assert (await client.post(URL.format(aid=activity.id), json=FEEDBACK)).status_code == 403


@pytest.mark.asyncio
async def test_invalid_body_is_422_and_stores_nothing(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    await login(client, s["coordinator"].email)
    for body in ({**FEEDBACK, "rating": 6}, {**FEEDBACK, "feedback": "   "}, {**FEEDBACK, "school_id": str(uuid4())}):
        assert (await client.post(URL.format(aid=activity.id), json=body)).status_code == 422
    assert await _rows(db_session, activity) == []


@pytest.mark.asyncio
async def test_logs_carry_ids_and_never_the_free_text(client, db_session, caplog):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    await login(client, s["coordinator"].email)
    with caplog.at_level(logging.INFO, logger="app.school.feedback"):
        await client.post(URL.format(aid=activity.id), json=FEEDBACK)
        await client.post(URL.format(aid=activity.id), json=FEEDBACK)
    messages = [r.getMessage() for r in caplog.records if r.name == "app.school.feedback"]
    assert "activity_feedback_submitted" in messages and "activity_feedback_duplicate" in messages
    dumped = " ".join(str(getattr(r, "extra_fields", "")) for r in caplog.records)
    assert FEEDBACK["feedback"] not in dumped and str(activity.id) in dumped
```

- [ ] **Step 3: Run to verify they fail**

Run: `cd apps/api && python -m pytest tests/test_enh_018_submit.py -q`
Expected: FAIL — 404 (route not found) on the happy-path tests; 404 ≠ 403/422 in the others.

- [ ] **Step 4: Implement** `apps/api/app/api/school_feedback.py` (submit part; the list routes follow in Tasks 4–5)

```python
"""ENH-018 -- school activity feedback (docs/superpowers/specs/2026-09-23-enh-018-school-activity-feedback-design.md).

A School Coordinator records one feedback per completed Edusphere activity of their own school (`School CRM.md §31`); the
principal reads it; Edusphere admins read every school's. Two routers, like `school_transfers.py`, so `schools.py` and
`admin.py` do not grow. The caller's school always comes from their server-owned profile, never from a request."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import _own_school_id, _require_coordinator_user
from app.core.database import get_db
from app.core.logging import get_logger, request_id_ctx
from app.models import AuditLog, School, SchoolActivity, SchoolActivityAttendance, SchoolActivityFeedback, User
from app.schemas import (
    ActivityFeedbackCreate,
    ActivityFeedbackOut,
    ActivityParticipation,
    AdminActivityFeedbackOut,
    AdminFeedbackPage,
    FeedbackStatusFilter,
    SchoolFeedbackActivity,
    SchoolFeedbackPage,
)

coordinator_router = APIRouter(prefix="/school", tags=["school-feedback"])
admin_router = APIRouter(prefix="/overseas-admin", tags=["school-feedback"])
logger = get_logger("app.school.feedback")

# The `detail` strings are a contract (spec §5.1): a client may match on them.
ACTIVITY_NOT_FOUND = "Activity not found"
NOT_EDUSPHERE_ACTIVITY = "Feedback is only collected for Edusphere activities"
NOT_YET_HELD = "Feedback opens once the activity has taken place"
ALREADY_SUBMITTED = "Feedback has already been submitted for this activity"
UNIQUE_CONSTRAINT = "uq_activity_feedback_activity"
ACTION_SUBMIT = "school.activity_feedback_submit"
NO_ATTENDANCE = ActivityParticipation(present=0, marked=0)


def _feedback_out(feedback: SchoolActivityFeedback, submitter_name: str) -> ActivityFeedbackOut:
    return ActivityFeedbackOut(
        id=feedback.id, activity_id=feedback.activity_id, trainer_name=feedback.trainer_name, rating=feedback.rating, satisfaction=feedback.satisfaction,
        feedback=feedback.feedback, suggestions=feedback.suggestions, submitted_by_name=submitter_name, submitted_at=feedback.created_at,
    )


async def _participation(db: AsyncSession, activity_ids: list[UUID]) -> dict[UUID, ActivityParticipation]:
    """Present-of-marked per activity for one page, in ONE grouped query (D4: computed, never stored)."""
    if not activity_ids:
        return {}
    rows = await db.execute(
        select(SchoolActivityAttendance.activity_id, func.count(), func.count().filter(SchoolActivityAttendance.present.is_(True)))
        .where(SchoolActivityAttendance.activity_id.in_(activity_ids))
        .group_by(SchoolActivityAttendance.activity_id)
    )
    return {activity_id: ActivityParticipation(present=present, marked=marked) for activity_id, marked, present in rows.all()}


def _refuse(status: int, detail: str, reason: str, context: dict) -> HTTPException:
    logger.info("activity_feedback_rejected", extra={"extra_fields": {**context, "reason": reason}})
    return HTTPException(status, detail)


@coordinator_router.post("/activities/{activity_id}/feedback", status_code=201, response_model=ActivityFeedbackOut)
async def submit_activity_feedback(activity_id: UUID, payload: ActivityFeedbackCreate, user: User = Depends(_require_coordinator_user), db: AsyncSession = Depends(get_db)):
    """One feedback per activity, then immutable (D5). The activity is loaded together with the caller's own school, so another
    school's activity is the same 404 as a missing one. No existence pre-check: the unique constraint decides a race, and the
    feedback row and its audit row commit together or not at all."""
    school_id = _own_school_id(user)
    context = {"actor_id": str(user.id), "school_id": str(school_id), "activity_id": str(activity_id)}
    activity = await db.scalar(select(SchoolActivity).where(SchoolActivity.id == activity_id, SchoolActivity.school_id == school_id))
    if activity is None:
        raise _refuse(404, ACTIVITY_NOT_FOUND, "not_found", context)
    if activity.activity_type is None:
        raise _refuse(422, NOT_EDUSPHERE_ACTIVITY, "untyped", context)
    if activity.scheduled_at > datetime.now(UTC):
        raise _refuse(422, NOT_YET_HELD, "not_yet_held", context)
    feedback = SchoolActivityFeedback(activity_id=activity.id, school_id=school_id, submitted_by_user_id=user.id, **payload.model_dump())
    db.add(feedback)
    try:
        await db.flush()
        db.add(
            AuditLog(
                user_id=user.id, action=ACTION_SUBMIT, entity_type="school_activity", entity_id=str(activity.id),
                metadata_json={"school_id": str(school_id), "feedback_id": str(feedback.id), "rating": feedback.rating, "satisfaction": feedback.satisfaction, "request_id": request_id_ctx.get()},
            )
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if UNIQUE_CONSTRAINT not in str(exc.orig):
            raise
        logger.info("activity_feedback_duplicate", extra={"extra_fields": context})
        raise HTTPException(409, ALREADY_SUBMITTED) from exc
    await db.refresh(feedback, ["created_at"])
    logger.info("activity_feedback_submitted", extra={"extra_fields": {**context, "feedback_id": str(feedback.id), "rating": feedback.rating, "satisfaction": feedback.satisfaction}})
    return _feedback_out(feedback, user.full_name)
```

Register in `apps/api/app/main.py`: add `school_feedback` to the `from app.api import ...` line and append `school_feedback.coordinator_router, school_feedback.admin_router` to the router tuple.

- [ ] **Step 5: Run to verify they pass** — same command; all pass. Also rerun Tasks 1–2 tests.
- [ ] **Step 6: Refactor check** — no duplication with `schools.py`; `_refuse` only used here. Rerun.
- [ ] **Step 7: Commit** — `feat(enh-018): coordinator submits activity feedback`

---

### Task 4: School read endpoint (coordinator + principal)

**Files:**
- Modify: `apps/api/app/api/school_feedback.py`
- Test: `apps/api/tests/test_enh_018_reads.py`

**Interfaces:**
- Produces: `GET /api/v1/school/activity-feedback` → `SchoolFeedbackPage`; dependency `_require_school_reader`.

- [ ] **Step 1: Write the failing tests** (`apps/api/tests/test_enh_018_reads.py`, school part)

```python
import pytest
from enh005_helpers import login, mk_school, mk_user
from enh018_helpers import FEEDBACK, URL, mark, mk_activity

# ENH-018 spec §5.2-5.3 / AC5-AC6.
SCHOOL = "/api/v1/school/activity-feedback"
ADMIN = "/api/v1/overseas-admin/school-activity-feedback"


async def _submit(client, s, activity, **over):
    await login(client, s["coordinator"].email)
    response = await client.post(URL.format(aid=activity.id), json={**FEEDBACK, **over})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_coordinator_sees_only_own_eligible_activities_with_participation_and_feedback(client, db_session):
    a = await mk_school(db_session, label="A", students=3)
    b = await mk_school(db_session, label="B")
    done = await mk_activity(db_session, a["school"], a["coordinator"], minutes=-120)
    awaiting = await mk_activity(db_session, a["school"], a["coordinator"], minutes=-60)
    await mk_activity(db_session, a["school"], a["coordinator"], minutes=60)  # future: not listed
    await mk_activity(db_session, a["school"], a["coordinator"], activity_type=None)  # untyped: not listed
    await mk_activity(db_session, b["school"], b["coordinator"])  # other school: not listed
    await mark(db_session, done, a["coordinator"], a["students"][:2], a["students"][2:])
    await _submit(client, a, done)
    body = (await client.get(SCHOOL)).json()
    assert body["total"] == 2 and [i["activity_id"] for i in body["items"]] == [str(awaiting.id), str(done.id)]
    by_id = {i["activity_id"]: i for i in body["items"]}
    assert by_id[str(done.id)]["participation"] == {"present": 2, "marked": 3}
    assert by_id[str(done.id)]["feedback"]["rating"] == 4
    assert by_id[str(awaiting.id)]["participation"] == {"present": 0, "marked": 0} and by_id[str(awaiting.id)]["feedback"] is None


@pytest.mark.asyncio
async def test_status_filter_and_paging(client, db_session):
    s = await mk_school(db_session, label="A")
    acts = [await mk_activity(db_session, s["school"], s["coordinator"], minutes=-10 * (i + 1)) for i in range(3)]
    await _submit(client, s, acts[0])
    awaiting = (await client.get(SCHOOL, params={"status": "awaiting"})).json()
    submitted = (await client.get(SCHOOL, params={"status": "submitted"})).json()
    assert awaiting["total"] == 2 and all(i["feedback"] is None for i in awaiting["items"])
    assert submitted["total"] == 1 and submitted["items"][0]["activity_id"] == str(acts[0].id)
    page = (await client.get(SCHOOL, params={"limit": 1, "offset": 1})).json()
    assert (page["total"], page["limit"], page["offset"], len(page["items"])) == (3, 1, 1, 1)
    assert page["items"][0]["activity_id"] == str(acts[1].id)
    for bad in ({"status": "nope"}, {"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert (await client.get(SCHOOL, params=bad)).status_code == 422


@pytest.mark.asyncio
async def test_principal_reads_own_school_but_cannot_submit(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    await _submit(client, s, activity)
    await login(client, s["principal"].email)
    body = (await client.get(SCHOOL)).json()
    assert body["items"][0]["feedback"]["feedback"] == FEEDBACK["feedback"]
    other = await mk_activity(db_session, s["school"], s["coordinator"])
    assert (await client.post(URL.format(aid=other.id), json=FEEDBACK)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_teacher", "school_parent", "career_counselor", "overseas_admin"])
async def test_other_roles_cannot_read_the_school_list(client, db_session, role):
    s = await mk_school(db_session, label="A")
    other = await mk_user(db_session, role=role, name=f"{role} user", school_id=s["school"].id, assigned_by=s["admin"])
    await db_session.commit()
    await login(client, other.email)
    assert (await client.get(SCHOOL)).status_code == 403


@pytest.mark.asyncio
async def test_unlinked_principal_is_403_not_500(client, db_session):
    s = await mk_school(db_session, label="A")
    orphan = await mk_user(db_session, role="school_principal", name="Unlinked Principal", assigned_by=s["admin"])
    await db_session.commit()
    await login(client, orphan.email)
    assert (await client.get(SCHOOL)).status_code == 403
```

- [ ] **Step 2: Run to verify they fail** — `python -m pytest tests/test_enh_018_reads.py -q` → 404 route not found.

- [ ] **Step 3: Implement** (append to `school_feedback.py`)

```python
async def _require_school_reader(user: User = Depends(get_current_user)) -> User:
    """Coordinator and principal of a school (D8). Resolved as a dependency, so a wrong role is 403 before any 422."""
    if user.role not in {"school_coordinator", "school_principal"}:
        raise HTTPException(403, "School Coordinator or Principal role required")
    _own_school_id(user)  # 403 for an account not linked to a school
    return user


@coordinator_router.get("/activity-feedback", response_model=SchoolFeedbackPage)
async def list_school_activity_feedback(
    status: FeedbackStatusFilter = "all",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(_require_school_reader),
    db: AsyncSession = Depends(get_db),
):
    """The caller's school's feedback-eligible activities (typed, already held -- D1/D7), newest first, each with its computed
    participation and its feedback or null, so "awaiting" is visible."""
    conditions = [SchoolActivity.school_id == _own_school_id(user), SchoolActivity.activity_type.is_not(None), SchoolActivity.scheduled_at <= datetime.now(UTC)]
    if status == "awaiting":
        conditions.append(SchoolActivityFeedback.id.is_(None))
    elif status == "submitted":
        conditions.append(SchoolActivityFeedback.id.is_not(None))
    joined = select(SchoolActivity).outerjoin(SchoolActivityFeedback, SchoolActivityFeedback.activity_id == SchoolActivity.id).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(joined.subquery()))
    rows = (
        await db.execute(
            joined.add_columns(SchoolActivityFeedback, User.full_name)
            .outerjoin(User, User.id == SchoolActivityFeedback.submitted_by_user_id)
            .order_by(SchoolActivity.scheduled_at.desc(), SchoolActivity.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    counts = await _participation(db, [activity.id for activity, _, _ in rows])
    items = [
        SchoolFeedbackActivity(
            activity_id=activity.id, title=activity.title, activity_type=activity.activity_type, scheduled_at=activity.scheduled_at,
            participation=counts.get(activity.id, NO_ATTENDANCE), feedback=_feedback_out(feedback, name) if feedback else None,
        )
        for activity, feedback, name in rows
    ]
    return SchoolFeedbackPage(items=items, total=total or 0, limit=limit, offset=offset)
```

- [ ] **Step 4: Run to verify they pass.**
- [ ] **Step 5: Commit** — `feat(enh-018): coordinator/principal feedback list`

---

### Task 5: Admin read endpoint

**Files:** Modify `apps/api/app/api/school_feedback.py`; Test: append to `apps/api/tests/test_enh_018_reads.py`.

**Interfaces:** Produces `GET /api/v1/overseas-admin/school-activity-feedback` → `AdminFeedbackPage`; dependency `_require_feedback_admin`.

- [ ] **Step 1: Write the failing tests** (append)

```python
@pytest.mark.asyncio
async def test_admin_reads_all_schools_newest_first_and_filters_by_school(client, db_session):
    a = await mk_school(db_session, label="A", students=1)
    b = await mk_school(db_session, label="B")
    act_a = await mk_activity(db_session, a["school"], a["coordinator"])
    act_b = await mk_activity(db_session, b["school"], b["coordinator"])
    await mark(db_session, act_a, a["coordinator"], a["students"])
    first = await _submit(client, a, act_a)
    second = await _submit(client, b, act_b, rating=2)
    await login(client, a["admin"].email)
    body = (await client.get(ADMIN, params={"limit": 100})).json()
    ids = [i["id"] for i in body["items"]]
    assert ids.index(second["id"]) < ids.index(first["id"])
    item = next(i for i in body["items"] if i["id"] == first["id"])
    assert item["school_name"] == a["school"].name and item["activity_title"] == act_a.title and item["activity_type"] == "career_seminar"
    assert item["participation"] == {"present": 1, "marked": 1} and item["submitted_by_name"] == a["coordinator"].full_name
    assert "email" not in str(item)
    only_b = (await client.get(ADMIN, params={"school_id": str(b["school"].id)})).json()
    assert only_b["total"] == 1 and only_b["items"][0]["id"] == second["id"]


@pytest.mark.asyncio
async def test_admin_filter_edge_cases(client, db_session):
    s = await mk_school(db_session, label="A")
    await login(client, s["admin"].email)
    empty = (await client.get(ADMIN, params={"school_id": "00000000-0000-0000-0000-000000000000"})).json()
    assert (empty["total"], empty["items"]) == (0, [])
    assert (await client.get(ADMIN, params={"school_id": "not-a-uuid"})).status_code == 422
    assert (await client.get(ADMIN, params={"limit": 101})).status_code == 422


@pytest.mark.asyncio
async def test_super_admin_reads_and_school_roles_are_refused(client, db_session):
    s = await mk_school(db_session, label="A")
    root = await mk_user(db_session, role="super_admin", name="Super Admin", division="global")
    await db_session.commit()
    await login(client, root.email)
    assert (await client.get(ADMIN)).status_code == 200
    for who in ("coordinator", "principal", "teacher", "parent"):
        await login(client, s[who].email)
        assert (await client.get(ADMIN)).status_code == 403
```

> Note for the implementer: if `login()` (division `"overseas"`) cannot sign a `super_admin` in, check how `test_enh_005_admin_reads.py` logs a super admin in and copy that — do not change `enh005_helpers`.

- [ ] **Step 2: Run to verify they fail** (404).

- [ ] **Step 3: Implement** (append)

```python
async def _require_feedback_admin(user: User = Depends(get_current_user)) -> User:
    """Edusphere management for this feature is the existing cross-school pair (D2); no new role or grant."""
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    return user


@admin_router.get("/school-activity-feedback", response_model=AdminFeedbackPage)
async def admin_list_activity_feedback(
    school_id: UUID | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(_require_feedback_admin),
    db: AsyncSession = Depends(get_db),
):
    """Every school's submitted feedback, newest submission first, optionally for one school. An unknown school is an empty page."""
    conditions = [] if school_id is None else [SchoolActivityFeedback.school_id == school_id]
    total = await db.scalar(select(func.count()).select_from(SchoolActivityFeedback).where(*conditions))
    rows = (
        await db.execute(
            select(SchoolActivityFeedback, SchoolActivity, School.name, User.full_name)
            .join(SchoolActivity, SchoolActivity.id == SchoolActivityFeedback.activity_id)
            .join(School, School.id == SchoolActivityFeedback.school_id)
            .join(User, User.id == SchoolActivityFeedback.submitted_by_user_id)
            .where(*conditions)
            .order_by(SchoolActivityFeedback.created_at.desc(), SchoolActivityFeedback.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    counts = await _participation(db, [activity.id for _, activity, _, _ in rows])
    items = [
        AdminActivityFeedbackOut(
            **_feedback_out(feedback, submitter).model_dump(), school_id=feedback.school_id, school_name=school_name, activity_title=activity.title,
            activity_type=activity.activity_type, scheduled_at=activity.scheduled_at, participation=counts.get(activity.id, NO_ATTENDANCE),
        )
        for feedback, activity, school_name, submitter in rows
    ]
    return AdminFeedbackPage(items=items, total=total or 0, limit=limit, offset=offset)
```

- [ ] **Step 4: Run to verify they pass**, then run the backend regression set:

Run: `cd apps/api && python -m pytest tests/test_enh_018_model.py tests/test_enh_018_schemas.py tests/test_enh_018_submit.py tests/test_enh_018_reads.py tests/test_sch_001_school_portal_access.py tests/test_sch_007_parent_portal.py tests/test_sch_008_student_timeline.py tests/test_sch_011_entitlements.py tests/test_sch_reports.py -q` and `python -m ruff check app tests` (if configured in `pyproject.toml`).
Expected: all pass; lint clean.

- [ ] **Step 5: Commit** — `feat(enh-018): admin cross-school feedback list`

---

### Task 6: Frontend types and helpers

**Files:**
- Create: `apps/web/lib/activityFeedback.ts`
- Modify: `apps/web/app/controls.css` (append feedback styles)
- Test: `apps/web/tests/lib/activityFeedback.test.ts`

**Interfaces:** Produces types `Participation`, `ActivityFeedback`, `FeedbackActivity`, `AdminActivityFeedback`, `FeedbackFilter`; `FEEDBACK_FILTERS`, `SCORE_LABELS`, `activityTypeLabel(type)`, `participationText(p)`, `scoreText(n)`, `isFeedbackEligible(activity, now?)`.

- [ ] **Step 1: Failing test**

```ts
import { describe, expect, it } from "vitest";

import { activityTypeLabel, isFeedbackEligible, participationText, scoreText } from "@/lib/activityFeedback";

describe("activityFeedback helpers", () => {
  it("words participation, including attendance never marked", () => {
    expect(participationText({ present: 42, marked: 50 })).toBe("42 of 50 present");
    expect(participationText({ present: 0, marked: 0 })).toBe("Not marked");
  });
  it("labels a score with words, not a number alone", () => {
    expect(scoreText(1)).toBe("1 – Poor");
    expect(scoreText(5)).toBe("5 – Excellent");
  });
  it("labels activity types and falls back to the raw value", () => {
    expect(activityTypeLabel("campus_visit")).toBe("Monthly campus visit");
    expect(activityTypeLabel("something_new")).toBe("something_new");
  });
  it("is eligible only when typed and already held", () => {
    const now = Date.parse("2026-09-23T10:00:00Z");
    expect(isFeedbackEligible({ activity_type: "career_seminar", scheduled_at: "2026-09-23T09:59:00Z" }, now)).toBe(true);
    expect(isFeedbackEligible({ activity_type: "career_seminar", scheduled_at: "2026-09-23T10:01:00Z" }, now)).toBe(false);
    expect(isFeedbackEligible({ activity_type: null, scheduled_at: "2026-09-01T10:00:00Z" }, now)).toBe(false);
    expect(isFeedbackEligible({ scheduled_at: "2026-09-01T10:00:00Z" }, now)).toBe(false);
  });
});
```

- [ ] **Step 2: Run** `cd apps/web && npx vitest run tests/lib/activityFeedback.test.ts` → FAIL (module not found).

- [ ] **Step 3: Implement** `apps/web/lib/activityFeedback.ts`

```ts
// ENH-018 -- shapes of the activity-feedback API (docs/superpowers/specs/2026-09-23-enh-018-school-activity-feedback-design.md §5)
// and how its values are worded. A score or status is always shown as text, never as colour or a bare number.

export type Participation = { present: number; marked: number };

export type ActivityFeedback = {
  id: string;
  activity_id: string;
  trainer_name: string | null;
  rating: number;
  satisfaction: number;
  feedback: string;
  suggestions: string | null;
  submitted_by_name: string;
  submitted_at: string;
};

/** A row of the coordinator/principal list: an eligible activity and its feedback, or null while awaiting. */
export type FeedbackActivity = { activity_id: string; title: string; activity_type: string; scheduled_at: string; participation: Participation; feedback: ActivityFeedback | null };

export type AdminActivityFeedback = ActivityFeedback & { school_id: string; school_name: string; activity_title: string; activity_type: string; scheduled_at: string; participation: Participation };

export const FEEDBACK_FILTERS = [["all", "All"], ["awaiting", "Awaiting feedback"], ["submitted", "Submitted"]] as const;
export type FeedbackFilter = (typeof FEEDBACK_FILTERS)[number][0];

export const SCORE_LABELS = ["Poor", "Fair", "Good", "Very good", "Excellent"] as const;

// Same wording as the Activities scheduling form's category options (SchoolActivitiesPanel).
const ACTIVITY_TYPES: Record<string, string> = {
  career_seminar: "Career seminar",
  career_awareness_session: "Student career awareness session",
  parent_orientation: "Parent orientation",
  campus_visit: "Monthly campus visit",
};

export const activityTypeLabel = (type: string) => ACTIVITY_TYPES[type] ?? type;
export const participationText = (p: Participation) => (p.marked === 0 ? "Not marked" : `${p.present} of ${p.marked} present`);
export const scoreText = (n: number) => `${n} – ${SCORE_LABELS[n - 1] ?? ""}`.trim();

/** Mirrors the API's rule (spec D1/D7) so the Activities list only offers the link where the POST can succeed. */
export function isFeedbackEligible(activity: { activity_type?: string | null; scheduled_at: string }, now = Date.now()): boolean {
  return !!activity.activity_type && Date.parse(activity.scheduled_at) <= now;
}
```

Append to `apps/web/app/controls.css`:

```css
/* ENH-018 activity feedback: score radios, read-only details, and long free text that must wrap rather than widen the page. */
.score-field{border:0;margin:0;padding:0;min-width:0}
.score-field legend{font-weight:800;font-size:13px;margin-bottom:7px;padding:0}
.score-options{display:flex;flex-wrap:wrap;gap:4px 16px}
.score-options label{display:flex;align-items:center;gap:6px;min-height:44px;font-weight:600}
.feedback-details{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 16px;margin:8px 0 0}
.feedback-details dt{font-weight:800;font-size:13px}
.feedback-details dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
.feedback-row{flex-direction:column;align-items:stretch!important}
@media(max-width:640px){.feedback-details{grid-template-columns:minmax(0,1fr)}.feedback-details dd{margin-bottom:6px}}
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** — `feat(enh-018): feedback types, wording helpers and styles`

---

### Task 7: Read-only details and the feedback form

**Files:**
- Create: `apps/web/components/ActivityFeedbackDetails.tsx`, `apps/web/components/ActivityFeedbackForm.tsx`
- Test: `apps/web/tests/components/ActivityFeedbackForm.test.tsx`

**Interfaces:**
- Consumes: Task 6 helpers; `detailMessage`, `isRequestBody`, `NOT_COMPLETED` (`@/lib/apiErrors`); `formatDate` (`@/lib/formatDate`).
- Produces: `<ActivityFeedbackDetails feedback={ActivityFeedback} />`; `<ActivityFeedbackForm activity={FeedbackActivity} onSubmitted={(f: ActivityFeedback) => void} onDuplicate={() => void} onCancel={() => void} />`.

- [ ] **Step 1: Failing test**

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ActivityFeedbackForm from "@/components/ActivityFeedbackForm";
import type { FeedbackActivity } from "@/lib/activityFeedback";

const ACTIVITY: FeedbackActivity = { activity_id: "act-1", title: "Career Seminar", activity_type: "career_seminar", scheduled_at: "2026-09-20T09:00:00Z", participation: { present: 42, marked: 50 }, feedback: null };
const SAVED = { id: "fb-1", activity_id: "act-1", trainer_name: "Ms. Rao", rating: 4, satisfaction: 5, feedback: "Great", suggestions: null, submitted_by_name: "Coordinator", submitted_at: "2026-09-21T09:00:00Z" };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function setup(response: () => Promise<Response>) {
  const fetchMock = vi.fn(response);
  vi.stubGlobal("fetch", fetchMock);
  const handlers = { onSubmitted: vi.fn(), onDuplicate: vi.fn(), onCancel: vi.fn() };
  render(<ActivityFeedbackForm activity={ACTIVITY} {...handlers} />);
  return { fetchMock, ...handlers };
}
function fill() {
  fireEvent.click(screen.getByLabelText("4 – Very good", { selector: "input[name=rating]" }));
  fireEvent.click(screen.getByLabelText("5 – Excellent", { selector: "input[name=satisfaction]" }));
  fireEvent.change(screen.getByLabelText("Trainer / Counsellor (optional)"), { target: { value: "Ms. Rao" } });
  fireEvent.change(screen.getByLabelText("Feedback"), { target: { value: "Great" } });
}
const submit = () => fireEvent.submit(screen.getByRole("button", { name: "Submit feedback" }).closest("form")!);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ActivityFeedbackForm", () => {
  it("moves focus to its heading and labels every §31 field, with scores as grouped radios", () => {
    setup(() => Promise.resolve(json(SAVED, 201)));
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: /Feedback: Career Seminar/ }));
    expect(screen.getByRole("group", { name: "Overall rating" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "School satisfaction" })).toBeTruthy();
    expect(screen.getAllByRole("radio")).toHaveLength(10);
    expect(screen.getByText(/42 of 50 present/)).toBeTruthy();
    expect(screen.getByLabelText("Feedback")).toHaveAttribute("maxlength", "5000");
    expect(screen.getByLabelText("Feedback")).toHaveAccessibleDescription(/personal details/);
  });

  it("posts the typed values and reports the stored feedback", async () => {
    const { fetchMock, onSubmitted } = setup(() => Promise.resolve(json(SAVED, 201)));
    fill();
    submit();
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith(SAVED));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/school/activities/act-1/feedback");
    expect(JSON.parse(String(init.body))).toEqual({ rating: 4, satisfaction: 5, trainer_name: "Ms. Rao", feedback: "Great", suggestions: null });
  });

  it("disables submit while saving", async () => {
    let release!: (r: Response) => void;
    setup(() => new Promise<Response>((resolve) => (release = resolve)));
    fill();
    submit();
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    release(json(SAVED, 201));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Saving…" })).toBeNull());
  });

  it("keeps the entry and focuses a readable alert when the server refuses", async () => {
    setup(() => Promise.resolve(json({ detail: [{ msg: "Value error, must not be blank" }] }, 422)));
    fill();
    submit();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Must not be blank");
    expect(document.activeElement).toBe(alert);
    expect(screen.getByLabelText("Feedback")).toHaveValue("Great");
  });

  it("hands a 409 (already submitted, e.g. a retry after a lost response) to the parent instead of an error", async () => {
    const { onDuplicate } = setup(() => Promise.resolve(json({ detail: "Feedback has already been submitted for this activity" }, 409)));
    fill();
    submit();
    await waitFor(() => expect(onDuplicate).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says the entry is kept when the network drops, and Cancel calls back", async () => {
    const { onCancel } = setup(() => Promise.reject(new TypeError("Failed to fetch")));
    fill();
    submit();
    expect((await screen.findByRole("alert")).textContent).toMatch(/your entry is kept/);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run** `npx vitest run tests/components/ActivityFeedbackForm.test.tsx` → FAIL (module not found).

- [ ] **Step 3: Implement** `apps/web/components/ActivityFeedbackDetails.tsx`

```tsx
import { type ActivityFeedback, scoreText } from "@/lib/activityFeedback";
import { formatDate } from "@/lib/formatDate";

// ENH-018: one submitted feedback, read-only. Shared by the school list and the admin list. Free text renders as React text
// (escaped) and wraps inside its column, so a long unbroken word cannot widen the page.
export default function ActivityFeedbackDetails({ feedback }: { feedback: ActivityFeedback }) {
  return (
    <dl className="feedback-details">
      <dt>Overall rating</dt>
      <dd>{scoreText(feedback.rating)}</dd>
      <dt>School satisfaction</dt>
      <dd>{scoreText(feedback.satisfaction)}</dd>
      <dt>Trainer / Counsellor</dt>
      <dd>{feedback.trainer_name ?? "Not recorded"}</dd>
      <dt>Feedback</dt>
      <dd>{feedback.feedback}</dd>
      <dt>Suggestions</dt>
      <dd>{feedback.suggestions ?? "None"}</dd>
      <dt>Submitted</dt>
      <dd>{`${feedback.submitted_by_name}, ${formatDate(feedback.submitted_at, true)}`}</dd>
    </dl>
  );
}
```

`apps/web/components/ActivityFeedbackForm.tsx`

```tsx
"use client";

import { FormEvent, useEffect, useId, useRef, useState } from "react";

import { type ActivityFeedback, type FeedbackActivity, participationText, SCORE_LABELS } from "@/lib/activityFeedback";
import { detailMessage, isRequestBody, NOT_COMPLETED } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";

type Props = { activity: FeedbackActivity; onSubmitted: (feedback: ActivityFeedback) => void; onDuplicate: () => void; onCancel: () => void };

// ENH-018: the coordinator's feedback on one completed activity (spec §7.2). Native radios in a fieldset give arrow-key
// navigation and a spoken group name; `required` on the radios and the feedback textarea gives native validation. On a
// refusal the entry is kept and the alert takes focus; a 409 goes to the parent, which shows the feedback already stored.
function ScoreField({ name, legend }: { name: string; legend: string }) {
  return (
    <fieldset className="score-field">
      <legend>{legend}</legend>
      <div className="score-options">
        {SCORE_LABELS.map((label, i) => (
          <label key={label}>
            <input type="radio" name={name} value={i + 1} required />
            {`${i + 1} – ${label}`}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function ActivityFeedbackForm({ activity, onSubmitted, onDuplicate, onCancel }: Props) {
  const id = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => headingRef.current?.focus(), []);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const text = (key: string) => String(form.get(key) ?? "").trim() || null;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/school/activities/${activity.activity_id}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating: Number(form.get("rating")), satisfaction: Number(form.get("satisfaction")), trainer_name: text("trainer_name"), feedback: String(form.get("feedback") ?? ""), suggestions: text("suggestions") }),
      });
      const data = await response.json().catch(() => null);
      if (response.status === 409) return onDuplicate();
      if (!response.ok || !isRequestBody(data)) return setError(detailMessage((data as { detail?: unknown } | null)?.detail, "Could not save the feedback."));
      onSubmitted(data as ActivityFeedback);
    } catch {
      setError(NOT_COMPLETED);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="action-card">
      <form className="form" onSubmit={submit} aria-labelledby={`${id}-heading`}>
        <div>
          <h3 id={`${id}-heading`} ref={headingRef} tabIndex={-1}>{`Feedback: ${activity.title}`}</h3>
          <p className="muted" style={{ margin: 0 }}>{`${formatDate(activity.scheduled_at, true)} · ${participationText(activity.participation)}`}</p>
        </div>
        <ScoreField name="rating" legend="Overall rating" />
        <ScoreField name="satisfaction" legend="School satisfaction" />
        <div className="field">
          <label htmlFor={`${id}-trainer`}>Trainer / Counsellor (optional)</label>
          <input id={`${id}-trainer`} name="trainer_name" maxLength={200} autoComplete="off" />
        </div>
        <div className="field">
          <label htmlFor={`${id}-feedback`}>Feedback</label>
          <textarea id={`${id}-feedback`} name="feedback" required maxLength={5000} aria-describedby={`${id}-privacy`} />
          <p id={`${id}-privacy`} className="muted" style={{ margin: 0, fontSize: 13 }}>Describe the session. Please don't include students' personal details.</p>
        </div>
        <div className="field">
          <label htmlFor={`${id}-suggestions`}>Suggestions (optional)</label>
          <textarea id={`${id}-suggestions`} name="suggestions" maxLength={5000} />
        </div>
        {error && <div ref={errorRef} tabIndex={-1} className="form-error" role="alert">{error}</div>}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Submit feedback"}</button>
          <button type="button" className="btn secondary" onClick={onCancel} disabled={busy}>Cancel</button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** — `feat(enh-018): feedback form and read-only details`

---

### Task 8: Coordinator/principal Feedback page

**Files:**
- Create: `apps/web/components/SchoolActivityFeedbackPanel.tsx`
- Create: `apps/web/app/school/coordinator/feedback/page.tsx`, `apps/web/app/school/coordinator/feedback/loading.tsx`
- Create: `apps/web/app/school/principal/feedback/page.tsx`, `apps/web/app/school/principal/feedback/loading.tsx`
- Modify: `apps/web/lib/navigation.ts:37-38` (add `"feedback"` after `"activities"` for coordinator, after `"reports"` for principal)
- Test: `apps/web/tests/components/SchoolActivityFeedbackPanel.test.tsx`

**Interfaces:**
- Consumes: Tasks 6–7; `isPage`, `Page` (`@/lib/apiErrors`).
- Produces: `<SchoolActivityFeedbackPanel initial={Page<FeedbackActivity>} canSubmit={boolean} />`.

- [ ] **Step 1: Failing test**

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolActivityFeedbackPanel from "@/components/SchoolActivityFeedbackPanel";
import type { FeedbackActivity } from "@/lib/activityFeedback";
import { SCHOOL_NAV } from "@/lib/navigation";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const SAVED = { id: "fb-1", activity_id: "a1", trainer_name: null, rating: 3, satisfaction: 4, feedback: "Good", suggestions: null, submitted_by_name: "Coordinator", submitted_at: "2026-09-21T09:00:00Z" };
const row = (id: string, feedback: typeof SAVED | null = null): FeedbackActivity => ({ activity_id: id, title: `Seminar ${id}`, activity_type: "career_seminar", scheduled_at: "2026-09-20T09:00:00Z", participation: { present: 0, marked: 0 }, feedback });
const page = (items: FeedbackActivity[], total = items.length) => ({ items, total, limit: 25, offset: 0 });
const item = (title: string) => screen.getAllByRole("listitem").find((li) => li.textContent?.includes(title))!;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SchoolActivityFeedbackPanel", () => {
  it("adds Feedback to the coordinator and principal navigation", () => {
    expect(SCHOOL_NAV.coordinator.map((n) => n.href)).toContain("/school/coordinator/feedback");
    expect(SCHOOL_NAV.principal.map((n) => n.href)).toContain("/school/principal/feedback");
  });

  it("shows the empty state with a way to the Activities page", () => {
    render(<SchoolActivityFeedbackPanel initial={page([])} canSubmit />);
    expect(screen.getByRole("heading", { name: "No completed Edusphere activities yet." })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to Activities" })).toHaveAttribute("href", "/school/coordinator/activities");
  });

  it("words status and participation in text, and shows stored feedback in a disclosure", () => {
    render(<SchoolActivityFeedbackPanel initial={page([row("a1", SAVED), row("a2")])} canSubmit />);
    expect(within(item("Seminar a1")).getByText("Submitted")).toBeTruthy();
    expect(within(item("Seminar a2")).getByText("Awaiting feedback")).toBeTruthy();
    expect(within(item("Seminar a2")).getByText(/Not marked/)).toBeTruthy();
    fireEvent.click(within(item("Seminar a1")).getByText("View feedback"));
    expect(within(item("Seminar a1")).getByText("3 – Good")).toBeTruthy();
  });

  it("principal view is read-only", () => {
    render(<SchoolActivityFeedbackPanel initial={page([row("a2")])} canSubmit={false} />);
    expect(screen.queryByRole("button", { name: /Give feedback/ })).toBeNull();
    expect(screen.queryByRole("link", { name: "Go to Activities" })).toBeNull();
  });

  it("submitting updates the row in place, announces it and returns focus to the status message", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ ...SAVED, activity_id: "a2" }, 201))));
    render(<SchoolActivityFeedbackPanel initial={page([row("a2")])} canSubmit />);
    fireEvent.click(screen.getByRole("button", { name: "Give feedback for Seminar a2" }));
    fireEvent.click(screen.getByLabelText("3 – Good", { selector: "input[name=rating]" }));
    fireEvent.click(screen.getByLabelText("4 – Very good", { selector: "input[name=satisfaction]" }));
    fireEvent.change(screen.getByLabelText("Feedback"), { target: { value: "Good" } });
    fireEvent.submit(screen.getByRole("button", { name: "Submit feedback" }).closest("form")!);
    const status = await screen.findByText("Feedback saved for Seminar a2.");
    expect(within(item("Seminar a2")).getByText("Submitted")).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(status.closest("[role=status]")));
  });

  it("cancel closes the form and puts focus back on its button", () => {
    render(<SchoolActivityFeedbackPanel initial={page([row("a2")])} canSubmit />);
    const trigger = screen.getByRole("button", { name: "Give feedback for Seminar a2" });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Submit feedback" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Give feedback for Seminar a2" }));
  });

  it("on 409 it reloads the list so the stored feedback is shown", async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(url.includes("/feedback?") || url.includes("activity-feedback") ? json(page([row("a2", SAVED)])) : json({ detail: "Feedback has already been submitted for this activity" }, 409)));
    vi.stubGlobal("fetch", fetchMock);
    render(<SchoolActivityFeedbackPanel initial={page([row("a2")])} canSubmit />);
    fireEvent.click(screen.getByRole("button", { name: "Give feedback for Seminar a2" }));
    fireEvent.click(screen.getByLabelText("3 – Good", { selector: "input[name=rating]" }));
    fireEvent.click(screen.getByLabelText("4 – Very good", { selector: "input[name=satisfaction]" }));
    fireEvent.change(screen.getByLabelText("Feedback"), { target: { value: "Again" } });
    fireEvent.submit(screen.getByRole("button", { name: "Submit feedback" }).closest("form")!);
    expect(await screen.findByText(/already been submitted/)).toBeTruthy();
    await waitFor(() => expect(within(item("Seminar a2")).getByText("Submitted")).toBeTruthy());
  });

  it("filter change fetches that status; a failed fetch shows a retryable alert", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({}, 500)).mockResolvedValueOnce(json(page([])));
    vi.stubGlobal("fetch", fetchMock);
    render(<SchoolActivityFeedbackPanel initial={page([row("a1", SAVED)])} canSubmit />);
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "awaiting" } });
    expect((await screen.findByRole("alert")).textContent).toMatch(/Could not load/);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/school/activity-feedback?status=awaiting&limit=25&offset=0");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Nothing awaiting feedback." })).toBeTruthy();
  });

  it("loads more and says how many are shown", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ items: [row("a2")], total: 2, limit: 25, offset: 1 }))));
    render(<SchoolActivityFeedbackPanel initial={page([row("a1", SAVED)], 2)} canSubmit />);
    expect(screen.getByText("Showing 1 of 2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Showing 2 of 2")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });
});
```

- [ ] **Step 2: Run** → FAIL (module not found; nav assertion fails).

- [ ] **Step 3: Implement** `apps/web/components/SchoolActivityFeedbackPanel.tsx`

```tsx
"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import ActivityFeedbackDetails from "@/components/ActivityFeedbackDetails";
import ActivityFeedbackForm from "@/components/ActivityFeedbackForm";
import { type ActivityFeedback, activityTypeLabel, FEEDBACK_FILTERS, type FeedbackActivity, type FeedbackFilter, participationText } from "@/lib/activityFeedback";
import { isPage, type Page } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";

// ENH-018 (spec §7.1): a school's completed Edusphere activities and their feedback. The first page is server-rendered; the
// filter and "Load more" fetch on the client (the ENH-005 admin-queue pattern). The coordinator opens the form inline under a
// row; the principal (canSubmit=false) only reads. Status is always a text badge, never colour alone.
const LIMIT = 25;
const EMPTY: Record<FeedbackFilter, string> = { all: "No completed Edusphere activities yet.", awaiting: "Nothing awaiting feedback.", submitted: "No feedback submitted yet." };

export default function SchoolActivityFeedbackPanel({ initial, canSubmit }: { initial: Page<FeedbackActivity>; canSubmit: boolean }) {
  const [filter, setFilter] = useState<FeedbackFilter>("all");
  const [items, setItems] = useState(initial.items);
  const [total, setTotal] = useState(initial.total);
  const [loading, setLoading] = useState<"first" | "more" | null>(null);
  const [failed, setFailed] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const messageRef = useRef<HTMLDivElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const triggers = useRef(new Map<string, HTMLButtonElement>());

  const load = useCallback(async (next: FeedbackFilter, offset: number, mode: "first" | "more") => {
    controller.current?.abort();
    const abort = (controller.current = new AbortController());
    setLoading(mode);
    try {
      const response = await fetch(`/api/v1/school/activity-feedback?status=${next}&limit=${LIMIT}&offset=${offset}`, { signal: abort.signal });
      const data = await response.json().catch(() => null);
      if (!response.ok || !isPage<FeedbackActivity>(data)) return setFailed(true);
      setFailed(false);
      setItems((prev) => (mode === "more" ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
    } catch (error) {
      if ((error as Error).name !== "AbortError") setFailed(true);
    } finally {
      if (!abort.signal.aborted) setLoading(null);
    }
  }, []);

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (failed) alertRef.current?.focus();
  }, [failed]);

  function announce(text: string) {
    setMessage(text);
    requestAnimationFrame(() => messageRef.current?.focus());
  }
  function changeFilter(next: FeedbackFilter) {
    setFilter(next);
    setMessage(null);
    setOpenId(null);
    void load(next, 0, "first");
  }
  function onSubmitted(activity: FeedbackActivity, feedback: ActivityFeedback) {
    setOpenId(null);
    if (filter === "awaiting") {
      setItems((prev) => prev.filter((row) => row.activity_id !== activity.activity_id));
      setTotal((t) => Math.max(0, t - 1));
    } else {
      setItems((prev) => prev.map((row) => (row.activity_id === activity.activity_id ? { ...row, feedback } : row)));
    }
    announce(`Feedback saved for ${activity.title}.`);
  }
  function onDuplicate() {
    setOpenId(null);
    announce("Feedback had already been submitted for this activity; showing what was saved.");
    void load(filter, 0, "first");
  }
  function onCancel(activityId: string) {
    setOpenId(null);
    requestAnimationFrame(() => triggers.current.get(activityId)?.focus());
  }

  return (
    <div className="portal-content">
      <div className="card">
        <div className="portal-title">
          <div>
            <h2>Activity feedback</h2>
            <p className="muted">{canSubmit ? "Rate each completed Edusphere activity once. Edusphere uses it to improve the next session." : "Feedback your coordinator recorded after each Edusphere activity."}</p>
          </div>
        </div>
        <div className="table-controls">
          <div>
            <label htmlFor="feedback-filter">Show</label>
            <select id="feedback-filter" className="select" value={filter} disabled={loading !== null} onChange={(e) => changeFilter(e.target.value as FeedbackFilter)}>
              {FEEDBACK_FILTERS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
            </select>
          </div>
        </div>
        <div ref={messageRef} tabIndex={-1} role="status" aria-live="polite">{message && <div className="form-message">{message}</div>}</div>
        {failed && (
          <div ref={alertRef} tabIndex={-1} className="form-error" role="alert">
            <p style={{ margin: 0 }}>Could not load activity feedback.</p>
            <button type="button" className="btn small secondary" style={{ marginTop: 8 }} onClick={() => void load(filter, 0, "first")}>Try again</button>
          </div>
        )}
        {loading === "first" ? (
          <div aria-busy="true">
            <p className="muted">Loading activity feedback…</p>
            <div className="skeleton-line" aria-hidden="true" />
          </div>
        ) : items.length === 0 && !failed ? (
          <div className="empty">
            <h3>{EMPTY[filter]}</h3>
            {filter === "all" && <p>Feedback opens after a career seminar, career awareness session, parent orientation or campus visit has taken place.</p>}
            {filter === "all" && canSubmit && <Link className="btn secondary small" href="/school/coordinator/activities">Go to Activities</Link>}
          </div>
        ) : items.length > 0 ? (
          <>
            <p className="muted" aria-live="polite">{`Showing ${items.length} of ${total}`}</p>
            <ul className="link-list" role="list" aria-label="Completed Edusphere activities">
              {items.map((row) => (
                <li key={row.activity_id} className="feedback-row">
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 16px", justifyContent: "space-between", alignItems: "center" }}>
                    <div className="who">
                      <strong>{row.title}</strong>
                      <span>{`${activityTypeLabel(row.activity_type)} · ${formatDate(row.scheduled_at, true)} · ${participationText(row.participation)}`}</span>
                    </div>
                    <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                      <span className="badge">{row.feedback ? "Submitted" : "Awaiting feedback"}</span>
                      {canSubmit && !row.feedback && openId !== row.activity_id && (
                        <button
                          type="button"
                          className="btn small"
                          aria-label={`Give feedback for ${row.title}`}
                          ref={(el) => void (el ? triggers.current.set(row.activity_id, el) : triggers.current.delete(row.activity_id))}
                          onClick={() => {
                            setMessage(null);
                            setOpenId(row.activity_id);
                          }}
                        >
                          Give feedback
                        </button>
                      )}
                    </div>
                  </div>
                  {row.feedback && (
                    <details>
                      <summary>View feedback</summary>
                      <ActivityFeedbackDetails feedback={row.feedback} />
                    </details>
                  )}
                  {openId === row.activity_id && (
                    <ActivityFeedbackForm activity={row} onSubmitted={(feedback) => onSubmitted(row, feedback)} onDuplicate={onDuplicate} onCancel={() => onCancel(row.activity_id)} />
                  )}
                </li>
              ))}
            </ul>
            {items.length < total && (
              <button type="button" className="btn secondary small" disabled={loading !== null} onClick={() => void load(filter, items.length, "more")}>{loading === "more" ? "Loading…" : "Load more"}</button>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
```

`apps/web/app/school/coordinator/feedback/page.tsx`

```tsx
import PortalShell from "@/components/PortalShell";
import SchoolActivityFeedbackPanel from "@/components/SchoolActivityFeedbackPanel";
import { accessUnavailable } from "@/components/AccessUnavailable";
import type { FeedbackActivity } from "@/lib/activityFeedback";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-018: the coordinator records feedback on each completed Edusphere activity of their own school.
export default async function SchoolCoordinatorFeedbackPage() {
  let user: User;
  let initial: Page<FeedbackActivity>;
  try {
    [user, initial] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Page<FeedbackActivity>>("/api/v1/school/activity-feedback?status=all&limit=25&offset=0")]);
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolActivityFeedbackPanel initial={initial} canSubmit />
    </PortalShell>
  );
}
```

`apps/web/app/school/principal/feedback/page.tsx` — identical except: component name `SchoolPrincipalFeedbackPage`, comment "ENH-018 (D8): the principal reads their school's activity feedback; read-only.", `nav={SCHOOL_NAV.principal}`, `roleLabel="Principal"`, `canSubmit={false}`.

`apps/web/app/school/coordinator/feedback/loading.tsx`

```tsx
// ENH-018: shown while the server reads the first page, so navigation is never a blank screen (ENH-011 pattern).
export default function Loading() {
  return (
    <div className="portal-content" aria-busy="true" aria-label="Loading activity feedback">
      <div className="card">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
      </div>
    </div>
  );
}
```

`apps/web/app/school/principal/feedback/loading.tsx`

```tsx
export { default } from "../../coordinator/feedback/loading";
```

`apps/web/lib/navigation.ts` lines 37–38:

```ts
  coordinator: ["dashboard", "students", "promotion", "transfers", "activities", "feedback", "team", "reports", "entitlements", "notifications"].map(...unchanged),
  principal: ["dashboard", "reports", "feedback", "entitlements"].map(...unchanged),
```

- [ ] **Step 4: Run** → PASS; also `npx vitest run tests/components/PortalShell.test.tsx tests/lib/skills.test.ts`.
- [ ] **Step 5: Commit** — `feat(enh-018): coordinator and principal feedback pages`

---

### Task 9: Admin cross-school Feedback page

**Files:**
- Create: `apps/web/components/AdminActivityFeedbackPanel.tsx`, `apps/web/app/overseas/admin/activity-feedback/page.tsx`
- Modify: `apps/web/lib/navigation.ts:74` (add `"activity-feedback"` after `"school-transfers"`)
- Test: `apps/web/tests/components/AdminActivityFeedbackPanel.test.tsx`

**Interfaces:** Consumes Tasks 6–7, `isPage`. Produces `<AdminActivityFeedbackPanel />` (no props; loads after first paint).

- [ ] **Step 1: Failing test**

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminActivityFeedbackPanel from "@/components/AdminActivityFeedbackPanel";
import type { AdminActivityFeedback } from "@/lib/activityFeedback";
import { PORTAL_NAV } from "@/lib/navigation";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const SCHOOLS = [{ id: "s1", name: "Sunrise School" }, { id: "s2", name: "Lakeview School" }];
const fb = (n: string, school = SCHOOLS[0]): AdminActivityFeedback => ({
  id: `fb-${n}`, activity_id: `a-${n}`, trainer_name: "Ms. Rao", rating: 4, satisfaction: 5, feedback: `Feedback ${n}`, suggestions: null, submitted_by_name: "Fatima", submitted_at: "2026-09-21T09:00:00Z",
  school_id: school.id, school_name: school.name, activity_title: `Seminar ${n}`, activity_type: "campus_visit", scheduled_at: "2026-09-20T09:00:00Z", participation: { present: 40, marked: 45 },
});
const page = (items: AdminActivityFeedback[], total = items.length, offset = 0) => ({ items, total, limit: 25, offset });

function stub(handler: (url: string) => Response) {
  const fn = vi.fn((url: string) => Promise.resolve(handler(String(url))));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminActivityFeedbackPanel", () => {
  it("is in the overseas admin navigation", () => {
    expect(PORTAL_NAV["overseas/admin"].map((n) => n.href)).toContain("/overseas/admin/activity-feedback");
  });

  it("shows a busy skeleton, then one card per feedback with school, activity, participation and all fields", async () => {
    stub((url) => (url.includes("/schools") ? json(SCHOOLS) : json(page([fb("1")]))));
    render(<AdminActivityFeedbackPanel />);
    expect(document.querySelector("[aria-busy=true]")).toBeTruthy();
    const card = (await screen.findByText("Seminar 1")).closest("li")!;
    for (const text of [/Sunrise School/, /Monthly campus visit/, /40 of 45 present/, "4 – Very good", "5 – Excellent", "Ms. Rao", "Feedback 1"]) {
      expect(within(card).getByText(text)).toBeTruthy();
    }
  });

  it("filters by school and pages with Load more", async () => {
    const fetchMock = stub((url) => (url.includes("/schools") ? json(SCHOOLS) : url.includes("offset=25") ? json(page([fb("2")], 26, 25)) : json(page([fb("1")], 26))));
    render(<AdminActivityFeedbackPanel />);
    await screen.findByText("Seminar 1");
    expect(screen.getByText("Showing 1 of 26")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Seminar 2")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("School"), { target: { value: "s2" } });
    expect(fetchMock.mock.calls.map((c) => c[0])).toContain("/api/v1/overseas-admin/school-activity-feedback?school_id=s2&limit=25&offset=0");
  });

  it("empty state, and a failed load offers Try again", async () => {
    let fail = true;
    stub((url) => (url.includes("/schools") ? json(SCHOOLS) : fail ? json({}, 500) : json(page([]))));
    render(<AdminActivityFeedbackPanel />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/Could not load/);
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "No feedback submitted yet." })).toBeTruthy();
  });

  it("still lists feedback when the school list cannot load (filter just shows All schools)", async () => {
    stub((url) => (url.includes("/schools") ? json({}, 500) : json(page([fb("1")]))));
    render(<AdminActivityFeedbackPanel />);
    expect(await screen.findByText("Seminar 1")).toBeTruthy();
    expect(within(screen.getByLabelText("School")).getAllByRole("option")).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** `apps/web/components/AdminActivityFeedbackPanel.tsx`

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import ActivityFeedbackDetails from "@/components/ActivityFeedbackDetails";
import { type AdminActivityFeedback, activityTypeLabel, participationText } from "@/lib/activityFeedback";
import { isPage } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";

// ENH-018 (spec §7.3): every school's activity feedback for Edusphere management, newest first. Loaded after first paint like
// the ENH-005 queue. Each feedback is a card (a <dl>) rather than a wide table, so long free text reflows on a phone. The school
// filter reuses GET /overseas-admin/schools; if that fails the list still works, unfiltered.
const LIMIT = 25;
type SchoolOption = { id: string; name: string };

export default function AdminActivityFeedbackPanel() {
  const [schools, setSchools] = useState<SchoolOption[]>([]);
  const [schoolId, setSchoolId] = useState("");
  const [items, setItems] = useState<AdminActivityFeedback[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState<"first" | "more" | null>("first");
  const [failed, setFailed] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const alertRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async (school: string, offset: number, mode: "first" | "more") => {
    controller.current?.abort();
    const abort = (controller.current = new AbortController());
    setLoading(mode);
    if (mode === "first") setItems(null);
    try {
      const filter = school ? `school_id=${encodeURIComponent(school)}&` : "";
      const response = await fetch(`/api/v1/overseas-admin/school-activity-feedback?${filter}limit=${LIMIT}&offset=${offset}`, { signal: abort.signal });
      const data = await response.json().catch(() => null);
      if (!response.ok || !isPage<AdminActivityFeedback>(data)) return setFailed(true);
      setFailed(false);
      setItems((prev) => (mode === "more" && prev ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
    } catch (error) {
      if ((error as Error).name !== "AbortError") setFailed(true);
    } finally {
      if (!abort.signal.aborted) setLoading(null);
    }
  }, []);

  useEffect(() => {
    void load("", 0, "first");
    fetch("/api/v1/overseas-admin/schools")
      .then((r) => (r.ok ? r.json() : []))
      .then((rows: unknown) => setSchools(Array.isArray(rows) ? rows.map((s: SchoolOption) => ({ id: s.id, name: s.name })) : []))
      .catch(() => setSchools([]));
    return () => controller.current?.abort();
  }, [load]);
  useEffect(() => {
    if (failed) alertRef.current?.focus();
  }, [failed]);

  function changeSchool(next: string) {
    setSchoolId(next);
    void load(next, 0, "first");
  }

  return (
    <div className="action-card wide">
      <div>
        <h3>{`School activity feedback${total > 0 ? ` (${total})` : ""}`}</h3>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>What School Coordinators said after each Edusphere activity.</p>
      </div>
      <div className="table-controls">
        <div>
          <label htmlFor="feedback-school">School</label>
          <select id="feedback-school" className="select" value={schoolId} disabled={loading !== null} onChange={(e) => changeSchool(e.target.value)}>
            <option value="">All schools</option>
            {schools.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
      </div>
      {failed && (
        <div ref={alertRef} tabIndex={-1} className="form-error" role="alert">
          <p style={{ margin: 0 }}>Could not load activity feedback.</p>
          <button type="button" className="btn small secondary" style={{ marginTop: 8 }} onClick={() => void load(schoolId, 0, "first")}>Try again</button>
        </div>
      )}
      {items === null && !failed ? (
        <div aria-busy="true">
          <p className="muted" style={{ margin: "0 0 8px" }}>Loading activity feedback…</p>
          <div className="skeleton-line" aria-hidden="true" />
        </div>
      ) : items !== null && items.length === 0 && !failed ? (
        <div className="empty"><h3>No feedback submitted yet.</h3></div>
      ) : items !== null && items.length > 0 ? (
        <>
          <p className="muted" aria-live="polite">{`Showing ${items.length} of ${total}`}</p>
          <ul className="link-list" role="list" aria-label="Activity feedback">
            {items.map((f) => (
              <li key={f.id} className="feedback-row">
                <div className="who">
                  <strong>{f.activity_title}</strong>
                  <span>{`${f.school_name} · ${activityTypeLabel(f.activity_type)} · ${formatDate(f.scheduled_at, true)} · ${participationText(f.participation)}`}</span>
                </div>
                <ActivityFeedbackDetails feedback={f} />
              </li>
            ))}
          </ul>
          {items.length < total && (
            <button type="button" className="btn secondary small" disabled={loading !== null} onClick={() => void load(schoolId, items.length, "more")}>{loading === "more" ? "Loading…" : "Load more"}</button>
          )}
        </>
      ) : null}
    </div>
  );
}
```

`apps/web/app/overseas/admin/activity-feedback/page.tsx`

```tsx
import AdminActivityFeedbackPanel from "@/components/AdminActivityFeedbackPanel";
import PortalShell from "@/components/PortalShell";
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import { serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-018 (D2): Edusphere management reads every school's activity feedback. A static route, so it wins over `[section]`;
// admin-only like the API, so nobody else is shown a screen that can only fail (ENH-005's school-transfers page pattern).
const ADMIN_ROLES = ["overseas_admin", "super_admin"];

export default async function AdminActivityFeedbackPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e);
  }
  if (!ADMIN_ROLES.includes(user.role)) return accessDenied(user, "Overseas Administrator role required");
  return (
    <PortalShell nav={PORTAL_NAV["overseas/admin"]} roleLabel="Overseas Administrator" userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Workspace</div>
            <h2>Activity Feedback</h2>
            <p className="muted">Feedback School Coordinators recorded after each Edusphere activity, across every partner school.</p>
          </div>
        </div>
        <AdminActivityFeedbackPanel />
      </div>
    </PortalShell>
  );
}
```

`apps/web/lib/navigation.ts:74` — insert `"activity-feedback"` after `"school-transfers"` in the `"overseas/admin"` array.

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** — `feat(enh-018): admin cross-school feedback page`

---

### Task 10: "Give feedback" link on the Activities list

**Files:**
- Modify: `apps/web/components/SchoolActivitiesPanel.tsx` (type + one table cell), `apps/web/app/school/coordinator/activities/page.tsx` (type only)
- Test: `apps/web/tests/components/SchoolActivitiesPanel.test.tsx` (new)

- [ ] **Step 1: Failing test**

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolActivitiesPanel from "@/components/SchoolActivitiesPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
afterEach(cleanup);

const past = "2026-01-10T09:00:00Z";
const future = "2099-01-10T09:00:00Z";

describe("SchoolActivitiesPanel (ENH-018 link)", () => {
  it("offers Give feedback only on typed activities that have taken place, and keeps Mark attendance on every row", () => {
    render(
      <SchoolActivitiesPanel
        students={[]}
        activities={[
          { id: "1", title: "Career Seminar", scheduled_at: past, activity_type: "career_seminar" },
          { id: "2", title: "Sports Day", scheduled_at: past, activity_type: null },
          { id: "3", title: "Campus Visit", scheduled_at: future, activity_type: "campus_visit" },
        ]}
      />,
    );
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByRole("link", { name: "Give feedback for Career Seminar" })).toHaveAttribute("href", "/school/coordinator/feedback");
    expect(within(rows[1]).queryByRole("link")).toBeNull();
    expect(within(rows[2]).queryByRole("link")).toBeNull();
    for (const row of rows) expect(within(row).getByRole("button", { name: "Mark attendance" })).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run** → FAIL (no link).

- [ ] **Step 3: Implement** — in `SchoolActivitiesPanel.tsx`:
  - `type Activity = { id: string; title: string; scheduled_at: string; activity_type?: string | null };`
  - `import Link from "next/link";` and `import { isFeedbackEligible } from "@/lib/activityFeedback";`
  - Actions cell becomes:

```tsx
<td>
  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
    <button className="btn ghost small" onClick={() => startMarking(a.id)}>Mark attendance</button>
    {isFeedbackEligible(a) && <Link className="btn secondary small" href="/school/coordinator/feedback" aria-label={`Give feedback for ${a.title}`}>Give feedback</Link>}
  </div>
</td>
```

  - In `activities/page.tsx`: `type Activity = { id: string; title: string; scheduled_at: string; activity_type?: string | null };`

- [ ] **Step 4: Run** this test plus the whole vitest suite (`npx vitest run`) → PASS.
- [ ] **Step 5: Commit** — `feat(enh-018): link completed Edusphere activities to feedback`

---

### Task 11: Playwright end-to-end

**Files:** Create `apps/web/tests/e2e/enh-018-school-activity-feedback.spec.ts`.

Requires the running stack (`docker compose up`, `python -m app.seed`, `alembic upgrade head`) — the user brings it up.

- [ ] **Step 1: Write the spec**

```ts
import { expect, test, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-018 -- coordinator submits feedback on a completed Edusphere activity (keyboard only), the principal reads it, the admin reads
// it across schools, and a second submission is refused. Throwaway school per run. Requires the seeded stack (see enh-005 spec header).
const ADMIN_EMAIL = "overseasadmin@edusphere.local";
const ADMIN_PASSWORD = "Demo@123";

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(landing);
}

test("coordinator gives feedback by keyboard; principal and admin read it; a duplicate is refused (ENH-018)", async ({ page }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  const coordinatorEmail = `enh018-e2e-coord-${unique}@example.local`;
  const schoolName = `E2E ENH-018 School ${unique}`;
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", schoolName);
  await page.fill("#school-coordinator-name", "E2E ENH-018 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "**/school/coordinator/dashboard");
  const title = `E2E Career Seminar ${unique}`;
  const created = await page.request.post("/api/v1/school/activities", { data: { title, scheduled_at: new Date(Date.now() - 3_600_000).toISOString(), activity_type: "career_seminar" } });
  expect(created.status()).toBe(201);
  const activity = await created.json();

  // Invite a principal through the existing team flow's API and activate them.
  const invite = await page.request.post("/api/v1/school/invites", { data: { role: "school_principal", email: `enh018-e2e-principal-${unique}@example.local`, full_name: "E2E ENH-018 Principal" } });
  expect(invite.status()).toBe(201);
  const principalToken = (await invite.json()).development_invite_token;

  await page.goto("/school/coordinator/activities");
  await page.getByRole("link", { name: `Give feedback for ${title}` }).click();
  await page.waitForURL("**/school/coordinator/feedback");

  await page.setViewportSize({ width: 320, height: 800 });
  await page.getByRole("button", { name: `Give feedback for ${title}` }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: `Feedback: ${title}` })).toBeFocused();
  await page.keyboard.press("Tab"); // first rating radio
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight"); // 4 – Very good
  await page.keyboard.press("Tab"); // satisfaction group
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight"); // 5 – Excellent
  await page.keyboard.press("Tab");
  await page.keyboard.type("Ms. Rao");
  await page.keyboard.press("Tab");
  const longWord = "Excellent".repeat(40);
  await page.keyboard.type(`Students were engaged. ${longWord}`);
  await page.keyboard.press("Tab");
  await page.keyboard.type("More time for questions.");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
  await expect(page.getByText(`Feedback saved for ${title}.`)).toBeVisible();
  await page.getByText("View feedback").first().click();
  await expect(page.getByText("4 – Very good")).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), { message: "long feedback text overflows at 320px" }).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });

  const duplicate = await page.request.post(`/api/v1/school/activities/${activity.id}/feedback`, { data: { rating: 1, satisfaction: 1, feedback: "again" } });
  expect(duplicate.status()).toBe(409);

  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${principalToken}/accept`);
  await page.fill("#invite-password", "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/principal/dashboard");
  await page.goto("/school/principal/feedback");
  await expect(page.getByText(title)).toBeVisible();
  await expect(page.getByRole("button", { name: /Give feedback/ })).toHaveCount(0);

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  await page.goto("/overseas/admin/activity-feedback");
  await page.getByLabel("School").selectOption({ label: schoolName });
  const card = page.getByRole("listitem").filter({ hasText: title });
  await expect(card.getByText("Ms. Rao")).toBeVisible();
  await expect(card.getByText("5 – Excellent")).toBeVisible();

  expect(pageErrors).toEqual([]);
});
```

> Implementer: confirm the principal-invite endpoint path/body and the accept-page selectors against `tests/e2e/sch-team-management.spec.ts` and `sch-003-school-onboarding.spec.ts` before running; adjust only this spec, never product code.

- [ ] **Step 2: Run** `cd apps/web && npx playwright test tests/e2e/enh-018-school-activity-feedback.spec.ts` against the running stack → PASS. If it fails, diagnose (superpowers:systematic-debugging); do not weaken assertions.
- [ ] **Step 3: Commit** — `test(enh-018): end-to-end feedback journey`

---

### Task 12: Documentation and full verification

**Files:**
- Modify: `docs/architecture/API_CONTRACT.md` (School addendum: the three endpoints, bodies, status codes, `detail` strings)
- Modify: `docs/quality/RTM.md` (ENH-018 row: §31 → spec → endpoints → tests)
- Modify: `docs/delivery/ENHANCEMENT_BACKLOG.md` (§31 row status "Built — ENH-018"; ENH-018 entry: record corrections D1–D9, keep original text)

- [ ] **Step 1: Write the docs** (factual; cite spec decisions D1–D9; mark nothing `EXPLICIT_APPROVAL` beyond the in-session confirmations).
- [ ] **Step 2: Full verification**
  - `cd apps/api && python -m pytest -q` (full backend suite; per the team cadence, at least the ENH-018 + SCH regression set listed in Task 5)
  - `cd apps/api && python -m ruff check .` (if configured)
  - `cd apps/web && npx vitest run && npx tsc --noEmit && npm run lint && npm run build`
- [ ] **Step 3: Commit** — `docs(enh-018): API contract, RTM and backlog status`

Completion is **not** claimed here: browser validation and the independent Codex review follow.
