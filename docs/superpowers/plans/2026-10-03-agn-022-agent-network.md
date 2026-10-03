# AGN-022 Agent Network Oversight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overseas Admin sees every agent organisation with its counts, drills read-only into one agency's students and
applications (audited), and suspends/reinstates it from the same screen.

**Architecture:** One read-only service (`services/agent_network.py`) counts by organisation id, reusing AGN-018's definitions.
`admin.py`'s `agents_router` gains additive keys on `GET /agent-orgs` and three new GET routes; suspend/reinstate is the shipped
AGN-001 route. Two new standalone admin pages with two client panels and one shared drill-down list component.

**Tech Stack:** FastAPI, Pydantic v2, async SQLAlchemy, PostgreSQL, pytest-asyncio; Next.js (app router), React, vitest +
Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-03-agn-022-agent-network-design.md` (decision `DEC-SCOPE-064`).

## Global Constraints

- No migration, no new dependency, no change to models, `transition_org`, `agent_denial_reason`, `_require`, the approval page
  or any agent-side route.
- `GET /overseas-admin/agent-orgs`: only the keys `staff_count` and `counts` are added; nothing else changes.
- Gate every new route with `_require_overseas_admin(user)` before any lookup (403 "Overseas Admin role required").
- Unknown org → `404 "Organisation not found"`. Paging `limit` 1–100 (default 25), `offset ≥ 0`.
- New routes send `Cache-Control: private, no-store`. Drill-down rows never include email, phone or date of birth.
- Drill-down reads write one `AuditLog(action="agent_network.students_read"|"agent_network.applications_read",
  entity_type="agent_org", outcome="read")` and commit before returning (fail closed).
- Log line `agent_network.read` with ids, list name, row count and duration only (no names).
- Frontend: new page heading "Agent network" (`h2`); never "Agent Approvals"; no `.action-card`; nav label "Agent network".
- Lite tests only (owner, 2026-10-03): the AGN-022 files plus the directly affected suites; the owner runs full suites later.

## Review Focus

1. A linked student's login with an application created by **another** agency — must not count in this org's per-student
   application count (Task 3 test `test_student_application_count_ignores_other_agencies`).
2. An org with zero members' data (fresh pending org) — detail returns zeros, lists empty, no division-by-anything or `None`
   amounts (Task 2/3 `test_an_empty_org_is_all_zeros`).
3. Applications `status` filter with a legacy value (e.g. `offer_received`) — 422, not a silent empty page (Task 3).
4. Double-click on Suspend / a stale 409 — one request, message shown, summary refetched (Task 6 vitest).
5. Crafted page URL `/overseas/admin/agent-network/..%2Fagents` — not-found without any API call (Task 5 lib test + Task 6).

---

### Task 1: Count service + additive list keys (AC1, AC8)

**Files:**
- Create: `apps/api/app/services/agent_network.py`
- Create: `apps/api/tests/agn022_helpers.py`
- Create: `apps/api/tests/test_agn_022_network.py`
- Modify: `apps/api/app/api/admin.py` (`list_agent_orgs`, imports)

**Interfaces:**
- Produces: `members_of(org_id) -> Select`; `NETWORK_APPLICATION` (column clause); `org_counts(db, org_ids) -> dict[UUID, {"staff_count","students","applications","enrollments"}]`;
  `agn022_helpers.network_world(db) -> dict` (dashboard_world + `s4` deactivated staff + deposits + `empty` org);
  `agn022_helpers.NETWORK = {"staff_count": 3, "students": 4, "applications": 7, "enrollments": 1}`.

- [ ] **Step 1: Fixture.** `tests/agn022_helpers.py`:

```python
"""AGN-022 fixture: AGN-018's dashboard world (hand counts in agn018_helpers), plus a deactivated staff member, deposits in every
state and an empty organisation. Expected figures are worked out next to the rows that produce them."""

from tests.agn001_helpers import mk_active_org, uniq
from tests.agn004_helpers import mk_staff
from tests.agn011_helpers import mk_deposit
from tests.agn018_helpers import dashboard_world

