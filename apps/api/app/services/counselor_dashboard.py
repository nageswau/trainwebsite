"""ccrm-032 (DEC-SCOPE-277, D1-D10): the overseas counselor's action dashboard -- twelve sections over the counselor's own leads, tasks,
follow-ups, appointments, calls, students and applications, computed live on every read. Each section is its full count plus the first
`LIMIT` items, soonest first, and every item links to the page where the work is done. Read-only and not audited (ccrm-036 P9). Spec:
docs/superpowers/specs/2026-10-25-ccrm-032-counselor-action-dashboard-design.md."""

from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application_outcome import TERMINAL
from app.lead_stages import CLOSED, STAGE_LABELS
from app.models import (
    LEAD_APPOINTMENT_OPEN,
    AgentStudent,
    ApplicationDepositRecord,
    ApplicationOffer,
    ApplicationOfferCondition,
    Appointment,
    CounselorTask,
    DocumentRequest,
    Enquiry,
    LeadCall,
    LeadFollowUp,
    OverseasApplication,
    StudentDocument,
    University,
    User,
    VisaCase,
)
from app.services import counselor_students, lead_handover, student_archive
from app.services.agent_applications import WITHDRAWN
from app.services.bdm_appointments import IST, today_ist
from app.services.counselor_tasks import TASKS_URL
from app.visa_status import label as visa_label

LIMIT = 10  # D6
WINDOW_DAYS = 14  # D4: "approaching" = due within this many days (past-due included, flagged)
FOLLOW_UP_DAYS = 7  # ccrm-042 (DEC-SCOPE-313): follow-ups and tasks = overdue + today + the next 7 days
NOT_CONTACTED = ("new", "assigned", "first_call_pending")  # D10
PAST_NEXT_ACTION = frozenset({"application_enrollment", "converted"})  # the counselor's link is in place (ccrm-003 MANUAL_BEFORE)
VISA_WAITING = ("submitted", "additional_info_requested", "decision_pending")
BASE = "/overseas/counselor"
OWNER = func.coalesce(User.full_name, AgentStudent.full_name)


def _human(value: str | None) -> str:
    return value.replace("_", " ").capitalize() if value else ""


def _item(id_, label: str, detail: str, when, href: str, overdue: bool = False) -> dict:
    return {"id": id_, "label": label, "detail": detail, "date": when, "overdue": overdue, "href": href}


async def _section(db: AsyncSession, stmt, to_item) -> dict:
    count = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = (await db.execute(stmt.limit(LIMIT))).all()
    return {"count": count, "more": count > LIMIT, "items": [to_item(*row) for row in rows]}


def _lead_href(lead_id) -> str:
    return f"{BASE}/leads/{lead_id}"


def _lead_label(lead: Enquiry) -> str:
    return f"{lead.lead_code} · {lead.name}"


def _app_href(app: OverseasApplication) -> str:
    """D5: the student's 360 for a direct student, else the applications list narrowed as the ccrm-012 search does."""
    if app.student_id:
        return f"{BASE}/students/{app.student_id}"
    return f"{BASE}/applications?{urlencode({'university': app.university_id, 'intake': app.intake})}"


def _app_label(app: OverseasApplication, owner: str | None) -> str:
    return f"{app.application_code} · {owner or 'Student'}"


def _apps(user: User, *columns):
    """D2: the counselor's own live applications -- not withdrawn, not closed or on hold, the student not archived -- with the
    university name and the owner's display name (a student with no login keeps the agency record's name)."""
    a = OverseasApplication
    return (
        select(a, University.name, OWNER, *columns)
        .join(University, University.id == a.university_id)
        .outerjoin(User, User.id == a.student_id)
        .outerjoin(AgentStudent, AgentStudent.id == a.agent_student_id)
        .where(
            a.counselor_id == user.id,
            a.status != WITHDRAWN,
            student_archive.not_archived(a.student_id),
            or_(a.outcome.is_(None), a.outcome.notin_((*TERMINAL, "on_hold"))),
        )
    )


def _app_item(id_, app, university: str, owner, what: str, when: date | None, today: date) -> dict:
    detail = f"{what} · {university}" if what else university
    return _item(id_, _app_label(app, owner), detail, when, _app_href(app), overdue=when is not None and when < today)


