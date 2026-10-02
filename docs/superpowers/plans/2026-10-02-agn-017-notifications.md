# AGN-017 — Agent Notifications + Deadline Reminders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agency Masters/Staff get exactly one in-app + email notice per relevant event and a de-duplicated daily reminder for
deadlines and overdue tasks, with a Notifications page and unread badge.

**Architecture:** One service module (`app/services/agent_notifications.py`) owns recipients, notice text and the daily job;
routes call it before their existing commit. Reminders are made idempotent by a partial unique `notifications.dedupe_key`
(`ON CONFLICT DO NOTHING`). Email reuses the ENH-014 queue (`queue_deliveries`, email channel only). The frontend adds a
`notifications` agent section through the existing `PortalPage` pattern and an optional `NavItem.badge`.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Pydantic 2, Alembic, PostgreSQL 16, Celery beat; Next.js App Router + TypeScript;
pytest; vitest; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-02-agn-017-notifications-design.md` (`DEC-SCOPE-055`).

## Global Constraints

- Channels: in-app + email only — `channels=["email"]`; never WhatsApp/SMS (D19, N5).
- Recipient: active assigned staff member, else active Masters of the record's org; never the actor; inactive org → none (N2).
- Bodies: no names, emails, phones, passport data or user-typed free text; document type only if in `schemas.AgentDocumentType`,
  else "A document"; university name stripped of control characters and capped at 120 (§8).
- `action_url` ∈ {`/overseas/agent/students`, `/overseas/agent/documents`, `/overseas/agent/applications`, `/overseas/agent/tasks`}.
- Reminders: windows {3, 1, 0} days, IST date (`Asia/Kolkata`); overdue tasks = one digest per recipient per IST day (N4).
- Dedupe keys: `agn017:deadline:{app_id}:{kind}:{date}:{days_left}:{user_id}`, `agn017:overdue:{today}:{user_id}`.
- Beat: `crontab(hour=2, minute=30)` UTC (08:00 IST), entry `agn017-daily-reminders`.
- Migration `0061_agent_notifications` after `0060_agent_app_enrollment`; additive only.
- Existing contracts unchanged: `GET /workflows/notifications`, `PATCH /workflows/notifications/{id}/read`. New
  `GET /workflows/notifications/unread-count` → `{"unread": int}`.
- No new dependencies. Services must not import `app.api.*`.
- Lite tests only (owner runs full suites separately): `tests/test_agn_017_*.py` plus the named regression files per task; web
  typecheck + lint + the touched vitest files.
- Logs: ids and counts only (`agn017_*` events).

## Test command

```
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn017 --profile ci run --rm \
  -v "$PWD/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <files>"
```

Web: `cd apps/web && npx vitest run <files> && npx tsc --noEmit && npx next lint` (or the repo's `npm run lint`).

## Review Focus

1. A staff member who changes the status of their **own** student — expect no notice to anyone (actor removed; Masters are not a
   fallback when an active assignee exists).
2. An application with an agency record whose assignee was **deactivated** — expect the Masters to get the notice instead.
3. A counselor `PATCH` that changes only `next_action` on an agency application — expect no agency notice (status unchanged).
4. The reminder job run twice in one IST day, and once at 18:29 vs 18:31 UTC on the day before a deadline — expect no duplicate and
   the IST date (18:31 UTC is already the next IST day).
5. A task title / document note containing an email address and `\r\n` — expect neither in any notice title or body.

Each line has a test in the owning task below.

---

### Task 1: Migration + model — `dedupe_key` and partial indexes

**Files:**
- Create: `apps/api/alembic/versions/0061_agent_notifications.py`
- Modify: `apps/api/app/models.py` (`Notification`, `OverseasApplication.__table_args__`, `AgentTask.__table_args__`)
- Modify: `apps/api/tests/test_agn_016_migration.py`, `apps/api/tests/test_agn_013_migration.py` (single-head expectation only, if
  they pin `0060`)
- Test: `apps/api/tests/test_agn_017_migration.py`

**Interfaces:**
- Produces: `Notification.dedupe_key: Mapped[str | None]` (String(200)); index names `ux_notifications_dedupe_key`,
  `ix_overseas_applications_agent_application_deadline`, `ix_overseas_applications_agent_offer_deadline`, `ix_agent_tasks_open_due`.

- [ ] **Step 1: Write the failing test**

```python
"""AGN-017 AC10 -- 0061 is the single head; the column and partial indexes exist."""
import pytest
from sqlalchemy import text
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_0061_is_the_single_head():
    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    assert heads == ["0061_agent_notifications"]


