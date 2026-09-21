import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from enh005_helpers import login, mk_request, mk_school, mk_student, move_student_directly
from sqlalchemy import select, update

from app.models import AuditLog, SchoolStudentTransferRequest

# ENH-005 spec §5.2: destinations, the coordinator's own request list (redaction, status filter, pagination), cancel, history.

DEST = "/api/v1/school/transfer-destinations"
LIST = "/api/v1/school/transfer-requests"
CANCEL = "/api/v1/school/transfer-requests/{rid}/cancel"
HISTORY = "/api/v1/school/students/{sid}/transfer-history"
NOT_PERMITTED = "Not permitted for this transfer request"
DECIDED = "This transfer request has already been decided"
REQUEST_KEYS = {"id", "direction", "status", "student_id", "student_code", "student_name", "from_school", "to_school", "reason", "decision_note", "created_at", "decided_at"}


@pytest_asyncio.fixture
async def three(db_session):
    a = await mk_school(db_session, label="A", students=2)
    b = await mk_school(db_session, label="B")
    c = await mk_school(db_session, label="C")
    return a, b, c


async def _file(db, student, *, frm, to, filer, requester, **kw):
    return await mk_request(db, student, from_school=frm["school"], to_school=to["school"], filed_by_school=filer["school"], requester=requester, **kw)


# ------------------------------------------------------------------------------------------ destinations


@pytest.mark.asyncio
async def test_destinations_are_every_other_school_as_id_and_name_only(client, db_session, three):
    a, b, c = three
    await login(client, a["coordinator"].email)
    response = await client.get(DEST)
    assert response.status_code == 200, response.text
    by_id = {row["id"]: row for row in response.json()}
    assert str(a["school"].id) not in by_id
    assert by_id[str(b["school"].id)] == {"id": str(b["school"].id), "name": b["school"].name}
    assert by_id[str(c["school"].id)]["name"] == c["school"].name
    assert all(set(row) == {"id", "name"} for row in by_id.values())


@pytest.mark.asyncio
async def test_destinations_are_for_coordinators_only(client, db_session, three):
    a, _, _ = three
    assert (await client.get(DEST)).status_code == 401
    await login(client, a["parent"].email)
    assert (await client.get(DEST)).status_code == 403


# ------------------------------------------------------------------------------------------ list


@pytest.mark.asyncio
async def test_each_coordinator_lists_only_the_requests_their_own_school_filed(client, db_session, three):
    a, b, c = three
    a1, a2 = a["students"]
    await _file(db_session, a1, frm=a, to=b, filer=a, requester=a["coordinator"])  # A asks to send a1 to B
    await _file(db_session, a2, frm=a, to=c, filer=c, requester=c["coordinator"])  # C asks for a2 (incoming for C)

    await login(client, a["coordinator"].email)
    mine = (await client.get(LIST)).json()
    assert [(r["direction"], r["student_id"]) for r in mine["items"]] == [("outgoing", str(a1.id))]
    assert mine["total"] == 1
    await login(client, b["coordinator"].email)  # B is only the destination: it did not file, so it sees nothing
    assert (await client.get(LIST)).json()["items"] == []
    await login(client, c["coordinator"].email)
    assert [r["direction"] for r in (await client.get(LIST)).json()["items"]] == ["incoming"]


@pytest.mark.asyncio
async def test_status_filter_defaults_to_pending_and_rejects_an_unknown_value(client, db_session, three):
    a, b, _ = three
    a1, a2 = a["students"]
    await _file(db_session, a1, frm=a, to=b, filer=a, requester=a["coordinator"], status="pending")
    await _file(db_session, a2, frm=a, to=b, filer=a, requester=a["coordinator"], status="cancelled")
    await login(client, a["coordinator"].email)

    assert [r["status"] for r in (await client.get(LIST)).json()["items"]] == ["pending"]
    assert [r["status"] for r in (await client.get(LIST, params={"status": "cancelled"})).json()["items"]] == ["cancelled"]
    assert {r["status"] for r in (await client.get(LIST, params={"status": "all"})).json()["items"]} == {"pending", "cancelled"}
    assert (await client.get(LIST, params={"status": "bogus"})).status_code == 422


@pytest.mark.asyncio
async def test_pagination_orders_newest_first_returns_total_and_bounds_its_inputs(client, db_session, three):
    a, b, _ = three
    kids = [a["students"][0], a["students"][1], await mk_student(db_session, a["school"], a["coordinator"], "third")]
    await db_session.commit()
    rows = [await _file(db_session, k, frm=a, to=b, filer=a, requester=a["coordinator"]) for k in kids]
    await login(client, a["coordinator"].email)

    first = (await client.get(LIST, params={"limit": 2, "offset": 0})).json()
    second = (await client.get(LIST, params={"limit": 2, "offset": 2})).json()

    assert (first["total"], first["limit"], first["offset"]) == (3, 2, 0)
    assert [r["id"] for r in first["items"]] == [str(rows[2].id), str(rows[1].id)]  # newest first
    assert [r["id"] for r in second["items"]] == [str(rows[0].id)]
    for bad in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "x"}):
        assert (await client.get(LIST, params=bad)).status_code == 422, bad


