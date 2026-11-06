"""hrc-031 (DEC-SCOPE-412, spec docs/superpowers/specs/2026-11-06-hrc-031-candidate-portal-completion-design.md): every §11 section reads the
caller's own records in both portals -- applications with their date and next action (P2/P3), interviews, documents with no pool gate for a
candidate (P4), offers (P6), notices that open a page the recipient can reach (P7) and the student's new sections (P9). Someone else's record
answers 404; staff are refused. The shared test database is never truncated, so every assertion is about this test's own rows."""

from datetime import date

import pytest
from sqlalchemy import event, func, select, update

from app.core.database import engine
from app.models import Candidate, JobApplication, JobOffer, Notification
from app.services import applications, offers
from app.services import portal as portal_svc
from tests.rec001_helpers import login, make_user
from tests.rec017_helpers import student_application
from tests.test_hrc_015_documents import ACCOUNT, BASE, PNG, _post_doc, queued  # noqa: F401
from tests.test_rec_017_tracking import _requirement, _team
from tests.test_rec_020_interviews import _interview, _move, _to_past, published  # noqa: F401

pytestmark = pytest.mark.asyncio
ROLES = ("candidate", "it_student")
APPLICATIONS = "/api/v1/candidate/applications"
INTERVIEWS = "/api/v1/candidate/interviews"
RESULTS = "/api/v1/candidate/results"
OFFERS = "/api/v1/workflows/it/student/offers"
NOTICES = "/api/v1/workflows/notifications"


async def _seeker(client, db, role):
    """A signed-in candidate or student with one Shortlisted application; returns the recruiter too (not signed in)."""
    _, recruiter = await _team(client, db)
    job = await _requirement(db, recruiter)
    user = await make_user(db, role, "it")
    application = await student_application(db, job.id, user, status="shortlisted")
    await db.commit()
    await login(client, user)
    return recruiter, user, job, application


def _row(payload: dict, application) -> dict:
    return next(r for r in payload["rows"] if r["code"] == application.application_code)


