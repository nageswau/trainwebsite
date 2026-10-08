"""ENH-031 (DEC-SCOPE-039) -- read-only lookups behind the searchable reference pickers.

Every lookup applies the scope of the write endpoint it feeds (spec §5), so a picker never offers a value that write would
refuse. Reads only: one structured log line per call (counts, never the search text) and no AuditLog row (ENH-016 D15).
"""

import logging
import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.identifiers import uuid_reference
from app.core.rbac import agent_denial_reason
from app.models import AgentStudent, AuditLog, Company, Country, Job, JobApplication, OverseasApplication, OverseasCourse, School, SchoolStudent, University, User
from app.services.agent_orgs import org_member_ids
from app.services.agent_students import application_scope, visible_student_user_ids

logger = logging.getLogger("app.lookups")
router = APIRouter(prefix="/lookups", tags=["lookups"])

LINK_MIN_CHARS = 3
LINK_LIMIT = 10
# Owner decision after the final review (2026-09-30): the agent link search cannot be used to probe emails or harvest the
# directory -- email matches only in full, names only from the start of a word, and each agent gets 30 searches a minute
# (counted from audit rows, the house no-new-table throttle pattern; the rows carry no search text).
LINK_RATE_LIMIT = 30
LINK_RATE_WINDOW = timedelta(minutes=1)
LINK_AUDIT_ACTION = "lookup.agent_link_search"
FORBIDDEN = "This role cannot use this lookup"
# upc-002 QA-02: names a user may type that the stored name lacks. The catalogue keeps "USA" and "Dubai (UAE)" (AC1), and a few
# countries are commonly known by another name. Matched as a case-insensitive substring, like the name itself.
COUNTRY_ALIASES = {
    "US": ("United States", "United States of America", "America"),
    "AE": ("United Arab Emirates", "UAE", "Emirates"),
    "GB": ("UK", "Great Britain", "Britain", "England", "Scotland", "Wales", "Northern Ireland"),
    "NL": ("Holland",),
    "KR": ("Korea, Republic of",),
    "CZ": ("Czech Republic",),
    "TR": ("Turkey",),
}


def _pattern(q: str | None) -> str | None:
    """A literal, case-insensitive substring pattern for `ILIKE ... ESCAPE '\\'`, or None for no filter."""
    term = (q or "").strip()
    if not term:
        return None
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _like(column, pattern: str):
    return column.ilike(pattern, escape="\\")


def _allow(user: User, roles: set[str], division: str | None = None) -> None:
    if user.role != "super_admin" and user.role not in roles:
        raise HTTPException(403, FORBIDDEN)
    # tel-017 (DEC-SCOPE-076): a counselor can be IT now, so the overseas lookups check the division as workflows._require does.
    if division and user.role != "super_admin" and user.division != division:
        raise HTTPException(403, "Wrong EduSphere division")
    reason = agent_denial_reason(user)
    if reason:
        raise HTTPException(403, reason)


async def _page(db: AsyncSession, stmt: Select, limit: int, to_item: Callable, lookup: str, user: User) -> dict:
    rows = (await db.execute(stmt.limit(limit + 1))).all()
    truncated = len(rows) > limit
    items = [to_item(row) for row in rows[:limit]]
    logger.info("lookup", extra={"extra_fields": {"lookup": lookup, "role": user.role, "count": len(items), "truncated": truncated}})
    return {"items": items, "truncated": truncated}


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


async def _link_wait_seconds(db: AsyncSession, user: User) -> int:
    """Seconds before this agent may search again; 0 means allowed."""
    now = datetime.now(UTC)
    recent = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.user_id == user.id, AuditLog.action == LINK_AUDIT_ACTION, AuditLog.created_at > now - LINK_RATE_WINDOW)
            .order_by(AuditLog.created_at.desc())
            .limit(LINK_RATE_LIMIT)
        )
    ).all()
    if len(recent) < LINK_RATE_LIMIT:
        return 0
    return max(1, math.ceil((recent[-1] + LINK_RATE_WINDOW - now).total_seconds()))