@pytest.mark.asyncio
async def test_dedupe_column_and_partial_indexes_exist(db_session):
    column = await db_session.scalar(text("SELECT is_nullable FROM information_schema.columns WHERE table_name='notifications' AND column_name='dedupe_key'"))
    assert column == "YES"
    rows = dict((await db_session.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE indexname IN ('ux_notifications_dedupe_key','ix_overseas_applications_agent_application_deadline','ix_overseas_applications_agent_offer_deadline','ix_agent_tasks_open_due')"))).all())
    assert set(rows) == {"ux_notifications_dedupe_key", "ix_overseas_applications_agent_application_deadline", "ix_overseas_applications_agent_offer_deadline", "ix_agent_tasks_open_due"}
    assert "UNIQUE" in rows["ux_notifications_dedupe_key"] and "dedupe_key IS NOT NULL" in rows["ux_notifications_dedupe_key"]
    assert "status" in rows["ix_agent_tasks_open_due"] and "open" in rows["ix_agent_tasks_open_due"]
```

- [ ] **Step 2: Run — expect FAIL** (head is `0060_agent_app_enrollment`; column missing).
- [ ] **Step 3: Implement**

`models.py` — `Notification`:
```python
    # AGN-017 (DEC-SCOPE-055 N6): set only on scheduled reminders; the partial unique index makes a second run a no-op.
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    __table_args__ = (Index("ux_notifications_dedupe_key", "dedupe_key", unique=True, postgresql_where=text("dedupe_key IS NOT NULL")),)
```
`OverseasApplication.__table_args__` gains (or is created with):
```python
        Index("ix_overseas_applications_agent_application_deadline", "application_deadline", postgresql_where=text("agent_student_id IS NOT NULL")),
        Index("ix_overseas_applications_agent_offer_deadline", "offer_deadline", postgresql_where=text("agent_student_id IS NOT NULL")),
```
`AgentTask.__table_args__` gains `Index("ix_agent_tasks_open_due", "due_at", postgresql_where=text("status = 'open'"))`.

Migration (0060's guarded idiom; downgrade drops exactly what it added — keys are derived metadata, not user data):
```python
"""AGN-017 -- notifications.dedupe_key (+ partial unique index) and partial indexes for the daily reminder queries.

Revision ID: 0061_agent_notifications
Revises: 0060_agent_app_enrollment
"""
import sqlalchemy as sa
from alembic import op

revision = "0061_agent_notifications"
down_revision = "0060_agent_app_enrollment"
branch_labels = None
depends_on = None

INDEXES = (
    ("ux_notifications_dedupe_key", "notifications", ["dedupe_key"], True, "dedupe_key IS NOT NULL"),
    ("ix_overseas_applications_agent_application_deadline", "overseas_applications", ["application_deadline"], False, "agent_student_id IS NOT NULL"),
    ("ix_overseas_applications_agent_offer_deadline", "overseas_applications", ["offer_deadline"], False, "agent_student_id IS NOT NULL"),
    ("ix_agent_tasks_open_due", "agent_tasks", ["due_at"], False, "status = 'open'"),
)


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    if inspector is None or "dedupe_key" not in {c["name"] for c in inspector.get_columns("notifications")}:
        op.add_column("notifications", sa.Column("dedupe_key", sa.String(200), nullable=True))
    for name, table, cols, unique, where in INDEXES:
        if inspector is None or name not in {i["name"] for i in inspector.get_indexes(table)}:
            op.create_index(name, table, cols, unique=unique, postgresql_where=sa.text(where))


def downgrade() -> None:
    for name, table, *_ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_column("notifications", "dedupe_key")
```
- [ ] **Step 4: Run** `test_agn_017_migration.py test_agn_016_migration.py test_agn_013_migration.py` — PASS (update any test that
  asserts `0060` is the head to `0061`, with a comment).
- [ ] **Step 5: Commit** `feat(agn-017): 0061 dedupe_key and reminder indexes`.

---

### Task 2: Service core — recipients, text helpers, `notify`

**Files:**
- Create: `apps/api/app/services/agent_notifications.py`
- Create: `apps/api/tests/agn017_helpers.py`
- Test: `apps/api/tests/test_agn_017_recipients.py`

**Interfaces:**
- Produces:
  - `INDIA: ZoneInfo`, `CHANNELS = ["email"]`, URL constants `STUDENTS_URL`, `DOCUMENTS_URL`, `APPLICATIONS_URL`, `TASKS_URL`
  - `document_label(value: str | None) -> str`, `clean_text(value: str | None, limit: int = 120) -> str`
  - `async recipients(db, record: AgentStudent, actor: User | None) -> list[User]`
  - `async notify(db, users: list[User], title: str, body: str, action_url: str) -> int` (no commit)
- Helpers: `tests/agn017_helpers.py` → `async notices(db, user) -> list[Notification]` (newest first), `async deactivate(db, member)`.

- [ ] **Step 1: Write failing tests** — assignee gets it; actor removed; deactivated assignee → Masters; unassigned → Masters;
  suspended org → none; other org never; `document_label("Passport") == "Passport"`, `document_label("my scan of rahul") ==
  "A document"`; `clean_text("Uni\r\nX" + "y"*200)` has no `\r`/`\n` and length ≤ 120; `notify` queues only email deliveries
  (`NotificationDelivery.channel == "email"` even with WhatsApp opted in via `enh014_helpers.set_prefs`).
- [ ] **Step 2: Run — FAIL** (module missing).
- [ ] **Step 3: Implement**

```python
"""AGN-017 (DEC-SCOPE-055): agency notifications and daily reminders. Recipients are the student's active assigned staff member,
else the organisation's active Masters, never the actor (N2). In-app + email only (D19, N5). Bodies carry no names and no
user-typed text (spec §8). Nothing here commits except the daily job; event notices ride the caller's transaction."""

import logging
from typing import get_args
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrg, AgentOrgMember, AgentStudent, Notification, User
from app.notifications.dispatch import queue_deliveries
from app.schemas import AgentDocumentType

logger = logging.getLogger(__name__)

INDIA = ZoneInfo("Asia/Kolkata")
CHANNELS = ["email"]
STUDENTS_URL, DOCUMENTS_URL, APPLICATIONS_URL, TASKS_URL = (f"/overseas/agent/{s}" for s in ("students", "documents", "applications", "tasks"))
KNOWN_DOCUMENT_TYPES = frozenset(get_args(AgentDocumentType))


def document_label(value: str | None) -> str:
    return value if value in KNOWN_DOCUMENT_TYPES else "A document"


def clean_text(value: str | None, limit: int = 120) -> str:
    """Stored text bound for an email: control characters (CR/LF included) become spaces, runs collapse, then a hard cap."""
    return " ".join("".join(ch if ch.isprintable() else " " for ch in value or "").split())[:limit]


async def _org(db: AsyncSession, record: AgentStudent) -> AgentOrg | None:
    return await db.scalar(select(AgentOrg).join(AgentOrgMember, AgentOrgMember.org_id == AgentOrg.id).where(AgentOrgMember.user_id == record.agent_id))


async def _active_masters(db: AsyncSession, org_id) -> list[User]:
    rows = await db.scalars(
        select(User).join(AgentOrgMember, AgentOrgMember.user_id == User.id)
        .where(AgentOrgMember.org_id == org_id, AgentOrgMember.role == "master", AgentOrgMember.status == "active", User.active.is_(True))
        .order_by(AgentOrgMember.seq)
    )
    return list(rows)


async def active_member_user(db: AsyncSession, member_id, org_id) -> User | None:
    row = (await db.execute(select(AgentOrgMember, User).join(User, User.id == AgentOrgMember.user_id).where(AgentOrgMember.id == member_id))).first()
    if row is None:
        return None
    member, user = row
    return user if member.org_id == org_id and member.status == "active" and user.active else None


async def recipients(db: AsyncSession, record: AgentStudent, actor: User | None) -> list[User]:
    org = await _org(db, record)
    if org is None or org.status != "active":
        return []
    assignee = await active_member_user(db, record.assigned_member_id, org.id) if record.assigned_member_id else None
    users = [assignee] if assignee else await _active_masters(db, org.id)
    return [u for u in users if actor is None or u.id != actor.id]


async def notify(db: AsyncSession, users: list[User], title: str, body: str, action_url: str) -> int:
    for user in users:
        item = Notification(user_id=user.id, title=title, body=body, read=False, action_url=action_url)
        db.add(item)
        await queue_deliveries(db, item, user, channels=CHANNELS)
    return len(users)
```
- [ ] **Step 4: Run** `test_agn_017_recipients.py` — PASS.
- [ ] **Step 5: Commit** `feat(agn-017): recipient rule and email-only notify`.

---

### Task 3: Event — student assigned / reassigned

**Files:**
- Modify: `apps/api/app/services/agent_notifications.py` (add `student_assigned`)
- Modify: `apps/api/app/api/agent_students.py` (`assign_student`, before `await db.commit()`)
- Test: `apps/api/tests/test_agn_017_events.py`

**Interfaces:**
- Produces: `async student_assigned(db, record: AgentStudent, member_id, actor: User) -> int`

- [ ] **Step 1: Failing tests** — Master assigns record to `other_staff` → `other_staff` has exactly one notice, title "Student
  assigned to you", `action_url == "/overseas/agent/students"`, body mentions "2 open tasks" when two open tasks exist (one done task
  not counted); re-assigning the same member → no new notice; unassign (`member_id: null`) → no notice; previous assignee gets
  nothing; one email delivery queued.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement**

Service:
```python
async def student_assigned(db: AsyncSession, record: AgentStudent, member_id, actor: User) -> int:
    """N1/N9: only the new assignee hears about it, with the number of open tasks that moved with the student (AGN-016 T1)."""
    org = await _org(db, record)
    user = await active_member_user(db, member_id, org.id) if org is not None and org.status == "active" and member_id else None
    if user is None or user.id == actor.id:
        return 0
    open_tasks = await db.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.agent_student_id == record.id, AgentTask.status == "open"))
    moved = f" {open_tasks} open task{'s' if open_tasks != 1 else ''} moved with them." if open_tasks else ""
    return await notify(db, [user], "Student assigned to you", f"A student is now assigned to you.{moved}", STUDENTS_URL)
