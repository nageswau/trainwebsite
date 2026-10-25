"""ccrm-033 (DEC-SCOPE-271, RR1-RR3) -- a reassignment carries a logged reason: required when an existing owner is replaced or removed,
optional on a first assignment (RR1); kept in the audit row and the status history, shown in History, sent to both counselors; hidden
from the agent (RR2) and the student (ccrm-016 H2). Lead owner: `owner_reason` on the admin PATCH, notices, the lead timeline (RR3).
The shared test database is never truncated: every assertion is about rows the test made."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AuditLog, OverseasStudentCounselor
from tests.agn001_helpers import client_for, login, mk_user
from tests.agn008_helpers import APPS
from tests.agn023_helpers import ASSIGN, assign_audits, assign_world, fresh, notices
from tests.tel004_helpers import make_user
from tests.tel018_helpers import as_user, make_counselor, setup

REQUIRED = "Give a reason for the reassignment"
STATUS = "/api/v1/workflows/overseas/applications/{}/status"
ADMIN_LEADS = "/api/v1/admin/leads"


def student_url(student_id) -> str:
    return f"/api/v1/admin/users/{student_id}/counselor"


@pytest_asyncio.fixture
async def world(db_session):
    w = await assign_world(db_session, status="university_selection")
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    return w


# --- application counselor ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_replacing_an_application_counselor_without_a_reason_is_refused(db_session, world):
    async with client_for(world["admin"].email) as c:
        for body in ({}, {"reason": ""}, {"reason": "   "}):
            r = await c.put(ASSIGN.format(world["direct_app"].id), json={"counselor_id": str(world["counselor2"].id), **body})
            assert r.status_code == 422 and r.json()["detail"] == REQUIRED, r.text
    assert (await fresh(db_session, world["direct_app"])).counselor_id == world["counselor"].id
    assert len(await assign_audits(db_session, world["direct_app"])) == 1


@pytest.mark.asyncio
async def test_the_reason_is_validated(db_session, world):
    async with client_for(world["admin"].email) as c:
        for reason in ("x" * 501, "bad\x00text"):
            r = await c.put(ASSIGN.format(world["direct_app"].id), json={"counselor_id": str(world["counselor2"].id), "reason": reason})
            assert r.status_code == 422, reason


@pytest.mark.asyncio
async def test_an_application_reassignment_logs_the_reason_everywhere(db_session, world):
    app = world["direct_app"]
    async with client_for(world["admin"].email) as c:
        r = await c.put(ASSIGN.format(app.id), json={"counselor_id": str(world["counselor2"].id), "reason": "  Counsellor on leave  "})
        assert r.status_code == 200 and r.json()["changed"] is True, r.text
        staff_history = (await c.get(STATUS.format(app.id))).json()["history"]
    assert (await assign_audits(db_session, app))[-1] == {"from_counselor_id": str(world["counselor"].id), "to_counselor_id": str(world["counselor2"].id),
                                                          "reason": "Counsellor on leave"}  # fmt: skip
    assert (staff_history[-1]["notes"], staff_history[-1]["reason"]) == ("EduSphere counsellor changed", "Counsellor on leave")
    assert (await notices(db_session, world["counselor"]))[-1].body == "An application has moved to another counselor. Reason: Counsellor on leave"
    assert (await notices(db_session, world["counselor2"]))[-1].body.endswith("Reason: Counsellor on leave")
    async with client_for(world["direct_student"].email) as c:  # H2: the student never sees a reason
        assert all("reason" not in h for h in (await c.get(STATUS.format(app.id))).json()["history"])


@pytest.mark.asyncio
async def test_the_agency_sees_the_change_but_not_the_reason(db_session, world):  # RR2
    app = world["app"]
    async with client_for(world["admin"].email) as c:
        assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(world["counselor2"].id), "reason": "Workload balance"})).status_code == 200
    async with client_for(world["master"].email) as c:
        history = (await c.get(APPS + f"/{app.id}")).json()["application"]["history"]
    changed = [h for h in history if h["notes"] == "EduSphere counsellor changed"]
    assert len(changed) == 1 and changed[0]["reason"] is None


@pytest.mark.asyncio
async def test_a_first_application_assignment_needs_no_reason_but_keeps_one(db_session):
    w = await assign_world(db_session)
    async with client_for(w["admin"].email) as c:
        assert (await c.put(ASSIGN.format(w["app"].id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
        r = await c.put(ASSIGN.format(w["direct_app"].id), json={"counselor_id": str(w["counselor"].id), "reason": "New intake"})
        assert r.status_code == 200
    assert (await assign_audits(db_session, w["app"])) == [{"from_counselor_id": None, "to_counselor_id": str(w["counselor"].id)}]
    assert (await assign_audits(db_session, w["direct_app"]))[0]["reason"] == "New intake"


@pytest.mark.asyncio
async def test_the_same_counselor_needs_no_reason(db_session, world):
    async with client_for(world["admin"].email) as c:
        r = await c.put(ASSIGN.format(world["direct_app"].id), json={"counselor_id": str(world["counselor"].id)})
    assert r.status_code == 200 and r.json()["changed"] is False


# --- student counselor (csc-005) ------------------------------------------------------------------------------------------------
async def _linked_student(db, counselor):
    student = await mk_user(db, role="overseas_student", full_name="Reason Walk-in")
    db.add(OverseasStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db.commit()
    return student


@pytest.mark.asyncio
async def test_replacing_a_students_counselor_needs_a_reason_and_shows_it_in_history(client, db_session):
    old = await mk_user(db_session, role="counselor", full_name="Old Counselor")
    new = await mk_user(db_session, role="counselor", full_name="New Counselor")
    admin = await mk_user(db_session, role="overseas_admin")
    student = await _linked_student(db_session, old)
    await login(client, admin.email)
    r = await client.put(student_url(student.id), json={"counselor_id": str(new.id)})
    assert r.status_code == 422 and r.json()["detail"] == REQUIRED
    r = await client.put(student_url(student.id), json={"counselor_id": str(new.id), "reason": "Student asked for a change"})
    assert r.status_code == 200 and r.json()["changed"] is True, r.text
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "overseas.student.counselor_assign", AuditLog.entity_id == str(student.id)))
    assert audit.metadata_json == {"from_counselor_id": str(old.id), "to_counselor_id": str(new.id), "reason": "Student asked for a change"}
    assert (await notices(db_session, old))[-1].body == "A student has moved to another counselor. Reason: Student asked for a change"
    assert (await notices(db_session, new))[-1].body.endswith("Reason: Student asked for a change")
    items = (await client.get(f"/api/v1/counselor/students/{student.id}/history")).json()["items"]
    assigned = [i for i in items if i["summary"] == "Counselor assigned"]
    assert len(assigned) == 1 and assigned[0]["reason"] == "Student asked for a change"


# --- lead owner (RR3) -----------------------------------------------------------------------------------------------------------
async def _owned_lead(client, db):
    _, _, counselor, row = await setup(db)
    admin = await make_user(db, "it_admin", "it")
    await as_user(client, admin)
    assert (await client.patch(f"{ADMIN_LEADS}/{row.id}", json={"owner_id": str(counselor.id)})).status_code == 200  # first: no reason
    return admin, counselor, row


def _field_error(response, field: str) -> bool:
    return response.status_code == 422 and any(e["loc"][-1] == field for e in response.json()["detail"])


@pytest.mark.asyncio
async def test_replacing_or_removing_a_lead_owner_needs_a_reason(client, db_session):
    _, counselor, row = await _owned_lead(client, db_session)
    other = await make_counselor(db_session)
    url = f"{ADMIN_LEADS}/{row.id}"
    assert _field_error(await client.patch(url, json={"owner_id": str(other.id)}), "owner_reason")
    assert _field_error(await client.patch(url, json={"owner_id": None, "owner_reason": " "}), "owner_reason")
    assert _field_error(await client.patch(url, json={"owner_id": str(other.id), "owner_reason": "x" * 501}), "owner_reason")
    assert (await client.patch(url, json={"owner_id": str(counselor.id)})).status_code == 200  # same owner: no change, no reason
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(row.id), AuditLog.action == "lead.owner_change"))).all()
    assert [r.metadata_json for r in rows] == [{"from_owner_id": None, "owner_id": str(counselor.id)}]


@pytest.mark.asyncio
async def test_a_lead_reassignment_is_logged_notified_and_on_the_timeline(client, db_session):
    _, counselor, row = await _owned_lead(client, db_session)
    other = await make_counselor(db_session)
    url = f"{ADMIN_LEADS}/{row.id}"
    assert (await client.patch(url, json={"owner_id": str(other.id), "owner_reason": "Language match"})).status_code == 200
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(row.id), AuditLog.action == "lead.owner_change").order_by(AuditLog.created_at.desc()).limit(1))
    assert audit.metadata_json == {"from_owner_id": str(counselor.id), "owner_id": str(other.id), "reason": "Language match"}
    new_notice, old_notice = (await notices(db_session, other))[-1], (await notices(db_session, counselor))[-1]
    assert (new_notice.title, new_notice.action_url) == ("Lead assigned to you", f"/it/counselor/leads/{row.id}")
    assert new_notice.body == f"{row.lead_code} is now yours. Reason: Language match"
    assert (old_notice.title, old_notice.body) == ("Lead reassigned", f"{row.lead_code} has moved to another counselor. Reason: Language match")
    timeline = (await client.get(f"{url}/timeline?limit=100")).json()["items"]
    changes = [t for t in timeline if t["kind"] == "handover"]
    assert changes[0]["from_value"] == str(counselor.id) and changes[0]["to_value"] == str(other.id) and changes[0]["reason"] == "Language match"
    assert (await client.patch(url, json={"owner_id": None, "owner_reason": "Lead paused"})).status_code == 200
    removed = [t for t in (await client.get(f"{url}/timeline?limit=100")).json()["items"] if t["kind"] == "handover"][0]
    assert (removed["from_value"], removed["to_value"], removed["reason"]) == (str(other.id), "", "Lead paused")
    assert (await notices(db_session, other))[-1].title == "Lead reassigned"