ORGS = "/api/v1/overseas-admin/agent-orgs"


async def network_world(db) -> dict:
    w = await dashboard_world(db)
    s4 = await mk_staff(db, w["org"], full_name="Staff Four", active=False)  # deactivated: not in staff_count
    a1, a3, a4 = w["apps"]["a1"], w["apps"]["a3"], w["apps"]["a4"]
    by = w["master"]
    await mk_deposit(db, a1, by=by, amount="10000.00", status="pending")  # pending: excluded everywhere
    await mk_deposit(db, a3, by=by, amount="30000.00", status="remitted")
    await mk_deposit(db, a4, by=by, amount="20000.00", status="refunded", refund_amount="5000.00")
    empty = await mk_active_org(db, name=f"Empty {uniq()}")
    return w | {"s4": s4, "empty": empty}


# staff s1 s2 s3 (s4 deactivated); students/applications/enrollments = agn018 MASTER.
NETWORK = {"staff_count": 3, "students": 4, "applications": 7, "enrollments": 1}
ZERO = {"staff_count": 0, "students": 0, "applications": 0, "enrollments": 0}
# Commission (agn018): claimable INR 1000 (a2 eligible) + USD 200 (a1 estimated); claims 1 (a3); revenue INR 12000 (a4), USD 500 (a8).
COMMISSION = {
    "claimable": [{"currency": "INR", "count": 1, "amount": 1000.0}, {"currency": "USD", "count": 1, "amount": 200.0}],
    "claims": 1,
    "revenue": [{"currency": "INR", "count": 1, "amount": 12000.0}, {"currency": "USD", "count": 1, "amount": 500.0}],
}
# Deposits: collected = remitted a3 30000 + refunded a4 20000 (count 2); refunded amount = 5000; pending a1 excluded.
DEPOSITS = {"currency": "INR", "count": 2, "collected": 50000.0, "remitted": 30000.0, "refunded": 5000.0}
```

(`mk_deposit(**fields)` passes `refund_amount` straight to the model; pass `Decimal("5000.00")` if the column rejects a str.)

- [ ] **Step 2: Failing tests** in `tests/test_agn_022_network.py`:

```python
"""AGN-022 -- Overseas Admin agent network (DEC-SCOPE-064; spec §8)."""

import pytest

from tests.agn001_helpers import login, mk_user
from tests.agn022_helpers import NETWORK, ORGS, ZERO, network_world


async def _admin(client, db, role="overseas_admin"):
    admin = await mk_user(db, role=role)
    await login(client, admin.email)
    return admin


def _item(body, org_id):
    return next(i for i in body["items"] if i["id"] == str(org_id))


@pytest.mark.asyncio
async def test_the_list_adds_counts_that_match_the_fixture(client, db_session):  # AC1, AC8
    w = await network_world(db_session)
    await _admin(client, db_session)
    body = (await client.get(ORGS, params={"q": w["org"].prefix, "limit": 100})).json()
    item = _item(body, w["org"].id)
    assert item["staff_count"] == NETWORK["staff_count"]
    assert item["counts"] == {k: NETWORK[k] for k in ("students", "applications", "enrollments")}
    assert set(item) == {"id", "name", "prefix", "status", "created_at", "masters", "staff_count", "counts"}  # existing keys kept


@pytest.mark.asyncio
async def test_other_agencies_and_empty_orgs_count_on_their_own(client, db_session):  # AC1, AC3
    w = await network_world(db_session)
    await _admin(client, db_session)
    empty = _item((await client.get(ORGS, params={"q": w["empty"]["org"].prefix})).json(), w["empty"]["org"].id)
    assert {"staff_count": empty["staff_count"], **empty["counts"]} == ZERO
    noise = _item((await client.get(ORGS, params={"q": w["other"]["org"].prefix})).json(), w["other"]["org"].id)
    assert noise["counts"] == {"students": 1, "applications": 1, "enrollments": 1}  # the noise agency's own rows only
