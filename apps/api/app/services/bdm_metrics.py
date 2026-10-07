"""bdm-021 (DEC-SCOPE-086, spec §2-§4): a College organization's student funnel and revenue, computed live from attributed records (D5b).

Read-only; nothing here writes. `S` is the set of students linked to the organization's leads (bdm-017's explicit conversion link;
L9 makes it one lead per student, so a student counts for one organization only). Each stage counts distinct students by its own
definition (B6). Only aggregates leave this module (AC3).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import distinct, exists, func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.payments import PAID_STATUSES
from app.models import (
    BdmActivity,
    BdmAppointment,
    BdmAppointmentEvent,
    BdmMouEvent,
    BdmOrganization,
    BdmTask,
    BdmTrip,
    Certificate,
    Enquiry,
    Enrollment,
    JobApplication,
    JobOffer,
    Payment,
    SchoolStudent,
    User,
)
from app.services.agent_deposits import REFERENCE_TYPE as AGENT_DEPOSIT
from app.services.bdm_activities import day_range

CURRENCY = "INR"
ACCEPTED_OFFER = ("accepted", "joined")  # workflows.update_job_offer marks the application hired on these

# (key, label, definition) -- the written definitions of spec §3, sent with every response so the panel shows the same words.
STAGES = (
    ("contacted", "Contacted", "Leads entered by BDMs for this organization (students contacted = leads entered)."),
    ("leads", "Leads", "Student enquiries attributed to this organization."),
    ("registrations", "Registrations", "Students whose account is linked to one of these leads."),
    ("training", "Training", "Registered students with at least one enrollment that is not withdrawn."),
    ("certification", "Certification", "Registered students with at least one issued certificate."),
    ("internship", "Internship", "Internships are not recorded in EduSphere."),
    ("placement", "Placement", "Registered students with an accepted or joined job offer."),
)
REVENUE_LINES = (
    ("training", "Training fees", "Paid INR payments of the registered students; pending, failed and refunded payments are excluded."),
    ("internship", "Internship", "No internship revenue is recorded in EduSphere."),
    ("placement", "Placement", "No placement revenue is recorded in EduSphere."),
    ("other", "Other", "No other revenue is recorded in EduSphere."),
)


def show_revenue(user: User, org: BdmOrganization) -> bool:
    """B3: the assigned BDM, a manager (load_scoped already limited them to their team) and super_admin."""
    return user.role in ("bdm_manager", "super_admin") or org.assigned_bdm_user_id == user.id


async def college_business(db: AsyncSession, org: BdmOrganization, with_revenue: bool) -> dict:
    """One SELECT of scalar subqueries over `S` -- a constant query count whatever the organization's size."""
    students = select(Enquiry.converted_user_id).where(Enquiry.bdm_organization_id == org.id, Enquiry.converted_user_id.is_not(None))

    def distinct_students(column, *where):
        return select(func.count(distinct(column))).where(column.in_(students), *where).scalar_subquery()

    query = select(
        select(func.count()).select_from(Enquiry).where(Enquiry.bdm_organization_id == org.id).scalar_subquery(),
        distinct_students(Enquiry.converted_user_id, Enquiry.bdm_organization_id == org.id),
        distinct_students(Enrollment.student_id, Enrollment.status != "withdrawn"),
        distinct_students(Certificate.student_id, Certificate.status == "issued"),
        select(func.count(distinct(JobApplication.student_id)))
        .join(JobOffer, JobOffer.application_id == JobApplication.id)
        .where(JobApplication.student_id.in_(students), JobOffer.status.in_(ACCEPTED_OFFER))
        .scalar_subquery(),
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(
            Payment.user_id.in_(students),
            Payment.status.in_(PAID_STATUSES),
            Payment.currency == CURRENCY,
            Payment.reference_type != AGENT_DEPOSIT,
        )
        .scalar_subquery(),
    )
    leads, registrations, training, certification, placement, fees = (await db.execute(query)).one()
    counts = {"contacted": leads, "leads": leads, "registrations": registrations, "training": training, "certification": certification, "placement": placement}
    funnel = [{"key": k, "label": label, "definition": d, "tracked": k in counts, "count": counts.get(k)} for k, label, d in STAGES]
    revenue = None
    if with_revenue:
        amounts = {"training": Decimal(str(fees)).quantize(Decimal("0.01"))}
        revenue = {"lines": [{"key": k, "label": label, "definition": d, "tracked": k in amounts, "amount": amounts.get(k)} for k, label, d in REVENUE_LINES]}
    return {"organization_id": org.id, "currency": CURRENCY, "funnel": funnel, "revenue": revenue}


