# AGN-021 View Staff Activity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An agency Master opens any of their staff members' student-journey activity (read from the audit log) from the Team page; another organisation's users get 404.

**Architecture:** One read-only, Master-only route `GET /workflows/overseas/agent/team/staff/{member_id}/activity` in `api/agent_team.py`, a non-locking `find_staff_member` extracted in `services/agent_orgs.py`, and a new `services/staff_activity.py` that filters `audit_logs` by the staff user and a seven-action allow-list and resolves each row's subject in at most three batched queries. The UI adds an **Activity** mode to `AgentStaffRow` rendering a new `AgentStaffActivity` component. No migration, no new audit writes.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, PostgreSQL, Pydantic 2, pytest + pytest-asyncio + httpx; Next.js (App Router), React, TypeScript, vitest + Testing Library, Playwright. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-01-agn-021-staff-activity-design.md` (approved 2026-10-01). Read it with this plan.

## Global Constraints

- Decision `DEC-SCOPE-046` A1–A5 (provisional number). Staff performance/KPIs stay parked under `C-10`.
- Allow-list (exact, in this order): `agent_student.create`, `agent_student.update`, `agent_student.duplicate_override`, `agent.student_link`, `overseas.application.create`, `document.upload`, `document.verify`.
- Route: `GET /api/v1/workflows/overseas/agent/team/staff/{member_id}/activity`, `limit` 1–100 default 25, `offset` 0–10000 default 0; response `{items, total, limit, offset}`; item `{id, at, action, subject, fields}`.
- 404 detail exactly `"Staff member not found"` (existing); Staff → existing 403 `"Only an agency Master can manage the team"`.
- Missing / unresolvable subject: exactly `"No longer available"`. Subject formats: record → name; application → `"<student> — <university>"`; document → `"<document_type> — <student>"` (em dash with spaces).
- Never in the response: reviewer notes, field values, emails, phone numbers, metadata other than `fields` (field names) for `agent_student.update`.
- Order `created_at DESC, id DESC`. Read-only: no lock, no commit, no cache.
- Log line `agent_org_staff_activity_viewed` with `extra={"extra_fields": {org_id, actor_id, member_id, offset}}` — ids only (the module's existing logger style).
- UI labels (exact): `agent_student.create` "Created a student record"; `agent_student.update` "Edited a student record"; `agent_student.duplicate_override` "Saved a student record despite a duplicate warning"; `agent.student_link` "Linked a student account"; `overseas.application.create` "Created an application"; `document.upload` "Uploaded a document"; `document.verify` "Verified a document"; anything else "Other activity". States: "Loading activity…", "No activity yet.", generic error "Unable to load activity." + **Try again**; page size 10 in the row; **Refresh**, **Close**.
- Existing tests: assertions never edited. Tests run for real; outcomes read from output. Per feature: lite backend set only (owner runs the full suite every 4–5 stories).

## Test commands

The owner's stack is up (`docker compose -p agn021 ... up -d postgres redis`). **`API_TEST <paths>`** (Windows-form mount path — `$PWD` mounts a stale tree under Git Bash):

```bash
docker compose -p agn021 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/agn-021/apps/api:/app" \
  api-test sh -c "alembic upgrade head && python -m pytest -q <paths>"
```

**`WEB_TEST <paths>`** = `cd apps/web && npx vitest run <paths>` (`npm ci` once if `node_modules` is missing).

**Lite backend set** (Task 5): `tests/test_agn_021_activity.py tests/test_agn_001_*.py tests/test_agn_002_*.py tests/test_agn_003_*.py tests/test_agn_004_*.py tests/test_ovs_005_*.py`.

## Review Focus

1. **Two rows written in one transaction share `created_at`** (a create saved over a duplicate warning writes `agent_student.create` and `agent_student.duplicate_override` together) — expected: a stable order across pages (`id` tiebreak), no row repeated or skipped between page 1 and page 2. Pinned in Task 1 (`test_paging_is_stable_on_equal_timestamps`).
2. **An audit row whose `entity_id` is not a UUID, or whose entity was deleted** — expected: `"No longer available"`, never a 500. Pinned in Task 1 (`test_unresolvable_subjects_read_no_longer_available`).
3. **The Master pages forward while an older page request is still in flight** — expected: the newer page stays on screen. Pinned in Task 2 (`ignores a response older than the latest request`).
4. **A member id that is a Master's own member id** (not staff) — expected: the same 404 as an unknown id. Pinned in Task 1 (`test_other_agency_master_and_unknown_ids_are_404`).
5. **Reviewer notes typed by staff while verifying** — expected: never in the activity response. Pinned in Task 1 (`test_staff_work_appears_on_the_next_request`, `notes` assertion).

---

## File Structure

**Backend — create:** `apps/api/app/services/staff_activity.py` (allow-list, subject resolution, page); `apps/api/tests/test_agn_021_activity.py`.
**Backend — modify:** `apps/api/app/services/agent_orgs.py` (`find_staff_member`, `_staff_member` delegates); `apps/api/app/api/agent_team.py` (route).
**Frontend — create:** `apps/web/components/AgentStaffActivity.tsx`; `apps/web/tests/components/AgentStaffActivity.test.tsx`; `apps/web/tests/e2e/agn-021-staff-activity.spec.ts`.
**Frontend — modify:** `apps/web/lib/agentStaff.ts` (type + labels); `apps/web/components/AgentStaffRow.tsx` (mode + button); `apps/web/tests/components/AgentStaffRow.test.tsx` (new cases only).
**Docs (Task 5):** decision register, backlog, conflict matrix, RBAC matrix, API contract, screen catalogue (+ json), role navigation note, RTM, RAID.

---

### Task 1: Backend — the activity route, lookup and read (AC01–AC06)

**Files:**
- Create: `apps/api/app/services/staff_activity.py`, `apps/api/tests/test_agn_021_activity.py`
- Modify: `apps/api/app/services/agent_orgs.py` (`_staff_member`, ~L321-330), `apps/api/app/api/agent_team.py` (imports; new route after `staff_permissions`)

**Interfaces:**
- Produces: `agent_orgs.find_staff_member(db, org_id, member_id) -> AgentOrgMember` (404 `"Staff member not found"`, no lock); `staff_activity.STAFF_ACTIVITY_ACTIONS: tuple[str, ...]`, `staff_activity.MAX_ACTIVITY_OFFSET = 10_000`, `staff_activity.UNAVAILABLE = "No longer available"`, `staff_activity.staff_activity_page(db, member, *, limit: int, offset: int) -> dict`; HTTP route as in Global Constraints.

- [ ] **Step 1: Write the failing tests** — `apps/api/tests/test_agn_021_activity.py`:

```python
"""AGN-021 -- a Master views one staff member's student-journey activity (spec §4-§5, §7; DEC-SCOPE-046 A1-A5)."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import AgentOrg, AuditLog
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import STAFF, mk_staff
from tests.agn003_helpers import DOC_VERIFY, agency_document
from tests.agn004_helpers import RECORDS

MASTER_ONLY = "Only an agency Master can manage the team"
NOT_FOUND = "Staff member not found"


def activity(member_id) -> str:
    return f"{STAFF}/{member_id}/activity"


async def _agency(db, name: str) -> dict:
    ctx = await mk_active_org(db, name=f"{name} {uniq()}")
    staff = await mk_staff(db, ctx["org"], full_name=f"{name} Staff", can_verify_documents=True)
    return ctx | {"staff": staff}


async def _row(db, user_id, action: str, *, entity_type: str = "agent_student", entity_id=None, metadata=None, at=None) -> AuditLog:
    row = AuditLog(user_id=user_id, action=action, entity_type=entity_type, entity_id=str(entity_id or uuid.uuid4()), metadata_json=metadata or {})
    if at is not None:
        row.created_at = at
    db.add(row)
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_staff_work_appears_on_the_next_request(db_session):  # AC01, AC04; Review Focus 5
    a = await _agency(db_session, "Activity Work")
    world = await agency_document(db_session, a, assigned_to=a["staff"]["member"])
    linkable = await mk_user(db_session, role="overseas_student", full_name="Linkable Student")
    email = f"asha-{uniq()}@example.local"
    async with client_for(a["master"].email) as m, client_for(a["staff"]["user"].email) as s:
        url = activity(a["staff"]["member"].id)
        assert (await m.get(url)).json()["total"] == 0
        created = await s.post(RECORDS, json={"full_name": "Asha Rao", "email": email})
        assert created.status_code == 201, created.text
        record_id = created.json()["id"]
        first = (await m.get(url)).json()  # the next request already shows it
        assert [(i["action"], i["subject"]) for i in first["items"]] == [("agent_student.create", "Asha Rao")]
        assert (await s.patch(f"{RECORDS}/{record_id}", json={"phone": "+91 98765 43210"})).status_code == 200
        assert (await s.post(RECORDS, json={"full_name": "Asha Again", "email": email, "confirm_duplicate": True})).status_code == 201
        assert (await s.post("/api/v1/workflows/overseas/agent/students", json={"student_id": str(linkable.id)})).status_code == 201
        app = await s.post("/api/v1/workflows/overseas/applications", json={"student_id": str(world["student"].id), "university_id": str(world["university"].id), "intake": "Jan 2028"})
        assert app.status_code == 201, app.text
        upload = await s.post("/api/v1/workflows/overseas/documents", json={"student_id": str(world["student"].id), "application_id": str(world["application"].id), "document_type": "Transcript", "file_url": "uploads/agn021.pdf"})
        assert upload.status_code == 201, upload.text
        verify = await s.patch(DOC_VERIFY.format(world["document"].id), json={"verification_status": "verified", "notes": "Secret reviewer note"})
        assert verify.status_code == 200, verify.text
        page = await m.get(url)
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 8 and body["limit"] == 25 and body["offset"] == 0
    got = {(i["action"], i["subject"], tuple(i["fields"] or ())) for i in body["items"]}
    assert got == {
        ("agent_student.create", "Asha Rao", ()),
        ("agent_student.update", "Asha Rao", ("phone",)),
        ("agent_student.create", "Asha Again", ()),
        ("agent_student.duplicate_override", "Asha Again", ()),
        ("agent.student_link", "Linkable Student", ()),
        ("overseas.application.create", "Agency Student — AGN003 University", ()),
        ("document.upload", "Transcript — Agency Student", ()),
        ("document.verify", "Passport — Agency Student", ()),
    }
    ats = [i["at"] for i in body["items"]]
    assert ats == sorted(ats, reverse=True)
    assert set(body["items"][0]) == {"id", "at", "action", "subject", "fields"}
    for secret in ("Secret reviewer note", email, "98765", "43210"):
        assert secret not in page.text


@pytest.mark.asyncio
async def test_other_agency_master_and_unknown_ids_are_404(db_session):  # AC02; Review Focus 4
    a = await _agency(db_session, "Activity Owner")
    b = await _agency(db_session, "Activity Other")
    async with client_for(b["master"].email) as other, client_for(a["master"].email) as m:
        cross = await other.get(activity(a["staff"]["member"].id))
        own_master = await m.get(activity(a["member"].id))
        unknown = await m.get(activity(uuid.uuid4()))
    for response in (cross, own_master, unknown):
        assert response.status_code == 404 and response.json()["detail"] == NOT_FOUND


@pytest.mark.asyncio
async def test_staff_and_inactive_agencies_are_refused(db_session):  # AC02
    a = await _agency(db_session, "Activity Refused")
    async with client_for(a["staff"]["user"].email) as s:
        own = await s.get(activity(a["staff"]["member"].id))
    assert own.status_code == 403 and own.json()["detail"] == MASTER_ONLY
    org = await db_session.get(AgentOrg, a["org"].id, populate_existing=True)
    org.status = "suspended"
    await db_session.commit()
    async with client_for(a["master"].email) as m:
        assert (await m.get(activity(a["staff"]["member"].id))).status_code == 403


@pytest.mark.asyncio
async def test_only_allow_listed_rows_of_this_staff_member_appear(db_session):  # AC03
    a = await _agency(db_session, "Activity Filter")
    other_staff = await mk_staff(db_session, a["org"], full_name="Other Staff")
    staff_id = a["staff"]["user"].id
    for action in ("auth.login", "auth.change_password", "profile.update", "message.send", "lookup.agent_link_search", "support.create", "agent_student.archive"):
        await _row(db_session, staff_id, action)
    await _row(db_session, other_staff["user"].id, "agent_student.create")
    async with client_for(a["master"].email) as m:
        body = (await m.get(activity(a["staff"]["member"].id))).json()
    assert body["total"] == 0 and body["items"] == []


@pytest.mark.asyncio
async def test_unresolvable_subjects_read_no_longer_available(db_session):  # AC04; Review Focus 2
    a = await _agency(db_session, "Activity Gone")
    staff_id = a["staff"]["user"].id
    await _row(db_session, staff_id, "agent_student.create")  # entity deleted / never existed
    await _row(db_session, staff_id, "overseas.application.create", entity_type="overseas_application")
    await _row(db_session, staff_id, "document.upload", entity_type="student_document")
    bad = AuditLog(user_id=staff_id, action="agent_student.update", entity_type="agent_student", entity_id="not-a-uuid", metadata_json={"fields": "phone"})
    db_session.add(bad)
    await db_session.commit()
    async with client_for(a["master"].email) as m:
        response = await m.get(activity(a["staff"]["member"].id))
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 4
    assert {i["subject"] for i in items} == {"No longer available"}
    assert next(i for i in items if i["action"] == "agent_student.update")["fields"] is None  # not a list -> None


@pytest.mark.asyncio
async def test_paging_is_stable_on_equal_timestamps(db_session):  # AC05; Review Focus 1
    a = await _agency(db_session, "Activity Paging")
    same = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    rows = [await _row(db_session, a["staff"]["user"].id, "document.upload", entity_type="student_document", at=same) for _ in range(3)]
    async with client_for(a["master"].email) as m:
        one = (await m.get(activity(a["staff"]["member"].id), params={"limit": 2, "offset": 0})).json()
        two = (await m.get(activity(a["staff"]["member"].id), params={"limit": 2, "offset": 2})).json()
    ids = [i["id"] for i in one["items"]] + [i["id"] for i in two["items"]]
    assert sorted(ids) == sorted(str(r.id) for r in rows) and len(set(ids)) == 3
    assert ids == sorted(ids, reverse=True)  # id DESC tiebreak
    assert (one["total"], one["limit"], two["offset"]) == (3, 2, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10001}])
async def test_paging_bounds_are_422(db_session, params):  # AC05
    a = await _agency(db_session, "Activity Bounds")
    async with client_for(a["master"].email) as m:
        assert (await m.get(activity(a["staff"]["member"].id), params=params)).status_code == 422
        assert (await m.get(f"{STAFF}/not-a-uuid/activity")).status_code == 422


@pytest.mark.asyncio
async def test_deactivated_staff_stay_viewable(db_session):  # AC06
    a = await _agency(db_session, "Activity Deactivated")
    gone = await mk_staff(db_session, a["org"], full_name="Gone Staff", active=False)
    await _row(db_session, gone["user"].id, "agent_student.create")
    async with client_for(a["master"].email) as m:
        response = await m.get(activity(gone["member"].id))
    assert response.status_code == 200 and response.json()["total"] == 1
```

Before Step 2, confirm two request shapes against existing tests and fix only the test if they differ: the CRM create response key `id` (`grep -n "RECORDS" apps/api/tests/test_agn_004_students.py | head`) and the application-create body (`intake` accepted — compare `tests/test_agn_004_staff_scope.py` and `apps/api/app/schemas.py` `OverseasApplicationCreate`).

- [ ] **Step 2: Run to verify they fail**

Run: `API_TEST tests/test_agn_021_activity.py`
Expected: FAIL — every route call returns `404 Not Found` (no route) / `405`; `test_paging_bounds_are_422` fails for the same reason.

- [ ] **Step 3: Extract `find_staff_member`** — `apps/api/app/services/agent_orgs.py`, replace `_staff_member` with:

```python
async def find_staff_member(db: AsyncSession, org_id, member_id) -> AgentOrgMember:
    """The organisation's staff member, else 404 -- another agency's member, every Master and an unknown id read the same (no
    disclosure). No lock: read paths (AGN-021 activity) use it as is; `_staff_member` adds the user lock for changes."""
    member = await db.scalar(
        select(AgentOrgMember).where(AgentOrgMember.id == member_id, AgentOrgMember.org_id == org_id, AgentOrgMember.role == "staff").execution_options(populate_existing=True)
    )
    if not member:
        raise HTTPException(404, "Staff member not found")
    return member


async def _staff_member(db: AsyncSession, org: AgentOrg, member_id) -> tuple[AgentOrgMember, User]:
    """`find_staff_member`, then the user row locked after the organisation (lock order: org -> user -> tokens, as
    reset-password/Re-send)."""
    member = await find_staff_member(db, org.id, member_id)
    user = await db.get(User, member.user_id, with_for_update=True, populate_existing=True)
    return member, user
```

- [ ] **Step 4: Create the read** — `apps/api/app/services/staff_activity.py`:

```python
"""AGN-021 / DEC-SCOPE-046 -- a Master reads one staff member's student-journey work from the audit log.

Spec: docs/superpowers/specs/2026-10-01-agn-021-staff-activity-design.md §4-§5. Read-only: no new audit writes, no lock, no cache
(A4: an action is visible on the next request). Subjects are things the Master may already read -- every entity a staff member can
act on is inside the agency (AGN-004 G4) and agency membership is permanent -- and only names/labels leave this module: never
notes, field values, emails or other metadata (A3).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrgMember, AgentStudent, AuditLog, OverseasApplication, StudentDocument, University, User

# A1: student-journey work only. Every action is written today with the staff user as `user_id` (spec §4 table).
STAFF_ACTIVITY_ACTIONS = (
    "agent_student.create",
    "agent_student.update",
    "agent_student.duplicate_override",
    "agent.student_link",
    "overseas.application.create",
    "document.upload",
    "document.verify",
)
MAX_ACTIVITY_OFFSET = 10_000
UNAVAILABLE = "No longer available"


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _key(entity_type: str, entity_id) -> tuple[str, str] | None:
    parsed = _uuid(entity_id)
    return (entity_type, str(parsed)) if parsed else None


def _joined(*parts: str | None) -> str:
    return " — ".join(p for p in parts if p) or UNAVAILABLE


async def _subjects(db: AsyncSession, rows: list[AuditLog]) -> dict[tuple[str, str], str]:
    """At most one batched query per entity type on the page."""
    wanted: dict[str, set[uuid.UUID]] = {"agent_student": set(), "overseas_application": set(), "student_document": set()}
    for row in rows:
        parsed = _uuid(row.entity_id)
        if parsed and row.entity_type in wanted:
            wanted[row.entity_type].add(parsed)
    names: dict[tuple[str, str], str] = {}
    if wanted["agent_student"]:
        query = select(AgentStudent.id, AgentStudent.full_name, User.full_name).outerjoin(User, User.id == AgentStudent.student_id).where(AgentStudent.id.in_(wanted["agent_student"]))
        for rid, own, linked in (await db.execute(query)).all():
            names[("agent_student", str(rid))] = _joined(own or linked)
    if wanted["overseas_application"]:
        query = (
            select(OverseasApplication.id, User.full_name, University.name)
            .outerjoin(User, User.id == OverseasApplication.student_id)
            .outerjoin(University, University.id == OverseasApplication.university_id)
            .where(OverseasApplication.id.in_(wanted["overseas_application"]))
        )
        for rid, student, university in (await db.execute(query)).all():
            names[("overseas_application", str(rid))] = _joined(student, university)
    if wanted["student_document"]:
        query = select(StudentDocument.id, StudentDocument.document_type, User.full_name).outerjoin(User, User.id == StudentDocument.student_id).where(StudentDocument.id.in_(wanted["student_document"]))
        for rid, document_type, student in (await db.execute(query)).all():
            names[("student_document", str(rid))] = _joined(document_type, student)
    return names


def _fields(row: AuditLog) -> list[str] | None:
    """Edited field NAMES for an edit only (A3); anything that is not a list of strings is dropped."""
    if row.action != "agent_student.update":
        return None
    value = (row.metadata_json or {}).get("fields")
    return [f for f in value if isinstance(f, str)] if isinstance(value, list) else None


async def staff_activity_page(db: AsyncSession, member: AgentOrgMember, *, limit: int, offset: int) -> dict:
    """One page of the staff member's allow-listed audit rows, newest first (`id` breaks equal timestamps: rows written in one
    transaction share `created_at`), in the organisation-list shape `{items, total, limit, offset}`."""
    where = (AuditLog.user_id == member.user_id, AuditLog.action.in_(STAFF_ACTIVITY_ACTIONS))
    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*where))
    rows = list((await db.scalars(select(AuditLog).where(*where).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset))).all())
    names = await _subjects(db, rows)
    items = [
        {"id": row.id, "at": row.created_at, "action": row.action, "subject": names.get(_key(row.entity_type, row.entity_id), UNAVAILABLE), "fields": _fields(row)}
        for row in rows
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}
```

(`names.get(None, UNAVAILABLE)` is safe for a non-UUID `entity_id`: `None` is a valid dict key and never stored.)

- [ ] **Step 5: Add the route** — `apps/api/app/api/agent_team.py`: add `find_staff_member` to the `app.services.agent_orgs` import list; add `from app.services.staff_activity import MAX_ACTIVITY_OFFSET, staff_activity_page`; append to the module docstring `AGN-021 -- a staff member's activity (DEC-SCOPE-046; read-only).`; after `staff_permissions`:

```python
@router.get("/staff/{member_id}/activity")
async def staff_activity(
    member_id: UUID,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=MAX_ACTIVITY_OFFSET),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AGN-021 (DEC-SCOPE-046 A1-A4): one staff member's student-journey work, newest first. Master-only; another agency's member,
    a Master and an unknown id are the same 404. Read-only: no lock, no commit, no cache."""
    membership = _require_master(user)
    member = await find_staff_member(db, membership.org_id, member_id)
    page = await staff_activity_page(db, member, limit=limit, offset=offset)
    logger.info(
        "agent_org_staff_activity_viewed",
        extra={"extra_fields": {"org_id": str(membership.org_id), "actor_id": str(user.id), "member_id": str(member.id), "offset": offset}},
    )
    return page
```

- [ ] **Step 6: Run to verify they pass, then the neighbours**

Run: `API_TEST tests/test_agn_021_activity.py tests/test_agn_002_staff.py tests/test_agn_002_master_rules.py tests/test_agn_003_permissions.py`
Expected: PASS (the AGN-002/003 suites exercise `_staff_member` through edit / deactivate / reactivate / reset / permissions).

- [ ] **Step 7: Refactor check, then commit** — reread the diff for duplication with `agent_team._staff_out` / the staff list paging (none expected); rerun Step 6 if anything changed.

```bash
git add apps/api/app/services/staff_activity.py apps/api/app/services/agent_orgs.py apps/api/app/api/agent_team.py apps/api/tests/test_agn_021_activity.py
git commit -m "feat(agn-021): Masters read a staff member's student-journey activity (404 outside the agency)"
```

---

### Task 2: Frontend — `AgentStaffActivity` and its labels (AC07)

**Files:**
- Modify: `apps/web/lib/agentStaff.ts`
- Create: `apps/web/components/AgentStaffActivity.tsx`, `apps/web/tests/components/AgentStaffActivity.test.tsx`

**Interfaces:**
- Consumes: Task 1's route and item shape.
- Produces: `type StaffActivityItem = { id: string; at: string; action: string; subject: string; fields: string[] | null }`; `ACTIVITY_LABELS: Record<string, string>`; `activityLabel(action: string): string`; default export `AgentStaffActivity({ member, onClose }: { member: StaffMember; onClose: () => void })`; `ACTIVITY_PAGE_SIZE = 10`.

- [ ] **Step 1: Write the failing tests** — `apps/web/tests/components/AgentStaffActivity.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStaffActivity from "@/components/AgentStaffActivity";
import { activityLabel, type StaffMember } from "@/lib/agentStaff";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const member: StaffMember = { id: "m1", code: "ABC-S001", full_name: "Priya", email: "p@example.local", phone: null, status: "active", setup: null, permissions: { can_verify_documents: false, can_view_reports: false } };
const item = (n: number, action = "agent_student.create", extra: Record<string, unknown> = {}) => ({ id: `a${n}`, at: "2026-10-01T09:30:00Z", action, subject: `Student ${n}`, fields: null, ...extra });
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 10, offset });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("activityLabel (AGN-021)", () => {
  it("labels every allow-listed action and falls back for others", () => {
    expect(activityLabel("agent_student.create")).toBe("Created a student record");
    expect(activityLabel("document.verify")).toBe("Verified a document");
    expect(activityLabel("something.new")).toBe("Other activity");
  });
});

describe("AgentStaffActivity (AGN-021)", () => {
  it("shows loading, then the member's activity with subject, edited field names and time", async () => {
    const mock = vi.fn().mockResolvedValue(res(page([item(1), item(2, "agent_student.update", { fields: ["phone", "date_of_birth"] })])));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffActivity member={member} onClose={() => {}} />);
    expect(screen.getByText("Loading activity…")).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Activity of ABC-S001" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText(/Edited a student record/)).toBeInTheDocument();
    expect(within(list).getByText(/Student 2 — phone, date of birth/)).toBeInTheDocument();
    expect(list.querySelector("time")).toHaveAttribute("dateTime", "2026-10-01T09:30:00Z");
    expect(mock.mock.calls[0][0]).toBe("/api/v1/workflows/overseas/agent/team/staff/m1/activity?limit=10&offset=0");
  });

  it("shows an empty state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([]))));
    render(<AgentStaffActivity member={member} onClose={() => {}} />);
    expect(await screen.findByText("No activity yet.")).toBeInTheDocument();
  });

  it("shows the server's message for a refused request and recovers with Try again", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({ detail: "Staff member not found" }, 404)).mockResolvedValueOnce(res(page([item(1)]))));
    render(<AgentStaffActivity member={member} onClose={() => {}} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Staff member not found");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/Student 1/)).toBeInTheDocument();
  });

  it("says Unable to load activity for a server error, a dropped connection or a body that is not a page", async () => {
    for (const failure of [Promise.resolve(res({ detail: "boom" }, 500)), Promise.reject(new TypeError("Failed to fetch")), Promise.resolve(res("<html>"))]) {
      vi.stubGlobal("fetch", vi.fn().mockReturnValue(failure));
      render(<AgentStaffActivity member={member} onClose={() => {}} />);
      expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load activity.");
      cleanup();
    }
  });

  it("pages through activity and refreshes the current page", async () => {
    const ten = Array.from({ length: 10 }, (_, i) => item(i + 1));
    const mock = vi.fn().mockResolvedValueOnce(res(page(ten, 11))).mockResolvedValueOnce(res(page([item(11)], 11, 10))).mockResolvedValueOnce(res(page([item(11)], 11, 10)));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffActivity member={member} onClose={() => {}} />);
    const pager = await screen.findByRole("navigation", { name: "Activity pages" });
    expect(within(pager).getByText("Showing 1–10 of 11")).toBeInTheDocument();
    expect(within(pager).getByRole("button", { name: "Previous page" })).toBeDisabled();
    fireEvent.click(within(pager).getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Showing 11–11 of 11")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await vi.waitFor(() => expect(mock).toHaveBeenCalledTimes(3));
    expect(mock.mock.calls[2][0]).toContain("offset=10");
  });

  it("ignores a response older than the latest request", async () => {  // Review Focus 3
    let slow: (r: Response) => void = () => {};
    const mock = vi.fn()
      .mockResolvedValueOnce(res(page(Array.from({ length: 10 }, (_, i) => item(i + 1)), 11)))
      .mockReturnValueOnce(new Promise<Response>((r) => { slow = r; }))
      .mockResolvedValueOnce(res(page(Array.from({ length: 10 }, (_, i) => item(i + 1)), 11)));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffActivity member={member} onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "Next page" })); // request 2 hangs
    fireEvent.click(screen.getByRole("button", { name: "Refresh" })); // request 3 resolves first
    await vi.waitFor(() => expect(mock).toHaveBeenCalledTimes(3));
    slow(res(page([item(99)], 11, 10)));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByText(/Student 99/)).toBeNull();
  });

  it("closes with the Close button and with Escape", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([item(1)]))));
    const onClose = vi.fn();
    render(<AgentStaffActivity member={member} onClose={onClose} />);
    fireEvent.click(await screen.findByRole("button", { name: "Close activity" }));
    fireEvent.keyDown(screen.getByRole("region", { name: "Activity" }), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
```

Note on "ignores a response older…": Refresh is clicked while request 2 (offset 10) is pending, so it re-requests offset 10 as request 3, which resolves first; request 2's late body (`Student 99`) must not render. Refresh stays enabled while loading (Step 4) for exactly this reason.

- [ ] **Step 2: Run to verify they fail**

Run: `WEB_TEST tests/components/AgentStaffActivity.test.tsx`
Expected: FAIL — cannot resolve `@/components/AgentStaffActivity` / `activityLabel` not exported.

- [ ] **Step 3: Add the type and labels** — append to `apps/web/lib/agentStaff.ts`:

```ts
// AGN-021 (DEC-SCOPE-046): one line of a staff member's activity, as GET …/staff/{id}/activity returns it.
export type StaffActivityItem = { id: string; at: string; action: string; subject: string; fields: string[] | null };

export const ACTIVITY_LABELS: Record<string, string> = {
  "agent_student.create": "Created a student record",
  "agent_student.update": "Edited a student record",
  "agent_student.duplicate_override": "Saved a student record despite a duplicate warning",
  "agent.student_link": "Linked a student account",
  "overseas.application.create": "Created an application",
  "document.upload": "Uploaded a document",
  "document.verify": "Verified a document",
};

export function activityLabel(action: string): string {
  return ACTIVITY_LABELS[action] ?? "Other activity";
}
```

- [ ] **Step 4: Write the component** — `apps/web/components/AgentStaffActivity.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { activityLabel, STAFF_URL, type StaffActivityItem, type StaffMember } from "@/lib/agentStaff";
import { isPage, type Page } from "@/lib/apiErrors";
import { formatDate } from "@/lib/formatDate";

export const ACTIVITY_PAGE_SIZE = 10;
const UNABLE = "Unable to load activity.";

class Refused extends Error {}

// AGN-021 (DEC-SCOPE-046 A1-A4): a staff member's student-journey work, shown inside their row on the Team page. Read on every
// open / page / Refresh (no cache), so a new action shows on the next load. Only the newest request may update the screen.
export default function AgentStaffActivity({ member, onClose }: { member: StaffMember; onClose: () => void }) {
  const [data, setData] = useState<Page<StaffActivityItem> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const latest = useRef(0);
  const headingId = `staff-activity-${member.id}`;

  const load = useCallback(
    (at: number) => {
      const request = ++latest.current;
      setLoading(true);
      setError(null);
      fetch(`${STAFF_URL}/${member.id}/activity?limit=${ACTIVITY_PAGE_SIZE}&offset=${at}`)
        .then(async (response) => {
          const body: unknown = await response.json().catch(() => null);
          if (!response.ok) {
            const detail = (body as { detail?: unknown } | null)?.detail;
            throw new Refused(response.status < 500 && typeof detail === "string" ? detail : UNABLE);
          }
          if (!isPage<StaffActivityItem>(body)) throw new Refused(UNABLE);
          if (request === latest.current) setData(body);
        })
        .catch((failure: unknown) => {
          if (request === latest.current) setError(failure instanceof Refused ? failure.message : UNABLE);
        })
        .finally(() => {
          if (request === latest.current) setLoading(false);
        });
    },
    [member.id],
  );

  useEffect(() => {
    load(offset);
  }, [load, offset]);

  return (
    <section aria-labelledby={headingId} style={{ marginTop: 8 }} onKeyDown={(event) => event.key === "Escape" && onClose()}>
      <h4 id={headingId} style={{ margin: "0 0 4px" }}>Activity</h4>
      {error ? (
        <>
          <p className="form-error" role="alert">{error}</p>
          <button type="button" className="btn secondary small" onClick={() => load(offset)}>Try again</button>
        </>
      ) : data === null ? (
        <p className="muted" role="status">Loading activity…</p>
      ) : data.items.length === 0 ? (
        <p className="muted">No activity yet.</p>
      ) : (
        <ol aria-label={`Activity of ${member.code}`} aria-busy={loading} style={{ paddingLeft: 18, margin: "4px 0" }}>
          {data.items.map((item) => (
            <li key={item.id} style={{ fontSize: 13, marginBottom: 4 }}>
              <strong>{activityLabel(item.action)}</strong> · {item.subject}
              {item.fields && item.fields.length > 0 ? ` — ${item.fields.map((f) => f.replaceAll("_", " ")).join(", ")}` : ""}{" "}
              <span className="muted"><time dateTime={item.at}>{formatDate(item.at, true)}</time></span>
            </li>
          ))}
        </ol>
      )}
      {data && data.total > ACTIVITY_PAGE_SIZE && (
        <nav aria-label="Activity pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, margin: "4px 0" }}>
          <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
          <button type="button" className="btn secondary small" aria-label="Previous page" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - ACTIVITY_PAGE_SIZE))}>Previous</button>
          <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(offset + ACTIVITY_PAGE_SIZE)}>Next</button>
        </nav>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
        <button type="button" className="btn secondary small" onClick={() => load(offset)}>Refresh</button>
        <button type="button" className="btn secondary small" aria-label="Close activity" autoFocus onClick={onClose}>Close</button>
      </div>
    </section>
  );
}
```

(`section` with `aria-labelledby` has the implicit `region` role the test queries. `Refresh` stays enabled while loading — the latest-request guard makes overlapping loads safe, which is what the stale-response test exercises.)

- [ ] **Step 5: Run to verify they pass**

Run: `WEB_TEST tests/components/AgentStaffActivity.test.tsx` then `cd apps/web && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 6: Commit**

```bash
git add apps/web/lib/agentStaff.ts apps/web/components/AgentStaffActivity.tsx apps/web/tests/components/AgentStaffActivity.test.tsx
git commit -m "feat(agn-021): staff activity list with loading, empty, error, paging and refresh"
```

---

### Task 3: Frontend — Activity on the staff row (AC07)

**Files:**
- Modify: `apps/web/components/AgentStaffRow.tsx` (`Mode` L10; render; buttons ~L137-155)
- Test: `apps/web/tests/components/AgentStaffRow.test.tsx` (append cases; existing cases untouched)

**Interfaces:**
- Consumes: `AgentStaffActivity` (Task 2).

- [ ] **Step 1: Write the failing tests** — open `AgentStaffRow.test.tsx`, reuse its existing member fixture / render helper names, and append:

```tsx
describe("AgentStaffRow activity (AGN-021)", () => {
  it("opens the member's activity in the row and returns focus to Activity on Close", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, limit: 10, offset: 0 }))));
    render(<ul><AgentStaffRow member={MEMBER} onChanged={() => {}} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: `Activity of ${MEMBER.full_name}` }));
    expect(await screen.findByText("No activity yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: `Edit ${MEMBER.full_name}` })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Close activity" }));
    await vi.waitFor(() => expect(screen.getByRole("button", { name: `Activity of ${MEMBER.full_name}` })).toHaveFocus());
  });

  it("offers Activity for a deactivated member too", () => {
    render(<ul><AgentStaffRow member={{ ...MEMBER, status: "deactivated" }} onChanged={() => {}} /></ul>);
    expect(screen.getByRole("button", { name: `Activity of ${MEMBER.full_name}` })).toBeInTheDocument();
  });
});
```

(Replace `MEMBER` with the file's existing member fixture name; add `vi`/`afterEach` imports only if the file lacks them.)

- [ ] **Step 2: Run to verify they fail**

Run: `WEB_TEST tests/components/AgentStaffRow.test.tsx`
Expected: the two new cases FAIL (no Activity button); existing cases PASS.

- [ ] **Step 3: Implement** — `apps/web/components/AgentStaffRow.tsx`:
  - `import AgentStaffActivity from "./AgentStaffActivity";`
  - `type Mode = "view" | "edit" | "confirm-deactivate" | "confirm-reset" | "permissions" | "activity";`
  - update the component comment's action list to include activity (AGN-021);
  - before the `mode === "view"` block: `{mode === "activity" && <AgentStaffActivity member={member} onClose={() => close("activity")} />}`
  - in the view buttons, right after Permissions:
    ```tsx
    <button id={id("activity")} className="btn secondary small" aria-label={`Activity of ${member.full_name}`} onClick={() => setMode("activity")}>Activity</button>
    ```

- [ ] **Step 4: Run to verify they pass**

Run: `WEB_TEST tests/components/AgentStaffRow.test.tsx tests/components/AgentStaffPanel.test.tsx tests/components/AgentStaffActivity.test.tsx` then `cd apps/web && npx tsc --noEmit && npx vitest run`
Expected: PASS (full vitest once).

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/AgentStaffRow.tsx apps/web/tests/components/AgentStaffRow.test.tsx
git commit -m "feat(agn-021): Activity on each staff row (Masters), focus returns on Close"
```

