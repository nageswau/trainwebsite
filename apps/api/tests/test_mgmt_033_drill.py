"""mgmt-033 -- drill-down navigation (spec DD1-DD14; AC1: the rows at each level add up to the parent figure; AC2: the final level shows
the record; AC3: super_admin cannot open money chains), read with `GET /management/drill/{chain}?path=...`.

The stack DB is shared and never emptied, so each test works in a random far-past month with its own courses, applications and
companies: a level below the first is filtered to them and read absolutely; level 0 is compared with the parent dashboard's revenue
read by the same user in the same test."""

import random
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Candidate, Company, Job, JobApplication, RecCandidateSource, RecruiterInvoice, RecruiterPayment, UniversityCommissionReceipt
from app.services import candidates as candidate_svc
from tests.bdm001_helpers import login, make_user
from tests.test_mgmt_004_ledger import as_user, category, create, post
from tests.test_mgmt_006_abroad_revenue import linked_application, overseas_payment
from tests.test_mgmt_007_it_revenue import batch, course, enrol, fee

DRILL = "/api/v1/management/drill"


def a_month() -> tuple[int, int]:
    return random.randint(2001, 2025), random.randint(1, 12)


def month_param(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def tag() -> str:
    return uuid.uuid4().hex[:8]


async def drill(client, chain: str, month: str, path: list[str] | None = None, *, status: int = 200, **params) -> dict:
    query = {"month": month, **params, **({"path": ",".join(path)} if path else {})}
    response = await client.get(f"{DRILL}/{chain}", params=query)
    assert response.status_code == status, response.text
    return response.json()


def money(value) -> Decimal:
    return Decimal(value)


def assert_adds_up(data: dict) -> None:
    """AC1: every row of the level (all on one page here) adds up to the figure the level drills into."""
    assert data["total_rows"] == len(data["rows"])
    assert sum((money(r["amount"]) for r in data["rows"]), Decimal(0)) == money(data["total"])
    assert sum(r["count"] for r in data["rows"]) == data["count"]


def row(data: dict, key: str) -> dict:
    (found,) = [r for r in data["rows"] if r["key"] == key]
    return found


async def approved_income(client, db, on: date, amount: str, vertical: str) -> dict:
    """An approved manual income entry with no tags. Leaves an accountant signed in."""
    await as_user(client, db)
    cat = await category(client, kind="income")
    entry = await create(client, cat["id"], kind="income", vertical=vertical, entry_date=on.isoformat(), amount=amount)
    assert (await post(client, entry["id"], "submit")).status_code == 200
    await as_user(client, db, "partner")
    assert (await post(client, entry["id"], "approve")).status_code == 200
    await as_user(client, db)
    return entry


async def it_payment(db, on: date, amount: str = "30000.00"):
    """One paid enrolment fee on a fresh course and batch with a trainer; returns (program, batch, trainer, enrolment, payment)."""
    from tests.test_mgmt_005_auto_lines import ist

    program = await course(db)
    item = await batch(db, program)
    trainer = await make_user(db, "trainer", "it", name=f"Trainer {tag()}")
    item.trainer_id = trainer.id
    await db.commit()
    enrolment = await enrol(db, item, on)
    payment = await fee(db, enrolment, when=ist(on.year, on.month, on.day), amount=amount)
    return program, item, trainer, enrolment, payment


async def recruitment_payment(db, on: date, amount: str = "50000.00"):
    """An invoice payment on a fresh company's requirement (assigned recruiter), with one selected and one joined candidate."""
    recruiter = await make_user(db, "placement_team", "global", name=f"Recruiter {tag()}")
    company = Company(name=f"Mgmt033 Co {tag()}")
    db.add(company)
    await db.flush()
    job = Job(company_id=company.id, title=f"Java {tag()}", location="Pune", description="", skills=[], status="sourcing", assigned_recruiter_user_id=recruiter.id)
    db.add(job)
    await db.flush()
    source = await db.scalar(select(RecCandidateSource).where(func.lower(RecCandidateSource.name) == "referral"))
    names = {}
    for status in ("selected", "joined", "sourced"):
        candidate = Candidate(
            candidate_code=await candidate_svc.next_code(db), source_id=source.id, created_by_user_id=recruiter.id, name=f"Cand {status} {tag()}", email=f"{tag()}@example.com", preferred_locations=[]
        )
        db.add(candidate)
        await db.flush()
        db.add(JobApplication(job_id=job.id, candidate_id=candidate.id, status=status))
        names[status] = candidate.name
    invoice = RecruiterInvoice(job_id=job.id, invoice_number=f"INV-{tag()}", invoice_date=on, due_date=on, amount=Decimal("90000"), created_by_user_id=recruiter.id)
    db.add(invoice)
    await db.flush()
    payment = RecruiterPayment(invoice_id=invoice.id, received_on=on, amount=Decimal(amount), created_by_user_id=recruiter.id)
    db.add(payment)
    await db.commit()
    return company, recruiter, job, payment, names


async def audit_rows(db, user_id) -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.user_id == user_id, AuditLog.entity_type == "mgmt.drill").order_by(AuditLog.created_at))).all())


