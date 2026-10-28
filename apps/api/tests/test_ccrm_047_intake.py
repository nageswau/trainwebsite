"""ccrm-047 -- the intake is a month and year ("Sep 2027") wherever it is entered: lead create (telecaller, manager, counselor walk-in),
the lead qualification, the student profile (student and staff) and the application create. A new value in another shape is 422; a
legacy free-text value already stored is kept on an unrelated save (AC6). The shared test database is never truncated."""

import uuid

import pytest
from sqlalchemy import select

from app.models import Enquiry, LeadQualification, OverseasApplication, OverseasStudentProfile, TelProduct
from tests.agn001_helpers import login, mk_user, uniq
from tests.bdm017_helpers import as_user
from tests.enh031_helpers import mk_application, mk_university
from tests.tel004_helpers import make_telecaller, make_tl_manager

LEADS = "/api/v1/telecaller/leads"
WALK_IN = "/api/v1/counselor/walk-in-leads"
APPLY = "/api/v1/workflows/overseas/applications"
ME = "/api/v1/overseas/me/profile"
BAD = ["September next year", "Sep", "2027", "sep 2027", "Sept 2027", "Sep  2027", "Fall 2027"]


def mobile() -> str:
    return f"9{uuid.uuid4().int % 10**9:09d}"


async def product(db, group: str, name: str) -> TelProduct:
    return await db.scalar(select(TelProduct).where(TelProduct.product_group == group, TelProduct.name == name))


async def lead_body(db, group: str = "overseas", name: str = "UK", **over) -> dict:
    prod = await product(db, group, name)
    return {"name": "Asha Rao", "phone": mobile(), "product_id": str(prod.id), "source": "instagram"} | over


async def qualification(db, lead_id) -> LeadQualification | None:
    stmt = select(LeadQualification).where(LeadQualification.lead_id == uuid.UUID(str(lead_id))).execution_options(populate_existing=True)
    return await db.scalar(stmt)


# --- lead create (AC1, AC5, IT edge) ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_telecaller_lead_keeps_its_intake_and_the_lead_detail_shows_it(client, db_session):
    tel = await make_telecaller(db_session, await make_tl_manager(db_session), team="overseas")
    await as_user(client, tel)
    response = await client.post(LEADS, json=await lead_body(db_session, intake="Sep 2027"))
    assert response.status_code == 201, response.text
    lead_id = response.json()["id"]
    row = await qualification(db_session, lead_id)
    assert row is not None and row.intake == "Sep 2027" and row.updated_by_user_id == tel.id
    shown = await client.get(f"{LEADS}/{lead_id}/qualification")
    assert shown.status_code == 200 and shown.json()["intake"] == "Sep 2027"


