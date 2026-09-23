"""ENH-022 (DEC-SCOPE-027) -- per-route tier enforcement against a real database.

Every gated write: allowed at the service's minimum tier, a 403 with the exact message one tier below / with no tier / after
expiry, nothing written but one `school.tier_access_denied` audit row, and an out-of-scope caller still gets the pre-ENH-022
answer with no tier audit (no tier oracle)."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from enh005_helpers import login, mk_school, mk_staff
from enh011_helpers import ASSESSMENTS, BATCHES, ENROLMENTS, SESSIONS
from sqlalchemy import func, select
from test_sch_010_overseas_bridge import _make_university

from app.api.schools import TIER_DENIED
from app.models import AuditLog, PortfolioEntry, SchoolActivity, SchoolCareerRecord, SchoolLanguageRecord, SchoolPsychometricRecord, SchoolSkillBatch, SchoolTestPrepRecord

NO_TIER = "This school has no active partnership tier."
EXPIRED_ON = date.today() - timedelta(days=2)  # two days back: already past on the India date whatever the host timezone


async def denials(db, school_id) -> int:
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == TIER_DENIED, AuditLog.entity_id == str(school_id)))


async def world(db, tier, valid_until=None, staff_role=None) -> dict:
    w = await mk_school(db, label="T", tier=tier, tier_valid_until=valid_until)
    if staff_role:
        w["staff"] = await mk_staff(db, w["school"], w["admin"], role=staff_role)
    return w


def activity(activity_type=None) -> dict:
    body = {"title": "Session", "scheduled_at": datetime.now(UTC).isoformat()}
    return body | ({"activity_type": activity_type} if activity_type else {})


async def activity_count(db, school_id) -> int:
    return await db.scalar(select(func.count()).select_from(SchoolActivity).where(SchoolActivity.school_id == school_id))


# --- Activities (create + attendance) ---------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_campus_visit_needs_platinum(client, db_session):
    w = await world(db_session, "gold")
    await login(client, w["coordinator"].email)
    r = await client.post("/api/v1/school/activities", json=activity("campus_visit"))
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Gold partnership does not include Monthly campus visits (requires Platinum or higher)."
    assert await activity_count(db_session, w["school"].id) == 0
    assert await denials(db_session, w["school"].id) == 1

    p = await world(db_session, "platinum")
    await login(client, p["coordinator"].email)
    assert (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).status_code == 201
    assert await denials(db_session, p["school"].id) == 0


@pytest.mark.asyncio
async def test_bronze_activity_allowed_on_bronze(client, db_session):
    w = await world(db_session, "bronze")
    await login(client, w["coordinator"].email)
    assert (await client.post("/api/v1/school/activities", json=activity("career_seminar"))).status_code == 201


@pytest.mark.asyncio
async def test_free_text_activity_needs_any_valid_tier(client, db_session):
    ok = await world(db_session, "bronze")
    await login(client, ok["coordinator"].email)
    assert (await client.post("/api/v1/school/activities", json=activity())).status_code == 201
    none = await world(db_session, None)
    await login(client, none["coordinator"].email)
    r = await client.post("/api/v1/school/activities", json=activity())
    assert (r.status_code, r.json()["detail"]) == (403, NO_TIER)
    assert await activity_count(db_session, none["school"].id) == 0


@pytest.mark.asyncio
async def test_expired_partnership_blocks_activities(client, db_session):
    w = await world(db_session, "platinum", valid_until=EXPIRED_ON)
    await login(client, w["coordinator"].email)
    r = await client.post("/api/v1/school/activities", json=activity("career_seminar"))
    assert r.status_code == 403
    assert r.json()["detail"] == f"This school's partnership expired on {EXPIRED_ON.strftime('%d %b %Y')}."


@pytest.mark.asyncio
async def test_invalid_activity_type_is_still_422_before_the_tier_check(client, db_session):
    w = await world(db_session, None)
    await login(client, w["coordinator"].email)
    assert (await client.post("/api/v1/school/activities", json=activity("webinar"))).status_code == 422
    assert await denials(db_session, w["school"].id) == 0


@pytest.mark.asyncio
async def test_attendance_uses_the_stored_activity_type(client, db_session):
    w = await world(db_session, "platinum")
    await login(client, w["coordinator"].email)
    created = (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).json()
    w["school"].tier = "gold"  # downgraded after the visit was scheduled
    await db_session.commit()
    body = {"records": [{"student_id": str(w["students"][0].id), "present": True}]}
    r = await client.post(f"/api/v1/school/activities/{created['id']}/attendance", json=body)
    assert r.status_code == 403
    assert "Monthly campus visits" in r.json()["detail"]
    assert await denials(db_session, w["school"].id) == 1


@pytest.mark.asyncio
async def test_other_schools_activity_is_still_404_with_no_tier_audit(client, db_session):
    rich = await world(db_session, "platinum")
    await login(client, rich["coordinator"].email)
    created = (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).json()
    poor = await world(db_session, None)
    await login(client, poor["coordinator"].email)
    body = {"records": [{"student_id": str(poor["students"][0].id), "present": True}]}
    r = await client.post(f"/api/v1/school/activities/{created['id']}/attendance", json=body)
    assert r.status_code == 404
    assert await denials(db_session, poor["school"].id) == 0


# --- Career-counselor and psychometric records --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("record_type", ["guidance_session", "counselling_note", "recommendation"])
async def test_every_career_record_needs_silver(client, db_session, record_type):
    w = await world(db_session, "bronze", staff_role="career_counselor")
    await login(client, w["staff"].email)
    body = {"school_student_id": str(w["students"][0].id), "record_type": record_type, "notes": "n"}
    r = await client.post("/api/v1/school/career-counselor/records", json=body)
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Bronze partnership does not include Individual counselling (requires Silver or higher)."
    written = select(func.count()).select_from(SchoolCareerRecord).where(SchoolCareerRecord.school_student_id == w["students"][0].id)
    assert await db_session.scalar(written) == 0
    assert await denials(db_session, w["school"].id) == 1

    s = await world(db_session, "silver", staff_role="career_counselor")
    await login(client, s["staff"].email)
    body["school_student_id"] = str(s["students"][0].id)
    assert (await client.post("/api/v1/school/career-counselor/records", json=body)).status_code == 201


@pytest.mark.asyncio
async def test_psychometric_update_is_blocked_after_expiry_and_changes_nothing(client, db_session):
    w = await world(db_session, "bronze", staff_role="psychometric_team")
    await login(client, w["staff"].email)
    created = await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(w["students"][0].id), "assessment_type": "Aptitude"})
    assert created.status_code == 201
    w["school"].tier_valid_until = EXPIRED_ON
    await db_session.commit()
    r = await client.patch(f"/api/v1/school/psychometric-team/records/{created.json()['id']}", json={"report_url": "https://example.local/r.pdf"})
    assert r.status_code == 403
    assert r.json()["detail"].startswith("This school's partnership expired on")
    record = await db_session.get(SchoolPsychometricRecord, UUID(created.json()["id"]))
    await db_session.refresh(record)
    assert (record.report_url, record.status) == (None, "assigned")
    assert await denials(db_session, w["school"].id) == 1


@pytest.mark.asyncio
async def test_tierless_school_cannot_get_psychometric_records(client, db_session):
    w = await world(db_session, None, staff_role="psychometric_team")
    await login(client, w["staff"].email)
    r = await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(w["students"][0].id), "assessment_type": "Aptitude"})
    assert (r.status_code, r.json()["detail"]) == (403, NO_TIER)


@pytest.mark.asyncio
async def test_counselor_outside_portfolio_keeps_the_old_403_and_no_tier_audit(client, db_session):
    target = await world(db_session, None)
    outsider = await world(db_session, "platinum", staff_role="career_counselor")
    await login(client, outsider["staff"].email)
    body = {"school_student_id": str(target["students"][0].id), "record_type": "guidance_session", "notes": "n"}
    r = await client.post("/api/v1/school/career-counselor/records", json=body)
    assert (r.status_code, r.json()["detail"]) == (403, "This student is at a school outside your own portfolio")
    assert await denials(db_session, target["school"].id) == 0


# --- Test preparation and language classes -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ielts_needs_gold_and_patch_uses_the_stored_test_type(client, db_session):
    w = await world(db_session, "silver", staff_role="academic_team")
    await login(client, w["staff"].email)
    r = await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(w["students"][0].id), "test_type": "ielts"})
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Silver partnership does not include IELTS coaching (requires Gold or higher)."

    g = await world(db_session, "gold", staff_role="academic_team")
    await login(client, g["staff"].email)
    created = await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(g["students"][0].id), "test_type": "sat"})
    assert created.status_code == 201
    g["school"].tier = "silver"
    await db_session.commit()
    # A body `test_type` must not choose the service that is checked: the stored record's SAT is.
    patched = await client.patch(f"/api/v1/school/academic-team/test-prep-records/{created.json()['id']}", json={"actual_score": "1400", "test_type": "ielts"})
    assert patched.status_code == 403
    assert "SAT coaching" in patched.json()["detail"]
    record = await db_session.get(SchoolTestPrepRecord, UUID(created.json()["id"]))
    await db_session.refresh(record)
    assert record.actual_score is None


@pytest.mark.asyncio
async def test_invalid_test_type_is_still_422_before_the_tier_check(client, db_session):
    w = await world(db_session, None, staff_role="academic_team")
    await login(client, w["staff"].email)
    r = await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(w["students"][0].id), "test_type": "toefl"})
    assert r.status_code == 422
    assert await denials(db_session, w["school"].id) == 0


@pytest.mark.asyncio
async def test_language_classes_need_gold_on_create_and_update(client, db_session):
    w = await world(db_session, "gold", staff_role="academic_team")
    await login(client, w["staff"].email)
    created = await client.post("/api/v1/school/academic-team/language-records", json={"school_student_id": str(w["students"][0].id), "language": "German"})
    assert created.status_code == 201
    w["school"].tier = "bronze"
    await db_session.commit()
    r = await client.patch(f"/api/v1/school/academic-team/language-records/{created.json()['id']}", json={"certification_status": "certified"})
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Bronze partnership does not include Foreign language classes (requires Gold or higher)."
    record = await db_session.get(SchoolLanguageRecord, UUID(created.json()["id"]))
    await db_session.refresh(record)
    assert record.certification_status != "certified"
    again = await client.post("/api/v1/school/academic-team/language-records", json={"school_student_id": str(w["students"][0].id), "language": "French"})
    assert again.status_code == 403
    assert await denials(db_session, w["school"].id) == 2


# --- Skills tracker (ENH-011) ----------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_digital_skills_batch_needs_silver_soft_skills_bronze(client, db_session):
    w = await world(db_session, "bronze", staff_role="career_counselor")
    await login(client, w["staff"].email)
    base = {"school_id": str(w["school"].id), "title": "T", "start_date": "2026-10-01"}
    r = await client.post(BATCHES, json=base | {"module_type": "digital_skills"})
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Bronze partnership does not include Web designing (requires Silver or higher)."
    written = select(func.count()).select_from(SchoolSkillBatch).where(SchoolSkillBatch.school_id == w["school"].id)
    assert await db_session.scalar(written) == 0
    assert (await client.post(BATCHES, json=base | {"module_type": "soft_skills"})).status_code == 201


@pytest.mark.asyncio
async def test_every_skills_write_is_blocked_after_expiry(client, db_session):
    w = await world(db_session, "silver", staff_role="career_counselor")
    await login(client, w["staff"].email)
    today = date.today().isoformat()
    batch = (await client.post(BATCHES, json={"school_id": str(w["school"].id), "module_type": "digital_skills", "title": "T", "start_date": today})).json()
    enrolment = (await client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [str(w["students"][0].id)]})).json()[0]
    session = (await client.post(f"{BATCHES}/{batch['id']}/sessions", json={"session_date": today})).json()
    assessment = (await client.post(f"{BATCHES}/{batch['id']}/assessments", json={"name": "Quiz", "max_score": 10})).json()
    w["school"].tier_valid_until = EXPIRED_ON
    await db_session.commit()
    writes = [
        client.patch(f"{BATCHES}/{batch['id']}", json={"title": "New"}),
        client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [str(w["students"][0].id)]}),
        client.patch(f"{ENROLMENTS}/{enrolment['id']}", json={"status": "completed"}),
        client.post(f"{BATCHES}/{batch['id']}/sessions", json={"session_date": (date.today() + timedelta(days=1)).isoformat()}),
        client.put(f"{SESSIONS}/{session['id']}/attendance", json={"records": [{"enrollment_id": enrolment["id"], "present": True}]}),
        client.post(f"{BATCHES}/{batch['id']}/assessments", json={"name": "Quiz 2", "max_score": 10}),
        client.put(f"{ASSESSMENTS}/{assessment['id']}/scores", json={"scores": [{"enrollment_id": enrolment["id"], "score": 5}]}),
    ]
    for write in writes:
        r = await write
        assert r.status_code == 403, r.text
        assert r.json()["detail"].startswith("This school's partnership expired on")
    assert await denials(db_session, w["school"].id) == len(writes)
    stored = await db_session.get(SchoolSkillBatch, UUID(batch["id"]))
    await db_session.refresh(stored)
    assert stored.title == "T"


@pytest.mark.asyncio
async def test_batch_in_another_portfolio_is_still_404_with_no_tier_audit(client, db_session):
    w = await world(db_session, "platinum", staff_role="career_counselor")
    await login(client, w["staff"].email)
    batch = (await client.post(BATCHES, json={"school_id": str(w["school"].id), "module_type": "soft_skills", "title": "T", "start_date": "2026-10-01"})).json()
    other = await world(db_session, None, staff_role="career_counselor")
    await login(client, other["staff"].email)
    assert (await client.patch(f"{BATCHES}/{batch['id']}", json={"title": "X"})).status_code == 404
    assert await denials(db_session, other["school"].id) == 0


# --- Digital portfolio (ENH-012) -------------------------------------------------------------------------------------------

PORTFOLIO = "/api/v1/school/students/{sid}/portfolio"


@pytest.mark.asyncio
async def test_portfolio_writes_need_gold_and_reads_stay_open(client, db_session):
    w = await world(db_session, "silver")
    url = PORTFOLIO.format(sid=w["students"][0].id)
    await login(client, w["coordinator"].email)
    r = await client.post(f"{url}/entries", json={"section": "project", "title": "Robot"})
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Silver partnership does not include Digital portfolio creation (requires Gold or higher)."
    assert (await client.patch(f"{url}/personal-statement", json={"personal_statement": "Hi"})).status_code == 403
    assert (await client.get(url)).status_code == 200
    assert await denials(db_session, w["school"].id) == 2


@pytest.mark.asyncio
async def test_portfolio_update_and_delete_blocked_after_downgrade(client, db_session):
    w = await world(db_session, "gold")
    url = PORTFOLIO.format(sid=w["students"][0].id)
    await login(client, w["coordinator"].email)
    entry = (await client.post(f"{url}/entries", json={"section": "project", "title": "Robot"})).json()
    w["school"].tier = "silver"
    await db_session.commit()
    assert (await client.patch(f"{url}/entries/{entry['id']}", json={"title": "Changed"})).status_code == 403
    assert (await client.delete(f"{url}/entries/{entry['id']}")).status_code == 403
    row = await db_session.get(PortfolioEntry, UUID(entry["id"]))
    await db_session.refresh(row)
    assert row.title == "Robot"


# --- School -> Overseas bridge and bridged visa cases ------------------------------------------------------------------------


async def bridged_application(client, db_session, tier):
    w = await world(db_session, tier)
    university = await _make_university(db_session)
    await login(client, w["admin"].email)
    r = await client.post(f"/api/v1/overseas-admin/school-students/{w['students'][0].id}/applications", json={"university_id": str(university.id), "intake": "Fall 2027"})
    return w, r


@pytest.mark.asyncio
async def test_bridged_application_needs_gold(client, db_session):
    w, r = await bridged_application(client, db_session, "silver")
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Silver partnership does not include Application support (requires Gold or higher)."
    assert await denials(db_session, w["school"].id) == 1
    _, ok = await bridged_application(client, db_session, "gold")
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_visa_case_on_a_bridged_application_needs_platinum(client, db_session):
    _, gold_app = await bridged_application(client, db_session, "gold")
    r = await client.post("/api/v1/workflows/overseas/visa", json={"application_id": gold_app.json()["id"], "status": "checklist"})
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Gold partnership does not include Visa support (requires Platinum or higher)."

    p, platinum_app = await bridged_application(client, db_session, "platinum")
    visa = await client.post("/api/v1/workflows/overseas/visa", json={"application_id": platinum_app.json()["id"], "status": "checklist"})
    assert visa.status_code == 201, visa.text
    p["school"].tier_valid_until = EXPIRED_ON
    await db_session.commit()
    assert (await client.patch(f"/api/v1/workflows/overseas/visa/{visa.json()['id']}", json={"tracking_reference": "X1"})).status_code == 403
    assert await denials(db_session, p["school"].id) == 1


# --- /school/entitlements is only a report: unchanged (AC-8) ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_entitlements_report_is_unchanged_for_an_expired_school(client, db_session):
    w = await world(db_session, "gold", valid_until=EXPIRED_ON)
    await login(client, w["coordinator"].email)
    response = await client.get("/api/v1/school/entitlements")
    assert response.status_code == 200
    body = response.json()
    assert (body["tier"], body["tier_valid_until"]) == ("gold", EXPIRED_ON.isoformat())
    assert [s["key"] for s in body["services"]][-1] == "digital_portfolio_creation"
    assert all(s["included"] for s in body["services"])
    assert await denials(db_session, w["school"].id) == 0
