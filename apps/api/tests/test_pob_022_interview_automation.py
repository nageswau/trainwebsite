"""pob-022 (DEC-SCOPE-421 A1-A8) -- interview coordination automation: the approved confirmation template, the reminders (once each, re-armed
by a reschedule), the feedback chase follow-up and its escalation to the Team Lead, and the settings. The shared test database is never
truncated, so the sweep tests stamp every other interview's markers first and the sweeps run at a chosen `now`."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update

from app.models import (
    AuditLog,
    CompanyContact,
    Interview,
    InterviewAutomationSetting,
    InterviewFeedback,
    Notification,
    RecruiterFollowUp,
    RecruiterMessage,
    RecruiterMessageTemplate,
)
from app.notifications.events import EVENTS, RECRUITMENT_EVENTS
from app.services import interview_automation as auto
from tests.rec001_helpers import login, make_pm, make_recruiter
from tests.test_rec_020_interviews import INTERVIEWS, _at, _interview, _schedule, _setup, published, smtp_on  # noqa: F401

SETTINGS = "/api/v1/recruiter/interview-automation/settings"
DEFAULTS = {"first_reminder_hours": 24, "second_reminder_hours": 2, "reminder_template_id": None, "chase_after_hours": 24, "escalate_after_hours": 24,
            "chase_template_id": None}  # fmt: skip
ESCALATED = "it.interview.feedback_escalated"


def _tag() -> str:
    return uuid.uuid4().hex[:8]


async def _template(db, **over) -> RecruiterMessageTemplate:
    values = {"channel": "email", "kind": "interview_confirmation", "name": f"Confirm {_tag()}", "subject": "Interview for {job_title}",
              "body": "Hello {name}, your interview for {job_title} is on {interview_date} at {interview_time}.", "category": "candidate",
              "status": "approved"} | over  # fmt: skip
    template = RecruiterMessageTemplate(**values)
    db.add(template)
    await db.commit()
    return template


@pytest_asyncio.fixture
async def automation(db_session):
    """The settings row at its defaults for the test, and back to them after."""

    async def put(**values):
        row = await db_session.get(InterviewAutomationSetting, 1)
        if row is None:
            row = InterviewAutomationSetting(id=1)
            db_session.add(row)
        for key, value in (DEFAULTS | values).items():
            setattr(row, key, value)
        await db_session.commit()

    await put()
    yield put
    await put()


@pytest.fixture
def sweep_sent(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr("app.services.interview_automation.enqueue_recruiter_email", lambda message_id: sent.append(str(message_id)) or True)
    return sent


async def _only_this(db, interview_id):
    """Every other interview is out of the sweeps' reach."""
    stamp = datetime.now(UTC) + timedelta(days=400)
    await db.execute(update(Interview).where(Interview.id != interview_id).values(
        first_reminder_at=func.coalesce(Interview.first_reminder_at, stamp), second_reminder_at=func.coalesce(Interview.second_reminder_at, stamp),
        chase_escalated_at=func.coalesce(Interview.chase_escalated_at, stamp)))  # fmt: skip
    await db.commit()


async def _row(db, interview_id) -> Interview:
    return await db.scalar(select(Interview).where(Interview.id == interview_id).execution_options(populate_existing=True))


async def _reminders(db, candidate_id) -> list[RecruiterMessage]:

    rows = await db.scalars(select(RecruiterMessage).where(RecruiterMessage.candidate_id == candidate_id, RecruiterMessage.subject.like("Interview reminder%")).execution_options(populate_existing=True))
    return list(rows.all())


async def _got(db, user_id, event) -> list[Notification]:

    return list((await db.scalars(select(Notification).where(Notification.user_id == user_id, Notification.event_type == event).execution_options(populate_existing=True))).all())


# --- A2 settings -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_settings_defaults_for_a_manager(client, db_session, automation):
    await login(client, await make_pm(db_session))
    response = await client.get(SETTINGS)
    assert response.status_code == 200, response.text
    assert response.json() == DEFAULTS


