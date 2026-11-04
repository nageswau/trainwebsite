"""hrc-018 -- configurable matching engine with explanations (DEC-SCOPE-392 E1-E12; AC1-AC4). The rec-016 world builds every fixture
with unique skills, so only a test's own candidates can match its requirement."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.models import AuditLog, CandidateEducation, CandidateSkill, JobSkill, MatchSetting, UserPermissionOverride
from app.services import matching
from tests.rec001_helpers import login, make_user
from tests.test_rec_016_matching import _body, _matches, _row, _world

REQ = "/api/v1/recruiter/requirements"
SETTINGS = "/api/v1/recruiter/match-settings"
DEFAULTS = {"skills": 40, "experience": 20, "qualification": 15, "location": 10, "role": 10, "salary": 5}


# --- the pure rules (E2, E4) ---------------------------------------------------------------------------------------------------------
def test_allocate_shares_a_total_by_weight_in_whole_points():
    assert matching.allocate([40, 20, 15, 10, 10, 5]) == [40, 20, 15, 10, 10, 5]
    assert matching.allocate([1, 1, 1]) == [34, 33, 33]
    assert matching.allocate([2, 0, 2], 40) == [20, 0, 20]
    assert matching.allocate([0, 0]) == [0, 0]
    assert sum(matching.allocate([3, 7, 11], 37)) == 37


def test_factor_points_spread_100_over_the_factors_that_apply():
    points = matching.factor_points(DEFAULTS, {"skills", "role"})
    assert points == {"skills": 80, "role": 20}
    assert sum(matching.factor_points(DEFAULTS, set(DEFAULTS)).values()) == 100
    assert matching.factor_points({**DEFAULTS, "role": 0}, {"role"}) == {"role": 0}


def test_years_and_rupees_read_plainly():
    assert matching.years(36) == "3 yrs" and matching.years(12) == "1 yr" and matching.years(18) == "1.5 yrs"
    assert matching.rupees(Decimal("800000")) == "₹8L" and matching.rupees(Decimal("850000")) == "₹8.5L"
    assert matching.rupees(Decimal("50000")) == "₹50,000"


# --- the admin weights (E2, E3; AC1) -------------------------------------------------------------------------------------------------
async def _reset_settings(db):
    await db.execute(delete(MatchSetting))
    await db.commit()


@pytest.mark.asyncio
async def test_settings_default_to_the_spec_weights_and_only_super_admin_saves(client, db_session):
    await _reset_settings(db_session)
    w = await _world(client, db_session)
    read = await client.get(SETTINGS)
    assert read.status_code == 200 and read.json() == {"weights": DEFAULTS, "defaults": DEFAULTS, "can_edit": False}
    refused = await client.put(SETTINGS, json={"weights": DEFAULTS})
    assert refused.status_code == 403
    await login(client, w.manager)
    assert (await client.put(SETTINGS, json={"weights": DEFAULTS})).status_code == 403
    admin = await make_user(db_session, "super_admin", "it")
    await login(client, admin)
    wanted = {**DEFAULTS, "skills": 50, "salary": 0, "role": 5}
    saved = await client.put(SETTINGS, json={"weights": wanted})
    assert saved.status_code == 200, saved.text
    assert saved.json() == {"weights": wanted, "defaults": DEFAULTS, "can_edit": True}
    assert (await client.get(SETTINGS)).json()["weights"] == wanted
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_matching.weights").order_by(AuditLog.created_at.desc()))
    assert row.metadata_json["changes"] == {"skills": [40, 50], "role": [10, 5], "salary": [5, 0]}
    await _reset_settings(db_session)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "weights",
    [
        {**DEFAULTS, "skills": 41},  # 101 (AC1)
        {**DEFAULTS, "skills": 39},  # 99
        {**DEFAULTS, "skills": -1, "role": 51},
        {k: v for k, v in DEFAULTS.items() if k != "role"},
        {**DEFAULTS, "luck": 0},
        {**DEFAULTS, "skills": 40.5},
    ],
)
async def test_settings_must_be_six_whole_weights_that_sum_to_100(client, db_session, weights):
    admin = await make_user(db_session, "super_admin", "it")
    await login(client, admin)
    response = await client.put(SETTINGS, json={"weights": weights})
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_settings_roles(client, db_session):
    for role, status in (("hr_team", 200), ("bdm", 403), ("it_student", 403)):
        await login(client, await make_user(db_session, role, "it"))
        assert (await client.get(SETTINGS)).status_code == status, role


# --- the six factors and the explanation (E1, E4, E5, E7; AC3, AC4) ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_full_match_scores_100_on_six_factors_with_a_sentence_each(client, db_session):
    await _reset_settings(db_session)
    w = await _world(client, db_session)
    java, sql, aws = await w.skill("Java"), await w.skill("SQL"), await w.skill("AWS")
    job = await w.requirement(
        required=[(java, 2), (sql, 2)], preferred=[(aws, 1)], experience_min_months=24, experience_max_months=60, location="Pune",
        qualification="B.Tech or MCA", salary_max=Decimal("1000000"), expected_joining_date=date.today() + timedelta(days=60),
    )
    best = await w.candidate(java, sql, aws, experience_months=50, relevant_experience_months=36, location="Pune", qualification="MCA",
                             preferred_role="Java Developer", expected_salary=Decimal("800000"), expected_annual_inr=Decimal("800000"),
                             notice_days=30)
    body = _body(await _matches(client, job))
    assert body["disclaimer"] == matching.DISCLAIMER and "not a guarantee" in body["disclaimer"]
    assert [(f["key"], f["points"]) for f in body["criteria"]["factors"]] == list(DEFAULTS.items())
    row = _row(body, best)
    assert row["score"] == 100 == sum(b["points"] for b in row["breakdown"])
    text = {e["key"]: e["text"] for e in row["explanation"]}
    assert text["skills"] == "Matches 2 of 2 required skills · 1 of 1 preferred"
    assert text["experience"] == "3 yrs relevant (needs 2–5 yrs)"
    assert text["qualification"] == "MCA matches the qualification"
    assert text["location"] == "In or prefers Pune"
    assert text["role"] == "Wants a Java Developer role"
    assert text["salary"].startswith("Expected ₹8L within budget (up to ₹10L) · Available by ")
    assert row["skills"] == {"required_matched": [java.name, sql.name], "required_missing": [], "preferred_matched": [aws.name], "preferred_missing": []}


@pytest.mark.asyncio
async def test_partial_matches_explain_what_is_missing(client, db_session):
    await _reset_settings(db_session)
    w = await _world(client, db_session)
    java, aws, gcp = await w.skill("Java"), await w.skill("AWS"), await w.skill("GCP")
    job = await w.requirement(required=[(java, 2)], preferred=[(aws, 1), (gcp, 1)], experience_min_months=24, location="Pune",
                              qualification="B.Tech", salary_max=Decimal("600000"))
    weak = await w.candidate(java, gcp, experience_months=6, location="Delhi", qualification="BCom", preferred_role="Accountant",
                             expected_annual_inr=Decimal("900000"), expected_salary=Decimal("900000"))
    unknown = await w.candidate(java)
    body = _body(await _matches(client, job))
    text = {e["key"]: e for e in _row(body, weak)["explanation"]}
    assert text["skills"]["text"] == f"Matches 1 of 1 required skills · 1 of 2 preferred (missing {aws.name})"
    assert text["experience"]["text"] == "6 mos experience (needs 2+ yrs)" and text["experience"]["matched"] is False
    assert text["qualification"]["text"] == "Qualification does not match"
    assert text["location"]["text"] == "Not in or preferring Pune"
    assert text["role"]["text"] == "Preferred role differs from the job title"
    assert text["salary"]["text"] == "Expected ₹9L above budget (up to ₹6L)"
    assert _row(body, weak)["skills"]["preferred_missing"] == [aws.name]
    text = {e["key"]: e["text"] for e in _row(body, unknown)["explanation"]}
    assert text["experience"] == "Experience not recorded (needs 2+ yrs)"
    assert text["qualification"] == "Qualification not recorded"
    assert text["role"] == "Preferred role not recorded"
    assert text["salary"] == "Expected salary not recorded"


@pytest.mark.asyncio
async def test_a_factor_without_job_data_does_not_apply_and_the_rest_share_100(client, db_session):
    await _reset_settings(db_session)
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)], work_mode="remote")  # skills + role apply
    match = await w.candidate(java, preferred_roles=["java developer"])
    body = _body(await _matches(client, job))
    assert {f["key"]: (f["applies"], f["points"]) for f in body["criteria"]["factors"]} == {
        "skills": (True, 80), "experience": (False, 0), "qualification": (False, 0), "location": (False, 0), "role": (True, 20), "salary": (False, 0),
    }
    assert _row(body, match)["score"] == 100 and [e["key"] for e in _row(body, match)["explanation"]] == ["skills", "role"]


@pytest.mark.asyncio
async def test_admin_weights_change_the_score(client, db_session):
    await _reset_settings(db_session)
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)], work_mode="remote")
    no_role = await w.candidate(java)
    assert _row(_body(await _matches(client, job)), no_role)["score"] == 80
    db_session.add(MatchSetting(id=1, **{f"{k}_weight": v for k, v in {**DEFAULTS, "skills": 30, "role": 20}.items()}))
    await db_session.commit()
    assert _row(_body(await _matches(client, job)), no_role)["score"] == 60
    await _reset_settings(db_session)


@pytest.mark.asyncio
async def test_changing_a_candidate_skill_changes_the_score_on_the_next_read(client, db_session):
    """AC4 (§13 "candidate profile changed -> refresh"): scores are live."""
    await _reset_settings(db_session)
    w = await _world(client, db_session)
    java, aws = await w.skill("Java"), await w.skill("AWS")
    job = await w.requirement(required=[(java, 2)], preferred=[(aws, 2)], work_mode="remote")
    candidate = await w.candidate(java)
    before = _row(_body(await _matches(client, job)), candidate)["score"]
    db_session.add(CandidateSkill(candidate_id=candidate.id, skill_id=aws.id, level="beginner", added_by_user_id=w.recruiter.id))
    await db_session.commit()
    assert _row(_body(await _matches(client, job)), candidate)["score"] > before


# --- hard filters (E6; AC2) ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_candidate_missing_a_required_skill_is_excluded(client, db_session):
    w = await _world(client, db_session)
    java, sql = await w.skill("Java"), await w.skill("SQL")
    job = await w.requirement(required=[(java, 2), (sql, 2)])
    keep = await w.candidate(java, sql)
    await w.candidate(java)
    assert [i["id"] for i in _body(await _matches(client, job))["items"]] == [str(keep.id)]


@pytest.mark.asyncio
async def test_each_optional_hard_filter_excludes_misses_and_unknowns(client, db_session):
    await _reset_settings(db_session)
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)], experience_min_months=24, location="Pune", qualification="B.Tech, M.Tech",
                              salary_max=Decimal("50000"), salary_period="month")  # ₹6L a year
    fits = await w.candidate(java, experience_months=30, location="Pune", qualification="M.Tech", expected_annual_inr=Decimal("600000"))
    young = await w.candidate(java, experience_months=12, location="Pune", qualification="M.Tech", expected_annual_inr=Decimal("600000"))
    away = await w.candidate(java, experience_months=30, location="Delhi", qualification="M.Tech", expected_annual_inr=Decimal("600000"))
    degree = await w.candidate(java, experience_months=30, location="Pune", qualification="BSc", expected_annual_inr=Decimal("600000"))
    dear = await w.candidate(java, experience_months=30, location="Pune", qualification="M.Tech", expected_annual_inr=Decimal("700000"))
    blank = await w.candidate(java)
    second_degree = await w.candidate(java, experience_months=30, location="Pune", qualification="BSc", expected_annual_inr=Decimal("1"))
    db_session.add(CandidateEducation(candidate_id=second_degree.id, position=2, degree=" b.tech "))
    await db_session.commit()
    everyone = {fits, young, away, degree, dear, blank, second_degree}
    assert {i["id"] for i in _body(await _matches(client, job))["items"]} == {str(c.id) for c in everyone}
    weights = await _weights(db_session, job)
    for key, gone in (("experience", {young, blank}), ("location", {away, blank}), ("qualification", {degree, blank}), ("salary", {dear, blank})):
        saved = await client.put(f"{REQ}/{job.id}/skill-weights", json={"weights": weights, "hard_filters": {key: True}})
        assert saved.status_code == 200, saved.text
        body = _body(await _matches(client, job))
        assert {i["id"] for i in body["items"]} == {str(c.id) for c in everyone - gone}, key
        assert body["criteria"]["hard_filters"][key] == {"on": True, "available": True}
        off = await client.put(f"{REQ}/{job.id}/skill-weights", json={"weights": weights, "hard_filters": {key: False}})
        assert off.status_code == 200, off.text


async def _weights(db, job) -> list[dict]:
    rows = (await db.scalars(select(JobSkill).where(JobSkill.job_id == job.id))).all()
    return [{"id": str(r.id), "weight": r.weight} for r in rows]


@pytest.mark.asyncio
async def test_hard_filters_are_validated_audited_and_need_the_job_value(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)], work_mode="remote")
    weights = await _weights(db_session, job)
    for key, message in (("experience", "minimum experience"), ("qualification", "qualification"), ("location", "location"), ("salary", "maximum salary")):
        refused = await client.put(f"{REQ}/{job.id}/skill-weights", json={"weights": weights, "hard_filters": {key: True}})
        assert refused.status_code == 422 and message in refused.json()["detail"], refused.text
    assert (await client.put(f"{REQ}/{job.id}/skill-weights", json={"weights": weights, "hard_filters": {"luck": True}})).status_code == 422
    job.experience_min_months = 12
    await db_session.commit()
    saved = await client.put(f"{REQ}/{job.id}/skill-weights", json={"weights": weights, "hard_filters": {"experience": True}})
    assert saved.status_code == 200, saved.text
    await db_session.refresh(job)
    assert job.match_hard_experience is True
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(job.id), AuditLog.action == "recruiter_requirement.weights"))
    assert row.metadata_json["changes"] == {"Hard filter: experience": [False, True]}
    await login(client, w.manager)  # a manager reads matches but does not edit the requirement (rec-016 M7)
    assert (await client.put(f"{REQ}/{job.id}/skill-weights", json={"weights": weights, "hard_filters": {"experience": False}})).status_code == 403


# --- salary visibility (E8, E9) ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_without_the_compensation_grant_the_salary_text_has_no_amounts(client, db_session):
    await _reset_settings(db_session)
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 2)], work_mode="remote", salary_max=Decimal("1000000"))
    candidate = await w.candidate(java, expected_annual_inr=Decimal("800000"))
    db_session.add(UserPermissionOverride(user_id=w.recruiter.id, resource="candidates.compensation", action="view", effect="deny",
                                          created_by_id=w.manager.id, reason="hrc-018 test"))
    await db_session.commit()
    text = {e["key"]: e["text"] for e in _row(_body(await _matches(client, job)), candidate)["explanation"]}
    assert text["salary"] == "Salary details are restricted" and "₹" not in str(_body(await _matches(client, job)))


# --- the same engine both ways (E10, E12) --------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_candidate_to_jobs_gives_the_same_score_and_hides_salary_from_the_candidate(client, db_session):
    await _reset_settings(db_session)
    w = await _world(client, db_session)
    java, sql = await w.skill("Java"), await w.skill("SQL")
    fit = await w.requirement(required=[(java, 2)], location="Pune", salary_max=Decimal("1000000"))
    other = await w.requirement(required=[(sql, 2)])
    candidate = await w.candidate(java, location="Pune", expected_annual_inr=Decimal("800000"))
    staff = _row(_body(await _matches(client, fit)), candidate)
    found = await matching.jobs_for_candidate(db_session, candidate, [fit, other])
    assert [m["job_id"] for m in found] == [fit.id]  # `other` fails its required-skill hard filter
    assert found[0]["score"] == staff["score"]
    assert [e["key"] for e in found[0]["explanation"]] == [e["key"] for e in staff["explanation"] if e["key"] != "salary"]
    assert "₹" not in str(found) and "breakdown" not in found[0]  # E9: not even the salary item's matched flag
    staff_view = await matching.jobs_for_candidate(db_session, candidate, [fit], audience="staff")
    assert any(e["key"] == "salary" for e in staff_view[0]["explanation"])
    assert uuid.UUID(str(found[0]["job_id"]))


# --- with hrc-009 (DEC-SCOPE-390 R1): a hard filter decides who fits, so switching one flags the open applications ------------------
@pytest.mark.asyncio
async def test_turning_a_hard_filter_on_flags_open_applications_for_review(client, db_session):
    from tests.test_hrc_009_review import _flags
    from tests.test_hrc_009_review import _world as review_world

    w = await review_world(client, db_session, master=True)
    rows = (await db_session.scalars(select(JobSkill).where(JobSkill.job_id == uuid.UUID(w["job"])))).all()
    weights = [{"id": str(r.id), "weight": r.weight} for r in rows]
    url = f"{REQ}/{w['job']}/skill-weights"
    assert (await client.put(url, json={"weights": weights})).status_code == 200  # nothing changed: nothing flagged
    assert (await _flags(db_session, w))["a"] == (False, "sourced")
    saved = await client.put(url, json={"weights": weights, "hard_filters": {"location": True}})
    assert saved.status_code == 200, saved.text
    assert await _flags(db_session, w) == {"a": (True, "sourced"), "b": (True, "shortlisted"), "c": (False, "rejected")}
