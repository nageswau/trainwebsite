"""pob-016 (DEC-SCOPE-419) -- the requirement validation checklist: the eight items and their follow-ups (C1-C5), the blocking rules (C6), the
sourcing guard (C7-C9), the warning after sourcing has started (C10), the Team Lead's override (C11), who may do what (C12) and the audit (C14).
Names are unique per test (the database is shared and never truncated)."""

import subprocess
import sys
from datetime import timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, event, select

from app.models import AuditLog, Company, CompanyContact, Job, RecruiterFollowUp, RequirementChecklistSetting
from app.services import recruiter_follow_ups
from app.services import recruiter_requirements as requirements
from app.services import requirement_checklist as checklist
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user
from tests.test_rec_007_requirements import BASE, _company, _tag

pytestmark = pytest.mark.asyncio

KEYS = ("role_scope", "skills_experience", "openings", "location_work_mode", "salary_budget", "hiring_process", "commercial_terms", "timeline")
RULES = "/api/v1/recruiter/requirement-checklist/settings"


async def _world(client, db, *, blocks: bool | None = None) -> dict:
    """A manager's recruiter (signed in) with a company and a requirement that has reached `requirement_received`. `outsider` is on another team."""
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager, name=f"Rec {_tag()}")
    outsider = await make_recruiter(db, await make_pm(db), name=f"Outsider {_tag()}")
    company = await _company(db, recruiter, checklist_blocks_sourcing=blocks)
    await login(client, recruiter)
    response = await client.post(BASE, json={"company_id": str(company.id), "title": f"Checked {_tag()}", "location": "Pune"})
    assert response.status_code == 201, response.text
    req = response.json()["requirement"]
    assert (await client.post(f"{BASE}/{req['id']}/status", json={"status": "requirement_received"})).status_code == 200
    return {"manager": manager, "recruiter": recruiter, "outsider": outsider, "company": company, "id": req["id"], "code": req["code"], "url": f"{BASE}/{req['id']}/checklist"}


async def _mark(client, w, key: str, status: str, expected: int = 200) -> dict:
    response = await client.put(f"{w['url']}/items/{key}", json={"status": status})
    assert response.status_code == expected, response.text
    return response.json()


async def _mark_all(client, w, status: str = "confirmed", keys=KEYS) -> dict:
    body = {}
    for key in keys:
        body = await _mark(client, w, key, status)
    return body


async def _move(client, w, status: str, expected: int = 200) -> dict:
    response = await client.post(f"{BASE}/{w['id']}/status", json={"status": status, **({"note": "Client paused hiring"} if status == "closed" else {})})  # pob-026 S11
    assert response.status_code == expected, response.text
    return response.json()


def _item(body: dict, key: str) -> dict:
    return next(i for i in body["items"] if i["key"] == key)


async def _follow_ups(db, job_id) -> list[RecruiterFollowUp]:
    stmt = select(RecruiterFollowUp).where(RecruiterFollowUp.job_id == job_id).order_by(RecruiterFollowUp.created_at).execution_options(populate_existing=True)
    return list((await db.scalars(stmt)).all())


async def _audits(db, job_id, action: str) -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.entity_id == str(job_id), AuditLog.action == action).order_by(AuditLog.created_at))).all())


@pytest_asyncio.fixture
async def db(db_session):
    return db_session


@pytest_asyncio.fixture
async def global_rule(db):
    """Restores the one settings row: the database is shared."""
    yield
    await db.execute(delete(RequirementChecklistSetting))
    await db.commit()


