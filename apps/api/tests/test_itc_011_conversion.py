"""itc-011 -- the one-step IT conversion: POST /counselor/leads/{id}/convert-it (and the IT Admin's /admin/leads/{id}/convert-it) makes the
IT student, the enrolment, the fee rows and the onboarding checklist in one transaction; a retry with the same Idempotency-Key creates
nothing; any failure rolls everything back. GET .../convert-it is the dialog's prefill; /it/enrollments/{id}/onboarding the checklist."""

import datetime
import random
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import (
    AuditLog,
    Batch,
    Enquiry,
    Enrollment,
    ItConversion,
    ItOnboardingItem,
    ItOnboardingTemplateItem,
    ItStudentCounselor,
    LeadCounselingRecord,
    Payment,
    Program,
    TelProduct,
    User,
)
from app.services import it_conversion, provisioning
from tests.tel004_helpers import make_user
from tests.tel018_helpers import as_user, c_url, handover, make_student, setup

TODAY = datetime.date.today()


def _phone() -> str:
    return f"9{random.randint(100000000, 999999999)}"  # the shared test DB: a fixed mobile would match another test's student


def _capture(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def capture(channel, payload):
        sent.append(payload)
        return "sent", None

    monkeypatch.setattr(provisioning, "send_notification", capture)
    return sent


async def _batch(db, *, capacity: int = 20, fees: int = 45000, open_: bool = True, status: str = "upcoming") -> Batch:
    tag = uuid.uuid4().hex[:8]
    program = Program(slug=f"i011-{tag}", category="Software Development", title=f"I011 Course {tag}", summary="", duration="3 months", eligibility="",
                      fees=fees, certification="", curriculum=[], placement_assistance="", trainer_name="T", active=True)  # fmt: skip
    db.add(program)
    await db.flush()
    batch = Batch(program_id=program.id, name=f"PY-{tag}", start_date=TODAY + datetime.timedelta(days=10), end_date=TODAY + datetime.timedelta(days=100),
                  schedule="Mon-Fri", capacity=capacity, enrollment_open=open_, status=status)  # fmt: skip
    db.add(batch)
    await db.commit()
    return batch


async def _lead(client, db, status: str = "qualified", **over):
    manager, tel, counselor, lead = await setup(db, "it", status=status, phone=over.pop("phone", _phone()), **over)
    assert (await handover(client, tel, lead, counselor)).status_code == 200
    await as_user(client, counselor)
    return counselor, lead


def _body(lead, batch, **over) -> dict:
    return {"student": {"full_name": lead.name, "email": lead.email, "phone": lead.phone}, "batch_id": str(batch.id), "fee": "45000"} | over


async def _convert(client, url, body, key: str | None = None):
    headers = {"Idempotency-Key": key or uuid.uuid4().hex}
    return await client.post(url, json=body, headers=headers)


async def _count(db, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where))


async def _student(db, email: str) -> User | None:
    return await db.scalar(select(User).where(func.lower(User.email) == email.lower()).execution_options(populate_existing=True))


