"""ENH-023 (DEC-SCOPE-030) -- tier changes and grandfathered work against a real database."""

import logging
from datetime import date, timedelta
from uuid import UUID

import pytest
from enh005_helpers import login, mk_school, mk_staff
from sqlalchemy import func, select

from app.api.schools import TIER_DENIED, TIER_SERVICES, TIER_UPDATE
from app.models import AuditLog

SCHOOLS = "/api/v1/overseas-admin/schools"
PLATINUM = [k for k, _ in TIER_SERVICES["platinum"]]
EXPIRED_ON = date.today() - timedelta(days=2)
NO_TIER = "This school has no active partnership tier."


async def world(db, tier, staff_role=None, students=1) -> dict:
    w = await mk_school(db, label="T23", tier=tier, students=students)
    if staff_role:
        w["staff"] = await mk_staff(db, w["school"], w["admin"], role=staff_role)
    return w


async def change_tier(client, w, **body) -> dict:
    """PATCH the tier as the school's Overseas Admin (the only sanctioned tier change)."""
    await login(client, w["admin"].email)
    r = await client.patch(f"{SCHOOLS}/{w['school'].id}", json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def tier_rows(db, school_id) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.action == TIER_UPDATE, AuditLog.entity_id == str(school_id)).order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())


async def denials(db, school_id) -> int:
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == TIER_DENIED, AuditLog.entity_id == str(school_id)))


# --- The transition record (AC-1..AC-4, AC-9) ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_downgrade_records_the_transition_and_returns_tier_change(client, db_session):
    w = await world(db_session, "platinum")
    body = await change_tier(client, w, tier="gold")
    assert body["tier"] == "gold"
    assert body["tier_change"]["direction"] == "downgrade"
    assert [s["key"] for s in body["tier_change"]["lost"]] == PLATINUM
    [row] = await tier_rows(db_session, w["school"].id)
    assert row.metadata_json == {
        "tier": "gold", "from_tier": "platinum", "to_tier": "gold", "direction": "downgrade",
        "gained": [], "lost": PLATINUM, "tier_valid_until": None, "previous_tier_valid_until": None,
    }


@pytest.mark.asyncio
async def test_upgrade_records_gained_services(client, db_session):
    w = await world(db_session, "gold")
    body = await change_tier(client, w, tier="platinum")
    assert body["tier_change"]["direction"] == "upgrade"
    [row] = await tier_rows(db_session, w["school"].id)
    assert (row.metadata_json["from_tier"], row.metadata_json["gained"], row.metadata_json["lost"]) == ("gold", PLATINUM, [])


@pytest.mark.asyncio
async def test_same_tier_and_valid_until_only_are_unchanged(client, db_session):
    w = await world(db_session, "gold")
    same = await change_tier(client, w, tier="gold")
    only_date = await change_tier(client, w, tier_valid_until="2027-03-31")
    assert same["tier_change"]["direction"] == only_date["tier_change"]["direction"] == "unchanged"
    rows = await tier_rows(db_session, w["school"].id)
    assert [r.metadata_json["direction"] for r in rows] == ["unchanged", "unchanged"]
    assert rows[1].metadata_json["tier_valid_until"] == "2027-03-31"
    assert rows[1].metadata_json["previous_tier_valid_until"] is None


@pytest.mark.asyncio
async def test_profile_only_patch_has_no_tier_change(client, db_session):
    w = await world(db_session, "gold")
    body = await change_tier(client, w, branch="North")
    assert body["tier_change"] is None
    assert body["branch"] == "North"
    assert await tier_rows(db_session, w["school"].id) == []


@pytest.mark.asyncio
async def test_down_then_up_keeps_both_transitions(client, db_session):
    w = await world(db_session, "platinum")
    await change_tier(client, w, tier="gold")
    await change_tier(client, w, tier="platinum")
    rows = await tier_rows(db_session, w["school"].id)
    assert [(r.metadata_json["from_tier"], r.metadata_json["to_tier"]) for r in rows] == [("platinum", "gold"), ("gold", "platinum")]


@pytest.mark.asyncio
async def test_invalid_tier_is_still_422_and_records_nothing(client, db_session):
    w = await world(db_session, "gold")
    await login(client, w["admin"].email)
    r = await client.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "diamond"})
    assert (r.status_code, r.json()["detail"]) == (422, "tier must be one of bronze, silver, gold, platinum")
    assert await tier_rows(db_session, w["school"].id) == []


