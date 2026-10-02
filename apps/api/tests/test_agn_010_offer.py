"""AGN-010 AC01-AC04, AC07 -- record an offer: validation, stage sync, history, audit, no-op retries, PATCH deadline cross-check
(spec §4)."""

from datetime import date, timedelta

import pytest
import pytest_asyncio

from app.models import OverseasApplication
from tests.agn001_helpers import client_for
from tests.agn008_helpers import APPS
from tests.agn010_helpers import OFFER_DATE, history_of, offer_audits, offer_body, offer_url, offer_world, writes_for


@pytest_asyncio.fixture
async def world(db_session):
    return await offer_world(db_session)


async def _app(db, world) -> OverseasApplication:
    return await db.get(OverseasApplication, world["app"].id, populate_existing=True)


@pytest.mark.asyncio
async def test_recording_a_conditional_offer_moves_to_offer_with_one_history_and_audit_row(db_session, world):
    async with client_for(world["staff"]["user"].email) as c:
        r = await c.put(offer_url(world["app"].id), json=offer_body(offer_document_id=world["letter"].id, expected_status="university_selection"))
    assert r.status_code == 200, r.text
    body = r.json()["application"]
    assert body["status"] == "offer"
    assert body["offer"] == {
        "type": "conditional",
        "date": OFFER_DATE.isoformat(),
        "deadline": (OFFER_DATE + timedelta(days=30)).isoformat(),
        "conditions": "IELTS 6.5 overall",
        "document": {"id": str(world["letter"].id), "name": "Offer letter", "verification_status": "pending"},
    }
    assert [d["id"] for d in body["offer_letters"]] == [str(world["letter"].id)]
    assert "file_url" not in body["offer_letters"][0]
    [h] = await history_of(db_session, world["app"].id)
    assert (h.from_status, h.to_status) == ("university_selection", "offer")
    assert h.notes.startswith("Offer recorded: Conditional, offer date ") and "Conditions: IELTS 6.5 overall" in h.notes
    [audit] = await offer_audits(db_session, world["app"].id)
    assert audit.metadata_json["offer_type"] == "conditional" and audit.metadata_json["to_status"] == "offer"
    assert "IELTS" not in str(audit.metadata_json)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"offer_deadline": OFFER_DATE - timedelta(days=1)}, "Offer deadline cannot be before the offer date"),
        ({"conditions": "   "}, "A conditional offer needs its conditions"),
        ({"conditions": None}, "A conditional offer needs its conditions"),
        ({"offer_type": "unconditional"}, "An unconditional offer has no conditions"),
        ({"offer_date": date.today() + timedelta(days=5)}, "Offer date cannot be in the future"),
        ({"offer_type": "maybe"}, None),
        ({"offer_type": None}, None),
        ({"offer_date": "1999-12-31"}, "Dates must be between 2000 and 2100"),
        ({"conditions": "x" * 2001}, None),
    ],
)
async def test_invalid_offers_are_422_and_write_nothing(db_session, world, overrides, message):
    async with client_for(world["master"].email) as c:
        r = await c.put(offer_url(world["app"].id), json=offer_body(**overrides))
    assert r.status_code == 422
    if message:
        assert message in str(r.json()["detail"])
    assert await writes_for(db_session, world["app"].id) == (0, 0)
    assert (await _app(db_session, world)).offer_type is None


@pytest.mark.asyncio
async def test_missing_type_is_422(db_session, world):
    body = offer_body()
    del body["offer_type"]
    async with client_for(world["master"].email) as c:
        assert (await c.put(offer_url(world["app"].id), json=body)).status_code == 422


@pytest.mark.asyncio
async def test_deadline_on_the_offer_date_and_no_deadline_are_accepted(db_session, world):
    async with client_for(world["master"].email) as c:
        assert (await c.put(offer_url(world["app"].id), json=offer_body(offer_deadline=OFFER_DATE))).status_code == 200
        r = await c.put(offer_url(world["app"].id), json=offer_body(offer_deadline=None))
    assert r.status_code == 200 and r.json()["application"]["offer"]["deadline"] is None


