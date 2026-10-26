"""nehn-041 (DEC-SCOPE-291 S1-S9): one search box across every kind of student the caller may already see -- IT students, overseas
students, agency students with no login and school students -- by Student ID, name, email, phone in any format, course, agency or
school. Each kind reads through the scope its own list already applies (nothing new is granted) and is capped at 20.

The ccrm-012 rules are reused as they are: 3-100 characters, a phone-shaped search matches the phone's digits, every search writes one
audit row holding result counts only (never the search text) and those rows are the 30-a-minute budget."""

from collections import defaultdict
from urllib.parse import urlencode
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import agent_denial_reason
from app.models import AgentOrg, AgentOrgMember, AgentStudent, AuditLog, Batch, Enrollment, OverseasApplication, OverseasCourse, Program, School, SchoolStudent, User
from app.services import counselor_search, counselor_students
from app.services.agent_students import student_scope, visible_student_user_ids

KINDS = ("it_student", "overseas_student", "agency_student", "school_student")
DIVISION_KINDS = {"it": {"it_student"}, "overseas": {"overseas_student", "agency_student"}, "school": {"school_student"}}
GROUP_LIMIT = 20
RATE_LIMIT = counselor_search.RATE_LIMIT
AUDIT_ACTION = "student.search"
FORBIDDEN = "This role cannot search students"
AGENT_LIST = "/overseas/agent/students"


ROLE_KINDS = {
    "super_admin": KINDS,
    "it_admin": ("it_student",),
    "overseas_admin": ("overseas_student", "agency_student"),
    "agent": ("overseas_student", "agency_student"),
    "counselor": ("overseas_student",),
}


def caller_kinds(user: User) -> tuple[str, ...]:
    """S1: the kinds this caller already sees on their own lists; anyone else 403."""
    if user.role not in ROLE_KINDS or (user.role == "counselor" and user.division != "overseas"):  # an IT counselor works leads only (tel-017)
        raise HTTPException(403, FORBIDDEN)
    reason = agent_denial_reason(user) if user.role == "agent" else None
    if reason:
        raise HTTPException(403, reason)
    return ROLE_KINDS[user.role]


def _users_link(user: User, student: User) -> str:
    """The Users panel, searched for this student (Super Admin / IT Admin have no per-student page)."""
    base = "/admin/users" if user.role == "super_admin" else "/it/admin/students"
    return f"{base}?{urlencode({'q': student.student_code or student.email})}"


def _join(*parts) -> str:
    return " · ".join(part for part in parts if part)


async def _rows(db: AsyncSession, stmt) -> list:
    return (await db.execute(stmt.limit(GROUP_LIMIT + 1))).all()


async def _it_students(db: AsyncSession, user: User, pattern: str, digits: str | None, program: UUID | None) -> list:
    enrolled = select(Enrollment.student_id).join(Batch, Batch.id == Enrollment.batch_id)
    course_match = User.id.in_(enrolled.join(Program, Program.id == Batch.program_id).where(Program.title.ilike(pattern, escape="\\")))
    stmt = select(User).where(User.role == "it_student", counselor_search._matches(pattern, digits, (User.full_name, User.email, User.student_code), (User.phone,)) | course_match)
    if program:
        stmt = stmt.where(User.id.in_(enrolled.where(Batch.program_id == program)))
    students = [row[0] for row in await _rows(db, stmt.order_by(User.full_name, User.id))]
    titles: dict = defaultdict(list)
    if students:
        found = await db.execute(
            select(Enrollment.student_id, Program.title)
            .join(Batch, Batch.id == Enrollment.batch_id)
            .join(Program, Program.id == Batch.program_id)
            .where(Enrollment.student_id.in_([s.id for s in students]))
            .order_by(Program.title)
        )
        for student_id, title in found.all():
            titles[student_id].append(title)
    return [{"id": s.id, "code": s.student_code, "label": s.full_name, "detail": _join(s.email, s.phone, ", ".join(titles[s.id])), "href": _users_link(user, s)} for s in students]


