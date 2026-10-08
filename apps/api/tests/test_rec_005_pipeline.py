"""rec-005 -- the company B2B pipeline (spec §2/§4; AC1-AC4; DEC-SCOPE-127 P1-P8). Names are unique per test (shared database)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company, CompanyStageHistory
from app.recruiter_stages import EVENTS, MANUAL, ORDER, STAGES
from app.services import company_pipeline
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user

BASE = "/api/v1/recruiter/companies"
BOARD = "/api/v1/recruiter/pipeline"


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _company(client) -> dict:
    response = await client.post(BASE, json={"name": f"Pipe {uuid.uuid4().hex[:10]} Ltd"})
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _move(client, company_id, from_stage, to_stage, reason=None):
    body = {"from_stage": from_stage, "to_stage": to_stage, **({"reason": reason} if reason is not None else {})}
    return await client.post(f"{BASE}/{company_id}/stage", json=body)


async def _history(db, company_id):
    stmt = select(CompanyStageHistory).where(CompanyStageHistory.company_id == uuid.UUID(company_id)).order_by(CompanyStageHistory.position)
    return (await db.scalars(stmt.execution_options(populate_existing=True))).all()


async def _locked(db, company_id) -> Company:
    return await db.scalar(select(Company).where(Company.id == uuid.UUID(company_id)).with_for_update().execution_options(populate_existing=True))


# --- catalogue (P1) -------------------------------------------------------------------------------------------------------------
def test_catalogue_is_the_13_source_stages_in_order():
    assert [label for _, label, _ in STAGES] == [
        "New Lead", "Contacted", "Interested", "Meeting Scheduled", "Requirement Discussion", "Requirement Received", "JD Received",
        "Candidates Sourcing", "Profiles Shared", "Interview", "Selected", "Joined", "Requirement Closed",
    ]
    assert MANUAL == ("contacted", "interested", "meeting_scheduled", "requirement_discussion")
    assert all(to in ORDER and sources <= set(ORDER) for sources, to in EVENTS.values())


# --- detail shape ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_new_company_starts_at_new_lead_with_the_stepper(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    p = company["pipeline"]
    assert p["stage"] == "new_lead" and p["stage_label"] == "New Lead" and p["lost"] is None
    assert p["can_move"] is True and p["can_reopen"] is False
    assert [s["state"] for s in p["steps"][:3]] == ["current", "upcoming", "upcoming"]
    assert {s["kind"] for s in p["steps"]} == {"start", "manual", "driven"}
    assert company["stage"] == "new_lead" and company["lost"] is False
    assert company["permissions"] == {"can_edit": True, "can_archive": True, "can_restore": False, "can_reassign": False}  # unchanged


# --- manual moves (AC1, AC2) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recruiter_moves_forward_and_history_records_it(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    response = await _move(client, company["id"], "new_lead", "contacted")
    assert response.status_code == 200, response.text
    p = response.json()["company"]["pipeline"]
    assert p["stage"] == "contacted" and [s["state"] for s in p["steps"][:3]] == ["done", "current", "upcoming"]
    [row] = await _history(db_session, company["id"])
    assert (row.from_stage, row.to_stage, row.event, row.actor_user_id, row.reason) == ("new_lead", "contacted", "manual", recruiter.id, None)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == company["id"], AuditLog.action == "recruiter_company.stage_changed"))
    assert audit.metadata_json == {"from": "new_lead", "to": "contacted", "backward": False, "reason": False}


@pytest.mark.asyncio
async def test_moving_back_needs_a_reason(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await _move(client, company["id"], "new_lead", "meeting_scheduled")
    refused = await _move(client, company["id"], "meeting_scheduled", "contacted")
    assert refused.status_code == 422 and refused.json()["detail"][0]["loc"] == ["body", "reason"]
    moved = await _move(client, company["id"], "meeting_scheduled", "contacted", "Contact left the company")
    assert moved.status_code == 200
    rows = await _history(db_session, company["id"])
    assert rows[-1].reason == "Contact left the company"


@pytest.mark.asyncio
@pytest.mark.parametrize("to_stage, message", [
    ("joined", "This stage moves with the company's requirements"),
    ("requirement_received", "This stage moves with the company's requirements"),
    ("new_lead", "New Lead is the starting stage"),
    ("won", "Choose a stage of the company pipeline"),
])
async def test_only_manual_stages_can_be_chosen(client, db_session, to_stage, message):
    await _team(client, db_session)
    company = await _company(client)
    response = await _move(client, company["id"], "new_lead", to_stage)
    assert response.status_code == 422
    assert message in response.json()["detail"][0]["msg"]
    assert await _history(db_session, company["id"]) == []


@pytest.mark.asyncio
async def test_same_stage_is_refused(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await _move(client, company["id"], "new_lead", "contacted")
    response = await _move(client, company["id"], "contacted", "contacted")
    assert response.status_code == 422 and "already at this stage" in response.json()["detail"][0]["msg"]


@pytest.mark.asyncio
async def test_a_stale_from_stage_is_409_naming_the_current_stage(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await _move(client, company["id"], "new_lead", "contacted")
    response = await _move(client, company["id"], "new_lead", "interested")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stage_changed" and response.json()["detail"]["current_stage"] == "contacted"


@pytest.mark.asyncio
async def test_no_manual_move_once_requirements_drive_the_stage(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    locked = await _locked(db_session, company["id"])
    assert await company_pipeline.apply_event(db_session, locked, "requirement_received") is True
    await db_session.commit()
    response = await _move(client, company["id"], "requirement_received", "requirement_discussion", "back")
    assert response.status_code == 422 and "moves with its requirements" in response.json()["detail"][0]["msg"]


@pytest.mark.asyncio
async def test_manager_and_bdm_cannot_move(client, db_session):
    manager, _ = await _team(client, db_session)
    bdm = await make_user(db_session, "bdm", "it")
    company = await _company(client)
    await db_session.execute(Company.__table__.update().where(Company.id == uuid.UUID(company["id"])).values(assigned_bdm_user_id=bdm.id))
    await db_session.commit()
    for actor in (manager, bdm):
        await login(client, actor)
        response = await _move(client, company["id"], "new_lead", "contacted")
        assert response.status_code == 403
    await login(client, bdm)
    detail = (await client.get(f"{BASE}/{company['id']}")).json()["company"]["pipeline"]
    assert detail["can_move"] is False and detail["can_reopen"] is False


@pytest.mark.asyncio
async def test_out_of_scope_company_is_404(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await _team(client, db_session)  # another team's recruiter
    assert (await _move(client, company["id"], "new_lead", "contacted")).status_code == 404
    assert (await client.get(f"{BASE}/{company['id']}/stage-history")).status_code == 404
    assert (await client.post(f"{BASE}/{company['id']}/lost", json={"reason": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_archived_company_cannot_move(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await client.post(f"{BASE}/{company['id']}/archive")
    assert (await _move(client, company["id"], "new_lead", "contacted")).status_code == 409


@pytest.mark.asyncio
async def test_unknown_body_fields_are_refused(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    response = await client.post(f"{BASE}/{company['id']}/stage", json={"from_stage": "new_lead", "to_stage": "contacted", "actor_user_id": "x"})
    assert response.status_code == 422


# --- lost / reopen (AC4, P5) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lost_needs_a_reason_and_keeps_the_stage(client, db_session):
    manager, recruiter = await _team(client, db_session)
    company = await _company(client)
    await _move(client, company["id"], "new_lead", "interested")
    for body in ({}, {"reason": "   "}):
        assert (await client.post(f"{BASE}/{company['id']}/lost", json=body)).status_code == 422
    response = await client.post(f"{BASE}/{company['id']}/lost", json={"reason": "Chose a competitor"})
    assert response.status_code == 200, response.text
    p = response.json()["company"]["pipeline"]
    assert p["stage"] == "interested" and p["lost"]["reason"] == "Chose a competitor" and p["can_move"] is False
    assert response.json()["company"]["lost"] is True
    assert (await client.post(f"{BASE}/{company['id']}/lost", json={"reason": "again"})).json()["detail"]["code"] == "company_lost"
    moved = await _move(client, company["id"], "interested", "contacted", "r")
    assert moved.status_code == 409 and moved.json()["detail"]["code"] == "company_lost"
    rows = await _history(db_session, company["id"])
    assert (rows[-1].event, rows[-1].from_stage, rows[-1].to_stage, rows[-1].actor_user_id) == ("lost", "interested", "interested", recruiter.id)


@pytest.mark.asyncio
async def test_only_a_manager_reopens(client, db_session):
    manager, recruiter = await _team(client, db_session)
    company = await _company(client)
    await client.post(f"{BASE}/{company['id']}/lost", json={"reason": "No budget"})
    refused = await client.post(f"{BASE}/{company['id']}/reopen", json={"reason": "Budget approved"})
    assert refused.status_code == 403
    await login(client, manager)
    detail = (await client.get(f"{BASE}/{company['id']}")).json()["company"]["pipeline"]
    assert detail["can_reopen"] is True and detail["can_move"] is False
    assert (await client.post(f"{BASE}/{company['id']}/reopen", json={})).status_code == 422
    response = await client.post(f"{BASE}/{company['id']}/reopen", json={"reason": "Budget approved"})
    assert response.status_code == 200, response.text
    assert response.json()["company"]["pipeline"]["lost"] is None and response.json()["company"]["pipeline"]["stage"] == "new_lead"
    again = await client.post(f"{BASE}/{company['id']}/reopen", json={"reason": "x"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "company_not_lost"
    rows = await _history(db_session, company["id"])
    assert (rows[-1].event, rows[-1].reason, rows[-1].actor_user_id) == ("reopen", "Budget approved", manager.id)


@pytest.mark.asyncio
async def test_super_admin_moves_and_reopens(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await _move(client, company["id"], "new_lead", "contacted")).status_code == 200
    assert (await client.post(f"{BASE}/{company['id']}/lost", json={"reason": "x"})).status_code == 200
    assert (await client.post(f"{BASE}/{company['id']}/reopen", json={"reason": "y"})).status_code == 200


# --- engine events (AC3, P2/P3) -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_events_drive_the_later_stages_forward_only(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    locked = await _locked(db_session, company["id"])
    assert await company_pipeline.apply_event(db_session, locked, "jd_received") is True  # jumps forward from New Lead
    assert await company_pipeline.apply_event(db_session, locked, "requirement_received") is False  # never backward
    assert await company_pipeline.apply_event(db_session, locked, "jd_received") is False  # a repeat does nothing
    assert await company_pipeline.apply_event(db_session, locked, "candidate_selected") is True
    await db_session.commit()
    rows = await _history(db_session, company["id"])
    assert [(r.from_stage, r.to_stage, r.event, r.actor_user_id) for r in rows] == [
        ("new_lead", "jd_received", "jd_received", None), ("jd_received", "selected", "candidate_selected", None)
    ]
    assert locked.stage == "selected"


@pytest.mark.asyncio
async def test_a_new_requirement_reopens_a_closed_pipeline(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    locked = await _locked(db_session, company["id"])
    assert await company_pipeline.apply_event(db_session, locked, "requirement_closed") is True
    assert await company_pipeline.apply_event(db_session, locked, "requirement_received") is True
    assert locked.stage == "requirement_received"
    await db_session.commit()


@pytest.mark.asyncio
async def test_first_call_moves_a_new_lead_to_contacted_only_once(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    locked = await _locked(db_session, company["id"])
    assert await company_pipeline.apply_event(db_session, locked, "call_logged") is True
    assert await company_pipeline.apply_event(db_session, locked, "call_logged") is False
    await db_session.commit()


@pytest.mark.asyncio
async def test_events_leave_a_lost_company_alone(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await client.post(f"{BASE}/{company['id']}/lost", json={"reason": "gone"})
    locked = await _locked(db_session, company["id"])
    assert await company_pipeline.apply_event(db_session, locked, "requirement_received") is False
    await db_session.commit()


@pytest.mark.asyncio
async def test_unknown_event_is_a_caller_bug(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    locked = await _locked(db_session, company["id"])
    with pytest.raises(KeyError):
        await company_pipeline.apply_event(db_session, locked, "won_the_lottery")
    await db_session.rollback()


# --- history --------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stage_history_is_newest_first_with_labels_and_actor(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    await _move(client, company["id"], "new_lead", "contacted")
    locked = await _locked(db_session, company["id"])
    await company_pipeline.apply_event(db_session, locked, "requirement_received")
    await db_session.commit()
    page = (await client.get(f"{BASE}/{company['id']}/stage-history?limit=1")).json()
    assert page["total"] == 2 and page["limit"] == 1
    [newest] = page["items"]
    assert newest["event"] == "requirement_received" and newest["actor"] is None and newest["to_label"] == "Requirement Received"
    older = (await client.get(f"{BASE}/{company['id']}/stage-history?offset=1")).json()["items"][0]
    assert older["actor"]["id"] == str(recruiter.id) and older["from_label"] == "New Lead"


# --- board (P7) -----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_board_counts_and_lists_by_stage_within_scope(client, db_session):
    manager, _ = await _team(client, db_session)
    first, second, lost, archived = [await _company(client) for _ in range(4)]
    await _move(client, first["id"], "new_lead", "contacted")
    await client.post(f"{BASE}/{lost['id']}/lost", json={"reason": "x"})
    await client.post(f"{BASE}/{archived['id']}/archive")
    board = (await client.get(BOARD)).json()
    counts = {s["key"]: s["count"] for s in board["stages"]}
    assert counts["new_lead"] == 1 and counts["contacted"] == 1 and board["lost_count"] == 1
    assert len(board["stages"]) == 13 and board["total"] == 2
    contacted = (await client.get(f"{BOARD}?stage=contacted")).json()
    assert [i["id"] for i in contacted["items"]] == [first["id"]] and contacted["items"][0]["stage_label"] == "Contacted"
    assert [i["id"] for i in (await client.get(f"{BOARD}?stage=lost")).json()["items"]] == [lost["id"]]
    assert (await client.get(f"{BOARD}?stage=won")).status_code == 422
    await login(client, manager)
    # The manager's scope includes the whole unassigned queue (shared DB): look at the one stage this test controls.
    team_board = (await client.get(f"{BOARD}?stage=contacted&limit=100")).json()
    assert first["id"] in {i["id"] for i in team_board["items"]} and second["id"] not in {i["id"] for i in team_board["items"]}
    await _team(client, db_session)  # another recruiter sees none of these
    assert (await client.get(BOARD)).json()["total"] == 0


@pytest.mark.asyncio
async def test_board_refuses_other_roles(client, db_session):
    await login(client, await make_user(db_session, "student", "it"))
    assert (await client.get(BOARD)).status_code == 403
