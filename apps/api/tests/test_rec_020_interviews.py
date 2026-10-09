"""rec-020 -- interview management (spec §1-§3; AC1, AC2; DEC-SCOPE-148 IV1-IV12). The shared test database is never truncated, so every
value is unique per test; a "past" interview is made by moving its time back in the database (the API refuses a past time)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.models import AuditLog, Company, CompanyContact, Interview, InterviewEvent, JobApplication, Notification, RecruiterMessage
from app.services import interviews as svc
from tests.rec001_helpers import as_role, login, make_recruiter, make_user
from tests.rec017_helpers import student_application
from tests.test_rec_017_tracking import _add, _candidate, _requirement, _tag, _team

INTERVIEWS = "/api/v1/recruiter/interviews"
APPS = "/api/v1/recruiter/applications"


def _at(days: float = 2, minute: int = 0) -> str:
    when = (datetime.now(UTC) + timedelta(days=days)).replace(second=0, microsecond=0, minute=minute)
    return when.isoformat().replace("+00:00", "Z")


@pytest.fixture
def smtp_on(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from_email", "noreply@edusphere.local")


@pytest.fixture
def published(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr("app.api.recruiter_interviews.enqueue_recruiter_email", lambda message_id: sent.append(str(message_id)) or True)
    return sent


async def _setup(client, db, *, status="requirement_received"):
    manager, recruiter = await _team(client, db)
    job = await _requirement(db, recruiter, status=status)
    candidate = await _candidate(db, recruiter)
    application = (await _add(client, job, candidate)).json()["application"]
    return {"manager": manager, "recruiter": recruiter, "job": job, "candidate": candidate, "application": application}


async def _schedule(client, application_id, **over):
    body = {"application_id": str(application_id), "round": "hr_round", "scheduled_at": _at(), "mode": "Online", "notify": False} | over
    return await client.post(INTERVIEWS, json=body)


async def _interview(client, application_id, **over) -> dict:
    response = await _schedule(client, application_id, **over)
    assert response.status_code == 201, response.text
    return response.json()["interview"]


async def _to_past(db, interview_id, hours=1):
    await db.execute(update(Interview).where(Interview.id == interview_id).values(scheduled_at=datetime.now(UTC) - timedelta(hours=hours)))
    await db.commit()


async def _move(client, interview_id, status, note=None):
    return await client.post(f"{INTERVIEWS}/{interview_id}/status", json={"status": status, **({"note": note} if note else {})})


async def _app_status(db, application_id) -> str:
    return await db.scalar(select(JobApplication.status).where(JobApplication.id == application_id).execution_options(populate_existing=True))


# --- the catalogue (IV1-IV3) --------------------------------------------------------------------------------------------------------
def test_catalogue_matches_section_14():
    assert list(svc.ROUND_LABELS) == ["hr_round", "technical_round", "manager_round", "final_round", "client_round"]
    assert list(svc.STATUS_LABELS) == ["scheduled", "confirmed", "completed", "rescheduled", "no_show", "selected", "rejected", "on_hold"]
    assert svc.OPEN == ("scheduled", "confirmed", "rescheduled")
    assert svc.MOVES == {
        "confirmed": ("scheduled", "rescheduled"),
        "completed": svc.OPEN,
        "no_show": svc.OPEN,
        "on_hold": (*svc.OPEN, "completed"),
        "selected": ("completed", "on_hold"),
        "rejected": ("completed", "on_hold"),
    }


# --- schedule (IV5-IV8) -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_schedule_creates_a_coded_interview_with_history_and_moves_the_application_and_company(client, db_session):
    s = await _setup(client, db_session)
    when = _at(3)
    response = await _schedule(client, s["application"]["id"], scheduled_at=when, interviewer="Meera (HR)", location="Pune office",
                               meeting_url="https://meet.example.com/x")
    assert response.status_code == 201, response.text
    body = response.json()
    item = body["interview"]
    assert item["code"].startswith("INT-") and len(item["code"]) >= 10
    assert (item["round"], item["round_label"], item["status"], item["status_label"]) == ("hr_round", "HR Round", "scheduled", "Scheduled")
    assert (item["interviewer"], item["location"], item["meeting_url"], item["mode"]) == ("Meera (HR)", "Pune office", "https://meet.example.com/x", "Online")
    assert item["candidate"]["id"] == str(s["candidate"].id) and item["requirement"]["id"] == str(s["job"].id)
    assert item["application"]["status"] == "interview"
    assert [(h["event"], h["to_status"]) for h in item["history"]] == [("scheduled", "scheduled")]
    assert {m["key"] for m in item["allowed_statuses"]} == {"confirmed", "on_hold"}  # completed / no_show wait for the time (AC2)
    assert item["can_edit"] and item["can_reschedule"]
    assert body["notifications"] == {"candidate": "off", "contact": None}
    assert await _app_status(db_session, s["application"]["id"]) == "interview"
    company = await db_session.scalar(select(Company).where(Company.id == s["job"].company_id).execution_options(populate_existing=True))
    assert company.stage == "interview"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_interview.create", AuditLog.entity_id == item["id"]))
    assert audit is not None and "Meera" not in str(audit.metadata_json)


@pytest.mark.asyncio
@pytest.mark.parametrize("when, message", [(-1, "future"), (400, "12 months")])
async def test_schedule_in_the_past_or_too_far_is_422_on_the_field(client, db_session, when, message):
    s = await _setup(client, db_session)
    response = await _schedule(client, s["application"]["id"], scheduled_at=_at(when))
    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"][-1] == "scheduled_at" and message in error["msg"]


@pytest.mark.asyncio
async def test_schedule_needs_a_round_a_known_mode_and_an_http_link(client, db_session):
    s = await _setup(client, db_session)
    assert (await _schedule(client, s["application"]["id"], round=None)).status_code == 422
    assert (await _schedule(client, s["application"]["id"], round="lunch_round")).status_code == 422
    assert (await _schedule(client, s["application"]["id"], mode="Carrier pigeon")).status_code == 422
    assert (await _schedule(client, s["application"]["id"], meeting_url="javascript:alert(1)")).status_code == 422
    assert (await _schedule(client, s["application"]["id"], status="confirmed")).status_code == 422  # server-owned


@pytest.mark.asyncio
async def test_multiple_rounds_on_one_application_and_one_day_are_allowed(client, db_session):
    s = await _setup(client, db_session)
    hr = await _interview(client, s["application"]["id"], scheduled_at=_at(2, 0))
    tech = await _interview(client, s["application"]["id"], round="technical_round", scheduled_at=_at(2, 30))
    assert hr["code"] != tech["code"] and tech["round_label"] == "Technical Round"
    listed = (await client.get(f"{APPS}/{s['application']['id']}/interviews")).json()
    assert [i["id"] for i in listed["items"]] == [tech["id"], hr["id"]] and listed["can_schedule"] is True


@pytest.mark.asyncio
async def test_same_candidate_same_time_is_409_across_requirements(client, db_session):
    s = await _setup(client, db_session)
    other_job = await _requirement(db_session, s["recruiter"])
    other = (await _add(client, other_job, s["candidate"])).json()["application"]
    when = _at(4)
    await _interview(client, s["application"]["id"], scheduled_at=when)
    clash = await _schedule(client, other["id"], scheduled_at=when)
    assert clash.status_code == 409 and "already has an interview" in clash.json()["detail"]
    assert (await _schedule(client, other["id"], scheduled_at=_at(4, 15))).status_code == 201


@pytest.mark.asyncio
async def test_a_closed_requirement_or_a_finished_application_cannot_be_scheduled(client, db_session):
    s = await _setup(client, db_session)
    assert (await client.post(f"{APPS}/{s['application']['id']}/status", json={"status": "rejected"})).status_code == 200
    refused = await _schedule(client, s["application"]["id"])
    assert refused.status_code == 409 and "open application" in refused.json()["detail"]
    listed = (await client.get(f"{APPS}/{s['application']['id']}/interviews")).json()
    assert listed["can_schedule"] is False
    t = await _setup(client, db_session)
    t["job"].status = "closed"
    await db_session.commit()
    assert (await _schedule(client, t["application"]["id"])).status_code == 409


@pytest.mark.asyncio
async def test_contact_must_be_an_active_contact_of_the_requirements_company(client, db_session):
    s = await _setup(client, db_session)
    other = Company(name=f"Other Co {_tag()}")
    db_session.add(other)
    await db_session.flush()
    foreign = CompanyContact(company_id=other.id, name="Elsewhere", email=f"{_tag()}@example.com")
    own = CompanyContact(company_id=s["job"].company_id, name=f"Priya {_tag()}", email=f"{_tag()}@example.com")
    db_session.add_all([foreign, own])
    await db_session.commit()
    bad = await _schedule(client, s["application"]["id"], contact_id=str(foreign.id))
    assert bad.status_code == 422 and bad.json()["detail"][0]["loc"][-1] == "contact_id"
    good = await _interview(client, s["application"]["id"], contact_id=str(own.id))
    assert good["contact"] == {"id": str(own.id), "name": own.name}


# --- reschedule (IV4, AC1) ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_a_rescheduled_interview_keeps_history(client, db_session):
    s = await _setup(client, db_session)
    first, second = _at(2), _at(5)
    item = await _interview(client, s["application"]["id"], scheduled_at=first)
    response = await client.post(f"{INTERVIEWS}/{item['id']}/reschedule", json={"scheduled_at": second, "reason": "Panel unavailable", "notify": False})
    assert response.status_code == 200, response.text
    moved = response.json()["interview"]
    assert moved["status"] == "rescheduled" and moved["scheduled_at"].startswith(second[:16])
    latest = moved["history"][-1]
    assert (latest["event"], latest["from_status"], latest["to_status"], latest["note"]) == ("rescheduled", "scheduled", "rescheduled", "Panel unavailable")
    assert latest["old_scheduled_at"].startswith(first[:16]) and latest["new_scheduled_at"].startswith(second[:16])
    assert latest["actor"]["id"] == str(s["recruiter"].id)
    same = await client.post(f"{INTERVIEWS}/{item['id']}/reschedule", json={"scheduled_at": second})
    assert same.status_code == 422 and same.json()["detail"][0]["loc"][-1] == "scheduled_at"
    past = await client.post(f"{INTERVIEWS}/{item['id']}/reschedule", json={"scheduled_at": _at(-1)})
    assert past.status_code == 422


@pytest.mark.asyncio
async def test_reschedule_into_another_interview_of_the_candidate_is_409(client, db_session):
    s = await _setup(client, db_session)
    taken = _at(6)
    await _interview(client, s["application"]["id"], scheduled_at=taken)
    other = await _interview(client, s["application"]["id"], round="technical_round", scheduled_at=_at(7))
    clash = await client.post(f"{INTERVIEWS}/{other['id']}/reschedule", json={"scheduled_at": taken})
    assert clash.status_code == 409


@pytest.mark.asyncio
async def test_a_no_show_or_on_hold_interview_can_be_rescheduled_but_a_decided_one_cannot(client, db_session):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    await _to_past(db_session, item["id"])
    assert (await _move(client, item["id"], "no_show")).status_code == 200
    again = await client.post(f"{INTERVIEWS}/{item['id']}/reschedule", json={"scheduled_at": _at(3)})
    assert again.status_code == 200 and again.json()["interview"]["status"] == "rescheduled"
    await _to_past(db_session, item["id"])
    assert (await _move(client, item["id"], "completed")).status_code == 200
    assert (await _move(client, item["id"], "rejected")).status_code == 200
    refused = await client.post(f"{INTERVIEWS}/{item['id']}/reschedule", json={"scheduled_at": _at(3)})
    assert refused.status_code == 409


# --- statuses (IV3, AC2) and the side effects (IV8) ---------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["no_show", "completed"])
async def test_ac2_no_show_and_completed_only_after_the_scheduled_time(client, db_session, target):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    early = await _move(client, item["id"], target)
    assert early.status_code == 422 and "time has passed" in early.json()["detail"]
    await _to_past(db_session, item["id"])
    late = await _move(client, item["id"], target, note="Checked with the panel")
    assert late.status_code == 200, late.text
    assert late.json()["interview"]["history"][-1] == late.json()["interview"]["history"][-1] | {"event": "status", "from_status": "scheduled", "to_status": target, "note": "Checked with the panel"}


@pytest.mark.asyncio
async def test_moves_follow_the_table(client, db_session):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    assert (await _move(client, item["id"], "selected")).status_code == 409
    confirmed = await _move(client, item["id"], "confirmed")
    assert confirmed.status_code == 200 and confirmed.json()["interview"]["status_label"] == "Confirmed"
    assert (await _move(client, item["id"], "confirmed")).status_code == 409
    assert (await _move(client, item["id"], "on_hold")).status_code == 200
    assert (await _move(client, item["id"], "scheduled")).status_code == 422  # never chosen
    await _to_past(db_session, item["id"])
    held = (await client.get(f"{INTERVIEWS}/{item['id']}")).json()
    assert {m["key"] for m in held["allowed_statuses"]} == {"selected", "rejected"}


@pytest.mark.asyncio
async def test_hr_round_selected_keeps_the_application_at_interview_then_technical_round(client, db_session):
    s = await _setup(client, db_session)
    hr = await _interview(client, s["application"]["id"])
    await _to_past(db_session, hr["id"])
    await _move(client, hr["id"], "completed")
    passed = await _move(client, hr["id"], "selected")
    assert passed.status_code == 200 and passed.json()["interview"]["allowed_statuses"] == []
    assert not passed.json()["interview"]["can_edit"] and not passed.json()["interview"]["can_reschedule"]
    assert await _app_status(db_session, s["application"]["id"]) == "interview"
    tech = await _interview(client, s["application"]["id"], round="technical_round")
    assert tech["application"]["status"] == "interview"


@pytest.mark.asyncio
@pytest.mark.parametrize("round_, decision, expected", [("final_round", "selected", "selected"), ("client_round", "selected", "selected"),
                                                         ("hr_round", "rejected", "rejected"), ("final_round", "rejected", "rejected")])
async def test_decisions_feed_the_application(client, db_session, round_, decision, expected):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"], round=round_)
    await _to_past(db_session, item["id"])
    await _move(client, item["id"], "completed")
    response = await _move(client, item["id"], decision)
    assert response.status_code == 200
    assert response.json()["interview"]["application"]["status"] == expected
    assert await _app_status(db_session, s["application"]["id"]) == expected


@pytest.mark.asyncio
async def test_edit_changes_details_only_and_never_a_decided_interview(client, db_session):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    edited = await client.patch(f"{INTERVIEWS}/{item['id']}", json={"interviewer": "Ravi", "round": "manager_round", "location": None})
    assert edited.status_code == 200 and (edited.json()["interviewer"], edited.json()["round"]) == ("Ravi", "manager_round")
    assert (await client.patch(f"{INTERVIEWS}/{item['id']}", json={"scheduled_at": _at(9)})).status_code == 422
    assert (await client.patch(f"{INTERVIEWS}/{item['id']}", json={"round": None})).status_code == 422
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_interview.update", AuditLog.entity_id == item["id"]))
    assert audit.metadata_json == {"fields": ["interviewer", "round"]}
    await _to_past(db_session, item["id"])
    await _move(client, item["id"], "completed")
    await _move(client, item["id"], "rejected")
    assert (await client.patch(f"{INTERVIEWS}/{item['id']}", json={"interviewer": "Late"})).status_code == 409


# --- who (IV10) ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_reads_but_cannot_write_and_another_recruiter_gets_404(client, db_session):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    await login(client, s["manager"])
    read = await client.get(f"{INTERVIEWS}/{item['id']}")
    assert read.status_code == 200 and read.json()["allowed_statuses"] == [] and not read.json()["can_edit"]
    assert (await _move(client, item["id"], "confirmed")).status_code == 403
    assert (await _schedule(client, s["application"]["id"])).status_code == 403
    stranger = await make_recruiter(db_session, s["manager"])
    await login(client, stranger)
    assert (await client.get(f"{INTERVIEWS}/{item['id']}")).status_code == 404
    assert (await _move(client, item["id"], "confirmed")).status_code == 404
    assert (await _schedule(client, s["application"]["id"])).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("hr_team", "it"), ("it_admin", "it"), ("employer", "it"), ("it_student", "it")])
async def test_other_roles_are_refused(client, db_session, role, division):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    await as_role(client, db_session, role, division)
    assert (await client.get(INTERVIEWS)).status_code == 403
    assert (await client.get(f"{INTERVIEWS}/{item['id']}")).status_code == 403
    assert (await _schedule(client, s["application"]["id"])).status_code == 403


# --- notifications (IV9) ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_schedule_emails_an_external_candidate_and_the_contact_after_the_commit(client, db_session, smtp_on, published):
    s = await _setup(client, db_session)
    contact = CompanyContact(company_id=s["job"].company_id, name=f"Priya {_tag()}", email=f"{_tag()}@example.com")
    db_session.add(contact)
    await db_session.commit()
    response = await _schedule(client, s["application"]["id"], contact_id=str(contact.id), notify=True, meeting_url="https://meet.example.com/y")
    assert response.status_code == 201, response.text
    assert response.json()["notifications"] == {"candidate": "queued", "contact": "queued"}
    rows = (await db_session.scalars(select(RecruiterMessage).where(RecruiterMessage.id.in_(published)))).all()
    assert len(rows) == 2 and {r.delivery_status for r in rows} == {"queued"}
    to_contact = next(r for r in rows if r.contact_id == contact.id)
    assert s["candidate"].name in to_contact.body and s["candidate"].candidate_code in to_contact.body
    assert s["candidate"].email not in to_contact.body  # R8: never the candidate's contact details
    to_candidate = next(r for r in rows if r.candidate_id == s["candidate"].id)
    assert "https://meet.example.com/y" in to_candidate.body and "HR Round" in to_candidate.subject
    moved = await client.post(f"{INTERVIEWS}/{response.json()['interview']['id']}/reschedule", json={"scheduled_at": _at(6)})
    assert moved.json()["notifications"] == {"candidate": "queued", "contact": "queued"} and len(published) == 4


@pytest.mark.asyncio
async def test_without_smtp_or_an_address_the_interview_is_still_saved(client, db_session, published):
    s = await _setup(client, db_session)
    response = await _schedule(client, s["application"]["id"], notify=True)
    assert response.status_code == 201 and response.json()["notifications"] == {"candidate": "email_off", "contact": None}
    assert published == []


@pytest.mark.asyncio
async def test_a_student_candidate_gets_the_in_app_notification(client, db_session, published, smtp_on):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    student = await make_user(db_session, "it_student", "it")
    application = await student_application(db_session, job.id, student, status="shortlisted")
    await db_session.commit()
    response = await _schedule(client, application.id, notify=True)
    assert response.status_code == 201, response.text
    assert response.json()["notifications"]["candidate"] == "in_app" and published == []
    note = await db_session.scalar(select(Notification).where(Notification.user_id == student.id, Notification.title == "Interview scheduled"))
    assert note is not None and "HR Round" in note.body


# --- lists (IV12) -------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_views_and_counts(client, db_session):
    recruiter = await make_recruiter(db_session, None)
    await login(client, recruiter)
    job = await _requirement(db_session, recruiter)
    apps = [(await _add(client, job, await _candidate(db_session, recruiter))).json()["application"] for _ in range(4)]
    upcoming = await _interview(client, apps[0]["id"])
    awaiting = await _interview(client, apps[1]["id"])
    held = await _interview(client, apps[2]["id"])
    closed = await _interview(client, apps[3]["id"])
    for item in (awaiting, closed):
        await _to_past(db_session, item["id"])
    await _move(client, held["id"], "on_hold")
    await _move(client, closed["id"], "no_show")
    page = (await client.get(INTERVIEWS, params={"view": "upcoming"})).json()
    assert page["counts"] == {"upcoming": 1, "awaiting_update": 1, "on_hold": 1, "closed": 1}
    assert [i["id"] for i in page["items"]] == [upcoming["id"]]
    for view, item in (("awaiting_update", awaiting), ("on_hold", held), ("closed", closed)):
        assert [i["id"] for i in (await client.get(INTERVIEWS, params={"view": view})).json()["items"]] == [item["id"]]
    assert (await client.get(INTERVIEWS, params={"view": "someday"})).status_code == 422


# --- the legacy routes (IV11, AC3) --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_legacy_staff_routes_get_a_code_history_and_the_clash(client, db_session):
    s = await _setup(client, db_session)
    await as_role(client, db_session, "hr_team", "it")
    when = "2031-03-01T10:00:00+00:00"
    created = await client.post("/api/v1/workflows/it/interviews", json={"application_id": s["application"]["id"], "scheduled_at": when})
    assert created.status_code == 201, created.text
    interview_id = created.json()["id"]
    assert created.json()["code"].startswith("INT-")
    clash = await client.post("/api/v1/workflows/it/interviews", json={"application_id": s["application"]["id"], "scheduled_at": when})
    assert clash.status_code == 409
    moved = await client.patch(f"/api/v1/workflows/it/interviews/{interview_id}", json={"scheduled_at": "2031-03-02T10:00:00+00:00"})
    assert moved.status_code == 200
    decided = await client.patch(f"/api/v1/workflows/it/interviews/{interview_id}", json={"result": "on_hold"})
    assert decided.status_code == 200 and decided.json()["result"] == "on_hold"
    events = (await db_session.scalars(select(InterviewEvent).where(InterviewEvent.interview_id == interview_id).order_by(InterviewEvent.position))).all()
    assert [(e.event, e.to_status) for e in events] == [("scheduled", "scheduled"), ("rescheduled", "rescheduled"), ("status", "on_hold")]
    stored = await db_session.scalar(select(Interview).where(Interview.id == interview_id).execution_options(populate_existing=True))
    assert stored.status == "on_hold" and stored.round is None
