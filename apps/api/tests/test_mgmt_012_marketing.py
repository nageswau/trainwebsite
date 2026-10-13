"""mgmt-012 -- marketing budget, spend, ROI (spec MK1-MK14; AC1 the source's Instagram row computes ROI from its figures, AC2 spend never
double-counts, negative: a budget for an unknown channel -> 422, edge: zero spend -> ROI "—").

The stack DB is shared and never emptied, so each test works in a random far-past month and compares the figures before and after adding
its own rows."""

import random
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry, LeadStageHistory, LedgerCategory, LedgerEntry, Payment, Receipt, TelCampaign, TelProduct
from app.services import management_marketing
from tests.bdm001_helpers import login, make_user
from tests.test_mgmt_005_auto_lines import trip_expense

MARKETING = "/api/v1/management/marketing"
BUDGETS = "/api/v1/management/marketing/budgets"
D = Decimal


def tag() -> str:
    return uuid.uuid4().hex[:8]


def a_month() -> tuple[int, int]:
    return random.randint(2001, 2025), random.randint(1, 12)


def month_param(year: int, number: int) -> str:
    return f"{year:04d}-{number:02d}"


def at(year: int, number: int, day: int, hour: int = 6) -> datetime:
    return datetime(year, number, day, hour, tzinfo=UTC)  # 06:00 UTC is the same day in IST


async def as_user(client, db, role: str = "accountant"):
    user = await make_user(db, role, "global")
    await login(client, user)
    return user


async def view(client, month: str) -> dict:
    response = await client.get(MARKETING, params={"month": month})
    assert response.status_code == 200, response.text
    return response.json()


def row(out: dict, channel: str) -> dict:
    return next(r for r in out["channels"] if r["channel"] == channel)


def moved(before: dict, after: dict, channel: str, key: str) -> D:
    return D(str(row(after, channel)[key])) - D(str(row(before, channel)[key]))


# --- data builders ---------------------------------------------------------------------------------------------------------------
async def lead(db, source: str, created: datetime, *, campaign_id=None, qualified: datetime | None = None, converted: datetime | None = None,
               student=None, status: str | None = None) -> Enquiry:  # fmt: skip
    """A lead created at `created`; `qualified` adds a history step to Qualified; `converted` links `student` and records the conversion."""
    row = Enquiry(division="it", name=f"Lead {tag()}", subject="Course", message="", source=source, status=status or "new", campaign_id=campaign_id, created_at=created)
    if converted is not None:
        admin = await make_user(db, "it_admin", "it")
        student = student or await make_user(db, "it_student", "it")
        row.status = status or "converted"
        row.converted_user_id, row.converted_at, row.converted_by_user_id = student.id, converted, admin.id
    db.add(row)
    await db.flush()
    if qualified is not None:
        db.add(LeadStageHistory(lead_id=row.id, from_stage="contacted", to_stage="qualified", event="manual", created_at=qualified))
    if converted is not None and row.status == "converted":
        db.add(LeadStageHistory(lead_id=row.id, from_stage="application_enrollment", to_stage="converted", event="converted", created_at=converted))
    await db.commit()
    return row


async def paid(db, user_id, amount: str, on: datetime, *, currency: str = "INR", reference_type: str = "enrollment_fee", status: str = "paid") -> None:
    payment = Payment(user_id=user_id, division="it", reference_type=reference_type, amount=D(amount), currency=currency, status=status)
    db.add(payment)
    await db.flush()
    db.add(Receipt(payment_id=payment.id, user_id=user_id, division="it", receipt_no=f"RC-T-{tag()}", amount=payment.amount, currency=currency, file_url="receipts/t.pdf", issued_at=on))
    await db.commit()


async def expense(db, year: int, number: int, amount: str, *, channel: str | None, status: str = "approved", reversal_of_id=None, category: str = "Marketing") -> LedgerEntry:
    category_id = await db.scalar(select(LedgerCategory.id).where(LedgerCategory.kind == "expense", LedgerCategory.name == category))
    author = await make_user(db, "accountant", "global")
    entry = LedgerEntry(entry_date=date(year, number, 10), kind="expense", category_id=category_id, amount=D(amount), description="Test", vertical="shared",
                        channel=channel, status=status, reversal_of_id=reversal_of_id, created_by_user_id=author.id, updated_by_user_id=author.id)  # fmt: skip
    db.add(entry)
    await db.commit()
    return entry