# --- access (DD4, AC3) ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("chain", ["abroad", "it", "recruitment"])
@pytest.mark.parametrize("role", ["partner", "accountant"])
async def test_finance_tier_opens_every_chain(client, db_session, chain, role):
    await as_user(client, db_session, role)
    year, month = a_month()
    data = await drill(client, chain, month_param(year, month))
    assert data["chain"] == chain
    assert data["breadcrumbs"] == []
    assert data["level"]["key"] == {"abroad": "country", "it": "course", "recruitment": "company"}[chain]
    assert data["record"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("chain", ["abroad", "it", "recruitment"])
@pytest.mark.parametrize(
    "role,division,detail", [("super_admin", "global", "Finance access required"), ("it_admin", "it", "Management access required"), ("trainer", "it", "Management access required")]
)
async def test_super_admin_and_others_cannot_open_money_chains(client, db_session, chain, role, division, detail):
    await login(client, await make_user(db_session, role, division))
    response = await client.get(f"{DRILL}/{chain}")
    assert response.status_code == 403
    assert response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(f"{DRILL}/it")).status_code == 401


# --- level 0 equals the parent dashboard (DD2, AC1) -----------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partner", "accountant"])
async def test_level_zero_equals_the_dashboard_revenue(client, db_session, role):
    year, month = a_month()
    on = date(year, month, 12)
    await it_payment(db_session, on)
    application, _ = await linked_application(db_session)
    await overseas_payment(db_session, on, application=application)
    await recruitment_payment(db_session, on)
    await as_user(client, db_session, role)
    m = month_param(year, month)
    abroad = (await client.get("/api/v1/management/revenue/abroad", params={"month": m})).json()
    it = (await client.get("/api/v1/management/revenue/it", params={"month": m})).json()
    rec = (await client.get("/api/v1/management/revenue/recruitment", params={"month": m})).json()
    assert money((await drill(client, "abroad", m, limit=100))["total"]) == money(abroad["revenue"]["month"])
    assert money((await drill(client, "it", m, limit=100))["total"]) == money(it["totals"]["revenue"])
    assert money((await drill(client, "recruitment", m, limit=100))["total"]) == money(rec["revenue"]["total"])


# --- the IT chain, top to record (DD1, DD6, DD9) --------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_it_chain_walks_from_course_to_the_payment_record(client, db_session):
    year, month = a_month()
    on = date(year, month, 9)
    program, item, trainer, enrolment, payment = await it_payment(db_session, on, "30000.00")
    second = await enrol(db_session, item, on)
    from tests.test_mgmt_005_auto_lines import ist

    await fee(db_session, second, when=ist(year, month, 10), amount="12000.00")
    company, _, job, _, _ = await recruitment_payment(db_session, on)  # a placement for the first student
    candidate = Candidate(
        candidate_code=await candidate_svc.next_code(db_session),
        source_id=(await db_session.scalar(select(RecCandidateSource.id).where(func.lower(RecCandidateSource.name) == "referral"))),
        created_by_user_id=trainer.id,
        name=f"Placed {tag()}",
        email=f"{tag()}@example.com",
        preferred_locations=[],
        user_id=enrolment.student_id,
    )
    db_session.add(candidate)
    await db_session.flush()
    db_session.add(JobApplication(job_id=job.id, candidate_id=candidate.id, student_id=enrolment.student_id, status="joined"))
    await db_session.commit()

    await as_user(client, db_session, "partner")
    m = month_param(year, month)
    top = await drill(client, "it", m, limit=100)
    assert_adds_up(top)
    course_row = row(top, str(program.id))
    assert course_row["name"] == program.title
    assert money(course_row["amount"]) == Decimal("42000.00")

    batches = await drill(client, "it", m, [str(program.id)])
    assert money(batches["total"]) == Decimal("42000.00")
    assert batches["level"]["key"] == "batch"
    assert [b["level"] for b in batches["breadcrumbs"]] == ["course"]
    assert batches["breadcrumbs"][0]["name"] == program.title
    assert_adds_up(batches)

    trainers = await drill(client, "it", m, [str(program.id), str(item.id)])
    assert trainers["level"]["key"] == "trainer"
    assert row(trainers, str(trainer.id))["name"] == trainer.full_name
    assert_adds_up(trainers)

    students = await drill(client, "it", m, [str(program.id), str(item.id), str(trainer.id)])
    assert students["level"]["key"] == "student"
    assert len(students["rows"]) == 2
    assert_adds_up(students)

    payments = await drill(client, "it", m, [str(program.id), str(item.id), str(trainer.id), str(enrolment.student_id)])
    assert payments["level"]["key"] == "payment"
    (line,) = payments["rows"]
    assert line["key"] == str(payment.id) and money(line["amount"]) == Decimal("30000.00")
    assert line["latest"] == on.isoformat()

    record = await drill(client, "it", m, [str(program.id), str(item.id), str(trainer.id), str(enrolment.student_id), str(payment.id)])
    assert record["level"] is None and record["rows"] == []
    assert record["record"]["id"] == str(payment.id)
    assert money(record["record"]["amount"]) == Decimal("30000.00")
    assert {"label": "Enrolment", "value": enrolment.enrollment_code} in record["record"]["details"]
    outcomes = record["record"]["outcomes"]
    assert outcomes["title"] == "Placement"
    assert [(o["name"], o["status"]) for o in outcomes["items"]] == [(f"{job.title} · {company.name}", "Joined")]


