# tel-017 IT Counselor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow `counselor` in the IT division, give IT counselors a `/it/counselor` workspace (Dashboard + My Leads), and close every
overseas-only route to them.

**Architecture:** The server allow-list gains IT `counselor`. A small `_it_counselor` portal handler is dispatched before
`_operations`, and the leads query is shared and filtered by `user.division`. Nine role-only overseas routes gain the
`division == "overseas"` gate that `workflows._require` already applies. The web adds the nav, pages, middleware entry and a
division-aware landing helper.

**Tech Stack:** FastAPI + SQLAlchemy async (pytest in the `api-test` container); Next.js App Router + vitest + Playwright (`web-test`
container).

**Spec:** `docs/superpowers/specs/2026-10-06-tel-017-it-counselor-design.md`

## Global Constraints
- No migration and no schema change. No response-shape change on any existing endpoint.
- The refusal text for a wrong division is exactly `"Wrong EduSphere division"` (403), the same as `workflows._require`.
- `super_admin` is exempt from every new division gate.
- Inline authorization: a role check, then a division check, then the scope. No new `require_*` dependency.
- The overseas counselor's output is byte-identical to today's.

## Review Focus
- An IT counselor holding an overseas lead id (`Enquiry.division == "overseas"`, `owner_id == them`) must not see it: covered in Task 2.
- An overseas counselor opening `/portal/it/counselor/leads` → 403: covered in Task 2.
- An IT counselor typing `/it/counselor/visa` → 404 page, and the API → 404: covered in Tasks 2 and 3.
- An IT counselor's post-login landing and the "Back to dashboard" links must not point at `/overseas/counselor/dashboard`: covered in
  Task 3 (`dashboardPathFor`).
- `university_rep`/`agent`/`overseas_student` on the newly gated lookups keep their 200s: covered by the existing ENH-031 lookup tests
  in Task 1's lite run.

---

### Task 1: IT counselor creation + overseas division gates

**Files:**
- Modify: `apps/api/app/api/admin.py` (`allowed_by_division["it"]`; the three `/overseas-admin` bridge routes ~L1787/1810/1853)
- Modify: `apps/api/app/api/lookups.py` (`_allow` gains `division`; four counselor-admitting routes)
- Modify: `apps/api/app/api/inbound.py` (two routes)
- Test: `apps/api/tests/test_tel_017_it_counselor.py` (new)

**Interfaces:** Produces `lookups._allow(user, roles, division: str | None = None)`.

- [ ] **Step 1: Write the failing tests**

