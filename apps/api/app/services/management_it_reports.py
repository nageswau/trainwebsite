"""itc-032 (DEC-SCOPE-369) -- the management IT reports, six read-only tabs over two cohorts (spec docs/superpowers/specs/2026-11-03-
itc-032-management-it-reports-design.md):

- leads       funnel (course x source, by current stage), conversions (by course) -- IT leads, not merged, created in the range
- activity    calls, completed follow-ups and conversions on IT leads, per staff member, at a time in the range
- enrolments  revenue, training, placement -- IT enrolments (seat taken) enrolled in the range

Every report reads one list of rows (one per lead, event or enrolment) and builds its totals, its groups and its drill-down page from that
same list, so each figure ties out to its rows by construction (AC1). The five filters apply to every report by one rule each (AC2): course
(a lead through its product's course), batch (a lead: the batch's course), owner (the lead's owner, the event's actor, the student's IT
counselor), the date range on the cohort's anchor, and status (a lead stage, or the itc-031 lifecycle stage derived on read). Nothing is
stored; the figures are itc-013's fee account, itc-021's attendance rule and itc-031's stage. No student or lead name leaves."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, literal, select, union, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.lead_stages import CLOSED, NURTURE, ORDER, STAGES
from app.models import Batch, Enquiry, Enrollment, ItStudentCounselor, LeadCall, LeadFollowUp, Payment, Program, TelProduct, User
from app.schemas import IT_LIFECYCLE_STAGES
from app.services import fee_accounts, it_accounts, it_lifecycle, it_status_labels, training_progress
from app.services.bdm_performance import _instants
from app.services.lead_calls import NOT_CONNECTED
from app.services.management_training import NOT_TAKEN
from app.services.telecaller_reports import SOURCE_LABELS

REPORTS = (
    ("funnel", "Lead funnel"), ("conversions", "Conversions"), ("revenue", "Revenue & outstanding"), ("training", "Attendance & completion"),
    ("placement", "Placement outcomes"), ("activity", "Team activity"),
)  # fmt: skip
KEYS = tuple(key for key, _ in REPORTS)
LEAD_REPORTS = frozenset({"funnel", "conversions", "activity"})
EXPORT_CAP = it_accounts.EXPORT_CAP
NO_OWNER = "Choose an owner from the list"
NO_STATUS = "Choose a status from the list"
NO_COURSE_LABEL = "No course"
UNKNOWN = "Unknown"
OUTCOMES = ("placed", "interview", "hr_screening", "resume_submitted", "not_placed", "not_started")
NOT_STARTED = "Not started"
KINDS = {"call": "Call", "follow_up": "Follow-up completed", "conversion": "Conversion"}

DEFINITIONS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "funnel": (
        ("leads", "Leads", "IT leads created in the period (India time), not merged into another lead."),
        ("open", "Open", "Of those, leads now at an open stage before Converted."),
        ("nurture", "Nurture", "Of those, leads now parked in Nurture."),
        ("converted", "Converted", "Of those, leads now at Converted."),
        ("closed", "Closed", "Of those, leads now at a closed stage (not interested, not eligible, lost, duplicate...)."),
        ("by_stage", "By stage", "Of those, the leads now at each stage; the stages add up to Leads."),
    ),
    "conversions": (
        ("leads", "Leads", "IT leads created in the period (India time), not merged into another lead."),
        ("converted", "Converted", "Of those, leads with a conversion to a student recorded."),
        ("conversion_pct", "Conversion rate", "Converted ÷ Leads, of the same leads."),
    ),
    "activity": (
        ("calls", "Calls", "Calls logged on IT leads in the period (India time), by the person who called."),
        ("connected_calls", "Connected calls", "Of those calls, the ones not ending busy, no answer, switched off or wrong number."),
        ("follow_ups", "Follow-ups completed", "Follow-ups on IT leads marked done in the period, by the person who completed them."),
        ("conversions", "Conversions", "IT leads converted to a student in the period, by the person who converted them."),
    ),
    "revenue": (
        ("enrolments", "Enrolments", "IT enrolments enrolled in the period (seat taken: not pending consent or rejected)."),
        ("billed", "Billed", "Total payable on those enrolments' fee accounts (fee less approved discount)."),
        ("collected", "Collected", "Confirmed payments (paid or succeeded) on those enrolments to date."),
        ("outstanding", "Outstanding", "Positive balances of those enrolments that are active, as of today."),
        ("overdue", "Overdue", "Installments of those active enrolments still owed after their due date (India time), as of today."),
    ),
    "training": (
        ("enrolments", "Enrolments", "IT enrolments enrolled in the period (seat taken: not pending consent or rejected)."),
        ("attendance_pct", "Attendance", "Classes attended (present or late; approved leave as the leave policy sets) ÷ attendance counted, over those seats."),
        ("completion_pct", "Completion", "Enrolments completed (status completed or a certificate issued) ÷ enrolments."),
    ),
    "placement": (
        ("enrolments", "Enrolments", "IT enrolments enrolled in the period (seat taken: not pending consent or rejected)."),
        ("placed", "Placed", "Enrolments whose lifecycle stage is Placed (a joined job application)."),
        ("interview", "Interview", "The student's furthest application is at interview or selected, or HR marked them interview ready."),
        ("hr_screening", "HR screening", "The student's resume is under HR review, screening, or changes were requested."),
        ("resume_submitted", "Resume submitted", "The student's resume was received by HR."),
        ("not_placed", "Not placed", "The IT Admin set the enrolment to Not placed."),
        ("not_started", NOT_STARTED, "No placement step yet (placement shows on the student's newest seat only)."),
    ),
}


@dataclass
class Filters:
    program_id: UUID | None = None
    batch_id: UUID | None = None
    owner_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    status: str | None = None
    lead_program: UUID | None = None  # the course leads narrow to: the chosen one, or the chosen batch's

    def echo(self) -> dict:
        return {k: (str(v) if v is not None else None) for k, v in vars(self).items() if k != "lead_program"}


def _people_ids():
    """Everyone the owner filter can name: IT lead owners, callers, completers and converters, and IT counselors of students."""
    it_lead = Enquiry.division == "it"
    return union(
        select(Enquiry.owner_id.label("id")).where(it_lead, Enquiry.owner_id.is_not(None)),
        select(Enquiry.converted_by_user_id).where(it_lead, Enquiry.converted_by_user_id.is_not(None)),
        select(LeadCall.caller_user_id).join(Enquiry, Enquiry.id == LeadCall.lead_id).where(it_lead),
        select(LeadFollowUp.completed_by_user_id).join(Enquiry, Enquiry.id == LeadFollowUp.lead_id).where(it_lead, LeadFollowUp.completed_by_user_id.is_not(None)),
        select(ItStudentCounselor.counselor_user_id),
    ).subquery()


async def resolve(db: AsyncSession, report: str, f: Filters) -> Filters:
    """itc-017's range and course/batch checks (and words), then the owner and the status of the report's family."""
    base = await it_accounts.resolve(db, it_accounts.Filters(f.program_id, f.batch_id, f.date_from, f.date_to))
    f.date_from, f.date_to = base.date_from, base.date_to
    if f.owner_id is not None:
        ids = _people_ids()
        if not await db.scalar(select(func.count()).select_from(ids).where(ids.c.id == f.owner_id)):
            raise HTTPException(422, NO_OWNER)
    if f.status is not None and f.status not in (STAGES if report in LEAD_REPORTS else IT_LIFECYCLE_STAGES):
        raise HTTPException(422, NO_STATUS)
    f.lead_program = f.program_id or (await db.scalar(select(Batch.program_id).where(Batch.id == f.batch_id)) if f.batch_id else None)
    return f


async def options(db: AsyncSession, report: str) -> dict:
    ids = _people_ids()
    people = (await db.execute(select(User.id, User.full_name, User.active).where(User.id.in_(select(ids.c.id))).order_by(func.lower(User.full_name), User.id))).all()
    kind = "lead" if report in LEAD_REPORTS else "lifecycle"
    labels = await it_status_labels.labels(db, kind)
    codes = STAGES if kind == "lead" else IT_LIFECYCLE_STAGES
    return {
        **await it_accounts.choices(db),
        "owners": [{"id": i, "name": n if active else f"{n} (inactive)"} for i, n, active in people],
        "statuses": [{"value": c, "label": labels.get(c, c)} for c in codes],
    }


def definitions(report: str) -> list[dict]:
    return [{"key": k, "label": label, "definition": text} for k, label, text in DEFINITIONS[report]]


def _pct(part: float, whole: float) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def _money(value) -> float:
    return round(float(value or 0), 2)


def _ist(moment) -> str | None:
    return moment.astimezone(fee_accounts.INDIA).date().isoformat() if moment else None


def _sorted_groups(groups: dict, key) -> list[dict]:
    return sorted(groups.values(), key=key)


# --- the lead cohort: funnel and conversions ----------------------------------------------------------------------------------------
Owner, Actor, Student, Counselor = aliased(User), aliased(User), aliased(User), aliased(User)


def _lead_scope(f: Filters) -> list:
    where = [Enquiry.division == "it", Enquiry.merged_at.is_(None)]
    if f.lead_program:
        where.append(Enquiry.product_id.in_(select(TelProduct.id).where(TelProduct.program_id == f.lead_program)))
    if f.status:
        where.append(Enquiry.status == f.status)
    return where


def _with_course(stmt):
    return stmt.outerjoin(TelProduct, TelProduct.id == Enquiry.product_id).outerjoin(Program, Program.id == TelProduct.program_id)


async def _leads(db: AsyncSession, f: Filters) -> list:
    lo, hi = _instants(f.date_from, f.date_to)
    stmt = _with_course(
        select(Enquiry.id, Enquiry.lead_code, Enquiry.source, Enquiry.status, Enquiry.created_at, Enquiry.converted_at, Program.id.label("program_id"),
               Program.title, Owner.full_name.label("owner")).select_from(Enquiry)
    ).outerjoin(Owner, Owner.id == Enquiry.owner_id).where(*_lead_scope(f), Enquiry.created_at >= lo, Enquiry.created_at < hi)  # fmt: skip
    if f.owner_id:
        stmt = stmt.where(Enquiry.owner_id == f.owner_id)
    return (await db.execute(stmt.order_by(Enquiry.created_at.desc(), Enquiry.id))).all()


def _bucket(stage: str) -> str:
    if stage == "converted":
        return "converted"
    if stage == NURTURE:
        return "nurture"
    return "closed" if stage in CLOSED else "open"


def _lead_item(r, labels: dict) -> dict:
    return {
        "lead_code": r.lead_code, "course": r.title or NO_COURSE_LABEL, "source": SOURCE_LABELS.get(r.source, r.source), "owner": r.owner or UNKNOWN,
        "stage": labels.get(r.status, r.status), "created_on": _ist(r.created_at), "converted_on": _ist(r.converted_at),
    }  # fmt: skip


async def funnel(db: AsyncSession, f: Filters) -> dict:
    rows, labels = await _leads(db, f), await it_status_labels.labels(db, "lead")
    counts = dict.fromkeys(("open", "nurture", "converted", "closed"), 0)
    stages: dict[str, int] = defaultdict(int)
    groups: dict = {}
    for r in rows:
        bucket = _bucket(r.status)
        counts[bucket] += 1
        stages[r.status] += 1
        g = groups.setdefault((r.program_id, r.source), {
            "program_id": str(r.program_id) if r.program_id else None, "course": r.title or NO_COURSE_LABEL, "source": SOURCE_LABELS.get(r.source, r.source),
            "leads": 0, **dict.fromkeys(counts, 0),
        })  # fmt: skip
        g["leads"] += 1
        g[bucket] += 1
    order = (*ORDER, NURTURE, *(s for s in STAGES if s not in ORDER and s != NURTURE))
    by_stage = [{"stage": s, "label": labels.get(s, s), "count": stages[s]} for s in order if stages[s]]
    return {
        "totals": {"leads": len(rows), **counts, "by_stage": by_stage},
        "groups": _sorted_groups(groups, lambda g: (g["course"].lower(), -g["leads"], g["source"].lower())),
        "rows": [_lead_item(r, labels) for r in rows],
    }


async def conversions(db: AsyncSession, f: Filters) -> dict:
    rows, labels = await _leads(db, f), await it_status_labels.labels(db, "lead")
    groups: dict = {}
    for r in rows:
        g = groups.setdefault(r.program_id, {"program_id": str(r.program_id) if r.program_id else None, "course": r.title or NO_COURSE_LABEL, "leads": 0, "converted": 0})
        g["leads"] += 1
        g["converted"] += r.converted_at is not None
    for g in groups.values():
        g["conversion_pct"] = _pct(g["converted"], g["leads"])
    converted = [r for r in rows if r.converted_at is not None]
    items = [{**_lead_item(r, labels), "days_to_convert": (r.converted_at - r.created_at).days} for r in sorted(converted, key=lambda r: r.converted_at, reverse=True)]
    return {
        "totals": {"leads": len(rows), "converted": len(converted), "conversion_pct": _pct(len(converted), len(rows))},
        "groups": _sorted_groups(groups, lambda g: (-g["converted"], g["course"].lower())),
        "rows": items,
    }


# --- team activity ------------------------------------------------------------------------------------------------------------------


async def activity(db: AsyncSession, f: Filters) -> dict:
    events = union_all(
        select(literal("call").label("kind"), LeadCall.occurred_at.label("at"), LeadCall.caller_user_id.label("actor"), LeadCall.lead_id.label("lead_id"),
               LeadCall.outcome.label("outcome")),
        select(literal("follow_up"), LeadFollowUp.completed_at, LeadFollowUp.completed_by_user_id, LeadFollowUp.lead_id, literal(None))
        .where(LeadFollowUp.completed_at.is_not(None)),
        select(literal("conversion"), Enquiry.converted_at, Enquiry.converted_by_user_id, Enquiry.id, literal(None)).where(Enquiry.converted_at.is_not(None)),
    ).subquery()  # fmt: skip
    lo, hi = _instants(f.date_from, f.date_to)
    stmt = _with_course(
        select(events.c.kind, events.c.at, events.c.actor, events.c.outcome, Enquiry.lead_code, Enquiry.status, Program.title, Actor.full_name.label("staff"))
        .select_from(events).join(Enquiry, Enquiry.id == events.c.lead_id)
    ).outerjoin(Actor, Actor.id == events.c.actor).where(*_lead_scope(f), events.c.at >= lo, events.c.at < hi)  # fmt: skip
    if f.owner_id:
        stmt = stmt.where(events.c.actor == f.owner_id)
    rows = (await db.execute(stmt.order_by(events.c.at.desc(), Enquiry.lead_code))).all()
    labels = await it_status_labels.labels(db, "lead")
    figures = ("calls", "connected_calls", "follow_ups", "conversions")
    totals = dict.fromkeys(figures, 0)
    groups: dict = {}
    items = []
    for r in rows:
        connected = r.kind == "call" and r.outcome not in NOT_CONNECTED
        hit = {"call": "calls", "follow_up": "follow_ups", "conversion": "conversions"}[r.kind]
        g = groups.setdefault(r.actor, {"owner_id": str(r.actor) if r.actor else None, "staff": r.staff or UNKNOWN, **dict.fromkeys(figures, 0)})
        for target in (g, totals):
            target[hit] += 1
            target["connected_calls"] += connected
        items.append({
            "at": r.at.astimezone(fee_accounts.INDIA).strftime("%Y-%m-%d %H:%M"), "kind": KINDS[r.kind], "connected": ("Yes" if connected else "No") if r.kind == "call" else None,
            "staff": r.staff or UNKNOWN, "lead_code": r.lead_code, "course": r.title or NO_COURSE_LABEL, "stage": labels.get(r.status, r.status),
        })  # fmt: skip
    return {
        "totals": {"events": len(rows), **totals},
        "groups": _sorted_groups(groups, lambda g: (-(g["calls"] + g["follow_ups"] + g["conversions"]), g["staff"].lower())),
        "rows": items,
    }


# --- the enrolment cohort: revenue, training, placement -----------------------------------------------------------------------------


async def _enrolments(db: AsyncSession, f: Filters) -> tuple[list, dict]:
    """The cohort's rows with their derived lifecycle (itc-031), narrowed to the status when one is chosen."""
    stmt = (
        select(Enrollment.id, Enrollment.enrollment_code, Enrollment.status, Enrollment.student_id, Enrollment.batch_id, Enrollment.enrolled_on,
               Enrollment.progress_percent, Student.student_code, Program.id.label("program_id"), Program.title, Batch.name.label("batch"),
               Counselor.full_name.label("counselor"))
        .select_from(Enrollment).join(Batch, Batch.id == Enrollment.batch_id).join(Program, Program.id == Batch.program_id)
        .join(Student, Student.id == Enrollment.student_id)
        .outerjoin(ItStudentCounselor, ItStudentCounselor.student_user_id == Enrollment.student_id).outerjoin(Counselor, Counselor.id == ItStudentCounselor.counselor_user_id)
        .where(Enrollment.status.not_in(NOT_TAKEN), Enrollment.enrolled_on >= f.date_from, Enrollment.enrolled_on <= f.date_to)
    )  # fmt: skip
    if f.batch_id:
        stmt = stmt.where(Batch.id == f.batch_id)
    if f.program_id:
        stmt = stmt.where(Batch.program_id == f.program_id)
    if f.owner_id:
        stmt = stmt.where(ItStudentCounselor.counselor_user_id == f.owner_id)
    rows = (await db.execute(stmt.order_by(func.lower(Program.title), Enrollment.enrolled_on.desc(), Enrollment.enrollment_code))).all()
    derived = await it_lifecycle.derive_many(db, [r.id for r in rows])
    if f.status:
        rows = [r for r in rows if derived[r.id]["stage"] == f.status]
    return rows, derived


