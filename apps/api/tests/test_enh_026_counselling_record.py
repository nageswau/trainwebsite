"""ENH-026 -- counselling record API (spec §5.1, AC26-1..AC26-9, AC-R1..AC-R4)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school, mk_staff

RECORDS = "/api/v1/school/career-counselor/records"
IST = ZoneInfo("Asia/Kolkata")
TODAY = datetime.now(IST).date()
LEGACY_KEYS = {"id", "school_student_id", "record_type", "notes", "created_at"}


@pytest_asyncio.fixture
async def world(db_session):
    ctx = await mk_school(db_session, label="E26", students=2)
    ctx["counselor"] = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    ctx["sid"] = str(ctx["students"][0].id)
    return ctx


async def _create(client, world, **body):
    return await client.post(RECORDS, json={"school_student_id": world["sid"], "record_type": "counselling_note", "notes": "Met.", **body})


@pytest.mark.asyncio
async def test_legacy_three_field_post_behaves_as_before(client, world):
    await login(client, world["counselor"].email)
    r = await _create(client, world)
    assert r.status_code == 201
    body = r.json()
    assert LEGACY_KEYS <= set(body)
    assert body["status"] == "completed" and body["completed_on"] == TODAY.isoformat()  # C3


@pytest.mark.asyncio
async def test_create_with_every_section_7_field(client, world):
    await login(client, world["counselor"].email)
    fields = {
        "status": "scheduled", "scheduled_for": "2026-12-01T10:00:00+05:30", "notes": "",
        "career_interests": ["Design"], "global_education_interest": True, "academic_strengths": ["Maths"],
        "weak_areas": ["Essays"], "recommended_careers": ["Architect"], "recommended_courses": ["B.Arch"],
        "recommended_stream": ["Science"], "recommended_skills": ["Sketching"], "parent_participated": True,
        "parent_participation_note": "Mother attended online",
    }
    r = await _create(client, world, **fields)
    assert r.status_code == 201, r.text
    listed = (await client.get(RECORDS)).json()[0]
    for key, value in fields.items():
        if key == "scheduled_for":
            assert datetime.fromisoformat(listed[key]) == datetime.fromisoformat(value)
        else:
            assert listed[key] == value, key
    assert listed["counselor_name"] == world["counselor"].full_name


@pytest.mark.parametrize("status", ["not_started", "scheduled", "completed"])
@pytest.mark.asyncio
async def test_create_accepts_only_the_initial_statuses(client, world, status):
    await login(client, world["counselor"].email)
    extra = {"scheduled_for": "2026-12-01T10:00:00+05:30"} if status == "scheduled" else {}
    assert (await _create(client, world, status=status, **extra)).status_code == 201


@pytest.mark.asyncio
async def test_create_cannot_start_at_follow_up(client, world):
    await login(client, world["counselor"].email)
    r = await _create(client, world, status="follow_up_required", next_follow_up_date=(TODAY + timedelta(days=3)).isoformat())
    assert r.status_code == 422
    assert r.json()["detail"] == "status must be one of not_started, scheduled, completed when creating a record"


@pytest.mark.asyncio
async def test_scheduled_needs_a_date_and_completed_needs_notes(client, world):
    await login(client, world["counselor"].email)
    r = await _create(client, world, status="scheduled", notes="")
    assert (r.status_code, r.json()["detail"]) == (422, "scheduled_for is required when status is Scheduled")
    r = await _create(client, world, status="completed", notes="  ")
    assert (r.status_code, r.json()["detail"]) == (422, "notes is required")


@pytest.mark.asyncio
async def test_recommendation_stays_notes_only(client, world):
    await login(client, world["counselor"].email)
    ok = await client.post(RECORDS, json={"school_student_id": world["sid"], "record_type": "recommendation", "notes": "Cyber security"})
    assert ok.status_code == 201 and ok.json()["status"] is None
    bad = await client.post(RECORDS, json={"school_student_id": world["sid"], "record_type": "recommendation", "notes": "x", "status": "completed"})
    assert (bad.status_code, bad.json()["detail"]) == (422, "recommendation records take notes only")


@pytest.mark.asyncio
async def test_existing_error_messages_are_unchanged(client, world):
    await login(client, world["counselor"].email)
    assert (await client.post(RECORDS, json={"record_type": "counselling_note", "notes": "x"})).json()["detail"] == "school_student_id is required"
    bad_type = await client.post(RECORDS, json={"school_student_id": world["sid"], "record_type": "nope", "notes": "x"})
    assert bad_type.json()["detail"] == "record_type must be one of guidance_session, counselling_note, recommendation"
    assert (await _create(client, world, notes="")).json()["detail"] == "notes is required"


@pytest.mark.asyncio
async def test_owner_fields_cannot_be_set_on_create(client, world):
    await login(client, world["counselor"].email)
    r = await _create(client, world, career_counselor_user_id=str(world["coordinator"].id))
    assert (r.status_code, r.json()["detail"]) == (422, "career_counselor_user_id is not an accepted field")


@pytest.mark.asyncio
async def test_school_readers_see_the_structured_fields(client, world):
    await login(client, world["counselor"].email)
    await _create(client, world, weak_areas=["Essays"])
    await login(client, world["coordinator"].email)
    row = (await client.get("/api/v1/school/career-records")).json()[0]
    assert row["weak_areas"] == ["Essays"] and row["status"] == "completed" and LEGACY_KEYS <= set(row)


@pytest.mark.asyncio
async def test_counsellor_payloads_never_carry_student_master_data(client, world):
    """AC26-9 / C10: DEC-SCOPE-028 keeps service roles to name + school; the record serializer adds no student fields."""
    await login(client, world["counselor"].email)
    created = (await _create(client, world)).json()
    listed = (await client.get(RECORDS)).json()[0]
    for body in (created, listed):
        assert not {"grade_or_class", "grade_level", "date_of_birth", "section", "roll_number", "student_code"} & set(body)
