"""pob-012 -- vendor commercials, payables and performance (DEC-SCOPE-433 W1-W10). Shared database: every value is unique per test."""

import importlib.util
import pathlib
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app import models
from app.models import AuditLog, Candidate, Company, Interview, Job, JobApplication, JobApplicationStatusHistory, ProfileShare, ProfileShareItem, UserPermissionOverride
from tests.rec001_helpers import login, make_recruiter
from tests.test_pob_011_vendor_requirements import _vendor
from tests.test_rec_017_tracking import _candidate, _requirement, _tag, _team

COMPANIES = "/api/v1/recruiter/companies"
BILLS = "/api/v1/recruiter/vendor-bills"
PERF = "/api/v1/recruiter/vendors"
LEDGER = "/api/v1/management/ledger/lines"
TODAY = date.today()


def _bill(**over) -> dict:
    return {"kind": "payable", "bill_number": f"VB-{_tag()}", "bill_date": (TODAY - timedelta(days=3)).isoformat(), "due_date": TODAY.isoformat(), "amount": "10000.00"} | over


async def _setup(client, db):
    manager, recruiter = await _team(client, db)
    vendor = await _vendor(db, recruiter)
    return manager, recruiter, vendor


# --- W2/W3: bills and payments -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_payable_is_recorded_paid_in_part_and_totalled(client, db_session):
    _, _, vendor = await _setup(client, db_session)
    created = await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill(milestone="On joining"))
    assert created.status_code == 201, created.text
    bill = created.json()["bill"]
    assert (bill["kind"], bill["payment_status"], bill["milestone"], bill["outstanding"]) == ("payable", "unpaid", "On joining", "10000.00")
    assert bill["permissions"] == {"can_pay": True, "can_cancel": True}
    paid = await client.post(f"{BILLS}/{bill['id']}/payments", json={"paid_on": TODAY.isoformat(), "amount": "4000.00", "reference": "NEFT 1"})
    assert paid.status_code == 201, paid.text
    assert (paid.json()["bill"]["payment_status"], paid.json()["bill"]["outstanding"]) == ("part_paid", "6000.00")
    over = await client.post(f"{BILLS}/{bill['id']}/payments", json={"paid_on": TODAY.isoformat(), "amount": "6000.01"})
    assert over.status_code == 422, over.text
    await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill(kind="receivable", amount="2500.00"))
    listing = (await client.get(f"{COMPANIES}/{vendor.id}/vendor-bills")).json()
    assert len(listing["items"]) == 2 and listing["can_edit"] is True
    assert listing["totals"]["payable"] == {"billed": "10000.00", "paid": "4000.00", "outstanding": "6000.00", "last_paid_on": TODAY.isoformat()}
    assert listing["totals"]["receivable"]["outstanding"] == "2500.00"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "vendor_commercials.payment_recorded", AuditLog.entity_id == bill["id"]))
    assert audit.metadata_json["amount"] == "4000.00" and "NEFT" not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_bill_rules(client, db_session):
    _, recruiter, vendor = await _setup(client, db_session)
    number = f"VB-{_tag()}"
    assert (await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill(bill_number=number))).status_code == 201
    dup = await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill(bill_number=number.lower()))
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "bill_number_taken"
    future = await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill(bill_date=(TODAY + timedelta(days=1)).isoformat(), due_date=(TODAY + timedelta(days=2)).isoformat()))
    assert future.status_code == 422
    due_before = await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill(due_date=(TODAY - timedelta(days=5)).isoformat()))
    assert due_before.status_code == 422
    assert (await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill(amount="0"))).status_code == 422
    assert (await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill(kind="refund"))).status_code == 422
    client_only = Company(name=f"Client {_tag()}", assigned_recruiter_user_id=recruiter.id)
    db_session.add(client_only)
    await db_session.commit()
    assert (await client.post(f"{COMPANIES}/{client_only.id}/vendor-bills", json=_bill())).status_code == 422
    other_job = await _requirement(db_session, recruiter)
    wrong = await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill(requirement_id=str(other_job.id)))
    assert wrong.status_code == 422
    other_job.via_vendor_id = vendor.id
    await db_session.commit()
    right = await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill(requirement_id=str(other_job.id)))
    assert right.status_code == 201 and right.json()["bill"]["requirement"]["id"] == str(other_job.id)


