"""rec-003 -- the recruiter company master (spec §4-§5; AC1-AC7; DEC-SCOPE-119 D1-D6). Names are unique per test (shared database)."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company, CompanyAssignmentHistory, RecCampaign, RecIndustry, RecLeadSource
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user

BASE = "/api/v1/recruiter/companies"


def _name(prefix: str = "Acme") -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]} Technologies"


async def _source(db, name: str = "Website") -> RecLeadSource:
    return await db.scalar(select(RecLeadSource).where(RecLeadSource.name == name))


async def _create(client, **body):
    return await client.post(BASE, json={"name": _name(), **body})


async def _team(client, db):
    """A manager with one logged-in recruiter."""
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _audits(db, company_id, action):
    return (await db.scalars(select(AuditLog).where(AuditLog.entity_id == str(company_id), AuditLog.action == f"recruiter_company.{action}"))).all()


# --- create (AC1) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recruiter_creates_a_company_with_every_field(client, db_session):
    _, recruiter = await _team(client, db_session)
    source = await _source(db_session, "LinkedIn")
    campaign = RecCampaign(name=f"Camp {uuid.uuid4().hex[:6]}", lead_source_id=source.id, start_date=date(2026, 9, 1))
    industry = RecIndustry(name=f"Fintech {uuid.uuid4().hex[:6]}")
    bdm = await make_user(db_session, "bdm", "it")
    db_session.add_all([campaign, industry])
    await db_session.commit()
    body = {
        "website": "abc.example.com",
        "linkedin_url": "https://linkedin.com/company/abc",
        "industry_id": str(industry.id),
        "employee_count": 250,
        "city": "Pune",
        "state": "MH",
        "country": "India",
        "head_office": "Pune HQ",
        "branches": "Mumbai\nDelhi",
        "description": "Product company",
        "lead_source_id": str(source.id),
        "campaign_id": str(campaign.id),
        "priority": "hot",
        "assigned_bdm_user_id": str(bdm.id),
    }
    response = await _create(client, **body)
    assert response.status_code == 201, response.text
    company = response.json()["company"]
    assert company["code"].startswith("CMP-") and len(company["code"]) == 10
    assert company["assigned_recruiter"]["id"] == str(recruiter.id)
    assert company["website"] == "https://abc.example.com"
    assert company["lead_source"]["name"] == "LinkedIn" and company["campaign"]["id"] == str(campaign.id)
    assert company["industry"]["id"] == str(industry.id) and company["assigned_bdm"]["id"] == str(bdm.id)
    assert company["branches"] == "Mumbai\nDelhi" and company["priority"] == "hot" and company["employee_count"] == 250
    assert company["permissions"] == {"can_edit": True, "can_archive": True, "can_restore": False, "can_reassign": False}
    assert len(await _audits(db_session, company["id"], "create")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body, message",
    [
        ({"priority": "urgent"}, "priority"),
        ({"website": "javascript:alert(1)"}, "http"),
        ({"linkedin_url": "data:text/html,x"}, "http"),
        ({"employee_count": -1}, "employees"),
        ({"company_code": "CMP-999999"}, "company_code"),
        ({"name": "   "}, "Company name"),
    ],
)
async def test_invalid_input_is_a_422(client, db_session, body, message):
    await _team(client, db_session)
    response = await _create(client, **body)
    assert response.status_code == 422
    assert message in response.text


@pytest.mark.asyncio
async def test_campaign_must_belong_to_the_lead_source(client, db_session):
    await _team(client, db_session)
    linkedin, website = await _source(db_session, "LinkedIn"), await _source(db_session, "Website")
    campaign = RecCampaign(name=f"Camp {uuid.uuid4().hex[:6]}", lead_source_id=linkedin.id, start_date=date(2026, 9, 1))
    db_session.add(campaign)
    await db_session.commit()
    response = await _create(client, lead_source_id=str(website.id), campaign_id=str(campaign.id))
    assert response.status_code == 422 and "campaign" in response.text.lower()
    response = await _create(client, campaign_id=str(campaign.id))  # a campaign alone brings its lead source
    assert response.status_code == 201 and response.json()["company"]["lead_source"]["id"] == str(linkedin.id)


@pytest.mark.asyncio
async def test_inactive_catalogue_values_cannot_be_set(client, db_session):
    await _team(client, db_session)
    industry = RecIndustry(name=f"Old {uuid.uuid4().hex[:6]}", active=False)
    db_session.add(industry)
    await db_session.commit()
    response = await _create(client, industry_id=str(industry.id))
    assert response.status_code == 422 and "industry" in response.text.lower()
    response = await _create(client, industry_id=str(uuid.uuid4()))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_assigned_bdm_must_be_an_active_bdm(client, db_session):
    await _team(client, db_session)
    other = await make_user(db_session, "counselor", "overseas")
    inactive = await make_user(db_session, "bdm", "it", active=False)
    for user in (other, inactive):
        response = await _create(client, assigned_bdm_user_id=str(user.id))
        assert response.status_code == 422 and "BDM" in response.text


# --- duplicates (D2) ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exact_name_is_a_409_and_a_normalised_name_warns(client, db_session):
    await _team(client, db_session)
    name = _name("Dup")
    assert (await client.post(BASE, json={"name": name, "city": "Pune"})).status_code == 201
    exact = await client.post(BASE, json={"name": name, "confirm_duplicate": True})
    assert exact.status_code == 409 and "already exists" in exact.text
    similar = await client.post(BASE, json={"name": "  " + name.upper().replace(" ", "  ")})
    assert similar.status_code == 409
    detail = similar.json()["detail"]
    assert detail["code"] == "possible_duplicate" and detail["total"] == 1 and detail["matches"][0]["city"] == "Pune"
    confirmed = await client.post(BASE, json={"name": name.upper(), "confirm_duplicate": True})
    assert confirmed.status_code == 201
    assert len(await _audits(db_session, confirmed.json()["company"]["id"], "duplicate_override")) == 1


@pytest.mark.asyncio
async def test_employer_registration_collides_with_a_recruiter_company_name(client, db_session):
    await _team(client, db_session)
    name = _name("Shared")
    assert (await client.post(BASE, json={"name": name})).status_code == 201
    payload = {"email": f"emp-{uuid.uuid4().hex[:8]}@example.local", "password": "Sup3r-Secret-Pass!", "full_name": "Emp Contact", "company_name": name}
    assert (await client.post("/api/v1/employer/register", json=payload)).status_code == 409  # EMP-001 unchanged


# --- scope (AC2, AC3) -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_recruiter_sees_only_their_own_companies(client, db_session):
    manager, mine = await _team(client, db_session)
    own = (await _create(client)).json()["company"]
    other = await make_recruiter(db_session, manager)
    await login(client, other)
    theirs = (await _create(client)).json()["company"]
    assert (await client.get(f"{BASE}/{own['id']}")).status_code == 404
    ids = [c["id"] for c in (await client.get(BASE, params={"limit": 100})).json()["items"]]
    assert theirs["id"] in ids and own["id"] not in ids
    assert (await client.patch(f"{BASE}/{own['id']}", json={"city": "X"})).status_code == 404


@pytest.mark.asyncio
async def test_manager_reassigns_with_history(client, db_session):
    manager, first = await _team(client, db_session)
    company = (await _create(client)).json()["company"]
    second = await make_recruiter(db_session, manager)
    assert (await client.post(f"{BASE}/{company['id']}/assign", json={"recruiter_user_id": str(second.id)})).status_code == 403
    await login(client, manager)
    listed = (await client.get(BASE, params={"assigned": str(first.id), "limit": 100})).json()["items"]
    assert company["id"] in [c["id"] for c in listed]
    response = await client.post(f"{BASE}/{company['id']}/assign", json={"recruiter_user_id": str(second.id)})
    assert response.status_code == 200, response.text
    body = response.json()["company"]
    assert body["assigned_recruiter"]["id"] == str(second.id)
    assert body["permissions"] == {"can_edit": False, "can_archive": False, "can_restore": False, "can_reassign": True}
    history = body["assignment_history"]
    assert len(history) == 1 and history[0]["from_user"]["id"] == str(first.id) and history[0]["to_user"]["id"] == str(second.id)
    assert history[0]["changed_by"]["id"] == str(manager.id)
    again = await client.post(f"{BASE}/{company['id']}/assign", json={"recruiter_user_id": str(second.id)})
    assert again.status_code == 409
    await login(client, first)
    assert (await client.get(f"{BASE}/{company['id']}")).status_code == 404
    await login(client, second)
    assert (await client.get(f"{BASE}/{company['id']}")).status_code == 200
    assert len(await _audits(db_session, company["id"], "assign")) == 1


@pytest.mark.asyncio
async def test_reassign_target_must_be_an_active_recruiter_in_the_team(client, db_session):
    manager, _ = await _team(client, db_session)
    company = (await _create(client)).json()["company"]
    outsider = await make_recruiter(db_session, await make_pm(db_session))
    inactive = await make_recruiter(db_session, manager, active=False)
    not_recruiter = await make_user(db_session, "hr_team", "it")
    await login(client, manager)
    for target in (outsider, inactive, not_recruiter):
        response = await client.post(f"{BASE}/{company['id']}/assign", json={"recruiter_user_id": str(target.id)})
        assert response.status_code == 422, target.role
    super_admin = await as_role(client, db_session, "super_admin", "global")
    assert super_admin
    response = await client.post(f"{BASE}/{company['id']}/assign", json={"recruiter_user_id": str(outsider.id)})
    assert response.status_code == 200  # super_admin: any active recruiter


@pytest.mark.asyncio
async def test_another_managers_team_is_out_of_scope(client, db_session):
    _, _ = await _team(client, db_session)
    company = (await _create(client)).json()["company"]
    await as_role(client, db_session, "placement_manager", "global")
    assert (await client.get(f"{BASE}/{company['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_manager_creates_unassigned_or_for_a_report(client, db_session):
    manager, recruiter = await _team(client, db_session)
    await login(client, manager)
    unassigned = await _create(client)
    assert unassigned.status_code == 201 and unassigned.json()["company"]["assigned_recruiter"] is None
    assigned = await _create(client, assigned_recruiter_user_id=str(recruiter.id))
    assert assigned.status_code == 201 and assigned.json()["company"]["assigned_recruiter"]["id"] == str(recruiter.id)
    company_id = assigned.json()["company"]["id"]
    history = (await db_session.scalars(select(CompanyAssignmentHistory).where(CompanyAssignmentHistory.company_id == uuid.UUID(company_id)))).all()
    assert len(history) == 1 and history[0].from_user_id is None
    queue = (await client.get(BASE, params={"assigned": "unassigned", "limit": 100})).json()["items"]
    assert unassigned.json()["company"]["id"] in [c["id"] for c in queue]
    await login(client, recruiter)
    response = await _create(client, assigned_recruiter_user_id=str(manager.id))
    assert response.status_code == 403  # a recruiter's companies are always their own


# --- edit / archive / restore (AC6, AC7) ----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_edit_is_partial_and_a_noop_is_not_audited(client, db_session):
    manager, _ = await _team(client, db_session)
    company = (await _create(client, city="Pune")).json()["company"]
    response = await client.patch(f"{BASE}/{company['id']}", json={"city": "Mumbai", "priority": "warm"})
    assert response.status_code == 200 and response.json()["company"]["city"] == "Mumbai"
    assert (await client.patch(f"{BASE}/{company['id']}", json={"city": "Mumbai"})).status_code == 200
    assert len(await _audits(db_session, company["id"], "update")) == 1
    assert (await client.patch(f"{BASE}/{company['id']}", json={"priority": None})).json()["company"]["priority"] is None
    await login(client, manager)
    assert (await client.patch(f"{BASE}/{company['id']}", json={"city": "Delhi"})).status_code == 403


@pytest.mark.asyncio
async def test_archive_hides_and_restore_is_the_managers(client, db_session):
    manager, recruiter = await _team(client, db_session)
    company = (await _create(client)).json()["company"]
    url = f"{BASE}/{company['id']}"
    assert (await client.post(f"{url}/archive")).json()["company"]["archived"] is True
    assert (await client.post(f"{url}/archive")).status_code == 409
    assert (await client.patch(url, json={"city": "X"})).status_code == 409
    assert company["id"] not in [c["id"] for c in (await client.get(BASE, params={"limit": 100})).json()["items"]]
    archived = (await client.get(BASE, params={"limit": 100, "include_archived": True})).json()["items"]
    assert company["id"] in [c["id"] for c in archived]
    assert (await client.post(f"{url}/restore")).status_code == 403
    await login(client, manager)
    assert (await client.post(f"{url}/assign", json={"recruiter_user_id": str(recruiter.id)})).status_code == 409
    assert (await client.post(f"{url}/restore")).json()["company"]["archived"] is False


# --- the assigned BDM (R10) and outsiders ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_assigned_bdm_reads_but_cannot_write(client, db_session):
    await _team(client, db_session)
    bdm = await make_user(db_session, "bdm", "it")
    company = (await _create(client, assigned_bdm_user_id=str(bdm.id))).json()["company"]
    other_bdm = await make_user(db_session, "bdm", "it")
    await login(client, bdm)
    body = (await client.get(f"{BASE}/{company['id']}")).json()["company"]
    assert body["permissions"] == {"can_edit": False, "can_archive": False, "can_restore": False, "can_reassign": False}
    assert company["id"] in [c["id"] for c in (await client.get(BASE)).json()["items"]]
    assert (await client.patch(f"{BASE}/{company['id']}", json={"city": "X"})).status_code == 403
    assert (await client.post(f"{BASE}/{company['id']}/archive")).status_code == 403
    assert (await _create(client)).status_code == 403
    assert (await client.get(f"{BASE}/bdm-options")).status_code == 403
    await login(client, other_bdm)
    assert (await client.get(f"{BASE}/{company['id']}")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("hr_team", "it"), ("it_admin", "it"), ("employer", "it"), ("it_student", "it"), ("telecaller", "global")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(BASE)).status_code == 403
    assert (await _create(client)).status_code == 403


@pytest.mark.asyncio
async def test_bdm_options_lists_active_bdms_only(client, db_session):
    await _team(client, db_session)
    tag = uuid.uuid4().hex[:6]
    active = await make_user(db_session, "bdm", "it", name=f"Bdm Active {tag}")
    await make_user(db_session, "bdm", "it", active=False, name=f"Bdm Gone {tag}")
    items = (await client.get(f"{BASE}/bdm-options", params={"q": tag})).json()["items"]
    assert items == [{"id": str(active.id), "full_name": active.full_name}]


# --- employer self-registration (AC4) -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_employer_company_lands_unassigned_with_source_website(client, db_session):
    name = _name("Employer")
    payload = {"email": f"emp-{uuid.uuid4().hex[:8]}@example.local", "password": "Sup3r-Secret-Pass!", "full_name": "Emp Contact", "company_name": name}
    assert (await client.post("/api/v1/employer/register", json=payload)).status_code == 200  # EMP-001 contract
    company = await db_session.scalar(select(Company).where(Company.name == name))
    assert company.company_code.startswith("CMP-") and company.assigned_recruiter_user_id is None
    assert company.lead_source_id == (await _source(db_session, "Website")).id
    await as_role(client, db_session, "placement_manager", "global")
    queue = (await client.get(BASE, params={"assigned": "unassigned", "q": name})).json()["items"]
    assert [c["id"] for c in queue] == [str(company.id)] and queue[0]["lead_source"]["name"] == "Website"


@pytest.mark.asyncio
async def test_list_filters_and_search_by_code(client, db_session):
    await _team(client, db_session)
    hot = (await _create(client, priority="hot", city="Chennai")).json()["company"]
    await _create(client, priority="cold")
    by_code = (await client.get(BASE, params={"q": hot["code"]})).json()
    assert [c["id"] for c in by_code["items"]] == [hot["id"]] and by_code["total"] == 1
    hot_ids = [c["id"] for c in (await client.get(BASE, params={"priority": "hot", "city": "chenn", "limit": 100})).json()["items"]]
    assert hot["id"] in hot_ids
    assert (await client.get(BASE, params={"priority": "urgent"})).status_code == 422
    assert (await client.get(BASE, params={"assigned": "nobody"})).status_code == 422
