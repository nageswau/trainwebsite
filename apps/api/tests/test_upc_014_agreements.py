"""upc-014 -- MoU / agreement management (spec §1-§5; AC1-AC4, P1, N1, E1, S1, R1; DEC-SCOPE-140 AG1-AG18)."""

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, Country, OverseasCourse, University, UniversityAgreement, UniversityStageHistory
from app.services.bdm_travel import india_today
from tests.test_upc_026_documents import _owned, add
from tests.upc003_helpers import as_role, catalogue_country, create, login, url

MENU = "/api/v1/partnership/agreements"
SIGNATORIES = "/api/v1/partnership/agreement-signatories"


def ag_url(agreement_id, tail: str = "") -> str:
    return f"{MENU}/{agreement_id}{tail}"


def day(offset: int) -> str:
    return (india_today() + timedelta(days=offset)).isoformat()


async def course(db, university_id, title="MSc Data Science") -> OverseasCourse:
    row = OverseasCourse(university_id=uuid.UUID(str(university_id)), title=title, level="PG", category="Tech", duration="1 year", tuition_fee="GBP 20,000", intake="Sep")
    db.add(row)
    await db.commit()
    return row


async def india(db) -> Country:
    return await db.scalar(select(Country).where(Country.iso2 == "IN"))


def body(**over) -> dict:
    """The backlog's positive scenario: a 3-year exclusive MoU for India."""
    return {"agreement_type": "mou", "start_date": day(-10), "expiry_date": day(3 * 365), "exclusivity": "exclusive"} | over


async def make(client, university_id, **over) -> dict:
    response = await client.post(url(university_id, "agreements"), json=body(**over))
    assert response.status_code == 201, response.text
    return response.json()["agreement"]


async def move(client, agreement: dict, to: str, **extra):
    return await client.post(ag_url(agreement["id"], "/status"), json={"from_status": agreement["status"], "to_status": to, **extra})


async def moved(client, agreement: dict, to: str) -> dict:
    response = await move(client, agreement, to)
    assert response.status_code == 200, response.text
    return response.json()["agreement"]


async def signing_fields(client, uni_id, signer_id, kind="mou") -> dict:
    doc = await add(client, uni_id, kind=kind, title=f"Signed {kind} {uuid.uuid4().hex[:6]}")
    return {
        "document_id": doc["id"], "edusphere_signatory_user_id": str(signer_id), "edusphere_signed_on": day(-1),
        "university_signatory_name": "Prof. A. Registrar", "university_signed_on": day(-2),
    }  # fmt: skip


async def signed(client, head, pm, uni_id, **over) -> dict:
    """pm drafts, sends and puts it under review; the head approves; pm records the signing fields and signs."""
    a = await make(client, uni_id, **over)
    for to in ("sent", "under_review"):
        a = await moved(client, a, to)
    await login(client, head)
    a = await moved(client, a, "approved")
    await login(client, pm)
    response = await client.patch(ag_url(a["id"]), json=await signing_fields(client, uni_id, pm.id, a["agreement_type"]))
    assert response.status_code == 200, response.text
    return await moved(client, response.json()["agreement"], "signed")


# --- AC1 + P1: the 17 fields --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_seventeen_fields_are_stored_and_returned(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    c1, c2 = await course(db_session, uni["id"]), await course(db_session, uni["id"], "MBA")
    country = await india(db_session)
    values = body(
        renewal_date=day(3 * 365 - 90), commercial_terms="Standard recruitment partnership", territory="India (all states)",
        recruitment_rights="Exclusive recruitment of Indian UG and PG students", course_ids=[str(c1.id), str(c2.id)],
        country_ids=[str(country.id)], payment_terms="Net 30 after census date", marketing_rights="Co-branded fairs and webinars",
    )  # fmt: skip
    response = await client.post(url(uni["id"], "agreements"), json=values)
    assert response.status_code == 201, response.text
    a = response.json()["agreement"]
    assert re.fullmatch(r"MOU-\d{6}", a["mou_number"])
    assert a["university"]["id"] == uni["id"] and a["status"] == "draft" and a["effective_status"] == "draft"
    for key in ("agreement_type", "start_date", "expiry_date", "renewal_date", "commercial_terms", "exclusivity", "territory", "recruitment_rights", "payment_terms", "marketing_rights"):
        assert a[key] == values[key], key
    assert a["all_courses"] is False and {c["id"] for c in a["courses"]} == {str(c1.id), str(c2.id)}
    assert a["countries"] == [{"id": str(country.id), "name": country.name}]
    for key in ("document", "edusphere_signatory", "edusphere_signed_on", "university_signatory_name", "university_signed_on", "previous", "renewed_by"):
        assert a[key] is None, key
    assert a["created_by"]["id"] == str(pm.id) and [e["kind"] for e in a["events"]] == ["create"]
    listed = (await client.get(url(uni["id"], "agreements"))).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == a["id"]
    assert (await client.get(ag_url(a["id"]))).json()["agreement"]["mou_number"] == a["mou_number"]


