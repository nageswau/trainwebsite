"""bdm-021 (DEC-SCOPE-086, spec §2-§4): a College organization's student funnel and revenue, computed live from attributed records (D5b).

Read-only; nothing here writes. `S` is the set of students linked to the organization's leads (bdm-017's explicit conversion link;
L9 makes it one lead per student, so a student counts for one organization only). Each stage counts distinct students by its own
definition (B6). Only aggregates leave this module (AC3).
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, Select, and_, cast, distinct, exists, func, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.payments import PAID_STATUSES
from app.models import (
    AgentOrg,
    AgentStudent,
    BdmActivity,
    BdmAppointment,
    BdmAppointmentEvent,
    BdmMou,
    BdmMouEvent,
    BdmOrganization,
    BdmTask,
    BdmTrip,
    Certificate,
    Enquiry,
    Enrollment,
    JobApplication,
    JobOffer,
    OverseasApplication,
    Payment,
    PlacementProfile,
    School,
    SchoolCareerRecord,
    SchoolPsychometricRecord,
    SchoolStudent,
    User,
)
from app.schemas import COUNTED_CAREER_STATUSES
from app.services.agent_applications import OVERSEAS_APPLICATION_STAGES, WITHDRAWN
from app.services.agent_dashboard import funnel_columns
from app.services.agent_deposits import REFERENCE_TYPE as AGENT_DEPOSIT
from app.services.agent_network import NETWORK_APPLICATION, members_of
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import IST

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


def college_columns(org_id) -> dict:
    """The funnel and fee figures of one College organization as scalar subqueries over `S`. `org_id` is a value, or (bdm-024's master
    view) the correlated `BdmOrganization.id` of an outer SELECT, so the panel and the master view run the same SQL."""
    students = select(Enquiry.converted_user_id).where(Enquiry.bdm_organization_id == org_id, Enquiry.converted_user_id.is_not(None))

    def distinct_students(column, *where):
        return select(func.count(distinct(column))).where(column.in_(students), *where).scalar_subquery()

    return {
        "leads": select(func.count()).select_from(Enquiry).where(Enquiry.bdm_organization_id == org_id).scalar_subquery(),
        "registrations": distinct_students(Enquiry.converted_user_id, Enquiry.bdm_organization_id == org_id),
        "training": distinct_students(Enrollment.student_id, Enrollment.status != "withdrawn"),
        "certification": distinct_students(Certificate.student_id, Certificate.status == "issued"),
        "placement": select(func.count(distinct(JobApplication.student_id)))
        .join(JobOffer, JobOffer.application_id == JobApplication.id)
        .where(JobApplication.student_id.in_(students), JobOffer.status.in_(ACCEPTED_OFFER))
        .scalar_subquery(),
        "fees": select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.user_id.in_(students), *fee_filter()).scalar_subquery(),
    }


def fee_filter() -> list:
    """R-1 (D17): paid INR payments, never an agent deposit (pass-through)."""
    return [Payment.status.in_(PAID_STATUSES), Payment.currency == CURRENCY, Payment.reference_type != AGENT_DEPOSIT]


async def college_business(db: AsyncSession, org: BdmOrganization, with_revenue: bool) -> dict:
    """One SELECT of scalar subqueries over `S` -- a constant query count whatever the organization's size."""
    query = select(*college_columns(org.id).values())
    leads, registrations, training, certification, placement, fees = (await db.execute(query)).one()
    counts = {"contacted": leads, "leads": leads, "registrations": registrations, "training": training, "certification": certification, "placement": placement}
    funnel = [{"key": k, "label": label, "definition": d, "tracked": k in counts, "count": counts.get(k)} for k, label, d in STAGES]
    revenue = None
    if with_revenue:
        amounts = {"training": Decimal(str(fees)).quantize(Decimal("0.01"))}
        revenue = {"lines": [{"key": k, "label": label, "definition": d, "tracked": k in amounts, "amount": amounts.get(k)} for k, label, d in REVENUE_LINES]}
    return {"organization_id": org.id, "currency": CURRENCY, "funnel": funnel, "revenue": revenue}


# bdm-022 (DEC-SCOPE-110, spec §1-§3): a linked Agent organization's Agent -> Students -> ... -> Revenue chain (Appendix B A-01...A-06).
# The figures are the agency Master dashboard's (`funnel_columns`), scoped to the organization's members as AGN-022 scopes it (B3).
AGENT_STEPS = (
    ("students", "Students", "Active students of the agency.", "students"),
    ("applications", "Applications", "The agency's applications, except withdrawn ones.", "applications"),
    ("offers", "Offers", "Applications that reached the offer stage or have an offer recorded, including ones withdrawn after the offer.",
     "offers"),
    ("visa", "Visa", "Applications with an approved visa.", "visa_approvals"),
    ("enrolled", "Enrolled", "Applications at the Enrolled stage.", "enrollments"),
    ("revenue", "Revenue", "Not tracked: deposits pass through to universities and commission is not shown to BDMs (awaiting a decision).",
     None),
)
EARLIER_STAGES = "earlier_stage_names"  # B6: a legacy status (e.g. `offer_received`) still counts, under its own row