@pytest.mark.asyncio
async def test_settings_are_forbidden_for_a_recruiter(client, db_session, automation):
    await login(client, await make_recruiter(db_session, await make_pm(db_session)))
    assert (await client.get(SETTINGS)).status_code == 403
    assert (await client.put(SETTINGS, json=DEFAULTS)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("change", "field"), [
    ({"second_reminder_hours": 24}, "second_reminder_hours"), ({"first_reminder_hours": 0}, "first_reminder_hours"),
    ({"first_reminder_hours": 169}, "first_reminder_hours"), ({"escalate_after_hours": 721}, "escalate_after_hours"),
])  # fmt: skip
async def test_settings_validation(client, db_session, automation, change, field):
    await login(client, await make_pm(db_session))
    response = await client.put(SETTINGS, json=DEFAULTS | change)
    assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == field, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("over", [{"status": "draft"}, {"channel": "whatsapp", "kind": "interview_reminder", "subject": None, "category": "whatsapp"}])
async def test_settings_refuse_a_template_that_is_not_an_approved_shared_email(client, db_session, automation, over):
    manager = await make_pm(db_session)
    template = await _template(db_session, **over)
    await login(client, manager)
    response = await client.put(SETTINGS, json=DEFAULTS | {"chase_template_id": str(template.id)})
    assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == "chase_template_id"


@pytest.mark.asyncio
async def test_settings_saved_and_audited(client, db_session, automation):
    manager = await make_pm(db_session)
    template = await _template(db_session, kind="recruitment_proposal", category="company")
    await login(client, manager)
    body = DEFAULTS | {"second_reminder_hours": None, "chase_after_hours": 48, "chase_template_id": str(template.id)}
    response = await client.put(SETTINGS, json=body)
    assert response.status_code == 200 and response.json() == body
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "interview_automation.settings", AuditLog.user_id == manager.id))
    assert audit.metadata_json["changes"]["chase_after_hours"] == [24, 48]


# --- A1 confirmation template ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_confirmation_uses_the_template_for_the_candidate_and_the_contact(client, db_session, smtp_on, published, automation):  # noqa: F811
    s = await _setup(client, db_session)
    template = await _template(db_session)
    contact = CompanyContact(company_id=s["job"].company_id, name=f"Anil {_tag()}", email=f"{_tag()}@example.com")
    db_session.add(contact)
    await db_session.commit()
    response = await _schedule(client, s["application"]["id"], contact_id=str(contact.id), notify=True, template_id=str(template.id),
                               meeting_url="https://meet.example.com/t")  # fmt: skip
    assert response.status_code == 201, response.text
    assert response.json()["notifications"] == {"candidate": "queued", "contact": "queued"}
    rows = (await db_session.scalars(select(RecruiterMessage).where(RecruiterMessage.id.in_(published)))).all()
    to_candidate = next(r for r in rows if r.candidate_id == s["candidate"].id)
    to_contact = next(r for r in rows if r.contact_id == contact.id)
    title = s["job"].title
    assert to_candidate.subject == f"Interview for {title}" and to_candidate.body.startswith(f"Hello {s['candidate'].name}, your interview for {title} is on ")
    assert "https://meet.example.com/t" in to_candidate.body and to_candidate.calendar_ics  # the details and the invite still follow
    assert to_contact.body.startswith(f"Hello {contact.name}, ") and s["candidate"].candidate_code in to_contact.body
    assert {r.template_id for r in rows} == {template.id}
    await db_session.refresh(template)
    assert template.last_used_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("over", [{"status": "draft"}, {"kind": "offer_follow_up"}, {"status": "archived"}])
async def test_confirmation_template_must_be_an_approved_interview_confirmation(client, db_session, over, automation):
    s = await _setup(client, db_session)
    template = await _template(db_session, **over)
    response = await _schedule(client, s["application"]["id"], notify=True, template_id=str(template.id))
    assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == "template_id"


@pytest.mark.asyncio
async def test_a_personal_template_is_refused(client, db_session, automation):
    s = await _setup(client, db_session)
    template = await _template(db_session, status="draft", owner_user_id=s["recruiter"].id)
    response = await _schedule(client, s["application"]["id"], notify=True, template_id=str(template.id))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_without_a_template_the_standard_text_stays(client, db_session, smtp_on, published, automation):  # noqa: F811
    s = await _setup(client, db_session)
    response = await _schedule(client, s["application"]["id"], notify=True)
    assert response.status_code == 201
    row = await db_session.scalar(select(RecruiterMessage).where(RecruiterMessage.id.in_(published)))
    assert row.body.startswith(f"Dear {s['candidate'].name},") and row.template_id is None