@pytest.mark.asyncio
async def test_all_courses_and_numbers_are_unique(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    a, b = await make(client, uni["id"], all_courses=True), await make(client, uni["id"])
    assert a["all_courses"] is True and a["courses"] == [] and a["mou_number"] != b["mou_number"]


# --- N1 + AG12: validation ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_invalid_values_are_422(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    foreign = await course(db_session, (await create_owned(client, db_session, head, pm))["id"])
    own = await course(db_session, uni["id"])
    post = lambda **over: client.post(url(uni["id"], "agreements"), json=body(**over))  # noqa: E731
    assert (await post(start_date=day(10), expiry_date=day(5))).status_code == 422  # the backlog's negative scenario
    assert (await post(start_date=day(10), expiry_date=day(10))).status_code == 422
    assert (await post(renewal_date=day(4 * 365))).status_code == 422
    assert (await post(agreement_type="lease")).status_code == 422
    assert (await post(exclusivity="partly")).status_code == 422
    assert (await post(course_ids=[str(foreign.id)])).status_code == 422
    assert (await post(all_courses=True, course_ids=[str(own.id)])).status_code == 422
    assert (await post(country_ids=[str(uuid.uuid4())])).status_code == 422
    assert (await post(territory="x" * 501)).status_code == 422
    assert (await post(unexpected="field")).status_code == 422
    assert (await post(status="signed")).status_code == 422  # status only through the commands


# --- AG5 / AG6 / AC2 / S1: the flow ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_head_approves_and_signing_needs_the_document_and_both_signatories(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    a = await make(client, uni["id"])
    assert (await move(client, a, "signed")).status_code == 409  # not a step of the flow
    a = await moved(client, a, "sent")
    a = await moved(client, a, "under_review")
    a = await moved(client, a, "negotiation")
    a = await moved(client, a, "under_review")
    refused = await move(client, a, "approved")
    assert refused.status_code == 403  # AG6: only the head approves
    await login(client, head)
    a = await moved(client, a, "approved")
    await login(client, pm)
    missing = await move(client, a, "signed")
    assert missing.status_code == 422 and "document" in missing.text.lower()  # AC2
    fields = await signing_fields(client, uni["id"], pm.id)
    for key in fields:
        partial = fields | {key: None}  # everything but this one
        response = await client.patch(ag_url(a["id"]), json=partial)
        assert response.status_code == 200, response.text
        assert (await move(client, response.json()["agreement"], "signed")).status_code == 422, key
        await client.patch(ag_url(a["id"]), json={key: fields[key]})
    a = (await client.get(ag_url(a["id"]))).json()["agreement"]
    a = await moved(client, a, "signed")
    assert a["document"]["id"] == fields["document_id"] and a["edusphere_signatory"]["id"] == str(pm.id)
    assert a["university_signatory_name"] == "Prof. A. Registrar"
    a = await moved(client, a, "active")
    assert a["status"] == "active" and a["effective_status"] == "active"
    assert [e["to_status"] for e in a["events"] if e["kind"] == "status"] == ["sent", "under_review", "negotiation", "under_review", "approved", "signed", "active"]
    # S1: the university moved to Agreement Signed, once, with a history row
    detail = (await client.get(url(uni["id"]))).json()["university"]
    assert detail["stage"] == "agreement_signed"
    rows = (await db_session.scalars(select(UniversityStageHistory).where(UniversityStageHistory.university_id == uuid.UUID(uni["id"])))).all()
    assert [(r.kind, r.to_stage) for r in rows] == [("move", "agreement_signed")] and a["mou_number"] in rows[0].note


@pytest.mark.asyncio
async def test_the_document_must_be_this_universitys_and_of_the_agreement_type(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    a = await make(client, uni["id"], agreement_type="partnership_agreement")
    wrong_kind = await add(client, uni["id"], kind="mou", title="An MoU")
    assert (await client.patch(ag_url(a["id"]), json={"document_id": wrong_kind["id"]})).status_code == 422
    assert (await client.patch(ag_url(a["id"]), json={"document_id": str(uuid.uuid4())})).status_code == 422
    other_uni = await create_owned(client, db_session, head, pm)
    foreign = await add(client, other_uni["id"], kind="partnership_agreement", title="Their agreement")
    assert (await client.patch(ag_url(a["id"]), json={"document_id": foreign["id"]})).status_code == 422
    student = await as_role(client, db_session, "student", "overseas")
    await login(client, pm)
    assert (await client.patch(ag_url(a["id"]), json={"edusphere_signatory_user_id": str(student.id)})).status_code == 422
    assert (await client.patch(ag_url(a["id"]), json={"edusphere_signed_on": day(1)})).status_code == 422  # not in the future


async def create_owned(client, db, head, pm) -> dict:
    await login(client, head)
    uni = await create(client, (await catalogue_country(db)).id)
    assert (await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})).status_code == 200
    await login(client, pm)
    return uni


