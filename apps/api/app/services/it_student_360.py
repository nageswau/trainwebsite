"""itc-029 (DEC-SCOPE-358): the IT student 360 for the IT counselor, HR and the IT Admin (spec 2026-11-03-itc-029-it-student-360-design.md).

Read only, no table of its own: each section is read live from its own record through that feature's reader (AC1), with batched queries
so the count is fixed whatever the number of enrolments (AC3). Scope (S1) is itc-028's: the IT counselor their itc-003 students, HR the
nehn-017 pool (`student_progress.view`), the IT Admin any IT student; out of scope is the same 404 as a missing student (AC2); a trainer
or any other role is 403. A section the reader may not see is omitted, never null (S3, Q-28: HR gets no fee, profile, lead, risk or
notifications -- HR's existing rules). Nothing is logged or audited (S5)."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.lead_stages import label as stage_label
from app.models import (
    Assessment,
    AssessmentAttempt,
    Assignment,
    Batch,
    Enquiry,
    Enrollment,
    ItStudentProfile,
    Notification,
    NotificationPreference,
    Program,
    StudentRiskFlag,
    Submission,
    User,
)  # fmt: skip
from app.services import fee_accounts, hr_reviews, it_student_counselors, it_student_notes, lead_timeline, student_resumes
from app.services import training_progress as progress
from app.services.permissions import user_has_grant

READERS_ONLY = "Only the student's IT counselor, HR or the IT Admin can open the student 360"
NO_LEAD_FOR_HR = "The lead history is for the IT counselor and the IT Admin"
VIEWERS = {"it_admin": "admin", "counselor": "counselor", "hr_team": "hr"}
SECTIONS = ("contact", "profile", "lead", "enrollments", "fee", "risk", "feedback", "resumes", "hr_review", "notes", "notifications")
HR_SECTIONS = ("contact", "enrollments", "feedback", "resumes", "hr_review", "notes")
PROFILE_FIELDS = ("city", "qualification", "emergency_contact_name", "emergency_contact_relation", "emergency_contact_phone")
RECENT, NOTIFICATIONS, EXCERPT = 5, 10, 300
Staff = aliased(User)


def _viewer(user: User) -> str:
    """The reader's viewer key, or 403. The student itself is resolved by `it_student_notes.staff_student` (scope + 404)."""
    viewer = VIEWERS.get(user.role)
    if viewer is None or (viewer != "hr" and user.division != "it"):
        raise HTTPException(403, READERS_ONLY)
    return viewer


async def _lead(db: AsyncSession, student_id: UUID):
    """The IT lead the student was converted from (`uq_enquiries_converted_user`: at most one), with its owner's name."""
    stmt = (
        select(Enquiry, Staff.full_name).outerjoin(Staff, Staff.id == Enquiry.owner_id)
        .where(Enquiry.converted_user_id == student_id, Enquiry.division == "it")
    )  # fmt: skip
    return (await db.execute(stmt)).first()


def _lead_out(row, user: User) -> dict | None:
    if row is None:
        return None
    lead, owner = row
    return {
        "id": lead.id, "lead_code": lead.lead_code, "stage": lead.status, "stage_label": stage_label(lead.status), "owner": owner,
        "created_at": lead.created_at, "converted_at": lead.converted_at,
        "href": f"/it/counselor/leads/{lead.id}" if lead.owner_id == user.id else None,  # the counselor's lead page opens only their own
    }  # fmt: skip


async def _enrollments(db: AsyncSession, student: User, *, attendance: bool) -> tuple[list[Enrollment], list[dict]]:
    att = progress.attendance(student_id=student.id)
    trainer = aliased(User)
    rows = (
        await db.execute(
            select(Enrollment, Batch, Program.title, trainer.full_name, progress.percent(att.c.attended, att.c.counted), att.c.marked)
            .join(Batch, Batch.id == Enrollment.batch_id).join(Program, Program.id == Batch.program_id)
            .outerjoin(trainer, trainer.id == Batch.trainer_id).outerjoin(att, att.c.batch_id == Enrollment.batch_id)
            .where(Enrollment.student_id == student.id).order_by(Enrollment.created_at.desc(), Enrollment.id)
        )
    ).all()  # fmt: skip
    out = []
    for e, batch, program, trainer_name, pct, marked in rows:
        row = {
            "id": e.id, "enrollment_code": e.enrollment_code, "program": program, "batch": batch.name, "trainer": trainer_name, "status": e.status,
            "start_date": e.start_date or batch.start_date, "end_date": e.end_date or batch.end_date, "delivery_mode": e.delivery_mode or batch.mode,
            "progress_percent": e.progress_percent,  # S6: the trainer's figure until itc-022 computes it
        }  # fmt: skip
        if attendance:  # nehn-017's rule for HR: attendance only with `attendance.view`
            row |= {"attendance_percent": float(pct) if pct is not None else None, "attendance_marked": marked or 0}
        out.append(row)
    return [e for e, *_ in rows], out


async def _fee(db: AsyncSession, enrollments: list[Enrollment]) -> dict:
    accounts = await fee_accounts.accounts(db, enrollments)
    billed = [a["balance"] for a in accounts if a["state"] != "not_billed"]
    return {"accounts": accounts, "balance": sum(billed) if billed else None}