@router.get("/overseas-students")
async def overseas_students(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    purpose: Literal["link"] | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: every overseas student. Counselor: students of their own applications. Agent: students linked to their agency.
    `purpose=link` (agent only, D2 as revised 2026-09-30): search-only (q >= 3 chars), at most 10, masked email, own agency's
    links left out; the email must be typed in full, names match from the start of a word, 30 searches a minute per agent."""
    stmt = select(User).where(User.role == "overseas_student")
    pattern = _pattern(q)
    if purpose == "link":
        if user.role != "agent":
            raise HTTPException(403, FORBIDDEN)
        _allow(user, {"agent"})
        term = (q or "").strip()
        if len(term) < LINK_MIN_CHARS:
            raise HTTPException(422, f"Type at least {LINK_MIN_CHARS} characters")
        wait = await _link_wait_seconds(db, user)
        if wait:
            logger.warning("agent_link_search_throttled", extra={"extra_fields": {"actor_id": str(user.id), "wait_seconds": wait}})
            raise HTTPException(429, f"Too many student searches; try again in {wait} seconds", headers={"Retry-After": str(wait)})
        limit = min(limit, LINK_LIMIT)
        escaped = pattern[1:-1]  # the literal, escaped term without _pattern's surrounding wildcards
        stmt = stmt.where(
            # AGN-004: skip rows with no login -- one NULL in a NOT IN subquery would make it match nothing at all.
            User.id.not_in(select(AgentStudent.student_id).where(AgentStudent.agent_id.in_(org_member_ids(user)), AgentStudent.student_id.is_not(None))),
            or_(func.lower(User.email) == term.lower(), _like(User.full_name, f"{escaped}%"), _like(User.full_name, f"% {escaped}%")),
        )
        db.add(AuditLog(user_id=user.id, action=LINK_AUDIT_ACTION, entity_type="lookup", outcome="searched", metadata_json={"purpose": "link"}))
        await db.commit()
    else:
        _allow(user, {"overseas_admin", "counselor", "agent"}, "overseas")
        if user.role == "counselor":
            stmt = stmt.where(User.id.in_(select(OverseasApplication.student_id).where(OverseasApplication.counselor_id == user.id)))
        elif user.role == "agent":
            stmt = stmt.where(User.id.in_(visible_student_user_ids(user)))  # AGN-004 (G4): staff see their assigned students only
        if pattern:
            stmt = stmt.where(or_(_like(User.full_name, pattern), _like(User.email, pattern)))
    stmt = stmt.order_by(User.full_name, User.id)
    masked = purpose == "link"
    return await _page(
        db, stmt, limit,
        lambda row: {"id": row[0].id, "label": row[0].full_name, "detail": mask_email(row[0].email) if masked else row[0].email},
        "overseas-students", user,
    )


def _join(*parts) -> str:
    return " · ".join(part for part in parts if part)


@router.get("/overseas-counselors")
async def overseas_counselors(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AGN-023 follow-up: the Overseas Admin's Assign counsellor picker -- active overseas counselors by name (name + id only).
    Replaces the picker's read of /admin/users, whose 500-row cap hid older counselors."""
    _allow(user, {"overseas_admin"}, "overseas")
    stmt = select(User).where(User.role == "counselor", User.division == "overseas", User.active.is_(True))
    pattern = _pattern(q)
    if pattern:
        stmt = stmt.where(_like(User.full_name, pattern))
    stmt = stmt.order_by(User.full_name, User.id)
    return await _page(db, stmt, limit, lambda row: {"id": row[0].id, "label": row[0].full_name, "detail": None}, "overseas-counselors", user)


@router.get("/overseas-applications")
async def overseas_applications(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    student_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """workflows._assigned_application's rule: student own; counselor own; university_rep own university; agent own agency;
    admin all. Bridged (School) applications have no student_id and are labelled with the school student's name. Agency students
    with no login (AGN-008) are labelled with the agency record's name."""
    _allow(user, {"overseas_student", "counselor", "university_rep", "agent", "overseas_admin"}, "overseas")
    student_name = func.coalesce(User.full_name, AgentStudent.full_name, SchoolStudent.full_name)
    stmt = (
        select(OverseasApplication, student_name, University.name, OverseasCourse.title)
        .join(University, University.id == OverseasApplication.university_id)
        .outerjoin(OverseasCourse, OverseasCourse.id == OverseasApplication.course_id)
        .outerjoin(User, User.id == OverseasApplication.student_id)
        .outerjoin(SchoolStudent, SchoolStudent.id == OverseasApplication.school_student_id)
        .outerjoin(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)
    )
    if user.role == "overseas_student":
        stmt = stmt.where(OverseasApplication.student_id == user.id)
    elif user.role == "counselor":
        stmt = stmt.where(OverseasApplication.counselor_id == user.id)
    elif user.role == "agent":
        stmt = stmt.where(*application_scope(user))
    elif user.role == "university_rep":
        university_id = uuid_reference(user.profile.get("university_id"), "university reference", required=False)
        stmt = stmt.where(OverseasApplication.university_id == university_id if university_id else false())
    if student_id:
        stmt = stmt.where(OverseasApplication.student_id == student_id)
    pattern = _pattern(q)
    if pattern:
        stmt = stmt.where(or_(_like(student_name, pattern), _like(University.name, pattern), _like(OverseasCourse.title, pattern), _like(OverseasApplication.application_reference, pattern)))
    stmt = stmt.order_by(student_name, University.name, OverseasApplication.id)
    return await _page(
        db, stmt, limit,
        lambda row: {"id": row[0].id, "label": row[1] or "Unnamed student", "detail": _join(row[2], row[3], row[0].status)},
        "overseas-applications", user,
    )


@router.get("/it-job-applications")
async def it_job_applications(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every job application -- the scope schedule_interview / create offer accept today."""
    _allow(user, {"placement_team", "hr_team", "it_admin"})
    stmt = (
        select(JobApplication, User.full_name, Job.title, Company.name)
        .join(User, User.id == JobApplication.student_id)
        .join(Job, Job.id == JobApplication.job_id)
        .join(Company, Company.id == Job.company_id)
    )
    pattern = _pattern(q)
    if pattern:
        stmt = stmt.where(or_(_like(User.full_name, pattern), _like(Job.title, pattern), _like(Company.name, pattern)))
    stmt = stmt.order_by(User.full_name, JobApplication.id)
    return await _page(
        db, stmt, limit,
        lambda row: {"id": row[0].id, "label": row[1], "detail": _join(row[2], row[3], row[0].status)},
        "it-job-applications", user,
    )


@router.get("/countries")
async def countries(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """upc-002: every country, catalogue and internal ISO rows alike, by name, ISO code or common alias; an exact code ranks first."""
    _allow(user, {"overseas_admin"}, "overseas")
    stmt = select(Country)
    pattern = _pattern(q)
    if pattern:
        term = (q or "").strip()
        code = term.upper()
        aliased = [iso2 for iso2, names in COUNTRY_ALIASES.items() if any(term.lower() in name.lower() for name in names)]
        stmt = stmt.where(or_(_like(Country.name, pattern), Country.iso2 == code, Country.iso2.in_(aliased)))
        stmt = stmt.order_by((Country.iso2 == code).desc().nulls_last())
    stmt = stmt.order_by(Country.name, Country.id)
    return await _page(
        db, stmt, limit,
        lambda row: {"id": row[0].id, "label": row[0].name, "detail": _join(row[0].iso2, row[0].region) or None},
        "countries", user,
    )


@router.get("/schools")
async def schools(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The School->Overseas bridge's first step (D4): every partner school, for the bridge's roles."""
    _allow(user, {"overseas_admin", "counselor"}, "overseas")
    stmt = select(School)
    pattern = _pattern(q)
    if pattern:
        stmt = stmt.where(or_(_like(School.name, pattern), _like(School.school_code, pattern)))
    stmt = stmt.order_by(School.name, School.id)
    return await _page(db, stmt, limit, lambda row: {"id": row[0].id, "label": row[0].name, "detail": row[0].school_code}, "schools", user)


@router.get("/school-students")
async def school_students(
    school_id: UUID,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The bridge's second step (D4): students of ONE chosen school only -- no cross-school name browsing."""
    _allow(user, {"overseas_admin", "counselor"}, "overseas")
    if await db.get(School, school_id) is None:
        raise HTTPException(404, "School not found")
    stmt = select(SchoolStudent).where(SchoolStudent.school_id == school_id)
    pattern = _pattern(q)
    if pattern:
        stmt = stmt.where(or_(_like(SchoolStudent.full_name, pattern), _like(SchoolStudent.student_code, pattern)))
    stmt = stmt.order_by(SchoolStudent.full_name, SchoolStudent.id)
    return await _page(
        db, stmt, limit,
        lambda row: {"id": row[0].id, "label": row[0].full_name, "detail": _join(row[0].grade_or_class, row[0].student_code)},
        "school-students", user,
    )