```
Route (inside `if changed:` before commit):
```python
        if new_id:
            await notices.student_assigned(db, row, new_id, user)  # AGN-017 (DEC-SCOPE-055 N1): in this transaction
```
(import `from app.services import agent_notifications as notices`.)
- [ ] **Step 4: Run** `test_agn_017_events.py -k assign` + `test_agn_004_assign*.py` (or the AGN-004 assign file) — PASS.
- [ ] **Step 5: Commit** `feat(agn-017): notify the new assignee`.

---

### Task 4: Events — document requested; document rejected / changes required

**Files:**
- Modify: service (`document_requested`, `document_needs_attention`)
- Modify: `apps/api/app/api/agent_documents.py` (`create_request`, after `svc.add_event`)
- Modify: `apps/api/app/api/workflows.py` (`_agent_document_review` and the counselor/admin branch of `verify_document`, after
  `add_event`, before `_audit`)
- Test: `test_agn_017_events.py`

**Interfaces:**
- Produces: `async document_requested(db, record, document_type: str, actor) -> int`;
  `async document_needs_attention(db, document: StudentDocument, actor) -> int` (no-op unless status ∈ {`rejected`,`changes_required`}).

- [ ] **Step 1: Failing tests** — Master requests "Passport" for staff's record → staff gets "Document requested" / "Passport was
  requested for one of your students."; staff requests for own record → nobody; a `document_label`/`note` with an email and CRLF
  never appears in any notice; Master rejects a pending agency document with a reason → staff gets "Document needs attention" /
  "{type}: rejected."; `verified` → no agency notice; counselor rejects a document whose application has an agency record → staff
  notified, the student's existing "Document reviewed" notice still created; a free-text uploaded type ("rahul's scan") renders
  "A document"; a document with no agency record → no agency notice.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement**

```python
OUTCOME_TEXT = {"rejected": "rejected", "changes_required": "changes required"}


