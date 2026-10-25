"""mgmt-001: the Management Command Center's own routes. Every later mgmt item adds its routes here or beside it, each asking
`services/management_access` for its tier first (M13)."""

from datetime import date, timedelta
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
    DrillOut,
    ApplicationFunnelOut,
    CapitalEntryCreate,
    CapitalEntryOut,
    CapitalOut,
    CapitalSharesIn,
    CapitalSharesOut,
    CrmReportsOut,
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
    ManagementAgentsOut,
    ManagementBdmOut,
    ManagementCounselingOut,
    ManagementHealthOut,
    ManagementHomeOut,
    ManagementMeOut,
    ManagementSchoolsOut,
    ManagementSchoolValuesIn,
    ManagementSchoolValuesOut,
    ManagementSnapshotOut,
    ManagementTrainingOut,
    ManagementUniversitiesOut,
    MarketingBudgetsIn,
    MarketingOut,
    PnlOut,
    RecruitmentDashboardOut,
    RecruitmentRevenueOut,
    SalaryMonthIn,
    SalaryMonthOut,
    StudentFunnelOut,
    TelecallingOut,
)
from app.services import (
    accounts,
    investments,
    ledger,
    management_abroad_revenue,
    management_agents,
    management_audit,
    management_bdm,
    management_counseling,
    management_crm_reports,
    management_drill,
    management_expenses,
    management_funnel,
    management_health,
    management_home,
    management_it_revenue,
    management_marketing,
    management_metrics,
    management_pnl,
    management_recruitment,
    management_recruitment_revenue,
    management_schools,
    management_telecalling,
    management_training,
    management_universities,
    partner_capital,
    salaries,
    telecaller_performance,
)
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.bdm_performance import period
from app.services.management_access import can_view_operational, can_view_university_commission, require_crm_reports, require_management, require_partner_only, tiers
from app.services.partnership_metrics import period as partnership_period

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


