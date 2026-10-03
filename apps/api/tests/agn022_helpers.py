"""AGN-022 fixture: AGN-018's dashboard world (hand counts in agn018_helpers), plus a deactivated staff member, deposits in every
state that matters and an empty organisation. Expected figures are worked out next to the rows that produce them."""

from datetime import UTC, date, datetime
from decimal import Decimal

from tests.agn001_helpers import mk_active_org, uniq
from tests.agn004_helpers import mk_staff
from tests.agn011_helpers import mk_deposit, mk_deposit_payment
from tests.agn018_helpers import dashboard_world

ORGS = "/api/v1/overseas-admin/agent-orgs"
DETAIL = ORGS + "/{oid}"
STUDENTS = ORGS + "/{oid}/students"
APPLICATIONS = ORGS + "/{oid}/applications"


async def mk_paid_deposit(db, app, *, by, amount: str, status: str, **fields):
    """A deposit captured through a paid payment, then moved to `status` with the fields its check constraints require."""
    deposit = await mk_deposit(db, app, by=by, amount=amount)
    payment = await mk_deposit_payment(db, deposit, by, status="paid", active=False)
    deposit.status, deposit.paid_payment_id, deposit.paid_at = status, payment.id, datetime.now(UTC)
    for key, value in fields.items():
        setattr(deposit, key, value)
    await db.commit()
    return deposit


async def network_world(db) -> dict:
    w = await dashboard_world(db)
    s4 = await mk_staff(db, w["org"], full_name="Staff Four", active=False)  # deactivated: not in staff_count
    a1, a3, a4 = w["apps"]["a1"], w["apps"]["a3"], w["apps"]["a4"]
    by = w["master"]
    await mk_deposit(db, a1, by=by, amount="10000.00", status="pending")  # pending: excluded everywhere
    await mk_paid_deposit(db, a3, by=by, amount="30000.00", status="remitted", remitted_at=date.today(), remittance_reference="UTR 1")
    await mk_paid_deposit(db, a4, by=by, amount="20000.00", status="refunded", refunded_at=date.today(), refund_amount=Decimal("5000.00"), refund_reason="Visa refused")
    empty = await mk_active_org(db, name=f"Empty {uniq()}")
    return w | {"s4": s4, "empty": empty}


# Staff s1 s2 s3 (s4 deactivated); students / applications / enrollments = agn018 MASTER.
NETWORK = {"staff_count": 3, "students": 4, "applications": 7, "enrollments": 1}
ZERO = {"staff_count": 0, "students": 0, "applications": 0, "enrollments": 0}
# Commission (agn018): claimable INR 1000 (a2 eligible) + USD 200 (a1 estimated); claims 1 (a3); revenue INR 12000 (a4), USD 500 (a8).
COMMISSION = {
    "claimable": [{"currency": "INR", "count": 1, "amount": 1000.0}, {"currency": "USD", "count": 1, "amount": 200.0}],
    "claims": 1,
    "revenue": [{"currency": "INR", "count": 1, "amount": 12000.0}, {"currency": "USD", "count": 1, "amount": 500.0}],
}
# Deposits: collected = remitted a3 30000 + refunded a4 20000 (count 2); refunded amount = 5000; pending a1 excluded.
DEPOSITS = {"currency": "INR", "count": 2, "collected": 50000.0, "remitted": 30000.0, "refunded": 5000.0}