@pytest.mark.asyncio
async def test_one_request_makes_the_student_enrolment_fee_and_checklist(client, db_session, monkeypatch):
    sent = _capture(monkeypatch)
    counselor, lead = await _lead(client, db_session)
    batch = await _batch(db_session)
    response = await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, batch))
    assert response.status_code == 201, response.text
    body = response.json()
    student = await _student(db_session, lead.email)
    assert (student.role, student.division, student.full_name, student.phone) == ("it_student", "it", lead.name, lead.phone)
    assert student.profile == {"registration_source": "lead_conversion"} and student.student_code
    assert body["student"]["id"] == str(student.id) and body["student"]["setup"] == "pending_setup"
    assert "development_welcome_token" not in body and body["email_status"] in {"sent", "not_configured", "failed"}
    assert len(sent) == 1  # the welcome link, after the commit
    enrollment = await db_session.scalar(select(Enrollment).where(Enrollment.student_id == student.id))
    assert (enrollment.batch_id, enrollment.status, enrollment.slot_locked) == (batch.id, "pending_consent", True)  # C2: consent kept
    assert body["enrollment"]["id"] == str(enrollment.id) and body["enrollment"]["batch"] == batch.name
    fees = (await db_session.scalars(select(Payment).where(Payment.reference_id == enrollment.id))).all()
    assert [(float(p.amount), p.status, p.reference_type, p.division) for p in fees] == [(45000.0, "pending", "enrollment_fee", "it")]
    assert body["fee_account"]["total_payable"] == 45000.0 and body["fee_account"]["balance"] == 45000.0
    labels = list(await db_session.scalars(select(ItOnboardingTemplateItem.label).where(ItOnboardingTemplateItem.active.is_(True)).order_by(ItOnboardingTemplateItem.position)))
    assert labels and [i["label"] for i in body["checklist"]] == labels and not any(i["done"] for i in body["checklist"])
    # tel-018 link + itc-003 counselor; the lead waits at Application/Enrollment until the student consents (C2)
    assert (body["lead"]["status"], body["lead"]["converted_user"]["id"]) == ("application_enrollment", str(student.id))
    assert body["lead"]["permissions"]["convert_it"] is False and body["lead"]["it_conversion"] == {"enrollment_id": str(enrollment.id)}
    link = await db_session.scalar(select(ItStudentCounselor).where(ItStudentCounselor.student_user_id == student.id))
    assert link.counselor_user_id == counselor.id
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == it_conversion.CONVERTED, AuditLog.entity_id == str(lead.id)))
    assert audit.metadata_json["enrollment_id"] == str(enrollment.id) and lead.email not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_the_lead_converts_once_the_student_accepts_the_agreement(client, db_session, monkeypatch):
    """AC2: the lead stays linked to the student; tel-018's sync moves it to Converted once the enrolment is active."""
    _capture(monkeypatch)
    counselor, lead = await _lead(client, db_session)
    batch = await _batch(db_session)
    assert (await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, batch))).status_code == 201
    student = await _student(db_session, lead.email)
    enrollment = await db_session.scalar(select(Enrollment).where(Enrollment.student_id == student.id))
    enrollment.status = "active"  # what accepting the agreement does
    await db_session.commit()
    detail = (await client.get(c_url(lead.id))).json()
    assert detail["status"] == "converted" and detail["converted_user"]["id"] == str(student.id)
    assert detail["milestones"]["items"][0]["reference"] == enrollment.enrollment_code


@pytest.mark.asyncio
async def test_a_retry_with_the_same_key_creates_nothing(client, db_session, monkeypatch):
    sent = _capture(monkeypatch)
    _, lead = await _lead(client, db_session)
    batch = await _batch(db_session)
    url, key = c_url(lead.id, "/convert-it"), uuid.uuid4().hex
    first = await _convert(client, url, _body(lead, batch), key)
    assert first.status_code == 201, first.text
    again = await _convert(client, url, _body(lead, batch), key)
    assert again.status_code == 200, again.text
    assert again.json()["replayed"] is True and again.json()["enrollment"] == first.json()["enrollment"]
    student = await _student(db_session, lead.email)
    assert await _count(db_session, Enrollment, Enrollment.student_id == student.id) == 1
    assert await _count(db_session, Payment, Payment.user_id == student.id) == 1
    assert await _count(db_session, ItConversion, ItConversion.lead_id == lead.id) == 1
    assert len(sent) == 1  # no second welcome mail
    other = await _convert(client, url, _body(lead, batch))  # another key on a converted lead
    assert other.status_code == 409


@pytest.mark.asyncio
async def test_any_failure_rolls_everything_back(client, db_session, monkeypatch):
    _capture(monkeypatch)
    _, lead = await _lead(client, db_session)
    batch = await _batch(db_session)

    async def broken(db, enrollment):
        raise RuntimeError("checklist store down")

    monkeypatch.setattr(it_conversion, "_checklist", broken)
    with pytest.raises(RuntimeError):
        await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, batch))
    assert await _student(db_session, lead.email) is None
    assert await _count(db_session, Enrollment, Enrollment.batch_id == batch.id) == 0
    row = await db_session.scalar(select(Enquiry).where(Enquiry.id == lead.id).execution_options(populate_existing=True))
    assert (row.status, row.converted_user_id) == ("qualified", None)


@pytest.mark.asyncio
async def test_a_full_or_closed_batch_is_409_and_creates_nothing(client, db_session, monkeypatch):
    _capture(monkeypatch)
    _, lead = await _lead(client, db_session)
    full = await _batch(db_session, capacity=1)
    db_session.add(Enrollment(student_id=(await make_student(db_session)).id, batch_id=full.id, enrollment_code=f"EDU-I011-{uuid.uuid4().hex[:8]}", status="active"))
    await db_session.commit()
    closed = await _batch(db_session, open_=False)
    for batch, message in ((full, "This batch is full"), (closed, "Enrollment is closed for this batch")):
        response = await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, batch))
        assert (response.status_code, response.json()["detail"]) == (409, message)
    assert await _student(db_session, lead.email) is None
    missing = await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, full, batch_id=str(uuid.uuid4())))
    assert missing.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["new", "contacted", "application_enrollment", "lost"])
