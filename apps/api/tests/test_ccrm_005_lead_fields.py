"""ccrm-005 (DEC-SCOPE-259): the spec §3 lead fields -- contact preference, enquiry date, marketing consent and referral on the lead
(LF1, LF4, LF5) through create, the details edit and the CSV import (LF6); the overseas study, academic and English test answers in the
qualification (LF1, LF3); the counselor's writes on their own leads (LF7) and the conversion carry-over (LF8). The shared test database is
never truncated: every assertion is about rows the test made."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Country, Enquiry, LeadEnglishTest, OverseasStudentEnglishTest, OverseasStudentProfile, OverseasStudentQualification, TelProduct
from app.services.bdm_appointments import today_ist
from tests.tel004_helpers import make_telecaller, make_tl_manager
from tests.tel018_helpers import as_user, c_url, handover, setup
from tests.test_ccrm_008_convert import _capture, _phone
from tests.test_tel_006_import import campaign, csv_bytes, manager_in, recorded, row, upload  # noqa: F401 (fixture)

LEADS = "/api/v1/telecaller/leads"
CONTACT = {"contact_preference": "whatsapp", "enquiry_date": "2026-09-14", "marketing_opt_in": True, "referral_name": "Priya Raman",
           "referral_contact": "priya@example.com"}
IELTS = {"test_type": "IELTS", "status": "taken", "overall_score": 6.5, "test_date": "2024-01-10", "valid_until": "2026-01-10"}


def today() -> date:
    return today_ist(datetime.now(UTC))


def q_url(lead_id, base: str = LEADS) -> str:
    return f"{base}/{lead_id}/qualification"


async def stored(db, lead_id) -> Enquiry:
    return await db.scalar(select(Enquiry).where(Enquiry.id == lead_id).execution_options(populate_existing=True))


async def overseas_product(db) -> TelProduct:
    return await db.scalar(select(TelProduct).where(TelProduct.product_group == "overseas", TelProduct.name == "UK"))


async def country(db) -> Country:
    tag = uuid.uuid4().hex[:8]
    row_ = Country(slug=f"ccrm005-{tag}", name=f"Studyland {tag}", overview="", tuition="", living_expenses="", visa_process=[],
                   work_opportunities="", post_study_work="", pr_opportunities="", faq=[])
    db.add(row_)
    await db.commit()
    return row_


async def telecaller_in(client, db, team: str = "overseas"):
    tel = await make_telecaller(db, await make_tl_manager(db), team=team)
    await as_user(client, tel)
    return tel


def new_lead(product: TelProduct, **over) -> dict:
    return {"name": f"Lead {uuid.uuid4().hex[:6]}", "phone": f"9{uuid.uuid4().int % 10**9:09d}", "product_id": str(product.id),
            "source": "walk_in", **over}


async def audits(db, lead_id, action: str) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.entity_id == str(lead_id), AuditLog.action == action)
    return list((await db.scalars(stmt)).all())


async def handed(client, db, **over):
    manager, tel, counselor, lead = await setup(db, "overseas", product_id=(await overseas_product(db)).id, **over)
    assert (await handover(client, tel, lead, counselor)).status_code == 200
    await as_user(client, counselor)
    return tel, counselor, lead


# --- LF1 / LF4 / LF5: the lead's own fields ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_round_trips_the_contact_fields_and_stamps_the_consent(client, db_session):
    await telecaller_in(client, db_session)
    response = await client.post(LEADS, json=new_lead(await overseas_product(db_session), **CONTACT))
    assert response.status_code == 201, response.text
    body = response.json()
    assert {k: body[k] for k in CONTACT} == CONTACT and body["marketing_consent_at"]
    lead = await stored(db_session, body["id"])
    assert lead.enquiry_date == date(2026, 9, 14) and lead.marketing_opt_in is True and lead.marketing_consent_at is not None


@pytest.mark.asyncio
async def test_enquiry_date_defaults_to_the_created_date_and_consent_is_not_asked(client, db_session):
    await telecaller_in(client, db_session)
    body = (await client.post(LEADS, json=new_lead(await overseas_product(db_session)))).json()
    assert body["enquiry_date"] == today().isoformat()
    assert body["marketing_opt_in"] is None and body["marketing_consent_at"] is None and body["contact_preference"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "value"), [
    ("contact_preference", "pigeon"), ("enquiry_date", (date.today() + timedelta(days=3)).isoformat()), ("enquiry_date", "1999-12-31"),
    ("referral_name", "x" * 161), ("referral_contact", "y" * 121),
])
async def test_invalid_contact_fields_are_422(client, db_session, field, value):
    await telecaller_in(client, db_session)
    response = await client.post(LEADS, json=new_lead(await overseas_product(db_session), **{field: value}))
    assert response.status_code == 422 and any(e["loc"][-1] == field for e in response.json()["detail"]), response.text


@pytest.mark.asyncio
async def test_details_edit_changes_the_fields_and_audits_the_consent_change_without_values(client, db_session):
    await telecaller_in(client, db_session)
    lead_id = (await client.post(LEADS, json=new_lead(await overseas_product(db_session)))).json()["id"]
    response = await client.patch(f"{LEADS}/{lead_id}", json={"marketing_opt_in": False, "referral_name": "Arun", "contact_preference": "email"})
    assert response.status_code == 200, response.text
    assert response.json()["marketing_opt_in"] is False and response.json()["referral_name"] == "Arun"
    consent = await audits(db_session, lead_id, "lead.consent_change")
    assert [a.metadata_json for a in consent] == [{"from": None, "to": False}]
    contact = await audits(db_session, lead_id, "lead.contact_update")
    assert contact[-1].metadata_json == {"fields": ["contact_preference", "referral_name"]}  # names only, consent has its own row
    # back to "not asked" clears the stamp
    cleared = (await client.patch(f"{LEADS}/{lead_id}", json={"marketing_opt_in": None})).json()
    assert cleared["marketing_opt_in"] is None and cleared["marketing_consent_at"] is None


@pytest.mark.asyncio
async def test_an_unchanged_consent_writes_no_audit(client, db_session):
    await telecaller_in(client, db_session)
    lead_id = (await client.post(LEADS, json=new_lead(await overseas_product(db_session), marketing_opt_in=True))).json()["id"]
    before = (await stored(db_session, lead_id)).marketing_consent_at
    assert (await client.patch(f"{LEADS}/{lead_id}", json={"marketing_opt_in": True})).status_code == 200
    assert await audits(db_session, lead_id, "lead.consent_change") == []
    assert (await stored(db_session, lead_id)).marketing_consent_at == before


# --- LF6: CSV import ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_import_round_trips_the_contact_fields(client, db_session, recorded):  # noqa: F811 (fixture)
    await manager_in(client, db_session)
    camp = await campaign(db_session)
    header = ["name", "phone", "contact_preference", "enquiry_date", "marketing_opt_in", "referral_name", "referral_contact"]
    rows = [row(contact_preference="sms", enquiry_date="2026-08-01", marketing_opt_in="yes", referral_name="Kiran", referral_contact="9000000001"),
            row(marketing_opt_in="no"), row(enquiry_date="01/08/2026")]
    response = await upload(client, camp, csv_bytes(rows, header))
    assert response.status_code == 201, response.text
    first, second, bad = response.json()["rows"]
    assert (first["status"], second["status"], bad["status"]) == ("created", "created", "rejected") and "enquiry_date" in bad["error"].lower().replace(" ", "_")
    lead = await stored(db_session, first["lead_id"])
    assert (lead.contact_preference, lead.enquiry_date, lead.marketing_opt_in, lead.referral_name, lead.referral_contact) == (
        "sms", date(2026, 8, 1), True, "Kiran", "9000000001")
    assert lead.marketing_consent_at is not None
    assert (await stored(db_session, second["lead_id"])).marketing_opt_in is False


@pytest.mark.asyncio
async def test_the_import_template_lists_the_new_columns(client, db_session):
    await manager_in(client, db_session)
    header = (await client.get("/api/v1/telecaller/imports/template")).text.strip().split(",")
    assert header[-5:] == ["contact_preference", "enquiry_date", "marketing_opt_in", "referral_name", "referral_contact"]


# --- LF1 / LF3: the overseas qualification ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overseas_qualification_round_trips_study_academic_and_english_tests(client, db_session):
    await telecaller_in(client, db_session)
    lead_id = (await client.post(LEADS, json=new_lead(await overseas_product(db_session)))).json()["id"]
    place = await country(db_session)
    future = (today() + timedelta(days=400)).isoformat()
    sent = {"preferred_country_id": str(place.id), "study_mode": "full_time", "preferred_campus": "Manchester city campus", "academic_cgpa": 8.4,
            "backlogs": 1, "english_tests": [IELTS, {"test_type": "PTE", "status": "booked", "test_date": future}]}
    response = await client.put(q_url(lead_id), json=sent)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["preferred_country"] == {"id": str(place.id), "name": place.name} and body["study_mode"] == "full_time"
    assert body["preferred_campus"] == "Manchester city campus" and body["academic_cgpa"] == 8.4 and body["backlogs"] == 1
    tests = body["english_tests"]
    assert [t["test_type"] for t in tests] == ["IELTS", "PTE"]
    assert tests[0]["overall_score"] == 6.5 and tests[0]["expired"] is True and tests[1]["expired"] is False
    rows = (await db_session.scalars(select(LeadEnglishTest).where(LeadEnglishTest.lead_id == uuid.UUID(lead_id)).order_by(LeadEnglishTest.position))).all()
    assert [r.position for r in rows] == [0, 1]
    # a later save replaces the list; left out = cleared (QD2)
    again = (await client.put(q_url(lead_id), json={"english_tests": [IELTS | {"overall_score": 7}]})).json()
    assert [t["overall_score"] for t in again["english_tests"]] == [7.0] and again["preferred_country"] is None and again["backlogs"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("sent", "field"), [
    ({"preferred_country_id": str(uuid.uuid4())}, "preferred_country_id"),
    ({"study_mode": "evening"}, "study_mode"),
    ({"academic_cgpa": 10.5}, "academic_cgpa"),
    ({"backlogs": 100}, "backlogs"),
    ({"english_tests": [IELTS | {"overall_score": 9.5}]}, "english_tests"),
    ({"english_tests": [IELTS] * 6}, "english_tests"),
])
async def test_invalid_overseas_answers_are_422(client, db_session, sent, field):
    await telecaller_in(client, db_session)
    lead_id = (await client.post(LEADS, json=new_lead(await overseas_product(db_session)))).json()["id"]
    response = await client.put(q_url(lead_id), json=sent)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert field in (detail if isinstance(detail, str) else " ".join(str(e["loc"]) for e in detail))


@pytest.mark.asyncio
async def test_the_new_overseas_fields_do_not_apply_to_an_it_lead(client, db_session):
    await telecaller_in(client, db_session, team="it")
    product = await db_session.scalar(select(TelProduct).where(TelProduct.product_group == "it", TelProduct.name == "Cyber Security"))
    lead_id = (await client.post(LEADS, json=new_lead(product))).json()["id"]
    response = await client.put(q_url(lead_id), json={"study_mode": "online", "english_tests": [IELTS]})
    assert response.status_code == 422 and "english_tests" in response.json()["detail"] and "study_mode" in response.json()["detail"]
    read = (await client.get(q_url(lead_id))).json()
    assert read["english_tests"] == [] and read["preferred_country"] is None


# --- LF7: the counselor on their own lead -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_edits_the_contact_fields_of_their_lead(client, db_session):
    _, _, lead = await handed(client, db_session)
    response = await client.patch(c_url(lead.id), json={"contact_preference": "call", "marketing_opt_in": True, "referral_name": "Asha"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["contact_preference"] == "call" and body["marketing_opt_in"] is True and body["permissions"]  # the counselor detail
    assert len(await audits(db_session, lead.id, "lead.consent_change")) == 1


@pytest.mark.asyncio
async def test_counselor_cannot_change_contact_details_product_or_priority(client, db_session):
    _, _, lead = await handed(client, db_session)
    for sent in ({"name": "New"}, {"priority": "hot"}, {"product_id": str(uuid.uuid4())}):
        assert (await client.patch(c_url(lead.id), json=sent)).status_code == 422


@pytest.mark.asyncio
async def test_counselor_saves_and_reads_the_qualification_of_their_lead(client, db_session):
    _, counselor, lead = await handed(client, db_session)
    base = "/api/v1/counselor/leads"
    response = await client.put(q_url(lead.id, base), json={"study_mode": "part_time", "english_tests": [IELTS]})
    assert response.status_code == 200, response.text
    assert response.json()["updated_by"]["id"] == str(counselor.id) and response.json()["read_only"] is False
    assert (await client.get(q_url(lead.id, base))).json()["study_mode"] == "part_time"


@pytest.mark.asyncio
async def test_another_counselors_lead_is_404_and_the_telecaller_stays_read_only(client, db_session):
    tel, _, lead = await handed(client, db_session)
    _, _, other, _ = await setup(db_session, "overseas")
    await as_user(client, other)
    assert (await client.patch(c_url(lead.id), json={"contact_preference": "sms"})).status_code == 404
    assert (await client.get(q_url(lead.id, "/api/v1/counselor/leads"))).status_code == 404
    assert (await client.put(q_url(lead.id, "/api/v1/counselor/leads"), json={})).status_code == 404
    await as_user(client, tel)
    assert (await client.patch(f"{LEADS}/{lead.id}", json={"contact_preference": "sms"})).status_code == 403


# --- LF8: conversion carries the data -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_conversion_copies_study_mode_country_backlogs_and_english_tests(client, db_session, monkeypatch):
    _capture(monkeypatch)
    _, counselor, lead = await handed(client, db_session, status="qualified", phone=_phone())
    place = await country(db_session)
    saved = await client.put(q_url(lead.id, "/api/v1/counselor/leads"), json={
        "study_mode": "online", "preferred_country_id": str(place.id), "academic_cgpa": 7.9, "backlogs": 2, "english_tests": [IELTS]})
    assert saved.status_code == 200, saved.text
    response = await client.post(c_url(lead.id, "/convert"), json={"full_name": lead.name, "email": lead.email, "phone": lead.phone})
    assert response.status_code == 201, response.text
    student_id = uuid.UUID(response.json()["student"]["id"])
    profile = await db_session.get(OverseasStudentProfile, student_id)
    assert profile.study_mode == "online" and profile.preferred_country_ids == [str(place.id)]
    tests = (await db_session.scalars(select(OverseasStudentEnglishTest).where(OverseasStudentEnglishTest.student_user_id == student_id))).all()
    assert [(t.test_type, float(t.overall_score)) for t in tests] == [("IELTS", 6.5)]
    quals = (await db_session.scalars(select(OverseasStudentQualification).where(OverseasStudentQualification.student_user_id == student_id))).all()
    assert [(q.score_type, float(q.score), q.backlogs) for q in quals] == [("cgpa", 7.9, 2)]
