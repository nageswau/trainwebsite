"""hrc-032 (DEC-SCOPE-412 N1-N7, N12) -- the §13 triggers: each produces its notice exactly once, through the itc-002 catalogue, with text that
is safe to preview; an internal stage tells the candidate nothing. The shared test database is never truncated, so the sweeps' tests stamp
every other row's marker first and read only their own recipients' notices."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import Interview, InterviewFeedback, InterviewInterviewer, InterviewPanelFeedback, Job, JobApplication, Notification, NotificationDelivery, NotificationPreference
from app.notifications.events import EVENTS, RECRUITMENT_EVENTS
from app.services import recruitment_notices
from tests.rec001_helpers import login, make_user
from tests.rec017_helpers import student_application
from tests.test_hrc_007_approval import _require, _restore_settings  # noqa: F401
from tests.test_hrc_009_review import _patch
from tests.test_hrc_009_review import _world as _owned_world
from tests.test_hrc_027_candidate_jobs import JOBS
from tests.test_hrc_027_candidate_jobs import _setup as _jobs_setup
from tests.test_hrc_028_interviews import _student_setup
from tests.test_hrc_030_results import _decide, _hr_manager, _queue_row, _release, approval_required  # noqa: F401
from tests.test_rec_007_requirements import BASE
from tests.test_rec_016_matching import _world as _match_world
from tests.test_rec_020_interviews import _interview, _setup

APPS = "/api/v1/recruiter/applications"


async def _got(db, user_id, event: str) -> list[Notification]:
    db.expire_all()
    return list((await db.scalars(select(Notification).where(Notification.user_id == user_id, Notification.event_type == event))).all())


# --- the catalogue (N1; AC4) -----------------------------------------------------------------------------------------------------------
def test_every_recruitment_text_is_safe_to_preview():
    for key in RECRUITMENT_EVENTS:
        event = EVENTS.get(key)
        if event is None:
            continue
        text = f"{event.title} {event.body}".lower()
        for word in ("selected", "rejected", "shortlisted", "feedback:", "score", "congratulations", "salary", "not moving forward"):
            assert word not in text, (key, word)


def test_every_new_trigger_is_a_recruitment_event_with_a_label():
    for key in ("it.application.new", "it.application.updated", "it.application.received", "it.requirement.changed", "it.requirement.assigned",
                "it.requirement.approval_needed", "it.interview.feedback_overdue", "it.interview.result_published", "it.job.new_match",
                "it.interview.scheduled", "it.interview.assigned", "it.offer.received", "it.requirement.review_needed", "it.candidate.unassigned"):  # fmt: skip
        assert RECRUITMENT_EVENTS[key]


# --- N2: applied -> owners, once; the candidate keeps the receipt ------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_candidates_own_application_tells_the_owners_once(client, db_session):
    w, user, _candidate, match, _other, _ = await _jobs_setup(client, db_session)
    for row in (w.recruiter, user, match):
        await db_session.refresh(row)
    recruiter_id, user_id, match_id = w.recruiter.id, user.id, match.id
    response = await client.post(f"{JOBS}/{match_id}/apply")
    assert response.status_code == 201, response.text
    notices = await _got(db_session, recruiter_id, "it.application.new")
    assert len(notices) == 1 and notices[0].action_url == f"/recruiter/requirements/{match_id}"
    assert notices[0].entity_type == "job_application"
    assert await _got(db_session, user_id, "it.application.new") == []
    receipts = await _got(db_session, user_id, "it.application.received")
    assert len(receipts) == 1 and receipts[0].title == "Application received"
    assert (await client.post(f"{JOBS}/{match_id}/apply")).status_code == 409  # a repeat adds nothing
    assert len(await _got(db_session, recruiter_id, "it.application.new")) == 1


@pytest.mark.asyncio
async def test_a_recruiter_added_application_tells_no_owner(client, db_session):
    s = await _setup(client, db_session)
    assert await _got(db_session, s["recruiter"].id, "it.application.new") == []


# --- N3: vacancy changed -> owners but the editor, once --------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_vacancy_edit_tells_the_other_owners_once(client, db_session):
    w = await _owned_world(client, db_session, open_apps=False)
    await _patch(client, w, {"description": f"New text {w['tag']}"})
    assert len(await _got(db_session, w["mate_id"], "it.requirement.changed")) == 1
    assert len(await _got(db_session, w["officer_id"], "it.requirement.changed")) == 1
    assert await _got(db_session, w["primary_id"], "it.requirement.changed") == []


@pytest.mark.asyncio
async def test_an_edit_that_changes_nothing_tells_nobody(client, db_session):
    w = await _owned_world(client, db_session, open_apps=False)
    await _patch(client, w, {"description": "Old text"})
    assert await _got(db_session, w["mate_id"], "it.requirement.changed") == []


@pytest.mark.asyncio
async def test_an_eligibility_edit_with_open_applications_sends_only_the_review_notice(client, db_session):
    w = await _owned_world(client, db_session)
    await _patch(client, w, {"experience_min_months": 24})
    assert len(await _got(db_session, w["mate_id"], "it.requirement.review_needed")) == 1
    assert await _got(db_session, w["mate_id"], "it.requirement.changed") == []


@pytest.mark.asyncio
async def test_a_status_change_tells_the_other_owners(client, db_session):
    w = await _owned_world(client, db_session, open_apps=False)
    response = await client.post(f"{BASE}/{w['job']}/status", json={"status": "requirement_received"})
    assert response.status_code == 200, response.text
    assert len(await _got(db_session, w["mate_id"], "it.requirement.changed")) == 1
    assert await _got(db_session, w["primary_id"], "it.requirement.changed") == []


@pytest.mark.asyncio
async def test_a_new_co_owner_is_told_and_the_actor_is_not(client, db_session):
    w = await _owned_world(client, db_session, open_apps=False)
    assert len(await _got(db_session, w["mate_id"], "it.requirement.assigned")) == 1
    assert await _got(db_session, w["primary_id"], "it.requirement.assigned") == []


@pytest.mark.asyncio
async def test_a_submit_tells_the_hr_managers_and_the_answer_tells_the_owners(client, db_session):
    await _require(db_session, "recruiter", True)
    w = await _owned_world(client, db_session, open_apps=False)
    approver = await make_user(db_session, "hr_manager", "it")
    approver_id = approver.id
    response = await client.post(f"{BASE}/{w['job']}/submit", json={})
    assert response.status_code == 200, response.text
    assert len(await _got(db_session, approver_id, "it.requirement.approval_needed")) == 1
    await db_session.refresh(approver)
    await login(client, approver)
    assert (await client.post(f"{BASE}/{w['job']}/approve", json={})).status_code == 200
    assert len(await _got(db_session, w["primary_id"], "it.requirement.changed")) == 1


# --- N5: the candidate's stage: visible moves only, and never the word ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_internal_stage_tells_the_candidate_nothing(client, db_session):
    recruiter, student, application = await _student_setup(client, db_session)
    student_id, application_id = student.id, application.id
    await login(client, recruiter)
    before = len(await _got(db_session, student_id, "it.application.updated"))
    response = await client.post(f"{APPS}/{application_id}/status", json={"status": "profile_shared"})  # internal: the candidate still reads the same stage
    assert response.status_code == 200, response.text
    assert len(await _got(db_session, student_id, "it.application.updated")) == before


@pytest.mark.asyncio
async def test_a_visible_move_tells_the_candidate_once_without_the_stage_word(client, db_session):
    recruiter, student, application = await _student_setup(client, db_session)
    student_id, application_id = student.id, application.id
    await login(client, recruiter)
    response = await client.post(f"{APPS}/{application_id}/status", json={"status": "rejected", "rejection_reason": "skills_mismatch"})
    assert response.status_code == 200, response.text
    notices = await _got(db_session, student_id, "it.application.updated")
    assert len(notices) == 1 and notices[0].title == "Job application updated"
    assert "reject" not in notices[0].body.lower()
    assert notices[0].entity_id == str(application_id)


# --- N4: result published: once, no result in the preview ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_published_result_is_notified_once_with_no_result_text(client, db_session, approval_required):  # noqa: F811
    recruiter, student, application = await _student_setup(client, db_session)
    student_id = student.id
    item = await _decide(client, db_session, recruiter, application.id)
    await login(client, await _hr_manager(db_session))
    _page, row = await _queue_row(client, item["id"])
    message = f"Congratulations {uuid.uuid4().hex[:6]}"
    assert (await _release(client, row["id"], message)).status_code == 200
    notices = await _got(db_session, student_id, "it.interview.result_published")
    assert len(notices) == 1 and notices[0].title == "Interview result"
    assert message not in notices[0].body and "congratulations" not in notices[0].body.lower()
    assert (await _release(client, row["id"], message)).status_code == 409
    assert len(await _got(db_session, student_id, "it.interview.result_published")) == 1


# --- N6: the feedback-overdue sweep ----------------------------------------------------------------------------------------------------
async def _only_this_interview(db, interview_id):
    await db.execute(update(Interview).where(Interview.id != interview_id, Interview.overdue_notified_at.is_(None)).values(overdue_notified_at=datetime.now(UTC)))
    await db.commit()


async def _overdue_world(client, db, *, hours=30):
    s = await _setup(client, db)
    item = await _interview(client, s["application"]["id"])
    interview_id = uuid.UUID(item["id"])
    await db.execute(update(Interview).where(Interview.id == interview_id).values(scheduled_at=datetime.now(UTC) - timedelta(hours=hours), ends_at=None))
    await db.commit()
    await _only_this_interview(db, interview_id)
    return s, interview_id


@pytest.mark.asyncio
async def test_overdue_feedback_tells_the_owner_once_and_stamps_the_interview(client, db_session):
    s, interview_id = await _overdue_world(client, db_session)
    recruiter_id = s["recruiter"].id
    first = await recruitment_notices.run_feedback_overdue()
    assert first == {"interviews": 1}
    notices = await _got(db_session, recruiter_id, "it.interview.feedback_overdue")
    assert len(notices) == 1 and notices[0].entity_id == str(interview_id) and notices[0].action_url == "/recruiter/interviews"
    assert await db_session.scalar(select(Interview.overdue_notified_at).where(Interview.id == interview_id).execution_options(populate_existing=True)) is not None
    assert await recruitment_notices.run_feedback_overdue() == {"interviews": 0}
    assert len(await _got(db_session, recruiter_id, "it.interview.feedback_overdue")) == 1


@pytest.mark.asyncio
async def test_panel_members_who_owe_feedback_are_told_and_who_gave_it_are_not(client, db_session):
    s, interview_id = await _overdue_world(client, db_session)
    owes = await make_user(db_session, "interviewer", "it")
    gave = await make_user(db_session, "interviewer", "it")
    owes_id, gave_id = owes.id, gave.id
    for person in (owes, gave):
        db_session.add(InterviewInterviewer(interview_id=interview_id, user_id=person.id, kind="internal", assigned_by_user_id=s["recruiter"].id))
    db_session.add(InterviewPanelFeedback(interview_id=interview_id, interviewer_user_id=gave.id, attendance="no_show"))
    await db_session.commit()
    await recruitment_notices.run_feedback_overdue()
    assert len(await _got(db_session, owes_id, "it.interview.feedback_overdue")) == 1
    assert await _got(db_session, gave_id, "it.interview.feedback_overdue") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("hours", "status"), [(2, "scheduled"), (30, "cancelled"), (30, "on_hold")])
async def test_not_overdue_within_the_grace_period_or_when_closed(client, db_session, hours, status):
    s, interview_id = await _overdue_world(client, db_session, hours=hours)
    await db_session.execute(update(Interview).where(Interview.id == interview_id).values(status=status, cancel_reason="Called off" if status == "cancelled" else None))
    await db_session.commit()
    assert await recruitment_notices.run_feedback_overdue() == {"interviews": 0}
    assert await _got(db_session, s["recruiter"].id, "it.interview.feedback_overdue") == []


@pytest.mark.asyncio
async def test_recorded_feedback_is_not_overdue(client, db_session):
    s, interview_id = await _overdue_world(client, db_session)
    db_session.add(InterviewFeedback(interview_id=interview_id, overall_rating=4, recorded_by_user_id=s["recruiter"].id))
    await db_session.commit()
    assert await recruitment_notices.run_feedback_overdue() == {"interviews": 0}


@pytest.mark.asyncio
async def test_the_sweep_is_bounded(client, db_session, monkeypatch):
    s, interview_id = await _overdue_world(client, db_session)
    second = await _interview(client, s["application"]["id"], scheduled_at=(datetime.now(UTC) + timedelta(days=9)).isoformat())
    await db_session.execute(update(Interview).where(Interview.id == uuid.UUID(second["id"])).values(scheduled_at=datetime.now(UTC) - timedelta(hours=40), overdue_notified_at=None))
    await db_session.commit()
    monkeypatch.setattr(recruitment_notices, "SWEEP_LIMIT", 1)
    assert await recruitment_notices.run_feedback_overdue() == {"interviews": 1}
    assert await recruitment_notices.run_feedback_overdue() == {"interviews": 1}  # the next run takes the rest
    assert await recruitment_notices.run_feedback_overdue() == {"interviews": 0}


# --- N7/N12: new matching vacancy -----------------------------------------------------------------------------------------------------
async def _only_this_job(db, job_id):
    await db.execute(update(Job).where(Job.id != job_id, Job.match_notified_at.is_(None)).values(match_notified_at=datetime.now(UTC)))
    await db.commit()


async def _match_setup(client, db, *, opted_in=True, **job_fields):
    w = await _match_world(client, db)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 1)], work_mode="remote", **job_fields)
    user = await make_user(db, "it_student", "it")
    await w.candidate(java, user_id=user.id, opted_in=opted_in, preferred_role="Java Developer")
    await db.execute(update(Job).where(Job.id == job.id).values(match_notified_at=None))
    await db.commit()
    await _only_this_job(db, job.id)
    return w, job, user


@pytest.mark.asyncio
async def test_a_new_match_tells_the_candidate_once(client, db_session):
    _w, job, user = await _match_setup(client, db_session)
    user_id, job_id = user.id, job.id
    assert await recruitment_notices.run_new_matches() == {"jobs": 1, "candidates": 1}
    notices = await _got(db_session, user_id, "it.job.new_match")
    assert len(notices) == 1 and notices[0].entity_id == str(job_id) and notices[0].action_url == "/it/student/jobs"
    assert await recruitment_notices.run_new_matches() == {"jobs": 0, "candidates": 0}
    assert len(await _got(db_session, user_id, "it.job.new_match")) == 1


@pytest.mark.asyncio
async def test_a_new_match_respects_consent(client, db_session):
    _w, _job, user = await _match_setup(client, db_session, opted_in=False)
    assert (await recruitment_notices.run_new_matches())["candidates"] == 0
    assert await _got(db_session, user.id, "it.job.new_match") == []


@pytest.mark.asyncio
async def test_a_new_match_uses_only_email_without_a_channel_opt_in_and_adds_whatsapp_with_one(client, db_session):
    _w, _job, user = await _match_setup(client, db_session)
    db_session.add(NotificationPreference(user_id=user.id, whatsapp_opt_in=True))
    await db_session.commit()
    await recruitment_notices.run_new_matches()
    note = (await _got(db_session, user.id, "it.job.new_match"))[0]
    channels = (await db_session.scalars(select(NotificationDelivery.channel).where(NotificationDelivery.notification_id == note.id))).all()
    assert sorted(channels) == ["email", "whatsapp"]


@pytest.mark.asyncio
async def test_an_internal_job_tells_nobody_and_is_not_stamped(client, db_session):
    _w, job, user = await _match_setup(client, db_session, visibility="internal")
    await db_session.refresh(job)
    job_id = job.id
    assert await recruitment_notices.run_new_matches() == {"jobs": 0, "candidates": 0}
    assert await _got(db_session, user.id, "it.job.new_match") == []
    assert await db_session.scalar(select(Job.match_notified_at).where(Job.id == job_id).execution_options(populate_existing=True)) is None


@pytest.mark.asyncio
async def test_someone_who_already_applied_is_not_told(client, db_session):
    _w, job, user = await _match_setup(client, db_session)
    await student_application(db_session, job.id, user, status="sourced")
    await db_session.commit()
    assert (await recruitment_notices.run_new_matches())["candidates"] == 0
    assert await _got(db_session, user.id, "it.job.new_match") == []


@pytest.mark.asyncio
async def test_a_candidate_who_misses_the_jobs_skills_is_not_told(client, db_session):
    w, _job, _user = await _match_setup(client, db_session)
    rust = await w.skill("Rust")
    other = await make_user(db_session, "it_student", "it")
    await w.candidate(rust, user_id=other.id, opted_in=True)
    await db_session.commit()
    await recruitment_notices.run_new_matches()
    assert await _got(db_session, other.id, "it.job.new_match") == []


@pytest.mark.asyncio
async def test_a_job_with_no_scored_skills_is_stamped_and_tells_nobody(client, db_session):
    w = await _match_world(client, db_session)
    job = await w.requirement(work_mode="remote")
    await db_session.execute(update(Job).where(Job.id == job.id).values(match_notified_at=None))
    await db_session.commit()
    await _only_this_job(db_session, job.id)
    assert await recruitment_notices.run_new_matches() == {"jobs": 1, "candidates": 0}


@pytest.mark.asyncio
async def test_the_application_owner_is_not_lost_when_the_job_primary_differs(client, db_session):
    """The overdue notice goes to the application's owner; the job's primary only when the application has none."""
    s, _interview_id = await _overdue_world(client, db_session)
    other = await make_user(db_session, "placement_team", "it")
    other_id, recruiter_id = other.id, s["recruiter"].id
    await db_session.execute(update(JobApplication).where(JobApplication.id == uuid.UUID(s["application"]["id"])).values(owner_user_id=other.id))
    await db_session.commit()
    await recruitment_notices.run_feedback_overdue()
    assert len(await _got(db_session, other_id, "it.interview.feedback_overdue")) == 1
    assert await _got(db_session, recruiter_id, "it.interview.feedback_overdue") == []