async def document_requested(db, record, document_type, actor) -> int:
    return await notify(db, await recipients(db, record, actor), "Document requested", f"{document_label(document_type)} was requested for one of your students.", DOCUMENTS_URL)


async def _document_record(db, document) -> AgentStudent | None:
    record_id = document.agent_student_id
    if record_id is None and document.application_id:
        record_id = await db.scalar(select(OverseasApplication.agent_student_id).where(OverseasApplication.id == document.application_id))
    return await db.get(AgentStudent, record_id) if record_id else None


async def document_needs_attention(db, document, actor) -> int:
    outcome = OUTCOME_TEXT.get(document.verification_status)
    record = await _document_record(db, document) if outcome else None
    if record is None:
        return 0
    return await notify(db, await recipients(db, record, actor), "Document needs attention", f"{document_label(document.document_type)}: {outcome}.", DOCUMENTS_URL)
```
Hooks: `await notices.document_requested(db, record, payload.document_type, user)` in `create_request`;
`await notices.document_needs_attention(db, item, user)` in both review branches (workflows imports the service module; the
service never imports `app.api`).
- [ ] **Step 4: Run** `test_agn_017_events.py -k document` + `test_agn_009_*.py` + `test_agn_003_verify.py` — PASS.
- [ ] **Step 5: Commit** `feat(agn-017): document request and rejection notices`.

---

### Task 5: Events — status changed (CRM, PATCH, advance, enrollment) without double notice

**Files:**
- Modify: service (`has_commission`, `status_changed`)
- Modify: `apps/api/app/api/agent_applications.py` (`change_status`, `save_enrollment`)
- Modify: `apps/api/app/api/workflows.py` (`update_overseas_application`, `advance_overseas_application`)
- Test: `test_agn_017_events.py`

**Interfaces:**
- Produces: `async has_commission(db, application_id) -> bool`;
  `async status_changed(db, application, old_status: str, actor: User, *, had_commission: bool) -> int`.

- [ ] **Step 1: Failing tests** — Master advances staff's application `enquiry → eligibility_evaluation` → staff gets "Application
  status changed" / "{university}: Enquiry → Eligibility evaluation."; staff advances own → nobody; `expected_status` stale (409)
  → nobody; counselor PATCH changing only `next_action` → nobody; counselor advance on an agency application → staff notified,
  student's notice unchanged; deactivated assignee → Masters notified; Master confirms enrollment on a staff-assigned application →
  staff gets the status notice, each Master has exactly one notice from this request ("Commission estimated"); enrollment on an
  **unassigned** record → each Master exactly one notice (commission), none with the status title; application without
  `agent_student_id` → no agency notice; university name with CRLF is cleaned.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement**

```python
async def has_commission(db, application_id) -> bool:
    return bool(await db.scalar(select(AgentCommission.id).where(AgentCommission.application_id == application_id)))


