import pytest
import pytest_asyncio
from enh005_helpers import login, mk_request, mk_result, mk_school, mk_staff, mk_student
from sqlalchemy import event, select, update

from app.core.database import engine
from app.models import AuditLog, Notification, SchoolStudent, SchoolStudentTransferRequest

# ENH-005 spec §5.3: reject, the admin queue with its preview, and the admin history. Real Postgres.

LIST = "/api/v1/overseas-admin/school-transfer-requests"
REJECT = "/api/v1/overseas-admin/school-transfer-requests/{rid}/reject"
HISTORY = "/api/v1/overseas-admin/school-students/{sid}/transfer-history"
DECIDED = "This transfer request has already been decided"


@pytest_asyncio.fixture
async def world(db_session):
    a = await mk_school(db_session, label="A", students=2)
    b = await mk_school(db_session, label="B", students=0)
    c = await mk_school(db_session, label="C", students=0)
    outgoing = await mk_request(db_session, a["students"][0], from_school=a["school"], to_school=b["school"], filed_by_school=a["school"], requester=a["coordinator"], reason="Family is moving")
    incoming = await mk_request(db_session, a["students"][1], from_school=a["school"], to_school=c["school"], filed_by_school=c["school"], requester=c["coordinator"])
    return {"a": a, "b": b, "c": c, "outgoing": outgoing, "incoming": incoming, "admin": a["admin"]}


async def _rejected_by(client, w, request, note=None):
    await login(client, w["admin"].email)
    return await client.post(REJECT.format(rid=request.id), json={} if note is None else {"note": note})


async def _titles(db, user):
    return [(n.title, n.body) for n in (await db.scalars(select(Notification).where(Notification.user_id == user.id))).all()]


# ------------------------------------------------------------------------------------------ reject


@pytest.mark.asyncio
async def test_reject_changes_only_the_request_and_records_the_note(client, db_session, world):
    w = world
    student = w["a"]["students"][0]
    response = await _rejected_by(client, w, w["outgoing"], "Please resubmit after term ends")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["decision_note"], body["decided_by"]["id"]) == ("rejected", "Please resubmit after term ends", str(w["admin"].id))
    row = await db_session.get(SchoolStudentTransferRequest, w["outgoing"].id, populate_existing=True)
    assert (row.status, row.decided_by_user_id is not None, row.decided_at is not None, row.outcome) == ("rejected", True, True, None)
    kid = await db_session.get(SchoolStudent, student.id, populate_existing=True)
    assert (kid.school_id, kid.assigned_teacher_user_id) == (w["a"]["school"].id, w["a"]["teacher"].id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.transfer_request_rejected", AuditLog.entity_id == str(w["outgoing"].id)))
    assert audit is not None and "Please resubmit" not in str(audit.metadata_json)  # the note is never copied into audit
    await login(client, w["a"]["coordinator"].email)  # the filing coordinator can read the decision
    (mine,) = (await client.get("/api/v1/school/transfer-requests", params={"status": "rejected"})).json()["items"]
    assert mine["decision_note"] == "Please resubmit after term ends"


@pytest.mark.asyncio
async def test_reject_accepts_an_empty_body_and_validates_the_note(client, db_session, world):
    w = world
    await login(client, w["admin"].email)
    assert (await client.post(REJECT.format(rid=w["outgoing"].id))).status_code == 200  # no body at all
    for bad in ({"note": "a\u202eb"}, {"note": "x" * 501}, {"note": "ok", "status": "approved"}, {"school_id": "x"}):
        response = await client.post(REJECT.format(rid=w["incoming"].id), json=bad)
        assert response.status_code == 422, bad
    row = await db_session.get(SchoolStudentTransferRequest, w["incoming"].id, populate_existing=True)
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_reject_is_admin_only_and_refuses_decided_or_unknown_requests(client, db_session, world):
    w = world
    for who in (w["a"]["coordinator"], w["c"]["coordinator"], w["a"]["parent"]):
        await login(client, who.email)
        assert (await client.post(REJECT.format(rid=w["incoming"].id), json={})).status_code == 403
    client.cookies.clear()
    assert (await client.post(REJECT.format(rid=w["incoming"].id), json={})).status_code == 401
    assert (await _rejected_by(client, w, w["incoming"])).status_code == 200
    again = await client.post(REJECT.format(rid=w["incoming"].id), json={})
    assert (again.status_code, again.json()) == (409, {"detail": DECIDED})
    assert (await client.post(REJECT.format(rid="00000000-0000-0000-0000-000000000000"), json={})).status_code == 404


@pytest.mark.asyncio
async def test_the_rejection_notice_to_an_incoming_requester_carries_only_the_student_code(client, db_session, world):
    w = world
    await _rejected_by(client, w, w["incoming"])  # filed by school C for a student of A
    await _rejected_by(client, w, w["outgoing"])  # filed by school A for its own student

    (incoming_notice,) = await _titles(db_session, w["c"]["coordinator"])
    text = " ".join(incoming_notice)
    assert w["a"]["students"][1].student_code in text
    assert w["a"]["students"][1].full_name not in text and w["a"]["school"].name not in text
    (outgoing_notice,) = await _titles(db_session, w["a"]["coordinator"])
    assert w["a"]["students"][0].full_name in " ".join(outgoing_notice)


# ------------------------------------------------------------------------------------------ admin list


@pytest.mark.asyncio
async def test_the_admin_queue_is_complete_and_carries_the_preview_counts(client, db_session, world):
    w = world
    kid = w["a"]["students"][0]
    staff = await mk_staff(db_session, w["a"]["school"], w["admin"])
    await mk_result(db_session, kid, staff, "draft", "d")
    await mk_result(db_session, kid, staff, "verified", "v")
    await mk_result(db_session, kid, staff, "published", "p")
    await mk_staff(db_session, w["b"]["school"], w["admin"])  # B has a service-delivery portfolio; C does not
    await login(client, w["admin"].email)

    response = await client.get(LIST, params={"limit": 100})  # the queue is global and the test database is shared: find our own rows

    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] >= 2 and (page["limit"], page["offset"]) == (100, 0)
    by_id = {row["id"]: row for row in page["items"]}
    out, inc = by_id[str(w["outgoing"].id)], by_id[str(w["incoming"].id)]
    assert (out["direction"], inc["direction"]) == ("outgoing", "incoming")
    assert (out["student_name"], out["student_code"], out["reason"]) == (kid.full_name, kid.student_code, "Family is moving")
    assert out["requester"]["id"] == str(w["a"]["coordinator"].id) and out["filed_by_school"]["id"] == str(w["a"]["school"].id)
    assert out["preview"] == {"linked_parents": 1, "in_flight_results": 2, "to_school_has_portfolio_staff": True, "pending_parent_invite": False}
    assert inc["student_name"] == w["a"]["students"][1].full_name  # the admin's view is never redacted
    assert inc["preview"] == {"linked_parents": 0, "in_flight_results": 0, "to_school_has_portfolio_staff": False, "pending_parent_invite": False}
    assert inc["filed_by_school"]["id"] == str(w["c"]["school"].id)


