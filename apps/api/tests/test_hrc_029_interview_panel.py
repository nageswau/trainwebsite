"""hrc-029 -- the interview panel (DEC-SCOPE-405 V1-V11; AC1-AC6): assigning internal interviewers and employer users, the panel member's
own interviews, the resume shared with them, their feedback, the recruiter's view of it and the candidate never seeing it. The shared test
database is never truncated, so every value is unique per test."""

import uuid

import pytest
from sqlalchemy import select, update

from app.core.security import hash_password
from app.models import AuditLog, CandidateResume, Company, EmployerProfile, Notification, User
from app.services import candidates as candidate_svc
from tests.rec001_helpers import login, make_user
from tests.test_hrc_028_interviews import _student_setup
from tests.test_rec_020_interviews import INTERVIEWS, _interview, _move, _setup, _to_past

MINE = "/api/v1/interviewer/interviews"
PDF = b"%PDF-1.4 hrc-029 resume"


def _tag() -> str:
    return uuid.uuid4().hex[:8]


async def _employer(db, company_id, *, active=True) -> User:
    user = User(email=f"emp-{_tag()}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"), full_name=f"Employer {_tag()}", role="employer",
                division="it", active=active)  # fmt: skip
    db.add(user)
    await db.flush()
    db.add(EmployerProfile(user_id=user.id, company_id=company_id, registration_status=None))
    await db.commit()
    return user


async def _other_company(db) -> Company:
    company = Company(name=f"Other Co {_tag()}")
    db.add(company)
    await db.commit()
    return company


async def _resume(db, candidate_id, uploader_id, version=1) -> CandidateResume:
    item = CandidateResume(candidate_id=candidate_id, version=version, storage_key=candidate_svc.store(PDF, "application/pdf"), content_type="application/pdf",
                           file_name="cv.pdf", size_bytes=len(PDF), uploaded_by_user_id=uploader_id)  # fmt: skip
    db.add(item)
    await db.commit()
    return item


async def _assign(client, interview_id, *members):
    """members: users, the first one the lead"""
    body = {"interviewers": [{"user_id": str(u.id), "is_lead": n == 0} for n, u in enumerate(members)]}
    return await client.put(f"{INTERVIEWS}/{interview_id}/interviewers", json=body)


async def _world(client, db):
    s = await _setup(client, db)
    interviewer = await make_user(db, "interviewer", "it", name=f"Asha {_tag()}")
    employer = await _employer(db, s["job"].company_id)
    await login(client, s["recruiter"])
    s["item"] = await _interview(client, s["application"]["id"])
    return s | {"interviewer": interviewer, "employer": employer}


def _feedback(**over) -> dict:
    return {"attendance": "attended", "score": 4, "recommendation": "yes", "notes": "Solid Java answers"} | over


# --- V2/V3: assigning the panel --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_options_list_internal_interviewers_and_only_this_companys_active_employers(client, db_session):
    s = await _world(client, db_session)
    stranger = await _employer(db_session, (await _other_company(db_session)).id)
    gone = await _employer(db_session, s["job"].company_id, active=False)
    await login(client, s["recruiter"])
    response = await client.get(f"{INTERVIEWS}/{s['item']['id']}/interviewer-options")
    assert response.status_code == 200, response.text
    kinds = {o["id"]: o["kind"] for o in response.json()["items"]}
    assert kinds[str(s["interviewer"].id)] == "internal" and kinds[str(s["employer"].id)] == "employer"
    assert str(stranger.id) not in kinds and str(gone.id) not in kinds


