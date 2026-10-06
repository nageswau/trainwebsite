"""tel-009 -- the lead qualification form (spec §3, §5; DEC-SCOPE-092): GET/PUT /telecaller/leads/{id}/qualification. Basic fields always,
the IT or overseas fields by the product group (QD2), shared fields written through to the lead (QD1), no stage move and one names-only
audit row (QD3), the tel-008 scope and handed-over rule (QF3). The shared test database is never truncated."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry, LeadQualification, TelProduct
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager, make_user

LEADS = "/api/v1/telecaller/leads"
AUDIT = "lead.qualification_update"
BASIC = {"qualification": "B.Tech", "current_org": "VIT University", "passing_year": 2025, "work_experience_years": 1,
         "city": "Chennai", "state": "Tamil Nadu"}
IT = {"it_skill_level": "beginner", "career_objective": "Become a SOC analyst", "preferred_batch": "Weekend evenings",
      "budget_range": "40-60k", "preferred_mode": "online"}
OVERSEAS = {"study_level": "masters", "preferred_course": "MSc Data Science", "intake": "Sep 2027", "academic_percentage": 72.5,
            "english_test_status": "IELTS booked", "passport_status": "valid", "budget_range": "20-25 lakh"}


def url(lead_id) -> str:
    return f"{LEADS}/{lead_id}/qualification"


async def product(db, group: str, name: str) -> TelProduct:
    return await db.scalar(select(TelProduct).where(TelProduct.product_group == group, TelProduct.name == name))


async def setup(db, group: str | None = "overseas", name: str = "UK", **over):
    manager = await make_tl_manager(db)
    tel = await make_telecaller(db, manager, team="overseas" if group == "overseas" else "it")
    prod = await product(db, group, name) if group else None
    row = Enquiry(**({"division": "overseas" if group == "overseas" else "it", "name": f"Lead {uuid.uuid4().hex[:6]}",
                      "email": f"{uuid.uuid4().hex[:8]}@example.local", "phone": "9876543210", "subject": "Study abroad", "message": "",
                      "source": "website", "telecaller_user_id": tel.id, "product_id": prod.id if prod else None, "status": "contacted"} | over))
    db.add(row)
    await db.commit()
    return manager, tel, row


async def audits(db, row) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.entity_type == "enquiry", AuditLog.entity_id == str(row.id), AuditLog.action == AUDIT)
    return list((await db.scalars(stmt)).all())


# --- AC1: sections by product group ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_empty_read_returns_the_lead_shared_values_and_group(client, db_session):
    _, tel, row = await setup(db_session, city="Pune", qualification="BSc")
    await as_user(client, tel)
    response = await client.get(url(row.id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["product_group"] == "overseas" and body["product"]["name"] == "UK" and body["product"]["group"] == "overseas"
    assert body["city"] == "Pune" and body["qualification"] == "BSc" and body["study_level"] is None
    assert body["updated_by"] is None and body["updated_at"] is None and body["read_only"] is False


@pytest.mark.asyncio
async def test_overseas_lead_saves_basic_and_overseas_fields(client, db_session):
    """Positive scenario: Overseas UK Masters, intake Sep 2027."""
    _, tel, row = await setup(db_session)
    await as_user(client, tel)
    response = await client.put(url(row.id), json=BASIC | OVERSEAS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["study_level"] == "masters" and body["intake"] == "Sep 2027" and body["academic_percentage"] == 72.5
    assert body["updated_by"]["id"] == str(tel.id) and body["updated_at"]
    saved = await db_session.scalar(select(LeadQualification).where(LeadQualification.lead_id == row.id).execution_options(populate_existing=True))
    assert saved.academic_percentage == Decimal("72.50") and saved.passport_status == "valid"


@pytest.mark.asyncio
async def test_it_fields_on_an_overseas_lead_are_422(client, db_session):
    _, tel, row = await setup(db_session)
    await as_user(client, tel)
    response = await client.put(url(row.id), json=BASIC | {"preferred_mode": "online"})
    assert response.status_code == 422 and "preferred_mode" in response.text


@pytest.mark.asyncio
async def test_it_lead_accepts_it_fields_and_refuses_overseas_ones(client, db_session):
    _, tel, row = await setup(db_session, "it", "Cyber Security")
    await as_user(client, tel)
    assert (await client.put(url(row.id), json=BASIC | IT)).status_code == 200
    assert (await client.put(url(row.id), json={"study_level": "ug"})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(("group", "name"), [("other", "General Enquiry"), (None, None)])
async def test_other_or_no_product_takes_basic_fields_only(client, db_session, group, name):
    """Edge case: a lead with an "Other" product (or none) has the basic fields only."""
    _, tel, row = await setup(db_session, group, name or "")
    await as_user(client, tel)
    body = (await client.get(url(row.id))).json()
    assert body["product_group"] == group
    assert (await client.put(url(row.id), json=BASIC)).status_code == 200
    assert (await client.put(url(row.id), json={"budget_range": "10k"})).status_code == 422


# --- AC2: ranges ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{"academic_percentage": 120}, {"academic_percentage": -1}, {"passing_year": 1900}, {"passing_year": 2101},
                                 {"work_experience_years": 51}, {"study_level": "phd"}, {"passport_status": "lost"}, {"intake": "x" * 41},
                                 {"current_org": "Bad\x00name"}, {"lead_id": str(uuid.uuid4())}])
async def test_invalid_values_are_422_and_nothing_is_saved(client, db_session, bad):
    _, tel, row = await setup(db_session)
    await as_user(client, tel)
    assert (await client.put(url(row.id), json=bad)).status_code == 422
    assert await db_session.scalar(select(LeadQualification).where(LeadQualification.lead_id == row.id)) is None


# --- AC3: a group change keeps the other group's values -----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_switching_group_keeps_and_never_clears_the_hidden_values(client, db_session):
    _, tel, row = await setup(db_session)
    await as_user(client, tel)
    assert (await client.put(url(row.id), json=BASIC | OVERSEAS)).status_code == 200
    java = await product(db_session, "it", "Java")
    assert (await client.patch(f"{LEADS}/{row.id}", json={"product_id": str(java.id)})).status_code == 200
    assert (await client.put(url(row.id), json=BASIC | {"preferred_mode": "offline"})).status_code == 200
    body = (await client.get(url(row.id))).json()
    assert body["product_group"] == "it" and body["preferred_mode"] == "offline"
    assert body["study_level"] == "masters" and body["intake"] == "Sep 2027"  # hidden, kept
    assert body["budget_range"] is None  # shared by both groups: the IT save replaced it


# --- AC4 / AC5: write-through, no stage move, audit ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_shared_fields_write_through_stage_stays_and_one_names_only_audit(client, db_session):
    _, tel, row = await setup(db_session)
    await as_user(client, tel)
    assert (await client.put(url(row.id), json=BASIC | OVERSEAS)).status_code == 200
    lead = await db_session.scalar(select(Enquiry).where(Enquiry.id == row.id).execution_options(populate_existing=True))
    assert (lead.qualification, lead.passing_year, lead.city, lead.state) == ("B.Tech", 2025, "Chennai", "Tamil Nadu")
    assert lead.status == "contacted"
    [audit] = await audits(db_session, row)
    assert audit.user_id == tel.id and "city" in audit.metadata_json["fields"] and "intake" in audit.metadata_json["fields"]
    assert "Chennai" not in str(audit.metadata_json)
    assert (await client.put(url(row.id), json=BASIC | OVERSEAS)).status_code == 200  # same values again: idempotent, no new audit
    assert len(await audits(db_session, row)) == 1
    assert (await client.put(url(row.id), json=BASIC | OVERSEAS | {"city": None})).status_code == 200  # omitted/null clears
    lead = await db_session.scalar(select(Enquiry).where(Enquiry.id == row.id).execution_options(populate_existing=True))
    assert lead.city is None and len(await audits(db_session, row)) == 2


# --- AC6: scope, roles, handed over ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_other_telecallers_lead_and_unknown_id_are_404(client, db_session):
    manager, _, row = await setup(db_session)
    other = await make_telecaller(db_session, manager, team="overseas")
    await as_user(client, other)
    assert (await client.get(url(row.id))).status_code == 404
    assert (await client.put(url(row.id), json=BASIC)).status_code == 404
    assert (await client.get(url(uuid.uuid4()))).status_code == 404


@pytest.mark.asyncio
async def test_manager_reads_and_writes_a_reports_lead(client, db_session):
    manager, _, row = await setup(db_session)
    await as_user(client, manager)
    assert (await client.put(url(row.id), json=BASIC | OVERSEAS)).status_code == 200
    assert (await client.get(url(row.id))).json()["updated_by"]["id"] == str(manager.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_admin", "it"), ("counselor", "overseas"), ("overseas_student", "overseas")])
async def test_other_roles_are_403(client, db_session, role, division):
    _, _, row = await setup(db_session)
    await as_user(client, await make_user(db_session, role, division))
    assert (await client.get(url(row.id))).status_code == 403
    assert (await client.put(url(row.id), json=BASIC)).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client, db_session):
    _, _, row = await setup(db_session)
    assert (await client.get(url(row.id))).status_code == 401


@pytest.mark.asyncio
async def test_handed_over_lead_is_read_only_for_the_telecaller(client, db_session):
    counselor = await make_user(db_session, "counselor", "overseas")
    manager, tel, row = await setup(db_session, owner_id=counselor.id)
    await as_user(client, tel)
    body = (await client.get(url(row.id))).json()
    assert body["read_only"] is True
    assert (await client.put(url(row.id), json=BASIC)).status_code == 403
    await as_user(client, manager)  # D1: a manager still writes
    assert (await client.put(url(row.id), json=BASIC)).status_code == 200