# --- AC1: the source's Instagram row ---------------------------------------------------------------------------------------------
def test_ac1_roi_of_the_source_instagram_row():
    # §10: Instagram spent ₹85K and brought ₹5L of revenue -> (5,00,000 − 85,000) ÷ 85,000 × 100
    assert management_marketing.roi(D("500000"), D("85000")) == 488.2


def test_edge_zero_spend_has_no_roi():
    assert management_marketing.roi(D("4000"), D("0")) is None
    assert management_marketing.roi(D("0"), D("0")) is None


@pytest.mark.asyncio
async def test_ac1_the_instagram_row_through_the_api(client, db_session):
    await as_user(client, db_session)
    year, number = a_month()
    month = month_param(year, number)
    before = await view(client, month)
    await expense(db_session, year, number, "85000", channel="instagram")
    customer = await lead(db_session, "instagram", at(year, number, 2), converted=at(year, number, 3))
    await paid(db_session, customer.converted_user_id, "500000", at(year, number, 5))
    after = await view(client, month)
    assert moved(before, after, "instagram", "spend") == D("85000")
    assert moved(before, after, "instagram", "revenue") == D("500000")
    ig = row(after, "instagram")
    spend, revenue = D(ig["spend"]), D(ig["revenue"])
    assert ig["roi"] == management_marketing.roi(revenue, spend)
    assert ig["label"] == "Instagram"


# --- AC2: spend never double-counts -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac2_only_approved_channel_tagged_expenses_are_spend_once(client, db_session):
    await as_user(client, db_session)
    year, number = a_month()
    month = month_param(year, number)
    before = await view(client, month)
    tagged = await expense(db_session, year, number, "1000", channel="google")  # counts, in Google only
    await expense(db_session, year, number, "500", channel="google", status="draft")  # not approved
    await expense(db_session, year, number, "250", channel="google", status="submitted")  # not approved
    await expense(db_session, year, number, "700", channel=None)  # untagged marketing spend: no channel to put it in
    await trip_expense(db_session, on=date(year, number, 12), amount="1800.00")  # automatic line, no channel
    mid = await view(client, month)
    assert moved(before, mid, "google", "spend") == D("1000")
    assert D(mid["totals"]["spend"]) - D(before["totals"]["spend"]) == D("1000")
    assert sum(D(r["spend"]) for r in mid["channels"]) == D(mid["totals"]["spend"])
    await expense(db_session, year, number, "1000", channel="google", reversal_of_id=tagged.id)  # an approved reversal nets it out
    after = await view(client, month)
    assert moved(before, after, "google", "spend") == D("0")
    assert D(after["totals"]["spend"]) == D(before["totals"]["spend"])


# --- K3-K5: leads, qualified, customers -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_leads_qualified_and_customers_per_channel(client, db_session):
    await as_user(client, db_session)
    year, number = a_month()
    month = month_param(year, number)
    before = await view(client, month)
    await lead(db_session, "bdm", at(year, number, 1))  # a lead only
    await lead(db_session, "bdm", at(year, number, 2), qualified=at(year, number, 3))  # reached Qualified
    await lead(db_session, "bdm", at(year, number, 4), converted=at(year, number, 20))  # converted in the month: lead, qualified, customer
    prior = (year, number - 1) if number > 1 else (year - 1, 12)
    await lead(db_session, "bdm", at(*prior, 15), converted=at(year, number, 8))  # created earlier, converted now: a customer, not a lead
    await lead(db_session, "bdm", at(year, number, 5), status="qualified")  # its current stage is Qualified
    after = await view(client, month)
    assert moved(before, after, "bdm", "leads") == 4
    assert moved(before, after, "bdm", "qualified") == 3
    assert moved(before, after, "bdm", "customers") == 2
    assert after["totals"]["leads"] == sum(r["leads"] for r in after["channels"])
    bdm = row(after, "bdm")
    assert bdm["conversion"] == round(bdm["customers"] / bdm["leads"] * 100, 1)


