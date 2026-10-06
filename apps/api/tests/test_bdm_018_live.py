"""bdm-018 -- the live School stages from the linked School's data (spec §4; AC4, H2) and SchoolOut.linked_bdm (spec §5.6)."""

from uuid import UUID, uuid4

import pytest

from app.models import (
    OverseasApplication,
    PortfolioEntry,
    PortfolioProfile,
    SchoolCareerRecord,
    SchoolParentLink,
    SchoolPsychometricRecord,
    SchoolStudent,
)
from tests.agn003_helpers import mk_university
from tests.bdm001_helpers import login, make_user
from tests.bdm002_helpers import ORGS
from tests.bdm018_helpers import QUEUE, SCHOOLS, pending_request, requested, school_payload, school_world, user

LIVE = ("school_onboarding", "users_created", "career_guidance", "psychometric", "profile_building", "university_planning")


async def _states(client, db, w) -> dict[str, str]:
    await login(client, await user(db, w["ids"]["owner"]))
    steps = (await client.get(f"{ORGS}/{w['org']['id']}")).json()["organization"]["pipeline"]["steps"]
    return {s["key"]: s["state"] for s in steps}


async def _linked(client, db) -> dict:
    """A School organization linked to a fresh School created from its request; returns the world with `school` (id string)."""
    w = await pending_request(client, db)
    response = await client.post(SCHOOLS, json=school_payload(bdm_onboarding_request_id=w["item"]["id"]))
    assert response.status_code == 201, response.text
    w["school"] = response.json()
    return w


async def _student(db, w) -> SchoolStudent:
    code = uuid4().hex[:8].upper()
    student = SchoolStudent(school_id=UUID(w["school"]["id"]), student_code=code, full_name="Student One", created_by_user_id=w["ids"]["admin"])
    db.add(student)
    await db.commit()
    return student


@pytest.mark.asyncio
async def test_without_a_request_or_link_live_steps_await_handover(client, db_session):
    w = await school_world(client, db_session)
    states = await _states(client, db_session, w)
    assert states["signed"] == "current"
    assert all(states[k] == "awaiting_handover" for k in LIVE)


@pytest.mark.asyncio
async def test_a_pending_request_makes_school_onboarding_current(client, db_session):
    w = await school_world(client, db_session)
    await requested(client, w["org"])
    states = await _states(client, db_session, w)
    assert states["signed"] == "done"
    assert states["school_onboarding"] == "current"
    assert all(states[k] == "upcoming" for k in LIVE[1:])


@pytest.mark.asyncio
async def test_a_rejected_request_returns_to_awaiting_handover(client, db_session):
    w = await pending_request(client, db_session)
    await client.post(f"{QUEUE}/{w['item']['id']}/reject", json={"reason": "Not yet"})
    states = await _states(client, db_session, w)
    assert states["signed"] == "current" and states["school_onboarding"] == "awaiting_handover"