```python
"""tel-017 (DEC-SCOPE-076) -- the counselor role in the IT division; an IT counselor gets no overseas access (AC1-AC4)."""

import uuid

import pytest

from app.models import Enquiry
from tests.bdm001_helpers import USERS, email, login, make_user

DENIED = "Wrong EduSphere division"
ZERO = uuid.UUID(int=0)


def _counselor_payload(division: str) -> dict:
    return {"role": "counselor", "division": division, "email": email("cns"), "full_name": "Kavya Counselor"}


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "target"), [("it_admin", "it", "it"), ("super_admin", "global", "it"), ("overseas_admin", "overseas", "overseas"), ("super_admin", "global", "overseas")])
async def test_admin_creates_a_counselor_in_its_division(client, db_session, role, division, target):
    await login(client, await make_user(db_session, role, division))
    response = await client.post(USERS, json=_counselor_payload(target))
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "counselor" and response.json()["division"] == target


@pytest.mark.asyncio
async def test_overseas_admin_still_cannot_create_an_it_counselor(client, db_session):
    await login(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await client.post(USERS, json=_counselor_payload("it"))).status_code == 403


# Every counselor-admitting overseas route (workflows.py's 14 plus the 9 role-only gates), with a nil id where one is needed: the
# division gate must refuse before any lookup, so no fixture rows are required.
OVERSEAS_ROUTES = [
    ("POST", "/api/v1/workflows/overseas/applications", {"student_id": str(ZERO), "university_id": str(ZERO), "intake": "Fall 2027"}),
    ("GET", "/api/v1/workflows/overseas/applications", None),
    ("PATCH", f"/api/v1/workflows/overseas/applications/{ZERO}", {"status": "enquiry"}),
    ("POST", f"/api/v1/workflows/overseas/applications/{ZERO}/advance", {}),
    ("GET", f"/api/v1/workflows/overseas/applications/{ZERO}/status", None),
    ("POST", "/api/v1/workflows/overseas/documents", {"student_id": str(ZERO), "document_type": "passport", "file_name": "p.pdf"}),
    ("PATCH", f"/api/v1/workflows/overseas/documents/{ZERO}/verify", {"verification_status": "verified"}),
    ("GET", f"/api/v1/workflows/overseas/documents/{ZERO}/download", None),
    ("GET", f"/api/v1/workflows/overseas/applications/{ZERO}/visa-checklist", None),
    ("GET", f"/api/v1/workflows/overseas/applications/{ZERO}/visa-status", None),
    ("PATCH", f"/api/v1/workflows/overseas/visa/{ZERO}", {"status": "submitted"}),
    ("POST", "/api/v1/workflows/overseas/visa", {"application_id": str(ZERO)}),
    ("POST", "/api/v1/workflows/overseas/appointments", {"student_id": str(ZERO), "scheduled_at": "2027-01-01T10:00:00Z", "appointment_type": "counselling"}),
    ("PATCH", f"/api/v1/workflows/overseas/appointments/{ZERO}", {"status": "completed"}),
    ("GET", "/api/v1/overseas-admin/school-students/lookup?code=STU-0001", None),
    ("POST", f"/api/v1/overseas-admin/school-students/{ZERO}/applications", {"university_id": str(ZERO), "intake": "Fall 2027"}),
    ("GET", "/api/v1/overseas-admin/school-applications", None),
    ("GET", "/api/v1/lookups/overseas-students", None),
    ("GET", "/api/v1/lookups/overseas-applications", None),
    ("GET", "/api/v1/lookups/schools", None),
    ("GET", f"/api/v1/lookups/school-students?school_id={ZERO}", None),
    ("GET", "/api/v1/inbound/university-email", None),
    ("PATCH", f"/api/v1/inbound/university-email/{ZERO}/match", {"application_id": str(ZERO)}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path", "body"), OVERSEAS_ROUTES, ids=[f"{m} {p.split('?')[0]}" for m, p, _ in OVERSEAS_ROUTES])
async def test_every_overseas_counselor_route_refuses_an_it_counselor(client, db_session, method, path, body):
    await login(client, await make_user(db_session, "counselor", "it"))
    response = await client.request(method, path, json=body)
    assert response.status_code == 403, response.text
```

Every request body must pass validation, or FastAPI returns 422 before the gate runs. If a parametrised case returns 422, read that
route's schema and fix the body. Never loosen the assertion.

- [ ] **Step 2: Run, and confirm the expected failures**

Run (from the worktree root, Git Bash):

```
docker compose -p tel017 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/tel-017/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q tests/test_tel_017_it_counselor.py"
```

Expected: the IT-create cases return 422 "Role is not valid", the 14 workflows cases pass, and the 9 role-only routes fail with
200/404/422 instead of 403.

- [ ] **Step 3: Implement**

`admin.py` allow-list:

```python
        "it": {"it_student", "trainer", "placement_team", "hr_team", "it_admin", "bdm", "telecaller", "counselor"},
```

Each of the three `/overseas-admin` bridge routes, directly after its existing role check:

```python
    if user.role != "super_admin" and user.division != "overseas":
        raise HTTPException(403, "Wrong EduSphere division")  # tel-017: an IT counselor has the role but not the division
```

`lookups._allow`:

