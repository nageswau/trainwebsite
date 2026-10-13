"""mgmt-001: the Management Command Center's own routes. Every later mgmt item adds its routes here or beside it, each asking
`services/management_access` for its tier first (M13)."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models import INVESTMENT_STATUSES, INVESTMENT_VERTICALS, User
from app.schemas import (
    AbroadRevenueOut,
    AccountsOut,
    ApplicationFunnelOut,
    DepartmentCreate,
    DepartmentOut,
    DepartmentPage,
    DepartmentUpdate,
    ExpenseDashboardOut,
    FinanceBalancesIn,
    InvestmentCreate,
    InvestmentOut,
    InvestmentPageOut,
    InvestmentUpdate,
    ItRevenueOut,
    ItRevenuePaymentPage,
    ManagementActivityOut,
    ManagementBdmOut,
    ManagementCounselingOut,
    ManagementMeOut,
    ManagementSnapshotOut,
    RecruitmentRevenueOut,
    SalaryMonthIn,
    SalaryMonthOut,
    TelecallingOut,
)
from app.services import (
    accounts,
    investments,
    ledger,
    management_abroad_revenue,
    management_audit,
    management_bdm,
    management_counseling,
    management_expenses,
    management_it_revenue,
    management_metrics,
    management_recruitment_revenue,
    management_telecalling,
    salaries,
    telecaller_performance,
)
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.bdm_performance import period
from app.services.management_access import can_view_operational, require_management, require_partner_only, tiers

router = APIRouter(prefix="/management", tags=["management"])
MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"  # the `month` query of the expense (mgmt-010), salary (mgmt-011) and accounts (mgmt-013) routes
EARLIEST_MONTH = date(2000, 1, 1)  # mgmt-010 (ME9): the ledger's earliest entry date (ML4)


@router.get("/me", response_model=ManagementMeOut)
async def management_me(user: User = Depends(get_current_user)):
    """The caller and the tiers they may see: partner (all), accountant (finance), super_admin (operational); anyone else 403."""
    require_management(user)
    return {"id": user.id, "full_name": user.full_name, "role": user.role, "tiers": tiers(user)}


@router.get("/activity", response_model=ManagementActivityOut)
async def management_activity(
    actor: UUID | None = None,
    kind: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """mgmt-002 (MA5-MA7): who did what in management, newest first, limited to the kinds the caller's tier may see. Read-only."""
    require_management(user)
    if kind and kind not in management_audit.KINDS:
        raise HTTPException(422, "Unknown activity kind")
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, "The end date must be on or after the start date")
    return await management_audit.activity(db, user, actor_id=actor, kind=kind, date_from=date_from, date_to=date_to, limit=limit, offset=offset)