@pytest.mark.asyncio
async def test_a_pending_incoming_row_is_redacted_with_the_same_schema_and_complete_once_approved(client, db_session, three):
    a, b, c = three
    a1, a2 = a["students"]
    outgoing = await _file(db_session, a1, frm=a, to=b, filer=a, requester=a["coordinator"])
    incoming = await _file(db_session, a2, frm=a, to=c, filer=c, requester=c["coordinator"])
    await login(client, c["coordinator"].email)

    (row,) = (await client.get(LIST)).json()["items"]
    assert row["student_id"] is None and row["student_name"] is None and row["from_school"] is None
    assert row["student_code"] == a2.student_code and row["to_school"]["id"] == str(c["school"].id)
    await login(client, a["coordinator"].email)
    (full,) = (await client.get(LIST)).json()["items"]
    assert set(row) == set(full) == REQUEST_KEYS  # one schema, redacted or not

    await db_session.execute(update(SchoolStudentTransferRequest).where(SchoolStudentTransferRequest.id == incoming.id).values(status="approved", decided_at=datetime.now(UTC)))
    await db_session.commit()
    await login(client, c["coordinator"].email)
    (approved,) = (await client.get(LIST, params={"status": "approved"})).json()["items"]
    assert (approved["student_id"], approved["student_name"], approved["from_school"]["id"]) == (str(a2.id), a2.full_name, str(a["school"].id))
    assert outgoing.id != incoming.id


# ------------------------------------------------------------------------------------------ cancel


@pytest.mark.asyncio
async def test_the_filing_school_can_cancel_a_pending_request_once(client, db_session, three):
    a, b, _ = three
    row = await _file(db_session, a["students"][0], frm=a, to=b, filer=a, requester=a["coordinator"])
    await login(client, a["coordinator"].email)

    first = await client.post(CANCEL.format(rid=row.id))
    second = await client.post(CANCEL.format(rid=row.id))

    assert first.status_code == 200, first.text
    assert (first.json()["status"], first.json()["decided_at"] is not None) == ("cancelled", True)
    assert (second.status_code, second.json()) == (409, {"detail": DECIDED})
    await db_session.refresh(row)
    assert (row.status, row.decided_by_user_id) == ("cancelled", a["coordinator"].id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.transfer_request_cancelled", AuditLog.entity_id == str(row.id)))
    assert audit is not None and audit.user_id == a["coordinator"].id


@pytest.mark.asyncio
async def test_cancelling_a_request_you_did_not_file_or_that_does_not_exist_is_the_identical_403(client, db_session, three):
    a, b, _ = three
    row = await _file(db_session, a["students"][0], frm=a, to=b, filer=a, requester=a["coordinator"])
    await login(client, b["coordinator"].email)  # the destination school did not file it

    theirs = await client.post(CANCEL.format(rid=row.id))
    unknown = await client.post(CANCEL.format(rid=uuid.uuid4()))

    assert (theirs.status_code, theirs.json()) == (unknown.status_code, unknown.json()) == (403, {"detail": NOT_PERMITTED})
    await db_session.refresh(row)
    assert row.status == "pending"
    assert (await client.post(CANCEL.format(rid="not-a-uuid"))).status_code == 422


@pytest.mark.asyncio
async def test_a_decided_request_cannot_be_cancelled(client, db_session, three):
    a, b, _ = three
    row = await _file(db_session, a["students"][0], frm=a, to=b, filer=a, requester=a["coordinator"], status="approved")
    await login(client, a["coordinator"].email)
    response = await client.post(CANCEL.format(rid=row.id))
    assert (response.status_code, response.json()) == (409, {"detail": DECIDED})


# ------------------------------------------------------------------------------------------ history


@pytest.mark.asyncio
async def test_history_lists_approved_transfers_without_reason_or_staff_ids_for_the_new_school_and_the_parent(client, db_session, three):
    a, b, _ = three
    child = a["students"][0]
    approved = await _file(db_session, child, frm=a, to=b, filer=a, requester=a["coordinator"], status="approved", reason="PRIVATE reason")
    await db_session.execute(update(SchoolStudentTransferRequest).where(SchoolStudentTransferRequest.id == approved.id).values(decided_at=datetime.now(UTC), decided_by_user_id=a["admin"].id))
    await _file(db_session, child, frm=a, to=b, filer=b, requester=b["coordinator"], status="rejected")  # not approved: not history
    await db_session.commit()
    await move_student_directly(db_session, child, b["school"])

    for who in (b["coordinator"], a["parent"]):  # the new school's coordinator, and the parent (account still at A) by link
        await login(client, who.email)
        response = await client.get(HISTORY.format(sid=child.id))
        assert response.status_code == 200, (who.role, response.text)
        body = response.json()
        assert body["student"] == {"id": str(child.id), "full_name": child.full_name}
        (entry,) = body["history"]
        assert set(entry) == {"id", "decided_at", "from_school", "to_school"}
        assert (entry["from_school"]["name"], entry["to_school"]["name"]) == (a["school"].name, b["school"].name)
    await login(client, a["coordinator"].email)  # the losing school can no longer read the student at all
    assert (await client.get(HISTORY.format(sid=child.id))).status_code == 403


@pytest.mark.asyncio
async def test_history_is_empty_for_a_student_who_never_transferred(client, db_session, three):
    a, _, _ = three
    await login(client, a["coordinator"].email)
    assert (await client.get(HISTORY.format(sid=a["students"][0].id))).json()["history"] == []