@pytest.mark.asyncio
async def test_signing_never_moves_the_stage_backwards_and_a_lost_university_cannot_sign(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    uni_id = uuid.UUID(uni["id"])
    await db_session.execute(update(University).where(University.id == uni_id).values(stage="active_partner"))
    await db_session.commit()
    await signed(client, head, pm, uni["id"])
    assert (await client.get(url(uni["id"]))).json()["university"]["stage"] == "active_partner"
    other = await create_owned(client, db_session, head, pm)
    a = await make(client, other["id"])
    for to in ("sent", "under_review"):
        a = await moved(client, a, to)
    await login(client, head)
    a = await moved(client, a, "approved")
    await login(client, pm)
    a = (await client.patch(ag_url(a["id"]), json=await signing_fields(client, other["id"], pm.id))).json()["agreement"]
    await db_session.execute(update(University).where(University.id == uuid.UUID(other["id"])).values(lost_at=datetime.now(UTC), lost_reason="Went elsewhere"))
    await db_session.commit()
    assert (await move(client, a, "signed")).status_code == 409


@pytest.mark.asyncio
async def test_a_stale_from_status_is_409_and_editing_freezes(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    a = await make(client, uni["id"])
    await moved(client, a, "sent")
    stale = await move(client, a, "sent")  # from_status is still "draft"
    assert stale.status_code == 409
    sent = (await client.get(ag_url(a["id"]))).json()["agreement"]
    assert (await client.patch(ag_url(a["id"]), json={"territory": "South India"})).status_code == 200
    same = await client.patch(ag_url(a["id"]), json={"territory": "South India"})
    assert len(same.json()["agreement"]["events"]) == len(sent["events"]) + 1  # an equal value is not a change
    s = await signed(client, head, pm, uni["id"])
    assert (await client.patch(ag_url(s["id"]), json={"territory": "All India"})).status_code == 409
    approved = await make(client, uni["id"], agreement_type="partnership_agreement")
    for to in ("sent", "under_review"):
        approved = await moved(client, approved, to)
    await login(client, head)
    approved = await moved(client, approved, "approved")
    await login(client, pm)
    assert (await client.patch(ag_url(approved["id"]), json={"territory": "All India"})).status_code == 409  # AG11: terms frozen
    assert (await client.patch(ag_url(approved["id"]), json={"university_signatory_name": "Dean"})).status_code == 200


# --- AC3: Expiring / Expired are derived ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_expiring_and_expired_appear_automatically(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    a = await signed(client, head, pm, uni["id"], start_date=day(-700), expiry_date=day(30))
    assert a["status"] == "signed" and a["effective_status"] == "expiring" and a["days_to_expiry"] == 30
    filtered = (await client.get(MENU, params={"status": "expiring", "q": a["mou_number"]})).json()
    assert [i["id"] for i in filtered["items"]] == [a["id"]]
    aid = uuid.UUID(a["id"])
    for expiry, expected in (
        (india_today() + timedelta(days=91), "signed"),
        (india_today() + timedelta(days=90), "expiring"),
        (india_today(), "expiring"),
        (india_today() - timedelta(days=1), "expired"),
    ):
        await db_session.execute(update(UniversityAgreement).where(UniversityAgreement.id == aid).values(expiry_date=expiry))
        await db_session.commit()
        got = (await client.get(ag_url(a["id"]))).json()["agreement"]
        assert got["effective_status"] == expected, expiry
        listed = (await client.get(MENU, params={"status": expected, "q": a["mou_number"]})).json()
        assert listed["total"] == 1, expected
    draft = await make(client, uni["id"], agreement_type="commission_agreement", start_date=day(-400), expiry_date=day(10))
    assert draft["effective_status"] == "draft"  # only a signed or active agreement expires


# --- AC4: renewal ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_renewal_links_the_old_and_new_rows(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    old = await signed(client, head, pm, uni["id"], start_date=day(-1000), expiry_date=day(20), territory="India", all_courses=True)
    draft = await make(client, uni["id"], agreement_type="partnership_agreement")
    assert (await client.post(ag_url(draft["id"], "/renew"), json={"start_date": day(21), "expiry_date": day(1100)})).status_code == 409
    assert (await client.post(ag_url(old["id"], "/renew"), json={"start_date": day(21), "expiry_date": day(20)})).status_code == 422
    response = await client.post(ag_url(old["id"], "/renew"), json={"start_date": day(21), "expiry_date": day(1100)})
    assert response.status_code == 201, response.text
    new = response.json()["agreement"]
    assert new["status"] == "draft" and new["mou_number"] != old["mou_number"]
    assert new["previous"]["id"] == old["id"] and new["territory"] == "India" and new["all_courses"] is True and new["document"] is None
    old_now = (await client.get(ag_url(old["id"]))).json()["agreement"]
    assert old_now["renewed_by"]["id"] == new["id"] and old_now["status"] == "signed"  # stays in force until the renewal is signed
    assert (await client.post(ag_url(old["id"], "/renew"), json={"start_date": day(21), "expiry_date": day(1100)})).status_code == 409
    for to in ("sent", "under_review"):
        new = await moved(client, new, to)
    await login(client, head)
    new = await moved(client, new, "approved")
    await login(client, pm)
    new = (await client.patch(ag_url(new["id"]), json=await signing_fields(client, uni["id"], pm.id))).json()["agreement"]
    new = await moved(client, new, "signed")
    old_now = (await client.get(ag_url(old["id"]))).json()["agreement"]
    assert old_now["status"] == "renewed" and old_now["effective_status"] == "renewed"
    assert old_now["events"][-1]["to_status"] == "renewed" and new["mou_number"] in old_now["events"][-1]["note"]


# --- E1: overlapping agreements ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overlapping_active_agreements_of_the_same_type_are_409(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    await signed(client, head, pm, uni["id"], start_date=day(-10), expiry_date=day(365))
    second = await make(client, uni["id"], start_date=day(100), expiry_date=day(800))
    for to in ("sent", "under_review"):
        second = await moved(client, second, to)
    await login(client, head)
    second = await moved(client, second, "approved")
    await login(client, pm)
    second = (await client.patch(ag_url(second["id"]), json=await signing_fields(client, uni["id"], pm.id))).json()["agreement"]
    clash = await move(client, second, "signed")
    assert clash.status_code == 409 and "overlap" in clash.text.lower()
    await signed(client, head, pm, uni["id"], agreement_type="partnership_agreement", start_date=day(-10), expiry_date=day(365))  # other type


# --- R1: access ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_who_reads_and_who_writes(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    a = await make(client, uni["id"])
    detail = (await client.get(url(uni["id"]))).json()["university"]["permissions"]
    assert detail["can_manage_agreements"] is True and detail["can_approve_agreements"] is False
    await login(client, other)
    assert (await client.get(url(uni["id"], "agreements"))).status_code == 200  # every manager reads every university (AG13)
    assert (await client.get(ag_url(a["id"]))).status_code == 200
    assert (await client.post(url(uni["id"], "agreements"), json=body())).status_code == 403
    assert (await client.patch(ag_url(a["id"]), json={"territory": "x"})).status_code == 403
    assert (await move(client, a, "sent")).status_code == 403
    assert (await client.get(url(uni["id"], "agreement-options"))).status_code == 403
    for role, division in (("overseas_admin", "overseas"), ("counselor", "overseas"), ("agent", "overseas")):
        await as_role(client, db_session, role, division)
        assert (await client.get(url(uni["id"], "agreements"))).status_code == 403, role
        assert (await client.get(MENU)).status_code == 403, role
        assert (await client.get(ag_url(a["id"]))).status_code == 403, role
    await login(client, head)
    assert (await client.get(url(uni["id"]))).json()["university"]["permissions"]["can_approve_agreements"] is True
    assert (await client.get(url(uuid.uuid4(), "agreements"))).status_code == 404
    assert (await client.get(ag_url(uuid.uuid4()))).status_code == 404
    await db_session.execute(update(University).where(University.id == uuid.UUID(uni["id"])).values(active=False))
    await db_session.commit()
    await login(client, pm)
    assert (await client.post(url(uni["id"], "agreements"), json=body())).status_code == 409
    assert (await move(client, a, "sent")).status_code == 409
    assert (await client.get(url(uni["id"], "agreements"))).status_code == 200


@pytest.mark.asyncio
async def test_options_list_the_universitys_courses_and_agreement_documents(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    c = await course(db_session, uni["id"])
    mou = await add(client, uni["id"], kind="mou", title="MoU 2026")
    await add(client, uni["id"], kind="brochure", title="Brochure")
    options = (await client.get(url(uni["id"], "agreement-options"))).json()
    assert options == {
        "courses": [{"id": str(c.id), "title": c.title, "level": "PG"}],
        "documents": [{"id": mou["id"], "kind": "mou", "title": "MoU 2026", "current_version": 1}],
    }


@pytest.mark.asyncio
async def test_signatories_are_searched_among_active_partnership_staff(client, db_session):
    head, pm, _, _ = await _owned(client, db_session)
    found = (await client.get(SIGNATORIES, params={"q": pm.email})).json()
    assert [i["id"] for i in found["items"]] == [str(pm.id)] and set(found["items"][0]) == {"id", "label", "detail"}
    assert [i["id"] for i in (await client.get(SIGNATORIES, params={"q": head.email})).json()["items"]] == [str(head.id)]
    student = await as_role(client, db_session, "student", "overseas")
    await login(client, pm)
    assert (await client.get(SIGNATORIES, params={"q": student.email})).json()["items"] == []
    await as_role(client, db_session, "overseas_admin", "overseas")
    assert (await client.get(SIGNATORIES)).status_code == 403


# --- AG17 + AG18: audit and the menu list ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_audit_rows_carry_no_free_text_and_the_menu_lists_and_filters(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    a = await make(client, uni["id"], commercial_terms="Secret 15% margin", territory="Kerala")
    await client.post(ag_url(a["id"], "/status"), json={"from_status": "draft", "to_status": "sent", "note": "Emailed to the dean"})
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == a["id"]))).all()
    assert [r.action for r in rows] == ["university_agreement.create", "university_agreement.status"]
    assert all("Secret" not in str(r.metadata_json) and "dean" not in str(r.metadata_json) for r in rows)
    page = (await client.get(MENU, params={"q": uni["university_code"]})).json()
    assert page["total"] == 1 and page["items"][0]["mou_number"] == a["mou_number"] and "events" not in page["items"][0]
    assert (await client.get(MENU, params={"agreement_type": "partnership_agreement", "q": uni["university_code"]})).json()["total"] == 0
    assert (await client.get(MENU, params={"status": "sent", "q": a["mou_number"]})).json()["total"] == 1
    assert (await client.get(MENU, params={"status": "bogus"})).status_code == 422
