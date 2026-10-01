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
from enh005_helpers import login, mk_school, mk_staff
from httpx import ASGITransport
from sqlalchemy import func, select

from app.api import school_funding
from app.main import app
from app.models import AuditLog, Notification, SchoolFundingRecord

CASES = "/api/v1/school/funding-records"
IST = ZoneInfo("Asia/Kolkata")
TODAY = datetime.now(IST).date()
RECORD_KEYS = {
    "id", "school_student_id", "support_type", "status", "status_changed_on", "provider_name", "amount_text", "notes",
    "closure_reason", "created_at", "updated_at", "counselor_name", "updated_by_name",
}
SECRET_PROVIDER = "Secret Bank Ltd"
SECRET_NOTES = "Family income details kept private"


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