```

- [ ] **Step 3: Run — expect FAIL** `KeyError: 'staff_count'`.
  Run: `.venv/Scripts/python -m pytest -q tests/test_agn_022_network.py -p no:cacheprovider`

- [ ] **Step 4: Implement** `services/agent_network.py` (`members_of`, `NETWORK_APPLICATION`, `org_counts` — three statements
  grouped by `AgentOrgMember.org_id`: active staff; `AgentStudent.status == "active"` joined on `agent_id == user_id`;
  applications `count(case(status != WITHDRAWN))`, `count(case(status == "enrolled"))` joined on `agent_id == user_id` with
  `NETWORK_APPLICATION`; zero defaults; `{}` for no ids). In `list_agent_orgs`, after `orgs` is loaded:
  `counts = await org_counts(db, [o.id for o in orgs])` and add `"staff_count": c["staff_count"], "counts": {students,
  applications, enrollments}` to each item.

- [ ] **Step 5: Run — expect PASS** (new file + `tests/test_agn_001_org_admin.py`).
- [ ] **Step 6: Commit** `feat(agn-022): per-organisation counts on the admin agent-org list`.

### Task 2: Organisation detail with money (AC1, AC2, AC3, AC5, AC7)

**Files:**
- Modify: `apps/api/app/services/agent_dashboard.py` (extract `commission_totals`)
- Modify: `apps/api/app/services/agent_network.py` (`org_money`)
- Modify: `apps/api/app/schemas.py` (`AgentNetworkCounts`, `AgentOrgMasterOut`, `AgentNetworkDepositsOut`, `AgentOrgDetailOut`)
- Modify: `apps/api/app/api/admin.py` (`_network_org`, `_master_row`, `get_agent_org`)
- Test: `apps/api/tests/test_agn_022_network.py`

**Interfaces:**
- Consumes: Task 1 `org_counts`, `members_of`.
- Produces: `agent_dashboard.commission_totals(db, member_ids: Select) -> dict` (same shape as `commission_summary`);
  `agent_network.org_money(db, org_id) -> {"commission": ..., "deposits": {"currency","count","collected","remitted","refunded"}}`;
  `admin._network_org(db, org_id) -> AgentOrg` (404); route `GET /overseas-admin/agent-orgs/{org_id}` → `AgentOrgDetailOut`.

- [ ] **Step 1: Failing tests:**

```python
DETAIL = ORGS + "/{oid}"


@pytest.mark.asyncio
async def test_the_detail_matches_the_fixture(client, db_session):  # AC1, AC2, AC7
    w = await network_world(db_session)
    await _admin(client, db_session)
    r = await client.get(DETAIL.format(oid=w["org"].id))
    assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
    body = r.json()
    assert body["staff_count"] == 3 and body["counts"] == {"students": 4, "applications": 7, "enrollments": 1}
    assert body["commission"] == COMMISSION and body["deposits"] == DEPOSITS
    assert [m["code"] for m in body["masters"]] == [w["member"].code]
    assert "staff" not in body  # R-API-3: count only


@pytest.mark.asyncio
async def test_an_empty_org_is_all_zeros(client, db_session):  # AC3
    w = await network_world(db_session)
    await _admin(client, db_session, role="super_admin")
    body = (await client.get(DETAIL.format(oid=w["empty"]["org"].id))).json()
    assert body["counts"] == {"students": 0, "applications": 0, "enrollments": 0} and body["staff_count"] == 0
    assert body["commission"] == {"claimable": [], "claims": 0, "revenue": []}
    assert body["deposits"] == {"currency": "INR", "count": 0, "collected": 0.0, "remitted": 0.0, "refunded": 0.0}


@pytest.mark.asyncio
async def test_unknown_and_malformed_ids(client, db_session):
    await _admin(client, db_session)
    assert (await client.get(DETAIL.format(oid=uuid.uuid4()))).json() == {"detail": "Organisation not found"}
    assert (await client.get(DETAIL.format(oid="not-a-uuid"))).status_code == 422
