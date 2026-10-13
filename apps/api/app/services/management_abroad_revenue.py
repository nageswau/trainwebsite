"""mgmt-006 (spec MR1-MR12): the §4 Abroad Education revenue dashboard. Read-only; every rupee comes from `ledger.lines()` (vertical
`abroad`), so it reconciles with the ledger: revenue by kind, by country / university / intake / agency (+ an Unattributed row each),
the Abroad expenses and the gross contribution, for the selected month and the Indian financial year to date. University commission is
left out entirely for anyone but a partner (M3, MR7). Spec: docs/superpowers/specs/2026-10-13-mgmt-006-abroad-revenue-design.md."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrg, AgentOrgMember, AgentStudent, Country, OverseasApplication, Payment, University, UniversityCommissionReceipt, User
from app.services import ledger
from app.services.management_access import can_view_university_commission
from app.services.management_expenses import financial_year_start, month_key, next_month

# MR3 (Q-09): the four kinds that partition Abroad revenue, in source order.
KINDS = (
    ("service_fees", "Student service fees"),
    ("other_payments", "Application-related & other student payments"),
    ("university_commission", "University commission"),
    ("manual", "Recorded in the ledger"),
)
BREAKDOWNS = (("country", "Country-wise"), ("university", "University-wise"), ("intake", "Intake-wise"), ("agency", "Agency-wise"))
COMMISSION = "university_commission"
DIRECT = "Direct (no agency)"  # MR5: a linked application that no agency owns
AGENCY_NOT_RECORDED = "Agency not recorded"  # an agent user with no organisation (legacy rows)


def _figure() -> dict[str, Decimal]:
    return {"month": Decimal(0), "year": Decimal(0)}


def _out(figure: dict[str, Decimal]) -> dict[str, Decimal]:
    return {period: amount.quantize(ledger.CENTS) for period, amount in figure.items()}


def _add(figure: dict[str, Decimal], amount: Decimal, in_month: bool) -> None:
    figure["year"] += amount
    if in_month:
        figure["month"] += amount


async def dashboard(db: AsyncSession, user: User, month_start: date) -> dict:
    year_start, end = financial_year_start(month_start), next_month(month_start)
    commission_visible = can_view_university_commission(user)
    table = ledger.lines()
    c = table.c
    in_period = [c.entry_date >= year_start, c.entry_date < end]
    if not commission_visible:
        in_period.append(c.source != COMMISSION)  # MR7: never fetched, so no figure can carry it
    in_month = (c.entry_date >= month_start).label("in_month")

    # MR5: a payment is attributed through the application its reference_id names; a receipt through its university.
    agent_user_id = func.coalesce(OverseasApplication.agent_id, AgentStudent.agent_id)
    kind = case((c.source == COMMISSION, COMMISSION), (c.source == "manual", "manual"), (Payment.reference_type == "service_fee", "service_fees"), else_="other_payments").label("kind")
    agency = case((OverseasApplication.id.is_(None), None), (agent_user_id.is_(None), DIRECT), (AgentOrg.name.is_(None), AGENCY_NOT_RECORDED), else_=AgentOrg.name).label("agency")
    intake = func.nullif(func.trim(OverseasApplication.intake), "").label("intake")
    grouped = (
        select(kind, in_month, Country.name.label("country"), University.name.label("university"), intake, agency, func.sum(c.signed_amount))
        .select_from(table)
        .outerjoin(Payment, and_(c.source == "payment", Payment.id == c.id))
        .outerjoin(OverseasApplication, OverseasApplication.id == Payment.reference_id)
        .outerjoin(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)
        .outerjoin(AgentOrgMember, AgentOrgMember.user_id == agent_user_id)
        .outerjoin(AgentOrg, AgentOrg.id == AgentOrgMember.org_id)
        .outerjoin(UniversityCommissionReceipt, and_(c.source == COMMISSION, UniversityCommissionReceipt.id == c.id))
        .outerjoin(University, University.id == func.coalesce(OverseasApplication.university_id, UniversityCommissionReceipt.university_id))
        .outerjoin(Country, Country.id == University.country_id)
        .where(*in_period, c.vertical == "abroad", c.kind == "income", c.counted)
        .group_by(kind, in_month, Country.name, University.name, intake, agency)
    )
    kinds = {key: _figure() for key, _ in KINDS}
    revenue, agent_generated = _figure(), _figure()
    breakdowns: dict[str, dict] = {key: defaultdict(_figure) for key, _ in BREAKDOWNS}
    unattributed = {key: _figure() for key, _ in BREAKDOWNS}
    for kind_key, month_flag, country, university, intake_label, agency_label, amount in (await db.execute(grouped)).all():
        _add(kinds[kind_key], amount, month_flag)
        _add(revenue, amount, month_flag)
        if agency_label not in (None, DIRECT):
            _add(agent_generated, amount, month_flag)  # MR4: a subset of revenue, never added to it
        for key, label in (("country", country), ("university", university), ("intake", intake_label), ("agency", agency_label)):
            _add(breakdowns[key][label] if label else unattributed[key], amount, month_flag)

    expenses: dict[str, dict] = defaultdict(_figure)
    expense_total, shared = _figure(), _figure()
    spent = select(c.vertical, c.category_label, in_month, func.sum(c.signed_amount)).where(*in_period, c.vertical.in_(("abroad", "shared")), c.kind == "expense", c.counted)
    for vertical, label, month_flag, amount in (await db.execute(spent.group_by(c.vertical, c.category_label, in_month))).all():
        if vertical == "shared":
            _add(shared, amount, month_flag)  # MR6: shown as a note, never allocated here (Q-04 belongs to mgmt-009)
        else:
            _add(expenses[label], amount, month_flag)
            _add(expense_total, amount, month_flag)

    other = await db.execute(
        select(c.currency, c.kind, func.sum(c.amount), func.count())
        .where(*in_period, c.vertical == "abroad", c.source != "manual", c.counted.is_(False))
        .group_by(c.currency, c.kind)
        .order_by(c.currency, c.kind)
    )

    def rows(figures: dict) -> list[dict]:
        """Largest annual first; a row netted to zero in both periods (a reversal) says nothing (mgmt-010 QA-01)."""
        ordered = sorted(figures.items(), key=lambda item: (-item[1]["year"], item[0].lower()))
        return [{"label": label, **_out(figure)} for label, figure in ordered if figure["month"] or figure["year"]]

    return {
        "month": month_key(month_start),
        "year_start": year_start,
        "year_label": f"{year_start.year}-{(year_start.year + 1) % 100:02d}",
        "commission_visible": commission_visible,
        "kinds": [{"key": key, "label": label, **_out(kinds[key])} for key, label in KINDS if commission_visible or key != COMMISSION],
        "revenue": _out(revenue),
        "agent_generated": _out(agent_generated),
        "breakdowns": [{"key": key, "label": label, "rows": rows(breakdowns[key]), "unattributed": _out(unattributed[key])} for key, label in BREAKDOWNS],
        "expenses": rows(expenses),
        "expense_total": _out(expense_total),
        "shared_expenses": _out(shared),
        "contribution": _out({period: revenue[period] - expense_total[period] for period in ("month", "year")}),
        "not_counted": [{"currency": cur, "kind": k, "amount": Decimal(amount).quantize(ledger.CENTS), "count": count} for cur, k, amount, count in other.all()],
    }
