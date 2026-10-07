"""tel-015 (DEC-SCOPE-114, spec §3): the merged lead timeline -- every EVID-019 §13 event kind with actor and time (AC1), kept across a
reassignment (AC2), in a stable order for equal timestamps (AC3), read through the telecaller, counselor and admin routes (TM1). The
shared test database is never truncated: every assertion is about leads the test made."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import AuditLog, Enquiry, LeadCall
from tests.tel004_helpers import make_telecaller, make_tl_manager, make_user
from tests.tel016_helpers import as_user, body, book_url, make_counselor
from tests.tel018_helpers import c_url, enrol, handover_url, make_student

LEADS = "/api/v1/telecaller/leads"
ASSIGN = f"{LEADS}/assign"


def t_url(lead_id, **params) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{LEADS}/{lead_id}/timeline" + (f"?{query}" if query else "")


def admin_url(lead_id) -> str:
    return f"/api/v1/admin/leads/{lead_id}/timeline"


async def new_lead(db, *, division: str = "it", telecaller=None, status: str = "new", **over) -> Enquiry:
    row = Enquiry(**({"division": division, "name": f"Lead {uuid.uuid4().hex[:6]}", "email": f"{uuid.uuid4().hex[:8]}@example.local",
                      "phone": "9876543210", "subject": "Cyber Security", "message": "Call me", "source": "walk_in", "status": status,
                      "telecaller_user_id": telecaller.id if telecaller else None} | over))
    db.add(row)
    await db.commit()
    return row


async def team(db):
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager), await make_telecaller(db, manager)


async def items(client, url: str) -> list[dict]:
    response = await client.get(url)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def assign(client, manager, row, telecaller) -> None:
    await as_user(client, manager)
    response = await client.post(ASSIGN, json={"lead_ids": [str(row.id)], "telecaller_user_id": str(telecaller.id)})
    assert response.status_code == 200, response.text


async def call(client, row, outcome: str = "interested", **over) -> None:
    response = await client.post(f"{LEADS}/{row.id}/calls", json={"duration_seconds": 125, "call_type": "outgoing", "outcome": outcome} | over)
    assert response.status_code == 201, response.text


async def whatsapp(client, row, text: str = "Hello from EduSphere") -> None:
    response = await client.post(f"{LEADS}/{row.id}/messages", json={"channel": "whatsapp", "body": text})
    assert response.status_code == 201, response.text


# --- AC1: the full §13 chain ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_full_chain_every_kind_has_actor_and_time(client, db_session):
    manager, tel, _ = await team(db_session)
    counselor = await make_counselor(db_session)
    row = await new_lead(db_session)
    db_session.add(AuditLog(user_id=manager.id, action="lead.create", entity_type="enquiry", entity_id=str(row.id),
                            metadata_json={"source": "walk_in", "assigned": False}))
    await db_session.commit()

    await assign(client, manager, row, tel)
    await as_user(client, tel)
    await call(client, row, remarks="Keen on the weekend batch")
    await whatsapp(client, row)
    due = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    assert (await client.post(f"{LEADS}/{row.id}/follow-ups", json={"due_at": due, "reason": "fee_details", "notes": "Send fees"})).status_code == 201
    assert (await client.post(book_url(row.id), json=body(counselor))).status_code == 201
    await as_user(client, manager)
    assert (await client.post(handover_url(row.id), json={"counselor_id": str(counselor.id)})).status_code == 200
    student = await make_student(db_session)
    await enrol(db_session, student)
    await as_user(client, counselor)
    response = await client.post(c_url(row.id, "/student-link"), json={"student_id": str(student.id)})
    assert response.status_code == 200, response.text

    await as_user(client, tel)
    rows = await items(client, t_url(row.id, limit=100))
    kinds = {r["kind"] for r in rows}
    assert {"created", "assignment", "stage", "call", "message", "follow_up", "appointment", "handover", "student_link", "milestone"} <= kinds
    assert all(r["at"] for r in rows)
    by_kind = {r["kind"]: r for r in rows}  # newest first, so the oldest of each kind wins
    assert by_kind["created"]["actor"]["id"] == str(manager.id) and by_kind["created"]["from_value"] == "walk_in"
    assert (by_kind["assignment"]["to_value"], by_kind["assignment"]["to_label"], by_kind["assignment"]["event"]) == (str(tel.id), tel.full_name, "manual")
    assert by_kind["assignment"]["actor"]["id"] == str(manager.id)
    c = by_kind["call"]
    assert (c["from_value"], c["to_value"], c["duration_seconds"], c["reason"], c["actor"]["id"]) == (
        "outgoing", "interested", 125, "Keen on the weekend batch", str(tel.id))
    m = by_kind["message"]
    assert (m["from_value"], m["to_value"], m["reason"], m["actor"]["id"]) == ("whatsapp", "", "Hello from EduSphere", str(tel.id))
    f = by_kind["follow_up"]
    assert (f["event"], f["from_value"], f["reason"], f["actor"]["id"]) == ("scheduled", "fee_details", "Send fees", str(tel.id))
    assert f["scheduled_for"] is not None
    cancelled = next(r for r in rows if r["kind"] == "follow_up" and r["event"] == "cancelled")  # tel-018: the handover cancels it
    assert (cancelled["actor"], cancelled["reason"]) == (None, "Handed over to counselor")
    a = by_kind["appointment"]
    assert (a["from_value"], a["to_value"], a["event"], a["actor"]["id"]) == ("", "scheduled", "it_course_counselling", str(tel.id))
    assert a["subject"].startswith("CAP-") and a["scheduled_for"] is not None
    h = by_kind["handover"]
    assert (h["to_value"], h["to_label"], h["actor"]["id"]) == (str(counselor.id), counselor.full_name, str(manager.id))
    s = by_kind["student_link"]
    assert (s["event"], s["to_value"], s["to_label"], s["actor"]["id"]) == ("linked", str(student.id), student.full_name, str(counselor.id))
    ms = by_kind["milestone"]
    assert (ms["event"], ms["status"], ms["actor"]) == ("enrollment", "active", None)
    assert any(r["kind"] == "stage" and r["event"] == "converted" for r in rows)  # T29: an enrolled student converts at once

    # the counselor and the admin read the same timeline
    await as_user(client, counselor)
    assert [r["id"] for r in await items(client, c_url(row.id, "/timeline?limit=100"))] == [r["id"] for r in rows]
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert [r["id"] for r in await items(client, f"{admin_url(row.id)}?limit=100")] == [r["id"] for r in rows]


# --- AC2: reassignment keeps the history ----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reassigned_lead_keeps_previous_telecallers_events(client, db_session):
    manager, a, b = await team(db_session)
    row = await new_lead(db_session, telecaller=a, status="assigned")
    await as_user(client, a)
    await call(client, row, outcome="busy")
    await whatsapp(client, row)
    await assign(client, manager, row, b)

    await as_user(client, a)
    assert (await client.get(t_url(row.id))).status_code == 404
    await as_user(client, b)
    rows = await items(client, t_url(row.id))
    assert {(r["kind"], r["actor"]["id"]) for r in rows if r["kind"] in ("call", "message")} == {("call", str(a.id)), ("message", str(a.id))}
    move = next(r for r in rows if r["kind"] == "assignment")
    assert (move["from_value"], move["from_label"], move["to_value"], move["to_label"]) == (str(a.id), a.full_name, str(b.id), b.full_name)


# --- AC3: stable order --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_equal_timestamps_order_is_stable_and_causal(client, db_session):
    manager, tel, _ = await team(db_session)
    row = await new_lead(db_session)
    await assign(client, manager, row, tel)  # one transaction: the assignment audit and the stage move share `at`
    first = await items(client, t_url(row.id))
    assert [r["kind"] for r in first] == ["stage", "assignment", "created"]  # the move above its cause; the creation last
    assert first[0]["at"] == first[1]["at"]
    assert [r["id"] for r in await items(client, t_url(row.id))] == [r["id"] for r in first]
    paged = [r["id"] for offset in range(3) for r in await items(client, t_url(row.id, limit=1, offset=offset))]
    assert paged == [r["id"] for r in first]


# --- edge cases ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_system_events_have_no_actor(client, db_session):
    manager, tel, _ = await team(db_session)
    row = await new_lead(db_session, telecaller=tel, status="assigned", source="website")
    db_session.add(AuditLog(user_id=None, action="lead.assign", entity_type="enquiry", entity_id=str(row.id),
                            metadata_json={"from": None, "to": str(tel.id), "method": "round_robin"}))
    await db_session.commit()
    await as_user(client, manager)
    rows = await items(client, t_url(row.id))
    assert [(r["kind"], r["actor"], r["event"]) for r in rows if r["kind"] in ("assignment", "created")] == [
        ("assignment", None, "round_robin"), ("created", None, None)]


@pytest.mark.asyncio
async def test_an_unassignment_has_an_empty_target(client, db_session):
    manager, tel, _ = await team(db_session)
    row = await new_lead(db_session)
    db_session.add(AuditLog(user_id=manager.id, action="lead.assign", entity_type="enquiry", entity_id=str(row.id),
                            metadata_json={"from": str(tel.id), "to": None, "method": "deactivation"}))
    await db_session.commit()
    await as_user(client, manager)
    move = next(r for r in await items(client, t_url(row.id)) if r["kind"] == "assignment")
    assert (move["from_label"], move["to_value"], move["to_label"]) == (tel.full_name, "", "")


@pytest.mark.asyncio
async def test_excerpts_are_capped_at_200(client, db_session):
    _, tel, _ = await team(db_session)
    row = await new_lead(db_session, telecaller=tel, status="assigned")
    await as_user(client, tel)
    await whatsapp(client, row, "w" * 900)
    await call(client, row, outcome="busy", remarks="r" * 600)
    rows = await items(client, t_url(row.id))
    assert {r["kind"]: len(r["reason"]) for r in rows if r["kind"] in ("call", "message")} == {"call": 200, "message": 200}


@pytest.mark.asyncio
async def test_a_call_is_placed_at_when_it_happened(client, db_session):
    _, tel, _ = await team(db_session)
    row = await new_lead(db_session, telecaller=tel, status="contacted")
    earlier = datetime.now(UTC) - timedelta(days=3)
    db_session.add(LeadCall(lead_id=row.id, caller_user_id=tel.id, occurred_at=earlier, duration_seconds=30, call_type="incoming",
                            outcome="busy", remarks=None))
    await db_session.commit()
    await as_user(client, tel)
    rows = await items(client, t_url(row.id))
    assert [r["kind"] for r in rows] == ["created", "call"]  # the call is older than the lead row written just now
    assert rows[1]["reason"] is None and rows[1]["from_value"] == "incoming"


@pytest.mark.asyncio
async def test_follow_up_done_and_cancelled_are_entries(client, db_session):
    _, tel, _ = await team(db_session)
    row = await new_lead(db_session, telecaller=tel, status="contacted")
    await as_user(client, tel)
    due = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    ids = []
    for reason in ("fee_details", "course_details"):
        response = await client.post(f"{LEADS}/{row.id}/follow-ups", json={"due_at": due, "reason": reason})
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    assert (await client.post(f"/api/v1/telecaller/follow-ups/{ids[0]}/complete")).status_code == 200
    assert (await client.post(f"/api/v1/telecaller/follow-ups/{ids[1]}/cancel", json={"reason": "Lead asked to stop"})).status_code == 200
    events = {(r["event"], r["from_value"]): r for r in await items(client, t_url(row.id)) if r["kind"] == "follow_up"}
    assert set(events) == {("scheduled", "fee_details"), ("scheduled", "course_details"), ("done", "fee_details"), ("cancelled", "course_details")}
    assert events[("done", "fee_details")]["actor"]["id"] == str(tel.id)
    cancelled = events[("cancelled", "course_details")]
    assert (cancelled["actor"]["id"], cancelled["reason"]) == (str(tel.id), "Lead asked to stop")


@pytest.mark.asyncio
async def test_unlink_removes_milestones(client, db_session):
    manager, tel, _ = await team(db_session)
    counselor = await make_counselor(db_session)
    row = await new_lead(db_session, telecaller=tel, status="counselling_completed", owner_id=counselor.id)
    student = await make_student(db_session)
    await enrol(db_session, student, status="pending_consent")  # not yet a conversion: the counselor may unlink
    await as_user(client, counselor)
    assert (await client.post(c_url(row.id, "/student-link"), json={"student_id": str(student.id)})).status_code == 200
    assert any(r["kind"] == "milestone" for r in await items(client, c_url(row.id, "/timeline")))
    assert (await client.delete(c_url(row.id, "/student-link"))).status_code == 200
    await as_user(client, manager)
    rows = await items(client, t_url(row.id))
    assert not any(r["kind"] == "milestone" for r in rows)
    assert [r["event"] for r in rows if r["kind"] == "student_link"] == ["unlinked", "linked"]


# --- scope ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scope(client, db_session):
    _, tel, other = await team(db_session)
    row = await new_lead(db_session, telecaller=tel, status="assigned")
    overseas = await new_lead(db_session, division="overseas")
    await as_user(client, other)
    assert (await client.get(t_url(row.id))).status_code == 404
    await as_user(client, await make_counselor(db_session))
    assert (await client.get(c_url(row.id, "/timeline"))).status_code == 404
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(admin_url(row.id))).status_code == 200
    assert (await client.get(admin_url(overseas.id))).status_code == 403
    assert (await client.get(admin_url(uuid.uuid4()))).status_code == 404
    assert (await client.get(f"{admin_url(row.id)}?limit=101")).status_code == 422
    await as_user(client, tel)
    assert (await client.get(admin_url(row.id))).status_code == 403
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    assert (await client.get(admin_url(overseas.id))).status_code == 200