def _stage_label(status: str) -> str:
    """The agency screens' wording (`stageLabel` in lib/agentApplications.ts): underscores to spaces, first letter capital."""
    return status.replace("_", " ").capitalize()


async def agent_performance(db: AsyncSession, org: BdmOrganization) -> dict:
    """Unlinked: `linked: false` and nothing else. Linked: the agency, one SELECT of the shared scalar subqueries and one grouped count
    of applications by stage -- a constant query count whatever the agency's size. Only aggregates leave (AC4)."""
    now = datetime.now(UTC)
    if org.agent_org_id is None:
        return {"organization_id": org.id, "linked": False, "agency": None, "steps": [], "applications_by_stage": [], "visa_applications": None,
                "as_of": now}
    agency = await db.get_one(AgentOrg, org.agent_org_id)
    members = members_of(agency.id)
    apps = [OverseasApplication.agent_id.in_(members), NETWORK_APPLICATION]
    columns = funnel_columns([AgentStudent.agent_id.in_(members)], apps)
    figures = (await db.execute(select(*(column.label(key) for key, column in columns.items())))).one()._mapping
    by_status = dict((await db.execute(select(OverseasApplication.status, func.count()).where(*apps).group_by(OverseasApplication.status))).all())
    stages = [{"key": s, "label": _stage_label(s), "count": by_status.pop(s, 0)} for s in (*OVERSEAS_APPLICATION_STAGES, WITHDRAWN)]
    if by_status:
        stages.append({"key": EARLIER_STAGES, "label": "Earlier stage names", "count": sum(by_status.values())})
    steps = [{"key": key, "label": label, "definition": definition, "tracked": source is not None, "count": figures[source] if source else None}
             for key, label, definition, source in AGENT_STEPS]
    return {
        "organization_id": org.id,
        "linked": True,
        "agency": {"name": agency.name, "prefix": agency.prefix, "status": agency.status},
        "steps": steps,
        "applications_by_stage": stages,
        "visa_applications": figures["visa_applications"],
        "as_of": now,
    }


# bdm-015 (DEC-SCOPE-099, spec §3): the daily activity report's counts -- Appendix B M-rows for one BDM and one IST day. Every builder
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


def _owned(column, bdm):
    """`bdm` is one BDM's id, or (bdm-023) a sub-select of a team's BDM ids."""
    return column.in_(bdm) if isinstance(bdm, Select) else column == bdm


def _completed(bdm, start, end) -> list:
    return [_owned(BdmAppointment.bdm_user_id, bdm), BdmAppointment.status == "completed", BdmAppointment.starts_at >= start, BdmAppointment.starts_at < end]


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


def _of_type(org_type: str):
    return select(BdmOrganization.id).where(BdmOrganization.org_type == org_type)


def _mou_moved_to(status: str, org_type: str | None = None):
    """M-09 / M-11: MoU events by the BDM that moved a MoU into `status` (an event that kept it there is not a transition); bdm-016's
    K-A04 limits M-11 to agent organizations."""
    def build(bdm, start, end):
        where = [_owned(BdmMouEvent.actor_user_id, bdm), BdmMouEvent.to_status == status, BdmMouEvent.from_status.is_distinct_from(status),
                 BdmMouEvent.created_at >= start, BdmMouEvent.created_at < end]
        if org_type:
            where.append(BdmMouEvent.mou_id.in_(select(BdmMou.id).where(BdmMou.organization_id.in_(_of_type(org_type)))))
        return _count(BdmMouEvent, *where)
    return build


def _travel(bdm, start, end):
    return _count(BdmTrip, BdmTrip.bdm_user_id == bdm, BdmTrip.travel_status == "completed", BdmTrip.completed_at >= start,
                  BdmTrip.completed_at < end)


def _leads(bdm, start, end):
    return _count(Enquiry, Enquiry.bdm_user_id == bdm, Enquiry.created_at >= start, Enquiry.created_at < end)


def _follow_ups(bdm, start, end):
    return _count(BdmTask, BdmTask.assignee_user_id == bdm, BdmTask.kind == "follow_up", BdmTask.status == "done",
                  BdmTask.completed_at >= start, BdmTask.completed_at < end)


def _new_orgs(org_type: str):
    """M-14: organizations of `org_type` the BDM created in the window."""
    def build(bdm, start, end):
        return _count(BdmOrganization, BdmOrganization.created_by_user_id == bdm, BdmOrganization.org_type == org_type,
                      BdmOrganization.created_at >= start, BdmOrganization.created_at < end)
    return build


