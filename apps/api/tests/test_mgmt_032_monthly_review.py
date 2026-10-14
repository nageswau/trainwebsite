"""mgmt-032 -- the Monthly Business Review (EVID-017 §32, spec MR1-MR14; acceptance: the September draft is created on 1 October,
figures are frozen after finalise even if the ledger changes, the PDF matches the screen; finalising without Problems is 422).
The stack DB is shared and never emptied: each test takes a random past month (no one else's review lives there) and clears it first,
and each section is compared with its own page's endpoint for that month, read in the same test."""

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest
from pdf_text import pdf_text
from sqlalchemy import delete, func, select

from app.models import AuditLog, MonthlyReview, Notification, NotificationDelivery, User
from app.services import investments, monthly_review
from app.services import management_metrics as metrics
from app.services.management_expenses import next_month
from tests.bdm001_helpers import login, make_user
from tests.test_mgmt_009_pnl import approved_entry

URL = "/api/v1/management/reviews"
PROBLEMS = {"went_wrong": "Two agents churned.", "delayed": "The Pune office fit-out.", "intervention": "Approve the hiring plan."}
SECTIONS = {"revenue", "expenses", "profitability", "sales", "partnerships", "people", "marketing", "investments", "next_month"}


async def as_user(client, db, role: str = "partner", division: str = "global"):
    user = await make_user(db, role, division)
    client.cookies.clear()
    await login(client, user)
    return user


async def fresh_month(db) -> date:
    """A random past month with no review (any left by an earlier run is removed first)."""
    month = date(random.randint(2001, 2025), random.randint(1, 12), 1)
    await db.execute(delete(MonthlyReview).where(MonthlyReview.month == month))
    await db.commit()
    return month


def key(month: date) -> str:
    return f"{month.year:04d}-{month.month:02d}"


async def ok(response, status: int = 200) -> dict:
    assert response.status_code == status, response.text
    return response.json()


async def generated(client, db) -> tuple[date, dict]:
    month = await fresh_month(db)
    return month, await ok(await client.post(f"{URL}/{key(month)}/generate"), 201)


# --- access (MR1) ---------------------------------------------------------------------------------------------------------------
def routes(month: str) -> list[tuple[str, str, dict | None]]:
    return [("get", URL, None), ("get", f"{URL}/{month}", None), ("post", f"{URL}/{month}/generate", None), ("patch", f"{URL}/{month}", {"went_wrong": "x"}),
            ("post", f"{URL}/{month}/finalise", None), ("get", f"{URL}/{month}/pdf", None)]  # fmt: skip


@pytest.mark.asyncio
async def test_signed_out_is_401_everywhere(client):
    client.cookies.clear()
    for method, url, body in routes("2024-01"):
        assert (await client.request(method, url, json=body)).status_code == 401, url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "division", "detail"),
    [("super_admin", "global", "Only partners can open this"), ("accountant", "global", "Only partners can open this"), ("it_admin", "it", "Management access required")],
)
async def test_everyone_but_partners_is_refused_everywhere(client, db_session, role, division, detail):
    await as_user(client, db_session, role, division)
    for method, url, body in routes("2024-01"):
        response = await client.request(method, url, json=body)
        assert response.status_code == 403, url
        assert response.json()["detail"] == detail


# --- generate / regenerate (MR4) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_drafts_a_finished_month_and_regenerating_keeps_the_narrative(client, db_session):
    await as_user(client, db_session)
    month, body = await generated(client, db_session)
    assert body["month"] == key(month) and body["status"] == "draft" and body["finalised_at"] is None
    assert set(body["snapshot"]) == SECTIONS
    assert body["narrative"] == dict.fromkeys(monthly_review.NARRATIVE_KEYS, "")
    await ok(await client.patch(f"{URL}/{key(month)}", json={"went_wrong": "  Late fees.  "}))
    again = await ok(await client.post(f"{URL}/{key(month)}/generate"))  # 200: refreshed, not created
    assert again["narrative"]["went_wrong"] == "Late fees."
    assert again["generated_at"] >= body["generated_at"]
    listed = await ok(await client.get(URL))
    assert [i["status"] for i in listed["items"] if i["month"] == key(month)] == ["draft"]