@pytest.mark.asyncio
async def test_the_preview_flags_a_parent_invite_that_approval_would_clear(client, db_session, world):
    """Approval clears `pending_parent_email` (the invite belongs to the losing school), so a parent who has not accepted yet ends up with no
    linked child. The admin has to see that BEFORE deciding (DEC-SCOPE-021 open item), and only for a student that has such an invite."""
    w = world
    invited = w["a"]["students"][0]
    await db_session.execute(update(SchoolStudent).where(SchoolStudent.id == invited.id).values(pending_parent_email="not-yet-accepted@example.local"))
    await db_session.commit()
    await login(client, w["admin"].email)

    by_id = {row["id"]: row for row in (await client.get(LIST, params={"limit": 100})).json()["items"]}

    assert by_id[str(w["outgoing"].id)]["preview"]["pending_parent_invite"] is True
    assert by_id[str(w["incoming"].id)]["preview"]["pending_parent_invite"] is False
    assert "not-yet-accepted@example.local" not in (await client.get(LIST, params={"limit": 100})).text  # a boolean: the address is never sent


@pytest.mark.asyncio
async def test_the_admin_queue_filters_by_status_and_paginates_newest_first(client, db_session, world):
    w = world
    await db_session.execute(update(SchoolStudentTransferRequest).where(SchoolStudentTransferRequest.id == w["incoming"].id).values(status="cancelled"))
    await db_session.commit()
    await login(client, w["admin"].email)

    pending_ids = [r["id"] for r in (await client.get(LIST, params={"limit": 100})).json()["items"]]  # pending is the default
    assert str(w["outgoing"].id) in pending_ids and str(w["incoming"].id) not in pending_ids
    cancelled = (await client.get(LIST, params={"status": "cancelled", "limit": 100})).json()["items"]
    assert str(w["incoming"].id) in [r["id"] for r in cancelled] and {r["status"] for r in cancelled} == {"cancelled"}
    newest = (await client.get(LIST, params={"status": "all", "limit": 1})).json()
    assert (newest["total"] >= 2, len(newest["items"]), newest["items"][0]["id"]) == (True, 1, str(w["incoming"].id))  # newest first
    assert (await client.get(LIST, params={"status": "bogus"})).status_code == 422
    for bad in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert (await client.get(LIST, params=bad)).status_code == 422, bad
    for who in (w["a"]["coordinator"], w["a"]["parent"]):
        await login(client, who.email)
        assert (await client.get(LIST)).status_code == 403


@pytest.mark.asyncio
async def test_the_preview_costs_a_constant_number_of_queries_however_many_rows(client, db_session, world):
    w = world
    await login(client, w["admin"].email)

    async def statements_for_list() -> int:
        seen = []
        listener = lambda conn, cursor, statement, *a: seen.append(statement)  # noqa: E731
        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            assert (await client.get(LIST, params={"limit": 100})).status_code == 200
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        return len(seen)

    two_rows = await statements_for_list()
    for i in range(6):
        kid = await mk_student(db_session, w["a"]["school"], w["a"]["coordinator"], f"extra{i}")
        await db_session.commit()
        await mk_request(db_session, kid, from_school=w["a"]["school"], to_school=w["b"]["school"], filed_by_school=w["a"]["school"], requester=w["a"]["coordinator"])
    eight_rows = await statements_for_list()
    assert eight_rows == two_rows


# ------------------------------------------------------------------------------------------ admin history


@pytest.mark.asyncio
async def test_the_admin_history_lists_every_status_with_names(client, db_session, world):
    w = world
    kid = w["a"]["students"][0]
    await mk_request(db_session, kid, from_school=w["a"]["school"], to_school=w["c"]["school"], filed_by_school=w["c"]["school"], requester=w["c"]["coordinator"], status="rejected")
    await login(client, w["admin"].email)

    response = await client.get(HISTORY.format(sid=kid.id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["student"] == {"id": str(kid.id), "full_name": kid.full_name}
    assert sorted(r["status"] for r in body["history"]) == ["pending", "rejected"]
    assert all(r["requester"]["name"] and r["from_school"]["name"] for r in body["history"])
    assert (await client.get(HISTORY.format(sid="00000000-0000-0000-0000-000000000000"))).status_code == 404
    await login(client, w["a"]["coordinator"].email)
    assert (await client.get(HISTORY.format(sid=kid.id))).status_code == 403
