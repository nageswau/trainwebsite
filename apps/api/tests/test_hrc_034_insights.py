"""hrc-034 (DEC-SCOPE-416): skill demand, portal analytics and data quality. Every figure ties out to its definition; the database is shared and
never truncated, so a test compares before and after, or finds its own rows."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import (
    Candidate,
    CandidateDuplicate,
    CandidateEducation,
    CandidateImportBatch,
    CandidateImportRow,
    CandidateResume,
    CandidateSkill,
    Job,
    JobSkill,
    Notification,
    NotificationDelivery,
    PortalEvent,
)
from app.notifications.delivery import MAX_ATTEMPTS
from app.notifications.events import notify
from app.services import candidate_profile, portal_events, recruitment_insights
from app.services.bdm_appointments import today_ist
from tests.rec001_helpers import login, make_user
from tests.test_rec_016_matching import _world

pytestmark = pytest.mark.asyncio
BASE = "/api/v1/recruiter/recruitment-insights"
JOBS = "/api/v1/candidate/jobs"
LEGACY_APPLY = "/api/v1/workflows/it/jobs/{}/apply"


def _today() -> date:
    return today_ist(datetime.now(UTC))


async def _hr(client, db):
    await login(client, await make_user(db, "hr_manager", "it"))


async def _get(client, path, **params) -> dict:
    response = await client.get(f"{BASE}/{path}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _skill_row(client, skill_id) -> dict | None:
    offset = 0
    while True:
        page = await _get(client, "skill-demand", limit=100, offset=offset)
        found = next((r for r in page["items"] if r["skill_id"] == str(skill_id)), None)
        if found or offset + 100 >= page["total"]:
            return found
        offset += 100


def _figures(body) -> dict:
    return {f["key"]: f for f in body["figures"]}


async def _events(db, user_id, job_id=None) -> list[tuple]:
    db.expire_all()
    rows = await db.execute(select(PortalEvent.kind, PortalEvent.job_id, PortalEvent.day).where(PortalEvent.user_id == user_id, *([PortalEvent.job_id == job_id] if job_id else [])))
    return sorted(rows.all(), key=lambda r: r[0])


# --- I1: who ----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("role", "division", "code"), [("hr_manager", "it", 200), ("placement_manager", "global", 200), ("partner", "global", 200), ("super_admin", "global", 200),
                                                        ("placement_team", "it", 403), ("placement_officer", "it", 403), ("hr_team", "it", 403), ("it_admin", "it", 403), ("it_student", "it", 403), ("candidate", "it", 403)])  # fmt: skip
@pytest.mark.parametrize("path", ["skill-demand", "skill-demand/vacancies", "portal-analytics", "data-quality", "data-quality/duplicates"])
async def test_only_a_grant_holder_reads(client, db_session, role, division, code, path):
    await login(client, await make_user(db_session, role, division))
    assert (await client.get(f"{BASE}/{path}", params={"n": 1} if path.endswith("vacancies") else {})).status_code == code


@pytest.mark.parametrize("path", ["skill-demand", "skill-demand/vacancies", "portal-analytics", "data-quality", "data-quality/duplicates"])
async def test_anonymous_is_refused(client, path):
    assert (await client.get(f"{BASE}/{path}")).status_code == 401


# --- I2: skill demand -------------------------------------------------------------------------------------------------------------------
async def test_demand_counts_open_jobs_and_supply_counts_the_active_pool(client, db_session):
    w = await _world(client, db_session)
    java, rust = await w.skill("Java"), await w.skill("Rust")
    await w.requirement(required=[(java, 1), (rust, 1)])
    await w.requirement(preferred=[(java, 1)])
    closed = await w.requirement(required=[(java, 1)])
    closed.status = "closed"
    await w.candidate(java)
    archived = await w.candidate(java)
    archived.archived_at = datetime.now(UTC)
    await db_session.commit()
    await _hr(client, db_session)
    row = await _skill_row(client, java.id)
    assert (row["required_jobs"], row["preferred_jobs"], row["open_jobs"], row["supply"], row["zero_supply"]) == (1, 1, 2, 1, False)
    assert row["name"] == f"Java {w.tag}"


async def test_a_skill_in_demand_with_zero_supply_is_flagged_and_counted(client, db_session):
    w = await _world(client, db_session)
    rust = await w.skill("Rust")
    await _hr(client, db_session)
    before = _figures(await _get(client, "skill-demand"))["zero_supply"]["value"]
    await w.requirement(required=[(rust, 1)])
    await _hr(client, db_session)
    row = await _skill_row(client, rust.id)
    assert row["supply"] == 0 and row["open_jobs"] == 1 and row["zero_supply"] is True
    assert _figures(await _get(client, "skill-demand"))["zero_supply"]["value"] == before + 1


async def test_a_held_skill_with_no_open_job_is_supply_only(client, db_session):
    w = await _world(client, db_session)
    go = await w.skill("Go")
    await w.candidate(go)
    await _hr(client, db_session)
    row = await _skill_row(client, go.id)
    assert (row["open_jobs"], row["supply"], row["zero_supply"]) == (0, 1, False)


async def test_free_text_job_skills_are_their_own_figure(client, db_session):
    w = await _world(client, db_session)
    job = await w.requirement()
    await _hr(client, db_session)
    before = _figures(await _get(client, "skill-demand"))["free_text"]["value"]
    db_session.add(JobSkill(job_id=job.id, skill_id=None, name=f"Basket weaving {w.tag}", kind="required", weight=1, position=9))
    await db_session.commit()
    assert _figures(await _get(client, "skill-demand"))["free_text"]["value"] == before + 1


async def test_sorting_and_paging_are_stable(client, db_session):
    await _hr(client, db_session)
    page = await _get(client, "skill-demand", sort="supply", limit=2)
    assert page["limit"] == 2 and len(page["items"]) <= 2
    supplies = [r["supply"] for r in page["items"]]
    assert supplies == sorted(supplies, reverse=True)
    assert (await client.get(f"{BASE}/skill-demand", params={"sort": "name; drop"})).status_code == 422


async def test_a_vacancy_under_n_matches_is_listed_with_the_matching_pages_count(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 1)])
    await w.candidate(java)
    await w.candidate(java)
    await _hr(client, db_session)

    async def row(n):
        body = await _get(client, "skill-demand/vacancies", n=n, limit=100)
        assert body["n"] == n and body["checked"] <= recruitment_insights.MAX_VACANCIES_CHECKED
        return next((r for r in body["items"] if r["id"] == str(job.id)), None), body

    found, _ = await row(3)
    if found is None:  # the newest 200 are checked, and this job is the newest
        pytest.fail("the new job should be checked")
    assert found["matches"] == 2 and found["reason"] is None and found["code"] == job.requirement_code and found["company"]
    assert (await row(2))[0] is None  # 2 matches is not fewer than 2
    assert (await client.get(f"{BASE}/skill-demand/vacancies", params={"n": 0})).status_code == 422


async def test_a_hard_filter_lowers_the_vacancy_count_and_a_job_with_no_skills_says_so(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    hard = await w.requirement(required=[(java, 1)], experience_min_months=24, match_hard_experience=True, work_mode="remote")
    bare = await w.requirement()
    await w.candidate(java)  # unknown experience fails the hard filter
    await _hr(client, db_session)
    items = {r["id"]: r for r in (await _get(client, "skill-demand/vacancies", n=1, limit=100))["items"]}
    assert items[str(hard.id)]["matches"] == 0 and items[str(hard.id)]["reason"] is None
    assert items[str(bare.id)]["matches"] == 0 and items[str(bare.id)]["reason"] == "no_skills"


# --- I3: events -------------------------------------------------------------------------------------------------------------------------
async def _seeker(client, db, role="it_student"):
    w = await _world(client, db)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 1)], work_mode="remote")
    user = await make_user(db, role, "it")
    candidate = await w.candidate(java, user_id=user.id, opted_in=True)
    await login(client, user)
    return w, user, candidate, job


async def test_the_jobs_page_writes_one_view_per_person_job_and_day(client, db_session):
    w, user, _c, job = await _seeker(client, db_session)
    job_id = job.id
    for _ in range(2):
        assert (await client.get(JOBS, params={"q": w.tag, "view": "all"})).status_code == 200
    assert await _events(db_session, user.id) == [("job_view", job_id, _today())]


async def test_only_the_cards_returned_count_as_viewed(client, db_session):
    w, user, _c, job = await _seeker(client, db_session)
    assert (await client.get(JOBS, params={"q": w.tag, "view": "all", "offset": 50})).status_code == 200
    assert await _events(db_session, user.id, job.id) == []


@pytest.mark.parametrize("role", ["it_student", "candidate"])
async def test_applying_writes_start_and_submit_once(client, db_session, role):
    _w, user, _c, job = await _seeker(client, db_session, role)
    assert (await client.post(f"{JOBS}/{job.id}/apply")).status_code == 201
    assert (await client.post(f"{JOBS}/{job.id}/apply")).status_code == 409
    assert [e[0] for e in await _events(db_session, user.id, job.id)] == ["apply_start", "apply_submit"]


async def test_a_refused_attempt_stays_as_a_start_only(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    job = await w.requirement(required=[(java, 1)], experience_min_months=24, match_hard_experience=True, work_mode="remote")
    user = await make_user(db_session, "it_student", "it")
    await w.candidate(java, user_id=user.id, opted_in=True)
    await login(client, user)
    assert (await client.post(f"{JOBS}/{job.id}/apply")).status_code == 422
    assert [e[0] for e in await _events(db_session, user.id, job.id)] == ["apply_start"]


async def test_a_job_the_caller_cannot_see_writes_nothing(client, db_session):
    _w, user, _c, job = await _seeker(client, db_session)
    job.status = "closed"
    await db_session.commit()
    assert (await client.post(f"{JOBS}/{job.id}/apply")).status_code == 404
    assert await _events(db_session, user.id, job.id) == []


async def test_the_legacy_student_route_writes_both(client, db_session):
    _w, user, _c, job = await _seeker(client, db_session)
    assert (await client.post(LEGACY_APPLY.format(job.id), json={})).status_code == 201
    assert [e[0] for e in await _events(db_session, user.id, job.id)] == ["apply_start", "apply_submit"]


async def test_an_event_holds_ids_only():
    assert set(PortalEvent.__table__.columns.keys()) == {"id", "kind", "user_id", "job_id", "day", "created_at"}


# --- I4: retention ----------------------------------------------------------------------------------------------------------------------
async def test_retention_deletes_only_past_the_limit(client, db_session):
    _w, user, _c, job = await _seeker(client, db_session)
    today = _today()
    old = today - timedelta(days=portal_events.RETENTION_DAYS + 1)
    edge = today - timedelta(days=portal_events.RETENTION_DAYS)
    db_session.add_all([PortalEvent(kind="job_view", user_id=user.id, job_id=job.id, day=old), PortalEvent(kind="job_view", user_id=user.id, job_id=job.id, day=edge)])
    await db_session.commit()
    assert await portal_events.run_retention() >= 1
    assert [e[2] for e in await _events(db_session, user.id, job.id)] == [edge]


async def test_retention_is_scheduled_daily():
    from app.worker import celery

    assert celery.conf.beat_schedule["hrc034-portal-events-retention"]["task"] == "app.worker.portal_events_retention_task"


# --- I3: portal analytics ---------------------------------------------------------------------------------------------------------------
async def test_the_funnel_ties_out_to_the_events(client, db_session):
    _w, user, _c, job = await _seeker(client, db_session)
    other = await make_user(db_session, "it_student", "it")
    today = _today()
    await _hr(client, db_session)
    before = {s["key"]: s for s in (await _get(client, "portal-analytics"))["funnel"]}
    db_session.add_all([PortalEvent(kind="job_view", user_id=user.id, job_id=job.id, day=today), PortalEvent(kind="job_view", user_id=other.id, job_id=job.id, day=today),
                        PortalEvent(kind="apply_start", user_id=user.id, job_id=job.id, day=today)])  # fmt: skip
    await db_session.commit()
    body = await _get(client, "portal-analytics")
    steps = {s["key"]: s for s in body["funnel"]}
    assert steps["job_view"]["people"] == before["job_view"]["people"] + 2 and steps["job_view"]["events"] == before["job_view"]["events"] + 2
    assert steps["apply_start"]["people"] == before["apply_start"]["people"] + 1
    assert steps["apply_start"]["dropped"] == max(steps["job_view"]["people"] - steps["apply_start"]["people"], 0)
    assert steps["job_view"]["dropped"] is None
    for key, step in steps.items():
        count = await db_session.scalar(select(func.count()).select_from(PortalEvent).where(PortalEvent.kind == key, PortalEvent.day >= date.fromisoformat(body["from"]), PortalEvent.day <= today))
        assert count == step["events"]


async def test_a_period_filters_events_and_registrations_and_can_be_empty(client, db_session):
    await _hr(client, db_session)
    long_ago = _today() - timedelta(days=330)
    body = await _get(client, "portal-analytics", **{"from": long_ago.isoformat(), "to": (long_ago + timedelta(days=1)).isoformat()})
    assert body["registrations"] == {"total": 0, "verified": 0}
    assert all(s["events"] == 0 and s["people"] == 0 for s in body["funnel"])


@pytest.mark.parametrize("params", [{"from": "2026-05-02", "to": "2026-05-01"}, {"to": "2999-01-01"}, {"from": "2020-01-01", "to": "2026-01-01"}, {"from": "nonsense"}])
async def test_a_bad_period_is_refused(client, db_session, params):
    await _hr(client, db_session)
    assert (await client.get(f"{BASE}/portal-analytics", params=params)).status_code == 422


async def test_a_new_portal_candidate_counts_as_registered_and_in_a_band(client, db_session):
    w = await _world(client, db_session)
    await _hr(client, db_session)
    before = await _get(client, "portal-analytics")
    user = await make_user(db_session, "candidate", "it")
    candidate = await w.candidate(user_id=user.id, opted_in=True)
    candidate.email_verified_at = datetime.now(UTC)
    await db_session.commit()
    after = await _get(client, "portal-analytics")
    assert after["registrations"]["total"] == before["registrations"]["total"] + 1 and after["registrations"]["verified"] == before["registrations"]["verified"] + 1
    assert sum(b["count"] for b in after["completion"]) == sum(b["count"] for b in before["completion"]) + 1
    assert [b["label"] for b in after["completion"]] == ["0-24%", "25-49%", "50-74%", "75-99%", "100%"]


async def test_the_completeness_expression_equals_the_profile_rule(client, db_session):
    """The dashboard's SQL and hrc-010's Python must agree, for an empty profile and a full one."""
    w = await _world(client, db_session)
    a, b, c = await w.skill("A"), await w.skill("B"), await w.skill("C")
    empty = await w.candidate()
    full = await w.candidate(a, b, c)
    full.email_verified_at = datetime.now(UTC)
    full.experience_months = 0
    full.preferred_roles = ["Developer"]
    full.preferred_locations = ["Pune"]
    full.expected_salary = 100
    db_session.add(CandidateEducation(candidate_id=full.id, position=1, degree="BTech"))
    db_session.add(CandidateResume(candidate_id=full.id, version=1, storage_key="k", content_type="application/pdf", size_bytes=1, uploaded_by_user_id=w.recruiter.id))
    await db_session.commit()
    for person in (empty, full):
        stored = await candidate_profile.rows(db_session, person.id)
        skills = await candidate_profile.skill_count(db_session, person.id)
        resumes = await db_session.scalar(select(func.count()).select_from(CandidateResume).where(CandidateResume.candidate_id == person.id))
        rule = candidate_profile.completeness(person, stored, skills, resumes)["percent"]
        assert await db_session.scalar(select(recruitment_insights.completeness_expr()).where(Candidate.id == person.id)) == rule
    assert await db_session.scalar(select(recruitment_insights.completeness_expr()).where(Candidate.id == full.id)) == 100


# --- I5: data quality -------------------------------------------------------------------------------------------------------------------
async def _ties(client, key, plus: int, before: int) -> dict:
    """The figure rose by `plus` and its drill-down's total equals it."""
    figure = _figures(await _get(client, "data-quality"))[key]
    assert figure["value"] == before + plus
    drill = await _get(client, f"data-quality/{key}", limit=5)
    assert drill["total"] == figure["value"] and drill["figure"]["key"] == key
    return drill


