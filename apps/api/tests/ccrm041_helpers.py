"""ccrm-041 test builders: one fixture "world" for the counselor CRM permission matrix (DEC-SCOPE-278). Users are inserted directly and
signed in with the token `/auth/login` issues (tel-026's pattern: no bcrypt round); the records a row's path needs are made through the
real routes where they carry rules (offer, condition, checklist, document request, task, hold) and inserted otherwise. Every value is
unique per call: the test database is shared and never truncated."""

import random
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.models import (
    AgentStudent,
    Agreement,
    CounselorMessageTemplate,
    DocumentChecklistTemplate,
    DocumentChecklistTemplateItem,
    Enquiry,
    LeadCall,
    LeadFollowUp,
    LeadLostReason,
    LeadMessage,
    NotificationPreference,
    OverseasApplication,
    OverseasStudentArchive,
    OverseasStudentCounselor,
    TelecallerProfile,
    TelMessageTemplate,
    User,
    UserRoleAssignment,
    VisaCase,
)
from app.services.agent_orgs import ensure_agent_org
from tests.agn003_helpers import mk_university
from tests.agn009_helpers import mk_doc
from tests.tel026_helpers import headers

API = "/api/v1"
APPS = API + "/workflows/overseas/applications/{}"

# Who calls. `cns` owns every record of the world (the lead, the student, both applications, the task); `cns_out` is another overseas
# counselor; `tel` / `mgr` are the lead's telecaller and their manager; `student` is the direct student; `agent` is the agency's Master.
ROLES = ("anon", "cns", "cns_out", "it_cns", "ovs_admin", "it_admin", "super", "tel", "mgr", "student", "agent", "partner")


def uniq(label: str = "") -> str:
    return f"{label}{uuid.uuid4().hex[:8]}"


def today() -> date:
    return date.today()


async def _add(db, row):
    db.add(row)
    await db.flush()
    return row


async def _user(db, role: str, division: str = "overseas", **over) -> User:
    return await _add(
        db,
        User(
            email=f"{uniq('c41-')}@example.local",
            password_hash="!",
            full_name=f"{role} {uniq()}",
            role=role,
            division=division,
            active=True,
            email_verified=True,
            phone=f"+91 9{random.randint(100000000, 999999999)}",
            **over,
        ),
    )


async def _ok(response, status: int = 201) -> dict:
    assert response.status_code == status, response.text
    return response.json()


async def _current_agreement(db, kind: str) -> Agreement:
    """The current overseas consent of `kind` (CN1: the latest active row). Reused, never replaced: a new row would ask every student again."""
    stmt = select(Agreement).where(Agreement.division == "overseas", Agreement.kind == kind, Agreement.active.is_(True)).order_by(Agreement.created_at.desc())
    row = await db.scalar(stmt.limit(1))
    return row or await _add(db, Agreement(division="overseas", kind=kind, version="1.0", title="Data processing consent", body="We process your data.", active=True))


