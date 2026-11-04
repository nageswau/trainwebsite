"""hrc-024 (DEC-SCOPE-393, spec docs/superpowers/specs/2026-11-04-hrc-024-candidate-routing-design.md): a website candidate is routed by the
default recruiter, then source, skill-category and location rules (R1-R5, AC1/AC2), by round robin or least workload inside a rule's group
(R6), or goes to the unassigned queue with an alert (R9, AC3); the assignment is notified and in hrc-012's history (R8, AC4). Settings and
rules are the placement manager's (R11)."""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.models import (
    AuditLog,
    Candidate,
    CandidateAssignmentHistory,
    CandidateRoutingRule,
    CandidateRoutingSetting,
    CandidateSkill,
    Notification,
    RecCandidateSource,
    Skill,
    SkillCategory,
)
from app.services import candidate_routing as routing
from app.services import website_intake as intake
from tests.rec038_helpers import _recruiter, _user, add, make_candidate, tag
from tests.tel026_helpers import headers
from tests.test_hrc_008_visibility import _job

pytestmark = pytest.mark.asyncio
URL = "/api/v1/recruiter/candidate-routing"


@pytest_asyncio.fixture
async def clean(db_session):
    """Routing is global (one settings row, one rule table): each test starts with none and the stored ones come back after."""
    db = db_session
    setting = await db.get(CandidateRoutingSetting, 1)
    saved_setting = (setting.default_recruiter_user_id, setting.strategy) if setting else None
    rules = [{c.name: getattr(r, c.name) for c in CandidateRoutingRule.__table__.columns} for r in (await db.scalars(select(CandidateRoutingRule))).all()]
    await db.execute(delete(CandidateRoutingRule))
    await db.execute(delete(CandidateRoutingSetting))
    await db.commit()
    yield
    await db.rollback()
    await db.execute(delete(CandidateRoutingRule))
    await db.execute(delete(CandidateRoutingSetting))
    if saved_setting:
        db.add(CandidateRoutingSetting(id=1, default_recruiter_user_id=saved_setting[0], strategy=saved_setting[1]))
    db.add_all(CandidateRoutingRule(**r) for r in rules)
    await db.commit()


async def _world(db):
    manager = await _user(db, "placement_manager", "global")
    rec, rec2 = await _recruiter(db, manager), await _recruiter(db, manager)
    return manager, rec, rec2


async def _source(db) -> RecCandidateSource:
    return await add(db, RecCandidateSource(name=tag("Src ")))


async def _category(db) -> SkillCategory:
    return await add(db, SkillCategory(name=tag("Cat ")))


async def _candidate(db, creator, source=None, **fields) -> Candidate:
    candidate = await make_candidate(db, creator, **fields)
    if source is not None:
        candidate.source_id = source.id
    await db.flush()
    return candidate


async def _rule(db, kind, recruiter, **value) -> CandidateRoutingRule:
    return await add(db, CandidateRoutingRule(kind=kind, recruiter_user_id=recruiter.id, **value))


async def _route(db, candidate):
    owner = await routing.on_website_candidate(db, candidate)
    await db.commit()
    return owner


async def _notices(db, user, event):
    return (await db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.event_type == event))).all()


# --- AC1: each rule type ---------------------------------------------------------------------------------------------------------------
async def test_a_source_rule_routes_to_its_recruiter_with_history_audit_and_notice(db_session, clean):
    manager, rec, _ = await _world(db_session)
    source = await _source(db_session)
    rule = await _rule(db_session, "source", rec, source_id=source.id)
    candidate = await _candidate(db_session, manager, source)
    cid = candidate.id

    owner = await _route(db_session, candidate)

    assert owner == rec.id
    assert (await db_session.get(Candidate, cid)).owner_user_id == rec.id
    history = (await db_session.scalars(select(CandidateAssignmentHistory).where(CandidateAssignmentHistory.candidate_id == cid))).all()
    assert [(h.kind, h.from_user_id, h.to_user_id, h.changed_by_user_id, h.reason) for h in history] == [("owner", None, rec.id, None, "route")]  # AC4
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(cid), AuditLog.action == "candidate.assign"))
    assert audit.user_id is None and audit.metadata_json["reason"] == "route"
    assert audit.metadata_json["method"] == "source_rule" and audit.metadata_json["rule_id"] == str(rule.id)
    notices = await _notices(db_session, rec, "it.candidate.assigned")
    assert [(n.entity_id, n.action_url) for n in notices] == [(str(cid), f"/recruiter/candidates/{cid}")]