async def test_duplicates_tie_out_to_the_queue(client, db_session):
    w = await _world(client, db_session)
    first, second = await w.candidate(), await w.candidate()
    await _hr(client, db_session)
    before = _figures(await _get(client, "data-quality"))["duplicates"]["value"]
    db_session.add(CandidateDuplicate(candidate_id=first.id, other_id=second.id, signals=["email"]))
    await db_session.commit()
    drill = await _ties(client, "duplicates", 1, before)
    assert {"candidate", "other"} <= set(drill["items"][0])


async def test_failed_imports_count_error_rows_only(client, db_session):
    w = await _world(client, db_session)
    person = await w.candidate()
    await _hr(client, db_session)
    before = _figures(await _get(client, "data-quality"))["failed_imports"]["value"]
    source = person.source_id
    batch = CandidateImportBatch(uploaded_by_user_id=person.created_by_user_id, source_id=source, idempotency_key=w.tag, file_sha256="0" * 64, file_name=f"{w.tag}.csv", total_rows=2, created_count=1, error_count=1)
    db_session.add(batch)
    await db_session.flush()
    db_session.add_all([CandidateImportRow(batch_id=batch.id, row_number=2, status="created", candidate_id=person.id, reason=None),
                        CandidateImportRow(batch_id=batch.id, row_number=3, status="error", reason="Mobile is not valid")])  # fmt: skip
    await db_session.commit()
    drill = await _ties(client, "failed_imports", 1, before)
    newest = drill["items"][0]
    assert (newest["file_name"], newest["row_number"], newest["reason"]) == (f"{w.tag}.csv", 3, "Mobile is not valid")