@pytest.mark.parametrize("role", ROLES)
async def test_applications_show_the_visible_stage_the_date_and_the_next_action(client, db_session, role):
    _, _user, job, application = await _seeker(client, db_session, role)
    response = await client.get(APPLICATIONS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [c["key"] for c in body["columns"]] == ["code", "role", "company", "location", "status", "applied_on", "next_action"]
    assert len(body["rows"]) == 1  # only the caller's
    row = _row(body, application)
    assert row["role"] == job.title and row["status"] == "Shortlisted" and row["next_action"] == portal_svc.NO_ACTION
    assert date.today().strftime("%Y") in row["applied_on"]
    assert not {"candidate_id", "owner_user_id", "rejection_reason", "student_id"} & set(row)  # the allow-list


async def test_next_action_rules():
    upcoming = "12 Nov 2026, 10:00 AM IST (UTC+05:30)"
    assert portal_svc.next_action("interview", upcoming, False) == f"Attend your interview: {upcoming}"
    assert portal_svc.next_action("interview", None, False) == portal_svc.AWAIT_INTERVIEW
    assert portal_svc.next_action("selected", None, True) == portal_svc.REVIEW_OFFER
    assert portal_svc.next_action("selected", None, False) == portal_svc.AWAIT_OFFER
    for closed in ("rejected", "withdrawn", "joined"):  # a leftover interview or offer asks nothing of them any more
        assert portal_svc.next_action(closed, upcoming, True) == portal_svc.NO_ACTION
    assert portal_svc.next_action("sourced", None, False) == portal_svc.NO_ACTION


@pytest.mark.parametrize("role", ROLES)
async def test_an_upcoming_interview_is_the_next_action_and_an_unreleased_decision_stays_hidden(client, db_session, published, role):  # noqa: F811
    recruiter, user, _job, application = await _seeker(client, db_session, role)
    await login(client, recruiter)
    item = await _interview(client, application.id, round="final_round")
    await login(client, user)
    row = _row((await client.get(APPLICATIONS)).json(), application)
    assert row["next_action"].startswith("Attend your interview: ") and row["status"] == "Interview"
    listed = (await client.get(INTERVIEWS)).json()
    assert [r["round"] for r in listed["rows"]] == ["Final Round"]
    assert {c["key"] for c in listed["columns"]} >= {"round", "when", "link", "status"}

    await login(client, recruiter)
    await _to_past(db_session, item["id"])
    assert (await _move(client, item["id"], "completed")).status_code == 200
    assert (await _move(client, item["id"], "selected")).status_code == 200  # waits for approval: nothing moves for the candidate
    await login(client, user)
    row = _row((await client.get(APPLICATIONS)).json(), application)
    assert row["status"] == "Interview" and row["next_action"] == portal_svc.AWAIT_INTERVIEW
    assert (await client.get(INTERVIEWS)).json()["rows"][0]["status"] == "Completed"
    assert (await client.get(RESULTS)).json()["items"] == []
    for path in (APPLICATIONS, INTERVIEWS, RESULTS):
        assert "Selected" not in (await client.get(path)).text


@pytest.mark.parametrize("role", ROLES)
async def test_an_offer_is_readable_and_is_the_next_action(client, db_session, role):
    _, user, job, application = await _seeker(client, db_session, role)
    application.status = application.candidate_status = "selected"
    offer = JobOffer(application_id=application.id, position=job.title, status="offer_received", offered_on=date.today())
    db_session.add(offer)
    await db_session.commit()
    assert _row((await client.get(APPLICATIONS)).json(), application)["next_action"] == portal_svc.REVIEW_OFFER
    response = await client.get(OFFERS)
    assert response.status_code == 200, response.text
    assert [i["id"] for i in response.json()["items"]] == [str(offer.id)]


@pytest.mark.parametrize("role", ROLES)
async def test_another_persons_records_answer_404_and_never_appear(client, db_session, role):
    _, owner, job, application = await _seeker(client, db_session, role)
    application.status = application.candidate_status = "selected"
    offer = JobOffer(application_id=application.id, position=job.title, status="offer_received", offered_on=date.today())
    notice = Notification(user_id=owner.id, title="Private notice", body="Only the owner", read=False)
    db_session.add_all((offer, notice))
    await db_session.commit()
    owner_candidate = await db_session.scalar(select(Candidate).where(Candidate.user_id == owner.id))
    owner_candidate.opted_in = True
    await db_session.commit()

    other = await make_user(db_session, role, "it")
    await login(client, other)
    for path in (APPLICATIONS, INTERVIEWS):
        assert (await client.get(path)).json()["rows"] == []
    assert (await client.get(RESULTS)).json()["items"] == []
    assert (await client.get(OFFERS)).json()["items"] == []
    assert "Private notice" not in (await client.get(NOTICES)).text
    assert (await client.get(f"{OFFERS}/{offer.id}/letter")).status_code == 404
    assert (await client.patch(f"{NOTICES}/{notice.id}/read")).status_code == 404
    assert (await client.get(f"{ACCOUNT}/{offer.id}/link")).status_code == 404


async def test_staff_cannot_read_the_portal_sections(client, db_session):
    recruiter = await make_user(db_session, "placement_team", "it")
    await db_session.commit()
    await login(client, recruiter)
    for path in (APPLICATIONS, INTERVIEWS, RESULTS, OFFERS, ACCOUNT):
        assert (await client.get(path)).status_code == 403, path


async def test_the_query_count_does_not_grow_with_the_applications(client, db_session):
    async def statements(path) -> int:
        seen: list[str] = []
        listener = lambda *args: seen.append(args[2])  # noqa: E731 -- (conn, cursor, statement, ...)
        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            assert (await client.get(path)).status_code == 200
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        return len(seen)

    recruiter, user, _job, _application = await _seeker(client, db_session, "candidate")
    small = await statements(APPLICATIONS), await statements(INTERVIEWS)
    for _ in range(3):
        job = await _requirement(db_session, recruiter)
        await student_application(db_session, job.id, user, status="shortlisted")
    await db_session.commit()
    assert (await statements(APPLICATIONS), await statements(INTERVIEWS)) == small


async def test_a_candidate_works_their_documents_without_the_pool(client, db_session, queued):  # noqa: F811
    """P4: leaving the pool keeps the applications, so it keeps what was asked for them; a student still needs the pool (hrc-015 D8)."""
    recruiter, user, _job, _application = await _seeker(client, db_session, "candidate")
    candidate = await db_session.scalar(select(Candidate).where(Candidate.user_id == user.id))
    candidate_id = candidate.id
    await db_session.execute(update(Candidate).where(Candidate.id == candidate_id).values(opted_in=True, owner_user_id=recruiter.id))
    await db_session.commit()
    await login(client, recruiter)
    asked = await client.post(f"{BASE}/{candidate_id}/document-requests", json={"document_type": "certificate", "note": "Your degree"})
    assert asked.status_code == 201, asked.text
    await db_session.execute(update(Candidate).where(Candidate.id == candidate_id).values(opted_in=False))  # then they leave the pool
    await db_session.commit()
    await login(client, user)
    body = (await client.get(ACCOUNT)).json()
    assert body["available"] is True and [r["document_type"] for r in body["requests"]] == ["certificate"]
    made = await _post_doc(client, ACCOUNT, PNG, document_type="certificate", request_id=asked.json()["id"])
    assert made.status_code == 201, made.text
    body = (await client.get(ACCOUNT)).json()
    assert body["requests"][0]["status"] == "received" and body["documents"][0]["uploaded_by"] == "you"
    link = await client.get(f"{ACCOUNT}/{made.json()['id']}/link")
    assert link.status_code == 200, link.text


async def test_a_student_outside_the_pool_still_has_no_documents(client, db_session):
    _, user, _job, _application = await _seeker(client, db_session, "it_student")
    await db_session.execute(update(Candidate).where(Candidate.user_id == user.id).values(opted_in=False))
    await db_session.commit()
    assert (await client.get(ACCOUNT)).json() == {"available": False, "requests": [], "documents": []}


async def test_an_archived_candidate_has_no_documents(client, db_session):
    _, user, _job, _application = await _seeker(client, db_session, "candidate")
    await db_session.execute(update(Candidate).where(Candidate.user_id == user.id).values(archived_at=func.now()))
    await db_session.commit()
    assert (await client.get(ACCOUNT)).json()["available"] is False


@pytest.mark.parametrize(("role", "applications_url", "interviews_url", "offers_url"), [
    ("candidate", "/it/careers/portal/applications", "/it/careers/portal/interviews", "/it/careers/portal/applications"),
    ("it_student", "/it/student/job-applications", "/it/student/job-applications", "/it/student/placement-status"),
])  # fmt: skip
async def test_notices_open_a_page_the_recipient_can_reach(client, db_session, published, role, applications_url, interviews_url, offers_url):  # noqa: F811
    recruiter, user, _job, application = await _seeker(client, db_session, role)
    user_id, application_id = user.id, application.id
    await login(client, recruiter)
    await _interview(client, application_id, notify=True)
    application = await db_session.get(JobApplication, application_id, populate_existing=True)
    await applications._notify(db_session, application, "Interview result", "Message")
    await offers._notify_received(db_session, application)
    await db_session.commit()
    rows = (await db_session.scalars(select(Notification).where(Notification.user_id == user_id))).all()
    by_title = {n.title: n.action_url for n in rows}
    assert by_title["Interview scheduled"] == interviews_url
    assert by_title["Interview result"] == applications_url and by_title["Job offer received"] == offers_url


@pytest.mark.parametrize("role", ROLES)
async def test_qa_the_tables_stack_on_a_phone_and_a_candidate_is_not_told_of_mock_interviews(client, db_session, role):
    await _seeker(client, db_session, role)
    assert (await client.get(APPLICATIONS)).json()["stack"] is True
    interviews = (await client.get(INTERVIEWS)).json()
    assert interviews["stack"] is True and "Mock" not in interviews["subtitle"]
    if role == "it_student":
        for section in ("job-applications", "interview-schedule"):
            assert (await client.get(f"/api/v1/portal/it/student/{section}")).json()["stack"] is True


@pytest.mark.parametrize(("section", "title"), [("results", "My Results"), ("documents", "Documents"), ("privacy", "Privacy")])
async def test_a_student_has_the_new_sections(client, db_session, section, title):
    _, _user, _job, _application = await _seeker(client, db_session, "it_student")
    response = await client.get(f"/api/v1/portal/it/student/{section}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == title and body["rows"] == [] and "locked" not in body


async def test_a_student_table_carries_the_date_and_next_action_and_notifications_offer_preferences(client, db_session):
    _, _user, _job, application = await _seeker(client, db_session, "it_student")
    body = (await client.get("/api/v1/portal/it/student/job-applications")).json()
    assert [c["key"] for c in body["columns"]][-2:] == ["applied_on", "next_action"]
    assert _row(body, application)["next_action"] == portal_svc.NO_ACTION
    assert body["panels"][0]["title"] == "Open jobs"  # unchanged
    notices = (await client.get("/api/v1/portal/it/student/notifications")).json()
    assert {"label": "Notification preferences", "href": "/account/profile"} in notices["actions"]
