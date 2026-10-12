"""mgmt-011 -- salary management + employee cost ratio (spec SM1-SM14; AC1 ratio, AC2 super_admin 403, AC3 salary cost once in expenses).

The stack DB is shared and never emptied: every test works in its own random far-past month and its own new departments."""

import calendar
import random
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog, Department, LedgerCategory, LedgerEntry
from app.services import management_audit
from tests.bdm001_helpers import login, make_user

SALARIES = "/api/v1/management/salaries"
DEPARTMENTS = "/api/v1/management/departments"
LEDGER = "/api/v1/management/ledger"


def a_month() -> str:
    return f"{random.randint(2001, 2025)}-{random.randint(1, 12):02d}"


async def as_user(client, db, role: str = "accountant"):
    user = await make_user(db, role, "global")
    await login(client, user)
    return user


async def department(client, name: str | None = None) -> dict:
    response = await client.post(DEPARTMENTS, json={"name": name or f"Dept {uuid.uuid4().hex[:8]}"})
    assert response.status_code == 201, response.text
    return response.json()


def row(department_id: str, **overrides) -> dict:
    return {"department_id": department_id, "headcount": 4, "payable": "200000", "paid": "180000", "incentives": "15000", "commissions": "5000",
            "employer_cost": "20000", **overrides}  # fmt: skip


async def put(client, month: str, rows: list[dict]):
    return await client.put(SALARIES, params={"month": month}, json={"rows": rows})


async def view(client, month: str) -> dict:
    response = await client.get(SALARIES, params={"month": month})
    assert response.status_code == 200, response.text
    return response.json()


def mine(out: dict, department_id: str) -> dict:
    return next(r for r in out["rows"] if r["department"]["id"] == department_id)


async def approved_income(db, month: str, amount: str) -> None:
    """Approved manual income in the month: the revenue the ratio divides by (SM7)."""
    year, number = (int(p) for p in month.split("-"))
    category_id = await db.scalar(select(LedgerCategory.id).where(LedgerCategory.kind == "income").limit(1))
    author = await make_user(db, "accountant", "global")
    db.add(LedgerEntry(entry_date=date(year, number, 10), kind="income", category_id=category_id, amount=Decimal(amount), description="Fees",
                       vertical="it", status="approved", created_by_user_id=author.id, updated_by_user_id=author.id))  # fmt: skip
    await db.commit()


# --- AC1: the ratio -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_cost_and_ratio_follow_the_formula(client, db_session):
    await as_user(client, db_session)
    month = a_month()
    a, b = await department(client), await department(client)
    await approved_income(db_session, month, "1000000")
    response = await put(client, month, [row(a["id"]), row(b["id"], headcount=1, payable="50000", paid="50000", incentives="0", commissions="0", employer_cost="5000")])
    assert response.status_code == 200, response.text
    out = await view(client, month)
    first = mine(out, a["id"])
    assert first["entered"] is True and first["total_cost"] == "220000.00"  # SM6: paid + incentives + commissions + employer cost
    assert mine(out, b["id"])["total_cost"] == "55000.00"
    # Revenue is every counted income line of the month; this month has only ours unless another test's random month collides.
    revenue = Decimal(out["revenue"])
    assert revenue >= Decimal("1000000.00")
    totals = out["totals"]
    assert Decimal(totals["total_cost"]) >= Decimal("275000.00")
    expected = (Decimal(totals["total_cost"]) / revenue * 100).quantize(Decimal("0.01"))
    assert Decimal(out["ratio"]) == expected


@pytest.mark.asyncio
async def test_ratio_is_null_without_revenue_and_unentered_departments_show_no_figures(client, db_session):
    await as_user(client, db_session)
    month = "1999-02"  # before every other test's months: no revenue
    d = await department(client)
    out = await view(client, month)
    assert out["revenue"] == "0.00" and out["ratio"] is None
    r = mine(out, d["id"])
    assert r["entered"] is False and r["headcount"] is None and r["total_cost"] is None and r["warnings"] == []


