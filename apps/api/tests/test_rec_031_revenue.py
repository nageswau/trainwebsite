"""rec-031 -- revenue / commercial tracking, track only (spec §1-§3; AC1-AC3; DEC-SCOPE-176 RV1-RV10). The shared test database is never
truncated, so every value is unique per test and every list assertion is scoped to the test's own requirement."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company, Job, JobApplication, JobApplicationStatusHistory, JobOffer, RecruiterContract, RecruiterPayment
from app.services.recruiter_requirements import ist_today
from tests.rec001_helpers import as_role, login, make_recruiter
from tests.test_rec_017_tracking import _candidate, _requirement, _team

REQ = "/api/v1/recruiter/requirements"
INVOICES = "/api/v1/recruiter/invoices"
COMPANIES = "/api/v1/recruiter/companies"
TODAY = ist_today()


def _number() -> str:
    return f"INV-{uuid.uuid4().hex[:10]}"


async def _hire(db, job: Job, creator, status="joined", compensation=600000, currency="INR", joining_status="joined") -> JobApplication:
    """A candidate on the requirement at `status`; with `compensation`, an accepted offer whose joining is `joining_status`."""
    candidate = await _candidate(db, creator)
    application = JobApplication(job_id=job.id, candidate_id=candidate.id, status=status, added_by_user_id=creator.id)
    db.add(application)
    await db.flush()
    if compensation is not None:
        db.add(
            JobOffer(
                application_id=application.id,
                compensation=compensation,
                currency=currency,
                status="accepted",
                joining_status=joining_status,
                actual_joining_date=TODAY if joining_status == "joined" else None,
                not_joined_reason="Took another offer" if joining_status == "did_not_join" else None,
            )
        )
    await db.commit()
    return application


async def _contract(db, job: Job, creator, basis="fixed", value="50000"):
    """RV1: the company's current contract, at any status (Discussion here), carries the fee per hire."""
    db.add(RecruiterContract(company_id=job.company_id, created_by_user_id=creator.id, status="discussion", fee_basis=basis, fee_value=Decimal(value), is_current=True))
    await db.commit()


async def _setup(client, db, *, hires=0):
    manager, recruiter = await _team(client, db)
    job = await _requirement(db, recruiter)
    for _ in range(hires):
        await _hire(db, job, recruiter)
    return manager, recruiter, job


async def _revenue(client, job) -> dict:
    response = await client.get(f"{REQ}/{job.id}/revenue")
    assert response.status_code == 200, response.text
    return response.json()


async def _invoice(client, job, **over):
    body = {"requirement_id": str(job.id), "invoice_number": _number(), "invoice_date": TODAY.isoformat(), "due_date": (TODAY + timedelta(days=30)).isoformat(), "amount": "150000"} | over
    return await client.post(INVOICES, json=body)


async def _pay(client, invoice_id, amount, **over):
    return await client.post(f"{INVOICES}/{invoice_id}/payments", json={"received_on": TODAY.isoformat(), "amount": amount} | over)


def _field(response) -> str:
    return response.json()["detail"][0]["loc"][-1]


# --- the §23 figures (AC1, AC3, RV1-RV5) ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_source_scenario_three_joined_at_50000_invoiced_and_part_paid(client, db_session):
    """Backlog positive scenario: 3 joined × ₹50,000 = ₹1,50,000 invoiced; ₹1,00,000 received → ₹50,000 outstanding (AC1)."""
    manager, recruiter, job = await _setup(client, db_session, hires=3)
    await _contract(db_session, job, recruiter)
    r = await _revenue(client, job)
    assert (r["selected"], r["joined"]) == (3, 3)
    assert r["fee"] == {"basis": "fixed", "value": "50000.00", "source": "contract", "contract_status_label": "Discussion", "override": None}
    assert r["expected_revenue"] == "150000.00" and r["unpriced_hires"] == 0 and len(r["hires"]) == 3
    assert all(h["fee"] == "50000.00" and h["joined_on"] == TODAY.isoformat() for h in r["hires"])
    created = await _invoice(client, job, amount="150000")
    assert created.status_code == 201, created.text
    invoice = created.json()["invoice"]
    assert (invoice["amount"], invoice["received"], invoice["outstanding"], invoice["payment_status"]) == ("150000.00", "0.00", "150000.00", "unpaid")
    paid = await _pay(client, invoice["id"], "100000", reference="UTR 123")
    assert paid.status_code == 201, paid.text
    invoice = paid.json()["invoice"]
    assert (invoice["received"], invoice["outstanding"], invoice["payment_status"], invoice["payment_status_label"]) == ("100000.00", "50000.00", "part_paid", "Part paid")
    assert invoice["payments"][0]["reference"] == "UTR 123"
    r = await _revenue(client, job)
    assert (r["invoiced"], r["received"], r["outstanding"], r["over_invoiced"]) == ("150000.00", "100000.00", "50000.00", False)
    assert [i["id"] for i in r["invoices"]] == [invoice["id"]]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_revenue.payment_recorded", AuditLog.entity_id == invoice["id"]))
    assert audit.metadata_json == {"job_id": str(job.id), "payment_id": invoice["payments"][0]["id"], "amount": "100000.00"}


