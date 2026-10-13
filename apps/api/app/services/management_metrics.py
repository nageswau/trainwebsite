"""mgmt-003 (Management Appendix B): the single owner of the Command Center's figures. It reads the module tables live and keeps no
copies. The business snapshot S1-S15 (spec MS1-MS17) is one SELECT of fifteen scalar subqueries, so the query count is fixed at one
and every figure is read from the same moment."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import ScalarSelect, and_, distinct, exists, func, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AcademicYear,
    AgentOrg,
    AgentOrgMember,
    AgentStudent,
    ApplicationDeposit,
    ApplicationStatusHistory,
    Batch,
    Candidate,
    Company,
    Country,
    DocumentRequest,
    Enrollment,
    OverseasApplication,
    OverseasCourse,
    RecruiterProfile,
    School,
    SchoolStudent,
    StudentDocument,
    University,
    User,
    VisaCase,
)
from app.partnership_stages import GROUPS
from app.recruiter_stages import ORDER as COMPANY_STAGES
from app.services import application_filters
from app.services.agent_applications import OFFER_COUNTED_STATUSES, OVERSEAS_APPLICATION_STAGES, WITHDRAWN, stage_label
from app.services.bdm_appointments import IST

# (Appendix B id, response key, the source's wording), in source order (EVID-017 §3).
SNAPSHOT: tuple[tuple[str, str, str], ...] = (
    ("S1", "total_students", "Total Students"),
    ("S2", "active_students", "Active Students"),
    ("S3", "it_training_students", "IT Training Students"),
    ("S4", "abroad_education_students", "Abroad Education Students"),
    ("S5", "agent_students", "Agent Students"),
    ("S6", "placement_students", "Placement Students"),
    ("S7", "active_agents", "Active Agents"),
    ("S8", "partner_schools", "Partner Schools"),
    ("S9", "university_partners", "University Partners"),
    ("S10", "partner_companies", "Partner Companies"),
    ("S11", "trainers", "Trainers"),
    ("S12", "counselors", "Counselors"),
    ("S13", "telecallers", "Telecallers"),
    ("S14", "bdms", "BDMs"),
    ("S15", "recruiters", "Recruiters"),
)

STUDENT_ROLES = ("it_student", "overseas_student")
UNIVERSITY_PARTNER_STAGES = tuple(key for key, group in GROUPS.items() if group == "partner")  # MS9: the upc-025 G1 rule
PARTNER_COMPANY_STAGES = COMPANY_STAGES[COMPANY_STAGES.index("interested") + 1 :]  # MS10: past "Interested"

active_student = and_(User.active.is_(True), User.role.in_(STUDENT_ROLES))
running_enrolment = and_(Enrollment.status != "withdrawn", Batch.status == "active")  # MS3: an enrolment in an active batch
live_application = OverseasApplication.status != WITHDRAWN
open_application = OverseasApplication.status.not_in((WITHDRAWN, "enrolled"))  # MS2: neither withdrawn nor already abroad
# MS5: an active student of an agency whose organisation is active (`agent_id` is any member of it, as AGN-001 scopes students).
agency_student = and_(
    AgentStudent.status == "active",
    exists().where(AgentOrgMember.user_id == AgentStudent.agent_id, AgentOrg.id == AgentOrgMember.org_id, AgentOrg.status == "active"),
)
login_less = and_(agency_student, AgentStudent.student_id.is_(None))  # MS1: a linked login is already counted as the user


def _count(*where, of=None) -> ScalarSelect:
    return select(func.count(distinct(of)) if of is not None else func.count()).where(*where).scalar_subquery()


def _staff(role: str) -> ScalarSelect:
    return _count(User.role == role, User.active.is_(True))


def _active_students() -> ScalarSelect:
    """MS2: three disjoint populations -- users, school students, login-less agency students -- each counted once."""
    enrolled = select(Enrollment.student_id).join(Batch, Batch.id == Enrollment.batch_id).where(running_enrolment)
    applying = select(OverseasApplication.student_id).where(open_application, OverseasApplication.student_id.is_not(None))
    users = _count(active_student, User.id.in_(union(enrolled, applying)))
    this_year = select(AcademicYear.id).where(AcademicYear.status == "active")
    school_applying = select(OverseasApplication.school_student_id).where(open_application)
    school = _count(or_(SchoolStudent.academic_year_id.in_(this_year), SchoolStudent.id.in_(school_applying)))
    agency = _count(login_less, AgentStudent.id.in_(select(OverseasApplication.agent_student_id).where(open_application)))
    return select(users + school + agency).scalar_subquery()


def _abroad_students() -> ScalarSelect:
    """MS4: one person per agency student, school student or user (in that order); a deactivated user's own applications drop out."""
    person = func.coalesce(OverseasApplication.agent_student_id, OverseasApplication.school_student_id, OverseasApplication.student_id)
    own_user_live = or_(
        OverseasApplication.agent_student_id.is_not(None),
        OverseasApplication.school_student_id.is_not(None),
        exists().where(User.id == OverseasApplication.student_id, User.active.is_(True)),
    )
    return _count(live_application, own_user_live, of=person)


