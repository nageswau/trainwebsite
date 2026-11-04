"""hrc-005 (DEC-SCOPE-380) -- vacancy fields completion and job duplicate detection (AC1-AC7, V1-V9). Names are unique per test (the
database is shared and never truncated)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Job, RecLeadSource
from app.services.recruiter_requirements import ist_today
from tests.rec001_helpers import login, make_user
from tests.test_rec_007_requirements import BASE, _company, _team


def _tag() -> str:
    return uuid.uuid4().hex[:8]


async def _source(db) -> RecLeadSource:
    row = RecLeadSource(name=f"Src {_tag()}", sort_order=9999)
    db.add(row)
    await db.commit()
    return row


async def _post(client, company, **body):
    return await client.post(BASE, json={"company_id": str(company.id), "title": f"Analyst {_tag()}", "location": "Pune", **body})


# --- AC1: every §4.2 field saves, reads and clears ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_every_new_field_saves_and_reads_back(client, db_session):
    _, _, company = await _team(client, db_session)
    source = await _source(db_session)
    manager = await make_user(db_session, "interviewer", "it")
    body = {
        "requisition_reference": f"RQ-{_tag()}", "source_id": str(source.id), "certifications": "AWS SAA\nCKA", "country": "India",
        "state": "Maharashtra", "city": "Pune", "relocation_required": True, "travel_requirement": "Up to 25%", "salary_currency": "usd",
        "salary_period": "month", "salary_min": "1000", "salary_max": "2000", "benefits": "Health cover\nMeals",
        "hiring_manager_user_id": str(manager.id), "expected_joining_date": str(ist_today() + timedelta(days=45)),
    }
    response = await _post(client, company, **body)
    assert response.status_code == 201, response.text
    req = response.json()["requirement"]
    for key in ("requisition_reference", "certifications", "country", "state", "city", "relocation_required", "travel_requirement",
                "salary_period", "benefits", "expected_joining_date"):  # fmt: skip
        assert req[key] == body[key], key
    assert req["salary_currency"] == "USD"
    assert req["source"]["id"] == str(source.id)
    assert req["hiring_manager"]["id"] == str(manager.id)
    assert req["updated_by"]["id"] == req["created_by"]["id"]

    cleared = {k: None for k in ("requisition_reference", "source_id", "certifications", "relocation_required", "travel_requirement",
                                 "salary_currency", "salary_period", "benefits", "hiring_manager_user_id", "expected_joining_date")}  # fmt: skip
    response = await client.patch(f"{BASE}/{req['id']}", json=cleared)
    assert response.status_code == 200, response.text
    out = response.json()["requirement"]
    assert out["source"] is None and out["hiring_manager"] is None and out["requisition_reference"] is None and out["benefits"] is None


@pytest.mark.asyncio
async def test_bad_values_are_422(client, db_session):
    _, recruiter, company = await _team(client, db_session)
    for body in ({"salary_currency": "rupees"}, {"salary_period": "hour"}, {"hiring_manager_user_id": str(recruiter.id)},
                 {"source_id": str(uuid.uuid4())}):  # fmt: skip
        response = await _post(client, company, **body)
        assert response.status_code == 422, (body, response.text)


@pytest.mark.asyncio
async def test_hiring_manager_picker_lists_active_interviewers_only(client, db_session):
    await _team(client, db_session)
    name = f"Hm {_tag()}"
    active = await make_user(db_session, "interviewer", "it", name=name)
    await make_user(db_session, "interviewer", "it", name=f"{name} gone", active=False)
    await make_user(db_session, "hr_manager", "it", name=f"{name} hr")
    response = await client.get(f"{BASE}/hiring-managers", params={"q": name})
    assert response.status_code == 200, response.text
    assert [i["id"] for i in response.json()["items"]] == [str(active.id)]


@pytest.mark.asyncio
async def test_hiring_manager_picker_refuses_non_writers(client, db_session):
    await login(client, await make_user(db_session, "it_student", "it"))
    assert (await client.get(f"{BASE}/hiring-managers")).status_code == 403


# --- V3 / AC4: location ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_location_is_derived_from_city_state_country_and_follows_them(client, db_session):
    _, _, company = await _team(client, db_session)
    response = await client.post(BASE, json={"company_id": str(company.id), "title": f"Ops {_tag()}", "city": "Pune", "state": "Maharashtra", "country": "India"})
    assert response.status_code == 201, response.text
    req = response.json()["requirement"]
    assert req["location"] == "Pune, Maharashtra, India"
    moved = (await client.patch(f"{BASE}/{req['id']}", json={"city": "Mumbai"})).json()["requirement"]
    assert moved["location"] == "Mumbai, Maharashtra, India"
    typed = (await client.patch(f"{BASE}/{req['id']}", json={"location": "Andheri office"})).json()["requirement"]
    kept = (await client.patch(f"{BASE}/{typed['id']}", json={"city": "Thane"})).json()["requirement"]
    assert kept["location"] == "Andheri office"


@pytest.mark.asyncio
async def test_location_or_city_is_required(client, db_session):
    _, _, company = await _team(client, db_session)
    response = await client.post(BASE, json={"company_id": str(company.id), "title": f"Ops {_tag()}"})
    assert response.status_code == 422
    assert "location" in response.text.lower()


# --- V4/V5 / AC2-AC3: duplicates -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_same_company_title_and_city_is_a_possible_duplicate(client, db_session):
    _, _, company = await _team(client, db_session)
    title = f"Data Engineer {_tag()}"
    first = await client.post(BASE, json={"company_id": str(company.id), "title": title, "city": "Pune"})
    assert first.status_code == 201
    response = await client.post(BASE, json={"company_id": str(company.id), "title": f"  {title.upper()} ", "city": "pune", "location": "Hinjewadi"})
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "possible_duplicate" and detail["total"] == 1
    assert detail["matches"][0]["code"] == first.json()["requirement"]["code"]


@pytest.mark.asyncio
async def test_legacy_free_text_location_matches_the_city(client, db_session):
    _, recruiter, company = await _team(client, db_session)
    title = f"Tester {_tag()}"
    db_session.add(Job(company_id=company.id, title=title, location="Pune", description="", skills=[], status="sourcing", assigned_recruiter_user_id=recruiter.id))
    await db_session.commit()
    response = await client.post(BASE, json={"company_id": str(company.id), "title": title, "city": "Pune", "state": "MH"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_ended_jobs_and_other_companies_never_match(client, db_session):
    _, recruiter, company = await _team(client, db_session)
    other = await _company(db_session, recruiter)
    title = f"Closer {_tag()}"
    db_session.add(Job(company_id=company.id, title=title, location="Pune", description="", skills=[], status="closed", assigned_recruiter_user_id=recruiter.id))
    db_session.add(Job(company_id=other.id, title=title, location="Pune", description="", skills=[], status="sourcing", assigned_recruiter_user_id=recruiter.id))
    await db_session.commit()
    assert (await client.post(BASE, json={"company_id": str(company.id), "title": title, "location": "Pune"})).status_code == 201


@pytest.mark.asyncio
async def test_same_requisition_reference_needs_a_reason_which_is_audited(client, db_session):
    _, _, company = await _team(client, db_session)
    ref = f"RQ-{_tag()}"
    first = await _post(client, company, requisition_reference=ref)
    assert first.status_code == 201
    refused = await _post(client, company, requisition_reference=f" {ref.lower()} ")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "possible_duplicate"
    saved = await _post(client, company, requisition_reference=ref, duplicate_reason="Second batch, client confirmed")
    assert saved.status_code == 201, saved.text
    job_id = saved.json()["requirement"]["id"]
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == job_id, AuditLog.action == "recruiter_requirement.duplicate_override"))
    assert row.metadata_json["reason"] == "Second batch, client confirmed"
    assert row.metadata_json["match_codes"] == [first.json()["requirement"]["code"]]


@pytest.mark.asyncio
async def test_an_edit_into_a_duplicate_is_checked_but_unrelated_edits_are_not(client, db_session):
    _, _, company = await _team(client, db_session)
    title = f"Backend {_tag()}"
    await client.post(BASE, json={"company_id": str(company.id), "title": title, "city": "Pune"})
    other = (await client.post(BASE, json={"company_id": str(company.id), "title": f"Frontend {_tag()}", "city": "Pune"})).json()["requirement"]
    response = await client.patch(f"{BASE}/{other['id']}", json={"title": title})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "possible_duplicate"
    assert (await client.patch(f"{BASE}/{other['id']}", json={"title": title, "duplicate_reason": "Different team"})).status_code == 200
    # the job is now a duplicate itself; editing something unrelated does not ask again
    assert (await client.patch(f"{BASE}/{other['id']}", json={"department": "Platform"})).status_code == 200


@pytest.mark.asyncio
async def test_a_stale_save_is_still_record_changed_before_the_duplicate_check(client, db_session):
    _, _, company = await _team(client, db_session)
    title = f"Stale {_tag()}"
    await client.post(BASE, json={"company_id": str(company.id), "title": title, "city": "Pune"})
    other = (await client.post(BASE, json={"company_id": str(company.id), "title": f"Other {_tag()}", "city": "Pune"})).json()["requirement"]
    await client.patch(f"{BASE}/{other['id']}", json={"department": "X"})
    response = await client.patch(f"{BASE}/{other['id']}", json={"title": title, "expected_updated_at": other["updated_at"]})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "record_changed"


# --- V6 / AC5: last updated by ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_updated_by_follows_the_last_writer(client, db_session):
    manager, recruiter, company = await _team(client, db_session)
    req = (await _post(client, company)).json()["requirement"]
    admin = await make_user(db_session, "super_admin", "global")
    await login(client, admin)
    out = (await client.patch(f"{BASE}/{req['id']}", json={"department": "Finance"})).json()["requirement"]
    assert out["updated_by"]["id"] == str(admin.id)
    await login(client, recruiter)
    out = (await client.post(f"{BASE}/{req['id']}/status", json={"status": "requirement_received"})).json()["requirement"]
    assert out["updated_by"]["id"] == str(recruiter.id)


# --- V7 / AC7: history redaction ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_history_hides_pay_currency_period_and_benefits(client, db_session):
    _, _, company = await _team(client, db_session)
    req = (await _post(client, company)).json()["requirement"]
    await client.patch(f"{BASE}/{req['id']}", json={"salary_currency": "EUR", "salary_period": "month", "benefits": "Car", "city": "Pune"})
    item = (await client.get(f"{BASE}/{req['id']}/history")).json()["items"][0]
    for key in ("salary_currency", "salary_period", "benefits"):
        assert "EUR" not in str(item["changes"][key]) and "Car" not in str(item["changes"][key]), item["changes"][key]
    assert "Pune" in str(item["changes"]["city"])