async def test_failed_notifications_tie_out_without_the_recipient_or_error(client, db_session, monkeypatch):
    monkeypatch.setattr("app.notifications.dispatch._publish", lambda delivery_id, countdown: None)
    await _hr(client, db_session)
    before = _figures(await _get(client, "data-quality"))["failed_notifications"]["value"]
    person = await make_user(db_session, "placement_team", "it")
    import uuid

    note = (await notify(db_session, [person], "it.requirement.changed", uuid.uuid4()))[0]
    assert isinstance(note, Notification)
    db_session.add(NotificationDelivery(notification_id=note.id, channel="email", status="failed", attempt_count=MAX_ATTEMPTS, error="secret smtp text"))
    await db_session.commit()
    exceptions = await client.get("/api/v1/recruiter/notification-exceptions", params={"limit": 1})
    drill = await _ties(client, "failed_notifications", 1, before)
    assert drill["total"] == exceptions.json()["total"]
    assert all("recipient" not in row and "error" not in row for row in drill["items"])
    assert "secret smtp text" not in str(drill) and person.full_name not in str(drill)


async def test_incomplete_profiles_use_the_threshold_and_skip_inactive(client, db_session):
    w = await _world(client, db_session)
    await _hr(client, db_session)
    before = _figures(await _get(client, "data-quality"))["incomplete_profiles"]["value"]
    person = await w.candidate()
    gone = await w.candidate()
    gone.archived_at = datetime.now(UTC)
    await db_session.commit()
    drill = await _ties(client, "incomplete_profiles", 1, before)
    assert drill["figure"]["definition"].startswith(f"Active pool candidates under {recruitment_insights.INCOMPLETE_BELOW}%")
    assert all(row["percent"] < recruitment_insights.INCOMPLETE_BELOW for row in drill["items"])
    assert all(set(row) == {"candidate_code", "percent"} for row in drill["items"]) and person.name not in str(drill)


