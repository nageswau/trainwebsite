# AGN-023 EduSphere Counselor Assignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Overseas Admin assigns (and swaps) an EduSphere overseas counselor on any overseas application. On an agency application, the counselor supports the agency within the agency's rules. The Admin and counselor lists filter by agency and counselor.

**Architecture:**
- A dedicated Admin-only `PUT …/counselor` route owns `counselor_id` after creation. It audits, writes history and notifies. The generic PATCH refuses the field.
- Agency rules are enforced on the counselor's existing routes (advance, visa, documents queue) only when `agent_id IS NOT NULL`.
- A small new service, `application_filters`, parses, applies and describes the list filters on the shared "Application Tracking" portal payload.
- The web reads the filters from the URL and adds an assign control as a server-declared `DataTable` column type, like the existing `join` type.

**Tech Stack:** FastAPI + SQLAlchemy async (Python 3.12), pytest/pytest-asyncio, Next.js App Router + React (TypeScript), vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-06-agn-023-counselor-assignment-design.md` (H1–H12, AC01–AC21). Read it before starting.

## Global Constraints

- Decision `DEC-SCOPE-090` (bdm-020 took `089`). API contract §12M. **No migration.** Feature ID `AGN-023`.
- Authorization follows the inline pattern: a role check, then division, then scope. Never `require_role`/`require_permission`. The assign route is `overseas_admin` only. `super_admin` is **not** allowed, even though `_require` waves it through.
- Exact user-facing strings (copy them verbatim):
  - `"Only the Overseas Admin can assign a counselor"` (403)
  - `"This application is closed"` (409)
  - `"Choose an active overseas counselor"` (422)
  - `"Use Assign counselor to change the counselor"` (422)
  - `"Only the agency's Master confirms enrollment"` (403)
  - `"A visa case starts at the checklist stage"` (422)
  - `"The visa decision is recorded by the agency"` (422)
  - `"Filter not available"` (422)
  - `"Unknown filter value"` (422)
  - `"EduSphere counsellor assigned"` / `"EduSphere counsellor changed"` (history notes and agency notice titles)
  - `"Application assigned to you"`, `"Application reassigned"`, `"An application has moved to another counselor."`
  - `"Enrollment is confirmed by the agency."`
  - `"No applications match these filters"`
  - `"Not assigned"` (Admin column), `"Not assigned yet"` (agency detail)
- Agency notification bodies carry **no person names**. The university name is allowed, as in AGN-017 `status_changed`.
- Agency-only behavior is keyed on `OverseasApplication.agent_id IS NOT NULL`. Every non-agency application keeps today's behavior.
- Run only the **lite** backend set (this feature's files plus the listed regression files). The owner runs the full suite. Never judge a test outcome by reasoning: run it.
- Shell aliases used below. Run them from the worktree root `C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/prd84` in Git Bash. The owner starts and stops the docker stack, so if the `prd84` stack is not up, ask them.
  - `API_TEST "<pytest args>"` means:
    `docker compose -p prd84 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/prd84/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <pytest args>"`
  - `WEB_TEST "<cmd>"` means:
    `MSYS_NO_PATHCONV=1 docker compose -p prd84 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/prd84/apps/web:/app" -v /app/node_modules web-test sh -c "<cmd>"`
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push; the owner pushes.

## Review Focus

1. **The Admin re-picks the counselor while a notice is mid-send, or assigns twice quickly.** The row lock must serialize the two requests, giving exactly one history row and one set of notices. Task 1 adds a concurrent-assign test.
2. **The previous counselor still has the case open after a swap.** Their next advance or visa call must get `403`, not succeed on stale access. Task 1 (AC02) pins the advance call.
3. **A counselor's visa PATCH on an agency case the agency has just moved.** It must apply the agency's stage under the lock, never a stale one, and must not silently move a decided case. Task 2 pins the decided lock and the forward-only rule.
4. **A filter URL that has been edited or pasted** (a deleted agency id, garbage, a filter for the wrong role). The API refuses it with `422`, and the page falls back to the unfiltered list with the message instead of an access-denied card. Tasks 3 and 4.
5. **Rows past the 500-row cap.** A filtered list must still find an old agency application. Task 3 has a test with more than 500 rows.

---

### Task 1: Assign route, generic PATCH refusal, notices

**Files:**
- Modify: `apps/api/app/schemas.py` (after `class OverseasApplicationUpdate`, ~L380)
- Modify: `apps/api/app/api/workflows.py` (imports ~L95-107; `update_overseas_application` ~L1897-1943; new route right after it)
- Modify: `apps/api/app/services/agent_notifications.py` (new `counselor_assigned` after `status_changed`)
- Modify: `apps/api/tests/test_tel_017_it_counselor.py:189-192` (the PATCH now refuses `counselor_id`)
- Create: `apps/api/tests/agn023_helpers.py`
- Create: `apps/api/tests/test_agn_023_assign.py`

**Interfaces:**
- Produces:
  - `PUT /api/v1/workflows/overseas/applications/{id}/counselor`, body `{"counselor_id": uuid}`, which returns `{"id", "counselor_id", "counselor_name", "changed": bool}`.
  - `agency_notices.counselor_assigned(db, application, actor, *, changed: bool) -> None`.
  - Test helpers `assign_world(db, *, status="offer") -> dict`, `notices(db, user)`, `fresh(db, app)`, `history_notes(db, app)`, `assign_audits(db, app)`, and the constants `ASSIGN`, `UPDATE`, `ADVANCE`, `PORTAL`.

- [ ] **Step 1: Write the helpers**

`apps/api/tests/agn023_helpers.py`:

```python
"""AGN-023 test helpers: the AGN-009 agency world (a Master, a Verify staff member assigned the no-login student, another agency) plus
an Overseas Admin, two active overseas counselors, an inactive one, an IT counselor, an agency application and a direct one."""

from sqlalchemy import select

from app.models import ApplicationStatusHistory, AuditLog, Notification, OverseasApplication
from tests.agn001_helpers import mk_user, uniq
from tests.agn008_helpers import mk_application
from tests.agn009_helpers import world as documents_world

ASSIGN = "/api/v1/workflows/overseas/applications/{}/counselor"
UPDATE = "/api/v1/workflows/overseas/applications/{}"
ADVANCE = "/api/v1/workflows/overseas/applications/{}/advance"
PORTAL = "/api/v1/portal/overseas/{}/{}"


async def assign_world(db, *, status: str = "offer") -> dict:
    w = await documents_world(db)
    w["admin"] = await mk_user(db, role="overseas_admin", full_name=f"Admin {uniq()}")
    w["counselor"] = await mk_user(db, role="counselor", full_name=f"Counsellor A {uniq()}")
    w["counselor2"] = await mk_user(db, role="counselor", full_name=f"Counsellor B {uniq()}")
    w["inactive"] = await mk_user(db, role="counselor", full_name=f"Inactive {uniq()}", active=False)
    w["it_counselor"] = await mk_user(db, role="counselor", division="it", full_name=f"IT {uniq()}")
    w["app"] = await mk_application(db, agent=w["master"], university=w["university"], record=w["record"], status=status)
    w["direct_student"] = await mk_user(db, role="overseas_student", full_name=f"Direct {uniq()}")
    w["direct_app"] = await mk_application(db, agent=None, university=w["university"], student=w["direct_student"], status=status)
    return w


async def notices(db, user) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at)
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


async def fresh(db, app) -> OverseasApplication:
    return await db.get(OverseasApplication, app.id, populate_existing=True)


async def history_notes(db, app) -> list[str | None]:
    stmt = select(ApplicationStatusHistory.notes).where(ApplicationStatusHistory.application_id == app.id).order_by(ApplicationStatusHistory.created_at)
    return list((await db.scalars(stmt)).all())


async def assign_audits(db, app) -> list[dict]:
    stmt = select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.counselor_assign").order_by(AuditLog.created_at)
    return [row.metadata_json for row in (await db.scalars(stmt)).all()]
```

- [ ] **Step 2: Write the failing tests**

`apps/api/tests/test_agn_023_assign.py`:

```python
"""AGN-023 AC01-AC08 -- the Overseas Admin assigns or swaps an EduSphere counselor (spec §3.1, §3.2, §5)."""

import asyncio
import uuid

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for
from tests.agn023_helpers import ADVANCE, ASSIGN, UPDATE, assign_audits, assign_world, fresh, history_notes, notices


@pytest_asyncio.fixture
async def world(db_session):
    return await assign_world(db_session)


async def _assign(c, app, counselor):
    return await c.put(ASSIGN.format(app.id), json={"counselor_id": str(counselor.id)})


@pytest.mark.asyncio
async def test_admin_assigns_a_counselor_who_then_sees_the_application(db_session, world):  # AC01
    async with client_for(world["admin"].email) as c:
        r = await _assign(c, world["app"], world["counselor"])
    assert r.status_code == 200, r.text
    assert r.json() == {"id": str(world["app"].id), "counselor_id": str(world["counselor"].id), "counselor_name": world["counselor"].full_name, "changed": True}
    assert (await fresh(db_session, world["app"])).counselor_id == world["counselor"].id
    assert await history_notes(db_session, world["app"]) == ["EduSphere counsellor assigned"]
    assert await assign_audits(db_session, world["app"]) == [{"from_counselor_id": None, "to_counselor_id": str(world["counselor"].id)}]
    async with client_for(world["counselor"].email) as c:
        rows = (await c.get("/api/v1/portal/overseas/counselor/applications")).json()["rows"]
    assert str(world["app"].id) in {str(row["id"]) for row in rows}


@pytest.mark.asyncio
async def test_a_swap_moves_access_and_tells_both_counselors(db_session, world):  # AC02, AC08
    async with client_for(world["admin"].email) as c:
        assert (await _assign(c, world["app"], world["counselor"])).status_code == 200
        r = await _assign(c, world["app"], world["counselor2"])
    assert r.status_code == 200 and r.json()["changed"] is True
    assert await history_notes(db_session, world["app"]) == ["EduSphere counsellor assigned", "EduSphere counsellor changed"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(ADVANCE.format(world["app"].id), json={"to_status": "visa_documentation"})).status_code == 403
    assert [n.title for n in await notices(db_session, world["counselor"])] == ["Application assigned to you", "Application reassigned"]
    reassigned = (await notices(db_session, world["counselor"]))[-1]
    assert reassigned.body == "An application has moved to another counselor."
    assert [n.title for n in await notices(db_session, world["counselor2"])] == ["Application assigned to you"]


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["counselor", "master", "university_rep", "super_admin", "overseas_student"])
async def test_only_the_overseas_admin_may_assign(db_session, world, who):  # AC03
    from tests.agn001_helpers import mk_user

    users = {"counselor": world["counselor"], "master": world["master"]}
    user = users.get(who) or await mk_user(db_session, role=who, division="overseas")
    async with client_for(user.email) as c:
        r = await _assign(c, world["app"], world["counselor2"])
    assert r.status_code == 403, r.text
    assert (await fresh(db_session, world["app"])).counselor_id is None


@pytest.mark.asyncio
async def test_an_unknown_application_is_404(world):  # AC03
    async with client_for(world["admin"].email) as c:
        r = await c.put(ASSIGN.format(uuid.uuid4()), json={"counselor_id": str(world["counselor"].id)})
    assert r.status_code == 404 and r.json()["detail"] == "Application not found"


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["null", "missing", "it_counselor", "inactive", "admin", "unknown"])
async def test_the_counselor_must_be_an_active_overseas_counselor(db_session, world, target):  # AC04
    body = {
        "null": {"counselor_id": None},
        "missing": {},
        "it_counselor": {"counselor_id": str(world["it_counselor"].id)},
        "inactive": {"counselor_id": str(world["inactive"].id)},
        "admin": {"counselor_id": str(world["admin"].id)},
        "unknown": {"counselor_id": str(uuid.uuid4())},
    }[target]
    async with client_for(world["admin"].email) as c:
        r = await c.put(ASSIGN.format(world["app"].id), json=body)
    assert r.status_code == 422, r.text
    if target not in {"null", "missing"}:
        assert r.json()["detail"] == "Choose an active overseas counselor"
    assert (await fresh(db_session, world["app"])).counselor_id is None
    assert await history_notes(db_session, world["app"]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["withdrawn", "enrolled"])
async def test_a_closed_application_is_refused(db_session, status):  # AC05
    w = await assign_world(db_session, status=status)
    async with client_for(w["admin"].email) as c:
        r = await _assign(c, w["app"], w["counselor"])
    assert r.status_code == 409 and r.json()["detail"] == "This application is closed"
    assert (await fresh(db_session, w["app"])).counselor_id is None


@pytest.mark.asyncio
async def test_re_picking_the_same_counselor_changes_nothing(db_session, world):  # AC06
    async with client_for(world["admin"].email) as c:
        await _assign(c, world["app"], world["counselor"])
        r = await _assign(c, world["app"], world["counselor"])
    assert r.status_code == 200 and r.json()["changed"] is False
    assert len(await history_notes(db_session, world["app"])) == 1
    assert len(await assign_audits(db_session, world["app"])) == 1
    assert len(await notices(db_session, world["counselor"])) == 1


@pytest.mark.asyncio
async def test_two_assignments_at_once_leave_one_history_row(db_session, world):  # Review Focus 1
    async with client_for(world["admin"].email) as a, client_for(world["admin"].email) as b:
        results = await asyncio.gather(_assign(a, world["app"], world["counselor"]), _assign(b, world["app"], world["counselor"]))
    assert sorted(r.json()["changed"] for r in results) == [False, True]
    assert len(await history_notes(db_session, world["app"])) == 1
    assert len(await notices(db_session, world["counselor"])) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["admin", "counselor"])
async def test_the_generic_update_refuses_counselor_id(db_session, world, who):  # AC07
    async with client_for(world["admin"].email) as c:
        await _assign(c, world["app"], world["counselor"])
    async with client_for(world[who].email) as c:
        for value in (str(world["counselor2"].id), None):
            r = await c.patch(UPDATE.format(world["app"].id), json={"counselor_id": value})
            assert r.status_code == 422, r.text
            assert r.json()["detail"] == "Use Assign counselor to change the counselor"
    assert (await fresh(db_session, world["app"])).counselor_id == world["counselor"].id


@pytest.mark.asyncio
async def test_the_agency_hears_without_names_and_a_direct_application_does_not_notify_it(db_session, world):  # AC08
    staff = world["staff"]["user"]  # the no-login student's assigned staff member: the AGN-017 recipient
    async with client_for(world["admin"].email) as c:
        await _assign(c, world["app"], world["counselor"])
        await _assign(c, world["app"], world["counselor2"])
        await _assign(c, world["direct_app"], world["counselor"])
    titles = [n.title for n in await notices(db_session, staff)]
    assert titles == ["EduSphere counsellor assigned", "EduSphere counsellor changed"]
    for n in await notices(db_session, staff):
        assert world["counselor"].full_name not in n.body and world["counselor2"].full_name not in n.body
        assert world["record"].full_name not in n.body
    assert await notices(db_session, world["master"]) == []  # the assignee is told, not the Masters (AGN-017 N2)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `API_TEST "tests/test_agn_023_assign.py"`
Expected: FAIL. Most tests get `405 Method Not Allowed`, because no PUT route exists yet; the PATCH tests get `200`, not `422`.

- [ ] **Step 4: Add the schema**

In `apps/api/app/schemas.py`, directly after `class OverseasApplicationUpdate(...)` (and its fields):

```python
class OverseasApplicationCounselorAssign(BaseModel):
    """AGN-023 (DEC-SCOPE-090 H8): swap only -- a counselor is required; null or missing is a 422."""

    counselor_id: UUID
```

- [ ] **Step 5: Add the agency notice**

In `apps/api/app/services/agent_notifications.py`, directly after `async def status_changed(...)`:

```python
async def counselor_assigned(db: AsyncSession, application: OverseasApplication, actor: User, *, changed: bool) -> None:
    """AGN-023 (DEC-SCOPE-090 H5): an EduSphere counselor was assigned to, or changed on, an agency application. AGN-017 recipients;
    no person names in the body (the counselor's name is on the application detail, H7)."""
    if application.agent_student_id is None:
        return
    record = await db.get(AgentStudent, application.agent_student_id)
    users = await recipients(db, record, actor) if record else []
    university = clean_text(await db.scalar(select(University.name).where(University.id == application.university_id)))
    title = "EduSphere counsellor changed" if changed else "EduSphere counsellor assigned"
    await notify(db, users, title, f"{university}: an EduSphere counsellor is now supporting this application.", APPLICATIONS_URL)
```

- [ ] **Step 6: Refuse `counselor_id` in the generic PATCH**

In `apps/api/app/api/workflows.py`, add the module constants near the top (after `logger = ...`):

```python
COUNSELOR_REFUSED_ON_UPDATE = "Use Assign counselor to change the counselor"  # AGN-023 (DEC-SCOPE-090 H10)
APPLICATION_CLOSED = "This application is closed"
CHOOSE_ACTIVE_COUNSELOR = "Choose an active overseas counselor"
```

In `update_overseas_application`, directly after `changes = payload.model_dump(exclude_unset=True)`, add:

```python
    # AGN-023 (DEC-SCOPE-090 H10): after creation only the Admin's assign route changes the counselor (audited, notified).
    if "counselor_id" in changes:
        raise HTTPException(422, COUNSELOR_REFUSED_ON_UPDATE)
```

Then delete these two lines further down in the same function:

```python
    if changes.get("counselor_id"):
        await _require_overseas_counselor(db, changes["counselor_id"])
```

and change `allowed = {"counselor_id", "intake", "status", "application_reference", "offer_letter_url"}` to
`allowed = {"intake", "status", "application_reference", "offer_letter_url"}`.

- [ ] **Step 7: Add the route**

Add `OverseasApplicationCounselorAssign` to the `from app.schemas import (...)` list. Add `AgentStudent` and `SchoolStudent` to the `from app.models import (...)` list if they are missing (check with grep first). Then, directly after `update_overseas_application`:

```python
async def _owner_name(db: AsyncSession, item: OverseasApplication) -> str:
    """The application's student for an internal counselor notice: the account, else the agency record, else the school record."""
    for model, key in ((User, item.student_id), (AgentStudent, item.agent_student_id), (SchoolStudent, item.school_student_id)):
        if key is not None:
            name = await db.scalar(select(model.full_name).where(model.id == key))
            if name:
                return name
    return "A student"