```

- [ ] **Step 2: Run — expect FAIL** (405/404 on the new path).
- [ ] **Step 3: Implement.** In `agent_dashboard.py` move `commission_summary`'s body into
  `commission_totals(db, member_ids)`; `commission_summary` returns `await commission_totals(db, org_member_ids(user))`.
  `org_money`: `commission_totals(db, members_of(org_id))`; deposits: one select over `ApplicationDeposit` joined to
  `OverseasApplication` with `agent_id.in_(members_of(org_id))`, `NETWORK_APPLICATION`, `count(case(status in PAID_STATES))`,
  `coalesce(sum(case(status in PAID_STATES, amount)), 0)`, `coalesce(sum(case(status == "remitted", amount)), 0)`,
  `coalesce(sum(case(status == "refunded", refund_amount)), 0)` (`PAID_STATES` from `services/agent_deposits.py`). Route: gate,
  `_network_org`, counts, `org_masters(org.id)` via `_master_row` (also used by `list_agent_orgs`), money, `as_of=now`, header.
- [ ] **Step 4: Run — expect PASS**, plus `tests/test_agn_018_dashboard.py` (commission refactor unchanged).
- [ ] **Step 5: Commit** `feat(agn-022): admin organisation detail with counts and money`.

### Task 3: Read-only drill-down lists with audit (AC5, AC6, AC7)

**Files:**
- Modify: `apps/api/app/services/agent_network.py` (`org_students`, `org_applications`)
- Modify: `apps/api/app/schemas.py` (`AgentNetworkStudentOut`, `AgentNetworkStudentPage`, `AgentNetworkApplicationOut`, `AgentNetworkApplicationPage`)
- Modify: `apps/api/app/api/admin.py` (`_audit_network_read`, two routes)
- Test: `apps/api/tests/test_agn_022_network.py`

**Interfaces:**
- Produces: `org_students(db, org_id, *, status, limit, offset) -> (list[dict], int)` rows `{id, full_name, status, assigned_code,
  has_login, applications, created_at}`; `org_applications(db, org_id, *, status, limit, offset) -> (list[dict], int)` rows
  `{id, student_name, university, country, status, enrollment_date, created_at, updated_at}`; `APPLICATION_FILTERS =
  (*OVERSEAS_APPLICATION_STAGES, WITHDRAWN)`.

- [ ] **Step 1: Failing tests:**

```python
STUDENTS = ORGS + "/{oid}/students"
APPLICATIONS = ORGS + "/{oid}/applications"
FORBIDDEN_KEYS = {"email", "phone", "date_of_birth", "phone_digits", "notes"}


async def _reads(db, org_id, action):
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(org_id), AuditLog.action == action))


@pytest.mark.asyncio
async def test_students_are_listed_read_only_and_audited(client, db_session):  # AC6, AC7
    w = await network_world(db_session)
    admin = await _admin(client, db_session)
    r = await client.get(STUDENTS.format(oid=w["org"].id), params={"limit": 2})
    assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
    body = r.json()
    assert body["total"] == 4 and len(body["items"]) == 2 and body["limit"] == 2
    assert not FORBIDDEN_KEYS & set(body["items"][0])
    archived = (await client.get(STUDENTS.format(oid=w["org"].id), params={"status": "archived"})).json()
    assert archived["total"] == 1 and archived["items"][0]["assigned_code"] == w["s1"]["member"].code
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(w["org"].id), AuditLog.action == "agent_network.students_read").order_by(AuditLog.created_at))
    assert row.user_id == admin.id and row.entity_type == "agent_org" and row.metadata_json == {"status": "active", "limit": 2, "offset": 0, "returned": 2}
    assert await _reads(db_session, w["org"].id, "agent_network.students_read") == 2


@pytest.mark.asyncio
async def test_student_application_count_ignores_other_agencies(client, db_session):  # Review Focus 1
    w = await network_world(db_session)
    await _admin(client, db_session)
    r2 = await db_session.scalar(select(AgentStudent).where(AgentStudent.agent_id == w["master"].id, AgentStudent.student_id.is_not(None)))
    await mk_application(db_session, agent=w["other"]["master"], university=w["u1"], student=await db_session.get(User, r2.student_id), status="enquiry")
    rows = (await client.get(STUDENTS.format(oid=w["org"].id), params={"limit": 100})).json()["items"]
    assert next(r for r in rows if r["has_login"])["applications"] == 2  # a3, a4 -- not the other agency's row


