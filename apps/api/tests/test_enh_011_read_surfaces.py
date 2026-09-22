import pytest
from enh005_helpers import move_student_directly
from enh011_helpers import BATCHES, ENROLMENTS, SESSIONS, create_batch, enrol, login, skills_world
from sqlalchemy import update

from app.models import School

# ENH-011 spec §5.2: Skills in the SCH-007 overview, the SCH-008 timeline and the SCH-011 entitlements -- read in each role's
# EXISTING scope (parent: linked child; teacher: assigned; coordinator/principal: own school). AC-07, AC-08, AC-09.

OVERVIEW = "/api/v1/school/students/{sid}/overview"
TIMELINE = "/api/v1/school/students/{sid}/timeline"


async def _tracked(client, w):
    """kid0: a certified Soft Skills enrolment with attendance and a score; a withdrawn Digital Skills enrolment."""
    kid0 = w["a"]["students"][0]
    await login(client, w["counselor"].email)
    soft = await create_batch(client, w["a"]["school"].id, title="Leadership", topic="Teamwork", trainer_name="R. Iyer")
    digital = await create_batch(client, w["a"]["school"].id, module_type="digital_skills", title="Coding")
    [s_row] = await enrol(client, soft["id"], kid0)
    [d_row] = await enrol(client, digital["id"], kid0)
    session = (await client.post(f"{BATCHES}/{soft['id']}/sessions", json={"session_date": "2026-10-05"})).json()
    await client.put(f"{SESSIONS}/{session['id']}/attendance", json={"records": [{"enrollment_id": s_row["id"], "present": True}]})
    assessment = (await client.post(f"{BATCHES}/{soft['id']}/assessments", json={"name": "Speech", "max_score": 20})).json()
    await client.put(f"/api/v1/school/career-counselor/skill-assessments/{assessment['id']}/scores", json={"scores": [{"enrollment_id": s_row["id"], "score": 16, "remarks": "Pace"}]})
    await client.patch(f"{ENROLMENTS}/{s_row['id']}", json={"status": "completed"})
    await client.patch(f"{ENROLMENTS}/{s_row['id']}", json={"status": "certified"})
    await client.patch(f"{ENROLMENTS}/{d_row['id']}", json={"status": "withdrawn"})
    return kid0, soft, digital


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["parent", "teacher", "coordinator", "principal"])
async def test_overview_has_skills_block_in_every_reader_scope(client, db_session, who):
    w = await skills_world(db_session)
    kid0, _soft, _digital = await _tracked(client, w)
    await login(client, w["a"][who].email)
    skills = (await client.get(OVERVIEW.format(sid=kid0.id))).json()["skills"]
    assert skills["soft_skills"]["status"] == "certified"
    [enrolment] = skills["soft_skills"]["enrollments"]
    assert enrolment["batch_title"] == "Leadership" and enrolment["topic"] == "Teamwork" and enrolment["trainer_name"] == "R. Iyer"
    assert enrolment["status"] == "certified" and enrolment["attendance"] == {"present": 1, "marked": 1}
    assert enrolment["assessments"] == [{"name": "Speech", "max_score": 20.0, "score": 16.0, "remarks": "Pace"}]
    # Withdrawn only: shown, but the module reads as not started.
    assert skills["digital_skills"]["status"] == "not_started" and skills["digital_skills"]["enrollments"][0]["status"] == "withdrawn"


@pytest.mark.asyncio
async def test_overview_skills_rollup_and_empty_block(client, db_session):
    w = await skills_world(db_session)
    kid0, kid1 = w["a"]["students"]
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    [row] = await enrol(client, batch["id"], kid0)
    await login(client, w["a"]["coordinator"].email)
    assert (await client.get(OVERVIEW.format(sid=kid0.id))).json()["skills"]["soft_skills"]["status"] == "in_progress"
    assert (await client.get(OVERVIEW.format(sid=kid1.id))).json()["skills"] == {"soft_skills": {"status": "not_started", "enrollments": []}, "digital_skills": {"status": "not_started", "enrollments": []}}
    await login(client, w["counselor"].email)
    await client.patch(f"{ENROLMENTS}/{row['id']}", json={"status": "completed"})
    await login(client, w["a"]["coordinator"].email)
    assert (await client.get(OVERVIEW.format(sid=kid0.id))).json()["skills"]["soft_skills"]["status"] == "completed"


@pytest.mark.asyncio
async def test_other_students_skills_never_leak(client, db_session):
    w = await skills_world(db_session)
    kid0, _soft, _digital = await _tracked(client, w)
    kid1 = w["a"]["students"][1]
    await login(client, w["a"]["parent"].email)  # linked to kid0 only
    assert (await client.get(OVERVIEW.format(sid=kid1.id))).status_code == 403
    await login(client, w["a"]["teacher"].email)  # assigned kid0 only
    assert (await client.get(OVERVIEW.format(sid=kid1.id))).status_code == 403
    await login(client, w["b"]["coordinator"].email)
    assert (await client.get(OVERVIEW.format(sid=kid0.id))).status_code == 403
    assert (await client.get(TIMELINE.format(sid=kid0.id))).status_code == 403


@pytest.mark.asyncio
async def test_timeline_has_enrolled_completed_certified_events(client, db_session):
    w = await skills_world(db_session)
    kid0, _soft, _digital = await _tracked(client, w)
    await login(client, w["a"]["parent"].email)
    events = [(e["category"], e["type"], e["title"]) for e in (await client.get(TIMELINE.format(sid=kid0.id))).json()["events"] if e["category"] in {"soft_skills", "digital_skills"}]
    assert ("soft_skills", "skill_enrolled", "Enrolled in Leadership") in events
    assert ("soft_skills", "skill_completed", "Completed Leadership") in events
    assert ("soft_skills", "skill_certified", "Certified in Leadership") in events
    assert ("digital_skills", "skill_enrolled", "Enrolled in Coding") in events
    assert not any(t == "skill_completed" for c, t, _ in events if c == "digital_skills")


@pytest.mark.asyncio
async def test_frozen_enrolment_still_visible_at_the_new_school(client, db_session):
    w = await skills_world(db_session)
    kid0, _soft, _digital = await _tracked(client, w)
    await move_student_directly(db_session, kid0, w["b"]["school"])
    await login(client, w["b"]["coordinator"].email)
    skills = (await client.get(OVERVIEW.format(sid=kid0.id))).json()["skills"]
    assert skills["soft_skills"]["status"] == "certified" and skills["soft_skills"]["enrollments"][0]["frozen"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("tier,expected", [("bronze", {"soft_skills": 2}), ("silver", {"soft_skills": 2, "web_designing": 1})])
async def test_entitlements_count_non_withdrawn_enrolments(client, db_session, tier, expected):
    w = await skills_world(db_session)
    await db_session.execute(update(School).where(School.id == w["a"]["school"].id).values(tier=tier))
    await db_session.commit()
    kid0, kid1 = w["a"]["students"]
    await login(client, w["counselor"].email)
    soft = await create_batch(client, w["a"]["school"].id)
    digital = await create_batch(client, w["a"]["school"].id, module_type="digital_skills")
    await enrol(client, soft["id"], kid0, kid1)
    rows = await enrol(client, digital["id"], kid0, kid1)
    await client.patch(f"{ENROLMENTS}/{rows[0]['id']}", json={"status": "withdrawn"})
    await login(client, w["a"]["coordinator"].email)
    services = {s["key"]: s["used"] for s in (await client.get("/api/v1/school/entitlements")).json()["services"]}
    assert {k: services[k] for k in expected} == expected
    if tier == "bronze":
        assert "web_designing" not in services
