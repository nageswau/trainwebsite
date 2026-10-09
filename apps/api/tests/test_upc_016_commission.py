"""upc-016 -- commercial / commission terms, restricted (spec §1-§5; AC1, AC2, P1, N1, E1; DEC-SCOPE-144 CM1-CM15)."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, University, UniversityCommissionTerm
from app.services import university_commission as svc
from app.services.partnership_access import COMMISSION_FIELDS, strip_commission
from tests.test_upc_014_agreements import ag_url, course, create_owned, india, make, moved, signed
from tests.test_upc_026_documents import _owned
from tests.upc003_helpers import as_role, login, url

MENU = "/api/v1/partnership/commission-terms"


def terms_url(agreement_id, term_id=None) -> str:
    return ag_url(agreement_id, "/commission-terms") + (f"/{term_id}" if term_id else "")


def term_body(**over) -> dict:
    """The backlog's positive scenario: 15% on first-year tuition, payable after visa approval + enrolment."""
    return {"commission_percent": "15", "currency": "GBP", "trigger": "visa_and_enrolment", "conditions": "15% of first-year tuition"} | over


async def add_term(client, agreement_id, **over) -> dict:
    response = await client.post(terms_url(agreement_id), json=term_body(**over))
    assert response.status_code == 201, response.text
    return response.json()["term"]


async def drafted(client, db):
    head, pm, other, uni = await _owned(client, db)
    return head, pm, other, uni, await make(client, uni["id"])


# --- strip_commission (CM12) --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("role", ["counselor", "overseas_admin", "bdm", "agent", "university_rep", "overseas_student", "telecaller"])
def test_strip_commission_removes_commission_fields_for_other_roles(role):
    payload = {"id": "a1", "commission_terms": [{"commission_percent": "15.00"}], "mou_number": "MOU-000001"}
    out = strip_commission(SimpleNamespace(role=role), payload)
    assert out == {"id": "a1", "mou_number": "MOU-000001"} and "commission_terms" in payload  # a copy; the input is untouched


@pytest.mark.parametrize("role", ["super_admin", "partnership_manager", "partnership_head"])
def test_strip_commission_keeps_them_for_commission_roles(role):
    payload = {"id": "a1", "commission_terms": []}
    assert strip_commission(SimpleNamespace(role=role), payload) == payload
    assert "commission_terms" in COMMISSION_FIELDS


# --- P1 + AC2: a manager records, reads and edits -------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_records_reads_and_edits_a_term(client, db_session):
    _, pm, _, uni, a = await drafted(client, db_session)
    c = await course(db_session, uni["id"])
    country = await india(db_session)
    t = await add_term(client, a["id"], course_ids=[str(c.id)], country_ids=[str(country.id)], payment_timeline="Within 60 days of census", payment_terms="Invoice per intake")
    assert t["commission_percent"] == "15.00" and t["fixed_amount"] is None and t["currency"] == "GBP"
    assert t["trigger"] == "visa_and_enrolment" and t["trigger_label"] == "Visa approval + enrolment"
    assert t["conditions"] == "15% of first-year tuition" and t["payment_timeline"] == "Within 60 days of census" and t["payment_terms"] == "Invoice per intake"
    assert t["courses"] == [{"id": str(c.id), "title": c.title, "level": "PG"}] and t["countries"] == [{"id": str(country.id), "name": country.name}]
    assert t["agreement_id"] == a["id"] and t["created_by"]["id"] == str(pm.id) and t["permissions"] == {"can_edit": True}
    listed = (await client.get(terms_url(a["id"]))).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == t["id"] and listed["limit"] == 50 and listed["offset"] == 0
    response = await client.patch(terms_url(a["id"], t["id"]), json={"commission_percent": None, "fixed_amount": "1500.50", "currency": "USD", "course_ids": []})
    assert response.status_code == 200, response.text
    edited = response.json()["term"]
    assert edited["commission_percent"] is None and edited["fixed_amount"] == "1500.50" and edited["currency"] == "USD" and edited["courses"] == []
    agreement = (await client.get(ag_url(a["id"]))).json()["agreement"]
    assert [x["id"] for x in agreement["commission_terms"]] == [t["id"]]  # the agreement carries its terms for commission roles
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == t["id"]).order_by(AuditLog.created_at))).all()
    assert [r.action for r in audit] == ["university_commission_term.create", "university_commission_term.update"]
    assert "1500" not in str(audit[1].metadata_json) and set(audit[1].metadata_json["fields"]) == {"commission_percent", "fixed_amount", "currency", "course_ids"}


