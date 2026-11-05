"""pob-001 -- client commercial terms behind `commercials.client.view` / `.edit` (DEC-SCOPE-401 C1-C9). The shared test database is never
truncated and the role grants are shared, so every revocation here is a per-user deny override (nehn-007) on a user the test creates."""

import uuid

import pytest
from sqlalchemy import select

from app.core import rbac
from app.models import UserPermissionOverride
from tests.bdm005_helpers import PDF_BYTES
from tests.rec001_helpers import login, make_pm, make_recruiter
from tests.test_rec_030_contracts import _company, _start, _upload, c_url
from tests.test_rec_031_revenue import COMPANIES, INVOICES, REQ, _contract, _invoice, _setup

BY_RECRUITER = "/api/v1/recruiter/performance/by-recruiter"
TERMS = ("fee_basis", "fee_value", "payment_terms", "replacement_policy")
REFUSED = "Your role cannot view or change client commercial terms"


async def _deny(db, user, *actions: str) -> None:
    for action in actions:
        db.add(UserPermissionOverride(user_id=user.id, resource="commercials.client", action=action, effect="deny", reason="pob-001 test"))
    await db.commit()


async def _signed_contract(client, db):
    """A recruiter (default grants) with a company whose current contract has a fee, terms and a document."""
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    company = await _company(client)
    created = await _start(client, company["id"], fee_basis="fixed", fee_value="50000", payment_terms="30 days", replacement_policy="90 days")
    assert created.status_code == 201, created.text
    assert (await _upload(client, company["id"])).status_code == 200
    return manager, recruiter, company, created.json()["contract"]


# --- C2 / C3: the catalogue and the defaults ---------------------------------------------------------------------------------------
def test_catalogue_declares_the_commercial_and_contact_keys():
    keys = rbac.all_keys()
    for key in ("commercials.client.view", "commercials.client.edit", "commercials.vendor.view", "commercials.vendor.edit", "candidates.contact.view"):
        assert key in keys, key


def test_recruiters_and_managers_keep_client_commercials_by_default_and_nobody_holds_vendor_or_contact():
    holders = {role for role, keys in rbac.DEFAULT_GRANTS.items() if "commercials.client.view" in keys}
    editors = {role for role, keys in rbac.DEFAULT_GRANTS.items() if "commercials.client.edit" in keys}
    assert holders == {"placement_team", "placement_manager", "bdm"}  # the BDM reads the assigned company's contract (rec-030 R10)
    assert editors == {"placement_team", "placement_manager"}
    for role, keys in rbac.DEFAULT_GRANTS.items():
        assert not {k for k in keys if k.startswith(("commercials.vendor.", "candidates.contact."))}, role


# --- C5: contracts -------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_default_recruiter_sees_and_edits_the_terms(client, db_session):
    _, _, company, contract = await _signed_contract(client, db_session)
    assert contract["fee_value"] == "50000.00" and contract["payment_terms"] == "30 days"
    assert contract["permissions"]["can_view_terms"] is True and contract["permissions"]["can_edit_terms"] is True
    read = (await client.get(c_url(company["id"]))).json()
    assert read["can_view_terms"] is True and read["can_edit_terms"] is True
    changed = await client.patch(c_url(company["id"]), json={"fee_value": "60000"})
    assert changed.status_code == 200 and changed.json()["contract"]["fee_value"] == "60000.00"


@pytest.mark.asyncio
async def test_without_view_no_fee_or_terms_appear_and_their_writes_are_403(client, db_session):
    _, recruiter, company, contract = await _signed_contract(client, db_session)
    await _deny(db_session, recruiter, "view")
    read = (await client.get(c_url(company["id"]))).json()
    current = read["current"]
    assert not set(TERMS) & set(current), current
    assert current["permissions"]["can_view_terms"] is False and current["permissions"]["can_edit_terms"] is False
    assert current["permissions"]["can_upload"] is False and current["contract_document"] is not None  # the file's presence is not a term
    assert read["can_view_terms"] is False and read["can_edit_terms"] is False
    for body in ({"fee_value": "1"}, {"payment_terms": None}, {"fee_basis": None, "fee_value": None}):
        refused = await client.patch(c_url(company["id"]), json=body)
        assert refused.status_code == 403 and refused.json()["detail"] == REFUSED, body
    kept = await client.patch(c_url(company["id"]), json={"agreement_type": "Permanent hiring"})
    assert kept.status_code == 200 and kept.json()["contract"]["agreement_type"] == "Permanent hiring"
    assert not set(TERMS) & set(kept.json()["contract"])
    assert (await client.get(f"/api/v1/recruiter/contracts/{contract['id']}/documents/contract")).status_code == 403
    assert (await _upload(client, company["id"], kind="mou", data=PDF_BYTES)).status_code == 403
    other = await _company(client)
    assert (await _start(client, other["id"], fee_basis="fixed", fee_value="1")).status_code == 403
    started = await _start(client, other["id"], agreement_type="Contract staffing")
    assert started.status_code == 201 and not set(TERMS) & set(started.json()["contract"])