@router.put("/overseas/applications/{application_id}/counselor")
async def assign_overseas_counselor(
    application_id: UUID, payload: OverseasApplicationCounselorAssign, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """AGN-023 (DEC-SCOPE-090 §3.1): the Overseas Admin assigns or swaps an application's EduSphere counselor (H2, H8). Not
    super_admin, which `_require` would wave through."""
    if user.role != "overseas_admin" or user.division != "overseas":
        raise HTTPException(403, "Only the Overseas Admin can assign a counselor")
    item = await db.get(OverseasApplication, application_id, with_for_update=True)
    if item is None:
        raise HTTPException(404, "Application not found")
    if item.status in {WITHDRAWN, "enrolled"}:
        raise HTTPException(409, APPLICATION_CLOSED)
    counselor = await db.get(User, payload.counselor_id)
    if counselor is None or counselor.role != "counselor" or counselor.division != "overseas" or not counselor.active:
        raise HTTPException(422, CHOOSE_ACTIVE_COUNSELOR)
    result = {"id": item.id, "counselor_id": counselor.id, "counselor_name": counselor.full_name}
    if item.counselor_id == counselor.id:
        return {**result, "changed": False}
    previous_id = item.counselor_id
    item.counselor_id = counselor.id
    note = "EduSphere counsellor changed" if previous_id else "EduSphere counsellor assigned"
    db.add(ApplicationStatusHistory(application_id=item.id, from_status=item.status, to_status=item.status, next_action=item.next_action, notes=note, changed_by_id=user.id))
    await _audit(db, user, "overseas.application.counselor_assign", "overseas_application", item.id, {"from_counselor_id": str(previous_id) if previous_id else None, "to_counselor_id": str(counselor.id)})
    university = await db.scalar(select(University.name).where(University.id == item.university_id))
    await _notify_user(db, counselor, "Application assigned to you", f"{await _owner_name(db, item)} — {university}", "/overseas/counselor/applications")
    previous = await db.get(User, previous_id) if previous_id else None
    if previous is not None and previous.active:
        await _notify_user(db, previous, "Application reassigned", "An application has moved to another counselor.", "/overseas/counselor/applications")
    if item.agent_id is not None:
        await agency_notices.counselor_assigned(db, item, user, changed=previous_id is not None)
    await db.commit()
    return {**result, "changed": True}
```

Note: FastAPI validates the body before the handler runs, so a non-admin who sends an invalid body gets `422`, not `403`. The 403 tests send a valid body.

- [ ] **Step 8: Update the tel-017 test the change supersedes**

In `apps/api/tests/test_tel_017_it_counselor.py`, replace lines 189–192:

```python
    patch = await client.patch(f"/api/v1/workflows/overseas/applications/{app_id}", json={"counselor_id": str(bad)})
    assert patch.status_code == 422, patch.text
    assert (await db_session.get(OverseasApplication, uuid.UUID(app_id), populate_existing=True)).counselor_id == good.id
    assert (await client.patch(f"/api/v1/workflows/overseas/applications/{app_id}", json={"counselor_id": None})).status_code == 200
```

with:

```python
    # AGN-023 (DEC-SCOPE-090 H10): the generic update no longer changes the counselor at all; the assign route checks the target.
    for value in (str(bad), None):
        patch = await client.patch(f"/api/v1/workflows/overseas/applications/{app_id}", json={"counselor_id": value})
        assert patch.status_code == 422, patch.text
        assert patch.json()["detail"] == "Use Assign counselor to change the counselor"
    assert (await db_session.get(OverseasApplication, uuid.UUID(app_id), populate_existing=True)).counselor_id == good.id
    assign = await client.put(f"/api/v1/workflows/overseas/applications/{app_id}/counselor", json={"counselor_id": str(bad)})
    assert assign.status_code == 422, assign.text
```

- [ ] **Step 9: Run the tests**

Run: `API_TEST "tests/test_agn_023_assign.py tests/test_tel_017_it_counselor.py"`
Expected: PASS (every test).

- [ ] **Step 10: Run the lite regression for the touched paths**

Run: `API_TEST "tests/test_agn_008_status.py tests/test_agn_008_security.py tests/test_agn_017_events.py tests/test_agn_017_recipients.py tests/test_ovs_003_eligibility.py tests/test_agn_003_matrix.py"`
Expected: PASS. If a test PATCHes `counselor_id`, it now gets `422`. Report it rather than weakening the new rule.

- [ ] **Step 11: Commit**

```bash
git add apps/api/app/schemas.py apps/api/app/api/workflows.py apps/api/app/services/agent_notifications.py apps/api/tests/agn023_helpers.py apps/api/tests/test_agn_023_assign.py apps/api/tests/test_tel_017_it_counselor.py
git commit -m "feat(agn-023): Overseas Admin assigns an EduSphere counselor; generic update refuses counselor_id (AC01-AC08)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The counselor on an agency application (advance, visa, documents, agency detail)

**Files:**
- Modify: `apps/api/app/api/workflows.py`:
  - `advance_overseas_application` (~L1971)
  - `get_visa_checklist` (~L2191)
  - `update_visa` (~L2263)
  - `create_visa_case` (~L2291)
- Modify: `apps/api/app/services/portal.py` (the `section == "documents"` block, ~L1034)
- Modify: `apps/api/app/services/agent_applications.py` (`detail()`, ~L157)
- Create: `apps/api/tests/test_agn_023_counselor_scope.py`

**Interfaces:**
- Consumes: `assign_world`, `ASSIGN`, `ADVANCE`, `PORTAL`, `fresh` (Task 1); `mk_case`, `case_of`, `verified` from `tests/agn012_helpers.py`; `mk_doc` from `tests/agn009_helpers.py`; `mk_record` from `tests/agn004_helpers.py`.
- Produces:
  - `GET …/visa-checklist` gains `locked_reason: str | None`. It is non-null only on an agency application whose case is decided or enrolled. Task 6 reads it.
  - The agency detail gains `counselor_name: str | None`. Task 6 reads it.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/test_agn_023_counselor_scope.py`:

```python
"""AGN-023 AC09-AC14 -- a counselor on an agency application keeps to the agency's rules (spec §4); the agency sees the name (§6)."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentCommission, VisaCase
from tests.agn001_helpers import client_for
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import APPS, mk_application
from tests.agn009_helpers import mk_doc
from tests.agn012_helpers import case_of, mk_case, verified
from tests.agn023_helpers import ADVANCE, ASSIGN, PORTAL, assign_world, fresh

VISA = "/api/v1/workflows/overseas/visa"


async def _assigned(db, *, status="offer"):
    w = await assign_world(db, status=status)
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    return w


@pytest_asyncio.fixture
async def world(db_session):
    return await _assigned(db_session)


@pytest.mark.asyncio
async def test_the_counselor_cannot_enroll_an_agency_application(db_session, world):  # AC09
    async with client_for(world["counselor"].email) as c:
        r = await c.post(ADVANCE.format(world["app"].id), json={"to_status": "enrolled"})
        assert r.status_code == 403 and r.json()["detail"] == "Only the agency's Master confirms enrollment"
        assert (await c.post(ADVANCE.format(world["app"].id), json={"to_status": "visa_documentation"})).status_code == 200
    assert (await fresh(db_session, world["app"])).status == "visa_documentation"
    count = await db_session.scalar(select(func.count()).select_from(AgentCommission).where(AgentCommission.application_id == world["app"].id))
    assert count == 0


@pytest.mark.asyncio
async def test_a_direct_application_can_still_be_enrolled_by_its_counselor(db_session, world):  # AC11
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(ADVANCE.format(world["direct_app"].id), json={"to_status": "enrolled"})).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "code", "detail"), [("enquiry", 422, "An offer is needed before a visa case"), ("enrolled", 409, "This application is enrolled, so its visa case can no longer be changed")])
async def test_an_agency_visa_case_needs_an_offer_and_an_open_application(db_session, status, code, detail):  # AC10
    w = await _assigned(db_session)
    app = await fresh(db_session, w["app"])
    app.status = status
    await db_session.commit()
    async with client_for(w["counselor"].email) as c:
        r = await c.post(VISA, json={"application_id": str(w["app"].id), "checklist": ["Passport"]})
    assert r.status_code == code and r.json()["detail"] == detail
    assert await case_of(db_session, w["app"]) is None


@pytest.mark.asyncio
async def test_an_agency_visa_case_starts_at_the_checklist(db_session, world):  # AC10
    async with client_for(world["counselor"].email) as c:
        r = await c.post(VISA, json={"application_id": str(world["app"].id), "status": "documentation", "checklist": ["Passport"]})
        assert r.status_code == 422 and r.json()["detail"] == "A visa case starts at the checklist stage"
        assert (await c.post(VISA, json={"application_id": str(world["app"].id), "checklist": ["Passport"]})).status_code == 201


@pytest.mark.asyncio
async def test_agency_visa_updates_follow_the_agency_rules(db_session, world):  # AC10, Review Focus 3
    case = await mk_case(db_session, world["app"], checklist=["Passport"])
    async with client_for(world["counselor"].email) as c:
        gate = await c.patch(f"{VISA}/{case.id}", json={"status": "documentation"})
        assert gate.status_code == 422 and "not yet verified: Passport" in gate.json()["detail"]
        await verified(db_session, world, "Passport")
        assert (await c.patch(f"{VISA}/{case.id}", json={"status": "interview_prep"})).status_code == 200  # a skip, as the agency may
        back = await c.patch(f"{VISA}/{case.id}", json={"status": "documentation"})
        assert back.status_code == 422 and back.json()["detail"] == "A visa case can only move forward"
        locked = await c.patch(f"{VISA}/{case.id}", json={"checklist": ["Passport", "Bank statement"]})
        assert locked.status_code == 422 and locked.json()["detail"] == "The checklist can only be changed at the checklist stage"
        refused = await c.patch(f"{VISA}/{case.id}", json={"decision": "approved"})
        assert refused.status_code == 422 and refused.json()["detail"] == "The visa decision is recorded by the agency"
    row = await case_of(db_session, world["app"])
    row.status, row.decision, row.decided_at = "decision", "approved", datetime.now(UTC)
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        decided = await c.patch(f"{VISA}/{case.id}", json={"tracking_reference": "TR-1"})
        assert decided.status_code == 409 and decided.json()["detail"] == "The visa decision is recorded, so this case can no longer be changed"
        checklist = (await c.get(f"/api/v1/workflows/overseas/applications/{world['app'].id}/visa-checklist")).json()
    assert checklist["locked_reason"] == "The visa decision is recorded, so this case can no longer be changed"


@pytest.mark.asyncio
async def test_a_direct_visa_case_keeps_todays_behavior(db_session, world):  # AC11
    case = await mk_case(db_session, world["direct_app"], status="documentation")
    async with client_for(world["counselor"].email) as c:
        assert (await c.patch(f"{VISA}/{case.id}", json={"status": "checklist"})).status_code == 200  # no forward-only rule outside agencies
        checklist = (await c.get(f"/api/v1/workflows/overseas/applications/{world['direct_app'].id}/visa-checklist")).json()
    assert checklist["locked_reason"] is None


@pytest.mark.asyncio
async def test_the_documents_queue_lists_agency_documents_of_a_no_login_student(db_session, world):  # AC12
    doc = await mk_doc(db_session, record=world["record"], application=world["app"])
    async with client_for(world["counselor"].email) as c:
        rows = (await c.get(PORTAL.format("counselor", "documents"))).json()["rows"]
        assert {"id": str(doc.id), "student": world["record"].full_name} in [{"id": str(r["id"]), "student": r["student"]} for r in rows]
        r = await c.patch(f"/api/v1/workflows/overseas/documents/{doc.id}/verify", json={"verification_status": "rejected", "reviewer_notes": "Blurred"})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_counselor_responses_carry_no_agency_contact_or_counseling_data(db_session, world):  # AC13
    email, phone = "private-agn023@example.local", "+910000023023"
    record = await mk_record(db_session, agent=world["master"], full_name="Contact Student", email=email, phone=phone)
    app = await mk_application(db_session, agent=world["master"], university=world["university"], record=record, status="offer")
    async with client_for(world["admin"].email) as c:
        assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(world["counselor"].id)})).status_code == 200
    async with client_for(world["counselor"].email) as c:
        bodies = [(await c.get(PORTAL.format("counselor", s))).text for s in ("dashboard", "students", "applications", "documents", "visa")]
        bodies.append((await c.get("/api/v1/lookups/overseas-applications", params={"q": "Contact"})).text)
        bodies.append((await c.get(f"/api/v1/workflows/overseas/applications/{app.id}/visa-checklist")).text)
    for body in bodies:
        assert email not in body and phone not in body
        assert "budget" not in body.lower() and "shortlist" not in body.lower()


@pytest.mark.asyncio
async def test_the_agency_detail_shows_the_counselor_name_only(db_session, world):  # AC14
    async with client_for(world["master"].email) as c:
        detail = (await c.get(f"{APPS}/{world['app'].id}")).json()["application"]
    assert detail["counselor_name"] == world["counselor"].full_name
    assert world["counselor"].email not in str(detail)
    other = await mk_application(db_session, agent=world["master"], university=world["university"], record=world["record"], status="enquiry")
    async with client_for(world["master"].email) as c:
        assert (await c.get(f"{APPS}/{other.id}")).json()["application"]["counselor_name"] is None
```

Before running, check the field names the verify body uses against `PATCH /overseas/documents/{id}/verify` in `workflows.py` (~L2120) and its schema. If they differ, use the real names and note it in the commit. Do the same for the lookup's `q` parameter (`api/lookups.py` ~L146).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `API_TEST "tests/test_agn_023_counselor_scope.py"`
Expected: FAIL. `enrolled` is allowed (200), the visa rules don't apply, `locked_reason` is a KeyError, the documents row is missing, and `counselor_name` is a KeyError.

- [ ] **Step 3: Refuse `enrolled` in `/advance` on an agency application**

In `apps/api/app/api/workflows.py`, add the constants next to the Task 1 constants:

```python
MASTER_ENROLLS = "Only the agency's Master confirms enrollment"  # AGN-023 (DEC-SCOPE-090 H4), DEC-SCOPE-054 E1
AGENCY_VISA_STARTS_AT_CHECKLIST = "A visa case starts at the checklist stage"
AGENCY_RECORDS_VISA_DECISION = "The visa decision is recorded by the agency"
```

In `advance_overseas_application`, directly after the `if item.status == WITHDRAWN:` check:

```python
    if item.agent_id is not None and payload.to_status == "enrolled":
        raise HTTPException(403, MASTER_ENROLLS)
```

- [ ] **Step 4: Apply the agency visa rules**

Extend the existing import to `from app.services.agent_visa import VISA_CASE_STAGES, VISA_DECIDED, VISA_DECISION_DISCLAIMER, VISA_ENROLLED, VISA_OFFER_NEEDED, update_case`. Also add `OFFER_STAGES_ON` to the `app.services.agent_applications` import.

In `create_visa_case`, directly after `application = await _assigned_application(db, user, payload.application_id)`:

```python
    if application.agent_id is not None:  # AGN-023 (DEC-SCOPE-090 H4): the agency's AGN-012 start rules, under the same lock order
        await db.refresh(application, with_for_update=True)
        if application.status == "enrolled":
            raise HTTPException(409, VISA_ENROLLED)
        if application.status not in OFFER_STAGES_ON:
            raise HTTPException(422, VISA_OFFER_NEEDED)
        if payload.status != "checklist":
            raise HTTPException(422, AGENCY_VISA_STARTS_AT_CHECKLIST)
```

In `update_visa`, directly after `await _require_bridged_visa_entitlement(...)`, insert the agency branch. The existing code below it becomes the non-agency path:

```python
    if application.agent_id is not None:
        return await _update_agency_visa(db, user, application, item, payload)
```

and add this helper above `update_visa`:

```python
async def _update_agency_visa(db: AsyncSession, user: User, application: OverseasApplication, case: VisaCase, payload: dict) -> dict:
    """AGN-023 (DEC-SCOPE-090 H4, spec §4): a counselor's change to an agency visa case goes through the agency's own rules
    (agent_visa.update_case: decided lock, forward only, checklist lock, checklist gate). Lock order matches the agency route:
    the application, then the case; the expected stage is the one read under that lock. The decision stays with the agency."""
    await db.refresh(application, with_for_update=True)
    await db.refresh(case, with_for_update=True)
    if application.status == "enrolled":
        raise HTTPException(409, VISA_ENROLLED)
    if "decision" in payload:
        raise HTTPException(422, AGENCY_RECORDS_VISA_DECISION)
    changes: dict = {"expected_stage": case.status}
    target = payload.get("status")
    if target is not None and target != case.status:
        if target not in VISA_CASE_STAGES:
            raise HTTPException(422, f"'{target}' is not a supported visa case stage -- must be one of {VISA_CASE_STAGES}.")
        changes["to_stage"] = target
    if "checklist" in payload:
        changes["checklist"] = payload["checklist"]
    if payload.get("appointment_date"):
        changes["appointment_date"] = date.fromisoformat(payload["appointment_date"])
    if case.decision is None and "tracking_reference" in payload:
        case.tracking_reference = payload["tracking_reference"]
    await update_case(db, case, changes)
    await _audit(db, user, "visa.update", "visa_case", case.id, payload)
    await db.commit()
    return {"id": case.id, "status": case.status}
```

`update_case` raises `409 VISA_DECIDED` first for a decided case, so the tracking reference is never written after a decision (`case.decision is None` keeps the write behind that refusal).

In `get_visa_checklist`, make both return dicts carry `locked_reason`. Compute it once, right after `case = await db.scalar(...)`:

```python
    # AGN-023 (DEC-SCOPE-090 H12): agency cases tell the counselor's screen why nothing can be changed any more.
    locked_reason = None
    if application.agent_id is not None:
        locked_reason = VISA_ENROLLED if application.status == "enrolled" else VISA_DECIDED if case is not None and case.decision is not None else None
```

Then add `"locked_reason": locked_reason` to the no-case dict and to the case dict.

- [ ] **Step 5: List agency documents in the counselor's queue**

In `apps/api/app/services/portal.py`, `section == "documents"` block, replace the query and row comprehension with:

```python
            docs = (
                (
                    await db.execute(
                        # AGN-023 (DEC-SCOPE-090 §4): outer joins, so a no-login agency student's documents are listed; still scoped to app_ids.
                        select(StudentDocument, func.coalesce(User.full_name, AgentStudent.full_name, "A student"))
                        .outerjoin(User, User.id == StudentDocument.student_id)
                        .outerjoin(AgentStudent, AgentStudent.id == StudentDocument.agent_student_id)
                        .where(StudentDocument.application_id.in_(app_ids))
                        .order_by(StudentDocument.updated_at.desc())
                    )
                ).all()
                if app_ids
                else []
            )
```

and in the `_payload(...)` rows argument use
`({"id": d.id, "student": name, "document": d.document_type, "status": d.verification_status, "notes": d.reviewer_notes} for d, name in docs)`.

- [ ] **Step 6: Add the counselor's name to the agency detail**

In `apps/api/app/services/agent_applications.py`, `detail()`, add to the returned dict, after `"enrollment_check": ...`:

```python
        # AGN-023 (DEC-SCOPE-090 H7): the EduSphere counselor's name only -- never their email or phone.
        "counselor_name": await db.scalar(select(User.full_name).where(User.id == found.counselor_id)) if found.counselor_id else None,
```

- [ ] **Step 7: Run the tests**

Run: `API_TEST "tests/test_agn_023_counselor_scope.py tests/test_agn_023_assign.py"`
Expected: PASS.

- [ ] **Step 8: Run the lite regression**

Run: `API_TEST "tests/test_agn_012_visa.py tests/test_agn_012_security.py tests/test_agn_012_unchanged.py tests/test_agn_012_concurrency.py tests/test_agn_013_enrollment.py tests/test_agn_008_read.py tests/test_agn_009_documents.py tests/test_visa_001_checklist.py tests/test_visa_002_interview_prep.py tests/test_visa_003_status.py tests/test_ovs_003_eligibility.py"`
Expected: PASS. If a file name doesn't exist, list `tests/test_agn_013_*`/`tests/test_agn_009_*` and use the real names. A visa test that compares the checklist response to an exact dict needs `"locked_reason": None` added: that is a change this spec approved (additive field). Change only such equality asserts.

- [ ] **Step 9: Commit**

```bash
git add apps/api/app/api/workflows.py apps/api/app/services/portal.py apps/api/app/services/agent_applications.py apps/api/tests/test_agn_023_counselor_scope.py
git commit -m "feat(agn-023): counselor on an agency application keeps to the agency rules; agency detail shows the counselor (AC09-AC14)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: List columns and server-side filters

**Files:**
- Create: `apps/api/app/services/application_filters.py`
- Modify: `apps/api/app/api/portal.py` (the `portal` route)
- Modify: `apps/api/app/services/portal.py`:
  - `section_payload` (~L1598)
  - `_operations` signature (~L835)
  - the shared application block (~L987-1033)
- Create: `apps/api/tests/test_agn_023_filters.py`

**Interfaces:**
- Consumes: `assign_world`, `ASSIGN`, `PORTAL` (Task 1).
- Produces:
  - `GET /api/v1/portal/overseas/{admin|counselor}/{students|applications}?agency=&counselor=`.
  - Rows gain:
    - `is_agency: bool` (admin and counselor).
    - `agency: str | None` (admin and counselor).
    - `counselor: str` and `counselor_id: str | None` (admin only).
    - `assign: id` (admin only).
  - Admin columns gain `{"key": "assign", "label": "", "type": "assign_counselor"}`.
  - The payload gains `filters: {"agency": str | None, "counselor": str | None, "agencies": [{"value", "label"}], "counselors"?: [{"value", "label"}]}`. `counselors` is present for the Admin only.
  - Python: `application_filters.ApplicationFilters`, `parse(db, user, section, agency, counselor)`, `apply(stmt, filters)`, `row_labels(db, apps)`, `payload_part(db, user, filters)`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/test_agn_023_filters.py`:

```python
"""AGN-023 AC16-AC18, AC13 shape -- Agency / Counsellor filters on the overseas Students and Applications lists (spec §3.3)."""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from app.models import OverseasApplication
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import mk_application
from tests.agn023_helpers import ASSIGN, PORTAL, assign_world


@pytest_asyncio.fixture
async def world(db_session):
    w = await assign_world(db_session)
    async with client_for(w["admin"].email) as c:
        assert (await c.put(ASSIGN.format(w["app"].id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    w["other_app"] = await mk_application(db_session, agent=w["other"]["master"], university=w["university"], record=await mk_record(db_session, agent=w["other"]["master"], full_name=f"Other {uniq()}"))
    return w


async def _ids(c, role, section="applications", **params):
    r = await c.get(PORTAL.format(role, section), params=params)
    assert r.status_code == 200, r.text
    return r.json(), {str(row["id"]) for row in r.json()["rows"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["applications", "students"])
async def test_admin_filters_by_agency_and_counselor(world, section):  # AC16
    a, direct, other = str(world["app"].id), str(world["direct_app"].id), str(world["other_app"].id)
    async with client_for(world["admin"].email) as c:
        _, ids = await _ids(c, "admin", section, agency=str(world["org"].id))
        assert a in ids and other not in ids and direct not in ids
        _, ids = await _ids(c, "admin", section, agency="any")
        assert {a, other} <= ids and direct not in ids
        _, ids = await _ids(c, "admin", section, agency="none")
        assert direct in ids and a not in ids
        _, ids = await _ids(c, "admin", section, counselor=str(world["counselor"].id))
        assert a in ids and other not in ids
        _, ids = await _ids(c, "admin", section, agency="any", counselor="none")
        assert other in ids and a not in ids and direct not in ids


@pytest.mark.asyncio
async def test_admin_rows_and_options(world):  # AC15 data, AC16
    async with client_for(world["admin"].email) as c:
        data, _ = await _ids(c, "admin", agency=str(world["org"].id))
    row = next(r for r in data["rows"] if str(r["id"]) == str(world["app"].id))
    assert (row["is_agency"], row["agency"], row["counselor"], row["counselor_id"]) == (True, world["org"].name, world["counselor"].full_name, str(world["counselor"].id))
    assert {"key": "assign", "label": "", "type": "assign_counselor"} in data["columns"]
    assert data["filters"]["agency"] == str(world["org"].id) and data["filters"]["counselor"] is None
    assert {"value": str(world["org"].id), "label": world["org"].name} in data["filters"]["agencies"]
    labels = {o["value"]: o["label"] for o in data["filters"]["counselors"]}
    assert labels[str(world["inactive"].id)] == f"{world['inactive'].full_name} (inactive)"
    assert str(world["it_counselor"].id) not in labels


@pytest.mark.asyncio
async def test_a_counselor_filters_by_agency_within_their_own_caseload(world):  # AC17
    async with client_for(world["counselor"].email) as c:
        data, ids = await _ids(c, "counselor", agency=str(world["org"].id))
        assert ids == {str(world["app"].id)}
        assert [o["value"] for o in data["filters"]["agencies"]] == [str(world["org"].id)]  # never the other agency
        assert "counselors" not in data["filters"]
        row = data["rows"][0]
        assert (row["is_agency"], row["agency"]) == (True, world["org"].name) and "counselor_id" not in row
        _, ids = await _ids(c, "counselor", agency=str(world["other"]["org"].id))
        assert ids == set()
        r = await c.get(PORTAL.format("counselor", "applications"), params={"counselor": str(world["counselor"].id)})
    assert r.status_code == 422 and r.json()["detail"] == "Filter not available"


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "section", "params", "detail"), [
    ("admin", "applications", {"agency": "garbage"}, "Unknown filter value"),
    ("admin", "applications", {"agency": str(uuid.uuid4())}, "Unknown filter value"),
    ("admin", "applications", {"counselor": "any"}, "Unknown filter value"),
    ("admin", "dashboard", {"agency": "any"}, "Filter not available"),
    ("admin", "documents", {"counselor": "none"}, "Filter not available"),
])
async def test_bad_filters_are_refused(world, role, section, params, detail):  # AC18
    async with client_for(world["admin"].email) as c:
        r = await c.get(PORTAL.format(role, section), params=params)
    assert r.status_code == 422 and r.json()["detail"] == detail


@pytest.mark.asyncio
async def test_a_counselor_id_filter_must_name_an_overseas_counselor(world):  # AC18
    async with client_for(world["admin"].email) as c:
        r = await c.get(PORTAL.format("admin", "applications"), params={"counselor": str(world["it_counselor"].id)})
    assert r.status_code == 422 and r.json()["detail"] == "Unknown filter value"


@pytest.mark.asyncio
async def test_a_university_rep_gets_no_filters(db_session, world):  # AC18
    rep = await mk_user(db_session, role="university_rep", profile={"university_id": str(world["university"].id)})
    async with client_for(rep.email) as c:
        r = await c.get(PORTAL.format("university", "applications"), params={"agency": "any"})
        assert r.status_code == 422 and r.json()["detail"] == "Filter not available"
        plain = (await c.get(PORTAL.format("university", "applications"))).json()
    assert "filters" not in plain and all("counselor" not in row and "agency" not in row for row in plain["rows"])


@pytest.mark.asyncio
async def test_filters_apply_before_the_500_row_cap(db_session, world):  # AC16, Review Focus 5
    ctx = await mk_active_org(db_session, name=f"Old Agency {uniq()}")
    old = await mk_application(db_session, agent=ctx["master"], university=world["university"], record=await mk_record(db_session, agent=ctx["master"], full_name=f"Old {uniq()}"))
    old.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
    student = await mk_user(db_session, role="overseas_student")
    db_session.add_all(OverseasApplication(student_id=student.id, university_id=world["university"].id, status="enquiry", intake="Fall 2027") for _ in range(501))
    await db_session.commit()
    async with client_for(world["admin"].email) as c:
        _, unfiltered = await _ids(c, "admin")
        _, filtered = await _ids(c, "admin", agency=str(ctx["org"].id))
    assert str(old.id) not in unfiltered
    assert filtered == {str(old.id)}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `API_TEST "tests/test_agn_023_filters.py"`
Expected: FAIL. Query parameters are ignored, so the expected rows differ, there is no `filters` key, and no `422` is returned.

- [ ] **Step 3: Write the filters service**

`apps/api/app/services/application_filters.py`:

```python
"""AGN-023 (DEC-SCOPE-090 H11, spec §3.3): Agency / Counsellor filters on the overseas Students and Applications lists.

The Overseas Admin filters by agency and by counselor; a counselor by agency only. Filters only narrow the caller's existing scope and
are applied in SQL before the list's row cap. A filter value that is malformed, unknown, or not available to the caller is a 422 --
never silently ignored."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrg, AgentOrgMember, OverseasApplication, User

FILTER_SECTIONS = frozenset({"students", "applications"})
NOT_AVAILABLE = "Filter not available"
UNKNOWN_VALUE = "Unknown filter value"


@dataclass(frozen=True)
class ApplicationFilters:
    agency: UUID | str | None = None  # an agency org id, "any" or "none"
    counselor: UUID | str | None = None  # an overseas counselor id or "none"


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(422, UNKNOWN_VALUE) from None


async def parse(db: AsyncSession, user: User, section: str, agency: str | None, counselor: str | None) -> ApplicationFilters:
    if agency is None and counselor is None:
        return ApplicationFilters()
    available = user.division == "overseas" and user.role in {"overseas_admin", "counselor"} and section in FILTER_SECTIONS
    if not available or (counselor is not None and user.role != "overseas_admin"):
        raise HTTPException(422, NOT_AVAILABLE)
    parsed_agency: UUID | str | None = None
    if agency is not None:
        if agency in {"any", "none"}:
            parsed_agency = agency
        else:
            parsed_agency = _uuid(agency)
            if await db.get(AgentOrg, parsed_agency) is None:
                raise HTTPException(422, UNKNOWN_VALUE)
    parsed_counselor: UUID | str | None = None
    if counselor is not None:
        if counselor == "none":
            parsed_counselor = counselor
        else:
            parsed_counselor = _uuid(counselor)
            target = await db.get(User, parsed_counselor)
            if target is None or target.role != "counselor" or target.division != "overseas":
                raise HTTPException(422, UNKNOWN_VALUE)
    return ApplicationFilters(parsed_agency, parsed_counselor)


def apply(stmt: Select, filters: ApplicationFilters) -> Select:
    if filters.agency == "any":
        stmt = stmt.where(OverseasApplication.agent_id.is_not(None))
    elif filters.agency == "none":
        stmt = stmt.where(OverseasApplication.agent_id.is_(None))
    elif filters.agency is not None:
        stmt = stmt.where(OverseasApplication.agent_id.in_(select(AgentOrgMember.user_id).where(AgentOrgMember.org_id == filters.agency)))
    if filters.counselor == "none":
        stmt = stmt.where(OverseasApplication.counselor_id.is_(None))
    elif filters.counselor is not None:
        stmt = stmt.where(OverseasApplication.counselor_id == filters.counselor)
    return stmt


async def row_labels(db: AsyncSession, apps: list[OverseasApplication]) -> tuple[dict, dict]:
    """({agent user id: agency name}, {counselor id: counselor name}) for the listed applications -- two bounded lookups."""
    agent_ids = {a.agent_id for a in apps if a.agent_id is not None}
    counselor_ids = {a.counselor_id for a in apps if a.counselor_id is not None}
    agencies = dict((await db.execute(select(AgentOrgMember.user_id, AgentOrg.name).join(AgentOrg, AgentOrg.id == AgentOrgMember.org_id).where(AgentOrgMember.user_id.in_(agent_ids)))).all()) if agent_ids else {}
    counselors = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(counselor_ids)))).all()) if counselor_ids else {}
    return agencies, counselors


