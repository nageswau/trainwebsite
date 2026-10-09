"""bdm-021 -- a College organization's student funnel and revenue (spec §2-§4; AC1-AC4, B1-B8)."""

import uuid
from datetime import UTC, date, datetime

import pytest

from app.models import Batch, Certificate, Company, Enquiry, Enrollment, Job, JobOffer, Payment, Program, User
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm009_helpers import bdm_with_org
from tests.bdm017_helpers import as_user, student_email
from tests.rec017_helpers import student_application


def business(org_id) -> str:
    return f"/api/v1/bdm/organizations/{org_id}/business"


async def lead(db, org_id, bdm_id, student: User | None = None) -> Enquiry:
    row = Enquiry(
        division="it",
        name="Lead",
        email=student_email(),
        subject="Python",
        message="Lead entered by BDM",
        source="bdm",
        status="new",
        crm_sync_status="pending",
        metadata_json={},
        bdm_organization_id=org_id,
        bdm_user_id=bdm_id,
        converted_user_id=student.id if student else None,
        converted_at=datetime.now(UTC) if student else None,
        converted_by_user_id=bdm_id if student else None,
    )  # ck_enquiries_conversion: the three are set together
    db.add(row)
    await db.commit()
    return row


async def batch(db) -> Batch:
    unique = uuid.uuid4().hex[:8]
    program = Program(
        slug=f"bdm021-{unique}",
        category="Test",
        title=f"bdm-021 {unique}",
        summary="",
        duration="3 months",
        eligibility="",
        fees=1000,
        certification="",
        curriculum=[],
        placement_assistance="",
        trainer_name="Trainer",
    )
    db.add(program)
    await db.flush()
    row = Batch(program_id=program.id, name=f"Batch {unique}", schedule="Mon-Fri", capacity=20, status="active", start_date=date(2026, 1, 1), end_date=date(2026, 4, 1))
    db.add(row)
    await db.commit()
    return row


async def enroll(db, student: User, status: str) -> None:
    b = await batch(db)
    db.add(Enrollment(student_id=student.id, batch_id=b.id, enrollment_code=f"B021-{uuid.uuid4().hex[:10]}", status=status))
    await db.commit()


async def certify(db, student: User, status: str) -> None:
    b = await batch(db)
    code = uuid.uuid4().hex
    db.add(Certificate(student_id=student.id, program_id=b.program_id, certificate_no=f"C-{code[:12]}", verification_code=f"V-{code}", issued_on=date(2026, 5, 1), status=status))
    await db.commit()


async def offer(db, student: User, status: str) -> None:
    company = Company(name=f"bdm-021 Co {uuid.uuid4().hex[:8]}", partner_type="recruiter")
    db.add(company)
    await db.flush()
    job = Job(company_id=company.id, title="Engineer", location="Remote", description="", skills=[], status="requirement_received")
    db.add(job)
    await db.flush()
    application = await student_application(db, job.id, student, "sourced")
    db.add(application)
    await db.flush()
    db.add(JobOffer(application_id=application.id, status=status))
    await db.commit()


async def pay(db, student: User, amount: str, status: str = "paid", currency: str = "INR", reference_type: str = "enrollment") -> None:
    db.add(Payment(user_id=student.id, division="it", reference_type=reference_type, amount=amount, currency=currency, status=status))
    await db.commit()


async def student(db) -> User:
    return await make_user(db, "it_student", "it")


def by_key(items: list[dict]) -> dict[str, dict]:
    return {item["key"]: item for item in items}


async def seeded(client, db):
    """Six leads of one College organization (five linked), one linked lead of another organization. Leaves the client as the BDM."""
    manager, bdm, org = await bdm_with_org(client, db, "college")
    s1, s2, s3, s4, s5, outsider = [await student(db) for _ in range(6)]
    for s in (s1, s2, s3, s4, s5, None):
        await lead(db, org["id"], bdm.id, s)
    other = await create_org(client, org_type="college")
    await lead(db, other["id"], bdm.id, outsider)

    await enroll(db, s1, "active")
    await enroll(db, s2, "withdrawn")
    await enroll(db, s3, "pending_consent")
    await enroll(db, s3, "active")  # two enrollments, one student
    await enroll(db, outsider, "active")
    await certify(db, s1, "issued")
    await certify(db, s2, "revoked")
    await certify(db, s4, "issued")  # a certificate without an enrollment still counts (B6)
    await certify(db, outsider, "issued")
    await offer(db, s1, "accepted")
    await offer(db, s2, "offer_received")  # rec-022: the legacy "offered" is now Offer Received
    await offer(db, s3, "accepted")  # rec-022: a legacy "joined" offer is mapped to Accepted (0136)
    await offer(db, outsider, "accepted")

    await pay(db, s1, "1000.00")
    await pay(db, s1, "500.50", status="succeeded")
    await pay(db, s2, "999.00", status="pending")
    await pay(db, s3, "700.00", status="refunded")
    await pay(db, s3, "100.00", currency="USD")
    await pay(db, s4, "300.00", reference_type="agent_deposit")
    await pay(db, s5, "250.00")
    await pay(db, outsider, "5000.00")
    return manager, bdm, org


