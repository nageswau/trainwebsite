import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentCommission, AgentOrg, AgentOrgMember, AgentStudent, Country, OverseasApplication, StudentDocument, University, User, UserRoleAssignment
from tests.agn001_helpers import client_for, login, mk_active_org, mk_user


async def _university(db) -> University:
    country = Country(slug=f"agn-c-{uuid.uuid4().hex[:8]}", name="Testland", overview="", tuition="", living_expenses="", visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[])
    db.add(country)
    await db.flush()
    university = University(country_id=country.id, slug=f"agn-u-{uuid.uuid4().hex[:8]}", name=f"AGN Uni {uuid.uuid4().hex[:6]}", city="", overview="", eligibility="", requirements=[], deadlines=[], scholarships=[])
    db.add(university)
    await db.commit()
    return university


async def _tenant(db, name: str) -> dict:
    ctx = await mk_active_org(db, name=name)
    student = await mk_user(db, role="overseas_student", full_name=f"{name} Student")
    university = await _university(db)
    db.add(AgentStudent(agent_id=ctx["master"].id, student_id=student.id, status="active"))
    application = OverseasApplication(student_id=student.id, university_id=university.id, agent_id=ctx["master"].id, intake="Sep 2027", status="enrolled")
    db.add(application)
    await db.flush()
    document = StudentDocument(student_id=student.id, application_id=application.id, document_type="passport", file_url="local/agn.pdf")
    commission = AgentCommission(agent_id=ctx["master"].id, application_id=application.id, amount=1000, currency="INR", status="eligible")
    db.add_all([document, commission])
    await db.commit()
    return ctx | {"student": student, "university": university, "application": application, "document": document, "commission": commission}


async def _second_master(db, tenant) -> User:
    """Another Master of the tenant's organisation, with a usable password (bypasses the invite for scoping tests)."""
    user = await mk_user(db, role="agent", full_name="Second Master")
    db.add(UserRoleAssignment(user_id=user.id, division="overseas", role="agent", approval_status="approved"))
    org = await db.get(AgentOrg, tenant["org"].id, populate_existing=True)
    org.master_seq += 1
    db.add(AgentOrgMember(org_id=org.id, user_id=user.id, role="master", seq=org.master_seq, code=f"{org.prefix}-M{org.master_seq:03d}", status="active"))
    await db.commit()
    return user


@pytest_asyncio.fixture
async def world(db_session):
    return {"a": await _tenant(db_session, "Alpha Agency"), "b": await _tenant(db_session, "Bravo Agency")}


READS = [
    ("/api/v1/workflows/overseas/agent/students", "student_id", "student"),
    ("/api/v1/workflows/overseas/agent/commissions", "id", "commission"),
    ("/api/v1/workflows/overseas/applications", "id", "application"),
]
PORTAL_SECTIONS = ["dashboard", "students", "applications", "documents", "commissions", "reports"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("url", "key", "kind"), READS)
async def test_lists_show_own_org_rows_and_never_the_other_orgs(client, world, url, key, kind):  # AC06 reads
    await login(client, world["a"]["master"].email)
    ids = {str(row[key]) for row in (await client.get(url)).json()}
    assert str(world["a"][kind].id) in ids and str(world["b"][kind].id) not in ids


@pytest.mark.asyncio
@pytest.mark.parametrize("section", PORTAL_SECTIONS)
async def test_portal_sections_never_mention_the_other_org(client, world, section):  # AC06 portal
    await login(client, world["a"]["master"].email)
    response = await client.get(f"/api/v1/portal/overseas/agent/{section}")
    assert response.status_code == 200
    text = response.text
    for thing in ("student", "application", "document", "commission"):
        assert str(world["b"][thing].id) not in text
    assert world["b"]["student"].full_name not in text and world["b"]["master"].email not in text