# --- Precondition, empty string, typed contract (D12, D13, AC-15..AC-17) ----------------------------------------------


@pytest.mark.asyncio
async def test_stale_expected_tier_is_409_and_writes_nothing(client, db_session):
    w = await world(db_session, "platinum")
    await login(client, w["admin"].email)
    r = await client.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "gold", "expected_tier": "bronze"})
    assert r.status_code == 409
    assert r.json()["detail"] == "This school's tier changed to Platinum since you looked it up. Look it up again before changing the tier."
    await db_session.refresh(w["school"])
    assert w["school"].tier == "platinum"
    assert await tier_rows(db_session, w["school"].id) == []


@pytest.mark.asyncio
async def test_matching_expected_tier_saves_and_is_not_a_profile_field(client, db_session):
    w = await world(db_session, "platinum")
    body = await change_tier(client, w, tier="gold", expected_tier="platinum")
    assert body["tier_change"]["direction"] == "downgrade"
    profile_rows = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.profile_update", AuditLog.entity_id == str(w["school"].id)))
    assert profile_rows == 0


@pytest.mark.asyncio
async def test_expected_tier_empty_string_means_tierless(client, db_session):
    w = await world(db_session, None)
    body = await change_tier(client, w, tier="bronze", expected_tier="")
    assert body["tier_change"]["direction"] == "upgrade"
    await login(client, w["admin"].email)
    bad = await client.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "gold", "expected_tier": "diamond"})
    assert (bad.status_code, bad.json()["detail"]) == (422, "tier must be one of bronze, silver, gold, platinum")


@pytest.mark.asyncio
async def test_empty_string_tier_is_stored_as_a_removal(client, db_session):
    w = await world(db_session, "gold")
    body = await change_tier(client, w, tier="")
    assert body["tier"] is None
    assert body["tier_change"]["to_tier"] is None
    [row] = await tier_rows(db_session, w["school"].id)
    assert (row.metadata_json["to_tier"], row.metadata_json["tier"], row.metadata_json["direction"]) == (None, None, "downgrade")


@pytest.mark.asyncio
async def test_openapi_documents_the_typed_tier_change(client):
    spec = (await client.get("/openapi.json")).json()
    patch = spec["paths"]["/api/v1/overseas-admin/schools/{school_id}"]["patch"]
    assert patch["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/SchoolUpdateOut")
    direction = spec["components"]["schemas"]["TierChangeOut"]["properties"]["direction"]
    assert set(direction["enum"]) == {"upgrade", "downgrade", "unchanged"}


# --- Preview (AC-5) ----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_reports_a_downgrade_and_writes_nothing(client, db_session):
    w = await world(db_session, "platinum")
    await login(client, w["admin"].email)
    r = await client.get(f"{SCHOOLS}/{w['school'].id}/tier-change-preview", params={"tier": "gold"})
    assert r.status_code == 200
    assert r.json()["direction"] == "downgrade"
    assert [s["key"] for s in r.json()["lost"]] == PLATINUM
    assert await tier_rows(db_session, w["school"].id) == []
    await db_session.refresh(w["school"])
    assert w["school"].tier == "platinum"


@pytest.mark.asyncio
async def test_preview_empty_tier_means_removal(client, db_session):
    w = await world(db_session, "silver")
    await login(client, w["admin"].email)
    r = await client.get(f"{SCHOOLS}/{w['school'].id}/tier-change-preview", params={"tier": ""})
    assert (r.json()["direction"], r.json()["to_tier"]) == ("downgrade", None)
    assert len(r.json()["lost"]) == 7


@pytest.mark.asyncio
async def test_preview_errors(client, db_session):
    w = await world(db_session, "gold")
    await login(client, w["coordinator"].email)
    assert (await client.get(f"{SCHOOLS}/{w['school'].id}/tier-change-preview", params={"tier": "gold"})).status_code == 403
    await login(client, w["admin"].email)
    missing = await client.get(f"{SCHOOLS}/00000000-0000-0000-0000-000000000000/tier-change-preview", params={"tier": "gold"})
    assert missing.status_code == 404
    bad = await client.get(f"{SCHOOLS}/{w['school'].id}/tier-change-preview", params={"tier": "diamond"})
    assert (bad.status_code, bad.json()["detail"]) == (422, "tier must be one of bronze, silver, gold, platinum")