@pytest.mark.asyncio
async def test_a_manual_entry_without_a_course_is_the_unattributed_row(client, db_session):
    """DD7: one `none` row per level, and it can be drilled into like any other."""
    year, month = a_month()
    on = date(year, month, 3)
    await approved_income(client, db_session, on, "7000.00", "it")
    data = await drill(client, "it", month_param(year, month), limit=100)
    none = row(data, "none")
    assert none["name"] == "No course linked"
    assert money(none["amount"]) == Decimal("7000.00")
    below = await drill(client, "it", month_param(year, month), ["none"])
    assert below["breadcrumbs"][0] == {"level": "course", "level_label": "Course", "key": "none", "name": "No course linked"}
    assert row(below, "none")["name"] == "No batch"


# --- the abroad chain and university commission (DD5) ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_abroad_chain_walks_to_the_application_and_payment(client, db_session):
    year, month = a_month()
    on = date(year, month, 18)
    application, names = await linked_application(db_session)
    payment = await overseas_payment(db_session, on, amount="40000.00", application=application)
    await as_user(client, db_session, "accountant")
    m = month_param(year, month)
    top = await drill(client, "abroad", m, limit=100)
    assert_adds_up(top)
    countries = [r for r in top["rows"] if r["name"] == names["country"]]
    assert len(countries) == 1 and money(countries[0]["amount"]) == Decimal("40000.00")
    path = [countries[0]["key"]]
    for level in ("university", "agent", "staff", "student", "application", "payment"):
        data = await drill(client, "abroad", m, path)
        assert data["level"]["key"] == level
        assert money(data["total"]) == Decimal("40000.00")
        assert_adds_up(data)
        (only,) = data["rows"]
        if level == "university":
            assert only["name"] == names["university"]
        if level == "agent":
            assert only["name"] == names["agency"]
        if level == "student":
            assert only["key"] == str(payment.user_id)
        if level == "application":
            assert only["key"] == str(application.id)
        path.append(only["key"])
    record = await drill(client, "abroad", m, path)
    assert record["record"]["id"] == str(payment.id)
    assert {"label": "Intake", "value": names["intake"]} in record["record"]["details"]
    assert [b["level"] for b in record["breadcrumbs"]] == ["country", "university", "agent", "staff", "student", "application", "payment"]


@pytest.mark.asyncio
async def test_university_commission_is_in_the_partners_chain_only(client, db_session):
    year, month = a_month()
    application, names = await linked_application(db_session)
    creator = await make_user(db_session, "partnership_head", "global")
    db_session.add(
        UniversityCommissionReceipt(
            university_id=application.university_id, amount=Decimal("60000.00"), currency="INR", received_on=date(year, month, 20), reference=f"UC-{tag()}", created_by_user_id=creator.id
        )
    )
    await db_session.commit()
    m = month_param(year, month)
    await as_user(client, db_session, "partner")
    partner = await drill(client, "abroad", m, limit=100)
    (country,) = [r for r in partner["rows"] if r["name"] == names["country"]]
    assert money(country["amount"]) == Decimal("60000.00")
    agents = await drill(client, "abroad", m, [country["key"], str(application.university_id)])
    assert row(agents, "none")["name"] == "No agency"
    await as_user(client, db_session, "accountant")
    accountant = await drill(client, "abroad", m, limit=100)
    assert all(r["name"] != names["country"] for r in accountant["rows"])
    await drill(client, "abroad", m, [country["key"]], status=404)