@pytest.mark.asyncio
async def test_revenue_counts_joined_only(client, db_session):
    """AC3: Selected, Did Not Join (application withdrawn) and an accepted-but-pending joining add nothing to expected revenue."""
    _, recruiter, job = await _setup(client, db_session, hires=1)
    await _contract(db_session, job, recruiter)
    selected = await _hire(db_session, job, recruiter, status="selected", joining_status="pending")
    await _hire(db_session, job, recruiter, status="withdrawn", joining_status="did_not_join")
    await _hire(db_session, job, recruiter, status="interview", compensation=None)
    db_session.add(JobApplicationStatusHistory(application_id=selected.id, from_status="shortlisted", to_status="selected"))
    await db_session.commit()
    r = await _revenue(client, job)
    assert r["joined"] == 1 and r["expected_revenue"] == "50000.00" and len(r["hires"]) == 1
    assert r["selected"] == 2  # the joined hire (legacy row, no history) and the one now Selected


@pytest.mark.asyncio
async def test_selected_counts_an_application_that_entered_selected_and_moved_on(client, db_session):
    _, recruiter, job = await _setup(client, db_session)
    gone = await _hire(db_session, job, recruiter, status="withdrawn", joining_status="did_not_join")
    db_session.add(JobApplicationStatusHistory(application_id=gone.id, from_status="interview", to_status="selected"))
    await db_session.commit()
    r = await _revenue(client, job)
    assert (r["selected"], r["joined"], r["expected_revenue"]) == (1, 0, None)  # RV1: no fee anywhere -> no expected revenue
    assert r["fee"] == {"basis": None, "value": None, "source": None, "contract_status_label": None, "override": None}


@pytest.mark.asyncio
async def test_percent_of_ctc_prices_each_hire_and_flags_hires_without_an_inr_ctc(client, db_session):
    _, recruiter, job = await _setup(client, db_session)
    await _contract(db_session, job, recruiter, basis="percent_of_ctc", value="8.33")
    await _hire(db_session, job, recruiter, compensation=600000)
    await _hire(db_session, job, recruiter, compensation=1000000)
    await _hire(db_session, job, recruiter, compensation=900000, currency="USD")
    await _hire(db_session, job, recruiter, compensation=None)  # legacy Joined without an offer
    r = await _revenue(client, job)
    assert r["joined"] == 4 and r["unpriced_hires"] == 2
    assert sorted(h["fee"] for h in r["hires"] if h["fee"]) == ["49980.00", "83300.00"]
    assert r["expected_revenue"] == "133280.00"


