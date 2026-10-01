"""ENH-020 -- funding support case writes (spec §4.1-§4.5; AC01-AC10, AC12, AC17-AC19; plan Review Focus 1-3)."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school, mk_staff, move_student_directly
from httpx import ASGITransport
from sqlalchemy import func, select, update

from app.api import school_funding
from app.core.database import SessionLocal
from app.main import app
from app.models import AuditLog, Notification, SchoolFundingRecord, SchoolStaffAssignment, SchoolStudent

CASES = "/api/v1/school/funding-records"
IST = ZoneInfo("Asia/Kolkata")
TODAY = datetime.now(IST).date()
RECORD_KEYS = {
    "id", "school_student_id", "support_type", "status", "status_changed_on", "provider_name", "amount_text", "notes",
    "closure_reason", "created_at", "updated_at", "counselor_name", "updated_by_name",
}
SECRET_PROVIDER = "Secret Bank Ltd"
SECRET_NOTES = "Family income details kept private"


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    """Alembic's env.py calls `logging.config.fileConfig`, which DISABLES loggers that already exist; an earlier test that migrates
    in-process (ENH-001's downgrade/upgrade cycle) would silence `app.school.funding` and `caplog` would see nothing (the ENH-030
    fixture, same cause). Production is unaffected (Alembic runs in its own process)."""
    logging.getLogger("app.school.funding").disabled = False
    yield


@pytest_asyncio.fixture
async def world(db_session):
    ctx = await mk_school(db_session, label="E20", students=2)
    ctx["counselor"] = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    ctx["sid"] = str(ctx["students"][0].id)
    ctx["name"] = ctx["students"][0].full_name
    return ctx


async def _create(client, sid, support_type="education_loan", **body):
    return await client.post(CASES, json={"school_student_id": sid, "support_type": support_type, **body})


async def _new(client, world, **body) -> dict:
    r = await _create(client, world["sid"], **body)
    assert r.status_code == 201, r.text
    return r.json()


def _count(model, *where):
    return select(func.count()).select_from(model).where(*where)


def _rows_for(student_id):
    return _count(SchoolFundingRecord, SchoolFundingRecord.school_student_id == UUID(str(student_id)))


def _denied(user_id, reason=None):
    conditions = [AuditLog.action == "school.funding_record_denied", AuditLog.user_id == user_id, AuditLog.outcome == "denied"]
    return select(AuditLog).where(*conditions) if reason is None else select(AuditLog).where(*conditions, AuditLog.metadata_json["reason"].as_string() == reason)


# --- E1 create -----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_starts_at_required_today_and_is_audited_without_contents(client, world, db_session):  # AC01, AC19
    await login(client, world["counselor"].email)
    body = await _new(client, world, provider_name=SECRET_PROVIDER, amount_text="₹5,00,000", notes=SECRET_NOTES)
    assert set(body) == RECORD_KEYS
    assert (body["status"], body["status_changed_on"], body["support_type"]) == ("required", TODAY.isoformat(), "education_loan")
    assert (body["provider_name"], body["amount_text"], body["notes"], body["closure_reason"]) == (SECRET_PROVIDER, "₹5,00,000", SECRET_NOTES, None)
    assert body["counselor_name"] == world["counselor"].full_name and body["updated_by_name"] is None
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.funding_record_create", AuditLog.entity_id == body["id"]))
    assert audit.entity_type == "school_funding_record"
    assert audit.metadata_json == {"support_type": "education_loan", "fields": ["amount_text", "notes", "provider_name"]}
    saved = await db_session.get(SchoolFundingRecord, UUID(body["id"]))
    assert saved.school_id == world["school"].id


@pytest.mark.asyncio
async def test_create_notifies_linked_parents_without_contents(client, world, db_session):  # AC12
    await login(client, world["counselor"].email)
    await _new(client, world, provider_name=SECRET_PROVIDER, notes=SECRET_NOTES)
    note = await db_session.scalar(select(Notification).where(Notification.user_id == world["parent"].id).order_by(Notification.created_at.desc()))
    assert note.title == f"Funding support update for {world['name']}"
    assert note.body == "Education loan support is now being tracked (Required)."
    assert note.action_url == f"/school/parent/children/{world['sid']}"


@pytest.mark.asyncio
async def test_create_for_a_student_with_no_linked_parent_still_succeeds(client, world):  # Review Focus 3
    await login(client, world["counselor"].email)
    r = await _create(client, str(world["students"][1].id), "funding_guidance")
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_create_role_denial_is_audited(client, world, db_session):  # AC02, AC18
    for who in ("coordinator", "principal", "teacher", "parent"):
        await login(client, world[who].email)
        r = await _create(client, world["sid"])
        assert (r.status_code, r.json()["detail"]) == (403, "Career Counselor role required"), who
        assert (await db_session.scalars(_denied(world[who].id, "role"))).all(), who
    assert await db_session.scalar(_rows_for(world["sid"])) == 0


@pytest.mark.asyncio
async def test_create_outside_the_portfolio_is_denied_and_audited(client, world, db_session):  # AC02, AC18
    other = await mk_school(db_session, label="E20-Other", students=0)
    outsider = await mk_staff(db_session, other["school"], other["admin"], role="career_counselor")
    await login(client, outsider.email)
    r = await _create(client, world["sid"])
    assert (r.status_code, r.json()["detail"]) == (403, "This student is at a school outside your own portfolio")
    row = await db_session.scalar(_denied(outsider.id, "outside_portfolio"))
    assert row.entity_type == "school_student" and row.entity_id == world["sid"] and row.metadata_json == {"role": "career_counselor", "reason": "outside_portfolio"}
    assert await db_session.scalar(_rows_for(world["sid"])) == 0


@pytest.mark.asyncio
async def test_unknown_or_malformed_student(client, world):  # AC02, AC04
    await login(client, world["counselor"].email)
    r = await _create(client, "00000000-0000-0000-0000-000000000000")
    assert (r.status_code, r.json()["detail"]) == (404, "Student not found")
    r = await _create(client, "not-a-uuid")
    assert r.status_code == 422 and r.json()["detail"].startswith("school_student_id ")


@pytest.mark.parametrize(
    "tier,allowed",
    [
        ("platinum", {"education_loan", "financial_assistance", "scholarship", "funding_guidance"}),
        ("gold", {"scholarship"}),
        ("silver", set()),
        (None, set()),
    ],
)
@pytest.mark.asyncio
async def test_tier_gate_is_per_support_type(client, db_session, tier, allowed):  # AC03
    ctx = await mk_school(db_session, label=f"E20-{tier}", students=1, tier=tier)
    counselor = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    await login(client, counselor.email)
    for support_type in ("education_loan", "financial_assistance", "scholarship", "funding_guidance"):
        r = await _create(client, str(ctx["students"][0].id), support_type)
        assert r.status_code == (201 if support_type in allowed else 403), (support_type, r.text)
    denials = await db_session.scalar(_count(AuditLog, AuditLog.action == "school.tier_access_denied", AuditLog.user_id == counselor.id))
    assert denials == 4 - len(allowed)


@pytest.mark.asyncio
async def test_second_open_case_of_a_type_is_409_until_the_first_is_finished(client, world, db_session):  # AC04
    await login(client, world["counselor"].email)
    first = await _new(client, world)
    r = await _create(client, world["sid"], notes="again")
    assert (r.status_code, r.json()["detail"]) == (409, f"{world['name']} already has an open education loan case. Open it from the list to update it.")
    assert (await _create(client, world["sid"], "scholarship")).status_code == 201  # another type is its own case
    saved = await db_session.get(SchoolFundingRecord, UUID(first["id"]))
    saved.status, saved.closure_reason = "closed", "Bank refused"
    await db_session.commit()
    assert (await _create(client, world["sid"])).status_code == 201


@asynccontextmanager
async def _client_for(email):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await login(c, email)
        yield c


@pytest.mark.asyncio
async def test_concurrent_creates_one_wins(world, db_session):  # AC04
    second = await mk_staff(db_session, world["school"], world["admin"], role="career_counselor")
    async with _client_for(world["counselor"].email) as a, _client_for(second.email) as b:
        results = await asyncio.gather(_create(a, world["sid"]), _create(b, world["sid"]))
    assert sorted(r.status_code for r in results) == [201, 409]
    assert await db_session.scalar(_rows_for(world["sid"])) == 1


@pytest.mark.parametrize("key", ["status", "school_id", "career_counselor_user_id"])
@pytest.mark.asyncio
async def test_create_forbids_status_owner_and_school(client, world, key):  # AC10
    await login(client, world["counselor"].email)
    value = "approved" if key == "status" else str(world["coordinator"].id)
    r = await _create(client, world["sid"], **{key: value})
    assert (r.status_code, r.json()["detail"]) == (422, f"{key} is not an accepted field")


@pytest.mark.asyncio
async def test_create_survives_a_notification_failure(client, world, db_session, monkeypatch, caplog):  # AC12
    async def boom(*args, **kwargs):
        raise RuntimeError("queue down")

    monkeypatch.setattr(school_funding, "_notify_student_parents", boom)
    await login(client, world["counselor"].email)
    with caplog.at_level(logging.WARNING):
        body = await _new(client, world)
    assert await db_session.get(SchoolFundingRecord, UUID(body["id"])) is not None
    assert any(r.getMessage() == "funding_record_notify_failed" for r in caplog.records)


@pytest.mark.asyncio
async def test_logs_never_carry_case_contents(client, world, caplog):  # AC19
    await login(client, world["counselor"].email)
    with caplog.at_level(logging.INFO):
        await _new(client, world, provider_name=SECRET_PROVIDER, notes=SECRET_NOTES)
        await _create(client, world["sid"], provider_name=SECRET_PROVIDER, notes=SECRET_NOTES)  # the 409 path logs too
    assert any(r.getMessage() == "funding_record_create" for r in caplog.records)
    for record in caplog.records:
        text = f"{record.getMessage()} {getattr(record, 'extra_fields', '')}"
        assert SECRET_PROVIDER not in text and SECRET_NOTES not in text


# --- E2 update -----------------------------------------------------------------------------------------------------------

STAGES = ["counselling", "documents", "application", "approved", "completed"]


def _url(rid) -> str:
    return f"{CASES}/{rid}"


def _updates(rid):
    return _count(AuditLog, AuditLog.action == "school.funding_record_update", AuditLog.entity_id == str(rid))


async def _advance_to(client, rid, target):
    for stage in STAGES[: STAGES.index(target) + 1]:
        r = await client.patch(_url(rid), json={"status": stage})
        assert r.status_code == 200, r.text


async def _latest_note(db, parent_id):
    return await db.scalar(select(Notification).where(Notification.user_id == parent_id).order_by(Notification.created_at.desc()).limit(1))


@pytest.mark.asyncio
async def test_full_lifecycle_one_step_at_a_time(client, world, db_session):  # AC05
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    previous = "required"
    for stage in STAGES:
        r = await client.patch(_url(rec["id"]), json={"status": stage, "expected_status": previous})
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["status"], body["status_changed_on"], body["updated_by_name"]) == (stage, TODAY.isoformat(), world["counselor"].full_name)
        previous = stage
    assert await db_session.scalar(_updates(rec["id"])) == len(STAGES)


@pytest.mark.parametrize("start,target", [("required", "documents"), ("counselling", "required"), ("approved", "application"), ("required", "completed")])
@pytest.mark.asyncio
async def test_skips_and_backward_moves_are_422(client, world, start, target):  # AC05
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    if start != "required":
        await _advance_to(client, rec["id"], start)
    r = await client.patch(_url(rec["id"]), json={"status": target})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("Cannot change status from ")


@pytest.mark.parametrize("body", [{"status": "closed"}, {"status": "closed", "closure_reason": "   "}, {"status": "closed", "closure_reason": None}])
@pytest.mark.asyncio
async def test_closing_needs_a_reason(client, world, body):  # AC06, Review Focus 1
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    r = await client.patch(_url(rec["id"]), json=body)
    assert (r.status_code, r.json()["detail"]) == (422, "Give a reason for closing this case.")


@pytest.mark.parametrize("stage", ["required", "counselling", "approved"])
@pytest.mark.asyncio
async def test_any_open_stage_can_close_with_a_reason(client, world, stage):  # AC05, AC06
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    if stage != "required":
        await _advance_to(client, rec["id"], stage)
    r = await client.patch(_url(rec["id"]), json={"status": "closed", "closure_reason": "  Family chose another lender  "})
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["closure_reason"]) == ("closed", "Family chose another lender")


@pytest.mark.parametrize("body", [{"notes": "x", "closure_reason": "y"}, {"status": "counselling", "closure_reason": "y"}])
@pytest.mark.asyncio
async def test_a_reason_only_when_closing(client, world, db_session, body):  # AC06, Review Focus 2
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    r = await client.patch(_url(rec["id"]), json=body)
    assert (r.status_code, r.json()["detail"]) == (422, "A closure reason can only be given when closing the case.")
    assert await db_session.scalar(_updates(rec["id"])) == 0


@pytest.mark.parametrize("final,label", [("completed", "Completed"), ("closed", "Closed")])
@pytest.mark.asyncio
async def test_final_cases_are_read_only(client, world, db_session, final, label):  # AC07, D10
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    if final == "completed":
        await _advance_to(client, rec["id"], "completed")
    else:
        await client.patch(_url(rec["id"]), json={"status": "closed", "closure_reason": "Withdrawn"})
    before = await db_session.scalar(_updates(rec["id"]))
    for body in ({"notes": "late edit"}, {"status": "closed", "closure_reason": "x"}, {"provider_name": "Other"}):
        r = await client.patch(_url(rec["id"]), json=body)
        assert (r.status_code, r.json()["detail"]) == (422, f"This case is {label} and can no longer be changed.")
    assert await db_session.scalar(_updates(rec["id"])) == before


@pytest.mark.asyncio
async def test_stale_expected_status_is_409_and_writes_nothing(client, world, db_session):  # AC08
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    await client.patch(_url(rec["id"]), json={"status": "counselling"})
    r = await client.patch(_url(rec["id"]), json={"status": "counselling", "notes": "changed", "expected_status": "required"})
    assert (r.status_code, r.json()["detail"]) == (409, "This case was changed by someone else (now Counselling). Reload to see the latest.")
    assert await db_session.scalar(_updates(rec["id"])) == 1
    saved = await db_session.get(SchoolFundingRecord, UUID(rec["id"]), populate_existing=True)
    assert saved.notes == ""


@pytest.mark.asyncio
async def test_repeat_patch_is_a_noop(client, world, db_session):  # AC05
    await login(client, world["counselor"].email)
    rec = await _new(client, world, provider_name="HDFC", notes="n")
    r = await client.patch(_url(rec["id"]), json={"status": "required", "provider_name": " HDFC ", "notes": "n", "expected_status": "required"})
    assert r.status_code == 200 and r.json()["updated_by_name"] is None
    assert await db_session.scalar(_updates(rec["id"])) == 0


@pytest.mark.asyncio
async def test_update_audit_has_field_names_and_status_only(client, world, db_session):  # AC19
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    await client.patch(_url(rec["id"]), json={"status": "counselling", "provider_name": SECRET_PROVIDER, "notes": SECRET_NOTES})
    await client.patch(_url(rec["id"]), json={"amount_text": "₹2 lakh"})
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.funding_record_update", AuditLog.entity_id == rec["id"]))).all()
    metadata = [r.metadata_json for r in rows]
    assert {"changed_fields": ["status", "provider_name", "notes"], "status": {"old": "required", "new": "counselling"}} in metadata
    assert {"changed_fields": ["amount_text"]} in metadata
    assert SECRET_PROVIDER not in str(metadata) and SECRET_NOTES not in str(metadata)


@pytest.mark.asyncio
async def test_parents_notified_only_on_status_change(client, world, db_session):  # AC12
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    parent_rows = _count(Notification, Notification.user_id == world["parent"].id)
    after_create = await db_session.scalar(parent_rows)
    await client.patch(_url(rec["id"]), json={"notes": "edit", "provider_name": SECRET_PROVIDER})
    assert await db_session.scalar(parent_rows) == after_create
    await client.patch(_url(rec["id"]), json={"status": "counselling"})
    assert await db_session.scalar(parent_rows) == after_create + 1
    assert (await _latest_note(db_session, world["parent"].id)).body == "Education loan support is now at Counselling."
    await client.patch(_url(rec["id"]), json={"status": "closed", "closure_reason": "Secret reason"})
    note = await _latest_note(db_session, world["parent"].id)
    assert note.body == "Education loan support is now at Closed." and "Secret" not in note.title + note.body


@pytest.mark.asyncio
async def test_update_survives_a_notification_failure(client, world, db_session, monkeypatch):  # AC12
    await login(client, world["counselor"].email)
    rec = await _new(client, world)

    async def boom(*args, **kwargs):
        raise RuntimeError("queue down")

    monkeypatch.setattr(school_funding, "_notify_student_parents", boom)
    r = await client.patch(_url(rec["id"]), json={"status": "counselling"})
    assert r.status_code == 200 and r.json()["status"] == "counselling"
    saved = await db_session.get(SchoolFundingRecord, UUID(rec["id"]), populate_existing=True)
    assert saved.status == "counselling"


@pytest.mark.parametrize("key", ["support_type", "school_student_id", "school_id", "career_counselor_user_id", "status_changed_on"])
@pytest.mark.asyncio
async def test_type_ids_and_owner_cannot_be_patched(client, world, key):  # AC10
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    r = await client.patch(_url(rec["id"]), json={key: "x"})
    assert (r.status_code, r.json()["detail"]) == (422, f"{key} is not an accepted field")


@pytest.mark.asyncio
async def test_update_denials_are_audited(client, world, db_session):  # AC18
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    other = await mk_school(db_session, label="E20-OtherU", students=0)
    outsider = await mk_staff(db_session, other["school"], other["admin"], role="career_counselor")
    await login(client, outsider.email)
    r = await client.patch(_url(rec["id"]), json={"notes": "x"})
    assert (r.status_code, r.json()["detail"]) == (403, "This student is at a school outside your own portfolio")
    assert (await db_session.scalar(_denied(outsider.id, "outside_portfolio"))).entity_id == rec["id"]
    await login(client, world["coordinator"].email)
    r = await client.patch(_url(rec["id"]), json={"notes": "x"})
    assert (r.status_code, r.json()["detail"]) == (403, "Career Counselor role required")
    assert await db_session.scalar(_denied(world["coordinator"].id, "role")) is not None
    await login(client, world["counselor"].email)
    assert (await client.patch(_url("00000000-0000-0000-0000-000000000000"), json={"notes": "x"})).status_code == 404
    assert await db_session.scalar(_updates(rec["id"])) == 0


@pytest.mark.asyncio
async def test_a_second_portfolio_counsellor_may_advance(client, world, db_session):
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    second = await mk_staff(db_session, world["school"], world["admin"], role="career_counselor")
    await login(client, second.email)
    r = await client.patch(_url(rec["id"]), json={"status": "counselling"})
    assert r.status_code == 200
    assert (r.json()["counselor_name"], r.json()["updated_by_name"]) == (world["counselor"].full_name, second.full_name)


@pytest.mark.asyncio
async def test_a_downgrade_grandfathers_existing_cases(client, world, db_session):  # AC09
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    await login(client, world["admin"].email)
    r = await client.patch(f"/api/v1/overseas-admin/schools/{world['school'].id}", json={"tier": "gold"})
    assert r.status_code == 200, r.text
    await login(client, world["counselor"].email)
    assert (await client.patch(_url(rec["id"]), json={"status": "counselling"})).status_code == 200
    assert (await _create(client, str(world["students"][1].id), "education_loan")).status_code == 403
    assert (await _create(client, str(world["students"][1].id), "scholarship")).status_code == 201


@asynccontextmanager
async def _held(pk):
    """Another transaction holding the case's row lock until the block ends, so both PATCHes queue behind it."""
    session = SessionLocal()
    try:
        await session.execute(select(SchoolFundingRecord).where(SchoolFundingRecord.id == pk).with_for_update())
        yield
    finally:
        await session.rollback()
        await session.close()


