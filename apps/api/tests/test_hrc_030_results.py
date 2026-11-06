"""hrc-030 -- result approval and release (DEC-SCOPE-409 R1-R11; AC1-AC4): a decision becomes a result that waits for a `results.release`
holder, the candidate sees nothing of it until it is published (application stage, results, interview card, notices, offers), auto-release
publishes at once and only the right candidate sees it. The shared test database is never truncated, so every value is unique per test;
the global setting is restored after each test that changes it."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AuditLog, InterviewResult, Notification, RecruiterMessage, ResultReleaseSetting, User
from tests.rec001_helpers import login, make_user
from tests.test_hrc_028_interviews import _student_setup
from tests.test_rec_020_interviews import INTERVIEWS, _app_status, _interview, _move, _setup, _to_past, published, smtp_on  # noqa: F401

RESULTS = "/api/v1/recruiter/interview-results"
MINE = "/api/v1/candidate/results"
SCHEDULE = "/api/v1/portal/it/student/interview-schedule"
APPLICATIONS = "/api/v1/portal/it/student/job-applications"
NOTICE = "Interview result"


@pytest_asyncio.fixture
async def auto_release(db_session):
    """Turns auto-release on for one test and puts the stored value back."""
    row = await db_session.get(ResultReleaseSetting, 1)
    before = row.auto_release if row else None
    if row is None:
        row = ResultReleaseSetting(id=1, auto_release=True)
        db_session.add(row)
    row.auto_release = True
    await db_session.commit()
    yield
    row = await db_session.get(ResultReleaseSetting, 1, populate_existing=True)
    row.auto_release = bool(before)
    await db_session.commit()


@pytest_asyncio.fixture
async def approval_required(db_session):
    """The default (approval), made explicit so a leftover value from an interrupted run cannot change the outcome."""
    row = await db_session.get(ResultReleaseSetting, 1)
    if row is None:
        db_session.add(ResultReleaseSetting(id=1, auto_release=False))
    else:
        row.auto_release = False
    await db_session.commit()


async def _decide(client, db, recruiter, application_id, decision="selected", round_="final_round") -> dict:
    await login(client, recruiter)
    item = await _interview(client, application_id, round=round_)
    await _to_past(db, item["id"])
    assert (await _move(client, item["id"], "completed")).status_code == 200
    response = await _move(client, item["id"], decision)
    assert response.status_code == 200, response.text
    return response.json()["interview"]


async def _student_view(client, student) -> str:
    """Everything the student's portal and APIs say, as one text."""
    await login(client, student)
    parts = []
    for path in (SCHEDULE, APPLICATIONS, MINE, "/api/v1/workflows/notifications", "/api/v1/workflows/it/student/offers"):
        response = await client.get(path)
        assert response.status_code == 200, (path, response.text)
        parts.append(response.text)
    return "\n".join(parts)


async def _notices(db, user) -> list[Notification]:
    return list((await db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.title == NOTICE))).all())


async def _hr_manager(db) -> User:
    return await make_user(db, "hr_manager", "it")


async def _queue_row(client, interview_id) -> tuple[dict, dict]:
    """The page's counts and this interview's row -- paged, since the shared database keeps older waiting results ahead of it."""
    offset = 0
    while True:
        page = (await client.get(f"{RESULTS}?limit=100&offset={offset}")).json()
        row = next((r for r in page["items"] if r["interview"]["id"] == interview_id), None)
        if row is not None or offset + 100 >= page["total"]:
            return page, row
        offset += 100


async def _release(client, result_id, message=None):
    return await client.post(f"{RESULTS}/{result_id}/release", json={} if message is None else {"candidate_message": message})


# --- AC1: approval required -- invisible until published ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_decision_waits_for_approval_and_the_candidate_sees_nothing(client, db_session, approval_required):
    recruiter, student, application = await _student_setup(client, db_session)
    item = await _decide(client, db_session, recruiter, application.id)
    assert item["result_release"]["state"] == "pending_approval" and item["result_release"]["outcome"] == "selected" and item["result_release"]["is_final"] is True
    assert item["application"]["status"] == "selected"  # staff flows move as before (R3)
    assert "result" in item and item["result"] is None  # the legacy `result` field is kept as it was
    assert (await client.post(f"/api/v1/recruiter/applications/{application.id}/offer", json={"position": "Engineer"})).status_code == 409
    seen = await _student_view(client, student)
    assert "Selected" not in seen and "Congratulations" not in seen
    rows = (await client.get(APPLICATIONS)).json()["rows"]
    assert [r["status"] for r in rows] == ["Interview"]
    assert (await client.get(MINE)).json() == {"items": []}
    assert await _notices(db_session, student) == []


