"""itc-030 (DEC-SCOPE-367): the IT counselor's dashboard and workspace -- nine widgets over the caller's lead book (IT leads they own, not
merged) and student book (the IT students linked to them, itc-003), computed live on every read (spec docs/superpowers/specs/2026-11-03-
itc-030-it-counselor-dashboard-design.md). Each widget's figure is the full count of the statement its list reads (AC1), and every filter
applies by one rule (AC2): course through the lead's product or the student's enrolment, batch (leads: the batch's course), the date range
on each widget's own date, the stage on the lead widgets, and -- the IT Admin only -- the owner. Read only, not logged, not audited."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import NURTURE, ORDER, STAGES
from app.models import Batch, Enquiry, Enrollment, HrReviewTask, ItStudentCounselor, LeadFollowUp, Program, StudentRiskFlag, TelProduct, User
from app.services import application_filters, fee_accounts, hr_reviews, it_status_labels, lead_handover
from app.services.bdm_appointments import IST, today_ist

FORBIDDEN = "Only an IT counselor or the IT Admin has this dashboard"
BATCH_OUTSIDE = "The batch is not in that course"
OWNER_ADMIN_ONLY = "The owner filter is for the IT Admin"
CHOOSE_COUNSELOR = "Choose an IT counselor"
LIMIT = 10
PIPELINE = (*(s for s in ORDER if s != "converted"), NURTURE)  # the open stages a counselor still works
CONVERTIBLE = tuple(s for s in ORDER if lead_handover.convertible_stage(s))  # itc-011: Qualified .. Counselling Completed
RISK_REASONS = {"attendance": "Low attendance", "assessment": "Low assessment score", "absences": "Consecutive absences"}


@dataclass(frozen=True)
class _Scope:
    admin: bool
    owner: UUID | None  # the counselor whose book this is (None: the IT Admin's every counselor)
    program: UUID | None
    batch: UUID | None
    lead_program: UUID | None  # the course leads narrow to: the chosen one, or the chosen batch's
    start: date | None
    end: date | None
    stage: str | None


def _uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(422, application_filters.UNKNOWN_VALUE) from None


async def _scope(db: AsyncSession, user: User, program: str | None, batch: str | None, date_from: str | None, date_to: str | None, stage: str | None, owner: str | None) -> _Scope:
    if user.division != "it" or user.role not in ("counselor", "it_admin"):
        raise HTTPException(403, FORBIDDEN)
    admin = user.role == "it_admin"
    if owner is not None and not admin:
        raise HTTPException(422, OWNER_ADMIN_ONLY)
    start, end = application_filters.date_range(date_from, date_to)
    if stage is not None and stage not in STAGES:
        raise HTTPException(422, application_filters.UNKNOWN_VALUE)
    program_id, batch_id, owner_id = _uuid(program), _uuid(batch), _uuid(owner)
    if program_id and await db.get(Program, program_id) is None:
        raise HTTPException(422, application_filters.UNKNOWN_VALUE)
    batch_row = await db.get(Batch, batch_id) if batch_id else None
    if batch_id and batch_row is None:
        raise HTTPException(422, application_filters.UNKNOWN_VALUE)
    if batch_row and program_id and batch_row.program_id != program_id:
        raise HTTPException(422, BATCH_OUTSIDE)
    if owner_id:
        person = await db.get(User, owner_id)
        if person is None or person.role != "counselor" or person.division != "it":
            raise HTTPException(422, CHOOSE_COUNSELOR)
    return _Scope(admin, owner_id if admin else user.id, program_id, batch_id, program_id or (batch_row.program_id if batch_row else None), start, end, stage)


# --- the clauses ----------------------------------------------------------------------------------------------------------------------
def _in_range(column, s: _Scope) -> list:
    """The inclusive IST date range on a timestamp column."""
    out = []
    if s.start:
        out.append(column >= datetime.combine(s.start, time(), IST))
    if s.end:
        out.append(column < datetime.combine(s.end + timedelta(days=1), time(), IST))
    return out


def _leads(s: _Scope, *, stage: bool = True) -> list:
    where = [Enquiry.division == "it", Enquiry.merged_at.is_(None), Enquiry.owner_id == s.owner if s.owner else Enquiry.owner_id.is_not(None)]
    if s.lead_program:
        where.append(Enquiry.product_id.in_(select(TelProduct.id).where(TelProduct.program_id == s.lead_program)))
    if stage and s.stage:
        where.append(Enquiry.status == s.stage)
    return where


def _book(s: _Scope):
    """The student ids of the book: linked IT students (to the owner, or to any counselor for the IT Admin)."""
    stmt = select(ItStudentCounselor.student_user_id).join(User, User.id == ItStudentCounselor.student_user_id).where(User.role == "it_student")
    return stmt.where(ItStudentCounselor.counselor_user_id == s.owner) if s.owner else stmt


def _seat(s: _Scope, batch_column) -> list:
    """Course and batch on a row that carries a batch (an enrolment, a risk flag)."""
    if s.batch:
        return [batch_column == s.batch]
    if s.program:
        return [batch_column.in_(select(Batch.id).where(Batch.program_id == s.program))]
    return []


def _lead_href(s: _Scope, lead_id: UUID) -> str:
    return "/it/admin/leads" if s.admin else f"/it/counselor/leads/{lead_id}"


def _student_href(s: _Scope, student_id: UUID) -> str:
    return f"/it/admin/students/{student_id}" if s.admin else f"/it/counselor/students/{student_id}"


def _item(id_, label: str, detail: str, when, href: str, overdue: bool = False) -> dict:
    return {"id": id_, "label": label, "detail": detail, "date": when, "overdue": overdue, "href": href}


async def _section(db: AsyncSession, stmt, to_item) -> dict:
    """AC1: the figure is the full count of the very statement the list reads."""
    count = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = (await db.execute(stmt.limit(LIMIT))).all()
    return {"count": count, "more": count > LIMIT, "items": [to_item(*row) for row in rows]}


# --- the widgets ----------------------------------------------------------------------------------------------------------------------
async def _lead_widgets(db: AsyncSession, s: _Scope, labels: dict[str, str], now: datetime) -> dict:
    lead_cols = (Enquiry.id, Enquiry.name, Enquiry.lead_code, Enquiry.status)

    def lead_item(id_, name, code, status, when):
        return _item(id_, name, f"{code} · {labels.get(status, status)}", when, _lead_href(s, id_))

    created = _in_range(Enquiry.created_at, s)
    tomorrow = datetime.combine(today_ist(now) + timedelta(days=1), time(), IST)
    follow_ups = (
        select(LeadFollowUp.id, Enquiry.id, Enquiry.name, LeadFollowUp.next_action, LeadFollowUp.reason, LeadFollowUp.due_at).join(Enquiry, Enquiry.id == LeadFollowUp.lead_id)
        .where(*_leads(s), LeadFollowUp.status == "open", LeadFollowUp.due_at < tomorrow, *_in_range(LeadFollowUp.due_at, s))
        .order_by(LeadFollowUp.due_at, LeadFollowUp.id)
    )  # fmt: skip
    overdue = await db.scalar(select(func.count()).select_from(follow_ups.where(LeadFollowUp.due_at < now).order_by(None).subquery())) or 0
    stages = PIPELINE if s.stage is None else tuple(x for x in PIPELINE if x == s.stage)
    counts = dict((await db.execute(select(Enquiry.status, func.count()).where(*_leads(s), Enquiry.status.in_(PIPELINE), *created).group_by(Enquiry.status))).all())
    return {
        "assigned_leads": await _section(
            db, select(*lead_cols, Enquiry.created_at).where(*_leads(s), Enquiry.status.in_(PIPELINE), *created).order_by(Enquiry.created_at.desc(), Enquiry.id), lead_item
        ),
        "follow_ups": {
            **await _section(db, follow_ups, lambda fid, lid, name, action, reason, due: _item(fid, name, action or reason.replace("_", " ").capitalize(), due, _lead_href(s, lid), due < now)),
            "overdue": overdue,
        },  # fmt: skip
        "pipeline": {"count": sum(counts.values()), "stages": [{"stage": x, "label": labels.get(x, x), "count": counts.get(x, 0)} for x in stages]},
        "conversions": await _section(
            db,
            select(*lead_cols, Enquiry.converted_at).where(*_leads(s), Enquiry.converted_at.is_not(None), *_in_range(Enquiry.converted_at, s)).order_by(Enquiry.converted_at.desc(), Enquiry.id),
            lead_item,
        ),  # fmt: skip
        "ready_to_convert": await _section(
            db,
            select(*lead_cols, Enquiry.stage_changed_at)
            .where(*_leads(s), Enquiry.status.in_(CONVERTIBLE), Enquiry.converted_user_id.is_(None), *created)
            .order_by(Enquiry.stage_changed_at.desc(), Enquiry.id),
            lead_item,
        ),  # fmt: skip
    }


def _enrolled_on(s: _Scope) -> list:
    return [c for c in ((Enrollment.enrolled_on >= s.start) if s.start else None, (Enrollment.enrolled_on <= s.end) if s.end else None) if c is not None]


async def _student_widgets(db: AsyncSession, s: _Scope) -> dict:
    book = _book(s)
    active = (Enrollment.student_id.in_(book), Enrollment.status == "active", *_seat(s, Enrollment.batch_id), *_enrolled_on(s))
    enrolled = (
        select(User.id, User.full_name, User.student_code, func.min(Enrollment.enrolled_on)).join(Enrollment, Enrollment.student_id == User.id)
        .where(*active).group_by(User.id, User.full_name, User.student_code).order_by(User.full_name, User.id)
    )  # fmt: skip
    seats = (
        await db.execute(select(Enrollment.id, User.id, User.full_name, Batch.name).join(User, User.id == Enrollment.student_id).join(Batch, Batch.id == Enrollment.batch_id).where(*active))
    ).all()
    figures = await fee_accounts.balance_for(db, [row[0] for row in seats])
    owing = sorted(((figures[eid]["balance"], eid, sid, name, batch) for eid, sid, name, batch in seats if figures[eid]["state"] != "not_billed" and figures[eid]["balance"] > 0),
                   key=lambda r: (-r[0], r[3]))  # fmt: skip
    seat_match = exists().where(Enrollment.student_id == HrReviewTask.student_user_id, *_seat(s, Enrollment.batch_id))
    hr = (
        select(HrReviewTask.id, User.id, User.full_name, HrReviewTask.updated_at).join(User, User.id == HrReviewTask.student_user_id)
        .where(HrReviewTask.student_user_id.in_(book), HrReviewTask.stage == "changes_requested", *_in_range(HrReviewTask.updated_at, s), *((seat_match,) if s.batch or s.program else ()))
        .order_by(HrReviewTask.updated_at.desc(), HrReviewTask.id)
    )  # fmt: skip
    risk = (
        select(StudentRiskFlag.id, User.id, User.full_name, Batch.name, StudentRiskFlag.reasons, StudentRiskFlag.raised_at)
        .join(User, User.id == StudentRiskFlag.student_id).join(Batch, Batch.id == StudentRiskFlag.batch_id)
        .where(StudentRiskFlag.student_id.in_(book), StudentRiskFlag.cleared_at.is_(None), *_seat(s, StudentRiskFlag.batch_id), *_in_range(StudentRiskFlag.raised_at, s))
        .order_by(StudentRiskFlag.raised_at.desc(), StudentRiskFlag.id)
    )  # fmt: skip
    return {
        "enrolled_students": await _section(db, enrolled, lambda sid, name, code, since: _item(sid, name, code or "", since, _student_href(s, sid))),
        "outstanding_fees": {
            "count": len(owing), "more": len(owing) > LIMIT, "total": round(sum(r[0] for r in owing), 2),
            "items": [_item(eid, name, f"{batch} · INR {balance:,.2f} due", None, _student_href(s, sid)) for balance, eid, sid, name, batch in owing[:LIMIT]],
        },  # fmt: skip
        "at_risk": await _section(db, risk, lambda fid, sid, name, batch, reasons, raised: _item(
            fid, name, " · ".join([batch, *(RISK_REASONS.get(r, r) for r in reasons)]), raised, _student_href(s, sid))),
        "pending_hr": await _section(db, hr, lambda tid, sid, name, at: _item(
            tid, name, f"{hr_reviews.STAGE_LABELS['changes_requested']} · {hr_reviews.NEXT_ACTIONS['changes_requested']}", at, _student_href(s, sid))),
    }  # fmt: skip


async def _options(db: AsyncSession, s: _Scope, labels: dict[str, str]) -> dict:
    programs = (await db.execute(select(Program.id, Program.title).order_by(Program.title, Program.id))).all()
    batches = (await db.execute(select(Batch.id, Batch.name, Batch.program_id).order_by(Batch.name, Batch.id))).all()
    owners = []
    if s.admin:
        owners = (await db.execute(select(User.id, User.full_name).where(User.role == "counselor", User.division == "it", User.active.is_(True)).order_by(User.full_name, User.id))).all()
    return {
        "programs": [{"value": str(i), "label": t} for i, t in programs],
        "batches": [{"value": str(i), "label": n, "program": str(p)} for i, n, p in batches],
        "stages": [{"value": x, "label": labels.get(x, x)} for x in STAGES],
        "owners": [{"value": str(i), "label": n} for i, n in owners],
    }


async def dashboard(db: AsyncSession, user: User, now: datetime, *, program: str | None = None, batch: str | None = None, date_from: str | None = None,
                    date_to: str | None = None, stage: str | None = None, owner: str | None = None) -> dict:  # fmt: skip
    s = await _scope(db, user, program, batch, date_from, date_to, stage, owner)
    labels = await it_status_labels.labels(db, "lead")  # itc-005: the IT team's stage words
    return {
        "filters": {"program": program, "batch": batch, "from": date_from, "to": date_to, "stage": stage, "owner": owner if s.admin else None},
        "options": await _options(db, s, labels),
        "today": today_ist(now).isoformat(),
        "widgets": {**await _lead_widgets(db, s, labels, now), **await _student_widgets(db, s)},
    }