# --- N1 + E1 + CM2/CM3/CM5/CM6: validation ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_invalid_values_are_422(client, db_session):
    head, pm, _, _, a = await drafted(client, db_session)
    foreign = await course(db_session, (await create_owned(client, db_session, head, pm))["id"])
    post = lambda **over: client.post(terms_url(a["id"]), json=term_body(**over))  # noqa: E731
    assert (await post(commission_percent="100.01")).status_code == 422  # the backlog's negative scenario
    assert (await post(commission_percent="0")).status_code == 422
    assert (await post(commission_percent="12.345")).status_code == 422
    assert (await post(fixed_amount="1500")).status_code == 422  # E1: both set
    assert (await post(commission_percent=None)).status_code == 422  # neither set
    assert (await post(commission_percent=None, fixed_amount="0")).status_code == 422
    assert (await post(currency="AED")).status_code == 422
    assert (await post(trigger="application")).status_code == 422
    assert (await post(course_ids=[str(foreign.id)])).status_code == 422  # programmes of the agreement's university only
    assert (await post(country_ids=[str(uuid.uuid4())])).status_code == 422
    assert (await post(payment_timeline="x" * 501)).status_code == 422
    assert (await post(conditions="x" * 2001)).status_code == 422
    assert (await post(surprise=1)).status_code == 422
    assert (await post(commission_percent="100")).status_code == 201
    t = (await client.get(terms_url(a["id"]))).json()["items"][0]
    assert (await client.patch(terms_url(a["id"], t["id"]), json={"fixed_amount": "10"})).status_code == 422  # would hold both
    assert (await client.patch(terms_url(a["id"], t["id"]), json={"currency": None})).status_code == 422


# --- AC1 + N1 + CM7: nobody else reads ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_other_roles_get_no_commission_anywhere(client, db_session):
    head, pm, other, uni, a = await drafted(client, db_session)
    t = await add_term(client, a["id"])
    for role, division in (("overseas_admin", "overseas"), ("counselor", "overseas"), ("bdm", "overseas"), ("agent", "overseas"), ("university_rep", "overseas")):
        await as_role(client, db_session, role, division)
        assert (await client.get(terms_url(a["id"]))).status_code == 403, role
        assert (await client.get(MENU)).status_code == 403, role
        assert (await client.post(terms_url(a["id"]), json=term_body())).status_code == 403, role
        assert (await client.patch(terms_url(a["id"], t["id"]), json={"currency": "USD"})).status_code == 403, role
        assert (await client.delete(terms_url(a["id"], t["id"]))).status_code == 403, role
        detail = await client.get(url(uni["id"]))
        assert "commission_percent" not in detail.text and "commission_terms" not in detail.text, role
    client.cookies.clear()
    assert (await client.get(terms_url(a["id"]))).status_code == 401
    assert (await client.get(MENU)).status_code == 401
    await login(client, other)  # every manager reads every agreement's terms (CM7) but writes only their own (CM8)
    assert (await client.get(terms_url(a["id"]))).json()["items"][0]["permissions"] == {"can_edit": False}
    assert (await client.post(terms_url(a["id"]), json=term_body())).status_code == 403
    assert (await client.patch(terms_url(a["id"], t["id"]), json={"currency": "USD"})).status_code == 403
    assert (await client.delete(terms_url(a["id"], t["id"]))).status_code == 403
    await login(client, head)
    assert (await client.get(terms_url(a["id"]))).json()["items"][0]["permissions"] == {"can_edit": True}
    assert (await client.get(terms_url(uuid.uuid4()))).status_code == 404
    assert (await client.patch(terms_url(a["id"], uuid.uuid4()), json={"currency": "USD"})).status_code == 404
    other_agreement = await make(client, uni["id"])
    assert (await client.patch(terms_url(other_agreement["id"], t["id"]), json={"currency": "USD"})).status_code == 404  # no IDOR via the URL
    await db_session.execute(update(University).where(University.id == uuid.UUID(uni["id"])).values(active=False))
    await db_session.commit()
    await login(client, pm)
    assert (await client.post(terms_url(a["id"]), json=term_body())).status_code == 409
    assert (await client.get(terms_url(a["id"]))).status_code == 200


