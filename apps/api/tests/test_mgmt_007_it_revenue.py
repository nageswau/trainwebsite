"""mgmt-007 -- the IT Training revenue dashboard (spec IR1-IR12; AC: course revenue = the sum of its batches, student counts =
enrolments), read with `GET /management/revenue/it` and its payments drill-down `GET /management/revenue/it/payments`.

The stack DB is shared and never emptied, so each test works in a random far-past month with its own courses and batches; per-course
figures are absolute, company-wide IT totals are compared before and after (deltas)."""

import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import Batch, Enrollment, Payment, Program, Receipt
from tests.bdm001_helpers import login, make_user
from tests.test_mgmt_004_ledger import TODAY, as_user, category, create, post
from tests.test_mgmt_005_auto_lines import ist, trip_expense
from tests.test_mgmt_010_expenses import seeded

REVENUE = "/api/v1/management/revenue/it"
PAYMENTS = f"{REVENUE}/payments"


def a_month() -> tuple[int, int]:
    return random.randint(2001, 2025), random.randint(1, 12)


def month_param(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def tag() -> str:
    return uuid.uuid4().hex[:8]


async def course(db, title: str | None = None, fees: str = "30000.00") -> Program:
    t = tag()
    program = Program(
        slug=f"mgmt007-{t}",
        category="Development",
        title=title or f"Course {t}",
        summary="s",
        duration="3 months",
        eligibility="any",
        fees=Decimal(fees),
        certification="c",
        curriculum=[],
        placement_assistance="p",
        trainer_name="t",
    )
    db.add(program)
    await db.commit()
    return program


async def batch(db, program: Program, name: str | None = None) -> Batch:
    item = Batch(program_id=program.id, name=name or f"Batch {tag()}", start_date=date(2020, 1, 1), end_date=date(2020, 4, 1), schedule="Mon-Fri")
    db.add(item)
    await db.commit()
    return item


async def enrol(db, item: Batch, on: date, status: str = "active") -> Enrollment:
    student = await make_user(db, "it_student", "it")
    enrolment = Enrollment(student_id=student.id, batch_id=item.id, enrollment_code=f"ENR-{tag()}", enrolled_on=on, status=status)
    db.add(enrolment)
    await db.commit()
    return enrolment


async def fee(
    db, enrolment: Enrollment | None, *, when, amount: str = "30000.00", reference_type: str = "enrollment_fee", currency: str = "INR", status: str = "paid", installment_no: int | None = None
) -> Payment:
    """A paid IT payment referencing `enrolment` (None: no reference, e.g. an IT service fee), with the receipt issued `when`."""
    payer_id = enrolment.student_id if enrolment else (await make_user(db, "it_student", "it")).id
    payment = Payment(
        user_id=payer_id,
        division="it",
        reference_type=reference_type,
        reference_id=enrolment.id if enrolment else None,
        amount=Decimal(amount),
        currency=currency,
        status=status,
        installment_no=installment_no,
    )
    db.add(payment)
    await db.flush()
    db.add(Receipt(payment_id=payment.id, user_id=payer_id, division="it", receipt_no=f"RCP-{tag()}", amount=payment.amount, currency=currency, file_url="receipts/test.pdf", issued_at=when))
    await db.commit()
    return payment


async def approved(client, db, category_id: str, on: date, amount: str, *, kind: str = "expense", vertical: str = "it", **tags) -> dict:
    """An accountant's entry, approved by a partner. Leaves the partner signed in."""
    await as_user(client, db)
    entry = await create(client, category_id, kind=kind, entry_date=on.isoformat(), amount=amount, vertical=vertical, **{k: str(v) for k, v in tags.items()})
    assert (await post(client, entry["id"], "submit")).status_code == 200
    await as_user(client, db, "partner")
    assert (await post(client, entry["id"], "approve")).status_code == 200
    return entry


async def dashboard(client, month: str | None = None, period: str | None = None) -> dict:
    params = {k: v for k, v in {"month": month, "period": period}.items() if v}
    response = await client.get(REVENUE, params=params or None)
    assert response.status_code == 200, response.text
    return response.json()


def course_row(data: dict, program: Program) -> dict:
    (row,) = [c for c in data["courses"] if c["program_id"] == str(program.id)]
    return row


def batch_row(row: dict, item: Batch) -> dict:
    (found,) = [b for b in row["batches"] if b["batch_id"] == str(item.id)]
    return found


def money(value) -> Decimal:
    return Decimal(value)


# --- access (IR, M13) ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partner", "accountant"])
async def test_finance_tier_reads_the_dashboard(client, db_session, role):
    await as_user(client, db_session, role)
    data = await dashboard(client)
    assert data["period"] == "month"
    assert [i["key"] for i in data["income"]] == ["enrolment_fees", "other_fees", "manual"]
    assert [c["key"] for c in data["costs"]] == ["trainer", "marketing", "operational"]
    assert data["placement"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [REVENUE, f"{PAYMENTS}?unlinked=true"])
@pytest.mark.parametrize(
    "role,division,detail", [("super_admin", "global", "Finance access required"), ("it_admin", "it", "Management access required"), ("student", "it", "Management access required")]
)
async def test_other_roles_are_refused(client, db_session, url, role, division, detail):
    await login(client, await make_user(db_session, role, division))
    response = await client.get(url)
    assert response.status_code == 403
    assert response.json()["detail"] == detail


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [REVENUE, f"{PAYMENTS}?unlinked=true"])
async def test_signed_out_is_401(client, url):
    assert (await client.get(url)).status_code == 401