def _seat_item(r, stage_label: str) -> dict:
    return {
        "enrollment_code": r.enrollment_code, "student_code": r.student_code, "course": r.title, "batch": r.batch, "counselor": r.counselor or UNKNOWN,
        "enrolled_on": r.enrolled_on.isoformat(), "stage": stage_label,
    }  # fmt: skip


def _by_course(rows, items: list[dict], figures: tuple[str, ...]) -> dict:
    groups: dict = {}
    for r, item in zip(rows, items, strict=True):
        g = groups.setdefault(r.program_id, {"program_id": str(r.program_id), "course": r.title, "enrolments": 0, **dict.fromkeys(figures, 0)})
        g["enrolments"] += 1
        for key in figures:
            g[key] += item[key]
    return groups


async def revenue(db: AsyncSession, f: Filters) -> dict:
    rows, derived = await _enrolments(db, f)
    ids = [r.id for r in rows]
    accounts = await fee_accounts.balance_for(db, ids)
    late = {}
    if ids:
        today = fee_accounts.india_today()
        stmt = (
            select(Payment.reference_id, func.sum(Payment.amount))
            .where(Payment.division == "it", Payment.reference_type.in_(fee_accounts.FEE_REFERENCES), Payment.reference_id.in_(ids),
                   Payment.status.in_(fee_accounts.OWED), Payment.amount > 0, Payment.due_date < today)
            .group_by(Payment.reference_id)
        )  # fmt: skip
        late = {eid: _money(amount) for eid, amount in (await db.execute(stmt)).all()}
    labels = await it_status_labels.labels(db, "lifecycle")
    items = []
    for r in rows:
        fig, active = accounts[r.id], r.status == it_accounts.ACTIVE
        owing = active and fig["state"] != "not_billed" and fig["balance"] > 0
        items.append({
            **_seat_item(r, labels[derived[r.id]["stage"]]), "billed": _money(fig["total_payable"]), "collected": _money(fig["paid_confirmed"]),
            "outstanding": _money(fig["balance"]) if owing else 0.0, "overdue": late.get(r.id, 0.0) if active else 0.0,
        })  # fmt: skip
    money = ("billed", "collected", "outstanding", "overdue")
    groups = _by_course(rows, items, money)
    for g in groups.values():
        g.update({k: _money(g[k]) for k in money})
    return {
        "totals": {"enrolments": len(items), **{k: _money(sum(i[k] for i in items)) for k in money}},
        "groups": _sorted_groups(groups, lambda g: g["course"].lower()),
        "rows": items,
    }


