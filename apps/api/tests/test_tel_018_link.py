"""tel-018 -- the counselor's student link, the computed conversion (T5, T20, T29; DEC-SCOPE-099 HO1-HO3; AC3-AC5), suggestions and
the read-only milestones."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry, LeadStageHistory
from app.services import lead_handover
from tests.bdm017_helpers import conversion
from tests.tel004_helpers import make_user
from tests.tel018_helpers import apply_overseas, as_user, c_url, enrol, handover, make_counselor, make_student, setup


async def _with_counselor(client, db, division="it", status="counselling_completed", **lead_over):
    manager, tel, counselor, lead = await setup(db, division, status=status, **lead_over)
    assert (await handover(client, tel, lead, counselor)).status_code == 200
    await as_user(client, counselor)
    return manager, tel, counselor, lead


async def _status(db, lead_id) -> str:
    return await db.scalar(select(Enquiry.status).where(Enquiry.id == lead_id).execution_options(populate_existing=True))


async def link(client, lead, student):
    return await client.post(c_url(lead.id, "/student-link"), json={"student_id": str(student.id)})


@pytest.mark.asyncio
async def test_the_counselor_links_a_student_and_the_lead_moves_to_application_enrollment(client, db_session):
    """AC3 (first half)."""
    _, _, counselor, lead = await _with_counselor(client, db_session)
    student = await make_student(db_session)
    response = await link(client, lead, student)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["converted_user"]["id"]) == ("application_enrollment", str(student.id))
    assert body["permissions"] == {"return": False, "link": False, "unlink": True}
    assert body["milestones"]["student"]["id"] == str(student.id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(lead.id), AuditLog.action == "lead.convert"))
    assert (audit.user_id, audit.metadata_json) == (counselor.id, {"converted_user_id": str(student.id)})


@pytest.mark.asyncio
async def test_an_active_enrolment_converts_the_lead_on_the_next_read(client, db_session):
    """AC3 (second half): computed and recorded once, by the system."""
    _, _, _, lead = await _with_counselor(client, db_session)
    student = await make_student(db_session)
    await enrol(db_session, student, status="pending_consent")  # HO3: not yet an enrolment
    assert (await link(client, lead, student)).json()["status"] == "application_enrollment"
    assert (await client.get(c_url(lead.id))).json()["status"] == "application_enrollment"
    await enrol(db_session, student)
    body = (await client.get(c_url(lead.id))).json()
    assert (body["status"], body["status_label"]) == ("converted", "Converted")
    assert [m["kind"] for m in body["milestones"]["items"]] == ["enrollment", "enrollment"]
    rows = (await db_session.scalars(select(LeadStageHistory).where(LeadStageHistory.lead_id == lead.id, LeadStageHistory.event == "converted"))).all()
    assert [(r.from_stage, r.actor_user_id) for r in rows] == [("application_enrollment", None)]


@pytest.mark.asyncio
async def test_an_existing_enrolment_converts_at_link_time(client, db_session):
    """HO3: an enrolment that predates the link counts."""
    _, _, _, lead = await _with_counselor(client, db_session)
    student = await make_student(db_session)
    await enrol(db_session, student)
    assert (await link(client, lead, student)).json()["status"] == "converted"


@pytest.mark.asyncio
async def test_an_enrolled_overseas_application_converts_and_milestones_show_the_visa(client, db_session):
    _, _, _, lead = await _with_counselor(client, db_session, "overseas")
    student = await make_student(db_session, "overseas")
    application = await apply_overseas(db_session, student, status="offer_received", visa="checklist")
    assert (await link(client, lead, student)).json()["status"] == "application_enrollment"
    application.status = "enrolled"
    await db_session.commit()
    body = (await client.get(c_url(lead.id))).json()
    assert body["status"] == "converted"
    assert [(m["kind"], m["status"]) for m in body["milestones"]["items"]] == [("application", "enrolled"), ("visa", "checklist")]


@pytest.mark.asyncio
async def test_the_beat_sweep_converts_leads_nobody_opened(db_session, client):
    _, _, _, lead = await _with_counselor(client, db_session)
    student = await make_student(db_session)
    assert (await link(client, lead, student)).status_code == 200
    await enrol(db_session, student)
    assert await lead_handover.sweep_conversions(db_session) >= 1
    assert await _status(db_session, lead.id) == "converted"


@pytest.mark.asyncio
async def test_a_student_linked_to_another_lead_is_409(client, db_session):
    """AC4."""
    _, _, first_counselor, first = await _with_counselor(client, db_session)
    student = await make_student(db_session)
    assert (await link(client, first, student)).status_code == 200
    _, _, _, second = await _with_counselor(client, db_session)
    response = await link(client, second, student)
    assert (response.status_code, response.json()["detail"]) == (409, "This student is already linked to another lead")
    await as_user(client, first_counselor)
    response = await link(client, first, await make_student(db_session))
    assert (response.status_code, response.json()["detail"]) == (409, "Unlink the current student first")


@pytest.mark.asyncio
async def test_the_student_must_be_active_and_of_the_leads_division(client, db_session):
    _, _, _, lead = await _with_counselor(client, db_session)
    for target in (await make_student(db_session, "overseas"), await make_student(db_session, active=False), await make_user(db_session, "trainer", "it")):
        response = await link(client, lead, target)
        assert (response.status_code, response.json()["detail"]) == (422, "Enter the email of an active student account in this lead's division")


@pytest.mark.asyncio
async def test_the_counselor_unlinks_before_conversion_only(client, db_session):
    """HO1 / HO2."""
    _, _, _, lead = await _with_counselor(client, db_session)
    student = await make_student(db_session)
    assert (await link(client, lead, student)).status_code == 200
    response = await client.delete(c_url(lead.id, "/student-link"))
    assert (response.status_code, response.json()["status"], response.json()["converted_user"]) == (200, "follow_up", None)
    assert (await link(client, lead, student)).status_code == 200
    await enrol(db_session, student)
    assert (await client.get(c_url(lead.id))).json()["status"] == "converted"
    response = await client.delete(c_url(lead.id, "/student-link"))
    assert (response.status_code, response.json()["detail"]) == (409, "Only an admin can unlink a converted lead")


@pytest.mark.asyncio
async def test_the_admin_unlinks_a_converted_lead_back_to_follow_up(client, db_session):
    """HO2, and AC5: the admin link follows the same rules (conversion computed at link time)."""
    admin = await make_user(db_session, "it_admin", "it")
    _, _, _, lead = await setup(db_session, status="counselling_completed")
    student = await make_student(db_session)
    await enrol(db_session, student)
    await as_user(client, admin)
    response = await client.post(conversion(lead.id), json={"student_email": student.email})
    assert (response.status_code, response.json()["status"]) == (200, "converted")
    response = await client.delete(conversion(lead.id))
    assert (response.status_code, response.json()["status"], response.json()["converted_user"]) == (200, "follow_up", None)


@pytest.mark.asyncio
async def test_suggestions_match_the_leads_email_or_mobile_and_search(client, db_session):
    _, _, _, lead = await _with_counselor(client, db_session, phone="98765 43210")
    by_email = await make_student(db_session)
    by_email.email = lead.email
    by_phone = await make_student(db_session, phone="+91 98765 43210")
    other_division = await make_student(db_session, "overseas", phone="+91 98765 43210")
    await db_session.commit()
    items = (await client.get(c_url(lead.id, "/link-suggestions"))).json()["items"]
    ids = {i["id"] for i in items}
    assert {str(by_email.id), str(by_phone.id)} <= ids and str(other_division.id) not in ids
    assert all(i["linked_elsewhere"] is False for i in items if i["id"] in {str(by_email.id), str(by_phone.id)})
    found = (await client.get(c_url(lead.id, "/link-suggestions"), params={"q": by_phone.email.upper()})).json()["items"]
    assert [i["id"] for i in found] == [str(by_phone.id)]
    assert (await client.get(c_url(lead.id, "/link-suggestions"), params={"q": "ab"})).status_code == 422


@pytest.mark.asyncio
async def test_link_routes_are_the_assigned_counselors_only(client, db_session):
    manager, tel, _, lead = await _with_counselor(client, db_session)
    student = await make_student(db_session)
    await as_user(client, await make_counselor(db_session, "it"))
    assert (await link(client, lead, student)).status_code == 404
    assert (await client.get(c_url(lead.id, "/link-suggestions"))).status_code == 404
    for actor in (tel, manager):
        await as_user(client, actor)
        assert (await link(client, lead, student)).status_code == 403


@pytest.mark.asyncio
async def test_the_telecaller_sees_the_milestones_read_only(client, db_session):
    _, tel, _, lead = await _with_counselor(client, db_session)
    student = await make_student(db_session)
    assert (await link(client, lead, student)).status_code == 200
    await as_user(client, tel)
    body = (await client.get(f"/api/v1/telecaller/leads/{lead.id}")).json()
    assert (body["read_only"], body["milestones"]["student"]["id"]) == (True, str(student.id))
