"""tel-008 -- the telecaller lead workspace (spec §2, §4; DEC-SCOPE-084): My Leads, the lead detail, the PATCH of contact fields and
priority, the read-only handed-over lead (D1, T19) and the timeline of stage + priority changes (W1). The shared test database is never
truncated, so every list assertion narrows to telecallers created by the test."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry, TelCampaign, TelProduct
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager, make_user, stage_url

LEADS = "/api/v1/telecaller/leads"


def url(lead_id, suffix: str = "") -> str:
    return f"{LEADS}/{lead_id}{suffix}"


async def lead(db, telecaller=None, **over) -> Enquiry:
    values = {"division": "it", "name": f"Lead {uuid.uuid4().hex[:6]}", "email": f"{uuid.uuid4().hex[:8]}@example.local", "phone": "9876543210",
              "subject": "Python", "message": "Please call me", "source": "website",
              "telecaller_user_id": telecaller.id if telecaller else None} | over
    row = Enquiry(**values)
    db.add(row)
    await db.commit()
    return row


async def team(db):
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager), await make_telecaller(db, manager)


async def seed_product(db, name: str = "Cyber Security") -> TelProduct:
    return await db.scalar(select(TelProduct).where(TelProduct.product_group == "it", TelProduct.name == name))


async def audits(db, row, action: str) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.entity_type == "enquiry", AuditLog.entity_id == str(row.id), AuditLog.action == action)
    return list((await db.scalars(stmt.order_by(AuditLog.created_at))).all())


# --- AC1 / AC6: the list --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_telecaller_lists_only_own_leads_newest_first(client, db_session):
    _, tel, other = await team(db_session)
    first, second = await lead(db_session, tel), await lead(db_session, tel)
    await lead(db_session, other)
    await lead(db_session)  # unassigned
    await as_user(client, tel)
    body = (await client.get(LEADS)).json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [str(second.id), str(first.id)]
    item = body["items"][0]
    assert item["read_only"] is False and item["status_label"] == "New Lead" and item["telecaller"]["id"] == str(tel.id)
    assert {"lead_code", "priority", "product", "campaign", "whatsapp_number", "city", "state"} <= set(item)


@pytest.mark.asyncio
async def test_filters_and_search_only_narrow(client, db_session):
    _, tel, other = await team(db_session)
    cyber = await seed_product(db_session)
    camp = TelCampaign(name=f"Camp {uuid.uuid4().hex[:8]}", source="instagram", product_id=cyber.id, start_date=date(2026, 9, 1))
    db_session.add(camp)
    await db_session.commit()
    hot = await lead(db_session, tel, priority="hot", product_id=cyber.id, campaign_id=camp.id, status="contacted", name="Asha Hot")
    cold = await lead(db_session, tel, priority="cold", phone="+91 99887 76655", whatsapp_number="9000011111")
    await lead(db_session, other, priority="hot", product_id=cyber.id)  # out of scope: never listed whatever the filter
    await as_user(client, tel)

    async def ids(**params) -> list[str]:
        response = await client.get(LEADS, params=params)
        assert response.status_code == 200, response.text
        return [item["id"] for item in response.json()["items"]]

    assert await ids(priority="hot") == [str(hot.id)]
    assert await ids(product_id=str(cyber.id)) == [str(hot.id)]
    assert await ids(campaign_id=str(camp.id)) == [str(hot.id)]
    assert await ids(status="contacted") == [str(hot.id)]
    assert await ids(q="asha hot") == [str(hot.id)]
    assert await ids(q=hot.lead_code) == [str(hot.id)]
    assert await ids(q="99887") == [str(cold.id)]
    assert await ids(q="9000011111") == [str(cold.id)]
    assert await ids(q=cold.email.upper()) == [str(cold.id)]
    assert await ids(q="%") == []  # literal, not a wildcard
    assert (await client.get(LEADS, params={"priority": "urgent"})).status_code == 422


@pytest.mark.asyncio
async def test_paging_total_is_exact(client, db_session):
    _, tel, _ = await team(db_session)
    for _ in range(3):
        await lead(db_session, tel)
    await as_user(client, tel)
    body = (await client.get(LEADS, params={"limit": 2, "offset": 2})).json()
    assert (body["total"], len(body["items"]), body["limit"], body["offset"]) == (3, 1, 2, 2)
    assert (await client.get(LEADS, params={"limit": 101})).status_code == 422


@pytest.mark.asyncio
async def test_manager_lists_reports_leads_and_their_teams_queue(client, db_session):
    manager, tel, tel2 = await team(db_session)
    stranger = await make_telecaller(db_session, await make_tl_manager(db_session))
    mine = {str((await lead(db_session, tel)).id), str((await lead(db_session, tel2)).id)}
    theirs = await lead(db_session, stranger)
    await as_user(client, manager)
    listed = {item["id"] for item in (await client.get(LEADS, params={"limit": 100})).json()["items"]}
    assert mine <= listed and str(theirs.id) not in listed
    assert (await client.get(url(theirs.id))).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_admin", "it"), ("counselor", "it"), ("it_student", "it"), ("bdm_manager", "global")])
async def test_other_roles_are_403(client, db_session, role, division):
    row = await lead(db_session)
    await as_user(client, await make_user(db_session, role, division))
    assert (await client.get(LEADS)).status_code == 403
    assert (await client.get(url(row.id))).status_code == 403
    assert (await client.patch(url(row.id), json={"priority": "hot"})).status_code == 403
    assert (await client.get(url(row.id, "/timeline"))).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client, db_session):
    client.cookies.clear()
    assert (await client.get(LEADS)).status_code == 401


# --- AC2: detail and IDOR -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_detail_carries_message_and_another_telecallers_lead_is_404(client, db_session):
    _, tel, other = await team(db_session)
    mine, theirs = await lead(db_session, tel), await lead(db_session, other)
    await as_user(client, tel)
    body = (await client.get(url(mine.id))).json()
    assert (body["id"], body["message"], body["read_only"]) == (str(mine.id), "Please call me", False)
    for path in (url(theirs.id), url(uuid.uuid4()), url(theirs.id, "/timeline")):
        assert (await client.get(path)).status_code == 404
    assert (await client.patch(url(theirs.id), json={"priority": "hot"})).status_code == 404


# --- AC3: priority + timeline ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_priority_change_is_saved_audited_and_on_the_timeline(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel, status="contacted")
    await as_user(client, tel)
    response = await client.patch(url(row.id), json={"priority": "hot"})
    assert response.status_code == 200, response.text
    assert response.json()["priority"] == "hot"
    assert (await client.post(stage_url(row.id), json={"to_stage": "qualified"})).status_code == 200
    rows = await audits(db_session, row, "lead.priority_change")
    assert [(a.user_id, a.metadata_json) for a in rows] == [(tel.id, {"from": "warm", "to": "hot"})]

    timeline = (await client.get(url(row.id, "/timeline"))).json()
    assert timeline["total"] == 2
    newest, oldest = timeline["items"]
    assert (newest["kind"], newest["from_value"], newest["to_value"], newest["to_label"]) == ("stage", "contacted", "qualified", "Qualified")
    assert (oldest["kind"], oldest["from_label"], oldest["to_label"], oldest["actor"]["id"]) == ("priority", "Warm", "Hot", str(tel.id))
    assert newest["at"] >= oldest["at"]


@pytest.mark.asyncio
async def test_same_priority_is_a_no_op_without_audit(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    assert (await client.patch(url(row.id), json={"priority": "warm"})).status_code == 200
    assert await audits(db_session, row, "lead.priority_change") == []
    assert (await client.get(url(row.id, "/timeline"))).json()["total"] == 0


# --- D2: contact fields ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_contact_fields_and_product_update_with_a_names_only_audit(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    cyber = await seed_product(db_session)
    await as_user(client, tel)
    response = await client.patch(url(row.id), json={
        "name": "  Meena Rao ", "email": "Meena@Example.com", "phone": "98765 43211", "whatsapp_number": "+91 98765 43211",
        "city": "Hyderabad", "state": "Telangana", "product_id": str(cyber.id),
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["email"], body["city"], body["product"]["name"]) == ("Meena Rao", "meena@example.com", "Hyderabad", "Cyber Security")
    stored = await db_session.scalar(select(Enquiry).where(Enquiry.id == row.id).execution_options(populate_existing=True))
    assert stored.phone_normalized == "+919876543211"
    (audit,) = await audits(db_session, row, "lead.contact_update")
    assert audit.metadata_json == {"fields": ["city", "email", "name", "phone", "product_id", "state", "whatsapp_number"]}
    cleared = await client.patch(url(row.id), json={"city": "", "product_id": None})
    assert cleared.status_code == 200 and cleared.json()["city"] is None and cleared.json()["product"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"telecaller_user_id": str(uuid.uuid4())}, {"owner_id": None}, {"status": "qualified"}, {"source": "google"}, {"campaign_id": None},
    {"qualification": "B.Tech"}, {"priority": "urgent"}, {"email": "not-an-email"}, {"email": ""}, {"name": "  "}, {"phone": "abc"},
    {"city": "a\x00b"},
])
async def test_non_editable_or_invalid_fields_are_422(client, db_session, body):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    await as_user(client, tel)
    assert (await client.patch(url(row.id), json=body)).status_code == 422


@pytest.mark.asyncio
async def test_inactive_or_unknown_product_is_422(client, db_session):
    _, tel, _ = await team(db_session)
    row = await lead(db_session, tel)
    retired = TelProduct(product_group="it", name=f"Retired {uuid.uuid4().hex[:8]}", team="it", active=False, sort_order=0)
    db_session.add(retired)
    await db_session.commit()
    await as_user(client, tel)
    for product_id in (retired.id, uuid.uuid4()):
        response = await client.patch(url(row.id), json={"product_id": str(product_id)})
        assert response.status_code == 422, response.text


# --- AC4 / D1: handed over ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handed_over_lead_is_read_only_for_the_telecaller_only(client, db_session):
    manager, tel, _ = await team(db_session)
    counselor = await make_user(db_session, "counselor", "it")
    row = await lead(db_session, tel, owner_id=counselor.id, status="follow_up")
    await as_user(client, tel)
    assert (await client.get(url(row.id))).json()["read_only"] is True
    assert (await client.get(LEADS)).json()["items"][0]["read_only"] is True
    assert (await client.patch(url(row.id), json={"priority": "hot"})).status_code == 403
    assert (await client.post(stage_url(row.id), json={"to_stage": "interested"})).status_code == 403
    assert (await client.get(url(row.id, "/timeline"))).status_code == 200
    await as_user(client, manager)
    assert (await client.get(url(row.id))).json()["read_only"] is False
    assert (await client.patch(url(row.id), json={"priority": "hot"})).status_code == 200
    assert (await client.post(stage_url(row.id), json={"to_stage": "interested"})).status_code == 200