```python
def _allow(user: User, roles: set[str], division: str | None = None) -> None:
    if user.role != "super_admin" and user.role not in roles:
        raise HTTPException(403, FORBIDDEN)
    # tel-017 (DEC-SCOPE-076): a counselor can be IT now, so the overseas lookups check the division as workflows._require does.
    if division and user.role != "super_admin" and user.division != division:
        raise HTTPException(403, "Wrong EduSphere division")
    reason = agent_denial_reason(user)
    ...
```

Pass `"overseas"` at the four call sites: `overseas-students` (the non-link branch), `overseas-applications`, `schools`, and
`school-students`.

In both `inbound.py` routes, after the role check, add the same two-line division gate as in `admin.py`.

- [ ] **Step 4: Run the file again.** Expected: all tests pass.

- [ ] **Step 5: Commit** `feat(tel-017): counselor allowed in IT; overseas-only routes refuse other divisions`

### Task 2: IT counselor portal (Dashboard + My Leads)

**Files:**
- Modify: `apps/api/app/services/portal.py` (new `_routed_leads`, `_it_counselor`; the overseas `leads` branch reuses the helper;
  `section_payload` dispatch)
- Test: `apps/api/tests/test_tel_017_it_counselor.py` (append)

**Interfaces:** Produces `_routed_leads(db, user) -> list[Enquiry]` and `_it_counselor(db, user, section) -> dict | None`.

- [ ] **Step 1: Append the failing tests**

```python
async def _lead(db, division: str, owner, name: str, status: str = "new") -> Enquiry:
    row = Enquiry(division=division, name=name, email=email("lead"), subject="Full Stack", message="x", owner_id=owner.id if owner else None, status=status)
    db.add(row)
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_it_counselor_sees_only_it_leads_routed_to_them(client, db_session):
    me, other = await make_user(db_session, "counselor", "it"), await make_user(db_session, "counselor", "it")
    tag = uuid.uuid4().hex[:6]
    await _lead(db_session, "it", me, f"Mine {tag}")
    await _lead(db_session, "it", me, f"Mine contacted {tag}", status="contacted")
    await _lead(db_session, "it", other, f"Theirs {tag}")
    await _lead(db_session, "it", None, f"Unrouted {tag}")
    await _lead(db_session, "overseas", me, f"Overseas {tag}")
    await login(client, me)
    leads = await client.get("/api/v1/portal/it/counselor/leads")
    assert leads.status_code == 200, leads.text
    assert {r["name"] for r in leads.json()["rows"]} == {f"Mine {tag}", f"Mine contacted {tag}"}
    assert leads.json()["title"] == "My Leads"
    dash = await client.get("/api/v1/portal/it/counselor/dashboard")
    assert dash.status_code == 200, dash.text
    metrics = {m["label"]: m["value"] for m in dash.json()["metrics"]}
    assert metrics == {"Leads routed to you": 2, "New leads": 1}


@pytest.mark.asyncio
async def test_it_counselor_has_no_other_sections(client, db_session):
    await login(client, await make_user(db_session, "counselor", "it"))
    for section in ("visa", "applications", "documents", "appointments", "counselor-chat", "reports", "school-applications"):
        assert (await client.get(f"/api/v1/portal/it/counselor/{section}")).status_code == 404, section


@pytest.mark.asyncio
async def test_counselor_portals_refuse_the_other_division(client, db_session):
    await login(client, await make_user(db_session, "counselor", "it"))
    assert (await client.get("/api/v1/portal/overseas/counselor/dashboard")).status_code == 403
    await login(client, await make_user(db_session, "counselor", "overseas"))
    assert (await client.get("/api/v1/portal/it/counselor/leads")).status_code == 403
```

- [ ] **Step 2: Run, and confirm the expected failures.** The leads and dashboard tests fail: IT counselors fall into the overseas
  block, so leads is empty (overseas-filtered) and the dashboard shows overseas metrics. The 404 test fails on sections the overseas
  block serves.

- [ ] **Step 3: Implement** in `services/portal.py`:

