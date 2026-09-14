"""SCH-003/SCH-001/SCH-002/SCH-004/SCH-005/SCH-006 -- School partner onboarding, role-based
roster/activity access, bulk roster upload, and the three service-delivery modules (career
guidance, psychometric assessment, academic results).

Net-new router. `POST /overseas-admin/schools`/`GET /overseas-admin/schools` (Overseas
Admin creates the School + seed Coordinator, SCH-003) and `POST`/`GET /overseas-admin/
school-staff` (Overseas Admin/Super Admin creates an academic_team/career_counselor/
psychometric_team account and assigns its school portfolio, SCH-004/005/006, DEC-SCOPE-014)
live in `admin.py`'s `agents_router` (`/overseas-admin` namespace) -- this file covers
everything under the `/school` prefix, per `API_CONTRACT.md` §12A.
"""

import csv
import hashlib
import io
import secrets
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _set_auth_cookies
from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import hash_password
from app.models import (
    AuditLog,
    School,
    SchoolAcademicResult,
    SchoolAccountInvite,
    SchoolActivity,
    SchoolActivityAttendance,
    SchoolCareerRecord,
    SchoolParentLink,
    SchoolPsychometricRecord,
    SchoolResultStatusHistory,
    SchoolRosterUploadBatch,
    SchoolRosterUploadRow,
    SchoolStaffAssignment,
    SchoolStudent,
    User,
    UserRoleAssignment,
)
from app.services.integrations import send_notification

router = APIRouter(prefix="/school", tags=["school"])
SERVICE_DELIVERY_ROLES = {"academic_team", "career_counselor", "psychometric_team"}

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


@router.get("/students/roster-template")
async def roster_template(user: User = Depends(get_current_user)):
    # Registered before /students/{student_id} below: FastAPI/Starlette match routes in
    # registration order, so a static "roster-template" segment must be declared ahead of
    # a dynamic {student_id} path parameter on the same GET prefix, or every request here
    # would instead 422 trying (and failing) to parse "roster-template" as a UUID.
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(ROSTER_TEMPLATE_HEADERS)
    writer.writerow(["Jane Doe", "2015-04-12", "Grade 5", ""])
    return Response(content=buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=school-roster-template.csv"})


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


# ---------------------------------------------------------------------------------------
# SCH-002 -- School Coordinator bulk student roster upload (template-download-first)
# ---------------------------------------------------------------------------------------

# API_CONTRACT.md §12A flags the exact template column schema as Contracts-phase detail,
# not fixed by DATA_MODEL.md §6.13 -- resolved here as technical contract design, mapped
# directly from SCH-001's own already-built SchoolStudent creation fields (POST /school/
# students), not an invented field list.
ROSTER_TEMPLATE_HEADERS = ["full_name", "date_of_birth", "grade_or_class", "assigned_teacher_email"]


async def _batch_report(db: AsyncSession, batch: SchoolRosterUploadBatch) -> dict:
    rows = (
        await db.scalars(select(SchoolRosterUploadRow).where(SchoolRosterUploadRow.batch_id == batch.id).order_by(SchoolRosterUploadRow.row_number.asc()))
    ).all()
    return {
        "id": batch.id,
        "status": batch.status,
        "total_rows": batch.total_rows,
        "accepted_count": batch.accepted_count,
        "rejected_count": batch.rejected_count,
        "rows": [{"row_number": r.row_number, "status": r.status, "error_message": r.error_message, "created_student_id": r.created_student_id} for r in rows],
    }


@router.post("/students/bulk-upload", status_code=201)
async def bulk_upload_students(
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    if not idempotency_key:
        raise HTTPException(422, "Idempotency-Key header is required")
    school_id = _own_school_id(user)

    # A repeat with the same key replays the original batch's result rather than
    # re-processing the file -- API_CONTRACT.md §0.2's idempotency convention, same shape
    # as PAY-001's checkout replay.
    existing_batch = await db.scalar(select(SchoolRosterUploadBatch).where(SchoolRosterUploadBatch.idempotency_key == idempotency_key))
    if existing_batch:
        if existing_batch.school_id != school_id:
            raise HTTPException(403, "This upload batch belongs to a different institution")
        return await _batch_report(db, existing_batch)

    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(raw)))

    batch = SchoolRosterUploadBatch(school_id=school_id, uploaded_by_user_id=user.id, idempotency_key=idempotency_key, total_rows=len(rows), status="processing")
    db.add(batch)
    await db.flush()

    accepted = 0
    rejected = 0
    for i, row in enumerate(rows, start=1):
        full_name = (row.get("full_name") or "").strip()
        error = None
        student_dob = None
        assigned_teacher_user_id = None
        if not full_name:
            error = "full_name is required"
        if not error:
            dob_raw = (row.get("date_of_birth") or "").strip()
            if dob_raw:
                try:
                    student_dob = date.fromisoformat(dob_raw)
                except ValueError:
                    error = f"date_of_birth '{dob_raw}' is not a valid date (expected YYYY-MM-DD)"
        if not error:
            teacher_email = (row.get("assigned_teacher_email") or "").strip().lower()
            if teacher_email:
                teacher = await db.scalar(select(User).where(User.email == teacher_email, User.role == "school_teacher"))
                if not teacher or (teacher.profile or {}).get("school_id") != str(school_id):
                    error = f"assigned_teacher_email '{teacher_email}' is not an existing Teacher at your own school"
                else:
                    assigned_teacher_user_id = teacher.id
        # SCH-002-AC04: a row that fails validation is recorded and skipped -- it never
        # blocks or discards the rows around it.
        if error:
            db.add(SchoolRosterUploadRow(batch_id=batch.id, row_number=i, status="rejected", error_message=error))
            rejected += 1
            continue
        student = SchoolStudent(
            school_id=school_id, full_name=full_name, date_of_birth=student_dob,
            grade_or_class=(row.get("grade_or_class") or "").strip() or None,
            created_by_user_id=user.id, assigned_teacher_user_id=assigned_teacher_user_id,
        )
        db.add(student)
        await db.flush()
        db.add(SchoolRosterUploadRow(batch_id=batch.id, row_number=i, status="accepted", created_student_id=student.id))
        accepted += 1

    batch.accepted_count = accepted
    batch.rejected_count = rejected
    batch.status = "completed"
    db.add(AuditLog(user_id=user.id, action="school.roster_bulk_upload", entity_type="school_roster_upload_batch", entity_id=str(batch.id), metadata_json={"total": len(rows), "accepted": accepted, "rejected": rejected}))
    await db.commit()
    return await _batch_report(db, batch)


