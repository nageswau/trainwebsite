"""ENH-027 -- structured psychometric result fields through the API (spec §7: AC01-AC06, AC10)."""

import logging
from datetime import date, timedelta
from uuid import UUID

import pytest
from enh005_helpers import login, mk_school, mk_staff
from sqlalchemy import func, select

from app.models import AuditLog, Notification, SchoolPsychometricRecord

RECORDS = "/api/v1/school/psychometric-team/records"
FULL = {
    "test_date": "2026-09-10",
    "strengths": ["Logical reasoning", "Verbal ability"],
    "interest_areas": ["Engineering", "Design"],
    "personality_indicators": ["Analytical", "Reflective"],
    "recommended_careers": ["Software engineer", "Product designer"],
    "recommended_stream": ["Science (PCM)"],
    "counsellor_remarks": "Strong analytical profile.\nDiscuss design electives.",
    "parent_discussion_on": "2026-09-15",
    "parent_discussion_notes": "Parents agreed to explore design camps.",
    "follow_up_on": "2026-10-15",
}
KEYS = tuple(FULL)


async def _world(db, students: int = 1) -> dict:
    w = await mk_school(db, label="E27", students=students)
    w["psych"] = await mk_staff(db, w["school"], w["admin"], role="psychometric_team")
    w["student"] = w["students"][0]
    return w


async def _create(client, w, **extra) -> dict:
    r = await client.post(RECORDS, json={"school_student_id": str(w["student"].id), "assessment_type": "Aptitude Test", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _results(row: dict) -> dict:
    return {k: row[k] for k in KEYS}


async def _count(db, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where))


async def _team_row(client, record_id: str) -> dict:
    return next(r for r in (await client.get(RECORDS)).json() if r["id"] == record_id)


# --- AC01 ---
@pytest.mark.asyncio
async def test_create_with_all_twelve_fields_round_trips(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    body = await _create(client, w, report_url="/r.pdf", **FULL)
    assert (body["assessment_type"], body["report_url"], body["status"]) == ("Aptitude Test", "/r.pdf", "completed")
    assert _results(body) == FULL
    assert _results(await _team_row(client, body["id"])) == FULL


# --- AC02 ---
@pytest.mark.asyncio
async def test_patch_changes_only_sent_keys_and_null_clears(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w, **FULL)
    r = await client.patch(f"{RECORDS}/{created['id']}", json={"strengths": ["Numerical"], "follow_up_on": None})
    assert r.status_code == 200, r.text
    assert _results(r.json()) == {**FULL, "strengths": ["Numerical"], "follow_up_on": None}


@pytest.mark.asyncio
async def test_result_only_patch_keeps_status_and_sends_no_notification(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w)
    parent_notes = await _count(db_session, Notification, Notification.user_id == w["parent"].id)
    r = await client.patch(f"{RECORDS}/{created['id']}", json=FULL)
    assert (r.status_code, r.json()["status"]) == (200, "assigned")
    assert await _count(db_session, Notification, Notification.user_id == w["parent"].id) == parent_notes
    r = await client.patch(f"{RECORDS}/{created['id']}", json={"report_url": "/r.pdf"})
    assert r.json()["status"] == "completed"
    assert _results(r.json()) == FULL
    assert await _count(db_session, Notification, Notification.user_id == w["parent"].id) == parent_notes + 1


# --- AC03 ---
@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"strengths": "Logic"}, "strengths"),
        ({"strengths": [f"s{i}" for i in range(21)]}, "strengths"),
        ({"interest_areas": ["x" * 81]}, "interest_areas"),
        ({"personality_indicators": ["ok", "bad\x00"]}, "personality_indicators"),
        ({"counsellor_remarks": "x" * 4001}, "counsellor_remarks"),
        ({"parent_discussion_notes": "x" * 2001}, "parent_discussion_notes"),
        ({"counsellor_remarks": "a‮b"}, "counsellor_remarks"),
        ({"counsellor_remarks": 42}, "counsellor_remarks"),
        ({"test_date": "2026-02-30"}, "test_date"),
        ({"follow_up_on": 1700000000}, "follow_up_on"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_result_patch_is_422_and_changes_nothing(client, db_session, patch, field):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w, **FULL)
    audits = await _count(db_session, AuditLog, AuditLog.entity_id == created["id"])
    r = await client.patch(f"{RECORDS}/{created['id']}", json={"report_url": "/r.pdf", **patch})
    assert r.status_code == 422, r.text
    assert r.json()["detail"].startswith(f"{field} ")
    row = await _team_row(client, created["id"])
    assert _results(row) == FULL and (row["report_url"], row["status"]) == (None, "assigned")  # report_url not half-applied
    assert await _count(db_session, AuditLog, AuditLog.entity_id == created["id"]) == audits