async def training(db: AsyncSession, f: Filters) -> dict:
    rows, derived = await _enrolments(db, f)
    seats = {}
    if rows:
        att = training_progress.attendance()
        stmt = select(att.c.student_id, att.c.batch_id, att.c.attended, att.c.counted).where(
            att.c.student_id.in_(list({r.student_id for r in rows})), att.c.batch_id.in_(list({r.batch_id for r in rows}))
        )
        seats = {(s, b): (attended, counted) for s, b, attended, counted in (await db.execute(stmt)).all()}
    labels = await it_status_labels.labels(db, "lifecycle")
    items = []
    for r in rows:
        attended, counted = seats.get((r.student_id, r.batch_id), (0, 0))
        done = derived[r.id]["components"]["training"] == "completed"
        items.append({
            **_seat_item(r, labels[derived[r.id]["stage"]]), "attended": attended, "counted": counted, "attendance_pct": _pct(attended, counted),
            "progress": r.progress_percent, "completed": done,
        })  # fmt: skip
    groups = _by_course(rows, items, ("attended", "counted", "completed"))
    for g in groups.values():
        g.update(attendance_pct=_pct(g["attended"], g["counted"]), completion_pct=_pct(g["completed"], g["enrolments"]))
    attended, counted, completed = (sum(i[k] for i in items) for k in ("attended", "counted", "completed"))
    return {
        "totals": {"enrolments": len(items), "attended": attended, "counted": counted, "attendance_pct": _pct(attended, counted), "completed": completed,
                   "completion_pct": _pct(completed, len(items))},
        "groups": _sorted_groups(groups, lambda g: g["course"].lower()),
        "rows": items,
    }  # fmt: skip


