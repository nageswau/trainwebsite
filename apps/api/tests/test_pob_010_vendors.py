"""pob-010 -- the vendor master, onboarding and agreements (DEC-SCOPE-420 V1-V12). Shared database: every revocation is a per-user deny override."""

import uuid

import pytest
from sqlalchemy import select

from app.core import rbac
from app.models import AuditLog, Company, UserPermissionOverride
from tests.bdm005_helpers import PDF_BYTES
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user
from tests.test_rec_030_contracts import c_url

COMPANIES = "/api/v1/recruiter/companies"
REQUIREMENTS = "/api/v1/recruiter/requirements"
DRIVES = "/api/v1/recruiter/drives"
PIPELINE = "/api/v1/recruiter/pipeline"
NO_VENDOR_TERMS = "Your role cannot view or change vendor commercial terms"


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _vendor(client, partner_type="vendor", **body) -> dict:
    response = await client.post(COMPANIES, json={"name": f"Vendor {uuid.uuid4().hex[:8]} Pvt", "partner_type": partner_type, **body})
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _client_company(client) -> dict:
    response = await client.post(COMPANIES, json={"name": f"Client {uuid.uuid4().hex[:8]} Pvt"})
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _doc(client, company_id, kind):
    response = await client.post(f"{COMPANIES}/{company_id}/documents", data={"kind": kind}, files={"file": ("f.pdf", PDF_BYTES, "application/pdf")})
    assert response.status_code == 201, response.text


async def _move(client, company_id, status, from_status, **more):
    return await client.post(f"{COMPANIES}/{company_id}/vendor-status", json={"status": status, "from_status": from_status, **more})


async def _signed_agreement(client, company_id, party=None):
    query = f"?party={party}" if party else ""
    created = await client.post(c_url(company_id) + query, json={"direction": "we_pay_vendor", "confidentiality_terms": "Two years", "fee_basis": "fixed", "fee_value": "1000"})
    assert created.status_code == 201, created.text
    uploaded = await client.put(c_url(company_id, f"/document?kind=contract{'&party=' + party if party else ''}"), files={"file": ("s.pdf", PDF_BYTES, "application/pdf")})
    assert uploaded.status_code == 200, uploaded.text
    moved = await client.patch(c_url(company_id) + query, json={"status": "signed", "from_status": "discussion"})
    assert moved.status_code == 200, moved.text
    return moved.json()["contract"]


# --- V1-V4: the record ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_vendor_is_created_with_its_fields_and_starts_as_prospect(client, db_session):
    await _team(client, db_session)
    company = await _vendor(client, vendor_specialisations=["Java", " java "], vendor_service_categories=["Contract staffing"], vendor_locations=["Pune"])
    assert company["partner_type"] == "vendor" and company["vendor_status"] == "prospect" and company["vendor_status_label"] == "Prospect"
    vendor = company["vendor"]
    assert vendor["specialisations"] == ["Java"] and vendor["service_categories"] == ["Contract staffing"] and vendor["locations"] == ["Pune"]
    assert vendor["onboarding_form_on_file"] is False and vendor["nda_on_file"] is False and vendor["agreement"] is None
    assert vendor["history"] == []


@pytest.mark.asyncio
async def test_a_client_has_no_vendor_block_and_cannot_take_vendor_fields(client, db_session):
    await _team(client, db_session)
    company = await _client_company(client)
    assert company["partner_type"] == "recruiter" and company["vendor_status"] is None and company["vendor"] is None
    response = await client.patch(f"{COMPANIES}/{company['id']}", json={"vendor_locations": ["Pune"]})
    assert response.status_code == 422
    created = await client.post(COMPANIES, json={"name": f"X {uuid.uuid4().hex[:8]}", "vendor_locations": ["Pune"]})
    assert created.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["employer", "supplier", None])
async def test_a_client_cannot_send_employer_or_an_unknown_type(client, db_session, value):
    await _team(client, db_session)
    company = await _client_company(client)
    assert (await client.patch(f"{COMPANIES}/{company['id']}", json={"partner_type": value})).status_code == 422


@pytest.mark.asyncio
async def test_a_client_can_become_both_and_keeps_its_requirements(client, db_session):
    await _team(client, db_session)
    company = await _client_company(client)
    created = await client.post(REQUIREMENTS, json={"company_id": company["id"], "title": "Dev", "location": "Pune"})
    assert created.status_code == 201, created.text
    assert (await client.patch(f"{COMPANIES}/{company['id']}", json={"partner_type": "vendor"})).status_code == 409  # V4: it has a requirement
    both = await client.patch(f"{COMPANIES}/{company['id']}", json={"partner_type": "vendor_client", "vendor_locations": ["Goa"]})
    assert both.status_code == 200, both.text
    assert both.json()["company"]["vendor_status"] == "prospect"
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == company["id"], AuditLog.action == "recruiter_company.update"))).all()
    assert any("partner_type" in a.metadata_json["fields"] for a in audit)