def _linked_schools(bdm):
    return select(BdmOrganization.school_id).where(BdmOrganization.assigned_bdm_user_id == bdm, BdmOrganization.school_id.is_not(None))


def _students_generated(bdm, start, end):
    """M-27 (M-22 for the day): students added in the Schools linked to the BDM's organizations."""
    return _count(SchoolStudent, SchoolStudent.school_id.in_(_linked_schools(bdm)), SchoolStudent.created_at >= start, SchoolStudent.created_at < end)


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
    "new_prospects": ("Agent organizations you created that day.", _new_orgs("agent")),
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


# bdm-016 (DEC-SCOPE-103, spec §3): the monthly KPI catalogue for targets -- Appendix B.3 K-rows, each one M-row over the IST month. The
# bdm-015 builders take any half-open instant window, so they are reused as is; the rows below are the M-rows only a month needs.

def month_range(month: date) -> tuple[datetime, datetime]:
    """An IST calendar month (`month` is its first day) as a half-open instant range."""
    following = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    return datetime.combine(month, time.min, tzinfo=IST), datetime.combine(following, time.min, tzinfo=IST)


def _ist_day(instant: datetime) -> date:
    return instant.astimezone(IST).date()


def _last_day(end: datetime) -> date:
    return _ist_day(end - timedelta(days=1))


def _meetings_at(org_type: str):
    """M-06 filtered by the organization's type."""
    def build(bdm, start, end):
        return _count(BdmAppointment, *_completed(bdm, start, end), BdmAppointment.organization_id.in_(_of_type(org_type)))
    return build


def _active_schools(bdm, start, end):
    """M-17 (R12): linked Schools with a tier that has not expired by the month's last day -- or by today while the month runs."""
    as_of = func.least(_last_day(end), cast(func.timezone(IST.key, func.now()), Date))
    return _count(School, School.id.in_(_linked_schools(bdm)), School.tier.is_not(None),
                  or_(School.tier_valid_until.is_(None), School.tier_valid_until >= as_of))


def _dated(day_column, created_column, start, end):
    """R11: in the month by the record's own date, or by when it was created when it has none."""
    return or_(and_(day_column.is_not(None), day_column >= _ist_day(start), day_column <= _last_day(end)),
               and_(day_column.is_(None), created_column >= start, created_column < end))


def _students_served(record, where):
    """M-23 / M-24 (D31): distinct students of the BDM's linked Schools with a matching record in the window."""
    def build(bdm, start, end):
        students = select(SchoolStudent.id).where(SchoolStudent.school_id.in_(_linked_schools(bdm)))
        return select(func.count(distinct(record.school_student_id))).where(record.school_student_id.in_(students), *where(start, end)).scalar_subquery()
    return build


_career_guidance = _students_served(SchoolCareerRecord, lambda start, end: (
    SchoolCareerRecord.record_type == "guidance_session",
    or_(SchoolCareerRecord.status.is_(None), SchoolCareerRecord.status.in_(COUNTED_CAREER_STATUSES)),  # ENH-026 C5 `counts_as_completed`
    _dated(SchoolCareerRecord.completed_on, SchoolCareerRecord.created_at, start, end),
))
_psychometric_tests = _students_served(SchoolPsychometricRecord, lambda start, end: (
    SchoolPsychometricRecord.status == "completed",
    _dated(SchoolPsychometricRecord.test_date, SchoolPsychometricRecord.created_at, start, end),
))


def _attributed(bdm):
    """R10: the student accounts converted from the leads the BDM entered."""
    return select(Enquiry.converted_user_id).where(Enquiry.bdm_user_id == bdm, Enquiry.converted_user_id.is_not(None))


def _training_registrations(bdm, start, end):
    """M-28: attributed students with an enrollment created in the window (each once)."""
    return select(func.count(distinct(Enrollment.student_id))).where(
        Enrollment.student_id.in_(_attributed(bdm)), Enrollment.created_at >= start, Enrollment.created_at < end).scalar_subquery()


def _placement_candidates(bdm, start, end):
    """M-30: attributed students whose placement profile was created in the window (one profile per student)."""
    return _count(PlacementProfile, PlacementProfile.student_id.in_(_attributed(bdm)), PlacementProfile.created_at >= start,
                  PlacementProfile.created_at < end)


_NO_AGENT_LINK = "Not tracked yet: agent onboarding links arrive with the agent onboarding handover."
_NO_AGENT_CRM = "Not tracked yet: Agent CRM records are not linked to BDM organizations."