@pytest.mark.asyncio
async def test_applications_exclude_bridged_and_other_agencies_and_filter_by_stage(client, db_session):  # AC1, AC7
    w = await network_world(db_session)
    await _admin(client, db_session)
    body = (await client.get(APPLICATIONS.format(oid=w["org"].id), params={"limit": 100})).json()
    assert body["total"] == 9  # a1..a8 and a10 (withdrawn rows are listed; bridged and noise rows are not)
    assert not FORBIDDEN_KEYS & set(body["items"][0])
    enrolled = (await client.get(APPLICATIONS.format(oid=w["org"].id), params={"status": "enrolled"})).json()
    assert enrolled["total"] == 1 and enrolled["items"][0]["id"] == str(w["apps"]["a4"].id)
    assert (await client.get(APPLICATIONS.format(oid=w["org"].id), params={"status": "offer_received"})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [DETAIL, STUDENTS, APPLICATIONS])
async def test_every_new_route_is_admin_only(client, db_session, path):  # AC5
    w = await network_world(db_session)
    url = path.format(oid=w["org"].id)
    assert (await client.get(url)).status_code == 401
    for user in [w["master"], w["s1"]["user"], await mk_user(db_session, role="counselor"), await mk_user(db_session, role="overseas_student")]:
        await login(client, user.email)
        r = await client.get(url)
        assert r.status_code == 403 and r.json() == {"detail": "Overseas Admin role required"}
    await login(client, (await mk_user(db_session, role="counselor")).email)
    assert (await client.get(path.format(oid=uuid.uuid4()))).status_code == 403  # no existence leak
    assert await _reads(db_session, w["org"].id, "agent_network.students_read") == 0


@pytest.mark.asyncio
async def test_a_failed_audit_write_returns_no_data(client, db_session, monkeypatch):  # AC6 fail closed
    from app.api import admin as admin_api
    w = await network_world(db_session)
    await _admin(client, db_session)
    real = admin_api.AuditLog
    monkeypatch.setattr(admin_api, "AuditLog", lambda **kw: real(**{**kw, "user_id": uuid.uuid4()}))  # FK violation at commit
    with pytest.raises(IntegrityError):
        await client.get(STUDENTS.format(oid=w["org"].id))


@pytest.mark.asyncio
async def test_paging_is_validated(client, db_session):
    w = await network_world(db_session)
    await _admin(client, db_session)
    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "deleted"}):
        assert (await client.get(STUDENTS.format(oid=w["org"].id), params=params)).status_code == 422
```

- [ ] **Step 2: Run — expect FAIL** (routes missing).
- [ ] **Step 3: Implement** the service queries (students: outer joins to the login `User` and an aliased assignee
  `AgentOrgMember`; per-row application count as a correlated scalar subquery with `agent_id ∈ members_of`,
  `NETWORK_APPLICATION`, `status != WITHDRAWN`, and the `staff_rows` record-or-login join; applications via
  `with_owner(select(OverseasApplication, University.name, Country.name)...)`; both ordered `created_at desc, id desc`), the
  schemas, and the routes: gate → `_network_org` → validate applications `status in APPLICATION_FILTERS` (else 422 "Unknown
  application status") → query → `_audit_network_read` (add row, commit, log) → header → page.
- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Commit** `feat(agn-022): audited read-only drill-down into an agency's students and applications`.

### Task 4: Suspend from the network blocks the agency now (AC4)

**Files:** Test: `apps/api/tests/test_agn_022_network.py`

This pins existing AGN-001 behaviour from AGN-022's angle; it is expected to pass on first run (characterisation, no RED).