@pytest.mark.asyncio
async def test_publishing_shows_the_result_to_the_candidate_once_and_is_final(client, db_session, approval_required):
    recruiter, student, application = await _student_setup(client, db_session)
    item = await _decide(client, db_session, recruiter, application.id)
    approver = await _hr_manager(db_session)
    await login(client, approver)
    queue, row = await _queue_row(client, item["id"])
    assert row["can_release"] is True and row["state"] == "pending_approval" and "Congratulations" in row["candidate_message"]
    assert queue["counts"]["pending_approval"] >= 1
    message = "Well done -- the team will call you about joining."
    released = await _release(client, row["id"], message)
    assert released.status_code == 200, released.text
    assert (released.json()["state"], released.json()["release_mode"], released.json()["candidate_message"]) == ("released", "approval", message)
    assert (await _release(client, row["id"], "again")).status_code == 409  # R7: final
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "interview_result.release", AuditLog.entity_id == row["id"]))
    assert audit is not None and message not in str(audit.metadata_json)
    await login(client, student)
    assert [r["status"] for r in (await client.get(APPLICATIONS)).json()["rows"]] == ["Selected"]
    mine = (await client.get(MINE)).json()["items"]
    assert [(r["outcome_label"], r["message"]) for r in mine] == [("Selected", message)]
    assert any(r["status"] == "Selected" for r in (await client.get(SCHEDULE)).json()["rows"])
    notices = await _notices(db_session, student)
    assert len(notices) == 1 and message not in notices[0].body  # hrc-032 (N4): the message is in My results, not the preview
    await login(client, recruiter)
    assert (await client.get(f"{INTERVIEWS}/{item['id']}")).json()["result_release"]["state"] == "released"
    offer = await client.post(f"/api/v1/recruiter/applications/{application.id}/offer", json={"position": "Engineer"})
    assert offer.status_code == 201, offer.text


@pytest.mark.asyncio
async def test_a_blank_message_publishes_the_default_text(client, db_session, approval_required):
    recruiter, student, application = await _student_setup(client, db_session)
    item = await _decide(client, db_session, recruiter, application.id, decision="rejected")
    await login(client, await _hr_manager(db_session))
    result_id = item["result_release"]["id"]
    released = await _release(client, result_id, "   ")
    assert released.status_code == 200 and released.json()["candidate_message"].startswith("Thank you for interviewing")
    await login(client, student)
    assert [r["outcome_label"] for r in (await client.get(MINE)).json()["items"]] == ["Not selected"]
    assert [r["status"] for r in (await client.get(APPLICATIONS)).json()["rows"]] == ["Rejected"]


# --- AC2: auto-release --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_release_publishes_immediately(client, db_session, auto_release):
    recruiter, student, application = await _student_setup(client, db_session)
    item = await _decide(client, db_session, recruiter, application.id)
    assert (item["result_release"]["state"], item["result_release"]["release_mode"]) == ("released", "auto")
    await login(client, student)
    assert [r["status"] for r in (await client.get(APPLICATIONS)).json()["rows"]] == ["Selected"]
    assert len((await client.get(MINE)).json()["items"]) == 1
    assert len(await _notices(db_session, student)) == 1


# --- AC3: only the right candidate --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_only_the_right_candidate_sees_the_result(client, db_session, auto_release):
    recruiter, student, application = await _student_setup(client, db_session)
    await _decide(client, db_session, recruiter, application.id)
    other = await make_user(db_session, "it_student", "it")
    await login(client, other)
    assert (await client.get(MINE)).json() == {"items": []}
    await login(client, recruiter)
    assert (await client.get(MINE)).status_code == 403


# --- AC4: who publishes, and the setting -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_only_release_holders_read_the_queue_and_publish_and_never_their_own_decision(client, db_session, approval_required):
    recruiter, _student, application = await _student_setup(client, db_session)
    item = await _decide(client, db_session, recruiter, application.id, decision="rejected")
    result_id = item["result_release"]["id"]
    assert (await client.get(RESULTS)).status_code == 403
    assert (await _release(client, result_id)).status_code == 403
    admin = await make_user(db_session, "super_admin", "it")
    await login(client, admin)
    other = await _decide(client, db_session, admin, (await _student_setup(client, db_session))[2].id, decision="rejected")
    _, own = await _queue_row(client, other["id"])
    assert own["can_release"] is False
    assert (await _release(client, other["result_release"]["id"])).status_code == 403
    assert (await client.post(f"{RESULTS}/00000000-0000-0000-0000-000000000000/release", json={})).status_code == 404
    await login(client, await _hr_manager(db_session))
    assert (await _release(client, result_id)).status_code == 200