@pytest.mark.asyncio
async def test_switching_to_unconditional_is_recorded_in_history_and_clears_conditions(db_session, world):
    async with client_for(world["master"].email) as c:
        assert (await c.put(offer_url(world["app"].id), json=offer_body())).status_code == 200
        r = await c.put(offer_url(world["app"].id), json=offer_body(offer_type="unconditional", conditions=None, expected_status="offer"))
    assert r.status_code == 200 and r.json()["application"]["offer"]["conditions"] is None
    row = await _app(db_session, world)
    assert (row.offer_type, row.offer_conditions, row.status) == ("unconditional", None, "offer")
    first, second = await history_of(db_session, world["app"].id)
    assert (second.from_status, second.to_status) == ("offer", "offer")
    assert "Conditional → Unconditional" in second.notes and "conditions removed (were: IELTS 6.5 overall)" in second.notes
    assert len(await offer_audits(db_session, world["app"].id)) == 2


@pytest.mark.asyncio
async def test_an_identical_put_writes_nothing(db_session, world):
    async with client_for(world["master"].email) as c:
        assert (await c.put(offer_url(world["app"].id), json=offer_body(offer_document_id=world["letter"].id))).status_code == 200
        before = await writes_for(db_session, world["app"].id)
        r = await c.put(offer_url(world["app"].id), json=offer_body(offer_document_id=world["letter"].id))
    assert r.status_code == 200 and r.json()["application"]["offer"]["type"] == "conditional"
    assert await writes_for(db_session, world["app"].id) == before


@pytest.mark.asyncio
async def test_unlinking_the_document_is_a_change(db_session, world):
    async with client_for(world["master"].email) as c:
        await c.put(offer_url(world["app"].id), json=offer_body(offer_document_id=world["letter"].id))
        r = await c.put(offer_url(world["app"].id), json=offer_body(offer_document_id=None))
    assert r.json()["application"]["offer"]["document"] is None
    assert "offer letter removed" in (await history_of(db_session, world["app"].id))[-1].notes


@pytest.mark.asyncio
@pytest.mark.parametrize(("start", "end"), [("enquiry", "offer"), ("offer_received", "offer"), ("offer", "offer"), ("visa_documentation", "visa_documentation"), ("enrolled", "enrolled")])
async def test_stage_moves_forward_to_offer_only_from_before_it(db_session, world, start, end):
    row = await _app(db_session, world)
    row.status = start
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await c.put(offer_url(world["app"].id), json=offer_body(offer_type="unconditional", conditions=None))
    assert r.status_code == 200 and r.json()["application"]["status"] == end
    [h] = await history_of(db_session, world["app"].id)
    assert (h.from_status, h.to_status) == (start, end)


@pytest.mark.asyncio
@pytest.mark.parametrize(("setup", "detail"), [("withdrawn", "This application is withdrawn"), ("archived", "Unarchive this student first"), ("stale", "changed since you opened it")])
async def test_closed_or_stale_is_409_and_writes_nothing(db_session, world, setup, detail):
    body = offer_body()
    if setup == "withdrawn":
        (await _app(db_session, world)).status = "withdrawn"
    elif setup == "archived":
        world["record"].status = "archived"
        db_session.add(world["record"])
    else:
        body["expected_status"] = "enquiry"
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await c.put(offer_url(world["app"].id), json=body)
    assert r.status_code == 409 and detail in r.json()["detail"]
    assert await writes_for(db_session, world["app"].id) == (0, 0)


@pytest.mark.asyncio
async def test_patch_refuses_a_deadline_before_the_recorded_offer_date(db_session, world):
    async with client_for(world["master"].email) as c:
        await c.put(offer_url(world["app"].id), json=offer_body())
        r = await c.patch(f"{APPS}/{world['app'].id}", json={"offer_deadline": (OFFER_DATE - timedelta(days=1)).isoformat()})
        assert r.status_code == 422 and "Offer deadline cannot be before the offer date" in str(r.json()["detail"])
        assert (await c.patch(f"{APPS}/{world['app'].id}", json={"offer_deadline": None})).status_code == 200
        assert (await c.patch(f"{APPS}/{world['app'].id}", json={"offer_deadline": OFFER_DATE.isoformat()})).status_code == 200


def test_offer_audit_is_listed_in_staff_activity():  # AGN-021: a Master sees staff record offers
    from app.services.staff_activity import STAFF_ACTIVITY_ACTIONS

    assert "overseas.application.offer" in STAFF_ACTIVITY_ACTIONS


@pytest.mark.asyncio
async def test_patch_without_an_offer_keeps_todays_deadline_rules(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await c.patch(f"{APPS}/{world['app'].id}", json={"offer_deadline": "2001-01-01"})
    assert r.status_code == 200 and r.json()["application"]["offer"] is None
