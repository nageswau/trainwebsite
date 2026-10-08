"""rec-025 -- recruiter calls (spec §1-§3; DEC-SCOPE-132 CA1-CA9): log a call on a company contact or a candidate, the lists, the
contact's Last contacted, the next follow-up, and the same-day edit / delete. The shared test database is never truncated, so every
assertion uses rows created by the test."""

import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, RecCandidateSource, RecruiterCall, RecruiterFollowUp
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user

COMPANIES = "/api/v1/recruiter/companies"
CONTACTS = "/api/v1/recruiter/contacts"
CANDIDATES = "/api/v1/recruiter/candidates"
CALLS = "/api/v1/recruiter/calls"


def ago(**delta) -> str:
    return (datetime.now(UTC) - timedelta(**delta)).isoformat()


def at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def soon() -> str:
    return (datetime.now(UTC) + timedelta(days=1)).isoformat()


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _company_with_contact(client, **body) -> tuple[dict, dict]:
    response = await client.post(COMPANIES, json={"name": f"Call {uuid.uuid4().hex[:8]} Pvt", **body})
    assert response.status_code == 201, response.text
    company = response.json()["company"]
    contacts = (await client.post(f"{COMPANIES}/{company['id']}/contacts", json={"name": "Priya", "mobile": "+91 98765 43210"})).json()["items"]
    return company, contacts[0]


async def _candidate(client, db) -> dict:
    source = str(await db.scalar(select(RecCandidateSource.id).where(RecCandidateSource.name == "Referral")))
    body = {"name": "Rahul Sharma", "mobile": "9" + "".join(random.choices("0123456789", k=9)), "email": f"c{uuid.uuid4().hex[:10]}@example.com", "source_id": source}
    response = await client.post(CANDIDATES, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _log(client, **body):
    return await client.post(CALLS, json={"outcome": "connected"} | body)


async def _stored(db, caller, occurred_at, **party) -> RecruiterCall:
    """Written straight to the database -- the only way to have yesterday's call for the same-day rule."""
    row = RecruiterCall(caller_user_id=caller.id, occurred_at=occurred_at, direction="outgoing", outcome="connected", **party)
    db.add(row)
    await db.commit()
    return row


# --- log a contact call (AC1, AC2) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_connected_call_with_notes_updates_last_contacted(client, db_session):
    _, recruiter = await _team(client, db_session)
    company, contact = await _company_with_contact(client)
    response = await _log(client, contact_id=contact["id"], duration_seconds=185, notes="Discussed the Java JD\nSend profiles Friday")
    assert response.status_code == 201, response.text
    call = response.json()["call"]
    assert response.json()["follow_up_id"] is None
    assert call["kind"] == "contact" and call["company_id"] == company["id"] and call["contact"] == {"id": contact["id"], "name": "Priya"}
    assert call["candidate"] is None and call["outcome_label"] == "Connected" and call["connected"] is True and call["direction"] == "outgoing"
    assert call["duration_seconds"] == 185 and call["caller"]["id"] == str(recruiter.id) and call["can_change"] is True
    listed = (await client.get(f"{COMPANIES}/{company['id']}/contacts")).json()["items"][0]
    assert at(listed["last_contacted_at"]) == at(call["occurred_at"])  # AC1
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == call["id"], AuditLog.action == "recruiter_call.create"))
    assert audit.metadata_json["outcome"] == "connected" and "Java" not in str(audit.metadata_json)  # ids and keys only, never notes


@pytest.mark.asyncio
async def test_last_contacted_is_the_latest_call(client, db_session):
    await _team(client, db_session)
    company, contact = await _company_with_contact(client)
    latest = (await _log(client, contact_id=contact["id"], occurred_at=ago(hours=1))).json()["call"]
    await _log(client, contact_id=contact["id"], occurred_at=ago(days=3), outcome="no_answer")
    listed = (await client.get(f"{COMPANIES}/{company['id']}/contacts")).json()["items"][0]
    assert at(listed["last_contacted_at"]) == at(latest["occurred_at"])


@pytest.mark.asyncio
async def test_next_follow_up_creates_one_for_the_contact(client, db_session):
    await _team(client, db_session)
    company, contact = await _company_with_contact(client)
    due = soon()
    response = await _log(client, contact_id=contact["id"], outcome="call_back_requested",
                          next_follow_up={"due_at": due, "reason": "jd", "notes": "Call back for the JD"})
    assert response.status_code == 201, response.text
    fu_id = response.json()["follow_up_id"]
    fu = await db_session.scalar(select(RecruiterFollowUp).where(RecruiterFollowUp.id == uuid.UUID(fu_id)))
    assert fu.contact_id == uuid.UUID(contact["id"]) and fu.company_id == uuid.UUID(company["id"]) and fu.reason == "jd"  # AC2
    listed = (await client.get(f"{COMPANIES}/{company['id']}/contacts")).json()["items"][0]
    assert listed["next_follow_up_at"] is not None