@pytest.mark.asyncio
async def test_only_a_finished_month_can_be_generated(client, db_session):
    await as_user(client, db_session)
    today = monthly_review.ledger.today()
    for month in (today.replace(day=1), next_month(today.replace(day=1))):
        response = await client.post(f"{URL}/{key(month)}/generate")
        assert response.status_code == 422
        assert response.json()["detail"] == "Only a finished month can be reviewed"
    assert (await client.post(f"{URL}/2024-13/generate")).status_code == 422


@pytest.mark.asyncio
async def test_a_month_without_a_review_is_404(client, db_session):
    await as_user(client, db_session)
    month = await fresh_month(db_session)
    for method, url, body in routes(key(month))[1:]:
        if url.endswith("/generate"):
            continue
        response = await client.request(method, url, json=body)
        assert response.status_code == 404, url
        assert response.json()["detail"] == "No review for this month yet"


# --- the sections equal their pages (MR5-MR12) --------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_each_section_equals_its_page_for_the_month(client, db_session):
    month = await fresh_month(db_session)
    on = month + timedelta(days=9)
    await approved_entry(client, db_session, kind="income", vertical="abroad", on=on, amount="12000.00")
    await approved_entry(client, db_session, kind="income", vertical="school", on=on, amount="500.00")
    await approved_entry(client, db_session, kind="expense", vertical="it", on=on, amount="3000.00")
    await as_user(client, db_session)
    snap = (await ok(await client.post(f"{URL}/{key(month)}/generate"), 201))["snapshot"]
    m = {"month": key(month)}

    pnl = await ok(await client.get("/api/v1/management/pnl", params=m))
    rows = {r["key"]: Decimal(r["revenue"]) for r in pnl["rows"]}
    lines = {line["key"]: Decimal(line["amount"]) for line in snap["revenue"]["lines"]}
    assert [line["key"] for line in snap["revenue"]["lines"]] == ["abroad", "it", "recruitment", "other"]
    assert (lines["abroad"], lines["it"], lines["recruitment"]) == (rows["abroad"], rows["it"], rows["recruitment"])
    assert lines["other"] == rows["school"] + rows["other"] + rows["shared"]
    assert snap["revenue"]["total"] == pnl["total"]["revenue"] and Decimal(pnl["total"]["revenue"]) >= Decimal("12500.00")
    assert snap["profitability"] == {"revenue": pnl["total"]["revenue"], "expenses": pnl["total"]["expenses"], "net_profit": pnl["total"]["contribution"], "margin": pnl["total"]["margin"]}

    expenses = await ok(await client.get("/api/v1/management/expenses", params=m))
    heads = {g["key"]: g["month"] for g in expenses["groups"]}
    assert [e["key"] for e in snap["expenses"]["lines"]] == ["salaries", "rent", "marketing", "technology", "trainers", "travel", "commissions", "other"]
    assert {e["key"]: e["amount"] for e in snap["expenses"]["lines"]} == heads
    assert snap["expenses"]["total"] == expenses["totals"]["month"]

    marketing = (await ok(await client.get("/api/v1/management/marketing", params=m)))["totals"]
    assert snap["marketing"] == {k: marketing[k] for k in ("budget", "spend", "leads", "customers", "conversion", "revenue", "roi")}
    assert snap["sales"]["leads"] == marketing["leads"]

    salaries = await ok(await client.get("/api/v1/management/salaries", params=m))
    entered = [r for r in salaries["rows"] if r["entered"]]
    assert snap["people"]["employees"] == (salaries["totals"]["headcount"] if entered else None)
    assert snap["people"]["departments"] == [{"name": r["department"]["name"], "headcount": r["headcount"], "total_cost": r["total_cost"]} for r in entered]
    assert snap["people"]["attendance"] is None and snap["people"]["attendance_note"] == "Not tracked"

    counts = await metrics.plan_actuals(db_session, {"it_students", "applications", "enrollments", "placements", "agents", "school_mous", "universities", "companies"}, month, next_month(month))
    assert {k: snap["sales"][k] for k in ("students", "applications", "enrollments", "placements")} == {
        "students": counts["it_students"], "applications": counts["applications"], "enrollments": counts["enrollments"], "placements": counts["placements"],
    }  # fmt: skip
    assert snap["partnerships"] == {"agents": counts["agents"], "schools": counts["school_mous"], "universities": counts["universities"], "companies": counts["companies"]}

    from app.models import Investment

    end = next_month(month)
    in_month = await investments.totals(db_session, [Investment.invested_on >= month, Investment.invested_on < end])
    to_date = await investments.totals(db_session, [Investment.invested_on < end])
    assert snap["investments"] == {
        "new_count": in_month["count"], "new_amount": str(in_month["invested"]), "total": str(to_date["invested"]), "return": str(to_date["actual_return"]),
        "roi": None if to_date["roi"] is None else str(to_date["roi"]),
    }  # fmt: skip
    assert set(snap["next_month"]) == {"month", "label", "targets", "budget"} and snap["next_month"]["month"] == key(end)


