"""mgmt-018 (EVID-017 §13, spec CS1-CS12): the counseling dashboard -- Leads -> Counseling -> Conversion, per counselor and in total, for
an IST period. One grouped query per figure over every counselor, so the cost does not grow with the team. Conversions are the telecaller
T5 conversions (`telecaller_metrics.first_conversions`) credited to the lead's counselor; revenue is the management ledger's payment lines
and only the finance tier gets it (the super admin's read never touches the ledger). Read-only; only names, counts and rupees leave."""

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Uuid, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Appointment, AuditLog, Enquiry, Payment, User
from app.services import ledger
from app.services.bdm_performance import _instants
from app.services.management_access import can_view_finance
from app.services.telecaller_metrics import first_conversions

DIVISIONS = {"it": "IT", "overseas": "Overseas"}  # CS10: always shown, in this order; any other division follows
COUNTS = ("leads_assigned", "counseling_sessions", "follow_ups", "conversions")
# CS3-CS9, in §13 order: (key, label, definition, tracked).
FIGURES = (
    ("leads_assigned", "Leads assigned", "Leads handed over to the counselor in the period.", True),
    ("calls", "Calls", "Not tracked: calls are logged by telecallers, not counselors.", False),
    ("counseling_sessions", "Counseling sessions", "Appointments the counselor completed that were scheduled in the period.", True),
    ("follow_ups", "Follow-ups", "Counseling sessions with a lead or student the counselor had counseled before.", True),
    ("conversions", "Conversions", "The counselor's leads first converted in the period and still converted.", True),
    ("revenue", "Revenue", "Rupee payments in the period from the students of the counselor's converted leads.", True),
    ("conversion_pct", "Conversion %", "Of the leads handed over in the period, the share converted now.", True),
)


def _grouped(rows: Iterable) -> dict[UUID, tuple]:
    return {owner: tuple(values) for owner, *values in rows}


async def _handovers(db: AsyncSession, ids: list[UUID], lo: datetime, hi: datetime) -> dict[UUID, tuple]:
    """CS3 / CS9: per counselor, the distinct leads handed to them in the period and how many of those are converted with them now."""
    counselor = cast(AuditLog.metadata_json["counselor_id"].as_string(), Uuid)
    handed = (
        select(counselor.label("counselor"), cast(AuditLog.entity_id, Uuid).label("lead_id"))
        .where(AuditLog.action == "lead.handover", AuditLog.entity_type == "enquiry", AuditLog.created_at >= lo, AuditLog.created_at < hi)
        .distinct()
        .subquery()
    )
    converted = func.count().filter(Enquiry.status == "converted", Enquiry.owner_id == handed.c.counselor)
    stmt = select(handed.c.counselor, func.count(), converted).join(Enquiry, Enquiry.id == handed.c.lead_id).where(handed.c.counselor.in_(ids))
    return _grouped(await db.execute(stmt.group_by(handed.c.counselor)))


async def _sessions(db: AsyncSession, ids: list[UUID], lo: datetime, hi: datetime) -> dict[UUID, tuple]:
    """CS5 / CS6: completed appointments scheduled in the period, and those the counselor had completed one before with the same subject."""
    earlier = aliased(Appointment)
    repeat = (
        select(earlier.id)
        .where(earlier.staff_id == Appointment.staff_id, earlier.status == "completed", earlier.scheduled_at < Appointment.scheduled_at,
               or_(earlier.lead_id == Appointment.lead_id, earlier.student_id == Appointment.student_id))
        .exists()
    )  # fmt: skip
    stmt = select(Appointment.staff_id, func.count(), func.count().filter(repeat)).where(
        Appointment.staff_id.in_(ids), Appointment.status == "completed", Appointment.scheduled_at >= lo, Appointment.scheduled_at < hi
    )
    return _grouped(await db.execute(stmt.group_by(Appointment.staff_id)))