@pytest.mark.asyncio
async def test_a_writer_assigns_the_panel_lead_first_and_each_new_member_is_notified(client, db_session):
    s = await _world(client, db_session)
    response = await _assign(client, s["item"]["id"], s["employer"], s["interviewer"])
    assert response.status_code == 200, response.text
    body = response.json()["interview"]
    panel = [(m["id"], m["kind"], m["is_lead"], m["feedback"]) for m in body["interviewers"]]
    assert panel == [(str(s["employer"].id), "employer", True, None), (str(s["interviewer"].id), "internal", False, None)] and body["can_assign"]
    notes = (await db_session.scalars(select(Notification).where(Notification.user_id.in_([s["employer"].id, s["interviewer"].id])))).all()
    assert sorted(n.action_url for n in notes) == ["/it/employer/dashboard", "/it/interviewer/dashboard"]
    assert all(n.title == "Interview assigned" and s["candidate"].candidate_code in n.body for n in notes)
    # re-saving with a new lead notifies nobody again
    response = await _assign(client, s["item"]["id"], s["interviewer"], s["employer"])
    assert [m["is_lead"] for m in response.json()["interview"]["interviewers"]] == [True, False]
    assert await db_session.scalar(select(Notification.id).where(Notification.user_id == s["interviewer"].id).offset(1)) is None
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "recruiter_interview.interviewers", AuditLog.entity_id == s["item"]["id"]))).all()
    assert len(audit) == 2


@pytest.mark.asyncio
async def test_ineligible_people_are_422(client, db_session):
    s = await _world(client, db_session)
    stranger = await _employer(db_session, (await _other_company(db_session)).id)
    student = await make_user(db_session, "it_student", "it")
    await login(client, s["recruiter"])
    for person in (stranger, student):
        response = await _assign(client, s["item"]["id"], person)
        assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == "interviewers"


@pytest.mark.asyncio
async def test_two_leads_or_a_repeat_are_422(client, db_session):
    s = await _world(client, db_session)
    member = {"user_id": str(s["interviewer"].id), "is_lead": True}
    for people in ([member, {"user_id": str(s["employer"].id), "is_lead": True}], [member, member]):
        response = await client.put(f"{INTERVIEWS}/{s['item']['id']}/interviewers", json={"interviewers": people})
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_cancelled_interview_panel_cannot_change(client, db_session):
    s = await _world(client, db_session)
    assert (await client.post(f"{INTERVIEWS}/{s['item']['id']}/cancel", json={"reason": "Panel away", "notify": False})).status_code == 200
    assert (await _assign(client, s["item"]["id"], s["interviewer"])).status_code == 409


@pytest.mark.asyncio
async def test_the_manager_reads_the_panel_but_cannot_assign(client, db_session):
    s = await _world(client, db_session)
    await _assign(client, s["item"]["id"], s["interviewer"])
    await login(client, s["manager"])
    assert (await _assign(client, s["item"]["id"], s["interviewer"])).status_code == 403
    assert (await client.get(f"{INTERVIEWS}/{s['item']['id']}/interviewer-options")).status_code == 403
    read = (await client.get(f"{INTERVIEWS}/{s['item']['id']}")).json()
    assert [m["id"] for m in read["interviewers"]] == [str(s["interviewer"].id)] and read["can_assign"] is False


# --- V6: the panel member's own interviews (AC4) -----------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_interviewer_sees_only_assigned_interviews_and_no_contact_or_salary(client, db_session):
    s = await _world(client, db_session)
    await _assign(client, s["item"]["id"], s["interviewer"])
    await login(client, s["interviewer"])
    page = (await client.get(MINE)).json()
    assert [i["id"] for i in page["items"]] == [s["item"]["id"]] and page["counts"] == {"upcoming": 1, "past": 0}
    item = page["items"][0]
    assert item["candidate"]["code"] == s["candidate"].candidate_code and item["can_feedback"] is False and item["feedback"] is None
    assert not {"mobile", "email", "linkedin", "current_salary", "expected_salary"} & set(item["candidate"])
    assert "interviewers" not in item and "contact" not in item
    other = await make_user(db_session, "interviewer", "it")
    await login(client, other)
    assert (await client.get(MINE)).json()["items"] == []
    assert (await client.get(f"{MINE}/{s['item']['id']}")).status_code == 404
    assert (await client.put(f"{MINE}/{s['item']['id']}/feedback", json=_feedback())).status_code == 404
    assert (await client.get(f"{MINE}/{s['item']['id']}/resume")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["it_student", "placement_team", "hr_team"])
async def test_other_roles_are_403(client, db_session, role):
    user = await make_user(db_session, role, "it")
    await login(client, user)
    assert (await client.get(MINE)).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(MINE)).status_code == 401


