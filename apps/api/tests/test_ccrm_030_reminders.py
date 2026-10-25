"""ccrm-030 (DEC-SCOPE-270, RM1-RM10): the counselor reminder rules fire once on sample records (AC 12) and never again on a re-run (RM3);
the windows (RM2), the exclusions (RM4/RM5), the student reminder, first contact on assignment (RM8) and the admin routes (RM9/RM10).
The shared test database is never truncated: every assertion is about rows the test made.
Spec: docs/superpowers/specs/2026-10-25-ccrm-030-counselor-reminders-design.md."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import (
    AgentStudent,
    ApplicationDepositRecord,
    ApplicationOffer,
    ApplicationOfferCondition,
    ApplicationOutcome,
    AuditLog,
    CounselorReminderLog,
    CounselorReminderRule,
    CounselorTask,
    DocumentRequest,
    LeadCall,
    Notification,
    VisaCase,
)
from app.services import counselor_reminders as svc
from app.services import lead_handover
from app.services.bdm_travel import india_today
from tests.agn001_helpers import login, mk_active_org, mk_user, uniq
from tests.agn008_helpers import mk_application, mk_school_student
from tests.ccrm012_helpers import mk_lead, mk_university

URL = "/api/v1/overseas-admin/reminder-rules"


def day(offset: int = 0) -> date:
    return india_today() + timedelta(days=offset)


async def run(db) -> dict:
    return await svc.send_counselor_reminders(db, now=datetime.now(UTC))


async def fired(db, key: str, subject_id) -> int:
    return await db.scalar(select(func.count()).select_from(CounselorReminderLog).where(CounselorReminderLog.rule_key == key, CounselorReminderLog.subject_id == subject_id))


async def notes(db, user, title: str) -> list[Notification]:
    return list((await db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.title == title))).all())


async def rule_tasks(db, key: str, **link) -> list[CounselorTask]:
    column, value = next(iter(link.items()))
    return list((await db.scalars(select(CounselorTask).where(CounselorTask.rule_key == key, getattr(CounselorTask, column) == value))).all())


@pytest_asyncio.fixture(autouse=True)
async def default_rules(db_session):
    """Every rule enabled at its RM1 default, whatever an earlier test (or the admin route test) left behind."""
    for key, rule in svc.RULES.items():
        row = await db_session.get(CounselorReminderRule, key)
        if row is None:
            db_session.add(CounselorReminderRule(rule_key=key, enabled=True, offset_days=rule.offset, notify_student=bool(rule.student)))
        else:
            row.enabled, row.offset_days, row.notify_student = True, rule.offset, bool(rule.student)
    await db_session.commit()


async def set_rule(db, key: str, **values) -> None:
    row = await db.get(CounselorReminderRule, key)
    for field, value in values.items():
        setattr(row, field, value)
    await db.commit()


@pytest_asyncio.fixture
async def world(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name=f"Reminder Counselor {uniq()}")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Reminder Admin")
    student = await mk_user(db_session, role="overseas_student", full_name=f"Reminder Student {uniq()}")
    university = await mk_university(db_session, "Remindia")
    return {"counselor": counselor, "admin": admin, "student": student, "university": university}


async def direct_app(db, w, **fields):
    fields.setdefault("status", "university_selection")
    return await mk_application(db, agent=None, university=w["university"], student=w["student"], counselor_id=w["counselor"].id, **fields)


# --- notify rules (AC 12, RM2, RM3) -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_application_deadline_notifies_the_counselor_once(db_session, world):
    app = await direct_app(db_session, world, application_deadline=day(5))
    later = await direct_app(db_session, world, application_deadline=day(10))
    submitted = await direct_app(db_session, world, application_deadline=day(2), submitted_on=day(-1))
    await run(db_session)
    assert await fired(db_session, "application_deadline", app.id) == 1
    assert await fired(db_session, "application_deadline", later.id) == 0
    assert await fired(db_session, "application_deadline", submitted.id) == 0
    sent = [n for n in await notes(db_session, world["counselor"], "Application deadline approaching") if app.application_code in n.body]
    assert len(sent) == 1 and sent[0].action_url == "/overseas/counselor/applications" and world["student"].full_name not in sent[0].body
    assert await notes(db_session, world["student"], "Application deadline approaching") == []  # no student column on this rule
    counts = await run(db_session)  # RM3: the re-run sends nothing new for it
    assert await fired(db_session, "application_deadline", app.id) == 1 and counts["failed"] == 0
    assert len([n for n in await notes(db_session, world["counselor"], "Application deadline approaching") if app.application_code in n.body]) == 1


@pytest.mark.asyncio
async def test_a_changed_deadline_is_a_new_reminder(db_session, world):
    app = await direct_app(db_session, world, application_deadline=day(3))
    await run(db_session)
    app.application_deadline = day(4)
    await db_session.commit()
    await run(db_session)
    assert await fired(db_session, "application_deadline", app.id) == 2


@pytest.mark.asyncio
async def test_offer_deadline_reminds_counselor_and_direct_student(db_session, world):
    app = await direct_app(db_session, world, status="offer")
    offer = ApplicationOffer(application_id=app.id, offer_type="conditional", issue_date=day(-5), offer_deadline=day(2))
    db_session.add(offer)
    await db_session.commit()
    await run(db_session)
    assert await fired(db_session, "offer_deadline", offer.id) == 1
    assert any(app.application_code in n.body for n in await notes(db_session, world["counselor"], "Offer deadline approaching"))
    student_notes = [n for n in await notes(db_session, world["student"], "Offer deadline approaching") if app.application_code in n.body]
    assert len(student_notes) == 1 and student_notes[0].action_url == "/overseas/student/applications"


@pytest.mark.asyncio
async def test_student_reminder_can_be_switched_off(db_session, world):
    await set_rule(db_session, "offer_deadline", notify_student=False)
    app = await direct_app(db_session, world, status="offer")
    db_session.add(ApplicationOffer(application_id=app.id, offer_type="unconditional", issue_date=day(-5), offer_deadline=day(1)))
    await db_session.commit()
    await run(db_session)
    assert not [n for n in await notes(db_session, world["student"], "Offer deadline approaching") if app.application_code in n.body]


@pytest.mark.asyncio
async def test_deposit_and_condition_due(db_session, world):
    app = await direct_app(db_session, world, status="offer")
    offer = ApplicationOffer(application_id=app.id, offer_type="conditional", issue_date=day(-5))
    db_session.add(offer)
    await db_session.flush()
    deposit = ApplicationDepositRecord(
        application_id=app.id,
        required=True,
        amount=Decimal("500"),
        currency="GBP",
        due_date=day(1),
        payment_status="pending",
        recorded_by_id=world["counselor"].id,
        updated_by_id=world["counselor"].id,
    )
    mine = ApplicationOfferCondition(offer_id=offer.id, description="IELTS 6.5", owner="student", due_date=day(3))
    theirs = ApplicationOfferCondition(offer_id=offer.id, description="Reference", owner="counselor", due_date=day(2))
    met = ApplicationOfferCondition(offer_id=offer.id, description="Transcript", owner="student", due_date=day(1), status="met")
    db_session.add_all([deposit, mine, theirs, met])
    await db_session.commit()
    await run(db_session)
    assert await fired(db_session, "deposit_due", deposit.id) == 1
    assert [await fired(db_session, "condition_due", c.id) for c in (mine, theirs, met)] == [1, 1, 0]
    student_conditions = [n for n in await notes(db_session, world["student"], "Offer condition due") if app.application_code in n.body]
    assert len(student_conditions) == 1  # only the student's own condition reaches them
    assert "IELTS" not in student_conditions[0].body  # RM7: no typed text


@pytest.mark.asyncio
async def test_visa_appointment_counselor_only_by_default(db_session, world):
    app = await direct_app(db_session, world, status="visa_documentation")
    case = VisaCase(application_id=app.id, appointment_date=day(1))
    decided = VisaCase(application_id=app.id, appointment_date=day(1), decision="approved")
    db_session.add_all([case, decided])
    await db_session.commit()
    await run(db_session)
    assert await fired(db_session, "visa_appointment", case.id) == 1 and await fired(db_session, "visa_appointment", decided.id) == 0
    assert not [n for n in await notes(db_session, world["student"], "Visa appointment approaching") if app.application_code in n.body]


# --- task rules -----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_decision_overdue_adds_one_rule_task(db_session, world):
    app = await direct_app(db_session, world, submitted_on=day(-30), decision_due_on=day(-1))
    due_today = await direct_app(db_session, world, submitted_on=day(-30), decision_due_on=day(0))
    ancient = await direct_app(db_session, world, submitted_on=day(-90), decision_due_on=day(-40))
    await run(db_session)
    await run(db_session)
    tasks = await rule_tasks(db_session, "decision_overdue", application_id=app.id)
    assert len(tasks) == 1
    task = tasks[0]
    assert task.source == "rule" and task.counselor_user_id == world["counselor"].id and task.created_by_user_id == world["counselor"].id
    assert task.due_on == day(0) and task.status == "open" and app.application_code in task.title
    assert await rule_tasks(db_session, "decision_overdue", application_id=due_today.id) == []
    assert await rule_tasks(db_session, "decision_overdue", application_id=ancient.id) == []  # RM2 lookback
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(task.id), AuditLog.action == "counselor_task.create"))
    assert audit is not None and audit.metadata_json["rule"] == "decision_overdue"
    log = await db_session.scalar(select(CounselorReminderLog).where(CounselorReminderLog.subject_id == app.id))
    assert log.task_id == task.id and log.recipients == 1


@pytest.mark.asyncio
async def test_hold_review_goes_to_the_hold_owner(db_session, world):
    owner = await mk_user(db_session, role="counselor", full_name=f"Hold Owner {uniq()}")
    app = await direct_app(db_session, world, outcome="on_hold")
    db_session.add(ApplicationOutcome(application_id=app.id, outcome="on_hold", outcome_date=day(-10), review_date=day(0), hold_owner_id=owner.id, created_by_id=world["counselor"].id))
    await db_session.commit()
    deadline_too = await direct_app(db_session, world, outcome="on_hold", application_deadline=day(1))  # RM5: on hold pauses other rules
    await run(db_session)
    tasks = await rule_tasks(db_session, "hold_review", application_id=app.id)
    assert len(tasks) == 1 and tasks[0].counselor_user_id == owner.id
    assert await fired(db_session, "application_deadline", deadline_too.id) == 0


@pytest.mark.asyncio
async def test_document_overdue_tasks_counselor_and_reminds_student(db_session, world):
    request = DocumentRequest(student_user_id=world["student"].id, document_type="IELTS scorecard", due_date=day(-1), status="open", requested_by_user_id=world["counselor"].id)
    not_yet = DocumentRequest(student_user_id=world["student"].id, document_type="Passport", due_date=day(0), status="open", requested_by_user_id=world["counselor"].id)
    db_session.add_all([request, not_yet])
    await db_session.commit()
    await run(db_session)
    tasks = await rule_tasks(db_session, "document_overdue", student_user_id=world["student"].id)
    assert len(tasks) == 1 and "IELTS scorecard" in tasks[0].title
    assert await fired(db_session, "document_overdue", not_yet.id) == 0
    reminders = await notes(db_session, world["student"], "Requested document overdue")
    assert len(reminders) == 1 and reminders[0].action_url == "/overseas/student/documents"


@pytest.mark.asyncio
async def test_no_response_follow_up_task(db_session, world):
    quiet = await mk_lead(db_session, world["counselor"], status="contacted", stage_changed_at=datetime.now(UTC) - timedelta(days=4))
    called = await mk_lead(db_session, world["counselor"], status="contacted", stage_changed_at=datetime.now(UTC) - timedelta(days=4))
    db_session.add(
        LeadCall(lead_id=called.id, caller_user_id=world["counselor"].id, occurred_at=datetime.now(UTC) - timedelta(days=1), duration_seconds=60, call_type="outgoing", outcome="interested")
    )
    planned = await mk_lead(db_session, world["counselor"], status="follow_up", stage_changed_at=datetime.now(UTC) - timedelta(days=5), next_action="Call back", next_action_due=day(1))
    fresh = await mk_lead(db_session, world["counselor"], status="contacted")
    await db_session.commit()
    await run(db_session)
    assert len(await rule_tasks(db_session, "no_response", lead_id=quiet.id)) == 1
    for lead in (called, planned, fresh):
        assert await rule_tasks(db_session, "no_response", lead_id=lead.id) == []


@pytest.mark.asyncio
async def test_qa01_a_status_outside_the_pipeline_counts_as_before_the_offer(db_session, world):
    """QA-01: rows still carry pre-pipeline statuses (seeded `university_review`); before the offer stage means not yet at it."""
    legacy = await direct_app(db_session, world, status="university_review", submitted_on=day(-20), decision_due_on=day(-2))
    unsubmitted = await direct_app(db_session, world, status="university_review", application_deadline=day(2))
    await run(db_session)
    assert len(await rule_tasks(db_session, "decision_overdue", application_id=legacy.id)) == 1
    assert await fired(db_session, "application_deadline", unsubmitted.id) == 1


@pytest.mark.asyncio
async def test_qa02_a_school_bridged_application_reminds_its_overseas_counselor(db_session, world):
    """QA-02: a School-bridged application with an overseas counselor is theirs to work; there is no student login to remind."""
    school_student = await mk_school_student(db_session)
    app = await mk_application(
        db_session, agent=None, university=world["university"], school_student=school_student, counselor_id=world["counselor"].id, status="eligibility_evaluation", application_deadline=day(3)
    )
    await run(db_session)
    assert await fired(db_session, "application_deadline", app.id) == 1
    log = await db_session.scalar(select(CounselorReminderLog).where(CounselorReminderLog.subject_id == app.id))
    assert log.recipients == 1


# --- exclusions (RM4, RM5)------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_terminal_inactive_and_agency_exclusions(db_session, world):
    rejected = await direct_app(db_session, world, outcome="rejected", application_deadline=day(1))
    gone = await mk_user(db_session, role="counselor", active=False)
    orphan = await mk_application(db_session, agent=None, university=world["university"], student=world["student"], counselor_id=gone.id, status="university_selection", application_deadline=day(1))
    org = await mk_active_org(db_session)
    record = AgentStudent(agent_id=org["master"].id, full_name=f"Agency Kid {uniq()}", status="active", student_id=world["student"].id)
    db_session.add(record)
    await db_session.commit()
    agency = await mk_application(db_session, agent=org["master"], university=world["university"], record=record, counselor_id=world["counselor"].id, status="offer")
    db_session.add(ApplicationOffer(application_id=agency.id, offer_type="unconditional", issue_date=day(-3), offer_deadline=day(1)))
    await db_session.commit()
    counts = await run(db_session)
    assert await fired(db_session, "application_deadline", rejected.id) == 0
    assert await fired(db_session, "application_deadline", orphan.id) == 0 and counts["skipped"] >= 1
    assert any(agency.application_code in n.body for n in await notes(db_session, world["counselor"], "Offer deadline approaching"))
    assert not [n for n in await notes(db_session, world["student"], "Offer deadline approaching") if agency.application_code in n.body]  # RM4
    assert not [n for n in await notes(db_session, org["master"], "Offer deadline approaching")]  # agents: AGN-017 only


@pytest.mark.asyncio
async def test_a_disabled_rule_does_nothing(db_session, world):
    await set_rule(db_session, "application_deadline", enabled=False)
    app = await direct_app(db_session, world, application_deadline=day(1))
    counts = await run(db_session)
    assert await fired(db_session, "application_deadline", app.id) == 0 and counts["rules"]["application_deadline"] == 0


@pytest.mark.asyncio
async def test_the_offset_moves_the_window(db_session, world):
    await set_rule(db_session, "application_deadline", offset_days=14)
    app = await direct_app(db_session, world, application_deadline=day(12))
    await run(db_session)
    assert await fired(db_session, "application_deadline", app.id) == 1


# --- first contact (RM8) --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handover_adds_a_first_contact_task(db_session, world):
    telecaller = await mk_user(db_session, role="telecaller", full_name="Reminder Telecaller")
    lead = await mk_lead(db_session, telecaller, status="contacted")
    lead.owner_id = None
    await db_session.commit()
    await lead_handover.handover(db_session, telecaller, lead, world["counselor"].id)
    await db_session.commit()
    tasks = await rule_tasks(db_session, "first_contact", lead_id=lead.id)
    assert len(tasks) == 1 and tasks[0].due_on == day(1) and tasks[0].counselor_user_id == world["counselor"].id
    assert any(lead.lead_code in n.body for n in await notes(db_session, world["counselor"], "New lead assigned"))


@pytest.mark.asyncio
async def test_admin_owner_change_adds_first_contact_once(client, db_session, world):
    other = await mk_user(db_session, role="counselor", full_name=f"Prior Counselor {uniq()}")
    lead = await mk_lead(db_session, other, status="contacted")
    await login(client, world["admin"].email, "overseas")
    url = f"/api/v1/admin/leads/{lead.id}"
    # ccrm-033 RR1: replacing the prior counselor needs a reason; the unchanged resend needs none
    assert (await client.patch(url, json={"owner_id": str(world["counselor"].id), "owner_reason": "Workload balance"})).status_code == 200
    assert (await client.patch(url, json={"owner_id": str(world["counselor"].id)})).status_code == 200  # unchanged owner: nothing new
    assert len(await rule_tasks(db_session, "first_contact", lead_id=lead.id)) == 1
    await set_rule(db_session, "first_contact", enabled=False)
    assert (await client.patch(url, json={"owner_id": str(other.id), "owner_reason": "Workload balance"})).status_code == 200  # ccrm-033 RR1
    assert len(await rule_tasks(db_session, "first_contact", lead_id=lead.id)) == 1


# --- admin routes (RM9, RM10) ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_reads_and_changes_rules(client, db_session, world):
    await login(client, world["admin"].email, "overseas")
    rules = (await client.get(URL)).json()["rules"]
    assert [r["key"] for r in rules] == list(svc.RULES)
    by_key = {r["key"]: r for r in rules}
    assert by_key["application_deadline"]["offset_days"] == 7 and by_key["application_deadline"]["notify_student"] is None
    assert by_key["offer_deadline"]["notify_student"] is True
    response = await client.put(f"{URL}/offer_deadline", json={"enabled": False, "offset_days": 5, "notify_student": False})
    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is False and response.json()["offset_days"] == 5 and response.json()["notify_student"] is False
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "counselor_reminder_rule.update", AuditLog.user_id == world["admin"].id).order_by(AuditLog.created_at.desc()))
    assert set(audit.metadata_json["fields"]) == {"enabled", "offset_days", "notify_student"}
    assert (await client.put(f"{URL}/nope", json={"enabled": True, "offset_days": 1})).status_code == 404
    assert (await client.put(f"{URL}/visa_appointment", json={"enabled": True, "offset_days": 31})).status_code == 422
    assert (await client.put(f"{URL}/no_response", json={"enabled": True, "offset_days": 0})).status_code == 422
    assert (await client.put(f"{URL}/application_deadline", json={"enabled": True, "offset_days": 7, "notify_student": True})).status_code == 422
    assert (await client.put(f"{URL}/application_deadline", json={"enabled": True, "offset_days": 7, "extra": 1})).status_code == 422


@pytest.mark.asyncio
async def test_run_now_is_idempotent_and_logged(client, db_session, world):
    app = await direct_app(db_session, world, application_deadline=day(2))
    await login(client, world["admin"].email, "overseas")
    first = await client.post(f"{URL}/run")
    assert first.status_code == 200 and first.json()["failed"] == 0
    await client.post(f"{URL}/run")
    assert await fired(db_session, "application_deadline", app.id) == 1
    log = (await client.get(f"{URL}/log?limit=100")).json()
    mine = [i for i in log["items"] if app.application_code in i["summary"]]
    assert len(mine) == 1 and mine[0]["rule_label"] == "Application deadline approaching" and mine[0]["task_created"] is False


@pytest.mark.asyncio
async def test_only_the_overseas_admin(client, db_session, world):
    it_admin = await mk_user(db_session, role="overseas_admin", division="it")
    for person in (world["counselor"], it_admin):
        client.cookies.clear()
        await login(client, person.email, person.division)
        assert (await client.get(URL)).status_code == 403
        assert (await client.post(f"{URL}/run")).status_code == 403
        assert (await client.put(f"{URL}/no_response", json={"enabled": False, "offset_days": 3})).status_code == 403
        assert (await client.get(f"{URL}/log")).status_code == 403