@pytest.mark.asyncio
async def test_a_refused_follow_up_rolls_the_call_back(client, db_session):
    await _team(client, db_session)
    company, contact = await _company_with_contact(client)
    response = await _log(client, contact_id=contact["id"], next_follow_up={"due_at": ago(hours=1), "reason": "jd"})
    assert response.status_code == 422
    count = await db_session.scalar(select(func.count()).select_from(RecruiterCall).where(RecruiterCall.company_id == uuid.UUID(company["id"])))
    assert count == 0


# --- validation -------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exactly_one_party(client, db_session):
    await _team(client, db_session)
    _, contact = await _company_with_contact(client)
    candidate = await _candidate(client, db_session)
    for body in ({}, {"contact_id": contact["id"], "candidate_id": candidate["id"]}):
        response = await _log(client, **body)
        assert response.status_code == 422, body
        assert "contact_id" in str(response.json()["detail"])


@pytest.mark.asyncio
async def test_bad_values_are_422(client, db_session):
    await _team(client, db_session)
    _, contact = await _company_with_contact(client)
    for over in ({"outcome": "interested"}, {"direction": "missed"}, {"duration_seconds": 14401}, {"occurred_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
                 {"occurred_at": ago(days=9)}, {"notes": "x" * 2001}, {"caller_user_id": str(uuid.uuid4())}):
        assert (await _log(client, contact_id=contact["id"], **over)).status_code == 422, over


@pytest.mark.asyncio
async def test_unknown_party_is_404(client, db_session):
    await _team(client, db_session)
    assert (await _log(client, contact_id=str(uuid.uuid4()))).status_code == 404
    assert (await _log(client, candidate_id=str(uuid.uuid4()))).status_code == 404


# --- state ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_contact_of_an_archived_company_is_409(client, db_session):
    await _team(client, db_session)
    company, contact = await _company_with_contact(client)
    assert (await client.post(f"{COMPANIES}/{company['id']}/archive")).status_code == 200
    assert (await _log(client, contact_id=contact["id"])).status_code == 409
    assert (await client.get(f"{COMPANIES}/{company['id']}/calls")).status_code == 200  # history still reads


@pytest.mark.asyncio
async def test_an_inactive_contact_is_409(client, db_session):
    await _team(client, db_session)
    _, contact = await _company_with_contact(client)
    assert (await client.patch(f"{CONTACTS}/{contact['id']}", json={"active": False})).status_code == 200
    response = await _log(client, contact_id=contact["id"])
    assert response.status_code == 409 and "inactive" in response.json()["detail"]


# --- scope and roles --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_another_recruiters_company_is_404(client, db_session):
    await _team(client, db_session)
    company, contact = await _company_with_contact(client)
    await login(client, await make_recruiter(db_session))
    assert (await _log(client, contact_id=contact["id"])).status_code == 404
    assert (await client.get(f"{COMPANIES}/{company['id']}/calls")).status_code == 404


@pytest.mark.asyncio
async def test_manager_and_bdm_read_contact_calls_but_cannot_log(client, db_session):
    manager, _ = await _team(client, db_session)
    bdm = await make_user(db_session, "bdm", "it")
    company, contact = await _company_with_contact(client, assigned_bdm_user_id=str(bdm.id))
    await _log(client, contact_id=contact["id"])
    for reader in (manager, bdm):
        await login(client, reader)
        page = (await client.get(f"{COMPANIES}/{company['id']}/calls")).json()
        assert page["total"] == 1 and page["items"][0]["can_change"] is False
        assert (await _log(client, contact_id=contact["id"])).status_code == 403


@pytest.mark.asyncio
async def test_candidate_calls_follow_the_pool_rules(client, db_session):
    await _team(client, db_session)
    candidate = await _candidate(client, db_session)
    response = await _log(client, candidate_id=candidate["id"], outcome="no_answer", direction="outgoing")
    assert response.status_code == 201, response.text
    call = response.json()["call"]
    assert call["kind"] == "candidate" and call["company_id"] is None and call["connected"] is False
    assert call["candidate"] == {"id": candidate["id"], "name": "Rahul Sharma", "code": candidate["candidate_code"]}
    await login(client, await make_recruiter(db_session))  # R11: every recruiter works the whole pool
    assert (await _log(client, candidate_id=candidate["id"])).status_code == 201
    await as_role(client, db_session, "hr_team", "it")  # reads, never writes
    page = (await client.get(f"{CANDIDATES}/{candidate['id']}/calls")).json()
    assert page["total"] == 2 and [i["outcome"] for i in page["items"]] == ["connected", "no_answer"]  # newest first
    assert (await _log(client, candidate_id=candidate["id"])).status_code == 403
    await as_role(client, db_session, "bdm", "it")
    assert (await client.get(f"{CANDIDATES}/{candidate['id']}/calls")).status_code == 403


@pytest.mark.asyncio
async def test_a_candidate_call_takes_no_follow_up_and_an_archived_candidate_is_409(client, db_session):
    await _team(client, db_session)
    candidate = await _candidate(client, db_session)
    response = await _log(client, candidate_id=candidate["id"], next_follow_up={"due_at": soon(), "reason": "jd"})
    assert response.status_code == 422 and "next_follow_up" in str(response.json()["detail"])
    assert (await client.post(f"{CANDIDATES}/{candidate['id']}/archive")).status_code == 200
    assert (await _log(client, candidate_id=candidate["id"])).status_code == 409


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.post(CALLS, json={})).status_code == 401


