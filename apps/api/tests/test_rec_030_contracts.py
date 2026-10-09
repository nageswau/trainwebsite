"""rec-030 -- recruiter contracts / MoU (spec §1-§3; DEC-SCOPE-156 CT1-CT10): statuses in source order (AC1), Expired derived (AC2),
Signed needs the contract document (AC3), end before start 422, overlapping contracts 409, renewal, documents, history and roles. The
shared test database is never truncated, so every assertion uses a company created by the test."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, Company, RecruiterContract
from app.services.storage import storage
from tests.bdm005_helpers import PDF_BYTES
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user

COMPANIES = "/api/v1/recruiter/companies"
CONTRACTS = "/api/v1/recruiter/contracts"
TODAY = date.today()


def c_url(company_id: str, tail: str = "") -> str:
    return f"{COMPANIES}/{company_id}/contracts{tail}"


async def _team(client, db):
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, recruiter)
    return manager, recruiter


async def _company(client) -> dict:
    response = await client.post(COMPANIES, json={"name": f"CT {uuid.uuid4().hex[:8]} Pvt"})
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _start(client, company_id, **body):
    return await client.post(c_url(company_id), json=body)


async def _upload(client, company_id, kind="contract", data=PDF_BYTES, name="signed.pdf"):
    return await client.put(c_url(company_id, f"/document?kind={kind}"), files={"file": (name, data, "application/pdf")})


async def _move(client, company_id, status, from_status, **more):
    return await client.patch(c_url(company_id), json={"status": status, "from_status": from_status, **more})


async def _setup(client, db):
    manager, recruiter = await _team(client, db)
    company = await _company(client)
    return manager, recruiter, company


# --- create / read -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_contract_yet_then_start_one_with_the_section_22_fields(client, db_session):
    _, recruiter, company = await _setup(client, db_session)
    empty = await client.get(c_url(company["id"]))
    assert empty.status_code == 200 and empty.json() == {"current": None, "previous": [], "can_start": True}
    response = await _start(client, company["id"], status="proposal_sent", agreement_type="Permanent hiring", start_date="2026-04-01",
                            end_date="2027-03-31", fee_basis="percent_of_ctc", fee_value="8.33", payment_terms="30 days\nfrom joining",
                            replacement_policy="Free replacement within 90 days")
    assert response.status_code == 201, response.text
    c = response.json()["contract"]
    assert c["status"] == "proposal_sent" and c["status_label"] == "Proposal Sent" and c["is_current"] is True
    assert c["agreement_type"] == "Permanent hiring" and c["start_date"] == "2026-04-01" and c["end_date"] == "2027-03-31"
    assert c["fee_basis"] == "percent_of_ctc" and c["fee_value"] == "8.33" and c["payment_terms"] == "30 days\nfrom joining"
    assert c["contract_document"] is None and c["mou_document"] is None and c["created_by"]["id"] == str(recruiter.id)
    assert c["permissions"] == {"can_edit": True, "can_upload": True, "can_renew": False}
    read = (await client.get(c_url(company["id"]))).json()
    assert read["current"]["id"] == c["id"] and read["can_start"] is False
    assert (await _start(client, company["id"])).json()["detail"]["code"] == "contract_exists"
    detail = (await client.get(f"{COMPANIES}/{company['id']}")).json()["company"]
    assert detail["contract"] == {"status": "proposal_sent", "status_label": "Proposal Sent"}  # CT10
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_contract.created", AuditLog.entity_id == c["id"]))
    assert audit.metadata_json == {"company_id": company["id"], "status": "proposal_sent"}  # ids and status keys only


@pytest.mark.asyncio
async def test_defaults_to_discussion_and_the_company_has_no_contract_field_before(client, db_session):
    _, _, company = await _setup(client, db_session)
    assert (await client.get(f"{COMPANIES}/{company['id']}")).json()["company"]["contract"] is None
    c = (await _start(client, company["id"])).json()["contract"]
    assert c["status"] == "discussion" and c["fee_basis"] is None and c["fee_value"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body, field",
    [
        ({"start_date": "2026-05-01", "end_date": "2026-04-30"}, "end_date"),  # negative scenario: end before start
        ({"fee_basis": "fixed"}, "fee_value"),
        ({"fee_value": "50000"}, "fee_basis"),
        ({"fee_basis": "percent_of_ctc", "fee_value": "101"}, "fee_value"),
        ({"fee_basis": "fixed", "fee_value": "-1"}, "fee_value"),
        ({"status": "expired"}, "status"),  # CT2: never chosen
        ({"status": "signed"}, "status"),  # AC3: no contract document yet
        ({"agreement_type": "x" * 101}, "agreement_type"),
        ({"start_date": "2026-13-01"}, "start_date"),
    ],
)
async def test_invalid_input_is_a_422_on_its_field(client, db_session, body, field):
    _, _, company = await _setup(client, db_session)
    response = await _start(client, company["id"], **body)
    assert response.status_code == 422, response.text
    assert any(e["loc"][-1] == field for e in response.json()["detail"]), response.json()


# --- statuses (AC1, AC3) ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_proposal_sent_to_signed_with_the_pdf(client, db_session):
    """Positive scenario: Signed needs the contract document (AC3); skipping Negotiation and Contract Sent is allowed (CT1)."""
    _, _, company = await _setup(client, db_session)
    await _start(client, company["id"], status="proposal_sent")
    refused = await _move(client, company["id"], "signed", "proposal_sent")
    assert refused.status_code == 422 and refused.json()["detail"][0]["loc"][-1] == "status"
    uploaded = await _upload(client, company["id"])
    assert uploaded.status_code == 200, uploaded.text
    doc = uploaded.json()["contract"]["contract_document"]
    assert doc["name"] == "signed.pdf" and doc["content_type"] == "application/pdf" and "key" not in str(doc)
    signed = await _move(client, company["id"], "signed", "proposal_sent")
    assert signed.status_code == 200, signed.text
    c = signed.json()["contract"]
    assert c["status"] == "signed" and c["permissions"]["can_renew"] is True
    history = (await client.get(f"{CONTRACTS}/{c['id']}/history")).json()
    assert [(e["kind"], e["from_status"], e["to_status"]) for e in history["items"]] == [
        ("status", "proposal_sent", "signed"), ("document", "proposal_sent", "proposal_sent"), ("created", None, "proposal_sent")]
    assert history["items"][1]["changed"] == ["contract_document"]


@pytest.mark.asyncio
async def test_status_moves_back_and_stale_or_same_status_is_refused(client, db_session):
    _, _, company = await _setup(client, db_session)
    await _start(client, company["id"], status="negotiation")
    assert (await _move(client, company["id"], "proposal_sent", "negotiation")).status_code == 200  # CT1: a correction backwards
    stale = await _move(client, company["id"], "contract_sent", "negotiation")
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "contract_status_changed"
    same = await _move(client, company["id"], "proposal_sent", "proposal_sent")
    assert same.status_code == 422
    missing = await client.patch(c_url(company["id"]), json={"status": "negotiation"})
    assert missing.status_code == 422  # a status change carries from_status


@pytest.mark.asyncio
async def test_active_needs_both_dates_and_an_edit_with_no_change_records_nothing(client, db_session):
    _, _, company = await _setup(client, db_session)
    await _start(client, company["id"], status="contract_sent", start_date="2026-04-01")
    await _upload(client, company["id"])
    refused = await _move(client, company["id"], "active", "contract_sent")
    assert refused.status_code == 422 and refused.json()["detail"][0]["loc"][-1] == "end_date"
    ok = await _move(client, company["id"], "active", "contract_sent", end_date="2027-03-31")
    assert ok.status_code == 200 and ok.json()["contract"]["status"] == "active"
    c = ok.json()["contract"]
    same = await client.patch(c_url(company["id"]), json={"agreement_type": None, "start_date": "2026-04-01"})
    assert same.status_code == 200 and same.json()["contract"]["updated_at"] == c["updated_at"]
    stale = await client.patch(c_url(company["id"]), json={"payment_terms": "45 days", "expected_updated_at": "2020-01-01T00:00:00+00:00"})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "contract_changed"
    edit = await client.patch(c_url(company["id"]), json={"payment_terms": "45 days", "expected_updated_at": c["updated_at"]})
    assert edit.status_code == 200 and edit.json()["contract"]["payment_terms"] == "45 days"


# --- Expired (AC2), renewal and overlap (CT7, CT8) ------------------------------------------------------------------------------
async def _signed(client, company_id, start: date, end: date) -> dict:
    await _start(client, company_id, status="contract_sent", start_date=start.isoformat(), end_date=end.isoformat())
    await _upload(client, company_id)
    return (await _move(client, company_id, "signed", "contract_sent")).json()["contract"]


@pytest.mark.asyncio
async def test_expired_is_shown_automatically_after_the_end_date(client, db_session):
    _, _, company = await _setup(client, db_session)
    c = await _signed(client, company["id"], TODAY - timedelta(days=400), TODAY - timedelta(days=1))
    assert c["status"] == "expired" and c["status_label"] == "Expired" and c["expired_on"] == TODAY.isoformat()
    assert (await client.get(f"{COMPANIES}/{company['id']}")).json()["company"]["contract"]["status"] == "expired"
    locked = await _move(client, company["id"], "active", "expired")
    assert locked.status_code == 409 and locked.json()["detail"]["code"] == "contract_expired"
    revived = await client.patch(c_url(company["id"]), json={"end_date": (TODAY + timedelta(days=30)).isoformat()})  # a date correction
    assert revived.status_code == 200 and revived.json()["contract"]["status"] == "signed"


@pytest.mark.asyncio
async def test_renewal_keeps_the_old_contract_and_overlapping_windows_are_409(client, db_session):
    _, _, company = await _setup(client, db_session)
    old = await _signed(client, company["id"], date(2025, 4, 1), date(2026, 3, 31))
    overlap = await _start(client, company["id"], start_date="2026-03-01")
    assert overlap.status_code == 409 and overlap.json()["detail"]["code"] == "contract_overlap"  # edge case
    renewal = await _start(client, company["id"], start_date="2026-04-01", end_date="2027-03-31")
    assert renewal.status_code == 201, renewal.text
    new = renewal.json()["contract"]
    read = (await client.get(c_url(company["id"]))).json()
    assert read["current"]["id"] == new["id"] and [p["id"] for p in read["previous"]] == [old["id"]] and read["previous"][0]["is_current"] is False
    moved = await client.patch(c_url(company["id"]), json={"start_date": "2026-01-01"})
    assert moved.status_code == 409 and moved.json()["detail"]["code"] == "contract_overlap"
    old_history = (await client.get(f"{CONTRACTS}/{old['id']}/history")).json()["items"]
    assert old_history[0]["kind"] == "renewed"


@pytest.mark.asyncio
async def test_renewal_is_refused_while_the_current_contract_is_still_in_discussion(client, db_session):
    _, _, company = await _setup(client, db_session)
    await _start(client, company["id"])
    assert (await _start(client, company["id"])).status_code == 409


# --- documents ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mou_and_contract_documents_download_in_scope_only(client, db_session):
    manager, _, company = await _setup(client, db_session)
    await _start(client, company["id"])
    up = await _upload(client, company["id"], kind="mou", name="mou.pdf")
    assert up.status_code == 200 and up.json()["contract"]["mou_document"]["name"] == "mou.pdf" and up.json()["contract"]["contract_document"] is None
    contract_id = up.json()["contract"]["id"]
    row = await db_session.scalar(select(RecruiterContract).where(RecruiterContract.id == uuid.UUID(contract_id)))
    assert row.mou_document_key.startswith("recruiter-contracts/") and storage.read_bytes(row.mou_document_key) == PDF_BYTES
    download = await client.get(f"{CONTRACTS}/{contract_id}/documents/mou")
    assert download.status_code == 200 and download.content == PDF_BYTES
    assert download.headers["content-disposition"] == f'attachment; filename="mou-{company["code"]}.pdf"'
    assert (await client.get(f"{CONTRACTS}/{contract_id}/documents/contract")).status_code == 404  # none on file
    assert (await client.put(c_url(company["id"], "/document?kind=other"), files={"file": ("a.pdf", PDF_BYTES, "application/pdf")})).status_code == 422
    bad = await _upload(client, company["id"], data=b"not a pdf at all", name="x.pdf")
    assert bad.status_code == 415  # agent_documents.read_upload: the type is decided by the bytes
    await login(client, await make_recruiter(db_session, manager))  # a teammate: outside the company's scope
    assert (await client.get(f"{CONTRACTS}/{contract_id}/documents/mou")).status_code == 404
    assert (await client.get(f"{CONTRACTS}/{contract_id}/history")).status_code == 404


@pytest.mark.asyncio
async def test_upload_before_any_contract_is_404(client, db_session):
    _, _, company = await _setup(client, db_session)
    assert (await _upload(client, company["id"])).status_code == 404


# --- roles (CT9) ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_and_bdm_read_but_cannot_write_and_others_get_404(client, db_session):
    manager, _, company = await _setup(client, db_session)
    await _start(client, company["id"], status="proposal_sent", fee_basis="fixed", fee_value="50000")
    bdm = await make_user(db_session, "bdm", "global")
    await db_session.execute(update(Company).where(Company.id == uuid.UUID(company["id"])).values(assigned_bdm_user_id=bdm.id))
    await db_session.commit()
    for reader in (manager, bdm):
        await login(client, reader)
        read = await client.get(c_url(company["id"]))
        assert read.status_code == 200 and read.json()["current"]["fee_value"] == "50000.00"
        assert read.json()["current"]["permissions"] == {"can_edit": False, "can_upload": False, "can_renew": False} and read.json()["can_start"] is False
        assert (await client.patch(c_url(company["id"]), json={"payment_terms": "x"})).status_code == 403
        assert (await _upload(client, company["id"])).status_code == 403
    await login(client, await make_user(db_session, "employer", "it"))
    assert (await client.get(c_url(company["id"]))).status_code == 403  # commercial terms are staff only
    await login(client, await make_recruiter(db_session))
    assert (await client.get(c_url(company["id"]))).status_code == 404


@pytest.mark.asyncio
async def test_super_admin_writes_and_an_archived_company_is_read_only(client, db_session):
    _, recruiter, company = await _setup(client, db_session)
    await _start(client, company["id"])
    assert (await client.post(f"{COMPANIES}/{company['id']}/archive")).status_code == 200
    archived = await client.patch(c_url(company["id"]), json={"payment_terms": "x"})
    assert archived.status_code == 409
    assert (await client.get(c_url(company["id"]))).json()["current"]["permissions"]["can_edit"] is False
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await client.post(f"{COMPANIES}/{company['id']}/restore")).status_code == 200
    ok = await client.patch(c_url(company["id"]), json={"payment_terms": "Net 30"})
    assert ok.status_code == 200 and ok.json()["contract"]["payment_terms"] == "Net 30"