@pytest.mark.asyncio
async def test_the_setting_is_read_by_holders_and_changed_by_super_admin_only(client, db_session, approval_required):
    await login(client, await _hr_manager(db_session))
    assert (await client.get(f"{RESULTS}/settings")).json() == {"auto_release": False, "can_edit": False}
    assert (await client.put(f"{RESULTS}/settings", json={"auto_release": True})).status_code == 403
    await login(client, await make_user(db_session, "super_admin", "it"))
    saved = await client.put(f"{RESULTS}/settings", json={"auto_release": True})
    assert saved.status_code == 200 and saved.json()["auto_release"] is True
    assert (await client.put(f"{RESULTS}/settings", json={"auto_release": False})).json()["auto_release"] is False
    assert (await client.put(f"{RESULTS}/settings", json={"auto_release": "x"})).status_code == 422


# --- R1/R3: which decisions are final; the other paths --------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_earlier_round_selected_is_a_round_result_that_leaves_the_application(client, db_session, approval_required):
    recruiter, student, application = await _student_setup(client, db_session)
    item = await _decide(client, db_session, recruiter, application.id, round_="hr_round")
    assert item["result_release"]["is_final"] is False and "cleared the HR Round" in item["result_release"]["candidate_message"]
    await login(client, await _hr_manager(db_session))
    assert (await _release(client, item["result_release"]["id"])).status_code == 200
    await login(client, student)
    assert [r["status"] for r in (await client.get(APPLICATIONS)).json()["rows"]] == ["Interview"]
    assert [r["outcome_label"] for r in (await client.get(MINE)).json()["items"]] == ["Selected"]


@pytest.mark.asyncio
async def test_a_feedback_decision_records_a_result(client, db_session, approval_required):
    recruiter, student, application = await _student_setup(client, db_session)
    await login(client, recruiter)
    item = await _interview(client, application.id, round="final_round")
    await _to_past(db_session, item["id"])
    await _move(client, item["id"], "completed")
    body = {"technical_rating": 4, "communication_rating": 4, "overall_rating": 4, "strengths": "Java", "weaknesses": None, "recruiter_comments": None,
            "company_feedback": None, "next_round": None, "final_decision": "rejected"}  # fmt: skip
    saved = await client.put(f"{INTERVIEWS}/{item['id']}/feedback", json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["interview"]["result_release"]["state"] == "pending_approval"
    await login(client, student)
    assert [r["status"] for r in (await client.get(APPLICATIONS)).json()["rows"]] == ["Interview"]


@pytest.mark.asyncio
async def test_the_legacy_result_patch_records_a_result_and_holds_the_candidate_view(client, db_session, approval_required):
    recruiter, student, application = await _student_setup(client, db_session)
    await login(client, recruiter)
    item = await _interview(client, application.id, round="final_round")
    await _to_past(db_session, item["id"])
    await _move(client, item["id"], "completed")
    patched = await client.patch(f"/api/v1/workflows/it/interviews/{item['id']}", json={"result": "selected"})
    assert patched.status_code == 200 and patched.json()["status"] == "selected"
    result = await db_session.scalar(select(InterviewResult).where(InterviewResult.interview_id == item["id"]))
    assert result is not None and result.state == "pending_approval"
    assert await _app_status(db_session, application.id) == "selected"
    await login(client, student)
    assert [r["status"] for r in (await client.get(APPLICATIONS)).json()["rows"]] == ["Interview"]


@pytest.mark.asyncio
async def test_a_candidate_without_a_login_gets_a_queued_email_on_release(client, db_session, approval_required, smtp_on, published):  # noqa: F811
    s = await _setup(client, db_session)
    item = await _decide(client, db_session, s["recruiter"], s["application"]["id"], decision="rejected")
    await login(client, await _hr_manager(db_session))
    assert (await _release(client, item["result_release"]["id"], "Thanks for your time.")).status_code == 200
    mail = await db_session.scalar(select(RecruiterMessage).where(RecruiterMessage.candidate_id == s["candidate"].id, RecruiterMessage.subject.like(f"{NOTICE}%")))
    assert mail is not None and "Thanks for your time." in mail.body and str(mail.id) in published


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(RESULTS)).status_code == 401
    assert (await client.get(MINE)).status_code == 401