```python
async def _routed_leads(db: AsyncSession, user: User) -> list[Enquiry]:
    # CNS-001 / tel-017: leads routed to this counselor (`Enquiry.owner_id`), in the counselor's own division only.
    return list((await db.scalars(select(Enquiry).where(Enquiry.division == user.division, Enquiry.owner_id == user.id).order_by(Enquiry.created_at.desc()))).all())


def _leads_payload(rows: list[Enquiry]):
    return _payload(
        "My Leads",
        "Enquiries routed to you.",
        (("id", "reference"), ("name", "Name"), ("subject", "Interest"), ("status", "Status")),
        ({"id": e.id, "name": e.name, "subject": e.subject, "status": e.status} for e in rows),
    )


async def _it_counselor(db: AsyncSession, user: User, section: str):
    """tel-017 (DEC-SCOPE-076 C1): the IT counselor works leads only -- Dashboard and My Leads. tel-016 adds Appointments, tel-018
    the student link. Every overseas section stays with the overseas counselor (anything else here is a 404)."""
    if section not in {"dashboard", "leads"}:
        return None
    rows = await _routed_leads(db, user)
    if section == "leads":
        return _leads_payload(rows)
    return _payload(
        "Counselor Dashboard",
        "IT leads routed to you.",
        (("name", "Name"), ("subject", "Interest"), ("status", "Status")),
        ({"name": e.name, "subject": e.subject, "status": e.status} for e in rows[:5]),
        ({"label": "Leads routed to you", "value": len(rows)}, {"label": "New leads", "value": sum(1 for e in rows if e.status == "new")}),
    )
```

The overseas `leads` branch becomes `return _leads_payload(await _routed_leads(db, user))`. Its division is `overseas`, so the
output is identical. Keep the CNS-001 comment. In `section_payload`, before the final `else`:

```python
    elif user.role == "counselor" and user.division == "it":
        result = await _it_counselor(db, user, section)
```

- [ ] **Step 4: Run the file plus the lite regression set.** Run `tests/test_tel_017_it_counselor.py`, `test_cns_001_counselor_workspace.py`,
  `test_i19_counselor_chat.py`, `test_uni_001_university_rep_portal.py`, `test_sch_010_overseas_bridge.py`,
  `test_enh_031_lookups_*.py`, `test_rbac.py`, `test_tel_001_provisioning.py` and `test_agn_018_portal_compat.py`. Expected: all pass.
- [ ] **Step 5: Commit** `feat(tel-017): IT counselor workspace -- Dashboard and My Leads`

### Task 3: Web — nav, pages, landing, middleware, user-create option

**Files:**
- Modify: `apps/web/lib/navigation.ts`, `apps/web/middleware.ts`, `apps/web/components/{WorkflowPanel,PortalPage,LoginForm,HeaderAuthActions,AccessUnavailable}.tsx`,
  `apps/web/app/account/{profile,password}/page.tsx`
- Create: `apps/web/app/it/counselor/dashboard/page.tsx`, `apps/web/app/it/counselor/[section]/page.tsx`
- Test: `apps/web/tests/lib/navigation.counselor.test.ts` (new)

**Interfaces:** Produces `dashboardPathFor(user: { role: string; division?: string | null }): string`.

- [ ] **Step 1: Failing vitest**

```ts
import { describe, expect, it } from "vitest";
import { dashboardPathFor, PORTAL_NAV, ROLE_DASHBOARD_PATH } from "@/lib/navigation";

describe("tel-017 IT counselor navigation", () => {
  it("lands an IT counselor on the IT workspace and everyone else as before", () => {
    expect(dashboardPathFor({ role: "counselor", division: "it" })).toBe("/it/counselor/dashboard");
    expect(dashboardPathFor({ role: "counselor", division: "overseas" })).toBe("/overseas/counselor/dashboard");
    expect(dashboardPathFor({ role: "trainer", division: "it" })).toBe(ROLE_DASHBOARD_PATH.trainer);
    expect(dashboardPathFor({ role: "nobody" })).toBe("/");
  });
  it("gives the IT counselor Dashboard and Leads only", () => {
    expect(PORTAL_NAV["it/counselor"].map((i) => i.href)).toEqual(["/it/counselor/dashboard", "/it/counselor/leads"]);
  });
  it("lists Counselors for the IT admin", () => {
    expect(PORTAL_NAV["it/admin"].some((i) => i.href === "/it/admin/counselors")).toBe(true);
  });
});
```

