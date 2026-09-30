"""ENH-026 -- counselling record API (spec §5.1, AC26-1..AC26-9, AC-R1..AC-R4)."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school, mk_staff
from enh014_helpers import drain
from httpx import ASGITransport
from sqlalchemy import func, select, update

from app.core.database import SessionLocal
from app.main import app
from app.models import AuditLog, Notification, NotificationDelivery, SchoolCareerRecord, SchoolStudent
from app.notifications import delivery as delivery_module

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
    assert (r.status_code, r.json()["detail"]) == (422, "A scheduled session needs a date and time.")
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


# --- PATCH (Task 4) ---------------------------------------------------------------------------------------------

def _patch_url(rid):
    return f"{RECORDS}/{rid}"


async def _new(client, world, **body):
    r = await _create(client, world, **body)
    assert r.status_code == 201, r.text
    return r.json()


def _audits(action, entity_id):
    return select(func.count()).select_from(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == str(entity_id))


@pytest.mark.asyncio
async def test_full_lifecycle_with_follow_up_loop(client, world):
    await login(client, world["counselor"].email)
    rec = await _new(client, world, status="not_started", notes="")
    url = _patch_url(rec["id"])
    r = await client.patch(url, json={"status": "scheduled", "scheduled_for": "2026-12-01T10:00:00+05:30", "expected_status": "not_started"})
    assert r.status_code == 200 and r.json()["status"] == "scheduled"
    r = await client.patch(url, json={"status": "completed", "notes": "Discussed design."})
    assert r.json()["status"] == "completed" and r.json()["completed_on"] == TODAY.isoformat()
    follow = (TODAY + timedelta(days=7)).isoformat()
    r = await client.patch(url, json={"status": "follow_up_required", "next_follow_up_date": follow})
    assert r.json()["next_follow_up_date"] == follow
    r = await client.patch(url, json={"status": "scheduled", "scheduled_for": "2027-01-05T09:00:00+05:30"})
    assert r.status_code == 200 and r.json()["next_follow_up_date"] is None  # C7: cleared on leaving
    assert r.json()["updated_by_name"] == world["counselor"].full_name


@pytest.mark.parametrize("start,target", [("not_started", "completed"), ("scheduled", "not_started"), ("completed", "scheduled")])
@pytest.mark.asyncio
async def test_skips_and_backward_moves_are_422(client, world, start, target):
    await login(client, world["counselor"].email)
    extra = {"scheduled_for": "2026-12-01T10:00:00+05:30"} if start == "scheduled" else {}
    rec = await _new(client, world, status=start, **extra)
    r = await client.patch(_patch_url(rec["id"]), json={"status": target, "scheduled_for": "2026-12-02T10:00:00+05:30", "notes": "n"})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("Cannot change status from ")


@pytest.mark.asyncio
async def test_rescheduling_requires_a_new_scheduled_for(client, world):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)  # completed
    await client.patch(_patch_url(rec["id"]), json={"status": "follow_up_required", "next_follow_up_date": (TODAY + timedelta(days=1)).isoformat()})
    r = await client.patch(_patch_url(rec["id"]), json={"status": "scheduled"})
    assert (r.status_code, r.json()["detail"]) == (422, "A scheduled session needs a date and time.")


@pytest.mark.asyncio
async def test_follow_up_date_must_not_be_in_the_past(client, world):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    r = await client.patch(_patch_url(rec["id"]), json={"status": "follow_up_required", "next_follow_up_date": (TODAY - timedelta(days=1)).isoformat()})
    assert (r.status_code, r.json()["detail"]) == (422, "The next follow-up date must be today or later.")


@pytest.mark.asyncio
async def test_follow_up_date_messages_are_worded_for_people(client, world):
    """QA-03 (browser QA 2026-09-28): the 422 text is shown to the counsellor as-is, so it names no API field."""
    await login(client, world["counselor"].email)
    rec = await _new(client, world)  # completed
    r = await client.patch(_patch_url(rec["id"]), json={"status": "follow_up_required"})
    assert (r.status_code, r.json()["detail"]) == (422, "Choose the next follow-up date.")
    r = await client.patch(_patch_url(rec["id"]), json={"next_follow_up_date": (TODAY + timedelta(days=3)).isoformat()})
    assert (r.status_code, r.json()["detail"]) == (422, "A next follow-up date can only be set when the status is Follow-up Required.")


@pytest.mark.asyncio
async def test_legacy_row_moves_only_to_completed_or_follow_up(client, world, db_session):
    legacy = SchoolCareerRecord(school_student_id=world["students"][0].id, career_counselor_user_id=world["counselor"].id, record_type="counselling_note", notes="old note")
    db_session.add(legacy)
    await db_session.commit()
    await login(client, world["counselor"].email)
    assert (await client.patch(_patch_url(legacy.id), json={"status": "not_started"})).status_code == 422
    assert (await client.patch(_patch_url(legacy.id), json={"status": "scheduled", "scheduled_for": "2026-12-01T10:00:00+05:30"})).status_code == 422
    r = await client.patch(_patch_url(legacy.id), json={"status": "completed", "expected_status": None})
    assert r.status_code == 200 and r.json()["status"] == "completed" and r.json()["notes"] == "old note"


@pytest.mark.asyncio
async def test_legacy_field_edit_keeps_status_null(client, world, db_session):
    legacy = SchoolCareerRecord(school_student_id=world["students"][0].id, career_counselor_user_id=world["counselor"].id, record_type="guidance_session", notes="old")
    db_session.add(legacy)
    await db_session.commit()
    await login(client, world["counselor"].email)
    r = await client.patch(_patch_url(legacy.id), json={"weak_areas": ["Essays"]})
    assert r.status_code == 200 and r.json()["status"] is None and r.json()["weak_areas"] == ["Essays"]


@pytest.mark.asyncio
async def test_stale_expected_status_is_409_and_writes_nothing(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)  # completed
    r = await client.patch(_patch_url(rec["id"]), json={"expected_status": "scheduled", "notes": "changed"})
    assert r.status_code == 409
    assert r.json()["detail"] == "This record was changed by someone else (now Completed). Reload to see the latest."
    assert await db_session.scalar(_audits("school.career_record_update", rec["id"])) == 0
    saved = await db_session.get(SchoolCareerRecord, rec["id"], populate_existing=True)
    assert saved.notes == "Met."


@pytest.mark.asyncio
async def test_patch_resending_current_values_is_a_noop(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world, weak_areas=["Essays"])
    r = await client.patch(_patch_url(rec["id"]), json={"status": "completed", "notes": "Met.", "weak_areas": ["Essays"], "expected_status": "completed"})
    assert r.status_code == 200
    assert await db_session.scalar(_audits("school.career_record_update", rec["id"])) == 0


@pytest.mark.asyncio
async def test_update_is_audited_with_names_and_status_only(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    await client.patch(_patch_url(rec["id"]), json={"status": "follow_up_required", "next_follow_up_date": (TODAY + timedelta(days=2)).isoformat(), "weak_areas": ["Secret detail"]})
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.career_record_update", AuditLog.entity_id == rec["id"]))
    assert row.metadata_json["status"] == {"old": "completed", "new": "follow_up_required"}
    assert "weak_areas" in row.metadata_json["changed_fields"]
    assert "Secret detail" not in str(row.metadata_json)


@pytest.mark.asyncio
async def test_parents_are_notified_only_on_status_change(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    parent_rows = select(func.count()).select_from(Notification).where(Notification.user_id == world["parent"].id)
    after_create = await db_session.scalar(parent_rows)
    await client.patch(_patch_url(rec["id"]), json={"weak_areas": ["Essays"]})
    assert await db_session.scalar(parent_rows) == after_create
    await client.patch(_patch_url(rec["id"]), json={"status": "follow_up_required", "next_follow_up_date": (TODAY + timedelta(days=2)).isoformat()})
    assert await db_session.scalar(parent_rows) == after_create + 1


@pytest.mark.asyncio
async def test_notification_failure_keeps_the_status_change(client, world, db_session, monkeypatch, enqueued):
    async def boom(*args, **kwargs):
        raise RuntimeError("smtp down")
    await login(client, world["counselor"].email)
    rec = await _new(client, world)  # created while the mailer is healthy
    # ENH-014: the send now happens in the worker; force the failure where it happens.
    monkeypatch.setattr(delivery_module, "send_parent_notification_email", boom)
    r = await client.patch(_patch_url(rec["id"]), json={"status": "follow_up_required", "next_follow_up_date": (TODAY + timedelta(days=2)).isoformat()})
    assert r.status_code == 200
    saved = await db_session.get(SchoolCareerRecord, rec["id"], populate_existing=True)
    assert saved.status == "follow_up_required"
    await drain(enqueued)
    failed = (await db_session.scalars(select(NotificationDelivery).join(Notification, Notification.id == NotificationDelivery.notification_id)
                                       .where(Notification.user_id == world["parent"].id, NotificationDelivery.status == "failed"))).all()
    assert failed and all(d.error == "unexpected RuntimeError" for d in failed)


@pytest.mark.asyncio
async def test_authorization(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    other = await mk_school(db_session, label="E26-Other", students=0)
    outsider = await mk_staff(db_session, other["school"], other["admin"], role="career_counselor")
    await login(client, outsider.email)
    assert (await client.patch(_patch_url(rec["id"]), json={"notes": "x"})).status_code == 403
    await login(client, world["coordinator"].email)
    assert (await client.patch(_patch_url(rec["id"]), json={"notes": "x"})).status_code == 403
    await login(client, world["counselor"].email)
    assert (await client.patch(_patch_url("00000000-0000-0000-0000-000000000000"), json={"notes": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_a_second_portfolio_counsellor_may_edit(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    second = await mk_staff(db_session, world["school"], world["admin"], role="career_counselor")
    await login(client, second.email)
    r = await client.patch(_patch_url(rec["id"]), json={"weak_areas": ["Essays"]})
    assert r.status_code == 200
    assert r.json()["counselor_name"] == world["counselor"].full_name and r.json()["updated_by_name"] == second.full_name


@pytest.mark.asyncio
async def test_below_silver_is_a_tier_denial(client, db_session):
    ctx = await mk_school(db_session, label="E26-Bronze", tier="bronze")
    counselor = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    rec = SchoolCareerRecord(school_student_id=ctx["students"][0].id, career_counselor_user_id=counselor.id, record_type="counselling_note", notes="n", status="not_started")
    db_session.add(rec)
    await db_session.commit()
    await login(client, counselor.email)
    r = await client.patch(_patch_url(rec.id), json={"status": "scheduled", "scheduled_for": "2026-12-01T10:00:00+05:30"})
    assert r.status_code == 403


@asynccontextmanager
async def _client_for(email):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await login(c, email)
        yield c


@asynccontextmanager
async def _held(pk):
    """Another transaction holding the record's row lock until the block ends, so both PATCHes queue behind it."""
    session = SessionLocal()
    try:
        await session.execute(select(SchoolCareerRecord).where(SchoolCareerRecord.id == pk).with_for_update())
        yield
    finally:
        await session.rollback()
        await session.close()


