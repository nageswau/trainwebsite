"""pob-008 (DEC-SCOPE-423 B1-B11) -- recruiter follow-up reminders (once each, re-armed by a reschedule, to the current owner), outreach
cadences (the Team Lead's library, a run started on an outreach message, the next step's follow-up when no reply came, stopped by a reply or
Do Not Contact) and the first-outreach follow-up of a new company or contact. The shared test database is never truncated, so the sweep
tests take every other row out of reach first and the sweeps run at a chosen `now`."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import (
    AuditLog,
    CompanyContact,
    Notification,
    RecruiterContactCadence,
    RecruiterFollowUp,
    RecruiterMessageTemplate,
)
from app.notifications.events import EVENTS, RECRUITMENT_EVENTS
from app.services import recruiter_cadences as cadences
from tests.rec001_helpers import login, make_pm, make_recruiter
from tests.test_rec_009_candidates import mail, mobile

COMPANIES = "/api/v1/recruiter/companies"
MESSAGES = "/api/v1/recruiter/messages"
LINKEDIN = f"{MESSAGES}/linkedin"
FOLLOW_UPS = "/api/v1/recruiter/follow-ups"
CADENCES = "/api/v1/recruiter/cadences"
DUE = "it.recruiter.follow_up_due"


def unique(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


def at(**delta) -> datetime:
    return datetime.now(UTC) + timedelta(**delta)


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _company(client, **over) -> dict:
    response = await client.post(COMPANIES, json={"name": unique("Cadence Co")} | over)
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _contact(client, company_id, **over) -> dict:
    name = over.pop("name", unique("Asha"))
    response = await client.post(f"{COMPANIES}/{company_id}/contacts", json={"name": name, "mobile": mobile(), "email": mail()} | over)
    assert response.status_code == 201, response.text
    return next(c for c in response.json()["items"] if c["name"] == name)


async def _follow_ups(db, company_id) -> list[RecruiterFollowUp]:
    rows = await db.scalars(select(RecruiterFollowUp).where(RecruiterFollowUp.company_id == company_id).order_by(RecruiterFollowUp.created_at)
                            .execution_options(populate_existing=True))  # fmt: skip
    return list(rows.all())


async def _got(db, user_id) -> list[Notification]:
    rows = await db.scalars(select(Notification).where(Notification.user_id == user_id, Notification.event_type == DUE).execution_options(populate_existing=True))
    return list(rows.all())


async def _only_these_follow_ups(db, *ids):
    """Every other open follow-up is out of the reminder sweep's reach."""
    await db.execute(update(RecruiterFollowUp).where(RecruiterFollowUp.id.not_in(ids), RecruiterFollowUp.reminded_at.is_(None)).values(reminded_at=datetime.now(UTC)))
    await db.commit()


async def _only_these_runs(db, *ids):
    await db.execute(update(RecruiterContactCadence).where(RecruiterContactCadence.id.not_in(ids), RecruiterContactCadence.status == "active")
                     .values(next_step_at=datetime.now(UTC) + timedelta(days=4000)))  # fmt: skip
    await db.commit()


async def _follow_up(client, company_id, **over) -> dict:
    body = {"reason": "jd", "due_at": at(minutes=20).isoformat()} | over
    response = await client.post(f"{COMPANIES}/{company_id}/follow-ups", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _template(db, channel="email", **over) -> RecruiterMessageTemplate:
    values = {"channel": channel, "kind": {"email": "company_introduction", "whatsapp": "follow_up"}.get(channel), "name": unique("Step tpl"),
              "subject": "Following up, {name}" if channel == "email" else None, "body": "Hello {name}, any update from {company}?",
              "category": "company", "status": "approved"} | over  # fmt: skip
    template = RecruiterMessageTemplate(**values)
    db.add(template)
    await db.commit()
    return template


def _steps(template_id=None) -> list[dict]:
    return [{"day": 0, "channel": "email", "template_id": None}, {"day": 3, "channel": "linkedin", "template_id": None},
            {"day": 7, "channel": "email", "template_id": str(template_id) if template_id else None}]  # fmt: skip


async def _cadence(client, manager, recruiter, **over) -> dict:
    """The manager creates it, then the recruiter is signed back in."""
    await login(client, manager)
    response = await client.post(CADENCES, json={"name": unique("Intro cadence"), "steps": _steps()} | over)
    assert response.status_code == 201, response.text
    await login(client, recruiter)
    return response.json()


async def _linkedin(client, contact_id) -> dict:
    response = await client.post(LINKEDIN, json={"contact_id": contact_id, "action": "message", "body": "Hi, are you hiring?"})
    assert response.status_code == 201, response.text
    return response.json()


async def _started(client, db):
    manager, recruiter = await _team(client, db)
    company = await _company(client)
    contact = await _contact(client, company["id"])
    message = await _linkedin(client, contact["id"])
    return manager, recruiter, company, contact, message


async def _run(db, contact_id) -> RecruiterContactCadence:
    return await db.scalar(select(RecruiterContactCadence).where(RecruiterContactCadence.contact_id == contact_id)
                           .order_by(RecruiterContactCadence.created_at.desc()).execution_options(populate_existing=True))  # fmt: skip


def test_the_worker_and_the_service_import_in_a_fresh_interpreter():
    import subprocess
    import sys

    # the worker tasks' own import order (telecaller_alerts first: main's telecaller cycle only resolves from that end)
    code = ("import app.worker; import app.services.telecaller_alerts; import app.services.recruiter_cadences; "
            "assert {'pob008-cadences', 'pob008-follow-up-reminders'} <= set(app.worker.celery.conf.beat_schedule)")  # fmt: skip
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd="/app")
    assert result.returncode == 0, result.stderr[-2000:]