@pytest.mark.asyncio
async def test_a_lead_without_an_intake_gets_no_qualification_row(client, db_session):
    tel = await make_telecaller(db_session, await make_tl_manager(db_session), team="overseas")
    await as_user(client, tel)
    response = await client.post(LEADS, json=await lead_body(db_session))
    assert response.status_code == 201, response.text
    assert await qualification(db_session, response.json()["id"]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", BAD)
async def test_a_malformed_lead_intake_is_422_and_creates_nothing(client, db_session, bad):
    tel = await make_telecaller(db_session, await make_tl_manager(db_session), team="overseas")
    await as_user(client, tel)
    payload = await lead_body(db_session, intake=bad)
    response = await client.post(LEADS, json=payload)
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"][-1] == "intake"
    assert await db_session.scalar(select(Enquiry.id).where(Enquiry.phone == payload["phone"])) is None


@pytest.mark.asyncio
async def test_an_it_lead_cannot_carry_an_intake(client, db_session):
    tel = await make_telecaller(db_session, await make_tl_manager(db_session))
    await as_user(client, tel)
    payload = await lead_body(db_session, "it", "Cyber Security", intake="Sep 2027")
    response = await client.post(LEADS, json=payload)
    assert response.status_code == 422, response.text
    assert await db_session.scalar(select(Enquiry.id).where(Enquiry.phone == payload["phone"])) is None


@pytest.mark.asyncio
async def test_a_counselor_walk_in_lead_keeps_its_intake(client, db_session):
    counselor = await mk_user(db_session, role="counselor", full_name="Walk In Counselor")
    await login(client, counselor.email)
    response = await client.post(WALK_IN, json=await lead_body(db_session, source="walk_in", intake="Jan 2028"))
    assert response.status_code == 201, response.text
    assert (await qualification(db_session, response.json()["id"])).intake == "Jan 2028"


# --- lead qualification (AC5, AC6) ------------------------------------------------------------------------------------------------
async def qualified_lead(db, intake: str):
    tel = await make_telecaller(db, await make_tl_manager(db), team="overseas")
    uk = await product(db, "overseas", "UK")
    lead = Enquiry(
        division="overseas", name=f"Lead {uuid.uuid4().hex[:6]}", phone=mobile(), subject="Study abroad", message="", source="website", telecaller_user_id=tel.id, product_id=uk.id, status="contacted"
    )
    db.add(lead)
    await db.flush()
    db.add(LeadQualification(lead_id=lead.id, intake=intake, updated_by_user_id=tel.id))
    await db.commit()
    return tel, lead


@pytest.mark.asyncio
async def test_a_new_qualification_intake_must_be_a_month_and_year(client, db_session):
    tel, lead = await qualified_lead(db_session, "Sep 2027")
    await as_user(client, tel)
    bad = await client.put(f"{LEADS}/{lead.id}/qualification", json={"intake": "September next year"})
    assert bad.status_code == 422 and bad.json()["detail"][0]["loc"][-1] == "intake"
    good = await client.put(f"{LEADS}/{lead.id}/qualification", json={"intake": "Feb 2028"})
    assert good.status_code == 200, good.text
    assert good.json()["intake"] == "Feb 2028"


@pytest.mark.asyncio
async def test_a_legacy_qualification_intake_survives_an_unrelated_save(client, db_session):
    tel, lead = await qualified_lead(db_session, "Fall 2027 maybe")
    await as_user(client, tel)
    response = await client.put(f"{LEADS}/{lead.id}/qualification", json={"intake": "Fall 2027 maybe", "city": "Pune"})
    assert response.status_code == 200, response.text
    assert response.json()["intake"] == "Fall 2027 maybe" and response.json()["city"] == "Pune"


# --- student profile (AC2, AC3, AC5, AC6) -----------------------------------------------------------------------------------------
async def caseload(db):
    counselor = await mk_user(db, role="counselor", full_name="Intake Counselor")
    student = await mk_user(db, role="overseas_student", full_name=f"{uniq('i47')} Student")
    await mk_application(db, student=student, university=await mk_university(db, name=uniq("Intake Uni")), counselor=counselor)
    return counselor, student


@pytest.mark.asyncio
async def test_the_student_sets_a_preferred_intake(client, db_session):
    _, student = await caseload(db_session)
    await login(client, student.email)
    response = await client.put(ME, json={"preferred_intake": "Sep 2027"})
    assert response.status_code == 200, response.text
    assert response.json()["profile"]["preferred_intake"] == "Sep 2027"
    bad = await client.put(ME, json={"preferred_intake": "September next year"})
    assert bad.status_code == 422 and bad.json()["detail"][0]["loc"][-1] == "preferred_intake"


@pytest.mark.asyncio
async def test_the_counselor_edits_the_students_intake(client, db_session):
    counselor, student = await caseload(db_session)
    await login(client, counselor.email)
    url = f"/api/v1/counselor/students/{student.id}/profile"
    response = await client.put(url, json={"preferred_intake": "Jan 2029"})
    assert response.status_code == 200 and response.json()["profile"]["preferred_intake"] == "Jan 2029"
    assert (await client.put(url, json={"preferred_intake": "Spring 2029"})).status_code == 422


@pytest.mark.asyncio
async def test_a_legacy_profile_intake_survives_an_unrelated_save(client, db_session):
    counselor, student = await caseload(db_session)
    db_session.add(OverseasStudentProfile(student_user_id=student.id, preferred_intake="September 2027", updated_by_user_id=counselor.id))
    await db_session.commit()
    await login(client, student.email)
    response = await client.put(ME, json={"preferred_intake": "September 2027", "city": "Hyderabad"})
    assert response.status_code == 200, response.text
    assert response.json()["profile"]["preferred_intake"] == "September 2027" and response.json()["profile"]["city"] == "Hyderabad"


async def stored_intake(db, application_id) -> str:
    stmt = select(OverseasApplication.intake).where(OverseasApplication.id == uuid.UUID(application_id)).execution_options(populate_existing=True)
    return await db.scalar(stmt)


# --- application create (AC4, AC5) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_application_intake_must_be_a_month_and_year(client, db_session):
    student = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('a47')} Student")
    await login(client, student.email)
    university = await mk_university(db_session, name=uniq("Apply Uni"))
    bad = await client.post(APPLY, json={"university_id": str(university.id), "intake": "September next year"})
    assert bad.status_code == 422 and bad.json()["detail"][0]["loc"][-1] == "intake"
    good = await client.post(APPLY, json={"university_id": str(university.id), "intake": "Sep 2027"})
    assert good.status_code == 201, good.text
    assert await stored_intake(db_session, good.json()["id"]) == "Sep 2027"


@pytest.mark.asyncio
async def test_an_application_without_an_intake_keeps_the_server_default(client, db_session):
    student = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('d47')} Student")
    await login(client, student.email)
    university = await mk_university(db_session, name=uniq("Default Uni"))
    response = await client.post(APPLY, json={"university_id": str(university.id)})
    assert response.status_code == 201, response.text
    assert await stored_intake(db_session, response.json()["id"]) == "Next intake"