async def test_a_skill_category_rule_routes_by_a_skill_of_that_category(db_session, clean):
    manager, rec, _ = await _world(db_session)
    category = await _category(db_session)
    skill = await add(db_session, Skill(name=tag("Skl "), category_id=category.id))
    await _rule(db_session, "skill_category", rec, skill_category_id=category.id)
    candidate = await _candidate(db_session, manager, await _source(db_session))
    await add(db_session, CandidateSkill(candidate_id=candidate.id, skill_id=skill.id, level="beginner", added_by_user_id=manager.id))

    assert await _route(db_session, candidate) == rec.id


async def test_a_location_rule_matches_the_city_or_location_case_insensitively(db_session, clean):
    manager, rec, rec2 = await _world(db_session)
    city = tag("Pune")
    await _rule(db_session, "location", rec, location=city)
    await _rule(db_session, "location", rec2, location=f"{city}x")
    by_city = await _candidate(db_session, manager, await _source(db_session), city=f"  {city.upper()} ")
    by_location = await _candidate(db_session, manager, await _source(db_session), location=f"{city.lower()}x")

    assert await _route(db_session, by_city) == rec.id
    assert await _route(db_session, by_location) == rec2.id


async def test_rule_kinds_apply_in_order_source_then_category_then_location(db_session, clean):
    manager, rec, rec2 = await _world(db_session)
    rec3 = await _recruiter(db_session, manager)
    source, category, city = await _source(db_session), await _category(db_session), tag("City")
    skill = await add(db_session, Skill(name=tag("Skl "), category_id=category.id))
    await _rule(db_session, "location", rec3, location=city)
    await _rule(db_session, "skill_category", rec2, skill_category_id=category.id)
    candidate = await _candidate(db_session, manager, source, city=city)
    await add(db_session, CandidateSkill(candidate_id=candidate.id, skill_id=skill.id, level="beginner", added_by_user_id=manager.id))
    assert await _route(db_session, candidate) == rec2.id  # the category beats the location

    await _rule(db_session, "source", rec, source_id=source.id)
    again = await _candidate(db_session, manager, source, city=city)
    await add(db_session, CandidateSkill(candidate_id=again.id, skill_id=skill.id, level="beginner", added_by_user_id=manager.id))
    assert await _route(db_session, again) == rec.id  # the source beats both


# --- AC2: the default recruiter ------------------------------------------------------------------------------------------------------
async def test_the_default_recruiter_overrides_every_rule_while_active(db_session, clean):
    manager, rec, rec2 = await _world(db_session)
    source = await _source(db_session)
    await _rule(db_session, "source", rec, source_id=source.id)
    db_session.add(CandidateRoutingSetting(id=1, default_recruiter_user_id=rec2.id, strategy="round_robin"))
    await db_session.flush()

    first = await _candidate(db_session, manager, source)
    assert await _route(db_session, first) == rec2.id
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(first.id), AuditLog.action == "candidate.assign"))
    assert audit.metadata_json["method"] == "default_recruiter"

    rec2.active = False  # R4: an inactive default recruiter -> the rules apply
    second = await _candidate(db_session, manager, source)
    assert await _route(db_session, second) == rec.id


# --- AC3 / R9: no match -> the queue and an alert ----------------------------------------------------------------------------------------
async def test_no_match_leaves_the_candidate_unassigned_and_alerts_managers_and_hr_managers(db_session, clean):
    manager, rec, _ = await _world(db_session)
    hr = await _user(db_session, "hr_manager", "it")
    await _rule(db_session, "source", rec, source_id=(await _source(db_session)).id)
    candidate = await _candidate(db_session, manager, await _source(db_session))
    cid = candidate.id

    assert await _route(db_session, candidate) is None

    assert (await db_session.get(Candidate, cid)).owner_user_id is None
    [mine] = await _notices(db_session, manager, "it.candidate.unassigned")
    assert (mine.entity_id, mine.action_url, mine.title) == (str(cid), "/recruiter/candidates?owner=unassigned", "Candidate needs a recruiter")
    [theirs] = await _notices(db_session, hr, "it.candidate.unassigned")
    assert theirs.action_url is None  # hr_manager has no candidate screens
    assert not await _notices(db_session, rec, "it.candidate.assigned")


async def test_inactive_rule_recruiters_put_the_candidate_in_the_queue(db_session, clean):
    manager, rec, rec2 = await _world(db_session)
    source = await _source(db_session)
    await _rule(db_session, "source", rec, source_id=source.id)
    await _rule(db_session, "source", rec2, source_id=source.id)
    rec.active = rec2.active = False
    candidate = await _candidate(db_session, manager, source)
    assert await _route(db_session, candidate) is None