# --- period and validation (IR1) ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_default_is_the_current_ist_month(client, db_session):
    await as_user(client, db_session)
    data = await dashboard(client)
    assert data["month"] == TODAY.strftime("%Y-%m")
    assert data["start"] == TODAY.replace(day=1).isoformat()


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"month": "2026-13"}, {"month": "abc"}, {"month": "1999-12"}, {"period": "week"}])
async def test_bad_period_is_422(client, db_session, params):
    await as_user(client, db_session)
    assert (await client.get(REVENUE, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_future_month_is_422(client, db_session):
    await as_user(client, db_session)
    future = (TODAY.replace(day=1) + timedelta(days=40)).strftime("%Y-%m")
    response = await client.get(REVENUE, params={"month": future})
    assert response.status_code == 422
    assert response.json()["detail"] == "Choose this month or an earlier one"


@pytest.mark.asyncio
async def test_year_period_spans_the_financial_year_to_date(client, db_session):
    await as_user(client, db_session)
    program = await course(db_session)
    item = await batch(db_session, program)
    year = random.randint(2001, 2024)
    first = await enrol(db_session, item, date(year, 4, 2))  # April: inside FY year-(year+1)
    await fee(db_session, first, when=ist(year, 4, 2), amount="1000.00")
    before = await enrol(db_session, item, date(year, 3, 30))  # March: the previous financial year
    await fee(db_session, before, when=ist(year, 3, 30), amount="500.00")
    data = await dashboard(client, month_param(year, 9), "year")
    assert data["start"] == date(year, 4, 1).isoformat()
    assert data["end"] == date(year, 9, 30).isoformat()
    assert data["label"] == f"Financial year {year}-{(year + 1) % 100:02d} to date"
    row = course_row(data, program)
    assert money(row["revenue"]) == Decimal("1000.00")
    assert row["enrolments"] == 1
    month = await dashboard(client, month_param(year, 9))
    assert all(c["program_id"] != str(program.id) for c in month["courses"])  # nothing in September itself


# --- attribution and figures (IR2-IR10, AC) -----------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_course_revenue_is_the_sum_of_its_batches_and_students_are_enrolments(client, db_session):
    year, month = a_month()
    on = date(year, month, 10)
    program = await course(db_session)
    first, second = await batch(db_session, program, "Morning"), await batch(db_session, program, "Evening")
    a = await enrol(db_session, first, on)
    b = await enrol(db_session, first, on, status="pending_consent")
    c = await enrol(db_session, second, on)
    await fee(db_session, a, when=ist(year, month, 10), amount="30000.00")
    await fee(db_session, b, when=ist(year, month, 11), amount="15000.00", installment_no=1)  # an EMI instalment
    await fee(db_session, c, when=ist(year, month, 12), amount="12000.00", reference_type="enrollment")  # the legacy reference type
    await fee(db_session, c, when=ist(year, month, 12), amount="9999.00", status="pending")  # unpaid: never counted

    await as_user(client, db_session)
    row = course_row(await dashboard(client, month_param(year, month)), program)
    assert money(batch_row(row, first)["revenue"]) == Decimal("45000.00")
    assert money(batch_row(row, second)["revenue"]) == Decimal("12000.00")
    assert money(row["revenue"]) == sum((money(b["revenue"]) for b in row["batches"]), Decimal(0)) + money(row["unbatched"]["revenue"]) == Decimal("57000.00")
    assert batch_row(row, first)["enrolments"] == 2
    assert batch_row(row, second)["enrolments"] == 1
    assert row["enrolments"] == 3
    assert row["title"] == program.title


@pytest.mark.asyncio
async def test_a_course_with_no_fee_lists_its_enrolments_at_zero(client, db_session):
    year, month = a_month()
    program = await course(db_session, fees="0")
    item = await batch(db_session, program)
    await enrol(db_session, item, date(year, month, 5))
    await as_user(client, db_session)
    row = course_row(await dashboard(client, month_param(year, month)), program)
    assert row["enrolments"] == 1
    assert money(row["revenue"]) == Decimal(0)


@pytest.mark.asyncio
async def test_tagged_costs_split_by_head_and_contribution(client, db_session):
    year, month = a_month()
    on = date(year, month, 8)
    program = await course(db_session)
    item = await batch(db_session, program)
    await fee(db_session, await enrol(db_session, item, on), when=ist(year, month, 8), amount="50000.00")
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    await approved(client, db_session, await seeded(client, "Trainer payments"), on, "20000.00", batch_id=item.id)
    await approved(client, db_session, await seeded(client, "Marketing"), on, "5000.00", program_id=program.id)  # course-level
    await approved(client, db_session, await seeded(client, "Software"), on, "1000.00")  # IT, no course
    after = await dashboard(client, month_param(year, month))

    row = course_row(after, program)
    assert money(batch_row(row, item)["costs"]) == Decimal("20000.00")
    assert money(row["unbatched"]["costs"]) == Decimal("5000.00")
    assert money(row["costs"]) == Decimal("25000.00")
    assert money(row["contribution"]) == Decimal("25000.00")

    def cost(data, key):
        (found,) = [c for c in data["costs"] if c["key"] == key]
        return money(found["amount"])

    assert cost(after, "trainer") - cost(before, "trainer") == Decimal("20000.00")
    assert cost(after, "marketing") - cost(before, "marketing") == Decimal("5000.00")
    assert cost(after, "operational") - cost(before, "operational") == Decimal("1000.00")
    assert money(after["unlinked"]["costs"]) - money(before["unlinked"]["costs"]) == Decimal("1000.00")
    assert money(after["totals"]["costs"]) - money(before["totals"]["costs"]) == Decimal("26000.00")


@pytest.mark.asyncio
async def test_income_kinds_unlinked_fees_and_manual_income(client, db_session):
    year, month = a_month()
    on = date(year, month, 20)
    program = await course(db_session)
    item = await batch(db_session, program)
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    await fee(db_session, await enrol(db_session, item, on), when=ist(year, month, 20), amount="40000.00")
    await fee(db_session, None, when=ist(year, month, 20), amount="2500.00", reference_type="service_fee")  # IT service fee: no course
    await as_user(client, db_session)
    income = await category(client, kind="income")
    await approved(client, db_session, income["id"], on, "7000.00", kind="income", batch_id=item.id)
    after = await dashboard(client, month_param(year, month))

    def kind(data, key):
        (found,) = [i for i in data["income"] if i["key"] == key]
        return money(found["amount"])

    assert kind(after, "enrolment_fees") - kind(before, "enrolment_fees") == Decimal("40000.00")
    assert kind(after, "other_fees") - kind(before, "other_fees") == Decimal("2500.00")
    assert kind(after, "manual") - kind(before, "manual") == Decimal("7000.00")
    assert money(after["unlinked"]["revenue"]) - money(before["unlinked"]["revenue"]) == Decimal("2500.00")
    assert money(batch_row(course_row(after, program), item)["revenue"]) == Decimal("47000.00")
    assert money(after["totals"]["revenue"]) - money(before["totals"]["revenue"]) == Decimal("49500.00")


@pytest.mark.asyncio
async def test_courses_plus_unlinked_reconcile_with_the_totals(client, db_session):
    year, month = a_month()
    on = date(year, month, 3)
    program = await course(db_session)
    item = await batch(db_session, program)
    await fee(db_session, await enrol(db_session, item, on), when=ist(year, month, 3), amount="11000.00")
    await fee(db_session, None, when=ist(year, month, 3), amount="900.00", reference_type="service_fee")
    await as_user(client, db_session)
    data = await dashboard(client, month_param(year, month))
    for field in ("revenue", "costs"):
        courses = sum((money(c[field]) for c in data["courses"]), Decimal(0))
        assert courses + money(data["unlinked"][field]) == money(data["totals"][field])
    assert money(data["totals"]["contribution"]) == money(data["totals"]["revenue"]) - money(data["totals"]["costs"])
    assert data["totals"]["enrolments"] == sum(c["enrolments"] for c in data["courses"])
    assert money(data["totals"]["revenue"]) == sum((money(i["amount"]) for i in data["income"]), Decimal(0))
    assert money(data["totals"]["costs"]) == sum((money(c["amount"]) for c in data["costs"]), Decimal(0))


@pytest.mark.asyncio
async def test_unapproved_reversed_other_vertical_and_foreign_money_are_excluded(client, db_session):
    year, month = a_month()
    on = date(year, month, 14)
    program = await course(db_session)
    item = await batch(db_session, program)
    enrolment = await enrol(db_session, item, on)
    await fee(db_session, enrolment, when=ist(year, month, 14), amount="300.00", currency="USD")  # not counted (IR12)
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    trainer = await seeded(client, "Trainer payments")
    await create(client, trainer, entry_date=on.isoformat(), amount="999.00", vertical="it", batch_id=str(item.id))  # a draft
    await approved(client, db_session, trainer, on, "4000.00", vertical="shared", batch_id=item.id)  # another vertical (IR2)
    reversed_entry = await approved(client, db_session, trainer, on, "800.00", batch_id=item.id)
    await as_user(client, db_session)
    reversal = await post(client, reversed_entry["id"], "reverse", reason="Booked twice")  # dated today, submitted (ML11)
    assert reversal.status_code == 201, reversal.text
    await as_user(client, db_session, "partner")
    assert (await post(client, reversal.json()["id"], "approve")).status_code == 200
    after = await dashboard(client, month_param(year, month))

    row = course_row(after, program)
    assert money(row["revenue"]) == Decimal(0)  # the USD fee is not counted
    assert money(row["costs"]) == Decimal("800.00")  # the draft and the shared entry never count
    assert money(after["totals"]["costs"]) - money(before["totals"]["costs"]) == Decimal("800.00")
    usd = [n for n in after["not_counted"] if n["currency"] == "USD"]
    assert usd and money(usd[0]["amount"]) >= Decimal("300.00")
    today_row = course_row(await dashboard(client), program)
    assert money(today_row["costs"]) == Decimal("-800.00")  # the reversal counts negative on its own day


@pytest.mark.asyncio
async def test_college_bdm_trip_expenses_are_unlinked_it_costs(client, db_session):
    year, month = a_month()
    await as_user(client, db_session)
    before = await dashboard(client, month_param(year, month))
    await trip_expense(db_session, on=date(year, month, 9), bdm_type="college", amount="1800.00")
    after = await dashboard(client, month_param(year, month))
    assert money(after["unlinked"]["costs"]) - money(before["unlinked"]["costs"]) == Decimal("1800.00")


# --- payments drill-down (IR11) -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_payments_of_a_course_a_batch_and_unlinked(client, db_session):
    year, month = a_month()
    on = date(year, month, 6)
    program = await course(db_session)
    first, second = await batch(db_session, program), await batch(db_session, program)
    a = await enrol(db_session, first, on)
    b = await enrol(db_session, second, on)
    pa = await fee(db_session, a, when=ist(year, month, 6), amount="1000.00", installment_no=2)
    pb = await fee(db_session, b, when=ist(year, month, 7), amount="2000.00")
    loose = await fee(db_session, None, when=ist(year, month, 7), amount="300.00", reference_type="service_fee")
    await as_user(client, db_session)
    m = month_param(year, month)

    by_course = (await client.get(PAYMENTS, params={"month": m, "program_id": str(program.id)})).json()
    assert by_course["total"] == 2
    assert [i["id"] for i in by_course["items"]] == [str(pb.id), str(pa.id)]  # newest first
    first_item = by_course["items"][1]
    assert first_item["enrollment_code"] == a.enrollment_code
    assert first_item["course"] == program.title
    assert first_item["batch"] == first.name
    assert first_item["installment_no"] == 2
    assert first_item["receipt_no"].startswith("RCP-")
    assert money(first_item["amount"]) == Decimal("1000.00")
    assert first_item["entry_date"] == on.isoformat()
    assert not ({"student", "name", "full_name", "email", "user_id"} & set(first_item))  # Q-32: no names

    by_batch = (await client.get(PAYMENTS, params={"month": m, "batch_id": str(second.id)})).json()
    assert [i["id"] for i in by_batch["items"]] == [str(pb.id)]

    unlinked = (await client.get(PAYMENTS, params={"month": m, "unlinked": "true", "limit": 100})).json()
    assert str(loose.id) in [i["id"] for i in unlinked["items"]]
    assert all(i["course"] is None for i in unlinked["items"])

    paged = (await client.get(PAYMENTS, params={"month": m, "program_id": str(program.id), "limit": 1, "offset": 1})).json()
    assert paged["total"] == 2 and [i["id"] for i in paged["items"]] == [str(pa.id)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [{}, {"unlinked": "true", "program_id": "00000000-0000-0000-0000-000000000001"}, {"program_id": "not-a-uuid"}, {"unlinked": "true", "limit": 0}, {"unlinked": "true", "limit": 101}],
)
async def test_payments_scope_must_be_exactly_one(client, db_session, params):
    await as_user(client, db_session)
    assert (await client.get(PAYMENTS, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_payments_unknown_course_or_batch_is_422(client, db_session):
    await as_user(client, db_session)
    unknown = str(uuid.uuid4())
    course_response = await client.get(PAYMENTS, params={"program_id": unknown})
    assert course_response.status_code == 422
    assert course_response.json()["detail"] == "Choose a course from the list"
    batch_response = await client.get(PAYMENTS, params={"batch_id": unknown})
    assert batch_response.status_code == 422
    assert batch_response.json()["detail"] == "Choose a batch from the list"
