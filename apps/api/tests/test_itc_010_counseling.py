"""itc-010 (DEC-SCOPE-343): the IT counseling record -- one row per session on a lead handed to an IT counselor (C1), read by the
telecaller side (C8), with the objections catalogue (C6). The shared test database is never truncated: every assertion is about rows the
test made."""

import logging
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models import AuditLog, LeadCounselingObjection, LeadCounselingRecord
from tests.tel004_helpers import make_user
from tests.tel007_helpers import product
from tests.tel018_helpers import as_user, c_url, handover, setup
from tests.test_ccrm_004_counselor_activities import close, handed

NOTES = "Parent will pay secret-counsel-notes-71"
OBJECTION_TEXT = "Wants weekend batch secret-objection-42"
OBJECTIONS = "/api/v1/telecaller/counseling-objections"


def day(offset: int) -> str:
    return (datetime.now(ZoneInfo("Asia/Kolkata")).date() + timedelta(days=offset)).isoformat()


async def objection(db, *, active: bool = True) -> LeadCounselingObjection:
    row = LeadCounselingObjection(name=f"Objection {uuid.uuid4().hex[:8]}", active=active, sort_order=5000)
    db.add(row)
    await db.commit()
    return row


async def full_body(db, **over) -> dict:
    course, worry = await product(db), await objection(db)
    return {
        "recommended_product_id": str(course.id),
        "objection_ids": [str(worry.id)],
        "objection_notes": OBJECTION_TEXT,
        "fee_quoted": "45000.00",
        "expected_joining_date": day(10),
        "decision_maker": "parent",
        "outcome": "interested",
        "next_follow_up": day(3),
        "notes": NOTES,
    } | over


def t_url(lead_id, tail: str = "") -> str:
    return f"/api/v1/telecaller/leads/{lead_id}{tail}"


def field_error(response, field: str) -> bool:
    return response.status_code == 422 and any(e["loc"][-1] == field for e in response.json()["detail"])


# --- AC1 / AC4: record, list, timeline ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_it_counselor_records_every_field_and_it_shows_in_list_and_timeline(client, db_session, caplog):
    _, _, counselor, row = await handed(client, db_session, "it")
    body = await full_body(db_session)
    with caplog.at_level(logging.INFO):
        response = await client.post(c_url(row.id, "/counseling"), json=body)
    assert response.status_code == 201, response.text
    out = response.json()
    assert out["recommended_product"]["id"] == body["recommended_product_id"]
    assert [o["id"] for o in out["objections"]] == body["objection_ids"]
    assert (out["objection_notes"], out["fee_quoted"], out["expected_joining_date"], out["decision_maker"], out["outcome"], out["next_follow_up"], out["notes"]) == (
        OBJECTION_TEXT,
        "45000.00",
        body["expected_joining_date"],
        "parent",
        "interested",
        body["next_follow_up"],
        NOTES,
    )
    assert out["author"]["id"] == str(counselor.id)
    listed = (await client.get(c_url(row.id, "/counseling"))).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == out["id"]
    items = (await client.get(c_url(row.id, "/timeline"))).json()["items"]
    entry = next(i for i in items if i["kind"] == "counseling")
    assert entry["event"] == "created" and entry["to_value"] == "interested" and entry["actor"]["id"] == str(counselor.id)
    assert NOTES not in caplog.text and OBJECTION_TEXT not in caplog.text  # C11
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "lead_counseling.create", AuditLog.entity_id == str(row.id)))
    assert audit is not None and NOTES not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_only_the_outcome_is_required(client, db_session):
    _, _, _, row = await handed(client, db_session, "it")
    assert field_error(await client.post(c_url(row.id, "/counseling"), json={"notes": "x"}), "outcome")
    response = await client.post(c_url(row.id, "/counseling"), json={"outcome": "needs_time"})
    assert response.status_code == 201, response.text
    assert response.json()["objections"] == [] and response.json()["fee_quoted"] is None


# --- AC2 / AC3 / the "−" case: validation ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "value"), [("fee_quoted", "-1"), ("decision_maker", "uncle"), ("outcome", "maybe"), ("notes", "x" * 4001)])
async def test_bad_values_are_422(client, db_session, field, value):
    _, _, _, row = await handed(client, db_session, "it")
    assert field_error(await client.post(c_url(row.id, "/counseling"), json={"outcome": "interested", field: value}), field)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["expected_joining_date", "next_follow_up"])