from app.api import schools  # noqa: E402
from app.models import Notification, NotificationDelivery  # noqa: E402


async def notices_for(db, user_id) -> list[Notification]:
    return list((await db.scalars(select(Notification).where(Notification.user_id == user_id))).all())


# --- Notifications (AC-1..AC-3, AC-11) ---------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upgrade_notifies_coordinator_principal_and_admin_only(client, db_session):
    w = await world(db_session, "gold")
    await change_tier(client, w, tier="platinum")
    [coord] = await notices_for(db_session, w["coordinator"].id)
    [principal] = await notices_for(db_session, w["principal"].id)
    [admin] = await notices_for(db_session, w["admin"].id)
    assert coord.title == principal.title == "Your partnership is now Platinum"
    assert "Visa support" in coord.body
    assert (coord.action_url, principal.action_url) == ("/school/coordinator/entitlements", "/school/principal/entitlements")
    assert admin.title.startswith("Tier change recorded: ") and admin.action_url is None
    assert await notices_for(db_session, w["teacher"].id) == [] and await notices_for(db_session, w["parent"].id) == []
    delivered = await db_session.scalar(select(func.count()).select_from(NotificationDelivery).where(NotificationDelivery.notification_id == coord.id, NotificationDelivery.channel == "email"))
    assert delivered == 1


@pytest.mark.asyncio
async def test_downgrade_notice_lists_lost_services(client, db_session):
    w = await world(db_session, "platinum")
    await change_tier(client, w, tier=None)
    [coord] = await notices_for(db_session, w["coordinator"].id)
    assert coord.title == "Your partnership changed from Platinum to no partnership tier"
    assert "Work already started for them can still be completed." in coord.body


@pytest.mark.asyncio
async def test_unchanged_tier_notifies_nobody(client, db_session):
    w = await world(db_session, "gold")
    await change_tier(client, w, tier="gold")
    await change_tier(client, w, tier_valid_until="2027-03-31")
    assert await notices_for(db_session, w["coordinator"].id) == []
    assert await notices_for(db_session, w["admin"].id) == []


@pytest.mark.asyncio
async def test_failing_email_never_fails_or_undoes_the_tier_change(client, db_session, monkeypatch, caplog):
    async def boom(**kwargs):
        raise RuntimeError(f"recipient refused: <{kwargs['to_email']}>")  # what real SMTP errors look like

    monkeypatch.setattr(schools, "send_parent_notification_email", boom)
    w = await world(db_session, "gold")
    with caplog.at_level(logging.WARNING, logger="app.admin"):
        body = await change_tier(client, w, tier="platinum")
    assert body["tier"] == "platinum"
    await db_session.refresh(w["school"])
    assert w["school"].tier == "platinum"
    assert len(await tier_rows(db_session, w["school"].id)) == 1
    # S1 / AC-18: ids and the error type only -- never the address the exception carried, never a traceback.
    failures = [r for r in caplog.records if r.getMessage() == "tier_change_notification_failed"]
    assert len(failures) == 3  # coordinator, principal, acting admin
    for record in failures:
        assert set(record.extra_fields) == {"school_id", "recipient_id", "error_type"}
        assert record.extra_fields["error_type"] == "RuntimeError"
        assert record.exc_info is None
        assert "@" not in str(record.extra_fields)


from datetime import UTC, datetime  # noqa: E402

from app.models import SchoolLanguageRecord, SchoolTestPrepRecord  # noqa: E402


def activity(activity_type=None) -> dict:
    body = {"title": "Session", "scheduled_at": datetime.now(UTC).isoformat()}
    return body | ({"activity_type": activity_type} if activity_type else {})


def attendance(w) -> dict:
    return {"records": [{"student_id": str(w["students"][0].id), "present": True}]}


async def grandfathered(db, school_id) -> int:
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.tier_grandfathered", AuditLog.entity_id == str(school_id)))


# --- Grandfathered work: activities and records (AC-6..AC-8) ----------------------------------------------------------


