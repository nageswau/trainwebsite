"""pob-027 (DEC-SCOPE-434 I1-I8) -- intake automation: a new requirement's owner and notice in the same request (AC1), the configured tasks
created once on assignment (AC2), and the escalation rules firing once per rule and item (AC3). The shared test database is never truncated:
the template is reset around each test, every other escalation rule is switched off, and the sweeps run at a chosen `now`."""

import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from app.models import AuditLog, EscalationEvent, EscalationRule, Job, Notification, RecruiterFollowUp, RequirementAutomationSetting, RequirementTask, User
from app.notifications.events import EVENTS, RECRUITMENT_EVENTS
from app.services import escalations
from app.services import requirement_intake as intake
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user
from tests.test_rec_007_requirements import BASE, _company, _tag

pytestmark = pytest.mark.asyncio

SETTINGS = "/api/v1/recruiter/intake-automation/settings"
RULES = "/api/v1/recruiter/escalation-rules"
TEMPLATE = [{"kind": "sourcing", "title": "Prepare the sourcing plan", "due_in_hours": 24},
            {"kind": "screening", "title": "Screen the first shortlisted profiles", "due_in_hours": 72}]  # fmt: skip


@pytest_asyncio.fixture
async def template(db_session):
    """The settings row at the seeded template for the test, and back to it after."""

    async def put(items):
        row = await db_session.get(RequirementAutomationSetting, 1, populate_existing=True)
        if row is None:
            row = RequirementAutomationSetting(id=1)
            db_session.add(row)
        row.task_template = items
        await db_session.commit()

    await put(TEMPLATE)
    yield put
    await put(TEMPLATE)


@pytest_asyncio.fixture
async def rules_off(db_session):
    """No other test's rule fires in a sweep here; ours are switched off after."""
    await db_session.execute(update(EscalationRule).values(active=False))
    await db_session.commit()
    yield
    await db_session.execute(update(EscalationRule).values(active=False))
    await db_session.commit()


async def _notices(db, job_id, event: str) -> list[Notification]:
    stmt = select(Notification).where(Notification.event_type == event, Notification.entity_id == str(job_id)).execution_options(populate_existing=True)
    return list((await db.scalars(stmt)).all())


async def _tasks(db, job_id) -> list[RequirementTask]:
    stmt = select(RequirementTask).where(RequirementTask.job_id == job_id).order_by(RequirementTask.due_at).execution_options(populate_existing=True)
    return list((await db.scalars(stmt)).all())


async def _create(client, company, expected: int = 201, **extra) -> dict:
    response = await client.post(BASE, json={"company_id": str(company.id), "title": f"Intake {_tag()}", "location": "Pune", **extra})
    assert response.status_code == expected, response.text
    return response.json()["requirement"]


# --- AC1: owner and notice in the same request ------------------------------------------------------------------------------------------
async def test_a_managers_requirement_goes_to_the_company_recruiter_who_is_told(client, db_session, template):
    manager = await make_pm(db_session)
    recruiter = await make_recruiter(db_session, manager)
    company = await _company(db_session, recruiter)
    await login(client, manager)
    req = await _create(client, company)
    assert req["assigned_recruiter"]["id"] == str(recruiter.id)
    [notice] = await _notices(db_session, req["id"], "it.requirement.assigned")
    assert notice.user_id == recruiter.id
    tasks = await _tasks(db_session, req["id"])
    assert [(t.kind, t.title, t.assignee_user_id, t.status) for t in tasks] == [
        ("sourcing", "Prepare the sourcing plan", recruiter.id, "open"), ("screening", "Screen the first shortlisted profiles", recruiter.id, "open")]  # fmt: skip
    assert abs(tasks[1].due_at - tasks[0].due_at - timedelta(hours=48)) < timedelta(minutes=1)  # 72 h and 24 h from the same moment


async def test_a_recruiters_own_requirement_is_not_notified_to_themselves(client, db_session, template):
    recruiter = await make_recruiter(db_session, await make_pm(db_session))
    company = await _company(db_session, recruiter)
    await login(client, recruiter)
    req = await _create(client, company)
    assert await _notices(db_session, req["id"], "it.requirement.assigned") == []
    assert {t.assignee_user_id for t in await _tasks(db_session, req["id"])} == {recruiter.id}