@pytest.mark.asyncio
async def test_invalid_result_on_create_creates_nothing(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    r = await client.post(RECORDS, json={"school_student_id": str(w["student"].id), "assessment_type": "Aptitude Test", "strengths": "Logic"})
    assert (r.status_code, r.json()["detail"].startswith("strengths ")) == (422, True)
    assert await _count(db_session, SchoolPsychometricRecord, SchoolPsychometricRecord.school_student_id == w["student"].id) == 0


@pytest.mark.asyncio
async def test_existing_create_messages_are_unchanged(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    r = await client.post(RECORDS, json={"school_student_id": str(w["student"].id), "strengths": "Logic"})
    assert (r.status_code, r.json()["detail"]) == (422, "assessment_type is required")


# --- AC04 ---
@pytest.mark.asyncio
async def test_other_roles_cannot_write_results(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w)
    counselor = await mk_staff(db_session, w["school"], w["admin"], role="career_counselor")
    for user in (w["coordinator"], w["principal"], w["teacher"], w["parent"], counselor):
        await login(client, user.email)
        assert (await client.patch(f"{RECORDS}/{created['id']}", json={"strengths": ["x"]})).status_code == 403, user.role
        r = await client.post(RECORDS, json={"school_student_id": str(w["student"].id), "assessment_type": "X", **FULL})
        assert r.status_code == 403, user.role


@pytest.mark.asyncio
async def test_out_of_portfolio_member_gets_403_before_validation(client, db_session):
    w = await _world(db_session)
    other = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w)
    await login(client, other["psych"].email)
    for body in ({"strengths": ["x"]}, {"strengths": "not a list"}):
        assert (await client.patch(f"{RECORDS}/{created['id']}", json=body)).status_code == 403
    r = await client.post(RECORDS, json={"school_student_id": str(w["student"].id), "assessment_type": "X", "strengths": "not a list"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_expired_partnership_blocks_a_result_patch_and_changes_nothing(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w)
    w["school"].tier_valid_until = date.today() - timedelta(days=2)
    await db_session.commit()
    r = await client.patch(f"{RECORDS}/{created['id']}", json=FULL)
    assert r.status_code == 403
    record = await db_session.get(SchoolPsychometricRecord, UUID(created["id"]))
    await db_session.refresh(record)
    assert record.strengths is None and record.test_date is None


# --- AC05 ---
@pytest.mark.asyncio
async def test_readers_see_result_fields_in_every_read_path(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w, report_url="/r.pdf", **FULL)
    sid = w["student"].id

    await login(client, w["coordinator"].email)
    row = next(r for r in (await client.get("/api/v1/school/psychometric-records")).json() if r["id"] == created["id"])
    assert _results(row) == FULL
    assert "report_url" not in row  # Client Question #20: unchanged

    await login(client, w["parent"].email)
    overview = (await client.get(f"/api/v1/school/students/{sid}/overview")).json()
    assert _results(overview["psychometric"]["assessments"][0]) == FULL

    await login(client, w["teacher"].email)
    portfolio = (await client.get(f"/api/v1/school/students/{sid}/portfolio")).json()
    assert _results(portfolio["psychometric_report"][0]) == FULL

    await login(client, w["principal"].email)
    view = (await client.get(f"/api/v1/school/students/{sid}/360-view")).json()
    assert _results(view["tabs"]["psychometric_assessment"]["data"]["assessments"][0]) == FULL


# --- AC06 ---
@pytest.mark.asyncio
async def test_legacy_record_serializes_nulls_everywhere(client, db_session):
    w = await _world(db_session)
    legacy = SchoolPsychometricRecord(school_student_id=w["student"].id, psychometric_team_user_id=w["psych"].id, assessment_type="Legacy Test", status="assigned")
    db_session.add(legacy)
    await db_session.commit()
    nulls = dict.fromkeys(KEYS)

    await login(client, w["psych"].email)
    assert _results(await _team_row(client, str(legacy.id))) == nulls
    await login(client, w["coordinator"].email)
    row = next(r for r in (await client.get("/api/v1/school/psychometric-records")).json() if r["id"] == str(legacy.id))
    assert _results(row) == nulls
    await login(client, w["principal"].email)
    view = (await client.get(f"/api/v1/school/students/{w['student'].id}/360-view")).json()
    assert _results(view["tabs"]["psychometric_assessment"]["data"]["assessments"][0]) == nulls


# --- AC10 ---
@pytest.mark.asyncio
async def test_patch_ignores_ownership_student_and_status_keys(client, db_session):
    w = await _world(db_session, students=2)
    await login(client, w["psych"].email)
    created = await _create(client, w)
    r = await client.patch(f"{RECORDS}/{created['id']}", json={
        "school_student_id": str(w["students"][1].id), "psychometric_team_user_id": str(w["coordinator"].id),
        "status": "completed", "assessment_type": "Changed", "strengths": ["Kept"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["school_student_id"], body["status"], body["assessment_type"], body["strengths"]) == (str(w["student"].id), "assigned", "Aptitude Test", ["Kept"])
    record = await db_session.get(SchoolPsychometricRecord, UUID(created["id"]))
    await db_session.refresh(record)
    assert record.psychometric_team_user_id == w["psych"].id


@pytest.mark.asyncio
async def test_audit_metadata_names_fields_never_values(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w, **FULL)
    await client.patch(f"{RECORDS}/{created['id']}", json={"strengths": ["Secret strength"], "report_url": "/r.pdf"})
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == created["id"]).order_by(AuditLog.created_at))).all()
    create_row, update_row = rows[0], rows[-1]
    assert create_row.metadata_json == {"assessment_type": "Aptitude Test", "fields": sorted(KEYS)}
    assert update_row.metadata_json == {"fields": ["report_url", "strengths"]}
    assert "Secret strength" not in str([r.metadata_json for r in rows])


@pytest.mark.asyncio
async def test_saving_results_logs_field_names_never_values(client, db_session, caplog):
    caplog.set_level(logging.DEBUG)
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w, strengths=["Secret strength"])
    await client.patch(f"{RECORDS}/{created['id']}", json={"counsellor_remarks": "Secret remark", "follow_up_on": "2026-10-15"})
    saved = [getattr(r, "extra_fields", {}) for r in caplog.records if r.getMessage() == "psychometric_results_saved"]
    assert [(s["action"], s["fields"]) for s in saved] == [("create", ["strengths"]), ("update", ["counsellor_remarks", "follow_up_on"])]
    assert all(s["record_id"] == created["id"] and s["actor_id"] == str(w["psych"].id) for s in saved)
    logged = "\n".join(f"{r.getMessage()} {getattr(r, 'extra_fields', '')}" for r in caplog.records)
    assert "Secret strength" not in logged and "Secret remark" not in logged


@pytest.mark.asyncio
async def test_blank_date_clears_and_markup_is_stored_as_plain_text(client, db_session):
    w = await _world(db_session)
    await login(client, w["psych"].email)
    created = await _create(client, w, test_date="2026-09-10")
    r = await client.patch(f"{RECORDS}/{created['id']}", json={"test_date": "", "counsellor_remarks": "<script>alert(1)</script>"})
    assert (r.json()["test_date"], r.json()["counsellor_remarks"]) == (None, "<script>alert(1)</script>")