async def _conversions(db: AsyncSession, ids: list[UUID], lo: datetime, hi: datetime) -> dict[UUID, tuple]:
    """CS7 (AC): tel-021's D13 rule -- still converted, first converted in the period -- credited to the lead's counselor."""
    first = first_conversions()
    stmt = select(Enquiry.owner_id, func.count()).join(first, first.c.lead_id == Enquiry.id).where(Enquiry.status == "converted", Enquiry.owner_id.in_(ids), first.c.at >= lo, first.c.at < hi)
    return _grouped(await db.execute(stmt.group_by(Enquiry.owner_id)))


async def _revenue(db: AsyncSession, ids: list[UUID], start: date, end: date) -> dict[UUID, tuple]:
    """CS8: the counted payment lines of the ledger (mgmt-005) dated in the period, paid by a student linked to a converted lead."""
    lines = ledger.lines()
    c = lines.c
    stmt = (
        select(Enquiry.owner_id, func.sum(c.signed_amount))
        .select_from(lines)
        .join(Payment, Payment.id == c.id)
        .join(Enquiry, Enquiry.converted_user_id == Payment.user_id)
        .where(c.source == "payment", c.counted, c.entry_date >= start, c.entry_date <= end, Enquiry.status == "converted", Enquiry.owner_id.in_(ids))
    )
    return _grouped(await db.execute(stmt.group_by(Enquiry.owner_id)))


def _pct(converted: int, assigned: int) -> float | None:
    return round(100 * converted / assigned, 1) if assigned else None


def _figures(rows: list[dict], money: bool) -> dict:
    """A group's figures: the sum of its rows (CS1), its conversion % from the summed parts (CS9)."""
    out: dict = {key: sum(r[key] for r in rows) for key in COUNTS}
    out["calls"] = None
    out["revenue"] = sum((r["revenue"] for r in rows), Decimal(0)).quantize(ledger.CENTS) if money else None
    out["conversion_pct"] = _pct(sum(r["_converted"] for r in rows), out["leads_assigned"])
    return out


async def dashboard(db: AsyncSession, user: User, start: date, end: date, now: datetime) -> dict:
    """Every counselor, active or not (CS1), for the inclusive IST dates `start`..`end`."""
    money = can_view_finance(user)
    people = (await db.execute(select(User.id, User.full_name, User.division, User.active).where(User.role == "counselor"))).all()
    ids = [p.id for p in people]
    lo, hi = _instants(start, end)
    handovers, sessions, conversions = (await _handovers(db, ids, lo, hi), await _sessions(db, ids, lo, hi), await _conversions(db, ids, lo, hi))
    revenue = await _revenue(db, ids, start, end) if money else {}

    order = {division: i for i, division in enumerate(DIVISIONS)}
    rows = []
    for p in sorted(people, key=lambda p: (order.get(p.division, len(order)), p.division, p.full_name.lower(), str(p.id))):
        assigned, converted = handovers.get(p.id, (0, 0))
        held, repeats = sessions.get(p.id, (0, 0))
        rows.append({
            "id": p.id, "full_name": p.full_name, "division": p.division, "active": p.active,
            "leads_assigned": assigned, "calls": None, "counseling_sessions": held, "follow_ups": repeats,
            "conversions": conversions.get(p.id, (0,))[0],
            "revenue": Decimal(revenue.get(p.id, (0,))[0] or 0).quantize(ledger.CENTS) if money else None,
            "conversion_pct": _pct(converted, assigned), "_converted": converted,
        })  # fmt: skip

    divisions = list(DIVISIONS) + sorted({r["division"] for r in rows} - set(DIVISIONS))
    return {
        "from_": start,
        "to": end,
        "as_of": now,
        "revenue_visible": money,
        "figures": [{"key": key, "label": label, "definition": text, "tracked": tracked} for key, label, text, tracked in FIGURES],
        "total": {"division": None, "label": "All counselors", "counselor_count": len(rows), **_figures(rows, money)},
        "divisions": [
            {"division": d, "label": DIVISIONS.get(d, d.capitalize()), "counselor_count": len(group), **_figures(group, money)}
            for d in divisions
            for group in [[r for r in rows if r["division"] == d]]
        ],
        "counselors": rows,
    }
