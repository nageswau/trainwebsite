"""pob-005 -- contact status, decision-maker, source/verification, Do Not Contact, replies, duplicates and the per-contact timeline
(DEC-SCOPE-411 D1-D11). The shared test database is never truncated, so every value is unique per test."""

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import AuditLog, CompanyContact, RecruiterFollowUp
from app.services import profile_sharing
from tests.rec001_helpers import login, make_pm, make_recruiter
from tests.test_rec_009_candidates import mail, mobile

COMPANIES = "/api/v1/recruiter/companies"
CONTACTS = "/api/v1/recruiter/contacts"
MESSAGES = "/api/v1/recruiter/messages"
CALLS = "/api/v1/recruiter/calls"
DNC = "This contact has asked not to be contacted"


def unique(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _company(client) -> dict:
    response = await client.post(COMPANIES, json={"name": unique("Status Co")})
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _contact(client, company_id, **over) -> dict:
    name = over.pop("name", unique("Priya"))
    response = await client.post(f"{COMPANIES}/{company_id}/contacts", json={"name": name, "mobile": mobile(), "email": mail()} | over)
    assert response.status_code == 201, response.text
    return next(c for c in response.json()["items"] if c["name"] == name)


async def _status(client, company_id, contact_id) -> str:
    items = (await client.get(f"{COMPANIES}/{company_id}/contacts")).json()["items"]
    return next(c for c in items if c["id"] == contact_id)["status"]


async def _whatsapp(client, contact_id):
    return await client.post(MESSAGES, json={"channel": "whatsapp", "contact_id": contact_id, "body": "Hello"})


async def _call(client, contact_id, outcome="no_answer", direction="outgoing"):
    return await client.post(CALLS, json={"contact_id": contact_id, "outcome": outcome, "direction": direction})


async def _meeting(client, company_id, **people):
    starts = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    return await client.post(f"{COMPANIES}/{company_id}/meetings", json={"meeting_type": "contract_discussion", "starts_at": starts, "mode": "Online", **people})


async def _set(client, contact_id, **body):
    response = await client.patch(f"{CONTACTS}/{contact_id}", json=body)
    assert response.status_code == 200, response.text
    return response


# --- D1-D3: the new fields (AC4) -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_new_fields_save_and_read_back(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    verified = (date.today() - timedelta(days=3)).isoformat()
    contact = await _contact(client, company["id"], is_decision_maker=True, source="linkedin", verified_on=verified, preferred_channel="linkedin")
    assert contact["is_decision_maker"] is True and contact["source"] == "linkedin" and contact["verified_on"] == verified
    assert contact["preferred_channel"] == "linkedin" and contact["status"] == "not_contacted" and contact["follow_up_due"] is False
    await _set(client, contact["id"], is_decision_maker=False, source=None, status="not_interested")
    assert await _status(client, company["id"], contact["id"]) == "not_interested"
    plain = await _contact(client, company["id"])
    assert plain["is_decision_maker"] is False and plain["source"] is None and plain["verified_on"] is None
    blocked = await _contact(client, company["id"], status="do_not_contact")  # added straight as Do not contact (D5)
    assert blocked["status"] == "do_not_contact" and blocked["status_changed_at"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [{"source": "fax"}, {"status": "follow_up_due"}, {"status": "bogus"}, {"verified_on": (date.today() + timedelta(days=3)).isoformat()}, {"is_decision_maker": "yes"}],
)
async def test_invalid_values_are_422(client, db_session, body):
    await _team(client, db_session)
    company = await _company(client)
    response = await client.post(f"{COMPANIES}/{company['id']}/contacts", json={"name": unique("Bad")} | body)
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_follow_up_due_is_derived_from_an_open_follow_up(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    db_session.add(RecruiterFollowUp(company_id=uuid.UUID(company["id"]), contact_id=uuid.UUID(contact["id"]), reason="jd",
                                     due_at=datetime.now(UTC) - timedelta(hours=1), created_by_user_id=recruiter.id))  # fmt: skip
    await db_session.commit()
    items = (await client.get(f"{COMPANIES}/{company['id']}/contacts")).json()["items"]
    assert next(c for c in items if c["id"] == contact["id"])["follow_up_due"] is True


@pytest.mark.asyncio
async def test_a_manual_status_change_is_audited(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    await _set(client, contact["id"], status="do_not_contact")
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "recruiter_company.contact_status", AuditLog.entity_id == company["id"]))).all()
    assert [(r.metadata_json["from"], r.metadata_json["to"], r.metadata_json["cause"]) for r in rows] == [("not_contacted", "do_not_contact", "manual")]
    assert rows[0].metadata_json["contact_id"] == contact["id"]