# --- AC2: super_admin and other roles are refused ----------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["super_admin", "it_admin"])
async def test_ac2_non_finance_roles_get_403_everywhere(client, db_session, role):
    await as_user(client, db_session, role)
    month = a_month()
    checks = [
        await client.get(SALARIES, params={"month": month}),
        await put(client, month, []),
        await client.get(DEPARTMENTS),
        await client.post(DEPARTMENTS, json={"name": "Sneaky"}),
        await client.patch(f"{DEPARTMENTS}/{uuid.uuid4()}", json={"active": False}),
    ]
    assert [r.status_code for r in checks] == [403] * 5
    if role == "super_admin":
        assert checks[0].json()["detail"] == "Finance access required"


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(SALARIES, params={"month": "2020-01"})).status_code == 401


@pytest.mark.asyncio
async def test_partner_can_read_and_write(client, db_session):
    await as_user(client, db_session, "partner")
    month = a_month()
    d = await department(client)
    assert (await put(client, month, [row(d["id"])])).status_code == 200
    assert mine(await view(client, month), d["id"])["headcount"] == 4


# --- AC3: salary cost appears once in expenses -------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac3_each_saved_department_row_is_one_automatic_salary_expense_line(client, db_session):
    await as_user(client, db_session)
    month = a_month()
    d = await department(client, f"Training {uuid.uuid4().hex[:6]}")
    zero = await department(client)
    await put(client, month, [row(d["id"]), row(zero["id"], headcount=0, payable="0", paid="0", incentives="0", commissions="0", employer_cost="0")])
    lines = (await client.get(LEDGER, params={"include": "auto", "month": month, "kind": "expense", "limit": 100})).json()["items"]
    salary = [line for line in lines if line["source"] == "salary"]
    ours = [line for line in salary if line["description"] == f"Salaries · {d['name']}"]
    assert len(ours) == 1
    line = ours[0]
    year, number = (int(p) for p in month.split("-"))
    last_day = date(year, number, calendar.monthrange(year, number)[1]).isoformat()
    assert (line["kind"], line["vertical"], line["category_label"], line["amount"], line["counted"]) == ("expense", "shared", "Salaries", "220000.00", True)
    assert line["entry_date"] == last_day
    assert not [line for line in salary if line["description"] == f"Salaries · {zero['name']}"]  # nothing to post for a zero cost
    # Re-saving the month replaces the line instead of adding another one.
    await put(client, month, [row(d["id"], paid="190000")])
    lines = (await client.get(LEDGER, params={"include": "auto", "month": month, "kind": "expense", "limit": 100})).json()["items"]
    ours = [line for line in lines if line["source"] == "salary" and line["description"] == f"Salaries · {d['name']}"]
    assert [line["amount"] for line in ours] == ["230000.00"]


@pytest.mark.asyncio
async def test_ac3_the_manual_salaries_category_is_inactive(client, db_session):
    await as_user(client, db_session)
    categories = (await client.get(f"{LEDGER}/categories")).json()["items"]
    assert [c["active"] for c in categories if c["kind"] == "expense" and c["name"] == "Salaries"] == [False]


# --- PUT: replace the month (SM4) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_put_replaces_the_month(client, db_session):
    await as_user(client, db_session)
    month = a_month()
    a, b = await department(client), await department(client)
    await put(client, month, [row(a["id"]), row(b["id"])])
    response = await put(client, month, [row(a["id"], headcount=5)])
    assert response.status_code == 200
    out = response.json()  # the PUT answers with the month view
    assert mine(out, a["id"])["headcount"] == 5 and mine(out, b["id"])["entered"] is False
    assert out["updated_by"] is not None and out["updated_at"] is not None


@pytest.mark.asyncio
async def test_put_paid_above_payable_saves_with_a_warning(client, db_session):
    await as_user(client, db_session)
    month = a_month()
    d = await department(client)
    response = await put(client, month, [row(d["id"], payable="100", paid="150")])
    assert response.status_code == 200
    assert mine(response.json(), d["id"])["warnings"] == ["paid_exceeds_payable"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [("headcount", -1), ("headcount", 100_001), ("headcount", 1.5), ("paid", "-1"), ("payable", "1.234"), ("incentives", "abc"),
     ("employer_cost", "1000000000000"), ("commissions", None)],
)  # fmt: skip
async def test_put_rejects_bad_values_on_their_field(client, db_session, field, value):
    await as_user(client, db_session)
    d = await department(client)
    response = await put(client, a_month(), [row(d["id"], **{field: value})])
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == field


