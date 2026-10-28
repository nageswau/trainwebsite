"""ccrm-036 (DEC-SCOPE-269, P1-P9; source PDF §1 "measure counselor performance", §4 conversion by counselor): the overseas counselor's
own performance report. The period figures are mgmt-018's, computed by `management_counseling`'s own builders for this counselor (P3, no
revenue), then their lead follow-up completion and tasks; the "now" figures and the stage / sub-status table are their whole caseload by
ccrm-034's predicates (P7, P8). Read-only and not audited (P9); only counts, percentages and stage names leave.
Spec: docs/superpowers/specs/2026-10-25-ccrm-036-counselor-performance-design.md.

ccrm-053 (DEC-SCOPE-325, PF1-PF10): the counselor's leads split by division (Overseas / IT), the intake filter (lead figures by the lead's
qualification intake, application figures by the application's) and the lead-division filter; and `team`, every overseas counselor's
figures for the Overseas Admin -- one grouped query per figure family, never a loop per counselor (PF9).
Spec: docs/superpowers/specs/2026-10-28-ccrm-053-counselor-performance-admin-design.md."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application_sub_status import label as sub_status_label
from app.models import CounselorTask, Enquiry, LeadFollowUp, LeadQualification, StudentDocument, User, VisaCase
from app.services import counselor_tasks, lead_follow_ups, lead_handover, management_counseling
from app.services import management_crm_reports as crm
from app.services.agent_applications import stage_label
from app.services.bdm_activities import india_date
from app.services.bdm_performance import _instants

A = crm.A
CRM_TEXT = {(report, key): text for report, rows in crm.DEFINITIONS.items() for key, _, text in rows}
PERCENT = {"conversion_pct", "follow_up_completion_pct"}
LEAD_DIVISIONS = ("overseas", "it")  # PF1: the split; Leads is their sum
# PF1: (key, label, definition). The intake and lead-division filters narrow these three.
LEAD_FIGURES = (
    ("leads", "Leads", "Leads the counselor owns that were created in the period: Overseas plus IT. The intake and lead-division filters apply."),
    ("leads_overseas", "Overseas leads", "Of those leads, the ones in the Overseas division."),
    ("leads_it", "IT leads", "Of those leads, the ones in the IT division."),
)
# P3-P5, in the page's order: (key, label, definition). The mgmt-018 figures keep its labels and definitions.
PERIOD_FIGURES = (
    *LEAD_FIGURES,
    *((key, label, text) for key, label, text, _ in management_counseling.FIGURES if key != "revenue"),
    ("follow_ups_due", "Lead follow-ups due", "Follow-ups on your leads due in the period; cancelled ones are left out."),
    ("follow_ups_completed", "Lead follow-ups completed", "Of the follow-ups due in the period, the ones marked done."),
    ("follow_up_completion_pct", "Follow-up completion %", "Lead follow-ups completed as a share of those due."),
    ("tasks_completed", "Tasks completed", "Your tasks marked done in the period."),
)
# P5-P7: the figures as they stand now.
NOW_FIGURES = (
    ("overdue_tasks", "Overdue tasks", "Your open tasks due before today (India time)."),
    ("overdue_follow_ups", "Overdue follow-ups", "Open follow-ups on your leads that are past due."),
    ("applications", "Applications", "Every application assigned to you, at any stage. The intake filter applies to the application figures."),
    ("students", "Students", crm.STUDENTS_DEF[2]),
    ("offers", "Offers", CRM_TEXT[("universities", "offers")]),
    ("visas_pending", "Visas pending", CRM_TEXT[("visa", "pending")]),
    ("visas_approved", "Visas approved", CRM_TEXT[("visa", "approved")]),
    ("visas_refused", "Visas refused", CRM_TEXT[("visa", "refused")]),
    ("enrollments", "Enrolments", CRM_TEXT[("universities", "enrollments")]),
    ("documents_pending", "Documents pending verification", "Current documents on your applications waiting to be verified."),
)
TABLE_DEFINITIONS = (
    ("applications", "Applications", "Every application assigned to you, by its stage and sub-status. Closed applications are listed too."),
    crm.STUDENTS_DEF,
)


def _visa(*statuses: str):
    return exists().where(VisaCase.application_id == A.id, VisaCase.visa_status.in_(statuses))


def _figures(rows: tuple, values: dict) -> list[dict]:
    return [{"key": k, "label": label, "definition": text, "unit": "percent" if k in PERCENT else "count", "value": values[k]} for k, label, text in rows]


async def _follow_ups(db: AsyncSession, user: User, lo: datetime, hi: datetime, now: datetime) -> dict:
    """P4 / P6: follow-ups on the leads handed to this counselor (owner and division)."""
    fu = LeadFollowUp
    due = and_(fu.due_at >= lo, fu.due_at < hi, fu.status != "cancelled")
    stmt = select(func.count().filter(due), func.count().filter(due, fu.status == "done"), func.count().filter(lead_follow_ups.overdue(now)))
    row = (await db.execute(stmt.where(fu.lead_id.in_(select(Enquiry.id).where(*lead_handover.counselor_scope(user)))))).one()
    return {"follow_ups_due": row[0], "follow_ups_completed": row[1], "follow_up_completion_pct": crm._rate(row[1], row[0]), "overdue_follow_ups": row[2]}


async def _tasks(db: AsyncSession, user: User, lo: datetime, hi: datetime, today: date) -> dict:
    """P5: ccrm-029's Overdue band now; tasks done in the period."""
    t = CounselorTask
    completed = and_(t.status == "done", t.completed_at >= lo, t.completed_at < hi)
    stmt = select(func.count().filter(counselor_tasks.band_filter("overdue", today)), func.count().filter(completed)).where(t.counselor_user_id == user.id)
    overdue, done = (await db.execute(stmt)).one()
    return {"overdue_tasks": overdue, "tasks_completed": done}