async def test_an_unexpected_routing_error_leaves_the_candidate_unassigned_and_alerted(db_session, clean, monkeypatch):
    manager, rec, _ = await _world(db_session)
    source = await _source(db_session)
    await _rule(db_session, "source", rec, source_id=source.id)
    candidate = await _candidate(db_session, manager, source)
    cid = candidate.id

    async def boom(*_):
        raise RuntimeError("boom")

    monkeypatch.setattr(routing, "_choose", boom)
    assert await _route(db_session, candidate) is None
    assert (await db_session.get(Candidate, cid)).owner_user_id is None
    assert await _notices(db_session, manager, "it.candidate.unassigned")


# --- R6: the strategy inside a group --------------------------------------------------------------------------------------------------
async def test_round_robin_takes_turns_among_a_rule_groups_recruiters(db_session, clean):
    manager, rec, rec2 = await _world(db_session)
    source = await _source(db_session)
    await _rule(db_session, "source", rec, source_id=source.id)
    await _rule(db_session, "source", rec2, source_id=source.id)
    owners = [await _route(db_session, await _candidate(db_session, manager, source)) for _ in range(4)]
    assert set(owners) == {rec.id, rec2.id}
    assert owners[0] != owners[1] and owners[0] == owners[2] and owners[1] == owners[3]


async def test_least_workload_picks_the_recruiter_with_fewest_open_candidates(db_session, clean):
    manager, rec, rec2 = await _world(db_session)
    source = await _source(db_session)
    await _rule(db_session, "source", rec, source_id=source.id)
    await _rule(db_session, "source", rec2, source_id=source.id)
    db_session.add(CandidateRoutingSetting(id=1, strategy="least_workload"))
    busy, idle = sorted([rec, rec2], key=lambda u: u.id)  # round robin would start with the lower id
    await _candidate(db_session, manager, owner_user_id=busy.id)
    archived = await _candidate(db_session, manager, owner_user_id=idle.id)
    archived.archived_at = datetime.now(UTC)  # not open work
    await db_session.flush()

    assert await _route(db_session, await _candidate(db_session, manager, source)) == idle.id


# --- R7: the website paths ---------------------------------------------------------------------------------------------------------------
async def test_a_website_application_routes_a_new_candidate_but_not_a_matched_one(client, db_session, clean):
    manager, rec, _ = await _world(db_session)
    website = await intake.source_id(db_session)
    await _rule(db_session, "source", rec, source_id=website)
    job = await _job(db_session)
    email = f"{tag('w24-')}@example.com"
    body = {"full_name": "Asha Web", "email": email, "phone": None, "resume_url": "/local-files/career-resumes/x.pdf", "cover_note": "Hi"}
    ip = {"X-Forwarded-For": f"2001:db8::{uuid.uuid4().hex[:4]}"}

    assert (await client.post(f"/api/v1/public/jobs/{job.id}/apply", json=body, headers=ip)).status_code == 201
    candidate = await db_session.scalar(select(Candidate).where(Candidate.email == email))
    assert candidate.owner_user_id == rec.id

    candidate.owner_user_id = None  # a matched candidate keeps what it has: routing runs only on create
    await db_session.commit()
    assert (await client.post(f"/api/v1/public/jobs/{job.id}/apply", json=body, headers=ip)).status_code == 201
    await db_session.refresh(candidate)
    assert candidate.owner_user_id is None


async def test_portal_verification_routes_the_candidate_it_creates(db_session, clean):
    from app.services import candidate_portal as portal

    manager, rec, _ = await _world(db_session)
    await _rule(db_session, "source", rec, source_id=await intake.source_id(db_session))
    user = await _user(db_session, "candidate", "it")
    user.email = f"{tag('p24-')}@example.com"
    user.phone = None
    candidate = await portal.link_candidate(db_session, user, "127.0.0.1")
    await db_session.commit()
    assert candidate.owner_user_id == rec.id


