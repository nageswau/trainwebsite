"""pob-003 -- company business context and last contact (DEC-SCOPE-406 D1-D5). Names are unique per test (shared database)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company, RecruiterMeeting, Skill, SkillCategory
from tests.rec001_helpers import login, make_pm, make_recruiter

BASE = "/api/v1/recruiter/companies"
CALLS = "/api/v1/recruiter/calls"
MESSAGES = "/api/v1/recruiter/messages"
CONTEXT = {
    "products_services": "Payroll software\nHR consulting",
    "departments_hiring": ["Engineering", "Sales"],
    "hiring_locations": ["Pune", "Remote"],
    "target_roles": ["Java Developer", "Account Executive"],
    "branch_locations": [{"city": "Pune", "state": "Maharashtra", "country": "India"}, {"city": "Austin", "state": None, "country": "USA"}],
}


def _name() -> str:
    return f"Ctx {uuid.uuid4().hex[:8]} Pvt"


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _company(client, **body) -> dict:
    response = await client.post(BASE, json={"name": _name(), **body})
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _skills(db, *, count: int = 2, active: bool = True) -> list[Skill]:
    category = await db.scalar(select(SkillCategory).limit(1))
    rows = [Skill(name=f"pob003 {uuid.uuid4().hex[:8]}", category_id=category.id, active=active) for _ in range(count)]
    db.add_all(rows)
    await db.commit()
    return rows


# --- D1-D3: saving and reading the context (AC1) -------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_every_business_context_field_saves_and_reads_back(client, db_session):
    await _team(client, db_session)
    java, sales = await _skills(db_session)
    company = await _company(client)
    assert company["branch_locations"] == [] and company["skill_demand"] == [] and company["departments_hiring"] == []
    assert company["products_services"] is None and company["last_contacted_at"] is None
    saved = await client.patch(f"{BASE}/{company['id']}", json={**CONTEXT, "skill_demand_ids": [str(sales.id), str(java.id)]})
    assert saved.status_code == 200, saved.text
    out = saved.json()["company"]
    for field in ("products_services", "departments_hiring", "hiring_locations", "target_roles", "branch_locations"):
        assert out[field] == CONTEXT[field], field
    assert [s["id"] for s in out["skill_demand"]] == [str(sales.id), str(java.id)]  # the saved order
    assert out["skill_demand"][0] == {"id": str(sales.id), "name": sales.name, "active": True}
    again = (await client.get(f"{BASE}/{company['id']}")).json()["company"]
    assert again["branch_locations"] == CONTEXT["branch_locations"] and len(again["skill_demand"]) == 2


@pytest.mark.asyncio
async def test_create_accepts_the_context_too(client, db_session):
    await _team(client, db_session)
    (skill,) = await _skills(db_session, count=1)
    company = await _company(client, **CONTEXT, skill_demand_ids=[str(skill.id)])
    assert company["target_roles"] == CONTEXT["target_roles"] and company["skill_demand"][0]["id"] == str(skill.id)
    assert company["branch_locations"][1]["country"] == "USA"


@pytest.mark.asyncio
async def test_lists_are_trimmed_and_deduplicated_and_empty_lists_clear(client, db_session):
    await _team(client, db_session)
    company = await _company(client, **CONTEXT)
    saved = await client.patch(f"{BASE}/{company['id']}", json={"departments_hiring": [" Engineering ", "engineering", "", "QA"]})
    assert saved.json()["company"]["departments_hiring"] == ["Engineering", "QA"]
    cleared = await client.patch(f"{BASE}/{company['id']}", json={"branch_locations": [], "target_roles": [], "skill_demand_ids": []})
    out = cleared.json()["company"]
    assert out["branch_locations"] == [] and out["target_roles"] == [] and out["hiring_locations"] == CONTEXT["hiring_locations"]


@pytest.mark.asyncio
async def test_the_legacy_branches_text_is_untouched(client, db_session):
    await _team(client, db_session)
    company = await _company(client, branches="Pune, Mumbai")
    out = (await client.patch(f"{BASE}/{company['id']}", json={"branch_locations": [{"city": "Delhi"}]})).json()["company"]
    assert out["branches"] == "Pune, Mumbai" and out["branch_locations"] == [{"city": "Delhi", "state": None, "country": None}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"branch_locations": [{"city": ""}]},
        {"branch_locations": [{"city": "Pune", "zip": "411001"}]},
        {"branch_locations": [{"city": f"C{i}"} for i in range(51)]},
        {"departments_hiring": [f"D{i}" for i in range(21)]},
        {"target_roles": ["x" * 121]},
        {"hiring_locations": ["Pune\u0007"]},
        {"products_services": "x" * 2001},
        {"skill_demand_ids": [str(uuid.uuid4())]},
        {"target_roles": None},
        {"branch_locations": None},
        {"branch_locations": [{"city": "Pune"}]},
    ],
)
async def test_invalid_context_is_a_422(client, db_session, body):
    await _team(client, db_session)
    company = await _company(client)
    assert (await client.patch(f"{BASE}/{company['id']}", json=body)).status_code == 422


@pytest.mark.asyncio
async def test_a_new_inactive_skill_is_refused_but_a_kept_one_stays(client, db_session):
    await _team(client, db_session)
    keep, other = await _skills(db_session)
    (inactive,) = await _skills(db_session, count=1, active=False)
    company = await _company(client, skill_demand_ids=[str(keep.id)])
    refused = await client.patch(f"{BASE}/{company['id']}", json={"skill_demand_ids": [str(keep.id), str(inactive.id)]})
    assert refused.status_code == 422 and refused.json()["detail"] == "Choose an active skill"
    keep.active = False
    await db_session.commit()
    kept = await client.patch(f"{BASE}/{company['id']}", json={"skill_demand_ids": [str(keep.id), str(other.id)]})
    assert kept.status_code == 200 and kept.json()["company"]["skill_demand"][0]["active"] is False


@pytest.mark.asyncio
async def test_a_repeated_skill_is_a_422(client, db_session):
    await _team(client, db_session)
    (skill,) = await _skills(db_session, count=1)
    company = await _company(client)
    assert (await client.patch(f"{BASE}/{company['id']}", json={"skill_demand_ids": [str(skill.id), str(skill.id)]})).status_code == 422


@pytest.mark.asyncio
async def test_unchanged_context_writes_no_audit_and_a_change_names_its_fields(client, db_session):
    await _team(client, db_session)
    company = await _company(client, **CONTEXT)
    await client.patch(f"{BASE}/{company['id']}", json=CONTEXT)
    await client.patch(f"{BASE}/{company['id']}", json={"target_roles": ["Tester"], "branch_locations": CONTEXT["branch_locations"]})
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == company["id"], AuditLog.action == "recruiter_company.update"))).all()
    assert [r.metadata_json["fields"] for r in rows] == [["target_roles"]]


@pytest.mark.asyncio
async def test_a_manager_cannot_edit_the_context(client, db_session):
    manager, _ = await _team(client, db_session)
    company = await _company(client)
    await login(client, manager)
    assert (await client.patch(f"{BASE}/{company['id']}", json={"target_roles": ["X"]})).status_code == 403


# --- D4 / D5: last contact (AC2) -----------------------------------------------------------------------------------------------------
async def _contact(client, company_id) -> str:
    response = await client.post(f"{BASE}/{company_id}/contacts", json={"name": "Priya HR", "mobile": "+91 98765 43210", "is_primary": True})
    assert response.status_code == 201, response.text
    return response.json()["items"][0]["id"]


async def _stored(db, company_id) -> Company:
    db.expire_all()
    return await db.scalar(select(Company).where(Company.id == uuid.UUID(company_id)))


@pytest.mark.asyncio
async def test_logging_a_call_sets_last_contact_without_bumping_updated_at(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    before = await _stored(db_session, company["id"])
    updated_at = before.updated_at
    at = datetime.now(UTC) - timedelta(minutes=5)
    logged = await client.post(CALLS, json={"contact_id": contact, "outcome": "connected", "occurred_at": at.isoformat()})
    assert logged.status_code == 201, logged.text
    stored = await _stored(db_session, company["id"])
    assert abs((stored.last_contacted_at - at).total_seconds()) < 1 and stored.updated_at == updated_at
    out = (await client.get(f"{BASE}/{company['id']}")).json()["company"]
    assert out["last_contacted_at"] is not None


@pytest.mark.asyncio
async def test_editing_or_deleting_a_call_recomputes_last_contact(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    now = datetime.now(UTC)
    first = (await client.post(CALLS, json={"contact_id": contact, "outcome": "connected", "occurred_at": (now - timedelta(minutes=30)).isoformat()})).json()
    second = (await client.post(CALLS, json={"contact_id": contact, "outcome": "no_answer", "occurred_at": (now - timedelta(minutes=2)).isoformat()})).json()
    assert (await client.delete(f"{CALLS}/{second['call']['id']}")).status_code == 204
    stored = await _stored(db_session, company["id"])
    assert abs((stored.last_contacted_at - (now - timedelta(minutes=30))).total_seconds()) < 1
    assert (await client.delete(f"{CALLS}/{first['call']['id']}")).status_code == 204
    assert (await _stored(db_session, company["id"])).last_contacted_at is None


@pytest.mark.asyncio
async def test_a_whatsapp_message_sets_last_contact(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    sent = await client.post(MESSAGES, json={"contact_id": contact, "channel": "whatsapp", "body": "Hello"})
    assert sent.status_code == 201, sent.text
    assert (await _stored(db_session, company["id"])).last_contacted_at is not None


@pytest.mark.asyncio
async def test_a_completed_meeting_sets_last_contact(client, db_session):
    _, recruiter = await _team(client, db_session)
    recruiter_id = recruiter.id
    company = await _company(client)
    starts = datetime.now(UTC) - timedelta(hours=1)
    meeting_id = uuid.uuid4()
    meeting = RecruiterMeeting(id=meeting_id, meeting_code=f"MTG-{uuid.uuid4().hex[:8]}", company_id=uuid.UUID(company["id"]), meeting_type="contract_discussion",
                               starts_at=starts, mode="Online", created_by_user_id=recruiter_id)  # fmt: skip
    db_session.add(meeting)
    await db_session.commit()
    assert (await _stored(db_session, company["id"])).last_contacted_at is None  # scheduled is not contact
    done = await client.post(f"/api/v1/recruiter/meetings/{meeting_id}/outcome", json={"outcome": "Agreed terms"})
    assert done.status_code == 200, done.text
    assert abs(((await _stored(db_session, company["id"])).last_contacted_at - starts).total_seconds()) < 1


@pytest.mark.asyncio
async def test_the_list_carries_last_contact_and_sorts_by_it_most_recent_first_never_last(client, db_session):
    await _team(client, db_session)
    tag = uuid.uuid4().hex[:6]
    names = [f"Srt {tag} {letter}" for letter in "ABC"]
    ids = [(await client.post(BASE, json={"name": n})).json()["company"]["id"] for n in names]
    now = datetime.now(UTC)
    for company_id, minutes in ((ids[0], 60), (ids[1], 5)):
        contact = await _contact(client, company_id)
        await client.post(CALLS, json={"contact_id": contact, "outcome": "connected", "occurred_at": (now - timedelta(minutes=minutes)).isoformat()})
    page = (await client.get(BASE, params={"q": f"Srt {tag}", "sort": "last_contacted"})).json()
    assert [r["name"] for r in page["items"]] == [names[1], names[0], names[2]]
    assert page["items"][2]["last_contacted_at"] is None and page["items"][0]["last_contacted_at"] is not None
    default = (await client.get(BASE, params={"q": f"Srt {tag}"})).json()
    assert [r["name"] for r in default["items"]] == names
    assert (await client.get(BASE, params={"sort": "nope"})).status_code == 422
