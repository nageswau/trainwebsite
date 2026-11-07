"""pob-007 -- BD activity completeness (DEC-SCOPE-422 A1-A12): LinkedIn outreach logging and its timeline rows, message outcomes with a
next follow-up, call details, meeting details with action items that become follow-ups, follow-up priority and reminder, and BD visits as
`company_visit` meetings. The shared test database is never truncated, so every value is unique per test."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, RecruiterFollowUp, RecruiterMeeting, RecruiterMessageTemplate, UserPermissionOverride
from tests.rec001_helpers import login, make_pm, make_recruiter
from tests.test_rec_009_candidates import mail, mobile
from tests.test_rec_017_tracking import _candidate, _requirement

COMPANIES = "/api/v1/recruiter/companies"
MESSAGES = "/api/v1/recruiter/messages"
LINKEDIN = f"{MESSAGES}/linkedin"
CALLS = "/api/v1/recruiter/calls"
MEETINGS = "/api/v1/recruiter/meetings"
FOLLOW_UPS = "/api/v1/recruiter/follow-ups"


def unique(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


def later(**delta) -> str:
    return (datetime.now(UTC) + timedelta(**delta)).isoformat()


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _company(client) -> dict:
    response = await client.post(COMPANIES, json={"name": unique("BD Co")})
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _contact(client, company_id, **over) -> dict:
    name = over.pop("name", unique("Priya"))
    response = await client.post(f"{COMPANIES}/{company_id}/contacts", json={"name": name, "mobile": mobile(), "email": mail()} | over)
    assert response.status_code == 201, response.text
    return next(c for c in response.json()["items"] if c["name"] == name)


async def _setup(client, db):
    manager, recruiter = await _team(client, db)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    return manager, recruiter, company, contact


async def _linkedin_template(db, manager) -> RecruiterMessageTemplate:
    template = RecruiterMessageTemplate(channel="linkedin", kind=None, name=unique("LI intro"), body="Hi {name}", category="linkedin", status="approved",
                                        created_by_user_id=manager.id)
    db.add(template)
    await db.commit()
    return template


async def _timeline(client, company_id, **params) -> list[dict]:
    response = await client.get(f"{COMPANIES}/{company_id}/timeline", params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


# --- A1/A2: LinkedIn outreach (AC1, AC3) ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_linkedin_connection_request_is_logged_and_appears_in_the_timelines(client, db_session):
    manager, recruiter, company, contact = await _setup(client, db_session)
    template = await _linkedin_template(db_session, manager)
    sent = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    response = await client.post(LINKEDIN, json={"contact_id": contact["id"], "action": "connection_request", "sent_at": sent, "template_id": str(template.id),
                                                 "body": "Hi Priya, glad to connect"})
    assert response.status_code == 201, response.text
    message = response.json()
    assert message["channel"] == "linkedin" and message["linkedin_action"] == "connection_request" and message["delivery_status"] is None
    assert message["template"]["name"] == template.name and message["body"] == "Hi Priya, glad to connect" and message["follow_up"] is None
    await db_session.refresh(template)
    assert template.last_used_at is not None
    listed = (await client.get(f"{COMPANIES}/{company['id']}/messages")).json()["items"]
    assert listed[0]["id"] == message["id"]
    for params in ({}, {"contact_id": contact["id"]}):
        rows = [r for r in await _timeline(client, company["id"], **params) if r["kind"] == "message"]
        assert rows[0]["event"] == "linkedin" and rows[0]["status"] == "connection_request" and rows[0]["to_label"] == contact["name"]
    contacts = (await client.get(f"{COMPANIES}/{company['id']}/contacts")).json()["items"]
    assert next(c for c in contacts if c["id"] == contact["id"])["status"] == "contacted"
    assert (await client.get(f"{COMPANIES}/{company['id']}")).json()["company"]["last_contacted_at"] is not None
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == message["id"], AuditLog.action == "recruiter_message.create"))
    assert audit.metadata_json["channel"] == "linkedin" and "body" not in audit.metadata_json


@pytest.mark.asyncio
async def test_a_linkedin_message_with_a_next_follow_up_creates_it_in_the_same_request(client, db_session):
    _, _, company, contact = await _setup(client, db_session)
    response = await client.post(LINKEDIN, json={"contact_id": contact["id"], "action": "message", "body": "Following up on our chat",
                                                 "next_follow_up": {"due_at": later(days=2), "reason": "new_requirement", "notes": "Check reply"}})
    assert response.status_code == 201, response.text
    follow_up = response.json()["follow_up"]
    stored = await db_session.get(RecruiterFollowUp, uuid.UUID(follow_up["id"]))
    assert stored.contact_id == uuid.UUID(contact["id"]) and stored.reason == "new_requirement" and stored.notes == "Check reply"


@pytest.mark.asyncio
async def test_a_candidate_linkedin_message_reads_in_the_candidate_timeline(client, db_session):
    _, recruiter = await _team(client, db_session)
    candidate = await _candidate(db_session, recruiter)
    response = await client.post(LINKEDIN, json={"candidate_id": str(candidate.id), "action": "message", "body": "A role for you"})
    assert response.status_code == 201, response.text
    rows = (await client.get(f"/api/v1/recruiter/candidates/{candidate.id}/timeline")).json()["items"]
    assert any(r["kind"] == "message" and r["event"] == "linkedin" and r["status"] == "message" for r in rows)
    refused = await client.post(LINKEDIN, json={"candidate_id": str(candidate.id), "action": "message", "body": "x",
                                                "next_follow_up": {"due_at": later(days=1), "reason": "jd"}})
    assert refused.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "status", "text"),
    [
        ({"action": "message"}, 422, "Write the message you sent"),
        ({"action": "connection_request", "sent_at": later(hours=2)}, 422, "can't be in the future"),
        ({"action": "poke"}, 422, ""),
        ({"action": "message", "body": "x" * 2001}, 422, ""),
    ],
)
async def test_linkedin_refusals(client, db_session, body, status, text):
    _, _, _, contact = await _setup(client, db_session)
    response = await client.post(LINKEDIN, json={"contact_id": contact["id"], **body})
    assert response.status_code == status, response.text
    assert text in response.text


@pytest.mark.asyncio
async def test_linkedin_needs_a_usable_linkedin_template_scope_and_contactable_person(client, db_session):
    manager, recruiter, company, contact = await _setup(client, db_session)
    whatsapp = RecruiterMessageTemplate(channel="whatsapp", kind="follow_up", name=unique("WA"), body="Hi", category="whatsapp", status="approved", created_by_user_id=manager.id)
    draft = RecruiterMessageTemplate(channel="linkedin", name=unique("LI draft"), body="Hi", category="linkedin", status="draft", created_by_user_id=manager.id)
    db_session.add_all([whatsapp, draft])
    await db_session.commit()
    for template in (whatsapp, draft):
        response = await client.post(LINKEDIN, json={"contact_id": contact["id"], "action": "connection_request", "template_id": str(template.id)})
        assert response.status_code == 422 and "Choose an active LinkedIn template" in response.text
    dnc = await _contact(client, company["id"])
    assert (await client.patch(f"/api/v1/recruiter/contacts/{dnc['id']}", json={"status": "do_not_contact"})).status_code == 200
    assert (await client.post(LINKEDIN, json={"contact_id": dnc["id"], "action": "connection_request"})).status_code == 409
    other = await make_recruiter(db_session, manager)
    await login(client, other)
    assert (await client.post(LINKEDIN, json={"contact_id": contact["id"], "action": "connection_request"})).status_code == 404


# --- A3: message outcome and next follow-up ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_message_outcome_is_recorded_once_with_its_follow_up(client, db_session):
    manager, recruiter, company, contact = await _setup(client, db_session)
    message = (await client.post(MESSAGES, json={"channel": "whatsapp", "contact_id": contact["id"], "body": "Hello"})).json()
    response = await client.post(f"{MESSAGES}/{message['id']}/outcome", json={"outcome": "Asked for our fee deck",
                                                                            "next_follow_up": {"due_at": later(days=3), "reason": "payment_commercial"}})
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["outcome"] == "Asked for our fee deck" and out["follow_up"]["id"]
    stored = await db_session.get(RecruiterFollowUp, uuid.UUID(out["follow_up"]["id"]))
    assert stored.company_id == uuid.UUID(company["id"]) and stored.contact_id == uuid.UUID(contact["id"])
    again = await client.post(f"{MESSAGES}/{message['id']}/outcome", json={"outcome": "Again"})
    assert again.status_code == 409
    other = await make_recruiter(db_session, manager)
    await login(client, other)
    assert (await client.post(f"{MESSAGES}/{message['id']}/outcome", json={"outcome": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_a_candidate_message_outcome_is_refused_and_a_bad_follow_up_rolls_back(client, db_session):
    _, recruiter, company, contact = await _setup(client, db_session)
    candidate = await _candidate(db_session, recruiter)
    note = (await client.post(LINKEDIN, json={"candidate_id": str(candidate.id), "action": "message", "body": "Hi"})).json()
    assert (await client.post(f"{MESSAGES}/{note['id']}/outcome", json={"outcome": "x"})).status_code == 422
    message = (await client.post(LINKEDIN, json={"contact_id": contact["id"], "action": "connection_request"})).json()
    past = await client.post(f"{MESSAGES}/{message['id']}/outcome", json={"outcome": "Accepted", "next_follow_up": {"due_at": later(days=-1), "reason": "jd"}})
    assert past.status_code == 422
    listed = (await client.get(f"{COMPANIES}/{company['id']}/messages")).json()["items"]
    assert next(m for m in listed if m["id"] == message["id"])["outcome"] is None


# --- A4: call fields --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_call_records_the_requirement_objections_and_next_action(client, db_session):
    _, recruiter, company, contact = await _setup(client, db_session)
    from app.models import Company

    job = await _requirement(db_session, recruiter, company=await db_session.get(Company, uuid.UUID(company["id"])))
    response = await client.post(CALLS, json={"contact_id": contact["id"], "outcome": "connected", "job_id": str(job.id),
                                              "objections": ["fee_too_high", "existing_vendors"], "objection_notes": "Pays 6% elsewhere",
                                              "next_action": "Send the revised fee proposal"})
    assert response.status_code == 201, response.text
    call = response.json()["call"]
    assert call["requirement"] == {"id": str(job.id), "code": job.requirement_code, "title": job.title}
    assert call["objections"] == ["fee_too_high", "existing_vendors"] and call["objection_notes"] == "Pays 6% elsewhere"
    assert call["next_action"] == "Send the revised fee proposal"
    edited = await client.patch(f"{CALLS}/{call['id']}", json={"objections": ["timing"], "job_id": None, "next_action": None})
    assert edited.status_code == 200, edited.text
    assert edited.json()["objections"] == ["timing"] and edited.json()["requirement"] is None and edited.json()["next_action"] is None


@pytest.mark.asyncio
async def test_call_field_refusals(client, db_session):
    _, recruiter, company, contact = await _setup(client, db_session)
    elsewhere = await _requirement(db_session, recruiter)
    bad_job = await client.post(CALLS, json={"contact_id": contact["id"], "outcome": "connected", "job_id": str(elsewhere.id)})
    assert bad_job.status_code == 422 and "requirement of this company" in bad_job.text
    for objections in (["nope"], ["timing", "timing"]):
        assert (await client.post(CALLS, json={"contact_id": contact["id"], "outcome": "connected", "objections": objections})).status_code == 422
    candidate = await _candidate(db_session, recruiter)
    on_candidate = await client.post(CALLS, json={"candidate_id": str(candidate.id), "outcome": "connected", "job_id": str(elsewhere.id)})
    assert on_candidate.status_code == 422


# --- A5/A6/A7: meeting fields and action items (AC2) ----------------------------------------------------------------------------------
async def _meeting(client, db, company_id, contact_id=None, meeting_type="requirement_discussion") -> dict:
    body = {"meeting_type": meeting_type, "starts_at": later(days=1), "mode": "In person", **({"contact_id": contact_id} if contact_id else {})}
    response = await client.post(f"{COMPANIES}/{company_id}/meetings", json=body)
    assert response.status_code == 201, response.text
    meeting = response.json()
    await db.execute(update(RecruiterMeeting).where(RecruiterMeeting.id == uuid.UUID(meeting["id"])).values(starts_at=datetime.now(UTC) - timedelta(hours=1)))
    await db.commit()
    return meeting


@pytest.mark.asyncio
async def test_a_meeting_outcome_records_forecast_notes_and_each_action_item_becomes_a_follow_up(client, db_session):
    _, _, company, contact = await _setup(client, db_session)
    meeting = await _meeting(client, db_session, company["id"], contact["id"])
    response = await client.post(f"{MEETINGS}/{meeting['id']}/outcome", json={
        "outcome": "They plan to hire this quarter",
        "hiring_forecast": [{"role": "Java Developer", "count": 5, "timeframe": "next_3_months"}, {"role": "QA", "count": 2, "timeframe": "this_month"}],
        "commercial_notes": "Open to 7.5% on CTC",
        "action_items": [{"action": "Send the proposal", "due_at": later(days=2), "reason": "payment_commercial"},
                         {"action": "Ask for the JDs", "due_at": later(days=4), "reason": "jd"}],
    })
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["hiring_forecast"][0] == {"role": "Java Developer", "count": 5, "timeframe": "next_3_months"}
    assert out["commercial_notes"] == "Open to 7.5% on CTC" and out["commercial_notes_visible"] is True
    assert [a["action"] for a in out["action_items"]] == ["Send the proposal", "Ask for the JDs"]
    rows = (await db_session.scalars(select(RecruiterFollowUp).where(RecruiterFollowUp.id.in_([uuid.UUID(a["follow_up_id"]) for a in out["action_items"]])))).all()
    assert {(r.notes, r.reason, r.contact_id) for r in rows} == {("Send the proposal", "payment_commercial", uuid.UUID(contact["id"])),
                                                                ("Ask for the JDs", "jd", uuid.UUID(contact["id"]))}
    rows = [r for r in await _timeline(client, company["id"]) if r["kind"] == "meeting"]
    assert all("7.5%" not in (r["reason"] or "") for r in rows)


@pytest.mark.asyncio
async def test_one_bad_action_item_refuses_the_whole_outcome(client, db_session):
    _, _, company, _ = await _setup(client, db_session)
    meeting = await _meeting(client, db_session, company["id"])
    response = await client.post(f"{MEETINGS}/{meeting['id']}/outcome", json={
        "outcome": "Done", "action_items": [{"action": "Fine", "due_at": later(days=2), "reason": "jd"}, {"action": "Past", "due_at": later(days=-1), "reason": "jd"}]})
    assert response.status_code == 422
    again = (await client.get(f"{MEETINGS}/{meeting['id']}")).json()
    assert again["status"] == "scheduled" and again["action_items"] == []
    count = await db_session.scalar(select(RecruiterFollowUp.id).where(RecruiterFollowUp.company_id == uuid.UUID(company["id"]), RecruiterFollowUp.notes == "Fine"))
    assert count is None
    too_many = [{"action": f"A{i}", "due_at": later(days=2), "reason": "jd"} for i in range(11)]
    assert (await client.post(f"{MEETINGS}/{meeting['id']}/outcome", json={"outcome": "x", "action_items": too_many})).status_code == 422


@pytest.mark.asyncio
async def test_commercial_notes_need_the_client_commercials_grant(client, db_session):
    _, recruiter, company, _ = await _setup(client, db_session)
    first = await _meeting(client, db_session, company["id"])
    assert (await client.post(f"{MEETINGS}/{first['id']}/outcome", json={"outcome": "ok", "commercial_notes": "8%"})).status_code == 200
    db_session.add(UserPermissionOverride(user_id=recruiter.id, resource="commercials.client", action="view", effect="deny", reason="pob-007 test"))
    await db_session.commit()
    hidden = (await client.get(f"{MEETINGS}/{first['id']}")).json()
    assert hidden["commercial_notes"] is None and hidden["commercial_notes_visible"] is False
    second = await _meeting(client, db_session, company["id"])
    refused = await client.post(f"{MEETINGS}/{second['id']}/outcome", json={"outcome": "ok", "commercial_notes": "9%"})
    assert refused.status_code == 403
    assert (await client.post(f"{MEETINGS}/{second['id']}/outcome", json={"outcome": "ok"})).status_code == 200


@pytest.mark.asyncio
async def test_a_bd_visit_is_a_company_visit_meeting(client, db_session):
    _, _, company, _ = await _setup(client, db_session)
    meeting = await _meeting(client, db_session, company["id"], meeting_type="company_visit")
    assert meeting["meeting_type"] == "company_visit"
    rows = [r for r in await _timeline(client, company["id"]) if r["kind"] == "meeting"]
    assert rows[0]["from_value"] == "company_visit"


# --- A8: follow-up priority and reminder ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_follow_up_keeps_its_priority_and_reminder(client, db_session):
    _, _, company, _ = await _setup(client, db_session)
    plain = await client.post(f"{COMPANIES}/{company['id']}/follow-ups", json={"due_at": later(days=2), "reason": "jd"})
    assert plain.status_code == 201 and plain.json()["priority"] == "medium" and plain.json()["remind_at"] is None
    remind = later(days=1)
    response = await client.post(f"{COMPANIES}/{company['id']}/follow-ups", json={"due_at": later(days=2), "reason": "jd", "priority": "high", "remind_at": remind})
    assert response.status_code == 201, response.text
    fu = response.json()
    assert fu["priority"] == "high" and datetime.fromisoformat(fu["remind_at"]) == datetime.fromisoformat(remind)
    moved = await client.patch(f"{FOLLOW_UPS}/{fu['id']}", json={"priority": "low", "remind_at": None})
    assert moved.status_code == 200 and moved.json()["priority"] == "low" and moved.json()["remind_at"] is None


@pytest.mark.asyncio
async def test_follow_up_reminder_refusals(client, db_session):
    _, _, company, _ = await _setup(client, db_session)
    url = f"{COMPANIES}/{company['id']}/follow-ups"
    after_due = await client.post(url, json={"due_at": later(days=1), "reason": "jd", "remind_at": later(days=2)})
    assert after_due.status_code == 422 and "remind_at" in after_due.text
    past = await client.post(url, json={"due_at": later(days=1), "reason": "jd", "remind_at": later(hours=-1)})
    assert past.status_code == 422 and "remind_at" in past.text
    assert (await client.post(url, json={"due_at": later(days=1), "reason": "jd", "priority": "urgent"})).status_code == 422
    fu = (await client.post(url, json={"due_at": later(days=3), "reason": "jd", "remind_at": later(days=2)})).json()
    early = await client.patch(f"{FOLLOW_UPS}/{fu['id']}", json={"due_at": later(days=1)})
    assert early.status_code == 422 and "remind_at" in early.text
    both = await client.patch(f"{FOLLOW_UPS}/{fu['id']}", json={"due_at": later(days=1), "remind_at": later(hours=12)})
    assert both.status_code == 200, both.text