@pytest.mark.asyncio
async def test_an_employer_who_left_the_company_loses_the_interview(client, db_session):
    s = await _world(client, db_session)
    await _assign(client, s["item"]["id"], s["employer"])
    await login(client, s["employer"])
    assert (await client.get(f"{MINE}/{s['item']['id']}")).status_code == 200
    moved = await _other_company(db_session)
    await db_session.execute(update(EmployerProfile).where(EmployerProfile.user_id == s["employer"].id).values(company_id=moved.id))
    await db_session.commit()
    assert (await client.get(f"{MINE}/{s['item']['id']}")).status_code == 404


# --- V7/V8: feedback (AC1, AC2) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_feedback_waits_for_the_interview_time_then_the_recruiter_sees_it_and_nothing_moves(client, db_session):
    s = await _world(client, db_session)
    await _assign(client, s["item"]["id"], s["interviewer"], s["employer"])
    await login(client, s["interviewer"])
    response = await client.put(f"{MINE}/{s['item']['id']}/feedback", json=_feedback())
    assert response.status_code == 409 and "time has passed" in response.json()["detail"]
    await _to_past(db_session, s["item"]["id"])
    response = await client.put(f"{MINE}/{s['item']['id']}/feedback", json=_feedback())
    assert response.status_code == 200, response.text
    mine = response.json()
    assert mine["feedback"]["recommendation_label"] == "Recommend" and mine["feedback"]["score"] == 4 and mine["can_feedback"]
    await login(client, s["employer"])
    employer_view = (await client.get(f"{MINE}/{s['item']['id']}")).json()
    assert employer_view["feedback"] is None and employer_view["feedback_overdue"] is False  # held under 24 h ago
    await login(client, s["recruiter"])
    read = (await client.get(f"{INTERVIEWS}/{s['item']['id']}")).json()
    by = {m["id"]: m["feedback"] for m in read["interviewers"]}
    assert by[str(s["interviewer"].id)]["notes"] == "Solid Java answers" and by[str(s["employer"].id)] is None
    assert read["status"] == "scheduled" and read["feedback"] is None  # advisory: rec-021's feedback and the status are untouched
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "interviewer.feedback", AuditLog.entity_id == s["item"]["id"]))
    assert set(audit.metadata_json["fields"]) == {"attendance", "score", "recommendation", "notes"}
    assert "Solid Java" not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_attended_needs_a_score_and_a_recommendation_and_a_no_show_clears_them(client, db_session):
    s = await _world(client, db_session)
    await _assign(client, s["item"]["id"], s["interviewer"])
    await _to_past(db_session, s["item"]["id"])
    await login(client, s["interviewer"])
    response = await client.put(f"{MINE}/{s['item']['id']}/feedback", json={"attendance": "attended"})
    assert response.status_code == 422 and {e["loc"][-1] for e in response.json()["detail"]} == {"score", "recommendation"}
    response = await client.put(f"{MINE}/{s['item']['id']}/feedback", json=_feedback(attendance="no_show"))
    assert response.status_code == 200, response.text
    assert (response.json()["feedback"]["score"], response.json()["feedback"]["recommendation"], response.json()["feedback"]["attendance_label"]) == (None, None, "No-show")
    assert (await client.put(f"{MINE}/{s['item']['id']}/feedback", json=_feedback(score=6))).status_code == 422


@pytest.mark.asyncio
async def test_overdue_after_24_hours_without_feedback(client, db_session):
    s = await _world(client, db_session)
    await _assign(client, s["item"]["id"], s["interviewer"])
    await _to_past(db_session, s["item"]["id"], hours=30)
    await login(client, s["interviewer"])
    item = (await client.get(MINE, params={"view": "past"})).json()["items"][0]
    assert item["feedback_overdue"] is True and item["can_feedback"] is True