@router.get("/crm-reports", response_model=CrmReportsOut)
async def crm_reports(
    date_from: date | None = None,
    date_to: date | None = None,
    counselor: str | None = Query(None, max_length=36),
    country: UUID | None = None,
    university: UUID | None = None,
    course: UUID | None = None,
    intake: str | None = Query(None, max_length=80),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ccrm-034 (§13, AC 8, DEC-SCOPE-266 R1-R10): ageing, university performance, visa outcomes, document readiness, lead conversion
    by intake and the forecast by intake -- counts only. Partner, super_admin and the Overseas Admin; everyone else 403."""
    require_crm_reports(user)
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, "The end date must be on or after the start date")
    filters = management_crm_reports.ReportFilters(date_from=date_from, date_to=date_to, counselor=_id_or_none(counselor), country=country, university=university, course=course, intake=intake or None)
    today = india_date(await db_now(db))
    body = await management_crm_reports.reports(db, filters, today)
    return {**body, "filters": {key: None if value is None else str(value) for key, value in vars(filters).items()}, "as_of": today}


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


@router.get("/training", response_model=ManagementTrainingOut)
async def training_dashboard(
    from_: date | None = Query(None, alias="from"), to: date | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """mgmt-017 (§12, spec TR1-TR16): the training KPIs and every trainer's figures for `from`..`to` (IST, default this month).
    Operational tier (partner, super_admin)."""
    _operational(user)
    now = await db_now(db)
    start, end = period(from_, to, india_date(now))
    return await management_training.dashboard(db, start, end, now)


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


@router.get("/pnl", response_model=PnlOut)
async def profit_and_loss(
    month: str | None = Query(None, pattern=MONTH), period: Literal["month", "quarter", "year"] = "month", user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """mgmt-009 (§7, spec PL1-PL12): revenue, expenses, contribution and margin per vertical, the unallocated shared costs and the total
    for `month`, its financial-year quarter or its financial year to date. Finance tier only (partner, accountant); super_admin gets
    "Finance access required" (M13). University commission is in the figures for partners only (M3)."""
    ledger.require_finance(user)
    return await management_pnl.dashboard(db, user, await _past_month(db, month), period)


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


# --- mgmt-015: partner capital accounts (spec CP1-CP15). Partner-only (M13): super_admin, the accountant and every other role 403 -------
@router.get("/capital", response_model=CapitalOut)
async def capital_accounts(
    month: str | None = Query(None, pattern=MONTH),
    period: Literal["month", "quarter", "year"] = "year",
    offset: int = Query(0, ge=0, le=10_000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """§24 (CP8-CP10): each partner's figures as of today, the indicative profit share over `period` up to `month` (default this IST
    month's financial year to date), 25 entries from `offset`, newest first, and the share history."""
    _partner(user)
    chosen = await _past_month(db, month)
    return await partner_capital.view(db, user, chosen, period, offset, india_date(await db_now(db)))


@router.post("/capital/entries", response_model=CapitalEntryOut, status_code=201)
async def record_capital_entry(body: CapitalEntryCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """CP2-CP4, CP12: records one capital entry and its audit row together."""
    _partner(user)
    entry = await partner_capital.add_entry(db, user, body, india_date(await db_now(db)))
    await db.refresh(entry)  # the server-set created_at
    [out] = await partner_capital.entries_out(db, [entry])
    return out


@router.put("/capital/shares", response_model=CapitalSharesOut)
async def set_capital_shares(body: CapitalSharesIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """CP5/CP6/CP12/CP14: sets the sent partners' share % and commitment from the month; answers with the whole share history."""
    _partner(user)
    today = india_date(await db_now(db))
    await partner_capital.set_shares(db, user, body, today)
    return {"items": await partner_capital.share_history(db, today)}


# --- mgmt-011: salaries + departments (spec SM1-SM14). Finance tier only (M13): super_admin and every other role 403 --------------------


@router.get("/salaries", response_model=SalaryMonthOut)
async def salary_month(month: str | None = Query(None, pattern=MONTH), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """SM14: the month's grid (active departments + any with a row), totals, R6, revenue and the Employee Cost Ratio (R7)."""
    ledger.require_finance(user)
    return await salaries.month_view(db, salaries.first_day(month), can_view_university_commission(user))


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
    return await salaries.month_view(db, first, can_view_university_commission(user))


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
    return await accounts.view(db, salaries.first_day(month, accounts.FUTURE), can_view_university_commission(user))


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
    return await accounts.view(db, first, can_view_university_commission(user))


# --- mgmt-012: marketing budget & ROI (spec MK1-MK14). Every management role reads lead figures; money for the finance tier only -------
@router.get("/marketing", response_model=MarketingOut)
async def marketing(month: str | None = Query(None, pattern=MONTH), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """MK11: K1-K7 per channel, the §15 groups and the campaigns for `month` (YYYY-MM, default this IST month). super_admin reads the
    lead counts; budget, spend, revenue and ROI are null and never queried."""
    require_management(user)
    return await management_marketing.dashboard(db, user, salaries.first_day(month, management_marketing.FUTURE))


@router.put("/marketing/budgets", response_model=MarketingOut)
async def save_marketing_budgets(
    body: MarketingBudgetsIn, month: str = Query(..., pattern=MONTH), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """MK4: replaces the month's budgets with the ones sent; answers with the month as GET shows it. Partner and accountant only."""
    ledger.require_finance(user)
    first = salaries.first_day(month, management_marketing.FUTURE)
    changed = await management_marketing.save_budgets(db, user, first, body.budgets)
    await db.commit()
    salaries.log("marketing_budgets_saved", user, month=month, channels=changed)
    return await management_marketing.dashboard(db, user, first)


# --- mgmt-019: company-wide Telecalling dashboard (spec TC1-TC16). Operational tier (M13) ----------------------------------------------
@router.get("/telecalling", response_model=TelecallingOut)
async def telecalling(date_from: date | None = None, date_to: date | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§14 per telecaller, per team and for the company over tel-023's period rules (TC2); the accountant and everyone else 403."""
    _operational(user)
    first, last = telecaller_performance.date_range(date_from, date_to, india_date(await db_now(db)))
    return await management_telecalling.dashboard(db, first, last)


# --- mgmt-025: company-wide Recruitment dashboard (spec RC1-RC12). Operational tier (M13); revenue for the finance tier only -------------
@router.get("/recruitment", response_model=RecruitmentDashboardOut)
async def recruitment(date_from: date | None = None, date_to: date | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§21's eleven KPIs over rec-033's period rules and the company pipeline now; the accountant and everyone else 403 (RC10)."""
    _operational(user)
    return await management_recruitment.dashboard(db, user, date_from, date_to, await db_now(db))


# --- mgmt-021: Agent network dashboard (spec AN1-AN14). Operational tier (M13); money for the finance tier only (AN9) ---------------------
@router.get("/agents", response_model=ManagementAgentsOut)
async def agents_dashboard(from_: date | None = Query(None, alias="from"), to: date | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§17 for every approved agency and in total, for `from`..`to` (IST, default this month; AN13). The accountant and everyone else 403."""
    _operational(user)
    now = await db_now(db)
    start, end = period(from_, to, india_date(now))
    return await management_agents.dashboard(db, user, start, end, now)


# --- mgmt-022: School dashboard (spec SD1-SD16). Every management role reads; money and the values for the finance tier only ------------
@router.get("/schools", response_model=ManagementSchoolsOut)
async def schools_dashboard(from_: date | None = Query(None, alias="from"), to: date | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§18 for every school and in total, for `from`..`to` (IST, default this month; SD2). Anyone outside management 403 (SD1)."""
    require_management(user)
    now = await db_now(db)
    today = india_date(now)
    start, end = period(from_, to, today)
    return await management_schools.dashboard(db, user, start, end, now, today)


@router.patch("/schools/{school_id}", response_model=ManagementSchoolValuesOut)
async def set_school_values(school_id: UUID, payload: ManagementSchoolValuesIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """SD13: a school's contract / renewal value. Finance tier only (partner, accountant); super_admin gets "Finance access required"."""
    ledger.require_finance(user)
    return await management_schools.set_values(db, user, school_id, payload.model_dump(exclude_unset=True))


# --- mgmt-016: Student funnel (spec SF1-SF16). Operational tier (M13); counts only -------------------------------------------------------
@router.get("/funnel", response_model=StudentFunnelOut)
async def student_funnel(
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    by: Literal["country", "course", "agent", "school", "counselor", "source", "bdm", "intake", "branch"] | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """§11 for `from`..`to` (IST, default this month; SF1): the lead journey, then the IT and abroad paths, optionally broken down `by` one
    dimension (SF16). The accountant and everyone else 403."""
    _operational(user)
    now = await db_now(db)
    start, end = period(from_, to, india_date(now))
    return await management_funnel.dashboard(db, start, end, now, by)


# --- mgmt-023: University partnership dashboard (spec UD1-UD14). Operational tier (M13); revenue for the partners only (UD10) ----------
@router.get("/universities", response_model=ManagementUniversitiesOut, response_model_exclude_unset=True)
async def universities_dashboard(from_: date | None = Query(None, alias="from"), to: date | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§19 now, with Applications, Enrollments and Revenue for `from`..`to` (IST, default this month to date, as upc-029; UD3). The
    accountant and everyone else 403."""
    _operational(user)
    today = india_date(await db_now(db))
    first, last = partnership_period(from_ or today.replace(day=1), to or today)
    return await management_universities.dashboard(db, user, first, last, today)


# --- mgmt-030: Business health score (spec BH1-BH14). Operational tier (M13); the finance factors for partners only -----------------
@router.get("/health", response_model=ManagementHealthOut)
async def business_health(month: str | None = Query(None, pattern=MONTH), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§30 for `month` (YYYY-MM, default the last complete IST month; BH2) against the month before. Partners get all twelve factors,
    super_admin the six operational ones scored on their own (BH1); the accountant and everyone else 403."""
    _operational(user)
    this_month = india_date(await db_now(db)).replace(day=1)
    chosen = await _past_month(db, month) if month else (this_month - timedelta(days=1)).replace(day=1)
    return await management_health.health(db, user, chosen, this_month)

# --- mgmt-033: drill-down navigation (spec DD1-DD14). Finance tier only: every chain is money (AC3, M13) -------------------------------
@router.get("/drill/{chain}", response_model=DrillOut)
async def drill_down(
    chain: str,
    month: str | None = Query(None, pattern=MONTH),
    period: Literal["month", "year"] = "month",
    path: str | None = Query(None, max_length=400),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100_000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """One level of a revenue chain (abroad, it, recruitment) below the chosen `path` (comma-separated keys, `none` = unattributed) for
    `month` or its financial year to date, or the record at the end. Reads of students and below are audited (DD11)."""
    ledger.require_finance(user)
    return await management_drill.drill(db, user, chain, await _past_month(db, month), period, path, limit=limit, offset=offset)


# --- mgmt-031: Partner home dashboard (spec HM1-HM14). Operational tier (M13); the money for partners only ------------------------
@router.get("/home", response_model=ManagementHomeOut, response_model_exclude_unset=True)
async def management_home_dashboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """§31: today's snapshot and the nine panels, each the figure of the page it links to. Partners get the money; super_admin gets
    no money key at all (HM2). The accountant and everyone else 403."""
    _operational(user)
    return await management_home.home(db, user, india_date(await db_now(db)))