# --- K6: revenue attribution ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_revenue_is_fees_paid_after_the_link_by_students_of_the_channels_converted_leads(client, db_session):
    await as_user(client, db_session)
    year, number = a_month()
    month = month_param(year, number)
    before = await view(client, month)
    customer = await lead(db_session, "referral", at(year, number, 1), converted=at(year, number, 10))
    sid = customer.converted_user_id
    await paid(db_session, sid, "4000", at(year, number, 12))  # counts
    await paid(db_session, sid, "999", at(year, number, 5))  # before the link: not marketing's
    await paid(db_session, sid, "50", at(year, number, 15), currency="USD")  # another currency: not counted
    await paid(db_session, sid, "7000", at(year, number, 15), reference_type="agent_deposit")  # pass-through
    await paid(db_session, sid, "300", at(year, number, 15), status="pending")  # not paid
    linked = await lead(db_session, "referral", at(year, number, 1), converted=at(year, number, 2), status="application_enrollment")
    await paid(db_session, linked.converted_user_id, "800", at(year, number, 12))  # linked but not converted
    after = await view(client, month)
    assert moved(before, after, "referral", "revenue") == D("4000")
    assert D(after["totals"]["revenue"]) - D(before["totals"]["revenue"]) == D("4000")


# --- §15 source groups and campaigns ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_source_groups_and_influencer_not_tracked(client, db_session):
    await as_user(client, db_session)
    year, number = a_month()
    month = month_param(year, number)
    before = await view(client, month)
    for source in ("instagram", "facebook", "whatsapp", "website", "exhibition_event", "college"):
        await lead(db_session, source, at(year, number, 3))
    after = await view(client, month)
    g0, g1 = before["groups"], after["groups"]
    assert g1["social"] - g0["social"] == 3
    assert g1["website"] - g0["website"] == 1
    assert g1["events"] - g0["events"] == 1
    assert g1["college"] - g0["college"] == 1
    assert g1["school"] - g0["school"] == 0 and g1["agent"] - g0["agent"] == 0
    assert g1["influencer"] is None


@pytest.mark.asyncio
async def test_campaigns_that_ran_or_brought_leads_in_the_month(client, db_session):
    await as_user(client, db_session)
    year, number = a_month()
    month = month_param(year, number)
    product = TelProduct(product_group="it", name=f"MK product {tag()}", team="it", active=True, sort_order=1000)
    db_session.add(product)
    await db_session.flush()
    running = TelCampaign(name=f"MK running {tag()}", source="facebook", product_id=product.id, start_date=date(year, number, 1))
    over = TelCampaign(name=f"MK over {tag()}", source="google", product_id=product.id, start_date=date(year - 1, 1, 1), end_date=date(year - 1, 2, 1))
    db_session.add_all([running, over])
    await db_session.commit()
    await lead(db_session, "facebook", at(year, number, 4), campaign_id=running.id, qualified=at(year, number, 5))
    await lead(db_session, "google", at(year, number, 4), campaign_id=over.id)  # ended, but brought a lead this month
    out = await view(client, month)
    names = {c["name"]: c for c in out["campaigns"]}
    assert names[running.name] | {"id": None} == {"id": None, "name": running.name, "channel": "facebook", "label": "Facebook", "active": True, "leads": 1, "qualified": 1, "customers": 0}
    assert names[over.name]["leads"] == 1
    later = await view(client, month_param(year + 1, number))  # neither runs nor has leads then
    assert running.name in {c["name"] for c in later["campaigns"]}  # open-ended: still running
    assert over.name not in {c["name"] for c in later["campaigns"]}


# --- MK11: access ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_super_admin_sees_lead_counts_and_no_money(client, db_session):
    await as_user(client, db_session, "super_admin")
    year, number = a_month()
    out = await view(client, month_param(year, number))
    assert out["money_visible"] is False
    for r in [*out["channels"], out["totals"]]:
        assert {r["budget"], r["spend"], r["revenue"], r["roi"]} == {None}
        assert isinstance(r["leads"], int)
    write = await client.put(BUDGETS, params={"month": month_param(year, number)}, json={"budgets": []})
    assert write.status_code == 403 and write.json()["detail"] == "Finance access required"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["it_admin", "telecaller_manager", "telecaller"])