@pytest.mark.asyncio
async def test_reschedule_confirms_with_the_template(client, db_session, smtp_on, published, automation):  # noqa: F811
    s = await _setup(client, db_session)
    template = await _template(db_session)
    item = await _interview(client, s["application"]["id"])
    moved = await client.post(f"{INTERVIEWS}/{item['id']}/reschedule", json={"scheduled_at": _at(6), "template_id": str(template.id)})
    assert moved.status_code == 200, moved.text
    row = await db_session.scalar(select(RecruiterMessage).where(RecruiterMessage.id.in_(published)))
    assert row.template_id == template.id and row.body.startswith(f"Hello {s['candidate'].name}")


# --- A3/A4 reminders -------------------------------------------------------------------------------------------------------------------
async def _reminder_world(client, db, days=3):
    s = await _setup(client, db)
    item = await _interview(client, s["application"]["id"], scheduled_at=_at(days))
    interview_id = uuid.UUID(item["id"])
    await _only_this(db, interview_id)
    return s, interview_id, (await _row(db, interview_id)).scheduled_at


@pytest.mark.asyncio
async def test_each_reminder_is_sent_once(client, db_session, smtp_on, sweep_sent, automation):  # noqa: F811
    s, interview_id, at = await _reminder_world(client, db_session)
    row = await _row(db_session, interview_id)
    assert row.first_reminder_at is None and row.second_reminder_at is None  # armed: the interview is days away
    assert await auto.run_reminders(at - timedelta(hours=25)) == {"interviews": 0}
    assert await auto.run_reminders(at - timedelta(hours=23)) == {"interviews": 1}
    assert await auto.run_reminders(at - timedelta(hours=22)) == {"interviews": 0}
    assert await auto.run_reminders(at - timedelta(hours=1)) == {"interviews": 1}
    assert await auto.run_reminders(at - timedelta(minutes=30)) == {"interviews": 0}
    sent = await _reminders(db_session, s["candidate"].id)
    assert len(sent) == 2 and len(sweep_sent) == 2 and all(r.calendar_ics is None for r in sent)
    assert all(r.subject.startswith("Interview reminder: HR Round - ") for r in sent)


@pytest.mark.asyncio
async def test_both_slots_due_at_once_send_one(client, db_session, smtp_on, sweep_sent, automation):  # noqa: F811
    s, interview_id, at = await _reminder_world(client, db_session)
    assert await auto.run_reminders(at - timedelta(hours=1)) == {"interviews": 1}
    assert await auto.run_reminders(at - timedelta(minutes=30)) == {"interviews": 0}
    assert len(await _reminders(db_session, s["candidate"].id)) == 1


@pytest.mark.asyncio
async def test_a_reschedule_rearms_the_reminders(client, db_session, smtp_on, sweep_sent, automation):  # noqa: F811
    s, interview_id, at = await _reminder_world(client, db_session)
    await auto.run_reminders(at - timedelta(hours=1))
    moved = await client.post(f"{INTERVIEWS}/{interview_id}/reschedule", json={"scheduled_at": _at(5)})
    assert moved.status_code == 200
    row = await _row(db_session, interview_id)
    assert row.first_reminder_at is None and row.second_reminder_at is None
    assert await auto.run_reminders(row.scheduled_at - timedelta(hours=23)) == {"interviews": 1}


@pytest.mark.asyncio
async def test_a_reschedule_inside_the_window_is_not_reminded_at_once(client, db_session, smtp_on, sweep_sent, automation):  # noqa: F811
    s, interview_id, _at_ = await _reminder_world(client, db_session)
    soon = (datetime.now(UTC) + timedelta(hours=3)).replace(second=0, microsecond=0)
    moved = await client.post(f"{INTERVIEWS}/{interview_id}/reschedule", json={"scheduled_at": soon.isoformat()})
    assert moved.status_code == 200, moved.text
    row = await _row(db_session, interview_id)
    assert row.first_reminder_at is not None and row.second_reminder_at is None  # 3 h away: inside 24 h, not yet inside 2 h
    assert await auto.run_reminders() == {"interviews": 0}
    assert await auto.run_reminders(soon - timedelta(hours=1)) == {"interviews": 1}