@pytest.mark.asyncio
async def test_campus_visit_scheduled_before_a_downgrade_can_still_take_attendance(client, db_session):
    w = await world(db_session, "platinum")
    await login(client, w["coordinator"].email)
    visit = (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).json()
    await change_tier(client, w, tier="gold")
    await login(client, w["coordinator"].email)
    r = await client.post(f"/api/v1/school/activities/{visit['id']}/attendance", json=attendance(w))
    assert r.status_code == 200, r.text
    assert await grandfathered(db_session, w["school"].id) == 1  # D14: committed with the attendance
    assert (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).status_code == 403  # new work
    assert await denials(db_session, w["school"].id) == 1


@pytest.mark.asyncio
async def test_a_grandfathered_write_that_then_fails_leaves_no_grandfather_row(client, db_session):
    w = await world(db_session, "platinum")
    await login(client, w["coordinator"].email)
    visit = (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).json()
    await change_tier(client, w, tier="gold")
    await login(client, w["coordinator"].email)
    r = await client.post(f"/api/v1/school/activities/{visit['id']}/attendance", json={"records": []})  # 422 after the tier check
    assert r.status_code == 422
    assert await grandfathered(db_session, w["school"].id) == 0


@pytest.mark.asyncio
async def test_free_text_activity_attendance_survives_removal(client, db_session):
    w = await world(db_session, "bronze")
    await login(client, w["coordinator"].email)
    free = (await client.post("/api/v1/school/activities", json=activity())).json()
    await change_tier(client, w, tier=None)
    await login(client, w["coordinator"].email)
    assert (await client.post(f"/api/v1/school/activities/{free['id']}/attendance", json=attendance(w))).status_code == 200
    r = await client.post("/api/v1/school/activities", json=activity())
    assert (r.status_code, r.json()["detail"]) == (403, NO_TIER)


@pytest.mark.asyncio
async def test_psychometric_record_survives_tier_removal(client, db_session):
    w = await world(db_session, "bronze", staff_role="psychometric_team")
    await login(client, w["staff"].email)
    body = {"school_student_id": str(w["students"][0].id), "assessment_type": "Aptitude"}
    record = (await client.post("/api/v1/school/psychometric-team/records", json=body)).json()
    await change_tier(client, w, tier=None)
    await login(client, w["staff"].email)
    patched = await client.patch(f"/api/v1/school/psychometric-team/records/{record['id']}", json={"report_url": "https://example.local/r.pdf"})
    assert patched.status_code == 200, patched.text
    assert (await client.post("/api/v1/school/psychometric-team/records", json=body)).status_code == 403


