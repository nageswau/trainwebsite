import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from enh005_helpers import login, mk_request, mk_school, mk_student
from sqlalchemy import func, select, update

from app.api import school_transfers
from app.models import AuditLog, SchoolStudentTransferRequest

# ENH-005 spec §5.2 (filing), D7 (cap), D8 (throttle), security review S3 (probing). Real Postgres.

OUT = "/api/v1/school/students/{sid}/transfer-requests"
IN = "/api/v1/school/transfer-requests/incoming"
NOT_AT_INSTITUTION = "This student is not at your institution"
ALREADY_PENDING = "A transfer request is already pending for this student"
FILED, DENIED = "school.transfer_request_filed", "school.transfer_request_denied"
UNKNOWN_CODE = "00000000"  # well-formed, but no student has it (codes are random 8-hex; this one is never generated in tests)


async def _rows(db, **where):
    stmt = select(SchoolStudentTransferRequest)
    for column, value in where.items():
        stmt = stmt.where(getattr(SchoolStudentTransferRequest, column) == value)
    return list((await db.scalars(stmt)).all())


async def _audits(db, user, *actions):
    stmt = select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action.in_(actions or (FILED, DENIED))).order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())


@pytest_asyncio.fixture
async def two(db_session):
    a = await mk_school(db_session, label="A")
    b = await mk_school(db_session, label="B")
    return a, b


# ------------------------------------------------------------------------------------------ outgoing


@pytest.mark.asyncio
async def test_outgoing_creates_a_pending_row_with_server_derived_fields(client, db_session, two):
    a, b = two
    student = a["students"][0]
    await login(client, a["coordinator"].email)

    response = await client.post(OUT.format(sid=student.id), json={"to_school_id": str(b["school"].id), "reason": "Family is moving"})

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["direction"], body["status"], body["reason"]) == ("outgoing", "pending", "Family is moving")
    assert (body["student_id"], body["student_name"], body["student_code"]) == (str(student.id), student.full_name, student.student_code)
    assert body["from_school"] == {"id": str(a["school"].id), "name": a["school"].name}
    assert body["to_school"] == {"id": str(b["school"].id), "name": b["school"].name}
    (row,) = await _rows(db_session, school_student_id=student.id)
    assert (row.from_school_id, row.to_school_id, row.filed_by_school_id, row.requested_by_user_id, row.status) == (a["school"].id, b["school"].id, a["school"].id, a["coordinator"].id, "pending")
    (audit,) = await _audits(db_session, a["coordinator"])
    assert (audit.action, audit.outcome, audit.entity_id) == (FILED, "recorded", str(row.id))


@pytest.mark.asyncio
async def test_outgoing_for_a_foreign_or_unknown_student_is_the_identical_403_and_audited(client, db_session, two):
    a, b = two
    await login(client, a["coordinator"].email)
    body = {"to_school_id": str(b["school"].id)}

    foreign = await client.post(OUT.format(sid=b["students"][0].id), json=body)
    unknown = await client.post(OUT.format(sid=uuid.uuid4()), json=body)

    assert (foreign.status_code, foreign.json()) == (unknown.status_code, unknown.json()) == (403, {"detail": NOT_AT_INSTITUTION})
    audits = await _audits(db_session, a["coordinator"])
    assert [(x.action, x.outcome) for x in audits] == [(DENIED, "denied")] * 2
    assert await _rows(db_session, school_student_id=b["students"][0].id) == []


@pytest.mark.asyncio
async def test_outgoing_rejects_a_bad_destination_and_client_supplied_server_fields(client, db_session, two):
    a, b = two
    student = a["students"][0]
    await login(client, a["coordinator"].email)
    url = OUT.format(sid=student.id)

    assert (await client.post(url, json={"to_school_id": str(a["school"].id)})).status_code == 422  # same school
    assert (await client.post(url, json={"to_school_id": str(uuid.uuid4())})).status_code == 422  # unknown school
    assert (await client.post(url, json={"to_school_id": "nope"})).status_code == 422
    for extra in ("from_school_id", "filed_by_school_id", "status", "school_id", "student_id"):
        response = await client.post(url, json={"to_school_id": str(b["school"].id), extra: str(uuid.uuid4())})
        assert response.status_code == 422, (extra, response.text)
    assert (await client.post(OUT.format(sid="not-a-uuid"), json={"to_school_id": str(b["school"].id)})).status_code == 422
    assert await _rows(db_session, school_student_id=student.id) == []


