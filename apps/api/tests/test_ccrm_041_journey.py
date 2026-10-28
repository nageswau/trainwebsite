"""ccrm-041 -- the Appendix B sample journey through the counselor CRM's routes (DEC-SCOPE-278 G6-G8; spec
docs/superpowers/specs/2026-10-25-ccrm-041-go-live-verification-design.md §5): enquiry -> convert -> three applications -> A missing a
transcript, B a conditional offer, C rejected -> the student accepts B -> visa -> enrolment. A and B never change when C is rejected
(AC 3, AC 9); every status change names its author (AC 6); the reminder rules fire once on the seeded deadlines (AC 12)."""

import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import (
    ApplicationStatusHistory,
    CounselorReminderRule,
    CounselorTask,
    DocumentChecklistTemplate,
    DocumentChecklistTemplateItem,
    Notification,
    OverseasApplication,
    User,
)
from app.services import counselor_reminders, provisioning
from app.services.bdm_travel import india_today
from tests.agn003_helpers import mk_university
from tests.tel016_helpers import setup
from tests.tel026_helpers import headers

API = "/api/v1"
APPS = API + "/workflows/overseas/applications"
APP = APPS + "/{}"
PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


def day(offset: int = 0) -> str:
    return (india_today() + timedelta(days=offset)).isoformat()


async def ok(response, status: int = 200) -> dict:
    assert response.status_code == status, response.text
    return response.json()


async def snapshot(client, db, user, app_id) -> dict:
    """Everything one application shows: its row, offers, checklist, decision record and history (G7)."""
    row = await db.get(OverseasApplication, app_id, populate_existing=True)
    history = await db.scalar(select(func.count()).select_from(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == app_id))
    reads = {tail: (await client.get(APP.format(app_id) + tail, headers=headers(user))).json() for tail in ("/offers", "/checklist", "/deposit", "/details")}
    return {"row": (row.status, row.sub_status, row.outcome, row.updated_at), "history": history, **reads}


async def titles(db, user) -> list[str]:
    return sorted((await db.scalars(select(Notification.title).where(Notification.user_id == user.id))).all())