@pytest.mark.asyncio
async def test_test_prep_and_language_records_survive_downgrades(client, db_session):
    w = await world(db_session, "gold", staff_role="academic_team")
    await login(client, w["staff"].email)
    sid = str(w["students"][0].id)
    sat = (await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": sid, "test_type": "sat"})).json()
    german = (await client.post("/api/v1/school/academic-team/language-records", json={"school_student_id": sid, "language": "German"})).json()
    await change_tier(client, w, tier="bronze")
    await login(client, w["staff"].email)
    assert (await client.patch(f"/api/v1/school/academic-team/test-prep-records/{sat['id']}", json={"actual_score": "1400"})).status_code == 200
    assert (await client.patch(f"/api/v1/school/academic-team/language-records/{german['id']}", json={"certification_status": "certified"})).status_code == 200
    assert (await db_session.get(SchoolTestPrepRecord, UUID(sat["id"]), populate_existing=True)).actual_score == "1400"
    assert (await db_session.get(SchoolLanguageRecord, UUID(german["id"]), populate_existing=True)).certification_status == "certified"
    assert (await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": sid, "test_type": "sat"})).status_code == 403


@pytest.mark.asyncio
async def test_expired_school_is_refused_even_on_grandfathered_work(client, db_session):
    w = await world(db_session, "platinum")
    await login(client, w["coordinator"].email)
    visit = (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).json()
    await change_tier(client, w, tier="gold", tier_valid_until=EXPIRED_ON.isoformat())
    await login(client, w["coordinator"].email)
    r = await client.post(f"/api/v1/school/activities/{visit['id']}/attendance", json=attendance(w))
    assert r.status_code == 403
    assert r.json()["detail"].startswith("This school's partnership expired on")


@pytest.mark.asyncio
async def test_work_created_after_the_downgrade_is_not_grandfathered(client, db_session):
    w = await world(db_session, "platinum")
    await change_tier(client, w, tier="gold")
    await change_tier(client, w, tier="platinum")
    await login(client, w["coordinator"].email)
    visit = (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).json()
    w["school"].tier = "gold"  # a direct database change leaves no transition row
    await db_session.commit()
    r = await client.post(f"/api/v1/school/activities/{visit['id']}/attendance", json=attendance(w))
    assert r.status_code == 403
    assert "Monthly campus visits" in r.json()["detail"]


from enh011_helpers import ASSESSMENTS, BATCHES, ENROLMENTS, SESSIONS  # noqa: E402

from app.models import SchoolSkillBatch  # noqa: E402


@pytest.mark.asyncio
async def test_digital_skills_batch_can_be_finished_after_a_downgrade_but_not_grown(client, db_session):
    w = await world(db_session, "silver", staff_role="career_counselor")
    await login(client, w["staff"].email)
    today = date.today().isoformat()
    sid = str(w["students"][0].id)
    batch = (await client.post(BATCHES, json={"school_id": str(w["school"].id), "module_type": "digital_skills", "title": "T", "start_date": today})).json()
    enrolment = (await client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [sid]})).json()[0]
    await change_tier(client, w, tier="bronze")  # web_designing lost
    await login(client, w["staff"].email)

    assert (await client.patch(f"{BATCHES}/{batch['id']}", json={"title": "Renamed"})).status_code == 200
    session = await client.post(f"{BATCHES}/{batch['id']}/sessions", json={"session_date": today})
    assert session.status_code == 201, session.text
    marked = await client.put(f"{SESSIONS}/{session.json()['id']}/attendance", json={"records": [{"enrollment_id": enrolment["id"], "present": True}]})
    assert marked.status_code == 200, marked.text
    assessment = await client.post(f"{BATCHES}/{batch['id']}/assessments", json={"name": "Quiz", "max_score": 10})
    assert assessment.status_code == 201, assessment.text
    scored = await client.put(f"{ASSESSMENTS}/{assessment.json()['id']}/scores", json={"scores": [{"enrollment_id": enrolment["id"], "score": 7}]})
    assert scored.status_code == 200, scored.text
    assert (await client.patch(f"{ENROLMENTS}/{enrolment['id']}", json={"status": "completed"})).status_code == 200

    # Growing the commitment is new work: refused (D8).
    assert await grandfathered(db_session, w["school"].id) == 6  # batch edit, session, attendance, assessment, scores, status

    grown = await client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [sid]})
    assert grown.status_code == 403
    new_batch = await client.post(BATCHES, json={"school_id": str(w["school"].id), "module_type": "digital_skills", "title": "New", "start_date": today})
    assert new_batch.status_code == 403
    assert await denials(db_session, w["school"].id) == 2
    stored = await db_session.get(SchoolSkillBatch, UUID(batch["id"]), populate_existing=True)
    assert stored.title == "Renamed"


from test_sch_010_overseas_bridge import _make_university  # noqa: E402

from app.models import PortfolioEntry  # noqa: E402

PORTFOLIO = "/api/v1/school/students/{sid}/portfolio"


@pytest.mark.asyncio
async def test_portfolio_work_can_be_edited_after_a_downgrade_but_not_added(client, db_session):
    w = await world(db_session, "gold")
    url = PORTFOLIO.format(sid=w["students"][0].id)
    await login(client, w["coordinator"].email)
    entry = (await client.post(f"{url}/entries", json={"section": "project", "title": "Robot"})).json()
    assert (await client.patch(f"{url}/personal-statement", json={"personal_statement": "Hi"})).status_code == 200
    await change_tier(client, w, tier="silver")
    await login(client, w["coordinator"].email)
    assert (await client.patch(f"{url}/entries/{entry['id']}", json={"title": "Robot v2"})).status_code == 200
    assert (await client.patch(f"{url}/personal-statement", json={"personal_statement": "Hello"})).status_code == 200
    assert (await client.post(f"{url}/entries", json={"section": "project", "title": "New"})).status_code == 403
    assert (await client.delete(f"{url}/entries/{entry['id']}")).status_code == 204
    assert await db_session.get(PortfolioEntry, UUID(entry["id"]), populate_existing=True) is None