@pytest.mark.asyncio
async def test_leaving_the_vendor_relationship_is_refused_once_it_has_an_agreement(client, db_session):
    await _team(client, db_session)
    company = await _vendor(client)
    freed = await client.patch(f"{COMPANIES}/{company['id']}", json={"partner_type": "recruiter"})
    assert freed.status_code == 200 and freed.json()["company"]["vendor_status"] is None  # no agreement yet
    assert (await client.patch(f"{COMPANIES}/{company['id']}", json={"partner_type": "vendor"})).json()["company"]["vendor_status"] == "prospect"
    assert (await client.post(c_url(company["id"]), json={})).status_code == 201
    assert (await client.patch(f"{COMPANIES}/{company['id']}", json={"partner_type": "recruiter"})).status_code == 409


@pytest.mark.asyncio
async def test_an_employer_owned_company_cannot_change_type(client, db_session):
    await _team(client, db_session)
    company = await _client_company(client)
    row = await db_session.get(Company, uuid.UUID(company["id"]))
    row.partner_type = "employer"
    await db_session.commit()
    assert (await client.patch(f"{COMPANIES}/{company['id']}", json={"partner_type": "vendor_client"})).status_code == 409


# --- V5-V7: onboarding ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_a_vendor_is_onboarded_and_contracted_end_to_end(client, db_session):
    manager, recruiter = await _team(client, db_session)
    vendor = await _vendor(client)
    vid = vendor["id"]
    # submit needs the form
    assert (await _move(client, vid, "registration_submitted", "prospect")).status_code == 409
    await _doc(client, vid, "vendor_onboarding_form")
    moved = await _move(client, vid, "registration_submitted", "prospect")
    assert moved.status_code == 200, moved.text
    # approve is the manager's, and needs the NDA
    assert (await _move(client, vid, "approved", "registration_submitted")).status_code == 403
    await login(client, manager)
    assert (await _move(client, vid, "approved", "registration_submitted")).status_code == 409
    await login(client, recruiter)
    await _doc(client, vid, "nda")
    await login(client, manager)
    approved = await _move(client, vid, "approved", "registration_submitted")
    assert approved.status_code == 200 and approved.json()["company"]["vendor"]["nda_on_file"] is True
    # active needs a signed agreement
    await login(client, recruiter)
    assert (await _move(client, vid, "active", "approved")).status_code == 409
    contract = await _signed_agreement(client, vid)
    assert contract["party"] == "vendor" and contract["direction"] == "we_pay_vendor" and contract["confidentiality_terms"] == "Two years"
    active = await _move(client, vid, "active", "approved")
    assert active.status_code == 200, active.text
    body = active.json()["company"]
    assert body["vendor_status"] == "active" and body["vendor"]["agreement"]["status"] == "signed"
    assert [h["to_status"] for h in body["vendor"]["history"]] == ["active", "approved", "registration_submitted"]
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == vid, AuditLog.action == "recruiter_company.vendor_status"))).all()
    assert len(audit) == 3 and all("reason" not in a.metadata_json for a in audit)


@pytest.mark.asyncio
async def test_suspend_and_return_need_a_manager_and_a_reason(client, db_session):
    manager, recruiter = await _team(client, db_session)
    vendor = await _vendor(client)
    vid = vendor["id"]
    await _doc(client, vid, "vendor_onboarding_form")
    assert (await _move(client, vid, "registration_submitted", "prospect")).status_code == 200
    assert (await _move(client, vid, "prospect", "registration_submitted", reason="Bad form")).status_code == 403
    await login(client, manager)
    assert (await _move(client, vid, "prospect", "registration_submitted")).status_code == 422
    returned = await _move(client, vid, "prospect", "registration_submitted", reason="Bad form")
    assert returned.status_code == 200 and returned.json()["company"]["vendor"]["history"][0]["reason"] == "Bad form"


@pytest.mark.asyncio
async def test_a_stale_or_impossible_move_is_refused(client, db_session):
    _, _ = await _team(client, db_session)
    vendor = await _vendor(client)
    assert (await _move(client, vendor["id"], "registration_submitted", "approved")).status_code == 409  # stale
    assert (await _move(client, vendor["id"], "active", "prospect")).status_code == 422  # no such step
    client_company = await _client_company(client)
    assert (await _move(client, client_company["id"], "registration_submitted", "prospect")).status_code == 409  # not a vendor


