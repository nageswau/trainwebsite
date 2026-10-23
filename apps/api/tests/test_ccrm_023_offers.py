"""ccrm-023 (DEC-SCOPE-245, OF1-OF4) -- offer records with history: the counselor/admin routes, the agency PUT/PATCH writing rows, the
mirror, sub-status (OF3), withdraw (OF4), scope, CC5 notices, and nehn-001's portal predicates (OF1). Agency world: agn023_helpers."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import ApplicationOffer, ApplicationStatusHistory, AuditLog
from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import APPS
from tests.agn009_helpers import PDF, mk_doc
from tests.agn010_helpers import offer_body, offer_url
from tests.agn023_helpers import ASSIGN, PORTAL, assign_world, fresh, notices

BASE = "/api/v1/workflows/overseas/applications/{}"
OFFERS = BASE + "/offers"
LETTERS = BASE + "/offer-letters"
WITHDRAW = OFFERS + "/{}/withdraw"
ISSUED = date.today() - timedelta(days=2)


def body(letter, **overrides) -> dict:
    data = {
        "offer_type": "conditional",
        "issue_date": ISSUED.isoformat(),
        "offer_deadline": (ISSUED + timedelta(days=30)).isoformat(),
        "conditions": "IELTS 6.5 overall",
        "currency": "GBP",
        "tuition_amount": "18500.00",
        "scholarship_amount": "2000",
        "deposit_amount": "3000",
        "deposit_deadline": (ISSUED + timedelta(days=14)).isoformat(),
        "offer_document_id": str(letter.id),
    }
    data.update(overrides)
    return data


@pytest_asyncio.fixture
async def world(db_session):
    w = await assign_world(db_session, status="university_selection")
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    w["direct_letter"] = await mk_doc(db_session, student=w["direct_student"], application=w["direct_app"], document_type="Offer letter")
    w["agency_letter"] = await mk_doc(db_session, record=w["record"], application=w["app"], document_type="Offer letter")
    return w


async def _offers(db, app) -> list[ApplicationOffer]:
    stmt = select(ApplicationOffer).where(ApplicationOffer.application_id == app.id).order_by(ApplicationOffer.created_at, ApplicationOffer.id)
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


async def _history(db, app) -> list[ApplicationStatusHistory]:
    stmt = select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == app.id).order_by(ApplicationStatusHistory.created_at, ApplicationStatusHistory.id)
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


@pytest.mark.asyncio
async def test_the_counselor_records_an_offer_with_a_row_mirror_stage_sub_status_history_audit_and_notice(db_session, world):  # AC1, AC9
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        r = await c.post(OFFERS.format(app.id), json=body(world["direct_letter"]))
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["changed"] is True and data["status"] == "offer" and data["sub_status"] == "conditional_offer"
    offer = data["offer"]
    assert offer["status"] == "active" and offer["offer_type"] == "conditional" and offer["tuition_amount"] == "18500.00"
    assert offer["document"] == {"id": str(world["direct_letter"].id), "name": "Offer letter"}
    assert offer["recorded_by"] == world["counselor"].full_name
    [row] = await _offers(db_session, app)
    assert (row.status, row.recorded_by_id, row.currency) == ("active", world["counselor"].id, "GBP")
    item = await fresh(db_session, app)
    assert (item.status, item.sub_status) == ("offer", "conditional_offer")
    assert (item.offer_type, item.offer_date, item.offer_deadline, item.offer_conditions, item.offer_document_id) == (
        "conditional", ISSUED, ISSUED + timedelta(days=30), "IELTS 6.5 overall", world["direct_letter"].id,
    )  # fmt: skip
    [h] = [h for h in await _history(db_session, app) if h.notes and h.notes.startswith("Offer recorded")]
    assert (h.from_status, h.to_status, h.from_sub_status, h.to_sub_status, h.changed_by_id) == ("university_selection", "offer", None, "conditional_offer", world["counselor"].id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.offer"))
    assert audit.metadata_json["offer_type"] == "conditional" and "IELTS" not in str(audit.metadata_json) and "18500" not in str(audit.metadata_json)
    assert "Offer recorded" in [n.title for n in await notices(db_session, world["direct_student"])]


@pytest.mark.asyncio
@pytest.mark.parametrize(("offer_type", "sub_status"), [("unconditional", "unconditional_offer"), ("pathway", "conditional_offer"), ("other", "conditional_offer")])
async def test_each_type_sets_its_sub_status(db_session, world, offer_type, sub_status):  # OF3
    app = world["direct_app"]
    conditions = None if offer_type == "unconditional" else "Complete the foundation year"
    async with client_for(world["counselor"].email) as c:
        r = await c.post(OFFERS.format(app.id), json=body(world["direct_letter"], offer_type=offer_type, conditions=conditions))
    assert r.status_code == 201, r.text
    item = await fresh(db_session, app)
    assert (item.sub_status, item.offer_type) == (sub_status, offer_type)


@pytest.mark.asyncio
async def test_a_new_offer_supersedes_the_previous_one_and_nothing_is_overwritten(db_session, world):  # AC2
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(OFFERS.format(app.id), json=body(world["direct_letter"]))).status_code == 201
        r = await c.post(OFFERS.format(app.id), json=body(world["direct_letter"], offer_type="unconditional", conditions=None, tuition_amount="17000"))
        assert r.status_code == 201, r.text
        listed = (await c.get(OFFERS.format(app.id))).json()
    first, second = await _offers(db_session, app)
    assert (first.status, first.offer_type, str(first.tuition_amount)) == ("superseded", "conditional", "18500.00")
    assert (second.status, second.offer_type) == ("active", "unconditional")
    item = await fresh(db_session, app)
    assert (item.offer_type, item.offer_conditions, item.sub_status) == ("unconditional", None, "unconditional_offer")
    assert [o["status"] for o in listed["offers"]] == ["active", "superseded"]  # newest first


@pytest.mark.asyncio
async def test_an_identical_retry_writes_nothing(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(OFFERS.format(app.id), json=body(world["direct_letter"]))).status_code == 201
        before = len(await _history(db_session, app))
        r = await c.post(OFFERS.format(app.id), json=body(world["direct_letter"]))
    assert r.status_code == 200 and r.json()["changed"] is False
    assert len(await _offers(db_session, app)) == 1 and len(await _history(db_session, app)) == before


@pytest.mark.asyncio
async def test_the_offer_letter_is_required_and_must_be_this_applications(db_session, world):  # AC3
    app = world["direct_app"]
    passport = await mk_doc(db_session, student=world["direct_student"], application=app, document_type="Passport")
    async with client_for(world["counselor"].email) as c:
        missing = body(world["direct_letter"])
        missing.pop("offer_document_id")
        assert (await c.post(OFFERS.format(app.id), json=missing)).status_code == 422
        r = await c.post(OFFERS.format(app.id), json=body(world["agency_letter"]))  # another application's letter
        assert r.status_code == 422 and r.json()["detail"] == "Choose an offer letter uploaded for this application"
        assert (await c.post(OFFERS.format(app.id), json=body(passport))).status_code == 422
    assert await _offers(db_session, app) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"currency": None}, "Choose the currency of the amounts"),
        ({"offer_deadline": (ISSUED - timedelta(days=1)).isoformat()}, "Offer deadline cannot be before the issue date"),
        ({"deposit_deadline": (ISSUED - timedelta(days=1)).isoformat()}, "Deposit deadline cannot be before the issue date"),
        ({"issue_date": (date.today() + timedelta(days=5)).isoformat()}, "Issue date cannot be in the future"),
        ({"conditions": None}, "A conditional offer needs its conditions"),
        ({"offer_type": "unconditional"}, "An unconditional offer has no conditions"),
        ({"tuition_amount": "-1"}, None),
        ({"currency": "pounds"}, None),
        ({"offer_type": "maybe"}, None),
        ({"surprise": 1}, None),
    ],
)
async def test_invalid_offers_are_422(db_session, world, overrides, message):
    async with client_for(world["counselor"].email) as c:
        r = await c.post(OFFERS.format(world["direct_app"].id), json=body(world["direct_letter"], **overrides))
    assert r.status_code == 422
    if message:
        assert message in r.text


@pytest.mark.asyncio
async def test_currency_is_optional_without_amounts_and_upper_cased(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        bare = body(world["direct_letter"], currency=None, tuition_amount=None, scholarship_amount=None, deposit_amount=None)
        assert (await c.post(OFFERS.format(app.id), json=bare)).status_code == 201
        r = await c.post(OFFERS.format(app.id), json=body(world["direct_letter"], currency="usd"))
    assert r.status_code == 201 and r.json()["offer"]["currency"] == "USD"


@pytest.mark.asyncio
async def test_a_later_stage_keeps_its_stage_and_sub_status(db_session, world):
    app = await fresh(db_session, world["direct_app"])
    app.status = "visa_documentation"
    app.sub_status = "visa_applied"
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(OFFERS.format(app.id), json=body(world["direct_letter"]))).status_code == 201
    item = await fresh(db_session, app)
    assert (item.status, item.sub_status, item.offer_type) == ("visa_documentation", "visa_applied", "conditional")


@pytest.mark.asyncio
async def test_on_an_agency_application_the_counselor_records_and_the_agency_is_told(db_session, world):  # CC4, CC5
    app = world["app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(OFFERS.format(app.id), json=body(world["agency_letter"]))).status_code == 201
    assert "Offer recorded" in [n.title for n in await notices(db_session, world["staff"]["user"])]
    async with client_for(world["staff"]["user"].email) as c:
        detail = (await c.get(f"{APPS}/{app.id}")).json()["application"]
    assert detail["offer"]["type"] == "conditional" and detail["sub_status"] == "conditional_offer"  # the mirror keeps agency reads working


@pytest.mark.asyncio
async def test_the_agency_put_writes_a_row_sets_the_sub_status_and_tells_the_counselor(db_session, world):  # AC4
    app = world["app"]
    async with client_for(world["staff"]["user"].email) as c:
        r = await c.put(offer_url(app.id), json=offer_body(offer_document_id=world["agency_letter"].id))
        assert r.status_code == 200, r.text
        r = await c.put(offer_url(app.id), json=offer_body(offer_type="unconditional", conditions=None, offer_document_id=world["agency_letter"].id))
        assert r.status_code == 200, r.text
    first, second = await _offers(db_session, app)
    assert (first.status, second.status, second.offer_type, second.recorded_by_id) == ("superseded", "active", "unconditional", world["staff"]["user"].id)
    item = await fresh(db_session, app)
    assert item.sub_status == "unconditional_offer"
    titles = [n.title for n in await notices(db_session, world["counselor"])]
    assert titles.count("Offer recorded") == 2


@pytest.mark.asyncio
async def test_the_agency_patch_of_the_offer_deadline_supersedes_the_active_row(db_session, world):
    app = world["app"]
    new_deadline = date.today() + timedelta(days=60)
    async with client_for(world["staff"]["user"].email) as c:
        assert (await c.put(offer_url(app.id), json=offer_body(offer_document_id=world["agency_letter"].id))).status_code == 200
        r = await c.patch(f"{APPS}/{app.id}", json={"offer_deadline": new_deadline.isoformat()})
        assert r.status_code == 200, r.text
    first, second = await _offers(db_session, app)
    assert (first.status, second.status, second.offer_deadline, second.conditions) == ("superseded", "active", new_deadline, "IELTS 6.5 overall")


@pytest.mark.asyncio
async def test_withdraw_needs_a_reason_clears_the_mirror_keeps_the_stage_and_clears_the_sub_status(db_session, world):  # AC5, OF4
    app = world["app"]
    async with client_for(world["counselor"].email) as c:
        offer_id = (await c.post(OFFERS.format(app.id), json=body(world["agency_letter"]))).json()["offer"]["id"]
        assert (await c.post(WITHDRAW.format(app.id, offer_id), json={"status": "withdrawn_by_university"})).status_code == 422
        assert (await c.post(WITHDRAW.format(app.id, offer_id), json={"status": "superseded", "reason": "x"})).status_code == 422
        r = await c.post(WITHDRAW.format(app.id, offer_id), json={"status": "withdrawn_by_university", "reason": "Course cancelled"})
        assert r.status_code == 200, r.text
        assert r.json()["offer"]["status"] == "withdrawn_by_university"
        again = await c.post(WITHDRAW.format(app.id, offer_id), json={"status": "expired", "reason": "Deadline passed"})
        assert again.status_code == 409
    [row] = await _offers(db_session, app)
    assert (row.status, row.status_reason, row.closed_by_id) == ("withdrawn_by_university", "Course cancelled", world["counselor"].id)
    item = await fresh(db_session, app)
    assert (item.status, item.sub_status, item.offer_type, item.offer_date, item.offer_deadline, item.offer_document_id) == ("offer", None, None, None, None, None)
    last = (await _history(db_session, app))[-1]
    assert (last.from_sub_status, last.to_sub_status) == ("conditional_offer", None) and "Course cancelled" in last.notes
    assert "Offer withdrawn" in [n.title for n in await notices(db_session, world["staff"]["user"])]


@pytest.mark.asyncio
async def test_an_offer_of_another_application_is_404(db_session, world):
    async with client_for(world["counselor"].email) as c:
        offer_id = (await c.post(OFFERS.format(world["app"].id), json=body(world["agency_letter"]))).json()["offer"]["id"]
        r = await c.post(WITHDRAW.format(world["direct_app"].id, offer_id), json={"status": "expired", "reason": "Lapsed"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_scope_and_roles(db_session, world):  # AC6
    app = world["direct_app"]
    rep = await mk_user(db_session, role="university_rep", profile={"university_id": str(world["university"].id)})
    other_student = await mk_user(db_session, role="overseas_student")
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(OFFERS.format(app.id), json=body(world["direct_letter"]))).status_code == 201
    async with client_for(world["counselor2"].email) as c:
        assert (await c.get(OFFERS.format(app.id))).status_code == 403
        assert (await c.post(OFFERS.format(app.id), json=body(world["direct_letter"]))).status_code == 403
    async with client_for(rep.email) as c:
        assert (await c.post(OFFERS.format(app.id), json=body(world["direct_letter"]))).status_code == 403
        assert (await c.get(OFFERS.format(app.id))).status_code == 403
    async with client_for(other_student.email) as c:
        assert (await c.get(OFFERS.format(app.id))).status_code == 403
    async with client_for(world["direct_student"].email) as c:
        own = await c.get(OFFERS.format(app.id))
        assert own.status_code == 200 and len(own.json()["offers"]) == 1 and own.json()["offer_letters"] == []
        assert (await c.post(OFFERS.format(app.id), json=body(world["direct_letter"]))).status_code == 403
    async with client_for(world["admin"].email) as c:
        listed = await c.get(OFFERS.format(app.id))
        assert listed.status_code == 200 and [d["id"] for d in listed.json()["offer_letters"]] == [str(world["direct_letter"].id)]
    assert "file_url" not in listed.text
    async with client_for(world["staff"]["user"].email) as c:  # an agent reads its own agency application's offers
        assert (await c.get(OFFERS.format(world["app"].id))).status_code == 200


@pytest.mark.asyncio
async def test_a_withdrawn_application_is_409(db_session, world):
    app = await fresh(db_session, world["direct_app"])
    app.status = "withdrawn"
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        r = await c.post(OFFERS.format(app.id), json=body(world["direct_letter"]))
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_the_counselor_uploads_an_offer_letter_then_records_with_it(db_session, world):
    app = world["app"]  # agency record: the document is owned like the application
    async with client_for(world["counselor"].email) as c:
        bad = await c.post(LETTERS.format(app.id), files={"file": ("letter.txt", b"hello", "text/plain")})
        assert bad.status_code == 415
        r = await c.post(LETTERS.format(app.id), files={"file": ("offer.pdf", PDF, "application/pdf")})
        assert r.status_code == 201, r.text
        document = r.json()["document"]
        assert set(document) == {"id", "name"}
        assert (await c.post(OFFERS.format(app.id), json=body(world["agency_letter"], offer_document_id=document["id"]))).status_code == 201
    async with client_for(world["counselor2"].email) as c:
        assert (await c.post(LETTERS.format(app.id), files={"file": ("offer.pdf", PDF, "application/pdf")})).status_code == 403
    count = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "document.upload", AuditLog.user_id == world["counselor"].id))
    assert count == 1


# --- nehn-001 (OF1): the portal's offer predicates ---


@pytest.mark.asyncio
async def test_nehn_001_an_offer_stage_application_counts_for_the_student(db_session, world):
    app = await fresh(db_session, world["direct_app"])
    student = world["direct_student"]
    async with client_for(student.email) as c:
        dash = (await c.get(PORTAL.format("student", "dashboard"))).json()
        assert {m["label"]: m["value"] for m in dash["metrics"]}["Offers"] == 0  # university_selection does not count
    for status in ("offer", "visa_documentation", "enrolled", "offer_received"):
        app.status = status
        await db_session.commit()
        async with client_for(student.email) as c:
            dash = (await c.get(PORTAL.format("student", "dashboard"))).json()
            letters = (await c.get(PORTAL.format("student", "offer-letters"))).json()
        assert {m["label"]: m["value"] for m in dash["metrics"]}["Offers"] == 1, status
        assert len(letters["rows"]) == 1, status
    app.status = "withdrawn"  # withdrawn before any offer was recorded
    await db_session.commit()
    async with client_for(student.email) as c:
        dash = (await c.get(PORTAL.format("student", "dashboard"))).json()
    assert {m["label"]: m["value"] for m in dash["metrics"]}["Offers"] == 0


@pytest.mark.asyncio
async def test_nehn_001_the_student_offer_list_shows_the_recorded_type_and_deadline(db_session, world):
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(OFFERS.format(world["direct_app"].id), json=body(world["direct_letter"]))).status_code == 201
    async with client_for(world["direct_student"].email) as c:
        letters = (await c.get(PORTAL.format("student", "offer-letters"))).json()
    [row] = letters["rows"]
    assert row["offer_type"] == "Conditional" and row["offer_deadline"] == (ISSUED + timedelta(days=30)).isoformat()