@pytest.mark.asyncio
async def test_cancel_only_unpaid_and_no_payment_after(client, db_session):
    _, _, vendor = await _setup(client, db_session)
    bill = (await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill())).json()["bill"]
    paid = (await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill())).json()["bill"]
    await client.post(f"{BILLS}/{paid['id']}/payments", json={"paid_on": TODAY.isoformat(), "amount": "1.00"})
    refused = await client.post(f"{BILLS}/{paid['id']}/cancel", json={"reason": "Wrong amount"})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "bill_has_payments"
    assert (await client.post(f"{BILLS}/{bill['id']}/cancel", json={"reason": ""})).status_code == 422
    cancelled = await client.post(f"{BILLS}/{bill['id']}/cancel", json={"reason": "Raised twice"})
    assert cancelled.status_code == 200 and cancelled.json()["bill"]["payment_status"] == "cancelled"
    again = await client.post(f"{BILLS}/{bill['id']}/payments", json={"paid_on": TODAY.isoformat(), "amount": "1.00"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "bill_cancelled"
    totals = (await client.get(f"{COMPANIES}/{vendor.id}/vendor-bills")).json()["totals"]["payable"]
    assert totals["billed"] == "10000.00"  # the cancelled bill counts nowhere


# --- W4: grants and scope --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_grants_and_scope(client, db_session):
    _, recruiter, vendor = await _setup(client, db_session)
    bill = (await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill())).json()["bill"]
    db_session.add(UserPermissionOverride(user_id=recruiter.id, resource="commercials.vendor", action="edit", effect="deny", reason="pob-012 test"))
    await db_session.commit()
    assert (await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill())).status_code == 403
    assert (await client.post(f"{BILLS}/{bill['id']}/payments", json={"paid_on": TODAY.isoformat(), "amount": "1.00"})).status_code == 403
    read = (await client.get(f"{COMPANIES}/{vendor.id}/vendor-bills")).json()
    assert read["can_edit"] is False and read["items"][0]["permissions"] == {"can_pay": False, "can_cancel": False}
    db_session.add(UserPermissionOverride(user_id=recruiter.id, resource="commercials.vendor", action="view", effect="deny", reason="pob-012 test"))
    await db_session.commit()
    assert (await client.get(f"{COMPANIES}/{vendor.id}/vendor-bills")).status_code == 403
    assert (await client.get(f"{PERF}/performance")).status_code == 403
    assert (await client.get(f"{PERF}/{vendor.id}/performance")).status_code == 403
    other = await make_recruiter(db_session)
    await login(client, other)
    assert (await client.get(f"{COMPANIES}/{vendor.id}/vendor-bills")).status_code == 404
    assert (await client.post(f"{BILLS}/{bill['id']}/payments", json={"paid_on": TODAY.isoformat(), "amount": "1.00"})).status_code == 404
    assert (await client.get(f"{PERF}/{vendor.id}/performance")).status_code == 404


# --- W5: the ledger --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bill_payments_feed_the_ledger(client, db_session):
    _, _, vendor = await _setup(client, db_session)
    payable = (await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill())).json()["bill"]
    receivable = (await client.post(f"{COMPANIES}/{vendor.id}/vendor-bills", json=_bill(kind="receivable"))).json()["bill"]
    out = (await client.post(f"{BILLS}/{payable['id']}/payments", json={"paid_on": TODAY.isoformat(), "amount": "700.00"})).json()["bill"]["payments"][0]
    into = (await client.post(f"{BILLS}/{receivable['id']}/payments", json={"paid_on": TODAY.isoformat(), "amount": "300.00"})).json()["bill"]["payments"][0]
    from app.services import ledger

    table = ledger.lines()
    rows = {r.id: r for r in (await db_session.execute(select(table).where(table.c.id.in_([uuid.UUID(out["id"]), uuid.UUID(into["id"])])))).all()}
    paid, received = rows[uuid.UUID(out["id"])], rows[uuid.UUID(into["id"])]
    assert (paid.source, paid.kind, paid.vertical, str(paid.amount), paid.counted) == ("vendor_payment", "expense", "recruitment", "700.00", True)
    assert (received.source, received.kind, received.vertical, str(received.amount)) == ("vendor_receipt", "income", "recruitment", "300.00")
    assert payable["bill_number"] in paid.description and vendor.name not in paid.description


