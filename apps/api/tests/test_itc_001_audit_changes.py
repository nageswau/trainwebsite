"""itc-001 -- field-change audit with before and after values (AC1-AC4; Q-02: one row per student whose attendance actually changed).

The shared `audit_changes` helper, its first adopters (a trainer's attendance overwrite, the admin lead stage/owner PATCH) and the
`changes` field on GET /admin/audit."""

import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.services import audit_changes
from tests.bdm001_helpers import make_user
from tests.bdm017_helpers import ADMIN_LEADS, as_user
from tests.tel004_helpers import lead
from tests.test_nehn_023_attendance_corrections import _login, _user, _world

AUDIT = "/api/v1/admin/audit"
ATTENDANCE = "/api/v1/workflows/it/trainer/attendance"
DAY = datetime.date(2026, 10, 20)  # _world's existing "absent" mark


# --- the helper ---------------------------------------------------------------------------------------------------------------
def test_changes_lists_only_the_changed_fields_as_old_new_pairs():
    before = {"status": "absent", "batch": "B1", "owner_id": None}
    after = {"status": "present", "batch": "B1", "owner_id": "u-2"}
    assert audit_changes.changes(before, after) == {"status": ["absent", "present"], "owner_id": [None, "u-2"]}


def test_no_change_is_an_empty_diff():
    assert audit_changes.changes({"status": "absent"}, {"status": "absent"}) == {}


def test_blank_and_none_are_the_same_empty_value():
    """Browser QA-01: the attendance form sends "" for an empty note, so a re-save over a null note is not a change."""
    assert audit_changes.changes({"notes": None, "owner_id": ""}, {"notes": "", "owner_id": None}) == {}
    assert audit_changes.changes({"status": None}, {"status": "present"}) == {"status": [None, "present"]}


def test_pii_fields_are_marked_changed_never_stored_as_values():
    before = {"phone": "9000000001", "email": "a@x.in", "notes": "old note", "parent_phone": "1", "reason": "r1", "status": "a"}
    after = {"phone": "9000000002", "email": "b@x.in", "notes": "new note", "parent_phone": "2", "reason": "r2", "status": "a"}
    diff = audit_changes.changes(before, after)
    assert diff == {"phone": "changed", "email": "changed", "notes": "changed", "parent_phone": "changed", "reason": "changed"}
    assert "9000000001" not in str(diff) and "new note" not in str(diff)


def test_values_are_json_safe():
    uid = uuid.uuid4()
    before = {"fee": Decimal("1000.50"), "day": datetime.date(2026, 1, 2), "at": None, "who": None}
    after = {"fee": Decimal("1200.00"), "day": datetime.date(2026, 1, 3), "at": datetime.datetime(2026, 1, 3, 9, 30, tzinfo=datetime.UTC), "who": uid}
    assert audit_changes.changes(before, after) == {
        "fee": ["1000.50", "1200.00"],
        "day": ["2026-01-02", "2026-01-03"],
        "at": [None, "2026-01-03T09:30:00+00:00"],
        "who": [None, str(uid)],
    }


@pytest.mark.asyncio
async def test_audit_change_writes_one_row_with_changes_and_nothing_when_unchanged(db_session):
    actor = await make_user(db_session, "it_admin", "it")
    entity = uuid.uuid4().hex
    row = audit_changes.audit_change(db_session, actor, "thing.update", "itc001", entity, {"status": "a"}, {"status": "b"}, metadata={"k": 1})
    assert audit_changes.audit_change(db_session, actor, "thing.update", "itc001", entity, {"status": "b"}, {"status": "b"}) is None
    await db_session.commit()
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == entity))).all()
    assert [r.id for r in rows] == [row.id]
    assert (rows[0].user_id, rows[0].action, rows[0].metadata_json) == (actor.id, "thing.update", {"k": 1, "changes": {"status": ["a", "b"]}})


@pytest.mark.asyncio
async def test_a_rollback_leaves_no_audit_row(db_session):
    actor = await make_user(db_session, "it_admin", "it")
    entity = uuid.uuid4().hex
    audit_changes.audit_change(db_session, actor, "thing.update", "itc001", entity, {"status": "a"}, {"status": "b"})
    await db_session.rollback()
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.entity_id == entity)) is None