def _value(value: UUID | str | None) -> str | None:
    return None if value is None else str(value)


async def payload_part(db: AsyncSession, user: User, filters: ApplicationFilters) -> dict:
    """The applied values plus the dropdown options. A counselor's agency options are only the agencies on their own applications, so no
    agency outside their caseload is named; the Admin's counselor options include inactive counselors (past assignments name them)."""
    orgs = select(AgentOrg.id, AgentOrg.name).join(AgentOrgMember, AgentOrgMember.org_id == AgentOrg.id).join(OverseasApplication, OverseasApplication.agent_id == AgentOrgMember.user_id)
    if user.role == "counselor":
        orgs = orgs.where(OverseasApplication.counselor_id == user.id)
    part: dict = {
        "agency": _value(filters.agency),
        "counselor": _value(filters.counselor),
        "agencies": [{"value": str(i), "label": n} for i, n in (await db.execute(orgs.distinct().order_by(AgentOrg.name))).all()],
    }
    if user.role == "overseas_admin":
        rows = (await db.execute(select(User.id, User.full_name, User.active).where(User.role == "counselor", User.division == "overseas").order_by(User.full_name))).all()
        part["counselors"] = [{"value": str(i), "label": n if active else f"{n} (inactive)"} for i, n, active in rows]
    return part