@router.get("/snapshot", response_model=ManagementSnapshotOut)
async def management_snapshot(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """mgmt-003 (§3, spec MS1-MS19): S1-S15 for the operational tier (partner, super_admin); the accountant and everyone else 403."""
    _operational(user)
    today = india_date(await db_now(db))
    figures = await management_metrics.snapshot(db, today)
    return {"as_of": today, "kpis": [{"id": kpi_id, "key": key, "label": label, "value": figures[key]} for kpi_id, key, label in management_metrics.SNAPSHOT]}


def _id_or_none(value: str | None) -> UUID | str | None:
    """mgmt-024 (MF14): an agency / counselor filter -- "none" or an id; anything else is a 422."""
    if value is None or value == "none":
        return value
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(422, "Unknown filter value") from None


@router.get("/applications", response_model=ApplicationFunnelOut)
async def application_funnel(
    date_from: date | None = None,
    date_to: date | None = None,
    agency: str | None = Query(None, max_length=36),
    counselor: str | None = Query(None, max_length=36),
    country: UUID | None = None,
    university: UUID | None = None,
    course: UUID | None = None,
    intake: str | None = Query(None, max_length=80),
    staff: UUID | None = None,
    status: str | None = Query(None, max_length=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """mgmt-024 (§20, spec MF1-MF18): the application funnel over the filtered applications, counts only, for the operational tier
    (partner, super_admin); the accountant and everyone else 403."""
    require_management(user)
    if not can_view_operational(user):
        raise HTTPException(403, "Operational access required")
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, "The end date must be on or after the start date")
    filters = management_metrics.ApplicationFunnelFilters(
        date_from=date_from, date_to=date_to, agency=_id_or_none(agency), counselor=_id_or_none(counselor), country=country,
        university=university, course=course, intake=intake or None, staff=staff, status=status or None,
    )  # fmt: skip
    counts = await management_metrics.applications(db, filters)
    return {
        "filters": {key: None if value is None else str(value) for key, value in vars(filters).items()},
        "stages": [{"key": key, "label": label, "tracked": tracked, "value": counts[key] if tracked else None} for key, label, tracked in management_metrics.FUNNEL],
        "withdrawn": counts["withdrawn"],
        "options": await management_metrics.application_options(db),
    }


def _operational(user: User) -> User:
    """M13: the operational tier (partner, super_admin); the accountant gets "Operational access required", anyone else 403 too."""
    require_management(user)
    if not can_view_operational(user):
        raise HTTPException(403, "Operational access required")
    return user


@router.get("/bdm", response_model=ManagementBdmOut)
async def bdm_dashboard(
    type: Literal["agent", "school", "college"] = "agent",  # noqa: A002 -- the backlog's query parameter name
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """mgmt-020 (§16, spec BD1-BD12): one BDM type's figures, company-wide, for `from`..`to` (IST, default this month; bdm-024 P2)."""
    _operational(user)
    now = await db_now(db)
    start, end = period(from_, to, india_date(now))
    return await management_bdm.dashboard(db, type, start, end, now)


@router.get("/counseling", response_model=ManagementCounselingOut)
async def counseling_dashboard(
    from_: date | None = Query(None, alias="from"), to: date | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """mgmt-018 (§13, spec CS1-CS12): every counselor's figures and the totals for `from`..`to` (IST, default this month). Operational
    tier; only the finance tier among it (partner) gets revenue."""
    _operational(user)
    now = await db_now(db)
    start, end = period(from_, to, india_date(now))
    return await management_counseling.dashboard(db, user, start, end, now)


@router.get("/expenses", response_model=ExpenseDashboardOut)
async def expense_dashboard(month: str | None = Query(None, pattern=MONTH), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """mgmt-010 (§8, spec ME1-ME10): the expense heads for `month` (YYYY-MM, default this IST month) and its financial year to date.
    Finance tier only (partner, accountant); super_admin gets "Finance access required" (M13)."""
    ledger.require_finance(user)
    return await management_expenses.dashboard(db, await _past_month(db, month))


@router.get("/revenue/abroad", response_model=AbroadRevenueOut)
async def abroad_revenue(month: str | None = Query(None, pattern=MONTH), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """mgmt-006 (§4, spec MR1-MR12): Abroad Education revenue, its breakdowns, expenses and gross contribution for `month` and its
    financial year to date. Finance tier only (M13); university commission is in the figures for partners only (M3)."""
    ledger.require_finance(user)
    return await management_abroad_revenue.dashboard(db, user, await _past_month(db, month))


async def _past_month(db: AsyncSession, month: str | None) -> date:
    """ME9 (mgmt-006 MR10): the first day of `month` (YYYY-MM), default this IST month; January 2000 up to this month, else 422."""
    this_month = india_date(await db_now(db)).replace(day=1)
    chosen = date(int(month[:4]), int(month[5:]), 1) if month else this_month
    if chosen < EARLIEST_MONTH:
        raise HTTPException(422, "Choose January 2000 or a later month")
    if chosen > this_month:
        raise HTTPException(422, "Choose this month or an earlier one")
    return chosen


@router.get("/revenue/it", response_model=ItRevenueOut)
async def it_revenue(
    month: str | None = Query(None, pattern=MONTH), period: Literal["month", "year"] = "month", user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """mgmt-007 (§5, spec IR1-IR12): IT Training revenue, costs and enrolments per course and batch for `month` or its financial year
    to date. Finance tier only (partner, accountant); super_admin gets "Finance access required" (M13)."""
    ledger.require_finance(user)
    return await management_it_revenue.dashboard(db, await _past_month(db, month), period)


@router.get("/revenue/it/payments", response_model=ItRevenuePaymentPage)
async def it_revenue_payments(
    month: str | None = Query(None, pattern=MONTH),
    period: Literal["month", "year"] = "month",
    program_id: UUID | None = None,
    batch_id: UUID | None = None,
    unlinked: bool = False,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """mgmt-007 (IR11): the IT payments behind one course, one batch or the "Not linked to a course" row, newest first. No names (Q-32)."""
    ledger.require_finance(user)
    chosen = await _past_month(db, month)
    return await management_it_revenue.payments(db, chosen, period, program_id=program_id, batch_id=batch_id, unlinked=unlinked, limit=limit, offset=offset)


@router.get("/revenue/recruitment", response_model=RecruitmentRevenueOut)
async def recruitment_revenue(
    month: str | None = Query(None, pattern=MONTH), period: Literal["month", "year"] = "month", user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """mgmt-008 (§6, spec RR1-RR12): Recruitment revenue by kind and the nine KPIs for `month` or its financial year to date. Every
    management role reads the KPIs; only the finance tier (partner, accountant) gets money -- the super admin's read has none (RR9)."""
    require_management(user)
    chosen = await _past_month(db, month)
    return await management_recruitment_revenue.dashboard(db, user, chosen, period, await db_now(db))


def _partner(user: User) -> User:
    """mgmt-014 (MI12, M13): partner-only. The accountant and super_admin get "Only partners can open this"; anyone else 403 too."""
    return require_partner_only(require_management(user))


@router.get("/investments", response_model=InvestmentPageOut)
async def list_investments(
    date_from: date | None = None,
    date_to: date | None = None,
    vertical: str | None = None,
    status: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """mgmt-014 (§23, MI8/MI9): the register, newest first, with totals over every match (cancelled excluded) and the investor choices."""
    _partner(user)
    if vertical and vertical not in INVESTMENT_VERTICALS:
        raise HTTPException(422, "Unknown vertical")
    if status and status not in INVESTMENT_STATUSES:
        raise HTTPException(422, "Unknown status")
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, "The end date must be on or after the start date")
    return await investments.page(db, date_from=date_from, date_to=date_to, vertical=vertical, status=status, limit=limit, offset=offset)


@router.post("/investments", response_model=InvestmentOut, status_code=201)
async def create_investment(body: InvestmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """mgmt-014 (MI1-MI6, MI11): records an investment and its audit entry together."""
    _partner(user)
    return await investments.one(db, await investments.create(db, user, body))


@router.get("/investments/{investment_id}", response_model=InvestmentOut)
async def get_investment(investment_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _partner(user)
    return await investments.one(db, await investments.get(db, investment_id))


@router.patch("/investments/{investment_id}", response_model=InvestmentOut)
async def update_investment(investment_id: UUID, body: InvestmentUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """mgmt-014 (MI10/MI11): changes only the fields sent; a change is audited with before and after values."""
    _partner(user)
    return await investments.one(db, await investments.update(db, user, investment_id, body))


# --- mgmt-011: salaries + departments (spec SM1-SM14). Finance tier only (M13): super_admin and every other role 403 --------------------


@router.get("/salaries", response_model=SalaryMonthOut)
async def salary_month(month: str | None = Query(None, pattern=MONTH), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """SM14: the month's grid (active departments + any with a row), totals, R6, revenue and the Employee Cost Ratio (R7)."""
    ledger.require_finance(user)
    return await salaries.month_view(db, salaries.first_day(month))


@router.put("/salaries", response_model=SalaryMonthOut)
async def save_salary_month(
    body: SalaryMonthIn, month: str = Query(..., pattern=MONTH), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """SM4: replaces the month with the rows sent; answers with the month as GET shows it."""
    ledger.require_finance(user)
    first = salaries.first_day(month)
    changed = await salaries.save_month(db, user, first, body.rows)
    await db.commit()
    salaries.log("salary_month_saved", user, month=month, changed=changed)
    return await salaries.month_view(db, first)


@router.get("/departments", response_model=DepartmentPage)
async def list_departments(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ledger.require_finance(user)
    return {"items": await salaries.departments(db)}


@router.post("/departments", response_model=DepartmentOut, status_code=201)
async def create_department(body: DepartmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ledger.require_finance(user)
    try:
        department = await salaries.create_department(db, user, body)
    except IntegrityError:  # the unique index, when two people add the same name at once
        await db.rollback()
        raise HTTPException(409, salaries.DUPLICATE) from None
    await db.commit()
    salaries.log("department_created", user, department_id=str(department.id))
    return salaries.department_out(department)


@router.patch("/departments/{department_id}", response_model=DepartmentOut)
async def change_department(department_id: UUID, body: DepartmentUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Rename or (de)activate (SM2)."""
    ledger.require_finance(user)
    try:
        department = await salaries.change_department(db, user, department_id, body)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, salaries.DUPLICATE) from None
    await db.commit()
    salaries.log("department_changed", user, department_id=str(department.id))
    return salaries.department_out(department)


# --- mgmt-013: accounts dashboard (spec AD1-AD14). Finance tier only (M13): super_admin and every other role 403 ------------------------
@router.get("/accounts", response_model=AccountsOut)
async def accounts_month(month: str | None = Query(None, pattern=MONTH), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AD14: the month's income and expense heads, profit, today's receivables and pending invoices, and the entered balances."""
    ledger.require_finance(user)
    return await accounts.view(db, salaries.first_day(month, accounts.FUTURE))


@router.put("/accounts/balances", response_model=AccountsOut)
async def save_accounts_balances(
    body: FinanceBalancesIn, month: str = Query(..., pattern=MONTH), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """AD8: saves the month's cash/bank, payables and tax liabilities (all null removes them); answers with the month as GET shows it."""
    ledger.require_finance(user)
    first = salaries.first_day(month, accounts.FUTURE)
    changed = await accounts.save_balances(db, user, first, body)
    await db.commit()
    salaries.log("finance_balances_saved", user, month=month, fields=changed)
    return await accounts.view(db, first)


# --- mgmt-019: company-wide Telecalling dashboard (spec TC1-TC16). Operational tier (M13) ----------------------------------------------
@router.get("/telecalling", response_model=TelecallingOut)
async def telecalling(date_from: date | None = None, date_to: date | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§14 per telecaller, per team and for the company over tel-023's period rules (TC2); the accountant and everyone else 403."""
    _operational(user)
    first, last = telecaller_performance.date_range(date_from, date_to, india_date(await db_now(db)))
    return await management_telecalling.dashboard(db, first, last)