# --- W6/W7: performance ----------------------------------------------------------------------------------------------------------
async def _application(db, job, candidate, status, *, entered=()):
    application = JobApplication(job_id=job.id, candidate_id=candidate.id, status=status)
    db.add(application)
    await db.flush()
    for to_status in entered:
        db.add(JobApplicationStatusHistory(application_id=application.id, from_status="profile_shared", to_status=to_status))
    return application


async def _share(db, job, vendor, applications, by, at):
    share = ProfileShare(job_id=job.id, company_id=vendor.id, channel="email", shared_by_user_id=by.id, recipient="vendor", detail="anonymised")
    db.add(share)
    await db.flush()
    share.created_at = at
    for a in applications:
        db.add(ProfileShareItem(share_id=share.id, candidate_id=a.candidate_id, application_id=a.id))
    await db.flush()


@pytest.mark.asyncio
async def test_metrics_tie_out_to_the_drill_down(client, db_session):
    _, recruiter, vendor = await _setup(client, db_session)
    start = datetime.now(UTC) - timedelta(days=10)
    job = await _requirement(db_session, recruiter)
    job.via_vendor_id, job.created_at = vendor.id, start
    idle = await _requirement(db_session, recruiter)  # via the vendor, never shared: counted, no response time
    idle.via_vendor_id = vendor.id
    people = [await _candidate(db_session, recruiter) for _ in range(4)]
    a_join = await _application(db_session, job, people[0], "joined", entered=("interview", "selected"))
    a_sel = await _application(db_session, job, people[1], "rejected", entered=("interview", "selected"))
    a_int = await _application(db_session, job, people[2], "rejected", entered=("interview",))
    a_new = await _application(db_session, job, people[3], "profile_shared")
    await _share(db_session, job, vendor, [a_join, a_sel], recruiter, start + timedelta(hours=6))
    await _share(db_session, job, vendor, [a_int, a_new, a_join], recruiter, start + timedelta(hours=30))  # a_join again: counted once
    await db_session.commit()
    detail = await client.get(f"{PERF}/{vendor.id}/performance")
    assert detail.status_code == 200, detail.text
    d = detail.json()
    m = d["metrics"]
    assert (m["requirements"], m["responded_requirements"], m["avg_response_hours"]) == (2, 1, "6.0")
    assert (m["submitted"], m["interviewed"], m["placed"], m["joined"]) == (4, 3, 2, 1)
    assert (m["interview_rate"], m["joining_rate"]) == ("75.0", "50.0")
    # tie-out: each figure equals its drill-down count
    assert len(d["requirements"]) == m["requirements"] and sum(r["response_hours"] is not None for r in d["requirements"]) == m["responded_requirements"]
    subs = d["submissions"]
    assert len(subs) == m["submitted"] and sum(s["interviewed"] for s in subs) == m["interviewed"]
    assert sum(s["placed"] for s in subs) == m["placed"] and sum(s["joined"] for s in subs) == m["joined"]
    page = (await client.get(f"{PERF}/performance", params={"limit": 200})).json()
    row = next(r for r in page["items"] if r["vendor"]["id"] == str(vendor.id))
    assert row["metrics"] == m


@pytest.mark.asyncio
async def test_a_vendor_with_no_submissions_shows_null_rates(client, db_session):
    _, _, vendor = await _setup(client, db_session)
    m = (await client.get(f"{PERF}/{vendor.id}/performance")).json()["metrics"]
    assert (m["submitted"], m["interview_rate"], m["joining_rate"], m["avg_response_hours"]) == (0, None, None, None)


# --- W10: the migration ----------------------------------------------------------------------------------------------------------
def test_the_migration_repeats_the_model_checks():
    path = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0314_vendor_bills.py"
    spec = importlib.util.spec_from_file_location("m0314", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.BILL_CHECKS == models.VENDOR_BILL_CHECKS and module.PAYMENT_CHECKS == models.VENDOR_BILL_PAYMENT_CHECKS
    assert module.down_revision == "0313_submissions"