@pytest.mark.parametrize("company_owner", ["none", "inactive"])
async def test_no_eligible_owner_puts_it_in_the_team_lead_queue(client, db_session, template, company_owner):
    manager = await make_pm(db_session)
    lead = await make_pm(db_session)
    owner = await make_recruiter(db_session, manager, active=False) if company_owner == "inactive" else None
    company = await _company(db_session, owner)
    await login(client, manager)
    req = await _create(client, company)
    assert req["assigned_recruiter"] is None
    job = await db_session.get(Job, uuid.UUID(req["id"]), populate_existing=True)
    assert job.assigned_recruiter_user_id is None
    told = {n.user_id for n in await _notices(db_session, req["id"], "it.requirement.unowned")}
    assert {manager.id, lead.id} <= told
    assert await _tasks(db_session, req["id"]) == []


async def test_the_legacy_staff_route_assigns_the_company_recruiter(client, db_session, template):
    recruiter = await make_recruiter(db_session, await make_pm(db_session))
    company = await _company(db_session, recruiter)
    admin = await make_user(db_session, "it_admin", "it")
    await login(client, admin)
    response = await client.post("/api/v1/workflows/it/jobs", json={"company_id": str(company.id), "title": f"Legacy {_tag()}"})
    assert response.status_code == 201, response.text
    job = await db_session.get(Job, uuid.UUID(response.json()["id"]), populate_existing=True)
    assert job.assigned_recruiter_user_id == recruiter.id
    assert [n.user_id for n in await _notices(db_session, job.id, "it.requirement.assigned")] == [recruiter.id]
    assert len(await _tasks(db_session, job.id)) == 2


# --- AC2: assignment creates the configured tasks once -----------------------------------------------------------------------------------
async def test_assignment_creates_the_tasks_once_and_a_reassignment_moves_them(client, db_session, template):
    manager = await make_pm(db_session)
    first = await make_recruiter(db_session, manager)
    second = await make_recruiter(db_session, manager)
    company = await _company(db_session)
    await login(client, manager)
    req = await _create(client, company)
    assert await _tasks(db_session, req["id"]) == []
    assert (await client.post(f"{BASE}/{req['id']}/assign", json={"recruiter_user_id": str(first.id)})).status_code == 200
    tasks = await _tasks(db_session, req["id"])
    assert len(tasks) == 2 and {t.assignee_user_id for t in tasks} == {first.id}
    assert [n.user_id for n in await _notices(db_session, req["id"], "it.requirement.assigned")] == [first.id]
    login_first = tasks[0]
    await login(client, first)
    assert (await client.post(f"{BASE}/{req['id']}/tasks/{login_first.id}/complete")).status_code == 200
    await login(client, manager)
    assert (await client.post(f"{BASE}/{req['id']}/assign", json={"recruiter_user_id": str(second.id)})).status_code == 200
    tasks = await _tasks(db_session, req["id"])
    assert len(tasks) == 2
    assert {(t.status, t.assignee_user_id) for t in tasks} == {("done", first.id), ("open", second.id)}
    assert second.id in {n.user_id for n in await _notices(db_session, req["id"], "it.requirement.assigned")}


async def test_an_empty_template_creates_no_tasks(client, db_session, template):
    await template([])
    recruiter = await make_recruiter(db_session, await make_pm(db_session))
    company = await _company(db_session, recruiter)
    await login(client, recruiter)
    req = await _create(client, company)
    assert await _tasks(db_session, req["id"]) == []


# --- I6: the task API ------------------------------------------------------------------------------------------------------------------
async def test_tasks_are_listed_and_completed_once(client, db_session, template):
    manager = await make_pm(db_session)
    recruiter = await make_recruiter(db_session, manager)
    outsider = await make_recruiter(db_session, await make_pm(db_session))
    company = await _company(db_session, recruiter)
    await login(client, recruiter)
    req = await _create(client, company)
    other = await _create(client, company)
    body = (await client.get(f"{BASE}/{req['id']}/tasks")).json()
    assert [t["kind"] for t in body["items"]] == ["sourcing", "screening"]
    assert body["items"][0]["assignee"]["id"] == str(recruiter.id) and body["items"][0]["can_complete"] is True
    task_id = body["items"][0]["id"]
    assert (await client.post(f"{BASE}/{other['id']}/tasks/{task_id}/complete")).status_code == 404  # another requirement's task
    done = await client.post(f"{BASE}/{req['id']}/tasks/{task_id}/complete")
    assert done.status_code == 200, done.text
    assert done.json()["task"]["status"] == "done" and done.json()["task"]["can_complete"] is False
    assert (await client.post(f"{BASE}/{req['id']}/tasks/{task_id}/complete")).status_code == 409
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "requirement_task.complete", AuditLog.entity_id == task_id))
    assert audit is not None and audit.metadata_json == {"job_id": req["id"], "kind": "sourcing"}
    await login(client, outsider)
    assert (await client.get(f"{BASE}/{req['id']}/tasks")).status_code == 404
    assert (await client.post(f"{BASE}/{req['id']}/tasks/{body['items'][1]['id']}/complete")).status_code == 404


