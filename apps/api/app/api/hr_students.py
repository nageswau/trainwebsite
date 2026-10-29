"""nehn-017 (DEC-SCOPE-310, API §12HH, RBAC §2.221): HR's read-only view of a student's training -- progress, completion, attendance and
the document types HR may open (services/hr_students H1/H2). Nothing financial is read.

Every route checks the grant first (403), then the HR scope -- hr_team or super_admin; another role given the key has no population rule
and is refused (403, deny by default) -- then the student (404 outside the population, so nothing confirms a student exists). The detail
carries `attendance` only with `attendance.view` and `documents` only with `student_documents.view` (the keys are left out, not null).
A document download is audited, and its audit row commits before the URL is returned (fail closed)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE
from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AuditLog, Batch, Enrollment, ProfileDocument, Program, User
from app.services import hr_students
from app.services import training_progress as progress
from app.services.management_training import NOT_TAKEN
from app.services.permissions import user_has_grant
from app.services.reports.training import CERTIFICATE, Trainer, completed
from app.services.storage import storage

router = APIRouter(prefix="/hr/students", tags=["hr-students"])
logger = get_logger("app.hr_students")

PAGE_SIZE = 25
READERS = hr_students.HR_ROLES | {"super_admin"}
NOT_FOUND = "Student not found"
DOWNLOAD_ACTION = "hr.student_document_download"
TAKEN = Enrollment.status.not_in(NOT_TAKEN)  # H4: a seat shown (counted or dropped); `completed` is the training reports' C1


async def _authorized(db: AsyncSession, user: User, resource: str, action: str) -> None:
    if not await user_has_grant(db, user, resource, action):
        raise HTTPException(403, "You don't have permission to view this")
    if user.role not in READERS:
        raise HTTPException(403, "HR role required")


async def _student(db: AsyncSession, student_id: UUID) -> User:
    student = await db.scalar(select(User).where(User.id == student_id, User.id.in_(hr_students.population())))
    if student is None:
        raise HTTPException(404, NOT_FOUND)
    return student


@router.get("")
async def list_students(
    response: Response, q: str | None = Query(None, max_length=100), page: int = Query(1, ge=1, le=10_000), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """The population by name, 25 a page; `q` matches the Student ID exactly, or the name or email in part."""
    await _authorized(db, user, "student_progress", "view")
    stmt = (
        select(User.id, User.student_code, User.full_name, func.count(Enrollment.id).filter(TAKEN).label("courses"), func.count(Enrollment.id).filter(completed).label("completed"))
        .outerjoin(Enrollment, Enrollment.student_id == User.id)
        .where(User.id.in_(hr_students.population()))
        .group_by(User.id)
    )
    if q and q.strip():
        term = q.strip()
        stmt = stmt.where(or_(func.lower(User.student_code) == term.lower(), User.full_name.icontains(term, autoescape=True), User.email.icontains(term, autoescape=True)))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await db.execute(stmt.order_by(func.lower(User.full_name), User.id).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE))).mappings().all()
    response.headers.update(NO_STORE)
    return {
        "items": [{"id": r["id"], "student_code": r["student_code"], "full_name": r["full_name"], "courses": r["courses"], "completed": r["completed"]} for r in rows],
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
    }


@router.get("/{student_id}")
async def student_detail(student_id: UUID, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _authorized(db, user, "student_progress", "view")
    student = await _student(db, student_id)
    can = {
        "attendance": await user_has_grant(db, user, "attendance", "view"),
        "documents": await user_has_grant(db, user, "student_documents", "view"),
        "download": await user_has_grant(db, user, "student_documents", "download"),
    }
    att = progress.attendance(student_id=student.id)
    rows = (
        (
            await db.execute(
                select(
                    Enrollment.status,
                    Enrollment.progress_percent,
                    Program.title,
                    Batch.name,
                    Trainer.full_name.label("trainer"),
                    CERTIFICATE,
                    completed.label("completed"),
                    att.c.marked,
                    att.c.present,
                    att.c.absent,
                    att.c.late,
                    att.c.excused,
                    progress.percent(att.c.attended, att.c.marked).label("attendance_pct"),
                )
                .select_from(Enrollment)
                .join(Batch, Batch.id == Enrollment.batch_id)
                .join(Program, Program.id == Batch.program_id)
                .outerjoin(Trainer, Trainer.id == Batch.trainer_id)
                .outerjoin(att, att.c.batch_id == Enrollment.batch_id)
                .where(Enrollment.student_id == student.id, TAKEN)
                .order_by(Enrollment.enrolled_on.desc(), Enrollment.id)
            )
        )
        .mappings()
        .all()
    )
    seats = []
    for r in rows:
        seat = {
            "course": r["title"],
            "batch": r["name"],
            "trainer": r["trainer"],
            "status": r["status"],
            "progress": r["progress_percent"],
            "completed": r["completed"],
            "certificate": r["certificate"],
        }
        if can["attendance"]:
            seat["attendance"] = {
                **{k: r[k] or 0 for k in ("marked", "present", "absent", "late", "excused")},
                "attendance_pct": float(r["attendance_pct"]) if r["attendance_pct"] is not None else None,
            }
        seats.append(seat)
    body = {"student": {"id": student.id, "student_code": student.student_code, "full_name": student.full_name}, "seats": seats, "can": can}
    if can["documents"]:
        documents = (await db.scalars(select(ProfileDocument).where(ProfileDocument.user_id == student.id).order_by(ProfileDocument.created_at.desc()))).all()
        body["documents"] = [
            {"id": d.id, "document_type": d.document_type, "original_filename": d.original_filename, "uploaded_at": d.created_at} for d in documents if hr_students.allowed_type(d.document_type)
        ]
    response.headers.update(NO_STORE)
    return body


@router.get("/{student_id}/documents/{document_id}/download")
async def download_document(student_id: UUID, document_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A short-lived URL for one allowed-type document (nehn-003 private serving). A closed type is a 403."""
    await _authorized(db, user, "student_documents", "download")
    student = await _student(db, student_id)
    document = await db.get(ProfileDocument, document_id)
    if document is None or document.user_id != student.id:
        raise HTTPException(404, "Document not found")
    if not hr_students.allowed_type(document.document_type):
        raise HTTPException(403, "This document type is not open to HR")
    key = document.file_url.removeprefix("/local-files/").lstrip("/")
    db.add(AuditLog(user_id=user.id, action=DOWNLOAD_ACTION, entity_type="profile_document", entity_id=str(document.id), metadata_json={"student_id": str(student.id)}))
    await db.commit()
    logger.info(DOWNLOAD_ACTION, extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id), "document_id": str(document.id)}})
    return {"url": storage.presign_download(key), "expires_in": 900 if storage.bucket else None}
