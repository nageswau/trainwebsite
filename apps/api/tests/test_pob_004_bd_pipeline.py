"""pob-004 (DEC-SCOPE-417) -- BD stages, client status, loss/inactive reasons and the auto-inactive sweep. Names are unique per test (shared DB)."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import (
    AuditLog,
    Company,
    CompanyStageHistory,
    Job,
    JobApplication,
    JobOffer,
    RecCompanyInactiveReason,
    RecCompanyLostReason,
    RecContactRole,
    RecruiterFollowUp,
)
from app.recruiter_stages import CLIENT_LABELS, LABELS, MANUAL, ORDER
from app.services import company_pipeline
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user
from tests.rec038_helpers import make_candidate

BASE = "/api/v1/recruiter/companies"
BOARD = "/api/v1/recruiter/pipeline"
REQUIREMENTS = "/api/v1/recruiter/requirements"


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _company(client) -> dict:
    response = await client.post(BASE, json={"name": f"BD {uuid.uuid4().hex[:10]} Ltd"})
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _detail(client, company_id) -> dict:
    return (await client.get(f"{BASE}/{company_id}")).json()["company"]


async def _history(db, company_id):
    stmt = select(CompanyStageHistory).where(CompanyStageHistory.company_id == uuid.UUID(company_id)).order_by(CompanyStageHistory.position)
    return (await db.scalars(stmt.execution_options(populate_existing=True))).all()


async def _row(db, company_id) -> Company:
    return await db.scalar(select(Company).where(Company.id == uuid.UUID(company_id)).execution_options(populate_existing=True))


async def _reason(db, model=RecCompanyLostReason, *, active=True) -> uuid.UUID:
    row = model(name=f"Reason {uuid.uuid4().hex[:8]}", active=active)
    db.add(row)
    await db.commit()
    return row.id


async def _role(db) -> uuid.UUID:
    return await db.scalar(select(RecContactRole.id).where(RecContactRole.active.is_(True)).order_by(RecContactRole.sort_order).limit(1))


async def _requirement(client, company_id) -> str:
    made = await client.post(REQUIREMENTS, json={"company_id": company_id, "title": f"Dev {uuid.uuid4().hex[:6]}", "location": "Pune"})
    assert made.status_code == 201, made.text
    requirement_id = made.json()["requirement"]["id"] if "requirement" in made.json() else made.json()["id"]
    moved = await client.post(f"{REQUIREMENTS}/{requirement_id}/status", json={"status": "requirement_received"})
    assert moved.status_code == 200, moved.text
    return requirement_id


async def _joined(db, recruiter, requirement_id) -> None:
    candidate = await make_candidate(db, recruiter)
    application = JobApplication(job_id=uuid.UUID(requirement_id), candidate_id=candidate.id, status="joined")
    db.add(application)
    await db.flush()
    db.add(JobOffer(application_id=application.id, status="accepted", joining_status="joined", actual_joining_date=date.today()))
    await db.commit()


# --- catalogue and labels (D1) ---------------------------------------------------------------------------------------------------
def test_the_ladder_adds_the_bd_stages_in_spec_order_with_spec_labels():
    assert ORDER[:9] == (
        "new_lead", "research_completed", "hr_contact_identified", "contacted", "interested", "meeting_scheduled", "requirement_discussion",
        "vendor_registration", "requirement_received",
    )
    assert [LABELS[k] for k in ("new_lead", "research_completed", "hr_contact_identified", "contacted", "meeting_scheduled", "vendor_registration")] == [
        "Target Identified", "Research Completed", "HR Contact Identified", "Outreach Sent", "Meeting Booked", "Vendor Registration / Agreement",
    ]
    assert {"research_completed", "hr_contact_identified", "vendor_registration"} <= set(MANUAL)
    assert "active_client" not in ORDER and "inactive" not in ORDER and "follow_up_due" not in ORDER  # D2, D3, D11
    assert CLIENT_LABELS == {"prospect": "Prospect", "active_client": "Active Client", "repeat_business": "Repeat Business"}


@pytest.mark.asyncio
async def test_a_person_can_choose_a_new_stage(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    moved = await client.post(f"{BASE}/{company['id']}/stage", json={"from_stage": "new_lead", "to_stage": "research_completed"})
    assert moved.status_code == 200 and moved.json()["company"]["pipeline"]["stage_label"] == "Research Completed"


# --- automatic moves (AC1, D4) ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_contact_with_a_role_moves_the_company_once(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    plain = await client.post(f"{BASE}/{company['id']}/contacts", json={"name": "No Role", "mobile": "9000000001"})
    assert plain.status_code == 201, plain.text
    assert (await _detail(client, company["id"]))["stage"] == "new_lead"  # no role: nothing moves
    role = str(await _role(db_session))
    assert (await client.post(f"{BASE}/{company['id']}/contacts", json={"name": "HR One", "mobile": "9000000002", "role_id": role})).status_code == 201
    assert (await client.post(f"{BASE}/{company['id']}/contacts", json={"name": "HR Two", "mobile": "9000000003", "role_id": role})).status_code == 201
    assert (await _detail(client, company["id"]))["stage"] == "hr_contact_identified"
    assert [r.event for r in await _history(db_session, company["id"])] == ["hr_contact_added"]


@pytest.mark.asyncio
async def test_an_edit_that_sets_a_role_moves_the_company(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact_id = (await client.post(f"{BASE}/{company['id']}/contacts", json={"name": "Later Role", "mobile": "9000000004"})).json()["items"][0]["id"]
    edited = await client.patch(f"/api/v1/recruiter/contacts/{contact_id}", json={"role_id": str(await _role(db_session))})
    assert edited.status_code == 200, edited.text
    assert (await _detail(client, company["id"]))["stage"] == "hr_contact_identified"


@pytest.mark.asyncio
async def test_a_role_never_moves_a_company_past_the_stage(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await client.post(f"{BASE}/{company['id']}/stage", json={"from_stage": "new_lead", "to_stage": "interested"})
    await client.post(f"{BASE}/{company['id']}/contacts", json={"name": "HR", "mobile": "9000000005", "role_id": str(await _role(db_session))})
    assert (await _detail(client, company["id"]))["stage"] == "interested"


@pytest.mark.asyncio
@pytest.mark.parametrize("start", ["research_completed", "hr_contact_identified"])
async def test_a_first_call_still_moves_a_company_from_the_new_stages(client, db_session, start):
    await _team(client, db_session)
    company = await _company(client)
    await client.post(f"{BASE}/{company['id']}/stage", json={"from_stage": "new_lead", "to_stage": start})
    locked = await db_session.scalar(select(Company).where(Company.id == uuid.UUID(company["id"])).with_for_update().execution_options(populate_existing=True))
    assert await company_pipeline.apply_event(db_session, locked, "call_logged") is True
    assert locked.stage == "contacted"
    await db_session.commit()


@pytest.mark.asyncio
async def test_a_contract_sent_moves_to_vendor_registration_once_without_making_a_client(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    created = await client.post(f"{BASE}/{company['id']}/contracts", json={"status": "discussion"})
    assert created.status_code == 201, created.text
    assert (await _detail(client, company["id"]))["stage"] == "new_lead"
    for before, status in (("discussion", "proposal_sent"), ("proposal_sent", "contract_sent")):
        changed = await client.patch(f"{BASE}/{company['id']}/contracts", json={"from_status": before, "status": status})
        assert changed.status_code == 200, changed.text
    detail = await _detail(client, company["id"])
    assert detail["stage"] == "vendor_registration" and detail["client_status"] == "prospect"
    assert [r.event for r in await _history(db_session, company["id"])] == ["contract_registration"]


@pytest.mark.asyncio
async def test_a_contract_created_as_sent_moves_too(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    assert (await client.post(f"{BASE}/{company['id']}/contracts", json={"status": "contract_sent"})).status_code == 201
    assert (await _detail(client, company["id"]))["stage"] == "vendor_registration"


@pytest.mark.asyncio
async def test_a_vendor_side_agreement_never_moves_the_client_pipeline(client, db_session):
    """pob-010 V10: a `vendor_client` company's vendor agreement is not the client journey; its client contract still is."""
    await _team(client, db_session)
    response = await client.post(BASE, json={"name": f"BD {uuid.uuid4().hex[:10]} Ltd", "partner_type": "vendor_client", "vendor_locations": ["Goa"]})
    assert response.status_code == 201, response.text
    company = response.json()["company"]
    vendor = await client.post(f"{BASE}/{company['id']}/contracts?party=vendor", json={"status": "discussion"})
    assert vendor.status_code == 201, vendor.text
    for before, status in (("discussion", "proposal_sent"), ("proposal_sent", "contract_sent")):
        changed = await client.patch(f"{BASE}/{company['id']}/contracts?party=vendor", json={"from_status": before, "status": status})
        assert changed.status_code == 200, changed.text
    detail = await _detail(client, company["id"])
    assert detail["stage"] == "new_lead" and detail["client_status"] == "prospect"
    assert await _history(db_session, company["id"]) == []
    assert (await client.post(f"{BASE}/{company['id']}/contracts?party=client", json={"status": "contract_sent"})).status_code == 201
    assert (await _detail(client, company["id"]))["stage"] == "vendor_registration"


