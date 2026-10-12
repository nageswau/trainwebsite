"""mgmt-003 (Management Appendix B): the single owner of the Command Center's figures. It reads the module tables live and keeps no
copies. The business snapshot S1-S15 (spec MS1-MS17) is one SELECT of fifteen scalar subqueries, so the query count is fixed at one
and every figure is read from the same moment."""

from datetime import date

from sqlalchemy import ScalarSelect, and_, distinct, exists, func, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AcademicYear,
    AgentOrg,
    AgentOrgMember,
    AgentStudent,
    Batch,
    Candidate,
    Company,
    Enrollment,
    OverseasApplication,
    RecruiterProfile,
    School,
    SchoolStudent,
    University,
    User,
)
from app.partnership_stages import GROUPS
from app.recruiter_stages import ORDER as COMPANY_STAGES
from app.services.agent_applications import WITHDRAWN

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
