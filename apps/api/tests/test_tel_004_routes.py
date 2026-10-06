"""tel-004 -- the stage routes (spec §5; AC2-AC6, PL4, T23, T25): POST /telecaller/leads/{id}/stage, both stage-history reads, the admin
PATCH through the engine and bdm-017's link / unlink as pipeline events."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry
from tests.bdm017_helpers import ADMIN_LEADS, as_user, conversion, student_email
from tests.tel004_helpers import history_url, lead, make_telecaller, make_tl_manager, make_user, stage_url


async def _team(db):
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager), await make_telecaller(db, manager, team="overseas")


async def _status(db, row) -> str:
    return await db.scalar(select(Enquiry.status).where(Enquiry.id == row.id).execution_options(populate_existing=True))


# --- telecaller route: scope ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_telecaller_moves_own_lead_and_reads_its_history(client, db_session):
    _, tel, _ = await _team(db_session)
    row = await lead(db_session, telecaller=tel, status="contacted")
    await as_user(client, tel)
    response = await client.post(stage_url(row.id), json={"to_stage": "qualified"})
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"id", "status", "status_label", "stage_changed_at"}
    assert (response.json()["status"], response.json()["status_label"]) == ("qualified", "Qualified")
    assert (await client.post(stage_url(row.id), json={"to_stage": "lost", "reason": "  Joined elsewhere  "})).status_code == 200
    history = (await client.get(history_url(row.id))).json()
    assert history["total"] == 2
    assert [(h["from_stage"], h["to_stage"], h["to_label"], h["reason"], h["actor"]["id"]) for h in history["items"]] == [
        ("contacted", "qualified", "Qualified", None, str(tel.id)),
        ("qualified", "lost", "Lost", "Joined elsewhere", str(tel.id)),
    ]


@pytest.mark.asyncio
async def test_other_telecallers_and_unassigned_leads_are_404_for_a_telecaller(client, db_session):
    _, tel, other = await _team(db_session)
    theirs, unassigned = await lead(db_session, telecaller=other), await lead(db_session)
    await as_user(client, tel)
    for row in (theirs, unassigned):
        assert (await client.post(stage_url(row.id), json={"to_stage": "qualified"})).status_code == 404
        assert (await client.get(history_url(row.id))).status_code == 404
    assert (await client.post(stage_url(uuid.uuid4()), json={"to_stage": "qualified"})).status_code == 404


@pytest.mark.asyncio
async def test_manager_scope_is_direct_reports_and_their_teams_unassigned_queue(client, db_session):
    manager, tel, _ = await _team(db_session)
    stranger = await make_telecaller(db_session, await make_tl_manager(db_session))
    report_lead, queue_it = await lead(db_session, telecaller=tel), await lead(db_session)
    other_lead = await lead(db_session, telecaller=stranger)
    await as_user(client, manager)
    assert (await client.post(stage_url(report_lead.id), json={"to_stage": "interested"})).status_code == 200
    assert (await client.post(stage_url(queue_it.id), json={"to_stage": "interested"})).status_code == 200
    assert (await client.post(stage_url(other_lead.id), json={"to_stage": "interested"})).status_code == 404


@pytest.mark.asyncio
async def test_manager_without_reports_sees_no_queue_and_super_admin_sees_all(client, db_session):
    lonely = await make_tl_manager(db_session)
    row = await lead(db_session)
    await as_user(client, lonely)
    assert (await client.post(stage_url(row.id), json={"to_stage": "interested"})).status_code == 404
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    assert (await client.post(stage_url(row.id), json={"to_stage": "interested"})).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_admin", "it"), ("counselor", "it"), ("it_student", "it"), ("bdm_manager", "global")])
async def test_other_roles_are_403_on_the_telecaller_routes(client, db_session, role, division):
    row = await lead(db_session)
    await as_user(client, await make_user(db_session, role, division))
    assert (await client.post(stage_url(row.id), json={"to_stage": "qualified"})).status_code == 403
    assert (await client.get(history_url(row.id))).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client, db_session):
    row = await lead(db_session)
    client.cookies.clear()
    assert (await client.post(stage_url(row.id), json={"to_stage": "qualified"})).status_code == 401


# --- AC2-AC4 over HTTP ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rule_violations_are_422_and_telecaller_reopen_is_403(client, db_session):
    manager, tel, _ = await _team(db_session)
    row = await lead(db_session, telecaller=tel, status="contacted")
    await as_user(client, tel)
    for body in ({"to_stage": "converted"}, {"to_stage": "counselling_completed"}, {"to_stage": "application_enrollment"},
                 {"to_stage": "lost"}, {"to_stage": "lost", "reason": "   "}, {"to_stage": "qualified", "actor_user_id": str(manager.id)},
                 {"to_stage": "lost", "reason": "x" * 501}, {"to_stage": "Qualified"}):
        assert (await client.post(stage_url(row.id), json=body)).status_code == 422, body
    assert await _status(db_session, row) == "contacted"
    assert (await client.post(stage_url(row.id), json={"to_stage": "not_eligible", "reason": "Below minimum marks"})).status_code == 200
    response = await client.post(stage_url(row.id), json={"to_stage": "follow_up", "reason": "Please reopen"})
    assert (response.status_code, response.json()["detail"]) == (403, "Only a manager can reopen a closed lead")
    await as_user(client, manager)
    assert (await client.post(stage_url(row.id), json={"to_stage": "follow_up", "reason": "Marks re-checked"})).status_code == 200
    events = [h["event"] for h in (await client.get(history_url(row.id))).json()["items"]]
    assert events == ["manual", "reopen"]


# --- T25: admin PATCH through the engine ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_patch_follows_the_stage_rules(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    row = await lead(db_session, status="contacted")
    await as_user(client, admin)
    url = f"{ADMIN_LEADS}/{row.id}"
    assert (await client.patch(url, json={"status": "converted"})).status_code == 422
    assert (await client.patch(url, json={"status": "lost"})).status_code == 422
    assert (await client.patch(url, json={"status": 7})).status_code == 422
    assert (await client.patch(url, json={"status": "lost", "reason": "Duplicate enquiry"})).status_code == 200
    assert (await client.patch(url, json={"status": "follow_up", "reason": "Not a duplicate"})).status_code == 200  # admins reopen
    assert (await client.patch(url, json={"status": "follow_up", "owner_id": str(admin.id)})).status_code == 200  # same stage: no-op
    assert await _status(db_session, row) == "follow_up"
    history = (await client.get(history_url(row.id, admin=True))).json()
    assert [(h["to_stage"], h["event"], h["actor"]["id"]) for h in history["items"]] == [("lost", "manual", str(admin.id)),
                                                                                        ("follow_up", "reopen", str(admin.id))]
    audits = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == str(row.id), AuditLog.action == "lead.update"))).all()
    assert audits and all("reason" not in a for a in audits)  # reasons live in the history only


@pytest.mark.asyncio
async def test_admin_history_keeps_division_scope(client, db_session):
    row = await lead(db_session, division="overseas")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(history_url(row.id, admin=True))).status_code == 403
    assert (await client.get(history_url(uuid.uuid4(), admin=True))).status_code == 404
    await as_user(client, await make_user(db_session, "counselor", "it"))
    assert (await client.get(history_url(row.id, admin=True))).status_code == 403


@pytest.mark.asyncio
async def test_admin_rows_carry_the_stage_label(client, db_session):
    row = await lead(db_session, status="first_call_pending")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    item = next(i for i in (await client.get(ADMIN_LEADS, params={"q": row.lead_code})).json()["items"] if i["id"] == str(row.id))
    assert item["status_label"] == "First Call Pending"


# --- PL4: bdm-017 link / unlink are pipeline events ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_link_moves_to_application_enrollment_and_unlink_to_follow_up(client, db_session):
    row = await lead(db_session, status="interested")
    student = await make_user(db_session, "it_student", "it")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    response = await client.post(conversion(row.id), json={"student_email": student.email})
    assert (response.status_code, response.json()["status"]) == (200, "application_enrollment")
    response = await client.delete(conversion(row.id))
    assert (response.status_code, response.json()["status"]) == (200, "follow_up")
    events = [(h["to_stage"], h["event"]) for h in (await client.get(history_url(row.id, admin=True))).json()["items"]]
    assert events == [("application_enrollment", "student_linked"), ("follow_up", "student_unlinked")]


@pytest.mark.asyncio
async def test_linking_a_closed_lead_keeps_its_stage(client, db_session):
    row = await lead(db_session, status="lost")
    student = await make_user(db_session, "it_student", "it")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    response = await client.post(conversion(row.id), json={"student_email": student.email})
    assert (response.status_code, response.json()["status"]) == (200, "lost")


@pytest.mark.asyncio
async def test_a_taken_student_is_still_409_and_the_stage_is_unchanged(client, db_session):
    first, second = await lead(db_session, status="interested"), await lead(db_session, status="interested")
    student = await make_user(db_session, "it_student", "it")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.post(conversion(first.id), json={"student_email": student.email})).status_code == 200
    response = await client.post(conversion(second.id), json={"student_email": student.email})
    assert response.status_code == 409
    assert await _status(db_session, second) == "interested"
    assert (await client.post(conversion(second.id), json={"student_email": student_email()})).status_code == 422