# --- I3: the settings --------------------------------------------------------------------------------------------------------------------
async def test_only_a_team_lead_reads_and_changes_the_template(client, db_session, template):
    recruiter = await make_recruiter(db_session, await make_pm(db_session))
    await login(client, recruiter)
    assert (await client.get(SETTINGS)).status_code == 403
    assert (await client.put(SETTINGS, json={"task_template": []})).status_code == 403
    manager = await make_pm(db_session)
    await login(client, manager)
    assert (await client.get(SETTINGS)).json() == {"task_template": TEMPLATE}
    new = [{"kind": "screening", "title": "Call the shortlisted", "due_in_hours": 12}]
    saved = await client.put(SETTINGS, json={"task_template": new})
    assert saved.status_code == 200 and saved.json() == {"task_template": new}
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "requirement_automation.settings", AuditLog.user_id == manager.id))
    assert audit is not None and audit.metadata_json == {"tasks": [2, 1]}


@pytest.mark.parametrize(
    "item",
    [{"kind": "calling", "title": "x", "due_in_hours": 1}, {"kind": "sourcing", "title": " ", "due_in_hours": 1},
     {"kind": "sourcing", "title": "x", "due_in_hours": 0}, {"kind": "sourcing", "title": "x", "due_in_hours": 721}],
)  # fmt: skip
async def test_a_bad_template_item_is_422(client, db_session, template, item):
    await login(client, await make_pm(db_session))
    assert (await client.put(SETTINGS, json={"task_template": [item]})).status_code == 422


async def test_more_than_ten_template_items_is_422(client, db_session, template):
    await login(client, await make_pm(db_session))
    assert (await client.put(SETTINGS, json={"task_template": [TEMPLATE[0]] * 11})).status_code == 422


# --- I7: the rules ---------------------------------------------------------------------------------------------------------------------
async def test_rules_are_created_listed_and_switched_off_by_a_team_lead(client, db_session, rules_off):
    recruiter = await make_recruiter(db_session, await make_pm(db_session))
    await login(client, recruiter)
    assert (await client.get(RULES)).status_code == 403
    assert (await client.post(RULES, json={"event_type": "follow_up_overdue", "after_hours": 4, "notify": "reporting_manager"})).status_code == 403
    manager = await make_pm(db_session)
    await login(client, manager)
    assert (await client.post(RULES, json={"event_type": "nope", "after_hours": 4, "notify": "reporting_manager"})).status_code == 422
    assert (await client.post(RULES, json={"event_type": "follow_up_overdue", "after_hours": 0, "notify": "reporting_manager"})).status_code == 422
    created = await client.post(RULES, json={"event_type": "follow_up_overdue", "after_hours": 4, "notify": "reporting_manager"})
    assert created.status_code == 201, created.text
    rule = created.json()["rule"]
    assert rule | {"id": None, "created_at": None} == {"id": None, "event_type": "follow_up_overdue", "after_hours": 4, "notify": "reporting_manager",
                                                       "active": True, "created_at": None}  # fmt: skip
    assert rule["id"] in [r["id"] for r in (await client.get(RULES)).json()["items"]]
    changed = await client.patch(f"{RULES}/{rule['id']}", json={"active": False, "after_hours": 8})
    assert changed.status_code == 200 and changed.json()["rule"]["active"] is False and changed.json()["rule"]["after_hours"] == 8
    assert (await client.patch(f"{RULES}/{uuid.uuid4()}", json={"active": True})).status_code == 404
    actions = set((await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == rule["id"]))).all())
    assert actions == {"escalation_rule.create", "escalation_rule.update"}


async def _rule(db, manager: User, event_type: str, hours: int, notify: str = "reporting_manager", created_at: datetime | None = None) -> EscalationRule:
    rule = EscalationRule(event_type=event_type, after_hours=hours, notify=notify, created_by_user_id=manager.id)
    db.add(rule)
    await db.flush()
    if created_at is not None:
        rule.created_at = created_at
    await db.commit()
    return rule


async def _escalated(db, rule, entity_id) -> int:
    return len((await db.scalars(select(EscalationEvent).where(EscalationEvent.rule_id == rule.id, EscalationEvent.entity_id == entity_id))).all())


async def _escalation_notices(db, entity_id) -> list[Notification]:
    stmt = select(Notification).where(Notification.event_type == escalations.EVENT, Notification.entity_id == str(entity_id))
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