@pytest.mark.asyncio
async def test_a_second_pending_request_for_the_same_student_is_409_and_index_backed(client, db_session, two):
    a, b = two
    student = a["students"][0]
    await login(client, a["coordinator"].email)
    body = {"to_school_id": str(b["school"].id)}

    assert (await client.post(OUT.format(sid=student.id), json=body)).status_code == 201
    second = await client.post(OUT.format(sid=student.id), json=body)

    assert (second.status_code, second.json()) == (409, {"detail": ALREADY_PENDING})
    assert len(await _rows(db_session, school_student_id=student.id)) == 1
    assert [x.outcome for x in await _audits(db_session, a["coordinator"])] == ["recorded", "denied"]


@pytest.mark.asyncio
async def test_only_a_school_coordinator_can_file_and_a_stranger_gets_401(client, db_session, two):
    a, b = two
    url, body = OUT.format(sid=a["students"][0].id), {"to_school_id": str(b["school"].id)}
    assert (await client.post(url, json=body)).status_code == 401
    for who in (a["principal"], a["teacher"], a["parent"], a["admin"]):
        await login(client, who.email)
        assert (await client.post(url, json=body)).status_code == 403, who.role
        assert (await client.post(IN, json={"student_code": UNKNOWN_CODE})).status_code == 403, who.role
    assert await _rows(db_session, school_student_id=a["students"][0].id) == []


# ------------------------------------------------------------------------------------------ incoming


@pytest.mark.asyncio
async def test_incoming_is_the_identical_202_for_every_well_formed_code(client, db_session, two):
    a, b = two
    await login(client, a["coordinator"].email)
    valid = b["students"][0]
    own = a["students"][0]

    replies = [
        await client.post(IN, json={"student_code": valid.student_code}),  # a real student at another school
        await client.post(IN, json={"student_code": UNKNOWN_CODE}),  # nobody
        await client.post(IN, json={"student_code": own.student_code.lower()}),  # our own student, lower-case
        await client.post(IN, json={"student_code": valid.student_code}),  # a duplicate of the first
    ]

    assert {(r.status_code, json.dumps(r.json())) for r in replies} == {(202, json.dumps({"accepted": True}))}
    assert len(await _rows(db_session, school_student_id=valid.id)) == 1  # created once, only for the valid student
    assert await _rows(db_session, school_student_id=own.id) == []
    (row,) = await _rows(db_session, school_student_id=valid.id)
    assert (row.from_school_id, row.to_school_id, row.filed_by_school_id) == (b["school"].id, a["school"].id, a["school"].id)
    audits = await _audits(db_session, a["coordinator"])
    assert [x.outcome for x in audits] == ["recorded", "denied", "denied", "denied"]
    assert {x.metadata_json.get("reason_token") for x in audits if x.outcome == "denied"} == {"unknown_code", "own_school", "duplicate"}


@pytest.mark.asyncio
async def test_incoming_rejects_a_malformed_code_and_client_supplied_fields_with_422(client, db_session, two):
    a, _ = two
    await login(client, a["coordinator"].email)
    for bad in ("XYZ", "A3F9C21", "G3F9C21B", "", "٣٣٣٣٣٣٣٣"):
        assert (await client.post(IN, json={"student_code": bad})).status_code == 422, bad
    assert (await client.post(IN, json={"student_code": UNKNOWN_CODE, "school_id": str(uuid.uuid4())})).status_code == 422
    assert await _audits(db_session, a["coordinator"]) == []  # a 422 is not an attempt


# ------------------------------------------------------------------------------------------ audit hygiene


@pytest.mark.asyncio
async def test_audit_rows_never_hold_the_code_the_reason_or_a_name(client, db_session, two):
    a, b = two
    student = b["students"][0]
    await login(client, a["coordinator"].email)
    secret_reason = "SECRET-REASON-TEXT"
    await client.post(IN, json={"student_code": student.student_code, "reason": secret_reason})
    await client.post(IN, json={"student_code": UNKNOWN_CODE, "reason": secret_reason})
    await client.post(OUT.format(sid=a["students"][0].id), json={"to_school_id": str(b["school"].id), "reason": secret_reason})

    blob = json.dumps([x.metadata_json for x in await _audits(db_session, a["coordinator"])])
    for forbidden in (secret_reason, student.student_code, UNKNOWN_CODE, student.full_name, a["students"][0].full_name):
        assert forbidden not in blob
    assert "request_id" in blob