```python
@pytest.mark.asyncio
async def test_suspend_blocks_master_and_staff_on_their_next_request_and_reinstate_restores(client, db_session):  # AC4
    w = await network_world(db_session)
    await _admin(client, db_session)
    async with client_for(w["master"].email) as master, client_for(w["s1"]["user"].email) as staff:
        assert (await master.get(RECORDS)).status_code == 200 and (await staff.get(RECORDS)).status_code == 200
        assert (await client.post(f"{ORGS}/{w['org'].id}/suspend")).json()["status"] == "suspended"
        for c in (master, staff):
            r = await c.get(RECORDS)
            assert r.status_code == 403 and r.json()["detail"] == "Your agency's account is suspended"
        assert (await client.get(DETAIL.format(oid=w["org"].id))).json()["status"] == "suspended"  # still readable by admins
        await client.post(f"{ORGS}/{w['org'].id}/reinstate")
        assert (await master.get(RECORDS)).status_code == 200 and (await staff.get(RECORDS)).status_code == 200
```

- [ ] Run, expect PASS; also run `tests/test_agn_001_registration_and_gate.py`. Commit `test(agn-022): suspend from the network denies the agency on its next request`.

### Task 5: Navigation, shared lib, Agent network list page (AC9, AC10, AC11)

**Files:**
- Create: `apps/web/lib/agentNetwork.ts` (types, `ORGS_URL`, `orgUrl(id, sub?)` with `encodeURIComponent`, `isUuid`, `ORG_STATUS_LABEL`)
- Create: `apps/web/components/AgentNetworkPanel.tsx`
- Create: `apps/web/app/overseas/admin/agent-network/page.tsx`
- Modify: `apps/web/lib/navigation.ts` (append entry)
- Test: `apps/web/tests/lib/agentNetwork.test.ts`, `apps/web/tests/components/AgentNetworkPanel.test.tsx`, `apps/web/tests/lib/navigation.bdm.test.ts` (add one assertion beside the BDMs one, or a new `navigation.agentNetwork.test.ts`)

- [ ] **Step 1: Failing tests** — lib: `isUuid` accepts a v4 UUID, rejects `"..%2Fagents"`, `""`, `"abc"`; `orgUrl("x/y","students")`
  encodes the slash. Nav: `PORTAL_NAV["overseas/admin"]` contains `{label:"Agent network",href:"/overseas/admin/agent-network"}`
  after "Agent deposits". Panel (fetch stubbed like `AgentApprovalPanel.test.tsx`):
  - first call `${ORGS}?limit=20&offset=0` (All), loading text "Loading agencies…", then a row with name link to
    `/overseas/admin/agent-network/<id>`, status text, Masters codes and the four counts;
  - "Suspended" button → `status=suspended`, `aria-pressed`;
  - search submits `q`;
  - Next page keeps the old rows (dimmed, `aria-busy="true"`) until the new page resolves, then focuses the results heading;
  - a slow first response resolving after a newer one is ignored;
  - 500 → `role="alert"` + Retry works; empty → "No agencies match “x”." / "No suspended agencies.";
  - an agency named `<img src=x onerror=alert(1)>` renders as text (no `img` element);
  - no element with text "Agent Approvals" and no `.action-card`.
