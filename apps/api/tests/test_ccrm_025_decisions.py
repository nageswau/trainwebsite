"""ccrm-025 (DEC-SCOPE-255) -- the student's decision on the current offer: accept (sub-status, history, notices, the D1 warning), decline
(ccrm-015's offer_declined outcome, from either route), the refusals and scope, and the daily expiry job (D3). Uses ccrm-023's world."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import ApplicationOffer, ApplicationOutcome, AuditLog
from app.services.application_offers import expire_offers
from tests.agn001_helpers import client_for
from tests.agn003_helpers import mk_university
from tests.agn008_helpers import mk_application
from tests.agn009_helpers import mk_doc
from tests.agn023_helpers import ASSIGN, fresh, history_notes, notices
from tests.ccrm025_helpers import offers_world
from tests.test_ccrm_023_offers import ISSUED, OFFERS, _offers, body

DECIDE = OFFERS + "/{}/decision"
OUTCOME = "/api/v1/workflows/overseas/applications/{}/outcome"
TODAY = date.today()


@pytest_asyncio.fixture
async def world(db_session):
    return await offers_world(db_session)


async def _record(world, app, letter, **overrides) -> dict:
    async with client_for(world["counselor"].email) as c:
        r = await c.post(OFFERS.format(app.id), json=body(letter, **overrides))
    assert r.status_code == 201, r.text
    return r.json()["offer"]


async def _offer(db, offer_id) -> ApplicationOffer:
    return await db.get(ApplicationOffer, offer_id, populate_existing=True)


@pytest.mark.asyncio
async def test_accepting_records_the_decision_sub_status_history_audit_and_notice(db_session, world):  # AC1
    app = world["direct_app"]
    offer = await _record(world, app, world["direct_letter"])
    assert offer["decision"] == "considering" and offer["decision_label"] == "Considering" and offer["decision_date"] is None
    async with client_for(world["counselor"].email) as c:
        r = await c.post(DECIDE.format(app.id, offer["id"]), json={"decision": "accepted", "decision_date": ISSUED.isoformat()})
        again = await c.post(DECIDE.format(app.id, offer["id"]), json={"decision": "accepted", "decision_date": ISSUED.isoformat()})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["changed"] is True and data["sub_status"] == "offer_accepted" and data["other_accepted"] == []
    assert (data["offer"]["decision"], data["offer"]["decision_date"], data["offer"]["decided_by"]) == ("accepted", ISSUED.isoformat(), world["counselor"].full_name)
    assert again.status_code == 200 and again.json()["changed"] is False
    row = await _offer(db_session, offer["id"])
    assert (row.decision, row.decision_date, row.decided_by_id, row.status) == ("accepted", ISSUED, world["counselor"].id, "active")
    assert (await fresh(db_session, app)).sub_status == "offer_accepted"
    assert sum(1 for n in await history_notes(db_session, app) if n and n.startswith("Offer accepted")) == 1
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.offer_decision"))).all()
    assert [a.metadata_json["decision"] for a in audits] == ["accepted"]
    assert "Offer accepted" in [n.title for n in await notices(db_session, world["direct_student"])]


@pytest.mark.asyncio
async def test_declining_writes_the_offer_declined_outcome_and_closes_the_application(db_session, world):  # AC2
    app = world["direct_app"]
    offer = await _record(world, app, world["direct_letter"])
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(DECIDE.format(app.id, offer["id"]), json={"decision": "declined"})).status_code == 422  # no reason
        assert (await c.post(DECIDE.format(app.id, offer["id"]), json={"decision": "accepted"})).status_code == 200
        r = await c.post(DECIDE.format(app.id, offer["id"]), json={"decision": "declined", "reason": "Chose another university", "another_offer_preferred": True})
        late = await c.post(DECIDE.format(app.id, offer["id"]), json={"decision": "accepted"})
    assert r.status_code == 200, r.text
    assert r.json()["offer"]["decision"] == "declined" and r.json()["sub_status"] == "conditional_offer"  # Offer accepted is undone
    item = await fresh(db_session, app)
    assert (item.outcome, item.status) == ("offer_declined", "offer")
    event = await db_session.scalar(select(ApplicationOutcome).where(ApplicationOutcome.application_id == app.id, ApplicationOutcome.outcome == "offer_declined"))
    assert (event.reason, event.another_offer_preferred, event.outcome_date) == ("Chose another university", True, TODAY)
    assert late.status_code == 409  # closed until the Overseas Admin reopens it
    assert "Application update" in [n.title for n in await notices(db_session, world["direct_student"])]


@pytest.mark.asyncio
async def test_the_ccrm_015_outcome_route_also_records_the_decline_on_the_current_offer(db_session, world):
    app = world["direct_app"]
    offer = await _record(world, app, world["direct_letter"])
    async with client_for(world["counselor"].email) as c:
        r = await c.post(OUTCOME.format(app.id), json={"outcome": "offer_declined", "reason": "Fees too high"})
    assert r.status_code == 200, r.text
    row = await _offer(db_session, offer["id"])
    assert (row.decision, row.decision_date, row.decided_by_id) == ("declined", TODAY, world["counselor"].id)


@pytest.mark.asyncio
async def test_accepting_warns_about_the_students_other_accepted_offers_but_never_blocks(db_session, world):  # AC3, D1
    student, first = world["direct_student"], world["direct_app"]
    second = await mk_application(db_session, agent=None, university=await mk_university(db_session), student=student, status="university_selection")
    async with client_for(world["admin"].email) as c:
        assert (await c.put(ASSIGN.format(second.id), json={"counselor_id": str(world["counselor"].id)})).status_code == 200
    second_letter = await mk_doc(db_session, student=student, application=second, document_type="Offer letter")
    one = await _record(world, first, world["direct_letter"])
    two = await _record(world, second, second_letter)
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(DECIDE.format(first.id, one["id"]), json={"decision": "accepted"})).json()["other_accepted"] == []
        r = await c.post(DECIDE.format(second.id, two["id"]), json={"decision": "accepted"})
    assert r.status_code == 200, r.text
    first_code = (await fresh(db_session, first)).application_code
    assert [(o["id"], o["application_code"]) for o in r.json()["other_accepted"]] == [(str(first.id), first_code)]


@pytest.mark.asyncio
async def test_only_the_current_offer_of_this_application_can_be_decided_on_a_valid_date(db_session, world):
    app = world["direct_app"]
    old = await _record(world, app, world["direct_letter"])
    new = await _record(world, app, world["direct_letter"], offer_type="unconditional", conditions=None)
    other = await _record(world, world["app"], world["agency_letter"])
    async with client_for(world["counselor"].email) as c:
        superseded = await c.post(DECIDE.format(app.id, old["id"]), json={"decision": "accepted"})
        foreign = await c.post(DECIDE.format(app.id, other["id"]), json={"decision": "accepted"})
        early = await c.post(DECIDE.format(app.id, new["id"]), json={"decision": "accepted", "decision_date": (ISSUED - timedelta(days=1)).isoformat()})
        future = await c.post(DECIDE.format(app.id, new["id"]), json={"decision": "accepted", "decision_date": (TODAY + timedelta(days=5)).isoformat()})
        expired = await c.post(DECIDE.format(app.id, new["id"]), json={"decision": "expired"})
    assert superseded.status_code == 409 and superseded.json()["detail"] == "Only the current offer can be accepted or declined"
    assert foreign.status_code == 404
    assert early.status_code == 422 and early.json()["detail"] == "The decision date cannot be before the offer was issued"
    assert future.status_code == 422 and expired.status_code == 422
    assert (await _offer(db_session, new["id"])).decision == "considering"


@pytest.mark.asyncio
async def test_scope_and_on_hold_refuse_a_decision(db_session, world):  # AC7
    app = world["direct_app"]
    offer = await _record(world, app, world["direct_letter"])
    url, accept = DECIDE.format(app.id, offer["id"]), {"decision": "accepted"}
    for email in (world["counselor2"].email, world["direct_student"].email):
        async with client_for(email) as c:
            assert (await c.post(url, json=accept)).status_code == 403, email
    item = await fresh(db_session, app)
    item.outcome = "on_hold"
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(url, json=accept)).status_code == 409
    item.outcome = None
    await db_session.commit()
    async with client_for(world["admin"].email) as c:
        assert (await c.post(url, json=accept)).status_code == 200  # the Overseas Admin on any application


@pytest.mark.asyncio
async def test_accepting_an_agency_application_tells_the_agency(db_session, world):  # CC5
    offer = await _record(world, world["app"], world["agency_letter"])
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(DECIDE.format(world["app"].id, offer["id"]), json={"decision": "accepted"})).status_code == 200
    assert "Offer accepted" in [n.title for n in await notices(db_session, world["staff"]["user"])]


@pytest.mark.asyncio
async def test_the_daily_job_expires_undecided_offers_past_their_deadline_once(db_session, world):  # AC4, D3
    app = world["direct_app"]
    deadline = TODAY - timedelta(days=1)
    offer = await _record(world, app, world["direct_letter"], offer_deadline=deadline.isoformat())
    assert await expire_offers(db_session, TODAY) >= 1
    row = await _offer(db_session, offer["id"])
    assert (row.decision, row.decision_date, row.decided_by_id, row.status, row.closed_by_id) == ("expired", TODAY, None, "expired", None)
    assert row.status_reason == f"Offer deadline {deadline.isoformat()} passed without a decision"
    item = await fresh(db_session, app)
    assert (item.status, item.sub_status, item.offer_type) == ("offer", None, None)  # OF4: the stage stays, the mirror is cleared
    assert any(n and n.startswith("Offer expired") for n in await history_notes(db_session, app))
    for person in (world["counselor"], world["direct_student"]):
        assert "Offer expired" in [n.title for n in await notices(db_session, person)]
    assert await expire_offers(db_session, TODAY) == 0  # a rerun finds nothing left


@pytest.mark.asyncio
async def test_the_job_leaves_decided_undated_future_and_on_hold_offers_alone(db_session, world):
    past = (TODAY - timedelta(days=1)).isoformat()
    accepted = await _record(world, world["direct_app"], world["direct_letter"], offer_deadline=past)
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(DECIDE.format(world["direct_app"].id, accepted["id"]), json={"decision": "accepted"})).status_code == 200
    held = await _record(world, world["app"], world["agency_letter"], offer_deadline=past)
    item = await fresh(db_session, world["app"])
    item.outcome = "on_hold"
    await db_session.commit()
    await expire_offers(db_session, TODAY)
    assert (await _offer(db_session, accepted["id"])).status == "active"
    assert (await _offer(db_session, held["id"])).decision == "considering"
    item.outcome = None
    await db_session.commit()
    undated = await _record(world, world["app"], world["agency_letter"], offer_deadline=None)
    await expire_offers(db_session, TODAY)
    assert (await _offer(db_session, undated["id"])).status == "active"
    assert [o.status for o in await _offers(db_session, world["app"])] == ["superseded", "active"]