def _outcome(d: dict) -> str:
    if d["stage"] in ("placed", "not_placed"):
        return d["stage"]
    return d["components"]["placement"] or "not_started"


async def placement(db: AsyncSession, f: Filters) -> dict:
    rows, derived = await _enrolments(db, f)
    labels = await it_status_labels.labels(db, "lifecycle")
    items = [{**_seat_item(r, labels[derived[r.id]["stage"]]), "outcome": _outcome(derived[r.id])} for r in rows]
    for item in items:
        item["outcome_label"] = labels.get(item["outcome"], NOT_STARTED)
        item.update({o: int(item["outcome"] == o) for o in OUTCOMES})
    groups = _by_course(rows, items, OUTCOMES)
    for item in items:
        for o in OUTCOMES:
            del item[o]
    return {
        "totals": {"enrolments": len(items), **{o: sum(g[o] for g in groups.values()) for o in OUTCOMES}},
        "groups": _sorted_groups(groups, lambda g: g["course"].lower()),
        "rows": items,
    }


RUN = {"funnel": funnel, "conversions": conversions, "activity": activity, "revenue": revenue, "training": training, "placement": placement}

# --- CSV (R5): the drill-down columns of each report, in order ------------------------------------------------------------------------
_LEAD = [("Lead", "lead_code"), ("Course", "course"), ("Source", "source"), ("Owner", "owner"), ("Stage", "stage"), ("Created on", "created_on")]
_SEAT = [("Enrolment", "enrollment_code"), ("Student ID", "student_code"), ("Course", "course"), ("Batch", "batch"), ("Counselor", "counselor"),
         ("Enrolled on", "enrolled_on"), ("Stage", "stage")]  # fmt: skip
COLUMNS: dict[str, list[tuple[str, str]]] = {
    "funnel": [*_LEAD, ("Converted on", "converted_on")],
    "conversions": [*_LEAD, ("Converted on", "converted_on"), ("Days to convert", "days_to_convert")],
    "activity": [("When (IST)", "at"), ("Activity", "kind"), ("Connected", "connected"), ("Staff", "staff"), ("Lead", "lead_code"), ("Course", "course"),
                 ("Lead stage", "stage")],
    "revenue": [*_SEAT, ("Billed (INR)", "billed"), ("Collected (INR)", "collected"), ("Outstanding (INR)", "outstanding"), ("Overdue (INR)", "overdue")],
    "training": [*_SEAT, ("Attended", "attended"), ("Counted", "counted"), ("Attendance %", "attendance_pct"), ("Progress %", "progress"), ("Completed", "completed")],
    "placement": [*_SEAT, ("Placement outcome", "outcome_label")],
}  # fmt: skip