- [ ] **Step 2: Run — expect FAIL** (modules missing). `npx vitest run tests/lib/agentNetwork.test.ts tests/components/AgentNetworkPanel.test.tsx tests/lib/navigation.bdm.test.ts`
- [ ] **Step 3: Implement** the lib, the panel (URL state `tab/page/q` as `AgentApprovalPanel`; request sequence ref for stale
  drops; `.table compact stack` in a `.table-scroll` region labelled by the results heading; `data-label` on cells), the page
  (copy of `agent-deposits/page.tsx` with heading "Agent network" and copy "Every agency on EduSphere, with its people and
  pipeline. Open an agency to see its students and applications or to suspend it."), and the nav entry.
- [ ] **Step 4: Run — expect PASS**; also `tests/components/AgentApprovalPanel.test.tsx`, `tests/lib/navigation*.test.ts`.
- [ ] **Step 5: Commit** `feat(agn-022): Agent network list page for Overseas Admin`.

### Task 6: Organisation detail page with drill-down and actions (AC9, AC10, AC11)

**Files:**
- Create: `apps/web/components/AgentOrgDetailPanel.tsx` (summary, money, actions)
- Create: `apps/web/components/AgentNetworkRecords.tsx` (one paged read-only list; `kind: "students" | "applications"`)
- Create: `apps/web/app/overseas/admin/agent-network/[orgId]/page.tsx`
- Test: `apps/web/tests/components/AgentOrgDetailPanel.test.tsx`, `apps/web/tests/components/AgentNetworkRecords.test.tsx`

- [ ] **Step 1: Failing tests:**
  - Detail loads `orgUrl(id)`; shows `h2` name + prefix, status text, four metric tiles (zeros render "0"), commission per
    currency (INR and USD rows, never one total), deposits collected/remitted/refunded, Masters.
  - `canAct` + active → Suspend opens inline confirm; Confirm sends exactly one `POST …/suspend` even on a double click; success
    announces "<name> suspended." in the status region, refetches the summary and focuses the Reinstate button.
  - 409 → server message shown, summary refetched. Network error → "Network error. Check your connection and try again."
  - `canAct=false` (super_admin) → no Suspend/Reinstate buttons. Pending org → link "Review in Agent Approvals" to `/overseas/admin/agents`.
  - 404 → "Organisation not found" + link "Back to Agent network". 500 → alert + Retry.
  - Students/Applications are **not fetched** on first render; clicking "Students" fetches `…/students?status=active&limit=20&offset=0`;
    "Archived" refetches with `status=archived`; applications show `stageLabel(status)`; empty texts; error + Retry.
- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** (reuse `formatInr`, `formatDate`, `stageLabel`, `detailMessage`, `useFocusAfterRender`, `isPage`;
  in-flight ref for the action; page validates `isUuid(orgId)` → `notFound()` before rendering).
- [ ] **Step 4: Run — expect PASS**, then `npm run typecheck` and `npm run lint`.
- [ ] **Step 5: Commit** `feat(agn-022): agency detail with read-only drill-down and suspend/reinstate`.

### Task 7: Playwright spec (AC4, AC10) — written now, run in the browser-validation session

**Files:** Create `apps/web/tests/e2e/agn-022-agent-network.spec.ts`

Flow (unique names per run, `helpers/agency.ts` to register/approve an agency): admin opens "Agent network" from the sidebar,
searches the agency, opens it, sees counts, opens Students, suspends (confirm), then the Master's next agent page shows the
suspended message; reinstate restores. Viewport 375 px: no horizontal scroll (`document.documentElement.scrollWidth <= 375`).

- [ ] Write the spec; `npx tsc --noEmit` covers it; it is **not run** here (no running web+API stack in lite mode). Commit with Task 8.

### Task 8: Documentation and traceability

**Files:** `docs/architecture/API_CONTRACT.md` (AGN-022 block), `docs/architecture/RBAC_MATRIX.md` (admin read-only drill-down,
audit), `docs/quality/RTM.md` (AGN-022 row, AC1–AC11 → tests), `docs/delivery/ENHANCEMENT_BACKLOG.md` (AGN-022 status
IMPLEMENTED, NOT COMPLETE — browser validation and Codex review pending), `docs/delivery/AGENT_CRM_BACKLOG.md` status table row,
`docs/decisions/PRODUCT_DECISION_REGISTER.md` DEC-SCOPE-064 status line.

- [ ] Update, run the lite set once more, commit `docs(agn-022): contract, RBAC, RTM and backlog status`.

## Lite test set (owner instruction: no full suites)

Backend: `tests/test_agn_022_network.py`, `tests/test_agn_001_org_admin.py`, `tests/test_agn_018_dashboard.py`,
`tests/test_agn_001_registration_and_gate.py`, `tests/test_agn_011_admin.py`, `tests/test_agn_002_staff_access.py`; `ruff check`
on changed files. Web: the new vitest files, `AgentApprovalPanel.test.tsx`, `AdminAgentDepositsPanel.test.tsx`,
`AgentDashboardPanel.test.tsx`, `tests/lib/navigation*.test.ts`; `npm run typecheck`; `npm run lint`.