@pytest.mark.asyncio
async def test_a_decided_or_cancelled_interview_takes_no_feedback(client, db_session):
    s = await _world(client, db_session)
    await _assign(client, s["item"]["id"], s["interviewer"])
    await _to_past(db_session, s["item"]["id"])
    assert (await _move(client, s["item"]["id"], "completed")).status_code == 200
    assert (await _move(client, s["item"]["id"], "rejected")).status_code == 200
    await login(client, s["interviewer"])
    response = await client.put(f"{MINE}/{s['item']['id']}/feedback", json=_feedback())
    assert response.status_code == 409
    item = (await client.get(f"{MINE}/{s['item']['id']}")).json()
    assert item["status"] == "completed" and item["can_feedback"] is False  # hrc-001 H3: the decision is not released to the panel


@pytest.mark.asyncio
async def test_a_member_with_feedback_cannot_be_removed(client, db_session):
    s = await _world(client, db_session)
    await _assign(client, s["item"]["id"], s["interviewer"], s["employer"])
    await _to_past(db_session, s["item"]["id"])
    await login(client, s["interviewer"])
    await client.put(f"{MINE}/{s['item']['id']}/feedback", json=_feedback())
    await login(client, s["recruiter"])
    assert (await _assign(client, s["item"]["id"], s["employer"])).status_code == 409
    assert (await _assign(client, s["item"]["id"], s["interviewer"])).status_code == 200  # the employer had none


# --- V4/V5: the resume (AC6) -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_resume_shared_at_assignment_downloads_audited_and_a_later_version_is_not_shared(client, db_session):
    s = await _world(client, db_session)
    first = await _resume(db_session, s["candidate"].id, s["recruiter"].id)
    await _assign(client, s["item"]["id"], s["interviewer"])
    await _resume(db_session, s["candidate"].id, s["recruiter"].id, version=2)
    await login(client, s["interviewer"])
    assert (await client.get(f"{MINE}/{s['item']['id']}")).json()["has_resume"] is True
    response = await client.get(f"{MINE}/{s['item']['id']}/resume")
    assert response.status_code == 200 and response.content == PDF
    assert response.headers["content-disposition"].startswith("attachment") and response.headers["cache-control"] == "private, no-store"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "interviewer.resume_download", AuditLog.entity_id == s["item"]["id"]))
    assert audit.user_id == s["interviewer"].id and audit.metadata_json["resume_id"] == str(first.id) and audit.metadata_json["version"] == 1


@pytest.mark.asyncio
async def test_no_resume_or_outside_the_window_is_404(client, db_session):
    s = await _world(client, db_session)
    await _assign(client, s["item"]["id"], s["interviewer"])
    await login(client, s["interviewer"])
    assert (await client.get(f"{MINE}/{s['item']['id']}")).json()["has_resume"] is False
    assert (await client.get(f"{MINE}/{s['item']['id']}/resume")).status_code == 404
    t = await _world(client, db_session)
    await _resume(db_session, t["candidate"].id, t["recruiter"].id)
    await _assign(client, t["item"]["id"], t["interviewer"])
    await _to_past(db_session, t["item"]["id"], hours=24 * 8 + 2)
    await login(client, t["interviewer"])
    assert (await client.get(f"{MINE}/{t['item']['id']}/resume")).status_code == 404
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.action == "interviewer.resume_download", AuditLog.entity_id == t["item"]["id"])) is None


# --- V11: the candidate never sees it (AC3) -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_panel_feedback_never_reaches_the_student_or_the_employer_list(client, db_session):
    recruiter, student, application = await _student_setup(client, db_session)
    interviewer = await make_user(db_session, "interviewer", "it")
    await login(client, recruiter)
    item = await _interview(client, application.id)
    await _assign(client, item["id"], interviewer)
    await _to_past(db_session, item["id"])
    secret = f"LEAK-{_tag()}"
    await login(client, interviewer)
    assert (await client.put(f"{MINE}/{item['id']}/feedback", json=_feedback(notes=secret, recommendation="strong_no"))).status_code == 200
    await login(client, student)
    for path in ("/api/v1/portal/it/student/interview-schedule", "/api/v1/portal/it/student/job-applications", "/api/v1/workflows/notifications"):
        response = await client.get(path)
        assert response.status_code == 200, (path, response.text)
        assert secret not in response.text and "strong_no" not in response.text and "Strongly do not" not in response.text
    assert (await client.get(MINE)).status_code == 403