# bdm-015 (DEC-SCOPE-096, spec §3): the daily activity report's counts -- Appendix B M-rows for one BDM and one IST day. Every builder
# returns a scalar subquery over a half-open instant window [start, end), so a monthly window (bdm-016/023/024) can reuse them as is.
# A not-tracked count has no builder: it is labelled, never 0 (R10).

_SCHOOL_PRESENTATIONS = ("career_guidance_presentation", "psychometric_presentation", "profile_building_presentation")


def _count(model, *where):
    return select(func.count()).select_from(model).where(*where).scalar_subquery()


def _activities(bdm, start, end, channel: str, direction: str | None = None):
    where = [BdmActivity.bdm_user_id == bdm, BdmActivity.occurred_at >= start, BdmActivity.occurred_at < end, BdmActivity.channel == channel]
    if direction:
        where.append(BdmActivity.direction == direction)
    return _count(BdmActivity, *where)


def _completed(bdm, start, end) -> list:
    return [BdmAppointment.bdm_user_id == bdm, BdmAppointment.status == "completed", BdmAppointment.starts_at >= start, BdmAppointment.starts_at < end]


def _meetings(*types: str):
    """M-06 (no types) and its typed variants M-10, M-18, M-20, M-25, M-26: own appointments completed in the window."""
    def build(bdm, start, end):
        return _count(BdmAppointment, *_completed(bdm, start, end), *([BdmAppointment.appointment_type.in_(types)] if types else []))
    return build


def _contacted(org_type: str):
    """M-05: distinct organizations of `org_type` with an own activity or an own completed appointment in the window."""
    def build(bdm, start, end):
        touched = union(
            select(BdmActivity.organization_id).where(BdmActivity.bdm_user_id == bdm, BdmActivity.occurred_at >= start, BdmActivity.occurred_at < end),
            select(BdmAppointment.organization_id).where(*_completed(bdm, start, end)),
        )
        return _count(BdmOrganization, BdmOrganization.org_type == org_type, BdmOrganization.id.in_(touched))
    return build


def _appointments_fixed(bdm, start, end):
    """M-07: booked in the window, minus those cancelled within the same window."""
    cancelled = select(BdmAppointmentEvent.id).where(
        BdmAppointmentEvent.appointment_id == BdmAppointment.id, BdmAppointmentEvent.to_status == "cancelled",
        BdmAppointmentEvent.created_at >= start, BdmAppointmentEvent.created_at < end,
    )
    return _count(BdmAppointment, BdmAppointment.bdm_user_id == bdm, BdmAppointment.created_at >= start, BdmAppointment.created_at < end,
                  ~exists(cancelled))


def _mou_moved_to(status: str):
    """M-09 / M-11: MoU events by the BDM that moved a MoU into `status` (an event that kept it there is not a transition)."""
    def build(bdm, start, end):
        return _count(BdmMouEvent, BdmMouEvent.actor_user_id == bdm, BdmMouEvent.to_status == status,
                      BdmMouEvent.from_status.is_distinct_from(status), BdmMouEvent.created_at >= start, BdmMouEvent.created_at < end)
    return build


def _travel(bdm, start, end):
    return _count(BdmTrip, BdmTrip.bdm_user_id == bdm, BdmTrip.travel_status == "completed", BdmTrip.completed_at >= start,
                  BdmTrip.completed_at < end)


def _leads(bdm, start, end):
    return _count(Enquiry, Enquiry.bdm_user_id == bdm, Enquiry.created_at >= start, Enquiry.created_at < end)


def _follow_ups(bdm, start, end):
    return _count(BdmTask, BdmTask.assignee_user_id == bdm, BdmTask.kind == "follow_up", BdmTask.status == "done",
                  BdmTask.completed_at >= start, BdmTask.completed_at < end)


def _new_prospects(bdm, start, end):
    return _count(BdmOrganization, BdmOrganization.created_by_user_id == bdm, BdmOrganization.org_type == "agent",
                  BdmOrganization.created_at >= start, BdmOrganization.created_at < end)


def _students_generated(bdm, start, end):
    """M-27 (M-22 for the day): students added in the Schools linked to the BDM's organizations."""
    linked = select(BdmOrganization.school_id).where(BdmOrganization.assigned_bdm_user_id == bdm, BdmOrganization.school_id.is_not(None))
    return _count(SchoolStudent, SchoolStudent.school_id.in_(linked), SchoolStudent.created_at >= start, SchoolStudent.created_at < end)


