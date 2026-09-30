"""AGN-004 / DEC-SCOPE-041 -- agent students: scoping, students with no login, duplicate warning.

Functions only (the shape of services/agent_orgs.py); write functions never commit -- the router locks the organisation, writes,
audits and commits. Spec: docs/superpowers/specs/2026-09-30-agn-004-agent-students-design.md.
"""

import logging
import re
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.rbac import is_agent_staff
from app.models import AgentOrgMember, AgentStudent, OverseasApplication, User
from app.services.agent_orgs import STAFF, org_member_ids

logger = logging.getLogger("app.agent_students")

PHONE_MIN_DIGITS = 7


def student_scope(user: User) -> list[ColumnElement]:
    """The agent_students rows the caller may see: the organisation's (AGN-001 D1); a staff member only those assigned to them
    (G4). For a Master this is exactly the AGN-001 clause."""
    clauses = [AgentStudent.agent_id.in_(org_member_ids(user))]
    if is_agent_staff(user):
        clauses.append(AgentStudent.assigned_member_id == user.agent_membership.id)
    return clauses


def visible_student_user_ids(user: User) -> Select:
    """User ids of the linked students (with an account) the caller may see."""
    return select(AgentStudent.student_id).where(*student_scope(user), AgentStudent.student_id.is_not(None))


def application_scope(user: User) -> list[ColumnElement]:
    """The organisation's applications; a staff member only those of their assigned students (G4)."""
    clauses = [OverseasApplication.agent_id.in_(org_member_ids(user))]
    if is_agent_staff(user):
        clauses.append(OverseasApplication.student_id.in_(visible_student_user_ids(user)))
    return clauses