async def test_a_lead_outside_the_convertible_stages_is_409(client, db_session, monkeypatch, status):
    _capture(monkeypatch)
    _, lead = await _lead(client, db_session)
    lead.status = status
    if status == "lost":
        lead.lost_reason = "Other"
    await db_session.commit()
    response = await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, await _batch(db_session)))
    assert response.status_code == 409, response.text
    assert await _student(db_session, lead.email) is None


@pytest.mark.asyncio
async def test_only_the_owner_it_counselor_may_convert(client, db_session, monkeypatch):
    _capture(monkeypatch)
    _, lead = await _lead(client, db_session)
    batch = await _batch(db_session)
    other = await make_user(db_session, "counselor", "it")
    await as_user(client, other)
    assert (await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, batch))).status_code == 404
    assert (await client.get(c_url(lead.id, "/convert-it"))).status_code == 404
    await as_user(client, await make_user(db_session, "counselor", "overseas"))
    assert (await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, batch))).status_code in {403, 404}
    await as_user(client, await make_user(db_session, "telecaller", "it"))
    assert (await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, batch))).status_code == 403


@pytest.mark.asyncio
async def test_an_overseas_counselor_gets_403_on_their_own_overseas_lead(client, db_session, monkeypatch):
    _capture(monkeypatch)
    manager, tel, counselor, lead = await setup(db_session, "overseas", status="qualified", phone=_phone())
    assert (await handover(client, tel, lead, counselor)).status_code == 200
    await as_user(client, counselor)
    response = await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, await _batch(db_session)))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_key_is_required_and_checked(client, db_session):
    _, lead = await _lead(client, db_session)
    batch = await _batch(db_session)
    assert (await client.post(c_url(lead.id, "/convert-it"), json=_body(lead, batch))).status_code == 422
    assert (await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, batch), "bad key!")).status_code == 422


@pytest.mark.asyncio
async def test_an_existing_it_student_is_offered_then_linked_without_a_mail(client, db_session, monkeypatch):
    sent = _capture(monkeypatch)
    phone = _phone()
    existing = await make_student(db_session, phone=phone)
    _, lead = await _lead(client, db_session, phone=phone)
    batch = await _batch(db_session)
    clash = await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, batch))
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "student_exists"
    body = _body(lead, batch, student_id=str(existing.id))
    body.pop("student")
    response = await _convert(client, c_url(lead.id, "/convert-it"), body)
    assert response.status_code == 201, response.text
    assert response.json()["student"]["id"] == str(existing.id) and "email_status" not in response.json()
    assert await _count(db_session, Enrollment, Enrollment.student_id == existing.id, Enrollment.batch_id == batch.id) == 1
    assert sent == []


@pytest.mark.asyncio
async def test_an_email_of_another_account_is_refused_without_naming_it(client, db_session, monkeypatch):
    _capture(monkeypatch)
    overseas = await make_student(db_session, "overseas")
    _, lead = await _lead(client, db_session)
    body = _body(lead, await _batch(db_session))
    body["student"]["email"] = overseas.email  # typed in the dialog
    response = await _convert(client, c_url(lead.id, "/convert-it"), body)
    assert (response.status_code, response.json()["detail"]) == (409, it_conversion.EMAIL_TAKEN)
    assert overseas.full_name not in response.text


@pytest.mark.asyncio
async def test_both_or_neither_student_is_422(client, db_session):
    _, lead = await _lead(client, db_session)
    batch = await _batch(db_session)
    both = _body(lead, batch, student_id=str(uuid.uuid4()))
    neither = _body(lead, batch)
    neither.pop("student")
    for body in (both, neither):
        assert (await _convert(client, c_url(lead.id, "/convert-it"), body)).status_code == 422


@pytest.mark.asyncio
async def test_installments_make_one_fee_row_each(client, db_session, monkeypatch):
    _capture(monkeypatch)
    _, lead = await _lead(client, db_session)
    batch = await _batch(db_session)
    plan = [{"amount": "20000", "due_date": TODAY.isoformat()}, {"amount": "25000", "due_date": (TODAY + datetime.timedelta(days=30)).isoformat()}]
    response = await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, batch, installments=plan))
    assert response.status_code == 201, response.text
    enrollment_id = uuid.UUID(response.json()["enrollment"]["id"])
    rows = (await db_session.scalars(select(Payment).where(Payment.reference_id == enrollment_id).order_by(Payment.installment_no))).all()
    assert [(p.installment_no, float(p.amount), p.due_date) for p in rows] == [(1, 20000.0, TODAY), (2, 25000.0, TODAY + datetime.timedelta(days=30))]
    assert [i["amount"] for i in response.json()["fee_account"]["installments"]] == [20000.0, 25000.0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fee", "plan", "message"),
    [
        ("45000", [{"amount": "20000", "due_date": TODAY.isoformat()}], it_conversion.SUM_MISMATCH),
        ("0", [{"amount": "1", "due_date": TODAY.isoformat()}], it_conversion.NO_FEE_PLAN),
        ("100", [{"amount": "100", "due_date": (TODAY - datetime.timedelta(days=2)).isoformat()}], it_conversion.DUE_PAST),
    ],
)
async def test_a_bad_fee_plan_is_422_and_creates_nothing(client, db_session, fee, plan, message):
    _, lead = await _lead(client, db_session)
    response = await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, await _batch(db_session), fee=fee, installments=plan))
    assert response.status_code == 422 and message in response.text
    assert await _student(db_session, lead.email) is None