```

- [ ] **Step 4: Wire the route**

In `apps/api/app/api/portal.py`, add `from app.services import application_filters` and change the route:

```python
@router.get("/{division}/{role}/{section}")
async def portal(
    division: str, role: str, section: str, agency: str | None = None, counselor: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
```

and, directly before `payload = await section_payload(db, user, section)`:

```python
    # AGN-023 (DEC-SCOPE-090 H11): optional list filters; a filter on the wrong section or role is a 422, never ignored.
    filters = await application_filters.parse(db, user, section, agency, counselor)
```

then call `payload = await section_payload(db, user, section, filters=filters)`.

- [ ] **Step 5: Thread the filters and build the columns**

In `apps/api/app/services/portal.py`:
- Add `from app.services import application_filters` and `from app.services.application_filters import ApplicationFilters`.
- Change `async def section_payload(db, user, section)` to `async def section_payload(db: AsyncSession, user: User, section: str, *, filters: ApplicationFilters | None = None) -> dict | None:`. In its `else:` branch, call `result = await _operations(db, user, section, filters=filters)`.
- Change `async def _operations(db: AsyncSession, user: User, section: str):` to `async def _operations(db: AsyncSession, user: User, section: str, *, filters: ApplicationFilters | None = None):`.

In the `if user.role in {"counselor", "university_rep", "overseas_admin"}:` block, directly before `applications = owned(...)`:

```python
        if filters is not None:  # AGN-023 (DEC-SCOPE-090 H11): SQL-side, before the row cap; parse() admits only students/applications
            stmt = application_filters.apply(stmt, filters)
```

Replace the `if section in {"students", "applications", "admission-updates", "offer-letters"}:` return with:

```python
        if section in {"students", "applications", "admission-updates", "offer-letters"}:
            columns = [("id", "reference"), ("student", "Student"), ("university", "University"), ("reference", "Reference"), ("status", "Status"), ("next_action", "Next action")]
            rows = [{"id": a.id, "student_id": s.id, "student": s.full_name, "university": u.name, "reference": a.application_reference, "status": a.status, "next_action": a.next_action} for a, u, s in applications]
            if user.role in {"overseas_admin", "counselor"}:  # AGN-023 (DEC-SCOPE-090 §3.3); university_rep unchanged
                agencies, counselors = await application_filters.row_labels(db, [a for a, _, _ in applications])
                for row, (a, _, _) in zip(rows, applications, strict=True):
                    row |= {"is_agency": a.agent_id is not None, "agency": agencies.get(a.agent_id)}
                    if user.role == "overseas_admin":
                        row |= {"counselor": counselors.get(a.counselor_id) or "Not assigned", "counselor_id": str(a.counselor_id) if a.counselor_id else None, "assign": a.id}
                columns.insert(2, ("agency", "Agency"))
                if user.role == "overseas_admin":
                    columns.insert(4, ("counselor", "EduSphere counsellor"))
                    columns.append(("assign", "", "assign_counselor"))
            payload = _payload("Application Tracking", "Assigned applications and next actions.", columns, rows)
            if user.role in {"overseas_admin", "counselor"}:
                payload["filters"] = await application_filters.payload_part(db, user, filters or ApplicationFilters())
            return payload
```

- [ ] **Step 6: Run the tests**

Run: `API_TEST "tests/test_agn_023_filters.py tests/test_agn_023_counselor_scope.py tests/test_agn_023_assign.py"`
Expected: PASS.

- [ ] **Step 7: Run the lite regression for the portal**

Run: `API_TEST "tests/test_agn_008_read.py tests/test_agn_003_matrix.py tests/test_enh_031_lookups_students.py"` and `grep -ln "portal/overseas/\(admin\|counselor\|university\)" apps/api/tests/*.py`, then run every file that grep lists.
Expected: PASS. A test that compares a whole row or the column list with `==` needs the new keys added. That is approved by spec §3.3; change only such equality asserts and list them in the commit body.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/services/application_filters.py apps/api/app/api/portal.py apps/api/app/services/portal.py apps/api/tests/test_agn_023_filters.py
git commit -m "feat(agn-023): Agency/Counsellor columns and server-side list filters (AC16-AC18)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Filter bar with URL state

**Files:**
- Modify: `apps/web/lib/types.ts` (`PortalPayload`)
- Modify: `apps/web/app/overseas/admin/[section]/page.tsx`, `apps/web/app/overseas/counselor/[section]/page.tsx`
- Modify: `apps/web/components/PortalPage.tsx`
- Modify: `apps/web/components/PortalSection.tsx`
- Create: `apps/web/components/ApplicationFilterBar.tsx`
- Create: `apps/web/tests/components/ApplicationFilterBar.test.tsx`

**Interfaces:**
- Consumes: the payload `filters` from Task 3.
- Produces:
  - `PortalPayload.filters?: ApplicationFilterState`.
  - `ApplicationFilterBar({filters, error}: {filters: ApplicationFilterState; error?: string | null})`.
  - `PortalPage({..., query?: Record<string, string | string[] | undefined>})`.
  - `PortalSection({data, lead, emptyText})`.

- [ ] **Step 1: Write the failing test**

`apps/web/tests/components/ApplicationFilterBar.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationFilterBar from "@/components/ApplicationFilterBar";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/overseas/admin/applications" }));

afterEach(() => {
  cleanup();
  push.mockReset();
});

const ADMIN = {
  agency: null,
  counselor: null,
  agencies: [{ value: "org1", label: "Demo Global Education" }],
  counselors: [{ value: "c1", label: "Asha Rao" }, { value: "c2", label: "Old Hand (inactive)" }],
};

describe("ApplicationFilterBar", () => {
  it("puts the chosen agency in the URL and keeps the counselor", () => {
    render(<ApplicationFilterBar filters={{ ...ADMIN, counselor: "none" }} />);
    fireEvent.change(screen.getByLabelText("Agency"), { target: { value: "org1" } });
    expect(push).toHaveBeenCalledWith("/overseas/admin/applications?agency=org1&counselor=none");
  });

  it("offers All, Any agency, Not from an agency and each agency", () => {
    render(<ApplicationFilterBar filters={ADMIN} />);
    const options = Array.from((screen.getByLabelText("Agency") as HTMLSelectElement).options).map((o) => o.textContent);
    expect(options).toEqual(["All", "Any agency", "Not from an agency", "Demo Global Education"]);
    const counselors = Array.from((screen.getByLabelText("Counsellor") as HTMLSelectElement).options).map((o) => o.textContent);
    expect(counselors).toEqual(["All", "Not assigned", "Asha Rao", "Old Hand (inactive)"]);
  });

  it("choosing All removes that filter from the URL", () => {
    render(<ApplicationFilterBar filters={{ ...ADMIN, agency: "any" }} />);
    fireEvent.change(screen.getByLabelText("Agency"), { target: { value: "" } });
    expect(push).toHaveBeenCalledWith("/overseas/admin/applications");
  });

  it("has no Counsellor filter for a counselor, and Clear filters only when one is applied", () => {
    const { rerender } = render(<ApplicationFilterBar filters={{ agency: null, counselor: null, agencies: ADMIN.agencies }} />);
    expect(screen.queryByLabelText("Counsellor")).toBeNull();
    expect(screen.queryByRole("link", { name: "Clear filters" })).toBeNull();
    rerender(<ApplicationFilterBar filters={{ agency: "org1", counselor: null, agencies: ADMIN.agencies }} />);
    expect(screen.getByRole("link", { name: "Clear filters" })).toHaveAttribute("href", "/overseas/admin/applications");
  });

  it("announces a refused filter", () => {
    render(<ApplicationFilterBar filters={ADMIN} error="Unknown filter value" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Unknown filter value -- showing all applications.");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `WEB_TEST "npx vitest run tests/components/ApplicationFilterBar.test.tsx"`
Expected: FAIL with "Failed to resolve import @/components/ApplicationFilterBar".

- [ ] **Step 3: Add the type**

In `apps/web/lib/types.ts`, change `PortalPayload` and add the filter types above it:

```ts
// AGN-023 (DEC-SCOPE-090 H11): the overseas Students/Applications list filters; `counselors` is the Overseas Admin's only.
export type FilterOption = { value: string; label: string };
export type ApplicationFilterState = { agency: string | null; counselor: string | null; agencies: FilterOption[]; counselors?: FilterOption[] };
export type PortalPayload = {
  title:string; subtitle:string; metrics:{label:string;value:string|number}[];
  actions:{label:string;href:string}[]; columns:{key:string;label:string;type?:string}[];
  rows:Record<string, unknown>[]; panels:{title:string;items:string[]}[];
  filters?: ApplicationFilterState;
};
```

- [ ] **Step 4: Write the component**

`apps/web/components/ApplicationFilterBar.tsx`:

```tsx
"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import type { ApplicationFilterState } from "@/lib/types";

// AGN-023 (DEC-SCOPE-090 H11): Agency (Admin and counselor) and Counsellor (Admin only) filters. The values live in the URL, so a
// filtered list survives a reload and can be shared; the server applies them (before its row cap) and refuses a bad value.
export default function ApplicationFilterBar({ filters, error }: { filters: ApplicationFilterState; error?: string | null }) {
  const router = useRouter();
  const pathname = usePathname();

  function go(next: { agency: string | null; counselor: string | null }) {
    const params = new URLSearchParams();
    if (next.agency) params.set("agency", next.agency);
    if (next.counselor) params.set("counselor", next.counselor);
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  const applied = Boolean(filters.agency || filters.counselor);
  return (
    <form className="form filter-bar" aria-label="Filter applications" onSubmit={(event) => event.preventDefault()} style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end", marginBottom: 12 }}>
      <div className="field">
        <label htmlFor="filter-agency">Agency</label>
        <select id="filter-agency" value={filters.agency ?? ""} onChange={(event) => go({ agency: event.target.value || null, counselor: filters.counselor })}>
          <option value="">All</option>
          <option value="any">Any agency</option>
          <option value="none">Not from an agency</option>
          {filters.agencies.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
      {filters.counselors && (
        <div className="field">
          <label htmlFor="filter-counselor">Counsellor</label>
          <select id="filter-counselor" value={filters.counselor ?? ""} onChange={(event) => go({ agency: filters.agency, counselor: event.target.value || null })}>
            <option value="">All</option>
            <option value="none">Not assigned</option>
            {filters.counselors.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
      )}
      {applied && <Link href={pathname}>Clear filters</Link>}
      {error && <p className="form-error" role="alert">{error} -- showing all applications.</p>}
    </form>
  );
}
```

- [ ] **Step 5: Give PortalSection an empty-state override**

In `apps/web/components/PortalSection.tsx`, change the signature to
`export default function PortalSection({data, lead, emptyText}: {data: PortalPayload; lead?: React.ReactNode; emptyText?: string})`.
Replace the empty `<div className="empty">…</div>` with:

```tsx
emptyText ? <div className="empty"><h3>{emptyText}</h3></div> : <div className="empty"><h3>No records yet</h3><p>When this workflow has data, permitted records will appear here. Use the relevant action above to begin.</p></div>
```

- [ ] **Step 6: Pass the URL query through**

Both route files (`apps/web/app/overseas/admin/[section]/page.tsx` and `apps/web/app/overseas/counselor/[section]/page.tsx`) become, with `role` set to `"admin"` or `"counselor"` to match the file:

```tsx
import PortalPage from "@/components/PortalPage";
export default async function Page({params,searchParams}:{params:Promise<{section:string}>;searchParams:Promise<Record<string,string|string[]|undefined>>}){const{section}=await params;return <PortalPage division="overseas" role="admin" section={section} query={await searchParams}/>}
```

In `apps/web/components/PortalPage.tsx`:
- Add `import ApplicationFilterBar from "./ApplicationFilterBar";` to the import line.
- Change the signature to `({division,role,section,query}:{division:"it"|"overseas";role:string;section:string;query?:Record<string,string|string[]|undefined>})`.
- Directly before `let user:User;`, add:

```tsx
// AGN-023 (DEC-SCOPE-090 H11): only agency/counselor travel to the API; a refused filter (422) falls back to the unfiltered list with
// the message, instead of the access-unavailable card.
const filterParams=new URLSearchParams(Object.entries(query||{}).filter((e):e is [string,string]=>(e[0]==="agency"||e[0]==="counselor")&&typeof e[1]==="string"));const filterQuery=filterParams.toString();let filterError:string|null=null;
const portalUrl=`/api/v1/portal/${division}/${role}/${section}`;
```

In the `Promise.all`, replace `serverApi<PortalPayload>(\`/api/v1/portal/${division}/${role}/${section}\`).catch((e)=>{…})` with:

```tsx
serverApi<PortalPayload>(filterQuery?`${portalUrl}?${filterQuery}`:portalUrl).catch((e)=>{if(filterQuery&&e instanceof ApiError&&e.status===422){filterError=e.message;return serverApi<PortalPayload>(portalUrl)}if((agentApplications||agentDocuments||agentTasks||agentNotifications||agentPerformance)&&e instanceof ApiError&&e.status===404)return null;throw e})
```

Finally, in the `main` chain, put this immediately before the final `:<PortalSection data={data}/>;`:

```tsx
// AGN-023 (DEC-SCOPE-090 H11): the overseas Admin's and counselor's Students/Applications lists lead with the filter bar.
:data.filters&&(key==="overseas/admin"||key==="overseas/counselor")?<PortalSection data={data} lead={<ApplicationFilterBar filters={data.filters} error={filterError}/>} emptyText={data.filters.agency||data.filters.counselor?"No applications match these filters":undefined}/>
```

- [ ] **Step 7: Run the tests and the type check**

Run: `WEB_TEST "npx vitest run tests/components/ApplicationFilterBar.test.tsx && npx tsc --noEmit && npx eslint components/ApplicationFilterBar.tsx components/PortalPage.tsx components/PortalSection.tsx 'app/overseas/admin/[section]/page.tsx' 'app/overseas/counselor/[section]/page.tsx'"`
Expected: PASS. There must be no type or lint errors. If `ApiError.message` is not the API `detail`, read `apps/web/lib/api.ts` `serverApi` and pass the detail it stores.

- [ ] **Step 8: Commit**

```bash
git add apps/web/lib/types.ts apps/web/components/ApplicationFilterBar.tsx apps/web/components/PortalSection.tsx apps/web/components/PortalPage.tsx "apps/web/app/overseas/admin/[section]/page.tsx" "apps/web/app/overseas/counselor/[section]/page.tsx" apps/web/tests/components/ApplicationFilterBar.test.tsx
git commit -m "feat(agn-023): agency/counsellor filter bar with URL state (AC19)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Admin assign control in the table

**Files:**
- Create: `apps/web/components/AssignCounselorButton.tsx`
- Modify: `apps/web/components/DataTable.tsx` (`renderCell`)
- Create: `apps/web/tests/components/AssignCounselorButton.test.tsx`

**Interfaces:**
- Consumes: the row keys `id`, `counselor`, `counselor_id` and the column type `assign_counselor` (Task 3); `PUT …/counselor` (Task 1); `GET /api/v1/admin/users?role=counselor`, which returns `[{id, name, division, active, …}]`.
- Produces: `AssignCounselorButton({applicationId, currentId}: {applicationId: string; currentId: string | null})`.

- [ ] **Step 1: Write the failing test**

`apps/web/tests/components/AssignCounselorButton.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AssignCounselorButton from "@/components/AssignCounselorButton";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body });
const USERS = [
  { id: "c1", name: "Asha Rao", division: "overseas", active: true },
  { id: "c2", name: "Old Hand", division: "overseas", active: false },
  { id: "c3", name: "IT Person", division: "it", active: true },
];

function stub(put: () => Promise<unknown>) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method === "PUT" ? put() : json(200, USERS)));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("AssignCounselorButton", () => {
  it("lists active overseas counselors only and assigns one", async () => {
    const fetchMock = stub(() => json(200, { id: "a1", counselor_id: "c1", counselor_name: "Asha Rao", changed: true }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    const select = (await screen.findByLabelText("EduSphere counsellor")) as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual(["Choose…", "Asha Rao"]);
    fireEvent.change(select, { target: { value: "c1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Asha Rao assigned.");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/workflows/overseas/applications/a1/counselor", expect.objectContaining({ method: "PUT", body: JSON.stringify({ counselor_id: "c1" }) }));
    expect(refresh).toHaveBeenCalled();
  });

  it("reads Change counsellor when one is set, with no clear option", async () => {
    stub(() => json(200, {}));
    render(<AssignCounselorButton applicationId="a1" currentId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: "Change counsellor" }));
    const select = (await screen.findByLabelText("EduSphere counsellor")) as HTMLSelectElement;
    expect(select.value).toBe("c1");
    expect(Array.from(select.options).some((o) => o.value === "" && o.textContent !== "Choose…")).toBe(false);
  });

  it("shows the API's refusal", async () => {
    stub(() => json(409, { detail: "This application is closed" }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    fireEvent.change(await screen.findByLabelText("EduSphere counsellor"), { target: { value: "c1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This application is closed");
    expect(refresh).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `WEB_TEST "npx vitest run tests/components/AssignCounselorButton.test.tsx"`
Expected: FAIL. The module is not found.

- [ ] **Step 3: Write the component**

`apps/web/components/AssignCounselorButton.tsx`:

```tsx
"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { sendJson } from "@/lib/apiErrors";

type Counselor = { id: string; name: string; division: string; active: boolean };

// AGN-023 (DEC-SCOPE-090 §3.1, §6): the Overseas Admin assigns or swaps an application's EduSphere counselor. Swap only (H8): there
// is no "none" choice. The picker lists active overseas counselors; the server re-checks every rule.
export default function AssignCounselorButton({ applicationId, currentId }: { applicationId: string; currentId: string | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [counselors, setCounselors] = useState<Counselor[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const label = currentId ? "Change counsellor" : "Assign counsellor";
  const selectId = `assign-counselor-${applicationId}`;

  function start() {
    setOpen(true);
    setMessage(null);
    fetch("/api/v1/admin/users?role=counselor")
      .then((res) => (res.ok ? res.json() : []))
      .then((users: Counselor[]) => setCounselors(users.filter((u) => u.active && u.division === "overseas")))
      .catch(() => setCounselors([]));
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const counselorId = String(new FormData(event.currentTarget).get("counselor_id") || "");
    if (!counselorId) return;
    setBusy(true);
    const result = await sendJson(`/api/v1/workflows/overseas/applications/${applicationId}/counselor`, "PUT", { counselor_id: counselorId });
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true });
      return;
    }
    const name = counselors?.find((c) => c.id === counselorId)?.name ?? "Counsellor";
    setMessage({ text: `${name} assigned.`, failed: false });
    setOpen(false);
    router.refresh();
  }

  return (
    <div>
      {!open ? (
        <button type="button" className="btn small secondary" onClick={start}>{label}</button>
      ) : (
        <form className="form" onSubmit={save} aria-label={label}>
          <div className="field">
            <label htmlFor={selectId}>EduSphere counsellor</label>
            {counselors === null ? (
              <p className="muted">Loading counsellors…</p>
            ) : (
              <select id={selectId} name="counselor_id" defaultValue={currentId ?? ""} required>
                <option value="" disabled>Choose…</option>
                {counselors.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            )}
          </div>
          <button className="btn small" disabled={busy || counselors === null}>{busy ? "Saving…" : "Save"}</button>{" "}
          <button type="button" className="btn small secondary" onClick={() => setOpen(false)}>Cancel</button>
        </form>
      )}
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"}>{message.text}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Render it from the table**

In `apps/web/components/DataTable.tsx`, add `import AssignCounselorButton from "./AssignCounselorButton";` and, at the top of `renderCell` (before the `join` branch):

```tsx
  // AGN-023 (DEC-SCOPE-090 §6): the Overseas Admin's assign/change control, declared by the server like `join`.
  if (column.type === "assign_counselor") {
    return <AssignCounselorButton applicationId={String(row.id)} currentId={(row.counselor_id as string | null) ?? null} />;
  }
```

- [ ] **Step 5: Run the tests**

Run: `WEB_TEST "npx vitest run tests/components/AssignCounselorButton.test.tsx tests/components/ApplicationFilterBar.test.tsx && npx tsc --noEmit && npx eslint components/AssignCounselorButton.tsx components/DataTable.tsx"`
Expected: PASS. Then run the existing DataTable tests: `WEB_TEST "npx vitest run tests/components -t DataTable"`. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/AssignCounselorButton.tsx apps/web/components/DataTable.tsx apps/web/tests/components/AssignCounselorButton.test.tsx
git commit -m "feat(agn-023): Assign/Change counsellor control on the Admin application list (AC15)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Counselor screens offer only what is allowed; agency detail line

**Files:**
- Modify: `apps/web/components/CounselorEvaluationPanel.tsx`
- Modify: `apps/web/components/CounselorVisaPanel.tsx`
- Modify: `apps/web/components/AgentApplicationDetail.tsx` (the `<dl>` ending ~L143)
- Modify: `apps/web/lib/agentApplications.ts` (`AgentApplicationDetail` type, ~L131)
- Create: `apps/web/tests/components/CounselorAgencyLimits.test.tsx`
- Modify: `apps/web/tests/components/AgentApplicationDetail.test.tsx` (add one case)

**Interfaces:**
- Consumes: the row `is_agency` (Task 3); `visa-checklist.locked_reason` and the detail `counselor_name` (Task 2).

- [ ] **Step 1: Write the failing tests**

`apps/web/tests/components/CounselorAgencyLimits.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorEvaluationPanel from "@/components/CounselorEvaluationPanel";
import CounselorVisaPanel from "@/components/CounselorVisaPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: async () => body });
const ROWS = [
  { id: "agency1", student: "Priya", university: "U1", reference: null, status: "status_tracking", next_action: null, is_agency: true },
  { id: "direct1", student: "Ravi", university: "U1", reference: null, status: "status_tracking", next_action: null, is_agency: false },
];

describe("counselor limits on agency applications (H12)", () => {
  it("never offers Enrolled on an agency application, and says why", async () => {  // AC20
    vi.stubGlobal("fetch", vi.fn(() => json({ rows: ROWS })));
    render(<CounselorEvaluationPanel />);
    const agency = (await screen.findByRole("heading", { name: "Priya" })).closest(".card") as HTMLElement;
    expect(within(agency).getByText("Enrollment is confirmed by the agency.")).toBeInTheDocument();
    expect(within(agency).queryByRole("button", { name: "Advance stage" })).toBeNull();
    const direct = screen.getByRole("heading", { name: "Ravi" }).closest(".card") as HTMLElement;
    fireEvent.click(within(direct).getByRole("button", { name: "Advance stage" }));
    expect(Array.from((within(direct).getByLabelText("Advance to") as HTMLSelectElement).options).map((o) => o.value)).toEqual(["enrolled"]);
  });

  it("offers no visa stage once the agency case is locked, and shows the reason", async () => {  // AC21
    const locked = "The visa decision is recorded, so this case can no longer be changed";
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/counselor/applications")) return json({ rows: [ROWS[0]] });
      if (url.includes("/visa-checklist")) return json({ exists: true, id: "v1", status: "decision", checklist: [], locked_reason: locked });
      return json({ exists: true, status: "decision", appointment_date: null, tracking_reference: null, disclaimer: "" });
    }));
    render(<CounselorVisaPanel />);
    const card = (await screen.findByRole("heading", { name: "Priya" })).closest(".card") as HTMLElement;
    expect(await within(card).findByText(locked)).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: /^Advance to/ })).toBeNull();
  });

  it("offers only later visa stages on an open agency case", async () => {  // AC21
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/counselor/applications")) return json({ rows: [ROWS[0]] });
      if (url.includes("/visa-checklist")) return json({ exists: true, id: "v1", status: "interview_prep", checklist: [], locked_reason: null });
      return json({ exists: true, status: "interview_prep", appointment_date: null, tracking_reference: null, disclaimer: "" });
    }));
    render(<CounselorVisaPanel />);
    const card = (await screen.findByRole("heading", { name: "Priya" })).closest(".card") as HTMLElement;
    const buttons = await within(card).findAllByRole("button", { name: /^Advance to/ });
    expect(buttons.map((b) => b.textContent)).toEqual(["Advance to Tracking", "Advance to Decision"]);
  });
});
```

In `apps/web/tests/components/AgentApplicationDetail.test.tsx`, add one `it` inside the main `describe`. It should reuse that file's existing detail fixture and render helper: read the top of the file to learn their names, and if no shared helper exists, use the same pattern as the first test in the file. The case renders the fixture with `counselor_name: "Asha Rao"`, then asserts `screen.getByText("EduSphere counsellor")` and `screen.getByText("Asha Rao")`. It renders again with `counselor_name: null` and asserts `screen.getByText("Not assigned yet")`. Every existing fixture object of type `AgentApplicationDetail` in that file also gets `counselor_name: null`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `WEB_TEST "npx vitest run tests/components/CounselorAgencyLimits.test.tsx tests/components/AgentApplicationDetail.test.tsx"`
Expected: FAIL. The agency card still offers **Advance stage** with Enrolled, the locked reason doesn't render, and the counselor line is missing.

- [ ] **Step 3: Limit the stage list**

In `apps/web/components/CounselorEvaluationPanel.tsx`:
- Extend the row type to `type ApplicationRow = { id: string; student: string; university: string; reference: string | null; status: string; next_action: string | null; is_agency?: boolean };`.
- In the `rows.map`, replace `const nextStages = STAGES.slice(currentIndex + 1);` with:

```tsx
          // AGN-023 (DEC-SCOPE-090 H12): an agency application is enrolled by the agency's Master only (DEC-SCOPE-054); not offered here.
          const nextStages = STAGES.slice(currentIndex + 1).filter((stage) => !(row.is_agency && stage === "enrolled"));
```

- Directly after `{row.next_action && <p …>{row.next_action}</p>}`, add:

```tsx
              {row.is_agency && <p className="muted" style={{ fontSize: 13 }}>Enrollment is confirmed by the agency.</p>}
```

For an agency row at `status_tracking`, the list is now empty, so the existing "No further stage to advance to." branch renders. The test asserts that **Advance stage** is absent.

- [ ] **Step 4: Honour the visa lock**

In `apps/web/components/CounselorVisaPanel.tsx`:
- Change the type to `type Checklist = { exists: boolean; id?: string; status: string | null; checklist: ChecklistItem[]; locked_reason?: string | null };`.
- Replace the `{nextStages.length > 0 && (` block opener with:

```tsx
                  {/* AGN-023 (DEC-SCOPE-090 H12): a decided or enrolled agency case offers no stage; the server would refuse it. */}
                  {checklist.locked_reason && <p className="muted" style={{ fontSize: 13 }}>{checklist.locked_reason}</p>}
                  {!checklist.locked_reason && nextStages.length > 0 && (
```

The stage list is already forward-only (`STAGES.slice(currentIndex + 1)`). That is unchanged.

- [ ] **Step 5: Show the counselor on the agency detail**

In `apps/web/lib/agentApplications.ts`, add `counselor_name: string | null; // AGN-023 (DEC-SCOPE-090 H7): the EduSphere counselor's name only` to `AgentApplicationDetail` after `enrollment_confirmed_at`.

In `apps/web/components/AgentApplicationDetail.tsx`, directly after `<dd>{detail.next_action ?? "—"}</dd>`:

```tsx
            <dt>EduSphere counsellor</dt>
            <dd>{detail.counselor_name ?? "Not assigned yet"}</dd>
```

- [ ] **Step 6: Run the tests**

Run: `WEB_TEST "npx vitest run tests/components/CounselorAgencyLimits.test.tsx tests/components/AgentApplicationDetail.test.tsx tests/components/CounselorVisaPanel.test.tsx && npx tsc --noEmit && npx eslint components/CounselorEvaluationPanel.tsx components/CounselorVisaPanel.tsx components/AgentApplicationDetail.tsx lib/agentApplications.ts"`
Expected: PASS. If `tsc` reports other fixtures of type `AgentApplicationDetail` without `counselor_name`, add `counselor_name: null` to each.

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/CounselorEvaluationPanel.tsx apps/web/components/CounselorVisaPanel.tsx apps/web/components/AgentApplicationDetail.tsx apps/web/lib/agentApplications.ts apps/web/tests/components/CounselorAgencyLimits.test.tsx apps/web/tests/components/AgentApplicationDetail.test.tsx
git commit -m "feat(agn-023): counselor screens hide Enrolled and locked visa stages on agency applications; agency sees the counsellor (AC14, AC20, AC21)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: End-to-end flow

**Files:**
- Create: `apps/web/tests/e2e/agn-023-counselor-assignment.spec.ts`

**Interfaces:**
- Consumes: seeded accounts `agent@edusphere.local`, `overseasadmin@edusphere.local`, `counselor@edusphere.local` (password `Demo@123`); `signIn` from `./helpers/agency`; `pickFromList` from `./helpers/pick`.

- [ ] **Step 1: Write the spec**

```ts
import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { pickFromList } from "./helpers/pick";

// AGN-023 -- the Overseas Admin filters to agency applications with no counsellor and assigns one; the counsellor filters by that
// agency, is not offered Enrolled, and advances; the agency sees the counsellor's name. Unique names per run (shared E2E DB).
const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

async function agencyApplication(page: Page, name: string) {
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
}

test("admin assigns a counsellor to an agency application; counsellor advances (no Enrolled); agency sees the name", async ({ browser }) => {
  const name = `E2E Handoff ${stamp()}`;
  const agency = await browser.newPage();
  await signIn(agency, "agent@edusphere.local", "Demo@123");
  await agencyApplication(agency, name);

  // The seeded counsellor is the one who signs in below, so assign that account by its name.
  const counselor = await browser.newPage();
  await signIn(counselor, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  const counselorName: string = (await (await counselor.request.get("/api/v1/auth/me")).json()).full_name;

  const admin = await browser.newPage();
  await signIn(admin, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await admin.goto("/overseas/admin/applications?agency=any&counselor=none");
  await expect(admin.getByLabel("Agency")).toHaveValue("any");
  await expect(admin.getByLabel("Counsellor")).toHaveValue("none");
  const row = admin.getByRole("row", { name: new RegExp(name) });
  await row.getByRole("button", { name: "Assign counsellor" }).click();
  await row.getByLabel("EduSphere counsellor").selectOption({ label: counselorName });
  await row.getByRole("button", { name: "Save" }).click();
  await expect(admin.getByText(`${counselorName} assigned.`)).toBeVisible();

  await counselor.goto("/overseas/counselor/applications");
  const card = counselor.locator(".card").filter({ has: counselor.getByRole("heading", { name }) });
  await expect(card.getByText("Enrollment is confirmed by the agency.")).toBeVisible();
  await card.getByRole("button", { name: "Advance stage" }).click();
  await expect(card.getByLabel("Advance to").locator("option[value=enrolled]")).toHaveCount(0);
  await card.getByLabel("Advance to").selectOption("eligibility_evaluation");
  await card.getByRole("button", { name: "Advance" }).click();
  await expect(card.getByRole("status")).toContainText("Application advanced");

  await agency.goto("/overseas/agent/applications");
  await agency.getByRole("list", { name: "Applications", exact: true }).getByRole("button", { name: new RegExp(`^View ${name} — `) }).click();
  await expect(agency.getByRole("region", { name: new RegExp(`^${name} — `) }).getByText(counselorName)).toBeVisible();
});
```

`DataTable` pages its rows. On a shared E2E database with many unassigned agency applications, the new row may not be on page 1. In that case, type `name` into the table's own search input before locating the row: read `DataTable.tsx` for that input's label. The other way is to filter by the seeded agency's id, taken from the Agency dropdown option whose label is the seeded agency's name.

- [ ] **Step 2: Run it**

The owner must have the `prd84` stack running and seeded (`docker compose -p prd84 -f docker-compose.yml exec -T api python -m app.seed`). Then:
Run: `WEB_TEST "npx playwright test tests/e2e/agn-023-counselor-assignment.spec.ts"`, adding `-e E2E_BASE_URL=http://host.docker.internal:<web port>` to the docker part, where the web port is the one the owner's stack exposes.
Expected: PASS. Also re-run the neighbours: `tests/e2e/agn-012-visa.spec.ts tests/e2e/agn-013-enrollment.spec.ts tests/e2e/ovs-003-eligibility.spec.ts tests/e2e/visa-003-status.spec.ts`.

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/agn-023-counselor-assignment.spec.ts
git commit -m "test(agn-023): e2e hand-off from admin filter and assign to counselor advance and agency view

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Documentation and traceability

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (new `### DEC-SCOPE-090` entry at the end of the DEC-SCOPE run)
- Modify: `docs/architecture/API_CONTRACT.md` (new `## 12M` after `## 12L`)
- Modify: `docs/architecture/RBAC_MATRIX.md` (the §2.7 counselor row ~L122, and the AGN-008 notes block ~L247-270)
- Modify: `docs/delivery/AGENT_CRM_BACKLOG.md`, `docs/features/MASTER_FEATURE_CATALOG.md` (AGN-023 entry)
- Modify: `docs/product/PRD_OPEN_ITEMS.md` (item 84)
- Modify: `docs/quality/RTM.md` (AGN-023 row)
- Modify: `docs/superpowers/specs/2026-10-06-agn-023-counselor-assignment-design.md` (Status line: built)

- [ ] **Step 1: Decision register**

Add, following the format of the `DEC-SCOPE-054` entry:

```markdown
### DEC-SCOPE-090 — EduSphere counselor assignment and agency hand-off (`AGN-023`)

**Status:** `EXPLICIT_APPROVAL` (owner, in-session, 2026-10-06) for H1–H12; built on `feature/agn-023`. Drafted as `089`; bdm-020 took
`089` on `main` @ `4e5730ee`. **Resolves:** `PRD_OPEN_ITEMS.md` item 84. **Spec:** `docs/superpowers/specs/2026-10-06-agn-023-counselor-assignment-design.md`.

- **H1** The counselor supports the agency; the agency keeps ownership.
- **H2** The Overseas Admin assigns (`PUT /workflows/overseas/applications/{id}/counselor`), and can change the counselor.
- **H3** At any open stage; `withdrawn`/`enrolled` → 409.
- **H4** On an agency application the counselor advances (never `enrolled`, which stays with the Master, `DEC-SCOPE-054` E1), runs the
  visa case under the AGN-012 rules, and verifies documents. The visa decision stays with the agency.
- **H5** Notices: the new counselor, the previous counselor on a change, the agency (AGN-017 recipients, no names).
- **H6** The counselor sees the application only — no agency counseling, budget, shortlist, email or phone.
- **H7** The agency sees the counselor's name only.
- **H8** Swap only; a counselor cannot be cleared.
- **H9** The assign action covers every overseas application; H4/H6 apply to agency applications only.
- **H10** The generic `PATCH /workflows/overseas/applications/{id}` refuses `counselor_id` (422).
- **H11** Students/Applications filters: Admin by agency and counselor, counselor by agency; server-side, before the row cap.
- **H12** On agency applications the counselor's screens hide **Enrolled** and locked or backward visa stages.

**Consequences:** narrows `DEC-SCOPE-054` E4's tolerance for the counselor only (the Admin and university_rep generic update is
unchanged); `tel-017`'s PATCH-based counselor check moves to the assign route. No migration.
```

- [ ] **Step 2: API contract §12M**

Add `## 12M. EduSphere counselor assignment (\`AGN-023\`) — addendum, 2026-10-06`. Document:
- `PUT …/counselor`: its body, response, order of checks and every error string from the Global Constraints.
- The `PATCH` refusal.
- The portal `agency`/`counselor` query parameters with their values and 422s.
- The new row keys and the `filters` payload.
- `visa-checklist.locked_reason` and the agency detail's `counselor_name`.
- The counselor `/advance` and visa refusals on agency applications.

Copy the exact strings and shapes from Tasks 1–3.

- [ ] **Step 3: RBAC matrix**

Make these changes:
- §2.7 `counselor` row: append "; on an agency application (`agent_id` set): advance except to `enrolled`, visa under AGN-012 rules, no visa decision (`AGN-023`, `DEC-SCOPE-090`)".
- `overseas_admin` row: append "; assign/change an application's EduSphere counselor (`AGN-023`)".
- AGN-008 notes block: add one line, "**AGN-023 (`DEC-SCOPE-090`):** `counselor_id` is set only by `PUT …/counselor` (Overseas Admin; not super_admin); the generic PATCH refuses it for every role", and cite the test files.

- [ ] **Step 4: Backlog, catalogue, open items, RTM, spec status**

Make these changes:
- `AGENT_CRM_BACKLOG.md` and `MASTER_FEATURE_CATALOG.md`: add an AGN-023 entry in the same shape as AGN-022. Include the title, `DEC-SCOPE-090`, AC01–AC21 by reference to the spec, and status `VERIFIED, full regression deferred`.
- `PRD_OPEN_ITEMS.md` item 84: append "— **Resolved 2026-10-06 by `DEC-SCOPE-090` (`AGN-023`)**" to the first cell.
- `RTM.md`: add an `AGN-023` row in the format of the `bdm-020` row. It must cover evidence (item 84 plus the owner's answers), decision, the spec ACs, the API §12M, RBAC, the test files from Tasks 1–7, and the code files.
- Spec Status line: "Built on `feature/agn-023` (2026-10-06); lite backend set, vitest and the AGN-023 e2e green; full backend suite deferred to the owner".

- [ ] **Step 5: Check the links and numbers**

Run: `grep -rn "DEC-SCOPE-089" docs/superpowers/specs/2026-10-06-agn-023-counselor-assignment-design.md docs/superpowers/plans/2026-10-06-agn-023-counselor-assignment.md`
Expected: only the "drafted as `089`" mentions.
Run: `git fetch origin && git grep -n "DEC-SCOPE-090\|^## 12M" origin/main -- docs`
Expected: no hits. If another feature has taken either one, renumber to the next free value everywhere on this branch before committing.

- [ ] **Step 6: Commit**

```bash
git add docs
git commit -m "docs(agn-023): DEC-SCOPE-090, API 12M, RBAC, backlog, catalogue, RTM; resolve PRD open item 84

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Completion report (after Task 8)

Report the following, with real command output:
- Which lite backend files ran, and their pass counts.
- The vitest, tsc and eslint results.
- The e2e result.
- That the full backend suite was **not** run, by the owner's standing choice.
- Any existing test whose equality assert was widened (Tasks 2–3), with file and line.

Then give the owner the push command: `git push -u origin feature/agn-023`.