# --- the recruitment chain (DD8) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recruitment_chain_ends_with_the_requirements_selections_and_joinings(client, db_session):
    year, month = a_month()
    on = date(year, month, 7)
    company, recruiter, job, payment, names = await recruitment_payment(db_session, on, "45000.00")
    await as_user(client, db_session, "partner")
    m = month_param(year, month)
    top = await drill(client, "recruitment", m, limit=100)
    assert_adds_up(top)
    assert row(top, str(company.id))["name"] == company.name
    path = [str(company.id)]
    recruiters = await drill(client, "recruitment", m, path)
    assert row(recruiters, str(recruiter.id))["name"] == recruiter.full_name
    path.append(str(recruiter.id))
    jobs = await drill(client, "recruitment", m, path)
    assert row(jobs, str(job.id))["name"] == f"{job.title} · {job.requirement_code}"
    path.append(str(job.id))
    payments = await drill(client, "recruitment", m, path)
    assert row(payments, str(payment.id))
    record = await drill(client, "recruitment", m, [*path, str(payment.id)])
    outcomes = record["record"]["outcomes"]
    assert outcomes["title"] == "Selections and joinings"
    assert sorted((o["name"], o["status"]) for o in outcomes["items"]) == sorted([(names["selected"], "Selected"), (names["joined"], "Joined")])


# --- period (DD3) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_year_period_runs_from_april(client, db_session):
    year = random.randint(2001, 2024)
    program, *_ = await it_payment(db_session, date(year, 4, 2), "1000.00")
    await as_user(client, db_session)
    data = await drill(client, "it", month_param(year, 9), [str(program.id)], period="year")
    assert data["start"] == date(year, 4, 1).isoformat() and data["end"] == date(year, 9, 30).isoformat()
    assert money(data["total"]) == Decimal("1000.00")
    await drill(client, "it", month_param(year, 9), [str(program.id)], status=404)  # nothing in September itself


# --- tampered paths (DD12) ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tampered_paths_are_refused(client, db_session):
    year, month = a_month()
    program, item, trainer, enrolment, payment = await it_payment(db_session, date(year, month, 5))
    await as_user(client, db_session)
    m = month_param(year, month)
    assert (await client.get(f"{DRILL}/visa", params={"month": m})).status_code == 404
    for bad in ("not-a-uuid", f"{program.id},,{item.id}", ",".join([str(program.id)] * 6), f"{program.id},{item.id},{trainer.id},{enrolment.student_id},none"):
        response = await client.get(f"{DRILL}/it", params={"month": m, "path": bad})
        assert response.status_code == 422, bad
    assert (await client.get(f"{DRILL}/it", params={"month": m, "path": str(uuid.uuid4())})).status_code == 404
    assert (await client.get(f"{DRILL}/it", params={"month": "2026-13"})).status_code == 422
    assert (await client.get(f"{DRILL}/it", params={"month": m, "period": "week"})).status_code == 422


# --- audit (DD11) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reads_of_students_and_below_are_audited(client, db_session):
    year, month = a_month()
    program, item, trainer, enrolment, payment = await it_payment(db_session, date(year, month, 5))
    user = await as_user(client, db_session, "accountant")
    m = month_param(year, month)
    path = [str(program.id), str(item.id), str(trainer.id), str(enrolment.student_id), str(payment.id)]
    for depth in range(3):
        await drill(client, "it", m, path[:depth])
    assert await audit_rows(db_session, user.id) == []
    for depth in (3, 4, 5):
        await drill(client, "it", m, path[:depth])
    rows = await audit_rows(db_session, user.id)
    assert [(r.action, r.metadata_json["fields"]) for r in rows] == [
        ("mgmt.drill.view", ["it", "student"]),
        ("mgmt.drill.view", ["it", "payment"]),
        ("mgmt.drill.view", ["it", "record"]),
    ]
    assert [r.entity_id for r in rows] == [str(trainer.id), str(enrolment.student_id), str(payment.id)]