# ------------------------------------------------------------------------------------------ cap (D7) and throttle (D8)


@pytest.mark.asyncio
async def test_the_open_request_cap_is_409_before_any_lookup_and_a_freed_slot_restores_filing(client, db_session, two, monkeypatch):
    a, b = two
    monkeypatch.setattr(school_transfers, "MAX_OPEN_TRANSFER_REQUESTS_PER_SCHOOL", 2)
    kids = [await mk_student(db_session, a["school"], a["coordinator"], f"cap{i}") for i in range(3)]
    await db_session.commit()
    held = [await mk_request(db_session, k, from_school=a["school"], to_school=b["school"], filed_by_school=a["school"], requester=a["coordinator"]) for k in kids[:2]]
    await login(client, a["coordinator"].email)
    too_many = {"detail": "Too many open transfer requests; wait for a decision or cancel one"}

    outgoing = await client.post(OUT.format(sid=kids[2].id), json={"to_school_id": str(b["school"].id)})
    incoming = await client.post(IN, json={"student_code": UNKNOWN_CODE})

    assert (outgoing.status_code, outgoing.json()) == (409, too_many)
    assert (incoming.status_code, incoming.json()) == (409, too_many)  # the cap answers before the code is even looked up
    # AC-27 (Codex review): a refused attempt is an attempt, so each cap refusal writes its own `denied` row, with a token and IDs only.
    refusals = [x for x in await _audits(db_session, a["coordinator"], DENIED) if x.metadata_json.get("reason_token") == "cap_reached"]
    assert len(refusals) == 2 and {x.outcome for x in refusals} == {"denied"}
    assert all(x.metadata_json["school_id"] == str(a["school"].id) for x in refusals)
    blob = json.dumps([x.metadata_json for x in refusals])
    assert UNKNOWN_CODE not in blob and kids[2].student_code not in blob  # never the code that was typed
    await db_session.execute(update(SchoolStudentTransferRequest).where(SchoolStudentTransferRequest.id == held[0].id).values(status="cancelled"))
    await db_session.commit()
    assert (await client.post(OUT.format(sid=kids[2].id), json={"to_school_id": str(b["school"].id)})).status_code == 201


@pytest.mark.asyncio
async def test_the_hourly_filing_throttle_counts_every_attempt_and_lapses(client, db_session, two, monkeypatch):
    a, b = two
    monkeypatch.setattr(school_transfers, "TRANSFER_FILINGS_PER_HOUR", 3)
    await login(client, a["coordinator"].email)
    for i in range(3):
        assert (await client.post(IN, json={"student_code": f"0000000{i}"})).status_code == 202

    blocked = await client.post(IN, json={"student_code": "00000009"})
    blocked_out = await client.post(OUT.format(sid=a["students"][0].id), json={"to_school_id": str(b["school"].id)})

    assert blocked.status_code == blocked_out.status_code == 429
    assert blocked.json()["detail"].startswith("Too many transfer requests; try again in ")
    assert 1 <= int(blocked.headers["Retry-After"]) <= 3600
    # The throttle's 429 is logged, not audited (spec §8): the throttle counts these rows, so auditing its own refusals would feed it.
    assert len(await _audits(db_session, a["coordinator"])) == 3
    assert (await client.post(IN, json={"student_code": "nope"})).status_code == 422  # validation still comes first
    await login(client, b["coordinator"].email)
    assert (await client.post(IN, json={"student_code": UNKNOWN_CODE})).status_code == 202  # another coordinator is unaffected
    await db_session.execute(update(AuditLog).where(AuditLog.user_id == a["coordinator"].id).values(created_at=datetime.now(UTC) - timedelta(hours=2)))
    await db_session.commit()
    await login(client, a["coordinator"].email)
    assert (await client.post(IN, json={"student_code": "00000009"})).status_code == 202  # the window has lapsed
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id == a["coordinator"].id, AuditLog.action == "school.transfer_throttle")) == 0