# --- D4/D7: automatic moves and replies (AC1) --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_message_contacts_and_a_logged_reply_moves_to_replied(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    sent = await _whatsapp(client, contact["id"])
    assert sent.status_code == 201, sent.text
    assert await _status(client, company["id"], contact["id"]) == "contacted"
    message_id = sent.json()["id"]
    replied = await client.post(f"{MESSAGES}/{message_id}/reply", json={})
    assert replied.status_code == 200, replied.text
    assert replied.json()["replied_at"] is not None
    assert await _status(client, company["id"], contact["id"]) == "replied"
    again = await client.post(f"{MESSAGES}/{message_id}/reply", json={})
    assert again.status_code == 200 and again.json()["replied_at"] == replied.json()["replied_at"]
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "recruiter_message.reply", AuditLog.entity_id == message_id))).all()
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_reply_time_rules_and_scope(client, db_session):
    manager, _ = await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    message_id = (await _whatsapp(client, contact["id"])).json()["id"]
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    early = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    for when in (future, early):
        assert (await client.post(f"{MESSAGES}/{message_id}/reply", json={"replied_at": when})).status_code == 422
    assert (await client.post(f"{MESSAGES}/{uuid.uuid4()}/reply", json={})).status_code == 404
    await login(client, await make_recruiter(db_session, manager))  # another recruiter: the message is out of scope
    assert (await client.post(f"{MESSAGES}/{message_id}/reply", json={})).status_code == 404


