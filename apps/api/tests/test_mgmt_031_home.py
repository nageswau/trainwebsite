"""mgmt-031 -- GET /management/home, the §31 partner home (EVID-017 §31/§2, spec HM1-HM14; acceptance: every panel matches its page's
figure; super_admin sees no money). The stack DB is shared and never emptied, so each panel is compared with its own page's endpoint
read in the same test, and rows are found by id rather than by position where others' rows may sort first."""

import datetime
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.models import ManagementDiscussion, ManagementTask
from tests.bdm001_helpers import login, make_user
from tests.test_mgmt_026_plans import THIS_MONTH, add_months, clear, key, new_item, new_plan

URL = "/api/v1/management/home"
TODAY = datetime.datetime.now(datetime.timezone(timedelta(hours=5, minutes=30))).date()
MONEY_SNAPSHOT = {"revenue", "expenses", "profit", "cash"}
OPERATIONAL_SNAPSHOT = {"students", "applications", "enrollments"}
PANELS = {"urgent", "pending_decisions", "meetings", "targets", "growth", "my_tasks", "recent_discussions", "next_plan"}


async def as_user(client, db, role: str = "partner", division: str = "global"):
    user = await make_user(db, role, division)
    client.cookies.clear()
    await login(client, user)
    return user


async def get(client, url: str = URL, **params) -> dict:
    response = await client.get(url, params=params or None)
    assert response.status_code == 200, response.text
    return response.json()


def last_complete_month() -> str:
    return key(add_months(THIS_MONTH, -1))


# --- access (HM2) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "division", "detail"), [("accountant", "global", "Operational access required"), ("it_admin", "it", "Management access required"), ("counselor", "overseas", "Management access required")]
)
async def test_other_roles_are_refused(client, db_session, role, division, detail):
    await as_user(client, db_session, role, division)
    response = await client.get(URL)
    assert response.status_code == 403
    assert response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_the_partner_gets_the_business_home(client, db_session):
    await as_user(client, db_session)
    body = await get(client)
    assert body["scope"] == "business"
    assert body["as_of"] == TODAY.isoformat() and body["month"] == key(THIS_MONTH)
    assert set(body["snapshot"]) == MONEY_SNAPSHOT | OPERATIONAL_SNAPSHOT
    assert PANELS | {"financial_position"} <= set(body)


@pytest.mark.asyncio
async def test_super_admin_gets_no_money(client, db_session):
    """HM2 / AC: no money key anywhere in the response -- not even null."""
    await as_user(client, db_session, "super_admin")
    body = await get(client)
    assert body["scope"] == "operational"
    assert set(body["snapshot"]) == OPERATIONAL_SNAPSHOT
    assert "financial_position" not in body
    assert PANELS <= set(body)
    assert all(u["key"] != "overdue_receivables" for u in body["urgent"])
    assert all(f["key"] in {"sales_pipeline", "student_growth", "enrollment", "agent_growth", "school_growth", "universities"} for f in body["growth"]["factors"])
    assert all(row["kpi"] != "revenue" for row in (body["targets"] or {"rows": []})["rows"])


# --- the snapshot matches its pages (HM4) ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_snapshot_matches_its_pages(client, db_session):
    await as_user(client, db_session)
    body = await get(client)
    snap = body["snapshot"]
    pnl = (await get(client, "/api/v1/management/pnl"))["total"]
    assert (snap["revenue"], snap["expenses"], snap["profit"]) == (pnl["revenue"], pnl["expenses"], pnl["contribution"])

    students = {k["key"]: k["value"] for k in (await get(client, "/api/v1/management/snapshot"))["kpis"]}["total_students"]
    assert snap["students"] == students
    funnel = await get(client, "/api/v1/management/applications", date_from=THIS_MONTH.isoformat(), date_to=TODAY.isoformat())
    assert snap["applications"] == next(s["value"] for s in funnel["stages"] if s["key"] == "created")
    health = await get(client, "/api/v1/management/health", month=key(THIS_MONTH))
    assert snap["enrollments"] == next(int(f["current"]) for f in health["factors"] if f["key"] == "enrollment")

    cash = snap["cash"]
    if cash["month"] is not None:
        accounts = await get(client, "/api/v1/management/accounts", month=cash["month"])
        assert Decimal(cash["amount"]) == Decimal(accounts["balances"]["cash_bank"])
        assert cash["month"] <= key(THIS_MONTH)
    else:
        assert cash["amount"] is None


@pytest.mark.asyncio
async def test_financial_position_matches_the_accounts_page(client, db_session):
    await as_user(client, db_session)
    body = await get(client)
    position = body["financial_position"]
    month = position["balance_month"] or key(THIS_MONTH)
    accounts = await get(client, "/api/v1/management/accounts", month=month)
    assert Decimal(position["receivables"]) == Decimal(accounts["receivables"]["total"])
    assert Decimal(position["receivables_overdue"]) == Decimal(accounts["receivables"]["overdue"])
    assert position["pending_invoices"]["count"] == accounts["pending_invoices"]["count"]
    for field in ("cash_bank", "payables", "tax_liabilities"):
        expected = accounts["balances"][field] if position["balance_month"] else None
        assert (position[field] is None and expected is None) or Decimal(position[field]) == Decimal(expected)