async def test_a_job_missing_fields_names_them(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    await _hr(client, db_session)
    before = _figures(await _get(client, "data-quality"))["jobs_missing_fields"]["value"]
    bare = await w.requirement(work_mode="remote")
    bare.description = " "
    await db_session.commit()
    complete = await w.requirement(required=[(java, 1)], work_mode="remote", qualification="BTech", experience_min_months=12, employment_type="full_time", vacancies=2)
    complete.description = "A complete requirement"
    await db_session.commit()
    assert isinstance(complete, Job)
    drill = await _ties(client, "jobs_missing_fields", 1, before)
    row = await _find_row(client, "jobs_missing_fields", bare.requirement_code)
    assert row["missing"] == ["required skill", "description", "qualification", "minimum experience", "employment type", "vacancies"]
    assert await _find_row(client, "jobs_missing_fields", complete.requirement_code) is None and drill["items"]


async def test_an_on_site_job_needs_a_location_and_a_remote_one_does_not(client, db_session):
    w = await _world(client, db_session)
    onsite = await w.requirement(work_mode="onsite")
    onsite.location = " "
    remote = await w.requirement(work_mode="remote")
    remote.location = " "
    await db_session.commit()
    await _hr(client, db_session)
    assert "on-site location" in (await _find_row(client, "jobs_missing_fields", onsite.requirement_code))["missing"]
    assert "on-site location" not in (await _find_row(client, "jobs_missing_fields", remote.requirement_code))["missing"]


async def _find_row(client, key, code) -> dict | None:
    offset = 0
    while True:
        page = await _get(client, f"data-quality/{key}", limit=100, offset=offset)
        found = next((r for r in page["items"] if r.get("code") == code), None)
        if found or offset + 100 >= page["total"]:
            return found
        offset += 100


async def test_an_unknown_figure_is_404_and_paging_is_bounded(client, db_session):
    await _hr(client, db_session)
    assert (await client.get(f"{BASE}/data-quality/nonsense")).status_code == 404
    assert (await client.get(f"{BASE}/data-quality/duplicates", params={"limit": 1000})).status_code == 422


async def test_a_link_appears_only_with_the_pages_grant(client, db_session):
    await _hr(client, db_session)
    figures = _figures(await _get(client, "data-quality"))
    assert figures["failed_notifications"]["href"] == "/recruiter/notification-exceptions"  # hr_manager holds notifications.retry
    assert figures["duplicates"]["href"] is None and figures["failed_imports"]["href"] is None
    await login(client, await make_user(db_session, "placement_manager", "global"))
    figures = _figures(await _get(client, "data-quality"))
    assert figures["duplicates"]["href"] == "/recruiter/candidates/duplicates" and figures["failed_imports"]["href"] == "/recruiter/candidates/import"
    await login(client, await make_user(db_session, "partner", "global"))
    assert all(f["href"] is None for f in (await _get(client, "data-quality"))["figures"])


async def test_reads_write_no_skill_row(client, db_session):
    """The reports only read: no candidate skill or event appears from reading them."""
    await _hr(client, db_session)
    before = (await db_session.scalar(select(func.count()).select_from(CandidateSkill)), await db_session.scalar(select(func.count()).select_from(PortalEvent)))
    for path in ("skill-demand", "skill-demand/vacancies", "portal-analytics", "data-quality"):
        await _get(client, path)
    db_session.expire_all()
    assert before == (await db_session.scalar(select(func.count()).select_from(CandidateSkill)), await db_session.scalar(select(func.count()).select_from(PortalEvent)))