@pytest.mark.asyncio
async def test_out_of_scope_and_wrong_roles_cannot_move_a_vendor(client, db_session):
    _, _ = await _team(client, db_session)
    vendor = await _vendor(client)
    other_manager = await make_pm(db_session)
    other = await make_recruiter(db_session, other_manager)
    await login(client, other)
    assert (await _move(client, vendor["id"], "registration_submitted", "prospect")).status_code == 404
    bdm = await make_user(db_session, "bdm", "it")
    await login(client, bdm)
    assert (await _move(client, vendor["id"], "registration_submitted", "prospect")).status_code == 404


# --- V8-V9: agreements ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_both_keeps_one_current_contract_per_party(client, db_session):
    await _team(client, db_session)
    company = await _vendor(client, "vendor_client")
    cid = company["id"]
    client_contract = await client.post(c_url(cid), json={"fee_basis": "fixed", "fee_value": "500"})
    assert client_contract.status_code == 201 and client_contract.json()["contract"]["party"] == "client"
    vendor_contract = await client.post(c_url(cid) + "?party=vendor", json={"direction": "vendor_pays_us"})
    assert vendor_contract.status_code == 201, vendor_contract.text
    assert (await client.post(c_url(cid) + "?party=vendor", json={})).status_code == 409  # one in progress per party
    client_side = (await client.get(c_url(cid))).json()
    vendor_side = (await client.get(c_url(cid) + "?party=vendor")).json()
    assert client_side["current"]["id"] == client_contract.json()["contract"]["id"] and vendor_side["current"]["id"] == vendor_contract.json()["contract"]["id"]
    detail = (await client.get(f"{COMPANIES}/{cid}")).json()["company"]
    assert detail["contract"]["status"] == "discussion" and detail["vendor"]["agreement"]["status"] == "discussion"


@pytest.mark.asyncio
async def test_the_wrong_party_and_client_only_terms_are_refused(client, db_session):
    await _team(client, db_session)
    plain = await _client_company(client)
    vendor = await _vendor(client)
    assert (await client.post(c_url(plain["id"]) + "?party=vendor", json={})).status_code == 422
    assert (await client.post(c_url(vendor["id"]) + "?party=client", json={})).status_code == 422
    assert (await client.get(c_url(plain["id"]) + "?party=vendor")).status_code == 422
    assert (await client.post(c_url(plain["id"]), json={"direction": "we_pay_vendor"})).status_code == 422  # a client contract has no direction
    assert (await client.post(c_url(plain["id"]), json={"confidentiality_terms": "x"})).status_code == 422


@pytest.mark.asyncio
async def test_a_vendor_agreement_needs_a_direction_from_signed(client, db_session):
    await _team(client, db_session)
    vendor = await _vendor(client)
    assert (await client.post(c_url(vendor["id"]), json={})).status_code == 201
    assert (await client.put(c_url(vendor["id"], "/document?kind=contract"), files={"file": ("s.pdf", PDF_BYTES, "application/pdf")})).status_code == 200
    refused = await client.patch(c_url(vendor["id"]), json={"status": "signed", "from_status": "discussion"})
    assert refused.status_code == 422 and "direction" in refused.text


def test_vendor_commercials_default_to_the_people_who_contract_vendors():
    holders = {role for role, keys in rbac.DEFAULT_GRANTS.items() if "commercials.vendor.view" in keys}
    editors = {role for role, keys in rbac.DEFAULT_GRANTS.items() if "commercials.vendor.edit" in keys}
    assert holders == editors == {"placement_team", "placement_manager"}


@pytest.mark.asyncio
async def test_vendor_terms_follow_the_vendor_grant_not_the_client_grant(client, db_session):
    _, recruiter = await _team(client, db_session)
    vendor = await _vendor(client)
    contract = await _signed_agreement(client, vendor["id"])
    db_session.add(UserPermissionOverride(user_id=recruiter.id, resource="commercials.vendor", action="view", effect="deny", reason="pob-010 test"))
    await db_session.commit()
    hidden = (await client.get(c_url(vendor["id"]))).json()["current"]
    for field in ("fee_basis", "fee_value", "direction", "confidentiality_terms", "payment_terms", "replacement_policy"):
        assert field not in hidden
    assert hidden["permissions"]["can_view_terms"] is False
    refused = await client.patch(c_url(vendor["id"]), json={"fee_value": "2"})
    assert refused.status_code == 403 and refused.json()["detail"] == NO_VENDOR_TERMS
    download = await client.get(f"/api/v1/recruiter/contracts/{contract['id']}/documents/contract")
    assert download.status_code == 403
    plain = await _client_company(client)  # the client grant is untouched
    assert (await client.post(c_url(plain["id"]), json={"fee_basis": "fixed", "fee_value": "9"})).status_code == 201