@pytest.mark.asyncio
async def test_calls_and_meetings_move_forward_only(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    a, b, c = [await _contact(client, company["id"]) for _ in range(3)]
    assert (await _call(client, a["id"], "no_answer")).status_code == 201
    assert await _status(client, company["id"], a["id"]) == "contacted"
    assert (await _call(client, b["id"], "connected")).status_code == 201
    assert await _status(client, company["id"], b["id"]) == "replied"
    assert (await _call(client, c["id"], "busy", "incoming")).status_code == 201
    assert await _status(client, company["id"], c["id"]) == "replied"
    assert (await _meeting(client, company["id"], contact_id=a["id"], participant_contact_ids=[b["id"]])).status_code == 201
    assert await _status(client, company["id"], a["id"]) == "meeting_scheduled"
    assert await _status(client, company["id"], b["id"]) == "meeting_scheduled"
    assert (await _whatsapp(client, a["id"])).status_code == 201  # never backwards
    assert await _status(client, company["id"], a["id"]) == "meeting_scheduled"


@pytest.mark.asyncio
async def test_not_interested_is_never_moved_automatically(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    await _set(client, contact["id"], status="not_interested")
    assert (await _call(client, contact["id"], "connected")).status_code == 201
    assert await _status(client, company["id"], contact["id"]) == "not_interested"


# --- D6: Do Not Contact (AC2) ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_do_not_contact_refuses_outreach_with_409(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    message_id = (await _whatsapp(client, contact["id"])).json()["id"]
    await _set(client, contact["id"], status="do_not_contact")
    for response in (
        await _whatsapp(client, contact["id"]),
        await _call(client, contact["id"], "connected"),
        await _meeting(client, company["id"], contact_id=contact["id"]),
        await _meeting(client, company["id"], participant_contact_ids=[contact["id"]]),
    ):
        assert response.status_code == 409, response.text
        assert response.json()["detail"] == DNC
    with pytest.raises(HTTPException) as refused:
        await profile_sharing._contact(db_session, SimpleNamespace(company_id=uuid.UUID(company["id"])), SimpleNamespace(contact_id=uuid.UUID(contact["id"]), channel="email"))
    assert refused.value.status_code == 409 and refused.value.detail == DNC
    assert (await _call(client, contact["id"], "connected", "incoming")).status_code == 201  # they called us
    assert (await client.post(f"{MESSAGES}/{message_id}/reply", json={})).status_code == 200  # a reply is still recorded
    assert await _status(client, company["id"], contact["id"]) == "do_not_contact"


# --- D8: duplicates warn (AC3) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicates_across_companies_warn_without_naming_out_of_scope_ones(client, db_session):
    manager, recruiter = await _team(client, db_session)
    first, second = await _company(client), await _company(client)
    number, address = mobile(), mail()
    mine = await _contact(client, first["id"], mobile=number)
    await login(client, await make_recruiter(db_session, manager))  # another recruiter's company holds the same email
    theirs = await _company(client)
    await _contact(client, theirs["id"], email=address)
    await login(client, recruiter)
    check = await client.get(f"{COMPANIES}/{second['id']}/contacts/duplicates", params={"mobile": number.replace(" ", ""), "email": address.upper()})
    assert check.status_code == 200, check.text
    out = check.json()
    assert out["others"] == 1
    assert out["matches"] == [
        {"id": mine["id"], "name": mine["name"], "active": True, "company": {"id": first["id"], "name": first["name"]}, "same_company": False, "on": ["mobile"]}
    ]
    same = (await client.get(f"{COMPANIES}/{first['id']}/contacts/duplicates", params={"mobile": number})).json()
    assert same["matches"][0]["same_company"] is True
    excluded = (await client.get(f"{COMPANIES}/{first['id']}/contacts/duplicates", params={"mobile": number, "exclude": mine["id"]})).json()
    assert excluded == {"matches": [], "others": 0}
    assert (await client.get(f"{COMPANIES}/{first['id']}/contacts/duplicates")).json() == {"matches": [], "others": 0}
    assert (await client.get(f"{COMPANIES}/{theirs['id']}/contacts/duplicates", params={"mobile": number})).status_code == 404


# --- D10/D11: the per-contact timeline and follow-ups (AC5) -----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_per_contact_timeline_and_follow_ups(client, db_session):
    _, recruiter = await _team(client, db_session)
    company, other = await _company(client), await _company(client)
    a, b = await _contact(client, company["id"]), await _contact(client, company["id"])
    stranger = await _contact(client, other["id"])
    sent = (await _whatsapp(client, a["id"])).json()
    await client.post(f"{MESSAGES}/{sent['id']}/reply", json={})
    await _call(client, b["id"], "busy")
    db_session.add_all([
        RecruiterFollowUp(company_id=uuid.UUID(company["id"]), contact_id=uuid.UUID(c["id"]), reason="jd", due_at=datetime.now(UTC) + timedelta(days=1), created_by_user_id=recruiter.id)
        for c in (a, b)
    ])  # fmt: skip
    await db_session.commit()
    rows = (await client.get(f"{COMPANIES}/{company['id']}/timeline", params={"contact_id": a["id"]})).json()["items"]
    kinds = sorted(r["kind"] for r in rows)
    assert kinds == ["contact_status", "contact_status", "follow_up", "message", "message_reply"], kinds
    moves = [(r["from_value"], r["to_value"]) for r in rows if r["kind"] == "contact_status"]
    assert set(moves) == {("not_contacted", "contacted"), ("contacted", "replied")}
    assert all(r["to_label"] for r in rows if r["kind"] == "contact_status")
    whole = (await client.get(f"{COMPANIES}/{company['id']}/timeline")).json()["items"]
    assert "contact_status" not in {r["kind"] for r in whole} and "message_reply" in {r["kind"] for r in whole}
    assert (await client.get(f"{COMPANIES}/{company['id']}/timeline", params={"contact_id": stranger["id"]})).status_code == 404
    follow_ups = (await client.get(f"{COMPANIES}/{company['id']}/follow-ups", params={"contact_id": b["id"]})).json()
    assert follow_ups["total"] == 1 and follow_ups["items"][0]["contact"]["id"] == b["id"]
    assert (await client.get(f"{COMPANIES}/{company['id']}/follow-ups", params={"contact_id": stranger["id"]})).status_code == 404


@pytest.mark.asyncio
async def test_a_deactivated_contact_keeps_its_status(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    await _set(client, contact["id"], status="replied")
    await _set(client, contact["id"], active=False)
    row = await db_session.scalar(select(CompanyContact).where(CompanyContact.id == uuid.UUID(contact["id"])).execution_options(populate_existing=True))
    assert row.status == "replied" and row.status_changed_at is not None