@pytest.mark.asyncio
async def test_concurrent_transitions_serialize_on_the_row_lock(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world, status="scheduled", scheduled_for="2026-12-01T10:00:00+05:30")
    second = await mk_staff(db_session, world["school"], world["admin"], role="career_counselor")
    async with _client_for(world["counselor"].email) as a, _client_for(second.email) as b:
        async with _held(rec["id"]):
            first = asyncio.create_task(a.patch(_patch_url(rec["id"]), json={"status": "completed", "notes": "A", "expected_status": "scheduled"}))
            other = asyncio.create_task(b.patch(_patch_url(rec["id"]), json={"status": "completed", "notes": "B", "expected_status": "scheduled"}))
            await asyncio.sleep(0.3)
        results = sorted([(await first).status_code, (await other).status_code])
    assert results == [200, 409]


@pytest.mark.asyncio
async def test_a_patch_racing_a_transfer_out_of_the_portfolio_is_refused(client, world, db_session):  # AC26-7 (spec §5.1)
    await login(client, world["counselor"].email)
    rec = await _new(client, world, status="scheduled", scheduled_for="2026-12-01T10:00:00+05:30")
    other = await mk_school(db_session, label="E26-RaceB", admin=world["admin"])
    mover = SessionLocal()
    try:
        # Stand-in for transfer approval: hold the student's row lock (as school_transfers.py does), then move the student.
        await mover.execute(select(SchoolStudent).where(SchoolStudent.id == world["students"][0].id).with_for_update())
        pending = asyncio.create_task(client.patch(_patch_url(rec["id"]), json={"status": "completed", "notes": "Race", "expected_status": "scheduled"}))
        await asyncio.sleep(0.5)  # the PATCH holds the record lock and is queued on the student's row lock
        assert not pending.done()
        await mover.execute(update(SchoolStudent).where(SchoolStudent.id == world["students"][0].id).values(school_id=other["school"].id))
        await mover.commit()
    finally:
        await mover.close()
    r = await pending
    assert (r.status_code, r.json()["detail"]) == (403, "This student is at a school outside your own portfolio")
    async with SessionLocal() as check:
        saved = await check.get(SchoolCareerRecord, UUID(rec["id"]))
        assert (saved.status, saved.notes) == ("scheduled", rec["notes"])  # nothing written
        audited = await check.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == rec["id"], AuditLog.action == "school.career_record_update"))
        assert audited == 0


@pytest.mark.asyncio
async def test_record_type_and_owner_cannot_be_patched(client, world):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    for key in ("record_type", "school_student_id", "career_counselor_user_id"):
        r = await client.patch(_patch_url(rec["id"]), json={key: "x"})
        assert (r.status_code, r.json()["detail"]) == (422, f"{key} is not an accepted field")


@pytest.mark.asyncio
async def test_recommendation_patch_accepts_notes_only(client, world):
    await login(client, world["counselor"].email)
    rec = (await client.post(RECORDS, json={"school_student_id": world["sid"], "record_type": "recommendation", "notes": "A"})).json()
    assert (await client.patch(_patch_url(rec["id"]), json={"notes": "B"})).json()["notes"] == "B"
    r = await client.patch(_patch_url(rec["id"]), json={"status": "completed"})
    assert (r.status_code, r.json()["detail"]) == (422, "recommendation records take notes only")