# --- B1-B4 reminders (AC1) --------------------------------------------------------------------------------------------------------------
def test_the_reminder_event_is_catalogued_with_fixed_text():
    assert EVENTS[DUE].entity_type == "recruiter_follow_up" and DUE in RECRUITMENT_EVENTS
    assert "{" not in EVENTS[DUE].body


@pytest.mark.asyncio
async def test_a_follow_up_due_soon_is_reminded_once(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    fu = await _follow_up(client, company["id"])
    await _only_these_follow_ups(db_session, uuid.UUID(fu["id"]))
    assert await cadences.run_follow_up_reminders() == {"reminded": 1}
    assert await cadences.run_follow_up_reminders() == {"reminded": 0}  # once per follow-up
    notices = await _got(db_session, recruiter.id)
    assert [(n.entity_id, n.action_url) for n in notices] == [(fu["id"], "/recruiter/follow-ups")]
    assert "Asha" not in notices[0].body and notices[0].title == "Follow-up due"
    assert (await client.get(f"{FOLLOW_UPS}?due=today")).status_code == 200


@pytest.mark.asyncio
async def test_a_reminder_time_wins_and_a_far_follow_up_waits(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    timed = await _follow_up(client, company["id"], due_at=at(hours=5).isoformat(), remind_at=at(hours=2).isoformat())
    later = await _follow_up(client, company["id"], due_at=at(days=2).isoformat())
    await _only_these_follow_ups(db_session, uuid.UUID(timed["id"]), uuid.UUID(later["id"]))
    assert await cadences.run_follow_up_reminders() == {"reminded": 0}
    assert await cadences.run_follow_up_reminders(at(hours=2, minutes=1)) == {"reminded": 1}
    assert [n.entity_id for n in await _got(db_session, recruiter.id)] == [timed["id"]]
    assert await cadences.run_follow_up_reminders(at(days=3)) == {"reminded": 1}  # overdue: reminded too


@pytest.mark.asyncio
async def test_a_reschedule_re_arms_the_reminder(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(client)
    fu = await _follow_up(client, company["id"])
    await _only_these_follow_ups(db_session, uuid.UUID(fu["id"]))
    await cadences.run_follow_up_reminders()
    response = await client.patch(f"{FOLLOW_UPS}/{fu['id']}", json={"due_at": at(minutes=25).isoformat()})
    assert response.status_code == 200, response.text
    assert response.json()["reminded_at"] is None
    notes = await client.patch(f"{FOLLOW_UPS}/{fu['id']}", json={"notes": "only notes"})  # not a reschedule: stays armed as it is
    assert notes.status_code == 200
    assert await cadences.run_follow_up_reminders() == {"reminded": 1}
    assert len(await _got(db_session, recruiter.id)) == 2


@pytest.mark.asyncio
async def test_the_reminder_goes_to_the_current_owner_and_skips_archived(client, db_session):
    manager, recruiter = await _team(client, db_session)
    other = await make_recruiter(db_session, manager)
    company = await _company(client)
    archived = await _company(client)
    fu = await _follow_up(client, company["id"])
    gone = await _follow_up(client, archived["id"])
    assert (await client.post(f"{COMPANIES}/{archived['id']}/archive")).status_code == 200
    await login(client, manager)
    assert (await client.post(f"{COMPANIES}/{company['id']}/assign", json={"recruiter_user_id": str(other.id)})).status_code == 200
    await _only_these_follow_ups(db_session, uuid.UUID(fu["id"]), uuid.UUID(gone["id"]))
    assert await cadences.run_follow_up_reminders() == {"reminded": 1}
    assert [n.entity_id for n in await _got(db_session, other.id)] == [fu["id"]]
    assert await _got(db_session, recruiter.id) == []


# --- B5 the cadence library ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_team_lead_manages_cadences_and_a_recruiter_reads_them(client, db_session):
    manager, recruiter = await _team(client, db_session)
    template = await _template(db_session)
    created = await _cadence(client, manager, recruiter, steps=_steps(template.id), description="Three touches")
    assert created["steps"][2]["template"] == {"id": str(template.id), "name": template.name} and created["active"] is True
    listed = await client.get(CADENCES)
    assert listed.status_code == 200 and created["id"] in {c["id"] for c in listed.json()["items"]}
    assert (await client.post(CADENCES, json={"name": unique("Nope"), "steps": _steps()})).status_code == 403
    assert (await client.patch(f"{CADENCES}/{created['id']}", json={"active": False})).status_code == 403
    await login(client, manager)
    off = await client.patch(f"{CADENCES}/{created['id']}", json={"active": False, "name": created["name"] + " v2"})
    assert off.status_code == 200 and off.json()["active"] is False
    assert created["id"] not in {c["id"] for c in (await client.get(CADENCES)).json()["items"]}
    assert created["id"] in {c["id"] for c in (await client.get(CADENCES, params={"include_inactive": "true"})).json()["items"]}
    audit = await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == created["id"]))
    assert set(audit.all()) == {"recruiter_cadence.create", "recruiter_cadence.update"}


@pytest.mark.asyncio
async def test_a_role_outside_the_recruiter_crm_cannot_read_cadences(client, db_session):
    from tests.rec001_helpers import make_user

    await login(client, await make_user(db_session, "student", "it"))
    assert (await client.get(CADENCES)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("steps", [
    [{"day": 1, "channel": "email"}, {"day": 3, "channel": "email"}],  # the first step is day 0
    [{"day": 0, "channel": "email"}, {"day": 0, "channel": "email"}],  # strictly increasing
    [{"day": 0, "channel": "email"}],  # at least two
    [{"day": 0, "channel": "fax"}, {"day": 2, "channel": "email"}],  # a known channel
    [{"day": 0, "channel": "email"}, {"day": 91, "channel": "email"}],  # at most 90 days
    [{"day": 0, "channel": "email"}] + [{"day": d, "channel": "call"} for d in range(1, 11)],  # at most ten
])  # fmt: skip
async def test_cadence_step_rules(client, db_session, steps):
    await login(client, await make_pm(db_session))
    response = await client.post(CADENCES, json={"name": unique("Bad"), "steps": steps})
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_a_step_template_must_be_approved_shared_and_of_the_channel(client, db_session):
    manager = await make_pm(db_session)
    await login(client, manager)
    wrong_channel = await _template(db_session, channel="whatsapp", subject=None)
    draft = await _template(db_session, status="draft")
    personal = await _template(db_session, status="draft", owner_user_id=manager.id)
    for template in (wrong_channel, draft, personal):
        response = await client.post(CADENCES, json={"name": unique("Tpl"), "steps": _steps(template.id)})
        assert response.status_code == 422, response.text
        assert response.json()["detail"][0]["loc"][-1] == "steps"
    name = unique("Same")
    assert (await client.post(CADENCES, json={"name": name, "steps": _steps()})).status_code == 201
    assert (await client.post(CADENCES, json={"name": name.upper(), "steps": _steps()})).status_code == 409


# --- B6/B9 a run on an outreach message --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_cadence_starts_on_a_contact_message_once(client, db_session):
    manager, recruiter, company, contact, message = await _started(client, db_session)
    cadence = await _cadence(client, manager, recruiter)
    response = await client.post(f"{MESSAGES}/{message['id']}/cadence", json={"cadence_id": cadence["id"]})
    assert response.status_code == 201, response.text
    run = response.json()["cadence"]
    assert (run["name"], run["status"], run["step"], run["steps"], run["can_stop"]) == (cadence["name"], "active", 1, 3, True)
    assert datetime.fromisoformat(run["next_step_at"]) - datetime.fromisoformat(message["sent_at"]) == timedelta(days=3)
    listed = (await client.get(f"{COMPANIES}/{company['id']}/messages")).json()["items"]
    assert next(m for m in listed if m["id"] == message["id"])["cadence"]["id"] == run["id"]
    again = await client.post(f"{MESSAGES}/{message['id']}/cadence", json={"cadence_id": cadence["id"]})
    assert again.status_code == 409
    second = await _linkedin(client, contact["id"])
    assert (await client.post(f"{MESSAGES}/{second['id']}/cadence", json={"cadence_id": cadence["id"]})).status_code == 409  # one per contact


@pytest.mark.asyncio
async def test_a_start_is_refused_out_of_scope_inactive_or_do_not_contact(client, db_session):
    manager, recruiter, company, contact, message = await _started(client, db_session)
    cadence = await _cadence(client, manager, recruiter)
    off = await _cadence(client, manager, recruiter)
    await login(client, manager)
    await client.patch(f"{CADENCES}/{off['id']}", json={"active": False})
    await login(client, recruiter)
    assert (await client.post(f"{MESSAGES}/{message['id']}/cadence", json={"cadence_id": off["id"]})).status_code == 422
    assert (await client.post(f"{MESSAGES}/{message['id']}/cadence", json={"cadence_id": str(uuid.uuid4())})).status_code == 422
    stranger = await make_recruiter(db_session, manager)
    await login(client, stranger)
    assert (await client.post(f"{MESSAGES}/{message['id']}/cadence", json={"cadence_id": cadence["id"]})).status_code == 404
    await login(client, recruiter)
    patched = await client.patch(f"/api/v1/recruiter/contacts/{contact['id']}", json={"status": "do_not_contact"})
    assert patched.status_code == 200, patched.text
    assert (await client.post(f"{MESSAGES}/{message['id']}/cadence", json={"cadence_id": cadence["id"]})).status_code == 409


@pytest.mark.asyncio
async def test_a_logged_reply_stops_the_cadence(client, db_session):
    manager, recruiter, _company_, contact, message = await _started(client, db_session)
    cadence = await _cadence(client, manager, recruiter)
    await client.post(f"{MESSAGES}/{message['id']}/cadence", json={"cadence_id": cadence["id"]})
    assert (await client.post(f"{MESSAGES}/{message['id']}/reply", json={})).status_code == 200
    run = await _run(db_session, uuid.UUID(contact["id"]))
    assert (run.status, run.end_reason, run.next_step_at) == ("replied", "reply", None)
    await _only_these_runs(db_session, run.id)
    assert await cadences.run_cadences(at(days=30)) == {"steps": 0, "ended": 0}


@pytest.mark.asyncio
async def test_do_not_contact_and_a_manual_stop_end_the_cadence(client, db_session):
    manager, recruiter, company, contact, message = await _started(client, db_session)
    cadence = await _cadence(client, manager, recruiter)
    await client.post(f"{MESSAGES}/{message['id']}/cadence", json={"cadence_id": cadence["id"]})
    await client.patch(f"/api/v1/recruiter/contacts/{contact['id']}", json={"status": "do_not_contact"})
    run = await _run(db_session, uuid.UUID(contact["id"]))
    assert (run.status, run.end_reason) == ("stopped", "do_not_contact")
    other = await _contact(client, company["id"])
    message = await _linkedin(client, other["id"])
    await client.post(f"{MESSAGES}/{message['id']}/cadence", json={"cadence_id": cadence["id"]})
    stopped = await client.post(f"{MESSAGES}/{message['id']}/cadence/stop")
    assert stopped.status_code == 200, stopped.text
    assert (stopped.json()["cadence"]["status"], stopped.json()["cadence"]["end_reason"], stopped.json()["cadence"]["can_stop"]) == ("stopped", "manual", False)
    assert (await client.post(f"{MESSAGES}/{message['id']}/cadence/stop")).status_code == 409


# --- B8 the cadence sweep (AC2, AC3) ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_without_a_reply_each_next_step_becomes_a_follow_up(client, db_session):
    manager, recruiter, company, contact, message = await _started(client, db_session)
    template = await _template(db_session)
    cadence = await _cadence(client, manager, recruiter, steps=_steps(template.id))
    await client.post(f"{MESSAGES}/{message['id']}/cadence", json={"cadence_id": cadence["id"]})
    run = await _run(db_session, uuid.UUID(contact["id"]))
    await _only_these_runs(db_session, run.id)
    before = {f.id for f in await _follow_ups(db_session, uuid.UUID(company["id"]))}
    assert await cadences.run_cadences(at(days=2)) == {"steps": 0, "ended": 0}  # not before the day
    assert await cadences.run_cadences(at(days=3, minutes=1)) == {"steps": 1, "ended": 0}
    step2 = [f for f in await _follow_ups(db_session, uuid.UUID(company["id"])) if f.id not in before]
    assert [(f.reason, str(f.contact_id), f.created_by_user_id, f.status) for f in step2] == [("cadence_step", contact["id"], recruiter.id, "open")]
    assert step2[0].notes.startswith(f"{cadence['name']} — step 2 of 3: LinkedIn")
    assert await cadences.run_cadences(at(days=3, minutes=2)) == {"steps": 0, "ended": 0}  # once per step
    assert await cadences.run_cadences(at(days=7, minutes=1)) == {"steps": 1, "ended": 1}  # the last step completes the run
    last = (await _follow_ups(db_session, uuid.UUID(company["id"])))[-1]
    assert f"Template: {template.name}" in last.notes and f"Hello {contact['name']}, any update from {company['name']}?" in last.notes
    run = await _run(db_session, uuid.UUID(contact["id"]))
    assert (run.status, run.step, run.end_reason, run.last_follow_up_id) == ("completed", 3, "last_step", last.id)


@pytest.mark.asyncio
async def test_the_sweep_stops_a_run_whose_contact_replied_or_left(client, db_session):
    manager, recruiter, company, contact, message = await _started(client, db_session)
    cadence = await _cadence(client, manager, recruiter)
    await client.post(f"{MESSAGES}/{message['id']}/cadence", json={"cadence_id": cadence["id"]})
    other = await _contact(client, company["id"])
    second = await _linkedin(client, other["id"])
    await client.post(f"{MESSAGES}/{second['id']}/cadence", json={"cadence_id": cadence["id"]})
    first_run, second_run = await _run(db_session, uuid.UUID(contact["id"])), await _run(db_session, uuid.UUID(other["id"]))
    # changed behind the hooks' back: the sweep is the safety net
    await db_session.execute(update(CompanyContact).where(CompanyContact.id == uuid.UUID(contact["id"])).values(status="replied"))
    await db_session.execute(update(CompanyContact).where(CompanyContact.id == uuid.UUID(other["id"])).values(active=False))
    await db_session.commit()
    await _only_these_runs(db_session, first_run.id, second_run.id)
    before = len(await _follow_ups(db_session, uuid.UUID(company["id"])))
    assert await cadences.run_cadences(at(days=4)) == {"steps": 0, "ended": 2}
    assert len(await _follow_ups(db_session, uuid.UUID(company["id"]))) == before
    first_run, second_run = await _run(db_session, uuid.UUID(contact["id"])), await _run(db_session, uuid.UUID(other["id"]))
    assert (first_run.status, first_run.end_reason, second_run.status, second_run.end_reason) == ("replied", "reply", "stopped", "inactive")


@pytest.mark.asyncio
async def test_a_reassigned_company_moves_the_cadence_to_the_new_owner(client, db_session):
    manager, recruiter, company, contact, message = await _started(client, db_session)
    cadence = await _cadence(client, manager, recruiter)
    await client.post(f"{MESSAGES}/{message['id']}/cadence", json={"cadence_id": cadence["id"]})
    other = await make_recruiter(db_session, manager)
    await login(client, manager)
    assert (await client.post(f"{COMPANIES}/{company['id']}/assign", json={"recruiter_user_id": str(other.id)})).status_code == 200
    run = await _run(db_session, uuid.UUID(contact["id"]))
    await _only_these_runs(db_session, run.id)
    assert await cadences.run_cadences(at(days=4)) == {"steps": 1, "ended": 0}
    step = (await _follow_ups(db_session, uuid.UUID(company["id"])))[-1]
    assert (step.reason, step.created_by_user_id) == ("cadence_step", other.id)


# --- B10 first outreach ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_new_company_or_contact_gets_one_first_outreach_follow_up(client, db_session):
    _, recruiter = await _team(client, db_session)
    bare = await _company(client)
    rows = await _follow_ups(db_session, uuid.UUID(bare["id"]))
    assert [(f.reason, f.contact_id, f.created_by_user_id) for f in rows] == [("first_outreach", None, recruiter.id)]
    assert timedelta(hours=23) < rows[0].due_at - datetime.now(UTC) <= timedelta(hours=24)
    contact = await _contact(client, bare["id"])
    rows = await _follow_ups(db_session, uuid.UUID(bare["id"]))
    assert [(f.reason, str(f.contact_id) if f.contact_id else None) for f in rows] == [("first_outreach", None), ("first_outreach", contact["id"])]
    await _contact(client, bare["id"], status="do_not_contact")
    assert len(await _follow_ups(db_session, uuid.UUID(bare["id"]))) == 2  # none for a Do Not Contact person
    with_contact = await _company(client, contact={"name": unique("First"), "mobile": mobile()})
    rows = await _follow_ups(db_session, uuid.UUID(with_contact["id"]))
    assert len(rows) == 1 and rows[0].reason == "first_outreach" and rows[0].contact_id is not None