# --- R11: the routes -------------------------------------------------------------------------------------------------------------------
async def test_a_manager_configures_routing_and_every_change_is_audited(client, db_session, clean):
    manager, rec, rec2 = await _world(db_session)
    source = await _source(db_session)
    await db_session.commit()
    h = headers(manager)

    empty = (await client.get(URL, headers=h)).json()
    assert empty == {"default_recruiter": None, "strategy": "round_robin", "rules": [], "can_edit": True}

    saved = await client.put(URL, json={"default_recruiter_user_id": str(rec2.id), "strategy": "least_workload"}, headers=h)
    assert saved.status_code == 200, saved.text
    assert saved.json()["default_recruiter"]["id"] == str(rec2.id) and saved.json()["strategy"] == "least_workload"

    made = await client.post(f"{URL}/rules", json={"kind": "source", "source_id": str(source.id), "recruiter_user_id": str(rec.id)}, headers=h)
    assert made.status_code == 201, made.text
    rule = made.json()
    assert (rule["kind"], rule["value_label"], rule["recruiter"]["id"]) == ("source", source.name, str(rec.id))
    city = await client.post(f"{URL}/rules", json={"kind": "location", "location": "  Pune ", "recruiter_user_id": str(rec.id)}, headers=h)
    assert city.json()["value_label"] == "Pune"

    listed = (await client.get(URL, headers=h)).json()["rules"]
    assert [r["kind"] for r in listed] == ["source", "location"]  # routing order

    duplicate = await client.post(f"{URL}/rules", json={"kind": "location", "location": "pune", "recruiter_user_id": str(rec.id)}, headers=h)
    assert duplicate.status_code == 409

    assert (await client.delete(f"{URL}/rules/{rule['id']}", headers=h)).status_code == 204
    assert (await client.delete(f"{URL}/rules/{rule['id']}", headers=h)).status_code == 404
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.user_id == manager.id, AuditLog.action.like("candidate.routing%")))).all()
    assert sorted(actions) == ["candidate.routing_rule_add", "candidate.routing_rule_add", "candidate.routing_rule_delete", "candidate.routing_settings"]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"kind": "location", "recruiter_user_id": "R"}, "Enter a location"),
        ({"kind": "source", "location": "Pune", "recruiter_user_id": "R"}, "Choose a candidate source"),
        ({"kind": "skill_category", "recruiter_user_id": "R"}, "Choose a skill category"),
        ({"kind": "source", "source_id": str(uuid.uuid4()), "recruiter_user_id": "R"}, "Choose a candidate source"),
        ({"kind": "skill_category", "skill_category_id": str(uuid.uuid4()), "recruiter_user_id": "R"}, "Choose a skill category"),
        ({"kind": "location", "location": "Pune", "recruiter_user_id": str(uuid.uuid4())}, "Choose an active recruiter"),
        ({"kind": "branch", "location": "Pune", "recruiter_user_id": "R"}, "Rule type"),
        ({"kind": "location", "location": "x" * 81, "recruiter_user_id": "R"}, "Location"),
    ],
)
async def test_a_rule_is_validated(client, db_session, clean, body, message):
    manager, rec, _ = await _world(db_session)
    await db_session.commit()
    body = {k: (str(rec.id) if v == "R" else v) for k, v in body.items()}
    response = await client.post(f"{URL}/rules", json=body, headers=headers(manager))
    assert response.status_code == 422 and message in response.json()["detail"], response.text


async def test_settings_are_validated(client, db_session, clean):
    manager, rec, _ = await _world(db_session)
    officer = await _user(db_session, "placement_officer", "it")
    await db_session.commit()
    h = headers(manager)
    bad = await client.put(URL, json={"default_recruiter_user_id": str(officer.id), "strategy": "round_robin"}, headers=h)
    assert bad.status_code == 422 and "Choose an active recruiter" in bad.json()["detail"]
    assert (await client.put(URL, json={"default_recruiter_user_id": None, "strategy": "random"}, headers=h)).status_code == 422
    cleared = await client.put(URL, json={"default_recruiter_user_id": None, "strategy": "round_robin"}, headers=h)
    assert cleared.status_code == 200 and cleared.json()["default_recruiter"] is None


@pytest.mark.parametrize("role", ["placement_team", "hr_manager", "hr_team", "placement_officer", "telecaller"])
async def test_only_managers_and_super_admin_see_or_change_routing(client, db_session, clean, role):
    user = await _user(db_session, role, "it")
    await db_session.commit()
    h = headers(user)
    assert (await client.get(URL, headers=h)).status_code == 403
    assert (await client.put(URL, json={"default_recruiter_user_id": None, "strategy": "round_robin"}, headers=h)).status_code == 403
    assert (await client.post(f"{URL}/rules", json={"kind": "location", "location": "Pune", "recruiter_user_id": str(user.id)}, headers=h)).status_code == 403
    assert (await client.delete(f"{URL}/rules/{uuid.uuid4()}", headers=h)).status_code == 403
    admin = await _user(db_session, "super_admin", "global")
    await db_session.commit()
    assert (await client.get(URL, headers=headers(admin))).status_code == 200