# --- narrative, finalise, freeze (MR13, AC2, negative) --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_finalising_without_the_problems_section_is_422(client, db_session):
    await as_user(client, db_session)
    month, _ = await generated(client, db_session)
    await ok(await client.patch(f"{URL}/{key(month)}", json={"went_wrong": "Churn.", "hiring": "Two trainers."}))
    response = await client.post(f"{URL}/{key(month)}/finalise")
    assert response.status_code == 422
    assert response.json()["detail"] == "Answer every Problems question before finalising: What is delayed?, What needs management intervention?"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"went_wrong": "x" * 4001}, {"surprise": "x"}, {"went_wrong": 5}])
async def test_a_bad_narrative_is_422(client, db_session, body):
    await as_user(client, db_session)
    month, _ = await generated(client, db_session)
    assert (await client.patch(f"{URL}/{key(month)}", json=body)).status_code == 422


@pytest.mark.asyncio
async def test_figures_are_frozen_after_finalise_and_a_final_review_never_changes(client, db_session):
    month = await fresh_month(db_session)
    on = month + timedelta(days=3)
    await as_user(client, db_session)
    await ok(await client.post(f"{URL}/{key(month)}/generate"), 201)
    await ok(await client.patch(f"{URL}/{key(month)}", json=PROBLEMS))
    final = await ok(await client.post(f"{URL}/{key(month)}/finalise"))
    assert final["status"] == "final" and final["finalised_at"] and final["finalised_by"]["full_name"]

    await approved_entry(client, db_session, kind="income", vertical="it", on=on, amount="777.00")  # the ledger changes afterwards
    partner = await as_user(client, db_session)
    live = await ok(await client.get("/api/v1/management/pnl", params={"month": key(month)}))
    after = await ok(await client.get(f"{URL}/{key(month)}"))
    assert after["snapshot"] == final["snapshot"] != {} and live["total"]["revenue"] != final["snapshot"]["revenue"]["total"]
    for method, url, body in [("post", f"{URL}/{key(month)}/generate", None), ("patch", f"{URL}/{key(month)}", {"hiring": "x"}), ("post", f"{URL}/{key(month)}/finalise", None)]:
        response = await client.request(method, url, json=body)
        assert response.status_code == 409, url
        assert response.json()["detail"] == "This review is final and cannot change"
    assert partner.id  # the second partner can read it too