@pytest.mark.asyncio
async def test_previous_contracts_hide_their_terms_too(client, db_session):
    _, recruiter, company, _ = await _signed_contract(client, db_session)
    assert (await client.patch(c_url(company["id"]), json={"status": "signed", "from_status": "discussion"})).status_code == 200
    assert (await _start(client, company["id"], fee_basis="fixed", fee_value="70000")).status_code == 201  # a renewal
    await _deny(db_session, recruiter, "view")
    read = (await client.get(c_url(company["id"]))).json()
    assert len(read["previous"]) == 1 and not set(TERMS) & set(read["previous"][0])


@pytest.mark.asyncio
async def test_view_without_edit_reads_the_terms_but_cannot_change_them(client, db_session):
    _, recruiter, company, _ = await _signed_contract(client, db_session)
    await _deny(db_session, recruiter, "edit")
    current = (await client.get(c_url(company["id"]))).json()["current"]
    assert current["fee_value"] == "50000.00" and current["permissions"]["can_edit_terms"] is False
    assert (await client.patch(c_url(company["id"]), json={"fee_value": "1"})).status_code == 403
    assert (await client.get(f"/api/v1/recruiter/contracts/{current['id']}/documents/contract")).status_code == 200


@pytest.mark.asyncio
async def test_the_deny_applies_to_that_recruiter_only(client, db_session):
    manager, recruiter, company, _ = await _signed_contract(client, db_session)
    await _deny(db_session, recruiter, "view")
    await login(client, manager)  # AC2: the Team Lead sees the team's commercials
    current = (await client.get(c_url(company["id"]))).json()["current"]
    assert current["fee_value"] == "50000.00" and current["payment_terms"] == "30 days"


# --- C6: revenue ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_without_view_every_revenue_route_is_403(client, db_session):
    _, recruiter, job = await _setup(client, db_session, hires=1)
    await _contract(db_session, job, recruiter)
    assert (await client.get(f"{REQ}/{job.id}/revenue")).status_code == 200
    invoice = (await _invoice(client, job)).json()["invoice"]
    await _deny(db_session, recruiter, "view")
    for response in (
        await client.get(f"{REQ}/{job.id}/revenue"),
        await client.get(f"{COMPANIES}/{job.company_id}/revenue"),
        await client.get(INVOICES),
        await _invoice(client, job),
        await client.post(f"{INVOICES}/{invoice['id']}/payments", json={"received_on": invoice["invoice_date"], "amount": "1"}),
        await client.post(f"{INVOICES}/{invoice['id']}/cancel", json={"reason": "Wrong amount"}),
    ):
        assert response.status_code == 403 and response.json()["detail"] == "Your role cannot view client commercials", response.text


@pytest.mark.asyncio
async def test_a_manager_without_edit_cannot_override_the_fee(client, db_session):
    manager, recruiter, job = await _setup(client, db_session, hires=1)
    await login(client, manager)
    allowed = await client.put(f"{REQ}/{job.id}/fee", json={"fee_basis": "fixed", "fee_value": "40000"})  # + a grant holder edits the fee
    assert allowed.status_code == 200 and allowed.json()["permissions"]["can_set_fee"] is True
    await _deny(db_session, manager, "edit")
    assert (await client.get(f"{REQ}/{job.id}/revenue")).json()["permissions"]["can_set_fee"] is False
    refused = await client.put(f"{REQ}/{job.id}/fee", json={"fee_basis": "fixed", "fee_value": "1"})
    assert refused.status_code == 403 and refused.json()["detail"] == REFUSED


# --- C7: the recruiter comparison ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_comparison_drops_revenue_without_view(client, db_session):
    manager, recruiter, job = await _setup(client, db_session, hires=0)
    await login(client, manager)
    shown = (await client.get(BY_RECRUITER)).json()
    assert shown["revenue_visible"] is True and all("revenue" in row for row in shown["items"]) and "revenue" in shown["totals"]
    await _deny(db_session, manager, "view")
    hidden = (await client.get(BY_RECRUITER)).json()
    assert hidden["revenue_visible"] is False and hidden["items"]
    assert not any("revenue" in row for row in hidden["items"]) and "revenue" not in hidden["totals"]


@pytest.mark.asyncio
async def test_refusals_are_logged_without_values(client, db_session, caplog):
    _, recruiter, company, _ = await _signed_contract(client, db_session)
    await _deny(db_session, recruiter, "view")
    caplog.set_level("WARNING", logger="app.recruiter")
    marker = f"9{uuid.uuid4().int % 10**6}"
    assert (await client.patch(c_url(company["id"]), json={"fee_value": marker})).status_code == 403
    records = [r for r in caplog.records if r.getMessage() == "recruiter_commercials_refused"]
    assert records and marker not in str(records[0].__dict__)
    assert await db_session.scalar(select(UserPermissionOverride.id).where(UserPermissionOverride.user_id == recruiter.id))