@pytest.mark.asyncio
async def test_a_reminder_skips_a_do_not_contact_contact(client, db_session, smtp_on, sweep_sent, automation):  # noqa: F811
    s = await _setup(client, db_session)
    contact = CompanyContact(company_id=s["job"].company_id, name=f"Ravi {_tag()}", email=f"{_tag()}@example.com", status="do_not_contact")
    db_session.add(contact)
    await db_session.commit()
    item = await _interview(client, s["application"]["id"], contact_id=str(contact.id), scheduled_at=_at(3))
    interview_id = uuid.UUID(item["id"])
    await _only_this(db_session, interview_id)
    at = (await _row(db_session, interview_id)).scheduled_at
    assert await auto.run_reminders(at - timedelta(hours=1)) == {"interviews": 1}

    assert (await db_session.scalars(select(RecruiterMessage).where(RecruiterMessage.contact_id == contact.id))).all() == []
    assert len(await _reminders(db_session, s["candidate"].id)) == 1


@pytest.mark.asyncio
async def test_a_reminder_uses_the_approved_template_and_falls_back_when_archived(client, db_session, smtp_on, sweep_sent, automation):  # noqa: F811
    template = await _template(db_session, subject="Interview reminder: {job_title}", body="Reminder for {name}: {interview_date} {interview_time}.")
    await automation(reminder_template_id=template.id)
    s, interview_id, at = await _reminder_world(client, db_session)
    await auto.run_reminders(at - timedelta(hours=23))
    first = await _reminders(db_session, s["candidate"].id)
    assert len(first) == 1 and first[0].body.startswith(f"Reminder for {s['candidate'].name}: ") and first[0].template_id == template.id
    template.status = "archived"
    await db_session.commit()
    await auto.run_reminders(at - timedelta(hours=1))
    second = [r for r in await _reminders(db_session, s["candidate"].id) if r.id != first[0].id]
    assert len(second) == 1 and second[0].body.startswith(f"Dear {s['candidate'].name},") and second[0].template_id is None


@pytest.mark.asyncio
async def test_a_reminder_switched_off_is_not_sent(client, db_session, smtp_on, sweep_sent, automation):  # noqa: F811
    await automation(first_reminder_hours=None, second_reminder_hours=None)
    s, interview_id, at = await _reminder_world(client, db_session)
    assert await auto.run_reminders(at - timedelta(hours=1)) == {"interviews": 0}


@pytest.mark.asyncio
async def test_a_portal_candidate_gets_an_in_app_reminder(client, db_session, automation):
    from tests.rec001_helpers import make_user
    from tests.rec017_helpers import student_application
    from tests.test_rec_017_tracking import _requirement
    from tests.test_rec_020_interviews import _team

    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    student = await make_user(db_session, "it_student", "it")
    application = await student_application(db_session, job.id, student, status="shortlisted")
    await db_session.commit()
    item = await _interview(client, application.id, scheduled_at=_at(3))
    interview_id = uuid.UUID(item["id"])
    await _only_this(db_session, interview_id)
    at = (await _row(db_session, interview_id)).scheduled_at
    assert await auto.run_reminders(at - timedelta(hours=1)) == {"interviews": 1}
    notices = await _got(db_session, student.id, "it.interview.reminder")
    assert len(notices) == 1 and notices[0].title == "Interview reminder" and notices[0].entity_id == str(interview_id)


# --- A5/A6 feedback chase and escalation -----------------------------------------------------------------------------------------------
async def _overdue(client, db, manager=True):
    s = await _setup(client, db) if manager else None
    if not manager:
        from tests.test_rec_017_tracking import _add, _candidate, _requirement

        recruiter = await make_recruiter(db, None)
        await login(client, recruiter)
        job = await _requirement(db, recruiter)
        candidate = await _candidate(db, recruiter)
        s = {"recruiter": recruiter, "job": job, "candidate": candidate, "application": (await _add(client, job, candidate)).json()["application"]}
    item = await _interview(client, s["application"]["id"])
    interview_id = uuid.UUID(item["id"])
    await db.execute(update(Interview).where(Interview.id == interview_id).values(scheduled_at=datetime.now(UTC) - timedelta(hours=30), ends_at=None))
    await db.commit()
    await _only_this(db, interview_id)
    return s, interview_id