# key -> (label, definition, builder; None = not tracked). The definition goes out with every KPI, so the page shows the same words.
TARGET_METRICS = {
    "college_meetings": ("College Meetings", "Your appointments at colleges completed this month.", _meetings_at("college")),
    "agent_meetings": ("Agent Meetings", "Your appointments at agents completed this month.", _meetings_at("agent")),
    "new_colleges": ("New Colleges", "College organizations you created this month.", _new_orgs("college")),
    "new_agents": ("New Agents", _NO_AGENT_LINK, None),
    "appointments": ("Appointments", "Appointments you booked this month, except ones cancelled the same month.", _appointments_fixed),
    "mous": ("MoUs", "MoUs you moved to Signed this month.", _mou_moved_to("signed")),
    "student_leads": ("Student Leads", "Student leads you entered this month.", _leads),
    "new_agent_leads": ("New Agent Leads", "Agent organizations you created this month.", _new_orgs("agent")),
    "agreements_signed": ("Agreements Signed", "Agent MoUs you moved to Signed this month.", _mou_moved_to("signed", "agent")),
    "active_agents": ("Active Agents", _NO_AGENT_LINK, None),
    "agent_students": ("Agent Students", _NO_AGENT_CRM, None),
    "applications": ("Applications", _NO_AGENT_CRM, None),
    "enrollments": ("Enrollments", _NO_AGENT_CRM, None),
    "schools_contacted": ("Schools Contacted", "Schools with an activity you logged or a meeting you completed this month.", _contacted("school")),
    "school_meetings": ("School Meetings", "Your appointments at schools completed this month.", _meetings_at("school")),
    "school_presentations": ("Presentations", "Your career guidance, psychometric and profile building presentations completed this month.",
                             _meetings(*_SCHOOL_PRESENTATIONS)),
    "proposals": ("Proposals", "MoUs you moved to Proposal Sent this month.", _mou_moved_to("proposal_sent")),
    "active_schools": ("Active Schools", "Schools linked to your organizations with a tier still valid at the month's end (today, for this month).",
                       _active_schools),
    "students_onboarded": ("Students Onboarded", "Students added this month in the schools linked to your organizations.", _students_generated),
    "career_guidance": ("Career Guidance", "Students in your linked schools with a career guidance session completed this month.", _career_guidance),
    "psychometric_tests": ("Psychometric Tests", "Students in your linked schools with a psychometric test completed this month.", _psychometric_tests),
    "colleges_contacted": ("Colleges Contacted", "Colleges with an activity you logged or a meeting you completed this month.", _contacted("college")),
    "meetings": ("Meetings", "Your appointments completed this month.", _meetings()),
    "college_presentations": ("Presentations", "Your IT training presentations completed this month.", _meetings("it_training_presentation")),
    "course_promotions": ("Course Promotions", "Your course promotion appointments completed this month.", _meetings("course_promotion")),
    "training_registrations": ("Training Registrations", "Students from your leads who enrolled in training this month.", _training_registrations),
    "internship_students": ("Internship Students", "Not tracked: internships are not recorded in EduSphere.", None),
    "placement_candidates": ("Placement Candidates", "Students from your leads who became placement candidates this month.", _placement_candidates),
}

# R1: the type's own source list (Agent / School / College §A), then the §12 common list; a common KPI identical to one already listed
# (same metric, same filter) is shown once.
_COMMON = ("college_meetings", "agent_meetings", "new_colleges", "new_agents", "appointments", "mous", "student_leads")
_OWN = {
    "agent": ("new_agent_leads", "agent_meetings", "new_agents", "agreements_signed", "active_agents", "agent_students", "applications", "enrollments"),
    "school": ("schools_contacted", "school_meetings", "school_presentations", "proposals", "mous", "active_schools", "students_onboarded",
               "career_guidance", "psychometric_tests"),
    "college": ("colleges_contacted", "meetings", "college_presentations", "mous", "course_promotions", "student_leads", "training_registrations",
                "internship_students", "placement_candidates"),
}
TARGET_KPIS: dict[str, tuple[str, ...]] = {bdm_type: tuple(dict.fromkeys(own + _COMMON)) for bdm_type, own in _OWN.items()}


async def monthly_counts(db: AsyncSession, bdm_user_id: UUID, bdm_type: str, month: date, *, future: bool = False) -> list[dict]:
    """One SELECT of scalar subqueries for the BDM's IST month; none for a month that has not started (R6: achieved is null)."""
    keys = TARGET_KPIS[bdm_type]
    tracked = [key for key in keys if TARGET_METRICS[key][2] is not None]
    values: dict = {}
    if not future:
        start, end = month_range(month)
        result = (await db.execute(select(*(TARGET_METRICS[key][2](bdm_user_id, start, end) for key in tracked)))).one()
        values = dict(zip(tracked, result, strict=True))
    return [{"key": key, "label": TARGET_METRICS[key][0], "definition": TARGET_METRICS[key][1], "tracked": TARGET_METRICS[key][2] is not None,
             "achieved": values.get(key)} for key in keys]
