"""tel-005 -- manual lead creation, the duplicate panel, the duplicate check and "Add enquiry to this lead" (spec §1, §3; DEC-SCOPE-086;
I1, I2, I5, R1-R6). The test database is shared and never truncated, and the duplicate match runs across every lead, so each test uses a
fresh mobile number and email."""

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Enquiry, LeadEnquiry, LeadStageHistory, TelCampaign, TelProduct
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager, make_user

LEADS = "/api/v1/telecaller/leads"
CHECK = f"{LEADS}/duplicate-check"


def mobile() -> str:
    """A ten-digit Indian mobile never used before (6-9 lead digit)."""
    return f"9{uuid.uuid4().int % 10**9:09d}"


def mail() -> str:
    return f"t5-{uuid.uuid4().hex[:10]}@example.com"


async def product(db, name: str = "Cyber Security") -> TelProduct:
    return await db.scalar(select(TelProduct).where(TelProduct.product_group == "it", TelProduct.name == name))


async def team(db):
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager), await make_telecaller(db, manager)


async def existing(db, telecaller=None, **over) -> Enquiry:
    values = {"division": "it", "name": f"Old {uuid.uuid4().hex[:6]}", "email": mail(), "phone": mobile(), "subject": "Python",
              "message": "Earlier enquiry", "source": "website", "telecaller_user_id": telecaller.id if telecaller else None} | over
    row = Enquiry(**values)
    db.add(row)
    await db.commit()
    return row


async def body(db, **over) -> dict:
    cyber = await product(db)
    return {"name": "Rahul Kumar", "phone": mobile(), "product_id": str(cyber.id), "source": "instagram"} | over


async def audits(db, entity_id, action: str) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.entity_type == "enquiry", AuditLog.entity_id == str(entity_id), AuditLog.action == action)
    return list((await db.scalars(stmt)).all())