async def status_changed(db, application, old_status, actor, *, had_commission: bool) -> int:
    """N3: any status change to an agency application. AC3: when this change just created the commission, the users the AGT-003
    trigger already told ("Commission estimated") are left out, so nobody gets two notices for one change."""
    if application.status == old_status or application.agent_student_id is None:
        return 0
    record = await db.get(AgentStudent, application.agent_student_id)
    users = await recipients(db, record, actor) if record else []
    if not had_commission and application.agent_id and await has_commission(db, application.id):
        agent = await db.get(User, application.agent_id)
        told = {u.id for u in await notification_recipients(db, agent)} if agent else set()
        users = [u for u in users if u.id not in told]
    university = clean_text(await db.scalar(select(University.name).where(University.id == application.university_id)))
    body = f"{university}: {stage_label(old_status)} → {stage_label(application.status)}."
    return await notify(db, users, "Application status changed", body, APPLICATIONS_URL)
```
(`notification_recipients` from `app.services.agent_orgs`; `stage_label` from `app.services.agent_applications`.)

Hooks — each route captures `had = await notices.has_commission(db, item.id)` **before** its `_maybe_trigger_agent_commission`
call (CRM `change_status` never reaches `enrolled`, so passes `had_commission=True`), then before commit:
`await notices.status_changed(db, item, old, user, had_commission=had)`. In `update_overseas_application` only when
`item.status != old_status` (the service also guards).
- [ ] **Step 4: Run** `test_agn_017_events.py -k status` + `test_agn_008_status*.py` + `test_agn_013_enrollment.py` +
  `test_agn_013_concurrency.py` — PASS.
- [ ] **Step 5: Commit** `feat(agn-017): status-change notices without double notice on enrollment`.

---

### Task 6: Event — task created

**Files:** service (`task_created`), `apps/api/app/api/agent_tasks.py` (`create_task`, after `new_task`), `test_agn_017_events.py`.

**Interfaces:** Produces `async task_created(db, record: AgentStudent, task: AgentTask, actor) -> int`.

- [ ] **Step 1: Failing tests** — Master creates a task on staff's record → staff gets "New task" / "A new task on one of your
  students is due {DD Mon YYYY}." (IST date; title text absent); staff creates own → nobody; archived (409) → nobody.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement**

```python
def ist_date(value) -> str:
    return value.astimezone(INDIA).strftime("%d %b %Y")


async def task_created(db, record, task, actor) -> int:
    return await notify(db, await recipients(db, record, actor), "New task", f"A new task on one of your students is due {ist_date(task.due_at)}.", TASKS_URL)
```
Hook: `await notices.task_created(db, student, task, user)` after `new_task(...)` (flush happens inside `queue_deliveries`).
- [ ] **Step 4: Run** `-k task` + `test_agn_016_create_read.py` — PASS.
- [ ] **Step 5: Commit** `feat(agn-017): new-task notice`.

---

### Task 7: Daily reminders — deadlines and overdue digest, idempotent

**Files:** service (`send_daily_reminders`, `run_daily_reminders`), `test_agn_017_reminders.py`, `test_agn_017_concurrency.py`.

**Interfaces:**
- Produces: `async send_daily_reminders(db, *, now: datetime) -> dict[str, int]` (`created`, `duplicate`, `failed`);
  `async run_daily_reminders() -> dict` (opens `SessionLocal`, `now=datetime.now(UTC)`).

- [ ] **Step 1: Failing tests**
  - application deadline today+3 / +1 / +0 → one reminder each with the right title; +2 → none;
  - status `offer` with both deadlines in window → only the offer reminder; `withdrawn`/`enrolled` → none; archived record → none;
    suspended org → none; deadline moved from +3 to +1 after a run → a new "tomorrow" reminder next run;
  - overdue: 3 open overdue tasks on staff's records + 1 done → staff gets one "Overdue tasks" / "You have 3 overdue tasks.";
    Masters get none (assignee active);
  - second call with the same `now` → `created == 0`, `duplicate > 0`, no new rows;
  - IST boundary: deadline D; `now = D-1 18:29 UTC` → "Deadline tomorrow"; `now = D-1 18:31 UTC` → "Deadline today";
  - a failing item (monkeypatch `queue_deliveries` to raise once) → `failed == 1`, other reminders still created, nothing raised;
  - concurrency: two `send_daily_reminders` on two sessions via `asyncio.gather` → each key exists once.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement**

```python
WINDOWS = {3: "Deadline in 3 days", 1: "Deadline tomorrow", 0: "Deadline today"}
CHUNK = 200


async def _remind(db, user, title, body, url, key) -> bool:
    stmt = (
        pg_insert(Notification)
        .values(id=uuid4(), user_id=user.id, title=title, body=body, read=False, action_url=url, dedupe_key=key)
        .on_conflict_do_nothing(index_elements=["dedupe_key"], index_where=Notification.dedupe_key.isnot(None))
        .returning(Notification.id)
    )
    new_id = await db.scalar(stmt)
    if new_id is None:
        return False
    await queue_deliveries(db, await db.get(Notification, new_id), user, channels=CHANNELS)
    return True