async def test_a_date_before_today_is_422_and_today_is_fine(client, db_session, field):
    _, _, _, row = await handed(client, db_session, "it")
    assert field_error(await client.post(c_url(row.id, "/counseling"), json={"outcome": "interested", field: day(-1)}), field)
    assert (await client.post(c_url(row.id, "/counseling"), json={"outcome": "interested", field: day(0)})).status_code == 201


@pytest.mark.asyncio
async def test_an_overseas_or_inactive_product_is_422(client, db_session):
    _, _, _, row = await handed(client, db_session, "it")
    overseas, inactive = await product(db_session, group="overseas", team="overseas"), await product(db_session, active=False)
    for course in (overseas, inactive):
        response = await client.post(c_url(row.id, "/counseling"), json={"outcome": "interested", "recommended_product_id": str(course.id)})
        assert field_error(response, "recommended_product_id")


@pytest.mark.asyncio
async def test_an_unknown_or_inactive_objection_is_422(client, db_session):
    _, _, _, row = await handed(client, db_session, "it")
    inactive = await objection(db_session, active=False)
    for ids in ([str(inactive.id)], [str(uuid.uuid4())]):
        assert field_error(await client.post(c_url(row.id, "/counseling"), json={"outcome": "interested", "objection_ids": ids}), "objection_ids")


# --- C7: who may write -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_another_counselors_lead_is_404(client, db_session):
    _, _, _, row = await handed(client, db_session, "it")
    other = await make_user(db_session, "counselor", "it")
    await as_user(client, other)
    assert (await client.post(c_url(row.id, "/counseling"), json={"outcome": "interested"})).status_code == 404
    assert (await client.get(c_url(row.id, "/counseling"))).status_code == 404


@pytest.mark.asyncio
async def test_an_overseas_counselor_and_a_telecaller_are_403(client, db_session):
    _, tel, _, row = await handed(client, db_session, "overseas")
    assert (await client.post(c_url(row.id, "/counseling"), json={"outcome": "interested"})).status_code == 403
    await as_user(client, tel)
    assert (await client.post(c_url(row.id, "/counseling"), json={"outcome": "interested"})).status_code == 403


@pytest.mark.asyncio
async def test_a_closed_lead_is_409_for_create_and_edit(client, db_session):
    _, _, _, row = await handed(client, db_session, "it")
    created = (await client.post(c_url(row.id, "/counseling"), json={"outcome": "interested"})).json()
    await close(db_session, row)
    assert (await client.post(c_url(row.id, "/counseling"), json={"outcome": "interested"})).status_code == 409
    assert (await client.patch(c_url(row.id, f"/counseling/{created['id']}"), json={"outcome": "not_interested"})).status_code == 409
    assert (await client.get(c_url(row.id, "/counseling"))).json()["total"] == 1  # still readable


# --- PATCH -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_edit_replaces_sent_fields_and_objections_and_is_audited(client, db_session):
    _, _, counselor, row = await handed(client, db_session, "it")
    created = (await client.post(c_url(row.id, "/counseling"), json=await full_body(db_session))).json()
    other = await objection(db_session)
    response = await client.patch(c_url(row.id, f"/counseling/{created['id']}"), json={"outcome": "needs_time", "objection_ids": [str(other.id)], "fee_quoted": "40000"})
    assert response.status_code == 200, response.text
    out = response.json()
    assert (out["outcome"], out["fee_quoted"], [o["id"] for o in out["objections"]]) == ("needs_time", "40000.00", [str(other.id)])
    assert out["notes"] == NOTES and out["decision_maker"] == "parent"  # not sent = kept
    assert out["updated_by"]["id"] == str(counselor.id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "lead_counseling.update", AuditLog.entity_id == str(row.id)))
    assert audit.metadata_json["changes"]["outcome"] == ["interested", "needs_time"]
    items = (await client.get(c_url(row.id, "/timeline"))).json()["items"]
    assert any(i["kind"] == "counseling" and i["event"] == "updated" and i["to_value"] == "needs_time" for i in items)


