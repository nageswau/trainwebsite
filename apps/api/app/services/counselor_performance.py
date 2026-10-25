"""ccrm-036 (DEC-SCOPE-269, P1-P9; source PDF §1 "measure counselor performance", §4 conversion by counselor): the overseas counselor's
own performance report. The period figures are mgmt-018's, computed by `management_counseling`'s own builders for this counselor (P3, no
revenue), then their lead follow-up completion and tasks; the "now" figures and the stage / sub-status table are their whole caseload by
ccrm-034's predicates (P7, P8). Read-only and not audited (P9); only counts, percentages and stage names leave.
Spec: docs/superpowers/specs/2026-10-25-ccrm-036-counselor-performance-design.md."""

from datetime import date, datetime

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application_sub_status import label as sub_status_label
from app.models import CounselorTask, Enquiry, LeadFollowUp, StudentDocument, User, VisaCase
from app.services import counselor_tasks, lead_follow_ups, lead_handover, management_counseling
from app.services import management_crm_reports as crm
from app.services.agent_applications import stage_label
from app.services.bdm_activities import india_date
from app.services.bdm_performance import _instants

A = crm.A
CRM_TEXT = {(report, key): text for report, rows in crm.DEFINITIONS.items() for key, _, text in rows}
PERCENT = {"conversion_pct", "follow_up_completion_pct"}
# P3-P5, in the page's order: (key, label, definition). The mgmt-018 figures keep its labels and definitions.
PERIOD_FIGURES = (
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
    ("applications", "Applications", "Every application assigned to you, at any stage."),
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


async def _caseload(db: AsyncSession, user: User) -> tuple[list[dict], dict]:
    """P7 / P8: every application of this counselor, grouped by stage and sub-status, and the total row with the outcome counts."""
    measures = {
        "applications": func.count(), "students": crm.STUDENTS, "offers": func.count().filter(crm.OFFER),
        "visas_pending": func.count().filter(_visa(*crm.VISA_PENDING)), "visas_approved": func.count().filter(_visa("approved")),
        "visas_refused": func.count().filter(_visa("refused")), "enrollments": func.count().filter(crm.CONFIRMED),
    }  # fmt: skip
    rows, total = await crm._report(db, crm.ReportFilters(counselor=user.id), [A.status.label("stage"), A.sub_status.label("sub_status")], measures)
    rows.sort(key=lambda r: (crm._stage_order(r["stage"]), r["stage"], crm._sub_order(r["stage"], r["sub_status"])))
    table = [
        {"stage": r["stage"], "stage_label": stage_label(r["stage"]), "sub_status": r["sub_status"],
         "sub_status_label": sub_status_label(r["sub_status"]) or crm.NOT_SET, "applications": r["applications"], "students": r["students"]}
        for r in rows
    ]  # fmt: skip
    pending = select(func.count()).select_from(StudentDocument).join(A, A.id == StudentDocument.application_id)
    total["documents_pending"] = await db.scalar(pending.where(A.counselor_id == user.id, StudentDocument.archived_at.is_(None), StudentDocument.verification_status == "pending"))
    return table, total


async def report(db: AsyncSession, user: User, start: date, end: date, now: datetime) -> dict:
    """The counselor's report for the inclusive IST dates `start`..`end`; `now` is the database clock."""
    lo, hi = _instants(start, end)
    period = await management_counseling.counselor_figures(db, user.id, start, end)
    follow_ups = await _follow_ups(db, user, lo, hi, now)
    tasks = await _tasks(db, user, lo, hi, india_date(now))
    table, total = await _caseload(db, user)
    values = {**period, **follow_ups, **tasks, **total}
    return {
        "from_": start,
        "to": end,
        "as_of": now,
        "period": _figures(PERIOD_FIGURES, values),
        "now": _figures(NOW_FIGURES, values),
        "applications": {
            "rows": table,
            "total": {"applications": total["applications"], "students": total["students"]},
            "definitions": [{"key": k, "label": label, "definition": text} for k, label, text in TABLE_DEFINITIONS],
        },
    }
