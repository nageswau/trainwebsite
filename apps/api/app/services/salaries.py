"""mgmt-011 (spec SM1-SM14): salary management -- department totals per month (M6) and the Employee Cost Ratio (Appendix B R6/R7).

Finance tier only (M13): the routes call `ledger.require_finance` first, so super_admin and every other role get 403. Every write adds a
`management_audit` row (field names, never salary values) in the caller's transaction; the routes in `api/management.py` commit once.
Saved rows reach the ledger as automatic "Salaries" expense lines through `ledger.lines()` (SM8). Nothing is copied.
Spec: docs/superpowers/specs/2026-10-12-mgmt-011-salary-management-design.md.
"""

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SALARY_MONEY, Department, SalaryMonthTotal, User
from app.schemas import DepartmentCreate, DepartmentUpdate, SalaryRowIn
from app.services import ledger, management_audit

logger = logging.getLogger("app.management")
FIGURES = ("headcount", *SALARY_MONEY)
COST = ("paid", "incentives", "commissions", "employer_cost")  # SM6: R6 = what the month cost, cash basis
CENTS = Decimal("0.01")
NOT_FOUND = "Department not found"
DUPLICATE = "A department with this name already exists"
FUTURE = "Salaries can be recorded up to the current month"


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def first_day(month: str | None, future: str = FUTURE) -> date:
    """`YYYY-MM` (the route's pattern has already checked the shape) -> the month's 1st, the current IST month when none is given; a
    month after the current one is 422 with `future` (mgmt-013's accounts page passes its own wording)."""
    current = ledger.today().replace(day=1)
    if month is None:
        return current
    year, number = (int(part) for part in month.split("-"))
    first = date(year, number, 1)
    if first > current:
        raise HTTPException(422, [{"loc": ["query", "month"], "msg": future, "type": "value_error"}])
    return first


def log(event: str, user: User, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), **extra}})


# --- departments (SM1, SM2) ---------------------------------------------------------------------------------------------------------
def department_out(d: Department) -> dict:
    return {"id": d.id, "name": d.name, "active": d.active}


async def departments(db: AsyncSession) -> list[dict]:
    rows = (await db.scalars(select(Department).order_by(Department.active.desc(), func.lower(Department.name)))).all()
    return [department_out(d) for d in rows]


async def name_taken(db: AsyncSession, name: str, except_id=None) -> bool:
    stmt = select(Department.id).where(func.lower(Department.name) == name.lower())
    if except_id is not None:
        stmt = stmt.where(Department.id != except_id)
    return await db.scalar(stmt.limit(1)) is not None