# --- AC3: escalations fire per rule, once -----------------------------------------------------------------------------------------------
async def test_an_unowned_requirement_escalates_once_to_every_team_lead(client, db_session, template, rules_off):
    manager = await make_pm(db_session)
    company = await _company(db_session)
    await login(client, manager)
    req = await _create(client, company)
    job_id = uuid.UUID(req["id"])
    rule = await _rule(db_session, manager, "requirement_unowned", 2, "reporting_manager", created_at=datetime.now(UTC) - timedelta(minutes=1))
    now = datetime.now(UTC) + timedelta(hours=1)
    await escalations.run_escalations(now)
    assert await _escalated(db_session, rule, job_id) == 0  # not yet 2 hours
    now = datetime.now(UTC) + timedelta(hours=3)
    await escalations.run_escalations(now)
    await escalations.run_escalations(now)
    assert await _escalated(db_session, rule, job_id) == 1
    assert manager.id in {n.user_id for n in await _escalation_notices(db_session, job_id)}
    assert len([n for n in await _escalation_notices(db_session, job_id) if n.user_id == manager.id]) == 1


async def test_an_overdue_task_escalates_to_the_owners_reporting_manager(client, db_session, template, rules_off):
    manager = await make_pm(db_session)
    other_lead = await make_pm(db_session)
    recruiter = await make_recruiter(db_session, manager)
    company = await _company(db_session, recruiter)
    await login(client, recruiter)
    req = await _create(client, company)
    first, second = await _tasks(db_session, req["id"])
    rule = await _rule(db_session, manager, "requirement_task_overdue", 1, created_at=datetime.now(UTC) - timedelta(minutes=1))
    await escalations.run_escalations(first.due_at + timedelta(hours=2))
    assert await _escalated(db_session, rule, first.id) == 1 and await _escalated(db_session, rule, second.id) == 0
    told = {n.user_id for n in await _escalation_notices(db_session, first.id)}
    assert manager.id in told and other_lead.id not in told and recruiter.id not in told


async def test_a_done_task_and_a_backlog_item_do_not_escalate(client, db_session, template, rules_off):
    manager = await make_pm(db_session)
    recruiter = await make_recruiter(db_session, manager)
    company = await _company(db_session, recruiter)
    await login(client, recruiter)
    req = await _create(client, company)
    first, second = await _tasks(db_session, req["id"])
    assert (await client.post(f"{BASE}/{req['id']}/tasks/{first.id}/complete")).status_code == 200
    rule = await _rule(db_session, manager, "requirement_task_overdue", 1, created_at=second.due_at + timedelta(hours=5))  # the rule is newer
    await escalations.run_escalations(second.due_at + timedelta(hours=6))
    assert await _escalated(db_session, rule, first.id) == 0 and await _escalated(db_session, rule, second.id) == 0


async def test_an_overdue_follow_up_escalates_to_all_team_leads(client, db_session, rules_off):
    manager = await make_pm(db_session)
    lead = await make_pm(db_session)
    recruiter = await make_recruiter(db_session, manager)
    company = await _company(db_session, recruiter)
    now = datetime.now(UTC)
    follow_up = RecruiterFollowUp(company_id=company.id, reason="jd", due_at=now, created_by_user_id=recruiter.id)
    db_session.add(follow_up)
    await db_session.commit()
    rule = await _rule(db_session, manager, "follow_up_overdue", 4, "all_team_leads", created_at=now - timedelta(minutes=1))
    await escalations.run_escalations(now + timedelta(hours=5))
    assert await _escalated(db_session, rule, follow_up.id) == 1
    assert {manager.id, lead.id} <= {n.user_id for n in await _escalation_notices(db_session, follow_up.id)}
    off = await _rule(db_session, manager, "follow_up_overdue", 4, created_at=now - timedelta(minutes=1))
    off.active = False
    await db_session.commit()
    await escalations.run_escalations(now + timedelta(hours=5))
    assert await _escalated(db_session, off, follow_up.id) == 0


async def test_the_events_are_catalogued_without_names():
    for key in (intake.UNOWNED, escalations.EVENT):
        assert key in EVENTS and key in RECRUITMENT_EVENTS
        assert "{" not in EVENTS[key].body


async def test_the_worker_imports_cleanly_in_a_fresh_interpreter():
    """pob-016 lesson: the services must not enter the telecaller import cycle that pytest's conftest hides."""
    code = "import app.worker as w; w.escalations_task; from app.services import escalations, requirement_intake"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=".")
    assert result.returncode == 0, result.stderr[-2000:]
