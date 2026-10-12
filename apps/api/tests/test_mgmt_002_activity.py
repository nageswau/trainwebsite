"""mgmt-002 -- the management audit trail: `management_audit.record` and GET /management/activity (spec MA1-MA10; AC1, AC2)."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import AuditLog
from app.services import management_audit
from tests.bdm001_helpers import login, make_user

ACTIVITY = "/api/v1/management/activity"

# EVID-017 §2's seven "who did X" points (MA2).
SECTION_2 = [
    ("mgmt.task", "create", ["title", "deadline"], None),
    ("mgmt.plan", "update", ["target"], None),
    ("mgmt.ledger", "approve", ["status"], {"status": ("pending", "approved")}),
    ("mgmt.investment", "create", ["amount"], {"amount": (None, "500000.00")}),
    ("mgmt.ledger", "update", ["amount"], {"amount": ("1000.00", "1500.00")}),
    ("mgmt.decision", "decide", ["status"], None),
    ("mgmt.task", "complete", ["status"], None),
]


async def write_all(db, actor) -> list[AuditLog]:
    rows = [management_audit.record(db, actor, kind, verb, str(uuid.uuid4()), fields=fields, values=values) for kind, verb, fields, values in SECTION_2]
    await db.commit()
    return rows


async def activity(client, **params) -> dict:
    response = await client.get(ACTIVITY, params=params)
    assert response.status_code == 200, response.text
    return response.json()


# --- record (MA1-MA4, MA10) ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_record_adds_one_row_with_actor_and_field_names_without_committing(db_session):
    partner = await make_user(db_session, "partner", "global")
    row = management_audit.record(db_session, partner, "mgmt.task", "create", "T-1", fields=["title", "deadline"])
    assert row in db_session.new  # the caller's transaction commits it with the record (MA10)
    assert (row.user_id, row.action, row.entity_type, row.entity_id) == (partner.id, "mgmt.task.create", "mgmt.task", "T-1")
    assert row.metadata_json == {"fields": ["title", "deadline"]}
    await db_session.rollback()


def test_record_refuses_unknown_kind_and_verb():
    with pytest.raises(ValueError):
        management_audit.record(None, None, "mgmt.unknown", "create", "x")
    with pytest.raises(ValueError):
        management_audit.record(None, None, "mgmt.task", "delete", "x")


def test_values_only_for_finance_and_partner_only_kinds_and_named_fields():
    with pytest.raises(ValueError):  # MA3: an operational kind never stores values
        management_audit.record(None, None, "mgmt.task", "update", "x", fields=["title"], values={"title": ("a", "b")})
    with pytest.raises(ValueError):  # a value for a field the entry does not name
        management_audit.record(None, None, "mgmt.ledger", "update", "x", fields=["amount"], values={"note": ("a", "b")})


@pytest.mark.asyncio
async def test_values_are_stored_as_strings(db_session):
    accountant = await make_user(db_session, "accountant", "global")
    row = management_audit.record(db_session, accountant, "mgmt.ledger", "update", "L-1", fields=["amount"], values={"amount": (1000, "1500.00")})
    assert row.metadata_json == {"fields": ["amount"], "values": {"amount": {"before": "1000", "after": "1500.00"}}}
    await db_session.rollback()


@pytest.mark.asyncio
async def test_bulk_import_is_one_entry_with_a_count(client, db_session):
    partner = await make_user(db_session, "partner", "global")
    management_audit.record(db_session, partner, "mgmt.ledger", "import", None, count=42)
    await db_session.commit()
    await login(client, partner)
    body = await activity(client, actor=str(partner.id))
    assert body["total"] == 1
    assert body["items"][0]["verb"] == "import" and body["items"][0]["count"] == 42


# --- AC1: each of the seven §2 kinds produces an entry with the actor ---------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_seven_section_2_actions_are_listed_with_the_actor(client, db_session):
    partner = await make_user(db_session, "partner", "global", name="Partner One")
    await write_all(db_session, partner)
    await login(client, partner)
    body = await activity(client, actor=str(partner.id))
    assert body["total"] == 7
    # One transaction shares one timestamp, so the seven compare as a multiset.
    assert sorted((i["kind"], i["verb"]) for i in body["items"]) == sorted((k, v) for k, v, _, _ in SECTION_2)
    for item in body["items"]:
        assert item["actor"] == {"id": str(partner.id), "full_name": "Partner One", "role": "partner"}
        assert item["kind_label"] and item["at"]
    ledger = next(i for i in body["items"] if i["verb"] == "update" and i["kind"] == "mgmt.ledger")
    assert ledger["fields"] == ["amount"] and ledger["values"] == {"amount": {"before": "1000.00", "after": "1500.00"}}
    assert {"id": str(partner.id), "full_name": "Partner One", "role": "partner"} in body["actors"]


@pytest.mark.asyncio
async def test_partner_two_sees_that_partner_one_approved_an_expense(client, db_session):
    one = await make_user(db_session, "partner", "global")
    two = await make_user(db_session, "partner", "global")
    management_audit.record(db_session, one, "mgmt.ledger", "approve", "E-1", fields=["status"])
    await db_session.commit()
    await login(client, two)
    body = await activity(client, actor=str(one.id), kind="mgmt.ledger")
    assert [(i["verb"], i["entity_id"], i["actor"]["id"]) for i in body["items"]] == [("approve", "E-1", str(one.id))]


# --- AC2 and MA5: tier filtering -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac2_accountant_cannot_see_an_investment_entry(client, db_session):
    partner = await make_user(db_session, "partner", "global")
    await write_all(db_session, partner)
    await login(client, await make_user(db_session, "accountant", "global"))
    body = await activity(client, actor=str(partner.id))
    assert {i["kind"] for i in body["items"]} == {"mgmt.ledger"}  # finance only: no investment, no operational kinds
    assert body["total"] == 2
    assert {k["value"] for k in body["kinds"]} == {"mgmt.ledger"}
    assert (await activity(client, actor=str(partner.id), kind="mgmt.investment"))["items"] == []


@pytest.mark.asyncio
async def test_super_admin_sees_operational_entries_only_and_capital_filter_returns_none(client, db_session):
    partner = await make_user(db_session, "partner", "global")
    await write_all(db_session, partner)
    management_audit.record(db_session, partner, "mgmt.capital", "create", "C-1", fields=["amount"], values={"amount": (None, "100")})
    await db_session.commit()
    await login(client, await make_user(db_session, "super_admin", "global"))
    body = await activity(client, actor=str(partner.id))
    assert {i["kind"] for i in body["items"]} == {"mgmt.task", "mgmt.plan", "mgmt.decision"}
    capital = await activity(client, kind="mgmt.capital")
    assert capital["items"] == [] and capital["total"] == 0


@pytest.mark.asyncio
async def test_actors_lists_only_people_with_a_visible_entry(client, db_session):
    partner = await make_user(db_session, "partner", "global")
    management_audit.record(db_session, partner, "mgmt.investment", "create", "I-1", fields=["amount"])
    await db_session.commit()
    await login(client, await make_user(db_session, "accountant", "global"))
    body = await activity(client)
    assert str(partner.id) not in {a["id"] for a in body["actors"]}


@pytest.mark.asyncio
async def test_non_management_entries_are_never_listed(client, db_session):
    partner = await make_user(db_session, "partner", "global")
    db_session.add(AuditLog(user_id=partner.id, action="lead.update", entity_type="enquiry", entity_id="x", metadata_json={}))
    await db_session.commit()
    await login(client, partner)
    assert (await activity(client, actor=str(partner.id)))["total"] == 0


# --- MA6: filters, paging, validation ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_date_filter_is_inclusive_ist_days(client, db_session):
    partner = await make_user(db_session, "partner", "global")
    old = management_audit.record(db_session, partner, "mgmt.task", "create", "OLD")
    new = management_audit.record(db_session, partner, "mgmt.task", "create", "NEW")
    # 2026-01-10 23:30 IST is 18:00 UTC on the 10th; 2026-01-11 00:30 IST is 19:00 UTC on the 10th.
    old.created_at = datetime(2026, 1, 10, 18, 0, tzinfo=UTC)
    new.created_at = datetime(2026, 1, 10, 19, 0, tzinfo=UTC)
    await db_session.commit()
    await login(client, partner)
    on_10th = await activity(client, actor=str(partner.id), date_from="2026-01-10", date_to="2026-01-10")
    on_11th = await activity(client, actor=str(partner.id), date_from="2026-01-11")
    assert [i["entity_id"] for i in on_10th["items"]] == ["OLD"]
    assert [i["entity_id"] for i in on_11th["items"]] == ["NEW"]


@pytest.mark.asyncio
async def test_paging_is_newest_first(client, db_session):
    partner = await make_user(db_session, "partner", "global")
    base = datetime.now(UTC) - timedelta(hours=1)
    for n in range(5):
        management_audit.record(db_session, partner, "mgmt.task", "create", f"T{n}").created_at = base + timedelta(minutes=n)
    await db_session.commit()
    await login(client, partner)
    first = await activity(client, actor=str(partner.id), limit=2)
    last = await activity(client, actor=str(partner.id), limit=2, offset=4)
    assert (first["total"], first["limit"], first["offset"]) == (5, 2, 0)
    assert [i["entity_id"] for i in first["items"]] == ["T4", "T3"]
    assert [i["entity_id"] for i in last["items"]] == ["T0"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [{"kind": "mgmt.unknown"}, {"date_from": "2026-02-02", "date_to": "2026-02-01"}, {"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10_001}, {"actor": "nope"}],
)
async def test_bad_filters_are_422(client, db_session, params):
    await login(client, await make_user(db_session, "partner", "global"))
    assert (await client.get(ACTIVITY, params=params)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["it_admin", "overseas_admin", "bdm_manager"])
async def test_no_management_tier_is_403(client, db_session, role):
    await login(client, await make_user(db_session, role, "global" if role == "bdm_manager" else role.split("_")[0]))
    assert (await client.get(ACTIVITY)).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(ACTIVITY)).status_code == 401


@pytest.mark.asyncio
async def test_activity_cannot_be_edited(client, db_session):
    await login(client, await make_user(db_session, "partner", "global"))
    for method in ("post", "put", "patch", "delete"):
        assert (await client.request(method.upper(), ACTIVITY)).status_code == 405


# --- MA8: the admin audit view and export leave out finance and partner-only management rows -----------------------------------
@pytest.mark.asyncio
async def test_admin_audit_and_export_hide_finance_and_partner_only_entries(client, db_session, monkeypatch):
    from app.api import admin

    written = {}
    monkeypatch.setattr(admin.storage, "write_bytes", lambda key, data, content_type: written.update(data=data))
    partner = await make_user(db_session, "partner", "global")
    rows = await write_all(db_session, partner)
    ids = {str(r.id) for r in rows}
    await login(client, await make_user(db_session, "super_admin", "global"))
    listed = (await client.get("/api/v1/admin/audit")).json()
    assert {x["entity_type"] for x in listed if str(x["id"]) in ids} == {"mgmt.task", "mgmt.plan", "mgmt.decision"}
    assert (await client.post("/api/v1/admin/audit/export")).status_code == 201
    exported = json.loads(written["data"])
    assert {x["entity_type"] for x in exported if x["id"] in ids} == {"mgmt.task", "mgmt.plan", "mgmt.decision"}