- [ ] **Step 2: Run** `npx vitest run tests/lib/navigation.counselor.test.ts` in `web-test`. Expected: FAIL (`dashboardPathFor` is not
  exported).
- [ ] **Step 3: Implement.**
  - `navigation.ts`: after `ROLE_DASHBOARD_PATH`:

    ```ts
    // tel-017 (DEC-SCOPE-076): a counselor belongs to IT or Overseas, so the landing depends on the division too.
    export function dashboardPathFor(user: { role: string; division?: string | null }): string {
      if (user.role === "counselor" && user.division === "it") return "/it/counselor/dashboard";
      return ROLE_DASHBOARD_PATH[user.role] ?? "/";
    }
    ```

    Add `"it/counselor": ["dashboard","leads"].map(...)` using the same mapper as the other rows, and insert `"counselors"` after
    `"trainers"` in `it/admin`.
  - Consumers: replace `ROLE_DASHBOARD_PATH[user.role] || "/"` with `dashboardPathFor(user)` (LoginForm uses `data.user`;
    HeaderAuthActions uses `user`; AccessUnavailable has two sites; account profile/password use `user`).
  - `middleware.ts`: `it\/(student|trainer|placement|hr|admin|counselor)`.
  - Pages: copy the overseas counselor pages with `division="it"`.
  - `PortalPage` labels: `"it/counselor":"Counselor"`.
  - `WorkflowPanel` `ROLES_BY_DIVISION.it`: append `"counselor"`.
- [ ] **Step 4: Run** the new vitest file plus `tests/lib/navigation*.test.ts`, `tests/components/AccessUnavailable.test.tsx`,
  `tests/components/WorkflowPanel*.test.tsx`, `tests/components/AdminUserManagementPanel.test.tsx`, then `npx tsc --noEmit` and
  `npx eslint` on the changed files. Expected: all green.
- [ ] **Step 5: Commit** `feat(tel-017): IT counselor workspace pages, nav and division-aware landing`

### Task 4: Playwright + docs

**Files:**
- Create: `apps/web/tests/e2e/tel-017-it-counselor.spec.ts`
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (DEC-SCOPE-076), `docs/architecture/RBAC_MATRIX.md`, `docs/ux/ROLE_NAVIGATION.md`,
  `docs/ux/SCREEN_CATALOG.md`, `docs/delivery/TELECALLER_CRM_BACKLOG.md` (tel-017 status)

- [ ] **Step 1: The e2e spec.** It seeds an IT counselor and an IT lead routed to them through the API (`it_admin` creates the counselor,
  then the test sets the password; `PATCH /admin/leads/{id}` sets `owner_id`), following the `tel-001` e2e spec's seeding helpers. It
  asserts:
  - sign-in at `/it/login` lands on `/it/counselor/dashboard`;
  - the nav has exactly Dashboard and Leads;
  - My Leads lists the lead;
  - `/overseas/counselor/dashboard` shows the access-unavailable card;
  - `/it/counselor/visa` returns 404;
  - the IT admin Users form's Role select offers `counselor`.
- [ ] **Step 2: Run it** against the isolated stack. Expected: pass.
- [ ] **Step 3: Docs.** Add the DEC-SCOPE-076 entry (T3, C1, the division-immutability finding, the 9 gated routes), the RBAC matrix
  counselor row (IT: leads only), the role-nav entry for IT Counselor, the screen catalogue entries `/it/counselor/{dashboard,leads}`
  and `/it/admin/counselors`, and mark the backlog status.
- [ ] **Step 4: Commit** `test(tel-017): e2e`, then `docs(tel-017): DEC-SCOPE-076, RBAC, navigation, screens, backlog`