@pytest.mark.asyncio
async def test_a_client_grant_denied_recruiter_still_handles_vendor_terms(client, db_session):
    _, recruiter = await _team(client, db_session)
    db_session.add(UserPermissionOverride(user_id=recruiter.id, resource="commercials.client", action="view", effect="deny", reason="pob-010 test"))
    await db_session.commit()
    vendor = await _vendor(client)
    contract = await _signed_agreement(client, vendor["id"])
    assert contract["fee_basis"] == "fixed"


# --- V10-V11: client-only views -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac2_a_vendor_never_appears_in_the_client_list_and_both_appears_in_each(client, db_session):
    await _team(client, db_session)
    vendor = await _vendor(client)
    both = await _vendor(client, "vendor_client")
    plain = await _client_company(client)

    async def ids(query=""):
        return {c["id"] for c in (await client.get(f"{COMPANIES}?limit=100{query}")).json()["items"]}

    assert await ids() >= {both["id"], plain["id"]} and vendor["id"] not in await ids()
    listed = await ids("&relationship=vendor")
    assert listed >= {vendor["id"], both["id"]} and plain["id"] not in listed
    assert await ids("&relationship=all") >= {vendor["id"], both["id"], plain["id"]}
    assert (await client.get(f"{COMPANIES}?relationship=nope")).status_code == 422
    prospects = await ids("&relationship=vendor&vendor_status=prospect")
    assert vendor["id"] in prospects
    assert vendor["id"] not in await ids("&relationship=vendor&vendor_status=active")


@pytest.mark.asyncio
async def test_a_vendor_only_company_is_refused_as_a_client(client, db_session):
    await _team(client, db_session)
    vendor = await _vendor(client)
    refused = await client.post(REQUIREMENTS, json={"company_id": vendor["id"], "title": "Dev", "location": "Pune"})
    assert refused.status_code == 422 and refused.json()["detail"].startswith("This company is a vendor only"), refused.text
    drive = {"company_id": vendor["id"], "college_name": "ABC", "requirement_ids": [str(uuid.uuid4())], "drive_date": "2027-01-20", "job_role": "SDE", "vacancies": 1}
    refused = await client.post(DRIVES, json=drive)
    assert refused.status_code == 422 and refused.json()["detail"].startswith("This company is a vendor only"), refused.text
    assert (await client.post("/api/v1/workflows/it/jobs", json={"company_id": vendor["id"], "title": "Dev"})).status_code == 422
    assert (await client.post("/api/v1/workflows/it/jobs", json={"company_name": vendor["name"], "title": "Dev"})).status_code == 422


@pytest.mark.asyncio
async def test_the_pipeline_board_leaves_a_vendor_out(client, db_session):
    await _team(client, db_session)
    vendor = await _vendor(client)
    both = await _vendor(client, "vendor_client")
    board = await client.get(f"{PIPELINE}?limit=100")
    assert board.status_code == 200, board.text
    listed = {c["id"] for c in board.json()["items"]}
    assert both["id"] in listed and vendor["id"] not in listed


@pytest.mark.asyncio
async def test_public_partners_leave_a_vendor_out(client, db_session):
    await _team(client, db_session)
    vendor = await _vendor(client)
    home = await client.get("/api/v1/public/home")
    assert home.status_code == 200
    assert vendor["id"] not in {str(p["id"]) for p in home.json()["partners"]}


@pytest.mark.asyncio
async def test_merging_a_vendor_is_refused(client, db_session):
    manager = await make_pm(db_session)
    await make_recruiter(db_session, manager)
    await login(client, manager)
    vendor = await _vendor(client)
    plain = await _client_company(client)
    preview = await client.get(f"{COMPANIES}/{plain['id']}/merge?victim={vendor['code']}")
    assert preview.status_code == 409 and "vendor" in preview.text.lower(), preview.text


@pytest.mark.asyncio
async def test_a_contract_refusal_never_logs_the_value(client, db_session, caplog):
    _, recruiter = await _team(client, db_session)
    vendor = await _vendor(client)
    db_session.add(UserPermissionOverride(user_id=recruiter.id, resource="commercials.vendor", action="edit", effect="deny", reason="pob-010 test"))
    await db_session.commit()
    assert (await client.post(c_url(vendor["id"]), json={"confidentiality_terms": "SECRET-TERM"})).status_code == 403
    assert "SECRET-TERM" not in caplog.text