@pytest.mark.asyncio
async def test_finalise_notifies_every_active_partner_with_a_link_and_no_figures(client, db_session):
    other = await make_user(db_session, "partner", "global")
    me = await as_user(client, db_session)
    month, _ = await generated(client, db_session)
    await ok(await client.patch(f"{URL}/{key(month)}", json=PROBLEMS))
    await ok(await client.post(f"{URL}/{key(month)}/finalise"))
    link = f"/management/reviews/{key(month)}"
    notes = (await db_session.scalars(select(Notification).where(Notification.action_url == link))).all()
    active = await db_session.scalar(select(func.count()).select_from(User).where(User.role == "partner", User.active.is_(True)))
    assert len(notes) == active and other.id in {n.user_id for n in notes}
    assert {(n.title, n.body) for n in notes} == {(f"Monthly business review for {month:%B %Y} is final", f"{me.full_name} finalised it. Open the review to read it.")}
    channels = (await db_session.scalars(select(NotificationDelivery.channel).where(NotificationDelivery.notification_id.in_([n.id for n in notes])))).all()
    assert channels and set(channels) == {"email"}


# --- beat (MR3, AC1) ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_september_draft_is_created_on_1_october_once(db_session):
    year = random.randint(2001, 2025)
    september = date(year, 9, 1)
    await db_session.execute(delete(MonthlyReview).where(MonthlyReview.month == september))
    await db_session.commit()
    assert await monthly_review.draft_previous_month(db_session, date(year, 10, 1)) is True
    review = await db_session.scalar(select(MonthlyReview).where(MonthlyReview.month == september))
    assert review.status == "draft" and review.updated_by_user_id is None and set(review.snapshot) == SECTIONS
    first = review.generated_at
    assert await monthly_review.draft_previous_month(db_session, date(year, 10, 1)) is False  # a rerun leaves the draft alone
    assert await db_session.scalar(select(MonthlyReview.generated_at).where(MonthlyReview.month == september)) == first


def test_the_beat_entry_runs_on_the_1st_at_06_00_ist():
    from app.worker import celery

    entry = celery.conf.beat_schedule["mgmt032-monthly-review"]
    assert entry["task"] == "app.worker.draft_monthly_review_task"
    schedule = entry["schedule"]
    assert (schedule.day_of_month, schedule.hour, schedule.minute) == ({1}, {0}, {30})  # UTC 00:30 = 06:00 IST


# --- PDF (MR14, AC3) and audit --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_pdf_is_the_screen(client, db_session):
    month = await fresh_month(db_session)
    await approved_entry(client, db_session, kind="income", vertical="abroad", on=month + timedelta(days=1), amount="4321.00")
    await as_user(client, db_session)
    await ok(await client.post(f"{URL}/{key(month)}/generate"), 201)
    review = await ok(await client.patch(f"{URL}/{key(month)}", json={**PROBLEMS, "went_wrong": "Fees <b>late</b> & lost"}))
    response = await client.get(f"{URL}/{key(month)}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf" and response.headers["cache-control"] == "no-store"
    assert f"monthly-review-{key(month)}.pdf" in response.headers["content-disposition"]
    text = " ".join(pdf_text(response.content).split())
    assert "EduSphere Monthly Business Review" in text and review["label"] in text and "Draft" in text
    assert "Fees <b>late</b> & lost" in text and "Not tracked" in text
    total = Decimal(review["snapshot"]["revenue"]["total"])
    assert f"{total:,.2f}" in text


@pytest.mark.asyncio
async def test_partner_writes_are_audited_with_field_names(client, db_session):
    partner = await as_user(client, db_session)
    month, body = await generated(client, db_session)
    await ok(await client.patch(f"{URL}/{key(month)}", json=PROBLEMS))
    await ok(await client.post(f"{URL}/{key(month)}/finalise"))
    await client.get(f"{URL}/{key(month)}/pdf")
    rows = (await db_session.execute(select(AuditLog.action, AuditLog.metadata_json).where(AuditLog.entity_id == body["id"], AuditLog.user_id == partner.id).order_by(AuditLog.created_at))).all()
    assert [a for a, _ in rows] == ["mgmt.review.create", "mgmt.review.update", "mgmt.review.complete", "mgmt.review.download"]
    assert sorted(rows[1][1]["fields"]) == sorted(PROBLEMS) and "values" not in rows[1][1]
