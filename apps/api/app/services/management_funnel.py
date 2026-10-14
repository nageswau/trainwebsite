"""mgmt-016 (EVID-017 §11, spec SF1-SF16): the student funnel -- the lead journey, then the IT training and abroad education paths side by
side -- for an IST period, optionally broken down by one dimension. Each stage counts the records that reached it in the period (SF2:
activity, not a cohort, since a lead and the records of the student it became are not linked). Every stage is one select of one row per
counted record with its dimension columns, so a stage costs one query with or without a breakdown, and the rows plus "Unknown" always add
up to the stage total (AC2). Read-only; only counts and organisation or staff names leave."""

from collections import Counter
from collections.abc import Callable
from datetime import date, datetime

from sqlalchemy import Select, Subquery, case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    AgentOrg,
    AgentOrgMember,
    ApplicationStatusHistory,
    Appointment,
    Batch,
    Certificate,
    Country,
    Enquiry,
    Enrollment,
    JobApplication,
    JobOffer,
    LeadCall,
    OverseasApplication,
    OverseasCourse,
    Program,
    School,
    SchoolStudent,
    University,
    User,
    VisaCase,
)
from app.services.agent_applications import OFFER_COUNTED_STATUSES
from app.services.bdm_performance import _instants
from app.services.telecaller_metrics import first_conversions
from app.services.telecaller_reports import SOURCE_LABELS

PATHS = (("lead", "Lead journey"), ("it", "IT training"), ("abroad", "Abroad education"))
# SF16: (key, label, tracked). A dimension applies to the stages whose select carries its column; Branch is not tracked anywhere (M10).
DIMENSIONS = (
    ("country", "Country", True), ("course", "Course", True), ("agent", "Agent", True), ("school", "School", True),
    ("counselor", "Counselor", True), ("source", "Marketing source", True), ("bdm", "BDM", True), ("intake", "Intake", True),
    ("branch", "Branch", False),
)  # fmt: skip
NOT_SEATED = ("pending_consent", "rejected")  # SF7: an enrolment that never took its seat


def _leads(*where) -> Select:
    """One row per lead. Counselor = the lead's current owner when that is a counselor (SF16)."""
    owner = aliased(User)
    counselor = case((owner.role == "counselor", Enquiry.owner_id)).label("counselor")
    return select(Enquiry.id, counselor, Enquiry.source.label("source"), Enquiry.bdm_user_id.label("bdm")).outerjoin(owner, owner.id == Enquiry.owner_id).where(*where)


def _abroad(*where) -> Select:
    """One row per overseas application: its university's country, course, agency, school, counselor and intake (blank = Unknown)."""
    return (
        select(OverseasApplication.id, University.country_id.label("country"), OverseasApplication.course_id.label("course"),
               AgentOrgMember.org_id.label("agent"), SchoolStudent.school_id.label("school"), OverseasApplication.counselor_id.label("counselor"),
               func.nullif(func.trim(OverseasApplication.intake), "").label("intake"))
        .join(University, University.id == OverseasApplication.university_id)
        .outerjoin(AgentOrgMember, AgentOrgMember.user_id == OverseasApplication.agent_id)
        .outerjoin(SchoolStudent, SchoolStudent.id == OverseasApplication.school_student_id)
        .where(*where)
    )  # fmt: skip


def _first_move(statuses) -> Subquery:
    """Each application's first recorded move into one of `statuses` (`id`, `at`)."""
    h = ApplicationStatusHistory
    return select(h.application_id.label("id"), func.min(h.created_at).label("at")).where(h.to_status.in_(statuses)).group_by(h.application_id).subquery()


def _first_moved(statuses, lo: datetime, hi: datetime) -> Select:
    first = _first_move(statuses)
    return _abroad(first.c.at >= lo, first.c.at < hi).join(first, first.c.id == OverseasApplication.id)


def _student_offers(*where) -> Select:
    """SF10/SF11: job offers to EduSphere students (an outside candidate has no `student_id`)."""
    return select(JobOffer.id).join(JobApplication, JobApplication.id == JobOffer.application_id).where(JobApplication.student_id.is_not(None), *where)


