"""ENH-031 (DEC-SCOPE-037) -- read-only lookups behind the searchable reference pickers.

Every lookup applies the scope of the write endpoint it feeds (spec §5), so a picker never offers a value that write would
refuse. Reads only: one structured log line per call (counts, never the search text) and no AuditLog row (ENH-016 D15).
"""

import logging
from collections.abc import Callable
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.identifiers import uuid_reference
from app.core.rbac import agent_denial_reason
from app.models import AgentStudent, Company, Job, JobApplication, OverseasApplication, OverseasCourse, SchoolStudent, University, User
from app.services.agent_orgs import org_member_ids

logger = logging.getLogger("app.lookups")
router = APIRouter(prefix="/lookups", tags=["lookups"])

LINK_MIN_CHARS = 3
LINK_LIMIT = 10
FORBIDDEN = "This role cannot use this lookup"


def _pattern(q: str | None) -> str | None:
    """A literal, case-insensitive substring pattern for `ILIKE ... ESCAPE '\\'`, or None for no filter."""
    term = (q or "").strip()
    if not term:
        return None
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _like(column, pattern: str):
    return column.ilike(pattern, escape="\\")


def _allow(user: User, roles: set[str]) -> None:
    if user.role != "super_admin" and user.role not in roles:
        raise HTTPException(403, FORBIDDEN)
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


@router.get("/overseas-students")
async def overseas_students(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    purpose: Literal["link"] | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: every overseas student. Counselor: students of their own applications. Agent: students linked to their agency.
    `purpose=link` (agent only, D2): search-only (q >= 3 chars), at most 10, masked email, own agency's links left out."""
    stmt = select(User).where(User.role == "overseas_student")
    pattern = _pattern(q)
    if purpose == "link":
        if user.role != "agent":
            raise HTTPException(403, FORBIDDEN)
        _allow(user, {"agent"})
        if len((q or "").strip()) < LINK_MIN_CHARS:
            raise HTTPException(422, f"Type at least {LINK_MIN_CHARS} characters")
        limit = min(limit, LINK_LIMIT)
        stmt = stmt.where(User.id.not_in(select(AgentStudent.student_id).where(AgentStudent.agent_id.in_(org_member_ids(user)))))
    else:
        _allow(user, {"overseas_admin", "counselor", "agent"})
        if user.role == "counselor":
            stmt = stmt.where(User.id.in_(select(OverseasApplication.student_id).where(OverseasApplication.counselor_id == user.id)))
        elif user.role == "agent":
            stmt = stmt.where(User.id.in_(select(AgentStudent.student_id).where(AgentStudent.agent_id.in_(org_member_ids(user)))))
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


@router.get("/overseas-applications")
async def overseas_applications(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    student_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """workflows._assigned_application's rule: student own; counselor own; university_rep own university; agent own agency;
    admin all. Bridged (School) applications have no student_id and are labelled with the school student's name."""
    _allow(user, {"overseas_student", "counselor", "university_rep", "agent", "overseas_admin"})
    student_name = func.coalesce(User.full_name, SchoolStudent.full_name)
    stmt = (
        select(OverseasApplication, student_name, University.name, OverseasCourse.title)
        .join(University, University.id == OverseasApplication.university_id)
        .outerjoin(OverseasCourse, OverseasCourse.id == OverseasApplication.course_id)
        .outerjoin(User, User.id == OverseasApplication.student_id)
        .outerjoin(SchoolStudent, SchoolStudent.id == OverseasApplication.school_student_id)
    )
    if user.role == "overseas_student":
        stmt = stmt.where(OverseasApplication.student_id == user.id)
    elif user.role == "counselor":
        stmt = stmt.where(OverseasApplication.counselor_id == user.id)
    elif user.role == "agent":
        stmt = stmt.where(OverseasApplication.agent_id.in_(org_member_ids(user)))
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
