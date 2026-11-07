"""pob-023 -- template library governance and the composer everywhere (DEC-SCOPE-408 G1-G12; AC1-AC5 and the archived-name edge):
channels and categories, Draft -> Approved -> Archived, personal vs shared, versions, the placeholder allow-list with a context record,
the commercial grant on {package_range}, and LinkedIn/calling copy mode. The shared test database is never truncated, so every value is
unique per test."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company, CompanyContact, RecruiterMessage, RecruiterMessageTemplate, UserPermissionOverride
from app.services import recruiter_messages as svc
from tests.rec001_helpers import login, make_pm, make_recruiter
from tests.test_rec_017_tracking import _add, _candidate, _requirement
from tests.test_rec_020_interviews import _interview

TEMPLATES = "/api/v1/recruiter/templates"
MESSAGES = "/api/v1/recruiter/messages"


def unique(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


def wa_body(**over) -> dict:
    return {"channel": "whatsapp", "kind": "follow_up", "category": "whatsapp", "name": unique("Gov"), "body": "Hi {name}, {recruiter} here."} | over


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    other = await make_recruiter(db, manager)
    return manager, recruiter, other


async def _create(client, body: dict) -> dict:
    response = await client.post(TEMPLATES, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _contact(db, recruiter, **over) -> tuple[Company, CompanyContact]:
    company = Company(name=unique("Gov Co"), assigned_recruiter_user_id=recruiter.id)
    db.add(company)
    await db.flush()
    contact = CompanyContact(company_id=company.id, name=unique("Priya"), mobile="+919812345678", email=f"{uuid.uuid4().hex[:8]}@acme.example", designation="HR Lead", **over)
    db.add(contact)
    await db.commit()
    return company, contact


async def _seen(client, name: str) -> int:
    return (await client.get(TEMPLATES, params={"q": name})).json()["total"]


# --- AC1: Draft -> approve -> visible to the team ----------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_recruiters_shared_template_is_a_draft_until_the_team_lead_approves_it(client, db_session):
    manager, recruiter, other = await _team(client, db_session)
    await login(client, recruiter)
    draft = await _create(client, wa_body(purpose="Chase a JD", language="Hindi", industry="IT"))
    assert (draft["status"], draft["visibility"], draft["active"], draft["version"]) == ("draft", "shared", False, 1)
    assert draft["created_by"]["id"] == str(recruiter.id) and draft["can_approve"] is False and draft["can_edit"] is True
    assert (await client.post(f"{TEMPLATES}/{draft['id']}/approve")).status_code == 403
    await login(client, other)
    assert await _seen(client, draft["name"]) == 0
    assert (await client.get(f"{TEMPLATES}/{draft['id']}/versions")).status_code == 404
    await login(client, manager)
    listed = (await client.get(TEMPLATES, params={"q": draft["name"], "status": "draft"})).json()["items"]
    assert [t["id"] for t in listed] == [draft["id"]] and listed[0]["can_approve"] is True
    approved = await client.post(f"{TEMPLATES}/{draft['id']}/approve")
    assert approved.status_code == 200 and approved.json()["status"] == "approved" and approved.json()["active"] is True
    assert (await client.post(f"{TEMPLATES}/{draft['id']}/approve")).status_code == 409
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.entity_id == draft["id"], AuditLog.action == "recruiter_template.approve"))
    await login(client, other)
    assert await _seen(client, draft["name"]) == 1
    usable = (await client.get(TEMPLATES, params={"q": draft["name"], "usable": True})).json()["items"]
    assert [t["id"] for t in usable] == [draft["id"]] and usable[0]["can_edit"] is False


@pytest.mark.asyncio
async def test_a_managers_shared_template_is_approved_at_once(client, db_session):
    manager, _, _ = await _team(client, db_session)
    await login(client, manager)
    created = await _create(client, wa_body())
    assert created["status"] == "approved" and created["active"] is True


@pytest.mark.asyncio
async def test_personal_templates_are_the_authors_only(client, db_session):
    manager, recruiter, other = await _team(client, db_session)
    company, contact = await _contact(db_session, recruiter)
    await login(client, recruiter)
    mine = await _create(client, wa_body(visibility="personal"))
    assert (mine["status"], mine["visibility"]) == ("draft", "personal")
    assert (await client.get(TEMPLATES, params={"q": mine["name"], "usable": True, "mine": True})).json()["total"] == 1
    rendered = await client.get(f"{MESSAGES}/render", params={"template_id": mine["id"], "contact_id": str(contact.id)})
    assert rendered.status_code == 200 and rendered.json()["body"].startswith(f"Hi {contact.name}")
    sent = await client.post(MESSAGES, json={"channel": "whatsapp", "contact_id": str(contact.id), "template_id": mine["id"], "body": "Hi"})
    assert sent.status_code == 201, sent.text
    for viewer in (other, manager):
        await login(client, viewer)
        assert await _seen(client, mine["name"]) == 0
        assert (await client.patch(f"{TEMPLATES}/{mine['id']}", json={"body": "x"})).status_code == 404
    await login(client, manager)
    assert (await client.post(f"{TEMPLATES}/{mine['id']}/approve")).status_code == 404


# --- AC2: editing creates a version -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_each_content_edit_is_a_version_and_a_status_change_is_not(client, db_session):
    manager, _, _ = await _team(client, db_session)
    await login(client, manager)
    created = await _create(client, wa_body(body="Hi {name}"))
    edited = await client.patch(f"{TEMPLATES}/{created['id']}", json={"body": "Hello {name}", "purpose": "Warm follow-up"})
    assert edited.status_code == 200 and edited.json()["version"] == 2 and edited.json()["updated_by"]["id"] == str(manager.id)
    assert (await client.patch(f"{TEMPLATES}/{created['id']}", json={"body": "Hello {name}"})).json()["version"] == 2  # no change, no version
    assert (await client.post(f"{TEMPLATES}/{created['id']}/archive")).json()["version"] == 2
    versions = (await client.get(f"{TEMPLATES}/{created['id']}/versions")).json()["items"]
    assert [(v["version"], v["body"]) for v in versions] == [(2, "Hello {name}"), (1, "Hi {name}")]
    assert versions[0]["edited_by"]["full_name"] == manager.full_name and versions[0]["purpose"] == "Warm follow-up"


@pytest.mark.asyncio
async def test_archive_restore_and_who_may_edit(client, db_session):
    manager, recruiter, other = await _team(client, db_session)
    await login(client, recruiter)
    draft = await _create(client, wa_body())
    await login(client, manager)
    await client.post(f"{TEMPLATES}/{draft['id']}/approve")
    await login(client, recruiter)
    assert (await client.patch(f"{TEMPLATES}/{draft['id']}", json={"body": "Mine now"})).status_code == 403  # approved: the Team Lead's
    assert (await client.post(f"{TEMPLATES}/{draft['id']}/archive")).status_code == 403
    await login(client, manager)
    assert (await client.post(f"{TEMPLATES}/{draft['id']}/archive")).json()["status"] == "archived"
    assert (await client.patch(f"{TEMPLATES}/{draft['id']}", json={"body": "x"})).status_code == 409
    assert (await client.post(f"{TEMPLATES}/{draft['id']}/archive")).status_code == 409
    restored = await client.post(f"{TEMPLATES}/{draft['id']}/restore")
    assert restored.status_code == 200 and restored.json()["status"] == "draft"
    assert (await client.patch(f"{TEMPLATES}/{draft['id']}", json={"visibility": "personal"})).status_code == 422


# --- G1 / AC5: channels, categories and calling scripts ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_calling_script_keeps_and_renders_its_steps(client, db_session):
    manager, recruiter, _ = await _team(client, db_session)
    _, contact = await _contact(db_session, recruiter)
    await login(client, manager)
    steps = ["Introduce yourself as {recruiter}", "Ask {name} about open roles", "Agree a follow-up date"]
    script = await _create(client, {"channel": "call", "category": "calling", "name": unique("Call"), "body": "Opening for {company}", "steps": steps})
    assert script["kind"] is None and script["steps"] == steps
    await login(client, recruiter)
    rendered = (await client.get(f"{MESSAGES}/render", params={"template_id": script["id"], "contact_id": str(contact.id)})).json()
    assert rendered["steps"][1] == f"Ask {contact.name} about open roles" and rendered["template"]["channel"] == "call"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"channel": "call", "category": "calling", "steps": []}, "at least one step"),
        ({"channel": "call", "category": "calling"}, "at least one step"),
        ({"steps": ["Hi"]}, "Only calling scripts have steps"),
        ({"category": "vendors"}, "Choose a category"),
        ({"channel": "linkedin", "category": "linkedin", "kind": "follow_up"}, "LinkedIn templates have no kind"),
        ({"channel": "linkedin", "category": "linkedin", "body": "Hi {salary}"}, "Unknown placeholder {salary}"),
        ({"channel": "sms", "category": "candidate"}, "Channel"),
    ],
)
async def test_invalid_governed_templates_are_422(client, db_session, body, detail):
    await login(client, await make_pm(db_session))
    payload = wa_body() | body
    if payload["channel"] != "whatsapp" and "kind" not in body:
        payload.pop("kind")
    response = await client.post(TEMPLATES, json=payload)
    assert response.status_code == 422 and detail in str(response.json()["detail"]), response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", [None, "   "])
async def test_a_blank_language_on_an_edit_is_the_default_as_on_create(client, db_session, blank):
    """QA-06: `language` is required in the table, so a cleared value is English rather than a 500."""
    await login(client, await make_pm(db_session))
    created = await _create(client, wa_body(language="Hindi"))
    response = await client.patch(f"{TEMPLATES}/{created['id']}", json={"language": blank})
    assert response.status_code == 200, response.text
    assert (response.json()["language"], response.json()["version"]) == ("English", 2)


@pytest.mark.asyncio
async def test_a_null_message_on_an_edit_is_a_sentence(client, db_session):
    await login(client, await make_pm(db_session))
    created = await _create(client, wa_body())
    response = await client.patch(f"{TEMPLATES}/{created['id']}", json={"body": None})
    assert response.status_code == 422 and response.json()["detail"] == "Message is required", response.text


@pytest.mark.asyncio
async def test_the_library_filters_by_category_status_language_and_mine(client, db_session):
    manager, recruiter, _ = await _team(client, db_session)
    await login(client, recruiter)
    tag = unique("Filt")
    tpo = await _create(client, {"channel": "email", "kind": "company_introduction", "category": "college_tpo", "name": f"{tag} A", "subject": "Hi", "body": "Hi", "language": "Telugu"})
    await _create(client, wa_body(name=f"{tag} B"))
    ids = lambda r: [t["id"] for t in r.json()["items"]]  # noqa: E731
    assert ids(await client.get(TEMPLATES, params={"q": tag, "category": "college_tpo"})) == [tpo["id"]]
    assert ids(await client.get(TEMPLATES, params={"q": tag, "language": "telugu"})) == [tpo["id"]]
    assert len(ids(await client.get(TEMPLATES, params={"q": tag, "mine": True, "status": "draft"}))) == 2
    assert (await client.get(TEMPLATES, params={"q": "Chase", "channel": "linkedin"})).status_code == 200


# --- G8 / AC3: placeholders from a context record; {package_range} needs the grant ------------------------------------------------
async def _job_template(client, manager) -> dict:
    await login(client, manager)
    return await _create(client, {"channel": "linkedin", "category": "linkedin", "name": unique("LI"), "body": "{name} ({designation}): {job_title} in {job_location}, {package_range}"})


@pytest.mark.asyncio
async def test_a_requirement_context_fills_job_placeholders_and_package_range_needs_the_grant(client, db_session):
    manager, recruiter, _ = await _team(client, db_session)
    company, contact = await _contact(db_session, recruiter)
    job = await _requirement(db_session, recruiter, company=company)
    job.salary_min, job.salary_max = Decimal("600000"), Decimal("900000")
    await db_session.commit()
    template = await _job_template(client, manager)
    await login(client, recruiter)
    params = {"template_id": template["id"], "contact_id": str(contact.id), "job_id": str(job.id)}
    body = (await client.get(f"{MESSAGES}/render", params=params)).json()["body"]
    assert body == f"{contact.name} (HR Lead): {job.title} in Pune, INR 600,000 – 900,000 a year"
    db_session.add(UserPermissionOverride(user_id=recruiter.id, resource="commercials.client", action="view", effect="deny", reason="pob-023 test"))
    await db_session.commit()
    denied = (await client.get(f"{MESSAGES}/render", params=params)).json()
    assert denied["body"] == f"{contact.name} (HR Lead): {job.title} in Pune, " and "package_range" in denied["missing"]


@pytest.mark.asyncio
async def test_a_context_outside_the_partys_company_or_scope_is_404(client, db_session):
    manager, recruiter, other = await _team(client, db_session)
    _, contact = await _contact(db_session, recruiter)
    elsewhere = await _requirement(db_session, recruiter)  # the recruiter's own job, but at another company
    hidden = await _requirement(db_session, other)
    template = await _job_template(client, manager)
    await login(client, recruiter)
    for job in (elsewhere, hidden):
        response = await client.get(f"{MESSAGES}/render", params={"template_id": template["id"], "contact_id": str(contact.id), "job_id": str(job.id)})
        assert response.status_code == 404 and response.json()["detail"] == "Job requirement not found"


@pytest.mark.asyncio
async def test_an_interview_context_fills_the_interview_placeholders_for_its_candidate_only(client, db_session):
    manager, recruiter, _ = await _team(client, db_session)
    await login(client, manager)
    template = await _create(client, {"channel": "email", "kind": "interview_confirmation", "category": "candidate", "name": unique("IC"),
                                      "subject": "{job_title} interview", "body": "{candidate}: {interview_date} {interview_time}, {interview_mode} {interview_link}"})
    await login(client, recruiter)
    job = await _requirement(db_session, recruiter)
    candidate, stranger = await _candidate(db_session, recruiter), await _candidate(db_session, recruiter)
    application = (await _add(client, job, candidate)).json()["application"]
    interview = await _interview(client, application["id"], meeting_url="https://meet.example.com/abc", scheduled_at="2027-01-15T05:00:00Z")
    params = {"template_id": template["id"], "candidate_id": str(candidate.id), "interview_id": interview["id"]}
    rendered = (await client.get(f"{MESSAGES}/render", params=params)).json()
    assert rendered["subject"] == f"{job.title} interview"
    assert rendered["body"] == f"{candidate.name}: 15 Jan 2027 10:30 AM, Online https://meet.example.com/abc" and rendered["missing"] == []
    other = await client.get(f"{MESSAGES}/render", params=params | {"candidate_id": str(stranger.id)})
    assert other.status_code == 404 and other.json()["detail"] == "Interview not found"


# --- G10 / AC4: copy mode is logged ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_linkedin_copy_is_logged_without_its_text_and_is_not_a_message(client, db_session):
    manager, recruiter, other = await _team(client, db_session)
    company, contact = await _contact(db_session, recruiter)
    template = await _job_template(client, manager)
    await login(client, recruiter)
    copied = await client.post(f"{MESSAGES}/copies", json={"template_id": template["id"], "channel": "linkedin", "contact_id": str(contact.id)})
    assert copied.status_code == 201, copied.text
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_template.copy", AuditLog.entity_id == template["id"]))
    assert row.user_id == recruiter.id and row.metadata_json == {"channel": "linkedin", "kind": "contact", "party_id": str(contact.id)}
    assert await db_session.scalar(select(RecruiterMessage.id).where(RecruiterMessage.contact_id == contact.id)) is None
    stored = await db_session.scalar(select(RecruiterMessageTemplate).where(RecruiterMessageTemplate.id == uuid.UUID(template["id"])).execution_options(populate_existing=True))
    assert stored.last_used_at is not None
    await db_session.refresh(company)
    assert company.last_contacted_at is None
    mismatch = await client.post(f"{MESSAGES}/copies", json={"template_id": template["id"], "channel": "call", "contact_id": str(contact.id)})
    assert mismatch.status_code == 422
    await login(client, other)
    assert (await client.post(f"{MESSAGES}/copies", json={"template_id": template["id"], "channel": "linkedin", "contact_id": str(contact.id)})).status_code == 404


@pytest.mark.asyncio
async def test_a_do_not_contact_person_cannot_be_copied_for(client, db_session):
    """pob-005 D6 refuses all outreach to a Do Not Contact person server-side; a copied LinkedIn note or calling script is outreach too."""
    manager, recruiter, _ = await _team(client, db_session)
    _, contact = await _contact(db_session, recruiter, status="do_not_contact")
    template = await _job_template(client, manager)
    await login(client, recruiter)
    refused = await client.post(f"{MESSAGES}/copies", json={"template_id": template["id"], "channel": "linkedin", "contact_id": str(contact.id)})
    assert refused.status_code == 409 and refused.json()["detail"] == "This contact has asked not to be contacted"
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.action == "recruiter_template.copy", AuditLog.entity_id == template["id"])) is None


@pytest.mark.asyncio
async def test_a_linkedin_or_call_template_cannot_be_sent_as_whatsapp(client, db_session):
    manager, recruiter, _ = await _team(client, db_session)
    _, contact = await _contact(db_session, recruiter)
    template = await _job_template(client, manager)
    await login(client, recruiter)
    response = await client.post(MESSAGES, json={"channel": "whatsapp", "contact_id": str(contact.id), "template_id": template["id"], "body": "Hi"})
    assert response.status_code == 422


# --- edge: an archived template referenced in old logs still renders its name -------------------------------------------------------
@pytest.mark.asyncio
async def test_an_archived_template_keeps_its_name_in_the_log_and_sending_bumps_last_used(client, db_session):
    manager, recruiter, _ = await _team(client, db_session)
    company, contact = await _contact(db_session, recruiter)
    await login(client, manager)
    template = await _create(client, wa_body())
    assert template["last_used_at"] is None
    await login(client, recruiter)
    assert (await client.post(MESSAGES, json={"channel": "whatsapp", "contact_id": str(contact.id), "template_id": template["id"], "body": "Hi"})).status_code == 201
    await login(client, manager)
    assert (await client.post(f"{TEMPLATES}/{template['id']}/archive")).status_code == 200
    item = (await client.get(TEMPLATES, params={"q": template["name"]})).json()["items"][0]
    assert item["last_used_at"] is not None
    await login(client, recruiter)
    listed = (await client.get(f"/api/v1/recruiter/companies/{company.id}/messages")).json()["items"]
    assert listed[0]["template"]["name"] == template["name"]
    assert (await client.get(TEMPLATES, params={"q": template["name"], "usable": True})).json()["total"] == 0


def test_the_allow_list_is_fixed():
    assert svc.PLACEHOLDERS == (
        "name", "company", "recruiter", "designation", "job_title", "job_location", "package_range", "candidate", "interview_date",
        "interview_time", "interview_mode", "interview_link",
    )  # fmt: skip