async def snapshot(db: AsyncSession, today: date) -> dict[str, int]:
    """S1-S15 as `{key: count}` in `SNAPSHOT` order, `today` being the IST date (S8's tier validity)."""
    figures = {
        "total_students": select(_count(active_student) + _count(of=SchoolStudent.id) + _count(login_less)).scalar_subquery(),
        "active_students": _active_students(),
        "it_training_students": _count(running_enrolment, Batch.id == Enrollment.batch_id, User.id == Enrollment.student_id, User.active.is_(True), of=Enrollment.student_id),
        "abroad_education_students": _abroad_students(),
        "agent_students": _count(agency_student),
        "placement_students": _count(Candidate.opted_in.is_(True), Candidate.archived_at.is_(None), User.id == Candidate.user_id, User.active.is_(True)),
        "active_agents": _count(AgentOrg.status == "active"),
        "partner_schools": _count(School.tier.is_not(None), School.tier_valid_until >= today),
        "university_partners": _count(University.active.is_(True), University.lost_at.is_(None), University.stage.in_(UNIVERSITY_PARTNER_STAGES)),
        "partner_companies": _count(Company.archived_at.is_(None), Company.lost_at.is_(None), Company.stage.in_(PARTNER_COMPANY_STAGES)),
        "trainers": _staff("trainer"),
        "counselors": _staff("counselor"),
        "telecallers": _staff("telecaller"),
        "bdms": _staff("bdm"),
        "recruiters": _count(User.role == "placement_team", User.active.is_(True), RecruiterProfile.user_id == User.id, of=User.id),
    }
    row = (await db.execute(select(*(query.label(key) for key, query in figures.items())))).one()
    return {key: int(row._mapping[key]) for _, key, _ in SNAPSHOT}


# --- mgmt-024 (§20, Appendix B "Funnels", spec MF1-MF18): the application funnel --------------------------------------------------

# (key, the source's wording, tracked), in source order (EVID-017 §20). M9: three stages have no data and say so, never 0.
FUNNEL: tuple[tuple[str, str, bool], ...] = (
    ("created", "Applications Created", True),
    ("documents_complete", "Documents Complete", True),
    ("submitted", "Submitted", True),
    ("under_review", "Under Review", False),
    ("offer", "Offer", True),
    ("accepted", "Accepted", False),
    ("deposit", "Deposit", True),
    ("cas_coe", "CAS/COE", False),
    ("visa", "Visa", True),
    ("visa_approved", "Visa Approved", True),
    ("enrollment", "Enrollment", True),
)
FUNNEL_STAFF_ROLES = ("super_admin", "overseas_admin", "counselor")  # MF13: the EduSphere staff who move an application on
DEPOSIT_REACHED = ("paid", "remitted")  # MF7: Appendix B literally; a refunded deposit is not counted


@dataclass(frozen=True)
class ApplicationFunnelFilters:
    """MF2/MF12: every filter is optional and they AND together. `agency` / `counselor` are an id or "none" (application_filters)."""

    date_from: date | None = None
    date_to: date | None = None
    agency: UUID | str | None = None
    counselor: UUID | str | None = None
    country: UUID | None = None
    university: UUID | None = None
    course: UUID | None = None
    intake: str | None = None
    staff: UUID | None = None
    status: str | None = None


def _of_application(model) -> bool:
    return model.application_id == OverseasApplication.id


# MF4: the application's own documents are all verified (at least one), and its agency student has no open document request.
_documents_complete = and_(
    exists().where(_of_application(StudentDocument)),
    ~exists().where(_of_application(StudentDocument), StudentDocument.verification_status != "verified"),
    ~exists().where(DocumentRequest.agent_student_id == OverseasApplication.agent_student_id, DocumentRequest.status == "open"),
)
# The computed stages and the withdrawn count (MF11), each a predicate on one application; None = every application.
FUNNEL_COUNTS = {
    "created": None,
    "documents_complete": _documents_complete,
    "submitted": OverseasApplication.submitted_on.is_not(None),  # MF5
    "offer": or_(OverseasApplication.status.in_(OFFER_COUNTED_STATUSES), OverseasApplication.offer_type.is_not(None)),  # MF6: O5
    "deposit": exists().where(_of_application(ApplicationDeposit), ApplicationDeposit.status.in_(DEPOSIT_REACHED)),
    "visa": exists().where(_of_application(VisaCase)),  # MF8
    "visa_approved": exists().where(_of_application(VisaCase), VisaCase.decision == "approved"),
    "enrollment": OverseasApplication.status == "enrolled",  # MF9
    "withdrawn": OverseasApplication.status == WITHDRAWN,
}