def phone_digits(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")[:20]
    return digits or None


# --- students (with or without a login): reads -----------------------------------------------------------------------------------

Assignee = aliased(User)


def _identity(row: AgentStudent, account: User | None) -> dict:
    """A linked student's name, email and phone come from their own account (F2)."""
    source = account if account is not None else row
    return {"full_name": source.full_name, "email": source.email, "phone": source.phone}


def record_item(row: AgentStudent, account: User | None, member: AgentOrgMember | None, member_user: User | None) -> dict:
    """List shape. An explicit allowlist: agent_id, student_id and phone_digits are never returned."""
    return {
        "id": row.id,
        "has_login": row.student_id is not None,
        **_identity(row, account),
        "preferred_country": row.preferred_country,
        "preferred_intake": row.preferred_intake,
        "status": row.status,
        "assigned_to": {"id": member.id, "code": member.code, "full_name": member_user.full_name, "status": member.status} if member else None,
        "created_at": row.created_at,
    }


def _rows_stmt() -> Select:
    return (
        select(AgentStudent, User, AgentOrgMember, Assignee)
        .outerjoin(User, User.id == AgentStudent.student_id)
        .outerjoin(AgentOrgMember, AgentOrgMember.id == AgentStudent.assigned_member_id)
        .outerjoin(Assignee, Assignee.id == AgentOrgMember.user_id)
    )


async def record_detail(db: AsyncSession, row: AgentStudent) -> dict:
    found = (await db.execute(_rows_stmt().where(AgentStudent.id == row.id).execution_options(populate_existing=True))).one()
    created_by = await db.get(User, row.agent_id)
    archived_by = await db.get(User, row.archived_by_user_id) if row.archived_by_user_id else None
    student = found[0]
    return {
        **record_item(*found),
        "date_of_birth": student.date_of_birth,
        "highest_qualification": student.highest_qualification,
        "institution": student.institution,
        "graduation_year": student.graduation_year,
        "preferred_course": student.preferred_course,
        "notes": student.notes,
        "created_by": created_by.full_name if created_by else None,
        "archived_at": student.archived_at,
        "archived_by": archived_by.full_name if archived_by else None,
        "updated_at": student.updated_at,
    }


async def load_scoped(db: AsyncSession, user: User, student_id, *, lock: bool = False) -> AgentStudent:
    """The caller's student or 404 -- the scope is in the WHERE clause, never checked after loading."""
    stmt = select(AgentStudent).where(AgentStudent.id == student_id, *student_scope(user)).execution_options(populate_existing=True)
    row = await db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise HTTPException(404, "Student not found")
    return row


def _contains(column, term: str):
    """Literal, case-insensitive substring match (`%`, `_` and `\\` escaped), as lookups._pattern."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


async def list_page(db: AsyncSession, user: User, *, q: str | None, include_archived: bool, assigned, limit: int, offset: int) -> dict:
    filters = list(student_scope(user))
    if not include_archived:
        filters.append(AgentStudent.status == "active")
    if assigned == "none":
        filters.append(AgentStudent.assigned_member_id.is_(None))
    elif assigned is not None:
        filters.append(AgentStudent.assigned_member_id == assigned)
    term = (q or "").strip()
    name = func.coalesce(User.full_name, AgentStudent.full_name)
    if term:
        email, phone = func.coalesce(User.email, AgentStudent.email), func.coalesce(User.phone, AgentStudent.phone)
        filters.append(or_(_contains(name, term), _contains(email, term), _contains(phone, term)))
    base = _rows_stmt().where(*filters)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(base.order_by(name, AgentStudent.id).limit(limit).offset(offset))).all()
    return {"items": [record_item(*r) for r in rows], "total": total or 0, "limit": limit, "offset": offset}


# --- duplicate warning (D7, F3, F4) ------------------------------------------------------------------------------------------------


async def find_duplicates(db: AsyncSession, user: User, *, email: str | None, digits: str | None, exclude_id=None) -> tuple[list[dict], int]:
    """Same email or same phone digits inside the caller's agency, archived and linked included. Staff get the rows they can see;
    the others only as a count. Never searches `users` beyond the agency's own linked rows."""
    conditions = []
    if email:
        conditions += [func.lower(AgentStudent.email) == email, func.lower(User.email) == email]
    if digits and len(digits) >= PHONE_MIN_DIGITS:
        conditions += [AgentStudent.phone_digits == digits, func.regexp_replace(User.phone, r"\D", "", "g") == digits]
    else:
        digits = None
    if not conditions:
        return [], 0
    stmt = select(AgentStudent, User).outerjoin(User, User.id == AgentStudent.student_id).where(AgentStudent.agent_id.in_(org_member_ids(user)), or_(*conditions))
    if exclude_id is not None:
        stmt = stmt.where(AgentStudent.id != exclude_id)
    staff_member_id = user.agent_membership.id if is_agent_staff(user) else None
    matches, hidden = [], 0
    for row, account in (await db.execute(stmt.order_by(AgentStudent.created_at, AgentStudent.id))).all():
        if staff_member_id is not None and row.assigned_member_id != staff_member_id:
            hidden += 1
            continue
        ident = _identity(row, account)
        matched_on = [label for label, hit in (("email", bool(email) and (ident["email"] or "").lower() == email), ("phone", bool(digits) and phone_digits(ident["phone"]) == digits)) if hit]
        # str(): an HTTPException detail is not run through FastAPI's JSON encoder, so a UUID would fail to serialise.
        matches.append({"id": str(row.id), "full_name": ident["full_name"], "has_login": row.student_id is not None, "status": row.status, "matched_on": matched_on})
    return matches, hidden


def duplicate_conflict(matches: list[dict], hidden: int) -> HTTPException:
    return HTTPException(409, {"message": "A student with this email or phone already exists in your agency", "code": "possible_duplicate", "matches": matches, "hidden_matches": hidden})


# --- writes (no commit) ------------------------------------------------------------------------------------------------------------


def create_record(db: AsyncSession, user: User, data: dict) -> AgentStudent:
    """D4: a staff creator is the assignee; a Master's student starts unassigned."""
    row = AgentStudent(
        agent_id=user.id,
        student_id=None,
        status="active",
        assigned_member_id=user.agent_membership.id if is_agent_staff(user) else None,
        phone_digits=phone_digits(data.get("phone")),
        updated_by_user_id=user.id,
        **data,
    )
    db.add(row)
    return row


def apply_update(row: AgentStudent, user: User, changes: dict) -> list[str]:
    """Returns the names of the fields whose value actually changed (a no-op PATCH audits nothing)."""
    changed = [field for field, value in changes.items() if getattr(row, field) != value]
    for field in changed:
        setattr(row, field, changes[field])
    if "phone" in changed:
        row.phone_digits = phone_digits(row.phone)
    if changed:
        row.updated_by_user_id = user.id
    return sorted(changed)


def set_archived(row: AgentStudent, user: User, archived: bool) -> None:
    row.status = "archived" if archived else "active"
    row.archived_at = datetime.now(UTC) if archived else None
    row.archived_by_user_id = user.id if archived else None
    row.updated_by_user_id = user.id


async def active_staff_member(db: AsyncSession, user: User, member_id) -> AgentOrgMember:
    """G5: only an ACTIVE staff member of the caller's own agency can receive a new assignment."""
    member = await db.scalar(
        select(AgentOrgMember).where(AgentOrgMember.id == member_id, AgentOrgMember.org_id == user.agent_membership.org_id, AgentOrgMember.role == STAFF, AgentOrgMember.status == "active")
    )
    if member is None:
        raise HTTPException(422, "Choose an active Staff member of this agency")
    return member