---

### Task 4: Playwright — staff work shows in the Master's next load (AC01, AC07)

**Files:**
- Create: `apps/web/tests/e2e/agn-021-staff-activity.spec.ts`

Needs the full stack (owner starts it; ask for the exact command with this worktree's ports) and `python -m app.seed`; run with `E2E_BASE_URL=http://localhost:<web port>`.

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from "@playwright/test";

import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";
import { E2E_PASSWORD } from "./helpers/welcome";

// AGN-021 -- a Master opens a staff member's Activity on the Team page; work the staff member does shows on the next load
// (Refresh, or reopening). Requires the stack running with `python -m app.seed` applied.

test("a staff member's work appears in the Master's activity view on the next load (AGN-021)", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "agn021");
  const staffEmail = `agn021-s-${unique}@example.local`;

  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  const created = await page.request.post("/api/v1/workflows/overseas/agent/team/staff", { data: { full_name: "Upsilon Staff", email: staffEmail } });
  expect(created.status()).toBe(201);

  await page.goto("/overseas/agent/team");
  await page.getByRole("button", { name: "Activity of Upsilon Staff" }).click();
  await expect(page.getByText("No activity yet.")).toBeVisible();

  const staff = await (await browser.newContext()).newPage();
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);
  const record = await staff.request.post("/api/v1/workflows/overseas/agent/crm/students", { data: { full_name: `Phi Student ${unique}` } });
  expect(record.status()).toBe(201);

  await page.getByRole("button", { name: "Refresh" }).click();
  const list = page.getByRole("list", { name: /Activity of .*-S001/ });
  await expect(list.getByText("Created a student record")).toBeVisible();
  await expect(list.getByText(`Phi Student ${unique}`)).toBeVisible();

  await page.getByRole("button", { name: "Close activity" }).click();
  await expect(page.getByRole("button", { name: "Activity of Upsilon Staff" })).toBeFocused();
});