def _ist_start(day: date) -> datetime:
    return datetime.combine(day, time.min, IST)


def _funnel_where(filters: ApplicationFunnelFilters) -> list:
    where = []
    if filters.date_from:
        where.append(OverseasApplication.created_at >= _ist_start(filters.date_from))
    if filters.date_to:
        where.append(OverseasApplication.created_at < _ist_start(filters.date_to + timedelta(days=1)))
    if filters.country:
        where.append(OverseasApplication.university_id.in_(select(University.id).where(University.country_id == filters.country)))
    if filters.university:
        where.append(OverseasApplication.university_id == filters.university)
    if filters.course:
        where.append(OverseasApplication.course_id == filters.course)
    if filters.intake:
        where.append(OverseasApplication.intake == filters.intake)
    if filters.staff:
        where.append(exists().where(_of_application(ApplicationStatusHistory), ApplicationStatusHistory.changed_by_id == filters.staff))
    if filters.status:
        where.append(OverseasApplication.status == filters.status)
    return where


async def applications(db: AsyncSession, filters: ApplicationFunnelFilters) -> dict[str, int]:
    """`{key: count}` of `FUNNEL_COUNTS` over the filtered applications -- one SELECT (MF15)."""
    counts = [(func.count() if rule is None else func.count().filter(rule)).label(key) for key, rule in FUNNEL_COUNTS.items()]
    stmt = select(*counts).select_from(OverseasApplication).where(*_funnel_where(filters))
    stmt = application_filters.apply(stmt, application_filters.ApplicationFilters(filters.agency, filters.counselor))
    row = (await db.execute(stmt)).one()
    return {key: int(row._mapping[key]) for key in FUNNEL_COUNTS}


def _choices(rows, *, inactive: bool = False) -> list[dict]:
    """(id, label[, active]) rows as choices; with `inactive`, a deactivated person is labelled so (past work still names them)."""
    return [{"value": str(row[0]), "label": row[1] if not inactive or row[2] else f"{row[1]} (inactive)"} for row in rows]


def _status_order(status: str) -> tuple[int, str]:
    """The stage sequence first, then withdrawn, then any legacy value alphabetically."""
    if status in OVERSEAS_APPLICATION_STAGES:
        return (OVERSEAS_APPLICATION_STAGES.index(status), "")
    return (len(OVERSEAS_APPLICATION_STAGES) + (status != WITHDRAWN), status)


async def application_options(db: AsyncSession) -> dict[str, list[dict]]:
    """MF14: the dropdown choices -- only values present on applications (staff: those in the status history), sorted by label."""
    applied_to = select(OverseasApplication.university_id)
    queries = {
        "agencies": select(AgentOrg.id, AgentOrg.name)
        .join(AgentOrgMember, AgentOrgMember.org_id == AgentOrg.id)
        .where(AgentOrgMember.user_id.in_(select(OverseasApplication.agent_id)))
        .distinct()
        .order_by(AgentOrg.name),
        "counselors": select(User.id, User.full_name, User.active).where(User.id.in_(select(OverseasApplication.counselor_id))).order_by(User.full_name),
        "countries": select(Country.id, Country.name).where(Country.id.in_(select(University.country_id).where(University.id.in_(applied_to)))).order_by(Country.name),
        "universities": select(University.id, University.name).where(University.id.in_(applied_to)).order_by(University.name),
        "courses": select(OverseasCourse.id, OverseasCourse.title + " — " + University.name)
        .join(University, University.id == OverseasCourse.university_id)
        .where(OverseasCourse.id.in_(select(OverseasApplication.course_id)))
        .order_by(OverseasCourse.title, University.name),
        "staff": select(User.id, User.full_name, User.active).where(User.role.in_(FUNNEL_STAFF_ROLES), User.id.in_(select(ApplicationStatusHistory.changed_by_id))).order_by(User.full_name),
    }
    options = {key: _choices((await db.execute(query)).all(), inactive=key in {"counselors", "staff"}) for key, query in queries.items()}
    intakes = (await db.scalars(select(OverseasApplication.intake).distinct().order_by(OverseasApplication.intake))).all()
    statuses = sorted((await db.scalars(select(OverseasApplication.status).distinct())).all(), key=_status_order)
    options["intakes"] = [{"value": intake, "label": intake} for intake in intakes]
    options["statuses"] = [{"value": status, "label": stage_label(status)} for status in statuses]
    return options
