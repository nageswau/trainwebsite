"""ccrm-008 (DEC-SCOPE-252, K1-K6) -- the counselor converts a lead handed to them into an overseas student in one step:
POST /counselor/leads/{id}/convert creates the csc-002 account, links the lead (tel-018) and copies the lead's data into the ccrm-007
profile; the set-password link is mailed after the commit."""

import random
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Enquiry, LeadQualification, OverseasStudentCounselor, OverseasStudentProfile, OverseasStudentQualification, User
from app.services import counselor_students, lead_conversion, provisioning
from tests.tel018_helpers import as_user, c_url, handover, make_counselor, make_student, setup


def _capture(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def capture(channel, payload):
        sent.append(payload)
        return "sent", None

    monkeypatch.setattr(provisioning, "send_notification", capture)
    return sent


def _phone() -> str:
    return f"9{random.randint(100000000, 999999999)}"  # the shared test DB: a fixed mobile would match another test's student


async def _lead(client, db, status="qualified", **over):
    manager, tel, counselor, lead = await setup(db, "overseas", status=status, phone=over.pop("phone", _phone()), **over)
    assert (await handover(client, tel, lead, counselor)).status_code == 200
    await as_user(client, counselor)
    return tel, counselor, lead


def _body(lead, **over) -> dict:
    return {"full_name": lead.name, "email": lead.email, "phone": lead.phone, **over}


async def convert(client, lead, **over):
    return await client.post(c_url(lead.id, "/convert"), json=_body(lead, **over))


async def _fresh(db, model, key):
    return await db.scalar(select(model).where(key).execution_options(populate_existing=True))


@pytest.mark.asyncio
async def test_converting_creates_the_student_links_the_lead_and_copies_its_data(client, db_session, monkeypatch):
    _capture(monkeypatch)
    tel, counselor, lead = await _lead(client, db_session, status="counselling_completed", city="Pune", state="Maharashtra", qualification="B.Tech", institution="COEP", passing_year=2024)
    db_session.add(
        LeadQualification(
            lead_id=lead.id,
            updated_by_user_id=tel.id,
            study_level="masters",
            preferred_course="MS Data Science",
            intake="Fall 2027",
            academic_percentage=Decimal("78.50"),
            work_experience_years=2,
            current_org="Infosys",
            budget_range="20-25 lakh",
        )
    )
    await db_session.commit()
    response = await convert(client, lead)
    assert response.status_code == 201, response.text
    body = response.json()
    student = await _fresh(db_session, User, User.email == lead.email.lower())
    assert (student.role, student.division, student.full_name, student.phone) == ("overseas_student", "overseas", lead.name, lead.phone)
    assert student.profile == {"registration_source": "lead_conversion"}
    assert body["student"]["id"] == str(student.id) and body["student"]["setup"] == "pending_setup"
    assert "development_welcome_token" not in body and body["email_status"] in {"sent", "not_configured", "failed"} and body["expires_at"]
    # tel-018: linked, Application/Enrollment; source / owner / telecaller kept
    assert (body["lead"]["status"], body["lead"]["converted_user"]["id"]) == ("application_enrollment", str(student.id))
    assert body["lead"]["permissions"]["convert"] is False
    row = await _fresh(db_session, Enquiry, Enquiry.id == lead.id)
    assert (row.owner_id, row.telecaller_user_id, row.source, row.converted_by_user_id) == (counselor.id, tel.id, "website", counselor.id)
    # csc-001 link + audits
    assert await db_session.scalar(select(OverseasStudentCounselor.counselor_user_id).where(OverseasStudentCounselor.student_user_id == student.id)) == counselor.id
    actions = set((await db_session.scalars(select(AuditLog.action).where(AuditLog.user_id == counselor.id))).all())
    assert {"counselor.student_create", "lead.convert", "overseas_student_profile.update"} <= actions
    # ccrm-007 profile copy
    profile = await _fresh(db_session, OverseasStudentProfile, OverseasStudentProfile.student_user_id == student.id)
    assert (profile.city, profile.state, profile.preferred_course, profile.preferred_intake, profile.preferred_level) == ("Pune", "Maharashtra", "MS Data Science", "Fall 2027", "PG")
    assert (profile.work_experience_months, profile.work_experience_details) == (24, "Infosys")
    quals = (await db_session.scalars(select(OverseasStudentQualification).where(OverseasStudentQualification.student_user_id == student.id))).all()
    assert [(q.level, q.qualification_name, q.institution, q.year_completed, q.score_type, q.score) for q in quals] == [("other", "B.Tech", "COEP", 2024, "percentage", Decimal("78.50"))]


@pytest.mark.asyncio
async def test_a_lead_with_no_data_to_copy_converts_without_a_profile(client, db_session, monkeypatch):
    _capture(monkeypatch)
    _, _, lead = await _lead(client, db_session)
    response = await convert(client, lead)
    assert response.status_code == 201, response.text
    assert await db_session.scalar(select(OverseasStudentProfile).where(OverseasStudentProfile.student_user_id == uuid.UUID(response.json()["student"]["id"]))) is None


@pytest.mark.asyncio
async def test_a_value_the_profile_refuses_is_dropped_not_the_conversion(client, db_session, monkeypatch):
    """K3: a passing year beyond the profile's range is left on the lead; the rest is copied."""
    _capture(monkeypatch)
    _, _, lead = await _lead(client, db_session, city="Chennai", qualification="Diploma", passing_year=2099)
    response = await convert(client, lead)
    assert response.status_code == 201, response.text
    student_id = uuid.UUID(response.json()["student"]["id"])
    profile = await _fresh(db_session, OverseasStudentProfile, OverseasStudentProfile.student_user_id == student_id)
    assert profile.city == "Chennai"
    quals = (await db_session.scalars(select(OverseasStudentQualification).where(OverseasStudentQualification.student_user_id == student_id))).all()
    assert [(q.qualification_name, q.year_completed) for q in quals] == [("Diploma", None)]


@pytest.mark.asyncio
async def test_a_phone_only_lead_converts_with_the_email_the_counselor_types(client, db_session, monkeypatch):
    """K2."""
    _capture(monkeypatch)
    _, _, lead = await _lead(client, db_session, email=None)
    email = f"typed-{uuid.uuid4().hex[:8]}@example.local"
    response = await convert(client, lead, email=email)
    assert response.status_code == 201, response.text
    assert response.json()["student"]["email"] == email
    assert (await _fresh(db_session, Enquiry, Enquiry.id == lead.id)).email is None  # the lead itself is not changed


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["assigned", "first_call_pending", "contacted"])
async def test_a_lead_before_qualified_is_422_and_creates_nothing(client, db_session, monkeypatch, status):
    """K1."""
    _capture(monkeypatch)
    _, _, lead = await _lead(client, db_session, status=status)
    response = await convert(client, lead)
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "Move the lead to Qualified before converting it"
    assert await db_session.scalar(select(func.count()).select_from(User).where(User.email == lead.email.lower())) == 0
    detail = (await client.get(c_url(lead.id))).json()
    assert (detail["permissions"]["convert"], detail["permissions"]["link"]) == (False, True)