@pytest.mark.asyncio
async def test_writes_on_the_other_orgs_rows_are_refused(client, world, db_session):  # AC06 writes
    a, b = world["a"], world["b"]
    await login(client, a["master"].email)
    claim = await client.post(f"/api/v1/workflows/overseas/agent/commissions/{b['commission'].id}/claim")
    assert claim.status_code == 404
    app = await client.post("/api/v1/workflows/overseas/applications", json={"student_id": str(b["student"].id), "university_id": str(b["university"].id), "intake": "Jan 2028"})
    assert app.status_code == 403
    doc_on_app = await client.post("/api/v1/workflows/overseas/documents", json={"student_id": str(b["student"].id), "application_id": str(b["application"].id), "document_type": "passport", "file_url": "local/x.pdf"})
    assert doc_on_app.status_code == 403
    doc_plain = await client.post("/api/v1/workflows/overseas/documents", json={"student_id": str(b["student"].id), "document_type": "passport", "file_url": "local/x.pdf"})
    assert doc_plain.status_code == 403
    download = await client.get(f"/api/v1/workflows/overseas/documents/{b['document'].id}/download")
    assert download.status_code == 403
    await db_session.refresh(b["commission"])
    assert b["commission"].status == "eligible"


@pytest.mark.asyncio
async def test_a_second_master_sees_and_claims_what_the_first_created(client, world, db_session):  # D1 in-org sharing
    a = world["a"]
    second = await _second_master(db_session, a)
    await login(client, second.email)
    students = (await client.get("/api/v1/workflows/overseas/agent/students")).json()
    assert str(a["student"].id) in {s["student_id"] for s in students}
    assert (await client.post(f"/api/v1/workflows/overseas/agent/commissions/{a['commission'].id}/claim")).status_code == 200


@pytest.mark.asyncio
async def test_linking_a_student_already_linked_by_another_master_is_409(client, world, db_session):  # E12
    second = await _second_master(db_session, world["a"])
    await login(client, second.email)
    response = await client.post("/api/v1/workflows/overseas/agent/students", json={"student_id": str(world["a"]["student"].id)})
    assert response.status_code == 409 and response.json()["detail"] == "Student is already linked to this agency"


@pytest.mark.asyncio
async def test_another_org_may_still_refer_the_same_student(client, world):  # E12, today's behaviour
    await login(client, world["b"]["master"].email)
    response = await client.post("/api/v1/workflows/overseas/agent/students", json={"student_id": str(world["a"]["student"].id)})
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_two_masters_claiming_one_commission_at_once_claim_it_once(world, db_session):  # race: claim
    second = await _second_master(db_session, world["a"])
    url = f"/api/v1/workflows/overseas/agent/commissions/{world['a']['commission'].id}/claim"
    async with client_for(world["a"]["master"].email) as c1, client_for(second.email) as c2:
        results = await asyncio.gather(c1.post(url), c2.post(url))
    assert sorted(r.status_code for r in results) == [200, 409]


@pytest.mark.asyncio
async def test_two_masters_linking_one_student_at_once_link_it_once(world, db_session):  # race: link
    second = await _second_master(db_session, world["a"])
    student = await mk_user(db_session, role="overseas_student")
    body = {"student_id": str(student.id)}
    async with client_for(world["a"]["master"].email) as c1, client_for(second.email) as c2:
        results = await asyncio.gather(c1.post("/api/v1/workflows/overseas/agent/students", json=body), c2.post("/api/v1/workflows/overseas/agent/students", json=body))
    assert sorted(r.status_code for r in results) == [201, 409]
    assert await db_session.scalar(select(func.count()).select_from(AgentStudent).where(AgentStudent.student_id == student.id)) == 1


@pytest.mark.asyncio
async def test_a_super_admin_on_agent_routes_behaves_as_before(client, db_session):  # Review Focus 2
    admin = await mk_user(db_session, role="super_admin", division="global")
    await login(client, admin.email)
    assert (await client.get("/api/v1/workflows/overseas/agent/students")).json() == []
    assert (await client.get("/api/v1/workflows/overseas/agent/commissions")).json() == []
    assert (await client.get("/api/v1/portal/overseas/agent/dashboard")).status_code == 200
