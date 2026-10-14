"""mgmt-026 -- next month plan + target vs actual (spec PN1-PN16; AC1-AC3). Plans are unique per month in the shared database, so every
test takes its month from the `free_month` fixture, which clears the month before and after (no plan is left behind)."""

import datetime
import random
import uuid
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.models import AgentOrg, AuditLog, ManagementPlan, ManagementPlanItem, ManagementTask
from app.services.bdm_appointments import IST
from tests.bdm001_helpers import login, make_user

PLANS = "/api/v1/management/plans"
TODAY = datetime.datetime.now(ZoneInfo("Asia/Kolkata")).date()
THIS_MONTH = TODAY.replace(day=1)


def add_months(day: datetime.date, months: int) -> datetime.date:
    index = day.year * 12 + day.month - 1 + months
    return datetime.date(index // 12, index % 12 + 1, 1)


def key(day: datetime.date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


async def as_user(client, db, role: str = "partner", division: str = "global"):
    user = await make_user(db, role, division)
    client.cookies.clear()
    await login(client, user)
    return user


async def clear(db, months: list[datetime.date]) -> None:
    items = select(ManagementPlanItem.id).join(ManagementPlan, ManagementPlan.id == ManagementPlanItem.plan_id).where(ManagementPlan.month.in_(months))
    await db.execute(delete(ManagementTask).where(ManagementTask.source == "plan", ManagementTask.source_id.in_(items)))
    await db.execute(delete(ManagementPlan).where(ManagementPlan.month.in_(months)))
    await db.commit()


@pytest_asyncio.fixture
async def free_month(db_session):
    """A month inside the planning window (next month … 12 ahead), with no plan before or after the test."""
    month = add_months(THIS_MONTH, random.randint(1, 12))
    await clear(db_session, [month])
    yield month
    await clear(db_session, [month])


@pytest_asyncio.fixture
async def far_month(db_session):
    """A plan stored directly for a far-future month (outside the window, so only reads use it), cleared afterwards."""
    month = datetime.date(random.randint(2200, 2900), 6, 1)
    owner = await make_user(db_session, "partner", "global")
    plan = ManagementPlan(month=month, status="active", created_by_user_id=owner.id, updated_by_user_id=owner.id)
    db_session.add(plan)
    await db_session.commit()
    yield plan
    await clear(db_session, [month])


async def new_plan(client, month: datetime.date, **extra) -> dict:
    response = await client.post(PLANS, json={"month": key(month), **extra})
    assert response.status_code == 201, response.text
    return response.json()


async def new_item(client, month: datetime.date, **body) -> dict:
    response = await client.post(f"{PLANS}/{key(month)}/items", json={"vertical": "abroad", "text": "Recruit 30 new agents", **body})
    assert response.status_code == 201, response.text
    return response.json()


def located(response, field: str) -> str:
    assert response.status_code == 422, response.text
    found = [e["msg"] for e in response.json()["detail"] if e["loc"][-1] == field]
    assert found, response.text
    return found[0]


# --- access (PN8) --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partner", "super_admin"])
async def test_the_operational_tier_reads_plans(client, db_session, role):
    await as_user(client, db_session, role)
    assert (await client.get(PLANS)).status_code == 200
    assert (await client.get(f"{PLANS}/options")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division", "message"), [("accountant", "global", "Operational management access required"), ("trainer", "it", "Management access required")])
async def test_everyone_else_is_refused(client, db_session, role, division, message):
    await as_user(client, db_session, role, division)
    for response in (await client.get(PLANS), await client.post(PLANS, json={"month": key(add_months(THIS_MONTH, 1))})):
        assert response.status_code == 403 and response.json()["detail"] == message


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    client.cookies.clear()
    assert (await client.get(PLANS)).status_code == 401


# --- plans (PN2, PN3, PN11) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_partner_plans_a_month_once(client, db_session, free_month):
    partner = await as_user(client, db_session)
    plan = await new_plan(client, free_month)
    assert plan["month"] == key(free_month) and plan["status"] == "draft" and plan["label"] == free_month.strftime("%B %Y")
    assert plan["item_count"] == 0 and plan["created_by"]["id"] == str(partner.id)
    again = await client.post(PLANS, json={"month": key(free_month)})
    assert again.status_code == 409 and again.json()["detail"] == "This month already has a plan"
    assert key(free_month) in [p["month"] for p in (await client.get(PLANS)).json()["items"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [-1, 13])
async def test_a_month_outside_the_window_is_422(client, db_session, offset):
    await as_user(client, db_session)
    message = located(await client.post(PLANS, json={"month": key(add_months(THIS_MONTH, offset))}), "month")
    assert message == "Choose this month or one of the next 12"


@pytest.mark.asyncio
@pytest.mark.parametrize("month", ["2026-13", "2026-1", "next"])
async def test_a_malformed_month_is_422(client, db_session, month):
    await as_user(client, db_session)
    assert (await client.post(PLANS, json={"month": month})).status_code == 422
    assert (await client.get(f"{PLANS}/{month}")).status_code == 422


@pytest.mark.asyncio
async def test_an_unknown_month_is_404(client, db_session):
    await as_user(client, db_session)
    response = await client.get(f"{PLANS}/2999-01")
    assert response.status_code == 404 and response.json()["detail"] == "Plan not found"


@pytest.mark.asyncio
async def test_the_current_month_can_be_planned(client, db_session):
    await clear(db_session, [THIS_MONTH])
    try:
        await as_user(client, db_session)
        assert (await new_plan(client, THIS_MONTH))["month"] == key(THIS_MONTH)
    finally:
        await clear(db_session, [THIS_MONTH])


# --- AC1: the source's October 2026 plan is representable -----------------------------------------------------------------------
OCTOBER_PLAN = [
    ("abroad", "Recruit 30 new agents", "agents", 30), ("abroad", "100+ applicants", "applications", 100),
    ("abroad", "300 enrollments target", "enrollments", 300), ("abroad", "Sign Korean universities", None, None),
    ("abroad", "Sign Japanese universities", None, None), ("abroad", "Increase UK/Germany/Australia applications", None, None),
    ("it", "500 new students", "it_students", 500), ("it", "10 new batches", "batches", 10), ("it", "90% course completion", None, None),
    ("it", "100 placement-ready students", None, None), ("school", "20 new school meetings", None, None), ("school", "10 MoUs", "school_mous", 10),
    ("school", "500 students onboarded", "school_students", 500), ("recruitment", "20 new companies", "companies", 20),
    ("recruitment", "100 job openings", None, None), ("recruitment", "50 placements", "placements", 50),
]  # fmt: skip


@pytest.mark.asyncio
async def test_ac1_the_october_plan_is_stored_in_vertical_order(client, db_session, free_month):
    await as_user(client, db_session)
    await new_plan(client, free_month, status="active")
    for vertical, text, kpi, target in reversed(OCTOBER_PLAN):  # entry order must not decide the vertical order
        await new_item(client, free_month, vertical=vertical, text=text, kpi=kpi, target=target)
    plan = (await client.get(f"{PLANS}/{key(free_month)}")).json()
    assert plan["status"] == "active" and len(plan["items"]) == 16
    assert [i["vertical"] for i in plan["items"]] == sorted((v for v, *_ in OCTOBER_PLAN), key=["abroad", "it", "school", "recruitment"].index)
    agents = next(i for i in plan["items"] if i["kpi"] == "agents")
    assert Decimal(agents["target"]) == 30 and agents["done"] is False and agents["task_count"] == 0
    summary = next(p for p in (await client.get(PLANS)).json()["items"] if p["month"] == key(free_month))
    assert summary["item_count"] == 16 and summary["kpi_count"] == 9 and summary["done_count"] == 0


# --- AC2: "Agents 30 → 27 = 90%" from data (PN6) ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac2_agents_thirty_against_twenty_seven_is_ninety_per_cent(client, db_session, far_month):
    at = datetime.datetime(far_month.month.year, 6, 10, 12, tzinfo=IST)
    for _ in range(27):
        db_session.add(AgentOrg(name="Plan Agency", prefix=uuid.uuid4().hex[:6].upper(), status="active", created_at=at))
    db_session.add(ManagementPlanItem(plan_id=far_month.id, vertical="abroad", text="Recruit 30 new agents", kpi="agents", target=30, position=1,
                                      created_by_user_id=far_month.created_by_user_id, updated_by_user_id=far_month.created_by_user_id))  # fmt: skip
    db_session.add(ManagementPlanItem(plan_id=far_month.id, vertical="abroad", text="Sign Korean universities", done=True, position=2,
                                      created_by_user_id=far_month.created_by_user_id, updated_by_user_id=far_month.created_by_user_id))  # fmt: skip
    await db_session.commit()
    await as_user(client, db_session)
    progress = (await client.get(f"{PLANS}/{key(far_month.month)}/progress")).json()
    assert progress["state"] == "upcoming" and progress["label"] == far_month.month.strftime("%B %Y")
    [row] = progress["rows"]
    assert row["kpi"] == "agents" and row["kpi_label"] == "New agents" and row["unit"] == "count"
    assert Decimal(row["target"]) == 30 and Decimal(row["actual"]) == 27 and row["achievement"] == 90
    assert progress["free_text"] == {"total": 1, "done": 1}


@pytest.mark.asyncio
async def test_the_current_month_is_running(client, db_session):
    await clear(db_session, [THIS_MONTH])
    try:
        await as_user(client, db_session)
        await new_plan(client, THIS_MONTH)
        progress = (await client.get(f"{PLANS}/{key(THIS_MONTH)}/progress")).json()
        assert progress["state"] == "running" and progress["rows"] == [] and progress["free_text"] == {"total": 0, "done": 0}
    finally:
        await clear(db_session, [THIS_MONTH])


# --- AC3 + item rules (PN4) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac3_a_free_text_item_toggles_done(client, db_session, free_month):
    await as_user(client, db_session)
    await new_plan(client, free_month)
    item = await new_item(client, free_month, text="Sign Korean universities")
    url = f"{PLANS}/{key(free_month)}/items/{item['id']}"
    assert (await client.patch(url, json={"done": True})).json()["done"] is True
    assert (await client.patch(url, json={"done": False})).json()["done"] is False


@pytest.mark.asyncio
async def test_negative_a_kpi_not_in_the_catalogue_is_422(client, db_session, free_month):
    await as_user(client, db_session)
    await new_plan(client, free_month)
    response = await client.post(f"{PLANS}/{key(free_month)}/items", json={"vertical": "abroad", "text": "Visitors", "kpi": "website_visits", "target": 5})
    located(response, "kpi")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "field", "message"),
    [
        ({"kpi": "agents"}, "target", "Give the target for this KPI"),
        ({"target": 30}, "target", "Only a KPI item has a target"),
        ({"kpi": "agents", "target": "30.5"}, "target", "Give a whole number from 1 to 1,000,000"),
        ({"kpi": "agents", "target": 1_000_001}, "target", "Give a whole number from 1 to 1,000,000"),
        ({"kpi": "agents", "target": 30, "done": True}, "done", "Only a free-text item is marked done"),
        ({"vertical": "marketing"}, "vertical", None),
        ({"text": "x"}, "text", None),
    ],
)
async def test_item_rules_are_field_located_422s(client, db_session, free_month, body, field, message):
    await as_user(client, db_session)
    await new_plan(client, free_month)
    found = located(await client.post(f"{PLANS}/{key(free_month)}/items", json={"vertical": "abroad", "text": "Recruit 30 new agents", **body}), field)
    if message:
        assert message in found


@pytest.mark.asyncio
async def test_switching_kpi_items_and_free_text_items(client, db_session, free_month):
    await as_user(client, db_session)
    await new_plan(client, free_month)
    item = await new_item(client, free_month, text="Sign Korean universities")
    url = f"{PLANS}/{key(free_month)}/items/{item['id']}"
    await client.patch(url, json={"done": True})
    made_kpi = (await client.patch(url, json={"kpi": "universities", "target": 2})).json()
    assert made_kpi["kpi"] == "universities" and made_kpi["done"] is False  # PN4: a KPI item is never "done"
    located(await client.patch(url, json={"kpi": None}), "target")  # a target without a KPI: refused, not a CHECK 500
    free = (await client.patch(url, json={"kpi": None, "target": None})).json()
    assert free["kpi"] is None and free["target"] is None


@pytest.mark.asyncio
async def test_an_item_of_another_months_plan_is_404(client, db_session, free_month):
    await as_user(client, db_session)
    other = add_months(free_month, 1) if free_month < add_months(THIS_MONTH, 12) else add_months(free_month, -1)
    await clear(db_session, [other])
    try:
        await new_plan(client, free_month)
        await new_plan(client, other)
        item = await new_item(client, other)
        response = await client.patch(f"{PLANS}/{key(free_month)}/items/{item['id']}", json={"done": False})
        assert response.status_code == 404 and response.json()["detail"] == "Plan item not found"
    finally:
        await clear(db_session, [other])


# --- PN7: revenue is partners' only ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_revenue_kpi_is_partner_only(client, db_session, free_month):
    partner = await as_user(client, db_session)
    await new_plan(client, free_month)
    assert "revenue" in [k["key"] for k in (await client.get(f"{PLANS}/options")).json()["kpis"]]
    revenue = await new_item(client, free_month, vertical="other", text="Revenue ₹50L", kpi="revenue", target="5000000")
    await new_item(client, free_month, text="Sign Japanese universities")
    await as_user(client, db_session, "super_admin")
    assert "revenue" not in [k["key"] for k in (await client.get(f"{PLANS}/options")).json()["kpis"]]
    plan = (await client.get(f"{PLANS}/{key(free_month)}")).json()
    assert [i["text"] for i in plan["items"]] == ["Sign Japanese universities"]
    assert next(p for p in (await client.get(PLANS)).json()["items"] if p["month"] == key(free_month))["item_count"] == 1
    assert (await client.get(f"{PLANS}/{key(free_month)}/progress")).json()["rows"] == []
    url = f"{PLANS}/{key(free_month)}/items/{revenue['id']}"
    assert (await client.patch(url, json={"target": 1})).status_code == 404
    assert (await client.delete(url)).status_code == 404
    refused = await client.post(f"{PLANS}/{key(free_month)}/items", json={"vertical": "other", "text": "Revenue", "kpi": "revenue", "target": 10})
    assert refused.status_code == 403 and refused.json()["detail"] == "Only partners can set a revenue target"
    client.cookies.clear()
    await login(client, partner)
    [row] = (await client.get(f"{PLANS}/{key(free_month)}/progress")).json()["rows"]
    assert row["unit"] == "inr" and Decimal(row["target"]) == 5_000_000


@pytest.mark.asyncio
async def test_the_revenue_actual_is_the_pnl_total_revenue(client, db_session, far_month):
    db_session.add(ManagementPlanItem(plan_id=far_month.id, vertical="other", text="Revenue", kpi="revenue", target=100, position=1,
                                      created_by_user_id=far_month.created_by_user_id, updated_by_user_id=far_month.created_by_user_id))  # fmt: skip
    await db_session.commit()
    await as_user(client, db_session)
    [row] = (await client.get(f"{PLANS}/{key(far_month.month)}/progress")).json()["rows"]
    pnl = await client.get("/api/v1/management/pnl", params={"month": key(far_month.month)})
    expected = Decimal(pnl.json()["total"]["revenue"]) if pnl.status_code == 200 else Decimal(0)  # a far month the P&L refuses has no ledger
    assert Decimal(row["actual"]) == expected and row["achievement"] == 0


# --- PN3: a closed plan is read-only until reopened ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_closed_plan_refuses_changes_until_reopened(client, db_session, free_month):
    owner = await make_user(db_session, "trainer", "it")
    await as_user(client, db_session)
    await new_plan(client, free_month)
    item = await new_item(client, free_month, text="Sign Korean universities")
    month_url, item_url = f"{PLANS}/{key(free_month)}", f"{PLANS}/{key(free_month)}/items/{item['id']}"
    assert (await client.patch(month_url, json={"status": "closed"})).json()["status"] == "closed"
    closed = "This plan is closed. Reopen it to change it."
    for response in (
        await client.post(f"{month_url}/items", json={"vertical": "it", "text": "500 new students"}),
        await client.patch(item_url, json={"done": True}),
        await client.delete(item_url),
        await client.post(f"{item_url}/tasks", json={"owner_user_id": str(owner.id), "deadline": TODAY.isoformat()}),
    ):
        assert response.status_code == 409 and response.json()["detail"] == closed
    assert (await client.patch(month_url, json={"status": "active"})).json()["status"] == "active"
    assert (await client.patch(item_url, json={"done": True})).status_code == 200


# --- PN9: audit ("who changed a target") ---------------------------------------------------------------------------------------
async def audits(db, entity_id: str) -> list[AuditLog]:
    db.expire_all()
    return list((await db.scalars(select(AuditLog).where(AuditLog.entity_id == entity_id).order_by(AuditLog.created_at))).all())


@pytest.mark.asyncio
async def test_every_write_is_audited_with_field_names_only(client, db_session, free_month):
    partner_id = (await as_user(client, db_session)).id
    plan = await new_plan(client, free_month)
    item = await new_item(client, free_month, kpi="agents", target=30)
    url = f"{PLANS}/{key(free_month)}/items/{item['id']}"
    await client.patch(url, json={"target": 35})
    await client.patch(url, json={"target": 35})  # no change, nothing recorded
    await client.patch(f"{PLANS}/{key(free_month)}", json={"status": "active"})
    rows = await audits(db_session, item["id"])
    assert [(r.action, r.metadata_json["fields"]) for r in rows] == [("mgmt.plan.create", ["vertical", "text", "kpi", "target"]), ("mgmt.plan.update", ["target"])]
    assert all(r.user_id == partner_id and "values" not in r.metadata_json for r in rows)
    assert [(r.action, r.metadata_json["fields"]) for r in await audits(db_session, plan["id"])] == [("mgmt.plan.create", ["month", "status"]), ("mgmt.plan.update", ["status"])]
    assert (await client.delete(url)).status_code == 204
    assert (await audits(db_session, item["id"]))[-1].action == "mgmt.plan.delete"
    assert (await client.get(f"{PLANS}/{key(free_month)}")).json()["items"] == []


# --- PN10: a plan item becomes a mgmt-028 task -----------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_plan_item_creates_a_management_task(client, db_session, free_month):
    owner = await make_user(db_session, "partnership_manager", "global")
    await as_user(client, db_session)
    await new_plan(client, free_month)
    item = await new_item(client, free_month, text="Sign Korean universities")
    response = await client.post(f"{PLANS}/{key(free_month)}/items/{item['id']}/tasks", json={"owner_user_id": str(owner.id), "priority": "high", "deadline": (TODAY + timedelta(days=3)).isoformat()})
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["title"] == "Sign Korean universities" and task["source"] == "plan" and task["owner"]["id"] == str(owner.id)
    stored = await db_session.get(ManagementTask, uuid.UUID(task["id"]))
    assert stored.source_id == uuid.UUID(item["id"])
    assert (await client.get(f"{PLANS}/{key(free_month)}")).json()["items"][0]["task_count"] == 1
    inactive = await make_user(db_session, "trainer", "it", active=False)
    bad = await client.post(f"{PLANS}/{key(free_month)}/items/{item['id']}/tasks", json={"owner_user_id": str(inactive.id), "deadline": TODAY.isoformat()})
    assert located(bad, "owner_user_id") == "Choose an active staff member"
