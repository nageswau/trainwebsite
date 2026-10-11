"""rec-027 -- the company timeline and the candidate timeline (spec §1-§2; TL1-TL10): every kind with time, actor and summary (AC1),
the tie order (AC2), out of scope → 404, the readers, masking for the BDM (TL4) and deleted calls (TL6). The shared test database is
never truncated, so every assertion is scoped to companies and candidates made here."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event

from app.core.database import engine
from app.models import (
    Company,
    CompanyStageHistory,
    JobApplication,
    JobStatusHistory,
    ProfileShare,
    ProfileShareItem,
    RecruiterCall,
    RecruiterContract,
    RecruiterContractEvent,
    RecruiterFollowUp,
)
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user
from tests.test_rec_017_tracking import _add, _candidate, _move, _requirement
from tests.test_rec_020_interviews import _interview
from tests.test_rec_022_offers import _offer, _status

COMPANIES = "/api/v1/recruiter/companies"
CANDIDATES = "/api/v1/recruiter/candidates"
CALLS = "/api/v1/recruiter/calls"
MESSAGES = "/api/v1/recruiter/messages"


def soon(**delta) -> str:
    return (datetime.now(UTC) + timedelta(days=2, **delta)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def timeline(client, kind: str, party_id, expected: int = 200, **params) -> dict:
    response = await client.get(f"/api/v1/recruiter/{kind}/{party_id}/timeline", params=params)
    assert response.status_code == expected, response.text
    return response.json()


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _company(client, **body) -> tuple[dict, dict]:
    response = await client.post(COMPANIES, json={"name": f"TL {uuid.uuid4().hex[:8]} Pvt", **body})
    assert response.status_code == 201, response.text
    company = response.json()["company"]
    contacts = (await client.post(f"{COMPANIES}/{company['id']}/contacts", json={"name": "Priya", "mobile": "+91 98765 43210"})).json()["items"]
    return company, contacts[0]


def summary(row: dict) -> tuple:
    return row["kind"], row["event"]


# --- AC1: every communication kind, with time, actor and summary --------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_call_then_a_whatsapp_read_newest_first_with_actor_and_summary(client, db_session):
    _, recruiter = await _team(client, db_session)
    company, contact = await _company(client)
    call = await client.post(CALLS, json={"contact_id": contact["id"], "outcome": "connected", "duration_seconds": 125, "notes": "Discussed the JD"})
    assert call.status_code == 201, call.text
    sent = await client.post(MESSAGES, json={"contact_id": contact["id"], "channel": "whatsapp", "body": "Profiles coming Friday"})
    assert sent.status_code == 201, sent.text

    page = await timeline(client, "companies", company["id"])
    rows = [r for r in page["items"] if r["kind"] in ("call", "message")]
    assert [summary(r) for r in rows] == [("message", "whatsapp"), ("call", "outgoing")]
    message, call_row = rows
    me = {"id": str(recruiter.id), "full_name": recruiter.full_name}
    assert message["actor"] == me and call_row["actor"] == me
    assert message["to_label"] == "Priya" and message["reason"] == "Profiles coming Friday" and message["at"]
    assert (call_row["from_value"], call_row["from_label"], call_row["to_label"]) == ("connected", "Connected", "Priya")
    assert call_row["duration_seconds"] == 125 and call_row["reason"] == "Discussed the JD"
    assert page["total"] == len(page["items"]) and page["limit"] == 50 and page["offset"] == 0


@pytest.mark.asyncio
async def test_meetings_follow_ups_requirements_shares_and_contracts_appear(client, db_session):
    _, recruiter = await _team(client, db_session)
    company, contact = await _company(client)
    meeting = await client.post(f"{COMPANIES}/{company['id']}/meetings", json={"meeting_type": "hr_meeting", "starts_at": soon(), "mode": "Online"})
    assert meeting.status_code == 201, meeting.text
    fu = await client.post(f"{COMPANIES}/{company['id']}/follow-ups", json={"due_at": soon(hours=3), "reason": "jd", "notes": "Chase the JD"})
    assert fu.status_code == 201, fu.text
    assert (await client.post(f"/api/v1/recruiter/follow-ups/{fu.json()['id']}/cancel", json={"reason": "Sent already"})).status_code == 200

    stored = await db_session.get(Company, uuid.UUID(company["id"]))
    job = await _requirement(db_session, recruiter, company=stored)
    db_session.add(JobStatusHistory(job_id=job.id, from_status=None, to_status="requirement_received", changed_by_user_id=recruiter.id))
    candidate = await _candidate(db_session, recruiter, mobile="+919812345678")
    application = JobApplication(job_id=job.id, candidate_id=candidate.id, status="profile_shared")
    contract = RecruiterContract(company_id=stored.id, created_by_user_id=recruiter.id, contract_document_key="secret/contract-key.pdf", contract_document_content_type="application/pdf")
    db_session.add_all([application, contract])
    await db_session.flush()
    db_session.add(RecruiterContractEvent(contract_id=contract.id, actor_user_id=recruiter.id, kind="created", to_status="discussion", changed=["fee_value"]))
    share = ProfileShare(job_id=job.id, company_id=stored.id, channel="other", shared_by_user_id=recruiter.id)
    db_session.add(share)
    await db_session.flush()
    db_session.add(
        ProfileShareItem(
            share_id=share.id,
            candidate_id=candidate.id,
            application_id=application.id,
            response="interested",
            feedback="Strong Java",
            responded_by_user_id=recruiter.id,
            responded_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    page = await timeline(client, "companies", company["id"])
    by = {summary(r): r for r in page["items"]}
    assert ("meeting", "scheduled") in by and by[("meeting", "scheduled")]["from_value"] == "hr_meeting"
    assert by[("meeting", "scheduled")]["scheduled_for"] is not None and by[("meeting", "scheduled")]["subject"]
    # Scheduling moved the company to Meeting Scheduled (rec-028 AC1): the stage entry sits above the meeting it came from (TL5).
    chain = [summary(r) for r in page["items"]]
    stage = next(r for r in page["items"] if r["kind"] == "stage" and r["to_value"] == "meeting_scheduled")
    assert stage["to_label"] == "Meeting Scheduled" and chain.index(summary(stage)) < chain.index(("meeting", "scheduled"))
    assert by[("follow_up", "scheduled")]["from_value"] == "jd" and by[("follow_up", "scheduled")]["reason"] == "Chase the JD"
    cancelled = by[("follow_up", "cancelled")]
    assert cancelled["reason"] == "Sent already" and cancelled["actor"]["id"] == str(recruiter.id)
    requirement = by[("requirement", None)]
    assert requirement["to_label"] == "Requirement Received" and job.requirement_code in requirement["subject"]
    assert by[("share", "other")]["subject"] and by[("share", "other")]["to_value"] == "1"
    response = by[("share_response", "interested")]
    assert response["to_label"] == candidate.name and response["reason"] == "Strong Java"
    contract_row = by[("contract", "created")]
    assert contract_row["to_label"] == "Discussion"
    body = str(page)
    assert "secret/contract-key.pdf" not in body and "fee_value" not in body  # TL4: no document key, no field list
    assert candidate.email not in body and "9812345678" not in body  # TL4: candidates by name only


# --- AC2 and the edges -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_equal_timestamps_read_in_causal_order_and_page_stably(client, db_session):
    _, recruiter = await _team(client, db_session)
    company, contact = await _company(client)
    when, cid = datetime(2026, 9, 14, 10, 0, tzinfo=UTC), uuid.UUID(company["id"])
    db_session.add_all(
        [
            RecruiterCall(company_id=cid, contact_id=uuid.UUID(contact["id"]), caller_user_id=recruiter.id, occurred_at=when, direction="outgoing", outcome="connected", created_at=when),
            CompanyStageHistory(company_id=cid, from_stage="new_lead", to_stage="contacted", event="call_logged", actor_user_id=recruiter.id, created_at=when),
            RecruiterFollowUp(company_id=cid, reason="jd", due_at=when + timedelta(days=1), created_by_user_id=recruiter.id, created_at=when),
        ]
    )
    await db_session.commit()

    page = await timeline(client, "companies", company["id"])
    kinds = [r["kind"] for r in page["items"]]
    assert kinds == ["stage", "follow_up", "call"]
    paged = [(await timeline(client, "companies", company["id"], limit=1, offset=i))["items"][0]["kind"] for i in range(3)]
    assert paged == kinds
    assert (await timeline(client, "companies", company["id"], limit=1, offset=3))["items"] == []


@pytest.mark.asyncio
async def test_a_deleted_call_is_excluded(client, db_session):
    await _team(client, db_session)
    company, contact = await _company(client)
    call = (await client.post(CALLS, json={"contact_id": contact["id"], "outcome": "busy"})).json()["call"]
    assert (await client.delete(f"{CALLS}/{call['id']}")).status_code == 204
    assert "call" not in [r["kind"] for r in (await timeline(client, "companies", company["id"]))["items"]]


@pytest.mark.asyncio
async def test_a_fixed_number_of_queries_whatever_the_data(client, db_session):
    await _team(client, db_session)
    company, contact = await _company(client)
    statements: list[str] = []

    def count(*args):
        statements.append(args[2])

    async def measure() -> int:
        statements.clear()
        event.listen(engine.sync_engine, "before_cursor_execute", count)
        try:
            await timeline(client, "companies", company["id"])
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", count)
        return len(statements)

    before = await measure()
    for outcome in ("busy", "no_answer", "connected"):
        assert (await client.post(CALLS, json={"contact_id": contact["id"], "outcome": outcome})).status_code == 201
    assert await measure() == before


# --- TL3: readers and scope --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_super_admin_and_the_assigned_bdm_read_another_recruiter_gets_404(client, db_session):
    manager, _ = await _team(client, db_session)
    bdm = await make_user(db_session, "bdm", "it")
    company, contact = await _company(client, assigned_bdm_user_id=str(bdm.id))
    assert (await client.post(CALLS, json={"contact_id": contact["id"], "outcome": "connected", "notes": "Hello"})).status_code == 201
    for reader in (manager, bdm):
        await login(client, reader)
        assert "call" in [r["kind"] for r in (await timeline(client, "companies", company["id"]))["items"]]
    await as_role(client, db_session, "super_admin", "global")
    assert (await timeline(client, "companies", company["id"]))["total"] == 1
    await login(client, await make_recruiter(db_session, manager))
    await timeline(client, "companies", company["id"], 404)
    await login(client, await make_user(db_session, "bdm", "it"))  # a BDM not assigned to it
    await timeline(client, "companies", company["id"], 404)


@pytest.mark.asyncio
async def test_unknown_or_malformed_ids_bad_paging_and_other_roles(client, db_session):
    await _team(client, db_session)
    company, _ = await _company(client)
    await timeline(client, "companies", uuid.uuid4(), 404)
    assert (await client.get(f"{COMPANIES}/not-a-uuid/timeline")).status_code == 422
    await timeline(client, "companies", company["id"], 422, limit=0)
    await timeline(client, "companies", company["id"], 422, limit=101)
    await timeline(client, "companies", company["id"], 422, offset=-1)
    for role, division in (("hr_team", "it"), ("telecaller", "it"), ("employer", "it")):
        await as_role(client, db_session, role, division)
        await timeline(client, "companies", company["id"], 403)
    client.cookies.clear()
    await timeline(client, "companies", company["id"], 401)


# --- TL2: the candidate timeline ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_candidate_timeline_lists_calls_messages_applications_interviews_offers_and_shares(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    company = await db_session.get(Company, job.company_id)
    candidate = await _candidate(db_session, recruiter, mobile=f"+9198{uuid.uuid4().int % 10**8:08d}")
    application = (await _add(client, job, candidate)).json()["application"]
    assert (await client.post(CALLS, json={"candidate_id": str(candidate.id), "outcome": "connected", "notes": "Keen"})).status_code == 201
    sent = await client.post(MESSAGES, json={"candidate_id": str(candidate.id), "channel": "whatsapp", "body": "Interview on Monday"})
    assert sent.status_code == 201, sent.text
    interview = await _interview(client, application["id"])
    assert (await _move(client, application["id"], "selected")).status_code == 200
    offer = await _offer(client, application["id"])
    assert (await _status(client, offer["id"], "accepted")).status_code == 200
    stored = await db_session.get(JobApplication, uuid.UUID(application["id"]))
    share = ProfileShare(job_id=job.id, company_id=company.id, channel="portal", shared_by_user_id=recruiter.id)
    db_session.add(share)
    await db_session.flush()
    db_session.add(
        ProfileShareItem(share_id=share.id, candidate_id=candidate.id, application_id=stored.id, response="interview_requested", responded_by_user_id=recruiter.id, responded_at=datetime.now(UTC))
    )
    await db_session.commit()

    page = await timeline(client, "candidates", candidate.id)
    kinds = {r["kind"] for r in page["items"]}
    assert kinds == {"call", "message", "application", "interview", "offer", "share", "share_response"}
    by = {summary(r): r for r in page["items"]}
    assert by[("call", "outgoing")]["reason"] == "Keen" and by[("call", "outgoing")]["actor"]["id"] == str(recruiter.id)
    assert by[("message", "whatsapp")]["reason"] == "Interview on Monday"
    scheduled = by[("interview", "scheduled")]
    assert scheduled["subject"] == interview["code"] or interview.get("interview_code") == scheduled["subject"]
    assert scheduled["scheduled_for"] is not None and scheduled["context"] == company.name
    accepted = next(r for r in page["items"] if r["kind"] == "offer" and r["to_value"] == "accepted")
    assert accepted["to_label"] == "Accepted" and accepted["context"] == company.name
    first = [r for r in page["items"] if r["kind"] == "application"][-1]
    assert first["from_value"] == "" and first["to_label"] and job.requirement_code in first["subject"]
    assert by[("share", "portal")]["context"] == company.name
    assert by[("share_response", "interview_requested")]["context"] == company.name
    assert candidate.email not in str(page)


@pytest.mark.asyncio
async def test_candidate_timeline_readers(client, db_session):
    _, recruiter = await _team(client, db_session)
    candidate = await _candidate(db_session, recruiter)
    assert (await client.post(CALLS, json={"candidate_id": str(candidate.id), "outcome": "busy"})).status_code == 201
    await login(client, await make_recruiter(db_session))  # R11: every recruiter reads the whole pool
    assert [r["kind"] for r in (await timeline(client, "candidates", candidate.id))["items"]] == ["call"]
    await as_role(client, db_session, "hr_team", "it")
    assert (await timeline(client, "candidates", candidate.id))["total"] == 1
    for role, division in (("bdm", "it"), ("telecaller", "it"), ("employer", "it")):
        await as_role(client, db_session, role, division)
        await timeline(client, "candidates", candidate.id, 403)
    await as_role(client, db_session, "super_admin", "global")
    await timeline(client, "candidates", uuid.uuid4(), 404)
    await timeline(client, "candidates", candidate.id, 422, limit=101)
    hidden = await _candidate(db_session, recruiter, user_id=(await make_user(db_session, "student", "it")).id, opted_in=False)
    await timeline(client, "candidates", hidden.id, 404)  # a student who has not opted in is outside the pool