async def _risk(db: AsyncSession, student: User) -> list[dict]:
    rows = await db.execute(
        select(StudentRiskFlag, Batch.name).join(Batch, Batch.id == StudentRiskFlag.batch_id)
        .where(StudentRiskFlag.student_id == student.id, StudentRiskFlag.cleared_at.is_(None)).order_by(StudentRiskFlag.raised_at.desc())
    )  # fmt: skip
    return [
        {"enrollment_id": f.enrollment_id, "batch": batch, "reasons": f.reasons, "attendance_percent": f.attendance_percent,
         "assessment_percent": f.assessment_percent, "consecutive_absences": f.consecutive_absences, "raised_at": f.raised_at}
        for f, batch in rows.all()
    ]  # fmt: skip


def _excerpt(text: str) -> str:
    return text if len(text) <= EXCERPT else text[: EXCERPT - 1] + "…"


async def _feedback(db: AsyncSession, student: User) -> list[dict]:
    """S6: the newest graded assignment and assessment feedback (itc-022's trainer feedback notes do not exist yet)."""
    submissions = await db.execute(
        select(Submission, Assignment.title, Assignment.max_score, Staff.full_name).join(Assignment, Assignment.id == Submission.assignment_id)
        .outerjoin(Staff, Staff.id == Submission.graded_by_id).where(Submission.student_id == student.id, func.length(func.trim(Submission.feedback)) > 0)
        .order_by(func.coalesce(Submission.graded_at, Submission.updated_at).desc()).limit(RECENT)
    )  # fmt: skip
    attempts = await db.execute(
        select(AssessmentAttempt, Assessment.title, Assessment.max_score).join(Assessment, Assessment.id == AssessmentAttempt.assessment_id)
        .where(AssessmentAttempt.student_id == student.id, func.length(func.trim(AssessmentAttempt.feedback)) > 0)
        .order_by(func.coalesce(AssessmentAttempt.graded_at, AssessmentAttempt.updated_at).desc()).limit(RECENT)
    )  # fmt: skip
    items = [
        {"kind": "assignment", "title": title, "score": s.score, "max_score": top, "feedback": _excerpt(s.feedback), "by": grader, "at": s.graded_at or s.updated_at}
        for s, title, top, grader in submissions.all()
    ] + [
        {"kind": "assessment", "title": title, "score": float(a.score) if a.score is not None else None, "max_score": top, "feedback": _excerpt(a.feedback),
         "by": None, "at": a.graded_at or a.updated_at}
        for a, title, top in attempts.all()
    ]  # fmt: skip
    return sorted(items, key=lambda i: i["at"], reverse=True)[:RECENT]


async def _profile(db: AsyncSession, student: User) -> dict:
    """itc-012's record for its own readers (C1: the counselor and the IT Admin -- never HR)."""
    profile = await db.get(ItStudentProfile, student.id)
    calls_opt_out = await db.scalar(select(NotificationPreference.calls_opt_out).where(NotificationPreference.user_id == student.id))
    return {field: getattr(profile, field, None) for field in PROFILE_FIELDS} | {"calls_allowed": not calls_opt_out}


async def _notifications(db: AsyncSession, student: User) -> list[dict]:
    """S4: what was sent, never the body (older notices carry free text)."""
    rows = await db.execute(
        select(Notification.id, Notification.title, Notification.event_type, Notification.created_at, Notification.read)
        .where(Notification.user_id == student.id).order_by(Notification.created_at.desc(), Notification.id).limit(NOTIFICATIONS)
    )  # fmt: skip
    return [{"id": i, "title": title, "event_type": kind, "sent_at": at, "read": read} for i, title, kind, at, read in rows.all()]


async def read(db: AsyncSession, user: User, student_id: UUID) -> dict:
    viewer = _viewer(user)
    student = await it_student_notes.staff_student(db, user, student_id)
    hr = viewer == "hr"
    counselor = (await it_student_counselors.counselors_of(db, [student.id])).get(student.id)
    enrollments, seats = await _enrollments(db, student, attendance=not hr or await user_has_grant(db, user, "attendance", "view"))
    out = {
        "student": {"id": student.id, "full_name": student.full_name, "student_code": student.student_code, "active": student.active},
        "viewer": viewer, "sections": list(HR_SECTIONS if hr else SECTIONS),
        "contact": {"email": student.email, "phone": student.phone, "counselor": {"id": counselor.id, "full_name": counselor.full_name} if counselor else None},
        "enrollments": seats,
        "feedback": await _feedback(db, student),
        "resumes": {"items": (await student_resumes.listing(db, student, hr_only=hr))["items"]},
        "hr_review": await hr_reviews.staff_task(db, student.id),
        "notes": {k: v for k, v in (await it_student_notes.page(db, user, student, RECENT, 0)).items() if k in ("items", "total")},
    }  # fmt: skip
    if not hr:
        out |= {
            "profile": await _profile(db, student), "lead": _lead_out(await _lead(db, student.id), user), "fee": await _fee(db, enrollments),
            "risk": await _risk(db, student), "notifications": await _notifications(db, student),
        }  # fmt: skip
    return out


async def lead_timeline_page(db: AsyncSession, user: User, student_id: UUID, limit: int, offset: int) -> dict:
    """The `lead` section's timeline (tel-015), for the same audience: the counselor and the IT Admin."""
    if _viewer(user) == "hr":
        raise HTTPException(403, NO_LEAD_FOR_HR)
    student = await it_student_notes.staff_student(db, user, student_id)
    row = await _lead(db, student.id)
    if row is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    return await lead_timeline.page(db, row[0].id, limit, offset)