# --- adopter: attendance overwrite (the backlog's + case; Q-02) ---------------------------------------------------------------
async def _mark(client, batch, records):
    return await client.post(ATTENDANCE, json={"batch_id": str(batch.id), "session_date": DAY.isoformat(), "records": records})


async def _attendance_rows(db_session, attendance_id):
    return (await db_session.scalars(select(AuditLog).where(AuditLog.action == "attendance.update", AuditLog.entity_id == str(attendance_id)))).all()


@pytest.mark.asyncio
async def test_re_marking_absent_to_present_audits_the_old_and_new_status(client, db_session):
    trainer = await _user(db_session, "trainer", "Audit Trainer")
    student, batch, attendance = await _world(db_session, trainer=trainer)
    await _login(client, trainer)
    response = await _mark(client, batch, [{"student_id": str(student.id), "status": "present", "notes": "Joined late"}])
    assert response.status_code == 201, response.text
    rows = await _attendance_rows(db_session, attendance.id)
    assert len(rows) == 1
    assert rows[0].user_id == trainer.id and rows[0].entity_type == "attendance"
    assert rows[0].metadata_json == {
        "batch_id": str(batch.id),
        "student_id": str(student.id),
        "session_date": DAY.isoformat(),
        "changes": {"status": ["absent", "present"], "notes": "changed"},
    }
    # the bulk row is unchanged (nehn-042 shape)
    bulk = await db_session.scalar(select(AuditLog).where(AuditLog.action == "attendance.bulk_mark", AuditLog.entity_id == str(batch.id)))
    assert bulk.metadata_json == {"session_date": DAY.isoformat(), "records": 1}


@pytest.mark.asyncio
async def test_an_unchanged_re_mark_and_a_first_mark_write_no_change_row(client, db_session):
    trainer = await _user(db_session, "trainer", "Audit Trainer")
    student, batch, attendance = await _world(db_session, trainer=trainer)
    await _login(client, trainer)
    assert (await _mark(client, batch, [{"student_id": str(student.id), "status": "absent"}])).status_code == 201
    assert await _attendance_rows(db_session, attendance.id) == []
    first = await db_session.scalar(select(AuditLog).where(AuditLog.action == "attendance.update", AuditLog.metadata_json["student_id"].as_string() == str(student.id)))
    assert first is None


# --- adopter: admin lead PATCH (stage and owner) -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_lead_patch_records_the_stage_and_owner_change_in_its_one_row(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    counselor = await make_user(db_session, "counselor", "it")
    row = await lead(db_session, status="contacted")
    await as_user(client, admin)
    url = f"{ADMIN_LEADS}/{row.id}"
    assert (await client.patch(url, json={"status": "interested", "owner_id": str(counselor.id)})).status_code == 200
    assert (await client.patch(url, json={"status": "interested"})).status_code == 200  # a resend: no change
    audits = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == str(row.id), AuditLog.action == "lead.update").order_by(AuditLog.created_at))).all()
    assert audits == [
        {"status": "interested", "owner_id": str(counselor.id), "changes": {"status": ["contacted", "interested"], "owner_id": [None, str(counselor.id)]}},
        {"status": "interested"},
    ]


# --- the viewer --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_audit_returns_changes_only_in_the_field_diff_shape(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    kind = f"itc001.{uuid.uuid4().hex[:10]}"
    db_session.add_all(
        [
            AuditLog(user_id=admin.id, action="a.diff", entity_type=kind, entity_id="1", metadata_json={"changes": {"status": ["absent", "present"]}}),
            AuditLog(user_id=admin.id, action="a.legacy", entity_type=kind, entity_id="2", metadata_json={"changes": [{"kpi": "x", "from": 1, "to": 2}]}),
            AuditLog(user_id=admin.id, action="a.none", entity_type=kind, entity_id="3", metadata_json={}),
        ]
    )
    await db_session.commit()
    await as_user(client, admin)
    response = await client.get(AUDIT, params={"entity_type": kind})
    assert response.status_code == 200
    assert {r["action"]: r["changes"] for r in response.json()} == {"a.diff": {"status": ["absent", "present"]}, "a.legacy": None, "a.none": None}


@pytest.mark.asyncio
async def test_a_non_admin_still_gets_403(client, db_session):
    trainer = await _user(db_session, "trainer", "Not Admin")
    await _login(client, trainer)
    assert (await client.get(AUDIT)).status_code == 403
