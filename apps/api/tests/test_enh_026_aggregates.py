"""ENH-026 -- counted-as-completed rule in every aggregate (spec §5.3, C5, C14, AC26-6)."""
import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school, mk_staff

from app.models import SchoolCareerRecord


@pytest_asyncio.fixture
async def world(db_session):
    ctx = await mk_school(db_session, label="E26-Agg", students=5)
    counselor = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    s = ctx["students"]
    rows = [
        (s[0], "counselling_note", None), (s[1], "counselling_note", "completed"), (s[2], "counselling_note", "follow_up_required"),
        (s[3], "counselling_note", "not_started"), (s[4], "counselling_note", "scheduled"),
        (s[0], "guidance_session", "scheduled"),
    ]
    for student, record_type, status in rows:
        db_session.add(SchoolCareerRecord(
            school_student_id=student.id, career_counselor_user_id=counselor.id, record_type=record_type, notes="n", status=status,
            recommended_careers=["Law"] if status == "completed" else None,
        ))
    await db_session.commit()
    ctx["counselor"] = counselor
    return ctx


@pytest.mark.asyncio
async def test_kpis_count_only_completed_follow_up_and_legacy(client, world):
    await login(client, world["coordinator"].email)
    data = (await client.get("/api/v1/school/dashboard")).json()
    kpis = {k["key"]: k for k in data["school_crm_kpis"]}
    assert kpis["individual_counselling_completed"]["value"] == 3  # s0 legacy, s1 completed, s2 follow-up
    assert kpis["career_guidance_completed"]["value"] == 0  # s0's guidance session is only scheduled
    assert data["career_guidance"]["students_covered"] == 5  # any record, unchanged


@pytest.mark.asyncio
async def test_entitlement_usage_counts_delivered_counselling_notes(client, world):
    await login(client, world["coordinator"].email)
    services = {s["key"]: s for s in (await client.get("/api/v1/school/entitlements")).json()["services"]}
    assert services["individual_counselling"]["used"] == 3


@pytest.mark.asyncio
async def test_overview_status_values(client, world):
    await login(client, world["coordinator"].email)
    s = world["students"]
    first = (await client.get(f"/api/v1/school/students/{s[0].id}/overview")).json()
    assert first["career_guidance"]["status"] == "in_progress"
    assert first["counselling"]["status"] == "completed"
    assert (await client.get(f"/api/v1/school/students/{s[3].id}/overview")).json()["counselling"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_overview_keeps_old_keys_and_adds_structured_recommendations(client, world):
    await login(client, world["coordinator"].email)
    body = (await client.get(f"/api/v1/school/students/{world['students'][1].id}/overview")).json()
    note = body["counselling"]["notes"][0]
    assert {"id", "record_type", "notes", "created_at"} <= set(note) and note["status"] == "completed"
    assert body["recommended_careers"] == []  # unchanged meaning: recommendation-type notes
    assert body["structured_recommendations"][0]["recommended_careers"] == ["Law"]


@pytest.mark.asyncio
async def test_portfolio_career_guidance_carries_status(client, world):
    await login(client, world["coordinator"].email)
    body = (await client.get(f"/api/v1/school/students/{world['students'][1].id}/portfolio")).json()
    assert body["career_guidance"][0]["status"] == "completed"