async def _overseas_students(db: AsyncSession, user: User, pattern: str, digits: str | None) -> list:
    applied = select(OverseasApplication.student_id).join(OverseasCourse, OverseasCourse.id == OverseasApplication.course_id).where(OverseasCourse.title.ilike(pattern, escape="\\"))
    stmt = select(User).where(User.role == "overseas_student", counselor_search._matches(pattern, digits, (User.full_name, User.email, User.student_code), (User.phone,)) | User.id.in_(applied))
    if user.role == "counselor":
        stmt = stmt.where(User.id.in_(counselor_students.visible_student_ids(user)))
    elif user.role == "agent":
        stmt = stmt.where(User.id.in_(visible_student_user_ids(user)))
    students = [row[0] for row in await _rows(db, stmt.order_by(User.full_name, User.id))]

    def href(s: User) -> str:
        if user.role == "super_admin":
            return _users_link(user, s)
        if user.role == "agent":
            return AGENT_LIST
        return f"/overseas/{'admin' if user.role == 'overseas_admin' else 'counselor'}/students/{s.id}"

    return [{"id": s.id, "code": s.student_code, "label": s.full_name, "detail": _join(s.email, s.phone), "href": href(s)} for s in students]


async def _agency_students(db: AsyncSession, user: User, pattern: str, digits: str | None) -> list:
    """Rows with no login only: a linked row is its account, found as an overseas student (S3)."""
    stmt = (
        select(AgentStudent, AgentOrg)
        .join(AgentOrgMember, AgentOrgMember.user_id == AgentStudent.agent_id)
        .join(AgentOrg, AgentOrg.id == AgentOrgMember.org_id)
        .where(
            AgentStudent.student_id.is_(None),
            counselor_search._matches(pattern, digits, (AgentStudent.full_name, AgentStudent.email, AgentStudent.student_code, AgentOrg.name, AgentOrg.prefix), (AgentStudent.phone,)),
        )
    )
    if user.role == "agent":
        stmt = stmt.where(*student_scope(user))
    rows = await _rows(db, stmt.order_by(AgentStudent.full_name, AgentStudent.id))
    return [
        {
            "id": s.id,
            "code": s.student_code,
            "label": s.full_name,
            "detail": _join(s.email, s.phone, org.name),
            "href": AGENT_LIST if user.role == "agent" else f"/overseas/admin/agent-network/{org.id}",
        }
        for s, org in rows
    ]


async def _school_students(db: AsyncSession, user: User, pattern: str, digits: str | None) -> list:
    stmt = (
        select(SchoolStudent, School)
        .join(School, School.id == SchoolStudent.school_id)
        .where(counselor_search._matches(pattern, digits, (SchoolStudent.full_name, SchoolStudent.student_code, School.name), (SchoolStudent.student_mobile,)))
    )
    rows = await _rows(db, stmt.order_by(SchoolStudent.full_name, SchoolStudent.id))
    # S7: no school-student page is open to the Super Admin, so the card names the school instead of linking
    return [{"id": s.id, "code": s.student_code, "label": s.full_name, "detail": _join(s.grade_or_class, school.name), "href": None} for s, school in rows]


async def search(db: AsyncSession, user: User, text: str, pattern: str, *, kinds: tuple[str, ...], program: UUID | None) -> dict:
    """`kinds` are the caller's kinds after the filters; `pattern` is `text` as an escaped `%…%` ILIKE pattern."""
    wait = await counselor_search._wait_seconds(db, user, AUDIT_ACTION)
    if wait:
        raise HTTPException(429, f"Too many searches; try again in {wait} seconds", headers={"Retry-After": str(wait)})
    digits = counselor_search._digits_pattern(text)
    readers = {
        "it_student": lambda: _it_students(db, user, pattern, digits, program),
        "overseas_student": lambda: _overseas_students(db, user, pattern, digits),
        "agency_student": lambda: _agency_students(db, user, pattern, digits),
        "school_student": lambda: _school_students(db, user, pattern, digits),
    }
    groups = {}
    for kind in kinds:
        items = await readers[kind]()
        groups[kind] = {"items": items[:GROUP_LIMIT], "more": len(items) > GROUP_LIMIT}
    db.add(AuditLog(user_id=user.id, action=AUDIT_ACTION, entity_type="search", outcome="searched", metadata_json={kind: len(group["items"]) for kind, group in groups.items()}))
    await db.commit()
    return {"q": text, "groups": groups}
