"""ccrm-024 (DEC-SCOPE-260, C1-C11) -- offer conditions: add and update on the current offer, evidence for met (C2), notes for
waived/failed (C5), the agent owner on agency applications only (C6), seeding from the offer text (C1) on the counselor route and the
agency PUT, history on supersede (C3), the agency deadline PATCH moving them (C9), the all-satisfied summary (C4), scope and no file keys."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import ApplicationOfferCondition, AuditLog
from tests.agn001_helpers import client_for
from tests.agn008_helpers import APPS
from tests.agn009_helpers import PDF, mk_doc
from tests.agn010_helpers import offer_body, offer_url
from tests.agn023_helpers import fresh, history_notes, notices
from tests.ccrm025_helpers import offers_world
from tests.test_ccrm_023_offers import BASE, OFFERS, WITHDRAW, body

CONDITIONS = OFFERS + "/{}/conditions"
CONDITION = CONDITIONS + "/{}"
EVIDENCE = BASE + "/condition-evidence"
DUE = (date.today() + timedelta(days=20)).isoformat()


@pytest_asyncio.fixture
async def world(db_session):
    return await offers_world(db_session)


async def _rows(db, offer_id) -> list[ApplicationOfferCondition]:
    stmt = select(ApplicationOfferCondition).where(ApplicationOfferCondition.offer_id == offer_id).order_by(ApplicationOfferCondition.created_at, ApplicationOfferCondition.id)
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


async def _offer(c, app, letter, **overrides) -> dict:
    r = await c.post(OFFERS.format(app.id), json=body(letter, **overrides))
    assert r.status_code == 201, r.text
    return r.json()["offer"]


async def _evidence(c, app) -> dict:
    r = await c.post(EVIDENCE.format(app.id), files={"file": ("ielts.pdf", PDF, "application/pdf")})
    assert r.status_code == 201, r.text
    return r.json()["document"]


@pytest.mark.asyncio
async def test_recording_an_offer_with_conditions_text_seeds_one_open_student_condition(db_session, world):  # AC6, C1
    async with client_for(world["counselor"].email) as c:
        offer = await _offer(c, world["direct_app"], world["direct_letter"])
        listed = (await c.get(OFFERS.format(world["direct_app"].id))).json()
    [row] = await _rows(db_session, offer["id"])
    assert (row.description, row.owner, row.status, row.created_by_id) == ("IELTS 6.5 overall", "student", "open", world["counselor"].id)
    [view] = listed["offers"][0]["condition_items"]
    assert (view["description"], view["owner"], view["owner_label"], view["status_label"], view["evidence"]) == ("IELTS 6.5 overall", "student", "Student", "Open", None)
    assert listed["offers"][0]["conditions_summary"] == {"total": 1, "satisfied": 0, "open": 1, "failed": 0, "all_satisfied": False}
    assert listed["agency"] is False and listed["evidence_documents"] == []


@pytest.mark.asyncio
async def test_an_offer_without_conditions_text_seeds_nothing(db_session, world):
    async with client_for(world["counselor"].email) as c:
        offer = await _offer(c, world["direct_app"], world["direct_letter"], offer_type="unconditional", conditions=None)
    assert await _rows(db_session, offer["id"]) == []


@pytest.mark.asyncio
async def test_the_counselor_adds_a_condition_with_history_audit_and_both_sides_told(db_session, world):  # AC1, CC5
    app = world["app"]
    async with client_for(world["counselor"].email) as c:
        offer = await _offer(c, app, world["agency_letter"], offer_type="pathway", conditions=None)
        r = await c.post(CONDITIONS.format(app.id, offer["id"]), json={"description": "Final transcript", "owner": "agent", "due_date": DUE})
    assert r.status_code == 201, r.text
    condition = r.json()["condition"]
    assert (condition["description"], condition["owner"], condition["due_date"], condition["status"]) == ("Final transcript", "agent", DUE, "open")
    assert r.json()["conditions_summary"]["total"] == 1
    [row] = await _rows(db_session, offer["id"])
    assert (row.created_by_id, row.status_changed_at) == (world["counselor"].id, None)
    item = await fresh(db_session, app)
    assert (item.status, item.sub_status) == ("offer", "conditional_offer")
    assert f"Offer condition added: Final transcript (owner Agent, due {DUE})." in await history_notes(db_session, app)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.offer_condition"))
    assert audit.metadata_json == {"offer_id": offer["id"], "condition_id": condition["id"], "action": "added", "status": "open"}
    assert "Offer condition updated" in [n.title for n in await notices(db_session, world["staff"]["user"])]


@pytest.mark.asyncio
async def test_met_needs_this_applications_condition_evidence(db_session, world):  # AC2, C2, C11
    app = world["direct_app"]
    passport = await mk_doc(db_session, student=world["direct_student"], application=app, document_type="Passport")
    foreign = await mk_doc(db_session, record=world["record"], application=world["app"], document_type="Condition evidence")
    async with client_for(world["counselor"].email) as c:
        offer = await _offer(c, app, world["direct_letter"])
        [seeded] = offer["condition_items"]
        url = CONDITION.format(app.id, offer["id"], seeded["id"])
        r = await c.patch(url, json={"status": "met"})
        assert r.status_code == 422 and r.json()["detail"] == "Attach the evidence before marking the condition met"
        for document in (passport, foreign):
            r = await c.patch(url, json={"status": "met", "evidence_document_id": str(document.id)})
            assert r.status_code == 422 and r.json()["detail"] == "Choose condition evidence uploaded for this application"
        evidence = await _evidence(c, app)
        r = await c.patch(url, json={"status": "met", "evidence_document_id": evidence["id"]})
        again = await c.patch(url, json={"status": "met", "evidence_document_id": evidence["id"]})
        listed = (await c.get(OFFERS.format(app.id))).json()
    assert r.status_code == 200, r.text
    assert r.json()["condition"]["status"] == "met" and r.json()["condition"]["evidence"] == evidence and r.json()["changed"] is True
    assert again.status_code == 200 and again.json()["changed"] is False
    assert r.json()["conditions_summary"] == {"total": 1, "satisfied": 1, "open": 0, "failed": 0, "all_satisfied": True}  # C4
    assert [d["id"] for d in listed["evidence_documents"]] == [evidence["id"]] and "file_url" not in str(listed)
    [row] = await _rows(db_session, offer["id"])
    assert row.status_changed_at is not None and row.updated_by_id == world["counselor"].id
    assert "Offer condition updated: IELTS 6.5 overall -- Met." in await history_notes(db_session, app)
    assert "Offer condition updated" in [n.title for n in await notices(db_session, world["direct_student"])]


@pytest.mark.asyncio
async def test_waived_and_failed_need_a_note_and_failed_blocks_all_satisfied(db_session, world):  # AC3, AC7, C5
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        offer = await _offer(c, app, world["direct_letter"])
        [seeded] = offer["condition_items"]
        second = (await c.post(CONDITIONS.format(app.id, offer["id"]), json={"description": "Pay deposit", "owner": "student"})).json()["condition"]
        for status in ("waived", "failed"):
            r = await c.patch(CONDITION.format(app.id, offer["id"], seeded["id"]), json={"status": status})
            assert r.status_code == 422 and r.json()["detail"] == "Give a note when a condition is waived or failed", status
        waived = await c.patch(CONDITION.format(app.id, offer["id"], seeded["id"]), json={"status": "waived", "note": "University waived IELTS"})
        failed = await c.patch(CONDITION.format(app.id, offer["id"], second["id"]), json={"status": "failed", "note": "Missed"})
    assert waived.status_code == 200 and failed.status_code == 200, failed.text
    assert failed.json()["conditions_summary"] == {"total": 2, "satisfied": 1, "open": 0, "failed": 1, "all_satisfied": False}


@pytest.mark.asyncio
async def test_an_agent_owner_needs_an_agency_application_and_validation_is_422(db_session, world):  # AC4, C6
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        offer = await _offer(c, app, world["direct_letter"])
        url = CONDITIONS.format(app.id, offer["id"])
        r = await c.post(url, json={"description": "Transcript", "owner": "agent"})
        assert r.status_code == 422 and r.json()["detail"] == "Only an agency application can have a condition owned by the agent"
        assert (await c.post(url, json={"description": "  ", "owner": "student"})).status_code == 422
        assert (await c.post(url, json={"description": "x", "owner": "university"})).status_code == 422
        assert (await c.post(url, json={"description": "x", "owner": "student", "status": "met"})).status_code == 422  # extra key
    assert len(await _rows(db_session, offer["id"])) == 1


@pytest.mark.asyncio
async def test_a_superseded_offers_conditions_stay_and_are_read_only(db_session, world):  # AC5, AC6, C3
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        first = await _offer(c, app, world["direct_letter"])
        second = await _offer(c, app, world["direct_letter"], conditions="IELTS 7.0 overall")
        [old] = first["condition_items"]
        r = await c.patch(CONDITION.format(app.id, first["id"], old["id"]), json={"description": "Edited"})
        assert r.status_code == 409 and r.json()["detail"] == "Conditions can be changed only on the current offer"
        assert (await c.post(CONDITIONS.format(app.id, first["id"]), json={"description": "x", "owner": "student"})).status_code == 409
        assert (await c.patch(CONDITION.format(app.id, second["id"], old["id"]), json={"description": "x"})).status_code == 404
        listed = (await c.get(OFFERS.format(app.id))).json()["offers"]
    assert [[i["description"] for i in o["condition_items"]] for o in listed] == [["IELTS 7.0 overall"], ["IELTS 6.5 overall"]]


@pytest.mark.asyncio
async def test_a_closed_offer_refuses_condition_writes_and_another_applications_offer_is_404(db_session, world):  # AC5
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        offer = await _offer(c, app, world["direct_letter"])
        agency = await _offer(c, world["app"], world["agency_letter"])
        assert (await c.post(CONDITIONS.format(app.id, agency["id"]), json={"description": "x", "owner": "student"})).status_code == 404
        assert (await c.post(WITHDRAW.format(app.id, offer["id"]), json={"status": "expired", "reason": "Lapsed"})).status_code == 200
        r = await c.post(CONDITIONS.format(app.id, offer["id"]), json={"description": "x", "owner": "student"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_the_agency_put_seeds_and_the_deadline_patch_moves_the_conditions(db_session, world):  # AC6, C1, C9
    app = world["app"]
    async with client_for(world["staff"]["user"].email) as c:
        assert (await c.put(offer_url(app.id), json=offer_body(offer_document_id=world["agency_letter"].id))).status_code == 200
    async with client_for(world["counselor"].email) as c:
        [first] = (await c.get(OFFERS.format(app.id))).json()["offers"]
        [seeded] = first["condition_items"]
        assert (await c.post(CONDITIONS.format(app.id, first["id"]), json={"description": "Pay deposit", "owner": "student"})).status_code == 201
    async with client_for(world["staff"]["user"].email) as c:
        r = await c.patch(f"{APPS}/{app.id}", json={"offer_deadline": (date.today() + timedelta(days=60)).isoformat()})
        assert r.status_code == 200, r.text
        listed = (await c.get(OFFERS.format(app.id))).json()["offers"]  # the agency reads conditions
    assert seeded["owner"] == "student" and seeded["description"] == "IELTS 6.5 overall"
    new, old = listed
    assert (new["status"], old["status"]) == ("active", "superseded")
    assert sorted(i["description"] for i in new["condition_items"]) == ["IELTS 6.5 overall", "Pay deposit"] and old["condition_items"] == []


@pytest.mark.asyncio
async def test_on_hold_allows_condition_writes_and_a_terminal_outcome_refuses_them(db_session, world):  # AC9, C8
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        offer = await _offer(c, app, world["direct_letter"])
    item = await fresh(db_session, app)
    item.outcome = "on_hold"
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(CONDITIONS.format(app.id, offer["id"]), json={"description": "Visa letter", "owner": "counselor"})).status_code == 201
    item.outcome = "rejected"
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(CONDITIONS.format(app.id, offer["id"]), json={"description": "x", "owner": "counselor"})).status_code == 409


@pytest.mark.asyncio
async def test_scope_readers_see_conditions_but_cannot_write(db_session, world):  # AC8
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        offer = await _offer(c, app, world["direct_letter"])
    [seeded] = offer["condition_items"]
    async with client_for(world["direct_student"].email) as c:
        got = (await c.get(OFFERS.format(app.id))).json()
        assert got["offers"][0]["condition_items"][0]["id"] == seeded["id"] and got["evidence_documents"] == []
        assert (await c.post(CONDITIONS.format(app.id, offer["id"]), json={"description": "x", "owner": "student"})).status_code == 403
        assert (await c.patch(CONDITION.format(app.id, offer["id"], seeded["id"]), json={"description": "x"})).status_code == 403
        assert (await c.post(EVIDENCE.format(app.id), files={"file": ("a.pdf", PDF, "application/pdf")})).status_code == 403
    async with client_for(world["counselor2"].email) as c:
        assert (await c.post(CONDITIONS.format(app.id, offer["id"]), json={"description": "x", "owner": "student"})).status_code == 403
    async with client_for(world["admin"].email) as c:
        r = await c.patch(CONDITION.format(app.id, offer["id"], seeded["id"]), json={"description": "IELTS 6.5, no band below 6.0", "due_date": DUE})
    assert r.status_code == 200 and r.json()["condition"]["due_date"] == DUE