@pytest.mark.asyncio
async def test_a_past_date_already_stored_still_saves_but_a_new_past_date_is_422(client, db_session):
    _, _, _, row = await handed(client, db_session, "it")
    created = (await client.post(c_url(row.id, "/counseling"), json={"outcome": "interested", "expected_joining_date": day(1)})).json()
    record = await db_session.get(LeadCounselingRecord, uuid.UUID(created["id"]))
    record.expected_joining_date = datetime.now(ZoneInfo("Asia/Kolkata")).date() - timedelta(days=5)
    await db_session.commit()
    url = c_url(row.id, f"/counseling/{created['id']}")
    assert (await client.patch(url, json={"outcome": "needs_time"})).status_code == 200  # AC3 applies at creation / change only
    assert field_error(await client.patch(url, json={"expected_joining_date": day(-2)}), "expected_joining_date")


@pytest.mark.asyncio
async def test_a_record_of_another_lead_or_unknown_is_404(client, db_session):
    _, _, _, row = await handed(client, db_session, "it")
    _, _, counselor_b, row_b = await setup(db_session, "it")
    mine = (await client.post(c_url(row.id, "/counseling"), json={"outcome": "interested"})).json()
    assert (await client.patch(c_url(row.id, f"/counseling/{uuid.uuid4()}"), json={"outcome": "enrolled"})).status_code == 404
    # the same counselor holding a second lead cannot edit record A through lead B's URL
    row_b.owner_id = (await db_session.get(LeadCounselingRecord, uuid.UUID(mine["id"]))).author_user_id
    await db_session.commit()
    assert (await client.patch(c_url(row_b.id, f"/counseling/{mine['id']}"), json={"outcome": "enrolled"})).status_code == 404


@pytest.mark.asyncio
async def test_null_on_outcome_is_422_on_edit(client, db_session):
    _, _, _, row = await handed(client, db_session, "it")
    created = (await client.post(c_url(row.id, "/counseling"), json={"outcome": "interested"})).json()
    assert field_error(await client.patch(c_url(row.id, f"/counseling/{created['id']}"), json={"outcome": None}), "outcome")


# --- C8: the telecaller side reads ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_telecaller_and_manager_read_and_the_record_survives_a_return(client, db_session):
    manager, tel, counselor, row = await handed(client, db_session, "it")
    created = (await client.post(c_url(row.id, "/counseling"), json={"outcome": "needs_time"})).json()
    assert (await client.post(c_url(row.id, "/return"), json={"reason": "Not ready yet"})).status_code == 200
    assert (await client.get(c_url(row.id, "/counseling"))).status_code == 404  # the counselor has lost the lead
    for reader in (tel, manager):
        await as_user(client, reader)
        response = await client.get(t_url(row.id, "/counseling"))
        assert response.status_code == 200, response.text
        assert [i["id"] for i in response.json()["items"]] == [created["id"]]
    other_tel = await make_user(db_session, "telecaller", "it")
    await as_user(client, other_tel)
    assert (await client.get(t_url(row.id, "/counseling"))).status_code == 404


# --- C6: the objections catalogue --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_manages_objections_and_a_counselor_sees_active_ones_only(client, db_session):
    manager, _, counselor, _ = await setup(db_session, "it")
    await as_user(client, manager)
    name = f"Too far {uuid.uuid4().hex[:6]}"
    created = await client.post(OBJECTIONS, json={"name": name})
    assert created.status_code == 201, created.text
    assert (await client.post(OBJECTIONS, json={"name": name.upper()})).status_code == 409
    oid = created.json()["id"]
    assert (await client.patch(f"{OBJECTIONS}/{oid}", json={"active": False})).json()["active"] is False
    await as_user(client, counselor)
    names = [o["name"] for o in (await client.get(f"{OBJECTIONS}?limit=100&q={name}")).json()["items"]]
    assert name not in names
    assert (await client.post(OBJECTIONS, json={"name": "x"})).status_code == 403


@pytest.mark.asyncio
async def test_handover_then_counseling_for_an_it_lead_from_scratch(client, db_session):
    """The happy path from the backlog: Python Full Stack, ₹45,000, joining in ten days, decision-maker parent."""
    _, tel, counselor, row = await setup(db_session, "it")
    assert (await handover(client, tel, row, counselor)).status_code == 200
    await as_user(client, counselor)
    body = await full_body(db_session, objection_ids=[], objection_notes=None)
    assert (await client.post(c_url(row.id, "/counseling"), json=body)).status_code == 201