@router.get("/roster-uploads/{batch_id}")
async def get_roster_upload(batch_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    batch = await db.get(SchoolRosterUploadBatch, batch_id)
    if not batch or batch.school_id != school_id:
        raise HTTPException(404, "Upload batch not found")
    return await _batch_report(db, batch)


# ---------------------------------------------------------------------------------------
# SCH-004/005/006 -- Career Guidance & Counselling, Psychometric Assessment, Academic
# Results. All three specialized roles are scoped to a school portfolio (DEC-SCOPE-013),
# not a single institution.
# ---------------------------------------------------------------------------------------


async def _portfolio_school_ids(db: AsyncSession, user: User) -> set:
    rows = (await db.scalars(select(SchoolStaffAssignment.school_id).where(SchoolStaffAssignment.user_id == user.id))).all()
    return set(rows)


async def _student_in_portfolio(db: AsyncSession, user: User, student_id: UUID) -> SchoolStudent:
    student = await db.get(SchoolStudent, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    portfolio = await _portfolio_school_ids(db, user)
    if student.school_id not in portfolio:
        raise HTTPException(403, "This student is at a school outside your own portfolio")
    return student


async def _readable_students(db: AsyncSession, user: User) -> set:
    """The set of school_student_id values this reading role (Coordinator/Principal/
    Teacher/Parent) may see published/visible service-delivery content for -- reuses the
    exact same scoping as SCH-001's own roster access, since it's the same underlying
    own-institution/assigned/own-child rule (SCH-001-AC02/AC03)."""
    school_id = _own_school_id(user)
    stmt = await _scoped_students_query(db, user, school_id)
    return set((await db.scalars(stmt.with_only_columns(SchoolStudent.id))).all())


@router.get("/portfolio-students")
async def list_portfolio_students(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Shared across the three specialized roles -- their own school portfolio's students,
    with each student's own school name for clarity since a portfolio can span several
    schools (unlike SCH-001's own-institution-only roles)."""
    if user.role not in SERVICE_DELIVERY_ROLES:
        raise HTTPException(403, "Academic Team, Career Counselor, or Psychometric Team role required")
    portfolio = await _portfolio_school_ids(db, user)
    if not portfolio:
        return []
    rows = (
        await db.execute(select(SchoolStudent, School).join(School, School.id == SchoolStudent.school_id).where(SchoolStudent.school_id.in_(portfolio)).order_by(SchoolStudent.full_name.asc()))
    ).all()
    return [{"id": s.id, "full_name": s.full_name, "school_id": s.school_id, "school_name": sc.name} for s, sc in rows]


# --- SCH-004: Career Guidance & Counselling ---------------------------------------------

@router.post("/career-counselor/records", status_code=201)
async def create_career_record(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "career_counselor":
        raise HTTPException(403, "Career Counselor role required")
    student_id = payload.get("school_student_id")
    if not student_id:
        raise HTTPException(422, "school_student_id is required")
    student = await _student_in_portfolio(db, user, UUID(str(student_id)))
    record_type = payload.get("record_type")
    if record_type not in {"guidance_session", "counselling_note", "recommendation"}:
        raise HTTPException(422, "record_type must be one of guidance_session, counselling_note, recommendation")
    notes = str(payload.get("notes", "")).strip()
    if not notes:
        raise HTTPException(422, "notes is required")
    record = SchoolCareerRecord(school_student_id=student.id, career_counselor_user_id=user.id, record_type=record_type, notes=notes)
    db.add(record)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.career_record_create", entity_type="school_career_record", entity_id=str(record.id), metadata_json={"record_type": record_type}))
    await db.commit()
    return {"id": record.id, "school_student_id": record.school_student_id, "record_type": record.record_type, "notes": record.notes, "created_at": record.created_at}


@router.get("/career-counselor/records")
async def list_career_counselor_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "career_counselor":
        raise HTTPException(403, "Career Counselor role required")
    portfolio = await _portfolio_school_ids(db, user)
    if not portfolio:
        return []
    student_ids = (await db.scalars(select(SchoolStudent.id).where(SchoolStudent.school_id.in_(portfolio)))).all()
    rows = (await db.scalars(select(SchoolCareerRecord).where(SchoolCareerRecord.school_student_id.in_(student_ids)).order_by(SchoolCareerRecord.created_at.desc()))).all()
    return [{"id": r.id, "school_student_id": r.school_student_id, "record_type": r.record_type, "notes": r.notes, "created_at": r.created_at} for r in rows]


@router.get("/career-records")
async def list_readable_career_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Read-only for School Coordinator/Principal/Teacher/Parent, own scope -- no
    Draft/Published gate for this content, unlike results (visible as soon as created)."""
    if user.role not in {"school_coordinator", "school_principal", "school_teacher", "school_parent"}:
        raise HTTPException(403, "School role required")
    readable = await _readable_students(db, user)
    if not readable:
        return []
    rows = (await db.scalars(select(SchoolCareerRecord).where(SchoolCareerRecord.school_student_id.in_(readable)).order_by(SchoolCareerRecord.created_at.desc()))).all()
    return [{"id": r.id, "school_student_id": r.school_student_id, "record_type": r.record_type, "notes": r.notes, "created_at": r.created_at} for r in rows]


# --- SCH-005: Psychometric Assessment ----------------------------------------------------

@router.post("/psychometric-team/records", status_code=201)
async def create_psychometric_record(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "psychometric_team":
        raise HTTPException(403, "Psychometric Team role required")
    student_id = payload.get("school_student_id")
    if not student_id:
        raise HTTPException(422, "school_student_id is required")
    student = await _student_in_portfolio(db, user, UUID(str(student_id)))
    assessment_type = str(payload.get("assessment_type", "")).strip()
    if not assessment_type:
        raise HTTPException(422, "assessment_type is required")
    record = SchoolPsychometricRecord(
        school_student_id=student.id, psychometric_team_user_id=user.id, assessment_type=assessment_type,
        report_url=payload.get("report_url"), status="completed" if payload.get("report_url") else "assigned",
    )
    db.add(record)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.psychometric_record_create", entity_type="school_psychometric_record", entity_id=str(record.id), metadata_json={"assessment_type": assessment_type}))
    await db.commit()
    return {"id": record.id, "school_student_id": record.school_student_id, "assessment_type": record.assessment_type, "report_url": record.report_url, "status": record.status, "created_at": record.created_at}


@router.patch("/psychometric-team/records/{record_id}")
async def update_psychometric_record(record_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "psychometric_team":
        raise HTTPException(403, "Psychometric Team role required")
    record = await db.get(SchoolPsychometricRecord, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    await _student_in_portfolio(db, user, record.school_student_id)
    if "report_url" in payload:
        record.report_url = payload["report_url"]
        record.status = "completed" if payload["report_url"] else record.status
    db.add(AuditLog(user_id=user.id, action="school.psychometric_record_update", entity_type="school_psychometric_record", entity_id=str(record.id), metadata_json={}))
    await db.commit()
    return {"id": record.id, "school_student_id": record.school_student_id, "assessment_type": record.assessment_type, "report_url": record.report_url, "status": record.status}


@router.get("/psychometric-team/records")
async def list_psychometric_team_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "psychometric_team":
        raise HTTPException(403, "Psychometric Team role required")
    portfolio = await _portfolio_school_ids(db, user)
    if not portfolio:
        return []
    student_ids = (await db.scalars(select(SchoolStudent.id).where(SchoolStudent.school_id.in_(portfolio)))).all()
    rows = (await db.scalars(select(SchoolPsychometricRecord).where(SchoolPsychometricRecord.school_student_id.in_(student_ids)).order_by(SchoolPsychometricRecord.created_at.desc()))).all()
    return [{"id": r.id, "school_student_id": r.school_student_id, "assessment_type": r.assessment_type, "report_url": r.report_url, "status": r.status, "created_at": r.created_at} for r in rows]


@router.get("/psychometric-records")
async def list_readable_psychometric_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"school_coordinator", "school_principal", "school_teacher", "school_parent"}:
        raise HTTPException(403, "School role required")
    readable = await _readable_students(db, user)
    if not readable:
        return []
    rows = (await db.scalars(select(SchoolPsychometricRecord).where(SchoolPsychometricRecord.school_student_id.in_(readable)).order_by(SchoolPsychometricRecord.created_at.desc()))).all()
    return [{"id": r.id, "school_student_id": r.school_student_id, "assessment_type": r.assessment_type, "status": r.status, "created_at": r.created_at} for r in rows]


# --- SCH-006: Academic Results (Draft -> Verified -> Published) -------------------------

def _result_out(r: SchoolAcademicResult) -> dict:
    percentage = round(float(r.marks_obtained) / float(r.max_marks) * 100, 2) if float(r.max_marks) else None
    return {
        "id": r.id, "school_student_id": r.school_student_id, "academic_year": r.academic_year, "term": r.term,
        "subject": r.subject, "max_marks": float(r.max_marks), "marks_obtained": float(r.marks_obtained),
        "percentage": percentage, "grade": r.grade, "status": r.status,
        "uploaded_by_user_id": r.uploaded_by_user_id, "verified_by_user_id": r.verified_by_user_id,
        "published_by_user_id": r.published_by_user_id,
    }


@router.post("/academic-team/results", status_code=201)
async def create_academic_result(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    student_id = payload.get("school_student_id")
    if not student_id:
        raise HTTPException(422, "school_student_id is required")
    student = await _student_in_portfolio(db, user, UUID(str(student_id)))
    try:
        max_marks = float(payload.get("max_marks"))
        marks_obtained = float(payload.get("marks_obtained"))
    except (TypeError, ValueError):
        raise HTTPException(422, "max_marks and marks_obtained must be numbers")
    subject = str(payload.get("subject", "")).strip()
    academic_year = str(payload.get("academic_year", "")).strip()
    term = str(payload.get("term", "")).strip()
    if not subject or not academic_year or not term:
        raise HTTPException(422, "academic_year, term, and subject are required")
    result = SchoolAcademicResult(
        school_student_id=student.id, academic_year=academic_year, term=term, subject=subject,
        max_marks=max_marks, marks_obtained=marks_obtained, grade=payload.get("grade"),
        status="draft", uploaded_by_user_id=user.id,
    )
    db.add(result)
    await db.flush()
    db.add(SchoolResultStatusHistory(result_id=result.id, from_status="none", to_status="draft", changed_by_user_id=user.id))
    db.add(AuditLog(user_id=user.id, action="school.result_create", entity_type="school_academic_result", entity_id=str(result.id), metadata_json={"subject": subject}))
    await db.commit()
    return _result_out(result)


@router.patch("/academic-team/results/{result_id}")
async def update_academic_result(result_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    result = await db.get(SchoolAcademicResult, result_id)
    if not result:
        raise HTTPException(404, "Result not found")
    await _student_in_portfolio(db, user, result.school_student_id)
    if result.status != "draft":
        raise HTTPException(409, "Only a Draft result can be edited")
    for field in ("subject", "academic_year", "term", "grade"):
        if field in payload:
            setattr(result, field, payload[field])
    for field in ("max_marks", "marks_obtained"):
        if field in payload:
            setattr(result, field, float(payload[field]))
    db.add(AuditLog(user_id=user.id, action="school.result_update", entity_type="school_academic_result", entity_id=str(result.id), metadata_json={}))
    await db.commit()
    return _result_out(result)


async def _advance_result(result_id: UUID, target: str, user: User, db: AsyncSession) -> SchoolAcademicResult:
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    result = await db.get(SchoolAcademicResult, result_id)
    if not result:
        raise HTTPException(404, "Result not found")
    await _student_in_portfolio(db, user, result.school_student_id)
    expected_from = "draft" if target == "verified" else "verified"
    if result.status != expected_from:
        raise HTTPException(409, f"A result must be {expected_from} before it can be moved to {target} -- no skip-stage transition")
    # DEC-ROLE-007: the uploader may never also verify or publish their own entry.
    if result.uploaded_by_user_id == user.id:
        raise HTTPException(403, "A different Academic Team member must perform this step -- you cannot verify or publish your own upload")
    from_status = result.status
    result.status = target
    if target == "verified":
        result.verified_by_user_id = user.id
        result.verified_at = datetime.now(UTC)
    else:
        result.published_by_user_id = user.id
        result.published_at = datetime.now(UTC)
    db.add(SchoolResultStatusHistory(result_id=result.id, from_status=from_status, to_status=target, changed_by_user_id=user.id))
    db.add(AuditLog(user_id=user.id, action=f"school.result_{target}", entity_type="school_academic_result", entity_id=str(result.id), metadata_json={}))
    await db.commit()
    return result


@router.post("/academic-team/results/{result_id}/verify")
async def verify_academic_result(result_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await _advance_result(result_id, "verified", user, db)
    return _result_out(result)


@router.post("/academic-team/results/{result_id}/publish")
async def publish_academic_result(result_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await _advance_result(result_id, "published", user, db)
    return _result_out(result)


@router.get("/academic-team/results")
async def list_academic_team_results(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    portfolio = await _portfolio_school_ids(db, user)
    if not portfolio:
        return []
    student_ids = (await db.scalars(select(SchoolStudent.id).where(SchoolStudent.school_id.in_(portfolio)))).all()
    rows = (await db.scalars(select(SchoolAcademicResult).where(SchoolAcademicResult.school_student_id.in_(student_ids)).order_by(SchoolAcademicResult.created_at.desc()))).all()
    return [_result_out(r) for r in rows]


@router.get("/results")
async def list_readable_results(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Read-only for School Coordinator/Principal/Teacher/Parent, own scope -- filtered to
    status='published' only. A Draft/Verified result is never returned, even indirectly
    (SCH-006-AC02)."""
    if user.role not in {"school_coordinator", "school_principal", "school_teacher", "school_parent"}:
        raise HTTPException(403, "School role required")
    readable = await _readable_students(db, user)
    if not readable:
        return []
    rows = (
        await db.scalars(
            select(SchoolAcademicResult).where(SchoolAcademicResult.school_student_id.in_(readable), SchoolAcademicResult.status == "published").order_by(SchoolAcademicResult.published_at.desc())
        )
    ).all()
    return [_result_out(r) for r in rows]
