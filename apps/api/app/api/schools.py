"""SCH-003/SCH-001 -- School partner onboarding, and Principal/Coordinator/Teacher/Parent
role-based access to the student roster and activities.

Net-new router. `POST /overseas-admin/schools`/`GET /overseas-admin/schools` (Overseas
Admin creates the School + seed Coordinator, SCH-003) live in `admin.py`'s `agents_router`
(`/overseas-admin` namespace, alongside the Agent approval routes) -- this file covers
everything under the `/school` prefix: the Coordinator-side invite flow and public token
acceptance (SCH-003), and role-scoped student/activity access (SCH-001), per
`API_CONTRACT.md` §12A.
"""

import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _set_auth_cookies
from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import hash_password
from app.models import AuditLog, School, SchoolAccountInvite, SchoolActivity, SchoolActivityAttendance, SchoolParentLink, SchoolStudent, User, UserRoleAssignment
from app.services.integrations import send_notification

router = APIRouter(prefix="/school", tags=["school"])

INVITABLE_ROLES = {"school_principal", "school_teacher", "school_parent"}
INVITE_EXPIRY_DAYS = 7


def _require_coordinator(user: User) -> UUID:
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = user.profile.get("school_id") if user.profile else None
    if not school_id:
        raise HTTPException(403, "This account is not linked to a school")
    return UUID(str(school_id))