@pytest.mark.asyncio
async def test_a_scholarship_fee_of_zero_bills_nothing(client, db_session, monkeypatch):
    _capture(monkeypatch)
    _, lead = await _lead(client, db_session)
    response = await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, await _batch(db_session), fee="0"))
    assert response.status_code == 201, response.text
    assert response.json()["fee_account"]["state"] == "not_billed"
    assert await _count(db_session, Payment, Payment.reference_id == uuid.UUID(response.json()["enrollment"]["id"])) == 0


@pytest.mark.asyncio
async def test_the_dialog_prefill_uses_the_counseling_fee_and_recommended_course(client, db_session):
    counselor, lead = await _lead(client, db_session)
    recommended, other = await _batch(db_session), await _batch(db_session)
    full = await _batch(db_session, capacity=0)
    course = TelProduct(product_group="it", name=f"Course {uuid.uuid4().hex[:6]}", team="it", program_id=recommended.program_id, active=True)
    db_session.add(course)
    await db_session.flush()
    db_session.add(LeadCounselingRecord(lead_id=lead.id, author_user_id=counselor.id, updated_by_user_id=counselor.id, recommended_product_id=course.id,
                                        fee_quoted=Decimal("42000.00"), outcome="interested"))  # fmt: skip
    await db_session.commit()
    response = await client.get(c_url(lead.id, "/convert-it"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["prefill"]["fee"] == 42000.0 and body["prefill"]["email"] == lead.email
    assert body["prefill"]["recommended_program_id"] == str(recommended.program_id)
    ids = [b["id"] for b in body["batches"]]
    assert ids[0] == str(recommended.id) and body["batches"][0]["recommended"] is True
    assert str(other.id) in ids and str(full.id) not in ids
    assert body["checklist"] and all(isinstance(label, str) for label in body["checklist"])


@pytest.mark.asyncio
async def test_the_it_admin_converts_an_it_lead(client, db_session, monkeypatch):
    _capture(monkeypatch)
    _, lead = await _lead(client, db_session)
    batch = await _batch(db_session)
    admin = await make_user(db_session, "it_admin", "it")
    await as_user(client, admin)
    url = f"/api/v1/admin/leads/{lead.id}/convert-it"
    assert (await client.get(url)).status_code == 200
    response = await _convert(client, url, _body(lead, batch))
    assert response.status_code == 201, response.text
    assert response.json()["lead"]["status"] == "application_enrollment"
    await as_user(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert (await client.get(url)).status_code == 403


@pytest.mark.asyncio
async def test_the_checklist_is_read_and_ticked_by_the_right_people(client, db_session, monkeypatch):
    _capture(monkeypatch)
    counselor, lead = await _lead(client, db_session)
    response = await _convert(client, c_url(lead.id, "/convert-it"), _body(lead, await _batch(db_session)))
    enrollment_id, item = response.json()["enrollment"]["id"], response.json()["checklist"][0]["id"]
    url = f"/api/v1/it/enrollments/{enrollment_id}/onboarding"
    ticked = await client.patch(f"{url}/{item}", json={"done": True})
    assert ticked.status_code == 200 and ticked.json()["items"][0]["done"] is True
    row = await db_session.scalar(select(ItOnboardingItem).where(ItOnboardingItem.id == uuid.UUID(item)).execution_options(populate_existing=True))
    assert row.done_by_user_id == counselor.id and row.done_at is not None
    assert (await client.patch(f"{url}/{uuid.uuid4()}", json={"done": True})).status_code == 404
    await as_user(client, await make_user(db_session, "counselor", "it"))  # not the student's counselor
    assert (await client.get(url)).status_code == 404
    await as_user(client, await make_user(db_session, "it_student", "it"))  # another student
    assert (await client.get(url)).status_code == 404
    await as_user(client, await make_user(db_session, "trainer", "it"))
    assert (await client.get(url)).status_code == 403
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    undone = await client.patch(f"{url}/{item}", json={"done": False})
    assert undone.status_code == 200 and undone.json()["items"][0]["done"] is False
