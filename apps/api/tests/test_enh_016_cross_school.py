"""ENH-016 §34 cross-school dashboard and §27 school-wise utilization (AC09, AC10, AC16, Review Focus 5)."""

from datetime import timedelta

import pytest
from enh016_helpers import login, make_school, make_student

from app.api.school_analytics import utilization
from app.api.schools import _today_ist
from app.models import SchoolPsychometricRecord


def test_utilization_counts_delivered_pending_and_untracked():  # AC10
    usage = {"career_seminar": 2, "career_awareness_session": 0, "parent_orientation": 0, "psychometric_test": 5, "soft_skills": 0}
    assert utilization("bronze", usage) == {"services_included": 5, "delivered": 2, "pending": 3, "not_tracked": 0, "utilization_pct": 40.0}
    assert utilization(None, usage) == {"services_included": 0, "delivered": 0, "pending": 0, "not_tracked": 0, "utilization_pct": None}
    gold = utilization("gold", {"dedicated_counselor": True, "career_seminar": 1})
    assert gold["services_included"] == 13 and gold["delivered"] == 1 and gold["not_tracked"] == 12
    platinum = utilization("platinum", {"dedicated_counselor": True, "monthly_campus_visits": 0})
    assert platinum["delivered"] == 1 and platinum["pending"] == 1


async def _all_rows(client) -> list[dict]:
    rows, offset = [], 0
    while True:
        page = (await client.get("/api/v1/overseas-admin/analytics/schools", params={"limit": 100, "offset": offset})).json()
        rows += page["items"]
        offset += 100
        if offset >= page["total"]:
            return rows


@pytest.mark.asyncio
async def test_new_and_renewal_windows_at_their_edges(client, db_session):  # AC09
    today = _today_ist()
    tagged = {}
    for days in (90, 91):
        tagged[f"new{days}"] = (await make_school(db_session, partnership_date=today - timedelta(days=days)))["school"]
    for days in (-1, 60, 61):
        tagged[f"renew{days}"] = (await make_school(db_session, partnership_date=today - timedelta(days=400), tier_valid_until=today + timedelta(days=days)))["school"]
    ctx = await make_school(db_session, tier=None, partnership_date=today - timedelta(days=400))  # no tier -> not active
    await db_session.commit()
    await login(client, ctx["overseas_admin"])

    by_id = {r["school_id"]: r for r in await _all_rows(client)}

    assert by_id[str(tagged["new90"].id)]["is_new"] is True
    assert by_id[str(tagged["new91"].id)]["is_new"] is False
    assert by_id[str(tagged["renew60"].id)]["renewal_due"] is True
    assert by_id[str(tagged["renew61"].id)]["renewal_due"] is False
    assert by_id[str(tagged["renew-1"].id)]["renewal_due"] is True  # already expired counts
    # D6 (revised): active = a tier that is set and not past its end date
    assert by_id[str(tagged["renew60"].id)]["is_active"] is True
    assert by_id[str(tagged["renew-1"].id)]["is_active"] is False
    assert by_id[str(ctx["school"].id)]["is_active"] is False and by_id[str(ctx["school"].id)]["renewal_due"] is False
    summary = (await client.get("/api/v1/overseas-admin/analytics/summary")).json()
    assert summary["schools"]["total"] == len(by_id)
    assert summary["schools"]["active"] < summary["schools"]["total"]


@pytest.mark.asyncio
async def test_rows_count_students_participation_and_services(client, db_session):  # AC10
    ctx = await make_school(db_session, tier="bronze", name="ENH016 Rows School")
    s = await make_student(db_session, ctx, grade_level=8)
    await make_student(db_session, ctx, grade_level=9)
    db_session.add(SchoolPsychometricRecord(school_student_id=s.id, psychometric_team_user_id=ctx["psychometric_team"].id, assessment_type="A"))
    await db_session.commit()
    await login(client, ctx["super_admin"])

    row = {r["school_id"]: r for r in await _all_rows(client)}[str(ctx["school"].id)]

    assert row["name"] == "ENH016 Rows School" and row["tier"] == "bronze"
    assert row["students"] == 2 and row["student_participation"] == 1
    assert row["services_included"] == 5 and row["delivered"] == 1 and row["pending"] == 4 and row["utilization_pct"] == 20.0
    assert row["pending_activities"] == 0


@pytest.mark.asyncio
async def test_rows_offset_is_bounded(client, db_session):  # final review, Minor 5 (re-graded Important)
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx["overseas_admin"])
    assert (await client.get("/api/v1/overseas-admin/analytics/schools", params={"offset": 10**20})).status_code == 422


@pytest.mark.asyncio
async def test_summary_and_rows_hold_no_student_level_fields(client, db_session):  # AC16
    ctx = await make_school(db_session)
    s = await make_student(db_session, ctx, name="Secret Name", grade_level=8)
    db_session.add(SchoolPsychometricRecord(school_student_id=s.id, psychometric_team_user_id=ctx["psychometric_team"].id, assessment_type="A", status="completed"))
    await db_session.commit()
    await login(client, ctx["super_admin"])
    for path in ("/api/v1/overseas-admin/analytics/summary", "/api/v1/overseas-admin/analytics/schools"):
        response = await client.get(path)
        assert response.status_code == 200, response.text
        assert "Secret Name" not in response.text and "school_student_id" not in response.text and "full_name" not in response.text
    summary = (await client.get("/api/v1/overseas-admin/analytics/summary")).json()
    assert summary["outcomes"]["scholarships"] == {"value": None, "tracked": False, "note": "No school-student scholarship link exists yet (ENH-017)."}
    assert summary["outcomes"]["internships"]["tracked"] is True  # ENH-021, merged from main
    assert summary["students"]["psychometric"] >= 1 and summary["students"]["by_grade"]["8"] >= 1
    assert set(summary["outcomes"]) == {"applications", "offers", "visas", "admissions", "scholarships", "internships"}
