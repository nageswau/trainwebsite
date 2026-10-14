"""mgmt-022 (EVID-017 §18, spec SD1-SD16): the school dashboard -- the §18 figures and every school's row, for an IST period, plus the
school money of Q-23: ledger income tagged with a school (SD12) and the contract / renewal value kept on the school (SD13).

Nothing is counted here that another module does not already define: the BDM figures are mgmt-020's School BDM dashboard (SD3), the
student figures ENH-016's indicators (SD4-SD9), the teacher and parent membership ENH-008's rule (SD6) and the profile completion
ENH-012's formula (SD10). The finance tier alone gets money; the super admin's read never touches the ledger or the value columns (SD1).
Only counts, percentages, school names and rupees leave (SD16)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.portfolio import portfolio_completion
from app.api.school_analytics import _is_active, _renewal_due, portfolio_sections, statement_ids, student_indicators
from app.models import LedgerEntry, School, SchoolParentLink, SchoolStudent, User
from app.services import ledger, management_audit, management_bdm
from app.services.management_access import can_view_finance

STUDENT_FIGURES = (("career_guidance", "guidance"), ("psychometric_tests", "psych_completed"), ("academic_results", "published_results"))
BDM_FIGURES = (("schools_contacted", "school_leads"), ("meetings", "meetings"), ("proposals", "proposals"), ("mous", "mous"))  # SD3
VALUES = ("contract_value", "renewal_value")
NOT_FOUND = "School not found"
# §18 order: (key, the source's word, definition, basis).
FIGURES = (
    ("schools_contacted", "Schools contacted", "School organizations the School BDMs created in the period.", "period"),
    ("meetings", "Meetings", "Appointments the School BDMs completed in the period.", "period"),
    ("proposals", "Proposals", "MoUs the School BDMs moved to Proposal Sent in the period.", "period"),
    ("mous", "MoUs", "MoUs the School BDMs moved to Signed in the period.", "period"),
    ("active_schools", "Active schools", "Partner schools whose tier is set and not past its end date, today.", "now"),
    ("students", "Students", "Student records of every partner school, now.", "now"),
    ("teachers", "Teachers", "Teacher accounts of the partner schools, now.", "now"),
    ("parents", "Parents", "Parent accounts linked to a partner school's student, now; each parent counted once.", "now"),
    ("career_guidance", "Career guidance", "Students with a completed career guidance session.", "now"),
    ("psychometric_tests", "Psychometric tests", "Students with a completed psychometric test.", "now"),
    ("academic_results", "Academic results", "Students with at least one published academic result.", "now"),
    ("profile_completion", "Student profile completion", "Average portfolio completion of the students, in per cent.", "now"),
    ("revenue", "School revenue", "Approved School projects income dated in the period, in rupees.", "period"),
)


async def _accounts(db: AsyncSession, ids: set[UUID]) -> tuple[dict[UUID, set], dict[UUID, set]]:
    """SD6, ENH-008 in bulk: a teacher belongs to the school in `profile.school_id`; a parent to every school where a linked child
    studies, or (an account from before the links) to the one in `profile.school_id`."""
    teachers: dict[UUID, set] = {i: set() for i in ids}
    parents: dict[UUID, set] = {i: set() for i in ids}
    by_text = {str(i): i for i in ids}
    accounts = await db.execute(select(User.id, User.role, User.profile).where(User.role.in_(("school_teacher", "school_parent"))))
    for user_id, role, profile in accounts.all():
        school_id = by_text.get(str((profile or {}).get("school_id")))
        if school_id is not None:
            (teachers if role == "school_teacher" else parents)[school_id].add(user_id)
    links = select(SchoolParentLink.parent_user_id, SchoolStudent.school_id).join(SchoolStudent, SchoolStudent.id == SchoolParentLink.school_student_id)
    parent_ids = set((await db.scalars(select(User.id).where(User.role == "school_parent"))).all())
    for parent_id, school_id in (await db.execute(links.distinct())).all():
        if parent_id in parent_ids:
            parents[school_id].add(parent_id)
    return teachers, parents


async def _students(db: AsyncSession) -> tuple[dict[UUID, list[UUID]], dict[str, set[UUID]], dict[UUID, int]]:
    """SD5/SD7-SD10: every school's student ids, the ENH-016 indicators and each student's ENH-012 completion (as ENH-016's scorecards)."""
    roster = (await db.execute(select(SchoolStudent.id, SchoolStudent.school_id, SchoolStudent.date_of_birth, SchoolStudent.grade_or_class))).all()
    scope = select(SchoolStudent.id)
    indicators = await student_indicators(db, scope)
    sections = await portfolio_sections(db, scope)
    statements = await statement_ids(db, scope)
    by_school: dict[UUID, list[UUID]] = {}
    completion: dict[UUID, int] = {}
    for sid, school_id, born, grade in roster:
        by_school.setdefault(school_id, []).append(sid)
        completion[sid] = portfolio_completion(
            profile_complete=born is not None and grade is not None,
            has_academic=sid in indicators["published_results"],
            has_psychometric=sid in indicators["psych_started"],
            has_career=sid in indicators["career_any"],
            has_language=sid in indicators["language_started"],
            sections=sections.get(sid, set()),
            has_statement=sid in statements,
        )
    return by_school, indicators, completion


async def _revenue(db: AsyncSession, start: date, end: date) -> tuple[Decimal, dict[UUID, Decimal]]:
    """SD11: the counted School projects income in the period (mgmt-005 lines); SD12: its approved entries tagged with a school."""
    c = ledger.lines().c
    total = await db.scalar(select(func.coalesce(func.sum(c.signed_amount), 0)).where(c.counted, c.kind == "income", c.vertical == "school", c.entry_date >= start, c.entry_date <= end))
    signed = case((LedgerEntry.reversal_of_id.is_(None), LedgerEntry.amount), else_=-LedgerEntry.amount)
    tagged = select(LedgerEntry.school_id, func.sum(signed)).where(LedgerEntry.school_id.is_not(None), LedgerEntry.status == "approved", LedgerEntry.entry_date >= start, LedgerEntry.entry_date <= end)
    return Decimal(total), dict((await db.execute(tagged.group_by(LedgerEntry.school_id))).all())


def _rupees(value) -> Decimal:
    return Decimal(value or 0).quantize(ledger.CENTS)


def _average(values: list[int]) -> int | None:
    return round(sum(values) / len(values)) if values else None


async def dashboard(db: AsyncSession, user: User, start: date, end: date, now: datetime, today: date) -> dict:
    """Every school (SD15) for the inclusive IST dates `start`..`end`; the student-based totals are the sums of the rows."""
    money = can_view_finance(user)
    bdm = {f["key"]: f["value"] for f in (await management_bdm.dashboard(db, "school", start, end, now))["figures"]}
    schools = sorted((await db.scalars(select(School))).all(), key=lambda s: (s.name.casefold(), str(s.id)))
    ids = {s.id for s in schools}
    by_school, indicators, completion = await _students(db)
    teachers, parents = await _accounts(db, ids)
    revenue, tagged = await _revenue(db, start, end) if money else (Decimal(0), {})

    rows: list[dict[str, Any]] = []
    for s in schools:
        students = by_school.get(s.id, [])
        rows.append({
            "id": s.id, "name": s.name, "tier": s.tier, "active": _is_active(s, today), "renewal_due": _renewal_due(s, today), "tier_valid_until": s.tier_valid_until,
            "students": len(students), "teachers": len(teachers[s.id]), "parents": len(parents[s.id]),
            **{key: sum(1 for sid in students if sid in indicators[indicator]) for key, indicator in STUDENT_FIGURES},
            "profile_completion": _average([completion[sid] for sid in students]),
            "revenue": _rupees(tagged.get(s.id)) if money else None,
            **{key: getattr(s, key) if money else None for key in VALUES},
        })  # fmt: skip

    def money_sum(key: str) -> Decimal | None:
        return sum((r[key] for r in rows if r[key] is not None), Decimal(0)).quantize(ledger.CENTS) if money else None

    totals = {
        **{key: bdm[source] for key, source in BDM_FIGURES},
        "active_schools": sum(r["active"] for r in rows),
        **{key: sum(r[key] for r in rows) for key in ("students", *(k for k, _ in STUDENT_FIGURES))},
        "teachers": len(set().union(*teachers.values())),
        "parents": len(set().union(*parents.values())),
        "profile_completion": _average([completion[sid] for sids in by_school.values() for sid in sids]),
        "revenue": _rupees(revenue) if money else None,
        **{key: money_sum(key) for key in VALUES},
        "contracts_not_entered": sum(r["contract_value"] is None for r in rows) if money else None,
    }
    return {
        "from_": start,
        "to": end,
        "as_of": now,
        "money_visible": money,
        "figures": [{"key": key, "label": label, "definition": text, "basis": basis} for key, label, text, basis in FIGURES],
        "totals": totals,
        "untagged_revenue": _rupees(revenue - sum(tagged.values(), Decimal(0))) if money else None,
        "schools": rows,
    }


async def set_values(db: AsyncSession, user: User, school_id: UUID, changes: dict) -> dict:
    """SD13: the finance tier's change of a school's contract / renewal value. The row lock serialises two editors; one audit row with
    the before and after values (MA3) commits with the change. Nothing changed = nothing recorded."""
    school = await db.scalar(select(School).where(School.id == school_id).with_for_update())
    if school is None:
        raise HTTPException(404, NOT_FOUND)
    before = {key: getattr(school, key) for key in VALUES}
    changes = {key: None if value is None else value.quantize(ledger.CENTS) for key, value in changes.items()}
    changed = [key for key in VALUES if key in changes and changes[key] != before[key]]
    if changed:
        for key in changed:
            setattr(school, key, changes[key])
        management_audit.record(db, user, "mgmt.school_value", "update", str(school.id), fields=changed, values={k: (before[k], changes[k]) for k in changed})
        await db.commit()
        ledger.logger.info("school_values_changed", extra={"extra_fields": {"actor_id": str(user.id), "school_id": str(school.id), "changed": changed}})
    return {"id": school.id, **{key: getattr(school, key) for key in VALUES}}