test("the activity view fits a 320 px screen (AGN-021)", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await page.goto("/overseas/agent/team");
  const activity = page.getByRole("button", { name: /^Activity of / }).first();
  if (await activity.count()) {
    await activity.click();
    await expect(page.getByRole("region", { name: "Activity" })).toBeVisible();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
```

(If the seeded agency has no staff, the second test still checks the Team page width; the first test covers the open view at the default viewport. If `registerApprovedAgency`'s generated prefix makes the `-S001` pattern brittle, match the list by `name: /^Activity of /` instead.)

- [ ] **Step 2: Run** (stack up; owner confirmed)

Run: `cd apps/web && E2E_BASE_URL=http://localhost:<web port> npx playwright test tests/e2e/agn-021-staff-activity.spec.ts tests/e2e/agn-002-staff.spec.ts tests/e2e/agn-003-staff-permissions.spec.ts`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/agn-021-staff-activity.spec.ts
git commit -m "test(agn-021): e2e -- staff work appears in the Master's activity view on the next load"
```

---

### Task 5: Documentation, lite regression, evidence

**Files:** `docs/decisions/PRODUCT_DECISION_REGISTER.md`, `docs/delivery/ENHANCEMENT_BACKLOG.md`, `docs/evidence/CONFLICT_MATRIX.md`, `docs/architecture/RBAC_MATRIX.md`, `docs/architecture/API_CONTRACT.md`, `docs/ux/SCREEN_CATALOG.md`, `docs/ux/screen_catalog.json`, `docs/ux/ROLE_NAVIGATION.md`, `docs/quality/RTM.md`, `docs/delivery/RAID.md`

- [ ] **Step 1: Decision** — add `### DEC-SCOPE-046 — Agent staff activity (AGN-021)` after `DEC-SCOPE-044`, in its format: ID note (provisional; renumber on merge if taken), Question (the owner's AGN-021 statement and AC verbatim from spec §1), Evidence (EVID-015 §2; spec §4 audit table), Conflicts recorded (earlier AGN-021 scope superseded by AGN-003 PR #33 — owner re-scoped in-session 2026-10-01), Resolution A1–A5 verbatim from spec §1 (`EXPLICIT_APPROVAL`), Consequences (route, two services, Activity on the staff row; no migration). Update the D13 (DEC-SCOPE-038), S1 (DEC-SCOPE-040) and D1 (DEC-SCOPE-042) parentheticals: "staff activity decided as `DEC-SCOPE-046` (`AGN-021`); staff performance remains blocked".

- [ ] **Step 2: Backlog** — `ENHANCEMENT_BACKLOG.md`: `## AGN-021` section in the AGN-003 format (business requirement, existing behaviour, decisions, dependencies AGN-001/002/003/004, AGN-021-AC01…AC07 = spec §7, regression risks = spec §9, status); summary-table row; decision-table row; the EVID-015 row ("staff activity → AGN-021; staff performance and CRM settings stay parked").

- [ ] **Step 3: Architecture + UX** — `RBAC_MATRIX.md`: a "View staff activity" row (Master ✅, Staff ❌ 403, other agency 404) beside the Staff Performance N/A row; `API_CONTRACT.md`: the route (params, item shape, 403/404/422, allow-list, never-returned fields); `SCREEN_CATALOG.md` + `screen_catalog.json`: SCR-AGT-007 gains the Activity section (states, page size 10, Refresh/Close); `ROLE_NAVIGATION.md`: one note under Agent (Team page, Masters only; no new nav item).

- [ ] **Step 4: RAID + C-10** — `RAID.md`: audit-log retention still open (activity shows everything retained); a composite `(user_id, created_at)` index if `audit_logs` grows (not built). `CONFLICT_MATRIX.md` `C-10`: staff activity lifted by `DEC-SCOPE-046`.

- [ ] **Step 5: Lite backend regression**

Run: `API_TEST tests/test_agn_021_activity.py tests/test_agn_001_*.py tests/test_agn_002_*.py tests/test_agn_003_*.py tests/test_agn_004_*.py tests/test_ovs_005_*.py`
Expected: PASS. Also `cd apps/web && npx vitest run && npx tsc --noEmit && npm run lint` — PASS. Full backend suite: **not run** (owner cadence).

- [ ] **Step 6: RTM** — `docs/quality/RTM.md` AGN-021 row: AC01–AC07 → tests → results; lite-set command and counts; Playwright run; "browser validation and independent Codex review pending" (owner requirement); full suite not run.

- [ ] **Step 7: Commit**

```bash
git add docs/
git commit -m "docs(agn-021): DEC-SCOPE-046, backlog, RBAC/API, screens, RTM evidence, RAID"
```

---

## Self-review (done while writing)

- **Spec coverage:** §5.1 route → T1 Step 5; §5.2 `find_staff_member` → T1 Step 3, `staff_activity` → T1 Step 4; §5.3 errors → T1 tests; §6 labels/component → T2, row → T3; §7 AC01–AC06 → T1, AC07 → T2/T3/T4; §8 logging → T1 Step 5; §10 docs → T5.
- **Placeholders:** two deliberate "check then adapt the test only" notes (T1 request shapes; T3 fixture name) — each names the file to read. No TBD.
- **Names:** `find_staff_member`, `STAFF_ACTIVITY_ACTIONS`, `MAX_ACTIVITY_OFFSET`, `UNAVAILABLE`, `staff_activity_page`, `StaffActivityItem`, `ACTIVITY_LABELS`, `activityLabel`, `ACTIVITY_PAGE_SIZE`, `AgentStaffActivity` — consistent across tasks.
- **Review Focus:** five items, each pinned to a test in its owning task.