@pytest.mark.asyncio
async def test_put_rejects_duplicate_unknown_and_newly_inactive_departments(client, db_session):
    await as_user(client, db_session)
    month = a_month()
    d = await department(client)
    dup = await put(client, month, [row(d["id"]), row(d["id"])])
    assert dup.status_code == 422 and "once" in str(dup.json()["detail"])
    unknown = await put(client, month, [row(str(uuid.uuid4()))])
    assert unknown.status_code == 422 and "department" in str(unknown.json()["detail"]).lower()
    kept = await department(client)
    await put(client, month, [row(kept["id"])])
    for target in (d, kept):
        assert (await client.patch(f"{DEPARTMENTS}/{target['id']}", json={"active": False})).status_code == 200
    inactive = await put(client, month, [row(kept["id"]), row(d["id"])])
    assert inactive.status_code == 422 and "no longer in use" in str(inactive.json()["detail"])
    # A department deactivated after its month was entered keeps its row and can still be corrected (SM2).
    assert (await put(client, month, [row(kept["id"], headcount=2)])).status_code == 200
    assert mine(await view(client, month), kept["id"])["department"]["active"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("month", ["2026-13", "26-01", "2026-1", "", "2999-01"])
async def test_bad_or_future_month_is_422(client, db_session, month):
    await as_user(client, db_session)
    assert (await client.get(SALARIES, params={"month": month})).status_code == 422
    assert (await put(client, month, [])).status_code == 422


@pytest.mark.asyncio
async def test_month_defaults_to_the_current_month(client, db_session):
    await as_user(client, db_session)
    out = (await client.get(SALARIES)).json()
    assert out["month"] == out["current_month"]


@pytest.mark.asyncio
async def test_put_writes_one_audit_row_without_values_and_none_for_a_no_op(client, db_session):
    await as_user(client, db_session)
    month = a_month()
    d = await department(client)
    await put(client, month, [row(d["id"])])
    await put(client, month, [row(d["id"])])  # nothing changed
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_type == "mgmt.salary", AuditLog.entity_id == month))).all()
    assert len(rows) == 1
    meta = rows[0].metadata_json
    assert meta["count"] == 1 and "paid" in meta["fields"] and "values" not in meta


# --- departments (SM1, SM2) ----------------------------------------------------------------------------------------------------------
def test_audit_catalogue_registers_the_finance_kinds():
    assert management_audit.KINDS["mgmt.salary"][1] == "finance" and management_audit.KINDS["mgmt.department"][1] == "finance"


@pytest.mark.asyncio
async def test_department_add_rename_deactivate_and_duplicates(client, db_session):
    await as_user(client, db_session)
    name = f"Ops {uuid.uuid4().hex[:8]}"
    d = await department(client, name)
    assert (d["name"], d["active"]) == (name, True)
    assert (await client.post(DEPARTMENTS, json={"name": name.upper()})).status_code == 409
    assert (await client.post(DEPARTMENTS, json={"name": "x"})).status_code == 422
    renamed = await client.patch(f"{DEPARTMENTS}/{d['id']}", json={"name": f"{name} 2"})
    assert renamed.status_code == 200 and renamed.json()["name"] == f"{name} 2"
    assert (await client.patch(f"{DEPARTMENTS}/{d['id']}", json={"active": False})).json()["active"] is False
    assert (await client.patch(f"{DEPARTMENTS}/{uuid.uuid4()}", json={"active": False})).status_code == 404
    listed = (await client.get(DEPARTMENTS)).json()["items"]
    assert any(i["id"] == d["id"] and i["active"] is False for i in listed)
    audits = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == d["id"]))).all()
    assert sorted(audits) == ["mgmt.department.create", "mgmt.department.update", "mgmt.department.update"]


@pytest.mark.asyncio
async def test_inactive_department_without_a_row_is_left_out_of_the_grid(client, db_session):
    await as_user(client, db_session)
    d = await department(client)
    await client.patch(f"{DEPARTMENTS}/{d['id']}", json={"active": False})
    out = await view(client, a_month())
    assert d["id"] not in {r["department"]["id"] for r in out["rows"]}


@pytest.mark.asyncio
async def test_seeded_departments_exist(db_session):
    names = set((await db_session.scalars(select(Department.name))).all())
    assert {"Counseling", "Telecalling", "Training"} <= names