async def _guarded(db, counts, ids: dict, make) -> None:
    """One reminder in a savepoint: a failure is counted and logged with ids only, never raised (AC6)."""
    try:
        async with db.begin_nested():
            counts["created" if await make() else "duplicate"] += 1
    except Exception:
        counts["failed"] += 1
        logger.exception("agn017_reminder_failed", extra={"extra_fields": {k: str(v) for k, v in ids.items()}})


async def _deadline_reminders(db, today, counts, cache) -> None:
    days = [today + timedelta(days=d) for d in WINDOWS]
    last = None
    while True:
        q = (
            select(OverseasApplication, AgentStudent, University.name)
            .join(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)
            .join(University, University.id == OverseasApplication.university_id)
            .where(AgentStudent.status == "active", OverseasApplication.status.notin_([WITHDRAWN, "enrolled"]),
                   or_(OverseasApplication.application_deadline.in_(days), OverseasApplication.offer_deadline.in_(days)))
            .order_by(OverseasApplication.id).limit(CHUNK)
        )
        if last is not None:
            q = q.where(OverseasApplication.id > last)
        rows = (await db.execute(q)).all()
        if not rows:
            return
        for app, record, university in rows:
            kinds = (("offer", app.offer_deadline),) if app.status in OFFER_STAGES_ON else (("application", app.application_deadline), ("offer", app.offer_deadline))
            for kind, when in kinds:
                if when not in days:
                    continue
                left = (when - today).days
                body = f"{clean_text(university)}: {kind} deadline {when:%d %b %Y}."
                for user in await _cached_recipients(db, record, cache):
                    key = f"agn017:deadline:{app.id}:{kind}:{when.isoformat()}:{left}:{user.id}"
                    await _guarded(db, counts, {"application_id": app.id, "user_id": user.id},
                                   lambda u=user, k=key: _remind(db, u, WINDOWS[left], body, APPLICATIONS_URL, k))
        await db.commit()
        last = rows[-1][0].id


async def _cached_recipients(db, record, cache) -> list[User]:
    if record.id not in cache:
        cache[record.id] = await recipients(db, record, None)
    return cache[record.id]


async def _overdue_digests(db, now, today, counts, cache) -> None:
    per_record = (await db.execute(
        select(AgentTask.agent_student_id, func.count()).join(AgentStudent, AgentStudent.id == AgentTask.agent_student_id)
        .where(AgentTask.status == "open", AgentTask.due_at < now, AgentStudent.status == "active").group_by(AgentTask.agent_student_id)
    )).all()
    totals: dict = {}
    for record_id, n in per_record:
        record = await db.get(AgentStudent, record_id)
        for user in await _cached_recipients(db, record, cache):
            totals[user.id] = (user, totals.get(user.id, (user, 0))[1] + n)
    for user, n in totals.values():
        body = f"You have {n} overdue task{'s' if n != 1 else ''}."
        await _guarded(db, counts, {"user_id": user.id}, lambda u=user, b=body: _remind(db, u, "Overdue tasks", b, TASKS_URL, f"agn017:overdue:{today.isoformat()}:{u.id}"))
    await db.commit()


async def send_daily_reminders(db, *, now: datetime) -> dict[str, int]:
    today = now.astimezone(INDIA).date()
    counts = {"created": 0, "duplicate": 0, "failed": 0}
    cache: dict = {}
    await _deadline_reminders(db, today, counts, cache)
    await _overdue_digests(db, now, today, counts, cache)
    logger.info("agn017_reminders_done", extra={"extra_fields": {"day": today.isoformat(), **counts}})
    return counts


async def run_daily_reminders() -> dict[str, int]:
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await send_daily_reminders(db, now=datetime.now(UTC))
```
- [ ] **Step 4: Run** `test_agn_017_reminders.py test_agn_017_concurrency.py` — PASS.
- [ ] **Step 5: Commit** `feat(agn-017): idempotent daily deadline reminders and overdue digest`.

---

### Task 8: Celery beat entry

**Files:** `apps/api/app/worker.py`; test `test_agn_017_reminders.py::test_beat_runs_the_reminders_daily_at_0800_ist`.

- [ ] **Step 1: Failing test**

```python
def test_beat_runs_the_reminders_daily_at_0800_ist():
    from celery.schedules import crontab
    from app.worker import celery
    entry = celery.conf.beat_schedule["agn017-daily-reminders"]
    assert entry["task"] == "app.worker.send_daily_reminders_task"
    assert entry["schedule"] == crontab(hour=2, minute=30)
    assert "enh014-sweep-stale-deliveries" in celery.conf.beat_schedule
