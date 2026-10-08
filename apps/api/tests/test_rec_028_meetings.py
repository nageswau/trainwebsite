"""rec-028 -- company meetings (spec §1-§3; DEC-SCOPE-133 MT1-MT10): schedule, participants, the pipeline move (AC1), reschedule history,
the outcome with a next action (AC2), cancel, the lists and the roles. The shared test database is never truncated, so every list
assertion uses a recruiter created by the test."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, RecruiterFollowUp, RecruiterMeeting
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user

COMPANIES = "/api/v1/recruiter/companies"
MEETINGS = "/api/v1/recruiter/meetings"
TYPES = ["company_meeting", "hr_meeting", "requirement_discussion", "recruitment_presentation", "contract_discussion",
         "campus_recruitment_discussion", "placement_drive_discussion"]


def soon(**delta) -> str:
    return (datetime.now(UTC) + (timedelta(**delta) if delta else timedelta(days=1))).isoformat()


def m_url(meeting_id, action: str = "") -> str:
    return f"{MEETINGS}/{meeting_id}{'/' + action if action else ''}"


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _company(client, **body) -> dict:
    response = await client.post(COMPANIES, json={"name": f"MT {uuid.uuid4().hex[:8]} Pvt", **body})
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _contact(client, company_id, name="Priya") -> dict:
    response = await client.post(f"{COMPANIES}/{company_id}/contacts", json={"name": name})
    assert response.status_code == 201, response.text
    return next(c for c in response.json()["items"] if c["name"] == name)


async def _schedule(client, company_id, **over):
    body = {"meeting_type": "contract_discussion", "starts_at": soon(), "mode": "Online"} | over
    return await client.post(f"{COMPANIES}/{company_id}/meetings", json=body)


async def _started(db, meeting_id) -> None:
    """Moves the start into the past -- the only way to record an outcome in a test (the API refuses a past start)."""
    await db.execute(update(RecruiterMeeting).where(RecruiterMeeting.id == uuid.UUID(meeting_id)).values(starts_at=datetime.now(UTC) - timedelta(hours=1)))
    await db.commit()


async def _stage(client, company_id) -> str:
    return (await client.get(f"{COMPANIES}/{company_id}")).json()["company"]["stage"]


# --- schedule (MT1-MT5, AC1) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_contract_discussion_with_two_contacts_moves_the_company_to_meeting_scheduled(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    priya, ravi = await _contact(client, company["id"]), await _contact(client, company["id"], "Ravi")
    colleague = await make_recruiter(db_session)
    response = await _schedule(client, company["id"], contact_id=priya["id"], participant_contact_ids=[ravi["id"]],
                               participant_user_ids=[str(colleague.id)], mode="In person", location="Pune office",
                               purpose="Fee per hire\nand terms")
    assert response.status_code == 201, response.text
    m = response.json()
    assert m["code"].startswith("MTG-") and m["status"] == "scheduled" and m["meeting_type"] == "contract_discussion"
    assert m["contact"] == {"id": priya["id"], "name": "Priya"} and m["location"] == "Pune office" and m["purpose"] == "Fee per hire\nand terms"
    assert sorted(c["name"] for c in m["participants"]["contacts"]) == ["Priya", "Ravi"]  # the primary contact is always a participant
    assert [r["id"] for r in m["participants"]["recruiters"]] == [str(colleague.id)]
    assert m["can_change"] is True and m["can_record_outcome"] is False
    assert [h["event"] for h in m["history"]] == ["scheduled"] and m["created_by"]["id"] == str(recruiter.id)
    assert await _stage(client, company["id"]) == "meeting_scheduled"  # AC1
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == m["id"], AuditLog.action == "recruiter_meeting.create"))
    assert audit.metadata_json["meeting_type"] == "contract_discussion" and "Fee" not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_scheduling_never_moves_a_company_already_past_meeting_scheduled(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    move = await client.post(f"{COMPANIES}/{company['id']}/stage", json={"from_stage": "new_lead", "to_stage": "requirement_discussion"})
    assert move.status_code == 200, move.text
    assert (await _schedule(client, company["id"])).status_code == 201
    assert await _stage(client, company["id"]) == "requirement_discussion"


@pytest.mark.asyncio
async def test_the_seven_source_types_and_three_modes_are_accepted_and_others_refused(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    for meeting_type in TYPES:
        assert (await _schedule(client, company["id"], meeting_type=meeting_type)).status_code == 201
    for mode in ("Online", "Phone", "In person"):
        assert (await _schedule(client, company["id"], mode=mode)).status_code == 201
    assert (await _schedule(client, company["id"], meeting_type="lunch")).json()["detail"][0]["loc"] == ["body", "meeting_type"]
    assert (await _schedule(client, company["id"], mode="Fax")).status_code == 422


@pytest.mark.asyncio
async def test_a_start_in_the_past_or_beyond_a_year_and_an_unsafe_link_are_422_on_the_field(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    for start in (soon(minutes=-5), soon(days=400)):
        response = await _schedule(client, company["id"], starts_at=start)
        assert response.status_code == 422 and response.json()["detail"][0]["loc"] == ["body", "starts_at"]
    response = await _schedule(client, company["id"], meeting_url="javascript:alert(1)")
    assert response.status_code == 422 and response.json()["detail"][0]["loc"] == ["body", "meeting_url"]
    ok = await _schedule(client, company["id"], meeting_url="https://meet.example.com/abc")
    assert ok.status_code == 201 and ok.json()["meeting_url"] == "https://meet.example.com/abc"


@pytest.mark.asyncio
async def test_a_participant_contact_from_another_company_is_422(client, db_session):
    await _team(client, db_session)
    company, other = await _company(client), await _company(client)
    stranger = await _contact(client, other["id"], "Stranger")
    for body in ({"participant_contact_ids": [stranger["id"]]}, {"contact_id": stranger["id"]}):
        response = await _schedule(client, company["id"], **body)
        assert response.status_code == 422, response.text
        assert response.json()["detail"][0]["loc"][1] in ("participant_contact_ids", "contact_id")


@pytest.mark.asyncio
async def test_an_inactive_contact_or_a_non_recruiter_participant_is_422(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await _contact(client, company["id"])  # the primary
    contact = await _contact(client, company["id"], "Ravi")
    assert (await client.patch(f"/api/v1/recruiter/contacts/{contact['id']}", json={"active": False})).status_code == 200
    assert (await _schedule(client, company["id"], participant_contact_ids=[contact["id"]])).status_code == 422
    student = await make_user(db_session, "it_student", "it")
    inactive = await make_recruiter(db_session, active=False)
    for user in (student, inactive):
        response = await _schedule(client, company["id"], participant_user_ids=[str(user.id)])
        assert response.status_code == 422 and response.json()["detail"][0]["loc"] == ["body", "participant_user_ids"]


# --- roles and scope (MT9) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_and_assigned_bdm_read_but_cannot_write(client, db_session):
    manager, _ = await _team(client, db_session)
    bdm = await make_user(db_session, "bdm", "it")
    company = await _company(client, assigned_bdm_user_id=str(bdm.id))
    m = (await _schedule(client, company["id"])).json()
    for reader in (manager, bdm):
        await login(client, reader)
        page = (await client.get(f"{COMPANIES}/{company['id']}/meetings")).json()
        assert [i["id"] for i in page["items"]] == [m["id"]] and page["items"][0]["can_change"] is False
        assert (await client.get(m_url(m["id"]))).status_code == 200
        assert (await _schedule(client, company["id"])).status_code == 403
        assert (await client.patch(m_url(m["id"]), json={"purpose": "x"})).status_code == 403
        assert (await client.post(m_url(m["id"], "outcome"), json={"outcome": "x"})).status_code == 403
        assert (await client.post(m_url(m["id"], "cancel"), json={"reason": "x"})).status_code == 403


@pytest.mark.asyncio
async def test_another_recruiter_gets_404_and_other_roles_403(client, db_session):
    manager, _ = await _team(client, db_session)
    company = await _company(client)
    m = (await _schedule(client, company["id"])).json()
    await login(client, await make_recruiter(db_session, manager))
    assert (await client.get(f"{COMPANIES}/{company['id']}/meetings")).status_code == 404
    assert (await client.get(m_url(m["id"]))).status_code == 404
    assert (await _schedule(client, company["id"])).status_code == 404
    assert (await client.patch(m_url(m["id"]), json={"purpose": "x"})).status_code == 404
    assert m["id"] not in [i["id"] for i in (await client.get(f"{MEETINGS}?view=upcoming")).json()["items"]]
    await as_role(client, db_session, "hr_team", "it")
    assert (await client.get(f"{MEETINGS}?view=upcoming")).status_code == 403
    assert (await client.get(f"{MEETINGS}/recruiter-options")).status_code == 403


@pytest.mark.asyncio
async def test_super_admin_schedules_and_an_archived_company_is_read_only(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    m = (await _schedule(client, company["id"])).json()
    await client.post(f"{COMPANIES}/{company['id']}/archive")
    assert (await client.get(f"{COMPANIES}/{company['id']}/meetings")).json()["items"][0]["can_change"] is False
    assert (await _schedule(client, company["id"])).status_code == 409
    assert (await client.post(m_url(m["id"], "cancel"), json={"reason": "x"})).status_code == 409
    other = await _company(client)
    await as_role(client, db_session, "super_admin", "global")
    response = await _schedule(client, other["id"])
    assert response.status_code == 201 and response.json()["can_change"] is True


# --- reschedule / edit (MT3, MT5, MT6) ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rescheduling_keeps_the_history_and_edits_replace_participants(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    priya, ravi = await _contact(client, company["id"]), await _contact(client, company["id"], "Ravi")
    m = (await _schedule(client, company["id"], participant_contact_ids=[priya["id"]])).json()
    new_start = soon(days=3)
    response = await client.patch(m_url(m["id"]), json={"starts_at": new_start, "reschedule_reason": "Client asked", "participant_contact_ids": [ravi["id"]]})
    assert response.status_code == 200, response.text
    out = response.json()
    assert [c["name"] for c in out["participants"]["contacts"]] == ["Ravi"]
    assert [h["event"] for h in out["history"]] == ["scheduled", "rescheduled"]
    moved = out["history"][1]
    assert moved["old_starts_at"] is not None and moved["new_starts_at"] == out["starts_at"] and moved["reason"] == "Client asked"
    assert (await client.patch(m_url(m["id"]), json={"starts_at": soon(minutes=-1)})).json()["detail"][0]["loc"] == ["body", "starts_at"]
    assert (await client.patch(m_url(m["id"]), json={"mode": None})).status_code == 422
    same = await client.patch(m_url(m["id"]), json={"starts_at": out["starts_at"], "purpose": "Agenda"})
    assert [h["event"] for h in same.json()["history"]] == ["scheduled", "rescheduled"] and same.json()["purpose"] == "Agenda"


# --- outcome (MT7, AC2) and cancel ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_outcome_with_a_next_action_creates_a_follow_up(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    priya = await _contact(client, company["id"])
    m = (await _schedule(client, company["id"], contact_id=priya["id"])).json()
    early = await client.post(m_url(m["id"], "outcome"), json={"outcome": "Agreed"})
    assert early.status_code == 422  # not started yet
    await _started(db_session, m["id"])
    assert (await client.get(m_url(m["id"]))).json()["can_record_outcome"] is True
    missing = await client.post(m_url(m["id"], "outcome"), json={"outcome": "Agreed", "next_action": "Send the MoU draft"})
    assert missing.status_code == 422 and {e["loc"][1] for e in missing.json()["detail"]} >= {"next_action_due_at"}
    due = soon(days=2)
    response = await client.post(m_url(m["id"], "outcome"), json={
        "outcome": "Agreed on 8.33%", "next_action": "Send the MoU draft", "next_action_due_at": due, "next_action_reason": "contract_mou"})
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["status"] == "completed" and out["outcome"] == "Agreed on 8.33%" and out["follow_up"] is not None
    assert out["can_change"] is False and [h["event"] for h in out["history"]][-1] == "completed"
    fu = await db_session.scalar(select(RecruiterFollowUp).where(RecruiterFollowUp.id == uuid.UUID(out["follow_up"]["id"])))
    assert fu.reason == "contract_mou" and fu.notes == "Send the MoU draft" and fu.contact_id == uuid.UUID(priya["id"]) and fu.status == "open"
    company_after = (await client.get(f"{COMPANIES}/{company['id']}")).json()["company"]
    assert company_after["next_follow_up_at"] is not None
    assert (await client.post(m_url(m["id"], "outcome"), json={"outcome": "Again"})).status_code == 409
    assert (await client.post(m_url(m["id"], "cancel"), json={"reason": "x"})).status_code == 409


@pytest.mark.asyncio
async def test_outcome_without_next_action_creates_no_follow_up_and_cancel_needs_a_reason(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    m = (await _schedule(client, company["id"])).json()
    await _started(db_session, m["id"])
    out = (await client.post(m_url(m["id"], "outcome"), json={"outcome": "Not interested yet"})).json()
    assert out["status"] == "completed" and out["follow_up"] is None and out["next_action"] is None
    other = (await _schedule(client, company["id"])).json()
    assert (await client.post(m_url(other["id"], "cancel"), json={})).status_code == 422
    cancelled = await client.post(m_url(other["id"], "cancel"), json={"reason": "HR on leave"})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled" and cancelled.json()["cancel_reason"] == "HR on leave"
    assert (await client.patch(m_url(other["id"]), json={"purpose": "x"})).status_code == 409


# --- lists (MT10) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_four_views_and_their_counts(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    upcoming = (await _schedule(client, company["id"])).json()
    waiting = (await _schedule(client, company["id"])).json()
    await _started(db_session, waiting["id"])
    done = (await _schedule(client, company["id"])).json()
    await _started(db_session, done["id"])
    await client.post(m_url(done["id"], "outcome"), json={"outcome": "Good"})
    gone = (await _schedule(client, company["id"])).json()
    await client.post(m_url(gone["id"], "cancel"), json={"reason": "Postponed"})
    expected = {"upcoming": upcoming, "awaiting_outcome": waiting, "completed": done, "cancelled": gone}
    for view, meeting in expected.items():
        page = (await client.get(f"{MEETINGS}?view={view}")).json()
        assert [i["id"] for i in page["items"]] == [meeting["id"]], view
        assert page["counts"] == {"upcoming": 1, "awaiting_outcome": 1, "completed": 1, "cancelled": 1}
    company_page = (await client.get(f"{COMPANIES}/{company['id']}/meetings")).json()
    assert [i["id"] for i in company_page["items"][:2]] == [waiting["id"], upcoming["id"]] and company_page["total"] == 4


@pytest.mark.asyncio
async def test_recruiter_options_list_active_placement_users_by_name(client, db_session):
    await _team(client, db_session)
    name = f"Zed {uuid.uuid4().hex[:6]}"
    active = await make_recruiter(db_session, name=name)
    await make_recruiter(db_session, name=f"{name} gone", active=False)
    page = (await client.get(f"{MEETINGS}/recruiter-options", params={"q": name})).json()
    assert page["items"] == [{"id": str(active.id), "full_name": name}] and page["total"] == 1