@pytest.mark.asyncio
async def test_a_closed_lead_is_409(client, db_session, monkeypatch):
    _capture(monkeypatch)
    _, _, lead = await _lead(client, db_session)
    lead.status = "lost"
    await db_session.commit()
    response = await convert(client, lead)
    assert response.status_code == 409, response.text


@pytest.mark.asyncio
async def test_converting_twice_is_409_the_second_time(client, db_session, monkeypatch):
    """K5: the second request (serialised by the lead lock) finds the lead linked."""
    _capture(monkeypatch)
    _, _, lead = await _lead(client, db_session)
    assert (await convert(client, lead)).status_code == 201
    second = await convert(client, lead, email=f"again-{uuid.uuid4().hex[:8]}@example.local")
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_an_existing_student_with_the_email_or_mobile_is_409_with_the_link_offer(client, db_session, monkeypatch):
    """K4: no account is created; the counselor links the existing student instead."""
    sent = _capture(monkeypatch)
    phone = _phone()
    existing = await make_student(db_session, "overseas", phone=f"+91 {phone[:5]} {phone[5:]}")
    _, _, lead = await _lead(client, db_session, phone=phone)
    by_phone = await convert(client, lead)
    by_email = await convert(client, lead, email=existing.email.upper(), phone=None)
    for response in (by_phone, by_email):
        assert response.status_code == 409, response.text
        assert response.json()["detail"] == lead_conversion.STUDENT_EXISTS
    assert sent == [] and await db_session.scalar(select(func.count()).select_from(User).where(User.email == lead.email.lower())) == 0
    assert (await _fresh(db_session, Enquiry, Enquiry.id == lead.id)).converted_user_id is None


@pytest.mark.asyncio
async def test_another_staff_users_email_is_csc_002s_audited_409(client, db_session, monkeypatch):
    _capture(monkeypatch)
    other = await make_counselor(db_session, "overseas")
    _, counselor, lead = await _lead(client, db_session)
    response = await convert(client, lead, email=other.email)
    assert (response.status_code, response.json()["detail"]) == (409, "Email already exists")
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.user_id == counselor.id, AuditLog.action == "counselor.student_create_rejected"))
    assert (await _fresh(db_session, Enquiry, Enquiry.id == lead.id)).converted_user_id is None


@pytest.mark.asyncio
async def test_another_counselors_lead_is_404(client, db_session, monkeypatch):
    _capture(monkeypatch)
    _, _, lead = await _lead(client, db_session)
    await as_user(client, await make_counselor(db_session, "overseas"))
    assert (await convert(client, lead)).status_code == 404


@pytest.mark.asyncio
async def test_an_it_counselor_and_a_telecaller_are_403(client, db_session, monkeypatch):
    _capture(monkeypatch)
    manager, tel, counselor, lead = await setup(db_session, "it", status="qualified", phone=_phone())
    assert (await handover(client, tel, lead, counselor)).status_code == 200
    await as_user(client, counselor)
    refused = await convert(client, lead)  # W1: an IT counselor works leads only
    assert (refused.status_code, refused.json()["detail"]) == (403, lead_conversion.COUNSELOR_ONLY)  # QA-01: not csc-002's walk-in wording
    assert (await client.get(c_url(lead.id))).json()["permissions"]["convert"] is False
    await as_user(client, tel)
    assert (await convert(client, lead)).status_code == 403


@pytest.mark.asyncio
async def test_extra_fields_are_refused(client, db_session, monkeypatch):
    """csc-002's privilege guard: role, division and account flags are server-set."""
    _capture(monkeypatch)
    _, _, lead = await _lead(client, db_session)
    assert (await convert(client, lead, role="overseas_admin")).status_code == 422


@pytest.mark.asyncio
async def test_the_csc_002_mail_budget_applies(client, db_session, monkeypatch):
    _capture(monkeypatch)
    monkeypatch.setattr(counselor_students, "MAIL_LIMIT", 1)
    _, counselor, lead = await _lead(client, db_session)
    db_session.add(AuditLog(user_id=counselor.id, action="counselor.student_create", entity_type="user", entity_id=str(counselor.id), outcome="created"))
    await db_session.commit()
    response = await convert(client, lead)
    assert response.status_code == 429, response.text
    assert (await _fresh(db_session, Enquiry, Enquiry.id == lead.id)).converted_user_id is None
