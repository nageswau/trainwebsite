"""rec-024 -- recruiter follow-ups (spec §1-§3; DEC-SCOPE-131 FU1-FU10): create, the company's list, the Today / Overdue / Upcoming lists,
edit / reschedule, complete, cancel, links, the cap and the derived next follow-up. The shared test database is never truncated, so every
list assertion uses a recruiter created by the test."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Job, RecruiterFollowUp
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import IST
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user
from tests.rec017_helpers import student_application

COMPANIES = "/api/v1/recruiter/companies"
FOLLOW_UPS = "/api/v1/recruiter/follow-ups"


def soon(**delta) -> str:
    return (datetime.now(UTC) + (timedelta(**delta) if delta else timedelta(days=1))).isoformat()


def fu_url(fu_id, action: str = "") -> str:
    return f"{FOLLOW_UPS}/{fu_id}{'/' + action if action else ''}"


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _company(client, **body) -> dict:
    response = await client.post(COMPANIES, json={"name": f"FU {uuid.uuid4().hex[:8]} Pvt", **body})
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _create(client, company_id, **over):
    return await client.post(f"{COMPANIES}/{company_id}/follow-ups", json={"due_at": soon(), "reason": "jd"} | over)


async def _stored(db, company_id, creator, due_at, **over) -> RecruiterFollowUp:
    """Written straight to the database -- the only way to have one already due (the API refuses a past time)."""
    row = RecruiterFollowUp(company_id=uuid.UUID(company_id), due_at=due_at, reason="offer_status", created_by_user_id=creator.id, **over)
    db.add(row)
    await db.commit()
    return row


async def _job(db, company_id) -> Job:
    job = Job(company_id=uuid.UUID(company_id), title="Java Developer", location="Pune", description="Java", status="requirement_received")
    db.add(job)
    await db.commit()
    return job


# --- create (AC3, FU5, FU6) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recruiter_adds_a_follow_up_for_jd_due_tomorrow(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = (await client.post(f"{COMPANIES}/{company['id']}/contacts", json={"name": "Priya"})).json()["items"][0]
    response = await _create(client, company["id"], contact_id=contact["id"], notes="Ask for the JD\nfor Java roles")
    assert response.status_code == 201, response.text
    fu = response.json()
    assert fu["reason"] == "jd" and fu["status"] == "open" and fu["overdue"] is False and fu["can_change"] is True
    assert fu["company"]["id"] == company["id"] and fu["company"]["code"] == company["code"]
    assert fu["contact"] == {"id": contact["id"], "name": "Priya"} and fu["requirement"] is None
    assert fu["notes"] == "Ask for the JD\nfor Java roles"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == fu["id"], AuditLog.action == "recruiter_follow_up.create"))
    assert audit.metadata_json["reason"] == "jd" and "JD" not in str(audit.metadata_json)  # ids and keys only, never notes


@pytest.mark.asyncio
async def test_the_nine_source_reasons_are_accepted_and_others_refused(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    reasons = ["new_requirement", "jd", "profile_feedback", "interview_feedback", "offer_status", "joining_confirmation", "new_openings",
               "contract_mou", "payment_commercial"]
    for reason in reasons:
        assert (await _create(client, company["id"], reason=reason)).status_code == 201
    response = await _create(client, company["id"], reason="fee_details")
    assert response.status_code == 422 and response.json()["detail"][0]["loc"] == ["body", "reason"]


@pytest.mark.asyncio
async def test_a_due_time_in_the_past_or_too_far_is_422_on_the_field(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    for due in (soon(minutes=-5), soon(days=400)):
        response = await _create(client, company["id"], due_at=due)
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "due_at"]
    assert (await _create(client, company["id"], due_at="2026-11-01T10:00:00")).status_code == 422  # no offset
    assert (await _create(client, company["id"], status="done")).status_code == 422  # server-owned


@pytest.mark.asyncio
async def test_links_must_belong_to_the_company(client, db_session):
    await _team(client, db_session)
    company, other = await _company(client), await _company(client)
    foreign_contact = (await client.post(f"{COMPANIES}/{other['id']}/contacts", json={"name": "Ravi"})).json()["items"][0]
    response = await _create(client, company["id"], contact_id=foreign_contact["id"])
    assert response.status_code == 422 and response.json()["detail"] == "Choose an active contact of this company"
    job, foreign_job = await _job(db_session, company["id"]), await _job(db_session, other["id"])
    assert (await _create(client, company["id"], job_id=str(foreign_job.id))).status_code == 422
    student = await make_user(db_session, "it_student", "it")
    application = await student_application(db_session, job.id, student)
    foreign_application = await student_application(db_session, foreign_job.id, student)
    db_session.add_all([application, foreign_application])
    await db_session.commit()
    assert (await _create(client, company["id"], application_id=str(foreign_application.id))).status_code == 422
    response = await _create(client, company["id"], job_id=str(job.id), application_id=str(application.id))
    assert response.status_code == 201, response.text
    assert response.json()["requirement"] == {"id": str(job.id), "title": "Java Developer"}
    assert response.json()["application_id"] == str(application.id)
    other_job = await _job(db_session, company["id"])
    assert (await _create(client, company["id"], job_id=str(other_job.id), application_id=str(application.id))).status_code == 422


@pytest.mark.asyncio
async def test_an_inactive_contact_cannot_be_chosen(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    items = (await client.post(f"{COMPANIES}/{company['id']}/contacts", json={"name": "A"})).json()["items"]
    await client.patch(f"/api/v1/recruiter/contacts/{items[0]['id']}", json={"active": False})
    assert (await _create(client, company["id"], contact_id=items[0]["id"])).status_code == 422


@pytest.mark.asyncio
async def test_the_open_cap_is_50_per_company(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    for _ in range(50):
        await _stored(db_session, company["id"], recruiter, datetime.now(UTC) + timedelta(days=2))
    response = await _create(client, company["id"])
    assert response.status_code == 409 and "50 open follow-ups" in response.json()["detail"]


# --- roles and scope (FU3, FU4) -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_and_assigned_bdm_read_but_cannot_write(client, db_session):
    manager, _ = await _team(client, db_session)
    bdm = await make_user(db_session, "bdm", "it")
    company = await _company(client, assigned_bdm_user_id=str(bdm.id))
    fu = (await _create(client, company["id"])).json()
    for reader in (manager, bdm):
        await login(client, reader)
        page = (await client.get(f"{COMPANIES}/{company['id']}/follow-ups")).json()
        assert [i["id"] for i in page["items"]] == [fu["id"]] and page["items"][0]["can_change"] is False
        assert (await _create(client, company["id"])).status_code == 403
        assert (await client.patch(fu_url(fu["id"]), json={"notes": "x"})).status_code == 403
        assert (await client.post(fu_url(fu["id"], "complete"), json={})).status_code == 403
        assert (await client.post(fu_url(fu["id"], "cancel"), json={"reason": "x"})).status_code == 403


@pytest.mark.asyncio
async def test_another_recruiter_gets_404_and_other_roles_403(client, db_session):
    manager, _ = await _team(client, db_session)
    company = await _company(client)
    fu = (await _create(client, company["id"])).json()
    await login(client, await make_recruiter(db_session, manager))
    assert (await client.get(f"{COMPANIES}/{company['id']}/follow-ups")).status_code == 404
    assert (await _create(client, company["id"])).status_code == 404
    assert (await client.patch(fu_url(fu["id"]), json={"notes": "x"})).status_code == 404
    assert (await client.post(fu_url(fu["id"], "complete"), json={})).status_code == 404
    assert fu["id"] not in [i["id"] for i in (await client.get(f"{FOLLOW_UPS}?due=upcoming")).json()["items"]]
    await as_role(client, db_session, "hr_team", "it")
    assert (await client.get(f"{FOLLOW_UPS}?due=today")).status_code == 403
    assert (await client.get(f"{COMPANIES}/{company['id']}/follow-ups")).status_code == 403


@pytest.mark.asyncio
async def test_super_admin_writes(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    await as_role(client, db_session, "super_admin", "global")
    fu = await _create(client, company["id"])
    assert fu.status_code == 201 and fu.json()["can_change"] is True


@pytest.mark.asyncio
async def test_archived_company_follow_ups_are_read_only(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    fu = (await _create(client, company["id"])).json()
    await client.post(f"{COMPANIES}/{company['id']}/archive")
    assert (await client.get(f"{COMPANIES}/{company['id']}/follow-ups")).json()["items"][0]["can_change"] is False
    assert (await _create(client, company["id"])).status_code == 409
    assert (await client.post(fu_url(fu["id"], "complete"), json={})).status_code == 409


@pytest.mark.asyncio
async def test_reassignment_moves_open_follow_ups_with_the_company(client, db_session):
    manager, _ = await _team(client, db_session)
    company = await _company(client)
    fu = (await _create(client, company["id"])).json()
    other = await make_recruiter(db_session, manager)
    await login(client, manager)
    assert (await client.post(f"{COMPANIES}/{company['id']}/assign", json={"recruiter_user_id": str(other.id)})).status_code == 200
    await login(client, other)
    page = (await client.get(f"{FOLLOW_UPS}?due=upcoming")).json()
    assert [i["id"] for i in page["items"]] == [fu["id"]] and page["items"][0]["can_change"] is True


# --- the daily list (AC1, FU2) --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_today_is_due_today_plus_overdue_for_the_recruiter_only(client, db_session):
    manager, recruiter = await _team(client, db_session)
    company = await _company(client)
    now = datetime.now(UTC)
    _, end_of_today = day_range(now.astimezone(IST).date())
    overdue = await _stored(db_session, company["id"], recruiter, now - timedelta(days=3))
    later_today = await _stored(db_session, company["id"], recruiter, min(now + timedelta(minutes=1), end_of_today - timedelta(seconds=1)))
    tomorrow = await _stored(db_session, company["id"], recruiter, end_of_today + timedelta(hours=2))
    await _stored(db_session, company["id"], recruiter, now - timedelta(days=1), status="done", completed_at=now, completed_by_user_id=recruiter.id)
    # a colleague's follow-up, due today, never shows
    colleague = await make_recruiter(db_session, manager)
    await login(client, colleague)
    colleague_company = await _company(client)
    await _stored(db_session, colleague_company["id"], colleague, now - timedelta(hours=1))
    await login(client, recruiter)

    today = (await client.get(f"{FOLLOW_UPS}?due=today")).json()
    assert [i["id"] for i in today["items"]] == [str(overdue.id), str(later_today.id)]  # oldest due first
    assert today["items"][0]["overdue"] is True
    assert today["counts"] == {"today": 2, "overdue": today["counts"]["overdue"], "upcoming": 1}
    assert today["counts"]["overdue"] in (1, 2)  # later_today may already have passed when the window is tight
    assert today["day"] == now.astimezone(IST).date().isoformat()
    response = await client.get(f"{FOLLOW_UPS}?due=overdue")
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["id"] == str(overdue.id)
    upcoming = (await client.get(f"{FOLLOW_UPS}?due=upcoming")).json()
    assert [i["id"] for i in upcoming["items"]] == [str(tomorrow.id)]
    assert (await client.get(f"{FOLLOW_UPS}?due=yesterday")).status_code == 422
    await login(client, manager)  # the manager reads the team's lists
    team = (await client.get(f"{FOLLOW_UPS}?due=today&limit=100")).json()
    assert {str(overdue.id), str(later_today.id)} <= {i["id"] for i in team["items"]}
    assert all(i["can_change"] is False for i in team["items"])


# --- edit, complete, cancel, next follow-up (AC2, FU5, FU7, FU9) ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_reschedule_and_edit_send_only_changes(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    fu = (await _create(client, company["id"])).json()
    new_due = soon(days=3)
    response = await client.patch(fu_url(fu["id"]), json={"due_at": new_due, "reason": "jd", "notes": "Call HR"})
    assert response.status_code == 200, response.text
    assert response.json()["notes"] == "Call HR"
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == fu["id"], AuditLog.action == "recruiter_follow_up.update"))).all()
    assert [a.metadata_json["fields"] for a in audits] == [["due_at", "notes"]]
    assert (await client.patch(fu_url(fu["id"]), json={"due_at": soon(minutes=-1)})).status_code == 422
    assert (await client.patch(fu_url(fu["id"]), json={"reason": None})).status_code == 422
    overdue = await _stored(db_session, company["id"], recruiter, datetime.now(UTC) - timedelta(days=1))
    assert (await client.patch(fu_url(overdue.id), json={"notes": "still chasing"})).status_code == 200  # due unchanged: no due check


@pytest.mark.asyncio
async def test_completing_updates_the_next_follow_up(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    contact = (await client.post(f"{COMPANIES}/{company['id']}/contacts", json={"name": "Priya"})).json()["items"][0]
    first = (await _create(client, company["id"], due_at=soon(days=1), contact_id=contact["id"])).json()
    second = (await _create(client, company["id"], due_at=soon(days=5))).json()

    async def next_of_company():
        detail = (await client.get(f"{COMPANIES}/{company['id']}")).json()["company"]
        row = next(r for r in (await client.get(f"{COMPANIES}?q={company['code']}")).json()["items"] if r["id"] == company["id"])
        assert row["next_follow_up_at"] == detail["next_follow_up_at"]
        return detail["next_follow_up_at"]

    def same(a, b):
        return datetime.fromisoformat(a) == datetime.fromisoformat(b)

    assert same(await next_of_company(), first["due_at"])
    contacts = (await client.get(f"{COMPANIES}/{company['id']}/contacts")).json()["items"]
    assert same(contacts[0]["next_follow_up_at"], first["due_at"])
    done = await client.post(fu_url(first["id"], "complete"), json={"outcome": "JD received"})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "done" and done.json()["outcome"] == "JD received" and done.json()["completed_by"] is not None
    assert same(await next_of_company(), second["due_at"])
    assert (await client.get(f"{COMPANIES}/{company['id']}/contacts")).json()["items"][0]["next_follow_up_at"] is None
    assert (await client.post(fu_url(first["id"], "complete"), json={})).status_code == 409
    cancelled = await client.post(fu_url(second["id"], "cancel"), json={"reason": "Company paused hiring"})
    assert cancelled.status_code == 200 and cancelled.json()["cancel_reason"] == "Company paused hiring"
    assert await next_of_company() is None
    assert (await client.post(fu_url(second["id"], "cancel"), json={"reason": "again"})).status_code == 409
    page = (await client.get(f"{COMPANIES}/{company['id']}/follow-ups")).json()
    assert page["total"] == 2 and all(i["can_change"] is False for i in page["items"])
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id.in_([first["id"], second["id"]])))).all()
    assert sorted(actions) == ["recruiter_follow_up.cancel", "recruiter_follow_up.complete", "recruiter_follow_up.create", "recruiter_follow_up.create"]


@pytest.mark.asyncio
async def test_cancel_needs_a_reason(client, db_session):
    await _team(client, db_session)
    company = await _company(client)
    fu = (await _create(client, company["id"])).json()
    assert (await client.post(fu_url(fu["id"], "cancel"), json={})).status_code == 422
    assert (await client.post(fu_url(fu["id"], "cancel"), json={"reason": "  "})).status_code == 422


@pytest.mark.asyncio
async def test_company_list_orders_open_by_due_then_closed(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    later = (await _create(client, company["id"], due_at=soon(days=4))).json()
    sooner = (await _create(client, company["id"], due_at=soon(days=2))).json()
    closed = (await _create(client, company["id"], due_at=soon(days=1))).json()
    await client.post(fu_url(closed["id"], "complete"), json={})
    page = (await client.get(f"{COMPANIES}/{company['id']}/follow-ups")).json()
    assert [i["id"] for i in page["items"]] == [sooner["id"], later["id"], closed["id"]]
    assert (await client.get(f"{COMPANIES}/{uuid.uuid4()}/follow-ups")).status_code == 404
    assert (await client.patch(fu_url(uuid.uuid4()), json={"notes": "x"})).status_code == 404