@pytest.mark.asyncio
async def test_a_signed_contract_makes_an_active_client(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    locked = await db_session.scalar(select(Company).where(Company.id == uuid.UUID(company["id"])).with_for_update().execution_options(populate_existing=True))
    await company_pipeline.contract_moved(db_session, locked, "signed", None)
    await company_pipeline.contract_moved(db_session, locked, "active", None)  # a repeat does nothing
    await db_session.commit()
    assert locked.client_status == "active_client" and locked.stage == "vendor_registration"
    assert [r.event for r in await _history(db_session, company["id"])] == ["contract_registration", "active_client"]


@pytest.mark.asyncio
async def test_first_requirement_makes_an_active_client_and_the_stage_still_follows_requirements(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await _requirement(client, company["id"])
    detail = await _detail(client, company["id"])
    assert detail["client_status"] == "active_client" and detail["client_status_label"] == "Active Client"
    assert detail["stage"] == "requirement_received"  # rec-005's driven stage is untouched
    await _requirement(client, company["id"])  # a second requirement, no joining yet
    assert (await _detail(client, company["id"]))["client_status"] == "active_client"
    events = [r.event for r in await _history(db_session, company["id"])]
    assert events.count("active_client") == 1 and "repeat_business" not in events
    locked = await db_session.scalar(select(Company).where(Company.id == uuid.UUID(company["id"])).with_for_update().execution_options(populate_existing=True))
    assert await company_pipeline.apply_event(db_session, locked, "jd_received") is True  # later events still fire
    await db_session.commit()


@pytest.mark.asyncio
async def test_a_second_requirement_after_a_joining_is_repeat_business_once(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    first = await _requirement(client, company["id"])
    await _joined(db_session, recruiter, first)
    await _requirement(client, company["id"])
    assert (await _detail(client, company["id"]))["client_status"] == "repeat_business"
    await _requirement(client, company["id"])
    events = [r.event for r in await _history(db_session, company["id"])]
    assert events.count("repeat_business") == 1


@pytest.mark.asyncio
async def test_the_joining_requirement_itself_is_not_repeat_business(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    first = await _requirement(client, company["id"])
    await _joined(db_session, recruiter, first)
    job = await db_session.get(Job, uuid.UUID(first))
    locked = await db_session.scalar(select(Company).where(Company.id == uuid.UUID(company["id"])).with_for_update().execution_options(populate_existing=True))
    await company_pipeline.requirement_received(db_session, locked, job, None)  # the same requirement arriving again
    await db_session.commit()
    assert locked.client_status == "active_client"


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ["lost", "inactive"])
async def test_a_flagged_company_never_moves_by_itself(client, db_session, flag):
    await _team(client, db_session)
    company = await _company(client)
    model = RecCompanyLostReason if flag == "lost" else RecCompanyInactiveReason
    assert (await client.post(f"{BASE}/{company['id']}/{flag}", json={"reason_id": str(await _reason(db_session, model))})).status_code == 200
    await client.post(f"{BASE}/{company['id']}/contacts", json={"name": "HR", "mobile": "9000000006", "role_id": str(await _role(db_session))})
    await _requirement(client, company["id"])
    detail = await _detail(client, company["id"])
    assert detail["stage"] == "new_lead" and detail["client_status"] == "prospect"


# --- Lost needs a catalogue reason (AC2, D6) -----------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lost_refuses_free_text_and_anything_but_an_active_lost_reason(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    url = f"{BASE}/{company['id']}/lost"
    assert (await client.post(url, json={"reason": "Free text"})).status_code == 422
    assert (await client.post(url, json={})).status_code == 422
    bad = [uuid.uuid4(), await _reason(db_session, active=False), await _reason(db_session, RecCompanyInactiveReason)]
    for reason_id in bad:
        response = await client.post(url, json={"reason_id": str(reason_id)})
        assert response.status_code == 422 and response.json()["detail"][0]["loc"] == ["body", "reason_id"], response.text
    assert (await _detail(client, company["id"]))["lost"] is False


@pytest.mark.asyncio
async def test_lost_stores_the_reason_and_a_rename_keeps_what_was_recorded(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    reason_id = await _reason(db_session)
    reason = await db_session.get(RecCompanyLostReason, reason_id)
    name = reason.name
    response = await client.post(f"{BASE}/{company['id']}/lost", json={"reason_id": str(reason_id), "note": "Went with Acme"})
    assert response.status_code == 200, response.text
    assert response.json()["company"]["pipeline"]["lost"]["reason"] == f"{name}: Went with Acme"
    row = await _row(db_session, company["id"])
    assert row.lost_reason_id == reason_id
    [entry] = await _history(db_session, company["id"])
    assert (entry.event, entry.reason, entry.actor_user_id) == ("lost", f"{name}: Went with Acme", recruiter.id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == company["id"], AuditLog.action == "recruiter_company.lost"))
    assert audit.metadata_json == {"stage": "new_lead", "reason_id": str(reason_id)}  # never the text
    reason.name = f"Renamed {uuid.uuid4().hex[:6]}"
    await db_session.commit()
    assert (await _detail(client, company["id"]))["pipeline"]["lost"]["reason"] == f"{name}: Went with Acme"


@pytest.mark.asyncio
async def test_a_lost_reason_without_a_note_is_just_its_name(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    reason_id = await _reason(db_session)
    name = (await db_session.get(RecCompanyLostReason, reason_id)).name
    response = await client.post(f"{BASE}/{company['id']}/lost", json={"reason_id": str(reason_id)})
    assert response.json()["company"]["pipeline"]["lost"]["reason"] == name


@pytest.mark.asyncio
async def test_a_long_note_is_refused(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    response = await client.post(f"{BASE}/{company['id']}/lost", json={"reason_id": str(await _reason(db_session)), "note": "x" * 301})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_pre_upgrade_free_text_lost_reason_still_reads_and_reopens(client, db_session):
    manager, _ = await _team(client, db_session)
    company = await _company(client)
    await db_session.execute(update(Company).where(Company.id == uuid.UUID(company["id"])).values(lost_at=datetime.now(UTC), lost_reason="Old typed reason"))
    await db_session.commit()
    assert (await _detail(client, company["id"]))["pipeline"]["lost"]["reason"] == "Old typed reason"
    await login(client, manager)
    assert (await client.post(f"{BASE}/{company['id']}/reopen", json={"reason": "Back"})).status_code == 200


# --- Inactive (D3, D7, D9) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_inactive_keeps_the_stage_and_only_a_manager_reopens(client, db_session):
    manager, recruiter = await _team(client, db_session)
    company = await _company(client)
    await client.post(f"{BASE}/{company['id']}/stage", json={"from_stage": "new_lead", "to_stage": "interested"})
    reason_id = await _reason(db_session, RecCompanyInactiveReason)
    name = (await db_session.get(RecCompanyInactiveReason, reason_id)).name
    response = await client.post(f"{BASE}/{company['id']}/inactive", json={"reason_id": str(reason_id)})
    assert response.status_code == 200, response.text
    body = response.json()["company"]
    assert body["inactive"] is True and body["stage"] == "interested" and body["pipeline"]["inactive"]["reason"] == name
    assert body["pipeline"]["can_move"] is False and body["pipeline"]["can_reopen"] is False
    conflict = await client.post(f"{BASE}/{company['id']}/stage", json={"from_stage": "interested", "to_stage": "contacted", "reason": "x"})
    assert conflict.status_code == 409 and conflict.json()["detail"]["code"] == "company_inactive"
    for flag, model in (("inactive", RecCompanyInactiveReason), ("lost", RecCompanyLostReason)):
        again = await client.post(f"{BASE}/{company['id']}/{flag}", json={"reason_id": str(await _reason(db_session, model))})
        assert again.status_code == 409 and again.json()["detail"]["code"] == "company_inactive"
    assert (await client.post(f"{BASE}/{company['id']}/reopen", json={"reason": "Mine"})).status_code == 403
    await login(client, manager)
    assert (await _detail(client, company["id"]))["pipeline"]["can_reopen"] is True
    reopened = await client.post(f"{BASE}/{company['id']}/reopen", json={"reason": "Hiring again"})
    assert reopened.status_code == 200 and reopened.json()["company"]["pipeline"]["inactive"] is None
    assert reopened.json()["company"]["stage"] == "interested"
    row = await _row(db_session, company["id"])
    assert (row.inactive_at, row.inactive_reason, row.inactive_reason_id) == (None, None, None)
    assert [r.event for r in await _history(db_session, company["id"])][-2:] == ["inactive", "reopen"]
    assert (await _history(db_session, company["id"]))[-2].actor_user_id == recruiter.id


@pytest.mark.asyncio
async def test_inactive_refusals(client, db_session):
    manager, _ = await _team(client, db_session)
    company = await _company(client)
    url = f"{BASE}/{company['id']}/inactive"
    assert (await client.post(url, json={"reason": "typed"})).status_code == 422
    wrong_list = await client.post(url, json={"reason_id": str(await _reason(db_session))})
    assert wrong_list.status_code == 422 and wrong_list.json()["detail"][0]["loc"] == ["body", "reason_id"]
    good = str(await _reason(db_session, RecCompanyInactiveReason))
    await login(client, manager)  # in scope but not `can_edit`: 403, as Lost
    assert (await client.post(url, json={"reason_id": good})).status_code == 403
    await _team(client, db_session)  # another recruiter: out of scope
    assert (await client.post(url, json={"reason_id": good})).status_code == 404
    await login(client, await make_user(db_session, "student", "it"))
    assert (await client.post(url, json={"reason_id": good})).status_code in (403, 404)


@pytest.mark.asyncio
async def test_a_lost_company_cannot_be_marked_inactive(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await client.post(f"{BASE}/{company['id']}/lost", json={"reason_id": str(await _reason(db_session))})
    response = await client.post(f"{BASE}/{company['id']}/inactive", json={"reason_id": str(await _reason(db_session, RecCompanyInactiveReason))})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "company_lost"


# --- the board (AC3, D3, D11) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_board_leaves_inactive_out_and_offers_the_filters(client, db_session):
    _, recruiter = await _team(client, db_session)
    open_co, dormant, lost, client_co = [await _company(client) for _ in range(4)]
    await client.post(f"{BASE}/{dormant['id']}/inactive", json={"reason_id": str(await _reason(db_session, RecCompanyInactiveReason))})
    await client.post(f"{BASE}/{lost['id']}/lost", json={"reason_id": str(await _reason(db_session))})
    await _requirement(client, client_co["id"])
    db_session.add(RecruiterFollowUp(company_id=uuid.UUID(open_co["id"]), reason="new_requirement", due_at=datetime.now(UTC) - timedelta(hours=1),
                                     created_by_user_id=recruiter.id))
    await db_session.commit()
    board = (await client.get(BOARD)).json()
    counts = {s["key"]: s["count"] for s in board["stages"]}
    assert counts["new_lead"] == 1 and counts["requirement_received"] == 1  # neither inactive nor lost
    assert board["total"] == 2 and board["lost_count"] == 1
    assert {b["key"]: (b["label"], b["count"]) for b in board["buckets"]} == {
        "active_client": ("Active Client", 1), "repeat_business": ("Repeat Business", 0), "follow_up_due": ("Follow-up Due", 1),
        "inactive": ("Inactive", 1), "lost": ("Lost", 1),
    }

    async def ids(stage):
        return [i["id"] for i in (await client.get(f"{BOARD}?stage={stage}")).json()["items"]]

    assert await ids("inactive") == [dormant["id"]] and await ids("active_client") == [client_co["id"]]
    assert await ids("repeat_business") == [] and await ids("follow_up_due") == [open_co["id"]]
    rows = {i["id"]: i for i in board["items"]}
    assert rows[open_co["id"]]["follow_up_due"] is True and rows[client_co["id"]]["follow_up_due"] is False
    assert rows[client_co["id"]]["client_status_label"] == "Active Client" and rows[open_co["id"]]["inactive"] is False
    assert (await _detail(client, open_co["id"]))["pipeline"]["follow_up_due"] is True
    assert (await _detail(client, client_co["id"]))["pipeline"]["follow_up_due"] is False


@pytest.mark.asyncio
async def test_board_filters_stay_within_the_callers_scope(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await client.post(f"{BASE}/{company['id']}/inactive", json={"reason_id": str(await _reason(db_session, RecCompanyInactiveReason))})
    await _team(client, db_session)
    assert (await client.get(f"{BOARD}?stage=inactive")).json()["items"] == []


@pytest.mark.asyncio
async def test_a_future_follow_up_is_not_due(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    db_session.add(RecruiterFollowUp(company_id=uuid.UUID(company["id"]), reason="new_requirement", due_at=datetime.now(UTC) + timedelta(days=2),
                                     created_by_user_id=recruiter.id))
    await db_session.commit()
    assert (await _detail(client, company["id"]))["pipeline"]["follow_up_due"] is False


# --- reason catalogues (D5) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["lost-reasons", "inactive-reasons"])
async def test_a_manager_manages_the_reasons_and_a_recruiter_only_reads_active_ones(client, db_session, kind):
    manager, recruiter = await _team(client, db_session)
    await login(client, manager)
    name = f"Reason {uuid.uuid4().hex[:8]}"
    created = await client.post(f"/api/v1/recruiter/catalogue/{kind}", json={"name": name})
    assert created.status_code == 201, created.text
    assert (await client.patch(f"/api/v1/recruiter/catalogue/{kind}/{created.json()['id']}", json={"active": False})).status_code == 200
    await login(client, recruiter)
    assert (await client.post(f"/api/v1/recruiter/catalogue/{kind}", json={"name": "Nope"})).status_code == 403
    listed = (await client.get(f"/api/v1/recruiter/catalogue/{kind}?limit=100")).json()["items"]
    assert name not in {i["name"] for i in listed} and listed  # seeded values


# --- the sweep (D8) --------------------------------------------------------------------------------------------------------------
OLD = timedelta(days=company_pipeline.INACTIVE_AFTER_DAYS + 1)


async def _dormant(db, **extra) -> Company:
    past = datetime.now(UTC) - OLD
    company = Company(name=f"Dormant {uuid.uuid4().hex[:10]}", created_at=past, stage_changed_at=past, **extra)
    db.add(company)
    await db.commit()
    return company


async def _refetch(db, company) -> Company:
    return await db.scalar(select(Company).where(Company.id == company.id).execution_options(populate_existing=True))


@pytest.mark.asyncio
async def test_the_sweep_flags_a_dormant_company_once_with_a_system_row(db_session):
    company = await _dormant(db_session)
    first = await company_pipeline.run_inactive_sweep()
    assert first["inactive"] >= 1
    row = await _refetch(db_session, company)
    assert row.inactive_at is not None and row.inactive_reason == company_pipeline.AUTO_INACTIVE_REASON and row.inactive_reason_id is None
    [entry] = (await db_session.scalars(select(CompanyStageHistory).where(CompanyStageHistory.company_id == company.id))).all()
    assert (entry.event, entry.actor_user_id, entry.from_stage, entry.to_stage) == ("inactive", None, "new_lead", "new_lead")
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(company.id), AuditLog.action == "recruiter_company.inactive"))
    assert audit.user_id is None
    await company_pipeline.run_inactive_sweep()
    assert len((await db_session.scalars(select(CompanyStageHistory).where(CompanyStageHistory.company_id == company.id))).all()) == 1


@pytest.mark.asyncio
async def test_the_sweep_spares_recent_or_live_companies(db_session):
    recruiter = await make_user(db_session, "placement_team", "global")
    recent_contact = await _dormant(db_session, last_contacted_at=datetime.now(UTC) - timedelta(days=3))
    fresh = Company(name=f"Fresh {uuid.uuid4().hex[:10]}")
    moved = await _dormant(db_session)
    await db_session.execute(update(Company).where(Company.id == moved.id).values(stage_changed_at=datetime.now(UTC)))
    live = await _dormant(db_session)
    followed = await _dormant(db_session)
    lost = await _dormant(db_session, lost_at=datetime.now(UTC) - OLD, lost_reason="Old")
    db_session.add_all([
        fresh,
        Job(company_id=live.id, title="Live", location="Pune", description="Role", skills=[], status="sourcing", created_at=datetime.now(UTC) - OLD, updated_at=datetime.now(UTC) - OLD),
        RecruiterFollowUp(company_id=followed.id, reason="new_requirement", due_at=datetime.now(UTC) - OLD, created_by_user_id=recruiter.id),
    ])  # fmt: skip
    await db_session.commit()
    await company_pipeline.run_inactive_sweep()
    for company in (recent_contact, fresh, moved, live, followed, lost):
        assert (await _refetch(db_session, company)).inactive_at is None, company.name