# --- create (I1, I2, R5, R6) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_telecaller_creates_a_lead_assigned_to_themselves(client, db_session):
    _, tel, _ = await team(db_session)
    cyber = await product(db_session)
    camp = TelCampaign(name=f"Sep {uuid.uuid4().hex[:8]}", source="instagram", product_id=cyber.id, start_date=date(2026, 9, 1))
    db_session.add(camp)
    await db_session.commit()
    await as_user(client, tel)
    payload = await body(db_session, phone="+91 98" + mobile()[2:], campaign_id=str(camp.id), priority="hot", city="Pune")
    response = await client.post(LEADS, json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["email"] is None  # I1: a mobile is enough
    assert (data["status"], data["telecaller"]["id"], data["division"]) == ("assigned", str(tel.id), "it")
    assert (data["subject"], data["message"], data["priority"], data["campaign"]["id"]) == ("Cyber Security", "", "hot", str(camp.id))
    assert data["read_only"] is False
    lead = await db_session.get(Enquiry, uuid.UUID(data["id"]))
    assert lead.phone_normalized.startswith("+9198")
    history = (await db_session.scalars(select(LeadStageHistory).where(LeadStageHistory.lead_id == lead.id))).all()
    assert [(h.from_stage, h.to_stage, h.event, h.actor_user_id) for h in history] == [("new", "assigned", "assigned", tel.id)]
    [audit] = await audits(db_session, lead.id, "lead.create")
    assert audit.user_id == tel.id and "Rahul" not in str(audit.metadata_json)  # no personal data in the audit row


@pytest.mark.asyncio
async def test_a_manager_lead_waits_unassigned_in_its_teams_queue(client, db_session):
    manager, _, _ = await team(db_session)
    await as_user(client, manager)
    response = await client.post(LEADS, json=await body(db_session, email=mail().upper(), subject="Weekend batch", message="Call after 6"))
    assert response.status_code == 201, response.text
    data = response.json()
    assert (data["status"], data["telecaller"], data["division"]) == ("new", None, "it")
    assert data["email"] == data["email"].lower() and (data["subject"], data["message"]) == ("Weekend batch", "Call after 6")
    listed = (await client.get(LEADS, params={"q": data["lead_code"]})).json()["items"]
    assert [item["id"] for item in listed] == [data["id"]]  # in the manager's team queue


@pytest.mark.asyncio
async def test_a_product_without_a_team_needs_a_division(client, db_session):
    _, tel, _ = await team(db_session)
    other = TelProduct(product_group="other", name=f"Other {uuid.uuid4().hex[:8]}", team=None)
    db_session.add(other)
    await db_session.commit()
    await as_user(client, tel)
    missing = await client.post(LEADS, json=await body(db_session, product_id=str(other.id)))
    assert missing.status_code == 422 and "division" in missing.text.lower()
    ok = await client.post(LEADS, json=await body(db_session, product_id=str(other.id), division="overseas"))
    assert ok.status_code == 201 and ok.json()["division"] == "overseas"


@pytest.mark.asyncio
async def test_the_product_team_decides_the_division(client, db_session):
    _, tel, _ = await team(db_session)
    await as_user(client, tel)
    response = await client.post(LEADS, json=await body(db_session, division="overseas"))
    assert response.status_code == 422  # an IT product's lead is an IT lead


@pytest.mark.asyncio
async def test_create_validation(client, db_session):
    _, tel, _ = await team(db_session)
    cyber = await product(db_session)
    inactive = TelProduct(product_group="it", name=f"Old {uuid.uuid4().hex[:8]}", team="it", active=False)
    other_camp = TelCampaign(name=f"C {uuid.uuid4().hex[:8]}", source="google", product_id=cyber.id, start_date=date(2026, 9, 1))
    off_camp = TelCampaign(name=f"C {uuid.uuid4().hex[:8]}", source="instagram", product_id=cyber.id, start_date=date(2026, 9, 1), active=False)
    db_session.add_all([inactive, other_camp, off_camp])
    await db_session.commit()
    await as_user(client, tel)
    for over in (
        {"phone": None}, {"phone": "12345"}, {"name": " "}, {"product_id": None}, {"product_id": str(inactive.id)},
        {"source": "tiktok"}, {"email": "not-an-email"}, {"campaign_id": str(other_camp.id)}, {"campaign_id": str(off_camp.id)},
        {"priority": "urgent"}, {"telecaller_user_id": str(tel.id)}, {"passing_year": 1800},
    ):
        payload = await body(db_session, **over)
        response = await client.post(LEADS, json={k: v for k, v in payload.items() if v is not None})
        assert response.status_code == 422, (over, response.text)


@pytest.mark.asyncio
async def test_roles(client, db_session):
    payload = await body(db_session)
    client.cookies.clear()
    assert (await client.post(LEADS, json=payload)).status_code == 401
    assert (await client.get(CHECK, params={"phone": payload["phone"]})).status_code == 401
    counselor = await make_user(db_session, "counselor", "it")
    await as_user(client, counselor)
    assert (await client.post(LEADS, json=payload)).status_code == 403
    assert (await client.get(CHECK, params={"phone": payload["phone"]})).status_code == 403
    lead = await existing(db_session)
    assert (await client.post(f"{LEADS}/{lead.id}/enquiries", json={"subject": "Again", "source": "website"})).status_code == 403


# --- duplicates (T12, R1, R2) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_duplicate_mobile_in_another_format_is_blocked_with_the_panel(client, db_session):
    _, tel, other = await team(db_session)
    number = mobile()
    old = await existing(db_session, other, phone=f"0{number[:5]} {number[5:]}", status="contacted")
    await as_user(client, tel)
    before = await db_session.scalar(select(func.count()).select_from(Enquiry))
    response = await client.post(LEADS, json=await body(db_session, phone=f"+91 {number}"))
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert (detail["code"], detail["message"]) == ("duplicate_lead", "Lead already exists.")
    [match] = detail["matches"]
    assert match["id"] == str(old.id) and match["lead_code"] == old.lead_code and match["name"] == old.name
    assert (match["status"], match["status_label"], match["matched_on"]) == ("contacted", "Contacted", ["phone"])
    assert match["telecaller"]["full_name"] == other.full_name and match["counselor"] is None and match["last_contact_at"] is None
    assert match["in_scope"] is False
    assert [(e["subject"], e["source"]) for e in match["enquiries"]] == [("Python", "website")]
    assert not {"phone", "email", "whatsapp_number", "message"} & set(match)  # nothing of the other lead beyond what was typed
    assert await db_session.scalar(select(func.count()).select_from(Enquiry)) == before


@pytest.mark.asyncio
async def test_a_duplicate_email_in_another_case_and_a_closed_lead_match(client, db_session):
    _, tel, _ = await team(db_session)
    address = mail()
    old = await existing(db_session, tel, email=address, status="not_interested")
    await as_user(client, tel)
    response = await client.post(LEADS, json=await body(db_session, email=address.upper()))
    assert response.status_code == 409
    [match] = response.json()["detail"]["matches"]
    assert (match["id"], match["status"], match["matched_on"], match["in_scope"]) == (str(old.id), "not_interested", ["email"], True)


@pytest.mark.asyncio
async def test_the_duplicate_check_endpoint(client, db_session):
    _, tel, _ = await team(db_session)
    old = await existing(db_session)
    db_session.add(LeadEnquiry(lead_id=old.id, subject="Second ask", message="Hi again", source="google"))
    await db_session.commit()
    await as_user(client, tel)
    found = await client.get(CHECK, params={"phone": old.phone, "email": old.email})
    assert found.status_code == 200
    [match] = found.json()["matches"]
    assert match["matched_on"] == ["phone", "email"]
    assert [e["subject"] for e in match["enquiries"]] == ["Second ask", "Python"]  # newest first, the lead's own enquiry included
    assert (await client.get(CHECK, params={"phone": mobile()})).json() == {"matches": []}
    assert (await client.get(CHECK)).status_code == 422
    assert (await client.get(CHECK, params={"phone": "12"})).status_code == 422


# --- Add enquiry to this lead (I5, AC3) ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_any_telecaller_adds_an_enquiry_to_a_closed_lead_which_stays_closed(client, db_session):
    _, tel, other = await team(db_session)
    old = await existing(db_session, other, status="not_interested")
    cyber = await product(db_session)
    camp = TelCampaign(name=f"C {uuid.uuid4().hex[:8]}", source="google", product_id=cyber.id, start_date=date(2026, 9, 1))
    db_session.add(camp)
    await db_session.commit()
    await as_user(client, tel)
    response = await client.post(f"{LEADS}/{old.id}/enquiries",
                                 json={"subject": "Now interested", "message": "Called back", "source": "google", "campaign_id": str(camp.id)})
    assert response.status_code == 201, response.text
    data = response.json()
    assert (data["lead_id"], data["lead_code"], data["subject"], data["source"]) == (str(old.id), old.lead_code, "Now interested", "google")
    row = await db_session.get(LeadEnquiry, uuid.UUID(data["id"]))
    assert (row.created_by_user_id, row.campaign_id, row.message) == (tel.id, camp.id, "Called back")
    await db_session.refresh(old)
    assert old.status == "not_interested"  # T13: only a manager reopens
    assert len(await audits(db_session, old.id, "lead.enquiry_add")) == 1
    # the owner's timeline shows it
    await as_user(client, other)
    rows = (await client.get(f"{LEADS}/{old.id}/timeline")).json()["items"]
    enquiry = next(r for r in rows if r["kind"] == "enquiry")
    assert (enquiry["to_value"], enquiry["from_value"], enquiry["reason"], enquiry["actor"]["id"]) == ("Now interested", "google", "Called back", str(tel.id))


@pytest.mark.asyncio
async def test_add_enquiry_validation(client, db_session):
    _, tel, _ = await team(db_session)
    old = await existing(db_session)
    await as_user(client, tel)
    url = f"{LEADS}/{old.id}/enquiries"
    assert (await client.post(f"{LEADS}/{uuid.uuid4()}/enquiries", json={"subject": "Again", "source": "website"})).status_code == 404
    for bad in ({"subject": "", "source": "website"}, {"subject": "Again", "source": "tiktok"}, {"subject": "Again"},
                {"subject": "Again", "source": "website", "campaign_id": str(uuid.uuid4())}, {"subject": "Again", "source": "website", "x": 1}):
        assert (await client.post(url, json=bad)).status_code == 422, bad


# --- R7: two intakes of one person serialise ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lock_identity_holds_the_persons_keys_until_the_transaction_ends():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.core.config import settings
    from app.services import lead_intake

    engine = create_async_engine(settings.database_url)
    phone_key, email_key = lead_intake.identity(mobile(), mail())
    probe = text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))")
    try:
        async with AsyncSession(engine) as first, AsyncSession(engine) as second:
            async with first.begin():
                await lead_intake.lock_identity(first, phone_key, email_key)
                async with second.begin():
                    assert await second.scalar(probe, {"key": f"lead:phone:{phone_key}"}) is False
                    assert await second.scalar(probe, {"key": f"lead:email:{email_key}"}) is False
            async with second.begin():  # released when the first transaction ends
                assert await second.scalar(probe, {"key": f"lead:phone:{phone_key}"}) is True
    finally:
        await engine.dispose()