@pytest.mark.asyncio
async def test_the_requirement_override_wins_and_only_the_manager_sets_it(client, db_session):
    manager, recruiter, job = await _setup(client, db_session, hires=2)
    await _contract(db_session, job, recruiter)
    refused = await client.put(f"{REQ}/{job.id}/fee", json={"fee_basis": "fixed", "fee_value": "60000"})
    assert refused.status_code == 403  # RV10: a pricing exception is the manager's
    assert (await _revenue(client, job))["permissions"] == {"can_invoice": True, "can_set_fee": False}
    await login(client, manager)
    response = await client.put(f"{REQ}/{job.id}/fee", json={"fee_basis": "fixed", "fee_value": "60000"})
    assert response.status_code == 200, response.text
    r = response.json()
    assert r["fee"]["source"] == "requirement" and r["fee"]["override"] == {"basis": "fixed", "value": "60000.00"} and r["expected_revenue"] == "120000.00"
    assert r["permissions"] == {"can_invoice": True, "can_set_fee": True}
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_revenue.fee_set", AuditLog.entity_id == str(job.id)))
    assert audit.metadata_json == {"from": None, "to": {"basis": "fixed", "value": "60000.00"}}
    cleared = (await client.put(f"{REQ}/{job.id}/fee", json={"fee_basis": None, "fee_value": None})).json()
    assert cleared["fee"]["source"] == "contract" and cleared["expected_revenue"] == "100000.00"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"fee_basis": "fixed", "fee_value": "-1"}, "fee_value"),
        ({"fee_basis": "percent_of_ctc", "fee_value": "101"}, "fee_value"),
        ({"fee_basis": "fixed", "fee_value": None}, "fee_value"),
        ({"fee_basis": None, "fee_value": "10"}, "fee_basis"),
        ({"fee_basis": "hourly", "fee_value": "10"}, "fee_basis"),
        ({"fee_basis": "fixed", "fee_value": "1.234"}, "fee_value"),
    ],
)
async def test_fee_override_validation_422(client, db_session, body, field):
    manager, _, job = await _setup(client, db_session)
    await login(client, manager)
    response = await client.put(f"{REQ}/{job.id}/fee", json=body)
    assert response.status_code == 422 and _field(response) == field, response.text


# --- invoices and payments (AC1, AC2, RV6-RV9) -----------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"amount": "-5000"}, "amount"),  # backlog negative scenario
        ({"amount": "0"}, "amount"),
        ({"amount": "12.345"}, "amount"),
        ({"invoice_number": "  "}, "invoice_number"),
        ({"invoice_number": "x" * 41}, "invoice_number"),
        ({"invoice_date": (TODAY + timedelta(days=2)).isoformat()}, "invoice_date"),
        ({"due_date": (TODAY - timedelta(days=1)).isoformat()}, "due_date"),
        ({"note": "y" * 501}, "note"),
    ],
)
async def test_invoice_validation_422(client, db_session, over, field):
    _, _, job = await _setup(client, db_session)
    response = await _invoice(client, job, **over)
    assert response.status_code == 422 and _field(response) == field, response.text


@pytest.mark.asyncio
async def test_blank_required_text_says_it_is_required(client, db_session):
    """QA31-01: the form sends null for a blank field; the message names the field instead of the parser's "valid string"."""
    _, _, job = await _setup(client, db_session)
    for blank in (None, "", "   "):
        response = await _invoice(client, job, invoice_number=blank)
        assert response.status_code == 422 and _field(response) == "invoice_number"
        assert response.json()["detail"][0]["msg"].endswith("Invoice number is required"), response.text
    invoice = (await _invoice(client, job, amount="10")).json()["invoice"]
    response = await client.post(f"{INVOICES}/{invoice['id']}/cancel", json={"reason": None})
    assert response.status_code == 422 and response.json()["detail"][0]["msg"].endswith("Reason is required"), response.text


@pytest.mark.asyncio
async def test_invoice_numbers_are_unique_ignoring_case(client, db_session):
    _, _, job = await _setup(client, db_session)
    number = _number()
    assert (await _invoice(client, job, invoice_number=number)).status_code == 201
    taken = await _invoice(client, job, invoice_number=f"  {number.lower()} ")
    assert taken.status_code == 409 and taken.json()["detail"]["code"] == "invoice_number_taken"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"amount": "-1"}, "amount"),
        ({"amount": "0"}, "amount"),
        ({"received_on": (TODAY + timedelta(days=2)).isoformat()}, "received_on"),
        ({"received_on": (TODAY - timedelta(days=11)).isoformat()}, "received_on"),  # before the invoice date
        ({"reference": "r" * 101}, "reference"),
    ],
)
async def test_payment_validation_422(client, db_session, over, field):
    _, _, job = await _setup(client, db_session)
    invoice = (await _invoice(client, job, invoice_date=(TODAY - timedelta(days=10)).isoformat(), amount="1000")).json()["invoice"]
    response = await _pay(client, invoice["id"], **({"amount": "10"} | over))
    assert response.status_code == 422 and _field(response) == field, response.text


