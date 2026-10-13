"""mgmt-021 (EVID-017 §17, spec AN1-AN14): the agent network dashboard -- the twelve §17 figures and every approved agency ranked along
Agent → Staff → Student → Application → Enrollment → Revenue, for an IST period. One grouped statement per figure family over every
agency, so the cost does not grow with the network.

Applications, offers, visa and enrollments are mgmt-024's funnel predicates over the agency's applications created in the period, so an
agency row equals the Applications funnel filtered by that agency (AN6). Commission and revenue are the management ledger's counted lines
(mgmt-005), revenue attributed to the agency as mgmt-006 does (AN7, AN8), and only the finance tier gets them: the super admin's read never
touches the ledger (AN9). Read-only; agency names, prefixes, counts and rupees leave, never a member or student (AGN-022 is untouched)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentCommission, AgentOrg, AgentOrgMember, AgentStudent, OverseasApplication, Payment, User
from app.services import ledger
from app.services.bdm_performance import _instants
from app.services.management_access import can_view_finance
from app.services.management_metrics import FUNNEL_COUNTS

ACTIVE, SUSPENDED = "active", "suspended"  # AN1/AN2: approved agencies; pending and rejected applications are not agents
COUNTS = ("staff", "students", "applications", "offers", "visa", "enrollments")
MONEY = ("commission", "revenue")
FUNNEL = (("applications", "created"), ("offers", "offer"), ("visa", "visa"), ("enrollments", "enrollment"))  # (key, mgmt-024 stage)
# §17 order: (key, the source's word, definition).
FIGURES = (
    ("agents", "Total agents", "Approved agencies: active or suspended."),
    ("new_agents", "New agents", "Approved agencies registered in the period."),
    ("active_agents", "Active agents", "Agencies whose account is active."),
    ("inactive_agents", "Inactive agents", "Agencies whose account is suspended."),
    ("staff", "Agent staff", "Active staff members of the agencies, right now."),
    ("students", "Students", "Student records the agencies added in the period."),
    ("applications", "Applications", "Applications the agencies created in the period, as on the Applications funnel."),
    ("offers", "Offers", "Of those applications, the ones with an offer."),
    ("visa", "Visa", "Of those applications, the ones with a visa case."),
    ("enrollments", "Enrollments", "Of those applications, the ones enrolled."),
    ("commission", "Commission", "Agent commission paid in the period, in rupees (a cost)."),
    ("revenue", "Revenue", "Rupee payments in the period from the agencies' students' applications."),
)
CHAIN = (("agents", "Agent"), ("staff", "Staff"), ("students", "Student"), ("applications", "Application"), ("enrollments", "Enrollment"), ("revenue", "Revenue"))


def _grouped(rows) -> dict[UUID, tuple]:
    return {org_id: tuple(values) for org_id, *values in rows}


async def _counts(db: AsyncSession, ids: list[UUID], lo: datetime, hi: datetime) -> tuple[dict, dict, dict]:
    """AN4-AN6: per agency, its active staff now, the student records added in the period and the funnel over its applications created
    in the period. Students and applications belong to an agency through the `agent_id` of one of its members (AGN-001)."""
    org = AgentOrgMember.org_id
    staff = select(org, func.count()).where(org.in_(ids), AgentOrgMember.role == "staff", AgentOrgMember.status == "active").group_by(org)
    students = (
        select(org, func.count()).join(AgentStudent, AgentStudent.agent_id == AgentOrgMember.user_id).where(org.in_(ids), AgentStudent.created_at >= lo, AgentStudent.created_at < hi).group_by(org)
    )
    stages = [func.count() if (rule := FUNNEL_COUNTS[stage]) is None else func.count().filter(rule) for _, stage in FUNNEL]
    funnel = (
        select(org, *stages)
        .join(OverseasApplication, OverseasApplication.agent_id == AgentOrgMember.user_id)
        .where(org.in_(ids), OverseasApplication.created_at >= lo, OverseasApplication.created_at < hi)
        .group_by(org)
    )
    return _grouped(await db.execute(staff)), _grouped(await db.execute(students)), _grouped(await db.execute(funnel))


async def _money(db: AsyncSession, ids: list[UUID], start: date, end: date) -> tuple[dict, dict]:
    """AN7 / AN8: the counted ledger lines dated in the period -- paid commissions by the agent's agency, and Abroad payments by the
    agency of the application they pay for (mgmt-006 MR5: the application's agent, else its agency record's)."""
    lines = ledger.lines()
    c = lines.c
    dated = [c.counted, c.entry_date >= start, c.entry_date <= end, AgentOrgMember.org_id.in_(ids)]
    commission = (
        select(AgentOrgMember.org_id, func.sum(c.signed_amount))
        .select_from(lines)
        .join(AgentCommission, AgentCommission.id == c.id)
        .join(AgentOrgMember, AgentOrgMember.user_id == AgentCommission.agent_id)
        .where(c.source == "agent_commission", *dated)
        .group_by(AgentOrgMember.org_id)
    )
    agent_user_id = func.coalesce(OverseasApplication.agent_id, AgentStudent.agent_id)
    revenue = (
        select(AgentOrgMember.org_id, func.sum(c.signed_amount))
        .select_from(lines)
        .join(Payment, Payment.id == c.id)
        .join(OverseasApplication, OverseasApplication.id == Payment.reference_id)
        .outerjoin(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)
        .join(AgentOrgMember, AgentOrgMember.user_id == agent_user_id)
        .where(c.source == "payment", c.vertical == "abroad", c.kind == "income", *dated)
        .group_by(AgentOrgMember.org_id)
    )
    return _grouped(await db.execute(commission)), _grouped(await db.execute(revenue))


def _rupees(found: dict, org_id: UUID) -> Decimal:
    return Decimal(found.get(org_id, (0,))[0] or 0).quantize(ledger.CENTS)


async def dashboard(db: AsyncSession, user: User, start: date, end: date, now: datetime) -> dict:
    """Every approved agency (AN1, AN11) for the inclusive IST dates `start`..`end`; the totals are the sum of the rows (AN12)."""
    money = can_view_finance(user)
    lo, hi = _instants(start, end)
    orgs = (await db.execute(select(AgentOrg.id, AgentOrg.name, AgentOrg.prefix, AgentOrg.status, AgentOrg.created_at).where(AgentOrg.status.in_((ACTIVE, SUSPENDED))))).all()
    ids = [o.id for o in orgs]
    staff, students, funnel = await _counts(db, ids, lo, hi)
    commission, revenue = await _money(db, ids, start, end) if money else ({}, {})

    rows = []
    for o in orgs:
        stages = funnel.get(o.id, (0,) * len(FUNNEL))
        rows.append({
            "id": o.id, "name": o.name, "prefix": o.prefix, "status": o.status, "new": lo <= o.created_at < hi,
            "staff": staff.get(o.id, (0,))[0], "students": students.get(o.id, (0,))[0],
            **{key: stages[i] for i, (key, _) in enumerate(FUNNEL)},
            "commission": _rupees(commission, o.id) if money else None, "revenue": _rupees(revenue, o.id) if money else None,
        })  # fmt: skip
    # AN10: one order for every role, so it never hints at money the reader may not see.
    rows.sort(key=lambda r: (-r["enrollments"], -r["applications"], -r["students"], r["name"].casefold(), str(r["id"])))

    totals = {
        "agents": len(rows),
        "new_agents": sum(r["new"] for r in rows),
        "active_agents": sum(r["status"] == ACTIVE for r in rows),
        "inactive_agents": sum(r["status"] == SUSPENDED for r in rows),
        **{key: sum(r[key] for r in rows) for key in COUNTS},
        **{key: sum((r[key] for r in rows), Decimal(0)).quantize(ledger.CENTS) if money else None for key in MONEY},
    }
    return {
        "from_": start,
        "to": end,
        "as_of": now,
        "money_visible": money,
        "figures": [{"key": key, "label": label, "definition": text} for key, label, text in FIGURES],
        "totals": totals,
        "chain": [{"key": key, "label": label, "value": totals[key]} for key, label in CHAIN if money or key not in MONEY],
        "agencies": rows,
    }