# --- AC1-AC4 ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_funnel_counts_match_the_written_definitions(client, db_session):
    _, _, org = await seeded(client, db_session)
    response = await client.get(business(org["id"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert [s["key"] for s in body["funnel"]] == ["contacted", "leads", "registrations", "training", "certification", "internship", "placement"]
    counts = {s["key"]: s["count"] for s in body["funnel"]}
    assert counts == {"contacted": 6, "leads": 6, "registrations": 5, "training": 2, "certification": 2, "internship": None, "placement": 2}
    assert all(s["definition"] for s in body["funnel"])


@pytest.mark.asyncio
async def test_only_paid_inr_fees_of_registered_students_are_revenue(client, db_session):
    _, _, org = await seeded(client, db_session)
    body = (await client.get(business(org["id"]))).json()
    assert body["currency"] == "INR"
    lines = by_key(body["revenue"]["lines"])
    assert list(lines) == ["training", "internship", "placement", "other"]
    assert lines["training"]["tracked"] is True
    assert lines["training"]["amount"] == "1750.50"  # 1000 paid + 500.50 succeeded + 250 paid; pending, refunded, USD, deposit excluded


@pytest.mark.asyncio
async def test_untracked_stages_and_lines_are_labelled_not_zero(client, db_session):
    _, _, org = await seeded(client, db_session)
    body = (await client.get(business(org["id"]))).json()
    internship = by_key(body["funnel"])["internship"]
    assert (internship["tracked"], internship["count"]) == (False, None)
    assert not internship["definition"].startswith("Not tracked")  # QA21-01: the panel's badge says it; the note says why
    for key in ("internship", "placement", "other"):
        line = by_key(body["revenue"]["lines"])[key]
        assert (line["tracked"], line["amount"]) == (False, None)
        assert line["definition"] and not line["definition"].startswith("Not tracked")


@pytest.mark.asyncio
async def test_no_per_student_data_is_exposed(client, db_session):
    _, _, org = await seeded(client, db_session)
    body = (await client.get(business(org["id"]))).json()
    assert set(body) == {"organization_id", "currency", "funnel", "revenue"}
    assert body["organization_id"] == org["id"]
    assert all(set(s) == {"key", "label", "definition", "tracked", "count"} for s in body["funnel"])
    assert set(body["revenue"]) == {"lines"}
    assert all(set(line) == {"key", "label", "definition", "tracked", "amount"} for line in body["revenue"]["lines"])


@pytest.mark.asyncio
async def test_an_organization_without_leads_reads_real_zeros(client, db_session):
    _, _, org = await bdm_with_org(client, db_session, "college")
    body = (await client.get(business(org["id"]))).json()
    counts = {s["key"]: s["count"] for s in body["funnel"]}
    assert counts == {"contacted": 0, "leads": 0, "registrations": 0, "training": 0, "certification": 0, "internship": None, "placement": 0}
    assert by_key(body["revenue"]["lines"])["training"]["amount"] == "0.00"


@pytest.mark.asyncio
async def test_unlinking_a_lead_removes_its_student_on_the_next_read(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session, "college")
    s = await student(db_session)
    row = await lead(db_session, org["id"], bdm.id, s)
    await enroll(db_session, s, "active")
    await pay(db_session, s, "400.00")
    assert by_key((await client.get(business(org["id"]))).json()["funnel"])["training"]["count"] == 1
    row.converted_user_id = row.converted_at = row.converted_by_user_id = None
    await db_session.commit()
    body = (await client.get(business(org["id"]))).json()
    assert {s["key"]: s["count"] for s in body["funnel"]}["registrations"] == 0
    assert by_key(body["revenue"]["lines"])["training"]["amount"] == "0.00"


# --- who sees what (B1-B3) ----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_manager_and_super_admin_see_revenue(client, db_session):
    manager, _, org = await seeded(client, db_session)
    for viewer in (manager, await make_user(db_session, "super_admin", "global")):
        await as_user(client, viewer)
        body = (await client.get(business(org["id"]))).json()
        assert by_key(body["revenue"]["lines"])["training"]["amount"] == "1750.50"


@pytest.mark.asyncio
async def test_another_college_bdm_sees_the_funnel_but_not_revenue(client, db_session):
    _, _, org = await seeded(client, db_session)
    await as_user(client, await make_bdm(db_session, await make_manager(db_session), "college"))
    response = await client.get(business(org["id"]))
    assert response.status_code == 200
    body = response.json()
    assert body["revenue"] is None
    assert {s["key"]: s["count"] for s in body["funnel"]}["registrations"] == 5


@pytest.mark.asyncio
async def test_a_school_bdm_gets_404_for_a_college_organization(client, db_session):
    _, _, org = await bdm_with_org(client, db_session, "college")
    await as_user(client, await make_bdm(db_session, await make_manager(db_session), "school"))
    response = await client.get(business(org["id"]))
    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found"


@pytest.mark.asyncio
async def test_a_non_college_organization_has_no_business_view(client, db_session):
    _, _, org = await bdm_with_org(client, db_session, "school")
    own = await client.get(business(org["id"]))
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    admin = await client.get(business(org["id"]))
    assert (own.status_code, admin.status_code) == (404, 404)
    assert own.json()["detail"] == admin.json()["detail"] == "Organization not found"


@pytest.mark.asyncio
async def test_an_unknown_organization_is_404_and_a_bad_id_422(client, db_session):
    await bdm_with_org(client, db_session, "college")
    assert (await client.get(business(uuid.uuid4()))).status_code == 404
    assert (await client.get(business("not-a-uuid"))).status_code == 422


@pytest.mark.asyncio
async def test_other_roles_are_refused_and_anonymous_is_401(client, db_session):
    _, _, org = await bdm_with_org(client, db_session, "college")
    client.cookies.clear()
    assert (await client.get(business(org["id"]))).status_code == 401
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(business(org["id"]))).status_code == 403