@pytest.mark.asyncio
async def test_payments_cannot_exceed_the_invoice(client, db_session):
    """AC2 (RV7): over-payment is refused, naming what is outstanding; paying exactly the rest settles the invoice."""
    _, _, job = await _setup(client, db_session)
    invoice = (await _invoice(client, job, amount="1000")).json()["invoice"]
    assert (await _pay(client, invoice["id"], "600")).status_code == 201
    over = await _pay(client, invoice["id"], "400.01")
    assert over.status_code == 422 and _field(over) == "amount" and "₹400.00" in over.json()["detail"][0]["msg"]
    settled = (await _pay(client, invoice["id"], "400")).json()["invoice"]
    assert (settled["outstanding"], settled["payment_status"], settled["permissions"]) == ("0.00", "paid", {"can_pay": False, "can_cancel": False})
    assert (await _pay(client, invoice["id"], "0.01")).status_code == 422
    rows = (await db_session.execute(select(RecruiterPayment.amount).where(RecruiterPayment.invoice_id == uuid.UUID(invoice["id"])))).scalars().all()
    assert sorted(rows) == [Decimal("400.00"), Decimal("600.00")]


@pytest.mark.asyncio
async def test_cancel_an_unpaid_invoice_and_its_rules(client, db_session):
    """RV8: never edited or deleted; an unpaid invoice is cancelled with a reason, counts nowhere, and keeps its number."""
    _, _, job = await _setup(client, db_session)
    number = _number()
    invoice = (await _invoice(client, job, invoice_number=number, amount="5000")).json()["invoice"]
    assert (await client.post(f"{INVOICES}/{invoice['id']}/cancel", json={"reason": "x"})).status_code == 422
    cancelled = await client.post(f"{INVOICES}/{invoice['id']}/cancel", json={"reason": "Wrong amount"})
    assert cancelled.status_code == 200, cancelled.text
    c = cancelled.json()["invoice"]
    assert (c["payment_status"], c["cancel_reason"], c["overdue"], c["permissions"]) == ("cancelled", "Wrong amount", False, {"can_pay": False, "can_cancel": False})
    assert (await client.post(f"{INVOICES}/{invoice['id']}/cancel", json={"reason": "Again"})).status_code == 409
    assert (await _pay(client, invoice["id"], "10")).status_code == 409
    r = await _revenue(client, job)
    assert (r["invoiced"], r["outstanding"]) == ("0.00", "0.00") and r["invoices"][0]["payment_status"] == "cancelled"
    assert (await _invoice(client, job, invoice_number=number)).status_code == 409
    paid = (await _invoice(client, job, amount="100")).json()["invoice"]
    await _pay(client, paid["id"], "10")
    refused = await client.post(f"{INVOICES}/{paid['id']}/cancel", json={"reason": "Too late"})
    assert refused.status_code == 409


@pytest.mark.asyncio
async def test_did_not_join_after_invoicing_flags_over_invoicing(client, db_session):
    """RV9: an invoice is never changed automatically; the view says when open invoices exceed expected revenue."""
    _, recruiter, job = await _setup(client, db_session, hires=1)
    await _contract(db_session, job, recruiter)
    await _invoice(client, job, amount="100000")  # invoiced for two hires
    r = await _revenue(client, job)
    assert r["expected_revenue"] == "50000.00" and r["over_invoiced"] is True