@pytest.mark.asyncio
async def test_once_linked_each_live_step_follows_its_own_evidence(client, db_session):
    w = await _linked(client, db_session)
    states = await _states(client, db_session, w)
    assert (states["school_onboarding"], states["users_created"]) == ("done", "current")
    assert all(states[k] == "upcoming" for k in LIVE[2:])

    student_id = (await _student(db_session, w)).id
    teacher = await make_user(db_session, "school_teacher", "overseas")
    teacher.profile = {"school_id": w["school"]["id"]}
    await db_session.commit()
    assert (await _states(client, db_session, w))["users_created"] == "current"  # no parent yet: all three are needed
    parent_id = (await make_user(db_session, "school_parent", "overseas")).id
    db_session.add(SchoolParentLink(parent_user_id=parent_id, school_student_id=student_id, linked_by_user_id=w["ids"]["admin"]))
    await db_session.commit()
    states = await _states(client, db_session, w)
    assert (states["users_created"], states["career_guidance"]) == ("done", "current")

    counselor_id = (await make_user(db_session, "career_counselor", "overseas")).id
    db_session.add(SchoolCareerRecord(school_student_id=student_id, career_counselor_user_id=counselor_id, record_type="guidance_session", notes="x", status="scheduled"))
    await db_session.commit()
    assert (await _states(client, db_session, w))["career_guidance"] == "current"  # scheduled is not completed
    db_session.add(SchoolCareerRecord(school_student_id=student_id, career_counselor_user_id=counselor_id, record_type="guidance_session", notes="x", status="completed"))
    # Per-step evidence (H2): a later step is done on its own even while an earlier one is not.
    db_session.add(PortfolioEntry(school_student_id=student_id, section="project", title="Robot", created_by_user_id=w["ids"]["admin"], updated_by_user_id=w["ids"]["admin"]))
    await db_session.commit()
    states = await _states(client, db_session, w)
    assert (states["career_guidance"], states["psychometric"], states["profile_building"]) == ("done", "current", "done")

    team_id = (await make_user(db_session, "psychometric_team", "overseas")).id
    db_session.add(SchoolPsychometricRecord(school_student_id=student_id, psychometric_team_user_id=team_id, assessment_type="Aptitude", status="assigned"))
    await db_session.commit()
    assert (await _states(client, db_session, w))["psychometric"] == "current"
    db_session.add(SchoolPsychometricRecord(school_student_id=student_id, psychometric_team_user_id=team_id, assessment_type="Aptitude", status="completed"))
    await db_session.commit()
    states = await _states(client, db_session, w)
    assert (states["psychometric"], states["university_planning"]) == ("done", "current")

    university_id = (await mk_university(db_session)).id
    db_session.add(OverseasApplication(school_student_id=student_id, university_id=university_id, intake="Fall 2027"))
    await db_session.commit()
    states = await _states(client, db_session, w)
    assert all(states[k] == "done" for k in LIVE)
    stage = (await client.get(f"{ORGS}/{w['org']['id']}")).json()["organization"]["pipeline"]["stage"]
    assert stage == "signed"  # H11: live stages are never stored


@pytest.mark.asyncio
async def test_a_personal_statement_alone_counts_as_profile_building(client, db_session):
    w = await _linked(client, db_session)
    student_id = (await _student(db_session, w)).id
    profile = PortfolioProfile(school_student_id=student_id, personal_statement=None)
    db_session.add(profile)
    await db_session.commit()
    profile_id = profile.id
    assert (await _states(client, db_session, w))["profile_building"] == "upcoming"
    (await db_session.get_one(PortfolioProfile, profile_id)).personal_statement = "I like physics."
    await db_session.commit()
    assert (await _states(client, db_session, w))["profile_building"] == "done"


@pytest.mark.asyncio
async def test_school_out_names_the_linked_bdm_on_list_lookup_and_patch(client, db_session):
    w = await _linked(client, db_session)
    expected = {"full_name": w["owner"].full_name, "active": True, "organization_code": w["org"]["code"]}
    code, school_id = w["school"]["school_code"], w["school"]["id"]
    listed = next(s for s in (await client.get(SCHOOLS)).json() if s["id"] == school_id)
    assert listed["linked_bdm"] == expected
    assert (await client.get(f"{SCHOOLS}/lookup", params={"code": code})).json()["linked_bdm"] == expected
    patched = await client.patch(f"{SCHOOLS}/{school_id}", json={"branch": "North"})
    assert patched.json()["linked_bdm"] == expected


@pytest.mark.asyncio
async def test_a_school_coordinator_never_receives_bdm_data(client, db_session):
    w = await _linked(client, db_session)
    coordinator = await make_user(db_session, "school_coordinator", "overseas")
    coordinator.profile = {"school_id": w["school"]["id"]}
    await db_session.commit()
    await login(client, coordinator)
    assert (await client.get(SCHOOLS)).status_code == 403
    assert (await client.get(QUEUE)).status_code == 403
    assert (await client.get(f"{ORGS}/{w['org']['id']}")).status_code == 403