```
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement**

```python
@celery.task
def send_daily_reminders_task():
    """AGN-017 (DEC-SCOPE-055 N4): daily at 08:00 IST via beat; idempotent per day (notifications.dedupe_key)."""
    from app.services.agent_notifications import run_daily_reminders

    return _run_with_fresh_pool(run_daily_reminders)


celery.conf.beat_schedule = {
    "enh014-sweep-stale-deliveries": {"task": "app.worker.sweep_stale_deliveries_task", "schedule": 300.0},
    "agn017-daily-reminders": {"task": "app.worker.send_daily_reminders_task", "schedule": crontab(hour=2, minute=30)},  # UTC = 08:00 IST
}
```
- [ ] **Step 4: Run** the test + `test_enh_014_sweeper.py` — PASS.
- [ ] **Step 5: Commit** `feat(agn-017): beat schedules the daily reminders`.

---

### Task 9: `GET /workflows/notifications/unread-count`

**Files:** `apps/api/app/schemas.py` (`NotificationUnreadCount`), `apps/api/app/api/workflows.py`, `test_agn_017_api.py`.

- [ ] **Step 1: Failing tests** — two unread + one read for staff → `{"unread": 2}`; another user's unread not counted; unauthenticated
  → 401; existing `GET /workflows/notifications` response keys unchanged (`{"id","title","body","read","action_url","created_at"}` —
  `dedupe_key` absent); `PATCH …/{other user's id}/read` → 404.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement**

```python
class NotificationUnreadCount(BaseModel):
    unread: int


@router.get("/notifications/unread-count", response_model=NotificationUnreadCount)
async def unread_notification_count(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-017 (DEC-SCOPE-055 N7): the caller's own unread count, for the nav badge."""
    count = await db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.read.is_(False)))
    return {"unread": count or 0}
```
- [ ] **Step 4: Run** `test_agn_017_api.py` — PASS.
- [ ] **Step 5: Commit** `feat(agn-017): unread notification count`.

---

### Task 10: Frontend — Notifications section, nav badge

**Files:**
- Modify: `apps/web/lib/navigation.ts` (`NavItem.badge?`, `"notifications"` after `"tasks"` in the agent nav)
- Modify: `apps/web/components/PortalShell.tsx` (badge render; mobile label)
- Modify: `apps/web/components/PortalPage.tsx` (`agentNotifications` section, count fetch, badge on the nav item)
- Modify: `apps/web/components/SchoolNotificationList.tsx` (`localTime?: boolean`)
- Create: `apps/web/components/AgentNotificationsSection.tsx`
- Modify: `apps/web/app/globals.css` (one rule `.portal-nav .nav-badge{margin-left:8px;padding:1px 8px}`)
- Tests: `apps/web/tests/components/PortalPage.agentNotifications.test.tsx`, `AgentNotificationsSection.test.tsx`,
  `PortalShell.badge.test.tsx`, existing `SchoolNotificationList.test.tsx` (+ one `localTime` case)

**Interfaces:**
- Produces: `NavItem = { label; href; children?; badge?: number }`; `withBadge(nav: NavItem[], href: string, count: number | null)`
  in `lib/navigation.ts`; `AgentNotificationsSection({ user }: { user: User })`.

- [ ] **Step 1: Failing tests**
  - `PortalShell`: an item with `badge: 3` → link accessible name "Notifications 3 unread"; `badge: 120` → text "99+"; `badge: 0` or
    absent → no `.nav-badge`; the mobile menu entry reads "Notifications (3 unread)".
  - `PortalPage` (mocks `serverApi` as the existing `PortalPage.agentTasks.test.tsx` does): section `notifications` renders the
    section with a 404 portal payload; unread-count `{unread: 2}` → badge 2 on the Notifications item; unread-count rejects → no badge,
    page still renders.
  - `AgentNotificationsSection`: list renders titles and "Open: {title}" links; empty text; list rejects with 500 →
    "This section couldn't load. Refresh to try again."; 401 → the access-unavailable login card; 100 items → "Showing your latest
    100 notifications."; Super Admin → note.
  - `SchoolNotificationList`: default output unchanged; `localTime` renders a `<time>` element.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** (code shapes)

`lib/navigation.ts`:
```ts
export type NavItem = { label:string; href:string; children?:NavItem[]; badge?:number };
// AGN-017 (DEC-SCOPE-055 N8): Notifications for Masters and staff, after Tasks.
//   ["dashboard","students","universities","applications","documents","tasks","notifications","commissions","reports","team"]
export function withBadge(nav: NavItem[], href: string, count: number | null): NavItem[] {
  return count ? nav.map((item) => (item.href === href ? { ...item, badge: count } : item)) : nav;
}
```
`PortalShell.tsx` (desktop link body and mobile label):
```tsx
const badgeText=(n:number)=>n>99?"99+":String(n);
// desktop: <Link …>{x.label}{x.badge?<span className="badge nav-badge">{badgeText(x.badge)}<span className="visually-hidden"> unread</span></span>:null}</Link>
// mobile:  label: x.badge?`${x.label} (${badgeText(x.badge)} unread)`:x.label
```
`PortalPage.tsx`: `const agentNotifications=key==="overseas/agent"&&section==="notifications";` joins the 404-tolerated set and the
`main` switch (`<AgentNotificationsSection user={user}/>`); for `agent`, `Promise.all` also fetches
`serverApi<{unread:number}>("/api/v1/workflows/notifications/unread-count").then(r=>r.unread).catch(()=>null)`, then
`withBadge(agentNavFor(...), "/overseas/agent/notifications", unread)`.

`AgentNotificationsSection.tsx` (server):
```tsx
import { Suspense } from "react";
import SchoolNotificationList, { type NotificationItem } from "./SchoolNotificationList";
import SectionUnavailable from "./SectionUnavailable";
import { accessUnavailable } from "./AccessUnavailable";
import { ApiError, serverApi } from "@/lib/api";
import type { User } from "@/lib/types";

const EMPTY = "No notifications yet. You'll be told here about assignments, document requests, status changes, new tasks and upcoming deadlines.";
const WINDOW = 100; // GET /workflows/notifications returns the newest 100

async function List() {
  let items: NotificationItem[];
  try {
    items = await serverApi<NotificationItem[]>("/api/v1/workflows/notifications");
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return accessUnavailable(e, "/overseas/login");
    return <SectionUnavailable title="Notifications" />;
  }
  return (
    <>
      <SchoolNotificationList notifications={items} emptyText={EMPTY} localTime />
      {items.length >= WINDOW && <p className="muted">Showing your latest {WINDOW} notifications.</p>}
    </>
  );
}

export default function AgentNotificationsSection({ user }: { user: User }) {
  const member = user.role === "agent";
  return (
    <div className="portal-content">
      <div className="portal-title"><div><div className="eyebrow">Workspace</div><h1>Notifications</h1>
        <p className="muted">{member ? "Assignments, document requests, status changes, new tasks and deadline reminders for your students." : "Agency notifications go to the agency's own Masters and Staff."}</p></div></div>
      {member && <div className="card"><Suspense fallback={<p className="muted" role="status">Loading notifications…</p>}><List /></Suspense></div>}
    </div>
  );
}
```
`SchoolNotificationList.tsx`: `localTime?: boolean` → `{localTime ? <LocalTime value={n.created_at} time /> : formatDate(n.created_at, true, SCHOOL_TIME_ZONE)}`.
- [ ] **Step 4: Run** the four vitest files + `PortalPage.agentTasks.test.tsx` + `PortalPage.agentApplications.test.tsx`;
  `npx tsc --noEmit`; lint — PASS.
- [ ] **Step 5: Commit** `feat(agn-017): agent Notifications page and unread badge`.

---

### Task 11: E2E spec (run in browser validation, not in the lite pass)

**Files:** `apps/web/tests/e2e/agn-017-notifications.spec.ts` using `helpers/agency.ts` (`registerApprovedAgency`, `signIn`) and the
team UI to add a staff member (as `agn-016-tasks.spec.ts` does).

- [ ] **Step 1: Write** — Master assigns a student to staff → staff signs in → nav "Notifications 1 unread" → page lists "Student
  assigned to you" → "Open: Student assigned to you" navigates to Students → back on Notifications, the badge is gone (after reload).
- [ ] **Step 2: Typecheck/lint only** in the lite pass; executed during browser validation.
- [ ] **Step 3: Commit** `test(agn-017): e2e notifications spec`.

---

### Task 12: Docs and traceability

**Files:** `docs/architecture/API_CONTRACT.md` (unread-count; agency notices), `docs/architecture/DATA_MODEL.md` (`dedupe_key`,
indexes), `docs/quality/RTM.md` (AGN-017 rows → tests), `docs/delivery/ENHANCEMENT_BACKLOG.md` + `AGENT_CRM_BACKLOG.md` (status
"implemented; browser validation and Codex review pending" — **not** complete), spec §3 wording ("cached per record within a run"
for recipients in the job).

- [ ] **Step 1: Write the entries.**
- [ ] **Step 2: Commit** `docs(agn-017): contract, data model, RTM, backlog status`.

---

## Self-review

- Spec coverage: N1 → T3/T6; N2 → T2; N3 → T5; N4 → T7/T8; N5 → T2; N6 → T1/T7; N7 → T9; N8 → T10; N9 → T4; N10 → T7; §8 → T2/T4/T5;
  §9 → T10; AC1–AC10 → T1–T10; e2e → T11; docs → T12.
- Deviation recorded: recipients in the job are cached per record within a run instead of "one query per chunk" (simpler; same
  bound in practice). Spec updated in T12.
- Review Focus 1 → T5 test "staff advances own → nobody"; 2 → T5 deactivated; 3 → T5 next_action only; 4 → T7 rerun + IST boundary;
  5 → T4 CRLF/email.