# --- receivables and the company view ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_receivables_list_views_counts_and_overdue(client, db_session):
    _, _, job = await _setup(client, db_session)
    old = (TODAY - timedelta(days=40)).isoformat()
    overdue = (await _invoice(client, job, invoice_date=old, due_date=(TODAY - timedelta(days=10)).isoformat(), amount="300")).json()["invoice"]
    due = (await _invoice(client, job, amount="200")).json()["invoice"]
    paid = (await _invoice(client, job, amount="100")).json()["invoice"]
    await _pay(client, paid["id"], "100")
    cancelled = (await _invoice(client, job, amount="50")).json()["invoice"]
    await client.post(f"{INVOICES}/{cancelled['id']}/cancel", json={"reason": "Duplicate"})
    assert overdue["overdue"] is True and due["overdue"] is False

    async def ids(view):
        body = (await client.get(f"{INVOICES}?view={view}&limit=100&company_id={job.company_id}")).json()
        return body, [i["id"] for i in body["items"] if i["requirement"]["id"] == str(job.id)]

    body, mine = await ids("outstanding")
    assert mine == [overdue["id"], due["id"]]  # due date ascending
    assert set(body["counts"]) == {"outstanding", "overdue", "paid", "cancelled"} and Decimal(body["outstanding_total"]) >= Decimal("500")
    assert (await ids("overdue"))[1] == [overdue["id"]]
    assert (await ids("paid"))[1] == [paid["id"]]
    assert (await ids("cancelled"))[1] == [cancelled["id"]]
    assert (await client.get(f"{INVOICES}?view=everything")).status_code == 422


@pytest.mark.asyncio
async def test_the_company_view_totals_its_requirements(client, db_session):
    _, recruiter, job = await _setup(client, db_session, hires=2)
    await _contract(db_session, job, recruiter)
    company = await db_session.get(Company, job.company_id)
    second = await _requirement(db_session, recruiter, company=company)
    await _hire(db_session, second, recruiter)
    invoice = (await _invoice(client, job, amount="100000")).json()["invoice"]
    await _pay(client, invoice["id"], "40000")
    response = await client.get(f"{COMPANIES}/{job.company_id}/revenue")
    assert response.status_code == 200, response.text
    body = response.json()
    rows = {row["requirement"]["id"]: row for row in body["requirements"]}
    assert set(rows) == {str(job.id), str(second.id)}
    assert (rows[str(job.id)]["joined"], rows[str(job.id)]["expected_revenue"], rows[str(job.id)]["outstanding"]) == (2, "100000.00", "60000.00")
    assert rows[str(second.id)]["expected_revenue"] == "50000.00"
    assert body["totals"] == {"selected": 3, "joined": 3, "expected_revenue": "150000.00", "invoiced": "100000.00", "received": "40000.00", "outstanding": "60000.00"}


# --- roles and scope (RV10) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_another_recruiter_gets_404_everywhere(client, db_session):
    manager, _, job = await _setup(client, db_session)
    invoice = (await _invoice(client, job, amount="100")).json()["invoice"]
    await login(client, await make_recruiter(db_session, manager))
    assert (await client.get(f"{REQ}/{job.id}/revenue")).status_code == 404
    assert (await _invoice(client, job)).status_code == 404
    assert (await _pay(client, invoice["id"], "1")).status_code == 404
    assert (await client.post(f"{INVOICES}/{invoice['id']}/cancel", json={"reason": "Not mine"})).status_code == 404
    assert (await client.get(f"{COMPANIES}/{job.company_id}/revenue")).status_code == 404
    assert all(i["id"] != invoice["id"] for i in (await client.get(f"{INVOICES}?limit=100&company_id={job.company_id}")).json()["items"])


@pytest.mark.asyncio
async def test_the_manager_records_invoices_for_the_team(client, db_session):
    manager, _, job = await _setup(client, db_session)
    await login(client, manager)
    invoice = await _invoice(client, job, amount="100")
    assert invoice.status_code == 201
    assert (await _pay(client, invoice.json()["invoice"]["id"], "100")).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("bdm", "it"), ("hr_team", "it"), ("student", "it"), ("employer", "it")])
async def test_other_roles_are_refused(client, db_session, role, division):
    _, _, job = await _setup(client, db_session)
    actor = await as_role(client, db_session, role, division)
    if role == "bdm":  # R10 reads the requirement, but revenue is not the BDM's (RV10)
        company = await db_session.get(Company, job.company_id)
        company.assigned_bdm_user_id = actor.id
        await db_session.commit()
    assert (await client.get(f"{REQ}/{job.id}/revenue")).status_code == 403
    assert (await _invoice(client, job)).status_code == 403
    assert (await client.get(INVOICES)).status_code == 403