async def test_other_roles_are_refused(client, db_session, role):
    await as_user(client, db_session, role)
    assert (await client.get(MARKETING)).status_code == 403
    assert (await client.put(BUDGETS, params={"month": "2020-01"}, json={"budgets": []})).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(MARKETING)).status_code == 401
    assert (await client.put(BUDGETS, params={"month": "2020-01"}, json={"budgets": []})).status_code == 401


@pytest.mark.asyncio
async def test_a_partner_reads_money(client, db_session):
    await as_user(client, db_session, "partner")
    out = await view(client, month_param(*a_month()))
    assert out["money_visible"] is True and out["totals"]["spend"] is not None


# --- MK3/MK4: budgets ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_put_replaces_the_months_budgets(client, db_session):
    await as_user(client, db_session)
    month = month_param(*a_month())
    first = await client.put(BUDGETS, params={"month": month}, json={"budgets": [{"channel": "instagram", "amount": "100000"}, {"channel": "google", "amount": "0"}]})
    assert first.status_code == 200, first.text
    assert row(first.json(), "instagram")["budget"] == "100000.00"
    assert row(first.json(), "google")["budget"] == "0.00"  # a budget of nothing, not "not set"
    assert row(first.json(), "school")["budget"] is None
    second = (await client.put(BUDGETS, params={"month": month}, json={"budgets": [{"channel": "google", "amount": "200000.50"}]})).json()
    assert row(second, "instagram")["budget"] is None and row(second, "google")["budget"] == "200000.50"
    assert second["totals"]["budget"] == "200000.50"
    assert second["budgets_updated_by"] is not None
    cleared = (await client.put(BUDGETS, params={"month": month}, json={"budgets": []})).json()
    assert {r["budget"] for r in cleared["channels"]} == {None} and cleared["totals"]["budget"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("budgets", "where"),
    [
        ([{"channel": "tiktok", "amount": "1"}], ["body", "budgets", 0, "channel"]),  # the backlog's negative case
        ([{"channel": "instagram", "amount": "-5"}], ["body", "budgets", 0, "amount"]),
        ([{"channel": "instagram", "amount": "1.005"}], ["body", "budgets", 0, "amount"]),
        ([{"channel": "instagram", "amount": "1"}, {"channel": "instagram", "amount": "2"}], ["body", "budgets"]),
    ],
)
async def test_budget_422s_name_their_field(client, db_session, budgets, where):
    await as_user(client, db_session)
    response = await client.put(BUDGETS, params={"month": "2019-03"}, json={"budgets": budgets})
    assert response.status_code == 422
    assert any(item["loc"][: len(where)] == where for item in response.json()["detail"]), response.text


@pytest.mark.asyncio
async def test_a_future_month_is_refused(client, db_session):
    await as_user(client, db_session, "partner")
    today = management_marketing.ledger.today()
    future = month_param(today.year + 1, today.month)
    assert (await client.get(MARKETING, params={"month": future})).status_code == 422
    assert (await client.put(BUDGETS, params={"month": future}, json={"budgets": []})).status_code == 422
    assert (await client.get(MARKETING, params={"month": "2026-13"})).status_code == 422


@pytest.mark.asyncio
async def test_a_save_is_audited_with_channel_names_and_no_amounts(client, db_session):
    user = await as_user(client, db_session)
    month = month_param(*a_month())
    body = {"budgets": [{"channel": "website", "amount": "1234"}, {"channel": "agent", "amount": "99"}]}
    assert (await client.put(BUDGETS, params={"month": month}, json=body)).status_code == 200
    assert (await client.put(BUDGETS, params={"month": month}, json=body)).status_code == 200  # no change: no second row
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_type == "mgmt.marketing_budget", AuditLog.user_id == user.id))).all()
    assert len(rows) == 1
    assert rows[0].entity_id == month
    assert rows[0].metadata_json["fields"] == ["website", "agent"]
    assert "1234" not in str(rows[0].metadata_json)


@pytest.mark.asyncio
async def test_the_audit_kind_is_finance_tier(client, db_session):
    await as_user(client, db_session, "super_admin")
    kinds = {k["value"] for k in (await client.get("/api/v1/management/activity")).json()["kinds"]}
    assert "mgmt.marketing_budget" not in kinds