async def create_department(db: AsyncSession, user: User, payload: DepartmentCreate) -> Department:
    if await name_taken(db, payload.name):
        raise HTTPException(409, DUPLICATE)
    department = Department(name=payload.name, created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(department)
    await db.flush()
    management_audit.record(db, user, "mgmt.department", "create", str(department.id), fields=["name"])
    return department


async def change_department(db: AsyncSession, user: User, department_id, payload: DepartmentUpdate) -> Department:
    """Rename or (de)activate; a deactivated department keeps its months (SM2). A change that changes nothing writes nothing."""
    department = await db.scalar(select(Department).where(Department.id == department_id).with_for_update())
    if department is None:
        raise HTTPException(404, NOT_FOUND)
    sent = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    changed = [field for field, value in sent.items() if getattr(department, field) != value]
    if not changed:
        return department
    if "name" in changed and await name_taken(db, sent["name"], except_id=department.id):
        raise HTTPException(409, DUPLICATE)
    for field in changed:
        setattr(department, field, sent[field])
    department.updated_by_user_id = user.id
    await db.flush()
    management_audit.record(db, user, "mgmt.department", "update", str(department.id), fields=changed)
    return department


# --- one month (SM3-SM7, SM14) ------------------------------------------------------------------------------------------------------
def total_cost(figures: dict) -> Decimal:
    """SM6 (R6): paid + incentives + commissions + employer cost."""
    cost = Decimal(0)
    for f in COST:
        cost += figures[f]
    return cost.quantize(CENTS)


def ratio(cost: Decimal, revenue: Decimal) -> Decimal | None:
    """R7 = employee cost ÷ revenue × 100, half-up to 2 decimals; unknown (null) without revenue."""
    return (cost / revenue * 100).quantize(CENTS, ROUND_HALF_UP) if revenue > 0 else None


async def revenue(db: AsyncSession, month: date) -> Decimal:
    """SM7: the month's counted ledger income -- approved manual entries + rupee automatic lines, every vertical (mgmt-005)."""
    table = ledger.lines()
    where = ledger.list_filters(month=month_key(month), kind="income", category_id=None, vertical=None, table=table)
    return (await ledger.lines_totals(db, table, where))["income"]


async def month_view(db: AsyncSession, month: date) -> dict:
    saved = {r.department_id: r for r in (await db.scalars(select(SalaryMonthTotal).where(SalaryMonthTotal.month == month))).all()}
    shown = (await db.scalars(select(Department).where(Department.active.is_(True) | Department.id.in_(list(saved))).order_by(func.lower(Department.name)))).all()
    rows: list[dict] = []
    totals: dict = {"headcount": 0, **dict.fromkeys(SALARY_MONEY, Decimal("0.00"))}
    for d in shown:
        row = saved.get(d.id)
        figures: dict = {f: (getattr(row, f) if row else None) for f in FIGURES}
        if row:
            for f in FIGURES:
                totals[f] += figures[f]
        warnings = ["paid_exceeds_payable"] if row and row.paid > row.payable else []  # SM5
        rows.append({"department": department_out(d), "entered": row is not None, **figures, "total_cost": total_cost(figures) if row else None, "warnings": warnings})
    totals["total_cost"] = total_cost(totals)
    income = await revenue(db, month)
    latest = max(saved.values(), key=lambda r: r.updated_at, default=None)
    editor = await db.get(User, latest.updated_by_user_id) if latest else None
    return {
        "month": month_key(month),
        "current_month": month_key(ledger.today()),
        "rows": rows,
        "totals": totals,
        "revenue": income,
        "ratio": ratio(totals["total_cost"], income),
        "updated_at": latest.updated_at if latest else None,
        "updated_by": {"id": editor.id, "full_name": editor.full_name} if editor else None,
    }


def row_error(index: int, message: str) -> HTTPException:
    """A database rule's 422 in FastAPI's own shape, placed on the row's department."""
    return HTTPException(422, [{"loc": ["body", "rows", index, "department_id"], "msg": message, "type": "value_error"}])


async def save_month(db: AsyncSession, user: User, month: date, rows: list[SalaryRowIn]) -> int:
    """SM4: the month becomes exactly `rows`. A transaction-scoped advisory lock serialises two saves of one month (SM12); one audit
    row names the changed fields and how many departments changed (SM11), and a save that changes nothing writes none."""
    key = month_key(month)
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"salary:{key}"))))
    saved = {r.department_id: r for r in (await db.scalars(select(SalaryMonthTotal).where(SalaryMonthTotal.month == month))).all()}
    known = {d.id: d for d in (await db.scalars(select(Department).where(Department.id.in_([r.department_id for r in rows])))).all()}
    for index, r in enumerate(rows):
        department = known.get(r.department_id)
        if department is None:
            raise row_error(index, "Choose a department from the list")
        if not department.active and r.department_id not in saved:
            raise row_error(index, f"{department.name} is no longer in use; reactivate it first")
    fields: set[str] = set()
    changed = 0
    for r in rows:
        values = r.model_dump(include=set(FIGURES))
        row = saved.pop(r.department_id, None)
        if row is None:
            db.add(SalaryMonthTotal(month=month, department_id=r.department_id, created_by_user_id=user.id, updated_by_user_id=user.id, **values))
            fields.update(FIGURES)
            changed += 1
            continue
        diff = [f for f in FIGURES if getattr(row, f) != values[f]]
        if diff:
            for f in diff:
                setattr(row, f, values[f])
            row.updated_by_user_id = user.id
            fields.update(diff)
            changed += 1
    for row in saved.values():  # left out of the PUT: removed
        await db.delete(row)
        fields.update(FIGURES)
        changed += 1
    if changed:
        await db.flush()
        management_audit.record(db, user, "mgmt.salary", "update", key, fields=[f for f in FIGURES if f in fields], count=changed)
    return changed