async def world(db, client) -> dict:
    users = {
        "cns": await _user(db, "counselor"), "cns_out": await _user(db, "counselor"), "it_cns": await _user(db, "counselor", "it"),
        "ovs_admin": await _user(db, "overseas_admin"), "it_admin": await _user(db, "it_admin", "it"), "super": await _user(db, "super_admin", "global"),
        "mgr": await _user(db, "telecaller_manager", "global"), "student": await _user(db, "overseas_student"), "agent": await _user(db, "agent"),
        "partner": await _user(db, "partner", "global"),
    }  # fmt: skip
    users["tel"] = await _user(db, "telecaller")
    await _add(db, TelecallerProfile(user_id=users["tel"].id, team="overseas", employee_id=uniq("E41-"), reporting_manager_user_id=users["mgr"].id))
    cns, student, agent = users["cns"], users["student"], users["agent"]
    db.add(UserRoleAssignment(user_id=agent.id, division="overseas", role="agent", approval_status="approved"))
    await db.flush()
    await ensure_agent_org(db, agent, agency_name=uniq("C41 Agency "), status="active")

    # The lead, handed to the counselor (tel-018), with the counselor's own call, follow-up and message on it.
    lead = await _add(
        db,
        Enquiry(
            division="overseas",
            name=f"Lead {uniq()}",
            email=f"{uniq('c41-lead-')}@example.local",
            phone=f"9{random.randint(100000000, 999999999)}",
            subject="Study abroad",
            message="",
            source="website",
            status="qualified",
            telecaller_user_id=users["tel"].id,
            owner_id=cns.id,
        ),
    )
    now = datetime.now(UTC)
    call = await _add(db, LeadCall(lead_id=lead.id, caller_user_id=cns.id, call_type="outgoing", outcome="interested", duration_seconds=60, occurred_at=now))
    follow_up = await _add(db, LeadFollowUp(lead_id=lead.id, due_at=now + timedelta(days=1), reason="course_details", status="open", created_by_user_id=cns.id))
    message = await _add(db, LeadMessage(lead_id=lead.id, sender_user_id=cns.id, channel="whatsapp", body="Hello", sent_at=now))
    tel_template = await _add(db, TelMessageTemplate(channel="whatsapp", kind="welcome", name=uniq("C41 tpl "), body="Hi {name}"))
    lost_reason = await _add(db, LeadLostReason(name=uniq("C41 reason ")))

    # The direct student's application at University selection, and an agency application, both counselled by `cns`.
    university = await mk_university(db)
    app = await _add(db, OverseasApplication(student_id=student.id, university_id=university.id, intake="Fall 2027", status="university_selection", counselor_id=cns.id))
    record = await _add(db, AgentStudent(agent_id=agent.id, student_id=None, status="active", full_name=f"No Login {uniq()}"))
    agency_app = await _add(db, OverseasApplication(agent_id=agent.id, agent_student_id=record.id, university_id=university.id, intake="Fall 2027", status="university_selection", counselor_id=cns.id))
    held = await _add(db, OverseasApplication(student_id=student.id, university_id=university.id, intake="Spring 2028", status="university_selection", counselor_id=cns.id))
    enrolled = await _add(db, OverseasApplication(student_id=student.id, university_id=university.id, intake="Fall 2026", status="enrolled", sub_status="enrolled", counselor_id=cns.id))
    db.add(NotificationPreference(user_id=student.id, whatsapp_opt_in=True))  # ccrm-040 CN7: a WhatsApp to the student needs it
    visa = await _add(db, VisaCase(application_id=app.id, status="checklist", checklist=[]))
    # A student of `cns` with no application (archivable, csc-001 W3), and an archived one (only the Admin restores).
    lonely, archived = await _user(db, "overseas_student"), await _user(db, "overseas_student")
    for who in (student, lonely, archived):
        db.add(OverseasStudentCounselor(student_user_id=who.id, counselor_user_id=cns.id, assigned_by_user_id=users["ovs_admin"].id))
    db.add(OverseasStudentArchive(student_user_id=archived.id, archived_by_user_id=users["ovs_admin"].id, reason="Closed"))
    template = await _add(db, CounselorMessageTemplate(channel="email", name=uniq("C41 template "), subject="Hello", body="Hello there"))
    checklist_template = await _add(db, DocumentChecklistTemplate(name=uniq("C41 "), kind="visa", country_id=university.country_id, gate_mode="warn", version=1))
    await _add(db, DocumentChecklistTemplateItem(template_id=checklist_template.id, position=1, document_type="Passport", required=True, allowed_statuses=["pending", "verified"]))
    agreement = await _current_agreement(db, "data_processing")
    await db.commit()
    letter = await mk_doc(db, student=student, application=app, document_type="Offer letter")
    document = await mk_doc(db, student=student, application=app, document_type="Passport")
    enrol_doc = await mk_doc(db, student=student, application=app, document_type="Enrolment confirmation")

    # Records whose rules live in their routes: made by the counselor through them.
    as_cns = headers(cns)
    offer = await _ok(await client.post(APPS.format(app.id) + "/offers", headers=as_cns, json={
        "offer_type": "conditional", "issue_date": (today() - timedelta(days=1)).isoformat(), "offer_deadline": (today() + timedelta(days=30)).isoformat(),
        "conditions": "IELTS 6.5", "offer_document_id": str(letter.id)}))  # fmt: skip
    offer = offer["offer"]
    condition = await _ok(
        await client.post(
            APPS.format(app.id) + f"/offers/{offer['id']}/conditions",
            headers=as_cns,
            json={"description": "Final transcript", "owner": "student", "due_date": (today() + timedelta(days=20)).isoformat()},
        )
    )
    condition = condition["condition"]
    await _ok(await client.post(APPS.format(app.id) + "/checklist", headers=as_cns))
    item = (await _ok(await client.post(APPS.format(app.id) + "/checklist/items", headers=as_cns, json={"document_type": "CV", "required": False})))["checklist"]["items"][0]
    await _ok(await client.put(APPS.format(app.id) + f"/checklist/items/{item['id']}/documents/{document.id}", headers=as_cns), 200)
    request = await _ok(
        await client.post(f"{API}/counselor/students/{student.id}/document-requests", headers=as_cns, json={"due_date": (today() + timedelta(days=7)).isoformat(), "document_type": "Passport"})
    )
    task = await _ok(await client.post(f"{API}/counselor/tasks", headers=as_cns, json={"title": "Call the student", "due_on": today().isoformat()}))
    await _ok(await client.post(APPS.format(held.id) + "/outcome", headers=as_cns, json={
        "outcome": "on_hold", "reason": "Waiting for funds", "review_date": (today() + timedelta(days=10)).isoformat(), "hold_owner_id": str(cns.id)}), 200)  # fmt: skip
    # ccrm-048: a required deposit on the direct application, for the Finance tab's receipt upload
    await _ok(await client.put(APPS.format(app.id) + "/deposit", headers=as_cns, json={"required": True, "payment_status": "pending", "amount": "3000", "currency": "GBP"}), 200)

    ids = {
        "lead": lead.id, "call": call.id, "follow_up": follow_up.id, "message": message.id, "tel_template": tel_template.id, "lost_reason": lost_reason.id,
        "student": student.id, "lonely": lonely.id, "archived": archived.id, "app": app.id, "agency_app": agency_app.id, "held": held.id, "enrolled": enrolled.id,
        "record": record.id, "visa": visa.id, "template": template.id, "checklist_template": checklist_template.id, "agreement": agreement.id,
        "letter": letter.id, "document": document.id, "enrol_doc": enrol_doc.id, "offer": offer["id"], "condition": condition["id"], "item": item["id"], "request": request["request"]["id"], "task": task["id"], "country": university.country_id, "university": university.id,
    }  # fmt: skip
    return {"users": users, **{k: str(v) for k, v in ids.items()}, **{f"{k}_id": str(u.id) for k, u in users.items()}}
