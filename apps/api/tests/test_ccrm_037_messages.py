"""ccrm-037 (DEC-SCOPE-273, MT1-MT10) -- the Overseas Admin's message templates for counselors and the student message log:
/counselor/templates (library, preview) and /counselor/students/{id}/messages|replies (render, send, record a reply, list). The overseas
counselor sends to the students in csc-001 scope, optionally about one of their own applications; the Overseas Admin manages templates and
reads every log; the student, the agent and other roles never see it."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.config import settings
from app.models import AuditLog, OverseasStudentCounselor, StudentMessage
from app.services import counselor_messages
from tests.agn001_helpers import login, mk_user, uniq
from tests.enh031_helpers import mk_application, mk_course, mk_university

TEMPLATES = "/api/v1/counselor/templates"


def url(student_id, tail: str = "messages") -> str:
    return f"/api/v1/counselor/students/{student_id}/{tail}"


@pytest.fixture
def smtp_on(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.local")


@pytest_asyncio.fixture
async def world(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name="Nora Counselor")
    other = await mk_user(db_session, role="counselor", full_name="Omar Counselor")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Ada Admin")
    student = await mk_user(db_session, role="overseas_student", full_name="Priya Student")
    student.phone = "98765 43210"
    university = await mk_university(db_session, name=uniq("Leeds"))
    course = await mk_course(db_session, university, "MSc Data Science")
    own = await mk_application(db_session, student=student, university=university, counselor=counselor, course=course, reference="REF-37")
    own.application_deadline, own.offer_deadline = date(2026, 9, 14), date(2026, 12, 1)
    foreign = await mk_application(db_session, student=student, university=await mk_university(db_session), counselor=other)
    await db_session.commit()
    return {"counselor": counselor, "other": other, "admin": admin, "student": student, "university": university, "own": own, "foreign": foreign}


async def mk_template(client, admin, *, channel="whatsapp", body="Hi {name}, about {university}: {course} ({intake}), apply by {application_deadline}. {counselor}", subject=None) -> dict:
    await login(client, admin.email)
    payload = {"channel": channel, "name": uniq("Tpl"), "body": body, **({"subject": subject or "About {university}"} if channel == "email" else {})}
    response = await client.post(TEMPLATES, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --- the template library (MT1, MT2) -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_overseas_admin_manages_templates_and_the_counselor_reads_active_ones(client, db_session, world):
    template = await mk_template(client, world["admin"])
    assert template["active"] is True and template["subject"] is None
    hidden = await mk_template(client, world["admin"], body="Old text")
    response = await client.patch(f"{TEMPLATES}/{hidden['id']}", json={"active": False})
    assert response.status_code == 200 and response.json()["active"] is False
    assert {t["id"] for t in (await client.get(TEMPLATES, params={"limit": 50, "q": "Tpl"})).json()["items"]} >= {template["id"], hidden["id"]}

    await login(client, world["counselor"].email)
    ids = {t["id"] for t in (await client.get(TEMPLATES, params={"limit": 50, "active": "false"})).json()["items"]}
    assert hidden["id"] not in ids  # the counselor never sees an inactive template, whatever they ask
    assert (await client.get(f"{TEMPLATES}/{hidden['id']}/preview")).status_code == 404
    assert (await client.post(TEMPLATES, json={"channel": "whatsapp", "name": uniq("X"), "body": "Hi"})).status_code == 403
    assert (await client.patch(f"{TEMPLATES}/{template['id']}", json={"active": False})).status_code == 403
    assert (await client.get(f"{TEMPLATES}/{template['id']}/preview")).json()["body"].startswith("Hi Priya Sharma, about University of Example")
    actions = set(await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id.in_([template["id"], hidden["id"]]))))
    assert actions == {"counselor_template.create", "counselor_template.update"}


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("telecaller", "overseas"), ("counselor", "it"), ("agent", "overseas"), ("overseas_student", "overseas"), ("partnership_head", "overseas")])
async def test_other_roles_cannot_read_or_write_templates(client, db_session, role, division):
    user = await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division=division)
    assert (await client.get(TEMPLATES)).status_code == 403
    assert (await client.post(TEMPLATES, json={"channel": "whatsapp", "name": uniq("X"), "body": "Hi"})).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client, world):
    assert (await client.get(TEMPLATES)).status_code == 401
    assert (await client.get(url(world["student"].id))).status_code == 401


@pytest.mark.asyncio
async def test_super_admin_writes_templates(client, db_session):
    root = await mk_user(db_session, role="super_admin", division="it")
    await login(client, root.email, division="it")
    assert (await client.post(TEMPLATES, json={"channel": "email", "name": uniq("Root"), "subject": "Hello {name}", "body": "Hi"})).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,detail",
    [
        ({"channel": "whatsapp", "body": "Hi {student}"}, "Unknown placeholder {student}. Use {name}, {university}, {course}, {intake}, {application_deadline}, {offer_deadline} or {counselor}"),
        ({"channel": "whatsapp", "body": "Hi", "subject": "S"}, "Only email templates have a subject"),
        ({"channel": "email", "body": "Hi"}, "Subject is required"),
        ({"channel": "whatsapp", "body": "x" * 1001}, "A WhatsApp message must be at most 1000 characters"),
    ],
)
async def test_template_rules_are_422(client, world, payload, detail):
    await login(client, world["admin"].email)
    response = await client.post(TEMPLATES, json={"name": uniq("Bad"), **payload})
    assert response.status_code == 422 and response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_a_template_name_is_unique_per_channel_and_the_channel_is_fixed(client, world):
    template = await mk_template(client, world["admin"])
    response = await client.post(TEMPLATES, json={"channel": "whatsapp", "name": template["name"].upper(), "body": "Hi"})
    assert response.status_code == 409 and template["name"].upper() in response.json()["detail"]
    assert (await client.post(TEMPLATES, json={"channel": "email", "name": template["name"], "subject": "S", "body": "Hi"})).status_code == 201
    response = await client.patch(f"{TEMPLATES}/{template['id']}", json={"channel": "email"})
    assert response.status_code == 422 and response.json()["detail"] == "Channel cannot be changed"


# --- render (MT2, MT4) --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_render_fills_the_students_and_the_applications_values(client, world):
    template = await mk_template(client, world["admin"])
    await login(client, world["counselor"].email)
    response = await client.get(url(world["student"].id, "messages/render"), params={"template_id": template["id"], "application_id": str(world["own"].id)})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["body"] == f"Hi Priya Student, about {world['university'].name}: MSc Data Science (Sep 2027), apply by 14 Sept 2026. Nora Counselor"
    assert data["missing"] == [] and data["template"]["id"] == template["id"]

    general = (await client.get(url(world["student"].id, "messages/render"), params={"template_id": template["id"]})).json()
    assert general["body"] == "Hi Priya Student, about :  (), apply by . Nora Counselor"
    assert general["missing"] == ["university", "course", "intake", "application_deadline"]


@pytest.mark.asyncio
async def test_render_refuses_another_counselors_application_and_the_admin(client, world):
    template = await mk_template(client, world["admin"])
    response = await client.get(url(world["student"].id, "messages/render"), params={"template_id": template["id"]})
    assert response.status_code == 403  # the admin reads the log but does not send (MT4)
    await login(client, world["counselor"].email)
    response = await client.get(url(world["student"].id, "messages/render"), params={"template_id": template["id"], "application_id": str(world["foreign"].id)})
    assert response.status_code == 422 and response.json()["detail"] == "Choose one of this student's applications"


# --- send (MT3-MT6) -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_whatsapp_send_is_logged_against_the_student_and_application(client, db_session, world):
    template = await mk_template(client, world["admin"])
    await login(client, world["counselor"].email)
    body = {"channel": "whatsapp", "template_id": template["id"], "body": "Hi Priya, your offer is in", "application_id": str(world["own"].id)}
    response = await client.post(url(world["student"].id), json=body)
    assert response.status_code == 201, response.text
    message = response.json()
    assert message["direction"] == "outbound" and message["channel"] == "whatsapp" and message["delivery_status"] is None
    assert message["application"] == {"id": str(world["own"].id), "label": f"{world['university'].name} · REF-37"}
    assert message["template"] == {"id": template["id"], "name": template["name"]} and message["sender"]["full_name"] == "Nora Counselor"
    row = await db_session.get(StudentMessage, uuid.UUID(message["id"]))
    assert row.student_user_id == world["student"].id and row.application_id == world["own"].id

    page = (await client.get(url(world["student"].id))).json()
    assert page["total"] == 1 and page["items"][0]["id"] == message["id"]
    assert page["recipient"] == {"name": "Priya Student", "email": world["student"].email, "whatsapp_to": "919876543210"}
    assert page["applications"] == [{"id": str(world["own"].id), "label": f"{world['university'].name} · REF-37"}]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == message["id"]))
    assert audit.action == "student_message.create" and "offer" not in str(audit.metadata_json) and world["student"].email not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_an_email_is_queued_and_published_after_the_commit(client, world, smtp_on, student_emails_enqueued):
    template = await mk_template(client, world["admin"], channel="email", body="Dear {name}")
    await login(client, world["counselor"].email)
    response = await client.post(url(world["student"].id), json={"channel": "email", "template_id": template["id"], "subject": "Your offer", "body": "Dear Priya"})
    assert response.status_code == 201, response.text
    assert response.json()["delivery_status"] == "queued" and response.json()["subject"] == "Your offer" and response.json()["application"] is None
    assert student_emails_enqueued == [(response.json()["id"], 0)]


@pytest.mark.asyncio
async def test_send_rules(client, db_session, world, monkeypatch):
    whatsapp = await mk_template(client, world["admin"])
    await login(client, world["counselor"].email)
    send = lambda body: client.post(url(world["student"].id), json=body)  # noqa: E731
    response = await send({"channel": "email", "subject": "S", "body": "B"})
    assert response.status_code == 503  # SMTP unset (MT5)
    response = await send({"channel": "email", "template_id": whatsapp["id"], "subject": "S", "body": "B"})
    assert response.status_code == 503
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@example.local")
    response = await send({"channel": "email", "template_id": whatsapp["id"], "subject": "S", "body": "B"})
    assert response.status_code == 422 and response.json()["detail"] == "Choose an active email template"
    response = await send({"channel": "whatsapp", "body": "B", "application_id": str(world["foreign"].id)})
    assert response.status_code == 422 and response.json()["detail"] == "Choose one of this student's applications"
    for payload in ({"channel": "whatsapp", "body": "  "}, {"channel": "whatsapp", "body": "B", "subject": "S"}, {"channel": "email", "body": "B"},
                    {"channel": "whatsapp", "body": "B", "to": "+447000000000"}, {"channel": "sms", "body": "B"}):  # fmt: skip
        assert (await send(payload)).status_code == 422, payload

    world["student"].phone = "12"
    await db_session.commit()
    response = await send({"channel": "whatsapp", "body": "B"})
    assert response.status_code == 409 and response.json()["detail"] == "This student has no usable mobile number"
    world["student"].phone, world["student"].active = "9876543210", False
    await db_session.commit()
    response = await send({"channel": "whatsapp", "body": "B"})
    assert response.status_code == 409 and response.json()["detail"] == "This student's account is deactivated"
    assert await db_session.scalar(select(func.count()).select_from(StudentMessage).where(StudentMessage.student_user_id == world["student"].id)) == 0


@pytest.mark.asyncio
async def test_daily_caps(client, world, monkeypatch, smtp_on, student_emails_enqueued):
    monkeypatch.setattr(counselor_messages, "DAILY_CAP", 1)
    monkeypatch.setattr(counselor_messages, "EMAIL_DAILY_CAP", 1)
    monkeypatch.setattr(counselor_messages, "REPLY_DAILY_CAP", 1)
    await login(client, world["counselor"].email)
    for status in (201, 409):
        assert (await client.post(url(world["student"].id), json={"channel": "whatsapp", "body": "Hi"})).status_code == status
        assert (await client.post(url(world["student"].id, "replies"), json={"channel": "whatsapp", "body": "Thanks"})).status_code == status
    assert (await client.post(url(world["student"].id), json={"channel": "email", "subject": "S", "body": "B"})).status_code == 201
    assert (await client.post(url(world["student"].id), json={"channel": "email", "subject": "S", "body": "B"})).status_code == 429


# --- replies (MT7) ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_reply_is_recorded_by_hand(client, db_session, world):
    await login(client, world["counselor"].email)
    response = await client.post(url(world["student"].id, "replies"), json={"channel": "email", "subject": "Re: offer", "body": "I accept", "application_id": str(world["own"].id)})
    assert response.status_code == 201, response.text
    reply = response.json()
    assert reply["direction"] == "inbound" and reply["delivery_status"] is None and reply["template"] is None and reply["subject"] == "Re: offer"
    assert reply["application"]["id"] == str(world["own"].id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == reply["id"]))
    assert audit.action == "student_message.reply" and "accept" not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_reply_rules(client, world):
    await login(client, world["counselor"].email)
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    old = (datetime.now(UTC) - timedelta(days=9)).isoformat()
    for payload, detail in (
        ({"channel": "whatsapp", "body": "Hi", "received_at": future}, "The reply time can't be in the future"),
        ({"channel": "whatsapp", "body": "Hi", "received_at": old}, "Replies can be recorded up to 7 days back"),
    ):
        response = await client.post(url(world["student"].id, "replies"), json=payload)
        assert response.status_code == 422 and detail in response.text
    for payload in ({"channel": "whatsapp", "body": "Hi", "subject": "S"}, {"channel": "whatsapp", "body": "Hi", "template_id": str(uuid.uuid4())}, {"channel": "email", "body": " "}):
        assert (await client.post(url(world["student"].id, "replies"), json=payload)).status_code == 422, payload
    earlier = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    response = await client.post(url(world["student"].id, "replies"), json={"channel": "whatsapp", "body": "Got it", "received_at": earlier})
    assert response.status_code == 201 and response.json()["sent_at"][:10] == earlier[:10]


# --- read and scope (MT4, MT9) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_log_survives_a_reassignment_and_the_admin_reads_it(client, db_session, world):
    await login(client, world["counselor"].email)
    sent = (await client.post(url(world["student"].id), json={"channel": "whatsapp", "body": "Hello"})).json()
    db_session.add(OverseasStudentCounselor(student_user_id=world["student"].id, counselor_user_id=world["other"].id, assigned_by_user_id=world["admin"].id))
    await db_session.commit()
    await login(client, world["other"].email)  # `other` also has the student in scope (their own application)
    assert [m["id"] for m in (await client.get(url(world["student"].id))).json()["items"]] == [sent["id"]]
    await login(client, world["admin"].email)
    page = (await client.get(url(world["student"].id))).json()
    assert [m["id"] for m in page["items"]] == [sent["id"]] and len(page["applications"]) == 2  # every application for the admin
    response = await client.post(url(world["student"].id), json={"channel": "whatsapp", "body": "Hello"})
    assert response.status_code == 403 and response.json()["detail"] == "Only the student's counselor can send messages"
    assert (await client.post(url(world["student"].id, "replies"), json={"channel": "whatsapp", "body": "Hello"})).status_code == 403


@pytest.mark.asyncio
async def test_out_of_scope_unknown_and_non_students_are_404(client, db_session, world):
    stranger = await mk_user(db_session, role="overseas_student")
    await login(client, world["counselor"].email)
    for target in (stranger.id, uuid.uuid4(), world["other"].id):
        assert (await client.get(url(target))).status_code == 404
        response = await client.post(url(target), json={"channel": "whatsapp", "body": "Hi"})
        assert response.status_code == 404 and response.json()["detail"] == "Student not found"
        assert (await client.post(url(target, "replies"), json={"channel": "whatsapp", "body": "Hi"})).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("overseas_student", "overseas"), ("agent", "overseas"), ("telecaller", "overseas"), ("counselor", "it")])
async def test_other_roles_never_see_the_log(client, db_session, world, role, division):
    user = world["student"] if role == "overseas_student" else await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division=division)
    assert (await client.get(url(world["student"].id))).status_code == 403
    assert (await client.post(url(world["student"].id), json={"channel": "whatsapp", "body": "Hi"})).status_code == 403