# --- C1-C3: the items -----------------------------------------------------------------------------------------------------------------
async def test_a_new_requirement_has_the_eight_items_unreviewed(client, db):
    w = await _world(client, db)
    response = await client.get(w["url"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert [i["key"] for i in body["items"]] == list(KEYS)
    assert all(i["status"] is None and i["label"] and i["hint"] and i["follow_up"] is None for i in body["items"])
    assert body["summary"] == {"total": 8, "confirmed": 0, "not_applicable": 0, "missing": 0, "not_reviewed": 8, "complete": False}
    assert body["blocking"] == {"on": False, "company_rule": None, "global_rule": False}
    assert body["override"] is None and body["sourcing_started"] is False and body["warning"] is None


async def test_every_item_confirmed_or_not_applicable_is_complete(client, db):
    w = await _world(client, db)
    await _mark_all(client, w, keys=KEYS[:-1])
    body = await _mark(client, w, KEYS[-1], "not_applicable")
    assert body["summary"] == {"total": 8, "confirmed": 7, "not_applicable": 1, "missing": 0, "not_reviewed": 0, "complete": True}


async def test_an_unknown_item_or_status_is_refused(client, db):
    w = await _world(client, db)
    await _mark(client, w, "dress_code", "confirmed", expected=422)
    await _mark(client, w, "openings", "maybe", expected=422)


# --- AC1, C4, C5: a missing item creates a follow-up ------------------------------------------------------------------------------------
async def test_ac1_a_missing_item_creates_a_follow_up_with_the_decision_maker(client, db):
    w = await _world(client, db)
    primary = CompanyContact(company_id=w["company"].id, name=f"Primary {_tag()}", is_primary=True)
    decider = CompanyContact(company_id=w["company"].id, name=f"Decider {_tag()}")
    db.add_all([primary, decider])
    await db.commit()
    await db.execute(Job.__table__.update().where(Job.id == w["id"]).values(decision_maker_contact_id=decider.id))
    await db.commit()

    body = await _mark(client, w, "salary_budget", "missing")

    [fu] = await _follow_ups(db, w["id"])
    assert fu.reason == "clarification" and fu.status == "open" and fu.company_id == w["company"].id and fu.contact_id == decider.id
    assert fu.created_by_user_id == w["recruiter"].id
    assert w["code"] in fu.notes and "Salary budget" in fu.notes
    assert timedelta(days=1, hours=23) < fu.due_at - fu.created_at <= timedelta(days=2, minutes=1)
    follow_up = _item(body, "salary_budget")["follow_up"]
    assert follow_up["id"] == str(fu.id) and follow_up["status"] == "open" and follow_up["contact"] == decider.name


async def test_the_follow_up_falls_back_from_an_inactive_decision_maker_to_the_primary_then_to_no_contact(client, db):
    w = await _world(client, db)
    await _mark(client, w, "openings", "missing")
    primary = CompanyContact(company_id=w["company"].id, name=f"Primary {_tag()}", is_primary=True)
    gone = CompanyContact(company_id=w["company"].id, name=f"Gone {_tag()}", active=False)
    db.add_all([primary, gone])
    await db.commit()
    await db.execute(Job.__table__.update().where(Job.id == w["id"]).values(decision_maker_contact_id=gone.id))
    await db.commit()
    await _mark(client, w, "timeline", "missing")
    none, with_primary = await _follow_ups(db, w["id"])
    assert none.contact_id is None and with_primary.contact_id == primary.id
    primary.is_primary = False
    await db.commit()
    await _mark(client, w, "role_scope", "missing")
    assert (await _follow_ups(db, w["id"]))[-1].contact_id is None


async def test_the_follow_up_appears_on_the_companys_list_with_its_reason(client, db):
    w = await _world(client, db)
    await _mark(client, w, "openings", "missing")
    response = await client.get(f"/api/v1/recruiter/companies/{w['company'].id}/follow-ups")
    assert response.status_code == 200, response.text
    [item] = response.json()["items"]
    assert item["reason"] == "clarification" and item["requirement"]["id"] == w["id"]


async def test_saving_the_same_status_again_changes_nothing(client, db):
    w = await _world(client, db)
    await _mark(client, w, "openings", "missing")
    await _mark(client, w, "openings", "missing")
    assert len(await _follow_ups(db, w["id"])) == 1
    assert len(await _audits(db, w["id"], "recruiter_requirement.checklist_item")) == 1


@pytest.mark.parametrize(("status", "closed"), [("confirmed", "done"), ("not_applicable", "cancelled")])
async def test_c5_leaving_missing_closes_its_open_follow_up(client, db, status, closed):
    w = await _world(client, db)
    await _mark(client, w, "openings", "missing")
    body = await _mark(client, w, "openings", status)
    [fu] = await _follow_ups(db, w["id"])
    assert fu.status == closed
    assert (fu.outcome if closed == "done" else fu.cancel_reason)
    assert _item(body, "openings")["follow_up"]["status"] == closed


async def test_c5_marking_missing_again_makes_a_new_follow_up(client, db):
    w = await _world(client, db)
    await _mark(client, w, "openings", "missing")
    await _mark(client, w, "openings", "confirmed")
    await _mark(client, w, "openings", "missing")
    assert [f.status for f in await _follow_ups(db, w["id"])] == ["done", "open"]


async def test_c5_a_follow_up_closed_by_hand_is_left_alone(client, db):
    w = await _world(client, db)
    await _mark(client, w, "openings", "missing")
    [fu] = await _follow_ups(db, w["id"])
    done = await client.post(f"/api/v1/recruiter/follow-ups/{fu.id}/complete", json={"outcome": "Client replied"})
    assert done.status_code == 200, done.text
    assert _item((await client.get(w["url"])).json(), "openings")["status"] == "missing"
    await _mark(client, w, "openings", "confirmed")
    [fu] = await _follow_ups(db, w["id"])
    assert fu.status == "done" and fu.outcome == "Client replied"


async def test_c4_the_open_follow_up_cap_refuses_and_saves_nothing(client, db, monkeypatch):
    monkeypatch.setattr(recruiter_follow_ups, "OPEN_CAP", 0)
    w = await _world(client, db)
    await _mark(client, w, "openings", "missing", expected=409)
    assert _item((await client.get(w["url"])).json(), "openings")["status"] is None
    assert await _follow_ups(db, w["id"]) == []


# --- AC2, C6-C9: the guard ---------------------------------------------------------------------------------------------------------------
async def test_with_the_rules_off_a_requirement_moves_as_before(client, db):
    w = await _world(client, db)
    assert (await _move(client, w, "sourcing"))["requirement"]["status"] == "sourcing"


async def test_ac2_with_blocking_on_moving_to_sourcing_is_a_409_listing_the_missing_items(client, db):
    w = await _world(client, db, blocks=True)
    await _mark_all(client, w, keys=KEYS[:6])
    await _mark(client, w, "commercial_terms", "missing")
    detail = (await _move(client, w, "sourcing", expected=409))["detail"]
    assert detail["code"] == "checklist_incomplete"
    assert detail["missing"] == [{"key": "commercial_terms", "label": "Commercial terms", "status": "missing"},
                                 {"key": "timeline", "label": "Joining date and turnaround", "status": None}]  # fmt: skip
    assert "Commercial terms" in detail["message"] and "Joining date and turnaround" in detail["message"]
    assert (await client.get(f"{BASE}/{w['id']}")).json()["requirement"]["status"] == "requirement_received"


async def test_a_complete_checklist_passes_the_guard(client, db):
    w = await _world(client, db, blocks=True)
    await _mark_all(client, w)
    assert (await _move(client, w, "sourcing"))["requirement"]["status"] == "sourcing"


@pytest.mark.parametrize("target", ["shortlisting", "profiles_shared", "interviewing", "selected"])
async def test_c8_skipping_sourcing_does_not_bypass_the_guard(client, db, target):
    w = await _world(client, db, blocks=True)
    assert (await _move(client, w, target, expected=409))["detail"]["code"] == "checklist_incomplete"


async def test_the_guard_leaves_other_moves_alone(client, db):
    w = await _world(client, db, blocks=True)
    assert (await _move(client, w, "on_hold"))["requirement"]["status"] == "on_hold"
    assert (await _move(client, w, "closed"))["requirement"]["status"] == "closed"


async def test_c9_a_requirement_already_started_is_never_blocked(client, db):
    w = await _world(client, db)
    await _move(client, w, "sourcing")
    await _move(client, w, "on_hold")
    await db.execute(Company.__table__.update().where(Company.id == w["company"].id).values(checklist_blocks_sourcing=True))
    await db.commit()
    assert (await _move(client, w, "sourcing"))["requirement"]["status"] == "sourcing"


async def test_c7_the_it_workflow_route_meets_the_same_guard(client, db):
    w = await _world(client, db, blocks=True)
    """`/workflows/it/jobs` moves a requirement through `change_status`, where the guard sits."""
    job = await db.get(Job, w["id"])
    with pytest.raises(HTTPException) as refused:
        await requirements.change_status(db, None, job, "sourcing")
    assert refused.value.status_code == 409 and refused.value.detail["code"] == "checklist_incomplete"


async def test_c6_the_company_rule_beats_the_global_rule(client, db, global_rule):
    db.add(RequirementChecklistSetting(id=1, block_sourcing=True))
    await db.commit()
    w = await _world(client, db)
    assert (await client.get(w["url"])).json()["blocking"] == {"on": True, "company_rule": None, "global_rule": True}
    await _move(client, w, "sourcing", expected=409)
    await db.execute(Company.__table__.update().where(Company.id == w["company"].id).values(checklist_blocks_sourcing=False))
    await db.commit()
    assert (await client.get(w["url"])).json()["blocking"] == {"on": False, "company_rule": False, "global_rule": True}
    await _move(client, w, "sourcing")


async def test_only_a_super_admin_sets_the_global_rule_and_it_is_audited(client, db, global_rule):
    w = await _world(client, db)
    assert (await client.put(RULES, json={"block_sourcing": True})).status_code == 403
    await login(client, w["manager"])
    assert (await client.put(RULES, json={"block_sourcing": True})).status_code == 403
    admin = await make_user(db, "super_admin", "it")
    await login(client, admin)
    response = await client.put(RULES, json={"block_sourcing": True})
    assert response.status_code == 200 and response.json() == {"block_sourcing": True}
    [row] = (await db.scalars(select(AuditLog).where(AuditLog.action == "requirement_checklist.global_rule", AuditLog.user_id == admin.id))).all()
    assert row.metadata_json["changes"] == {"block_sourcing": [False, True]}
    assert (await client.put(RULES, json={"block_sourcing": True})).status_code == 200  # no change, no second row
    assert len((await db.scalars(select(AuditLog).where(AuditLog.action == "requirement_checklist.global_rule", AuditLog.user_id == admin.id))).all()) == 1


async def test_the_company_rule_is_for_the_companys_manager_and_is_audited(client, db):
    w = await _world(client, db)
    url = f"/api/v1/recruiter/companies/{w['company'].id}/checklist-rule"
    assert (await client.put(url, json={"block_sourcing": True})).status_code == 403  # the recruiter
    await login(client, await make_pm(db))
    assert (await client.put(url, json={"block_sourcing": True})).status_code == 404  # another team's manager
    await login(client, w["manager"])
    assert (await client.put(url, json={})).status_code == 422  # the value must be stated: null means "use the global rule"
    response = await client.put(url, json={"block_sourcing": True})
    assert response.status_code == 200, response.text
    assert response.json() == {"block_sourcing": True}
    [row] = (await db.scalars(select(AuditLog).where(AuditLog.action == "requirement_checklist.company_rule", AuditLog.entity_id == str(w["company"].id)))).all()
    assert row.user_id == w["manager"].id and row.metadata_json["changes"] == {"block_sourcing": [None, True]}
    assert (await client.put(url, json={"block_sourcing": None})).json() == {"block_sourcing": None}


# --- C10: after sourcing has started, a warning only ------------------------------------------------------------------------------------
async def test_c10_editing_after_sourcing_started_warns_and_still_saves(client, db):
    w = await _world(client, db, blocks=True)
    await _mark_all(client, w)
    await _move(client, w, "sourcing")
    assert (await client.get(w["url"])).json()["warning"] is None
    body = await _mark(client, w, "salary_budget", "missing")
    assert body["sourcing_started"] is True and "already started" in body["warning"]
    assert _item(body, "salary_budget")["status"] == "missing"
    assert len(await _follow_ups(db, w["id"])) == 1
    assert (await client.get(f"{BASE}/{w['id']}")).json()["requirement"]["status"] == "sourcing"


# --- AC3, C11: the override ---------------------------------------------------------------------------------------------------------------
async def test_ac3_a_team_lead_override_is_audited_and_lets_the_owner_move(client, db):
    w = await _world(client, db, blocks=True)
    await _mark(client, w, "salary_budget", "missing")
    await _move(client, w, "sourcing", expected=409)

    await login(client, w["manager"])
    assert (await client.get(w["url"])).json()["can_override"] is True
    response = await client.post(f"{w['url']}/override", json={"reason": "Client is on leave; start sourcing now"})
    assert response.status_code == 200, response.text
    override = response.json()["override"]
    assert override["reason"] == "Client is on leave; start sourcing now" and override["by"]["id"] == str(w["manager"].id) and override["at"]
    assert response.json()["can_override"] is False

    [row] = await _audits(db, w["id"], "recruiter_requirement.checklist_override")
    assert row.user_id == w["manager"].id and row.metadata_json["reason"] == "Client is on leave; start sourcing now"
    assert "salary_budget" in row.metadata_json["incomplete"] and "timeline" in row.metadata_json["incomplete"]
    history = (await client.get(f"{BASE}/{w['id']}/history")).json()["items"]
    assert any(i["action"] == "recruiter_requirement.checklist_override" and i["changes"] for i in history)

    await login(client, w["recruiter"])
    assert (await _move(client, w, "sourcing"))["requirement"]["status"] == "sourcing"


async def test_an_override_needs_a_reason(client, db):
    w = await _world(client, db, blocks=True)
    await login(client, w["manager"])
    assert (await client.post(f"{w['url']}/override", json={})).status_code == 422
    assert (await client.post(f"{w['url']}/override", json={"reason": "   "})).status_code == 422


async def test_only_a_team_lead_or_super_admin_overrides(client, db):
    w = await _world(client, db, blocks=True)
    body = {"reason": "Please"}
    assert (await client.post(f"{w['url']}/override", json=body)).status_code == 403  # the recruiter
    assert (await client.get(w["url"])).json()["can_override"] is False
    await login(client, await make_pm(db))
    assert (await client.post(f"{w['url']}/override", json=body)).status_code == 404  # another team's manager
    await login(client, await make_user(db, "super_admin", "it"))
    assert (await client.post(f"{w['url']}/override", json=body)).status_code == 200


async def test_an_override_is_refused_when_nothing_is_being_blocked(client, db):
    w = await _world(client, db)  # the rule is off
    await login(client, w["manager"])
    url = f"{w['url']}/override"
    assert (await client.post(url, json={"reason": "x"})).status_code == 409
    assert (await client.get(w["url"])).json()["can_override"] is False

    await db.execute(Company.__table__.update().where(Company.id == w["company"].id).values(checklist_blocks_sourcing=True))
    await db.commit()
    assert (await client.post(url, json={"reason": "first"})).status_code == 200
    assert (await client.post(url, json={"reason": "second"})).status_code == 409  # already overridden

    complete = await _world(client, db, blocks=True)
    await _mark_all(client, complete)
    await login(client, complete["manager"])
    assert (await client.post(f"{complete['url']}/override", json={"reason": "x"})).status_code == 409

    started = await _world(client, db)
    await _move(client, started, "sourcing")
    await db.execute(Company.__table__.update().where(Company.id == started["company"].id).values(checklist_blocks_sourcing=True))
    await db.commit()
    await login(client, started["manager"])
    assert (await client.post(f"{started['url']}/override", json={"reason": "x"})).status_code == 409


# --- C12: who ---------------------------------------------------------------------------------------------------------------------------
async def test_scope_and_roles_on_the_items(client, db):
    w = await _world(client, db)
    assert (await client.get(w["url"])).json()["can_edit"] is True
    await login(client, w["outsider"])
    assert (await client.get(w["url"])).status_code == 404
    await _mark(client, w, "openings", "confirmed", expected=404)
    await login(client, w["manager"])  # reads and overrides, but is not a requirement writer (hrc-006 O5)
    assert (await client.get(w["url"])).json()["can_edit"] is False
    await _mark(client, w, "openings", "confirmed", expected=403)
    await login(client, await make_user(db, "student", "it"))
    assert (await client.get(w["url"])).status_code == 403


async def test_a_placement_officer_on_the_requirement_answers_items_and_gets_a_follow_up_made(client, db):
    w = await _world(client, db)
    officer = await make_user(db, "placement_officer", "it", name=f"Officer {_tag()}")
    added = await client.post(f"{BASE}/{w['id']}/assignments", json={"user_id": str(officer.id), "role": "placement_officer"})
    assert added.status_code == 201, added.text
    await login(client, officer)
    await _mark(client, w, "openings", "missing")  # the officer has no company scope; the requirement's scope is what counts
    [fu] = await _follow_ups(db, w["id"])
    assert fu.created_by_user_id == officer.id
    await _mark(client, w, "openings", "confirmed")
    assert (await _follow_ups(db, w["id"]))[0].status == "done"


async def test_a_cancelled_requirement_refuses_the_checklist_writes(client, db):
    w = await _world(client, db, blocks=True)
    await _move(client, w, "cancelled")
    await _mark(client, w, "openings", "confirmed", expected=409)
    await login(client, w["manager"])
    assert (await client.post(f"{w['url']}/override", json={"reason": "x"})).status_code == 409


# --- C13, C14 ---------------------------------------------------------------------------------------------------------------------------
async def test_c13_answering_an_item_does_not_move_the_requirements_token(client, db):
    w = await _world(client, db)
    before = (await client.get(f"{BASE}/{w['id']}")).json()["requirement"]["updated_at"]
    await _mark(client, w, "openings", "missing")
    assert (await client.get(f"{BASE}/{w['id']}")).json()["requirement"]["updated_at"] == before


async def test_c14_an_answer_is_audited_with_labels_and_shows_in_the_history(client, db):
    w = await _world(client, db)
    await _mark(client, w, "openings", "missing")
    await _mark(client, w, "openings", "confirmed")
    first, second = await _audits(db, w["id"], "recruiter_requirement.checklist_item")
    assert first.user_id == w["recruiter"].id and first.metadata_json["item"] == "openings"
    assert first.metadata_json["changes"] == {"Number of openings": ["Not reviewed", "Missing"]}
    assert second.metadata_json["changes"] == {"Number of openings": ["Missing", "Confirmed"]}
    items = (await client.get(f"{BASE}/{w['id']}/history")).json()["items"]
    assert sum(i["action"] == "recruiter_requirement.checklist_item" for i in items) == 2


async def test_the_read_makes_a_bounded_number_of_queries(client, db):
    """One query for the items (their follow-ups, contacts and authors joined), however many are answered."""
    w = await _world(client, db)
    await _mark(client, w, "openings", "missing")
    job = await db.get(Job, w["id"])
    statements = []

    def count(_conn, _cursor, statement, *_rest):
        if statement.lstrip().upper().startswith("SELECT") and "job_checklist_items" in statement:
            statements.append(statement)

    engine = (await db.connection()).sync_engine
    event.listen(engine, "before_cursor_execute", count)
    try:
        await checklist.view(db, job)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert len(statements) == 1


@pytest.mark.parametrize("module", ["app.services.recruiter_requirements", "app.services.applications", "app.services.requirement_checklist", "app.seed"])
async def test_each_module_imports_in_a_fresh_interpreter(module):
    """QA-01: `python -m app.seed` and the worker start without `app.main`, which every test here has already imported, so only a new interpreter sees an import cycle."""
    done = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-600:]