# --- CM9 + CM10 + CM11: when terms change ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_terms_freeze_at_approval_and_renewal_copies_them(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    a = await make(client, uni["id"])
    t = await add_term(client, a["id"])
    for to in ("sent", "under_review"):
        a = await moved(client, a, to)
    assert (await client.patch(terms_url(a["id"], t["id"]), json={"currency": "USD"})).status_code == 200  # still negotiable
    await login(client, head)
    a = await moved(client, a, "approved")
    await login(client, pm)
    frozen = await client.post(terms_url(a["id"]), json=term_body())
    assert frozen.status_code == 409 and "renew" in frozen.text.lower()
    assert (await client.patch(terms_url(a["id"], t["id"]), json={"currency": "GBP"})).status_code == 409
    assert (await client.delete(terms_url(a["id"], t["id"]))).status_code == 409
    assert (await client.get(terms_url(a["id"]))).json()["items"][0]["permissions"] == {"can_edit": False}

    s = await signed(client, head, pm, uni["id"], start_date="2026-01-01", expiry_date="2027-01-01", agreement_type="commission_agreement")
    await login(client, head)
    original = await client.get(terms_url(s["id"]))
    assert original.json()["total"] == 0
    # terms of a signed agreement can only arrive by renewal; seed one on the signed row directly to prove the copy
    seeded = {"fixed_amount": 2000, "currency": "AUD", "trigger": "tuition_paid", "course_ids": [], "country_ids": []}
    db_session.add(UniversityCommissionTerm(agreement_id=uuid.UUID(s["id"]), created_by_user_id=pm.id, updated_by_user_id=pm.id, **seeded))
    await db_session.commit()
    await login(client, pm)
    response = await client.post(ag_url(s["id"], "/renew"), json={"start_date": "2027-01-02", "expiry_date": "2028-01-02"})
    assert response.status_code == 201, response.text
    renewal = response.json()["agreement"]
    copied = renewal["commission_terms"]
    assert len(copied) == 1 and copied[0]["fixed_amount"] == "2000.00" and copied[0]["currency"] == "AUD" and copied[0]["trigger"] == "tuition_paid"
    assert copied[0]["permissions"] == {"can_edit": True}  # the renewal is a draft


@pytest.mark.asyncio
async def test_delete_and_the_cap(client, db_session):
    _, _, _, _, a = await drafted(client, db_session)
    t = await add_term(client, a["id"])
    response = await client.delete(terms_url(a["id"], t["id"]))
    assert response.status_code == 204
    assert (await client.get(terms_url(a["id"]))).json()["total"] == 0
    assert (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == t["id"]))).all()[-1] == "university_commission_term.delete"
    for _ in range(svc.MAX_TERMS):
        await add_term(client, a["id"])
    capped = await client.post(terms_url(a["id"]), json=term_body())
    assert capped.status_code == 409


# --- CM14: the menu list --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_menu_lists_every_term_with_filters(client, db_session):
    _, _, _, uni, a = await drafted(client, db_session)
    marker = f"Menu{uuid.uuid4().hex[:6]}"
    await add_term(client, a["id"], trigger="enrolment", currency="CAD")
    await add_term(client, a["id"], commission_percent=None, fixed_amount="900", trigger="tuition_paid", currency="CAD")
    page = (await client.get(MENU, params={"q": a["mou_number"]})).json()
    assert page["total"] == 2 and {i["agreement"]["mou_number"] for i in page["items"]} == {a["mou_number"]}
    item = page["items"][0]
    assert item["university"] == {"id": uni["id"], "name": uni["name"], "university_code": uni["university_code"]}
    assert item["agreement"]["effective_status"] == "draft" and item["agreement"]["status_label"] == "Draft"
    assert (await client.get(MENU, params={"q": a["mou_number"], "trigger": "tuition_paid"})).json()["total"] == 1
    assert (await client.get(MENU, params={"q": a["mou_number"], "currency": "GBP"})).json()["total"] == 0
    assert (await client.get(MENU, params={"q": marker})).json()["total"] == 0
    assert (await client.get(MENU, params={"trigger": "nope"})).status_code == 422