# --- the panels match their pages (HM5-HM13) ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_growth_matches_the_health_page(client, db_session):
    await as_user(client, db_session)
    body = await get(client)
    health = await get(client, "/api/v1/management/health")
    growth = body["growth"]
    assert growth["month"] == health["month"] == last_complete_month()
    assert (growth["score"], growth["rag"]) == (health["score"], health["rag"])
    assert [(f["key"], f["change"], f["rag"]) for f in growth["factors"]] == [(f["key"], f["change"], f["rag"]) for f in health["factors"]]
    reds = [u for u in body["urgent"] if u["key"] == "red_health"]
    red_count = sum(f["rag"] == "red" for f in health["factors"])
    assert (reds[0]["count"] if reds else 0) == red_count


@pytest.mark.asyncio
async def test_an_overdue_decision_is_pending_and_urgent(client, db_session):
    partner = await as_user(client, db_session)
    before = await get(client)
    created = await client.post(
        "/api/v1/management/discussions",
        json={"topic": "Renew office lease", "discussion_date": (TODAY - timedelta(days=20)).isoformat(), "status": "open",
              "participant_ids": [str(partner.id)], "decision": "Renew for two years", "responsible_user_id": str(partner.id),
              "deadline": (TODAY - timedelta(days=1)).isoformat()},
    )  # fmt: skip
    assert created.status_code == 201, created.text
    body = await get(client)

    pending = await get(client, "/api/v1/management/discussions", pending="true", limit=5)
    assert body["pending_decisions"]["total"] == pending["total"] == before["pending_decisions"]["total"] + 1
    assert [d["id"] for d in body["pending_decisions"]["items"]] == [d["id"] for d in pending["items"]]
    overdue = {u["key"]: u["count"] for u in body["urgent"]}.get("overdue_decisions", 0)
    assert overdue == {u["key"]: u["count"] for u in before["urgent"]}.get("overdue_decisions", 0) + 1

    recent = await get(client, "/api/v1/management/discussions", limit=5)
    assert [d["id"] for d in body["recent_discussions"]["items"]] == [d["id"] for d in recent["items"]]
    assert body["recent_discussions"]["total"] == recent["total"]
    await db_session.execute(update(ManagementDiscussion).where(ManagementDiscussion.id == created.json()["id"]).values(status="cancelled"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_my_overdue_task_is_in_my_tasks_and_urgent(client, db_session):
    partner = await as_user(client, db_session)
    before = await get(client)
    created = await client.post("/api/v1/management/tasks", json={"title": "Sign the lease", "owner_user_id": str(partner.id), "priority": "high", "deadline": TODAY.isoformat()})
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    await db_session.execute(update(ManagementTask).where(ManagementTask.id == task_id).values(deadline=TODAY - timedelta(days=2)))
    await db_session.commit()
    body = await get(client)

    mine = await get(client, "/api/v1/management/tasks", owner="me", limit=5)
    assert body["my_tasks"]["counts"] == mine["counts"]
    assert [t["id"] for t in body["my_tasks"]["items"]] == [t["id"] for t in mine["items"]]
    assert body["my_tasks"]["counts"]["overdue"] == 1  # a fresh partner owns only this task
    assert {u["key"]: u["count"] for u in body["urgent"]}["overdue_tasks"] == {u["key"]: u["count"] for u in before["urgent"]}.get("overdue_tasks", 0) + 1


@pytest.mark.asyncio
async def test_todays_meetings_match_the_meetings_page(client, db_session):
    """HM7 / QA31-01: the calendar's first five of today, and today's total (the panel stays bounded on a busy day)."""
    await as_user(client, db_session)
    before = await get(client)
    start = datetime.datetime.combine(TODAY, datetime.time(23, 30), datetime.timezone(timedelta(hours=5, minutes=30)))
    for _ in range(6):
        created = await client.post(
            "/api/v1/management/meetings", json={"title": "Partner sync", "kind": "partner", "starts_at": start.isoformat(), "mode": "Online", "meeting_url": "https://meet.example.com/x"}
        )
        assert created.status_code == 201, created.text
    body = await get(client)
    page = await get(client, "/api/v1/management/meetings")
    assert [m["id"] for m in body["meetings"]["items"]] == [m["id"] for m in page["items"][:5]]
    assert body["meetings"]["total"] == len(page["items"]) == before["meetings"]["total"] + 6


@pytest.mark.asyncio
async def test_targets_and_next_month_plan_match_the_plans_pages(client, db_session):
    nxt = add_months(THIS_MONTH, 1)
    await clear(db_session, [THIS_MONTH, nxt])
    try:
        await as_user(client, db_session)
        empty = await get(client)
        assert empty["targets"] is None
        assert empty["next_plan"] == {"month": key(nxt), "label": nxt.strftime("%B %Y"), "plan": None}

        await new_plan(client, THIS_MONTH)
        await new_item(client, THIS_MONTH, kpi="applications", target="100")
        await new_item(client, THIS_MONTH, text="Sign Japanese universities")
        await new_plan(client, nxt)
        await new_item(client, nxt, kpi="agents", target="30")
        body = await get(client)

        progress = await get(client, f"/api/v1/management/plans/{key(THIS_MONTH)}/progress")
        targets = body["targets"]
        assert targets["month"] == key(THIS_MONTH) and targets["row_total"] == len(progress["rows"]) == 1
        assert [(r["kpi"], r["target"], r["actual"], r["achievement"]) for r in targets["rows"]] == [(r["kpi"], r["target"], r["actual"], r["achievement"]) for r in progress["rows"]]
        assert targets["free_text"] == progress["free_text"] == {"total": 1, "done": 0}
        plan = body["next_plan"]["plan"]
        assert (plan["item_count"], plan["kpi_count"], plan["status"]) == (1, 1, "draft")
    finally:
        await clear(db_session, [THIS_MONTH, nxt])