def _stages(start: date, end: date) -> list[tuple[str, str, str, str, Select]]:
    """(key, label, path, definition, select of one row per counted record) in §11 order."""
    lo, hi = _instants(start, end)
    first = first_conversions()
    seated = (
        select(Enrollment.id, Batch.program_id.label("course"))
        .join(Batch, Batch.id == Enrollment.batch_id)
        .where(Enrollment.enrolled_on >= start, Enrollment.enrolled_on <= end, Enrollment.status.not_in(NOT_SEATED), Batch.status != "cancelled")
    )
    visa = exists().where(VisaCase.application_id == OverseasApplication.id, VisaCase.decision == "approved", VisaCase.decided_at >= lo, VisaCase.decided_at < hi)
    return [
        ("leads", "Leads", "lead", "Leads created in the period, from every source and division.", _leads(Enquiry.created_at >= lo, Enquiry.created_at < hi)),
        ("telecalling", "Telecalling", "lead", "Leads with at least one telecaller call logged in the period.",
         _leads(exists().where(LeadCall.lead_id == Enquiry.id, LeadCall.occurred_at >= lo, LeadCall.occurred_at < hi))),
        ("counseling", "Counseling", "lead", "Leads with a counseling appointment completed that was scheduled in the period.",
         _leads(exists().where(Appointment.lead_id == Enquiry.id, Appointment.status == "completed", Appointment.scheduled_at >= lo, Appointment.scheduled_at < hi))),
        ("registration", "Registration", "lead", "Leads first converted in the period and still converted.",
         _leads(Enquiry.status == "converted", first.c.at >= lo, first.c.at < hi).join(first, first.c.lead_id == Enquiry.id)),
        ("training", "Training", "it", "Course seats taken in the period (enrolled, not pending consent or rejected, batch not cancelled).", seated),
        ("it_application", "Application", "it", "Job applications of EduSphere students created in the period.",
         select(JobApplication.id).where(JobApplication.student_id.is_not(None), JobApplication.created_at >= lo, JobApplication.created_at < hi)),
        ("certification", "Certification", "it", "Certificates issued in the period.",
         select(Certificate.id, Certificate.program_id.label("course")).where(Certificate.issued_on >= start, Certificate.issued_on <= end)),
        ("placement", "Placement", "it", "Job offers made to EduSphere students in the period.", _student_offers(JobOffer.offered_on >= start, JobOffer.offered_on <= end)),
        ("joining", "Joining", "it", "Job offers EduSphere students joined, by actual joining date in the period.",
         _student_offers(JobOffer.joining_status == "joined", JobOffer.actual_joining_date >= start, JobOffer.actual_joining_date <= end)),
        ("abroad_education", "Abroad Education", "abroad", "Overseas applications created in the period, from students, schools and agencies.",
         _abroad(OverseasApplication.created_at >= lo, OverseasApplication.created_at < hi)),
        ("abroad_application", "Application", "abroad", "Overseas applications submitted in the period.",
         _abroad(OverseasApplication.submitted_on >= start, OverseasApplication.submitted_on <= end)),
        ("offer", "Offer", "abroad", "Applications whose first move into an offer status was recorded in the period.", _first_moved(OFFER_COUNTED_STATUSES, lo, hi)),
        ("visa", "Visa", "abroad", "Applications with a visa decided approved in the period.", _abroad(visa)),
        ("enrollment", "Enrollment", "abroad", "Applications whose first move to enrolled was recorded in the period.", _first_moved(("enrolled",), lo, hi)),
    ]  # fmt: skip


def _people(rows) -> dict:
    return {id_: f"{name} (inactive)" if not active else name for id_, name, active in rows}


# SF16: the label of each value of a dimension, from at most two lookups.
LABELS: dict[str, Callable[[list], list[Select]]] = {
    "country": lambda ids: [select(Country.id, Country.name).where(Country.id.in_(ids))],
    "course": lambda ids: [
        select(Program.id, Program.title).where(Program.id.in_(ids)),
        select(OverseasCourse.id, OverseasCourse.title + " — " + University.name).join(University, University.id == OverseasCourse.university_id).where(OverseasCourse.id.in_(ids)),
    ],
    "agent": lambda ids: [select(AgentOrg.id, AgentOrg.name).where(AgentOrg.id.in_(ids))],
    "school": lambda ids: [select(School.id, School.name).where(School.id.in_(ids))],
}  # fmt: skip


async def _labels(db: AsyncSession, by: str, values: list) -> dict:
    if by in ("counselor", "bdm"):
        return _people(await db.execute(select(User.id, User.full_name, User.active).where(User.id.in_(values))))
    if by == "source":
        return {v: SOURCE_LABELS.get(v, v) for v in values}
    if by == "intake":
        return {v: v for v in values}
    labels: dict = {}
    for stmt in LABELS[by](values):
        labels.update({id_: label for id_, label in await db.execute(stmt)})
    return labels


async def dashboard(db: AsyncSession, start: date, end: date, now: datetime, by: str | None) -> dict:
    """The fourteen stage counts for the inclusive IST dates `start`..`end`; with `by`, each applicable stage grouped by that dimension."""
    stages = _stages(start, end)
    applies = {key: [s[0] for s in stages if key in s[4].selected_columns.keys()] for key, _, _ in DIMENSIONS}
    counts: dict[str, dict] = {}
    for key, *_, stmt in stages:
        sub = stmt.subquery()
        if by is not None and key in applies[by]:
            counts[key] = dict((await db.execute(select(sub.c[by], func.count()).group_by(sub.c[by]))).all())
        else:
            counts[key] = {None: await db.scalar(select(func.count()).select_from(sub))}

    breakdown = None
    if by is not None:
        label, tracked = next((label, tracked) for key, label, tracked in DIMENSIONS if key == by)
        on = applies[by]
        values = sorted({v for stage in on for v in counts[stage] if v is not None}, key=str)
        names = await _labels(db, by, values) if values else {}
        rows = [{"value": str(v), "label": names.get(v, str(v)), "counts": {stage: counts[stage].get(v, 0) for stage in on}} for v in values]
        # QA16-02: names are not unique (two programs or people can share one), so a repeated label carries its record's short id.
        repeated = {label for label, n in Counter(r["label"] for r in rows).items() if n > 1}
        for r in rows:
            if r["label"] in repeated:
                r["label"] = f"{r['label']} ({r['value'][:8]})"
        rows.sort(key=lambda r: (-sum(r["counts"].values()), r["label"].lower(), r["value"]))
        breakdown = {"by": by, "label": label, "tracked": tracked, "stages": on, "rows": rows, "unknown": {stage: counts[stage].get(None, 0) for stage in on}}

    return {
        "from_": start,
        "to": end,
        "as_of": now,
        "paths": [{"key": key, "label": label} for key, label in PATHS],
        "stages": [{"key": key, "label": label, "path": path, "definition": text, "value": sum(counts[key].values())} for key, label, path, text, _ in stages],
        "dimensions": [{"key": key, "label": label, "tracked": tracked, "stages": applies[key]} for key, label, tracked in DIMENSIONS],
        "breakdown": breakdown,
    }