@pytest.mark.asyncio
async def test_personal_statement_never_started_is_new_work(client, db_session):
    w = await world(db_session, "gold")
    url = PORTFOLIO.format(sid=w["students"][0].id)
    await change_tier(client, w, tier="silver")
    await login(client, w["coordinator"].email)
    assert (await client.patch(f"{url}/personal-statement", json={"personal_statement": "Hi"})).status_code == 403


@pytest.mark.asyncio
async def test_unknown_portfolio_entry_is_404_before_the_tier_check(client, db_session):
    w = await world(db_session, "silver")
    url = PORTFOLIO.format(sid=w["students"][0].id)
    await login(client, w["coordinator"].email)
    r = await client.patch(f"{url}/entries/00000000-0000-0000-0000-000000000000", json={"title": "X"})
    assert r.status_code == 404
    assert await denials(db_session, w["school"].id) == 0


@pytest.mark.asyncio
async def test_visa_case_can_be_updated_after_a_downgrade_but_not_opened(client, db_session):
    w = await world(db_session, "platinum", students=2)
    university = await _make_university(db_session)
    await login(client, w["admin"].email)
    apps = [
        await client.post(f"/api/v1/overseas-admin/school-students/{s.id}/applications", json={"university_id": str(university.id), "intake": "Fall 2027"})
        for s in w["students"]
    ]
    assert [a.status_code for a in apps] == [201, 201]
    visa = await client.post("/api/v1/workflows/overseas/visa", json={"application_id": apps[0].json()["id"], "status": "checklist"})
    assert visa.status_code == 201, visa.text
    await change_tier(client, w, tier="gold")  # visa_support lost; application_support kept
    assert (await client.patch(f"/api/v1/workflows/overseas/visa/{visa.json()['id']}", json={"tracking_reference": "X1"})).status_code == 200
    second = await client.post("/api/v1/workflows/overseas/visa", json={"application_id": apps[1].json()["id"], "status": "checklist"})
    assert second.status_code == 403
    assert "Visa support" in second.json()["detail"]


# --- Concurrent tier changes queue on the school row lock (Task 2's with_for_update) -----------------------------------


import asyncio  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import School  # noqa: E402


@asynccontextmanager
async def _school_locked(school_id):
    session = SessionLocal()
    try:
        await session.execute(select(School).where(School.id == school_id).with_for_update())
        yield
    finally:
        await session.rollback()
        await session.close()


@pytest.mark.asyncio
async def test_concurrent_tier_changes_queue_and_record_true_transitions(db_session):
    w = await world(db_session, "platinum")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as admin:
        await login(admin, w["admin"].email)
        async with _school_locked(w["school"].id):
            first = asyncio.create_task(admin.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "gold"}))
            await asyncio.sleep(0.3)
            second = asyncio.create_task(admin.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "silver"}))
            await asyncio.sleep(0.7)
            assert not first.done() and not second.done(), "both tier changes must still be in flight while the school row is held"
        results = await asyncio.wait_for(asyncio.gather(first, second), timeout=20)
    assert [r.status_code for r in results] == [200, 200]
    rows = await tier_rows(db_session, w["school"].id)
    assert len(rows) == 2
    assert rows[0].metadata_json["from_tier"] == "platinum"
    # The assertion that proves update_school's own row lock (fails without .with_for_update(): the second change reads a stale tier).
    assert rows[1].metadata_json["from_tier"] == rows[0].metadata_json["to_tier"]


# --- Legacy "" tier rows (whole-branch review finding #1): stored before ENH-023, must not be a forever-409 -----------


@pytest.mark.asyncio
async def test_legacy_empty_string_tier_row_is_not_a_forever_409(client, db_session):
    w = await world(db_session, "gold")
    w["school"].tier = ""
    await db_session.commit()
    await login(client, w["admin"].email)
    r = await client.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "bronze", "expected_tier": None})
    assert r.status_code == 200, r.text
    assert r.json()["tier"] == "bronze"


@pytest.mark.asyncio
async def test_legacy_empty_string_tier_row_accepts_profile_edit_with_null_expected_tier(client, db_session):
    w = await world(db_session, "gold")
    w["school"].tier = ""
    await db_session.commit()
    await login(client, w["admin"].email)
    r = await client.patch(f"{SCHOOLS}/{w['school'].id}", json={"expected_tier": None, "branch": "X"})
    assert r.status_code == 200, r.text