@pytest.mark.asyncio
async def test_concurrent_transitions_serialize_on_the_row_lock(world, db_session):  # spec §4.3
    second = await mk_staff(db_session, world["school"], world["admin"], role="career_counselor")
    async with _client_for(world["counselor"].email) as a, _client_for(second.email) as b:
        rec = await _new(a, world)
        async with _held(rec["id"]):
            first = asyncio.create_task(a.patch(_url(rec["id"]), json={"status": "counselling", "expected_status": "required"}))
            other = asyncio.create_task(b.patch(_url(rec["id"]), json={"status": "closed", "closure_reason": "Withdrawn", "expected_status": "required"}))
            await asyncio.sleep(0.3)
        results = sorted([(await first).status_code, (await other).status_code])
    assert results == [200, 409]


@pytest.mark.asyncio
async def test_a_patch_racing_a_transfer_out_of_the_portfolio_is_refused(client, world, db_session):  # spec §4.3
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    other = await mk_school(db_session, label="E20-RaceB", admin=world["admin"])
    mover = SessionLocal()
    try:
        await mover.execute(select(SchoolStudent).where(SchoolStudent.id == world["students"][0].id).with_for_update())
        pending = asyncio.create_task(client.patch(_url(rec["id"]), json={"status": "counselling", "expected_status": "required"}))
        await asyncio.sleep(0.5)  # the PATCH holds the case lock and waits on the student's row lock
        assert not pending.done()
        await mover.execute(update(SchoolStudent).where(SchoolStudent.id == world["students"][0].id).values(school_id=other["school"].id))
        await mover.commit()
    finally:
        await mover.close()
    r = await pending
    assert (r.status_code, r.json()["detail"]) == (403, "This student is at a school outside your own portfolio")
    async with SessionLocal() as check:
        assert (await check.get(SchoolFundingRecord, UUID(rec["id"]))).status == "required"


@pytest.mark.asyncio
async def test_previous_school_case_is_read_only_after_transfer(client, world, db_session):  # AC17, D12
    await login(client, world["counselor"].email)
    rec = await _new(client, world)
    new_school = await mk_school(db_session, label="E20-New", admin=world["admin"], students=0)
    db_session.add(SchoolStaffAssignment(user_id=world["counselor"].id, school_id=new_school["school"].id, role="career_counselor", assigned_by_user_id=world["admin"].id))
    await db_session.commit()
    await move_student_directly(db_session, world["students"][0], new_school["school"])
    # the counsellor covers both schools, so only the creating-school rule (D12) refuses
    r = await client.patch(_url(rec["id"]), json={"status": "counselling"})
    assert (r.status_code, r.json()["detail"]) == (403, "This case belongs to the student's previous school and can no longer be changed.")
    assert (await db_session.scalar(_denied(world["counselor"].id, "previous_school"))).entity_id == rec["id"]
    assert (await _create(client, world["sid"])).status_code == 201  # the new school opens its own case