async def dashboard(db: AsyncSession, user: User, now: datetime) -> dict:
    """The caller has checked the role (an overseas counselor)."""
    today = today_ist(now)
    start = datetime.combine(today, time.min, IST)
    end, horizon = start + timedelta(days=1), today + timedelta(days=WINDOW_DAYS)
    week = today + timedelta(days=FOLLOW_UP_DAYS)  # ccrm-042: the last day the follow-ups and tasks sections cover
    leads = lead_handover.counselor_scope(user)
    s: dict = {}

    s["new_leads"] = await _section(
        db,
        select(Enquiry).where(*leads, Enquiry.status.in_(NOT_CONTACTED)).order_by(Enquiry.created_at.desc(), Enquiry.id),
        lambda e: _item(e.id, _lead_label(e), f"{STAGE_LABELS.get(e.status, e.status)}, received", e.created_at, _lead_href(e.id)),
    )

    def appointment(a: Appointment, lead: Enquiry | None, student: str | None) -> dict:
        who = _lead_label(lead) if lead else student or "Student"
        href = _lead_href(lead.id) if lead else f"{BASE}/students/{a.student_id}" if a.student_id else f"{BASE}/appointments"
        return _item(a.id, who, f"{_human(a.appointment_type)} · {_human(a.mode)}", a.scheduled_at, href)

    s["appointments_today"] = await _section(
        db,
        select(Appointment, Enquiry, User.full_name)
        .outerjoin(Enquiry, Enquiry.id == Appointment.lead_id)
        .outerjoin(User, User.id == Appointment.student_id)
        .where(Appointment.staff_id == user.id, Appointment.status.in_(LEAD_APPOINTMENT_OPEN), Appointment.scheduled_at >= start, Appointment.scheduled_at < end)
        .order_by(Appointment.scheduled_at, Appointment.id),
        appointment,
    )
    s["calls_today"] = await _section(
        db,
        select(LeadCall, Enquiry)
        .join(Enquiry, Enquiry.id == LeadCall.lead_id)
        .where(LeadCall.caller_user_id == user.id, LeadCall.occurred_at >= start, LeadCall.occurred_at < end)
        .order_by(LeadCall.occurred_at.desc(), LeadCall.id),
        lambda c, e: _item(c.id, _lead_label(e), _human(c.outcome), c.occurred_at, _lead_href(e.id)),
    )
    s["follow_ups"] = await _section(
        db,
        select(LeadFollowUp, Enquiry)
        .join(Enquiry, Enquiry.id == LeadFollowUp.lead_id)
        .where(*leads, LeadFollowUp.status == "open", LeadFollowUp.due_at < start + timedelta(days=FOLLOW_UP_DAYS + 1))
        .order_by(LeadFollowUp.due_at, LeadFollowUp.id),
        lambda f, e: _item(f.id, _lead_label(e), f.next_action or _human(f.reason), f.due_at, _lead_href(e.id), overdue=f.due_at < start),
    )
    s["overdue_tasks"] = await _section(  # ccrm-042: the key stays for compatibility; the section now also lists tasks due this week
        db,
        select(CounselorTask).where(CounselorTask.counselor_user_id == user.id, CounselorTask.status == "open", CounselorTask.due_on <= week).order_by(CounselorTask.due_on, CounselorTask.id),
        lambda t: _item(t.id, t.title, _human(t.priority) + " priority", t.due_on, TASKS_URL, overdue=t.due_on < today),
    )
    s["no_next_action"] = await _section(
        db,
        select(Enquiry).where(*leads, Enquiry.status.notin_((*NOT_CONTACTED, *CLOSED, *PAST_NEXT_ACTION)), Enquiry.next_action.is_(None)).order_by(Enquiry.stage_changed_at, Enquiry.id),
        lambda e: _item(e.id, _lead_label(e), f"{STAGE_LABELS.get(e.status, e.status)} since", e.stage_changed_at, _lead_href(e.id)),
    )

    # D5 pending documents: a visible, unarchived student with an open request or a document awaiting verification
    open_requests = select(func.count()).where(DocumentRequest.student_user_id == User.id, DocumentRequest.status == "open").scalar_subquery()
    to_verify = select(func.count()).where(StudentDocument.student_id == User.id, StudentDocument.archived_at.is_(None), StudentDocument.verification_status == "pending").scalar_subquery()
    next_due = select(func.min(DocumentRequest.due_date)).where(DocumentRequest.student_user_id == User.id, DocumentRequest.status == "open").scalar_subquery()

    def pending(student: User, requested: int, verify: int, due: date | None) -> dict:
        parts = [f"{n} {word}" for n, word in ((requested, "requested"), (verify, "to verify")) if n]
        return _item(student.id, student.full_name, " · ".join(parts), due, f"{BASE}/students/{student.id}", overdue=due is not None and due < today)

    s["pending_documents"] = await _section(
        db,
        select(User, open_requests, to_verify, next_due)
        .where(User.role == "overseas_student", User.id.in_(counselor_students.visible_student_ids(user)), student_archive.not_archived(User.id), or_(open_requests > 0, to_verify > 0))
        .order_by(next_due.asc().nulls_last(), User.full_name, User.id),
        pending,
    )

    a = OverseasApplication
    s["not_ready"] = await _section(
        db,
        _apps(user).where(a.status == "university_selection", a.submitted_on.is_(None), a.documents_completed_on.is_(None)).order_by(a.application_deadline.asc().nulls_last(), a.id),
        lambda app, uni, owner: _app_item(app.id, app, uni, owner, "Application deadline" if app.application_deadline else "Checklist not complete", app.application_deadline, today),
    )
    s["awaiting_decision"] = await _section(
        db,
        _apps(user).where(a.status == "university_selection", a.submitted_on.isnot(None)).order_by(a.decision_due_on.asc().nulls_last(), a.submitted_on, a.id),
        lambda app, uni, owner: (
            _app_item(app.id, app, uni, owner, "Decision expected" if app.decision_due_on else "Submitted", app.decision_due_on or app.submitted_on, today)
            | {"overdue": app.decision_due_on is not None and app.decision_due_on < today}
        ),
    )

    # offers_due: three kinds of dated offer work merged into one list by date (one query per kind)
    o, c, d = ApplicationOffer, ApplicationOfferCondition, ApplicationDepositRecord
    kinds = (
        (
            "Offer deadline",
            _apps(user, o.id.label("item_id"), o.offer_deadline.label("due"))
            .join(o, and_(o.application_id == a.id, o.status == "active", o.decision == "considering"))
            .where(o.offer_deadline <= horizon),
        ),
        (
            "Condition due",
            _apps(user, c.id.label("item_id"), c.due_date.label("due"))
            .join(o, and_(o.application_id == a.id, o.status == "active"))
            .join(c, and_(c.offer_id == o.id, c.status == "open"))
            .where(c.due_date <= horizon),
        ),
        (
            "Deposit due",
            _apps(user, d.id.label("item_id"), d.due_date.label("due")).join(d, and_(d.application_id == a.id, d.required.is_(True), d.payment_status == "pending")).where(d.due_date <= horizon),
        ),
    )
    offer_rows = []
    for what, stmt in kinds:
        offer_rows += [(due, what, item_id, app, uni, owner) for app, uni, owner, item_id, due in (await db.execute(stmt)).all()]
    offer_rows.sort(key=lambda r: (r[0], str(r[2])))
    s["offers_due"] = {
        "count": len(offer_rows),
        "more": len(offer_rows) > LIMIT,
        "items": [_app_item(item_id, app, uni, owner, what, due, today) for due, what, item_id, app, uni, owner in offer_rows[:LIMIT]],
    }

    v = VisaCase
    upcoming = and_(v.appointment_date.isnot(None), v.appointment_date.between(today, horizon))

    def visa(app, uni, owner, case: VisaCase) -> dict:
        """QA-01/02: the detail names the date shown -- the appointment in the window, else the expected decision (when known)."""
        if case.appointment_date and today <= case.appointment_date <= horizon:
            return _app_item(case.id, app, uni, owner, "Visa appointment", case.appointment_date, today)
        status = f"Visa {visa_label(case.visa_status).lower()}"
        if case.expected_decision_date is None:
            return _app_item(case.id, app, uni, owner, status, None, today)
        what = "Visa decision expected" if case.visa_status == "decision_pending" else f"{status}, decision expected"
        return _app_item(case.id, app, uni, owner, what, case.expected_decision_date, today)

    s["visa"] = await _section(
        db,
        _apps(user, v).join(v, v.application_id == a.id).where(v.decision.is_(None), or_(upcoming, v.visa_status.in_(VISA_WAITING))).order_by(v.appointment_date.asc().nulls_last(), v.id),
        visa,
    )
    approved = or_(a.sub_status == "visa_approved", exists().where(v.application_id == a.id, v.decision == "approved"))
    s["enrolment"] = await _section(
        db,
        _apps(user)
        .where(or_(and_(a.status != "enrolled", a.enrollment_confirmed_at.is_(None), approved), and_(a.status == "enrolled", a.arrival_confirmed_at.is_(None))))
        .order_by(a.course_start_date.asc().nulls_last(), a.id),
        # overdue once the course has started and the enrolment or arrival is still not confirmed
        lambda app, uni, owner: _app_item(
            app.id, app, uni, owner, ("Confirm arrival" if app.status == "enrolled" else "Confirm enrolment") + (", course starts" if app.course_start_date else ""), app.course_start_date, today
        ),
    )
    return {"today": today, "window_days": WINDOW_DAYS, "follow_up_days": FOLLOW_UP_DAYS, "sections": s}