# --- same-day edit and delete (AC3) -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_edit_todays_call(client, db_session):
    await _team(client, db_session)
    _, contact = await _company_with_contact(client)
    call = (await _log(client, contact_id=contact["id"], notes="first")).json()["call"]
    response = await client.patch(f"{CALLS}/{call['id']}", json={"notes": "Discussed fees", "duration_seconds": 60, "direction": "incoming"})
    assert response.status_code == 200, response.text
    assert response.json()["notes"] == "Discussed fees" and response.json()["direction"] == "incoming"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == call["id"], AuditLog.action == "recruiter_call.update"))
    assert audit.metadata_json == {"fields": ["direction", "duration_seconds", "notes"]}
    for body in ({"outcome": "busy"}, {"contact_id": contact["id"]}, {"direction": None}, {"occurred_at": ago(days=2)}):
        assert (await client.patch(f"{CALLS}/{call['id']}", json=body)).status_code == 422, body


@pytest.mark.asyncio
async def test_yesterdays_call_is_409(client, db_session):
    _, recruiter = await _team(client, db_session)
    company, contact = await _company_with_contact(client)
    row = await _stored(db_session, recruiter, datetime.now(UTC) - timedelta(days=2), company_id=uuid.UUID(company["id"]), contact_id=uuid.UUID(contact["id"]))
    page = (await client.get(f"{COMPANIES}/{company['id']}/calls")).json()
    assert page["items"][0]["can_change"] is False
    assert (await client.patch(f"{CALLS}/{row.id}", json={"notes": "late"})).status_code == 409
    assert (await client.delete(f"{CALLS}/{row.id}")).status_code == 409


@pytest.mark.asyncio
async def test_only_the_caller_changes_a_call(client, db_session):
    await _team(client, db_session)
    candidate = await _candidate(client, db_session)
    call = (await _log(client, candidate_id=candidate["id"])).json()["call"]
    await login(client, await make_recruiter(db_session))
    assert (await client.get(f"{CANDIDATES}/{candidate['id']}/calls")).json()["items"][0]["can_change"] is False
    assert (await client.patch(f"{CALLS}/{call['id']}", json={"notes": "mine"})).status_code == 403
    assert (await client.delete(f"{CALLS}/{call['id']}")).status_code == 403
    assert (await client.patch(f"{CALLS}/{uuid.uuid4()}", json={"notes": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_archived_candidate_freezes_its_calls(client, db_session):
    await _team(client, db_session)
    candidate = await _candidate(client, db_session)
    call = (await _log(client, candidate_id=candidate["id"])).json()["call"]
    await client.post(f"{CANDIDATES}/{candidate['id']}/archive")
    assert (await client.get(f"{CANDIDATES}/{candidate['id']}/calls")).json()["items"][0]["can_change"] is False
    assert (await client.patch(f"{CALLS}/{call['id']}", json={"notes": "x"})).status_code == 409


@pytest.mark.asyncio
async def test_delete_keeps_the_follow_up(client, db_session):
    await _team(client, db_session)
    company, contact = await _company_with_contact(client)
    logged = (await _log(client, contact_id=contact["id"], next_follow_up={"due_at": soon(), "reason": "new_openings"})).json()
    response = await client.delete(f"{CALLS}/{logged['call']['id']}")
    assert response.status_code == 204
    assert (await client.get(f"{COMPANIES}/{company['id']}/calls")).json()["total"] == 0
    fu = await db_session.scalar(select(RecruiterFollowUp).where(RecruiterFollowUp.id == uuid.UUID(logged["follow_up_id"])))
    assert fu is not None and fu.status == "open"
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.entity_id == logged["call"]["id"], AuditLog.action == "recruiter_call.delete"))