# key -> (definition, builder; None = not tracked). The definition goes out with every count, so the page shows the same words.
DAILY_METRICS = {
    "calls_made": ("Outgoing calls you logged that day.", lambda b, s, e: _activities(b, s, e, "call", "outbound")),
    "school_visits": ("Visits you logged that day.", lambda b, s, e: _activities(b, s, e, "visit")),
    "colleges_contacted": ("Colleges with an activity you logged or a meeting you completed that day.", _contacted("college")),
    "agents_contacted": ("Agents with an activity you logged or a meeting you completed that day.", _contacted("agent")),
    "schools_contacted": ("Schools with an activity you logged or a meeting you completed that day.", _contacted("school")),
    "meetings_completed": ("Your appointments completed that day.", _meetings()),
    "appointments_fixed": ("Appointments you booked that day, except ones cancelled the same day.", _appointments_fixed),
    "travel_completed": ("Your trips marked completed that day.", _travel),
    "proposals_sent": ("MoUs you moved to Proposal Sent that day.", _mou_moved_to("proposal_sent")),
    "mous_discussed": ("Your MoU or agreement discussions completed that day.", _meetings("mou_discussion", "agreement_discussion")),
    "mous_signed": ("MoUs you moved to Signed that day.", _mou_moved_to("signed")),
    "student_leads": ("Student leads you entered that day.", _leads),
    "follow_ups_completed": ("Follow-ups you marked done that day.", _follow_ups),
    "new_prospects": ("Agent organizations you created that day.", _new_prospects),
    "new_agents": ("Not tracked yet: agent onboarding links arrive with the agent onboarding handover.", None),
    "agent_training": ("Your product training sessions completed that day.", _meetings("product_training")),
    "applications_generated": ("Not tracked yet: Agent CRM applications are not linked to BDM organizations.", None),
    "enrollments_generated": ("Not tracked yet: Agent CRM enrollments are not linked to BDM organizations.", None),
    "presentations": ("Your career guidance, psychometric and profile building presentations completed that day.",
                      _meetings(*_SCHOOL_PRESENTATIONS)),
    "students_generated": ("Students added that day in the schools linked to your organizations.", _students_generated),
    "career_guidance_sessions": ("Your career guidance presentations completed that day.", _meetings("career_guidance_presentation")),
    "psychometric_sessions": ("Your psychometric presentations completed that day.", _meetings("psychometric_presentation")),
}

# R1: per BDM type, the source's own list, order and wording (College = §11 common; Agent §G; School §G).
DAILY_REPORTS: dict[str, tuple[tuple[str, str], ...]] = {
    "college": (
        ("calls_made", "Calls made"), ("colleges_contacted", "Colleges contacted"), ("agents_contacted", "Agents contacted"),
        ("meetings_completed", "Meetings completed"), ("appointments_fixed", "Appointments fixed"), ("travel_completed", "Travel completed"),
        ("proposals_sent", "Proposals sent"), ("mous_discussed", "MoUs discussed"), ("mous_signed", "MoUs signed"),
        ("student_leads", "Student leads generated"), ("follow_ups_completed", "Follow-ups completed"),
    ),
    "agent": (
        ("calls_made", "Calls made"), ("agents_contacted", "Agents contacted"), ("meetings_completed", "Meetings"),
        ("new_prospects", "New prospects"), ("new_agents", "New agents"), ("mous_signed", "Agreements"), ("agent_training", "Agent training"),
        ("follow_ups_completed", "Follow-ups"), ("student_leads", "Student leads generated"),
        ("applications_generated", "Applications generated"), ("enrollments_generated", "Enrollments generated"),
    ),
    "school": (
        ("schools_contacted", "Schools contacted"), ("calls_made", "Calls"), ("meetings_completed", "Meetings"),
        ("school_visits", "School visits"), ("presentations", "Presentations"), ("proposals_sent", "Proposals"), ("mous_signed", "MoUs"),
        ("follow_ups_completed", "Follow-ups"), ("students_generated", "Students generated"),
        ("career_guidance_sessions", "Career guidance sessions"), ("psychometric_sessions", "Psychometric sessions"),
    ),
}


async def daily_counts(db: AsyncSession, bdm_user_id: UUID, bdm_type: str, day: date) -> list[dict]:
    """One SELECT of scalar subqueries for the BDM's IST day -- a constant query count whatever the data size."""
    start, end = day_range(day)
    rows = DAILY_REPORTS[bdm_type]
    tracked = [key for key, _ in rows if DAILY_METRICS[key][1] is not None]
    result = (await db.execute(select(*(DAILY_METRICS[key][1](bdm_user_id, start, end) for key in tracked)))).one()
    values = dict(zip(tracked, result, strict=True))
    return [{"key": key, "label": label, "definition": DAILY_METRICS[key][0], "tracked": key in values, "count": values.get(key)}
            for key, label in rows]