# P7: the outcome counts over a set of applications -- one counselor's (by stage) or every counselor's (by counselor, ccrm-053).
MEASURES = {
    "applications": func.count(), "students": crm.STUDENTS, "offers": func.count().filter(crm.OFFER),
    "visas_pending": func.count().filter(_visa(*crm.VISA_PENDING)), "visas_approved": func.count().filter(_visa("approved")),
    "visas_refused": func.count().filter(_visa("refused")), "enrollments": func.count().filter(crm.CONFIRMED),
}  # fmt: skip


async def _leads(db: AsyncSession, ids: list[UUID], lo: datetime, hi: datetime, intake: str | None, division: str | None) -> dict[UUID, tuple]:
    """PF1-PF3: per owner, the leads created in the period -- all, Overseas, IT -- narrowed by the qualification intake and the division."""
    e = Enquiry
    split = (func.count().filter(e.division == d) for d in LEAD_DIVISIONS)
    divisions = [division] if division else list(LEAD_DIVISIONS)
    stmt = select(e.owner_id, func.count(), *split).where(e.owner_id.in_(ids), e.division.in_(divisions), e.created_at >= lo, e.created_at < hi)
    if intake:
        stmt = stmt.join(LeadQualification, LeadQualification.lead_id == e.id).where(LeadQualification.intake == intake)
    return management_counseling._grouped(await db.execute(stmt.group_by(e.owner_id)))


def _lead_values(counts: dict[UUID, tuple], counselor_id: UUID) -> dict:
    return dict(zip((k for k, _, _ in LEAD_FIGURES), counts.get(counselor_id, (0, 0, 0)), strict=True))


async def _caseload(db: AsyncSession, user: User, intake: str | None) -> tuple[list[dict], dict]:
    """P7 / P8: every application of this counselor (PF2: of the intake), by stage and sub-status, and the total row with the outcome counts."""
    f = crm.ReportFilters(counselor=user.id, intake=intake)
    rows, total = await crm._report(db, f, [A.status.label("stage"), A.sub_status.label("sub_status")], MEASURES)
    rows.sort(key=lambda r: (crm._stage_order(r["stage"]), r["stage"], crm._sub_order(r["stage"], r["sub_status"])))
    table = [
        {"stage": r["stage"], "stage_label": stage_label(r["stage"]), "sub_status": r["sub_status"],
         "sub_status_label": sub_status_label(r["sub_status"]) or crm.NOT_SET, "applications": r["applications"], "students": r["students"]}
        for r in rows
    ]  # fmt: skip
    pending = select(func.count()).select_from(StudentDocument).join(A, A.id == StudentDocument.application_id)
    pending = pending.where(A.counselor_id == user.id, StudentDocument.archived_at.is_(None), StudentDocument.verification_status == "pending")
    total["documents_pending"] = await db.scalar(pending.where(A.intake == intake) if intake else pending)
    return table, total