@pytest.mark.asyncio
async def test_the_appendix_b_journey(client, db_session, monkeypatch):
    async def mail(channel, payload):  # the welcome link is mailed after the commit; no SMTP here
        return "sent", None

    monkeypatch.setattr(provisioning, "send_notification", mail)
    for key, rule in counselor_reminders.RULES.items():  # RM1 defaults, whatever an earlier test left behind
        row = await db_session.get(CounselorReminderRule, key) or CounselorReminderRule(rule_key=key)
        row.enabled, row.offset_days, row.notify_student = True, rule.offset, bool(rule.student)
        db_session.add(row)
    await db_session.commit()

    # 1. The enquiry: a telecaller's overseas lead, handed to the counselor (tel-018) -> a first-contact task (ccrm-030 RM8).
    _, tel, counselor, lead = await setup(db_session, "overseas", status="interested", phone=f"9{random.randint(100000000, 999999999)}")
    as_tel, as_cns = headers(tel), headers(counselor)
    await ok(await client.post(f"{API}/telecaller/leads/{lead.id}/handover", headers=as_tel, json={"counselor_id": str(counselor.id)}))
    tasks = (await db_session.scalars(select(CounselorTask.title).where(CounselorTask.counselor_user_id == counselor.id))).all()
    assert tasks == [f"First contact: {lead.lead_code}"]
    # The counselor counsels and qualifies the lead (ccrm-003), then converts it (ccrm-008).
    for stage in ("counselling_scheduled", "counselling_completed", "qualified"):
        await ok(await client.post(f"{API}/counselor/leads/{lead.id}/stage", headers=as_cns, json={"to_stage": stage, "next_action": "Next step", "next_action_due": day(2)}))
    email = f"c41-journey-{uuid.uuid4().hex[:8]}@example.local"
    converted = await ok(await client.post(f"{API}/counselor/leads/{lead.id}/convert", headers=as_cns, json={"full_name": "Asha Journey", "email": email}), 201)
    assert converted["lead"]["status"] == "application_enrollment"
    student = await db_session.get(User, uuid.UUID(converted["student"]["id"]))
    assert (student.role, student.division, student.full_name) == ("overseas_student", "overseas", "Asha Journey")

    # 2. Three applications, each its own record and code (ccrm-011), all counselled by the counselor.
    universities = [await mk_university(db_session) for _ in range(3)]
    a, b, c = [(await ok(await client.post(APPS, headers=as_cns, json={"student_id": str(student.id), "university_id": str(u.id), "intake": "Sep 2027"}), 201))["id"] for u in universities]
    rows = [await db_session.get(OverseasApplication, uuid.UUID(x)) for x in (a, b, c)]
    assert len({r.application_code for r in rows}) == 3 and {r.counselor_id for r in rows} == {counselor.id}

    # 3. A: the destination's admission checklist blocks Ready for Submission while the transcript is missing (ccrm-018/019, CC10).
    template = DocumentChecklistTemplate(name="Admission", kind="admission", country_id=universities[0].country_id, gate_mode="block", version=1)
    db_session.add(template)
    await db_session.flush()
    db_session.add(DocumentChecklistTemplateItem(template_id=template.id, position=1, document_type="Transcripts", required=True, allowed_statuses=["pending", "verified"]))
    await db_session.commit()
    await ok(await client.post(APP.format(a) + "/sub-status", headers=as_cns, json={"sub_status": "documents_pending"}))
    refused = await client.post(APP.format(a) + "/sub-status", headers=as_cns, json={"sub_status": "ready_for_submission"})
    assert refused.status_code == 409, refused.text
    assert [m["label"] for m in refused.json()["detail"]["missing"]] == ["Transcripts"]

    # 4. B: a conditional offer with a condition, a deposit and deadlines inside the reminder windows (ccrm-023/024/025).
    letter = (await ok(await client.post(APP.format(b) + "/offer-letters", headers=as_cns, files={"file": ("offer.pdf", PDF, "application/pdf")}), 201))["document"]
    offer = (await ok(await client.post(APP.format(b) + "/offers", headers=as_cns, json={
        "offer_type": "conditional", "issue_date": day(-1), "offer_deadline": day(2), "conditions": "IELTS 6.5", "currency": "GBP",
        "tuition_amount": "18500", "offer_document_id": letter["id"]}), 201))["offer"]  # fmt: skip
    await ok(await client.post(APP.format(b) + f"/offers/{offer['id']}/conditions", headers=as_cns, json={"description": "Final transcript", "owner": "student", "due_date": day(2)}), 201)
    await ok(await client.put(APP.format(b) + "/deposit", headers=as_cns, json={"required": True, "payment_status": "pending", "amount": "3000", "currency": "GBP", "due_date": day(2)}))
    assert (await db_session.get(OverseasApplication, uuid.UUID(b), populate_existing=True)).sub_status == "conditional_offer"

    # 5. C is rejected; A and B do not change (AC 3, AC 9) and C's history names the counselor and the reason (AC 6).
    before = {x: await snapshot(client, db_session, counselor, x) for x in (a, b)}
    await ok(await client.post(APP.format(c) + "/outcome", headers=as_cns, json={"outcome": "rejected", "reason": "Grades below the cut-off"}))
    assert {x: await snapshot(client, db_session, counselor, x) for x in (a, b)} == before
    history = await ok(await client.get(APP.format(c) + "/status", headers=as_cns))
    last = (history["history"] if isinstance(history, dict) else history)[-1]
    assert last["changed_by"] == counselor.full_name and last["outcome"] == "rejected" and last["reason"] == "Grades below the cut-off", last

    # 6. The reminder run notices B's deadlines once: the counselor, and the student for their own condition, offer and deposit (AC 12).
    await counselor_reminders.send_counselor_reminders(db_session, now=datetime.now(UTC))
    due = ["Deposit due", "Offer condition due", "Offer deadline approaching"]
    assert [t for t in await titles(db_session, counselor) if t in due] == due
    assert [t for t in await titles(db_session, student) if t in due] == due
    counts = (len(await titles(db_session, counselor)), len(await titles(db_session, student)))
    await counselor_reminders.send_counselor_reminders(db_session, now=datetime.now(UTC))
    assert (len(await titles(db_session, counselor)), len(await titles(db_session, student))) == counts  # RM3: never twice

    # 7. The student accepts B (ccrm-025); A and C do not change.
    before = {x: await snapshot(client, db_session, counselor, x) for x in (a, c)}
    await ok(await client.post(APP.format(b) + f"/offers/{offer['id']}/decision", headers=as_cns, json={"decision": "accepted", "decision_date": day()}))
    assert (await db_session.get(OverseasApplication, uuid.UUID(b), populate_existing=True)).sub_status == "offer_accepted"

    # 8. Visa on B (ccrm-026): the appointment inside the window is reminded, then submitted and approved.
    visa = await ok(await client.post(f"{API}/workflows/overseas/visa", headers=as_cns, json={"application_id": b}), 201)
    lifecycle = f"{API}/workflows/overseas/visa/{visa['id']}/lifecycle"
    steps = [("not_started", "preparing", {}), ("preparing", "appointment_booked", {"appointment_date": day(1), "appointment_place": "VFS Chennai"})]
    for current, target, extra in steps:
        await ok(await client.patch(lifecycle, headers=as_cns, json={"expected_visa_status": current, "visa_status": target, **extra}))
    await counselor_reminders.send_counselor_reminders(db_session, now=datetime.now(UTC))
    assert "Visa appointment approaching" in await titles(db_session, counselor)
    assert "Visa appointment approaching" not in await titles(db_session, student)  # RM6: the counselor only
    for current, target, extra in [("appointment_booked", "submitted", {"submission_date": day()}), ("submitted", "approved", {})]:
        await ok(await client.patch(lifecycle, headers=as_cns, json={"expected_visa_status": current, "visa_status": target, **extra}))
    row = await db_session.get(OverseasApplication, uuid.UUID(b), populate_existing=True)
    assert (row.status, row.sub_status) == ("status_tracking", "visa_approved")

    # 9. Enrolment on B with the confirmation document (ccrm-027); A and C are still as they were.
    document = (await ok(await client.post(APP.format(b) + "/enrollment-documents", headers=as_cns, files={"file": ("enrolment.pdf", PDF, "application/pdf")}), 201))["document"]
    await ok(await client.put(APP.format(b) + "/enrollment", headers=as_cns, json={
        "expected_status": "status_tracking", "enrollment_date": day(), "enrollment_document_id": document["id"], "pre_enrollment_checklist_complete": True}))  # fmt: skip
    row = await db_session.get(OverseasApplication, uuid.UUID(b), populate_existing=True)
    assert (row.status, row.sub_status) == ("enrolled", "enrolled")
    assert {x: await snapshot(client, db_session, counselor, x) for x in (a, c)} == before
    # The lead reads as Converted once its student has an enrolled application (tel-018).
    assert (await ok(await client.get(f"{API}/counselor/leads/{lead.id}", headers=as_cns)))["status"] == "converted"