@router.post("/team/invites", status_code=201)
async def create_invite(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    school_id = _require_coordinator(user)
    role = payload.get("role")
    if role not in INVITABLE_ROLES:
        raise HTTPException(422, f"role must be one of {sorted(INVITABLE_ROLES)}")
    email = str(payload.get("email", "")).lower().strip()
    full_name = str(payload.get("full_name", "")).strip()
    if not email or not full_name:
        raise HTTPException(422, "email and full_name are required")
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    raw = secrets.token_urlsafe(32)
    invite = SchoolAccountInvite(
        school_id=school_id,
        role=role,
        invited_by_user_id=user.id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        email=email,
        full_name=full_name,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.add(invite)
    await db.flush()
    # SCH-003: this table's own Contracts-phase note (`DATA_MODEL.md` §6.15) leaves invite
    # delivery channel as email-only per `NOT-001` -- no `Notification` row is created
    # since no `User` exists yet to own one; the send is fire-and-forget, same
    # never-block-the-write discipline as every other notification path (`OVS-004-AC02`).
    status_, error = await send_notification("email", {"to": email, "template": "school_invite", "role": role, "school_id": str(school_id), "invite_token": raw})
    db.add(AuditLog(user_id=user.id, action="school.invite_create", entity_type="school_account_invite", entity_id=str(invite.id), metadata_json={"role": role, "school_id": str(school_id), "notification_status": status_, "notification_error": error}))
    await db.commit()
    response = {"id": invite.id, "role": invite.role, "email": invite.email, "status": invite.status, "expires_at": invite.expires_at}
    from app.core.config import settings

    if settings.environment == "development":
        response["development_invite_token"] = raw
    return response


@router.get("/team")
async def list_team(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    school_id = _require_coordinator(user)
    accounts = (
        await db.scalars(select(User).where(User.role.in_(("school_principal", "school_teacher", "school_parent", "school_coordinator"))))
    ).all()
    accounts = [a for a in accounts if (a.profile or {}).get("school_id") == str(school_id)]
    invites = (
        await db.scalars(select(SchoolAccountInvite).where(SchoolAccountInvite.school_id == school_id, SchoolAccountInvite.status == "pending").order_by(SchoolAccountInvite.created_at.desc()))
    ).all()
    return {
        "accounts": [{"id": a.id, "name": a.full_name, "email": a.email, "role": a.role} for a in accounts],
        "pending_invites": [{"id": i.id, "role": i.role, "email": i.email, "full_name": i.full_name, "expires_at": i.expires_at} for i in invites],
    }


@router.post("/invites/{token}/accept", status_code=201)
async def accept_invite(token: str, payload: dict, response: Response, db: AsyncSession = Depends(get_db)):
    digest = hashlib.sha256(token.encode()).hexdigest()
    invite = await db.scalar(select(SchoolAccountInvite).where(SchoolAccountInvite.token_hash == digest))
    if not invite or invite.status != "pending":
        raise HTTPException(409, "This invite has already been used, expired, or was revoked")
    if invite.expires_at < datetime.now(UTC):
        invite.status = "expired"
        await db.commit()
        raise HTTPException(409, "This invite has already been used, expired, or was revoked")
    password = str(payload.get("password", ""))
    if len(password) < 10:
        raise HTTPException(422, "Password must be at least 10 characters")
    if await db.scalar(select(User).where(User.email == invite.email)):
        raise HTTPException(409, "Email already exists")
    # SCH-003-AC06 / DATA_MODEL.md §6.15: the resulting account's `school_id` is always the
    # invite's own `school_id`, never a value supplied at acceptance time -- closes the
    # same class of IDOR risk `AGT-002`/`UNI-001` already guard against, applied here to
    # account creation.
    account = User(
        email=invite.email,
        password_hash=hash_password(password),
        full_name=invite.full_name,
        role=invite.role,
        division="overseas",
        active=True,
        email_verified=False,
        profile={"school_id": str(invite.school_id)},
    )
    db.add(account)
    await db.flush()
    db.add(UserRoleAssignment(user_id=account.id, division="overseas", role=invite.role, is_active=True, assigned_by_user_id=invite.invited_by_user_id, approval_status="approved"))
    invite.status = "accepted"
    invite.accepted_at = datetime.now(UTC)
    invite.accepted_by_user_id = account.id
    db.add(AuditLog(user_id=account.id, action="school.invite_accept", entity_type="school_account_invite", entity_id=str(invite.id), metadata_json={"role": invite.role, "school_id": str(invite.school_id)}))
    await db.commit()
    _set_auth_cookies(response, account)
    return {"id": account.id, "email": account.email, "role": account.role}


# ---------------------------------------------------------------------------------------
# SCH-001 -- School Portal role-based access (Principal/Coordinator/Teacher/Parent)
# ---------------------------------------------------------------------------------------

SCHOOL_ROLES = {"school_principal", "school_coordinator", "school_teacher", "school_parent"}


def _own_school_id(user: User) -> UUID:
    if user.role not in SCHOOL_ROLES:
        raise HTTPException(403, "School role required")
    school_id = (user.profile or {}).get("school_id")
    if not school_id:
        raise HTTPException(403, "This account is not linked to a school")
    return UUID(str(school_id))


def _student_out(s: SchoolStudent) -> dict:
    return {
        "id": s.id,
        "full_name": s.full_name,
        "date_of_birth": s.date_of_birth,
        "grade_or_class": s.grade_or_class,
        "assigned_teacher_user_id": s.assigned_teacher_user_id,
    }


async def _scoped_students_query(db: AsyncSession, user: User, school_id: UUID):
    """SCH-001-AC02/AC03: every query is filtered server-side by the acting role's own
    scope -- own institution for Principal/Coordinator, own institution + assigned only for
    Teacher, own institution + own child(ren) only for Parent. Never a client-supplied
    filter, and a narrower-than-institution scope is a distinct check from the
    institution check itself, not implied by it (same class as `DEC-SCOPE-013`'s
    portfolio-vs-institution distinction for the School service-delivery roles)."""
    stmt = select(SchoolStudent).where(SchoolStudent.school_id == school_id)
    if user.role == "school_teacher":
        stmt = stmt.where(SchoolStudent.assigned_teacher_user_id == user.id)
    elif user.role == "school_parent":
        linked = select(SchoolParentLink.school_student_id).where(SchoolParentLink.parent_user_id == user.id)
        stmt = stmt.where(SchoolStudent.id.in_(linked))
    return stmt


@router.get("/dashboard")
async def school_dashboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"school_coordinator", "school_principal"}:
        raise HTTPException(403, "School Coordinator or Principal role required")
    school_id = _own_school_id(user)
    student_count = len((await db.scalars(select(SchoolStudent.id).where(SchoolStudent.school_id == school_id))).all())
    upcoming = (
        await db.scalars(
            select(SchoolActivity).where(SchoolActivity.school_id == school_id, SchoolActivity.scheduled_at >= datetime.now(UTC)).order_by(SchoolActivity.scheduled_at.asc()).limit(10)
        )
    ).all()
    return {
        "student_count": student_count,
        "upcoming_activities": [{"id": a.id, "title": a.title, "scheduled_at": a.scheduled_at} for a in upcoming],
    }


@router.get("/students")
async def list_students(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    school_id = _own_school_id(user)
    stmt = await _scoped_students_query(db, user, school_id)
    rows = (await db.scalars(stmt.order_by(SchoolStudent.full_name.asc()))).all()
    return [_student_out(s) for s in rows]


@router.get("/students/{student_id}")
async def get_student(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    school_id = _own_school_id(user)
    student = await db.get(SchoolStudent, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    if student.school_id != school_id:
        raise HTTPException(403, "This student is at a different institution")
    if user.role == "school_teacher" and student.assigned_teacher_user_id != user.id:
        raise HTTPException(403, "This student is not assigned to you")
    if user.role == "school_parent":
        linked = await db.scalar(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == user.id, SchoolParentLink.school_student_id == student.id))
        if not linked:
            raise HTTPException(403, "This student is not linked to your account")
    return _student_out(student)


@router.post("/students", status_code=201)
async def create_student(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    full_name = str(payload.get("full_name", "")).strip()
    if not full_name:
        raise HTTPException(422, "full_name is required")
    assigned_teacher_user_id = None
    teacher_email = payload.get("assigned_teacher_email")
    if teacher_email:
        teacher = await db.scalar(select(User).where(User.email == str(teacher_email).lower().strip(), User.role == "school_teacher"))
        if not teacher or (teacher.profile or {}).get("school_id") != str(school_id):
            raise HTTPException(422, "assigned_teacher_email must be an existing Teacher at your own school")
        assigned_teacher_user_id = teacher.id
    dob = payload.get("date_of_birth")
    student = SchoolStudent(
        school_id=school_id,
        full_name=full_name,
        date_of_birth=date.fromisoformat(dob) if dob else None,
        grade_or_class=payload.get("grade_or_class"),
        created_by_user_id=user.id,
        assigned_teacher_user_id=assigned_teacher_user_id,
    )
    db.add(student)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.student_create", entity_type="school_student", entity_id=str(student.id), metadata_json={"school_id": str(school_id)}))
    await db.commit()
    return _student_out(student)


@router.patch("/students/{student_id}")
async def update_student(student_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    student = await db.get(SchoolStudent, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    if student.school_id != school_id:
        raise HTTPException(403, "This student is at a different institution")
    if "full_name" in payload and payload["full_name"]:
        student.full_name = payload["full_name"]
    if "grade_or_class" in payload:
        student.grade_or_class = payload["grade_or_class"]
    if "date_of_birth" in payload:
        student.date_of_birth = date.fromisoformat(payload["date_of_birth"]) if payload["date_of_birth"] else None
    if "assigned_teacher_email" in payload:
        teacher_email = payload["assigned_teacher_email"]
        if teacher_email:
            teacher = await db.scalar(select(User).where(User.email == str(teacher_email).lower().strip(), User.role == "school_teacher"))
            if not teacher or (teacher.profile or {}).get("school_id") != str(school_id):
                raise HTTPException(422, "assigned_teacher_email must be an existing Teacher at your own school")
            student.assigned_teacher_user_id = teacher.id
        else:
            student.assigned_teacher_user_id = None
    db.add(AuditLog(user_id=user.id, action="school.student_update", entity_type="school_student", entity_id=str(student.id), metadata_json={}))
    await db.commit()
    return _student_out(student)


@router.post("/students/{student_id}/parents", status_code=201)
async def link_parent(student_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    student = await db.get(SchoolStudent, student_id)
    if not student or student.school_id != school_id:
        raise HTTPException(404, "Student not found")
    parent_email = str(payload.get("parent_email", "")).lower().strip()
    parent = await db.scalar(select(User).where(User.email == parent_email, User.role == "school_parent"))
    if not parent or (parent.profile or {}).get("school_id") != str(school_id):
        raise HTTPException(422, "parent_email must be an existing Parent at your own school")
    existing = await db.scalar(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == parent.id, SchoolParentLink.school_student_id == student.id))
    if existing:
        raise HTTPException(409, "This parent is already linked to this student")
    link = SchoolParentLink(parent_user_id=parent.id, school_student_id=student.id, linked_by_user_id=user.id)
    db.add(link)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.parent_link", entity_type="school_parent_link", entity_id=str(link.id), metadata_json={"student_id": str(student.id), "parent_id": str(parent.id)}))
    await db.commit()
    return {"id": link.id, "parent_user_id": parent.id, "school_student_id": student.id}


@router.get("/activities")
async def list_activities(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    rows = (await db.scalars(select(SchoolActivity).where(SchoolActivity.school_id == school_id).order_by(SchoolActivity.scheduled_at.desc()))).all()
    return [{"id": a.id, "title": a.title, "scheduled_at": a.scheduled_at} for a in rows]


@router.post("/activities", status_code=201)
async def create_activity(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    title = str(payload.get("title", "")).strip()
    scheduled_at = payload.get("scheduled_at")
    if not title or not scheduled_at:
        raise HTTPException(422, "title and scheduled_at are required")
    activity = SchoolActivity(school_id=school_id, title=title, scheduled_at=datetime.fromisoformat(scheduled_at), created_by_user_id=user.id)
    db.add(activity)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.activity_create", entity_type="school_activity", entity_id=str(activity.id), metadata_json={"school_id": str(school_id)}))
    await db.commit()
    return {"id": activity.id, "title": activity.title, "scheduled_at": activity.scheduled_at}


@router.post("/activities/{activity_id}/attendance")
async def mark_attendance(activity_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    activity = await db.get(SchoolActivity, activity_id)
    if not activity or activity.school_id != school_id:
        raise HTTPException(404, "Activity not found")
    records = payload.get("records", [])
    if not isinstance(records, list) or not records:
        raise HTTPException(422, "records must be a non-empty list of {student_id, present}")
    student_ids = {UUID(str(r["student_id"])) for r in records}
    own_students = set((await db.scalars(select(SchoolStudent.id).where(SchoolStudent.id.in_(student_ids), SchoolStudent.school_id == school_id))).all())
    if own_students != student_ids:
        raise HTTPException(422, "One or more students are not on your own institution's roster")
    for r in records:
        sid = UUID(str(r["student_id"]))
        existing = await db.scalar(select(SchoolActivityAttendance).where(SchoolActivityAttendance.activity_id == activity.id, SchoolActivityAttendance.school_student_id == sid))
        if existing:
            existing.present = bool(r.get("present", True))
            existing.marked_by_user_id = user.id
        else:
            db.add(SchoolActivityAttendance(activity_id=activity.id, school_student_id=sid, present=bool(r.get("present", True)), marked_by_user_id=user.id))
    db.add(AuditLog(user_id=user.id, action="school.attendance_mark", entity_type="school_activity", entity_id=str(activity.id), metadata_json={"count": len(records)}))
    await db.commit()
    return {"activity_id": activity.id, "marked": len(records)}