@pytest.mark.asyncio
async def test_overdue_feedback_creates_one_chase_follow_up(client, db_session, automation):
    template = await _template(db_session, kind="recruitment_proposal", category="company", subject="Feedback", body="Dear {name}, any feedback on {candidate}?")
    await automation(chase_template_id=template.id)
    s, interview_id = await _overdue(client, db_session)
    assert await auto.run_feedback_chase() == {"chased": 1, "escalated": 0}
    assert await auto.run_feedback_chase() == {"chased": 0, "escalated": 0}
    row = await _row(db_session, interview_id)
    fu = await db_session.get(RecruiterFollowUp, row.chase_follow_up_id)
    assert fu.reason == "interview_feedback" and fu.status == "open" and fu.company_id == s["job"].company_id
    assert fu.job_id == s["job"].id and str(fu.application_id) == s["application"]["id"] and fu.created_by_user_id == s["recruiter"].id
    assert fu.notes == f"Subject: Feedback\n\nDear , any feedback on {s['candidate'].name}?"  # no contact on the interview: {name} is empty


@pytest.mark.asyncio
async def test_not_chased_within_the_window(client, db_session, automation):
    await automation(chase_after_hours=48)
    _s, _interview_id = await _overdue(client, db_session)
    assert await auto.run_feedback_chase() == {"chased": 0, "escalated": 0}


@pytest.mark.asyncio
async def test_an_open_chase_escalates_once_to_the_team_lead(client, db_session, automation):
    s, interview_id = await _overdue(client, db_session)
    await auto.run_feedback_chase()
    later = datetime.now(UTC) + timedelta(hours=25)
    assert await auto.run_feedback_chase(later - timedelta(hours=2)) == {"chased": 0, "escalated": 0}
    assert await auto.run_feedback_chase(later) == {"chased": 0, "escalated": 1}
    assert await auto.run_feedback_chase(later) == {"chased": 0, "escalated": 0}
    notices = await _got(db_session, s["manager"].id, ESCALATED)
    assert len(notices) == 1 and notices[0].entity_id == str(interview_id)
    assert await _got(db_session, s["recruiter"].id, ESCALATED) == []


@pytest.mark.asyncio
async def test_without_a_reporting_manager_every_active_manager_hears(client, db_session, automation):
    spare = await make_pm(db_session)
    _s, interview_id = await _overdue(client, db_session, manager=False)
    await auto.run_feedback_chase()
    assert await auto.run_feedback_chase(datetime.now(UTC) + timedelta(hours=25)) == {"chased": 0, "escalated": 1}
    assert len(await _got(db_session, spare.id, ESCALATED)) == 1


@pytest.mark.asyncio
async def test_recorded_feedback_or_a_closed_follow_up_stops_the_escalation(client, db_session, automation):
    s, interview_id = await _overdue(client, db_session)
    await auto.run_feedback_chase()
    db_session.add(InterviewFeedback(interview_id=interview_id, overall_rating=4, recorded_by_user_id=s["recruiter"].id))
    await db_session.commit()
    assert await auto.run_feedback_chase(datetime.now(UTC) + timedelta(hours=25)) == {"chased": 0, "escalated": 0}
    s2, interview2 = await _overdue(client, db_session)
    await auto.run_feedback_chase()
    row = await _row(db_session, interview2)
    await db_session.execute(update(RecruiterFollowUp).where(RecruiterFollowUp.id == row.chase_follow_up_id).values(
        status="done", completed_at=datetime.now(UTC), completed_by_user_id=s2["recruiter"].id))  # fmt: skip
    await db_session.commit()
    assert await auto.run_feedback_chase(datetime.now(UTC) + timedelta(hours=25)) == {"chased": 0, "escalated": 0}


@pytest.mark.asyncio
async def test_feedback_recorded_before_the_chase_means_no_follow_up(client, db_session, automation):
    s, interview_id = await _overdue(client, db_session)
    db_session.add(InterviewFeedback(interview_id=interview_id, overall_rating=3, recorded_by_user_id=s["recruiter"].id))
    await db_session.commit()
    assert await auto.run_feedback_chase() == {"chased": 0, "escalated": 0}


# --- A8 catalogue ----------------------------------------------------------------------------------------------------------------------
def test_the_new_notices_are_recruitment_events_with_safe_text():
    assert RECRUITMENT_EVENTS["it.interview.reminder"] == "Interview reminder"  # tagged: the reminder writes its own text (date, link)
    event = EVENTS[ESCALATED]
    assert RECRUITMENT_EVENTS[ESCALATED] == event.title
    text = f"{event.title} {event.body}".lower()
    assert "selected" not in text and "rejected" not in text and "{" not in text