async def report(db: AsyncSession, user: User, start: date, end: date, now: datetime, intake: str | None = None, division: str | None = None) -> dict:
    """The counselor's report for the inclusive IST dates `start`..`end`; `now` is the database clock. `intake` / `division`: PF2 / PF3."""
    lo, hi = _instants(start, end)
    leads = _lead_values(await _leads(db, [user.id], lo, hi, intake, division), user.id)
    period = await management_counseling.counselor_figures(db, user.id, start, end)
    follow_ups = await _follow_ups(db, user, lo, hi, now)
    tasks = await _tasks(db, user, lo, hi, india_date(now))
    table, total = await _caseload(db, user, intake)
    values = {**leads, **period, **follow_ups, **tasks, **total}
    return {
        "from_": start,
        "to": end,
        "as_of": now,
        "intake": intake,
        "division": division,
        "period": _figures(PERIOD_FIGURES, values),
        "now": _figures(NOW_FIGURES, values),
        "applications": {
            "rows": table,
            "total": {"applications": total["applications"], "students": total["students"]},
            "definitions": [{"key": k, "label": label, "definition": text} for k, label, text in TABLE_DEFINITIONS],
        },
    }


# --- ccrm-053: the Overseas Admin's list -------------------------------------------------------------------------------------------
_TEXT = {k: (label, text) for k, label, text in (*PERIOD_FIGURES, *NOW_FIGURES)}
# Browser QA-01: the admin reads about each counselor, never "you".
_TEXT["applications"] = ("Applications", "Every application assigned to the counselor, at any stage. The intake filter applies to the application figures.")
TEAM_KEYS = (
    "leads", "leads_overseas", "leads_it", "leads_assigned", "calls", "counseling_sessions", "conversions", "conversion_pct",
    "students", "applications", "visas_pending", "visas_approved", "visas_refused", "enrollments",
)  # fmt: skip
TEAM_COLUMNS = (
    {"key": "full_name", "label": "Counselor", "definition": "Every active overseas counselor; an inactive one only when they have a figure."},
    *({"key": k, "label": _TEXT[k][0], "definition": _TEXT[k][1]} for k in TEAM_KEYS),
)
TEAM_COUNTS = tuple(k for k in TEAM_KEYS if k != "conversion_pct")
CASELOAD_KEYS = ("students", "applications", "visas_pending", "visas_approved", "visas_refused", "enrollments")


async def overseas_counselor(db: AsyncSession, counselor_id: UUID) -> User | None:
    """PF6: the detail's subject -- an overseas counselor, active or not; anyone else reads as missing."""
    return await db.scalar(select(User).where(User.id == counselor_id, User.role == "counselor", User.division == "overseas"))


async def team(db: AsyncSession, start: date, end: date, now: datetime, intake: str | None = None, division: str | None = None) -> dict:
    """PF7-PF9: one row per overseas counselor and a Total row (counts summed, students distinct, conversion % from the summed parts)."""
    people = (await db.execute(select(User.id, User.full_name, User.active).where(User.role == "counselor", User.division == "overseas"))).all()
    ids = [p.id for p in people]
    lo, hi = _instants(start, end)
    counts = await management_counseling._counts(db, ids, lo, hi)
    leads = await _leads(db, ids, lo, hi, intake, division)
    rows, caseload_total = await crm._report(db, crm.ReportFilters(intake=intake), [A.counselor_id.label("counselor_id")], MEASURES, A.counselor_id.in_(ids))
    caseload = {r["counselor_id"]: r for r in rows}

    items, converted = [], 0
    for p in sorted(people, key=lambda p: (p.full_name.lower(), str(p.id))):
        figures = management_counseling._figures(p.id, *counts)
        apps = caseload.get(p.id, {})
        row = {"id": p.id, "full_name": p.full_name, "active": p.active, **_lead_values(leads, p.id),
               **{k: figures[k] for k in TEAM_KEYS if k in figures}, **{k: apps.get(k, 0) for k in CASELOAD_KEYS}}  # fmt: skip
        if p.active or any(row[k] for k in TEAM_COUNTS):
            items.append(row)
            converted += figures["_converted"]
    totals = {"full_name": "Total", **{k: sum(r[k] for r in items) for k in TEAM_COUNTS}}
    totals["students"] = caseload_total["students"]
    totals["conversion_pct"] = management_counseling._pct(converted, totals["leads_assigned"])
    return {"from_": start, "to": end, "as_of": now, "intake": intake, "division": division, "columns": list(TEAM_COLUMNS), "items": items, "totals": totals}
